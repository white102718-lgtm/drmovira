<script lang="ts" setup>
import {
  computed,
  onActivated,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useAccessStore } from '@vben/stores';

import type {
  AdgenFeatureRoute,
  AdgenRouteModel,
  AdgenRuntimeConfig,
} from '#/api/adgen-operations';

import { getAdgenRuntimeConfigApi } from '#/api/adgen-operations';
import { Alert, Button } from 'ant-design-vue';
import {
  type AdgenCanvasMountHandle,
  mountAdgenCanvas,
} from '#/embedded/adgen-canvas/embed';
import { getEmptyMediaGenerationConfig } from '#/embedded/adgen-canvas/utils/mediaModelConfig';

const route = useRoute();
const router = useRouter();
const accessStore = useAccessStore();
const canvasMountTarget = ref<HTMLDivElement>();
const mountError = ref('');
let canvasMountHandle: AdgenCanvasMountHandle | undefined;
let hasActivated = false;
let mountRequestId = 0;

const canvasId = computed(() => {
  const routeCanvasId = route.params.id;
  return typeof routeCanvasId === 'string' && routeCanvasId.trim()
    ? routeCanvasId.trim()
    : 'adpulse-default';
});

function getInitialTitle() {
  const title = route.query.title;
  return typeof title === 'string' && title.trim()
    ? title.trim()
    : 'AI创意画布';
}

function getAccessToken(): null | string {
  const token = accessStore.accessToken;
  if (!token || token.startsWith('fusion-demo-role:')) return null;
  return token;
}

function handleBack() {
  const target = route.params.id ? '/creative/canvas' : '/home';
  void router.push(target);
}

function buildPendingCanvasMediaConfig() {
  return getEmptyMediaGenerationConfig();
}

/**
 * 将后端返回的数据库模型文档转换为画布运行时描述。
 *
 * @remarks
 * 功能路由接口是模型目录的唯一来源；这里不再合并前端内置模型配置。
 */
function buildRuntimeModelCatalogEntry(
  routeModel: AdgenRouteModel,
) {
  const runtimeModelConfig = routeModel.config || {};
  return {
    ...runtimeModelConfig,
    description: runtimeModelConfig.description || routeModel.name,
    label: routeModel.name || routeModel.id,
    pricing: runtimeModelConfig.pricing || {},
  };
}

function buildCanvasMediaConfig(runtimeConfig: AdgenRuntimeConfig) {
  const config = getEmptyMediaGenerationConfig();
  config.currency = {
    code: runtimeConfig.currency?.code || 'CNY',
    cnyToUsdRate: runtimeConfig.currency?.cnyToUsdRate || 0.14,
  };

  for (const routeConfig of runtimeConfig.featureRoutes) {
    for (const routeModel of routeConfig.models) {
      config.model_catalog[routeModel.id] = {
        ...buildRuntimeModelCatalogEntry(routeModel),
      };
    }

    const enabledModels = routeConfig.models
      .filter((model) => model.enabled)
      .map((model) => model.id);
    const defaultModel = enabledModels.includes(routeConfig.defaultModel)
      ? routeConfig.defaultModel
      : enabledModels[0] || '';

    config.features[routeConfig.featureKey] = {
      ...(routeConfig.config || {}),
      [routeConfig.limitField]: routeConfig.limit,
      default_model: defaultModel,
      enabled_models: enabledModels,
      ...(routeConfig.resolution
        ? { default_resolution: routeConfig.resolution }
        : {}),
    };
  }

  return config;
}

async function refreshCanvasMediaConfig() {
  const requestId = ++mountRequestId;

  try {
    const mediaConfig = buildCanvasMediaConfig(
      await getAdgenRuntimeConfigApi(),
    );
    if (requestId !== mountRequestId) return;
    canvasMountHandle?.updateOptions({ mediaConfig });
  } catch (error) {
    console.error('[Canvas] 模型路由配置加载失败，模型列表保持为空:', error);
  }
}

function mountCanvas() {
  if (!route.path.startsWith('/creative/canvas/')) return;

  const mountTarget = canvasMountTarget.value;
  if (!mountTarget) return;

  mountRequestId += 1;
  mountError.value = '';

  try {
    canvasMountHandle?.dispose();
    canvasMountHandle = mountAdgenCanvas(mountTarget, {
      canvasId: canvasId.value,
      getAccessToken,
      initialTitle: getInitialTitle(),
      mediaConfig: buildPendingCanvasMediaConfig(),
      onBack: handleBack,
    });
    void refreshCanvasMediaConfig();
  } catch (error) {
    mountError.value =
      error instanceof Error ? error.message : '画布编辑器加载失败';
  }
}

onMounted(() => {
  mountCanvas();
});
onActivated(() => {
  if (hasActivated) void refreshCanvasMediaConfig();
  hasActivated = true;
});
onBeforeUnmount(() => {
  mountRequestId += 1;
  canvasMountHandle?.dispose();
  canvasMountHandle = undefined;
});

// 画布名称属于草稿内容，不是嵌入实例的身份。标题同步到路由时不得重新挂载，
// 否则会重新加载服务端视口，表现为改名后节点整体发生偏移。
watch(canvasId, () => {
  mountCanvas();
});
</script>

<template>
  <Page
    class="bg-slate-950 flex h-full min-h-0 flex-col"
    content-class="!h-auto min-h-0 flex flex-1 flex-col overflow-hidden p-0"
  >
    <div class="relative h-full min-h-0 w-full">
      <div
        id="adgen-creative-canvas-mount"
        ref="canvasMountTarget"
        class="h-full min-h-0 w-full overflow-hidden"
        :data-canvas-id="canvasId"
      ></div>

      <div
        v-if="mountError"
        class="absolute inset-0 z-50 flex items-center justify-center bg-slate-950/90 p-6"
      >
        <div class="w-full max-w-lg">
          <Alert
            :description="mountError"
            message="AI创意画布加载失败"
            show-icon
            type="error"
          />
          <div class="mt-4 flex justify-center gap-2">
            <Button @click="handleBack">
              <span class="flex items-center gap-1.5">
                <IconifyIcon icon="lucide:arrow-left" />
                返回
              </span>
            </Button>
            <Button type="primary" @click="mountCanvas">
              <span class="flex items-center gap-1.5">
                <IconifyIcon icon="lucide:refresh-cw" />
                重试
              </span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  </Page>
</template>
