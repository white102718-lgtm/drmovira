/** 规则筛选候选协议纯测试，不计真实SQL/HTTP来源或数据范围验收。 */
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import {
  scopeOptionsParameters,
  parseRuleScopeOptionPage,
  ruleScopeOptionsApi,
} from '@/api/orbit/rule-scope-options'
const auth = vi.hoisted(() => ({ token: 'Bearer actual' }))
vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => 'omit',
  orbitAuthHeaders: (extra: HeadersInit = {}) => ({
    ...Object.fromEntries(new Headers(extra).entries()),
    Authorization: auth.token,
  }),
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const operator = (n = 1) => ({
  id: id(n),
  name: '真实姓名',
  team_id: id(3),
  team_name: '真实团队',
  active: false,
})
const vendor = (n = 4) => ({
  id: id(n),
  name: '资料名称不是代称',
  alias: null,
  availability: 'UNAVAILABLE',
})
const page = (items: unknown[]) => ({
  items,
  next_cursor: null,
  data_as_of: '2026-11-09T01:00:00.123456Z',
  scope_version: 7,
})
const query = () => ({
  kind: 'OPERATOR',
  action: 'CREATE',
  owner_user_id: id(2),
  owner_team_id: id(3),
})
const fetcher = vi.fn(),
  response = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status })
