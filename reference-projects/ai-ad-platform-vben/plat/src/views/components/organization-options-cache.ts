import type { SystemDepartmentApi, SystemUserApi } from '#/api';

import { getSystemDepartmentTree, getUserList } from '#/api';
import { FULL_OPTION_PAGE_SIZE } from '#/constants/pagination';

let departmentsCache: SystemDepartmentApi.Department[] | undefined;
let departmentsRequest: Promise<SystemDepartmentApi.Department[]> | undefined;
let usersCache: SystemUserApi.User[] | undefined;
let usersRequest: Promise<SystemUserApi.User[]> | undefined;

/** 页面内所有组织架构选择器共享同一次部门树请求。 */
export async function getSharedDepartmentTree() {
  if (departmentsCache) return departmentsCache;
  departmentsRequest ??= getSystemDepartmentTree();
  try {
    departmentsCache = await departmentsRequest;
    return departmentsCache;
  } catch (error) {
    departmentsRequest = undefined;
    throw error;
  }
}

async function loadAllUsers() {
  const result = await getUserList({
    page: 1,
    pageSize: FULL_OPTION_PAGE_SIZE,
  });
  return result.items;
}

/** 页面内所有用户选择器共享同一次完整用户列表请求。 */
export async function getSharedOrganizationUsers() {
  if (usersCache) return usersCache;
  usersRequest ??= loadAllUsers();
  try {
    usersCache = await usersRequest;
    return usersCache;
  } catch (error) {
    usersRequest = undefined;
    throw error;
  }
}
