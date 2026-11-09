import { adpulseClient } from '#/api/request';

/** 通用分页返回结构 (后端 ApiResponse.data) */
export interface PaginatedResult<T = Record<string, any>> {
  columns: string[];
  data: T[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

/** 数组参数以重复键形式序列化 (department=a&department=b), 覆盖 adpulseClient 默认的逗号拼接 */
const repeatArrayParams = { paramsSerializer: { indexes: null } } as const;

export interface OverviewQuery {
  channel?: string;
  date?: string;
  department?: string | string[];
  game_platform?: string;
  page?: number;
  page_size?: number;
  placer?: string;
  region?: string;
  sort_by?: string;
  sort_order?: string;
}

/** 项目维度概览 */
export function getProjectOverview(params?: OverviewQuery) {
  return adpulseClient.get<PaginatedResult>('/dashboard/project_overview', {
    params,
    ...repeatArrayParams,
  });
}

/** 投手维度 · 今日 Top */
export function getPlacerOverview(params?: OverviewQuery) {
  return adpulseClient.get<PaginatedResult>('/dashboard/placer_overview', {
    params,
    ...repeatArrayParams,
  });
}

/** 本月消耗排行榜 (group_by: placer 投手 / department 团队) */
export function getPlacerLeaderboard(params?: {
  channel?: string;
  date?: string;
  department?: string | string[];
  game_platform?: string;
  group_by?: 'department' | 'placer';
  month?: string;
  page?: number;
  page_size?: number;
  placer?: string;
  region?: string;
}) {
  return adpulseClient.get<PaginatedResult>('/dashboard/placer_leaderboard', {
    params,
    ...repeatArrayParams,
  });
}

export interface ChannelResult extends PaginatedResult {
  total_row: Record<string, any>;
}

/** 渠道商维度 (筛选不传 = 全部项目) */
export function getChannelOverview(params?: {
  channel?: string;
  date?: string;
  department?: string | string[];
  game_platform?: string;
  page?: number;
  page_size?: number;
  placer?: string;
  region?: string;
}) {
  return adpulseClient.get<ChannelResult>('/dashboard/channel_overview', {
    params,
    ...repeatArrayParams,
  });
}

export interface SpendSummaryResult {
  今日总消耗: number;
  昨日: number;
  本月: number;
  消耗趋势: Array<{ date: string; 消耗: number; 进行中?: boolean }>;
  环比昨日: null | string;
  近7日平均: number;
}

/** 今日总消耗概览 (今日/昨日/近7日平均/本月 + N日折线) */
export function getSpendSummary(
  params?: {
    date?: string;
    game_platform?: string;
    placer?: string;
    region?: string;
    trend_days?: number;
  },
  config?: { signal?: AbortSignal },
) {
  return adpulseClient.get<SpendSummaryResult>('/dashboard/spend_summary', {
    params,
    signal: config?.signal,
    ...repeatArrayParams,
  });
}

export interface IntradayTrendProjectDetail {
  付费成本?: null | number;
  消耗: number;
  订阅成本?: null | number;
  项目: string;
}

export interface IntradayTrendPoint {
  付费成本: null | number;
  时间: string;
  消耗: null | number;
  项目明细?: IntradayTrendProjectDetail[];
}

export interface IntradayTrendResult {
  data: IntradayTrendPoint[];
  kpi_target: null | number;
}

/** 全局当天分时趋势 */
export function getIntradayTrend(
  params?: {
    date?: string;
    game_platform?: string;
    kpi_target?: number;
    /** 24h (默认) / 7d / 30d */
    period?: string;
    placer?: string;
    region?: string;
  },
  config?: { signal?: AbortSignal },
) {
  return adpulseClient.get<IntradayTrendResult>('/dashboard/intraday_trend', {
    params,
    signal: config?.signal,
    ...repeatArrayParams,
  });
}

export interface FilterOptions {
  account_attributes?: string[];
  channels: Array<{ label: string; value: string }>;
  /** 部门显示名与历史报表查询值。 */
  department_options?: Array<{ label: string; value: string }>;
  departments: string[];
  /** label 与接单流程的 display_name 一致；value 为稳定用户 ID。 */
  designers?: Array<{ label: string; value: string }>;
  placers: Array<{ label: string; value: string }>;
  /** 产能按项目 ID 筛选，旧报表继续使用 projects 名称数组。 */
  project_options?: Array<{ label: string; value: string }>;
  projects: string[];
  /** 国家名称来自 MySQL，value 仍为国家代码。 */
  region_options?: Array<{ label: string; value: string }>;
  regions: string[];
}

export interface PersonnelSpendItem {
  /** 飞书登记的账户属性原文，账户及系列/组/广告层返回。 */
  account_attribute?: null | string;
  account_count: number;
  /** 人员关联账户按区间累计消耗拆分；大于 0 为已消耗，其余含 null 为未消耗。 */
  account_spent_count?: number;
  account_unspent_count?: number;
  account_id?: string;
  /** 账户层最新同步的账户状态码，缺失时为 null。 */
  account_status?: null | number | string;
  /** 按区间累计消耗大于 0 的对象 ID 去重；人员层返回三项，系列层返回组和广告数量。 */
  ad_count?: number;
  adset_count?: number;
  campaign_count?: number;
  ad_set_id?: null | string;
  ad_set_name?: null | string;
  campaign_id?: null | string;
  campaign_name?: null | string;
  /** 项目及系列/组/广告层的单账户成效指标，分母为零时为 null。 */
  cpc?: null | number;
  cpm?: null | number;
  department?: null | string;
  game_platform?: string;
  id: string;
  missing_spend_count: number;
  name: string;
  payment_cost?: null | number;
  project_count: number;
  /** 参与聚合的广告日记录数，与跨日期去重的对象数量不同。 */
  record_count: number;
  register_cost?: null | number;
  /** 无有效金额为 null，零消耗为 0；不同币种分别统计。 */
  spends: Array<{ amount: null | number; currency: string }>;
  /** 依据未四舍五入的累计金额识别已消耗币种，供金额颜色使用。 */
  spent_currencies?: string[];
  /** 运营代养账户标识，仅账户层返回。 */
  tag?: null | string;
}

/** 顶部筛选范围汇总；消耗沿用人员归属，账户和项目跨人员去重。 */
export interface PersonnelSpendSummary {
  account_count: number;
  personnel_count: number;
  project_count: number;
  spends: PersonnelSpendItem['spends'];
}

export type PersonnelSpendLevel =
  | 'account'
  | 'ad'
  | 'adset'
  | 'campaign'
  | 'personnel'
  | 'project';

export interface PersonnelSpendResult {
  data: PersonnelSpendItem[];
  data_updated_at: null | string;
  level: PersonnelSpendLevel;
  missing_spend_count: number;
  record_count: number;
  /** 仅人员层 include_summary=true 时返回，下钻响应不清除已加载汇总。 */
  summary?: PersonnelSpendSummary;
  total: number;
}

export interface PersonnelSpendQuery {
  account_attribute?: string;
  account_id?: string;
  ad_set_id?: string;
  campaign_id?: string;
  date: string;
  department?: string;
  game_platform?: string;
  include_summary?: boolean;
  level?: PersonnelSpendLevel;
  placer_id?: string;
}

/** 人员 → 账户 → 项目 → 系列 → 广告组 → 广告；后三层也支持从人员页直接进入。 */
export function getPersonnelSpend(params: PersonnelSpendQuery) {
  return adpulseClient.get<PersonnelSpendResult>('/dashboard/personnel-spend', {
    params,
  });
}

/** 看板筛选项 (项目/地区/渠道商/投手) */
export function getFilterOptions(params?: {
  include_account_attributes?: boolean;
}) {
  return adpulseClient.get<FilterOptions>('/dashboard/filter_options', {
    params,
  });
}

/** 筛选项前缀搜索 (项目/地区/投手), 下拉框按需加载 */
export function searchFilterOptions(params: {
  limit?: number;
  q?: string;
  type: 'placer' | 'project' | 'region';
}) {
  return adpulseClient.get<Array<{ label: string; value: string }>>(
    '/dashboard/filter_search',
    { params },
  );
}

export interface TemplateFilters {
  game_platform: string[];
  placer: string[];
  region: string[];
}

/** 模板列表项: 只有名称 + 上次使用时间 */
export interface FilterTemplate {
  id: string;
  name: string;
  use_time: null | string;
}

/** 应用模板返回: 含实际筛选参数 */
export interface FilterTemplateDetail extends FilterTemplate {
  filters: TemplateFilters;
}

/** 筛选模板 (个人私有) 列表, 按上次使用时间倒序 */
export function listFilterTemplates() {
  return adpulseClient.get<FilterTemplate[]>('/dashboard/filter_templates');
}

/** 应用模板: 取实际筛选参数, 并刷新使用时间 */
export function applyFilterTemplate(id: string) {
  return adpulseClient.get<FilterTemplateDetail>(
    `/dashboard/filter_templates/${id}`,
  );
}

/** 保存当前筛选为模板 */
export function createFilterTemplate(body: {
  filters: TemplateFilters;
  name: string;
}) {
  return adpulseClient.post<FilterTemplate>(
    '/dashboard/filter_templates',
    body,
  );
}

/** 删除筛选模板 */
export function deleteFilterTemplate(id: string) {
  return adpulseClient.delete(`/dashboard/filter_templates/${id}`);
}

// ==================== 实时预警 ====================

export interface AlertMetric {
  change_display?: string;
  change_rate?: number;
  code: string;
  display: string;
  label: string;
  target?: number;
  target_display?: string;
  value: number;
}

export interface AlertAction {
  label: string;
  style: 'danger' | 'secondary';
  type: 'ignore' | 'open_account' | 'pause' | 'snooze' | 'view';
}

export interface AlertItem {
  actions: AlertAction[];
  checked_at: string;
  id: string;
  is_mock?: boolean;
  level?: string;
  metrics: AlertMetric[];
  minutes_ago: number;
  object_id?: string;
  object_name: string;
  placer_id: string;
  platform: string;
  project_name: string;
  rule_id: string;
  rule_type: string;
  rule_type_label: string;
  severity: 'critical' | 'info' | 'warning';
  severity_label: string;
  status: 'action_pending' | 'ignored' | 'pending' | 'snoozed';
  tag: string;
  title: string;
}

export interface AlertFeedResult {
  generated_at: string;
  items: AlertItem[];
  minutes: number;
  summary: { critical: number; info: number; total: number; warning: number };
  total: number;
}

/** 实时预警 Feed */
export async function getAlertFeed(params?: {
  all_records?: boolean;
  include_handled?: boolean;
  minutes?: number;
  mock?: boolean;
  page?: number;
  page_size?: number;
  platform?: string;
  project_id?: string;
  status?: string;
}): Promise<AlertFeedResult> {
  const res = await adpulseClient.get<{
    code: number;
    data: AlertFeedResult;
    message: string;
  }>('/alert-realtime/feed', { params, responseReturn: 'body' } as any);
  return (res as any).data;
}

/** 执行预警动作 (pause / snooze / ignore / view / open_account) */
export async function doAlertAction(
  id: string,
  body: {
    action_type:
      | 'handled'
      | 'ignore'
      | 'open_account'
      | 'pause'
      | 'snooze'
      | 'view';
    snooze_minutes?: number;
  },
): Promise<{ action_type: string; id: string; status: string }> {
  const res = await adpulseClient.post<{
    code: number;
    data: { action_type: string; id: string; status: string };
    message: string;
  }>(`/alert-realtime/${id}/action`, body, { responseReturn: 'body' } as any);
  return (res as any).data;
}
