/** 原TaskEvent只读observer：认证仅用内存header；不解MAC、不执行任务、不将观察事件当平台成功。 */
import { orbitAuthHeaders, orbitCredentials } from './authentication'
import {
  parseTask,
  taskHttpError,
  type Task,
  type TaskErrorBody,
  type TaskFieldError,
} from './tasks'

export interface TaskEvent {
  event_id: string
  sequence: number
  schema_version: 1
  task_id: string
  task_revision: number
  node_id: string | null
  state: string
  occurred_at: string
  request_id: string
}
export interface TaskEventSnapshot {
  task: Task
  checkpoint: string
}
export type TaskObserverState =
  | 'snapshot'
  | 'connecting'
  | 'live'
  | 'reconnecting'
  | 'resynchronizing'
  | 'revoked'
  | 'failed'
  | 'stopped'
export class TaskEventError extends Error {
  readonly source: 'server' | 'local'
  readonly field_errors: TaskFieldError[]
  readonly retryable: boolean
  readonly request_id: string | null
  constructor(
    public code: string,
    message: string,
    public status = 0,
    details?: TaskErrorBody,
  ) {
    super(message)
    this.source = details ? 'server' : 'local'
    this.field_errors = details?.field_errors ?? []
    this.retryable = details?.retryable ?? false
    this.request_id = details?.request_id ?? null
  }
}
const uuid = (value: unknown): value is string =>
  typeof value === 'string' && /^[a-f\d]{8}(-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(value)
const safe = (value: unknown): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 1
const plain = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value)
const schema = () =>
  new TaskEventError('EVENT_SCHEMA_INVALID', '事件格式不受支持，已停止订阅，请重新读取任务')
function dateTime(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 64) return false
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-](\d{2}):(\d{2}))$/.exec(
      value,
    )
  if (!match) return false
  const [, y, m, d, h, min, sec, zoneH = '0', zoneM = '0'] = match
  return (
    +m >= 1 &&
    +m <= 12 &&
    +d >= 1 &&
    +d <= new Date(Date.UTC(+y, +m, 0)).getUTCDate() &&
    +h <= 23 &&
    +min <= 59 &&
    +sec <= 59 &&
    +zoneH <= 23 &&
    +zoneM <= 59 &&
    Number.isFinite(Date.parse(value))
  )
}
export function parseTaskEvent(value: unknown): TaskEvent {
  const keys = [
    'event_id',
    'sequence',
    'schema_version',
    'task_id',
    'task_revision',
    'node_id',
    'state',
    'occurred_at',
    'request_id',
  ]
  if (
    !plain(value) ||
    Object.keys(value).length !== keys.length ||
    keys.some((key) => !Object.hasOwn(value, key)) ||
    !uuid(value.event_id) ||
    !safe(value.sequence) ||
    value.schema_version !== 1 ||
    !uuid(value.task_id) ||
    !safe(value.task_revision) ||
    !(value.node_id === null || uuid(value.node_id)) ||
    typeof value.state !== 'string' ||
    [...value.state].length < 1 ||
    [...value.state].length > 40 ||
    !dateTime(value.occurred_at) ||
    !uuid(value.request_id)
  )
    throw schema()
  return Object.freeze({ ...value }) as unknown as TaskEvent
}
export type TaskEventFrame = { kind: 'event'; event: TaskEvent } | { kind: 'revoked' }

