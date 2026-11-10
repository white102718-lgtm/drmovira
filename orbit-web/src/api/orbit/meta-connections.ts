/** Meta连接只显示脱敏状态；授权URL仅在内存短期保存，不保存Token。 */
import { referenceRequest, ReferenceApiError, writeHeaders } from './references'
import { ensureMetaBrowserSession } from './authentication'
import type { AccountImportBatch } from './accounts'
export interface MetaAutoImportBatch {
  id: string
  state: AccountImportBatch['state']
  total: number
  success_count: number
  failed_count: number
  duplicate_count: number
}
export interface MetaAutoImport extends Omit<MetaAutoImportBatch, 'state'> {
  state: 'QUEUED' | 'DISCOVERING' | 'IMPORTING' | 'SUCCEEDED' | 'PARTIAL_SUCCESS' | 'FAILED'
  error_code: string | null
  batches: MetaAutoImportBatch[]
}
export interface MetaConnection {
  auto_import?: MetaAutoImport | null
  id: string
  kind: 'LOGIN' | 'BM'
  status: 'ACTIVE' | 'REAUTH_REQUIRED' | 'DISCONNECTED'
  revision: number
  principal_id: string | null
  expires_at: string | null
  data_access_expires_at: string | null
  updated_at: string
}
export interface MetaApplicationChoice {
  id: string
  name: string
  app_id: string
  revision: number
}
export interface MetaCapabilities {
  applications?: MetaApplicationChoice[]
  csrf_token: string
  configured: boolean
}
export interface MetaAuthorization {
  authorize_url: string
  expires_at: string
}
export interface MetaAccountCandidate {
  external_id: string
  name: string | null
  currency: string | null
  timezone: string | null
}
export interface MetaAccountSelection {
  account_ids: string[]
  operator_user_id: string
  owner_team_id: string
  vendor_id: string
  channel_id: string | null
}
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const stamp = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 19) === v.slice(0, 19)
const text = (v: unknown, n: number): v is string =>
  typeof v === 'string' && v.length > 0 && v.length <= n
