<script setup lang="ts">
import type {
  DeliveryGooglePreview,
  DeliveryGooglePreviewGroup,
  DeliveryGooglePushBatch,
} from '#/api/delivery-report';
import type { TableColumnsType } from 'ant-design-vue';

import { computed, onBeforeUnmount, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Modal,
  Spin,
  Table,
  Tag,
  message,
} from 'ant-design-vue';

import { deliveryReportApi } from '#/api/delivery-report';

const emit = defineEmits<{ completed: [] }>();
const open = ref(false);
const loading = ref(false);
const pushing = ref(false);
const reportIds = ref<string[]>([]);
const preview = ref<DeliveryGooglePreview>();
const batch = ref<DeliveryGooglePushBatch>();
const historyMode = ref(false);
const recentBatches = ref<DeliveryGooglePushBatch[]>([]);
let pollTimer: number | undefined;

const isFinished = computed(() =>
  batch.value ? [2, 3, 4].includes(batch.value.status) : false,
);
const resultMessage = computed(() => {
  if (!batch.value) return '';
  if (batch.value.status === 2)
    return `已成功写入 ${batch.value.successCount} 条日报。`;
  if (batch.value.status === 3)
    return `成功 ${batch.value.successCount} 条，失败 ${batch.value.failedCount} 条，可重试失败记录。`;
  if (batch.value.status === 4)
    return `本次 ${batch.value.failedCount || batch.value.totalCount} 条日报均未写入。`;
  return '后台正在写入Google Sheet，请保持窗口打开查看结果。';
});

/** 打开跨项目预览，服务端会重新读取日报并校验每个项目的有效模板。 */
async function show(ids: string[]) {
  clearPoll();
  open.value = true;
  reportIds.value = [...ids];
  historyMode.value = false;
  preview.value = undefined;
  batch.value = undefined;
  loading.value = true;
  try {
    preview.value = await deliveryReportApi.previewGooglePush(ids);
  } catch {
    open.value = false;
  } finally {
    loading.value = false;
  }
}

/** 打开当前用户最近推送记录，运行中的批次在进入详情后继续轮询。 */
async function showHistory() {
  clearPoll();
  open.value = true;
  historyMode.value = true;
  preview.value = undefined;
  batch.value = undefined;
  loading.value = true;
  try {
    recentBatches.value = await deliveryReportApi.recentGooglePushBatches();
  } finally {
    loading.value = false;
  }
}

async function viewBatch(id: string) {
  loading.value = true;
  try {
    batch.value = await deliveryReportApi.googlePushBatch(id);
    schedulePoll();
  } finally {
    loading.value = false;
  }
}

async function confirmPush() {
  pushing.value = true;
  try {
    batch.value = await deliveryReportApi.createGooglePushBatch(
      reportIds.value,
    );
    schedulePoll();
  } finally {
    pushing.value = false;
  }
}

async function pollBatch() {
  if (!open.value || !batch.value || isFinished.value) return;
  try {
    batch.value = await deliveryReportApi.googlePushBatch(batch.value.id);
    if (isFinished.value) {
      emit('completed');
      if (batch.value.status === 2) message.success(resultMessage.value);
      return;
    }
    schedulePoll();
  } catch {
    clearPoll();
    message.error('推送状态查询失败，请关闭窗口后重新查看日报');
  }
}

function schedulePoll() {
  clearPoll();
  if (!open.value || !batch.value || isFinished.value) return;
  pollTimer = window.setTimeout(() => void pollBatch(), 1500);
}

async function retry() {
  if (!batch.value) return;
  pushing.value = true;
  try {
    batch.value = await deliveryReportApi.retryGooglePushBatch(batch.value.id);
    schedulePoll();
  } finally {
    pushing.value = false;
  }
}

function close() {
  clearPoll();
  open.value = false;
}

function clearPoll() {
  if (pollTimer !== undefined) window.clearTimeout(pollTimer);
  pollTimer = undefined;
}

function previewColumns(
  group: DeliveryGooglePreviewGroup,
): TableColumnsType<Record<string, unknown>> {
  return group.fieldMappings.map((mapping) => ({
    dataIndex: mapping.systemField,
    key: mapping.systemField,
    title: mapping.uniqueKey
      ? `${mapping.targetHeader}（唯一值）`
      : mapping.targetHeader,
    width: 150,
  }));
}

function previewRows(group: DeliveryGooglePreviewGroup) {
  return group.rows.map((row) => ({ key: row.reportId, ...row.values }));
}

function statusLabel(status: number) {
  return ['待执行', '写入中', '成功', '部分失败', '失败'][status] || '未知';
}

function statusColor(status: number) {
  if (status === 2) return 'success';
  if (status === 3) return 'warning';
  if (status === 4) return 'error';
  return 'processing';
}

function itemStatusLabel(status: number) {
  return ['待执行', '写入中', '成功', '失败'][status] || '未知';
}

function formatTime(value?: string) {
  return value ? value.replace('T', ' ').slice(0, 19) : '—';
}

onBeforeUnmount(clearPoll);
defineExpose({ show, showHistory });
</script>

