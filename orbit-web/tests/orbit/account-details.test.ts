/** 组件服务替身验证18列/弹窗/竞态；不替代真实Python/数据库/IdP/平台验收。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElCheckboxGroup, ElDrawer, ElRadioGroup } from 'element-plus'
import Accounts from '@/views/orbit/accounts/index.vue'
import Drawer from '@/views/orbit/accounts/AccountDetailsDrawer.vue'
import type { ExtendedAccount } from '@/api/orbit/account-details'
import { ReferenceApiError } from '@/api/orbit/references'
import { ElDropdown, ElDropdownItem } from 'element-plus'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  identities: vi.fn(),
  owners: vi.fn(),
  capabilities: vi.fn(),
}))
const router = vi.hoisted(() => ({ push: vi.fn() }))
const currentUser = vi.hoisted(() => ({ permissions: [] as string[] }))
const actions = vi.hoisted(() => ({ capabilities: vi.fn(), reason: vi.fn() }))
const assignment = vi.hoisted(() => ({ owners: vi.fn(), vendors: vi.fn(), assign: vi.fn() }))
vi.mock('@/store/modules/user', () => ({ default: () => currentUser }))
vi.mock('@/api/orbit/account-actions', () => ({ accountActionsApi: actions }))
vi.mock('@/api/orbit/account-assignment', () => ({ accountAssignmentApi: assignment }))
vi.mock('vue-router', () => ({ useRouter: () => router }))
vi.mock('@/api/orbit/account-details', async (original) => ({
  ...(await original<typeof import('@/api/orbit/account-details')>()),
  accountDetailsApi: api,
}))
vi.mock('@/api/orbit/accounts', () => ({ accountApi: { capabilities: api.capabilities } }))
const wrappers: ReturnType<typeof mount>[] = []
const unknown = {
  amount: null,
  currency: 'USD',
  kind: 'UNKNOWN',
  status: 'UNSYNCED',
  source: 'NOT_PROVIDED',
  business_date: null,
  observed_at: null,
} as const
const text = {
  value: null,
  code: null,
  status: 'UNSYNCED',
  source: 'NOT_PROVIDED',
  observed_at: null,
  reason_code: 'NOT_PROVIDED',
} as const
function row(name = '账户甲'): ExtendedAccount {
  return {
    account: {
      id: 'account',
      external_id: '0000123',
      name,
      ownership: { owner_user_id: 'owner', owner_team_id: 'team' },
      vendor_id: 'vendor',
      vendor_alias: null,
      currency: 'USD',
      timezone: {
        id: 'America/New_York',
        display_label: 'UTC-05:00（America/New_York）',
        reference_at: '2026-11-08T05:00:00Z',
        offset_at: '-05:00',
      },
      auth_status: 'UNKNOWN',
      account_status: 'UNKNOWN',
      revision: 1,
      synced_at: null,
      balance: { ...unknown },
      spend: { ...unknown, kind: 'SPEND' },
    },
    details: {
      account_id: 'account',
      revision: 1,
      source_revision: 0,
      owner_display: '投手甲',
      vendor_display: {
        name: '完整户商资料名称',
        source: 'REFERENCE_CATALOG',
        reason_code: 'ALIAS_NOT_MAPPED',
      },
      personal_profile: { ...text },
      business_entity: { ...text },
      payment_type: { ...text },
      payment_method: { ...text },
      blocked_reason: { ...text },
      payable: { ...unknown, kind: 'BILL' },
      lifetime_spend: { ...unknown, kind: 'SPEND' },
      business_managers: null,
      identity_status: 'UNSYNCED',
      identity_observed_at: null,
      identity_count: null,
      authorized_at: null,
      unbound_at: null,
      blocked_observed_at: null,
      note: null,
      spend_window: {
        mode: 'TODAY',
        date_from: '2026-11-08',
        date_to: '2026-11-08',
        timezone: 'America/New_York',
        reference_at: '2026-11-08T05:00:00Z',
        coverage: 'NOT_COLLECTED',
        snapshot_id: null,
      },
    },
  }
}
function page(value = row()) {
  return {
    items: [value],
    next_cursor: null,
    data_as_of: '2026-11-08T05:00:00Z',
    scope_version: 1,
    account_version: 1,
    metric_snapshot_id: null,
  }
}
beforeEach(() => {
  vi.clearAllMocks()
  currentUser.permissions = []
  actions.capabilities.mockImplementation((_id: string, kind: string) =>
    Promise.resolve({
      csrf_token: 'action-csrf',
      revision: 1,
      next_effective_from: kind === 'ASSIGNMENT' ? '2026-11-10T05:00:00Z' : null,
    }),
  )
  actions.reason.mockImplementation((intent: { accountId: string; action: string }) =>
    Promise.resolve({
      id: intent.accountId,
      revision: 2,
      request_id: 'request-id',
      state: intent.action === 'SYNC' ? 'WAITING_EXECUTOR' : 'SUCCEEDED',
    }),
  )
  assignment.owners.mockResolvedValue({ items: [], next_cursor: null })
  assignment.vendors.mockResolvedValue({ items: [], next_cursor: null })
  localStorage.clear()
  api.list.mockResolvedValue(page())
  api.get.mockResolvedValue(row())
  api.owners.mockResolvedValue({
    items: [{ id: 'owner', name: '投手甲', team_id: 'team', team_name: '团队甲' }],
    next_cursor: null,
  })
  api.capabilities.mockRejectedValue(new Error('没有导入权限'))
  api.identities.mockRejectedValue(new Error('身份资源接口尚未就绪'))
})
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  document.body.innerHTML = ''
  vi.useRealTimers()
})
async function render(component: typeof Accounts | typeof Drawer = Accounts) {
  const wrapper = mount(component, { attachTo: document.body, global: { plugins: [ElementPlus] } })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
function button(title: string) {
  const found = [...document.querySelectorAll('button')].find(
    (el) => el.textContent?.trim() === title,
  )
  if (!found) throw new Error(`未找到${title}`)
  found.click()
  return found
}
function headers() {
  return [...document.querySelectorAll('.el-table__header th')].map((el) => el.textContent?.trim())
}

describe('账户18列与详情，组件服务替身范围', () => {
  it('原账户页面通过真实路由入口进入范围二级页，不依赖导入权限', async () => {
    await render()
    button('账户范围')
    expect(router.push).toHaveBeenCalledWith('/orbit/account-scopes')
    expect(headers()).toHaveLength(18)
  })
  it('保留18列、前导零、未知与真实代称缺口，投手候选使用read接口', async () => {
    await render()
    expect(headers()).toHaveLength(18)
    expect(headers()).toContain('应付账单')
    expect(headers()).toContain('被封原因')
    expect(document.body.textContent).toContain('0000123')
    expect(document.body.textContent).toContain('尚未提供真实代称')
    expect(document.body.textContent).toContain('尚未同步身份资源')
    expect(api.list.mock.calls[0][0].get('mode')).toBe('TODAY')
    expect(api.list.mock.calls[0][0].has('date_from')).toBe(false)
    expect(api.owners).toHaveBeenCalledOnce()
    expect(api.identities).not.toHaveBeenCalled()
  })
  it('日期取消不查，快捷确认只发送mode，不按浏览器时区展开日期', async () => {
    const wrapper = await render()
    button('今天')
    await flushPromises()
    wrapper.findComponent(ElRadioGroup).vm.$emit('update:modelValue', 'LAST7')
    button('取消')
    await flushPromises()
    expect(api.list).toHaveBeenCalledOnce()
    button('今天')
    await flushPromises()
    wrapper.findComponent(ElRadioGroup).vm.$emit('update:modelValue', 'LAST7')
    button('确认日期')
    await flushPromises()
    expect(api.list.mock.lastCall?.[0].get('mode')).toBe('LAST7')
    expect(api.list.mock.lastCall?.[0].has('date_from')).toBe(false)
  })
  it('列设置取消不改，确认保存列ID且名称和操作始终存在', async () => {
    const wrapper = await render()
    button('列设置')
    await flushPromises()
    wrapper.findComponent(ElCheckboxGroup).vm.$emit('update:modelValue', ['owner'])
    button('取消')
    await flushPromises()
    expect(headers()).toHaveLength(18)
    button('列设置')
    await flushPromises()
    wrapper.findComponent(ElCheckboxGroup).vm.$emit('update:modelValue', ['owner'])
    button('应用字段设置')
    await flushPromises()
    expect(headers()).toEqual(['投放师', '账户名称 / ID', '操作'])
    expect(JSON.parse(localStorage.getItem('orbit-account-columns-v1')!)).toEqual(['owner', 'name'])
  })
  it('迟到列表响应不能覆盖较新的查询', async () => {
    let resolve!: (value: ReturnType<typeof page>) => void
    api.list.mockImplementationOnce(() => new Promise((done) => (resolve = done)))
    const wrapper = await render()
    const search = wrapper.find('input[placeholder="名称前缀或完整数字ID"]')
    await search.setValue('新查询')
    await search.trigger('keyup.enter')
    await flushPromises()
    expect(document.body.textContent).toContain('账户甲')
    resolve(page(row('过期账户')))
    await flushPromises()
    expect(document.body.textContent).not.toContain('过期账户')
  })
  it('请求失败清空旧列表且显式重试，不把错误当空成功', async () => {
    await render()
    api.list.mockRejectedValueOnce(new Error('权限已撤销'))
    button('查询')
    await flushPromises()
    expect(document.body.textContent).toContain('权限已撤销')
    expect(document.body.textContent).not.toContain('0000123')
    button('重新查询')
    await flushPromises()
    expect(document.body.textContent).toContain('0000123')
  })
  it('详情保留完整原名与每项金额来源，身份失败不填空资源', async () => {
    const wrapper = await render(Drawer)
    ;(wrapper.vm as unknown as { open: (id: string, q: URLSearchParams) => void }).open(
      'account',
      new URLSearchParams({ mode: 'TODAY' }),
    )
    await flushPromises()
    expect(document.body.textContent).toContain('完整户商资料名称')
    expect(document.body.textContent).toContain('累计总花费')
    expect(document.body.textContent).toContain('NOT_PROVIDED')
    button('读取身份资源')
    await flushPromises()
    expect(document.body.textContent).toContain('身份资源接口尚未就绪')
    expect(document.body.textContent).not.toContain('本次已观测快照中没有身份资源')
  })
  it('关闭详情立即作废旧请求，重新打开不被旧对象响应覆盖', async () => {
    let resolve!: (value: ExtendedAccount) => void
    api.get.mockImplementationOnce(() => new Promise((done) => (resolve = done)))
    const wrapper = await render(Drawer)
    const drawer = wrapper.vm as unknown as { open: (id: string, q: URLSearchParams) => void }
    drawer.open('old', new URLSearchParams())
    await flushPromises()
    wrapper.findComponent(ElDrawer).vm.$emit('close')
    wrapper.findComponent(ElDrawer).vm.$emit('update:modelValue', false)
    await flushPromises()
    drawer.open('new', new URLSearchParams())
    await flushPromises()
    resolve(row('旧对象原名'))
    await flushPromises()
    expect(document.body.textContent).not.toContain('旧对象原名')
    expect(document.body.textContent).toContain('账户甲')
  })
  it('只读权限不显示写动作，详情和原18列查询仍保留', async () => {
    const wrapper = await render()
    expect(wrapper.findComponent(ElDropdown).exists()).toBe(false)
    expect(actions.capabilities).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('详情')
    expect(document.body.textContent).toContain('18列')
  })
  it('按明确sync权限显示并真正打开原因弹窗，受理后刷新而不伪改资料', async () => {
    currentUser.permissions = ['accounts.sync']
    const wrapper = await render()
    expect(wrapper.findAllComponents(ElDropdownItem).map((node) => node.props('command'))).toEqual([
      'SYNC',
    ])
    const dropdown = wrapper.findComponent(ElDropdown)
    dropdown.vm.$emit('command', 'ASSIGNMENT')
    await flushPromises()
    expect(actions.capabilities).not.toHaveBeenCalled()
    dropdown.vm.$emit('command', 'SYNC')
    await flushPromises()
    expect(actions.capabilities.mock.calls[0].slice(0, 2)).toEqual(['account', 'SYNC'])
    await wrapper.find('textarea[aria-label="账户操作原因"]').setValue('核对平台资料')
    button('确认受理只读同步')
    await flushPromises()
    expect(document.body.textContent).toContain('只读同步已受理，尚未确认执行结果')
    expect(api.list).toHaveBeenCalledTimes(2)
    expect(document.body.textContent).toContain('未同步')
    expect(document.body.textContent).not.toContain('0 USD')
  })
  it('assign/unbind独立权限入口各自接正确弹窗，不要求导入权限', async () => {
    currentUser.permissions = ['accounts.assign', 'accounts.unbind']
    const wrapper = await render()
    expect(wrapper.findAllComponents(ElDropdownItem).map((node) => node.props('command'))).toEqual([
      'ASSIGNMENT',
      'UNBIND',
    ])
    wrapper.findComponent(ElDropdown).vm.$emit('command', 'ASSIGNMENT')
    await flushPromises()
    expect(actions.capabilities.mock.calls[0].slice(0, 2)).toEqual(['account', 'ASSIGNMENT'])
    expect(assignment.owners).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).toContain('分配广告账户')
    wrapper.findComponent(ElDropdown).vm.$emit('command', 'UNBIND')
    await flushPromises()
    expect(actions.capabilities.mock.calls[1].slice(0, 2)).toEqual(['account', 'UNBIND'])
    await wrapper.find('textarea[aria-label="账户操作原因"]').setValue('结束本地关联')
    button('确认本地解绑')
    await flushPromises()
    expect(actions.reason.mock.calls[0][0].action).toBe('UNBIND')
    expect(document.body.textContent).toContain('本地解绑已完成')
  })
  it('菜单打开后撤动作也不能靠旧command打开弹窗', async () => {
    currentUser.permissions = ['accounts.sync']
    const wrapper = await render()
    const dropdown = wrapper.findComponent(ElDropdown)
    currentUser.permissions = []
    dropdown.vm.$emit('command', 'SYNC')
    await flushPromises()
    expect(actions.capabilities).not.toHaveBeenCalled()
  })
  it('实际父页面关闭重开未知同步仍沿原意图，成功后才刷新', async () => {
    currentUser.permissions = ['accounts.sync']
    actions.reason.mockRejectedValueOnce(
      new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '网络中断'),
    )
    const wrapper = await render()
    wrapper.findComponent(ElDropdown).vm.$emit('command', 'SYNC')
    await flushPromises()
    await wrapper.find('textarea[aria-label="账户操作原因"]').setValue('父页面保留原意图')
    button('确认受理只读同步')
    await flushPromises()
    const original = structuredClone(actions.reason.mock.calls[0][0])
    expect(api.list).toHaveBeenCalledTimes(1)
    button('关闭')
    wrapper.findComponent(ElDropdown).vm.$emit('command', 'SYNC')
    await flushPromises()
    button('重试原请求')
    await flushPromises()
    expect(actions.reason.mock.calls[1][0]).toEqual(original)
    expect(api.list).toHaveBeenCalledTimes(2)
  })
})
