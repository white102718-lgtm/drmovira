<script lang="ts" setup>
import { onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import FullHeightTabs from '#/views/components/FullHeightTabs.vue';
import MaterialStatistics from '#/views/dashboard/material-statistics.vue';

import MaterialBoard from './material-board.vue';
import PersonnelConsumptionRanking from './material-dashboard.vue';
import TeamCapacity from './team-capacity.vue';

const route = useRoute();
const router = useRouter();
const validTabs = new Set(['board', 'capacity', 'statistics', 'personnel']);
const activeTab = ref('board');
const tabs = [
  { key: 'board', label: '素材看板' },
  { key: 'statistics', label: '素材效果统计' },
  { key: 'capacity', label: '团队产能' },
  { key: 'personnel', label: '人员消耗排行' },
];

function syncTabFromRoute() {
  const queryTab = Array.isArray(route.query.tab)
    ? route.query.tab[0]
    : route.query.tab;
  if (typeof queryTab === 'string' && validTabs.has(queryTab)) {
    activeTab.value = queryTab;
  }
}

onMounted(syncTabFromRoute);
watch(() => route.query.tab, syncTabFromRoute);
watch(activeTab, (tab) => {
  router.replace({ query: { ...route.query, tab } });
});
</script>

<template>
  <div
    class="adpulse-section-page adpulse-tabs-page adpulse-full-height-tabs-page material-insights bg-background h-full min-h-0"
  >
    <div class="material-insights-workspace flex h-full min-h-0 flex-col">
      <FullHeightTabs
        v-model:active-key="activeTab"
        class="min-h-0 flex-1"
        :tabs="tabs"
      >
        <div
          v-show="activeTab === 'board'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <MaterialBoard />
        </div>
        <div
          v-show="activeTab === 'statistics'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <MaterialStatistics />
        </div>
        <div
          v-show="activeTab === 'capacity'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <TeamCapacity />
        </div>
        <div
          v-show="activeTab === 'personnel'"
          class="full-height-tabs-content h-full min-h-0 min-w-0 overflow-hidden"
        >
          <PersonnelConsumptionRanking />
        </div>
      </FullHeightTabs>
    </div>
  </div>
</template>

<style scoped>
.material-insights-workspace {
  box-sizing: border-box;
  padding: var(--adpulse-card-padding);
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: var(--adpulse-page-radius);
  box-shadow: var(--adpulse-card-shadow);
}
</style>
