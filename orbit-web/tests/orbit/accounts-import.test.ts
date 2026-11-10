/** 组件服务替身只验证导入交互与未知结果，不代表真实平台绑定。 */
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import ImportAccounts from '@/views/orbit/accounts/ImportAccounts.vue'
import { ReferenceApiError } from '@/api/orbit/references'

const api = vi.hoisted(() => ({
  capabilities: vi.fn(),
  owners: vi.fn(),
  createImport: vi.fn(),
  getImport: vi.fn(),
  list: vi.fn(),
}))
vi.mock('@/api/orbit/accounts', () => ({ accountApi: api }))
vi.mock('@/api/orbit/references', async (original) => ({
  ...(await original<typeof import('@/api/orbit/references')>()),
  referenceApi: { list: api.list },
}))
const person = { id: 'person', name: '投手甲', team_id: 'team', team_name: '团队甲' }
const batch = {
  id: 'batch',
  revision: 1,
  vendor_id: 'vendor',
  state: 'QUEUED',
  total: 1,
  success_count: 0,
  failed_count: 0,
  duplicate_count: 0,
  rows: [
    {
      id: 'row',
      token_index: 0,
      line_no: 1,
      column: 1,
      raw_display: '0001',
      normalized_id: '0001',
      duplicate_of: null,
      state: 'WAITING',
      account_id: null,
      name: null,
      spend: { amount: null, currency: 'XXX' },
      retryable: false,
      error_code: null,
      observed_at: null,
    },
  ],
  next_cursor: null,
}
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  api.capabilities.mockResolvedValue({ csrf_token: 'fixture-csrf' })
  api.owners.mockResolvedValue({ items: [person], next_cursor: null })
  api.list.mockResolvedValue({
    items: [{ value: { id: 'vendor', name: '户商甲', availability: 'AVAILABLE' } }],
    next_cursor: null,
  })
})
afterEach(() => {
  wrappers.forEach((wrapper) => wrapper.unmount())
  wrappers.length = 0
  document.body.innerHTML = ''
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})
async function render() {
  const wrapper = mount(ImportAccounts, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  await wrapper.vm.open()
  await flushPromises()
  return wrapper
}
function button(wrapper: ReturnType<typeof mount>, title: string) {
  const found = wrapper.findAll('button').find((item) => item.text() === title)
  if (!found) throw new Error(`未找到按钮：${title}`)
  return found
}
async function fill(wrapper: ReturnType<typeof mount>, text = 'act_0001') {
  const owner = wrapper.findAllComponents(ElSelect)[0]
  owner.vm.$emit('update:modelValue', person.id)
  owner.vm.$emit('change', person.id)
  await flushPromises()
  wrapper.findAllComponents(ElSelect)[1].vm.$emit('update:modelValue', 'vendor')
  await wrapper.find('textarea').setValue(text)
  await flushPromises()
}
describe('账户导入弹窗，服务替身范围', () => {
  it('按目标owner读取户商，原始文本与前导零直接提交，排队不称平台成功', async () => {
    api.createImport.mockResolvedValue(batch)
    const wrapper = await render()
    await fill(wrapper)
    expect(api.list.mock.calls[0][0]).toBe('VENDOR')
    expect(api.list.mock.calls[0][1].get('owner_user_id')).toBe('person')
    await button(wrapper, '预检并提交导入').trigger('click')
    await flushPromises()
    expect(api.createImport.mock.calls[0][0]).toEqual({
      vendor_id: 'vendor',
      owner_user_id: 'person',
      owner_team_id: 'team',
      account_ids_text: 'act_0001',
    })
    expect(wrapper.text()).toContain('批次尚未完成')
    expect(wrapper.text()).toContain('未提供/未知')
    expect(wrapper.text()).toContain('状态：已排队')
    expect(wrapper.emitted('accepted')).toHaveLength(1)
  })
  it('户商留空仍能提交，明确传null并保留投手团队', async () => {
    api.createImport.mockResolvedValue({ ...batch, vendor_id: null })
    const wrapper = await render()
    await fill(wrapper)
    wrapper.findAllComponents(ElSelect)[1].vm.$emit('update:modelValue', '')
    await flushPromises()
    expect(button(wrapper, '预检并提交导入').attributes('disabled')).toBeUndefined()
    await button(wrapper, '预检并提交导入').trigger('click')
    await flushPromises()
    expect(api.createImport.mock.calls[0][0]).toMatchObject({
      vendor_id: null,
      owner_user_id: 'person',
      owner_team_id: 'team',
    })
  })
  it('原始501重复项仍超限，不能仅凭去重后1项提交', async () => {
    const wrapper = await render()
    await fill(wrapper, '1 '.repeat(501))
    expect(button(wrapper, '预检并提交导入').attributes('disabled')).toBeDefined()
    expect(api.createImport).not.toHaveBeenCalled()
  })
  it('结果未知时锁定意图并重用同一幂等键', async () => {
    api.createImport
      .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '网络中断'))
      .mockResolvedValueOnce(batch)
    const wrapper = await render()
    await fill(wrapper)
    await button(wrapper, '预检并提交导入').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('本次提交结果尚未确认')
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
    await button(wrapper, '重试本次导入').trigger('click')
    await flushPromises()
    expect(api.createImport.mock.calls[0]).toEqual(api.createImport.mock.calls[1])
  })
  it('没有户商候选时给出导入分配指引，不退化成自由文本', async () => {
    api.list.mockResolvedValue({ items: [], next_cursor: null })
    const wrapper = await render()
    await fill(wrapper)
    expect(wrapper.text()).toContain('请联系管理员导入并分配户商引用资料')
    expect(api.createImport).not.toHaveBeenCalled()
  })
})
