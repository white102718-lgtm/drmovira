<script setup lang="ts">
import type {
  DeliveryLineOption,
  DeliveryMetrics,
  DeliveryReportResult,
  DeliveryReportRow,
} from '#/api/delivery-report';
import type { TableColumnsType } from 'ant-design-vue';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';
import { useAccess } from '@vben/access';
import { IconifyIcon } from '@vben/icons';
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Image,
  Input,
  InputNumber,
  Modal,
  Popover,
  Select,
  Table,
  Upload,
  message,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { deliveryReportApi } from '#/api/delivery-report';
import { createReportWorkbook, downloadReportWorkbook } from './report-excel';
import type { ReportExportRow } from './report-excel';
import { uploadDailyReportAttachment } from '#/api/daily-report';
import { downloadStoredFileApi } from '#/api/file';
import DeliveryReportGooglePushModal from './DeliveryReportGooglePushModal.vue';
import DeliveryReportGoogleTemplateModal from './DeliveryReportGoogleTemplateModal.vue';

const props = withDefaults(
  defineProps<{
    performance?: boolean;
    readOnly?: boolean;
    detailDays?: DeliveryReportResult[];
    reporterId?: string;
  }>(),
  {
    performance: false,
    readOnly: false,
  },
);
const emit = defineEmits<{ saved: [] }>();
const { hasAccessByCodes } = useAccess();

interface EditorRow extends DeliveryReportRow {
  /** 手工新增行的编辑标记，不使用金额是否为零判断来源。 */
  reportDate?: string;
  reporterName?: string;
  manual: boolean;
  key: string;
  uploading: boolean;
}
type NumericMetric = Exclude<
  keyof DeliveryMetrics,
  'adjustmentType' | 'remark'
>;
const numericFields: { key: NumericMetric; title: string; money?: boolean }[] =
  [
    { key: 'dailySpend', title: '日报消耗', money: true },
    { key: 'impressions', title: '展示' },
    { key: 'clicks', title: '点击' },
    { key: 'installs', title: '账户内安装' },
    { key: 'registrations', title: '账户内注册' },
    { key: 'firstPurchases', title: '账户内首购' },
    { key: 'adjustmentAmount', title: '调整金额', money: true },
    { key: 'secondaryDeduction', title: '二次核减', money: true },
  ];
const date = ref(dayjs().subtract(1, 'day'));
const dateRange = ref<[ReturnType<typeof dayjs>, ReturnType<typeof dayjs>]>([
  dayjs().subtract(1, 'day'),
  dayjs().subtract(1, 'day'),
]);
type ReadRange = { startDate: string; endDate: string };
const loadedRange = ref<ReadRange | null>(null);
function selectedRange(): ReadRange {
  return {
    startDate: dateRange.value[0].format('YYYY-MM-DD'),
    endDate: dateRange.value[1].format('YYYY-MM-DD'),
  };
}
const loadedDate = ref('');
const rows = ref<EditorRow[]>([]);
const options = ref<DeliveryLineOption[]>([]);
const reporterName = ref('');
const unmatchedCount = ref(0);
const loading = ref(false);
const saving = ref(false);
const exporting = ref(false);
const dirty = ref(false);
const error = ref(false);
const previews = ref<Record<string, string>>({});
const screenshotRow = ref<EditorRow | null>(null);
const screenshotOpen = ref(false);
const screenshotLoading = ref(false);
let previewRequest = 0;
const viewOnly = computed(() => props.performance || props.readOnly);
const reporterFilter = ref('');
const projectFilter = ref('');
const lineFilter = ref('');
const statsExpanded = ref(true);
const appliedFilters = ref({ reporter: '', project: '', line: '' });
const pageNumber = ref(1);
const pageSize = ref(20);
const totalRows = ref(0);
const statistics = ref({ count: 0, dailySpend: 0, actualSpend: 0 });
const statsLoading = ref(false);
const statsFailed = ref(false);
const statisticsRange = ref<ReadRange | null>(null);
const selectedRowKeys = ref<string[]>([]);
const googleTemplateModal = ref<{ show: () => Promise<void> }>();
const googlePushModal = ref<{
  show: (ids: string[]) => Promise<void>;
  showHistory: () => Promise<void>;
}>();
let statsSequence = 0;
const displayedRows = computed(() => rows.value);
const canManageGooglePush = computed(() =>
  hasAccessByCodes(['workbench:daily:report:push']),
);
const canPushGoogle = computed(
  () =>
    canManageGooglePush.value &&
    viewOnly.value &&
    !props.performance &&
    !props.detailDays,
);
const selectedReportIds = computed(() =>
  rows.value
    .filter((row) => selectedRowKeys.value.includes(row.key) && row.id)
    .map((row) => row.id as string),
);
const rowSelection = computed(() =>
  canPushGoogle.value
    ? {
        getCheckboxProps: (row: EditorRow) => ({ disabled: !row.id }),
        onChange: (keys: Array<number | string>) => {
          selectedRowKeys.value = keys.map(String);
        },
        selectedRowKeys: selectedRowKeys.value,
      }
    : undefined,
);
const summaryCards = computed(() => [
  {
    label: '已填日报',
    value: String(statistics.value.count),
    unit: '条',
    icon: 'lucide:files',
  },
  {
    label: '日报消耗合计',
    value: money(statistics.value.dailySpend),
    unit: 'USD',
    icon: 'lucide:wallet',
  },
  {
    label: '实际消耗合计',
    value: money(statistics.value.actualSpend),
    unit: 'USD',
    icon: 'lucide:chart-no-axes-combined',
  },
]);
async function loadStatistics(requestedRange: ReadRange) {
  statisticsRange.value = requestedRange;
  const request = ++statsSequence;
  statsLoading.value = true;
  statsFailed.value = false;
  try {
    const result = await deliveryReportApi.stats({
      ...requestedRange,
      reporterId: props.reporterId,
      ...appliedFilters.value,
    });
    if (!disposed && request === statsSequence) statistics.value = result;
  } catch {
    if (!disposed && request === statsSequence) statsFailed.value = true;
  } finally {
    if (!disposed && request === statsSequence) statsLoading.value = false;
  }
}
function changePage(pagination: { current?: number; pageSize?: number }) {
  if (!viewOnly.value || props.detailDays || loading.value) return;
  const size = pagination.pageSize || pageSize.value;
  pageNumber.value = size === pageSize.value ? pagination.current || 1 : 1;
  pageSize.value = size;
  void load(false);
}
function searchReports() {
  appliedFilters.value = {
    reporter: reporterFilter.value.trim(),
    project: projectFilter.value.trim(),
    line: lineFilter.value.trim(),
  };
  handleQuery();
}
function resetFilters() {
  reporterFilter.value = '';
  projectFilter.value = '';
  lineFilter.value = '';
  dateRange.value = [dayjs().subtract(1, 'day'), dayjs().subtract(1, 'day')];
  searchReports();
}
const pendingRows = computed(() => rows.value.filter((row) => !row.saved));

