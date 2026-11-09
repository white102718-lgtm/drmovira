<script lang="ts" setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue';

import {
  Button,
  message,
  Modal,
  Pagination,
  Select,
  Switch,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { addAdCreativeMaterialApi, listAdCreativesApi } from '#/api';
import {
  AD_CREATIVE_ACCEPT,
  AD_CREATIVE_ALLOWED_EXTS,
  validateFileType,
} from '#/utils/upload';

import DateRangePicker from '../../components/DateRangePicker.vue';
import MaterialCard from '../../components/MaterialCard.vue';

interface Props {
  open: boolean;
  selectedIds?: string[];
}

interface Emits {
  (e: 'update:open', value: boolean): void;
  (e: 'confirm', materials: any[]): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const modalOpen = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value),
});

const isBrowseMode = ref(false);

const searchFormValues = ref<Record<string, any>>({
  operator: undefined,
  filetype: undefined,
  created_at_range: [
    dayjs(dayjs.tz().subtract(30, 'days').format('YYYY-MM-DD')).valueOf(),
    dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
  ] as [number, number],
});

const cardMaterials = ref<any[]>([]);
const cardPage = ref(1);
const cardPageSize = ref(24);
const cardTotal = ref(0);
const cardLoading = ref(false);

const currentPageSelectedIds = ref<Set<string>>(new Set());
const selectedItems = ref<Map<string, any>>(new Map());

const isSelecting = ref(false);
const selectionBox = ref({ startX: 0, startY: 0, endX: 0, endY: 0 });
const gridContainer = ref<HTMLElement>();
const selectionStartSelectedIds = ref<Set<string>>(new Set());

/** 上传中状态 */
const uploading = ref(false);
const fileInputRef = ref<HTMLInputElement>();

async function fetchCardMaterials() {
  cardLoading.value = true;
  try {
    const params: Record<string, any> = {
      page: cardPage.value,
      pageSize: cardPageSize.value,
    };
    if (searchFormValues.value.operator) {
      params.user = searchFormValues.value.operator;
    }
    if (searchFormValues.value.filetype) {
      params.filetype = searchFormValues.value.filetype;
    }
    const range = searchFormValues.value.created_at_range;
    if (range && Array.isArray(range) && range.length === 2) {
      params.start_time = dayjs(range[0]).format('YYYY-MM-DD HH');
      params.end_time = dayjs(range[1]).format('YYYY-MM-DD HH');
    }
    const res = await listAdCreativesApi(params);
    cardMaterials.value = res.items || [];
    cardTotal.value = res.total || 0;
    await nextTick();
    refreshSelectionUI();
  } finally {
    cardLoading.value = false;
  }
}

function refreshSelectionUI() {
  const newSet = new Set<string>();
  cardMaterials.value.forEach((item) => {
    if (selectedItems.value.has(item.id)) newSet.add(item.id);
  });
  currentPageSelectedIds.value = newSet;
}

function handleCardSearch() {
  cardPage.value = 1;
  fetchCardMaterials();
}

function resetSearchForm() {
  searchFormValues.value = {
    operator: undefined,
    filetype: undefined,
    created_at_range: [
      dayjs(dayjs.tz().subtract(30, 'days').format('YYYY-MM-DD')).valueOf(),
      dayjs(dayjs.tz().format('YYYY-MM-DD')).endOf('day').valueOf(),
    ],
  };
  cardPage.value = 1;
  fetchCardMaterials();
}

function handleCardPageChange(p: number, size: number) {
  cardPage.value = p;
  cardPageSize.value = size;
  fetchCardMaterials();
}

function toggleCardSelect(item: any) {
  const id = item.id;
  if (selectedItems.value.has(id)) {
    selectedItems.value.delete(id);
    const newSet = new Set(currentPageSelectedIds.value);
    newSet.delete(id);
    currentPageSelectedIds.value = newSet;
  } else {
    selectedItems.value.set(id, item);
    const newSet = new Set(currentPageSelectedIds.value);
    newSet.add(id);
    currentPageSelectedIds.value = newSet;
  }
}

function selectAllPage() {
  cardMaterials.value.forEach((item) => {
    selectedItems.value.set(item.id, item);
  });
  currentPageSelectedIds.value = new Set(cardMaterials.value.map((m) => m.id));
}

function invertSelection() {
  const newSet = new Set<string>();
  cardMaterials.value.forEach((item) => {
    if (!currentPageSelectedIds.value.has(item.id)) {
      selectedItems.value.set(item.id, item);
      newSet.add(item.id);
    } else {
      selectedItems.value.delete(item.id);
    }
  });
  currentPageSelectedIds.value = newSet;
}

function clearSelection() {
  selectedItems.value.clear();
  currentPageSelectedIds.value = new Set();
}

function getSelectionCount() {
  return selectedItems.value.size;
}

