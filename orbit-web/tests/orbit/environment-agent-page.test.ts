import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton } from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Page from '@/views/orbit/environments/index.vue'
import AgentRegistrationForm from '@/views/orbit/environments/AgentRegistrationForm.vue'
import { environmentApi, AgentApiError } from '@/api/orbit/environments'
const user = vi.hoisted(() => ({
  id: 1,
  permissions: ['environments.read', 'environments.enroll', 'environments.revoke'],
}))
vi.mock('@/store/modules/user', () => ({ default: () => user }))
const id = '00000000-0000-0000-0000-000000000001'
const body = { name: '执行机 A', endpoint: 'http://127.0.0.1:50325', probe_interval: 30 }
const agent = { ...body, id, revision: 1, state: 'OFFLINE' as const, last_heartbeat: null }
let actor = 1,
  role = 'SUPER_ADMIN',
  w: VueWrapper
beforeEach(() => {
  actor = 1
  role = 'SUPER_ADMIN'
  user.permissions = ['environments.read', 'environments.enroll', 'environments.revoke']
  vi.spyOn(environmentApi, 'capabilities').mockImplementation(async (operation) => ({
    actor_id: actor,
    tenant_id: id,
    data_role: role as 'SUPER_ADMIN',
    csrf_token: operation === 'READ' ? null : 'abcdefghijklmnop',
  }))
  vi.spyOn(environmentApi, 'list').mockResolvedValue({
    items: [agent],
    next_cursor: null,
    scope_version: 1,
    data_as_of: '2026-11-09T00:00:00.000Z',
  })
  vi.spyOn(environmentApi, 'get').mockResolvedValue(agent)
})
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start() {
  w = mount(Page, { global: { plugins: [ElementPlus] }, attachTo: document.body })
  await flushPromises()
}
async function click(label: string) {
  const b = w.findAllComponents(ElButton).find((b) => b.text() === label)
  expect(b, label).toBeTruthy()
  await b!.trigger('click')
  await flushPromises()
}
it('retains seven Agent fields and separates absent certificate/login/capability from offline state', async () => {
  await start()
  expect(w.text()).toContain('执行机 A')
  await click('详情')
  for (const label of [
    '设备证书',
    '客户端/API',
    'Profile',
    '代理',
    'Meta 登录',
    '账户身份',
    '操作能力',
    '租约',
    '当前任务',
    '故障',
    '未知',
  ])
    expect(document.body.textContent).toContain(label)
  expect(document.body.textContent).not.toContain('登记成功即在线')
})
it('ordinary users remain read-only even with enrollment permission', async () => {
  role = 'USER'
  await start()
  expect(w.findAllComponents(ElButton).some((b) => b.text() === '登记机器')).toBe(false)
  expect(w.findAllComponents(ElButton).some((b) => b.text() === '修改')).toBe(false)
})
it('enroll-only administrator can register without fetching a forbidden list', async () => {
  user.permissions = ['environments.enroll']
  await start()
  await click('登记机器')
  expect(environmentApi.list).not.toHaveBeenCalled()
  expect(w.findComponent(AgentRegistrationForm).exists()).toBe(true)
})
it('single-page next retains applied filters rather than accumulating rows', async () => {
  vi.mocked(environmentApi.list)
    .mockResolvedValueOnce({
      items: [agent],
      next_cursor: 'cursor-next',
      scope_version: 1,
      data_as_of: '2026-11-09T00:00:00.000Z',
    })
    .mockResolvedValueOnce({
      items: [{ ...agent, id: '00000000-0000-0000-0000-000000000002', name: '执行机 B' }],
      next_cursor: null,
      scope_version: 1,
      data_as_of: '2026-11-09T00:00:00.000Z',
    })
  await start()
  await click('下一页')
  expect(environmentApi.list).toHaveBeenLastCalledWith(
    expect.objectContaining({ cursor: 'cursor-next', page_size: 20 }),
    expect.any(AbortSignal),
  )
  expect(w.text()).toContain('执行机 B')
  expect(w.text()).not.toContain('执行机 A')
})
it('unknown create survives close/reopen and retries exact original intent, with only fresh CSRF', async () => {
  const write = vi
    .spyOn(environmentApi, 'write')
    .mockRejectedValueOnce(new AgentApiError(0, 'NETWORK', '未知', true))
    .mockResolvedValueOnce(agent)
  await start()
  await click('登记机器')
  w.findComponent(AgentRegistrationForm).vm.$emit('submit', body)
  await flushPromises()
  expect(write).toHaveBeenCalledTimes(1)
  const first = structuredClone(write.mock.calls[0][0])
  await click('关闭')
  await click('恢复未确认操作')
  await click('重试原请求')
  expect(write.mock.calls[1][0]).toEqual(first)
  expect(write).toHaveBeenCalledTimes(2)
})
it('changed real actor cannot recover or send previous unknown intent', async () => {
  const write = vi
    .spyOn(environmentApi, 'write')
    .mockRejectedValue(new AgentApiError(0, 'NETWORK', '未知', true))
  await start()
  await click('登记机器')
  w.findComponent(AgentRegistrationForm).vm.$emit('submit', body)
  await flushPromises()
  actor = 2
  await click('重试原请求')
  expect(write).toHaveBeenCalledTimes(1)
  expect(document.body.textContent).toContain('身份已变化')
})
it('explicit 403 after unknown cannot discard original intent', async () => {
  const write = vi
    .spyOn(environmentApi, 'write')
    .mockRejectedValueOnce(new AgentApiError(0, 'NETWORK', '未知', true))
    .mockRejectedValueOnce(new AgentApiError(403, 'FORBIDDEN', '无权限'))
  await start()
  await click('登记机器')
  w.findComponent(AgentRegistrationForm).vm.$emit('submit', body)
  await flushPromises()
  await click('重试原请求')
  expect(write.mock.calls[1][0]).toEqual(write.mock.calls[0][0])
  expect(document.body.textContent).toContain('重试原请求')
})
it('confirmed save with failed readback never becomes an unknown write', async () => {
  const write = vi.spyOn(environmentApi, 'write').mockResolvedValue(agent)
  await start()
  await click('登记机器')
  vi.mocked(environmentApi.get).mockRejectedValue(new Error('读取失败'))
  w.findComponent(AgentRegistrationForm).vm.$emit('submit', body)
  await flushPromises()
  expect(write).toHaveBeenCalledTimes(1)
  expect(document.body.textContent).toContain('已保存')
  expect(document.body.textContent).not.toContain('重试原请求')
})
it('query clicks during a write cannot change the write generation or unlock a second intent', async () => {
  let finish!: (v: typeof agent) => void
  vi.spyOn(environmentApi, 'write').mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
  )
  await start()
  await click('登记机器')
  w.findComponent(AgentRegistrationForm).vm.$emit('submit', body)
  await flushPromises()
  await click('查询')
  expect(environmentApi.list).toHaveBeenCalledTimes(1)
  finish(agent)
  await flushPromises()
  expect(document.body.textContent).toContain('已保存')
})
it('editing and revoking use current readback revision and reason, then read back', async () => {
  const write = vi.spyOn(environmentApi, 'write').mockResolvedValue({ ...agent, revision: 2 })
  await start()
  await click('修改')
  w.findComponent(AgentRegistrationForm).vm.$emit('submit', { ...body, name: '更新机器' })
  await flushPromises()
  expect(write.mock.calls[0][0]).toMatchObject({
    id,
    revision: 1,
    operation: 'ENROLL',
    body: { ...body, name: '更新机器' },
  })
  await click('撤销')
  await w.find('textarea[aria-label="撤销原因"]').setValue('机器停用')
  await click('确认撤销')
  expect(write.mock.calls[1][0]).toMatchObject({
    id,
    revision: 1,
    operation: 'REVOKE',
    body: { reason: '机器停用' },
  })
})
it('opens account environment associations for read-only users independently of account APIs', async () => {
  const { bindingApi } = await import('@/api/orbit/environments-bindings')
  vi.spyOn(bindingApi, 'list').mockResolvedValue({
    items: [],
    next_cursor: null,
    data_as_of: '2026-11-09T00:00:00.000000Z',
    scope_version: 1,
  })
  role = 'USER'
  user.permissions = ['environments.read']
  await start()
  await click('账户环境关联')
  expect(bindingApi.list).toHaveBeenCalledTimes(1)
})
it('keeps current operator filter and unavailable related filters explicit', async () => {
  await start()
  await w.find('input[aria-label="当前投手 UUID"]').setValue(id)
  await click('查询')
  expect(environmentApi.list).toHaveBeenLastCalledWith(
    expect.objectContaining({ operator_user_id: id }),
    expect.any(AbortSignal),
  )
  for (const label of ['渠道', '指标配置', '实体类型', '尚无关联事实来源'])
    expect(w.text()).toContain(label)
})
it('pending intent cannot be presented as an unrelated record detail', async () => {
  vi.spyOn(environmentApi, 'write').mockRejectedValue(new AgentApiError(0, 'NETWORK', '未知', true))
  await start()
  await click('登记机器')
  w.findComponent(AgentRegistrationForm).vm.$emit('submit', body)
  await flushPromises()
  await click('关闭')
  await click('详情')
  expect(environmentApi.get).not.toHaveBeenCalled()
  await click('恢复未确认操作')
  expect(document.body.textContent).toContain('重试原请求')
})
it('detail dialog constrains its actual inline width to the viewport instead of a fixed 760px', async () => {
  await start()
  await click('详情')
  const dialog = document.querySelector<HTMLElement>('.el-dialog')!
  expect(dialog.style.getPropertyValue('--el-dialog-width')).toBe('min(760px, calc(100vw - 24px))')
})