/** 日报列表只读；填写入口允许编辑当前日期的新行和历史已填记录。 */
function canEdit() {
  return !viewOnly.value;
}
let disposed = false;
let sequence = 0;
const uploading = computed(() => rows.value.some((row) => row.uploading));
const busy = computed(
  () => loading.value || saving.value || uploading.value || exporting.value,
);
const projects = computed(() => [
  ...new Map(
    options.value.map((line) => [
      line.projectId,
      { value: line.projectId, label: line.projectName },
    ]),
  ).values(),
]);
const platforms = computed(() =>
  [
    ...new Set([
      'facebook',
      'google',
      'tiktok',
      ...rows.value.map((row) => row.platform),
    ]),
  ].map((value) => ({ value, label: value })),
);
const adjustments = ['未设置', '公司承担', '本人承担'].map((value) => ({
  value,
  label: value,
}));
/** 金额字段说明与当前业务计算口径保持一致，支持鼠标和键盘查看。 */
const fieldHelp: Record<string, string> = {
  actualSpend:
    '平台同步的当日投放消耗，按项目、代理线和平台汇总。系统自动获取，不可修改；无平台数据时按 0 处理。',
  dailySpend:
    '投放师确认并记录的当日消耗。首次默认等于实际消耗，可按业务情况修改；保存后保留填写值。',
  returnSpend:
    '含回流消耗 = 实际消耗 − 调整金额。调整金额为负数时，相当于加上其绝对值；无平台数据时，实际消耗按 0 计算。',
  returnIncrease:
    '回流增加额 = 实际消耗 − 日报消耗。结果可以为负数；无平台数据时，实际消耗按 0 计算。',
};
const columns = computed<TableColumnsType<EditorRow>>(() => [
  { key: 'date', title: '日期', width: 130, fixed: 'left', align: 'left' },
  ...(viewOnly.value
    ? [
        {
          key: 'reporter',
          title: '投手姓名',
          width: 140,
          fixed: 'left' as const,
          align: 'left' as const,
        },
      ]
    : []),
  { key: 'project', title: '项目', width: 200 },
  { key: 'line', title: '代理线', width: 200 },
  { key: 'platform', title: '平台', width: 140 },
  { key: 'actualSpend', title: '实际消耗', width: 155, align: 'left' },
  ...numericFields
    .filter(
      (field) =>
        !props.performance ||
        ['dailySpend', 'adjustmentAmount', 'secondaryDeduction'].includes(
          field.key,
        ),
    )
    .map((field) => ({
      key: field.key,
      title: field.title,
      width: 145,
      align: 'left' as const,
    })),
  { key: 'adjustmentType', title: '调整承担', width: 145 },
  { key: 'returnSpend', title: '含回流消耗', width: 145, align: 'left' },
  { key: 'returnIncrease', title: '回流增加额', width: 145, align: 'left' },
  { key: 'remark', title: '备注', width: 220 },
  { key: 'attachments', title: '截图', width: 180 },
  ...(!viewOnly.value && pendingRows.value.some((row) => row.manual)
    ? [{ key: 'actions', title: '操作', width: 85, fixed: 'right' as const }]
    : []),
]);

