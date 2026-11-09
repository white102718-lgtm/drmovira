import { adpulseClient } from '#/api/request';

export const getDashboardDetail = (
  tabKey: string,
  params: Record<string, string>,
  config?: { signal?: AbortSignal },
) => {
  // 根据不同的标签页类型，请求不同的接口
  const endpoint = `dashboard/detail/${tabKey}`;
  return adpulseClient.get(endpoint, {
    params,
    signal: config?.signal,
  });
};

/** 单对象(系列/组/广告)每半小时明细,列与面板小时模式一致; end_date 缺省为 date 单天; 后端分页 */
export function getAdDrill(params: {
  date: string;
  end_date?: string;
  level: string;
  object_id: string;
  page?: number;
  page_size?: number;
  show_1d?: boolean;
}) {
  return adpulseClient.get<{
    columns: string[];
    data: Record<string, any>[];
    total: number;
  }>(`/dashboard/drill/${params.level}`, {
    params: {
      date: params.date,
      end_date: params.end_date,
      object_id: params.object_id,
      page: params.page,
      page_size: params.page_size,
      show_1d: params.show_1d,
    },
  });
}

/** 按账户 ID 批量查所属 BM,返回 {account_id: [{bm_id, bm_name}]} */
export function getBmMap(accountIds: string[]) {
  return adpulseClient.post<
    Record<string, Array<{ bm_id: string; bm_name: string }>>
  >('/dashboard/bm-map', { account_ids: accountIds });
}

export function getBiHistory(params: {
  agent_line: string;
  date: string;
  game_platform: string;
}) {
  return adpulseClient.get('/dashboard/bi_history', { params });
}

export function getOperationHistory(params: {
  agent_line?: string;
  date: string;
  game_platform?: string;
}) {
  return adpulseClient.get('/dashboard/operation_history', { params });
}

export function adOperate(data: {
  id: string;
  level: string;
  name?: string;
  object_type?: 'personal' | 'system';
  op_type: 'budget' | 'delete' | 'pause' | 'start';
  personal_id: string;
  timezone_name?: string;
  value?: number;
}) {
  return adpulseClient.post('/operations/operate', data);
}

export interface ChooseDevOption {
  id: string;
  name: string;
  type?: 'personal' | 'system';
}

export function getChooseDevOptions(params: {
  ad_ids?: string[];
  adset_ids?: string[];
  campaign_ids?: string[];
}) {
  return adpulseClient.post<Record<string, ChooseDevOption[]>>(
    '/operations/choose-dev',
    params,
  );
}

export interface DeleteAdNode {
  ad_id: string;
  ad_name: string;
  effective_status?: null | string;
}

export interface DeleteAdsetNode {
  ads: DeleteAdNode[];
  adset_id: string;
  adset_name: string;
}

export interface DeleteCampaignNode {
  adsets: DeleteAdsetNode[];
  campaign_id: string;
  campaign_name: string;
  can_delete: boolean;
  reason: null | string;
}

export interface DeleteAccountNode {
  account_id: string;
  account_name: string;
  campaigns: DeleteCampaignNode[];
}

export function getDeletePreview(data: { ids: string[]; level: string }) {
  return adpulseClient.post<{ accounts: DeleteAccountNode[] }>(
    '/operations/delete-preview',
    data,
  );
}

export interface AdOperateProgress {
  error?: null | string;
  op_type: 'budget' | 'delete' | 'pause' | 'start';
  status: string;
  updated_at: string;
  value?: null | number;
}

export type AdOperateStatusMap = Record<
  string,
  Partial<Record<AdOperateProgress['op_type'], AdOperateProgress>>
>;

export function getAdOperateStatus(
  ids: string[],
  level: string,
  config?: { signal?: AbortSignal; skipErrorMessage?: boolean },
) {
  return adpulseClient.get<AdOperateStatusMap>('/operations/operate-status', {
    ...config,
    params: { ids: ids.join(','), level },
  });
}

/** Mongo 中按用户、旧版 Tab key 保存；两个数组允许分别更新。 */
export interface DashboardColumnSetting {
  column_order?: string[];
  visible_columns?: string[];
}

export function getColumnSettingApi() {
  return adpulseClient.get<null | Record<string, DashboardColumnSetting>>(
    '/dashboard/column-settings',
    { skipErrorMessage: true },
  );
}

export function saveColumnSettingApi(
  tab: string,
  options: DashboardColumnSetting,
) {
  return adpulseClient.put(
    '/dashboard/column-settings',
    { tab, ...options },
    { skipErrorMessage: true },
  );
}

export const submitHourlyReport = (
  date: string,
  china_date: string,
  agent_line: string,
  game_platform: string,
  registrations: number,
  first_recharge_amount: number,
  first_recharge_users: number,
) => {
  const endpoint = `/dashboard/report/hourly_submit`;
  return adpulseClient.post(
    endpoint,
    {
      agent_line,
      date,
      china_date,
      first_recharge_amount,
      first_recharge_users,
      game_platform,
      registrations,
    },
    { responseReturn: 'body' },
  );
};
