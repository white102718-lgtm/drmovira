import type { PersonnelDashboardAdapter } from '../adapter';
import type {
  PersonnelDashboardCategory,
  PersonnelDashboardField,
  PersonnelDashboardListQuery,
  PersonnelDashboardListResult,
  PersonnelDashboardRow,
  PersonnelDashboardSchema,
  PersonnelDashboardValue,
} from '../types';

import { summarizePersonnelDashboardRows } from '../normalize';
import { getPersonnelDashboardSchema } from '../schema';

const names: Record<PersonnelDashboardCategory, string[]> = {
  account: ['陈航', '赵宁', '林琦'],
  agencyLine: ['陈航', '赵宁', '林琦'],
  gamePlatform: ['陈航', '赵宁', '林琦'],
  placer: ['陈航', '赵宁', '林琦'],
  runningSeries: ['陈航', '赵宁', '林琦'],
};

const departments = [
  { label: '增长一部', value: 'dept-growth-1' },
  { label: '全球发行部', value: 'dept-global' },
  { label: '日本增长组', value: 'dept-japan' },
];

const accountTypes = [
  '普通户（未加白）',
  '准稳户（加白其它国家牌照）',
  '加白户/稳定户（加白巴西牌照）',
];

const projectNames = ['Bonu7', 'Starfall', 'Pixel Quest'];

function mockUpdatedAt(index: number) {
  return `2026-08-${String(12 - (index % 4)).padStart(2, '0')} ${String(
    8 + (index % 9),
  ).padStart(2, '0')}:0${index % 6}`;
}

function numericValue(field: PersonnelDashboardField, index: number) {
  if (index % 11 === 10) return null;
  if (index % 8 === 7 && field.key !== 'name') return 0;
  const scale = index + 1;
  if (field.dataType === 'percent') return ((index % 5) + 1) / 100;
  if (field.key.toLowerCase().includes('roas')) {
    return Number((0.42 + (index % 6) * 0.57).toFixed(2));
  }
  if (field.dataType === 'currency') {
    return Number((12.48 * scale).toFixed(2));
  }
  return scale * 37;
}

function fieldValue(
  field: PersonnelDashboardField,
  category: PersonnelDashboardCategory,
  index: number,
): PersonnelDashboardValue {
  const categoryNames = names[category];
  const baseName = categoryNames[index % categoryNames.length] ?? category;
  if (field.key === 'name') {
    return baseName;
  }
  if (field.key === 'updatedAt') {
    return mockUpdatedAt(index);
  }
  if (field.key === 'accountId') {
    return `act_${String(8_420_016_500 + index * 791)}`;
  }
  if (field.key === 'accountType') {
    return accountTypes[index % accountTypes.length] ?? '普通户（未加白）';
  }
  if (field.key === 'projectName') {
    return projectNames[index % projectNames.length] ?? 'Bonu7';
  }
  if (field.key === 'runningCampaign') return String(index + 1);
  if (field.key === 'statusText') {
    if (index % 7 === 6) return '异常';
    return index % 4 === 3 ? '已暂停' : '投放中';
  }
  if (field.key === 'effectiveStatus') {
    return index % 4 === 3 ? 'PAUSED' : 'ACTIVE';
  }
  if (field.key === 'accountStatus') return index % 7 === 6 ? '2' : '1';
  return numericValue(field, index);
}

function buildRows(schema: PersonnelDashboardSchema) {
  return Array.from({ length: 17 }, (_, index) => {
    const department =
      departments[index % departments.length] ?? departments[0];
    if (!department) {
      throw new Error('Personnel departments are not configured');
    }
    const values = Object.fromEntries(
      schema.fields.map((field) => [
        field.key,
        fieldValue(field, schema.category, index),
      ]),
    );
    const id = `${schema.category}-${String(index + 1).padStart(3, '0')}`;
    return {
      ...values,
      // 投手工作簿不展示最新时间，但页面筛选和数据截止时间仍需要它。
      updatedAt: mockUpdatedAt(index),
      currency: index % 9 === 8 ? 'EUR' : 'USD',
      departmentId: department.value,
      departmentName: department.label,
      id,
      key: id,
    } as PersonnelDashboardRow;
  });
}

function statusMatches(
  row: PersonnelDashboardRow,
  status: PersonnelDashboardListQuery['status'],
) {
  if (!status || status === 'all') return true;
  const combined = `${row.statusText ?? ''}${row.effectiveStatus ?? ''}`;
  if (status === 'running') return combined.includes('投放中');
  if (status === 'paused') return combined.includes('暂停');
  return combined.includes('异常');
}

export interface MockPersonnelDashboardAdapterOptions {
  delay?: number;
}

export class MockPersonnelDashboardAdapter
  implements PersonnelDashboardAdapter
{
  private readonly delay: number;

  constructor(options: MockPersonnelDashboardAdapterOptions = {}) {
    this.delay = options.delay ?? 160;
  }

  async list(
    query: PersonnelDashboardListQuery,
  ): Promise<PersonnelDashboardListResult> {
    const schema = getPersonnelDashboardSchema(query.category);
    const keyword = query.keyword?.trim().toLowerCase();
    const filtered = buildRows(schema).filter((row) => {
      const matchesKeyword =
        !keyword ||
        Object.values(row).some((value) =>
          String(value ?? '')
            .toLowerCase()
            .includes(keyword),
        );
      const updatedDate = String(row.updatedAt ?? '').slice(0, 10);
      const matchesStart = !query.startDate || updatedDate >= query.startDate;
      const matchesEnd = !query.endDate || updatedDate <= query.endDate;
      const matchesDepartment =
        !query.departmentId || row.departmentId === query.departmentId;
      return (
        matchesKeyword &&
        matchesStart &&
        matchesEnd &&
        matchesDepartment &&
        statusMatches(row, query.status)
      );
    });
    const sortField = schema.fields.find(
      (field) => field.key === query.sortField && field.sortable,
    );
    if (sortField) {
      filtered.sort((left, right) => {
        const leftValue = left[sortField.key];
        const rightValue = right[sortField.key];
        const result =
          typeof leftValue === 'number' && typeof rightValue === 'number'
            ? leftValue - rightValue
            : String(leftValue ?? '').localeCompare(
                String(rightValue ?? ''),
                'zh-CN',
                { numeric: true },
              );
        return query.sortOrder === 'asc' ? result : -result;
      });
    }
    const page = Math.max(1, query.page ?? 1);
    const pageSize = Math.max(1, query.pageSize ?? 10);
    let dataCutoff = '';
    for (const row of filtered) {
      const updatedAt = String(row.updatedAt ?? '');
      if (updatedAt > dataCutoff) dataCutoff = updatedAt;
    }
    const result = {
      dataCutoff,
      departmentOptions: departments,
      items: filtered.slice((page - 1) * pageSize, page * pageSize),
      page,
      pageSize,
      schema,
      summaryRows: summarizePersonnelDashboardRows(filtered, schema),
      total: filtered.length,
    };
    if (this.delay <= 0) return result;
    return new Promise((resolve) =>
      globalThis.setTimeout(() => resolve(result), this.delay),
    );
  }
}
