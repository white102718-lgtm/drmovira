import { defineComponent, h } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import LaunchPage from '@/views/orbit/launch/index.vue'
import { launchApi, type LaunchPlan } from '@/api/orbit/launch'
import { newDraft } from '@/api/orbit/launch-form'

vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
vi.mock('@/store/modules/user', () => ({ default: () => ({ permissions: [] }) }))

const TemplatesStub = defineComponent({
  name: 'TemplatesPanel',
  props: ['active'],
  emits: ['applied', 'blocked', 'failure'],
  setup: (props) => () => h('section', { 'data-test': 'template-state' }, String(props.active)),
})
const DraftStub = defineComponent({
  name: 'DraftEditor',
  props: ['modelValue'],
  emits: ['update:modelValue', 'locked'],
  setup: (props) => () => h('section', { 'data-test': 'draft-state' }, String(props.modelValue)),
})
let wrapper: VueWrapper
beforeEach(() => {
  sessionStorage.clear()
  vi.spyOn(launchApi, 'capabilities').mockResolvedValue({
    actor_user_id: 'owner',
    actor_team_id: 'team',
    actor_label: '本人',
    data_role: 'SUPER_ADMIN',
    csrf_token: 'memory-csrf',
    actions: ['create', 'edit'],
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
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start() {
  wrapper = mount(LaunchPage, {
    attachTo: document.body,
    global: {
      plugins: [ElementPlus],
      stubs: { TemplatesPanel: TemplatesStub, DraftEditor: DraftStub },
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
function tab(name: string) {
  const result = wrapper.findAll('[role="tab"]').find((element) => element.text() === name)
  expect(result).toBeTruthy()
  return result!
}

it('真实ElementPlus在成功apply后先同步内部tab再开抽屉，关闭后可重返模板继续归档', async () => {
  await start()
  await tab('模板管理').trigger('click')
  await flushPromises()
  const templates = wrapper.findComponent(TemplatesStub)
  expect(templates.props('active')).toBe(true)
  templates.vm.$emit('blocked', true)
  await flushPromises()
  const plan: LaunchPlan = {
    ...newDraft({ owner_user_id: 'owner', owner_team_id: 'team' }),
    id: 'real-applied-plan',
    revision: 1,
    state: 'DRAFT',
    created_at: '2026-11-08T00:00:00Z',
    updated_at: '2026-11-08T00:00:00Z',
  }
  // 模拟业务子组件仍在结束请求：先已确认结果，再撤销busy，不能依赖微任务偶然顺序。
  templates.vm.$emit('applied', plan)
  await flushPromises()
  expect(tab('创建广告').attributes('aria-selected')).toBe('true')
  expect(templates.props('active')).toBe(false)
  const editor = wrapper.findComponent(DraftStub)
  expect(editor.props('modelValue')).toBe(true)
  templates.vm.$emit('blocked', false)
  editor.vm.$emit('update:modelValue', false)
  await flushPromises()
  await tab('模板管理').trigger('click')
  await flushPromises()
  expect(tab('模板管理').attributes('aria-selected')).toBe('true')
  expect(templates.props('active')).toBe(true)
})

it('普通模板待确认结果及草稿打开时仍不能切页，成功内部切换标志不会遗留', async () => {
  await start()
  await tab('模板管理').trigger('click')
  await flushPromises()
  const templates = wrapper.findComponent(TemplatesStub)
  templates.vm.$emit('blocked', true)
  await flushPromises()
  await tab('创建广告').trigger('click')
  await flushPromises()
  expect(tab('模板管理').attributes('aria-selected')).toBe('true')
  expect(templates.props('active')).toBe(true)
  templates.vm.$emit('blocked', false)
  await flushPromises()
  await tab('创建广告').trigger('click')
  await flushPromises()
  const create = wrapper.findAll('button').find((button) => button.text() === '创建广告')!
  await create.trigger('click')
  await flushPromises()
  expect(wrapper.findComponent(DraftStub).props('modelValue')).toBe(true)
  await tab('模板管理').trigger('click')
  await flushPromises()
  expect(tab('创建广告').attributes('aria-selected')).toBe('true')
  expect(templates.props('active')).toBe(false)
})
