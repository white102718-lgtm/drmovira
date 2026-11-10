/** 18列独立扩展；来源、覆盖与未知状态原样保留，不将空字段换成0。 */
import { referenceRequest } from './references'
import type { AccountObservation, OrbitAccount, AccountOwnerOption } from './accounts'

export interface AccountTextObservation {
  value: string | null
  code: string | null
  status: 'SYNCED' | 'UNSYNCED' | 'FAILED' | 'UNKNOWN'
  reason_code: string | null
  source: string
  observed_at: string | null
}
export interface AccountDetails {
  account_id: string
  revision: number
  source_revision: number
  owner_display: string | null
  vendor_display: {
    name: string | null
    source: string
    reason_code: string | null
    alias_source?: string
    alias_revision?: number | null
  }
  personal_profile: AccountTextObservation
  business_entity: AccountTextObservation
  payment_type: AccountTextObservation
  payment_method: AccountTextObservation
  blocked_reason: AccountTextObservation
  payable: AccountObservation
  lifetime_spend: AccountObservation
  business_managers: { external_id: string; name: string }[] | null
  identity_status: string
  identity_observed_at: string | null
  identity_count: number | null
  authorized_at: string | null
  unbound_at: string | null
  blocked_observed_at: string | null
  note: string | null
  spend_sync?: {
    reason_code: 'NOT_AUTHORIZED' | 'READ_REJECTED' | 'NOT_PROVIDED' | null
    observed_at: string
  } | null
  spend_window: {
    mode: string
    date_from: string | null
    date_to: string | null
    timezone: string
    reference_at: string
    coverage: 'COMPLETE' | 'PARTIAL' | 'NOT_COLLECTED'
    snapshot_id: string | null
  }
}
export interface ExtendedAccount {
  account: OrbitAccount
  details: AccountDetails
}
export interface AccountIdentities {
  account_id: string
  resources: {
    external_id: string
    name: string
    kind: 'PAGE' | 'PIXEL' | 'APPLICATION'
    usable: boolean
    reason_code: string | null
  }[]
  capability_version: string
  observed_at: string
}
export const accountDetailsApi = {
  owners: (query: URLSearchParams, signal?: AbortSignal) =>
    referenceRequest<{
      items: AccountOwnerOption[]
      next_cursor: string | null
    }>(`/accounts/owner-options?${query}`, { signal }),
  list: (query: URLSearchParams, signal?: AbortSignal) =>
    referenceRequest<{
      items: ExtendedAccount[]
      next_cursor: string | null
      data_as_of: string
      scope_version: number
      account_version: number
      metric_snapshot_id: string | null
    }>(`/accounts/extended?${query}`, { signal }),
  get: (id: string, query: URLSearchParams, signal?: AbortSignal) =>
    referenceRequest<ExtendedAccount>(`/accounts/${encodeURIComponent(id)}/details?${query}`, {
      signal,
    }),
  identities: (id: string, signal?: AbortSignal) =>
    referenceRequest<AccountIdentities>(`/accounts/${encodeURIComponent(id)}/identities`, {
      signal,
    }),
}

export const accountStates = { ACTIVE: '可用', DISABLED: '已停用', UNKNOWN: '未知' }
export const accountAuthorizations = {
  AUTHORIZED: '已授权',
  EXPIRED: '已过期',
  REVOKED: '已撤销',
  UNKNOWN: '未知',
}
export const accountDateModes: Record<string, string> = {
  TODAY: '今天',
  YESTERDAY: '昨天',
  LAST7: '过去7天',
  LAST14: '过去14天',
  LAST30: '过去30天',
  THISWEEK: '本周',
  LASTWEEK: '上周',
  THISMONTH: '本月',
  LASTMONTH: '上个月',
  MAX: '最大日期范围',
  CUSTOM: '自定义',
}
export function accountTime(value: string | null) {
  return value ? `${new Date(value).toLocaleString('zh-CN')}（本地时间）` : '未提供'
}
export function accountAmount(value: AccountObservation) {
  if (value.amount !== null) return `${value.amount} ${value.currency}`
  return value.status === 'FAILED'
    ? '读取失败'
    : value.status === 'UNSYNCED'
      ? '未同步'
      : '未提供/未知'
}
export function accountText(value: AccountTextObservation) {
  if (value.value !== null) return value.value
  if (value.reason_code === 'NOT_AUTHORIZED') return '未授权'
  if (value.status === 'FAILED') return '读取失败'
  return value.status === 'UNSYNCED' ? '未同步' : '未提供/未知'
}
export function accountPeriod(row: ExtendedAccount) {
  const w = row.details.spend_window
  return w.date_from && w.date_to
    ? `${w.date_from}${w.date_from === w.date_to ? '' : ` 至 ${w.date_to}`}（账户当地日）`
    : '尚无已发布业务日'
}

/** 采集尝试成功不代表日期覆盖完整，金额仍由原覆盖合同决定。 */
export function accountSpendStatus(details: AccountDetails) {
  const sync = details.spend_sync
  if (!sync) return '尚未读取消耗'
  if (sync.reason_code === 'NOT_AUTHORIZED') return '未获消耗读取权限'
  if (sync.reason_code === 'READ_REJECTED') return 'Meta 拒绝读取消耗'
  if (sync.reason_code === 'NOT_PROVIDED') return 'Meta 未返回日消耗，不能视为零'
  return '已读取返回的日消耗；完整性以日期覆盖为准'
}
