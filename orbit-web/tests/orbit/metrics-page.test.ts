/** 真实ElementPlus父状态机，API替身仅纯交互证据，不算后端联调。 */
import { reactive } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Page from '@/views/orbit/monitor/index.vue'
import Form from '@/views/orbit/monitor/MetricQueryForm.vue'
import { metricProfilesApi } from '@/api/orbit/metric-profiles'
import { metricsApi, MetricsError, type MetricQuery, type Metrics } from '@/api/orbit/metrics'
const state = vi.hoisted(() => ({
  user: { id: '1', roles: ['reader'], permissions: ['monitor.read'] },
  cookie: '',
}))
vi.mock('@/store/modules/user', () => ({ default: () => state.user }))
vi.mock('@/api/orbit/authentication', () => ({ cookieCsrf: () => state.cookie }))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
const id = '00000000-0000-0000-0000-000000000001',
  csrf = 'real_context_csrf_1234567'
const body: MetricQuery = {
  date_from: '2026-01-01',
  date_to: '2026-01-02',
  dataset: 'ACCOUNT',
  metric_profile_id: id,
  scope_snapshot_id: null,
  channel_id: null,
  operator_user_id: null,
  q: '',
  sort: 'spend',
  direction: 'DESC',
  cursor: null,
  page_size: 20,
  granularity: 'SUMMARY',
}
const page = (cursor: string | null = null, revision = 1): Metrics => ({
  items: [],
  next_cursor: cursor,
  scope_version: revision,
  snapshot_id: id,
  data_as_of: '2026-11-08T00:00:00Z',
  missing_count: 0,
  query_snapshot_id: id,
  totals: [],
})
let wrapper: VueWrapper | undefined
beforeEach(() => {
  state.user = reactive({ id: '1', roles: ['reader'], permissions: ['monitor.read'] })
  state.cookie = ''
  vi.spyOn(metricsApi, 'query').mockResolvedValue(page())
  vi.spyOn(metricsApi, 'capabilities').mockResolvedValue({ csrf_token: csrf })
  vi.spyOn(metricProfilesApi, 'list').mockResolvedValue({
    items: [],
    next_cursor: null,
    data_as_of: '2026-11-08T00:00:00Z',
    scope_version: 1,
  })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start(props = {}) {
  wrapper = mount(Page, {
    props: { csrfToken: csrf, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
}
async function tab(label = '广告账户') {
  const node = wrapper!.findAll('[role=tab]').find((t) => t.text() === label)!
  await node.trigger('click')
  await flushPromises()
}
async function submit(value = body) {
  wrapper!.findComponent(Form).vm.$emit('query', value)
  await flushPromises()
}
async function click(text: string) {
  const node = wrapper!.findAll('button').find((b) => b.text() === text)!
  expect(node, text).toBeTruthy()
  await node.trigger('click')
  await flushPromises()
}
it('保留原七Tab顺序，不自动POST/假卡/AI建议，默认依赖说明', async () => {
  await start()
  expect(wrapper!.findAll('[role=tab]').map((t) => t.text())).toEqual([
    '监测与规则优化',
    '投放师',
    '渠道',
    '广告账户',
    '广告系列',
    '广告组',
    '广告',
  ])
  expect(metricsApi.query).not.toHaveBeenCalled()
  expect(wrapper!.text()).toContain('暂无可用监测数据')
  await tab('渠道')
  expect(wrapper!.text()).toContain('此维度暂不可用')
  expect(wrapper!.text()).not.toContain('风险金额')
})
it('native缺CSRF零发送且monitor.read原门禁不借launch.read', async () => {
  await start({ csrfToken: '' })
  await tab()
  expect(metricsApi.capabilities).toHaveBeenCalledTimes(1)
  await submit()
  expect(metricsApi.query).toHaveBeenCalledTimes(1)
  expect(vi.mocked(metricsApi.query).mock.calls[0][1].csrf_token).toBe(csrf)
  state.user.permissions = ['launch.read']
  await flushPromises()
  expect(wrapper!.text()).toContain('没有查看广告投放数据的权限')
  await submit()
  expect(metricsApi.query).toHaveBeenCalledTimes(1)
})
it('成功短页nextcursor仍翻页，上一页使用冻结原条件而非页内计数', async () => {
  vi.mocked(metricsApi.query)
    .mockResolvedValueOnce(page('next_signed'))
    .mockResolvedValueOnce(page(null))
    .mockResolvedValueOnce(page('next_signed'))
  await start()
  await tab()
  await submit()
  expect(wrapper!.text()).toContain('第1页')
  await click('下一页')
  expect(metricsApi.query).toHaveBeenNthCalledWith(
    2,
    { ...body, cursor: 'next_signed' },
    expect.anything(),
    expect.any(AbortSignal),
  )
  expect(wrapper!.text()).toContain('第2页')
  await click('上一页')
  expect(metricsApi.query).toHaveBeenNthCalledWith(
    3,
    body,
    expect.anything(),
    expect.any(AbortSignal),
  )
  expect(wrapper!.text()).toContain('第1页')
  expect(vi.mocked(metricsApi.query).mock.calls[0][1].idempotency_key).not.toBe(
    vi.mocked(metricsApi.query).mock.calls[1][1].idempotency_key,
  )
})
it('503不是空数据，保留五字段和原意图同key显式重试', async () => {
  vi.mocked(metricsApi.query)
    .mockRejectedValueOnce(
      new MetricsError(
        503,
        'SOURCE_UNAVAILABLE',
        '真实来源未就绪',
        [
          {
            path: '/metric_profile_id',
            code: 'UNVERIFIED',
            message: '尚未登记',
            constraint: 'registered',
          },
        ],
        true,
        id,
        false,
        'server',
      ),
    )
    .mockResolvedValueOnce(page())
  await start()
  await tab()
  await submit()
  expect(wrapper!.text()).toContain('暂无可用数据')
  expect(wrapper!.text()).toContain('/metric_profile_id')
  expect(wrapper!.text()).toContain(id)
  expect(wrapper!.text()).not.toContain('当前筛选没有实体')
  await click('使用原查询重试')
  const calls = vi.mocked(metricsApi.query).mock.calls
  expect(calls[1][0]).toEqual(calls[0][0])
  expect(calls[1][1]).toEqual(calls[0][1])
})
it('未知网络结果锁编辑/离开须确认，同键重试不自动新意图', async () => {
  vi.mocked(metricsApi.query).mockRejectedValueOnce(
    new MetricsError(0, 'NETWORK_UNAVAILABLE', '结果未知', [], true, null, true),
  )
  vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
  await start()
  await tab()
  await submit()
  expect(wrapper!.findComponent(Form).props('disabled')).toBe(true)
  await tab('广告系列')
  expect(wrapper!.findComponent(Form).props('dataset')).toBe('ACCOUNT')
  await click('使用原查询重试')
  const calls = vi.mocked(metricsApi.query).mock.calls
  expect(calls[1][1]).toEqual(calls[0][1])
})
it('403清数据与恢复key，不将权限失败当作无结果', async () => {
  vi.mocked(metricsApi.query).mockRejectedValue(
    new MetricsError(403, 'PERMISSION_DENIED', '当前权限不足'),
  )
  await start()
  await tab()
  await submit()
  expect(wrapper!.text()).toContain('当前权限不足')
  expect(wrapper!.findAll('button').some((b) => b.text() === '使用原查询重试')).toBe(false)
  expect(wrapper!.text()).not.toContain('当前筛选没有实体')
})
it('actor/context变化中断旧网络，旧成功/失败不能污染新上下文', async () => {
  let resolve!: (value: Metrics) => void
  vi.mocked(metricsApi.query).mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await start()
  await tab()
  await submit()
  const signal = vi.mocked(metricsApi.query).mock.calls[0][2]!
  state.user.id = '2'
  await flushPromises()
  expect(signal.aborted).toBe(true)
  resolve(page(null, 999))
  await flushPromises()
  expect(wrapper!.text()).not.toContain('权限版本999')
  expect(wrapper!.findComponent(Form).props('disabled')).toBe(false)
})
it('换条件后重置历史和数据，关闭active也abort并清旧结果', async () => {
  await start()
  await tab()
  await submit()
  expect(wrapper!.text()).toContain('权限版本1')
  wrapper!.findComponent(Form).vm.$emit('changed')
  await flushPromises()
  expect(wrapper!.text()).not.toContain('权限版本1')
  await submit()
  await wrapper!.setProps({ active: false })
  expect(wrapper!.text()).not.toContain('权限版本1')
  expect(wrapper!.findComponent(Form).props('disabled')).toBe(true)
})
it('409明确提示原快照失效，确认后保留输入但重建首页意图', async () => {
  vi.mocked(metricsApi.query)
    .mockRejectedValueOnce(new MetricsError(409, 'SCOPE_CHANGED', '范围已变化'))
    .mockResolvedValueOnce(page())
  await start()
  await tab()
  await submit()
  expect(wrapper!.text()).toContain('数据范围已变化')
  await click('确认并重新查询')
  await submit()
  const calls = vi.mocked(metricsApi.query).mock.calls
  expect(calls[1][0].cursor).toBeNull()
  expect(calls[1][1].idempotency_key).not.toBe(calls[0][1].idempotency_key)
})
it('收到可信错误请求ID及字段code全部显示为纯文本', async () => {
  vi.mocked(metricsApi.query).mockRejectedValue(
    new MetricsError(
      422,
      'FIELD_INVALID',
      '<img src=x>',
      [{ path: '/q', code: 'MAX_LENGTH', message: '<b>错误</b>', constraint: '100码点' }],
      false,
      id,
      false,
      'server',
    ),
  )
  await start()
  await tab()
  await submit()
  expect(wrapper!.text()).toContain('MAX_LENGTH')
  expect(wrapper!.text()).toContain('<img src=x>')
  expect(wrapper!.find('img').exists()).toBe(false)
  expect(wrapper!.text()).toContain(id)
})
it('显式CSRF与cookie来源优先，不借其他菜单或重复取得上下文', async () => {
  state.cookie = 'cookie_context_csrf_12345'
  await start({ csrfToken: '' })
  await tab()
  await submit()
  expect(metricsApi.capabilities).not.toHaveBeenCalled()
  expect(vi.mocked(metricsApi.query).mock.calls[0][1].csrf_token).toBe(state.cookie)
  await wrapper!.setProps({ csrfToken: csrf })
  await submit()
  expect(vi.mocked(metricsApi.query).mock.calls[1][1].csrf_token).toBe(csrf)
})
it('上下文503可明确重试，403清数据禁查询，不转成空成功', async () => {
  vi.mocked(metricsApi.capabilities)
    .mockRejectedValueOnce(
      new MetricsError(503, 'SOURCE_UNAVAILABLE', '暂时无法准备查询', [], true, id),
    )
    .mockRejectedValueOnce(
      new MetricsError(403, 'PERMISSION_DENIED', '当前无法查询', [], false, id),
    )
  await start({ csrfToken: '' })
  await tab()
  expect(wrapper!.text()).toContain('暂时无法准备查询')
  await submit()
  expect(metricsApi.query).not.toHaveBeenCalled()
  await click('重新准备查询')
  expect(wrapper!.text()).toContain('当前无法查询')
  expect(wrapper!.findComponent(Form).props('disabled')).toBe(true)
  await submit()
  expect(metricsApi.query).not.toHaveBeenCalled()
})
it('上下文GET在身份变化后abort，旧CSRF不能覆盖新用户', async () => {
  let resolve!: (value: { csrf_token: string }) => void
  vi.mocked(metricsApi.capabilities)
    .mockImplementationOnce(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    .mockResolvedValueOnce({ csrf_token: 'new_actor_context_csrf_12345' })
  await start({ csrfToken: '' })
  const signal = vi.mocked(metricsApi.capabilities).mock.calls[0][0]!
  state.user.id = '2'
  await flushPromises()
  expect(signal.aborted).toBe(true)
  resolve({ csrf_token: 'old_actor_context_csrf_12345' })
  await flushPromises()
  await tab()
  await submit()
  expect(vi.mocked(metricsApi.query).mock.calls[0][1].csrf_token).toBe(
    'new_actor_context_csrf_12345',
  )
})
