import type { AdDashboardAdapter } from '../adapter';
import type {
  AdDashboardCategory,
  AdDashboardListQuery,
  AdDashboardListResult,
} from '../types';

import { adpulseClient } from '#/api/request';

import {
  normalizeAdDashboardRow,
  summarizeAdDashboardRows,
} from '../normalize';
import { getAdDashboardSchema } from '../schema';

interface LegacyDashboardResponse {
  data: Record<string, unknown>[];
  pagination?: {
    page?: number;
    page_size?: number;
    total?: number;
  };
}

/** 将页面使用的新分类名还原成旧广告面板接口要求的筛选参数名。 */
export function buildLegacySelectionParams(
  selectedIds: AdDashboardListQuery['selectedIds'],
) {
  const params: Record<string, string> = {};
  for (const [category, ids] of Object.entries(selectedIds ?? {})) {
    if (!ids?.length) continue;
    const schema = getAdDashboardSchema(category as AdDashboardCategory);
    params[schema.legacyTabKey] = ids.join(',');
  }
  return params;
}

export class HttpAdDashboardAdapter implements AdDashboardAdapter {
  async list(query: AdDashboardListQuery): Promise<AdDashboardListResult> {
    const schema = getAdDashboardSchema(query.category);
    // 只发送当前维度支持的后端排序字段，不能直接透传页面的英文 key。
    const sortField = schema.fields.find(
      (field) => field.key === query.sortField && field.sortable,
    );
    const response = await adpulseClient.get<LegacyDashboardResponse>(
      `/dashboard/detail/${schema.legacyTabKey}`,
      {
        params: {
          ...buildLegacySelectionParams(query.selectedIds),
          date:
            query.startDate && query.endDate
              ? `${query.startDate},${query.endDate}`
              : undefined,
          id: query.id,
          name: query.name,
          page: query.page,
          page_size: query.pageSize,
          placer_id:
            query.category === 'agencyLine'
              ? query.placerIds?.join(',') || undefined
              : undefined,
          sort_by: sortField?.sortKey,
          sort_order: sortField?.sortKey ? query.sortOrder : undefined,
          status: query.status === 'all' ? undefined : query.status,
        },
      },
    );
    const items = response.data.map((row, index) =>
      normalizeAdDashboardRow(row, schema, index),
    );
    let dataCutoff = '';
    for (const row of items) {
      const updatedAt = String(row.updatedAt ?? '');
      if (updatedAt > dataCutoff) dataCutoff = updatedAt;
    }

    return {
      dataCutoff,
      items,
      page: response.pagination?.page ?? query.page ?? 1,
      pageSize: response.pagination?.page_size ?? query.pageSize ?? 50,
      schema,
      summaryRows: summarizeAdDashboardRows(items, schema),
      total: response.pagination?.total ?? items.length,
    };
  }
}
