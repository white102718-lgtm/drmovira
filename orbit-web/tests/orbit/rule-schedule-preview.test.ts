/** ElementPlus实际预览组件挂载，SDK替身不计真实HTTP/DST调度验收。 */
import { mount, flushPromises, DOMWrapper, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElDialog } from 'element-plus'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Preview from '@/views/orbit/rules/RuleSchedulePreview.vue'
import { ruleSchedulePreviewApi } from '@/api/orbit/rule-schedule-preview'
import { RuleApiError } from '@/api/orbit/rules'
vi.mock('@/api/orbit/rule-schedule-preview', async (original) => ({
  ...(await original<typeof import('@/api/orbit/rule-schedule-preview')>()),
  ruleSchedulePreviewApi: { preview: vi.fn() },
}))
const schedule = () => ({
  frequency: 'INTERVAL',
  interval_minutes: 30,
  time_of_day: null,
  weekday: null,
  timezone: 'UTC',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
})
const result = () => ({
  reference_at: '2026-01-01T00:00:00.123456Z',
  timezone: 'UTC',
  slots: [{ local_time: '2026-01-01T00:30:00+00:00', utc_time: '2026-01-01T00:30:00.000000Z' }],
  skipped_local_times: [],
})
const id = '00000000-0000-4000-8000-000000000001'
let w: VueWrapper | undefined
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(ruleSchedulePreviewApi.preview).mockResolvedValue(result())
})
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
})
async function render(props = {}) {
  w = mount(Preview, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
    props: {
      action: 'CREATE',
      ruleId: null,
      ruleRevision: null,
      schedule: schedule() as never,
      csrfToken: 'current-session-csrf',
      contextKey: 'real-actor-epoch',
      permissionCodes: ['rules.create'],
      ...props,
    },
  })
  await flushPromises()
}
const button = (text: string) => {
  const b = new DOMWrapper(document.body).findAll('button').find((x) => x.text() === text)
  expect(b, text).toBeTruthy()
  return b!
}
const run = async () => {
  await button('预览运行时间').trigger('click')
  await flushPromises()
}
function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}
it('仅明确点击POST当前Schedule7，不自动构造五条/写入', async () => {
  await render()
  expect(ruleSchedulePreviewApi.preview).not.toHaveBeenCalled()
  await run()
  expect(ruleSchedulePreviewApi.preview).toHaveBeenCalledWith(
    { action: 'CREATE', rule_id: null, rule_revision: null, schedule: schedule() },
    { csrf_token: 'current-session-csrf' },
    expect.any(AbortSignal),
  )
  expect(document.body.textContent ?? '').toContain(result().reference_at)
  expect(document.body.textContent ?? '').toContain(result().slots[0].local_time)
  expect(document.body.textContent ?? '').toContain(result().slots[0].utc_time)
  expect(w!.emitted('saved')).toBeUndefined()
})
it('UPDATE仅对应edit动作和当前版本，不借read', async () => {
  await render({ action: 'UPDATE', ruleId: id, ruleRevision: 7, permissionCodes: ['rules.edit'] })
  await run()
  expect(ruleSchedulePreviewApi.preview).toHaveBeenCalledWith(
    expect.objectContaining({ action: 'UPDATE', rule_id: id, rule_revision: 7 }),
    expect.anything(),
    expect.any(AbortSignal),
  )
})
it('缺动作/缺日期或时区不发请求，不推断客户端日期', async () => {
  await render({ schedule: { ...schedule(), timezone: '', start_date: '' } })
  expect(button('预览运行时间').attributes('disabled')).toBeDefined()
  expect(document.body.textContent ?? '').toContain('请先完整填写')
  expect(ruleSchedulePreviewApi.preview).not.toHaveBeenCalled()
  await w!.setProps({ schedule: schedule() as never, permissionCodes: ['rules.read'] })
  expect(button('预览运行时间').attributes('disabled')).toBeDefined()
  expect(document.body.textContent ?? '').toContain('没有当前创建或编辑动作')
})
it('服务端零记录真实空状态，既不补五条也不造触发记录', async () => {
  vi.mocked(ruleSchedulePreviewApi.preview).mockResolvedValue({ ...result(), slots: [] })
  await render()
  await run()
  expect(document.body.textContent ?? '').toContain('没有可运行时刻')
  expect(document.body.querySelector('.el-table')).toBeNull()
})
it('显示真实DST跳过墙钟和中文原因', async () => {
  vi.mocked(ruleSchedulePreviewApi.preview).mockResolvedValue({
    ...result(),
    skipped_local_times: [
      { local_time: '2026-03-08T02:30:00', reason_code: 'DST_NONEXISTENT_LOCAL_TIME' },
    ],
  })
  await render()
  await run()
  expect(document.body.textContent ?? '').toContain('2026-03-08T02:30:00')
  expect(document.body.textContent ?? '').toContain('该本地时刻不存在，已跳过')
})
it('改schedule立刻清结果，旧回包不能当新预览', async () => {
  const d = deferred<any>()
  vi.mocked(ruleSchedulePreviewApi.preview).mockReturnValue(d.promise)
  await render()
  await run()
  const signal = vi.mocked(ruleSchedulePreviewApi.preview).mock.calls[0][2]!
  await w!.setProps({ schedule: { ...schedule(), interval_minutes: 60 } as never })
  expect(signal.aborted).toBe(true)
  d.resolve(result())
  await flushPromises()
  expect(document.body.textContent ?? '').not.toContain(result().reference_at)
  expect(document.body.textContent ?? '').not.toContain('00:30:00+00:00')
})
it('切actor/revision时清结果并取消旧读取', async () => {
  await render()
  await run()
  await w!.setProps({ contextKey: 'new-actor' })
  expect(document.body.textContent ?? '').not.toContain(result().reference_at)
  await run()
  await w!.setProps({
    action: 'UPDATE',
    ruleId: id,
    ruleRevision: 2,
    permissionCodes: ['rules.edit'],
  })
  expect(document.body.textContent ?? '').not.toContain(result().reference_at)
  expect(ruleSchedulePreviewApi.preview).toHaveBeenCalledTimes(2)
})
it.each([401, 403])(
  '%d清敏感旧结果且禁止用改schedule解锁，当前认证刷新后可手动读',
  async (status) => {
    await render()
    await run()
    vi.mocked(ruleSchedulePreviewApi.preview).mockRejectedValue(
      new RuleApiError(status, 'CURRENT_DENIED', '当前会话不可读取'),
    )
    await run()
    expect(document.body.textContent ?? '').not.toContain(result().reference_at)
    expect(document.body.textContent ?? '').toContain('CURRENT_DENIED')
    await w!.setProps({ schedule: { ...schedule(), interval_minutes: 60 } as never })
    expect(button('预览运行时间').attributes('disabled')).toBeDefined()
    await w!.setProps({ csrfToken: 'new-current-session-csrf' })
    expect(button('预览运行时间').attributes('disabled')).toBeUndefined()
    expect(ruleSchedulePreviewApi.preview).toHaveBeenCalledTimes(2)
  },
)
it('503/409显式来源错误，不冒充空结果或自动重试', async () => {
  vi.mocked(ruleSchedulePreviewApi.preview).mockRejectedValue(
    new RuleApiError(503, 'PREVIEW_UNAVAILABLE', '时间来源未就绪'),
  )
  await render()
  await run()
  expect(document.body.textContent ?? '').toContain('PREVIEW_UNAVAILABLE')
  expect(document.body.textContent ?? '').not.toContain('没有可运行时刻')
  expect(ruleSchedulePreviewApi.preview).toHaveBeenCalledTimes(1)
})
it('明确取消和卸载中断在途，迟到结果不外显', async () => {
  const d = deferred<any>()
  vi.mocked(ruleSchedulePreviewApi.preview).mockReturnValue(d.promise)
  await render()
  await run()
  const signal = vi.mocked(ruleSchedulePreviewApi.preview).mock.calls[0][2]!
  await button('取消预览').trigger('click')
  expect(signal.aborted).toBe(true)
  d.resolve(result())
  await flushPromises()
  expect(document.body.textContent ?? '').not.toContain(result().reference_at)
  await run()
  const second = vi.mocked(ruleSchedulePreviewApi.preview).mock.calls[1][2]!
  w!.unmount()
  w = undefined
  expect(second.aborted).toBe(true)
})

