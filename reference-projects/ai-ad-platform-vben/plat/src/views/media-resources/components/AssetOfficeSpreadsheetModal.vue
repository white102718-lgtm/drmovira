<script lang="ts" setup>
import type {
  AssetBatchEditField,
  AssetBatchEditSubmission,
  AssetBatchEditValue,
  AssetSpreadsheetSourceRow,
} from './AssetBatchEditModal.vue';

import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Alert, Button, message, Modal, Spin } from 'ant-design-vue';
import dayjs from 'dayjs';
import {
  createUniver,
  DataValidationRenderMode,
  LifecycleStages,
  LocaleType,
  mergeLocales,
} from '@univerjs/presets';
import {
  AUTO_FILL_APPLY_TYPE,
  AutoFillCommand,
  IAutoFillService,
  IRenderManagerService,
  ISheetSelectionRenderService,
  UniverSheetsCorePreset,
} from '@univerjs/preset-sheets-core';
import sheetsCoreZhCN from '@univerjs/preset-sheets-core/locales/zh-CN';
import { UniverSheetsConditionalFormattingPreset } from '@univerjs/preset-sheets-conditional-formatting';
import sheetsConditionalFormattingZhCN from '@univerjs/preset-sheets-conditional-formatting/locales/zh-CN';
import { UniverSheetsDataValidationPreset } from '@univerjs/preset-sheets-data-validation';
import sheetsDataValidationZhCN from '@univerjs/preset-sheets-data-validation/locales/zh-CN';
import { UniverSheetsFilterPreset } from '@univerjs/preset-sheets-filter';
import sheetsFilterZhCN from '@univerjs/preset-sheets-filter/locales/zh-CN';
import { UniverSheetsFindReplacePreset } from '@univerjs/preset-sheets-find-replace';
import sheetsFindReplaceZhCN from '@univerjs/preset-sheets-find-replace/locales/zh-CN';
import { UniverSheetsSortPreset } from '@univerjs/preset-sheets-sort';
import sheetsSortZhCN from '@univerjs/preset-sheets-sort/locales/zh-CN';
import { UniverSheetsTablePreset } from '@univerjs/preset-sheets-table';
import sheetsTableZhCN from '@univerjs/preset-sheets-table/locales/zh-CN';

import '@univerjs/preset-sheets-conditional-formatting/lib/index.css';
import '@univerjs/preset-sheets-core/lib/index.css';
import '@univerjs/preset-sheets-data-validation/lib/index.css';
import '@univerjs/preset-sheets-filter/lib/index.css';
import '@univerjs/preset-sheets-find-replace/lib/index.css';
import '@univerjs/preset-sheets-sort/lib/index.css';
import '@univerjs/preset-sheets-table/lib/index.css';

import { getSharedOrganizationUsers } from '../../components/organization-options-cache';

const TECHNICAL_ID_HEADER = '__ADPULSE_ASSET_RECORD_ID__';
const AUTOFILL_HANDLE_SIZE = 8;

type UniverRuntime = ReturnType<typeof createUniver>;
type OrganizationUser = Awaited<
  ReturnType<typeof getSharedOrganizationUsers>
>[number];

interface DisplayOption {
  label: string;
  value: string;
}

interface ValidationIssue {
  columnIndex: number;
  message: string;
  rowIndex: number;
}

interface QuickUserEntry {
  label: string;
  recognized: boolean;
}

interface QuickUserEditorState {
  columnIndex: number;
  entries: QuickUserEntry[];
  rowIndex: number;
}

interface QuickUserCloseHitbox {
  bottom: number;
  columnIndex: number;
  entryIndex: number;
  left: number;
  right: number;
  rowIndex: number;
  top: number;
}

interface WorksheetCapacityOptions {
  allowCreate: boolean;
  currentColumnCount: number;
  currentRowCount: number;
  dataRowCount: number;
  fieldCount: number;
}

function calculateWorksheetCapacity({
  allowCreate,
  currentColumnCount,
  currentRowCount,
  dataRowCount,
  fieldCount,
}: WorksheetCapacityOptions) {
  return {
    columnCount: Math.max(currentColumnCount, fieldCount + 1),
    rowCount: Math.max(
      currentRowCount,
      dataRowCount + 1 + (allowCreate ? 1 : 0),
    ),
  };
}

