/** 原指标查询合同：金融值只保留字符串；来源缺失不转换成空成功。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parsePlanFieldError, type PlanFieldError } from './launch-validation'

export const metricDatasets = [
  'ACCOUNT',
  'CAMPAIGN',
  'ADSET',
  'AD',
  'OPERATOR',
  'CHANNEL',
  'ASSET',
  'LAUNCH',
] as const
export const metricValueKeys = [
  'spend',
  'impressions',
  'clicks',
  'registrations',
  'purchases',
  'purchase_value',
  'roas',
  'cpm',
  'ctr',
  'cpc',
  'cpa',
  'usage',
] as const
export const metricSorts = [
  'spend',
  'impressions',
  'clicks',
  'purchases',
  'roas',
  'cpm',
  'name',
] as const
export type MetricDataset = (typeof metricDatasets)[number]
export type MetricValues = Record<(typeof metricValueKeys)[number], string | null>
export interface MetricQuery {
  date_from: string
  date_to: string
  dataset: MetricDataset
  metric_profile_id: string
  scope_snapshot_id: string | null
  channel_id: string | null
  operator_user_id: string | null
  q: string
  sort: (typeof metricSorts)[number]
  direction: 'ASC' | 'DESC'
  cursor: string | null
  page_size: 20 | 50 | 100 | 200
  granularity: 'SUMMARY' | 'DAY'
}
export interface MetricRow {
  tenant_id: string
  owner_team_id: string | null
  operator_user_id: string | null
  entity_id: string
  name: string
  channel_id: string | null
  product_name_snapshot: string | null
  currency: string
  metric_profile_id: string
  business_date: string | null
  account_count: number
  ad_count: number
  values: MetricValues
  quality: 'COMPLETE' | 'PARTIAL' | 'STALE' | 'UNKNOWN'
  coverage: string
}
export interface MetricTotal {
  tenant_id: string
  currency: string
  metric_profile_id: string
  values: MetricValues
  account_count: number
  ad_count: number
  missing_count: number
  coverage: string
}
export interface Metrics {
  items: MetricRow[]
  next_cursor: string | null
  scope_version: number
  snapshot_id: string
  data_as_of: string
  missing_count: number
  query_snapshot_id: string
  totals: MetricTotal[]
}
export interface FrozenMetricsRequest {
  csrf_token: string
  idempotency_key: string
}
export class MetricsError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public field_errors: PlanFieldError[] = [],
    public retryable = false,
    public request_id: string | null = null,
    public unknown_result = false,
    public source: 'local' | 'server' = 'local',
  ) {
    super(message)
  }
}
const object = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  !!v &&
  typeof v === 'object' &&
  !Array.isArray(v) &&
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k))
const string = (v: unknown, max: number, min = 1): v is string =>
  typeof v === 'string' && [...v].length >= min && [...v].length <= max
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v)
const nullable = (v: unknown, check: (v: unknown) => boolean) => v === null || check(v)
const integer = (v: unknown, max = 2147483647, min = 0): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v >= min && v <= max
const decimal = (v: unknown): v is string =>
  typeof v === 'string' && v.length <= 28 && /^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/.test(v)
const day = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}$/.test(v) &&
  v.slice(0, 4) !== '0000' &&
  Number.isFinite(Date.parse(v)) &&
  new Date(`${v}T00:00:00Z`).toISOString().slice(0, 10) === v
const instant = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(v) &&
  day(v.slice(0, 10)) &&
  Number.isFinite(Date.parse(v)) &&
  +v.slice(11, 13) <= 23 &&
  +v.slice(14, 16) <= 59 &&
  +v.slice(17, 19) <= 59
function invalid(request = false): never {
  throw new MetricsError(
    request ? 422 : 502,
    request ? 'FIELD_INVALID' : 'INVALID_RESPONSE',
    request
      ? '查询字段不符合原合同，请检查日期、UUID、页大小和筛选值'
      : '指标响应未能完整核验，请保留原查询后重试',
  )
}
export function parseMetricQuery(v: unknown): MetricQuery {
  if (
    !object(v, [
      'date_from',
      'date_to',
      'dataset',
      'metric_profile_id',
      'scope_snapshot_id',
      'channel_id',
      'operator_user_id',
      'q',
      'sort',
      'direction',
      'cursor',
      'page_size',
      'granularity',
    ]) ||
    !day(v.date_from) ||
    !day(v.date_to) ||
    !metricDatasets.includes(v.dataset as MetricDataset) ||
    !uuid(v.metric_profile_id) ||
    !nullable(v.scope_snapshot_id, uuid) ||
    !nullable(v.operator_user_id, uuid) ||
    !nullable(v.channel_id, (x) => string(x, 64)) ||
    !string(v.q, 100, 0) ||
    !metricSorts.includes(v.sort as MetricQuery['sort']) ||
    !['ASC', 'DESC'].includes(v.direction as string) ||
    !nullable(v.cursor, (x) => string(x, 2048)) ||
    ![20, 50, 100, 200].includes(v.page_size as number) ||
    !['SUMMARY', 'DAY'].includes(v.granularity as string)
  )
    invalid(true)
  const count = (Date.parse(v.date_to as string) - Date.parse(v.date_from as string)) / 86400000 + 1
  if (count < 1 || count > 93) invalid(true)
  // 未来日期必须由服务端逐账户当地today核验，客户端不以浏览器/上海日代替。
  return structuredClone(v) as unknown as MetricQuery
}
export function parseMetricValues(v: unknown): MetricValues {
  if (!object(v, [...metricValueKeys]) || !metricValueKeys.every((k) => nullable(v[k], decimal)))
    invalid()
  return { ...v } as MetricValues
}
export function parseMetricRow(v: unknown): MetricRow {
  if (
    !object(v, [
      'tenant_id',
      'owner_team_id',
      'operator_user_id',
      'entity_id',
      'name',
      'channel_id',
      'product_name_snapshot',
      'currency',
      'metric_profile_id',
      'business_date',
      'account_count',
      'ad_count',
      'values',
      'quality',
      'coverage',
    ]) ||
    !uuid(v.tenant_id) ||
    !nullable(v.owner_team_id, uuid) ||
    !nullable(v.operator_user_id, uuid) ||
    !string(v.entity_id, 64) ||
    !string(v.name, 255, 0) ||
    !nullable(v.channel_id, uuid) ||
    !nullable(v.product_name_snapshot, (x) => string(x, 100)) ||
    !string(v.currency, 3, 3) ||
    !uuid(v.metric_profile_id) ||
    !nullable(v.business_date, day) ||
    !integer(v.account_count) ||
    !integer(v.ad_count) ||
    !['COMPLETE', 'PARTIAL', 'STALE', 'UNKNOWN'].includes(v.quality as string) ||
    !decimal(v.coverage)
  )
    invalid()
  return { ...v, values: parseMetricValues(v.values) } as unknown as MetricRow
}
export function parseMetricTotal(v: unknown): MetricTotal {
  if (
    !object(v, [
      'tenant_id',
      'currency',
      'metric_profile_id',
      'values',
      'account_count',
      'ad_count',
      'missing_count',
      'coverage',
    ]) ||
    !uuid(v.tenant_id) ||
    !string(v.currency, 3, 3) ||
    !uuid(v.metric_profile_id) ||
    !integer(v.account_count) ||
    !integer(v.ad_count) ||
    !integer(v.missing_count) ||
    !decimal(v.coverage)
  )
    invalid()
  return { ...v, values: parseMetricValues(v.values) } as unknown as MetricTotal
}
export function parseMetrics(v: unknown): Metrics {
  if (
    !object(v, [
      'items',
      'next_cursor',
      'scope_version',
      'snapshot_id',
      'data_as_of',
      'missing_count',
      'query_snapshot_id',
      'totals',
    ]) ||
    !Array.isArray(v.items) ||
    v.items.length > 200 ||
    !nullable(v.next_cursor, (x) => string(x, 2048)) ||
    !integer(v.scope_version, Number.MAX_SAFE_INTEGER, 1) ||
    !uuid(v.snapshot_id) ||
    !instant(v.data_as_of) ||
    !integer(v.missing_count) ||
    !uuid(v.query_snapshot_id) ||
    !Array.isArray(v.totals) ||
    v.totals.length > 1000
  )
    invalid()
  return {
    ...v,
    items: v.items.map(parseMetricRow),
    totals: v.totals.map(parseMetricTotal),
  } as unknown as Metrics
}
export const metricsApi = {
  /** monitor.read专属当前上下文；只读取得CSRF，不借用其他菜单能力。 */
  async capabilities(signal?: AbortSignal): Promise<{ csrf_token: string }> {
    signal?.throwIfAborted()
    const controller = new AbortController(),
      abort = () => controller.abort(),
      timer = setTimeout(abort, 15000)
    signal?.addEventListener('abort', abort, { once: true })
    let status = 0
    try {
      const response = await fetch(
        `${import.meta.env.VITE_APP_BASE_API}/api/v1/metrics/capabilities`,
        {
          method: 'GET',
          headers: orbitAuthHeaders({ Accept: 'application/json' }),
          credentials: orbitCredentials(),
          cache: 'no-store',
          signal: controller.signal,
        },
      )
      status = response.status
      let data: unknown
      try {
        data = await response.json()
      } catch {
        throw new MetricsError(status, 'INVALID_RESPONSE', '查询准备暂不可用，请重试')
      }
      if (controller.signal.aborted) throw new Error('aborted')
      if (status !== 200) {
        try {
          if (
            !object(data, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
            !string(data.code, 64) ||
            !string(data.message, 1000) ||
            !Array.isArray(data.field_errors) ||
            data.field_errors.length > 100 ||
            typeof data.retryable !== 'boolean' ||
            !uuid(data.request_id)
          )
            invalid()
          const fields = data.field_errors.map(parsePlanFieldError)
          throw new MetricsError(
            status,
            data.code as string,
            data.message as string,
            fields,
            data.retryable,
            data.request_id as string,
            false,
            'server',
          )
        } catch (error) {
          if (error instanceof MetricsError && error.source === 'server') throw error
          throw new MetricsError(status, 'INVALID_ERROR_RESPONSE', '查询准备暂不可用，请重试')
        }
      }
      if (!object(data, ['csrf_token']) || !string(data.csrf_token, 255, 16))
        throw new MetricsError(status, 'INVALID_RESPONSE', '查询准备暂不可用，请重试')
      return { csrf_token: data.csrf_token }
    } catch (error) {
      if (signal?.aborted) throw new DOMException('查询准备已取消', 'AbortError')
      if (error instanceof MetricsError) throw error
      throw new MetricsError(status, 'NETWORK_UNAVAILABLE', '连接中断，请重新准备查询', [], true)
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
    }
  },
  /** 一次原POST，无自动重试；调用方保管冻结意图，任何请求体不进入URL或Storage。 */
  async query(
    value: MetricQuery,
    frozen: FrozenMetricsRequest,
    signal?: AbortSignal,
  ): Promise<Metrics> {
    const body = JSON.stringify(parseMetricQuery(value))
    if (
      !object(frozen, ['csrf_token', 'idempotency_key']) ||
      !string(frozen.csrf_token, 255, 16) ||
      typeof frozen.idempotency_key !== 'string' ||
      !/^[\x20-\x7e]{16,128}$/.test(frozen.idempotency_key)
    )
      invalid(true)
    signal?.throwIfAborted()
    const headers = orbitAuthHeaders({
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRF-Token': frozen.csrf_token,
      'Idempotency-Key': frozen.idempotency_key,
    })
    if (headers['X-CSRF-Token'] !== frozen.csrf_token)
      throw new MetricsError(
        409,
        'CSRF_CONTEXT_CHANGED',
        '会话上下文已变化，请确认原查询后重新查询',
      )
    const controller = new AbortController(),
      abort = () => controller.abort(),
      timer = setTimeout(abort, 15000)
    signal?.addEventListener('abort', abort, { once: true })
    let status = 0
    try {
      const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/metrics/query`, {
        method: 'POST',
        headers,
        credentials: orbitCredentials(),
        cache: 'no-store',
        signal: controller.signal,
        body,
      })
      status = response.status
      let data: unknown
      try {
        data = await response.json()
      } catch {
        throw new MetricsError(
          status,
          'INVALID_RESPONSE',
          '服务响应无法确认，请保留原查询并重试',
          [],
          false,
          null,
          true,
        )
      }
      if (controller.signal.aborted) throw new Error('aborted')
      if (status !== 200) {
        let fields: PlanFieldError[]
        try {
          if (
            !object(data, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
            !string(data.code, 64) ||
            !string(data.message, 1000) ||
            !Array.isArray(data.field_errors) ||
            data.field_errors.length > 100 ||
            typeof data.retryable !== 'boolean' ||
            !uuid(data.request_id)
          )
            invalid()
          fields = data.field_errors.map(parsePlanFieldError)
        } catch {
          throw new MetricsError(
            status,
            'INVALID_ERROR_RESPONSE',
            '服务错误格式无法确认，请保留原查询并重试',
            [],
            false,
            null,
            true,
          )
        }
        const error = data as {
          code: string
          message: string
          retryable: boolean
          request_id: string
        }
        throw new MetricsError(
          status,
          error.code,
          error.message,
          fields,
          error.retryable,
          error.request_id,
          false,
          'server',
        )
      }
      try {
        return parseMetrics(data)
      } catch {
        throw new MetricsError(
          status,
          'INVALID_RESPONSE',
          '查询响应未能完整核验，请保留原意图重试',
          [],
          false,
          null,
          true,
        )
      }
    } catch (error) {
      if (signal?.aborted) throw new DOMException('指标请求已取消', 'AbortError')
      if (error instanceof MetricsError) throw error
      throw new MetricsError(
        status,
        'NETWORK_UNAVAILABLE',
        '指标服务连接中断，结果未知，请使用原查询重试',
        [],
        true,
        null,
        true,
      )
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
    }
  },
}
