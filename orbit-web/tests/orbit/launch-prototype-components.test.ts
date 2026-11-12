import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { it, expect, vi, afterEach } from 'vitest'
import { newDraft } from '@/api/orbit/launch-form'
import { prototypeCampaign } from '@/api/orbit/launch-prototype'
import Fields from '@/views/orbit/launch/PrototypeCampaignFields.vue'
import Accounts from '@/views/orbit/launch/PrototypeAccountTable.vue'
import { accountApi, type OrbitAccount } from '@/api/orbit/accounts'
afterEach(() => vi.restoreAllMocks())
it('原型页签复制父级生成独立后代，份数归一，删除确认前不修改', async () => {
  const form = newDraft({ owner_user_id: 'u', owner_team_id: 't' })
  form.campaigns = [prototypeCampaign()]
  form.campaigns[0].copies = 4
  const w = mount(Fields, {
    props: { form, campaignName: '渠道·投放师' },
    global: { plugins: [ElementPlus] },
  })
  await w
    .findAll('button')
    .find((b) => b.text() === '复制当前系列')!
    .trigger('click')
  expect(form.campaigns).toHaveLength(2)
  expect(form.campaigns[1].copies).toBe(1)
  expect(form.campaigns[1].adsets[0].ads[0].local_id).not.toBe(
    form.campaigns[0].adsets[0].ads[0].local_id,
  )
  expect(w.emitted('clone-branch')?.[0][0]).toHaveProperty(
    form.campaigns[0].local_id,
    form.campaigns[1].local_id,
  )
  const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
  await w
    .findAll('button')
    .find((b) => b.text() === '删除')!
    .trigger('click')
  await flushPromises()
  expect(form.campaigns).toHaveLength(2)
  confirm.mockResolvedValue('confirm')
  await w
    .findAll('button')
    .find((b) => b.text() === '删除')!
    .trigger('click')
  await flushPromises()
  expect(form.campaigns).toHaveLength(1)
  w.unmount()
})
it('账户表批选只收当前负责人且授权有效账户，未知余额不补零', async () => {
  const row = (id: string, owner: string, status = 'AUTHORIZED') =>
    ({
      id,
      name: id,
      external_id: id,
      ownership: { owner_user_id: owner, owner_team_id: 't' },
      auth_status: status,
      account_status: 'ACTIVE',
      currency: 'USD',
      balance: { amount: null },
    }) as OrbitAccount
  vi.spyOn(accountApi, 'list').mockResolvedValue({
    items: [row('allowed', 'u'), row('other', 'other'), row('expired', 'u', 'EXPIRED')],
    next_cursor: null,
    data_as_of: 'today',
    scope_version: 1,
  })
  const w = mount(Accounts, {
    props: { selected: [], ownership: { owner_user_id: 'u', owner_team_id: 't' }, canRead: true },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  await w
    .findAll('button')
    .find((b) => b.text() === '选择当前筛选中的可用账户')!
    .trigger('click')
  expect(w.emitted('update:selected')?.[0][0]).toEqual(['allowed'])
  expect(w.text()).toContain('— USD')
  expect(w.text()).not.toContain('0.00')
  w.unmount()
})
