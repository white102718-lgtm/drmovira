<script lang="ts" setup>
import type {
  TableColumnsType,
  TablePaginationConfig,
  UploadFile,
  UploadProps,
} from 'ant-design-vue';
import type { Worksheet } from 'exceljs';
import type { AssetImportFailedFile, AssetImportHistoryRecord } from '#/api';
import type { SystemPageResult } from '#/api/system/types';

import { computed, reactive, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  message,
  Modal,
  Select,
  Table,
  Tag,
  Upload,
  UploadDragger,
} from 'ant-design-vue';

import {
  getInventoryAssetPresentationKeys,
  getInventoryAssetTemplateFields,
  INVENTORY_ASSET_TYPES,
  type InventoryAssetTypeMeta,
} from './asset-types';
import { ASSET_MODAL_TABLE_BODY_HEIGHT } from './asset-table-layout';

const ASSET_IMPORT_MAX_FILE_SIZE = 5 * 1024 * 1024;
const ASSET_IMPORT_TEMPLATE_MAX_ROWS = 5000;
const ASSET_IMPORT_MODAL_Z_INDEX = 3000;
const IMPORT_HISTORY_DEFAULT_PAGE_SIZE = 10;
// 导入记录与失败详情是批量导入弹窗内触发的后续视图，必须位于父弹窗之上，避免遮罩层拦截操作。
const ASSET_IMPORT_CHILD_MODAL_Z_INDEX = 3010;
const importableAssetTypes = INVENTORY_ASSET_TYPES.filter(
  (assetType) => assetType.assetType !== 'AD_ACCOUNT',
);

export interface AssetFileImportFailure {
  line: number;
  message: string;
}

export interface AssetFileImportResult {
  failedFileBase64?: string | null;
  failedFileName?: string | null;
  failures: AssetFileImportFailure[];
  successCount: number;
  totalCount: number;
}

const props = defineProps<{
  defaultAssetSubtype?: string;
  onDownloadFailedFile: (id: string) => Promise<AssetImportFailedFile>;
  onImport: (file: File, subtype: string) => Promise<AssetFileImportResult>;
  onLoadHistory: (params: {
    page: number;
    pageSize: number;
  }) => Promise<SystemPageResult<AssetImportHistoryRecord>>;
}>();

interface ImportHistoryRecord extends AssetImportHistoryRecord {
  assetTypeLabel: string;
}

const open = ref(false);
const importing = ref(false);
const importFailureModalOpen = ref(false);
const importHistoryModalOpen = ref(false);
const importHistoryLoading = ref(false);
const fileList = ref<UploadFile[]>([]);
const selectedFile = ref<File>();
const uploadError = ref('');
const importFailures = ref<AssetFileImportFailure[]>([]);
const importHistoryRecords = ref<ImportHistoryRecord[]>([]);
const selectedAssetSubtype = ref('');
const importHistoryPagination = reactive({
  page: 1,
  pageSize: IMPORT_HISTORY_DEFAULT_PAGE_SIZE,
  total: 0,
});

const selectedAssetType = computed(() => {
  return (
    importableAssetTypes.find(
      (assetType) => assetType.subtype === selectedAssetSubtype.value,
    ) ?? importableAssetTypes[0]
  );
});
const assetTypeOptions = importableAssetTypes.map((assetType) => ({
  label: assetType.label,
  value: assetType.subtype,
}));
const importFailureColumns: TableColumnsType<AssetFileImportFailure> = [
  { dataIndex: 'line', key: 'line', title: '行号', width: 88 },
  { dataIndex: 'message', key: 'message', title: '失败原因' },
];
const importHistoryColumns: TableColumnsType<ImportHistoryRecord> = [
  { dataIndex: 'createdAt', key: 'createdAt', title: '导入时间', width: 172 },
  { key: 'assetType', title: '资产类型', width: 120 },
  { dataIndex: 'fileName', key: 'fileName', title: '导入文件', width: 220 },
  { dataIndex: 'totalCount', key: 'totalCount', title: '总数', width: 88 },
  { dataIndex: 'successCount', key: 'successCount', title: '成功', width: 88 },
  { key: 'failureCount', title: '失败', width: 88 },
  { key: 'actions', title: '操作', width: 144 },
];
const importHistoryPaginationConfig = computed<TablePaginationConfig>(() => ({
  current: importHistoryPagination.page,
  pageSize: importHistoryPagination.pageSize,
  pageSizeOptions: ['10', '20', '50'],
  showSizeChanger: true,
  showTotal: (total) => `共 ${total} 条`,
  total: importHistoryPagination.total,
}));

