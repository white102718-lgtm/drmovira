<script setup lang="ts">
import { Page } from '@vben/common-ui';
import { useTabs } from '@vben/hooks';
import SecondaryPageHeader from '#/components/SecondaryPageHeader.vue';
import DeliveryReportPanel from './components/DeliveryReportPanel.vue';

defineOptions({ name: 'WorkbenchDailyReportApplication' });
const { closeCurrentTab } = useTabs();
</script>

<template>
  <Page auto-content-height>
    <main class="min-w-0 space-y-4 p-4 lg:p-6">
      <SecondaryPageHeader
        back-to="/workbench/daily-reports"
        card
        title="填写投放日报"
        description="按日期查询本人投放数据，确认日报消耗并补充截图后保存。"
      />
      <DeliveryReportPanel @saved="closeCurrentTab()" />
    </main>
  </Page>
</template>