it('初始不弹出，点击后为原生有名modal，加载/结果仅在弹窗', async () => {
  const d = deferred<any>()
  vi.mocked(ruleSchedulePreviewApi.preview).mockReturnValue(d.promise)
  await render()
  expect(w!.findComponent(ElDialog).props('modelValue')).toBe(false)
  const initialModal = document.body.querySelector('[role="dialog"]')
  if (initialModal) expect(new DOMWrapper(initialModal).isVisible()).toBe(false)
  await run()
  const modal = document.body.querySelector('[role="dialog"]')!
  expect(modal).not.toBeNull()
  expect(modal.getAttribute('aria-modal')).toBe('true')
  const label = modal.getAttribute('aria-labelledby')
  expect(
    label ? document.getElementById(label)?.textContent : modal.getAttribute('aria-label'),
  ).toContain('预览未来5次运行')
  expect(modal.textContent).toContain('正在读取未来运行时间')
  d.resolve(result())
  await flushPromises()
  expect(modal.textContent).toContain(result().reference_at)
  expect(w!.find('.schedule-preview').text()).not.toContain(result().reference_at)
})
it('主动关闭abort并清内容，不自动重发/保存，显式再次查询才打开', async () => {
  const d = deferred<any>()
  vi.mocked(ruleSchedulePreviewApi.preview).mockReturnValueOnce(d.promise)
  await render()
  await run()
  const signal = vi.mocked(ruleSchedulePreviewApi.preview).mock.calls[0][2]!
  const close = new DOMWrapper(document.body).find('button.el-dialog__headerbtn')
  expect(close.exists()).toBe(true)
  await close.trigger('click')
  await flushPromises()
  expect(signal.aborted).toBe(true)
  expect(w!.findComponent(ElDialog).props('modelValue')).toBe(false)
  d.resolve(result())
  await flushPromises()
  expect(document.body.textContent).not.toContain(result().reference_at)
  expect(ruleSchedulePreviewApi.preview).toHaveBeenCalledTimes(1)
  w!.findComponent(ElDialog).vm.$emit('closed')
  await flushPromises()
  expect(document.activeElement).toBe(button('预览运行时间').element)
  await run()
  expect(ruleSchedulePreviewApi.preview).toHaveBeenCalledTimes(2)
  expect(w!.findComponent(ElDialog).props('modelValue')).toBe(true)
  expect(w!.emitted('saved')).toBeUndefined()
})
it('Schedule改动/禁用/撤权关闭modal并清旧内容', async () => {
  await render()
  await run()
  await w!.setProps({ schedule: { ...schedule(), interval_minutes: 60 } as never })
  expect(w!.findComponent(ElDialog).props('modelValue')).toBe(false)
  expect(document.body.textContent).not.toContain(result().reference_at)
  await run()
  await w!.setProps({ disabled: true })
  expect(w!.findComponent(ElDialog).props('modelValue')).toBe(false)
  expect(document.body.textContent).not.toContain(result().reference_at)
})
