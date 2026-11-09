import type {
  ComponentRecordType,
  GenerateMenuAndRoutesOptions,
  RouteRecordStringComponent,
} from '@vben/types';

import { generateAccessible } from '@vben/access';
import { preferences } from '@vben/preferences';

import message from 'ant-design-vue/es/message';

import { getAllMenusApi } from '#/api/core/menu';
import { isFusionDemoMode } from '#/api/fusion/mode';
import { BasicLayout, IFrameView } from '#/layouts';
import { $t } from '#/locales';
import { filterDemoMenuTree } from '#/mock/demo-access';
import { readSelectedDemoRole } from '#/mock/demo-role-preview';

import {
  getUnifiedDemoMenus,
  normalizeNestedLayoutComponents,
} from './menu-schema';

const forbiddenComponent = () => import('#/views/_core/fallback/forbidden.vue');

async function generateAccess(options: GenerateMenuAndRoutesOptions) {
  const pageMap: ComponentRecordType = import.meta.glob('../views/**/*.vue');

  const layoutMap: ComponentRecordType = {
    BasicLayout,
    IFrameView,
  };

  return await generateAccessible(preferences.app.accessMode, {
    ...options,
    fetchMenuListAsync: async () => {
      const loadingSubtitle = document.querySelector(
        '#__app-loading__ .loading-subtitle',
      );
      if (loadingSubtitle) {
        loadingSubtitle.textContent = `${$t('common.loadingMenu')}...`;
      } else {
        message.loading({
          content: `${$t('common.loadingMenu')}...`,
          duration: 1.5,
        });
      }

      // 演示模式按本地选择的角色生成菜单；正式环境仍保留后端权限菜单。
      const demoMode = isFusionDemoMode();
      const selectedRole = demoMode ? readSelectedDemoRole() : undefined;
      let backendMenus: RouteRecordStringComponent[];
      if (demoMode) {
        backendMenus = selectedRole
          ? filterDemoMenuTree(getUnifiedDemoMenus(), selectedRole.id)
          : [];
      } else {
        backendMenus = await getAllMenusApi();
      }

      flattenHiddenPageChildRoutes(backendMenus);

      // 任务中心随已打开的页签保留筛选状态；关闭页签时由框架清除组件缓存。
      const taskCenterMenu = findMenuByPath(backendMenus, '/workbench/tasks');
      if (taskCenterMenu) {
        taskCenterMenu.meta = Object.assign(
          taskCenterMenu.meta ?? { title: '任务中心' },
          {
            keepAlive: true,
          },
        );
      }

      // 平台与代理线配置已下线，后端旧菜单仍返回该节点时也不再注册入口。
      removeMenuPath(backendMenus, '/management/platform-config');

      // 数据库迁移尚未执行时，后端可能仍会下发已下线的媒介资源菜单。
      // 在动态菜单入口统一剔除，避免继续注册路由或显示菜单。
      removeMenuEntries(
        backendMenus,
        (menu) =>
          menu.path === '/media-resources/dashboard' ||
          menu.name === 'MediaResourceDashboard' ||
          menu.path === '/media-resources/assignments' ||
          menu.name === 'MediaResourceAssignments',
      );

      // 可见业务菜单必须以角色授权后的结果为准，禁止在前端用兜底菜单扩大权限。
      const homeMenu = backendMenus.find(
        (menu: RouteRecordStringComponent) => menu.path === '/home',
      );

      if (homeMenu?.meta) {
        // 首页是全局稳定落点，必须固定在标签栏首位且不可被关闭或解除固定。
        Object.assign(homeMenu.meta, {
          affixTab: true,
          affixTabOrder: -999,
          keepAlive: true,
          tabClosable: false,
        });
      }

      const hasProfileMenu = hasMenuPath(backendMenus, '/profile');
      if (!hasProfileMenu) {
        backendMenus.push({
          name: 'Profile',
          path: '/profile',
          component: '/profile/index',
          meta: {
            hideInMenu: true,
            title: '个人信息',
          },
        });
      }
      const automatedRuleConfig = findMenuByPath(
        backendMenus,
        '/createAdvertisement/automated-rule-config',
      );
      if (automatedRuleConfig) {
        automatedRuleConfig.meta = Object.assign(
          automatedRuleConfig.meta ?? { title: '规则配置' },
          {
            activePath: '/AutomatedRules',
            hideInTab: true,
          },
        );
      } else {
        backendMenus.push({
          name: 'AutomatedRuleConfig',
          path: '/createAdvertisement/automated-rule-config',
          component: '/createAdvertisement/AutomatedRuleConfig',
          meta: {
            hideInMenu: true,
            hideInTab: true,
            title: '规则配置',
            activePath: '/AutomatedRules',
          },
        });
      }

      const hasDrilldown = hasMenuPath(backendMenus, '/data-report/drilldown');
      if (!hasDrilldown) {
        backendMenus.push({
          name: 'Drilldown',
          path: '/data-report/drilldown',
          component: '/dataReport/Drilldown',
          meta: {
            hideInMenu: true,
            title: '下钻分析',
          },
        });
      }

      ensureLegacyRequirementPitcherRedirect(backendMenus);
      ensureLegacyRequirementDetailRedirect(backendMenus);

      const hasCreateRequirement = hasMenuPath(
        backendMenus,
        '/requirement/create',
      );
      if (!hasCreateRequirement) {
        backendMenus.push({
          name: 'CreateRequirement',
          path: '/requirement/create',
          component: '/requirement/create',
          meta: { hideInMenu: true, title: '新建需求' },
        });
      }

      const hasWorkbenchMaterialTaskCreate = hasMenuPath(
        backendMenus,
        '/workbench/tasks/create-material',
      );
      if (!hasWorkbenchMaterialTaskCreate) {
        backendMenus.push({
          name: 'WorkbenchMaterialTaskCreate',
          path: '/workbench/tasks/create-material',
          component: '/requirement/create',
          meta: {
            activePath: '/workbench/tasks',
            hideInMenu: true,
            title: '新建素材任务',
          },
        });
      }

      const hasWorkbenchDeliveryTaskCreate = hasMenuPath(
        backendMenus,
        '/workbench/tasks/create-delivery',
      );
      if (!hasWorkbenchDeliveryTaskCreate) {
        backendMenus.push({
          name: 'WorkbenchDeliveryTaskCreate',
          path: '/workbench/tasks/create-delivery',
          component: '/workbench/delivery-task-create',
          meta: {
            activePath: '/workbench/tasks',
            hideInMenu: true,
            title: '新建投放任务',
          },
        });
      }

      ensureWorkbenchApprovalRoutes(backendMenus);
      ensureWorkbenchApplicationRoutes(backendMenus);
      ensureCloakBatchCreateRoute(backendMenus);
      relocateFeishuSyncMenu(backendMenus);
      ensureDeveloperSyncHistoryRoute(backendMenus);
      relocateApprovalConfigMenu(backendMenus);
      relocateDataIntegrationMenu(backendMenus);
      ensureDataIntegrationRoutes(backendMenus);
      ensureRoleMemberRoute(backendMenus);

      // 登录/操作日志在后端以按钮权限存在，不会作为导航菜单下发；
      // 补充受权限保护的隐藏路由，供系统管理页中的审计入口跳转。
      if (!demoMode) {
        ensureSystemAuditRoutes(backendMenus);
      }

      // MPower 渠道列表由菜单下发，新增/编辑/详情为模块内隐藏页。
      ensureMpowerChannelRoutes(backendMenus);

      ensureCreativeCanvasEditor(backendMenus);
      ensureMyDashboardMenu(backendMenus);

      const pathQueryMap: Record<string, Record<string, string>> = {
        '/management/developers': { tab: 'facebook' },
        '/management/platform-resources': { tab: 'personal' },
      };
      applyPathQuery(backendMenus, pathQueryMap);
      normalizeNestedLayoutComponents(backendMenus);

      return backendMenus;
    },
    // 可以指定没有权限跳转403页面
    forbiddenComponent,
    // 如果 route.meta.menuVisibleWithForbidden = true
    layoutMap,
    pageMap,
  });
}

