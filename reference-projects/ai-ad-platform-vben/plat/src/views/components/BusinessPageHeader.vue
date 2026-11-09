<script lang="ts" setup>
import { useId } from 'vue';

import Card from 'ant-design-vue/es/card';
import { IconifyIcon } from '@vben/icons';

interface Props {
  compact?: boolean;
  description: string;
  icon?: string;
  title: string;
}

defineOptions({ name: 'BusinessPageHeader' });
const props = withDefaults(defineProps<Props>(), {
  compact: false,
});

const titleId = useId();
</script>

<template>
  <header :aria-labelledby="titleId">
    <Card
      v-if="!props.compact"
      :body-style="{
        padding:
          'var(--adpulse-page-header-padding-block) var(--adpulse-page-gutter)',
      }"
      class="business-page-header"
    >
      <div
        class="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
      >
        <div class="flex min-w-0 items-center gap-2.5">
          <span
            v-if="icon"
            aria-hidden="true"
            class="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-lg text-base"
          >
            <IconifyIcon :icon="icon" />
          </span>
          <div class="min-w-0">
            <h1
              :id="titleId"
              class="text-foreground m-0 font-semibold leading-5 text-[var(--adpulse-page-title-size)]"
            >
              {{ title }}
            </h1>
            <p
              class="text-muted-foreground mb-0 mt-0.5 max-w-3xl text-[13px] leading-[18px]"
            >
              {{ description }}
            </p>
          </div>
        </div>

        <div
          v-if="$slots.extra"
          class="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end"
        >
          <slot name="extra"></slot>
        </div>
      </div>
    </Card>
    <div
      v-else
      class="flex flex-col gap-2 py-1 sm:flex-row sm:items-center sm:justify-between"
    >
      <div class="flex min-w-0 items-start gap-2.5">
        <span
          v-if="icon"
          aria-hidden="true"
          class="bg-muted text-foreground grid size-8 shrink-0 place-items-center rounded-md"
        >
          <IconifyIcon :icon="icon" />
        </span>
        <div class="min-w-0">
          <h1
            :id="titleId"
            class="text-foreground m-0 font-semibold leading-5 text-[var(--adpulse-page-title-size)]"
          >
            {{ title }}
          </h1>
          <p
            class="text-muted-foreground mb-0 mt-0.5 max-w-3xl text-[13px] leading-[18px]"
          >
            {{ description }}
          </p>
        </div>
      </div>

      <div
        v-if="$slots.extra"
        class="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end"
      >
        <slot name="extra"></slot>
      </div>
    </div>
  </header>
</template>
