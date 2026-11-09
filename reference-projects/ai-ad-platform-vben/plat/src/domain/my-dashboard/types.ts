import type {
  AdDashboardListQuery,
  AdDashboardListResult,
} from '../ad-dashboard';

/** 日期沿用广告账户本地报表日期，金额始终按账户币种返回。 */
export interface DashboardDateQuery {
  endDate: string;
  startDate: string;
}

export interface DashboardMetrics {
  cpa: null | number;
  ctr: null | number;
  registrations: number;
  spend: number;
}

export interface DashboardSummary extends DashboardMetrics {
  cpaChange: null | number;
  currency: string;
  registrationsChange: null | number;
  spendChange: null | number;
}

export interface DashboardOverview {
  dataCutoff: string;
  dateBasis: 'account_local';
  previousEndDate: string;
  previousStartDate: string;
  summaries: DashboardSummary[];
}

export interface DashboardAccount extends DashboardMetrics {
  accountStatus: null | string;
  activity: 'active' | 'attention' | 'idle' | 'unknown';
  currency: string;
  id: string;
  name: string;
}

export interface DashboardAccounts {
  activity: {
    active: number;
    attention: number;
    idle: number;
    rate: number;
    scopeLabel: string;
    total: number;
    unknown: number;
  };
  items: DashboardAccount[];
}

export interface DashboardTrend {
  cumulative: boolean;
  granularity: 'day' | 'hour';
  series: {
    currency: string;
    points: (DashboardMetrics & { label: string })[];
  }[];
}

export interface DashboardObjectQuery extends AdDashboardListQuery {
  accountId?: string;
}

/** 代理线明细成效来自广告数据 API：账户原币种，CTR 为比率，空值保留。 */
export interface DashboardCampaignPerformance {
  cpa: null | number;
  ctr: null | number;
  currency: string;
  id: string;
  name: string;
  spend: null | number;
}

export type DashboardRange = 'month' | 'today' | 'week';
export type DashboardActionKind = 'bid_review' | 'budget' | 'observe';

/** 智能体按北京时间查询；不提供 placer_id，所有角色都使用 JWT 本人。 */
export interface DashboardAnalyzeQuery {
  account_id?: string;
  end_date: string;
  /** 单条代理线手动分析时传稳定 campaign_id，不提交浏览器成效数据。 */
  focus_id?: string;
  grain?: 'campaign';
  range: DashboardRange;
  start_date: string;
}

/** 此处代理线是 campaign_id；金额为 USD，CTR 经 Adapter 统一为百分数。 */
export interface DashboardAnalysisObject {
  action?: string;
  cpa: null | number;
  ctr: null | number;
  id: string;
  kind?: DashboardActionKind;
  label?: string;
  level: 'campaign';
  name: string;
  reason?: string;
  spend: number;
  status?: '表现良好' | '观察中' | '需处理';
}

export interface DashboardAnalysisAction {
  action: string;
  expected: string;
  kind: DashboardActionKind;
  label: string;
  priority: string;
  reason: string;
  target: string;
}

export interface DashboardAnalysis {
  analysis: {
    actions?: DashboardAnalysisAction[];
    anomaly?: string;
    confidence?: 'high' | 'low' | 'medium';
    headline?: string;
    locate?: string;
    suggested_kind?: DashboardActionKind;
  };
  fact: {
    account_id?: string;
    cpa: null | number;
    cpa_change: null | number;
    end_date: string;
    objects: DashboardAnalysisObject[];
    placer_id: string;
    range: DashboardRange;
    registrations: number;
    registrations_change: null | number;
    series: { labels: string[]; registrations: number[]; spend: number[] };
    spend: number;
    spend_change: null | number;
    start_date: string;
  };
}

export interface DashboardHosting {
  cadence?: 'hourly' | 'realtime';
  enabled: boolean;
  feishu_bound?: boolean;
  placer_id?: string;
  range?: DashboardRange;
  spend_change_threshold?: number;
  updated_at?: string;
}

/** 托管监测本人整窗，不接受账户或其他投放师身份。 */
export type DashboardHostingQuery =
  | {
      cadence: 'hourly' | 'realtime';
      enabled: true;
      range: DashboardRange;
      spend_change_threshold: number;
    }
  | { enabled: false };

/** 正式与演示数据在 Adapter 处切换，页面只调用同一套查询服务。 */
export interface MyDashboardAdapter {
  accounts(query: DashboardDateQuery): Promise<DashboardAccounts>;
  analyze(
    query: DashboardAnalyzeQuery,
    signal?: AbortSignal,
  ): Promise<DashboardAnalysis>;
  getHosting(): Promise<DashboardHosting>;
  list(query: DashboardObjectQuery): Promise<AdDashboardListResult>;
  overview(query: DashboardDateQuery): Promise<DashboardOverview>;
  saveHosting(query: DashboardHostingQuery): Promise<DashboardHosting>;
  trend(query: DashboardDateQuery): Promise<DashboardTrend>;
}
