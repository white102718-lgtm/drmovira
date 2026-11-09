import type { Recordable, UserInfo } from '@vben/types';

import { ref } from 'vue';
import { useRouter } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';
import { resetAllStores, useAccessStore, useUserStore } from '@vben/stores';

import notification from 'ant-design-vue/es/notification';
import { defineStore } from 'pinia';

import type { AuthApi } from '#/api/core/auth';

import { ApiBusinessError } from '#/api/backend-response';
import {
  feishuCallbackApi,
  loginApi,
  logoutApi,
  mfaBindApi,
  mfaVerifyApi,
} from '#/api/core/auth';
import { getUserInfoApi } from '#/api/core/user';
import { isFusionDemoMode } from '#/api/fusion/mode';
import { $t } from '#/locales';
import { clearSelectedDemoRole } from '#/mock/demo-role-preview';
import { resetRoutes } from '#/router';

export const useAuthStore = defineStore('auth', () => {
  const accessStore = useAccessStore();
  const userStore = useUserStore();
  const router = useRouter();

  const loginLoading = ref(false);

  /** MFA阶段状态：none=密码登录/未进入MFA, setup=待绑定, verify=待验证 */
  const mfaStep = ref<'none' | 'setup' | 'verify'>('none');
  /** 密码登录返回的临时挑战令牌（仅内存，不持久化） */
  const challengeToken = ref('');
  /** 挑战有效秒数（仅用于前端倒计时，实际有效期以后端Redis为准） */
  const challengeExpiresInSeconds = ref(0);
  /** MFA绑定密钥（仅MFA_BIND_REQUIRED时存在，仅内存，离开页面必须清空） */
  const mfaSecret = ref('');
  /** otpauth URI用于二维码生成（仅MFA_BIND_REQUIRED时存在，仅内存） */
  const otpAuthUri = ref('');

  /**
   * 消费后端返回的统一 LoginResult，根据 loginStatus 分支处理。
   * - SUCCESS: 保存JWT + 权限 + 用户信息，跳转首页
   * - MFA_BIND_REQUIRED: 保存挑战和MFA密钥，切换到绑定页面
   * - MFA_VERIFY_REQUIRED: 保存挑战，切换到验证页面
   *
   * 兼容性兜底：旧版后端部署可能不返回 `loginStatus` 字段。
   * - 若存在 `accessToken`，视为 SUCCESS
   * - 若存在 `challengeToken` 且 `mfaSecret`，视为 MFA_BIND_REQUIRED
   * - 若仅存在 `challengeToken`，视为 MFA_VERIFY_REQUIRED
   * 新版后端返回 `loginStatus` 后，兜底逻辑自动失效。
   */
  async function consumeLoginResult(
    result: AuthApi.LoginResult,
    onSuccess?: () => Promise<void> | void,
  ) {
    // 兼容旧版后端：loginStatus 缺失时按字段存在性推断
    const status: AuthApi.LoginStatus | undefined =
      result.loginStatus ??
      (result.accessToken
        ? 'SUCCESS'
        : result.challengeToken
          ? result.mfaSecret
            ? 'MFA_BIND_REQUIRED'
            : 'MFA_VERIFY_REQUIRED'
          : undefined);

    switch (status) {
      case 'MFA_BIND_REQUIRED': {
        if (!result.challengeToken || !result.mfaSecret || !result.otpAuthUri) {
          throw new Error('MFA绑定响应字段不完整，请重新登录');
        }
        challengeToken.value = result.challengeToken;
        challengeExpiresInSeconds.value =
          result.challengeExpiresInSeconds ?? 300;
        mfaSecret.value = result.mfaSecret;
        otpAuthUri.value = result.otpAuthUri;
        mfaStep.value = 'setup';
        return;
      }

      case 'MFA_VERIFY_REQUIRED': {
        if (!result.challengeToken) {
          throw new Error('MFA验证响应缺少挑战令牌，请重新登录');
        }
        challengeToken.value = result.challengeToken;
        challengeExpiresInSeconds.value =
          result.challengeExpiresInSeconds ?? 300;
        // 安全：已绑定用户的MFA密钥绝不能返回前端，确保这里不留旧值
        mfaSecret.value = '';
        otpAuthUri.value = '';
        mfaStep.value = 'verify';
        return;
      }

      case 'SUCCESS': {
        if (!result.accessToken) {
          throw new Error('登录成功响应缺少访问令牌');
        }
        await handleLoginSuccess(result, onSuccess);
        resetMfaState();
        return;
      }

      default:
        throw new Error(`未知的登录状态: ${status ?? 'undefined'}`);
    }
  }

  /** 使用手机号和密码登录。 */
  async function authLogin(
    params: Recordable<any>,
    onSuccess?: () => Promise<void> | void,
  ) {
    let userInfo: null | UserInfo = null;
    try {
      loginLoading.value = true;
      const phone = (params.phone as string) ?? '';
      const password = (params.password as string) ?? '';
      const result = await loginApi({ phone, password });
      await consumeLoginResult(result, onSuccess);
      if (
        result.loginStatus === 'SUCCESS' &&
        accessStore.accessToken &&
        userStore.userInfo
      ) {
        userInfo = userStore.userInfo;
      }
    } finally {
      loginLoading.value = false;
    }
    return { userInfo };
  }

  /** 使用飞书 OAuth 回调结果登录并复用统一会话落地流程。 */
  async function authFeishuLogin(
    params: AuthApi.FeishuCallbackParams,
    onSuccess?: () => Promise<void> | void,
  ) {
    try {
      loginLoading.value = true;
      const result = await feishuCallbackApi(params);
      await consumeLoginResult(result, onSuccess);
    } finally {
      loginLoading.value = false;
    }
  }

  /**
   * MFA首次绑定（提交6位动态码）
   * 绑定成功会直接返回 SUCCESS + JWT，内部自动 handleLoginSuccess
   */
  async function authMfaBind(
    totpCode: string,
    onSuccess?: () => Promise<void> | void,
  ) {
    let userInfo: null | UserInfo = null;
    try {
      loginLoading.value = true;
      const result = await mfaBindApi({
        challengeToken: challengeToken.value,
        totpCode,
      });
      await consumeLoginResult(result, onSuccess);
      if (
        result.loginStatus === 'SUCCESS' &&
        accessStore.accessToken &&
        userStore.userInfo
      ) {
        userInfo = userStore.userInfo;
      }
    } catch (error: any) {
      // 业务错误处理（详见 FRONTEND_API_RESPONSE_INTEGRATION.md §4）：
      // - 410/411/412/414：MFA 挑战失效或状态变化，清除挑战并返回密码登录步骤
      // - 413：动态码错误/过期/已使用，停留 MFA 步骤继续重试，不重置挑战
      // - 4xx 其他：交给调用页面展示
      // - 5xx/6xx：已由全局拦截器展示
      if (
        error instanceof ApiBusinessError &&
        (error.code === 410 ||
          error.code === 411 ||
          error.code === 412 ||
          error.code === 414)
      ) {
        resetMfaState();
      }
      throw error;
    } finally {
      loginLoading.value = false;
    }
    return { userInfo };
  }

  /**
   * MFA验证（已绑定用户，提交6位动态码）
   * 验证成功会直接返回 SUCCESS + JWT
   */
  async function authMfaVerify(
    totpCode: string,
    onSuccess?: () => Promise<void> | void,
  ) {
    let userInfo: null | UserInfo = null;
    try {
      loginLoading.value = true;
      const result = await mfaVerifyApi({
        challengeToken: challengeToken.value,
        totpCode,
      });
      await consumeLoginResult(result, onSuccess);
      if (
        result.loginStatus === 'SUCCESS' &&
        accessStore.accessToken &&
        userStore.userInfo
      ) {
        userInfo = userStore.userInfo;
      }
    } catch (error: any) {
      // 业务错误处理同 authMfaBind：
      // - 410/411/412/414：挑战失效，清除并返回密码登录步骤
      // - 413：动态码错误，停留 MFA 页面继续重试
      if (
        error instanceof ApiBusinessError &&
        (error.code === 410 ||
          error.code === 411 ||
          error.code === 412 ||
          error.code === 414)
      ) {
        resetMfaState();
      }
      throw error;
    } finally {
      loginLoading.value = false;
    }
    return { userInfo };
  }

  /**
   * 登录成功统一处理：保存JWT、写入权限码、拉用户信息、跳转首页
   * 新协议直接用后端响应的 permissions，不再调用返回空数组的 getAccessCodesApi
   */
  async function handleLoginSuccess(
    result: AuthApi.LoginResult,
    onSuccess?: () => Promise<void> | void,
  ) {
    // 1. 保存正式JWT（只有 SUCCESS 才走到这里，accessToken 已在消费入口校验非空）
    accessStore.setAccessToken(result.accessToken!);

    // 2. 直接写入登录响应返回的权限码（不要再被 getAccessCodesApi 的空数组覆盖）
    accessStore.setAccessCodes(result.permissions ?? []);

    // 3. 调用 /auth/me 拉取完整用户信息
    const userInfo = await fetchUserInfo();
    userStore.setUserInfo(userInfo);

    // 4. 登录过期弹层态清理 / 路由跳转
    if (accessStore.loginExpired) {
      accessStore.setLoginExpired(false);
    } else {
      onSuccess
        ? await onSuccess?.()
        : await router.push(
            userInfo.homePath || preferences.app.defaultHomePath,
          );
    }

    // 5. 登录成功提示
    if (userInfo?.realName) {
      notification.success({
        description: `${$t('authentication.loginSuccessDesc')}:${userInfo?.realName}`,
        duration: 3,
        message: $t('authentication.loginSuccess'),
      });
    }

    return userInfo;
  }

  /**
   * 清空全部MFA临时敏感数据
   * 必须在：登录成功、挑战过期/失效、用户主动返回登录表单时调用
   * 注意这些数据只在内存中，不写入任何持久化存储
   */
  function resetMfaState() {
    mfaStep.value = 'none';
    challengeToken.value = '';
    challengeExpiresInSeconds.value = 0;
    mfaSecret.value = '';
    otpAuthUri.value = '';
  }

  async function logout(redirect = true) {
    try {
      await logoutApi();
    } catch {
      // 不做任何处理
    }

    // Demo logout is a role-switch boundary: the next visit starts at the
    // local role selector. Production identity/session behavior stays intact.
    if (isFusionDemoMode()) {
      clearSelectedDemoRole();
      resetRoutes();
      accessStore.setAccessMenus([]);
      accessStore.setAccessRoutes([]);
      accessStore.setAccessCodes([]);
    }

    try {
      resetAllStores();
    } catch {
      // A legacy setup-style Pinia store may not expose $reset().  Session
      // cleanup and the login redirect must still complete in that case.
    }
    resetMfaState();
    accessStore.setLoginExpired(false);

    // 退出后只进入当前前端登录页，禁止跳转旧 OAuth/IdP 站点。
    if (redirect) {
      await router.replace(LOGIN_PATH);
    }
  }

  async function fetchUserInfo(silent = false) {
    let userInfo: null | UserInfo = null;
    const authUserInfo = await getUserInfoApi(silent);
    // 兼容尚未返回 permissions 的旧版 /auth/me：保留登录响应中已经写入的权限码。
    if (Array.isArray(authUserInfo.permissions)) {
      accessStore.setAccessCodes(authUserInfo.permissions);
    }
    userInfo = authUserInfo;
    userStore.setUserInfo(userInfo);
    return userInfo;
  }

  function $reset() {
    loginLoading.value = false;
    resetMfaState();
  }

  return {
    $reset,
    authLogin,
    authFeishuLogin,
    authMfaBind,
    authMfaVerify,
    challengeExpiresInSeconds,
    challengeToken,
    fetchUserInfo,
    loginLoading,
    mfaSecret,
    mfaStep,
    otpAuthUri,
    resetMfaState,
    logout,
  };
});