function applyPathQuery(
  menus: RouteRecordStringComponent[],
  pathQueryMap: Record<string, Record<string, string>>,
) {
  for (const menu of menus) {
    if (menu.path && pathQueryMap[menu.path]) {
      menu.meta = {
        ...menu.meta,
        query: { ...pathQueryMap[menu.path], ...menu.meta?.query },
        title: menu.meta?.title ?? String(menu.name ?? menu.path),
      };
    }
    if (menu.children?.length) {
      applyPathQuery(menu.children, pathQueryMap);
    }
  }
}

export { generateAccess };

/** 旧投手工作台已合并到任务中心；保留原地址作为兼容跳转。 */
function ensureLegacyRequirementPitcherRedirect(
  menus: RouteRecordStringComponent[],
): void {
  const legacyRoute = findMenuByPath(menus, '/requirement/pitcher');
  if (legacyRoute) {
    delete (legacyRoute as { component?: string }).component;
    legacyRoute.redirect = '/workbench/tasks';
    legacyRoute.meta = {
      ...legacyRoute.meta,
      activePath: '/workbench/tasks',
      hideInMenu: true,
      title: '任务中心',
    };
    return;
  }

  menus.push({
    name: 'LegacyRequirementPitcherRedirect',
    path: '/requirement/pitcher',
    redirect: '/workbench/tasks',
    meta: {
      activePath: '/workbench/tasks',
      hideInMenu: true,
      title: '任务中心',
    },
  } as RouteRecordStringComponent);
}

