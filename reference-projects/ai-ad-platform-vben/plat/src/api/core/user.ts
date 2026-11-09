import type { UserInfo } from '@vben/types';

import { adpulseClient, backendClient } from '#/api/request';

/**
 * 后端 /auth/me 返回的当前会话数据
 */
interface AuthMeResponse {
  avatarUrl?: null | string;
  department?: null | string;
  departments?: string[];
  userId: string;
  displayName: string;
  email?: null | string;
  englishNickname?: null | string;
  feishuOpenId?: null | string;
  permissions: string[];
  phone?: string;
  realName?: null | string;
  roles?: string[];
  username?: null | string;
}

export interface AuthUserInfo extends UserInfo {
  avatarSourceUrl?: string;
  department?: string;
  departments: string[];
  displayName: string;
  email?: string;
  englishNickname?: string;
  feishuOpenId?: string;
  permissions: string[];
  phone?: string;
  username: string;
}

/**
 * 读取业务服务当前会话的角色编码，与素材工单后端权限判断保持一致。
 * 系统 /auth/me 的 roles 是展示名称，不能用于 OPERATOR 等编码判断。
 */
export async function getCurrentUserRoleCodesApi(): Promise<string[]> {
  const data = await adpulseClient.get<{ roles: string[] }>('/users/info');
  return data.roles.map((role) => role.trim().toLowerCase());
}

let currentAvatarObjectUrl = '';

async function resolveAvatarUrl(source?: null | string) {
  if (!source) return '';
  if (!source.startsWith('/files/')) return source;
  try {
    const blob = await backendClient.get<Blob>(source, {
      responseReturn: 'body',
      responseType: 'blob',
    });
    if (currentAvatarObjectUrl) URL.revokeObjectURL(currentAvatarObjectUrl);
    currentAvatarObjectUrl = URL.createObjectURL(blob);
    return currentAvatarObjectUrl;
  } catch {
    // 头像文件异常不应阻断登录态恢复和其他个人信息展示。
    return '';
  }
}

/**
 * 获取用户信息(当前登录会话快照)
 * @param silent 落地页探测登录态时传 true:401 不弹全局错误提示(由调用方自行处理跳转)
 */
export async function getUserInfoApi(silent = false): Promise<AuthUserInfo> {
  const data = await backendClient.get<AuthMeResponse>(
    '/auth/me',
    silent ? ({ skipErrorMessage: true } as any) : undefined,
  );
  // 映射为 Vben 框架需要的 UserInfo 结构
  return {
    userId: data.userId,
    full_name: data.displayName,
    displayName: data.displayName,
    realName: data.realName || data.englishNickname || '',
    englishNickname: data.englishNickname || undefined,
    username: data.username || '',
    phone: data.phone,
    email: data.email || undefined,
    department: data.department || undefined,
    departments: data.departments ?? [],
    feishuOpenId: data.feishuOpenId || '',
    permissions: data.permissions ?? [],
    // 权限码交由认证 store 同步，确保恢复会话时也能刷新按钮权限。
    roles: data.roles ?? [],
    // 首页由 preferences.app.defaultHomePath 兜底,可按需扩展
    homePath: '',
    // 头像可按需扩展
    avatar: await resolveAvatarUrl(data.avatarUrl),
    avatarSourceUrl: data.avatarUrl || undefined,
  } as AuthUserInfo;
}
