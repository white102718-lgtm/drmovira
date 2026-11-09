/** 只读探测请求；受理与检查完成都不授予广告操作能力。 */
import { AgentFieldError, environmentRequest } from './environments'
export interface ProbeIntent {
  agent_id: string
  revision: number
  actor_id: number
  tenant_id: string
  key: string
}
export interface ProbeAck {
  id: string
  revision: 1
  state: 'QUEUED'
  request_id: string
}
export interface ProbeResult {
  id: string
  agent_id: string
  state: 'QUEUED' | 'COMPLETED' | 'FAILED' | 'EXPIRED'
  created_at: string
  expires_at: string
  completed_at: string | null
  error_code: string | null
}
/** 父页面按租户/操作者/设备保留；仅在本页内存存放，不写入浏览器存储。 */
export interface ProbeSession {
  intent: ProbeIntent | null
  requestId: string | null
  result: ProbeResult | null
}
export const newProbeSession = (): ProbeSession => ({ intent: null, requestId: null, result: null })
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const utc = (v: unknown): v is string =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 19) === v.slice(0, 19)
function invalid(): never {
  throw new AgentFieldError('', '探测响应不符合合同')
}
function exact(value: unknown, fields: string[]): Record<string, unknown> {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    Object.keys(value).length !== fields.length ||
    fields.some((k) => !Object.hasOwn(value, k))
  )
    invalid()
  return value as Record<string, unknown>
}
export function parseProbeResult(value: unknown, agent: string, request: string): ProbeResult {
  const r = exact(value, [
    'id',
    'agent_id',
    'state',
    'created_at',
    'expires_at',
    'completed_at',
    'error_code',
  ])
  if (
    !uuid(r.id) ||
    r.id !== request ||
    !uuid(r.agent_id) ||
    r.agent_id !== agent ||
    !['QUEUED', 'COMPLETED', 'FAILED', 'EXPIRED'].includes(String(r.state)) ||
    !utc(r.created_at) ||
    !utc(r.expires_at) ||
    Date.parse(r.expires_at) <= Date.parse(r.created_at) ||
    (r.completed_at !== null &&
      (!utc(r.completed_at) || Date.parse(r.completed_at) < Date.parse(r.created_at))) ||
    (r.error_code !== null &&
      (typeof r.error_code !== 'string' || !/^[A-Z][A-Z0-9_]{0,63}$/.test(r.error_code)))
  )
    invalid()
  if (r.state === 'QUEUED' && (r.completed_at !== null || r.error_code !== null)) invalid()
  if (r.state === 'COMPLETED' && (r.completed_at === null || r.error_code !== null)) invalid()
  if (r.state === 'FAILED' && (r.completed_at === null || r.error_code === null)) invalid()
  return r as unknown as ProbeResult
}
export const probeApi = {
  submit: (intent: ProbeIntent, csrf: string) =>
    environmentRequest<ProbeAck>(
      `execution-agents/${encodeURIComponent(intent.agent_id)}/probe`,
      (value) => {
        const r = exact(value, ['id', 'revision', 'state', 'request_id'])
        if (!uuid(r.id) || !uuid(r.request_id) || r.revision !== 1 || r.state !== 'QUEUED')
          invalid()
        return r as unknown as ProbeAck
      },
      {
        method: 'POST',
        headers: {
          'X-CSRF-Token': csrf,
          'Idempotency-Key': intent.key,
          'If-Match': `"${intent.revision}"`,
        },
      },
      202,
    ),
  get: (agent: string, request: string, signal?: AbortSignal) =>
    environmentRequest(
      `execution-agents/${encodeURIComponent(agent)}/probe-requests/${encodeURIComponent(request)}`,
      (v) => parseProbeResult(v, agent, request),
      { signal },
    ),
}
