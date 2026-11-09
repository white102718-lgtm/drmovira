import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton } from 'element-plus'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Page from '@/views/orbit/environments/index.vue'
import BindingPanel from '@/views/orbit/environments/ProfileBindingsPanel.vue'
import AgentMonitorPanel from '@/views/orbit/environments/AgentMonitorPanel.vue'
import { environmentApi } from '@/api/orbit/environments'
import { bindingApi } from '@/api/orbit/environments-bindings'
import { monitorApi } from '@/api/orbit/environments-monitor'
const user = vi.hoisted(() => ({
  id: 1,
  permissions: ['environments.read', 'environments.enroll'],
}))
vi.mock('@/store/modules/user', () => ({ default: () => user }))
const id = '00000000-0000-0000-0000-000000000001'
const agent = {
  id,
  revision: 1,
  name: '机器',
  endpoint: 'http://127.0.0.1:50325',
  probe_interval: 30,
  state: 'OFFLINE' as const,
  last_heartbeat: null,
}
const report = {
  agent_id: id,
  machine_state: 'SUSPECT' as const,
  last_heartbeat: '2026-11-09T00:00:00Z',
  api_status: 'READY' as const,
  inventory_coverage: 'ACTIVE_ONLY' as const,
  last_error: null,
  received_at: '2026-11-09T00:00:00Z',
}
let w: VueWrapper
beforeEach(() => {
  vi.spyOn(environmentApi, 'capabilities').mockImplementation(async (op) => ({
    actor_id: 1,
    tenant_id: id,
    data_role: 'SUPER_ADMIN',
    csrf_token: op === 'READ' ? null : 'abcdefghijklmnop',
  }))
  vi.spyOn(environmentApi, 'list').mockResolvedValue({
    items: [agent],
    next_cursor: null,
    data_as_of: '2026-11-09T00:00:00Z',
    scope_version: 1,
  })
  vi.spyOn(environmentApi, 'get').mockResolvedValue(agent)
  vi.spyOn(bindingApi, 'list').mockResolvedValue({
    items: [],
    next_cursor: null,
    data_as_of: '2026-11-09T00:00:00Z',
    scope_version: 1,
  })
  vi.spyOn(monitorApi, 'get').mockResolvedValue(report)
  vi.spyOn(monitorApi, 'profiles').mockResolvedValue({
    items: [
      {
        id,
        agent_id: id,
        external_profile_id: 'chosen-profile',
        process_state: 'ACTIVE',
        identity_state: 'UNKNOWN',
        account_ids: [],
        observed_at: '2026-11-09T00:00:00Z',
      },
    ],
    next_cursor: null,
    data_as_of: '2026-11-09T00:00:00Z',
    scope_version: 1,
  })
})
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function click(label: string) {
  const b = w.findAllComponents(ElButton).find((b) => b.text() === label)
  expect(b, label).toBeTruthy()
  await b!.trigger('click')
  await flushPromises()
}
async function input(label: string, value: string) {
  const element = document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!
  element.value = value
  element.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
it('device detail loads real monitor and stops it immediately on close', async () => {
  w = mount(Page, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  await click('详情')
  expect(monitorApi.get).toHaveBeenCalledWith(id, expect.any(AbortSignal))
  expect(document.body.textContent).toContain('心跳疑似中断')
  await click('关闭')
  expect(
    w.findComponent(AgentMonitorPanel).exists()
      ? w.findComponent(AgentMonitorPanel).props('active')
      : false,
  ).toBe(false)
})
it('binding profile picker uses observed ID only and keeps manual fields and UNKNOWN semantics', async () => {
  w = mount(BindingPanel, {
    props: { modelValue: true, canRead: true, canWrite: true },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  await click('新增关联')
  await input('Agent ID', id)
  await click('从设备观察选择 Profile')
  await click('选择此 Profile')
  expect((document.querySelector('input[aria-label="Profile ID"]') as HTMLInputElement).value).toBe(
    'chosen-profile',
  )
  await input('Profile ID', 'manual-profile')
  expect((document.querySelector('input[aria-label="Profile ID"]') as HTMLInputElement).value).toBe(
    'manual-profile',
  )
  expect(document.body.textContent).toContain('选择不会改变身份核验状态')
})
it('enroll-only retains manual profile input without attempting monitor reads', async () => {
  w = mount(BindingPanel, {
    props: { modelValue: true, canRead: false, canWrite: true },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  await click('新增关联')
  await input('Agent ID', id)
  expect(document.body.textContent).toContain('无环境读取权限')
  expect(monitorApi.get).not.toHaveBeenCalled()
  expect(monitorApi.profiles).not.toHaveBeenCalled()
})
it('superadmin with probe action can confirm a new request and retains it after closing detail', async () => {
  const { probeApi } = await import('@/api/orbit/environments-probe')
  user.permissions.push('environments.probe')
  const submit = vi
    .spyOn(probeApi, 'submit')
    .mockResolvedValue({ id, revision: 1, state: 'QUEUED', request_id: id })
  vi.spyOn(probeApi, 'get').mockResolvedValue({
    id,
    agent_id: id,
    state: 'QUEUED',
    created_at: '2026-11-09T00:00:00Z',
    expires_at: '2026-11-09T00:02:00Z',
    completed_at: null,
    error_code: null,
  })
  w = mount(Page, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
  await click('详情')
  await click('主动只读探测')
  await click('确认开始探测')
  expect(submit).toHaveBeenCalledTimes(1)
  await click('关闭')
  await click('详情')
  expect(document.body.textContent).toContain('等待设备执行')
  expect(submit).toHaveBeenCalledTimes(1)
  user.permissions.pop()
})
