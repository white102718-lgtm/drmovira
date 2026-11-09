import type { AiJobPayload, AsyncTask } from '#/api';

import { computed, ref } from 'vue';

import { defineStore } from 'pinia';

import {
  cancelAsyncTaskApi,
  createAiJobApi,
  getAsyncTasksApi,
  isFusionDemoMode,
  retryAsyncTaskApi,
  saveGenerationRecordApi,
  updateDemoAsyncTaskApi,
  upsertDemoAsyncTaskApi,
} from '#/api';

const audioCapabilities = new Set([
  'music-generate',
  'tts-generate',
  'tts-preview',
]);
const imageCapabilities = new Set([
  'batch-image',
  'batch-image-edit',
  'image-edit',
  'image-generate',
  'image-inpaint',
]);
const textCapabilities = new Set([
  'ad-crawler',
  'copy-script',
  'fb-ad-scraper',
  'material-tagging',
  'news-trends',
  'video-analyze',
]);

function getOutputKind(capability: AiJobPayload['capability']) {
  if (audioCapabilities.has(capability)) return 'audio' as const;
  if (imageCapabilities.has(capability)) return 'image' as const;
  if (textCapabilities.has(capability)) return 'text' as const;
  return 'video' as const;
}

export const useGlobalTaskStore = defineStore('fusion-global-task', () => {
  const drawerOpen = ref(false);
  const loading = ref(false);
  const tasks = ref<AsyncTask[]>([]);
  const demoTaskTimers = new Map<string, number[]>();

  const activeCount = computed(
    () =>
      tasks.value.filter(
        (item) =>
          item.status === 'cancel_requested' ||
          item.status === 'queued' ||
          item.status === 'running',
      ).length,
  );

  async function refresh(projectId?: string) {
    loading.value = true;
    try {
      tasks.value = await getAsyncTasksApi(projectId);
    } finally {
      loading.value = false;
    }
  }

  function clearDemoTaskTimers(taskId: string) {
    const timers = demoTaskTimers.get(taskId) ?? [];
    timers.forEach((timer) => window.clearTimeout(timer));
    demoTaskTimers.delete(taskId);
  }

  function patchTask(taskId: string, patch: Partial<AsyncTask>) {
    const current = tasks.value.find((item) => item.id === taskId);
    // Update through Vue's reactive proxy first. Mutating the canonical demo
    // proxy before this would make Vue compare equal values and skip the UI
    // update even though the timer completed successfully.
    if (current) Object.assign(current, patch);
    const canonical = updateDemoAsyncTaskApi(taskId, patch);
    return current ?? canonical;
  }

  function scheduleDemoTask(task: AsyncTask, aiPayload?: AiJobPayload) {
    if (
      !isFusionDemoMode() ||
      task.status !== 'queued' ||
      demoTaskTimers.has(task.id)
    ) {
      return;
    }

    const runningTimer = window.setTimeout(() => {
      const current = tasks.value.find((item) => item.id === task.id);
      if (current?.status !== 'queued') return;
      patchTask(task.id, {
        message: task.platform
          ? '平台资源校验完成，正在创建广告对象'
          : '输入检查完成，正在执行模型与媒体处理',
        progress: task.platform ? 45 : 36,
        status: 'running',
        updatedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
      });
    }, 700);

    const completionTimer = window.setTimeout(() => {
      const current = tasks.value.find((item) => item.id === task.id);
      if (current && ['queued', 'running'].includes(current.status)) {
        const completed = patchTask(task.id, {
          message: task.platform
            ? '广告系列、广告组和广告已创建'
            : '有效结果已生成并写入生成历史',
          progress: 100,
          resultCount: aiPayload?.expectedCount ?? current.resultCount,
          status: 'success',
          updatedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
        });
        if (aiPayload && completed?.status === 'success') {
          const kind = getOutputKind(aiPayload.capability);
          void saveGenerationRecordApi({
            assets: Array.from(
              { length: Math.min(aiPayload.expectedCount, 6) },
              (_, index) => ({
                id: `${task.id}-result-${index + 1}`,
                kind,
                name: `${aiPayload.capability}-结果-${index + 1}`,
              }),
            ),
            capability: aiPayload.capability,
            createdAt: task.createdAt,
            id: `history-${task.id}`,
            inputCount: aiPayload.inputMaterialIds?.length ?? 0,
            parameters: aiPayload.parameters,
            projectId: aiPayload.projectId,
            prompt: aiPayload.prompt ?? '',
            resultCount: aiPayload.expectedCount,
            sessionId: task.id,
            status: 'success',
            title: `${aiPayload.capability} · ${aiPayload.expectedCount} 个产出`,
          });
        }
      }
      demoTaskTimers.delete(task.id);
    }, 2200);

    demoTaskTimers.set(task.id, [runningTimer, completionTimer]);
  }

  function addTask(task: AsyncTask, aiPayload?: AiJobPayload) {
    const canonical = upsertDemoAsyncTaskApi(task);
    tasks.value = [
      canonical,
      ...tasks.value.filter((item) => item.id !== canonical.id),
    ];
    scheduleDemoTask(canonical, aiPayload);
    return canonical;
  }

  async function submitAiJob(payload: AiJobPayload) {
    const task = await createAiJobApi(payload);
    const canonical = addTask(task, payload);
    return canonical;
  }

  function openDrawer() {
    drawerOpen.value = true;
  }

  async function requestCancel(taskId: string) {
    const task = tasks.value.find((item) => item.id === taskId);
    if (!task || !['queued', 'running'].includes(task.status)) return task;
    const updated = await cancelAsyncTaskApi(taskId);
    clearDemoTaskTimers(taskId);
    const index = tasks.value.findIndex((item) => item.id === taskId);
    if (index !== -1) tasks.value[index] = updated;
    return updated;
  }

  async function retryTask(taskId: string) {
    const source = tasks.value.find((item) => item.id === taskId);
    if (!source) return;
    const retry = await retryAsyncTaskApi(taskId);
    const canonical = addTask(retry);
    drawerOpen.value = true;
    return canonical;
  }

  return {
    activeCount,
    addTask,
    drawerOpen,
    loading,
    openDrawer,
    refresh,
    requestCancel,
    retryTask,
    submitAiJob,
    tasks,
  };
});
