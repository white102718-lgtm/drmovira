<script lang="ts" setup>
import { VbenTiptap } from '@vben/plugins/tiptap';

const content = defineModel<string>({ default: '' });
</script>

<template>
  <VbenTiptap
    v-model="content"
    :min-height="200"
    :max-height="600"
    :previewable="false"
    placeholder="请输入需求描述..."
  />
</template>
