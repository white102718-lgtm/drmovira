import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  clearCookieSession,
  cookieSessionActive,
  finishEnterpriseLogin,
  logoutCookieSession,
  orbitAuthHeaders,
  orbitCredentials,
  probeCookieSession,
  refreshCookieCsrfForRecovery,
  safeReturnTo,
  startEnterpriseLogin,
} from '@/api/orbit/authentication'
import { captureAuthEntry, takeAuthEntry } from '@/api/orbit/auth-entry'

vi.mock('@/utils/auth', () => ({ getToken: () => 'native-fixture-token' }))
const session = {
  user: { id: 'fixture-user' },
  scope_version: 1,
  menu_codes: [],
  permission_codes: [],
  csrf_token: 'fixture-cookie-csrf-token',
  expires_at: '2026-11-09T00:00:00Z',
}
afterEach(() => {
  clearCookieSession()
  takeAuthEntry()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('Cookie登录入口和会话边界', () => {
  it('已验证恢复仅刷新Cookie运输CSRF，保留原权限和请求CAS', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(session)))
    vi.stubGlobal('fetch', fetch)
    const original = await probeCookieSession()
    const renewed = 'renewed-cookie-csrf-token'
    const write = vi.spyOn(Storage.prototype, 'setItem')
    refreshCookieCsrfForRecovery(renewed)
    expect(orbitAuthHeaders({ 'X-CSRF-Token': 'old', 'If-Match': '"7"' })).toEqual({
      'X-CSRF-Token': renewed,
      'If-Match': '"7"',
    })
    expect(original).toEqual(session)
    expect(cookieSessionActive()).toBe(true)
    expect(fetch).toHaveBeenCalledOnce()
    expect(write).not.toHaveBeenCalled()
  })
  it('JWT模式刷新不创建Cookie身份或覆盖Bearer', () => {
    refreshCookieCsrfForRecovery('renewed-cookie-csrf-token')
    expect(cookieSessionActive()).toBe(false)
    expect(orbitCredentials()).toBe('omit')
    expect(orbitAuthHeaders()).toEqual({ Authorization: 'Bearer native-fixture-token' })
  })
  it.each(['short', ' a-valid-cookie-csrf-token', 'a'.repeat(256), 'a'.repeat(16) + '\n'])(
    '拒绝非法恢复运输校验且不创建身份',
    (value) => {
      expect(() => refreshCookieCsrfForRecovery(value)).toThrow()
      expect(cookieSessionActive()).toBe(false)
    },
  )
  it.each([
    '//evil.example',
    '/%2f%2fevil.example',
    '/%255c%255cevil.example',
    'https://evil.example',
    '/\nredirect',
    '/%00',
    '/%xx',
    ['/index'],
  ])('站外、嵌套编码、控制字符或多值返回地址安全回退：%s', (value) => {
    expect(safeReturnTo(value)).toBe('/index')
  })
  it('保留合法站内筛选地址', () => {
    expect(safeReturnTo('/orbit/system/users?q=%E4%BA%BA%E5%91%98')).toBe(
      '/orbit/system/users?q=%E4%BA%BA%E5%91%98',
    )
  })
  it('入口先清除邀请片段，只能从内存提取一次，不写浏览器存储', () => {
    const write = vi.spyOn(Storage.prototype, 'setItem')
    const history = { state: { existing: true }, replaceState: vi.fn() }
    captureAuthEntry(
      { pathname: '/invite', search: '', hash: '#' + 'i'.repeat(43) } as Location,
      history as unknown as History,
    )
    expect(history.replaceState).toHaveBeenCalledWith(null, '', '/invite')
    expect(takeAuthEntry()).toEqual({ invitation: 'i'.repeat(43) })
    expect(takeAuthEntry()).toBeNull()
    expect(write).not.toHaveBeenCalled()
  })
  it('非法邀请和回调入口不把凭据保留在路由状态', () => {
    const history = { state: null, replaceState: vi.fn() }
    captureAuthEntry(
      { pathname: '/invite', search: '?token=bad', hash: '#bad' } as Location,
      history as unknown as History,
    )
    expect(takeAuthEntry()).toBeNull()
    captureAuthEntry(
      { pathname: '/auth/callback', search: '?state=s&code=c', hash: '' } as Location,
      history as unknown as History,
    )
    expect(history.replaceState).toHaveBeenLastCalledWith(null, '', '/auth/callback')
    expect(takeAuthEntry()).toEqual({ callback: 'state=s&code=c' })
  })
  it('并发探测共用一次服务端验证，Cookie模式不发送旧Bearer，写请求使用Cookie CSRF', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(session)))
    vi.stubGlobal('fetch', fetch)
    await Promise.all([probeCookieSession(), probeCookieSession()])
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(cookieSessionActive()).toBe(true)
    expect(orbitCredentials()).toBe('same-origin')
    expect(
      orbitAuthHeaders({ authorization: 'Bearer old', 'X-CSRF-Token': 'old', 'If-Match': '"7"' }),
    ).toEqual({ 'X-CSRF-Token': session.csrf_token, 'If-Match': '"7"' })
    const [, init] = fetch.mock.calls[0]
    expect(init.cache).toBe('no-store')
    expect(init.credentials).toBe('same-origin')
    expect(init.referrerPolicy).toBe('no-referrer')
  })
  it('无Cookie时保留原Bearer独立请求模式', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })))
    expect(await probeCookieSession()).toBeNull()
    expect(orbitCredentials()).toBe('omit')
    expect(orbitAuthHeaders().Authorization).toBe('Bearer native-fixture-token')
  })
  it('退出清理后迟到探测响应不能恢复前端登录态', async () => {
    let finish!: (value: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise((resolve) => {
            finish = resolve
          }),
      ),
    )
    const pending = probeCookieSession()
    clearCookieSession()
    finish(new Response(JSON.stringify(session)))
    expect(await pending).toBeNull()
    expect(cookieSessionActive()).toBe(false)
  })
  it('邀请凭据只放正文，重定向授权地址须为HTTPS', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ authorize_url: 'https://idp.fixture.example/authorize?state=s' }),
        ),
      )
    vi.stubGlobal('fetch', fetch)
    const token = 'i'.repeat(43)
    await startEnterpriseLogin('/index', undefined, token)
    const [url, init] = fetch.mock.calls[0]
    expect(url).toMatch(/invitation-authorization-sessions$/)
    expect(url).not.toContain(token)
    expect(JSON.parse(init.body)).toEqual({ invitation_token: token, return_to: '/index' })
    fetch.mockResolvedValue(new Response(JSON.stringify({ authorize_url: 'javascript:alert(1)' })))
    await expect(startEnterpriseLogin('/index')).rejects.toThrow('登录授权地址无效')
  })
  it('回调拒绝重复参数，合法回调验证Cookie会话并拒绝站外返回地址', async () => {
    const fetch = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify(session), {
          headers: { 'X-ORBIT-Return-To': encodeURIComponent('//evil.example') },
        }),
    )
    vi.stubGlobal('fetch', fetch)
    await expect(finishEnterpriseLogin('state=s&state=other&code=c')).rejects.toThrow(
      '登录回调无效',
    )
    expect(fetch).not.toHaveBeenCalled()
    expect(await finishEnterpriseLogin('state=s&code=c')).toBe('/index')
    expect(cookieSessionActive()).toBe(true)
  })
  it('退出网络失败保留同键重试，不携带凭据正文', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session)))
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await probeCookieSession()
    await expect(logoutCookieSession()).rejects.toThrow('连接中断')
    await logoutCookieSession()
    const first = fetch.mock.calls[1][1],
      second = fetch.mock.calls[2][1]
    expect(first.headers['Idempotency-Key']).toBe(second.headers['Idempotency-Key'])
    expect(first.body).toBeUndefined()
    expect(cookieSessionActive()).toBe(false)
  })
})
