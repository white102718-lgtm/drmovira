<script lang="ts" setup>
import { computed, onUnmounted } from 'vue';

import { AuthPageLayout } from '@vben/layouts';
import { preferences } from '@vben/preferences';

import { $t } from '#/locales';

const appName = computed(() => preferences.app.name);
const logo = computed(() => preferences.logo.source);
const clickLogo = () => {};
let pointerFrame: null | number = null;

function handlePointerMove(event: PointerEvent) {
  if (event.pointerType === 'touch' || pointerFrame !== null) return;
  const shell = event.currentTarget;
  if (!(shell instanceof HTMLElement)) return;

  pointerFrame = requestAnimationFrame(() => {
    const bounds = shell.getBoundingClientRect();
    shell.style.setProperty('--grid-x', `${event.clientX - bounds.left}px`);
    shell.style.setProperty('--grid-y', `${event.clientY - bounds.top}px`);
    pointerFrame = null;
  });
}

function handlePointerLeave(event: PointerEvent) {
  const shell = event.currentTarget;
  if (!(shell instanceof HTMLElement)) return;

  if (pointerFrame !== null) {
    cancelAnimationFrame(pointerFrame);
    pointerFrame = null;
  }
  shell.style.removeProperty('--grid-x');
  shell.style.removeProperty('--grid-y');
}

onUnmounted(() => {
  if (pointerFrame !== null) cancelAnimationFrame(pointerFrame);
});
</script>

<template>
  <!-- :toolbar="false"禁用工具栏 -->
  <AuthPageLayout
    class="adpulse-auth-shell"
    :app-name="appName"
    :logo="logo"
    :page-description="$t('authentication.pageDesc')"
    :page-title="$t('authentication.pageTitle')"
    :toolbar="false"
    :click-logo="clickLogo"
    @pointerleave="handlePointerLeave"
    @pointermove="handlePointerMove"
  >
    <!-- 自定义工具栏 -->
    <!-- <template #toolbar></template> -->
  </AuthPageLayout>
</template>

<style>
.adpulse-auth-shell {
  --grid-x: 72%;
  --grid-y: 38%;

  position: relative;
  background:
    radial-gradient(
      ellipse 48% 58% at 0% 100%,
      rgb(147 197 253 / 55%),
      transparent 72%
    ),
    radial-gradient(
      ellipse 42% 48% at 100% 0%,
      rgb(251 191 142 / 48%),
      transparent 72%
    ),
    #fdfefe;
}

.adpulse-auth-shell::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  background-image:
    linear-gradient(rgb(71 85 105 / 8%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(71 85 105 / 8%) 1px, transparent 1px);
  background-size: 36px 36px;
  mask-image: radial-gradient(
    260px circle at var(--grid-x) var(--grid-y),
    black 4%,
    rgb(0 0 0 / 80%) 36%,
    transparent 76%
  );
  transition: opacity 180ms ease;
}

.adpulse-auth-shell > .absolute {
  top: 24px;
  left: 50%;
  width: max-content;
  transform: translateX(-50%);
}

.adpulse-auth-shell > .absolute > div {
  gap: 8px;
  margin: 0;
}

.adpulse-auth-shell > .absolute img {
  width: 32px;
  height: 32px;
}

.adpulse-auth-shell > .absolute p {
  font-size: var(--adpulse-page-title-size);
  font-weight: 650;
  color: var(--adpulse-text);
  letter-spacing: -0.02em;
}

.adpulse-auth-shell .login-background {
  display: none;
}

.adpulse-auth-shell > .flex-center > div:last-child {
  z-index: 1;
  width: min(420px, calc(100% - 32px));
  padding: calc(var(--adpulse-card-padding) * 1.75);
  padding-bottom: calc(var(--adpulse-card-padding) * 2);
  overflow: hidden;
  background: rgb(255 255 255 / 96%);
  border: 1px solid var(--adpulse-border);
  border-radius: var(--adpulse-card-radius);
  box-shadow: var(--adpulse-elevated-shadow);
  backdrop-filter: blur(10px);
}

.adpulse-auth-shell .auth-form-title {
  font-size: calc(var(--adpulse-page-title-size) + 4px);
  line-height: 1.25;
}

.adpulse-auth-shell > .flex-center > div:last-child > .mt-6 {
  margin-top: 0;
}

@media (max-width: 640px) {
  .adpulse-auth-shell > .absolute {
    top: 20px;
  }

  .adpulse-auth-shell > .flex-center > div:last-child {
    width: calc(100% - 24px);
    padding: 24px 20px 32px;
    border-radius: var(--adpulse-card-radius);
  }
}
</style>
