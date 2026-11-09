import type { ProjectComparisonAdapter } from './adapter';
import type {
  ComparisonPeriod,
  ComparisonPeriodMode,
  ProjectComparisonAgencyLine,
  ProjectComparisonCreativeDirection,
  ProjectComparisonDataQuality,
  ProjectComparisonMetricKey,
  ProjectComparisonOverview,
  ProjectComparisonProjectProvider,
  ProjectComparisonQuery,
  ProjectComparisonSourceData,
  ProjectComparisonSourceRecord,
  ProjectComparisonTrendPoint,
} from './types';

import { evaluateProjectComparisonAlerts } from './alert-rules';
import {
  calculateComparisonMetrics,
  calculateMetricValues,
} from './calculations';
import { buildProjectComparisonInsights } from './insight-rules';
import { projectComparisonMetricConfigs } from './metric-config';

const DAY_IN_MS = 86_400_000;

function asDate(day: string) {
  const parsed = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime()))
    throw new Error('日期格式应为 YYYY-MM-DD');
  return parsed;
}

function dateKey(date: Date) {
  return date.toISOString().slice(0, 10);
}

function addDays(day: string, amount: number) {
  const date = asDate(day);
  date.setUTCDate(date.getUTCDate() + amount);
  return dateKey(date);
}

function daysBetween(period: ComparisonPeriod) {
  return (
    Math.floor(
      (asDate(period.endDate).getTime() - asDate(period.startDate).getTime()) /
        DAY_IN_MS,
    ) + 1
  );
}

function dayIncludes(period: ComparisonPeriod, day: string) {
  return day >= period.startDate && day <= period.endDate;
}

function asOfParts(asOf: string) {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):/.exec(asOf);
  const day = match?.[1];
  const hour = match?.[2];
  if (!day || !hour) throw new Error('演示数据截止时间格式不正确');
  return { day, hour: Number(hour) };
}

function bucketOf(
  record: ProjectComparisonSourceRecord,
  granularity: 'day' | 'hour',
) {
  return granularity === 'hour'
    ? `${record.day} ${String(record.hour).padStart(2, '0')}:00`
    : record.day;
}

function sumRecords(records: readonly ProjectComparisonSourceRecord[]) {
  const byBucket = new Map<string, ProjectComparisonSourceRecord[]>();
  for (const record of records) {
    const key = record.agencyLineId;
    const current = byBucket.get(key) ?? [];
    current.push(record);
    byBucket.set(key, current);
  }
  return byBucket;
}

function metricByKey<T extends { key: ProjectComparisonMetricKey }>(
  metrics: readonly T[],
) {
  return Object.fromEntries(
    metrics.map((metric) => [metric.key, metric]),
  ) as Record<ProjectComparisonMetricKey, T>;
}

function filterPeriodRecords<T extends ProjectComparisonSourceRecord>(
  records: readonly T[],
  period: ComparisonPeriod,
  asOf: { day: string; hour: number },
  mode: ComparisonPeriodMode,
  isCurrent: boolean,
): T[] {
  if (!isCurrent && mode !== 'custom') {
    const currentDays = Math.max(
      1,
      Math.floor(
        (asDate(asOf.day).getTime() - asDate(period.startDate).getTime()) /
          DAY_IN_MS,
      ) + 1,
    );
    const comparisonEnd = addDays(
      period.startDate,
      Math.min(daysBetween(period), currentDays) - 1,
    );
    return records.filter(
      (record) =>
        dayIncludes({ ...period, endDate: comparisonEnd }, record.day) &&
        !(record.day === comparisonEnd && record.hour >= asOf.hour),
    );
  }
  return records.filter((record) => {
    if (!dayIncludes(period, record.day)) return false;
    if (isCurrent && record.day === asOf.day && record.hour >= asOf.hour)
      return false;
    return isCurrent ? record.day <= asOf.day : true;
  });
}

function groupByKey<T>(items: readonly T[], getKey: (item: T) => string) {
  const result = new Map<string, T[]>();
  for (const item of items) {
    const key = getKey(item);
    const grouped = result.get(key) ?? [];
    grouped.push(item);
    result.set(key, grouped);
  }
  return result;
}

