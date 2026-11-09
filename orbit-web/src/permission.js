import router from './router'
import { ElMessage } from 'element-plus'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { getToken, removeToken } from '@/utils/auth'
import { isHttp, isPathMatch } from '@/utils/validate'
import { isRelogin } from '@/utils/request'
import useUserStore from '@/store/modules/user'
import useLockStore from '@/store/modules/lock'
import useSettingsStore from '@/store/modules/settings'
import usePermissionStore from '@/store/modules/permission'
import {
  cookieSessionActive,
  probeCookieSession,
  clearCookieSession,
} from '@/api/orbit/authentication'

NProgress.configure({ showSpinner: false })

const whiteList = ['/login', '/register']

const isWhiteList = (path) => {
  return whiteList.some((pattern) => isPathMatch(pattern, path))
}

router.beforeEach(async (to, from) => {
  NProgress.start()
  if (['/orbit-login', '/invite', '/auth/callback'].includes(to.path)) return true
  let cookieAuthenticated = cookieSessionActive()
  if (!getToken() && !cookieAuthenticated && !isWhiteList(to.path)) {
    try {
      cookieAuthenticated = Boolean(await probeCookieSession())
    } catch {
      NProgress.done()
      return '/orbit-login'
    }
  }
  if (getToken() || cookieAuthenticated) {
    to.meta.title && useSettingsStore().setTitle(to.meta.title)
    const isLock = useLockStore().isLock
    if (to.path === '/login') {
      NProgress.done()
      return { path: '/' }
    }
    if (isWhiteList(to.path)) {
      return true
    }
    if (isLock && to.path !== '/lock') {
      NProgress.done()
      return { path: '/lock' }
    }
    if (!isLock && to.path === '/lock') {
      NProgress.done()
      return { path: '/' }
    }
    if (useUserStore().roles.length === 0) {
      isRelogin.show = true
      try {
        // 拉取user_info信息
        await useUserStore().getInfo()
        isRelogin.show = false
        // 根据roles权限生成可访问的路由
        const accessRoutes = await usePermissionStore().generateRoutes()
        accessRoutes.forEach((route) => {
          if (!isHttp(route.path)) {
            router.addRoute(route)
          }
        })
        // 重新导航到目标路由，确保动态路由已注册
        return { ...to, replace: true }
      } catch (err) {
        // 过期会话的注销也可能返回401；仍须清除本机旧身份并完成导航，不能留在空白页。
        try {
          await useUserStore().logOut()
        } catch {
          // 这只清理已读取失败的本机身份，不声称服务端注销已确认成功。
        } finally {
          const staleUser = useUserStore()
          staleUser.token = ''
          staleUser.id = ''
          staleUser.name = ''
          staleUser.nickName = ''
          staleUser.avatar = ''
          staleUser.roles = []
          staleUser.permissions = []
          removeToken()
          clearCookieSession()
          isRelogin.show = false
          NProgress.done()
        }
        ElMessage.error(err)
        return { path: '/login', query: { redirect: to.fullPath } }
      }
    }
    return true
  } else {
    // 没有token
    if (isWhiteList(to.path)) {
      // 在免登录白名单，直接进入
      return true
    }
    NProgress.done()
    return `/login?redirect=${to.fullPath}` // 否则全部重定向到登录页
  }
})

router.afterEach(() => {
  NProgress.done()
})
