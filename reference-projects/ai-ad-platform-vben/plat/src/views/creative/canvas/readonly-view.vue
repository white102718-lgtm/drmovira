<script lang="ts" setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAccessStore } from '@vben/stores';
import { Page } from '@vben/common-ui';
import { Alert, Button, Spin } from 'ant-design-vue';
import { getCanvasViewApi } from '#/api/canvas';
import type { CanvasDraft } from '#/embedded/adgen-canvas/features/canvas/types';
import { mountReadonlyCanvas } from '#/embedded/adgen-canvas/readonly-embed';

const accessStore = useAccessStore();
const route = useRoute();
const router = useRouter();
const target = ref<HTMLDivElement>();
const loading = ref(false);
const error = ref('');
let requestId = 0;
let dispose: (() => void) | undefined;

/** 草稿只传给展示组件，不连接保存或生成接口。 */
async function load() {
  const current = ++requestId;
  dispose?.();
  dispose = undefined;
  loading.value = true;
  error.value = '';
  try {
    const canvas = await getCanvasViewApi(String(route.params.id));
    await nextTick();
    if (current !== requestId || !target.value) return;
    const draft = canvas.draft || {
      version: 1,
      title: canvas.name,
      nodes: [],
      edges: [],
      viewport: {},
      updatedAt: canvas.updatedAt,
    };
    dispose = mountReadonlyCanvas(
      target.value,
      draft as unknown as CanvasDraft,
      canvas.name,
      () => {
        void router.push('/creative/canvas');
      },
      canvas.id,
      () => accessStore.accessToken,
    );
  } catch (cause) {
    if (current === requestId)
      error.value = cause instanceof Error ? cause.message : '画布加载失败';
  } finally {
    if (current === requestId) loading.value = false;
  }
}
watch(
  () => route.params.id,
  () => {
    void load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  requestId += 1;
  dispose?.();
});
</script>

<template>
  <Page
    class="flex h-full min-h-0 flex-col"
    content-class="!h-auto min-h-0 flex flex-1 flex-col overflow-hidden p-0"
  >
    <div class="relative h-full min-h-0 flex-1">
      <div ref="target" class="h-full min-h-0 w-full overflow-hidden" />
      <div
        v-if="loading"
        class="bg-background/80 absolute inset-0 z-50 flex items-center justify-center"
      >
        <Spin />
      </div>
      <div
        v-else-if="error"
        class="bg-background absolute inset-0 z-50 flex flex-col items-center justify-center gap-4 p-6"
      >
        <Alert type="error" :message="error" show-icon />
        <div class="flex gap-2">
          <Button @click="router.push('/creative/canvas')">返回列表</Button
          ><Button @click="load">重试</Button>
        </div>
      </div>
    </div>
  </Page>
</template>
