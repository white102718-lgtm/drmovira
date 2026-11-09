<script lang="ts" setup>
import type { TableColumnsType, UploadProps } from 'ant-design-vue';

import type { ProjectContextOption } from '#/api';
import type {
  AgencyLineImportError,
  AgencyLineImportResult,
} from '#/domain/agency-line';
import type { OptimizerOption } from '#/domain/agency-line/optimizer';

import { computed, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Checkbox,
  Drawer,
  Input,
  message,
  Modal,
  Select,
  Table,
  Tag,
  Upload,
} from 'ant-design-vue';

import { getUserList } from '#/api/system/user';
import {
  agencyLineService,
  parseAgencyLineImportRows,
  prepareAgencyLineImportRows,
  resolveAgencyLineImportProjectNames,
} from '#/domain/agency-line';

type ImportRecord = Record<string, unknown>;

interface ImportPreviewRecord extends ImportRecord {
  _row: number;
}

const props = defineProps<{
  open: boolean;
  projects: ProjectContextOption[];
  /** 嵌套在项目详情上方时，同步抬高导入抽屉及其错误弹窗。 */
  zIndex?: number;
}>();

const emit = defineEmits<{
  (event: 'imported', result: AgencyLineImportResult): void;
  (event: 'update:open', open: boolean): void;
}>();

const MAX_IMPORT_FILE_BYTES = 2 * 1024 * 1024;
const MAX_IMPORT_ROWS = 1000;

const rows = ref<ImportRecord[]>([]);
const sourceFileName = ref('');
const parsing = ref(false);
const saving = ref(false);
const overwriteExisting = ref(false);
const fileError = ref('');
const parseErrors = ref<AgencyLineImportError[]>([]);
const importResult = ref<AgencyLineImportResult>();
const requestIdsByRow = ref<Record<number, string>>({});
const fileErrorsOpen = ref(false);
const optimizerOptions = ref<OptimizerOption[]>([]);
const retryableRows = ref<number[]>([]);
const editingLocked = computed(
  () =>
    saving.value ||
    parsing.value ||
    Boolean(importResult.value?.items.length || retryableRows.value.length),
);

// 文件错误保留上传时快照；预览和提交始终使用当前编辑内容重新校验。
const currentPreview = computed(() => {
  const resolution = resolveAgencyLineImportProjectNames(
    rows.value,
    props.projects,
  );
  const parsed = parseAgencyLineImportRows(resolution.rows);
  const errors = [
    ...resolution.errors,
    ...parsed.errors,
    ...validateProjectRelations(parsed.rows),
  ];
  const rowsByName = new Map<string, number[]>();
  rows.value.forEach((record, index) => {
    const lineName = String(record.name ?? '')
      .trim()
      .toLowerCase();
    if (lineName)
      rowsByName.set(lineName, [
        ...(rowsByName.get(lineName) ?? []),
        index + 1,
      ]);
    const id = String(record.optimizerId ?? '').trim();
    const name = String(record.optimizerName ?? '').trim();
    if (
      id &&
      !optimizerOptions.value.some(
        (option) => option.value === id && option.name === name,
      )
    ) {
      errors.push({
        code: 'invalid_value',
        field: 'optimizerId',
        message: '投手 ID 与姓名不匹配，请重新选择投手',
        row: index + 1,
      });
    }
  });
  for (const [name, rowNumbers] of rowsByName) {
    if (rowNumbers.length < 2) continue;
    for (const row of rowNumbers) {
      errors.push({
        code: 'duplicate',
        field: 'name',
        message: `批次内代理线名称重复：${name}（数据行 ${rowNumbers.join('、')}）`,
        row,
      });
    }
  }
  for (const error of errors) {
    if (
      error.field === 'optimizerId' &&
      !rows.value[error.row - 1]?.optimizerId
    ) {
      error.message = '未匹配到启用的投手，请修正姓名或选择投手 ID';
    }
  }
  return { errors, rows: resolution.rows };
});
const previewErrors = computed(() => [
  ...currentPreview.value.errors,
  ...(importResult.value?.errors ?? []),
]);

