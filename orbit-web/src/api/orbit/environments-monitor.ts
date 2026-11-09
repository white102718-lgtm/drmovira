/** 只读控制面可信观察；不连接用户的 localhost，不由浏览器推算身份或机器状态。 */
import { AgentFieldError, environmentRequest } from './environments'
export interface AgentMonitor {
  agent_id: string
  machine_state: 'READY' | 'SUSPECT' | 'OFFLINE' | 'REVOKED'
  last_heartbeat: string | null
  api_status: 'READY' | 'UNREACHABLE' | 'AUTH_FAILED' | 'UNKNOWN'
  inventory_coverage: 'FULL' | 'ACTIVE_ONLY' | 'UNAVAILABLE'
  last_error: string | null
  received_at: string | null
}
export interface ObservedProfile {
  id: string
  agent_id: string
  external_profile_id: string
  process_state: 'ACTIVE' | 'INACTIVE' | 'UNKNOWN'
  identity_state: 'VALID' | 'LOGIN_REQUIRED' | 'CHALLENGE' | 'IDENTITY_MISMATCH' | 'UNKNOWN'
  account_ids: string[]
  observed_at: string
}
export interface ProfilePage {
  items: ObservedProfile[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export interface ProfileQuery {
  page_size: number
  cursor?: string
  q?: string
  status?: string
}
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
function fail(): never {
  throw new AgentFieldError('', '环境监测响应不符合合同')
}
function exact(v: unknown, keys: string[]): Record<string, unknown> {
  if (
    !v ||
    typeof v !== 'object' ||
    Array.isArray(v) ||
    Object.keys(v).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(v, key))
  )
    fail()
  return v as Record<string, unknown>
}
const utc = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 19) === v.slice(0, 19)
const safeText = (v: unknown, max: number): v is string =>
  typeof v === 'string' &&
  !!v &&
  [...v].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(v)
export function parseAgentMonitor(value: unknown, agentId: string): AgentMonitor {
  const row = exact(value, [
    'agent_id',
    'machine_state',
    'last_heartbeat',
    'api_status',
    'inventory_coverage',
    'last_error',
    'received_at',
  ])
  if (
    !uuid(row.agent_id) ||
    row.agent_id !== agentId ||
    !['READY', 'SUSPECT', 'OFFLINE', 'REVOKED'].includes(String(row.machine_state)) ||
    !['READY', 'UNREACHABLE', 'AUTH_FAILED', 'UNKNOWN'].includes(String(row.api_status)) ||
    !['FULL', 'ACTIVE_ONLY', 'UNAVAILABLE'].includes(String(row.inventory_coverage)) ||
    (row.last_heartbeat !== null && !utc(row.last_heartbeat)) ||
    (row.received_at !== null && !utc(row.received_at)) ||
    (row.last_error !== null &&
      (typeof row.last_error !== 'string' || !/^[A-Z][A-Z0-9_]{0,63}$/.test(row.last_error)))
  )
    fail()
  return row as unknown as AgentMonitor
}
export function parseProfilePage(value: unknown, agentId: string, size: number): ProfilePage {
  const row = exact(value, ['items', 'next_cursor', 'data_as_of', 'scope_version'])
  if (
    !Array.isArray(row.items) ||
    row.items.length > size ||
    !utc(row.data_as_of) ||
    !Number.isSafeInteger(row.scope_version) ||
    (row.scope_version as number) < 1 ||
    (row.next_cursor !== null && !safeText(row.next_cursor, 2048))
  )
    fail()
  const ids = new Set<string>()
  const items = row.items.map((value) => {
    const item = exact(value, [
      'id',
      'agent_id',
      'external_profile_id',
      'process_state',
      'identity_state',
      'account_ids',
      'observed_at',
    ])
    if (
      !uuid(item.id) ||
      ids.has(item.id) ||
      !uuid(item.agent_id) ||
      item.agent_id !== agentId ||
      !safeText(item.external_profile_id, 128) ||
      item.external_profile_id !== item.external_profile_id.normalize('NFC').trim() ||
      !['ACTIVE', 'INACTIVE', 'UNKNOWN'].includes(String(item.process_state)) ||
      !['VALID', 'LOGIN_REQUIRED', 'CHALLENGE', 'IDENTITY_MISMATCH', 'UNKNOWN'].includes(
        String(item.identity_state),
      ) ||
      !Array.isArray(item.account_ids) ||
      item.account_ids.length > 500 ||
      !item.account_ids.every(uuid) ||
      new Set(item.account_ids).size !== item.account_ids.length ||
      !utc(item.observed_at)
    )
      fail()
    ids.add(item.id)
    return item as unknown as ObservedProfile
  })
  if (row.next_cursor && !items.length) fail()
  return { ...row, items } as unknown as ProfilePage
}
export const monitorApi = {
  get: (id: string, signal?: AbortSignal) =>
    environmentRequest(
      `execution-agents/${encodeURIComponent(id)}/monitor`,
      (v) => parseAgentMonitor(v, id),
      { signal },
    ),
  profiles: (id: string, query: ProfileQuery, signal?: AbortSignal) => {
    if (![20, 50, 100, 200].includes(query.page_size))
      throw new AgentFieldError('page_size', '分页大小无效')
    const params = new URLSearchParams({ page_size: String(query.page_size) })
    for (const key of ['q', 'status', 'cursor'] as const)
      if (query[key]) params.set(key, query[key]!)
    return environmentRequest(
      `execution-agents/${encodeURIComponent(id)}/profiles?${params}`,
      (v) => parseProfilePage(v, id, query.page_size),
      { signal },
      200,
      8 * 1024 * 1024,
    )
  },
}