function buildTrend(
  currentRecords: readonly ProjectComparisonSourceRecord[],
  comparisonRecords: readonly ProjectComparisonSourceRecord[],
  metric: ProjectComparisonMetricKey,
  serviceFeePercent: number,
  granularity: 'day' | 'hour',
): ProjectComparisonTrendPoint[] {
  const currentByBucket = new Map<string, ProjectComparisonSourceRecord[]>();
  const comparisonByBucket = new Map<string, ProjectComparisonSourceRecord[]>();
  for (const record of currentRecords) {
    const bucket = bucketOf(record, granularity);
    const items = currentByBucket.get(bucket) ?? [];
    items.push(record);
    currentByBucket.set(bucket, items);
  }
  for (const record of comparisonRecords) {
    const bucket = bucketOf(record, granularity);
    const items = comparisonByBucket.get(bucket) ?? [];
    items.push(record);
    comparisonByBucket.set(bucket, items);
  }
  const currentBuckets = [...currentByBucket.keys()].sort();
  const comparisonBuckets = [...comparisonByBucket.keys()].sort();
  const length = Math.max(currentBuckets.length, comparisonBuckets.length);
  return Array.from({ length }, (_, index) => {
    const currentBucket = currentBuckets[index] ?? '';
    const comparisonBucket = comparisonBuckets[index] ?? '';
    return {
      bucket: currentBucket,
      comparison: comparisonBucket
        ? (calculateMetricValues(
            comparisonByBucket.get(comparisonBucket) ?? [],
            serviceFeePercent,
          )[metric] ?? null)
        : null,
      comparisonBucket,
      current: currentBucket
        ? (calculateMetricValues(
            currentByBucket.get(currentBucket) ?? [],
            serviceFeePercent,
          )[metric] ?? null)
        : null,
    };
  });
}

function buildDataQuality(
  query: ProjectComparisonQuery,
  source: ProjectComparisonSourceData,
  currentRecords: readonly ProjectComparisonSourceRecord[],
  comparisonRecords: readonly ProjectComparisonSourceRecord[],
): ProjectComparisonDataQuality {
  const asOf = asOfParts(source.asOf);
  const requestedCurrentHours = daysBetween(query.current) * 24;
  const requestedComparisonHours = daysBetween(query.comparison) * 24;
  const lineCount = Math.max(1, source.agencyLines.length);
  const messages: string[] = [];
  if (
    query.mode === 'custom' &&
    requestedCurrentHours !== requestedComparisonHours
  ) {
    messages.push('自定义对比区间长度不同，请结合总量和日均值解读。');
  }
  if (query.current.endDate >= asOf.day) {
    messages.push(
      `当前周期数据截至 ${source.asOf}，当天按相同时间进度与对比期对齐。`,
    );
  }
  return {
    ...(source.authority ? { authority: source.authority } : {}),
    asOf: source.asOf,
    comparisonCoverage: Math.min(
      1,
      comparisonRecords.length / (requestedComparisonHours * lineCount),
    ),
    currentCoverage: Math.min(
      1,
      currentRecords.length / (requestedCurrentHours * lineCount),
    ),
    messages,
  };
}

export class ProjectComparisonService {
  constructor(
    private readonly adapter: ProjectComparisonAdapter,
    private readonly projects: ProjectComparisonProjectProvider,
  ) {}

  getDefaultQuery(
    projectId: string,
    mode: ComparisonPeriodMode = 'today',
  ): ProjectComparisonQuery {
    const current =
      mode === 'last-7-days'
        ? { endDate: '2026-08-14', startDate: '2026-08-08' }
        : { endDate: '2026-08-14', startDate: '2026-08-14' };
    const comparison =
      mode === 'last-7-days'
        ? { endDate: '2026-08-07', startDate: '2026-08-01' }
        : { endDate: '2026-08-13', startDate: '2026-08-13' };
    return {
      comparison,
      current,
      granularity: mode === 'today' ? 'hour' : 'day',
      mode,
      projectId,
    };
  }

