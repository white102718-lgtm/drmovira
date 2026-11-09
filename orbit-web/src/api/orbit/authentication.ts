import { getToken } from '@/utils/auth'
import type { OrbitUser } from './users'

export interface ProductSession {
  user: OrbitUser
  scope_version: number
  menu_codes: string[]
  permission_codes: string[]
  csrf_token: string
  expires_at: string
}
export interface LoginProvider {
  id: string
  name: string
}
let current: ProductSession | null = null
let pending: Promise<ProductSession | null> | null = null
let logoutKey: string | null = null
let epoch = 0

/** 只在内存保存服务端已验证会话的公开状态；HttpOnly凭据不进入JS存储。 */
export function cookieSessionActive() {
  return current !== null
}
export function clearCookieSession() {
  epoch++
  current = null
  pending = null
  logoutKey = null
}

/** 仅在规则恢复已核对真实actor/tenant后刷新运输CSRF；不替换身份或授予权限。 */
export function refreshCookieCsrfForRecovery(csrfToken: string): void {
  if (
    typeof csrfToken !== 'string' ||
    csrfToken.length < 16 ||
    csrfToken.length > 255 ||
    csrfToken !== csrfToken.trim() ||
    /[^\u0021-\u007e]/u.test(csrfToken)
  )
    throw new Error('恢复会话校验无效')
  if (current) current = { ...current, csrf_token: csrfToken }
}
export function cookieCsrf() {
  return current?.csrf_token
}
export function orbitCredentials(): RequestCredentials {
  return current ? 'same-origin' : 'omit'
}
export function orbitAuthHeaders(extra: HeadersInit = {}): Record<string, string> {
  const headers: Record<string, string> =
    extra instanceof Headers || Array.isArray(extra)
      ? Object.fromEntries(new Headers(extra).entries())
      : { ...extra }
  const token = getToken()
  if (current) {
    for (const key of Object.keys(headers))
      if (['authorization', 'x-csrf-token'].includes(key.toLowerCase())) delete headers[key]
    headers['X-CSRF-Token'] = current.csrf_token
  } else if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

export function safeReturnTo(value: unknown): string {
  if (typeof value !== 'string' || !value || [...value].length > 255 || value !== value.trim())
    return '/index'
  let candidate = value
  try {
    for (let attempt = 0; attempt < 8; attempt++) {
      if (
        !candidate.startsWith('/') ||
        candidate.startsWith('//') ||
        /[\\\p{Cc}\p{Cf}\p{Cs}]/u.test(candidate)
      )
        return '/index'
      const decoded = decodeURIComponent(candidate)
      if (decoded === candidate) return value
      candidate = decoded
    }
  } catch {
    /* 无效编码不进入路由或外部登录。 */
  }
  return '/index'
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1/auth${path}`, {
      ...init,
      cache: 'no-store',
      credentials: 'same-origin',
      referrerPolicy: 'no-referrer',
    })
  } catch {
    throw new Error('登录服务连接中断，请重新发起登录')
  }
}
async function json(response: Response) {
  let value
  try {
    value = await response.json()
  } catch {
    throw new Error('登录服务响应无效，请重新发起登录')
  }
  if (!response.ok) throw new Error(value?.message ?? '登录验证失败，请重新发起登录')
  return value
}
function remember(value: ProductSession): ProductSession {
  if (
    !value?.user?.id ||
    !Number.isSafeInteger(value.scope_version) ||
    !Array.isArray(value.menu_codes) ||
    !Array.isArray(value.permission_codes) ||
    typeof value.csrf_token !== 'string' ||
    value.csrf_token.length < 16 ||
    !Number.isFinite(Date.parse(value.expires_at))
  ) {
    throw new Error('登录会话响应无效，请重新发起登录')
  }
  current = value
  logoutKey = null
  return value
}
export async function probeCookieSession(): Promise<ProductSession | null> {
  if (!pending) {
    const started = epoch
    pending = (async () => {
      const response = await request('/session')
      if (started !== epoch) return current
      if ([401, 404].includes(response.status)) {
        current = null
        return null
      }
      const value = await json(response)
      return started === epoch ? remember(value) : current
    })().finally(() => {
      if (started === epoch) pending = null
    })
  }
  return pending
}
export async function loginProviders(): Promise<LoginProvider[]> {
  const value = await json(await request('/providers'))
  if (
    !Array.isArray(value.items) ||
    value.items.length > 100 ||
    value.items.some(
      (item: LoginProvider) => typeof item?.id !== 'string' || typeof item.name !== 'string',
    )
  )
    throw new Error('登录提供者响应无效')
  return value.items
}
export async function startEnterpriseLogin(
  returnTo: unknown,
  providerId?: string,
  invitation?: string,
): Promise<string> {
  if (invitation !== undefined && !/^[A-Za-z0-9_-]{43}$/.test(invitation))
    throw new Error('邀请无效，请重新打开管理员发送的链接')
  const path =
    invitation !== undefined
      ? '/invitation-authorization-sessions'
      : providerId
        ? `/providers/${encodeURIComponent(providerId)}/authorization-sessions`
        : '/authorization-sessions'
  const body =
    invitation !== undefined
      ? { invitation_token: invitation, return_to: safeReturnTo(returnTo) }
      : { return_to: safeReturnTo(returnTo) }
  const value = await json(
    await request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
  let target: URL
  try {
    target = new URL(value.authorize_url)
  } catch {
    throw new Error('登录授权地址无效')
  }
  if (
    target.protocol !== 'https:' ||
    target.port ||
    target.username ||
    target.password ||
    target.hash ||
    /[\p{Cc}\p{Cf}\p{Cs}\\]/u.test(value.authorize_url)
  )
    throw new Error('登录授权地址无效')
  return target.href
}
export async function finishEnterpriseLogin(query: string): Promise<string> {
  const parameters = new URLSearchParams(query)
  if (
    Array.from(parameters).length !== 2 ||
    parameters.getAll('state').length !== 1 ||
    parameters.getAll('code').length !== 1 ||
    !parameters.get('state') ||
    !parameters.get('code')
  )
    throw new Error('登录回调无效，请重新发起登录')
  const response = await request(`/callback?${parameters.toString()}`)
  remember(await json(response))
  try {
    return safeReturnTo(decodeURIComponent(response.headers.get('X-ORBIT-Return-To') ?? '/index'))
  } catch {
    return '/index'
  }
}
export async function logoutCookieSession(): Promise<void> {
  if (!current) return
  logoutKey ??= `session-logout-${crypto.randomUUID()}`
  const response = await request('/session', {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': current.csrf_token, 'Idempotency-Key': logoutKey },
  })
  if (response.status !== 401) await json(response)
  clearCookieSession()
}
