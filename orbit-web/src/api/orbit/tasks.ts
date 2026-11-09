/** 原Task/TaskNode只读合同；UUID和平台大整数ID始终字符串，不发任何写动作。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'

export const taskStates = [
  'QUEUED',
  'RUNNING',
  'VERIFYING',
  'UNKNOWN',
  'RETRY_WAIT',
  'SUCCEEDED',
  'PARTIAL_SUCCESS',
  'FAILED',
  'CANCELLED',
  'NEEDS_HUMAN',
] as const
export const nodeStates = [
  'DRAFT',
  'VALIDATED',
  'QUEUED',
  'RUNNING',
  'ACCEPTED',
  'VERIFYING',
  'SUCCEEDED',
  'FAILED',
  'UNKNOWN',
  'RETRY_WAIT',
  'CANCELLED',
  'EXPIRED',
  'BLOCKED_AUTH',
  'BLOCKED_DEPENDENCY',
  'NEEDS_HUMAN',
] as const
export const nodeKinds = [
  'UPLOAD',
  'CAMPAIGN',
  'ADSET',
  'CREATIVE',
  'AD',
  'VERIFY',
  'ENABLE',
  'ALLOCATION',
] as const
export type TaskState = (typeof taskStates)[number]
export type TaskNodeState = (typeof nodeStates)[number]
export type TaskNodeKind = (typeof nodeKinds)[number]
export type TaskPageSize = 20 | 50 | 100 | 200
export type ExecutionMode = 'META_API' | 'ADSPOWER_UI'
export interface TaskNode {
  id: string
  node_key: string
  parent_ids: string[]
  kind: TaskNodeKind
  state: TaskNodeState
  external_id: string | null
  attempt: number
  error_code: string | null
  error_message: string | null
  retryable: boolean
  configuration_state: 'UNVERIFIED' | 'VERIFIED' | 'MISMATCH' | 'UNKNOWN'
  delivery_state: 'UNKNOWN' | 'ACTIVE' | 'PAUSED' | 'REVIEWING' | 'BLOCKED'
  updated_at: string
  execution_mode?: ExecutionMode
  no_op?: boolean
}
export interface Task {
  id: string
  revision: number
  ownership: { owner_user_id: string; owner_team_id: string }
  state: TaskState
  nodes: TaskNode[]
  latest_event_id: string | null
  needs_manual_reconciliation: boolean
  created_at: string
  node_count: number
  next_node_cursor: string | null
  execution_mode?: ExecutionMode
}
export interface TaskPage<T = Task> {
  items: T[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export interface TaskListQuery {
  page_size: TaskPageSize
  cursor?: string
  status?: TaskState
  operator_user_id?: string
}
export interface TaskNodeQuery {
  page_size: TaskPageSize
  cursor?: string
  status?: TaskNodeState
  q?: string
}
export interface TaskFieldError {
  path: string
  code: string
  message: string
  constraint: string
}
/** 服务端原Error合同；本地合成错误没有服务端request_id，不冒充此结构。 */
export interface TaskErrorBody {
  code: string
  message: string
  field_errors: TaskFieldError[]
  retryable: boolean
  request_id: string
}
export class TaskApiError extends Error {
  readonly source: 'server' | 'local'
  readonly field_errors: TaskFieldError[]
  readonly retryable: boolean
  readonly request_id: string | null
  constructor(
    public status: number,
    public code: string,
    message: string,
    details?: TaskErrorBody,
  ) {
    super(message)
    this.source = details ? 'server' : 'local'
    this.field_errors = details?.field_errors ?? []
    this.retryable = details?.retryable ?? false
    this.request_id = details?.request_id ?? null
  }
}
export const taskStateLabels: Record<TaskState | TaskNodeState, string> = {
  DRAFT: '草稿',
  VALIDATED: '已预检',
  QUEUED: '排队中',
  RUNNING: '处理中',
  ACCEPTED: '已受理',
  VERIFYING: '核验中',
  UNKNOWN: '结果待核实',
  RETRY_WAIT: '等待安全重试',
  SUCCEEDED: '已成功',
  PARTIAL_SUCCESS: '部分成功',
  FAILED: '已失败',
  CANCELLED: '已取消',
  EXPIRED: '已过期',
  BLOCKED_AUTH: '授权受阻',
  BLOCKED_DEPENDENCY: '父级受阻',
  NEEDS_HUMAN: '待人工处理',
}
export const nodeKindLabels: Record<TaskNodeKind, string> = {
  UPLOAD: '素材上传',
  CAMPAIGN: '系列',
  ADSET: '广告组',
  CREATIVE: '创意',
  AD: '广告',
  VERIFY: '回读核验',
  ENABLE: '启用',
  ALLOCATION: '素材分配',
}
export const configurationLabels = {
  UNVERIFIED: '未核验',
  VERIFIED: '核验一致',
  MISMATCH: '配置不一致',
  UNKNOWN: '未知',
}
export const deliveryLabels = {
  UNKNOWN: '未知',
  ACTIVE: '投放中',
  PAUSED: '已暂停',
  REVIEWING: '审核中',
  BLOCKED: '投放受阻',
}
export const executionLabels = { META_API: 'Meta API', ADSPOWER_UI: 'AdsPower' }
export const taskTag = (state: string): 'success' | 'warning' | 'danger' | 'info' =>
  state === 'SUCCEEDED'
    ? 'success'
    : ['FAILED', 'BLOCKED_AUTH', 'BLOCKED_DEPENDENCY'].includes(state)
      ? 'danger'
      : ['UNKNOWN', 'NEEDS_HUMAN', 'PARTIAL_SUCCESS'].includes(state)
        ? 'warning'
        : 'info'
