<script setup lang="ts">
import { IconifyIcon } from '@vben/icons';

interface Props {
  fill?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  fill: false,
});
</script>

<template>
  <div
    aria-busy="true"
    aria-label="加载中..."
    aria-live="polite"
    class="flex w-full flex-col items-center justify-center gap-3 text-center"
    :class="props.fill ? 'min-h-0 flex-1 py-6' : 'min-h-48 py-8'"
    role="status"
  >
    <div
      aria-hidden="true"
      class="grid size-10 place-items-center text-blue-600 dark:text-blue-400"
    >
      <IconifyIcon
        class="size-8 animate-spin motion-reduce:animate-none"
        icon="lucide:loader-circle"
      />
    </div>
    <p class="m-0 text-sm font-medium text-slate-500 dark:text-slate-400">
      加载中...
    </p>
  </div>
</template>