function releasePreviews() {
  previewRequest++;
  screenshotOpen.value = false;
  screenshotRow.value = null;
  screenshotLoading.value = false;
  Object.values(previews.value).forEach((url) => URL.revokeObjectURL(url));
  previews.value = {};
}

watch(
  () => props.detailDays,
  (days) => {
    if (!days) return;
    releasePreviews();
    rows.value = days.flatMap((day) =>
      day.rows.map((row) => ({
        ...row,
        reportDate: day.date,
        reporterName: day.reporterName,
        manual: false,
        key: day.date + '-' + row.id,
        uploading: false,
      })),
    );
  },
  { immediate: true },
);

async function applyResult(result: DeliveryReportResult) {
  releasePreviews();
  rows.value = result.rows
    .filter((row) => !viewOnly.value || row.saved)
    .map((row) => ({
      ...row,
      manual: false,
      key: `row-${++sequence}`,
      uploading: false,
    }));
  loadedDate.value = result.date;
  reporterName.value = result.reporterName;
  unmatchedCount.value = result.unmatchedCount;
  dirty.value = false;
  error.value = false;
}

/** 只在点击查看后读取截图；快速切换或关闭后忽略过期响应。 */
async function showScreenshots(row: EditorRow) {
  screenshotRow.value = row;
  screenshotOpen.value = true;
  screenshotLoading.value = true;
  const request = ++previewRequest;
  const results = await Promise.allSettled(
    row.attachments.map(async (file) => {
      if (previews.value[file.id]) return;
      const blob = await downloadStoredFileApi(file.id);
      if (!disposed && screenshotOpen.value && request === previewRequest) {
        previews.value[file.id] = URL.createObjectURL(blob);
      }
    }),
  );
  if (request !== previewRequest || disposed) return;
  screenshotLoading.value = false;
  if (results.some((result) => result.status === 'rejected'))
    message.warning('部分截图加载失败，可点击重试');
}

function closeScreenshots() {
  previewRequest++;
  screenshotLoading.value = false;
}

async function load(refreshStatistics = true) {
  loading.value = true;
  try {
    if (viewOnly.value) {
      const requestedRange = refreshStatistics
        ? selectedRange()
        : loadedRange.value || selectedRange();
      if (refreshStatistics) {
        pageNumber.value = 1;
        void loadStatistics(requestedRange);
      }
      const response = await deliveryReportApi.page({
        ...requestedRange,
        reporterId: props.reporterId,
        page: pageNumber.value,
        pageSize: pageSize.value,
        ...appliedFilters.value,
      });
      const days = response.days;
      totalRows.value = Number(response.total);
      if (disposed) return;
      releasePreviews();
      selectedRowKeys.value = [];
      rows.value = days.flatMap((day) =>
        day.rows.map((row) => ({
          ...row,
          reportDate: day.date,
          reporterName: day.reporterName,
          manual: false,
          key: day.reporterId + '-' + day.date + '-' + row.id,
          uploading: false,
        })),
      );
      loadedRange.value = requestedRange;
      loadedDate.value = requestedRange.startDate;
      reporterName.value = days.length === 1 ? days[0]!.reporterName : '';
      unmatchedCount.value = 0;
      error.value = false;
      dirty.value = false;
      return;
    }
    const result = await deliveryReportApi.query(
      date.value.format('YYYY-MM-DD'),
    );
    if (!disposed) await applyResult(result);
  } catch {
    error.value = true;
    if (viewOnly.value) rows.value = [];
    message.error('日报查询失败，原有填写内容已保留，请检查后重试');
  } finally {
    loading.value = false;
  }
}

function handleQuery() {
  if (dirty.value)
    Modal.confirm({
      title: '重新查询会放弃未保存的修改',
      content: '已保存的日报消耗和截图仍会保留。',
      onOk: load,
    });
  else void load();
}

