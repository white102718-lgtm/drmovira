<script setup lang="ts">
import { Fallback } from '@vben/common-ui';

defineProps<{ status: '403' | '404' }>();
</script>

<template>
  <main class="core-fallback-page">
    <Fallback class="core-fallback-content" :status="status" />
  </main>
</template>

<style scoped>
.core-fallback-page {
  display: grid;
  place-items: center;
  width: 100%;
  min-height: 100%;
  padding: var(--adpulse-page-gutter);
  color: var(--adpulse-text);
  background: var(--adpulse-surface-muted);
}

.core-fallback-content {
  width: min(100%, 720px);
  min-height: min(
    560px,
    calc(100dvh - var(--adpulse-page-gutter) - var(--adpulse-page-gutter))
  );
  padding: clamp(24px, 5vw, 48px);
  background: var(--adpulse-surface);
  border: 1px solid var(--adpulse-border);
  border-radius: var(--adpulse-card-radius);
  box-shadow: var(--adpulse-card-shadow);
}

.core-fallback-content :deep(svg) {
  max-height: min(220px, 28dvh);
}

.core-fallback-content :deep(p.text-foreground) {
  margin-top: var(--adpulse-section-gap);
  font-size: calc(var(--adpulse-page-title-size) + 3px);
  font-weight: 600;
  line-height: 1.35;
}

.core-fallback-content :deep(p.text-muted-foreground) {
  margin-block: var(--adpulse-content-gap) var(--adpulse-section-gap);
  font-size: var(--adpulse-control-font-size);
}
</style>
