import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AuthLogin from '@/views/orbit/auth/Login.vue'
import { captureAuthEntry, takeAuthEntry } from '@/api/orbit/auth-entry'

const values = vi.hoisted(() => ({
  route: { path: '/invite', query: {} },
  replace: vi.fn(),
  start: vi.fn(),
  finish: vi.fn(),
  providers: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => values.route,
  useRouter: () => ({ replace: values.replace }),
}))
vi.mock('@/store/modules/user', () => ({
  default: () => ({ token: '', roles: [], permissions: [] }),
}))
vi.mock('@/api/orbit/authentication', async (original) => ({
  ...(await original<typeof import('@/api/orbit/authentication')>()),
  startEnterpriseLogin: values.start,
  finishEnterpriseLogin: values.finish,
  loginProviders: values.providers,
}))
const wrappers: ReturnType<typeof mount>[] = []
function entry(path: string, hash = '', search = '') {
  captureAuthEntry(
    { pathname: path, hash, search } as Location,
    { replaceState: vi.fn() } as unknown as History,
  )
}
function render() {
  const wrapper = mount(AuthLogin, {
    global: { plugins: [ElementPlus], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  values.route.path = '/invite'
  values.route.query = {}
  takeAuthEntry()
})
afterEach(() => {
  wrappers.forEach((wrapper) => wrapper.unmount())
  wrappers.length = 0
  vi.resetAllMocks()
  vi.unstubAllGlobals()
  takeAuthEntry()
})
describe('公开认证页面', () => {
  it('合法邀请在首屏启用操作，凭据仅传给授权接口', async () => {
    const token = 'i'.repeat(43)
    entry('/invite', '#' + token)
    values.start.mockRejectedValue(new Error('测试服务暂不可用'))
    const wrapper = render()
    await flushPromises()
    const button = wrapper.findAll('button').find((item) => item.text() === '验证身份并接受邀请')!
    expect(button.attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).not.toContain(token)
    await button.trigger('click')
    await flushPromises()
    expect(values.start).toHaveBeenCalledWith('/index', undefined, token)
    expect(wrapper.text()).toContain('测试服务暂不可用')
  })
  it('没有邀请凭据时不发送请求并提供重新打开指引', async () => {
    const wrapper = render()
    await flushPromises()
    expect(wrapper.text()).toContain('邀请凭据缺失或格式无效')
    expect(
      wrapper
        .findAll('button')
        .find((item) => item.text() === '验证身份并接受邀请')
        ?.attributes('disabled'),
    ).toBeDefined()
    expect(values.start).not.toHaveBeenCalled()
  })
  it('离开回调页面后迟到结果不能把用户强制跳回原目标', async () => {
    values.route.path = '/auth/callback'
    entry('/auth/callback', '', '?state=s&code=c')
    let finish!: (value: string) => void
    values.finish.mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const wrapper = render()
    await flushPromises()
    wrapper.unmount()
    finish('/index')
    await flushPromises()
    expect(values.replace).not.toHaveBeenCalled()
  })
  it('离开邀请页面后迟到的授权地址不能触发外部跳转', async () => {
    entry('/invite', '#' + 'i'.repeat(43))
    let complete!: (value: string) => void
    values.start.mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve
        }),
    )
    const assign = vi.fn()
    const original = window
    vi.stubGlobal(
      'window',
      new Proxy(original, {
        get(target, key, receiver) {
          if (key === 'location') return { assign }
          return Reflect.get(target, key, receiver)
        },
      }),
    )
    const wrapper = render()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((item) => item.text() === '验证身份并接受邀请')!
      .trigger('click')
    wrapper.unmount()
    complete('https://idp.example/authorize')
    await flushPromises()
    expect(assign).not.toHaveBeenCalled()
  })
})
