import { orbitAuthHeaders, orbitCredentials } from './authentication'

/** 本地账号与外部OIDC已验证身份分开；当前目录不将邮箱或昵称当作身份凭证。 */
export interface OrbitUser {
  id: string
  revision: number
  display_name: string
  nickname: string
  email: string
  phone: string
  team_id: string
  role_ids: string[]
  data_role: 'USER' | 'TEAM_ADMIN' | 'SUPER_ADMIN'
  managed_team_ids: string[]
  status: 'INVITED' | 'ENABLED' | 'DISABLED'
  identity_status: 'LOCAL_ACCOUNT' | 'UNVERIFIED' | 'OIDC_VERIFIED'
}
export interface UserPage {
  items: OrbitUser[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export type UserWrite = Omit<OrbitUser, 'id' | 'revision' | 'identity_status'>
export interface UserCapabilities {
  can_create: boolean
  csrf_token: string
  actor_user_id: string
  protected_user_ids: string[]
  data_role: OrbitUser['data_role']
  managed_team_ids: string[]
}
export interface ReferencePage {
  items: { id: string; name: string }[]
  next_cursor: string | null
}
/** 只读投递元数据；管理端永远不取得一次性邀请凭据或链接。 */
export interface InvitationStatus {
  can_invite: boolean
  blocked_reason: string | null
  invitation: null | {
    id: string
    state: 'ACTIVE' | 'CONSUMED' | 'REVOKED' | 'EXPIRED'
    created_at: string
    expires_at: string
    delivery_state: 'QUEUED' | 'SENDING' | 'ACCEPTED' | 'FAILED' | 'UNKNOWN' | null
    failure_code: string | null
  }
}
export interface InvitationAcknowledgment {
  id: string
  revision: number
  state: 'INVITATION_QUEUED'
  request_id: string
}
export class UserRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/users${path}`, {
      cache: 'no-store',
      credentials: orbitCredentials(),
      ...init,
      headers: orbitAuthHeaders(init.headers),
    })
  } catch {
    throw new Error('网络中断，请重试；重复保存会沿用原幂等键')
  }
  let body
  try {
    body = await response.json()
  } catch {
    throw new Error('服务响应无效，请稍后重试')
  }
  if (!response.ok || (typeof body?.code === 'number' && body.code !== 200)) {
    throw new UserRequestError(
      body?.message ?? body?.msg ?? '人员请求失败，请重试',
      response.status,
    )
  }
  return body
}
export const userApi = {
  invitationStatus: (id: string) =>
    request<InvitationStatus>(`/${encodeURIComponent(id)}/invitation`),
  invite: (id: string, revision: number, csrf: string, key: string) =>
    request<InvitationAcknowledgment>(`/${encodeURIComponent(id)}/invitation`, {
      method: 'POST',
      headers: {
        'X-CSRF-Token': csrf,
        'Idempotency-Key': key,
        'If-Match': `"${revision}"`,
      },
    }),
  update: (id: string, value: UserWrite, revision: number, csrf: string, key: string) =>
    request<OrbitUser>(`/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
        'Idempotency-Key': key,
        'If-Match': `"${revision}"`,
      },
      body: JSON.stringify(value),
    }),
  capabilities: () => request<UserCapabilities>('/capabilities'),
  options: (query: URLSearchParams) => request<ReferencePage>(`/reference-options?${query}`),
  create: (value: UserWrite, csrf: string, key: string) =>
    request<OrbitUser>('', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Idempotency-Key': key },
      body: JSON.stringify(value),
    }),
  list: (query: URLSearchParams) => request<UserPage>(`?${query}`),
  get: (id: string) => request<OrbitUser>(`/${encodeURIComponent(id)}`),
}
