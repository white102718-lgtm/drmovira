<script lang="ts" setup>
import type { VxeGridInstance, VxeGridProps } from 'vxe-table';
import type { Dayjs } from 'dayjs';

import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  DatePicker,
  Input,
  message,
  Modal,
  Select,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import { VxeGrid } from 'vxe-table';

import 'vxe-table/styles/all.scss';

import StableUserSelect from '../../components/StableUserSelect.vue';
import { getSharedOrganizationUsers } from '../../components/organization-options-cache';
import {
  downloadAssetWorkbook,
  formatAssetExportTimestamp,
} from './asset-export';

export type AssetBatchEditValue = string | string[];

export interface AssetBatchEditRequiredWhen {
  fieldKey: string;
  hint: string;
  incompatibleMessage?: string;
  values: string[];
}

export interface AssetBatchEditField {
  aliases?: string[];
  editable?: boolean;
  helpText?: string;
  key: string;
  label: string;
  multiple?: boolean;
  options?: Array<{ label: string; value: string }>;
  placeholder?: string;
  required?: boolean;
  requiredWhen?: AssetBatchEditRequiredWhen;
  sensitive?: boolean;
  type: 'date' | 'password' | 'select' | 'text' | 'textarea' | 'user';
}

export interface AssetSpreadsheetSourceRow {
  id?: string;
  isNew?: boolean;
  origin?: 'manual' | 'paste';
  values: Record<string, AssetBatchEditValue>;
}

export interface AssetSpreadsheetSubmissionRow
  extends AssetSpreadsheetSourceRow {
  changedFields: string[];
  rowNumber: number;
}

export interface AssetBatchEditSubmission {
  rows: AssetSpreadsheetSubmissionRow[];
}

interface EditorRow extends Record<string, unknown> {
  __cellRevisions: Record<string, number>;
  __dirtyFields: Set<string>;
  __errors: Record<string, string>;
  __id?: string;
  __isNew: boolean;
  __key: string;
  __original: Record<string, AssetBatchEditValue>;
  __origin: 'existing' | 'manual' | 'paste';
}

interface CellChange {
  after: AssetBatchEditValue;
  before: AssetBatchEditValue;
  fieldKey: string;
  rowIndex?: number;
  rowKey: string;
  rowSnapshot?: EditorRow;
}

interface PastePreviewRow {
  errors: string[];
  line: number;
  target?: EditorRow;
  values: Record<string, AssetBatchEditValue>;
}

interface SelectionPoint {
  fieldKey: string;
  rowKey: string;
}

interface SelectionBounds {
  endField: number;
  endRow: number;
  startField: number;
  startRow: number;
}

interface ActiveCell {
  fieldKey: string;
  rowKey: string;
}

interface FocusableEditor {
  focus?: () => void;
}

interface FilterCondition {
  dateRange?: [Dayjs, Dayjs];
  fieldKey: string;
  id: string;
  value: AssetBatchEditValue;
}

interface QuickPasteResult {
  error?: string;
  value: AssetBatchEditValue;
}

type OrganizationUser = Awaited<
  ReturnType<typeof getSharedOrganizationUsers>
>[number];

const DateRangePicker = DatePicker.RangePicker;

const props = withDefaults(
  defineProps<{
    allowCreate?: boolean;
    fields: AssetBatchEditField[];
    identifierKey: string;
    loading?: boolean;
    resolveIdentifiers?: (
      identifiers: string[],
    ) => Promise<AssetSpreadsheetSourceRow[]>;
    rows: AssetSpreadsheetSourceRow[];
    submitting: boolean;
    targetLabel: string;
    title: string;
  }>(),
  { allowCreate: false, loading: false },
);

const emit = defineEmits<{
  submit: [submission: AssetBatchEditSubmission];
}>();

const open = defineModel<boolean>('open', { default: false });
const gridRef = ref<VxeGridInstance<EditorRow>>();
const editorRows = ref<EditorRow[]>([]);
const initialRows = ref<AssetSpreadsheetSourceRow[]>([]);
const undoStack = ref<CellChange[][]>([]);
const filterConditions = ref<FilterCondition[]>([]);
const sortField = ref('');
const sortDirection = ref<'asc' | 'desc'>('asc');
const fillField = ref('');
const fillValue = ref<AssetBatchEditValue>('');
const statisticField = ref('');
const fullscreen = ref(false);
const pasteOpen = ref(false);
const pasteText = ref('');
const pasteHasHeader = ref(true);
const pastePreview = ref<PastePreviewRow[]>([]);
const pasteResolving = ref(false);
const ignoredPasteHeaders = ref<string[]>([]);
const selectionEnd = ref<SelectionPoint>();
const selectionStart = ref<SelectionPoint>();
const gridContainerRef = ref<HTMLElement>();
const activeCell = ref<ActiveCell>();
const activeDraft = ref<AssetBatchEditValue>('');
const activeEditorOpen = ref(false);
const activeEditorRef = ref<FocusableEditor>();
const activeStartValue = ref<AssetBatchEditValue>('');
const isDraggingSelection = ref(false);
const hasDraggedSelection = ref(false);
const internalClipboard = ref<{
  matrix: AssetBatchEditValue[][];
  text: string;
}>();
let newRowSequence = 0;
let filterConditionSequence = 0;
let pendingSelectionEnd: SelectionPoint | undefined;
let selectionFrame: number | undefined;

const columnKeyByField = computed(
  () =>
    new Map(
      props.fields.map((field, index) => [field.key, `__column_${index}`]),
    ),
);
const fieldByColumnKey = computed(
  () =>
    new Map(props.fields.map((field, index) => [`__column_${index}`, field])),
);
const fieldByKey = computed(
  () => new Map(props.fields.map((field) => [field.key, field])),
);
const fieldIndexByKey = computed(
  () => new Map(props.fields.map((field, index) => [field.key, index])),
);
const optionLabelByField = computed(() => {
  const lookups = new Map<string, Map<string, string>>();
  for (const field of props.fields) {
    if (!field.options?.length) continue;
    lookups.set(
      field.key,
      new Map(field.options.map((option) => [option.value, option.label])),
    );
  }
  return lookups;
});
const selectValueLookupByField = computed(() => {
  const lookups = new Map<string, Map<string, null | string>>();
  for (const field of props.fields) {
    if (field.type !== 'select') continue;
    const lookup = new Map<string, null | string>();
    for (const option of field.options ?? []) {
      for (const key of [option.value, option.label]) {
        const existing = lookup.get(key);
        lookup.set(
          key,
          lookup.has(key) && existing !== option.value ? null : option.value,
        );
      }
    }
    lookups.set(field.key, lookup);
  }
  return lookups;
});
const editableFields = computed(() =>
  props.fields.filter((field) => field.editable !== false),
);
const nonSensitiveFields = computed(() =>
  props.fields.filter((field) => !field.sensitive),
);
const identifierField = computed(() =>
  fieldByKey.value.get(props.identifierKey),
);
const canAddFilterCondition = computed(
  () =>
    filterConditions.value.every((condition) => condition.fieldKey) &&
    filterConditions.value.length < nonSensitiveFields.value.length,
);
const pasteColumnHeaderText = computed(() =>
  props.fields.map((field) => field.label).join('\t'),
);

function cloneValue(
  value: AssetBatchEditValue | undefined,
): AssetBatchEditValue {
  return Array.isArray(value) ? [...value] : (value ?? '');
}

function equalValue(left: AssetBatchEditValue, right: AssetBatchEditValue) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function hasFilterValue(value: AssetBatchEditValue) {
  return Array.isArray(value)
    ? value.length > 0
    : String(value).trim().length > 0;
}

function addFilterCondition() {
  if (!canAddFilterCondition.value) return;
  filterConditions.value.push({
    fieldKey: '',
    id: `filter-${++filterConditionSequence}`,
    value: '',
  });
}

function removeFilterCondition(conditionId: string) {
  filterConditions.value = filterConditions.value.filter(
    (condition) => condition.id !== conditionId,
  );
}

function filterFieldOptions(conditionId: string) {
  const usedFieldKeys = new Set(
    filterConditions.value
      .filter((condition) => condition.id !== conditionId)
      .map((condition) => condition.fieldKey)
      .filter(Boolean),
  );
  return nonSensitiveFields.value
    .filter((field) => !usedFieldKeys.has(field.key))
    .map((field) => ({ label: field.label, value: field.key }));
}

function filterFieldFor(condition: FilterCondition) {
  return fieldByKey.value.get(condition.fieldKey);
}

function handleFilterFieldChange(condition: FilterCondition, fieldKey: string) {
  condition.fieldKey = fieldKey;
  condition.dateRange = undefined;
  const field = fieldByKey.value.get(fieldKey);
  condition.value =
    field?.type === 'select' || field?.type === 'user' ? [] : '';
}

function handleFilterDateRangeChange(
  condition: FilterCondition,
  value: unknown,
) {
  if (
    Array.isArray(value) &&
    value.length === 2 &&
    dayjs.isDayjs(value[0]) &&
    dayjs.isDayjs(value[1])
  ) {
    condition.dateRange = [value[0], value[1]];
    return;
  }
  condition.dateRange = undefined;
}

function normalizeFilterSelection(value: unknown) {
  if (Array.isArray(value))
    return [...new Set(value.map(String).filter(Boolean))];
  if (typeof value === 'string' || typeof value === 'number')
    return value ? [String(value)] : [];
  return [];
}

function textFilterKeywords(value: AssetBatchEditValue) {
  const rawValues = Array.isArray(value) ? value : [value];
  return [
    ...new Set(
      rawValues
        .flatMap((item) => String(item).split(/\s+/))
        .map((item) => item.trim().toLocaleLowerCase())
        .filter(Boolean),
    ),
  ];
}

function displayValue(value: AssetBatchEditValue, field?: AssetBatchEditField) {
  if (field?.sensitive)
    return value && String(value).length > 0 ? '已配置' : '';
  if (Array.isArray(value)) return value.join('、');
  const optionLabel = field
    ? optionLabelByField.value.get(field.key)?.get(value)
    : undefined;
  return optionLabel ?? value;
}

function exportValue(value: AssetBatchEditValue, field: AssetBatchEditField) {
  if (!field.sensitive) return displayValue(value, field);
  return Array.isArray(value) ? value.join('、') : value;
}

