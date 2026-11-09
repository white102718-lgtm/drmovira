<script setup lang="ts">
defineProps<{
  no: string;
  title: string;
  subtitle?: string;
  mb?: string;
}>();
</script>

<template>
  <div class="flex items-start justify-between" :class="mb || 'mb-5'">
    <div>
      <div class="text-xs text-gray-400 leading-none mb-1">{{ no }}</div>
      <div class="flex items-center gap-2">
        <h2 class="text-xl font-bold text-gray-900 leading-tight">{{ title }}</h2>
        <slot name="title-action" />
      </div>
      <p v-if="subtitle" class="text-xs text-gray-600 mt-1">{{ subtitle }}</p>
    </div>
    <slot name="right" />
  </div>
</template>
