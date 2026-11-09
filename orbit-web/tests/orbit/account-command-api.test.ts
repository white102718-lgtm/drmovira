/** 诊断SDK合同替身，不代替真实HTTP/权限验收。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { accountCommandApi } from '@/api/orbit/account-command'
const request = vi.hoisted(() => vi.fn())
vi.mock('@/api/orbit/references', async (original) => ({
  ...(await original<typeof import('@/api/orbit/references')>()),
  referenceRequest: request,
}))
const value = {
  command_id: '10000000-0000-4000-8000-000000000001',
  account_id: 'account/id',
  kind: 'SYNC',
  accepted_request_id: 'request-id',
  revision: 2,
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
  request.mockReset()
})
it('仅GET并绑定原账户、动作、受理request_id，不增加写头或TaskID', async () => {
  request.mockResolvedValue(value)
  const controller = new AbortController()
  expect(
    await accountCommandApi.status('account/id', 'SYNC', 'request-id', controller.signal),
  ).toEqual(value)
  expect(request.mock.calls[0]).toEqual([
    '/accounts/account%2Fid/actions/status?kind=SYNC&request_id=request-id',
    { signal: controller.signal },
  ])
})
it.each([
  { account_id: 'other' },
  { kind: 'UNBIND' },
  { accepted_request_id: 'other' },
  { task_id: 'fake-task' },
  { state: 'QUEUED' },
  { attempt_count: 5 },
  { revision: 0 },
  { completed_at: '2026-11-08' },
  { updated_at: '2026-02-30T00:00:00.000Z' },
  { last_error_code: 'platform token raw response' },
])('错关联、原Task状态或错字段拒绝，不显示虚假状态 %j', async (changes) => {
  request.mockResolvedValue({ ...value, ...changes })
  await expect(accountCommandApi.status('account/id', 'SYNC', 'request-id')).rejects.toMatchObject({
    status: 502,
    code: 'INVALID_RESPONSE',
  })
})
