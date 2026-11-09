import type { AgencyLineAdapter } from '../adapter';
import type {
  AgencyLine,
  AgencyLineCreateCommand,
  AgencyLineDeliveryUrlHistory,
  AgencyLineListQuery,
  AgencyLineListResult,
  AgencyLineOption,
  AgencyLineUpsertInput,
} from '../types';

import type { AgentLineConfigItem } from '#/api/management/platform-config';

import { mainBackendClient } from '#/api/request';

type LegacyAgencyLineRecord = Omit<
  AgentLineConfigItem,
  'budget_cap' | 'budget_floor'
> & {
  budget_cap?: number | string;
  budget_floor?: number | string;
  media_platform?: string;
  objective?: string;
  optimizer_id?: string;
  pixel_id?: string;
  pixel_name?: string;
  platform?: string;
  project_id?: string;
  test_code?: string;
  token?: string;
  type?: string;
  cloak_url?: string;
};

type ApiAgencyLine = Omit<
  AgencyLine,
  'optimizerId' | 'optimizerName' | 'pixelName' | 'projectId'
> & {
  optimizerId?: null | string;
  optimizerName: null | string;
  pixelName: null | string;
  projectId?: null | string;
};

function asOptionalNumber(value: unknown) {
  if (value === '' || value === null || value === undefined) return undefined;
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function normalizePlatform(record: LegacyAgencyLineRecord) {
  return (
    record.platform?.trim().toLowerCase() ||
    record.media_platform?.trim().toLowerCase() ||
    'unknown'
  );
}

function readCreatedAgencyLine(
  value: unknown,
  input: AgencyLineUpsertInput,
  bindingProjectId?: null | string,
): AgencyLine | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const candidate = value as Record<string, unknown>;

  let projectedProjectId = bindingProjectId;
  if (candidate.binding && typeof candidate.binding === 'object') {
    const binding = candidate.binding as Record<string, unknown>;
    projectedProjectId =
      binding.status === 'bound' && typeof binding.projectId === 'string'
        ? binding.projectId
        : null;
  }
  if (candidate.data && typeof candidate.data === 'object') {
    return readCreatedAgencyLine(candidate.data, input, projectedProjectId);
  }
  if (candidate.agencyLine && typeof candidate.agencyLine === 'object') {
    return readCreatedAgencyLine(
      candidate.agencyLine,
      input,
      projectedProjectId,
    );
  }

  let stableId = '';
  if (typeof candidate.id === 'string') stableId = candidate.id.trim();
  else if (typeof candidate._id === 'string') stableId = candidate._id.trim();
  if (!stableId) return undefined;

  if (typeof candidate.name === 'string') {
    let canonicalProjectId = projectedProjectId ?? undefined;
    if (
      projectedProjectId === undefined &&
      Object.hasOwn(candidate, 'projectId')
    ) {
      canonicalProjectId =
        typeof candidate.projectId === 'string'
          ? candidate.projectId
          : undefined;
    }
    return {
      ...input,
      ...(candidate as Partial<AgencyLine>),
      createdAt:
        typeof candidate.createdAt === 'string'
          ? candidate.createdAt
          : new Date().toISOString(),
      id: stableId,
      projectId: canonicalProjectId,
      updatedAt:
        typeof candidate.updatedAt === 'string'
          ? candidate.updatedAt
          : new Date().toISOString(),
    } as AgencyLine;
  }

  const line = normalizeLegacyAgencyLine(
    candidate as unknown as LegacyAgencyLineRecord,
  );
  return {
    ...line,
    projectId:
      projectedProjectId === undefined
        ? line.projectId
        : (projectedProjectId ?? undefined),
  };
}

export function normalizeLegacyAgencyLine(
  record: LegacyAgencyLineRecord,
): AgencyLine {
  const name =
    record.agent_line?.trim() || record._id?.trim() || record.id?.trim() || '';
  return {
    autoRun: record.auto_run ?? false,
    budgetCap: asOptionalNumber(record.budget_cap),
    budgetFloor: asOptionalNumber(record.budget_floor),
    cloakUrl: record.cloak_url?.trim() ?? '',
    createdAt: record.create_time ?? '',
    deliveryUrl: record.package_url?.trim() ?? '',
    enabled: record.enabled ?? false,
    id: record.id?.trim() || record._id?.trim() || name,
    isSend: record.is_send ?? false,
    legacyGamePlatform: record.game_platform?.trim() || undefined,
    name,
    objective: record.objective?.trim() ?? '',
    optimizerId: record.optimizer_id?.trim() || undefined,
    optimizerName: record.optimizer?.trim() ?? '',
    packageName: record.package_name?.trim() ?? '',
    packageType: record.package_type?.trim() ?? '',
    pageId: record.page_id?.trim() ?? '',
    pixelId: record.pixel_id?.trim() ?? '',
    pixelName: record.pixel_name?.trim() ?? '',
    platform: normalizePlatform(record),
    projectId: record.project_id?.trim() || undefined,
    testCode: record.test_code?.trim() ?? '',
    token: record.token?.trim() ?? '',
    type: record.type?.trim() ?? '',
    updatedAt: record.update_time ?? record.create_time ?? '',
  };
}

