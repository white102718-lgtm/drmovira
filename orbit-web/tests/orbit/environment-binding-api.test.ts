import { afterEach, expect, it, vi } from 'vitest'
import {
  bindingApi,
  parseBindingWrite,
  type BindingIntent,
} from '@/api/orbit/environments-bindings'
const id = '00000000-0000-0000-0000-000000000001'
const body = {
  account_id: id,
  agent_id: id,
  profile_external_id: 'Profile-001',
  ownership: { owner_user_id: id, owner_team_id: id },
}
const row = { ...body, id, revision: 1, identity_state: 'UNKNOWN', verified_at: null }
const intent: BindingIntent = {
  operation: 'SAVE',
  actor_id: 1,
  tenant_id: id,
  key: 'original-binding-key',
  body,
}
afterEach(() => vi.restoreAllMocks())
it('retains all original binding fields, rejecting credentials and invalid ownership', () => {
  expect(parseBindingWrite(body)).toEqual(body)
  for (const invalid of [
    { ...body, api_key: 'secret' },
    { ...body, ownership: { owner_user_id: id } },
    { ...body, profile_external_id: 'x'.repeat(129) },
    { ...body, account_id: 'bad' },
  ])
    expect(() => parseBindingWrite(invalid)).toThrow()
})
it('registration does not promote unknown identity to verified', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(row), { status: 201 }),
  )
  expect(await bindingApi.write(intent, 'abcdefghijklmnop')).toEqual(row)
})
it('unbind retains original reason/key/CAS and validates receipt identity and version', async () => {
  const spy = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(
      new Response(JSON.stringify({ id, revision: 3, unbound_at: '2026-11-09T00:00:00.000000Z' })),
    )
  await bindingApi.write(
    { ...intent, operation: 'UNBIND', id, revision: 2, body: { reason: '停止关联' } },
    'abcdefghijklmnop',
  )
  expect(String(spy.mock.calls[0][0])).toContain(`/profile-bindings/${id}/unbind`)
  expect(new Headers(spy.mock.calls[0][1]?.headers).get('If-Match')).toBe('"2"')
  spy.mockResolvedValue(
    new Response(JSON.stringify({ id, revision: 4, unbound_at: '2026-11-09T00:00:00.000000Z' })),
  )
  await expect(
    bindingApi.write(
      { ...intent, operation: 'UNBIND', id, revision: 2, body: { reason: '停止关联' } },
      'abcdefghijklmnop',
    ),
  ).rejects.toMatchObject({ unknown_result: true })
})
it('never rewrites external Profile ID whitespace or Unicode identity', () => {
  for (const profile_external_id of [' Profile-001', 'Profile-001 ', 'e\u0301'])
    expect(() => parseBindingWrite({ ...body, profile_external_id })).toThrow()
})
