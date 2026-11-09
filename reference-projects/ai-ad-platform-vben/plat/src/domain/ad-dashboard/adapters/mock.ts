import type { AdDashboardAdapter } from '../adapter';
import type {
  AdDashboardCategory,
  AdDashboardField,
  AdDashboardListQuery,
  AdDashboardListResult,
  AdDashboardRow,
  AdDashboardSchema,
  AdDashboardValue,
} from '../types';

import {
  calculateAdDashboardEfficiencyMetrics,
  summarizeAdDashboardRows,
} from '../normalize';
import { getAdDashboardSchema } from '../schema';
import { getAdDashboardStatusOptions } from '../status';

const names: Record<AdDashboardCategory, string[]> = {
  account: ['ADS 41785', 'IFC-USD-GMT+5.30-CD5262-1119', 'Meta SEA 备用账户'],
  ad: ['1 - 广告副本', '8-9-27', 'Starfall 夏季 UGC'],
  adSet: ['1', 'ID Broad 18-34', 'US Value LAL 3%'],
  agencyLine: ['Bonu7-TF-Z27-45', 'MP012-FB', 'Starfall-Google-US'],
  campaign: ['Bonu7-TF-Z5A-53', 'ID_RewardHook_AEO', 'US_Packshot_Value'],
  channel: ['MPower-BM绑卡户', 'MP012-FB', 'Google Global MCC'],
  department: ['TF', '增长一部', '全球发行部'],
  pixel: ['Starfall iOS 像素', 'Pixel Quest Android 像素', 'Orbit BR 转化像素'],
  platform: ['facebook', 'google', 'tiktok'],
  project: ['bonu', 'Starfall', 'Pixel Quest'],
};

function numericValue(field: AdDashboardField, index: number) {
  if (index % 11 === 10) return null;
  if (index % 8 === 7 && !['id', 'name'].includes(field.key)) return 0;
  const scale = index + 1;
  if (field.dataType === 'percent') return ((index % 5) + 1) / 100;
  if (field.key.toLowerCase().includes('roas')) return 0.4 + (index % 6) * 0.58;
  if (field.dataType === 'currency') return Number((12.48 * scale).toFixed(2));
  return scale * 37;
}

function fieldValue(
  field: AdDashboardField,
  category: AdDashboardCategory,
  index: number,
): AdDashboardValue {
  const categoryNames = names[category];
  const baseName = categoryNames[index % categoryNames.length] ?? category;
  if (field.key === 'name')
    return `${baseName}${index > 2 ? ` ${index + 1}` : ''}`;
  if (field.key === 'id')
    return `${category}-${String(index + 1).padStart(3, '0')}`;
  if (field.key === 'pixelId') return `px_${String(12_024_801_001 + index)}`;
  if (field.key === 'updatedAt') {
    return `2026-08-${String(12 - (index % 4)).padStart(2, '0')} ${String(8 + (index % 9)).padStart(2, '0')}:0${index % 6}`;
  }
  if (field.key === 'createdAt')
    return `2026-08-${String(1 + (index % 9)).padStart(2, '0')} 09:30`;
  // 分层状态统一在 buildRows 中赋值，同时保留原始码和展示文案。
  if (field.dataType === 'status') return null;
  if (field.dataType === 'url') {
    return index % 11 === 10
      ? null
      : `https://example.com/ads/${category}-${index + 1}`;
  }
  if (field.dataType === 'identifier')
    return `${field.key}-${category}-${index + 1}`;
  if (field.dataType === 'text') {
    const textByKey: Record<string, string> = {
      accountName: `广告账户 ${index + 1}`,
      agencyLineName:
        ['MP012-FB', 'Starfall-Google-US', 'Orbit-TikTok-JP'][index % 3] ??
        'MP012-FB',
      budgetRange: index % 2 ? '50–500' : '',
      channelName:
        ['MP012-FB', 'Google Global MCC', 'TikTok 日本渠道'][index % 3] ??
        'MP012-FB',
      departmentName: ['TF', '增长一部', '全球发行部'][index % 3] ?? 'TF',
      projectName: ['bonu', 'Starfall', 'Pixel Quest'][index % 3] ?? 'bonu',
    };
    return textByKey[field.key] || `${field.label} ${index + 1}`;
  }
  return numericValue(field, index);
}

