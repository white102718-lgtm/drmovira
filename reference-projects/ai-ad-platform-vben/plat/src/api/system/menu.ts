import { backendClient } from '#/api/request';

export namespace SystemMenuApi {
  export interface Menu {
    cacheable: 0 | 1;
    children?: Menu[];
    component?: null | string;
    createdAt: string;
    externalLink?: null | string;
    icon?: null | string;
    id: string;
    menuCode: string;
    menuName: string;
    menuType: 1 | 2 | 3;
    parentId: string;
    permissionCode?: null | string;
    remark?: null | string;
    routePath?: null | string;
    sortOrder: number;
    status: 0 | 1;
    updatedAt: string;
    visible: 0 | 1;
  }

  export interface SaveRequest {
    cacheable: 0 | 1;
    component?: string;
    externalLink?: string;
    icon?: string;
    menuCode: string;
    menuName: string;
    menuType: 1 | 2 | 3;
    parentId: string;
    permissionCode?: string;
    remark?: string;
    routePath?: string;
    sortOrder?: number;
    status: 0 | 1;
    visible: 0 | 1;
  }
}

function getMenuList() {
  return backendClient.get<SystemMenuApi.Menu[]>('/menus/tree');
}

function createMenu(data: SystemMenuApi.SaveRequest) {
  return backendClient.post<SystemMenuApi.Menu>('/menus', data);
}

function updateMenu(id: string, data: SystemMenuApi.SaveRequest) {
  return backendClient.put<SystemMenuApi.Menu>(`/menus/${id}`, data);
}

function deleteMenu(id: string) {
  return backendClient.delete(`/menus/${id}`);
}

export { createMenu, deleteMenu, getMenuList, updateMenu };
