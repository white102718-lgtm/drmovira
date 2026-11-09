/** 投放账户选择的独立严格SDK；不解游标、不拉全量ID，不替代服务端实时归属检查。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { LaunchValidationError, parsePlanHttpFieldError } from './launch-validation'
import type { ScopeFilter, ScopeMemberPage, ScopeRequest, ScopeSnapshot } from './scopes'

export type { ScopeFilter, ScopeMemberPage, ScopeRequest, ScopeSnapshot }
export interface ScopeMutation {
  csrf_token: string
  idempotency_key: string
}
export interface AccountCandidate {
  id: string
  external_id: string
  name: string
  ownership: { owner_user_id: string; owner_team_id: string }
  currency: string
  auth_status: 'AUTHORIZED' | 'EXPIRED' | 'REVOKED' | 'UNKNOWN'
  account_status: 'ACTIVE' | 'DISABLED' | 'UNKNOWN'
}
export interface CandidatePage {
  items: AccountCandidate[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export type PlanAccountSelection =
  | { kind: 'IDS'; account_ids: string[]; snapshot: null }
  | { kind: 'SNAPSHOT'; account_ids: []; snapshot: ScopeSnapshot }
const record = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)
const exact = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  record(v) && Object.keys(v).length === keys.length && keys.every((k) => Object.hasOwn(v, k))
const str = (v: unknown, max: number, min = 1): v is string =>
  typeof v === 'string' && [...v].length >= min && [...v].length <= max
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v)
const safe = (v: unknown, min = 1, max = Number.MAX_SAFE_INTEGER): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v >= min && v <= max
function date(v: unknown): v is string {
  if (typeof v !== 'string') return false
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|([+-])(\d{2}):(\d{2}))$/.exec(v)
  return (
    !!match &&
    +match[2] >= 1 &&
    +match[2] <= 12 &&
    +match[3] >= 1 &&
    +match[3] <= new Date(Date.UTC(+match[1], +match[2], 0)).getUTCDate() &&
    +match[4] <= 23 &&
    +match[5] <= 59 &&
    +match[6] <= 59 &&
    +(match[8] ?? 0) <= 23 &&
    +(match[9] ?? 0) <= 59 &&
    Number.isFinite(Date.parse(v))
  )
}
const cursor = (v: unknown) => v === null || str(v, 2048)
function bad(request = false): never {
  throw new LaunchValidationError(
    request ? 422 : 502,
    request ? 'FIELD_VALIDATION_FAILED' : 'INVALID_RESPONSE',
    request ? '账户范围参数不符合合同' : '账户范围响应不符合合同，请重新读取',
  )
}
export function parseScopeSnapshot(v: unknown): ScopeSnapshot {
  if (
    !exact(v, ['id', 'count', 'scope_version', 'hash', 'created_at']) ||
    !uuid(v.id) ||
    !safe(v.count, 0, 2147483647) ||
    !safe(v.scope_version) ||
    !str(v.hash, 64, 64) ||
    !date(v.created_at)
  )
    bad()
  return v as unknown as ScopeSnapshot
}
export function parseScopeMembers(v: unknown): ScopeMemberPage {
  if (
    !exact(v, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(v.items) ||
    v.items.length > 200 ||
    !cursor(v.next_cursor) ||
    !date(v.data_as_of) ||
    !safe(v.scope_version)
  )
    bad()
  const seen = new Set<string>()
  for (const item of v.items) {
    if (
      !exact(item, ['account_id', 'external_id', 'name']) ||
      !uuid(item.account_id) ||
      !str(item.external_id, 64) ||
      !/^\d+$/.test(item.external_id) ||
      !str(item.name, 10000) ||
      seen.has(item.account_id.toLowerCase())
    )
      bad()
    seen.add(item.account_id.toLowerCase())
  }
  return v as unknown as ScopeMemberPage
}
/** 仅投影选账户所需字段；账户完整合同的其余真实观察字段由账户模块负责，不伪造观察值。 */
export function parseCandidatePage(v: unknown): CandidatePage {
  if (
    !exact(v, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(v.items) ||
    v.items.length > 200 ||
    !cursor(v.next_cursor) ||
    !date(v.data_as_of) ||
    !safe(v.scope_version)
  )
    bad()
  const seen = new Set<string>()
  const items = v.items.map((item) => {
    if (
      !record(item) ||
      !uuid(item.id) ||
      !str(item.external_id, 64) ||
      !/^\d+$/.test(item.external_id) ||
      !str(item.name, 10000) ||
      !exact(item.ownership, ['owner_user_id', 'owner_team_id']) ||
      !uuid(item.ownership.owner_user_id) ||
      !uuid(item.ownership.owner_team_id) ||
      typeof item.currency !== 'string' ||
      !/^[A-Z]{3}$/.test(item.currency) ||
      !['AUTHORIZED', 'EXPIRED', 'REVOKED', 'UNKNOWN'].includes(String(item.auth_status)) ||
      !['ACTIVE', 'DISABLED', 'UNKNOWN'].includes(String(item.account_status)) ||
      seen.has(item.id.toLowerCase())
    )
      bad()
    seen.add(item.id.toLowerCase())
    return {
      id: item.id,
      external_id: item.external_id,
      name: item.name,
      ownership: item.ownership,
      currency: item.currency,
      auth_status: item.auth_status,
      account_status: item.account_status,
    } as AccountCandidate
  })
  return {
    items,
    next_cursor: v.next_cursor as string | null,
    data_as_of: v.data_as_of,
    scope_version: v.scope_version,
  }
}
export function checkScopeRequest(v: unknown): ScopeRequest {
  if (
    !exact(v, ['mode', 'account_ids', 'filter']) ||
    !Array.isArray(v.account_ids) ||
    v.account_ids.length > 50000 ||
    !v.account_ids.every(uuid) ||
    new Set(v.account_ids.map((x) => x.toLowerCase())).size !== v.account_ids.length
  )
    bad(true)
  if (v.mode === 'IDS') {
    if (!v.account_ids.length || v.filter !== null) bad(true)
  } else if (v.mode === 'FILTER') {
    const f = v.filter
    if (
      v.account_ids.length ||
      !exact(f, ['q', 'status', 'auth_status', 'operator_user_id', 'vendor_id']) ||
      !str(f.q, 100, 0) ||
      !(f.status === null || ['ACTIVE', 'DISABLED', 'UNKNOWN'].includes(String(f.status))) ||
      !(
        f.auth_status === null ||
        ['AUTHORIZED', 'EXPIRED', 'REVOKED', 'UNKNOWN'].includes(String(f.auth_status))
      ) ||
      !(f.operator_user_id === null || uuid(f.operator_user_id)) ||
      !(f.vendor_id === null || uuid(f.vendor_id))
    )
      bad(true)
  } else bad(true)
  // 已逐字段限制为JSON值；避免对调用方Vue代理structuredClone而产生DataCloneError。
  return JSON.parse(JSON.stringify(v)) as ScopeRequest
}
function pageQuery(q: string, size: number, token: string | null) {
  if (!str(q, 100, 0) || ![20, 50, 100, 200].includes(size) || !cursor(token)) bad(true)
  const query = new URLSearchParams({ q, page_size: String(size) })
  if (token !== null) query.set('cursor', token)
  return query
}
async function request<T>(
  path: string,
  parse: (v: unknown) => T,
  signal?: AbortSignal,
  mutation?: { value: ScopeRequest; context: ScopeMutation },
): Promise<T> {
  signal?.throwIfAborted()
  const headers = orbitAuthHeaders({
    'Content-Type': 'application/json',
    ...(mutation
      ? {
          'X-CSRF-Token': mutation.context.csrf_token,
          'Idempotency-Key': mutation.context.idempotency_key,
        }
      : {}),
  })
  if (
    mutation &&
    (!str(mutation.context.csrf_token, 4096) ||
      !/^[\x20-\x7e]{16,128}$/.test(mutation.context.idempotency_key) ||
      new Headers(headers).get('X-CSRF-Token') !== mutation.context.csrf_token)
  )
    throw new LaunchValidationError(
      409,
      'SESSION_CONTEXT_CHANGED',
      '会话已变化，请确认原冻结意图后恢复',
    )
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), 15000)
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  try {
    const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1${path}`, {
      method: mutation ? 'POST' : 'GET',
      headers,
      credentials: orbitCredentials(),
      cache: 'no-store',
      signal: controller.signal,
      ...(mutation ? { body: JSON.stringify(mutation.value) } : {}),
    })
    const data: unknown = await response.json()
    if (response.status !== (mutation ? 201 : 200)) {
      if (
        !exact(data, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
        !str(data.code, 64) ||
        !str(data.message, 1000) ||
        !Array.isArray(data.field_errors) ||
        data.field_errors.length > 100 ||
        typeof data.retryable !== 'boolean' ||
        !uuid(data.request_id)
      )
        bad()
      throw new LaunchValidationError(
        response.status,
        data.code,
        data.message,
        data.field_errors.map(parsePlanHttpFieldError),
        data.retryable,
        data.request_id,
        false,
        response.status,
      )
    }
    return parse(data)
  } catch (error) {
    if (
      error instanceof LaunchValidationError &&
      (error.code !== 'INVALID_RESPONSE' || error.http_status !== null)
    )
      throw error
    if (!mutation && signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    throw new LaunchValidationError(
      0,
      mutation ? 'SCOPE_RESULT_UNKNOWN' : 'SCOPE_READ_FAILED',
      mutation ? '冻结结果未知，请使用原意图恢复，勿另建范围' : '读取失败，请重试',
      [],
      true,
      null,
      !!mutation,
    )
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', cancel)
  }
}
export const launchAccountScopesApi = {
  capabilities: (signal?: AbortSignal) =>
    request(
      '/scope-snapshots/capabilities',
      (v) => {
        if (
          !exact(v, ['csrf_token', 'max_members', 'max_plan_accounts']) ||
          !str(v.csrf_token, 4096) ||
          v.max_members !== 50000 ||
          v.max_plan_accounts !== 500
        )
          bad()
        return v as { csrf_token: string; max_members: number; max_plan_accounts: number }
      },
      signal,
    ),
  create: (value: ScopeRequest, context: ScopeMutation, signal?: AbortSignal) =>
    request('/scope-snapshots', parseScopeSnapshot, signal, {
      value: checkScopeRequest(value),
      context: { ...context },
    }),
  members: (id: string, q: string, size: number, token: string | null, signal?: AbortSignal) => {
    if (!uuid(id)) bad(true)
    return request(
      `/scope-snapshots/${encodeURIComponent(id)}/members?${pageQuery(q, size, token)}`,
      parseScopeMembers,
      signal,
    )
  },
  candidates: (filter: ScopeFilter, size: number, token: string | null, signal?: AbortSignal) => {
    checkScopeRequest({ mode: 'FILTER', account_ids: [], filter })
    const query = pageQuery(filter.q, size, token)
    for (const key of ['status', 'auth_status', 'operator_user_id', 'vendor_id'] as const)
      if (filter[key] !== null) query.set(key, filter[key])
    return request(`/accounts?${query}`, parseCandidatePage, signal)
  },
}
