/** 原生ElementPlus表单纯挂载；不代表指标来源或HTTP验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Form from '@/views/orbit/monitor/MetricQueryForm.vue'
import {
  metricProfilesApi,
  MetricProfileError,
  type MetricProfile,
} from '@/api/orbit/metric-profiles'
let wrapper: VueWrapper | undefined
const profile: MetricProfile = {
  id: '00000000-0000-0000-0000-000000000001',
  version: 'observed-v001',
  source: 'FIXTURE',
  register_action_type: null,
  purchase_action_type: 'purchase',
  value_action_type: null,
  attribution_windows: ['original'],
  action_report_time: 'observed',
  timezone_policy: 'ACCOUNT_LOCAL',
  breakdown: 'TOTAL',
  maturity_days: 28,
  verified: true,
}
beforeEach(() => {
  vi.spyOn(metricProfilesApi, 'history').mockResolvedValue({
    items: [profile],
    next_cursor: null,
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 1,
  })
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start(props = {}) {
  wrapper = mount(Form, {
    props: { dataset: 'ACCOUNT', ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
}
async function fill() {
  await wrapper!.find('input[aria-label="开始业务日"]').setValue('2026-01-01')
  await wrapper!.find('input[aria-label="结束业务日"]').setValue('2026-01-02')
  await wrapper!.find('.el-select__wrapper').trigger('click')
  await flushPromises()
  const option = [...document.querySelectorAll<HTMLElement>('.el-select-dropdown__item')].find(
    (node) => node.textContent?.includes(profile.version),
  )!
  expect(option).toBeTruthy()
  option.click()
  await flushPromises()
}
it('13字段完整发出，原可选项为空时null，cursor仅父分页管理', async () => {
  await start()
  await fill()
  await wrapper!.find('form').trigger('submit')
  const value = wrapper!.emitted('query')![0][0] as Record<string, unknown>
  expect(Object.keys(value)).toHaveLength(13)
  expect(value).toMatchObject({
    dataset: 'ACCOUNT',
    scope_snapshot_id: null,
    channel_id: null,
    operator_user_id: null,
    cursor: null,
    page_size: 20,
    granularity: 'SUMMARY',
  })
  expect(wrapper!.text()).toContain('含首尾最多93天')
  expect(wrapper!.text()).toContain('账户当地')
})
it('未填写或日期非法不产生query，错误可读', async () => {
  await start()
  await wrapper!.find('form').trigger('submit')
  expect(wrapper!.emitted('query')).toBeUndefined()
  expect(wrapper!.find('[role=alert]').text()).toContain('日期范围')
  await fill()
  await wrapper!.find('input[aria-label="结束业务日"]').setValue('2026-04-04')
  await wrapper!.find('form').trigger('submit')
  expect(wrapper!.emitted('query')).toBeUndefined()
})
it('可选渠道/投手/范围完整不截断，清除恢复null', async () => {
  await start()
  await fill()
  const input = wrapper!.find('input[aria-label="渠道ID（可选）"]')
  await input.setValue('渠道😀'.repeat(20))
  await wrapper!.find('form').trigger('submit')
  expect((wrapper!.emitted('query')![0][0] as { channel_id: string }).channel_id).toBe(
    '渠道😀'.repeat(20),
  )
  await input.setValue('')
  await wrapper!.find('form').trigger('submit')
  expect((wrapper!.emitted('query')![1][0] as { channel_id: null }).channel_id).toBeNull()
})
it('真实disabled防发请求；context变化清空旧输入而dataset变化保留原筛选', async () => {
  await start()
  await fill()
  await wrapper!.setProps({ dataset: 'AD' })
  await wrapper!.find('form').trigger('submit')
  expect((wrapper!.emitted('query')![0][0] as { dataset: string }).dataset).toBe('AD')
  await wrapper!.setProps({ disabled: true })
  await wrapper!.find('form').trigger('submit')
  expect(wrapper!.emitted('query')).toHaveLength(1)
  await wrapper!.setProps({ disabled: false, contextKey: 'different_actor' })
  expect(wrapper!.findAllComponents({ name: 'ElSelect' })[0].props('modelValue')).toBe('')
})
it('选择真实目录版本/来源状态，无手填UUID；未指定scope明确全部可见账户', async () => {
  await start()
  await fill()
  expect(metricProfilesApi.history).toHaveBeenCalledWith(
    { q: '', metric_profile_id: null, cursor: null, page_size: 50 },
    expect.any(AbortSignal),
  )
  expect(wrapper!.text()).toContain('全部当前可见账户')
  expect(wrapper!.text()).toContain('隔离测试样本')
  expect(wrapper!.find('input[aria-label="指标配置UUID"]').exists()).toBe(false)
})
it('版本只筛已加载候选，完整ID才原远程精确q；下一页真实GET不拉全量', async () => {
  vi.mocked(metricProfilesApi.history).mockResolvedValue({
    items: [profile],
    next_cursor: 'opaque_next',
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 1,
  })
  await start()
  await fill()
  const select = wrapper!.findAllComponents({ name: 'ElSelect' })[0]
  const search = select.props('remoteMethod') as (value: string) => void
  const before = vi.mocked(metricProfilesApi.history).mock.calls.length
  search('observed-v001')
  await flushPromises()
  expect(metricProfilesApi.history).toHaveBeenCalledTimes(before)
  search(profile.id)
  await flushPromises()
  expect(metricProfilesApi.history).toHaveBeenLastCalledWith(
    { q: profile.id, metric_profile_id: null, cursor: null, page_size: 50 },
    expect.any(AbortSignal),
  )
  const next = wrapper!.findAll('button').find((button) => button.text() === '更多配置')!
  await next.trigger('click')
  await flushPromises()
  expect(metricProfilesApi.history).toHaveBeenLastCalledWith(
    { q: profile.id, metric_profile_id: null, cursor: 'opaque_next', page_size: 50 },
    expect.any(AbortSignal),
  )
})
it('目录403不伪空，context变化丢弃迟到候选并abort', async () => {
  vi.mocked(metricProfilesApi.history).mockRejectedValueOnce(
    new MetricProfileError(403, 'PERMISSION_DENIED', '当前无权'),
  )
  await start()
  await wrapper!.find('.el-select__wrapper').trigger('click')
  await flushPromises()
  expect(wrapper!.text()).toContain('当前无法读取指标配置')
  let resolve!: (value: unknown) => void
  vi.mocked(metricProfilesApi.history).mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await wrapper!
    .findAll('button')
    .find((button) => button.text() === '重新读取配置')!
    .trigger('click')
  await flushPromises()
  const signal = vi.mocked(metricProfilesApi.history).mock.calls.at(-1)![1]!
  vi.mocked(metricProfilesApi.history).mockResolvedValueOnce({
    items: [],
    next_cursor: null,
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 2,
  })
  await wrapper!.setProps({ contextKey: 'other_actor' })
  expect(signal.aborted).toBe(true)
  resolve({
    items: [profile],
    next_cursor: null,
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 1,
  })
  await flushPromises()
  expect(
    wrapper!
      .findAllComponents({ name: 'ElOption' })
      .some((option) => option.props('label')?.includes(profile.version)),
  ).toBe(false)
})

it('不同配置同版本来源状态时，选项与已选显示真实完整ID并保存准确配置', async () => {
  const second = { ...profile, id: '00000000-0000-0000-0000-000000000002' }
  vi.mocked(metricProfilesApi.history).mockResolvedValue({
    items: [profile, second],
    next_cursor: null,
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 1,
  })
  await start()
  await wrapper!.find('input[aria-label="开始业务日"]').setValue('2026-01-01')
  await wrapper!.find('input[aria-label="结束业务日"]').setValue('2026-01-02')
  await wrapper!.find('.el-select__wrapper').trigger('click')
  await flushPromises()
  const options = [...document.querySelectorAll<HTMLElement>('.el-select-dropdown__item')]
  for (const candidate of [profile, second]) {
    expect(options.filter((item) => item.textContent?.includes(candidate.id))).toHaveLength(1)
  }
  const target = options.find((item) => item.textContent?.includes(second.id))!
  target.click()
  await flushPromises()
  expect(
    wrapper!.findAll('.el-select__selected-item').some((item) => item.text().includes(second.id)),
  ).toBe(true)
  await wrapper!.find('form').trigger('submit')
  expect(wrapper!.emitted('query')![0][0]).toMatchObject({ metric_profile_id: second.id })
})

it('同一个指标ID的旧版本可独立选择并随查询发出', async () => {
  vi.mocked(metricProfilesApi.history).mockResolvedValue({
    items: [
      { ...profile, version: 'old.v1' },
      { ...profile, version: 'new.v2' },
    ],
    next_cursor: null,
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 1,
  })
  await start()
  await wrapper!.find('input[aria-label="开始业务日"]').setValue('2026-01-01')
  await wrapper!.find('input[aria-label="结束业务日"]').setValue('2026-01-02')
  await wrapper!.find('.el-select__wrapper').trigger('click')
  await flushPromises()
  const old = [...document.querySelectorAll<HTMLElement>('.el-select-dropdown__item')].find((n) =>
    n.textContent?.includes('old.v1'),
  )!
  old.click()
  await flushPromises()
  await wrapper!.find('form').trigger('submit')
  expect(wrapper!.emitted('query')![0][1]).toBe('old.v1')
  expect(
    (wrapper!.emitted('query')![0][0] as { metric_profile_id: string }).metric_profile_id,
  ).toBe(profile.id)
  expect(Object.keys(wrapper!.emitted('query')![0][0] as object)).toHaveLength(13)
})