function lineOptions(row: EditorRow) {
  return options.value
    .filter((line) => line.projectId === row.projectId)
    .map((line) => ({ value: line.agencyLineId, label: line.agencyLineName }));
}
function changeProject(row: EditorRow) {
  row.projectName =
    options.value.find((line) => line.projectId === row.projectId)
      ?.projectName ?? '';
  row.agencyLineId = '';
  row.agencyLineName = '';
  dirty.value = true;
}
function changeLine(row: EditorRow) {
  row.agencyLineName =
    options.value.find((line) => line.agencyLineId === row.agencyLineId)
      ?.agencyLineName ?? '';
  dirty.value = true;
}
function addRow() {
  rows.value.push({
    key: `manual-${++sequence}`,
    id: null,
    projectId: '',
    projectName: '',
    agencyLineId: '',
    agencyLineName: '',
    platform: 'facebook',
    actualSpend: 0,
    manual: true,
    metrics: {
      dailySpend: 0,
      impressions: 0,
      clicks: 0,
      installs: 0,
      registrations: 0,
      firstPurchases: 0,
      adjustmentAmount: 0,
      secondaryDeduction: 0,
      adjustmentType: '未设置',
      remark: '',
    },
    attachments: [],
    accountIds: [],
    campaignIds: [],
    saved: false,
    uploading: false,
  });
  dirty.value = true;
}
function removeDraft(row: EditorRow) {
  rows.value = rows.value.filter((item) => item.key !== row.key);
  dirty.value = true;
}

/** 同一行上传串行处理，批量选择、粘贴与已有图片合计最多五张。 */
async function uploadImages(row: EditorRow, files: File[]) {
  if (busy.value || !canEdit()) return;
  if (row.attachments.length + files.length > 5) {
    message.warning('每条日报最多关联5张截图');
    return;
  }
  if (
    files.some(
      (file) =>
        !['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(
          file.type,
        ),
    )
  ) {
    message.warning('仅支持 PNG、JPEG、WebP、GIF 图片');
    return;
  }
  row.uploading = true;
  try {
    for (const file of files) {
      const uploaded = await uploadDailyReportAttachment(file);
      if (!row.attachments.some((item) => item.id === uploaded.id)) {
        row.attachments.push({
          id: uploaded.id,
          name: uploaded.originalName,
          mimeType: uploaded.mimeType,
        });
        previews.value[uploaded.id] = URL.createObjectURL(file);
        dirty.value = true;
      }
    }
  } catch {
    message.error('截图上传失败，已上传的截图已保留，请重试');
  } finally {
    row.uploading = false;
  }
}
function beforeUpload(row: EditorRow, file: File, files: File[]) {
  if (file === files[0]) void uploadImages(row, files);
  return false;
}
function pasteImages(row: EditorRow, event: ClipboardEvent) {
  const files = [...(event.clipboardData?.files ?? [])];
  if (files.length === 0) return;
  event.preventDefault();
  void uploadImages(row, files);
}
function removeImage(row: EditorRow, id: string) {
  if (!canEdit() || busy.value) return;
  row.attachments = row.attachments.filter((file) => file.id !== id);
  dirty.value = true;
}
function money(value: null | number) {
  return Number(value ?? 0).toFixed(2);
}
function numericField(key: unknown) {
  return numericFields.find((field) => field.key === key);
}

