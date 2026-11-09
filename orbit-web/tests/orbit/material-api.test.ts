import { afterEach, describe, expect, it, vi } from 'vitest'
import { materialApi, type MaterialUploadState } from '../../src/api/orbit/materials'

vi.mock('../../src/api/orbit/authentication', () => ({
  orbitCredentials: () => 'same-origin',
  orbitAuthHeaders: (extra: Record<string, string>) => extra,
}))
vi.mock('../../src/api/orbit/material-hash', () => ({
  hashMaterialFile: async () => 'a'.repeat(64),
}))
const ID = '00000000-0000-4000-8000-000000000001'
const metadata = { name: '真实文件SDK合同', category_id: ID, tag_ids: [] }
const session = {
  id: ID,
  asset_id: ID,
  expires_at: '2030-01-01T00:00:00Z',
  part_size: 8 * 1024 * 1024,
  parts: [{ part_number: 1, url: 'https://untrusted.invalid/collect' }],
}
const asset = {
  ...metadata,
  id: ID,
  revision: 1,
  state: 'SCANNING',
  kind: 'IMAGE',
  sha256: 'a'.repeat(64),
  preview_url: null,
  duration_seconds: null,
  ownership: { owner_user_id: ID, owner_team_id: ID },
}
const response = (value: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => value,
})
afterEach(() => vi.unstubAllGlobals())

describe('素材SDK重试与同源边界', () => {
  it('安全集合一次请求与重扫原版本、原因及意图键独立于原Asset合同', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [] }))
      .mockResolvedValueOnce(response(asset, 202))
    vi.stubGlobal('fetch', fetcher)
    await materialApi.security([ID, '00000000-0000-4000-8000-000000000002'])
    expect(fetcher.mock.calls[0][0]).toContain('/assets/security?asset_ids=')
    expect(
      new URL(fetcher.mock.calls[0][0], 'https://fixture.example').searchParams.get('asset_ids'),
    ).toBe(`${ID},00000000-0000-4000-8000-000000000002`)
    await materialApi.rescan(asset, '复核原因', 'csrf', 'same-intent-key')
    const init = fetcher.mock.calls[1][1]
    expect(init.headers).toMatchObject({
      'If-Match': '"1"',
      'Idempotency-Key': 'same-intent-key',
      'X-CSRF-Token': 'csrf',
    })
    expect(JSON.parse(init.body)).toEqual({ reason: '复核原因' })
    expect(init.credentials).toBe('same-origin')
  })
  it('任意响应上传URL不会成为凭据发送目标', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response(session, 201))
      .mockResolvedValueOnce(response({ part_number: 1, etag: 'a'.repeat(64) }))
      .mockResolvedValueOnce(response(asset, 202))
    vi.stubGlobal('fetch', fetcher)
    const result = await materialApi.upload(
      new File(['test'], 'a.png', { type: 'image/png' }),
      metadata,
      'csrf',
      () => {},
      {},
    )
    expect(result.state).toBe('SCANNING')
    expect(fetcher.mock.calls).toHaveLength(3)
    for (const [url, init] of fetcher.mock.calls) {
      expect(url).not.toContain('untrusted.invalid')
      expect(init.credentials).toBe('same-origin')
      expect(init.cache).toBe('no-store')
    }
    expect(fetcher.mock.calls[1][0]).toContain(`/assets/upload-sessions/${ID}/parts/1`)
  })
  it('分片响应丢失重试保持创建会话与分片意图键', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response(session, 201))
      .mockRejectedValueOnce(new Error('lost acknowledgement'))
      .mockResolvedValueOnce(response({ part_number: 1, etag: 'a'.repeat(64) }))
      .mockResolvedValueOnce(response(asset, 202))
    vi.stubGlobal('fetch', fetcher)
    const state: MaterialUploadState = {}
    const file = new File(['test'], 'a.png', { type: 'image/png' })
    await expect(materialApi.upload(file, metadata, 'csrf', () => {}, state)).rejects.toThrow(
      '网络中断',
    )
    const key = (fetcher.mock.calls[1][1].headers as Record<string, string>)['Idempotency-Key']
    await materialApi.upload(file, metadata, 'csrf', () => {}, state)
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/upload-sessions'))).toHaveLength(1)
    expect((fetcher.mock.calls[2][1].headers as Record<string, string>)['Idempotency-Key']).toBe(
      key,
    )
  })
  it('完成响应丢失重试不重传已确认分片', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response(session, 201))
      .mockResolvedValueOnce(response({ part_number: 1, etag: 'a'.repeat(64) }))
      .mockRejectedValueOnce(new Error('lost completion'))
      .mockResolvedValueOnce(response(asset, 202))
    vi.stubGlobal('fetch', fetcher)
    const state: MaterialUploadState = {}
    const file = new File(['test'], 'a.png', { type: 'image/png' })
    await expect(materialApi.upload(file, metadata, 'csrf', () => {}, state)).rejects.toThrow()
    const key = (fetcher.mock.calls[2][1].headers as Record<string, string>)['Idempotency-Key']
    await materialApi.upload(file, metadata, 'csrf', () => {}, state)
    expect(fetcher.mock.calls.filter(([url]) => url.includes('/parts/'))).toHaveLength(1)
    expect((fetcher.mock.calls[3][1].headers as Record<string, string>)['Idempotency-Key']).toBe(
      key,
    )
  })
  it('READY去重复用仍重新读取现有素材且不发文件', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response({ ...session, part_size: 0 }, 201))
      .mockResolvedValueOnce(response({ ...asset, state: 'READY' }))
    vi.stubGlobal('fetch', fetcher)
    const result = await materialApi.upload(
      new File(['test'], 'a.png', { type: 'image/png' }),
      metadata,
      'csrf',
      () => {},
      {},
    )
    expect(result.state).toBe('READY')
    expect(fetcher.mock.calls).toHaveLength(2)
    expect(fetcher.mock.calls[1][1].method).toBeUndefined()
  })
  it('超限图片不创建任何上传会话', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    const file = { type: 'image/png', size: 20 * 1024 * 1024 + 1 } as File
    await expect(materialApi.upload(file, metadata, 'csrf', () => {}, {})).rejects.toThrow('20MiB')
    expect(fetcher).not.toHaveBeenCalled()
  })
})

it('标签分类查询按原字段编码筛选和签名游标，不修改内容或发送任意字段', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(response({ items: [], next_cursor: null, data_as_of: '', scope_version: 1 }))
  vi.stubGlobal('fetch', fetcher)
  await materialApi.taxonomy('tags', 'signed+/=', {
    q: '标签_% &字',
    status: 'DISABLED',
    page_size: 200,
  })
  const [url, init] = fetcher.mock.calls[0]
  const query = new URL(url, 'https://app.fixture.example').searchParams
  expect(query.get('q')).toBe('标签_% &字')
  expect(query.get('cursor')).toBe('signed+/=')
  expect(query.get('status')).toBe('DISABLED')
  expect(query.get('page_size')).toBe('200')
  expect(init.credentials).toBe('same-origin')
})
