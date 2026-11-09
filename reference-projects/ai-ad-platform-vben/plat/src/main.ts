import {
  initPreferences,
  preferences,
  updatePreferences,
} from '@vben/preferences';
import { unmountGlobalLoading } from '@vben/utils';

import { overridesPreferences } from './preferences';
import { installFeedbackDiagnostics } from './utils/feedback-diagnostics';

import './styles/business-sections.css';

function showLoadingError() {
  const el = document.querySelector('#__app-loading__ .loading-subtitle');
  if (el) el.textContent = '初始化失败，请刷新页面';
}

/**
 * 应用初始化完成之后再进行页面加载渲染
 */
async function initApplication() {
  installFeedbackDiagnostics();
  // 启动模块与本地偏好设置互不依赖，提前请求可缩短首屏的网络等待时间。
  const bootstrapPromise = import('./bootstrap');
  // name用于指定项目唯一标识
  // 用于区分不同项目的偏好设置以及存储数据的key前缀以及其他一些需要隔离的数据
  const env = import.meta.env.PROD ? 'prod' : 'dev';
  const appVersion = import.meta.env.VITE_APP_VERSION;
  const namespace = `${import.meta.env.VITE_APP_NAMESPACE}-${appVersion}-${env}`;

  try {
    // app偏好设置初始化
    await initPreferences({
      namespace,
      overrides: overridesPreferences,
    });
    // 仅迁移旧版黑色默认主题；用户主动选择的其他主题色继续由偏好设置持久化。
    const colorPrimary =
      preferences.theme.colorPrimary.toLowerCase() === '#18181b'
        ? '#5B8DEF'
        : preferences.theme.colorPrimary;
    // 产品基线：桌面端默认展开，禁止自动悬停缩放；用户可以通过
    // 侧栏内的单一按钮主动收起/展开，选择会保存在偏好设置中。
    updatePreferences({
      breadcrumb: {
        enable: false,
      },
      app: {
        contentPadding: 0,
        contentPaddingBottom: 0,
        contentPaddingLeft: 0,
        contentPaddingRight: 0,
        contentPaddingTop: 0,
        enableCheckUpdates: true,
        layout: 'sidebar-nav',
        name: 'Mpower',
      },
      header: {
        height: 46,
      },
      sidebar: {
        collapsed: false,
        collapsedButton: true,
        enable: true,
        // Vben 中 true 表示侧栏处于固定状态；false 会在鼠标进入时以
        // 浮层方式展开，导致内容看起来被侧栏覆盖。
        expandOnHover: true,
        fixedButton: false,
        hidden: false,
        width: 210,
      },
      tabbar: {
        enable: true,
        height: 36,
        // 偏好设置会被持久化；启动时强制同步上限，让已有本地配置也能释放旧缓存。
        maxCount: 10,
      },
      theme: {
        builtinType: 'default',
        colorPrimary,
        mode: 'light',
        radius: '0.625',
        semiDarkHeader: false,
        semiDarkSidebar: false,
      },
      widget: { notification: true, refresh: false, sidebarToggle: false },
    });

    // 启动应用并挂载
    // vue应用主要逻辑及视图
    const { bootstrap } = await bootstrapPromise;
    await bootstrap(namespace);
  } catch (error) {
    console.error('[initApplication] 初始化失败:', error);
    showLoadingError();
  } finally {
    unmountGlobalLoading();
  }
}

initApplication();