/** 导出已查询范围内的全部行，分页读取仍由后端校验查看权限。 */
async function exportExcel() {
  if (busy.value || error.value || !loadedRange.value) return;
  exporting.value = true;
  const selected = {
    ...loadedRange.value,
    ...appliedFilters.value,
    reporterId: props.reporterId,
  };
  try {
    const data: ReportExportRow[] = [];
    const seen = new Set<string>();
    let total = 0;
    for (let page = 1; page === 1 || data.length < total; page++) {
      const response = await deliveryReportApi.page({
        ...selected,
        page,
        pageSize: 100,
      });
      if (disposed) return;
      if (page === 1) total = Number(response.total);
      else if (Number(response.total) !== total)
        throw new Error('日报数据已变化，请重新查询后导出');
      const batch = response.days.flatMap((day) =>
        day.rows.map((row) => ({ day, row })),
      );
      if (batch.length === 0 && data.length < total)
        throw new Error('日报数据已变化，请重新查询后导出');
      for (const { day, row } of batch) {
        const key = day.reporterId + ':' + row.id;
        if (seen.has(key)) throw new Error('日报数据已变化，请重新查询后导出');
        seen.add(key);
        data.push({
          date: day.date,
          reporter: day.reporterName,
          project: row.projectName,
          line: row.agencyLineName,
          platform: row.platform,
          actualSpend: Number(row.actualSpend || 0),
          ...row.metrics,
          ...Object.fromEntries(
            numericFields.map((field) => [
              field.key,
              Number(row.metrics[field.key]),
            ]),
          ),
          returnSpend: Number(
            money(
              Number(row.actualSpend || 0) -
                Number(row.metrics.adjustmentAmount),
            ),
          ),
          returnIncrease: Number(
            money(
              Number(row.actualSpend || 0) - Number(row.metrics.dailySpend),
            ),
          ),
          attachments: row.attachments.length,
        });
      }
    }
    if (!data.length) {
      message.info('当前筛选条件下暂无可导出的日报');
      return;
    }
    const moneyKeys = new Set([
      'actualSpend',
      'dailySpend',
      'adjustmentAmount',
      'secondaryDeduction',
      'returnSpend',
      'returnIncrease',
    ]);
    const exportColumns = columns.value
      .filter((column) => column.key !== 'actions')
      .map((column) => ({
        key: String(column.key),
        title: column.key === 'attachments' ? '截图数量' : String(column.title),
        money: moneyKeys.has(String(column.key)),
      }));
    const workbook = await createReportWorkbook(
      exportColumns,
      data,
      '投放日报',
    );
    if (disposed) return;
    await downloadReportWorkbook(
      workbook,
      '投放日报_' + selected.startDate + '_' + selected.endDate + '.xlsx',
    );
    message.success('已导出 ' + data.length + ' 条日报');
  } catch (error) {
    if (!disposed)
      message.error(
        error instanceof Error ? error.message : '导出失败，请重试',
      );
  } finally {
    exporting.value = false;
  }
}

async function showGooglePush() {
  if (!canManageGooglePush.value) return;
  if (selectedReportIds.value.length === 0) {
    message.warning('请先选择要写入项目日报的记录');
    return;
  }
  await googlePushModal.value?.show(selectedReportIds.value);
}

async function save() {
  if (viewOnly.value || rows.value.length === 0) return;
  const keys = new Set<string>();
  for (const row of rows.value) {
    if (!row.projectId || !row.agencyLineId || !row.platform) {
      message.warning('请为每条日报选择项目、代理线和平台');
      return;
    }
    const key = JSON.stringify([row.projectId, row.agencyLineId, row.platform]);
    if (keys.has(key)) {
      message.warning('项目、代理线和平台重复，请直接修改原有记录');
      return;
    }
    keys.add(key);
    if (
      numericFields.some(
        (field) =>
          row.metrics[field.key] === null ||
          !Number.isFinite(Number(row.metrics[field.key])) ||
          (field.key !== 'adjustmentAmount' && row.metrics[field.key] < 0),
      )
    ) {
      message.warning('请检查指标，消耗和数量不能为空或小于0');
      return;
    }
  }
  saving.value = true;
  try {
    await applyResult(
      await deliveryReportApi.save(loadedDate.value, rows.value),
    );
    message.success('投放日报已保存');
  } finally {
    saving.value = false;
  }
  // 保存成功且解除忙碌状态后通知父页面关闭页签，避免被离开守卫拦截。
  emit('saved');
}

onBeforeRouteLeave(() => {
  if (!dirty.value && !busy.value) return true;
  if (busy.value) {
    message.info('正在处理日报，请稍候再离开');
    return false;
  }
  return new Promise<boolean>((resolve) => {
    Modal.confirm({
      title: '日报有未保存的修改，是否离开？',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });
});

function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) {
    event.preventDefault();
    event.returnValue = '';
  }
}
onMounted(async () => {
  if (props.detailDays) return;
  window.addEventListener('beforeunload', beforeUnload);
  try {
    if (!viewOnly.value) options.value = await deliveryReportApi.options();
  } catch {
    message.error('项目与代理线选项加载失败，请刷新页面重试');
  }
  await load();
});
onBeforeUnmount(() => {
  disposed = true;
  window.removeEventListener('beforeunload', beforeUnload);
  releasePreviews();
});
</script>

