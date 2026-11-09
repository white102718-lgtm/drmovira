<script lang="ts" setup>
import { Bell, X } from 'lucide-vue-next';

interface ToastNotification {
  date: string;
  id: string;
  message: string;
  title: string;
}

defineProps<{ items: ToastNotification[] }>();

const emit = defineEmits<{
  close: [id: string];
  view: [item: ToastNotification];
}>();
</script>

<template>
  <div
    class="site-notification-toast-stack"
    aria-atomic="false"
    aria-live="polite"
  >
    <TransitionGroup name="site-notification-toast">
      <article
        v-for="item in items"
        :key="item.id"
        class="bg-card text-card-foreground relative overflow-hidden rounded-xl shadow-lg"
      >
        <button
          type="button"
          class="hover:bg-muted/50 focus-visible:ring-ring flex w-full gap-3 px-4 py-3.5 pr-12 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset"
          :aria-label="`查看系统通知：${item.title}`"
          @click="emit('view', item)"
        >
          <span
            class="bg-muted text-foreground mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg"
            aria-hidden="true"
          >
            <Bell class="size-4" :stroke-width="1.8" />
          </span>
          <span class="min-w-0 flex-1">
            <strong class="block truncate text-sm font-semibold leading-5">
              {{ item.title }}
            </strong>
            <span
              class="text-muted-foreground mt-1 line-clamp-2 block text-sm leading-5"
            >
              {{ item.message }}
            </span>
            <time class="text-muted-foreground mt-1.5 block text-xs leading-4">
              {{ item.date }}
            </time>
          </span>
        </button>
        <button
          type="button"
          class="text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring absolute right-2 top-2 flex size-8 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2"
          :aria-label="`关闭通知：${item.title}`"
          @click="emit('close', item.id)"
        >
          <X class="size-4" aria-hidden="true" />
        </button>
      </article>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.site-notification-toast-stack {
  position: fixed;
  z-index: 1100;
  top: 72px;
  right: 16px;
  display: grid;
  width: min(360px, calc(100vw - 32px));
  gap: 8px;
  pointer-events: none;
}

.site-notification-toast-stack > * {
  pointer-events: auto;
}

.site-notification-toast-enter-active,
.site-notification-toast-leave-active {
  transition:
    transform 240ms cubic-bezier(0.16, 1, 0.3, 1),
    opacity 180ms ease-out;
}

.site-notification-toast-enter-from,
.site-notification-toast-leave-to {
  opacity: 0;
  transform: translateX(24px);
}

.site-notification-toast-move {
  transition: transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
}

@media (max-width: 640px) {
  .site-notification-toast-stack {
    top: 60px;
    right: 12px;
    width: calc(100vw - 24px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .site-notification-toast-enter-active,
  .site-notification-toast-leave-active,
  .site-notification-toast-move {
    transition: none;
  }
}
</style>
