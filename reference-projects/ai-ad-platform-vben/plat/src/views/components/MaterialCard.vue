<script lang="ts" setup>
import { computed, onUnmounted, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { Card, Checkbox, Image, message, Tooltip, Tree } from 'ant-design-vue';

import {
  getCommonMaterialsByIdsApi,
  getMaterialsByIds,
  getMaterialUrlApi,
} from '#/api';

interface Props {
  checked: boolean;
  item: Record<string, any>;
  /** 当前页素材列表，用来在预览弹窗里翻上一张 / 下一张 */
  items?: Record<string, any>[];
  previewMode?: 'adcreative' | 'material';
  previewOnly?: boolean;
  /** 素材归属的库，决定预览走哪个详情接口：公共素材库是独立集合，materials 那条链路查不到 */
  source?: 'common' | 'material';
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  previewMode: 'material',
  previewOnly: false,
  source: 'material',
});

const emit = defineEmits<{
  (e: 'update:checked', value: boolean): void;
}>();

const previewOpen = ref(false);

const [PreviewModal, previewModalApi] = useVbenModal({
  modal: true,
  class: '!w-[calc(100vw-24px)] lg:!w-[min(1280px,92vw)]',
  contentClass: '!overflow-auto',
  showCancelButton: false,
  showConfirmButton: false,
  fullscreenButton: false,
  onOpenChange(open: boolean) {
    previewOpen.value = open;
    if (open) {
      window.addEventListener('keydown', onPreviewKeydown);
    } else {
      window.removeEventListener('keydown', onPreviewKeydown);
    }
  },
});

const loading = ref(false);
const mediaUrl = ref<null | string>(null);
const fileType = ref<string | undefined>(undefined);
const currentItem = ref<any>(null);
const lastPreviewTime = ref(0);
const CACHE_DURATION = 30_000;

const previewIndex = computed(() => {
  const id = currentItem.value?.id;
  if (id == null) return -1;
  return props.items.findIndex((entry) => entry.id === id);
});

const prevItem = computed(() => {
  const index = previewIndex.value;
  return index > 0 ? props.items[index - 1] : undefined;
});

const nextItem = computed(() => {
  const index = previewIndex.value;
  if (index < 0 || index >= props.items.length - 1) return undefined;
  return props.items[index + 1];
});

const showGalleryNav = computed(() => props.items.length > 1);

const stripItems = computed(() => {
  const index = previewIndex.value;
  if (index < 0) return [];
  return [
    { key: 'prev', item: props.items[index - 1] },
    { key: 'current', item: props.items[index] },
    { key: 'next', item: props.items[index + 1] },
    { key: 'next2', item: props.items[index + 2] },
  ];
});

const tagCount = computed(
  () => props.item.tags_new?.length || props.item.tags_len || 0,
);

// 标签数也撑起底栏：公共素材没有平台/剪辑/消耗，否则整条底栏不渲染，标签数跟着看不见
const hasBottomBar = computed(
  () =>
    !!(
      props.item.game_platform ||
      props.item.creative_editor ||
      props.item.total_spent != null
    ) ||
    (props.previewMode !== 'adcreative' && tagCount.value > 0),
);

const tagTooltipContent = computed(() => {
  const titles: string[] = props.item.tags_titles || props.item.tags_new || [];
  return titles.length > 0 ? titles.join(', ') : `${tagCount.value} 个标签`;
});

function onPreviewKeydown(event: KeyboardEvent) {
  if (!previewOpen.value) return;
  if (event.key === 'ArrowLeft') {
    event.preventDefault();
    goPrev();
  } else if (event.key === 'ArrowRight') {
    event.preventDefault();
    goNext();
  }
}

function goPrev() {
  if (prevItem.value) void openPreview(prevItem.value);
}

function goNext() {
  if (nextItem.value) void openPreview(nextItem.value);
}

