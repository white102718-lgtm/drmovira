/** 原生ElementPlus表单状态纯测；不调用helper/HTTP，不等于页面联调或真实候选验收。 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { h } from 'vue'
import ElementPlus, { ElInputNumber, ElOption, ElSelect } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Form from '@/views/orbit/rules/RuleDefinitionForm.vue'
import type { RuleWrite } from '@/api/orbit/rules'

const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const owner = { id: id(), name: '真实投放师', team_id: id(2), team_name: '真实团队' }
const other = { id: id(9), name: '另一投放师', team_id: id(10), team_name: '另一团队' }
// label由父从真实原DTO派生，不要求持久MetricProfile.name字段。
const profile = { id: id(3), label: 'META已登记', version: 'v-real-01' }
const scope = {
  id: id(4),
  label: '已保存完整范围',
  count: 521,
  owner_user_id: owner.id,
  owner_team_id: owner.team_id,
}
const defaults = { timezone: 'America/New_York', start_date: '2024-01-01', end_date: '2024-12-31' }
const timezones = [{ value: defaults.timezone, label: '纽约 · IANA时区' }]
const value = (): RuleWrite => ({
  name: '原规则',
  ownership: { owner_user_id: owner.id, owner_team_id: owner.team_id },
  target_level: 'AD',
  scope_snapshot_id: scope.id,
  logic: 'AND',
  groups: [
    { logic: 'OR', conditions: [{ metric: 'spend', operator: 'GTE', threshold: '0.000001' }] },
  ],
  window: 'LAST_3D',
  metric_profile_id: profile.id,
  schedule: {
    frequency: 'INTERVAL',
    interval_minutes: 30,
    time_of_day: null,
    weekday: null,
    ...defaults,
  },
  cooldown_minutes: 60,
  max_daily: 5,
})
let wrapper: VueWrapper | undefined
const fetcher = vi.fn()
beforeEach(() => {
  vi.stubGlobal('fetch', fetcher)
  fetcher.mockReset()
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
async function render(props = {}, ready = true) {
  wrapper = mount(Form, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
    props: {
      ...(ready
        ? {
            modelValue: value(),
            ownerOptions: [owner, other],
            profileOptions: [profile],
            scope,
            timezones,
          }
        : {}),
      ...props,
    },
  })
  await flushPromises()
  return wrapper
}
function button(label: string) {
  const found = wrapper!.findAll('button').find((node) => node.text() === label)
  expect(found, label).toBeTruthy()
  return found!
}
async function select(label: string, selected: string | number) {
  const control = wrapper!
    .findAllComponents(ElSelect)
    .find((node) => node.props('ariaLabel') === label || node.attributes('aria-label') === label)
  expect(control, label).toBeTruthy()
  control!.vm.$emit('update:modelValue', selected)
  control!.vm.$emit('change', selected)
  await flushPromises()
}
async function submit() {
  await wrapper!.find('form').trigger('submit')
  await flushPromises()
}
function emitted(index = 0) {
  return wrapper!.emitted('submit')?.[index]?.[0] as RuleWrite | undefined
}

it('只有原明确非日期默认，不伪造日期/时区/UUID/账户数量，空候选不能提交', async () => {
  await render({}, false)
  expect(wrapper!.find('input[aria-label="规则名称"]').element).toHaveProperty('value', '新建规则')
  expect(wrapper!.find('input[aria-label="开始日期"]').element).toHaveProperty('value', '')
  expect(wrapper!.find('input[aria-label="截止日期"]').element).toHaveProperty('value', '')
  expect(wrapper!.find('input[aria-label="第1组第1条阈值"]').element).toHaveProperty('value', '')
  expect(wrapper!.text()).toContain('没有可用归属人员')
  expect(wrapper!.text()).toContain('没有可用指标配置')
  expect(wrapper!.text()).not.toContain('已冻结 0')
  expect(button('保存规则').attributes('disabled')).toBeDefined()
  await submit()
  expect(emitted()).toBeUndefined()
  expect(fetcher).not.toHaveBeenCalled()
})

it('父提供真实上下文后完整11/7字段提交，Decimal/null保持且不修改原对象', async () => {
  const original = value()
  await render({ modelValue: original })
  expect(wrapper!.text()).toContain('已冻结 521 个账户')
  expect(wrapper!.text()).toContain(profile.id)
  expect(wrapper!.text()).toContain('不换汇、不跨币求和')
  await wrapper!.find('input[aria-label="规则名称"]').setValue(' 编辑规则 ')
  await submit()
  expect(Object.keys(emitted()!)).toHaveLength(11)
  expect(Object.keys(emitted()!.schedule)).toHaveLength(7)
  expect(emitted()).toMatchObject({
    name: '编辑规则',
    scope_snapshot_id: scope.id,
    schedule: { time_of_day: null, weekday: null },
    groups: [{ conditions: [{ threshold: '0.000001' }] }],
  })
  expect(original.name).toBe('原规则')
  expect(fetcher).not.toHaveBeenCalled()
})

it('编辑可复用父传已保存上下文，不用UUID造候选或借原snapshot creator身份', async () => {
  await render({ ownerOptions: [], profileOptions: [], savedContext: { owner, profile } })
  await submit()
  expect(emitted()?.scope_snapshot_id).toBe(scope.id)
  await wrapper!.setProps({ savedContext: null })
  expect(button('保存规则').attributes('disabled')).toBeDefined()
  await submit()
  expect(wrapper!.emitted('submit')).toHaveLength(1)
})

it('换owner只能取真实候选团队且旧scope立即失效，父重验新scope后才可保存', async () => {
  await render()
  await select('所属投放师', other.id)
  expect(wrapper!.find('input[aria-label="所属团队"]').element).toHaveProperty(
    'value',
    other.team_name,
  )
  expect(wrapper!.find('input[aria-label="所属团队"]').attributes('readonly')).toBeDefined()
  expect(wrapper!.emitted('ownership-change')![0][0]).toEqual({
    owner_user_id: other.id,
    owner_team_id: other.team_id,
  })
  expect(button('保存规则').attributes('disabled')).toBeDefined()
  await wrapper!.setProps({
    scope: { ...scope, id: id(12), owner_user_id: other.id, owner_team_id: other.team_id },
  })
  await submit()
  expect(emitted()!.ownership.owner_team_id).toBe(other.team_id)
  expect(emitted()!.scope_snapshot_id).toBe(id(12))
})

it.each([null, 0, 50001])('父范围数量%s不能当完整可保存范围，缺字段不补0', async (count) => {
  await render({ scope: { ...scope, count } })
  expect(button('保存规则').attributes('disabled')).toBeDefined()
  await submit()
  expect(emitted()).toBeUndefined()
})

it('50000完整成员和真实picker事件保留，组件不自行网络查询', async () => {
  await render({ scope: { ...scope, count: 50000 } })
  await button('选择账户范围').trigger('click')
  expect(wrapper!.emitted('choose-scope')![0][0]).toEqual(value().ownership)
  await submit()
  expect(emitted()).toBeTruthy()
  expect(wrapper!.text()).toContain('50000 个账户')
  expect(fetcher).not.toHaveBeenCalled()
})

it('父撤候选/加载/来源错误后不可提交，不能沿旧有效状态继续保存', async () => {
  await render({ profilesLoading: true })
  expect(button('保存规则').attributes('disabled')).toBeDefined()
  await wrapper!.setProps({ profilesLoading: false, profilesError: '配置已撤回' })
  expect(wrapper!.text()).toContain('配置已撤回')
  await submit()
  expect(emitted()).toBeUndefined()
  await wrapper!.setProps({ profilesError: '', profileOptions: [{ ...profile, available: false }] })
  expect(button('保存规则').attributes('disabled')).toBeDefined()
  await wrapper!.setProps({ profileOptions: [profile], timezones: [] })
  expect(button('保存规则').attributes('disabled')).toBeDefined()
})

it('三种频率切换清空所有互斥字段，默认星期从1开始且Schedule七键齐全', async () => {
  await render()
  await select('运行方式', 'DAILY')
  await submit()
  expect(emitted()!.schedule).toMatchObject({
    frequency: 'DAILY',
    interval_minutes: null,
    time_of_day: '10:00',
    weekday: null,
  })
  await wrapper!.find('input[aria-label="执行时刻"]').setValue('06:30')
  await select('运行方式', 'WEEKLY')
  await submit()
  expect(emitted(1)!.schedule).toMatchObject({
    frequency: 'WEEKLY',
    interval_minutes: null,
    time_of_day: '06:30',
    weekday: 1,
  })
  await select('运行方式', 'INTERVAL')
  await submit()
  expect(emitted(2)!.schedule).toMatchObject({
    frequency: 'INTERVAL',
    interval_minutes: 30,
    time_of_day: null,
    weekday: null,
  })
  expect(Object.keys(emitted(2)!.schedule)).toHaveLength(7)
})

it('367日拒绝但366日允许，开始/结束日期不从浏览器今天生成', async () => {
  await render()
  await wrapper!.find('input[aria-label="截止日期"]').setValue('2025-01-01')
  await submit()
  expect(emitted()).toBeUndefined()
  expect(wrapper!.text()).toContain('366')
  await wrapper!.find('input[aria-label="截止日期"]').setValue('2024-12-31')
  await submit()
  expect(emitted()!.schedule.start_date).toBe('2024-01-01')
})

it('20叶/每组10/最多5组都有操作和提交双重边界，最少1组1条', async () => {
  const original = value()
  original.groups = Array.from({ length: 2 }, () => ({
    logic: 'AND',
    conditions: Array.from({ length: 10 }, () => ({
      metric: 'spend',
      operator: 'GTE',
      threshold: '0',
    })),
  })) as RuleWrite['groups']
  await render({ modelValue: original })
  expect(wrapper!.text()).toContain('20 / 20')
  expect(button('添加条件组').attributes('disabled')).toBeDefined()
  expect(button('第1组添加条件').attributes('disabled')).toBeDefined()
  await button('删除第1组第1条').trigger('click')
  await button('添加条件组').trigger('click')
  expect(wrapper!.text()).toContain('20 / 20')
  await wrapper!.find('input[aria-label="第3组第1条阈值"]').setValue('0')
  await submit()
  expect(emitted()!.groups).toHaveLength(3)
  expect(emitted()!.groups.reduce((sum, group) => sum + group.conditions.length, 0)).toBe(20)
  await wrapper!.setProps({
    modelValue: {
      ...value(),
      groups: Array.from({ length: 5 }, () => ({
        logic: 'AND',
        conditions: [{ metric: 'spend', operator: 'GTE', threshold: '0' }],
      })),
    },
  })
  expect(button('添加条件组').attributes('disabled')).toBeDefined()
  expect(button('删除第1组第1条').attributes('disabled')).toBeDefined()
})

it('阈值字符串空/null不补0，CTR/计数上限错误不发submit，叶错误中文可读', async () => {
  await render()
  const threshold = wrapper!.find('input[aria-label="第1组第1条阈值"]')
  await threshold.setValue('')
  await threshold.trigger('blur')
  await submit()
  expect(emitted()).toBeUndefined()
  // ElementPlus原错误展示使用短延迟；等待真实DOM，不更改组件或弱化字段断言。
  await vi.waitFor(() => expect(wrapper!.text()).toContain('阈值必填'))
  await select('第1组第1条指标', 'clicks')
  await threshold.setValue('0.1')
  await submit()
  expect(emitted()).toBeUndefined()
  await threshold.setValue('9007199254740993000000')
  await submit()
  expect(emitted()!.groups[0].conditions[0].threshold).toBe('9007199254740993000000')
  await select('第1组第1条指标', 'ctr')
  await threshold.setValue('100.000001')
  await submit()
  expect(wrapper!.emitted('submit')).toHaveLength(1)
})

it('服务端pointer对应原字段，编辑后不展示上次意图的旧错误', async () => {
  const fieldErrors = [
    {
      path: '/groups/0/conditions/0/threshold',
      code: 'RANGE',
      message: '原阈值已超范围',
      constraint: null,
    },
  ]
  await render({ fieldErrors })
  expect(wrapper!.text()).toContain('原阈值已超范围')
  await wrapper!.find('input[aria-label="规则名称"]').setValue('改名')
  expect(wrapper!.text()).not.toContain('原阈值已超范围')
  await wrapper!.setProps({ fieldErrors: [{ ...fieldErrors[0], message: '新请求阈值错误' }] })
  expect(wrapper!.text()).toContain('新请求阈值错误')
})

it.each([{ readOnly: true }, { disabled: true }, { busy: true }])(
  '只读/禁用/等待均防提交与条件修改 %j',
  async (props) => {
    await render(props)
    await submit()
    expect(emitted()).toBeUndefined()
    expect(button('添加条件组').attributes('disabled')).toBeDefined()
    expect(wrapper!.find('input[aria-label="规则名称"]').attributes('disabled')).toBeDefined()
    if ('readOnly' in props) {
      expect(wrapper!.findAll('button').some((node) => node.text() === '保存规则')).toBe(false)
      await button('关闭').trigger('click')
      expect(wrapper!.emitted('cancel')).toHaveLength(1)
    }
  },
)

it('取消只发取消事件、不提交也不请求服务', async () => {
  await render()
  await button('取消').trigger('click')
  expect(wrapper!.emitted('cancel')).toHaveLength(1)
  expect(emitted()).toBeUndefined()
  expect(fetcher).not.toHaveBeenCalled()
})

it('指标11项和比较符6项来自原白名单，不提供第三层递归条件', async () => {
  await render()
  const controls = wrapper!.findAllComponents(ElSelect)
  const metrics = controls.find((node) => node.props('ariaLabel') === '第1组第1条指标')!
  const operators = controls.find((node) => node.props('ariaLabel') === '第1组第1条比较符')!
  expect(metrics.findAllComponents(ElOption).map((node) => node.props('value'))).toEqual([
    'spend',
    'impressions',
    'clicks',
    'registrations',
    'purchases',
    'purchase_value',
    'roas',
    'cpm',
    'ctr',
    'cpc',
    'cpa',
  ])
  expect(operators.findAllComponents(ElOption).map((node) => node.props('value'))).toEqual([
    'GT',
    'GTE',
    'LT',
    'LTE',
    'EQ',
    'NEQ',
  ])
  expect(wrapper!.text()).not.toContain('添加子组')
})

it('冷却0有明确意义，清空数字字段不静默补0或发缺键正文', async () => {
  await render()
  const cooldown = wrapper!
    .findAllComponents(ElInputNumber)
    .find((node) => node.props('ariaLabel') === '分析冷却分钟')!
  cooldown.vm.$emit('update:modelValue', 0)
  await flushPromises()
  await submit()
  expect(emitted()!.cooldown_minutes).toBe(0)
  cooldown.vm.$emit('update:modelValue', undefined)
  await flushPromises()
  await submit()
  expect(wrapper!.emitted('submit')).toHaveLength(1)
})

it('可选调度预览slot传当前Schedule副本，不能反向改原11字段表单', async () => {
  let received: RuleWrite['schedule'] | undefined
  const original = value()
  wrapper = mount(Form, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
    props: {
      modelValue: original,
      ownerOptions: [owner],
      profileOptions: [profile],
      scope,
      timezones,
    },
    slots: {
      'schedule-preview': ({ schedule }: { schedule: RuleWrite['schedule'] }) => {
        received = schedule
        return h('p', { 'data-preview-interval': schedule.interval_minutes }, '真实调度槽')
      },
    },
  })
  await flushPromises()
  expect(received).toEqual(original.schedule)
  received!.interval_minutes = 99
  const input = wrapper
    .findAllComponents(ElInputNumber)
    .find((x) => x.props('ariaLabel') === '间隔分钟')!
  expect(input.props('modelValue')).toBe(30)
  input.vm.$emit('update:modelValue', 60)
  await flushPromises()
  expect(received!.interval_minutes).toBe(60)
  expect(original.schedule.interval_minutes).toBe(30)
  await submit()
  expect(emitted()!.schedule.interval_minutes).toBe(60)
  expect(Object.keys(emitted()!)).toHaveLength(11)
})
