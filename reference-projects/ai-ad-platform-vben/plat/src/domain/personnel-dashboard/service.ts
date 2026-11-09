import type { PersonnelDashboardAdapter } from './adapter';
import type {
  PersonnelDashboardCategory,
  PersonnelDashboardCsvExport,
  PersonnelDashboardListQuery,
  PersonnelDashboardRow,
  PersonnelDashboardSchema,
} from './types';

import { formatPersonnelDashboardValue } from './format';
import {
  getPersonnelDashboardSchema,
  personnelDashboardCategoryOrder,
  resolvePersonnelDashboardCategory,
} from './schema';

function csvCell(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

function csvRows(
  rows: PersonnelDashboardRow[],
  schema: PersonnelDashboardSchema,
) {
  const headers = schema.fields.map((field) => csvCell(field.label)).join(',');
  const data = rows.map((row) =>
    schema.fields
      .map((field) =>
        csvCell(
          String(
            formatPersonnelDashboardValue(row[field.key], field, row.currency),
          ),
        ),
      )
      .join(','),
  );
  return `\uFEFF${[headers, ...data].join('\r\n')}`;
}

export class PersonnelDashboardService {
  constructor(private readonly adapter: PersonnelDashboardAdapter) {}

  async exportCsv(
    query: PersonnelDashboardListQuery,
  ): Promise<PersonnelDashboardCsvExport> {
    const firstPage = await this.list({ ...query, page: 1, pageSize: 100 });
    const rows = [...firstPage.items];
    const totalPages = Math.ceil(firstPage.total / 100);
    for (let page = 2; page <= totalPages; page += 1) {
      const result = await this.list({ ...query, page, pageSize: 100 });
      rows.push(...result.items);
    }
    const suffix = `${query.startDate ?? 'all'}_${query.endDate ?? 'all'}`;
    return {
      content: csvRows(rows, firstPage.schema),
      fileName: `人员数据_${firstPage.schema.sheetName}_${suffix}.csv`,
      rowCount: rows.length,
    };
  }

  getCategories() {
    return personnelDashboardCategoryOrder.map((category) => ({
      label: getPersonnelDashboardSchema(category).label,
      value: category,
    }));
  }

  getSchema(category: PersonnelDashboardCategory) {
    return getPersonnelDashboardSchema(category);
  }

  list(query: PersonnelDashboardListQuery) {
    return this.adapter.list({
      ...query,
      page: Math.max(1, query.page ?? 1),
      pageSize: Math.min(100, Math.max(1, query.pageSize ?? 10)),
    });
  }

  resolveCategory(value?: null | string) {
    return resolvePersonnelDashboardCategory(value);
  }
}
