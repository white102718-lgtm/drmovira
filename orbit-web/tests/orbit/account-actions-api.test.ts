/** SDK严格合同控制，HTTP使用替身；真实后台结果由主线专项提供。 */
import { beforeEach, expect, it, vi } from 'vitest'
import { accountActionsApi, type AccountReasonIntent } from '@/api/orbit/account-actions'
import { ReferenceApiError } from '@/api/orbit/references'

const request = vi.hoisted(() => vi.fn())
vi.mock('@/api/orbit/references', async (original) => ({
  ...(await original<typeof import('@/api/orbit/references')>()),
  referenceRequest: request,
}))
const intent: AccountReasonIntent = {
  accountId: 'account-id',
  action: 'SYNC',
  key: 'immutable-key',
  reason: '核对资料',
  capability: { csrf_token: 'memory-only-csrf', revision: 5, next_effective_from: null },
}
const ack = {
  id: intent.accountId,
  revision: 6,
  state: 'WAITING_EXECUTOR',
  request_id: 'request-id',
}
beforeEach(() => request.mockReset())

it('原路径、Reason仅字段、CSRF/CAS/幂等都保留，重试不改请求', async () => {
  request.mockResolvedValue(ack)
  await accountActionsApi.reason(intent)
  await accountActionsApi.reason(intent)
  expect(request.mock.calls[0]).toEqual(request.mock.calls[1])
  expect(request.mock.calls[0]).toEqual([
    '/accounts/account-id/sync',
    {
      method: 'POST',
      headers: {
        'X-CSRF-Token': 'memory-only-csrf',
        'Idempotency-Key': 'immutable-key',
        'If-Match': '"5"',
      },
      body: JSON.stringify({ reason: '核对资料' }),
    },
  ])
})

it('能力按指定动作取，解绑仍为原POST/Reason', async () => {
  request.mockResolvedValue({ ...ack, state: 'SUCCEEDED' })
  await accountActionsApi.capabilities('account/id', 'UNBIND')
  expect(request.mock.calls[0][0]).toBe('/accounts/account%2Fid/actions/capabilities?action=UNBIND')
  await accountActionsApi.reason({ ...intent, action: 'UNBIND' })
  expect(request.mock.calls[1][0]).toBe('/accounts/account-id/unbind')
})

it('错误账户/版本/状态/额外字段回执保持不确定，不能伪装已成功', async () => {
  for (const value of [
    { ...ack, id: 'other' },
    { ...ack, revision: 99 },
    { ...ack, state: 'SUCCEEDED' },
    { ...ack, extra: true },
    { ...ack, request_id: '' },
  ]) {
    request.mockResolvedValueOnce(value)
    await expect(accountActionsApi.reason(intent)).rejects.toBeInstanceOf(ReferenceApiError)
  }
})
