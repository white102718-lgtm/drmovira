/** 独立预检/提交合同SDK，尚未接页面；每次请求沿用调用方冻结意图，不生成幂等键、不重试。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { ReferenceApiError } from './references'
import { parseTask, type Task } from './tasks'

export interface ValidatePlan {
  allocation_id: string
  name_reservation_id: string
}
export interface ExecutePlan {
  hash: string
  activate_ack: boolean
}
export interface AllocationRequest {
  asset_ids: string[]
  allow_repeat: boolean
  seed: number
  algorithm_version: 'allocation-v1'
}
export interface FrozenMutation {
  csrf_token: string
  idempotency_key: string
  if_match: string
}
export interface PlanFieldError {
  path: string
  code: string
  message: string
  constraint: string
}
/** 通用HTTP错误处理器的既有nullable兼容，不能扩展200 PlanValidation.errors原schema。 */
export type PlanHttpFieldError = Omit<PlanFieldError, 'constraint'> & { constraint: string | null }
export interface PlanMoney {
  amount: string
  currency: string
}
export interface PlanValidation {
  valid: boolean
  hash: string | null
  expires_at: string | null
  errors: PlanFieldError[]
  campaign_count: number
  adset_count: number
  ad_count: number
  budget_totals: PlanMoney[]
  scope_version: number
  total_dag_node_count: number
}
export interface NameItem {
  slot_key: string
  name: string
  sequence: string
}
export interface NameReservation {
  id: string
  plan_revision: number
  naming_date: string
  items: NameItem[]
}
export interface AllocationItem {
  slot_key: string
  account_id: string
  asset_id: string
  asset_revision: number
}
export interface Allocation {
  id: string
  plan_id: string
  plan_revision: number
  state: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
  task_id: string | null
  algorithm_version: string
  seed: number
  items: AllocationItem[]
  warnings: string[]
  input_hash: string
}
export class LaunchValidationError extends ReferenceApiError {
  constructor(
    status: number,
    code: string,
    message: string,
    public field_errors: PlanHttpFieldError[] = [],
    public retryable = false,
    public request_id: string | null = null,
    /** true只表示客户端无法确认本次写结果，不能改key重复提交或宣告取消成功。 */
    public unknown_result = false,
    public http_status: number | null = null,
  ) {
    super(status, code, message)
  }
}
const uuid = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f\d]{8}(-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(value)
const object = (value: unknown, fields: string[]): value is Record<string, unknown> =>
  !!value &&
  typeof value === 'object' &&
  !Array.isArray(value) &&
  Object.keys(value).length === fields.length &&
  fields.every((field) => Object.hasOwn(value, field))
const text = (value: unknown, max: number, min = 1): value is string =>
  typeof value === 'string' && [...value].length >= min && [...value].length <= max
const integer = (value: unknown, min = 1, max = Number.MAX_SAFE_INTEGER): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max
const hash = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f\d]{64}$/.test(value)
function invalid(request = false): never {
  throw new LaunchValidationError(
    request ? 422 : 502,
    request ? 'FIELD_VALIDATION_FAILED' : 'INVALID_RESPONSE',
    request ? '请求不符合投放合同，请检查字段' : '服务响应不符合投放合同，请重新读取',
  )
}
function array(value: unknown, max: number, check: (entry: unknown) => unknown, min = 0) {
  if (!Array.isArray(value) || value.length < min || value.length > max) invalid()
  for (const entry of value) check(entry)
}
function day(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, date] = value.split('-').map(Number)
  return (
    month >= 1 &&
    month <= 12 &&
    date >= 1 &&
    date <= new Date(Date.UTC(year, month, 0)).getUTCDate()
  )
}
function dateTime(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const match =
    /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-](\d{2}):(\d{2}))$/.exec(value)
  return Boolean(
    match &&
      day(match[1]) &&
      +match[2] <= 23 &&
      +match[3] <= 59 &&
      +match[4] <= 59 &&
      +(match[5] ?? 0) <= 23 &&
      +(match[6] ?? 0) <= 59 &&
      Number.isFinite(Date.parse(value)),
  )
}
export function parsePlanFieldError(value: unknown): PlanFieldError {
  if (
    !object(value, ['path', 'code', 'message', 'constraint']) ||
    !text(value.path, 255) ||
    !text(value.code, 64) ||
    !text(value.message, 1000) ||
    !text(value.constraint, 500, 0)
  )
    invalid()
  return value as unknown as PlanFieldError
}
export function parsePlanHttpFieldError(value: unknown): PlanHttpFieldError {
  if (object(value, ['path', 'code', 'message', 'constraint']) && value.constraint === null) {
    parsePlanFieldError({ ...value, constraint: '' })
    return value as unknown as PlanHttpFieldError
  }
  return parsePlanFieldError(value)
}
export function parsePlanMoney(value: unknown): PlanMoney {
  if (
    !object(value, ['amount', 'currency']) ||
    !text(value.amount, 28) ||
    !/^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/.test(value.amount) ||
    typeof value.currency !== 'string' ||
    !/^[A-Z]{3}$/.test(value.currency)
  )
    invalid()
  return value as unknown as PlanMoney
}
export function parsePlanValidation(value: unknown): PlanValidation {
  if (
    !object(value, [
      'valid',
      'hash',
      'expires_at',
      'errors',
      'campaign_count',
      'adset_count',
      'ad_count',
      'budget_totals',
      'scope_version',
      'total_dag_node_count',
    ]) ||
    typeof value.valid !== 'boolean' ||
    !(value.hash === null || hash(value.hash)) ||
    !(value.expires_at === null || dateTime(value.expires_at)) ||
    !integer(value.scope_version) ||
    ![value.campaign_count, value.adset_count, value.ad_count, value.total_dag_node_count].every(
      (count) => integer(count, 0, 2147483647),
    )
  )
    invalid()
  array(value.errors, 1000, parsePlanFieldError)
  array(value.budget_totals, 100, parsePlanMoney)
  return value as unknown as PlanValidation
}
export function parseNameReservation(value: unknown): NameReservation {
  if (
    !object(value, ['id', 'plan_revision', 'naming_date', 'items']) ||
    !uuid(value.id) ||
    !integer(value.plan_revision) ||
    !day(value.naming_date)
  )
    invalid()
  array(
    value.items,
    10000,
    (entry) => {
      if (
        !object(entry, ['slot_key', 'name', 'sequence']) ||
        !text(entry.slot_key, 512) ||
        !text(entry.name, 200) ||
        !text(entry.sequence, 30) ||
        !/^[0-9]+$/.test(entry.sequence)
      )
        invalid()
    },
    1,
  )
  return value as unknown as NameReservation
}
export function parseAllocation(value: unknown): Allocation {
  if (
    !object(value, [
      'id',
      'plan_id',
      'plan_revision',
      'state',
      'task_id',
      'algorithm_version',
      'seed',
      'items',
      'warnings',
      'input_hash',
    ]) ||
    !uuid(value.id) ||
    !uuid(value.plan_id) ||
    !integer(value.plan_revision) ||
    !['QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED'].includes(String(value.state)) ||
    !(value.task_id === null || uuid(value.task_id)) ||
    !text(value.algorithm_version, 64) ||
    !integer(value.seed, 0, 2147483647) ||
    !hash(value.input_hash)
  )
    invalid()
  array(value.items, 10000, (entry) => {
    if (
      !object(entry, ['slot_key', 'account_id', 'asset_id', 'asset_revision']) ||
      !text(entry.slot_key, 512) ||
      !uuid(entry.account_id) ||
      !uuid(entry.asset_id) ||
      !integer(entry.asset_revision)
    )
      invalid()
  })
  array(value.warnings, 100, (entry) => {
    if (!text(entry, 500)) invalid()
  })
  return value as unknown as Allocation
}
function validateBody(value: unknown) {
  if (
    !object(value, ['allocation_id', 'name_reservation_id']) ||
    !uuid(value.allocation_id) ||
    !uuid(value.name_reservation_id)
  )
    invalid(true)
}
function executeBody(value: unknown) {
  if (
    !object(value, ['hash', 'activate_ack']) ||
    !hash(value.hash) ||
    typeof value.activate_ack !== 'boolean'
  )
    invalid(true)
}
function allocationBody(value: unknown) {
  if (
    !object(value, ['asset_ids', 'allow_repeat', 'seed', 'algorithm_version']) ||
    !Array.isArray(value.asset_ids) ||
    value.asset_ids.length < 1 ||
    value.asset_ids.length > 500 ||
    !Array.from(value.asset_ids).every(uuid) ||
    new Set(value.asset_ids.map((id) => id.toLowerCase())).size !== value.asset_ids.length ||
    typeof value.allow_repeat !== 'boolean' ||
    !integer(value.seed, 0, 2147483647) ||
    value.algorithm_version !== 'allocation-v1'
  )
    invalid(true)
}
function frozen(value: unknown): asserts value is FrozenMutation {
  if (
    !object(value, ['csrf_token', 'idempotency_key', 'if_match']) ||
    typeof value.csrf_token !== 'string' ||
    !/^[\x20-\x7e]{16,255}$/.test(value.csrf_token) ||
    typeof value.idempotency_key !== 'string' ||
    !/^[\x20-\x7e]{16,128}$/.test(value.idempotency_key) ||
    typeof value.if_match !== 'string' ||
    !/^"[1-9][0-9]{0,15}"$/.test(value.if_match) ||
    BigInt(value.if_match.slice(1, -1)) > 9007199254740991n
  )
    invalid(true)
}
function id(value: string) {
  if (!uuid(value)) invalid(true)
  return encodeURIComponent(value)
}
/** 一次请求，无重试；未知写结果完整返回给调用方，原冻结意图仍由调用方保管。 */
async function request<T>(
  path: string,
  expected: 200 | 202,
  parse: (value: unknown) => T,
  mutation?: FrozenMutation,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  if (mutation) frozen(mutation)
  if (signal?.aborted) throw new DOMException('请求已取消且尚未发送', 'AbortError')
  const headers = orbitAuthHeaders({
    Accept: 'application/json',
    ...(mutation
      ? {
          'X-CSRF-Token': mutation.csrf_token,
          'Idempotency-Key': mutation.idempotency_key,
          'If-Match': mutation.if_match,
          ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        }
      : {}),
  })
  if (mutation && headers['X-CSRF-Token'] !== mutation.csrf_token)
    throw new LaunchValidationError(
      409,
      'CSRF_CONTEXT_CHANGED',
      '会话已变化，请确认原操作结果后重新取得写入上下文',
    )
  const controller = new AbortController()
  let timedOut = false,
    httpStatus: number | null = null
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, 15000)
  try {
    const result = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1${path}`, {
      method: mutation ? 'POST' : 'GET',
      headers,
      credentials: orbitCredentials(),
      cache: 'no-store',
      signal: controller.signal,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    httpStatus = result.status
    let value: unknown
    try {
      value = await result.json()
    } catch {
      if (controller.signal.aborted) throw new DOMException('请求中断', 'AbortError')
      throw new LaunchValidationError(
        result.ok ? 502 : result.status,
        'INVALID_RESPONSE',
        '服务响应未能确认，请保留原操作并重新读取',
        [],
        false,
        null,
        Boolean(mutation),
        result.status,
      )
    }
    if (controller.signal.aborted) throw new DOMException('请求中断', 'AbortError')
    if (!result.ok) {
      try {
        if (
          !object(value, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
          !text(value.code, 64) ||
          !text(value.message, 1000) ||
          typeof value.retryable !== 'boolean' ||
          !uuid(value.request_id)
        )
          invalid()
        array(value.field_errors, 100, parsePlanHttpFieldError)
      } catch {
        throw new LaunchValidationError(
          result.status,
          'INVALID_ERROR_RESPONSE',
          '服务错误格式无效，请重新读取当前状态',
          [],
          false,
          null,
          Boolean(mutation),
          result.status,
        )
      }
      // 同键并发准备尚未返回最终Task，保留原意图；一般409仍按明确拒绝处理。
      throw new LaunchValidationError(
        result.status,
        value.code as string,
        value.message as string,
        value.field_errors as PlanHttpFieldError[],
        value.retryable as boolean,
        value.request_id as string,
        Boolean(
          mutation &&
            expected === 202 &&
            path.endsWith('/execute') &&
            result.status === 409 &&
            value.code === 'EXECUTION_PREPARATION_IN_PROGRESS',
        ),
        result.status,
      )
    }
    if (result.status !== expected)
      throw new LaunchValidationError(
        502,
        'UNEXPECTED_HTTP_STATUS',
        '受理状态与合同不一致，请保留原操作并重新读取',
        [],
        false,
        null,
        Boolean(mutation),
        result.status,
      )
    try {
      return parse(value)
    } catch {
      throw new LaunchValidationError(
        502,
        'INVALID_RESPONSE',
        '服务响应不符合投放合同，请保留原操作并重新读取',
        [],
        false,
        null,
        Boolean(mutation),
        result.status,
      )
    }
  } catch (cause) {
    if (cause instanceof LaunchValidationError) throw cause
    if (controller.signal.aborted && !mutation && signal?.aborted)
      throw new DOMException('读取已取消', 'AbortError')
    throw new LaunchValidationError(
      0,
      timedOut
        ? 'REQUEST_TIMEOUT'
        : controller.signal.aborted
          ? 'REQUEST_ABORTED'
          : 'NETWORK_UNAVAILABLE',
      mutation
        ? '本次写入结果尚未确认，请保留原幂等键与请求重试，勿重新提交新操作'
        : '读取中断，请重新读取',
      [],
      true,
      null,
      Boolean(mutation),
      httpStatus,
    )
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', abort)
  }
}
export const launchValidationApi = {
  reserveNames: (planId: string, mutation: FrozenMutation, signal?: AbortSignal) =>
    request(
      `/launch-plans/${id(planId)}/campaign-names`,
      200,
      parseNameReservation,
      mutation,
      undefined,
      signal,
    ),
  allocate: (
    planId: string,
    value: AllocationRequest,
    mutation: FrozenMutation,
    signal?: AbortSignal,
  ) => {
    allocationBody(value)
    return request(
      `/launch-plans/${id(planId)}/allocations`,
      202,
      (value) => {
        const parsed = parseAllocation(value)
        if (parsed.plan_id.toLowerCase() !== planId.toLowerCase()) invalid()
        return parsed
      },
      mutation,
      value,
      signal,
    )
  },
  allocation: (planId: string, allocationId: string, signal?: AbortSignal) =>
    request(
      `/launch-plans/${id(planId)}/allocations/${id(allocationId)}`,
      200,
      (value) => {
        const parsed = parseAllocation(value)
        if (
          parsed.id.toLowerCase() !== allocationId.toLowerCase() ||
          parsed.plan_id.toLowerCase() !== planId.toLowerCase()
        )
          invalid()
        return parsed
      },
      undefined,
      undefined,
      signal,
    ),
  validate: (
    planId: string,
    value: ValidatePlan,
    mutation: FrozenMutation,
    signal?: AbortSignal,
  ) => {
    validateBody(value)
    return request(
      `/launch-plans/${id(planId)}/validate`,
      200,
      parsePlanValidation,
      mutation,
      value,
      signal,
    )
  },
  execute: (
    planId: string,
    value: ExecutePlan,
    mutation: FrozenMutation,
    signal?: AbortSignal,
  ): Promise<Task> => {
    executeBody(value)
    return request(`/launch-plans/${id(planId)}/execute`, 202, parseTask, mutation, value, signal)
  },
}
