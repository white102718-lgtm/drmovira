<script lang="ts" setup>
/* eslint-disable vue/html-closing-bracket-newline, vue/html-self-closing, vue/multiline-html-element-content-newline */
import type {
  GoogleAccountId,
  GoogleDriveFile,
  GoogleMapping,
  GoogleMappingId,
  GoogleMappingPayload,
} from '#/api/data-integration';

import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Checkbox,
  DatePicker,
  Empty,
  Input,
  InputNumber,
  message,
  Modal,
  Radio,
  Select,
  Spin,
  Steps,
  Tabs,
  TimePicker,
} from 'ant-design-vue';

import {
  createGoogleMapping,
  getGoogleDriveFiles,
  getGoogleMappingDetail,
  getGoogleSheetColumns,
  getGoogleSheetTabs,
  syncGoogleMapping,
  updateGoogleMapping,
} from '#/api/data-integration';

type Direction = 'bidirectional' | 'read' | 'write';
type DateRangeType = 'current_month' | 'custom' | 'recent_days';
type Frequency = 'daily' | 'manual';
type ConflictStrategy = 'latest_wins' | 'sheets_wins' | 'system_wins';

interface OpenOptions {
  accountId: GoogleAccountId;
  email: string;
  mapping?: GoogleMapping;
}

interface SystemField {
  field: string;
  required: boolean;
  systemField: string;
  type: 'date' | 'number' | 'string';
}

interface FieldMapping extends SystemField {
  column?: string;
  columnName?: string;
}

interface RuleForm {
  conflictStrategy: ConflictStrategy;
  dateRange: string[];
  dateRangeType: DateRangeType;
  direction: Direction;
  name: string;
  recentDays: number;
  syncFrequency: Frequency;
  syncTime: string;
}

const emit = defineEmits<{ success: [] }>();
const TabPane = Tabs.TabPane;

const reportTypes = [
  {
    desc: '任务名称、花费、回流、点击等数据',
    label: '任务中心',
    value: 1,
  },
];
const directions: Array<{
  desc: string;
  disabled?: boolean;
  label: string;
  value: Direction;
}> = [
  {
    desc: '从 Google 表格拉取数据到系统',
    label: '← 读取 Google Sheets',
    value: 'read',
  },
  {
    desc: '将系统数据推送到 Google 表格',
    disabled: true,
    label: '写入 → Google Sheets',
    value: 'write',
  },
  {
    desc: '双向实时同步，以最新修改为准',
    disabled: true,
    label: '⇄ 双向同步',
    value: 'bidirectional',
  },
];
const frequencies: Array<{ label: string; value: Frequency }> = [
  { label: '每天自动同步', value: 'daily' },
  { label: '手动同步', value: 'manual' },
];
const systemFieldsMap: Record<number, SystemField[]> = {
  1: [
    { field: '日期', required: true, systemField: 'startDate', type: 'date' },
    {
      field: '项目名称',
      required: true,
      systemField: 'taskName',
      type: 'string',
    },
    {
      field: '任务线名称',
      required: true,
      systemField: 'subtaskName',
      type: 'string',
    },
    {
      field: '媒体平台',
      required: true,
      systemField: 'mediaPlacement',
      type: 'string',
    },
    {
      field: '花费金额',
      required: true,
      systemField: 'spendAmount',
      type: 'number',
    },
    {
      field: '回流金额',
      required: false,
      systemField: 'returnAmount',
      type: 'number',
    },
    {
      field: '展示次数',
      required: false,
      systemField: 'impressions',
      type: 'string',
    },
    {
      field: '点击量',
      required: false,
      systemField: 'clicks',
      type: 'string',
    },
    {
      field: '注册数',
      required: false,
      systemField: 'registrations',
      type: 'string',
    },
    {
      field: '购物次数',
      required: false,
      systemField: 'purchases',
      type: 'string',
    },
    {
      field: '订阅次数',
      required: false,
      systemField: 'subscriptions',
      type: 'string',
    },
  ],
};

