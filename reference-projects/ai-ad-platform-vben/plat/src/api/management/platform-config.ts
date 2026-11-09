import { adpulseClient } from '../request';

export interface PlatformConfigItem {
  _id: string;
  agent_lines: string[];
  agent_lines_count: number;
  attribution_platform?: string;
  departments?: string[];
  enabled: boolean;
  external_team?: string[];
  game_platform: string;
  internal_team?: string[];
  start_time?: string;
  target_region?: string[];
  total_budget?: string;
  visible?: boolean;
}

export interface AgentLineConfig {
  _id: string;
  agent_line?: string;
  auto_run?: boolean;
  budget_cap?: number;
  budget_floor?: number;
  enabled?: boolean;
  game_platform?: string;
  history_package_urls?: string[];
  id: null | string;
  is_send?: boolean;
  media_platform?: string;
  objective?: string;
  optimizer?: string;
  optimizer_id?: string;
  package_name?: string;
  package_type?: string;
  package_url?: string;
  page_id?: string;
  pixel_name?: string;
  project_id?: string;
}

export interface AgentLineKpiConfig {
  _id: string;
  agent_lines?: string[];
  agent_lines_temp?: string;
  check_hourly?: string;
  event_field?: string;
  event_name?: string;
  game_platform?: string;
  id?: null | string;
  is_default?: boolean;
  max_target_cost?: number;
  target_cost?: number;
  target_lifetime_hour?: number;
  target_lost_percent?: number;
  target_purpose?: string;
  type?: string;
}

export interface AgentLineConfigItem extends AgentLineConfig {
  create_time?: string;
  created_by?: string;
  update_time?: string;
  updated_by?: string;
}

export interface PlatformConfigParams {
  department?: string;
  game_platform?: string;
  name?: string;
  page?: number;
  pageSize?: number;
}

export async function getPlatformConfigList(params?: PlatformConfigParams) {
  const queryParams = new URLSearchParams();
  if (params?.game_platform) {
    queryParams.set('game_platform', params.game_platform);
  }
  if (params?.name) {
    queryParams.set('name', params.name);
  }
  if (params?.page) {
    queryParams.set('page', params.page.toString());
  }
  if (params?.pageSize) {
    queryParams.set('pageSize', params.pageSize.toString());
  }
  if (params?.department) {
    queryParams.set('department', params.department);
  }

  const query = queryParams.toString() ? `?${queryParams.toString()}` : '';
  return adpulseClient.get(`platform-config/${query}`);
}

export async function createPlatformConfig(
  data: Pick<PlatformConfigItem, 'game_platform'>,
) {
  return adpulseClient.post('platform-config/', data);
}

export async function updatePlatformConfig(
  id: string,
  data: Partial<
    Pick<
      PlatformConfigItem,
      | 'agent_lines'
      | 'attribution_platform'
      | 'departments'
      | 'enabled'
      | 'game_platform'
      | 'target_region'
      | 'total_budget'
      | 'visible'
    >
  >,
) {
  return adpulseClient.put(`platform-config/${id}`, data);
}

export async function deletePlatformConfig(id: string) {
  return adpulseClient.delete(`platform-config/${id}`);
}

/** 项目分组的代理线选项；project_id 用于搜索前后保持选中路径稳定。 */
export interface AgentOptionsItem {
  _id: string;
  agent_lines: string[];
  game_platform?: string;
  project_id?: string;
}

export async function getAgentOptions(platform?: string, agentName?: string) {
  const params: Record<string, string> = {};
  if (platform) {
    params.platform = platform;
  }
  if (agentName) {
    params.agent_name = agentName;
  }
  return adpulseClient.get<AgentOptionsItem[]>(
    'platform-config/agent_options/',
    {
      params,
    },
  );
}

export async function getPlatOptions() {
  return adpulseClient.get('platform-config/plat_options/');
}

export async function getAgentLineConfigList(
  gamePlatform?: string,
  agentLine?: string,
  department?: string,
  page = 1,
  pageSize = 20,
) {
  const params: Record<string, string | number> = {
    page,
    page_size: pageSize,
  };
  if (gamePlatform) {
    params.game_platform = gamePlatform;
  }
  if (agentLine) {
    params.agent_line = agentLine;
  }
  if (department) {
    params.department = department;
  }
  return adpulseClient.get<{
    items: AgentLineConfigItem[];
    page: number;
    page_size: number;
    total: number;
  }>('platform-config/agent-line/', { params });
}

