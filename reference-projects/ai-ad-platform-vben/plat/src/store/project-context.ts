import type { ProjectOption } from '#/api';

import { computed, ref, watch } from 'vue';

import { useStorage } from '@vueuse/core';
import { defineStore } from 'pinia';

import { getProjectOptionsApi } from '#/api';

export const useProjectContextStore = defineStore(
  'fusion-project-context',
  () => {
    const projectOptions = ref<ProjectOption[]>([]);
    const selectedProjectId = useStorage('fusion:selected-project-id', '');
    const selectedDeliveryLineId = useStorage(
      'fusion:selected-delivery-line-id',
      '',
    );
    const loading = ref(false);

    const currentProject = computed(
      () =>
        projectOptions.value.find(
          (item) => item.id === selectedProjectId.value,
        ) ?? null,
    );
    const deliveryLineOptions = computed(
      () => currentProject.value?.deliveryLines ?? [],
    );
    const currentDeliveryLine = computed(
      () =>
        deliveryLineOptions.value.find(
          (item) => item.id === selectedDeliveryLineId.value,
        ) ?? null,
    );

    async function loadProjectOptions(force = false) {
      if (projectOptions.value.length > 0 && !force) return;
      loading.value = true;
      try {
        projectOptions.value = await getProjectOptionsApi();
        const selectedProject = projectOptions.value.find(
          (item) => item.id === selectedProjectId.value,
        );
        if (
          !selectedProject ||
          ['archived', 'ended'].includes(selectedProject.status)
        ) {
          selectedProjectId.value =
            projectOptions.value.find(
              (item) => !['archived', 'ended'].includes(item.status),
            )?.id ?? '';
        }
      } finally {
        loading.value = false;
      }
    }

    function selectProject(projectId: string) {
      selectedProjectId.value = projectId;
    }

    function selectDeliveryLine(deliveryLineId: string) {
      selectedDeliveryLineId.value = deliveryLineId;
    }

    watch(
      [selectedProjectId, deliveryLineOptions],
      () => {
        if (
          !deliveryLineOptions.value.some(
            (item) => item.id === selectedDeliveryLineId.value,
          )
        ) {
          selectedDeliveryLineId.value = deliveryLineOptions.value[0]?.id ?? '';
        }
      },
      { immediate: true },
    );

    return {
      currentDeliveryLine,
      currentProject,
      deliveryLineOptions,
      loadProjectOptions,
      loading,
      projectOptions,
      selectDeliveryLine,
      selectedDeliveryLineId,
      selectedProjectId,
      selectProject,
    };
  },
);