const directionToApi: Record<Direction, number> = {
  bidirectional: 3,
  read: 1,
  write: 2,
};
const directionFromApi: Record<number, Direction> = {
  1: 'read',
  2: 'write',
  3: 'bidirectional',
};
const conflictToApi: Record<ConflictStrategy, number> = {
  latest_wins: 3,
  sheets_wins: 2,
  system_wins: 1,
};
const conflictFromApi: Record<number, ConflictStrategy> = {
  1: 'system_wins',
  2: 'sheets_wins',
  3: 'latest_wins',
};
const dateRangeToApi: Record<DateRangeType, number> = {
  current_month: 3,
  custom: 1,
  recent_days: 2,
};
const dateRangeFromApi: Record<number, DateRangeType> = {
  1: 'custom',
  2: 'recent_days',
  3: 'current_month',
};
const frequencyToApi: Record<Frequency, number> = { daily: 2, manual: 1 };
const frequencyFromApi: Record<number, Frequency> = {
  1: 'manual',
  2: 'daily',
};

const modalOpen = ref(false);
const loading = ref(false);
const saving = ref(false);
const isEdit = ref(false);
const editMappingId = ref<GoogleMappingId>();
const currentStep = ref(0);
const currentAccount = ref<{ accountId: GoogleAccountId; email: string }>();
const selectedReport = ref(1);
const searchKeyword = ref('');
const googleFilesData = ref<GoogleDriveFile[]>([]);
const currentFileTabs = ref<string[]>([]);
const selectedFile = ref<GoogleDriveFile>();
const selectedSheets = ref<string[]>([]);
const fieldMappingData = reactive<Record<string, FieldMapping[]>>({});
const sheetColumnsMap = reactive<Record<string, string[]>>({});
const activeTab = ref('');
const showMappingErrors = ref(false);
let searchTimer: number | undefined;

const form = reactive<RuleForm>({
  conflictStrategy: 'system_wins',
  dateRange: [],
  dateRangeType: 'recent_days',
  direction: 'read',
  name: '',
  recentDays: 7,
  syncFrequency: 'daily',
  syncTime: '00:00',
});

const filteredFiles = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase();
  if (!keyword) return googleFilesData.value;
  return googleFilesData.value.filter((file) =>
    file.name.toLowerCase().includes(keyword),
  );
});
const systemFields = computed(
  () => systemFieldsMap[selectedReport.value] ?? [],
);
const currentTabMappings = computed(
  () => fieldMappingData[activeTab.value] ?? [],
);
const googleColumns = computed(() =>
  (sheetColumnsMap[activeTab.value] ?? []).map((name, index) => ({
    label: `${indexToLetter(index)}列 — ${name}`,
    name,
    value: indexToLetter(index),
  })),
);
const reportTypeLabel = computed(
  () =>
    reportTypes.find((report) => report.value === selectedReport.value)
      ?.label ?? '—',
);
const directionLabel = computed(
  () =>
    ({
      bidirectional: '双向同步',
      read: '读取 Sheets',
      write: '写入 Sheets',
    })[form.direction],
);
const dateRangeLabel = computed(() => {
  if (form.dateRangeType === 'current_month') return '本月';
  if (form.dateRangeType === 'recent_days') return `最近 ${form.recentDays} 天`;
  return form.dateRange.length === 2
    ? `${form.dateRange[0]} 至 ${form.dateRange[1]}`
    : '—';
});
const syncFreqLabel = computed(() =>
  form.syncFrequency === 'manual' ? '仅手动同步' : `每天 ${form.syncTime}`,
);
const mappedFieldCount = computed(() =>
  Object.values(fieldMappingData).reduce(
    (count, mappings) =>
      count + mappings.filter((mapping) => mapping.column).length,
    0,
  ),
);
const canGoNext = computed(() =>
  currentStep.value === 0
    ? Boolean(
        selectedReport.value &&
          selectedFile.value &&
          selectedSheets.value.length > 0,
      )
    : true,
);

