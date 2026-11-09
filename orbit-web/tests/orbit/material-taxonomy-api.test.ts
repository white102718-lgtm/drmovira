/** 目录SDK严格合同与运输未知语义；不替代真实HTTP服务端验收。 */
import { afterEach, expect, it, vi } from 'vitest'
import {
  taxonomyApi,
  parseTaxonomy,
  parseTaxonomyPage,
  type TaxonomyIntent,
} from '@/api/orbit/material-taxonomy'
const id = '00000000-0000-4000-8000-000000000001'
const tag = { id, name: '标签', group: '分组', revision: 1, state: 'ENABLED' }
const read = { ...tag, visible_asset_count: null }
const page = {
  items: [read],
  next_cursor: null,
  data_as_of: '2026-11-09T00:00:00.000Z',
  scope_version: 1,
}
const intent: TaxonomyIntent = {
  kind: 'tags',
  operation: 'CREATE',
  actor_id: 1,
  tenant_id: id,
  key: 'same-intent-key-fixture',
  body: { name: '标签', group: '分组' },
}
afterEach(() => vi.unstubAllGlobals())
it('GET可见计数未知保持null，写响应不扩充计数', () => {
  expect(parseTaxonomy(read, 'tags', true)).toEqual(read)
  expect(parseTaxonomy(tag, 'tags', false)).toEqual(tag)
  expect(() => parseTaxonomy(tag, 'tags', true)).toThrow()
  expect(() => parseTaxonomy(read, 'tags', false)).toThrow()
})
it.each([
  { ...read, revision: true },
  { ...read, id: 'bad' },
  { ...read, name: '' },
  { ...read, group: 'x'.repeat(31) },
  { ...read, visible_asset_count: -1 },
  { ...read, extra: 'field' },
])('拒绝目录损坏字段 %#', (value) => expect(() => parseTaxonomy(value, 'tags', true)).toThrow())
it.each([
  { ...page, items: [read, read] },
  { ...page, items: [], next_cursor: 'next' },
  { ...page, data_as_of: '2026-02-30T00:00:00.000Z' },
  { ...page, items: Array(21).fill(read) },
])('拒绝重复、无界或错误日期分页 %#', (value) =>
  expect(() => parseTaxonomyPage(value, 'tags', 20)).toThrow(),
)
it('独立READ能力返回null CSRF且query显式操作', async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(
      async () => new Response(JSON.stringify({ actor_id: 1, tenant_id: id, csrf_token: null })),
    )
  vi.stubGlobal('fetch', fetcher)
  await expect(taxonomyApi.capabilities('READ')).resolves.toMatchObject({ csrf_token: null })
  expect(fetcher.mock.calls[0][0]).toContain('material-taxonomy/capabilities?operation=READ')
  await expect(taxonomyApi.capabilities('CREATE')).rejects.toMatchObject({ status: 502 })
})
it('PUT发送quoted CAS及原键，严格核回执ID版本正文', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...tag, revision: 2 })))
  vi.stubGlobal('fetch', fetcher)
  await taxonomyApi.write({ ...intent, operation: 'EDIT', id, revision: 1 }, 'csrf-test')
  expect(fetcher.mock.calls[0][1].headers).toMatchObject({
    'If-Match': '"1"',
    'Idempotency-Key': intent.key,
  })
  expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(intent.body)
  fetcher.mockResolvedValue(new Response(JSON.stringify({ ...tag, revision: 3 })))
  await expect(
    taxonomyApi.write({ ...intent, operation: 'EDIT', id, revision: 1 }, 'csrf-test'),
  ).rejects.toMatchObject({ unknown_result: true })
})
it('已知业务409与502/坏响应/网络未知明确区分', async () => {
  const fetcher = vi
    .fn()
    .mockRejectedValueOnce(new Error('network'))
    .mockResolvedValueOnce(new Response('broken', { status: 502 }))
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          code: 'NAME_CONFLICT',
          message: '重复名称',
          field_errors: [],
          retryable: false,
          request_id: id,
        }),
        { status: 409 },
      ),
    )
    .mockResolvedValueOnce(new Response('broken', { status: 403 }))
  vi.stubGlobal('fetch', fetcher)
  for (const unknown of [true, true, false, true])
    await expect(taxonomyApi.write(intent, 'csrf-test')).rejects.toMatchObject({
      unknown_result: unknown,
    })
})
it('读取超过2MiB拒绝，不接受无界目录', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(' '.repeat(2 * 1024 * 1024 + 1))))
  await expect(taxonomyApi.list('tags', { page_size: 20 })).rejects.toMatchObject({
    status: 502,
    code: 'INVALID_RESPONSE',
    unknown_result: false,
  })
})
