import { ruleRecoveryApi } from '@/api/orbit/rule-recovery'
vi.mock('@/api/orbit/rule-recovery', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rule-recovery')>()),
  ruleRecoveryApi: { get: vi.fn() },
}))
/** 原生ElementPlus+规则专属SDK替身；不计真实scope HTTP、容量或浏览器。 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElCheckbox, ElDialog, ElRadioGroup, ElSelect, ElOption } from 'element-plus'
import { ruleScopeOptionsApi } from '@/api/orbit/rule-scope-options'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Selector from '@/views/orbit/rules/RuleScopeSelector.vue'
import { RuleApiError } from '@/api/orbit/rules'
import { ruleEditorScopesApi as api, type ScopeMemberPage } from '@/api/orbit/rule-editor-scopes'
vi.mock('@/api/orbit/rule-editor-scopes', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rule-editor-scopes')>()),
  ruleEditorScopesApi: { accounts: vi.fn(), create: vi.fn(), members: vi.fn() },
}))
vi.mock('@/api/orbit/rule-scope-options', () => ({ ruleScopeOptionsApi: { options: vi.fn() } }))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const member = (n = 1) => ({ account_id: id(n), external_id: `000${n}`, name: `真实账户${n}` })
const page = (items = [member()], next_cursor: string | null = null): ScopeMemberPage => ({
  items,
  next_cursor,
  data_as_of: '2026-11-09T00:00:00Z',
  scope_version: 7,
})
const scope = () => ({
  id: id(10),
  count: 1,
  scope_version: 7,
  hash: 'a'.repeat(64),
  created_at: '2026-11-09T00:00:00Z',
})
const remoteOperator = (n = 20) => ({
  id: id(n),
  name: '真实操作者',
  team_id: id(3),
  team_name: '真实团队',
  active: false,
})
const remoteVendor = (n = 30) => ({
  id: id(n),
  name: '资料名称不是代称',
  alias: null,
  availability: 'UNAVAILABLE',
})
let wrapper: VueWrapper
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 1,
    tenant_id: id(99),
    csrf_token: 'actual-context-csrf-token',
  })
  vi.mocked(api.accounts).mockResolvedValue(page())
  vi.mocked(api.create).mockResolvedValue(scope())
  vi.mocked(api.members).mockResolvedValue(page())
  vi.mocked(ruleScopeOptionsApi.options).mockImplementation(
    async (query) =>
      ({
        ...page([]),
        items: query.kind === 'OPERATOR' ? [remoteOperator()] : [remoteVendor()],
      }) as never,
  )
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
async function render(props = {}) {
  wrapper = mount(Selector, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
    props: {
      modelValue: true,
      nativeActorId: 1,
      action: 'CREATE',
      ruleId: null,
      ownership: { owner_user_id: id(2), owner_team_id: id(3) },
      currentRuleRevision: null,
      csrfToken: 'actual-context-csrf-token',
      permissionCodes: ['rules.create'],
      contextKey: 'actor-session-a',
      ...props,
    },
  })
  await flushPromises()
  return wrapper
}
function button(label: string) {
  const found = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (item) => item.textContent?.trim() === label,
  )
  expect(found, label).toBeTruthy()
  return found!
}
async function click(label: string) {
  button(label).click()
  await flushPromises()
}
async function chooseMode(value: 'IDS' | 'FILTER') {
  wrapper.findComponent(ElRadioGroup).vm.$emit('update:modelValue', value)
  await flushPromises()
}
async function check(external = '0001') {
  const checkbox = wrapper
    .findAllComponents(ElCheckbox)
    .find(
      (item) =>
        item.props('ariaLabel') === `选择规则账户 ${external}` ||
        item.attributes('aria-label') === `选择规则账户 ${external}`,
    )
  expect(checkbox, external).toBeTruthy()
  checkbox!.vm.$emit('change', true)
  await flushPromises()
}
async function select(label: string, value: unknown) {
  const control = wrapper
    .findAllComponents(ElSelect)
    .find((item) => item.props('ariaLabel') === label || item.attributes('aria-label') === label)
  expect(control, label).toBeTruthy()
  control!.vm.$emit('update:modelValue', value)
  control!.vm.$emit('change', value)
  await flushPromises()
}
async function input(label: string, value: string) {
  const element = document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)
  expect(element, label).toBeTruthy()
  element!.value = value
  element!.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
const text = () => document.body.textContent ?? ''
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
it('只用规则create动作读取Member3，不借账户读取或默认勾选', async () => {
  await render()
  expect(api.accounts).toHaveBeenCalledWith(
    { action: 'CREATE', owner_user_id: id(2), owner_team_id: id(3), q: '', page_size: 50 },
    expect.any(AbortSignal),
  )
  expect(text()).toContain('明确选择 0 / 50000')
  expect(button('冻结所选范围').disabled).toBe(true)
  expect(api.create).not.toHaveBeenCalled()
  expect(text()).toContain('尚无真实候选')
})
it('没有当前动作或真实EditorContext就不发候选/冻结', async () => {
  await render({ permissionCodes: ['accounts.read', 'rules.read'] })
  expect(api.accounts).not.toHaveBeenCalled()
  expect(button('冻结所选范围').disabled).toBe(true)
  await wrapper.setProps({ permissionCodes: ['rules.create'], csrfToken: '' })
  await flushPromises()
  expect(api.accounts).not.toHaveBeenCalled()
})
it('IDS显式跨页保留，真实POST Scope5及成员核对后才choose', async () => {
  vi.mocked(api.accounts)
    .mockResolvedValueOnce(page([member()], 'next'))
    .mockResolvedValue(page([member(4)]))
  vi.mocked(api.create).mockResolvedValue({ ...scope(), count: 2 })
  await render()
  await check()
  await click('下一页账户')
  await check('0004')
  expect(text()).toContain('明确选择 2 / 50000')
  await click('冻结所选范围')
  const [body, headers] = vi.mocked(api.create).mock.calls[0]
  expect(body).toEqual({
    action: 'CREATE',
    rule_id: null,
    ownership: { owner_user_id: id(2), owner_team_id: id(3) },
    selection: { mode: 'IDS', account_ids: [id(), id(4)], filter: null },
  })
  expect(headers).toMatchObject({
    csrf_token: 'actual-context-csrf-token',
    idempotency_key: expect.any(String),
  })
  expect(headers).not.toHaveProperty('if_match')
  expect(api.members).toHaveBeenCalledWith(
    id(10),
    { q: '', page_size: 50 },
    expect.any(AbortSignal),
  )
  await click('应用真实范围')
  expect(wrapper.emitted('choose')?.[0]).toEqual([{ ...scope(), count: 2 }])
  expect(wrapper.emitted('pending-intent')?.at(-1)).toEqual([null])
})
it('FILTER全选五字段/空IDs，不拼当前页或假总数', async () => {
  await render({
    operatorOptions: [{ id: id(2), label: '真实投手' }],
    vendorOptions: [{ id: id(6), label: '真实户商' }],
  })
  await chooseMode('FILTER')
  await input('规则账户搜索', '真实%')
  await select('规则账户状态', 'ACTIVE')
  await select('规则账户授权状态', 'AUTHORIZED')
  await select('规则账户操作者', id(2))
  await select('规则账户户商', id(6))
  expect(button('冻结所选范围').disabled).toBe(true)
  await click('查询账户')
  await click('冻结所选范围')
  expect(vi.mocked(api.create).mock.calls[0][0].selection).toEqual({
    mode: 'FILTER',
    account_ids: [],
    filter: {
      q: '真实%',
      status: 'ACTIVE',
      auth_status: 'AUTHORIZED',
      operator_user_id: id(2),
      vendor_id: id(6),
    },
  })
  expect(text()).toContain('不支持从全选结果逐个排除')
})
it('零匹配/未知来源503不能冻结FILTER，不显示假快照', async () => {
  vi.mocked(api.accounts).mockResolvedValue(page([]))
  await render()
  await chooseMode('FILTER')
  expect(text()).toContain('零匹配')
  expect(button('冻结所选范围').disabled).toBe(true)
  expect(api.create).not.toHaveBeenCalled()
  vi.mocked(api.accounts).mockRejectedValue(
    new RuleApiError(503, 'RULE_SCOPE_SOURCE', '来源未就绪'),
  )
  await click('查询账户')
  expect(text()).toContain('RULE_SCOPE_SOURCE')
  expect(button('冻结所选范围').disabled).toBe(true)
})
it.each([20, 50, 100, 200] as const)('候选四档%d、历史cursor及已提交filter冻结', async (size) => {
  vi.mocked(api.accounts).mockResolvedValue(page([member()], 'next'))
  await render()
  await select('候选每页条数', size)
  await input('规则账户搜索', '尚未提交')
  await click('下一页账户')
  expect(api.accounts).toHaveBeenLastCalledWith(
    expect.objectContaining({ q: '', page_size: size, cursor: 'next' }),
    expect.any(AbortSignal),
  )
  await click('上一页账户')
  expect(vi.mocked(api.accounts).mock.calls.at(-1)![0]).not.toHaveProperty('cursor')
})
it('UPDATE固定quoted旧CAS，未知手动恢复不自动换键或正文', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true))
    .mockResolvedValue(scope())
  await render({
    action: 'UPDATE',
    ruleId: id(8),
    currentRuleRevision: 3,
    permissionCodes: ['rules.edit'],
  })
  await check()
  await click('冻结所选范围')
  const first = vi.mocked(api.create).mock.calls[0]
  expect(first[1]).toMatchObject({ if_match: '"3"' })
  expect(text()).toContain('原请求结果未知')
  expect(api.create).toHaveBeenCalledTimes(1)
  await click('使用原请求恢复')
  expect(vi.mocked(api.create).mock.calls[1].slice(0, 2)).toEqual(first.slice(0, 2))
  expect(wrapper.emitted('pending-intent')?.at(-1)).toEqual([null])
})
it('未知恢复后来403仍保留第一笔未知，不能另建scope写', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true))
    .mockRejectedValue(new RuleApiError(403, 'FORBIDDEN', '当前动作撤回'))
  await render()
  await check()
  await click('冻结所选范围')
  await click('使用原请求恢复')
  expect(text()).toContain('原请求结果未知')
  expect(button('冻结所选范围').disabled).toBe(true)
  expect(wrapper.emitted('pending-intent')?.at(-1)?.[0]).not.toBeNull()
})
it('明确422不是未知，可调整而不伪造成功', async () => {
  vi.mocked(api.create).mockRejectedValue(new RuleApiError(422, 'FIELD_INVALID', '真实字段拒绝'))
  await render()
  await check()
  await click('冻结所选范围')
  expect(text()).toContain('FIELD_INVALID')
  expect(text()).not.toContain('原请求结果未知')
  expect(wrapper.emitted('choose')).toBeUndefined()
  expect(wrapper.emitted('pending-intent')?.at(-1)).toEqual([null])
})
it('在途显式关闭中止本地等待、保留pending并禁止新写', async () => {
  const pending = deferred<ReturnType<typeof scope>>()
  vi.mocked(api.create).mockReturnValue(pending.promise)
  await render()
  await check()
  await click('冻结所选范围')
  const signal = vi.mocked(api.create).mock.calls[0][2]!
  await click('关闭并保留待确认请求')
  expect(signal.aborted).toBe(true)
  expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  await wrapper.setProps({ modelValue: false })
  pending.resolve(scope())
  await flushPromises()
  expect(wrapper.emitted('choose')).toBeUndefined()
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  expect(text()).toContain('原请求结果未知')
  expect(button('冻结所选范围').disabled).toBe(true)
})
it('父接管pending后跨卸载重建仍用原请求恢复，不声明内置持久化', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true))
    .mockResolvedValue(scope())
  await render()
  await check()
  await click('冻结所选范围')
  const record = wrapper.emitted('pending-intent')![0][0]
  const original = vi.mocked(api.create).mock.calls[0]
  wrapper.unmount()
  await render({ pendingIntent: record })
  await click('使用原请求恢复')
  expect(vi.mocked(api.create).mock.calls[1].slice(0, 2)).toEqual(original.slice(0, 2))
})
it('head/无关权限变化仍恢复原IfMatch，旧成员409不能apply', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true))
    .mockResolvedValue(scope())
  vi.mocked(api.members).mockRejectedValue(
    new RuleApiError(409, 'RULE_SCOPE_CHANGED', '旧范围不适用当前版本'),
  )
  await render({
    action: 'UPDATE',
    ruleId: id(8),
    currentRuleRevision: 3,
    permissionCodes: ['rules.edit'],
  })
  await check()
  await click('冻结所选范围')
  const first = vi.mocked(api.create).mock.calls[0]
  await wrapper.setProps({
    currentRuleRevision: 4,
    permissionCodes: ['rules.edit', 'unrelated.read'],
  })
  await flushPromises()
  await click('使用原请求恢复')
  expect(vi.mocked(api.create).mock.calls[1].slice(0, 2)).toEqual(first.slice(0, 2))
  expect(vi.mocked(api.create).mock.calls[1][1]).toMatchObject({ if_match: '"3"' })
  expect(button('应用真实范围').disabled).toBe(true)
  expect(text()).toContain('RULE_SCOPE_CHANGED')
})
it.each(['actor', 'owner', 'rule'])('不同%s上下文绝不重发原意图且不露旧数据', async (kind) => {
  vi.mocked(api.create).mockRejectedValue(
    new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true),
  )
  await render({
    action: 'UPDATE',
    ruleId: id(8),
    currentRuleRevision: 3,
    permissionCodes: ['rules.edit'],
  })
  await check()
  await click('冻结所选范围')
  await wrapper.setProps(
    kind === 'actor'
      ? { contextKey: 'different-actor' }
      : kind === 'owner'
        ? { ownership: { owner_user_id: id(20), owner_team_id: id(3) } }
        : { ruleId: id(20) },
  )
  await flushPromises()
  expect(button('使用原请求恢复').disabled).toBe(true)
  expect(text()).not.toContain('真实账户1')
  expect(api.create).toHaveBeenCalledTimes(1)
  await click('关闭并保留待确认请求')
  expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
})
it('成员原四档/分页及q冻结，错误403明确而不当空库存', async () => {
  vi.mocked(api.members).mockResolvedValue(page([member()], 'members-next'))
  await render()
  await check()
  await click('冻结所选范围')
  await select('成员每页条数', 200)
  await input('规则快照成员搜索', '未提交')
  await click('下一页成员')
  expect(api.members).toHaveBeenLastCalledWith(
    id(10),
    { q: '', page_size: 200, cursor: 'members-next' },
    expect.any(AbortSignal),
  )
  vi.mocked(api.members).mockRejectedValue(new RuleApiError(403, 'FORBIDDEN', '成员已不可读'))
  await click('查询冻结成员')
  expect(text()).toContain('FORBIDDEN')
  expect(button('应用真实范围').disabled).toBe(true)
})
it('晚候选不能覆盖新规则，关闭/卸载取消读取', async () => {
  const old = deferred<ScopeMemberPage>()
  vi.mocked(api.accounts)
    .mockReturnValueOnce(old.promise)
    .mockResolvedValue(page([member(4)]))
  await render()
  const first = vi.mocked(api.accounts).mock.calls[0][1]!
  await wrapper.setProps({
    action: 'UPDATE',
    ruleId: id(8),
    currentRuleRevision: 1,
    permissionCodes: ['rules.edit'],
  })
  await flushPromises()
  old.resolve(page([member()]))
  await flushPromises()
  expect(first.aborted).toBe(true)
  expect(text()).toContain('真实账户4')
  expect(text()).not.toContain('真实账户1')
  const last = vi.mocked(api.accounts).mock.calls.at(-1)![1]!
  wrapper.unmount()
  expect(last.aborted).toBe(true)
})
it('真实Dialog打开首搜索焦点、关闭后归还触发器；普通取消无POST', async () => {
  const opener = document.createElement('button')
  opener.textContent = '选择范围'
  document.body.append(opener)
  opener.focus()
  await render({ modelValue: false })
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  wrapper.findComponent(ElDialog).vm.$emit('opened')
  await flushPromises()
  expect(document.activeElement?.getAttribute('aria-label')).toBe('规则账户搜索')
  await click('取消本地选择')
  await wrapper.setProps({ modelValue: false })
  wrapper.findComponent(ElDialog).vm.$emit('closed')
  await flushPromises()
  expect(document.activeElement).toBe(opener)
  expect(api.create).not.toHaveBeenCalled()
})
it('父镜像同一pending不把正在等待的请求误标失败或重发', async () => {
  const waiting = deferred<ReturnType<typeof scope>>()
  vi.mocked(api.create).mockReturnValue(waiting.promise)
  await render()
  await check()
  await click('冻结所选范围')
  const record = wrapper.emitted('pending-intent')![0][0]
  await wrapper.setProps({ pendingIntent: record })
  await flushPromises()
  expect(text()).not.toContain('原请求结果未知')
  expect(api.create).toHaveBeenCalledTimes(1)
  waiting.resolve(scope())
  await flushPromises()
  expect(wrapper.emitted('pending-intent')?.at(-1)).toEqual([null])
})
it('未知请求当前原动作已撤回时不能恢复，关闭仍保留记录', async () => {
  vi.mocked(api.create).mockRejectedValue(
    new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true),
  )
  await render()
  await check()
  await click('冻结所选范围')
  await wrapper.setProps({ permissionCodes: ['rules.read'] })
  await flushPromises()
  expect(button('使用原请求恢复').disabled).toBe(true)
  expect(api.create).toHaveBeenCalledTimes(1)
  await click('关闭并保留待确认请求')
  expect(wrapper.emitted('pending-intent')?.at(-1)?.[0]).not.toBeNull()
})
it('已有成功回执重新打开必须重新核成员，不能直接应用旧资格', async () => {
  const waiting = deferred<ScopeMemberPage>()
  vi.mocked(api.members).mockResolvedValueOnce(page()).mockReturnValueOnce(waiting.promise)
  await render()
  await check()
  await click('冻结所选范围')
  expect(button('应用真实范围').disabled).toBe(false)
  await click('取消本地选择')
  await wrapper.setProps({ modelValue: false })
  await flushPromises()
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  expect(button('应用真实范围').disabled).toBe(true)
  waiting.resolve(page())
  await flushPromises()
  expect(button('应用真实范围').disabled).toBe(false)
})
it('同actor当前CSRF刷新只在手动恢复更新传输，业务三项逐字不变', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true))
    .mockResolvedValue(scope())
  await render({
    action: 'UPDATE',
    ruleId: id(8),
    currentRuleRevision: 3,
    permissionCodes: ['rules.edit'],
  })
  await check()
  await click('冻结所选范围')
  const first = vi.mocked(api.create).mock.calls[0],
    pending = wrapper.emitted('pending-intent')![0][0] as {
      intent: { auth: { csrf_token: string } }
    }
  await wrapper.setProps({ csrfToken: 'new-current-context-csrf-token' })
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 1,
    tenant_id: id(99),
    csrf_token: 'new-current-context-csrf-token',
  })
  await flushPromises()
  expect(api.create).toHaveBeenCalledTimes(1)
  await click('使用原请求恢复')
  const second = vi.mocked(api.create).mock.calls[1]
  expect(JSON.stringify(second[0])).toBe(JSON.stringify(first[0]))
  expect(second[1].idempotency_key).toBe(first[1].idempotency_key)
  expect('if_match' in second[1] && second[1].if_match).toBe('"3"')
  expect(second[1].csrf_token).toBe('new-current-context-csrf-token')
  expect(pending.intent.auth.csrf_token).toBe('actual-context-csrf-token')
})
it('head3旧成功恢复且members200只读历史，不能stamp为当前head4资格', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true))
    .mockResolvedValue(scope())
  vi.mocked(api.members).mockResolvedValue(page())
  vi.mocked(ruleScopeOptionsApi.options).mockImplementation(
    async (query) =>
      ({
        ...page([]),
        items: query.kind === 'OPERATOR' ? [remoteOperator()] : [remoteVendor()],
      }) as never,
  )
  await render({
    action: 'UPDATE',
    ruleId: id(8),
    currentRuleRevision: 3,
    permissionCodes: ['rules.edit'],
  })
  await check()
  await click('冻结所选范围')
  await wrapper.setProps({ currentRuleRevision: 4 })
  await flushPromises()
  await click('使用原请求恢复')
  expect(api.members).toHaveBeenCalledWith(
    id(10),
    { q: '', page_size: 50 },
    expect.any(AbortSignal),
  )
  expect(text()).toContain('仅供历史核对')
  expect(text()).toContain(id(10))
  expect(button('应用真实范围').disabled).toBe(true)
  expect(wrapper.emitted('choose')).toBeUndefined()
  expect(wrapper.emitted('pending-intent')?.at(-1)).toEqual([null])
})
it.each([401, 403])('候选%d即时清敏感选择和快照，不依赖props撤权，禁止新POST', async (status) => {
  vi.mocked(api.accounts)
    .mockResolvedValueOnce(page())
    .mockRejectedValue(new RuleApiError(status, 'ACCESS_REVOKED', '当前访问已撤回'))
  await render()
  await check()
  await click('冻结所选范围')
  expect(text()).toContain(id(10))
  await click('查询账户')
  expect(text()).toContain('ACCESS_REVOKED')
  expect(text()).not.toContain('真实账户1')
  expect(text()).not.toContain(id(10))
  expect(text()).toContain('明确选择 0 / 50000')
  expect(button('冻结所选范围').disabled).toBe(true)
  const count = vi.mocked(api.create).mock.calls.length
  await click('冻结所选范围')
  expect(api.create).toHaveBeenCalledTimes(count)
  expect(button('重新验证当前访问')).toBeTruthy()
})
it.each([401, 403])('成员%d清旧回执/成员/已选，但不假造空成功', async (status) => {
  vi.mocked(api.members)
    .mockResolvedValueOnce(page())
    .mockRejectedValue(new RuleApiError(status, 'ACCESS_REVOKED', '当前成员不可读'))
  await render()
  await check()
  await click('冻结所选范围')
  expect(text()).toContain(id(10))
  await click('查询冻结成员')
  expect(text()).toContain('ACCESS_REVOKED')
  expect(text()).not.toContain(id(10))
  expect(text()).not.toContain('真实账户1')
  expect(button('应用真实范围').disabled).toBe(true)
  expect(button('冻结所选范围').disabled).toBe(true)
})
it('普通候选网络503保留明确选择供重试，不当作撤权抹除', async () => {
  vi.mocked(api.accounts)
    .mockResolvedValueOnce(page())
    .mockRejectedValue(new RuleApiError(503, 'TEMPORARY_SOURCE', '来源暂不可用'))
  await render()
  await check()
  await click('查询账户')
  expect(text()).toContain('TEMPORARY_SOURCE')
  expect(text()).toContain('明确选择 1 / 50000')
  expect(api.create).not.toHaveBeenCalled()
})
it('未知期间head变化清旧游标栈，恢复后不再沿旧页回退', async () => {
  vi.mocked(api.accounts)
    .mockResolvedValueOnce(page([member()], 'next'))
    .mockResolvedValue(page([member(4)]))
  vi.mocked(api.create)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true))
    .mockResolvedValue(scope())
  await render({
    action: 'UPDATE',
    ruleId: id(8),
    currentRuleRevision: 3,
    permissionCodes: ['rules.edit'],
  })
  await click('下一页账户')
  await check('0004')
  await click('冻结所选范围')
  await wrapper.setProps({ currentRuleRevision: 4 })
  await flushPromises()
  await click('使用原请求恢复')
  expect(button('上一页账户').disabled).toBe(true)
  expect(button('应用真实范围').disabled).toBe(true)
})

it('规则专属远程两种候选独立加载，历史状态可筛且alias null不回退name', async () => {
  await render({ remoteOptions: true })
  expect(ruleScopeOptionsApi.options).toHaveBeenCalledTimes(2)
  expect(ruleScopeOptionsApi.options).toHaveBeenCalledWith(
    {
      kind: 'OPERATOR',
      action: 'CREATE',
      owner_user_id: id(2),
      owner_team_id: id(3),
      q: '',
      page_size: 50,
    },
    expect.any(AbortSignal),
  )
  expect(ruleScopeOptionsApi.options).toHaveBeenCalledWith(
    {
      kind: 'VENDOR',
      action: 'CREATE',
      owner_user_id: id(2),
      owner_team_id: id(3),
      q: '',
      page_size: 50,
    },
    expect.any(AbortSignal),
  )
  expect(
    wrapper
      .findAllComponents(ElSelect)
      .find((x) => x.props('ariaLabel') === '规则账户操作者')!
      .props('placeholder'),
  ).toBe('请选择操作者')
  expect(
    wrapper
      .findAllComponents(ElSelect)
      .find((x) => x.props('ariaLabel') === '规则账户户商')!
      .props('placeholder'),
  ).toBe('请选择户商')
  const labels = wrapper.findAllComponents(ElOption).map((x) => x.props('label'))
  expect(labels).toContain(`真实操作者 · 真实团队 · 已停用（仅历史筛选） · ${id(20)}`)
  expect(labels).toContain(
    `未设置代称 · 资料名称：资料名称不是代称 · 不可用（仅历史筛选） · ${id(30)}`,
  )
  await select('规则账户操作者', id(20))
  await select('规则账户户商', id(30))
  await click('查询账户')
  expect(api.accounts).toHaveBeenLastCalledWith(
    expect.objectContaining({ operator_user_id: id(20), vendor_id: id(30) }),
    expect.any(AbortSignal),
  )
})
it('候选q与原账户q独立，四档keyset不会伪全量或清掉当前filter', async () => {
  vi.mocked(ruleScopeOptionsApi.options).mockImplementation(
    async (query) =>
      ({
        ...page([], 'opaque-next'),
        items: query.kind === 'OPERATOR' ? [remoteOperator()] : [remoteVendor()],
      }) as never,
  )
  await render({ remoteOptions: true })
  await select('规则账户操作者', id(20))
  await input('规则账户搜索', '账户前缀')
  await click('查询账户')
  await input('操作者候选搜索', '人员前缀')
  await click('查询操作者候选')
  expect(ruleScopeOptionsApi.options).toHaveBeenLastCalledWith(
    expect.objectContaining({ kind: 'OPERATOR', q: '人员前缀', page_size: 50 }),
    expect.any(AbortSignal),
  )
  expect(ruleScopeOptionsApi.options).not.toHaveBeenLastCalledWith(
    expect.objectContaining({ q: '账户前缀' }),
    expect.anything(),
  )
  await click('下一页操作者候选')
  expect(ruleScopeOptionsApi.options).toHaveBeenLastCalledWith(
    expect.objectContaining({ q: '人员前缀', cursor: 'opaque-next' }),
    expect.any(AbortSignal),
  )
  await click('上一页操作者候选')
  expect(vi.mocked(ruleScopeOptionsApi.options).mock.calls.at(-1)![0]).not.toHaveProperty('cursor')
  for (const size of [20, 100, 200, 50]) {
    await select('操作者候选每页条数', size)
    expect(ruleScopeOptionsApi.options).toHaveBeenLastCalledWith(
      expect.objectContaining({ page_size: size, kind: 'OPERATOR' }),
      expect.any(AbortSignal),
    )
  }
  await click('查询账户')
  expect(api.accounts).toHaveBeenLastCalledWith(
    expect.objectContaining({ q: '账户前缀', operator_user_id: id(20) }),
    expect.any(AbortSignal),
  )
})
it('翻页保留曾真实选择的ID标签，非候选UUID不能塞入filter', async () => {
  vi.mocked(ruleScopeOptionsApi.options).mockImplementation(
    async (query) =>
      ({
        ...page([], query.cursor ? null : 'next'),
        items:
          query.kind === 'OPERATOR' ? [remoteOperator(query.cursor ? 21 : 20)] : [remoteVendor()],
      }) as never,
  )
  await render({ remoteOptions: true })
  await select('规则账户操作者', id(20))
  await click('下一页操作者候选')
  expect(wrapper.findAllComponents(ElOption).map((x) => x.props('value'))).toContain(id(20))
  await select('规则账户操作者', id(999))
  await click('查询账户')
  expect(api.accounts).toHaveBeenLastCalledWith(
    expect.objectContaining({ operator_user_id: id(20) }),
    expect.any(AbortSignal),
  )
})
it('两个远程请求各有epoch，快速查询迟到不覆盖，owner/revision变化清cursor与旧filter', async () => {
  await render({
    remoteOptions: true,
    action: 'UPDATE',
    ruleId: id(40),
    currentRuleRevision: 3,
    permissionCodes: ['rules.edit'],
  })
  await select('规则账户户商', id(30))
  await click('查询账户')
  const d = deferred<any>()
  vi.mocked(ruleScopeOptionsApi.options).mockReturnValueOnce(d.promise)
  await click('查询户商候选')
  const signal = vi.mocked(ruleScopeOptionsApi.options).mock.calls.at(-1)![1]!
  await wrapper.setProps({
    ownership: { owner_user_id: id(22), owner_team_id: id(3) },
    currentRuleRevision: 4,
  })
  await flushPromises()
  expect(signal.aborted).toBe(true)
  d.resolve({ ...page([]), items: [{ ...remoteVendor(99), name: '不应泄漏的旧资料' }] })
  await flushPromises()
  expect(text()).not.toContain('不应泄漏的旧资料')
  expect(ruleScopeOptionsApi.options).toHaveBeenCalledWith(
    expect.objectContaining({ kind: 'VENDOR', owner_user_id: id(22), rule_id: id(40) }),
    expect.any(AbortSignal),
  )
  await click('查询账户')
  expect(vi.mocked(api.accounts).mock.calls.at(-1)![0]).not.toHaveProperty('vendor_id')
})
it.each([401, 403, 409])('远程%d清旧候选/账户选择/已选filter，不能继续新写', async (status) => {
  await render({ remoteOptions: true })
  await select('规则账户操作者', id(20))
  await check()
  vi.mocked(ruleScopeOptionsApi.options).mockRejectedValueOnce(
    new RuleApiError(status, 'SCOPE_OPTIONS_CHANGED', '候选权限或来源变化'),
  )
  await click('查询操作者候选')
  expect(text()).toContain('SCOPE_OPTIONS_CHANGED')
  expect(wrapper.findAllComponents(ElOption).map((x) => x.props('value'))).not.toContain(id(20))
  expect(text()).not.toContain('真实操作者')
  expect(button('冻结所选范围').disabled).toBe(true)
  expect(api.create).not.toHaveBeenCalled()
})
it('候选503保留真实已选和已验证scope，不把查询失败当空或新增freeze资格门禁', async () => {
  await render({ remoteOptions: true })
  await select('规则账户操作者', id(20))
  await check()
  await click('冻结所选范围')
  expect(text()).toContain('完整账户数')
  expect(button('应用真实范围').disabled).toBe(false)
  const previousCalls = vi.mocked(api.create).mock.calls.length
  vi.mocked(ruleScopeOptionsApi.options).mockRejectedValueOnce(
    new RuleApiError(503, 'OPTIONS_UNAVAILABLE', '候选来源未就绪'),
  )
  await click('查询操作者候选')
  expect(text()).toContain('OPTIONS_UNAVAILABLE')
  expect(text()).toContain('完整账户数')
  expect(button('应用真实范围').disabled).toBe(false)
  expect(wrapper.findAllComponents(ElOption).map((x) => x.props('value'))).toContain(id(20))
  expect(api.create).toHaveBeenCalledTimes(previousCalls)
})
it('远程真实空页区别于503，关闭取消两个读取且不启动其它权限API', async () => {
  vi.mocked(ruleScopeOptionsApi.options).mockResolvedValue(page([]) as never)
  await render({ remoteOptions: true })
  expect(
    wrapper
      .findAllComponents(ElSelect)
      .find((x) => x.props('ariaLabel') === '规则账户操作者')!
      .props('placeholder'),
  ).toBe('尚无真实候选')
  expect(
    wrapper
      .findAllComponents(ElSelect)
      .find((x) => x.props('ariaLabel') === '规则账户户商')!
      .props('placeholder'),
  ).toBe('尚无真实候选')
  expect(text()).toContain('当前操作者候选查询没有匹配项')
  expect(text()).toContain('当前户商候选查询没有匹配项')
  const d = deferred<any>()
  vi.mocked(ruleScopeOptionsApi.options).mockReturnValue(d.promise)
  await click('查询操作者候选')
  const signal = vi.mocked(ruleScopeOptionsApi.options).mock.calls.at(-1)![1]!
  await wrapper.setProps({ modelValue: false })
  expect(signal.aborted).toBe(true)
  d.resolve({ ...page([]), items: [remoteOperator()] })
  await flushPromises()
  expect(api.create).not.toHaveBeenCalled()
})

it('在途候选随后撤权不能吞已发scope的未知意图', async () => {
  await render({ remoteOptions: true })
  await check()
  let reject!: (e: unknown) => void
  const remote = new Promise<any>((_, r) => (reject = r))
  vi.mocked(ruleScopeOptionsApi.options).mockReturnValueOnce(remote)
  await click('查询操作者候选')
  const writing = deferred<any>()
  vi.mocked(api.create).mockReturnValue(writing.promise)
  await click('冻结所选范围')
  const before = wrapper.emitted('pending-intent')!.at(-1)![0]
  expect(before).toBeTruthy()
  reject(new RuleApiError(403, 'CURRENT_REVOKED', '当前权限撤回'))
  await flushPromises()
  expect(wrapper.emitted('pending-intent')!.at(-1)![0]).toBe(before)
  expect(text()).toContain('CURRENT_REVOKED')
  expect(button('冻结所选范围').disabled).toBe(true)
})

it.each([401, 403, 409])(
  '真实SDK解析%d畸形正文后清旧候选/快照，保留已发未知scope意图',
  async (status) => {
    await render({ remoteOptions: true })
    await select('规则账户操作者', id(20))
    await check()
    await click('冻结所选范围')
    expect(text()).toContain('完整账户数')
    // 原SDK真实处理Response正文；只有fetch为协议替身，scope写仍独立受控。
    const actual = await vi.importActual<typeof import('@/api/orbit/rule-scope-options')>(
      '@/api/orbit/rule-scope-options',
    )
    let release!: (value: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>((resolve) => (release = resolve))),
    )
    vi.mocked(ruleScopeOptionsApi.options).mockImplementationOnce(
      actual.ruleScopeOptionsApi.options,
    )
    await click('查询操作者候选')
    const writing = deferred<any>()
    vi.mocked(api.create).mockReturnValueOnce(writing.promise)
    await click('冻结所选范围')
    const pending = wrapper.emitted('pending-intent')!.at(-1)![0]
    expect(pending).toBeTruthy()
    release(new Response(status === 401 ? '<html>private</html>' : '{"code":', { status }))
    await flushPromises()
    expect(text()).toContain('INVALID_RESPONSE')
    expect(text()).not.toContain('真实操作者')
    expect(text()).not.toContain('完整账户数')
    expect(wrapper.findAllComponents(ElOption).map((x) => x.props('value'))).not.toContain(id(20))
    expect(button('冻结所选范围').disabled).toBe(true)
    expect(wrapper.emitted('pending-intent')!.at(-1)![0]).toBe(pending)
  },
)

it('首次SCOPE主体不符零POST且不留下假未知意图', async () => {
  await render()
  await check()
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 2,
    tenant_id: id(99),
    csrf_token: 'different-actor-csrf-token',
  })
  await click('冻结所选范围')
  expect(api.create).not.toHaveBeenCalled()
  expect(wrapper.emitted('pending-intent')?.filter((x) => x[0]) ?? []).toEqual([])
  expect(document.body.textContent).toContain('RULE_RECOVERY_UI_ACTOR_CHANGED')
})
it('未知SCOPE遇租户变化保留原意图但禁止再POST', async () => {
  vi.mocked(api.create).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true),
  )
  await render()
  await check()
  await click('冻结所选范围')
  const original = wrapper.emitted('pending-intent')![0][0]
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 1,
    tenant_id: id(98),
    csrf_token: 'different-tenant-csrf-token',
  })
  await click('使用原请求恢复')
  expect(api.create).toHaveBeenCalledTimes(1)
  expect(wrapper.emitted('pending-intent')!.at(-1)![0]).toEqual(original)
  expect(document.body.textContent).toContain('RULE_RECOVERY_PRINCIPAL_CHANGED')
})

it('首次身份读取期间显式关闭取消读取，迟到ctx不能生成pending或POST', async () => {
  const waiting = deferred<any>()
  vi.mocked(ruleRecoveryApi.get).mockReturnValueOnce(waiting.promise)
  await render()
  await check()
  await click('冻结所选范围')
  const signal = vi.mocked(ruleRecoveryApi.get).mock.calls[0][1]!
  await click('取消本地选择')
  expect(signal.aborted).toBe(true)
  await wrapper.setProps({ modelValue: false })
  waiting.resolve({ actor_id: 1, tenant_id: id(99), csrf_token: 'current-context-csrf-token' })
  await flushPromises()
  expect(api.create).not.toHaveBeenCalled()
  expect(wrapper.emitted('pending-intent')?.filter((x) => x[0]) ?? []).toEqual([])
})

it('未知SCOPE弹窗内登录和复核可触达，事件不重发且保留原body/key/CAS', async () => {
  vi.mocked(api.create).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true),
  )
  await render()
  await check()
  await click('冻结所选范围')
  const old = wrapper.emitted('pending-intent')!.find((x) => x[0])![0]
  const modal = document.querySelector('.el-dialog')!
  expect(modal.querySelector('a[href="/login"]')?.getAttribute('target')).toBe('_blank')
  expect(modal.querySelector('a')?.getAttribute('rel')).toBe('noopener')
  await click('重新验证当前身份（不提交）')
  expect(wrapper.emitted('verifyIdentity')).toHaveLength(1)
  expect(api.create).toHaveBeenCalledTimes(1)
  expect(wrapper.emitted('pending-intent')!.at(-1)![0]).toEqual(old)
  await wrapper.setProps({ recoveryMessage: '核验失败，原请求保留' })
  expect(modal.textContent).toContain('核验失败，原请求保留')
})
