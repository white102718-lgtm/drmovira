import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { hashMaterialFile } from './material-hash'

export interface MaterialMetadata {
  name: string
  category_id: string
  tag_ids: string[]
}
export interface MaterialAsset extends MaterialMetadata {
  id: string
  revision: number
  ownership: { owner_user_id: string; owner_team_id: string }
  kind: 'IMAGE' | 'VIDEO'
  state: string
  sha256: string
  preview_url: string | null
  duration_seconds: string | null
}
/** 独立安全技术扩展；保留原Asset合同，不把历史READY视为检查通过。 */
export interface MaterialSecurity {
  asset_id: string
  revision: number
  scan_status: 'CLEAN' | 'INFECTED' | 'UNVERIFIED' | 'SCANNING'
  hash_matches: boolean
  engine_version: string | null
  database_version: number | null
  receipt_at: string | null
  rescan_allowed: boolean
  rescan_reason: string
}
export interface MaterialTaxonomy {
  id: string
  name: string
  revision: number
  state: string
  group?: string
  /** 当前可读、未归档素材关联数；没有素材读取权限时未知。 */
  visible_asset_count?: number | null
}
export interface MaterialPage<T> {
  items: T[]
  next_cursor: string | null
  data_as_of: string
  scope_version: number
}
export interface MaterialCapabilities {
  csrf_token: string
  default_category_id: string
  storage_mode: string
  max_batch_size: number
}
interface UploadSession {
  id: string
  asset_id: string
  expires_at: string
  part_size: number
  parts: { part_number: number; url: string }[]
}
export interface MaterialUploadState {
  sha256?: string
  session?: UploadSession
  createKey?: string
  completeKey?: string
  etags?: { part_number: number; etag: string }[]
  partKeys?: Record<number, string>
}
export class MaterialApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/${path}`, {
      ...init,
      credentials: orbitCredentials(),
      cache: 'no-store',
      headers: orbitAuthHeaders({ 'Content-Type': 'application/json', ...init.headers }),
    })
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new MaterialApiError(0, 'NETWORK_UNAVAILABLE', '网络中断，可保留同一上传任务重试')
  }
  let value
  try {
    value = await response.json()
  } catch {
    throw new MaterialApiError(502, 'INVALID_RESPONSE', '服务响应格式无效')
  }
  if (!response.ok || (typeof value?.code === 'number' && value.code !== 200)) {
    throw new MaterialApiError(
      response.status,
      value?.code ?? 'REQUEST_FAILED',
      value?.message ?? value?.msg ?? '素材操作失败',
    )
  }
  return value
}
const writeHeaders = (csrf: string, key: string, revision?: number) => ({
  'X-CSRF-Token': csrf,
  'Idempotency-Key': key,
  ...(revision !== undefined ? { 'If-Match': `"${revision}"` } : {}),
})
export const materialApi = {
  capabilities: () => request<MaterialCapabilities>('assets/capabilities'),
  list: (query: URLSearchParams) => request<MaterialPage<MaterialAsset>>(`assets?${query}`),
  get: (id: string) => request<MaterialAsset>(`assets/${encodeURIComponent(id)}`),
  security: (ids: string[]) =>
    request<{ items: MaterialSecurity[] }>(
      `assets/security?${new URLSearchParams({ asset_ids: ids.join(',') })}`,
    ),
  securityDetail: (id: string) =>
    request<MaterialSecurity>(`assets/${encodeURIComponent(id)}/security`),
  rescan: (asset: MaterialAsset, reason: string, csrf: string, key: string) =>
    request<MaterialAsset>(`assets/${encodeURIComponent(asset.id)}/rescan`, {
      method: 'POST',
      headers: writeHeaders(csrf, key, asset.revision),
      body: JSON.stringify({ reason }),
    }),
  references: (id: string, cursor = '') =>
    request<{
      items: { id: string; kind: string; resource_id: string; active: boolean }[]
      next_cursor: string | null
    }>(
      `assets/${encodeURIComponent(id)}/references${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`,
    ),
  edit: (asset: MaterialAsset, value: MaterialMetadata, csrf: string, key: string) =>
    request<MaterialAsset>(`assets/${asset.id}`, {
      method: 'PUT',
      headers: writeHeaders(csrf, key, asset.revision),
      body: JSON.stringify(value),
    }),
  archive: (assets: MaterialAsset[], reason: string, csrf: string, key: string) =>
    request('assets/bulk-delete', {
      method: 'POST',
      headers: writeHeaders(csrf, key),
      body: JSON.stringify({
        assets: assets.map(({ id, revision }) => ({ id, revision })),
        reason,
      }),
    }),
  taxonomy: (
    kind: 'tags' | 'categories',
    cursor = '',
    filters: { q?: string; status?: string; page_size?: number } = {},
  ) => {
    const query = new URLSearchParams()
    if (cursor) query.set('cursor', cursor)
    if (filters.q) query.set('q', filters.q)
    if (filters.status) query.set('status', filters.status)
    if (filters.page_size) query.set('page_size', String(filters.page_size))
    return request<MaterialPage<MaterialTaxonomy>>(`${kind}${query.size ? `?${query}` : ''}`)
  },
  saveTaxonomy: (
    kind: 'tags' | 'categories',
    value: { name: string; group?: string },
    csrf: string,
    key: string,
    existing?: MaterialTaxonomy,
  ) =>
    request<MaterialTaxonomy>(`${kind}${existing ? `/${existing.id}` : ''}`, {
      method: existing ? 'PUT' : 'POST',
      headers: writeHeaders(csrf, key, existing?.revision),
      body: JSON.stringify(value),
    }),
  archiveTaxonomy: (
    kind: 'tags' | 'categories',
    value: MaterialTaxonomy,
    reason: string,
    csrf: string,
    key: string,
  ) =>
    request(`${kind}/${value.id}/archive`, {
      method: 'POST',
      headers: writeHeaders(csrf, key, value.revision),
      body: JSON.stringify({ reason }),
    }),
  async upload(
    file: File,
    metadata: MaterialMetadata,
    csrf: string,
    progress: (n: number) => void,
    state: MaterialUploadState,
    signal?: AbortSignal,
  ) {
    const allowed = ['image/png', 'image/jpeg', 'video/mp4']
    const maximum = file.type === 'video/mp4' ? 500 * 1024 * 1024 : 20 * 1024 * 1024
    if (!allowed.includes(file.type) || file.size < 1 || file.size > maximum)
      throw new Error('仅支持JPEG/PNG≤20MiB或MP4≤500MiB')
    state.sha256 ??= await hashMaterialFile(file, signal)
    state.createKey ??= crypto.randomUUID()
    state.session ??= await request<UploadSession>('assets/upload-sessions', {
      method: 'POST',
      signal,
      headers: writeHeaders(csrf, state.createKey),
      body: JSON.stringify({ metadata, mime: file.type, size: file.size, sha256: state.sha256 }),
    })
    state.etags ??= []
    state.partKeys ??= {}
    const session = state.session
    if (session.part_size === 0) {
      const existing = await materialApi.get(session.asset_id)
      if (existing.state !== 'READY' || existing.sha256 !== state.sha256) {
        throw new Error('已有素材状态发生变化，请重新创建上传任务')
      }
      progress(100)
      return existing
    }
    if (
      !Number.isInteger(session.part_size) ||
      session.part_size < 1 ||
      session.part_size > 8 * 1024 * 1024
    )
      throw new Error('上传分片配置无效')
    for (const part of session.parts) {
      signal?.throwIfAborted()
      if (state.etags.some((p) => p.part_number === part.part_number)) continue
      // 忽略服务返回的任意主机URL，固定使用同源会话/分片路由，防止凭据外送。
      const blob = file.slice(
        (part.part_number - 1) * session.part_size,
        part.part_number * session.part_size,
      )
      state.partKeys[part.part_number] ??= crypto.randomUUID()
      const result = await request<{ part_number: number; etag: string }>(
        `assets/upload-sessions/${encodeURIComponent(session.id)}/parts/${part.part_number}`,
        {
          method: 'PUT',
          signal,
          headers: {
            ...writeHeaders(csrf, state.partKeys[part.part_number]),
            'Content-Type': 'application/octet-stream',
          },
          body: blob,
        },
      )
      state.etags.push(result)
      progress(Math.floor((state.etags.length / session.parts.length) * 95))
    }
    state.completeKey ??= crypto.randomUUID()
    const result = await request<MaterialAsset>(
      `assets/upload-sessions/${encodeURIComponent(session.id)}/complete`,
      {
        method: 'POST',
        signal,
        headers: writeHeaders(csrf, state.completeKey),
        body: JSON.stringify({ size: file.size, sha256: state.sha256, parts: state.etags }),
      },
    )
    progress(100)
    return result
  },
}
