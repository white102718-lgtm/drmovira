import { adpulseClient } from '#/api/request';

interface ApiResponse<T> {
  code: number;
  data: T;
  message: string;
}

// ==================== 响应类型 ====================

export interface CategoryCount {
  category: string;
  name: string;
  count: number;
}

export interface SeverityStat {
  severity: string;
  name: string;
  count: number;
  daily_average: number;
}

export interface TopRule {
  rule_id: string;
  rule_name: string;
  count: number;
}

export interface TriggerStats {
  days: number;
  total: number;
  by_severity: SeverityStat[];
  top_rules: TopRule[];
}

export interface AlertRulesSync {
  refresh_seconds: number;
  data_source_status: string;
}

export interface AlertRulesOverview {
  enabled_rule_count: number;
  total_rule_count: number;
  last_updated_at: string;
  category_counts: CategoryCount[];
  trigger_stats: TriggerStats;
  sync: AlertRulesSync;
}

export interface NotificationChannelItem {
  channel: string;
  name: string;
  target_name?: string;
  status: string;
  status_name: string;
  last_checked_at?: string;
}

export interface NotificationChannelsData {
  items: NotificationChannelItem[];
}

// ==================== API 函数 ====================

/** 获取预警规则概览（规则数量、分类统计、近 N 日触发统计） */
export async function getAlertRulesOverview(params?: {
  days?: number;
  project_id?: string;
  platform?: string;
}): Promise<AlertRulesOverview> {
  const res = await adpulseClient.get<ApiResponse<AlertRulesOverview>>(
    '/alert-rules/overview',
    { params, responseReturn: 'body' },
  );
  return (res as any).data;
}

/** 获取通知渠道连接状态 */
export async function getNotificationChannels(): Promise<NotificationChannelsData> {
  const res = await adpulseClient.get<ApiResponse<NotificationChannelsData>>(
    '/notification-channels',
    { responseReturn: 'body' },
  );
  return (res as any).data;
}
