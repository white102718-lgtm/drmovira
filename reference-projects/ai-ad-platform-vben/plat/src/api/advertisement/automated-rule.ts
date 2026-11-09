import { adpulseClient } from '#/api/request';

// 统一连接 backend_new（/adpulse-api）；成功响应由客户端解包为 data。

// ==================== 枚举 / 基础类型 ====================

export type ConditionOperator = 'between' | 'gte' | 'lte';
export type TimeWindow = 'past_2_days' | 'past_3_days' | 'today';
export type RuleLevel = 'ad' | 'adset' | 'campaign';
export type ActionType = 'daily_budget' | 'status';
export type NotificationChannel = 'feishu' | 'lark' | 'none' | 'telegram';
export type EffectiveType = 'custom' | 'long_term';
export type Frequency =
  | 'custom'
  | 'daily'
  | 'daily_times'
  | 'every_2_hours'
  | 'every_3_hours'
  | 'every_4_hours'
  | 'every_5_hours'
  | 'every_6_hours'
  | 'half_hour'
  | 'hourly';
export type AdjustDirection = 'decrease' | 'increase';
export type AdjustUnit = 'fixed' | 'percent';

// ==================== 条件 / 动作 / 通知 / 计划 ====================

export interface RuleCondition {
  metric: string;
  operator: ConditionOperator;
  time_window: TimeWindow;
  value: null | number;
  value_max: null | number;
  value_min: null | number;
}

export interface StatusAction {
  action_type: 'status';
  status: 'active' | 'paused';
}

export interface AdjustAction {
  action_type: 'daily_budget';
  direction: AdjustDirection;
  limit_type: 'max' | 'min';
  limit_value: number;
  unit: AdjustUnit;
  value: number;
}

export type RuleAction = AdjustAction | StatusAction;

export interface RuleNotification {
  channel: NotificationChannel;
  mention_user?: string;
  target: string;
}

export interface TargetScope {
  ad_ids: string[];
  adset_ids: string[];
  campaign_ids: string[];
}

export interface RuleSchedule {
  custom_check_times: string[];
  custom_cron: null | string;
  daily_check_times: string[];
  effective_ranges: any[];
  effective_type: EffectiveType;
  frequency: Frequency;
  timezone: string;
}

export interface Branch {
  actions: RuleAction[];
  branch_name: string;
  condition_expression: string;
  condition_logic: 'AND' | 'OR';
  conditions: RuleCondition[];
}

export interface LastExecution {
  checked_at: string;
  message: string;
  status: string;
}

// ==================== 主实体 ====================

export interface AutomationRule {
  schedule_summary: string;
  account_id: string;
  account_name: string;
  action_summary?: string;
  actions: RuleAction[];
  agent_line: string;
  auto_execute: boolean;
  branches?: Branch[];
  campaign_id: string;
  campaign_name?: string;
  condition_logic: 'AND' | 'OR';
  condition_summary?: string;
  conditions: RuleCondition[];
  created_at: string;
  created_by?: string;
  enabled: boolean;
  id: string;
  last_execution?: LastExecution;
  levels: RuleLevel[];
  media_buyer: string;
  notification: RuleNotification;
  platform?: string;
  project_id?: string;
  project_ids: string[];
  rule_name: string;
  schedule: RuleSchedule;
  target_scope: TargetScope;
  target_summary?: string;
  updated_at: string;
  updated_by?: string;
}

export type RulePayload = Omit<
  AutomationRule,
  | 'action_summary'
  | 'condition_summary'
  | 'created_at'
  | 'created_by'
  | 'id'
  | 'last_execution'
  | 'schedule_summary'
  | 'target_summary'
  | 'updated_at'
  | 'updated_by'
>;

// ==================== 查询参数 ====================

export interface RuleQuery {
  account_id?: string;
  /** 分类别名，后端会按 rule_type 处理（category=cost 等价 rule_type=spend） */
  category?: string;
  enabled?: boolean;
  keyword?: string;
  media_buyer?: string;
  page: number;
  page_size: number;
  project_id?: string;
  /** 规则类型筛选：spend/conversion/account/behavior/creative */
  rule_type?: string;
}

export interface RecordQuery {
  account?: string;
  account_id?: string;
  action_filter?: string;
  agent_line?: string;
  keyword?: string;
  level?: string;
  page: number;
  page_size: number;
  project_id?: string;
  rule_id?: string;
  checked_end?: string;
  checked_start?: string;
  source_type?: string;
  status?: string;
}

