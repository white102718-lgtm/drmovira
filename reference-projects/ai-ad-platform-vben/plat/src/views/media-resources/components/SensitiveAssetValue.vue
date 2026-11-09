<script lang="ts" setup>
import { computed, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button, Tooltip } from 'ant-design-vue';

const props = defineProps<{
  label: string;
  value?: string;
}>();

const isRevealed = ref(false);
const hasValue = computed(() => Boolean(props.value?.trim()));
const displayValue = computed(() => {
  if (!hasValue.value) return '-';
  return isRevealed.value ? props.value : '••••••••';
});

watch(
  () => props.value,
  () => {
    isRevealed.value = false;
  },
);
</script>

<template>
  <div class="flex min-w-0 items-center gap-1">
    <span
      class="min-w-0 flex-1 truncate font-mono"
      :title="isRevealed ? value : undefined"
    >
      {{ displayValue }}
    </span>
    <Tooltip v-if="hasValue" :title="isRevealed ? '隐藏明文' : '显示明文'">
      <Button
        :aria-label="`${isRevealed ? '隐藏' : '显示'}${label}明文`"
        class="!inline-flex !w-7 shrink-0 items-center justify-center"
        type="text"
        @click.stop="isRevealed = !isRevealed"
        @pointerdown.stop
      >
        <IconifyIcon
          aria-hidden="true"
          :icon="isRevealed ? 'lucide:eye-off' : 'lucide:eye'"
        />
      </Button>
    </Tooltip>
  </div>
</template>
