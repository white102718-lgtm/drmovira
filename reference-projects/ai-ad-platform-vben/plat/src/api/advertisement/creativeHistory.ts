import { adpulseClient } from '#/api/request';

const BASE_URL = '/operations/creative-histories';

// ==================== 数据类型定义 ====================

/**
 * 创意历史中的单个素材创意配置
 */
export interface CreativeHistoryItem {
  type: 'image' | 'video' | 'carousel';
  image_hash?: string;
  path?: string;
  picture?: string;
  title?: string;
  body?: string;
  description?: string;
  call_to_action?: { type: string };
  /** enrich_creatives_with_material_info 注入 */
  img?: string;
  filetype?: string;
}

/**
 * 素材创意历史记录
 */
export interface CreativeHistory {
  id: string;
  creatives: CreativeHistoryItem[];
  creatives_count: number;
  created_at: string;
  username: string;
  real_name: string;
}

/**
 * 历史列表响应
 */
export interface CreativeHistoryListResponse {
  items: CreativeHistory[];
  total: number;
  page: number;
  size: number;
}

// ==================== API 接口 ====================

/**
 * 获取素材创意历史列表
 */
export async function getCreativeHistories(params?: {
  page?: number;
  size?: number;
}) {
  return adpulseClient.get(`${BASE_URL}`, { params });
}

/**
 * 获取素材创意历史详情
 */
export async function getCreativeHistoryDetail(historyId: string) {
  return adpulseClient.get(`${BASE_URL}/${historyId}`);
}

/**
 * 复用素材创意历史（后端返回 creatives 数组，mode 由前端控制）
 */
export async function reuseCreativeHistory(historyId: string) {
  return adpulseClient.post(`${BASE_URL}/${historyId}/reuse`);
}

/**
 * 删除素材创意历史记录
 */
export async function deleteCreativeHistory(historyId: string) {
  return adpulseClient.delete(`${BASE_URL}/${historyId}`);
}