function createEditorRow(source: AssetSpreadsheetSourceRow): EditorRow {
  const row: EditorRow = {
    __cellRevisions: {},
    __dirtyFields: new Set(),
    __errors: {},
    __id: source.id,
    __isNew: Boolean(source.isNew),
    __key: source.id ?? `new-${++newRowSequence}`,
    __original: {},
    __origin: source.isNew ? (source.origin ?? 'paste') : 'existing',
  };
  props.fields.forEach((field) => {
    const value = cloneValue(source.values[field.key]);
    row.__original[field.key] = cloneValue(value);
    row.__cellRevisions[field.key] = 0;
    row[columnKeyByField.value.get(field.key)!] = value;
  });
  if (row.__isNew) {
    for (const field of props.fields) {
      if (isFieldEditable(row, field)) row.__dirtyFields.add(field.key);
    }
  }
  return row;
}

function rowValue(row: EditorRow, fieldKey: string): AssetBatchEditValue {
  return (row[columnKeyByField.value.get(fieldKey)!] ??
    '') as AssetBatchEditValue;
}

function columnField(columnKey?: string) {
  return fieldByColumnKey.value.get(columnKey ?? '')!;
}

function columnValue(row: EditorRow, columnKey?: string) {
  return (row[columnKey ?? ''] ?? '') as AssetBatchEditValue;
}

function cellDisplayText(row: EditorRow, columnKey?: string) {
  const field = columnField(columnKey);
  return displayValue(columnValue(row, columnKey), field) || '-';
}

function dateValue(value: AssetBatchEditValue): Dayjs | undefined {
  if (Array.isArray(value) || !value) return undefined;
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed : undefined;
}

function getEditorPopupContainer() {
  return document.body;
}

/** 避免浏览器把资产凭证单元格误判为站点登录表单并自动填入已保存账号。 */
function editorControlName(row: EditorRow, field: AssetBatchEditField) {
  const fieldIndex = fieldIndexByKey.value.get(field.key) ?? 0;
  return `asset-grid-cell-${row.__key}-${fieldIndex}`;
}

function isDirtyCell(row: EditorRow, columnKey?: string) {
  return row.__dirtyFields.has(columnField(columnKey).key);
}

function isFieldEditable(row: EditorRow, field: AssetBatchEditField) {
  return (
    field.editable !== false ||
    (row.__isNew && field.key === props.identifierKey)
  );
}

function cellError(row: EditorRow, columnKey?: string) {
  return row.__errors[columnField(columnKey).key];
}

function setRowValue(
  row: EditorRow,
  fieldKey: string,
  value: AssetBatchEditValue,
) {
  const nextValue = cloneValue(value);
  row[columnKeyByField.value.get(fieldKey)!] = nextValue;
  if (row.__isNew || !equalValue(nextValue, row.__original[fieldKey] ?? '')) {
    row.__dirtyFields.add(fieldKey);
  } else {
    row.__dirtyFields.delete(fieldKey);
  }
  delete row.__errors[fieldKey];
  row.__cellRevisions[fieldKey] = (row.__cellRevisions[fieldKey] ?? 0) + 1;
}

function clearRowErrors(row: EditorRow) {
  const errorFields = Object.keys(row.__errors);
  row.__errors = {};
  for (const fieldKey of errorFields) {
    row.__cellRevisions[fieldKey] = (row.__cellRevisions[fieldKey] ?? 0) + 1;
  }
}

function dirtyFields(row: EditorRow) {
  return [...row.__dirtyFields];
}

function rowStatus(row: EditorRow) {
  if (Object.keys(row.__errors).length) return 'error';
  if (row.__isNew) return 'new';
  return dirtyFields(row).length ? 'modified' : 'unchanged';
}

function rowHasResettableChanges(row: EditorRow) {
  return props.fields.some(
    (field) =>
      !equalValue(rowValue(row, field.key), row.__original[field.key] ?? ''),
  );
}

function hasCellValue(value: AssetBatchEditValue) {
  return Array.isArray(value)
    ? value.length > 0
    : String(value).trim().length > 0;
}

function matchesRequiredCondition(row: EditorRow, field: AssetBatchEditField) {
  const condition = field.requiredWhen;
  if (!condition) return false;
  const dependencyValue = rowValue(row, condition.fieldKey);
  return (
    !Array.isArray(dependencyValue) &&
    condition.values.includes(String(dependencyValue))
  );
}

function hasRequiredIndicator(field: AssetBatchEditField) {
  return Boolean(field.required || field.requiredWhen);
}

const filteredRows = computed(() => {
  let rows = [...editorRows.value];
  for (const condition of filterConditions.value) {
    const field = filterFieldFor(condition);
    if (!field) continue;
    if (field.type === 'date' && condition.dateRange) {
      const [start, end] = condition.dateRange;
      rows = rows.filter((row) => {
        const value = dateValue(rowValue(row, field.key));
        return (
          value && !value.isBefore(start, 'day') && !value.isAfter(end, 'day')
        );
      });
      continue;
    }
    if (
      (field.type === 'select' || field.type === 'user') &&
      hasFilterValue(condition.value)
    ) {
      const expected = normalizeFilterSelection(condition.value);
      rows = rows.filter((row) => {
        const actual = rowValue(row, field.key);
        const actualValues = Array.isArray(actual) ? actual : [actual];
        return expected.some((value) => actualValues.includes(value));
      });
      continue;
    }
    const keywords = textFilterKeywords(condition.value);
    if (!keywords.length) continue;
    rows = rows.filter((row) => {
      const actual = displayValue(rowValue(row, field.key), field)
        .trim()
        .toLocaleLowerCase();
      return keywords.some((keyword) => actual.includes(keyword));
    });
  }
  const sort = fieldByKey.value.get(sortField.value);
  if (sort) {
    rows.sort((left, right) => {
      const result = displayValue(rowValue(left, sort.key), sort).localeCompare(
        displayValue(rowValue(right, sort.key), sort),
        'zh-CN',
        { numeric: true },
      );
      return sortDirection.value === 'asc' ? result : -result;
    });
  }
  return rows;
});
const editorRowByKey = computed(
  () => new Map(editorRows.value.map((row) => [row.__key, row])),
);
const filteredRowIndexByKey = computed(
  () => new Map(filteredRows.value.map((row, index) => [row.__key, index])),
);
const selectionBounds = computed<SelectionBounds | undefined>(() => {
  if (!selectionStart.value || !selectionEnd.value) return undefined;
  const firstRow = filteredRowIndexByKey.value.get(selectionStart.value.rowKey);
  const lastRow = filteredRowIndexByKey.value.get(selectionEnd.value.rowKey);
  const firstField = fieldIndexByKey.value.get(selectionStart.value.fieldKey);
  const lastField = fieldIndexByKey.value.get(selectionEnd.value.fieldKey);
  if (
    firstRow === undefined ||
    lastRow === undefined ||
    firstField === undefined ||
    lastField === undefined
  )
    return undefined;
  return {
    endField: Math.max(firstField, lastField),
    endRow: Math.max(firstRow, lastRow),
    startField: Math.min(firstField, lastField),
    startRow: Math.min(firstRow, lastRow),
  };
});

const gridEmptyText = computed(() => {
  if (editorRows.value.length) return '没有符合当前筛选条件的数据';
  return props.allowCreate
    ? '暂无数据，可粘贴数据或添加空白行'
    : '暂无数据，请粘贴已有资产数据';
});

const changedRows = computed(() =>
  editorRows.value.filter((row) => row.__isNew || dirtyFields(row).length > 0),
);
const modifiedCellCount = computed(() =>
  editorRows.value.reduce((total, row) => total + dirtyFields(row).length, 0),
);
const changeSummary = computed(() => {
  const added = editorRows.value.filter((row) => row.__isNew).length;
  const modified = editorRows.value.filter(
    (row) => !row.__isNew && dirtyFields(row).length,
  ).length;
  return `新增 ${added} 行，修改 ${modified} 行 / ${modifiedCellCount.value} 个单元格`;
});

const gridOptions = computed<VxeGridProps<EditorRow>>(() => {
  return {
    border: false,
    columnConfig: { isCurrent: false, resizable: true },
    columns: [
      {
        field: '__status',
        fixed: 'left',
        slots: { default: 'status' },
        title: '变更状态',
        width: 176,
      },
      ...props.fields.map((field, index) => ({
        field: `__column_${index}`,
        minWidth: field.type === 'textarea' ? 220 : 160,
        slots: { default: 'cell', header: 'fieldHeader' },
        title: field.label,
      })),
    ],
    height: fullscreen.value ? '100%' : 500,
    keepSource: true,
    loading: props.loading,
    mouseConfig: { area: false, selected: false },
    rowConfig: { isCurrent: false, keyField: '__key' },
    scrollX: { enabled: true, gt: 8, oSize: 0, preSize: 1 },
    scrollY: { enabled: true, gt: 40, oSize: 0, preSize: 1 },
    showOverflow: true,
  };
});

function initialize() {
  cancelSelectionFrame();
  activeCell.value = undefined;
  activeEditorOpen.value = false;
  initialRows.value = props.rows.map((row) => ({
    ...row,
    values: Object.fromEntries(
      Object.entries(row.values).map(([key, value]) => [
        key,
        cloneValue(value),
      ]),
    ),
  }));
  editorRows.value = initialRows.value.map(createEditorRow);
  undoStack.value = [];
  filterConditions.value = [];
  sortField.value = '';
  pasteText.value = pasteHasHeader.value
    ? ''
    : `${pasteColumnHeaderText.value}\n`;
  pastePreview.value = [];
  ignoredPasteHeaders.value = [];
  selectionStart.value = undefined;
  selectionEnd.value = undefined;
  internalClipboard.value = undefined;
}

// VXE 在隐藏的 Modal 内首次挂载时可能缓存错误的滚动位移，导致表体数据落到可视区之外。
async function refreshGridLayout() {
  if (!open.value) return;
  await nextTick();
  const grid = gridRef.value;
  if (!grid) return;
  await grid.recalculate(true);
  await grid.scrollTo(1, 0);
  await grid.scrollTo(0, 0);
}

