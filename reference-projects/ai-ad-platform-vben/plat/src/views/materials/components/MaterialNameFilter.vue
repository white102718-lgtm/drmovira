<script setup lang="ts">
import { Input } from 'ant-design-vue';

const props = withDefaults(
  defineProps<{ id?: string; singleRow?: boolean; value: string }>(),
  {
    singleRow: false,
  },
);
const emit = defineEmits<{
  'update:value': [value: string];
}>();
</script>

<template>
  <Input.TextArea
    :id="id"
    :value="value"
    :auto-size="singleRow ? { minRows: 1, maxRows: 1 } : false"
    :rows="singleRow ? 1 : 2"
    allow-clear
    class="material-name-filter"
    :class="{ 'material-name-filter-single-row': props.singleRow }"
    aria-label="素材名称，每行一个"
    placeholder="输入系统素材名，每行一个"
    @update:value="(value) => emit('update:value', value)"
  />
</template>

<style scoped>
/* 固定两行高度；批量粘贴后只在输入框内滚动，不推挤文件夹列表。 */
.material-name-filter:not(.material-name-filter-single-row) :deep(textarea),
textarea.material-name-filter:not(.material-name-filter-single-row) {
  height: 64px;
  min-height: 64px;
  max-height: 64px;
  overflow-y: auto;
  overscroll-behavior-y: contain;
  resize: none;
}

.material-name-filter-single-row :deep(textarea),
textarea.material-name-filter-single-row {
  overscroll-behavior-y: contain;
  resize: none;
}
</style>
