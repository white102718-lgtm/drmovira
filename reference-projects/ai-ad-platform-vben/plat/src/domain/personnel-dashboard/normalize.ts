import type {
  PersonnelDashboardField,
  PersonnelDashboardRow,
  PersonnelDashboardSchema,
  PersonnelDashboardSummaryRow,
  PersonnelDashboardValue,
} from './types';

const legacySourceAliases: Record<string, string[]> = {
  名称: ['name', '投手', 'personnel_name'],
  状态: ['status'],
  最新时间: ['updatedAt', 'updated_at'],
  购物roas: ['购物ROAS', 'purchase_roas'],
  '1d购物roas': ['1d购物ROAS', 'purchase_roas_1d'],
  订阅价值: ['订单价值'],
  '1d订阅价值': ['1d订单价值'],
  订阅成本: ['订单成本'],
  '1d订阅成本': ['1d订单成本'],
  订阅数: ['订单数'],
  '1d订阅数': ['1d订单数'],
  订阅率: ['订单率'],
};

function resolveSourceValue(
  source: Record<string, unknown>,
  field: PersonnelDashboardField,
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

function excelSerialToIso(value: number) {
  const milliseconds = Math.round((value - 25_569) * 86_400_000);
  const date = new Date(milliseconds);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 16).replace('T', ' ');
}

export function normalizePersonnelDashboardValue(
  value: unknown,
  field: PersonnelDashboardField,
): PersonnelDashboardValue {
  if (value === '' || value === null || value === undefined) return null;
  if (['status', 'text'].includes(field.dataType)) return String(value);
  if (field.dataType === 'datetime') {
    if (typeof value === 'number') return excelSerialToIso(value);
    return String(value);
  }
  if (field.dataType === 'percent' && typeof value === 'string') {
    const parsed = Number(value.replace('%', '').replaceAll(',', ''));
    return Number.isFinite(parsed) ? parsed / 100 : null;
  }
  const parsed = Number(
    typeof value === 'string' ? value.replaceAll(',', '') : value,
  );
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizePersonnelDashboardRow(
  source: Record<string, unknown>,
  schema: PersonnelDashboardSchema,
  index: number,
): PersonnelDashboardRow {
  const values = Object.fromEntries(
    schema.fields.map((field) => [
      field.key,
      normalizePersonnelDashboardValue(
        resolveSourceValue(source, field),
        field,
      ),
    ]),
  );
  const id = String(
    source.id ?? source._id ?? values.name ?? `${schema.category}-${index + 1}`,
  );
  return {
    ...values,
    currency: String(source.currency ?? source['币种'] ?? 'USD'),
    departmentId: String(
      source.departmentId ?? source.department_id ?? source['部门ID'] ?? '',
    ),
    departmentName: String(
      source.departmentName ?? source.department ?? source['部门'] ?? '',
    ),
    id,
    key: id,
  };
}

export function summarizePersonnelDashboardRows(
  rows: PersonnelDashboardRow[],
  schema: PersonnelDashboardSchema,
): PersonnelDashboardSummaryRow[] {
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
    values,
  }));
}
