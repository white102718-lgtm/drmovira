import { adpulseClient } from '#/api/request';

// 统一连接 backend_new（/adpulse-api）；成功响应由客户端解包为 data。

export interface PaginatedData<T> {
  items: T[];
  page?: number;
  page_size?: number;
  total: number;
}

export type KpiMetric = 'daily_spend' | 'purchase_cost' | 'subscription_cost';
export type KpiDirection = 'above' | 'below';
export type KpiDeltaType = 'fixed' | 'percent';
export type KpiConditionLogic = 'AND' | 'OR';
export type KpiNotificationChannel = 'feishu' | 'lark' | 'none' | 'telegram';

export interface KpiOptionItem {
  code: string;
  name: string;
  unit?: string;
}

export interface KpiAgentTarget {
  agent_line: string;
  label: string;
  placer_id?: string;
  platform: string;
  project_id: string;
  project_name: string;
}

export interface KpiBaselineOptions {
  agent_targets: KpiAgentTarget[];
  condition_logics: KpiOptionItem[];
  delta_types: KpiOptionItem[];
  directions: KpiOptionItem[];
  metrics: KpiOptionItem[];
  schedule?: { frequency: string; name: string };
}

export interface KpiCondition {
  delta_type: KpiDeltaType;
  direction: KpiDirection;
  metric: KpiMetric;
  threshold: number;
}

export interface KpiNotification {
  channel: KpiNotificationChannel;
  mention_user?: string;
  target: string;
}

export interface KpiBaselineRule {
  agent_line: string;
  batch_group_id?: string;
  condition_logic: KpiConditionLogic;
  conditions: KpiCondition[];
  created_at?: string;
  created_by?: string;
  enabled: boolean;
  id: string;
  last_error?: string;
  last_evaluated_at?: string;
  last_snapshot_at?: string;
  notification: KpiNotification;
  placer_id?: string;
  platform: string;
  project_id?: string;
  project_name?: string;
  rule_name: string;
  severity?: string;
  updated_at?: string;
  updated_by?: string;
}

export interface KpiBaselinePayload {
  agent_line: string;
  condition_logic: KpiConditionLogic;
  conditions: KpiCondition[];
  enabled: boolean;
  notification: KpiNotification;
  platform: string;
  rule_name: string;
  severity?: string;
}

export interface KpiBatchCreatePayload
  extends Omit<KpiBaselinePayload, 'agent_line' | 'platform'> {
  // 传 true 表示对全部有效代理线创建规则，无需再传 agent_targets
  all_agent_targets?: boolean;
  agent_targets?: Array<{ agent_line: string; platform: string }>;
}

export interface KpiRuleQuery {
  agent_line?: string;
  batch_group_id?: string;
  enabled?: boolean;
  page: number;
  page_size: number;
  platform?: string;
  project_id?: string;
}

export interface KpiPreviewResult {
  agent_metrics: Record<string, null | number>;
  condition_logic: KpiConditionLogic;
  condition_results: Array<
    KpiCondition & {
      actual_value: null | number;
      baseline_value: null | number;
      difference: null | number;
      difference_rate: null | number;
      matched: boolean;
      reason: string;
      target_value: null | number;
    }
  >;
  matched: boolean;
  project_metrics: Record<string, null | number>;
  snapshot_at?: string;
  target: KpiAgentTarget;
}

export interface KpiSnapshot {
  agent_line_count: number;
  id: string;
  project_id: string;
  project_name: string;
  purchase_cost: null | number;
  purchases: number;
  snapshot_at: string;
  subscription_cost: null | number;
  subscriptions: number;
  total_spend: number;
}

export interface KpiRefreshResult {
  errors: string[];
  evaluated_count: number;
  project_count: number;
  refreshed_at: string;
  requested_project_count: number;
  skipped_duplicate_count: number;
  triggered_count: number;
}

export interface KpiAlertFeedItem {
  agent_line?: string;
  condition_logic?: string;
  condition_results?: any[];
  id: string;
  level?: string;
  notification_item?: Record<string, any>;
  placer_id?: string;
  project_id?: string;
  project_name?: string;
  rule_id?: string;
  rule_name?: string;
  severity?: string;
  snapshot_at?: string;
  source_type?: string;
  status?: string;
  updated_at?: string;
  [key: string]: any;
}