<template>
  <Modal
    v-model:open="open"
    :closable="!pushing"
    :mask-closable="false"
    :width="1100"
    :title="historyMode ? '项目日报推送记录' : '填写到项目日报'"
    @cancel="close"
  >
    <Spin :spinning="loading" class="w-full">
      <div v-if="historyMode && !batch">
        <Alert
          class="mb-4"
          show-icon
          type="info"
          message="最近20个推送批次"
          description="打开批次可查看逐条结果，并重试失败记录。"
        />
        <Table :data-source="recentBatches" :pagination="false" row-key="id">
          <Table.Column key="createdAt" title="发起时间" width="190">
            <template #default="{ record }">{{
              formatTime(record.createdAt)
            }}</template>
          </Table.Column>
          <Table.Column key="status" title="状态" width="120">
            <template #default="{ record }">
              <Tag :color="statusColor(record.status)">{{
                statusLabel(record.status)
              }}</Tag>
            </template>
          </Table.Column>
          <Table.Column
            key="totalCount"
            data-index="totalCount"
            title="总数"
            width="90"
          />
          <Table.Column
            key="successCount"
            data-index="successCount"
            title="成功"
            width="90"
          />
          <Table.Column
            key="failedCount"
            data-index="failedCount"
            title="失败"
            width="90"
          />
          <Table.Column key="actions" title="操作" width="100">
            <template #default="{ record }">
              <Button type="link" @click="viewBatch(record.id)">查看</Button>
            </template>
          </Table.Column>
        </Table>
      </div>
      <template v-if="preview">
        <Alert
          v-if="!batch"
          show-icon
          type="info"
          :message="`本次将 ${preview.totalCount} 条日报写入 ${preview.groups.length} 个项目日报。`"
          description="系统按项目使用唯一模板；模板配置的唯一字段组合相同时会更新原行。"
        />
        <Alert
          v-else
          show-icon
          :type="
            batch.status === 2
              ? 'success'
              : batch.status >= 3
                ? 'warning'
                : 'info'
          "
          :message="resultMessage"
        />

        <div v-if="!batch" class="mt-4 flex flex-col gap-4">
          <section
            v-for="group in preview.groups"
            :key="group.projectId"
            class="preview-group"
          >
            <div class="flex flex-wrap items-start justify-between gap-3 p-4">
              <div>
                <strong>{{ group.projectName }}</strong>
                <p class="text-muted-foreground mb-0 mt-1 text-sm">
                  {{ group.spreadsheetName }} · {{ group.sheetTitle }} ·
                  {{ group.templateName }}
                </p>
              </div>
              <Tag>{{ group.rows.length }} 条待写入</Tag>
            </div>
            <Table
              :columns="previewColumns(group)"
              :data-source="previewRows(group)"
              :pagination="false"
              :scroll="{ x: Math.max(900, group.fieldMappings.length * 150) }"
            />
          </section>
        </div>

        <div v-else class="mt-4">
          <div class="mb-3 flex items-center gap-2">
            <Tag :color="statusColor(batch.status)">{{
              statusLabel(batch.status)
            }}</Tag>
            <span class="text-muted-foreground text-sm"
              >批次 {{ batch.id }}</span
            >
          </div>
          <Table
            :data-source="batch.items"
            :pagination="false"
            :scroll="{ x: 760 }"
            row-key="id"
          >
            <Table.Column
              key="reportId"
              data-index="reportId"
              title="日报ID"
              width="150"
            />
            <Table.Column
              key="projectId"
              data-index="projectId"
              title="项目ID"
              width="150"
            />
            <Table.Column key="status" title="状态" width="110">
              <template #default="{ record }">
                <Tag
                  :color="
                    record.status === 3 ? 'error' : statusColor(record.status)
                  "
                >
                  {{ itemStatusLabel(record.status) }}
                </Tag>
              </template>
            </Table.Column>
            <Table.Column
              key="targetRow"
              data-index="targetRow"
              title="Google行"
              width="110"
            />
            <Table.Column
              key="errorMessage"
              data-index="errorMessage"
              title="结果说明"
            />
          </Table>
        </div>
      </template>
      <div v-else-if="batch" class="mt-4">
        <div class="mb-3 flex items-center gap-2">
          <Button type="link" @click="batch = undefined">返回推送记录</Button>
          <Tag :color="statusColor(batch.status)">{{
            statusLabel(batch.status)
          }}</Tag>
          <span class="text-muted-foreground text-sm">批次 {{ batch.id }}</span>
        </div>
        <Alert
          class="mb-4"
          show-icon
          :type="
            batch.status === 2
              ? 'success'
              : batch.status >= 3
                ? 'warning'
                : 'info'
          "
          :message="resultMessage"
        />
        <Table
          :data-source="batch.items"
          :pagination="false"
          :scroll="{ x: 760 }"
          row-key="id"
        >
          <Table.Column
            key="reportId"
            data-index="reportId"
            title="日报ID"
            width="150"
          />
          <Table.Column
            key="projectId"
            data-index="projectId"
            title="项目ID"
            width="150"
          />
          <Table.Column key="status" title="状态" width="110">
            <template #default="{ record }">
              <Tag
                :color="
                  record.status === 3 ? 'error' : statusColor(record.status)
                "
              >
                {{ itemStatusLabel(record.status) }}
              </Tag>
            </template>
          </Table.Column>
          <Table.Column
            key="targetRow"
            data-index="targetRow"
            title="Google行"
            width="110"
          />
          <Table.Column
            key="errorMessage"
            data-index="errorMessage"
            title="结果说明"
          />
        </Table>
      </div>
    </Spin>

    <template #footer>
      <div class="flex justify-end gap-2">
        <Button :disabled="pushing" @click="close">关闭</Button>
        <Button
          v-if="batch && [3, 4].includes(batch.status)"
          :loading="pushing"
          @click="retry"
        >
          <IconifyIcon icon="lucide:refresh-cw" class="mr-1" />重试失败记录
        </Button>
        <Button
          v-if="preview && !batch"
          type="primary"
          :loading="pushing"
          @click="confirmPush"
        >
          确认写入项目日报
        </Button>
      </div>
    </template>
  </Modal>
</template>

<style scoped>
.preview-group {
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}
</style>
