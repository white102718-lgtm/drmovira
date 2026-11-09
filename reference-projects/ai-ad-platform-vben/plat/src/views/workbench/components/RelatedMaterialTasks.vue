<script setup lang="ts">
import type { RelatedMaterialTask } from '#/api/task-center';

import { ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';
import { Button, Empty, Pagination, Spin, Tag } from 'ant-design-vue';
import dayjs from 'dayjs';

import { ORDER_STATUS_MAP } from '#/api/requirement';
import { listRelatedMaterialTasksApi } from '#/api/task-center';

const props = defineProps<{ taskId: string }>();
const emit = defineEmits<{ open: [orderId: string] }>();
const tasks = ref<RelatedMaterialTask[]>([]);
const total = ref(0);
const page = ref(1);
const loading = ref(false);
const error = ref(false);
const pageSize = 20;
let requestId = 0;

/** 切换投放任务或翻页后，仅允许最新请求更新当前详情。 */
async function loadTasks(nextPage = 1) {
  const currentRequest = ++requestId;
  page.value = nextPage;
  tasks.value = [];
  error.value = false;
  loading.value = true;
  try {
    const result = await listRelatedMaterialTasksApi(
      props.taskId,
      nextPage,
      pageSize,
    );
    if (currentRequest !== requestId) return;
    tasks.value = result.items;
    total.value = result.total;
  } catch {
    if (currentRequest !== requestId) return;
    error.value = true;
  } finally {
    if (currentRequest === requestId) loading.value = false;
  }
}

function formatDeliveryDate(value: null | string) {
  return value ? dayjs(value).format('YYYY-MM-DD') : '未设置';
}

function formatTime(value: null | string) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '未设置';
}

watch(
  () => props.taskId,
  () => {
    total.value = 0;
    void loadTasks();
  },
  { immediate: true },
);
</script>

<template>
  <section class="task-detail-section">
    <div
      class="text-foreground mb-3 flex min-w-0 items-center gap-2 text-sm font-semibold"
    >
      <IconifyIcon icon="lucide:images" />
      关联素材任务
      <Tag v-if="!loading && !error">{{ total }} 条</Tag>
    </div>
    <Spin v-if="loading" tip="正在加载关联素材任务" class="w-full py-6" />
    <div
      v-else-if="error"
      role="alert"
      class="text-muted-foreground flex flex-wrap items-center gap-3 py-4 text-sm"
    >
      关联素材任务加载失败，请重试
      <Button @click="loadTasks(page)">重试</Button>
    </div>
    <div v-else-if="tasks.length" class="space-y-3">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="bg-muted flex flex-wrap items-center justify-between gap-3 rounded-lg p-3"
      >
        <div class="min-w-0 flex-1 basis-56 space-y-2">
          <div class="flex flex-wrap items-center gap-2">
            <strong class="text-foreground break-words text-sm">{{
              task.title || '未命名素材任务'
            }}</strong>
            <Tag>{{
              ORDER_STATUS_MAP[task.status ?? ''] || task.status || '未知状态'
            }}</Tag>
          </div>
          <div class="text-muted-foreground break-words text-xs">
            {{ task.taskCode || task.orderNo || task.id }}
            · 负责人：{{ task.ownerName || '待分配' }} · 创建人：{{
              task.requesterName || '未知创建人'
            }}
          </div>
          <div
            class="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs"
          >
            <span
              >已完成 / 需求：{{ task.completedQuantity ?? 0 }} /
              {{ task.quantity ?? '未设置' }}</span
            >
            <span
              >交付时间：{{ formatDeliveryDate(task.expectedDeliveryAt) }}</span
            >
            <span>创建时间：{{ formatTime(task.createdAt) }}</span>
          </div>
        </div>
        <Button class="shrink-0" @click="emit('open', task.id)"
          >查看任务</Button
        >
      </div>
    </div>
    <Empty
      v-else
      :image="Empty.PRESENTED_IMAGE_SIMPLE"
      description="暂无关联素材任务"
    />
    <Pagination
      v-if="total > pageSize && !error"
      class="mt-4"
      :current="page"
      :page-size="pageSize"
      :total="total"
      :show-size-changer="false"
      :disabled="loading"
      size="small"
      @change="loadTasks"
    />
  </section>
</template>
