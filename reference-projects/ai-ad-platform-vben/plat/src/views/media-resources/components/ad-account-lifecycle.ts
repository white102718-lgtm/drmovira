import type { AssetLifecycleDetail } from '#/api';

import dayjs from 'dayjs';

import { assetFlowApi, getAdAccountLifecycle } from '#/api';
import { adDashboardService } from '#/domain/ad-dashboard';

import { successfulApplicationEvents } from './application-lifecycle-events';

const ACCOUNT_PAGE_LOAD_CONCURRENCY = 5;

interface AccountSpendResult {
  amount: number;
  currency: string;
  dataCutoff?: string;
}

function normalizedAccountId(accountId: string) {
  return accountId.trim().replace(/^act_/i, '');
}

async function loadAccountSpend(
  accountId: string,
  startDate: string,
  endDate: string,
): Promise<AccountSpendResult> {
  const result = await adDashboardService.list({
    category: 'account',
    endDate,
    id: normalizedAccountId(accountId),
    page: 1,
    pageSize: 100,
    startDate,
    status: 'all',
  });
  const expectedId = normalizedAccountId(accountId);
  const rows = result.items.filter(
    (row) => normalizedAccountId(row.id) === expectedId,
  );
  const currencies = [
    ...new Set(rows.map((row) => row.currency).filter(Boolean)),
  ];

  return {
    amount: rows.reduce(
      (total, row) => total + (typeof row.spend === 'number' ? row.spend : 0),
      0,
    ),
    currency: currencies.length === 1 ? (currencies[0] ?? 'USD') : 'USD',
    dataCutoff: result.dataCutoff || undefined,
  };
}

async function loadSpendRanges(
  accountId: string,
  ranges: Array<{ endDate: string; key: string; startDate: string }>,
) {
  const results = new Map<string, AccountSpendResult>();
  const failures = new Set<string>();
  for (
    let start = 0;
    start < ranges.length;
    start += ACCOUNT_PAGE_LOAD_CONCURRENCY
  ) {
    const batch = ranges.slice(start, start + ACCOUNT_PAGE_LOAD_CONCURRENCY);
    const settled = await Promise.allSettled(
      batch.map((range) =>
        loadAccountSpend(accountId, range.startDate, range.endDate),
      ),
    );
    settled.forEach((result, index) => {
      const key = batch[index]?.key;
      if (!key) return;
      if (result.status === 'fulfilled') results.set(key, result.value);
      else failures.add(key);
    });
  }
  return { failures, results };
}

/**
 * 合并 main 的广告账户使用区间、system 的审批轨迹与广告面板消耗数据。
 */
export async function loadAdAccountLifecycleDetail(
  accountId: string,
): Promise<AssetLifecycleDetail> {
  const [detail, applications] = await Promise.all([
    getAdAccountLifecycle(accountId),
    assetFlowApi.accountLifecycleApplications(accountId),
  ]);
  const today = dayjs.tz().format('YYYY-MM-DD');
  const stockedAt = detail.events.find(
    (event) => event.eventType === 'STOCKED',
  )?.occurredAt;
  const cumulativeStart = dayjs(stockedAt ?? today).format('YYYY-MM-DD');
  const usageRanges = detail.usagePeriods.map((period, index) => ({
    endDate: dayjs(period.endedAt ?? today).format('YYYY-MM-DD'),
    key: `usage-${index}`,
    startDate: dayjs(period.startedAt).format('YYYY-MM-DD'),
  }));
  const requestedRanges = [
    { endDate: today, key: 'cumulative', startDate: cumulativeStart },
    { endDate: today, key: 'today', startDate: today },
    ...usageRanges,
  ];
  const uniqueRanges = requestedRanges.filter(
    (range, index, ranges) =>
      range.startDate <= range.endDate &&
      ranges.findIndex(
        (candidate) =>
          candidate.startDate === range.startDate &&
          candidate.endDate === range.endDate,
      ) === index,
  );
  const spendRanges = await loadSpendRanges(accountId, uniqueRanges);
  const spendFor = (key: string) => {
    const range = requestedRanges.find((item) => item.key === key);
    if (!range) return undefined;
    const canonical = uniqueRanges.find(
      (item) =>
        item.startDate === range.startDate && item.endDate === range.endDate,
    );
    return canonical ? spendRanges.results.get(canonical.key) : undefined;
  };
  const cumulativeSpend = spendFor('cumulative');
  const todaySpend = spendFor('today');

  return {
    asset: {
      assetCode: detail.account.accountId,
      assetName: detail.account.accountName,
      assetType: '广告账户',
      currentUserName: detail.account.usageUserName,
      id: detail.account.accountId,
      projectName: detail.account.channelName,
      status: detail.account.inventoryStatus ?? 'AVAILABLE',
      teamName: detail.account.usageDepartmentName,
      spend: {
        cumulative: cumulativeSpend?.amount,
        currency: cumulativeSpend?.currency ?? todaySpend?.currency ?? 'USD',
        dataCutoff: cumulativeSpend?.dataCutoff ?? todaySpend?.dataCutoff,
        today: todaySpend?.amount,
        unavailable:
          spendRanges.failures.has('cumulative') ||
          spendRanges.failures.has('today'),
      },
    },
    events: [
      ...detail.events.map((event) => ({
        ...event,
        description:
          event.eventType === 'STOCKED'
            ? '账户已入库'
            : event.eventType === 'ASSIGNED'
              ? `发放给 ${event.targetUserName || '未记录使用人'}`
              : event.eventType === 'RELEASED'
                ? `结束 ${event.targetUserName || '原使用人'} 的使用`
                : event.description,
      })),
      ...applications.flatMap(successfulApplicationEvents),
    ].sort((left, right) => right.occurredAt.localeCompare(left.occurredAt)),
    usagePeriods: detail.usagePeriods.map((period, index) => {
      const spend = spendFor(`usage-${index}`);
      return {
        ...period,
        projectName: detail.account.channelName,
        spend: spend?.amount,
        spendCurrency: spend?.currency,
        spendUnavailable: !spend,
      };
    }),
  };
}
