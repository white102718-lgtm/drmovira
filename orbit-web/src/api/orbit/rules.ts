/** 原Rule九接口与专属CSRF辅助读取；严格合同，不发行模拟/调度资格。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parsePlanHttpFieldError, type PlanHttpFieldError } from './launch-validation'
import { ReferenceApiError } from './references'

export const ruleMetrics = [
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
] as const
export type RuleMetric = (typeof ruleMetrics)[number]
export type RuleLogic = 'AND' | 'OR'
export type RuleState = 'DRAFT' | 'ENABLED' | 'PAUSED' | 'ARCHIVED'
export type RuleRunState = 'RUNNING' | 'SUCCEEDED' | 'SKIPPED' | 'UNKNOWN' | 'FAILED'
export type RuleAction = 'CREATE' | 'UPDATE' | 'ENABLE' | 'PAUSE' | 'ARCHIVE' | 'SIMULATE'
export interface RuleCondition {
  metric: RuleMetric
  operator: 'GT' | 'GTE' | 'LT' | 'LTE' | 'EQ' | 'NEQ'
  threshold: string
}
export interface RuleConditionGroup {
  logic: RuleLogic
  conditions: RuleCondition[]
}
export interface RuleSchedule {
  frequency: 'INTERVAL' | 'DAILY' | 'WEEKLY'
  interval_minutes: number | null
  time_of_day: string | null
  weekday: number | null
  timezone: string
  start_date: string
  end_date: string
}
export interface RuleWrite {
  name: string
  ownership: { owner_user_id: string; owner_team_id: string }
  target_level: 'CAMPAIGN' | 'ADSET' | 'AD'
  scope_snapshot_id: string
  logic: RuleLogic
  groups: RuleConditionGroup[]
  window: 'TODAY' | 'YESTERDAY' | 'LAST_3D' | 'LAST_7D'
  metric_profile_id: string
  schedule: RuleSchedule
  cooldown_minutes: number
  max_daily: number
}
export interface Rule extends RuleWrite {
  id: string
  revision: number
  state: RuleState
  next_run_at: string | null
}
export interface ConditionResult {
  entity_id: string
  condition_index: number
  value: string | null
  result: 'TRUE' | 'FALSE' | 'UNKNOWN'
  reason_code: string | null
}
export interface RuleSimulation {
  id: string
  rule_id: string
  revision: number
  snapshot_id: string
  hash: string
  account_count: number
  scanned_count: number
  hit_count: number
  unknown_count: number
  false_count: number
  conditions: ConditionResult[]
  expires_at: string
  next_cursor: string | null
}
export interface RuleRun {
  id: string
  rule_id: string
  rule_revision: number
  schedule_slot: string
  snapshot_id: string
  state: RuleRunState
  hit_count: number
  reason_code: string | null
}
export interface RulePage<T = Rule> {
  items: T[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export interface RuleQuery {
  q?: string
  cursor?: string
  page_size?: 20 | 50 | 100 | 200
  status?: RuleState
  date_from?: string
  date_to?: string
  operator_user_id?: string
  channel_id?: string
  metric_profile_id?: string
  entity_type?: 'CAMPAIGN' | 'ADSET' | 'AD'
}
export type RuleRunQuery = Omit<RuleQuery, 'status'> & { status?: RuleRunState }
export interface RuleMutation {
  csrf_token: string
  idempotency_key: string
}
export interface RuleVersionMutation extends RuleMutation {
  if_match: string
}
export class RuleApiError extends ReferenceApiError {
  constructor(
    status: number,
    code: string,
    message: string,
    public field_errors: PlanHttpFieldError[] = [],
    public retryable = false,
    public request_id: string | null = null,
    public unknown_result = false,
    public source: 'local' | 'server' = 'local',
  ) {
    super(status, code, message)
  }
}
const writeFields = [
  'name',
  'ownership',
  'target_level',
  'scope_snapshot_id',
  'logic',
  'groups',
  'window',
  'metric_profile_id',
  'schedule',
  'cooldown_minutes',
  'max_daily',
]
const ruleStates = ['DRAFT', 'ENABLED', 'PAUSED', 'ARCHIVED']
const runStates = ['RUNNING', 'SUCCEEDED', 'SKIPPED', 'UNKNOWN', 'FAILED']
const actions = ['CREATE', 'UPDATE', 'ENABLE', 'PAUSE', 'ARCHIVE', 'SIMULATE']
const object = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  !!v &&
  typeof v === 'object' &&
  !Array.isArray(v) &&
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k))
const text = (v: unknown, max: number, min = 1): v is string =>
  typeof v === 'string' &&
  [...v].length >= min &&
  [...v].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(v)
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v)
const integer = (v: unknown, min = 0, max = 2147483647): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v >= min && v <= max
const decimal = (v: unknown): v is string =>
  typeof v === 'string' && v.length <= 28 && /^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/.test(v)
const member = (v: unknown, choices: readonly string[]): v is string =>
  typeof v === 'string' && choices.includes(v)
const nullable = (v: unknown, check: (v: unknown) => boolean) => v === null || check(v)
const day = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}$/.test(v) &&
  !v.startsWith('0000') &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 10) === v
const utc = (v: unknown): v is string =>
  typeof v === 'string' &&
  v.length <= 64 &&
  /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|\+00:00)$/.test(v) &&
  day(v.slice(0, 10)) &&
  Number.isFinite(Date.parse(v))
const cursor = (v: unknown) => text(v, 2048)
const clone = <T>(v: unknown): T => JSON.parse(JSON.stringify(v)) as T
function invalid(): never {
  throw new RuleApiError(502, 'INVALID_RESPONSE', '规则数据不符合原合同')
}
function local<T>(parse: (v: unknown) => T, value: unknown): T {
  try {
    return parse(value)
  } catch {
    throw new RuleApiError(422, 'FIELD_VALIDATION_FAILED', '规则请求字段不符合原合同')
  }
}
export function parseRuleCondition(value: unknown): RuleCondition {
  if (
    !object(value, ['metric', 'operator', 'threshold']) ||
    !member(value.metric, ruleMetrics) ||
    !member(value.operator, ['GT', 'GTE', 'LT', 'LTE', 'EQ', 'NEQ']) ||
    !decimal(value.threshold)
  )
    invalid()
  const [whole, fraction = ''] = value.threshold.split('.')
  const scaled = BigInt(whole) * 1000000n + BigInt(fraction.padEnd(6, '0'))
  if (
    ['impressions', 'clicks', 'registrations', 'purchases'].includes(value.metric) &&
    scaled % 1000000n
  )
    invalid()
  const bound =
    value.metric === 'ctr'
      ? 100n
      : value.metric === 'roas'
        ? 1000000n
        : ['spend', 'purchase_value', 'cpm', 'cpc', 'cpa'].includes(value.metric)
          ? 1000000000n
          : null
  if (bound !== null && scaled > bound * 1000000n) invalid()
  return clone(value)
}
export function parseRuleSchedule(value: unknown): RuleSchedule {
  if (
    !object(value, [
      'frequency',
      'interval_minutes',
      'time_of_day',
      'weekday',
      'timezone',
      'start_date',
      'end_date',
    ]) ||
    !member(value.frequency, ['INTERVAL', 'DAILY', 'WEEKLY']) ||
    !text(value.timezone, 64) ||
    !day(value.start_date) ||
    !day(value.end_date)
  )
    invalid()
  const span = (Date.parse(value.end_date) - Date.parse(value.start_date)) / 86400000
  if (span < 0 || span >= 366) invalid()
  try {
    new Intl.DateTimeFormat('en', { timeZone: value.timezone }).format()
  } catch {
    invalid()
  }
  if (value.frequency === 'INTERVAL') {
    if (
      !integer(value.interval_minutes, 15, 1440) ||
      value.time_of_day !== null ||
      value.weekday !== null
    )
      invalid()
  } else if (
    value.interval_minutes !== null ||
    typeof value.time_of_day !== 'string' ||
    !/^([01]\d|2[0-3]):[0-5]\d$/.test(value.time_of_day) ||
    (value.frequency === 'WEEKLY' ? !integer(value.weekday, 1, 7) : value.weekday !== null)
  )
    invalid()
  return clone(value)
}
export function parseRuleWrite(value: unknown): RuleWrite {
  if (
    !object(value, writeFields) ||
    !text(value.name, Number.MAX_SAFE_INTEGER) ||
    !text(value.name.normalize('NFC').trim(), 80) ||
    !object(value.ownership, ['owner_user_id', 'owner_team_id']) ||
    !uuid(value.ownership.owner_user_id) ||
    !uuid(value.ownership.owner_team_id) ||
    !member(value.target_level, ['CAMPAIGN', 'ADSET', 'AD']) ||
    !uuid(value.scope_snapshot_id) ||
    !uuid(value.metric_profile_id) ||
    !member(value.logic, ['AND', 'OR']) ||
    !member(value.window, ['TODAY', 'YESTERDAY', 'LAST_3D', 'LAST_7D']) ||
    !integer(value.cooldown_minutes, 0, 10080) ||
    !integer(value.max_daily, 1, 1000) ||
    !Array.isArray(value.groups) ||
    value.groups.length < 1 ||
    value.groups.length > 5
  )
    invalid()
  let count = 0
  for (const group of value.groups) {
    if (
      !object(group, ['logic', 'conditions']) ||
      !member(group.logic, ['AND', 'OR']) ||
      !Array.isArray(group.conditions) ||
      group.conditions.length < 1 ||
      group.conditions.length > 10
    )
      invalid()
    count += group.conditions.length
    if (count > 20) invalid()
    group.conditions.forEach(parseRuleCondition)
  }
  parseRuleSchedule(value.schedule)
  return clone({ ...value, name: value.name.normalize('NFC').trim() })
}
export function parseRule(value: unknown): Rule {
  if (
    !object(value, [...writeFields, 'id', 'revision', 'state', 'next_run_at']) ||
    !uuid(value.id) ||
    !integer(value.revision, 1, Number.MAX_SAFE_INTEGER) ||
    !member(value.state, ruleStates) ||
    !nullable(value.next_run_at, utc)
  )
    invalid()
  parseRuleWrite(Object.fromEntries(writeFields.map((key) => [key, value[key]])))
  return clone(value)
}
export function parseConditionResult(value: unknown): ConditionResult {
  if (
    !object(value, ['entity_id', 'condition_index', 'value', 'result', 'reason_code']) ||
    !uuid(value.entity_id) ||
    !integer(value.condition_index) ||
    !nullable(value.value, decimal) ||
    !member(value.result, ['TRUE', 'FALSE', 'UNKNOWN']) ||
    !nullable(value.reason_code, (v) => text(v, 64))
  )
    invalid()
  return clone(value)
}
export function parseRuleSimulation(value: unknown): RuleSimulation {
  if (
    !object(value, [
      'id',
      'rule_id',
      'revision',
      'snapshot_id',
      'hash',
      'account_count',
      'scanned_count',
      'hit_count',
      'unknown_count',
      'false_count',
      'conditions',
      'expires_at',
      'next_cursor',
    ]) ||
    !uuid(value.id) ||
    !uuid(value.rule_id) ||
    !uuid(value.snapshot_id) ||
    !integer(value.revision, 1, Number.MAX_SAFE_INTEGER) ||
    typeof value.hash !== 'string' ||
    !/^[a-f\d]{64}$/.test(value.hash) ||
    !utc(value.expires_at) ||
    !nullable(value.next_cursor, cursor) ||
    !Array.isArray(value.conditions) ||
    value.conditions.length > 10000
  )
    invalid()
  for (const field of [
    'account_count',
    'scanned_count',
    'hit_count',
    'unknown_count',
    'false_count',
  ]) {
    if (!integer(value[field])) invalid()
  }
  if (
    (value.hit_count as number) +
      (value.unknown_count as number) +
      (value.false_count as number) !==
    value.scanned_count
  )
    invalid()
  value.conditions.forEach(parseConditionResult)
  return clone(value)
}
export function parseRuleRun(value: unknown): RuleRun {
  if (
    !object(value, [
      'id',
      'rule_id',
      'rule_revision',
      'schedule_slot',
      'snapshot_id',
      'state',
      'hit_count',
      'reason_code',
    ]) ||
    !uuid(value.id) ||
    !uuid(value.rule_id) ||
    !uuid(value.snapshot_id) ||
    !integer(value.rule_revision, 1, Number.MAX_SAFE_INTEGER) ||
    !utc(value.schedule_slot) ||
    !member(value.state, runStates) ||
    !integer(value.hit_count) ||
    !nullable(value.reason_code, (v) => text(v, 64))
  )
    invalid()
  return clone(value)
}
function page<T>(value: unknown, parse: (v: unknown) => T): RulePage<T> {
  if (
    !object(value, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(value.items) ||
    value.items.length > 200 ||
    !nullable(value.next_cursor, cursor) ||
    !utc(value.data_as_of) ||
    !integer(value.scope_version, 1, Number.MAX_SAFE_INTEGER)
  )
    invalid()
  value.items.forEach(parse)
  return clone(value)
}
export const parseRulePage = (v: unknown) => page(v, parseRule)
export const parseRuleRunPage = (v: unknown) => page(v, parseRuleRun)
function queryString(value: RuleQuery | RuleRunQuery, runs = false): string {
  const keys = [
    'q',
    'cursor',
    'page_size',
    'status',
    'date_from',
    'date_to',
    'operator_user_id',
    'channel_id',
    'metric_profile_id',
    'entity_type',
  ]
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    Object.keys(value).some((k) => !keys.includes(k))
  )
    invalid()
  const normalized = { ...value }
  if (typeof normalized.q === 'string') normalized.q = normalized.q.normalize('NFC')
  for (const [key, v] of Object.entries(normalized)) {
    if (
      key === 'page_size'
        ? typeof v !== 'number' || ![20, 50, 100, 200].includes(v)
        : key === 'q'
          ? !text(v, 100, 0)
          : key === 'cursor'
            ? !cursor(v)
            : key === 'status'
              ? !member(v, runs ? runStates : ruleStates)
              : key.startsWith('date_')
                ? !day(v)
                : key === 'channel_id'
                  ? !text(v, 64)
                  : key === 'entity_type'
                    ? !member(v, ['CAMPAIGN', 'ADSET', 'AD'])
                    : !uuid(v)
    )
      invalid()
  }
  if (normalized.date_from && normalized.date_to && normalized.date_from > normalized.date_to)
    invalid()
  return new URLSearchParams(Object.entries(normalized).map(([k, v]) => [k, String(v)])).toString()
}
function frozen(value: RuleMutation | RuleVersionMutation, versioned: boolean) {
  if (
    !object(
      value,
      versioned ? ['csrf_token', 'idempotency_key', 'if_match'] : ['csrf_token', 'idempotency_key'],
    ) ||
    !text(value.csrf_token, 255, 16) ||
    typeof value.idempotency_key !== 'string' ||
    !/^[\x20-\x7e]{16,128}$/.test(value.idempotency_key)
  )
    invalid()
  if (
    versioned &&
    (typeof value.if_match !== 'string' ||
      !/^"[1-9]\d{0,15}"$/.test(value.if_match) ||
      BigInt(value.if_match.slice(1, -1)) > BigInt(Number.MAX_SAFE_INTEGER))
  )
    invalid()
  return {
    'X-CSRF-Token': value.csrf_token,
    'Idempotency-Key': value.idempotency_key,
    ...(versioned ? { 'If-Match': value.if_match as string } : {}),
  }
}
function context() {
  return JSON.stringify([
    orbitCredentials(),
    Object.entries(orbitAuthHeaders()).sort(([a], [b]) => a.localeCompare(b)),
  ])
}
async function transport<T>(
  path: string,
  parse: (v: unknown) => T,
  init: RequestInit = {},
  expected = 200,
): Promise<T> {
  const mutation = init.method !== undefined && init.method !== 'GET'
  init.signal?.throwIfAborted()
  const started = context()
  const supplied = new Headers(init.headers)
  const headers = orbitAuthHeaders({
    Accept: 'application/json',
    'Content-Type': 'application/json',
    ...Object.fromEntries(supplied.entries()),
  })
  if (mutation && new Headers(headers).get('x-csrf-token') !== supplied.get('x-csrf-token'))
    throw new RuleApiError(409, 'CSRF_CONTEXT_CHANGED', '会话已变化，请保留原操作并重新读取')
  const controller = new AbortController()
  const abort = () => controller.abort()
  const timer = setTimeout(abort, 15000)
  init.signal?.addEventListener('abort', abort, { once: true })
  let status = 0
  try {
    const result = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1${path}`, {
      ...init,
      signal: controller.signal,
      headers,
      credentials: orbitCredentials(),
      cache: 'no-store',
    })
    status = result.status
    let data: unknown
    try {
      data = await result.json()
    } catch {
      throw new RuleApiError(
        status || 502,
        'INVALID_RESPONSE',
        '服务响应未能确认',
        [],
        false,
        null,
        mutation,
      )
    }
    controller.signal.throwIfAborted()
    if (started !== context())
      throw new RuleApiError(
        409,
        'SESSION_CONTEXT_CHANGED',
        '会话已变化，已丢弃迟到响应',
        [],
        false,
        null,
        mutation,
      )
    if (!result.ok) {
      if (
        !object(data, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
        !text(data.code, 64) ||
        !text(data.message, 1000) ||
        !Array.isArray(data.field_errors) ||
        data.field_errors.length > 100 ||
        typeof data.retryable !== 'boolean' ||
        !uuid(data.request_id)
      )
        throw new RuleApiError(
          status,
          'INVALID_ERROR_RESPONSE',
          '服务错误响应未能确认',
          [],
          false,
          null,
          mutation,
        )
      let fields: PlanHttpFieldError[]
      try {
        fields = data.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleApiError(
          status,
          'INVALID_ERROR_RESPONSE',
          '服务错误响应未能确认',
          [],
          false,
          null,
          mutation,
        )
      }
      throw new RuleApiError(
        status,
        data.code,
        data.message,
        fields,
        data.retryable,
        data.request_id,
        false,
        'server',
      )
    }
    if (status !== expected)
      throw new RuleApiError(
        502,
        'UNEXPECTED_HTTP_STATUS',
        '服务状态不符合原合同',
        [],
        false,
        null,
        mutation,
      )
    try {
      return parse(data)
    } catch {
      throw new RuleApiError(
        502,
        'INVALID_RESPONSE',
        '服务响应不符合原规则合同',
        [],
        false,
        null,
        mutation,
      )
    }
  } catch (error) {
    if (error instanceof RuleApiError) throw error
    if (!mutation && init.signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    throw new RuleApiError(
      status,
      'NETWORK_UNAVAILABLE',
      '连接中断，请保留原请求及幂等键',
      [],
      true,
      null,
      mutation,
    )
  } finally {
    clearTimeout(timer)
    init.signal?.removeEventListener('abort', abort)
  }
}
function path(id: string) {
  if (!uuid(id)) local(() => invalid(), id)
  return `/rules/${encodeURIComponent(id)}`
}
function mutation<T>(
  url: string,
  method: string,
  body: unknown,
  auth: RuleMutation | RuleVersionMutation,
  parse: (v: unknown) => T,
  signal?: AbortSignal,
  expected = 200,
) {
  const headers = local(() => frozen(auth, url !== '/rules'), auth)
  // 立即序列化；在途调用方修改对象不会改变该次冻结意图，不生成新key或自动重试。
  return transport(
    url,
    parse,
    { method, headers, signal, ...(body === undefined ? {} : { body: JSON.stringify(body) }) },
    expected,
  )
}
function reason(value: unknown) {
  if (!object(value, ['reason']) || !text(value.reason, 1000) || !value.reason.trim()) invalid()
  return clone(value)
}
export const rulesApi = {
  async capabilities(action: RuleAction, signal?: AbortSignal) {
    if (!actions.includes(action))
      return Promise.reject(new RuleApiError(422, 'FIELD_VALIDATION_FAILED', '规则动作无效'))
    return transport(
      `/rules/capabilities?${new URLSearchParams({ action })}`,
      (v) => {
        if (!object(v, ['csrf_token']) || !text(v.csrf_token, 255, 16)) invalid()
        return { csrf_token: v.csrf_token }
      },
      { signal },
    )
  },
  async list(query: RuleQuery = {}, signal?: AbortSignal) {
    return transport(`/rules?${local(() => queryString(query), query)}`, parseRulePage, { signal })
  },
  async get(id: string, signal?: AbortSignal) {
    return transport(path(id), parseRule, { signal })
  },
  async create(body: RuleWrite, auth: RuleMutation, signal?: AbortSignal) {
    return mutation('/rules', 'POST', local(parseRuleWrite, body), auth, parseRule, signal, 201)
  },
  async update(id: string, body: RuleWrite, auth: RuleVersionMutation, signal?: AbortSignal) {
    return mutation(path(id), 'PUT', local(parseRuleWrite, body), auth, parseRule, signal)
  },
  async archive(
    id: string,
    body: { reason: string },
    auth: RuleVersionMutation,
    signal?: AbortSignal,
  ) {
    return mutation(path(id) + '/archive', 'POST', local(reason, body), auth, parseRule, signal)
  },
  async pause(
    id: string,
    body: { reason: string },
    auth: RuleVersionMutation,
    signal?: AbortSignal,
  ) {
    return mutation(path(id) + '/pause', 'POST', local(reason, body), auth, parseRule, signal)
  },
  async simulate(id: string, auth: RuleVersionMutation, signal?: AbortSignal) {
    return mutation(path(id) + '/simulate', 'POST', undefined, auth, parseRuleSimulation, signal)
  },
  async enable(
    id: string,
    body: { simulation_id: string },
    auth: RuleVersionMutation,
    signal?: AbortSignal,
  ) {
    const parsed = local((v) => {
      if (!object(v, ['simulation_id']) || !uuid(v.simulation_id)) invalid()
      return clone(v)
    }, body)
    return mutation(path(id) + '/enable', 'POST', parsed, auth, parseRule, signal)
  },
  async runs(id: string, query: RuleRunQuery = {}, signal?: AbortSignal) {
    return transport(
      `${path(id)}/runs?${local(() => queryString(query, true), query)}`,
      parseRuleRunPage,
      { signal },
    )
  },
}