/** 正式 API 允许两个优化师字段为 NULL，领域内保持空字符串以便展示。 */
export function normalizeAgencyLine(record: ApiAgencyLine): AgencyLine {
  return {
    ...record,
    cloakUrl: record.cloakUrl ?? '',
    deliveryUrl: record.deliveryUrl ?? '',
    optimizerId: record.optimizerId?.trim() || undefined,
    optimizerName: record.optimizerName ?? '',
    pixelId: record.pixelId ?? '',
    pixelName: record.pixelName ?? '',
    projectId: record.projectId || undefined,
    testCode: record.testCode ?? '',
    token: record.token ?? '',
    type: record.type ?? '',
  };
}

/** 全量写入显式传 NULL，避免序列化丢弃 undefined 后清空失效。 */
export function agencyLinePayload(input: AgencyLineUpsertInput) {
  return {
    ...input,
    optimizerId: input.optimizerId || null,
    optimizerName: input.optimizerName || null,
  };
}

export class HttpAgencyLineAdapter implements AgencyLineAdapter {
  async create(command: AgencyLineCreateCommand): Promise<AgencyLine> {
    const response = await mainBackendClient.post<unknown>(
      '/project/agency-lines',
      {
        agencyLine: agencyLinePayload(command.input),
        projectId: command.input.projectId,
      },
      {
        headers: { 'Idempotency-Key': command.requestId },
      },
    );
    const line = readCreatedAgencyLine(response, command.input);
    if (!line) {
      throw new Error('正式代理线创建接口未返回稳定代理线 ID');
    }
    if (!line.id.trim()) {
      throw new Error('正式代理线创建接口未返回稳定代理线 ID');
    }
    return normalizeAgencyLine(line);
  }

  async get(id: string): Promise<AgencyLine> {
    const line = await mainBackendClient.get<ApiAgencyLine>(
      `/project/agency-lines/${encodeURIComponent(id)}`,
    );
    return normalizeAgencyLine(line);
  }

  async getDeliveryUrlHistory(
    id: string,
  ): Promise<AgencyLineDeliveryUrlHistory[]> {
    return mainBackendClient.get<AgencyLineDeliveryUrlHistory[]>(
      `/project/agency-lines/${encodeURIComponent(id)}/delivery-url-history`,
    );
  }

  async list(query: AgencyLineListQuery = {}): Promise<AgencyLineListResult> {
    const page = Math.max(1, query.page ?? 1);
    const pageSize = Math.max(1, query.pageSize ?? 20);
    const response = await mainBackendClient.get<
      | Array<ApiAgencyLine | LegacyAgencyLineRecord>
      | {
          items?: Array<ApiAgencyLine | LegacyAgencyLineRecord>;
          total?: number;
        }
    >('/project/agency-lines', {
      params: { ...query, page, pageSize },
    });
    const records = Array.isArray(response) ? response : (response.items ?? []);
    const items = records.map((record) =>
      'name' in record
        ? normalizeAgencyLine(record)
        : normalizeLegacyAgencyLine(record),
    );

    return {
      items,
      page,
      pageSize,
      total: Number(
        Array.isArray(response)
          ? records.length
          : (response.total ?? records.length),
      ),
    };
  }

  async listOptions(
    query: AgencyLineListQuery = {},
  ): Promise<AgencyLineOption[]> {
    const result = await this.list({ ...query, page: 1, pageSize: 10_000 });
    return result.items.map(
      ({
        enabled,
        id,
        legacyGamePlatform,
        name,
        objective,
        pageId,
        pixelName,
        platform,
        projectId,
      }) => ({
        enabled,
        id,
        legacyGamePlatform,
        name,
        objective,
        pageId,
        pixelName,
        platform,
        projectId,
      }),
    );
  }

  async remove(id: string): Promise<void> {
    await mainBackendClient.delete(
      `/project/agency-lines/${encodeURIComponent(id)}`,
      { skipErrorMessage: true },
    );
  }

  async save(input: AgencyLineUpsertInput): Promise<AgencyLine> {
    if (!input.id) {
      throw new Error('正式新增代理线必须使用带幂等键的 create 契约');
    }
    const line = await mainBackendClient.put<ApiAgencyLine>(
      `/project/agency-lines/${encodeURIComponent(input.id)}`,
      agencyLinePayload(input),
    );
    return normalizeAgencyLine(line);
  }
}
