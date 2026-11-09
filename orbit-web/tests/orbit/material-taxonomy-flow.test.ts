/** 实际ElementPlus组件交互，API替身不等同SQL验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElInput, ElButton } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Taxonomy from '@/views/orbit/materials/MaterialTaxonomy.vue'
import { taxonomyApi, TaxonomyApiError } from '@/api/orbit/material-taxonomy'
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const item = (n = 1) => ({
  id: id(n),
  name: `标签${n}`,
  group: '组',
  revision: 1,
  state: 'ENABLED' as const,
  visible_asset_count: null,
})
const page = (n = 1, next_cursor: string | null = null) => ({
  items: [item(n)],
  next_cursor,
  data_as_of: '2026-11-09T00:00:00.000Z',
  scope_version: 1,
})
const cap = () => ({ actor_id: 1, tenant_id: id(99), csrf_token: 'csrf-fixture-token' })
let w: VueWrapper
beforeEach(() => {
  vi.spyOn(taxonomyApi, 'capabilities').mockResolvedValue(cap())
  vi.spyOn(taxonomyApi, 'list').mockResolvedValue(page())
  vi.spyOn(taxonomyApi, 'get').mockResolvedValue(item())
})
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function render(can = (p: string) => p.startsWith('tags.')) {
  w = mount(Taxonomy, {
    props: { modelValue: true, can, contextKey: 'actor-a' },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
  return w
}
const button = (label: string) => w.findAllComponents(ElButton).find((b) => b.text() === label)!
it('标签独立读权限不借assets能力且显示未知引用数', async () => {
  await render((p) => p === 'tags.read')
  expect(taxonomyApi.capabilities).toHaveBeenCalledWith('READ', expect.any(AbortSignal))
  expect(w.text()).toContain('未知')
  expect(button('新增').props('disabled')).toBe(true)
})
it('单页有界翻页替换，旧页请求晚到不能覆盖关闭后的页面', async () => {
  vi.mocked(taxonomyApi.list).mockResolvedValueOnce(page(1, 'next')).mockResolvedValueOnce(page(2))
  await render()
  await button('下一页目录').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('标签2')
  expect(w.text()).not.toContain('标签1')
  expect(taxonomyApi.list).toHaveBeenLastCalledWith(
    'tags',
    expect.objectContaining({ cursor: 'next' }),
    expect.any(AbortSignal),
  )
})
it('未知新增冻结原正文，关闭重开后显式重试同key并回读', async () => {
  const write = vi
    .spyOn(taxonomyApi, 'write')
    .mockRejectedValueOnce(new TaxonomyApiError(0, 'NETWORK_UNAVAILABLE', '未知', true))
    .mockResolvedValue({ ...item(), name: '原始标签' })
  await render()
  w.findAllComponents(ElInput)[0].vm.$emit('update:modelValue', '原始标签')
  await flushPromises()
  await button('新增').trigger('click')
  await flushPromises()
  expect(w.findAllComponents(ElInput)[0].props('disabled')).toBe(true)
  const original = structuredClone(write.mock.calls[0][0])
  await w.setProps({ modelValue: false })
  await w.setProps({ modelValue: true })
  await flushPromises()
  expect(write).toHaveBeenCalledTimes(1)
  await button('重试原请求').trigger('click')
  await flushPromises()
  expect(write.mock.calls[1][0]).toEqual(original)
  expect(taxonomyApi.get).toHaveBeenCalledWith('tags', id(), expect.any(AbortSignal))
})
it('create-only可以新增，不发目录或回读请求', async () => {
  vi.spyOn(taxonomyApi, 'write').mockResolvedValue(item())
  await render((p) => p === 'tags.create')
  expect(taxonomyApi.list).not.toHaveBeenCalled()
  w.findAllComponents(ElInput)[0].vm.$emit('update:modelValue', '标签1')
  await flushPromises()
  await button('新增').trigger('click')
  await flushPromises()
  expect(taxonomyApi.write).toHaveBeenCalledTimes(1)
  expect(taxonomyApi.get).not.toHaveBeenCalled()
  expect(w.text()).toContain('无读取权限')
})
it('未知停用保留原原因、对象版本及键；重新显式重试后回读停用', async () => {
  const write = vi
    .spyOn(taxonomyApi, 'write')
    .mockRejectedValueOnce(new TaxonomyApiError(502, 'INVALID_RESPONSE', '未知', true))
    .mockResolvedValue({ ...item(), state: 'DISABLED', revision: 2 })
  vi.mocked(taxonomyApi.get).mockResolvedValue({ ...item(), state: 'DISABLED', revision: 2 })
  await render()
  await button('停用').trigger('click')
  await flushPromises()
  const reasonInput = w
    .findAllComponents(ElInput)
    .find((input) => input.props('type') === 'textarea')!
  reasonInput.vm.$emit('update:modelValue', '明确停用原因')
  await flushPromises()
  await button('确认停用').trigger('click')
  await flushPromises()
  expect(write).toHaveBeenCalledTimes(1)
  const original = JSON.parse(JSON.stringify(write.mock.calls[0][0]))
  expect(original).toMatchObject({
    operation: 'ARCHIVE',
    id: id(),
    revision: 1,
    body: { reason: '明确停用原因' },
  })
  await button('重试原请求').trigger('click')
  await flushPromises()
  expect(write.mock.calls[1][0]).toEqual(original)
  expect(w.text()).toContain('版本 2，停用')
})
it('重新认证到异主体不发送原未知请求也不展示原正文', async () => {
  const write = vi
    .spyOn(taxonomyApi, 'write')
    .mockRejectedValue(new TaxonomyApiError(0, 'NETWORK_UNAVAILABLE', '未知', true))
  await render()
  w.findAllComponents(ElInput)[0].vm.$emit('update:modelValue', '原主体私有草稿')
  await flushPromises()
  await button('新增').trigger('click')
  await flushPromises()
  vi.mocked(taxonomyApi.capabilities).mockResolvedValue({ ...cap(), actor_id: 2 })
  await w.setProps({ contextKey: 'actor-b' })
  await flushPromises()
  expect(w.text()).not.toContain('原主体私有草稿')
  expect(w.findAllComponents(ElInput)[0].props('modelValue')).toBe('')
  expect(w.findAllComponents(ElButton).some((b) => b.text() === '重试原请求')).toBe(false)
  expect(write).toHaveBeenCalledTimes(1)
})
it('关闭后迟到读取不能留存旧目录', async () => {
  let resolve!: (v: ReturnType<typeof page>) => void
  vi.mocked(taxonomyApi.list).mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await render()
  await w.setProps({ modelValue: false })
  resolve(page())
  await flushPromises()
  expect(w.text()).not.toContain('标签1')
})
it('编辑保存原对象CAS与分组，已知重名拒绝后可以更正并使用新键', async () => {
  const write = vi
    .spyOn(taxonomyApi, 'write')
    .mockRejectedValueOnce(new TaxonomyApiError(409, 'NAME_CONFLICT', '名称重复'))
    .mockResolvedValue({ ...item(), name: '修正标签', group: '新分组', revision: 2 })
  vi.mocked(taxonomyApi.get).mockResolvedValue({
    ...item(),
    name: '修正标签',
    group: '新分组',
    revision: 2,
  })
  await render()
  await button('编辑').trigger('click')
  await flushPromises()
  w.findAllComponents(ElInput)[0].vm.$emit('update:modelValue', '重名标签')
  w.findAllComponents(ElInput)[1].vm.$emit('update:modelValue', '新分组')
  await flushPromises()
  await button('保存修改').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('名称重复')
  expect(write.mock.calls[0][0]).toMatchObject({
    operation: 'EDIT',
    id: id(),
    revision: 1,
    body: { name: '重名标签', group: '新分组' },
  })
  w.findAllComponents(ElInput)[0].vm.$emit('update:modelValue', '修正标签')
  await flushPromises()
  await button('保存修改').trigger('click')
  await flushPromises()
  expect(write.mock.calls[1][0].key).not.toBe(write.mock.calls[0][0].key)
  expect(write.mock.calls[1][0].revision).toBe(1)
  expect(w.text()).toContain('已保存并回读：修正标签')
})
it('未知请求再遇403不释放原意图，恢复同主体权限后仍重试原键', async () => {
  const write = vi
    .spyOn(taxonomyApi, 'write')
    .mockRejectedValueOnce(new TaxonomyApiError(0, 'NETWORK_UNAVAILABLE', '未知', true))
    .mockRejectedValueOnce(new TaxonomyApiError(403, 'PERMISSION_DENIED', '无权'))
    .mockResolvedValue(item())
  await render()
  w.findAllComponents(ElInput)[0].vm.$emit('update:modelValue', '标签1')
  await flushPromises()
  await button('新增').trigger('click')
  await flushPromises()
  const original = JSON.parse(JSON.stringify(write.mock.calls[0][0]))
  await button('重试原请求').trigger('click')
  await flushPromises()
  expect(button('重试原请求').props('disabled')).toBe(true)
  await button('重新核对目录权限').trigger('click')
  await flushPromises()
  await button('重试原请求').trigger('click')
  await flushPromises()
  expect(write.mock.calls[2][0]).toEqual(original)
})
it('写入已确认但GET回读失败时不重发写入，明确保留回读失败状态', async () => {
  const write = vi.spyOn(taxonomyApi, 'write').mockResolvedValue(item())
  vi.mocked(taxonomyApi.get).mockRejectedValue(
    new TaxonomyApiError(503, 'READ_UNAVAILABLE', '读取暂不可用'),
  )
  await render()
  w.findAllComponents(ElInput)[0].vm.$emit('update:modelValue', '标签1')
  await flushPromises()
  await button('新增').trigger('click')
  await flushPromises()
  expect(write).toHaveBeenCalledTimes(1)
  expect(w.text()).toContain('操作已保存，但回读未完成')
  expect(w.findAllComponents(ElButton).some((b) => b.text() === '重试原请求')).toBe(false)
})