function buildRows(schema: AdDashboardSchema): AdDashboardRow[] {
  const statuses = getAdDashboardStatusOptions(schema.category);
  const accountStatuses = getAdDashboardStatusOptions('account');
  return Array.from({ length: 24 }, (_, index) => {
    const values = Object.fromEntries(
      schema.fields.map((field) => [
        field.key,
        fieldValue(field, schema.category, index),
      ]),
    ) as AdDashboardRow;
    const status = statuses[index % statuses.length];
    if (status) {
      values.statusText = status.label;
      values.accountStatus =
        accountStatuses[index % accountStatuses.length]?.value ?? null;
      values.effectiveStatus =
        schema.category === 'account' ? null : status.value;
    }
    Object.assign(values, calculateAdDashboardEfficiencyMetrics(values));
    const id = String(values.id ?? `${schema.category}-${index + 1}`);
    return {
      ...values,
      currency: index % 9 === 8 ? 'EUR' : 'USD',
      id,
      key: id,
    };
  });
}

function statusMatches(row: AdDashboardRow, query: AdDashboardListQuery) {
  if (!query.status || query.status === 'all') return true;
  const rowStatus =
    query.category === 'account' ? row.accountStatus : row.effectiveStatus;
  return rowStatus === query.status;
}

export interface MockAdDashboardAdapterOptions {
  delay?: number;
}

export class MockAdDashboardAdapter implements AdDashboardAdapter {
  private readonly delay: number;

  constructor(options: MockAdDashboardAdapterOptions = {}) {
    this.delay = options.delay ?? 160;
  }

  async list(query: AdDashboardListQuery): Promise<AdDashboardListResult> {
    const schema = getAdDashboardSchema(query.category);
    const keyword = query.name?.trim().toLowerCase();
    const accountIds =
      query.category === 'account' ? query.id?.split(',') : undefined;
    const filtered = buildRows(schema).filter((row) => {
      const matchesKeyword =
        !keyword ||
        Object.values(row).some((value) =>
          String(value ?? '')
            .toLowerCase()
            .includes(keyword),
        );
      const matchesId =
        !query.id ||
        (accountIds
          ? accountIds.includes(row.id)
          : row.id === query.id.trim().replace(/^act_/, ''));
      const updatedDate = String(row.updatedAt ?? '').slice(0, 10);
      const matchesStart = !query.startDate || updatedDate >= query.startDate;
      const matchesEnd = !query.endDate || updatedDate <= query.endDate;
      return (
        matchesKeyword &&
        matchesId &&
        matchesStart &&
        matchesEnd &&
        statusMatches(row, query)
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
                {
                  numeric: true,
                },
              );
        return query.sortOrder === 'asc' ? result : -result;
      });
    }
    const page = Math.max(1, query.page ?? 1);
    const pageSize = Math.max(1, query.pageSize ?? 50);
    let dataCutoff = '';
    for (const row of filtered) {
      const updatedAt = String(row.updatedAt ?? '');
      if (updatedAt > dataCutoff) dataCutoff = updatedAt;
    }
    const result = {
      dataCutoff,
      items: filtered.slice((page - 1) * pageSize, page * pageSize),
      page,
      pageSize,
      schema,
      summaryRows: summarizeAdDashboardRows(filtered, schema),
      total: filtered.length,
    };
    if (this.delay <= 0) return result;
    return new Promise((resolve) =>
      window.setTimeout(() => resolve(result), this.delay),
    );
  }
}
