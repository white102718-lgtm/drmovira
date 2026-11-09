/** 真实ElementPlus组件+SDK替身；不是Rule运行来源/HTTP/浏览器验收。 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElDatePicker, ElSelect } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Runs from '@/views/orbit/rules/RuleRuns.vue'
import { RuleApiError, rulesApi, type RulePage, type RuleRun } from '@/api/orbit/rules'
vi.mock('@/api/orbit/rules', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rules')>()),
  rulesApi: { runs: vi.fn() },
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const run = (n = 1): RuleRun => ({
  id: id(n + 10),
  rule_id: id(),
  rule_revision: 7,
  schedule_slot: '2026-11-09T00:00:00.123Z',
  snapshot_id: id(3),
  state: 'UNKNOWN',
  hit_count: 0,
  reason_code: null,
})
const page = (items = [run()], next_cursor: string | null = null): RulePage<RuleRun> => ({
  items,
  next_cursor,
  data_as_of: '2026-11-09T00:00:01.000Z',
  scope_version: 9,
})
let wrapper: VueWrapper
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(rulesApi.runs).mockResolvedValue(page())
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function render(props = {}) {
  wrapper = mount(Runs, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
    props: { ruleId: id(), permissionCodes: ['rules.read'], contextKey: 'session-a', ...props },
  })
  await flushPromises()
  return wrapper
}
function button(label: string) {
  const found = wrapper.findAll('button').find((item) => item.text() === label)
  expect(found, label).toBeTruthy()
  return found!
}
async function select(label: string, value: unknown) {
  const control = wrapper
    .findAllComponents(ElSelect)
    .find((item) => item.props('ariaLabel') === label)
  expect(control).toBeTruthy()
  control!.vm.$emit('update:modelValue', value)
  control!.vm.$emit('change', value)
  await flushPromises()
}
async function date(index: number, value: string | null) {
  const control = wrapper.findAllComponents(ElDatePicker)[index]
  expect(control).toBeTruthy()
  control.vm.$emit('update:modelValue', value)
  await flushPromises()
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
it('原八字段与真实UTC/0/null，默认50条不补运行时间或成功', async () => {
  await render()
  expect(rulesApi.runs).toHaveBeenCalledWith(id(), { page_size: 50 }, expect.any(AbortSignal))
  const text = wrapper.text()
  for (const value of [
    id(11),
    id(),
    '7',
    '2026-11-09T00:00:00.123Z',
    id(3),
    '结果未知',
    '0',
    '未提供',
    '范围版本 9',
  ])
    expect(text).toContain(value)
  expect(text).not.toContain('已成功')
})
it('只有有效空页可显示空记录，加载/403/503不是空成功', async () => {
  vi.mocked(rulesApi.runs).mockResolvedValue(page([]))
  await render()
  expect(wrapper.text()).toContain('当前页无运行记录')
  expect(wrapper.find('table').exists()).toBe(false)
})
it.each([20, 50, 100, 200] as const)('原四档%d页重置首页', async (size) => {
  await render()
  await select('记录每页条数', size)
  expect(rulesApi.runs).toHaveBeenLastCalledWith(id(), { page_size: size }, expect.any(AbortSignal))
})
it('真实next/previous栈保持原opaque cursor，首尾禁用', async () => {
  vi.mocked(rulesApi.runs)
    .mockResolvedValueOnce(page([run()], 'page-2'))
    .mockResolvedValueOnce(page([run(2)], 'page-3'))
    .mockResolvedValueOnce(page([run(3)]))
    .mockResolvedValue(page())
  await render()
  expect(button('上一页记录').attributes('disabled')).toBeDefined()
  await button('下一页记录').trigger('click')
  await flushPromises()
  expect(rulesApi.runs).toHaveBeenLastCalledWith(
    id(),
    { page_size: 50, cursor: 'page-2' },
    expect.any(AbortSignal),
  )
  await button('下一页记录').trigger('click')
  await flushPromises()
  expect(rulesApi.runs).toHaveBeenLastCalledWith(
    id(),
    { page_size: 50, cursor: 'page-3' },
    expect.any(AbortSignal),
  )
  expect(button('下一页记录').attributes('disabled')).toBeDefined()
  await button('上一页记录').trigger('click')
  await flushPromises()
  expect(rulesApi.runs).toHaveBeenLastCalledWith(
    id(),
    { page_size: 50, cursor: 'page-2' },
    expect.any(AbortSignal),
  )
})
it('状态和原日期筛选只有提交生效，翻页冻结已提交query', async () => {
  vi.mocked(rulesApi.runs).mockResolvedValue(page([run()], 'next'))
  await render()
  await select('运行状态', 'FAILED')
  await date(0, '2026-11-01')
  await date(1, '2026-11-09')
  expect(rulesApi.runs).toHaveBeenCalledTimes(1)
  await button('查询记录').trigger('click')
  await flushPromises()
  const query = { page_size: 50, status: 'FAILED', date_from: '2026-11-01', date_to: '2026-11-09' }
  expect(rulesApi.runs).toHaveBeenLastCalledWith(id(), query, expect.any(AbortSignal))
  await select('运行状态', 'RUNNING')
  await date(0, '2026-10-01')
  await button('下一页记录').trigger('click')
  await flushPromises()
  expect(rulesApi.runs).toHaveBeenLastCalledWith(
    id(),
    { ...query, cursor: 'next' },
    expect.any(AbortSignal),
  )
  await button('查询记录').trigger('click')
  await flushPromises()
  expect(rulesApi.runs).toHaveBeenLastCalledWith(
    id(),
    { ...query, status: 'RUNNING', date_from: '2026-10-01' },
    expect.any(AbortSignal),
  )
})
it('清空日期不传null，父原其余参数完整保留不修改', async () => {
  const filters = {
    q: '原q',
    operator_user_id: id(4),
    channel_id: 'META',
    metric_profile_id: id(5),
    entity_type: 'AD' as const,
  }
  await render({ filters })
  await date(0, '2026-11-01')
  await date(0, null)
  await button('查询记录').trigger('click')
  await flushPromises()
  expect(rulesApi.runs).toHaveBeenLastCalledWith(
    id(),
    { ...filters, page_size: 50 },
    expect.any(AbortSignal),
  )
  expect(filters.q).toBe('原q')
})
it.each([403, 503, 409])('实际%d/code/path与请求ID可见，不自动重试/空成功', async (status) => {
  vi.mocked(rulesApi.runs).mockRejectedValue(
    new RuleApiError(
      status,
      'RULE_RUN_SOURCE',
      '来源不可用',
      [{ path: '/date_from', code: 'SOURCE', message: '真实日期语义未就绪', constraint: null }],
      true,
      id(99),
    ),
  )
  await render()
  expect(wrapper.text()).toContain('RULE_RUN_SOURCE')
  expect(wrapper.text()).toContain('/date_from: 真实日期语义未就绪')
  expect(wrapper.text()).toContain(id(99))
  expect(wrapper.text()).not.toContain('当前页无运行记录')
  expect(rulesApi.runs).toHaveBeenCalledTimes(1)
})
it('旧游标409后重新查询回首页，不悄悄调整结果', async () => {
  vi.mocked(rulesApi.runs)
    .mockResolvedValueOnce(page([run()], 'next'))
    .mockRejectedValueOnce(new RuleApiError(409, 'RULE_CURSOR_STALE', '范围已变化'))
    .mockResolvedValue(page())
  await render()
  await button('下一页记录').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('RULE_CURSOR_STALE')
  expect(wrapper.text()).not.toContain(id(11))
  await button('查询记录').trigger('click')
  await flushPromises()
  expect(rulesApi.runs).toHaveBeenLastCalledWith(id(), { page_size: 50 }, expect.any(AbortSignal))
})
it('无read或未选择规则不借其它权限读记录', async () => {
  await render({ permissionCodes: ['rules.create', 'rules.edit'] })
  expect(rulesApi.runs).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('缺少规则读取权限')
  await wrapper.setProps({ permissionCodes: ['rules.read'], ruleId: '' })
  await flushPromises()
  expect(rulesApi.runs).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('尚未选择规则')
})
it('规则切换取消旧signal，late响应不覆盖新规则', async () => {
  const old = deferred<RulePage<RuleRun>>()
  vi.mocked(rulesApi.runs)
    .mockReturnValueOnce(old.promise)
    .mockResolvedValue(page([{ ...run(2), rule_id: id(2), reason_code: 'CURRENT' }]))
  await render()
  const firstSignal = vi.mocked(rulesApi.runs).mock.calls[0][2]!
  expect(wrapper.text()).toContain('正在读取运行记录')
  await wrapper.setProps({ ruleId: id(2) })
  await flushPromises()
  expect(firstSignal.aborted).toBe(true)
  old.resolve(page([{ ...run(), reason_code: 'OLD-LATE' }]))
  await flushPromises()
  expect(wrapper.text()).toContain('CURRENT')
  expect(wrapper.text()).not.toContain('OLD-LATE')
})
it('认证/权限撤回立即清除已读数据并拒绝旧晚回', async () => {
  const old = deferred<RulePage<RuleRun>>()
  vi.mocked(rulesApi.runs).mockReturnValueOnce(old.promise)
  await render()
  const signal = vi.mocked(rulesApi.runs).mock.calls[0][2]!
  await wrapper.setProps({ contextKey: 'session-b', permissionCodes: [] })
  old.resolve(page([{ ...run(), reason_code: 'SECRET-OLD' }]))
  await flushPromises()
  expect(signal.aborted).toBe(true)
  expect(wrapper.text()).not.toContain('SECRET-OLD')
  expect(wrapper.text()).toContain('缺少规则读取权限')
})
it('父筛选更新取消旧页，晚失败不得覆盖新成功', async () => {
  let reject!: (e: unknown) => void
  const pending = new Promise<RulePage<RuleRun>>((_resolve, fail) => {
    reject = fail
  })
  vi.mocked(rulesApi.runs).mockReturnValueOnce(pending).mockResolvedValue(page())
  await render()
  await wrapper.setProps({ filters: { channel_id: 'META' } })
  await flushPromises()
  reject(new RuleApiError(503, 'OLD-ERROR', '旧来源失败'))
  await flushPromises()
  expect(wrapper.text()).not.toContain('OLD-ERROR')
  expect(wrapper.text()).toContain(id(11))
})
it('卸载取消且AbortError不渲染成来源失败', async () => {
  const pending = deferred<RulePage<RuleRun>>()
  vi.mocked(rulesApi.runs).mockReturnValue(pending.promise)
  await render()
  const signal = vi.mocked(rulesApi.runs).mock.calls[0][2]!
  wrapper.unmount()
  expect(signal.aborted).toBe(true)
  pending.resolve(page())
  await flushPromises()
})
it('不接受另一个规则的有效结构记录页', async () => {
  vi.mocked(rulesApi.runs).mockResolvedValue(page([{ ...run(), rule_id: id(88) }]))
  await render()
  expect(wrapper.text()).toContain('INVALID_RESPONSE')
  expect(wrapper.text()).not.toContain(id(88))
})
