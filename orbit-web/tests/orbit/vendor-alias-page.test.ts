import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import VendorAliases from '@/views/orbit/channels/VendorAliases.vue'
import { vendorAliasApi } from '@/api/orbit/vendor-aliases'
import { ReferenceApiError, type ReferenceRecord } from '@/api/orbit/references'

const item: ReferenceRecord = {
  value: {
    id: 'vendor',
    kind: 'VENDOR',
    name: '完整名称',
    source_key: 'source',
    availability: 'AVAILABLE',
    owner_team_id: 'team',
    data_owner_user_ids: ['user'],
  },
  revision: 1,
  catalog_revision: 1,
  updated_at: '',
}
const current = {
  vendor_id: 'vendor',
  alias: null,
  revision: 1,
  updated_at: null,
  catalog_revision: 1,
}
let wrapper: VueWrapper
beforeEach(() => {
  vi.spyOn(vendorAliasApi, 'capabilities').mockResolvedValue({
    can_manage: true,
    csrf_token: 'csrf',
  })
  vi.spyOn(vendorAliasApi, 'batch').mockResolvedValue({ items: [current], catalog_revision: 1 })
  vi.spyOn(vendorAliasApi, 'get').mockResolvedValue(current)
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

async function click(label: string) {
  const target = [...document.querySelectorAll('button')].find(
    (button) => button.textContent?.trim() === label,
  )
  expect(target).toBeTruthy()
  target!.click()
  await flushPromises()
}
async function fill(value: string, reason: string) {
  const alias = document.querySelector<HTMLInputElement>(
    'input[placeholder="请填写真实代称，不从名称推算"]',
  )!
  alias.value = value
  alias.dispatchEvent(new Event('input', { bubbles: true }))
  const textarea = document.querySelector('textarea')!
  textarea.value = reason
  textarea.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
async function open() {
  wrapper = mount(VendorAliases, {
    props: { vendors: [item] },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  await click('维护代称')
  await fill('真实代称', '维护原因')
}

it('网络结果未知时冻结字段，并使用相同正文版本和键重试', async () => {
  const save = vi
    .spyOn(vendorAliasApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '结果未知'))
    .mockResolvedValueOnce({ ...current, alias: '真实代称', revision: 2 })
  await open()
  await click('确认维护代称')
  expect(document.body.textContent).toContain('上次提交结果未知')
  expect(
    document.querySelector<HTMLInputElement>('input[placeholder="请填写真实代称，不从名称推算"]')!
      .disabled,
  ).toBe(true)
  await click('使用原幂等键重试')
  expect(save.mock.calls[0]).toEqual(save.mock.calls[1])
  expect(wrapper.emitted('changed')).toHaveLength(1)
})

it('CAS冲突必须重新读取，随后提交使用新版本与新键', async () => {
  const save = vi
    .spyOn(vendorAliasApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(409, 'REVISION_CONFLICT', '代称已修改'))
    .mockResolvedValueOnce({ ...current, alias: '再维护', revision: 3 })
  await open()
  await click('确认维护代称')
  expect(document.body.textContent).toContain('代称已修改')
  vi.mocked(vendorAliasApi.get).mockResolvedValueOnce({
    ...current,
    alias: '其他人维护',
    revision: 2,
  })
  await click('重新读取当前值')
  await fill('再维护', '基于当前版本')
  await click('确认维护代称')
  expect(save.mock.calls[0][2]).toBe(1)
  expect(save.mock.calls[1][2]).toBe(2)
  expect(save.mock.calls[0][4]).not.toBe(save.mock.calls[1][4])
})

it('没有维护动作时仍可读真实代称，不展示维护按钮', async () => {
  vi.mocked(vendorAliasApi.capabilities).mockResolvedValue({
    can_manage: false,
    csrf_token: 'csrf',
  })
  vi.mocked(vendorAliasApi.batch).mockResolvedValue({
    items: [{ ...current, alias: '真实只读代称' }],
    catalog_revision: 1,
  })
  wrapper = mount(VendorAliases, {
    props: { vendors: [item] },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  expect(wrapper.text()).toContain('真实只读代称')
  expect(wrapper.text()).not.toContain('维护代称')
})