/** 将历史素材详情链接迁移到任务中心，并保留原订单标识。 */
function legacyRequirementDetailRedirect(to: RouteLocation): RouteLocationRaw {
  const queryId = Array.isArray(to.query.id) ? to.query.id[0] : to.query.id;
  const query: Record<string, string> = {};
  if (typeof queryId === 'string' && queryId.trim()) {
    query.materialOrderId = queryId;
  }
  return { path: '/workbench/tasks', query };
}

function ensureLegacyRequirementDetailRedirect(
  menus: RouteRecordStringComponent[],
): void {
  const legacyRoute = findMenuByPath(menus, '/requirement/detail');
  if (legacyRoute) {
    delete (legacyRoute as { component?: string }).component;
    legacyRoute.redirect = legacyRequirementDetailRedirect;
    legacyRoute.meta = {
      ...legacyRoute.meta,
      activePath: '/workbench/tasks',
      hideInMenu: true,
      title: '素材任务详情',
    };
    return;
  }

  menus.push({
    name: 'LegacyRequirementDetailRedirect',
    path: '/requirement/detail',
    redirect: legacyRequirementDetailRedirect,
    meta: {
      activePath: '/workbench/tasks',
      hideInMenu: true,
      title: '素材任务详情',
    },
  } as RouteRecordStringComponent);
}

/**
 * 菜单管理允许将隐藏详情页归属到具体功能页，便于维护权限树。
 * 普通页面不是 RouterView 容器，注册前必须平铺其隐藏子页，避免 Vue Router
 * 在父页面内部渲染子路由；菜单管理树和后端权限关系不受影响。
 */
function flattenHiddenPageChildRoutes(
  menus: RouteRecordStringComponent[],
): void {
  const hiddenPageRoutes: RouteRecordStringComponent[] = [];
  const visit = (routes: RouteRecordStringComponent[]): void => {
    for (const route of routes) {
      if (!route.children?.length) continue;

      const children = route.children;
      const isPageRoute = Boolean(
        route.component &&
          route.component !== 'BasicLayout' &&
          route.component !== 'IFrameView',
      );
      if (isPageRoute) {
        const hiddenChildren = children.filter((child) =>
          Boolean(child.meta?.hideInMenu),
        );
        if (hiddenChildren.length > 0) {
          route.children = children.filter((child) => !child.meta?.hideInMenu);
          for (const child of hiddenChildren) {
            child.meta = {
              ...child.meta,
              activePath: route.path,
              title: child.meta?.title ?? String(child.name ?? child.path),
            };
            hiddenPageRoutes.push(child);
          }
        }
      }
      visit(route.children ?? []);
    }
  };

  visit(menus);
  for (const route of hiddenPageRoutes) {
    if (!hasMenuPath(menus, route.path)) menus.push(route);
  }
}

