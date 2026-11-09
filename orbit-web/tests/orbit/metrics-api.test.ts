/** 严格SDK纯测试；fetch替身不是原指标API或发行验收。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  metricDatasets,
  metricValueKeys,
  metricsApi,
  MetricsError,
  parseMetricQuery,
  parseMetrics,
  parseMetricRow,
  parseMetricTotal,
  parseMetricValues,
} from '@/api/orbit/metrics'
const auth = vi.hoisted(() => ({ headers: vi.fn(), credentials: vi.fn() }))
vi.mock('@/api/orbit/authentication', () => ({
  orbitAuthHeaders: auth.headers,
  orbitCredentials: auth.credentials,
}))
const id = (n = 1) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const query = () => ({
  date_from: '2026-01-01',
  date_to: '2026-01-02',
  dataset: 'AD' as const,
  metric_profile_id: id(),
  scope_snapshot_id: null,
  channel_id: null,
  operator_user_id: null,
  q: '',
  sort: 'spend' as const,
  direction: 'DESC' as const,
  cursor: null,
  page_size: 20 as const,
  granularity: 'SUMMARY' as const,
})
const values = () => Object.fromEntries(metricValueKeys.map((k) => [k, null]))
const row = () => ({
  tenant_id: id(),
  owner_team_id: null,
  operator_user_id: null,
  entity_id: '001234',
  name: '原名',
  channel_id: null,
  product_name_snapshot: null,
  currency: 'USD',
  metric_profile_id: id(),
  business_date: null,
  account_count: 1,
  ad_count: 2,
  values: values(),
  quality: 'UNKNOWN',
  coverage: '0',
})
const total = () => ({
  tenant_id: id(),
  currency: 'USD',
  metric_profile_id: id(),
  values: values(),
  account_count: 1,
  ad_count: 2,
  missing_count: 2,
  coverage: '0',
})
const result = () => ({
  items: [row()],
  next_cursor: 'opaque+/=',
  scope_version: Number.MAX_SAFE_INTEGER,
  snapshot_id: id(2),
  data_as_of: '2026-11-08T00:00:00.123Z',
  missing_count: 2,
  query_snapshot_id: id(3),
  totals: [total()],
})
const frozen = () => ({
  csrf_token: 'current_csrf_token_1234',
  idempotency_key: 'current_intent_key_1234',
})
const fetcher = vi.fn()
beforeEach(() => {
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
  auth.headers.mockImplementation((v) => ({ ...v, Authorization: 'Bearer memory-test' }))
  auth.credentials.mockReturnValue('omit')
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('精确13请求字段与8/15/12/8响应结构，null保留不补零', () => {
  expect(Object.keys(parseMetricQuery(query()))).toHaveLength(13)
  const value = parseMetrics(result())
  expect(Object.keys(value)).toHaveLength(8)
  expect(Object.keys(value.items[0])).toHaveLength(15)
  expect(Object.keys(value.items[0].values)).toHaveLength(12)
  expect(Object.keys(value.totals[0])).toHaveLength(8)
  expect(value.items[0].entity_id).toBe('001234')
  expect(value.items[0].values.spend).toBeNull()
  expect(value.next_cursor).toBe('opaque+/=')
})
it.each(metricDatasets)('原dataset枚举%s保留，未替服务端虚构映射', (dataset) =>
  expect(parseMetricQuery({ ...query(), dataset }).dataset).toBe(dataset),
)
it.each(Object.keys(query()))('缺少请求必需字段%s严格拒绝', (key) => {
  const value: Record<string, unknown> = query()
  delete value[key]
  expect(() => parseMetricQuery(value)).toThrow()
})
it.each([
  { date_from: '2026-02-30' },
  { date_to: '2025-12-31' },
  { date_to: '2026-04-04' },
  { dataset: 'CREATIVE' },
  { metric_profile_id: 'bad' },
  { scope_snapshot_id: '' },
  { operator_user_id: 1 },
  { channel_id: '' },
  { q: '😀'.repeat(101) },
  { sort: 'ctr' },
  { direction: 'desc' },
  { page_size: 25 },
  { cursor: '' },
  { granularity: 'UTC' },
  { unknown: true },
])('非法请求边界 %#', (patch) => expect(() => parseMetricQuery({ ...query(), ...patch })).toThrow())
it('日期93含首尾合法，未来日期留服务端逐账户核验', () => {
  expect(parseMetricQuery({ ...query(), date_to: '2026-04-03' }).date_to).toBe('2026-04-03')
  expect(
    parseMetricQuery({ ...query(), date_from: '2099-01-01', date_to: '2099-01-01' }),
  ).toBeTruthy()
})
it.each([0, 1.2, true, '01', '1e2', '1.0000001', '-1', '1'.repeat(29), NaN])(
  '金融字段拒绝浮点或非规范值 %#',
  (value) => expect(() => parseMetricValues({ ...values(), spend: value })).toThrow(),
)
it('28字符六位字符串原样保留，不转Number', () => {
  const amount = '123456789012345678901.123456'
  expect(parseMetricValues({ ...values(), spend: amount }).spend).toBe(amount)
})
it.each([
  { coverage: 0.5 },
  { quality: 'INVALID' },
  { business_date: '2026-02-30' },
  { name: '😀'.repeat(256) },
  { product_name_snapshot: '' },
  { account_count: 2147483648 },
  { values: { ...values(), extra: null } },
  { tenant_id: 'bad' },
  { extra: true },
])('非法行严格拒绝 %#', (patch) => expect(() => parseMetricRow({ ...row(), ...patch })).toThrow())
it.each([{ missing_count: -1 }, { currency: 'US' }, { coverage: '0.1234567' }, { extra: true }])(
  '非法total严格拒绝 %#',
  (patch) => expect(() => parseMetricTotal({ ...total(), ...patch })).toThrow(),
)
it.each([
  { items: Array(201).fill(row()) },
  { totals: Array(1001).fill(total()) },
  { scope_version: 0 },
  { scope_version: 9007199254740992 },
  { data_as_of: '2026-02-30T00:00:00Z' },
  { missing_count: -1 },
  { next_cursor: '' },
  { extra: true },
])('非法顶层严格拒绝 %#', (patch) =>
  expect(() => parseMetrics({ ...result(), ...patch })).toThrow(),
)
it('短页含nextcursor和空页真实totals均保留', () => {
  expect(parseMetrics({ ...result(), items: [] }).totals).toHaveLength(1)
  expect(parseMetrics(result()).next_cursor).not.toBeNull()
})
it('精确POST及冻结header，cookie/bearer在header而非URL，无自动重试', async () => {
  fetcher.mockResolvedValue(new Response(JSON.stringify(result()), { status: 200 }))
  const body = query()
  await metricsApi.query(body, frozen())
  expect(fetcher).toHaveBeenCalledTimes(1)
  const [url, init] = fetcher.mock.calls[0]
  expect(url).toMatch(/\/api\/v1\/metrics\/query$/)
  expect(url).not.toContain('memory-test')
  expect(init.method).toBe('POST')
  expect(init.credentials).toBe('omit')
  expect(JSON.parse(init.body)).toEqual(body)
  expect(init.headers).toMatchObject({
    'X-CSRF-Token': frozen().csrf_token,
    'Idempotency-Key': frozen().idempotency_key,
  })
  expect(init.headers['If-Match']).toBeUndefined()
})
it.each([400, 401, 403, 404, 409, 422, 429, 503])('原Error五字段HTTP%s保留', async (status) => {
  const value = {
    code: 'SOURCE_UNAVAILABLE',
    message: '来源尚未就绪',
    field_errors: [
      {
        path: '/metric_profile_id',
        code: 'UNVERIFIED',
        message: '配置待核验',
        constraint: 'registered',
      },
    ],
    retryable: true,
    request_id: id(8),
  }
  fetcher.mockResolvedValue(new Response(JSON.stringify(value), { status }))
  try {
    await metricsApi.query(query(), frozen())
    expect.unreachable()
  } catch (error) {
    expect(error).toMatchObject({ status, ...value, unknown_result: false, source: 'server' })
  }
  expect(fetcher).toHaveBeenCalledTimes(1)
})
it.each([200, 400, 502])('坏body HTTP%s保持未知写结果且不泄HTML', async (status) => {
  fetcher.mockResolvedValue(new Response('<private-upstream-body>', { status }))
  await expect(metricsApi.query(query(), frozen())).rejects.toMatchObject({
    status,
    unknown_result: true,
    source: 'local',
    request_id: null,
  })
  await expect(metricsApi.query(query(), frozen())).rejects.not.toThrow('private-upstream-body')
})
it('网络失败不偷偷换幂等键，显式同意图重试保留body/header', async () => {
  fetcher.mockRejectedValue(new Error('secret transport'))
  for (let i = 0; i < 2; i++)
    await expect(metricsApi.query(query(), frozen())).rejects.toMatchObject({
      unknown_result: true,
      code: 'NETWORK_UNAVAILABLE',
    })
  expect(fetcher.mock.calls[0][1].body).toBe(fetcher.mock.calls[1][1].body)
  expect(fetcher.mock.calls[0][1].headers).toEqual(fetcher.mock.calls[1][1].headers)
})
it('冻结csrf与当前会话变化时零发送', async () => {
  auth.headers.mockImplementation((v) => ({ ...v, 'X-CSRF-Token': 'changed_current_csrf' }))
  await expect(metricsApi.query(query(), frozen())).rejects.toMatchObject({
    code: 'CSRF_CONTEXT_CHANGED',
  })
  expect(fetcher).not.toHaveBeenCalled()
})
it('非法冻结key或预取消信号零发送', async () => {
  await expect(
    metricsApi.query(query(), {
      ...frozen(),
      idempotency_key: 1234567890123456 as unknown as string,
    }),
  ).rejects.toBeInstanceOf(MetricsError)
  const controller = new AbortController()
  controller.abort()
  await expect(metricsApi.query(query(), frozen(), controller.signal)).rejects.toMatchObject({
    name: 'AbortError',
  })
  expect(fetcher).not.toHaveBeenCalled()
})
it('200行/1000汇总上界与长Unicode字段完整，不因短页推断尾页', () => {
  const value = parseMetrics({
    ...result(),
    items: Array.from({ length: 200 }, (_, i) => ({
      ...row(),
      entity_id: String(i),
      name: '😀'.repeat(255),
    })),
    totals: Array(1000).fill(total()),
  })
  expect(value.items).toHaveLength(200)
  expect(value.totals).toHaveLength(1000)
  expect([...value.items[0].name]).toHaveLength(255)
})
it('成功状态不是200或字段错误缺code时不误当合法业务结果', async () => {
  fetcher.mockResolvedValueOnce(
    new Response(JSON.stringify({ id: id(), state: 'QUEUED' }), { status: 202 }),
  )
  await expect(metricsApi.query(query(), frozen())).rejects.toMatchObject({
    status: 202,
    unknown_result: true,
  })
  fetcher.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        code: 'BAD',
        message: '错误',
        request_id: id(),
        retryable: false,
        field_errors: [{ path: '/q', message: '字段', constraint: 'max100' }],
      }),
      { status: 422 },
    ),
  )
  await expect(metricsApi.query(query(), frozen())).rejects.toMatchObject({
    status: 422,
    source: 'local',
    field_errors: [],
    unknown_result: true,
  })
})
it('发送后外部abort不接受迟到响应', async () => {
  let resolve!: (value: Response) => void
  fetcher.mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  const controller = new AbortController(),
    request = metricsApi.query(query(), frozen(), controller.signal)
  controller.abort()
  resolve(new Response(JSON.stringify(result()), { status: 200 }))
  await expect(request).rejects.toMatchObject({ name: 'AbortError' })
})
it('当前查询上下文严格GET一个csrf字段，不用其他菜单或URL凭据', async () => {
  fetcher.mockResolvedValue(
    new Response(JSON.stringify({ csrf_token: 'current_server_csrf_12345' }), { status: 200 }),
  )
  await expect(metricsApi.capabilities()).resolves.toEqual({
    csrf_token: 'current_server_csrf_12345',
  })
  const [url, init] = fetcher.mock.calls[0]
  expect(url).toMatch(/\/api\/v1\/metrics\/capabilities$/)
  expect(url).not.toContain('memory-test')
  expect(init.method).toBe('GET')
  expect(init.body).toBeUndefined()
  expect(init.headers['Idempotency-Key']).toBeUndefined()
})
it.each([
  {},
  { csrf_token: '' },
  { csrf_token: 1 },
  { csrf_token: 'x'.repeat(256) },
  { csrf_token: 'valid_csrf_context_12345', extra: true },
])('上下文坏结构不伪造CSRF %#', async (value) => {
  fetcher.mockResolvedValue(new Response(JSON.stringify(value), { status: 200 }))
  await expect(metricsApi.capabilities()).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
    unknown_result: false,
  })
})
it('上下文403保留Error并非写入未知，坏响应不回显原文', async () => {
  fetcher.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        code: 'PERMISSION_DENIED',
        message: '无权查看',
        field_errors: [],
        retryable: false,
        request_id: id(),
      }),
      { status: 403 },
    ),
  )
  await expect(metricsApi.capabilities()).rejects.toMatchObject({
    status: 403,
    code: 'PERMISSION_DENIED',
    request_id: id(),
    unknown_result: false,
    source: 'server',
  })
  fetcher.mockResolvedValueOnce(new Response('secret_gateway_body', { status: 502 }))
  await expect(metricsApi.capabilities()).rejects.not.toThrow('secret_gateway_body')
})
