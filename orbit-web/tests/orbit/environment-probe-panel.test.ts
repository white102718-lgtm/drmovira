import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton } from 'element-plus'
import { reactive } from 'vue'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Panel from '@/views/orbit/environments/AgentProbePanel.vue'
import { probeApi, newProbeSession, type ProbeSession } from '@/api/orbit/environments-probe'
import { environmentApi, AgentApiError } from '@/api/orbit/environments'
const id = '00000000-0000-0000-0000-000000000001',
  req = '00000000-0000-0000-0000-000000000002'
const cap = {
  actor_id: 1,
  tenant_id: id,
  data_role: 'SUPER_ADMIN' as const,
  csrf_token: 'abcdefghijklmnop',
}
const queued = {
  id: req,
  agent_id: id,
  state: 'QUEUED' as const,
  created_at: '2026-11-09T00:00:00Z',
  expires_at: '2026-11-09T00:02:00Z',
  completed_at: null,
  error_code: null,
}
let w: VueWrapper, session: ProbeSession
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  session = reactive(newProbeSession())
  vi.spyOn(environmentApi, 'capabilities').mockResolvedValue(cap)
  vi.spyOn(probeApi, 'submit').mockResolvedValue({
    id: req,
    revision: 1,
    state: 'QUEUED',
    request_id: id,
  })
  vi.spyOn(probeApi, 'get').mockResolvedValue(queued)
})
afterEach(() => {
  w?.unmount()
  vi.useRealTimers()
  vi.restoreAllMocks()
})
async function start(extra = {}) {
  w = mount(Panel, {
    props: {
      agentId: id,
      revision: 4,
      actorId: 1,
      tenantId: id,
      canProbe: true,
      active: true,
      session,
      ...extra,
    },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
async function click(text: string) {
  const b = w.findAllComponents(ElButton).find((x) => x.text() === text)
  expect(b, text).toBeTruthy()
  await b!.trigger('click')
  await flushPromises()
}
async function submit() {
  await click('主动只读探测')
  expect(probeApi.submit).not.toHaveBeenCalled()
  await click('确认开始探测')
}
it('requires confirmation and shows queued without treating it as success', async () => {
  await start()
  await submit()
  expect(probeApi.submit).toHaveBeenCalledTimes(1)
  expect(w.text()).toContain('等待设备')
  expect(w.text()).toContain('不代表登录有效')
  expect(w.emitted('completed')).toBeUndefined()
})
it('polls GET only and emits completion then stops', async () => {
  await start()
  await submit()
  vi.mocked(probeApi.get).mockResolvedValue({
    ...queued,
    state: 'COMPLETED',
    completed_at: '2026-11-09T00:01:00Z',
  })
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  expect(w.text()).toContain('检查已完成')
  expect(w.emitted('completed')).toHaveLength(1)
  const n = vi.mocked(probeApi.get).mock.calls.length
  await vi.advanceTimersByTimeAsync(30000)
  expect(probeApi.get).toHaveBeenCalledTimes(n)
  expect(probeApi.submit).toHaveBeenCalledTimes(1)
})
it('unknown POST keeps exact intent through close and remount; retries only on explicit action', async () => {
  vi.mocked(probeApi.submit).mockRejectedValueOnce(new AgentApiError(0, 'NETWORK', '断网', true))
  await start()
  await submit()
  const first = vi.mocked(probeApi.submit).mock.calls[0][0]
  expect(w.text()).toContain('结果尚未确认')
  await w.setProps({ active: false })
  w.unmount()
  await start()
  expect(probeApi.submit).toHaveBeenCalledTimes(1)
  await click('重试原探测请求')
  expect(vi.mocked(probeApi.submit).mock.calls[1][0]).toEqual(first)
  expect(first.revision).toBe(4)
})
it('different current identity cannot replay the prior unknown intent', async () => {
  vi.mocked(probeApi.submit).mockRejectedValueOnce(new AgentApiError(0, 'NETWORK', '断网', true))
  await start()
  await submit()
  vi.mocked(environmentApi.capabilities).mockResolvedValue({ ...cap, actor_id: 2 })
  await click('重试原探测请求')
  expect(probeApi.submit).toHaveBeenCalledTimes(1)
  expect(w.text()).toContain('身份已变化')
})
it('close cancels in-flight GET and polling while preserving request id', async () => {
  await start()
  await submit()
  const signal = vi.mocked(probeApi.get).mock.calls[0][2]!
  await w.setProps({ active: false })
  expect(signal.aborted).toBe(true)
  await vi.advanceTimersByTimeAsync(30000)
  expect(probeApi.get).toHaveBeenCalledTimes(1)
  expect(session.requestId).toBe(req)
})
it('nonadmin capability cannot submit even when a stale action flag is true', async () => {
  vi.mocked(environmentApi.capabilities).mockResolvedValue({
    ...cap,
    data_role: 'USER',
    csrf_token: null,
  })
  await start()
  await submit()
  expect(probeApi.submit).not.toHaveBeenCalled()
  expect(w.text()).toContain('超级管理员')
})
it('hidden action does not fetch capability or send a probe', async () => {
  await start({ canProbe: false })
  expect(w.text()).not.toContain('确认开始探测')
  expect(w.findAllComponents(ElButton).some((b) => b.text() === '主动只读探测')).toBe(false)
  expect(environmentApi.capabilities).not.toHaveBeenCalled()
})
it('failed or expired results have distinct wording and do not imply valid identity', async () => {
  vi.mocked(probeApi.get).mockResolvedValue({
    ...queued,
    state: 'EXPIRED',
    error_code: 'PROBE_EXPIRED',
  })
  await start()
  await submit()
  expect(w.text()).toContain('探测已超时')
  expect(w.text()).not.toContain('检查已完成')
  expect(w.emitted('completed')).toHaveLength(1)
})
it('read failures stop automatic polling and allow explicit read retry without repeating POST', async () => {
  vi.mocked(probeApi.get).mockRejectedValueOnce(new AgentApiError(503, 'BUSY', '读取失败'))
  await start()
  await submit()
  await vi.advanceTimersByTimeAsync(30000)
  expect(probeApi.get).toHaveBeenCalledTimes(1)
  await click('重新读取探测结果')
  expect(probeApi.get).toHaveBeenCalledTimes(2)
  expect(probeApi.submit).toHaveBeenCalledTimes(1)
})
it('a new request after terminal completion cannot hide its unknown result behind the previous receipt', async () => {
  vi.mocked(probeApi.get).mockResolvedValue({
    ...queued,
    state: 'COMPLETED',
    completed_at: '2026-11-09T00:01:00Z',
  })
  await start()
  await submit()
  vi.mocked(probeApi.submit).mockRejectedValueOnce(new AgentApiError(0, 'NETWORK', '断网', true))
  await click('主动只读探测')
  await click('确认开始探测')
  expect(session.requestId).toBeNull()
  expect(w.text()).toContain('结果尚未确认')
  expect(w.findAllComponents(ElButton).some((b) => b.text() === '重试原探测请求')).toBe(true)
})
