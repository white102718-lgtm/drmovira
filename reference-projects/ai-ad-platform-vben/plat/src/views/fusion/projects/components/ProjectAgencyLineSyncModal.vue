<script setup lang="ts">
import type {
  ProjectAgencyLineSyncBatch,
  ProjectAgencyLineSyncFailure,
} from '#/api/fusion/types';

import { ref, watch } from 'vue';

import { Alert, Input, message, Modal, Pagination, Tag } from 'ant-design-vue';
import Button from 'ant-design-vue/es/button';

import AntDataTable from '#/components/ui/AntDataTable.vue';
import {
  listProjectAgencyLineSyncBatches,
  listProjectAgencyLineSyncFailures,
  synchronizeProjectAgencyLines,
} from '#/domain/project';

const props = defineProps<{
  canSynchronize: boolean;
  link?: string;
  open: boolean;
  projectId: string;
}>();
const emit = defineEmits<{
  synchronized: [];
  'update:open': [value: boolean];
}>();

const synchronizing = ref(false);
const historyOpen = ref(false);
const historyLoading = ref(false);
const historyError = ref('');
const histories = ref<ProjectAgencyLineSyncBatch[]>([]);
const historyPage = ref(1);
const historyTotal = ref(0);
const failureOpen = ref(false);
const failureLoading = ref(false);
const failureError = ref('');
const failures = ref<ProjectAgencyLineSyncFailure[]>([]);
const failurePage = ref(1);
const failureTotal = ref(0);
const selectedBatch = ref<ProjectAgencyLineSyncBatch>();

const historyColumns = [
  { key: 'startedAt', title: '同步时间', width: 170 },
  { key: 'triggerType', title: '触发方式', width: 100 },
  { key: 'status', title: '状态', width: 100 },
  { key: 'sheetTitle', title: '页签', width: 140 },
  { key: 'counts', title: '处理结果', width: 190 },
  { key: 'triggeredByName', title: '触发人', width: 130 },
  { key: 'actions', title: '失败详情', width: 110 },
];
const failureColumns = [
  { key: 'sheetRowNumber', title: 'Sheet 行号', width: 110 },
  { key: 'agencyLineName', title: '代理线', width: 180 },
  { key: 'failureReason', title: '失败原因' },
];
const statusMeta = {
  failed: { color: 'red', label: '失败' },
  partial: { color: 'orange', label: '部分成功' },
  running: { color: 'blue', label: '同步中' },
  success: { color: 'green', label: '成功' },
} as const;

function close() {
  if (!synchronizing.value) emit('update:open', false);
}

function openLink() {
  if (!props.link) return;
  const opened = window.open(props.link, '_blank', 'noopener,noreferrer');
  if (opened) opened.opener = null;
}

async function synchronize() {
  if (!props.link || !props.canSynchronize || synchronizing.value) return;
  synchronizing.value = true;
  try {
    const batch = await synchronizeProjectAgencyLines(props.projectId);
    if (batch.status === 'success') {
      message.success(`同步完成，共成功处理 ${batch.successRows} 行`);
    } else if (batch.status === 'partial') {
      message.warning(
        `同步部分成功：成功 ${batch.successRows} 行，失败 ${batch.failedRows} 行`,
      );
    } else {
      message.error(batch.errorMessage || '代理线同步失败，请查看同步记录');
    }
    emit('synchronized');
    if (historyOpen.value) await loadHistories(1);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '代理线同步失败');
  } finally {
    synchronizing.value = false;
  }
}

async function loadHistories(page = historyPage.value) {
  historyLoading.value = true;
  historyError.value = '';
  try {
    const result = await listProjectAgencyLineSyncBatches(
      props.projectId,
      page,
      10,
    );
    histories.value = result.items;
    historyPage.value = result.page;
    historyTotal.value = result.total;
  } catch (error) {
    historyError.value =
      error instanceof Error ? error.message : '同步记录加载失败';
  } finally {
    historyLoading.value = false;
  }
}

function showHistories() {
  historyOpen.value = true;
  void loadHistories(1);
}

async function loadFailures(page = failurePage.value) {
  if (!selectedBatch.value) return;
  failureLoading.value = true;
  failureError.value = '';
  try {
    const result = await listProjectAgencyLineSyncFailures(
      props.projectId,
      selectedBatch.value.id,
      page,
      20,
    );
    failures.value = result.items;
    failurePage.value = result.page;
    failureTotal.value = result.total;
  } catch (error) {
    failureError.value =
      error instanceof Error ? error.message : '失败详情加载失败';
  } finally {
    failureLoading.value = false;
  }
}

