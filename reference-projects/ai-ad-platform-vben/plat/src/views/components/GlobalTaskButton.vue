<script lang="ts" setup>
import type { AsyncTaskStatus } from '#/api';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import {
  Badge,
  Button,
  Drawer,
  Empty,
  message,
  Popconfirm,
  Progress,
  Skeleton,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { useGlobalTaskStore } from '#/store';

const router = useRouter();
const taskStore = useGlobalTaskStore();
const actingTaskId = ref('');

const statusConfig: Record<AsyncTaskStatus, { color: string; text: string }> = {
  cancel_requested: { color: 'warning', text: '取消确认中' },
  cancelled: { color: 'default', text: '已取消' },
  failed: { color: 'error', text: '失败，待退款' },
  partial_success: { color: 'warning', text: '部分成功' },
  queued: { color: 'processing', text: '排队中' },
  refund_pending: { color: 'warning', text: '退款处理中' },
  refunded: { color: 'default', text: '已退款' },
  running: { color: 'processing', text: '执行中' },
  success: { color: 'success', text: '已完成' },
};

const currentTasks = computed(() => taskStore.tasks);

async function openAllTasks() {
  taskStore.drawerOpen = false;
  await router.push('/fusion/ai-tasks');
}

async function cancelTask(taskId: string) {
  actingTaskId.value = taskId;
  try {
    await taskStore.requestCancel(taskId);
    message.success('取消请求已提交，服务端确认后结算未执行项');
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '取消请求失败，请稍后重试',
    );
  } finally {
    actingTaskId.value = '';
  }
}

async function retryTask(taskId: string) {
  actingTaskId.value = taskId;
  try {
    await taskStore.retryTask(taskId);
    message.success('已创建重试任务');
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '重试任务创建失败，请稍后重试',
    );
  } finally {
    actingTaskId.value = '';
  }
}

onMounted(() => taskStore.refresh());
</script>

<template>
  <div class="flex h-full items-center px-1">
    <Badge :count="taskStore.activeCount" :overflow-count="99">
      <Tooltip title="全局任务中心">
        <Button
          type="text"
          aria-label="打开全局任务中心"
          class="flex size-10 min-w-10 items-center justify-center p-0 text-slate-600"
          @click="taskStore.openDrawer"
        >
          <IconifyIcon icon="lucide:bell" class="text-xl" aria-hidden="true" />
        </Button>
      </Tooltip>
    </Badge>
  </div>

  <Drawer
    v-model:open="taskStore.drawerOpen"
    :width="440"
    title="全局任务中心"
    placement="right"
  >
    <template #extra>
      <Button type="link" @click="taskStore.refresh()">刷新</Button>
    </template>

    <Skeleton v-if="taskStore.loading" active :paragraph="{ rows: 8 }" />
    <Empty v-else-if="currentTasks.length === 0" description="暂无异步任务" />
    <div v-else class="space-y-3">
      <article
        v-for="task in currentTasks"
        :key="task.id"
        class="rounded-lg border border-slate-200 bg-white p-4"
      >
        <div class="mb-2 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="truncate text-sm font-medium text-slate-900">
              {{ task.title }}
            </div>
            <div class="mt-1 text-xs text-slate-500">{{ task.updatedAt }}</div>
          </div>
          <Tag :color="statusConfig[task.status].color">
            {{ statusConfig[task.status].text }}
          </Tag>
        </div>
        <Progress
          v-if="
            task.status === 'cancel_requested' ||
            task.status === 'queued' ||
            task.status === 'running'
          "
          :percent="task.progress"
          :status="task.status === 'running' ? 'active' : 'normal'"
        />
        <p v-if="task.message" class="mb-0 mt-2 text-xs text-slate-600">
          {{ task.message }}
        </p>
        <div
          v-if="
            ['queued', 'running'].includes(task.status) ||
            ['cancelled', 'failed'].includes(task.status)
          "
          class="mt-3 flex justify-end"
        >
          <Popconfirm
            v-if="['queued', 'running'].includes(task.status)"
            title="确认取消这个任务？"
            description="未执行项会停止，并按有效产出进行结算或退款。"
            ok-text="确认取消"
            cancel-text="继续执行"
            @confirm="cancelTask(task.id)"
          >
            <Button danger :loading="actingTaskId === task.id"> 取消 </Button>
          </Popconfirm>
          <Button
            v-else
            :loading="actingTaskId === task.id"
            @click="retryTask(task.id)"
          >
            重试
          </Button>
        </div>
      </article>
    </div>

    <div class="mt-4 border-t border-slate-200 pt-4">
      <Button block @click="openAllTasks">查看全部任务</Button>
    </div>
  </Drawer>
</template>
