<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { SyncProgressData, SystemAccount } from '#/api';

import { ref } from 'vue';

import { Page } from '@vben/common-ui';

import {
  Button,
  message,
  Popconfirm,
  Popover,
  Progress,
  Tag,
} from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getSyncProgress, getSystemAccounts, syncPersonalAccount } from '#/api';

import TargetedSyncModal from './TargetedSyncModal.vue';

const targetedSyncOpen = ref(false);
const targetedSyncId = ref('');

const openTargetedSync = (id: string) => {
  targetedSyncId.value = id;
  targetedSyncOpen.value = true;
};

const syncProgress = ref<SyncProgressData>({});

const isInProgress = (id: string) => {
  const p = syncProgress.value[id];
  if (!p) return false;
  return p.processed !== p.total;
};

const getProgressPercent = (id: string) => {
  const p = syncProgress.value[id];
  if (!p || p.total === 0) return 0;
  return Math.min(100, Math.round((p.processed / p.total) * 100));
};

const getProgressFormat = (id: string) => () => {
  const p = syncProgress.value[id];
  if (!p || p.processed > p.total) return '';
  return `${p.processed}/${p.total}`;
};

const fetchSyncProgress = async (ids: string[]) => {
  if (ids.length === 0) return;
  const res = await getSyncProgress(ids);
  syncProgress.value = res;
};

const formOptions: VbenFormProps = {
  commonConfig: {
    colon: false,
  },
  schema: [
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '精确匹配',
      },
      fieldName: 'id',
      label: '唯一标识',
      labelClass: 'w-[60px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '正常', value: true },
          { label: '异常', value: false },
        ],
        placeholder: '全部',
      },
      fieldName: 'status',
      label: '状态',
      labelClass: 'w-[40px]',
    },
  ],
  showCollapseButton: false,
  submitOnEnter: false,
  wrapperClass:
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[repeat(2,170px)_max-content] py-1 pb-1 gap-x-3',
};

const gridOptions: VxeGridProps<SystemAccount> = {
  columns: [
    { minWidth: 38, title: '序号', type: 'seq' },
    { field: '_id', minWidth: 180, title: '唯一标识' },
    { field: 'app_id', minWidth: 180, title: '应用ID' },
    {
      field: 'accounts',
      minWidth: 120,
      slots: { default: 'accounts' },
      title: '广告账户',
    },
    {
      field: 'pages',
      minWidth: 120,
      slots: { default: 'pages' },
      title: '主页',
    },
    {
      field: 'status',
      minWidth: 100,
      slots: { default: 'status' },
      title: '状态',
    },
    {
      field: 'update_time',
      formatter: ({ cellValue }) =>
        cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-',
      minWidth: 160,
      title: '更新时间',
    },
    {
      align: 'center',
      field: 'operate',
      fixed: 'right',
      slots: { default: 'operate' },
      title: '操作',
      width: 180,
    },
  ],
  pagerConfig: {
    pageSize: 20,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues) => {
        const params = {
          id: formValues.id || undefined,
          status: formValues.status,
          page: page.currentPage,
          page_size: page.pageSize,
        };
        const res = await getSystemAccounts(params);
        const ids = res.items.map((item: any) => item._id);
        fetchSyncProgress(ids);
        return res;
      },
    },
  },
  showOverflow: true,
  stripe: true,
  toolbarConfig: {
    refresh: true,
  },
};

const [Grid] = useVbenVxeGrid({
  formOptions,
  gridOptions,
  routeState: { scope: 'system_account' },
});

const handleSync = async (id: string) => {
  try {
    await syncPersonalAccount(id, 'system');
    message.success('同步任务提交成功');
  } catch {
    message.error('同步失败');
  }
};
</script>

<template>
  <Page
    content-class="!p-0 [&_.relative.rounded]:!pt-0 [&_.relative.rounded]:!pb-[2px]"
    class="h-full"
  >
    <Grid class="h-full">
      <template #accounts="{ row }">
        <Popover v-if="row.accounts?.length" placement="bottom" trigger="click">
          <template #content>
            <div class="max-h-[300px] max-w-[400px] overflow-y-auto">
              <div
                v-for="item in row.accounts"
                :key="item.id"
                class="mb-1 flex items-center gap-2 border-b border-gray-100 pb-1 last:mb-0 last:border-0 last:pb-0 dark:border-gray-700"
              >
                <span class="text-xs text-gray-500">{{ item.id }}</span>
                <span>{{ item.name }}</span>
              </div>
            </div>
          </template>
          <Tag color="blue" class="cursor-pointer">
            {{ row.accounts.length }} 个
          </Tag>
        </Popover>
        <span v-else class="text-gray-400">-</span>
      </template>

      <template #pages="{ row }">
        <Popover v-if="row.pages?.length" placement="bottom" trigger="click">
          <template #content>
            <div class="max-h-[300px] max-w-[400px] overflow-y-auto">
              <div
                v-for="item in row.pages"
                :key="item.id"
                class="mb-1 flex items-center gap-2 border-b border-gray-100 pb-1 last:mb-0 last:border-0 last:pb-0 dark:border-gray-700"
              >
                <span class="text-xs text-gray-500">{{ item.id }}</span>
                <span>{{ item.name }}</span>
              </div>
            </div>
          </template>
          <Tag color="orange" class="cursor-pointer">
            {{ row.pages.length }} 个
          </Tag>
        </Popover>
        <span v-else class="text-gray-400">-</span>
      </template>

      <template #status="{ row }">
        <Tag :color="row.status ? '' : 'error'">
          {{ row.status ? '正常' : '异常' }}
        </Tag>
      </template>

      <template #operate="{ row }">
        <template v-if="isInProgress(row._id)">
          <Progress
            :format="getProgressFormat(row._id)"
            :percent="getProgressPercent(row._id)"
            :title="`${getProgressPercent(row._id)}%`"
            style="width: 110px"
          />
        </template>
        <template v-else>
          <Popconfirm
            title="确定同步此系统资产吗"
            ok-text="确定"
            cancel-text="取消"
            @confirm="handleSync(row._id)"
          >
            <Button type="link">同步资产</Button>
          </Popconfirm>
          <Button type="link" @click="openTargetedSync(row._id)">
            定向同步
          </Button>
        </template>
      </template>
    </Grid>
    <TargetedSyncModal
      v-model:open="targetedSyncOpen"
      :personal-id="targetedSyncId"
      personal-type="system"
    />
  </Page>
</template>