function handleAfterOpenChange(isOpen: boolean) {
  if (isOpen) void refreshGridLayout();
}

function selectionPoints() {
  return selectionBounds.value;
}

function isCellSelected(row: EditorRow, fieldKey: string) {
  const points = selectionBounds.value;
  if (!points) return false;
  const rowIndex = filteredRowIndexByKey.value.get(row.__key) ?? -1;
  const fieldIndex = fieldIndexByKey.value.get(fieldKey) ?? -1;
  return (
    rowIndex >= points.startRow &&
    rowIndex <= points.endRow &&
    fieldIndex >= points.startField &&
    fieldIndex <= points.endField
  );
}

function cancelSelectionFrame() {
  pendingSelectionEnd = undefined;
  if (selectionFrame !== undefined) cancelAnimationFrame(selectionFrame);
  selectionFrame = undefined;
}

function flushSelectionEnd() {
  if (pendingSelectionEnd) {
    selectionEnd.value = pendingSelectionEnd;
    pendingSelectionEnd = undefined;
  }
  selectionFrame = undefined;
}

function handleSelectionMouseDown(
  event: MouseEvent,
  row: EditorRow,
  fieldKey: string,
) {
  if (event.button !== 0) return;
  cancelSelectionFrame();
  const point = { fieldKey, rowKey: row.__key };
  hasDraggedSelection.value = false;
  if (event.shiftKey && selectionStart.value) {
    selectionEnd.value = point;
    hasDraggedSelection.value = true;
  } else {
    selectionStart.value = point;
    selectionEnd.value = point;
  }
  isDraggingSelection.value = true;
}

function handleSelectionMouseEnter(row: EditorRow, fieldKey: string) {
  if (!isDraggingSelection.value || !selectionStart.value) return;
  const point = { fieldKey, rowKey: row.__key };
  const currentPoint = pendingSelectionEnd ?? selectionEnd.value;
  if (
    point.fieldKey === currentPoint?.fieldKey &&
    point.rowKey === currentPoint?.rowKey
  )
    return;
  hasDraggedSelection.value = true;
  pendingSelectionEnd = point;
  if (selectionFrame === undefined)
    selectionFrame = requestAnimationFrame(flushSelectionEnd);
}

function handleSelectionMouseUp() {
  if (!isDraggingSelection.value) return;
  if (selectionFrame !== undefined) cancelAnimationFrame(selectionFrame);
  flushSelectionEnd();
  isDraggingSelection.value = false;
  if (hasDraggedSelection.value)
    gridContainerRef.value?.focus({ preventScroll: true });
}

function pushUndo(changes: CellChange[]) {
  const actual = changes.filter(
    (change) =>
      change.fieldKey === '__new_row__' ||
      change.fieldKey === '__appended_row__' ||
      change.fieldKey === '__removed_row__' ||
      !equalValue(change.before, change.after),
  );
  if (!actual.length) return;
  undoStack.value = [...undoStack.value.slice(-99), actual];
}

function cloneEditorRowForUpdate(row: EditorRow): EditorRow {
  return {
    ...row,
    __cellRevisions: { ...row.__cellRevisions },
    __dirtyFields: new Set(row.__dirtyFields),
    __errors: { ...row.__errors },
    __original: row.__original,
  };
}

// 一次操作只替换受影响的行，让 Vue 与 VXE 在粘贴、填充、撤销后只刷新一批数据。
function applyCellChanges(
  changes: CellChange[],
  removedRowKeys: ReadonlySet<string> = new Set(),
) {
  const replacements = new Map<string, EditorRow>();
  for (const change of changes) {
    if (change.fieldKey.startsWith('__') || removedRowKeys.has(change.rowKey))
      continue;
    const source =
      replacements.get(change.rowKey) ??
      editorRowByKey.value.get(change.rowKey);
    if (!source) continue;
    const target = replacements.has(change.rowKey)
      ? source
      : cloneEditorRowForUpdate(source);
    setRowValue(target, change.fieldKey, change.after);
    replacements.set(change.rowKey, target);
  }
  if (!replacements.size && !removedRowKeys.size) return;
  editorRows.value = editorRows.value
    .filter((row) => !removedRowKeys.has(row.__key))
    .map((row) => replacements.get(row.__key) ?? row);
}

function normalizeEditorValue(value: unknown): AssetBatchEditValue {
  return Array.isArray(value)
    ? value.map(String)
    : value === undefined || value === null
      ? ''
      : String(value);
}

function isActiveCell(row: EditorRow, fieldKey: string) {
  return (
    activeCell.value?.rowKey === row.__key &&
    activeCell.value.fieldKey === fieldKey
  );
}

function commitActiveCell() {
  const point = activeCell.value;
  if (!point) return;
  const row = editorRowByKey.value.get(point.rowKey);
  const before = cloneValue(activeStartValue.value);
  const after = cloneValue(activeDraft.value);
  activeEditorOpen.value = false;
  activeCell.value = undefined;
  if (!row || equalValue(before, after)) return;
  setRowValue(row, point.fieldKey, after);
  pushUndo([{ after, before, fieldKey: point.fieldKey, rowKey: point.rowKey }]);
}

function activateCell(row: EditorRow, field: AssetBatchEditField) {
  if (
    hasDraggedSelection.value ||
    !isFieldEditable(row, field) ||
    isActiveCell(row, field.key)
  )
    return;
  commitActiveCell();
  const value = cloneValue(rowValue(row, field.key));
  activeStartValue.value = cloneValue(value);
  activeDraft.value = value;
  activeCell.value = { fieldKey: field.key, rowKey: row.__key };
  activeEditorOpen.value = ['date', 'select', 'user'].includes(field.type);
  void nextTick(() => activeEditorRef.value?.focus?.());
}

function handleActiveValue(value: unknown) {
  activeDraft.value = normalizeEditorValue(value);
}

function handleActiveDateValue(value: unknown) {
  const parsed = dayjs.isDayjs(value)
    ? value
    : value
      ? dayjs(String(value))
      : null;
  activeDraft.value = parsed?.isValid() ? parsed.format('YYYY-MM-DD') : '';
}

function handleActiveEditorOpenChange(isOpen: boolean) {
  activeEditorOpen.value = isOpen;
  if (isOpen) return;
  const closingCell = activeCell.value;
  void nextTick(() => {
    if (
      activeCell.value?.rowKey === closingCell?.rowKey &&
      activeCell.value?.fieldKey === closingCell?.fieldKey
    )
      commitActiveCell();
  });
}

function handleFillDateValue(value: unknown) {
  const parsed = dayjs.isDayjs(value)
    ? value
    : value
      ? dayjs(String(value))
      : null;
  fillValue.value = parsed?.isValid() ? parsed.format('YYYY-MM-DD') : '';
}

function undo() {
  const operation = undoStack.value.pop();
  if (!operation) return;
  const removedRowKeys = new Set<string>();
  const restoredRows: Array<{
    index: number;
    row: EditorRow;
  }> = [];
  const revertedChanges: CellChange[] = [];
  for (const change of [...operation].reverse()) {
    if (
      change.fieldKey === '__new_row__' ||
      change.fieldKey === '__appended_row__'
    ) {
      removedRowKeys.add(change.rowKey);
    } else if (change.fieldKey === '__removed_row__' && change.rowSnapshot) {
      restoredRows.push({
        index: change.rowIndex ?? editorRows.value.length,
        row: cloneEditorRowForUpdate(change.rowSnapshot),
      });
    } else {
      revertedChanges.push({ ...change, after: cloneValue(change.before) });
    }
  }
  applyCellChanges(revertedChanges, removedRowKeys);
  if (restoredRows.length) {
    const rows = [...editorRows.value];
    restoredRows
      .sort((left, right) => left.index - right.index)
      .forEach(({ index, row }) => rows.splice(index, 0, row));
    editorRows.value = rows;
  }
}

function addBlankRow() {
  if (!props.allowCreate) return;
  if (editorRows.value.length >= 1000) {
    message.warning('单次最多编辑 1000 行');
    return;
  }
  const row = createEditorRow({
    isNew: true,
    origin: 'manual',
    values: Object.fromEntries(
      props.fields.map((field) => [field.key, field.multiple ? [] : '']),
    ),
  });
  editorRows.value = [...editorRows.value, row];
  pushUndo([
    {
      after: '',
      before: '',
      fieldKey: '__new_row__',
      rowKey: row.__key,
    },
  ]);
  void nextTick(() => gridRef.value?.scrollToRow(row));
}

function resetRow(row: EditorRow) {
  const changes = props.fields
    .map((field) => ({
      after: cloneValue(row.__original[field.key]),
      before: rowValue(row, field.key),
      fieldKey: field.key,
      rowKey: row.__key,
    }))
    .filter((change) => !equalValue(change.before, change.after));
  if (!changes.length) return;
  applyCellChanges(changes);
  const refreshed = editorRowByKey.value.get(row.__key);
  if (refreshed) clearRowErrors(refreshed);
  pushUndo(changes);
}

function removeManualRow(row: EditorRow) {
  if (!row.__isNew || row.__origin !== 'manual') return;
  const rowIndex = editorRows.value.indexOf(row);
  pushUndo([
    {
      after: '',
      before: '',
      fieldKey: '__removed_row__',
      rowIndex,
      rowKey: row.__key,
      rowSnapshot: cloneEditorRowForUpdate(row),
    },
  ]);
  editorRows.value = editorRows.value.filter(
    (item) => item.__key !== row.__key,
  );
}

function restoreInitial() {
  Modal.confirm({
    content: '将清除全部暂存修改、新增行、筛选和排序，此操作不能撤销。',
    okText: '还原初始',
    title: '确认还原初始状态？',
    onOk: initialize,
  });
}

function fillValueForField(field: AssetBatchEditField) {
  if (field.multiple)
    return Array.isArray(fillValue.value) ? fillValue.value : [];
  return Array.isArray(fillValue.value) ? '' : fillValue.value;
}