function startSelection(event: MouseEvent) {
  if (isBrowseMode.value) return;
  const target = event.target as HTMLElement;
  const isInteractive =
    target.tagName === 'INPUT' ||
    target.tagName === 'BUTTON' ||
    target.closest('input') ||
    target.closest('button') ||
    target.closest('.ant-checkbox');
  if (isInteractive) return;
  if (!gridContainer.value) return;
  isSelecting.value = true;
  selectionStartSelectedIds.value = new Set(currentPageSelectedIds.value);
  const container = gridContainer.value;
  const rect = container.getBoundingClientRect();
  selectionBox.value.startX = event.clientX - rect.left + container.scrollLeft;
  selectionBox.value.startY = event.clientY - rect.top + container.scrollTop;
  selectionBox.value.endX = selectionBox.value.startX;
  selectionBox.value.endY = selectionBox.value.startY;
  document.addEventListener('mousemove', updateSelection);
  document.addEventListener('mouseup', endSelection);
  event.preventDefault();
}

function updateSelection(event: MouseEvent) {
  if (!isSelecting.value || !gridContainer.value) return;
  const container = gridContainer.value;
  const rect = container.getBoundingClientRect();
  selectionBox.value.endX = event.clientX - rect.left + container.scrollLeft;
  selectionBox.value.endY = event.clientY - rect.top + container.scrollTop;
  updateSelectedCards();
}

function updateSelectedCards() {
  const container = gridContainer.value;
  if (!container) return;

  const cards = container.querySelectorAll<HTMLElement>('[data-card-id]');
  const newSet = new Set(selectionStartSelectedIds.value);

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
    if (isIntersecting) {
      if (selectionStartSelectedIds.value.has(cardId)) {
        newSet.delete(cardId);
        selectedItems.value.delete(cardId);
      } else {
        newSet.add(cardId);
        const item = cardMaterials.value.find((m) => m.id === cardId);
        if (item) selectedItems.value.set(cardId, item);
      }
    }
  });
  currentPageSelectedIds.value = newSet;
}

function endSelection() {
  isSelecting.value = false;
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
}

watch(
  () => modalOpen.value,
  async (isOpen) => {
    if (isOpen && cardMaterials.value.length === 0) {
      await fetchCardMaterials();
    }
    if (!isOpen) {
      isBrowseMode.value = false;
    }
  },
);

function handleDragOver(event: DragEvent) {
  event.preventDefault();
}

async function handleDrop(event: DragEvent) {
  event.preventDefault();
  const files = Array.from(event.dataTransfer?.files || []);
  if (files.length > 0) await uploadFiles(files);
}

function handleFileInputChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  if (files.length > 0) uploadFiles(files);
  input.value = '';
}

async function uploadFiles(files: File[]) {
  const validFiles = files.filter((f) =>
    validateFileType(f, AD_CREATIVE_ALLOWED_EXTS, message.error),
  );
  if (validFiles.length === 0) return;
  uploading.value = true;
  let successCount = 0;
  let failCount = 0;
  try {
    for (const file of validFiles) {
      try {
        const formData = new FormData();
        formData.append('file', file);
        await addAdCreativeMaterialApi(formData);
        successCount++;
      } catch (err: any) {
        failCount++;
        message.error(`${file.name} 上传失败：${err?.message || '未知错误'}`);
      }
    }
    if (successCount > 0) {
      message.success(`成功上传 ${successCount} 个文件`);
      cardPage.value = 1;
      await fetchCardMaterials();
    }
    if (failCount > 0 && successCount === 0) {
    }
  } finally {
    uploading.value = false;
  }
}

function handleConfirm() {
  const result = [...selectedItems.value.values()].map((item) => ({ ...item }));
  if (result.length === 0) {
    message.warning('请至少选择一个素材');
    return;
  }
  emit('confirm', result);
  modalOpen.value = false;
}

function handleCancel() {
  modalOpen.value = false;
}

watch(
  () => props.selectedIds,
  (newIds) => {
    if (!newIds) return;
    const idSet = new Set(newIds);
    selectedItems.value.forEach((_, id) => {
      if (!idSet.has(id)) {
        selectedItems.value.delete(id);
      }
    });
    refreshSelectionUI();
  },
  { deep: true },
);

onUnmounted(() => {
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
});
</script>

