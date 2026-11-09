import { adpulseClient } from '../request';

// 特殊代理线映射
export interface SpecialAgentMapping {
  agent_line: string;
  description?: string;
  field_mappings: Record<string, string>;
  is_active: boolean;
}

// 字段映射项
export interface FieldMapItem {
  _id: string;
  created_at?: string;
  created_by?: string;
  default_field_mappings: Record<string, string>;
  description?: string;
  is_active: boolean;
  special_agent_mappings: SpecialAgentMapping[];
  updated_at?: string;
  updated_by?: string;
}

// 创建字段映射参数
export interface FieldMapCreate {
  default_field_mappings?: Record<string, string>;
  description?: string;
  is_active?: boolean;
  special_agent_mappings?: SpecialAgentMapping[];
}

// 更新字段映射参数
export interface FieldMapUpdate {
  default_field_mappings?: Record<string, string>;
  description?: string;
  is_active?: boolean;
  special_agent_mappings?: SpecialAgentMapping[];
}

// 更新特殊代理线映射参数
export interface SpecialAgentMappingUpdate {
  description?: string;
  field_mappings?: Record<string, string>;
  is_active?: boolean;
}

export interface FieldMapParams {
  is_active?: boolean;
  platform_id?: string;
}

// 获取所有平台的字段映射
export async function getFieldMapList(params?: FieldMapParams) {
  const queryParams = new URLSearchParams();
  if (params?.platform_id) {
    queryParams.set('platform_id', params.platform_id);
  }
  if (params?.is_active !== undefined) {
    queryParams.set('is_active', String(params.is_active));
  }

  const query = queryParams.toString() ? `?${queryParams.toString()}` : '';
  return adpulseClient.get(`field-map/${query}`);
}

// 获取某个平台的字段映射
export async function getFieldMap(platformId: string) {
  return adpulseClient.get(`field-map/${platformId}`);
}

// 创建字段映射
export async function createFieldMap(platformId: string, data: FieldMapCreate) {
  return adpulseClient.post(`field-map/${platformId}`, data);
}

// 更新字段映射
export async function updateFieldMap(platformId: string, data: FieldMapUpdate) {
  return adpulseClient.put(`field-map/${platformId}`, data);
}

// 删除字段映射
export async function deleteFieldMap(platformId: string) {
  return adpulseClient.delete(`field-map/${platformId}`);
}

// 获取特殊代理线映射
export async function getAgentMapping(platformId: string, agentLine: string) {
  return adpulseClient.get(`field-map/${platformId}/agent/${agentLine}`);
}

// 添加特殊代理线映射
export async function addAgentMapping(
  platformId: string,
  data: SpecialAgentMapping,
) {
  return adpulseClient.post(`field-map/${platformId}/agent`, data);
}

// 更新特殊代理线映射
export async function updateAgentMapping(
  platformId: string,
  agentLine: string,
  data: SpecialAgentMappingUpdate,
) {
  return adpulseClient.put(`field-map/${platformId}/agent/${agentLine}`, data);
}

// 删除特殊代理线映射
export async function deleteAgentMapping(
  platformId: string,
  agentLine: string,
) {
  return adpulseClient.delete(`field-map/${platformId}/agent/${agentLine}`);
}

// 表字段结构
export interface TableColumn {
  comment: string;
  field: string;
  type: string;
}

export interface TableSchemas {
  ad_hourly_cleaned: TableColumn[];
  ad_hourly_detail: TableColumn[];
}

// 获取表结构
export async function getTableSchemas() {
  return adpulseClient.get<TableSchemas>('field-map/schema/tables');
}
