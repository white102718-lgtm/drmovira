import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { aliasIntent, vendorAliasApi } from '@/api/orbit/vendor-aliases'

vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => 'same-origin',
  orbitAuthHeaders: (headers: Record<string, string>) => headers,
}))
const fetcher = vi.fn()
beforeEach(() => {
  vi.stubGlobal('fetch', fetcher)
  fetcher.mockImplementation(
    async () => new Response(JSON.stringify({ alias: null }), { status: 200 }),
  )
})
afterEach(() => {
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})

it('代称先NFC再按码点验证，不按UTF16截断名称', () => {
  expect(aliasIntent('e\u0301'.repeat(30), false, '真实来源')).toEqual({
    alias: 'é'.repeat(30),
    reason: '真实来源',
  })
  expect(aliasIntent('😀'.repeat(30), false, '维护').alias).toBe('😀'.repeat(30))
  expect(() => aliasIntent('😀'.repeat(31), false, '维护')).toThrow('1至30')
})
it('明确清除发送null，空输入不能冒充未知', () => {
  expect(aliasIntent('', true, '明确清除')).toEqual({ alias: null, reason: '明确清除' })
  expect(() => aliasIntent(' ', false, '空值')).toThrow()
})
it('控制符和无原因都拒绝，不静默吞掉换行', () => {
  expect(() => aliasIntent('代称\n', false, '维护')).toThrow()
  expect(() => aliasIntent('代称', false, ' ')).toThrow()
  expect(() => aliasIntent('代称', false, '维护\n')).toThrow()
})
it('维护请求只含alias和reason，携带独立版本及幂等键', async () => {
  await vendorAliasApi.save(
    'vendor/id',
    { alias: '真实代称', reason: '追溯' },
    2,
    'csrf',
    'stable-key',
  )
  const [url, init] = fetcher.mock.calls[0]
  expect(url).toContain('/vendor-aliases/vendor%2Fid')
  expect(init).toMatchObject({ method: 'PUT', cache: 'no-store', credentials: 'same-origin' })
  expect(init.headers).toMatchObject({
    'If-Match': '"2"',
    'X-CSRF-Token': 'csrf',
    'Idempotency-Key': 'stable-key',
  })
  expect(JSON.parse(init.body)).toEqual({ alias: '真实代称', reason: '追溯' })
})
it('批量当前读取只发UUID，不发名称或拥有者暗示数据', async () => {
  await vendorAliasApi.batch(['one', 'two'])
  expect(fetcher.mock.calls[0][0]).toContain('/vendor-aliases?ids=one%2Ctwo')
  expect(fetcher.mock.calls[0][1].body).toBeUndefined()
})
it('未知网络结果可用完全相同的冻结正文和幂等键重试', async () => {
  fetcher.mockRejectedValueOnce(new TypeError('offline'))
  const intent = aliasIntent('真实值', false, '重试')
  await expect(vendorAliasApi.save('id', intent, 1, 'csrf', 'same-key')).rejects.toMatchObject({
    status: 0,
  })
  await vendorAliasApi.save('id', intent, 1, 'csrf', 'same-key')
  expect(fetcher.mock.calls[0]).toEqual(fetcher.mock.calls[1])
})
it('服务端拒绝版本冲突保留真实状态，不模拟维护成功', async () => {
  fetcher.mockResolvedValueOnce(
    new Response(JSON.stringify({ code: 'REVISION_CONFLICT', message: '代称已修改' }), {
      status: 409,
    }),
  )
  await expect(
    vendorAliasApi.save('id', { alias: null, reason: '清除' }, 1, 'csrf', 'key'),
  ).rejects.toMatchObject({ status: 409, code: 'REVISION_CONFLICT' })
})
