import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getConfigurationMetadata,
  saveConfiguration,
  testConfiguration,
  type Configuration,
  type ConfigurationWrite,
} from '@/api/orbit/configuration'

vi.mock('@/utils/auth', () => ({ getToken: () => 'fixture-session' }))

afterEach(() => vi.unstubAllGlobals())

describe('系统配置请求安全边界', () => {
  it('明确的保存意图键原样发送，网络重试不会强制生成另一键', async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    const value: ConfigurationWrite = {
      section: 'AI_GPT',
      name: '模型',
      enabled: false,
      settings: {},
      secrets: {},
      reason: '网络重试',
    }
    await saveConfiguration(value, undefined, 'fixture-same-intent')
    await saveConfiguration(value, undefined, 'fixture-same-intent')
    expect(fetch.mock.calls.map((call) => call[1].headers['Idempotency-Key'])).toEqual([
      'fixture-same-intent',
      'fixture-same-intent',
    ])
  })

  it('非JSON网关错误不回显原始响应片段', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('fixture-sensitive-html', { status: 502 })),
    )
    await expect(getConfigurationMetadata()).rejects.toThrow('服务响应无效')
  })
  it('网络异常只显示恢复提示，不回显传输异常中的内容', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fixture-sensitive-error')))
    await expect(getConfigurationMetadata()).rejects.toThrow('网络连接中断')
  })
  it('凭据请求不缓存、不携带Cookie，并使用幂等键', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 'fixture' }), { status: 201 }))
    vi.stubGlobal('fetch', fetch)
    const value: ConfigurationWrite = {
      section: 'AI_GPT',
      name: 'fixture',
      enabled: false,
      settings: {},
      reason: 'fixture',
      secrets: { apiKey: { operation: 'REPLACE', value: 'fixture-secret' } },
    }
    await saveConfiguration(value)
    const [url, options] = fetch.mock.calls[0]
    expect(url).not.toContain('fixture-secret')
    expect(options.credentials).toBe('omit')
    expect(options.cache).toBe('no-store')
    expect(options.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/)
    expect(options.headers.Authorization).toBe('Bearer fixture-session')
    expect(JSON.parse(options.body).secrets.apiKey.operation).toBe('REPLACE')
  })

  it('识别若依HTTP200中的会话失效，不将其当作元数据', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 401, msg: 'fixture' }))),
    )
    await expect(getConfigurationMetadata()).rejects.toThrow('登录已失效')
  })

  it('传播安全的版本冲突，保留重新加载入口', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ code: 'REVISION_CONFLICT', message: '配置已变化，请刷新后重试' }),
            { status: 409 },
          ),
        ),
    )
    await expect(getConfigurationMetadata()).rejects.toThrow('配置已变化')
  })
  it('只读测试提交人工原因和原版本，不携带公开配置或凭据', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await testConfiguration({ id: 'fixture-id', revision: 7 } as Configuration, '人工核对连接')
    const [url, options] = fetch.mock.calls[0]
    expect(url).toContain('/fixture-id/test')
    expect(options.headers['If-Match']).toBe('"7"')
    expect(JSON.parse(options.body)).toEqual({ reason: '人工核对连接' })
    expect(options.cache).toBe('no-store')
    expect(options.credentials).toBe('omit')
  })
})
