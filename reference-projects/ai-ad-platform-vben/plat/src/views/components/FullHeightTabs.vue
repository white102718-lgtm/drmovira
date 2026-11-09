<script lang="ts" setup>
import { computed, useSlots } from 'vue';

import Tabs from 'ant-design-vue/es/tabs';

interface FullHeightTabItem {
  key: string;
  label: string;
}

const props = defineProps<{
  tabs: ReadonlyArray<FullHeightTabItem>;
}>();

const emit = defineEmits<{
  change: [key: string];
}>();

const activeKey = defineModel<string>('activeKey', { required: true });
const slots = useSlots();
const activeTabLabel = computed(
  () => props.tabs.find((tab) => tab.key === activeKey.value)?.label,
);

function handleChange(key: string | number) {
  emit('change', String(key));
}
</script>

<template>
  <div
    class="full-height-tabs-layout flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
  >
    <Tabs
      v-model:active-key="activeKey"
      class="min-w-0 shrink-0"
      @change="handleChange"
    >
      <Tabs.TabPane v-for="tab in tabs" :key="tab.key" :tab="tab.label" />
      <template v-if="slots.rightExtra" #rightExtra>
        <slot name="rightExtra" />
      </template>
    </Tabs>

    <div
      :aria-label="activeTabLabel"
      class="full-height-tabs-panel min-h-0 min-w-0 flex-1 overflow-hidden"
      role="region"
    >
      <slot :active-key="activeKey" />
    </div>
  </div>
</template>
