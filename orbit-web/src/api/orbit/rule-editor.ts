/** 规则编辑技术GET合同；不调用账户/指标菜单，不发行写入或执行资格。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { parseMetricProfile, type MetricProfile } from './metric-profiles'
import { parsePlanHttpFieldError } from './launch-validation'
import { RuleApiError } from './rules'

export type RuleEditorTarget =
  | { action: 'CREATE'; rule_id?: never }
  | { action: 'UPDATE'; rule_id: string }
export type RuleEditorQuery = RuleEditorTarget &
  (
    | { kind: 'OWNER'; owner_user_id?: never; owner_team_id?: never }
    | { kind: 'PROFILE'; owner_user_id: string; owner_team_id: string }
  ) & { q?: string; page_size?: 20 | 50 | 100 | 200; cursor?: string }
export interface RuleOwnerOption {
  id: string
  team_id: string
  name: string
  team_name: string
}
export interface RuleEditorContext {
  action: 'CREATE' | 'UPDATE'
  rule_id: string | null
  rule_revision: number | null
  editable: boolean
  csrf_token: string
  default_ownership: { owner_user_id: string; owner_team_id: string }
  selected_owner: { item: RuleOwnerOption | null; can_keep: boolean }
  selected_profile: {
    id: string
    bound_version: string
    current: MetricProfile | null
    status: 'CURRENT' | 'CHANGED' | 'UNAVAILABLE'
  } | null
}
export interface RuleEditorPage<T> {
  items: T[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export class RuleEditorApiError extends RuleApiError {}

const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v)
const safeText = (v: unknown, max: number, min = 1): v is string =>
  typeof v === 'string' &&
  [...v].length >= min &&
  [...v].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(v)
const positive = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v > 0
const record = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)
const object = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  record(v) && Object.keys(v).length === keys.length && keys.every((k) => Object.hasOwn(v, k))
function invalid(path = '/', response = true): never {
  throw new RuleEditorApiError(
    response ? 502 : 422,
    response ? 'INVALID_RESPONSE' : 'FIELD_INVALID',
    response ? '规则编辑辅助响应不符合合同' : '规则编辑候选参数无效',
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
function utc(v: unknown): v is string {
  if (
    typeof v !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|\+00:00)$/.test(v) ||
    !Number.isFinite(Date.parse(v))
  )
    return false
  const date = new Date(v)
  return !v.startsWith('0000') && date.toISOString().slice(0, 10) === v.slice(0, 10)
}
export function parseRuleOwnerOption(v: unknown): RuleOwnerOption {
  if (
    !object(v, ['id', 'team_id', 'name', 'team_name']) ||
    !uuid(v.id) ||
    !uuid(v.team_id) ||
    !safeText(v.name, 4096) ||
    !safeText(v.team_name, 4096)
  )
    invalid()
  return v as unknown as RuleOwnerOption
}
export function parseRuleEditorContext(v: unknown): RuleEditorContext {
  if (
    !object(v, [
      'action',
      'rule_id',
      'rule_revision',
      'editable',
      'csrf_token',
      'default_ownership',
      'selected_owner',
      'selected_profile',
    ]) ||
    !['CREATE', 'UPDATE'].includes(String(v.action)) ||
    typeof v.editable !== 'boolean' ||
    !safeText(v.csrf_token, 255, 16) ||
    !object(v.default_ownership, ['owner_user_id', 'owner_team_id']) ||
    !uuid(v.default_ownership.owner_user_id) ||
    !uuid(v.default_ownership.owner_team_id) ||
    !object(v.selected_owner, ['item', 'can_keep']) ||
    typeof v.selected_owner.can_keep !== 'boolean'
  )
    invalid()
  if (v.selected_owner.item === null) {
    if (v.selected_owner.can_keep) invalid()
  } else {
    const owner = parseRuleOwnerOption(v.selected_owner.item)
    if (
      owner.id.toLowerCase() !== v.default_ownership.owner_user_id.toLowerCase() ||
      owner.team_id.toLowerCase() !== v.default_ownership.owner_team_id.toLowerCase()
    )
      invalid()
  }
  if (v.action === 'CREATE') {
    if (
      v.rule_id !== null ||
      v.rule_revision !== null ||
      v.selected_profile !== null ||
      !v.editable
    )
      invalid()
  } else {
    if (!uuid(v.rule_id) || !positive(v.rule_revision)) invalid()
    const profile = v.selected_profile
    if (
      !object(profile, ['id', 'bound_version', 'current', 'status']) ||
      !uuid(profile.id) ||
      !safeText(profile.bound_version, 64) ||
      !['CURRENT', 'CHANGED', 'UNAVAILABLE'].includes(String(profile.status))
    )
      invalid()
    if (profile.current === null) {
      if (profile.status !== 'UNAVAILABLE') invalid()
    } else {
      let current: MetricProfile
      try {
        current = parseMetricProfile(profile.current)
      } catch {
        invalid()
      }
      if (
        current.id.toLowerCase() !== profile.id.toLowerCase() ||
        profile.status !== (current.version === profile.bound_version ? 'CURRENT' : 'CHANGED')
      )
        invalid()
    }
  }
  return v as unknown as RuleEditorContext
}
function parsePage<T>(
  v: unknown,
  parse: (item: unknown) => T,
  id: (item: T) => string,
): RuleEditorPage<T> {
  if (
    !object(v, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(v.items) ||
    v.items.length > 200 ||
    !(v.next_cursor === null || safeText(v.next_cursor, 2048)) ||
    !utc(v.data_as_of) ||
    !positive(v.scope_version)
  )
    invalid()
  let items: T[]
  try {
    items = v.items.map(parse)
  } catch {
    invalid()
  }
  if (
    new Set(items.map((item) => id(item).toLowerCase())).size !== items.length ||
    (!items.length && v.next_cursor !== null)
  )
    invalid()
  return {
    items,
    next_cursor: v.next_cursor,
    data_as_of: v.data_as_of,
    scope_version: v.scope_version,
  }
}
export const parseRuleOwnerPage = (v: unknown) =>
  parsePage(v, parseRuleOwnerOption, (item) => item.id)
export const parseRuleProfilePage = (v: unknown) =>
  parsePage(v, parseMetricProfile, (item) => item.id)

function query(value: unknown, options: boolean): URLSearchParams {
  const allowed = [
    'action',
    'rule_id',
    ...(options ? ['kind', 'owner_user_id', 'owner_team_id', 'q', 'page_size', 'cursor'] : []),
  ]
  if (!record(value) || Object.keys(value).some((k) => !allowed.includes(k))) invalid('/', false)
  const result = new URLSearchParams()
  if (value.action !== 'CREATE' && value.action !== 'UPDATE') invalid('/action', false)
  result.set('action', value.action)
  if (value.action === 'CREATE') {
    if (Object.hasOwn(value, 'rule_id')) invalid('/rule_id', false)
  } else {
    if (!uuid(value.rule_id)) invalid('/rule_id', false)
    result.set('rule_id', value.rule_id.toLowerCase())
  }
  if (!options) return result
  if (value.kind !== 'OWNER' && value.kind !== 'PROFILE') invalid('/kind', false)
  result.set('kind', value.kind)
  if (value.kind === 'OWNER') {
    if (Object.hasOwn(value, 'owner_user_id') || Object.hasOwn(value, 'owner_team_id'))
      invalid('/owner_user_id', false)
  } else {
    for (const key of ['owner_user_id', 'owner_team_id']) {
      if (!uuid(value[key])) invalid('/' + key, false)
      result.set(key, value[key].toLowerCase())
    }
  }
  if (value.q !== undefined) {
    if (typeof value.q !== 'string' || /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(value.q))
      invalid('/q', false)
    const q = value.q === '' ? '' : value.q.trim().normalize('NFC')
    if (value.q !== '' && !safeText(q, 100)) invalid('/q', false)
    if (value.kind === 'PROFILE' && q && !uuid(q)) invalid('/q', false)
    result.set('q', value.kind === 'PROFILE' ? q.toLowerCase() : q)
  }
  if (value.page_size !== undefined) {
    if (typeof value.page_size !== 'number' || ![20, 50, 100, 200].includes(value.page_size))
      invalid('/page_size', false)
    result.set('page_size', String(value.page_size))
  }
  if (value.cursor !== undefined) {
    if (!safeText(value.cursor, 2048)) invalid('/cursor', false)
    result.set('cursor', value.cursor)
  }
  return result
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
      throw new RuleEditorApiError(502, 'INVALID_RESPONSE', '规则编辑来源响应未能确认')
    }
    controller.signal.throwIfAborted()
    if (started !== authContext())
      throw new RuleEditorApiError(
        409,
        'SESSION_CONTEXT_CHANGED',
        '认证上下文已变化，已丢弃迟到响应',
      )
    if (!response.ok) {
      if (
        !object(value, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
        !safeText(value.code, 64) ||
        !safeText(value.message, 1000) ||
        !Array.isArray(value.field_errors) ||
        value.field_errors.length > 100 ||
        typeof value.retryable !== 'boolean' ||
        !uuid(value.request_id)
      )
        throw new RuleEditorApiError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则编辑来源错误响应不符合合同',
        )
      let fields
      try {
        fields = value.field_errors.map(parsePlanHttpFieldError)
      } catch {
        throw new RuleEditorApiError(
          status,
          'INVALID_ERROR_RESPONSE',
          '规则编辑来源错误响应不符合合同',
        )
      }
      throw new RuleEditorApiError(
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
      throw new RuleEditorApiError(502, 'UNEXPECTED_HTTP_STATUS', '规则编辑辅助只接受200响应')
    try {
      return parse(value)
    } catch {
      return invalid()
    }
  } catch (e) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (e instanceof RuleEditorApiError) throw e
    throw new RuleEditorApiError(
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
function options(
  queryValue: RuleEditorQuery & { kind: 'OWNER' },
  signal?: AbortSignal,
): Promise<RuleEditorPage<RuleOwnerOption>>
function options(
  queryValue: RuleEditorQuery & { kind: 'PROFILE' },
  signal?: AbortSignal,
): Promise<RuleEditorPage<MetricProfile>>
function options(
  queryValue: RuleEditorQuery,
  signal?: AbortSignal,
): Promise<RuleEditorPage<RuleOwnerOption | MetricProfile>>
async function options(
  queryValue: RuleEditorQuery,
  signal?: AbortSignal,
): Promise<RuleEditorPage<RuleOwnerOption | MetricProfile>> {
  const parameters = query(queryValue, true)
  return get(
    `editor-options?${parameters}`,
    (value) => {
      const result =
        parameters.get('kind') === 'OWNER' ? parseRuleOwnerPage(value) : parseRuleProfilePage(value)
      if (result.items.length > Number(parameters.get('page_size') ?? 50)) invalid()
      if (
        parameters.get('kind') === 'PROFILE' &&
        parameters.get('q') &&
        result.items.some((item) => item.id.toLowerCase() !== parameters.get('q'))
      )
        invalid()
      return result
    },
    signal,
  )
}
export const ruleEditorApi = {
  async context(target: RuleEditorTarget, signal?: AbortSignal): Promise<RuleEditorContext> {
    const parameters = query(target, false)
    return get(
      `edit-context?${parameters}`,
      (value) => {
        const result = parseRuleEditorContext(value)
        if (
          result.action !== parameters.get('action') ||
          result.rule_id !== parameters.get('rule_id')
        )
          invalid()
        return result
      },
      signal,
    )
  },
  options,
}