function resetCurrentImport() {
  fileList.value = [];
  selectedFile.value = undefined;
  uploadError.value = '';
  importFailures.value = [];
  importFailureModalOpen.value = false;
}

function selectDefaultAssetType() {
  const defaultAssetType = importableAssetTypes.find(
    (assetType) => assetType.subtype === props.defaultAssetSubtype,
  );
  selectedAssetSubtype.value =
    defaultAssetType?.subtype ?? importableAssetTypes[0]?.subtype ?? '';
}

function show() {
  resetCurrentImport();
  selectDefaultAssetType();
  open.value = true;
}

function handleRemove() {
  resetCurrentImport();
  return true;
}

function handleAssetTypeChange(value: unknown) {
  selectedAssetSubtype.value = String(value ?? '');
  resetCurrentImport();
}

/** 页面只做文件选择限制；Excel 的表头、字段与数据校验全部交由服务端。 */
const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  resetCurrentImport();
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (!extension || !['csv', 'xls', 'xlsx'].includes(extension)) {
    uploadError.value = '仅支持 .xlsx、.xls 或 .csv 文件';
    return Upload.LIST_IGNORE;
  }
  if (file.size > ASSET_IMPORT_MAX_FILE_SIZE) {
    uploadError.value = '文件不能超过 5MB';
    return Upload.LIST_IGNORE;
  }
  selectedFile.value = file;
  fileList.value = [file];
  return false;
};

function getTemplateHeaders(assetType: InventoryAssetTypeMeta) {
  if (assetType.presentationKeys?.length) {
    const fieldsByKey = new Map(
      assetType.fields.map((field) => [field.key, field]),
    );
    return getInventoryAssetPresentationKeys(assetType).map((key) => {
      if (key.startsWith('detail.')) {
        const field = fieldsByKey.get(key.slice('detail.'.length));
        return field?.excelHeader ?? field?.label ?? key;
      }
      if (key === 'projectName') return '所属项目';
      if (key === 'usageTeam') return '使用团队';
      return '备注';
    });
  }

  return [
    ...getInventoryAssetTemplateFields(assetType).map(
      (field) => field.excelHeader ?? field.label,
    ),
    ...(assetType.requiresChannel ? ['渠道名称'] : []),
    ...(assetType.importContextHeaders ?? []),
    ...(assetType.usageUserHeader ? [assetType.usageUserHeader] : []),
    '备注',
  ];
}

function getExcelColumnName(index: number) {
  let columnName = '';
  let currentIndex = index;
  while (currentIndex > 0) {
    const remainder = (currentIndex - 1) % 26;
    columnName = String.fromCharCode(65 + remainder) + columnName;
    currentIndex = Math.floor((currentIndex - 1) / 26);
  }
  return columnName;
}

/**
 * 将资产表单中的固定枚举项同步为 Excel 下拉，避免导入时出现无效值。
 * 渠道名称不是固定枚举，保持文本单元格以支持按名称填写。
 */
function applyTemplateSelectValidations(
  worksheet: Worksheet,
  assetType: InventoryAssetTypeMeta,
  headers: string[],
) {
  for (const field of getInventoryAssetTemplateFields(assetType)) {
    if (field.type !== 'select' || !field.options?.length) continue;

    const header = field.excelHeader ?? field.label;
    const columnIndex = headers.indexOf(header) + 1;
    if (columnIndex === 0) continue;

    const validation = {
      allowBlank: true,
      formulae: [`"${field.options.map((option) => option.label).join(',')}"`],
      showErrorMessage: true,
      type: 'list' as const,
    };
    const columnName = getExcelColumnName(columnIndex);
    for (
      let rowIndex = 2;
      rowIndex <= ASSET_IMPORT_TEMPLATE_MAX_ROWS + 1;
      rowIndex++
    ) {
      worksheet.getCell(`${columnName}${rowIndex}`).dataValidation = validation;
    }
  }
}

function downloadWorkbook(content: Uint8Array, fileName: string) {
  const fileUrl = URL.createObjectURL(
    new Blob([content], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }),
  );
  const link = document.createElement('a');
  link.href = fileUrl;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(fileUrl), 0);
}

