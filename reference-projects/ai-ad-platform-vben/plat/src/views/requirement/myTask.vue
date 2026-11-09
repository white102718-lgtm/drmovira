<script setup lang="ts">
import { onBeforeMount } from 'vue';
import { useRoute, useRouter } from 'vue-router';

defineOptions({ name: 'RequirementMyTask' });

const route = useRoute();
const router = useRouter();

onBeforeMount(() => {
  void router.replace({
    path: '/workbench/tasks',
    query: { ...route.query, source: 'material' },
  });
});
</script>

<template>
  <div
    class="adpulse-section-page bg-muted/40 text-muted-foreground grid h-full place-items-center text-sm"
  >
    正在前往任务中心…
  </div>
</template>
