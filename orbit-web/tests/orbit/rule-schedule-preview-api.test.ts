/** 只读POST协议纯测试，fetch替身不代表真实调度、API授权或DST来源验收。 */
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import {
  parseSchedulePreviewRequest,
  parseSchedulePreview,
  ruleSchedulePreviewApi,
} from '@/api/orbit/rule-schedule-preview'
const auth = vi.hoisted(() => ({ token: 'Bearer actual', csrf: undefined as string | undefined }))
vi.mock('@/api/orbit/authentication', () => ({
  cookieCsrf: () => auth.csrf,
  orbitCredentials: () => 'omit',
  orbitAuthHeaders: (extra: HeadersInit = {}) => ({
    ...Object.fromEntries(new Headers(extra).entries()),
    Authorization: auth.token,
  }),
}))
const id = '00000000-0000-4000-8000-000000000001'
const schedule = () => ({
  frequency: 'INTERVAL',
  interval_minutes: 30,
  time_of_day: null,
  weekday: null,
  timezone: 'UTC',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
})
const body = () => ({ action: 'CREATE', rule_id: null, rule_revision: null, schedule: schedule() })
const value = () => ({
  reference_at: '2026-01-01T00:00:00.123456Z',
  timezone: 'UTC',
  slots: [{ local_time: '2026-01-01T00:30:00+00:00', utc_time: '2026-01-01T00:30:00.000000Z' }],
  skipped_local_times: [],
})
const token = { csrf_token: 'current-session-csrf-token' }
const fetcher = vi.fn(),
  response = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status })
