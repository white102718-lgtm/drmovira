import type { Router } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';
import { useAccessStore, useUserStore } from '@vben/stores';
import { startProgress, stopProgress } from '@vben/utils';

import { isFusionDemoMode } from '#/api/fusion/mode';
import {
  canDemoRoute,
  getDemoAccessCodes,
  getDemoRouteNameByPath,
  isDemoManagedRouteName,
} from '#/mock/demo-access';
import {
  clearSelectedDemoRole,
  getDemoRoleAccessToken,
  isDemoRoleAccessToken,
  readSelectedDemoRole,
  toDemoRoleUserInfo,
} from '#/mock/demo-role-preview';
import { accessRoutes, coreRouteNames } from '#/router/routes';
import { useAuthStore } from '#/store/auth';

import { generateAccess } from './access';
import { resolveAuthorizedDefaultPath } from './default-route';

/**
 * 通用守卫配置
 * @param router
 */
function setupCommonGuard(router: Router) {
  // 记录已经加载的页面
  const loadedPaths = new Set<string>();

  router.beforeEach((to) => {
    to.meta.loaded = loadedPaths.has(to.path);

    // 页面加载进度条
    if (!to.meta.loaded && preferences.transition.progress) {
      startProgress();
    }
    return true;
  });

  router.afterEach((to) => {
    // 记录页面是否加载,如果已经加载，后续的页面切换动画等效果不在重复执行
    loadedPaths.add(to.path);

    // 关闭页面加载进度条
    if (preferences.transition.progress) {
      stopProgress();
    }
  });
}

/**
 * 权限访问守卫配置
 * @param router
 */
function setupAccessGuard(router: Router) {
  router.beforeEach(async (to, from) => {
    const accessStore = useAccessStore();
    const userStore = useUserStore();
    const authStore = useAuthStore();

    // 从本地 Demo 切换到真实鉴权时，清理旧演示会话，避免它跳过登录页。
    if (!isFusionDemoMode() && isDemoRoleAccessToken(accessStore.accessToken)) {
      clearSelectedDemoRole();
      accessStore.setAccessToken(null);
      accessStore.setRefreshToken(null);
      accessStore.setAccessCodes([]);
      accessStore.setIsAccessChecked(false);
      userStore.setUserInfo(null);
    }

    // 融合前端演示模式不依赖远程身份和菜单服务。首次进入必须先
    // 选择角色；选中的 Demo 身份只用于本地展示，不能替代生产鉴权。
    if (isFusionDemoMode()) {
      const profile = readSelectedDemoRole();
      if (profile) {
        const demoToken = getDemoRoleAccessToken(profile);
        accessStore.setAccessCodes(getDemoAccessCodes(profile.id));
        if (
          accessStore.accessToken !== demoToken ||
          userStore.userInfo?.userId !== profile.userId
        ) {
          accessStore.setAccessToken(demoToken);
          userStore.setUserInfo(toDemoRoleUserInfo(profile));
          accessStore.setIsAccessChecked(false);
        }
      } else if (isDemoRoleAccessToken(accessStore.accessToken)) {
        // Clears only the old/local Demo session, never a production token.
        accessStore.setAccessToken(null);
        accessStore.setIsAccessChecked(false);
        userStore.setUserInfo(null);
      }
    }
    // 基本路由，这些路由不需要进入权限拦截
    if (coreRouteNames.includes(to.name as string)) {
      if (to.path === LOGIN_PATH && accessStore.accessToken) {
        return decodeURIComponent(
          (to.query?.redirect as string) ||
            userStore.userInfo?.homePath ||
            preferences.app.defaultHomePath,
        );
      }
      return true;
    }

    // A hidden menu is not enough in the local role preview: copied URLs,
    // browser history and stale tabs must not reopen a previous role's page.
    // Unknown paths continue to resolve to the normal 404 fallback.
    if (isFusionDemoMode()) {
      const profile = readSelectedDemoRole();
      // On a hard refresh the dynamic route can still carry a fallback name
      // while its stable path is already known. Prefer the path mapping so an
      // authorized deep link (such as Task Center) is not rejected before the
      // access routes finish being restored.
      const routeName =
        typeof to.name === 'string' ? to.name : undefined;
      const managedRouteName = getDemoRouteNameByPath(to.path) ?? routeName;
      if (
        profile &&
        managedRouteName &&
        (isDemoManagedRouteName(managedRouteName) ||
          Boolean(getDemoRouteNameByPath(to.path))) &&
        !canDemoRoute(profile.id, managedRouteName)
      ) {
        return {
          path: '/forbidden',
          query: { redirect: to.fullPath },
          replace: true,
        };
      }
    }

    // accessToken 检查
    if (!accessStore.accessToken) {
      // 明确声明忽略权限访问权限，则可以访问
      if (to.meta.ignoreAccess) {
        return true;
      }

      // 只进入当前前端自带的登录页，禁止跳转旧 OAuth/IdP 站点。
      return {
        path: LOGIN_PATH,
        query: { redirect: to.fullPath },
        replace: true,
      };
    }

    // 是否已经生成过动态路由
    if (accessStore.isAccessChecked) {
      const preferredPath =
        userStore.userInfo?.homePath || preferences.app.defaultHomePath;
      if (to.path === preferredPath) {
        const authorizedPath = resolveAuthorizedDefaultPath({
          accessibleMenus: accessStore.accessMenus,
          accessibleRoutes: accessStore.accessRoutes,
          preferredPath,
        });
        if (authorizedPath !== preferredPath) {
          return { path: authorizedPath, replace: true };
        }
      }
      return true;
    }

    // 生成路由表
    // 当前登录用户拥有的角色标识列表
    const userInfo = userStore.userInfo || (await authStore.fetchUserInfo());
    const userRoles = userInfo.roles ?? [];

    // 生成菜单和路由
    const { accessibleMenus, accessibleRoutes } = await generateAccess({
      roles: userRoles,
      router,
      // 则会在菜单中显示，但是访问会被重定向到403
      routes: accessRoutes,
    });

    // 保存菜单信息和路由信息
    accessStore.setAccessMenus(accessibleMenus);
    accessStore.setAccessRoutes(accessibleRoutes);
    accessStore.setIsAccessChecked(true);
    const preferredPath = userInfo.homePath || preferences.app.defaultHomePath;
    const requestedRedirect = Array.isArray(from.query.redirect)
      ? from.query.redirect[0]
      : from.query.redirect;
    let redirectPath: string;
    if (requestedRedirect && requestedRedirect !== preferredPath) {
      redirectPath = requestedRedirect;
    } else if (
      requestedRedirect === preferredPath ||
      to.path === preferredPath
    ) {
      redirectPath = resolveAuthorizedDefaultPath({
        accessibleMenus,
        accessibleRoutes,
        preferredPath,
      });
    } else {
      redirectPath = to.fullPath;
    }
    return {
      ...router.resolve(decodeURIComponent(redirectPath)),
      replace: true,
    };
  });
}

/**
 * 项目守卫配置
 * @param router
 */
function createRouterGuard(router: Router) {
  /** 通用 */
  setupCommonGuard(router);
  /** 权限访问 */
  setupAccessGuard(router);
}

export { createRouterGuard };
