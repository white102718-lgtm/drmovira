import { referenceRequest, writeHeaders } from './references'

export interface VendorAlias {
  vendor_id: string
  alias: string | null
  revision: number
  updated_at: string | null
}
export interface VendorAliasResult extends VendorAlias {
  catalog_revision: number
}
export interface VendorAliasWrite {
  alias: string | null
  reason: string
}

/** 代称独立维护；名称、来源键、归属和平台字段均不进入此正文。 */
export function aliasIntent(alias: string, clear: boolean, reason: string): VendorAliasWrite {
  const normalized = alias.normalize('NFC').trim()
  const normalizedReason = reason.normalize('NFC').trim()
  const invalid = /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u
  if (!clear && (!normalized || [...normalized].length > 30 || invalid.test(alias)))
    throw new Error('代称须为1至30个字符，不能包含控制字符')
  if (!normalizedReason || [...normalizedReason].length > 1000 || invalid.test(reason))
    throw new Error('请填写1至1000字符的维护原因，不能包含控制字符')
  return { alias: clear ? null : normalized, reason: normalizedReason }
}

export const vendorAliasApi = {
  capabilities: () =>
    referenceRequest<{ can_manage: boolean; csrf_token: string }>('/vendor-aliases/capabilities'),
  get: (id: string) =>
    referenceRequest<VendorAliasResult>(`/vendor-aliases/${encodeURIComponent(id)}`),
  batch: (ids: string[]) =>
    referenceRequest<{ items: VendorAlias[]; catalog_revision: number }>(
      `/vendor-aliases?${new URLSearchParams({ ids: ids.join(',') })}`,
    ),
  save: (id: string, value: VendorAliasWrite, revision: number, csrf: string, key: string) =>
    referenceRequest<VendorAliasResult>(`/vendor-aliases/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: writeHeaders(csrf, key, revision),
      body: JSON.stringify(value),
    }),
}
