/** 父接线实际ElementPlus测试；子组件用具名替身触发合同事件，不是平台/后端受理验收。 */
import { defineComponent, h, reactive } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import LaunchPage from '@/views/orbit/launch/index.vue'
import { launchApi } from '@/api/orbit/launch'
import { ReferenceApiError } from '@/api/orbit/references'
import { plan, caps } from './plan-validation-fixtures'
import { taskFixture } from './tasks-fixtures'
const state = vi.hoisted(() => ({
  user: { permissions: [] as string[] },
  leave: undefined as undefined | (() => boolean),
}))
vi.mock('vue-router', () => ({
  onBeforeRouteLeave: vi.fn((callback) => {
    state.leave = callback
  }),
}))
vi.mock('@/store/modules/user', () => ({ default: () => state.user }))
const DraftStub = defineComponent({
  name: 'DraftEditor',
  props: [
    'modelValue',
    'plan',
    'readOnly',
    'identityReadAllowed',
    'focusField',
    'metricReadAllowed',
    'accountContextKey',
  ],
  emits: ['update:modelValue', 'saved', 'locked', 'closed'],
  setup: () => () => h('div'),
})
const ValidationStub = defineComponent({
  name: 'PlanValidationDialog',
  props: ['modelValue', 'plan', 'capabilities', 'validationAvailable', 'executeAvailable'],
  emits: ['update:modelValue', 'locked', 'locate', 'accepted'],
  setup: () => () => h('div'),
})
const TaskDetailStub = defineComponent({
  name: 'TaskDetails',
  props: ['modelValue', 'taskId', 'active'],
  emits: ['update:modelValue'],
  setup: () => () => h('div'),
})
const TemplateStub = defineComponent({
  name: 'TemplatesPanel',
  props: ['active', 'metricReadAllowed', 'metricContextKey'],
  emits: ['blocked', 'applied', 'failure'],
  setup: () => () => h('div'),
})
const TaskPanelStub = defineComponent({
  name: 'TaskPanel',
  props: ['active'],
  setup: () => () => h('div'),
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  sessionStorage.clear()
  state.user = reactive({ permissions: ['launch.read', 'accounts.read', 'tasks.read'] })
  state.leave = undefined
  vi.spyOn(launchApi, 'capabilities').mockResolvedValue({
    ...caps(),
    actions: ['create', 'edit', 'execute', 'publish'],
    validation_available: true,
    execution_available: false,
  })
  vi.spyOn(launchApi, 'list').mockResolvedValue({
    items: [plan()],
    next_cursor: null,
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 1,
  })
  vi.spyOn(launchApi, 'get').mockResolvedValue({ ...plan(), revision: 9 })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  sessionStorage.clear()
})
async function start() {
  wrapper = mount(LaunchPage, {
    attachTo: document.body,
    global: {
      plugins: [ElementPlus],
      stubs: {
        DraftEditor: DraftStub,
        PlanValidationDialog: ValidationStub,
        TaskDetails: TaskDetailStub,
        TemplatesPanel: TemplateStub,
        TaskPanel: TaskPanelStub,
      },
    },
  })
  await flushPromises()
  // 新版默认进入创建广告；列表回归从草稿管理入口关闭内嵌编辑后继续。
  const initialEditor = wrapper!.findComponent(DraftStub)
  if (initialEditor.exists() && initialEditor.props('modelValue')) {
    initialEditor.vm.$emit('update:modelValue', false)
    await flushPromises()
  }
}
const validation = () => wrapper!.findComponent(ValidationStub)
it('指标目录权限只从原monitor.read透传给计划与模板，权限变动同步换context', async () => {
  await start()
  const draft = wrapper!.findComponent(DraftStub)
  const templates = wrapper!.findComponent(TemplateStub)
  expect(draft.props('metricReadAllowed')).toBe(false)
  expect(templates.props('metricReadAllowed')).toBe(false)
  const previous = draft.props('accountContextKey')
  state.user.permissions.push('monitor.read')
  await flushPromises()
  expect(draft.props('metricReadAllowed')).toBe(true)
  expect(templates.props('metricReadAllowed')).toBe(true)
  expect(draft.props('accountContextKey')).not.toBe(previous)
  expect(templates.props('metricContextKey')).toBe(draft.props('accountContextKey'))
  state.user.permissions = ['launch.read']
  await flushPromises()
  expect(draft.props('metricReadAllowed')).toBe(false)
  expect(templates.props('metricReadAllowed')).toBe(false)
})
const editor = () => wrapper!.findComponent(DraftStub)
const button = (name: string) => wrapper!.findAll('button').find((row) => row.text() === name)!
async function click(name: string) {
  expect(button(name), name).toBeTruthy()
  await button(name).trigger('click')
  await flushPromises()
}
async function open() {
  await click('投放预检')
  expect(validation().props('modelValue')).toBe(true)
}
it('旧caps无availability默认关闭预检，明确依赖且不发head或任何假受理', async () => {
  vi.mocked(launchApi.capabilities).mockResolvedValue(caps())
  await start()
  expect(button('投放预检').attributes('disabled')).toBeDefined()
  expect(wrapper!.text()).toContain('预检依赖尚未就绪')
  await click('投放预检')
  expect(launchApi.get).not.toHaveBeenCalled()
  expect(validation().exists()).toBe(false)
})
it('按新caps和GET当前head9打开，冻结请求上下文且execute默认关闭，不猜7+1', async () => {
  await start()
  await open()
  expect(validation().props('plan').revision).toBe(9)
  expect(validation().props('validationAvailable')).toBe(true)
  expect(validation().props('executeAvailable')).toBe(false)
  expect(launchApi.capabilities).toHaveBeenCalledTimes(2)
  expect(launchApi.get).toHaveBeenCalledWith(plan().id)
  const old = validation().props('capabilities')
  vi.mocked(launchApi.capabilities).mockResolvedValue({
    ...caps(),
    csrf_token: 'different-context',
    validation_available: false,
  })
  await click('查询计划')
  expect(validation().props('capabilities')).toEqual(old)
  expect(launchApi.capabilities).toHaveBeenCalledTimes(2)
})
it('点击前真实权限/依赖撤回，先刷新caps阻止后续head与预检', async () => {
  await start()
  vi.mocked(launchApi.capabilities).mockResolvedValueOnce({
    ...caps(),
    actions: [],
    validation_available: false,
  })
  await click('投放预检')
  expect(launchApi.get).not.toHaveBeenCalled()
  expect(validation().exists()).toBe(false)
  expect(wrapper!.text()).toContain('预检依赖或编辑权限已变化')
})
it('子未知写入锁阻止关闭/切tab/路由离开/刷新，解锁并明确关闭后恢复', async () => {
  await start()
  await open()
  validation().vm.$emit('locked', true)
  await flushPromises()
  validation().vm.$emit('update:modelValue', false)
  await flushPromises()
  expect(validation().props('modelValue')).toBe(true)
  expect(state.leave!()).toBe(false)
  expect(button('创建广告').attributes('disabled')).toBeDefined()
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  const tab = wrapper!.findAll('[role="tab"]').find((row) => row.text() === '执行任务')!
  await tab.trigger('click')
  await flushPromises()
  expect(tab.attributes('aria-selected')).toBe('false')
  validation().vm.$emit('locked', false)
  validation().vm.$emit('update:modelValue', false)
  await flushPromises()
  expect(validation().props('modelValue')).toBe(false)
  expect(state.leave!()).toBe(true)
  await tab.trigger('click')
  await flushPromises()
  expect(tab.attributes('aria-selected')).toBe('true')
})
it('head读取失败保留列表；取消读取后迟到旧结果不能弹开预检', async () => {
  await start()
  vi.mocked(launchApi.get).mockRejectedValueOnce(
    new ReferenceApiError(503, 'READ_UNAVAILABLE', '当前head未读取'),
  )
  await click('投放预检')
  expect(wrapper!.text()).toContain('当前head未读取')
  expect(validation().exists()).toBe(false)
  let resolve!: (value: ReturnType<typeof plan>) => void
  vi.mocked(launchApi.get).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  await click('投放预检')
  expect(wrapper!.text()).toContain('正在读取服务器当前计划')
  await click('取消本地读取')
  resolve({ ...plan(), revision: 99 })
  await flushPromises()
  expect(validation().exists()).toBe(false)
  expect(button('投放预检').attributes('disabled')).toBeUndefined()
})
it('同版本字段定位再次GEThead，传真实Pointer给编辑器，来源权限独立传递', async () => {
  await start()
  await open()
  const path = '/campaigns/0/adsets/0/ads/0/title'
  validation().vm.$emit('locate', path, ['campaigns', '0', 'adsets', '0', 'ads', '0', 'title'])
  await flushPromises()
  expect(launchApi.get).toHaveBeenCalledTimes(2)
  expect(validation().props('modelValue')).toBe(false)
  expect(editor().props('modelValue')).toBe(true)
  expect(editor().props('focusField')).toEqual({
    path,
    segments: ['campaigns', '0', 'adsets', '0', 'ads', '0', 'title'],
    revision: 9,
  })
  expect(editor().props('identityReadAllowed')).toBe(true)
  expect(editor().props('readOnly')).toBe(false)
})
it('错误源head已变化不按旧树索引定位；非法Pointer不发GET', async () => {
  await start()
  await open()
  validation().vm.$emit('locate', '/name', ['different'])
  await flushPromises()
  expect(launchApi.get).toHaveBeenCalledTimes(1)
  expect(wrapper!.text()).toContain('不符合JSON Pointer')
  vi.mocked(launchApi.get).mockResolvedValueOnce({ ...plan(), revision: 10 })
  validation().vm.$emit('locate', '/campaigns/0/objective', ['campaigns', '0', 'objective'])
  await flushPromises()
  expect(editor().props('modelValue')).toBe(false)
  expect(validation().props('modelValue')).toBe(true)
  expect(wrapper!.text()).toContain('旧字段位置可能陈旧')
  expect(wrapper!.text()).toContain('/campaigns/0/objective')
})
it('仅实际Task合同事件接力既有详情，不把allocation/runtime UUID当Task', async () => {
  await start()
  await open()
  validation().vm.$emit('accepted', { id: plan().id, task_id: null, state: 'SUCCEEDED' })
  await flushPromises()
  expect(validation().props('modelValue')).toBe(true)
  expect(wrapper!.text()).toContain('未打开伪任务')
  expect(wrapper!.findComponent(TaskDetailStub).props('modelValue')).toBe(false)
  const task = taskFixture()
  validation().vm.$emit('locked', true)
  await flushPromises()
  validation().vm.$emit('accepted', task)
  await flushPromises()
  expect(validation().props('modelValue')).toBe(false)
  expect(wrapper!.findComponent(TaskDetailStub).props()).toMatchObject({
    modelValue: true,
    taskId: task.id,
    active: true,
  })
  expect(
    wrapper!
      .findAll('[role="tab"]')
      .find((row) => row.text() === '执行任务')
      ?.attributes('aria-selected'),
  ).toBe('true')
  expect(wrapper!.text()).not.toContain('广告创建成功')
  state.user.permissions = ['launch.read']
  await flushPromises()
  expect(wrapper!.findComponent(TaskDetailStub).exists()).toBe(false)
})
it('无tasks.read不因202授予读取，保留真实受理ID与权限提示', async () => {
  state.user.permissions = ['launch.read']
  await start()
  await open()
  validation().vm.$emit('accepted', taskFixture())
  await flushPromises()
  expect(wrapper!.findComponent(TaskDetailStub).exists()).toBe(false)
  expect(wrapper!.text()).toContain('当前没有 tasks.read 权限')
  expect(wrapper!.text()).toContain(taskFixture().id)
})
it('只读与编辑入口都传真实accounts.read，不能用launch动作冒来源授权', async () => {
  state.user.permissions = ['launch.read']
  await start()
  await click('详情')
  expect(editor().props('readOnly')).toBe(true)
  expect(editor().props('identityReadAllowed')).toBe(false)
  editor().vm.$emit('update:modelValue', false)
  await flushPromises()
  state.user.permissions.push('accounts.read')
  await click('编辑草稿')
  expect(editor().props('readOnly')).toBe(false)
  expect(editor().props('identityReadAllowed')).toBe(true)
})
