import type { RouteRecordStringComponent } from '@vben/types';

import { backendClient } from '#/api/request';

/**
 * 后端 MenuController /menus/ 返回的用户菜单路由节点（UserMenuRoute DTO）
 * context-path=/api，故完整路径为 GET /api/menus/
 *
 * 返回字段由后端 toUserRoute(Menu) 生成，见：
 *   adpulse-power-system/.../menu/service/MenuService.java#toUserRoute
 */
export interface UserMenuRouteNode {
  /** 菜单ID（字符串化的 Long），字段名带下划线 */
  _id: string;
  /** 父级ID，根节点为空字符串 */
  pid: string;
  /** 路由 name，对应后端 menuCode，稳定唯一 */
  name: string;
  /** 路由 path，对应后端 routePath 或由 menuCode 生成 */
  path: string;
  /** 组件：BasicLayout / IFrameView / views 相对路径（已补前置斜杠） */
  component?: string;
  /** 权限标识，对应后端 permissionCode，空串表示无 */
  authCode?: string;
  /** 节点类型：catalog=目录(menuType=1) / menu=菜单(menuType=2) */
  type?: 'catalog' | 'menu' | string;
  /** Vben 动态路由元数据 */
  meta?: {
    /** 菜单标题，中文 */
    title?: string;
    /** 图标名，例如 carbon:dashboard */
    icon?: string;
    /** 排序权重，数字越小越靠前 */
    order?: number;
    /** 是否在侧边栏隐藏：true=隐藏（路由仍可直接访问） */
    hideInMenu?: boolean;
    /** 是否开启 keep-alive 缓存 */
    keepAlive?: boolean;
    /** 外链 URL（非外链时为 null / undefined） */
    link?: string;
  };
  /** 子节点 */
  children?: UserMenuRouteNode[];
}

/**
 * 将后端 UserMenuRoute 节点映射为 vben 路由组件可消费的 RouteRecordStringComponent
 *
 * 字段对照表：
 *   后端 (UserMenuRouteNode)   →   前端 (RouteRecordStringComponent)
 *   name                       →   name（稳定路由key，直接使用）
 *   path                       →   path
 *   component                  →   component
 *   authCode                   →   meta.permissions[0]（若有值）
 *   meta.title                 →   meta.title
 *   meta.icon                  →   meta.icon
 *   meta.order                 →   meta.order
 *   meta.hideInMenu            →   meta.hideInMenu
 *   meta.keepAlive             →   meta.keepAlive
 *   meta.link                  →   meta.link（若有值，isLink=true）
 *   children                   →   children（递归转换）
 */
function convertUserMenuRouteToRoute(
  nodes: UserMenuRouteNode[],
): RouteRecordStringComponent[] {
  return nodes.map<RouteRecordStringComponent>((n) => {
    const children = n.children ? convertUserMenuRouteToRoute(n.children) : [];
    const perms: string[] = [];
    if (n.authCode) perms.push(n.authCode);

    const link = n.meta?.link;
    const isLink = Boolean(link && link.trim().length > 0);

    return {
      name: n.name,
      path: n.path ?? '/',
      component: n.component ?? '',
      meta: {
        title: n.meta?.title ?? n.name,
        icon: n.meta?.icon,
        order: n.meta?.order,
        hideInMenu: n.meta?.hideInMenu,
        keepAlive: n.meta?.keepAlive,
        link: isLink ? link : undefined,
        isLink,
        permissions: perms.length ? perms : undefined,
      },
      children: children.length ? children : undefined,
    } as RouteRecordStringComponent;
  });
}

/**
 * 获取用户所有菜单（已转换为 vben 可消费的路由结构）
 *
 * 后端：GET /menus/ → ApiResponse<List<UserMenuRoute>>
 * backendClient 已配置 responseReturn='data'，会自动提取 ApiResponse.data 字段。
 * defaultResponseInterceptor 判 code===0||200 为成功并取 data。
 */