function applyBulkFill() {
  const field = fieldByKey.value.get(fillField.value);
  if (!field || field.editable === false) return;
  const after = fillValueForField(field);
  const changes = filteredRows.value
    .map((row) => ({
      after: cloneValue(after),
      before: rowValue(row, field.key),
      fieldKey: field.key,
      rowKey: row.__key,
    }))
    .filter((change) => !equalValue(change.before, change.after));
  if (!changes.length) return message.info('当前筛选结果没有需要修改的值');
  Modal.confirm({
    content: `将影响 ${filteredRows.value.length} 行，实际修改 ${changes.length} 个单元格。`,
    okText: '应用填充',
    title: `批量填充“${field.label}”`,
    onOk: () => {
      applyCellChanges(changes);
      pushUndo(changes);
    },
  });
}

function normalizePasteHeader(value: string) {
  return value.replaceAll(/[*＊]/g, '').trim().toLocaleLowerCase();
}

const headerLookup = computed(() => {
  const map = new Map<string, AssetBatchEditField>();
  for (const field of props.fields) {
    [field.label, field.key, ...(field.aliases ?? [])].forEach((key) =>
      map.set(normalizePasteHeader(key), field),
    );
  }
  return map;
});

function parsePaste() {
  ignoredPasteHeaders.value = [];
  const matrix = pasteText.value
    .replaceAll('\r\n', '\n')
    .split('\n')
    .filter((line) => line.length > 0)
    .map((line) => line.split('\t'));
  if (!matrix.length) {
    pastePreview.value = [];
    return;
  }
  const hasTextHeader =
    !pasteHasHeader.value &&
    matrix[0]?.length === props.fields.length &&
    matrix[0].every(
      (cell, index) =>
        normalizePasteHeader(cell) ===
        normalizePasteHeader(props.fields[index]?.label ?? ''),
    );
  if (hasTextHeader) matrix.shift();
  const headers = pasteHasHeader.value ? matrix.shift()! : [];
  const mappedFields = pasteHasHeader.value
    ? headers.map((header) =>
        headerLookup.value.get(normalizePasteHeader(header)),
      )
    : props.fields;
  const headerErrors: string[] = [];
  if (pasteHasHeader.value) {
    const seen = new Set<string>();
    const ignored = new Set<string>();
    headers.forEach((header, index) => {
      const field = mappedFields[index];
      if (!field) ignored.add(header.trim() || '空白列');
      else if (seen.has(field.key)) headerErrors.push(`重复表头：${header}`);
      else seen.add(field.key);
    });
    ignoredPasteHeaders.value = [...ignored];
  }
  const existingByIdentifier = new Map(
    editorRows.value.map((row) => [
      String(rowValue(row, props.identifierKey)),
      row,
    ]),
  );
  const pastedIdentifiers = new Set<string>();
  pastePreview.value = matrix.slice(0, 1000).map((cells, index) => {
    const values: Record<string, AssetBatchEditValue> = {};
    mappedFields.forEach((field, columnIndex) => {
      if (field) values[field.key] = cells[columnIndex] ?? '';
    });
    const errors = [...headerErrors];
    const identifier = String(values[props.identifierKey] ?? '').trim();
    if (!identifier)
      errors.push(`${identifierField.value?.label ?? '唯一标识'}不能为空`);
    if (identifier && pastedIdentifiers.has(identifier))
      errors.push('唯一标识在本次粘贴中重复');
    pastedIdentifiers.add(identifier);
    const target = existingByIdentifier.get(identifier);
    if (target) {
      for (const field of mappedFields) {
        if (
          !field ||
          field.editable !== false ||
          values[field.key] === undefined
        )
          continue;
        if (!equalValue(rowValue(target, field.key), values[field.key]!))
          errors.push(`${field.label}为只读字段`);
      }
    }
    return {
      errors,
      line: index + (pasteHasHeader.value || hasTextHeader ? 2 : 1),
      target,
      values,
    };
  });
}

const pasteErrorCount = computed(() =>
  pastePreview.value.reduce((count, row) => count + row.errors.length, 0),
);

function setPasteHeaderMode(hasHeader: boolean) {
  pasteHasHeader.value = hasHeader;
  if (
    !hasHeader &&
    !pasteText.value.startsWith(`${pasteColumnHeaderText.value}\n`) &&
    pasteText.value !== pasteColumnHeaderText.value
  ) {
    pasteText.value = pasteText.value
      ? `${pasteColumnHeaderText.value}\n${pasteText.value}`
      : `${pasteColumnHeaderText.value}\n`;
  }
}

async function confirmPaste() {
  parsePaste();
  if (!pastePreview.value.length || pasteErrorCount.value) return;
  pasteResolving.value = true;
  try {
    const unresolvedIdentifiers = pastePreview.value
      .filter((preview) => !preview.target && preview.errors.length === 0)
      .map((preview) =>
        String(preview.values[props.identifierKey] ?? '').trim(),
      )
      .filter(Boolean);
    if (unresolvedIdentifiers.length && props.resolveIdentifiers) {
      const resolvedSources = await props.resolveIdentifiers(
        unresolvedIdentifiers,
      );
      const resolvedByIdentifier = new Map(
        resolvedSources.map((source) => [
          String(source.values[props.identifierKey] ?? '').trim(),
          createEditorRow({ ...source, isNew: false }),
        ]),
      );
      for (const preview of pastePreview.value) {
        if (preview.target) continue;
        const identifier = String(
          preview.values[props.identifierKey] ?? '',
        ).trim();
        preview.target = resolvedByIdentifier.get(identifier);
      }
    }

    for (const preview of pastePreview.value) {
      if (!preview.target) {
        if (!props.allowCreate)
          preview.errors.push(
            `该${props.targetLabel}类型不支持粘贴新增，只能修改已有资产`,
          );
        continue;
      }
      for (const field of props.fields) {
        if (field.editable !== false || preview.values[field.key] === undefined)
          continue;
        if (
          !equalValue(
            rowValue(preview.target, field.key),
            preview.values[field.key]!,
          )
        )
          preview.errors.push(`${field.label}为只读字段`);
      }
    }
    if (pasteErrorCount.value) return;

    const changes: CellChange[] = [];
    const appendedRows: EditorRow[] = [];
    const currentRowKeys = new Set(editorRows.value.map((row) => row.__key));
    for (const preview of pastePreview.value) {
      let target = preview.target;
      if (!target) {
        target = createEditorRow({
          isNew: true,
          origin: 'paste',
          values: preview.values,
        });
        appendedRows.push(target);
        changes.push({
          after: '',
          before: '',
          fieldKey: '__new_row__',
          rowKey: target.__key,
        });
        continue;
      }
      if (!currentRowKeys.has(target.__key)) {
        appendedRows.push(target);
        currentRowKeys.add(target.__key);
        changes.push({
          after: '',
          before: '',
          fieldKey: '__appended_row__',
          rowKey: target.__key,
        });
      }
      for (const field of editableFields.value) {
        if (preview.values[field.key] === undefined) continue;
        const before = rowValue(target, field.key);
        const after = cloneValue(preview.values[field.key]);
        if (!equalValue(before, after)) {
          changes.push({
            after,
            before,
            fieldKey: field.key,
            rowKey: target.__key,
          });
        }
      }
    }
    if (appendedRows.length)
      editorRows.value = [...editorRows.value, ...appendedRows];
    applyCellChanges(changes);
    pushUndo(changes);
    pasteOpen.value = false;
    message.success(
      `已暂存 ${pastePreview.value.length} 行粘贴数据，保存后生效`,
    );
  } finally {
    pasteResolving.value = false;
  }
}

function selectedTableRange() {
  const points = selectionPoints();
  if (!points) return undefined;
  return {
    fields: props.fields.slice(points.startField, points.endField + 1),
    points,
    rows: filteredRows.value.slice(points.startRow, points.endRow + 1),
  };
}

function clipboardText(matrix: AssetBatchEditValue[][]) {
  return matrix
    .map((row) =>
      row
        .map((value) => (Array.isArray(value) ? value.join('、') : value))
        .join('\t'),
    )
    .join('\n');
}

function isNativeClipboardTarget(
  target: EventTarget | null,
  allowCollapsedTextSelection = false,
) {
  if (!(target instanceof HTMLElement)) return false;
  if (
    allowCollapsedTextSelection &&
    (target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement)
  )
    return target.selectionStart !== target.selectionEnd;
  return Boolean(
    target.closest(
      'input, textarea, [contenteditable="true"], .ant-select-dropdown, .ant-picker-dropdown',
    ),
  );
}

function handleClipboardCopy(event: ClipboardEvent) {
  if (
    !open.value ||
    pasteOpen.value ||
    isNativeClipboardTarget(event.target, true)
  )
    return;
  const range = selectedTableRange();
  if (!range) return;
  if (range.fields.some((field) => field.sensitive)) {
    event.preventDefault();
    message.warning('选区包含敏感字段，不能复制');
    return;
  }
  const rawMatrix: AssetBatchEditValue[][] = [];
  const displayMatrix: AssetBatchEditValue[][] = [];
  for (const row of range.rows) {
    const rawRow: AssetBatchEditValue[] = [];
    const displayRow: AssetBatchEditValue[] = [];
    for (const field of range.fields) {
      const value = rowValue(row, field.key);
      rawRow.push(cloneValue(value));
      displayRow.push(displayValue(value, field));
    }
    rawMatrix.push(rawRow);
    displayMatrix.push(displayRow);
  }
  const text = clipboardText(displayMatrix);
  event.preventDefault();
  event.clipboardData?.setData('text/plain', text);
  internalClipboard.value = { matrix: rawMatrix, text };
  message.success(
    `已复制选区 ${range.rows.length} 行 × ${range.fields.length} 列`,
  );
}

function parseClipboardText(text: string) {
  const lines = text
    .replaceAll('\r\n', '\n')
    .replaceAll('\r', '\n')
    .split('\n');
  while (lines.at(-1) === '') lines.pop();
  return lines.map((line) => line.split('\t'));
}

