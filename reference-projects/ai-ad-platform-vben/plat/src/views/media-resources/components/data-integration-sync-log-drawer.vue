<script lang="ts" setup>
import type { GoogleMappingId, GoogleSyncLog } from '#/api/data-integration';
import type { TableColumnsType } from 'ant-design-vue';

import { computed, h, reactive, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Drawer,
  Empty,
  Pagination,
  Space,
  Table,
  Tag,
  Typography,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { getGoogleSyncLogs } from '#/api/data-integration';

const openState = ref(false);
const loading = ref(false);
const mappingId = ref<GoogleMappingId>();
const mappingName = ref('');
const rows = ref<GoogleSyncLog[]>([]);
const total = ref(0);
const loadError = ref('');
const pagination = reactive({ page: 1, pageSize: 20 });

const title = computed(() => `${mappingName.value} · 同步日志`);
const { Paragraph } = Typography;

const statusMeta: Record<
  GoogleSyncLog['status'],
  { color: string; label: string }
> = {
  0: { color: 'default', label: '等待中' },
  1: { color: 'processing', label: '执行中' },
  2: { color: 'success', label: '成功' },
  3: { color: 'error', label: '失败' },
};

const columns: TableColumnsType<GoogleSyncLog> = [
  {
    dataIndex: 'createdAt',
    key: 'createdAt',
    title: '触发时间',
    width: 170,
    customRender: ({ text }: { text?: string }) => formatTime(text),
  },
  {
    dataIndex: 'fullSync',
    key: 'fullSync',
    title: '同步类型',
    width: 100,
    customRender: ({ text }: { text: boolean }) =>
      text ? '全量同步' : '定时同步',
  },
  {
    dataIndex: 'status',
    key: 'status',
    title: '状态',
    width: 100,
    customRender: ({ text }: { text: GoogleSyncLog['status'] }) => {
      const meta = statusMeta[text] ?? statusMeta[0];
      return h(Tag, { color: meta.color }, () => meta.label);
    },
  },
  {
    key: 'duration',
    title: '耗时',
    width: 100,
    customRender: ({ record }: { record: GoogleSyncLog }) => duration(record),
  },
  {
    dataIndex: 'errorMessage',
    ellipsis: true,
    key: 'errorMessage',
    title: '执行结果',
    width: 260,
    customRender: ({ record }: { record: GoogleSyncLog }) =>
      record.status === 3
        ? record.errorMessage || '同步失败，未返回错误详情'
        : '—',
  },
];

function formatTime(value?: string) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—';
}

function duration(log: GoogleSyncLog) {
  if (!log.startedAt) return '—';
  const end = log.finishedAt ? dayjs(log.finishedAt) : dayjs();
  const seconds = Math.max(0, end.diff(dayjs(log.startedAt), 'second'));
  return seconds < 60
    ? `${seconds} 秒`
    : `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
}

async function loadLogs() {
  if (!mappingId.value) return;
  loading.value = true;
  loadError.value = '';
  try {
    const result = await getGoogleSyncLogs(mappingId.value, pagination);
    rows.value = result.items;
    total.value = result.total;
  } catch (error) {
    loadError.value =
      error instanceof Error ? error.message : '同步日志加载失败';
  } finally {
    loading.value = false;
  }
}

function changePage(page: number, pageSize: number) {
  pagination.page = pageSize === pagination.pageSize ? page : 1;
  pagination.pageSize = pageSize;
  void loadLogs();
}

async function open(options: { id: GoogleMappingId; name: string }) {
  mappingId.value = options.id;
  mappingName.value = options.name;
  pagination.page = 1;
  openState.value = true;
  await loadLogs();
}

defineExpose({ open });
</script>

<template>
  <Drawer v-model:open="openState" :title="title" :width="760">
    <template #extra>
      <Button :loading="loading" @click="loadLogs">
        <IconifyIcon icon="lucide:refresh-cw" class="mr-1" aria-hidden="true" />
        刷新
      </Button>
    </template>

    <Space direction="vertical" :size="16" class="w-full">
      <Paragraph type="secondary" class="!mb-0">
        展示手动、首次全量及定时同步任务的执行状态。失败任务可在“执行结果”中查看原因。
      </Paragraph>

      <Alert v-if="loadError" :message="loadError" show-icon type="error">
        <template #action>
          <Button @click="loadLogs">重新加载</Button>
        </template>
      </Alert>

      <Table
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        :pagination="false"
        :row-key="(row: GoogleSyncLog) => row.id"
        :scroll="{ x: 730 }"
        size="middle"
      >
        <template #emptyText>
          <Empty
            :image="Empty.PRESENTED_IMAGE_SIMPLE"
            description="暂无同步日志"
          />
        </template>
      </Table>

      <div v-if="total > 0" class="flex justify-end">
        <Pagination
          :current="pagination.page"
          :page-size="pagination.pageSize"
          :page-size-options="['20', '50', '100']"
          :total="total"
          show-size-changer
          show-quick-jumper
          @change="changePage"
          @show-size-change="changePage"
        />
      </div>
    </Space>
  </Drawer>
</template>
