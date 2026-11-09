<script setup lang="ts" generic="T extends object">
import { computed, useSlots } from 'vue';

import type { TableColumnType } from 'ant-design-vue';
import Table from 'ant-design-vue/es/table';

export interface AntDataTableColumn {
  align?: 'center' | 'left' | 'right';
  dataIndex?: string;
  key: string;
  title: string;
  width?: number | string;
}

interface Props {
  columns: AntDataTableColumn[];
  data: T[];
  emptyText?: string;
  expandedRowKeys?: Array<number | string>;
  loading?: boolean;
  paginate?: boolean;
  pageSize?: number;
  rowKey: keyof T | string;
  tableHeight?: number;
}

const props = withDefaults(defineProps<Props>(), {
  emptyText: '暂无数据',
  loading: false,
  paginate: true,
  pageSize: 20,
});

const slots = useSlots();

const tableColumns = computed<TableColumnType<T>[]>(() =>
  props.columns.map((column) => ({
    align: column.align,
    dataIndex: column.dataIndex ?? column.key,
    key: column.key,
    title: column.title,
    width: column.width,
  })),
);

const pagination = computed(() =>
  props.paginate
    ? {
        pageSize: props.pageSize,
        showSizeChanger: false,
        showTotal: (total: number) => `共 ${total} 条`,
      }
    : false,
);

const hasExpandedRows = computed(() => Boolean(slots['row-after']));
const hasCustomExpandColumn = computed(() => Boolean(slots['cell-expand']));
const tableScroll = computed(() =>
  props.tableHeight ? { y: Math.max(160, props.tableHeight - 40) } : undefined,
);
const tableStyle = computed(() =>
  props.tableHeight
    ? { '--adpulse-table-viewport-height': `${props.tableHeight}px` }
    : undefined,
);

function resolveRowKey(record: T) {
  return String((record as Record<string, unknown>)[String(props.rowKey)]);
}

function hasEmptyInternalTitle(column: TableColumnType<T>) {
  return (
    Array.isArray(column.title) &&
    column.title.length === 1 &&
    column.title[0] === ''
  );
}
</script>

<template>
  <Table
    :columns="tableColumns"
    :data-source="data"
    :expanded-row-keys="
      hasCustomExpandColumn ? expandedRowKeys?.map(String) : undefined
    "
    :loading="loading"
    :pagination="pagination"
    :row-key="resolveRowKey"
    :scroll="tableScroll"
    :show-expand-column="!hasCustomExpandColumn"
    :style="tableStyle"
  >
    <template #headerCell="{ column }">
      <template v-if="!hasEmptyInternalTitle(column)">
        <slot :name="`header-${String(column.key)}`" :column="column">
          {{ column.title }}
        </slot>
      </template>
    </template>
    <template #bodyCell="{ column, record, text }">
      <slot
        :name="`cell-${String(column.key)}`"
        :column="column"
        :record="record"
        :value="text ?? '-'"
      >
        {{ text ?? '-' }}
      </slot>
    </template>
    <template v-if="hasExpandedRows" #expandedRowRender="{ record }">
      <slot name="row-after" :columns="columns" :record="record" />
    </template>
    <template #emptyText>
      <slot name="empty">{{ emptyText }}</slot>
    </template>
    <template v-if="$slots.footer" #footer>
      <slot name="footer" :columns="columns" />
    </template>
  </Table>
</template>