function splitClipboardValues(value: string) {
  return value
    .split(/[、,，;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function createUserLookup(users: OrganizationUser[]) {
  const lookup = new Map<string, null | string>();
  for (const user of users) {
    for (const label of [
      user.id,
      user.displayName,
      user.realName,
      user.username,
    ]) {
      const key = label?.trim().toLocaleLowerCase();
      if (!key) continue;
      const existing = lookup.get(key);
      lookup.set(key, lookup.has(key) && existing !== user.id ? null : user.id);
    }
  }
  return lookup;
}

function matchUserIds(
  value: AssetBatchEditValue,
  userLookup: ReadonlyMap<string, null | string>,
) {
  const inputs = Array.isArray(value) ? value : splitClipboardValues(value);
  const matchedIds: string[] = [];
  for (const input of inputs) {
    const keyword = input.trim().toLocaleLowerCase();
    if (!keyword) continue;
    const id = userLookup.get(keyword);
    if (!id) return undefined;
    matchedIds.push(id);
  }
  return [...new Set(matchedIds)];
}

function parseQuickPasteValue(
  rawValue: AssetBatchEditValue,
  field: AssetBatchEditField,
  userLookup: ReadonlyMap<string, null | string>,
): QuickPasteResult {
  if (field.type === 'date') {
    if (Array.isArray(rawValue))
      return { error: `${field.label}不是有效日期`, value: '' };
    if (!rawValue.trim()) return { value: '' };
    const parsed = dayjs(rawValue.trim());
    return parsed.isValid()
      ? { value: parsed.format('YYYY-MM-DD') }
      : { error: `${field.label}不是有效日期`, value: '' };
  }
  if (field.type === 'select') {
    const inputs = Array.isArray(rawValue)
      ? rawValue
      : field.multiple
        ? splitClipboardValues(rawValue)
        : [rawValue.trim()];
    if (!inputs.some(Boolean)) return { value: field.multiple ? [] : '' };
    const values: string[] = [];
    const optionLookup = selectValueLookupByField.value.get(field.key);
    for (const input of inputs) {
      const value = optionLookup?.get(input);
      if (value === undefined || value === null)
        return {
          error: `${field.label}包含无法识别的选项“${input}”`,
          value: '',
        };
      values.push(value);
    }
    return { value: field.multiple ? values : values[0]! };
  }
  if (field.type === 'user') {
    const matchedIds = matchUserIds(rawValue, userLookup);
    if (!matchedIds)
      return { error: `${field.label}包含无法唯一匹配的用户`, value: '' };
    if (!matchedIds.length) return { value: field.multiple ? [] : '' };
    if (!field.multiple && matchedIds.length > 1)
      return { error: `${field.label}只能选择一个用户`, value: '' };
    return { value: field.multiple ? matchedIds : matchedIds[0]! };
  }
  return {
    value: Array.isArray(rawValue) ? rawValue.join('、') : rawValue,
  };
}

async function handleClipboardPaste(event: ClipboardEvent) {
  if (!open.value || pasteOpen.value || isNativeClipboardTarget(event.target))
    return;
  const range = selectedTableRange();
  if (!range) return;
  const text = event.clipboardData?.getData('text/plain') ?? '';
  if (!text) return;
  event.preventDefault();
  const textMatrix = parseClipboardText(text);
  if (!textMatrix.length || !textMatrix[0]?.length) return;
  const sourceMatrix =
    internalClipboard.value?.text === text
      ? internalClipboard.value.matrix
      : textMatrix;
  const rowCount = range.rows.length;
  const columnCount = range.fields.length;
  const isSingleValue =
    sourceMatrix.length === 1 && sourceMatrix[0]?.length === 1;
  const hasMatchingSize =
    sourceMatrix.length === rowCount &&
    sourceMatrix.every((row) => row.length === columnCount);
  if (!isSingleValue && !hasMatchingSize) {
    message.error(
      `粘贴区域尺寸不一致：选区为 ${rowCount} 行 × ${columnCount} 列`,
    );
    return;
  }

  let userLookup = new Map<string, null | string>();
  if (range.fields.some((field) => field.type === 'user')) {
    try {
      userLookup = createUserLookup(await getSharedOrganizationUsers());
    } catch {
      message.error('用户列表加载失败，暂时无法粘贴使用人字段');
      return;
    }
  }

  const changes: CellChange[] = [];
  for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
    const row = range.rows[rowIndex]!;
    for (let fieldIndex = 0; fieldIndex < columnCount; fieldIndex += 1) {
      const field = range.fields[fieldIndex]!;
      if (!isFieldEditable(row, field)) {
        message.error(`“${field.label}”为只读字段，无法粘贴`);
        return;
      }
      const sourceValue = isSingleValue
        ? sourceMatrix[0]![0]!
        : sourceMatrix[rowIndex]![fieldIndex]!;
      const parsed = parseQuickPasteValue(sourceValue, field, userLookup);
      if (parsed.error) {
        message.error(parsed.error);
        return;
      }
      changes.push({
        after: cloneValue(parsed.value),
        before: rowValue(row, field.key),
        fieldKey: field.key,
        rowKey: row.__key,
      });
    }
  }
  const actualChanges = changes.filter(
    (change) => !equalValue(change.before, change.after),
  );
  if (!actualChanges.length) {
    message.info('粘贴内容与当前值一致');
    return;
  }
  applyCellChanges(actualChanges);
  pushUndo(actualChanges);
  message.success(`已暂存修改 ${actualChanges.length} 个单元格，保存后生效`);
}

async function copyRows() {
  const points = selectionPoints();
  const selectedFields = points
    ? props.fields
        .slice(points.startField, points.endField + 1)
        .filter((field) => !field.sensitive)
    : nonSensitiveFields.value;
  const selectedRows = points
    ? filteredRows.value.slice(points.startRow, points.endRow + 1)
    : filteredRows.value;
  if (!selectedFields.length) {
    message.warning('选区只包含敏感字段，不能复制');
    return;
  }
  const headers = selectedFields.map((field) => field.label).join('\t');
  const lines = selectedRows.map((row) =>
    selectedFields
      .map((field) => displayValue(rowValue(row, field.key), field))
      .join('\t'),
  );
  await navigator.clipboard.writeText([headers, ...lines].join('\n'));
  message.success(
    points
      ? `已复制选区 ${selectedRows.length} 行 × ${selectedFields.length} 列`
      : `已复制当前筛选结果 ${filteredRows.value.length} 行`,
  );
}

async function exportRows() {
  const columns = props.fields.map((field) => ({
    key: field.key,
    label: field.label,
    selectOptions:
      field.editable !== false && field.type === 'select'
        ? field.options?.map((option) => option.label)
        : undefined,
  }));
  const rows = filteredRows.value.map((row) =>
    Object.fromEntries(
      props.fields.map((field) => [
        field.key,
        exportValue(rowValue(row, field.key), field),
      ]),
    ),
  );
  await downloadAssetWorkbook(
    `${props.title}_${formatAssetExportTimestamp()}.xlsx`,
    props.targetLabel,
    columns,
    rows,
  );
}

const statistics = computed(() => {
  const field = fieldByKey.value.get(statisticField.value);
  if (!field || field.sensitive) return '';
  const raw = filteredRows.value
    .map((row) => rowValue(row, field.key))
    .filter(
      (value) => !Array.isArray(value) && String(value).trim() !== '',
    ) as string[];
  const numbers = raw.map(Number).filter(Number.isFinite);
  if (numbers.length !== raw.length || !numbers.length)
    return `非空计数 ${raw.length}`;
  const sum = numbers.reduce((total, value) => total + value, 0);
  return `计数 ${numbers.length} · 求和 ${sum} · 平均值 ${sum / numbers.length} · 最大值 ${Math.max(...numbers)} · 最小值 ${Math.min(...numbers)}`;
});

function validate() {
  let firstError:
    | {
        fieldKey: string;
        kind: 'invalid' | 'missing';
        message: string;
        row: EditorRow;
        rowIndex: number;
      }
    | undefined;
  const missingFieldsByRow = new Map<number, string[]>();
  const previousErrorsByRow = new Map(
    editorRows.value.map((row) => [row.__key, { ...row.__errors }]),
  );
  for (const [rowIndex, row] of editorRows.value.entries()) {
    row.__errors = {};
    for (const field of props.fields) {
      const value = rowValue(row, field.key);
      const matchesCondition = matchesRequiredCondition(row, field);
      const isRequired = Boolean(field.required || matchesCondition);
      if (isRequired && !hasCellValue(value)) {
        const errorMessage = `${field.label}不能为空`;
        row.__errors[field.key] = errorMessage;
        const missingFields = missingFieldsByRow.get(rowIndex) ?? [];
        missingFields.push(field.label);
        missingFieldsByRow.set(rowIndex, missingFields);
        firstError ??= {
          fieldKey: field.key,
          kind: 'missing',
          message: errorMessage,
          row,
          rowIndex,
        };
      } else if (
        field.requiredWhen?.incompatibleMessage &&
        hasCellValue(value) &&
        !matchesCondition
      ) {
        const errorMessage = field.requiredWhen.incompatibleMessage;
        row.__errors[field.key] = errorMessage;
        firstError ??= {
          fieldKey: field.key,
          kind: 'invalid',
          message: errorMessage,
          row,
          rowIndex,
        };
      }
    }
  }
  const rowsByIdentifier = new Map<string, EditorRow[]>();
  for (const row of editorRows.value) {
    const identifier = String(rowValue(row, props.identifierKey)).trim();
    if (!identifier) continue;
    const matches = rowsByIdentifier.get(identifier) ?? [];
    matches.push(row);
    rowsByIdentifier.set(identifier, matches);
  }
  for (const rows of rowsByIdentifier.values()) {
    if (rows.length < 2) continue;
    for (const row of rows) {
      const errorMessage = `${identifierField.value?.label ?? '唯一标识'}在当前表格中重复`;
      row.__errors[props.identifierKey] = errorMessage;
      firstError ??= {
        fieldKey: props.identifierKey,
        kind: 'invalid',
        message: errorMessage,
        row,
        rowIndex: editorRows.value.indexOf(row),
      };
    }
  }
  for (const row of editorRows.value) {
    const previousErrors = previousErrorsByRow.get(row.__key) ?? {};
    for (const field of props.fields) {
      if (previousErrors[field.key] === row.__errors[field.key]) continue;
      row.__cellRevisions[field.key] =
        (row.__cellRevisions[field.key] ?? 0) + 1;
    }
  }
  if (firstError) {
    filterConditions.value = [];
    void nextTick(() =>
      gridRef.value?.scrollToRow(
        firstError!.row,
        columnKeyByField.value.get(firstError!.fieldKey),
      ),
    );
    if (firstError.kind === 'missing') {
      const missingFields = missingFieldsByRow.get(firstError.rowIndex) ?? [];
      const remainingRowCount = Math.max(missingFieldsByRow.size - 1, 0);
      message.error(
        `第 ${firstError.rowIndex + 1} 行必填字段未填写：${missingFields.join('、')}${remainingRowCount ? `；另有 ${remainingRowCount} 行存在必填字段未填写` : ''}`,
      );
    } else {
      message.error(`第 ${firstError.rowIndex + 1} 行：${firstError.message}`);
    }
    return false;
  }
  return true;
}

function submit() {
  commitActiveCell();
  if (!changedRows.value.length || !validate()) return;
  emit('submit', {
    rows: changedRows.value.map((row) => ({
      changedFields: dirtyFields(row),
      id: row.__id,
      isNew: row.__isNew,
      rowNumber: editorRows.value.indexOf(row) + 1,
      values: Object.fromEntries(
        props.fields.map((field) => [field.key, rowValue(row, field.key)]),
      ),
    })),
  });
}

function requestClose() {
  commitActiveCell();
  if (!changedRows.value.length) {
    open.value = false;
    return;
  }
  Modal.confirm({
    content: '关闭后所有未保存的修改都会丢失。',
    okText: '放弃修改',
    okType: 'danger',
    title: '存在未保存修改',
    onOk: () => (open.value = false),
  });
}

function handleShortcut(event: KeyboardEvent) {
  if (
    !open.value ||
    !(event.ctrlKey || event.metaKey) ||
    event.key.toLocaleLowerCase() !== 'z'
  )
    return;
  event.preventDefault();
  commitActiveCell();
  undo();
}

watch(
  () => [open.value, props.loading, props.rows] as const,
  ([isOpen, isLoading]) => {
    if (isOpen && !isLoading) {
      initialize();
      void refreshGridLayout();
    }
  },
);
watch(fullscreen, () => void refreshGridLayout());
watch(pasteText, parsePaste);
watch(pasteHasHeader, parsePaste);
watch(open, (isOpen) => {
  if (isOpen) {
    window.addEventListener('keydown', handleShortcut);
    window.addEventListener('copy', handleClipboardCopy);
    window.addEventListener('paste', handleClipboardPaste);
    window.addEventListener('mouseup', handleSelectionMouseUp);
  } else {
    commitActiveCell();
    cancelSelectionFrame();
    isDraggingSelection.value = false;
    window.removeEventListener('keydown', handleShortcut);
    window.removeEventListener('copy', handleClipboardCopy);
    window.removeEventListener('paste', handleClipboardPaste);
    window.removeEventListener('mouseup', handleSelectionMouseUp);
  }
});
onBeforeUnmount(() => {
  cancelSelectionFrame();
  window.removeEventListener('keydown', handleShortcut);
  window.removeEventListener('copy', handleClipboardCopy);
  window.removeEventListener('paste', handleClipboardPaste);
  window.removeEventListener('mouseup', handleSelectionMouseUp);
});
</script>

<template>
  <Modal
    :cancel-button-props="{ disabled: submitting }"
    :closable="!submitting"
    :footer="null"
    :keyboard="false"
    :mask-closable="false"
    :open="open"
    :width="fullscreen ? '100vw' : 'min(1500px, calc(100vw - 32px))'"
    :wrap-class-name="
      fullscreen
        ? 'asset-spreadsheet-modal is-fullscreen'
        : 'asset-spreadsheet-modal'
    "
    @cancel="requestClose"
    @after-open-change="handleAfterOpenChange"
  >
    <template #title>
      <div class="asset-editor-title">
        <div class="asset-editor-title__text">{{ title }}</div>
      </div>
    </template>

    <div class="asset-spreadsheet flex min-h-0 flex-col gap-2">
      <div class="asset-editor-toolbar">
        <div class="asset-editor-toolbar__group">
          <Button
            :disabled="!undoStack.length || submitting"
            type="text"
            @click="undo"
          >
            <IconifyIcon icon="lucide:undo-2" />撤销
          </Button>
          <Button
            :disabled="!changedRows.length || submitting"
            type="text"
            @click="restoreInitial"
          >
            <IconifyIcon icon="lucide:rotate-ccw" />还原初始
          </Button>
        </div>

        <span class="asset-editor-toolbar__divider" aria-hidden="true"></span>

        <div class="asset-editor-toolbar__group">
          <Button :disabled="submitting" @click="pasteOpen = true">
            <IconifyIcon icon="lucide:clipboard-paste" />粘贴数据
          </Button>
          <Button
            v-if="allowCreate"
            :disabled="submitting || editorRows.length >= 1000"
            size="small"
            @click="addBlankRow"
          >
            <IconifyIcon icon="lucide:plus" />添加空白行
          </Button>
          <Button
            :disabled="!filteredRows.length"
            type="text"
            @click="copyRows"
          >
            <IconifyIcon icon="lucide:copy" />复制
          </Button>
          <Button
            :disabled="!filteredRows.length"
            type="text"
            @click="exportRows"
          >
            <IconifyIcon icon="lucide:download" />导出
          </Button>
        </div>

        <Button
          class="asset-editor-toolbar__fullscreen"
          type="text"
          @click="fullscreen = !fullscreen"
        >
          <IconifyIcon
            :icon="fullscreen ? 'lucide:minimize-2' : 'lucide:maximize-2'"
          />
          {{ fullscreen ? '还原' : '全屏' }}
        </Button>
      </div>

      <section
        class="asset-editor-control-bar"
        aria-label="筛选、排序与批量填充"
      >
        <div class="asset-editor-control-group asset-editor-filter-group">
          <div class="asset-editor-control-group__label">
            <IconifyIcon class="size-4" icon="lucide:list-filter" />
            <span>筛选与排序</span>
            <span class="text-muted-foreground text-xs"
              >{{ filteredRows.length }} 行</span
            >
          </div>
          <div
            v-for="condition in filterConditions"
            :key="condition.id"
            class="asset-editor-filter-condition"
          >
            <Select
              allow-clear
              class="asset-editor-filter-field"
              :get-popup-container="getEditorPopupContainer"
              :options="filterFieldOptions(condition.id)"
              placeholder="选择筛选列"
              :value="condition.fieldKey || undefined"
              @update:value="
                handleFilterFieldChange(condition, String($event ?? ''))
              "
            />
            <div class="asset-editor-filter-value">
              <DateRangePicker
                v-if="filterFieldFor(condition)?.type === 'date'"
                allow-clear
                class="w-full"
                format="YYYY-MM-DD"
                :get-popup-container="getEditorPopupContainer"
                :placeholder="['开始日期', '结束日期']"
                :value="condition.dateRange"
                @update:value="handleFilterDateRangeChange(condition, $event)"
              />
              <Select
                v-else-if="filterFieldFor(condition)?.type === 'select'"
                allow-clear
                class="w-full"
                :get-popup-container="getEditorPopupContainer"
                mode="multiple"
                :options="filterFieldFor(condition)?.options"
                option-filter-prop="label"
                placeholder="选择一个或多个值"
                show-search
                :value="normalizeFilterSelection(condition.value)"
                @update:value="
                  condition.value = normalizeFilterSelection($event)
                "
              />
              <StableUserSelect
                v-else-if="filterFieldFor(condition)?.type === 'user'"
                :get-popup-container="getEditorPopupContainer"
                :model-value="normalizeFilterSelection(condition.value)"
                multiple
                placeholder="选择一个或多个人员"
                @update:model-value="
                  condition.value = normalizeFilterSelection($event)
                "
              />
              <Input.TextArea
                v-else
                :auto-size="{ minRows: 1, maxRows: 3 }"
                allow-clear
                autocomplete="off"
                :disabled="!condition.fieldKey"
                :name="`asset-grid-filter-${condition.id}`"
                placeholder="空格或换行输入多个值"
                :value="Array.isArray(condition.value) ? '' : condition.value"
                @update:value="condition.value = $event"
              />
            </div>
            <Tooltip title="删除筛选条件">
              <Button
                :aria-label="`删除${filterFieldFor(condition)?.label ?? ''}筛选条件`"
                danger
                type="text"
                @click="removeFilterCondition(condition.id)"
              >
                <IconifyIcon icon="lucide:x" />
              </Button>
            </Tooltip>
          </div>
          <Button
            :disabled="!canAddFilterCondition"
            @click="addFilterCondition"
          >
            <IconifyIcon icon="lucide:plus" />添加筛选条件
          </Button>
          <span class="text-muted-foreground text-sm">排序</span>
          <Select
            v-model:value="sortField"
            allow-clear
            class="asset-editor-sort-field"
            :get-popup-container="getEditorPopupContainer"
            :options="
              fields.map((field) => ({ label: field.label, value: field.key }))
            "
            placeholder="选择列"
          />
          <Select
            v-model:value="sortDirection"
            class="asset-editor-sort-direction"
            :get-popup-container="getEditorPopupContainer"
            :options="[
              { label: '升序', value: 'asc' },
              { label: '降序', value: 'desc' },
            ]"
          />
        </div>
        <div class="asset-editor-control-group">
          <div class="asset-editor-control-group__label">
            <IconifyIcon class="size-4" icon="lucide:paint-bucket" />
            <span>批量填充</span>
          </div>
          <Select
            v-model:value="fillField"
            class="asset-editor-fill-field"
            :get-popup-container="getEditorPopupContainer"
            :options="
              editableFields.map((field) => ({
                label: field.label,
                value: field.key,
              }))
            "
            placeholder="选择可编辑列"
            @change="fillValue = ''"
          />
          <div class="asset-editor-fill-value">
            <Select
              v-if="fieldByKey.get(fillField)?.type === 'select'"
              v-model:value="fillValue"
              allow-clear
              class="w-full"
              :get-popup-container="getEditorPopupContainer"
              :mode="
                fieldByKey.get(fillField)?.multiple ? 'multiple' : undefined
              "
              :options="fieldByKey.get(fillField)?.options"
              option-filter-prop="label"
              show-search
              placeholder="选择填充值"
            />
            <StableUserSelect
              v-else-if="fieldByKey.get(fillField)?.type === 'user'"
              :get-popup-container="getEditorPopupContainer"
              :model-value="fillValue"
              :multiple="fieldByKey.get(fillField)?.multiple"
              @update:model-value="fillValue = $event ?? ''"
            />
            <DatePicker
              v-else-if="fieldByKey.get(fillField)?.type === 'date'"
              allow-clear
              class="w-full"
              :get-popup-container="getEditorPopupContainer"
              placeholder="选择填充日期"
              :value="dateValue(fillValue)"
              @update:value="handleFillDateValue"
            />
            <Input.Password
              v-else-if="fieldByKey.get(fillField)?.type === 'password'"
              autocomplete="new-password"
              data-1p-ignore="true"
              data-bwignore="true"
              data-lpignore="true"
              name="asset-grid-fill-secret"
              :value="Array.isArray(fillValue) ? '' : fillValue"
              @update:value="fillValue = $event"
            />
            <Input
              v-else-if="fieldByKey.get(fillField)?.type !== 'textarea'"
              autocomplete="off"
              name="asset-grid-fill-value"
              placeholder="输入填充值"
              :value="Array.isArray(fillValue) ? '' : fillValue"
              @update:value="fillValue = $event"
            />
            <Input.TextArea
              v-else
              :auto-size="{ minRows: 1, maxRows: 3 }"
              autocomplete="off"
              name="asset-grid-fill-notes"
              :value="Array.isArray(fillValue) ? '' : fillValue"
              @update:value="fillValue = $event"
            />
          </div>
          <Button
            :disabled="!fillField || !filteredRows.length"
            @click="applyBulkFill"
            >应用填充</Button
          >
        </div>
      </section>

      <div
        ref="gridContainerRef"
        class="asset-spreadsheet-grid-shell"
        :class="{ 'is-drag-selecting': isDraggingSelection }"
        tabindex="0"
      >
        <VxeGrid
          ref="gridRef"
          class="asset-spreadsheet-grid"
          :data="filteredRows"
          v-bind="gridOptions"
          @scroll="commitActiveCell"
        >
          <template #empty>
            <div class="asset-editor-empty">
              <IconifyIcon icon="lucide:table-properties" />
              <span>{{ gridEmptyText }}</span>
            </div>
          </template>
          <template #status="{ row }">
            <div class="asset-editor-row-status">
              <Tag v-if="rowStatus(row) === 'new'" color="success"
                ><IconifyIcon icon="lucide:plus" />新增</Tag
              >
              <Tag v-else-if="rowStatus(row) === 'modified'" color="processing"
                ><IconifyIcon icon="lucide:pencil" />已修改</Tag
              >
              <Tag v-else-if="rowStatus(row) === 'error'" color="error"
                ><IconifyIcon icon="lucide:circle-alert" />校验失败</Tag
              >
              <Tag v-else>未变更</Tag>
              <Button
                v-if="
                  row.__isNew &&
                  row.__origin === 'manual' &&
                  rowHasResettableChanges(row)
                "
                type="link"
                @mousedown.stop
                @click.stop="resetRow(row)"
              >
                还原
              </Button>
              <Button
                v-else-if="row.__isNew && row.__origin === 'manual'"
                danger
                type="link"
                @mousedown.stop
                @click.stop="removeManualRow(row)"
              >
                移除
              </Button>
              <Button
                v-else-if="rowHasResettableChanges(row)"
                type="link"
                @mousedown.stop
                @click.stop="resetRow(row)"
              >
                还原
              </Button>
            </div>
          </template>
          <template #fieldHeader="{ column }">
            <Tooltip :title="columnField(column.field).requiredWhen?.hint">
              <span class="asset-editor-column-header">
                <span
                  v-if="hasRequiredIndicator(columnField(column.field))"
                  class="asset-editor-column-header__required"
                  aria-hidden="true"
                  >*</span
                >
                <span>{{ columnField(column.field).label }}</span>
                <IconifyIcon
                  v-if="columnField(column.field).requiredWhen"
                  class="text-muted-foreground size-3.5"
                  icon="lucide:circle-help"
                />
                <span v-if="columnField(column.field).required" class="sr-only"
                  >必填</span
                >
                <span
                  v-else-if="columnField(column.field).requiredWhen"
                  class="sr-only"
                  >{{ columnField(column.field).requiredWhen?.hint }}</span
                >
              </span>
            </Tooltip>
          </template>
          <template #cell="{ column, row }">
            <div
              class="asset-spreadsheet-cell"
              :class="{
                'asset-spreadsheet-cell--selected': isCellSelected(
                  row,
                  columnField(column.field).key,
                ),
              }"
              @mousedown.capture="
                handleSelectionMouseDown(
                  $event,
                  row,
                  columnField(column.field).key,
                )
              "
              @mouseenter="
                handleSelectionMouseEnter(row, columnField(column.field).key)
              "
            >
              <div
                v-memo="[
                  row.__cellRevisions[columnField(column.field).key] ?? 0,
                  isActiveCell(row, columnField(column.field).key),
                ]"
                class="asset-spreadsheet-cell__content"
              >
                <template
                  v-if="isFieldEditable(row, columnField(column.field))"
                >
                  <DatePicker
                    v-if="
                      isActiveCell(row, columnField(column.field).key) &&
                      columnField(column.field).type === 'date'
                    "
                    ref="activeEditorRef"
                    allow-clear
                    class="asset-spreadsheet-control w-full"
                    :class="{
                      'spreadsheet-cell--dirty': isDirtyCell(row, column.field),
                      'spreadsheet-cell--error': cellError(row, column.field),
                    }"
                    format="YYYY-MM-DD"
                    :get-popup-container="getEditorPopupContainer"
                    :open="activeEditorOpen"
                    :placeholder="
                      columnField(column.field).placeholder ?? '选择日期'
                    "
                    :value="dateValue(activeDraft)"
                    @open-change="handleActiveEditorOpenChange"
                    @update:value="handleActiveDateValue"
                  />
                  <Select
                    v-else-if="
                      isActiveCell(row, columnField(column.field).key) &&
                      columnField(column.field).type === 'select'
                    "
                    ref="activeEditorRef"
                    allow-clear
                    class="asset-spreadsheet-control w-full"
                    :class="{
                      'spreadsheet-cell--dirty': isDirtyCell(row, column.field),
                      'spreadsheet-cell--error': cellError(row, column.field),
                    }"
                    :get-popup-container="getEditorPopupContainer"
                    :mode="
                      columnField(column.field).multiple
                        ? 'multiple'
                        : undefined
                    "
                    :options="columnField(column.field).options"
                    :open="activeEditorOpen"
                    :placeholder="columnField(column.field).placeholder"
                    :value="activeDraft"
                    option-filter-prop="label"
                    show-search
                    @dropdown-visible-change="handleActiveEditorOpenChange"
                    @update:value="handleActiveValue"
                  />
                  <StableUserSelect
                    v-else-if="
                      isActiveCell(row, columnField(column.field).key) &&
                      columnField(column.field).type === 'user'
                    "
                    ref="activeEditorRef"
                    class="asset-spreadsheet-control w-full"
                    :class="{
                      'spreadsheet-cell--dirty': isDirtyCell(row, column.field),
                      'spreadsheet-cell--error': cellError(row, column.field),
                    }"
                    :get-popup-container="getEditorPopupContainer"
                    :model-value="activeDraft"
                    :multiple="columnField(column.field).multiple"
                    :open="activeEditorOpen"
                    :placeholder="columnField(column.field).placeholder"
                    @open-change="handleActiveEditorOpenChange"
                    @update:model-value="handleActiveValue"
                  />
                  <Tooltip
                    v-else-if="isActiveCell(row, columnField(column.field).key)"
                    :title="cellError(row, column.field)"
                  >
                    <Input.Password
                      v-if="columnField(column.field).sensitive"
                      ref="activeEditorRef"
                      autocomplete="new-password"
                      class="asset-spreadsheet-control w-full"
                      :class="{
                        'spreadsheet-cell--dirty': isDirtyCell(
                          row,
                          column.field,
                        ),
                        'spreadsheet-cell--error': cellError(row, column.field),
                      }"
                      data-1p-ignore="true"
                      data-bwignore="true"
                      data-lpignore="true"
                      :name="editorControlName(row, columnField(column.field))"
                      placeholder="已配置；输入新值将覆盖"
                      :value="Array.isArray(activeDraft) ? '' : activeDraft"
                      @update:value="handleActiveValue"
                      @blur="commitActiveCell"
                    />
                    <Input.TextArea
                      v-else-if="columnField(column.field).type === 'textarea'"
                      ref="activeEditorRef"
                      autocomplete="off"
                      class="asset-spreadsheet-control w-full"
                      :class="{
                        'spreadsheet-cell--dirty': isDirtyCell(
                          row,
                          column.field,
                        ),
                        'spreadsheet-cell--error': cellError(row, column.field),
                      }"
                      :name="editorControlName(row, columnField(column.field))"
                      :placeholder="columnField(column.field).placeholder"
                      :rows="1"
                      :value="Array.isArray(activeDraft) ? '' : activeDraft"
                      @update:value="handleActiveValue"
                      @blur="commitActiveCell"
                    />
                    <Input
                      v-else
                      ref="activeEditorRef"
                      autocomplete="off"
                      class="asset-spreadsheet-control w-full"
                      :class="{
                        'spreadsheet-cell--dirty': isDirtyCell(
                          row,
                          column.field,
                        ),
                        'spreadsheet-cell--error': cellError(row, column.field),
                      }"
                      :name="editorControlName(row, columnField(column.field))"
                      :placeholder="columnField(column.field).placeholder"
                      :value="Array.isArray(activeDraft) ? '' : activeDraft"
                      @update:value="handleActiveValue"
                      @blur="commitActiveCell"
                    />
                  </Tooltip>
                  <button
                    v-else
                    type="button"
                    class="asset-spreadsheet-cell__display"
                    :class="{
                      'spreadsheet-cell--dirty': isDirtyCell(row, column.field),
                      'spreadsheet-cell--error': cellError(row, column.field),
                    }"
                    :aria-label="`编辑${columnField(column.field).label}`"
                    :title="
                      cellError(row, column.field) ||
                      cellDisplayText(row, column.field)
                    "
                    @click="activateCell(row, columnField(column.field))"
                  >
                    <span class="asset-spreadsheet-cell__text">{{
                      cellDisplayText(row, column.field)
                    }}</span>
                  </button>
                </template>
                <div v-else class="spreadsheet-cell--readonly">
                  <span
                    class="asset-spreadsheet-cell__text"
                    :title="cellDisplayText(row, column.field)"
                    >{{ cellDisplayText(row, column.field) }}</span
                  >
                </div>
              </div>
            </div>
          </template>
        </VxeGrid>
      </div>

      <div class="asset-editor-footer">
        <div class="asset-editor-statistics">
          <span class="text-sm font-medium">统计</span>
          <Select
            v-model:value="statisticField"
            allow-clear
            class="w-44"
            :get-popup-container="getEditorPopupContainer"
            :options="
              nonSensitiveFields.map((field) => ({
                label: field.label,
                value: field.key,
              }))
            "
            placeholder="选择统计列"
          />
          <span class="text-muted-foreground text-sm">{{
            statistics || '选择列后显示当前筛选结果统计'
          }}</span>
        </div>
        <div class="asset-editor-actions">
          <span class="asset-editor-change-summary" aria-live="polite">{{
            changeSummary
          }}</span>
          <Button :disabled="submitting" @click="requestClose">取消</Button>
          <Button
            :disabled="!changedRows.length"
            :loading="submitting"
            type="primary"
            @click="submit"
            >保存修改</Button
          >
        </div>
      </div>
    </div>
  </Modal>

  <Modal
    v-model:open="pasteOpen"
    :confirm-loading="pasteResolving"
    :ok-button-props="{ disabled: !pastePreview.length || pasteErrorCount > 0 }"
    ok-text="确认暂存"
    title="粘贴 Excel / TSV 数据"
    width="min(1100px, calc(100vw - 32px))"
    @ok="confirmPaste"
  >
    <div class="flex flex-col gap-3">
      <Alert
        :message="
          allowCreate
            ? `按${identifierField?.label ?? '唯一标识'}匹配；未匹配行将暂存为新增。`
            : `按${identifierField?.label ?? '唯一标识'}匹配；当前类型只能修改已有数据。`
        "
        show-icon
        type="info"
      />
      <div class="flex items-center gap-2">
        <Button
          :type="pasteHasHeader ? 'primary' : 'default'"
          @click="setPasteHeaderMode(true)"
          >包含表头</Button
        ><Button
          :type="!pasteHasHeader ? 'primary' : 'default'"
          @click="setPasteHeaderMode(false)"
          >无表头</Button
        ><span class="text-muted-foreground text-sm"
          >无表头时按下方显示的当前数据列顺序匹配</span
        >
      </div>
      <Input.TextArea
        v-model:value="pasteText"
        :auto-size="{ minRows: 8, maxRows: 14 }"
        :placeholder="
          pasteHasHeader
            ? '在此粘贴 Excel 单元格内容'
            : '请在参考表头下一行粘贴 Excel 单元格内容'
        "
      />
      <Alert
        v-if="ignoredPasteHeaders.length"
        :message="`已忽略无关列：${ignoredPasteHeaders.join('、')}`"
        show-icon
        type="info"
      />
      <Alert
        v-if="pasteErrorCount"
        :message="`发现 ${pasteErrorCount} 个问题，修正后才能确认`"
        show-icon
        type="error"
      />
      <div
        v-if="pastePreview.length"
        class="max-h-64 overflow-auto rounded-lg border"
      >
        <div
          v-for="row in pastePreview.slice(0, 20)"
          :key="row.line"
          class="border-border flex gap-3 border-b px-3 py-2 text-sm last:border-b-0"
        >
          <span class="w-14 shrink-0">第 {{ row.line }} 行</span
          ><span v-if="row.errors.length" class="text-destructive">{{
            row.errors.join('；')
          }}</span
          ><span v-else class="text-success">{{
            row.target ? '匹配已有行，将覆盖修改' : '将新增暂存行'
          }}</span>
        </div>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.asset-editor-title {
  min-width: 0;
  padding-right: 40px;
}

