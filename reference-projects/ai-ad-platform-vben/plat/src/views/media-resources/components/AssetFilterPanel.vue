<script lang="ts" setup>
import type { AssetFilterField, AssetFilterValues } from './asset-filter';

import { computed } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button, DatePicker, Input, Select, Tag } from 'ant-design-vue';

import DepartmentSelect from '../../components/DepartmentSelect.vue';
import UserSelect from '../../components/UserSelect.vue';
import {
  isAssetFilterValueActive,
  normalizeAssetFilterValues,
} from './asset-filter';

const props = defineProps<{
  compact?: boolean;
  fields: readonly AssetFilterField[];
  filterValues: AssetFilterValues;
  keyword: string;
  keywordPlaceholder?: string;
  multilineKeyword?: boolean;
  open: boolean;
  panelId: string;
  searchInputKey: string;
}>();

const emit = defineEmits<{
  'update:filterValues': [value: AssetFilterValues];
  'update:keyword': [value: string];
  'update:open': [value: boolean];
}>();

const activeFilterCount = computed(
  () =>
    Object.values(props.filterValues).filter(isAssetFilterValueActive).length,
);

const filterLabelWidth = computed(() => {
  const longestLabelUnits = props.fields.reduce((maxUnits, field) => {
    const labelUnits = Array.from(field.label).reduce(
      (units, character) =>
        units + (/[^\u0000-\u00ff]/.test(character) ? 1 : 0.58),
      0,
    );
    return Math.max(maxUnits, labelUnits);
  }, 0);

  return Math.min(128, Math.max(56, Math.ceil(longestLabelUnits * 14 + 12)));
});

const filterPanelStyle = computed(() => ({
  '--asset-filter-measured-label-width': `${filterLabelWidth.value}px`,
}));

function filterControlId(key: string) {
  return `${props.panelId}-${key.replaceAll(/[^a-zA-Z0-9_-]/g, '-')}`;
}

function scalarFilterValue(key: string) {
  const value = props.filterValues[key];
  return Array.isArray(value) ? value.join('\n') : value;
}

function updateFilterValue(key: string, value: unknown) {
  const nextValues = { ...props.filterValues };
  const field = props.fields.find((item) => item.key === key);

  if (Array.isArray(value)) {
    const normalizedValues = normalizeAssetFilterValues(
      value.map(String),
      field?.control,
    );
    if (normalizedValues.length > 0) nextValues[key] = normalizedValues;
    else delete nextValues[key];
  } else {
    const normalizedValue = typeof value === 'string' ? value : '';
    if (normalizedValue.trim()) nextValues[key] = normalizedValue;
    else delete nextValues[key];
  }
  emit('update:filterValues', nextValues);
}

function resetFilters() {
  emit('update:filterValues', {});
}
</script>

