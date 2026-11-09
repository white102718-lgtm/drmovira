import type {
  DashboardAnalyzeQuery,
  DashboardCampaignPerformance,
  DashboardDateQuery,
  DashboardHostingQuery,
  DashboardObjectQuery,
  MyDashboardAdapter,
} from './types';

import { isFusionDemoMode } from '#/api/fusion/mode';

import { getAdDashboardSchema } from '../ad-dashboard/schema';
import { normalizeAdDashboardStatus } from '../ad-dashboard/status';
import { HttpMyDashboardAdapter, MockMyDashboardAdapter } from './adapters';

export type * from './types';

/** 指挥台查询入口；身份与可见范围由后端会话决定。 */
class MyDashboardService {
  constructor(private readonly adapter: MyDashboardAdapter) {}

  accounts(query: DashboardDateQuery) {
    return this.adapter.accounts(query);
  }

  analyze(query: DashboardAnalyzeQuery, signal?: AbortSignal) {
    return this.adapter.analyze(query, signal);
  }

  /** 成效表独立查询本人系列，智能体不可覆盖名称、金额或效率指标。 */
  async campaigns(query: Omit<DashboardObjectQuery, 'category'>) {
    const result = await this.list({
      ...query,
      category: 'campaign',
      sortField: 'spend',
      sortOrder: 'desc',
      status: 'all',
    });
    const items: DashboardCampaignPerformance[] = result.items.map((row) => ({
      id: row.id,
      name: String(row.name ?? row.id),
      currency: row.currency,
      spend: typeof row.spend === 'number' ? row.spend : null,
      ctr: typeof row.ctr === 'number' ? row.ctr : null,
      cpa:
        typeof row.registrationCost === 'number' ? row.registrationCost : null,
    }));
    return { items, total: result.total };
  }

  getHosting() {
    return this.adapter.getHosting();
  }

  getSchema(category: DashboardObjectQuery['category']) {
    return getAdDashboardSchema(category);
  }

  list(query: DashboardObjectQuery) {
    return this.adapter.list({
      ...query,
      page: Math.max(1, query.page ?? 1),
      pageSize: Math.min(100, Math.max(10, query.pageSize ?? 10)),
      status: normalizeAdDashboardStatus(query.category, query.status),
    });
  }

  overview(query: DashboardDateQuery) {
    return this.adapter.overview(query);
  }

  saveHosting(query: DashboardHostingQuery) {
    if (
      query.enabled &&
      (!Number.isInteger(query.spend_change_threshold) ||
        query.spend_change_threshold < 5 ||
        query.spend_change_threshold > 100)
    ) {
      throw new Error('消耗波动阈值应为 5–100 的整数。');
    }
    return this.adapter.saveHosting(query);
  }

  trend(query: DashboardDateQuery) {
    return this.adapter.trend(query);
  }
}

export const myDashboardService = new MyDashboardService(
  isFusionDemoMode()
    ? new MockMyDashboardAdapter()
    : new HttpMyDashboardAdapter(),
);
