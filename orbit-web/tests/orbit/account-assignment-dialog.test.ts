/** 分配弹窗服务替身；不声称未来归属已激活或真实数据库/平台验收。 */
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import AssignmentDialog from '@/views/orbit/accounts/AccountAssignmentDialog.vue'
import { ReferenceApiError } from '@/api/orbit/references'
import type { OrbitAccount } from '@/api/orbit/accounts'

const api = vi.hoisted(() => ({
  capabilities: vi.fn(),
  owners: vi.fn(),
  vendors: vi.fn(),
  assign: vi.fn(),
}))
vi.mock('@/api/orbit/account-actions', () => ({
  accountActionsApi: { capabilities: api.capabilities },
}))
vi.mock('@/api/orbit/account-assignment', () => ({ accountAssignmentApi: api }))
const account = {
  id: 'source',
  name: '账户甲',
  external_id: '00001',
  ownership: { owner_user_id: 'old-owner', owner_team_id: 'team' },
  vendor_id: null,
  timezone: { id: 'America/New_York' },
} as OrbitAccount
const owner = { id: 'target', name: '新投手', team_id: 'team', team_name: '真实团队' }
const peer = { ...owner, id: 'peer', name: '另一投手' }
const capability = {
  csrf_token: 'memory-csrf',
  revision: 7,
  next_effective_from: '2026-11-10T05:00:00Z',
}
const ack = { id: account.id, revision: 8, state: 'SCHEDULED', request_id: 'request-id' }
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  api.capabilities.mockResolvedValue(capability)
  api.owners.mockResolvedValue({ items: [owner, peer], next_cursor: null })
  api.vendors.mockResolvedValue({
    items: [{ id: 'vendor', name: '目录原名', alias: null }],
    next_cursor: null,
  })
  api.assign.mockResolvedValue(ack)
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})
async function render() {
  const wrapper = mount(AssignmentDialog, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  wrapper.vm.open(account)
  await flushPromises()
  return wrapper
}
function button(wrapper: ReturnType<typeof mount>, name = '确认未来分配') {
  const value = wrapper.findAll('button').find((node) => node.text() === name)
  if (!value) throw new Error(`找不到按钮：${name}`)
  return value
}
async function selectOwner(wrapper: ReturnType<typeof mount>, value = owner.id) {
  const control = wrapper.findAllComponents(ElSelect)[0]
  control.vm.$emit('update:modelValue', value)
  control.vm.$emit('change', value)
  await flushPromises()
}
async function fill(wrapper: ReturnType<typeof mount>) {
  await selectOwner(wrapper)
  wrapper.findAllComponents(ElSelect)[1].vm.$emit('update:modelValue', '')
  await wrapper.find('textarea').setValue('  转移给明确负责人员  ')
  await flushPromises()
}

it('五字段只用真实候选团队与服务端时间，显式null户商；SCHEDULED不提前改变账户', async () => {
  const wrapper = await render()
  expect(api.capabilities.mock.calls[0].slice(0, 2)).toEqual([account.id, 'ASSIGNMENT'])
  await fill(wrapper)
  expect(api.vendors.mock.calls[0].slice(0, 2)).toEqual([account.id, owner.id])
  expect(wrapper.text()).toContain('America/New_York')
  expect(wrapper.text()).toContain('目标团队：真实团队')
  await button(wrapper).trigger('click')
  await flushPromises()
  expect(api.assign.mock.calls[0][0]).toMatchObject({
    capability,
    body: {
      operator_user_id: owner.id,
      owner_team_id: owner.team_id,
      vendor_id: null,
      effective_from: capability.next_effective_from,
      reason: '转移给明确负责人员',
    },
  })
  expect(Object.keys(api.assign.mock.calls[0][0].body).sort()).toEqual([
    'effective_from',
    'operator_user_id',
    'owner_team_id',
    'reason',
    'vendor_id',
  ])
  expect(wrapper.text()).toContain('当前归属尚未因此提前转移')
  expect(account.ownership.owner_user_id).toBe('old-owner')
  expect(wrapper.emitted('accepted')).toEqual([[ack]])
})

it('换投手默认户商留空，迟到候选不能串投手', async () => {
  let resolve!: (value: unknown) => void
  api.vendors.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  const wrapper = await render()
  await selectOwner(wrapper)
  await selectOwner(wrapper, peer.id)
  const vendors = wrapper.findAllComponents(ElSelect)[1]
  expect(vendors.props('modelValue')).toBe('')
  expect(wrapper.text()).not.toContain('UNSET')
  resolve({
    items: [{ id: 'late-vendor', name: '旧投手迟到户商', alias: '旧代称' }],
    next_cursor: null,
  })
  await flushPromises()
  expect(wrapper.text()).not.toContain('旧投手迟到户商')
  await wrapper.find('textarea').setValue('新投手')
  await button(wrapper).trigger('click')
  await flushPromises()
  expect(api.assign.mock.calls[0][0].body.operator_user_id).toBe(peer.id)
})

it('未知结果关闭重开仍原5字段/key/CAS/时间，不能换新意图', async () => {
  api.assign.mockRejectedValueOnce(new ReferenceApiError(503, 'UNAVAILABLE', '暂不可确认'))
  const wrapper = await render()
  await fill(wrapper)
  await button(wrapper).trigger('click')
  await flushPromises()
  const original = structuredClone(api.assign.mock.calls[0][0])
  expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
  await button(wrapper, '关闭').trigger('click')
  wrapper.vm.open(account)
  await flushPromises()
  expect(api.capabilities).toHaveBeenCalledTimes(1)
  expect(api.owners).toHaveBeenCalledTimes(1)
  await button(wrapper, '重试原分配').trigger('click')
  await flushPromises()
  expect(api.assign.mock.calls[1][0]).toEqual(original)
})

it('明确版本409不报成功，重新取能力后才用新CAS与时刻', async () => {
  api.assign.mockRejectedValueOnce(new ReferenceApiError(409, 'REVISION_CONFLICT', '账户已更新'))
  const wrapper = await render()
  await fill(wrapper)
  await button(wrapper).trigger('click')
  await flushPromises()
  expect(wrapper.emitted('accepted')).toBeUndefined()
  api.capabilities.mockResolvedValue({
    ...capability,
    revision: 8,
    next_effective_from: '2026-11-11T05:00:00Z',
  })
  api.assign.mockResolvedValue({ ...ack, revision: 9 })
  await button(wrapper, '重新读取动作权限与时刻').trigger('click')
  await flushPromises()
  await button(wrapper).trigger('click')
  await flushPromises()
  expect(api.assign.mock.calls[1][0].capability.revision).toBe(8)
  expect(api.assign.mock.calls[1][0].body.effective_from).toBe('2026-11-11T05:00:00Z')
  expect(api.assign.mock.calls[1][0].key).not.toBe(api.assign.mock.calls[0][0].key)
})

it('缺选择、控制字符及无变化不能提交，取消不发写请求', async () => {
  const wrapper = await render()
  expect(button(wrapper).attributes('disabled')).toBeDefined()
  await fill(wrapper)
  for (const text of ['\u200b', '尾部换行\n', '字'.repeat(1001)]) {
    await wrapper.find('textarea').setValue(text)
    expect(button(wrapper).attributes('disabled')).toBeDefined()
  }
  await button(wrapper, '关闭').trigger('click')
  expect(api.assign).not.toHaveBeenCalled()
})

it('候选错误不伪装空资源，无法读取生效时刻不能提交', async () => {
  api.capabilities.mockResolvedValue({ ...capability, next_effective_from: null })
  api.owners.mockRejectedValueOnce(new ReferenceApiError(403, 'FORBIDDEN', '无分配权限'))
  const wrapper = await render()
  expect(wrapper.text()).toContain('服务端未提供可信生效时刻')
  expect(wrapper.text()).toContain('无分配权限')
  expect(button(wrapper).attributes('disabled')).toBeDefined()
  expect(api.assign).not.toHaveBeenCalled()
})
