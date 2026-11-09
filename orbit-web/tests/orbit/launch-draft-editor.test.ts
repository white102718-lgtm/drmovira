import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import DraftEditor from '@/views/orbit/launch/DraftEditor.vue'
import { launchApi, type LaunchCapabilities, type LaunchPlan } from '@/api/orbit/launch'
import { ReferenceApiError } from '@/api/orbit/references'
import { newDraft } from '@/api/orbit/launch-form'
import { readDraftRecovery } from '@/api/orbit/launch-recovery'
import PlanIdentityBindings from '@/views/orbit/launch/PlanIdentityBindings.vue'
import SourcePicker from '@/views/orbit/launch/SourcePicker.vue'
import PlanAccountScopePicker from '@/views/orbit/launch/PlanAccountScopePicker.vue'
import { accountIdentitiesApi } from '@/api/orbit/account-identities'
import PlanMetricProfileField from '@/views/orbit/launch/PlanMetricProfileField.vue'
import CampaignTree from '@/views/orbit/launch/CampaignTree.vue'
const caps: LaunchCapabilities = {
  actions: ['create', 'edit'],
  data_role: 'SUPER_ADMIN',
  csrf_token: 'csrf-never-cache',
  actor_user_id: '00000000-0000-0000-0000-000000000001',
  actor_team_id: '00000000-0000-0000-0000-000000000002',
  actor_label: '当前本人',
}
let wrapper: VueWrapper
const saved = (): LaunchPlan => ({
  ...newDraft({ owner_user_id: caps.actor_user_id, owner_team_id: caps.actor_team_id }),
  id: '00000000-0000-0000-0000-000000000003',
  revision: 1,
  state: 'DRAFT',
  created_at: '2026-11-08T00:00:00Z',
  updated_at: '2026-11-08T00:00:00Z',
})
beforeEach(() => {
  sessionStorage.clear()
  vi.spyOn(launchApi, 'owners').mockResolvedValue({
    items: [
      {
        id: caps.actor_user_id,
        name: caps.actor_label,
        team_id: caps.actor_team_id,
        team_name: '当前团队',
      },
    ],
    next_cursor: null,
    scope_version: 1,
  })
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  sessionStorage.clear()
})
async function start(props = {}) {
  wrapper = mount(DraftEditor, {
    attachTo: document.body,
    props: { modelValue: true, capabilities: caps, ...props },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
function nameInput() {
  const label = [...document.querySelectorAll<HTMLLabelElement>('label')].find(
    (label) => label.textContent?.trim() === '计划名称（草稿可空，最多100码点）',
  )!
  return document.getElementById(label.htmlFor) as HTMLInputElement
}
async function fill(value: string) {
  const input = nameInput()
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
async function click(text: string) {
  const button = [...document.querySelectorAll('button')].find(
    (button) => button.textContent?.trim() === text,
  )
  expect(button, text).toBeTruthy()
  button!.click()
  await flushPromises()
}
it('计划原指标UUID手填保存不要求monitor.read，已应用值进入原恢复草稿', async () => {
  const original = saved()
  original.campaigns = [
    { local_id: 'campaign', copies: 1, adsets: [{ local_id: 'group', copies: 1, ads: [] }] },
  ]
  const save = vi.spyOn(launchApi, 'save').mockResolvedValue(original)
  await start({ plan: original, metricReadAllowed: false })
  await wrapper.findComponent(CampaignTree).vm.focusField('group', ['metric_profile_id'])
  const field = wrapper.findComponent(PlanMetricProfileField)
  expect(field.props('canRead')).toBe(false)
  const uuid = '00000000-0000-4000-8000-000000000099'
  await field.get('input').setValue(uuid)
  expect(readDraftRecovery(caps.actor_user_id)?.body.campaigns[0].adsets[0].metric_profile_id).toBe(
    uuid,
  )
  await click('保存服务器草稿')
  expect(save.mock.calls[0][0].campaigns[0].adsets[0].metric_profile_id).toBe(uuid)
})
it('指标目录二级页期间关闭和保存守卫不丢意图，父locked事件向页面传播', async () => {
  const original = saved()
  original.campaigns = [
    { local_id: 'campaign', copies: 1, adsets: [{ local_id: 'group', copies: 1, ads: [] }] },
  ]
  const save = vi.spyOn(launchApi, 'save')
  await start({ plan: original, metricReadAllowed: true, accountContextKey: 'actual-user-1' })
  const tree = wrapper.findComponent(CampaignTree)
  tree.vm.$emit('browsing', true)
  await flushPromises()
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([true])
  expect(
    [...document.querySelectorAll<HTMLButtonElement>('button')].find(
      (b) => b.textContent?.trim() === '保存服务器草稿',
    )!.disabled,
  ).toBe(true)
  await click('关闭')
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  expect(save).not.toHaveBeenCalled()
  tree.vm.$emit('browsing', false)
  await flushPromises()
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([false])
})
it('首开真实actor默认归属，101emoji拒绝而100码点完整提交', async () => {
  const save = vi.spyOn(launchApi, 'save').mockResolvedValue(saved())
  await start()
  await fill('😀'.repeat(101))
  await click('保存服务器草稿')
  expect(save).not.toHaveBeenCalled()
  await fill('😀'.repeat(100))
  await click('保存服务器草稿')
  expect(save.mock.calls[0][0].name).toBe('😀'.repeat(100))
  expect(save.mock.calls[0][0].ownership.owner_user_id).toBe(caps.actor_user_id)
  expect(save.mock.calls[0][0]).not.toHaveProperty('id')
  expect(nameInput().getAttribute('maxlength')).toBeNull()
})
it('未知结果冻结父字段，重试使用同一完整正文与键且缓存不含CSRF', async () => {
  const save = vi
    .spyOn(launchApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '未知结果'))
    .mockResolvedValueOnce(saved())
  await start()
  await fill('需要恢复的草稿')
  await click('保存服务器草稿')
  expect(nameInput().disabled).toBe(true)
  expect(readDraftRecovery(caps.actor_user_id)?.pendingKey).toBe(save.mock.calls[0][2])
  expect(sessionStorage.getItem(`orbit.launch.draft.v1.${caps.actor_user_id}`)).not.toContain(
    caps.csrf_token,
  )
  const close = [...document.querySelectorAll('button')].find(
    (button) => button.textContent?.trim() === '关闭',
  )!
  expect(close.disabled).toBe(true)
  await click('重试本次保存')
  expect(save.mock.calls[1][2]).toBe(save.mock.calls[0][2])
  expect(save.mock.calls[1][0]).toEqual(save.mock.calls[0][0])
  expect(readDraftRecovery(caps.actor_user_id)).toBeNull()
  expect(wrapper.emitted('saved')).toHaveLength(1)
})
it('未知后撤权403不能伪装已确认或丢弃旧保存键', async () => {
  const save = vi
    .spyOn(launchApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '未知结果'))
    .mockRejectedValueOnce(new ReferenceApiError(403, 'PERMISSION_DENIED', '当前权限已变化'))
  await start()
  await click('保存服务器草稿')
  const key = save.mock.calls[0][2]
  await click('重试本次保存')
  expect(nameInput().disabled).toBe(true)
  expect(readDraftRecovery(caps.actor_user_id)?.pendingKey).toBe(key)
  expect(wrapper.emitted('saved')).toBeUndefined()
})
it('刷新后恢复保留旧意图，但新会话CSRF从当前caps获得', async () => {
  const save = vi
    .spyOn(launchApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '未知结果'))
    .mockResolvedValueOnce(saved())
  await start()
  await fill('刷新后原键恢复')
  await click('保存服务器草稿')
  const recovery = readDraftRecovery(caps.actor_user_id)!
  wrapper.unmount()
  document.body.innerHTML = ''
  await start({ recovery, capabilities: { ...caps, csrf_token: 'fresh-csrf' } })
  expect(nameInput().value).toBe('刷新后原键恢复')
  expect(nameInput().disabled).toBe(true)
  await click('重试本次保存')
  expect(save.mock.calls[1][2]).toBe(recovery.pendingKey)
  expect(save.mock.calls[1][1]).toBe('fresh-csrf')
})
it('只读详情不会强加拥有者写候选权限，且无保存按钮', async () => {
  await start({ plan: saved(), readOnly: true })
  expect(launchApi.owners).not.toHaveBeenCalled()
  expect(nameInput().disabled).toBe(true)
  expect(
    [...document.querySelectorAll('button')].some(
      (button) => button.textContent?.trim() === '保存服务器草稿',
    ),
  ).toBe(false)
  await click('关闭')
  expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
})
it('明确依赖未就绪是未保存，可继续编辑而非假成功', async () => {
  vi.spyOn(launchApi, 'save').mockRejectedValue(
    new ReferenceApiError(503, 'METRIC_PROFILE_DEPENDENCY_UNAVAILABLE', '指标资料未就绪'),
  )
  await start()
  await fill('仍未保存')
  await click('保存服务器草稿')
  expect(nameInput().disabled).toBe(false)
  expect(readDraftRecovery(caps.actor_user_id)?.pendingKey).toBeUndefined()
  expect(document.body.textContent).toContain('指标资料未就绪')
  expect(wrapper.emitted('saved')).toBeUndefined()
})
it('逐账户身份显式应用进入原恢复缓存，503不假保存，未知保存和刷新恢复仍冻结同正文与键', async () => {
  const account = '00000000-0000-0000-0000-000000000099',
    page = '99999999999999999999999999999999'
  const source = { ...saved(), account_ids: [account] }
  vi.spyOn(accountIdentitiesApi, 'get').mockResolvedValue({
    account_id: account,
    resources: [
      { external_id: page, name: '观察主页', kind: 'PAGE', usable: true, reason_code: null },
    ],
    capability_version: 'observe-1',
    observed_at: '2026-11-08T00:00:00Z',
  })
  const save = vi
    .spyOn(launchApi, 'save')
    .mockRejectedValueOnce(
      new ReferenceApiError(503, 'LAUNCH_IDENTITY_DEPENDENCY_UNAVAILABLE', '身份消费者尚未接通'),
    )
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '结果未知'))
    .mockRejectedValueOnce(new ReferenceApiError(403, 'PERMISSION_DENIED', '当前权限已撤回'))
  await start({ plan: source, identityReadAllowed: true })
  await click('配置身份')
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([true])
  expect(
    [...document.querySelectorAll<HTMLButtonElement>('button')].find(
      (node) => node.textContent?.trim() === '保存服务器草稿',
    )!.disabled,
  ).toBe(true)
  await click('读取本账户身份')
  wrapper
    .findComponent(PlanIdentityBindings)
    .findComponent({ name: 'ElSelectV2' })
    .vm.$emit('update:modelValue', page)
  await flushPromises()
  await click('应用到本地草稿')
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([false])
  const expected = [{ account_id: account, page_id: page, groups: [], ad_overrides: [] }]
  expect(readDraftRecovery(caps.actor_user_id)?.body.identity_bindings).toEqual(expected)
  await click('保存服务器草稿')
  expect(wrapper.emitted('saved')).toBeUndefined()
  expect(nameInput().disabled).toBe(false)
  expect(document.body.textContent).toContain('身份消费者尚未接通')
  await click('保存服务器草稿')
  expect(wrapper.findComponent(PlanIdentityBindings).props('disabled')).toBe(true)
  const recovery = readDraftRecovery(caps.actor_user_id)!
  expect(recovery.body.identity_bindings).toEqual(expected)
  expect(recovery.pendingKey).toBe(save.mock.calls[1][2])
  expect(JSON.stringify(recovery)).not.toContain(caps.csrf_token)
  wrapper.unmount()
  document.body.innerHTML = ''
  await start({ plan: source, recovery, identityReadAllowed: true })
  expect(document.body.textContent).toContain(page)
  expect(wrapper.findComponent(PlanIdentityBindings).props('disabled')).toBe(true)
  await click('重试本次保存')
  expect(save.mock.calls[2][0]).toEqual(save.mock.calls[1][0])
  expect(save.mock.calls[2][2]).toBe(save.mock.calls[1][2])
  expect(wrapper.emitted('saved')).toBeUndefined()
})
it('来源账户移除保留孤立身份并进入原缓存，只读详情仍能打开身份区域', async () => {
  const account = '00000000-0000-0000-0000-000000000099',
    original = {
      account_id: account,
      page_id: '12345678901234567890',
      groups: [],
      ad_overrides: [],
    }
  await start({
    plan: { ...saved(), account_ids: [account], identity_bindings: [original] },
    identityReadAllowed: true,
  })
  wrapper
    .findComponent(PlanAccountScopePicker)
    .vm.$emit('choose', { kind: 'IDS', account_ids: [], snapshot: null })
  await flushPromises()
  expect(wrapper.findComponent(PlanIdentityBindings).props('accountIds')).toEqual([])
  expect(wrapper.findComponent(PlanIdentityBindings).props('modelValue')).toEqual([original])
  expect(readDraftRecovery(caps.actor_user_id)?.body.identity_bindings).toEqual([original])
  expect(document.body.textContent).toContain('1 个绑定的账户已移出选择')
  wrapper.unmount()
  document.body.innerHTML = ''
  await start({
    readOnly: true,
    plan: { ...saved(), account_ids: [account], identity_bindings: [original] },
  })
  await click('查看身份')
  expect(document.body.textContent).toContain('逐账户身份配置')
  expect(wrapper.findComponent(PlanIdentityBindings).props('readOnly')).toBe(true)
  expect(
    [...document.querySelectorAll('button')].some(
      (node) => node.textContent?.trim() === '应用到本地草稿',
    ),
  ).toBe(false)
})
const accountUuid = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const scope = (count = 21) => ({
  id: accountUuid(700),
  count,
  scope_version: 8,
  hash: 'a'.repeat(64),
  created_at: '2026-11-08T00:00:00Z',
})
function chooseScope(count = 21) {
  wrapper
    .findComponent(PlanAccountScopePicker)
    .vm.$emit('choose', { kind: 'SNAPSHOT', account_ids: [], snapshot: scope(count) })
}
it('账户入口使用独立范围选择器并传真实read/context，素材渠道继续原选择器', async () => {
  await start({ identityReadAllowed: true, accountContextKey: 'actor-1-permissions-version-2' })
  const picker = wrapper.findComponent(PlanAccountScopePicker)
  expect(picker.props('canRead')).toBe(true)
  expect(picker.props('contextKey')).toContain('actor-1-permissions-version-2')
  await click('选择账户（0/500）')
  expect(picker.props('modelValue')).toBe(true)
  expect(wrapper.findComponent(SourcePicker).props('modelValue')).toBe(false)
  expect(nameInput().disabled).toBe(true)
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([true])
  picker.vm.$emit('update:modelValue', false)
  await flushPromises()
  await click('选择素材池（0/500）')
  expect(wrapper.findComponent(SourcePicker).props('kind')).toBe('assets')
  expect(wrapper.emitted('locked')?.at(-1)).toEqual([true])
})
it('没有accounts.read不能打开账户入口，不借launch动作读取', async () => {
  await start()
  const accountButton = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (v) => v.textContent?.trim() === '选择账户（0/500）',
  )!
  expect(accountButton.disabled).toBe(true)
  expect(wrapper.findComponent(PlanAccountScopePicker).props('canRead')).toBeFalsy()
})
it('真实snapshot数量参与展开，恢复只有scopeID则明确未知且身份须先保存解析', async () => {
  const campaign = {
    local_id: accountUuid(1),
    copies: 2,
    adsets: [
      { local_id: accountUuid(2), copies: 3, ads: [{ local_id: accountUuid(3), copies: 4 }] },
    ],
  }
  await start({ identityReadAllowed: true, plan: { ...saved(), campaigns: [campaign] } })
  chooseScope()
  await flushPromises()
  expect(document.body.textContent).toContain('选择账户（21/500）')
  expect(document.body.textContent).toMatch(/系列\s*42\s*· 广告组\s*126\s*· 广告\s*504/)
  expect(wrapper.findComponent(PlanIdentityBindings).props('disabled')).toBe(true)
  expect(readDraftRecovery(caps.actor_user_id)?.body).toMatchObject({
    account_ids: [],
    account_scope_snapshot_id: scope().id,
  })
  const recovery = readDraftRecovery(caps.actor_user_id)!
  wrapper.unmount()
  document.body.innerHTML = ''
  await start({ identityReadAllowed: true, recovery })
  expect(document.body.textContent).toContain('选择账户（数量待解析/500）')
  expect(document.body.textContent).toContain('展开数量未知')
  expect(wrapper.findComponent(PlanAccountScopePicker).props('selected')).toBeNull()
  expect(wrapper.findComponent(PlanIdentityBindings).props('disabled')).toBe(true)
})
it('保存解析后以真实server source回编；再保存和恢复缓存只含实际IDs/null与可写字段', async () => {
  const ids = Array.from({ length: 21 }, (_, i) => accountUuid(i + 100)),
    server = {
      ...saved(),
      name: '服务端规范名称',
      account_ids: ids,
      account_scope_snapshot_id: null,
      revision: 9,
    }
  const save = vi.spyOn(launchApi, 'save').mockResolvedValue(server)
  await start({ identityReadAllowed: true })
  chooseScope()
  await flushPromises()
  await click('保存服务器草稿')
  expect(save.mock.calls[0][0]).toMatchObject({
    account_ids: [],
    account_scope_snapshot_id: scope().id,
  })
  expect(nameInput().value).toBe(server.name)
  expect(document.body.textContent).toContain('选择账户（21/500）')
  expect(wrapper.findComponent(PlanIdentityBindings).props('accountIds')).toEqual(ids)
  expect(wrapper.findComponent(PlanIdentityBindings).props('disabled')).toBe(false)
  expect(readDraftRecovery(caps.actor_user_id)).toBeNull()
  await fill('下一次编辑')
  expect(readDraftRecovery(caps.actor_user_id)?.body).toMatchObject({
    account_ids: ids,
    account_scope_snapshot_id: null,
  })
  await click('保存服务器草稿')
  expect(save.mock.calls[1][0]).toMatchObject({
    account_ids: ids,
    account_scope_snapshot_id: null,
    name: '下一次编辑',
  })
  expect(save.mock.calls[1][3]).toEqual({ id: server.id, revision: 9 })
  for (const field of ['id', 'revision', 'state', 'created_at', 'updated_at'])
    expect(save.mock.calls[1][0]).not.toHaveProperty(field)
})
it('scope保存未知仍冻结同一个原请求/key，不能提前套用猜测解析IDs', async () => {
  const ids = [accountUuid(40)],
    save = vi
      .spyOn(launchApi, 'save')
      .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK', '未知'))
      .mockResolvedValueOnce({ ...saved(), account_ids: ids, account_scope_snapshot_id: null })
  await start({ identityReadAllowed: true })
  chooseScope(1)
  await flushPromises()
  await click('保存服务器草稿')
  const original = structuredClone(save.mock.calls[0][0]),
    key = save.mock.calls[0][2]
  expect(wrapper.findComponent(PlanIdentityBindings).props('accountIds')).toEqual([])
  expect(readDraftRecovery(caps.actor_user_id)?.body.account_scope_snapshot_id).toBe(scope().id)
  await click('重试本次保存')
  expect(save.mock.calls[1][0]).toEqual(original)
  expect(save.mock.calls[1][2]).toBe(key)
  expect(wrapper.findComponent(PlanIdentityBindings).props('accountIds')).toEqual(ids)
})
it('清除账户必须确认，保留所有孤立身份和原恢复正文，不删除快照', async () => {
  const original = { account_id: accountUuid(99), page_id: '100', groups: [], ad_overrides: [] }
  const confirm = vi
    .spyOn(ElMessageBox, 'confirm')
    .mockRejectedValueOnce('cancel')
    .mockResolvedValueOnce('confirm')
  await start({
    identityReadAllowed: true,
    plan: { ...saved(), account_ids: [original.account_id], identity_bindings: [original] },
  })
  await click('清除账户选择')
  expect(wrapper.findComponent(PlanIdentityBindings).props('accountIds')).toEqual([
    original.account_id,
  ])
  await click('清除账户选择')
  expect(confirm).toHaveBeenCalledTimes(2)
  expect(wrapper.findComponent(PlanIdentityBindings).props('accountIds')).toEqual([])
  expect(wrapper.findComponent(PlanIdentityBindings).props('modelValue')).toEqual([original])
  expect(readDraftRecovery(caps.actor_user_id)?.body.identity_bindings).toEqual([original])
})
it('子范围unknown锁挡关闭/保存/刷新；原上下文prop变化只传递，不丢子意图', async () => {
  const save = vi.spyOn(launchApi, 'save')
  await start({ identityReadAllowed: true, accountContextKey: 'original-context' })
  const picker = wrapper.findComponent(PlanAccountScopePicker)
  await click('选择账户（0/500）')
  picker.vm.$emit('locked', true)
  await flushPromises()
  const close = [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (v) => v.textContent?.trim() === '关闭',
  )!
  expect(close.disabled).toBe(true)
  expect(nameInput().disabled).toBe(true)
  await (
    wrapper.findComponent({ name: 'ElDrawer' }).props('beforeClose') as (
      done: () => void,
    ) => Promise<void>
  )(vi.fn())
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  await wrapper.setProps({ accountContextKey: 'changed-context' })
  expect(picker.props('contextKey')).toContain('changed-context')
  expect(picker.props('modelValue')).toBe(true)
  expect(save).not.toHaveBeenCalled()
})