  async getOverview(
    query: ProjectComparisonQuery,
  ): Promise<ProjectComparisonOverview> {
    this.validateQuery(query);
    const [project, source] = await Promise.all([
      this.projects.get(query.projectId),
      this.adapter.getSourceData(query),
    ]);
    const asOf = asOfParts(source.asOf);
    const currentRecords = filterPeriodRecords(
      source.records,
      query.current,
      asOf,
      query.mode,
      true,
    );
    const comparisonRecords = filterPeriodRecords(
      source.records,
      query.comparison,
      asOf,
      query.mode,
      false,
    );
    const serviceFeePercent = project.serviceFeePercent ?? 10;
    const current = calculateMetricValues(currentRecords, serviceFeePercent);
    const comparison = calculateMetricValues(
      comparisonRecords,
      serviceFeePercent,
    );
    const metrics = calculateComparisonMetrics(current, comparison);
    const currentByLine = sumRecords(currentRecords);
    const comparisonByLine = sumRecords(comparisonRecords);
    const agencyLines: ProjectComparisonAgencyLine[] = source.agencyLines.map(
      (line) => {
        const currentValues = calculateMetricValues(
          currentByLine.get(line.id) ?? [],
          serviceFeePercent,
        );
        const comparisonValues = calculateMetricValues(
          comparisonByLine.get(line.id) ?? [],
          serviceFeePercent,
        );
        return {
          agencyLineId: line.id,
          current: currentValues,
          metrics: metricByKey(
            calculateComparisonMetrics(currentValues, comparisonValues),
          ),
          name: line.name,
          platform: line.platform,
        };
      },
    );
    const currentCreativeDirectionRecords = filterPeriodRecords(
      source.creativeDirectionRecords ?? [],
      query.current,
      asOf,
      query.mode,
      true,
    );
    const comparisonCreativeDirectionRecords = filterPeriodRecords(
      source.creativeDirectionRecords ?? [],
      query.comparison,
      asOf,
      query.mode,
      false,
    );
    const agencyLineNames = new Map(
      source.agencyLines.map((line) => [line.id, line.name]),
    );
    const currentByCreativeDirection = groupByKey(
      currentCreativeDirectionRecords,
      (record) => record.creativeDirectionId,
    );
    const comparisonByCreativeDirection = groupByKey(
      comparisonCreativeDirectionRecords,
      (record) => record.creativeDirectionId,
    );
    const creativeDirections: ProjectComparisonCreativeDirection[] = (
      source.creativeDirections ?? []
    ).map((direction) => {
      const currentValues = calculateMetricValues(
        currentByCreativeDirection.get(direction.id) ?? [],
        serviceFeePercent,
      );
      const comparisonValues = calculateMetricValues(
        comparisonByCreativeDirection.get(direction.id) ?? [],
        serviceFeePercent,
      );
      return {
        agencyLineId: direction.agencyLineId,
        agencyLineName:
          agencyLineNames.get(direction.agencyLineId) ?? '未知代理线',
        assetType: direction.assetType,
        creativeDirectionId: direction.id,
        current: currentValues,
        materialVersionCount: direction.materialVersionIds.length,
        metrics: metricByKey(
          calculateComparisonMetrics(currentValues, comparisonValues),
        ),
        name: direction.name,
        platform: direction.platform,
      };
    });
    const alerts = evaluateProjectComparisonAlerts(metrics, agencyLines);
    const trends = Object.fromEntries(
      projectComparisonMetricConfigs.map(({ key }) => [
        key,
        buildTrend(
          currentRecords,
          comparisonRecords,
          key,
          serviceFeePercent,
          query.granularity,
        ),
      ]),
    );

    return {
      agencyLines,
      alerts,
      dataQuality: buildDataQuality(
        query,
        source,
        currentRecords,
        comparisonRecords,
      ),
      creativeDirections,
      insights: buildProjectComparisonInsights(
        metrics,
        agencyLines,
        creativeDirections,
        alerts,
      ),
      metrics,
      project,
      query,
      trends,
    };
  }

  private validateQuery(query: ProjectComparisonQuery) {
    if (!query.projectId.trim()) throw new Error('请选择项目');
    for (const period of [query.current, query.comparison]) {
      if (
        asDate(period.startDate).getTime() > asDate(period.endDate).getTime()
      ) {
        throw new Error('开始日期不能晚于结束日期');
      }
    }
  }
}
