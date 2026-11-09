/** 原Assignment五字段与独立候选辅助接口；候选不是后续执行授权。 */
import { ReferenceApiError, referenceRequest, writeHeaders } from './references'
import type { AccountActionAck, AccountActionCapability } from './account-actions'

export interface AssignmentOwner {
  id: string
  name: string
  team_id: string
  team_name: string
}
export interface AssignmentVendor {
  id: string
  name: string
  alias: string | null
}
export interface AssignmentBody {
  operator_user_id: string
  owner_team_id: string
  vendor_id: string | null
  effective_from: string
  reason: string
}
export interface AssignmentIntent {
  accountId: string
  key: string
  capability: AccountActionCapability
  body: AssignmentBody
}
export interface AssignmentPage<T> {
  items: T[]
  next_cursor: string | null
}
export const accountAssignmentApi = {
  owners: (accountId: string, query: URLSearchParams, signal?: AbortSignal) =>
    referenceRequest<AssignmentPage<AssignmentOwner>>(
      `/accounts/${encodeURIComponent(accountId)}/assignment-options?kind=OWNER&${query}`,
      { signal },
    ),
  vendors: (accountId: string, owner: string, query: URLSearchParams, signal?: AbortSignal) =>
    referenceRequest<AssignmentPage<AssignmentVendor>>(
      `/accounts/${encodeURIComponent(accountId)}/assignment-options?kind=VENDOR&owner_user_id=${encodeURIComponent(owner)}&${query}`,
      { signal },
    ),
  async assign(intent: AssignmentIntent) {
    const value = await referenceRequest<AccountActionAck>(
      `/accounts/${encodeURIComponent(intent.accountId)}/assignment`,
      {
        method: 'PUT',
        headers: writeHeaders(intent.capability.csrf_token, intent.key, intent.capability.revision),
        body: JSON.stringify(intent.body),
      },
    )
    if (
      !value ||
      Object.keys(value).sort().join(',') !== 'id,request_id,revision,state' ||
      value.id !== intent.accountId ||
      value.revision !== intent.capability.revision + 1 ||
      value.state !== 'SCHEDULED' ||
      typeof value.request_id !== 'string' ||
      !value.request_id
    ) {
      throw new ReferenceApiError(502, 'INVALID_RESPONSE', '分配回执无效，请重试原请求确认结果')
    }
    return value
  },
}
