import type { AdOperateProgress, AdOperateStatusMap } from '#/api/dashboard';

import type { AdDashboardCategory, AdDashboardRow } from './types';

import dayjs from 'dayjs';

export type DashboardOperationLevel = 'ad' | 'adset' | 'campaign';
export type DashboardConfiguredStatus = 'ACTIVE' | 'PAUSED';
export type DashboardOperationSnapshot = AdOperateStatusMap[string];

export interface PendingDashboardStatusChange {
  after: DashboardConfiguredStatus;
  before: DashboardConfiguredStatus;
  category: AdDashboardCategory;
  endDate: string;
  error?: string;
  id: string;
  key: string;
  level: DashboardOperationLevel;
  name: string;
  row: AdDashboardRow;
  startDate: string;
}

/** 固定用层级和对象 ID 隔离操作，切换页签后不能把别的层级状态覆盖过来。 */
export function dashboardOperationKey(
  level: DashboardOperationLevel,
  id: string,
) {
  return `${level}:${id}`;
}

export function dashboardOperationLevel(category: AdDashboardCategory) {
  const levels: Partial<Record<AdDashboardCategory, DashboardOperationLevel>> =
    {
      campaign: 'campaign',
      adSet: 'adset',
      ad: 'ad',
    };
  return levels[category];
}

export function isDashboardConfiguredStatus(
  status: unknown,
): status is DashboardConfiguredStatus {
  return status === 'ACTIVE' || status === 'PAUSED';
}

export function isDashboardOperationRunning(status?: string) {
  return ['PENDING', 'RETRY', 'SENDING', 'STARTED'].includes(status ?? '');
}

/** 只比较最新的开/关操作，历史失败不能盖过后续成功的指令。 */
export function latestDashboardToggle(snapshot?: DashboardOperationSnapshot) {
  return [snapshot?.start, snapshot?.pause]
    .filter((item): item is AdOperateProgress => Boolean(item))
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))[0];
}

/** 沿用旧面板：所选日期完整落在昨日到明日内才允许操作。 */
export function canOperateDashboardDates(startDate: string, endDate: string) {
  const today = dayjs.tz();
  return Boolean(
    startDate &&
      endDate &&
      startDate <= endDate &&
      startDate >= today.subtract(1, 'day').format('YYYY-MM-DD') &&
      endDate <= today.add(1, 'day').format('YYYY-MM-DD'),
  );
}

export function dashboardOperationDisabledReason(row: AdDashboardRow) {
  if (String(row.accountStatus) === '2') return '账户已停用，无法操作';
  if (row.configuredStatus === 'DELETED') return '已删除，无法操作';
  if (!isDashboardConfiguredStatus(row.configuredStatus))
    return '当前对象状态不支持开启或暂停';
  return '';
}
