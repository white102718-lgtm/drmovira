import type { AdDashboardCategory } from './types';

// 沿用旧版面板的分层枚举：账户筛选 account_status，其他对象筛选 effective_status（后端 delivery_str）。
const accountStatusLabels: Record<string, string> = {
  1: '正常',
  2: '已停用',
  3: '账单未结清',
  7: '待风险审核',
  8: '待结算',
  9: '宽限期',
  100: '待关闭',
  101: '已关闭',
};

const campaignStatusLabels: Record<string, string> = {
  ACTIVE: '投放中',
  PAUSED: '已暂停',
  IN_PROCESS: '处理中',
  WITH_ISSUES: '有问题',
  ARCHIVED: '已归档',
  DELETED: '已删除',
};

const adSetStatusLabels: Record<string, string> = {
  ACTIVE: '投放中',
  PAUSED: '已暂停',
  CAMPAIGN_PAUSED: '系列暂停',
  IN_PROCESS: '处理中',
  WITH_ISSUES: '有问题',
  ARCHIVED: '已归档',
  DELETED: '已删除',
};

const adStatusLabels: Record<string, string> = {
  ACTIVE: '投放中',
  PAUSED: '已暂停',
  CAMPAIGN_PAUSED: '系列暂停',
  ADSET_PAUSED: '组暂停',
  IN_PROCESS: '处理中',
  WITH_ISSUES: '有问题',
  DISAPPROVED: '已拒绝',
  PENDING_REVIEW: '待审核',
  PENDING_BILLING_INFO: '待结算信息',
  PREAPPROVED: '预审通过',
  ARCHIVED: '已归档',
  DELETED: '已删除',
};

const statusLabelsByCategory: Partial<
  Record<AdDashboardCategory, Record<string, string>>
> = {
  account: accountStatusLabels,
  campaign: campaignStatusLabels,
  adSet: adSetStatusLabels,
  ad: adStatusLabels,
  // 像素按关联广告展示明细，沿用旧版广告状态枚举。
  pixel: adStatusLabels,
};

/** 返回当前维度的真实状态码；汇总维度没有状态筛选项。 */
export function getAdDashboardStatusOptions(category: AdDashboardCategory) {
  return Object.entries(statusLabelsByCategory[category] ?? {}).map(
    ([value, label]) => ({ label, value }),
  );
}

/** 展示与筛选共用分层枚举；缺失保留空值，未知状态保留原值。 */
export function formatAdDashboardStatus(
  category: AdDashboardCategory,
  status?: null | number | string,
) {
  if (status === null || status === undefined || status === '') return null;
  const code = String(status);
  const labels = statusLabelsByCategory[category] ?? {};
  return Object.hasOwn(labels, code) ? (labels[code] ?? code) : code;
}

/** 全部状态及不属于当前维度的状态不下发，避免跨层级误筛选。 */
export function normalizeAdDashboardStatus(
  category: AdDashboardCategory,
  status?: string,
) {
  return status && Object.hasOwn(statusLabelsByCategory[category] ?? {}, status)
    ? status
    : undefined;
}
