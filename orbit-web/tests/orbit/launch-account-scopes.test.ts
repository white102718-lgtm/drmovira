/** transport替身仅证明原合同/认证/未知写边界，不是实际范围或数据库验收。 */
import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import {
  launchAccountScopesApi as api,
  parseScopeSnapshot,
  parseScopeMembers,
  parseCandidatePage,
  checkScopeRequest,
} from '@/api/orbit/launch-account-scopes'
const auth = vi.hoisted(() => ({ headers: vi.fn(), credentials: vi.fn() }))
vi.mock('@/api/orbit/authentication', () => ({
  orbitAuthHeaders: auth.headers,
  orbitCredentials: auth.credentials,
}))
const fetcher = vi.fn(),
  id = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const time = '2026-11-08T00:00:00Z',
  context = { csrf_token: 'private-csrf-fixture', idempotency_key: 'same-frozen-intent-123' }
const filter = () => ({
  q: '',
  status: null,
  auth_status: null,
  operator_user_id: id(8),
  vendor_id: null,
})
const snapshot = () => ({
  id: id(1),
  count: 50000,
  scope_version: Number.MAX_SAFE_INTEGER,
  hash: 'X'.repeat(64),
  created_at: time,
})
const page = () => ({
  items: [{ account_id: id(2), external_id: '0' + '9'.repeat(63), name: '😀'.repeat(10000) }],
  next_cursor: 'opaque-token',
  data_as_of: time,
  scope_version: 2,
})
const response = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status })
beforeEach(() => {
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
  auth.headers.mockImplementation((v) => ({ ...v, Authorization: 'Bearer test-memory-only' }))
  auth.credentials.mockReturnValue('omit')
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
it('严格保留50000范围、安全版本、64字符hash与数字字符串前导零', () => {
  expect(parseScopeSnapshot(snapshot()).count).toBe(50000)
  expect(parseScopeMembers(page()).items[0].external_id).toHaveLength(64)
})
it.each([
  { ...snapshot(), extra: true },
  { ...snapshot(), count: -1 },
  { ...snapshot(), scope_version: Number.MAX_SAFE_INTEGER + 1 },
  { ...snapshot(), hash: 'x'.repeat(63) },
  { ...snapshot(), created_at: 'yesterday' },
  { ...snapshot(), id: id(1).replaceAll('-', '') },
])('拒绝快照非法字段 %#', (v) => {
  expect(() => parseScopeSnapshot(v)).toThrow()
})
it('成员严格字段/重复/上限/游标，不能将平台ID转数值', () => {
  const v = page()
  expect(() => parseScopeMembers({ ...v, items: [{ ...v.items[0], external_id: 123 }] })).toThrow()
  expect(() => parseScopeMembers({ ...v, items: [v.items[0], v.items[0]] })).toThrow()
  expect(() => parseScopeMembers({ ...v, items: Array(201).fill(v.items[0]) })).toThrow()
  expect(() => parseScopeMembers({ ...v, next_cursor: '' })).toThrow()
})
it('IDS与FILTER严格互斥、重复拒绝、50000合法而50001不截断', () => {
  const ids = Array.from({ length: 50000 }, (_, i) => id(i + 1))
  expect(
    checkScopeRequest({ mode: 'IDS', account_ids: ids, filter: null }).account_ids,
  ).toHaveLength(50000)
  for (const v of [
    { mode: 'IDS', account_ids: [], filter: null },
    { mode: 'IDS', account_ids: [id(1), id(1)], filter: null },
    { mode: 'IDS', account_ids: [...ids, id(50001)], filter: null },
    { mode: 'FILTER', account_ids: [id(1)], filter: filter() },
    { mode: 'FILTER', account_ids: [], filter: { ...filter(), exclude: [] } },
  ])
    expect(() => checkScopeRequest(v)).toThrow()
})
it('候选仅投影真实归属和状态，未知完整账户字段不冒充快照成员', () => {
  const v = {
    items: [
      {
        id: id(1),
        external_id: '0001',
        name: '账户',
        ownership: { owner_user_id: id(8), owner_team_id: id(9) },
        currency: 'USD',
        auth_status: 'UNKNOWN',
        account_status: 'UNKNOWN',
        spend: { amount: null },
      },
    ],
    next_cursor: null,
    data_as_of: time,
    scope_version: 1,
  }
  expect(parseCandidatePage(v).items[0].external_id).toBe('0001')
  expect(() =>
    parseCandidatePage({ ...v, items: [{ ...v.items[0], ownership: { owner_user_id: id(8) } }] }),
  ).toThrow()
})
it('POST只接受201，冻结key/csrf/body及memory认证不在URL、不带虚构CAS', async () => {
  fetcher.mockResolvedValue(response(snapshot(), 201))
  const body = { mode: 'FILTER' as const, account_ids: [] as [], filter: filter() }
  await api.create(body, context)
  const [url, init] = fetcher.mock.calls[0]
  expect(url).toMatch(/\/api\/v1\/scope-snapshots$/)
  expect(url).not.toContain(context.csrf_token)
  expect(init.headers['Idempotency-Key']).toBe(context.idempotency_key)
  expect(init.headers['If-Match']).toBeUndefined()
  expect(init.headers.Authorization).toBe('Bearer test-memory-only')
  expect(JSON.parse(init.body)).toEqual(body)
  expect(init.cache).toBe('no-store')
})
it.each([200, 202])('非原成功状态%d不能冒充冻结成功', async (status) => {
  fetcher.mockResolvedValue(response(snapshot(), status))
  await expect(
    api.create({ mode: 'IDS', account_ids: [id(1)], filter: null }, context),
  ).rejects.toMatchObject({ unknown_result: true })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it('网络未知重放只能使用调用方原key/body，SDK不自动重试', async () => {
  fetcher
    .mockRejectedValueOnce(new TypeError('offline'))
    .mockResolvedValueOnce(response(snapshot(), 201))
  const body = { mode: 'FILTER' as const, account_ids: [] as [], filter: filter() }
  await expect(api.create(body, context)).rejects.toMatchObject({ unknown_result: true })
  expect(fetcher).toHaveBeenCalledTimes(1)
  await api.create(body, context)
  expect(fetcher.mock.calls[0][1].body).toEqual(fetcher.mock.calls[1][1].body)
  expect(fetcher.mock.calls[0][1].headers).toEqual(fetcher.mock.calls[1][1].headers)
})
it.each([400, 502])('畸形/网关错误%d不能证明写入未受理', async (status) => {
  fetcher.mockResolvedValue(new Response('<html>gateway</html>', { status }))
  await expect(
    api.create({ mode: 'IDS', account_ids: [id(1)], filter: null }, context),
  ).rejects.toMatchObject({ unknown_result: true })
})
it('原错误体保留字段指针和nullable constraint；GET错误不标未知写', async () => {
  fetcher.mockResolvedValue(
    response(
      {
        code: 'SCOPE_REVOKED',
        message: '范围变化',
        field_errors: [
          {
            path: '/filter/operator_user_id',
            code: 'INVALID',
            message: '拥有者变化',
            constraint: null,
          },
        ],
        retryable: false,
        request_id: id(5),
      },
      409,
    ),
  )
  await expect(api.members(id(1), '', 50, null)).rejects.toMatchObject({
    status: 409,
    unknown_result: false,
    field_errors: [{ path: '/filter/operator_user_id', constraint: null }],
  })
})
it('Cookie会话改写csrf时禁止偷偷替换原写上下文', async () => {
  auth.headers.mockImplementation((v) => ({ ...v, 'X-CSRF-Token': 'changed' }))
  await expect(
    api.create({ mode: 'IDS', account_ids: [id(1)], filter: null }, context),
  ).rejects.toMatchObject({ code: 'SESSION_CONTEXT_CHANGED', unknown_result: false })
  expect(fetcher).not.toHaveBeenCalled()
})
it('成员分页保留原opaque游标/四档，非法page_size不发送', async () => {
  fetcher.mockImplementation(() => Promise.resolve(response(page())))
  for (const size of [20, 50, 100, 200]) await api.members(id(1), '前缀', size, 'signed+/=')
  expect(new URL('http://test' + fetcher.mock.calls[0][0]).searchParams.get('cursor')).toBe(
    'signed+/=',
  )
  expect(() => api.members(id(1), '', 51, null)).toThrow()
  expect(fetcher).toHaveBeenCalledTimes(4)
})
it('候选只发原筛选，不塞owner_team/exclusion/date/凭据参数', async () => {
  fetcher.mockResolvedValue(
    response({ items: [], next_cursor: null, data_as_of: time, scope_version: 1 }),
  )
  await api.candidates(filter(), 20, null)
  const url = String(fetcher.mock.calls[0][0])
  expect(url).toContain('operator_user_id=')
  for (const value of ['owner_team_id', 'exclude', 'token', 'date_from'])
    expect(url).not.toContain(value)
})
it('已取消请求不发网络；读取异常不会生成未知写结果', async () => {
  const c = new AbortController()
  c.abort()
  await expect(api.members(id(1), '', 50, null, c.signal)).rejects.toMatchObject({
    name: 'AbortError',
  })
  expect(fetcher).not.toHaveBeenCalled()
  fetcher.mockRejectedValue(new TypeError('network'))
  await expect(api.members(id(1), '', 50, null)).rejects.toMatchObject({ unknown_result: false })
})
