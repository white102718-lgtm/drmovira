<template>
  <div v-if="inline && modelValue" class="prototype-surface">
    <slot />
    <footer class="prototype-footer"><slot name="footer" /></footer>
  </div>
  <el-drawer v-else-if="!inline" v-bind="$attrs" :model-value="modelValue"
    ><slot /><template #footer><slot name="footer" /></template
  ></el-drawer>
</template>
<script setup lang="ts">
defineOptions({ inheritAttrs: false })
defineProps<{ inline?: boolean; modelValue: boolean }>()
</script>
<style scoped>
.prototype-surface {
  max-width: 1280px;
  margin: auto;
}
.prototype-footer {
  background: white;
  padding: 14px 18px;
  margin-top: 16px;
  border-radius: 8px;
}
</style>