<template>
  <div
    class="asset-filter-panel flex min-w-0 flex-col"
    :class="compact ? 'gap-3' : 'gap-4'"
    :style="filterPanelStyle"
  >
    <div
      class="flex flex-col lg:flex-row lg:items-center"
      :class="compact ? 'gap-2' : 'gap-3'"
    >
      <Input.TextArea
        v-if="multilineKeyword"
        :key="searchInputKey"
        :auto-size="{ minRows: 1, maxRows: 3 }"
        :value="keyword"
        allow-clear
        autocomplete="off"
        aria-label="搜索广告账户名称或批量账户 ID"
        class="asset-filter-control asset-filter-textarea min-w-0 flex-1"
        :placeholder="keywordPlaceholder || '搜索全部资产信息'"
        @update:value="emit('update:keyword', String($event ?? ''))"
      />
      <Input.Search
        v-else
        :key="searchInputKey"
        :value="keyword"
        allow-clear
        autocomplete="off"
        aria-label="搜索全部资产信息"
        class="min-w-0 flex-1"
        :placeholder="keywordPlaceholder || '搜索全部资产信息'"
        @update:value="emit('update:keyword', String($event ?? ''))"
      />
      <div class="flex flex-wrap items-center gap-2">
        <Button
          :aria-controls="panelId"
          :aria-expanded="open"
          class="!inline-flex items-center"
          @click="emit('update:open', !open)"
        >
          <IconifyIcon aria-hidden="true" icon="lucide:list-filter" />
          {{ open ? '收起筛选' : '更多筛选' }}
          <Tag v-if="activeFilterCount" class="!m-0">
            {{ activeFilterCount }}
          </Tag>
          <IconifyIcon
            aria-hidden="true"
            :icon="open ? 'lucide:chevron-up' : 'lucide:chevron-down'"
          />
        </Button>
        <slot name="actions"></slot>
      </div>
    </div>

    <section
      v-if="open"
      :id="panelId"
      aria-label="全部资产信息筛选"
      class="border-border border-t"
      :class="compact ? 'pt-3' : 'pt-4'"
    >
      <div
        class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
        :class="compact ? 'mb-3' : 'mb-4'"
      >
        <div>
          <h3 class="text-foreground m-0 text-sm font-semibold">
            全部信息筛选
          </h3>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            下拉字段支持多选；文本字段可用空格或换行输入多个值，同一字段任一值命中即可。
          </p>
        </div>
        <Button
          v-if="activeFilterCount"
          class="self-start"
          type="text"
          @click="resetFilters"
        >
          清空筛选
        </Button>
      </div>

      <form @submit.prevent>
        <div class="asset-filter-fields">
          <div
            v-for="field in fields"
            :key="field.key"
            class="asset-filter-field min-w-0"
          >
            <label
              :for="filterControlId(field.key)"
              class="asset-filter-label text-foreground whitespace-nowrap text-sm font-medium"
              :title="field.label"
            >
              {{ field.label }}
            </label>
            <div class="min-w-0 flex-auto">
              <DatePicker
                v-if="field.control === 'date'"
                :id="filterControlId(field.key)"
                allow-clear
                class="asset-filter-control"
                :placeholder="field.placeholder || `筛选${field.label}`"
                :value="scalarFilterValue(field.key)"
                value-format="YYYY-MM-DD"
                @update:value="updateFilterValue(field.key, $event)"
              />
              <Select
                v-else-if="field.control === 'select'"
                :id="filterControlId(field.key)"
                allow-clear
                class="asset-filter-control"
                max-tag-count="responsive"
                mode="multiple"
                option-filter-prop="label"
                :options="field.options ? [...field.options] : undefined"
                :placeholder="field.placeholder || `筛选${field.label}`"
                show-search
                :value="filterValues[field.key]"
                @update:value="updateFilterValue(field.key, $event)"
              />
              <UserSelect
                v-else-if="field.control === 'user'"
                :id="filterControlId(field.key)"
                :aria-label="field.label"
                class="asset-filter-control"
                :model-value="filterValues[field.key]"
                multiple
                :placeholder="field.placeholder || `筛选${field.label}`"
                source="system"
                :style="{ width: '100%' }"
                @update:model-value="updateFilterValue(field.key, $event)"
              />
              <DepartmentSelect
                v-else-if="field.control === 'department'"
                :id="filterControlId(field.key)"
                :aria-label="field.label"
                class="asset-filter-control"
                :model-value="filterValues[field.key]"
                multiple
                :placeholder="field.placeholder || `筛选${field.label}`"
                :style="{ width: '100%' }"
                @update:model-value="updateFilterValue(field.key, $event)"
              />
              <Input.Password
                v-else-if="field.control === 'password'"
                :id="filterControlId(field.key)"
                allow-clear
                class="asset-filter-control"
                autocomplete="off"
                :placeholder="field.placeholder || `筛选${field.label}`"
                :value="scalarFilterValue(field.key)"
                @update:value="updateFilterValue(field.key, $event)"
              />
              <Input.TextArea
                v-else
                :id="filterControlId(field.key)"
                allow-clear
                autocomplete="off"
                class="asset-filter-control asset-filter-field-textarea asset-filter-textarea"
                :placeholder="field.placeholder || `筛选${field.label}`"
                :rows="1"
                :value="scalarFilterValue(field.key)"
                @update:value="updateFilterValue(field.key, $event)"
              />
            </div>
          </div>
        </div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.asset-filter-panel {
  --asset-filter-label-width: var(--asset-filter-measured-label-width);
  --asset-filter-control-width: var(--adpulse-filter-field-width, 220px);
}

.asset-filter-fields {
  display: flex;
  flex-wrap: wrap;
  gap: var(--adpulse-filter-row-gap, 12px)
    var(--adpulse-filter-column-gap, 16px);
  align-items: center;
}

.asset-filter-field {
  display: grid;
  grid-template-columns:
    var(--asset-filter-label-width)
    minmax(0, var(--asset-filter-control-width));
  flex: 1 1
    calc(
      var(--asset-filter-label-width) + var(--asset-filter-control-width) + 8px
    );
  max-width: calc(
    var(--asset-filter-label-width) + var(--asset-filter-control-width) + 8px
  );
  align-items: center;
  gap: 8px;
}

.asset-filter-label {
  overflow: hidden;
  text-align: right;
  text-overflow: ellipsis;
}

/* 筛选输入与下拉统一使用共享的 40px 控件基线。 */
.asset-filter-control {
  width: 100%;
  min-height: var(--adpulse-control-height);
}

/*
 * Ant TextArea 会把自定义 class 透传到内部 textarea，但该节点不带当前组件的
 * scoped 属性；使用自有语义 class 全局命中，避免拖拽改高及光标垂直偏移。
 */
:global(textarea.asset-filter-textarea) {
  box-sizing: border-box;
  min-height: calc(var(--adpulse-control-height) - 2px);
  padding-block: calc((var(--adpulse-control-height) - 1.5em - 2px) / 2);
  line-height: 1.5;
  resize: none;
}

/* 高级筛选保持单行视觉高度，多值换行内容在控件内部滚动。 */
.asset-filter-field-textarea {
  height: var(--adpulse-control-height);
  min-height: var(--adpulse-control-height);
  max-height: var(--adpulse-control-height);
}

@media (max-width: 639px) {
  .asset-filter-panel {
    --asset-filter-label-width: min(
      var(--asset-filter-measured-label-width),
      88px
    );
  }

  .asset-filter-field {
    width: 100%;
    max-width: none;
  }
}
</style>
