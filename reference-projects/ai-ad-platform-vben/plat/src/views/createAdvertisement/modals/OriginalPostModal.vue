<script lang="ts" setup>
import type { FbPost } from '#/api/management/fb-resource';
import type { MaterialItem } from '../types';

import { computed, onUnmounted, ref, watch } from 'vue';

import {
  Button,
  Checkbox,
  message,
  Modal,
  Pagination,
  Switch,
  Tooltip,
} from 'ant-design-vue';

import { getPosts } from '#/api/management/fb-resource';

interface Props {
  open: boolean;
  pageIds: string[];
  selectedPostIds?: string[];
}

interface Emits {
  (e: 'update:open', value: boolean): void;
  (e: 'confirm', posts: MaterialItem[]): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const loading = ref(false);
const posts = ref<FbPost[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(24);
const selectedItems = ref<Map<string, FbPost>>(new Map());

const isPreviewMode = ref(false);
const isSelecting = ref(false);
const selectionBox = ref({ startX: 0, startY: 0, endX: 0, endY: 0 });
const gridContainer = ref<HTMLElement | null>(null);
const selectionStartSelected = ref<Set<string>>(new Set());

const selectionCount = computed(() => selectedItems.value.size);

async function fetchPosts() {
  loading.value = true;
  try {
    const res: any = await getPosts({
      page: page.value,
      page_size: pageSize.value,
      id: props.pageIds,
    });
    const data = res?.data || res;
    posts.value = data?.items || [];
    total.value = data?.total || 0;
  } catch {
    posts.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

const dataLoaded = ref(false);

const pendingSelectedIds = ref<Set<string>>(new Set());

function syncSelectedFromPending() {
  if (pendingSelectedIds.value.size === 0) return;
  const map = new Map(selectedItems.value);
  posts.value.forEach((p) => {
    if (pendingSelectedIds.value.has(p.post_id)) {
      map.set(p.post_id, p);
    }
  });
  selectedItems.value = map;
}

watch(
  () => props.open,
  async (val) => {
    if (val) {
      pendingSelectedIds.value = new Set(props.selectedPostIds || []);
      selectedItems.value = new Map();
      if (!dataLoaded.value) {
        page.value = 1;
        await fetchPosts();
        dataLoaded.value = true;
      } else {
        syncSelectedFromPending();
      }
    }
  },
);

watch(posts, () => {
  syncSelectedFromPending();
});

function toggleSelect(post: FbPost) {
  if (isPreviewMode.value) return;
  const map = new Map(selectedItems.value);
  if (map.has(post.post_id)) {
    map.delete(post.post_id);
  } else {
    map.set(post.post_id, post);
  }
  selectedItems.value = map;
}

function selectAllPage() {
  const map = new Map(selectedItems.value);
  posts.value.forEach((p) => map.set(p.post_id, p));
  selectedItems.value = map;
}

function invertSelection() {
  const map = new Map(selectedItems.value);
  posts.value.forEach((p) => {
    if (map.has(p.post_id)) {
      map.delete(p.post_id);
    } else {
      map.set(p.post_id, p);
    }
  });
  selectedItems.value = map;
}

function clearSelection() {
  selectedItems.value = new Map();
}

function handleCardClick(post: FbPost) {
  toggleSelect(post);
}

const startSelection = (event: MouseEvent) => {
  if (isPreviewMode.value) return;

  const target = event.target as HTMLElement;
  const isInteractiveElement =
    target.tagName === 'INPUT' ||
    target.tagName === 'BUTTON' ||
    target.closest('input') ||
    target.closest('button') ||
    target.closest('.ant-checkbox');

  if (isInteractiveElement) return;
  if (!gridContainer.value) return;

  isSelecting.value = true;
  selectionStartSelected.value = new Set<string>(selectedItems.value.keys());

  const rect = gridContainer.value.getBoundingClientRect();
  selectionBox.value.startX =
    event.clientX - rect.left + gridContainer.value.scrollLeft;
  selectionBox.value.startY =
    event.clientY - rect.top + gridContainer.value.scrollTop;
  selectionBox.value.endX = selectionBox.value.startX;
  selectionBox.value.endY = selectionBox.value.startY;

  document.addEventListener('mousemove', updateSelection);
  document.addEventListener('mouseup', endSelection);
  event.preventDefault();
};

const updateSelection = (event: MouseEvent) => {
  if (!isSelecting.value || !gridContainer.value) return;

  const rect = gridContainer.value.getBoundingClientRect();
  selectionBox.value.endX =
    event.clientX - rect.left + gridContainer.value.scrollLeft;
  selectionBox.value.endY =
    event.clientY - rect.top + gridContainer.value.scrollTop;

  updateSelectedCards();
};

const endSelection = () => {
  isSelecting.value = false;
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
};

const updateSelectedCards = () => {
  if (!gridContainer.value) return;

  const container = gridContainer.value;
  const cards = container.querySelectorAll<HTMLElement>('[data-card-id]');
  const newSelected = new Map<string, FbPost>(selectedItems.value);
  [...selectionStartSelected.value].forEach((id) => {
    const post =
      selectedItems.value.get(id) || posts.value.find((p) => p.post_id === id);
    if (post) newSelected.set(id, post);
  });

  const selectionRect = {
    left: Math.min(selectionBox.value.startX, selectionBox.value.endX),
    top: Math.min(selectionBox.value.startY, selectionBox.value.endY),
    right: Math.max(selectionBox.value.startX, selectionBox.value.endX),
    bottom: Math.max(selectionBox.value.startY, selectionBox.value.endY),
  };

  const minSelectionSize = 5;
  if (
    Math.abs(selectionBox.value.endX - selectionBox.value.startX) <
      minSelectionSize ||
    Math.abs(selectionBox.value.endY - selectionBox.value.startY) <
      minSelectionSize
  ) {
    return;
  }

  const containerRect = container.getBoundingClientRect();

  cards.forEach((card) => {
    const cardRect = card.getBoundingClientRect();
    const cardRelativeRect = {
      left: cardRect.left - containerRect.left + container.scrollLeft,
      top: cardRect.top - containerRect.top + container.scrollTop,
      right: cardRect.right - containerRect.left + container.scrollLeft,
      bottom: cardRect.bottom - containerRect.top + container.scrollTop,
    };

    const isIntersecting = !(
      cardRelativeRect.right < selectionRect.left ||
      cardRelativeRect.left > selectionRect.right ||
      cardRelativeRect.bottom < selectionRect.top ||
      cardRelativeRect.top > selectionRect.bottom
    );

    const cardId = card.dataset.cardId!;
    const post = posts.value.find((p) => p.post_id === cardId);
    if (!post) return;

    if (isIntersecting) {
      if (selectionStartSelected.value.has(cardId)) {
        newSelected.delete(cardId);
      } else {
        newSelected.set(cardId, post);
      }
    }
  });

  selectedItems.value = newSelected;
};

function handlePageChange(p: number) {
  page.value = p;
  fetchPosts();
}

function handleConfirm() {
  if (selectedItems.value.size === 0) {
    message.warning('请至少选择一条原帖');
    return;
  }
  const result: MaterialItem[] = [...selectedItems.value.values()].map(
    (post) => ({
      id: post.post_id,
      materialId: post.post_id,
      pageId: post.page_id,
      isOriginalPost: true,
      name: post.name || post.post_id,
      filename: post.name || post.post_id,
      unique_name: post.name || post.post_id,
      thumbnail: post.thumbnail,
      uploadTime: '',
    }),
  );
  emit('confirm', result);
}

function handleCancel() {
  emit('update:open', false);
}

onUnmounted(() => {
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
});
</script>

<template>
  <Modal
    :open="open"
    width="1200px"
    centered
    class="original-post-modal"
    :footer="null"
    @cancel="handleCancel"
  >
    <template #title>
      <div class="flex items-center gap-2">
        <span>原帖列表</span>
        <Button
          :loading="loading"
          class="leading-[24px]"
          @click="
            () => {
              page = 1;
              fetchPosts();
            }
          "
        >
          <span class="icon-[ant-design--reload-outlined]"></span>
        </Button>
      </div>
    </template>
    <div class="ux-modal-workspace flex flex-col">
      <div class="mb-2 flex flex-shrink-0 items-center justify-end gap-2">
        <Tooltip>
          <template #title>
            <div v-if="!isPreviewMode">
              选择模式：拖拽框选 | 勾选多选 | 再次框选可取消
            </div>
            <div v-else>预览模式</div>
          </template>
          <Switch
            :checked="!isPreviewMode"
            checked-children="选择"
            un-checked-children="预览"
            @change="
              (checked) => {
                isPreviewMode = !checked;
                isSelecting = false;
              }
            "
          />
        </Tooltip>
        <Button.Group>
          <Button :disabled="loading" @click="selectAllPage">全选</Button>
          <Button :disabled="loading" @click="invertSelection">反选</Button>
          <Button :disabled="selectionCount === 0" @click="clearSelection">
            清空 ({{ selectionCount }})
          </Button>
        </Button.Group>
      </div>

      <div class="relative min-h-0 flex-1 overflow-hidden">
        <div
          v-if="loading"
          class="absolute inset-0 z-20 flex items-center justify-center bg-white/60"
        >
          <div class="flex items-center space-x-2">
            <div
              class="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-500"
            ></div>
            <span>加载中...</span>
          </div>
        </div>

        <div
          v-if="!loading && posts.length === 0"
          class="flex h-full flex-col items-center justify-center py-16 text-gray-400"
        >
          <span class="icon-[ant-design--inbox-outlined] mb-3 text-2xl"></span>
          <span class="text-sm">暂无数据</span>
        </div>

        <div v-else class="h-full overflow-y-auto">
          <div
            ref="gridContainer"
            class="relative grid grid-cols-6 gap-2 p-1"
            :class="{
              'select-none': !isPreviewMode,
              'cursor-crosshair': isSelecting && !isPreviewMode,
              'border-2 border-dashed border-blue-200':
                !isPreviewMode && posts.length > 0,
            }"
            @mousedown="startSelection"
          >
            <div
              v-if="isSelecting"
              class="pointer-events-none absolute z-10 rounded-sm border-2 border-blue-500"
              :style="{
                left: `${Math.min(selectionBox.startX, selectionBox.endX)}px`,
                top: `${Math.min(selectionBox.startY, selectionBox.endY)}px`,
                width: `${Math.abs(selectionBox.endX - selectionBox.startX)}px`,
                height: `${Math.abs(selectionBox.endY - selectionBox.startY)}px`,
                boxShadow: '0 0 0 1px rgba(59, 130, 246, 0.5)',
              }"
            ></div>

            <div
              v-for="post in posts"
              :key="post.post_id"
              :data-card-id="post.post_id"
              class="group relative cursor-pointer rounded border border-gray-200 bg-white p-2 transition-all hover:border-blue-400"
              :class="{
                'ring-2 ring-blue-500': selectedItems.has(post.post_id),
              }"
              @click="handleCardClick(post)"
            >
              <div class="absolute left-1.5 top-1.5 z-10">
                <Checkbox
                  :checked="selectedItems.has(post.post_id)"
                  @click.stop="toggleSelect(post)"
                />
              </div>
              <div class="h-[128px] flex-shrink-0 overflow-hidden">
                <img
                  v-if="post.thumbnail"
                  alt="原帖缩略图"
                  :src="`data:image/jpeg;base64,${post.thumbnail}`"
                  class="h-full w-full cursor-pointer object-contain transition-transform hover:scale-105"
                />
                <span
                  v-else
                  class="icon-[ant-design--picture-outlined] text-2xl text-gray-400"
                ></span>
              </div>
              <div class="mt-1.5 truncate text-xs text-gray-800">
                id：{{ post.post_id }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        class="mt-3 flex flex-shrink-0 items-center justify-between border-t pt-3"
      >
        <span class="text-sm text-gray-600">
          已选
          <span class="font-semibold text-blue-600">{{ selectionCount }}</span>
          条原帖
        </span>
        <div class="flex items-center gap-4">
          <Pagination
            :current="page"
            :page-size="pageSize"
            :total="total"
            :show-size-changer="false"
            @change="handlePageChange"
          />
          <div class="flex gap-2">
            <Button @click="handleCancel">取消</Button>
            <Button type="primary" @click="handleConfirm">确认</Button>
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>
