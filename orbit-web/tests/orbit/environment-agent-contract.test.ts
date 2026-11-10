import { expect, it } from 'vitest'
import { parseAgentWrite, parseAgent } from '@/api/orbit/environments'
const body = { name: ' 执行机 e\u0301 ', endpoint: 'http://localhost:50325/', probe_interval: 30 }
it('normalizes three original fields without introducing ownership, keys or online state', () => {
  expect(parseAgentWrite(body)).toEqual({
    name: '执行机 é',
    endpoint: 'http://127.0.0.1:50325',
    probe_interval: 30,
  })
})
it.each(['http://localhost:50325?key=secret', 'http://user:secret@localhost:50325'])(
  'rejects endpoint %s without requesting it',
  (endpoint) => {
    expect(() => parseAgentWrite({ ...body, endpoint })).toThrow()
  },
)
it.each([9, 301, 10.1, '30', null, true])('rejects invalid interval %s', (probe_interval) => {
  expect(() => parseAgentWrite({ ...body, probe_interval })).toThrow()
})
it('enforces Unicode limits and rejects controls before trim', () => {
  expect(parseAgentWrite({ ...body, name: '机'.repeat(80) }).name).toHaveLength(80)
  for (const name of ['', '  ', '机'.repeat(81), 'name\n', 'name\u200b'])
    expect(() => parseAgentWrite({ ...body, name })).toThrow()
})
it('refuses additional credential or state fields', () => {
  for (const field of ['api_key', 'state', 'certificate', 'owner_user_id'])
    expect(() => parseAgentWrite({ ...body, [field]: 'secret' })).toThrow()
})
const agent = {
  name: '执行机',
  endpoint: 'http://127.0.0.1:50325',
  probe_interval: 30,
  id: '00000000-0000-0000-0000-000000000001',
  revision: 1,
  state: 'OFFLINE',
  last_heartbeat: null,
}
it('accepts only original seven public agent fields and leaves absent heartbeat null', () => {
  expect(parseAgent(agent)).toEqual(agent)
  for (const change of [
    { revision: 0 },
    { state: 'ONLINE' },
    { id: '1' },
    { last_heartbeat: 'today' },
    { api_key: 'secret' },
  ])
    expect(() => parseAgent({ ...agent, ...change })).toThrow()
})
it('rejects impossible calendar heartbeat dates rather than rolling over into another day', () => {
  expect(() => parseAgent({ ...agent, last_heartbeat: '2026-02-30T00:00:00Z' })).toThrow()
})

it.each([
  ['http://local.adspower.net:50325', 'http://local.adspower.net:50325'],
  ['http://192.168.1.9:61000', 'http://192.168.1.9:61000'],
  ['https://api.example.com/ads/', 'https://api.example.com/ads'],
  ['http://[::1]:61001', 'http://[::1]:61001'],
  ['http://localhost:80', 'http://127.0.0.1'],
])('preserves custom API base %s', (endpoint, expected) => {
  expect(parseAgentWrite({ ...body, endpoint }).endpoint).toBe(expected)
})
