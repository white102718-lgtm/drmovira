import { ruleRecoveryApi } from '@/api/orbit/rule-recovery'
vi.mock('@/api/orbit/rule-recovery', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rule-recovery')>()),
  ruleRecoveryApi: { get: vi.fn() },
}))
/** 容器状态/原ElementPlus挂载；SDK为受控替身，不计真实HTTP或浏览器。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElInputNumber } from 'element-plus'
import Preview from '@/views/orbit/rules/RuleSchedulePreview.vue'
import { ruleSchedulePreviewApi } from '@/api/orbit/rule-schedule-preview'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Editor from '@/views/orbit/rules/RuleEditor.vue'
import Form from '@/views/orbit/rules/RuleDefinitionForm.vue'
import Selector from '@/views/orbit/rules/RuleScopeSelector.vue'
import { rulesApi, RuleApiError } from '@/api/orbit/rules'
import { ruleEditorApi } from '@/api/orbit/rule-editor'
import { ruleEditorDefinitionApi } from '@/api/orbit/rule-editor-definition'
vi.mock('@/api/orbit/rules', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rules')>()),
  rulesApi: { create: vi.fn(), update: vi.fn(), get: vi.fn() },
}))
vi.mock('@/api/orbit/rule-editor', () => ({
  ruleEditorApi: { context: vi.fn(), options: vi.fn() },
}))
vi.mock('@/api/orbit/rule-editor-definition', () => ({ ruleEditorDefinitionApi: { get: vi.fn() } }))
vi.mock('@/api/orbit/rule-schedule-preview', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rule-schedule-preview')>()),
  ruleSchedulePreviewApi: { preview: vi.fn() },
}))
const id = (n = 1) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
const owner = { id: id(2), team_id: id(3), name: '真实投手', team_name: '真实团队' }
const profile = {
  id: id(5),
  version: 'v-live',
  source: 'META',
  register_action_type: null,
  purchase_action_type: null,
  value_action_type: null,
  attribution_windows: ['7d_click'],
  action_report_time: 'conversion',
  timezone_policy: 'ACCOUNT_LOCAL',
  breakdown: 'TOTAL',
  maturity_days: 0,
  verified: true,
}
const body = () => ({
  name: '原规则',
  ownership: { owner_user_id: owner.id, owner_team_id: owner.team_id },
  target_level: 'AD',
  scope_snapshot_id: id(4),
  logic: 'AND',
  groups: [
    { logic: 'AND', conditions: [{ metric: 'spend', operator: 'GTE', threshold: '0.000001' }] },
  ],
  window: 'LAST_3D',
  metric_profile_id: profile.id,
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
const rule = () => ({ ...body(), id: id(), revision: 3, state: 'PAUSED', next_run_at: null })
const definition = () => ({
  rule: rule(),
  stored_scope: { id: id(4), count: 521, owner_user_id: owner.id, owner_team_id: owner.team_id },
})
const context = () => ({
  action: 'UPDATE',
  rule_id: id(),
  rule_revision: 3,
  editable: true,
  csrf_token: 'csrf-current',
  default_ownership: body().ownership,
  selected_owner: { item: owner, can_keep: true },
  selected_profile: {
    id: profile.id,
    bound_version: profile.version,
    current: profile,
    status: 'CURRENT',
  },
})
const page = (items: unknown[], next_cursor: string | null = null) => ({
  items,
  next_cursor,
  data_as_of: '2026-01-01T00:00:00.000Z',
  scope_version: 1,
})
let w: VueWrapper | undefined
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 1,
    tenant_id: id(99),
    csrf_token: 'recovery-current-csrf-token',
  })
  vi.mocked(ruleEditorApi.context).mockResolvedValue(context() as never)
  vi.mocked(ruleEditorDefinitionApi.get).mockResolvedValue(definition() as never)
  vi.mocked(ruleEditorApi.options).mockImplementation(
    async (q) => page(q.kind === 'OWNER' ? [owner] : [profile]) as never,
  )
  vi.mocked(rulesApi.update).mockResolvedValue(rule() as never)
})
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function render(props = {}) {
  w = mount(Editor, {
    attachTo: document.body,
    global: { plugins: [ElementPlus], stubs: { RuleScopeSelector: true } },
    props: {
      nativeActorId: 1,
      ruleId: id(),
      contextKey: 'actor-session-1',
      permissionCodes: ['rules.edit'],
      ...props,
    },
  })
  await flushPromises()
  return w
}
const form = () => w!.findComponent(Form)
function button(text: string) {
  const b = w!.findAll('button').find((x) => x.text() === text)
  expect(b, text).toBeTruthy()
  return b!
}
const emitSave = async () => {
  form().vm.$emit('submit', body())
  await flushPromises()
}
function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((a, b) => {
    resolve = a
    reject = b
  })
  return { promise, resolve, reject }
}
it('仅edit权限读取专属定义，真实521旧范围不冒充Scope5且不读creator成员', async () => {
  await render()
  expect(ruleEditorDefinitionApi.get).toHaveBeenCalledWith(id(), expect.any(AbortSignal))
  expect(rulesApi.get).not.toHaveBeenCalled()
  expect(form().props('scope')).toMatchObject({
    count: 521,
    label: '已保存范围，保存时重新校验权限',
  })
  expect(form().props('scope')).not.toHaveProperty('hash')
  expect(form().props('scope')).not.toHaveProperty('created_at')
  expect(w!.findComponent(Selector).exists()).toBe(false)
})
it('原11字段与quoted CAS保存，允许同正文no-op版本不增长', async () => {
  await render()
  await emitSave()
  expect(rulesApi.update).toHaveBeenCalledWith(
    id(),
    body(),
    expect.objectContaining({ if_match: '"3"', csrf_token: 'recovery-current-csrf-token' }),
    expect.any(AbortSignal),
  )
  expect(w!.emitted('saved')?.[0]).toEqual([rule()])
  const changes = w!.emitted('pendingIntent')!
  expect((changes[0][0] as any).kind).toBe('SAVE')
  expect(Object.keys((changes[0][0] as any).intent.body)).toHaveLength(11)
  expect(changes.at(-1)).toEqual([null])
})
it('定义与上下文revision漂移409，不能保存', async () => {
  vi.mocked(ruleEditorApi.context).mockResolvedValue({ ...context(), rule_revision: 4 } as never)
  await render()
  expect(w!.text()).toContain('409 EDITOR_CONTEXT_CHANGED')
  expect(form().props('readOnly')).toBe(true)
  await emitSave()
  expect(rulesApi.update).not.toHaveBeenCalled()
})
it.each(['ENABLED', 'ARCHIVED'])('%s只读但保留完整定义', async (state) => {
  vi.mocked(ruleEditorDefinitionApi.get).mockResolvedValue({
    ...definition(),
    rule: { ...rule(), state },
  } as never)
  vi.mocked(ruleEditorApi.context).mockResolvedValue({ ...context(), editable: false } as never)
  await render()
  expect(form().props('readOnly')).toBe(true)
  expect(form().props('modelValue')).toEqual(body())
  await emitSave()
  expect(rulesApi.update).not.toHaveBeenCalled()
})
it('创建无浏览器日期/时区假默认、空scope/profile不能提交', async () => {
  vi.mocked(ruleEditorApi.context).mockResolvedValue({
    ...context(),
    action: 'CREATE',
    rule_id: null,
    rule_revision: null,
    selected_profile: null,
  } as never)
  vi.mocked(ruleEditorApi.options).mockResolvedValue(page([]) as never)
  await render({ ruleId: null, permissionCodes: ['rules.create'] })
  expect(ruleEditorDefinitionApi.get).not.toHaveBeenCalled()
  expect(form().props('modelValue').schedule).toMatchObject({
    timezone: '',
    start_date: '',
    end_date: '',
  })
  expect(form().props('scope')).toBeNull()
  expect(rulesApi.create).not.toHaveBeenCalled()
})
it('候选分页不重置已修改名称，保留真实已加载配置', async () => {
  vi.mocked(ruleEditorApi.options).mockImplementation(
    async (q) => page(q.kind === 'OWNER' ? [owner] : [profile], 'next-page') as never,
  )
  await render()
  await form().find('input[aria-label="规则名称"]').setValue('尚未保存的名称')
  await button('下一页归属').trigger('click')
  await flushPromises()
  expect(ruleEditorApi.options).toHaveBeenCalledWith(
    expect.objectContaining({ kind: 'OWNER', cursor: 'next-page', page_size: 50 }),
    expect.any(AbortSignal),
  )
  expect(form().find('input[aria-label="规则名称"]').element).toHaveProperty(
    'value',
    '尚未保存的名称',
  )
  expect(form().props('profileOptions')[0].label).toContain(profile.id)
})
it('改owner清已保存scope并按真实新owner查询配置', async () => {
  await render()
  const ownership = { owner_user_id: id(9), owner_team_id: id(10) }
  form().vm.$emit('ownership-change', ownership)
  await flushPromises()
  expect(form().props('scope')).toBeNull()
  expect(ruleEditorApi.options).toHaveBeenCalledWith(
    expect.objectContaining({ kind: 'PROFILE', ...ownership }),
    expect.any(AbortSignal),
  )
  await emitSave()
  expect(rulesApi.update).not.toHaveBeenCalled()
})
it('候选403立即清所有旧敏感定义，不能发新保存', async () => {
  await render()
  vi.mocked(ruleEditorApi.options).mockRejectedValue(new RuleApiError(403, 'FORBIDDEN', '权限撤回'))
  await button('加载归属候选').trigger('click')
  await flushPromises()
  expect(form().exists()).toBe(false)
  expect(w!.text()).not.toContain('原规则')
  expect(w!.text()).toContain('FORBIDDEN')
  expect(rulesApi.update).not.toHaveBeenCalled()
})
it('普通503保留本地修改但阻止提交，明确来源失败', async () => {
  await render()
  vi.mocked(ruleEditorApi.options).mockRejectedValue(
    new RuleApiError(503, 'SOURCE_UNAVAILABLE', '来源未就绪'),
  )
  await button('加载指标候选').trigger('click')
  await flushPromises()
  expect(form().exists()).toBe(true)
  expect(w!.text()).toContain('SOURCE_UNAVAILABLE')
  await emitSave()
  expect(rulesApi.update).not.toHaveBeenCalled()
})
it('未确认保存先交父，手动用原body/key/CAS和当前CSRF恢复', async () => {
  await render()
  vi.mocked(rulesApi.update).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_ERROR', '结果未知', [], true, null, true),
  )
  await emitSave()
  const first = vi.mocked(rulesApi.update).mock.calls[0]
  const p = w!.emitted('pendingIntent')!.find((x) => (x[0] as any)?.kind === 'SAVE')![0] as any
  expect(Object.isFrozen(p.intent.body)).toBe(true)
  expect(w!.emitted('saved')).toBeUndefined()
  vi.mocked(ruleEditorApi.context).mockResolvedValue({
    ...context(),
    rule_revision: 4,
    csrf_token: 'csrf-new',
  } as never)
  await button('刷新恢复会话').trigger('click')
  await flushPromises()
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 1,
    tenant_id: id(99),
    csrf_token: 'recovery-new-csrf-token',
  })
  await button('使用原保存请求恢复').trigger('click')
  await flushPromises()
  const second = vi.mocked(rulesApi.update).mock.calls[1]
  expect(second[1]).toEqual(first[1])
  expect(second[2]).toEqual({ ...first[2], csrf_token: 'recovery-new-csrf-token' })
  expect(w!.emitted('saved')).toHaveLength(1)
})
it('明确422首次拒绝清pending并展示原字段path', async () => {
  await render()
  vi.mocked(rulesApi.update).mockRejectedValueOnce(
    new RuleApiError(422, 'FIELD_VALIDATION_FAILED', '名称错误', [
      { path: '/name', code: 'BAD', message: '名称错误', constraint: null },
    ]),
  )
  await emitSave()
  expect(w!.emitted('pendingIntent')!.at(-1)).toEqual([null])
  expect(form().props('fieldErrors')).toEqual([
    { path: '/name', code: 'BAD', message: '名称错误', constraint: null },
  ])
})
it('关闭保留进行中原意图，迟到成功不覆盖或发saved', async () => {
  const d = deferred<any>()
  vi.mocked(rulesApi.update).mockReturnValue(d.promise)
  await render()
  await emitSave()
  const call = vi.mocked(rulesApi.update).mock.calls[0]
  await button('关闭并保留未确认请求').trigger('click')
  expect(call[3]!.aborted).toBe(true)
  expect(w!.emitted('close')).toHaveLength(1)
  expect((w!.emitted('pendingIntent')!.at(-1)![0] as any).kind).toBe('SAVE')
  d.resolve(rule())
  await flushPromises()
  expect(w!.emitted('saved')).toBeUndefined()
})
it('父回传未知请求重挂载先取当前会话，不跨actor重发', async () => {
  await render()
  vi.mocked(rulesApi.update).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true),
  )
  await emitSave()
  const p = w!.emitted('pendingIntent')!.at(-1)![0]
  w!.unmount()
  await render({ pendingIntent: p, contextKey: 'different-actor' })
  expect(w!.text()).toContain('不能跨上下文恢复')
  expect(button('使用原保存请求恢复').attributes('disabled')).toBeDefined()
  expect(rulesApi.update).toHaveBeenCalledTimes(1)
})
it('同actor未知请求重挂载能获取当前CSRF恢复', async () => {
  await render()
  vi.mocked(rulesApi.update).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true),
  )
  await emitSave()
  const p = w!.emitted('pendingIntent')!.at(-1)![0]
  w!.unmount()
  await render({ pendingIntent: p })
  expect(button('使用原保存请求恢复').attributes('disabled')).toBeUndefined()
  await button('使用原保存请求恢复').trigger('click')
  await flushPromises()
  expect(w!.emitted('saved')).toHaveLength(1)
})
it('上下文切换中断读取并忽略旧定义', async () => {
  const d = deferred<any>(),
    next = deferred<any>()
  vi.mocked(ruleEditorDefinitionApi.get)
    .mockReturnValueOnce(d.promise)
    .mockReturnValueOnce(next.promise)
  await render()
  await w!.setProps({ ruleId: id(8) })
  d.resolve(definition())
  await flushPromises()
  expect(w!.text()).not.toContain('已保存范围，保存时重新校验权限')
  expect(rulesApi.update).not.toHaveBeenCalled()
})

it('CREATE真实Scope回传后原完整正文提交，不造scope回执或日期', async () => {
  vi.mocked(ruleEditorApi.context).mockResolvedValue({
    ...context(),
    action: 'CREATE',
    rule_id: null,
    rule_revision: null,
    selected_profile: null,
  } as never)
  vi.mocked(rulesApi.create).mockResolvedValue({ ...rule(), revision: 1, state: 'DRAFT' } as never)
  await render({ ruleId: null, permissionCodes: ['rules.create'] })
  form().vm.$emit('choose-scope', body().ownership)
  await flushPromises()
  const selector = w!.findComponent(Selector)
  expect(selector.props('ownership')).toEqual(body().ownership)
  expect(selector.props('remoteOptions')).toBe(true)
  selector.vm.$emit('choose', {
    id: id(4),
    count: 521,
    scope_version: 1,
    hash: 'a'.repeat(64),
    created_at: '2026-01-01T00:00:00.000Z',
  })
  await flushPromises()
  await emitSave()
  expect(rulesApi.create).toHaveBeenCalledWith(
    body(),
    expect.objectContaining({ csrf_token: 'recovery-current-csrf-token' }),
    expect.any(AbortSignal),
  )
  expect(w!.emitted('saved')).toHaveLength(1)
})
it('恢复Scope待选记录清pending后仍保持原owner，不把回执归给当前表单', async () => {
  const ownership = { owner_user_id: id(9), owner_team_id: id(10) }
  const intent = {
    body: {
      action: 'UPDATE',
      rule_id: id(),
      ownership,
      selection: { mode: 'IDS', account_ids: [id(11)], filter: null },
    },
    auth: { csrf_token: 'old', idempotency_key: 'old-key', if_match: '"3"' },
  }
  const record = {
    intent,
    context: JSON.stringify([
      'actor-session-1',
      'UPDATE',
      id(),
      ownership.owner_user_id,
      ownership.owner_team_id,
    ]),
  }
  await render({ pendingIntent: { kind: 'SCOPE', intent: record } })
  await button('打开原范围请求').trigger('click')
  const selector = w!.findComponent(Selector)
  expect(selector.props('ownership')).toEqual(ownership)
  expect(selector.props('modelValue')).toBe(true)
  selector.vm.$emit('pending-intent', null)
  await flushPromises()
  expect(selector.props('ownership')).toEqual(ownership)
  expect(form().props('modelValue')).toEqual(body())
  selector.vm.$emit('choose', {
    id: id(12),
    count: 1,
    scope_version: 1,
    hash: 'a'.repeat(64),
    created_at: '2026-01-01T00:00:00.000Z',
  })
  await flushPromises()
  expect(form().props('scope').id).toBe(id(4))
  expect(w!.text()).toContain('拥有者与当前表单不同')
})
it('定义401清私密数据；迟到另一路成功也不重建表单', async () => {
  vi.mocked(ruleEditorDefinitionApi.get).mockRejectedValue(
    new RuleApiError(401, 'SESSION_EXPIRED', '会话过期'),
  )
  await render()
  expect(form().exists()).toBe(false)
  expect(w!.text()).toContain('SESSION_EXPIRED')
  expect(w!.text()).not.toContain('真实投手')
  expect(ruleEditorApi.options).not.toHaveBeenCalled()
})
it('缺当前原动作不会探测Context/定义/候选', async () => {
  await render({ permissionCodes: ['rules.read'] })
  expect(ruleEditorApi.context).not.toHaveBeenCalled()
  expect(ruleEditorDefinitionApi.get).not.toHaveBeenCalled()
  expect(ruleEditorApi.options).not.toHaveBeenCalled()
  expect(form().exists()).toBe(false)
})

it('Form内实际预览读取当前未保存Schedule及真实Context，不提交Rule', async () => {
  vi.mocked(ruleSchedulePreviewApi.preview).mockResolvedValue({
    reference_at: '2026-01-01T00:00:00.123456Z',
    timezone: 'America/New_York',
    slots: [],
    skipped_local_times: [],
  })
  await render()
  const input = form()
    .findAllComponents(ElInputNumber)
    .find((x) => x.props('ariaLabel') === '间隔分钟')!
  input.vm.$emit('update:modelValue', 60)
  await flushPromises()
  await button('预览运行时间').trigger('click')
  await flushPromises()
  expect(ruleSchedulePreviewApi.preview).toHaveBeenCalledWith(
    {
      action: 'UPDATE',
      rule_id: id(),
      rule_revision: 3,
      schedule: { ...body().schedule, interval_minutes: 60 },
    },
    { csrf_token: 'csrf-current' },
    expect.any(AbortSignal),
  )
  const previewDialog = document.body.querySelector('[role="dialog"]')!
  expect(previewDialog?.textContent).toContain('2026-01-01T00:00:00.123456Z')
  expect(previewDialog?.textContent).toContain('America/New_York')
  expect(rulesApi.update).not.toHaveBeenCalled()
})
it('预览401/403即时清整个Editor敏感定义，不保留表单旧数据', async () => {
  vi.mocked(ruleSchedulePreviewApi.preview).mockRejectedValue(
    new RuleApiError(403, 'RULE_SCOPE_REVOKED', '当前规则范围已撤回'),
  )
  await render()
  await button('预览运行时间').trigger('click')
  await flushPromises()
  expect(form().exists()).toBe(false)
  expect(w!.text()).not.toContain('原规则')
  expect(w!.text()).toContain('RULE_SCOPE_REVOKED')
  expect(rulesApi.update).not.toHaveBeenCalled()
})
it('SAVE未确认期间禁用并清旧预览，不吞原pending保存意图', async () => {
  vi.mocked(ruleSchedulePreviewApi.preview).mockResolvedValue({
    reference_at: '2026-01-01T00:00:00.123456Z',
    timezone: 'America/New_York',
    slots: [],
    skipped_local_times: [],
  })
  await render()
  await button('预览运行时间').trigger('click')
  await flushPromises()
  const d = deferred<any>()
  vi.mocked(rulesApi.update).mockReturnValue(d.promise)
  await emitSave()
  expect(w!.findComponent(Preview).props('disabled')).toBe(true)
  expect(w!.text()).not.toContain('2026-01-01T00:00:00.123456Z')
  expect((w!.emitted('pendingIntent')!.at(-1)![0] as any).kind).toBe('SAVE')
})
it('owner切换使预览上下文失效并阻旧回包，不借新owner沿用旧结果', async () => {
  const d = deferred<any>()
  vi.mocked(ruleSchedulePreviewApi.preview).mockReturnValue(d.promise)
  await render()
  await button('预览运行时间').trigger('click')
  await flushPromises()
  const signal = vi.mocked(ruleSchedulePreviewApi.preview).mock.calls[0][2]!
  form().vm.$emit('ownership-change', { owner_user_id: id(9), owner_team_id: id(10) })
  await flushPromises()
  expect(signal.aborted).toBe(true)
  d.resolve({
    reference_at: '2026-01-01T00:00:00.123456Z',
    timezone: 'America/New_York',
    slots: [],
    skipped_local_times: [],
  })
  await flushPromises()
  expect(w!.text()).not.toContain('2026-01-01T00:00:00.123456Z')
})

it('首次真实身份与native页面不符不发SAVE，清旧显示且不造未知', async () => {
  await render()
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 2,
    tenant_id: id(99),
    csrf_token: 'different-actor-csrf-token',
  })
  await emitSave()
  expect(rulesApi.update).not.toHaveBeenCalled()
  expect(w!.emitted('pendingIntent')?.filter((x) => x[0]) ?? []).toEqual([])
  expect(form().exists()).toBe(false)
  expect(w!.text()).toContain('RULE_RECOVERY_UI_ACTOR_CHANGED')
})
it('未知SAVE主体变化拒绝第二POST，原key正文与pending保留', async () => {
  await render()
  vi.mocked(rulesApi.update).mockRejectedValueOnce(
    new RuleApiError(0, 'NETWORK_ERROR', '未知', [], true, null, true),
  )
  await emitSave()
  const old = w!.emitted('pendingIntent')!.find((x) => (x[0] as any)?.kind === 'SAVE')![0] as any
  vi.mocked(ruleRecoveryApi.get).mockResolvedValue({
    actor_id: 2,
    tenant_id: id(99),
    csrf_token: 'different-actor-csrf-token',
  })
  await button('使用原保存请求恢复').trigger('click')
  await flushPromises()
  expect(rulesApi.update).toHaveBeenCalledTimes(1)
  expect(w!.emitted('pendingIntent')!.at(-1)![0]).toEqual(old)
  expect(w!.text()).toContain('RULE_RECOVERY_PRINCIPAL_CHANGED')
})

it('Scope弹窗复核事件沿Editor交父，原保存/冻结不自动调用', async () => {
  await render()
  form().vm.$emit('choose-scope', body().ownership)
  await flushPromises()
  const selector = w!.findComponent(Selector)
  selector.vm.$emit('verifyIdentity')
  await flushPromises()
  expect(w!.emitted('verifyIdentity')).toHaveLength(1)
  expect(rulesApi.update).not.toHaveBeenCalled()
})
