<script setup lang="ts">
import { computed, ref, watch } from 'vue';

import { Check, Palette } from '@vben/icons';
import { preferences, updatePreferences } from '@vben/preferences';
import { TinyColor } from '@vben/utils';

import Button from 'ant-design-vue/es/button';
import Input from 'ant-design-vue/es/input';
import Popover from 'ant-design-vue/es/popover';
import Tooltip from 'ant-design-vue/es/tooltip';

import { $t } from '#/locales';

interface ThemeColorOption {
  color: string;
  labelKey: string;
}

interface ThemeColorGroup {
  labelKey: string;
  options: ThemeColorOption[];
}

const themeColorGroups: ThemeColorGroup[] = [
  {
    labelKey: 'page.themeColor.softGroup',
    options: [
      { color: '#5B8DEF', labelKey: 'page.themeColor.colors.softBlue' },
      { color: '#6F86D6', labelKey: 'page.themeColor.colors.mistyBlue' },
      { color: '#5C9C8A', labelKey: 'page.themeColor.colors.sageGreen' },
      { color: '#8A7CC9', labelKey: 'page.themeColor.colors.grayPurple' },
      { color: '#C17860', labelKey: 'page.themeColor.colors.terracotta' },
    ],
  },
  {
    labelKey: 'page.themeColor.darkGroup',
    options: [
      { color: '#274C77', labelKey: 'page.themeColor.colors.deepSeaBlue' },
      { color: '#2F5D50', labelKey: 'page.themeColor.colors.inkGreen' },
      { color: '#51447A', labelKey: 'page.themeColor.colors.indigoPurple' },
      { color: '#7A4540', labelKey: 'page.themeColor.colors.darkRedBrown' },
    ],
  },
];

const open = ref(false);
const customColor = ref('#5B8DEF');
const customColorTouched = ref(false);

const themeColors = themeColorGroups.flatMap((group) => group.options);
const isCustomColorSelected = computed(
  () => !themeColors.some((option) => isSelected(option.color)),
);
const isCustomColorValid = computed(() =>
  /^#[\dA-F]{6}$/i.test(customColor.value.trim()),
);
const showCustomColorError = computed(
  () => customColorTouched.value && !isCustomColorValid.value,
);

function normalizeHexColor(color: string) {
  const normalizedColor = new TinyColor(color);
  return normalizedColor.isValid
    ? normalizedColor.toHexString().toUpperCase()
    : '#5B8DEF';
}

function isSelected(color: string) {
  return (
    normalizeHexColor(preferences.theme.colorPrimary) ===
    normalizeHexColor(color)
  );
}

function updateThemeColor(color: string) {
  updatePreferences({
    theme: {
      colorPrimary: normalizeHexColor(color),
      mode: 'light',
      semiDarkHeader: false,
      semiDarkSidebar: false,
    },
  });
}

function handleSelect(color: string) {
  updateThemeColor(color);
  open.value = false;
}

function handleCustomColorInput(event: Event) {
  const target = event.target as HTMLInputElement;
  // 原生取色器拖动时会高频触发 input；这里只更新草稿，避免反复重建全局主题和关闭浮层。
  customColor.value = normalizeHexColor(target.value);
  customColorTouched.value = false;
}

function handleCustomHexInput(value: string) {
  customColor.value = value;
  customColorTouched.value = true;
}

function handleApplyCustomColor() {
  customColorTouched.value = true;
  if (!isCustomColorValid.value) return;

  customColor.value = normalizeHexColor(customColor.value.trim());
  updateThemeColor(customColor.value);
  open.value = false;
}

watch(open, (isOpen) => {
  if (!isOpen) return;
  customColor.value = normalizeHexColor(preferences.theme.colorPrimary);
  customColorTouched.value = false;
});
</script>

