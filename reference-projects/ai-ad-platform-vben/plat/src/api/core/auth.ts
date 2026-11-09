import { publicBackendClient, backendClient } from '#/api/request';

export namespace AuthApi {
  /** 登录状态 */
  export type LoginStatus =
    | 'SUCCESS'
    | 'MFA_BIND_REQUIRED'
    | 'MFA_VERIFY_REQUIRED';

  /** 手机号密码登录参数 */
  export interface LoginParams {
    /** 中国大陆手机号，兼容 +86 国际区号格式 */
    phone: string;
    /** 密码 */
    password: string;
  }

  /** MFA绑定/验证请求参数 */
  export interface MfaCodeParams {
    /** 密码登录返回的临时挑战令牌 */
    challengeToken: string;
    /** 验证器生成的6位动态码 */
    totpCode: string;
  }

  /** 飞书 OAuth 回调参数 */
  export interface FeishuCallbackParams {
    code: string;
    state: string;
  }

  /** 飞书 OAuth 登录初始化结果 */
  export interface FeishuOAuthInitResult {
    expiresInSeconds: number;
    gotoUrl: string;
  }

  /** 登录/MFA阶段统一响应 */
  export interface LoginResult {
    loginStatus: LoginStatus;
    /** MFA挑战令牌(仅MFA阶段存在) */
    challengeToken?: string;
    /** 挑战有效秒数(仅MFA阶段存在) */
    challengeExpiresInSeconds?: number;
    /** MFA绑定密钥(仅MFA_BIND_REQUIRED存在,仅展示一次) */
    mfaSecret?: string;
    /** otpauth URI(仅MFA_BIND_REQUIRED存在,用于生成二维码) */
    otpAuthUri?: string;
    /** 正式访问令牌(仅SUCCESS存在) */
    accessToken?: string;
    /** 令牌类型(仅SUCCESS存在) */
    tokenType?: 'Bearer';
    /** 令牌有效秒数(仅SUCCESS存在) */
    expiresInSeconds?: number;
    /** 用户ID(仅SUCCESS存在) */
    userId?: string;
    /** 用户显示名(仅SUCCESS存在) */
    displayName?: string;
    /** 用户权限码(仅SUCCESS存在) */
    permissions?: string[];
    /** 令牌签发时间ISO字符串(仅SUCCESS存在) */
    issuedAt?: string;
  }

  /** 刷新Token结果(旧协议预留,当前未使用) */
  export interface RefreshTokenResult {
    data: string;
    status: number;
  }
}

/**
 * 手机号密码登录(匿名接口)
 * - loginStatus=SUCCESS: 直接返回JWT
 * - loginStatus=MFA_BIND_REQUIRED: 返回挑战和MFA密钥,进入绑定流程
 * - loginStatus=MFA_VERIFY_REQUIRED: 返回挑战,进入验证流程
 */
export function loginApi(data: AuthApi.LoginParams) {
  return publicBackendClient.post<AuthApi.LoginResult>('/auth/login', data);
}

/** 初始化飞书扫码或网页跳转登录所需的一次性授权地址。 */
export function initializeFeishuLoginApi() {
  return publicBackendClient.post<AuthApi.FeishuOAuthInitResult>(
    '/auth/feishu/qr/init',
  );
}

/** 使用飞书回调授权码完成系统登录。 */
export function feishuCallbackApi(data: AuthApi.FeishuCallbackParams) {
  return publicBackendClient.post<AuthApi.LoginResult>(
    '/auth/feishu/callback',
    data,
  );
}

/** 已登录用户初始化飞书绑定二维码。 */
export function initializeFeishuBindApi() {
  return backendClient.post<AuthApi.FeishuOAuthInitResult>(
    '/auth/feishu/bind/init',
  );
}

/** 已登录用户把飞书身份绑到当前账号。 */
export function bindFeishuApi(data: AuthApi.FeishuCallbackParams) {
  return backendClient.post<{ feishuOpenId?: string }>(
    '/auth/feishu/bind/callback',
    data,
  );
}

/**
 * 首次绑定MFA动态码并完成登录(匿名接口)
 * 成功后返回 loginStatus=SUCCESS 和正式JWT
 */
export function mfaBindApi(data: AuthApi.MfaCodeParams) {
  return publicBackendClient.post<AuthApi.LoginResult>('/auth/mfa/bind', data);
}

/**
 * 验证已绑定用户的MFA动态码并完成登录(匿名接口)
 * 成功后返回 loginStatus=SUCCESS 和正式JWT
 */
export function mfaVerifyApi(data: AuthApi.MfaCodeParams) {
  return publicBackendClient.post<AuthApi.LoginResult>(
    '/auth/mfa/verify',
    data,
  );
}

/**
 * 刷新accessToken(当前后端未启用,保留占位)
 */
export async function refreshTokenApi(): Promise<AuthApi.RefreshTokenResult> {
  return { data: '', status: 200 };
}

/**
 * 退出登录
 */
export function logoutApi() {
  return backendClient.post('/auth/logout');
}

/**
 * 取后端签发的转发 token(当前后端未启用,保留占位)
 */
export async function getServiceTokenApi(): Promise<string> {
  return '';
}

/**
 * 获取用户权限码(已废弃)
 * 新协议中权限码在登录成功响应的 permissions 字段中直接返回,
 * 不要继续用此空数组覆盖权限。
 * @deprecated 使用登录响应 LoginResult.permissions 字段
 */
export async function getAccessCodesApi(): Promise<string[]> {
  return [];
}
