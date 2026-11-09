/** 规则专属账户范围SDK；只用rules辅助端点，不借账户/投放权限、不将当前页拼成全选。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { checkScopeRequest, parseScopeMembers, parseScopeSnapshot } from './launch-account-scopes'
import type { ScopeFilter, ScopeMemberPage, ScopeRequest, ScopeSnapshot } from './scopes'
import { parsePlanHttpFieldError } from './launch-validation'
import { RuleApiError, type RuleMutation, type RuleVersionMutation } from './rules'
import type { RuleEditorTarget } from './rule-editor'

export type RuleEditorAccountQuery = RuleEditorTarget & {
  owner_user_id: string
  owner_team_id: string
  q?: string
  status?: NonNullable<ScopeFilter['status']>
  auth_status?: NonNullable<ScopeFilter['auth_status']>
  operator_user_id?: string
  vendor_id?: string
  page_size?: 20 | 50 | 100 | 200
  cursor?: string
}
export interface RuleEditorMemberQuery {
  q?: string
  page_size?: 20 | 50 | 100 | 200
  cursor?: string
}
export type RuleEditorScopeWrite =
  | {
      action: 'CREATE'
      rule_id: null
      ownership: { owner_user_id: string; owner_team_id: string }
      selection: ScopeRequest
    }
  | {
      action: 'UPDATE'
      rule_id: string
      ownership: { owner_user_id: string; owner_team_id: string }
      selection: ScopeRequest
    }
export interface FrozenRuleEditorScopeIntent {
  readonly body: RuleEditorScopeWrite
  readonly auth: RuleMutation | RuleVersionMutation
}
export class RuleEditorScopeApiError extends RuleApiError {}
export type { ScopeFilter, ScopeMemberPage, ScopeRequest, ScopeSnapshot }
const record = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)
const exact = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  record(v) && Object.keys(v).length === keys.length && keys.every((k) => Object.hasOwn(v, k))
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v)
const text = (v: unknown, max: number, min = 1): v is string =>
  typeof v === 'string' &&
  [...v].length >= min &&
  [...v].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(v)
function invalid(path = '/', response = false, code = 'FIELD_INVALID'): never {
  throw new RuleEditorScopeApiError(
    response ? 502 : 422,
    response ? 'INVALID_RESPONSE' : code,
    response ? '规则账户范围响应不符合合同' : '规则账户范围参数无效',
    response
      ? []
      : [
          {
            path,
            code,
            message: code === 'DUPLICATE_VALUE' ? '不能重复选择同一账户' : '请检查原范围字段及组合',
            constraint: null,
          },
        ],
  )
}
function q(value: unknown, members = false): string {
  if (typeof value !== 'string' || /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(value)) invalid('/q')
  const normalized = value.trim().normalize('NFC')
  if ([...normalized].length > 100 || (members && value !== '' && !normalized)) invalid('/q')
  return normalized
}
function pagination(value: Record<string, unknown>, result: URLSearchParams) {
  if (value.page_size !== undefined) {
    if (typeof value.page_size !== 'number' || ![20, 50, 100, 200].includes(value.page_size))
      invalid('/page_size')
    result.set('page_size', String(value.page_size))
  }
  if (value.cursor !== undefined) {
    if (!text(value.cursor, 2048)) invalid('/cursor')
    result.set('cursor', value.cursor)
  }
}
function accountsQuery(value: unknown): URLSearchParams {
  const keys = [
    'action',
    'rule_id',
    'owner_user_id',
    'owner_team_id',
    'q',
    'status',
    'auth_status',
    'operator_user_id',
    'vendor_id',
    'page_size',
    'cursor',
  ]
  if (!record(value) || Object.keys(value).some((k) => !keys.includes(k))) invalid()
  const result = new URLSearchParams()
  if (value.action !== 'CREATE' && value.action !== 'UPDATE') invalid('/action')
  result.set('action', value.action)
  if (value.action === 'CREATE') {
    if (Object.hasOwn(value, 'rule_id')) invalid('/rule_id')
  } else {
    if (!uuid(value.rule_id)) invalid('/rule_id')
    result.set('rule_id', value.rule_id.toLowerCase())
  }
  for (const key of ['owner_user_id', 'owner_team_id']) {
    if (!uuid(value[key])) invalid('/' + key)
    result.set(key, value[key].toLowerCase())
  }
  if (value.q !== undefined) result.set('q', q(value.q))
  if (value.status !== undefined) {
    if (
      typeof value.status !== 'string' ||
      !['ACTIVE', 'DISABLED', 'UNKNOWN'].includes(value.status)
    )
      invalid('/status')
    result.set('status', String(value.status))
  }
  if (value.auth_status !== undefined) {
    if (
      typeof value.auth_status !== 'string' ||
      !['AUTHORIZED', 'EXPIRED', 'REVOKED', 'UNKNOWN'].includes(value.auth_status)
    )
      invalid('/auth_status')
    result.set('auth_status', String(value.auth_status))
  }
  for (const key of ['operator_user_id', 'vendor_id']) {
    if (value[key] !== undefined) {
      if (!uuid(value[key])) invalid('/' + key)
      result.set(key, value[key].toLowerCase())
    }
  }
  pagination(value, result)
  return result
}
function membersQuery(value: unknown): URLSearchParams {
  if (!record(value) || Object.keys(value).some((k) => !['q', 'page_size', 'cursor'].includes(k)))
    invalid()
  const result = new URLSearchParams()
  if (value.q !== undefined) result.set('q', q(value.q, true))
  pagination(value, result)
  return result
}
function selection(value: unknown): ScopeRequest {
  if (
    !exact(value, ['mode', 'account_ids', 'filter']) ||
    !Array.isArray(value.account_ids) ||
    value.account_ids.length > 50000
  )
    invalid('/account_ids')
  const seen = new Set<string>()
  for (const [index, item] of value.account_ids.entries()) {
    if (!uuid(item)) invalid(`/account_ids/${index}`)
    const key = item.toLowerCase()
    if (seen.has(key)) invalid(`/account_ids/${index}`, false, 'DUPLICATE_VALUE')
    seen.add(key)
  }
  if (value.mode === 'IDS') {
    if (!value.account_ids.length || value.filter !== null) invalid('/account_ids')
  } else if (value.mode === 'FILTER') {
    if (
      value.account_ids.length ||
      !exact(value.filter, ['q', 'status', 'auth_status', 'operator_user_id', 'vendor_id'])
    )
      invalid('/filter')
  } else invalid('/mode')
  const normalized = {
    ...value,
    filter: record(value.filter) ? { ...value.filter, q: q(value.filter.q) } : value.filter,
  }
  try {
    return checkScopeRequest(normalized)
  } catch {
    return invalid('/selection')
  }
}
export function freezeRuleEditorScopeIntent(
  body: RuleEditorScopeWrite,
  auth: RuleMutation | RuleVersionMutation,
): FrozenRuleEditorScopeIntent {
  if (
    !exact(body, ['action', 'rule_id', 'ownership', 'selection']) ||
    (body.action !== 'CREATE' && body.action !== 'UPDATE') ||
    !exact(body.ownership, ['owner_user_id', 'owner_team_id']) ||
    !uuid(body.ownership.owner_user_id) ||
    !uuid(body.ownership.owner_team_id)
  )
    invalid()
  const updating = body.action === 'UPDATE'
  if (updating ? !uuid(body.rule_id) : body.rule_id !== null) invalid('/rule_id')
  if (
    !exact(
      auth,
      updating ? ['csrf_token', 'idempotency_key', 'if_match'] : ['csrf_token', 'idempotency_key'],
    ) ||
    !text(auth.csrf_token, 255, 16) ||
    typeof auth.idempotency_key !== 'string' ||
    !/^[ -~]{16,128}$/.test(auth.idempotency_key)
  )
    invalid('/headers')
  if (
    updating &&
    (typeof auth.if_match !== 'string' ||
      !/^"[1-9][0-9]*"$/.test(auth.if_match) ||
      auth.if_match.length > 18 ||
      BigInt(auth.if_match.slice(1, -1)) > BigInt(Number.MAX_SAFE_INTEGER))
  )
    invalid('/If-Match')
  const selected = selection(body.selection)
  const copy = {
    action: body.action,
    rule_id: body.rule_id,
    ownership: { ...body.ownership },
    selection: selected,
  } as RuleEditorScopeWrite
  if (new TextEncoder().encode(JSON.stringify(copy)).byteLength > 2_500_000)
    throw new RuleEditorScopeApiError(413, 'BODY_TOO_LARGE', '规则账户冻结请求超过正文上限')
  Object.freeze(copy.ownership)
  Object.freeze(selected.account_ids)
  if (selected.filter) Object.freeze(selected.filter)
  Object.freeze(selected)
  Object.freeze(copy)
  return Object.freeze({
    body: copy,
    auth: Object.freeze({ ...auth }) as RuleMutation | RuleVersionMutation,
  })
}
function utc(value: string): boolean {
  return (
    /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|\+00:00)$/.test(value) &&
    !value.startsWith('0000')
  )
}
export function parseRuleEditorScope(value: unknown): ScopeSnapshot {
  let parsed: ScopeSnapshot
  try {
    parsed = parseScopeSnapshot(value)
  } catch {
    return invalid('/', true)
  }
  if (
    !Number.isSafeInteger(parsed.count) ||
    parsed.count < 1 ||
    parsed.count > 50000 ||
    !/^[a-f0-9]{64}$/.test(parsed.hash) ||
    !utc(parsed.created_at)
  )
    invalid('/', true)
  return parsed
}
export function parseRuleEditorMembers(value: unknown): ScopeMemberPage {
  let parsed: ScopeMemberPage
  try {
    parsed = parseScopeMembers(value)
  } catch {
    return invalid('/', true)
  }
  if (!utc(parsed.data_as_of) || (!parsed.items.length && parsed.next_cursor !== null))
    invalid('/', true)
  return parsed
}

const authContext = () =>
  JSON.stringify([
    orbitCredentials(),
    Object.entries(orbitAuthHeaders()).sort(([a], [b]) => a.localeCompare(b)),
  ])
async function body(response: Response, signal: AbortSignal): Promise<unknown> {
  // 技术响应预算；只读候选最多200项，不接受无界服务端正文。
  const reader = response.body?.getReader()
  if (!reader) invalid()
  const cancel = () => {
    void reader.cancel().catch(() => {
      /* 取消时保留原读取错误。 */
    })
  }
  signal.addEventListener('abort', cancel, { once: true })
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let bytes = 0,
    result = ''
  try {
    for (;;) {
      signal.throwIfAborted()
      const part = await reader.read()
      if (part.done) break
      bytes += part.value.byteLength
      if (bytes > 16 * 1024 * 1024) invalid()
      result += decoder.decode(part.value, { stream: true })
    }
    signal.throwIfAborted()
    result += decoder.decode()
    return JSON.parse(result)
  } finally {
    signal.removeEventListener('abort', cancel)
    try {
      await reader.cancel()
    } catch {
      /* 清理失败不掩盖原响应或取消错误。 */
    } finally {
      reader.releaseLock()
    }
  }
}
async function request<T>(
  path: string,
  parse: (v: unknown) => T,
  signal?: AbortSignal,
  intent?: FrozenRuleEditorScopeIntent,
): Promise<T> {
  signal?.throwIfAborted()
  const started = authContext()
  const supplied = intent
    ? {
        'X-CSRF-Token': intent.auth.csrf_token,
        'Idempotency-Key': intent.auth.idempotency_key,
        ...('if_match' in intent.auth ? { 'If-Match': intent.auth.if_match } : {}),
      }
    : {}
  const headers = orbitAuthHeaders({
    Accept: 'application/json',
    ...(intent ? { 'Content-Type': 'application/json' } : {}),
    ...supplied,
  })
  if (intent && new Headers(headers).get('x-csrf-token') !== intent.auth.csrf_token)
    throw new RuleEditorScopeApiError(
      409,
      'CSRF_CONTEXT_CHANGED',
      '会话已变化，请保留原冻结意图并重新读取',
    )
  const wireBody = intent ? JSON.stringify(intent.body) : undefined
  const controller = new AbortController(),
    abort = () => controller.abort()
  const timer = setTimeout(abort, 15000)
  signal?.addEventListener('abort', abort, { once: true })
  let status = 0
  try {
    const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/rules/${path}`, {
      method: intent ? 'POST' : 'GET',
      headers,
      ...(intent ? { body: wireBody } : {}),
      credentials: orbitCredentials(),
      signal: controller.signal,
      cache: 'no-store',
    })
    status = response.status
    let value: unknown
    try {
      value = await body(response, controller.signal)
    } catch (e) {
      if (controller.signal.aborted) throw e
      throw new RuleEditorScopeApiError(
        502,
        'INVALID_RESPONSE',
        '规则范围来源响应未能确认',
        [],
        false,
        null,
        !!intent,
      )
    }
    controller.signal.throwIfAborted()
    if (started !== authContext())
      throw new RuleEditorScopeApiError(
        409,
        'SESSION_CONTEXT_CHANGED',
        '认证上下文已变化，已丢弃迟到响应',
        [],
        false,
        null,
        !!intent,
      )
    if (!response.ok) {
      if (
        !exact(value, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
        !text(value.code, 64) ||
        !text(value.message, 1000) ||
        !Array.isArray(value.field_errors) ||
        value.field_errors.length > 100 ||
        typeof value.retryable !== 'boolean' ||
        !uuid(value.request_id)
      )
        throw new RuleEditorScopeApiError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则范围来源错误响应不符合合同',
          [],
          false,
          null,
          !!intent,
        )
      let fields
      try {
        fields = value.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleEditorScopeApiError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则范围来源错误响应不符合合同',
          [],
          false,
          null,
          !!intent,
        )
      }
      throw new RuleEditorScopeApiError(
        status,
        value.code,
        value.message,
        fields,
        value.retryable,
        value.request_id,
        false,
        'server',
      )
    }
    if (status !== (intent ? 201 : 200))
      throw new RuleEditorScopeApiError(
        502,
        'UNEXPECTED_HTTP_STATUS',
        '规则范围响应状态不符合合同',
        [],
        false,
        null,
        !!intent,
      )
    try {
      return parse(value)
    } catch {
      throw new RuleEditorScopeApiError(
        502,
        'INVALID_RESPONSE',
        '规则范围响应不符合合同',
        [],
        false,
        null,
        !!intent,
      )
    }
  } catch (e) {
    if (!intent && signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (e instanceof RuleEditorScopeApiError) throw e
    throw new RuleEditorScopeApiError(
      status,
      signal?.aborted
        ? 'REQUEST_ABORTED'
        : controller.signal.aborted
          ? 'READ_TIMEOUT'
          : 'NETWORK_UNAVAILABLE',
      signal?.aborted
        ? '请求已中止，已发送的冻结意图结果尚未确认'
        : controller.signal.aborted
          ? '请求超时，请保留原意图'
          : '连接中断，请保留原意图',
      [],
      true,
      null,
      !!intent,
    )
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}
function boundedPage(value: unknown, size: string | null) {
  const result = parseRuleEditorMembers(value)
  if (result.items.length > Number(size ?? 50)) invalid('/', true)
  return result
}
export const ruleEditorScopesApi = {
  async accounts(value: RuleEditorAccountQuery, signal?: AbortSignal): Promise<ScopeMemberPage> {
    const parameters = accountsQuery(value)
    return request(
      `editor-accounts?${parameters}`,
      (value) => boundedPage(value, parameters.get('page_size')),
      signal,
    )
  },
  async create(
    value: RuleEditorScopeWrite,
    auth: RuleMutation | RuleVersionMutation,
    signal?: AbortSignal,
  ): Promise<ScopeSnapshot> {
    const frozen = freezeRuleEditorScopeIntent(value, auth)
    return request(
      'editor-scope-snapshots',
      (value) => {
        const result = parseRuleEditorScope(value)
        if (
          frozen.body.selection.mode === 'IDS' &&
          result.count !== frozen.body.selection.account_ids.length
        )
          invalid('/', true)
        return result
      },
      signal,
      frozen,
    )
  },
  async members(
    snapshotId: string,
    value: RuleEditorMemberQuery = {},
    signal?: AbortSignal,
  ): Promise<ScopeMemberPage> {
    if (!uuid(snapshotId)) invalid('/id')
    const parameters = membersQuery(value)
    return request(
      `editor-scope-snapshots/${encodeURIComponent(snapshotId.toLowerCase())}/members?${parameters}`,
      (value) => boundedPage(value, parameters.get('page_size')),
      signal,
    )
  },
}
