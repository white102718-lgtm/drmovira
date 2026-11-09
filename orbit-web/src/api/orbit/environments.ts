import { orbitAuthHeaders, orbitCredentials } from './authentication'
/** 执行机登记数据；该地址只交由执行机使用，浏览器与控制面不得探测。 */
export interface AgentWrite {
  name: string
  endpoint: string
  probe_interval: number
}
export interface Agent extends AgentWrite {
  id: string
  revision: number
  state: 'READY' | 'SUSPECT' | 'OFFLINE' | 'REVOKED'
  last_heartbeat: string | null
}
export class AgentFieldError extends Error {
  constructor(
    public field: string,
    message: string,
  ) {
    super(message)
  }
}
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    Object.keys(value).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(value, key))
  )
    throw new AgentFieldError('', '执行机字段不符合合同')
  return value as Record<string, unknown>
}
export function parseAgentWrite(value: unknown): AgentWrite {
  const row = object(value, ['name', 'endpoint', 'probe_interval'])
  if (
    typeof row.name !== 'string' ||
    /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(row.name) ||
    [...row.name].length > 80
  )
    throw new AgentFieldError('name', '机器名称需为 1 至 80 个字符，不能含控制字符')
  const name = row.name.normalize('NFC').trim()
  if (!name || [...name].length > 80)
    throw new AgentFieldError('name', '机器名称需为 1 至 80 个字符')
  // 默认仅允许已配置的 50325 端口；允许端口变更须随服务端合同同步。
  if (
    typeof row.endpoint !== 'string' ||
    !/^http:\/\/(?:127\.0\.0\.1|localhost):50325\/?$/.test(row.endpoint)
  )
    throw new AgentFieldError(
      'endpoint',
      '本地 API 地址仅允许 http://localhost:50325 或 http://127.0.0.1:50325',
    )
  if (
    typeof row.probe_interval !== 'number' ||
    !Number.isInteger(row.probe_interval) ||
    row.probe_interval < 10 ||
    row.probe_interval > 300
  )
    throw new AgentFieldError('probe_interval', '探测周期需为 10 至 300 秒的整数')
  return { name, endpoint: 'http://127.0.0.1:50325', probe_interval: row.probe_interval }
}
export function parseAgent(value: unknown): Agent {
  const row = object(value, [
    'name',
    'endpoint',
    'probe_interval',
    'id',
    'revision',
    'state',
    'last_heartbeat',
  ])
  const write = parseAgentWrite({
    name: row.name,
    endpoint: row.endpoint,
    probe_interval: row.probe_interval,
  })
  if (
    typeof row.id !== 'string' ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(row.id) ||
    !Number.isSafeInteger(row.revision) ||
    (row.revision as number) < 1 ||
    typeof row.state !== 'string' ||
    !['READY', 'SUSPECT', 'OFFLINE', 'REVOKED'].includes(row.state)
  )
    throw new AgentFieldError('', '执行机响应身份、版本或状态无效')
  if (
    row.last_heartbeat !== null &&
    (typeof row.last_heartbeat !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(row.last_heartbeat) ||
      !Number.isFinite(Date.parse(row.last_heartbeat)) ||
      new Date(row.last_heartbeat).toISOString().slice(0, 19) !== row.last_heartbeat.slice(0, 19))
  )
    throw new AgentFieldError('', '执行机心跳时刻无效')
  return {
    ...write,
    id: row.id,
    revision: row.revision as number,
    state: row.state as Agent['state'],
    last_heartbeat: row.last_heartbeat as string | null,
  }
}

