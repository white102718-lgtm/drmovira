/** 列表专属只读候选：规则真实引用，无编辑或人员目录权限。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parsePlanHttpFieldError } from './launch-validation'
import { RuleApiError } from './rules'
export class RuleListFilterError extends RuleApiError {}
export type RuleFilterKind = 'OPERATOR' | 'METRIC_PROFILE' | 'CHANNEL'
export interface RuleFilterItem {
  id: string
  label: string | null
}
export interface RuleFilterPage {
  items: RuleFilterItem[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
const exact = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  !!v &&
  typeof v === 'object' &&
  !Array.isArray(v) &&
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k))
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const text = (v: unknown, max: number): v is string =>
  typeof v === 'string' &&
  [...v].length > 0 &&
  [...v].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(v)
function invalid(): never {
  throw new RuleListFilterError(502, 'INVALID_RESPONSE', '规则列表筛选响应不符合合同')
}
export function parseRuleFilterPage(v: unknown): RuleFilterPage {
  if (
    !exact(v, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(v.items) ||
    v.items.length > 200 ||
    (v.next_cursor !== null && !text(v.next_cursor, 2048)) ||
    typeof v.scope_version !== 'number' ||
    !Number.isSafeInteger(v.scope_version) ||
    v.scope_version < 1 ||
    typeof v.data_as_of !== 'string' ||
    !/^(?!0000)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(v.data_as_of) ||
    !Number.isFinite(Date.parse(v.data_as_of)) ||
    new Date(v.data_as_of).toISOString() !== v.data_as_of
  )
    invalid()
  let previous = ''
  const items = v.items.map((item: unknown) => {
    if (
      !exact(item, ['id', 'label']) ||
      !uuid(item.id) ||
      item.id <= previous ||
      (item.label !== null &&
        (typeof item.label !== 'string' ||
          [...item.label].length > 255 ||
          /[\p{Cs}]/u.test(item.label)))
    )
      invalid()
    previous = item.id
    return { id: item.id, label: item.label as string | null }
  })
  if (v.next_cursor && !items.length) invalid()
  return {
    items,
    next_cursor: v.next_cursor as string | null,
    data_as_of: v.data_as_of,
    scope_version: v.scope_version,
  }
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
      `${import.meta.env.VITE_APP_BASE_API}/api/v1/rules/list-filter-options?${path}`,
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
      throw new RuleListFilterError(
        [401, 403, 404, 409].includes(status) ? status : 502,
        'INVALID_RESPONSE',
        '规则列表筛选来源响应未能确认',
      )
    }
    controller.signal.throwIfAborted()
    if (started !== authContext())
      throw new RuleListFilterError(
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
        throw new RuleListFilterError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则列表筛选来源错误响应不符合合同',
        )
      let fields
      try {
        fields = value.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleListFilterError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则列表筛选来源错误响应不符合合同',
        )
      }
      throw new RuleListFilterError(
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
      throw new RuleListFilterError(502, 'UNEXPECTED_HTTP_STATUS', '规则列表筛选辅助只接受200响应')
    try {
      return parse(value)
    } catch {
      return invalid()
    }
  } catch (e) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (e instanceof RuleListFilterError) throw e
    throw new RuleListFilterError(
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
export const ruleListFilterApi = {
  async list(kind: RuleFilterKind, cursor?: string, signal?: AbortSignal): Promise<RuleFilterPage> {
    if (
      !['OPERATOR', 'METRIC_PROFILE', 'CHANNEL'].includes(kind) ||
      (cursor !== undefined && !text(cursor, 2048))
    )
      throw new RuleListFilterError(422, 'FIELD_INVALID', '候选类型或游标非法')
    const query = new URLSearchParams({ kind, page_size: '50', ...(cursor ? { cursor } : {}) })
    return get(query.toString(), parseRuleFilterPage, signal)
  },
}