const previewRows = computed<ImportPreviewRecord[]>(() =>
  rows.value.map((record, index) => ({ ...record, _row: index + 1 })),
);

const previewColumns: TableColumnsType<ImportRecord> = [
  { key: 'sequence', title: '行', width: 64 },
  { dataIndex: 'type', key: 'type', title: '类型', width: 140 },
  { dataIndex: 'platform', key: 'platform', title: '投放平台', width: 150 },
  { dataIndex: 'pixelName', key: 'pixelName', title: '像素名称', width: 180 },
  { dataIndex: 'pixelId', key: 'pixelId', title: '像素 ID', width: 180 },
  { dataIndex: 'token', key: 'token', title: 'Token', width: 220 },
  { dataIndex: 'testCode', key: 'testCode', title: '测试代码', width: 180 },
  { dataIndex: 'name', key: 'name', title: '代理线', width: 180 },
  {
    dataIndex: 'deliveryUrl',
    key: 'deliveryUrl',
    title: '投放链接',
    width: 220,
  },
  {
    dataIndex: 'optimizerName',
    key: 'optimizerName',
    title: '投手',
    width: 150,
  },
  { dataIndex: 'cloakUrl', key: 'cloakUrl', title: '斗篷链接', width: 220 },
  {
    dataIndex: 'projectName',
    key: 'projectId',
    title: '关联项目（选填）',
    width: 180,
  },
  { dataIndex: 'pageId', key: 'pageId', title: '主页 ID', width: 160 },
  {
    dataIndex: 'optimizerId',
    key: 'optimizerId',
    title: '投手 ID（可选择核对）',
    width: 260,
  },
];

/** 重名固定取返回顺序中的首项，避免重新校验造成归属跳变。 */
function matchOptimizer(record: ImportRecord) {
  const name = String(record.optimizerName ?? '').trim();
  record.optimizerId =
    optimizerOptions.value.find((option) => option.name === name)?.value ?? '';
}

function updatePreviewCell(row: number, field: string, value: unknown) {
  if (editingLocked.value) return;
  const record = rows.value[row - 1];
  if (!record) return;
  record[field] = value ?? '';
  if (field === 'optimizerName') matchOptimizer(record);
  if (field === 'optimizerId') {
    record.optimizerName =
      optimizerOptions.value.find((option) => option.value === value)?.name ??
      '';
  }
  // 预检未写入时允许修正；已尝试写入的批次锁定内容，复用请求 ID 安全重试。
  if (importResult.value) {
    const errors = importResult.value.errors.filter(
      (error) => error.row > 0 && error.row !== row,
    );
    importResult.value = errors.length
      ? { ...importResult.value, errors }
      : undefined;
  }
}

async function loadOptimizerOptions() {
  const options: OptimizerOption[] = [];
  const seen = new Set<string>();
  for (let page = 1; ; page += 1) {
    const result = await getUserList({ page, pageSize: 200, status: 1 });
    for (const user of result.items) {
      if (seen.has(user.id) || user.status !== 1) continue;
      seen.add(user.id);
      const name = (user.realName || user.displayName || user.id).trim();
      options.push({ label: `${name}（${user.id}）`, name, value: user.id });
    }
    if (page * 200 >= result.total) break;
    if (!result.items.length)
      throw new Error('投手列表加载不完整，请重新上传重试');
  }
  optimizerOptions.value = options;
}

const statusMeta = computed(() => {
  const status = importResult.value?.status;
  if (status === 'success') {
    return { message: '全部代理线导入成功', type: 'success' as const };
  }
  if (status === 'partial') {
    return {
      message:
        '部分代理线已导入；失败行保留请求 ID，可在正式后端确认最终状态后安全重试',
      type: 'warning' as const,
    };
  }
  if (status === 'validation_failed') {
    return {
      message: '导入未执行：请先修正全部校验错误',
      type: 'error' as const,
    };
  }
  if (status === 'failed') {
    return { message: '导入失败，未能保存代理线', type: 'error' as const };
  }
  return undefined;
});

