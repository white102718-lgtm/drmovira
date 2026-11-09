<script setup lang="ts" generic="T extends Record<string, any>">
import { computed, ref, watch } from 'vue';

import { VbenButton as ShadcnButton } from '@vben/common-ui';
import { LoaderCircle } from 'lucide-vue-next';

export interface ShadcnDataTableColumn {
  align?: 'center' | 'left' | 'right';
  dataIndex?: string;
  key: string;
  title: string;
  width?: number | string;
}

interface Props {
  columns: ShadcnDataTableColumn[];
  data: T[];
  emptyText?: string;
  loading?: boolean;
  page?: number;
  paginate?: boolean;
  pageSize?: number;
  rowKey: keyof T | string;
  stickyPagination?: boolean;
  tableHeight?: number;
  total?: number;
}

const props = withDefaults(defineProps<Props>(), {
  emptyText: '暂无数据',
  loading: false,
  paginate: true,
  pageSize: 20,
});

const emit = defineEmits<{
  (event: 'update:page', page: number): void;
}>();

const currentPage = ref(1);
const serverPaging = computed(() => props.total != null);
const displayPage = computed(() =>
  serverPaging.value ? (props.page ?? 1) : currentPage.value,
);
const totalCount = computed(() => props.total ?? props.data.length);
const totalPages = computed(() =>
  Math.max(1, Math.ceil(totalCount.value / props.pageSize)),
);
const visibleRows = computed(() => {
  if (!props.paginate) return props.data;
  if (serverPaging.value) return props.data;
  const start = (currentPage.value - 1) * props.pageSize;
  return props.data.slice(start, start + props.pageSize);
});
const rangeStart = computed(() =>
  totalCount.value === 0 ? 0 : (displayPage.value - 1) * props.pageSize + 1,
);
const rangeEnd = computed(() =>
  Math.min(displayPage.value * props.pageSize, totalCount.value),
);

function goToPage(page: number) {
  if (serverPaging.value) {
    emit('update:page', page);
    return;
  }
  currentPage.value = page;
}

function cellValue(row: T, column: ShadcnDataTableColumn) {
  return row[column.dataIndex ?? column.key] ?? '-';
}

function columnStyle(column: ShadcnDataTableColumn) {
  if (!column.width) return undefined;
  return {
    width:
      typeof column.width === 'number' ? `${column.width}px` : column.width,
  };
}

watch(
  () => props.data,
  () => {
    if (!serverPaging.value) currentPage.value = 1;
  },
);

watch(totalPages, (total) => {
  if (currentPage.value > total) currentPage.value = total;
});
</script>

<template>
  <div
    class="bg-card flex min-h-0 w-full flex-col overflow-hidden rounded-xl border"
    :style="{
      height: tableHeight
        ? `${tableHeight}px`
        : 'var(--adpulse-table-viewport-height)',
    }"
  >
    <div class="min-h-0 flex-1 overflow-auto">
      <table class="w-full min-w-max caption-bottom text-sm">
        <thead class="bg-muted/80 sticky top-0 z-[2] [&_tr]:border-b">
          <tr class="hover:bg-muted/50 border-b transition-colors">
            <th
              v-for="column in columns"
              :key="column.key"
              :class="[
                'text-muted-foreground h-[var(--adpulse-table-header-height)] whitespace-nowrap px-[var(--adpulse-table-cell-padding-inline)] text-left align-middle font-medium',
                column.align === 'center' && 'text-center',
                column.align === 'right' && 'text-right',
              ]"
              :style="columnStyle(column)"
              scope="col"
            >
              <slot :name="`header-${column.key}`" :column="column">
                {{ column.title }}
              </slot>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td
              :colspan="columns.length"
              class="text-muted-foreground h-[var(--adpulse-table-body-min-height)] p-4 text-center text-sm"
            >
              <LoaderCircle
                aria-hidden="true"
                class="mr-2 inline-block size-4 animate-spin motion-reduce:animate-none"
              />
              正在加载
            </td>
          </tr>
          <template
            v-else
            v-for="row in visibleRows"
            :key="String(row[rowKey])"
          >
            <tr class="ux-table-row border-b transition-colors">
              <td
                v-for="column in columns"
                :key="column.key"
                :class="[
                  'text-foreground h-[var(--adpulse-table-row-height)] min-h-[var(--adpulse-table-row-height)] px-[var(--adpulse-table-cell-padding-inline)] py-1 align-middle leading-5',
                  column.align === 'center' && 'text-center',
                  column.align === 'right' && 'text-right',
                ]"
                :style="columnStyle(column)"
              >
                <slot
                  :name="`cell-${column.key}`"
                  :column="column"
                  :record="row"
                  :value="cellValue(row, column)"
                >
                  {{ cellValue(row, column) }}
                </slot>
              </td>
            </tr>
            <slot name="row-after" :columns="columns" :record="row" />
          </template>
          <tr v-if="!loading && visibleRows.length === 0">
            <td
              :colspan="columns.length"
              class="text-muted-foreground h-[var(--adpulse-table-body-min-height)] p-4 text-center text-sm"
            >
              <slot name="empty">{{ emptyText }}</slot>
            </td>
          </tr>
        </tbody>
        <tfoot v-if="$slots.footer" class="bg-muted/50 border-t">
          <slot name="footer" :columns="columns" />
        </tfoot>
      </table>
    </div>
    <footer
      v-if="paginate && totalCount > pageSize"
      :class="[
        'flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3',
        stickyPagination && 'bg-card shrink-0',
      ]"
    >
      <span class="text-muted-foreground text-xs">
        显示 {{ rangeStart }}–{{ rangeEnd }}，共 {{ totalCount }} 条
      </span>
      <div class="flex items-center gap-2">
        <ShadcnButton
          :disabled="displayPage === 1"
          size="sm"
          type="button"
          variant="outline"
          @click="goToPage(displayPage - 1)"
        >
          上一页
        </ShadcnButton>
        <span class="text-muted-foreground text-xs">
          {{ displayPage }} / {{ totalPages }}
        </span>
        <ShadcnButton
          :disabled="displayPage === totalPages"
          size="sm"
          type="button"
          variant="outline"
          @click="goToPage(displayPage + 1)"
        >
          下一页
        </ShadcnButton>
      </div>
    </footer>
  </div>
</template>