<template>
  <Popover v-model:open="open" placement="bottomRight" trigger="click">
    <template #content>
      <div
        class="theme-color-panel"
        :aria-label="$t('page.themeColor.options')"
      >
        <section
          v-for="group in themeColorGroups"
          :key="group.labelKey"
          class="theme-color-section"
        >
          <h3 class="theme-color-section-title">{{ $t(group.labelKey) }}</h3>
          <div role="listbox">
            <button
              v-for="option in group.options"
              :key="option.color"
              :aria-label="`${$t('page.themeColor.switchTo')}${$t(option.labelKey)}`"
              :aria-selected="isSelected(option.color)"
              class="theme-color-option"
              role="option"
              type="button"
              @click="handleSelect(option.color)"
            >
              <span
                :style="{ backgroundColor: option.color }"
                class="theme-color-swatch"
                aria-hidden="true"
              >
                <Check v-if="isSelected(option.color)" class="size-3.5" />
              </span>
              <span>{{ $t(option.labelKey) }}</span>
            </button>
          </div>
        </section>

        <section class="theme-color-custom">
          <h3 class="theme-color-section-title">
            {{ $t('page.themeColor.custom') }}
          </h3>
          <div class="theme-color-custom-controls">
            <div class="theme-color-picker-wrap">
              <input
                :aria-label="$t('page.themeColor.customPicker')"
                :value="normalizeHexColor(customColor)"
                class="theme-color-picker"
                type="color"
                @input="handleCustomColorInput"
              />
              <Check
                v-if="isCustomColorSelected"
                class="theme-color-custom-check size-3.5"
                aria-hidden="true"
              />
            </div>
            <Input
              :aria-describedby="
                showCustomColorError ? 'theme-color-hex-error' : undefined
              "
              :aria-invalid="showCustomColorError"
              :maxlength="7"
              :placeholder="$t('page.themeColor.hexPlaceholder')"
              :status="showCustomColorError ? 'error' : undefined"
              :value="customColor"
              autocomplete="off"
              spellcheck="false"
              @blur="customColorTouched = true"
              @press-enter="handleApplyCustomColor"
              @update:value="handleCustomHexInput"
            />
            <Button
              :disabled="!isCustomColorValid"
              type="primary"
              @click="handleApplyCustomColor"
            >
              {{ $t('page.themeColor.apply') }}
            </Button>
            <p
              v-if="showCustomColorError"
              id="theme-color-hex-error"
              class="theme-color-error"
              role="alert"
            >
              {{ $t('page.themeColor.invalidHex') }}
            </p>
          </div>
        </section>
      </div>
    </template>

    <Tooltip :title="$t('page.themeColor.trigger')">
      <Button
        type="text"
        :aria-label="$t('page.themeColor.trigger')"
        class="theme-color-trigger"
        shape="circle"
      >
        <Palette class="size-4" aria-hidden="true" />
      </Button>
    </Tooltip>
  </Popover>
</template>

<style scoped>
.theme-color-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--adpulse-text-muted);
}

.theme-color-trigger:hover,
.theme-color-trigger:focus-visible {
  color: var(--adpulse-primary);
  background: var(--adpulse-primary-soft);
}

.theme-color-panel {
  display: grid;
  gap: 12px;
  width: min(248px, calc(100vw - 32px));
}

.theme-color-section-title {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 600;
  line-height: 20px;
  color: var(--adpulse-text-muted);
}

.theme-color-option {
  display: flex;
  gap: 10px;
  align-items: center;
  min-height: 36px;
  padding: 6px 8px;
  font-size: 13px;
  color: var(--adpulse-text);
  text-align: left;
  background: transparent;
  border: 0;
  border-radius: 8px;
}

.theme-color-option:hover,
.theme-color-option:focus-visible,
.theme-color-option[aria-selected='true'] {
  background: var(--adpulse-primary-soft);
}

.theme-color-swatch {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  color: white;
  border: 2px solid rgb(255 255 255 / 88%);
  border-radius: 999px;
  box-shadow: 0 0 0 1px rgb(15 23 42 / 10%);
}

.theme-color-custom {
  padding-top: 12px;
  border-top: 1px solid var(--adpulse-border);
}

.theme-color-custom-controls {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: start;
}

.theme-color-picker-wrap {
  position: relative;
  width: 36px;
  height: 32px;
}

.theme-color-picker {
  width: 36px;
  height: 32px;
  padding: 2px;
  cursor: pointer;
  background: var(--adpulse-surface);
  border: 1px solid var(--adpulse-border);
  border-radius: 8px;
}

.theme-color-picker:focus-visible {
  outline: 2px solid var(--adpulse-primary);
  outline-offset: 2px;
}

.theme-color-picker::-webkit-color-swatch-wrapper {
  padding: 0;
}

.theme-color-picker::-webkit-color-swatch {
  border: 0;
  border-radius: 5px;
}

.theme-color-picker::-moz-color-swatch {
  border: 0;
  border-radius: 5px;
}

.theme-color-custom-check {
  position: absolute;
  top: 9px;
  left: 11px;
  color: white;
  pointer-events: none;
  filter: drop-shadow(0 1px 1px rgb(15 23 42 / 35%));
}

.theme-color-error {
  grid-column: 2 / -1;
  margin: -2px 0 0;
  font-size: 12px;
  line-height: 18px;
  color: var(--ant-color-error, #ff4d4f);
}
</style>
