import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ScopePage from '@/views/orbit/accounts/scopes/index.vue'
import ScopeMembers from '@/views/orbit/accounts/scopes/ScopeMembers.vue'
const api = vi.hoisted(() => ({
  createScope: vi.fn(),
  getScopeCsrf: vi.fn(),
  getScopeMembers: vi.fn(),
}))
vi.mock('@/api/orbit/scopes', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers.length = 0
  document.body.innerHTML = ''
  vi.clearAllMocks()
})
const snapshot = {
  id: 'fixture',
  count: 1,
  scope_version: 1,
  hash: 'fixture',
  created_at: '2026-11-07T00:00:00Z',
}
const memberPage = {
  items: [{ account_id: 'id', external_id: '12345678901234567890', name: '最新成员' }],
  next_cursor: null,
  data_as_of: snapshot.created_at,
  scope_version: 1,
}
it('重复UUID包含大小写等价项时明确提示，不静默去重并提交成功', async () => {
  const w = mount(ScopePage, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  wrappers.push(w)
  const radios = w.findAll('input[type="radio"]')
  await radios[1].setValue(true)
  const identifier = '10000000-0000-4000-8000-0000000000ab'
  await w
    .find('textarea[aria-label="账户ID清单"]')
    .setValue(identifier + '\n' + identifier.toUpperCase())
  await w.find('form').trigger('submit')
  await flushPromises()
  expect(w.text()).toContain('账户ID清单包含重复项')
  expect(api.getScopeCsrf).not.toHaveBeenCalled()
  expect(api.createScope).not.toHaveBeenCalled()
})
it('修改页面筛选立即清除已确认范围，不能继续使用旧快照', async () => {
  const w = mount(ScopePage, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  wrappers.push(w)
  w.findComponent(ScopeMembers).vm.$emit('confirm', snapshot)
  await flushPromises()
  expect(w.find('[aria-label="已选择范围"]').exists()).toBe(true)
  await w.find('input[aria-label="账户名称或外部ID"]').setValue('changed')
  await flushPromises()
  expect(w.find('[aria-label="已选择范围"]').exists()).toBe(false)
})
it('超时后同一意图重用幂等键，修改筛选后换新键；连点只提交一次', async () => {
  api.getScopeCsrf.mockResolvedValue({ csrf_token: 'fixture-token' })
  let rejectFirst!: (error: Error) => void
  api.createScope
    .mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectFirst = reject
        }),
    )
    .mockRejectedValue(new Error('网络中断'))
  const w = mount(ScopePage, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  wrappers.push(w)
  await w.find('form').trigger('submit')
  await w.find('form').trigger('submit')
  await flushPromises()
  expect(api.createScope).toHaveBeenCalledTimes(1)
  const firstKey = api.createScope.mock.calls[0][1]
  rejectFirst(new Error('网络中断'))
  await flushPromises()
  await w.find('form').trigger('submit')
  await flushPromises()
  expect(api.createScope.mock.calls[1][1]).toBe(firstKey)
  await w.find('input[aria-label="账户名称或外部ID"]').setValue('changed')
  await w.find('form').trigger('submit')
  await flushPromises()
  expect(api.createScope.mock.calls[2][1]).not.toBe(firstKey)
})
it('弹窗关闭会取消请求，重新打开后迟到的旧结果不能覆盖新成员', async () => {
  let resolveOld!: (value: typeof memberPage) => void
  api.getScopeMembers
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve
        }),
    )
    .mockResolvedValue(memberPage)
  const w = mount(ScopeMembers, {
    props: { modelValue: true, snapshot },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  wrappers.push(w)
  await flushPromises()
  const signal = api.getScopeMembers.mock.calls[0][4] as AbortSignal
  await w.setProps({ modelValue: false })
  await flushPromises()
  expect(signal.aborted).toBe(true)
  await w.setProps({ modelValue: true })
  await flushPromises()
  resolveOld({
    ...memberPage,
    items: [{ account_id: 'old', external_id: 'old', name: '迟到旧成员' }],
  })
  await flushPromises()
  expect(document.body.textContent).toContain('最新成员')
  expect(document.body.textContent).not.toContain('迟到旧成员')
})
