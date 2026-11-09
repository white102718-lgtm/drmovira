import { afterEach, describe, expect, it, vi } from 'vitest'
import { userApi, UserRequestError } from '@/api/orbit/users'

vi.mock('@/utils/auth', () => ({ getToken: () => 'fixture-token' }))
afterEach(() => vi.unstubAllGlobals())
describe('邀请管理接口', () => {
  it('POST不带正文、邮箱和身份，版本带引号并沿用原幂等键', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await userApi.invite('person/id', 9, 'fixture-csrf', 'fixture-original-intent')
    const [url, options] = fetch.mock.calls[0]
    expect(url).toContain('/users/person%2Fid/invitation')
    expect(options.method).toBe('POST')
    expect(options.body).toBeUndefined()
    expect(options.headers['If-Match']).toBe('"9"')
    expect(options.headers['Idempotency-Key']).toBe('fixture-original-intent')
    expect(options.headers['X-CSRF-Token']).toBe('fixture-csrf')
    expect(options.cache).toBe('no-store')
  })
  it('明确拒绝保留HTTP状态，网关非JSON错误不回显响应', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{"message":"版本已变化"}', { status: 409 })),
    )
    await expect(userApi.invite('id', 1, 'csrf', 'intent')).rejects.toMatchObject({ status: 409 })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('upstream-private-fragment', { status: 502 })),
    )
    await expect(userApi.invitationStatus('id')).rejects.toThrow('服务响应无效')
    expect(new UserRequestError('拒绝', 403)).toBeInstanceOf(Error)
  })
})
