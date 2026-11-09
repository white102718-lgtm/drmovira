<script lang="ts" setup>
import { onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();

// 平台与代理线、字段映射和产品建档已整体下线，旧链接回落至开发者管理。
onMounted(() => {
  void router.replace({
    path: '/management/developers',
    query: { ...route.query, tab: 'facebook' },
  });
});
</script>

<template>
  <div class="h-full" />
</template>
