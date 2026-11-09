/** 批量显示资料纯协议测试；fetch替身不是真实HTTP/目录来源。 */
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import {
  ruleDisplayMetadataApi as api,
  displayMetadataIds,
  parseRuleDisplayMetadata,
} from '@/api/orbit/rule-display-metadata'
const auth = vi.hoisted(() => ({ token: 'current' }))
vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => 'omit',
  orbitAuthHeaders: (extra: HeadersInit = {}) => ({
    ...Object.fromEntries(new Headers(extra)),
    Authorization: auth.token,
  }),
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const item = (n = 1) => ({
  rule_id: id(n),
  revision: 3,
  owner_user_name: '真实投放师',
  owner_team_name: '真实团队',
  created_by: 9,
  created_by_name: null,
  created_at: '2026-11-09T01:00:00.123Z',
})
const fetcher = vi.fn()
beforeEach(() => {
  fetcher.mockReset()
  auth.token = 'current'
  vi.stubGlobal('fetch', fetcher)
  vi.stubEnv('VITE_APP_BASE_API', '/dev-api')
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})
it('真实1..200逗号唯一规范UUID，按原顺序一次GET无额外目录或写头', async () => {
  fetcher.mockResolvedValue(new Response(JSON.stringify({ items: [item(2), item()] })))
  const input = [id(2), id()]
  expect(await api.get(input)).toEqual([item(2), item()])
  const url = new URL(fetcher.mock.calls[0][0], 'https://fixture.local')
  expect(url.pathname).toBe('/dev-api/api/v1/rules/display-metadata')
  expect(Object.fromEntries(url.searchParams)).toEqual({ rule_ids: input.join(',') })
  expect(fetcher.mock.calls[0][1]).toMatchObject({ method: 'GET', cache: 'no-store' })
  expect(fetcher.mock.calls[0][1].body).toBeUndefined()
  expect(new Headers(fetcher.mock.calls[0][1].headers).has('If-Match')).toBe(false)
  expect(input).toEqual([id(2), id()])
})
it('UUID正边界200与空/201/重复/非规范/非数组严格拒绝', () => {
  expect(displayMetadataIds(Array.from({ length: 200 }, (_, n) => id(n + 1)))).toHaveLength(200)
  for (const v of [
    [],
    Array.from({ length: 201 }, (_, n) => id(n + 1)),
    [id(), id()],
    ['  ' + id()],
    ['not-id'],
    [id().toUpperCase().replace('4000', 'A000')],
    id(),
  ])
    expect(() => displayMetadataIds(v)).toThrow()
})
it('精确单键/七字段/全集顺序，不漏行或用错revision类型', () => {
  for (const v of [
    { items: [] },
    { items: [item(), item()] },
    { items: [item(2)] },
    { items: [{ ...item(), extra: 1 }] },
    { items: [{ ...item(), revision: true }] },
    { items: [{ ...item(), created_by: 0 }] },
    { items: [item()], extra: 1 },
  ])
    expect(() => parseRuleDisplayMetadata(v, [id()])).toThrow()
})
it('真实null姓名与原nativeID/UTC保真，不发明用户fallback', () => {
  const row = { ...item(), owner_user_name: null, owner_team_name: null, created_by_name: null }
  expect(parseRuleDisplayMetadata({ items: [row] }, [id()])).toEqual([row])
})
it('用户50/团队100码点边界及NFCtrim/控制符不偷偷改写', () => {
  expect(
    parseRuleDisplayMetadata(
      {
        items: [{ ...item(), owner_user_name: '界'.repeat(50), owner_team_name: '界'.repeat(100) }],
      },
      [id()],
    ),
  ).toHaveLength(1)
  for (const update of [
    { owner_user_name: '界'.repeat(51) },
    { owner_team_name: '界'.repeat(101) },
    { created_by_name: '' },
    { owner_user_name: ' e\u0301' },
    { owner_team_name: 'x\0' },
    { created_by_name: 'é ' },
  ])
    expect(() => parseRuleDisplayMetadata({ items: [{ ...item(), ...update }] }, [id()])).toThrow()
})
it('时间固定UTC毫秒，真实无效日和微秒/偏移不凑成功', () => {
  for (const created_at of [
    '2026-02-30T00:00:00.000Z',
    '2026-11-09T00:00:00Z',
    '2026-11-09T00:00:00.123456Z',
    '2026-11-09T00:00:00.123+00:00',
  ])
    expect(() => parseRuleDisplayMetadata({ items: [{ ...item(), created_at }] }, [id()])).toThrow()
})
it.each([401, 403, 404, 409, 503])('%d原错误保留，HTML授权正文不降为普通故障', async (status) => {
  fetcher.mockResolvedValue(
    new Response(
      JSON.stringify({
        code: 'CURRENT_UNAVAILABLE',
        message: '当前不可读',
        field_errors: [],
        retryable: false,
        request_id: id(8),
      }),
      { status },
    ),
  )
  await expect(api.get([id()])).rejects.toMatchObject({
    status,
    code: 'CURRENT_UNAVAILABLE',
    unknown_result: false,
  })
  if ([401, 403, 404, 409].includes(status)) {
    fetcher.mockResolvedValue(new Response('<html>private</html>', { status }))
    await expect(api.get([id()])).rejects.toMatchObject({ status, code: 'INVALID_RESPONSE' })
  }
})
it('200坏body/认证晚回/abort不接受为当前显示资料，不自动重试', async () => {
  fetcher.mockResolvedValue(new Response('{}'))
  await expect(api.get([id()])).rejects.toMatchObject({ status: 502 })
  fetcher.mockImplementation(async () => {
    auth.token = 'other'
    return new Response(JSON.stringify({ items: [item()] }))
  })
  await expect(api.get([id()])).rejects.toMatchObject({ code: 'SESSION_CONTEXT_CHANGED' })
  const c = new AbortController()
  c.abort()
  await expect(api.get([id()], c.signal)).rejects.toMatchObject({ name: 'AbortError' })
  expect(fetcher).toHaveBeenCalledTimes(2)
})
