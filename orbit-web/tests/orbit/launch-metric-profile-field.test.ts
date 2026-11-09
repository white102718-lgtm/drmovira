/** 真实ElementPlus挂载+GET替身，仅验证组件逻辑，不是实际目录或平台验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Field from '@/views/orbit/launch/PlanMetricProfileField.vue'
import {
  metricProfilesApi as api,
  MetricProfileError,
  type MetricProfilePage,
} from '@/api/orbit/metric-profiles'
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const page = (n = 1, cursor: string | null = null): MetricProfilePage => ({
  items: [
    {
      id: id(n),
      version: 'observed-v001',
      source: 'FIXTURE',
      register_action_type: null,
      purchase_action_type: 'opaque-action',
      value_action_type: null,
      attribution_windows: ['opaque-window'],
      action_report_time: 'opaque-report',
      timezone_policy: 'ACCOUNT_LOCAL',
      breakdown: 'TOTAL',
      maturity_days: 28,
      verified: true,
    },
  ],
  next_cursor: cursor,
  data_as_of: '2026-11-08T00:00:00Z',
  scope_version: 7,
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.spyOn(api, 'list').mockResolvedValue(page())
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start(props: Record<string, unknown> = {}) {
  wrapper = mount(Field, {
    attachTo: document.body,
    props: {
      bindingKey: 'group-a',
      contextKey: 'actor-1',
      modelValue: id(99),
      canRead: true,
      ...props,
    },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
const button = (label: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (v) => v.textContent?.trim() === label,
  )!
async function click(label: string) {
  expect(button(label), label).toBeTruthy()
  button(label).click()
  await flushPromises()
}
async function manual(value: string) {
  const input = wrapper!.find('input')
  await input.setValue(value)
  await flushPromises()
}
it('没有monitor.read仍能手填原UUID，目录不能打开且零GET；清除传undefined不是null', async () => {
  await start({ canRead: false })
  expect(button('从指标目录选择').disabled).toBe(true)
  await manual(id(3))
  await manual('')
  expect(wrapper!.emitted('update:modelValue')).toEqual([[id(3)], [undefined]])
  expect(api.list).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('仍可填写已有UUID保存草稿')
})
it('readonly或未知写入禁用时不能发GET或修改UUID', async () => {
  await start({ disabled: true })
  expect(wrapper!.get('input').attributes('disabled')).toBeDefined()
  wrapper!.findComponent({ name: 'ElInput' }).vm.$emit('update:modelValue', id(4))
  await click('从指标目录选择')
  expect(wrapper!.emitted('update:modelValue')).toBeUndefined()
  expect(api.list).not.toHaveBeenCalled()
})
it('只在显式打开目录后读真实原GET参数；候选未确认不改草稿', async () => {
  await start()
  expect(api.list).not.toHaveBeenCalled()
  await click('从指标目录选择')
  expect(api.list).toHaveBeenCalledWith(
    { q: '', metric_profile_id: null, cursor: null, page_size: 50 },
    expect.any(AbortSignal),
  )
  await click('查看并选择')
  expect(wrapper!.emitted('update:modelValue')).toBeUndefined()
  await click('取消指标选择')
  expect(wrapper!.emitted('update:modelValue')).toBeUndefined()
})
it('全部12原字段和null/windows完整显示，FIXTURE verified=true仍醒目标非平台验证', async () => {
  await start()
  await click('从指标目录选择')
  await click('查看并选择')
  const details = document.querySelector('.metric-detail')!
  expect(details.querySelectorAll('.el-descriptions__label')).toHaveLength(12)
  expect(details.textContent).toContain('未知（null）')
  for (const value of [
    'opaque-action',
    'opaque-window',
    'opaque-report',
    'ACCOUNT_LOCAL',
    'TOTAL',
    '28',
    'true',
    '非真实平台验证',
  ])
    expect(details.textContent).toContain(value)
  await click('使用此指标配置')
  expect(wrapper!.emitted('update:modelValue')).toEqual([[id(1)]])
  expect(wrapper!.emitted('browsing')).toEqual([[true], [false]])
})
it('分页遵循next_cursor而非返回条数，上一页还原原cursor', async () => {
  vi.mocked(api.list)
    .mockResolvedValueOnce(page(1, 'actual-cursor'))
    .mockResolvedValueOnce(page(2))
    .mockResolvedValueOnce(page(1, 'actual-cursor'))
  await start()
  await click('从指标目录选择')
  expect(button('下一页指标').disabled).toBe(false)
  await click('下一页指标')
  expect(api.list).toHaveBeenLastCalledWith(
    expect.objectContaining({ cursor: 'actual-cursor' }),
    expect.any(AbortSignal),
  )
  expect(document.body.textContent).toContain('第2页')
  await click('上一页指标')
  expect(api.list).toHaveBeenLastCalledWith(
    expect.objectContaining({ cursor: null }),
    expect.any(AbortSignal),
  )
})
it.each([20, 50, 100, 200])('每页%s条切换重置游标并实际发该参数', async (size) => {
  await start()
  await click('从指标目录选择')
  wrapper!.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', size)
  wrapper!.findComponent({ name: 'ElSelect' }).vm.$emit('change', size)
  await flushPromises()
  expect(api.list).toHaveBeenLastCalledWith(
    expect.objectContaining({ page_size: size, cursor: null }),
    expect.any(AbortSignal),
  )
})
it('UUID查询只在点击查询后发送，换条件禁止原游标翻页', async () => {
  vi.mocked(api.list).mockResolvedValue(page(1, 'next'))
  await start()
  await click('从指标目录选择')
  const inputs = wrapper!.findAllComponents({ name: 'ElInput' })
  inputs[1].vm.$emit('update:modelValue', id(3))
  await flushPromises()
  expect(api.list).toHaveBeenCalledTimes(1)
  expect(button('下一页指标').disabled).toBe(true)
  await click('查询指标目录')
  expect(api.list).toHaveBeenLastCalledWith(
    expect.objectContaining({ q: id(3), cursor: null }),
    expect.any(AbortSignal),
  )
})
it.each([401, 403])('HTTP%s显示拒绝并清候选，不能以空目录冒充成功', async (status) => {
  vi.mocked(api.list).mockRejectedValue(new MetricProfileError(status, 'PERMISSION_DENIED', '拒绝'))
  await start()
  await click('从指标目录选择')
  expect(document.body.textContent).toContain('这不是空目录')
  expect(document.body.textContent).not.toContain('本次查询没有指标配置')
  expect(wrapper!.get('input').element.value).toBe(id(99))
  expect(button('使用此指标配置').disabled).toBe(true)
})
it('409清游标后显式重查首页，原UUID不丢', async () => {
  vi.mocked(api.list)
    .mockResolvedValueOnce(page(1, 'old'))
    .mockRejectedValueOnce(new MetricProfileError(409, 'SCOPE_CHANGED', '变化'))
    .mockResolvedValueOnce(page())
  await start()
  await click('从指标目录选择')
  await click('下一页指标')
  expect(document.body.textContent).toContain('请重新查询首页')
  await click('查询指标目录')
  expect(api.list).toHaveBeenLastCalledWith(
    expect.objectContaining({ cursor: null }),
    expect.any(AbortSignal),
  )
  expect(wrapper!.emitted('update:modelValue')).toBeUndefined()
})
it.each([new MetricProfileError(503, 'DEPENDENCY_REQUIRED', '来源未配置'), new Error('网络中断')])(
  '依赖/网络失败可显式重读，不丢手填UUID',
  async (cause) => {
    vi.mocked(api.list).mockRejectedValueOnce(cause).mockResolvedValueOnce(page())
    await start()
    await click('从指标目录选择')
    expect(document.body.textContent).toContain('指标目录读取失败')
    await click('查询指标目录')
    expect(button('查看并选择')).toBeTruthy()
    expect(wrapper!.emitted('update:modelValue')).toBeUndefined()
  },
)
it.each([
  { bindingKey: 'group-b' },
  { contextKey: 'actor-2' },
  { canRead: false },
  { disabled: true },
])('绑定/权限/锁变化中止迟到响应且不改另一个广告组：%j', async (change) => {
  let resolve!: (value: MetricProfilePage) => void
  vi.mocked(api.list).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  await start()
  await click('从指标目录选择')
  const signal = vi.mocked(api.list).mock.calls[0][1]!
  await wrapper!.setProps(change)
  expect(signal.aborted).toBe(true)
  resolve(page(3))
  await flushPromises()
  expect(wrapper!.emitted('update:modelValue')).toBeUndefined()
  expect(wrapper!.emitted('browsing')?.at(-1)).toEqual([false])
})
it('关闭与卸载均取消当前GET，没有后台轮询或自动重试', async () => {
  vi.mocked(api.list).mockImplementation(() => new Promise(() => {}))
  await start()
  await click('从指标目录选择')
  const first = vi.mocked(api.list).mock.calls[0][1]!
  await click('取消指标选择')
  expect(first.aborted).toBe(true)
  await click('从指标目录选择')
  const second = vi.mocked(api.list).mock.calls[1][1]!
  wrapper!.unmount()
  wrapper = undefined
  expect(second.aborted).toBe(true)
  expect(api.list).toHaveBeenCalledTimes(2)
})