// ==================== 其他实体 ====================

export interface RuleRecord {
  account_id: string;
  checked_at: string;
  id: string;
  level: string;
  message: string;
  object_id: string;
  object_name: string;
  project_id: string;
  rule_id: string;
  rule_name: string;
  status: string;
}

export interface SuggestedAction {
  current_value: null | number;
  label: string;
  target_value: null | number;
  type: string;
}

export interface MetricSnapshot {
  budget?: null | number;
  purchase_roas?: null | number;
  purchases?: null | number;
  registrations?: null | number;
  registration_cost?: null | number;
  spend?: null | number;
  [key: string]: null | number | undefined;
}

export interface MetricWindow {
  hours: number;
  label: string;
  time_window: string;
  current: MetricSnapshot;
  baseline: MetricSnapshot;
  delta: MetricSnapshot;
}

export interface NotificationItem {
  account_id: string;
  account_name: string;
  ad_id: string;
  ad_name: string;
  adset_id: string;
  adset_name: string;
  agent_line: string;
  budget: null | number;
  campaign_id: string;
  campaign_name: string;
  cpi: null | number;
  handled_at?: string;
  handling_status: string;
  level: string;
  project_id: string;
  project_name: string;
  click_cost: null | number;
  impression_cost: null | number;
  purchase_cost: null | number;
  purchase_roas: null | number;
  purchases: null | number;
  record_status: string;
  registration_cost: null | number;
  registrations: null | number;
  roas: null | number;
  source_label: string;
  source_type: 'ai' | 'manual' | 'rule';
  spend: null | number;
  subscription_cost: null | number;
  suggested_action: SuggestedAction;
  metric_window?: MetricWindow | null;
}

export interface NotificationRecord extends RuleRecord {
  notification_item: NotificationItem;
}

export interface OptionItem {
  code: string;
  name: string;
}

export interface OperatorOption extends OptionItem {
  value_count: number;
}

export interface RuleOptions {
  actions: OptionItem[];
  adjust_directions: OptionItem[];
  adjust_units: OptionItem[];
  frequencies: OptionItem[];
  levels: OptionItem[];
  metrics: OptionItem[];
  notification_channels: OptionItem[];
  operators: OperatorOption[];
  status_values: OptionItem[];
  time_windows: OptionItem[];
  timezones: OptionItem[];
}

export interface Project {
  _id: string;
  agent_lines: { agent_line: string; platform: string }[];
  is_active: boolean;
  name: string;
}

export interface PlatformConfig {
  id: string;
  name: string;
  platform: string;
  raw: Record<string, any>;
  value: string;
}

export interface MediaBuyer {
  id: string;
  name: string;
  project_id: string;
  real_name: string;
  username: string;
}

export interface AdAccount {
  account_id: string;
  account_name: string;
  media_buyer_id: string;
  media_buyer_name: string;
  platform: string;
  project_id: string;
  timezone: string;
}

export interface AdObject {
  account_id: string;
  id: string;
  level: string;
  name: string;
  parent_id: null | string;
  status: string;
}

// ==================== 分页数据 ====================

interface PaginatedData<T> {
  items: T[];
  total: number;
}

// ==================== API 函数 ====================

export async function getOptions(): Promise<RuleOptions> {
  const res = await adpulseClient.get<RuleOptions>('/automation-rules/options');
  return res;
}

export async function getProjects(): Promise<Project[]> {
  const res = await adpulseClient.get<Project[]>('/project', {
    params: { is_active: true },
  });
  return res;
}

export async function getPlatformConfigs(): Promise<PlatformConfig[]> {
  const res = await adpulseClient.get<PlatformConfig[]>('/platform-configs');
  return res ?? [];
}

export async function getMediaBuyers(params?: {
  keyword?: string;
  project_id?: string;
}): Promise<MediaBuyer[]> {
  const res = await adpulseClient.get<MediaBuyer[]>('/media-buyers', {
    params,
  });
  return res ?? [];
}

export async function getAdAccounts(params?: {
  media_buyer?: string;
  platform?: string;
  project_id?: string;
}): Promise<AdAccount[]> {
  const res = await adpulseClient.get<AdAccount[]>('/ad-accounts', { params });
  return res ?? [];
}

