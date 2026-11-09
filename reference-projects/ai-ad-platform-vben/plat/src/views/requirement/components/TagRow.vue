<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';

import { useElementSize } from '@vueuse/core';
import { Popover } from 'ant-design-vue';

const props = defineProps<{ tags: string[] }>();

const containerRef = ref<HTMLElement | null>(null);
const visibleCount = ref(props.tags.length);
const { width } = useElementSize(containerRef);

// +N 徽章预估宽度
const BADGE_WIDTH = 40;

async function measure() {
  // 先重置为全部展示，等 DOM 更新后再测量实际宽度
  visibleCount.value = props.tags.length;
  await nextTick();

  const container = containerRef.value;
  if (!container || props.tags.length === 0) return;

  const tagEls = Array.from(
    container.querySelectorAll<HTMLElement>('.tag-item'),
  );
  if (tagEls.length === 0) return;

  const containerRight = container.getBoundingClientRect().right;
  let count = tagEls.length;

  for (let i = 0; i < tagEls.length; i++) {
    const el = tagEls[i]!;
    const elRight = el.getBoundingClientRect().right;
    // 不是最后一个时，需为 +N 徽章预留空间
    const limit =
      i === tagEls.length - 1 ? containerRight : containerRight - BADGE_WIDTH;

    if (elRight > limit) {
      count = i;
      break;
    }
  }

  visibleCount.value = Math.max(1, count);
}

// 容器宽度变化（列宽拖拽、窗口缩放）或 tags 数据变化时重新测量
watch([width, () => props.tags], measure, { immediate: true });
</script>

<template>
  <div
    ref="containerRef"
    class="flex items-center gap-1 mt-1 flex-nowrap overflow-hidden"
  >
    <span
      v-for="(tag, i) in tags"
      :key="tag"
      v-show="i < visibleCount"
      class="tag-item inline-flex items-center text-xs text-gray-400 bg-gray-50 border border-gray-100 rounded px-1.5 py-0.5 whitespace-nowrap flex-shrink-0"
    >{{ tag }}</span>

    <Popover
      v-if="visibleCount < tags.length"
      placement="bottom"
      trigger="click"
    >
      <template #content>
        <div class="flex flex-wrap gap-1.5 max-w-[275px] py-1">
          <span
            v-for="tag in tags.slice(visibleCount)"
            :key="tag"
            class="inline-flex items-center text-xs text-gray-400 bg-gray-50 border border-gray-100 rounded px-1.5 py-0.5 whitespace-nowrap"
          >{{ tag }}</span>
        </div>
      </template>
      <span
        class="inline-flex items-center text-xs text-gray-400 bg-gray-50 border border-dashed border-gray-200 rounded px-1.5 py-0.5 cursor-pointer hover:border-gray-400 hover:text-gray-600 flex-shrink-0"
        @click.stop
      >+{{ tags.length - visibleCount }}</span>
    </Popover>
  </div>
</template>
