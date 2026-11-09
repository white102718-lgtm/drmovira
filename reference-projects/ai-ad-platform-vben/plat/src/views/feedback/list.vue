<script setup lang="ts">
import type {
  OnActionClickParams,
  VxeTableGridOptions,
} from '#/adapter/vxe-table';
import type { FeedbackListItem } from '#/api';

import { onMounted, ref } from 'vue';

import { Page, useVbenDrawer } from '@vben/common-ui';
import Card from 'ant-design-vue/es/card';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getFeedbackListApi, getFeedbackSummaryApi } from '#/api';

import FeedbackDetailDrawer from './components/FeedbackDetailDrawer.vue';
import { useColumns, useGridFormSchema } from './data';

const [DetailDrawer, detailDrawerApi] = useVbenDrawer({
  connectedComponent: FeedbackDetailDrawer,
  destroyOnClose: true,
});

const summaryLoading = ref(false);
const summaryItems = ref([
  { key: 'total', label: '全部反馈', value: 0 },
  { key: 'pending', label: '待跟进', value: 0 },
  { key: 'processing', label: '跟进中', value: 0 },
  { key: 'resolved', label: '已解决', value: 0 },
  { key: 'closed', label: '已关闭', value: 0 },
]);

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    actionButtonsReverse: true,
    actionWrapperClass: 'ux-vben-filter-actions',
    schema: useGridFormSchema(),
    showCollapseButton: false,
    submitOnEnter: true,
    wrapperClass: 'ux-vben-filter-form',
  },
  gridOptions: {
    columns: useColumns(onActionClick),
    proxyConfig: {
      ajax: {
        query: async ({ page }, values) =>
          getFeedbackListApi({
            ...values,
            page: page.currentPage,
            pageSize: page.pageSize,
          }),
      },
    },
    rowConfig: { keyField: 'id' },
    toolbarConfig: {
      custom: true,
      export: false,
      refresh: { code: 'query' },
      zoom: true,
    },
  } as VxeTableGridOptions<FeedbackListItem>,
  separator: false,
});

function onActionClick({ code, row }: OnActionClickParams<FeedbackListItem>) {
  if (code === 'view') detailDrawerApi.setData(row).open();
}

async function loadSummary() {
  summaryLoading.value = true;
  try {
    const summary = await getFeedbackSummaryApi();
    summaryItems.value = summaryItems.value.map((item) => ({
      ...item,
      value: summary[item.key as keyof typeof summary],
    }));
  } finally {
    summaryLoading.value = false;
  }
}

async function handleDetailSuccess() {
  await Promise.all([gridApi.query(), loadSummary()]);
}

onMounted(loadSummary);
</script>

<template>
  <Page
    auto-content-height
    content-class="!flex !min-h-0 !flex-col !overflow-hidden !p-0"
    description="集中查看用户提交的需求、问题与体验建议，并结合账号、IP、设备、附件和控制台记录完成分析。"
    title="需求反馈搜集"
  >
    <DetailDrawer @success="handleDetailSuccess" />
    <div class="flex min-h-0 flex-1 flex-col gap-4 p-4">
      <div
        aria-label="反馈状态概览"
        class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5"
      >
        <Card
          v-for="item in summaryItems"
          :key="item.key"
          class="min-w-0 shadow-none"
        >
          <div class="p-4">
            <p class="text-muted-foreground text-sm font-medium">
              {{ item.label }}
            </p>
            <p
              aria-live="polite"
              class="mt-2 text-2xl font-semibold tabular-nums tracking-tight"
            >
              {{ summaryLoading ? '—' : item.value }}
            </p>
          </div>
        </Card>
      </div>
      <div class="ux-fill-grid-host min-h-0 flex-1">
        <Grid />
      </div>
    </div>
  </Page>
</template>
