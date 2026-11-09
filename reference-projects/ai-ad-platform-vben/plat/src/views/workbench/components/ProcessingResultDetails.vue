<script setup lang="ts">
import type { ResourceApplication } from '#/store/resource-applications';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { Button, Image, Spin, Tag } from 'ant-design-vue';

import { downloadOpenStoredFileApi, getOpenStoredFileApi } from '#/api/file';

interface ResultImage {
  error?: string;
  id: string;
  name: string;
  url?: string;
}

const props = defineProps<{
  actionData?: Record<string, unknown>;
  application: ResourceApplication;
}>();

type HandlerField = NonNullable<
  NonNullable<ResourceApplication['handlerAction']>['formSchema']
>[number];
type AllocatedAsset = NonNullable<
  ResourceApplication['allocatedAssets']
>[number];

const resultImages = ref<Record<string, ResultImage[]>>({});
const loadingImageFields = ref<Set<string>>(new Set());
const resultSection = ref<HTMLElement | null>(null);
let imageRequestVersion = 0;
let imageLoadFrame: number | undefined;
let imageLoadIdleCallback: number | undefined;
let imageLoadTimer: number | undefined;
let resultObserver: IntersectionObserver | undefined;
let isResultVisible = false;

const resultFields = computed(() => {
  const actionData = props.actionData ?? {};
  return (props.application.handlerAction?.formSchema ?? []).filter(
    (field) =>
      field.type !== 'section' && hasResultValue(actionData[field.key]),
  );
});

const allocatedAssets = computed<AllocatedAsset[]>(() => {
  if ((props.application.allocatedAssets?.length ?? 0) > 0) {
    return props.application.allocatedAssets ?? [];
  }
  const snapshots = props.actionData?._allocatedAssets;
  if (!Array.isArray(snapshots)) return [];
  return snapshots.filter(
    (item): item is AllocatedAsset =>
      typeof item === 'object' &&
      item !== null &&
      'id' in item &&
      'assetCode' in item &&
      'assetName' in item &&
      'assetType' in item,
  );
});

const hasResult = computed(
  () => resultFields.value.length > 0 || allocatedAssets.value.length > 0,
);

function hasResultValue(value: unknown) {
  if (Array.isArray(value)) return value.length > 0;
  return value !== undefined && value !== null && value !== '';
}

