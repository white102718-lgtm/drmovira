import {
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router';

import { resetStaticRoutes } from '@vben/utils';

import { createRouterGuard } from './guard';
import { routes } from './routes';

/**
 *  @zh_CN 创建vue-router实例
 */
const router = createRouter({
  history:
    import.meta.env.VITE_ROUTER_HISTORY === 'hash'
      ? createWebHashHistory(import.meta.env.VITE_BASE)
      : createWebHistory(import.meta.env.VITE_BASE),
  // 应该添加到路由的初始路由列表。
  routes,
  scrollBehavior: (to, _from, savedPosition) => {
    if (savedPosition) {
      return savedPosition;
    }
    return to.hash ? { behavior: 'smooth', el: to.hash } : { left: 0, top: 0 };
  },
  // 是否应该禁止尾部斜杠。
  // strict: true,
});

const CHUNK_LOAD_ERROR_PATTERN =
  /failed to fetch dynamically imported module|importing a module script failed|unable to preload css/i;
const CHUNK_RELOAD_COOLDOWN = 30_000;
const CHUNK_RELOAD_TIMESTAMP_KEY = 'adpulse:chunk-reload-timestamp';

/**
 * 生产发布会替换带 hash 的静态资源。旧标签页在切换到尚未加载过的页面时，
 * 可能继续请求已被清理的旧 chunk；此处仅自动刷新一次以加载最新入口文件，
 * 并通过短暂冷却时间避免部署窗口内持续刷新。
 */
router.onError((error, to) => {
  const errorMessage = error instanceof Error ? error.message : String(error);
  if (!CHUNK_LOAD_ERROR_PATTERN.test(errorMessage)) return;

  const now = Date.now();
  const lastReloadAt = Number(
    window.sessionStorage.getItem(CHUNK_RELOAD_TIMESTAMP_KEY) ?? 0,
  );

  if (now - lastReloadAt < CHUNK_RELOAD_COOLDOWN) return;

  window.sessionStorage.setItem(CHUNK_RELOAD_TIMESTAMP_KEY, String(now));
  // 导航失败时浏览器仍停留在原路由，刷新目标地址才能保留用户本次点击的菜单。
  window.location.replace(router.resolve(to).href);
});

const resetRoutes = () => resetStaticRoutes(router, routes);

// 创建路由守卫
createRouterGuard(router);

export { resetRoutes, router };
