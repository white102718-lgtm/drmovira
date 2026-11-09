import { backendClient } from '#/api/request';

export namespace SystemDepartmentApi {
  export interface Department {
    children?: Department[];
    createdAt: string;
    deptCode: string;
    deptName: string;
    id: string;
    leaderUserId?: null | string;
    level: number;
    parentId: string;
    path: string;
    remark?: null | string;
    sortOrder: number;
    /** 飞书来源的部门由组织同步维护，不允许手工修改或删除。 */
    sourceType?: 'FEISHU' | 'LOCAL';
    status: 0 | 1;
    updatedAt: string;
  }

  export interface SaveRequest {
    deptCode: string;
    deptName: string;
    leaderUserId?: string;
    parentId: string;
    remark?: string;
    sortOrder?: number;
    status: 0 | 1;
  }
}

function getSystemDepartmentTree() {
  return backendClient.get<SystemDepartmentApi.Department[]>(
    '/departments/tree',
  );
}

function createDepartment(data: SystemDepartmentApi.SaveRequest) {
  return backendClient.post<SystemDepartmentApi.Department>(
    '/departments',
    data,
  );
}

function updateDepartment(id: string, data: SystemDepartmentApi.SaveRequest) {
  return backendClient.put<SystemDepartmentApi.Department>(
    `/departments/${id}`,
    data,
  );
}

function deleteDepartment(id: string) {
  return backendClient.delete(`/departments/${id}`);
}

export {
  createDepartment,
  deleteDepartment,
  getSystemDepartmentTree,
  updateDepartment,
};
