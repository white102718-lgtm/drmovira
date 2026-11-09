import { afterEach, expect, it, vi } from 'vitest'
import { probeApi, parseProbeResult, type ProbeIntent } from '@/api/orbit/environments-probe'
const id = '00000000-0000-0000-0000-000000000001'
const requestId = '00000000-0000-0000-0000-000000000002'
const intent: ProbeIntent = {
  agent_id: id,
  revision: 4,
  actor_id: 1,
  tenant_id: id,
  key: 'probe-original-key',
}
const result = {
  id: requestId,
  agent_id: id,
  state: 'QUEUED',
  created_at: '2026-11-09T00:00:00Z',
  expires_at: '2026-11-09T00:02:00Z',
  completed_at: null,
  error_code: null,
}
afterEach(() => vi.restoreAllMocks())
it('submits original empty-body endpoint once with exact CAS and key and expects 202', async () => {
  const fetch = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(
      new Response(
        JSON.stringify({ id: requestId, revision: 1, state: 'QUEUED', request_id: id }),
        { status: 202 },
      ),
    )
  const ack = await probeApi.submit(intent, 'abcdefghijklmnop')
  expect(ack.id).toBe(requestId)
  expect(fetch).toHaveBeenCalledTimes(1)
  const [url, init] = fetch.mock.calls[0]
  expect(String(url)).toContain(`/execution-agents/${id}/probe`)
  expect(init?.method).toBe('POST')
  expect(init?.body).toBeUndefined()
  expect(new Headers(init?.headers).get('If-Match')).toBe('"4"')
  expect(new Headers(init?.headers).get('Idempotency-Key')).toBe(intent.key)
})
it('unknown write result remains unknown and is not automatically retried', async () => {
  const fetch = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('lost response'))
  await expect(probeApi.submit(intent, 'abcdefghijklmnop')).rejects.toMatchObject({
    unknown_result: true,
  })
  expect(fetch).toHaveBeenCalledTimes(1)
})
it('strict result identity, states, timestamp ordering and unknown fields are rejected', () => {
  expect(parseProbeResult(result, id, requestId)).toEqual(result)
  for (const change of [
    { id },
    { agent_id: requestId },
    { state: 'SUCCEEDED' },
    { created_at: 'bad' },
    { expires_at: '2026-11-08T00:00:00Z' },
    { extra: true },
    { completed_at: '2026-11-09T00:01:00Z' },
    { error_code: 'unsafe\ntext' },
  ]) {
    expect(() => parseProbeResult({ ...result, ...change }, id, requestId)).toThrow()
  }
})
it('completion is accepted only as terminal result and never uses the local device endpoint', async () => {
  const done = { ...result, state: 'COMPLETED', completed_at: '2026-11-09T00:01:00Z' }
  const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(done)))
  expect(await probeApi.get(id, requestId)).toEqual(done)
  expect(String(fetch.mock.calls[0][0])).toContain(
    `/execution-agents/${id}/probe-requests/${requestId}`,
  )
})
