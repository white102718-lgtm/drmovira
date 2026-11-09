/** 原六动作专属恢复身份；服务端当前principal，不接受客户端自报主体。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parsePlanHttpFieldError } from './launch-validation'
import { RuleApiError, type RuleAction } from './rules'
export class RuleRecoveryError extends RuleApiError {}
export interface RuleRecoveryPrincipal {
  actor_id: number
  tenant_id: string
}
export interface RuleRecoveryContext extends RuleRecoveryPrincipal {
  csrf_token: string
}
const exact = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  !!v &&
  typeof v === 'object' &&
  !Array.isArray(v) &&
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k))
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const text = (v: unknown, max: number, min = 1): v is string =>
  typeof v === 'string' &&
  [...v].length >= min &&
  [...v].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(v)
function invalid(): never {
  throw new RuleRecoveryError(502, 'INVALID_RESPONSE', '规则恢复身份响应不符合合同')
}
export function parseRuleRecoveryContext(value: unknown): RuleRecoveryContext {
  if (
    !exact(value, ['actor_id', 'tenant_id', 'csrf_token']) ||
    typeof value.actor_id !== 'number' ||
    !Number.isSafeInteger(value.actor_id) ||
    value.actor_id < 1 ||
    !uuid(value.tenant_id) ||
    !text(value.csrf_token, 255, 16)
  )
    invalid()
  return { ...value } as unknown as RuleRecoveryContext
}
export function recoveryPrincipal(value: RuleRecoveryContext): Readonly<RuleRecoveryPrincipal> {
  return Object.freeze({ actor_id: value.actor_id, tenant_id: value.tenant_id })
}
export function requireRecoveryPrincipal(
  saved: RuleRecoveryPrincipal | null,
  current: RuleRecoveryContext,
) {
  if (!saved || saved.actor_id !== current.actor_id || saved.tenant_id !== current.tenant_id)
    throw new RuleRecoveryError(
      403,
      'RULE_RECOVERY_PRINCIPAL_CHANGED',
      '当前登录主体与原请求不同，原请求已保留且不会发送',
    )
}
export function requireInitialRuleActor(
  nativeActorId: number | null,
  context: RuleRecoveryContext,
) {
  if (!Number.isSafeInteger(nativeActorId) || nativeActorId !== context.actor_id)
    throw new RuleRecoveryError(
      403,
      'RULE_RECOVERY_UI_ACTOR_CHANGED',
      '当前登录身份与页面身份不同，请重新认证或刷新页面后再新建请求',
    )
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
      `${import.meta.env.VITE_APP_BASE_API}/api/v1/rules/recovery-context?${path}`,
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
      throw new RuleRecoveryError(
        [401, 403, 404, 409].includes(status) ? status : 502,
        'INVALID_RESPONSE',
        '规则恢复身份来源响应未能确认',
      )
    }
    controller.signal.throwIfAborted()
    if (started !== authContext())
      throw new RuleRecoveryError(
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
        throw new RuleRecoveryError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则恢复身份来源错误响应不符合合同',
        )
      let fields
      try {
        fields = value.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleRecoveryError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则恢复身份来源错误响应不符合合同',
        )
      }
      throw new RuleRecoveryError(
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
      throw new RuleRecoveryError(502, 'UNEXPECTED_HTTP_STATUS', '规则恢复身份辅助只接受200响应')
    try {
      return parse(value)
    } catch {
      return invalid()
    }
  } catch (e) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (e instanceof RuleRecoveryError) throw e
    throw new RuleRecoveryError(
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
export const ruleRecoveryApi = {
  async get(action: RuleAction, signal?: AbortSignal): Promise<RuleRecoveryContext> {
    if (!['CREATE', 'UPDATE', 'ENABLE', 'PAUSE', 'ARCHIVE', 'SIMULATE'].includes(action))
      throw new RuleRecoveryError(422, 'FIELD_INVALID', '需要原规则动作')
    return get(new URLSearchParams({ action }).toString(), parseRuleRecoveryContext, signal)
  },
}
