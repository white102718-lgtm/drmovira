/** transport替身纯测：不是真实SSE/权限/平台验收，不修改原Task页面。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  loadTaskEventSnapshot,
  observeTaskEvents,
  parseTaskEvent,
  TaskSseDecoder,
  type TaskEvent,
  type TaskEventFrame,
} from '@/api/orbit/task-events'
import { taskFixture, taskUuid } from './tasks-fixtures'
const encoder = new TextEncoder()
const fetcher = vi.fn()
function event(sequence = 101): TaskEvent {
  return {
    event_id: taskUuid(50000 + sequence),
    sequence,
    schema_version: 1,
    task_id: taskUuid(10000),
    task_revision: 3,
    node_id: taskUuid(30000),
    state: 'RUNNING',
    occurred_at: '2026-11-08T00:01:02.123Z',
    request_id: taskUuid(60000),
  }
}
const frame = (value = event()) => `id: ${value.event_id}\ndata: ${JSON.stringify(value)}\n\n`
function snapshot(checkpoint = 'opaque.snapshot.MAC') {
  return new Response(
    JSON.stringify({
      ...taskFixture(taskUuid(10000), 1),
      revision: 2,
      latest_event_id: taskUuid(49000),
    }),
    {
      headers: { 'Content-Type': 'application/json', 'X-Task-Event-Checkpoint': checkpoint },
    },
  )
}
function stream(text: string, open = false) {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        if (text) controller.enqueue(encoder.encode(text))
        if (!open) controller.close()
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } },
  )
}
const failure = (status: number, code: string) =>
  new Response(
    JSON.stringify({
      code,
      message: 'fixture',
      field_errors: [],
      retryable: false,
      request_id: taskUuid(60000),
    }),
    { status },
  )
const flush = async () => {
  for (let i = 0; i < 35; i++) await Promise.resolve()
}
let observer: ReturnType<typeof observeTaskEvents> | undefined
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', fetcher)
  fetcher.mockReset()
})
afterEach(async () => {
  observer?.stop()
  await observer?.done.catch(() => {})
  observer = undefined
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('严格有界TaskEvent增量解码', () => {
  it('每个UTF8字节与CRLF任意分片、多帧、注释心跳保持完整Unicode', () => {
    const received: TaskEventFrame[] = []
    const decoder = new TaskSseDecoder((value) => received.push(value))
    const original = { ...event(), state: '中文🙂' }
    const bytes = encoder.encode(
      `: keepalive\r\n\r\n${frame(original).replaceAll('\n', '\r\n')}${frame(event(102))}`,
    )
    for (const byte of bytes) decoder.feed(new Uint8Array([byte]))
    decoder.finish()
    expect(received).toEqual([
      { kind: 'event', event: original },
      { kind: 'event', event: event(102) },
    ])
  })
  it('标准多行data仅在空行结束时交付，CR单独换行也支持', () => {
    const received: TaskEventFrame[] = []
    const decoder = new TaskSseDecoder((value) => received.push(value))
    const value = event()
    const json = JSON.stringify(value).replace(',"sequence"', ',\n"sequence"')
    decoder.feed(
      encoder.encode(
        `id: ${value.event_id}\r${json
          .split('\n')
          .map((part) => `data: ${part}`)
          .join('\r')}\r`,
      ),
    )
    expect(received).toEqual([])
    decoder.feed(encoder.encode('\r'))
    expect(received).toEqual([{ kind: 'event', event: value }])
  })
  it('observer撤权帧严格仅code，无虚构TaskEvent/id/sequence', () => {
    const received: TaskEventFrame[] = []
    const decoder = new TaskSseDecoder((value) => received.push(value))
    decoder.feed(encoder.encode('event: SCOPE_REVOKED\ndata: {"code":"SCOPE_REVOKED"}\n\n'))
    expect(received).toEqual([{ kind: 'revoked' }])
  })
  it.each([
    'event: OTHER\ndata: {}\n\n',
    'event: SCOPE_REVOKED\ndata: {"code":"SCOPE_REVOKED","sequence":1}\n\n',
    `id: ${taskUuid(1)}\nevent: SCOPE_REVOKED\ndata: {"code":"SCOPE_REVOKED"}\n\n`,
    `id: ${taskUuid(1)}\n${frame()}`,
    'retry: 100\n\n',
    'id: 12\n\n',
    'data: {broken}\n\n',
  ])('拒绝未知/重复/不完整控制字段：%s', (text) => {
    expect(() => new TaskSseDecoder(() => {}).feed(encoder.encode(text))).toThrow()
  })
  it('拒绝id/data错配、无id、非法UTF8、帧过大及EOF半帧，不交付未完成事件', () => {
    for (const text of [
      frame().replace(event().event_id, taskUuid(2)),
      `data: ${JSON.stringify(event())}\n\n`,
      `data: ${'x'.repeat(8193)}`,
    ])
      expect(() => new TaskSseDecoder(() => {}).feed(encoder.encode(text))).toThrow()
    expect(() => new TaskSseDecoder(() => {}).feed(new Uint8Array([0xff]))).toThrow()
    const decoder = new TaskSseDecoder(() => {
      throw new Error('不应交付')
    })
    decoder.feed(encoder.encode(frame().slice(0, -1)))
    expect(() => decoder.finish()).toThrow(/中断/)
  })
  it.each([
    'extra',
    'missing',
    'version',
    'sequence',
    'revision',
    'node',
    'task',
    'request',
    'state',
    'date',
  ])('原九字段schema严格校验：%s', (type) => {
    const value: Record<string, unknown> = { ...event() }
    if (type === 'extra') value.token = '不允许'
    if (type === 'missing') delete value.node_id
    if (type === 'version') value.schema_version = 2
    if (type === 'sequence') value.sequence = Number.MAX_SAFE_INTEGER + 1
    if (type === 'revision') value.task_revision = 0
    if (type === 'node') value.node_id = 123
    if (type === 'task') value.task_id = taskUuid(1).replaceAll('-', '')
    if (type === 'request') value.request_id = null
    if (type === 'state') value.state = '🙂'.repeat(41)
    if (type === 'date') value.occurred_at = '2026-02-30T00:00:00Z'
    expect(() => parseTaskEvent(value)).toThrow()
  })
  it('原state为1..40字符串而非Task枚举；不误拒合法扩展状态且冻结返回值', () => {
    expect(parseTaskEvent({ ...event(), state: 'PROVIDER_OBSERVED' }).state).toBe(
      'PROVIDER_OBSERVED',
    )
    expect(Object.isFrozen(parseTaskEvent(event()))).toBe(true)
  })
})

describe('Task单消费者observer协议', () => {
  const start = (callbacks: Partial<Parameters<typeof observeTaskEvents>[0]> = {}) => {
    const onSnapshot = vi.fn(),
      onEvent = vi.fn(),
      onState = vi.fn(),
      onRevoked = vi.fn()
    observer = observeTaskEvents({
      taskId: taskUuid(10000),
      onSnapshot,
      onEvent,
      onState,
      onRevoked,
      ...callbacks,
    })
    void observer.done.catch(() => {})
    return { onSnapshot, onEvent, onState, onRevoked }
  }
  it('快照同一响应header且MAC保持opaque；首帧101不从Task.revision2推算', async () => {
    fetcher.mockResolvedValueOnce(snapshot()).mockResolvedValueOnce(stream(frame(), true))
    const calls = start()
    await flush()
    expect(calls.onSnapshot).toHaveBeenCalledTimes(1)
    expect(calls.onEvent).toHaveBeenCalledWith(event())
    const [url, init] = fetcher.mock.calls[1]
    expect(String(url)).toContain(`/tasks/${taskUuid(10000)}/events`)
    expect(String(url)).not.toContain('MAC')
    expect(init.method).toBe('GET')
    expect(init.headers['X-Task-Event-Checkpoint']).toBe('opaque.snapshot.MAC')
    expect(init.headers['Last-Event-ID']).toBe(taskUuid(49000))
    expect(init.cache).toBe('no-store')
  })
  it('相同事件重复去重；断线重连只传最新真实event_id，不错用旧snapshot凭证', async () => {
    fetcher
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValueOnce(stream(frame() + frame()))
      .mockResolvedValueOnce(stream(frame() + frame(event(102)), true))
    const calls = start()
    await flush()
    expect(calls.onEvent).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    await flush()
    expect(calls.onEvent).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls[2][1].headers['Last-Event-ID']).toBe(event().event_id)
    expect(fetcher.mock.calls[2][1].headers['X-Task-Event-Checkpoint']).toBeUndefined()
  })
  it('序号缺口停止交付缺口之后的事件、重新取得快照，不能伪造连续成功', async () => {
    fetcher
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValueOnce(stream(frame() + frame(event(103))))
      .mockResolvedValueOnce(snapshot('fresh.MAC'))
      .mockResolvedValueOnce(stream('', true))
    const calls = start()
    await flush()
    expect(calls.onEvent.mock.calls.map((entry) => entry[0].sequence)).toEqual([101])
    await vi.advanceTimersByTimeAsync(1000)
    await flush()
    expect(calls.onSnapshot).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls[3][1].headers['X-Task-Event-Checkpoint']).toBe('fresh.MAC')
  })
  it('HTTP410只经新快照恢复；重复410明确失败，不能去掉游标跳过历史', async () => {
    fetcher
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValueOnce(failure(410, 'EVENT_CURSOR_EXPIRED'))
      .mockResolvedValueOnce(snapshot('new.MAC'))
      .mockResolvedValueOnce(failure(410, 'EVENT_CURSOR_EXPIRED'))
    const calls = start()
    const rejection = expect(observer!.done).rejects.toMatchObject({
      code: 'SNAPSHOT_RECOVERY_FAILED',
    })
    await flush()
    await vi.advanceTimersByTimeAsync(1000)
    await flush()
    await rejection
    expect(calls.onSnapshot).toHaveBeenCalledTimes(2)
    expect(fetcher.mock.calls[3][1].headers['Last-Event-ID']).toBeTruthy()
    expect(calls.onEvent).not.toHaveBeenCalled()
  })
  it.each([401, 403, 404])('首次HTTP%s即时终止，不重连、不借快照保留权限', async (status) => {
    fetcher.mockResolvedValueOnce(failure(status, 'PERMISSION_DENIED'))
    const calls = start()
    await observer!.done
    await vi.advanceTimersByTimeAsync(20000)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(calls.onRevoked).toHaveBeenCalledTimes(1)
    expect(calls.onSnapshot).not.toHaveBeenCalled()
  })
  it('流内撤权后同chunk后续事件不交付且停止读取，不写为全局Task状态', async () => {
    fetcher
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValueOnce(
        stream('event: SCOPE_REVOKED\ndata: {"code":"SCOPE_REVOKED"}\n\n' + frame()),
      )
    const calls = start()
    await observer!.done
    expect(calls.onRevoked).toHaveBeenCalledTimes(1)
    expect(calls.onEvent).not.toHaveBeenCalled()
    expect(calls.onState).toHaveBeenLastCalledWith(
      'revoked',
      expect.objectContaining({ code: 'SCOPE_REVOKED' }),
    )
  })
  it('网络失败1/2/5/10秒退避封顶，可取消等待且无隐藏重试', async () => {
    fetcher.mockRejectedValue(new TypeError('offline'))
    start()
    await flush()
    for (const [index, delay] of [1000, 2000, 5000, 10000, 10000].entries()) {
      expect(fetcher).toHaveBeenCalledTimes(index + 1)
      await vi.advanceTimersByTimeAsync(delay - 1)
      expect(fetcher).toHaveBeenCalledTimes(index + 1)
      await vi.advanceTimersByTimeAsync(1)
      await flush()
    }
    observer!.stop()
    await observer!.done
    const count = fetcher.mock.calls.length
    await vi.advanceTimersByTimeAsync(30000)
    expect(fetcher).toHaveBeenCalledTimes(count)
  })
  it('旧快照迟到不能覆盖新任务；外部Abort已取消不读取且取消活跃流', async () => {
    let finish!: (value: Response) => void
    fetcher.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const calls = start()
    observer!.stop()
    finish(snapshot())
    await observer!.done
    expect(calls.onSnapshot).not.toHaveBeenCalled()
    expect(calls.onEvent).not.toHaveBeenCalled()
    const controller = new AbortController()
    controller.abort()
    observer = observeTaskEvents({
      taskId: taskUuid(10000),
      signal: controller.signal,
      onSnapshot: vi.fn(),
      onEvent: vi.fn(),
      onRevoked: vi.fn(),
    })
    await observer.done
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('缺checkpoint终止，不悄悄降级成假轮询成功', async () => {
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify(taskFixture(taskUuid(10000), 1))))
    start()
    await expect(observer!.done).rejects.toMatchObject({ code: 'EVENT_SCHEMA_INVALID' })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it.each(['type', 'foreign', 'version', 'conflictingDuplicate'])(
    '事件流%s不伪造成功，未知schema终止、冲突重复触发快照',
    async (kind) => {
      let source: Response
      if (kind === 'type')
        source = new Response('{}', { headers: { 'Content-Type': 'application/json' } })
      else if (kind === 'foreign') source = stream(frame({ ...event(), task_id: taskUuid(9) }))
      else if (kind === 'version')
        source = stream(frame({ ...event(), schema_version: 2 } as never))
      else source = stream(frame() + frame({ ...event(), state: 'CHANGED' }))
      fetcher.mockResolvedValueOnce(snapshot()).mockResolvedValueOnce(source)
      const calls = start()
      if (kind === 'conflictingDuplicate') {
        await flush()
        expect(calls.onEvent).toHaveBeenCalledTimes(1)
        expect(calls.onState).toHaveBeenLastCalledWith(
          'reconnecting',
          expect.objectContaining({ code: 'EVENT_SEQUENCE_GAP' }),
        )
      } else {
        await expect(observer!.done).rejects.toMatchObject({ code: 'EVENT_SCHEMA_INVALID' })
        expect(calls.onEvent).not.toHaveBeenCalled()
      }
    },
  )
  it('流无心跳10秒后取消body并重连；stop之后不再通知旧Task', async () => {
    const cancel = vi.fn()
    fetcher.mockResolvedValueOnce(snapshot()).mockResolvedValueOnce(
      new Response(new ReadableStream({ cancel }), {
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    )
    const calls = start()
    await flush()
    await vi.advanceTimersByTimeAsync(10000)
    await flush()
    expect(cancel).toHaveBeenCalledTimes(1)
    expect(calls.onState).toHaveBeenLastCalledWith(
      'reconnecting',
      expect.objectContaining({ code: 'STREAM_IDLE' }),
    )
    observer!.stop()
    const states = calls.onState.mock.calls.length
    await observer!.done
    await vi.advanceTimersByTimeAsync(30000)
    expect(calls.onState).toHaveBeenCalledTimes(states)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
  it('外部Abort取消已打开的真实ReadableStream且不推进游标/重连', async () => {
    const cancel = vi.fn(),
      controller = new AbortController()
    fetcher.mockResolvedValueOnce(snapshot()).mockResolvedValueOnce(
      new Response(new ReadableStream({ cancel }), {
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    )
    const calls = start({ signal: controller.signal })
    await flush()
    controller.abort()
    await observer!.done
    expect(cancel).toHaveBeenCalledTimes(1)
    expect(calls.onEvent).not.toHaveBeenCalled()
    expect(calls.onState).toHaveBeenLastCalledWith('stopped')
  })
  it('HTTP403即使正文无效也撤权立停，不能当网络重试继续显示旧快照', async () => {
    fetcher.mockResolvedValueOnce(new Response('<html>forbidden</html>', { status: 403 }))
    const calls = start()
    await observer!.done
    expect(calls.onRevoked).toHaveBeenCalledTimes(1)
    expect(calls.onSnapshot).not.toHaveBeenCalled()
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('UI回调应用失败明确终止，不自动重连重复应用或推进到后续事件', async () => {
    fetcher
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValueOnce(stream(frame() + frame(event(102))))
    const apply = vi.fn(() => {
      throw new Error('fixture render failure')
    })
    start({ onEvent: apply })
    await expect(observer!.done).rejects.toMatchObject({ code: 'OBSERVER_CALLBACK_FAILED' })
    expect(apply).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
  it('同事务快照读取保持真实Task原schema，不能把响应头混到不同Task', async () => {
    fetcher.mockResolvedValueOnce(snapshot())
    const result = await loadTaskEventSnapshot(taskUuid(10000), new AbortController().signal)
    expect(result.task.nodes).toHaveLength(1)
    expect(result.checkpoint).toBe('opaque.snapshot.MAC')
    fetcher.mockResolvedValueOnce(snapshot())
    await expect(
      loadTaskEventSnapshot(taskUuid(9), new AbortController().signal),
    ).rejects.toMatchObject({ code: 'EVENT_SCHEMA_INVALID' })
  })
  it('Task快照原schema失配是终止错误，不能无限当网络中断重试', async () => {
    fetcher.mockResolvedValueOnce(
      new Response(JSON.stringify({ ...taskFixture(taskUuid(10000), 1), revision: '2' }), {
        headers: { 'X-Task-Event-Checkpoint': 'opaque.MAC' },
      }),
    )
    start()
    await expect(observer!.done).rejects.toMatchObject({ code: 'EVENT_SCHEMA_INVALID' })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
