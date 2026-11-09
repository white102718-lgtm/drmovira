<script lang="ts" setup>
import { onMounted, ref, watch } from 'vue';

import { Select } from 'ant-design-vue';

import { getDepartmentOptions } from '#/api/management/platform-config';

interface Props {
  /** 是否允许清空 */
  allowClear?: boolean;
  /** 是否禁用 */
  disabled?: boolean;
  /** 当前选中的值 */
  modelValue?: string | string[] | undefined;
  /** 是否多选 */
  multiple?: boolean;
  /** 外部传入的选项数据 */
  options?: Array<{ label: string; value: string }>;
  /** 占位符文本 */
  placeholder?: string;
  /** 是否可搜索 */
  showSearch?: boolean;
  /** 选择器原生尺寸。 */
  size?: 'large' | 'middle' | 'small';
  /** 自定义样式 */
  style?: Record<string, any>;
  /** 兼容旧的value prop */
  value?: string | string[] | undefined;
}

interface Emits {
  (e: 'update:modelValue', value: string | string[] | undefined): void;
  (e: 'update:value', value: string | string[] | undefined): void;
  (e: 'change', value: string | string[] | undefined): void;
}

const props = withDefaults(defineProps<Props>(), {
  multiple: false,
  showSearch: true,
  allowClear: true,
  placeholder: '请选择部门',
  disabled: false,
});

const emit = defineEmits<Emits>();

const loading = ref(false);
const departmentOptions = ref<Array<{ label: string; value: string }>>([]);

const loadOptions = async () => {
  try {
    loading.value = true;
    const response = await getDepartmentOptions();

    departmentOptions.value = response.map((name: string) => ({
      label: name,
      value: name,
    }));
  } catch (error) {
  } finally {
    loading.value = false;
  }
};

const handleChange = (value: unknown) => {
  const normalizedValue = Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : typeof value === 'string'
      ? value
      : undefined;
  emit('update:modelValue', normalizedValue);
  emit('update:value', normalizedValue);
  emit('change', normalizedValue);
};

// 监听外部传入的选项数据变化
watch(
  () => props.options,
  (newOptions) => {
    if (newOptions && newOptions.length > 0) {
      departmentOptions.value = newOptions;
    }
  },
  { immediate: true },
);

onMounted(() => {
  // 如果外部没有传入选项数据，则发起请求
  if (!props.options || props.options.length === 0) {
    loadOptions();
  }
});

// 导出刷新方法
const refresh = () => {
  loadOptions();
};

defineExpose({
  refresh,
  departmentOptions,
});
</script>

<template>
  <Select
    :value="modelValue || value"
    :options="departmentOptions"
    :max-tag-count="multiple ? 'responsive' : undefined"
    :mode="multiple ? 'multiple' : undefined"
    :show-search="showSearch"
    :size="size"
    :allow-clear="allowClear"
    :placeholder="placeholder"
    :style="{ minWidth: '120px', ...style }"
    :disabled="disabled"
    :loading="loading"
    :filter-option="
      (input: string, option: any) =>
        option.label.toLowerCase().includes(input.toLowerCase())
    "
    @change="handleChange"
  />
</template>