function invalid(): never {
  throw new ReferenceApiError(502, 'INVALID_META_RESPONSE', 'Meta连接响应无效，请重新读取')
}
function object(
  value: unknown,
  fields: string[],
  optional: string[] = [],
): Record<string, unknown> {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    fields.some((k) => !Object.hasOwn(value, k)) ||
    Object.keys(value).some((k) => ![...fields, ...optional].includes(k))
  )
    invalid()
  return value as Record<string, unknown>
}
export function parseConnections(value: unknown): { items: MetaConnection[] } {
  const p = object(value, ['items'])
  if (!Array.isArray(p.items) || p.items.length > 10000) invalid()
  const seen = new Set<string>()
  for (const item of p.items) {
    const r = object(
      item,
      [
        'id',
        'kind',
        'status',
        'revision',
        'principal_id',
        'expires_at',
        'data_access_expires_at',
        'updated_at',
      ],
      ['auto_import'],
    )
    if (
      !uuid(r.id) ||
      seen.has(r.id) ||
      !['LOGIN', 'BM'].includes(String(r.kind)) ||
      !['ACTIVE', 'REAUTH_REQUIRED', 'DISCONNECTED'].includes(String(r.status)) ||
      !Number.isSafeInteger(r.revision) ||
      Number(r.revision) < 1 ||
      (r.principal_id !== null && !text(r.principal_id, 128)) ||
      (r.expires_at !== null && !stamp(r.expires_at)) ||
      (r.data_access_expires_at !== null && !stamp(r.data_access_expires_at)) ||
      !stamp(r.updated_at)
    )
      invalid()
    if (r.auto_import != null) {
      const job = object(r.auto_import, [
        'id',
        'state',
        'error_code',
        'total',
        'success_count',
        'failed_count',
        'duplicate_count',
        'batches',
      ])
      if (
        !['QUEUED', 'DISCOVERING', 'IMPORTING', 'SUCCEEDED', 'PARTIAL_SUCCESS', 'FAILED'].includes(
          String(job.state),
        ) ||
        (job.error_code !== null && !text(job.error_code, 128)) ||
        !Array.isArray(job.batches)
      )
        invalid()
      for (const entry of [job, ...job.batches]) {
        if (
          !entry ||
          typeof entry !== 'object' ||
          !uuid(entry.id) ||
          ['total', 'success_count', 'failed_count', 'duplicate_count'].some(
            (k) => !Number.isSafeInteger(entry[k]) || Number(entry[k]) < 0,
          )
        )
          invalid()
      }
      for (const batch of job.batches) {
        object(batch, ['id', 'state', 'total', 'success_count', 'failed_count', 'duplicate_count'])
        if (
          !['QUEUED', 'RUNNING', 'SUCCEEDED', 'PARTIAL_SUCCESS', 'FAILED'].includes(
            String(batch.state),
          )
        )
          invalid()
      }
    }
    seen.add(r.id)
  }
  return p as unknown as { items: MetaConnection[] }
}
export function parseMetaCapabilities(value: unknown): MetaCapabilities {
  const p = object(value, ['csrf_token', 'configured'], ['applications'])
  if (!text(p.csrf_token, 4096) || typeof p.configured !== 'boolean') invalid()
  if (p.applications !== undefined) {
    if (!Array.isArray(p.applications) || p.applications.length > 200) invalid()
    const seen = new Set<string>()
    for (const candidate of p.applications) {
      const app = object(candidate, ['id', 'name', 'app_id', 'revision'])
      if (
        !uuid(app.id) ||
        seen.has(app.id) ||
        !text(app.name, 100) ||
        typeof app.app_id !== 'string' ||
        !/^\d{1,64}$/.test(app.app_id) ||
        !Number.isSafeInteger(app.revision) ||
        Number(app.revision) < 1
      )
        invalid()
      seen.add(app.id)
    }
  }
  return p as unknown as MetaCapabilities
}
export function parseAuthorization(value: unknown): MetaAuthorization {
  const p = object(value, ['authorize_url', 'expires_at'])
  if (!text(p.authorize_url, 8192) || !stamp(p.expires_at)) invalid()
  let url: URL
  try {
    url = new URL(p.authorize_url)
  } catch {
    invalid()
  }
  if (
    url.protocol !== 'https:' ||
    url.host !== 'www.facebook.com' ||
    url.username ||
    url.password ||
    url.hash ||
    !/^\/v\d{1,3}\.\d{1,2}\/dialog\/oauth$/.test(url.pathname)
  )
    invalid()
  return p as unknown as MetaAuthorization
}
export function parseMetaAccounts(value: unknown): {
  items: MetaAccountCandidate[]
  next_cursor: string | null
} {
  const p = object(value, ['items', 'next_cursor'], ['connection_revision'])
  if (
    !Array.isArray(p.items) ||
    p.items.length > 10000 ||
    (p.next_cursor !== null && !text(p.next_cursor, 2048))
  )
    invalid()
  const ids = new Set<string>()
  for (const item of p.items) {
    const r = object(item, ['external_id', 'name', 'currency', 'timezone'])
    if (
      typeof r.external_id !== 'string' ||
      !/^\d{1,64}$/.test(r.external_id) ||
      ids.has(r.external_id) ||
      (r.name !== null && !text(r.name, 4096)) ||
      (r.currency !== null && (typeof r.currency !== 'string' || !/^[A-Z]{3}$/.test(r.currency))) ||
      (r.timezone !== null && !text(r.timezone, 128))
    )
      invalid()
    ids.add(r.external_id)
  }
  return p as unknown as { items: MetaAccountCandidate[]; next_cursor: string | null }
}
function parseBatch(value: unknown): AccountImportBatch {
  if (!value || typeof value !== 'object') invalid()
  const p = value as Record<string, unknown>
  if (
    !uuid(p.id) ||
    !Number.isSafeInteger(p.revision) ||
    Number(p.revision) < 1 ||
    !['QUEUED', 'RUNNING', 'SUCCEEDED', 'PARTIAL_SUCCESS', 'FAILED'].includes(String(p.state)) ||
    !Array.isArray(p.rows) ||
    p.rows.length > 500 ||
    (p.vendor_id !== null && !uuid(p.vendor_id)) ||
    ['total', 'success_count', 'failed_count', 'duplicate_count'].some(
      (k) => !Number.isSafeInteger(p[k]) || Number(p[k]) < 0,
    ) ||
    (p.next_cursor !== null && !text(p.next_cursor, 2048))
  )
    invalid()
  return value as AccountImportBatch
}
const root = '/integrations/meta'
export const metaConnectionApi = {
  capabilities: async (signal?: AbortSignal) => {
    await ensureMetaBrowserSession()
    return parseMetaCapabilities(await referenceRequest(root + '/capabilities', { signal }))
  },
  list: async (signal?: AbortSignal) =>
    parseConnections(await referenceRequest(root + '/connections', { signal })),
  authorize: async (csrf: string, key: string, id?: string, applicationId?: string) =>
    parseAuthorization(
      await referenceRequest(
        root + (id ? `/connections/${encodeURIComponent(id)}` : '') + '/authorization-sessions',
        {
          method: 'POST',
          headers: writeHeaders(csrf, key),
          body: JSON.stringify({
            return_to: '/orbit/accounts',
            ...(!id && applicationId ? { application_id: applicationId } : {}),
          }),
        },
      ),
    ),
  disconnect: async (id: string, revision: number, reason: string, csrf: string, key: string) => {
    const p = object(
      await referenceRequest(root + `/connections/${encodeURIComponent(id)}/disconnect`, {
        method: 'POST',
        headers: writeHeaders(csrf, key),
        body: JSON.stringify({ revision, reason }),
      }),
      ['id', 'status', 'revision'],
    )
    if (p.id !== id || p.status !== 'DISCONNECTED' || p.revision !== revision + 1) invalid()
    return p
  },
  accounts: async (id: string, signal?: AbortSignal, cursor?: string) =>
    parseMetaAccounts(
      await referenceRequest(
        root +
          `/connections/${encodeURIComponent(id)}/accounts` +
          (cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''),
        { signal },
      ),
    ),
  select: async (id: string, value: MetaAccountSelection, csrf: string, key: string) =>
    parseBatch(
      await referenceRequest(root + `/connections/${encodeURIComponent(id)}/accounts`, {
        method: 'POST',
        headers: writeHeaders(csrf, key),
        body: JSON.stringify(value),
      }),
    ),
  connectBm: async (id: string, revision: number, csrf: string, key: string) => {
    const p = object(
      await referenceRequest(root + '/bm-connections', {
        method: 'POST',
        headers: writeHeaders(csrf, key),
        body: JSON.stringify({ configuration_id: id, configuration_revision: revision }),
      }),
      ['id', 'revision', 'status', 'kind', 'accessible_account_count'],
    )
    if (
      !uuid(p.id) ||
      !Number.isSafeInteger(p.revision) ||
      Number(p.revision) < 1 ||
      p.status !== 'ACTIVE' ||
      p.kind !== 'BM' ||
      !Number.isSafeInteger(p.accessible_account_count) ||
      Number(p.accessible_account_count) < 0 ||
      Number(p.accessible_account_count) > 10000
    )
      invalid()
    return p as unknown as {
      id: string
      revision: number
      status: 'ACTIVE'
      kind: 'BM'
      accessible_account_count: number
    }
  },
  navigate: (authorization: MetaAuthorization) => {
    parseAuthorization(authorization)
    if (Date.parse(authorization.expires_at) <= Date.now())
      throw new ReferenceApiError(410, 'AUTHORIZATION_EXPIRED', '授权链接已过期，请重新发起')
    window.location.assign(authorization.authorize_url)
  },
}
