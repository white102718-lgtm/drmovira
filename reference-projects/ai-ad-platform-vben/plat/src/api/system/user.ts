import type { SystemPageResult } from './types';

import { adpulseClient, backendClient } from '#/api/request';

export namespace SystemUserApi {
  /** 旧业务域仍在消费的用户结构，保留到相关接口迁移完成。 */
  export interface SystemUser {
    [key: string]: any;
    _id: string;
    name: string;
    password?: string;
    permissions: string[];
    phone?: string;
    remark?: string;
    status: 0 | 1;
  }

  export interface ApiKey {
    [key: string]: any;
    _id: string;
    created_at?: string;
    key?: string;
    name?: string;
  }

  export interface User {
    avatarUrl?: null | string;
    createdAt: string;
    createdBy?: null | string;
    displayName: string;
    email?: null | string;
    englishNickname?: null | string;
    id: string;
    ipAccessMode: 0 | 1 | 2;
    lastLoginAt?: null | string;
    lastLoginIp?: null | string;
    lockedUntil?: null | string;
    mfaBoundAt?: null | string;
    mfaStatus: 0 | 1;
    passwordChangedAt?: null | string;
    phone: string;
    primaryDepartmentId?: null | string;
    realName?: null | string;
    remark?: null | string;
    sourceType?: null | string;
    status: 0 | 1;
    updatedAt: string;
    updatedBy?: null | string;
    username?: null | string;
  }

  export interface DepartmentScope {
    departmentId: string;
    includeChildren: boolean;
  }

  export interface Detail {
    departmentScopes: DepartmentScope[];
    ipCidrs: string[];
    roleIds: string[];
    user: User;
  }

  export interface SaveRequest {
    avatarUrl?: string;
    departmentScopes: Array<{
      departmentId: string;
      includeChildren: boolean;
    }>;
    displayName: string;
    email?: string;
    englishNickname?: string;
    ipAccessMode: 0 | 1 | 2;
    ipCidrs: string[];
    password?: string;
    phone: string;
    primaryDepartmentId?: string;
    realName?: string;
    remark?: string;
    roleIds: string[];
    status: 0 | 1;
  }

  export interface PageParams {
    departmentId?: string;
    keyword?: string;
    page?: number;
    pageSize?: number;
    roleId?: string;
    status?: 0 | 1;
  }
}

export interface DepartmentScopeUser {
  _id?: string;
  department?: null | string;
  full_name?: string;
  name?: string;
  real_name?: string;
  status?: 0 | 1;
  user_id?: string;
  username?: string;
}

export interface DepartmentScopeUserOption {
  available: boolean;
  department?: string;
  label: string;
  name: string;
  userId: string;
}

interface DepartmentTreeNode {
  children?: DepartmentTreeNode[];
  deptName: string;
  id: string;
}

export function normalizeDepartmentScopeUserOptions(
  users: readonly DepartmentScopeUser[],
): DepartmentScopeUserOption[] {
  const seen = new Set<string>();
  const options: DepartmentScopeUserOption[] = [];
  for (const user of users) {
    const userId = (user.user_id ?? user._id ?? '').trim();
    if (!userId || seen.has(userId)) continue;
    seen.add(userId);
    const name =
      user.real_name?.trim() ||
      user.full_name?.trim() ||
      user.name?.trim() ||
      user.username?.trim() ||
      userId;
    const department = user.department?.trim() || undefined;
    options.push({
      available: user.status !== 0,
      department,
      label: department ? `${name} · ${department}` : name,
      name,
      userId,
    });
  }
  return options;
}

function getUserList(params: SystemUserApi.PageParams) {
  return backendClient.get<SystemPageResult<SystemUserApi.User>>('/users', {
    params,
  });
}

function getUserDetail(id: string) {
  return backendClient.get<SystemUserApi.Detail>(`/users/${id}`);
}

function createUser(data: SystemUserApi.SaveRequest) {
  return backendClient.post<SystemUserApi.Detail>('/users', data);
}