/** 只保留一个有界帧；跨UTF8字节/CRLF分片增量解码，注释不产生业务事件。 */
export class TaskSseDecoder {
  private decoder = new TextDecoder('utf-8', { fatal: true })
  private line = ''
  private afterCR = false
  private bytes = 0
  private id: string | undefined
  private name: string | undefined
  private data: string[] = []
  constructor(private emit: (frame: TaskEventFrame) => void) {}
  feed(bytes: Uint8Array) {
    // 分片解码避免网络一次给超大chunk时产生无界临时字符串。
    for (let at = 0; at < bytes.byteLength; at += 4096) {
      let text: string
      try {
        text = this.decoder.decode(bytes.subarray(at, at + 4096), { stream: true })
      } catch {
        throw schema()
      }
      this.text(text)
    }
  }
  finish() {
    try {
      this.text(this.decoder.decode())
    } catch (error) {
      if (error instanceof TaskEventError) throw error
      throw schema()
    }
    if (this.line || this.data.length || this.id !== undefined || this.name !== undefined)
      throw new TaskEventError('STREAM_TRUNCATED', '事件连接中断，将从已确认事件继续读取')
  }
  private text(value: string) {
    for (const char of value) {
      if (this.afterCR) {
        this.afterCR = false
        if (char === '\n') continue
      }
      if (char === '\r' || char === '\n') {
        this.consume()
        this.afterCR = char === '\r'
      } else {
        this.line += char
        if (this.line.length > 8192) throw schema()
      }
    }
  }
  private consume() {
    const line = this.line
    this.line = ''
    if (!line) {
      const { id, name, data } = this
      this.id = this.name = undefined
      this.data = []
      this.bytes = 0
      if (!data.length) {
        if (id !== undefined || name !== undefined) throw schema()
        return
      }
      let value: unknown
      try {
        value = JSON.parse(data.join('\n'))
      } catch {
        throw schema()
      }
      if (name === 'SCOPE_REVOKED') {
        if (
          id !== undefined ||
          !plain(value) ||
          Object.keys(value).length !== 1 ||
          value.code !== 'SCOPE_REVOKED'
        )
          throw schema()
        this.emit({ kind: 'revoked' })
      } else {
        if (name !== undefined) throw schema()
        const event = parseTaskEvent(value)
        if (id !== event.event_id) throw schema()
        this.emit({ kind: 'event', event })
      }
      return
    }
    this.bytes += new TextEncoder().encode(line).byteLength + 1
    if (this.bytes > 16384) throw schema()
    if (line.startsWith(':')) return
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    let value = colon < 0 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'data') this.data.push(value)
    else if (field === 'id' && this.id === undefined && uuid(value)) this.id = value
    else if (field === 'event' && this.name === undefined) this.name = value
    else throw schema()
  }
}

const interrupted = () => new DOMException('任务订阅已取消', 'AbortError')
const releases = new WeakMap<Response, () => void>()
function release(result: Response) {
  releases.get(result)?.()
  releases.delete(result)
}
const canceled = (signal: AbortSignal) => {
  if (signal.aborted) throw interrupted()
}
async function response(path: string, signal: AbortSignal, extra: Record<string, string> = {}) {
  canceled(signal)
  const child = new AbortController()
  const abort = () => child.abort()
  signal.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(abort, 10000)
  try {
    const result = await fetch(`${import.meta.env.VITE_APP_BASE_API}/api/v1${path}`, {
      method: 'GET',
      headers: orbitAuthHeaders(extra),
      credentials: orbitCredentials(),
      cache: 'no-store',
      signal: child.signal,
    })
    releases.set(result, () => signal.removeEventListener('abort', abort))
    return result
  } catch (error) {
    signal.removeEventListener('abort', abort)
    canceled(signal)
    if (error instanceof TaskEventError) throw error
    throw new TaskEventError('STREAM_UNAVAILABLE', '任务订阅读取中断，将按退避重新连接')
  } finally {
    clearTimeout(timer)
    // 响应头超时结束；父abort直到body消费/取消完成仍继续传给fetch，避免头/体交界的取消漏洞。
  }
}
async function take(reader: ReadableStreamDefaultReader<Uint8Array>, signal: AbortSignal) {
  canceled(signal)
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      reader.read(),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(
          () => reject(new TaskEventError('STREAM_IDLE', '连接未收到心跳，将重新连接')),
          10000,
        )
      }),
    ])
  } finally {
    if (timer) clearTimeout(timer)
  }
}
async function json(response: Response, signal: AbortSignal, limit: number): Promise<unknown> {
  if (!response.body) {
    release(response)
    throw schema()
  }
  const reader = response.body.getReader()
  const abort = () => {
    void reader.cancel().catch(() => {})
  }
  signal.addEventListener('abort', abort, { once: true })
  let length = 0,
    text = ''
  const decoder = new TextDecoder('utf-8', { fatal: true })
  try {
    while (true) {
      const { done, value } = await take(reader, signal)
      canceled(signal)
      if (done) break
      length += value.byteLength
      if (length > limit) throw schema()
      text += decoder.decode(value, { stream: true })
    }
    return JSON.parse(text + decoder.decode())
  } catch (error) {
    canceled(signal)
    if (error instanceof TaskEventError) throw error
    throw schema()
  } finally {
    signal.removeEventListener('abort', abort)
    await reader.cancel().catch(() => {})
    reader.releaseLock()
    release(response)
  }
}
async function checked(result: Response, signal: AbortSignal) {
  if (result.ok) return
  let value: unknown
  try {
    // 原100条字段错误的最坏JSON转义仍有界，不能用单个SSE帧的8KiB限制截断原Error。
    value = await json(result, signal, 2 * 1024 * 1024)
  } catch {
    canceled(signal)
  }
  const error = taskHttpError(result.status, value)
  throw new TaskEventError(
    error.code,
    error.message,
    error.status,
    error.source === 'server'
      ? {
          code: error.code,
          message: error.message,
          field_errors: error.field_errors,
          retryable: error.retryable,
          request_id: error.request_id!,
        }
      : undefined,
  )
}
function identifier(value: string) {
  if (!uuid(value)) throw schema()
  return value.toLowerCase()
}
export async function loadTaskEventSnapshot(
  taskId: string,
  signal: AbortSignal,
): Promise<TaskEventSnapshot> {
  const result = await response(`/tasks/${identifier(taskId)}`, signal, {
    Accept: 'application/json',
  })
  canceled(signal)
  await checked(result, signal)
  const value = await json(result, signal, 4 * 1024 * 1024)
  let task: Task
  try {
    task = parseTask(value)
  } catch {
    throw schema()
  }
  const checkpoint = result.headers.get('X-Task-Event-Checkpoint')
  if (
    task.id.toLowerCase() !== taskId.toLowerCase() ||
    !uuid(task.latest_event_id) ||
    !checkpoint ||
    !/^[\x21-\x7e]{1,8192}$/.test(checkpoint)
  )
    throw schema()
  return { task, checkpoint }
}
export interface TaskEventObserverOptions {
  taskId: string
  signal?: AbortSignal
  /** 回调同步替换真实快照；接入后不得把旧nodes与新revision拼接。 */
  onSnapshot: (value: TaskEventSnapshot) => void
  onEvent: (event: TaskEvent) => void
  onState?: (state: TaskObserverState, error?: TaskEventError) => void
  onRevoked: () => void
}
const pause = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(interrupted())
      return
    }
    const abort = () => {
      clearTimeout(timer)
      reject(interrupted())
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      resolve()
    }, ms)
    signal.addEventListener('abort', abort, { once: true })
  })

