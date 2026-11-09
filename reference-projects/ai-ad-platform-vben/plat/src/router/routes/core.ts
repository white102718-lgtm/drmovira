import type { RouteRecordRaw } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';

import { $t } from '#/locales';

const BasicLayout = () => import('#/layouts/basic.vue');
const AuthPageLayout = () => import('#/layouts/auth.vue');
const OtherLayout = () => import('#/layouts/other.vue');

const oauthLandingRoute: RouteRecordRaw = {
  name: 'OAuthLanding',
  path: '/oauth-landing',
  component: () => import('#/views/_core/authentication/oauth-landing.vue'),
  meta: {
    title: 'OAuth Landing',
    hideInBreadcrumb: true,
    hideInMenu: true,
    hideInTab: true,
    ignoreAccess: true,
  },
};
/** 全局404页面 */
const fallbackNotFoundRoute: RouteRecordRaw = {
  component: () => import('#/views/_core/fallback/not-found.vue'),
  meta: {
    hideInBreadcrumb: true,
    hideInMenu: true,
    hideInTab: true,
    title: '404',
  },
  name: 'FallbackNotFound',
  path: '/:path(.*)*',
};

/** Generic 403 target used by the local Demo role-preview guard. */
const forbiddenRoute: RouteRecordRaw = {
  component: OtherLayout,
  meta: {
    hideInBreadcrumb: true,
    hideInMenu: true,
    hideInTab: true,
    ignoreAccess: true,
    title: '无权限访问',
  },
  name: 'DemoForbidden',
  path: '/forbidden',
  children: [
    {
      component: () => import('#/views/_core/fallback/forbidden.vue'),
      meta: {
        hideInBreadcrumb: true,
        hideInMenu: true,
        hideInTab: true,
        ignoreAccess: true,
        title: '无权限访问',
      },
      name: 'DemoForbiddenPage',
      path: '',
    },
  ],
};

/** 基本路由，这些路由是必须存在的 */
const coreRoutes: RouteRecordRaw[] = [
  oauthLandingRoute,
  forbiddenRoute,
  /**
   * 根路由
   * 使用基础布局，作为所有页面的父级容器，子级就不必配置BasicLayout。
   * 此路由必须存在，且不应修改
   */
  {
    component: BasicLayout,
    meta: {
      hideInBreadcrumb: true,
      title: 'Root',
    },
    name: 'Root',
    path: '/',
    redirect: preferences.app.defaultHomePath,
    children: [],
  },
  {
    component: AuthPageLayout,
    meta: {
      hideInTab: true,
      title: 'Authentication',
    },
    name: 'Authentication',
    path: '/auth',
    redirect: LOGIN_PATH,
    children: [
      {
        name: 'Login',
        path: 'login',
        component: () => import('#/views/_core/authentication/login.vue'),
        meta: {
          title: $t('page.auth.login'),
        },
      },
      {
        name: 'FeishuOAuthCallback',
        path: 'feishu/callback',
        component: () =>
          import('#/views/_core/authentication/feishu-oauth-callback.vue'),
        meta: {
          title: '飞书登录',
        },
      },
      {
        name: 'CodeLogin',
        path: 'code-login',
        component: () => import('#/views/_core/authentication/code-login.vue'),
        meta: {
          title: $t('page.auth.codeLogin'),
        },
      },
      {
        name: 'QrCodeLogin',
        path: 'qrcode-login',
        component: () =>
          import('#/views/_core/authentication/qrcode-login.vue'),
        meta: {
          title: $t('page.auth.qrcodeLogin'),
        },
      },
      {
        name: 'ForgetPassword',
        path: 'forget-password',
        component: () =>
          import('#/views/_core/authentication/forget-password.vue'),
        meta: {
          title: $t('page.auth.forgetPassword'),
        },
      },
    ],
  },
  {
    component: OtherLayout,
    meta: {
      hideInTab: true,
      title: '隐私政策',
    },
    name: 'PrivacyPolicy',
    path: '/privacy-policy',
    children: [
      {
        path: '',
        name: 'SystemPrivacyPolicy',
        meta: {
          icon: 'mdi:file-document-outline',
          title: '隐私政策',
          ignoreAccess: true,
        },
        component: () => import('#/views/_core/privacy-policy/index.vue'),
      },
    ],
  },
];

export { coreRoutes, fallbackNotFoundRoute, forbiddenRoute };