function indexToLetter(index: number) {
  let letter = '';
  let value = index + 1;
  while (value > 0) {
    letter = String.fromCodePoint(65 + ((value - 1) % 26)) + letter;
    value = Math.floor((value - 1) / 26);
  }
  return letter;
}

function parseJson<T>(value: unknown, fallback: T): T {
  if (value && typeof value === 'object') return value as T;
  if (typeof value !== 'string') return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function clearRecord(record: Record<string, unknown>) {
  for (const key of Object.keys(record)) delete record[key];
}

function resetState() {
  currentStep.value = 0;
  isEdit.value = false;
  editMappingId.value = undefined;
  selectedReport.value = 1;
  searchKeyword.value = '';
  googleFilesData.value = [];
  currentFileTabs.value = [];
  selectedFile.value = undefined;
  selectedSheets.value = [];
  clearRecord(fieldMappingData);
  clearRecord(sheetColumnsMap);
  activeTab.value = '';
  showMappingErrors.value = false;
  Object.assign(form, {
    conflictStrategy: 'system_wins',
    dateRange: [],
    dateRangeType: 'recent_days',
    direction: 'read',
    name: '',
    recentDays: 7,
    syncFrequency: 'daily',
    syncTime: '00:00',
  } satisfies RuleForm);
}

async function loadDriveFiles(keyword?: string) {
  if (!currentAccount.value) return;
  googleFilesData.value = await getGoogleDriveFiles({
    accountId: currentAccount.value.accountId,
    ...(keyword ? { keyword } : {}),
  });
}

async function fillEditData(mapping: GoogleMapping) {
  if (!currentAccount.value) return;
  selectedReport.value = mapping.reportType;
  selectedFile.value = {
    id: mapping.spreadsheetId,
    modifiedTime: mapping.spreadsheetModifiedTime,
    name: mapping.spreadsheetName,
  };
  const tabs = await getGoogleSheetTabs({
    accountId: currentAccount.value.accountId,
    fileId: mapping.spreadsheetId,
  });
  currentFileTabs.value = tabs.map((tab) => tab.title);
  selectedSheets.value = parseJson<string[]>(mapping.sheetNames, []);
  form.name = mapping.name ?? '';
  form.direction = directionFromApi[mapping.syncDirection ?? 1] ?? 'read';
  form.conflictStrategy =
    conflictFromApi[mapping.conflictStrategy ?? 1] ?? 'system_wins';
  form.syncFrequency = frequencyFromApi[mapping.syncFrequency ?? 2] ?? 'daily';
  form.syncTime = mapping.syncTime ?? '00:00';
  form.dateRangeType =
    dateRangeFromApi[mapping.dateRangeType ?? 2] ?? 'recent_days';
  const dateConfig = parseJson<Record<string, number | string>>(
    mapping.dateRangeConfig,
    {},
  );
  if (form.dateRangeType === 'custom') {
    form.dateRange = [
      String(dateConfig.startDate ?? ''),
      String(dateConfig.endDate ?? ''),
    ];
  } else if (form.dateRangeType === 'recent_days') {
    form.recentDays = Number(dateConfig.days) || 7;
  }

  const savedMappings = parseJson<
    Record<string, GoogleMappingPayload['fieldMappings'][string]>
  >(mapping.fieldMappings, {});
  for (const sheet of selectedSheets.value) {
    const savedRows = savedMappings[sheet] ?? [];
    fieldMappingData[sheet] = (systemFieldsMap[mapping.reportType] ?? []).map(
      (field) => {
        const saved = savedRows.find(
          (item) => item.systemField === field.systemField,
        );
        return {
          ...field,
          column: saved?.sheetColumn,
          columnName: saved?.sheetColumnName,
        };
      },
    );
  }
}

async function open(options: OpenOptions) {
  resetState();
  currentAccount.value = {
    accountId: options.accountId,
    email: options.email,
  };
  isEdit.value = Boolean(options.mapping);
  editMappingId.value = options.mapping?.id;
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  form.dateRange = [
    firstDay.toISOString().slice(0, 10),
    today.toISOString().slice(0, 10),
  ];
  modalOpen.value = true;
  loading.value = true;
  try {
    await loadDriveFiles();
    if (options.mapping) {
      const detail = await getGoogleMappingDetail(options.mapping.id);
      await fillEditData(detail);
    }
  } finally {
    loading.value = false;
  }
}

function close() {
  modalOpen.value = false;
}

function requestClose() {
  Modal.confirm({
    content: '当前配置尚未保存，是否放弃？',
    okButtonProps: { danger: true },
    okText: '放弃',
    title: '放弃配置',
    onOk: close,
  });
}

async function selectFile(file: GoogleDriveFile) {
  if (!currentAccount.value) return;
  selectedFile.value = file;
  selectedSheets.value = [];
  currentFileTabs.value = [];
  const tabs = await getGoogleSheetTabs({
    accountId: currentAccount.value.accountId,
    fileId: file.id,
  });
  currentFileTabs.value = tabs.map((tab) => tab.title);
}

async function loadSheetColumns() {
  if (!currentAccount.value || !selectedFile.value) return;
  await Promise.all(
    selectedSheets.value.map(async (sheetName) => {
      if (sheetColumnsMap[sheetName]) return;
      sheetColumnsMap[sheetName] = await getGoogleSheetColumns({
        accountId: currentAccount.value!.accountId,
        fileId: selectedFile.value!.id,
        sheetName,
      });
    }),
  );
}

function initFieldMappings() {
  for (const sheet of selectedSheets.value) {
    if (fieldMappingData[sheet]) continue;
    const columns = sheetColumnsMap[sheet] ?? [];
    let sequentialIndex = 0;
    fieldMappingData[sheet] = systemFields.value.map((field) => {
      const matchingIndex = columns.findIndex(
        (column) => column && column.includes(field.field),
      );
      if (matchingIndex !== -1) {
        return {
          ...field,
          column: indexToLetter(matchingIndex),
          columnName: columns[matchingIndex],
        };
      }
      const columnName = columns[sequentialIndex];
      const result = columnName
        ? {
            column: indexToLetter(sequentialIndex),
            columnName,
          }
        : {};
      sequentialIndex += 1;
      return { ...field, ...result };
    });
  }
}

async function handleNext() {
  if (currentStep.value === 0) {
    loading.value = true;
    try {
      await loadSheetColumns();
      initFieldMappings();
      form.name ||= `${reportTypeLabel.value}同步`;
      activeTab.value = selectedSheets.value[0] ?? '';
    } finally {
      loading.value = false;
    }
  } else if (currentStep.value === 1) {
    const firstErrorSheet = selectedSheets.value.find((sheet) =>
      (fieldMappingData[sheet] ?? []).some(
        (mapping) => mapping.required && !mapping.column,
      ),
    );
    if (firstErrorSheet) {
      showMappingErrors.value = true;
      activeTab.value = firstErrorSheet;
      message.warning('请为所有必填字段选择对应列');
      return;
    }
    showMappingErrors.value = false;
  }
  currentStep.value += 1;
}

function updateColumnName(mapping: FieldMapping) {
  mapping.columnName = googleColumns.value.find(
    (column) => column.value === mapping.column,
  )?.name;
}

function buildFieldMappings(): GoogleMappingPayload['fieldMappings'] {
  return Object.fromEntries(
    Object.entries(fieldMappingData).map(([sheetName, mappings]) => [
      sheetName,
      mappings
        .filter((mapping) => mapping.column)
        .map((mapping) => ({
          sheetColumn: mapping.column!,
          sheetColumnName: mapping.columnName ?? mapping.column!,
          systemField: mapping.systemField,
        })),
    ]),
  );
}

function buildDateRangeConfig(): Record<string, number | string> {
  if (form.dateRangeType === 'custom') {
    return {
      endDate: form.dateRange[1] ?? '',
      startDate: form.dateRange[0] ?? '',
    };
  }
  return form.dateRangeType === 'recent_days' ? { days: form.recentDays } : {};
}

async function handleSave() {
  if (!currentAccount.value || !selectedFile.value) return;
  if (!form.name.trim()) {
    message.error('请输入配置名称');
    return;
  }
  const payload: GoogleMappingPayload = {
    conflictStrategy: conflictToApi[form.conflictStrategy],
    dateRangeConfig: buildDateRangeConfig(),
    dateRangeType: dateRangeToApi[form.dateRangeType],
    fieldMappings: buildFieldMappings(),
    googleAccountId: currentAccount.value.accountId,
    name: form.name.trim(),
    reportType: selectedReport.value,
    sheetNames: [...selectedSheets.value],
    spreadsheetId: selectedFile.value.id,
    spreadsheetModifiedTime: selectedFile.value.modifiedTime,
    spreadsheetName: selectedFile.value.name,
    syncDirection: directionToApi[form.direction],
    syncFrequency: frequencyToApi[form.syncFrequency],
    syncTime: form.syncTime,
  };
  saving.value = true;
  try {
    let mappingId = editMappingId.value;
    if (isEdit.value && mappingId !== undefined) {
      await updateGoogleMapping({ ...payload, id: mappingId });
    } else {
      mappingId = await createGoogleMapping(payload);
    }
    if (mappingId !== undefined) await syncGoogleMapping(mappingId);
    message.success('配置已保存，同步已触发');
    emit('success');
    close();
  } finally {
    saving.value = false;
  }
}

watch(searchKeyword, (keyword) => {
  if (!modalOpen.value || !currentAccount.value) return;
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    void loadDriveFiles(keyword.trim() || undefined);
  }, 400);
});

