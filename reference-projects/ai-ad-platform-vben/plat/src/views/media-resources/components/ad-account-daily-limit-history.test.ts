import { describe, expect, it } from 'vitest';

import {
  dailyLimitChangeLabel,
  formatDailyLimit,
  formatDailyLimitDateTime,
} from './ad-account-daily-limit-history';

describe('广告账户日限额变更记录格式化', () => {
  it('按币种保留两位小数并处理未设置值', () => {
    expect(formatDailyLimit(1234.5, 'USD')).toBe('USD 1,234.50');
    expect(formatDailyLimit(null, 'USD')).toBe('未设置');
  });

  it('将时间展示为 GMT+8 页面统一格式', () => {
    expect(formatDailyLimitDateTime('2026-09-18T10:32:07')).toBe(
      '2026-09-18 10:32:07',
    );
    expect(formatDailyLimitDateTime()).toBe('—');
  });

  it.each([
    ['SET', '首次设置'],
    ['INCREASE', '提高'],
    ['DECREASE', '降低'],
    ['CLEAR', '清除限额'],
  ] as const)(
    '展示 %s 变化类型文本',
    (changeType: 'CLEAR' | 'DECREASE' | 'INCREASE' | 'SET', label: string) => {
      expect(
        dailyLimitChangeLabel({
          changeType,
          changedAt: '2026-09-18T10:32:07',
          currentLimit: 1000,
          id: changeType,
          previousLimit: 800,
          source: 'FACEBOOK',
        }),
      ).toBe(label);
    },
  );
});
