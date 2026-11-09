<script setup lang="ts">
import { CountTo } from '@vben/common-ui';

const props = withDefaults(
  defineProps<{
    decimals?: number;
    duration?: number;
    prefix?: string;
    suffix?: string;
    value: number;
  }>(),
  {
    prefix: '',
    suffix: '',
    decimals: 0,
    duration: 2000,
  },
);
</script>

<template>
  <CountTo
    :end-val="props.value"
    :start-val="0"
    :duration="props.duration"
    :prefix="props.prefix"
    :suffix="props.suffix"
    :decimals="props.decimals"
  />
</template>
