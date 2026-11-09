<script setup lang="ts">
import type { SelectablePixel } from '#/api';

import { computed, reactive, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Form,
  Input,
  Modal,
  Pagination,
  Table,
  Tag,
} from 'ant-design-vue';

import { assetFlowApi } from '#/api';

const props = defineProps<{
  disabled?: boolean;
  label?: string;
  modelValue?: string[];
  placeholder?: string;
  required?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string[]];
}>();

const open = ref(false);
const loading = ref(false);
const rows = ref<SelectablePixel[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 10;
const selectedPixels = ref(new Map<string, SelectablePixel>());
const filters = reactive({
  pixelName: '',
  pixelId: '',
  bmName: '',
  bmId: '',
  pixelTestCode: '',
  remark: '',
});

const columns = [
  { dataIndex: 'pixelName', key: 'pixelName', title: '像素名称', width: 180 },
  { dataIndex: 'pixelId', key: 'pixelId', title: '像素 ID', width: 180 },
  { dataIndex: 'bmName', key: 'bmName', title: 'BM 名称', width: 160 },
  { dataIndex: 'bmId', key: 'bmId', title: 'BMID', width: 150 },
  {
    dataIndex: 'pixelTestCode',
    key: 'pixelTestCode',
    title: '测试代码',
    width: 140,
  },
  { dataIndex: 'remark', key: 'remark', title: '备注', width: 180 },
];

const selectedIds = computed(() => [...selectedPixels.value.keys()]);
const selectedDisplayItems = computed(() => {
  return (props.modelValue ?? []).map((id) => {
    const normalizedId = String(id);
    const pixel = selectedPixels.value.get(normalizedId);
    const label = [...new Set([pixel?.pixelName, pixel?.pixelId])]
      .filter(Boolean)
      .join(' · ');
    return {
      id: normalizedId,
      label: label || normalizedId,
    };
  });
});

/** 文本筛选支持业务人员常用的换行、空格和中英文标点批量粘贴。 */
function splitFilterValues(value: string) {
  return value
    .split(/[\s,，;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildFilterValues() {
  const values: Record<string, string[]> = {};
  const mappings = [
    ['details.pixelName', filters.pixelName],
    ['details.pixelId', filters.pixelId],
    ['details.bmName', filters.bmName],
    ['details.bmId', filters.bmId],
    ['details.pixelTestCode', filters.pixelTestCode],
    ['note', filters.remark],
  ] as const;
  for (const [key, value] of mappings) {
    const items = splitFilterValues(value);
    if (items.length > 0) values[key] = items;
  }
  return values;
}

async function loadPixels() {
  loading.value = true;
  try {
    const result = await assetFlowApi.selectablePixels({
      filterValues: buildFilterValues(),
      page: page.value,
      pageSize,
    });
    rows.value = result.items;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}

async function hydrateSelectedPixels(ids: string[]) {
  if (ids.length === 0) return;
  const requestedIds = new Set(ids.map(String));
  const result = await assetFlowApi.selectablePixels({
    filterValues: { id: ids },
    page: 1,
    pageSize: Math.min(100, Math.max(ids.length, 10)),
  });
  const next = new Map(selectedPixels.value);
  result.items.forEach((item) => {
    if (requestedIds.has(item.id) && next.has(item.id)) {
      next.set(item.id, item);
    }
  });
  selectedPixels.value = next;
}

function resetSelectedPixels(ids: string[]) {
  selectedPixels.value = new Map(
    ids.map((id) => {
      const normalizedId = String(id);
      return [
        normalizedId,
        selectedPixels.value.get(normalizedId) ?? {
          bmId: '',
          bmName: '',
          id: normalizedId,
          pixelId: normalizedId,
          pixelName: '',
          pixelTestCode: '',
          remark: '',
        },
      ];
    }),
  );
}

async function handleOpen() {
  if (props.disabled) return;
  resetSelectedPixels(props.modelValue ?? []);
  open.value = true;
  page.value = 1;
  await Promise.all([
    hydrateSelectedPixels(props.modelValue ?? []),
    loadPixels(),
  ]);
}

function handleSearch() {
  page.value = 1;
  void loadPixels();
}

function handleReset() {
  Object.assign(filters, {
    bmId: '',
    bmName: '',
    pixelId: '',
    pixelName: '',
    pixelTestCode: '',
    remark: '',
  });
  handleSearch();
}

function handleSelectionChange(
  keys: Array<number | string>,
  selectedRows: SelectablePixel[],
) {
  const currentPageIds = new Set(rows.value.map((item) => item.id));
  const selectedKeySet = new Set(keys.map(String));
  const next = new Map(selectedPixels.value);
  currentPageIds.forEach((id) => {
    if (!selectedKeySet.has(id)) next.delete(id);
  });
  selectedRows.forEach((item) => next.set(item.id, item));
  selectedPixels.value = next;
}

function handleConfirm() {
  emit('update:modelValue', selectedIds.value);
  open.value = false;
}

function handleRemoveSelectedPixel(pixelId: string) {
  emit(
    'update:modelValue',
    (props.modelValue ?? []).filter((id) => String(id) !== pixelId),
  );
}

async function handleCancel() {
  resetSelectedPixels(props.modelValue ?? []);
  await hydrateSelectedPixels(props.modelValue ?? []);
}

function handlePageChange(nextPage: number) {
  page.value = nextPage;
  void loadPixels();
}

watch(
  () => props.modelValue,
  async (ids) => {
    resetSelectedPixels(ids ?? []);
    await hydrateSelectedPixels(ids ?? []);
  },
  { immediate: true },
);
</script>

<template>
  <div class="min-w-0">
    <div
      v-if="label || !disabled"
      class="mb-2 flex min-h-10 flex-wrap items-center justify-between gap-2"
    >
      <span v-if="label" class="text-foreground text-sm">
        <span v-if="required" class="text-destructive mr-1" aria-hidden="true"
          >*</span
        >{{ label }}
      </span>
      <div v-if="!disabled" class="ml-auto flex shrink-0 items-center gap-1">
        <Button @click="handleOpen">
          {{ modelValue?.length ? '继续选择' : '选择' }}
        </Button>
        <Button
          v-if="modelValue?.length"
          type="text"
          @click="emit('update:modelValue', [])"
        >
          清空
        </Button>
      </div>
    </div>
    <div
      class="border-input bg-background flex min-h-10 min-w-0 flex-wrap items-center gap-2 rounded-md border px-3 py-1.5"
      :class="disabled ? 'cursor-not-allowed opacity-50' : ''"
      @click.self="handleOpen"
    >
      <Button
        v-if="selectedDisplayItems.length === 0"
        class="text-muted-foreground !flex min-w-0 flex-1 !items-center !justify-start !px-0 !py-0 !leading-6"
        :disabled="disabled"
        type="text"
        @click="handleOpen"
      >
        {{ placeholder || '请选择像素' }}
      </Button>
      <template v-else>
        <Tag
          v-for="item in selectedDisplayItems"
          :key="item.id"
          class="!m-0 !inline-flex max-w-full items-center gap-1 !whitespace-normal !py-0.5 !pl-2 !pr-1"
        >
          <span class="break-all">{{ item.label }}</span>
          <button
            v-if="!disabled"
            :aria-label="`删除像素 ${item.label}`"
            class="text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-sm transition-colors focus-visible:outline-none focus-visible:ring-2"
            type="button"
            @click.stop="handleRemoveSelectedPixel(item.id)"
          >
            <IconifyIcon class="text-xs" icon="lucide:x" />
          </button>
        </Tag>
      </template>
    </div>
  </div>

  <Modal
    v-model:open="open"
    :body-style="{
      height: 'min(620px, calc(100vh - 180px))',
    }"
    cancel-text="取消"
    ok-text="确认选择"
    title="选择像素"
    width="1240px"
    wrap-class-name="pixel-asset-selector-modal"
    @cancel="handleCancel"
    @ok="handleConfirm"
  >
    <div class="flex h-full min-h-0 flex-col gap-4">
      <Form
        class="flex flex-wrap items-end gap-x-3 gap-y-2"
        component="div"
        layout="horizontal"
        :wrapper-col="{ flex: '1 1 0' }"
      >
        <Form.Item class="mb-0 w-full sm:w-[300px]" label="像素名称">
          <Input.TextArea
            v-model:value="filters.pixelName"
            :auto-size="{ minRows: 1, maxRows: 3 }"
            allow-clear
            placeholder="输入像素名称（可批量）"
          />
        </Form.Item>
        <Form.Item class="mb-0 w-full sm:w-[300px]" label="像素 ID">
          <Input.TextArea
            v-model:value="filters.pixelId"
            :auto-size="{ minRows: 1, maxRows: 3 }"
            allow-clear
            placeholder="输入像素 ID（可批量）"
          />
        </Form.Item>
        <Form.Item class="mb-0 w-full sm:w-[300px]" label="BM 名称">
          <Input
            v-model:value="filters.bmName"
            allow-clear
            placeholder="请输入 BM 名称"
          />
        </Form.Item>
        <Form.Item class="mb-0 w-full sm:w-[300px]" label="BMID">
          <Input
            v-model:value="filters.bmId"
            allow-clear
            placeholder="请输入 BMID"
          />
        </Form.Item>
        <Form.Item class="mb-0 w-full sm:w-[300px]" label="测试代码">
          <Input
            v-model:value="filters.pixelTestCode"
            allow-clear
            placeholder="请输入像素测试代码"
          />
        </Form.Item>
        <Form.Item class="mb-0 w-full sm:w-[300px]" label="备注">
          <Input
            v-model:value="filters.remark"
            allow-clear
            placeholder="请输入备注"
          />
        </Form.Item>

        <div class="flex shrink-0 items-center gap-2">
          <Button @click="handleReset">重置</Button>
          <Button type="primary" @click="handleSearch">查询</Button>
        </div>
      </Form>

      <Table
        class="pixel-selector-table min-h-[240px] flex-1"
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        :pagination="false"
        :row-key="(record: SelectablePixel) => record.id"
        :row-selection="{
          preserveSelectedRowKeys: true,
          selectedRowKeys: selectedIds,
          onChange: handleSelectionChange,
        }"
        :scroll="{ x: 990, y: '100%' }"
        size="middle"
      />

      <div class="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <span class="text-sm"
          >共 {{ total }} 个，已选择 {{ selectedIds.length }} 个</span
        >
        <Pagination
          :current="page"
          :page-size="pageSize"
          :show-size-changer="false"
          :total="total"
          @change="handlePageChange"
        />
      </div>
    </div>
  </Modal>
</template>

<style scoped>
@media (max-width: 1023px), (max-height: 760px) {
}
</style>