function hasMenuPath(
  menus: RouteRecordStringComponent[],
  path: string,
): boolean {
  return menus.some(
    (menu) =>
      menu.path === path ||
      (menu.children?.length ? hasMenuPath(menu.children, path) : false),
  );
}

function removeMenuPath(
  menus: RouteRecordStringComponent[],
  path: string,
): void {
  for (let index = menus.length - 1; index >= 0; index -= 1) {
    const menu = menus[index];
    if (menu.path === path) {
      menus.splice(index, 1);
      continue;
    }
    if (menu.children?.length) removeMenuPath(menu.children, path);
  }
}

function removeMenuEntries(
  menus: RouteRecordStringComponent[],
  predicate: (menu: RouteRecordStringComponent) => boolean,
): void {
  for (let index = menus.length - 1; index >= 0; index -= 1) {
    const menu = menus[index];
    if (!menu) continue;
    if (predicate(menu)) {
      menus.splice(index, 1);
      continue;
    }
    if (menu.children?.length) {
      removeMenuEntries(menu.children, predicate);
    }
  }
}

/**
 * 画布编辑器必须和列表页同级注册。
 *
 * 测试环境菜单已经下发 `/creative/canvas/:id`，但常被挂在列表路由下面。
 * 列表页没有 `<router-view>`，结果是地址栏变了、标签也切了，内容还停在列表。
 * 生产环境没有这条菜单，走前端补路由所以看起来正常。这里统一拆出来再挂回根级。
 */
function ensureCreativeCanvasEditor(menus: RouteRecordStringComponent[]): void {
  removeMenuPath(menus, '/creative/canvas/:id');
  removeMenuEntries(menus, (menu) => menu.name === 'CreativeCanvasEditor');
  menus.push({
    name: 'CreativeCanvasEditor',
    path: '/creative/canvas/:id',
    component: '/creative/canvas/editor',
    meta: {
      activePath: '/creative/canvas',
      hideInMenu: true,
      title: 'AI创意画布编辑器',
    },
  });
}

/**
 * 审批详情与账号发放是审批中心的下钻页面，后端菜单未升级时也必须可直达。
 */
function ensureWorkbenchApprovalRoutes(
  menus: RouteRecordStringComponent[],
): void {
  const routes: RouteRecordStringComponent[] = [
    {
      name: 'WorkbenchApprovalHandle',
      path: '/workbench/approvals/:id',
      component: '/workbench/approval-handle',
      meta: {
        activePath: '/workbench/approvals',
        hideInMenu: true,
        title: '审批办理',
      },
    },
  ];

  for (const route of routes) {
    if (!hasMenuPath(menus, route.path)) menus.push(route);
  }
}

/**
 * 填写资源申请是申请中心的下钻页面，不能依赖后端菜单同步；
 * 否则已登录用户通过任务、项目或资产入口直达时会被 404 路由抢占。
 */
function ensureWorkbenchApplicationRoutes(
  menus: RouteRecordStringComponent[],
): void {
  const path = '/workbench/applications/create';
  if (hasMenuPath(menus, path)) return;

  menus.push({
    name: 'WorkbenchApplicationsCreate',
    path,
    component: '/workbench/applications-create',
    meta: {
      activePath: '/workbench/applications',
      hideInMenu: true,
      title: '填写资源申请',
    },
  });
}

/**
 * 批量创建页是斗篷管理列表的下钻页面，保持隐藏路由可直接访问。
 * 可见的斗篷管理入口必须由后端菜单与角色权限下发。
 */
