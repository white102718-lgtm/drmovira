/** 纯SDK/组件检查；不作为真实SQL或授权验收。 */
import { afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import Select from '@/views/orbit/rules/RuleListFilterSelect.vue'
import { parseRuleFilterPage, ruleListFilterApi } from '@/api/orbit/rule-list-filters'
import { RuleApiError } from '@/api/orbit/rules'
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const page = (
  items = [{ id: id(1), label: null as string | null }],
  next_cursor: string | null = null,
) => ({ items, next_cursor, data_as_of: '2026-11-09T01:00:00.000Z', scope_version: 1 })
afterEach(() => vi.restoreAllMocks())
it('保留真实nullable名称而不制造指标名称', () =>
  expect(parseRuleFilterPage(page())).toEqual(page()))
it.each([
  { ...page(), items: [{ id: 'bad', label: null }] },
  {
    ...page(),
    items: [
      { id: id(2), label: null },
      { id: id(1), label: null },
    ],
  },
  {
    ...page(),
    items: [
      { id: id(1), label: null },
      { id: id(1), label: null },
    ],
  },
  { ...page(), items: [{ id: id(1), label: 3 }] },
  { ...page(), items: [{ id: id(1), label: null, name: '假名' }] },
  { ...page(), scope_version: true },
  { ...page(), data_as_of: '2026-02-30T01:00:00.000Z' },
  { ...page(), items: [], next_cursor: 'next' },
  { ...page(), items: Array.from({ length: 201 }, (_, i) => ({ id: id(i), label: null })) },
])('拒绝损坏或无界响应 %#', (v) => expect(() => parseRuleFilterPage(v)).toThrow())
const render = (props = {}) =>
  mount(Select, {
    props: { kind: 'OPERATOR', modelValue: '', contextKey: 'actor-A', refreshKey: 0, ...props },
    global: { plugins: [ElementPlus] },
  })
it('仅展开时读取单页，翻页替换而不无限累加', async () => {
  const api = vi
    .spyOn(ruleListFilterApi, 'list')
    .mockResolvedValueOnce(page([{ id: id(1), label: '真实姓名' }], 'next'))
    .mockResolvedValueOnce(page([{ id: id(2), label: null }]))
  const w = render()
  expect(api).not.toHaveBeenCalled()
  w.findComponent(ElSelect).vm.$emit('visible-change', true)
  await flushPromises()
  expect(api).toHaveBeenCalledWith('OPERATOR', undefined, expect.any(AbortSignal))
  // Footer由真实ElementPlus渲染；方法从组件事件链触发。
  const buttons = w.findAllComponents({ name: 'ElButton' })
  await buttons.find((b) => b.text() === '下一页候选')!.trigger('click')
  await flushPromises()
  expect(api).toHaveBeenLastCalledWith('OPERATOR', 'next', expect.any(AbortSignal))
  expect(w.findAllComponents({ name: 'ElOption' }).map((x) => x.props('value'))).toEqual([id(2)])
  w.unmount()
})
it('无read权限不读候选', async () => {
  const api = vi.spyOn(ruleListFilterApi, 'list')
  const w = render({ disabled: true })
  w.findComponent(ElSelect).vm.$emit('visible-change', true)
  await flushPromises()
  expect(api).not.toHaveBeenCalled()
  w.unmount()
})
it('上下文变化丢弃迟到候选并清选择', async () => {
  let resolve!: (v: ReturnType<typeof page>) => void
  vi.spyOn(ruleListFilterApi, 'list').mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  const w = render({ modelValue: id(1) })
  w.findComponent(ElSelect).vm.$emit('visible-change', true)
  await flushPromises()
  await w.setProps({ contextKey: 'actor-B' })
  resolve(page())
  await flushPromises()
  expect(w.findAllComponents({ name: 'ElOption' })).toHaveLength(0)
  expect(w.emitted('update:modelValue')?.at(-1)).toEqual([''])
  w.unmount()
})
it('撤权清资料并通知父页关闭旧数据', async () => {
  const denied = new RuleApiError(403, 'PERMISSION_DENIED', '无权')
  vi.spyOn(ruleListFilterApi, 'list').mockRejectedValue(denied)
  const w = render()
  w.findComponent(ElSelect).vm.$emit('visible-change', true)
  await flushPromises()
  expect(w.emitted('denied')?.[0]).toEqual([denied])
  expect(w.findAllComponents({ name: 'ElOption' })).toHaveLength(0)
  w.unmount()
})

it('当前渠道候选使用CHANNEL端点并保留名称', async () => {
  const api = vi
    .spyOn(ruleListFilterApi, 'list')
    .mockResolvedValue(page([{ id: id(3), label: '当前渠道甲' }]))
  const w = render({ kind: 'CHANNEL' })
  expect(w.findComponent(ElSelect).props('placeholder')).toBe('全部渠道')
  w.findComponent(ElSelect).vm.$emit('visible-change', true)
  await flushPromises()
  expect(api).toHaveBeenCalledWith('CHANNEL', undefined, expect.any(AbortSignal))
  expect(w.findAllComponents({ name: 'ElOption' })[0].props('label')).toContain('当前渠道甲')
  w.unmount()
})
