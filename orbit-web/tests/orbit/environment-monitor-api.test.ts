import { afterEach, expect, it, vi } from 'vitest'
import { monitorApi, parseAgentMonitor, parseProfilePage } from '@/api/orbit/environments-monitor'
const id = '00000000-0000-0000-0000-000000000001'
const monitor = {
  agent_id: id,
  machine_state: 'SUSPECT',
  last_heartbeat: '2026-11-09T00:00:00.000000Z',
  api_status: 'READY',
  inventory_coverage: 'ACTIVE_ONLY',
  last_error: null,
  received_at: '2026-11-09T00:00:00.000000Z',
}
const profile = {
  id,
  agent_id: id,
  external_profile_id: 'p-001',
  process_state: 'ACTIVE',
  identity_state: 'UNKNOWN',
  account_ids: [id],
  observed_at: '2026-11-09T00:00:00.000000Z',
}
const page = {
  items: [profile],
  next_cursor: null,
  data_as_of: '2026-11-09T00:00:00.000000Z',
  scope_version: 1,
}
afterEach(() => vi.restoreAllMocks())
it('keeps server machine state and active-only inventory independently', () => {
  expect(parseAgentMonitor(monitor, id)).toEqual(monitor)
})
it.each([
  { api_status: 'ONLINE' },
  { inventory_coverage: 'ALL' },
  { agent_id: 'bad' },
  { last_error: 'secret=key' },
  { received_at: '2026-02-30T00:00:00Z' },
  { api_key: 'secret' },
])('rejects invalid or secret-bearing monitor response %j', (damage) => {
  expect(() => parseAgentMonitor({ ...monitor, ...damage }, id)).toThrow()
})
it('profile presence does not manufacture verified identity or additional accounts', () => {
  expect(parseProfilePage(page, id, 20)).toEqual(page)
})
it('rejects wrong-agent, duplicate, excessive accounts and over-sized pages', () => {
  for (const items of [
    [{ ...profile, agent_id: '00000000-0000-0000-0000-000000000002' }],
    [profile, profile],
    [{ ...profile, account_ids: Array(501).fill(id) }],
    Array(21).fill(profile),
  ])
    expect(() => parseProfilePage({ ...page, items }, id, 20)).toThrow()
})
it('uses only control-plane read endpoints with bounded query and abort signal', async () => {
  const spy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify(monitor)))
    .mockResolvedValueOnce(new Response(JSON.stringify(page)))
  const signal = new AbortController().signal
  await monitorApi.get(id, signal)
  await monitorApi.profiles(id, { page_size: 20, q: 'p', status: 'ACTIVE' }, signal)
  expect(String(spy.mock.calls[0][0])).toContain(`/execution-agents/${id}/monitor`)
  expect(String(spy.mock.calls[1][0])).toContain(
    `/execution-agents/${id}/profiles?page_size=20&q=p&status=ACTIVE`,
  )
  expect(spy.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true)
})
it('accepts the bounded original maximum page with 200 profiles and 500 account IDs each', async () => {
  const accounts = Array.from(
    { length: 500 },
    (_, i) => `00000000-0000-0000-0000-${String(i + 1).padStart(12, '0')}`,
  )
  const items = Array.from({ length: 200 }, (_, i) => ({
    ...profile,
    id: `00000000-0000-0000-0000-${String(i + 1001).padStart(12, '0')}`,
    external_profile_id: `profile-${i}`,
    account_ids: accounts,
  }))
  const body = JSON.stringify({ ...page, items })
  expect(body.length).toBeGreaterThan(2 * 1024 * 1024)
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(body))
  expect((await monitorApi.profiles(id, { page_size: 200 })).items).toHaveLength(200)
})