function ensureCloakBatchCreateRoute(
  menus: RouteRecordStringComponent[],
): void {
  const listPath = '/workbench/cloaks';
  const createPath = '/workbench/cloaks/batch-create';
  const existingRoute = findMenuByPath(menus, createPath);
  if (existingRoute) {
    existingRoute.meta = Object.assign(existingRoute.meta ?? {}, {
      keepAlive: true,
    });
    return;
  }

  menus.push({
    name: 'WorkbenchCloakBatchCreate',
    path: createPath,
    component: '/workbench/cloak-management/batch-create',
    meta: {
      activePath: listPath,
      hideInMenu: true,
      // 新建过程中允许切换标签页；关闭该标签页时再由框架销毁草稿状态。
      keepAlive: true,
      title: '批量创建斗篷',
    },
  });
}

/**
 * 将旧飞书同步菜单迁移为“飞书数据集成/文档同步”。组织架构同步由后端菜单
 * 独立授权；旧地址仅保留隐藏路由，确保历史收藏仍可访问。
 */
function relocateFeishuSyncMenu(menus: RouteRecordStringComponent[]): void {
  const system = findMenuByPath(menus, '/system-management');
  if (!system) return;
  const integration = findMenuByPath(
    menus,
    '/system-management/feishu-data-integration',
  );
  const targetParent = integration ?? system;
  const feishuSync =
    findVisibleMenuByPath(
      menus,
      '/system-management/feishu-data-integration/document-sync',
    ) ??
    findVisibleMenuByPath(menus, '/system-management/feishu-sync') ??
    findVisibleMenuByPath(
      menus,
      '/media-resources/account-management/feishu-sync',
    );

  if (feishuSync) {
    const alreadyUnderTarget =
      targetParent.children?.includes(feishuSync) ?? false;
    if (!alreadyUnderTarget) detachMenu(menus, feishuSync);
    feishuSync.name = 'SystemFeishuDocumentSync';
    feishuSync.path = integration
      ? '/system-management/feishu-data-integration/document-sync'
      : '/system-management/feishu-sync';
    feishuSync.component = '/media-resources/account-feishu-sync';
    feishuSync.meta = {
      ...feishuSync.meta,
      hideInMenu: false,
      icon: 'lucide:messages-square',
      order: 48,
      title: integration ? '文档同步' : '飞书同步',
    };
    if (!alreadyUnderTarget) {
      targetParent.children = [...(targetParent.children ?? []), feishuSync];
    }
  } else if (
    !hasMenuPath(
      menus,
      integration
        ? '/system-management/feishu-data-integration/document-sync'
        : '/system-management/feishu-sync',
    )
  ) {
    targetParent.children = [
      ...(targetParent.children ?? []),
      {
        name: integration ? 'SystemFeishuDocumentSync' : 'SystemFeishuSync',
        path: integration
          ? '/system-management/feishu-data-integration/document-sync'
          : '/system-management/feishu-sync',
        component: '/media-resources/account-feishu-sync',
        meta: {
          icon: 'lucide:messages-square',
          order: 48,
          title: integration ? '文档同步' : '飞书同步',
        },
      },
    ];
  }

  const legacyPath = '/media-resources/account-management/feishu-sync';
  const legacyRoute = findMenuByPath(menus, legacyPath);
  if (legacyRoute) {
    legacyRoute.name = 'LegacyMediaResourceAccountFeishuSync';
    legacyRoute.component = '/media-resources/account-feishu-sync';
    legacyRoute.meta = {
      ...legacyRoute.meta,
      activePath: integration
        ? '/system-management/feishu-data-integration/document-sync'
        : '/system-management/feishu-sync',
      hideInMenu: true,
      title: '文档同步',
    };
  } else {
    menus.push({
      name: 'LegacyMediaResourceAccountFeishuSync',
      path: legacyPath,
      component: '/media-resources/account-feishu-sync',
      meta: {
        activePath: integration
          ? '/system-management/feishu-data-integration/document-sync'
          : '/system-management/feishu-sync',
        hideInMenu: true,
        title: '文档同步',
      },
    });
  }
}

/** 数据同步记录是开发者管理的二级页面，不依赖后端新增菜单。 */
function ensureDeveloperSyncHistoryRoute(
  menus: RouteRecordStringComponent[],
): void {
  const path = '/management/developers/sync-history';
  if (hasMenuPath(menus, path)) return;
  menus.push({
    name: 'DeveloperSyncHistory',
    path,
    component: '/management/developers/sync-history',
    meta: {
      activePath: '/management/developers',
      hideInMenu: true,
      title: '数据同步记录',
    },
  });
}

