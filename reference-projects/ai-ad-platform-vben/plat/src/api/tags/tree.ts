import { backendClient } from '#/api/request';

// 配置相关接口
export interface TagConfig {
  created_at?: string;
  id: string;
  name: string;
  real_name: string;
  updated_at?: string;
}

export async function getTagConfigOptions(
  realName?: string,
): Promise<TagConfig[]> {
  const params = new URLSearchParams();
  if (realName) {
    params.set('real_name', realName);
  }
  const queryString = params.toString();
  const res = await backendClient.get(
    `/tags-edit/config/${queryString ? `?${queryString}` : ''}`,
  );
  return res.data || res || [];
}

export async function createTagConfig(
  name: string,
  realName: string,
): Promise<TagConfig> {
  const res = await backendClient.post('/tags-edit/config/', {
    name,
    real_name: realName,
  });
  return res.data || res;
}

export async function updateTagConfig(
  id: string,
  name: string,
): Promise<TagConfig> {
  const res = await backendClient.put(`/tags-edit/config/${id}`, { name });
  return res.data || res;
}

export async function deleteTagConfig(id: string): Promise<void> {
  return backendClient.delete(`/tags-edit/config/${id}`);
}

export interface TreeTagCreateRequest {
  config_id?: string;
  level: number;
  parent_id?: string;
  real_name?: string;
  title: string;
}

export async function getTreeTags(configId?: string, realName?: string) {
  const params = new URLSearchParams();
  if (configId) {
    params.set('config_id', configId);
  }
  if (realName) {
    params.set('real_name', realName);
  }
  const queryString = params.toString();
  return await backendClient.get(
    `/tags-edit/${queryString ? `?${queryString}` : ''}`,
  );
}

export async function addNodeTreeTag(data: TreeTagCreateRequest) {
  return await backendClient.post('/tags-edit/', data);
}

export async function deleteTreeTag(key: string) {
  return await backendClient.delete(`/tags-edit/${key}`);
}

export interface TreeTagUpdateRequest {
  config_id?: string;
  real_name?: string;
  title?: string;
}

export async function updateTreeTag(
  key: string,
  payload: TreeTagUpdateRequest,
) {
  return await backendClient.put(`/tags-edit/${key}`, payload);
}

export interface TreeDataStatsRequest {
  config_id?: string;
  date_field?: 'create_time' | 'date';
  end_date: string;
  min_spent?: number;
  origin?: boolean;
  real_name?: string;
  right_game_platform?: string;
  start_date: string;
  tag_filter_condition?: string;
  tags: string[];
}

export async function getTreeDataWithStats(
  startDate: string,
  endDate: string,
  rightGamePlatform?: string,
  realName?: string,
  configId?: string,
  tags?: string[],
  tagFilterCondition?: string,
  minSpent?: number,
  origin?: boolean,
  dateField: 'create_time' | 'date' = 'create_time',
) {
  const payload: TreeDataStatsRequest = {
    start_date: startDate,
    end_date: endDate,
    date_field: dateField,
    right_game_platform: rightGamePlatform,
    config_id: configId,
    real_name: realName,
    tags: tags || [], // 如果没有传tags，使用空数组
    tag_filter_condition: tagFilterCondition,
    min_spent: minSpent,
    origin,
  };
  return backendClient.post('tags-edit/tree_data', payload);
}

export async function exportTreeDataWithStats(payload: TreeDataStatsRequest) {
  return backendClient.post('tags-edit/tree_data/export', payload);
}
