import { orbitAuthHeaders, orbitCredentials } from './authentication'

/** 密钥仅存在本次提交内存，不经过若依会缓存请求体的防重复提交拦截器。 */
export interface ConfigField {
  key: string
  label: string
  type: 'text' | 'integer' | 'select' | 'secret'
  required: boolean
  defaultValue: string | number | null
  minimum: number | null
  maximum: number | null
  options: string[]
}

export interface ConfigSection {
  key: string
  label: string
  fields: ConfigField[]
}

export interface Configuration {
  id: string
  section: string
  name: string
  enabled: boolean
  revision: number
  settings: Record<string, string | number>
  secrets: Record<string, { configured: boolean; hint: string }>
  verificationStatus: string
  verifiedAt: string | null
  updatedAt: string
}

export interface ConfigurationWrite {
  section: string
  name: string
  enabled: boolean
  settings: Record<string, string | number>
  secrets: Record<string, { operation: 'KEEP' | 'REPLACE' | 'CLEAR'; value?: string }>
  reason: string
}

export interface MaterialScannerProfile {
  id: string
  label: string
  availability: 'READY' | 'UNAVAILABLE'
}

/** 仅接受公开候选白名单；服务端基础设施字段不得进入页面状态。 */
export async function listMaterialScannerProfiles(): Promise<MaterialScannerProfile[]> {
  const result = await request<{ items: unknown[] }>('/material-scanner-profiles')
  if (
    !result ||
    Object.keys(result).join() !== 'items' ||
    !Array.isArray(result.items) ||
    result.items.length > 16
  ) {
    throw new ConfigurationApiError(502, 'INVALID_RESPONSE', '扫描候选响应无效')
  }
  const ids = new Set<string>()
  return result.items.map((item) => {
    if (!item || typeof item !== 'object')
      throw new ConfigurationApiError(502, 'INVALID_RESPONSE', '扫描候选响应无效')
    const row = item as Record<string, unknown>
    if (
      Object.keys(row).sort().join() !== 'availability,id,label' ||
      typeof row.id !== 'string' ||
      !/^[a-z0-9_-]{1,40}$/.test(row.id) ||
      ids.has(row.id) ||
      typeof row.label !== 'string' ||
      /[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(row.label) ||
      typeof row.availability !== 'string' ||
      !['READY', 'UNAVAILABLE'].includes(row.availability)
    ) {
      throw new ConfigurationApiError(502, 'INVALID_RESPONSE', '扫描候选响应无效')
    }
    const label = row.label.normalize('NFC').trim()
    if (Array.from(label).length < 1 || Array.from(label).length > 80) {
      throw new ConfigurationApiError(502, 'INVALID_RESPONSE', '扫描候选响应无效')
    }
    ids.add(row.id)
    return {
      id: row.id,
      label,
      availability: row.availability as MaterialScannerProfile['availability'],
    }
  })
}

/** 仅保留安全状态码和说明，便于区分明确拒绝与结果未知的网络失败。 */
export class ConfigurationApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

/** Bearer认证请求不携带Cookie，不缓存配置请求或打印异常对象中的请求体。 */
async function request<T>(path = '', init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(
      `${import.meta.env.VITE_APP_BASE_API}/api/v1/system-configurations${path}`,
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
  } catch {
    throw new ConfigurationApiError(0, 'NETWORK_UNAVAILABLE', '网络连接中断，请检查后重试')
  }
  let result
  try {
    result = await response.json()
  } catch {
    throw new ConfigurationApiError(
      response.ok ? 502 : response.status,
      'INVALID_RESPONSE',
      '服务响应无效，请稍后重试',
    )
  }
  if (!response.ok || (typeof result?.code === 'number' && result.code !== 200)) {
    const status =
      response.status === 200 && typeof result?.code === 'number' ? result.code : response.status
    throw new ConfigurationApiError(
      status,
      typeof result?.code === 'string' ? result.code : 'REQUEST_FAILED',
      status === 401
        ? '登录已失效，请重新登录'
        : typeof result?.message === 'string'
          ? result.message
          : '系统配置请求失败',
    )
  }
  return result as T
}

/** 只返回公开字段元数据和独立主密钥是否可用。 */
export function getConfigurationMetadata() {
  return request<{ sections: ConfigSection[]; encryptionReady: boolean }>('/metadata')
}

/** 列表/详情仅含凭据是否配置的脱敏状态。 */
export function listConfigurations() {
  return request<Configuration[]>()
}

/** 修改必须携带原版本；所有Token在服务端认证加密后落库。 */
export function saveConfiguration(
  value: ConfigurationWrite,
  existing?: Configuration,
  requestKey: string = crypto.randomUUID(),
) {
  return request<Configuration>(existing ? `/${encodeURIComponent(existing.id)}` : '', {
    method: existing ? 'PUT' : 'POST',
    headers: {
      'Idempotency-Key': requestKey,
      ...(existing ? { 'If-Match': `"${existing.revision}"` } : {}),
    },
    body: JSON.stringify(value),
  })
}

/** 只读探测不代表AI生成/广告写能力验证成功。 */
export function testConfiguration(value: Configuration, reason: string) {
  return request<{
    configuration: Configuration
    result: { status: string; message: string }
  }>(`/${encodeURIComponent(value.id)}/test`, {
    method: 'POST',
    headers: { 'If-Match': `"${value.revision}"` },
    body: JSON.stringify({ reason }),
  })
}

/** 历史响应不包含字段旧值、新值或密钥内容；版本游标避免新记录插入导致翻页重复。 */
export interface ConfigurationAudit {
  id: string
  actorId: number
  action: string
  revision: number
  beforeRevision: number | null
  beforeHash: string | null
  afterHash: string | null
  hashAlgorithm: string | null
  changedFields: string[]
  reason: string
  createdAt: string
}
export function getConfigurationHistory(id: string, beforeRevision?: number) {
  const query = new URLSearchParams({ pageSize: '50' })
  if (beforeRevision !== undefined) query.set('beforeRevision', String(beforeRevision))
  return request<{ items: ConfigurationAudit[]; nextBeforeRevision: number | null }>(
    `/${encodeURIComponent(id)}/history?${query}`,
  )
}
