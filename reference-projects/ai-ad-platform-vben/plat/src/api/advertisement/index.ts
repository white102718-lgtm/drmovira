import { adpulseClient, plainClient } from '#/api/request';

export function queryAdStructure(data: {
  ad_ids?: string[];
  adset_ids?: string[];
  campaign_ids?: string[];
}) {
  return adpulseClient.post('/operations/query-ad-structure', data);
}

/**
 * 批量查询任务线信息
 */
export async function batchQueryMissionLineInfo(
  queries: Array<{ subtask_name: string; task_name: string }>,
  page = 1,
  pageSize = 15,
  filters?: {
    account_id?: string[];
    account_name?: string[];
    person_name?: string;
    pixel_name_filter?: string;
    status?: string;
  },
  metaOnly = false,
) {
  const data = {
    queries,
    page,
    page_size: pageSize,
    ...filters,
    ...(metaOnly ? { meta_only: true } : {}),
  };

  return adpulseClient.post('/operations/subtask-personal-account-info', data, {
    responseReturn: 'body',
  });
}

/**
 * 创建广告
 * @param data 广告参数
 * @returns 创建结果（返回完整响应，包含 data、code、message）
 */
export async function createAdvertisement(data: any) {
  return adpulseClient.post('/operations/create-ad', data);
}

export async function syncAdAccountApplications(data: {
  items: Array<{ personal_id: string; ad_account_ids: string[] }>;
  force_refresh: boolean;
}) {
  return adpulseClient.post('/fb_resource/ad_accounts/applications/sync', data);
}

export async function deleteAds(data: {
  ads: Array<{ id: string; name: string }>;
  object_type?: 'personal' | 'system';
  personal_id?: string;
}) {
  return adpulseClient.post('/operations/delete-ads', data);
}

export async function createAds(data: {
  account_id: string;
  link_url: string;
  object_type?: 'personal' | 'system';
  operations: Array<{
    ads: Array<{
      contextual_multi_ads?: { enroll_status: string };
      creative: {
        body?: string;
        call_to_action?: { type: string };
        description?: string;
        image_hash?: string;
        path?: string;
        picture?: string;
        title?: string;
        type: string;
      };
      name: string;
      status: string;
    }>;
    adset_id: string;
    adset_name: string;
    campaign_name: string;
  }>;
  page_id: string;
  personal_id?: string;
}) {
  return adpulseClient.post('/operations/create-ads', data);
}

/**
 * 查询操作历史
 * @param start 开始时间
 * @param end 结束时间
 * @param current_user
 * @returns 操作历史记录
 */
export async function getOperationHistory(params: {
  start: string;
  end: string;
  current_user?: string;
  operate_type?: string[];
  operte_level?: string;
  game_platform?: string;
  agent_line?: string;
  ad_status?: string;
  page?: number;
  page_size?: number;
}) {
  const {
    start,
    end,
    current_user,
    operate_type,
    operte_level,
    game_platform,
    agent_line,
    ad_status,
    page,
    page_size,
  } = params;
  const searchParams = new URLSearchParams();
  searchParams.append('start', start);
  searchParams.append('end', end);
  if (current_user) searchParams.append('current_user', current_user);
  (operate_type ?? []).forEach((t) => searchParams.append('operate_type', t));
  if (operte_level) searchParams.append('operte_level', operte_level);
  if (game_platform) searchParams.append('game_platform', game_platform);
  if (agent_line) searchParams.append('agent_line', agent_line);
  if (ad_status) searchParams.append('ad_status', ad_status);
  if (page) searchParams.append('page', String(page));
  if (page_size) searchParams.append('page_size', String(page_size));
  return adpulseClient.get(
    `/operations/operation_history?${searchParams.toString()}`,
  );
}

/**
 * 获取模板列表
 */
export async function getTemplateList(params?: { real_name?: string }) {
  return adpulseClient.get('/operations/templates/', { params });
}

/**
 * 获取模板详情
 */
export async function getTemplateDetail(templateId: string) {
  return adpulseClient.get(`/operations/templates/${templateId}`);
}

/**
 * 创建模板
 */
export async function createTemplate(data: {
  description?: string;
  name: string;
  real_name: string;
  settings: {};
}) {
  return adpulseClient.post('/operations/templates/', data);
}

/**
 * 更新模板
 */
export async function updateTemplate(
  templateId: string,
  data: {
    description?: string;
    name: string;
    real_name: string;
    settings: {};
  },
) {
  return adpulseClient.put(`/operations/templates/${templateId}`, data);
}

/**
 * 删除模板
 */
export async function deleteTemplate(templateId: string) {
  return adpulseClient.delete(`/operations/templates/${templateId}`);
}

/**
 * 获取素材模板列表
 */
export async function getMaterialTemplateList(params?: { real_name?: string }) {
  return adpulseClient.get('/operations/templates/materials', { params });
}

/**
 * 创建素材模板
 */
export async function createMaterialTemplate(data: {
  batchDescription?: string;
  batchTitle?: string;
  description?: string;
  name: string;
  real_name: string;
}) {
  return adpulseClient.post('/operations/templates/materials', data);
}

/**
 * 更新素材模板
 */
export async function updateMaterialTemplate(
  templateId: string,
  data: {
    batchDescription?: string;
    batchTitle?: string;
    description?: string;
    name?: string;
    real_name?: string;
  },
) {
  return adpulseClient.put(
    `/operations/templates/materials/${templateId}`,
    data,
  );
}

/**
 * 删除素材模板
 */
export async function deleteMaterialTemplate(templateId: string) {
  return adpulseClient.delete(`/operations/templates/materials/${templateId}`);
}

/**
 * 获取 AI 建议报告的 iframe 地址
 */
export async function getAiSuggestionReportUrl(params: {
  game_platform: string;
  report_type?: number;
  request_id?: string;
}) {
  return plainClient.get<{
    reports: Array<{ report_url: string }>;
  }>('/aiReport/v1/reports', { params, responseReturn: 'body' });
}

/**
 * 获取 Minio 报告预签名访问链接
 */
export async function getMinioPresignedUrl(minioPath: string) {
  return plainClient.get<{ url: string }>('/aiReport/v1/minio/presigned-url', {
    params: { minio_path: minioPath },
    responseReturn: 'body',
  });
}
