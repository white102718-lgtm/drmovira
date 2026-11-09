import { afterEach, expect, it, vi } from 'vitest'
import { environmentApi, AgentApiError, type AgentIntent } from '@/api/orbit/environments'
const id = '00000000-0000-0000-0000-000000000001'
const body = { name: '执行机', endpoint: 'http://127.0.0.1:50325', probe_interval: 30 }
const agent = { ...body, id, revision: 1, state: 'OFFLINE', last_heartbeat: null }
const caps = {
  actor_id: 1,
  tenant_id: id,
  data_role: 'SUPER_ADMIN',
  csrf_token: 'abcdefghijklmnop',
}
const intent: AgentIntent = {
  operation: 'ENROLL',
  actor_id: 1,
  tenant_id: id,
  key: 'original-intent-key',
  body,
}
afterEach(() => vi.restoreAllMocks())
it('uses independent operation capabilities and validates exact identity context', async () => {
  const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(caps)))
  expect(await environmentApi.capabilities('ENROLL')).toEqual(caps)
  expect(String(spy.mock.calls[0][0])).toContain('/execution-agents/capabilities?operation=ENROLL')
  spy.mockResolvedValue(new Response(JSON.stringify({ ...caps, data_role: 'USER' })))
  await expect(environmentApi.capabilities('ENROLL')).rejects.toBeInstanceOf(AgentApiError)
})
it('writes only once with original key/body and quoted revision, never requests endpoint', async () => {
  const spy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(new Response(JSON.stringify({ ...agent, revision: 3 })))
  await environmentApi.write({ ...intent, id, revision: 2 }, caps.csrf_token)
  expect(spy).toHaveBeenCalledTimes(1)
  const [url, init] = spy.mock.calls[0]
  expect(String(url)).toContain(`/execution-agents/${id}`)
  expect(init?.method).toBe('PUT')
  expect(init?.body).toBe(JSON.stringify(body))
  expect(new Headers(init?.headers).get('If-Match')).toBe('"2"')
  expect(new Headers(init?.headers).get('Idempotency-Key')).toBe(intent.key)
})
it('unconfirmed write responses preserve unknown status and never retry automatically', async () => {
  const spy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(new Response(JSON.stringify({ ...agent, revision: 2 }), { status: 201 }))
  await expect(environmentApi.write(intent, caps.csrf_token)).rejects.toMatchObject({
    unknown_result: true,
  })
  expect(spy).toHaveBeenCalledTimes(1)
})
it('transport loss and invalid JSON are unknown writes', async () => {
  const spy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('network'))
  await expect(environmentApi.write(intent, caps.csrf_token)).rejects.toMatchObject({
    unknown_result: true,
  })
  spy.mockResolvedValue(new Response('broken', { status: 201 }))
  await expect(environmentApi.write(intent, caps.csrf_token)).rejects.toMatchObject({
    unknown_result: true,
  })
})
it('keeps explicit forbidden responses distinct from unknown writes', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        code: 'FORBIDDEN',
        message: '无权限',
        field_errors: [],
        retryable: false,
        request_id: id,
      }),
      { status: 403 },
    ),
  )
  await expect(environmentApi.write(intent, caps.csrf_token)).rejects.toMatchObject({
    status: 403,
    unknown_result: false,
  })
})
it('enforces bounded pages and original date/status query', async () => {
  const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        items: [agent],
        next_cursor: null,
        scope_version: 1,
        data_as_of: '2026-11-09T00:00:00.000Z',
      }),
    ),
  )
  const result = await environmentApi.list({
    page_size: 20,
    date_from: '2026-11-01',
    date_to: '2026-11-09',
    status: 'OFFLINE',
  })
  expect(result.items).toEqual([agent])
  expect(String(spy.mock.calls[0][0])).toContain('date_from=2026-11-01')
  spy.mockResolvedValue(
    new Response(
      JSON.stringify({
        items: Array(21).fill(agent),
        next_cursor: null,
        scope_version: 1,
        data_as_of: '2026-11-09T00:00:00.000Z',
      }),
    ),
  )
  await expect(environmentApi.list({ page_size: 20 })).rejects.toBeInstanceOf(AgentApiError)
})
