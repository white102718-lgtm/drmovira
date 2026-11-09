import type { SystemPageResult } from './types';

import { backendClient } from '#/api/request';

export namespace SystemRoleApi {
  export interface Role {
    createdAt: string;
    createdBy?: null | string;
    id: string;
    remark?: null | string;
    roleCode: string;
    roleName: string;
    sortOrder: number;
    status: 0 | 1;
    updatedAt: string;
    updatedBy?: null | string;
  }

  export interface Detail {
    menuIds: string[];
    role: Role;
  }

  export interface SaveRequest {
    menuIds: string[];
    remark?: string;
    roleCode: string;
    roleName: string;
    sortOrder?: number;
    status: 0 | 1;
  }

  export interface PageParams {
    keyword?: string;
    page?: number;
    pageSize?: number;
    status?: 0 | 1;
  }
}

function getRoleList(params: SystemRoleApi.PageParams = {}) {
  return backendClient.get<SystemPageResult<SystemRoleApi.Role>>('/roles', {
    params,
  });
}

function getRoleDetail(id: string) {
  return backendClient.get<SystemRoleApi.Detail>(`/roles/${id}`);
}

function createRole(data: SystemRoleApi.SaveRequest) {
  return backendClient.post<SystemRoleApi.Detail>('/roles', data);
}

function updateRole(id: string, data: SystemRoleApi.SaveRequest) {
  return backendClient.put<SystemRoleApi.Detail>(`/roles/${id}`, data);
}

function deleteRole(id: string) {
  return backendClient.delete(`/roles/${id}`);
}

export { createRole, deleteRole, getRoleDetail, getRoleList, updateRole };