export const isTaskAbort = (error: unknown) => error instanceof Error && error.name === 'AbortError'
export const taskMessage = (error: unknown) =>
  error instanceof Error ? error.message : '任务读取失败，请重新读取'

const uuid = (value: unknown): value is string =>
  typeof value === 'string' &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
const integer = (value: unknown, minimum = 0, maximum = Number.MAX_SAFE_INTEGER) =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum && value <= maximum
const text = (value: unknown, maximum: number, minimum = 1): value is string =>
  typeof value === 'string' && [...value].length >= minimum && [...value].length <= maximum
const dateTime = (value: unknown) =>
  typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}T/.test(value) &&
  /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
  Number.isFinite(Date.parse(value))
const cursor = (value: unknown) => value === null || text(value, 2048)
const mode = (value: unknown) =>
  value === undefined || value === 'META_API' || value === 'ADSPOWER_UI'
function object(
  value: unknown,
  required: string[],
  optional: string[] = [],
): value is Record<string, unknown> {
  return (
    !!value &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    required.every((key) => Object.hasOwn(value, key)) &&
    Object.keys(value).every((key) => required.includes(key) || optional.includes(key))
  )
}
function invalid(): never {
  throw new TaskApiError(502, 'INVALID_RESPONSE', '任务服务响应不符合合同，请重新读取')
}
export function parseTaskErrorBody(value: unknown): TaskErrorBody {
  if (
    !object(value, ['code', 'message', 'field_errors', 'retryable', 'request_id']) ||
    !text(value.code, 64) ||
    !text(value.message, 1000) ||
    typeof value.retryable !== 'boolean' ||
    !uuid(value.request_id) ||
    !Array.isArray(value.field_errors) ||
    value.field_errors.length > 100 ||
    !value.field_errors.every(
      (field) =>
        object(field, ['path', 'code', 'message', 'constraint']) &&
        text(field.path, 255) &&
        text(field.code, 64) &&
        text(field.message, 1000) &&
        text(field.constraint, 500, 0),
    )
  )
    invalid()
  // 与网络原对象隔离，避免调用方随后改写错误详情。
  return {
    ...value,
    field_errors: value.field_errors.map((field) => ({ ...field })),
  } as TaskErrorBody
}
export function taskHttpError(status: number, value: unknown): TaskApiError {
  try {
    const details = parseTaskErrorBody(value)
    return new TaskApiError(status, details.code, details.message, details)
  } catch {
    // 保留HTTP授权状态；未知响应正文与任意message均不展示。
    return new TaskApiError(
      status,
      'INVALID_ERROR_RESPONSE',
      '任务服务错误响应不符合合同，请按当前权限重新读取',
    )
  }
}
export function parseTaskNode(value: unknown): TaskNode {
  if (
    !object(
      value,
      [
        'id',
        'node_key',
        'parent_ids',
        'kind',
        'state',
        'external_id',
        'attempt',
        'error_code',
        'error_message',
        'retryable',
        'configuration_state',
        'delivery_state',
        'updated_at',
      ],
      ['execution_mode', 'no_op'],
    )
  )
    invalid()
  if (
    !uuid(value.id) ||
    !text(value.node_key, 512) ||
    !Array.isArray(value.parent_ids) ||
    value.parent_ids.length > 100 ||
    !value.parent_ids.every(uuid) ||
    !nodeKinds.includes(value.kind as TaskNodeKind) ||
    !nodeStates.includes(value.state as TaskNodeState) ||
    !(
      value.external_id === null ||
      (typeof value.external_id === 'string' && /^[0-9]{1,64}$/.test(value.external_id))
    ) ||
    !integer(value.attempt, 0, 2147483647) ||
    !(value.error_code === null || text(value.error_code, 64)) ||
    !(value.error_message === null || text(value.error_message, 1000)) ||
    typeof value.retryable !== 'boolean' ||
    !Object.hasOwn(configurationLabels, value.configuration_state as string) ||
    !Object.hasOwn(deliveryLabels, value.delivery_state as string) ||
    !dateTime(value.updated_at) ||
    !mode(value.execution_mode) ||
    (value.no_op !== undefined && typeof value.no_op !== 'boolean')
  )
    invalid()
  return value as unknown as TaskNode
}
export function parseTask(value: unknown): Task {
  if (
    !object(
      value,
      [
        'id',
        'revision',
        'ownership',
        'state',
        'nodes',
        'latest_event_id',
        'needs_manual_reconciliation',
        'created_at',
        'node_count',
        'next_node_cursor',
      ],
      ['execution_mode'],
    )
  )
    invalid()
  if (
    !uuid(value.id) ||
    !integer(value.revision, 1) ||
    !object(value.ownership, ['owner_user_id', 'owner_team_id']) ||
    !uuid(value.ownership.owner_user_id) ||
    !uuid(value.ownership.owner_team_id) ||
    !taskStates.includes(value.state as TaskState) ||
    !Array.isArray(value.nodes) ||
    value.nodes.length > 200 ||
    !(value.latest_event_id === null || uuid(value.latest_event_id)) ||
    typeof value.needs_manual_reconciliation !== 'boolean' ||
    !dateTime(value.created_at) ||
    !integer(value.node_count, 0, 2147483647) ||
    (value.node_count as number) < value.nodes.length ||
    !cursor(value.next_node_cursor) ||
    !mode(value.execution_mode)
  )
    invalid()
  value.nodes.forEach(parseTaskNode)
  return value as unknown as Task
}
function parsePage<T>(value: unknown, parse: (entry: unknown) => T): TaskPage<T> {
  if (
    !object(value, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(value.items) ||
    value.items.length > 200 ||
    !cursor(value.next_cursor) ||
    !dateTime(value.data_as_of) ||
    !integer(value.scope_version, 1)
  )
    invalid()
  value.items.forEach(parse)
  return value as unknown as TaskPage<T>
}
function query(value: TaskListQuery | TaskNodeQuery, node: boolean) {
  const allowed = node
    ? ['page_size', 'cursor', 'status', 'q']
    : ['page_size', 'cursor', 'status', 'operator_user_id']
  if (
    Object.keys(value).some((key) => !allowed.includes(key)) ||
    ![20, 50, 100, 200].includes(value.page_size) ||
    (value.cursor !== undefined && !text(value.cursor, 2048)) ||
    (value.status !== undefined &&
      !(node ? nodeStates : taskStates).includes(value.status as never))
  )
    throw new TaskApiError(400, 'INVALID_QUERY', '任务筛选参数无效，请重新选择')
  const parameters = new URLSearchParams({ page_size: String(value.page_size) })
  if (value.cursor) parameters.set('cursor', value.cursor)
  if (value.status) parameters.set('status', value.status)
  if (node && 'q' in value && value.q !== undefined) {
    const prefix = value.q.normalize('NFC').trim()
    if (!text(prefix, 100, 0))
      throw new TaskApiError(422, 'FIELD_INVALID', '节点键前缀最多100个码点')
    if (prefix) parameters.set('q', prefix)
  }
  if (!node && 'operator_user_id' in value && value.operator_user_id !== undefined) {
    if (!uuid(value.operator_user_id))
      throw new TaskApiError(422, 'FIELD_INVALID', '拥有者标识无效')
    parameters.set('operator_user_id', value.operator_user_id)
  }
  return parameters
}
/** GET读取超时可安全重读；调用方取消仍保持AbortError，不能混作服务端失败。 */
async function read(path: string, signal?: AbortSignal): Promise<unknown> {
  if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  const deadline = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, 10000)
  function interrupted(error?: unknown) {
    if (signal?.aborted) throw new DOMException('读取已取消', 'AbortError')
    if (timedOut)
      throw new TaskApiError(504, 'READ_TIMEOUT', '读取超时，任务状态尚未刷新，请重新读取')
    if (isTaskAbort(error)) throw new DOMException('读取已取消', 'AbortError')
  }
  try {
    let response: Response
    try {
      response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1${path}`, {
        method: 'GET',
        signal: controller.signal,
        credentials: orbitCredentials(),
        cache: 'no-store',
        headers: orbitAuthHeaders({ Accept: 'application/json' }),
      })
    } catch (error) {
      interrupted(error)
      throw new TaskApiError(0, 'NETWORK_UNAVAILABLE', '网络中断，任务状态尚未刷新，请重新读取')
    }
    let value: unknown
    try {
      value = await response.json()
    } catch (error) {
      interrupted(error)
      if (!response.ok) throw taskHttpError(response.status, undefined)
      invalid()
    }
    interrupted()
    if (!response.ok) {
      throw taskHttpError(response.status, value)
    }
    return value
  } finally {
    clearTimeout(deadline)
    signal?.removeEventListener('abort', cancel)
  }
}

function identifier(id: string) {
  if (!uuid(id)) throw new TaskApiError(422, 'FIELD_INVALID', '任务标识无效')
  return encodeURIComponent(id)
}
export const tasksApi = {
  list: async (filters: TaskListQuery, signal?: AbortSignal) => {
    const page = parsePage(await read(`/tasks?${query(filters, false)}`, signal), parseTask)
    if (page.items.some((item) => item.nodes.length !== 0)) invalid()
    return page
  },
  get: async (id: string, signal?: AbortSignal) =>
    parseTask(await read(`/tasks/${identifier(id)}`, signal)),
  nodes: async (id: string, filters: TaskNodeQuery, signal?: AbortSignal) =>
    parsePage(
      await read(`/tasks/${identifier(id)}/nodes?${query(filters, true)}`, signal),
      parseTaskNode,
    ),
}