export async function createAgentLineConfig(
  gamePlatform: string,
  data: Omit<AgentLineConfigItem, 'id'>,
) {
  return adpulseClient.post(
    `platform-config/agent-line/${encodeURIComponent(gamePlatform)}`,
    data,
  );
}

export async function updateAgentLineConfig(
  _gamePlatform: string,
  data: Partial<AgentLineConfigItem> & { platform?: string },
) {
  return adpulseClient.put('platform-config/agent-line/', data);
}

export async function batchUpdateAgentLineConfig(
  configs: Partial<AgentLineConfigItem>[],
) {
  return adpulseClient.put('platform-config/agent-line/batch', configs);
}

export async function deleteAgentLineConfig(id: string) {
  return adpulseClient.delete(
    `platform-config/agent-line/${encodeURIComponent(id)}`,
  );
}

/** 批量查询代理线预算上下限，返回 [{ _id, budget_cap, budget_floor }] */
export async function getAgentLineBudgets(ids: string[]) {
  return adpulseClient.post('platform-config/agent-line/budgets', ids);
}

export async function getAgentLineKpiConfigList(
  gamePlatform?: string,
  agentLine?: string,
) {
  const queryParams = new URLSearchParams();
  if (gamePlatform) {
    queryParams.set('game_platform', gamePlatform);
  }
  if (agentLine) {
    queryParams.set('agent_line', agentLine);
  }
  const query = queryParams.toString() ? `?${queryParams.toString()}` : '';
  return adpulseClient.get(`platform-config/agent-line-kpi/${query}`);
}

export async function createAgentLineKpiConfig(
  data: Omit<AgentLineKpiConfig, 'id'>,
) {
  return adpulseClient.post('platform-config/agent-line-kpi/', data);
}

export async function updateAgentLineKpiConfig(
  id: string,
  data: Partial<Omit<AgentLineKpiConfig, 'id'>>,
) {
  return adpulseClient.put(`platform-config/agent-line-kpi/${id}`, data);
}

export async function deleteAgentLineKpiConfig(id: string) {
  return adpulseClient.delete(`platform-config/agent-line-kpi/${id}`);
}

// 部门配置接口
export interface DepartmentConfig {
  children?: DepartmentConfig[];
  id: string;
  name: string;
  parent_id?: string;
}

export async function getDepartmentConfigList() {
  return adpulseClient.get('department/');
}

export async function getDepartmentTree(): Promise<DepartmentConfig[]> {
  const result = await adpulseClient.get<{ items: DepartmentConfig[] }>(
    'department/tree',
  );
  return result.items ?? [];
}

export async function createDepartmentConfig(
  data: Omit<DepartmentConfig, 'id'>,
) {
  return adpulseClient.post<{ code: number; message: string }>(
    'department/',
    data,
    { responseReturn: 'body' },
  );
}

export async function updateDepartmentConfig(
  id: string,
  data: Partial<Omit<DepartmentConfig, 'id'>>,
) {
  return adpulseClient.put<{ code: number; message: string }>(
    `department/${id}`,
    data,
    { responseReturn: 'body' },
  );
}

export async function deleteDepartmentConfig(id: string) {
  return adpulseClient.delete(`department/${id}`);
}

export async function getDepartmentOptions() {
  return adpulseClient.get('department/options/');
}

// 批量导入平台配置
export async function importPlatformConfig(file: File) {
  const formData = new FormData();
  formData.append('file', file);

  return adpulseClient.post('platform-config/agent-line/parse-file', formData, {
    headers: {
      'Content-Type': undefined,
    },
    timeout: 300_000,
  });
}

export interface EffectiveAppIdItem {
  app_id: string;
  config_id: string;
  name: string;
}

export type EffectiveAppIdMap = Record<
  string,
  Omit<EffectiveAppIdItem, 'name'>
>;

export async function getEffectiveAppIds() {
  return adpulseClient.get<EffectiveAppIdMap>('facebook/effective/appid');
}

export async function getAdvertisingLogin(app_id: string, config_id: string) {
  return adpulseClient.get<string>('facebook/advertising/login', {
    params: { app_id, config_id },
  });
}

// 下载导入模板
export interface DownloadTemplateResponse {
  content: string;
  filename: string;
}

export async function downloadImportTemplate() {
  return adpulseClient.get<DownloadTemplateResponse>(
    'platform-config/template',
  );
}

// ========== 产品建档管理相关接口 ==========

// 产品接口
export interface TagProduct {
  created_at?: string;
  description?: string;
  enabled?: boolean;
  id?: string;
  name: string;
  updated_at?: string;
}

