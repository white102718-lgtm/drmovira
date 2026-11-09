import { orbitAuthHeaders, orbitCredentials } from './authentication'

export interface ScopeFilter {
  q: string
  status: 'ACTIVE' | 'DISABLED' | 'UNKNOWN' | null
  auth_status: 'AUTHORIZED' | 'EXPIRED' | 'REVOKED' | 'UNKNOWN' | null
  operator_user_id: string | null
  vendor_id: string | null
}
export type ScopeRequest =
  | { mode: 'IDS'; account_ids: string[]; filter: null }
  | { mode: 'FILTER'; account_ids: []; filter: ScopeFilter }
export interface ScopeSnapshot {
  id: string
  count: number
  scope_version: number
  hash: string
  created_at: string
}
export interface ScopeMember {
  account_id: string
  external_id: string
  name: string
}
export interface ScopeMemberPage {
  items: ScopeMember[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export class ScopeApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

/** 独立业务合同返回真实HTTP状态；不经过会缓存POST请求体的若依通用拦截器。 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(
    `${import.meta.env.VITE_APP_BASE_API}/api/v1/scope-snapshots${path}`,
    {
      ...init,
      cache: 'no-store',
      credentials: orbitCredentials(),
      headers: orbitAuthHeaders({
        'Content-Type': 'application/json',
        ...init.headers,
      }),
    },
  )
  if (!response.ok) {
    let code = 'REQUEST_FAILED'
    try {
      code = (await response.json()).code || code
    } catch {
      /* 网关非JSON错误不回显原始HTML。 */
    }
    const message =
      response.status === 401
        ? '登录已失效，请重新登录'
        : response.status === 403
          ? '权限或会话校验已失效，请刷新后重试'
          : response.status === 404
            ? '范围或账户已不在当前数据权限内'
            : response.status === 409
              ? '权限或范围已变化，请重新冻结范围'
              : response.status === 422
                ? '范围条件或分页参数无效，请检查输入'
                : response.status === 400
                  ? '请求格式无效，请检查输入'
                  : '范围服务暂不可用，请重试'
    throw new ScopeApiError(response.status, code, message)
  }
  return response.json() as Promise<T>
}

/** 一次用户意图的请求体和幂等键保持在内存中，网络失败重试不得另建快照。 */
export function createScope(value: ScopeRequest, key: string, csrf: string, signal?: AbortSignal) {
  return request<ScopeSnapshot>('', {
    method: 'POST',
    signal,
    headers: { 'Idempotency-Key': key, 'X-CSRF-Token': csrf },
    body: JSON.stringify(value),
  })
}
export function getScopeCsrf(signal?: AbortSignal) {
  // Python辅助入口只依赖accounts.read，不能借导入动作取得会话令牌。
  return request<{ csrf_token: string; max_members: number; max_plan_accounts: number }>(
    '/capabilities',
    { signal },
  )
}
export function getScopeMembers(
  id: string,
  q: string,
  size: number,
  cursor: string | null,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ q, page_size: String(size) })
  if (cursor !== null) query.set('cursor', cursor)
  return request<ScopeMemberPage>(`/${encodeURIComponent(id)}/members?${query}`, { signal })
}
