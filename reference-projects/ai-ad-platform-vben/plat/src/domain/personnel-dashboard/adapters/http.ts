import type { PersonnelDashboardAdapter } from '../adapter';
import type {
  PersonnelDashboardListQuery,
  PersonnelDashboardListResult,
} from '../types';

import { backendClient } from '#/api/request';

import {
  normalizePersonnelDashboardRow,
  summarizePersonnelDashboardRows,
} from '../normalize';
import { getPersonnelDashboardSchema } from '../schema';

interface LegacyDashboardResponse {
  data: Record<string, unknown>[];
  filter_options?: {
    departments?: Array<string | { label?: string; value?: string }>;
  };
  pagination?: {
    page?: number;
    page_size?: number;
    total?: number;
  };
}

export class HttpPersonnelDashboardAdapter
  implements PersonnelDashboardAdapter
{
  async list(
    query: PersonnelDashboardListQuery,
  ): Promise<PersonnelDashboardListResult> {
    const schema = getPersonnelDashboardSchema(query.category);
    const response = await backendClient.get<LegacyDashboardResponse>(
      `/dashboard/detail/${schema.legacyTabKey}`,
      {
        params: {
          date:
            query.startDate && query.endDate
              ? `${query.startDate},${query.endDate}`
              : undefined,
          department_id: query.departmentId,
          keyword: query.keyword,
          page: query.page,
          page_size: query.pageSize,
          sort_by: query.sortField,
          sort_order: query.sortOrder,
          status: query.status === 'all' ? undefined : query.status,
        },
      },
    );
    const items = response.data.map((row, index) =>
      normalizePersonnelDashboardRow(row, schema, index),
    );
    let dataCutoff = '';
    for (const row of items) {
      const updatedAt = String(row.updatedAt ?? '');
      if (updatedAt > dataCutoff) dataCutoff = updatedAt;
    }
    const departmentOptions = (response.filter_options?.departments ?? []).map(
      (option) =>
        typeof option === 'string'
          ? { label: option, value: option }
          : {
              label: String(option.label ?? option.value ?? ''),
              value: String(option.value ?? option.label ?? ''),
            },
    );

    return {
      dataCutoff,
      departmentOptions,
      items,
      page: response.pagination?.page ?? query.page ?? 1,
      pageSize: response.pagination?.page_size ?? query.pageSize ?? 20,
      schema,
      summaryRows: summarizePersonnelDashboardRows(items, schema),
      total: response.pagination?.total ?? items.length,
    };
  }
}
