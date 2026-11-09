import { orbitAuthHeaders, orbitCredentials } from './authentication'

export interface AuditItem {
  id: string
  actor_user_id: string
  action_code: string
  target_id: string | null
  tenant_id: string
  reason: string
  evidence_ref: string | null
  occurred_at: string
  request_id: string
}
export interface AuditPage {
  items: AuditItem[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export interface AuditFilters {
  q: string
  operator_user_id: string
  date_from: string
  date_to: string
}
export class AuditApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message)
  }
}
/** 原合同只读接口；不写缓存，不传客户端tenant/actor授权，不记录游标。 */
export async function listAuditEvents(
  filters: AuditFilters,
  size: number,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<AuditPage> {
  const query = new URLSearchParams({ page_size: String(size) })
  for (const [name, value] of Object.entries(filters)) if (value) query.set(name, value)
  if (cursor) query.set('cursor', cursor)
  const response = await fetch(
    `${import.meta.env.VITE_APP_BASE_API}/api/v1/audit-events?${query}`,
    {
      cache: 'no-store',
      credentials: orbitCredentials(),
      signal,
      headers: orbitAuthHeaders(),
    },
  )
  if (!response.ok) {
    let code = 'REQUEST_FAILED'
    try {
      const body = await response.json()
      if (typeof body.code === 'string') code = body.code
    } catch {
      /* 网关原始HTML不展示，也不记录。 */
    }
    const message =
      response.status === 401
        ? '登录已失效，请重新登录'
        : response.status === 403
          ? '审计读取权限已失效，请联系管理员'
          : response.status === 409
            ? '权限或查询上下文已变化，请重新查询'
            : response.status === 422
              ? '查询条件无效，请检查操作者UUID、UTC日期及搜索长度'
              : code === 'AUDIT_HISTORY_INCOMPLETE'
                ? '历史审计缺少必要身份或请求标识，需要先核对数据，记录未被隐藏或补造'
                : '审计查询暂不可用，请重试'
    throw new AuditApiError(
      response.status,
      code,
      message,
      response.headers.get('X-Request-ID') || undefined,
    )
  }
  return response.json()
}
