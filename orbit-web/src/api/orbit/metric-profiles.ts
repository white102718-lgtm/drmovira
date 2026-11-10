/** 原GET指标配置只读合同；不提供发布或执行入口，不把FIXTURE解释为平台证据。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { ReferenceApiError } from './references'
import { parsePlanHttpFieldError, type PlanHttpFieldError } from './launch-validation'

export interface MetricProfile {
  id: string
  version: string
  source: 'META' | 'FIXTURE'
  register_action_type: string | null
  purchase_action_type: string | null
  value_action_type: string | null
  attribution_windows: string[]
  action_report_time: string
  timezone_policy: 'ACCOUNT_LOCAL'
  breakdown: 'TOTAL'
  maturity_days: number
  verified: boolean
}
export interface MetricProfilePage {
  items: MetricProfile[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export interface MetricProfileQuery {
  q: string
  metric_profile_id: string | null
  cursor: string | null
  page_size: number
}
export class MetricProfileError extends ReferenceApiError {
  constructor(
    status: number,
    code: string,
    message: string,
    public field_errors: PlanHttpFieldError[] = [],
    public retryable = false,
    public request_id: string | null = null,
  ) {
    super(status, code, message)
  }
}
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v)
const text = (v: unknown, max: number, min = 1): v is string =>
  typeof v === 'string' && [...v].length >= min && [...v].length <= max
const object = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  !!v &&
  typeof v === 'object' &&
  !Array.isArray(v) &&
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k))
function invalid(request = false): never {
  throw new MetricProfileError(
    request ? 422 : 502,
    request ? 'FIELD_INVALID' : 'INVALID_RESPONSE',
    request
      ? '请输入完整指标UUID，并选择20、50、100或200条每页'
      : '指标配置响应不符合原合同，请重新读取',
  )
}
function dateTime(v: unknown): v is string {
  if (typeof v !== 'string') return false
  const m =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-](\d{2}):(\d{2}))$/.exec(v)
  return (
    !!m &&
    +m[2] >= 1 &&
    +m[2] <= 12 &&
    +m[3] >= 1 &&
    +m[3] <= new Date(Date.UTC(+m[1], +m[2], 0)).getUTCDate() &&
    +m[4] <= 23 &&
    +m[5] <= 59 &&
    +m[6] <= 59 &&
    +(m[7] ?? 0) <= 23 &&
    +(m[8] ?? 0) <= 59 &&
    Number.isFinite(Date.parse(v))
  )
}
export function parseMetricProfile(v: unknown): MetricProfile {
  if (
    !object(v, [
      'id',
      'version',
      'source',
      'register_action_type',
      'purchase_action_type',
      'value_action_type',
      'attribution_windows',
      'action_report_time',
      'timezone_policy',
      'breakdown',
      'maturity_days',
      'verified',
    ]) ||
    !uuid(v.id) ||
    !text(v.version, 64) ||
    !['META', 'FIXTURE'].includes(String(v.source)) ||
    !['register_action_type', 'purchase_action_type', 'value_action_type'].every(
      (k) => v[k] === null || text(v[k], 64),
    ) ||
    !Array.isArray(v.attribution_windows) ||
    v.attribution_windows.length < 1 ||
    v.attribution_windows.length > 10 ||
    !v.attribution_windows.every((x) => text(x, 64)) ||
    !text(v.action_report_time, 64) ||
    v.timezone_policy !== 'ACCOUNT_LOCAL' ||
    v.breakdown !== 'TOTAL' ||
    typeof v.maturity_days !== 'number' ||
    !Number.isSafeInteger(v.maturity_days) ||
    v.maturity_days < 1 ||
    v.maturity_days > 90 ||
    typeof v.verified !== 'boolean'
  )
    invalid()
  return v as unknown as MetricProfile
}
export function parseMetricProfilePage(v: unknown, historical = false): MetricProfilePage {
  if (
    !object(v, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(v.items) ||
    v.items.length > 200 ||
    !(v.next_cursor === null || text(v.next_cursor, 2048)) ||
    !dateTime(v.data_as_of) ||
    typeof v.scope_version !== 'number' ||
    !Number.isSafeInteger(v.scope_version) ||
    v.scope_version < 1
  )
    invalid()
  const seen = new Set<string>()
  for (const entry of v.items) {
    const item = parseMetricProfile(entry)
    const key = historical
      ? JSON.stringify([item.id.toLowerCase(), item.version])
      : item.id.toLowerCase()
    if (seen.has(key)) invalid()
    seen.add(key)
  }
  return v as unknown as MetricProfilePage
}
/** 仅接受已明确的四个参数；不吞掉未定义的报表/Owner通用过滤器。 */
export function metricProfileQuery(v: MetricProfileQuery): URLSearchParams {
  if (
    !object(v, ['q', 'metric_profile_id', 'cursor', 'page_size']) ||
    !text(v.q, 100, 0) ||
    !(v.q === '' || uuid(v.q)) ||
    !(v.metric_profile_id === null || uuid(v.metric_profile_id)) ||
    !(v.cursor === null || text(v.cursor, 2048)) ||
    ![20, 50, 100, 200].includes(v.page_size)
  )
    invalid(true)
  const q = new URLSearchParams({ page_size: String(v.page_size) })
  if (v.q) q.set('q', v.q.toLowerCase())
  if (v.metric_profile_id !== null) q.set('metric_profile_id', v.metric_profile_id.toLowerCase())
  if (v.cursor !== null) q.set('cursor', v.cursor)
  return q
}
export const metricProfilesApi = {
  list(query: MetricProfileQuery, signal?: AbortSignal): Promise<MetricProfilePage> {
    return metricProfilePageRequest(query, signal, false)
  },
  history(query: MetricProfileQuery, signal?: AbortSignal): Promise<MetricProfilePage> {
    return metricProfilePageRequest(query, signal, true)
  },
}
async function metricProfilePageRequest(
  query: MetricProfileQuery,
  signal: AbortSignal | undefined,
  historical: boolean,
): Promise<MetricProfilePage> {
  const params = metricProfileQuery(query)
  signal?.throwIfAborted()
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), 15000)
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  try {
    const response = await fetch(
      `${import.meta.env.VITE_APP_BASE_API}/api/v1/metric-profiles${historical ? '/history-candidates' : ''}?${params}`,
      {
        method: 'GET',
        cache: 'no-store',
        credentials: orbitCredentials(),
        headers: orbitAuthHeaders({ Accept: 'application/json' }),
        signal: controller.signal,
      },
    )
    let body: unknown
    try {
      body = await response.json()
    } catch {
      throw new MetricProfileError(
        response.status,
        'INVALID_RESPONSE',
        '指标服务返回了无法识别的响应，请重试',
      )
    }
    if (response.status !== 200) {
      if (
        !object(body, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
        !text(body.code, 64) ||
        !text(body.message, 1000) ||
        !Array.isArray(body.field_errors) ||
        body.field_errors.length > 100 ||
        typeof body.retryable !== 'boolean' ||
        !uuid(body.request_id)
      )
        throw new MetricProfileError(
          response.status,
          'INVALID_RESPONSE',
          '指标服务响应异常，请重试',
        )
      let fields: PlanHttpFieldError[]
      try {
        fields = body.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new MetricProfileError(
          response.status,
          'INVALID_RESPONSE',
          '指标服务错误字段不符合合同，请重试',
        )
      }
      throw new MetricProfileError(
        response.status,
        body.code,
        body.message,
        fields,
        body.retryable,
        body.request_id,
      )
    }
    return parseMetricProfilePage(body, historical)
  } catch (error) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (error instanceof MetricProfileError) throw error
    throw new MetricProfileError(0, 'NETWORK_UNAVAILABLE', '指标目录读取中断，请重试', [], true)
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}
