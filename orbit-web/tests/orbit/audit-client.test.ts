import { afterEach, expect, it, vi } from 'vitest'
import { AuditApiError, listAuditEvents } from '@/api/orbit/audit'
vi.mock('@/utils/auth', () => ({ getToken: () => 'fixture-session' }))
afterEach(() => vi.unstubAllGlobals())
const filter = { q: '', operator_user_id: '', date_from: '', date_to: '' }
it('审计查询编码合同字段与游标，独立鉴权并禁止缓存和Cookie', async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ items: [{ request_id: 'fixture-id' }], next_cursor: null })),
    )
  vi.stubGlobal('fetch', fetch)
  const signal = new AbortController().signal
  const page = await listAuditEvents(
    {
      ...filter,
      q: 'a&b',
      operator_user_id: 'user-id',
      date_from: '2026-11-01',
      date_to: '2026-11-06',
    },
    20,
    'a+/=',
    signal,
  )
  const url = new URL(fetch.mock.calls[0][0], 'http://localhost')
  expect(Object.fromEntries(url.searchParams)).toEqual({
    q: 'a&b',
    operator_user_id: 'user-id',
    date_from: '2026-11-01',
    date_to: '2026-11-06',
    page_size: '20',
    cursor: 'a+/=',
  })
  expect(fetch.mock.calls[0][1]).toMatchObject({
    cache: 'no-store',
    credentials: 'omit',
    signal,
    headers: { Authorization: 'Bearer fixture-session' },
  })
  expect(page.items[0].request_id).toBe('fixture-id')
})
it('审计错误保留状态和追踪UUID，不回显网关HTML或私有诊断', async () => {
  for (const status of [400, 401, 403, 409, 422, 503]) {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>private diagnostic</html>', { status })),
    )
    await expect(listAuditEvents(filter, 50, null)).rejects.toMatchObject({
      status,
      code: 'REQUEST_FAILED',
    })
    await expect(listAuditEvents(filter, 50, null)).rejects.not.toThrow('private diagnostic')
  }
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockImplementation(
        async () =>
          new Response(
            JSON.stringify({ code: 'AUDIT_HISTORY_INCOMPLETE', message: 'private diagnostic' }),
            { status: 503, headers: { 'X-Request-ID': 'fixture-request' } },
          ),
      ),
  )
  await expect(listAuditEvents(filter, 50, null)).rejects.toBeInstanceOf(AuditApiError)
  await expect(listAuditEvents(filter, 50, null)).rejects.toMatchObject({
    code: 'AUDIT_HISTORY_INCOMPLETE',
    requestId: 'fixture-request',
  })
  await expect(listAuditEvents(filter, 50, null)).rejects.toThrow('记录未被隐藏或补造')
})
it('取消请求保持AbortError语义，空筛选不伪造租户或操作者', async () => {
  const fetch = vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError'))
  vi.stubGlobal('fetch', fetch)
  await expect(listAuditEvents(filter, 50, null)).rejects.toMatchObject({ name: 'AbortError' })
  expect(
    Object.fromEntries(new URL(fetch.mock.calls[0][0], 'http://localhost').searchParams),
  ).toEqual({ page_size: '50' })
})
