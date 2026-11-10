/** 传输替身验证原只读合同，不是指标权威来源或生产连接器验收。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  metricProfilesApi as api,
  metricProfileQuery,
  parseMetricProfile,
  parseMetricProfilePage,
} from '@/api/orbit/metric-profiles'
const auth = vi.hoisted(() => ({ headers: vi.fn(), credentials: vi.fn() }))
vi.mock('@/api/orbit/authentication', () => ({
  orbitAuthHeaders: auth.headers,
  orbitCredentials: auth.credentials,
}))
const fetcher = vi.fn(),
  id = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const profile = () => ({
  id: id(1),
  version: '版本😀'.repeat(20) + '1234',
  source: 'FIXTURE',
  register_action_type: null,
  purchase_action_type: 'purchase',
  value_action_type: null,
  attribution_windows: ['7d_click', '1d_view'],
  action_report_time: 'conversion',
  timezone_policy: 'ACCOUNT_LOCAL',
  breakdown: 'TOTAL',
  maturity_days: 90,
  verified: false,
})
const page = () => ({
  items: [profile()],
  next_cursor: null,
  data_as_of: '2026-11-08T00:00:00.123Z',
  scope_version: Number.MAX_SAFE_INTEGER,
})
const query = () => ({ q: '', metric_profile_id: null, cursor: null, page_size: 50 })
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
beforeEach(() => {
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
  auth.headers.mockImplementation((v) => ({ ...v, Authorization: 'Bearer in-memory-test' }))
  auth.credentials.mockReturnValue('omit')
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('保留全部原12字段、nullable事件、窗口数组和boolean，不伪造Ownership', () => {
  const value = profile()
  expect(parseMetricProfile(value)).toEqual(value)
  expect(Object.keys(parseMetricProfile(value))).toHaveLength(12)
  expect(parseMetricProfilePage(page()).scope_version).toBe(Number.MAX_SAFE_INTEGER)
})
it.each([
  { extra: true },
  { ownership: { owner_user_id: id(8) } },
  { register_action_type: '' },
  { purchase_action_type: 1 },
  { value_action_type: false },
  { source: 'GOOGLE' },
  { maturity_days: 0 },
  { maturity_days: 91 },
  { maturity_days: 1.5 },
  { maturity_days: true },
  { verified: 'true' },
  { timezone_policy: 'UTC' },
  { breakdown: 'COUNTRY' },
  { version: '😀'.repeat(65) },
  { action_report_time: '' },
  { attribution_windows: [] },
  { attribution_windows: Array(11).fill('window') },
  { attribution_windows: [''] },
  { id: id(1).replaceAll('-', '') },
])('严格拒绝配置非法值 %#', (patch) => {
  expect(() => parseMetricProfile({ ...profile(), ...patch })).toThrow()
})
it('事件与版本字符串64码点完整，窗口最多10而不截断', () => {
  const value = {
    ...profile(),
    version: '😀'.repeat(64),
    register_action_type: 'x'.repeat(64),
    attribution_windows: Array(10).fill('x'.repeat(64)),
  }
  expect(parseMetricProfile(value)).toEqual(value)
  expect(() => parseMetricProfile({ ...value, register_action_type: 'x'.repeat(65) })).toThrow()
})
it('严格Page4字段、200上限、空页与短页nextcursor，不从行数猜尾页', () => {
  expect(parseMetricProfilePage({ ...page(), items: [] })).toMatchObject({ items: [] })
  expect(parseMetricProfilePage({ ...page(), next_cursor: 'opaque+/=' })).toMatchObject({
    next_cursor: 'opaque+/=',
  })
  expect(
    parseMetricProfilePage({
      ...page(),
      items: Array.from({ length: 200 }, (_, i) => ({ ...profile(), id: id(i + 1) })),
    }).items,
  ).toHaveLength(200)
  for (const v of [
    { ...page(), items: Array(201).fill(profile()) },
    { ...page(), items: [profile(), profile()] },
    { ...page(), next_cursor: '' },
    { ...page(), scope_version: Number.MAX_SAFE_INTEGER + 1 },
    { ...page(), data_as_of: '2026-02-30T00:00:00Z' },
    { ...page(), extra: true },
  ])
    expect(() => parseMetricProfilePage(v)).toThrow()
})
it('仅四参数、q和profile完整UUID大小写归一、原cursor不解码', () => {
  const value = metricProfileQuery({
    q: id(10).toUpperCase(),
    metric_profile_id: id(11),
    cursor: 'signed+/=',
    page_size: 20,
  })
  expect(value.get('q')).toBe(id(10))
  expect(value.get('metric_profile_id')).toBe(id(11))
  expect(value.get('cursor')).toBe('signed+/=')
  expect([...value.keys()].sort()).toEqual(['cursor', 'metric_profile_id', 'page_size', 'q'])
})
it.each([
  { q: '名称搜索' },
  { q: '00123' },
  { metric_profile_id: 'invalid' },
  { page_size: 51 },
  { page_size: 201 },
  { page_size: true },
  { cursor: '' },
  { status: 'ENABLED' },
  { date_from: '2026-11-01' },
  { operator_user_id: id(1) },
  { channel_id: id(1) },
  { entity_type: 'AD' },
])('未定义筛选或错误参数不发送 %#', (patch) => {
  expect(() => metricProfileQuery({ ...query(), ...patch } as never)).toThrow()
})
it('GET使用当前内存认证/no-store和原endpoint，凭据不在URL或body', async () => {
  fetcher.mockResolvedValue(response(page()))
  await api.list(query())
  const [url, init] = fetcher.mock.calls[0]
  expect(url).toMatch(/\/api\/v1\/metric-profiles\?page_size=50$/)
  expect(url).not.toContain('in-memory-test')
  expect(init).toMatchObject({ method: 'GET', cache: 'no-store', credentials: 'omit' })
  expect(init.headers.Authorization).toBe('Bearer in-memory-test')
  expect(init.body).toBeUndefined()
  expect(init.headers['Idempotency-Key']).toBeUndefined()
})
it('四档分页实际序列化，Cookie凭据模式原样沿用', async () => {
  auth.credentials.mockReturnValue('same-origin')
  auth.headers.mockImplementation((v) => ({ ...v, 'X-CSRF-Token': 'cookie-memory-only' }))
  fetcher.mockImplementation(() => Promise.resolve(response(page())))
  for (const size of [20, 50, 100, 200]) await api.list({ ...query(), page_size: size })
  expect(fetcher.mock.calls.map((c) => String(c[0]))).toEqual(
    [20, 50, 100, 200].map((n) => expect.stringContaining('page_size=' + n)),
  )
  expect(fetcher.mock.calls[0][1].credentials).toBe('same-origin')
})
it.each([201, 202])('不以非原200状态%d当列表成功', async (status) => {
  fetcher.mockResolvedValue(response(page(), status))
  await expect(api.list(query())).rejects.toMatchObject({ status, code: 'INVALID_RESPONSE' })
})
it.each([403, 409, 503])('原错误%d保留field_errors/nullable约束和request_id', async (status) => {
  fetcher.mockResolvedValue(
    response(
      {
        code: 'PROFILE_CHANGED',
        message: '当前配置已变化',
        field_errors: [{ path: '/q', code: 'INVALID', message: '完整ID', constraint: null }],
        retryable: false,
        request_id: id(8),
      },
      status,
    ),
  )
  await expect(api.list(query())).rejects.toMatchObject({
    status,
    code: 'PROFILE_CHANGED',
    request_id: id(8),
    field_errors: [{ path: '/q', constraint: null }],
  })
})
it('网关正文不回显，网络失败不自动重试', async () => {
  fetcher.mockResolvedValueOnce(new Response('<html>sensitive gateway</html>', { status: 502 }))
  await expect(api.list(query())).rejects.toMatchObject({ status: 502, code: 'INVALID_RESPONSE' })
  fetcher.mockRejectedValueOnce(new TypeError('network'))
  await expect(api.list(query())).rejects.toMatchObject({ status: 0, code: 'NETWORK_UNAVAILABLE' })
  expect(fetcher).toHaveBeenCalledTimes(2)
})
it('外部Abort在发送前不发请求，发送后实际传递到fetch signal', async () => {
  const before = new AbortController()
  before.abort()
  await expect(api.list(query(), before.signal)).rejects.toMatchObject({ name: 'AbortError' })
  expect(fetcher).not.toHaveBeenCalled()
  fetcher.mockImplementation(
    (_url, init) =>
      new Promise((_resolve, reject) =>
        init.signal.addEventListener('abort', () =>
          reject(new DOMException('abort', 'AbortError')),
        ),
      ),
  )
  const current = new AbortController(),
    pending = api.list(query(), current.signal)
  current.abort()
  await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true)
})

it('历史查询候选使用独立路径，不改变投放可用目录', async () => {
  const controller = new AbortController()
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        items: [],
        next_cursor: null,
        data_as_of: '2026-11-10T00:00:00.000Z',
        scope_version: 1,
      }),
      { status: 200 },
    ),
  )
  await api.history(
    { q: '', metric_profile_id: null, cursor: null, page_size: 50 },
    controller.signal,
  )
  expect(String(fetcher.mock.calls[0][0])).toContain('/metric-profiles/history-candidates?')
})

it('历史候选允许同ID的不同版本，拒绝同一版本重复', () => {
  const first = { ...profile(), version: 'old.v1' },
    second = { ...profile(), version: 'new.v2' }
  expect(parseMetricProfilePage({ ...page(), items: [first, second] }, true).items).toHaveLength(2)
  expect(() => parseMetricProfilePage({ ...page(), items: [first, second] })).toThrow()
  expect(() => parseMetricProfilePage({ ...page(), items: [first, first] }, true)).toThrow()
})