function createRequestId(prefix: string) {
  const suffix =
    typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function ensureRequestId(row: number) {
  requestIdsByRow.value[row] ??= createRequestId(`agency-line-import-${row}`);
  return requestIdsByRow.value[row];
}

function parseCsv(text: string): ImportRecord[] {
  const matrix: string[][] = [];
  let cell = '';
  let currentRow: string[] = [];
  let quoted = false;

  const normalized = text.replace(/^\uFEFF/, '');
  for (let index = 0; index < normalized.length; index += 1) {
    const char = normalized[index];
    const next = normalized[index + 1];
    if (char === '"') {
      if (quoted && next === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
      continue;
    }
    if (char === ',' && !quoted) {
      currentRow.push(cell.trim());
      cell = '';
      continue;
    }
    if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && next === '\n') index += 1;
      currentRow.push(cell.trim());
      if (currentRow.some(Boolean)) matrix.push(currentRow);
      currentRow = [];
      cell = '';
      continue;
    }
    cell += char;
  }
  currentRow.push(cell.trim());
  if (currentRow.some(Boolean)) matrix.push(currentRow);

  if (quoted) throw new Error('CSV 存在未闭合的引号');

  const headers = matrix.shift()?.map((header) => header.trim()) ?? [];
  if (headers.length === 0) throw new Error('CSV 缺少表头');
  if (new Set(headers).size !== headers.length) {
    throw new Error('CSV 表头存在重复字段');
  }
  if (matrix.some((values) => values.length > headers.length)) {
    throw new Error('CSV 数据列数超过表头列数');
  }
  return matrix.map((values) =>
    Object.fromEntries(
      headers.map((header, index) => [header, values[index] ?? '']),
    ),
  );
}

async function parseExcel(file: File): Promise<ImportRecord[]> {
  const XLSX = await import('xlsx');
  const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' });
  const firstSheetName = workbook.SheetNames[0];
  const worksheet = firstSheetName
    ? workbook.Sheets[firstSheetName]
    : undefined;
  if (!worksheet) throw new Error('Excel 文件中没有可读取的工作表');

  // Excel 与 CSV 统一转为表头对象，后续共用字段别名和业务校验。
  return XLSX.utils.sheet_to_json<ImportRecord>(worksheet, {
    defval: '',
    // 读取底层值而非 Excel 的科学计数法显示文本；长数值由领域校验提示精度风险。
    raw: true,
  });
}

function resetState() {
  rows.value = [];
  sourceFileName.value = '';
  fileError.value = '';
  parseErrors.value = [];
  fileErrorsOpen.value = false;
  optimizerOptions.value = [];
  retryableRows.value = [];
  importResult.value = undefined;
  requestIdsByRow.value = {};
}

function validateProjectRelations(
  parsedRows: ReturnType<typeof parseAgencyLineImportRows>['rows'],
) {
  const errors: AgencyLineImportError[] = [];
  for (const { input, row } of parsedRows) {
    if (!input.projectId) continue;
    const project = props.projects.find((item) => item.id === input.projectId);
    if (!project) {
      errors.push({
        code: 'invalid_value',
        field: 'projectId',
        message: `项目 ID 不存在：${input.projectId}`,
        row,
      });
      continue;
    }
  }
  return errors;
}