.asset-editor-title__text {
  overflow: hidden;
  color: hsl(var(--foreground));
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-editor-toolbar__divider {
  width: 1px;
  background-color: hsl(var(--border));
}

.asset-editor-toolbar {
  display: flex;
  min-height: 40px;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background-color: hsl(var(--muted) / 0.3);
  padding: 4px 8px;
}

.asset-editor-toolbar__group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
}

.asset-editor-toolbar__divider {
  height: 24px;
  margin: 0 4px;
}

.asset-editor-toolbar__fullscreen {
  margin-left: auto;
}

.asset-editor-control-bar {
  display: flex;
  overflow: visible;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background-color: hsl(var(--muted) / 0.3);
  padding: 8px 12px;
}

.asset-editor-control-group {
  display: flex;
  min-width: max-content;
  align-items: center;
  gap: 8px;
}

.asset-editor-filter-group {
  min-width: min(100%, 640px);
  flex: 1 1 640px;
  flex-wrap: wrap;
}

.asset-editor-filter-condition {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
}

.asset-editor-control-group__label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.asset-editor-filter-field,
.asset-editor-sort-field,
.asset-editor-fill-field {
  width: 128px;
}

.asset-editor-sort-direction {
  width: 88px;
}

.asset-editor-filter-value {
  width: 220px;
}

