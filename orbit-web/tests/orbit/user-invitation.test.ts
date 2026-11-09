import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import UserInvitation from '@/views/orbit/system/users/UserInvitation.vue'
import { UserRequestError } from '@/api/orbit/users'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  invitationStatus: vi.fn(),
  capabilities: vi.fn(),
  invite: vi.fn(),
}))
vi.mock('@/api/orbit/users', async (original) => ({
  ...(await original<typeof import('@/api/orbit/users')>()),
  userApi: api,
}))
const person = {
  id: 'fixture-user',
  revision: 7,
  display_name: '邀请验证人员',
  email: 'invite@fixture.example.org',
}
const ready = { can_invite: true, blocked_reason: null, invitation: null }
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  api.get.mockResolvedValue(person)
  api.invitationStatus.mockResolvedValue(ready)
  api.capabilities.mockResolvedValue({ csrf_token: 'fixture-csrf' })
})
afterEach(() => {
  wrappers.forEach((wrapper) => wrapper.unmount())
  wrappers.length = 0
  document.body.innerHTML = ''
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})
async function open() {
  const wrapper = mount(UserInvitation, {
    attachTo: document.body,
    global: { plugins: [ElementPlus] },
  })
  wrappers.push(wrapper)
  await wrapper.vm.open(person)
  await flushPromises()
  return wrapper
}
function button(wrapper: ReturnType<typeof mount>, text: string) {
  const result = wrapper.findAll('button').find((item) => item.text() === text)
  if (!result) throw new Error(`未找到按钮：${text}`)
  return result
}
describe('人员邀请状态与写入意图', () => {
  it('配置不足时显示真实原因，不能提交', async () => {
    api.invitationStatus.mockResolvedValue({
      ...ready,
      can_invite: false,
      blocked_reason: '请先配置通知渠道',
    })
    const wrapper = await open()
    expect(wrapper.text()).toContain('请先配置通知渠道')
    expect(button(wrapper, '发送邀请').attributes('disabled')).toBeDefined()
    expect(api.invite).not.toHaveBeenCalled()
  })
  it('响应丢失后保持原版本和幂等键，成功只提示排队', async () => {
    api.invite
      .mockRejectedValueOnce(new Error('网络中断'))
      .mockResolvedValueOnce({ state: 'INVITATION_QUEUED' })
    const wrapper = await open()
    await button(wrapper, '发送邀请').trigger('click')
    await flushPromises()
    await button(wrapper, '刷新状态').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('请先重试本次邀请')
    await button(wrapper, '重试本次邀请').trigger('click')
    await flushPromises()
    expect(api.invite.mock.calls[0]).toEqual(api.invite.mock.calls[1])
    expect(api.invite.mock.calls[0].slice(0, 3)).toEqual(['fixture-user', 7, 'fixture-csrf'])
    expect(wrapper.text()).toContain('邀请已排队，尚未确认通知渠道接收')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
  it('明确版本冲突后允许刷新，不显示已发送成功', async () => {
    api.invite.mockRejectedValueOnce(new UserRequestError('人员版本已变化', 409))
    const wrapper = await open()
    await button(wrapper, '发送邀请').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('人员版本已变化')
    api.get.mockResolvedValue({ ...person, revision: 8 })
    await button(wrapper, '刷新状态').trigger('click')
    await flushPromises()
    api.invite.mockResolvedValue({ state: 'INVITATION_QUEUED' })
    await button(wrapper, '发送邀请').trigger('click')
    await flushPromises()
    expect(api.invite.mock.calls[1][1]).toBe(8)
    expect(api.invite.mock.calls[0][3]).not.toBe(api.invite.mock.calls[1][3])
  })
  it('切换人员后延迟返回的数据不能覆盖当前邀请', async () => {
    let finish!: (value: typeof person) => void
    api.get.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const wrapper = mount(UserInvitation, {
      attachTo: document.body,
      global: { plugins: [ElementPlus] },
    })
    wrappers.push(wrapper)
    const first = wrapper.vm.open(person)
    api.get.mockResolvedValue({ ...person, id: 'second', display_name: '当前人员' })
    await wrapper.vm.open({ ...person, id: 'second' })
    await flushPromises()
    finish(person)
    await first
    await flushPromises()
    expect(wrapper.text()).toContain('当前人员')
    expect(wrapper.text()).not.toContain('邀请验证人员')
  })
})