const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
  if (parsing.value || saving.value) return Upload.LIST_IGNORE;
  resetState();
  sourceFileName.value = file.name;
  const lowerName = file.name.toLowerCase();
  const isCsv = lowerName.endsWith('.csv');
  const isExcel = lowerName.endsWith('.xls') || lowerName.endsWith('.xlsx');
  if (!isCsv && !isExcel) {
    fileError.value = '仅支持 CSV、XLSX 或 XLS 格式的文件';
    return Upload.LIST_IGNORE;
  }
  if (file.size > MAX_IMPORT_FILE_BYTES) {
    fileError.value = '导入文件不能超过 2 MB';
    return Upload.LIST_IGNORE;
  }
  parsing.value = true;
  try {
    const parsedRows = isCsv
      ? parseCsv(await file.text())
      : await parseExcel(file);
    if (parsedRows.length === 0) throw new Error('文件中没有可导入的数据行');
    if (parsedRows.length > MAX_IMPORT_ROWS) {
      throw new Error(`单次最多导入 ${MAX_IMPORT_ROWS} 行`);
    }
    await loadOptimizerOptions();
    const editableRows = prepareAgencyLineImportRows(parsedRows);
    editableRows.forEach((record) => {
      if (!record.optimizerId) matchOptimizer(record);
      if (!Object.prototype.hasOwnProperty.call(record, 'projectName')) {
        const project = props.projects.find(
          (item) => item.id === record.projectId,
        );
        if (project || !record.projectId)
          record.projectName = project?.name ?? '';
      }
    });
    rows.value = editableRows;
    parseErrors.value = [...currentPreview.value.errors];
  } catch (error) {
    rows.value = [];
    parseErrors.value = [];
    fileError.value = error instanceof Error ? error.message : '文件解析失败';
  } finally {
    parsing.value = false;
  }
  return Upload.LIST_IGNORE;
};

async function downloadTemplate() {
  try {
    const { Workbook } = await import('exceljs');
    const workbook = new Workbook();
    const sheet = workbook.addWorksheet('代理线导入');
    // 设置整列为文本，用户新增行也不会因默认数字格式而舍入长 ID。
    sheet.columns = [
      '类型',
      '投放平台',
      '像素名称',
      '像素 ID',
      'Token',
      '测试代码',
      '代理线',
      '投放链接',
      '投手',
      '斗篷链接',
      '项目名称',
      '主页 ID',
    ].map((header, index) => ({
      header,
      width: [18, 16, 26, 24, 36, 24, 26, 48, 18, 48, 20, 24][index],
      style: { numFmt: '@' },
    }));
    sheet.addRow([
      'PWA',
      'facebook',
      'Facebook Purchase Pixel',
      '12345678901234567',
      'example-token',
      'test-001',
      '美国 Facebook 主线',
      'https://example.com/landing-page',
      '',
      'https://example.com/cloak',
      '美国市场项目',
      '123456789',
    ]);
    sheet.views = [{ state: 'frozen', ySplit: 1 }];
    const bytes = new Uint8Array(await workbook.xlsx.writeBuffer());
    const url = URL.createObjectURL(
      new Blob([bytes], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = '代理线批量导入模板.xlsx';
    anchor.click();
    URL.revokeObjectURL(url);
  } catch {
    message.error('模板生成失败，请重试');
  }
}

async function importRows() {
  if (saving.value || parsing.value) return;
  if (rows.value.length === 0) {
    message.warning('请先选择导入文件');
    return;
  }
  if (currentPreview.value.errors.length > 0) {
    message.warning('请先修正预览中的校验错误');
    return;
  }
  saving.value = true;
  try {
    const rowNumbers =
      retryableRows.value.length > 0
        ? retryableRows.value
        : rows.value.map((_, index) => index + 1);
    const sourceRows = rowNumbers.map(
      (row) => currentPreview.value.rows[row - 1],
    );
    rowNumbers.forEach((row) => ensureRequestId(row));
    const result = await agencyLineService.saveMany(sourceRows, {
      overwriteExisting: overwriteExisting.value,
      requestIdsByRow: requestIdsByRow.value,
      retry: retryableRows.value.length > 0,
      rowNumbers,
    });
    importResult.value = result;
    // 重试预检失败不应丢失原失败行范围，否则可能再次提交已成功的行。
    if (
      result.items.length ||
      result.errors.some((error) => error.recoverable)
    ) {
      retryableRows.value = [
        ...new Set(
          result.errors
            .filter((error) => error.recoverable && error.row > 0)
            .map((error) => error.row),
        ),
      ].sort((left, right) => left - right);
    }
    if (result.items.length > 0) emit('imported', result);
    if (result.status === 'success') {
      emit('update:open', false);
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : '批量导入失败');
  } finally {
    saving.value = false;
  }
}

function closeDrawer() {
  if (!saving.value && !parsing.value) emit('update:open', false);
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      resetState();
      overwriteExisting.value = false;
    }
  },
);
</script>

