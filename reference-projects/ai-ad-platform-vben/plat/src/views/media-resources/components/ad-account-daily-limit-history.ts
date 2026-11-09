import type {
  AdAccountDailyLimitChange,
  AdAccountDailyLimitChangeType,
} from '#/api';

import dayjs from 'dayjs';

export const DAILY_LIMIT_CHANGE_META: Record<
  AdAccountDailyLimitChangeType,
  { color?: string; label: string }
> = {
  CLEAR: { color: 'error', label: '清除限额' },
  DECREASE: { color: 'warning', label: '降低' },
  INCREASE: { color: 'processing', label: '提高' },
  SET: { label: '首次设置' },
};

/** 按事件记录时的账户币种展示日限额，并统一保留两位小数。 */
export function formatDailyLimit(
  value: null | number | undefined,
  currency?: string,
) {
  if (value === null || value === undefined) return '未设置';
  const amount = new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(value);
  return currency ? `${currency} ${amount}` : amount;
}

export function formatDailyLimitDateTime(value?: string) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—';
}

export function dailyLimitChangeLabel(change: AdAccountDailyLimitChange) {
  return DAILY_LIMIT_CHANGE_META[change.changeType]?.label ?? '限额变更';
}
