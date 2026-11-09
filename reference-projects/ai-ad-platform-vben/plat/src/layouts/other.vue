<script lang="ts" setup>
import { computed } from 'vue';

import { AuthPageLayout } from '@vben/layouts';
import { preferences } from '@vben/preferences';

const appName = computed(() => preferences.app.name);
const logo = computed(() => preferences.logo.source);
const clickLogo = () => {};
</script>

<template>
  <!-- :toolbar="false"禁用工具栏 -->
  <AuthPageLayout
    :app-name="appName"
    :logo="logo"
    page-description=""
    page-title="隐私政策"
    :toolbar="false"
    :click-logo="clickLogo"
  />
</template>

<style scoped>
:deep(.flex.h-screen.overflow-hidden) {
  height: 100dvh !important;
  overflow: hidden auto !important;
}

:deep(.flex-center.relative.w-full) {
  align-items: flex-start !important;
  height: 100dvh !important;
  padding: 16px !important;
  overflow-y: auto !important;
}

:deep(.flex-col-center) {
  align-items: flex-start !important;
  justify-content: flex-start !important;
  height: auto !important;
  min-height: auto !important;
  padding: 0 !important;
}

:deep(.shadow-float) {
  width: min(100%, 960px) !important;
  min-width: 0 !important;
  max-width: 960px !important;
  padding-bottom: 0 !important;
  margin: 0 auto !important;
}

:deep(.enter-x) {
  width: 100% !important;
  max-width: none !important;
  margin: 0 !important;
}

@supports not (height: 100dvh) {
  :deep(.flex.h-screen.overflow-hidden),
  :deep(.flex-center.relative.w-full) {
    height: 100vh !important;
  }
}
</style>
