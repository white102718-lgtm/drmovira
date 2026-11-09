import { adpulseClient } from '#/api/request';

const BASE_URL = '/operations/material-groups';

// ==================== 数据类型定义 ====================

/**
 * 素材组中的单个素材配置
 */
export interface MaterialGroupItem {
  material_id: string; // 素材ID
  title: string; // 广告标题
  body: string; // 广告正文
  call_to_action?: string; // CTA按钮类型
}

/**
 * 素材组
 */
export interface MaterialGroup {
  id: string;
  name: string;
  description: string;
  tags: string[];
  materials: MaterialGroupItem[];
  materials_count: number;
  username: string;
  real_name: string;
  created_at: string;
  updated_at: string;
}

/**
 * 素材组应用历史
 */
export interface MaterialGroupHistory {
  id: string;
  group_id: string;
  group_name: string;
  materials: MaterialGroupItem[];
  materials_count: number;
  applied_at: string;
  real_name: string;
  apply_mode: 'replace' | 'append';
}

/**
 * 列表响应
 */
export interface MaterialGroupListResponse {
  items: MaterialGroup[];
  total: number;
  page: number;
  size: number;
}

/**
 * 历史列表响应
 */
export interface MaterialGroupHistoryListResponse {
  items: MaterialGroupHistory[];
  total: number;
  page: number;
  size: number;
}

// ==================== API 接口 ====================

/**
 * 创建素材组
 */
export async function createMaterialGroup(data: {
  name: string;
  description?: string;
  tags?: string[];
  materials: MaterialGroupItem[];
}) {
  return adpulseClient.post(`${BASE_URL}/`, data);
}

/**
 * 获取素材组列表
 */
export async function getMaterialGroups(params?: {
  name?: string;
  tags?: string;
  page?: number;
  size?: number;
}) {
  return adpulseClient.get(`${BASE_URL}/`, { params });
}

/**
 * 获取素材组详情
 */
export async function getMaterialGroupDetail(groupId: string) {
  return adpulseClient.get(`${BASE_URL}/${groupId}`);
}

/**
 * 更新素材组
 */
export async function updateMaterialGroup(
  groupId: string,
  data: {
    name?: string;
    description?: string;
    tags?: string[];
    materials?: MaterialGroupItem[];
  },
) {
  return adpulseClient.put(`${BASE_URL}/${groupId}`, data);
}

/**
 * 删除素材组
 */
export async function deleteMaterialGroup(groupId: string) {
  return adpulseClient.delete(`${BASE_URL}/${groupId}`);
}

/**
 * 应用素材组
 */
export async function applyMaterialGroup(
  groupId: string,
  mode: 'replace' | 'append',
) {
  return adpulseClient.post(`${BASE_URL}/${groupId}/apply`, { mode });
}

/**
 * 获取应用历史列表
 */
export async function getMaterialGroupHistories(params?: {
  page?: number;
  size?: number;
}) {
  return adpulseClient.get(`${BASE_URL}/histories`, { params });
}

/**
 * 获取历史详情
 */
export async function getHistoryDetail(historyId: string) {
  return adpulseClient.get(`${BASE_URL}/histories/${historyId}`);
}

/**
 * 重新应用历史
 */
export async function reapplyHistory(
  historyId: string,
  mode: 'replace' | 'append',
) {
  return adpulseClient.post(`${BASE_URL}/histories/${historyId}/reapply`, {
    mode,
  });
}
