import type { AdDashboardAdapter } from './adapter';
import type {
  AdDashboardCategory,
  AdDashboardListQuery,
  AdDashboardRow,
} from './types';

import {
  adDashboardCategoryOrder,
  getAdDashboardSchema,
  resolveAdDashboardCategory,
} from './schema';
import { normalizeAdDashboardStatus } from './status';

export class AdDashboardService {
  constructor(private readonly adapter: AdDashboardAdapter) {}

  getCategories() {
    return adDashboardCategoryOrder.map((category) => ({
      label: getAdDashboardSchema(category).label,
      value: category,
    }));
  }

  getSchema(category: AdDashboardCategory) {
    return getAdDashboardSchema(category);
  }

  list(query: AdDashboardListQuery) {
    return this.adapter.list(this.normalizeQuery(query, 100));
  }

  /** 与列表共用筛选和排序，分批取完后再下载，避免旧导出 10 万条上限截断。 */
  async listAll(query: AdDashboardListQuery) {
    const normalizedQuery = this.normalizeQuery(
      { ...query, pageSize: 10_000 },
      10_000,
    );
    const rows: AdDashboardRow[] = [];
    let total: number | undefined;
    for (let page = 1; ; page += 1) {
      const result = await this.adapter.list({ ...normalizedQuery, page });
      total ??= result.total;
      if (result.total !== total) {
        throw new Error('导出期间数据发生变化，请重新查询后导出');
      }
      rows.push(...result.items);
      // 部分旧维度按 DISTINCT ID 统计 total，明细还按名称分组；以读完一页判断结束。
      if (result.items.length < normalizedQuery.pageSize) return rows;
    }
  }

  resolveCategory(value?: null | string) {
    return resolveAdDashboardCategory(value);
  }

  private normalizeQuery(query: AdDashboardListQuery, maxPageSize: number) {
    let id = query.id?.trim() || undefined;
    if (query.category === 'account') {
      // 账户按换行批量输入，兼容旧链接的逗号；保留字符串精度并去重。
      id =
        [
          ...new Set(
            (id ?? '')
              .split(/[,\r\n]+/)
              .map((value) => value.trim().replace(/^act_/, '').trim())
              .filter(Boolean),
          ),
        ].join(',') || undefined;
    }
    return {
      ...query,
      // 当前层级搜索与 selectedIds 下钻条件独立传递，由后端取交集。
      id,
      page: Math.max(1, query.page ?? 1),
      pageSize: Math.min(maxPageSize, Math.max(1, query.pageSize ?? 50)),
      placerIds:
        query.category === 'agencyLine'
          ? [
              ...new Set(
                (query.placerIds ?? [])
                  .map((value) => value.trim())
                  .filter(Boolean),
              ),
            ]
          : undefined,
      status: normalizeAdDashboardStatus(query.category, query.status),
    };
  }
}
