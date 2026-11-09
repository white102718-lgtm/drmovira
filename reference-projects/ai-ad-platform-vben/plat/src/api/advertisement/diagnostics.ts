import { adpulseClient } from '#/api/request';

interface ApiResponse<T> {
  code: number;
  data: T;
  message: string;
}

// ==================== 查询参数 ====================

export interface DrilldownQuery {
  level: string;
  object_id: string;
  project_id?: string;
  platform?: string;
  agent_line?: string;
  account_id?: string;
  campaign_id?: string;
  adset_id?: string;
  ad_id?: string;
  window?: string;
  baseline_window?: string;
}

export interface TimelineQuery extends DrilldownQuery {
  event_type?: string;
  page?: number;
  page_size?: number;
}

// ==================== 响应类型 ====================

export interface DrilldownWindow {
  code: string;
  label: string;
  start_at: string;
  end_at: string;
}

export interface DrilldownSync {
  refresh_seconds: number;
  last_synced_at: string;
  data_source_status: string;
}

export interface DrilldownBuyer {
  placer_id: string;
  name: string;
}

export interface DrilldownPathItem {
  level: string;
  level_name: string;
  object_id: string;
  object_name: string;
  primary_metric?: number;
  primary_metric_name?: string;
  secondary_text?: string;
  change_rate?: number;
  alert_count?: number;
  is_current?: boolean;
}

export interface DrilldownMetric {
  code: string;
  name: string;
  value: number;
  unit?: string;
  threshold?: number;
  target?: number;
  change_value?: number;
  change_type?: string;
  status?: string;
}

export interface SuggestedAction {
  type: string;
  label: string;
  target_level?: string;
  target_id?: string;
  target_status?: string;
}

export interface RootCause {
  id: string;
  severity: string;
  severity_label: string;
  category: string;
  title: string;
  description: string;
  confidence: number;
  suggested_actions: SuggestedAction[];
}

export interface ChildrenMetrics {
  spend?: number;
  cpa?: number;
  roas?: number;
  registrations?: number;
}

export interface ChildrenItem {
  object_id: string;
  object_name: string;
  description?: string;
  metrics: ChildrenMetrics;
  status?: string;
  drilldown_available?: boolean;
}

export interface ChildrenSummary {
  /** 下一层对象总条数 */
  total?: number;
  hidden_count?: number;
  spend?: number;
  cpa?: number;
  roas?: number;
  registrations?: number;
}

export interface DrilldownChildren {
  level: string;
  sort?: string;
  items: ChildrenItem[];
  summary?: ChildrenSummary;
}

export interface TimelineSummary {
  start_at: string;
  end_at: string;
  operation_count: number;
  system_count: number;
}

export interface DrilldownData {
  title: string;
  summary: string;
  window: DrilldownWindow;
  sync: DrilldownSync;
  buyer?: DrilldownBuyer;
  path: DrilldownPathItem[];
  current_metrics: DrilldownMetric[];
  root_causes: RootCause[];
  children: DrilldownChildren;
  timeline_summary: TimelineSummary;
}

export interface TimelineEvent {
  id: string;
  event_type: string;
  event_type_label: string;
  occurred_at: string;
  operator?: string;
  title: string;
  description?: string;
  level?: string;
  object_id?: string;
  object_name?: string;
  source?: string;
  source_id?: string;
}

export interface DrilldownTimelineData {
  items: TimelineEvent[];
  total: number;
  page: number;
  page_size: number;
}

export interface ExportPayload {
  level: string;
  object_id: string;
  format: 'csv' | 'pdf';
  include_timeline?: boolean;
  include_children?: boolean;
  section?: string;
}

export interface ExportResult {
  task_id: string;
  status: string;
  download_url: string | null;
}

export interface DiagnosticActionPayload {
  source: string;
  source_id: string;
  action: {
    type: string;
    target_level?: string;
    target_id?: string;
    target_status?: string;
  };
  reason?: string;
}

export interface DiagnosticActionResult {
  id: string;
  status: string;
}

// ==================== API 函数 ====================

/** 获取下钻分析详情 */
export async function getDrilldown(params: DrilldownQuery): Promise<DrilldownData> {
  const res = await adpulseClient.get<ApiResponse<DrilldownData>>(
    '/diagnostics/drilldown',
    { params, responseReturn: 'body' },
  );
  return (res as any).data;
}

/** 获取下钻时间线 */
export async function getDrilldownTimeline(
  params: TimelineQuery,
): Promise<DrilldownTimelineData> {
  const res = await adpulseClient.get<ApiResponse<DrilldownTimelineData>>(
    '/diagnostics/drilldown/timeline',
    { params, responseReturn: 'body' },
  );
  return (res as any).data;
}

/** 导出下钻报告 */
export async function exportDrilldown(data: ExportPayload): Promise<ExportResult> {
  const res = await adpulseClient.post<ApiResponse<ExportResult>>(
    '/diagnostics/drilldown/export',
    data,
    { responseReturn: 'body' } as any,
  );
  return (res as any).data;
}

/** 创建诊断动作（当前只入库为 pending，不触发媒体平台） */
export async function createDiagnosticAction(
  data: DiagnosticActionPayload,
): Promise<DiagnosticActionResult> {
  const res = await adpulseClient.post<ApiResponse<DiagnosticActionResult>>(
    '/diagnostics/actions',
    data,
    { responseReturn: 'body' } as any,
  );
  return (res as any).data;
}
