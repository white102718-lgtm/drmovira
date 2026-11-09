import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton } from 'element-plus'
import { it, expect, vi, afterEach } from 'vitest'
import Panel from '@/views/orbit/environments/EnvironmentCapabilitiesPanel.vue'
import { environmentCapabilityApi } from '@/api/orbit/environment-capabilities'
let w: VueWrapper
const page = { items: [], next_cursor: null, data_as_of: '2026-11-10T00:00:00Z', scope_version: 1 }
afterEach(() => {
  w?.unmount()
  vi.restoreAllMocks()
})
it('显示未验证空态和全部原字段', async () => {
  vi.spyOn(environmentCapabilityApi, 'list').mockResolvedValue(page)
  w = mount(Panel, {
    props: { active: true, contextKey: 'actor1' },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  expect(w.text()).toContain('所有未列出动作均未验证')
  for (const s of [
    '工作流版本',
    '适配器版本',
    'AdsPower 版本',
    '内核版本',
    '页面语言',
    '验收证据',
    '验收时间',
  ])
    expect(w.text()).toContain(s)
})
it('翻页失败清除旧结果并提供重新读取', async () => {
  const api = vi
    .spyOn(environmentCapabilityApi, 'list')
    .mockResolvedValueOnce({ ...page, next_cursor: 'next' })
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValue(page)
  w = mount(Panel, {
    props: { active: true, contextKey: 'actor1' },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '下一页')!
    .trigger('click')
  await flushPromises()
  expect(w.text()).toContain('能力读取失败')
  expect(w.text()).not.toContain('下一页')
  await w
    .findAllComponents(ElButton)
    .find((b) => b.text() === '重新读取')!
    .trigger('click')
  await flushPromises()
  expect(api).toHaveBeenLastCalledWith(undefined, expect.any(AbortSignal))
  expect(w.text()).not.toContain('能力读取失败')
})
it('关闭或身份变化忽略旧请求', async () => {
  let resolve!: (p: typeof page) => void
  vi.spyOn(environmentCapabilityApi, 'list').mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  w = mount(Panel, {
    props: { active: true, contextKey: 'actor1' },
    global: { plugins: [ElementPlus] },
  })
  await w.setProps({ active: false })
  resolve(page)
  await flushPromises()
  expect(w.text()).not.toContain('数据时间')
})
