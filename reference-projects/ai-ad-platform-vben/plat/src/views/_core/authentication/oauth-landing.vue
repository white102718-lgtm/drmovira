<script lang="ts" setup>
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';
import { useAccessStore } from '@vben/stores';

import { getServiceTokenApi } from '#/api/core/auth';
import { useAuthStore } from '#/store/auth';

defineOptions({ name: 'OAuthLanding' });

const router = useRouter();
const accessStore = useAccessStore();
const authStore = useAuthStore();

const errorText = ref('');

const ERROR_MESSAGES: Record<string, string> = {
  not_provisioned: 'Mpower 中不存在此用户，请联系管理员开通后再登录。',
  disabled: '该账号已被禁用,请联系管理员。',
  no_phone: '账号未绑定手机号,请联系管理员补充后再登录。',
};

onMounted(async () => {
  const hash = window.location.hash || '';
  const errMatch = hash.match(/(?:^#|&)error=([^&]+)/);

  if (errMatch) {
    const code = decodeURIComponent(errMatch[1] ?? '');
    errorText.value = ERROR_MESSAGES[code] || `登录失败:${code}`;
    history.replaceState(null, '', window.location.pathname);
    return;
  }

  // 登录态由后端写进 HttpOnly cookie,这里靠 cookie 拉用户信息确认。
  // silent=true:登出后落地这里 cookie 已清,401 不弹错误提示,直接跳登录
  try {
    await authStore.fetchUserInfo(true);
  } catch {
    // cookie 缺失或失效时回到当前前端登录页，不再访问旧 OAuth 站点。
    await router.replace({
      path: LOGIN_PATH,
      query: { redirect: preferences.app.defaultHomePath },
    });
    return;
  }

  // 本地会话走 cookie;再取一个转发 token 放进 accessStore,供同源兄弟服务
  // (automationApi/aiReport)按 Authorization: Bearer 识别用户。失败则退回占位值,
  // 不影响本地后端(它认 cookie)。accessStore.accessToken 同时也是 vben 的登录态标志。
  try {
    accessStore.setAccessToken(await getServiceTokenApi());
  } catch {
    accessStore.setAccessToken('cookie');
  }
  history.replaceState(null, '', window.location.pathname);
  await router.replace(preferences.app.defaultHomePath);
});

function backToLogin() {
  void router.replace(LOGIN_PATH);
}
</script>

<template>
  <main class="oauth-landing-page">
    <section v-if="errorText" class="oauth-landing-card" role="alert">
      <h1>无法登录</h1>
      <div class="oauth-error-text">
        {{ errorText }}
      </div>
      <button class="oauth-login-button" type="button" @click="backToLogin">
        重新登录
      </button>
    </section>
    <div v-else class="oauth-loading" aria-live="polite">登录中，请稍候...</div>
  </main>
</template>

<style scoped>
.oauth-landing-page {
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: var(--adpulse-page-gutter);
  color: var(--adpulse-text);
  background: linear-gradient(145deg, #f8fafc, #f3f7fb);
}

.oauth-landing-card {
  width: min(380px, 100%);
  padding: calc(var(--adpulse-card-padding) * 1.5);
  text-align: center;
  background: var(--adpulse-surface);
  border: 1px solid var(--adpulse-border);
  border-radius: var(--adpulse-card-radius);
  box-shadow: var(--adpulse-elevated-shadow);
}

.oauth-landing-card h1 {
  margin: 0 0 12px;
  font-size: var(--adpulse-page-title-size);
  font-weight: 650;
}

.oauth-error-text {
  margin-bottom: 20px;
  font-size: var(--adpulse-control-font-size);
  line-height: 1.6;
  color: var(--adpulse-danger);
}

.oauth-login-button {
  min-height: var(--adpulse-control-height);
  padding: 0 18px;
  font-size: var(--adpulse-control-font-size);
  color: white;
  background: var(--adpulse-primary);
  border: 0;
  border-radius: var(--adpulse-radius);
}

.oauth-login-button:hover {
  background: var(--adpulse-primary-hover);
}

.oauth-loading {
  font-size: var(--adpulse-control-font-size);
  color: var(--adpulse-text-muted);
}
</style>
