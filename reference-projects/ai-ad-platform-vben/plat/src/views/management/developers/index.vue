<script lang="ts" setup>
import { onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import FullHeightTabs from '#/views/components/FullHeightTabs.vue';

import FacebookDevelopers from './components/FacebookDevelopers.vue';
import GoogleDevelopers from './components/GoogleDevelopers.vue';

const route = useRoute();
const router = useRouter();
const activePlatform = ref('facebook');
const validTabs = new Set(['facebook', 'google']);
const tabs = [
  { key: 'facebook', label: 'Facebook' },
  { key: 'google', label: 'Google' },
];

function updateActiveKeyFromRoute() {
  const tab = route.query.tab as string;
  if (tab && validTabs.has(tab)) activePlatform.value = tab;
}

onMounted(updateActiveKeyFromRoute);

watch(
  () => route.query.tab,
  (newTab) => {
    if (newTab && validTabs.has(newTab as string)) {
      activePlatform.value = newTab as string;
    }
  },
);

watch(activePlatform, (newKey) => {
  router.replace({ query: { ...route.query, tab: newKey } });
});
</script>

<template>
  <Page
    class="adpulse-section-page adpulse-tabs-page adpulse-full-height-tabs-page developer-management-page bg-background flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
    content-class="!h-auto min-h-0 min-w-0 flex flex-1 flex-col overflow-hidden"
  >
    <div class="developer-management-workspace flex h-full min-h-0 flex-col">
      <FullHeightTabs
        v-model:active-key="activePlatform"
        class="min-h-0 flex-1"
        :tabs="tabs"
      >
        <div
          v-show="activePlatform === 'facebook'"
          class="full-height-tabs-content ux-fill-grid-host h-full min-h-0 min-w-0 overflow-hidden"
        >
          <FacebookDevelopers />
        </div>
        <div
          v-show="activePlatform === 'google'"
          class="full-height-tabs-content ux-fill-grid-host h-full min-h-0 min-w-0 overflow-hidden"
        >
          <GoogleDevelopers />
        </div>
      </FullHeightTabs>
    </div>
  </Page>
</template>

<style scoped>
.developer-management-workspace {
  box-sizing: border-box;
  padding: var(--adpulse-card-padding);
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: var(--adpulse-page-radius);
  box-shadow: var(--adpulse-card-shadow);
}
</style>
