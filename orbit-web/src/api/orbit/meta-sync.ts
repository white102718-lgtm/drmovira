/** 采集口径和进度独立于广告数值查询；未知或未发布不能充当成功。 */
import { referenceRequest, ReferenceApiError, writeHeaders } from './references'
export interface MetaSyncPolicyValue {
  profile_id: string
  adapter_version: string
  scheduler_enabled: boolean
  revision: number
}
export interface MetaSyncChoice {
  profile_id: string
  profile_version: string
  adapter_version: string
}
export interface MetaSyncSettings {
  profile_id: string | null
  adapter_version: string | null
  scheduler_enabled: boolean
  revision: number
  csrf_token: string
  choices: MetaSyncChoice[]
}
export type MetaSyncState =
  | 'INVENTORY'
  | 'CAPTURING'
  | 'SEALED'
  | 'PUBLISHED'
  | 'RETRY_WAIT'
  | 'WAIT_REPORT'
  | 'FAILED'
export interface MetaSyncJob {
  id: string
  state: MetaSyncState
  updated_at: string
  last_error: string | null
  attempts: number
  next_run_at: string
  page_number: number
  date_from: string
  date_to: string
  profile_id: string
  profile_version: string
  adapter_version: string
}
export interface MetaSyncStatusRow {
  account_id: string
  account_name: string
  latest_job: MetaSyncJob | null
  last_published_at: string | null
}
export interface MetaSyncStatusPage {
  items: MetaSyncStatusRow[]
  next_cursor: string | null
  scope_version: number
  data_as_of: string
}
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const text = (v: unknown, n: number): v is string =>
  typeof v === 'string' && v.length > 0 && v.length <= n
const int = (v: unknown, low = 0, high = Number.MAX_SAFE_INTEGER): v is number =>
  Number.isSafeInteger(v) && Number(v) >= low && Number(v) <= high
const stamp = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 19) === v.slice(0, 19)
const date = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 10) === v
function invalid(): never {
  throw new ReferenceApiError(502, 'INVALID_META_SYNC_RESPONSE', '采集响应无效，请重新读取')
}
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    Object.keys(value).length !== keys.length ||
    keys.some((k) => !Object.hasOwn(value, k))
  )
    invalid()
  return value as Record<string, unknown>
}
export function parseMetaSyncSettings(value: unknown): MetaSyncSettings {
  const p = object(value, [
    'profile_id',
    'adapter_version',
    'scheduler_enabled',
    'revision',
    'csrf_token',
    'choices',
  ])
  if (
    (p.profile_id !== null && !uuid(p.profile_id)) ||
    (p.adapter_version !== null && !text(p.adapter_version, 64)) ||
    typeof p.scheduler_enabled !== 'boolean' ||
    !int(p.revision) ||
    !text(p.csrf_token, 4096) ||
    !Array.isArray(p.choices) ||
    p.choices.length > 200
  )
    invalid()
  if (
    p.revision === 0
      ? p.profile_id !== null || p.adapter_version !== null || p.scheduler_enabled
      : !p.profile_id || !p.adapter_version
  )
    invalid()
  const seen = new Set<string>()
  for (const item of p.choices) {
    const c = object(item, ['profile_id', 'profile_version', 'adapter_version'])
    if (!uuid(c.profile_id) || !text(c.profile_version, 64) || !text(c.adapter_version, 64))
      invalid()
    const key = JSON.stringify([c.profile_id, c.adapter_version])
    if (seen.has(key)) invalid()
    seen.add(key)
  }
  return p as unknown as MetaSyncSettings
}
export function parseMetaSyncStatus(value: unknown): MetaSyncStatusPage {
  const p = object(value, ['items', 'next_cursor', 'scope_version', 'data_as_of'])
  if (
    !Array.isArray(p.items) ||
    p.items.length > 50 ||
    (p.next_cursor !== null && !text(p.next_cursor, 2048)) ||
    !int(p.scope_version, 1) ||
    !stamp(p.data_as_of)
  )
    invalid()
  const seen = new Set<string>()
  for (const value of p.items) {
    const row = object(value, ['account_id', 'account_name', 'latest_job', 'last_published_at'])
    if (
      !uuid(row.account_id) ||
      seen.has(row.account_id) ||
      !text(row.account_name, 10000) ||
      (row.last_published_at !== null && !stamp(row.last_published_at))
    )
      invalid()
    seen.add(row.account_id)
    if (row.latest_job !== null) {
      const j = object(row.latest_job, [
        'id',
        'state',
        'updated_at',
        'last_error',
        'attempts',
        'next_run_at',
        'page_number',
        'date_from',
        'date_to',
        'profile_id',
        'profile_version',
        'adapter_version',
      ])
      if (
        !uuid(j.id) ||
        ![
          'INVENTORY',
          'CAPTURING',
          'SEALED',
          'PUBLISHED',
          'RETRY_WAIT',
          'WAIT_REPORT',
          'FAILED',
        ].includes(String(j.state)) ||
        !stamp(j.updated_at) ||
        !stamp(j.next_run_at) ||
        !int(j.attempts, 0, 3) ||
        !int(j.page_number) ||
        !date(j.date_from) ||
        !date(j.date_to) ||
        j.date_to < j.date_from ||
        !uuid(j.profile_id) ||
        !text(j.profile_version, 64) ||
        !text(j.adapter_version, 64) ||
        (j.last_error !== null &&
          ![
            'META_RATE_LIMITED',
            'META_TRANSIENT_FAILURE',
            'META_AUTH_FAILED',
            'META_READ_FORBIDDEN',
            'META_RESPONSE_INVALID',
            'META_COLLECTION_UNVERIFIED',
          ].includes(String(j.last_error)))
      )
        invalid()
    }
  }
  return p as unknown as MetaSyncStatusPage
}
export const metaSyncApi = {
  settings: async (signal?: AbortSignal, connectionId?: string) =>
    parseMetaSyncSettings(await referenceRequest(policyPath(connectionId), { signal })),
  save: async (value: MetaSyncPolicyValue, csrf: string, key: string, connectionId?: string) => {
    const result = object(
      await referenceRequest(policyPath(connectionId), {
        method: 'PUT',
        headers: { ...writeHeaders(csrf, key), 'If-Match': `"${value.revision}"` },
        body: JSON.stringify(value),
      }),
      ['profile_id', 'adapter_version', 'scheduler_enabled', 'revision'],
    )
    if (
      result.profile_id !== value.profile_id ||
      result.adapter_version !== value.adapter_version ||
      result.scheduler_enabled !== value.scheduler_enabled ||
      result.revision !== value.revision + 1
    )
      invalid()
    return result as unknown as MetaSyncPolicyValue
  },
  status: async (cursor: string | null = null, accountId?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams()
    if (cursor) query.set('cursor', cursor)
    if (accountId) query.set('account_id', accountId)
    return parseMetaSyncStatus(
      await referenceRequest('/metrics/sync-status' + (query.size ? '?' + query : ''), { signal }),
    )
  },
}

function policyPath(connectionId?: string) {
  if (connectionId === undefined) return '/integrations/meta/sync-settings'
  if (!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(connectionId)) invalid()
  return `/integrations/meta/connections/${connectionId}/sync-settings`
}