export async function getAdObjects(params?: {
  account_id?: string;
  keyword?: string;
  level?: string;
  page?: number;
  page_size?: number;
  parent_id?: string;
}): Promise<PaginatedData<AdObject>> {
  const res = await adpulseClient.get<PaginatedData<AdObject>>('/ad-objects', {
    params,
  });
  return res ?? { items: [], total: 0 };
}

export async function listRules(
  params: RuleQuery,
): Promise<PaginatedData<AutomationRule>> {
  const res = await adpulseClient.get<PaginatedData<AutomationRule>>(
    '/automation-rules',
    { params },
  );
  return res;
}

export async function getRule(id: string): Promise<AutomationRule> {
  const res = await adpulseClient.get<AutomationRule>(
    `/automation-rules/${id}`,
  );
  return res;
}

export async function createRule(data: RulePayload): Promise<{ id: string }> {
  const res = await adpulseClient.post<{ id: string }>(
    '/automation-rules',
    data,
    { skipErrorMessage: true },
  );
  return res;
}

export async function updateRule(
  id: string,
  data: RulePayload,
): Promise<{ id: string }> {
  const res = await adpulseClient.put<{ id: string }>(
    `/automation-rules/${id}`,
    data,
    { skipErrorMessage: true },
  );
  return res;
}

export async function copyRule(
  id: string,
): Promise<{ id: string; rule_name: string }> {
  const res = await adpulseClient.post<{ id: string; rule_name: string }>(
    `/automation-rules/${id}/copy`,
    {},
    {
      skipErrorMessage: true,
    },
  );
  return res;
}

export async function deleteRule(id: string): Promise<void> {
  await adpulseClient.delete(`/automation-rules/${id}`);
}

export async function toggleRule(
  id: string,
): Promise<{ enabled: boolean; id: string }> {
  const res = await adpulseClient.request<{ enabled: boolean; id: string }>(
    `/automation-rules/${id}/toggle`,
    {
      method: 'PATCH',
    },
  );
  return res;
}

export async function toggleAutoExecute(
  id: string,
  auto_execute: boolean,
): Promise<void> {
  await adpulseClient.request(`/automation-rules/${id}/auto-execute`, {
    method: 'PATCH',
    data: { auto_execute },
  });
}

export async function listRecords(
  params: RecordQuery,
): Promise<PaginatedData<RuleRecord>> {
  // 规则库行为记录包含已处理状态；待确认弹窗继续使用 pending 接口。
  const res = await adpulseClient.get<PaginatedData<RuleRecord>>(
    '/automation-rule-records/history',
    { params },
  );
  return res;
}

export async function listNotificationRecords(
  params: RecordQuery,
): Promise<PaginatedData<NotificationRecord>> {
  const res = await adpulseClient.get<PaginatedData<NotificationRecord>>(
    '/automation-rule-records',
    {
      params,
    },
  );
  return res;
}

export async function listHistoryRecords(
  params: RecordQuery,
): Promise<PaginatedData<RuleRecord>> {
  const res = await adpulseClient.get<PaginatedData<RuleRecord>>(
    '/automation-rule-records/history',
    { params },
  );
  return res;
}

export async function approveRecord(id: string): Promise<NotificationRecord> {
  const res = await adpulseClient.post<NotificationRecord>(
    `/automation-rule-records/${id}/approve`,
  );
  return res;
}

export async function ignoreRecord(id: string): Promise<NotificationRecord> {
  const res = await adpulseClient.post<NotificationRecord>(
    `/automation-rule-records/${id}/ignore`,
  );
  return res;
}

export type BatchActionPayload =
  | {
      action: {
        action_type: 'daily_budget';
        direction: 'decrease' | 'increase';
        unit: 'fixed' | 'percent';
        value: number;
      };
      record_ids: string[];
    }
  | {
      action: { action_type: 'status'; status: 'paused' };
      record_ids: string[];
    };

export async function batchAction(payload: BatchActionPayload): Promise<void> {
  await adpulseClient.post('/automation-rule-records/batch-action', payload);
}

export interface PendingSummary {
  ai_suggestion_count: number;
  rule_suggestion_count: number;
  total_pending_count: number;
}

export async function getPendingSummary(): Promise<PendingSummary> {
  const res = await adpulseClient.get<PendingSummary>(
    '/automation-rule-records/pending-summary',
  );
  return res;
}
