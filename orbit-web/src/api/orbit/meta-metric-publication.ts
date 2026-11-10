/** 复用已保存METRICS配置，发布证明只由服务端真实读取生成。 */
import { referenceRequest, ReferenceApiError, writeHeaders } from './references'
export interface PublicationOptions {
  csrf_token: string
  configured: boolean
  api_version: string | null
  adapter_version: string
  attribution_windows: string[]
  action_report_times: string[]
  configurations: {
    id: string
    name: string
    revision: number
    head_revision: number
    settings: Record<string, unknown>
  }[]
  connections: { id: string; revision: number; kind: 'LOGIN' | 'BM'; status: 'ACTIVE' }[]
}
export interface PublicationSelection {
  configuration_id: string
  configuration_revision: number
  connection_id: string
  connection_revision: number
  account_id: string
  attribution_windows: string[]
  action_report_time: string
  maturity_days: number
  expected_revision: number
}
export interface PublicationResult {
  id: string
  version: string
  revision: number
  adapter_version: string
}
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const revision = (v: unknown, min = 1) => Number.isSafeInteger(v) && Number(v) >= min
const record = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)
function invalid(): never {
  throw new ReferenceApiError(
    502,
    'INVALID_METRIC_PUBLICATION_RESPONSE',
    '指标发布响应无效，请重新读取',
  )
}
export function parsePublicationOptions(value: unknown): PublicationOptions {
  if (
    !record(value) ||
    typeof value.csrf_token !== 'string' ||
    !value.csrf_token ||
    typeof value.configured !== 'boolean' ||
    (value.api_version !== null && value.api_version !== 'v24.0') ||
    value.adapter_version !== 'META_INSIGHTS_V24_EXPLICIT_V1' ||
    !Array.isArray(value.attribution_windows) ||
    !value.attribution_windows.length ||
    value.attribution_windows.some((v) => !['1d_click', '7d_click', '1d_view'].includes(v)) ||
    !Array.isArray(value.action_report_times) ||
    !value.action_report_times.length ||
    value.action_report_times.some((v) => !['impression', 'conversion', 'mixed'].includes(v)) ||
    !Array.isArray(value.configurations) ||
    !Array.isArray(value.connections) ||
    value.configurations.length > 200 ||
    value.connections.length > 200
  )
    invalid()
  for (const row of value.configurations)
    if (
      !record(row) ||
      !uuid(row.id) ||
      typeof row.name !== 'string' ||
      !revision(row.revision) ||
      !revision(row.head_revision, 0) ||
      !record(row.settings)
    )
      invalid()
  for (const row of value.connections)
    if (
      !record(row) ||
      !uuid(row.id) ||
      !revision(row.revision) ||
      !['LOGIN', 'BM'].includes(String(row.kind)) ||
      row.status !== 'ACTIVE'
    )
      invalid()
  return value as unknown as PublicationOptions
}
export function parsePublicationResult(value: unknown): PublicationResult {
  if (
    !record(value) ||
    !uuid(value.id) ||
    !revision(value.revision) ||
    typeof value.version !== 'string' ||
    !value.version ||
    value.adapter_version !== 'META_INSIGHTS_V24_EXPLICIT_V1'
  )
    invalid()
  return value as unknown as PublicationResult
}
const root = '/api/v1/metric-profiles'
export const metricPublicationApi = {
  options: async (signal?: AbortSignal) =>
    parsePublicationOptions(await referenceRequest(root + '/publication-options', { signal })),
  publish: async (value: PublicationSelection, csrf: string, key: string) =>
    parsePublicationResult(
      await referenceRequest(root + '/publications', {
        method: 'POST',
        headers: writeHeaders(csrf, key),
        body: JSON.stringify(value),
      }),
    ),
}
