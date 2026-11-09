/** 原账户动作合同；受理回执保持原义，不当作实时平台同步状态。 */
import { ReferenceApiError, referenceRequest, writeHeaders } from './references'

export type AccountAction = 'ASSIGNMENT' | 'SYNC' | 'UNBIND'
export interface AccountActionCapability {
  csrf_token: string
  revision: number
  next_effective_from: string | null
}
export interface AccountActionAck {
  id: string
  revision: number
  state: string
  request_id: string
}
export interface AccountReasonIntent {
  accountId: string
  action: 'SYNC' | 'UNBIND'
  capability: AccountActionCapability
  key: string
  reason: string
}

export const accountActionsApi = {
  capabilities: (id: string, action: AccountAction, signal?: AbortSignal) =>
    referenceRequest<AccountActionCapability>(
      `/accounts/${encodeURIComponent(id)}/actions/capabilities?action=${action}`,
      { signal },
    ),
  async reason(intent: AccountReasonIntent): Promise<AccountActionAck> {
    const value = await referenceRequest<AccountActionAck>(
      `/accounts/${encodeURIComponent(intent.accountId)}/${intent.action.toLowerCase()}`,
      {
        method: 'POST',
        headers: writeHeaders(intent.capability.csrf_token, intent.key, intent.capability.revision),
        body: JSON.stringify({ reason: intent.reason }),
      },
    )
    // 错形回执不能解除不确定保护，否则可能用新幂等键重复提交已受理动作。
    if (
      !value ||
      Object.keys(value).sort().join(',') !== 'id,request_id,revision,state' ||
      value.id !== intent.accountId ||
      value.revision !== intent.capability.revision + 1 ||
      value.state !== (intent.action === 'SYNC' ? 'WAITING_EXECUTOR' : 'SUCCEEDED') ||
      typeof value.request_id !== 'string' ||
      !value.request_id
    ) {
      throw new ReferenceApiError(502, 'INVALID_RESPONSE', '动作回执无效，请重试原请求确认结果')
    }
    return value
  },
}
