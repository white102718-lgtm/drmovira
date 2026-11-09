import { AgentFieldError, environmentRequest } from './environments'
export interface BindingWrite {
  account_id: string
  agent_id: string
  profile_external_id: string
  ownership: { owner_user_id: string; owner_team_id: string }
}
export interface ProfileBinding extends BindingWrite {
  id: string
  revision: number
  identity_state: 'VALID' | 'LOGIN_REQUIRED' | 'CHALLENGE' | 'IDENTITY_MISMATCH' | 'UNKNOWN'
  verified_at: string | null
}
export interface UnboundBinding {
  id: string
  revision: number
  unbound_at: string
}
export interface BindingIntent {
  operation: 'SAVE' | 'UNBIND'
  actor_id: number
  tenant_id: string
  key: string
  id?: string
  revision?: number
  body: BindingWrite | { reason: string }
}
export interface BindingPage {
  items: ProfileBinding[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
const uuid = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(value)
const positive = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v > 0
function exact(v: unknown, keys: string[]): Record<string, unknown> {
  if (
    !v ||
    typeof v !== 'object' ||
    Array.isArray(v) ||
    Object.keys(v).length !== keys.length ||
    keys.some((k) => !Object.hasOwn(v, k))
  )
    throw new AgentFieldError('', '账户环境字段不符合合同')
  return v as Record<string, unknown>
}
function fail(): never {
  throw new AgentFieldError('', '账户环境响应不符合合同')
}
export function parseBindingWrite(v: unknown): BindingWrite {
  const row = exact(v, ['account_id', 'agent_id', 'profile_external_id', 'ownership']),
    owners = exact(row.ownership, ['owner_user_id', 'owner_team_id'])
  for (const [field, value] of Object.entries({
    account_id: row.account_id,
    agent_id: row.agent_id,
    ...owners,
  }))
    if (!uuid(value)) throw new AgentFieldError(field, '账户、设备和归属 ID 必须是完整 UUID')
  if (
    typeof row.profile_external_id !== 'string' ||
    !row.profile_external_id.trim() ||
    row.profile_external_id !== row.profile_external_id.normalize('NFC').trim() ||
    [...row.profile_external_id].length > 128 ||
    /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(row.profile_external_id)
  )
    throw new AgentFieldError('profile_external_id', 'Profile ID 需为 1 至 128 个字符')
  return {
    account_id: row.account_id as string,
    agent_id: row.agent_id as string,
    profile_external_id: row.profile_external_id,
    ownership: {
      owner_user_id: owners.owner_user_id as string,
      owner_team_id: owners.owner_team_id as string,
    },
  }
}
function parseBinding(v: unknown): ProfileBinding {
  const row = exact(v, [
    'account_id',
    'agent_id',
    'profile_external_id',
    'ownership',
    'id',
    'revision',
    'identity_state',
    'verified_at',
  ])
  const body = parseBindingWrite({
    account_id: row.account_id,
    agent_id: row.agent_id,
    profile_external_id: row.profile_external_id,
    ownership: row.ownership,
  })
  if (
    !uuid(row.id) ||
    !positive(row.revision) ||
    !['VALID', 'LOGIN_REQUIRED', 'CHALLENGE', 'IDENTITY_MISMATCH', 'UNKNOWN'].includes(
      String(row.identity_state),
    ) ||
    (row.verified_at !== null &&
      (typeof row.verified_at !== 'string' || !Number.isFinite(Date.parse(row.verified_at))))
  )
    fail()
  return {
    ...body,
    id: row.id,
    revision: row.revision,
    identity_state: row.identity_state as ProfileBinding['identity_state'],
    verified_at: row.verified_at as string | null,
  }
}
export const bindingApi = {
  list: (query: { page_size: number; cursor?: string }, signal?: AbortSignal) => {
    if (![20, 50, 100, 200].includes(query.page_size))
      throw new AgentFieldError('page_size', '分页大小无效')
    const params = new URLSearchParams({ page_size: String(query.page_size) })
    if (query.cursor) params.set('cursor', query.cursor)
    return environmentRequest<BindingPage>(
      `profile-bindings?${params}`,
      (value) => {
        const row = exact(value, ['items', 'next_cursor', 'data_as_of', 'scope_version'])
        if (
          !Array.isArray(row.items) ||
          row.items.length > query.page_size ||
          !positive(row.scope_version) ||
          (row.next_cursor !== null &&
            (typeof row.next_cursor !== 'string' ||
              !row.next_cursor ||
              row.next_cursor.length > 2048)) ||
          typeof row.data_as_of !== 'string' ||
          !Number.isFinite(Date.parse(row.data_as_of))
        )
          fail()
        const items = row.items.map(parseBinding)
        if (
          new Set(items.map((item) => item.id)).size !== items.length ||
          (row.next_cursor && !items.length)
        )
          fail()
        return { ...row, items } as unknown as BindingPage
      },
      { signal },
    )
  },
  get: (id: string, signal?: AbortSignal) =>
    environmentRequest(
      `profile-bindings/${encodeURIComponent(id)}`,
      (v) => {
        const row = parseBinding(v)
        if (row.id !== id) fail()
        return row
      },
      { signal },
    ),
  write: (intent: BindingIntent, csrf: string) =>
    environmentRequest<ProfileBinding | UnboundBinding>(
      `profile-bindings${intent.id ? '/' + encodeURIComponent(intent.id) : ''}${intent.operation === 'UNBIND' ? '/unbind' : ''}`,
      (value) => {
        if (intent.operation === 'UNBIND') {
          const row = exact(value, ['id', 'revision', 'unbound_at'])
          if (
            row.id !== intent.id ||
            row.revision !== (intent.revision ?? 0) + 1 ||
            typeof row.unbound_at !== 'string' ||
            !Number.isFinite(Date.parse(row.unbound_at))
          )
            fail()
          return row as unknown as UnboundBinding
        }
        const row = parseBinding(value),
          body = intent.body as BindingWrite
        if (
          (intent.id && row.id !== intent.id) ||
          row.revision !== (intent.revision ?? 0) + 1 ||
          row.account_id !== body.account_id ||
          row.agent_id !== body.agent_id ||
          row.profile_external_id !== body.profile_external_id ||
          row.ownership.owner_user_id !== body.ownership.owner_user_id ||
          row.ownership.owner_team_id !== body.ownership.owner_team_id ||
          row.identity_state !== 'UNKNOWN' ||
          row.verified_at !== null
        )
          fail()
        return row
      },
      {
        method: intent.operation === 'SAVE' && intent.id ? 'PUT' : 'POST',
        headers: {
          'X-CSRF-Token': csrf,
          'Idempotency-Key': intent.key,
          ...(intent.revision !== undefined ? { 'If-Match': `"${intent.revision}"` } : {}),
        },
        body: JSON.stringify(intent.body),
      },
      intent.operation === 'SAVE' && !intent.id ? 201 : 200,
    ),
}