/**
 * 审批设计器是系统级能力；旧后端仍返回媒介资源路径时迁移可见菜单，
 * 同时保留旧地址作为隐藏兼容入口。
 */
function relocateApprovalConfigMenu(menus: RouteRecordStringComponent[]): void {
  const system = findMenuByPath(menus, '/system-management');
  if (!system) return;
  const approval =
    findVisibleMenuByPath(menus, '/system-management/approval-config') ??
    findVisibleMenuByPath(menus, '/media-resources/approval-config');
  if (!approval) return;

  const alreadyUnderSystem = system.children?.includes(approval) ?? false;
  if (!alreadyUnderSystem) detachMenu(menus, approval);
  approval.name = 'SystemApprovalConfig';
  approval.path = '/system-management/approval-config';
  approval.component = '/media-resources/approval-config';
  approval.meta = {
    ...approval.meta,
    hideInMenu: false,
    icon: 'lucide:workflow',
    order: 35,
    title: '审批配置',
  };
  if (!alreadyUnderSystem) {
    system.children = [...(system.children ?? []), approval];
  }

  if (!hasMenuPath(menus, '/media-resources/approval-config')) {
    menus.push({
      name: 'LegacyMediaResourceApprovalConfig',
      path: '/media-resources/approval-config',
      component: '/media-resources/approval-config',
      meta: {
        activePath: '/system-management/approval-config',
        hideInMenu: true,
        title: '审批配置',
      },
    });
  }
}

/** Google 数据集成属于系统级外部服务配置，旧菜单存在时迁移到系统管理。 */
function relocateDataIntegrationMenu(
  menus: RouteRecordStringComponent[],
): void {
  const system = findMenuByPath(menus, '/system-management');
  if (!system) return;
  const integration =
    findVisibleMenuByPath(menus, '/system-management/data-integration') ??
    findVisibleMenuByPath(menus, '/media-resources/data-integration');
  if (!integration) return;

  const alreadyUnderSystem = system.children?.includes(integration) ?? false;
  if (!alreadyUnderSystem) detachMenu(menus, integration);
  integration.name = 'SystemDataIntegration';
  integration.path = '/system-management/data-integration';
  integration.component = '/media-resources/data-integration';
  integration.meta = {
    ...integration.meta,
    hideInMenu: false,
    icon: 'lucide:plug-zap',
    order: 47,
    title: 'Google数据集成',
  };
  if (!alreadyUnderSystem) {
    system.children = [...(system.children ?? []), integration];
  }
}

function findVisibleMenuByPath(
  menus: RouteRecordStringComponent[],
  path: string,
): RouteRecordStringComponent | undefined {
  for (const menu of menus) {
    if (menu.path === path && !menu.meta?.hideInMenu) return menu;
    if (menu.children?.length) {
      const matched = findVisibleMenuByPath(menu.children, path);
      if (matched) return matched;
    }
  }
  return undefined;
}

function detachMenu(
  menus: RouteRecordStringComponent[],
  target: RouteRecordStringComponent,
): boolean {
  const index = menus.indexOf(target);
  if (index !== -1) {
    menus.splice(index, 1);
    return true;
  }
  for (const menu of menus) {
    if (menu.children?.length && detachMenu(menu.children, target)) return true;
  }
  return false;
}

function ensureSystemAuditRoutes(menus: RouteRecordStringComponent[]): void {
  if (!hasMenuPath(menus, '/system/login-log')) {
    menus.push({
      name: 'SystemLoginLog',
      path: '/system/login-log',
      component: '/system/login-log/list',
      meta: {
        activePath: '/system-management/users',
        authority: ['system:login-log:list'],
        hideInMenu: true,
        title: '登录日志',
      },
    });
  }
  if (!hasMenuPath(menus, '/system/operation-log')) {
    menus.push({
      name: 'SystemOperationLog',
      path: '/system/operation-log',
      component: '/system/operation-log/list',
      meta: {
        activePath: '/system-management/users',
        authority: ['system:operation-log:list'],
        hideInMenu: true,
        title: '操作日志',
      },
    });
  }
}

