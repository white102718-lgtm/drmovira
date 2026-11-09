/** 分配SDK合同替身验证；不取代真实候选权限/归属事务验收。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { accountAssignmentApi, type AssignmentIntent } from '@/api/orbit/account-assignment'
const request = vi.hoisted(() => vi.fn())
vi.mock('@/api/orbit/references', async (original) => ({
  ...(await original<typeof import('@/api/orbit/references')>()),
  referenceRequest: request,
}))
const intent: AssignmentIntent = {
  accountId: 'account',
  key: 'original-key',
  capability: { csrf_token: 'in-memory', revision: 2, next_effective_from: '2026-11-10T05:00:00Z' },
  body: {
    operator_user_id: 'owner',
    owner_team_id: 'team',
    vendor_id: null,
    effective_from: '2026-11-10T05:00:00Z',
    reason: '负责人员转移',
  },
}
const ack = { id: 'account', revision: 3, state: 'SCHEDULED', request_id: 'request-id' }
beforeEach(() => request.mockReset())

it('原PUT/5字段/幂等CAS头，原意图重试不改变时刻或body', async () => {
  request.mockResolvedValue(ack)
  await accountAssignmentApi.assign(intent)
  await accountAssignmentApi.assign(intent)
  expect(request.mock.calls[0]).toEqual(request.mock.calls[1])
  expect(request.mock.calls[0]).toEqual([
    '/accounts/account/assignment',
    {
      method: 'PUT',
      headers: {
        'X-CSRF-Token': 'in-memory',
        'Idempotency-Key': 'original-key',
        'If-Match': '"2"',
      },
      body: JSON.stringify(intent.body),
    },
  ])
})
it('OWNER无导入依赖，VENDOR显式绑定目标投手且安全编码', async () => {
  request.mockResolvedValue({ items: [], next_cursor: null })
  await accountAssignmentApi.owners('account/id', new URLSearchParams({ q: '甲' }))
  await accountAssignmentApi.vendors(
    'account/id',
    'owner/id',
    new URLSearchParams({ page_size: '50' }),
  )
  expect(request.mock.calls[0][0]).toBe(
    '/accounts/account%2Fid/assignment-options?kind=OWNER&q=%E7%94%B2',
  )
  expect(request.mock.calls[1][0]).toBe(
    '/accounts/account%2Fid/assignment-options?kind=VENDOR&owner_user_id=owner%2Fid&page_size=50',
  )
})
it('错误回执不能假称当前归属已转移', async () => {
  for (const value of [
    { ...ack, state: 'SUCCEEDED' },
    { ...ack, revision: 99 },
    { ...ack, extra: true },
  ]) {
    request.mockResolvedValueOnce(value)
    await expect(accountAssignmentApi.assign(intent)).rejects.toMatchObject({
      status: 502,
      code: 'INVALID_RESPONSE',
    })
  }
})