async function openPreview(item: any) {
  if (!item) return;
  const isSameId =
    item.id && currentItem.value?.id && item.id === currentItem.value.id;
  if (isSameId && Date.now() - lastPreviewTime.value < CACHE_DURATION) {
    previewModalApi.open();
    return;
  }

  previewModalApi.open();
  loading.value = true;

  try {
    let targetItem = item;
    if (props.previewMode === 'material') {
      const detailRes = await (props.source === 'common'
        ? getCommonMaterialsByIdsApi([item.id])
        : getMaterialsByIds({
            ids: item.id ? [item.id] : undefined,
            basenames: [
              item.ad_name ||
                item.unique_name ||
                item.basename ||
                item.filename,
            ],
            fields: ['tags_tree', 'filename', 'updated_at'],
          }));
      const detailItems = detailRes.data?.items || detailRes.items || [];
      if (detailItems.length === 0) {
        message.error('获取素材详情失败');
        if (!currentItem.value) previewModalApi.close();
        return;
      }
      targetItem = { ...item, ...detailItems[0] };
    }
    // 公共素材的详情接口直接带 url，materials 那条得再换一次预签名
    mediaUrl.value =
      targetItem.url ?? (await getMaterialUrlApi(targetItem.filename)).url;
    fileType.value = targetItem.filetype || item.filetype;
    currentItem.value = targetItem;
    lastPreviewTime.value = Date.now();
  } catch {
    message.error('加载预览失败');
    if (!currentItem.value) previewModalApi.close();
  } finally {
    loading.value = false;
  }
}

onUnmounted(() => {
  window.removeEventListener('keydown', onPreviewKeydown);
});

defineExpose({ openPreview });
</script>

