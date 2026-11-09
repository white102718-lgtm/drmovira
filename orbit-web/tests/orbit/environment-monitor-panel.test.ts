import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton } from 'element-plus'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Panel from '@/views/orbit/environments/AgentMonitorPanel.vue'
import { monitorApi } from '@/api/orbit/environments-monitor'
import { AgentApiError } from '@/api/orbit/environments'
const id = '00000000-0000-0000-0000-000000000001'
const report = {
  agent_id: id,
  machine_state: 'SUSPECT' as const,
  last_heartbeat: '2026-11-09T00:00:00Z',
  api_status: 'READY' as const,
  inventory_coverage: 'ACTIVE_ONLY' as const,
  last_error: null,
  received_at: '2026-11-09T00:00:00Z',
}
const profile = {
  id,
  agent_id: id,
  external_profile_id: 'active-only-profile',
  process_state: 'ACTIVE' as const,
  identity_state: 'UNKNOWN' as const,
  account_ids: [id],
  observed_at: '2026-11-09T00:00:00Z',
}
const page = {
  items: [profile],
  next_cursor: null,
  data_as_of: '2026-11-09T00:00:00Z',
  scope_version: 1,
}
let w: VueWrapper
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  vi.spyOn(monitorApi, 'get').mockResolvedValue(report)
  vi.spyOn(monitorApi, 'profiles').mockResolvedValue(page)
})
afterEach(() => {
  w?.unmount()
  vi.useRealTimers()
  vi.restoreAllMocks()
})
async function start(props = {}) {
  w = mount(Panel, {
    props: { agentId: id, active: true, ...props },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
async function click(label: string) {
  const b = w.findAllComponents(ElButton).find((b) => b.text() === label)
  expect(b, label).toBeTruthy()
  await b!.trigger('click')
  await flushPromises()
}
it('shows server suspect state, limited active inventory, unknown identity and original profile fields', async () => {
  await start()
  for (const text of [
    '心跳疑似中断',
    '仅活跃 Profile',
    '不代表完整清单',
    'active-only-profile',
    '未取得新鲜身份核验',
    '账户 ID',
    '观察时刻',
  ])
    expect(w.text()).toContain(text)
  expect(w.text()).not.toContain('身份有效（服务端核验）')
})
it('polls every 15 seconds without inferring online status from local clock', async () => {
  await start()
  await vi.advanceTimersByTimeAsync(15000)
  await flushPromises()
  expect(monitorApi.get).toHaveBeenCalledTimes(2)
  expect(w.text()).toContain('心跳疑似中断')
})
it('pause stops polling and labels retained observations as historical', async () => {
  await start()
  await click('暂停自动刷新')
  await vi.advanceTimersByTimeAsync(45000)
  expect(monitorApi.get).toHaveBeenCalledTimes(1)
  expect(w.text()).toContain('已暂停')
  await click('恢复自动刷新')
  expect(monitorApi.get).toHaveBeenCalledTimes(2)
})
it('closing or unmounting cancels requests and leaves no polling', async () => {
  await start()
  const signal = vi.mocked(monitorApi.get).mock.calls[0][1]!
  await w.setProps({ active: false })
  expect(signal.aborted).toBe(true)
  await vi.advanceTimersByTimeAsync(30000)
  expect(monitorApi.get).toHaveBeenCalledTimes(1)
  w.unmount()
  await vi.advanceTimersByTimeAsync(30000)
  expect(monitorApi.get).toHaveBeenCalledTimes(1)
})
it('monitor forbidden does not hide independently permitted profiles', async () => {
  vi.mocked(monitorApi.get).mockRejectedValue(new AgentApiError(403, 'FORBIDDEN', '无权限'))
  await start()
  expect(w.text()).toContain('无监测读取权限')
  expect(w.text()).toContain('active-only-profile')
  expect(w.text()).toContain('覆盖范围未知')
})
it('stale or inaccessible profiles are cleared instead of kept as current evidence', async () => {
  await start()
  vi.mocked(monitorApi.profiles).mockRejectedValue(
    new AgentApiError(403, 'FORBIDDEN', '范围已变化'),
  )
  await click('刷新监测结果')
  expect(w.text()).not.toContain('active-only-profile')
  expect(w.text()).toContain('无 Profile 读取权限')
})
it('profile selection is opt-in and emits only the external ID, never valid identity', async () => {
  await start({ selectable: true })
  await click('选择此 Profile')
  expect(w.emitted('select')?.[0]).toEqual(['active-only-profile'])
  expect(w.emitted('verified')).toBeUndefined()
})
it('new agent cancels stale response and never displays previous device profiles', async () => {
  let resolve!: (v: typeof page) => void
  vi.mocked(monitorApi.profiles).mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await start()
  await w.setProps({ agentId: '00000000-0000-0000-0000-000000000002' })
  await flushPromises()
  resolve({ ...page, items: [{ ...profile, external_profile_id: 'stale-old-agent' }] })
  await flushPromises()
  expect(w.text()).not.toContain('stale-old-agent')
})
it('external completed probe refreshes observations without clearing applied Profile query', async () => {
  await start({ refreshKey: 0 })
  await w.get('input[aria-label="Profile 查询"]').setValue('keep-query')
  await click('查询 Profile')
  const before = vi.mocked(monitorApi.profiles).mock.calls.length
  await w.setProps({ refreshKey: 1 })
  await flushPromises()
  expect(monitorApi.profiles).toHaveBeenCalledTimes(before + 1)
  expect(vi.mocked(monitorApi.profiles).mock.lastCall?.[1]).toMatchObject({ q: 'keep-query' })
})