export async function getAllMenusApi() {
  const raw = await backendClient.get<UserMenuRouteNode[]>('/menus/');
  // 兼容：若后端后续返回外层包装或空值，做一次兜底规范化
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray((raw as any)?.data)
      ? (raw as any).data
      : [];
  return convertUserMenuRouteToRoute(list) as RouteRecordStringComponent[];
}

// ---------- 旧接口兼容（菜单管理页可能还在用，保留但标记） ----------
// 下面 BackendMenuNode / convertBackendMenuToRoute 仅用于 /menus/tree
// 接口（菜单管理后台页面），与当前用户菜单无关。若后续 tree 也改 DTO，
// 可以按 UserMenuRoute 模式重构。

/**
 * 后端 /menus/tree 返回的菜单权限树原始字段（管理后台页面使用）
 *
 * @deprecated 仅 /menus/tree 仍使用；若后端统一迁移为 UserMenuRoute 可删除。
 */
export interface BackendMenuNode {
  id: number | string;
  parentId?: number | string | null;
  /** 菜单类型：M=目录/菜单分组，C=菜单/页面，F=按钮权限 */
  menuType: 'M' | 'C' | 'F' | string;
  /** 唯一业务编码，建议和 menuName 稳定对应 */
  menuCode?: string;
  /** 菜单显示名称，中文 */
  menuName: string;
  /** 路由 path（仅目录和菜单项非空，按钮可空） */
  routePath?: string;
  /** 前端组件路径，例如 /dashboard/ad-manager 或 BasicLayout */
  component?: string;
  /** 图标名，例如 carbon:dashboard */
  icon?: string;
  /** 按钮/页面级别权限码，前端 v-auth 使用 */
  permissionCode?: string;
  /** 菜单是否在侧边栏显示：1=显示 0=隐藏（路由仍可直接访问） */
  visible?: 0 | 1 | boolean;
  /** 是否开启 keep-alive：1=缓存 0=不缓存 */
  cacheable?: 0 | 1 | boolean;
  /** 是否外链：1=外链 0=内部路由 */
  externalLink?: 0 | 1 | boolean;
  /** 排序权重，数字越小越靠前 */
  sortOrder?: number;
  /** 子节点 */
  children?: BackendMenuNode[];
}

/**
 * 将后端菜单字段映射为 vben 路由组件可消费的 RouteRecordStringComponent
 * （仅用于 /menus/tree 管理后台页面，动态菜单使用 convertUserMenuRouteToRoute）
 *
 * @deprecated 仅 /menus/tree 仍使用
 */
function convertBackendMenuToRoute(
  nodes: BackendMenuNode[],
): RouteRecordStringComponent[] {
  return nodes
    .filter((n) => n.menuType === 'M' || n.menuType === 'C')
    .map<RouteRecordStringComponent>((n) => {
      const children = n.children ? convertBackendMenuToRoute(n.children) : [];
      const perms: string[] = [];
      if (n.permissionCode) perms.push(n.permissionCode);
      // F 节点兼容：若后端后续补了按钮权限，自动合并到父级 meta.permissions
      n.children
        ?.filter((c) => c.menuType === 'F' && c.permissionCode)
        .forEach((c) => perms.push(c.permissionCode!));

      // 唯一 name：优先 menuCode，其次 routePath，最后 menuName
      const name = (n.menuCode || n.routePath || n.menuName).trim();
      // 可见性：后端 1=显示/0=隐藏 → 前端 hideInMenu = !visible
      const hideInMenu = n.visible === 0 || n.visible === false;
      const keepAlive = n.cacheable === 1 || n.cacheable === true;
      const isLink = n.externalLink === 1 || n.externalLink === true;

      return {
        name,
        path: n.routePath ?? '/',
        component: n.component ?? '',
        meta: {
          title: n.menuName,
          icon: n.icon,
          hideInMenu,
          keepAlive,
          isLink,
          permissions: perms.length ? perms : undefined,
        },
        children: children.length ? children : undefined,
      } as RouteRecordStringComponent;
    });
}

