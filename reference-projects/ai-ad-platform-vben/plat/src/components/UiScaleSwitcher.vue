<script setup lang="ts">
import { onMounted, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';
import { updatePreferences } from '@vben/preferences';

import Button from 'ant-design-vue/es/button';
import Popover from 'ant-design-vue/es/popover';
import Tooltip from 'ant-design-vue/es/tooltip';

import {
  applyUiScaleToDocument,
  getUiScaleDefinition,
  readStoredUiScale,
  UI_SCALE_CHANGE_EVENT,
  UI_SCALE_OPTIONS,
  UI_SCALE_STORAGE_KEY,
  type UiScale,
} from '#/constants/ui-scale';

const open = ref(false);
const currentScale = ref<UiScale>(readStoredUiScale());
const scaleOptions = UI_SCALE_OPTIONS;

function applyScale(value: UiScale) {
  const option = getUiScaleDefinition(value);

  currentScale.value = value;
  applyUiScaleToDocument(value);
  localStorage.setItem(UI_SCALE_STORAGE_KEY, value);
  updatePreferences({
    header: { height: option.headerHeight },
    sidebar: { width: option.sidebarWidth },
    tabbar: { height: option.tabbarHeight },
  });
  window.dispatchEvent(
    new CustomEvent<UiScale>(UI_SCALE_CHANGE_EVENT, { detail: value }),
  );
}

function handleSelect(value: UiScale) {
  applyScale(value);
  open.value = false;
}

onMounted(() => {
  applyScale(currentScale.value);
});
</script>

<template>
  <Popover v-model:open="open" placement="bottomRight" trigger="click">
    <template #content>
      <div class="ui-scale-panel" aria-label="页面大小选项" role="listbox">
        <button
          v-for="option in scaleOptions"
          :key="option.value"
          :aria-selected="currentScale === option.value"
          class="ui-scale-option"
          role="option"
          type="button"
          @click="handleSelect(option.value)"
        >
          <span class="ui-scale-option__indicator" aria-hidden="true">
            <IconifyIcon
              v-if="currentScale === option.value"
              icon="lucide:check"
            />
          </span>
          <span class="min-w-0 flex-1">
            <strong class="block font-medium">{{ option.label }}</strong>
            <small class="text-muted-foreground block">
              {{ option.description }}
            </small>
          </span>
        </button>
      </div>
    </template>

    <Tooltip title="页面大小">
      <Button
        :aria-label="`页面大小：${scaleOptions.find((item) => item.value === currentScale)?.label}`"
        class="ui-scale-trigger"
        shape="circle"
        type="text"
      >
        <IconifyIcon class="size-4" aria-hidden="true" icon="lucide:scan" />
      </Button>
    </Tooltip>
  </Popover>
</template>

<style scoped>
.ui-scale-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--adpulse-text-muted);
}

.ui-scale-trigger:hover,
.ui-scale-trigger:focus-visible {
  color: var(--adpulse-primary);
  background: var(--adpulse-primary-soft);
}

.ui-scale-panel {
  display: grid;
  gap: 3px;
  min-width: 220px;
}

.ui-scale-option {
  display: flex;
  gap: 8px;
  align-items: center;
  min-height: var(--adpulse-menu-item-height);
  padding: 5px 8px;
  font-size: var(--adpulse-control-font-size);
  color: var(--adpulse-text);
  text-align: left;
  background: transparent;
  border: 0;
  border-radius: 8px;
}

.ui-scale-option:hover,
.ui-scale-option:focus-visible,
.ui-scale-option[aria-selected='true'] {
  background: var(--adpulse-primary-soft);
}

.ui-scale-option__indicator {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 18px;
  height: 18px;
  color: var(--adpulse-primary);
}

.ui-scale-option__indicator :deep(svg) {
  width: 15px;
  height: 15px;
}
</style>
