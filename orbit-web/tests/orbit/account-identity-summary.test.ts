/** 摘要显示及原身份读取组件纯测；不代替真实数据库/Meta。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import Drawer from '@/views/orbit/accounts/AccountDetailsDrawer.vue'

const api = vi.hoisted(() => ({ get: vi.fn(), identities: vi.fn() }))
vi.mock('@/api/orbit/account-details', async (original) => ({
  ...(await original<typeof import('@/api/orbit/account-details')>()),
  accountDetailsApi: api,
}))
const wrappers: ReturnType<typeof mount>[] = []
const observation = { value: null, status: 'UNSYNCED', source: 'NOT_PROVIDED', observed_at: null }
const amount = { amount: null, status: 'UNSYNCED', source: 'NOT_PROVIDED', observed_at: null }
function fixture(status: string, count: number | null, observed: string | null) {
  return {
    account: {
      id: 'account',
      name: '账户甲',
      external_id: '00012',
      ownership: { owner_user_id: 'owner', owner_team_id: 'team' },
      auth_status: 'UNKNOWN',
      account_status: 'UNKNOWN',
      timezone: { display_label: 'UTC' },
      synced_at: null,
      balance: amount,
      spend: amount,
    },
    details: {
      personal_profile: observation,
      business_entity: observation,
      payment_type: observation,
      payment_method: observation,
      blocked_reason: observation,
      vendor_display: { source: 'NOT_PROVIDED' },
      business_managers: null,
      payable: amount,
      lifetime_spend: amount,
      spend_window: { coverage: 'NOT_COLLECTED' },
      identity_status: status,
      identity_count: count,
      identity_observed_at: observed,
    },
  }
}
beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
})
async function open(status: string, count: number | null, observed: string | null) {
  api.get.mockResolvedValue(fixture(status, count, observed))
  const wrapper = mount(Drawer, { attachTo: document.body, global: { plugins: [ElementPlus] } })
  wrappers.push(wrapper)
  ;(wrapper.vm as unknown as { open(id: string, query: URLSearchParams): void }).open(
    'account',
    new URLSearchParams(),
  )
  await flushPromises()
  return wrapper
}
function summary() {
  return [...document.querySelectorAll('.account-identity-summary tr')].map(
    (row) => row.textContent,
  )
}
it.each([
  ['SYNCED', 0, '2026-11-09T00:00:00Z', '已同步', '0'],
  ['SYNCED', 3, '2026-11-09T00:00:00Z', '已同步', '3'],
  ['UNSYNCED', null, null, '未同步', '未知'],
  ['UNKNOWN', null, null, '未知', '未知'],
  ['UNKNOWN', 0, null, '未知', '未知'],
  ['SYNCED', null, null, '已同步', '未知'],
  ['SYNCED', -1, null, '已同步', '未知'],
  ['SYNCED', 0.5, null, '已同步', '未知'],
])('摘要严格区分状态与计数 %s/%s', async (status, count, observed, label, total) => {
  await open(String(status), count as number | null, observed as string | null)
  expect(summary()[0]).toBe(`身份同步状态${label}`)
  expect(summary()[1]).toBe(`身份资源数量${total}`)
  expect(summary()[2]).toContain(observed ? '（本地时间）' : '未提供/未知')
  expect(document.body.textContent).toContain(
    status === 'UNSYNCED' ? '尚未同步身份资源' : '尚未读取身份资源',
  )
  expect(api.identities).not.toHaveBeenCalled()
})
it('摘要不代替身份GET，原读取与刷新流程保留', async () => {
  await open('SYNCED', 0, '2026-11-09T00:00:00Z')
  api.identities.mockResolvedValue({
    account_id: 'account',
    resources: [],
    capability_version: 'observed-only',
    observed_at: '2026-11-09T00:00:00Z',
  })
  const read = [...document.querySelectorAll('button')].find((button) =>
    button.textContent?.includes('读取身份资源'),
  )!
  read.click()
  await flushPromises()
  expect(api.identities).toHaveBeenCalledTimes(1)
  expect(document.body.textContent).toContain('本次已观测快照中没有身份资源')
  expect(document.body.textContent).not.toContain('尚未读取身份资源')
  read.click()
  await flushPromises()
  expect(api.identities).toHaveBeenCalledTimes(2)
  expect(summary()[1]).toBe('身份资源数量0')
})
