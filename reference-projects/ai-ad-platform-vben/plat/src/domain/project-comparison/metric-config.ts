import type { ComparisonAssessment, ProjectComparisonMetricKey } from './types';

export type ProjectComparisonMetricFormat =
  | 'count'
  | 'currency'
  | 'percent'
  | 'ratio';

export interface ProjectComparisonMetricConfig {
  format: ProjectComparisonMetricFormat;
  /** Financial metrics are deterministic demo projections until the formal ledger contract is connected. */
  isDemoProjection?: boolean;
  key: ProjectComparisonMetricKey;
  label: string;
  lowerIsBetter?: boolean;
  neutral?: boolean;
}

export const projectComparisonMetricConfigs: readonly ProjectComparisonMetricConfig[] =
  [
    { key: 'spend', label: '消耗', format: 'currency', neutral: true },
    { key: 'impressions', label: '展示', format: 'count', neutral: true },
    { key: 'clicks', label: '点击', format: 'count', neutral: true },
    { key: 'ctr', label: 'CTR', format: 'percent', neutral: true },
    { key: 'registrations', label: '注册数', format: 'count' },
    { key: 'firstPurchases', label: '首充数', format: 'count' },
    {
      key: 'registrationCost',
      label: '注册成本',
      format: 'currency',
      lowerIsBetter: true,
    },
    {
      key: 'firstPurchaseCost',
      label: '首充成本',
      format: 'currency',
      lowerIsBetter: true,
    },
    { key: 'roas', label: 'ROAS', format: 'ratio' },
    {
      key: 'serviceFeeRevenue',
      label: '服务费收入',
      format: 'currency',
      isDemoProjection: true,
    },
    {
      key: 'projectCost',
      label: '项目成本',
      format: 'currency',
      isDemoProjection: true,
      lowerIsBetter: true,
    },
    {
      key: 'projectProfit',
      label: '项目利润',
      format: 'currency',
      isDemoProjection: true,
    },
    {
      key: 'profitMargin',
      label: '利润率',
      format: 'percent',
      isDemoProjection: true,
    },
  ];

export const projectComparisonMetricConfigByKey = new Map(
  projectComparisonMetricConfigs.map((config) => [config.key, config]),
);

export function getMetricAssessment(
  config: ProjectComparisonMetricConfig,
  direction: 'down' | 'flat' | 'new' | 'up',
): ComparisonAssessment {
  if (direction === 'new') return 'unknown';
  if (config.neutral || direction === 'flat') return 'neutral';
  const isPositive = config.lowerIsBetter
    ? direction === 'down'
    : direction === 'up';
  return isPositive ? 'good' : 'bad';
}
