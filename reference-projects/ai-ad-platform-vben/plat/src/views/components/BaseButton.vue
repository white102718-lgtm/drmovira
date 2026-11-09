<script setup lang="ts">
import { useAttrs } from 'vue';

import Button from 'ant-design-vue/es/button';

interface Props {
  disabled?: boolean;
  loading?: boolean;
  size?: 'md' | 'sm' | 'xs';
  type?: 'button' | 'reset' | 'submit';
  variant?: 'black' | 'blue' | 'default' | 'green' | 'red' | 'red-text';
}

defineOptions({ inheritAttrs: false });

withDefaults(defineProps<Props>(), {
  disabled: false,
  loading: false,
  type: 'button',
  variant: 'default',
});

const attrs = useAttrs();

const sizeMap = {
  xs: 'small',
  sm: 'small',
  md: 'middle',
} as const;

const typeMap = {
  default: 'default',
  black: 'primary',
  blue: 'primary',
  green: 'default',
  red: 'primary',
  'red-text': 'link',
} as const;
</script>

<template>
  <Button
    v-bind="attrs"
    :aria-busy="loading || undefined"
    :danger="variant === 'red' || variant === 'red-text'"
    :disabled="disabled || loading"
    :html-type="type"
    :loading="loading"
    :size="size ? sizeMap[size] : undefined"
    :type="typeMap[variant]"
  >
    <slot></slot>
  </Button>
</template>
