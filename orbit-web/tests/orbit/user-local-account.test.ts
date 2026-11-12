import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import CreateUser from '@/views/orbit/system/users/CreateUser.vue'
import ResetPassword from '@/views/orbit/system/users/ResetPassword.vue'
import ReferenceSelect from '@/views/orbit/system/users/ReferenceSelect.vue'
import { userApi, type OrbitUser } from '@/api/orbit/users'
vi.mock('vue-router', () => ({ useRouter: () => ({ replace: vi.fn() }) }))
const person: OrbitUser = {
  id: 'person',
  revision: 1,
  display_name: '张三',
  nickname: '投手',
  email: 'person@example.com',
  phone: '13800000000',
  login_account: '13800000000',
  team_name: '团队',
  role_names: ['投手'],
  team_id: 'team',
  role_ids: ['role'],
  data_role: 'USER',
  managed_team_ids: [],
  status: 'ENABLED',
  identity_status: 'LOCAL_ACCOUNT',
}
let wrapper: VueWrapper
beforeEach(() => {
  vi.spyOn(userApi, 'capabilities').mockResolvedValue({
    can_create: true,
    csrf_token: 'test-csrf',
    actor_user_id: 'admin',
    protected_user_ids: ['admin'],
    data_role: 'SUPER_ADMIN',
    managed_team_ids: [],
  })
  vi.spyOn(userApi, 'get').mockResolvedValue(person)
  vi.spyOn(userApi, 'options').mockImplementation(async (query) => ({
    items: [{ id: query.get('kind') === 'TEAM' ? 'team' : 'role', name: '候选' }],
    next_cursor: null,
  }))
})
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})
async function fill(label: string, value: string) {
  const node = [...document.querySelectorAll<HTMLLabelElement>('label')].find(
    (item) => item.textContent?.trim() === label,
  )!
  const input = document.getElementById(node.htmlFor) as HTMLInputElement
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
async function click(label: string) {
  ;[...document.querySelectorAll('button')]
    .find((item) => item.textContent?.trim() === label)!
    .click()
  await flushPromises()
}
it('新增默认开启并设置密码，不要求邀请验证', async () => {
  const create = vi.spyOn(userApi, 'create').mockResolvedValue(person)
  wrapper = mount(CreateUser, { attachTo: document.body, global: { plugins: [ElementPlus] } })
  await (wrapper.vm as unknown as { open: () => Promise<void> }).open()
  await flushPromises()
  expect(document.body.textContent).not.toMatch(/邀请|验证身份/)
  await fill('姓名', '张三')
  await fill('昵称', '投手')
  await fill('邮箱', 'person@example.com')
  await fill('手机号 / 登录账号', '13800000000')
  const selects = wrapper.findAllComponents(ReferenceSelect)
  selects[0].vm.$emit('update:modelValue', 'team')
  selects[1].vm.$emit('update:modelValue', ['role'])
  await flushPromises()
  await fill('登录密码', 'TestPass123!')
  await fill('确认密码', 'WrongPass123!')
  await click('保存人员')
  expect(create).not.toHaveBeenCalled()
  await fill('确认密码', 'TestPass123!')
  await click('保存人员')
  expect(create.mock.calls[0][0]).toMatchObject({
    status: 'ENABLED',
    password: 'TestPass123!',
    phone: '13800000000',
    role_ids: ['role'],
  })
})
it('重置密码确认一致后提交，未知结果重试同一键和正文', async () => {
  const reset = vi
    .spyOn(userApi, 'resetPassword')
    .mockRejectedValueOnce(new Error('网络中断'))
    .mockResolvedValueOnce({ ...person, revision: 2 })
  wrapper = mount(ResetPassword, { attachTo: document.body, global: { plugins: [ElementPlus] } })
  await (wrapper.vm as unknown as { open: (p: OrbitUser) => Promise<void> }).open(person)
  await flushPromises()
  await fill('新密码', 'NewPassword123!')
  await fill('确认新密码', 'Mismatch123!')
  await click('重置并撤销旧会话')
  expect(reset).not.toHaveBeenCalled()
  await fill('确认新密码', 'NewPassword123!')
  await click('重置并撤销旧会话')
  expect(document.body.textContent).toContain('结果未知')
  await click('重试本次重置')
  expect(reset.mock.calls[0]).toEqual(reset.mock.calls[1])
  expect(reset.mock.calls[0].slice(0, 3)).toEqual(['person', 'NewPassword123!', 1])
})
