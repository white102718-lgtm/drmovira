<script lang="ts" setup>
import CoreFallback from './CoreFallback.vue';

defineOptions({ name: 'Fallback403Demo' });
</script>

<template>
  <CoreFallback status="403" />
</template>
