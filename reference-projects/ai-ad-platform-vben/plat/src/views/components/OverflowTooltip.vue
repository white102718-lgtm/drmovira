<script setup lang="ts">
import { ref } from 'vue';

import Tooltip from 'ant-design-vue/es/tooltip';

defineProps<{ text: string; overlayStyle?: Record<string, string> }>();

const textRef = ref<HTMLElement | null>(null);
const isOverflow = ref(false);

function checkOverflow() {
  const el = textRef.value;
  if (el) isOverflow.value = el.scrollWidth > el.clientWidth;
}
</script>

<template>
  <Tooltip :title="isOverflow ? text : undefined" :overlay-style="overlayStyle">
      <div
        ref="textRef"
        class="overflow-hidden text-ellipsis whitespace-nowrap"
        @mouseenter="checkOverflow"
      >
        {{ text }}
      </div>
  </Tooltip>
</template>
