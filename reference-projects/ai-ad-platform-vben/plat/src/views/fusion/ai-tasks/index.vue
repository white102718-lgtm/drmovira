<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Popconfirm,
  Progress,
  Row,
  Select,
  Table,
  Tag,
  message,
} from 'ant-design-vue';

import type { AsyncTask, AsyncTaskStatus } from '#/api';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import { useGlobalTaskStore, useProjectContextStore } from '#/store';

const taskStore = useGlobalTaskStore();
const projectStore = useProjectContextStore();
const router = useRouter();
const statusFilter = ref<AsyncTaskStatus | 'all'>('all');
const typeFilter = ref<'ai' | 'all' | 'publish'>('all');
const actingTaskId = ref('');
const routeState = createListRouteStateTarget({
  status: statusFilter,
  type: typeFilter,
});
const { commitQueryState, restoreFromRoute } = useListRouteState({
  state: routeState,
});
watch([statusFilter, typeFilter], () => {
  void commitQueryState();
});

const statusConfig: Record<AsyncTaskStatus, { color: string; label: string }> =
  {
    cancel_requested: { color: 'warning', label: '取消确认中' },
    cancelled: { color: 'default', label: '已取消' },
    failed: { color: 'error', label: '失败，待退款' },
    partial_success: { color: 'warning', label: '部分成功' },
    queued: { color: 'processing', label: '排队中' },
    refund_pending: { color: 'warning', label: '退款处理中' },
    refunded: { color: 'default', label: '已退款' },
    running: { color: 'processing', label: '执行中' },
    success: { color: 'success', label: '已完成' },
  };

const filteredTasks = computed(() =>
  taskStore.tasks.filter((task) => {
    const projectMatched =
      !projectStore.selectedProjectId ||
      task.projectId === projectStore.selectedProjectId;
    const statusMatched =
      statusFilter.value === 'all' || task.status === statusFilter.value;
    const typeMatched =
      typeFilter.value === 'all' ||
      (typeFilter.value === 'ai'
        ? Boolean(task.capability)
        : Boolean(task.platform));
    return projectMatched && statusMatched && typeMatched;
  }),
);

const stats = computed(() => [
  {
    icon: 'lucide:list-todo',
    label: '任务总数',
    value: filteredTasks.value.length,
  },
  {
    icon: 'lucide:loader-circle',
    label: '执行中',
    value: filteredTasks.value.filter((item) =>
      ['cancel_requested', 'queued', 'running'].includes(item.status),
    ).length,
  },
  {
    icon: 'lucide:circle-check-big',
    label: '成功',
    value: filteredTasks.value.filter((item) => item.status === 'success')
      .length,
  },
  {
    icon: 'lucide:receipt-refund',
    label: '退款处理',
    value: filteredTasks.value.filter((item) =>
      ['failed', 'refund_pending', 'refunded'].includes(item.status),
    ).length,
  },
]);

const columns: TableColumnsType<AsyncTask> = [
  { key: 'task', title: '任务', width: 340 },
  { dataIndex: 'status', key: 'status', title: '状态', width: 130 },
  { dataIndex: 'progress', key: 'progress', title: '进度', width: 180 },
  {
    dataIndex: 'resultCount',
    key: 'resultCount',
    title: '有效产出',
    width: 100,
  },
  { dataIndex: 'updatedAt', key: 'updatedAt', title: '更新时间', width: 170 },
  { key: 'billing', title: '计费处理', width: 160 },
  { key: 'actions', title: '操作', width: 190, fixed: 'right' },
];

function billingText(task: Record<string, any>) {
  if (task.status === 'failed') return '自动进入全额退款';
  if (task.status === 'cancelled')
    return task.refundable ? '自动进入退款' : '不可退款';
  if (task.status === 'partial_success') return '仅结算有效产出';
  if (task.status === 'cancel_requested') return '等待停止与核算';
  if (task.status === 'refund_pending') return '退款账本处理中';
  if (task.status === 'refunded') return '退款已完成';
  return task.status === 'success' ? '按有效产出结算' : '尚未结算';
}

async function cancelTask(task: AsyncTask) {
  actingTaskId.value = task.id;
  try {
    await taskStore.requestCancel(task.id);
    message.success('取消请求已提交，服务端确认后结算未执行项');
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '取消请求失败，请稍后重试',
    );
  } finally {
    actingTaskId.value = '';
  }
}

async function retryTask(task: AsyncTask) {
  actingTaskId.value = task.id;
  try {
    await taskStore.retryTask(task.id);
    message.success('已创建重试任务');
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '重试任务创建失败，请稍后重试',
    );
  } finally {
    actingTaskId.value = '';
  }
}

function reviewResult(task: AsyncTask) {
  router.push({
    path: '/fusion/adgen-library',
    query: { generationJob: task.id, tab: 'history' },
  });
}