function showFailures(batch: ProjectAgencyLineSyncBatch) {
  selectedBatch.value = batch;
  failureOpen.value = true;
  void loadFailures(1);
}

function dateTime(value?: string) {
  return value ? value.replace('T', ' ').slice(0, 19) : '—';
}

watch(
  () => props.projectId,
  () => {
    historyOpen.value = false;
    failureOpen.value = false;
    histories.value = [];
    failures.value = [];
  },
);
</script>

<template>
  <Modal
    :open="open"
    title="代理线链接"
    :closable="!synchronizing"
    :mask-closable="!synchronizing"
    :footer="null"
    @cancel="close"
  >
    <div class="space-y-4">
      <div>
        <label for="project-agency-line-sync-link" class="mb-2 block text-sm"
          >Google Sheet 链接</label
        >
        <Input
          id="project-agency-line-sync-link"
          :value="link || ''"
          readonly
          :placeholder="link ? undefined : '项目尚未配置代理线链接'"
        />
      </div>
      <Alert
        v-if="!link"
        type="warning"
        show-icon
        message="请先在编辑项目中配置包含 gid 的代理线链接"
      />
      <div class="flex flex-wrap justify-end gap-2">
        <Button :disabled="!link" @click="openLink">跳转</Button>
        <Button @click="showHistories">历史同步记录</Button>
        <Button
          type="primary"
          :disabled="!link || !canSynchronize"
          :loading="synchronizing"
          @click="synchronize"
          >手动同步</Button
        >
      </div>
    </div>
  </Modal>

  <Modal
    v-model:open="historyOpen"
    title="代理线同步记录"
    width="min(960px, 96vw)"
    :footer="null"
  >
    <Alert
      v-if="historyError"
      class="mb-3"
      type="error"
      :message="historyError"
      show-icon
    />
    <AntDataTable
      :columns="historyColumns"
      :data="histories"
      :loading="historyLoading"
      :paginate="false"
      row-key="id"
      empty-text="暂无同步记录"
    >
      <template #cell-startedAt="{ record }">{{
        dateTime(record.startedAt)
      }}</template>
      <template #cell-triggerType="{ record }">{{
        record.triggerType === 'manual' ? '手动' : '每小时自动'
      }}</template>
      <template #cell-status="{ record }">
        <Tag :color="statusMeta[record.status].color">{{
          statusMeta[record.status].label
        }}</Tag>
      </template>
      <template #cell-sheetTitle="{ record }">{{
        record.sheetTitle || '—'
      }}</template>
      <template #cell-counts="{ record }">
        共 {{ record.totalRows }} · 成功 {{ record.successRows }} · 失败
        {{ record.failedRows }}
      </template>
      <template #cell-triggeredByName="{ record }">{{
        record.triggeredByName || '系统定时同步'
      }}</template>
      <template #cell-actions="{ record }">
        <Button
          type="link"
          :disabled="record.failedRows === 0 && !record.errorMessage"
          @click="showFailures(record)"
          >查看</Button
        >
      </template>
    </AntDataTable>
    <div v-if="historyTotal > 10" class="mt-4 flex justify-end">
      <Pagination
        :current="historyPage"
        :page-size="10"
        :total="historyTotal"
        :show-size-changer="false"
        @change="loadHistories"
      />
    </div>
  </Modal>

  <Modal
    v-model:open="failureOpen"
    title="同步失败详情"
    width="min(800px, 96vw)"
    :footer="null"
  >
    <Alert
      v-if="selectedBatch?.errorMessage"
      class="mb-3"
      type="error"
      :message="selectedBatch.errorMessage"
      show-icon
    />
    <Alert
      v-if="failureError"
      class="mb-3"
      type="error"
      :message="failureError"
      show-icon
    />
    <AntDataTable
      :columns="failureColumns"
      :data="failures"
      :loading="failureLoading"
      :paginate="false"
      row-key="id"
      empty-text="该批次没有逐行失败记录"
    >
      <template #cell-agencyLineName="{ record }">{{
        record.agencyLineName || '未识别'
      }}</template>
    </AntDataTable>
    <div v-if="failureTotal > 20" class="mt-4 flex justify-end">
      <Pagination
        :current="failurePage"
        :page-size="20"
        :total="failureTotal"
        :show-size-changer="false"
        @change="loadFailures"
      />
    </div>
  </Modal>
</template>