beforeEach(() => {
  fetcher.mockReset()
  vi.stubGlobal('fetch', fetcher)
  vi.stubEnv('VITE_APP_BASE_API', '/dev-api')
  auth.token = 'Bearer actual'
  auth.csrf = undefined
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
  vi.useRealTimers()
})
it('POST四键原Schedule7和当前CSRF，无IfMatch/幂等头或写入资格', async () => {
  fetcher.mockResolvedValue(response(value()))
  const input = body()
  expect(await ruleSchedulePreviewApi.preview(input as never, token)).toEqual(value())
  expect(fetcher.mock.calls[0][0]).toBe('/dev-api/api/v1/rules/editor-schedule-preview')
  const options = fetcher.mock.calls[0][1]
  expect(options.method).toBe('POST')
  const headers = new Headers(options.headers)
  expect(headers.get('X-CSRF-Token')).toBe(token.csrf_token)
  expect(headers.has('If-Match')).toBe(false)
  expect(headers.has('Idempotency-Key')).toBe(false)
  expect(JSON.parse(options.body)).toEqual(input)
  expect(Object.keys(JSON.parse(options.body).schedule)).toHaveLength(7)
  expect(input).toEqual(body())
})
it('严格CREATE两null、UPDATE当前rev、Schedule互斥全部required', () => {
  expect(
    parseSchedulePreviewRequest({ ...body(), action: 'UPDATE', rule_id: id, rule_revision: 3 }),
  ).toMatchObject({ rule_revision: 3 })
  for (const change of [
    { rule_id: id },
    { rule_revision: 1 },
    { extra: true },
    { action: ['CREATE'] },
    { action: 'UPDATE', rule_id: id, rule_revision: null },
    { action: 'UPDATE', rule_id: id, rule_revision: 0 },
    { action: 'UPDATE', rule_id: id, rule_revision: true },
  ])
    expect(() => parseSchedulePreviewRequest({ ...body(), ...change })).toThrow()
  for (const change of [{ weekday: 1 }, { timezone: '' }, { end_date: '2027-01-02' }])
    expect(() =>
      parseSchedulePreviewRequest({ ...body(), schedule: { ...schedule(), ...change } }),
    ).toThrow()
  const missing = body() as any
  delete missing.schedule.weekday
  expect(() => parseSchedulePreviewRequest(missing)).toThrow()
})
it('零slots真实空，不默认补五条；原UTC6精度保留', () => {
  expect(parseSchedulePreview({ ...value(), slots: [] })).toEqual({ ...value(), slots: [] })
  expect(parseSchedulePreview(value()).reference_at).toContain('.123456Z')
})
it('DST缺失墙钟单列，local_time偏移与UTC/真实zone相符', () => {
  const result = {
    reference_at: '2026-03-08T00:00:00.000001Z',
    timezone: 'America/New_York',
    slots: [{ local_time: '2026-03-09T02:30:00-04:00', utc_time: '2026-03-09T06:30:00.000000Z' }],
    skipped_local_times: [
      { local_time: '2026-03-08T02:30:00', reason_code: 'DST_NONEXISTENT_LOCAL_TIME' },
    ],
  }
  expect(parseSchedulePreview(result)).toEqual(result)
  expect(() =>
    parseSchedulePreview({
      ...result,
      slots: [{ local_time: '2026-03-09T01:30:00-05:00', utc_time: '2026-03-09T06:30:00.000000Z' }],
    }),
  ).toThrow()
})
it('多于5、重复/倒序/早于参考、缺偏移/错误日期/UTC3均拒绝', () => {
  for (const v of [
    { ...value(), extra: 1 },
    { ...value(), reference_at: '2026-01-01T00:00:00.123Z' },
    { ...value(), slots: Array(6).fill(value().slots[0]) },
    { ...value(), slots: [value().slots[0], value().slots[0]] },
    {
      ...value(),
      slots: [{ local_time: '2025-12-31T23:30:00+00:00', utc_time: '2025-12-31T23:30:00.000000Z' }],
    },
    {
      ...value(),
      slots: [{ local_time: '2026-01-01T00:30:00', utc_time: value().slots[0].utc_time }],
    },
    {
      ...value(),
      skipped_local_times: [
        { local_time: '2026-02-30T02:00:00', reason_code: 'DST_NONEXISTENT_LOCAL_TIME' },
      ],
    },
  ])
    expect(() => parseSchedulePreview(v)).toThrow()
})
it('错误DST reason/重复墙钟/多于366不伪正常结果', () => {
  const skip = { local_time: '2026-03-08T02:30:00', reason_code: 'DST_NONEXISTENT_LOCAL_TIME' }
  for (const items of [[{ ...skip, reason_code: 'UNKNOWN' }], [skip, skip], Array(367).fill(skip)])
    expect(() => parseSchedulePreview({ ...value(), skipped_local_times: items })).toThrow()
})
it.each([401, 403, 409, 503])('真实%d code/path显式保留，不返回空预览', async (status) => {
  fetcher.mockResolvedValue(
    response(
      {
        code: 'PREVIEW_SOURCE',
        message: '当前来源不可用',
        field_errors: [
          { path: '/schedule/timezone', code: 'BAD', message: '时区不支持', constraint: null },
        ],
        retryable: true,
        request_id: id,
      },
      status,
    ),
  )
  await expect(ruleSchedulePreviewApi.preview(body() as never, token)).rejects.toMatchObject({
    status,
    code: 'PREVIEW_SOURCE',
    field_errors: [{ path: '/schedule/timezone' }],
    unknown_result: false,
  })
})
it('auth额外写头字段、坏csrf、Cookie代际漂移均不外发', async () => {
  await expect(
    ruleSchedulePreviewApi.preview(body() as never, { ...token, if_match: '"3"' } as never),
  ).rejects.toMatchObject({ status: 403 })
  auth.csrf = 'new-session-token'
  await expect(ruleSchedulePreviewApi.preview(body() as never, token)).rejects.toMatchObject({
    code: 'SESSION_CONTEXT_CHANGED',
  })
  expect(fetcher).not.toHaveBeenCalled()
})
it('当前认证变化丢弃迟到响应，不泄漏另一身份结果', async () => {
  fetcher.mockImplementation(async () => {
    auth.token = 'Bearer changed'
    return response(value())
  })
  await expect(ruleSchedulePreviewApi.preview(body() as never, token)).rejects.toMatchObject({
    code: 'SESSION_CONTEXT_CHANGED',
  })
})
it('取消/超时/坏响应均只读错误，不标写入未知', async () => {
  const controller = new AbortController()
  controller.abort()
  await expect(
    ruleSchedulePreviewApi.preview(body() as never, token, controller.signal),
  ).rejects.toMatchObject({ name: 'AbortError' })
  expect(fetcher).not.toHaveBeenCalled()
  fetcher.mockResolvedValue(response({ ...value(), timezone: 'Asia/Shanghai' }))
  await expect(ruleSchedulePreviewApi.preview(body() as never, token)).rejects.toMatchObject({
    code: 'INVALID_RESPONSE',
    unknown_result: false,
  })
})
