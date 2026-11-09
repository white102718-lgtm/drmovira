import type {
  ProjectComparisonAgencyLine,
  ProjectComparisonAlert,
  ProjectComparisonMetric,
} from './types';

import { projectComparisonMetricConfigByKey } from './metric-config';

const riskRules = [
  {
    direction: 'decrease' as const,
    key: 'roas' as const,
    threshold: 0.15,
    title: 'ROAS 明显下滑',
  },
  {
    direction: 'increase' as const,
    key: 'registrationCost' as const,
    threshold: 0.2,
    title: '注册成本上升',
  },
  {
    direction: 'increase' as const,
    key: 'firstPurchaseCost' as const,
    threshold: 0.2,
    title: '首充成本上升',
  },
  {
    direction: 'decrease' as const,
    key: 'projectProfit' as const,
    threshold: 0.2,
    title: '项目利润下滑',
  },
] as const;

function shouldAlert(
  metric: ProjectComparisonMetric,
  rule: (typeof riskRules)[number],
) {
  return (
    metric.status === 'valid' &&
    metric.changeRate !== null &&
    metric.current !== null &&
    metric.comparison !== null &&
    metric.comparison > 1 &&
    (rule.direction === 'increase'
      ? metric.changeRate >= rule.threshold
      : metric.changeRate <= -rule.threshold)
  );
}

function metricAlert(
  metric: ProjectComparisonMetric,
  title: string,
  line?: ProjectComparisonAgencyLine,
): ProjectComparisonAlert | undefined {
  const rule = riskRules.find((item) => item.key === metric.key);
  if (!rule || !shouldAlert(metric, rule)) return undefined;
  const label =
    projectComparisonMetricConfigByKey.get(metric.key)?.label ?? metric.key;
  const change = `${Math.abs((metric.changeRate ?? 0) * 100).toFixed(1)}%`;
  return {
    ...(line
      ? { agencyLineId: line.agencyLineId, agencyLineName: line.name }
      : {}),
    current: metric.current ?? 0,
    key: metric.key,
    level:
      metric.changeRate !== null &&
      (rule.direction === 'increase'
        ? metric.changeRate >= rule.threshold * 1.6
        : metric.changeRate <= -rule.threshold * 1.6)
        ? 'critical'
        : 'warning',
    message: `${line ? `${line.name}的` : ''}${label}较对比期${change}。`,
    title,
  };
}

export function evaluateProjectComparisonAlerts(
  projectMetrics: readonly ProjectComparisonMetric[],
  agencyLines: readonly ProjectComparisonAgencyLine[],
): ProjectComparisonAlert[] {
  const alerts: ProjectComparisonAlert[] = [];
  for (const metric of projectMetrics) {
    const rule = riskRules.find((item) => item.key === metric.key);
    if (!rule) continue;
    const alert = metricAlert(metric, rule.title);
    if (alert) alerts.push(alert);
  }
  for (const line of agencyLines) {
    for (const metric of Object.values(line.metrics)) {
      if (!metric) continue;
      const rule = riskRules.find((item) => item.key === metric.key);
      if (!rule) continue;
      const alert = metricAlert(metric, rule.title, line);
      if (alert) alerts.push(alert);
    }
  }
  return alerts.sort((left, right) => {
    if (left.level === right.level)
      return left.title.localeCompare(right.title);
    return left.level === 'critical' ? -1 : 1;
  });
}