<template>
  <div>
    <Modal
      v-model:open="modalOpen"
      title="临时上传广告"
      width="1500px"
      centered
      class="ad-creative-selection-modal"
      :footer="null"
      @cancel="handleCancel"
    >
      <div class="ux-modal-workspace flex flex-col">
        <div class="mb-2 flex flex-shrink-0 gap-10">
          <div class="flex-shrink-0 rounded border bg-white p-3">
            <div class="flex flex-wrap items-end gap-4 text-xs">
              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">文件类型</span>
                <Select
                  :value="searchFormValues.filetype"
                  :options="[
                    { label: '图片', value: 'image' },
                    { label: '视频', value: 'video' },
                  ]"
                  placeholder="请选择"
                  allow-clear
                  style="width: 120px"
                  @change="(val) => (searchFormValues.filetype = val)"
                />
              </div>

              <div class="flex flex-col gap-1">
                <span class="text-sm font-medium text-gray-700">创建时间</span>
                <DateRangePicker
                  :value="searchFormValues.created_at_range"
                  type="datetimerange"
                  format="yyyy-MM-dd HH"
                  :timePickerFormat="'HH'"
                  width="290px"
                  :clearable="false"
                  :isDateDisabled="
                    (ts) => ts > dayjs.tz().add(1, 'day').endOf('day').valueOf()
                  "
                  @update:value="
                    (val) => (searchFormValues.created_at_range = val)
                  "
                />
              </div>

              <div class="flex items-end gap-2 pb-0.5">
                <Button type="primary" @click="handleCardSearch">搜索</Button>
                <Button @click="resetSearchForm">重置</Button>
              </div>
            </div>
          </div>

          <!-- 上传区域 -->
          <div
            class="relative flex flex-1 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-blue-300 bg-blue-50 transition-colors hover:border-blue-400 hover:bg-blue-100"
            @dragover="handleDragOver"
            @drop="handleDrop"
            @click="fileInputRef?.click()"
          >
            <div
              v-if="uploading"
              class="flex flex-col items-center text-blue-500"
            >
              <span
                class="icon-[ant-design--loading-outlined] animate-spin text-2xl"
              ></span>
              <div class="mt-1 text-sm font-medium">上传中...</div>
            </div>
            <div v-else class="flex flex-col items-center text-blue-500">
              <span
                class="icon-[ant-design--cloud-upload-outlined] text-2xl"
              ></span>
              <div class="mt-1 text-sm font-medium">拖拽或点击上传</div>
              <div class="mt-0.5 text-xs text-gray-400">
                支持图片（JPG/PNG/GIF 等）/ 视频（MP4/MOV/AVI 等），支持批量
              </div>
            </div>
          </div>

          <input
            ref="fileInputRef"
            type="file"
            multiple
            :accept="AD_CREATIVE_ACCEPT"
            class="hidden"
            @change="handleFileInputChange"
          />
        </div>

        <div
          class="mb-1 flex flex-shrink-0 items-center justify-end gap-2 px-1"
        >
          <Tooltip>
            <template #title>
              <div v-if="!isBrowseMode">
                选择模式：拖拽框选 | 勾选多选 | 再次框选可取消
              </div>
              <div v-else>浏览模式</div>
            </template>
            <Switch
              :checked="!isBrowseMode"
              checked-children="选择"
              un-checked-children="浏览"
              @change="
                (checked) => {
                  isBrowseMode = !checked;
                  isSelecting = false;
                }
              "
            />
          </Tooltip>
          <Button.Group>
            <Button :disabled="cardLoading" @click="selectAllPage">
              全选
            </Button>
            <Button :disabled="cardLoading" @click="invertSelection">
              反选
            </Button>
            <Button
              :disabled="getSelectionCount() === 0"
              @click="clearSelection"
            >
              清空 ({{ getSelectionCount() }})
            </Button>
          </Button.Group>
        </div>

        <!-- 卡片列表区域 -->
        <div class="flex flex-1 flex-col overflow-hidden">
          <div class="relative min-h-0 flex-1 overflow-hidden">
            <div
              v-if="cardLoading"
              class="absolute inset-0 z-20 flex items-center justify-center bg-white/60"
            >
              <div class="flex items-center space-x-2">
                <div
                  class="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-500"
                ></div>
                <span>加载中...</span>
              </div>
            </div>

            <div class="h-full overflow-y-auto">
              <div
                v-if="!cardLoading && cardMaterials.length === 0"
                class="flex h-full flex-col items-center justify-center py-16 text-gray-400"
              >
                <span
                  class="icon-[ant-design--inbox-outlined] mb-3 text-2xl"
                ></span>
                <span class="text-sm">暂无数据</span>
              </div>
              <div
                v-else
                ref="gridContainer"
                class="relative grid select-none grid-cols-6 gap-1 border-2 border-dashed border-blue-200 px-1"
                :class="{
                  'cursor-crosshair': !isBrowseMode,
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

                <MaterialCard
                  v-for="item in cardMaterials"
                  :key="item.id"
                  :item="item"
                  :items="cardMaterials"
                  :checked="currentPageSelectedIds.has(item.id)"
                  preview-mode="adcreative"
                  @update:checked="() => toggleCardSelect(item)"
                />
              </div>
            </div>
          </div>

          <div
            class="flex flex-shrink-0 items-center justify-between border-t pt-2"
          >
            <span class="text-sm text-gray-600">
              已选择
              <span class="font-semibold text-blue-600">{{
                getSelectionCount()
              }}</span>
              个素材
            </span>
            <Pagination
              :current="cardPage"
              :page-size="cardPageSize"
              :total="cardTotal"
              show-size-changer
              :page-size-options="['24', '48', '100']"
              @change="handleCardPageChange"
            />
          </div>
        </div>
      </div>

      <div class="mt-3 flex items-center justify-end gap-2">
        <Button @click="handleCancel">取消</Button>
        <Button type="primary" @click="handleConfirm">确认选择</Button>
      </div>
    </Modal>
  </div>
</template>