const BASE = '/kpi-baseline-rules';

export async function getKpiBaselineOptions(): Promise<KpiBaselineOptions> {
  const res = await adpulseClient.get<KpiBaselineOptions>(`${BASE}/options`);
  return res;
}

export async function listKpiBaselineRules(
  params: KpiRuleQuery,
): Promise<PaginatedData<KpiBaselineRule>> {
  const res = await adpulseClient.get<PaginatedData<KpiBaselineRule>>(BASE, {
    params,
  });
  return res ?? { items: [], total: 0 };
}

export async function createKpiBaselineRule(
  data: KpiBaselinePayload,
): Promise<{ id: string }> {
  const res = await adpulseClient.post<{ id: string }>(BASE, data, {
    skipErrorMessage: true,
  });
  return res;
}

export async function createKpiBaselineRulesBatch(
  data: KpiBatchCreatePayload,
): Promise<{ batch_group_id: string; created_count: number; ids: string[] }> {
  const res = await adpulseClient.post<{
    batch_group_id: string;
    created_count: number;
    ids: string[];
  }>(`${BASE}/batch`, data, { skipErrorMessage: true });
  return res;
}

export async function updateKpiBaselineRule(
  id: string,
  data: Partial<KpiBaselinePayload>,
): Promise<{ id: string }> {
  const res = await adpulseClient.put<{ id: string }>(`${BASE}/${id}`, data, {
    skipErrorMessage: true,
  });
  return res;
}

export async function toggleKpiBaselineRule(
  id: string,
  enabled?: boolean,
): Promise<{ enabled: boolean; id: string }> {
  const res = await adpulseClient.request<{ enabled: boolean; id: string }>(
    `${BASE}/${id}/toggle`,
    { method: 'PATCH', data: enabled === undefined ? {} : { enabled } },
  );
  return res;
}

export async function deleteKpiBaselineRule(id: string): Promise<void> {
  await adpulseClient.delete(`${BASE}/${id}`);
}

export async function updateKpiBaselineBatchGroup(
  batchGroupId: string,
  data: Partial<KpiBaselinePayload>,
): Promise<void> {
  await adpulseClient.put(`${BASE}/batch-groups/${batchGroupId}`, data, {
    skipErrorMessage: true,
  });
}

export async function toggleKpiBaselineBatchGroup(
  batchGroupId: string,
  enabled: boolean,
): Promise<void> {
  await adpulseClient.request(`${BASE}/batch-groups/${batchGroupId}/toggle`, {
    method: 'PATCH',
    data: { enabled },
  });
}

export async function deleteKpiBaselineBatchGroup(
  batchGroupId: string,
): Promise<void> {
  await adpulseClient.delete(`${BASE}/batch-groups/${batchGroupId}`);
}

export async function previewKpiBaselineRule(
  data: KpiBaselinePayload,
): Promise<KpiPreviewResult> {
  const res = await adpulseClient.post<KpiPreviewResult>(
    `${BASE}/preview`,
    data,
    {
      skipErrorMessage: true,
    },
  );
  return res;
}

export async function listKpiSnapshots(params?: {
  limit?: number;
  project_id?: string;
}): Promise<{ items: KpiSnapshot[] }> {
  const res = await adpulseClient.get<{ items: KpiSnapshot[] }>(
    `${BASE}/snapshots`,
    {
      params,
    },
  );
  return res ?? { items: [] };
}

export async function refreshKpiSnapshots(): Promise<KpiRefreshResult> {
  const res = await adpulseClient.post<KpiRefreshResult>(
    `${BASE}/snapshots/refresh`,
  );
  return res;
}

export async function listKpiAlertFeed(params: {
  page: number;
  page_size: number;
  status?: string;
}): Promise<PaginatedData<KpiAlertFeedItem>> {
  const res = await adpulseClient.get<PaginatedData<KpiAlertFeedItem>>(
    '/alert-realtime/feed',
    {
      params: { all_records: 1, source_type: 'kpi_baseline', ...params },
    },
  );
  return res ?? { items: [], total: 0 };
}