<template>
  <Drawer
    :open="open"
    root-class-name="ux-fixed-drawer"
    :z-index="zIndex"
    :closable="!saving && !parsing"
    :mask-closable="!saving && !parsing"
    title="批量导入代理线"
    width="min(960px, 100vw)"
    @close="closeDrawer"
  >
    <Alert class="mb-4" type="info" show-icon>
      <template #message>上传文件后，可在预览中修改并核对</template>
      <template #description>
        支持 CSV、XLSX 和
        XLS。必填：代理线、投放平台；投手可留空，填写姓名后自动匹配启用人员，重名取首个，请在预览中核对或重新选择
        ID。投放链接、主页 ID、类型、像素名称、像素
        ID、Token、测试代码、斗篷链接和关联项目选填，填写项目时必须使用项目名称。平台值使用
        facebook、google、tiktok 或 kwai，且须已启用对应媒体字典。
      </template>
    </Alert>

    <div class="mb-4 flex flex-wrap items-center gap-2">
      <Button class="" @click="downloadTemplate">
        <IconifyIcon icon="lucide:download" class="mr-1 size-4" />
        下载 Excel 模板
      </Button>
      <Tag v-if="sourceFileName" color="blue">{{ sourceFileName }}</Tag>
    </div>

    <Upload.Dragger
      :height="128"
      accept=".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      :before-upload="beforeUpload"
      :disabled="saving || parsing"
      :show-upload-list="false"
      :multiple="false"
    >
      <p class="text-primary flex justify-center text-2xl">
        <IconifyIcon icon="lucide:file-up" />
      </p>
      <p class="mt-2 font-medium text-slate-800">
        点击或拖拽 CSV / Excel 文件到这里
      </p>
      <p class="text-sm text-slate-500">一次最多导入一个文件</p>
    </Upload.Dragger>

    <div class="mt-4 space-y-2">
      <Checkbox
        v-model:checked="overwriteExisting"
        :disabled="editingLocked"
        @change="importResult = undefined"
      >
        覆盖同名代理线
      </Checkbox>
      <p class="text-muted-foreground m-0 text-sm">
        勾选后按代理线名称匹配：同名更新，未匹配新增。空值覆盖原内容，项目名称留空时保留原关联项目；预算、启停等模板外配置保持不变。
      </p>
      <p class="text-muted-foreground m-0 text-sm">
        像素 ID、主页 ID 请使用文本格式填写。已被 Excel 舍入的长 ID
        需从原始来源重新复制，修改显示格式无法恢复丢失的数字。
      </p>
    </div>

    <Alert
      v-if="fileError"
      class="mt-4"
      show-icon
      type="error"
      message="文件校验未通过"
      :description="fileError"
    />

    <Alert
      v-else-if="parseErrors.length > 0"
      class="mt-4"
      show-icon
      type="error"
    >
      <template #message>
        文件校验发现
        {{ parseErrors.length }} 个问题，可修正后重新提交，或在预览中修正。
        <button
          type="button"
          class="text-blue-600 underline hover:text-blue-700 focus-visible:outline"
          @click="fileErrorsOpen = true"
        >
          查看错误
        </button>
      </template>
    </Alert>

    <Alert
      v-if="statusMeta"
      class="mt-4"
      show-icon
      :type="statusMeta.type"
      :message="statusMeta.message"
    />

    <section v-if="rows.length > 0" class="mt-5 min-w-0">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 class="m-0 text-base font-semibold text-slate-900">导入预览</h3>
        <span class="text-sm text-slate-500">共 {{ rows.length }} 行</span>
      </div>
      <div class="max-w-full overflow-x-auto">
        <Table
          :columns="previewColumns"
          :data-source="previewRows"
          :loading="parsing"
          :pagination="false"
          :scroll="{ x: 2500, y: '50vh' }"
          row-key="_row"
        >
          <template #bodyCell="{ column, record, index }">
            <template v-if="column.key === 'sequence'">
              {{ record._row ?? index + 1 }}
            </template>
            <template v-else>
              <Select
                v-if="column.key === 'optimizerId'"
                :value="record.optimizerId || undefined"
                :options="optimizerOptions"
                :disabled="editingLocked"
                :status="
                  previewErrors.some(
                    (error) =>
                      error.row === record._row &&
                      error.field === 'optimizerId',
                  )
                    ? 'error'
                    : undefined
                "
                :aria-label="`第 ${record._row} 行投手 ID`"
                class="w-full"
                show-search
                allow-clear
                option-filter-prop="label"
                option-label-prop="value"
                @change="updatePreviewCell(record._row, 'optimizerId', $event)"
              />
              <Input.Password
                v-else-if="column.key === 'token'"
                :value="String(record.token ?? '')"
                :disabled="editingLocked"
                autocomplete="new-password"
                :aria-label="`第 ${record._row} 行 Token`"
                @update:value="updatePreviewCell(record._row, 'token', $event)"
              />
              <Input
                v-else
                :value="String(record[column.dataIndex as string] ?? '')"
                :disabled="editingLocked"
                :aria-label="`第 ${record._row} 行${column.title}`"
                :status="
                  previewErrors.some(
                    (error) =>
                      error.row === record._row && error.field === column.key,
                  )
                    ? 'error'
                    : undefined
                "
                @update:value="
                  updatePreviewCell(
                    record._row,
                    column.dataIndex as string,
                    $event,
                  )
                "
              />
            </template>
          </template>
        </Table>
        <p
          v-if="retryableRows.length > 0"
          class="text-muted-foreground mt-2 text-sm"
        >
          已提交的批次保留原数据供安全重试，请先重试失败行确认保存结果。
        </p>
      </div>
    </section>

    <section v-if="previewErrors.length > 0" class="mt-5">
      <h3 class="m-0 mb-3 text-base font-semibold text-red-600">
        需修正的问题
      </h3>
      <div class="max-h-56 space-y-2 overflow-y-auto">
        <Alert
          v-for="(error, index) in previewErrors"
          :key="`${error.row}-${error.field}-${index}`"
          type="error"
          show-icon
          :message="`${error.row ? `第 ${error.row} 行 · ` : ''}${error.message}${error.requestId ? ` · 请求 ID：${error.requestId}` : ''}`"
        />
      </div>
    </section>

    <Modal
      v-model:open="fileErrorsOpen"
      wrap-class-name="ux-fixed-modal"
      :z-index="zIndex === undefined ? undefined : zIndex + 1"
      title="导入文件错误"
      :footer="null"
      width="min(640px, 100vw)"
    >
      <p class="text-muted-foreground">
        以下为上传时的文件校验结果；修正进度请查看预览中的问题。
      </p>
      <div class="space-y-2">
        <Alert
          v-for="(error, index) in parseErrors"
          :key="index"
          type="error"
          show-icon
          :message="`第 ${error.row} 行 · ${error.message}`"
        />
      </div>
    </Modal>

    <template #footer>
      <div class="flex justify-end gap-3">
        <Button
          class="min-w-20"
          :disabled="saving || parsing"
          @click="closeDrawer"
        >
          取消
        </Button>
        <Button
          class="min-w-24"
          type="primary"
          :loading="saving"
          :disabled="
            parsing || rows.length === 0 || currentPreview.errors.length > 0
          "
          @click="importRows"
        >
          {{ retryableRows.length > 0 ? '重试失败行' : '确认导入' }}
        </Button>
      </div>
    </template>
  </Drawer>
</template>
