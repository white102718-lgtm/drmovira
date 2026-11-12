/** 原路由守卫过期会话回归；注销失败不能使导航中断并残留旧身份。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Route = { path: string; fullPath: string; meta: { title?: string } }
const state = vi.hoisted(() => ({
  guard: null as null | ((to: Route, from: Route) => Promise<unknown>),
  getInfo: vi.fn(),
  getToken: vi.fn(),
  probe: vi.fn(),
  logOut: vi.fn(),
  generate: vi.fn(),
  removeToken: vi.fn(),
  clearCookie: vi.fn(),
  done: vi.fn(),
  error: vi.fn(),
  relogin: { show: false },
  user: {
    token: 'stale-token',
    id: 'old-id',
    name: '旧用户',
    nickName: '旧昵称',
    avatar: 'old-avatar',
    roles: [] as string[],
    permissions: ['old.permission'],
  },
}))
vi.mock('@/router', () => ({
  default: {
    beforeEach: (guard: typeof state.guard) => {
      state.guard = guard
    },
    afterEach: vi.fn(),
    addRoute: vi.fn(),
  },
}))
vi.mock('element-plus', () => ({ ElMessage: { error: state.error } }))
vi.mock('nprogress', () => ({ default: { configure: vi.fn(), start: vi.fn(), done: state.done } }))
vi.mock('@/utils/auth', () => ({ getToken: state.getToken, removeToken: state.removeToken }))
vi.mock('@/utils/validate', () => ({
  isHttp: () => false,
  isPathMatch: (a: string, b: string) => a === b,
}))
vi.mock('@/utils/request', () => ({ isRelogin: state.relogin }))
vi.mock('@/store/modules/user', () => ({
  default: () => Object.assign(state.user, { getInfo: state.getInfo, logOut: state.logOut }),
}))
vi.mock('@/store/modules/lock', () => ({ default: () => ({ isLock: false }) }))
vi.mock('@/store/modules/settings', () => ({ default: () => ({ setTitle: vi.fn() }) }))
vi.mock('@/store/modules/permission', () => ({
  default: () => ({ generateRoutes: state.generate }),
}))
vi.mock('@/api/orbit/authentication', () => ({
  cookieSessionActive: () => false,
  probeCookieSession: state.probe,
  clearCookieSession: state.clearCookie,
}))

const route = {
  path: '/orbit/rules/definitions',
  fullPath: '/orbit/rules/definitions?status=DRAFT',
  meta: {},
}
beforeEach(async () => {
  vi.clearAllMocks()
  vi.resetModules()
  Object.assign(state.user, {
    token: 'stale-token',
    id: 'old-id',
    name: '旧用户',
    nickName: '旧昵称',
    avatar: 'old-avatar',
    roles: [],
    permissions: ['old.permission'],
  })
  state.getToken.mockReturnValue('stale-token')
  state.getInfo.mockRejectedValue(Object.assign(new Error('会话已过期'), { status: 401 }))
  state.logOut.mockResolvedValue(undefined)
  state.generate.mockResolvedValue([])
  state.relogin.show = false
  await import('@/permission')
})

describe('过期身份路由恢复', () => {
  it.each(['success', 'rejected'] as const)(
    '注销%s仍进入登录并保留安全内部返回地址',
    async (mode) => {
      if (mode === 'rejected') state.logOut.mockRejectedValue(new Error('注销也返回401'))
      expect(await state.guard!(route, route)).toEqual({
        path: '/login',
        query: { redirect: route.fullPath },
      })
      expect(state.removeToken).toHaveBeenCalledOnce()
      expect(state.clearCookie).toHaveBeenCalledOnce()
      expect(state.user).toMatchObject({
        token: '',
        id: '',
        name: '',
        nickName: '',
        avatar: '',
        roles: [],
        permissions: [],
      })
      expect(state.relogin.show).toBe(false)
      expect(state.done).toHaveBeenCalled()
      expect(state.generate).not.toHaveBeenCalled()
    },
  )
  it('身份读取成功保留会话并继续原动态菜单导航', async () => {
    state.getInfo.mockResolvedValue(undefined)
    expect(await state.guard!(route, route)).toEqual({ ...route, replace: true })
    expect(state.generate).toHaveBeenCalledOnce()
    expect(state.logOut).not.toHaveBeenCalled()
    expect(state.removeToken).not.toHaveBeenCalled()
    expect(state.clearCookie).not.toHaveBeenCalled()
    expect(state.user.name).toBe('旧用户')
  })
})

it.each([502, 503, 504, 403])('资料读取HTTP%s不会注销真实会话', async (status) => {
  state.getToken.mockReturnValue('stale-token')
  state.getInfo.mockRejectedValue(Object.assign(new Error('upstream unavailable'), { response: { status } }))
  expect(await state.guard!(route, route)).toEqual({ path: '/service-unavailable', query: { redirect: route.fullPath }, replace: true })
  expect(state.logOut).not.toHaveBeenCalled()
  expect(state.removeToken).not.toHaveBeenCalled()
  expect(state.clearCookie).not.toHaveBeenCalled()
  expect(state.user.token).toBe('stale-token')
  expect(state.relogin.show).toBe(false)
})
it('网络中断不清身份，重试成功后继续读取菜单', async () => {
  state.getToken.mockReturnValue('stale-token')
  state.getInfo.mockRejectedValue(new Error('Network Error'))
  await state.guard!(route, route)
  expect(state.logOut).not.toHaveBeenCalled()
  state.getInfo.mockResolvedValue(undefined)
  expect(await state.guard!(route, route)).toEqual({ ...route, replace: true })
})
it('恢复页本身不再发认证请求，避免故障重定向循环', async () => {
  const recovery = {path:'/service-unavailable',fullPath:'/service-unavailable',meta:{}}
  expect(await state.guard!(recovery,route)).toBe(true)
  expect(state.getInfo).not.toHaveBeenCalled()
})
it('菜单读取502也不清登录，且清空不完整角色以确保下次重建路由', async () => {
  state.getInfo.mockImplementation(async () => { state.user.roles = ['admin'] })
  state.generate.mockRejectedValueOnce(Object.assign(new Error('gateway'),{response:{status:502}}))
  await state.guard!(route, route)
  expect(state.logOut).not.toHaveBeenCalled()
  expect(state.user.roles).toEqual([])
  state.generate.mockResolvedValue([])
  expect(await state.guard!(route, route)).toEqual({...route,replace:true})
})

it('Cookie会话探测遇到502保留会话并进入恢复页', async () => {
  state.getToken.mockReturnValue(undefined)
  state.probe.mockRejectedValue(Object.assign(new Error('gateway'), {status:502}))
  expect(await state.guard!(route,route)).toEqual({path:'/service-unavailable',query:{redirect:route.fullPath},replace:true})
  expect(state.clearCookie).not.toHaveBeenCalled()
  expect(state.logOut).not.toHaveBeenCalled()
})
