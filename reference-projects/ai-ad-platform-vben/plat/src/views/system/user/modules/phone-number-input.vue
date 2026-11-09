<script lang="ts" setup>
import { ref, watch } from 'vue';

import { Input, Select, Space } from 'ant-design-vue';

import {
  countryCallingCodeOptions,
  splitInternationalPhone,
} from './phone-number';

const props = withDefaults(
  defineProps<{
    controlSize?: 'large' | 'middle' | 'small';
    countryCodeMode?: 'input' | 'select';
    disabled?: boolean;
    value?: string;
  }>(),
  { countryCodeMode: 'select' },
);

const emit = defineEmits<{
  'update:value': [value: string];
}>();

const countryCode = ref('+86');
const nationalNumber = ref('');
let lastEmittedValue: string | undefined;

function emitPhone() {
  lastEmittedValue = `${countryCode.value}${nationalNumber.value}`;
  emit('update:value', lastEmittedValue);
}

function updateCountryCode(value: unknown) {
  if (typeof value !== 'string') return;
  countryCode.value = value;
  emitPhone();
}

function updateEditableCountryCode(value: string) {
  const digits = value.replace(/\D/g, '').slice(0, 3);
  countryCode.value = digits ? `+${digits}` : '';
  emitPhone();
}

function updateNationalNumber(value: string) {
  nationalNumber.value = value.replace(/\D/g, '').slice(0, 14);
  emitPhone();
}

defineExpose({
  getPhoneValue: () => `${countryCode.value}${nationalNumber.value}`,
});

watch(
  () => props.value,
  (value) => {
    if (value === lastEmittedValue) return;
    const phone = splitInternationalPhone(value);
    countryCode.value = phone.countryCode;
    nationalNumber.value = phone.nationalNumber;
  },
  { immediate: true },
);
</script>

<template>
  <Space.Compact
    class="w-full"
    :class="{ 'login-phone-compact': countryCodeMode === 'input' }"
    :size="controlSize"
  >
    <Input
      v-if="countryCodeMode === 'input'"
      :value="countryCode"
      autocomplete="tel-country-code"
      class="login-country-code-input"
      :disabled="disabled"
      inputmode="tel"
      :maxlength="4"
      :size="controlSize"
      style="width: 64px; flex: 0 0 64px"
      @update:value="updateEditableCountryCode"
    />
    <Select
      v-else
      :value="countryCode"
      :disabled="disabled"
      :options="countryCallingCodeOptions"
      option-filter-prop="label"
      show-search
      :size="controlSize"
      :suffix-icon="null"
      style="width: 64px; flex: 0 0 64px"
      @update:value="updateCountryCode"
    />
    <Input
      :value="nationalNumber"
      autocomplete="tel-national"
      class="login-national-number-input min-w-0 flex-1"
      :disabled="disabled"
      inputmode="numeric"
      :maxlength="14"
      placeholder="请输入手机号"
      :size="controlSize"
      @update:value="updateNationalNumber"
    />
  </Space.Compact>
</template>