function updateUser(id: string, data: SystemUserApi.SaveRequest) {
  const payload = { ...data };
  if (!payload.password) delete payload.password;
  return backendClient.put<SystemUserApi.Detail>(`/users/${id}`, payload);
}

/**
 * 更新用户角色时复用当前详情，避免角色成员页意外覆盖账号资料或安全策略。
 *
 * 后端的用户更新接口会整体替换关联关系，因此这里只变更 roleIds，其他必填字段
 * 均保留服务端当前值。
 */
function saveUserRoleIds(
  userId: string,
  detail: SystemUserApi.Detail,
  roleIds: string[],
) {
  const { user } = detail;
  return updateUser(userId, {
    avatarUrl: user.avatarUrl ?? undefined,
    departmentScopes: detail.departmentScopes,
    displayName: user.displayName,
    email: user.email ?? undefined,
    englishNickname: user.englishNickname ?? undefined,
    ipAccessMode: user.ipAccessMode,
    ipCidrs: detail.ipCidrs,
    phone: user.phone,
    primaryDepartmentId: user.primaryDepartmentId ?? undefined,
    realName: user.realName ?? undefined,
    remark: user.remark ?? undefined,
    roleIds,
    status: user.status,
  });
}

/** 为既有用户添加一个角色，不影响其账号及其他角色关系。 */
async function addUserToRole(userId: string, roleId: string) {
  const detail = await getUserDetail(userId);
  const roleIds = [...new Set([...detail.roleIds, roleId])];
  return saveUserRoleIds(userId, detail, roleIds);
}

/** 从既有用户移除一个角色，不删除用户账号。 */
async function removeUserFromRole(userId: string, roleId: string) {
  const detail = await getUserDetail(userId);
  const roleIds = detail.roleIds.filter((id) => id !== roleId);
  return saveUserRoleIds(userId, detail, roleIds);
}

function deleteUser(id: string) {
  return backendClient.delete(`/users/${id}`);
}

function resetUserPassword(id: string, newPassword: string) {
  return backendClient.post(`/users/${id}/password/reset`, { newPassword });
}

function resetUserMfa(id: string) {
  return backendClient.post(`/users/${id}/mfa/reset`);
}

// 用户名称列表由新广告后端提供；开发环境请求 /adpulse-api/users/names。
/** 用户展示名与业务传参名，分别对应 display_name 和 english_nickname。 */
export interface UserNameOption {
  full_name: string;
  real_name: string;
}

/** 获取用户名称选项，供页面分别绑定展示标签和提交值。 */
function getUserNameOptions(
  roles: Array<'creator' | 'operator' | 'operator_leader'> = [],
  scoped?: boolean,
) {
  const params = new URLSearchParams();
  roles.forEach((role) => params.append('roles', role));
  if (scoped) params.append('scoped', 'true');
  const query = params.toString();
  return adpulseClient.get<UserNameOption[]>(
    `/users/names${query ? `?${query}` : ''}`,
  );
}

/** 保留其他页面的字符串用法，统一从新响应取 real_name 作为业务值。 */
async function getUserOptions(
  roles: Array<'creator' | 'operator' | 'operator_leader'> = [],
  scoped?: boolean,
): Promise<string[]> {
  const users = await getUserNameOptions(roles, scoped);
  return users.map((user) => user.real_name);
}

function getTaskAssigneeNames(role: 'creator' | 'operator') {
  return adpulseClient.get<string[]>('/users/task-assignee-names', {
    params: { role },
  });
}

export interface UserProfileUpdateRequest {
  avatarUrl?: string;
  displayName: string;
  email?: string;
  englishNickname?: string;
  realName?: string;
}

export interface UserProfile {
  /** 是否已设置登录密码，由后端判定。 */
  hasPassword?: boolean;
  avatarUrl?: null | string;
  department?: null | string;
  departments: string[];
  displayName: string;
  email?: null | string;
  englishNickname?: null | string;
  phone?: null | string;
  realName?: null | string;
  roles: string[];
  userId: string;
  username?: null | string;
}

