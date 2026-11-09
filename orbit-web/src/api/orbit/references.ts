import { orbitAuthHeaders, orbitCredentials } from './authentication'

export type ReferenceKind = 'PRODUCT' | 'BUSINESS_AGENT' | 'VENDOR'
export interface Ownership {
  owner_team_id: string
  data_owner_user_ids: string[]
}
export interface ReferenceInput extends Ownership {
  id: string
  kind: ReferenceKind
  name: string
  availability: 'AVAILABLE' | 'UNAVAILABLE'
  source_key: string
  allowed_agent_ids?: string[]
}
export interface ReferenceRecord {
  value: ReferenceInput
  revision: number
  catalog_revision: number
  updated_at: string
}
export interface ReferencePage {
  items: ReferenceRecord[]
  next_cursor: string | null
  catalog_revision: number
  scope_version: number
}
export interface ReferenceImportInput {
  kind: ReferenceKind
  source: string
  reason: string
  base_catalog_revision: number
  items: ReferenceInput[]
}
export interface ReferenceIssue {
  row: number
  code: string
  message: string
}
export interface ReferenceResult {
  id: string
  revision: number
  state: 'VALIDATED' | 'REJECTED' | 'COMMITTED' | 'EXPIRED'
  base_catalog_revision: number
  expires_at: string
  issues: ReferenceIssue[]
  created_count: number
  updated_count: number
}
export interface ReferenceDifference {
  row: number
  id: string
  action: 'CREATE' | 'UPDATE'
  before: ReferenceInput | null
  after: ReferenceInput
}

export class ReferenceApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

/** 使用内存中的原认证或Cookie会话，不通过会缓存正文的通用重复提交拦截器。 */
export async function referenceRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1${path}`, {
      ...init,
      credentials: orbitCredentials(),
      cache: 'no-store',
      headers: orbitAuthHeaders({ 'Content-Type': 'application/json', ...init.headers }),
    })
  } catch {
    throw new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '网络中断；请使用重试保留本次幂等键')
  }
  let result
  try {
    result = await response.json()
  } catch {
    throw new ReferenceApiError(502, 'INVALID_RESPONSE', '服务响应无效，请稍后重试')
  }
  if (!response.ok || (typeof result?.code === 'number' && result.code !== 200)) {
    throw new ReferenceApiError(
      response.status,
      result?.code ?? 'REQUEST_FAILED',
      result?.message ?? result?.msg ?? '请求失败',
    )
  }
  return result as T
}
export function writeHeaders(csrf: string, key: string, revision?: number): Record<string, string> {
  return {
    'X-CSRF-Token': csrf,
    'Idempotency-Key': key,
    ...(revision ? { 'If-Match': `"${revision}"` } : {}),
  }
}
export const referenceApi = {
  capabilities: () =>
    referenceRequest<{ catalog_revision: number; csrf_token: string }>(
      '/reference-catalog-imports/capabilities',
    ),
  list: (kind: ReferenceKind, query = new URLSearchParams()) =>
    referenceRequest<ReferencePage>(`/reference-catalogs/${kind}?${query}`),
  preview: (value: ReferenceImportInput, csrf: string, key: string) =>
    referenceRequest<ReferenceResult>('/reference-catalog-imports', {
      method: 'POST',
      headers: writeHeaders(csrf, key),
      body: JSON.stringify(value),
    }),
  get: (id: string) =>
    referenceRequest<ReferenceResult>(`/reference-catalog-imports/${encodeURIComponent(id)}`),
  differences: (id: string) =>
    referenceRequest<{ items: ReferenceDifference[]; issues: ReferenceIssue[]; state: string }>(
      `/reference-catalog-imports/${encodeURIComponent(id)}/differences`,
    ),
  commit: (value: ReferenceResult, csrf: string, key: string) =>
    referenceRequest<ReferenceResult>(
      `/reference-catalog-imports/${encodeURIComponent(value.id)}/commit`,
      { method: 'POST', headers: writeHeaders(csrf, key, value.revision) },
    ),
}
