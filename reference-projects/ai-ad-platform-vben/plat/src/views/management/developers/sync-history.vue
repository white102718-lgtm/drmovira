<script lang="ts" setup>
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { Button, Card } from 'ant-design-vue';

import SyncHistoryTable from './components/SyncHistoryTable.vue';

const route = useRoute();
const router = useRouter();

function handleBack() {
  const tab = route.query.tab === 'google' ? 'google' : 'facebook';
  void router.push({ path: '/management/developers', query: { tab } });
}
</script>

<template>
  <Page
    class="developer-management-page bg-background flex h-full min-h-0 flex-col"
    content-class="!h-auto min-h-0 flex flex-1 flex-col overflow-hidden pb-6"
    description="查看开发者账号的数据同步运行状态与错误详情。"
    title="数据同步记录"
  >
    <template #extra>
      <Button @click="handleBack">返回开发者列表</Button>
    </template>
    <Card
      class="h-full min-h-0"
      :body-style="{
        display: 'flex',
        height: '100%',
        minHeight: 0,
        padding: '16px',
      }"
    >
      <div class="ux-fill-grid-host min-h-0 min-w-0 flex-1">
        <SyncHistoryTable class="h-full" />
      </div>
    </Card>
  </Page>
</template>
