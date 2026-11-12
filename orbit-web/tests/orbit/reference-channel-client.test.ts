import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { channelApi, type Channel, type ChannelWrite } from '@/api/orbit/channels'
import { referenceApi, ReferenceApiError, type ReferenceResult } from '@/api/orbit/references'

vi.mock('@/api/orbit/authentication', () => ({
  orbitCredentials: () => 'same-origin',
  orbitAuthHeaders: (headers: Record<string, string>) => ({
    ...headers,
    'X-CSRF-Token': headers['X-CSRF-Token'] || 'cookie-csrf-memory',
  }),
}))
const fetcher = vi.fn()
const value: ChannelWrite = {
  code: 'CHANNEL_1',
  name: '渠道',
  ownership: { owner_team_id: 'team', data_owner_user_ids: ['user'] },
  type: 'WEBSITE',
  media: 'META',
  url: 'https://example.com/?a=1',
  status: 'ENABLED',
}
const existing = {
  ...value,
  id: 'channel/id',
  revision: 3,
  created_at: '',
  updated_at: '',
} as Channel
beforeEach(() => {
  vi.stubGlobal('fetch', fetcher)
  fetcher.mockImplementation(async () => new Response(JSON.stringify(existing), { status: 200 }))
})
afterEach(() => {
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})
describe('引用资料与渠道真实客户端边界', () => {
  it('创建正文只有业务字段，会话在内存且不缓存', async () => {
    await channelApi.save(value, 'csrf-token', 'same-key-12345678')
    const [url, options] = fetcher.mock.calls[0]
    expect(url).toMatch(/\/api\/v1\/channels$/)
    expect(options).toMatchObject({ method: 'POST', credentials: 'same-origin', cache: 'no-store' })
    expect(JSON.parse(options.body)).toEqual(value)
    expect(options.headers['Idempotency-Key']).toBe('same-key-12345678')
    expect(options.headers['If-Match']).toBeUndefined()
  })
  it('编辑携带原版本且目标UUID编码', async () => {
    await channelApi.save(value, 'csrf', 'key-1234567890123', existing)
    expect(fetcher.mock.calls[0][0]).toContain('channel%2Fid')
    expect(fetcher.mock.calls[0][1].headers['If-Match']).toBe('"3"')
    expect(fetcher.mock.calls[0][1].method).toBe('PUT')
  })
  it('专门分配和停用请求保留原因且不夹带编辑字段', async () => {
    await channelApi.assign(existing, value.ownership, '转交原因', 'csrf', 'key-1234567890123')
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      ownership: value.ownership,
      reason: '转交原因',
    })
    await channelApi.archive(existing, '停用原因', 'csrf', 'key-1234567890123')
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ reason: '停用原因' })
    expect(fetcher.mock.calls[1][0]).toContain('/archive')
  })
  it('提交预览不发送新业务正文，使用冻结预览CAS', async () => {
    await referenceApi.commit(
      { id: 'preview/id', revision: 2 } as ReferenceResult,
      'csrf',
      'key-1234567890123',
    )
    expect(fetcher.mock.calls[0][0]).toContain('preview%2Fid/commit')
    expect(fetcher.mock.calls[0][1].body).toBeUndefined()
    expect(fetcher.mock.calls[0][1].headers['If-Match']).toBe('"2"')
  })
  it('户商候选绑定目标拥有者，游标原样编码', async () => {
    await referenceApi.list(
      'VENDOR',
      new URLSearchParams({ owner_user_id: 'u', cursor: 'cursor+/' }),
    )
    expect(fetcher.mock.calls[0][0]).toContain('owner_user_id=u&cursor=cursor%2B%2F')
  })
  it('权限/版本/过期错误保留服务端语义', async () => {
    fetcher.mockResolvedValue(
      new Response(JSON.stringify({ code: 'CATALOG_CHANGED', message: '目录已变化' }), {
        status: 409,
      }),
    )
    await expect(referenceApi.get('preview')).rejects.toMatchObject({
      status: 409,
      code: 'CATALOG_CHANGED',
      message: '目录已变化',
    })
  })
  it('网络未知结果明确提示保留幂等键', async () => {
    fetcher.mockRejectedValue(new TypeError('failed fetch'))
    await expect(channelApi.save(value, 'csrf', 'key-1234567890123')).rejects.toMatchObject({
      status: 0,
      code: 'NETWORK_UNAVAILABLE',
    })
  })
  it('HTML或无效响应不能冒充保存成功', async () => {
    fetcher.mockResolvedValue(new Response('<html>proxy failure</html>', { status: 200 }))
    await expect(channelApi.get('c')).rejects.toBeInstanceOf(ReferenceApiError)
  })
})
