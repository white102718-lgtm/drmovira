<script lang="ts" setup>
import type { GoogleSyncData } from '#/api/data-integration';
import type { TableColumnsType } from 'ant-design-vue';

import { computed, h, onMounted, reactive, ref, toRef } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Card,
  DatePicker,
  Empty,
  Input,
  Pagination,
  Space,
  Table,
  Tag,
} from 'ant-design-vue';
import dayjs, { type Dayjs } from 'dayjs';

import { getGoogleSyncData } from '#/api/data-integration';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

import MediaResourcePage from './components/MediaResourcePage.vue';

const route = useRoute();
const router = useRouter();
const mappingId = computed(() => String(route.params.id ?? ''));
const mappingName = computed(() => String(route.query.name ?? '集成数据'));
const loading = ref(false);
const rows = ref<GoogleSyncData[]>([]);
const total = ref(0);
const filters = reactive<{
  dateRange: [Dayjs, Dayjs] | undefined;
  page: number;
  pageSize: number;
  taskName: string;
}>({
  dateRange: undefined,
  page: 1,
  pageSize: 20,
  taskName: '',
});
const routeState = createListRouteStateTarget({
  date_range: toRef(filters, 'dateRange'),
  task_name: toRef(filters, 'taskName'),
});
const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    fields: {
      date_range: {
        codec: {
          parse(value) {
            const values = Array.isArray(value) ? value : [value];
            return values.length === 2 && values[0] && values[1]
              ? [dayjs(values[0]), dayjs(values[1])]
              : undefined;
          },
          serialize(value) {
            return value?.map((item) => item.format('YYYY-MM-DD'));
          },
        },
      },
    },
    onRouteStateRestored: () => loadData(),
    pagination: {
      defaultPageSize: 20,
      page: toRef(filters, 'page'),
      pageSize: toRef(filters, 'pageSize'),
    },
    state: routeState,
  });

const columns: TableColumnsType<GoogleSyncData> = [
  { dataIndex: 'startDate', key: 'startDate', title: '日期', width: 120 },
  { dataIndex: 'taskName', key: 'taskName', title: '项目名称', width: 180 },
  {
    dataIndex: 'subtaskName',
    key: 'subtaskName',
    title: '任务线名称',
    width: 190,
  },
  {
    dataIndex: 'mediaPlacement',
    key: 'mediaPlacement',
    title: '媒体平台',
    width: 110,
    customRender: ({ text }: { text?: string }) =>
      h(Tag, { color: 'blue' }, () => text || '—'),
  },
  {
    dataIndex: 'spendAmount',
    key: 'spendAmount',
    title: '花费金额',
    width: 130,
    align: 'right',
    customRender: ({ text }: { text?: number }) => money(text),
  },
  {
    dataIndex: 'returnAmount',
    key: 'returnAmount',
    title: '回流金额',
    width: 130,
    align: 'right',
    customRender: ({ text }: { text?: number }) => money(text),
  },
  { dataIndex: 'impressions', key: 'impressions', title: '展示', width: 110 },
  { dataIndex: 'clicks', key: 'clicks', title: '点击', width: 100 },
  {
    dataIndex: 'registrations',
    key: 'registrations',
    title: '注册',
    width: 100,
  },
  { dataIndex: 'purchases', key: 'purchases', title: '购物', width: 100 },
  {
    dataIndex: 'subscriptions',
    key: 'subscriptions',
    title: '订阅',
    width: 100,
  },
  {
    dataIndex: 'updatedAt',
    key: 'updatedAt',
    title: '更新时间',
    width: 170,
    customRender: ({ text }: { text?: string }) =>
      text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '—',
  },
];

function money(value?: number) {
  return value === undefined || value === null
    ? '—'
    : Number(value).toLocaleString('zh-CN', {
        maximumFractionDigits: 2,
        minimumFractionDigits: 2,
      });
}

async function loadData() {
  if (!mappingId.value) return;
  await commitQueryState();
  loading.value = true;
  try {
    const result = await getGoogleSyncData(mappingId.value, {
      endDate: filters.dateRange?.[1].format('YYYY-MM-DD'),
      page: filters.page,
      pageSize: filters.pageSize,
      startDate: filters.dateRange?.[0].format('YYYY-MM-DD'),
      taskName: filters.taskName.trim() || undefined,
    });
    rows.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}

function search() {
  filters.page = 1;
  void loadData();
}

async function reset() {
  await resetQueryState();
  await loadData();
}

function changePage(page: number, pageSize: number) {
  filters.page = pageSize === filters.pageSize ? page : 1;
  filters.pageSize = pageSize;
  void loadData();
}

onMounted(async () => {
  await restoreFromRoute();
  await loadData();
});
</script>

<template>
  <MediaResourcePage>
    <section
      class="flex flex-col justify-between gap-4 rounded-2xl border border-slate-200/80 bg-white px-6 py-5 shadow-sm sm:flex-row sm:items-center dark:border-slate-800 dark:bg-slate-900"
    >
      <div class="flex min-w-0 items-center gap-3">
        <Button
          class="!flex !size-9 !items-center !justify-center !rounded-lg !p-0"
          @click="router.push('/system-management/data-integration')"
        >
          <IconifyIcon icon="lucide:arrow-left" />
        </Button>
        <div class="min-w-0">
          <h1
            class="m-0 truncate text-xl font-semibold text-slate-950 dark:text-white"
          >
            {{ mappingName }} · 集成数据
          </h1>
          <p class="mb-0 mt-1 text-sm text-slate-500">
            查看 Google Sheets 已同步到系统的数据记录
          </p>
        </div>
      </div>
      <Button :loading="loading" @click="loadData">
        <IconifyIcon icon="lucide:refresh-cw" class="mr-1" />刷新
      </Button>
    </section>

    <Card
      class="!rounded-2xl !border-slate-200/80 shadow-sm dark:!border-slate-800"
    >
      <div class="mb-5 flex flex-wrap items-center gap-3">
        <Input
          v-model:value="filters.taskName"
          allow-clear
          class="!w-64"
          placeholder="搜索项目名称"
          @press-enter="search"
        />
        <DatePicker.RangePicker v-model:value="filters.dateRange" />
        <Space>
          <Button type="primary" @click="search">查询</Button>
          <Button @click="reset">重置</Button>
        </Space>
        <span class="ml-auto text-sm text-slate-500">共 {{ total }} 条</span>
      </div>

      <Table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        :pagination="false"
        :row-key="(row: GoogleSyncData) => row.id"
        :scroll="{ x: 1550 }"
        size="middle"
      >
        <template #emptyText>
          <Empty description="暂无集成数据" />
        </template>
      </Table>

      <div v-if="total > 0" class="mt-5 flex justify-end">
        <Pagination
          :current="filters.page"
          :page-size="filters.pageSize"
          :page-size-options="['20', '50', '100']"
          :total="total"
          show-size-changer
          show-quick-jumper
          @change="changePage"
          @show-size-change="changePage"
        />
      </div>
    </Card>
  </MediaResourcePage>
</template>
