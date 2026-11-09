/** 认证页面异常交互单测：服务替身只验证UI控制，不代表真实IdP异常验收。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AuthLogin from '@/views/orbit/auth/Login.vue'
import { captureAuthEntry, takeAuthEntry } from '@/api/orbit/auth-entry'

const state = vi.hoisted(() => ({
  route: { path: '/orbit-login', query: {} },
  replace: vi.fn(),
  start: vi.fn(),
  finish: vi.fn(),
  providers: vi.fn(),
  removeToken: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => state.route,
  useRouter: () => ({ replace: state.replace }),
}))
vi.mock('@/store/modules/user', () => ({
  default: () => ({ token: 'existing-account', roles: ['existing-role'], permissions: [] }),
}))
vi.mock('@/utils/auth', () => ({ removeToken: state.removeToken, getToken: () => '' }))
vi.mock('@/api/orbit/authentication', async (original) => ({
  ...(await original<typeof import('@/api/orbit/authentication')>()),
  startEnterpriseLogin: state.start,
  finishEnterpriseLogin: state.finish,
  loginProviders: state.providers,
}))
const wrappers: ReturnType<typeof mount>[] = []
function render() {
  const wrapper = mount(AuthLogin, {
    global: { plugins: [ElementPlus], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  wrappers.push(wrapper)
  return wrapper
}
function button(wrapper: ReturnType<typeof mount>, text: string) {
  const result = wrapper.findAll('button').find((item) => item.text() === text)
  if (!result) throw new Error(`未找到按钮：${text}`)
  return result
}
function callbackEntry() {
  state.route.path = '/auth/callback'
  captureAuthEntry(
    {
      pathname: '/auth/callback',
      hash: '',
      search: '?state=fixture-state&code=fixture-code',
    } as Location,
    { replaceState: vi.fn() } as unknown as History,
  )
}
beforeEach(() => {
  state.route.path = '/orbit-login'
  state.route.query = {}
  takeAuthEntry()
})
afterEach(() => {
  wrappers.forEach((wrapper) => wrapper.unmount())
  wrappers.length = 0
  takeAuthEntry()
  vi.resetAllMocks()
})

describe('认证异常交互，服务替身范围', () => {
  it('没有提供者时明确提示配置缺失且禁用登录', async () => {
    state.providers.mockResolvedValue([])
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('尚未配置企业登录，请联系管理员')
    expect(button(wrapper, '使用企业账号登录').attributes('disabled')).toBeDefined()
    expect(state.start).not.toHaveBeenCalled()
  })
  it('提供者暂不可用时保留错误，重读后恢复单提供者操作', async () => {
    state.providers
      .mockRejectedValueOnce(new Error('登录服务暂不可用，请稍后重试'))
      .mockResolvedValueOnce([{ id: 'provider-a', name: '企业提供者' }])
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('登录服务暂不可用，请稍后重试')
    expect(button(wrapper, '使用企业账号登录').attributes('disabled')).toBeDefined()
    await button(wrapper, '重新读取').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('登录服务暂不可用，请稍后重试')
    expect(button(wrapper, '使用企业账号登录').attributes('disabled')).toBeUndefined()
    expect(state.providers).toHaveBeenCalledTimes(2)
    expect(state.start).not.toHaveBeenCalled()
  })
  it('多个提供者时不擅自选择身份来源', async () => {
    state.providers.mockResolvedValue([
      { id: 'provider-a', name: '提供者一' },
      { id: 'provider-b', name: '提供者二' },
    ])
    const wrapper = render()
    await flushPromises()
    expect(button(wrapper, '使用企业账号登录').attributes('disabled')).toBeDefined()
    expect(state.start).not.toHaveBeenCalled()
  })
  it('发起中重复点击不制造第二次授权事务，限流错误不自动重试', async () => {
    state.providers.mockResolvedValue([{ id: 'provider-a', name: '企业提供者' }])
    let reject!: (error: Error) => void
    state.start.mockImplementation(
      () =>
        new Promise((_resolve, failed) => {
          reject = failed
        }),
    )
    const wrapper = render()
    await flushPromises()
    await button(wrapper, '使用企业账号登录').trigger('click')
    await button(wrapper, '使用企业账号登录').trigger('click')
    expect(state.start).toHaveBeenCalledTimes(1)
    reject(new Error('登录请求过于频繁，请稍后重试'))
    await flushPromises()
    expect(wrapper.text()).toContain('登录请求过于频繁，请稍后重试')
    expect(state.start).toHaveBeenCalledTimes(1)
    expect(state.removeToken).not.toHaveBeenCalled()
  })
  it('回调拒绝后不重放授权码，也不清除尚未替换的原账号', async () => {
    callbackEntry()
    state.finish.mockRejectedValue(new Error('邀请已过期，请重新获取邀请'))
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('邀请已过期，请重新获取邀请')
    expect(wrapper.text()).toContain('本次回调不能重复使用')
    expect(wrapper.text()).not.toContain('fixture-code')
    expect(state.finish).toHaveBeenCalledTimes(1)
    expect(state.removeToken).not.toHaveBeenCalled()
    expect(state.replace).not.toHaveBeenCalled()
    await button(wrapper, '重新发起登录').trigger('click')
    await flushPromises()
    expect(state.replace).toHaveBeenCalledWith('/orbit-login')
    expect(state.finish).toHaveBeenCalledTimes(1)
  })
  it('刷新丢失一次性回调参数时指引重新登录，不发送空回调', async () => {
    state.route.path = '/auth/callback'
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('登录回调参数缺失，请重新发起登录')
    expect(state.finish).not.toHaveBeenCalled()
    expect(state.removeToken).not.toHaveBeenCalled()
  })
})
