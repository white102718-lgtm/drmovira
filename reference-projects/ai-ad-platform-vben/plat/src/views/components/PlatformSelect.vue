<script lang="ts" setup>
import { h, onMounted, ref, watch } from 'vue';

import { Select, Tooltip } from 'ant-design-vue';

import { getPlatOptions } from '#/api/management/platform-config';

interface Props {
  /** 是否允许清空 */
  allowClear?: boolean;
  /** 是否禁用 */
  disabled?: boolean;
  /** 最多显示的标签数，'responsive' 表示自适应单行 */
  maxTagCount?: 'responsive' | number;
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
  /** 尺寸 */
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
  placeholder: '请选择平台',
  disabled: false,
});

const emit = defineEmits<Emits>();

const loading = ref(false);
const platformOptions = ref<Array<{ label: string; value: string }>>([]);

const loadOptions = async () => {
  try {
    loading.value = true;
    const response = await getPlatOptions();

    if (Array.isArray(response)) {
      platformOptions.value = response.map((platform: string) => ({
        label: platform,
        value: platform,
      }));
    }
  } catch {
  } finally {
    loading.value = false;
  }
};

const handleChange = (value: string | string[] | undefined) => {
  emit('update:modelValue', value);
  emit('update:value', value);
  emit('change', value);
};

// 监听外部传入的选项数据变化
watch(
  () => props.options,
  (newOptions) => {
    if (newOptions && newOptions.length > 0) {
      platformOptions.value = newOptions;
    }
  },
  { immediate: true },
);

onMounted(() => {
  // 只有在外部未传入options属性时才发起请求
  // 如果传入了options（即使是空数组），说明由父组件统一管理
  if (props.options === undefined) {
    loadOptions();
  }
});

const maxTagPlaceholder = (omittedValues: any[]) => {
  const labels = omittedValues
    .map((v: any) => v.label ?? v.value ?? String(v))
    .join('、');
  return h(Tooltip, { title: labels }, () => `+${omittedValues.length}`);
};

// 导出刷新方法
const refresh = () => {
  loadOptions();
};

defineExpose({
  refresh,
  platformOptions,
});
</script>

<template>
  <Select
    :value="modelValue || value"
    :options="platformOptions"
    :mode="multiple ? 'multiple' : undefined"
    :show-search="showSearch"
    :allow-clear="allowClear"
    :placeholder="placeholder"
    :style="{ minWidth: '120px', ...style }"
    :size="size"
    :disabled="disabled"
    :loading="loading"
    :max-tag-count="maxTagCount"
    :max-tag-placeholder="multiple ? maxTagPlaceholder : undefined"
    :filter-option="
      (input: string, option: any) =>
        option.label.toLowerCase().includes(input.toLowerCase())
    "
    @change="handleChange"
  />
</template>
