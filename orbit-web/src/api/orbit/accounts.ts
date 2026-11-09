/** 账户导入为持久化批次；202或QUEUED不等于平台资料已取得。 */
import { referenceRequest } from './references'

export interface AccountObservation {
  amount: string | null
  currency: string
  kind: 'AVAILABLE' | 'SPEND' | 'BILL' | 'UNKNOWN'
  status: 'SYNCED' | 'UNSYNCED' | 'FAILED' | 'UNKNOWN'
  source: string
  business_date: string | null
  observed_at: string | null
}
export interface AccountImportInput {
  vendor_id: string
  account_ids_text: string
  owner_user_id: string
  owner_team_id: string
}
export interface AccountImportRow {
  id: string
  token_index: number
  line_no: number
  column: number
  raw_display: string
  normalized_id: string | null
  duplicate_of: number | null
  state:
    | 'WAITING'
    | 'FETCHING'
    | 'SUCCEEDED'
    | 'ALREADY_EXISTS'
    | 'DUPLICATE'
    | 'INVALID'
    | 'FORBIDDEN'
    | 'OWNERSHIP_CONFLICT'
    | 'FAILED'
  account_id: string | null
  name: string | null
  spend: AccountObservation
  retryable: boolean
  error_code: string | null
  observed_at: string | null
}
export interface AccountImportBatch {
  id: string
  revision: number
  vendor_id: string
  state: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'PARTIAL_SUCCESS' | 'FAILED'
  total: number
  success_count: number
  failed_count: number
  duplicate_count: number
  rows: AccountImportRow[]
  next_cursor: string | null
}
export interface AccountOwnerOption {
  id: string
  name: string
  team_id: string
  team_name: string
}
export interface OrbitAccount {
  id: string
  external_id: string
  name: string
  ownership: { owner_user_id: string; owner_team_id: string }
  vendor_id: string | null
  vendor_alias: string | null
  currency: string
  timezone: { id: string; display_label: string; reference_at: string; offset_at: string }
  auth_status: 'AUTHORIZED' | 'EXPIRED' | 'REVOKED' | 'UNKNOWN'
  account_status: 'ACTIVE' | 'DISABLED' | 'UNKNOWN'
  spend: AccountObservation
  balance: AccountObservation
  revision: number
  synced_at: string | null
}
export const accountApi = {
  list: (query: URLSearchParams) =>
    referenceRequest<{
      items: OrbitAccount[]
      next_cursor: string | null
      data_as_of: string
      scope_version: number
    }>(`/accounts?${query}`),
  get: (id: string) => referenceRequest<OrbitAccount>(`/accounts/${encodeURIComponent(id)}`),
  capabilities: () =>
    referenceRequest<{
      csrf_token: string
      default_owner_user_id: string
      default_owner_team_id: string
    }>('/account-imports/capabilities'),
  owners: (query: URLSearchParams) =>
    referenceRequest<{ items: AccountOwnerOption[]; next_cursor: string | null }>(
      `/account-imports/owner-options?${query}`,
    ),
  createImport: (value: AccountImportInput, csrf: string, key: string) =>
    referenceRequest<AccountImportBatch>('/account-imports', {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrf, 'Idempotency-Key': key },
      body: JSON.stringify(value),
    }),
  getImport: (id: string, cursor?: string) =>
    referenceRequest<AccountImportBatch>(
      `/account-imports/${encodeURIComponent(id)}${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`,
    ),
}
