/** 真实ElementPlus+诊断服务替身，仅证明交互/晚到隔离，不计真实后台验收。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AccountCommandStatus from '@/views/orbit/accounts/AccountCommandStatus.vue'
import { ReferenceApiError } from '@/api/orbit/references'
const api = vi.hoisted(() => ({ status: vi.fn() }))
vi.mock('@/api/orbit/account-command', () => ({ accountCommandApi: api }))
const wrappers: ReturnType<typeof mount>[] = []
const value = {
  command_id: 'command-uuid',
  account_id: 'account-id',
  kind: 'SYNC',
  accepted_request_id: 'accepted-request',
  revision: 3,
  state: 'WAITING_RETRY',
  attempt_count: 1,
  last_error_code: null,
  effective_from: null,
  next_attempt_at: '2026-11-08T01:02:03.123Z',
  created_at: '2026-11-08T00:00:00.000Z',
  updated_at: '2026-11-08T01:00:00.000Z',
  completed_at: null,
}
beforeEach(() => {
  api.status.mockResolvedValue(value)
})
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount())
  vi.resetAllMocks()
})
function render(kind: 'SYNC' | 'UNBIND' | 'ASSIGNMENT' = 'SYNC') {
  const w = mount(AccountCommandStatus, {
    props: { accountId: 'account-id', kind, requestId: 'accepted-request' },
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(w)
  return w
}
it('显式查询前不发请求，真实状态、编号、UTC和null可区分且没有写控件', async () => {
  const w = render()
  expect(api.status).not.toHaveBeenCalled()
  await w.find('button').trigger('click')
  await flushPromises()
  expect(api.status.mock.calls[0].slice(0, 3)).toEqual(['account-id', 'SYNC', 'accepted-request'])
  expect(w.text()).toContain('WAITING_RETRY')
  expect(w.text()).toContain('command-uuid')
  expect(w.text()).toContain('accepted-request')
  expect(w.text()).toContain('未提供（null）')
  expect(w.text()).toContain('2026-11-08T01:02:03.123Z')
  expect(w.findAll('button')).toHaveLength(1)
  expect(w.find('button').text()).toBe('刷新当前状态')
})
it.each([401, 403, 404, 503])('读取失败%s清除旧状态但明确原回执保留', async (status) => {
  const w = render()
  await w.find('button').trigger('click')
  await flushPromises()
  api.status.mockRejectedValueOnce(new ReferenceApiError(status, 'DENIED', '不展示内部原文'))
  await w.find('button').trigger('click')
  await flushPromises()
  expect(w.text()).not.toContain('command-uuid')
  expect(w.text()).not.toContain('WAITING_RETRY')
  expect(w.text()).not.toContain('不展示内部原文')
  expect(w.text()).toContain('原受理回执保留')
})
it('换账户或原请求后晚到旧读取不得回填，重新查询仅当前关联', async () => {
  let resolve!: (v: typeof value) => void
  api.status.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r
    }),
  )
  const w = render()
  await w.find('button').trigger('click')
  const signal = api.status.mock.calls[0][3] as AbortSignal
  expect(api.status.mock.calls[0]).toHaveLength(4)
  await w.setProps({ accountId: 'other', requestId: 'other-request' })
  expect(signal.aborted).toBe(true)
  resolve(value)
  await flushPromises()
  expect(w.text()).not.toContain('command-uuid')
  expect(w.find('button').text()).toBe('查询当前状态')
})
it.each([
  ['SYNC', '只读元数据同步已完成，不表示金额采集或广告写入成功。'],
  ['ASSIGNMENT', '当前分配投影已激活，历史事实保持原冻结归属。'],
  ['UNBIND', '仅本地解绑已完成，平台广告及历史事实保留。'],
] as const)('成功说明按%s真实动作边界，不冒充统一Task', async (kind, meaning) => {
  api.status.mockResolvedValue({ ...value, kind, state: 'SUCCEEDED' })
  const w = render(kind)
  await w.find('button').trigger('click')
  await flushPromises()
  expect(w.text()).toContain(meaning)
})
