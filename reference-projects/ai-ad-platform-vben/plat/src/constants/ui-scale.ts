export type UiScale = 'large' | 'medium' | 'small' | 'xlarge' | 'xsmall';

export interface UiScaleDefinition {
  cardRadius: number;
  controlHeight: number;
  controlLineHeight: number;
  description: string;
  fontSize: number;
  headerHeight: number;
  label: string;
  padding: number;
  paddingLG: number;
  paddingMD: number;
  paddingSM: number;
  paddingXL: number;
  paddingXS: number;
  paddingXXS: number;
  radius: number;
  sidebarWidth: number;
  tabbarHeight: number;
  value: UiScale;
}

export const UI_SCALE_STORAGE_KEY = 'adpulse-ui-scale';
export const UI_SCALE_CHANGE_EVENT = 'adpulse:ui-scale-change';
export const DEFAULT_UI_SCALE: UiScale = 'medium';

export const UI_SCALE_OPTIONS: readonly UiScaleDefinition[] = [
  {
    value: 'xsmall',
    label: '更紧凑',
    description: '一屏显示最多数据',
    controlHeight: 24,
    controlLineHeight: 16,
    fontSize: 12,
    radius: 7,
    cardRadius: 10,
    paddingXXS: 2,
    paddingXS: 4,
    paddingSM: 8,
    padding: 12,
    paddingMD: 16,
    paddingLG: 20,
    paddingXL: 24,
    headerHeight: 42,
    sidebarWidth: 190,
    tabbarHeight: 32,
  },
  {
    value: 'small',
    label: '紧凑',
    description: '适合高频数据操作',
    controlHeight: 28,
    controlLineHeight: 18,
    fontSize: 13,
    radius: 8,
    cardRadius: 11,
    paddingXXS: 2,
    paddingXS: 6,
    paddingSM: 10,
    padding: 14,
    paddingMD: 18,
    paddingLG: 22,
    paddingXL: 28,
    headerHeight: 44,
    sidebarWidth: 200,
    tabbarHeight: 34,
  },
  {
    value: 'medium',
    label: '中等',
    description: '默认平衡尺寸',
    controlHeight: 32,
    controlLineHeight: 20,
    fontSize: 14,
    radius: 9,
    cardRadius: 12,
    paddingXXS: 4,
    paddingXS: 8,
    paddingSM: 12,
    padding: 16,
    paddingMD: 20,
    paddingLG: 24,
    paddingXL: 32,
    headerHeight: 46,
    sidebarWidth: 210,
    tabbarHeight: 36,
  },
  {
    value: 'large',
    label: '宽松',
    description: '更大的控件与间距',
    controlHeight: 36,
    controlLineHeight: 22,
    fontSize: 15,
    radius: 10,
    cardRadius: 13,
    paddingXXS: 4,
    paddingXS: 10,
    paddingSM: 14,
    padding: 18,
    paddingMD: 22,
    paddingLG: 28,
    paddingXL: 36,
    headerHeight: 50,
    sidebarWidth: 220,
    tabbarHeight: 38,
  },
  {
    value: 'xlarge',
    label: '大号',
    description: '适合远距离或大屏阅读',
    controlHeight: 40,
    controlLineHeight: 24,
    fontSize: 16,
    radius: 11,
    cardRadius: 14,
    paddingXXS: 4,
    paddingXS: 12,
    paddingSM: 16,
    padding: 20,
    paddingMD: 24,
    paddingLG: 32,
    paddingXL: 40,
    headerHeight: 54,
    sidebarWidth: 236,
    tabbarHeight: 42,
  },
] as const;

export function isUiScale(value: null | string): value is UiScale {
  return UI_SCALE_OPTIONS.some((option) => option.value === value);
}

export function getUiScaleDefinition(scale: UiScale) {
  const definition = UI_SCALE_OPTIONS.find((option) => option.value === scale);
  if (definition) return definition;

  const fallback = UI_SCALE_OPTIONS.find(
    (option) => option.value === DEFAULT_UI_SCALE,
  );
  if (!fallback) throw new Error('缺少默认页面大小配置');
  return fallback;
}

export function readStoredUiScale(): UiScale {
  if (typeof window === 'undefined') return DEFAULT_UI_SCALE;
  const savedScale = window.localStorage.getItem(UI_SCALE_STORAGE_KEY);
  return isUiScale(savedScale) ? savedScale : DEFAULT_UI_SCALE;
}

/** 同步非 Ant 业务组件使用的共享 CSS 令牌，Ant 自身只读取 ConfigProvider。 */
export function applyUiScaleToDocument(scale: UiScale) {
  if (typeof document === 'undefined') return;

  const definition = getUiScaleDefinition(scale);
  const root = document.documentElement;
  root.dataset.uiScale = scale;
  root.style.setProperty(
    '--adpulse-control-height',
    `${definition.controlHeight}px`,
  );
  root.style.setProperty(
    '--adpulse-control-font-size',
    `${definition.fontSize}px`,
  );
  root.style.setProperty(
    '--adpulse-control-line-height',
    `${definition.controlLineHeight}px`,
  );
  root.style.setProperty('--adpulse-radius', `${definition.radius}px`);
  root.style.setProperty('--adpulse-card-radius', `${definition.cardRadius}px`);
}
