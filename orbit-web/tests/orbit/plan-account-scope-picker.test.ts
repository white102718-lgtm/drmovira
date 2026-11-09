/** 真实ElementPlus挂载+transport替身，只证明选择器状态机，不表示真实账户范围验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import Picker from '@/views/orbit/launch/PlanAccountScopePicker.vue'
import {
  launchAccountScopesApi as api,
  type AccountCandidate,
} from '@/api/orbit/launch-account-scopes'
import { LaunchValidationError } from '@/api/orbit/launch-validation'
const id = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const owner = { owner_user_id: id(8), owner_team_id: id(9) },
  time = '2026-11-08T00:00:00Z'
const candidate = (n: number, currency = 'USD'): AccountCandidate => ({
  id: id(n),
  external_id: `000${n}`,
  name: `账户${n}`,
  ownership: { ...owner },
  currency,
  auth_status: 'AUTHORIZED',
  account_status: 'ACTIVE',
})
const snapshot = (count = 2) => ({
  id: id(20),
  count,
  scope_version: 3,
  hash: 'a'.repeat(64),
  created_at: time,
})
const page = (rows = [candidate(1)], next: string | null = null) => ({
  items: rows,
  next_cursor: next,
  data_as_of: time,
  scope_version: 3,
})
const members = (next: string | null = null) => ({
  items: [{ account_id: id(1), external_id: '0001', name: '冻结旧名称' }],
  next_cursor: next,
  data_as_of: time,
  scope_version: 3,
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.spyOn(api, 'candidates').mockResolvedValue(page())
  vi.spyOn(api, 'capabilities').mockResolvedValue({
    csrf_token: 'fixture-csrf',
    max_members: 50000,
    max_plan_accounts: 500,
  })
  vi.spyOn(api, 'create').mockResolvedValue(snapshot())
  vi.spyOn(api, 'members').mockResolvedValue(members())
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start(props: Record<string, unknown> = {}) {
  wrapper = mount(Picker, {
    attachTo: document.body,
    props: { modelValue: true, ownership: owner, canRead: true, ...props },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
const button = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (x) => x.textContent?.trim() === text,
  )!
async function click(text: string) {
  expect(button(text), text).toBeTruthy()
  button(text).click()
  await flushPromises()
}
async function mode(value: 'IDS' | 'FILTER') {
  wrapper!.findComponent({ name: 'ElRadioGroup' }).vm.$emit('update:modelValue', value)
  await flushPromises()
}
async function select(index = 0) {
  wrapper!.findAllComponents({ name: 'ElCheckbox' })[index].vm.$emit('change', true)
  await flushPromises()
}
it('未授权默认禁用、零读取、不能借计划权限读账户', async () => {
  await start({ canRead: false })
  expect(button('查询账户').disabled).toBe(true)
  expect(button('应用到账户选择').disabled).toBe(true)
  expect(api.candidates).not.toHaveBeenCalled()
  expect(api.capabilities).not.toHaveBeenCalled()
})
it('初次打开不拉全量，明确查询绑定目标owner；手动单选不创建快照', async () => {
  await start()
  expect(api.candidates).not.toHaveBeenCalled()
  await click('查询账户')
  expect(api.candidates).toHaveBeenCalledWith(
    expect.objectContaining({ operator_user_id: owner.owner_user_id }),
    50,
    null,
    expect.any(AbortSignal),
  )
  await select()
  await click('应用到账户选择')
  expect(wrapper!.emitted('choose')![0][0]).toEqual({
    kind: 'IDS',
    account_ids: [id(1)],
    snapshot: null,
  })
  expect(api.create).not.toHaveBeenCalled()
})
it('跨页手动勾选和取消保留本地明确ID，短页仍按nextcursor继续', async () => {
  vi.mocked(api.candidates)
    .mockResolvedValueOnce(page([candidate(1)], 'page2'))
    .mockResolvedValueOnce(page([candidate(2)], 'page3'))
    .mockResolvedValueOnce(page([candidate(1)], 'page2'))
  await start()
  await click('查询账户')
  await select()
  await click('下一页账户')
  expect(vi.mocked(api.candidates).mock.calls[1][2]).toBe('page2')
  await select()
  await click('上一页账户')
  expect(vi.mocked(api.candidates).mock.calls[2][2]).toBeNull()
  await select()
  await click('应用到账户选择')
  expect(wrapper!.emitted('choose')![0][0]).toMatchObject({ account_ids: [id(2)] })
})
it('归属不同候选不可选，币种冲突不会静默混入', async () => {
  vi.mocked(api.candidates).mockResolvedValue(
    page([
      candidate(1),
      candidate(2, 'EUR'),
      { ...candidate(3), ownership: { ...owner, owner_user_id: id(99) } },
    ]),
  )
  await start()
  await click('查询账户')
  expect(wrapper!.findAllComponents({ name: 'ElCheckbox' })[2].props('disabled')).toBe(true)
  await select(0)
  await select(1)
  expect(document.body.textContent).toContain('同一计划只能选择一种币种')
  await click('应用到账户选择')
  expect(wrapper!.emitted('choose')![0][0]).toMatchObject({ account_ids: [id(1)] })
})
it('500已选仍完整回显并禁止501，没有截断或静默全选', async () => {
  const ids = Array.from({ length: 500 }, (_, i) => id(i + 1))
  vi.mocked(api.candidates).mockResolvedValue(page([candidate(501)]))
  await start({ selected: { kind: 'IDS', account_ids: ids, snapshot: null } })
  await click('查询账户')
  expect(wrapper!.findComponent({ name: 'ElCheckbox' }).props('disabled')).toBe(true)
  expect(document.body.textContent).toContain('500 / 500')
  await click('应用到账户选择')
  expect((wrapper!.emitted('choose')![0][0] as { account_ids: string[] }).account_ids).toEqual(ids)
})
it('FILTER真正201后分页核对才可应用，原account_ids必须空且无排除扩展', async () => {
  await start()
  await mode('FILTER')
  expect(button('应用到账户选择').disabled).toBe(true)
  await click('冻结并核对完整范围')
  expect(api.create).toHaveBeenCalledWith(
    {
      mode: 'FILTER',
      account_ids: [],
      filter: {
        q: '',
        status: null,
        auth_status: null,
        operator_user_id: owner.owner_user_id,
        vendor_id: null,
      },
    },
    expect.objectContaining({ csrf_token: 'fixture-csrf', idempotency_key: expect.any(String) }),
  )
  expect(api.members).toHaveBeenCalledTimes(1)
  expect(document.body.textContent).toContain('冻结旧名称')
  await click('应用到账户选择')
  expect(api.members).toHaveBeenCalledTimes(2)
  expect(wrapper!.emitted('choose')![0][0]).toEqual({
    kind: 'SNAPSHOT',
    account_ids: [],
    snapshot: snapshot(),
  })
})
it.each([0, 501, 50000])('真实范围%d不截断为500，也不能用于计划', async (count) => {
  vi.mocked(api.create).mockResolvedValue(snapshot(count))
  await start()
  await mode('FILTER')
  await click('冻结并核对完整范围')
  expect(document.body.textContent).toContain(String(count))
  expect(button('应用到账户选择').disabled).toBe(true)
  expect(wrapper!.emitted('choose')).toBeUndefined()
})
it('成员游标上一页/四档重置，查询只改变视图不重建快照', async () => {
  vi.mocked(api.members).mockResolvedValue(members('next'))
  await start()
  await mode('FILTER')
  await click('冻结并核对完整范围')
  await click('下一页成员')
  expect(vi.mocked(api.members).mock.calls[1][3]).toBe('next')
  await click('上一页成员')
  expect(vi.mocked(api.members).mock.calls[2][3]).toBeNull()
  const size = wrapper!
    .findAllComponents({ name: 'ElSelect' })
    .find((v) => v.props('ariaLabel') === '每页成员数')!
  for (const n of [20, 100, 200, 50]) {
    size.vm.$emit('update:modelValue', n)
    await flushPromises()
    expect(button('上一页成员').disabled).toBe(true)
    await click('查询成员')
    expect(vi.mocked(api.members).mock.lastCall![2]).toBe(n)
    expect(vi.mocked(api.members).mock.lastCall![3]).toBeNull()
  }
  expect(api.create).toHaveBeenCalledTimes(1)
})
it.each([401, 403, 404, 409])(
  '成员读取%d使整范围失效清旧名，不保留可应用假快照',
  async (status) => {
    await start()
    await mode('FILTER')
    await click('冻结并核对完整范围')
    vi.mocked(api.members).mockRejectedValue(
      new LaunchValidationError(status, 'SCOPE_CHANGED', '范围失效'),
    )
    await click('查询成员')
    expect(document.body.textContent).not.toContain('冻结旧名称')
    expect(button('应用到账户选择').disabled).toBe(true)
    expect(wrapper!.emitted('choose')).toBeUndefined()
  },
)
it('成员版本漂移拒绝，不能只凭原count/ID继续应用', async () => {
  await start()
  await mode('FILTER')
  await click('冻结并核对完整范围')
  vi.mocked(api.members).mockResolvedValue({ ...members(), scope_version: 4 })
  await click('应用到账户选择')
  expect(button('应用到账户选择').disabled).toBe(true)
  expect(wrapper!.emitted('choose')).toBeUndefined()
})
it('应用前真实成员重读网络失败，不以旧成功快照继续emit', async () => {
  await start()
  await mode('FILTER')
  await click('冻结并核对完整范围')
  vi.mocked(api.members).mockRejectedValue(new LaunchValidationError(0, 'NETWORK', '网络中断'))
  await click('应用到账户选择')
  expect(wrapper!.emitted('choose')).toBeUndefined()
  expect(button('应用到账户选择').disabled).toBe(true)
  await click('查询成员')
  expect(api.create).toHaveBeenCalledTimes(1)
})
it('已存snapshot重开保持真实元数据，必须重新核对成员才能应用', async () => {
  await start({ selected: { kind: 'SNAPSHOT', account_ids: [], snapshot: snapshot() } })
  expect(document.body.textContent).toContain(snapshot().hash)
  expect(button('应用到账户选择').disabled).toBe(true)
  await click('查询成员')
  await click('应用到账户选择')
  expect(wrapper!.emitted('choose')![0][0]).toEqual({
    kind: 'SNAPSHOT',
    account_ids: [],
    snapshot: snapshot(),
  })
  expect(api.create).not.toHaveBeenCalled()
})
it('冻结中拥有者变化不丢原意图，恢复成功也不能给新拥有者直接应用', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new LaunchValidationError(0, 'UNKNOWN', '未知', [], true, null, true))
    .mockResolvedValueOnce(snapshot())
  await start()
  await mode('FILTER')
  await click('冻结并核对完整范围')
  const original = structuredClone(vi.mocked(api.create).mock.calls[0])
  await wrapper!.setProps({ ownership: { ...owner, owner_user_id: id(88) } })
  await click('恢复原冻结')
  expect(vi.mocked(api.create).mock.calls[1]).toEqual(original)
  expect(api.members).not.toHaveBeenCalled()
  expect(button('应用到账户选择').disabled).toBe(true)
  expect(button('取消本地选择').disabled).toBe(false)
})
it('冻结网络未知锁关闭/条件，同key同payload恢复且不再次取csrf', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new LaunchValidationError(0, 'UNKNOWN', '未知', [], true, null, true))
    .mockResolvedValueOnce(snapshot())
  await start()
  await mode('FILTER')
  await click('冻结并核对完整范围')
  expect(button('取消本地选择').disabled).toBe(true)
  expect(button('冻结并核对完整范围').disabled).toBe(true)
  expect(wrapper!.emitted('locked')!.at(-1)).toEqual([true])
  const first = structuredClone(vi.mocked(api.create).mock.calls[0])
  await click('恢复原冻结')
  expect(vi.mocked(api.create).mock.calls[1]).toEqual(first)
  expect(api.capabilities).toHaveBeenCalledTimes(1)
  expect(button('取消本地选择').disabled).toBe(false)
  expect(wrapper!.emitted('locked')!.at(-1)).toEqual([false])
})
it('未知写后换登录上下文禁止用新身份重放原意图，恢复原上下文才可继续', async () => {
  vi.mocked(api.create)
    .mockRejectedValueOnce(new LaunchValidationError(0, 'UNKNOWN', '未知', [], true, null, true))
    .mockResolvedValueOnce(snapshot())
  await start({ contextKey: 'actor-original' })
  await mode('FILTER')
  await click('冻结并核对完整范围')
  await wrapper!.setProps({ contextKey: 'actor-changed' })
  await click('恢复原冻结')
  expect(api.create).toHaveBeenCalledTimes(1)
  expect(button('取消本地选择').disabled).toBe(true)
  expect(document.body.textContent).toContain('不能把旧意图转交其他身份')
  await wrapper!.setProps({ contextKey: 'actor-original' })
  await click('恢复原冻结')
  expect(api.create).toHaveBeenCalledTimes(2)
})
it('拥有者/权限上下文改变清观察并禁止应用，保留原选择供用户重新处理', async () => {
  await start()
  await click('查询账户')
  await select()
  await wrapper!.setProps({ ownership: { ...owner, owner_team_id: id(90) } })
  await flushPromises()
  expect(button('应用到账户选择').disabled).toBe(true)
  expect(document.body.textContent).toContain('旧选择保留')
  expect(document.body.textContent).toContain('已明确勾选 1')
  await click('重新选择')
  expect(document.body.textContent).toContain('已明确勾选 0')
})
it('迟到候选不能盖过新筛选；关闭取消GET且不伪造服务器取消快照', async () => {
  let resolve!: (v: ReturnType<typeof page>) => void
  vi.mocked(api.candidates).mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await start()
  button('查询账户').click()
  await flushPromises()
  const signal = vi.mocked(api.candidates).mock.calls[0][3]!
  const input = wrapper!.findComponent({ name: 'ElInput' })
  input.vm.$emit('update:modelValue', '新的条件')
  await flushPromises()
  expect(signal.aborted).toBe(true)
  resolve(page([candidate(999)]))
  await flushPromises()
  expect(document.body.textContent).not.toContain('账户999')
  await click('取消本地选择')
  expect(wrapper!.emitted('update:modelValue')!.at(-1)).toEqual([false])
  expect(api.create).not.toHaveBeenCalled()
})
it('取消已冻结选择需确认，取消只是本地事件，不调用虚构删除接口', async () => {
  await start()
  await mode('FILTER')
  await click('冻结并核对完整范围')
  vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
  await click('取消本地选择')
  expect(wrapper!.emitted('update:modelValue')).toBeUndefined()
  await click('取消本地选择')
  expect(wrapper!.emitted('update:modelValue')!.at(-1)).toEqual([false])
  expect(api.create).toHaveBeenCalledTimes(1)
})
it('capabilities晚回时组件已卸载，不发起新的POST', async () => {
  let resolve!: (v: { csrf_token: string; max_members: number; max_plan_accounts: number }) => void
  vi.mocked(api.capabilities).mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await start()
  await mode('FILTER')
  button('冻结并核对完整范围').click()
  await flushPromises()
  wrapper!.unmount()
  wrapper = undefined
  resolve({ csrf_token: 'fixture', max_members: 50000, max_plan_accounts: 500 })
  await flushPromises()
  expect(api.create).not.toHaveBeenCalled()
})
