/** Element Plus真实挂载与observer替身纯测，不代替真实SSE或平台验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TaskEventLog from '@/views/orbit/launch/TaskEventLog.vue'
import TaskDetails from '@/views/orbit/launch/TaskDetails.vue'
import * as streams from '@/api/orbit/task-events'
import { tasksApi } from '@/api/orbit/tasks'
import { taskFixture, taskUuid } from './tasks-fixtures'

const event = (sequence: number): streams.TaskEvent => ({
  event_id: taskUuid(100000 + sequence),
  sequence,
  schema_version: 1,
  task_id: taskUuid(10000),
  task_revision: 2,
  node_id: sequence % 2 ? taskUuid(30000) : null,
  state: 'CUSTOM_OBSERVATION',
  occurred_at: '2026-11-08T08:00:00+08:00',
  request_id: taskUuid(200000 + sequence),
})
let wrapper: VueWrapper | undefined
const subscriptions: {
  options: streams.TaskEventObserverOptions
  stop: ReturnType<typeof vi.fn>
}[] = []
const descriptor = Object.getOwnPropertyDescriptor(document, 'visibilityState')
const snapshot = () => ({
  task: { ...taskFixture(taskUuid(10000), 1), state: 'QUEUED' as const },
  checkpoint: 'must-not-appear-in-log',
})
const shownSequences = () =>
  wrapper!.findAll('.event-list summary').map((item) => Number(/^序号(\d+)/.exec(item.text())![1]))
async function click(text: string) {
  await wrapper!
    .findAll('button')
    .find((node) => node.text() === text)!
    .trigger('click')
  await flushPromises()
}
async function standalone(count = 200) {
  wrapper = mount(TaskEventLog, {
    props: {
      events: Array.from({ length: count }, (_, n) => event(n + 1)),
      dropped: 0,
      segment: 1,
      segmentNotice: '本次新段',
    },
    global: { plugins: [ElementPlus] },
  })
}
async function detail() {
  wrapper = mount(TaskDetails, {
    attachTo: document.body,
    props: { modelValue: true, taskId: taskUuid(10000), active: true, contextKey: 'A:tasks.read' },
    global: { plugins: [ElementPlus] },
  })
  subscriptions[0].options.onSnapshot(snapshot())
  subscriptions[0].options.onState?.('live')
  await flushPromises()
}
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  subscriptions.length = 0
  vi.spyOn(tasksApi, 'get').mockResolvedValue(snapshot().task)
  vi.spyOn(streams, 'observeTaskEvents').mockImplementation((options) => {
    let resolve!: () => void
    const done = new Promise<void>((yes) => {
      resolve = yes
    })
    const stop = vi.fn(() => {
      options.onState?.('stopped')
      resolve()
    })
    subscriptions.push({ options, stop })
    options.onState?.('snapshot')
    return { stop, done }
  })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.restoreAllMocks()
  vi.useRealTimers()
  document.body.innerHTML = ''
  if (descriptor) Object.defineProperty(document, 'visibilityState', descriptor)
})
it('原九字段全文可展开读取，nullable节点和未知state不猜含义、不显示checkpoint或动作', async () => {
  await standalone(2)
  const row = wrapper!.findAll('details')[0]
  await row.find('summary').trigger('click')
  expect(row.findAll('dt')).toHaveLength(9)
  const value = event(2)
  for (const [key, field] of Object.entries(value)) {
    expect(row.text()).toContain(key)
    expect(row.text()).toContain(field === null ? '任务级事件（null）' : String(field))
  }
  expect(wrapper!.text()).toContain('不是完整历史或平台执行成功证明')
  expect(wrapper!.text()).not.toContain('must-not-appear-in-log')
  expect(wrapper!.findAll('button').map((node) => node.text())).toEqual([
    '较新记录',
    '较早记录',
    '回到最新记录',
  ])
})
it.each([20, 50, 100, 200])('仅缓存内分页%s条且不发HTTP', async (size) => {
  const fetcher = vi.spyOn(globalThis, 'fetch')
  await standalone()
  const select = wrapper!.findComponent({ name: 'ElSelect' })
  select.vm.$emit('update:modelValue', size)
  select.vm.$emit('change', size)
  await flushPromises()
  expect(shownSequences()).toHaveLength(size)
  expect(shownSequences()[0]).toBe(200)
  expect(fetcher).not.toHaveBeenCalled()
})
it('查看较早页按sequence锚定，追加事件不挪页；缓存淘汰锚点则明确回最新页', async () => {
  await standalone()
  await click('较早记录')
  expect(shownSequences()[0]).toBe(180)
  await wrapper!.setProps({
    events: Array.from({ length: 200 }, (_, n) => event(n + 11)),
    dropped: 10,
  })
  expect(shownSequences()[0]).toBe(180)
  await click('较新记录')
  expect(shownSequences()[0]).toBe(200)
  await click('回到最新记录')
  expect(shownSequences()[0]).toBe(210)
  await click('较早记录')
  await wrapper!.setProps({
    events: Array.from({ length: 200 }, (_, n) => event(n + 201)),
    dropped: 200,
  })
  expect(shownSequences()[0]).toBe(400)
  expect(wrapper!.text()).toContain('较早记录已移出200条缓存')
})
it('新段重置翻页与展开DOM；状态与ID只作安全文本', async () => {
  await standalone()
  await click('较早记录')
  await wrapper!.setProps({
    events: [{ ...event(900), state: '<img src=x onerror=alert(1)>' }],
    segment: 2,
  })
  expect(shownSequences()).toEqual([900])
  expect(wrapper!.text()).toContain('<img src=x onerror=alert(1)>')
  expect(wrapper!.find('img').exists()).toBe(false)
})
it('空记录解释是未收到本次事件，不宣称无历史', async () => {
  await standalone(0)
  expect(wrapper!.text()).toContain('不代表任务没有历史事件')
})
it('新段即使出现同一事件ID也清除原生详情展开状态', async () => {
  await standalone(1)
  const previous = wrapper!.find('details').element as HTMLDetailsElement
  previous.open = true
  await wrapper!.setProps({ segment: 2 })
  expect(wrapper!.find('details').element).not.toBe(previous)
  expect((wrapper!.find('details').element as HTMLDetailsElement).open).toBe(false)
})
it('手动重读先清观察段，不借用新快照之前的事件，旧observer仍不能回填', async () => {
  await detail()
  subscriptions[0].options.onEvent(event(101))
  await flushPromises()
  // 原Drawer teleport到body，按钮不在根wrapper的DOM子树内。
  const refresh = [...document.querySelectorAll('button')].find(
    (node) => node.textContent?.trim() === '重新读取任务',
  )!
  expect(refresh).toBeTruthy()
  refresh.click()
  await flushPromises()
  expect(wrapper!.findComponent(TaskEventLog).props('events')).toHaveLength(0)
  subscriptions[0].options.onEvent(event(102))
  subscriptions[1].options.onSnapshot(snapshot())
  subscriptions[1].options.onState?.('live')
  await flushPromises()
  expect(wrapper!.findComponent(TaskEventLog).props('events')).toHaveLength(0)
  expect(subscriptions[0].stop).toHaveBeenCalled()
})
it('详情缓存最多200且完整保存九字段；事件仍只合并一次GET，不改Task业务状态', async () => {
  await detail()
  for (let n = 1; n <= 205; n++) subscriptions[0].options.onEvent(event(n))
  await flushPromises()
  const log = wrapper!.findComponent(TaskEventLog)
  expect(log.props('events')).toHaveLength(200)
  expect(log.props('events')[0]).toEqual(event(6))
  expect(log.props('events')[199]).toEqual(event(205))
  expect(log.props('dropped')).toBe(5)
  expect(tasksApi.get).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  expect(tasksApi.get).toHaveBeenCalledOnce()
  expect(wrapper!.emitted('updated')!.at(-1)![0]).toMatchObject({ state: 'QUEUED' })
})
it('同checkpoint重连保留记录；resynchronizing立即清段并明确缺失未恢复', async () => {
  await detail()
  subscriptions[0].options.onEvent(event(101))
  await flushPromises()
  subscriptions[0].options.onState?.('reconnecting')
  expect(wrapper!.findComponent(TaskEventLog).props('events')).toHaveLength(1)
  subscriptions[0].options.onState?.('resynchronizing')
  await flushPromises()
  expect(wrapper!.findComponent(TaskEventLog).props('events')).toHaveLength(0)
  subscriptions[0].options.onSnapshot(snapshot())
  await flushPromises()
  expect(wrapper!.findComponent(TaskEventLog).text()).toContain('缺失事件未恢复')
  subscriptions[0].options.onEvent(event(300))
  await flushPromises()
  expect(wrapper!.findComponent(TaskEventLog).props('events')).toEqual([event(300)])
})
it('换actor/隐藏/关闭清记录并丢弃旧epoch事件与快照，不能混合新段', async () => {
  await detail()
  subscriptions[0].options.onEvent(event(101))
  await flushPromises()
  await wrapper!.setProps({ contextKey: 'B:tasks.read' })
  subscriptions[1].options.onSnapshot(snapshot())
  subscriptions[1].options.onState?.('live')
  subscriptions[1].options.onEvent(event(500))
  subscriptions[0].options.onEvent(event(102))
  subscriptions[0].options.onSnapshot(snapshot())
  await flushPromises()
  expect(wrapper!.findComponent(TaskEventLog).props('events')).toEqual([event(500)])
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
  document.dispatchEvent(new Event('visibilitychange'))
  await flushPromises()
  expect(wrapper!.findComponent(TaskEventLog).props('events')).toHaveLength(0)
  subscriptions[1].options.onEvent(event(501))
  await flushPromises()
  expect(wrapper!.findComponent(TaskEventLog).props('events')).toHaveLength(0)
  await wrapper!.setProps({ modelValue: false })
  expect(subscriptions[1].stop).toHaveBeenCalled()
})
it('撤权立即清缓存并清旧Task，不从控制帧捏造事件记录', async () => {
  await detail()
  subscriptions[0].options.onEvent(event(101))
  await flushPromises()
  const oldLog = wrapper!.findComponent(TaskEventLog)
  subscriptions[0].options.onState?.(
    'revoked',
    new streams.TaskEventError('SCOPE_REVOKED', '读取权限已撤销', 403),
  )
  await flushPromises()
  expect(oldLog.exists()).toBe(false)
  expect(wrapper!.findComponent(TaskEventLog).exists()).toBe(false)
  expect(subscriptions[0].stop).toHaveBeenCalled()
})
