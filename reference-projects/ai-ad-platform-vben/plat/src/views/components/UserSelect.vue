<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue';

import { Select } from 'ant-design-vue';

import { getUserOptions } from '#/api/system/user';

import { getSharedOrganizationUsers } from './organization-options-cache';

interface Props {
  /** 是否允许清空 */
  allowClear?: boolean;
  /** 是否禁用 */
  disabled?: boolean;
  /** 当前选中的值 */
  modelValue?: string | string[] | undefined;
  /** 是否多选 */
  multiple?: boolean;
  /** 占位符文本 */
  placeholder?: string;
  /** 是否可搜索 */
  showSearch?: boolean;
  /** 选择器原生尺寸。 */
  size?: 'large' | 'middle' | 'small';
  /** 用户数据来源；资产筛选应与系统用户管理保持一致。 */
  source?: 'adpulse' | 'system';
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
  placeholder: '请选择用户',
  disabled: false,
  source: 'adpulse',
});

const emit = defineEmits<Emits>();

const loading = ref(false);
const loadFailed = ref(false);
const userOptions = ref<Array<{ label: string; value: string }>>([]);

// 内部值状态，用于处理异步数据加载
const internalValue = ref<string | string[] | undefined>(
  props.modelValue || props.value,
);

// 确保数据加载完成后才使用value
const computedValue = computed(() => {
  // 如果还在加载中，返回undefined
  if (loading.value) {
    return undefined;
  }
  // 数据加载完成后，使用内部值
  return internalValue.value;
});

const loadOptions = async () => {
  loadFailed.value = false;
  try {
    loading.value = true;

    if (props.source === 'system') {
      const users = await getSharedOrganizationUsers();
      userOptions.value = users.map((user) => ({
        label: user.displayName,
        value: user.displayName,
      }));
      return;
    }

    const response = await getUserOptions();
    userOptions.value = Array.isArray(response)
      ? response.map((name) => ({ label: name, value: name }))
      : [];
  } catch {
    userOptions.value = [];
    loadFailed.value = true;
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
  internalValue.value = normalizedValue;

  emit('update:modelValue', normalizedValue);
  emit('update:value', normalizedValue);
  emit('change', normalizedValue);
};

onMounted(() => {
  loadOptions();
});

// 监听modelValue和value变化，同步到内部值
watch(
  () => props.modelValue || props.value,
  (newValue) => {
    internalValue.value = newValue;
  },
  { immediate: true },
);

// 监听数据加载完成，如果有初始值则设置
watch(
  () => userOptions.value,
  (newData) => {
    // 数据加载完成后，如果有值，确保设置到内部值
    const currentValue = props.modelValue || props.value;
    if (newData.length > 0 && currentValue !== undefined) {
      internalValue.value = currentValue;
    }
  },
);

// 监听loading状态变化，数据加载完成后检查是否需要设置值
watch(
  () => loading.value,
  (isLoading) => {
    const currentValue = props.modelValue || props.value;
    if (!isLoading && currentValue !== undefined) {
      internalValue.value = currentValue;
    }
  },
);

// 导出刷新方法
const refresh = () => {
  loadOptions();
};

defineExpose({
  refresh,
  userOptions,
});
</script>

<template>
  <Select
    :value="computedValue"
    :options="userOptions"
    :max-tag-count="multiple ? 'responsive' : undefined"
    :mode="multiple ? 'multiple' : undefined"
    :show-search="showSearch"
    :size="size"
    :allow-clear="allowClear"
    :placeholder="placeholder"
    :style="{ minWidth: '180px', ...style }"
    :disabled="disabled"
    :loading="loading"
    :not-found-content="loadFailed ? '用户列表加载失败' : undefined"
    @change="handleChange"
  />
</template>
