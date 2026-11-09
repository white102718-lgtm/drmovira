import { defineOverridesPreferences } from '@vben/preferences';

/**
 * @description 项目配置文件
 * 只需要覆盖项目中的一部分配置，不需要的配置不用覆盖，会自动使用默认配置
 * !!! 更改配置后请清空缓存，否则可能不生效, 浏览器f12->应用->应用->存储->清除网站数据
 */
export const overridesPreferences = defineOverridesPreferences({
  // overrides
  breadcrumb: {
    enable: false,
  },
  app: {
    accessMode: 'backend',
    name: import.meta.env.VITE_APP_TITLE,
    layout: 'sidebar-nav',
    // 页面组件统一负责内容留白，避免布局层与 Page 的 p-4 叠加。
    contentPadding: 0,
    contentPaddingBottom: 0,
    contentPaddingLeft: 0,
    contentPaddingRight: 0,
    contentPaddingTop: 0,
    enablePreferences: false, // 关闭偏好设置按钮
    defaultAvatar: '/avatar.png', // 默认头像,将图片放到 public/avatar.png
    authPageLayout: 'panel-center', // 登录界面默认居中
  },
  logo: {
    enable: true,
    // Logo 更新时通过版本参数绕过浏览器和 CDN 对同名静态资源的旧缓存。
    source: '/logo.svg?v=20260824',
  },
  header: {
    height: 46,
    menuAlign: 'start',
    mode: 'fixed',
  },
  navigation: {
    accordion: true,
    styleType: 'rounded',
  },
  shortcutKeys: {
    enable: false,
  },
  sidebar: {
    collapsed: false,
    collapsedButton: true,
    enable: true,
    // 固定侧栏；用户仍可使用底部按钮主动收起或展开。
    expandOnHover: true,
    extraCollapse: false,
    fixedButton: false,
    hidden: false,
    width: 210,
  },
  tabbar: {
    enable: true,
    height: 36,
    // 标签页与 KeepAlive 缓存会同时占用页面实例和接口数据；保留最近 10 个，
    // 达到上限时由标签栏自动关闭最早的非固定标签，避免新页面无法渲染。
    maxCount: 10,
  },
  theme: {
    builtinType: 'default',
    colorPrimary: '#5B8DEF',
    mode: 'light',
    radius: '0.625',
    semiDarkHeader: false,
    semiDarkSidebar: false,
  },
  transition: {
    name: 'fade',
  },
  widget: {
    globalSearch: false, // 隐藏搜索
    themeToggle: false, // 隐藏黑暗模式切换
    languageToggle: false, // 隐藏中英文切换
    notification: true, // 开启通知
    fullscreen: false, // 隐藏全屏
    sidebarToggle: false, // 桌面端仅使用侧栏内按钮；移动端仍自动显示菜单按钮
    refresh: false, // 刷新操作固定放在左侧返回按钮后
  },
});
