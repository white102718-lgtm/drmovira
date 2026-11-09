import type { ProjectSummary } from '#/domain/project';

export type ComparisonAssessment = 'bad' | 'good' | 'neutral' | 'unknown';

export type ComparisonDirection = 'down' | 'flat' | 'new' | 'up';

export type ComparisonGranularity = 'day' | 'hour';

export type ComparisonPeriodMode = 'custom' | 'last-7-days' | 'today';

export type ComparisonValueStatus = 'missing' | 'new' | 'no-base' | 'valid';

export type ProjectComparisonMetricKey =
  | 'clicks'
  | 'ctr'
  | 'firstPurchaseCost'
  | 'firstPurchases'
  | 'impressions'
  | 'profitMargin'
  | 'projectCost'
  | 'projectProfit'
  | 'registrationCost'
  | 'registrations'
  | 'roas'
  | 'serviceFeeRevenue'
  | 'spend';

export interface ComparisonPeriod {
  /** Inclusive local calendar date in the selected project's timezone. */
  endDate: string;
  /** Inclusive local calendar date in the selected project's timezone. */
  startDate: string;
}

export interface ProjectComparisonQuery {
  agencyLineIds?: string[];
  comparison: ComparisonPeriod;
  current: ComparisonPeriod;
  granularity: ComparisonGranularity;
  mode: ComparisonPeriodMode;
  projectId: string;
}

export interface ProjectComparisonMetric {
  assessment: ComparisonAssessment;
  changeRate: null | number;
  comparison: null | number;
  current: null | number;
  difference: null | number;
  direction: ComparisonDirection;
  key: ProjectComparisonMetricKey;
  status: ComparisonValueStatus;
}

export type ProjectComparisonMetricValues = Partial<
  Record<ProjectComparisonMetricKey, number>
>;

export interface ProjectComparisonTrendPoint {
  bucket: string;
  comparison: null | number;
  comparisonBucket: string;
  current: null | number;
}

export interface ProjectComparisonAgencyLine {
  agencyLineId: string;
  current: ProjectComparisonMetricValues;
  metrics: Partial<Record<ProjectComparisonMetricKey, ProjectComparisonMetric>>;
  name: string;
  platform: string;
}

/** A read-only creative direction composed from stable material version IDs. */
export interface ProjectComparisonCreativeDirection {
  agencyLineId: string;
  agencyLineName: string;
  assetType: 'image' | 'text' | 'video';
  creativeDirectionId: string;
  current: ProjectComparisonMetricValues;
  materialVersionCount: number;
  metrics: Partial<Record<ProjectComparisonMetricKey, ProjectComparisonMetric>>;
  name: string;
  platform: string;
}

export type ProjectComparisonAlertLevel = 'critical' | 'warning';

export interface ProjectComparisonAlert {
  agencyLineId?: string;
  agencyLineName?: string;
  current: number;
  key: ProjectComparisonMetricKey;
  level: ProjectComparisonAlertLevel;
  message: string;
  title: string;
}

export interface ProjectComparisonInsight {
  body: string;
  id:
    | 'best-creative-direction'
    | 'best-line'
    | 'overall-trend'
    | 'recommendation'
    | 'risk';
  title: string;
  tone: 'negative' | 'neutral' | 'positive';
}

/**
 * Formal reporting facts that the backend must supply together with metrics.
 * Mock data intentionally omits this field rather than claiming production
 * authority.
 */
export interface ProjectComparisonSourceAuthority {
  attributionWindow: string;
  currency: string;
  financialLedgerVersion: string;
  timezone: string;
}

export interface ProjectComparisonDataQuality {
  asOf: string;
  authority?: ProjectComparisonSourceAuthority;
  comparisonCoverage: number;
  currentCoverage: number;
  messages: string[];
}

export interface ProjectComparisonOverview {
  agencyLines: ProjectComparisonAgencyLine[];
  alerts: ProjectComparisonAlert[];
  creativeDirections: ProjectComparisonCreativeDirection[];
  dataQuality: ProjectComparisonDataQuality;
  insights: ProjectComparisonInsight[];
  metrics: ProjectComparisonMetric[];
  project: ProjectSummary;
  query: ProjectComparisonQuery;
  trends: Partial<
    Record<ProjectComparisonMetricKey, ProjectComparisonTrendPoint[]>
  >;
}

/** Internal adapter record. It remains deliberately separate from page types. */
export interface ProjectComparisonSourceRecord {
  agencyLineId: string;
  clicks: number;
  day: string;
  firstPurchaseRevenue: number;
  firstPurchases: number;
  hour: number;
  impressions: number;
  projectCost: number;
  registrations: number;
  spend: number;
}

export interface ProjectComparisonCreativeDirectionSourceRecord
  extends ProjectComparisonSourceRecord {
  creativeDirectionId: string;
}

export interface ProjectComparisonAgencyLineSource {
  id: string;
  name: string;
  platform: string;
}

export interface ProjectComparisonCreativeDirectionSource {
  agencyLineId: string;
  assetType: 'image' | 'text' | 'video';
  id: string;
  materialVersionIds: string[];
  name: string;
  platform: string;
}

export interface ProjectComparisonSourceData {
  agencyLines: ProjectComparisonAgencyLineSource[];
  asOf: string;
  authority?: ProjectComparisonSourceAuthority;
  creativeDirectionRecords?: ProjectComparisonCreativeDirectionSourceRecord[];
  creativeDirections?: ProjectComparisonCreativeDirectionSource[];
  records: ProjectComparisonSourceRecord[];
}

export interface ProjectComparisonProjectProvider {
  get(id: string): Promise<ProjectSummary>;
}
