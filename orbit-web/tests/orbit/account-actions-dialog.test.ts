/** ElementPlus组件与服务替身验证交互；不替代真实Python/数据库/平台验收。 */
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AccountActionDialog from '@/views/orbit/accounts/AccountActionDialog.vue'
import { ReferenceApiError } from '@/api/orbit/references'

const api = vi.hoisted(() => ({ capabilities: vi.fn(), reason: vi.fn() }))
vi.mock('@/api/orbit/account-actions', () => ({ accountActionsApi: api }))
const wrappers: ReturnType<typeof mount>[] = []
const account = { id: 'account-id', name: '账户甲', external_id: '00123' }
const ack = { id: account.id, revision: 6, state: 'WAITING_EXECUTOR', request_id: 'request-id' }

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  api.capabilities.mockResolvedValue({
    csrf_token: 'fixture-csrf',
    revision: 5,
    next_effective_from: null,
  })
  api.reason.mockResolvedValue(ack)
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})
async function render(kind: 'SYNC' | 'UNBIND' = 'SYNC') {
  const wrapper = mount(AccountActionDialog, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  wrapper.vm.open(account, kind)
  await flushPromises()
  return wrapper
}
function button(wrapper: ReturnType<typeof mount>, label: string) {
  const result = wrapper.findAll('button').find((node) => node.text() === label)
  if (!result) throw new Error(`未找到按钮：${label}`)
  return result
}

it('按当前动作取能力，不借导入；原因与当前CAS提交，受理不称同步完成', async () => {
  const wrapper = await render()
  expect(api.capabilities.mock.calls[0].slice(0, 2)).toEqual([account.id, 'SYNC'])
  expect(button(wrapper, '确认受理只读同步').attributes('disabled')).toBeDefined()
  await wrapper.find('textarea').setValue('  重新核对平台资料  ')
  await button(wrapper, '确认受理只读同步').trigger('click')
  await flushPromises()
  expect(api.reason.mock.calls[0][0]).toMatchObject({
    accountId: account.id,
    action: 'SYNC',
    reason: '重新核对平台资料',
    capability: { revision: 5 },
  })
  expect(wrapper.text()).toContain('只读同步已受理，尚未确认执行结果')
  expect(wrapper.emitted('accepted')).toEqual([[ack]])
})

it('本地解绑有明确边界，取消不提交', async () => {
  api.reason.mockResolvedValue({ ...ack, state: 'SUCCEEDED' })
  const wrapper = await render('UNBIND')
  expect(wrapper.text()).toContain('平台广告、凭据和历史事实保留')
  await wrapper.find('textarea').setValue('不再关联')
  await button(wrapper, '关闭').trigger('click')
  expect(api.reason).not.toHaveBeenCalled()
  wrapper.vm.open(account, 'UNBIND')
  await flushPromises()
  await wrapper.find('textarea').setValue('只解绑本地关联')
  await button(wrapper, '确认本地解绑').trigger('click')
  await flushPromises()
  expect(api.reason.mock.calls[0][0].action).toBe('UNBIND')
  expect(wrapper.text()).toContain('本地解绑已完成，平台广告及历史事实保留')
})

it('网络不确定锁定内容并重试同一key，关闭重开也不生成新意图', async () => {
  api.reason.mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '网络中断'))
  const wrapper = await render()
  await wrapper.find('textarea').setValue('保留原请求')
  await button(wrapper, '确认受理只读同步').trigger('click')
  await flushPromises()
  const first = structuredClone(api.reason.mock.calls[0][0])
  expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
  await button(wrapper, '关闭').trigger('click')
  wrapper.vm.open(account, 'SYNC')
  await flushPromises()
  expect(api.capabilities).toHaveBeenCalledTimes(1)
  expect(wrapper.text()).toContain('原请求结果尚未确认')
  await button(wrapper, '重试原请求').trigger('click')
  await flushPromises()
  expect(api.reason.mock.calls[1][0]).toEqual(first)
  expect(wrapper.emitted('accepted')).toEqual([[ack]])
})

it('Unicode上限按码点，拒绝末尾换行和隐藏格式字符', async () => {
  const wrapper = await render()
  await wrapper.find('textarea').setValue('😀'.repeat(1000))
  expect(button(wrapper, '确认受理只读同步').attributes('disabled')).toBeUndefined()
  for (const reason of ['字'.repeat(1001), '原因\n', '原因\u200b']) {
    await wrapper.find('textarea').setValue(reason)
    expect(button(wrapper, '确认受理只读同步').attributes('disabled')).toBeDefined()
  }
  expect(api.reason).not.toHaveBeenCalled()
})

it('动作403显式展示，不显示假成功；能力失败可重读', async () => {
  api.capabilities.mockRejectedValueOnce(new ReferenceApiError(403, 'FORBIDDEN', '无同步权限'))
  const wrapper = await render()
  expect(wrapper.text()).toContain('无同步权限')
  expect(api.reason).not.toHaveBeenCalled()
  await button(wrapper, '重新读取动作权限').trigger('click')
  await flushPromises()
  await wrapper.find('textarea').setValue('恢复后核验')
  api.reason.mockRejectedValueOnce(new ReferenceApiError(403, 'CSRF_INVALID', '会话已变更'))
  await button(wrapper, '确认受理只读同步').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('会话已变更')
  expect(wrapper.emitted('accepted')).toBeUndefined()
})

it('迟到能力不能覆盖新账户或新动作', async () => {
  let resolve!: (value: unknown) => void
  api.capabilities.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  const wrapper = await render()
  wrapper.vm.open({ ...account, id: 'account-new' }, 'UNBIND')
  await flushPromises()
  resolve({ csrf_token: 'late-csrf', revision: 999, next_effective_from: null })
  await flushPromises()
  await wrapper.find('textarea').setValue('新的账户动作')
  api.reason.mockResolvedValue({ ...ack, id: 'account-new', state: 'SUCCEEDED' })
  await button(wrapper, '确认本地解绑').trigger('click')
  await flushPromises()
  expect(api.reason.mock.calls[0][0]).toMatchObject({
    accountId: 'account-new',
    action: 'UNBIND',
    capability: { revision: 5 },
  })
})
