/** 真实ElementPlus挂载、observer协议替身：不作为真实SSE/平台结果验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TaskDetails from '@/views/orbit/launch/TaskDetails.vue'
import * as events from '@/api/orbit/task-events'
import { tasksApi, TaskApiError, type Task } from '@/api/orbit/tasks'
import { taskFixture, taskUuid, nodePage } from './tasks-fixtures'
type Subscription = {
  options: events.TaskEventObserverOptions
  stop: ReturnType<typeof vi.fn>
  reject: (error: unknown) => void
}
const subscriptions: Subscription[] = []
let wrapper: VueWrapper | undefined
const descriptor = Object.getOwnPropertyDescriptor(document, 'visibilityState')
function visible(value: string) {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value })
  document.dispatchEvent(new Event('visibilitychange'))
}
const task = (revision = 1) => ({
  ...taskFixture(),
  revision,
  state: 'QUEUED' as const,
  latest_event_id: taskUuid(9000 + revision),
})
function deliver(index = 0, value: Task = task()) {
  subscriptions[index].options.onSnapshot({ task: value, checkpoint: 'not-shown-in-ui' })
  subscriptions[index].options.onState?.('live')
}
function change(index = 0, sequence = 100) {
  subscriptions[index].options.onEvent({
    event_id: taskUuid(100000 + sequence),
    sequence,
    schema_version: 1,
    task_id: taskUuid(10000),
    task_revision: 2,
    node_id: taskUuid(10),
    state: 'FAILED',
    occurred_at: '2026-11-08T00:00:00Z',
    request_id: taskUuid(200000),
  })
}
async function start() {
  wrapper = mount(TaskDetails, {
    attachTo: document.body,
    props: { modelValue: true, taskId: taskUuid(10000), active: true },
    global: { plugins: [ElementPlus] },
  })
  deliver()
  await flushPromises()
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  visible('visible')
  subscriptions.length = 0
  vi.spyOn(tasksApi, 'get').mockResolvedValue(task(2))
  vi.spyOn(tasksApi, 'nodes').mockResolvedValue(nodePage())
  vi.spyOn(events, 'observeTaskEvents').mockImplementation((options) => {
    let resolve!: () => void, reject!: (error: unknown) => void
    const done = new Promise<void>((yes, no) => {
      resolve = yes
      reject = no
    })
    const stop = vi.fn(() => {
      options.onState?.('stopped')
      resolve()
    })
    subscriptions.push({ options, stop, reject })
    options.onState?.('snapshot')
    return { stop, done }
  })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
  if (descriptor) Object.defineProperty(document, 'visibilityState', descriptor)
})
it('同有tasks.read的身份上下文切换中断旧observer和GET，迟到错误/事件不污染新任务', async () => {
  await start()
  await wrapper!.setProps({ contextKey: 'actor-A:tasks.read' })
  deliver(1)
  await flushPromises()
  const detail = {
    code: 'READ_FAILED',
    message: '甲读取失败',
    field_errors: [{ path: '/nodes/0', code: 'INVALID', message: '字段说明', constraint: '条件' }],
    retryable: true,
    request_id: taskUuid(888888),
  }
  const cause = new events.TaskEventError(detail.code, detail.message, 503, detail)
  subscriptions[1].options.onState?.('failed', cause)
  await flushPromises()
  expect(document.body.textContent).toContain(detail.request_id)
  let rejectOld!: (error: unknown) => void
  vi.mocked(tasksApi.get).mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        rejectOld = reject
      }),
  )
  await vi.advanceTimersByTimeAsync(10000)
  await wrapper!.setProps({ contextKey: 'actor-B:tasks.read' })
  expect(subscriptions[1].stop).toHaveBeenCalled()
  deliver(2, {
    ...task(3),
    ownership: { owner_user_id: taskUuid(77777), owner_team_id: taskUuid(77778) },
  })
  await flushPromises()
  expect(document.body.textContent).not.toContain(detail.request_id)
  expect(document.body.textContent).toContain(taskUuid(77777))
  subscriptions[1].options.onState?.('revoked', cause)
  subscriptions[1].options.onSnapshot({ task: task(99), checkpoint: 'old-checkpoint' })
  change(1)
  rejectOld(new TaskApiError(403, detail.code, detail.message, detail))
  await flushPromises()
  await vi.advanceTimersByTimeAsync(1000)
  expect(document.body.textContent).not.toContain(detail.request_id)
  expect(document.body.textContent).toContain(taskUuid(77777))
  expect(wrapper!.emitted('updated')!.at(-1)![0]).toMatchObject({ revision: 3 })
  expect(wrapper!.emitted('revoked')).toBeUndefined()
})
it('SSE授权错误原五字段传递到详情与父层，清旧任务且停流', async () => {
  await start()
  const detail = {
    code: 'PERMISSION_DENIED',
    message: '读取权限变化',
    field_errors: [],
    retryable: false,
    request_id: taskUuid(888889),
  }
  subscriptions[0].options.onState?.(
    'revoked',
    new events.TaskEventError(detail.code, detail.message, 403, detail),
  )
  await flushPromises()
  expect(document.body.textContent).toContain(detail.request_id)
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(0)
  expect(subscriptions[0].stop).toHaveBeenCalled()
  expect(wrapper!.emitted('revoked')![0]![0]).toMatchObject({
    ...detail,
    status: 403,
    source: 'server',
  })
})
it('单observer快照开启，live不全量轮询；事件只合并触发GET，不以node FAILED臆造Task失败', async () => {
  await start()
  expect(events.observeTaskEvents).toHaveBeenCalledTimes(1)
  expect(document.body.textContent).toContain('任务更新已连接')
  expect(document.body.textContent).not.toContain('not-shown-in-ui')
  await vi.advanceTimersByTimeAsync(10000)
  expect(tasksApi.get).not.toHaveBeenCalled()
  for (let n = 0; n < 20; n++) change(0, 100 + n)
  await vi.advanceTimersByTimeAsync(999)
  expect(tasksApi.get).not.toHaveBeenCalled()
  expect(wrapper!.emitted('updated')!.at(-1)![0]).toMatchObject({ state: 'QUEUED', revision: 1 })
  await vi.advanceTimersByTimeAsync(1)
  await flushPromises()
  expect(tasksApi.get).toHaveBeenCalledTimes(1)
  expect(wrapper!.emitted('updated')!.at(-1)![0]).toMatchObject({ state: 'QUEUED', revision: 2 })
})
it('事件到达正在读取时只保留一次待刷新意图，没有并发GET风暴', async () => {
  await start()
  let complete!: (value: Task) => void
  vi.mocked(tasksApi.get).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve
      }),
  )
  change()
  await vi.advanceTimersByTimeAsync(1000)
  for (let n = 0; n < 200; n++) change(0, 200 + n)
  await vi.advanceTimersByTimeAsync(3000)
  expect(tasksApi.get).toHaveBeenCalledTimes(1)
  complete(task(2))
  await flushPromises()
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  expect(tasksApi.get).toHaveBeenCalledTimes(2)
})
it('重连fallback每10秒有界读取，503后仍可恢复；live立即停fallback', async () => {
  await start()
  subscriptions[0].options.onState?.(
    'reconnecting',
    new events.TaskEventError('STREAM_UNAVAILABLE', 'fixture'),
  )
  vi.mocked(tasksApi.get).mockRejectedValueOnce(
    new TaskApiError(503, 'UNAVAILABLE', '服务暂不可用'),
  )
  await vi.advanceTimersByTimeAsync(9999)
  expect(tasksApi.get).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  await flushPromises()
  expect(tasksApi.get).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(10000)
  await flushPromises()
  expect(tasksApi.get).toHaveBeenCalledTimes(2)
  subscriptions[0].options.onState?.('live')
  await vi.advanceTimersByTimeAsync(30000)
  expect(tasksApi.get).toHaveBeenCalledTimes(2)
})
it('410或缺口恢复新快照后取消旧节点页并回首页，保留明确恢复说明', async () => {
  await start()
  const next = [...document.querySelectorAll('button')].find(
    (button) => button.textContent?.trim() === '下一段节点',
  )!
  next.click()
  await flushPromises()
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(50)
  subscriptions[0].options.onState?.('resynchronizing')
  deliver(0, task(2))
  await flushPromises()
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(200)
  expect(document.body.textContent).toContain('已重新取得快照')
  expect(tasksApi.get).not.toHaveBeenCalled()
})
it('切Task/后台隐藏/关闭后停止observer；迟到快照与状态/错误不能覆盖新页面', async () => {
  await start()
  await wrapper!.setProps({ taskId: taskUuid(20000) })
  expect(subscriptions[0].stop).toHaveBeenCalledTimes(1)
  deliver(1, { ...task(), id: taskUuid(20000) })
  await flushPromises()
  deliver(0, task(99))
  change()
  subscriptions[0].options.onRevoked()
  await flushPromises()
  expect(document.body.textContent).toContain(taskUuid(20000))
  expect(document.body.textContent).not.toContain(taskUuid(10000))
  visible('hidden')
  expect(subscriptions[1].stop).toHaveBeenCalledTimes(1)
  subscriptions[1].reject(new events.TaskEventError('STREAM_IDLE', '旧连接失败不应显示'))
  await flushPromises()
  expect(document.body.textContent).not.toContain('旧连接失败不应显示')
  await vi.advanceTimersByTimeAsync(30000)
  expect(tasksApi.get).not.toHaveBeenCalled()
  visible('visible')
  deliver(2, { ...task(), id: taskUuid(20000) })
  await flushPromises()
  await wrapper!.setProps({ modelValue: false })
  expect(subscriptions[2].stop).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(11000)
  expect(tasksApi.get).not.toHaveBeenCalled()
})
it('观察撤权立停并清Task/node/详情，不把SCOPE_REVOKED伪装成Task业务状态', async () => {
  await start()
  subscriptions[0].options.onRevoked()
  await flushPromises()
  expect(subscriptions[0].stop).toHaveBeenCalledTimes(1)
  expect(wrapper!.emitted('revoked')).toHaveLength(1)
  expect(document.body.textContent).not.toContain(taskUuid(10000))
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(0)
  change()
  await vi.advanceTimersByTimeAsync(30000)
  expect(tasksApi.get).not.toHaveBeenCalled()
})
it('手动刷新仅重建一个observer，消费done拒绝后允许重新读取且没有未处理异常', async () => {
  await start()
  subscriptions[0].reject(new events.TaskEventError('EVENT_SCHEMA_INVALID', '需重新读取'))
  await flushPromises()
  expect(document.body.textContent).toContain('需重新读取')
  const button = [...document.querySelectorAll('button')].find(
    (value) => value.textContent?.trim() === '重新读取任务',
  )!
  expect(button.disabled).toBe(false)
  button.click()
  await flushPromises()
  expect(events.observeTaskEvents).toHaveBeenCalledTimes(2)
  expect(subscriptions[0].stop).toHaveBeenCalledTimes(1)
  deliver(1, task(2))
  await flushPromises()
  expect(document.body.textContent).toContain('任务更新已连接')
  expect(document.body.textContent).not.toContain('需重新读取')
})
it('初次快照网络失败进入重连后可手动重试，不能永久锁定读取按钮', async () => {
  wrapper = mount(TaskDetails, {
    attachTo: document.body,
    props: { modelValue: true, taskId: taskUuid(10000), active: true },
    global: { plugins: [ElementPlus] },
  })
  subscriptions[0].options.onState?.(
    'reconnecting',
    new events.TaskEventError('STREAM_UNAVAILABLE', '连接中断'),
  )
  await flushPromises()
  const button = [...document.querySelectorAll('button')].find(
    (value) => value.textContent?.trim() === '重新读取任务',
  )!
  expect(button.disabled).toBe(false)
  button.click()
  await flushPromises()
  expect(subscriptions[0].stop).toHaveBeenCalledTimes(1)
  expect(events.observeTaskEvents).toHaveBeenCalledTimes(2)
  deliver(1)
  await flushPromises()
  expect(document.body.textContent).toContain('任务更新已连接')
})
