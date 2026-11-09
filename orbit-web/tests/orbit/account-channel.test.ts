/** SDK/组件限定检查；真实SQL验收由主线单独执行。 */
import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElButton, ElInput, ElSelect } from 'element-plus'
import { accountChannelApi, parseAccountChannel } from '@/api/orbit/account-channel'
import Dialog from '@/views/orbit/accounts/AccountChannelDialog.vue'
import { channelApi } from '@/api/orbit/channels'
import { ReferenceApiError } from '@/api/orbit/references'
const id = '00000000-0000-4000-8000-000000000001'
const channel = '00000000-0000-4000-8000-000000000002'
const value = { account_id: id, channel_id: null, revision: 1, csrf_token: 'csrf-test' }
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('严格拒绝错账户、未知字段和损坏版本', () => {
  expect(parseAccountChannel(value, id)).toEqual(value)
  for (const item of [
    { ...value, account_id: channel },
    { ...value, extra: 1 },
    { ...value, revision: true },
    { ...value, channel_id: 'bad' },
  ])
    expect(() => parseAccountChannel(item, id)).toThrow()
})
it('PUT发送原CAS、幂等键和完整正文；错误回执保持未知', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ ...value, revision: 2, channel_id: channel, csrf_token: null }),
      ),
    )
  vi.stubGlobal('fetch', fetcher)
  const intent = {
    accountId: id,
    key: 'same-intent-key-0001',
    csrf: 'csrf-test',
    revision: 1,
    body: { channel_id: channel, reason: '改绑当前渠道' },
  }
  await accountChannelApi.save(intent)
  const init = fetcher.mock.calls[0][1]
  expect(init.headers['If-Match']).toBe('"1"')
  expect(init.headers['Idempotency-Key']).toBe(intent.key)
  expect(JSON.parse(init.body)).toEqual(intent.body)
  fetcher.mockResolvedValue(
    new Response(JSON.stringify({ ...value, revision: 2, channel_id: null, csrf_token: null })),
  )
  await expect(accountChannelApi.save(intent)).rejects.toMatchObject({ status: 502 })
})
async function render(csrf: string | null = 'csrf-test') {
  vi.spyOn(accountChannelApi, 'get').mockResolvedValue({ ...value, csrf_token: csrf })
  vi.spyOn(channelApi, 'list').mockResolvedValue({
    items: [],
    next_cursor: null,
    data_as_of: '2026-11-09T00:00:00.000Z',
    scope_version: 1,
  })
  const w = mount(Dialog, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  ;(w.vm as unknown as { open: (v: unknown) => void }).open({ id, name: '账户', external_id: '1' })
  await flushPromises()
  return w
}
it('只读账户能查看但不能提交', async () => {
  const w = await render(null)
  expect(
    w
      .findAllComponents(ElButton)
      .find((b) => b.text() === '保存关联')!
      .props('disabled'),
  ).toBe(true)
  w.unmount()
})
it('未知结果只显式重试同一意图，成功后GET回读', async () => {
  const save = vi
    .spyOn(accountChannelApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '中断'))
    .mockResolvedValue({ ...value, revision: 2, csrf_token: null })
  const w = await render()
  w.findComponent(ElInput).vm.$emit('update:modelValue', '清空关联原因')
  await flushPromises()
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '保存关联')!
    .trigger('click')
  await flushPromises()
  expect(save).toHaveBeenCalledTimes(1)
  expect(w.findComponent(ElSelect).props('disabled')).toBe(true)
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '重试原请求')!
    .trigger('click')
  await flushPromises()
  expect(save).toHaveBeenCalledTimes(2)
  expect(save.mock.calls[0][0]).toEqual(save.mock.calls[1][0])
  expect(accountChannelApi.get).toHaveBeenCalledTimes(2)
  w.unmount()
})
it('未知意图关闭再开与撤权拒绝后仍保留原键正文CAS', async () => {
  const save = vi
    .spyOn(accountChannelApi, 'save')
    .mockRejectedValueOnce(new ReferenceApiError(0, 'NETWORK_UNAVAILABLE', '中断'))
    .mockRejectedValueOnce(new ReferenceApiError(403, 'CSRF_INVALID', '已失效'))
    .mockResolvedValue({ ...value, revision: 2, csrf_token: null })
  const w = await render()
  w.findComponent(ElInput).vm.$emit('update:modelValue', '原原因')
  await flushPromises()
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '保存关联')!
    .trigger('click')
  await flushPromises()
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '关闭')!
    .trigger('click')
  await flushPromises()
  ;(w.vm as unknown as { open: (v: unknown) => void }).open({ id, name: '账户', external_id: '1' })
  await flushPromises()
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '重试原请求')!
    .trigger('click')
  await flushPromises()
  expect(w.findAllComponents(ElButton).some((b) => b.text() === '重试原请求')).toBe(true)
  ;(w.vm as unknown as { open: (v: unknown) => void }).open({ id, name: '账户', external_id: '1' })
  await flushPromises()
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '重试原请求')!
    .trigger('click')
  await flushPromises()
  expect(save.mock.calls.map(([i]) => [i.key, i.body, i.revision])).toEqual(
    Array(3).fill([save.mock.calls[0][0].key, { channel_id: null, reason: '原原因' }, 1]),
  )
  w.unmount()
})
