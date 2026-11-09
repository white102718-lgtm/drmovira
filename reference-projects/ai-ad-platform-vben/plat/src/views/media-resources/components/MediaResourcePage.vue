<script lang="ts" setup>
import { Page } from '@vben/common-ui';

defineOptions({ name: 'MediaResourcePage' });

const props = withDefaults(
  defineProps<{
    contentClass?: string;
  }>(),
  {
    contentClass: '!p-3 sm:!p-4',
  },
);
</script>

<template>
  <Page
    class="bg-muted/30 min-h-full w-full overflow-x-hidden"
    :content-class="props.contentClass"
  >
    <div class="flex w-full min-w-0 flex-col gap-[var(--adpulse-section-gap)]">
      <slot></slot>
    </div>
  </Page>
</template>
