import type { PersonnelDashboardField, PersonnelDashboardValue } from './types';

const numberFormatter = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 2,
});
const currencyFormatter = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const percentFormatter = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
  style: 'percent',
});

export function formatPersonnelDashboardValue(
  value: PersonnelDashboardValue | undefined,
  field: PersonnelDashboardField,
  currency = 'USD',
) {
  if (value === null || value === undefined || value === '') {
    return field.emptyText;
  }
  if (typeof value !== 'number') return value;
  if (field.dataType === 'percent') return percentFormatter.format(value);
  if (field.dataType === 'currency') {
    return `${currency} ${currencyFormatter.format(value)}`;
  }
  return numberFormatter.format(value);
}
