import { orbitAuthHeaders, orbitCredentials } from './authentication'

export interface Team {
  id: string
  name: string
  status: 'ENABLED' | 'DISABLED'
  revision: number
}
export interface TeamPage {
  items: Team[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export interface TeamCapabilities {
  data_role: 'USER' | 'TEAM_ADMIN' | 'SUPER_ADMIN'
  managed_team_ids: string[]
  can_create: boolean
  csrf_token: string
}
export class TeamApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

/** 团队请求不使用会持久缓存请求体的通用重复提交拦截器；会话及CSRF只在内存。 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/teams${path}`, {
      ...init,
      credentials: orbitCredentials(),
      cache: 'no-store',
      headers: orbitAuthHeaders({
        'Content-Type': 'application/json',
        ...init.headers,
      }),
    })
  } catch {
    throw new TeamApiError(0, 'NETWORK_UNAVAILABLE', '网络中断，重试会保留同一次保存意图')
  }
  let value
  try {
    value = await response.json()
  } catch {
    throw new TeamApiError(502, 'INVALID_RESPONSE', '服务响应无效，请稍后重试')
  }
  if (!response.ok || (typeof value?.code === 'number' && value.code !== 200)) {
    throw new TeamApiError(
      response.status,
      value?.code ?? 'REQUEST_FAILED',
      value?.message ?? value?.msg ?? '请求失败，请刷新重试',
    )
  }
  return value
}
export const teamApi = {
  capabilities: () => request<TeamCapabilities>('/capabilities'),
  list: (query: URLSearchParams) => request<TeamPage>(`?${query}`),
  get: (id: string) => request<Team>(`/${encodeURIComponent(id)}`),
  save: (value: Pick<Team, 'name' | 'status'>, csrf: string, key: string, existing?: Team) =>
    request<Team>(existing ? `/${encodeURIComponent(existing.id)}` : '', {
      method: existing ? 'PUT' : 'POST',
      headers: {
        'X-CSRF-Token': csrf,
        'Idempotency-Key': key,
        ...(existing ? { 'If-Match': `"${existing.revision}"` } : {}),
      },
      body: JSON.stringify(value),
    }),
}
