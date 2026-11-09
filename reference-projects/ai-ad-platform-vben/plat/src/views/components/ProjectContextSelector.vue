<script lang="ts" setup>
import { computed, onMounted } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Select, Tooltip } from 'ant-design-vue';

import { useProjectContextStore } from '#/store';

const projectStore = useProjectContextStore();

const projectOptions = computed(() =>
  projectStore.projectOptions.map((item) => ({
    label: item.name,
    value: item.id,
  })),
);
const deliveryLineOptions = computed(() =>
  projectStore.deliveryLineOptions.map((item) => ({
    label: item.name,
    value: item.id,
  })),
);

onMounted(() => projectStore.loadProjectOptions());
</script>

<template>
  <div
    class="project-context flex h-full min-w-0 items-center gap-2 px-2"
    aria-label="当前业务上下文"
  >
    <Tooltip title="切换项目后，工作台、素材、AI 任务和投放数据会同步切换">
      <span
        class="project-context-label flex items-center gap-1 text-xs text-slate-500"
      >
        <IconifyIcon icon="lucide:briefcase-business" class="text-base" />
        项目
      </span>
    </Tooltip>
    <Select
      :loading="projectStore.loading"
      :options="projectOptions"
      :value="projectStore.selectedProjectId"
      class="project-select w-48"
      option-filter-prop="label"
      show-search
      @change="(value) => projectStore.selectProject(String(value))"
    />
    <Select
      v-if="deliveryLineOptions.length > 0"
      :options="deliveryLineOptions"
      :value="projectStore.selectedDeliveryLineId"
      class="delivery-line-select w-36"
      size="small"
      @change="(value) => projectStore.selectDeliveryLine(String(value))"
    />
  </div>
</template>

<style scoped>
@media (max-width: 639px) {
  .project-context {
    flex: 1;
    gap: 4px;
    padding-inline: 4px;
  }

  .project-context-label,
  .delivery-line-select {
    display: none;
  }

  .project-select {
    width: min(34vw, 128px);
  }
}
</style>
