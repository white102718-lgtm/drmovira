import { ruleRecoveryApi } from '@/api/orbit/rule-recovery'
vi.mock('@/api/orbit/rule-recovery', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rule-recovery')>()),
  ruleRecoveryApi: { get: vi.fn() },
}))
/** 父页路由/认证/恢复协议挂载；List与Editor替身不计真实HTTP或三视口。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { reactive, defineComponent } from 'vue'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'
import ElementPlus from 'element-plus'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Page from '@/views/orbit/rules/index.vue'
const holder = vi.hoisted(() => ({ user: null as any }))
vi.mock('@/store/modules/user', () => ({ default: () => holder.user }))
const refresh = vi.fn()
const List = defineComponent({
  name: 'RuleList',
  props: ['permissionCodes', 'contextKey', 'pendingAction'],
  emits: ['create', 'edit', 'pendingAction'],
  setup(_, { expose }) {
    expose({ refresh })
    return {}
  },
  template: '<section>原列表筛选保留<input aria-label="局部筛选" /></section>',
})
const Editor = defineComponent({
  name: 'RuleEditor',
  props: ['ruleId', 'contextKey', 'permissionCodes', 'pendingIntent'],
  emits: ['pendingIntent', 'saved', 'close'],
  template: '<section>实际受控编辑器</section>',
})
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
let w: VueWrapper | undefined, router: ReturnType<typeof createRouter>
beforeEach(() => {
  holder.user = reactive({
    id: '1',
    getInfo: vi.fn().mockResolvedValue(undefined),
    token: 'token-a',
    permissions: ['rules.read', 'rules.create', 'rules.edit'],
  })
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 1,
    tenant_id: id(99),
    csrf_token: 'real-recovery-csrf-token',
  })
  refresh.mockReset()
  refresh.mockResolvedValue(undefined)
})
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
})
async function render(query = '') {
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/orbit/rules', component: Page },
      { path: '/other', component: { template: '<p>其它页面</p>' } },
    ],
  })
  await router.push('/orbit/rules' + query)
  await router.isReady()
  w = mount(RouterView, {
    attachTo: document.body,
    global: { plugins: [ElementPlus, router], stubs: { RuleList: List, RuleEditor: Editor } },
  })
  await flushPromises()
  return w
}
const list = () => w!.findComponent(List),
  editor = () => w!.findComponent(Editor)
function button(text: string) {
  const b = w!.findAll('button').find((x) => x.text() === text)
  expect(b, text).toBeTruthy()
  return b!
}
const pending = () => ({
  kind: 'SAVE',
  intent: {
    context: JSON.stringify([editor().props('contextKey'), id()]),
    action: 'UPDATE',
    ruleId: id(),
    body: { name: '不应跨actor展示的原正文' },
    key: 'same-key',
    ifMatch: '"3"',
  },
})
it('List→创建路由→返回保留同一列表与原本地筛选', async () => {
  await render()
  await list().find('input').setValue('未提交筛选')
  const instance = list().element
  list().vm.$emit('create', { csrf_token: 'actual' })
  await flushPromises()
  expect(router.currentRoute.value.query).toEqual({ mode: 'create' })
  expect(editor().props('ruleId')).toBeNull()
  editor().vm.$emit('close')
  await flushPromises()
  expect(router.currentRoute.value.query).toEqual({})
  expect(list().element).toBe(instance)
  expect(list().find('input').element).toHaveProperty('value', '未提交筛选')
})
it('编辑List真实rule.id放query，保存回列表显式refresh不重建列表', async () => {
  await render()
  const instance = list().element
  list().vm.$emit('edit', { id: id() }, { csrf_token: 'actual' })
  await flushPromises()
  expect(router.currentRoute.value.query).toEqual({ mode: 'edit', rule_id: id() })
  editor().vm.$emit('saved', { id: id() })
  await flushPromises()
  expect(router.currentRoute.value.query).toEqual({})
  expect(refresh).toHaveBeenCalledTimes(1)
  expect(list().element).toBe(instance)
})
it('edit-only直达不挂List/不探read，真实权限传给Editor', async () => {
  holder.user.permissions = ['rules.edit']
  await render('?mode=edit&rule_id=' + id())
  expect(list().exists()).toBe(false)
  expect(editor().props('permissionCodes')).toEqual(['rules.edit'])
  expect(editor().props('ruleId')).toBe(id())
})
it('create-only不用rules.read，父入口开真实CREATE模式', async () => {
  holder.user.permissions = ['rules.create']
  await render()
  expect(list().exists()).toBe(false)
  await button('创建规则').trigger('click')
  await flushPromises()
  expect(editor().exists()).toBe(true)
  expect(editor().props('ruleId')).toBeNull()
})
it.each([
  '?mode=edit',
  '?mode=edit&rule_id=not-uuid',
  '?mode=create&rule_id=' + id(),
  '?mode=edit&rule_id=' + id() + '&rule_id=' + id(2),
  '?mode=wrong',
])('严格query %s不创建伪编辑上下文', async (query) => {
  await render(query)
  expect(editor().exists()).toBe(false)
  expect(w!.text()).toContain('规则编辑地址无效')
})
it('父保存pending跨关闭恢复原mode/rule，不丢原业务意图或发新写', async () => {
  await render('?mode=edit&rule_id=' + id())
  const original = pending()
  editor().vm.$emit('pendingIntent', original)
  editor().vm.$emit('close')
  await flushPromises()
  expect(router.currentRoute.value.query).toEqual({})
  expect(w!.find('section[inert]').exists()).toBe(true)
  list().vm.$emit('create', {})
  await flushPromises()
  expect(router.currentRoute.value.query).toEqual({})
  await button('恢复原未确认请求').trigger('click')
  await flushPromises()
  expect(editor().props('pendingIntent')).toEqual(original)
  expect(router.currentRoute.value.query).toEqual({ mode: 'edit', rule_id: id() })
})
it('非空token刷新不换actor生命周期，手动恢复可更新传输认证', async () => {
  await render('?mode=edit&rule_id=' + id())
  const context = editor().props('contextKey')
  const original = pending()
  editor().vm.$emit('pendingIntent', original)
  holder.user.token = 'token-refreshed'
  await flushPromises()
  expect(editor().props('contextKey')).toBe(context)
  expect(editor().props('contextKey')).not.toContain('token-')
  expect(editor().props('pendingIntent')).toEqual(original)
})
it('跨actor隐藏编辑器与原正文，原未知阻新写且不重发', async () => {
  await render('?mode=edit&rule_id=' + id())
  editor().vm.$emit('pendingIntent', pending())
  holder.user.id = 'native-other'
  await flushPromises()
  expect(editor().exists()).toBe(false)
  expect(w!.text()).toContain('其它认证生命周期')
  expect(w!.text()).not.toContain('不应跨actor展示')
  await button('返回规则列表').trigger('click')
  await flushPromises()
  list().vm.$emit('create', {})
  expect(editor().exists()).toBe(false)
  expect(refresh).not.toHaveBeenCalled()
})
it('同actor非权限清空变化仍保留生命周期，退出清空换代且不恢复旧意图', async () => {
  await render('?mode=edit&rule_id=' + id())
  const context = editor().props('contextKey')
  editor().vm.$emit('pendingIntent', pending())
  holder.user.permissions = ['rules.edit']
  await flushPromises()
  expect(editor().props('contextKey')).toBe(context)
  holder.user.permissions = []
  await flushPromises()
  expect(editor().exists()).toBe(false)
  holder.user.permissions = ['rules.edit']
  await flushPromises()
  expect(editor().exists()).toBe(false)
})
it('pending清除后保存成功刷新，未知未确认时不主动refresh', async () => {
  await render('?mode=edit&rule_id=' + id())
  editor().vm.$emit('pendingIntent', pending())
  editor().vm.$emit('close')
  await flushPromises()
  expect(refresh).not.toHaveBeenCalled()
  await button('恢复原未确认请求').trigger('click')
  await flushPromises()
  editor().vm.$emit('pendingIntent', null)
  editor().vm.$emit('saved', {})
  await flushPromises()
  expect(refresh).toHaveBeenCalledTimes(1)
})
it('RuleRuns不冒充全局触发记录/5次预览，不加未实现菜单', async () => {
  await render()
  expect(w!.text()).toContain('/rule-hits')
  expect(w!.text()).not.toContain('调度后5次预览尚未接入')
})

it('迟到旧actor pending事件不能盖成新身份', async () => {
  await render('?mode=edit&rule_id=' + id())
  const previous = editor(),
    value = pending()
  holder.user.id = 'new-actor'
  await flushPromises()
  previous.vm.$emit('pendingIntent', value)
  await flushPromises()
  expect(w!.text()).not.toContain('有未确认的规则请求')
  expect(editor().props('pendingIntent')).toBeNull()
})

it('父完整保留SCOPE原请求，返回后只恢复原编辑目标', async () => {
  await render('?mode=edit&rule_id=' + id())
  const key = editor().props('contextKey')
  const value = {
    kind: 'SCOPE',
    intent: {
      context: JSON.stringify([key, 'UPDATE', id(), id(2), id(3)]),
      intent: {
        body: {
          action: 'UPDATE',
          rule_id: id(),
          ownership: { owner_user_id: id(2), owner_team_id: id(3) },
          selection: { mode: 'IDS', account_ids: [id(4)], filter: null },
        },
        auth: { csrf_token: 'session-csrf', idempotency_key: 'scope-old-key', if_match: '"3"' },
      },
    },
  }
  editor().vm.$emit('pendingIntent', value)
  editor().vm.$emit('close')
  await flushPromises()
  await button('恢复原未确认请求').trigger('click')
  await flushPromises()
  expect(editor().props('pendingIntent')).toEqual(value)
  expect(router.currentRoute.value.query).toEqual({ mode: 'edit', rule_id: id() })
})

const actionPending = () => ({
  principal: { actor_id: 1, tenant_id: id(99) },
  context: list().props('contextKey'),
  action: 'ARCHIVE',
  rule: { id: id(), name: '私有动作名' },
  body: { reason: '私有原因' },
  auth: { csrf_token: 'current', idempotency_key: 'same-action-key', if_match: '"3"' },
})
it('ACTION父接管不同Editor envelope，真实:key重挂载后保留原请求而不自动重发', async () => {
  await render()
  const old = list(),
    original = actionPending()
  old.vm.$emit('pendingAction', original)
  await flushPromises()
  expect(list().props('pendingAction')).toEqual(original)
  expect(w!.find('section[inert]').exists()).toBe(false)
  holder.user.id = 'another'
  await flushPromises()
  expect(list().vm).not.toBe(old.vm)
  expect(list().props('pendingAction')).toEqual(original)
  expect(w!.text()).not.toContain('私有动作名')
  expect(w!.text()).toContain('其它认证生命周期')
  list().vm.$emit('create')
  await flushPromises()
  expect(editor().exists()).toBe(false)
})
it('ACTION未确认阻SPA离开，原确认成功清父后才可离开', async () => {
  await render()
  list().vm.$emit('pendingAction', actionPending())
  await flushPromises()
  await router.push('/other')
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/orbit/rules')
  expect(w!.text()).toContain('请先在本页确认结果后再离开')
  list().vm.$emit('pendingAction', null)
  await flushPromises()
  await router.push('/other')
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/other')
})

it('已发ACTION在read撤回但原archive仍有效时保留List恢复入口，不强加read', async () => {
  await render()
  const original = actionPending(),
    old = list().element
  list().vm.$emit('pendingAction', original)
  await flushPromises()
  holder.user.permissions = ['rules.archive']
  await flushPromises()
  expect(list().exists()).toBe(true)
  expect(list().element).toBe(old)
  expect(list().props('pendingAction')).toEqual(original)
  expect(list().props('permissionCodes')).toEqual(['rules.archive'])
  expect(editor().exists()).toBe(false)
})

it('另一标签登录入口保留本页，实际双context复核只重绑UI不提交', async () => {
  await render()
  const original = actionPending()
  list().vm.$emit('pendingAction', original)
  await flushPromises()
  const login = w!.get('a[href="/login"]')
  expect(login.attributes()).toMatchObject({ target: '_blank', rel: 'noopener' })
  holder.user.id = '2'
  await flushPromises()
  vi.mocked(holder.user.getInfo).mockImplementation(async () => {
    holder.user.id = '1'
  })
  vi.mocked(ruleRecoveryApi.get).mockClear()
  await button('重新验证当前身份（不提交）').trigger('click')
  await flushPromises()
  expect(ruleRecoveryApi.get).toHaveBeenCalledTimes(2)
  expect(holder.user.getInfo).toHaveBeenCalledTimes(1)
  const restored = list().props('pendingAction')
  expect(restored.context).toBe(list().props('contextKey'))
  expect(restored.body).toEqual(original.body)
  expect(restored.auth).toEqual(original.auth)
  expect(restored.principal).toEqual(original.principal)
  expect(w!.text()).toContain('尚未提交')
})
it.each([
  { actor_id: 2, tenant_id: id(99) },
  { actor_id: 1, tenant_id: id(98) },
])('非原主体%j不刷新UI或重绑未知请求', async (principal) => {
  await render()
  const original = actionPending()
  list().vm.$emit('pendingAction', original)
  await flushPromises()
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    ...principal,
    csrf_token: 'different-principal-csrf-token',
  })
  await button('重新验证当前身份（不提交）').trigger('click')
  await flushPromises()
  expect(holder.user.getInfo).not.toHaveBeenCalled()
  expect(list().props('pendingAction')).toEqual(original)
  expect(w!.text()).toContain('RULE_RECOVERY_PRINCIPAL_CHANGED')
  expect(w!.text()).not.toContain('私有原因')
})

it.each(['SAVE', 'SCOPE'] as const)(
  '%s同主体证明后只更新技术context，原业务与CAS不变',
  async (kind) => {
    await render('?mode=edit&rule_id=' + id())
    const business = {
      action: 'UPDATE',
      rule_id: id(),
      ownership: { owner_user_id: id(2), owner_team_id: id(3) },
    }
    const fixed =
      kind === 'SAVE'
        ? { kind, intent: { ...pending().intent, principal: { actor_id: 1, tenant_id: id(99) } } }
        : {
            kind,
            intent: {
              principal: { actor_id: 1, tenant_id: id(99) },
              context: JSON.stringify([editor().props('contextKey'), 'UPDATE', id(), id(2), id(3)]),
              intent: {
                body: business,
                auth: {
                  csrf_token: 'old-csrf',
                  idempotency_key: 'same-scope-key',
                  if_match: '"3"',
                },
              },
            },
          }
    editor().vm.$emit('pendingIntent', fixed)
    await flushPromises()
    holder.user.token = ''
    await flushPromises()
    holder.user.token = 'reauthenticated'
    await flushPromises()
    const oldContext = list().props('contextKey')
    await button('重新验证当前身份（不提交）').trigger('click')
    await flushPromises()
    const restored = editor().props('pendingIntent')
    if (kind === 'SAVE') {
      expect(restored.intent.context).toBe(JSON.stringify([oldContext, id()]))
      expect(restored.intent.body).toEqual((fixed as any).intent.body)
      expect(restored.intent.key).toBe('same-key')
      expect(restored.intent.ifMatch).toBe('"3"')
    } else {
      expect(restored.intent.context).toBe(
        JSON.stringify([oldContext, 'UPDATE', id(), id(2), id(3)]),
      )
      expect(restored.intent.intent).toEqual((fixed as any).intent.intent)
    }
    expect(w!.text()).toContain('尚未提交')
  },
)
