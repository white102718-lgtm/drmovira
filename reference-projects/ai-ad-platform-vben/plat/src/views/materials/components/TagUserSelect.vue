<script lang="ts" setup>
import { onMounted, ref } from 'vue';

import { Select } from 'ant-design-vue';

import { getUserOptions } from '#/api/system/user';

interface Props {
  disabled?: boolean;
  modelValue?: string | undefined;
  placeholder?: string;
  style?: Record<string, any>;
}

interface Emits {
  (e: 'change', value: string | undefined): void;
  (e: 'update:modelValue', value: string | undefined): void;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '选择用户',
  disabled: false,
});

const emit = defineEmits<Emits>();

const userOptions = ref<Array<{ label: string; value: string }>>([]);
const loading = ref(false);

const loadOptions = async () => {
  try {
    loading.value = true;
    const response = await getUserOptions(['operator', 'operator_leader']);
    userOptions.value = response.map((user: string) => ({
      label: user,
      value: user,
    }));
  } catch (error) {
  } finally {
    loading.value = false;
  }
};

const handleChange = (value: string | undefined) => {
  emit('update:modelValue', value);
  emit('change', value);
};

onMounted(() => {
  loadOptions();
});
</script>

<template>
  <Select
    :value="modelValue"
    :options="userOptions"
    :loading="loading"
    :disabled="disabled"
    show-search
    allow-clear
    :placeholder="placeholder"
    :style="style"
    :filter-option="
      (input: string, option: any) =>
        option.label.toLowerCase().includes(input.toLowerCase())
    "
    @change="handleChange"
  />
</template>
```