async function downloadTemplate() {
  const assetType = selectedAssetType.value;
  if (!assetType) return;
  try {
    const { Workbook } = await import('exceljs');
    const workbook = new Workbook();
    const worksheet = workbook.addWorksheet(
      assetType.excelSheetName ?? assetType.label,
    );
    const headers = getTemplateHeaders(assetType);
    worksheet.addRow(headers);
    applyTemplateSelectValidations(worksheet, assetType, headers);
    worksheet.views = [{ state: 'frozen', ySplit: 1 }];
    worksheet.autoFilter = {
      from: 'A1',
      to: `${getExcelColumnName(headers.length)}1`,
    };
    for (const [index, header] of headers.entries()) {
      worksheet.getColumn(index + 1).width = Math.max(
        14,
        Math.min(28, header.length * 2 + 4),
      );
    }
    downloadWorkbook(
      new Uint8Array(await workbook.xlsx.writeBuffer()),
      `资产批量导入模板-${assetType.label}.xlsx`,
    );
    message.success(`${assetType.label}导入模板已下载`);
  } catch {
    message.error('模板生成失败，请稍后重试');
  }
}

function decodeBase64(content: string) {
  const binary = window.atob(content);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function toImportHistoryRecord(
  record: AssetImportHistoryRecord,
): ImportHistoryRecord {
  const assetType = importableAssetTypes.find(
    (item) => item.subtype === record.assetSubtype,
  );
  return {
    ...record,
    assetTypeLabel: assetType?.label ?? record.assetSubtype,
  };
}

/** 保留服务端返回的本地时间语义，仅统一为不带 T 的秒级展示格式。 */
function formatImportTime(value: string) {
  return value ? value.trim().slice(0, 19).replace('T', ' ') : '-';
}

async function loadImportHistory() {
  importHistoryLoading.value = true;
  try {
    const result = await props.onLoadHistory({
      page: importHistoryPagination.page,
      pageSize: importHistoryPagination.pageSize,
    });
    importHistoryRecords.value = result.items.map(toImportHistoryRecord);
    importHistoryPagination.page = result.page;
    importHistoryPagination.pageSize = result.pageSize;
    importHistoryPagination.total = result.total;
  } finally {
    importHistoryLoading.value = false;
  }
}

async function openImportHistory() {
  importHistoryPagination.page = 1;
  importHistoryPagination.pageSize = IMPORT_HISTORY_DEFAULT_PAGE_SIZE;
  importHistoryPagination.total = 0;
  importHistoryRecords.value = [];
  importHistoryModalOpen.value = true;
  try {
    await loadImportHistory();
  } catch {
    // 请求客户端已统一展示接口错误，此处关闭未能完成加载的记录弹窗。
    importHistoryModalOpen.value = false;
  }
}

async function handleImportHistoryTableChange(
  pagination: TablePaginationConfig,
) {
  const pageSize = pagination.pageSize ?? importHistoryPagination.pageSize;
  importHistoryPagination.page =
    pageSize === importHistoryPagination.pageSize
      ? (pagination.current ?? 1)
      : 1;
  importHistoryPagination.pageSize = pageSize;
  try {
    await loadImportHistory();
  } catch {
    // 请求客户端统一展示错误，保留当前弹窗以便用户重试或关闭。
  }
}

async function handleDownloadFailedFile(record: Record<string, unknown>) {
  if (typeof record.id !== 'string') {
    message.error('导入记录无效，请刷新后重试');
    return;
  }
  const failedFile = await props.onDownloadFailedFile(record.id);
  downloadWorkbook(decodeBase64(failedFile.contentBase64), failedFile.fileName);
}

async function submit() {
  const assetType = selectedAssetType.value;
  const file = selectedFile.value;
  if (!assetType || !file) {
    message.warning('请先选择导入文件');
    return;
  }
  importing.value = true;
  try {
    const result = await props.onImport(file, assetType.subtype);
    importFailures.value = result.failures;
    if (result.failures.length === 0) {
      message.success(`已成功处理 ${result.successCount} 条资产`);
      open.value = false;
      return;
    }
    importFailureModalOpen.value = true;
    message.warning(
      `成功处理 ${result.successCount} 条，${result.failures.length} 条失败`,
    );
  } catch (error) {
    // 后端已统一完成文件解析与字段校验；此处仅保留请求失败反馈，避免事件异常未处理。
    uploadError.value =
      error instanceof Error && error.message
        ? error.message
        : '服务端未完成导入，请稍后重试';
  } finally {
    importing.value = false;
  }
}

defineExpose({ show });
</script>

<template>
  <Modal
    v-model:open="open"
    :closable="!importing"
    :mask-closable="!importing"
    destroy-on-close
    title="批量导入资产"
    width="min(720px, calc(100vw - 32px))"
    :z-index="ASSET_IMPORT_MODAL_Z_INDEX"
  >
    <div class="flex flex-col gap-4">
      <div class="flex flex-wrap items-end gap-3">
        <div class="w-full sm:min-w-0 sm:flex-1">
          <label class="mb-2 block text-sm font-medium text-slate-700"
            >资产类型</label
          >
          <Select
            v-model:value="selectedAssetSubtype"
            :disabled="importing"
            :options="assetTypeOptions"
            class="w-full"
            @change="handleAssetTypeChange"
          />
        </div>
        <Button
          class="w-full sm:w-auto sm:shrink-0"
          :disabled="importing"
          @click="openImportHistory"
        >
          <IconifyIcon aria-hidden="true" icon="lucide:history" />导入记录
        </Button>
      </div>

      <Alert
        v-if="uploadError"
        :message="uploadError"
        role="alert"
        show-icon
        type="error"
      />
      <Alert
        v-else-if="selectedFile"
        message="文件已选择，提交后将由服务端解析并校验。"
        show-icon
        type="info"
      />

      <UploadDragger
        v-model:file-list="fileList"
        accept=".xlsx,.xls,.csv"
        :before-upload="beforeUpload"
        :disabled="importing"
        :max-count="1"
        @remove="handleRemove"
      >
        <p
          class="ant-upload-drag-icon flex items-center justify-center"
          aria-hidden="true"
        >
          <IconifyIcon
            class="text-primary block text-2xl"
            icon="lucide:file-up"
          />
        </p>
        <p class="ant-upload-text">将文件拖到此处，或点击选择文件</p>
        <p class="ant-upload-hint">
          支持 .xlsx、.xls、.csv，不超过 5MB，单次最多 5000 条
        </p>
      </UploadDragger>

      <div
        class="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-500"
      >
        <span>
          表头、必填字段、使用人及库存状态均由服务端统一处理；像素可用顿号或逗号填写多位使用人。
        </span>
        <Button type="link" @click="downloadTemplate">
          <IconifyIcon aria-hidden="true" icon="lucide:download" />下载{{
            selectedAssetType?.label
          }}导入模板
        </Button>
      </div>
    </div>

    <template #footer>
      <Button :disabled="importing" @click="open = false">取消</Button>
      <Button
        :disabled="!selectedFile"
        :loading="importing"
        type="primary"
        @click="submit"
      >
        导入资产
      </Button>
    </template>
  </Modal>

  <Modal
    v-model:open="importFailureModalOpen"
    footer=""
    title="导入失败详情"
    width="min(620px, calc(100vw - 32px))"
    :z-index="ASSET_IMPORT_CHILD_MODAL_Z_INDEX"
  >
    <Table
      class="asset-dialog-fixed-table"
      :columns="importFailureColumns"
      :data-source="importFailures"
      :pagination="false"
      :row-key="(record) => `${record.line}-${record.message}`"
      size="small"
      :scroll="{ y: ASSET_MODAL_TABLE_BODY_HEIGHT }"
      :style="{
        '--asset-dialog-table-height': `${ASSET_MODAL_TABLE_BODY_HEIGHT}px`,
      }"
    />
  </Modal>

  <Modal
    v-model:open="importHistoryModalOpen"
    footer=""
    title="导入记录"
    width="min(900px, calc(100vw - 32px))"
    :z-index="ASSET_IMPORT_CHILD_MODAL_Z_INDEX"
  >
    <div class="import-history-modal-content">
      <Table
        class="asset-dialog-fixed-table"
        :columns="importHistoryColumns"
        :data-source="importHistoryRecords"
        :loading="importHistoryLoading"
        :locale="{ emptyText: '暂无导入记录' }"
        :pagination="importHistoryPaginationConfig"
        :row-key="(record) => record.id"
        :scroll="{ x: 920, y: ASSET_MODAL_TABLE_BODY_HEIGHT }"
        size="small"
        :style="{
          '--asset-dialog-table-height': `${ASSET_MODAL_TABLE_BODY_HEIGHT}px`,
        }"
        @change="handleImportHistoryTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'createdAt'">
            {{ formatImportTime(record.createdAt) }}
          </template>
          <template v-else-if="column.key === 'assetType'">
            <Tag>{{ record.assetTypeLabel }}</Tag>
          </template>
          <template v-else-if="column.key === 'failureCount'">
            {{ record.failures.length }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <Button
              v-if="record.failures.length > 0"
              size="small"
              type="link"
              @click="handleDownloadFailedFile(record)"
            >
              下载失败文件
            </Button>
            <span v-else class="text-slate-400">无失败文件</span>
          </template>
        </template>
      </Table>
    </div>
  </Modal>
</template>

<style scoped>
.import-history-modal-content {
  height: min(480px, calc(100dvh - 160px));
  overflow: hidden;
}
</style>
