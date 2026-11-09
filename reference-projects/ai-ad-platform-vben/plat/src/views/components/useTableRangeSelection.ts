import type { Ref } from 'vue';

import { ref } from 'vue';

export interface TableCellPosition {
  columnIndex: number;
  rowIndex: number;
}

export interface TableRangeSelection {
  anchor: TableCellPosition;
  focus: TableCellPosition;
}

export interface TableSelectionBounds {
  columnEnd: number;
  columnStart: number;
  rowEnd: number;
  rowStart: number;
}

/** 描述一列如何从业务行转换为复制到剪贴板的展示文本。 */
export interface TableCopyColumn<Row> {
  getText: (row: Row) => string;
  key: string;
}

export function getSelectionBounds(
  selection: TableRangeSelection,
): TableSelectionBounds {
  return {
    columnEnd: Math.max(
      selection.anchor.columnIndex,
      selection.focus.columnIndex,
    ),
    columnStart: Math.min(
      selection.anchor.columnIndex,
      selection.focus.columnIndex,
    ),
    rowEnd: Math.max(selection.anchor.rowIndex, selection.focus.rowIndex),
    rowStart: Math.min(selection.anchor.rowIndex, selection.focus.rowIndex),
  };
}

export function isCellInSelection(
  selection: TableRangeSelection,
  rowIndex: number,
  columnIndex: number,
) {
  const bounds = getSelectionBounds(selection);
  return (
    rowIndex >= bounds.rowStart &&
    rowIndex <= bounds.rowEnd &&
    columnIndex >= bounds.columnStart &&
    columnIndex <= bounds.columnEnd
  );
}

function normalizeCellText(value: string) {
  return value.replaceAll(/[\t\r\n]+/g, ' ');
}

/** 将矩形选区序列化为 Excel 可识别的制表符分隔文本。 */
export function serializeTableRange<Row>(
  rows: Row[],
  columns: TableCopyColumn<Row>[],
  selection: TableRangeSelection,
) {
  const bounds = getSelectionBounds(selection);
  const selectedRows = rows.slice(bounds.rowStart, bounds.rowEnd + 1);
  const selectedColumns = columns.slice(
    bounds.columnStart,
    bounds.columnEnd + 1,
  );

  return selectedRows
    .map((row) =>
      selectedColumns
        .map((column) => normalizeCellText(column.getText(row)))
        .join('\t'),
    )
    .join('\r\n');
}

export interface UseTableRangeSelectionOptions<Row> {
  columns: Ref<TableCopyColumn<Row>[]>;
  rows: Ref<Row[]>;
}

/**
 * 管理表格矩形选区、键盘移动与剪贴板复制，不绑定具体表格组件。
 *
 * @remarks 行和列必须与页面当前可见顺序一致，避免复制隐藏列或其他分页数据。
 */
export function useTableRangeSelection<Row>(
  options: UseTableRangeSelectionOptions<Row>,
) {
  const isSelecting = ref(false);
  const selection = ref<TableRangeSelection>();

  function beginSelection(rowIndex: number, columnIndex: number) {
    selection.value = {
      anchor: { columnIndex, rowIndex },
      focus: { columnIndex, rowIndex },
    };
    isSelecting.value = true;
  }

  function extendSelection(rowIndex: number, columnIndex: number) {
    if (!selection.value || !isSelecting.value) return;
    selection.value = {
      ...selection.value,
      focus: { columnIndex, rowIndex },
    };
  }

  function endSelection() {
    isSelecting.value = false;
  }

  function clearSelection() {
    isSelecting.value = false;
    selection.value = undefined;
  }

  function isCellSelected(rowIndex: number, columnIndex: number) {
    return selection.value
      ? isCellInSelection(selection.value, rowIndex, columnIndex)
      : false;
  }

  function getCopiedText() {
    return selection.value
      ? serializeTableRange(
          options.rows.value,
          options.columns.value,
          selection.value,
        )
      : '';
  }

  function copySelection(event: ClipboardEvent) {
    const text = getCopiedText();
    if (!text || !event.clipboardData) return false;

    event.clipboardData.setData('text/plain', text);
    event.preventDefault();
    return true;
  }

  function moveSelection(
    rowOffset: number,
    columnOffset: number,
    extend = false,
  ) {
    const maxRowIndex = options.rows.value.length - 1;
    const maxColumnIndex = options.columns.value.length - 1;
    if (maxRowIndex < 0 || maxColumnIndex < 0) return false;

    const currentFocus = selection.value?.focus ?? {
      columnIndex: 0,
      rowIndex: 0,
    };
    const nextFocus = {
      columnIndex: Math.min(
        Math.max(currentFocus.columnIndex + columnOffset, 0),
        maxColumnIndex,
      ),
      rowIndex: Math.min(
        Math.max(currentFocus.rowIndex + rowOffset, 0),
        maxRowIndex,
      ),
    };

    selection.value = extend
      ? {
          anchor: selection.value?.anchor ?? { columnIndex: 0, rowIndex: 0 },
          focus: nextFocus,
        }
      : { anchor: nextFocus, focus: nextFocus };
    isSelecting.value = false;
    return true;
  }

  return {
    beginSelection,
    clearSelection,
    copySelection,
    endSelection,
    extendSelection,
    getCopiedText,
    isCellSelected,
    isSelecting,
    moveSelection,
    selection,
  };
}