<template>
  <div
    class="delivery-report-panel min-w-0 space-y-4"
    :class="{ 'delivery-report-list': viewOnly }"
  >
    <section v-if="viewOnly && !detailDays" aria-label="汇报统计看板">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-4">
        <button
          type="button"
          class="flex items-center gap-2 text-base font-semibold"
          :aria-expanded="statsExpanded"
          @click="statsExpanded = !statsExpanded"
        >
          汇报统计看板<IconifyIcon
            :icon="statsExpanded ? 'lucide:chevron-up' : 'lucide:chevron-down'"
            class="h-4 w-4"
          />
        </button>
        <div class="flex flex-wrap items-center gap-3">
          <span class="text-muted-foreground text-xs"
            >{{
              loadedRange
                ? loadedRange.startDate + ' 至 ' + loadedRange.endDate
                : '尚未查询'
            }}
            · 当前筛选范围内已填记录</span
          >
          <Button :disabled="busy" :loading="loading" @click="handleQuery"
            ><IconifyIcon
              icon="lucide:refresh-cw"
              class="mr-1"
            />更新数据</Button
          >
        </div>
      </div>
      <div
        v-if="statsExpanded"
        class="bg-muted/40 grid grid-cols-1 gap-4 rounded-xl p-4 lg:grid-cols-3"
        :aria-busy="loading"
      >
        <div
          v-for="item in summaryCards"
          :key="item.label"
          class="bg-card border-border rounded-xl border p-5"
        >
          <div
            class="text-muted-foreground flex items-center justify-between gap-3 text-sm"
          >
            <span>{{ item.label }}</span
            ><IconifyIcon :icon="item.icon" class="h-5 w-5" />
          </div>
          <div class="mt-6 flex flex-wrap items-baseline gap-2">
            <strong class="text-3xl font-semibold tabular-nums">{{
              statsLoading || statsFailed ? '—' : item.value
            }}</strong
            ><span class="text-muted-foreground text-xs">{{ item.unit }}</span>
          </div>
          <p class="text-muted-foreground mb-0 mt-3 text-xs">
            {{
              item.label === '实际消耗合计'
                ? '平台同步的最新消耗'
                : '已保存的日报数据'
            }}
          </p>
        </div>
      </div>
    </section>
    <Alert
      v-if="statsFailed && viewOnly && !detailDays"
      type="warning"
      show-icon
      message="统计加载失败，列表可继续查看"
    >
      <template #action
        ><Button
          :loading="statsLoading"
          @click="loadStatistics(statisticsRange || selectedRange())"
          >重试统计</Button
        ></template
      >
    </Alert>
    <Card v-if="viewOnly && !detailDays" class="delivery-filter-card">
      <form
        class="flex flex-wrap items-end gap-4"
        @submit.prevent="searchReports"
      >
        <label class="flex w-[300px] max-w-full flex-col gap-2"
          ><span>时间段</span
          ><DatePicker.RangePicker
            v-model:value="dateRange"
            :allow-clear="false"
            :disabled="busy"
            class="w-full"
        /></label>
        <label class="flex w-[220px] max-w-full flex-col gap-2"
          ><span>投手姓名</span
          ><Input
            v-model:value="reporterFilter"
            allow-clear
            placeholder="请输入投手姓名"
        /></label>
        <label class="flex w-[220px] max-w-full flex-col gap-2"
          ><span>项目名称</span
          ><Input
            v-model:value="projectFilter"
            allow-clear
            placeholder="请输入项目名称"
        /></label>
        <label class="flex w-[220px] max-w-full flex-col gap-2"
          ><span>代理线名称</span
          ><Input
            v-model:value="lineFilter"
            allow-clear
            placeholder="请输入代理线名称"
        /></label>
        <div class="flex items-center gap-2">
          <Button
            html-type="submit"
            type="primary"
            :disabled="busy"
            :loading="loading"
            >搜索</Button
          ><Button :disabled="busy" @click="resetFilters">重置</Button>
        </div>
      </form>
    </Card>
    <Card v-else-if="!viewOnly" :bordered="false">
      <div class="flex flex-wrap items-center gap-4">
        <label class="flex items-center gap-2"
          ><span class="whitespace-nowrap">日期</span
          ><DatePicker
            v-model:value="date"
            :allow-clear="false"
            :disabled="busy"
            class="w-[220px]"
        /></label>
        <Button :disabled="busy" :loading="loading" @click="handleQuery"
          >查询</Button
        >
        <span class="text-muted-foreground"
          >{{ reporterName }} · {{ loadedDate || '尚未查询' }} · 金额 USD</span
        >
        <template v-if="!viewOnly">
          <Button :disabled="busy || !loadedDate || error" @click="addRow"
            >添加行</Button
          >
          <Button
            type="primary"
            :loading="saving"
            :disabled="busy || !loadedDate || error || rows.length === 0"
            @click="save"
            >保存日报</Button
          >
        </template>
      </div>
    </Card>
    <Alert
      v-if="error"
      type="error"
      show-icon
      message="查询失败，当前内容不能保存；请重新查询成功后再操作。"
    />
    <Alert
      v-if="unmatchedCount"
      type="warning"
      show-icon
      :message="`${unmatchedCount}组平台数据未唯一匹配项目与代理线，未展示。`"
    />
    <Card
      class="delivery-detail-card"
      :bordered="viewOnly"
      :title="performance ? '绩效基础明细' : '投放日报明细'"
    >
      <template #extra>
        <div v-if="viewOnly && !detailDays" class="flex flex-wrap gap-2">
          <Button v-if="canPushGoogle" @click="googleTemplateModal?.show()">
            <IconifyIcon icon="lucide:settings-2" class="mr-1" />项目日报模板
          </Button>
          <Button v-if="canPushGoogle" @click="googlePushModal?.showHistory()">
            推送记录
          </Button>
          <Button
            v-if="canPushGoogle"
            type="primary"
            :disabled="busy || selectedReportIds.length === 0"
            @click="showGooglePush"
          >
            填写到项目日报（{{ selectedReportIds.length }}）
          </Button>
          <Button
            :loading="exporting"
            :disabled="busy || error || !loadedRange || totalRows === 0"
            @click="exportExcel"
            >导出 Excel</Button
          >
        </div>
      </template>
      <Table
        :columns="columns"
        :data-source="displayedRows"
        :loading="loading"
        :row-selection="rowSelection"
        :pagination="
          viewOnly && !detailDays
            ? {
                current: pageNumber,
                pageSize,
                total: totalRows,
                showSizeChanger: true,
                pageSizeOptions: ['20', '50', '100'],
                disabled: loading,
              }
            : { pageSize: 20, showSizeChanger: true }
        "
        @change="changePage"
        :scroll="{ x: (performance ? 2530 : 3230) + (viewOnly ? 140 : 0) }"
        row-key="key"
      >
        <template #emptyText>{{
          viewOnly
            ? '所选时间段及筛选条件下暂无已保存的投放日报。'
            : '所选日期暂无本人投放数据，可添加行补录。'
        }}</template>
        <template #headerCell="{ column }">
          <span
            class="flex w-full items-center justify-start gap-1 whitespace-nowrap text-left"
          >
            <span>{{ column.title }}</span>
            <Popover
              v-if="fieldHelp[String(column.key)]"
              :trigger="['hover', 'click', 'focus']"
              placement="top"
            >
              <template #content>
                <p class="m-0 max-w-[260px] text-sm leading-6">
                  {{ fieldHelp[String(column.key)] }}
                </p>
              </template>
              <button
                type="button"
                class="text-muted-foreground hover:text-primary focus-visible:ring-primary inline-flex h-6 w-6 shrink-0 items-center justify-center rounded focus-visible:outline-none focus-visible:ring-2"
                :aria-label="String(column.title) + '说明'"
                @click.stop
              >
                <IconifyIcon icon="lucide:circle-help" class="h-4 w-4" />
              </button>
            </Popover>
          </span>
        </template>
        <template #bodyCell="{ column, record }">
          <!-- Ant Table 的插槽类型丢失泛型；数据源固定为 EditorRow[]，仅在此恢复类型。 -->
          <template v-for="row in [record as EditorRow]" :key="row.key">
            <!-- 使用已加载日期，与保存日期一致；切换查询条件不会改动尚未保存的行日期。 -->
            <span v-if="column.key === 'date'">{{
              row.reportDate || loadedDate
            }}</span>
            <span v-else-if="column.key === 'reporter'">{{
              row.reporterName || reporterName
            }}</span>
            <template v-else-if="column.key === 'project'">
              <Select
                v-if="canEdit() && row.manual"
                v-model:value="row.projectId"
                :options="projects"
                show-search
                option-filter-prop="label"
                placeholder="选择项目"
                class="w-full"
                :disabled="busy"
                @change="changeProject(row)"
              />
              <span v-else>{{ row.projectName }}</span>
            </template>
            <template v-else-if="column.key === 'line'">
              <Select
                v-if="canEdit() && row.manual"
                v-model:value="row.agencyLineId"
                :options="lineOptions(row)"
                show-search
                option-filter-prop="label"
                placeholder="选择代理线"
                class="w-full"
                :disabled="busy || !row.projectId"
                @change="changeLine(row)"
              />
              <span v-else>{{ row.agencyLineName }}</span>
            </template>
            <template v-else-if="column.key === 'platform'">
              <Select
                v-if="canEdit() && row.manual"
                v-model:value="row.platform"
                :options="platforms"
                class="w-full"
                :disabled="busy"
                @change="dirty = true"
              />
              <span v-else>{{ row.platform }}</span>
            </template>
            <span v-else-if="column.key === 'actualSpend'">{{
              money(row.actualSpend)
            }}</span>
            <template v-else-if="numericField(column.key)">
              <span v-if="!canEdit()">{{
                numericField(column.key)!.money
                  ? money(row.metrics[numericField(column.key)!.key])
                  : row.metrics[numericField(column.key)!.key]
              }}</span>
              <InputNumber
                v-else
                v-model:value="row.metrics[numericField(column.key)!.key]"
                :aria-label="String(column.title)"
                :min="column.key === 'adjustmentAmount' ? undefined : 0"
                :precision="numericField(column.key)!.money ? 2 : 0"
                class="w-full text-left [&_input]:text-left"
                :disabled="busy"
                @change="dirty = true"
              />
            </template>
            <template v-else-if="column.key === 'adjustmentType'">
              <span v-if="!canEdit()">{{ row.metrics.adjustmentType }}</span>
              <Select
                v-else
                v-model:value="row.metrics.adjustmentType"
                :options="adjustments"
                class="w-full"
                :disabled="busy"
                @change="dirty = true"
              />
            </template>
            <span v-else-if="column.key === 'returnSpend'">{{
              money(
                Number(row.actualSpend ?? 0) -
                  Number(row.metrics.adjustmentAmount),
              )
            }}</span>
            <span v-else-if="column.key === 'returnIncrease'">{{
              money(
                Number(row.actualSpend ?? 0) - Number(row.metrics.dailySpend),
              )
            }}</span>
            <template v-else-if="column.key === 'remark'">
              <span v-if="!canEdit()">{{ row.metrics.remark || '—' }}</span>
              <Input.TextArea
                v-else
                v-model:value="row.metrics.remark"
                :maxlength="2000"
                :auto-size="{ minRows: 1, maxRows: 3 }"
                :disabled="busy"
                aria-label="备注"
                @change="dirty = true"
              />
            </template>
            <div
              v-else-if="column.key === 'attachments'"
              class="flex flex-wrap items-center gap-2"
              :tabindex="canEdit() ? 0 : undefined"
              aria-label="日报截图"
              @paste="pasteImages(row, $event)"
            >
              <span>{{ row.attachments.length }} 张</span>
              <Button
                v-if="row.attachments.length"
                type="link"
                @click="showScreenshots(row)"
                >查看</Button
              >
              <Upload
                v-if="canEdit()"
                accept="image/png,image/jpeg,image/webp,image/gif"
                multiple
                :show-upload-list="false"
                :disabled="busy || row.attachments.length >= 5"
                :before-upload="(file, files) => beforeUpload(row, file, files)"
              >
                <Button
                  :loading="row.uploading"
                  :disabled="busy || row.attachments.length >= 5"
                  >上传（{{ row.attachments.length }}/5）</Button
                >
              </Upload>
            </div>
            <Button
              v-else-if="column.key === 'actions' && !row.saved && row.manual"
              danger
              type="link"
              :disabled="busy"
              @click="removeDraft(row)"
              >移除</Button
            >
          </template>
        </template>
      </Table>
    </Card>
    <Modal
      v-model:open="screenshotOpen"
      title="日报截图"
      :footer="null"
      :width="720"
      @cancel="closeScreenshots"
    >
      <template v-if="screenshotRow">
        <p class="text-muted-foreground">
          {{ screenshotRow.projectName }} · {{ screenshotRow.agencyLineName }} ·
          {{ screenshotRow.attachments.length }} 张截图
        </p>
        <p v-if="screenshotLoading" role="status">正在加载截图…</p>
        <Image.PreviewGroup>
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div
              v-for="file in screenshotRow.attachments"
              :key="file.id"
              class="min-w-0 space-y-2"
            >
              <Image
                v-if="previews[file.id]"
                :src="previews[file.id]"
                :alt="file.name"
                :width="'100%'"
              />
              <div v-else-if="!screenshotLoading" class="text-muted-foreground">
                截图加载失败
                <Button type="link" @click="showScreenshots(screenshotRow)"
                  >重试</Button
                >
              </div>
              <p class="m-0 break-all text-sm">{{ file.name }}</p>
              <Button
                v-if="canEdit()"
                type="link"
                danger
                :disabled="busy"
                @click="removeImage(screenshotRow, file.id)"
                >移除</Button
              >
            </div>
          </div>
        </Image.PreviewGroup>
        <p
          v-if="screenshotRow.attachments.length === 0"
          class="text-muted-foreground"
        >
          暂无截图
        </p>
      </template>
    </Modal>
    <DeliveryReportGoogleTemplateModal
      v-if="canManageGooglePush"
      ref="googleTemplateModal"
    />
    <DeliveryReportGooglePushModal
      v-if="canManageGooglePush"
      ref="googlePushModal"
      @completed="selectedRowKeys = []"
    />
  </div>
</template>

<style scoped>
.delivery-report-list {
  padding-top: 16px;
}
/* 覆盖全局固定列表头的白色 !important 背景，所有表头统一为不透明底色。 */
</style>