/** 单Task单消费者；停止后所有迟到读取失效。序号首帧由服务器保证，绝不从Task.revision推算。 */
export function observeTaskEvents(options: TaskEventObserverOptions) {
  const id = identifier(options.taskId)
  const controller = new AbortController(),
    signal = controller.signal
  let terminal = false
  let stopped = false
  const stop = () => {
    controller.abort()
    if (!terminal && !stopped) {
      stopped = true
      options.onState?.('stopped')
    }
  }
  options.signal?.addEventListener('abort', stop, { once: true })
  if (options.signal?.aborted) stop()
  const state = (value: TaskObserverState, error?: TaskEventError) => {
    if (!signal.aborted && !terminal) options.onState?.(value, error)
  }
  const done = (async () => {
    let needSnapshot = true,
      recovery = 0,
      retry = 0
    let lastId: string | null = null,
      checkpoint: string | null = null
    let sequence: number | null = null,
      revision = 0
    const recent = new Map<number, string>()
    const seenIds = new Map<string, number>()
    const notify = (callback: () => void) => {
      try {
        callback()
      } catch {
        throw new TaskEventError(
          'OBSERVER_CALLBACK_FAILED',
          '任务观察结果未能应用，已停止订阅，请重新读取',
        )
      }
    }
    try {
      while (!signal.aborted) {
        try {
          if (needSnapshot) {
            state(recovery ? 'resynchronizing' : 'snapshot')
            const snapshot = await loadTaskEventSnapshot(id, signal)
            canceled(signal)
            notify(() => options.onSnapshot(snapshot))
            canceled(signal)
            lastId = snapshot.task.latest_event_id
            checkpoint = snapshot.checkpoint
            revision = snapshot.task.revision
            sequence = null
            recent.clear()
            seenIds.clear()
            needSnapshot = false
          }
          state('connecting')
          const result = await response(`/tasks/${id}/events`, signal, {
            Accept: 'text/event-stream',
            ...(lastId ? { 'Last-Event-ID': lastId } : {}),
            ...(checkpoint ? { 'X-Task-Event-Checkpoint': checkpoint } : {}),
          })
          canceled(signal)
          await checked(result, signal)
          if (
            result.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase() !==
              'text/event-stream' ||
            !result.body
          ) {
            await result.body?.cancel().catch(() => {})
            release(result)
            throw schema()
          }
          recovery = 0
          state('live')
          const reader = result.body.getReader()
          const abort = () => {
            void reader.cancel().catch(() => {})
          }
          signal.addEventListener('abort', abort, { once: true })
          const decoder = new TaskSseDecoder((frame) => {
            canceled(signal)
            if (frame.kind === 'revoked')
              throw new TaskEventError('SCOPE_REVOKED', '当前任务读取权限已撤销', 403)
            const event = frame.event
            if (event.task_id.toLowerCase() !== id) throw schema()
            if (sequence === null && event.event_id === lastId)
              throw new TaskEventError(
                'EVENT_SEQUENCE_GAP',
                '事件未位于快照之后，需要重新取得任务快照',
              )
            const signature = JSON.stringify([
              event.event_id,
              event.sequence,
              event.schema_version,
              event.task_id,
              event.task_revision,
              event.node_id,
              event.state,
              event.occurred_at,
              event.request_id,
            ])
            if (sequence !== null && event.sequence <= sequence) {
              if (recent.get(event.sequence) === signature) return
              throw new TaskEventError('EVENT_SEQUENCE_GAP', '事件重放不一致，需要重新取得任务快照')
            }
            if (
              (sequence !== null && event.sequence !== sequence + 1) ||
              event.task_revision < revision ||
              seenIds.has(event.event_id)
            )
              throw new TaskEventError('EVENT_SEQUENCE_GAP', '事件不连续，需要重新取得任务快照')
            notify(() => options.onEvent(event))
            canceled(signal)
            sequence = event.sequence
            revision = event.task_revision
            lastId = event.event_id
            checkpoint = null // 快照凭证仅绑定快照latest，不能冒充后续事件的续传凭证。
            recent.set(sequence, signature)
            seenIds.set(event.event_id, sequence)
            if (recent.size > 200) {
              const oldest = recent.keys().next().value!
              const old = JSON.parse(recent.get(oldest)!)
              seenIds.delete(old[0])
              recent.delete(oldest)
            }
            retry = 0
          })
          try {
            while (!signal.aborted) {
              const { done, value } = await take(reader, signal)
              canceled(signal)
              if (done) {
                decoder.finish()
                break
              }
              decoder.feed(value)
            }
          } finally {
            signal.removeEventListener('abort', abort)
            await reader.cancel().catch(() => {})
            reader.releaseLock()
            release(result)
          }
          throw new TaskEventError('STREAM_CLOSED', '事件连接已结束，将继续订阅')
        } catch (cause) {
          if (signal.aborted) break
          const error =
            cause instanceof TaskEventError
              ? cause
              : new TaskEventError('STREAM_UNAVAILABLE', '连接中断，将重新连接')
          if ([401, 403, 404].includes(error.status)) {
            terminal = true
            lastId = checkpoint = null
            recent.clear()
            seenIds.clear()
            options.onState?.('revoked', error)
            options.onRevoked()
            return
          }
          if (
            error.status === 410 ||
            error.code === 'EVENT_SEQUENCE_GAP' ||
            (error.status === 400 && error.code === 'EVENT_CURSOR_INVALID')
          ) {
            if (++recovery > 1)
              throw new TaskEventError(
                'SNAPSHOT_RECOVERY_FAILED',
                '重新取得快照后仍无法连续订阅，请手动重新读取',
              )
            needSnapshot = true
          } else if (
            ['EVENT_SCHEMA_INVALID', 'OBSERVER_CALLBACK_FAILED'].includes(error.code) ||
            (error.status >= 400 && ![429, 500, 502, 503, 504].includes(error.status))
          )
            throw error
          state('reconnecting', error)
          await pause([1000, 2000, 5000, 10000][Math.min(retry++, 3)], signal)
        }
      }
    } catch (error) {
      if (!signal.aborted) {
        terminal = true
        options.onState?.('failed', error instanceof TaskEventError ? error : schema())
        throw error
      }
    } finally {
      options.signal?.removeEventListener('abort', stop)
      if (!terminal && !stopped) options.onState?.('stopped')
      controller.abort()
    }
  })()
  return { stop, done }
}