function imageIds(field: HandlerField) {
  const value = props.actionData?.[field.key];
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function releaseImageUrls(images = resultImages.value) {
  for (const items of Object.values(images)) {
    for (const item of items) {
      if (item.url) URL.revokeObjectURL(item.url);
    }
  }
}

function cancelScheduledImageLoad() {
  if (imageLoadFrame !== undefined) {
    window.cancelAnimationFrame(imageLoadFrame);
    imageLoadFrame = undefined;
  }
  if (imageLoadIdleCallback !== undefined) {
    window.cancelIdleCallback(imageLoadIdleCallback);
    imageLoadIdleCallback = undefined;
  }
  if (imageLoadTimer !== undefined) {
    window.clearTimeout(imageLoadTimer);
    imageLoadTimer = undefined;
  }
}

function scheduleResultImagesLoad() {
  if (!isResultVisible || loadingImageFields.value.size === 0) return;

  cancelScheduledImageLoad();
  // 先让首屏完成两帧布局与绘制，再利用浏览器空闲时间下载较大的凭证图片。
  imageLoadFrame = window.requestAnimationFrame(() => {
    imageLoadFrame = window.requestAnimationFrame(() => {
      imageLoadFrame = undefined;
      const scheduleWhenIdle = window.requestIdleCallback;
      if (typeof scheduleWhenIdle === 'function') {
        imageLoadIdleCallback = scheduleWhenIdle(
          () => {
            imageLoadIdleCallback = undefined;
            void loadResultImages();
          },
          { timeout: 1500 },
        );
        return;
      }
      imageLoadTimer = window.setTimeout(() => {
        imageLoadTimer = undefined;
        void loadResultImages();
      }, 0);
    });
  });
}

function prepareResultImages() {
  imageRequestVersion += 1;
  cancelScheduledImageLoad();
  releaseImageUrls();
  resultImages.value = {};
  loadingImageFields.value = new Set(
    resultFields.value
      .filter((field) => field.type === 'image-upload')
      .map((field) => field.key),
  );
  scheduleResultImagesLoad();
}

async function loadResultImages() {
  const requestVersion = ++imageRequestVersion;
  releaseImageUrls();
  resultImages.value = {};

  const imageFields = resultFields.value.filter(
    (field) => field.type === 'image-upload',
  );
  loadingImageFields.value = new Set(imageFields.map((field) => field.key));

  const nextImages: Record<string, ResultImage[]> = {};
  await Promise.all(
    imageFields.map(async (field) => {
      nextImages[field.key] = await Promise.all(
        imageIds(field).map(async (fileId) => {
          try {
            const [file, blob] = await Promise.all([
              getOpenStoredFileApi(fileId),
              downloadOpenStoredFileApi(fileId),
            ]);
            return {
              id: fileId,
              name: file.originalName || `办理凭证 ${fileId}`,
              url: URL.createObjectURL(blob),
            };
          } catch {
            return {
              error: '文件加载失败',
              id: fileId,
              name: `办理凭证 ${fileId}`,
            };
          }
        }),
      );
    }),
  );

  if (requestVersion !== imageRequestVersion) {
    releaseImageUrls(nextImages);
    return;
  }
  resultImages.value = nextImages;
  loadingImageFields.value = new Set();
}

function formatResultValue(field: HandlerField) {
  const value = props.actionData?.[field.key];
  if (field.type === 'number') {
    const numberValue = Number(value);
    if (Number.isFinite(numberValue)) {
      return numberValue.toLocaleString('zh-CN', {
        maximumFractionDigits: 2,
        minimumFractionDigits: 2,
      });
    }
  }
  if (Array.isArray(value)) return value.map(String).join('、');
  if (typeof value === 'boolean') return value ? '是' : '否';
  return String(value ?? '-');
}

watch(
  () => [props.actionData, props.application.handlerAction] as const,
  prepareResultImages,
  { deep: true, immediate: true },
);

watch(
  resultSection,
  (section, previousSection) => {
    if (previousSection) resultObserver?.unobserve(previousSection);
    if (section) resultObserver?.observe(section);
  },
  { flush: 'post' },
);

onMounted(() => {
  if (!('IntersectionObserver' in window)) {
    isResultVisible = true;
    scheduleResultImagesLoad();
    return;
  }
  resultObserver = new IntersectionObserver(([entry]) => {
    isResultVisible = Boolean(entry?.isIntersecting);
    if (isResultVisible) scheduleResultImagesLoad();
    else cancelScheduledImageLoad();
  });
  if (resultSection.value) resultObserver.observe(resultSection.value);
});

onBeforeUnmount(() => {
  imageRequestVersion += 1;
  cancelScheduledImageLoad();
  resultObserver?.disconnect();
  releaseImageUrls();
});
</script>

<template>
  <section
    v-if="hasResult"
    ref="resultSection"
    aria-label="办理结果"
    class="mt-3 rounded-lg border border-teal-100 bg-teal-50/60 p-3"
  >
    <h4 class="m-0 text-sm font-semibold text-slate-800">办理结果</h4>

    <dl
      v-if="resultFields.length > 0"
      class="mb-0 mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2"
    >
      <div
        v-for="field in resultFields"
        :key="field.key"
        :class="
          field.width === 'full' || field.type === 'image-upload'
            ? 'sm:col-span-2'
            : ''
        "
      >
        <dt
          class="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500"
        >
          <span>{{ field.label }}</span>
          <span v-if="field.type === 'image-upload'">
            {{ imageIds(field).length }} 张 · 点击图片可放大
          </span>
        </dt>
        <dd
          v-if="field.type !== 'image-upload'"
          class="mb-0 mt-1 text-sm font-medium text-slate-800"
        >
          {{ formatResultValue(field) }}
        </dd>
        <dd v-else class="mb-0 mt-2">
          <div
            v-if="loadingImageFields.has(field.key)"
            class="flex min-h-28 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white text-xs text-slate-500"
            role="status"
          >
            <Spin />
            正在加载图片
          </div>
          <div v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <figure
              v-for="image in resultImages[field.key] || []"
              :key="image.id"
              class="m-0 min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white"
            >
              <div class="flex h-28 items-center justify-center bg-slate-100">
                <Image
                  v-if="image.url"
                  :alt="image.name"
                  :height="112"
                  :src="image.url"
                  width="100%"
                  class="object-cover"
                />
                <div
                  v-else
                  class="flex h-full w-full flex-col items-center justify-center border border-dashed border-red-200 p-2 text-center"
                >
                  <span class="text-xs text-red-600">{{ image.error }}</span>
                  <Button type="link" class="!px-0" @click="loadResultImages">
                    重试加载
                  </Button>
                </div>
              </div>
              <figcaption
                class="truncate px-2 py-2 text-xs text-slate-600"
                :title="image.name"
              >
                {{ image.name }}
              </figcaption>
            </figure>
          </div>
        </dd>
      </div>
    </dl>

    <div v-if="allocatedAssets.length > 0" class="mt-3">
      <p class="m-0 text-xs font-medium text-slate-600">
        已分配资产（{{ allocatedAssets.length }}）
      </p>
      <ul class="mb-0 mt-2 space-y-2 p-0">
        <li
          v-for="asset in allocatedAssets"
          :key="asset.id"
          class="flex list-none flex-col gap-3 rounded-md border border-teal-100 bg-white px-3 py-3 sm:flex-row sm:items-start sm:justify-between"
        >
          <div class="min-w-0 flex-1">
            <p class="m-0 break-words text-sm font-medium text-slate-800">
              {{ asset.assetName }}
            </p>
            <dl
              class="mb-0 mt-2 grid grid-cols-[64px_minmax(0,1fr)] gap-x-2 gap-y-1 text-xs"
            >
              <dt class="text-slate-500">资产 ID</dt>
              <dd class="m-0 break-all font-medium text-slate-700">
                {{ asset.id }}
              </dd>
              <dt class="text-slate-500">资产编码</dt>
              <dd class="m-0 break-all font-medium text-slate-700">
                {{ asset.assetCode }}
              </dd>
              <template v-if="asset.channelName || asset.projectName">
                <dt class="text-slate-500">资产归属</dt>
                <dd class="m-0 break-words font-medium text-slate-700">
                  {{ asset.channelName || asset.projectName }}
                </dd>
              </template>
            </dl>
          </div>
          <Tag class="!m-0 shrink-0">{{ asset.assetType }}</Tag>
        </li>
      </ul>
    </div>
  </section>
</template>
