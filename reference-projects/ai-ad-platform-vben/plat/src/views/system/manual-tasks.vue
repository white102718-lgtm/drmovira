<script setup lang="ts">
import type {
  ManualTask,
  ManualTaskAction,
  ManualTaskExecution,
  ManualTaskStatus,
} from '#/api/main/manual-tasks';
import type { TableColumnsType } from 'ant-design-vue';

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useAccess } from '@vben/access';
import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
  Input,
  message,
  Modal,
  Space,
  Table,
  Tag,
} from 'ant-design-vue';
import {
  getManualTaskExecution,
  getManualTaskExecutions,
  getManualTasks,
  triggerManualTask,
} from '#/api/main/manual-tasks';

defineOptions({ name: 'SystemManualTasks' });

const { hasAccessByCodes } = useAccess();
const canExecute = computed(() =>
  hasAccessByCodes(['system:manual-task:execute']),
);
const tasks = ref<ManualTask[]>([]);
const executions = ref<ManualTaskExecution[]>([]);
const loading = ref(false);
const triggering = ref<string>();
const confirmOpen = ref(false);
const confirmTask = ref<ManualTask>();
const confirmAction = ref<ManualTaskAction>();
const confirmationInput = ref('');
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const drawerOpen = ref(false);
const detailLoading = ref(false);
const selected = ref<ManualTaskExecution>();
let timer: ReturnType<typeof setInterval> | undefined;

const columns: TableColumnsType = [
  { dataIndex: 'taskName', title: '任务', width: 220 },
  { dataIndex: 'actionName', title: '操作类型', width: 120 },
  { dataIndex: 'status', title: '状态', width: 100 },
  { dataIndex: 'triggeredByName', title: '触发人', width: 130 },
  { dataIndex: 'triggeredAt', title: '触发时间', width: 180 },
  { dataIndex: 'startedAt', title: '开始时间', width: 180 },
  { dataIndex: 'finishedAt', title: '完成时间', width: 180 },
  { key: 'action', title: '操作', width: 90, fixed: 'right' },
];

const statusMeta: Record<ManualTaskStatus, { color: string; label: string }> = {
  FAILED: { color: 'error', label: '失败' },
  PENDING: { color: 'default', label: '排队中' },
  RUNNING: { color: 'processing', label: '执行中' },
  SUCCESS: { color: 'success', label: '成功' },
};

