import type {
  ProjectComparisonAdapter,
  ProjectComparisonFormalTransport,
} from '../adapter';
import type {
  ProjectComparisonAgencyLineSource,
  ProjectComparisonQuery,
  ProjectComparisonSourceAuthority,
  ProjectComparisonSourceData,
  ProjectComparisonSourceRecord,
} from '../types';

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown, message: string): UnknownRecord {
  if (!isRecord(value)) throw new Error(message);
  return value;
}

function readString(record: UnknownRecord, keys: readonly string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return undefined;
}

function readRequiredString(
  record: UnknownRecord,
  keys: readonly string[],
  message: string,
) {
  const value = readString(record, keys);
  if (!value) throw new Error(message);
  return value;
}

function readRequiredNumber(
  record: UnknownRecord,
  keys: readonly string[],
  message: string,
) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  throw new Error(message);
}

function readResponseRoot(response: unknown) {
  const envelope = asRecord(response, '正式项目环比接口返回格式无效');
  const data = isRecord(envelope.data) ? envelope.data : envelope;
  return isRecord(data.overview) ? data.overview : data;
}

function readAuthority(
  record: UnknownRecord,
): ProjectComparisonSourceAuthority {
  const authority = asRecord(
    record.authority ?? record.metric_context,
    '正式项目环比接口缺少数据口径上下文',
  );
  return {
    attributionWindow: readRequiredString(
      authority,
      ['attributionWindow', 'attribution_window'],
      '正式项目环比接口缺少归因窗口',
    ),
    currency: readRequiredString(
      authority,
      ['currency'],
      '正式项目环比接口缺少报告币种',
    ),
    financialLedgerVersion: readRequiredString(
      authority,
      ['financialLedgerVersion', 'financial_ledger_version'],
      '正式项目环比接口缺少财务账本口径版本',
    ),
    timezone: readRequiredString(
      authority,
      ['timezone', 'time_zone'],
      '正式项目环比接口缺少项目时区',
    ),
  };
}

function readAgencyLines(record: UnknownRecord) {
  if (!Array.isArray(record.agencyLines ?? record.agency_lines)) {
    throw new TypeError('正式项目环比接口缺少代理线稳定 ID 列表');
  }
  const values = (record.agencyLines ?? record.agency_lines) as unknown[];
  const ids = new Set<string>();
  return values.map((value): ProjectComparisonAgencyLineSource => {
    const line = asRecord(value, '正式项目环比接口包含无效代理线');
    const id = readRequiredString(
      line,
      ['id', '_id', 'agencyLineId', 'agency_line_id'],
      '正式项目环比接口代理线缺少稳定 ID',
    );
    if (ids.has(id)) throw new Error('正式项目环比接口返回重复代理线 ID');
    ids.add(id);
    return {
      id,
      name: readRequiredString(
        line,
        ['name', 'agencyLineName', 'agency_line_name'],
        '正式项目环比接口代理线缺少名称',
      ),
      platform: readRequiredString(
        line,
        ['platform', 'mediaPlatform', 'media_platform'],
        '正式项目环比接口代理线缺少投放平台',
      ),
    };
  });
}

function readRecords(
  record: UnknownRecord,
  validAgencyLineIds: ReadonlySet<string>,
) {
  if (!Array.isArray(record.records)) {
    throw new TypeError('正式项目环比接口缺少按项目和代理线聚合的指标记录');
  }
  return record.records.map((value): ProjectComparisonSourceRecord => {
    const source = asRecord(value, '正式项目环比接口包含无效指标记录');
    const agencyLineId = readRequiredString(
      source,
      ['agencyLineId', 'agency_line_id'],
      '正式项目环比接口记录缺少稳定代理线 ID',
    );
    if (!validAgencyLineIds.has(agencyLineId)) {
      throw new Error('正式项目环比接口记录引用了未授权或未知代理线');
    }
    const day = readRequiredString(
      source,
      ['day', 'date'],
      '正式项目环比接口记录缺少统计日期',
    );
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) {
      throw new Error('正式项目环比接口记录日期格式无效');
    }
    const hour = readRequiredNumber(
      source,
      ['hour'],
      '正式项目环比接口记录缺少统计小时',
    );
    if (!Number.isInteger(hour) || hour < 0 || hour > 23) {
      throw new Error('正式项目环比接口记录统计小时无效');
    }
    return {
      agencyLineId,
      clicks: readRequiredNumber(
        source,
        ['clicks'],
        '正式项目环比接口记录缺少点击数',
      ),
      day,
      firstPurchaseRevenue: readRequiredNumber(
        source,
        ['firstPurchaseRevenue', 'first_purchase_revenue'],
        '正式项目环比接口记录缺少首充收入',
      ),
      firstPurchases: readRequiredNumber(
        source,
        ['firstPurchases', 'first_purchases'],
        '正式项目环比接口记录缺少首充人数',
      ),
      hour,
      impressions: readRequiredNumber(
        source,
        ['impressions'],
        '正式项目环比接口记录缺少展示数',
      ),
      projectCost: readRequiredNumber(
        source,
        ['projectCost', 'project_cost'],
        '正式项目环比接口记录缺少项目成本',
      ),
      registrations: readRequiredNumber(
        source,
        ['registrations'],
        '正式项目环比接口记录缺少注册量',
      ),
      spend: readRequiredNumber(
        source,
        ['spend'],
        '正式项目环比接口记录缺少广告消耗',
      ),
    };
  });
}

/**
 * Strict adapter for a backend-owned project-comparison Read Model. The
 * transport is injected so this class cannot invent an endpoint, credentials,
 * authorization filters, or a fallback to the legacy dashboard API.
 */
export class HttpProjectComparisonAdapter implements ProjectComparisonAdapter {
  constructor(private readonly transport: ProjectComparisonFormalTransport) {}

  async getSourceData(
    query: ProjectComparisonQuery,
  ): Promise<ProjectComparisonSourceData> {
    const root = readResponseRoot(
      await this.transport.getOverviewSource(query),
    );
    const project = asRecord(root.project, '正式项目环比接口缺少项目稳定 ID');
    const projectId = readRequiredString(
      project,
      ['id', 'projectId', 'project_id'],
      '正式项目环比接口缺少项目稳定 ID',
    );
    if (projectId !== query.projectId) {
      throw new Error('正式项目环比接口返回的项目稳定 ID 不匹配');
    }
    const asOf = readRequiredString(
      root,
      ['asOf', 'as_of'],
      '正式项目环比接口缺少数据截止时间',
    );
    if (Number.isNaN(new Date(asOf).getTime())) {
      throw new TypeError('正式项目环比接口数据截止时间格式无效');
    }
    const authority = readAuthority(root);
    const agencyLines = readAgencyLines(root);
    const lineIds = new Set(agencyLines.map((line) => line.id));
    const requestedLineIds = new Set(query.agencyLineIds ?? []);
    if (
      requestedLineIds.size > 0 &&
      [...lineIds].some((lineId) => !requestedLineIds.has(lineId))
    ) {
      throw new Error('正式项目环比接口返回了筛选范围外的代理线');
    }
    return {
      agencyLines,
      asOf,
      authority,
      records: readRecords(root, lineIds),
    };
  }
}
