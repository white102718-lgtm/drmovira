/** 标签分类动作独立授权；未知写结果保留原意图，目录不依赖素材读取权限。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import { MaterialApiError, type MaterialTaxonomy, type MaterialPage } from './materials'
export type TaxonomyKind = 'tags' | 'categories'
export type TaxonomyOperation = 'READ' | 'CREATE' | 'EDIT' | 'ARCHIVE'
export interface TaxonomyCapability {
  actor_id: number
  tenant_id: string
  csrf_token: string | null
}
export interface TaxonomyIntent {
  kind: TaxonomyKind
  operation: Exclude<TaxonomyOperation, 'READ'>
  actor_id: number
  tenant_id: string
  id?: string
  revision?: number
  key: string
  body: { name: string; group?: string } | { reason: string }
}
export class TaxonomyApiError extends MaterialApiError {
  constructor(
    status: number,
    code: string,
    message: string,
    public unknown_result = false,
  ) {
    super(status, code, message)
  }
}
export const taxonomyAuthContext = () => JSON.stringify([orbitCredentials(), orbitAuthHeaders()])
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/.test(v)
const integer = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v >= 1
const text = (v: unknown, max: number, min = 0): v is string =>
  typeof v === 'string' &&
  [...v].length >= min &&
  [...v].length <= max &&
  !/[\p{Cc}\p{Cf}\p{Cs}\u2028\u2029]/u.test(v)
const exact = (v: unknown, keys: string[]): v is Record<string, unknown> =>
  !!v &&
  typeof v === 'object' &&
  !Array.isArray(v) &&
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k))
function invalid(): never {
  throw new TaxonomyApiError(502, 'INVALID_RESPONSE', '标签分类响应不符合合同')
}
export function parseTaxonomy(v: unknown, kind: TaxonomyKind, counts: boolean): MaterialTaxonomy {
  const keys = [
    'id',
    'name',
    'revision',
    'state',
    ...(kind === 'tags' ? ['group'] : []),
    ...(counts ? ['visible_asset_count'] : []),
  ]
  if (
    !exact(v, keys) ||
    !uuid(v.id) ||
    !text(v.name, 30, 1) ||
    !integer(v.revision) ||
    !['ENABLED', 'DISABLED'].includes(String(v.state)) ||
    (kind === 'tags' && !text(v.group, 30)) ||
    (counts &&
      v.visible_asset_count !== null &&
      !(
        typeof v.visible_asset_count === 'number' &&
        Number.isSafeInteger(v.visible_asset_count) &&
        v.visible_asset_count >= 0
      ))
  )
    invalid()
  return v as unknown as MaterialTaxonomy
}
export function parseTaxonomyPage(
  v: unknown,
  kind: TaxonomyKind,
  size: number,
): MaterialPage<MaterialTaxonomy> {
  if (
    !exact(v, ['items', 'next_cursor', 'data_as_of', 'scope_version']) ||
    !Array.isArray(v.items) ||
    v.items.length > size ||
    !integer(v.scope_version) ||
    (v.next_cursor !== null && !text(v.next_cursor, 2048, 1)) ||
    typeof v.data_as_of !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(v.data_as_of) ||
    !Number.isFinite(Date.parse(v.data_as_of)) ||
    new Date(v.data_as_of).toISOString() !== v.data_as_of
  )
    invalid()
  let previous = ''
  const items = v.items.map((item) => {
    const parsed = parseTaxonomy(item, kind, true)
    if (parsed.id <= previous) invalid()
    previous = parsed.id
    return parsed
  })
  if (v.next_cursor && !items.length) invalid()
  return { ...v, items } as unknown as MaterialPage<MaterialTaxonomy>
}
async function readBody(response: Response, signal: AbortSignal) {
  const reader = response.body?.getReader()
  if (!reader) invalid()
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let result = '',
    size = 0
  const abort = () => {
    void reader.cancel().catch(() => {})
  }
  signal.addEventListener('abort', abort, { once: true })
  try {
    for (;;) {
      signal.throwIfAborted()
      const chunk = await reader.read()
      if (chunk.done) break
      size += chunk.value.byteLength
      if (size > 2 * 1024 * 1024) invalid()
      result += decoder.decode(chunk.value, { stream: true })
    }
    signal.throwIfAborted()
    return JSON.parse(result + decoder.decode()) as unknown
  } finally {
    signal.removeEventListener('abort', abort)
    try {
      await reader.cancel()
    } catch {
      /* 不覆盖原响应错误 */
    }
    reader.releaseLock()
  }
}
async function request<T>(
  path: string,
  parse: (v: unknown) => T,
  init: RequestInit = {},
  expected = 200,
): Promise<T> {
  const context = taxonomyAuthContext(),
    controller = new AbortController(),
    cancel = () => controller.abort()
  let status = 0
  const write = !!init.method && init.method !== 'GET'
  init.signal?.throwIfAborted()
  init.signal?.addEventListener('abort', cancel, { once: true })
  const timer = setTimeout(cancel, 15000)
  try {
    const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/${path}`, {
      ...init,
      credentials: orbitCredentials(),
      cache: 'no-store',
      signal: controller.signal,
      headers: orbitAuthHeaders({ 'Content-Type': 'application/json', ...init.headers }),
    })
    status = response.status
    let body: unknown
    try {
      body = await readBody(response, controller.signal)
    } catch {
      throw new TaxonomyApiError(
        [401, 403, 404, 409].includes(status) ? status : 502,
        'INVALID_RESPONSE',
        '标签分类响应未能确认',
        write,
      )
    }
    if (context !== taxonomyAuthContext())
      throw new TaxonomyApiError(
        409,
        'SESSION_CONTEXT_CHANGED',
        '认证上下文已变化，请重新打开目录',
        write,
      )
    if (!response.ok) {
      const value = body as Record<string, unknown>
      const valid =
        exact(value, ['code', 'message', 'field_errors', 'retryable', 'request_id']) &&
        text(value.code, 64, 1) &&
        text(value.message, 1000, 1) &&
        Array.isArray(value.field_errors) &&
        value.field_errors.length <= 100 &&
        typeof value.retryable === 'boolean' &&
        uuid(value.request_id)
      throw new TaxonomyApiError(
        status,
        valid ? String(value.code) : 'INVALID_ERROR_RESPONSE',
        valid ? String(value.message) : '标签分类错误响应未能确认',
        write && (!valid || status >= 500),
      )
    }
    if (status !== expected)
      throw new TaxonomyApiError(502, 'UNEXPECTED_STATUS', '标签分类响应状态未能确认', write)
    try {
      return parse(body)
    } catch {
      throw new TaxonomyApiError(
        502,
        'INVALID_RESPONSE',
        '标签分类响应未能确认，请保留原请求重试',
        write,
      )
    }
  } catch (e) {
    if (e instanceof TaxonomyApiError) throw e
    if (init.signal?.aborted) throw new DOMException('请求已取消', 'AbortError')
    throw new TaxonomyApiError(status, 'NETWORK_UNAVAILABLE', '连接中断或超时，请重试原请求', write)
  } finally {
    clearTimeout(timer)
    init.signal?.removeEventListener('abort', cancel)
  }
}
export const taxonomyApi = {
  capabilities: (operation: TaxonomyOperation, signal?: AbortSignal) =>
    request<TaxonomyCapability>(
      `material-taxonomy/capabilities?operation=${operation}`,
      (v) => {
        if (
          !exact(v, ['actor_id', 'tenant_id', 'csrf_token']) ||
          !integer(v.actor_id) ||
          !uuid(v.tenant_id) ||
          (operation === 'READ' ? v.csrf_token !== null : !text(v.csrf_token, 255, 16))
        )
          invalid()
        return v as unknown as TaxonomyCapability
      },
      { signal },
    ),
  list: (
    kind: TaxonomyKind,
    query: { q?: string; status?: string; page_size: number; cursor?: string },
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams({ page_size: String(query.page_size) })
    for (const field of ['q', 'status', 'cursor'] as const)
      if (query[field]) params.set(field, query[field]!)
    return request(`${kind}?${params}`, (v) => parseTaxonomyPage(v, kind, query.page_size), {
      signal,
    })
  },
  get: (kind: TaxonomyKind, id: string, signal?: AbortSignal) =>
    request(
      `${kind}/${encodeURIComponent(id)}`,
      (v) => {
        const result = parseTaxonomy(v, kind, true)
        if (result.id !== id) invalid()
        return result
      },
      { signal },
    ),
  write: (intent: TaxonomyIntent, csrf: string) =>
    request<MaterialTaxonomy>(
      `${intent.kind}${intent.id ? '/' + encodeURIComponent(intent.id) : ''}${intent.operation === 'ARCHIVE' ? '/archive' : ''}`,
      (v) => {
        const result = parseTaxonomy(v, intent.kind, false)
        if (
          (intent.id && result.id !== intent.id) ||
          result.revision !== (intent.revision ?? 0) + 1 ||
          (intent.operation === 'ARCHIVE' && result.state !== 'DISABLED') ||
          ('name' in intent.body &&
            (result.name !== intent.body.name ||
              (intent.kind === 'tags' && result.group !== intent.body.group)))
        )
          invalid()
        return result
      },
      {
        method: intent.operation === 'EDIT' ? 'PUT' : 'POST',
        headers: {
          'X-CSRF-Token': csrf,
          'Idempotency-Key': intent.key,
          ...(intent.revision !== undefined ? { 'If-Match': `"${intent.revision}"` } : {}),
        },
        body: JSON.stringify(intent.body),
      },
      intent.operation === 'CREATE' ? 201 : 200,
    ),
}
