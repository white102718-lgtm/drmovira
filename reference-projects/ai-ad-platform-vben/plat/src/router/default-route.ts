import type { MenuRecordRaw, RouteRecordRaw } from '@vben/types';

const FALLBACK_FORBIDDEN_PATH = '/forbidden';
const FALLBACK_WELCOME_PATH = '/welcome';

function isInternalPath(path: unknown): path is string {
  return (
    typeof path === 'string' && path.startsWith('/') && !path.startsWith('//')
  );
}

function hasRoutePath(routes: RouteRecordRaw[], path: string): boolean {
  return routes.some(
    (route) =>
      route.path === path ||
      (route.children?.length ? hasRoutePath(route.children, path) : false),
  );
}

function findFirstInternalMenuPath(menus: MenuRecordRaw[]): string | undefined {
  for (const menu of menus) {
    if (isInternalPath(menu.path)) return menu.path;

    const childPath = menu.children?.length
      ? findFirstInternalMenuPath(menu.children)
      : undefined;
    if (childPath) return childPath;
  }
  return undefined;
}

/**
 * 根据后端授权结果选择登录后的稳定落点，避免未授权首页进入 404。
 */
export function resolveAuthorizedDefaultPath(options: {
  accessibleMenus: MenuRecordRaw[];
  accessibleRoutes: RouteRecordRaw[];
  preferredPath: string;
}): string {
  const { accessibleMenus, accessibleRoutes, preferredPath } = options;

  if (
    isInternalPath(preferredPath) &&
    hasRoutePath(accessibleRoutes, preferredPath)
  ) {
    return preferredPath;
  }

  const firstMenuPath = findFirstInternalMenuPath(accessibleMenus);
  if (firstMenuPath) return firstMenuPath;

  if (hasRoutePath(accessibleRoutes, FALLBACK_WELCOME_PATH)) {
    return FALLBACK_WELCOME_PATH;
  }

  return FALLBACK_FORBIDDEN_PATH;
}