async function load() {
  loading.value = true;
  try {
    const [taskItems, result] = await Promise.all([
      getManualTasks(),
      getManualTaskExecutions({ page: page.value, pageSize: pageSize.value }),
    ]);
    tasks.value = taskItems;
    executions.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}

function confirmRun(task: ManualTask, action: ManualTaskAction) {
  confirmTask.value = task;
  confirmAction.value = action;
  confirmationInput.value = '';
  confirmOpen.value = true;
}

const confirmationValid = computed(() => {
  if (!confirmAction.value?.dangerous) return true;
  return confirmationInput.value === confirmAction.value.confirmationText;
});

async function submitTask() {
  const task = confirmTask.value;
  const action = confirmAction.value;
  if (!task || !action || !confirmationValid.value) return;
  const triggerKey = `${task.code}:${action.code}`;
  triggering.value = triggerKey;
  try {
    await triggerManualTask(
      task.code,
      action.code,
      confirmationInput.value || undefined,
    );
    message.success(`${action.name}任务已提交`);
    confirmOpen.value = false;
    page.value = 1;
    await load();
  } finally {
    triggering.value = undefined;
  }
}

async function showLog(record: Record<string, any>) {
  drawerOpen.value = true;
  detailLoading.value = true;
  try {
    selected.value = await getManualTaskExecution(String(record.id));
  } finally {
    detailLoading.value = false;
  }
}

async function refreshLog() {
  if (!selected.value) return;
  detailLoading.value = true;
  try {
    selected.value = await getManualTaskExecution(selected.value.id);
  } finally {
    detailLoading.value = false;
  }
}

async function copyLog() {
  if (!selected.value?.logContent) return;
  await navigator.clipboard.writeText(selected.value.logContent);
  message.success('日志已复制');
}

function changePage(next: number, size: number) {
  page.value = next;
  pageSize.value = size;
  void load();
}

onMounted(() => {
  void load();
  timer = setInterval(() => {
    if (
      executions.value.some((item) =>
        ['PENDING', 'RUNNING'].includes(item.status),
      )
    )
      void load();
  }, 3000);
});
onBeforeUnmount(() => timer && clearInterval(timer));
</script>

<template>
  <main class="system-management-page min-h-full p-4 text-slate-700">
    <div class="mx-auto flex max-w-[1600px] flex-col gap-4">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="m-0 text-2xl font-semibold text-slate-900">手动任务</h1>
          <p class="m-0 mt-1 text-sm text-slate-500">
            人工触发可重复执行的后台任务，并查看每次触发事件和完整日志。
          </p>
        </div>
        <Button :loading="loading" @click="load">
          <IconifyIcon icon="lucide:refresh-cw" /> 刷新
        </Button>
      </header>

      <Alert
        v-if="!canExecute"
        message="当前账号只能查看任务和执行记录，不能触发任务。"
        show-icon
        type="info"
      />

      <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card v-for="task in tasks" :key="task.code" :title="task.name">
          <p class="min-h-10 text-sm text-slate-500">{{ task.description }}</p>
          <template #extra>
            <Tag v-if="task.running" color="processing">执行中</Tag>
          </template>
          <Space wrap>
            <Button
              v-for="action in task.actions"
              :key="action.code"
              :danger="action.dangerous"
              :type="action.dangerous ? 'primary' : 'default'"
              :disabled="!canExecute || task.running"
              :loading="triggering === `${task.code}:${action.code}`"
              @click="confirmRun(task, action)"
            >
              <IconifyIcon
                :icon="
                  action.dangerous
                    ? 'lucide:database-zap'
                    : 'lucide:scan-search'
                "
              />
              {{ action.name }}
            </Button>
          </Space>
        </Card>
        <Empty
          v-if="!loading && tasks.length === 0"
          description="暂无手动任务"
        />
      </section>

      <Card title="触发事件">
        <Table
          row-key="id"
          :columns="columns"
          :data-source="executions"
          :loading="loading"
          :pagination="{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
          }"
          :scroll="{ x: 1100 }"
          @change="
            (pagination) =>
              changePage(pagination.current || 1, pagination.pageSize || 20)
          "
        >
          <template #bodyCell="{ column, record }">
            <Tag
              v-if="column.dataIndex === 'status'"
              :color="statusMeta[record.status as ManualTaskStatus].color"
            >
              {{ statusMeta[record.status as ManualTaskStatus].label }}
            </Tag>
            <Space v-else-if="column.key === 'action'">
              <Button type="link" @click="showLog(record)">查看日志</Button>
            </Space>
          </template>
        </Table>
      </Card>
    </div>

    <Drawer v-model:open="drawerOpen" title="执行日志" width="min(900px, 92vw)">
      <template #extra>
        <Space>
          <Button :disabled="!selected?.logContent" @click="copyLog"
            >复制全部</Button
          >
          <Button :loading="detailLoading" @click="refreshLog">刷新日志</Button>
        </Space>
      </template>
      <div v-if="selected" class="mb-3 text-sm text-slate-500">
        {{ selected.taskName }} · {{ selected.actionName }} ·
        {{ selected.triggeredByName }} · {{ selected.triggeredAt }}
      </div>
      <pre
        class="min-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-4 text-xs leading-6 text-slate-100"
        >{{
          detailLoading ? '正在加载日志…' : selected?.logContent || '暂无日志'
        }}</pre
      >
    </Drawer>

    <Modal
      v-model:open="confirmOpen"
      :title="confirmAction?.dangerous ? '确认执行迁移' : '确认执行预检'"
      :closable="!triggering"
      :mask-closable="!triggering"
      :keyboard="!triggering"
    >
      <div class="space-y-4">
        <Alert
          :message="confirmAction?.name"
          :description="confirmAction?.description"
          show-icon
          :type="confirmAction?.dangerous ? 'warning' : 'info'"
        />
        <div v-if="confirmAction?.dangerous" class="space-y-2">
          <label
            for="manual-task-confirmation"
            class="text-foreground block text-sm font-medium"
          >
            请输入“{{ confirmAction.confirmationText }}”确认
          </label>
          <Input
            id="manual-task-confirmation"
            v-model:value="confirmationInput"
            :disabled="Boolean(triggering)"
            :placeholder="confirmAction.confirmationText"
            autocomplete="off"
            @press-enter="confirmationValid && submitTask()"
          />
        </div>
      </div>
      <template #footer>
        <Space>
          <Button :disabled="Boolean(triggering)" @click="confirmOpen = false"
            >取消</Button
          >
          <Button
            :danger="confirmAction?.dangerous"
            type="primary"
            :disabled="!confirmationValid"
            :loading="Boolean(triggering)"
            @click="submitTask"
          >
            {{ confirmAction?.name || '确认' }}
          </Button>
        </Space>
      </template>
    </Modal>
  </main>
</template>
