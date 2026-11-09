import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { parseTask, parseTaskNode, tasksApi, TaskApiError } from '@/api/orbit/tasks'
import { nodePage, taskFixture, taskNode, taskPage, taskUuid } from './tasks-fixtures'
const fetcher = vi.fn()
const response = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
beforeEach(() => {
  vi.stubGlobal('fetch', fetcher)
  fetcher.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
describe('Task原合同只读SDK', () => {
  it('只GET稀疏列表，node_count不从空nodes推断，编码游标和受控AbortSignal', async () => {
    const expected = taskPage()
    fetcher.mockResolvedValue(response(expected))
    const controller = new AbortController()
    const page = await tasksApi.list(
      { page_size: 20, status: 'UNKNOWN', cursor: 'opaque+/==', operator_user_id: taskUuid(80000) },
      controller.signal,
    )
    expect(page.items[0].node_count).toBe(275)
    expect(page.items[0].nodes).toEqual([])
    const [url, options] = fetcher.mock.calls[0]
    const query = new URL(String(url), 'http://localhost').searchParams
    expect(query.get('cursor')).toBe('opaque+/==')
    expect(query.get('status')).toBe('UNKNOWN')
    expect(query.get('operator_user_id')).toBe(taskUuid(80000))
    expect(options.method).toBe('GET')
    expect(options.signal).toBeInstanceOf(AbortSignal)
    expect(options.signal.aborted).toBe(false)
    expect(options.body).toBeUndefined()
    expect(options.cache).toBe('no-store')
  })
  it('详情保留首200、100父ID、超JS安全位数平台ID及可选字段', async () => {
    const expected = taskFixture()
    expected.nodes[0].parent_ids = Array.from({ length: 100 }, (_, i) => taskUuid(1000 + i))
    expected.execution_mode = 'ADSPOWER_UI'
    expected.nodes[0].no_op = false
    fetcher.mockResolvedValue(response(expected))
    const task = await tasksApi.get(expected.id)
    expect(task.nodes).toHaveLength(200)
    expect(task.nodes[0].parent_ids).toHaveLength(100)
    expect(task.nodes[0].external_id).toBe('1234567890123456789012345678901234567890')
    expect(task.nodes[0].no_op).toBe(false)
    expect(String(fetcher.mock.calls[0][0])).toContain(`/tasks/${expected.id}`)
  })
  it.each([20, 50, 100, 200] as const)(
    '节点page_size=%s与NFC前缀查询，保持完整返回字段',
    async (size) => {
      fetcher.mockResolvedValue(response(nodePage()))
      await tasksApi.nodes(taskUuid(10000), { page_size: size, q: ' e\u0301/ ', status: 'UNKNOWN' })
      const params = new URL(String(fetcher.mock.calls[0][0]), 'http://localhost').searchParams
      expect(params.get('page_size')).toBe(String(size))
      expect(params.get('q')).toBe('é/')
      expect(params.has('date_from')).toBe(false)
    },
  )
  it('未定义列表q/日期/channel或节点条件不静默伪查询', async () => {
    await expect(tasksApi.list({ page_size: 20, q: 'x' } as never)).rejects.toMatchObject({
      code: 'INVALID_QUERY',
    })
    await expect(
      tasksApi.nodes(taskUuid(10000), { page_size: 20, channel_id: 'x' } as never),
    ).rejects.toMatchObject({ code: 'INVALID_QUERY' })
    await expect(
      tasksApi.nodes(taskUuid(10000), { page_size: 20, q: '🙂'.repeat(101) }),
    ).rejects.toMatchObject({ status: 422 })
    expect(fetcher).not.toHaveBeenCalled()
  })
  it.each([401, 403, 404, 409, 410, 429, 503])(
    'HTTP%s保留受控状态和码，不能返回假Task成功',
    async (status) => {
      fetcher.mockResolvedValue(
        response(
          {
            code: status === 409 ? 'TASK_SNAPSHOT_CHANGED' : 'REQUEST_FAILED',
            message: '当前读取不可用',
            field_errors: [],
            retryable: false,
            request_id: taskUuid(60000),
          },
          status,
        ),
      )
      await expect(tasksApi.get(taskUuid(10000))).rejects.toMatchObject({
        status,
        message: '当前读取不可用',
      })
    },
  )
  it('网络与取消区分；取消不伪报网络失败且已取消不发请求', async () => {
    fetcher.mockRejectedValue(new TypeError('offline'))
    await expect(tasksApi.get(taskUuid(10000))).rejects.toMatchObject({
      status: 0,
      code: 'NETWORK_UNAVAILABLE',
    })
    const controller = new AbortController()
    controller.abort()
    fetcher.mockClear()
    await expect(tasksApi.get(taskUuid(10000), controller.signal)).rejects.toMatchObject({
      name: 'AbortError',
    })
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('读取10秒超时可重读，调用方取消仍中止真实fetch', async () => {
    vi.useFakeTimers()
    fetcher.mockImplementation(
      (_url, options) =>
        new Promise((_resolve, reject) => {
          options.signal.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          )
        }),
    )
    const timeout = tasksApi.get(taskUuid(10000))
    const timeoutAssertion = expect(timeout).rejects.toMatchObject({
      status: 504,
      code: 'READ_TIMEOUT',
    })
    await vi.advanceTimersByTimeAsync(10000)
    await timeoutAssertion
    expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true)
    const controller = new AbortController()
    const canceled = tasksApi.get(taskUuid(10000), controller.signal)
    const cancelAssertion = expect(canceled).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort()
    await cancelAssertion
    expect(fetcher.mock.calls[1][1].signal.aborted).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('JSON读取期间取消仍为AbortError', async () => {
    const controller = new AbortController()
    fetcher.mockResolvedValue({
      ok: true,
      json: async () => {
        controller.abort()
        throw new DOMException('aborted', 'AbortError')
      },
    })
    await expect(tasksApi.get(taskUuid(10000), controller.signal)).rejects.toMatchObject({
      name: 'AbortError',
    })
  })
  it.each([
    'numericId',
    'unsafeRevision',
    'extra',
    'missing',
    'over200',
    'invalidParent',
    'numericExternal',
    'badState',
  ])('拒绝不符合原schema的响应：%s', async (mutation) => {
    const value: any = taskFixture()
    if (mutation === 'numericId') value.id = 123
    if (mutation === 'unsafeRevision') value.revision = 9007199254740992
    if (mutation === 'extra') value.fake_success = true
    if (mutation === 'missing') delete value.node_count
    if (mutation === 'over200') value.nodes.push(taskNode(201))
    if (mutation === 'invalidParent') value.nodes[0].parent_ids = ['not-a-uuid']
    if (mutation === 'numericExternal') value.nodes[0].external_id = 123456789
    if (mutation === 'badState') value.nodes[0].state = 'FAILED_RETRYABLE'
    fetcher.mockResolvedValue(response(value))
    await expect(tasksApi.get(taskUuid(10000))).rejects.toBeInstanceOf(TaskApiError)
  })
  it('原可选值缺省保持未知，不补execution_mode/no_op或删跨页父ID', () => {
    const node = taskNode()
    expect(parseTaskNode(node).execution_mode).toBeUndefined()
    expect(parseTaskNode(node).no_op).toBeUndefined()
    const task = taskFixture()
    expect(parseTask(task).latest_event_id).toBeNull()
  })
})
