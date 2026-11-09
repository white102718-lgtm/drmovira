/** 真实ElementPlus组件+SDK替身，仅证明内部界面逻辑，不是预检后端或平台验收。 */
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Dialog from '@/views/orbit/launch/PlanValidationDialog.vue'
import { launchValidationApi as api, LaunchValidationError } from '@/api/orbit/launch-validation'
import { launchApi } from '@/api/orbit/launch'
import { plan, caps, names, allocation, validation, fixedTime } from './plan-validation-fixtures'
import { taskFixture, taskUuid as id } from './tasks-fixtures'
let wrapper: VueWrapper | undefined
const button = (name: string) =>
  [...document.querySelectorAll('button')].find((node) => node.textContent?.trim() === name)!
const click = async (name: string) => {
  button(name).click()
  await flushPromises()
}
beforeEach(() => {
  vi.useFakeTimers({
    toFake: ['Date', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'],
  })
  vi.setSystemTime(fixedTime)
  vi.spyOn(api, 'reserveNames').mockResolvedValue(names())
  vi.spyOn(api, 'allocate').mockResolvedValue(allocation())
  vi.spyOn(api, 'allocation').mockResolvedValue(allocation())
  vi.spyOn(api, 'validate').mockResolvedValue(validation())
  vi.spyOn(api, 'execute').mockResolvedValue(taskFixture())
  vi.spyOn(launchApi, 'get').mockResolvedValue({ ...plan(), revision: 9, state: 'VALIDATED' })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it.each([502, 400])('真实SDK遇非原HTTP%s错误体保持写锁，重试同URL/键/CAS原意图', async (status) => {
  vi.mocked(api.reserveNames).mockRestore()
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      status === 502
        ? new Response('<html>gateway</html>', { status })
        : new Response(JSON.stringify({ invalid_error: true }), { status }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(names()), { status: 200 }))
  vi.stubGlobal('fetch', fetcher)
  await start({ validationAvailable: true })
  await click('开始预检')
  expect(wrapper!.emitted('locked')?.at(-1)).toEqual([true])
  expect(button('关闭预检').disabled).toBe(true)
  expect(fetcher).toHaveBeenCalledTimes(1)
  await click('重试原预检请求')
  expect(fetcher).toHaveBeenCalledTimes(2)
  expect(fetcher.mock.calls[1][0]).toBe(fetcher.mock.calls[0][0])
  expect(fetcher.mock.calls[1][1].headers).toEqual(fetcher.mock.calls[0][1].headers)
  expect(fetcher.mock.calls[1][1].body).toBe(fetcher.mock.calls[0][1].body)
  expect(wrapper!.emitted('locked')?.at(-1)).toEqual([false])
  expect(document.body.textContent).toContain('状态版本已重新读取')
})
async function start(extra: Record<string, unknown> = {}) {
  wrapper = mount(Dialog, {
    attachTo: document.body,
    props: { modelValue: true, plan: plan(), capabilities: caps(), ...extra },
    global: { plugins: [ElementPlus] },
  })
  await flushPromises()
}
it('依赖默认关闭，完整预检入口禁用且没有发出任何假请求', async () => {
  await start()
  expect(button('开始预检').disabled).toBe(true)
  expect(button('查看提交确认').disabled).toBe(true)
  expect(document.body.textContent).toContain('预检依赖尚未就绪')
  expect(api.reserveNames).not.toHaveBeenCalled()
  expect(api.allocate).not.toHaveBeenCalled()
  expect(api.validate).not.toHaveBeenCalled()
})
it('原Dialog标题X关闭同步父model，未知写入锁仍阻止X卸载意图', async () => {
  await start()
  const header = document.querySelector<HTMLButtonElement>('.el-dialog__headerbtn')!
  expect(header).toBeTruthy()
  header.click()
  await flushPromises()
  expect(wrapper!.emitted('update:modelValue')?.at(-1)).toEqual([false])
  wrapper!.unmount()
  document.body.innerHTML = ''
  vi.mocked(api.reserveNames).mockRejectedValueOnce(
    new LaunchValidationError(0, 'NETWORK_UNAVAILABLE', '结果未知', [], true, null, true),
  )
  await start({ validationAvailable: true })
  await click('开始预检')
  document.querySelector<HTMLButtonElement>('.el-dialog__headerbtn')!.click()
  await flushPromises()
  expect(wrapper!.emitted('update:modelValue')).toBeUndefined()
  expect(document.body.textContent).toContain('不能直接关闭')
})
it('真实SDK调用顺序为名称→完整分配→预检→原GET重读head9，再经独立确认仅emit真实Task', async () => {
  await start({ validationAvailable: true, executeAvailable: true })
  await click('开始预检')
  expect(vi.mocked(api.reserveNames).mock.invocationCallOrder[0]).toBeLessThan(
    vi.mocked(api.allocate).mock.invocationCallOrder[0],
  )
  expect(vi.mocked(api.allocate).mock.invocationCallOrder[0]).toBeLessThan(
    vi.mocked(api.validate).mock.invocationCallOrder[0],
  )
  expect(vi.mocked(api.validate).mock.invocationCallOrder[0]).toBeLessThan(
    vi.mocked(launchApi.get).mock.invocationCallOrder[0],
  )
  expect(vi.mocked(api.validate).mock.calls[0][1]).toEqual({
    allocation_id: allocation().id,
    name_reservation_id: names().id,
  })
  expect(vi.mocked(api.validate).mock.calls[0][2].if_match).toBe('"7"')
  for (const value of [
    '预检通过',
    '999999999999999999999.123456',
    '12.340000',
    'UTC',
    '99',
    '全部DAG节点数',
    '当前状态版本 9',
  ])
    expect(document.body.textContent).toContain(value)
  expect(document.body.textContent).not.toContain(caps().csrf_token)
  await click('查看全部冻结展开')
  expect(document.querySelector('.mapping-table')?.textContent).toContain(
    allocation().items[0].slot_key,
  )
  document.querySelector<HTMLButtonElement>('.el-drawer__close-btn')!.click()
  await flushPromises()
  await click('查看提交确认')
  await click('确认提交任务')
  expect(vi.mocked(api.execute).mock.calls[0][2].if_match).toBe('"9"')
  expect(wrapper!.emitted('accepted')?.[0][0]).toEqual(taskFixture())
  expect(button('关闭预检').disabled).toBe(false)
  expect(document.body.textContent).toContain('任务已受理')
  expect(document.body.textContent).not.toContain('广告创建成功')
})
it('异步分配QUEUED/RUNNING必须真实GET到SUCCEEDED才validate，task_id=null不补Task', async () => {
  vi.mocked(api.allocate).mockResolvedValueOnce({ ...allocation(), state: 'QUEUED', items: [] })
  vi.mocked(api.allocation)
    .mockResolvedValueOnce({ ...allocation(), state: 'RUNNING', items: [] })
    .mockResolvedValueOnce(allocation())
  await start({ validationAvailable: true })
  await click('开始预检')
  expect(api.validate).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('无独立任务引用')
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  expect(api.validate).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  expect(api.validate).toHaveBeenCalledTimes(1)
  expect(api.allocation).toHaveBeenCalledTimes(2)
})
it('停止本地等待不假称取消服务端，继续读取复用原allocation而不新建', async () => {
  vi.mocked(api.allocate).mockResolvedValueOnce({ ...allocation(), state: 'QUEUED', items: [] })
  await start({ validationAvailable: true })
  await click('开始预检')
  await click('停止等待分配')
  expect(document.body.textContent).toContain('服务端分配仍可能继续')
  expect(api.validate).not.toHaveBeenCalled()
  await click('继续读取分配')
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  expect(api.allocate).toHaveBeenCalledTimes(1)
  expect(api.validate).toHaveBeenCalledTimes(1)
})
it('取消重分配保留原映射；明确确认才seed+1并使旧预检失效', async () => {
  const confirm = vi
    .spyOn(ElMessageBox, 'confirm')
    .mockRejectedValueOnce('cancel')
    .mockResolvedValueOnce('confirm' as never)
  await start({ validationAvailable: true })
  await click('开始预检')
  await click('重新分配（需确认）')
  expect(confirm).toHaveBeenCalledTimes(1)
  expect(api.allocate).toHaveBeenCalledTimes(1)
  vi.mocked(api.allocate).mockResolvedValueOnce({ ...allocation(), id: id(102), seed: 1 })
  await click('重新分配（需确认）')
  expect(api.allocate).toHaveBeenCalledTimes(2)
  expect(vi.mocked(api.allocate).mock.calls[1][1].seed).toBe(1)
  expect(api.reserveNames).toHaveBeenCalledTimes(1)
  expect(vi.mocked(api.validate).mock.calls[1][1].allocation_id).toBe(id(102))
})
it('200 valid=false显示全部1000字段错误并逐页定位JSON Pointer，不假装预检成功', async () => {
  const errors = Array.from({ length: 1000 }, (_, n) => ({
    path: `/campaigns/0/adsets/0/ads/${n}/body~1x~0`,
    code: 'FIELD_VALIDATION_FAILED',
    message: `错误${n}<img src=x>`,
    constraint: '必须提供',
  }))
  vi.mocked(api.validate).mockResolvedValueOnce({
    ...validation(),
    valid: false,
    hash: null,
    expires_at: null,
    errors,
  })
  await start({ validationAvailable: true, executeAvailable: true })
  await click('开始预检')
  expect(launchApi.get).not.toHaveBeenCalled()
  expect(button('查看提交确认').disabled).toBe(true)
  expect(document.querySelectorAll('.validation-errors .el-table__body tr')).toHaveLength(50)
  const locate = document.querySelector<HTMLButtonElement>(
    '.validation-errors .el-table__body tr button',
  )!
  locate.click()
  await flushPromises()
  expect(wrapper!.emitted('locate')?.[0]).toEqual([
    errors[0].path,
    ['campaigns', '0', 'adsets', '0', 'ads', '0', 'body/x~'],
  ])
  expect(document.querySelector('img[src="x"]')).toBeNull()
  await click('下一页错误')
  expect(document.body.textContent).toContain('错误99')
  expect(document.body.textContent).toContain('1000')
  await click('末页错误')
  expect(document.body.textContent).toContain('错误999')
  expect(button('下一页错误').disabled).toBe(true)
})
it('通用422所有字段/nullable约束可见，503依赖失败不创建假Task', async () => {
  vi.mocked(api.validate).mockRejectedValueOnce(
    new LaunchValidationError(
      422,
      'FIELD_VALIDATION_FAILED',
      '预检字段失败',
      [
        {
          path: '/identity_bindings',
          code: 'REQUIRED',
          message: '需要逐账户身份',
          constraint: null,
        },
      ],
      false,
    ),
  )
  await start({ validationAvailable: true })
  await click('开始预检')
  expect(document.querySelector('.validation-errors')?.textContent).toContain('/identity_bindings')
  expect(document.querySelector('.validation-errors')?.textContent).toContain('需要逐账户身份')
  expect(button('关闭预检').disabled).toBe(false)
  expect(wrapper!.emitted('accepted')).toBeUndefined()
  vi.mocked(api.validate).mockRejectedValueOnce(
    new LaunchValidationError(503, 'DEPENDENCY_UNAVAILABLE', '权威能力尚未就绪', [], true),
  )
  await click('开始预检')
  expect(document.body.textContent).toContain('权威能力尚未就绪')
  expect(api.execute).not.toHaveBeenCalled()
})
it('未知写结果锁定原意图，同key/body/CAS显式重试恢复，不偷偷生成新key', async () => {
  vi.mocked(api.reserveNames).mockRejectedValueOnce(
    new LaunchValidationError(0, 'NETWORK_UNAVAILABLE', '命名结果待确认', [], true, null, true),
  )
  await start({ validationAvailable: true })
  await click('开始预检')
  expect(button('关闭预检').disabled).toBe(true)
  expect(api.allocate).not.toHaveBeenCalled()
  const first = vi.mocked(api.reserveNames).mock.calls[0]
  await click('重试原预检请求')
  expect(vi.mocked(api.reserveNames).mock.calls[1]).toEqual(first)
  expect(api.validate).toHaveBeenCalledTimes(1)
  expect(button('关闭预检').disabled).toBe(false)
})
it('预检成功但GET head失败只重读head，不猜+1或重复预检写入', async () => {
  vi.mocked(launchApi.get).mockRejectedValueOnce(new Error('计划读取中断'))
  await start({ validationAvailable: true, executeAvailable: true })
  await click('开始预检')
  expect(button('查看提交确认').disabled).toBe(true)
  expect(api.validate).toHaveBeenCalledTimes(1)
  await click('重新读取计划版本')
  expect(api.validate).toHaveBeenCalledTimes(1)
  expect(launchApi.get).toHaveBeenCalledTimes(2)
  expect(button('查看提交确认').disabled).toBe(false)
})
it('GET发现配置漂移则旧hash失效；props/权限变化也清掉旧预检，不沿用旧确认', async () => {
  vi.mocked(launchApi.get).mockResolvedValueOnce({ ...plan(), revision: 9, name: '另一个配置' })
  await start({ validationAvailable: true, executeAvailable: true })
  await click('开始预检')
  expect(document.body.textContent).toContain('服务端配置已变化')
  expect(button('查看提交确认').disabled).toBe(true)
  await wrapper!.setProps({
    plan: { ...plan(), revision: 10 },
    capabilities: { ...caps(), actions: [] },
  })
  await flushPromises()
  expect(document.body.textContent).toContain('没有可用的计划编辑及预检权限')
  expect(button('开始预检').disabled).toBe(true)
})
it('TTL到期及上海跨日使已取得的预检/命名失效，不能继续提交', async () => {
  await start({ validationAvailable: true, executeAvailable: true })
  await click('开始预检')
  expect(button('查看提交确认').disabled).toBe(false)
  vi.setSystemTime('2026-11-08T02:15:01Z')
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  expect(button('查看提交确认').disabled).toBe(true)
  expect(document.body.textContent).toContain('预检有效期已结束')
  vi.setSystemTime('2026-11-08T16:00:00Z')
  await vi.advanceTimersByTimeAsync(1000)
  await flushPromises()
  expect(document.body.textContent).toContain('已跨上海命名日')
  expect(document.body.textContent).not.toContain(names().id)
})

it('分配FAILED展示实际警告，60次未完成仍不伪造失败或Task', async () => {
  vi.mocked(api.allocate).mockResolvedValueOnce({
    ...allocation(),
    state: 'FAILED',
    items: [],
    warnings: ['兼容图没有完整匹配'],
  })
  await start({ validationAvailable: true })
  await click('开始预检')
  expect(document.body.textContent).toContain('兼容图没有完整匹配')
  expect(api.validate).not.toHaveBeenCalled()
  wrapper!.unmount()
  wrapper = undefined
  vi.mocked(api.allocate).mockResolvedValueOnce({ ...allocation(), state: 'QUEUED', items: [] })
  vi.mocked(api.allocation).mockResolvedValue({ ...allocation(), state: 'QUEUED', items: [] })
  await start({ validationAvailable: true })
  await click('开始预检')
  await vi.advanceTimersByTimeAsync(60000)
  await flushPromises()
  expect(api.allocation).toHaveBeenCalledTimes(60)
  expect(document.body.textContent).toContain('本轮等待已结束')
  expect(button('继续读取分配').disabled).toBe(false)
  expect(api.validate).not.toHaveBeenCalled()
})
it('在途写请求遇Plan变更不自动换意图，迟到旧结果不能串到新计划', async () => {
  let complete!: (value: ReturnType<typeof names>) => void
  vi.mocked(api.reserveNames).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        complete = resolve
      }),
  )
  await start({ validationAvailable: true })
  await click('开始预检')
  await wrapper!.setProps({ plan: { ...plan(), id: id(200), name: '新计划' } })
  expect(button('关闭预检').disabled).toBe(true)
  complete(names())
  await flushPromises()
  expect(api.allocate).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('先前请求已收到响应')
  expect(button('关闭预检').disabled).toBe(false)
  expect(document.body.textContent).not.toContain(names().id)
})
it('未知execute遇父上下文变化不卸载丢意图，恢复后重试原提交并解锁', async () => {
  vi.mocked(api.execute).mockRejectedValueOnce(
    new LaunchValidationError(0, 'NETWORK_UNAVAILABLE', '原提交未知', [], true, null, true),
  )
  await start({ validationAvailable: true, executeAvailable: true })
  await click('开始预检')
  await click('查看提交确认')
  await click('确认提交任务')
  const original = vi.mocked(api.execute).mock.calls[0]
  expect(button('关闭预检').disabled).toBe(true)
  await wrapper!.setProps({ plan: { ...plan(), name: '已更换上下文' } })
  await flushPromises()
  expect(button('重试本次提交').disabled).toBe(true)
  expect(button('关闭预检').disabled).toBe(true)
  expect(api.execute).toHaveBeenCalledTimes(1)
  await wrapper!.setProps({ plan: plan() })
  await flushPromises()
  await click('重试本次提交')
  expect(vi.mocked(api.execute).mock.calls[1]).toEqual(original)
  expect(wrapper!.emitted('accepted')).toHaveLength(1)
  expect(button('关闭预检').disabled).toBe(false)
})
