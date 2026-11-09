<script setup lang="ts">
import type { StyleValue } from 'vue';

import type { PageProps } from './types';

import { computed, nextTick, onMounted, ref, useTemplateRef } from 'vue';

import { CSS_VARIABLE_LAYOUT_CONTENT_HEIGHT } from '@vben-core/shared/constants';
import { cn } from '@vben-core/shared/utils';

defineOptions({
  name: 'Page',
});

const { autoContentHeight = false, heightOffset = 0 } =
  defineProps<PageProps>();

const headerHeight = ref(0);
const footerHeight = ref(0);
const shouldAutoHeight = ref(false);

const headerRef = useTemplateRef<HTMLDivElement>('headerRef');
const footerRef = useTemplateRef<HTMLDivElement>('footerRef');

const contentStyle = computed<StyleValue>(() => {
  if (autoContentHeight) {
    return {
      height: `calc(var(${CSS_VARIABLE_LAYOUT_CONTENT_HEIGHT}) - ${headerHeight.value}px - ${typeof heightOffset === 'number' ? `${heightOffset}px` : heightOffset})`,
      overflowY: shouldAutoHeight.value ? 'auto' : 'unset',
    };
  }
  return {};
});

async function calcContentHeight() {
  if (!autoContentHeight) {
    return;
  }
  await nextTick();
  headerHeight.value = headerRef.value?.offsetHeight || 0;
  footerHeight.value = footerRef.value?.offsetHeight || 0;
  setTimeout(() => {
    shouldAutoHeight.value = true;
  }, 30);
}

onMounted(() => {
  calcContentHeight();
});
</script>

<template>
  <div class="vben-page relative min-w-0">
    <div
      v-if="
        description ||
        $slots.description ||
        title ||
        $slots.title ||
        $slots.extra
      "
      ref="headerRef"
      :class="
        cn(
          'vben-page__header bg-card border-border relative flex min-w-0 items-center gap-4 border-b px-6 py-4',
          headerClass,
        )
      "
    >
      <div class="vben-page__heading min-w-0 flex-auto">
        <slot name="title">
          <div
            v-if="title"
            class="vben-page__title mb-1 flex text-lg font-semibold leading-6"
          >
            {{ title }}
          </div>
        </slot>

        <slot name="description">
          <p
            v-if="description"
            class="vben-page__description text-muted-foreground mb-0 text-sm leading-5"
          >
            {{ description }}
          </p>
        </slot>
      </div>

      <div v-if="$slots.extra" class="vben-page__extra shrink-0">
        <slot name="extra"></slot>
      </div>
    </div>

    <div
      :class="cn('vben-page__content h-full min-w-0 p-4', contentClass)"
      :style="contentStyle"
    >
      <slot></slot>
    </div>

    <div
      v-if="$slots.footer"
      ref="footerRef"
      :class="
        cn(
          'bg-card align-center absolute bottom-0 left-0 right-0 flex px-6 py-4',
          footerClass,
        )
      "
    >
      <slot name="footer"></slot>
    </div>
  </div>
</template>
