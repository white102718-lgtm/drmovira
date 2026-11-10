import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, { ElButton } from 'element-plus'
import { it, expect, vi, afterEach } from 'vitest'
import Policy from '@/views/orbit/accounts/components/MetaSyncPolicy.vue'
import { metaSyncApi } from '@/api/orbit/meta-sync'
vi.mock('@/store/modules/user', () => ({
  default: () => ({ permissions: ['system.integrations.manage', 'accounts.sync'] }),
}))
afterEach(() => vi.restoreAllMocks())
it('unknown save retains exact request key/body and prevents closing until original retry resolves', async () => {
  const value = {
    profile_id: '00000000-0000-4000-8000-000000000001',
    adapter_version: 'v1',
    scheduler_enabled: false,
    revision: 1,
  }
  vi.spyOn(metaSyncApi, 'settings').mockResolvedValue({
    ...value,
    csrf_token: 'csrf',
    choices: [{ profile_id: value.profile_id, profile_version: 'p1', adapter_version: 'v1' }],
  })
  const save = vi
    .spyOn(metaSyncApi, 'save')
    .mockRejectedValueOnce(new Error('network'))
    .mockResolvedValueOnce({ ...value, revision: 2 })
  const w = mount(Policy, {
    props: { active: true, contextKey: 'one' },
    global: { plugins: [ElementPlus] },
  })
  const button = (label: string) => w.findAllComponents(ElButton).find((b) => b.text() === label)!
  await button('采集设置').trigger('click')
  await flushPromises()
  await button('保存采集设置').trigger('click')
  await flushPromises()
  expect(button('收起采集设置').props('disabled')).toBe(true)
  expect(w.text()).toContain('尚未确认保存结果')
  await button('用原请求重试').trigger('click')
  await flushPromises()
  expect(save.mock.calls[1]).toEqual(save.mock.calls[0])
  expect(w.text()).toContain('采集设置已保存')
  expect(button('收起采集设置').props('disabled')).toBe(false)
  w.unmount()
})

it('独立连接只读写自身设置，切换连接清除旧选择与重试', async () => {
  const first = '00000000-0000-4000-8000-000000000001',
    second = '00000000-0000-4000-8000-000000000002'
  const profile = '00000000-0000-4000-8000-000000000003'
  const settings = vi
    .spyOn(metaSyncApi, 'settings')
    .mockResolvedValue({
      profile_id: profile,
      adapter_version: 'v1',
      scheduler_enabled: false,
      revision: 1,
      csrf_token: 'csrf',
      choices: [{ profile_id: profile, profile_version: 'p1', adapter_version: 'v1' }],
    })
  const save = vi
    .spyOn(metaSyncApi, 'save')
    .mockResolvedValue({
      profile_id: profile,
      adapter_version: 'v1',
      scheduler_enabled: false,
      revision: 2,
    })
  const w = mount(Policy, {
    props: {
      active: true,
      contextKey: 'same-user',
      connectionId: first,
      connectionLabel: 'LOGIN 客户一',
    },
    global: { plugins: [ElementPlus] },
  })
  const button = (label: string) => w.findAllComponents(ElButton).find((b) => b.text() === label)!
  await button('采集设置').trigger('click')
  await flushPromises()
  expect(settings).toHaveBeenLastCalledWith(expect.any(AbortSignal), first)
  expect(w.text()).toContain('LOGIN 客户一')
  await button('保存采集设置').trigger('click')
  await flushPromises()
  expect(save.mock.calls[0][3]).toBe(first)
  await w.setProps({ connectionId: second, connectionLabel: 'BM 客户二' })
  expect(w.text()).not.toContain('采集设置已保存')
  await button('采集设置').trigger('click')
  await flushPromises()
  expect(settings).toHaveBeenLastCalledWith(expect.any(AbortSignal), second)
  w.unmount()
})