onMounted(async () => {
  try {
    await restoreFromRoute();
    await projectStore.loadProjectOptions();
    await taskStore.refresh();
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '任务中心加载失败，请稍后重试',
    );
  }
});
</script>

<template>
  <Page class="bg-slate-50">
    <div class="flex w-full min-w-0 flex-col gap-4">
      <section class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 class="m-0 text-xl font-semibold text-slate-900">全局任务中心</h1>
          <p class="mb-0 mt-1 text-sm text-slate-500">
            统一跟踪 AI 生成、批处理和多平台广告发布任务。
          </p>
        </div>
        <Button :loading="taskStore.loading" @click="taskStore.refresh()">
          <span class="flex items-center gap-1.5"
            ><IconifyIcon icon="lucide:refresh-cw" />刷新</span
          >
        </Button>
      </section>

      <Row :gutter="[12, 12]">
        <Col v-for="item in stats" :key="item.label" :xs="12" :lg="6">
          <Card class="border-slate-200" :body-style="{ padding: '16px' }">
            <div class="flex items-center gap-3">
              <div
                class="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600"
              >
                <IconifyIcon :icon="item.icon" />
              </div>
              <div>
                <div class="text-xs text-slate-500">{{ item.label }}</div>
                <div class="text-xl font-semibold text-slate-900">
                  {{ item.value }}
                </div>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      <Alert
        message="统一计费规则：失败、未产生有效结果或允许退款的取消任务全额退款；部分成功只结算有效产出。"
        type="info"
        show-icon
      />

      <Alert
        :message="`当前仅展示项目：${projectStore.currentProject?.name || '全部项目'}`"
        description="顶部全局项目切换后，任务列表与统计会同步更新。"
        type="info"
        show-icon
      />

      <Card class="border-slate-200" :body-style="{ padding: 0 }">
        <div class="flex flex-wrap gap-3 border-b border-slate-200 p-4">
          <Select
            v-model:value="typeFilter"
            class="w-40"
            :options="[
              { label: '全部任务类型', value: 'all' },
              { label: 'AI 创意任务', value: 'ai' },
              { label: '广告发布任务', value: 'publish' },
            ]"
          />
          <Select
            v-model:value="statusFilter"
            class="w-40"
            :options="[
              { label: '全部状态', value: 'all' },
              ...Object.entries(statusConfig).map(([value, item]) => ({
                label: item.label,
                value,
              })),
            ]"
          />
        </div>
        <Table
          :columns="columns"
          :data-source="filteredTasks"
          :loading="taskStore.loading"
          :pagination="{ pageSize: 12, showSizeChanger: true }"
          :row-key="(row: AsyncTask) => row.id"
          :scroll="{ x: 1080 }"
          size="middle"
        >
          <template #emptyText
            ><Empty description="没有符合条件的任务"
          /></template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'task'">
              <div class="flex items-start gap-3">
                <div
                  class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600"
                >
                  <IconifyIcon
                    :icon="
                      record.platform ? 'lucide:rocket' : 'lucide:sparkles'
                    "
                  />
                </div>
                <div class="min-w-0">
                  <div class="font-medium text-slate-900">
                    {{ record.title }}
                  </div>
                  <div class="mt-1 text-xs text-slate-500">
                    {{ record.id }} · {{ record.capability || record.platform }}
                  </div>
                </div>
              </div>
            </template>
            <template v-else-if="column.key === 'status'">
              <Tag
                :color="statusConfig[record.status as AsyncTaskStatus].color"
              >
                {{ statusConfig[record.status as AsyncTaskStatus].label }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'progress'">
              <Progress
                :percent="record.progress"
                :status="record.status === 'failed' ? 'exception' : undefined"
              />
            </template>
            <template v-else-if="column.key === 'resultCount'">{{
              record.resultCount ?? '-'
            }}</template>
            <template v-else-if="column.key === 'billing'">
              <span class="text-xs text-slate-600">{{
                billingText(record)
              }}</span>
            </template>
            <template v-else-if="column.key === 'actions'">
              <Popconfirm
                v-if="['queued', 'running'].includes(record.status)"
                title="确认取消这个任务？"
                description="执行端会停止未完成项，并按有效产出进行结算或退款。"
                ok-text="确认取消"
                cancel-text="继续执行"
                @confirm="cancelTask(record as AsyncTask)"
              >
                <Button
                  type="link"
                  danger
                  :loading="actingTaskId === record.id"
                >
                  取消
                </Button>
              </Popconfirm>
              <Button
                v-if="['cancelled', 'failed'].includes(record.status)"
                type="link"
                :loading="actingTaskId === record.id"
                @click="retryTask(record as AsyncTask)"
              >
                重试
              </Button>
              <Button
                v-if="['partial_success', 'success'].includes(record.status)"
                type="link"
                @click="reviewResult(record as AsyncTask)"
              >
                审核结果
              </Button>
            </template>
          </template>
        </Table>
      </Card>
    </div>
  </Page>
</template>
