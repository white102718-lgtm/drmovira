import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElButton } from 'element-plus'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import Panel from '@/views/orbit/environments/ProfileBindingsPanel.vue'
import { bindingApi } from '@/api/orbit/environments-bindings'
import { environmentApi, AgentApiError } from '@/api/orbit/environments'
const id = '00000000-0000-0000-0000-000000000001'
const body = {
  account_id: id,
  agent_id: id,
  profile_external_id: 'Profile-001',
  ownership: { owner_user_id: id, owner_team_id: id },
}
const row = { ...body, id, revision: 2, identity_state: 'UNKNOWN' as const, verified_at: null }
let w: VueWrapper,
  actor = 1
beforeEach(() => {
  actor = 1
  vi.spyOn(environmentApi, 'capabilities').mockImplementation(async (operation) => ({
    actor_id: actor,
    tenant_id: id,
    data_role: 'SUPER_ADMIN',
    csrf_token: operation === 'READ' ? null : 'abcdefghijklmnop',
  }))
  vi.spyOn(bindingApi, 'list').mockResolvedValue({
    items: [row],
    next_cursor: null,
    data_as_of: '2026-11-09T00:00:00.000000Z',
    scope_version: 1,
  })
  vi.spyOn(bindingApi, 'get').mockResolvedValue(row)
})
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function start(props = {}) {
  w = mount(Panel, {
    props: { modelValue: true, canRead: true, canWrite: true, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  await flushPromises()
}
async function click(label: string) {
  const button = w.findAllComponents(ElButton).find((b) => b.text() === label)
  expect(button, label).toBeTruthy()
  await button!.trigger('click')
  await flushPromises()
}
async function input(label: string, value: string) {
  const element = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(
    `[aria-label="${label}"]`,
  )!
  expect(element, label).toBeTruthy()
  element.value = value
  element.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
async function fill() {
  for (const [label, value] of [
    ['账户 ID', id],
    ['Agent ID', id],
    ['Profile ID', 'Profile-001'],
    ['归属用户 ID', id],
    ['归属团队 ID', id],
  ])
    await input(label, value)
}
it('lists original relationship fields without requiring accounts.read or fetching account directories', async () => {
  const fetch = vi.spyOn(globalThis, 'fetch')
  await start({ canWrite: false })
  expect(w.text()).toContain('Profile-001')
  expect(w.text()).toContain('未验证')
  expect(fetch).not.toHaveBeenCalled()
  expect(w.findAllComponents(ElButton).some((b) => b.text() === '新增关联')).toBe(false)
})
it('enroll-only administrator can register all original fields and skips readback without read permission', async () => {
  const write = vi.spyOn(bindingApi, 'write').mockResolvedValue({ ...row, revision: 1 })
  await start({ canRead: false })
  await click('新增关联')
  await fill()
  await click('保存关联')
  expect(write.mock.calls[0][0]).toMatchObject({ operation: 'SAVE', body })
  expect(bindingApi.list).not.toHaveBeenCalled()
  expect(bindingApi.get).not.toHaveBeenCalled()
  expect(w.text()).toContain('已保存')
})
it('unknown association preserves body/key/CAS through close and reopen then retries explicitly', async () => {
  const write = vi
    .spyOn(bindingApi, 'write')
    .mockRejectedValueOnce(new AgentApiError(0, 'NETWORK', '未知', true))
    .mockResolvedValueOnce(row)
  await start()
  await click('编辑关联')
  await click('保存关联')
  const original = structuredClone(write.mock.calls[0][0])
  await click('关闭操作')
  await click('恢复未确认关联')
  await click('重试原关联请求')
  expect(write.mock.calls[1][0]).toEqual(original)
})
it('different actor cannot replay association intent', async () => {
  const write = vi
    .spyOn(bindingApi, 'write')
    .mockRejectedValue(new AgentApiError(0, 'NETWORK', '未知', true))
  await start()
  await click('编辑关联')
  await click('保存关联')
  actor = 2
  await click('重试原关联请求')
  expect(write).toHaveBeenCalledTimes(1)
  expect(w.text()).toContain('身份已变化')
})
it('unbind sends reason and exact revision then verifies disappeared relation', async () => {
  const write = vi
    .spyOn(bindingApi, 'write')
    .mockResolvedValue({ id, revision: 3, unbound_at: '2026-11-09T00:00:00.000000Z' })
  await start()
  await click('解绑')
  vi.mocked(bindingApi.get).mockRejectedValue(new AgentApiError(404, 'NOT_FOUND', '不存在'))
  await input('解绑原因', '停止使用')
  await click('确认解绑')
  expect(write.mock.calls[0][0]).toMatchObject({
    operation: 'UNBIND',
    id,
    revision: 2,
    body: { reason: '停止使用' },
  })
  expect(w.text()).toContain('已解绑')
})
it('unknown association survives outer drawer close/reopen and denied retries', async () => {
  const write = vi
    .spyOn(bindingApi, 'write')
    .mockRejectedValueOnce(new AgentApiError(0, 'NETWORK', '未知', true))
    .mockRejectedValueOnce(new AgentApiError(403, 'FORBIDDEN', '拒绝'))
  await start()
  await click('编辑关联')
  await click('保存关联')
  const original = structuredClone(write.mock.calls[0][0])
  await w.setProps({ modelValue: false })
  await flushPromises()
  await w.setProps({ modelValue: true })
  await flushPromises()
  await click('恢复未确认关联')
  await click('重试原关联请求')
  expect(write.mock.calls[1][0]).toEqual(original)
  expect(document.body.textContent).toContain('重试原关联请求')
})
it('permission removal hides pending content; restoring same permission requires explicit recovery', async () => {
  const write = vi
    .spyOn(bindingApi, 'write')
    .mockRejectedValue(new AgentApiError(0, 'NETWORK', '未知', true))
  await start()
  await click('编辑关联')
  await click('保存关联')
  await w.setProps({ canWrite: false })
  await flushPromises()
  expect(
    w.findAllComponents(ElButton).some((b) => b.text() === '重试原关联请求' && b.isVisible()),
  ).toBe(false)
  expect(write).toHaveBeenCalledTimes(1)
  await w.setProps({ canWrite: true })
  await flushPromises()
  await click('恢复未确认关联')
  expect(write).toHaveBeenCalledTimes(1)
})
it('pending association prevents opening another detail under the original retry button', async () => {
  vi.spyOn(bindingApi, 'write').mockRejectedValue(new AgentApiError(0, 'NETWORK', '未知', true))
  await start()
  await click('编辑关联')
  await click('保存关联')
  await click('关闭操作')
  await click('关联详情')
  expect(bindingApi.get).toHaveBeenCalledTimes(1)
})
