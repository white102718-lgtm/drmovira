import { defineComponent, h, reactive } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import LaunchPage from '@/views/orbit/launch/index.vue'
import { launchApi } from '@/api/orbit/launch'
import { ReferenceApiError } from '@/api/orbit/references'
const state = vi.hoisted(() => ({ user: { permissions: [] as string[] } }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
vi.mock('@/store/modules/user', () => ({ default: () => state.user }))
const TaskStub = defineComponent({
  name: 'TaskPanel',
  props: ['active'],
  setup: (props) => () => h('section', { 'data-test': 'task-active' }, String(props.active)),
})
const TemplateStub = defineComponent({
  name: 'TemplatesPanel',
  props: ['active'],
  emits: ['blocked', 'applied', 'failure'],
  setup: () => () => h('div'),
})
const DraftStub = defineComponent({
  name: 'DraftEditor',
  props: ['modelValue'],
  emits: ['update:modelValue', 'locked'],
  setup: () => () => h('div'),
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  sessionStorage.clear()
  state.user = reactive({ permissions: ['tasks.read'] })
  vi.spyOn(launchApi, 'capabilities').mockResolvedValue({
    actions: [],
    csrf_token: 'fixture',
    actor_user_id: 'actor',
    actor_team_id: 'team',
    actor_label: '本人',
    data_role: 'USER',
  })
  vi.spyOn(launchApi, 'list').mockResolvedValue({
    items: [],
    next_cursor: null,
    scope_version: 1,
    data_as_of: '2026-11-08T00:00:00Z',
  })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start() {
  wrapper = mount(LaunchPage, {
    attachTo: document.body,
    global: {
      plugins: [ElementPlus],
      stubs: { TaskPanel: TaskStub, TemplatesPanel: TemplateStub, DraftEditor: DraftStub },
    },
  })
  await flushPromises()
}
it('仅tasks.read可打开真实任务入口，不调用launch.read，撤权即卸载任务内容', async () => {
  await start()
  expect(wrapper!.find('[data-test="task-active"]').text()).toBe('true')
  expect(launchApi.capabilities).not.toHaveBeenCalled()
  expect(launchApi.list).not.toHaveBeenCalled()
  const tabs = wrapper!.findAll('[role="tab"]')
  expect(tabs.find((tab) => tab.text() === '执行任务')?.attributes('aria-selected')).toBe('true')
  const planTab = tabs.find((tab) => tab.text() === '创建广告')!
  expect(planTab.classes()).toContain('is-disabled')
  await planTab.trigger('click')
  await flushPromises()
  expect(wrapper!.find('[data-test="task-active"]').text()).toBe('true')
  expect(launchApi.list).not.toHaveBeenCalled()
  state.user.permissions = []
  await flushPromises()
  expect(wrapper!.find('[data-test="task-active"]').exists()).toBe(false)
  expect(wrapper!.text()).toContain('旧任务数据已清除')
})
it('有launch.read但无tasks.read不显示任务tab，原布局和模板入口保留', async () => {
  state.user.permissions = ['launch.read']
  await start()
  expect(wrapper!.findAll('[role="tab"]').map((tab) => tab.text())).toEqual([
    '创建广告',
    '模板管理',
  ])
  expect(launchApi.list).toHaveBeenCalledTimes(1)
})
it('父菜单伪含launch.read但实际动作403时，仅有tasks.read才安全降级任务', async () => {
  state.user.permissions = ['launch.read', 'tasks.read']
  vi.mocked(launchApi.capabilities).mockRejectedValueOnce(
    new ReferenceApiError(403, 'PERMISSION_DENIED', '动作未授权'),
  )
  await start()
  expect(wrapper!.find('[data-test="task-active"]').text()).toBe('true')
  expect(wrapper!.text()).toContain('已切换任务查询')
  const planTab = wrapper!.findAll('[role="tab"]').find((tab) => tab.text() === '创建广告')!
  expect(planTab.classes()).toContain('is-disabled')
  await planTab.trigger('click')
  await flushPromises()
  expect(wrapper!.find('[data-test="task-active"]').text()).toBe('true')
  expect(launchApi.list).not.toHaveBeenCalled()
  expect(launchApi.capabilities).toHaveBeenCalledTimes(1)
})
it.each([403, 503])('无Task读取权限或非403错误不能凭失败授予任务入口：%s', async (status) => {
  state.user.permissions = status === 403 ? ['launch.read'] : ['launch.read', 'tasks.read']
  vi.mocked(launchApi.list).mockRejectedValueOnce(
    new ReferenceApiError(status, 'UNAVAILABLE', '计划读取暂不可用'),
  )
  await start()
  expect(wrapper!.text()).not.toContain('已切换任务查询')
  expect(wrapper!.text()).toContain('计划读取暂不可用')
  const task = wrapper!.find('[data-test="task-active"]')
  expect(task.exists() ? task.text() : 'false').toBe('false')
})
it('计划动作随后403时清除原列表与创建能力，保留Task入口且不再重读被禁计划', async () => {
  state.user.permissions = ['launch.read', 'tasks.read']
  vi.mocked(launchApi.list)
    .mockResolvedValueOnce({
      items: [
        {
          id: 'old',
          name: '旧计划不应保留',
          account_ids: [],
          asset_ids: [],
          state: 'DRAFT',
          revision: 1,
          updated_at: '2026-11-08T00:00:00Z',
        } as never,
      ],
      next_cursor: 'old-cursor',
      scope_version: 1,
      data_as_of: '2026-11-08T00:00:00Z',
    })
    .mockRejectedValueOnce(new ReferenceApiError(403, 'PERMISSION_DENIED', '动作已撤销'))
  await start()
  expect(wrapper!.text()).toContain('旧计划不应保留')
  await wrapper!
    .findAll('button')
    .find((button) => button.text() === '重新读取首页')!
    .trigger('click')
  await flushPromises()
  expect(wrapper!.text()).not.toContain('旧计划不应保留')
  expect(wrapper!.text()).not.toContain('下一页计划')
  expect(wrapper!.find('[data-test="task-active"]').text()).toBe('true')
  expect(
    wrapper!
      .findAll('[role="tab"]')
      .find((tab) => tab.text() === '创建广告')!
      .classes(),
  ).toContain('is-disabled')
})
it('原草稿待保存门禁继续阻止切任务，关闭后才可切换', async () => {
  state.user.permissions = ['*:*:*']
  await start()
  wrapper!.findComponent(DraftStub).vm.$emit('update:modelValue', true)
  await flushPromises()
  await wrapper!
    .findAll('[role="tab"]')
    .find((tab) => tab.text() === '执行任务')!
    .trigger('click')
  await flushPromises()
  expect(wrapper!.find('[data-test="task-active"]').text()).toBe('false')
  wrapper!.findComponent(DraftStub).vm.$emit('update:modelValue', false)
  await flushPromises()
  await wrapper!
    .findAll('[role="tab"]')
    .find((tab) => tab.text() === '执行任务')!
    .trigger('click')
  await flushPromises()
  expect(wrapper!.find('[data-test="task-active"]').text()).toBe('true')
})
