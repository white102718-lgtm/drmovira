<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watchEffect } from 'vue';

import { preferences } from '@vben/preferences';
import { getPopupContainer } from '@vben/utils';

import AntApp from 'ant-design-vue/es/app';
import ConfigProvider from 'ant-design-vue/es/config-provider';
import theme from 'ant-design-vue/es/theme';

import {
  applyUiScaleToDocument,
  getUiScaleDefinition,
  readStoredUiScale,
  UI_SCALE_CHANGE_EVENT,
  type UiScale,
} from '#/constants/ui-scale';
import { antdLocale } from '#/locales';

defineOptions({ name: 'App' });

// Vben 弹窗使用 --popup-z-index（2000）；Ant Design 的下拉菜单需高一层，避免被弹窗内容遮挡。
const antdPopupZIndex = 2001;
const uiScale = ref<UiScale>(readStoredUiScale());
applyUiScaleToDocument(uiScale.value);

function handleUiScaleChange(event: Event) {
  const scale = (event as CustomEvent<UiScale>).detail;
  uiScale.value = scale;
  applyUiScaleToDocument(scale);
}

onMounted(() => {
  window.addEventListener(UI_SCALE_CHANGE_EVENT, handleUiScaleChange);
});

onUnmounted(() => {
  window.removeEventListener(UI_SCALE_CHANGE_EVENT, handleUiScaleChange);
});

function hexToHslChannels(hex: string) {
  const normalized = hex.replace('#', '');
  if (!/^[\da-f]{6}$/i.test(normalized)) return '217 80% 65%';

  const red = Number.parseInt(normalized.slice(0, 2), 16) / 255;
  const green = Number.parseInt(normalized.slice(2, 4), 16) / 255;
  const blue = Number.parseInt(normalized.slice(4, 6), 16) / 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const delta = max - min;
  let hue = 0;

  if (delta !== 0) {
    if (max === red) hue = ((green - blue) / delta) % 6;
    else if (max === green) hue = (blue - red) / delta + 2;
    else hue = (red - green) / delta + 4;
    hue *= 60;
    if (hue < 0) hue += 360;
  }

  const lightness = (max + min) / 2;
  const saturation =
    delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1));

  return `${Math.round(hue)} ${Math.round(saturation * 100)}% ${Math.round(
    lightness * 100,
  )}%`;
}

watchEffect(() => {
  if (typeof document === 'undefined') return;
  document.documentElement.style.setProperty(
    '--primary',
    hexToHslChannels(preferences.theme.colorPrimary),
  );
});

const tokenTheme = computed(() => {
  const scale = getUiScaleDefinition(uiScale.value);
  const colorPrimary = preferences.theme.colorPrimary;
  const primaryColorTokens = theme.defaultAlgorithm({
    ...theme.defaultSeed,
    colorPrimary,
  });

  return {
    algorithm: theme.defaultAlgorithm,
    token: {
      borderRadius: scale.radius,
      borderRadiusLG: scale.cardRadius,
      colorBgBase: '#ffffff',
      colorBgContainer: '#ffffff',
      colorBgElevated: '#ffffff',
      colorBorder: '#e3e9f2',
      colorLink: colorPrimary,
      colorLinkActive: primaryColorTokens.colorPrimaryActive,
      colorLinkHover: primaryColorTokens.colorPrimaryHover,
      colorPrimary,
      controlHeight: scale.controlHeight,
      fontSize: scale.fontSize,
      lineHeight: scale.controlLineHeight / scale.fontSize,
      padding: scale.padding,
      paddingLG: scale.paddingLG,
      paddingMD: scale.paddingMD,
      paddingSM: scale.paddingSM,
      paddingXL: scale.paddingXL,
      paddingXS: scale.paddingXS,
      paddingXXS: scale.paddingXXS,
      zIndexPopupBase: antdPopupZIndex,
      fontFamily:
        '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", ui-sans-serif, sans-serif',
      wireframe: false,
    },
    components: {
      Pagination: {
        controlHeight: scale.controlHeight,
        controlHeightSM: scale.controlHeight,
      },
    },
  };
});
</script>

<template>
  <ConfigProvider
    component-size="middle"
    :get-popup-container="getPopupContainer"
    :locale="antdLocale"
    :theme="tokenTheme"
  >
    <AntApp>
      <RouterView />
    </AntApp>
  </ConfigProvider>
</template>
