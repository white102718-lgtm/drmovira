<script lang="ts" setup>
import type {
  AlertLimitChangeRecord,
  AlertLimitChangeType,
} from '#/api/alert-notifications';
import type { Dayjs } from 'dayjs';

import { onBeforeUnmount, reactive, ref, toRef, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  DatePicker,
  Empty,
  Form,
  FormItem,
  Input,
  Select,
  Table,
  Tag,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { getAlertLimitChangeRecords } from '#/api/alert-notifications';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import {
  DAILY_LIMIT_CHANGE_META,
  formatDailyLimit,
} from '../../components/ad-account-daily-limit-history';

const props = defineProps<{
  active: boolean;
}>();

const { RangePicker } = DatePicker;
const records = ref<AlertLimitChangeRecord[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref('');
const filters = reactive({
  changeType: undefined as AlertLimitChangeType | undefined,
  dateRange: undefined as [Dayjs, Dayjs] | undefined,
  keyword: '',
  page: 1,
  pageSize: 20,
});
const routeState = createListRouteStateTarget({
  change_type: toRef(filters, 'changeType'),
  date_range: toRef(filters, 'dateRange'),
  keyword: toRef(filters, 'keyword'),
});
let abortController: AbortController | undefined;
let requestVersion = 0;

const columns = [
  { dataIndex: 'occurredAt', key: 'occurredAt', title: '变更时间', width: 180 },
  {
    dataIndex: 'accountName',
    key: 'accountName',
    title: '广告户名称',
    width: 180,
  },
  { dataIndex: 'accountId', key: 'accountId', title: '广告户 ID', width: 180 },
  { dataIndex: 'changeType', key: 'changeType', title: '变化类型', width: 120 },
  {
    dataIndex: 'previousLimit',
    key: 'previousLimit',
    title: '原限额',
    width: 150,
  },
  {
    dataIndex: 'currentLimit',
    key: 'currentLimit',
    title: '新限额',
    width: 150,
  },
  { dataIndex: 'currency', key: 'currency', title: '币种', width: 100 },
  { dataIndex: 'source', key: 'source', title: '来源', width: 160 },
];
const changeTypeOptions: Array<{
  label: string;
  value: AlertLimitChangeType;
}> = [
  { label: '首次设置', value: 'SET' },
  { label: '提高', value: 'INCREASE' },
  { label: '降低', value: 'DECREASE' },
  { label: '清除限额', value: 'CLEAR' },
];

const { commitQueryState, restoreFromRoute } = useListRouteState({
  enabled: () => props.active,
  fields: {
    date_range: {
      codec: {
        parse(value) {
          const values = Array.isArray(value) ? value : [value];
          return values.length === 2 && values[0] && values[1]
            ? ([dayjs(values[0]), dayjs(values[1])] as [Dayjs, Dayjs])
            : undefined;
        },
        serialize(value) {
          return value?.map((item) => item.format('YYYY-MM-DD'));
        },
      },
    },
  },
  onRouteStateRestored: () => loadRecords(false),
  pagination: {
    defaultPageSize: 20,
    page: toRef(filters, 'page'),
    pageSize: toRef(filters, 'pageSize'),
  },
  scope: 'limit',
  state: routeState,
});

function resetRequest() {
  requestVersion += 1;
  abortController?.abort();
  abortController = undefined;
  loading.value = false;
}

async function loadRecords(commitRoute = true) {
  if (!props.active) return;
  if (commitRoute) await commitQueryState();
  resetRequest();
  const version = requestVersion;
  const controller = new AbortController();
  abortController = controller;
  loading.value = true;
  error.value = '';
  try {
    const result = await getAlertLimitChangeRecords(
      {
        changeType: filters.changeType,
        endDate: filters.dateRange?.[1].format('YYYY-MM-DD'),
        keyword: filters.keyword.trim() || undefined,
        page: filters.page,
        pageSize: filters.pageSize,
        startDate: filters.dateRange?.[0].format('YYYY-MM-DD'),
      },
      { signal: controller.signal, skipErrorMessage: true },
    );
    if (version !== requestVersion || controller.signal.aborted) return;
    records.value = result.items;
    total.value = result.total;
  } catch (requestError) {
    if (version !== requestVersion || controller.signal.aborted) return;
    error.value =
      requestError instanceof Error && requestError.message
        ? requestError.message
        : '限额变更记录暂时无法获取，请稍后重试。';
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}

function searchRecords() {
  filters.page = 1;
  void loadRecords();
}

function resetRecords() {
  filters.keyword = '';
  filters.changeType = undefined;
  filters.dateRange = undefined;
  searchRecords();
}

function handlePageChange(page: number, pageSize: number) {
  const pageSizeChanged = filters.pageSize !== pageSize;
  filters.page = pageSizeChanged ? 1 : page;
  filters.pageSize = pageSize;
  void loadRecords();
}

function formatTime(value?: string) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
}

function changeMeta(changeType: string) {
  return (
    DAILY_LIMIT_CHANGE_META[changeType as AlertLimitChangeType] ?? {
      label: '限额变更',
    }
  );
}

watch(
  () => props.active,
  async (active) => {
    resetRequest();
    if (!active) return;
    await restoreFromRoute();
    await loadRecords(false);
  },
  { immediate: true },
);

onBeforeUnmount(resetRequest);
</script>

<template>
  <div class="flex min-h-0 flex-col gap-4">
    <Form
      class="ux-filter-form"
      layout="vertical"
      @submit.prevent="searchRecords"
    >
      <FormItem class="ux-filter-field" label="关键词">
        <Input
          v-model:value="filters.keyword"
          allow-clear
          placeholder="搜索广告户 ID 或名称"
          @press-enter="searchRecords"
        >
          <template #prefix>
            <IconifyIcon aria-hidden="true" icon="lucide:search" />
          </template>
        </Input>
      </FormItem>
      <FormItem class="ux-filter-field" label="变化类型">
        <Select
          v-model:value="filters.changeType"
          allow-clear
          :options="changeTypeOptions"
          placeholder="全部变化类型"
        >
          <template #suffixIcon>
            <IconifyIcon aria-hidden="true" icon="lucide:gauge" />
          </template>
        </Select>
      </FormItem>
      <FormItem class="ux-filter-field" label="变更日期">
        <RangePicker v-model:value="filters.dateRange" class="w-full">
          <template #suffixIcon>
            <IconifyIcon aria-hidden="true" icon="lucide:calendar-days" />
          </template>
        </RangePicker>
      </FormItem>
      <div class="ux-filter-actions">
        <Button type="primary" @click="searchRecords">
          <template #icon>
            <IconifyIcon aria-hidden="true" icon="lucide:search" />
          </template>
          查询
        </Button>
        <Button @click="resetRecords">
          <template #icon>
            <IconifyIcon aria-hidden="true" icon="lucide:rotate-ccw" />
          </template>
          重置
        </Button>
      </div>
    </Form>

    <Alert v-if="error" :message="error" role="alert" show-icon type="error">
      <template #action>
        <Button @click="loadRecords(false)">重新加载</Button>
      </template>
    </Alert>

    <Table
      row-key="id"
      :columns="columns"
      :data-source="records"
      :loading="loading"
      :pagination="{
        current: filters.page,
        pageSize: filters.pageSize,
        showSizeChanger: true,
        total,
      }"
      :scroll="{ x: 1220 }"
      @change="
        (pagination) =>
          handlePageChange(pagination.current || 1, pagination.pageSize || 20)
      "
    >
      <template #emptyText><Empty description="暂无限额变更记录" /></template>
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'occurredAt'">
          <div class="tabular-nums">{{ formatTime(record.occurredAt) }}</div>
          <div class="text-muted-foreground mt-1 text-xs">GMT+8</div>
        </template>
        <template v-else-if="column.key === 'accountName'">
          {{ record.accountName || '-' }}
        </template>
        <template v-else-if="column.key === 'accountId'">
          <span class="font-mono">{{ record.accountId || '-' }}</span>
        </template>
        <template v-else-if="column.key === 'changeType'">
          <Tag :color="changeMeta(record.changeType).color">
            {{ changeMeta(record.changeType).label }}
          </Tag>
        </template>
        <template v-else-if="column.key === 'previousLimit'">
          <span class="tabular-nums">
            {{ formatDailyLimit(record.previousLimit) }}
          </span>
        </template>
        <template v-else-if="column.key === 'currentLimit'">
          <span class="font-medium tabular-nums">
            {{ formatDailyLimit(record.currentLimit) }}
          </span>
        </template>
        <template v-else-if="column.key === 'currency'">
          {{ record.currency || '-' }}
        </template>
        <template v-else-if="column.key === 'source'">
          <span class="inline-flex items-center gap-1.5">
            <IconifyIcon
              aria-hidden="true"
              class="text-muted-foreground size-4 shrink-0"
              icon="lucide:refresh-cw"
            />
            Facebook 平台同步
          </span>
        </template>
      </template>
    </Table>
  </div>
</template>
