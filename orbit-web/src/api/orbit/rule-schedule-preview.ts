/** 规则未来五次调度预览只读POST；不持久、不创建模拟或启用资格。 */
import { orbitAuthHeaders, orbitCredentials, cookieCsrf } from './authentication'
import { parsePlanHttpFieldError } from './launch-validation'
import { RuleApiError, parseRuleSchedule, type RuleSchedule } from './rules'
export class RuleSchedulePreviewError extends RuleApiError {}
export interface SchedulePreviewRequest {
  action: 'CREATE' | 'UPDATE'
  rule_id: string | null
  rule_revision: number | null
  schedule: RuleSchedule
}
export interface SchedulePreview {
  reference_at: string
  timezone: string
  slots: { local_time: string; utc_time: string }[]
  skipped_local_times: { local_time: string; reason_code: 'DST_NONEXISTENT_LOCAL_TIME' }[]
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
function invalid(): never {
  throw new RuleSchedulePreviewError(502, 'INVALID_RESPONSE', '调度预览响应不符合约定')
}
const wall = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^(?!0000)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(v) &&
  Number.isFinite(Date.parse(v + 'Z')) &&
  new Date(v + 'Z').toISOString().slice(0, 19) === v
function utc(v: unknown): v is string {
  return (
    typeof v === 'string' &&
    /^(?!0000)\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$/.test(v) &&
    wall(v.slice(0, 19))
  )
}
const micros = (v: string) =>
  BigInt(Date.parse(v.slice(0, 19) + 'Z')) * 1000n + BigInt(v.slice(20, 26))
export function parseSchedulePreviewRequest(v: unknown): SchedulePreviewRequest {
  if (
    !exact(v, ['action', 'rule_id', 'rule_revision', 'schedule']) ||
    typeof v.action !== 'string' ||
    !['CREATE', 'UPDATE'].includes(v.action)
  )
    throw new RuleSchedulePreviewError(
      422,
      'FIELD_VALIDATION_FAILED',
      '预览请求必须提供完整动作、规则和调度字段',
    )
  if (
    v.action === 'CREATE'
      ? v.rule_id !== null || v.rule_revision !== null
      : !uuid(v.rule_id) ||
        typeof v.rule_revision !== 'number' ||
        !Number.isSafeInteger(v.rule_revision) ||
        v.rule_revision < 1
  )
    throw new RuleSchedulePreviewError(422, 'FIELD_VALIDATION_FAILED', '创建或编辑版本字段不匹配')
  let schedule: RuleSchedule
  try {
    schedule = parseRuleSchedule(v.schedule)
  } catch {
    throw new RuleSchedulePreviewError(
      422,
      'FIELD_VALIDATION_FAILED',
      '请完整填写合法调度时区、日期与频率',
    )
  }
  return {
    action: v.action as 'CREATE' | 'UPDATE',
    rule_id: typeof v.rule_id === 'string' ? v.rule_id.toLowerCase() : null,
    rule_revision: v.rule_revision as number | null,
    schedule,
  }
}
export function parseSchedulePreview(v: unknown): SchedulePreview {
  if (
    !exact(v, ['reference_at', 'timezone', 'slots', 'skipped_local_times']) ||
    !utc(v.reference_at) ||
    !text(v.timezone, 64) ||
    !Array.isArray(v.slots) ||
    v.slots.length > 5 ||
    !Array.isArray(v.skipped_local_times) ||
    v.skipped_local_times.length > 366
  )
    invalid()
  let formatter: Intl.DateTimeFormat
  try {
    formatter = new Intl.DateTimeFormat('en-GB', {
      timeZone: v.timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    })
  } catch {
    return invalid()
  }
  let previous = micros(v.reference_at)
  const slots = v.slots.map((item) => {
    if (
      !exact(item, ['local_time', 'utc_time']) ||
      !utc(item.utc_time) ||
      typeof item.local_time !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-](?:0\d|1\d|2[0-3]):[0-5]\d$/.test(
        item.local_time,
      ) ||
      !wall(item.local_time.slice(0, 19))
    )
      invalid()
    const current = micros(item.utc_time)
    if (current <= previous || BigInt(Date.parse(item.local_time)) * 1000n !== current) invalid()
    const parts = Object.fromEntries(
      formatter.formatToParts(new Date(item.utc_time)).map((p) => [p.type, p.value]),
    )
    if (
      `${parts.year.padStart(4, '0')}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}` !==
      item.local_time.slice(0, 19)
    )
      invalid()
    previous = current
    return { local_time: item.local_time, utc_time: item.utc_time }
  })
  const seen = new Set<string>()
  const skipped_local_times = v.skipped_local_times.map((item) => {
    if (
      !exact(item, ['local_time', 'reason_code']) ||
      !wall(item.local_time) ||
      item.reason_code !== 'DST_NONEXISTENT_LOCAL_TIME' ||
      seen.has(item.local_time)
    )
      invalid()
    seen.add(item.local_time)
    return {
      local_time: item.local_time,
      reason_code: item.reason_code as 'DST_NONEXISTENT_LOCAL_TIME',
    }
  })
  return { reference_at: v.reference_at, timezone: v.timezone, slots, skipped_local_times }
}
const authContext = () =>
  JSON.stringify([
    orbitCredentials(),
    Object.entries(orbitAuthHeaders()).sort(([a], [b]) => a.localeCompare(b)),
  ])
