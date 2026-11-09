/** 环境动作能力原合同；与当前用户的菜单权限分离。 */
import { AgentFieldError, environmentRequest } from './environments'
export interface EnvironmentActionCapability {
  id: string
  agent_id: string
  profile_binding_id: string
  operation_kind: 'CREATE' | 'BUDGET_SET' | 'PAUSE' | 'DELETE' | 'ENABLE' | 'ARCHIVE'
  entity_type: 'CAMPAIGN' | 'ADSET' | 'AD'
  workflow_version: string
  adapter_version: string
  client_version: string
  browser_version: string
  page_language: string
  state: 'UNVERIFIED' | 'VERIFIED' | 'REVOKED'
  evidence_ref: string | null
  verified_at: string | null
}
export interface EnvironmentCapabilityPage {
  items: EnvironmentActionCapability[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
const fail = (): never => {
  throw new AgentFieldError('', '动作能力响应不符合合同')
}
const exact = (v: unknown, fields: string[]): Record<string, unknown> => {
  if (
    !v ||
    typeof v !== 'object' ||
    Array.isArray(v) ||
    Object.keys(v).length !== fields.length ||
    fields.some((k) => !Object.hasOwn(v, k))
  )
    fail()
  return v as Record<string, unknown>
}
const text = (v: unknown, max: number): v is string =>
  typeof v === 'string' && v.length > 0 && v.length <= max
const uuid = (v: unknown) =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const utc = (v: unknown) =>
  typeof v === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(v) &&
  Number.isFinite(Date.parse(v)) &&
  new Date(v).toISOString().slice(0, 19) === v.slice(0, 19)
export function parseCapabilityPage(value: unknown): EnvironmentCapabilityPage {
  const p = exact(value, ['items', 'next_cursor', 'data_as_of', 'scope_version'])
  if (
    !Array.isArray(p.items) ||
    p.items.length > 200 ||
    !utc(p.data_as_of) ||
    !Number.isSafeInteger(p.scope_version) ||
    Number(p.scope_version) < 1 ||
    (p.next_cursor !== null && !text(p.next_cursor, 2048))
  )
    fail()
  const versions = [
    'workflow_version',
    'adapter_version',
    'client_version',
    'browser_version',
    'page_language',
  ]
  const ids = new Set<string>()
  for (const value of p.items as unknown[]) {
    const r = exact(value, [
      'id',
      'agent_id',
      'profile_binding_id',
      'operation_kind',
      'entity_type',
      ...versions,
      'state',
      'evidence_ref',
      'verified_at',
    ])
    if (
      !uuid(r.id) ||
      !uuid(r.agent_id) ||
      !uuid(r.profile_binding_id) ||
      !['CREATE', 'BUDGET_SET', 'PAUSE', 'DELETE', 'ENABLE', 'ARCHIVE'].includes(
        String(r.operation_kind),
      ) ||
      !['CAMPAIGN', 'ADSET', 'AD'].includes(String(r.entity_type)) ||
      versions.some((k) => !text(r[k], 64)) ||
      !['UNVERIFIED', 'VERIFIED', 'REVOKED'].includes(String(r.state)) ||
      (r.evidence_ref !== null && !text(r.evidence_ref, 255)) ||
      (r.verified_at !== null && !utc(r.verified_at)) ||
      (r.state === 'VERIFIED' && (!r.evidence_ref || !r.verified_at)) ||
      (r.operation_kind === 'BUDGET_SET' && r.entity_type === 'AD') ||
      ids.has(String(r.id))
    )
      fail()
    ids.add(String(r.id))
  }
  return p as unknown as EnvironmentCapabilityPage
}
export const environmentCapabilityApi = {
  list: (cursor?: string, signal?: AbortSignal) =>
    environmentRequest<EnvironmentCapabilityPage>(
      'environment-capabilities?' +
        new URLSearchParams({ page_size: '50', ...(cursor ? { cursor } : {}) }),
      parseCapabilityPage,
      { signal },
    ),
}
