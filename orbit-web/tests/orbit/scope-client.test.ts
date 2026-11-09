import { afterEach, expect, it, vi } from 'vitest'
import {
  createScope,
  getScopeMembers,
  getScopeCsrf,
  ScopeApiError,
  type ScopeRequest,
} from '@/api/orbit/scopes'
vi.mock('@/utils/auth', () => ({ getToken: () => 'fixture-session' }))
afterEach(() => vi.unstubAllGlobals())
it('只读账户范围从Python capabilities取得CSRF，不借导入或旧Java csrf接口', async () => {
  const fetch = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        csrf_token: 'read-only-csrf',
        max_members: 50000,
        max_plan_accounts: 500,
      }),
    ),
  )
  vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal
  await expect(getScopeCsrf(signal)).resolves.toMatchObject({
    max_members: 50000,
    max_plan_accounts: 500,
  })
  expect(fetch.mock.calls[0][0]).toMatch(/\/api\/v1\/scope-snapshots\/capabilities$/)
  expect(fetch.mock.calls[0][1].signal).toBe(signal)
})
it('范围重试保留调用方幂等键/CSRF并透传取消信号，不缓存或发送Cookie', async () => {
  const fetch = vi
    .fn()
    .mockImplementation(() => Promise.resolve(new Response('{}', { status: 201 })))
  vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal
  const value: ScopeRequest = { mode: 'IDS', account_ids: ['fixture'], filter: null }
  await createScope(value, 'fixed-key-16-chars', 'fixture-csrf-token', signal)
  await createScope(value, 'fixed-key-16-chars', 'fixture-csrf-token', signal)
  for (const [, options] of fetch.mock.calls) {
    expect(options.headers['Idempotency-Key']).toBe('fixed-key-16-chars')
    expect(options.headers['X-CSRF-Token']).toBe('fixture-csrf-token')
    expect(options.signal).toBe(signal)
    expect(options.cache).toBe('no-store')
    expect(options.credentials).toBe('omit')
    expect(JSON.parse(options.body)).toEqual(value)
  }
})
it('成员查询只发送合同参数并编码游标，长外部ID保持字符串', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ items: [{ external_id: '12345678901234567890123456789012' }] }),
      ),
    )
  vi.stubGlobal('fetch', fetch)
  const page = await getScopeMembers('snapshot', 'a&b', 20, 'a+/=')
  const url = new URL(fetch.mock.calls[0][0], 'http://localhost')
  expect(Object.fromEntries(url.searchParams)).toEqual({
    q: 'a&b',
    page_size: '20',
    cursor: 'a+/=',
  })
  expect(page.items[0].external_id).toBe('12345678901234567890123456789012')
})
it('权限版本冲突保留状态码且不回显网关HTML或请求凭据', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response('<html>private diagnostic</html>', { status: 409 })),
  )
  await expect(getScopeCsrf()).rejects.toMatchObject({ status: 409, code: 'REQUEST_FAILED' })
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 'SCOPE_CHANGED', message: 'private diagnostic' }), {
        status: 409,
      }),
    ),
  )
  await expect(getScopeCsrf()).rejects.toThrow(ScopeApiError)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })))
  await expect(getScopeCsrf()).rejects.toThrow('登录已失效')
})
