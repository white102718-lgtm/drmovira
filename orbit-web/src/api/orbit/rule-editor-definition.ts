/** 规则编辑定义专属只读source；不借rules.read、不重建Scope5或当前权限证明。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parsePlanHttpFieldError } from './launch-validation'
import { RuleApiError, parseRule, type Rule } from './rules'
export interface StoredRuleScope {
  id: string
  count: number
  owner_user_id: string
  owner_team_id: string
}
export interface RuleEditorDefinition {
  rule: Rule
  stored_scope: StoredRuleScope
}
export class RuleEditorDefinitionError extends RuleApiError {}
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
function invalid(): never {
  throw new RuleEditorDefinitionError(502, 'INVALID_RESPONSE', '规则编辑定义响应不符合合同')
}
export function parseRuleEditorDefinition(value: unknown): RuleEditorDefinition {
  if (!exact(value, ['rule', 'stored_scope'])) invalid()
  let rule: Rule
  try {
    rule = parseRule(value.rule)
  } catch {
    return invalid()
  }
  const scope = value.stored_scope
  if (
    !exact(scope, ['id', 'count', 'owner_user_id', 'owner_team_id']) ||
    !uuid(scope.id) ||
    !uuid(scope.owner_user_id) ||
    !uuid(scope.owner_team_id) ||
    typeof scope.count !== 'number' ||
    !Number.isSafeInteger(scope.count) ||
    scope.count < 1 ||
    scope.count > 50000 ||
    scope.id.toLowerCase() !== rule.scope_snapshot_id.toLowerCase() ||
    scope.owner_user_id.toLowerCase() !== rule.ownership.owner_user_id.toLowerCase() ||
    scope.owner_team_id.toLowerCase() !== rule.ownership.owner_team_id.toLowerCase()
  )
    invalid()
  return {
    rule,
    stored_scope: {
      id: scope.id,
      count: scope.count,
      owner_user_id: scope.owner_user_id,
      owner_team_id: scope.owner_team_id,
    },
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
    const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/rules/${path}`, {
      method: 'GET',
      headers: orbitAuthHeaders({ Accept: 'application/json' }),
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
      throw new RuleEditorDefinitionError(502, 'INVALID_RESPONSE', '规则编辑来源响应未能确认')
    }
    controller.signal.throwIfAborted()
    if (started !== authContext())
      throw new RuleEditorDefinitionError(
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
        throw new RuleEditorDefinitionError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则编辑来源错误响应不符合合同',
        )
      let fields
      try {
        fields = value.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleEditorDefinitionError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则编辑来源错误响应不符合合同',
        )
      }
      throw new RuleEditorDefinitionError(
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
      throw new RuleEditorDefinitionError(
        502,
        'UNEXPECTED_HTTP_STATUS',
        '规则编辑辅助只接受200响应',
      )
    try {
      return parse(value)
    } catch {
      return invalid()
    }
  } catch (e) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (e instanceof RuleEditorDefinitionError) throw e
    throw new RuleEditorDefinitionError(
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
export const ruleEditorDefinitionApi = {
  async get(ruleId: string, signal?: AbortSignal): Promise<RuleEditorDefinition> {
    if (!uuid(ruleId)) throw new RuleEditorDefinitionError(422, 'FIELD_INVALID', '需要真实规则UUID')
    return get(
      `${encodeURIComponent(ruleId.toLowerCase())}/edit-definition`,
      (value) => {
        const definition = parseRuleEditorDefinition(value)
        if (definition.rule.id.toLowerCase() !== ruleId.toLowerCase()) invalid()
        return definition
      },
      signal,
    )
  },
}
