/** 项目日报按代理线项 + CMS GMT+0 自然日汇总的一行。 */

export const PROJECT_DAILY_RETENTION_DAYS = [
  2, 3, 4, 5, 6, 7, 10, 15, 20, 25, 30, 45, 60, 90,
] as const;

export type ProjectDailyRetentionDay =
  (typeof PROJECT_DAILY_RETENTION_DAYS)[number];

export type ProjectDailyReportDimension = 'day' | 'item';

export interface ProjectDailyReportOption {
  agencyLineId?: string;
  id: string;
  name: string;
  projectId?: string;
}

export interface ProjectDailyReportRow {
  /** 代理线，对应 CMS 推广商，如 66x-tt。 */
  agencyLineId: string;
  /** 代理线项，对应推广商下的渠道。 */
  agencyLineItemId: string;
  agencyLineItemName: string;
  agencyLineName: string;
  currency: string;
  date: string;
  firstDepositAmount: number;
  firstDepositUsers: number;
  id: string;
  projectId: string;
  projectName: string;
  rechargeAmount: number;
  /**
   * 各日留存率，单位为百分比 0～100。CMS 未到期字段为 -1，这里转为 null。
   */
  retention: Partial<Record<ProjectDailyRetentionDay, null | number>>;
  /** 按天汇总时带回的留存人数，和 CMS「717(31.87%)」同一展示。 */
  retentionUsers?: Partial<Record<ProjectDailyRetentionDay, null | number>>;
  dimension?: ProjectDailyReportDimension;
  repeatRechargeUsers: number;
  /**
   * 投放消耗，来自 AdPulse 日表 ad_daily_detail，按代理线项名称 + CMS GMT+0 日期字符串对齐。
   * 日表 date 是账户时区日。币种是美元，不能和 CMS 的 BRL 充值混用。
   */
  spendAmount: number;
  spendCurrency?: string;
  withdrawalAmount: number;
  withdrawalUsers: number;
}

export interface ProjectDailyReportQuery {
  agencyLineId?: string;
  agencyLineItemId?: string;
  dimension?: ProjectDailyReportDimension;
  endDate: string;
  includeCatalogs?: boolean;
  page?: number;
  pageSize?: number;
  projectId?: string;
  startDate: string;
}

export interface ProjectDailyReportSummary {
  averageRetention7: number | null;
  currency: string;
  firstDepositAmount: number;
  firstDepositUsers: number;
  rechargeAmount: number;
  spendAmount: number;
  withdrawalAmount: number;
}

export interface ProjectDailyReportResult {
  agencyLineItems: ProjectDailyReportOption[];
  agencyLines: ProjectDailyReportOption[];
  projects: ProjectDailyReportOption[];
  rows: ProjectDailyReportRow[];
  summary: ProjectDailyReportSummary;
  /** 当前筛选条件下的总行数。服务端分页时只返回当前页 rows。 */
  total?: number;
  /** 最近一次爬取完成时间（UTC ISO）。 */
  updatedAt: string;
}

export type ProjectDailyReportSyncStatusValue =
  | 'failed'
  | 'idle'
  | 'running'
  | 'succeeded';

export interface ProjectDailyReportSyncStatus {
  alreadyRunning?: boolean;
  errorMessage?: null | string;
  finishedAt: null | string;
  id: string;
  rowCount: number;
  startedAt: string;
  status: ProjectDailyReportSyncStatusValue;
  triggerType: 'manual' | 'schedule';
}

export interface ProjectDailyReportImportResult {
  files: number;
  projects: ProjectDailyReportOption[];
  rowCount: number;
  skippedFiles: string[];
  skippedRows: number;
  updatedAt: string;
}

export interface ProjectDailyReportAdapter {
  getSyncStatus(): Promise<ProjectDailyReportSyncStatus>;
  importExcel(file: File): Promise<ProjectDailyReportImportResult>;
  query(input: ProjectDailyReportQuery): Promise<ProjectDailyReportResult>;
  startSync(): Promise<ProjectDailyReportSyncStatus>;
}