const props = withDefaults(
  defineProps<{
    allowCreate?: boolean;
    fields: AssetBatchEditField[];
    identifierKey: string;
    loading?: boolean;
    rows: AssetSpreadsheetSourceRow[];
    statusHint?: string;
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
const spreadsheetContainer = ref<HTMLElement>();
const initializing = ref(false);
const dirty = ref(false);
const validationIssues = ref<ValidationIssue[]>([]);
const organizationUsers = ref<OrganizationUser[]>([]);
const quickUserEditor = ref<QuickUserEditorState>();
let runtime: UniverRuntime | undefined;
let autofillCopyModeDisposable: { dispose: () => void } | undefined;
let autofillHandleRefreshFrame: number | undefined;
let autofillHandleSubscriptions: Array<{ unsubscribe: () => void }> = [];
let lifecycleReadyDisposable: { dispose: () => void } | undefined;
let selectionChangedDisposable: { dispose: () => void } | undefined;
let valueChangedDisposable: { dispose: () => void } | undefined;
let quickUserCellRenderDisposable: { dispose: () => void } | undefined;
let quickUserCloseHitboxes: QuickUserCloseHitbox[] = [];
let pendingQuickUserRemoval: QuickUserCloseHitbox | undefined;

const identifierField = computed(() =>
  props.fields.find((field) => field.key === props.identifierKey),
);
function isQuickUserField(field: AssetBatchEditField) {
  return (
    field.type === 'user' &&
    (field.key === 'usageUsers' || field.key === 'userIds')
  );
}

const quickUserField = computed(() => {
  const columnIndex = props.fields.findIndex(isQuickUserField);
  return columnIndex >= 0
    ? { columnIndex, field: props.fields[columnIndex]! }
    : undefined;
});
const originalRowsById = computed(
  () =>
    new Map(props.rows.filter((row) => row.id).map((row) => [row.id!, row])),
);
const originalRowsByIdentifier = computed(() => {
  const rows = new Map<string, AssetSpreadsheetSourceRow>();
  for (const row of props.rows) {
    const identifier = scalarValue(row.values[props.identifierKey]).trim();
    if (identifier) rows.set(identifier, row);
  }
  return rows;
});
const validationSummary = computed(() => {
  if (!validationIssues.value.length) return '';
  const preview = validationIssues.value
    .slice(0, 5)
    .map((issue) => `第 ${issue.rowIndex + 1} 行：${issue.message}`)
    .join('；');
  const remaining = validationIssues.value.length - 5;
  return `${preview}${remaining > 0 ? `；另有 ${remaining} 项错误` : ''}`;
});

function cloneValue(
  value: AssetBatchEditValue | undefined,
): AssetBatchEditValue {
  return Array.isArray(value) ? [...value] : (value ?? '');
}

function scalarValue(value: AssetBatchEditValue | undefined) {
  return Array.isArray(value) ? value.join('、') : String(value ?? '');
}

function equalValue(
  left: AssetBatchEditValue | undefined,
  right: AssetBatchEditValue | undefined,
) {
  return JSON.stringify(cloneValue(left)) === JSON.stringify(cloneValue(right));
}

function hasValue(value: AssetBatchEditValue | undefined) {
  return Array.isArray(value)
    ? value.length > 0
    : String(value ?? '').trim().length > 0;
}

/** 兼容 Univer 多选 JSON 值和用户手工粘贴的分隔文本。 */
function splitMultipleValue(value: unknown) {
  const normalize = (items: unknown[]) => [
    ...new Set(items.map((item) => String(item ?? '').trim()).filter(Boolean)),
  ];
  if (Array.isArray(value)) return normalize(value);

  const text = String(value ?? '').trim();
  if (!text) return [];
  if (text.startsWith('[') && text.endsWith(']')) {
    try {
      const parsed: unknown = JSON.parse(text);
      if (Array.isArray(parsed)) return normalize(parsed);
    } catch {
      // 非法 JSON 继续按用户手工粘贴的普通文本处理，保留既有兼容能力。
    }
  }
  return normalize(text.split(/[、,，;；\n]/));
}

function uniqueDisplayOptions(options: DisplayOption[]) {
  const labelCounts = new Map<string, number>();
  for (const option of options) {
    labelCounts.set(option.label, (labelCounts.get(option.label) ?? 0) + 1);
  }
  return options.map((option) => ({
    ...option,
    label:
      (labelCounts.get(option.label) ?? 0) > 1
        ? `${option.label}（${option.value.slice(-8)}）`
        : option.label,
  }));
}

function userOptions() {
  return uniqueDisplayOptions(
    organizationUsers.value.map((user) => ({
      label: user.displayName || user.realName || user.username || user.id,
      value: user.id,
    })),
  );
}

function fieldOptions(field: AssetBatchEditField) {
  return uniqueDisplayOptions(
    field.type === 'user' ? userOptions() : (field.options ?? []),
  );
}

function refreshQuickUserCellRenderer() {
  const currentRuntime = runtime;
  const workbook = currentRuntime?.univerAPI.getActiveWorkbook();
  if (!currentRuntime || !workbook) return;

  const render = currentRuntime.univer
    .__getInjector()
    .get(IRenderManagerService)
    .getRenderById(workbook.getId());
  render?.mainComponent?.makeDirty(true);
  render?.scene.makeDirty(true);
}

function refreshQuickUserEditor() {
  const activeEditor = quickUserEditor.value;
  const userField = quickUserField.value;
  const worksheet = runtime?.univerAPI.getActiveWorkbook()?.getActiveSheet();
  if (!activeEditor || !userField || !worksheet) return;

  const rawValue = worksheet
    .getRange(activeEditor.rowIndex, activeEditor.columnIndex, 1, 1)
    .getValue();
  const recognizedLabels = new Set(
    fieldOptions(userField.field).map((option) => option.label),
  );
  quickUserEditor.value = {
    ...activeEditor,
    entries: splitMultipleValue(rawValue).map((label) => ({
      label,
      recognized: recognizedLabels.has(label),
    })),
  };
  refreshQuickUserCellRenderer();
}

function syncQuickUserEditorSelection(
  selections: Array<{
    endColumn: number;
    endRow: number;
    startColumn: number;
    startRow: number;
  }>,
) {
  quickUserEditor.value = undefined;
  quickUserCloseHitboxes = [];
  pendingQuickUserRemoval = undefined;
  refreshQuickUserCellRenderer();
  const userField = quickUserField.value;
  const worksheet = runtime?.univerAPI.getActiveWorkbook()?.getActiveSheet();
  if (!userField || !worksheet || selections.length !== 1) return;

  const [selection] = selections;
  if (
    !selection ||
    selection.startRow !== selection.endRow ||
    selection.startColumn !== selection.endColumn ||
    selection.startRow < 1 ||
    selection.startColumn !== userField.columnIndex
  ) {
    return;
  }

  const identifierColumnIndex = props.fields.findIndex(
    (field) => field.key === props.identifierKey,
  );
  if (identifierColumnIndex < 0) return;
  const accountIdentifier = String(
    worksheet
      .getRange(selection.startRow, identifierColumnIndex, 1, 1)
      .getValue() ?? '',
  ).trim();
  if (!accountIdentifier) return;

  quickUserEditor.value = {
    columnIndex: selection.startColumn,
    entries: [],
    rowIndex: selection.startRow,
  };
  refreshQuickUserEditor();
}

function writeQuickUserEntries(entries: QuickUserEntry[]) {
  const activeEditor = quickUserEditor.value;
  const worksheet = runtime?.univerAPI.getActiveWorkbook()?.getActiveSheet();
  if (!activeEditor || !worksheet) return;

  const labels = entries.map((entry) => entry.label);
  const range = worksheet.getRange(
    activeEditor.rowIndex,
    activeEditor.columnIndex,
    1,
    1,
  );
  if (labels.length > 0) {
    range.setValue(JSON.stringify(labels));
  } else {
    range.clearContent();
  }
  dirty.value = true;
  validationIssues.value = [];
  refreshQuickUserEditor();
}

function removeQuickUser(entryIndex: number) {
  const entries = quickUserEditor.value?.entries;
  if (!entries) return;
  writeQuickUserEntries(entries.filter((_, index) => index !== entryIndex));
}

function roundedRectPath(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const safeRadius = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + safeRadius, y);
  context.lineTo(x + width - safeRadius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + safeRadius);
  context.lineTo(x + width, y + height - safeRadius);
  context.quadraticCurveTo(
    x + width,
    y + height,
    x + width - safeRadius,
    y + height,
  );
  context.lineTo(x + safeRadius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - safeRadius);
  context.lineTo(x, y + safeRadius);
  context.quadraticCurveTo(x, y, x + safeRadius, y);
  context.closePath();
}

function fitCanvasText(
  context: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
) {
  if (context.measureText(text).width <= maxWidth) return text;
  let end = text.length;
  while (end > 0) {
    const candidate = `${text.slice(0, end)}…`;
    if (context.measureText(candidate).width <= maxWidth) return candidate;
    end -= 1;
  }
  return '';
}

function registerQuickUserCellRenderer(currentRuntime: UniverRuntime) {
  quickUserCellRenderDisposable?.dispose();
  quickUserCellRenderDisposable = currentRuntime.univerAPI
    .getSheetHooks()
    .onCellRender(
      [
        {
          zIndex: 100,
          drawWith(context, info, skeleton) {
            const editor = quickUserEditor.value;
            if (
              !editor ||
              editor.rowIndex !== info.row ||
              editor.columnIndex !== info.col ||
              editor.entries.length === 0
            ) {
              return;
            }

            const { endX, endY, startX, startY } = info.primaryWithCoord;
            const contentLeft = startX + 6;
            const contentRight = endX - 16;
            const contentWidth = Math.max(0, contentRight - contentLeft);
            if (contentWidth <= 0) return;
            const hitboxOffsetX = Number(skeleton?.rowHeaderWidth ?? 0);
            const hitboxOffsetY = Number(skeleton?.columnHeaderHeight ?? 0);

            context.save();
            context.beginPath();
            context.rect(
              startX + 1,
              startY + 1,
              Math.max(0, contentRight - startX - 1),
              Math.max(0, endY - startY - 2),
            );
            context.clip();
            context.fillStyle = '#ffffff';
            context.fillRect(
              startX + 1,
              startY + 1,
              Math.max(0, contentRight - startX - 1),
              Math.max(0, endY - startY - 2),
            );
            context.font = '12px Arial';
            context.textBaseline = 'middle';

            const chipHeight = 20;
            const horizontalGap = 4;
            const verticalGap = 4;
            const closeAreaWidth = 24;
            const closeHitSlop = 4;
            const closeIconHalfSize = 4;
            const chipPaddingLeft = 6;
            const chipPaddingRight = 4;
            const layouts: Array<{
              entry: QuickUserEntry;
              entryIndex: number;
              height: number;
              width: number;
              x: number;
              y: number;
            }> = [];
            let cursorX = contentLeft;
            let cursorY = startY + 4;

            for (const [entryIndex, entry] of editor.entries.entries()) {
              const measuredWidth = Math.ceil(
                context.measureText(entry.label).width,
              );
              const chipWidth = Math.min(
                contentWidth,
                measuredWidth +
                  chipPaddingLeft +
                  closeAreaWidth +
                  chipPaddingRight,
              );
              if (cursorX > contentLeft && cursorX + chipWidth > contentRight) {
                cursorX = contentLeft;
                cursorY += chipHeight + verticalGap;
              }
              layouts.push({
                entry,
                entryIndex,
                height: chipHeight,
                width: chipWidth,
                x: cursorX,
                y: cursorY,
              });
              cursorX += chipWidth + horizontalGap;
            }

            quickUserCloseHitboxes = [];
            for (const layout of layouts) {
              const { entry, entryIndex, height, width, x, y } = layout;
              if (y + height > endY - 2) break;
              roundedRectPath(context, x, y, width, height, 8);
              context.fillStyle = entry.recognized ? '#e6f4ff' : '#fff7e6';
              context.fill();
              context.strokeStyle = entry.recognized ? '#91caff' : '#ffd591';
              context.lineWidth = 1;
              context.stroke();

              const textMaxWidth = Math.max(
                0,
                width - chipPaddingLeft - closeAreaWidth - chipPaddingRight,
              );
              context.fillStyle = entry.recognized ? '#0958d9' : '#ad4e00';
              context.fillText(
                fitCanvasText(context, entry.label, textMaxWidth),
                x + chipPaddingLeft,
                y + height / 2,
              );

              const closeCenterX = x + width - closeAreaWidth / 2 - 2;
              const closeCenterY = y + height / 2;
              context.strokeStyle = entry.recognized ? '#1677ff' : '#d46b08';
              context.lineWidth = 1.5;
              context.beginPath();
              context.moveTo(
                closeCenterX - closeIconHalfSize,
                closeCenterY - closeIconHalfSize,
              );
              context.lineTo(
                closeCenterX + closeIconHalfSize,
                closeCenterY + closeIconHalfSize,
              );
              context.moveTo(
                closeCenterX + closeIconHalfSize,
                closeCenterY - closeIconHalfSize,
              );
              context.lineTo(
                closeCenterX - closeIconHalfSize,
                closeCenterY + closeIconHalfSize,
              );
              context.stroke();

              quickUserCloseHitboxes.push({
                bottom: y + height + closeHitSlop + hitboxOffsetY,
                columnIndex: info.col,
                entryIndex,
                left: x + width - closeAreaWidth - closeHitSlop + hitboxOffsetX,
                right: x + width + closeHitSlop + hitboxOffsetX,
                rowIndex: info.row,
                top: y - closeHitSlop + hitboxOffsetY,
              });
            }
            context.restore();
          },
          isHit(position, info) {
            if (props.submitting) return false;
            const editor = quickUserEditor.value;
            if (
              !editor ||
              editor.rowIndex !== info.row ||
              editor.columnIndex !== info.col
            ) {
              pendingQuickUserRemoval = undefined;
              return false;
            }
            pendingQuickUserRemoval = quickUserCloseHitboxes.find(
              (hitbox) =>
                hitbox.rowIndex === info.row &&
                hitbox.columnIndex === info.col &&
                position.x >= hitbox.left &&
                position.x <= hitbox.right &&
                position.y >= hitbox.top &&
                position.y <= hitbox.bottom,
            );
            return Boolean(pendingQuickUserRemoval);
          },
          onPointerDown(_info, eventState) {
            const hitbox = pendingQuickUserRemoval;
            pendingQuickUserRemoval = undefined;
            if (!hitbox) return;
            eventState?.stopPropagation?.();
            eventState?.preventDefault?.();
            removeQuickUser(hitbox.entryIndex);
          },
        },
      ],
      undefined,
      100,
    );
}

function optionMaps(field: AssetBatchEditField) {
  const options = fieldOptions(field);
  return {
    displayByValue: new Map(
      options.map((option) => [option.value, option.label]),
    ),
    valueByDisplay: new Map(
      options.flatMap((option) => [
        [option.label, option.value] as const,
        [option.value, option.value] as const,
      ]),
    ),
  };
}

function displayCellValue(
  source: AssetSpreadsheetSourceRow,
  field: AssetBatchEditField,
) {
  if (field.sensitive && source.id) return '';
  const value = source.values[field.key];
  if (field.type !== 'select' && field.type !== 'user') {
    return scalarValue(value);
  }
  const { displayByValue } = optionMaps(field);
  const values = Array.isArray(value) ? value : value ? [value] : [];
  const displayValues = values.map((item) => displayByValue.get(item) ?? item);
  if (displayValues.length === 0) return '';

  // Univer 的多选数据验证按序列化数组解析单元格值，分隔文本会被误判为范围外输入。
  return field.multiple
    ? JSON.stringify(displayValues)
    : displayValues.join('、');
}

function parseCellValue(
  rawValue: unknown,
  field: AssetBatchEditField,
): { error?: string; value: AssetBatchEditValue } {
  const text = String(rawValue ?? '').trim();
  if (field.type === 'date') {
    if (!text) return { value: '' };
    const parsed = dayjs(text);
    return parsed.isValid()
      ? { value: parsed.format('YYYY-MM-DD') }
      : { error: `${field.label}不是有效日期`, value: '' };
  }
  if (field.type !== 'select' && field.type !== 'user') {
    return { value: text };
  }
  if (!text) return { value: field.multiple ? [] : '' };
  const { valueByDisplay } = optionMaps(field);
  const inputs = field.multiple ? splitMultipleValue(rawValue) : [text];
  const values: string[] = [];
  for (const input of inputs) {
    const value = valueByDisplay.get(input);
    if (!value) {
      return {
        error: `${field.label}包含无法识别的选项“${input}”`,
        value: field.multiple ? [] : '',
      };
    }
    values.push(value);
  }
  return { value: field.multiple ? [...new Set(values)] : values[0]! };
}

function requiredByCondition(
  values: Record<string, AssetBatchEditValue>,
  field: AssetBatchEditField,
) {
  const condition = field.requiredWhen;
  if (!condition) return false;
  const dependency = values[condition.fieldKey];
  return (
    !Array.isArray(dependency) && condition.values.includes(dependency ?? '')
  );
}

function disposeUniver() {
  quickUserCellRenderDisposable?.dispose();
  quickUserCellRenderDisposable = undefined;
  quickUserCloseHitboxes = [];
  pendingQuickUserRemoval = undefined;
  autofillCopyModeDisposable?.dispose();
  autofillCopyModeDisposable = undefined;
  if (autofillHandleRefreshFrame !== undefined) {
    cancelAnimationFrame(autofillHandleRefreshFrame);
    autofillHandleRefreshFrame = undefined;
  }
  autofillHandleSubscriptions.forEach((subscription) =>
    subscription.unsubscribe(),
  );
  autofillHandleSubscriptions = [];
  lifecycleReadyDisposable?.dispose();
  lifecycleReadyDisposable = undefined;
  selectionChangedDisposable?.dispose();
  selectionChangedDisposable = undefined;
  valueChangedDisposable?.dispose();
  valueChangedDisposable = undefined;
  quickUserEditor.value = undefined;
  runtime?.univer.dispose();
  runtime = undefined;
}

function configureAutofillCopyMode(
  currentRuntime: UniverRuntime,
  unitId: string,
) {
  autofillCopyModeDisposable?.dispose();

  const autoFillService = currentRuntime.univer
    .__getInjector()
    .get(IAutoFillService);
  autoFillService.setDisableApplyType(AUTO_FILL_APPLY_TYPE.SERIES, true);
  autoFillService.setDisableApplyType(AUTO_FILL_APPLY_TYPE.ONLY_FORMAT, true);
  autoFillService.setDisableApplyType(AUTO_FILL_APPLY_TYPE.NO_FORMAT, true);
  autofillCopyModeDisposable = autoFillService.addHook({
    id: 'asset-office-copy-fill',
    priority: 100,
    disable: ({ unitId: activeUnitId }) => activeUnitId !== unitId,
    onBeforeFillData: () => AUTO_FILL_APPLY_TYPE.COPY,
  });
}

function scheduleAutofillHandles(
  currentRuntime: UniverRuntime,
  unitId: string,
  lastDataRow: number,
) {
  if (autofillHandleRefreshFrame !== undefined) {
    cancelAnimationFrame(autofillHandleRefreshFrame);
  }
  autofillHandleRefreshFrame = requestAnimationFrame(() => {
    autofillHandleRefreshFrame = undefined;
    if (runtime !== currentRuntime || !open.value) return;
    configureAutofillHandles(currentRuntime, unitId, lastDataRow);
  });
}

function configureAutofillHandles(
  currentRuntime: UniverRuntime,
  unitId: string,
  lastDataRow: number,
) {
  autofillHandleSubscriptions.forEach((subscription) =>
    subscription.unsubscribe(),
  );
  autofillHandleSubscriptions = [];

  const injector = currentRuntime.univer.__getInjector();
  const renderManager = injector.get(IRenderManagerService);
  const selectionRenderService = renderManager
    .getRenderById(unitId)
    ?.with(ISheetSelectionRenderService);
  selectionRenderService?.getSelectionControls().forEach((control) => {
    control.updateStyle({ autofillSize: AUTOFILL_HANDLE_SIZE });
    autofillHandleSubscriptions.push(
      control.fillControl.onDblclick$.subscribeEvent({
        priority: -100,
        next: ([, eventState]) => {
          const { endColumn, endRow, startColumn, startRow } = control.model;
          if (startRow < 1 || startRow > lastDataRow) return;

          eventState.skipNextObservers = true;
          eventState.stopPropagation();
          if (endRow >= lastDataRow) return;

          const sourceRange = {
            endColumn,
            endRow,
            startColumn,
            startRow,
          };
          void currentRuntime.univerAPI.executeCommand(AutoFillCommand.id, {
            applyType: AUTO_FILL_APPLY_TYPE.COPY,
            sourceRange,
            targetRange: { ...sourceRange, endRow: lastDataRow },
          });
        },
      }),
    );
  });
}

async function waitForUniverSteady(currentRuntime: UniverRuntime) {
  const { univerAPI } = currentRuntime;
  if (univerAPI.getCurrentLifecycleStage() >= LifecycleStages.Steady) return;

  await new Promise<void>((resolve) => {
    let eventDisposable: { dispose: () => void } | undefined;
    let waitDisposable: { dispose: () => void } | undefined;
    let settled = false;
    const complete = () => {
      if (settled) return;
      settled = true;
      eventDisposable?.dispose();
      if (lifecycleReadyDisposable === waitDisposable) {
        lifecycleReadyDisposable = undefined;
      }
      resolve();
    };

    eventDisposable = univerAPI.addEvent(
      univerAPI.Event.LifeCycleChanged,
      ({ stage }) => {
        if (stage >= LifecycleStages.Steady) complete();
      },
    );
    if (settled) {
      eventDisposable.dispose();
      return;
    }
    waitDisposable = { dispose: complete };
    lifecycleReadyDisposable = waitDisposable;
  });
}

async function initializeSpreadsheet() {
  if (
    !open.value ||
    props.loading ||
    initializing.value ||
    !spreadsheetContainer.value
  ) {
    return;
  }
  initializing.value = true;
  validationIssues.value = [];
  dirty.value = false;
  disposeUniver();
  try {
    if (props.fields.some((field) => field.type === 'user')) {
      organizationUsers.value = await getSharedOrganizationUsers();
    }
    if (!open.value || !spreadsheetContainer.value) return;

    runtime = createUniver({
      darkMode: false,
      locale: LocaleType.ZH_CN,
      locales: {
        [LocaleType.ZH_CN]: mergeLocales(
          sheetsCoreZhCN,
          sheetsFilterZhCN,
          sheetsSortZhCN,
          sheetsDataValidationZhCN,
          sheetsConditionalFormattingZhCN,
          sheetsFindReplaceZhCN,
          sheetsTableZhCN,
        ),
      },
      presets: [
        UniverSheetsCorePreset({
          container: spreadsheetContainer.value,
          footer: {
            menus: true,
            sheetBar: true,
            statisticBar: true,
            zoomSlider: true,
          },
          formulaBar: true,
          header: true,
          ribbonType: 'classic',
          statusBarStatistic: true,
          toolbar: true,
        }),
        UniverSheetsFilterPreset(),
        UniverSheetsSortPreset(),
        UniverSheetsDataValidationPreset({
          showEditOnDropdown: false,
          showSearchOnDropdown: true,
        }),
        UniverSheetsConditionalFormattingPreset(),
        UniverSheetsFindReplacePreset(),
        UniverSheetsTablePreset(),
      ],
    });

    const currentRuntime = runtime;
    const workbook = currentRuntime.univerAPI.createWorkbook({
      name: props.title,
    });
    const worksheet = workbook.getActiveSheet();
    const dataRows = props.rows.map((row) => [
      ...props.fields.map((field) => {
        const displayValue = displayCellValue(row, field);
        // Univer 会把空字符串视为已有值；使用 null 才能让双击填充柄识别为真正空单元格。
        return { v: displayValue === '' ? null : displayValue };
      }),
      { v: row.id ?? null },
    ]);
    const worksheetCapacity = calculateWorksheetCapacity({
      allowCreate: props.allowCreate,
      currentColumnCount: worksheet.getMaxColumns(),
      currentRowCount: worksheet.getMaxRows(),
      dataRowCount: dataRows.length,
      fieldCount: props.fields.length,
    });
    if (worksheetCapacity.rowCount > worksheet.getMaxRows()) {
      worksheet.setRowCount(worksheetCapacity.rowCount);
    }
    if (worksheetCapacity.columnCount > worksheet.getMaxColumns()) {
      worksheet.setColumnCount(worksheetCapacity.columnCount);
    }
    worksheet
      .getRange(0, 0, dataRows.length + 1, props.fields.length + 1)
      .setValues([
        [
          ...props.fields.map((field) => ({
            v: `${field.label}${field.required || field.requiredWhen ? ' *' : ''}${field.editable === false && !props.allowCreate ? '（只读）' : ''}`,
          })),
          { v: TECHNICAL_ID_HEADER },
        ],
        ...dataRows,
      ]);

    const headerRange = worksheet.getRange(0, 0, 1, props.fields.length);
    headerRange
      .setBackground('#f5f5f5')
      .setFontWeight('bold')
      .setHorizontalAlignment('center')
      .setWrap(true);
    worksheet.setRowHeight(0, 44);
    worksheet.setFrozenRows(1);
    props.fields.forEach((field, index) => {
      worksheet.setColumnWidth(
        index,
        isQuickUserField(field) ? 260 : field.type === 'textarea' ? 240 : 168,
      );
    });
    worksheet.hideColumns(props.fields.length, 1);

    // 下拉面板由 Univer 的懒加载控制器提供，必须等到 Steady 后再挂载规则。
    await waitForUniverSteady(currentRuntime);
    if (runtime !== currentRuntime || !open.value) return;

    const workbookId = workbook.getId();
    configureAutofillCopyMode(currentRuntime, workbookId);
    registerQuickUserCellRenderer(currentRuntime);
    // 未勾选资产时保留空白新增模板；此时不存在“已载入数据末行”，不能绑定定界双击填充。
    if (dataRows.length > 0) {
      configureAutofillHandles(currentRuntime, workbookId, dataRows.length);
      scheduleAutofillHandles(currentRuntime, workbookId, dataRows.length);
    }
    selectionChangedDisposable = currentRuntime.univerAPI.addEvent(
      currentRuntime.univerAPI.Event.SelectionChanged,
      ({ selections }) => {
        if (dataRows.length > 0) {
          scheduleAutofillHandles(currentRuntime, workbookId, dataRows.length);
        }
        syncQuickUserEditorSelection(selections);
      },
    );

    props.fields.forEach((field, index) => {
      const options = fieldOptions(field).map((option) => option.label);
      if (
        !options.length ||
        (field.type !== 'select' && field.type !== 'user')
      ) {
        return;
      }
      const rule = runtime!.univerAPI
        .newDataValidation()
        .requireValueInList(options, Boolean(field.multiple), true)
        .setOptions({ renderMode: DataValidationRenderMode.ARROW })
        .build();
      worksheet
        .getRange(1, index, worksheet.getMaxRows() - 1, 1)
        .setDataValidation(rule);
    });
    valueChangedDisposable = currentRuntime.univerAPI.addEvent(
      currentRuntime.univerAPI.Event.SheetValueChanged,
      () => {
        dirty.value = true;
        validationIssues.value = [];
        refreshQuickUserEditor();
      },
    );
  } catch (error) {
    disposeUniver();
    message.error('Excel 编辑器初始化失败，请关闭后重试');
    console.error(error);
  } finally {
    initializing.value = false;
  }
}

async function buildSubmission() {
  const workbook = runtime?.univerAPI.getActiveWorkbook();
  if (!workbook) return;
  await workbook.endEditingAsync(true);
  const worksheet = workbook.getActiveSheet();
  const rowCount = worksheet.getMaxRows();
  const columnCount = worksheet.getMaxColumns();
  const headerValues =
    worksheet.getRange(0, 0, 1, columnCount).getValues()[0] ?? [];
  const technicalIdColumn = headerValues.findIndex(
    (value) => value === TECHNICAL_ID_HEADER,
  );
  const values = worksheet
    .getRange(1, 0, rowCount - 1, columnCount)
    .getValues();
  const issues: ValidationIssue[] = [];
  const submissionRows: AssetBatchEditSubmission['rows'] = [];
  const identifiers = new Map<string, number>();

  for (const [sheetRowIndex, cells] of values.entries()) {
    const fieldCells = props.fields.map((_, index) => cells[index]);
    if (fieldCells.every((value) => String(value ?? '').trim() === ''))
      continue;
    const technicalId =
      technicalIdColumn >= 0
        ? String(cells[technicalIdColumn] ?? '').trim()
        : '';
    let original = technicalId
      ? originalRowsById.value.get(technicalId)
      : undefined;
    const parsedValues: Record<string, AssetBatchEditValue> = {};
    for (const [columnIndex, field] of props.fields.entries()) {
      const parsed = parseCellValue(cells[columnIndex], field);
      parsedValues[field.key] = parsed.value;
      if (parsed.error) {
        issues.push({
          columnIndex,
          message: parsed.error,
          rowIndex: sheetRowIndex + 1,
        });
      }
    }

    const identifier = scalarValue(parsedValues[props.identifierKey]).trim();
    original ??= originalRowsByIdentifier.value.get(identifier);
    if (!original && !props.allowCreate) {
      issues.push({
        columnIndex: Math.max(
          props.fields.findIndex((field) => field.key === props.identifierKey),
          0,
        ),
        message: `${props.targetLabel} Excel 批量处理仅支持修改已选数据`,
        rowIndex: sheetRowIndex + 1,
      });
    }
    if (technicalId && !original) {
      issues.push({
        columnIndex: 0,
        message: `该行关联的原${props.targetLabel}已失效，请关闭弹窗后重新选择`,
        rowIndex: sheetRowIndex + 1,
      });
    }
    if (original?.id) {
      const originalIdentifier = scalarValue(
        original.values[props.identifierKey],
      ).trim();
      if (identifier !== originalIdentifier) {
        issues.push({
          columnIndex: Math.max(
            props.fields.findIndex(
              (field) => field.key === props.identifierKey,
            ),
            0,
          ),
          message: `${identifierField.value?.label ?? '唯一标识'}是已有${props.targetLabel}的只读字段${props.allowCreate ? `；新增${props.targetLabel}请使用空白行` : '，不能修改'}`,
          rowIndex: sheetRowIndex + 1,
        });
      }
    }

    for (const [columnIndex, field] of props.fields.entries()) {
      if (original && field.sensitive && !hasValue(parsedValues[field.key])) {
        parsedValues[field.key] = cloneValue(original.values[field.key]);
      }
      if (original && field.editable === false) {
        parsedValues[field.key] = cloneValue(original.values[field.key]);
      }
      const required =
        field.required || requiredByCondition(parsedValues, field);
      if (required && !hasValue(parsedValues[field.key])) {
        issues.push({
          columnIndex,
          message: `${field.label}不能为空`,
          rowIndex: sheetRowIndex + 1,
        });
      }
      if (
        field.requiredWhen?.incompatibleMessage &&
        hasValue(parsedValues[field.key]) &&
        !requiredByCondition(parsedValues, field)
      ) {
        issues.push({
          columnIndex,
          message: field.requiredWhen.incompatibleMessage,
          rowIndex: sheetRowIndex + 1,
        });
      }
    }

    const normalizedIdentifier = scalarValue(
      parsedValues[props.identifierKey],
    ).trim();
    if (normalizedIdentifier) {
      const previousRow = identifiers.get(normalizedIdentifier);
      if (previousRow !== undefined) {
        issues.push({
          columnIndex: Math.max(
            props.fields.findIndex(
              (field) => field.key === props.identifierKey,
            ),
            0,
          ),
          message: `${identifierField.value?.label ?? '唯一标识'}与第 ${previousRow + 1} 行重复`,
          rowIndex: sheetRowIndex + 1,
        });
      } else {
        identifiers.set(normalizedIdentifier, sheetRowIndex + 1);
      }
    }

    const changedFields = original
      ? props.fields
          .filter(
            (field) =>
              field.editable !== false &&
              !equalValue(parsedValues[field.key], original!.values[field.key]),
          )
          .map((field) => field.key)
      : props.fields.map((field) => field.key);
    if (!original || changedFields.length) {
      submissionRows.push({
        changedFields,
        id: original?.id,
        isNew: !original,
        rowNumber: sheetRowIndex + 2,
        values: parsedValues,
      });
    }
  }

  validationIssues.value = issues;
  if (issues.length) {
    const first = issues[0]!;
    worksheet.getRange(first.rowIndex, first.columnIndex).activate();
    message.error(`校验未通过：${first.message}`);
    return;
  }
  if (!submissionRows.length) {
    message.info('没有需要保存的新增或修改');
    return;
  }
  return { rows: submissionRows } satisfies AssetBatchEditSubmission;
}

async function submit() {
  const submission = await buildSubmission();
  if (submission) emit('submit', submission);
}

function requestClose() {
  if (!dirty.value) {
    open.value = false;
    return;
  }
  Modal.confirm({
    content: '关闭后，Excel 中未保存的数据修改会丢失。',
    okText: '放弃修改',
    okType: 'danger',
    title: '存在未保存修改',
    zIndex: 3100,
    onOk: () => (open.value = false),
  });
}

watch(
  () => [open.value, props.loading, props.rows, props.fields] as const,
  async ([isOpen, isLoading]) => {
    if (!isOpen || isLoading) return;
    await nextTick();
    await initializeSpreadsheet();
  },
  { immediate: true },
);

watch(open, (isOpen) => {
  if (!isOpen) disposeUniver();
});

onBeforeUnmount(disposeUniver);
</script>

<template>
  <Modal
    :cancel-button-props="{ disabled: submitting }"
    :closable="!submitting"
    :footer="null"
    :keyboard="false"
    :mask-closable="false"
    :open="open"
    width="100vw"
    wrap-class-name="ux-fixed-modal asset-office-spreadsheet-modal is-fullscreen"
    @cancel="requestClose"
  >
    <template #title>
      <div class="flex min-w-0 items-center gap-2">
        <IconifyIcon
          aria-hidden="true"
          class="size-5 shrink-0 text-emerald-700"
          icon="lucide:sheet"
        />
        <span class="truncate">{{ title }}</span>
      </div>
    </template>

    <div class="asset-office-spreadsheet flex min-h-0 flex-col gap-3">
      <Alert
        v-if="validationIssues.length"
        closable
        show-icon
        type="error"
        :message="validationSummary"
        @close="validationIssues = []"
      />

      <div class="asset-office-spreadsheet__surface">
        <div
          ref="spreadsheetContainer"
          :aria-label="`${targetLabel} Excel 批量编辑器`"
          class="asset-office-spreadsheet__container"
        ></div>
        <div
          v-if="loading || initializing"
          class="asset-office-spreadsheet__loading"
        >
          <Spin tip="正在载入 Excel 编辑器…" />
        </div>
      </div>

      <div class="flex shrink-0 items-center justify-between gap-4">
        <p class="text-muted-foreground m-0 text-sm">
          {{
            statusHint ||
            (allowCreate
              ? '可添加空白行新增数据；已有敏感字段留空表示保持不变。'
              : '已有敏感字段留空表示保持不变；修改后填写新值即可覆盖。')
          }}
        </p>
        <div class="flex shrink-0 justify-end gap-2">
          <Button :disabled="submitting" @click="requestClose">取消</Button>
          <Button
            :disabled="loading || initializing"
            :loading="submitting"
            type="primary"
            @click="submit"
          >
            校验并保存
          </Button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<style>
.asset-office-spreadsheet {
  flex: 1;
}

.asset-office-spreadsheet-modal.is-fullscreen .ant-modal {
  top: 0;
  width: 100vw !important;
  max-width: none;
  height: 100dvh;
  margin: 0;
}

.asset-office-spreadsheet-modal.is-fullscreen .ant-modal-content {
  height: 100dvh;
  border-radius: 0;
}

.asset-office-spreadsheet__surface {
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.asset-office-spreadsheet__container {
  height: 100%;
  min-height: 0;
  width: 100%;
}

.asset-office-spreadsheet__loading {
  align-items: center;
  background: hsl(var(--background) / 0.9);
  display: flex;
  inset: 0;
  justify-content: center;
  position: absolute;
  z-index: 20;
}

/* Univer 将浮层挂到 body；需覆盖其内联层级并高于 Ant Modal。 */
body:has(.asset-office-spreadsheet-modal) .univer-popup,
body:has(.asset-office-spreadsheet-modal) [data-radix-popper-content-wrapper],
body:has(.asset-office-spreadsheet-modal) [data-u-context-menu-submenu='true'],
body:has(.asset-office-spreadsheet-modal) [data-u-comp='rect-popup'] {
  z-index: 3000 !important;
}
</style>
