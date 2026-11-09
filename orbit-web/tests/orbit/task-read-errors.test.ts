/** HTTP transport替身合同测试，不代表真实HTTP/SSE验收。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { parseTaskErrorBody, taskHttpError, tasksApi, TaskApiError } from '@/api/orbit/tasks'
import { loadTaskEventSnapshot, observeTaskEvents } from '@/api/orbit/task-events'
import { taskUuid } from './tasks-fixtures'
const fetcher = vi.fn()
const body = () => ({
  code: 'FIELD_INVALID',
  message: '读取条件不符',
  field_errors: [{ path: '/q', code: 'LENGTH', message: '字段过长', constraint: '最多100码点' }],
  retryable: true,
  request_id: taskUuid(9000),
})
const reply = (value: unknown, status = 422) => new Response(JSON.stringify(value), { status })
beforeEach(() => {
  vi.stubGlobal('fetch', fetcher)
  fetcher.mockReset()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
it('严格保留原Error五字段与FieldError四字段，Unicode按码点且返回副本', () => {
  const value = body()
  value.field_errors[0].constraint = ''
  const parsed = parseTaskErrorBody(value)
  expect(parsed).toEqual(value)
  value.field_errors[0].path = '/changed'
  expect(parsed.field_errors[0].path).toBe('/q')
  expect(parseTaskErrorBody({ ...body(), message: '🙂'.repeat(1000) }).message).toHaveLength(2000)
})
it.each([
  { extra: true },
  { request_id: null },
  { request_id: 'not-uuid' },
  { retryable: 1 },
  { code: '' },
  { code: 'a'.repeat(65) },
  { message: '🙂'.repeat(1001) },
  { field_errors: Array.from({ length: 101 }, () => body().field_errors[0]) },
  { field_errors: [{ ...body().field_errors[0], constraint: null }] },
  { field_errors: [{ ...body().field_errors[0], extra: true }] },
  { field_errors: [{ ...body().field_errors[0], path: '' }] },
  { field_errors: [{ ...body().field_errors[0], path: 'a'.repeat(256) }] },
  { field_errors: [{ ...body().field_errors[0], constraint: 'a'.repeat(501) }] },
  { field_errors: [{ ...body().field_errors[0], code: '' }] },
  { field_errors: [{ ...body().field_errors[0], code: 'a'.repeat(65) }] },
  { field_errors: [{ ...body().field_errors[0], message: '' }] },
  { field_errors: [{ ...body().field_errors[0], message: '🙂'.repeat(1001) }] },
  { field_errors: [{ path: '/q', code: 'INVALID', message: '缺约束' }] },
  { field_errors: null },
  { message: '' },
  { message: 123 },
])('拒绝非原Error字段边界 %#', (change) => {
  expect(() => parseTaskErrorBody({ ...body(), ...change })).toThrow(TaskApiError)
})
it.each(['code', 'message', 'field_errors', 'retryable', 'request_id'])(
  '原字段%s不可缺失',
  (key) => {
    const value: Record<string, unknown> = body()
    delete value[key]
    expect(() => parseTaskErrorBody(value)).toThrow()
  },
)
it.each([401, 403, 404, 409, 422, 503])('GET HTTP%s保留全部原错误信息且仍只GET', async (status) => {
  fetcher.mockResolvedValue(reply(body(), status))
  await expect(tasksApi.get(taskUuid(10000))).rejects.toMatchObject({
    ...body(),
    status,
    source: 'server',
  })
  expect(fetcher.mock.calls[0][1].method).toBe('GET')
  expect(String(fetcher.mock.calls[0][0])).not.toMatch(/token|csrf/i)
})
it.each([401, 403, 404, 502])('坏JSON HTTP%s保留状态且不泄露正文', async (status) => {
  fetcher.mockResolvedValue(new Response('<html>private upstream body</html>', { status }))
  await expect(tasksApi.get(taskUuid(10000))).rejects.toMatchObject({
    status,
    source: 'local',
    request_id: null,
    field_errors: [],
    retryable: false,
    code: 'INVALID_ERROR_RESPONSE',
  })
  expect(taskHttpError(status, { message: 'private upstream body' }).message).not.toContain(
    'private',
  )
})
it('SSE快照HTTP错误保留原五字段，100条最大字段错误不受8KiB帧限截断', async () => {
  const value = {
    ...body(),
    field_errors: Array.from({ length: 100 }, () => ({
      path: '🙂'.repeat(255),
      code: 'c'.repeat(64),
      message: '🙂'.repeat(1000),
      constraint: '\u0000'.repeat(500),
    })),
  }
  fetcher.mockResolvedValue(reply(value))
  await expect(
    loadTaskEventSnapshot(taskUuid(10000), new AbortController().signal),
  ).rejects.toMatchObject({ ...value, status: 422, source: 'server' })
})
it.each([401, 403, 404])('SSE坏授权HTTP%s终止、保留状态且无重连', async (status) => {
  fetcher.mockResolvedValue(new Response('<html>private</html>', { status }))
  const onState = vi.fn(),
    onRevoked = vi.fn()
  const observer = observeTaskEvents({
    taskId: taskUuid(10000),
    onSnapshot: vi.fn(),
    onEvent: vi.fn(),
    onState,
    onRevoked,
  })
  await observer.done
  expect(onRevoked).toHaveBeenCalledOnce()
  expect(onState).toHaveBeenLastCalledWith(
    'revoked',
    expect.objectContaining({ status, source: 'local', code: 'INVALID_ERROR_RESPONSE' }),
  )
  expect(fetcher).toHaveBeenCalledOnce()
})
it('原三参本地错误无虚构服务端请求编号或重试结论', () => {
  expect(new TaskApiError(0, 'NETWORK_UNAVAILABLE', '网络中断')).toMatchObject({
    source: 'local',
    request_id: null,
    field_errors: [],
    retryable: false,
  })
})
it('SSE合法服务端403原错误五字段在终止回调中完整保留', async () => {
  fetcher.mockResolvedValue(reply(body(), 403))
  const onState = vi.fn(),
    onRevoked = vi.fn()
  const observer = observeTaskEvents({
    taskId: taskUuid(10000),
    onSnapshot: vi.fn(),
    onEvent: vi.fn(),
    onState,
    onRevoked,
  })
  await observer.done
  expect(onState).toHaveBeenLastCalledWith(
    'revoked',
    expect.objectContaining({ ...body(), status: 403, source: 'server' }),
  )
  expect(onRevoked).toHaveBeenCalledOnce()
})
