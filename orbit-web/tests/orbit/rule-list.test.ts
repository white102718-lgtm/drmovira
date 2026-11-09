import { ruleRecoveryApi } from '@/api/orbit/rule-recovery'
vi.mock('@/api/orbit/rule-recovery', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rule-recovery')>()),
  ruleRecoveryApi: { get: vi.fn() },
}))
/** 原RuleList原生组件纯测：SDK替身仅核协议/交互，不计真实HTTP或浏览器验收。 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElDrawer, ElSelect } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ruleDisplayMetadataApi } from '@/api/orbit/rule-display-metadata'
vi.mock('@/api/orbit/rule-display-metadata', () => ({ ruleDisplayMetadataApi: { get: vi.fn() } }))
import List from '@/views/orbit/rules/RuleList.vue'
import { RuleApiError, rulesApi, type Rule, type RuleSimulation } from '@/api/orbit/rules'
vi.mock('@/api/orbit/rules', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rules')>()),
  rulesApi: {
    list: vi.fn(),
    get: vi.fn(),
    capabilities: vi.fn(),
    pause: vi.fn(),
    archive: vi.fn(),
    simulate: vi.fn(),
    enable: vi.fn(),
    runs: vi.fn(),
  },
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const row = (state: Rule['state'] = 'DRAFT'): Rule => ({
  id: id(),
  name: '原规则',
  revision: 1,
  state,
  next_run_at: null,
  ownership: { owner_user_id: id(2), owner_team_id: id(3) },
  target_level: 'AD',
  scope_snapshot_id: id(4),
  metric_profile_id: id(5),
  logic: 'AND',
  groups: [
    { logic: 'OR', conditions: [{ metric: 'spend', operator: 'GTE', threshold: '0.000001' }] },
  ],
  window: 'LAST_3D',
  schedule: {
    frequency: 'INTERVAL',
    interval_minutes: 30,
    time_of_day: null,
    weekday: null,
    timezone: 'America/New_York',
    start_date: '2026-01-01',
    end_date: '2026-12-31',
  },
  cooldown_minutes: 60,
  max_daily: 5,
})
const page = (items = [row()], next_cursor: string | null = null) => ({
  items,
  next_cursor,
  data_as_of: '2026-11-09T00:00:00.000Z',
  scope_version: 2,
})
const codes = [
  'rules.read',
  'rules.create',
  'rules.edit',
  'rules.pause',
  'rules.archive',
  'rules.enable',
]
let wrapper: VueWrapper
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 1,
    tenant_id: id(99),
    csrf_token: 'real-fixture-csrf-token',
  })
  vi.mocked(ruleDisplayMetadataApi.get).mockImplementation(async (ids) =>
    ids.map((rule_id) => ({
      rule_id,
      revision: 1,
      owner_user_name: '实际投放师',
      owner_team_name: '实际团队',
      created_by: 9,
      created_by_name: '实际创建人',
      created_at: '2026-11-09T01:00:00.123Z',
    })),
  )
  vi.mocked(rulesApi.list).mockResolvedValue(page())
  vi.mocked(rulesApi.get).mockResolvedValue(row())
  vi.mocked(rulesApi.capabilities).mockResolvedValue({ csrf_token: 'real-fixture-csrf-token' })
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function render(props = {}) {
  wrapper = mount(List, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
    props: { nativeActorId: 1, permissionCodes: codes, contextKey: 'session-a', ...props },
  })
  await flushPromises()
  return wrapper
}
function button(label: string) {
  const button = wrapper.findAll('button').find((b) => b.text() === label)
  expect(button, label).toBeTruthy()
  return button!
}
async function open() {
  await button('详情').trigger('click')
  await flushPromises()
}
async function choose(label: string, value: unknown) {
  const select = wrapper.findAllComponents(ElSelect).find((s) => s.props('ariaLabel') === label)
  expect(select).toBeTruthy()
  select!.vm.$emit('update:modelValue', value)
  select!.vm.$emit('change', value)
  await flushPromises()
}
function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}
it('无read不请求列表或任何cap，create-only不暗加read', async () => {
  await render({ permissionCodes: ['rules.create'] })
  expect(rulesApi.list).not.toHaveBeenCalled()
  expect(rulesApi.capabilities).not.toHaveBeenCalled()
  await button('创建规则').trigger('click')
  await flushPromises()
  expect(rulesApi.capabilities).toHaveBeenCalledWith('CREATE', expect.any(AbortSignal))
  expect(wrapper.emitted('create')?.[0]).toEqual([{ csrf_token: 'real-fixture-csrf-token' }])
})
it('真实列表字段和四档cursor导航，filter/page变化重置', async () => {
  vi.mocked(rulesApi.list)
    .mockResolvedValueOnce(page([row()], 'next-page'))
    .mockResolvedValue(page())
  await render()
  expect(wrapper.text()).toContain('原规则')
  await button('下一页').trigger('click')
  await flushPromises()
  expect(rulesApi.list).toHaveBeenLastCalledWith(
    { page_size: 50, cursor: 'next-page' },
    expect.any(AbortSignal),
  )
  await button('上一页').trigger('click')
  await flushPromises()
  expect(rulesApi.list).toHaveBeenLastCalledWith({ page_size: 50 }, expect.any(AbortSignal))
  for (const size of [20, 100, 200, 50]) {
    await choose('每页条数', size)
    expect(rulesApi.list).toHaveBeenLastCalledWith({ page_size: size }, expect.any(AbortSignal))
  }
})
it('原筛选完整交SDK，503/422不伪空结果', async () => {
  const fail = new RuleApiError(422, 'FIELD_VALIDATION_FAILED', '日期语义尚未提供')
  vi.mocked(rulesApi.list).mockRejectedValue(fail)
  await render({ filters: { date_from: '2026-01-01', channel_id: 'META' } })
  expect(rulesApi.list).toHaveBeenCalledWith(
    { date_from: '2026-01-01', channel_id: 'META', page_size: 50 },
    expect.any(AbortSignal),
  )
  expect(wrapper.text()).toContain('FIELD_VALIDATION_FAILED')
})
it('15字段详情和完整调度/Decimal保真，编辑仅emit真实cap和rule', async () => {
  await render()
  await open()
  expect(wrapper.text()).toContain('America/New_York')
  expect(wrapper.text()).toContain('0.000001')
  expect(wrapper.text()).toContain(id(4))
  expect(wrapper.text()).toContain('不适用')
  await button('编辑规则').trigger('click')
  await flushPromises()
  expect(wrapper.emitted('edit')?.[0]).toEqual([row(), { csrf_token: 'real-fixture-csrf-token' }])
  expect(wrapper.findComponent(ElDrawer).props('modelValue')).toBe(false)
})
it('详情读取失败不沿用列表行冒充，late detail不可覆盖另一身份', async () => {
  const wait = deferred<Rule>()
  vi.mocked(rulesApi.get).mockReturnValue(wait.promise)
  await render()
  await open()
  await wrapper.setProps({ contextKey: 'session-b', permissionCodes: [] })
  wait.resolve(row())
  await flushPromises()
  expect(wrapper.text()).not.toContain('America/New_York')
  expect(wrapper.text()).toContain('缺少规则读取权限')
})
it('旧列表晚返回不可覆盖当前身份', async () => {
  const wait = deferred<ReturnType<typeof page>>()
  vi.mocked(rulesApi.list).mockReturnValueOnce(wait.promise)
  await render()
  await wrapper.setProps({ contextKey: 'b', permissionCodes: [] })
  wait.resolve(page())
  await flushPromises()
  expect(wrapper.text()).not.toContain('原规则')
})
it('启用态先暂停，不能编辑/归档；无真实模拟不能启用', async () => {
  vi.mocked(rulesApi.get).mockResolvedValue(row('ENABLED'))
  await render()
  await open()
  expect(button('编辑规则').attributes('disabled')).toBeDefined()
  expect(button('归档').attributes('disabled')).toBeDefined()
  expect(button('启用').attributes('disabled')).toBeDefined()
  expect(button('暂停').attributes('disabled')).toBeUndefined()
})
it('暂停原因/当前CAS与cap，取消无写，成功更新真实版本', async () => {
  vi.mocked(rulesApi.get).mockResolvedValue(row('ENABLED'))
  vi.mocked(rulesApi.pause).mockResolvedValue({ ...row('PAUSED'), revision: 2 })
  await render()
  await open()
  await button('暂停').trigger('click')
  await flushPromises()
  expect(button('确认').attributes('disabled')).toBeDefined()
  await button('取消').trigger('click')
  expect(rulesApi.pause).not.toHaveBeenCalled()
  await button('暂停').trigger('click')
  await flushPromises()
  await wrapper.get('textarea[aria-label="操作原因"]').setValue('安全暂停')
  await button('确认').trigger('click')
  await flushPromises()
  expect(rulesApi.pause).toHaveBeenCalledWith(
    id(),
    { reason: '安全暂停' },
    expect.objectContaining({
      if_match: '"1"',
      csrf_token: 'real-fixture-csrf-token',
      idempotency_key: expect.any(String),
    }),
    expect.any(AbortSignal),
  )
  expect(wrapper.text()).toContain('2 / 已暂停')
})
it('未知归档手动重试保存相同body/key/CAS，不二次cap不自动发送', async () => {
  vi.mocked(rulesApi.archive)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true))
    .mockResolvedValue({ ...row('ARCHIVED'), revision: 2 })
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('已结束')
  await button('确认').trigger('click')
  await flushPromises()
  const first = vi.mocked(rulesApi.archive).mock.calls[0]
  expect(button('取消').attributes('disabled')).toBeDefined()
  expect(rulesApi.archive).toHaveBeenCalledTimes(1)
  expect(button('使用原请求重试').attributes('disabled')).toBeUndefined()
  await button('使用原请求重试').trigger('click')
  await flushPromises()
  const second = vi.mocked(rulesApi.archive).mock.calls[1]
  expect(second.slice(0, 3)).toEqual(first.slice(0, 3))
  expect(rulesApi.capabilities).toHaveBeenCalledTimes(1)
})
it('模拟实际503与运行记录503可见，不发行enable资格', async () => {
  vi.mocked(rulesApi.simulate).mockRejectedValue(
    new RuleApiError(503, 'SIMULATION_UNAVAILABLE', '缺少模拟来源'),
  )
  vi.mocked(rulesApi.runs).mockRejectedValue(
    new RuleApiError(503, 'RUNS_UNAVAILABLE', '运行来源未就绪'),
  )
  await render()
  await open()
  await button('模拟').trigger('click')
  await flushPromises()
  await button('确认').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('SIMULATION_UNAVAILABLE')
  expect(button('启用').attributes('disabled')).toBeDefined()
  await button('取消').trigger('click')
  await button('运行记录').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('RUNS_UNAVAILABLE')
  expect(wrapper.text()).not.toContain('当前页无运行记录')
})
it('只使用原Simulation13 expires_at与当前版本，无添加created_at；真实enable body', async () => {
  const sim: RuleSimulation = {
    id: id(20),
    rule_id: id(),
    revision: 1,
    snapshot_id: id(21),
    hash: 'a'.repeat(64),
    account_count: 1,
    scanned_count: 2,
    hit_count: 1,
    unknown_count: 1,
    false_count: 0,
    conditions: [
      {
        entity_id: id(22),
        condition_index: 0,
        value: null,
        result: 'UNKNOWN',
        reason_code: 'MISSING',
      },
    ],
    expires_at: '2099-01-01T00:00:00.000Z',
    next_cursor: 'more',
  }
  vi.mocked(rulesApi.simulate).mockResolvedValue(sim)
  vi.mocked(rulesApi.enable).mockResolvedValue({ ...row('ENABLED'), revision: 2 })
  await render()
  await open()
  await button('模拟').trigger('click')
  await flushPromises()
  await button('确认').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('当前结果不代表完整明细')
  expect(button('启用').attributes('disabled')).toBeUndefined()
  await button('启用').trigger('click')
  await flushPromises()
  await button('确认').trigger('click')
  await flushPromises()
  expect(rulesApi.enable).toHaveBeenCalledWith(
    id(),
    { simulation_id: id(20) },
    expect.objectContaining({ if_match: '"1"' }),
    expect.any(AbortSignal),
  )
})
it('原动作cap拒绝可见且不发写入，缺动作不探测cap', async () => {
  vi.mocked(rulesApi.capabilities).mockRejectedValue(
    new RuleApiError(403, 'FORBIDDEN', '动作已撤回'),
  )
  await render({ permissionCodes: ['rules.read', 'rules.archive'] })
  await open()
  expect(wrapper.findAll('button').some((b) => b.text() === '暂停')).toBe(false)
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('结束')
  await button('确认').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('FORBIDDEN')
  expect(rulesApi.archive).not.toHaveBeenCalled()
})
it('编辑未提交的名称后翻页仍沿已提交筛选，不污染cursor', async () => {
  vi.mocked(rulesApi.list).mockResolvedValue(page([row()], 'next-page'))
  await render()
  await wrapper.get('input[aria-label="规则名称"]').setValue('尚未提交')
  await button('下一页').trigger('click')
  await flushPromises()
  expect(rulesApi.list).toHaveBeenLastCalledWith(
    { page_size: 50, cursor: 'next-page' },
    expect.any(AbortSignal),
  )
  await button('查询').trigger('click')
  await flushPromises()
  expect(rulesApi.list).toHaveBeenLastCalledWith(
    { q: '尚未提交', page_size: 50 },
    expect.any(AbortSignal),
  )
})
it('未知意图认证变化后不显示旧对象，恢复原上下文用同键重试', async () => {
  vi.mocked(rulesApi.archive)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true))
    .mockResolvedValue({ ...row('ARCHIVED'), revision: 2 })
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('结束')
  await button('确认').trigger('click')
  await flushPromises()
  const original = vi.mocked(rulesApi.archive).mock.calls[0]
  await wrapper.setProps({ contextKey: 'other', permissionCodes: [] })
  await flushPromises()
  expect(wrapper.text()).toContain('恢复原认证上下文')
  expect(document.querySelector('.el-dialog')?.textContent ?? '').not.toContain('原规则')
  expect(rulesApi.archive).toHaveBeenCalledTimes(1)
  await wrapper.setProps({ contextKey: 'session-a', permissionCodes: codes })
  await flushPromises()
  await button('使用原请求重试').trigger('click')
  await flushPromises()
  expect(vi.mocked(rulesApi.archive).mock.calls[1].slice(0, 3)).toEqual(original.slice(0, 3))
})
it('错误模拟对象不能生成启用资格，归类未知保留原key', async () => {
  vi.mocked(rulesApi.simulate).mockResolvedValue({
    id: id(20),
    rule_id: id(99),
    revision: 1,
    snapshot_id: id(21),
    hash: 'a'.repeat(64),
    account_count: 0,
    scanned_count: 0,
    hit_count: 0,
    unknown_count: 0,
    false_count: 0,
    conditions: [],
    expires_at: '2099-01-01T00:00:00Z',
    next_cursor: null,
  })
  await render()
  await open()
  await button('模拟').trigger('click')
  await flushPromises()
  await button('确认').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('INVALID_RESPONSE')
  expect(button('启用').attributes('disabled')).toBeDefined()
  expect(button('使用原请求重试')).toBeTruthy()
})
it('真实已过期模拟不默认有效，不能发送enable', async () => {
  vi.mocked(rulesApi.simulate).mockResolvedValue({
    id: id(20),
    rule_id: id(),
    revision: 1,
    snapshot_id: id(21),
    hash: 'a'.repeat(64),
    account_count: 0,
    scanned_count: 0,
    hit_count: 0,
    unknown_count: 0,
    false_count: 0,
    conditions: [],
    expires_at: '2000-01-01T00:00:00Z',
    next_cursor: null,
  })
  await render()
  await open()
  await button('模拟').trigger('click')
  await flushPromises()
  await button('确认').trigger('click')
  await flushPromises()
  expect(button('启用').attributes('disabled')).toBeDefined()
  expect(rulesApi.enable).not.toHaveBeenCalled()
})
it('服务端原path字段错误可见，非unknown拒绝允许修改原因', async () => {
  vi.mocked(rulesApi.archive).mockRejectedValue(
    new RuleApiError(422, 'FIELD_VALIDATION_FAILED', '字段错误', [
      { path: '/reason', code: 'TOO_LONG', message: '原因过长', constraint: null },
    ]),
  )
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('测试原因')
  await button('确认').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('/reason: 原因过长')
  expect(wrapper.get('textarea').attributes('disabled')).toBeUndefined()
  expect(button('取消').attributes('disabled')).toBeUndefined()
})
it('创建cap晚回不向新身份emit，不添加虚构创建人时间', async () => {
  const wait = deferred<{ csrf_token: string }>()
  vi.mocked(rulesApi.capabilities).mockReturnValue(wait.promise)
  await render()
  expect(wrapper.text()).toContain('实际创建人')
  expect(wrapper.text()).toContain('2026-11-09T01:00:00.123Z')
  await button('创建规则').trigger('click')
  await wrapper.setProps({ contextKey: 'other', permissionCodes: [] })
  wait.resolve({ csrf_token: 'stale-cap' })
  await flushPromises()
  expect(wrapper.emitted('create')).toBeUndefined()
})
it('详情真实运行记录组件可翻页，关闭详情取消子组件读取', async () => {
  vi.mocked(rulesApi.runs)
    .mockResolvedValueOnce({
      items: [
        {
          id: id(30),
          rule_id: id(),
          rule_revision: 1,
          schedule_slot: '2026-11-09T00:00:00Z',
          snapshot_id: id(31),
          state: 'FAILED',
          hit_count: 0,
          reason_code: 'REAL-FIRST',
        },
      ],
      next_cursor: 'actual-next',
      data_as_of: '2026-11-09T00:00:01Z',
      scope_version: 2,
    })
    .mockResolvedValue({
      items: [],
      next_cursor: null,
      data_as_of: '2026-11-09T00:00:01Z',
      scope_version: 2,
    })
  await render()
  await open()
  await button('运行记录').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('REAL-FIRST')
  await button('下一页记录').trigger('click')
  await flushPromises()
  expect(rulesApi.runs).toHaveBeenLastCalledWith(
    id(),
    { page_size: 50, cursor: 'actual-next' },
    expect.any(AbortSignal),
  )
  expect(wrapper.text()).toContain('当前页无运行记录')
  const lastSignal = vi.mocked(rulesApi.runs).mock.calls.at(-1)![2]!
  wrapper.findComponent(ElDrawer).vm.$emit('close')
  await flushPromises()
  expect(lastSignal.aborted).toBe(true)
  expect(wrapper.find('section[aria-label="规则运行记录"]').exists()).toBe(false)
})

it('父显式refresh回首屏但保留appliedQuery与未提交筛选输入', async () => {
  vi.mocked(rulesApi.list).mockResolvedValue(page([row()], 'next-page'))
  await render()
  await wrapper.find('input[aria-label="规则名称"]').setValue('已提交')
  await button('查询').trigger('click')
  await flushPromises()
  await button('下一页').trigger('click')
  await flushPromises()
  expect(rulesApi.list).toHaveBeenLastCalledWith(
    { page_size: 50, q: '已提交', cursor: 'next-page' },
    expect.any(AbortSignal),
  )
  await wrapper.find('input[aria-label="规则名称"]').setValue('尚未提交')
  await (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh()
  await flushPromises()
  expect(rulesApi.list).toHaveBeenLastCalledWith(
    { page_size: 50, q: '已提交' },
    expect.any(AbortSignal),
  )
  expect(wrapper.find('input[aria-label="规则名称"]').element).toHaveProperty('value', '尚未提交')
  expect(button('上一页').attributes('disabled')).toBeDefined()
})

it.each([401, 403])('原列表读取%d立即清旧详情和敏感对象，不依赖props刷新', async (status) => {
  await render()
  await open()
  expect(document.body.textContent).toContain('账户范围快照')
  vi.mocked(rulesApi.list).mockRejectedValueOnce(
    new RuleApiError(status, 'READ_REVOKED', '当前读取已撤回'),
  )
  await button('查询').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('READ_REVOKED')
  expect(wrapper.findComponent(ElDrawer).props('modelValue')).toBe(false)
  expect(wrapper.findComponent(ElDrawer).text()).not.toContain('账户范围快照')
  expect(wrapper.findAll('button').some((b) => b.text() === '详情')).toBe(false)
  expect(rulesApi.archive).not.toHaveBeenCalled()
})
it('明确读撤权保留未知归档原key/CAS/body，但不外显旧对象名和原因', async () => {
  vi.mocked(rulesApi.archive)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_ERROR', '结果未知', [], true, null, true))
    .mockResolvedValueOnce({ ...row('ARCHIVED'), revision: 2 })
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('原私有原因')
  await button('确认').trigger('click')
  await flushPromises()
  const first = vi.mocked(rulesApi.archive).mock.calls[0]
  vi.mocked(rulesApi.list).mockRejectedValueOnce(
    new RuleApiError(403, 'READ_REVOKED', '读取已撤回'),
  )
  await button('查询').trigger('click')
  await flushPromises()
  expect(wrapper.text()).not.toContain('原规则')
  expect(wrapper.find('textarea').exists()).toBe(false)
  expect(wrapper.text()).toContain('旧对象内容已隐藏')
  await button('使用原请求重试').trigger('click')
  await flushPromises()
  const second = vi.mocked(rulesApi.archive).mock.calls[1]
  expect(second.slice(0, 3)).toEqual(first.slice(0, 3))
})
it.each([409, 503])('列表%d不冒撤权收走详情，运行记录入口不冒全局触发记录', async (status) => {
  await render()
  await open()
  expect(button('运行记录')).toBeTruthy()
  expect(wrapper.findAll('button').some((b) => b.text() === '触发记录')).toBe(false)
  vi.mocked(rulesApi.list).mockRejectedValueOnce(
    new RuleApiError(status, 'SOURCE_UNAVAILABLE', '稍后重试'),
  )
  await button('查询').trigger('click')
  await flushPromises()
  expect(wrapper.findComponent(ElDrawer).props('modelValue')).toBe(true)
  expect(wrapper.findComponent(ElDrawer).text()).toContain('账户范围快照')
})

it.each([401, 403])('原详情读取%d拒绝后清列表旧对象，不保留详情入口', async (status) => {
  await render()
  vi.mocked(rulesApi.get).mockRejectedValueOnce(
    new RuleApiError(status, 'READ_REVOKED', '读取已撤回'),
  )
  await open()
  expect(wrapper.text()).toContain('READ_REVOKED')
  expect(wrapper.findComponent(ElDrawer).props('modelValue')).toBe(false)
  expect(wrapper.findAll('button').some((b) => b.text() === '详情')).toBe(false)
  expect(rulesApi.capabilities).not.toHaveBeenCalled()
})

it('第二页归档成功先清父ACTION，再回已提交筛选首屏不重用旧cursor', async () => {
  vi.mocked(rulesApi.list)
    .mockResolvedValueOnce(page([row()], 'old-cursor'))
    .mockResolvedValue(page())
  vi.mocked(rulesApi.archive).mockResolvedValue({ ...row('ARCHIVED'), revision: 2 })
  await render()
  await wrapper.find('input[aria-label="规则名称"]').setValue('已提交')
  await button('查询').trigger('click')
  await flushPromises()
  vi.mocked(rulesApi.list).mockResolvedValueOnce(page([row()], 'old-cursor'))
  await (wrapper.vm as any).refresh()
  await flushPromises()
  await button('下一页').trigger('click')
  await flushPromises()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('真实结束')
  await button('确认').trigger('click')
  await flushPromises()
  expect(vi.mocked(rulesApi.list).mock.calls.at(-1)![0]).toEqual({ q: '已提交', page_size: 50 })
  expect(wrapper.emitted('pendingAction')!.at(-1)).toEqual([null])
})
it.each([403, 409])('未知动作恢复%d保持原意图，再次手动恢复仍同key/body/CAS', async (status) => {
  vi.mocked(rulesApi.archive)
    .mockRejectedValueOnce(new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true))
    .mockRejectedValueOnce(new RuleApiError(status, 'CURRENT_REJECTED', '本次拒绝'))
    .mockResolvedValueOnce({ ...row('ARCHIVED'), revision: 2 })
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('原始原因')
  await button('确认').trigger('click')
  await flushPromises()
  const first = vi.mocked(rulesApi.archive).mock.calls[0]
  await button('使用原请求重试').trigger('click')
  await flushPromises()
  expect(wrapper.emitted('pendingAction')!.at(-1)![0]).not.toBeNull()
  await button('使用原请求重试').trigger('click')
  await flushPromises()
  expect(vi.mocked(rulesApi.archive).mock.calls[2].slice(0, 3)).toEqual(first.slice(0, 3))
  expect(wrapper.emitted('pendingAction')!.at(-1)).toEqual([null])
})
it('父ACTION接管后真正卸载重挂载可恢复，未发确认不产生pending', async () => {
  vi.mocked(rulesApi.archive).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true),
  )
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  expect(wrapper.emitted('pendingAction')).toBeUndefined()
  await wrapper.get('textarea').setValue('原始原因')
  await button('确认').trigger('click')
  await flushPromises()
  const record = wrapper.emitted('pendingAction')!.at(-1)![0]
  const first = vi.mocked(rulesApi.archive).mock.calls[0]
  wrapper.unmount()
  vi.mocked(rulesApi.archive).mockResolvedValueOnce({ ...row('ARCHIVED'), revision: 2 })
  await render({ pendingAction: record })
  expect(rulesApi.archive).toHaveBeenCalledTimes(1)
  expect(button('使用原请求重试').attributes('disabled')).toBeUndefined()
  await button('使用原请求重试').trigger('click')
  await flushPromises()
  expect(vi.mocked(rulesApi.archive).mock.calls[1].slice(0, 3)).toEqual(first.slice(0, 3))
})

it('实际200行只批量一次metadata，Drawer另单户读并显示真实名/原native创建人与UTC', async () => {
  const items = Array.from({ length: 200 }, (_, n) => ({ ...row(), id: id(n + 100) }))
  vi.mocked(rulesApi.list).mockResolvedValue(page(items))
  vi.mocked(rulesApi.get).mockResolvedValue(items[0])
  await render()
  expect(ruleDisplayMetadataApi.get).toHaveBeenCalledTimes(1)
  expect(vi.mocked(ruleDisplayMetadataApi.get).mock.calls[0][0]).toEqual(items.map((r) => r.id))
  expect(wrapper.text()).toContain('实际投放师')
  expect(wrapper.text()).toContain('实际创建人')
  expect(wrapper.text()).toContain('2026-11-09T01:00:00.123Z')
  await open()
  expect(vi.mocked(ruleDisplayMetadataApi.get).mock.calls[1][0]).toEqual([items[0].id])
  expect(wrapper.findComponent(ElDrawer).text()).toContain('实际团队')
  expect(wrapper.findComponent(ElDrawer).text()).toContain('用户ID 9')
})
it('metadata加载/真实null姓名/503读取失败分别显示，不伪造当前用户或接口未提供', async () => {
  const d = deferred<any>()
  vi.mocked(ruleDisplayMetadataApi.get).mockReturnValueOnce(d.promise)
  await render()
  expect(wrapper.text()).toContain('正在读取创建人与归属资料')
  d.resolve([
    {
      rule_id: id(),
      revision: 1,
      owner_user_name: null,
      owner_team_name: null,
      created_by: 11,
      created_by_name: null,
      created_at: '2026-11-09T01:00:00.123Z',
    },
  ])
  await flushPromises()
  expect(wrapper.text()).toContain('未记录投放师姓名')
  expect(wrapper.text()).toContain('未记录创建人姓名')
  expect(wrapper.text()).toContain('用户ID 11')
  vi.mocked(ruleDisplayMetadataApi.get).mockRejectedValueOnce(
    new RuleApiError(503, 'RULE_DISPLAY_METADATA_UNAVAILABLE', '来源读取失败'),
  )
  await button('查询').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('显示资料读取失败')
  expect(wrapper.text()).toContain('RULE_DISPLAY_METADATA_UNAVAILABLE')
  expect(wrapper.text()).not.toContain('原接口尚未提供')
})
it('metadata revision与原Rule不匹配提示刷新，不能沿旧详情发编辑/暂停/归档', async () => {
  await render()
  vi.mocked(ruleDisplayMetadataApi.get).mockResolvedValueOnce([
    {
      rule_id: id(),
      revision: 2,
      owner_user_name: '新版姓名',
      owner_team_name: null,
      created_by: 11,
      created_by_name: null,
      created_at: '2026-11-09T01:00:00.123Z',
    },
  ])
  await open()
  expect(wrapper.text()).toContain('RULE_DISPLAY_METADATA_CHANGED')
  expect(button('编辑规则').attributes('disabled')).toBeDefined()
  expect(button('归档').attributes('disabled')).toBeDefined()
  expect(rulesApi.archive).not.toHaveBeenCalled()
  expect(rulesApi.capabilities).not.toHaveBeenCalled()
})
it.each([401, 403, 404])('metadata%d整批不再可见即清页与旧Drawer，不泄漏部分名', async (status) => {
  await render()
  await open()
  vi.mocked(ruleDisplayMetadataApi.get).mockRejectedValueOnce(
    new RuleApiError(status, 'NOT_VISIBLE', '当前规则资料不可读'),
  )
  await button('查询').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('NOT_VISIBLE')
  expect(wrapper.text()).not.toContain('实际投放师')
  expect(wrapper.findComponent(ElDrawer).props('modelValue')).toBe(false)
})
it('metadata独立epoch取消旧页，迟到名不能污染新页', async () => {
  const d = deferred<any>()
  vi.mocked(ruleDisplayMetadataApi.get).mockReturnValueOnce(d.promise)
  await render()
  const oldSignal = vi.mocked(ruleDisplayMetadataApi.get).mock.calls[0][1]!
  vi.mocked(rulesApi.list).mockResolvedValue(page([{ ...row(), id: id(90) }]))
  await button('查询').trigger('click')
  await flushPromises()
  expect(oldSignal.aborted).toBe(true)
  d.resolve([
    {
      rule_id: id(),
      revision: 1,
      owner_user_name: '不应出现的旧名',
      owner_team_name: null,
      created_by: 11,
      created_by_name: null,
      created_at: '2026-11-09T01:00:00.123Z',
    },
  ])
  await flushPromises()
  expect(wrapper.text()).not.toContain('不应出现的旧名')
  expect(wrapper.text()).toContain('实际投放师')
})

it('已发ACTION恢复仅原archive动作，不借rules.read重读或外显旧原因', async () => {
  const record = {
    principal: { actor_id: 1, tenant_id: id(99) },
    action: 'ARCHIVE',
    context: 'session-a',
    rule: row(),
    body: { reason: '私有原因' },
    auth: {
      csrf_token: 'real-fixture-csrf-token',
      idempotency_key: 'original-key',
      if_match: '"1"',
    },
  }
  vi.mocked(rulesApi.archive).mockResolvedValue({ ...row('ARCHIVED'), revision: 2 })
  await render({ permissionCodes: ['rules.archive'], pendingAction: record })
  expect(rulesApi.list).not.toHaveBeenCalled()
  expect(rulesApi.get).not.toHaveBeenCalled()
  expect(wrapper.text()).not.toContain('原规则')
  expect(wrapper.find('textarea').exists()).toBe(false)
  expect(button('使用原请求重试').attributes('disabled')).toBeUndefined()
  await button('使用原请求重试').trigger('click')
  await flushPromises()
  expect(rulesApi.archive).toHaveBeenCalledWith(
    id(),
    record.body,
    record.auth,
    expect.any(AbortSignal),
  )
  expect(ruleDisplayMetadataApi.get).not.toHaveBeenCalled()
})

it('首次ACTION实际actor不匹配不发POST或pending并隐藏旧详情', async () => {
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('原原因')
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 2,
    tenant_id: id(99),
    csrf_token: 'different-actor-csrf-token',
  })
  await button('确认').trigger('click')
  await flushPromises()
  expect(rulesApi.archive).not.toHaveBeenCalled()
  expect(wrapper.emitted('pendingAction')?.filter((x) => x[0]) ?? []).toEqual([])
  expect(wrapper.text()).not.toContain('实际投放师')
  expect(wrapper.findComponent(ElDrawer).props('modelValue')).toBe(false)
})
it('未知ACTION手动复核拒绝不同主体并保留原principal正文keyCAS', async () => {
  vi.mocked(rulesApi.archive).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true),
  )
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('原原因')
  await button('确认').trigger('click')
  await flushPromises()
  const old = wrapper.emitted('pendingAction')!.find((x) => x[0])![0]
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 2,
    tenant_id: id(99),
    csrf_token: 'different-actor-csrf-token',
  })
  await button('使用原请求重试').trigger('click')
  await flushPromises()
  expect(rulesApi.archive).toHaveBeenCalledTimes(1)
  expect(wrapper.emitted('pendingAction')!.at(-1)![0]).toEqual(old)
  expect(wrapper.text()).not.toContain('原原因')
  expect(wrapper.text()).toContain('RULE_RECOVERY_PRINCIPAL_CHANGED')
})

it('未知ACTION认证入口位于真实最上层Dialog内，复核事件不重发或改原请求', async () => {
  vi.mocked(rulesApi.archive).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true),
  )
  await render()
  await open()
  await button('归档').trigger('click')
  await flushPromises()
  await wrapper.get('textarea').setValue('原因')
  await button('确认').trigger('click')
  await flushPromises()
  const pending = wrapper.emitted('pendingAction')!.find((x) => x[0])![0]
  const modal = [...document.querySelectorAll<HTMLElement>('.el-dialog')].find((el) =>
    el.textContent?.includes('请求结果未知'),
  )!
  expect(modal).toBeTruthy()
  expect(modal.querySelector('a[href="/login"]')?.getAttribute('target')).toBe('_blank')
  expect(modal.querySelector('a')?.getAttribute('rel')).toBe('noopener')
  const verify = [...modal.querySelectorAll<HTMLButtonElement>('button')].find(
    (el) => el.textContent?.trim() === '重新验证当前身份（不提交）',
  )!
  verify.click()
  await flushPromises()
  expect(wrapper.emitted('verifyIdentity')).toHaveLength(1)
  expect(rulesApi.archive).toHaveBeenCalledTimes(1)
  expect(wrapper.emitted('pendingAction')!.at(-1)![0]).toEqual(pending)
  await wrapper.setProps({ recoveryMessage: '同主体已核验，尚未提交' })
  expect(modal.textContent).toContain('同主体已核验，尚未提交')
})

it.each([
  [{ ...row().schedule }, '每30分钟'],
  [
    {
      ...row().schedule,
      frequency: 'DAILY',
      interval_minutes: null,
      time_of_day: '09:35',
      weekday: null,
    },
    '每天 09:35（当地时间）',
  ],
  [
    {
      ...row().schedule,
      frequency: 'WEEKLY',
      interval_minutes: null,
      time_of_day: '23:45',
      weekday: 7,
    },
    '每周日 23:45（当地时间）',
  ],
] as const)('列表具体频次%s显示当前值与原IANA，不推算UTC', async (schedule, label) => {
  vi.mocked(rulesApi.list).mockResolvedValue(
    page([{ ...row(), schedule: schedule as Rule['schedule'] }]),
  )
  await render()
  expect(wrapper.text()).toContain(label)
  expect(wrapper.text()).toContain('America/New_York')
  expect(wrapper.text()).not.toContain('每天 null')
  expect(wrapper.text()).not.toContain('每null分钟')
})
it.each(['界'.repeat(100), '😀'.repeat(100), 'e\u0301'.repeat(100)])(
  '原NFC100码点完整发送，不受UTF16 maxlength截断',
  async (value) => {
    await render()
    const input = wrapper.get('input[aria-label="规则名称"]')
    expect(input.attributes('maxlength')).toBeUndefined()
    expect(input.attributes('aria-describedby')).toBe('rule-name-query-limit')
    await input.setValue(value)
    await button('查询').trigger('click')
    await flushPromises()
    expect(rulesApi.list).toHaveBeenLastCalledWith(
      { q: value.normalize('NFC'), page_size: 50 },
      expect.any(AbortSignal),
    )
    expect((input.element as HTMLInputElement).value).toBe(value)
  },
)
it('101码点本地拒绝不发HTTP、不改已提交q和cursor；清空按原空查询', async () => {
  vi.mocked(rulesApi.list).mockResolvedValue(page([row()], 'second-page'))
  await render()
  const input = wrapper.get('input[aria-label="规则名称"]')
  await input.setValue('既有条件')
  await button('查询').trigger('click')
  await flushPromises()
  const calls = vi.mocked(rulesApi.list).mock.calls.length
  for (const value of ['界'.repeat(101), '😀'.repeat(101), 'e\u0301'.repeat(101)]) {
    await input.setValue(value)
    await button('查询').trigger('click')
    await flushPromises()
    expect(rulesApi.list).toHaveBeenCalledTimes(calls)
    expect(wrapper.text()).toContain('最多100字符（/q）')
  }
  await button('下一页').trigger('click')
  await flushPromises()
  expect(rulesApi.list).toHaveBeenLastCalledWith(
    { q: '既有条件', page_size: 50, cursor: 'second-page' },
    expect.any(AbortSignal),
  )
  await input.setValue('')
  await button('查询').trigger('click')
  await flushPromises()
  expect(rulesApi.list).toHaveBeenLastCalledWith({ page_size: 50 }, expect.any(AbortSignal))
  expect(wrapper.text()).not.toContain('最多100字符（/q）')
})
