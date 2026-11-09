import { afterEach, expect, it, vi } from 'vitest'
import { accountIdentitiesApi, parseAccountIdentities } from '@/api/orbit/account-identities'
import { ReferenceApiError } from '@/api/orbit/references'
const id = '00000000-0000-0000-0000-000000000001'
const fixture = () => ({
  account_id: id,
  capability_version: 'observation-1',
  observed_at: '2026-11-08T00:00:00Z',
  resources: [
    {
      external_id: '9'.repeat(64),
      name: '真实观察主页',
      kind: 'PAGE',
      usable: true,
      reason_code: null,
    },
  ],
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
it('严格原四字段与64位外部ID字符串，不将usable解释成写授权', () => {
  const result = parseAccountIdentities(fixture())
  expect(result.resources[0].external_id).toBe('9'.repeat(64))
  expect(result).not.toHaveProperty('execution_eligible')
})
it.each([
  (row: any) => {
    row.extra = 'unknown'
  },
  (row: any) => {
    delete row.capability_version
  },
  (row: any) => {
    row.account_id = '{' + id + '}'
  },
  (row: any) => {
    row.observed_at = '2026-11-08'
  },
  (row: any) => {
    row.resources[0].external_id = 9007199254740993
  },
  (row: any) => {
    row.resources[0].external_id = '9'.repeat(65)
  },
  (row: any) => {
    row.resources[0].usable = 'true'
  },
  (row: any) => {
    row.resources[0].kind = 'EVENT'
  },
  (row: any) => {
    row.resources[0].token = 'not-a-contract-field'
  },
  (row: any) => {
    row.resources[0].reason_code = ''
  },
  (row: any) => {
    row.resources.push({ ...row.resources[0] })
  },
])('拒绝未知/错类型/越界/重复资源 % #', (change) => {
  const row = fixture()
  change(row)
  expect(() => parseAccountIdentities(row)).toThrow(ReferenceApiError)
})
it('5000资源完整保留而5001拒绝，不截断', () => {
  const row = fixture()
  row.resources = Array.from({ length: 5000 }, (_, i) => ({
    ...row.resources[0],
    external_id: String(i + 1),
  }))
  expect(parseAccountIdentities(row).resources).toHaveLength(5000)
  row.resources.push({ ...row.resources[0], external_id: '5001' })
  expect(() => parseAccountIdentities(row)).toThrow()
})
it('真实GET形状复用认证头与Abort，Token不放URL；错账户响应拒绝', async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(fixture()), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fetcher)
  const controller = new AbortController()
  expect((await accountIdentitiesApi.get(id, controller.signal)).account_id).toBe(id)
  expect(fetcher.mock.calls[0][0]).toMatch(
    /\/api\/v1\/accounts\/00000000-0000-0000-0000-000000000001\/identities$/,
  )
  expect(fetcher.mock.calls[0][0]).not.toMatch(/token|csrf|authorization/i)
  expect(fetcher.mock.calls[0][1].signal).toBe(controller.signal)
  fetcher.mockResolvedValue(
    new Response(
      JSON.stringify({ ...fixture(), account_id: '00000000-0000-0000-0000-000000000002' }),
      { status: 200 },
    ),
  )
  await expect(accountIdentitiesApi.get(id)).rejects.toMatchObject({
    code: 'INVALID_IDENTITY_RESPONSE',
  })
})
it('403/503原始错误保留，非法UUID不会发送GET', async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ code: 'IDENTITIES_UNAVAILABLE', message: '权威观察未同步' }), {
      status: 503,
    }),
  )
  vi.stubGlobal('fetch', fetcher)
  await expect(accountIdentitiesApi.get('invalid')).rejects.toMatchObject({ status: 422 })
  expect(fetcher).not.toHaveBeenCalled()
  await expect(accountIdentitiesApi.get(id)).rejects.toMatchObject({
    status: 503,
    code: 'IDENTITIES_UNAVAILABLE',
    message: '权威观察未同步',
  })
})
