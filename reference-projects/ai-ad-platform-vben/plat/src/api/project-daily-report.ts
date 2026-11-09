import type {
  ProjectDailyReportImportResult,
  ProjectDailyReportQuery,
  ProjectDailyReportResult,
  ProjectDailyReportSyncStatus,
} from '#/domain/project-daily-report/types';

import { useAccessStore } from '@vben/stores';

/**
 * 项目日报存在 Doris，由飞书智能体进程读写。
 * 这里走 /agent，不走 Java /backend。
 */
const BASE = import.meta.env.VITE_GLOB_AGENT_API_URL || '/agent';

export class ProjectDailyReportRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ProjectDailyReportRequestError';
    this.status = status;
  }
}

function authHeaders(): Record<string, string> {
  const token = useAccessStore().accessToken;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers ?? {}) },
  });
  if (response.ok) {
    return (await response.json()) as T;
  }
  let detail = '';
  try {
    const body = await response.json();
    detail = body?.detail ?? body?.message ?? '';
  } catch {
    detail = '';
  }
  throw new ProjectDailyReportRequestError(
    detail || '项目运营面板暂时无法访问，请稍后重试。',
    response.status,
  );
}

function queryString(params: ProjectDailyReportQuery) {
  const search = new URLSearchParams();
  search.set('startDate', params.startDate);
  search.set('endDate', params.endDate);
  if (params.projectId) search.set('projectId', params.projectId);
  if (params.agencyLineId) search.set('agencyLineId', params.agencyLineId);
  if (params.agencyLineItemId) {
    search.set('agencyLineItemId', params.agencyLineItemId);
  }
  if (params.page) search.set('page', String(params.page));
  if (params.pageSize != null) search.set('pageSize', String(params.pageSize));
  if (params.includeCatalogs === false) {
    search.set('includeCatalogs', 'false');
  }
  if (params.dimension && params.dimension !== 'item') {
    search.set('dimension', params.dimension);
  }
  return search.toString();
}

/** 读取已写入 Doris 的项目日报。 */
export function getProjectDailyReportApi(params: ProjectDailyReportQuery) {
  return request<ProjectDailyReportResult>(
    `/v1/project-daily-reports?${queryString(params)}`,
  );
}

export function getProjectDailyReportSyncApi() {
  return request<ProjectDailyReportSyncStatus>('/v1/project-daily-reports/sync');
}

export function startProjectDailyReportSyncApi() {
  return request<ProjectDailyReportSyncStatus>(
    '/v1/project-daily-reports/sync',
    { method: 'POST' },
  );
}

/** 手动导入 CMS / F9 导出的 Excel 或 zip，不要带 Content-Type，交给浏览器写 multipart。 */
export function importProjectDailyReportApi(file: File) {
  const body = new FormData();
  body.append('file', file);
  return request<ProjectDailyReportImportResult>(
    '/v1/project-daily-reports/import',
    { body, method: 'POST' },
  );
}