async function body(response: Response, signal: AbortSignal): Promise<unknown> {
  // 技术响应预算；最多5次预览和366个跳过墙钟，不接受无界服务端正文。
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
      if (bytes > 256 * 1024) invalid()
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
async function post<T>(
  payload: SchedulePreviewRequest,
  csrf: string,
  parse: (v: unknown) => T,
  signal?: AbortSignal,
): Promise<T> {
  signal?.throwIfAborted()
  const started = authContext(),
    controller = new AbortController(),
    abort = () => controller.abort()
  const timer = setTimeout(abort, 15000)
  signal?.addEventListener('abort', abort, { once: true })
  let status = 0
  try {
    const response = await fetch(
      `${import.meta.env.VITE_APP_BASE_API}/api/v1/rules/editor-schedule-preview`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
        headers: orbitAuthHeaders({
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf,
        }),
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
      throw new RuleSchedulePreviewError(502, 'INVALID_RESPONSE', '规则调度预览来源响应未能确认')
    }
    controller.signal.throwIfAborted()
    if (started !== authContext())
      throw new RuleSchedulePreviewError(
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
        throw new RuleSchedulePreviewError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则调度预览来源错误响应不符合合同',
        )
      let fields
      try {
        fields = value.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleSchedulePreviewError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则调度预览来源错误响应不符合合同',
        )
      }
      throw new RuleSchedulePreviewError(
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
      throw new RuleSchedulePreviewError(
        502,
        'UNEXPECTED_HTTP_STATUS',
        '规则调度预览辅助只接受200响应',
      )
    try {
      return parse(value)
    } catch {
      return invalid()
    }
  } catch (e) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (e instanceof RuleSchedulePreviewError) throw e
    throw new RuleSchedulePreviewError(
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
export const ruleSchedulePreviewApi = {
  async preview(
    value: SchedulePreviewRequest,
    auth: { csrf_token: string },
    signal?: AbortSignal,
  ): Promise<SchedulePreview> {
    const request = parseSchedulePreviewRequest(value)
    if (!exact(auth, ['csrf_token']) || !text(auth.csrf_token, 255, 16))
      throw new RuleSchedulePreviewError(403, 'CSRF_INVALID', '需要当前会话校验')
    if (cookieCsrf() !== undefined && cookieCsrf() !== auth.csrf_token)
      throw new RuleSchedulePreviewError(
        409,
        'SESSION_CONTEXT_CHANGED',
        '当前会话已变化，请刷新后预览',
      )
    return post(
      request,
      auth.csrf_token,
      (v) => {
        const result = parseSchedulePreview(v)
        if (result.timezone !== request.schedule.timezone) invalid()
        return result
      },
      signal,
    )
  },
}
