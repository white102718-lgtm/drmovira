<script lang="ts" setup>
import type { InventoryAssetField } from './asset-types';

import { DatePicker, FormItem, Input, Select } from 'ant-design-vue';

defineProps<{
  error?: string;
  field: InventoryAssetField;
  readonly?: boolean;
}>();

const modelValue = defineModel<string>({ default: '' });
</script>

<template>
  <FormItem
    :extra="readonly ? '唯一标识创建后不可修改' : undefined"
    :help="error"
    :label="field.label"
    :required="field.required && !readonly"
    :validate-status="error ? 'error' : undefined"
  >
    <DatePicker
      v-if="field.type === 'date'"
      v-model:value="modelValue"
      allow-clear
      class="w-full"
      :disabled="readonly"
      value-format="YYYY-MM-DD"
    />
    <Select
      v-else-if="field.type === 'select'"
      v-model:value="modelValue"
      allow-clear
      :disabled="readonly"
      :options="field.options"
      :placeholder="field.placeholder || '请选择'"
    />
    <Input.Password
      v-else-if="field.type === 'password'"
      v-model:value="modelValue"
      allow-clear
      autocomplete="new-password"
      :placeholder="field.placeholder || `请输入${field.label}`"
      :readonly="readonly"
    />
    <Input
      v-else
      v-model:value="modelValue"
      allow-clear
      :maxlength="120"
      :placeholder="field.placeholder || `请输入${field.label}`"
      :readonly="readonly"
      :type="field.type === 'url' ? 'url' : 'text'"
    />
  </FormItem>
</template>