beforeEach(() => {
  fetcher.mockReset()
  auth.token = 'Bearer actual'
  vi.stubGlobal('fetch', fetcher)
  vi.stubEnv('VITE_APP_BASE_API', '/dev-api')
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.useRealTimers()
})
it('严格GET规则专属接口+owner_team_id，无其它模块或写头', async () => {
  fetcher.mockResolvedValue(response(page([operator()])))
  expect(await ruleScopeOptionsApi.options(query() as never)).toEqual(page([operator()]))
  const url = new URL(fetcher.mock.calls[0][0], 'https://fixture.local')
  expect(url.pathname).toBe('/dev-api/api/v1/rules/editor-scope-options')
  expect(Object.fromEntries(url.searchParams)).toEqual(query())
  const options = fetcher.mock.calls[0][1]
  expect(options).toMatchObject({ method: 'GET', cache: 'no-store' })
  expect(options.body).toBeUndefined()
  expect(new Headers(options.headers).has('If-Match')).toBe(false)
  expect(new Headers(options.headers).has('Idempotency-Key')).toBe(false)
})
it('CREATE不带rule_id/UPDATE必需，禁止team_id别名和其它账户过滤参数', () => {
  for (const value of [
    { ...query(), rule_id: null },
    { ...query(), rule_id: id() },
    { ...query(), action: 'UPDATE' },
    { ...query(), team_id: id(3) },
    { ...query(), status: 'ACTIVE' },
    { ...query(), vendor_id: id(4) },
    { ...query(), kind: ['OPERATOR'] },
    { ...query(), owner_team_id: 'not-uuid' },
  ])
    expect(() => scopeOptionsParameters(value)).toThrow()
  expect(
    scopeOptionsParameters({ ...query(), action: 'UPDATE', rule_id: id() }).get('rule_id'),
  ).toBe(id())
})
it('候选q独立NFC100、字面前缀/完整UUID，不改变调用方', () => {
  const source = { ...query(), q: '  ' + 'e\u0301'.repeat(100) + '  ' }
  expect(scopeOptionsParameters(source).get('q')).toBe('é'.repeat(100))
  expect(source.q).toContain('e\u0301')
  for (const q of [' ', 'é'.repeat(101), 'x\n', '\ud800'])
    expect(() => scopeOptionsParameters({ ...query(), q })).toThrow()
  expect(scopeOptionsParameters({ ...query(), q: '' }).get('q')).toBe('')
  expect(scopeOptionsParameters({ ...query(), q: id(9) }).get('q')).toBe(id(9))
})
it('四档size和opaque cursor严格边界', () => {
  for (const page_size of [20, 50, 100, 200])
    expect(
      scopeOptionsParameters({ ...query(), page_size, cursor: 'signed-opaque' }).get('page_size'),
    ).toBe(String(page_size))
  for (const value of [
    { page_size: 21 },
    { page_size: '50' },
    { cursor: '' },
    { cursor: 'x'.repeat(2049) },
    { cursor: 'x\0' },
  ])
    expect(() => scopeOptionsParameters({ ...query(), ...value })).toThrow()
})
it('Operator5/Vendor4真实历史状态/null分别保存，不把name当alias', () => {
  expect(parseRuleScopeOptionPage('OPERATOR', page([operator()]))).toEqual(page([operator()]))
  const result = parseRuleScopeOptionPage('VENDOR', page([vendor()]))
  expect(result.items[0].alias).toBeNull()
  expect(result.items[0].name).toBe('资料名称不是代称')
  expect(result.items[0].availability).toBe('UNAVAILABLE')
})
it('坏type/多字段/错kind/假名称/重复ID不能凑成功页', () => {
  for (const row of [
    { ...operator(), active: 1 },
    { ...operator(), id: 7 },
    { ...operator(), extra: true },
    { ...operator(), team_name: null },
  ])
    expect(() => parseRuleScopeOptionPage('OPERATOR', page([row]))).toThrow()
  for (const row of [
    { ...vendor(), alias: 4 },
    { ...vendor(), alias: 'x'.repeat(31) },
    { ...vendor(), availability: ['AVAILABLE'] },
    { ...vendor(), name: '' },
  ])
    expect(() => parseRuleScopeOptionPage('VENDOR', page([row]))).toThrow()
  expect(() => parseRuleScopeOptionPage('VENDOR', page([operator()]))).toThrow()
  expect(() => parseRuleScopeOptionPage('OPERATOR', page([operator(), operator()]))).toThrow()
})
it('Page4/200/实际请求size/UTC与scope version有界，不用空吞坏页', async () => {
  for (const v of [
    { ...page([]), extra: 1 },
    { ...page([]), data_as_of: '2026-02-30T00:00:00Z' },
    { ...page([]), scope_version: 0 },
    { ...page([]), next_cursor: '' },
    { ...page([]), items: Array(201).fill(operator()) },
  ])
    expect(() => parseRuleScopeOptionPage('OPERATOR', v)).toThrow()
  fetcher.mockResolvedValue(response(page(Array.from({ length: 21 }, (_, n) => operator(n + 10)))))
  await expect(
    ruleScopeOptionsApi.options({ ...query(), page_size: 20 } as never),
  ).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
})
it.each([401, 403, 409, 503])('真实%d错误与pointer保留，不伪空', async (status) => {
  fetcher.mockResolvedValue(
    response(
      {
        code: 'RULE_SCOPE_CHANGED',
        message: '当前来源变化',
        field_errors: [
          { path: '/owner_team_id', code: 'CHANGED', message: '范围变化', constraint: null },
        ],
        retryable: true,
        request_id: id(10),
      },
      status,
    ),
  )
  await expect(ruleScopeOptionsApi.options(query() as never)).rejects.toMatchObject({
    status,
    code: 'RULE_SCOPE_CHANGED',
    field_errors: [{ path: '/owner_team_id' }],
    unknown_result: false,
  })
})
it('认证迟到/提前取消不混当前身份，未知网络只读可重试不自动重发', async () => {
  const controller = new AbortController()
  controller.abort()
  await expect(
    ruleScopeOptionsApi.options(query() as never, controller.signal),
  ).rejects.toMatchObject({ name: 'AbortError' })
  expect(fetcher).not.toHaveBeenCalled()
  fetcher.mockImplementation(async () => {
    auth.token = 'Bearer other'
    return response(page([operator()]))
  })
  await expect(ruleScopeOptionsApi.options(query() as never)).rejects.toMatchObject({
    code: 'SESSION_CONTEXT_CHANGED',
  })
  fetcher.mockRejectedValue(new Error('disconnected'))
  await expect(ruleScopeOptionsApi.options(query() as never)).rejects.toMatchObject({
    code: 'NETWORK_UNAVAILABLE',
    unknown_result: false,
  })
  expect(fetcher).toHaveBeenCalledTimes(2)
})
it('发出后调用方修改kind/size不改变已冻结GET解析合同', async () => {
  const mutable = { ...query(), page_size: 20 }
  fetcher.mockImplementation(async () => {
    mutable.kind = 'VENDOR'
    mutable.page_size = 200
    return response(page([operator()]))
  })
  expect((await ruleScopeOptionsApi.options(mutable as never)).items[0]).toEqual(operator())
})

it.each([401, 403, 409])('已收到%d的坏正文仍保留授权/漂移状态，不输出原正文', async (status) => {
  for (const raw of [
    '<html>private proxy error</html>',
    '{"code":',
    new Uint8Array([0xff]),
    'x'.repeat(2 * 1024 * 1024 + 1),
  ]) {
    fetcher.mockResolvedValue(new Response(raw, { status }))
    await expect(ruleScopeOptionsApi.options(query() as never)).rejects.toMatchObject({
      status,
      code: 'INVALID_RESPONSE',
      message: '规则筛选候选来源响应未能确认',
      unknown_result: false,
    })
  }
})
it('200坏正文仍是502，未收到响应的网络失败不冒充撤权', async () => {
  fetcher.mockResolvedValue(new Response('<html>bad</html>', { status: 200 }))
  await expect(ruleScopeOptionsApi.options(query() as never)).rejects.toMatchObject({ status: 502 })
  fetcher.mockRejectedValue(new Error('offline'))
  await expect(ruleScopeOptionsApi.options(query() as never)).rejects.toMatchObject({
    status: 0,
    code: 'NETWORK_UNAVAILABLE',
  })
})
