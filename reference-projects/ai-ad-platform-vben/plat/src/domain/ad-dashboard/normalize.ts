import type {
  AdDashboardField,
  AdDashboardRow,
  AdDashboardSchema,
  AdDashboardSummaryRow,
  AdDashboardValue,
} from './types';

import { formatAdDashboardStatus } from './status';

const legacySourceAliases: Record<string, string[]> = {
  ECPM: ['CPM', 'cpm', '千展', '千展成本'],
  '点击成本 CPC': ['点击成本'],
  '点击率 CTR': ['点击率'],
  购物roas: ['购物ROAS'],
  订阅价值: ['订单价值'],
  订阅成本: ['订单成本'],
  订阅数: ['订单数'],
  订阅率: ['订单率'],
};

/** 广告面板与人员面板共用账户状态文案；缺失保留空值，未知状态保留原值。 */
export function formatAccountStatus(status?: null | number | string) {
  return formatAdDashboardStatus('account', status);
}

function asNumber(value: AdDashboardValue | undefined) {
  return typeof value === 'number' ? value : null;
}

function divide(numerator: null | number, denominator: null | number) {
  return numerator !== null && denominator !== null && denominator > 0
    ? numerator / denominator
    : null;
}

/**
 * 统一广告面板末尾的效率指标：首充以现有的“购物数”作为首充事件口径。
 * 后端已提供同名指标时保留其值；缺失时再由基础漏斗数据推导。
 */
export function calculateAdDashboardEfficiencyMetrics(
  row: Record<string, AdDashboardValue>,
) {
  const spend = asNumber(row.spend);
  const impressions = asNumber(row.impressions);
  const clicks = asNumber(row.clicks);
  const registrations = asNumber(row.registrations);
  const purchases = asNumber(row.purchases);
  return {
    cpc: divide(spend, clicks),
    ctr: divide(clicks, impressions),
    ecpm: (() => {
      const cost = divide(spend, impressions);
      return cost === null ? null : cost * 1000;
    })(),
    firstPurchaseCost: divide(spend, purchases),
    firstPurchaseRate: divide(purchases, registrations),
    registrationCost: divide(spend, registrations),
    registrationRate: divide(registrations, clicks),
  };
}

function resolveSourceValue(
  source: Record<string, unknown>,
  field: AdDashboardField,
) {
  const keys = [
    field.sourceKey,
    field.key,
    ...(legacySourceAliases[field.sourceKey] ?? []),
  ];
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null) return value;
  }
  return null;
}

export function normalizeAdDashboardValue(
  value: unknown,
  field: AdDashboardField,
): AdDashboardValue {
  if (value === '' || value === null || value === undefined) return null;
  if (['identifier', 'status', 'text', 'url'].includes(field.dataType)) {
    return String(value);
  }
  if (field.dataType === 'datetime') return String(value);
  if (field.dataType === 'percent' && typeof value === 'string') {
    const parsed = Number(value.replace('%', '').replaceAll(',', ''));
    return Number.isFinite(parsed) ? parsed / 100 : null;
  }
  const parsed = Number(
    typeof value === 'string' ? value.replaceAll(',', '') : value,
  );
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizeAdDashboardRow(
  source: Record<string, unknown>,
  schema: AdDashboardSchema,
  index: number,
): AdDashboardRow {
  const row = Object.fromEntries(
    schema.fields.map((field) => [
      field.key,
      normalizeAdDashboardValue(resolveSourceValue(source, field), field),
    ]),
  ) as AdDashboardRow;
  if (
    ['department', 'project', 'agencyLine'].includes(schema.category) &&
    (source.id === null || source.id === 'null')
  ) {
    // 空部门、游戏平台和代理线仍是可下钻的分组。
    // 沿用旧接口的 null 字符串，让后端按对应字段 IS NULL 筛选。
    row.id = 'null';
    row.name ??= 'null';
  }
  if (
    ['account', 'campaign', 'adSet', 'ad', 'pixel'].includes(schema.category)
  ) {
    // 原始状态保留为行数据；主状态列与旧版、筛选器一致，展示实际投放状态。
    row.configuredStatus = source.status == null ? null : String(source.status);
    row.accountStatus =
      source.account_status == null ? null : String(source.account_status);
    row.effectiveStatus =
      source.effective_status == null ? null : String(source.effective_status);
    const status =
      schema.category === 'account'
        ? (row.accountStatus ?? row.effectiveStatus ?? row.statusText)
        : (row.effectiveStatus ?? row.statusText);
    row.statusText = formatAdDashboardStatus(schema.category, status);
  }
  const calculatedMetrics = calculateAdDashboardEfficiencyMetrics(row);
  for (const [key, value] of Object.entries(calculatedMetrics)) {
    if (row[key] === null) row[key] = value;
  }
  const id = String(row.id ?? source.id ?? `${schema.category}-${index + 1}`);
  return {
    ...row,
    // 操作列需要所属账户 ID，即使当前维度没有展示该字段（如广告组）。
    accountId: String(
      source['账户ID'] ?? source.accountId ?? source.account_id ?? '',
    ),
    currency: String(source.currency ?? source['币种'] ?? 'USD'),
    id,
    // 同一像素按广告展示多行，小时模式还有多个快照；筛选仍使用原始像素 ID。
    key:
      schema.category === 'pixel'
        ? JSON.stringify([id, source['广告ID'] ?? index, source['时间'] ?? ''])
        : id,
  };
}

export function summarizeAdDashboardRows(
  rows: AdDashboardRow[],
  schema: AdDashboardSchema,
): AdDashboardSummaryRow[] {
  const currencies = new Map<string, Record<string, number>>();
  for (const row of rows) {
    const values = currencies.get(row.currency) ?? {};
    for (const field of schema.fields) {
      if (!field.summarizable) continue;
      const value = row[field.key];
      if (typeof value === 'number') {
        values[field.key] = (values[field.key] ?? 0) + value;
      }
    }
    currencies.set(row.currency, values);
  }
  return [...currencies.entries()].map(([currency, values]) => ({
    currency,
    values: {
      ...values,
      ...calculateAdDashboardEfficiencyMetrics(values),
    },
  }));
}
