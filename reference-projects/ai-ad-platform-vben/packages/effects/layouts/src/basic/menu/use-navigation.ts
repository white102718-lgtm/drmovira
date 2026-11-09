import type { RouteRecordNormalized } from 'vue-router';

import { useRouter } from 'vue-router';

import { useTabbarStore } from '@vben/stores';
import { isHttpUrl, openRouteInNewWindow, openWindow } from '@vben/utils';

function useNavigation() {
  const router = useRouter();
  const tabbarStore = useTabbarStore();
  const routeMetaMap = new Map<string, RouteRecordNormalized>();

  // 初始化路由映射
  const initRouteMetaMap = () => {
    const routes = router.getRoutes();
    routes.forEach((route) => {
      routeMetaMap.set(route.path, route);
    });
  };

  initRouteMetaMap();

  // 监听路由变化
  router.afterEach(() => {
    initRouteMetaMap();
  });

  // 检查是否应该在新窗口打开
  const shouldOpenInNewWindow = (path: string): boolean => {
    if (isHttpUrl(path)) {
      return true;
    }
    const route = routeMetaMap.get(path);
    return route?.meta?.openInNewWindow ?? false;
  };

  const navigation = async (path: string) => {
    try {
      const route = routeMetaMap.get(path);
      const { openInNewWindow = false, query = {} } = route?.meta ?? {};

      if (isHttpUrl(path)) {
        openWindow(path, { target: '_blank' });
      } else if (openInNewWindow) {
        openRouteInNewWindow(path);
      } else {
        // 再次进入已打开的页面时沿用标签页的完整地址，避免丢失列表筛选、分页和日期。
        const openedTab = tabbarStore.getTabByKey(path);
        if (openedTab?.fullPath) {
          await router.push(openedTab.fullPath);
          return;
        }
        await router.push({
          path,
          query,
        });
      }
    } catch (error) {
      console.error('Navigation failed:', error);
      throw error;
    }
  };

  const willOpenedByWindow = (path: string) => {
    return shouldOpenInNewWindow(path);
  };

  return { navigation, willOpenedByWindow };
}

export { useNavigation };
