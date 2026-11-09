/** ElementPlus真实挂载+严格fixture响应，不是后端联调/浏览器验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TaskDetails from '@/views/orbit/launch/TaskDetails.vue'
import TaskPanel from '@/views/orbit/launch/TaskPanel.vue'
import { tasksApi, TaskApiError, type Task } from '@/api/orbit/tasks'
import { nodePage, taskFixture, taskNode, taskPage, taskUuid } from './tasks-fixtures'
import * as events from '@/api/orbit/task-events'

let wrapper: VueWrapper | undefined
const visibilityDescriptor = Object.getOwnPropertyDescriptor(document, 'visibilityState')
function visibility(value: string) {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value })
  document.dispatchEvent(new Event('visibilitychange'))
}
function button(text: string) {
  const found = [...document.querySelectorAll('button')].find(
    (node) => node.textContent?.trim() === text,
  )
  expect(found, `按钮${text}`).toBeTruthy()
  return found!
}
async function click(text: string) {
  button(text).click()
  await flushPromises()
}
async function start(task = taskFixture(taskUuid(10000), 2)) {
  vi.spyOn(tasksApi, 'get').mockResolvedValue(task)
  vi.spyOn(tasksApi, 'nodes').mockResolvedValue(nodePage())
  wrapper = mount(TaskDetails, {
    attachTo: document.body,
    props: { modelValue: true, taskId: task.id, active: true },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  visibility('visible')
  sessionStorage.clear()
  // 原字段/分页组件测试的观察器替身，仅把既有GET fixture接入快照回调；不是SSE联调。
  vi.spyOn(events, 'observeTaskEvents').mockImplementation((options) => {
    const controller = new AbortController()
    const done = tasksApi
      .get(options.taskId, controller.signal)
      .then((task) => {
        if (controller.signal.aborted) return
        options.onSnapshot({ task, checkpoint: 'unit-fixture' })
        options.onState?.('live')
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          options.onState?.('failed', cause)
          if ([401, 403, 404].includes(cause.status)) options.onRevoked()
        }
      })
    return { stop: () => controller.abort(), done }
  })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.useRealTimers()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
  if (visibilityDescriptor) Object.defineProperty(document, 'visibilityState', visibilityDescriptor)
  else Reflect.deleteProperty(document, 'visibilityState')
})

it('详情完整首200及真实node_count，配置/投放与任务状态分开，不生成执行操作', async () => {
  await start(taskFixture())
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(200)
  expect(document.body.textContent).toContain('总节点数 275')
  expect(document.body.textContent).toContain('未核验 / 未知')
  expect(document.body.textContent).toContain('需要人工对账')
  for (const text of ['执行任务', '安全重试', '取消任务', '开始投放'])
    expect(
      [...document.querySelectorAll('button')].some((node) => node.textContent?.trim() === text),
    ).toBe(false)
})

it('详情nextcursor正确接第201默认50，上一段回详情首200，不截父依赖', async () => {
  await start(taskFixture())
  await click('下一段节点')
  expect(tasksApi.nodes).toHaveBeenLastCalledWith(
    taskUuid(10000),
    { page_size: 50, cursor: 'detail-start-201-default50' },
    expect.any(AbortSignal),
  )
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(50)
  expect(document.body.textContent).toContain('/201')
  await click('上一段节点')
  expect(tasksApi.get).toHaveBeenCalledTimes(2)
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(200)
})

it('前缀查询从节点首页开始，101码点本地拒绝且不发送截断前缀', async () => {
  await start()
  const input = document.querySelector('input[aria-label="节点键前缀"]') as HTMLInputElement
  input.value = ' AD/ '
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  await click('查询节点')
  expect(tasksApi.nodes).toHaveBeenLastCalledWith(
    taskUuid(10000),
    { page_size: 50, q: 'AD/' },
    expect.any(AbortSignal),
  )
  const calls = vi.mocked(tasksApi.nodes).mock.calls.length
  input.value = '🙂'.repeat(101)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  await click('查询节点')
  expect(document.body.textContent).toContain('最多100个码点')
  expect(tasksApi.nodes).toHaveBeenCalledTimes(calls)
})

it('快速切换任务时abort旧请求，迟到旧响应不能覆盖新任务', async () => {
  let firstResolve!: (value: Task) => void, secondResolve!: (value: Task) => void
  const signals: AbortSignal[] = []
  vi.spyOn(tasksApi, 'get').mockImplementation((id, signal) => {
    signals.push(signal!)
    return new Promise((resolve) => {
      if (id === taskUuid(10000)) firstResolve = resolve
      else secondResolve = resolve
    })
  })
  wrapper = mount(TaskDetails, {
    attachTo: document.body,
    props: { modelValue: true, taskId: taskUuid(10000), active: true },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  await wrapper.setProps({ taskId: taskUuid(20000) })
  await flushPromises()
  expect(signals[0].aborted).toBe(true)
  secondResolve(taskFixture(taskUuid(20000), 1))
  await flushPromises()
  firstResolve(taskFixture(taskUuid(10000), 1))
  await flushPromises()
  expect(document.body.textContent).toContain(taskUuid(20000))
  expect(document.body.textContent).not.toContain(taskUuid(10000))
})

it('正常live不重复10秒全量GET，隐藏/关闭/卸载取消观察，恢复可见才重取快照', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  await start()
  await vi.advanceTimersByTimeAsync(9999)
  expect(tasksApi.get).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1)
  await flushPromises()
  expect(tasksApi.get).toHaveBeenCalledTimes(1)
  visibility('hidden')
  await vi.advanceTimersByTimeAsync(30000)
  expect(tasksApi.get).toHaveBeenCalledTimes(1)
  visibility('visible')
  await flushPromises()
  expect(tasksApi.get).toHaveBeenCalledTimes(2)
  await wrapper!.setProps({ modelValue: false })
  await vi.advanceTimersByTimeAsync(30000)
  expect(tasksApi.get).toHaveBeenCalledTimes(2)
  wrapper!.unmount()
  wrapper = undefined
  await vi.advanceTimersByTimeAsync(30000)
  expect(tasksApi.get).toHaveBeenCalledTimes(2)
})

it('观察撤权清除已有任务和节点并停止，不能继续展示缓存或假失败重发', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  await start()
  vi.mocked(events.observeTaskEvents).mock.calls[0][0].onRevoked()
  await flushPromises()
  expect(wrapper!.emitted('revoked')).toHaveLength(1)
  expect(document.body.textContent).toContain('当前任务读取权限已撤销')
  expect(document.body.textContent).not.toContain(taskUuid(10000))
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(0)
  const count = vi.mocked(tasksApi.get).mock.calls.length
  await vi.advanceTimersByTimeAsync(60000)
  expect(tasksApi.get).toHaveBeenCalledTimes(count)
})

it('快照409清节点和游标，重新读取后使用新版本，不能重复旧页', async () => {
  await start(taskFixture())
  vi.mocked(tasksApi.nodes).mockRejectedValueOnce(
    new TaskApiError(409, 'TASK_SNAPSHOT_CHANGED', '快照已变化'),
  )
  await click('下一段节点')
  expect(document.body.textContent).toContain('快照已变化')
  expect(button('下一段节点').disabled).toBe(true)
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(0)
  vi.mocked(tasksApi.get).mockResolvedValueOnce({ ...taskFixture(taskUuid(10000), 2), revision: 2 })
  await click('重新读取任务')
  expect(document.body.textContent).not.toContain('快照已变化')
  expect(document.querySelectorAll('.task-node-table .el-table__body tr')).toHaveLength(2)
})

it('节点二级详情保留全部100父ID/跨页提示/大整数与错误纯文本', async () => {
  const task = taskFixture(taskUuid(10000), 1)
  task.nodes[0] = {
    ...taskNode(),
    parent_ids: Array.from({ length: 100 }, (_, i) => taskUuid(5000 + i)),
    error_message: '<img src=x onerror=alert(1)> 中文🙂',
    retryable: true,
    no_op: false,
    execution_mode: 'ADSPOWER_UI',
  }
  await start(task)
  await click('节点详情')
  expect(document.querySelectorAll('.parent-list li')).toHaveLength(100)
  expect(document.body.textContent).toContain(taskUuid(5099))
  expect(document.body.textContent).toContain('跨页节点')
  expect(document.body.textContent).toContain('1234567890123456789012345678901234567890')
  expect(document.body.textContent).toContain('<img src=x onerror=alert(1)> 中文🙂')
  expect(document.querySelector('img[src="x"]')).toBeNull()
  expect(document.body.textContent).toContain('是（只读标记）')
})

it('Task列表仅激活时GET，空nodes展示275真实计数且拥有者筛选走服务器', async () => {
  vi.spyOn(tasksApi, 'list').mockResolvedValue(taskPage())
  wrapper = mount(TaskPanel, {
    attachTo: document.body,
    props: { active: false },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  expect(tasksApi.list).not.toHaveBeenCalled()
  await wrapper.setProps({ active: true })
  await flushPromises()
  expect(document.body.textContent).toContain('275')
  await click('仅查看此拥有者')
  expect(tasksApi.list).toHaveBeenLastCalledWith(
    { page_size: 20, operator_user_id: taskUuid(80000) },
    expect.any(AbortSignal),
  )
  await click('清除拥有者筛选')
  expect(tasksApi.list).toHaveBeenLastCalledWith({ page_size: 20 }, expect.any(AbortSignal))
})

it('列表有数据后403清除缓存，503不显示假空成功，可重新读取', async () => {
  vi.spyOn(tasksApi, 'list')
    .mockResolvedValueOnce(taskPage())
    .mockRejectedValueOnce(new TaskApiError(403, 'PERMISSION_DENIED', '读取权限已撤销'))
    .mockRejectedValueOnce(new TaskApiError(503, 'UNAVAILABLE', '服务暂不可用'))
    .mockResolvedValueOnce({ ...taskPage(), items: [], next_cursor: null })
  wrapper = mount(TaskPanel, {
    attachTo: document.body,
    props: { active: true },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  await click('重新读取首页')
  expect(document.body.textContent).toContain('旧数据已清除')
  expect(document.body.textContent).not.toContain(taskUuid(10000))
  await click('重新读取首页')
  expect(document.body.textContent).toContain('服务暂不可用')
  expect(document.body.textContent).not.toContain('当前范围没有符合条件的任务')
  await click('重新读取首页')
  expect(document.body.textContent).toContain('当前范围没有符合条件的任务')
})

it('详情观察到新版本时取消旧列表读取，迟到旧响应和旧详情不能倒退版本', async () => {
  let finish!: (page: ReturnType<typeof taskPage>) => void
  let pendingSignal!: AbortSignal
  vi.spyOn(tasksApi, 'list')
    .mockResolvedValueOnce(taskPage())
    .mockImplementationOnce((_query, signal) => {
      pendingSignal = signal!
      return new Promise((resolve) => {
        finish = resolve
      })
    })
  wrapper = mount(TaskPanel, {
    attachTo: document.body,
    props: { active: true },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  await click('重新读取首页')
  const detail = wrapper.findComponent(TaskDetails)
  const fresh = { ...taskFixture(taskUuid(10000), 0), revision: 7 }
  detail.vm.$emit('updated', fresh)
  await flushPromises()
  expect(pendingSignal.aborted).toBe(true)
  expect(document.body.textContent).toContain('任务版本已更新')
  finish(taskPage())
  detail.vm.$emit('updated', { ...fresh, revision: 2 })
  await flushPromises()
  const row = wrapper.find('.task-list .el-table__body tr')
  expect(row.text()).toContain('7')
  expect(row.text()).not.toContain('275')
})