.asset-editor-fill-value {
  width: 180px;
}

.asset-editor-filter-value > *,
.asset-editor-fill-value > * {
  width: 100%;
}

.asset-spreadsheet-grid-shell {
  min-width: 0;
  outline: none;
}

.asset-spreadsheet-grid-shell:focus-visible {
  border-radius: 4px;
  box-shadow: 0 0 0 2px hsl(var(--ring) / 0.25);
}

.asset-spreadsheet-grid-shell.is-drag-selecting {
  user-select: none;
}

.asset-spreadsheet-cell {
  position: relative;
  width: 100%;
  min-width: 0;
}

.asset-spreadsheet-cell__content {
  width: 100%;
  min-width: 0;
}

.asset-spreadsheet-cell__display {
  display: flex;
  min-height: 38px;
  width: 100%;
  min-width: 0;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: hsl(var(--foreground));
  cursor: text;
  padding: 0 10px;
  text-align: left;
}

.asset-spreadsheet-cell__display:hover {
  background: hsl(var(--muted) / 0.55);
}

.asset-spreadsheet-cell__display:focus-visible {
  border-color: hsl(var(--ring));
  box-shadow: 0 0 0 2px hsl(var(--ring) / 0.18);
  outline: none;
}

.asset-spreadsheet-cell__display > *,
.spreadsheet-cell--readonly > * {
  width: 100%;
  min-width: 0;
}

