/** 投放身份观察读取；严格校验原AccountIdentities，不将观察结果当作平台写授权。 */
import { referenceRequest, ReferenceApiError } from './references'
import type { AccountIdentities } from './account-details'

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const externalId = /^[0-9]{1,64}$/
function invalid(): never {
  throw new ReferenceApiError(
    502,
    'INVALID_IDENTITY_RESPONSE',
    '身份观察响应不符合原合同，未使用该结果',
  )
}
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid()
  const row = value as Record<string, unknown>
  if (Object.keys(row).length !== keys.length || keys.some((key) => !(key in row))) return invalid()
  return row
}
function text(value: unknown, min: number, max: number): value is string {
  return typeof value === 'string' && [...value].length >= min && [...value].length <= max
}
export function parseAccountIdentities(value: unknown): AccountIdentities {
  const row = object(value, ['account_id', 'resources', 'capability_version', 'observed_at'])
  if (
    typeof row.account_id !== 'string' ||
    !uuid.test(row.account_id) ||
    !text(row.capability_version, 1, 64) ||
    typeof row.observed_at !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(row.observed_at) ||
    !Number.isFinite(Date.parse(row.observed_at)) ||
    !Array.isArray(row.resources) ||
    row.resources.length > 5000
  )
    return invalid()
  const seen = new Set<string>()
  const resources = row.resources.map((value) => {
    const resource = object(value, ['external_id', 'name', 'kind', 'usable', 'reason_code'])
    if (
      typeof resource.external_id !== 'string' ||
      !externalId.test(resource.external_id) ||
      !text(resource.name, 0, 255) ||
      !['PAGE', 'PIXEL', 'APPLICATION'].includes(String(resource.kind)) ||
      typeof resource.usable !== 'boolean' ||
      !(resource.reason_code === null || text(resource.reason_code, 1, 64))
    )
      return invalid()
    const key = `${resource.kind}:${resource.external_id}`
    if (seen.has(key)) return invalid()
    seen.add(key)
    return {
      external_id: resource.external_id,
      name: resource.name,
      kind: resource.kind as 'PAGE' | 'PIXEL' | 'APPLICATION',
      usable: resource.usable,
      reason_code: resource.reason_code as string | null,
    }
  })
  return {
    account_id: row.account_id.toLowerCase(),
    resources,
    capability_version: row.capability_version,
    observed_at: row.observed_at,
  }
}
export const accountIdentitiesApi = {
  async get(accountId: string, signal?: AbortSignal): Promise<AccountIdentities> {
    if (!uuid.test(accountId))
      throw new ReferenceApiError(422, 'ACCOUNT_ID_INVALID', '账户ID不是规范UUID')
    const id = accountId.toLowerCase()
    const result = parseAccountIdentities(
      await referenceRequest<unknown>(`/accounts/${encodeURIComponent(id)}/identities`, { signal }),
    )
    if (result.account_id !== id) return invalid()
    return result
  },
}
