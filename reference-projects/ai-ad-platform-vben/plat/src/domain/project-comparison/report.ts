import type {
  ProjectComparisonAlert,
  ProjectComparisonMetric,
  ProjectComparisonMetricKey,
  ProjectComparisonOverview,
} from './types';

import { projectComparisonMetricConfigByKey } from './metric-config';

export interface ProjectComparisonReviewSection {
  body: string;
  id:
    | 'creative-direction-performance'
    | 'data-quality'
    | 'line-performance'
    | 'overall'
    | 'risk-action';
  title: string;
}

/**
 * A review draft is deliberately ephemeral. It is a presentation of the
 * current read-model snapshot, not an approved report or a persisted record.
 */
export interface ProjectComparisonReviewDraft {
  comparisonPeriodLabel: string;
  currentPeriodLabel: string;
  generatedAt: string;
  markdown: string;
  projectId: string;
  projectName: string;
  sections: ProjectComparisonReviewSection[];
  title: string;
}

function formatNumber(value: null | number, digits = 0) {
  if (value === null || Number.isNaN(value)) return '—';
  return value.toLocaleString('zh-CN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatMetric(
  overview: ProjectComparisonOverview,
  key: ProjectComparisonMetricKey,
  value: null | number,
) {
  const config = projectComparisonMetricConfigByKey.get(key);
  if (!config || value === null || Number.isNaN(value)) return '—';
  if (config.format === 'currency') {
    return `${overview.project.currency} ${formatNumber(value, 2)}`;
  }
  if (config.format === 'percent') return `${formatNumber(value * 100, 2)}%`;
  if (config.format === 'ratio') return `${formatNumber(value, 2)}x`;
  return formatNumber(value);
}

function formatChange(metric: ProjectComparisonMetric) {
  if (metric.status === 'new') return '新增基线';
  if (metric.status === 'missing') return '数据缺失';
  if (metric.changeRate === null) return '无可比基数';
  return `${metric.changeRate >= 0 ? '+' : ''}${(metric.changeRate * 100).toFixed(1)}%`;
}

function periodLabel(startDate: string, endDate: string) {
  return startDate === endDate ? startDate : `${startDate} 至 ${endDate}`;
}

function metricOf(
  overview: ProjectComparisonOverview,
  key: ProjectComparisonMetricKey,
) {
  return overview.metrics.find((metric) => metric.key === key);
}

function overallSection(overview: ProjectComparisonOverview) {
  const spend = metricOf(overview, 'spend');
  const registrations = metricOf(overview, 'registrations');
  const firstPurchases = metricOf(overview, 'firstPurchases');
  return {
    body: `广告消耗 ${formatMetric(overview, 'spend', spend?.current ?? null)}（环比 ${spend ? formatChange(spend) : '—'}）；注册量 ${formatMetric(overview, 'registrations', registrations?.current ?? null)}（环比 ${registrations ? formatChange(registrations) : '—'}）；首充人数 ${formatMetric(overview, 'firstPurchases', firstPurchases?.current ?? null)}（环比 ${firstPurchases ? formatChange(firstPurchases) : '—'}）。`,
    id: 'overall' as const,
    title: '整体表现',
  };
}

function linePerformanceSection(overview: ProjectComparisonOverview) {
  const bestLine = [...overview.agencyLines].sort(
    (left, right) => (right.current.roas ?? -1) - (left.current.roas ?? -1),
  )[0];
  if (!bestLine) {
    return {
      body: '当前筛选范围没有可用于排名的代理线数据。',
      id: 'line-performance' as const,
      title: '代理线表现',
    };
  }
  return {
    body: `当前按 ROAS 排名表现最佳的代理线为「${bestLine.name}」（${bestLine.platform}）：ROAS ${formatMetric(overview, 'roas', bestLine.current.roas ?? null)}，首充成本 ${formatMetric(overview, 'firstPurchaseCost', bestLine.current.firstPurchaseCost ?? null)}。`,
    id: 'line-performance' as const,
    title: '代理线表现',
  };
}

function creativeDirectionPerformanceSection(
  overview: ProjectComparisonOverview,
) {
  const bestDirection = [...overview.creativeDirections].sort(
    (left, right) => (right.current.roas ?? -1) - (left.current.roas ?? -1),
  )[0];
  if (!bestDirection) {
    return {
      body: '当前筛选范围暂无已接入的素材方向数据。',
      id: 'creative-direction-performance' as const,
      title: '素材方向表现',
    };
  }
  return {
    body: `当前按 ROAS 排名表现最佳的素材方向为「${bestDirection.name}」（${bestDirection.materialVersionCount} 个素材版本）：ROAS ${formatMetric(overview, 'roas', bestDirection.current.roas ?? null)}，首充成本 ${formatMetric(overview, 'firstPurchaseCost', bestDirection.current.firstPurchaseCost ?? null)}。`,
    id: 'creative-direction-performance' as const,
    title: '素材方向表现',
  };
}

function alertSummary(alerts: readonly ProjectComparisonAlert[]) {
  if (alerts.length === 0)
    return '当前范围未命中预设风险阈值，仍建议结合素材、账户和归因窗口进行人工复核。';
  return alerts
    .map(
      (alert) =>
        `${alert.level === 'critical' ? '严重' : '关注'}：${alert.message}`,
    )
    .join('；');
}

function riskActionSection(overview: ProjectComparisonOverview) {
  const recommendations = overview.insights
    .filter(
      (insight) => insight.id === 'recommendation' || insight.id === 'risk',
    )
    .map((insight) => insight.body);
  return {
    body: `${alertSummary(overview.alerts)}${recommendations.length > 0 ? ` 建议：${recommendations.join('；')}` : ''}`,
    id: 'risk-action' as const,
    title: '风险与建议',
  };
}

function dataQualitySection(overview: ProjectComparisonOverview) {
  const quality = overview.dataQuality;
  const notes =
    quality.messages.length > 0
      ? quality.messages.join(' ')
      : '当前查询窗口完整，指标按项目币种和选定范围聚合。';
  return {
    body: `数据截至 ${quality.asOf}；当前周期覆盖 ${(quality.currentCoverage * 100).toFixed(0)}%，对比周期覆盖 ${(quality.comparisonCoverage * 100).toFixed(0)}%。${notes} 财务指标仍是演示投影，正式报告必须以服务端确认的账本、时区和归因口径为准。`,
    id: 'data-quality' as const,
    title: '数据口径与校对',
  };
}

export function buildProjectComparisonReviewDraft(
  overview: ProjectComparisonOverview,
): ProjectComparisonReviewDraft {
  const currentPeriodLabel = periodLabel(
    overview.query.current.startDate,
    overview.query.current.endDate,
  );
  const comparisonPeriodLabel = periodLabel(
    overview.query.comparison.startDate,
    overview.query.comparison.endDate,
  );
  const title = `${overview.project.name} · 项目复盘草稿`;
  const sections = [
    overallSection(overview),
    linePerformanceSection(overview),
    creativeDirectionPerformanceSection(overview),
    riskActionSection(overview),
    dataQualitySection(overview),
  ];
  const markdown = [
    `# ${title}`,
    '',
    `- 当前周期：${currentPeriodLabel}`,
    `- 对比周期：${comparisonPeriodLabel}`,
    `- 数据截至：${overview.dataQuality.asOf}`,
    '- 生成方式：规则型草稿，需人工校对后使用。',
    '',
    ...sections.flatMap((section) => [
      `## ${section.title}`,
      '',
      section.body,
      '',
    ]),
  ].join('\n');

  return {
    comparisonPeriodLabel,
    currentPeriodLabel,
    generatedAt: overview.dataQuality.asOf,
    markdown,
    projectId: overview.project.id,
    projectName: overview.project.name,
    sections,
    title,
  };
}
