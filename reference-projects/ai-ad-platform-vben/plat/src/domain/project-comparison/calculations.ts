import type {
  ComparisonDirection,
  ProjectComparisonMetric,
  ProjectComparisonMetricKey,
  ProjectComparisonMetricValues,
  ProjectComparisonSourceRecord,
} from './types';

import {
  getMetricAssessment,
  projectComparisonMetricConfigByKey,
  projectComparisonMetricConfigs,
} from './metric-config';

const EPSILON = 0.000_001;

function sum(
  records: readonly ProjectComparisonSourceRecord[],
  key: keyof ProjectComparisonSourceRecord,
) {
  return records.reduce((total, record) => total + Number(record[key] ?? 0), 0);
}

export function calculateMetricValues(
  records: readonly ProjectComparisonSourceRecord[],
  serviceFeePercent: number,
): ProjectComparisonMetricValues {
  const spend = sum(records, 'spend');
  const impressions = sum(records, 'impressions');
  const clicks = sum(records, 'clicks');
  const registrations = sum(records, 'registrations');
  const firstPurchases = sum(records, 'firstPurchases');
  const firstPurchaseRevenue = sum(records, 'firstPurchaseRevenue');
  const projectCost = sum(records, 'projectCost');
  const serviceFeeRevenue = spend * (serviceFeePercent / 100);
  const projectProfit = serviceFeeRevenue - projectCost;

  return {
    clicks,
    ctr: impressions > 0 ? clicks / impressions : 0,
    firstPurchaseCost: firstPurchases > 0 ? spend / firstPurchases : 0,
    firstPurchases,
    impressions,
    profitMargin: serviceFeeRevenue > 0 ? projectProfit / serviceFeeRevenue : 0,
    projectCost,
    projectProfit,
    registrations,
    registrationCost: registrations > 0 ? spend / registrations : 0,
    roas: spend > 0 ? firstPurchaseRevenue / spend : 0,
    serviceFeeRevenue,
    spend,
  };
}

function resolveDirection(difference: number): ComparisonDirection {
  if (Math.abs(difference) < EPSILON) return 'flat';
  return difference > 0 ? 'up' : 'down';
}

/**
 * Handles the zero baseline explicitly: never surface Infinity or a fabricated
 * percentage. A new non-zero value is a useful event, not a 100% change.
 */
export function calculateComparisonMetric(
  key: ProjectComparisonMetricKey,
  current: null | number,
  comparison: null | number,
): ProjectComparisonMetric {
  const config = projectComparisonMetricConfigByKey.get(key);
  if (!config) throw new Error(`未知环比指标：${key}`);
  if (current === null || comparison === null) {
    return {
      assessment: 'unknown',
      changeRate: null,
      comparison,
      current,
      difference: null,
      direction: 'flat',
      key,
      status: 'missing',
    };
  }
  if (Math.abs(comparison) < EPSILON && Math.abs(current) >= EPSILON) {
    return {
      assessment: 'unknown',
      changeRate: null,
      comparison,
      current,
      difference: current,
      direction: 'new',
      key,
      status: 'new',
    };
  }
  if (Math.abs(comparison) < EPSILON) {
    return {
      assessment: 'neutral',
      changeRate: 0,
      comparison,
      current,
      difference: current,
      direction: 'flat',
      key,
      status: 'no-base',
    };
  }
  const difference = current - comparison;
  const direction = resolveDirection(difference);
  return {
    assessment: getMetricAssessment(config, direction),
    changeRate: difference / Math.abs(comparison),
    comparison,
    current,
    difference,
    direction,
    key,
    status: 'valid',
  };
}

export function calculateComparisonMetrics(
  current: ProjectComparisonMetricValues,
  comparison: ProjectComparisonMetricValues,
): ProjectComparisonMetric[] {
  return projectComparisonMetricConfigs.map(({ key }) =>
    calculateComparisonMetric(
      key,
      current[key] ?? null,
      comparison[key] ?? null,
    ),
  );
}
