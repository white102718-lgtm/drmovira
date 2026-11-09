import type { FilterOptions } from '#/api/dashboard/data-report';

import { onBeforeUnmount, onMounted, ref } from 'vue';

import { getFilterOptions } from '#/api/dashboard';

/** 三个素材页签均从 ERP 公共选项加载，日期及报表结果不改变候选项。 */
export function useMaterialFilterOptions() {
  const filterOptions = ref<FilterOptions | null>(null);
  const optionsLoading = ref(false);
  const optionsError = ref(false);
  let active = true;

  async function reloadOptions() {
    if (optionsLoading.value) return;
    optionsLoading.value = true;
    optionsError.value = false;
    try {
      const result = await getFilterOptions();
      if (active) filterOptions.value = result;
    } catch {
      if (active) optionsError.value = true;
    } finally {
      if (active) optionsLoading.value = false;
    }
  }

  onMounted(reloadOptions);
  onBeforeUnmount(() => {
    active = false;
  });
  return { filterOptions, optionsError, optionsLoading, reloadOptions };
}