function ensureMpowerChannelRoutes(menus: RouteRecordStringComponent[]): void {
  const routes: RouteRecordStringComponent[] = [
    {
      name: 'MpowerChannelCreate',
      path: '/media-resources/channels/create',
      component: '/media-resources/channel-management/ChannelEditor',
      meta: {
        activePath: '/media-resources/channels',
        hideInMenu: true,
        title: '添加渠道',
      },
    },
    {
      name: 'MpowerChannelEdit',
      path: '/media-resources/channels/:id/edit',
      component: '/media-resources/channel-management/ChannelEditor',
      meta: {
        activePath: '/media-resources/channels',
        hideInMenu: true,
        title: '编辑渠道',
      },
    },
    {
      name: 'MpowerChannelDetail',
      path: '/media-resources/channels/:id',
      component: '/media-resources/channel-management/ChannelDetail',
      meta: {
        activePath: '/media-resources/channels',
        hideInMenu: true,
        title: '渠道详情',
      },
    },
  ];

  routes.forEach((route) => {
    if (!hasMenuPath(menus, route.path)) menus.push(route);
  });
}

function ensureDataIntegrationRoutes(
  menus: RouteRecordStringComponent[],
): void {
  const path = '/system-management/data-integration/:id/data';
  if (hasMenuPath(menus, path)) return;
  menus.push({
    name: 'SystemDataIntegrationData',
    path,
    component: '/media-resources/data-integration-data',
    meta: {
      activePath: '/system-management/data-integration',
      hideInMenu: true,
      title: '集成数据',
    },
  });
}

/** 角色成员是角色权限列表的下钻页，后端菜单无需新增独立导航节点。 */
function ensureRoleMemberRoute(menus: RouteRecordStringComponent[]): void {
  const path = '/system-management/roles/:roleId/members';
  if (hasMenuPath(menus, path)) return;

  menus.push({
    name: 'SystemRoleMembers',
    path,
    component: '/system/role/members',
    meta: {
      activePath: '/system-management/roles',
      authority: ['system:role:list'],
      hideInMenu: true,
      title: '角色成员',
    },
  });
}

/**
 * 演示环境「我的看板」在测试网关菜单里可能还没有。开发模式挂到数据复盘下，正式构建只注册隐藏路由。
 */
function ensureMyDashboardMenu(menus: RouteRecordStringComponent[]): void {
  if (hasMenuPath(menus, '/data-growth/my-dashboard')) return;

  const item: RouteRecordStringComponent = {
    name: 'MyDashboard',
    path: '/data-growth/my-dashboard',
    component: '/data-growth/my-dashboard',
    meta: {
      icon: 'lucide:layout-dashboard',
      order: 5,
      title: '我的看板',
    },
  };

  const parent =
    findMenuByPath(menus, '/data-growth') ||
    findMenuByName(menus, 'DataGrowthCenter');

  if (import.meta.env.DEV) {
    if (parent) {
      parent.children = [item, ...(parent.children ?? [])];
      return;
    }
    menus.push(item);
    return;
  }

  menus.push({
    ...item,
    meta: {
      ...item.meta,
      hideInMenu: true,
    },
  });
}

function findMenuByName(
  menus: RouteRecordStringComponent[],
  name: string,
): RouteRecordStringComponent | undefined {
  for (const menu of menus) {
    if (menu.name === name) return menu;
    if (menu.children?.length) {
      const matched = findMenuByName(menu.children, name);
      if (matched) return matched;
    }
  }
  return undefined;
}

function findMenuByPath(
  menus: RouteRecordStringComponent[],
  path: string,
): RouteRecordStringComponent | undefined {
  for (const menu of menus) {
    if (menu.path === path) return menu;
    if (menu.children?.length) {
      const matched = findMenuByPath(menu.children, path);
      if (matched) return matched;
    }
  }
  return undefined;
}