export interface UserPasswordChangeRequest {
  newPassword: string;
  oldPassword?: string;
}

interface UploadedFile {
  id: string;
  mimeType: string;
  originalName: string;
}

async function sha256(file: File) {
  const buffer = await file.arrayBuffer();
  let digest: Uint8Array;
  if (globalThis.crypto?.subtle) {
    digest = new Uint8Array(
      await globalThis.crypto.subtle.digest('SHA-256', buffer),
    );
  } else {
    const { sha256: sha256Fallback } = await import('@noble/hashes/sha2.js');
    digest = sha256Fallback(new Uint8Array(buffer));
  }
  return [...digest]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
}

async function uploadProfileAvatar(file: File) {
  const data = new FormData();
  data.append('file', file);
  const uploaded = await backendClient.post<UploadedFile>(
    '/files/upload',
    data,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { contentHash: await sha256(file) },
      skipErrorMessage: true,
    } as any,
  );
  return `/files/${uploaded.id}/download`;
}

function getMyProfile() {
  return backendClient.get<UserProfile>('/users/me');
}

function updateMyProfile(data: UserProfileUpdateRequest) {
  return backendClient.put<UserProfile>('/users/me', data);
}

function changeMyPassword(data: UserPasswordChangeRequest) {
  return backendClient.put('/users/me/password', data);
}

function flattenDepartmentNames(
  nodes: readonly DepartmentTreeNode[],
): string[] {
  return nodes.flatMap((node) => [
    node.deptName,
    ...flattenDepartmentNames(node.children ?? []),
  ]);
}

async function getUserDepartmentOptions() {
  const departments =
    await backendClient.get<DepartmentTreeNode[]>('/departments/tree');
  return flattenDepartmentNames(departments ?? []);
}

async function getUserDepartmentScope(): Promise<DepartmentScopeUser[]> {
  const result = await getUserList({ page: 1, pageSize: 200 });
  return (result.items ?? []).map((user) => ({
    _id: user.id,
    full_name: user.displayName,
    name: user.displayName,
    real_name: user.realName ?? undefined,
    status: user.status,
    user_id: user.id,
    username: user.username ?? undefined,
  }));
}

async function getDepartmentScopeUserOptions() {
  const users = await getUserDepartmentScope();
  return normalizeDepartmentScopeUserOptions(users ?? []);
}

function getUserApiKeys(userId: string) {
  return backendClient.get<SystemUserApi.ApiKey[]>(`/users/${userId}/apikeys`);
}

function createApiKey(
  userId: string,
  data: { expires_days?: number; name?: string; remark?: string },
) {
  return backendClient.post(`/users/${userId}/apikey`, data);
}

function deleteApiKey(userId: string, keyId: string) {
  return backendClient.delete(`/users/${userId}/apikey/${keyId}`);
}

function getUserFullNames(
  roles: Array<'creator' | 'operator' | 'operator_leader'> = [],
  department?: string,
) {
  const params = new URLSearchParams();
  roles.forEach((role) => params.append('roles', role));
  if (department) {
    params.set('department', department);
  }
  const query = params.toString();
  return backendClient.get<string[]>(
    `/users/full_names${query ? `?${query}` : ''}`,
  );
}

export {
  addUserToRole,
  changeMyPassword,
  createApiKey,
  createUser,
  deleteApiKey,
  deleteUser,
  getDepartmentScopeUserOptions,
  getMyProfile,
  getUserApiKeys,
  getUserDepartmentOptions,
  getUserDepartmentScope,
  getUserDetail,
  getUserFullNames,
  getUserList,
  getUserNameOptions,
  getUserOptions,
  getTaskAssigneeNames,
  resetUserMfa,
  resetUserPassword,
  removeUserFromRole,
  updateMyProfile,
  uploadProfileAvatar,
  updateUser,
};
