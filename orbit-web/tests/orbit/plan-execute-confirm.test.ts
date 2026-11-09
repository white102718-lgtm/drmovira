import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Confirm from '@/views/orbit/launch/PlanExecuteConfirm.vue'
import { launchValidationApi as api, LaunchValidationError } from '@/api/orbit/launch-validation'
import { plan, caps, validation, names, allocation, fixedTime } from './plan-validation-fixtures'
import { taskFixture } from './tasks-fixtures'
let wrapper: VueWrapper | undefined
const button = (name: string) =>
  [...document.querySelectorAll('button')].find((node) => node.textContent?.trim() === name)!
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
  vi.setSystemTime(fixedTime)
  vi.spyOn(api, 'execute').mockResolvedValue(taskFixture())
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.restoreAllMocks()
})
async function start(extra: Record<string, unknown> = {}) {
  wrapper = mount(Confirm, {
    attachTo: document.body,
    props: {
      modelValue: true,
      plan: { ...plan(), revision: 9, state: 'VALIDATED' },
      capabilities: caps(),
      validation: validation(),
      allocation: allocation(),
      reservation: names(),
      ...extra,
    },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
it('执行默认false，完整确认字段和分币种原始金额可读但绝不发送', async () => {
  await start()
  expect(button('确认提交任务').disabled).toBe(true)
  expect(document.body.textContent).toContain('执行依赖尚未就绪')
  expect(document.body.textContent).toContain('999999999999999999999.123456')
  expect(document.body.textContent).toContain('12.340000')
  expect(api.execute).not.toHaveBeenCalled()
})
it('默认暂停提交使用重读head9而非source7/猜8，只emit真实Task受理且解除锁', async () => {
  await start({ available: true })
  button('确认提交任务').click()
  await flushPromises()
  expect(api.execute).toHaveBeenCalledTimes(1)
  expect(vi.mocked(api.execute).mock.calls[0][1]).toEqual({
    hash: validation().hash,
    activate_ack: false,
  })
  expect(vi.mocked(api.execute).mock.calls[0][2].if_match).toBe('"9"')
  expect(wrapper!.emitted('accepted')?.[0][0]).toEqual(taskFixture())
  expect(wrapper!.emitted('locked')?.at(-1)).toEqual([false])
  expect(document.body.textContent).not.toContain('广告创建成功')
})
it('激活必须独立publish与真实checkbox确认，不能默认勾选', async () => {
  const source = { ...plan(), activate_after_create: true }
  await start({ available: true, plan: source, capabilities: { ...caps(), actions: ['execute'] } })
  expect(button('确认提交任务').disabled).toBe(true)
  expect((document.querySelector('input[type="checkbox"]') as HTMLInputElement).disabled).toBe(true)
  await wrapper!.setProps({ capabilities: caps() })
  const check = wrapper!.findComponent({ name: 'ElCheckbox' })
  check.vm.$emit('update:modelValue', true)
  await flushPromises()
  button('确认提交任务').click()
  await flushPromises()
  expect(vi.mocked(api.execute).mock.calls[0][1].activate_ack).toBe(true)
})
it('过期/上海跨日/无execute/错误配置引用均禁止新请求', async () => {
  await start({
    available: true,
    validation: { ...validation(), expires_at: '2026-11-08T01:59:59Z' },
  })
  expect(button('确认提交任务').disabled).toBe(true)
  await wrapper!.setProps({
    validation: validation(),
    reservation: { ...names(), naming_date: '2026-11-07' },
  })
  expect(button('确认提交任务').disabled).toBe(true)
  await wrapper!.setProps({ reservation: names(), capabilities: { ...caps(), actions: ['edit'] } })
  expect(button('确认提交任务').disabled).toBe(true)
  expect(api.execute).not.toHaveBeenCalled()
})
it('未知结果保留同hash/key/CAS，不能关闭；明确重试才发送同一意图', async () => {
  vi.mocked(api.execute).mockRejectedValueOnce(
    new LaunchValidationError(0, 'NETWORK_UNAVAILABLE', '结果待确认', [], true, null, true),
  )
  await start({ available: true })
  button('确认提交任务').click()
  await flushPromises()
  expect(button('取消提交').disabled).toBe(true)
  expect(api.execute).toHaveBeenCalledTimes(1)
  const first = vi.mocked(api.execute).mock.calls[0]
  button('重试本次提交').click()
  await flushPromises()
  expect(vi.mocked(api.execute).mock.calls[1]).toEqual(first)
  expect(wrapper!.emitted('accepted')).toHaveLength(1)
})
it('同键准备忙态保留确认意图，不因409换key或宣告任务已受理', async () => {
  vi.mocked(api.execute).mockRejectedValueOnce(
    new LaunchValidationError(
      409,
      'EXECUTION_PREPARATION_IN_PROGRESS',
      '原请求仍在准备',
      [],
      false,
      null,
      true,
      409,
    ),
  )
  await start({ available: true })
  button('确认提交任务').click()
  await flushPromises()
  const original = vi.mocked(api.execute).mock.calls[0]
  expect(button('取消提交').disabled).toBe(true)
  expect(wrapper!.emitted('accepted')).toBeUndefined()
  expect(api.execute).toHaveBeenCalledTimes(1)
  button('重试本次提交').click()
  await flushPromises()
  expect(vi.mocked(api.execute).mock.calls[1]).toEqual(original)
  expect(wrapper!.emitted('accepted')?.[0][0]).toEqual(taskFixture())
})
it('未知请求遇上下文/权限变化仍保留意图但隐藏旧范围、禁重试，不把旧响应写入新上下文', async () => {
  vi.mocked(api.execute).mockRejectedValueOnce(
    new LaunchValidationError(0, 'NETWORK_UNAVAILABLE', '未知', [], true, null, true),
  )
  await start({ available: true })
  button('确认提交任务').click()
  await flushPromises()
  await wrapper!.setProps({ contextVersion: 'changed', capabilities: { ...caps(), actions: [] } })
  expect(button('重试本次提交').disabled).toBe(true)
  expect(document.body.textContent).not.toContain(plan().ownership.owner_user_id)
  expect(api.execute).toHaveBeenCalledTimes(1)
})
it('422字段错误完整保留，已知拒绝解除未知锁而不发Task成功', async () => {
  vi.mocked(api.execute).mockRejectedValueOnce(
    new LaunchValidationError(
      422,
      'FIELD_VALIDATION_FAILED',
      '字段失败',
      [{ path: '/activate_ack', code: 'ACK_REQUIRED', message: '必须确认', constraint: null }],
      false,
    ),
  )
  await start({ available: true })
  button('确认提交任务').click()
  await flushPromises()
  expect(document.querySelector('.submit-errors')?.textContent).toContain('/activate_ack')
  expect(document.querySelector('.submit-errors')?.textContent).toContain('必须确认')
  expect(button('取消提交').disabled).toBe(false)
  expect(wrapper!.emitted('accepted')).toBeUndefined()
})