onBeforeUnmount(() => {
  if (searchTimer) window.clearTimeout(searchTimer);
});

defineExpose({ open });
</script>

<template>
  <Modal
    v-model:open="modalOpen"
    :body-style="{ maxHeight: '72dvh', overflowY: 'auto' }"
    :closable="false"
    :footer="null"
    :mask-closable="false"
    :style="{ top: '24px' }"
    :width="1100"
    destroy-on-close
  >
    <template #title>
      <div class="flex items-center gap-3">
        <span
          class="flex size-9 items-center justify-center rounded-xl bg-blue-50 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400"
        >
          <IconifyIcon icon="lucide:table-properties" />
        </span>
        <div>
          <div class="text-base font-semibold">
            {{ isEdit ? '编辑映射配置' : '新建映射配置' }}
          </div>
          <div class="mt-0.5 text-xs font-normal text-slate-500">
            {{ currentAccount?.email || 'Google Sheets 数据同步' }}
          </div>
        </div>
      </div>
    </template>
    <Spin :spinning="loading">
      <div
        class="mb-6 rounded-xl border border-slate-100 bg-slate-50/80 px-6 py-4 sm:px-12 dark:border-slate-800 dark:bg-slate-800/50"
      >
        <Steps
          :current="currentStep"
          :items="[
            { description: '选择数据来源', title: '选择表格' },
            { description: '关联两端字段', title: '字段映射' },
            { description: '设置同步方式', title: '同步规则' },
          ]"
        />
      </div>

      <div
        v-if="currentStep === 0"
        class="grid min-h-[390px] gap-6 md:grid-cols-[300px_1fr]"
      >
        <section
          class="border-b border-slate-200 pb-5 md:border-b-0 md:border-r md:pb-0 md:pr-6 dark:border-slate-700"
        >
          <h3 class="m-0 text-sm font-semibold">选择系统报表</h3>
          <p class="mb-4 mt-1 text-xs text-slate-500">
            选择要与 Google Sheets 关联的报表类型
          </p>
          <Button
            v-for="report in reportTypes"
            :key="report.value"
            block
            class="!flex !items-center !justify-start !gap-3 !p-3.5 !text-left"
            :class="
              selectedReport === report.value
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30'
                : 'border-slate-200 hover:border-blue-400 dark:border-slate-700'
            "
            @click="selectedReport = report.value"
          >
            <span
              class="rounded-md bg-blue-100 p-2 text-blue-600 dark:bg-blue-950"
            >
              <IconifyIcon icon="lucide:file-spreadsheet" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block text-sm font-medium">{{ report.label }}</span>
              <span class="block text-xs text-slate-500">{{
                report.desc
              }}</span>
            </span>
            <IconifyIcon
              v-if="selectedReport === report.value"
              class="text-blue-600"
              icon="lucide:check"
            />
          </Button>
        </section>

        <section class="min-w-0">
          <h3 class="m-0 text-sm font-semibold">选择 Google 表格</h3>
          <p class="mb-4 mt-1 text-xs text-slate-500">
            从你的 Google Drive 中选择一个表格文件
          </p>
          <Input.Search
            v-model:value="searchKeyword"
            allow-clear
            class="!rounded-lg"
            placeholder="搜索表格名称..."
          />
          <div
            class="mt-3 max-h-[230px] overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-700"
          >
            <Button
              v-for="file in filteredFiles"
              :key="file.id"
              block
              class="!flex !items-center !justify-start !gap-3 !rounded-none !border-0 !border-b !p-3.5 !text-left last:!border-b-0"
              :class="
                selectedFile?.id === file.id
                  ? 'bg-blue-50 dark:bg-blue-950/30'
                  : 'hover:bg-slate-50 dark:hover:bg-slate-800'
              "
              @click="selectFile(file)"
            >
              <span class="rounded bg-emerald-600 p-1.5 text-white"
                ><IconifyIcon icon="lucide:sheet"
              /></span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-medium">{{
                  file.name
                }}</span>
                <span class="block text-xs text-slate-500"
                  >修改于 {{ file.modifiedTime?.slice(0, 10) || '—' }}</span
                >
              </span>
              <IconifyIcon
                v-if="selectedFile?.id === file.id"
                class="text-blue-600"
                icon="lucide:check"
              />
            </Button>
            <Empty
              v-if="filteredFiles.length === 0"
              :image="Empty.PRESENTED_IMAGE_SIMPLE"
              description="未找到表格"
            />
          </div>

          <div v-if="selectedFile" class="mt-5">
            <div class="text-sm font-medium">
              选择 Sheets
              <span class="font-normal text-slate-500">（可多选）</span>
            </div>
            <p class="mb-3 mt-1 text-xs text-slate-500">
              选择该表格中需要关联的工作表
            </p>
            <Checkbox.Group
              v-model:value="selectedSheets"
              :options="currentFileTabs"
            />
          </div>
        </section>
      </div>

      <div v-else-if="currentStep === 1" class="min-h-[390px]">
        <Tabs
          v-if="selectedSheets.length > 1"
          v-model:active-key="activeTab"
          size="small"
        >
          <TabPane v-for="sheet in selectedSheets" :key="sheet" :tab="sheet" />
        </Tabs>
        <div
          class="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700"
        >
          <div class="min-w-[840px] overflow-hidden">
            <div
              class="bg-muted text-muted-foreground grid grid-cols-[1fr_110px_1fr] text-xs font-semibold"
            >
              <div class="border-r border-slate-200 p-3 dark:border-slate-700">
                系统字段 · {{ reportTypeLabel }}
              </div>
              <div
                class="border-r border-slate-200 p-3 text-center dark:border-slate-700"
              >
                映射
              </div>
              <div class="p-3">
                GOOGLE SHEET 列 · {{ selectedFile?.name }} › {{ activeTab }}
              </div>
            </div>
            <div
              v-for="mapping in currentTabMappings"
              :key="mapping.systemField"
              class="grid min-h-12 grid-cols-[1fr_110px_1fr] items-center border-t border-slate-100 text-sm transition-colors hover:bg-slate-50/60 dark:border-slate-800 dark:hover:bg-slate-800/30"
              :class="
                showMappingErrors && mapping.required && !mapping.column
                  ? 'bg-red-50 dark:bg-red-950/20'
                  : ''
              "
            >
              <div
                class="flex items-center gap-2 border-r border-slate-200 px-3 py-2 dark:border-slate-700"
              >
                <span
                  class="size-2 rounded-full"
                  :class="mapping.column ? 'bg-blue-500' : 'bg-slate-300'"
                />
                <span class="min-w-0 flex-1"
                  >{{ mapping.field
                  }}<span v-if="mapping.required" class="text-red-500"
                    >*</span
                  ></span
                >
                <span
                  class="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500 dark:bg-slate-700"
                  >{{ mapping.type }}</span
                >
              </div>
              <div
                class="border-r border-slate-200 text-center text-xs dark:border-slate-700"
                :class="mapping.column ? 'text-blue-600' : 'text-slate-400'"
              >
                {{ mapping.column ? '— — →' : '— 忽略 —' }}
              </div>
              <div class="flex items-center gap-2 px-3 py-2">
                <Select
                  v-model:value="mapping.column"
                  allow-clear
                  class="min-w-0 flex-1"
                  :options="googleColumns"
                  placeholder="选择列..."
                  @change="updateColumnName(mapping)"
                />
                <span
                  class="w-10 text-xs"
                  :class="mapping.column ? 'text-green-600' : 'text-slate-400'"
                  >{{ mapping.column ? '已匹配' : '忽略' }}</span
                >
              </div>
            </div>
          </div>
        </div>
        <Alert
          class="mt-3"
          message="日期字段已设为同步主键，系统将按日期匹配和更新数据行"
          show-icon
          type="warning"
        />
      </div>

      <div v-else class="grid min-h-[390px] gap-5 md:grid-cols-[1fr_280px]">
        <div class="space-y-4">
          <section
            class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
          >
            <h3 class="mb-3 mt-0 text-sm font-semibold">配置名称</h3>
            <Input
              v-model:value="form.name"
              :maxlength="100"
              placeholder="请输入配置名称"
              show-count
            />
          </section>
          <section
            class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
          >
            <h3 class="m-0 text-sm font-semibold">同步方向</h3>
            <p class="mb-3 mt-1 text-xs text-slate-500">选择数据流向</p>
            <Radio.Group
              v-model:value="form.direction"
              class="flex w-full flex-col gap-2"
            >
              <label
                v-for="direction in directions"
                :key="direction.value"
                class="rounded-xl border p-3.5 transition-colors"
                :class="[
                  form.direction === direction.value
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-950/30'
                    : 'border-slate-200 dark:border-slate-700',
                  direction.disabled
                    ? 'cursor-not-allowed opacity-50'
                    : 'cursor-pointer',
                ]"
              >
                <Radio
                  :disabled="direction.disabled"
                  :value="direction.value"
                  >{{ direction.label }}</Radio
                >
                <div class="ml-6 mt-1 text-xs text-slate-500">
                  {{ direction.desc }}
                </div>
              </label>
            </Radio.Group>
          </section>
          <section
            v-if="form.direction === 'bidirectional'"
            class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
          >
            <h3 class="mb-3 mt-0 text-sm font-semibold">冲突处理</h3>
            <Select
              v-model:value="form.conflictStrategy"
              class="w-full"
              :options="[
                {
                  label: '以系统数据为准（覆盖 Sheets）',
                  value: 'system_wins',
                },
                {
                  label: '以 Sheets 数据为准（覆盖系统）',
                  value: 'sheets_wins',
                },
                { label: '以最后修改时间为准', value: 'latest_wins' },
              ]"
            />
          </section>
          <section
            class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
          >
            <h3 class="m-0 text-sm font-semibold">日期范围</h3>
            <p class="mb-3 mt-1 text-xs text-slate-500">
              按日期筛选同步的数据范围
            </p>
            <Radio.Group
              v-model:value="form.dateRangeType"
              button-style="solid"
            >
              <Radio.Button value="recent_days">最近 N 天</Radio.Button>
              <Radio.Button disabled value="current_month">本月</Radio.Button>
              <Radio.Button disabled value="custom">自定义区间</Radio.Button>
            </Radio.Group>
            <div
              v-if="form.dateRangeType === 'recent_days'"
              class="mt-3 flex items-center gap-2"
            >
              <InputNumber
                v-model:value="form.recentDays"
                :max="365"
                :min="1"
                disabled
              />
              <span>天</span>
            </div>
            <DatePicker.RangePicker
              v-else-if="form.dateRangeType === 'custom'"
              class="mt-3 w-full"
              disabled
            />
          </section>
          <section
            class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
          >
            <h3 class="m-0 text-sm font-semibold">自动同步频率</h3>
            <p class="mb-3 mt-1 text-xs text-slate-500">
              设置定时自动同步的间隔
            </p>
            <Radio.Group
              v-model:value="form.syncFrequency"
              class="flex flex-col gap-2"
            >
              <Radio
                v-for="frequency in frequencies"
                :key="frequency.value"
                :value="frequency.value"
                >{{ frequency.label }}</Radio
              >
            </Radio.Group>
            <div
              v-if="form.syncFrequency === 'daily'"
              class="mt-3 flex items-center gap-2 text-sm"
            >
              <span>同步时间：</span
              ><TimePicker
                v-model:value="form.syncTime as any"
                disabled
                format="HH:mm"
                value-format="HH:mm"
              />
            </div>
          </section>
        </div>

        <aside
          class="sticky top-0 h-fit rounded-xl border border-green-200 bg-green-50 p-5 shadow-sm dark:border-green-900 dark:bg-green-950/30"
        >
          <h3 class="mb-4 mt-0 text-sm font-semibold">配置摘要</h3>
          <dl class="m-0 space-y-3 text-sm">
            <div class="flex justify-between gap-3">
              <dt class="text-slate-500">报表类型</dt>
              <dd class="m-0 text-right font-medium">{{ reportTypeLabel }}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-slate-500">关联表格</dt>
              <dd class="m-0 break-all text-right font-medium">
                {{ selectedFile?.name || '—' }}
              </dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-slate-500">关联 Sheets</dt>
              <dd class="m-0 break-all text-right font-medium">
                {{ selectedSheets.join(', ') || '—' }}
              </dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-slate-500">已映射字段</dt>
              <dd class="m-0 text-right font-medium">
                {{ mappedFieldCount }} 个字段
              </dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-slate-500">同步方向</dt>
              <dd class="m-0 text-right font-medium">{{ directionLabel }}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-slate-500">日期范围</dt>
              <dd class="m-0 text-right font-medium">{{ dateRangeLabel }}</dd>
            </div>
            <div class="flex justify-between gap-3">
              <dt class="text-slate-500">自动同步</dt>
              <dd class="m-0 text-right font-medium">{{ syncFreqLabel }}</dd>
            </div>
          </dl>
        </aside>
      </div>

      <footer
        class="sticky -bottom-4 z-10 -mx-1 mt-6 flex items-center justify-between border-t border-slate-200 bg-white/95 px-1 pt-4 backdrop-blur dark:border-slate-700 dark:bg-slate-900/95"
      >
        <Button class="!rounded-lg" @click="requestClose">取消</Button>
        <div class="flex gap-2">
          <Button
            v-if="currentStep > 0"
            class="!rounded-lg"
            @click="currentStep -= 1"
            >上一步</Button
          >
          <Button
            v-if="currentStep < 2"
            :disabled="!canGoNext"
            class="!rounded-lg !px-5"
            type="primary"
            @click="handleNext"
            >下一步</Button
          >
          <Button
            v-else
            :loading="saving"
            class="!rounded-lg !px-5"
            type="primary"
            @click="handleSave"
            >保存并立即同步</Button
          >
        </div>
      </footer>
    </Spin>
  </Modal>
</template>
