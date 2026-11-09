import { createApp, watchEffect } from 'vue';

import { registerAccessDirective } from '@vben/access';
import {
  registerLoadingDirective,
  setDefaultDrawerProps,
  setDefaultModalProps,
} from '@vben/common-ui';
import { preferences } from '@vben/preferences';
import { initStores } from '@vben/stores';
import '@vben/styles';
import '@vben/styles/antd';

import { _api } from '@iconify/vue';
import { useTitle } from '@vueuse/core';

import { $t, setupI18n } from '#/locales';
import { router } from '#/router';
import { installFormLabelAlignment } from '#/utils/form-label-alignment';

import { initComponentAdapter } from './adapter/component';
import { initSetupVbenForm } from './adapter/form';
import App from './app.vue';
import './styles/ux-baseline.css';

// 为 Iconify 图标 CDN 请求启用 localStorage 持久化缓存。
function setupIconifyCache() {
  const CACHE_PREFIX = 'iconify_v1_';
  const originalFetch = _api.getFetch();
  if (!originalFetch) return;

  _api.setFetch(async (url: string) => {
    if (url.includes('iconify.design')) {
      const cacheKey = CACHE_PREFIX + url;
      try {
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
          return new Response(cached, {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
      } catch {}
      const response = await originalFetch(url);
      if (response.ok) {
        try {
          const text = await response.clone().text();
          localStorage.setItem(cacheKey, text);
        } catch {}
      }
      return response;
    }
    return originalFetch(url);
  });
}

setupIconifyCache();

/**
 * 统一拦截 Ant Design Vue Modal 与 Drawer 的遮罩点击。
 *
 * Ant Design Vue 4 未提供应用级的 `maskClosable` 默认配置；使用捕获阶段拦截，
 * 可让模板弹窗与命令式弹窗保持一致，同时不影响弹窗内容及其关闭按钮的点击事件。
 */
function preventAntOverlayDismissal(event: MouseEvent) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  if (target.matches('.ant-drawer-mask') || target.matches('.ant-modal-wrap')) {
    event.stopImmediatePropagation();
  }
}

async function bootstrap(namespace: string) {
  // 这些插件的下载不依赖组件适配器；尽早发起请求以缩短挂载前的关键路径。
  const pluginModulesPromise = Promise.all([
    import('@vben/common-ui/es/tippy'),
    import('@tanstack/vue-query'),
    import('@vben/plugins/motion'),
  ]);

  // 初始化组件适配器
  await initComponentAdapter();

  // 初始化表单组件
  await initSetupVbenForm();

  // 设置弹窗的默认配置
  // setDefaultModalProps({
  //   fullscreenButton: false,
  // });
  // 设置抽屉的默认配置
  // setDefaultDrawerProps({
  //   zIndex: 1020,
  // });

  // 遮罩点击不会关闭弹层，避免正在编辑的内容被误关闭。
  setDefaultModalProps({ closeOnClickModal: false });
  setDefaultDrawerProps({ closeOnClickModal: false });
  document.addEventListener('click', preventAntOverlayDismissal, true);

  const app = createApp(App);

  // 注册v-loading指令
  registerLoadingDirective(app, {
    loading: 'loading', // 在这里可以自定义指令名称，也可以明确提供false表示不注册这个指令
    spinning: 'spinning',
  });

  // 国际化 i18n 配置
  await setupI18n(app);

  // 配置 pinia-tore
  await initStores(app, { namespace });

  // 安装权限指令
  registerAccessDirective(app);

  const [{ initTippy }, { VueQueryPlugin }, { MotionPlugin }] =
    await pluginModulesPromise;

  // 初始化 tippy
  initTippy(app);

  // 配置路由及路由守卫
  app.use(router);

  // 配置@tanstack/vue-query
  app.use(VueQueryPlugin);

  // 配置Motion插件
  app.use(MotionPlugin);

  // 动态更新标题
  watchEffect(() => {
    if (preferences.app.dynamicTitle) {
      const routeTitle = router.currentRoute.value.meta?.title;
      const pageTitle =
        (routeTitle ? `${$t(routeTitle)} - ` : '') + preferences.app.name;
      useTitle(pageTitle);
    }
  });

  // Keep the global loading screen visible until the initial menu, dynamic
  // routes, and target page have all finished resolving.
  await router.isReady();
  app.mount('#app');
  installFormLabelAlignment();
}

export { bootstrap };
