import type {
  ProjectComparisonAgencyLine,
  ProjectComparisonAlert,
  ProjectComparisonCreativeDirection,
  ProjectComparisonInsight,
  ProjectComparisonMetric,
} from './types';

function findMetric(metrics: readonly ProjectComparisonMetric[], key: string) {
  return metrics.find((metric) => metric.key === key);
}

function formatRate(value: null | number | undefined) {
  return value === null || value === undefined
    ? '无可比基线'
    : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

export function buildProjectComparisonInsights(
  metrics: readonly ProjectComparisonMetric[],
  agencyLines: readonly ProjectComparisonAgencyLine[],
  creativeDirections: readonly ProjectComparisonCreativeDirection[],
  alerts: readonly ProjectComparisonAlert[],
): ProjectComparisonInsight[] {
  const roas = findMetric(metrics, 'roas');
  const profit = findMetric(metrics, 'projectProfit');
  const bestLine = [...agencyLines].sort(
    (left, right) => (right.current.roas ?? 0) - (left.current.roas ?? 0),
  )[0];
  const bestCreativeDirection = [...creativeDirections].sort(
    (left, right) => (right.current.roas ?? 0) - (left.current.roas ?? 0),
  )[0];
  const firstRisk = alerts[0];
  let trendTone: ProjectComparisonInsight['tone'] = 'neutral';
  if (roas?.assessment === 'good') trendTone = 'positive';
  if (roas?.assessment === 'bad') trendTone = 'negative';

  return [
    {
      body: `ROAS 环比 ${formatRate(roas?.changeRate)}，项目利润环比 ${formatRate(profit?.changeRate)}。`,
      id: 'overall-trend',
      title: '整体趋势',
      tone: trendTone,
    },
    {
      body: bestLine
        ? `${bestLine.name} 当前 ROAS ${(bestLine.current.roas ?? 0).toFixed(2)}，在已纳入的代理线中表现最佳。`
        : '当前筛选范围暂无可排名的代理线。',
      id: 'best-line',
      title: '最佳代理线',
      tone: bestLine ? 'positive' : 'neutral',
    },
    {
      body: bestCreativeDirection
        ? `${bestCreativeDirection.name} 当前 ROAS ${(bestCreativeDirection.current.roas ?? 0).toFixed(2)}，在已纳入的素材方向中表现最佳。`
        : '当前筛选范围暂无已接入的素材方向数据。',
      id: 'best-creative-direction',
      title: '最佳素材方向',
      tone: bestCreativeDirection ? 'positive' : 'neutral',
    },
    {
      body: firstRisk
        ? firstRisk.message
        : '未命中高风险阈值，仍建议结合素材与受众变化复核。',
      id: 'risk',
      title: '风险提示',
      tone: firstRisk ? 'negative' : 'neutral',
    },
    {
      body: firstRisk
        ? `建议优先检查${firstRisk.agencyLineName ? `${firstRisk.agencyLineName}的` : ''}${firstRisk.title}原因，并保留基线作为对照。`
        : '建议放大最佳代理线的有效组合，同时保持小预算对照实验。',
      id: 'recommendation',
      title: '建议动作',
      tone: firstRisk ? 'neutral' : 'positive',
    },
  ];
}
