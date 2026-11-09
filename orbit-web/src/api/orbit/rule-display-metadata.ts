/** 原Rule15独立批量显示资料；不借人员目录动作，不改变原业务DTO。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parsePlanHttpFieldError } from './launch-validation'
import { RuleApiError } from './rules'
export class RuleDisplayMetadataError extends RuleApiError {}
export interface RuleDisplayMetadata {
  rule_id: string
  revision: number
  owner_user_name: string | null
  owner_team_name: string | null
  created_by: number
  created_by_name: string | null
  created_at: string
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
const positive = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v > 0
function invalid(): never {
  throw new RuleDisplayMetadataError(502, 'INVALID_RESPONSE', '规则显示资料响应不符合合同')
}
export function displayMetadataIds(value: unknown): string[] {
  if (
    !Array.isArray(value) ||
    value.length < 1 ||
    value.length > 200 ||
    value.some((v) => !uuid(v)) ||
    new Set(value).size !== value.length
  )
    throw new RuleDisplayMetadataError(422, 'FIELD_INVALID', '规则ID必须为1至200个不重复规范UUID')
  return [...value]
}
export function parseRuleDisplayMetadata(
  value: unknown,
  requestedIds: readonly string[],
): RuleDisplayMetadata[] {
  if (
    !exact(value, ['items']) ||
    !Array.isArray(value.items) ||
    value.items.length !== requestedIds.length
  )
    invalid()
  return value.items.map((row: unknown, index: number) => {
    if (
      !exact(row, [
        'rule_id',
        'revision',
        'owner_user_name',
        'owner_team_name',
        'created_by',
        'created_by_name',
        'created_at',
      ]) ||
      !uuid(row.rule_id) ||
      row.rule_id !== requestedIds[index] ||
      !positive(row.revision) ||
      !positive(row.created_by)
    )
      invalid()
    for (const key of ['owner_user_name', 'owner_team_name', 'created_by_name'])
      if (
        row[key] !== null &&
        (!text(row[key], key === 'owner_team_name' ? 100 : 50) ||
          (row[key] as string).trim() !== row[key] ||
          (row[key] as string).normalize('NFC') !== row[key])
      )
        invalid()
    if (
      typeof row.created_at !== 'string' ||
      !/^(?!0000)\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\.\d{3}Z$/.test(
        row.created_at,
      ) ||
      !Number.isFinite(Date.parse(row.created_at)) ||
      new Date(row.created_at).toISOString() !== row.created_at
    )
      invalid()
    return { ...row } as unknown as RuleDisplayMetadata
  })
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
      `${import.meta.env.VITE_APP_BASE_API}/api/v1/rules/display-metadata?${path}`,
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
      throw new RuleDisplayMetadataError(
        [401, 403, 404, 409].includes(status) ? status : 502,
        'INVALID_RESPONSE',
        '规则显示资料来源响应未能确认',
      )
    }
    controller.signal.throwIfAborted()
    if (started !== authContext())
      throw new RuleDisplayMetadataError(
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
        throw new RuleDisplayMetadataError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则显示资料来源错误响应不符合合同',
        )
      let fields
      try {
        fields = value.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleDisplayMetadataError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则显示资料来源错误响应不符合合同',
        )
      }
      throw new RuleDisplayMetadataError(
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
      throw new RuleDisplayMetadataError(
        502,
        'UNEXPECTED_HTTP_STATUS',
        '规则显示资料辅助只接受200响应',
      )
    try {
      return parse(value)
    } catch {
      return invalid()
    }
  } catch (e) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (e instanceof RuleDisplayMetadataError) throw e
    throw new RuleDisplayMetadataError(
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
export const ruleDisplayMetadataApi = {
  async get(ruleIds: string[], signal?: AbortSignal): Promise<RuleDisplayMetadata[]> {
    const ids = displayMetadataIds(ruleIds)
    return get(
      new URLSearchParams({ rule_ids: ids.join(',') }).toString(),
      (value) => parseRuleDisplayMetadata(value, ids),
      signal,
    )
  },
}
