import type { RouteMeta as IRouteMeta } from '@vben-core/typings';

import 'vue-router';

declare module 'vue-router' {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface RouteMeta extends IRouteMeta {}
}

export interface VbenAdminProAppConfigRaw {
  VITE_GLOB_API_URL: string;
  VITE_GLOB_BACKEND_API_URL: string;
  VITE_GLOB_OTHER_API_URL: string;
  VITE_GLOB_ADPULSE_API_URL: string;
}

export interface ApplicationConfig {
  apiURL: string;
  backendURL: string;
  otherURL: string;
  /** 广告数据服务,与 backendURL 的 adpulse-system-server 分开部署 */
  adpulseURL: string;
}

declare global {
  interface Window {
    _VBEN_ADMIN_PRO_APP_CONF_: VbenAdminProAppConfigRaw;
  }
}