.asset-spreadsheet-cell__text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.asset-spreadsheet-cell__display.spreadsheet-cell--dirty {
  border-color: hsl(var(--primary));
  background: hsl(var(--primary) / 0.06);
}

.asset-spreadsheet-cell__display.spreadsheet-cell--error {
  border-color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 0.05);
}

.asset-spreadsheet-cell--selected {
  isolation: isolate;
}

.asset-spreadsheet-cell--selected::after {
  position: absolute;
  z-index: 2;
  inset: 1px;
  border: 2px solid hsl(var(--primary));
  border-radius: 4px;
  content: '';
  pointer-events: none;
}

.asset-editor-empty {
  display: flex;
  min-height: 160px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: hsl(var(--muted-foreground));
  font-size: 14px;
}

.asset-editor-empty svg {
  width: 24px;
  height: 24px;
}

.asset-editor-footer {
  display: flex;
  min-height: 56px;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  border-top: 1px solid hsl(var(--border));
  background-color: hsl(var(--card));
  padding-top: 12px;
}

.asset-editor-statistics,
.asset-editor-actions {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.asset-editor-actions {
  margin-left: auto;
}

.asset-editor-change-summary {
  color: hsl(var(--foreground));
  font-size: 13px;
  font-weight: 500;
}

.asset-editor-row-status {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.asset-editor-column-header {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 4px;
}

.asset-editor-column-header__required {
  color: hsl(var(--destructive));
  font-weight: 600;
}

:deep(.asset-spreadsheet-grid .vxe-table--fixed-left-wrapper),
:deep(
  .asset-spreadsheet-grid .vxe-table--fixed-left-wrapper .vxe-header--column
),
:deep(
  .asset-spreadsheet-grid .vxe-table--fixed-left-wrapper .vxe-body--column
) {
  background-color: hsl(var(--card));
}

:deep(.asset-spreadsheet-grid .vxe-table--fixed-left-wrapper::after) {
  position: absolute;
  z-index: 3;
  top: 0;
  right: 0;
  bottom: 0;
  width: 1px;
  background-color: hsl(var(--border));
  content: '';
  pointer-events: none;
}

.spreadsheet-cell--readonly {
  display: flex;
  min-height: 38px;
  min-width: 0;
  align-items: center;
  border-radius: 6px;
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  padding: 0 10px;
}

:deep(.asset-spreadsheet-control) {
  width: 100%;
}

:deep(.asset-spreadsheet-grid .vxe-body--column.col--selected) {
  box-shadow: none;
}

@media (max-width: 900px) {
  .asset-editor-toolbar__divider {
    display: none;
  }

  .asset-editor-toolbar__fullscreen {
    margin-left: 0;
  }

  .asset-editor-footer,
  .asset-editor-statistics,
  .asset-editor-actions {
    width: 100%;
  }

  .asset-editor-actions {
    justify-content: flex-end;
    margin-left: 0;
  }
}

:global(.asset-spreadsheet-modal.is-fullscreen .asset-spreadsheet) {
  width: 100%;
  min-height: 0;
  flex: 1 1 auto;
}

:global(.asset-spreadsheet-modal.is-fullscreen .asset-editor-toolbar),
:global(.asset-spreadsheet-modal.is-fullscreen .asset-editor-control-bar),
:global(.asset-spreadsheet-modal.is-fullscreen .asset-editor-footer) {
  flex: 0 0 auto;
}

:global(.asset-spreadsheet-modal.is-fullscreen .asset-spreadsheet-grid-shell) {
  min-height: 0;
  flex: 1 1 auto;
}

:global(.asset-spreadsheet-modal.is-fullscreen .asset-spreadsheet-grid) {
  height: 100%;
}
</style>
