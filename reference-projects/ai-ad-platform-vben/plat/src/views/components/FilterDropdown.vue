<script setup lang="ts">
/**
 * 通用列表筛选控件。
 *
 * 统一使用 Ant Design Vue Select，使筛选条件与页面表单使用相同的尺寸、
 * 键盘行为和无障碍语义；多选值直接透传给调用页面，避免增加数据转换层。
 */
import { computed } from 'vue';

import Select from 'ant-design-vue/es/select';

interface Option {
  label: string;
  value: string;
}

interface Props {
  clearable?: boolean;
  emptyText?: string;
  label: string;
  loading?: boolean;
  modelValue?: string | string[];
  multiple?: boolean;
  options?: Option[];
  placeholder?: string;
  searchable?: boolean;
  width?: string;
}

const props = withDefaults(defineProps<Props>(), {
  clearable: true,
  emptyText: '无匹配项',
  loading: false,
  modelValue: undefined,
  multiple: false,
  options: () => [],
  placeholder: '全部',
  searchable: true,
  width: 'var(--adpulse-filter-field-width)',
});

const emit = defineEmits<{
  'update:modelValue': [string | string[] | undefined];
}>();

const selectedValue = computed({
  get: () => props.modelValue,
  set: (value: string | string[] | undefined) =>
    emit('update:modelValue', value),
});

const inputStyle = computed(() => ({ width: props.width }));
</script>

<template>
  <label class="inline-flex min-w-0 items-center gap-2 text-sm">
    <span class="ux-filter-label w-16 shrink-0 text-slate-600">
      {{ label }}
    </span>
    <Select
      v-model:value="selectedValue"
      :allow-clear="clearable"
      :loading="loading"
      :mode="multiple ? 'multiple' : undefined"
      :not-found-content="loading ? '加载中…' : emptyText"
      :options="options"
      :placeholder="placeholder"
      :show-search="searchable"
      :style="inputStyle"
      option-filter-prop="label"
    />
  </label>
</template>