// 一级节点接口
export interface TagParentCategory {
  created_at?: string;
  description?: string;
  enabled?: boolean;
  id?: string;
  name: string;
  product_id: string;
  updated_at?: string;
}

// 二级节点接口
export interface TagSubCategory {
  created_at?: string;
  description?: string;
  enabled?: boolean;
  id?: string;
  name: string;
  parent_category_id: string;
  product_id: string;
  updated_at?: string;
}

// 内容接口
export interface TagContent {
  created_at?: string;
  description?: string;
  enabled?: boolean;
  id?: string;
  name: string;
  parent_category_id: string;
  product_id: string;
  sort_order?: number;
  sub_category_id: string;
  updated_at?: string;
  value?: string;
}

// 产品 CRUD
export async function getTagProductList(params?: {
  page?: number;
  pageSize?: number;
}) {
  const queryParams = new URLSearchParams();
  if (params?.page) queryParams.set('page', params.page.toString());
  if (params?.pageSize) queryParams.set('pageSize', params.pageSize.toString());
  const query = queryParams.toString() ? `?${queryParams.toString()}` : '';
  return adpulseClient.get(`tag-config/products${query}`);
}

export async function createTagProduct(data: Omit<TagProduct, 'id'>) {
  return adpulseClient.post('tag-config/products/', data);
}

export async function updateTagProduct(
  id: string,
  data: Partial<Omit<TagProduct, 'id'>>,
) {
  return adpulseClient.put(`tag-config/products/${id}`, data);
}

export async function deleteTagProduct(id: string) {
  return adpulseClient.delete(`tag-config/products/${id}`);
}

// 一级节点 CRUD
export async function getTagParentCategoryList(gamePlatform: string) {
  return adpulseClient.get(`material-category/tree/${gamePlatform}`);
}

// 获取分类树形结构
export interface MaterialCategoryTreeItem {
  children?: MaterialCategoryTreeItem[];
  id: string;
  name: string;
}

export async function getMaterialCategoryTree(gamePlatform: string) {
  return adpulseClient.get<MaterialCategoryTreeItem[]>(
    `material-category/tree/${gamePlatform}`,
  );
}

export interface MaterialCategoryContentItem {
  id: string;
  name: string;
  remark?: string;
  text: string;
  type: string;
  url?: string;
}

export interface MaterialSubCategoryWithContents {
  contents: MaterialCategoryContentItem[];
  id: string;
  name: string;
}

export async function getMaterialCategorySubCategoryContents(
  subCategoryId: string,
) {
  return adpulseClient.get<MaterialSubCategoryWithContents>(
    `material-category/sub-category/${subCategoryId}/contents`,
  );
}

// 一级分类操作
export async function createMaterialCategory(
  gamePlatform: string,
  data: { description?: string; name: string },
) {
  return adpulseClient.post(`material-category/${gamePlatform}/category`, data);
}

export async function updateMaterialCategory(
  categoryId: string,
  data: { description?: string; name: string },
) {
  return adpulseClient.put(`material-category/category/${categoryId}`, data);
}

export async function deleteMaterialCategory(
  gamePlatform: string,
  categoryId: string,
) {
  return adpulseClient.delete(
    `material-category/${gamePlatform}/category/${categoryId}`,
  );
}

// 二级分类操作
export async function createMaterialSubCategory(
  categoryId: string,
  data: { description?: string; name: string },
) {
  return adpulseClient.post(
    `material-category/category/${categoryId}/sub-category`,
    data,
  );
}

export async function updateMaterialSubCategory(
  categoryId: string,
  subCategoryId: string,
  data: { description?: string; name: string },
) {
  return adpulseClient.put(
    `material-category/category/${categoryId}/sub-category/${subCategoryId}`,
    data,
  );
}

export async function deleteMaterialSubCategory(
  categoryId: string,
  subCategoryId: string,
) {
  return adpulseClient.delete(
    `material-category/category/${categoryId}/sub-category/${subCategoryId}`,
  );
}

// 内容操作
export async function createMaterialContent(
  subCategoryId: string,
  formData: FormData,
) {
  return adpulseClient.post(
    `material-category/sub-category/${subCategoryId}/content`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 300_000,
    },
  );
}

export async function updateMaterialContent(
  subCategoryId: string,
  contentId: string,
  formData: FormData,
) {
  return adpulseClient.put(
    `material-category/sub-category/${subCategoryId}/content/${contentId}`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 300_000,
    },
  );
}

export async function deleteMaterialContent(
  subCategoryId: string,
  contentId: string,
) {
  return adpulseClient.delete(
    `material-category/sub-category/${subCategoryId}/content/${contentId}`,
  );
}
