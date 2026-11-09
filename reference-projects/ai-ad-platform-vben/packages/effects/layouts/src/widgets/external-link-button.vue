<script setup lang="ts">
import { VbenIconButton } from '@vben-core/shadcn-ui';

defineOptions({
  name: 'ExternalLinkButton',
});

function openExternalLink() {
  window.open('http://13.229.203.162:8088/superset/welcome/', '_blank');
}
</script>

<template>
  <VbenIconButton title="打开BI" @click="openExternalLink">
    <span class="text-la font-bold">BI</span>
  </VbenIconButton>
</template>
