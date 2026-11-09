/** 真实ElementPlus挂载；API替身仅验证只读目录状态机，不代表真实HTTP或权威配置验收。 */
import { reactive } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Page from '@/views/orbit/monitor/MetricProfiles.vue'
import {
  metricProfilesApi as api,
  MetricProfileError,
  type MetricProfile,
  type MetricProfilePage,
} from '@/api/orbit/metric-profiles'
const state = vi.hoisted(() => ({
  user: { id: '1', roles: ['tester'], permissions: ['monitor.read'] },
}))
vi.mock('@/store/modules/user', () => ({ default: () => state.user }))
const id = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const profile = (n = 1): MetricProfile => ({
  id: id(n),
  version: 'version-1',
  source: 'FIXTURE',
  register_action_type: null,
  purchase_action_type: 'purchase',
  value_action_type: 'purchase_value',
  attribution_windows: ['7d_click', '1d_view'],
  action_report_time: 'conversion',
  timezone_policy: 'ACCOUNT_LOCAL',
  breakdown: 'TOTAL',
  maturity_days: 28,
  verified: false,
})
const page = (n = 1, next: string | null = null): MetricProfilePage => ({
  items: [profile(n)],
  next_cursor: next,
  data_as_of: '2026-11-08T00:00:00Z',
  scope_version: 7,
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  state.user = reactive({ id: '1', roles: ['tester'], permissions: ['monitor.read'] })
  vi.spyOn(api, 'list').mockImplementation(() => Promise.resolve(page()))
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start(props: Record<string, unknown> = {}) {
  wrapper = mount(Page, { attachTo: document.body, props, global: { plugins: [ElementPlus] } })
  await flushPromises()
}
const button = (name: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('button')].find(
    (v) => v.textContent?.trim() === name,
  )!
async function click(name: string) {
  expect(button(name), name).toBeTruthy()
  button(name).click()
  await flushPromises()
}
async function input(index: number, value: string) {
  wrapper!.findAllComponents({ name: 'ElInput' })[index].vm.$emit('update:modelValue', value)
  await flushPromises()
}
it('原monitor.read门禁：launch.read不能借用，超级通配符能读', async () => {
  state.user.permissions = ['launch.read']
  await start()
  expect(api.list).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('缺少monitor.read')
  expect(button('查询指标配置').disabled).toBe(true)
  state.user.permissions = ['*:*:*']
  await flushPromises()
  expect(api.list).toHaveBeenCalledTimes(1)
})
it('初始仅真实GET首50、原scope/time元数据、无创建编辑执行按钮', async () => {
  await start()
  expect(api.list).toHaveBeenCalledWith(
    { q: '', metric_profile_id: null, cursor: null, page_size: 50 },
    expect.any(AbortSignal),
  )
  expect(document.body.textContent).toContain('当前返回1项')
  expect(document.body.textContent).toContain('权限版本7')
  expect(document.body.textContent).toContain('2026-11-08T00:00:00Z')
  for (const name of ['创建', '编辑', '执行', '发布'])
    expect(
      [...document.querySelectorAll('button')].some((v) => v.textContent?.trim() === name),
    ).toBe(false)
})
it('全部12字段详情展示null、数组、false和原值，FIXTURE不标平台已验证', async () => {
  await start()
  await click('查看全部字段')
  const text = document.body.textContent!
  for (const value of [
    'register_action_type',
    'purchase_action_type',
    'value_action_type',
    'attribution_windows',
    'action_report_time',
    'timezone_policy',
    'breakdown',
    'maturity_days',
    'verified',
    'version',
    'source',
    '7d_click',
    '1d_view',
    'ACCOUNT_LOCAL',
    'TOTAL',
    'false（否）',
    '未知（null',
    'FIXTURE测试配置',
  ])
    expect(text).toContain(value)
  expect(text).not.toContain('owner_user_id')
  await click('关闭详情')
  expect(wrapper!.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
})
it('META真实verified=true仍明确不替代当前执行授权', async () => {
  vi.mocked(api.list).mockResolvedValue({
    ...page(),
    items: [{ ...profile(), source: 'META', verified: true }],
  })
  await start()
  await click('查看全部字段')
  expect(document.body.textContent).toContain('true（是）')
  expect(document.body.textContent).toContain('不代替当前账户、能力、政策及执行授权核验')
})
it('短页保留next，三页前后历史用原cursor、不生成offset', async () => {
  vi.mocked(api.list)
    .mockResolvedValueOnce(page(1, 'token2'))
    .mockResolvedValueOnce(page(2, 'token3'))
    .mockResolvedValueOnce(page(3, null))
    .mockResolvedValueOnce(page(2, 'token3'))
    .mockResolvedValueOnce(page(1, 'token2'))
  await start()
  expect(button('下一页').disabled).toBe(false)
  await click('下一页')
  await click('下一页')
  expect(button('下一页').disabled).toBe(true)
  await click('上一页')
  await click('上一页')
  expect(vi.mocked(api.list).mock.calls.map((x) => x[0].cursor)).toEqual([
    null,
    'token2',
    'token3',
    'token2',
    null,
  ])
  expect(button('上一页').disabled).toBe(true)
})
it('四档size均回首且不沿用旧游标', async () => {
  vi.mocked(api.list).mockImplementation(() => Promise.resolve(page(1, 'next')))
  await start()
  const size = wrapper!.findComponent({ name: 'ElSelect' })
  for (const value of [20, 100, 200, 50]) {
    await click('下一页')
    size.vm.$emit('update:modelValue', value)
    await flushPromises()
    expect(vi.mocked(api.list).mock.lastCall![0]).toMatchObject({ page_size: value, cursor: null })
    expect(button('上一页').disabled).toBe(true)
  }
})
it('ID筛选变更清页/详情、不偷发未定义filter，显式提交后取交集', async () => {
  vi.mocked(api.list).mockImplementation(() => Promise.resolve(page(1, 'next')))
  await start()
  await click('下一页')
  await click('查看全部字段')
  await input(0, id(3))
  await input(1, id(4))
  expect(wrapper!.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
  expect(api.list).toHaveBeenCalledTimes(2)
  expect(button('下一页').disabled).toBe(true)
  await click('查询指标配置')
  expect(vi.mocked(api.list).mock.lastCall![0]).toEqual({
    q: id(3),
    metric_profile_id: id(4),
    page_size: 50,
    cursor: null,
  })
})
it.each([401, 403, 409, 503])('服务端%d清旧配置和详情，状态明确而非空列表成功', async (status) => {
  await start()
  await click('查看全部字段')
  vi.mocked(api.list).mockRejectedValue(new MetricProfileError(status, 'CHANGED', '受控错误'))
  await click('重新读取首页')
  expect(wrapper!.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
  expect(wrapper!.findComponent({ name: 'ElTable' }).props('data')).toEqual([])
  expect(document.body.textContent).not.toContain('当前筛选没有指标配置')
  if (status === 503) expect(document.body.textContent).toContain('权威来源尚未就绪')
  if (status === 409) expect(document.body.textContent).toContain('旧游标已清除')
})
it('409重试从首页重新建立游标', async () => {
  vi.mocked(api.list)
    .mockResolvedValueOnce(page(1, 'next'))
    .mockRejectedValueOnce(new MetricProfileError(409, 'CHANGED', '变化'))
    .mockResolvedValueOnce(page(3))
  await start()
  await click('下一页')
  await click('重试上次读取')
  expect(vi.mocked(api.list).mock.calls.map((x) => x[0].cursor)).toEqual([null, 'next', null])
})
it('网络失败的明确重试保留原下一页请求，不能偷变条件或自动循环', async () => {
  vi.mocked(api.list)
    .mockResolvedValueOnce(page(1, 'next'))
    .mockRejectedValueOnce(new MetricProfileError(0, 'NETWORK', '网络中断'))
    .mockResolvedValueOnce(page(2))
  await start()
  await click('下一页')
  expect(api.list).toHaveBeenCalledTimes(2)
  await click('重试上次读取')
  expect(vi.mocked(api.list).mock.calls[2][0]).toEqual(vi.mocked(api.list).mock.calls[1][0])
  expect(document.body.textContent).toContain('第2页')
})
it('成功空页有独立空状态，不能伪造默认配置', async () => {
  vi.mocked(api.list).mockResolvedValue({ ...page(), items: [] })
  await start()
  expect(document.body.textContent).toContain('当前筛选没有指标配置')
  expect(button('下一页').disabled).toBe(true)
  expect(
    [...document.querySelectorAll('button')].some((v) => v.textContent?.trim() === '查看全部字段'),
  ).toBe(false)
})
it('读取中换条件abort，迟到旧响应不覆盖新筛选', async () => {
  let resolve!: (v: MetricProfilePage) => void
  vi.mocked(api.list).mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await start()
  const signal = vi.mocked(api.list).mock.calls[0][1]!
  await input(0, id(8))
  expect(signal.aborted).toBe(true)
  vi.mocked(api.list).mockResolvedValue(page(8))
  await click('查询指标配置')
  resolve(page(999))
  await flushPromises()
  expect(wrapper!.findComponent({ name: 'ElTable' }).props('data')).toEqual([profile(8)])
  expect(document.body.textContent).not.toContain(id(999))
})
it('撤权/换身份立清旧数据并关闭详情，不让旧成功返回；恢复按新context首读', async () => {
  await start({ contextKey: 'login-1' })
  await click('查看全部字段')
  state.user.permissions = []
  await flushPromises()
  expect(wrapper!.findComponent({ name: 'ElTable' }).props('data')).toEqual([])
  expect(wrapper!.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
  expect(api.list).toHaveBeenCalledTimes(1)
  state.user.permissions = ['monitor.read']
  state.user.id = '2'
  await wrapper!.setProps({ contextKey: 'login-2' })
  await flushPromises()
  expect(vi.mocked(api.list).mock.lastCall![0].cursor).toBeNull()
  expect(api.list).toHaveBeenCalledTimes(2)
})
it('隐藏/卸载取消GET，后台不自动轮询或重试', async () => {
  let resolve!: (v: MetricProfilePage) => void
  vi.mocked(api.list).mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await start()
  const first = vi.mocked(api.list).mock.calls[0][1]!
  await wrapper!.setProps({ active: false })
  expect(first.aborted).toBe(true)
  resolve(page())
  await flushPromises()
  expect(wrapper!.findComponent({ name: 'ElTable' }).props('data')).toEqual([])
  await wrapper!.setProps({ active: true })
  await flushPromises()
  const second = vi.mocked(api.list).mock.calls[1][1]!
  wrapper!.unmount()
  wrapper = undefined
  expect(second.aborted).toBe(true)
  expect(api.list).toHaveBeenCalledTimes(2)
})
