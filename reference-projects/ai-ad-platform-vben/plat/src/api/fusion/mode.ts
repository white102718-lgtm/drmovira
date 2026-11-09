const fusionDemoMode = import.meta.env.VITE_FUSION_DEMO_MODE === 'true';

/**
 * 判断当前是否使用融合工作台的本地演示数据。
 *
 * 独立于融合 API 主入口，避免路由守卫为读取环境开关而把整套 Demo
 * fixtures 和业务适配器拉入首屏依赖图。
 */
export function isFusionDemoMode() {
  return fusionDemoMode;
}