<template>
  <div class="contents">
    <Card
      v-if="!previewOnly"
      :data-card-id="item.id"
      hoverable
      class="relative transition-all duration-200"
      :body-style="{ padding: '0' }"
    >
      <div class="flex flex-col">
        <div class="flex items-center justify-between border-b p-1">
          <Checkbox
            :checked="checked"
            @change="(e: any) => emit('update:checked', e.target.checked)"
          />
          <div class="mx-1 flex min-w-0 flex-1 items-center">
            <div
              class="flex-1 truncate text-xs font-medium"
              :title="item.filename"
            >
              {{ item.basename || item.filename }}
            </div>
            <div class="flex flex-shrink-0 items-center text-xs">
              {{
                item.created_at
                  ? new Date(item.created_at).toLocaleDateString('zh-CN', {
                      month: '2-digit',
                      day: '2-digit',
                    })
                  : ''
              }}
              {{ item.operator || item.user || '-' }}
            </div>
          </div>
          <div class="flex h-5 w-5 items-center justify-center">
            <span
              v-if="item.filetype === 'image'"
              class="icon-[ant-design--picture-outlined] text-base"
              :title="item.filetype"
            ></span>
            <span
              v-else-if="item.filetype === 'video'"
              class="icon-[ant-design--video-camera-outlined] text-base"
              :title="item.filetype"
            ></span>
          </div>
        </div>

        <div
          role="button"
          tabindex="0"
          :aria-label="`预览素材 ${item.basename || item.filename || ''}`"
          class="material-card-thumb"
          @click="openPreview(item)"
          @keydown.enter.prevent="openPreview(item)"
          @keydown.space.prevent="openPreview(item)"
        >
          <img
            :src="`data:image/png;base64,${item.img}`"
            :alt="item.basename || item.filename || '素材缩略图'"
            class="material-card-thumb__img"
          />
        </div>

        <div :class="['p-2', !hasBottomBar ? 'pb-0' : '']">
          <div
            v-if="hasBottomBar"
            class="relative flex items-center justify-between"
          >
            <div class="flex gap-2 text-xs text-gray-600">
              <span v-if="item.game_platform" :title="item.game_platform">
                {{ item.game_platform }}
              </span>
              <span v-if="item.creative_editor" :title="item.creative_editor">
                {{ item.creative_editor }}
              </span>
            </div>
            <span
              v-if="item.total_spent != null"
              class="text-center text-xs font-medium text-green-600"
              title="总消费"
            >
              {{ item.total_spent }}
            </span>
            <template v-if="previewMode !== 'adcreative'">
              <Tooltip v-if="tagCount > 0" :title="tagTooltipContent">
                <div
                  class="cursor-default rounded bg-black/60 px-1.5 py-0.5 text-xs text-white"
                >
                  标签 {{ tagCount }}
                </div>
              </Tooltip>
              <div v-else class="w-[38px]">&nbsp;</div>
            </template>
          </div>
        </div>
      </div>
    </Card>

    <PreviewModal>
      <template #title>
        <div class="flex items-center">
          <span class="flex-1 overflow-hidden text-ellipsis whitespace-nowrap">
            预览 -
            {{
              currentItem?.basename ||
              currentItem?.filename ||
              currentItem?.ad_name ||
              ''
            }}
          </span>
        </div>
      </template>

      <div
        v-if="loading && !currentItem"
        class="flex items-center justify-center"
        style="min-height: 400px"
      >
        <div class="text-center">
          <div
            class="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-gray-300 border-t-blue-500"
          ></div>
          <div class="text-gray-600">加载预览中...</div>
        </div>
      </div>

      <div
        v-else
        class="flex max-h-[75dvh] flex-col gap-4 overflow-auto lg:max-h-[65vh] lg:flex-row lg:gap-4"
      >
        <div class="material-preview-stage">
          <button
            v-if="showGalleryNav"
            type="button"
            class="material-preview-nav material-preview-nav--prev"
            :disabled="!prevItem"
            aria-label="上一张"
            @click.stop="goPrev"
          >
            <span class="icon-[lucide--chevron-left] text-2xl"></span>
          </button>
          <Image
            v-if="fileType === 'image' && mediaUrl"
            :src="mediaUrl"
            :preview="false"
            style="max-width: 100%; max-height: calc(65vh); object-fit: contain"
          />
          <video
            v-if="fileType === 'video' && mediaUrl"
            :src="mediaUrl"
            controls
            style="max-width: 100%; max-height: calc(65vh); object-fit: contain"
          ></video>
          <button
            v-if="showGalleryNav"
            type="button"
            class="material-preview-nav material-preview-nav--next"
            :disabled="!nextItem"
            aria-label="下一张"
            @click.stop="goNext"
          >
            <span class="icon-[lucide--chevron-right] text-2xl"></span>
          </button>
          <div
            v-if="loading"
            class="absolute inset-0 flex items-center justify-center bg-white/50"
          >
            <div
              class="h-10 w-10 animate-spin rounded-full border-4 border-gray-300 border-t-blue-500"
            ></div>
          </div>
        </div>

        <div class="flex w-full flex-shrink-0 flex-col overflow-hidden lg:w-80">
          <Card
            title="素材信息"
            class="flex flex-1 flex-col overflow-hidden"
            :body-style="{
              flex: 1,
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }"
          >
            <div class="flex flex-1 flex-col space-y-3 overflow-y-auto">
              <div class="flex-shrink-0">
                <div class="mb-2 text-sm font-medium">基本信息</div>
                <div class="space-y-1 text-sm">
                  <div class="flex justify-between">
                    <span>文件名:</span>
                    <span
                      class="max-w-[180px] truncate text-right"
                      :title="currentItem?.filename"
                    >
                      {{ currentItem?.filename || '-' }}
                    </span>
                  </div>
                  <div class="flex justify-between">
                    <span>原始文件名:</span>
                    <span
                      class="max-w-[180px] truncate text-right"
                      :title="currentItem?.origin_filename"
                    >
                      {{ currentItem?.origin_filename || '-' }}
                    </span>
                  </div>
                  <div class="flex justify-between">
                    <span>文件类型:</span>
                    <span>{{ currentItem?.filetype || '-' }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span>创建时间:</span>
                    <span>{{
                      currentItem?.created_at
                        ? currentItem?.created_at.slice(0, 19).replace('T', ' ')
                        : '-'
                    }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span>投手:</span>
                    <span>{{
                      currentItem?.operator || currentItem?.user || '-'
                    }}</span>
                  </div>
                  <template v-if="previewMode === 'material'">
                    <div class="flex justify-between">
                      <span>创意策划:</span>
                      <span>{{ currentItem?.creative_planner || '-' }}</span>
                    </div>
                    <div class="flex justify-between">
                      <span>国家:</span>
                      <span>{{ currentItem?.country || '-' }}</span>
                    </div>
                    <div class="flex justify-between">
                      <span>平台:</span>
                      <span>{{ currentItem?.game_platform || '-' }}</span>
                    </div>
                    <div class="flex justify-between">
                      <span>剪辑:</span>
                      <span>{{ currentItem?.creative_editor || '-' }}</span>
                    </div>
                  </template>
                </div>
              </div>

              <div
                v-if="previewMode === 'material'"
                class="flex flex-1 flex-col overflow-hidden"
              >
                <div class="mb-2 flex-shrink-0">
                  标签 ({{ currentItem?.tags_new?.length || 0 }})
                </div>
                <div
                  class="flex-1 overflow-y-auto rounded border border-gray-200 p-2"
                >
                  <Tree
                    v-if="
                      currentItem?.tags_tree && currentItem.tags_tree.length > 0
                    "
                    :tree-data="currentItem.tags_tree"
                    :show-line="true"
                    :show-icon="false"
                    :selectable="false"
                    default-expand-all
                  >
                    <template #title="{ title, key }">
                      <div class="flex items-center">
                        <span
                          class="bg-primary/10 text-primary mr-1 inline-flex h-5 w-5 items-center justify-center rounded text-xs font-medium"
                        >
                          {{ key.split('-').length }}
                        </span>
                        <span>{{ title }}</span>
                      </div>
                    </template>
                  </Tree>
                  <div v-else class="text-sm text-gray-400">无标签</div>
                </div>
              </div>
            </div>
          </Card>
        </div>

        <div
          v-if="showGalleryNav && stripItems.length > 0"
          class="material-preview-strip"
        >
          <button
            v-for="row in stripItems"
            :key="row.key"
            type="button"
            class="material-preview-strip__item"
            :class="{
              'is-current': row.key === 'current',
              'is-empty': !row.item,
            }"
            :disabled="!row.item || row.key === 'current'"
            :aria-label="
              row.item
                ? `预览 ${row.item.basename || row.item.filename || ''}`
                : '无素材'
            "
            @click="row.item && row.key !== 'current' && openPreview(row.item)"
          >
            <img
              v-if="row.item?.img"
              :src="`data:image/png;base64,${row.item.img}`"
              :alt="row.item.basename || row.item.filename || '缩略图'"
            />
          </button>
        </div>
      </div>
    </PreviewModal>
  </div>
</template>

<style scoped>
.material-card-thumb {
  flex: none;
  width: 100%;
  line-height: 0;
  cursor: pointer;
  background: #f3f4f6;
}

.material-card-thumb__img {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
}

.material-preview-stage {
  position: relative;
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  min-width: 0;
  overflow: hidden;
  background: #f5f5f5;
  border-radius: 8px;
}

.material-preview-nav {
  position: absolute;
  top: 50%;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  color: #fff;
  cursor: pointer;
  background: rgb(0 0 0 / 45%);
  border: 0;
  border-radius: 999px;
  transform: translateY(-50%);
}

.material-preview-nav:not(:disabled):hover {
  background: rgb(0 0 0 / 65%);
}

.material-preview-nav:disabled {
  cursor: default;
  opacity: 0.25;
}

.material-preview-nav--prev {
  left: 12px;
}

.material-preview-nav--next {
  right: 12px;
}

.material-preview-strip {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  gap: 8px;
  width: 92px;
}

.material-preview-strip__item {
  display: block;
  width: 92px;
  padding: 0;
  overflow: hidden;
  line-height: 0;
  cursor: pointer;
  background: #f3f4f6;
  border: 2px solid transparent;
  border-radius: 6px;
}

.material-preview-strip__item.is-current {
  cursor: default;
  border-color: #1677ff;
}

.material-preview-strip__item.is-empty {
  min-height: 92px;
  cursor: default;
  background: #f3f4f6;
}

.material-preview-strip__item img {
  display: block;
  width: 100%;
  height: auto;
}

@media (max-width: 1023px) {
  .material-preview-strip {
    flex-direction: row;
    width: 100%;
    overflow-x: auto;
  }

  .material-preview-strip__item,
  .material-preview-strip__item.is-empty {
    width: 72px;
    min-width: 72px;
  }
}
</style>
