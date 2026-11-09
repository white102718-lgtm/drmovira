/** 当前渠道独立扩展；原账户合同与历史广告事实保持不变。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { ReferenceApiError, referenceRequest, writeHeaders } from './references'
export interface AccountChannel {
  account_id: string
  channel_id: string | null
  revision: number
  csrf_token: string | null
}
export interface AccountChannelIntent {
  accountId: string
  revision: number
  csrf: string
  key: string
  body: { channel_id: string | null; reason: string }
}
export const accountChannelContext = () => JSON.stringify([orbitCredentials(), orbitAuthHeaders()])
const uuid = (v: unknown) =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
export function parseAccountChannel(value: unknown, accountId: string): AccountChannel {
  const v = value as AccountChannel
  if (
    !v ||
    typeof v !== 'object' ||
    Object.keys(v).sort().join(',') !== 'account_id,channel_id,csrf_token,revision' ||
    v.account_id !== accountId ||
    !uuid(v.account_id) ||
    (v.channel_id !== null && !uuid(v.channel_id)) ||
    !Number.isSafeInteger(v.revision) ||
    v.revision < 1 ||
    (v.csrf_token !== null &&
      (typeof v.csrf_token !== 'string' || !v.csrf_token || v.csrf_token.length > 2048))
  )
    throw new ReferenceApiError(502, 'INVALID_RESPONSE', '当前渠道回执无效，请确认原请求结果')
  return v
}
async function request(id: string, init: RequestInit = {}) {
  const context = accountChannelContext()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 15000)
  try {
    const value = await referenceRequest<unknown>(
      `/accounts/${encodeURIComponent(id)}/current-channel`,
      { ...init, signal: controller.signal },
    )
    if (context !== accountChannelContext())
      throw new ReferenceApiError(
        409,
        'SESSION_CONTEXT_CHANGED',
        '认证上下文已变化，请重新打开账户',
      )
    return parseAccountChannel(value, id)
  } finally {
    clearTimeout(timer)
  }
}
export const accountChannelApi = {
  get: (id: string) => request(id),
  async save(intent: AccountChannelIntent) {
    const value = await request(intent.accountId, {
      method: 'PUT',
      headers: writeHeaders(intent.csrf, intent.key, intent.revision),
      body: JSON.stringify(intent.body),
    })
    if (
      value.revision !== intent.revision + 1 ||
      value.channel_id !== intent.body.channel_id ||
      value.csrf_token !== null
    )
      throw new ReferenceApiError(502, 'INVALID_RESPONSE', '渠道变更回执无效，请重试原请求确认结果')
    return value
  },
}
