import { orbitAuthHeaders, orbitCredentials } from './authentication'

export interface BusinessRole {
  id: string
  name: string
  revision: number
  menu_codes: string[]
  permission_codes: string[]
}
export type RoleWrite = Pick<BusinessRole, 'name' | 'menu_codes' | 'permission_codes'>
export interface RoleCapabilities {
  menus: string[]
  permissions: string[]
  built_in_role_ids: string[]
  csrf_token: string
}
export interface RolePage {
  items: BusinessRole[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export class RoleApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

/** 角色请求不使用会持久缓存请求体的通用重复提交拦截器；会话及CSRF只在内存。 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/roles${path}`, {
      ...init,
      credentials: orbitCredentials(),
      cache: 'no-store',
      headers: orbitAuthHeaders({
        'Content-Type': 'application/json',
        ...init.headers,
      }),
    })
  } catch {
    throw new RoleApiError(0, 'NETWORK_UNAVAILABLE', '网络中断，重试会保留同一次保存意图')
  }
  let value
  try {
    value = await response.json()
  } catch {
    throw new RoleApiError(502, 'INVALID_RESPONSE', '服务响应无效，请稍后重试')
  }
  if (!response.ok || (typeof value?.code === 'number' && value.code !== 200)) {
    throw new RoleApiError(
      response.status,
      value?.code ?? 'REQUEST_FAILED',
      value?.message ?? value?.msg ?? '请求失败，请刷新重试',
    )
  }
  return value
}
export const roleApi = {
  capabilities: () => request<RoleCapabilities>('/capabilities'),
  list: (query: URLSearchParams) => request<RolePage>(`?${query}`),
  get: (id: string) => request<BusinessRole>(`/${encodeURIComponent(id)}`),
  save: (value: RoleWrite, csrf: string, key: string, existing?: BusinessRole) =>
    request<BusinessRole>(existing ? `/${encodeURIComponent(existing.id)}` : '', {
      method: existing ? 'PUT' : 'POST',
      headers: {
        'X-CSRF-Token': csrf,
        'Idempotency-Key': key,
        ...(existing ? { 'If-Match': `"${existing.revision}"` } : {}),
      },
      body: JSON.stringify(value),
    }),
}