export type AgentOperation = 'READ' | 'ENROLL' | 'REVOKE' | 'PROBE'
export interface AgentCapability {
  actor_id: number
  tenant_id: string
  data_role: 'SUPER_ADMIN' | 'TEAM_ADMIN' | 'USER'
  csrf_token: string | null
}
export interface AgentIntent {
  operation: 'ENROLL' | 'REVOKE'
  actor_id: number
  tenant_id: string
  key: string
  id?: string
  revision?: number
  body: AgentWrite | { reason: string }
}
export interface AgentQuery {
  page_size: number
  q?: string
  status?: string
  date_from?: string
  date_to?: string
  operator_user_id?: string
  cursor?: string
}
export interface AgentPage {
  items: Agent[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export class AgentApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public unknown_result = false,
  ) {
    super(message)
  }
}
export const agentAuthContext = () => JSON.stringify([orbitCredentials(), orbitAuthHeaders()])
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const integer = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v >= 1
const text = (v: unknown, max: number, min = 0): v is string =>
  typeof v === 'string' &&
  [...v].length >= min &&
  [...v].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(v)
const exact = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  !!v &&
  typeof v === 'object' &&
  !Array.isArray(v) &&
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k))
function invalid(): never {
  throw new AgentApiError(502, 'INVALID_RESPONSE', '执行机响应不符合合同')
}
async function readBody(response: Response, signal: AbortSignal) {
  const reader = response.body?.getReader()
  if (!reader) invalid()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let result = '',
    size = 0
  const abort = () => {
    void reader.cancel().catch(() => {})
  }
  signal.addEventListener('abort', abort, { once: true })
  try {
    for (;;) {
      signal.throwIfAborted()
      const chunk = await reader.read()
      if (chunk.done) break
      size += chunk.value.byteLength
      if (size > 2 * 1024 * 1024) invalid()
      result += decoder.decode(chunk.value, { stream: true })
    }
    signal.throwIfAborted()
    return JSON.parse(result + decoder.decode()) as unknown
  } finally {
    signal.removeEventListener('abort', abort)
    try {
      await reader.cancel()
    } catch {
      /* 不覆盖原响应错误 */
    }
    reader.releaseLock()
  }
}
export async function environmentRequest<T>(
  path: string,
  parse: (v: unknown) => T,
  init: RequestInit = {},
  expected = 200,
): Promise<T> {
  const context = agentAuthContext(),
    controller = new AbortController(),
    cancel = () => controller.abort()
  let status = 0
  const write = !!init.method && init.method !== 'GET'
  init.signal?.throwIfAborted()
  init.signal?.addEventListener('abort', cancel, { once: true })
  const timer = setTimeout(cancel, 15000)
  try {
    const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/${path}`, {
      ...init,
      credentials: orbitCredentials(),
      cache: 'no-store',
      signal: controller.signal,
      headers: orbitAuthHeaders({ 'Content-Type': 'application/json', ...init.headers }),
    })
    status = response.status
    let body: unknown
    try {
      body = await readBody(response, controller.signal)
    } catch {
      throw new AgentApiError(
        [401, 403, 404, 409].includes(status) ? status : 502,
        'INVALID_RESPONSE',
        '执行机响应未能确认',
        write,
      )
    }
    if (context !== agentAuthContext())
      throw new AgentApiError(
        409,
        'SESSION_CONTEXT_CHANGED',
        '认证上下文已变化，请重新打开目录',
        write,
      )
    if (!response.ok) {
      const value = body as Record<string, unknown>
      const valid =
        exact(value, ['code', 'message', 'field_errors', 'retryable', 'request_id']) &&
        text(value.code, 64, 1) &&
        text(value.message, 1000, 1) &&
        Array.isArray(value.field_errors) &&
        value.field_errors.length <= 100 &&
        typeof value.retryable === 'boolean' &&
        uuid(value.request_id)
      throw new AgentApiError(
        status,
        valid ? String(value.code) : 'INVALID_ERROR_RESPONSE',
        valid ? String(value.message) : '执行机错误响应未能确认',
        write && (!valid || status >= 500),
      )
    }
    if (status !== expected)
      throw new AgentApiError(502, 'UNEXPECTED_STATUS', '执行机响应状态未能确认', write)
    try {
      return parse(body)
    } catch {
      throw new AgentApiError(
        502,
        'INVALID_RESPONSE',
        '执行机响应未能确认，请保留原请求重试',
        write,
      )
    }
  } catch (e) {
    if (e instanceof AgentApiError) throw e
    if (init.signal?.aborted) throw new DOMException('请求已取消', 'AbortError')
    throw new AgentApiError(status, 'NETWORK_UNAVAILABLE', '连接中断或超时，请重试原请求', write)
  } finally {
    clearTimeout(timer)
    init.signal?.removeEventListener('abort', cancel)
  }
}

export const environmentApi = {
  capabilities: (operation: AgentOperation, signal?: AbortSignal) =>
    environmentRequest<AgentCapability>(
      `execution-agents/capabilities?operation=${operation}`,
      (value) => {
        if (
          !exact(value, ['actor_id', 'tenant_id', 'data_role', 'csrf_token']) ||
          !integer(value.actor_id) ||
          !uuid(value.tenant_id) ||
          !['SUPER_ADMIN', 'TEAM_ADMIN', 'USER'].includes(String(value.data_role)) ||
          (operation === 'READ'
            ? value.csrf_token !== null
            : value.data_role !== 'SUPER_ADMIN' || !text(value.csrf_token, 255, 16))
        )
          invalid()
        return value as unknown as AgentCapability
      },
      { signal },
    ),
  list: (query: AgentQuery, signal?: AbortSignal) => {
    if (![20, 50, 100, 200].includes(query.page_size))
      throw new AgentFieldError('page_size', '每页仅允许20、50、100或200条')
    const params = new URLSearchParams({ page_size: String(query.page_size) })
    for (const key of [
      'q',
      'status',
      'date_from',
      'date_to',
      'operator_user_id',
      'cursor',
    ] as const)
      if (query[key]) params.set(key, query[key]!)
    return environmentRequest<AgentPage>(
      `execution-agents?${params}`,
      (value) => {
        if (
          !exact(value, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
          !Array.isArray(value.items) ||
          value.items.length > query.page_size ||
          !integer(value.scope_version) ||
          (value.next_cursor !== null && !text(value.next_cursor, 2048, 1)) ||
          !text(value.data_as_of, 40, 20) ||
          !Number.isFinite(Date.parse(value.data_as_of))
        )
          invalid()
        const items = value.items.map(parseAgent)
        if (
          new Set(items.map((item) => item.id)).size !== items.length ||
          (value.next_cursor && !items.length)
        )
          invalid()
        return { ...value, items } as unknown as AgentPage
      },
      { signal },
    )
  },
  get: (id: string, signal?: AbortSignal) =>
    environmentRequest(
      `execution-agents/${encodeURIComponent(id)}`,
      (value) => {
        const result = parseAgent(value)
        if (result.id !== id) invalid()
        return result
      },
      { signal },
    ),
  write: (intent: AgentIntent, csrf: string) =>
    environmentRequest<Agent>(
      `execution-agents${intent.id ? '/' + encodeURIComponent(intent.id) : ''}${intent.operation === 'REVOKE' ? '/revoke' : ''}`,
      (value) => {
        const result = parseAgent(value)
        if (
          (intent.id && result.id !== intent.id) ||
          result.revision !== (intent.revision ?? 0) + 1 ||
          (intent.operation === 'REVOKE' && result.state !== 'REVOKED') ||
          ('name' in intent.body &&
            (result.name !== intent.body.name ||
              result.endpoint !== intent.body.endpoint ||
              result.probe_interval !== intent.body.probe_interval))
        )
          invalid()
        return result
      },
      {
        method: intent.operation === 'ENROLL' && intent.id ? 'PUT' : 'POST',
        headers: {
          'X-CSRF-Token': csrf,
          'Idempotency-Key': intent.key,
          ...(intent.revision !== undefined ? { 'If-Match': `"${intent.revision}"` } : {}),
        },
        body: JSON.stringify(intent.body),
      },
      intent.operation === 'ENROLL' && !intent.id ? 201 : 200,
    ),
}
