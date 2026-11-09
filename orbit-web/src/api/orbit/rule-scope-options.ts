/** 规则账户筛选远程候选；仅rules.create/edit，非人员/供应商写授权。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parsePlanHttpFieldError } from './launch-validation'
import { RuleApiError } from './rules'
export class RuleScopeOptionsError extends RuleApiError {}
export type ScopeOptionKind = 'OPERATOR' | 'VENDOR'
export interface RuleOperatorOption {
  id: string
  name: string
  team_id: string
  team_name: string
  active: boolean
}
export interface RuleVendorOption {
  id: string
  name: string
  alias: string | null
  availability: 'AVAILABLE' | 'UNAVAILABLE'
}
export interface RuleScopeOptionPage<T> {
  items: T[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export type RuleScopeOptionsQuery = {
  kind: ScopeOptionKind
  action: 'CREATE' | 'UPDATE'
  rule_id?: string
  owner_user_id: string
  owner_team_id: string
  q?: string
  page_size?: 20 | 50 | 100 | 200
  cursor?: string
}
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
function invalid(path = '/', response = true): never {
  throw new RuleScopeOptionsError(
    response ? 502 : 422,
    response ? 'INVALID_RESPONSE' : 'FIELD_INVALID',
    response ? '规则筛选候选响应不符合合同' : '规则筛选候选参数无效',
    response
      ? []
      : [
          {
            path,
            code: 'FIELD_INVALID',
            message: '请使用完整且符合组合要求的参数',
            constraint: null,
          },
        ],
  )
}
const positive = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v > 0
const utc = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^(?!0000)\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|\+00:00)$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 10) === v.slice(0, 10)
export function scopeOptionsParameters(v: unknown): URLSearchParams {
  if (
    !record(v) ||
    Object.keys(v).some(
      (k) =>
        ![
          'kind',
          'action',
          'rule_id',
          'owner_user_id',
          'owner_team_id',
          'q',
          'page_size',
          'cursor',
        ].includes(k),
    )
  )
    invalid('/', false)
  if (v.kind !== 'OPERATOR' && v.kind !== 'VENDOR') invalid('/kind', false)
  if (v.action !== 'CREATE' && v.action !== 'UPDATE') invalid('/action', false)
  if (v.action === 'CREATE' ? Object.hasOwn(v, 'rule_id') : !uuid(v.rule_id))
    invalid('/rule_id', false)
  if (!uuid(v.owner_user_id)) invalid('/owner_user_id', false)
  if (!uuid(v.owner_team_id)) invalid('/owner_team_id', false)
  const result = new URLSearchParams({
    kind: v.kind,
    action: v.action,
    owner_user_id: v.owner_user_id.toLowerCase(),
    owner_team_id: v.owner_team_id.toLowerCase(),
  })
  if (v.action === 'UPDATE') result.set('rule_id', String(v.rule_id).toLowerCase())
  if (v.q !== undefined) {
    if (!text(v.q, Number.MAX_SAFE_INTEGER, 0)) invalid('/q', false)
    const q = v.q.trim().normalize('NFC')
    if ([...q].length > 100 || (v.q !== '' && !q)) invalid('/q', false)
    result.set('q', q)
  }
  if (v.page_size !== undefined) {
    if (typeof v.page_size !== 'number' || ![20, 50, 100, 200].includes(v.page_size))
      invalid('/page_size', false)
    result.set('page_size', String(v.page_size))
  }
  if (v.cursor !== undefined) {
    if (!text(v.cursor, 2048)) invalid('/cursor', false)
    result.set('cursor', v.cursor)
  }
  return result
}
export function parseRuleScopeOptionPage<K extends ScopeOptionKind>(
  kind: K,
  v: unknown,
  size = 200,
): RuleScopeOptionPage<K extends 'OPERATOR' ? RuleOperatorOption : RuleVendorOption> {
  if (
    !exact(v, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(v.items) ||
    v.items.length > size ||
    v.items.length > 200 ||
    !utc(v.data_as_of) ||
    !positive(v.scope_version) ||
    (v.next_cursor !== null && !text(v.next_cursor, 2048))
  )
    invalid()
  const seen = new Set<string>()
  const items = v.items.map((item) => {
    if (!record(item) || !uuid(item.id) || seen.has(item.id.toLowerCase())) invalid()
    seen.add(item.id.toLowerCase())
    if (kind === 'OPERATOR') {
      if (
        !exact(item, ['id', 'name', 'team_id', 'team_name', 'active']) ||
        !text(item.name, 4096) ||
        !uuid(item.team_id) ||
        !text(item.team_name, 4096) ||
        typeof item.active !== 'boolean'
      )
        invalid()
    } else if (kind === 'VENDOR') {
      if (
        !exact(item, ['id', 'name', 'alias', 'availability']) ||
        !text(item.name, 255) ||
        (item.alias !== null && !text(item.alias, 30)) ||
        typeof item.availability !== 'string' ||
        !['AVAILABLE', 'UNAVAILABLE'].includes(item.availability)
      )
        invalid()
    } else invalid()
    return { ...item }
  })
  return {
    items,
    next_cursor: v.next_cursor,
    data_as_of: v.data_as_of,
    scope_version: v.scope_version,
  } as unknown as RuleScopeOptionPage<K extends 'OPERATOR' ? RuleOperatorOption : RuleVendorOption>
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
      if (bytes > 2 * 1024 * 1024) invalid()
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
async function get<T>(path: string, parse: (v: unknown) => T, signal?: AbortSignal): Promise<T> {
  signal?.throwIfAborted()
  const started = authContext(),
    controller = new AbortController(),
    abort = () => controller.abort()
  const timer = setTimeout(abort, 15000)
  signal?.addEventListener('abort', abort, { once: true })
  let status = 0
  try {
    const response = await fetch(
      `${import.meta.env.VITE_APP_BASE_API}/api/v1/rules/editor-scope-options?${path}`,
      {
        method: 'GET',
        headers: orbitAuthHeaders({ Accept: 'application/json' }),
        credentials: orbitCredentials(),
        signal: controller.signal,
        cache: 'no-store',
      },
    )
    status = response.status
    let value: unknown
    try {
      value = await body(response, controller.signal)
    } catch (e) {
      if (controller.signal.aborted) throw e
      // 已知授权/来源漂移状态不能因代理HTML或损坏正文降为普通来源故障。
      throw new RuleScopeOptionsError(
        [401, 403, 409].includes(status) ? status : 502,
        'INVALID_RESPONSE',
        '规则筛选候选来源响应未能确认',
      )
    }
    controller.signal.throwIfAborted()
    if (started !== authContext())
      throw new RuleScopeOptionsError(
        409,
        'SESSION_CONTEXT_CHANGED',
        '认证上下文已变化，已丢弃迟到响应',
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
        throw new RuleScopeOptionsError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则筛选候选来源错误响应不符合合同',
        )
      let fields
      try {
        fields = value.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleScopeOptionsError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则筛选候选来源错误响应不符合合同',
        )
      }
      throw new RuleScopeOptionsError(
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
    if (status !== 200)
      throw new RuleScopeOptionsError(
        502,
        'UNEXPECTED_HTTP_STATUS',
        '规则筛选候选辅助只接受200响应',
      )
    try {
      return parse(value)
    } catch {
      return invalid()
    }
  } catch (e) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (e instanceof RuleScopeOptionsError) throw e
    throw new RuleScopeOptionsError(
      status,
      controller.signal.aborted ? 'READ_TIMEOUT' : 'NETWORK_UNAVAILABLE',
      controller.signal.aborted ? '读取超时，请重新加载候选' : '连接中断，请重新加载候选',
      [],
      true,
    )
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}
export const ruleScopeOptionsApi = {
  async options<K extends ScopeOptionKind>(
    query: RuleScopeOptionsQuery & { kind: K },
    signal?: AbortSignal,
  ): Promise<RuleScopeOptionPage<K extends 'OPERATOR' ? RuleOperatorOption : RuleVendorOption>> {
    const parameters = scopeOptionsParameters(query),
      kind = query.kind,
      size = query.page_size ?? 50
    return get(parameters.toString(), (v) => parseRuleScopeOptionPage(kind, v, size), signal)
  },
}
