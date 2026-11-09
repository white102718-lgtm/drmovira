<script lang="ts" setup>
import { Maximize, Minimize } from '@vben-core/icons';

import { useFullscreen } from '@vueuse/core';

import { VbenIconButton } from '../button';

defineOptions({ name: 'FullScreen' });

const { isFullscreen, toggle } = useFullscreen();

// 重新检查全屏状态
isFullscreen.value = !!(
  document.fullscreenElement ||
  // @ts-ignore
  document.webkitFullscreenElement ||
  // @ts-ignore
  document.mozFullScreenElement ||
  // @ts-ignore
  document.msFullscreenElement
);
</script>
<template>
  <VbenIconButton aria-label="切换全屏" tooltip="切换全屏" @click="toggle">
    <Minimize v-if="isFullscreen" class="text-foreground size-4" />
    <Maximize v-else class="text-foreground size-4" />
  </VbenIconButton>
</template>
