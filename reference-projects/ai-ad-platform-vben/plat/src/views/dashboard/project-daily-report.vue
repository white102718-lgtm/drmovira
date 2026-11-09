<script lang="ts" setup>
import type { TableColumnsType, TableProps } from 'ant-design-vue';
import type {
  ProjectDailyReportDimension,
  ProjectDailyReportOption,
  ProjectDailyReportQuery,
  ProjectDailyReportResult,
  ProjectDailyReportRow,
  ProjectDailyReportSyncStatus,
  ProjectDailyRetentionDay,
} from '#/domain/project-daily-report';

import type { Dayjs } from 'dayjs';

import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import {
  Button,
  Card,
  DatePicker,
  message,
  Select,
  Table,
  Tag,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import utc from 'dayjs/plugin/utc';

import { ProjectDailyReportRequestError } from '#/api/project-daily-report';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import {
  PROJECT_DAILY_RETENTION_DAYS,
  projectDailyReportService,
} from '#/domain/project-daily-report';

dayjs.extend(utc);
dayjs.extend(isoWeek);

const router = useRouter();
const SYNC_POLL_MS = 8000;
const PAGE_SIZE = 20;

/** 页面日期跟 CMS 后台一致，用 GMT+0 自然日，不用北京时间。 */
function gmt0Today(): string {
  return dayjs.utc().format('YYYY-MM-DD');
}

function calendarDayRange(day: string): [number, number] {
  return [
    dayjs(day).startOf('day').valueOf(),
    dayjs(day).endOf('day').valueOf(),
  ];
}

function gmt0TodayRange(): [number, number] {
  return calendarDayRange(gmt0Today());
}

function gmt0DateShortcuts(): Record<string, [number, number]> {
  const today = dayjs.utc();
  const day = (offset: number) =>
    today.subtract(offset, 'day').format('YYYY-MM-DD');
  const weekStart = today.startOf('isoWeek').format('YYYY-MM-DD');
  const lastWeekStart = today
    .subtract(1, 'week')
    .startOf('isoWeek')
    .format('YYYY-MM-DD');
  const lastWeekEnd = today
    .subtract(1, 'week')
    .endOf('isoWeek')
    .format('YYYY-MM-DD');
  const monthStart = today.startOf('month').format('YYYY-MM-DD');
  const lastMonthStart = today
    .subtract(1, 'month')
    .startOf('month')
    .format('YYYY-MM-DD');
  const lastMonthEnd = today
    .subtract(1, 'month')
    .endOf('month')
    .format('YYYY-MM-DD');
  return {
    今天: calendarDayRange(day(0)),
    昨天: calendarDayRange(day(1)),
    过去7天: [calendarDayRange(day(6))[0], calendarDayRange(day(0))[1]],
    过去14天: [calendarDayRange(day(13))[0], calendarDayRange(day(0))[1]],
    过去30天: [calendarDayRange(day(29))[0], calendarDayRange(day(0))[1]],
    本周: [calendarDayRange(weekStart)[0], calendarDayRange(day(0))[1]],
    上周: [
      calendarDayRange(lastWeekStart)[0],
      calendarDayRange(lastWeekEnd)[1],
    ],
    本月: [calendarDayRange(monthStart)[0], calendarDayRange(day(0))[1]],
    上个月: [
      calendarDayRange(lastMonthStart)[0],
      calendarDayRange(lastMonthEnd)[1],
    ],
    '90天': [calendarDayRange(day(90))[0], calendarDayRange(day(0))[1]],
  };
}

function isGmt0DateDisabled(ts: number) {
  return dayjs(ts).format('YYYY-MM-DD') > gmt0Today();
}

const dateRange = ref<[number, number]>(gmt0TodayRange());
const dateShortcuts = gmt0DateShortcuts();
const datePickerValue = computed<[Dayjs, Dayjs]>(() => [
  dayjs(dateRange.value[0]),
  dayjs(dateRange.value[1]),
]);
const datePresets = Object.entries(dateShortcuts).map(([label, range]) => ({
  label,
  value: [dayjs(range[0]), dayjs(range[1])] as [Dayjs, Dayjs],
}));

function handleDateRangeChange(
  dates: [Dayjs, Dayjs] | [string, string] | null,
) {
  const start = dates?.[0];
  const end = dates?.[1];
  if (!start || !end) return;
  const startDay = dayjs(start);
  const endDay = dayjs(end);
  dateRange.value = [
    startDay.startOf('day').valueOf(),
    endDay.endOf('day').valueOf(),
  ];
}
const projectId = ref<string>();
const agencyLineId = ref<string>();
const agencyLineItemId = ref<string>();
const dimension = ref<ProjectDailyReportDimension>('item');
const loading = ref(false);
const currentPage = ref(1);
const fixedPageSize = ref(PAGE_SIZE);
const routeStateReady = ref(false);
const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    date_range: {
      codec: {
        parse(value) {
          const dates = Array.isArray(value) ? value : [];
          if (dates.length !== 2 || !dates[0] || !dates[1]) return undefined;
          const start = dayjs(dates[0]);
          const end = dayjs(dates[1]);
          return start.isValid() && end.isValid()
            ? ([start.startOf('day').valueOf(), end.endOf('day').valueOf()] as [
                number,
                number,
              ])
            : undefined;
        },
        serialize(value) {
          return value.map((date) => dayjs(date).format('YYYY-MM-DD'));
        },
      },
    },
  },
  onRouteStateRestored: () => {
    if (routeStateReady.value) return loadReport();
  },
  pagination: {
    defaultPageSize: PAGE_SIZE,
    page: currentPage,
    pageSize: fixedPageSize,
    pageSizes: [PAGE_SIZE],
  },
  state: createListRouteStateTarget({
    agency_line: agencyLineId,
    agency_line_item: agencyLineItemId,
    date_range: dateRange,
    dimension,
    project: projectId,
  }),
});
const catalogs = ref<{
  agencyLineItems: ProjectDailyReportOption[];
  agencyLines: ProjectDailyReportOption[];
  projects: ProjectDailyReportOption[];
}>({
  agencyLineItems: [],
  agencyLines: [],
  projects: [],
});
const result = ref<ProjectDailyReportResult | null>(null);
const syncStatus = ref<null | ProjectDailyReportSyncStatus>(null);
const startingSync = ref(false);
const importing = ref(false);
const importInput = ref<HTMLInputElement | null>(null);
const tableHost = ref<HTMLElement | null>(null);
const tableScrollY = ref(360);
let syncTimer: null | number = null;
let tableResize: null | ResizeObserver = null;

const tableScroll = computed(() => ({
  x: 'max-content' as const,
  y: tableScrollY.value,
}));

/** 表体高度 = 容器减去表头和底部分页，否则 ant Table 会撑破卡片切掉滚动。 */
function measureTableBody() {
  const host = tableHost.value;
  if (!host) return;
  const header = host.querySelector(
    '.ant-table-header, .ant-table-thead',
  ) as HTMLElement | null;
  const pagination = host.querySelector(
    '.ant-table-pagination',
  ) as HTMLElement | null;
  const chrome =
    (header?.offsetHeight ?? 44) + (pagination?.offsetHeight ?? 56) + 16;
  tableScrollY.value = Math.max(160, host.clientHeight - chrome);
}

const syncing = computed(() => syncStatus.value?.status === 'running');

const projectOptions = computed(() =>
  catalogs.value.projects.map((item) => ({
    label: item.name,
    value: item.id,
  })),
);
const agencyLineOptions = computed(() =>
  catalogs.value.agencyLines
    .filter((item) => !projectId.value || item.projectId === projectId.value)
    .map((item) => ({
      label: item.name,
      value: item.id,
    })),
);
const agencyLineItemOptions = computed(() =>
  catalogs.value.agencyLineItems
    .filter((item) => {
      if (projectId.value && item.projectId !== projectId.value) return false;
      if (agencyLineId.value && item.agencyLineId !== agencyLineId.value) {
        return false;
      }
      return true;
    })
    .map((item) => ({
      label: item.name,
      value: item.id,
    })),
);
const tableTotal = computed(
  () => result.value?.total ?? result.value?.rows.length ?? 0,
);
const tablePagination = computed(() => ({
  current: currentPage.value,
  pageSize: PAGE_SIZE,
  showSizeChanger: false,
  showTotal: (total: number) => `共 ${total} 条`,
  total: tableTotal.value,
}));

const isDayView = computed(() => dimension.value === 'day');
const showItemColumn = computed(
  () => !isDayView.value || !agencyLineItemId.value,
);

const columns = computed<TableColumnsType>(() => [
  ...(showItemColumn.value
    ? [
        {
          dataIndex: 'agencyLineItemName',
          key: 'agencyLineItemName',
          title: '代理线项',
          width: 220,
        },
      ]
    : []),
  { dataIndex: 'date', key: 'date', title: '日期(GMT+0)', width: 130 },
  {
    align: 'right' as const,
    dataIndex: 'spendAmount',
    key: 'spendAmount',
    title: '消耗(USD)',
    width: 120,
  },
  {
    align: 'right' as const,
    dataIndex: 'firstDepositUsers',
    key: 'firstDepositUsers',
    title: '首充人数',
    width: 110,
  },
  {
    align: 'right' as const,
    dataIndex: 'firstDepositAmount',
    key: 'firstDepositAmount',
    title: '首充金额',
    width: 120,
  },
  {
    align: 'right' as const,
    dataIndex: 'rechargeAmount',
    key: 'rechargeAmount',
    title: '充值金额',
    width: 120,
  },
  {
    align: 'right' as const,
    dataIndex: 'withdrawalUsers',
    key: 'withdrawalUsers',
    title: '提现人数',
    width: 110,
  },
  {
    align: 'right' as const,
    dataIndex: 'withdrawalAmount',
    key: 'withdrawalAmount',
    title: '提现金额',
    width: 120,
  },
  {
    align: 'right' as const,
    dataIndex: isDayView.value ? 'repeatRechargeLabel' : 'repeatRechargeUsers',
    key: isDayView.value ? 'repeatRechargeLabel' : 'repeatRechargeUsers',
    title: isDayView.value ? '当日复充' : '重复充值人数',
    width: isDayView.value ? 140 : 130,
  },
  ...PROJECT_DAILY_RETENTION_DAYS.map((day) => ({
    align: 'right' as const,
    dataIndex: `retention${day}`,
    key: `retention${day}`,
    title: `${day}日留存`,
    width: isDayView.value ? 130 : 100,
  })),
]);

const tableRows = computed(() =>
  (result.value?.rows ?? []).map((row) => ({
    ...row,
    repeatRechargeLabel: formatRepeatRecharge(row),
    ...Object.fromEntries(
      PROJECT_DAILY_RETENTION_DAYS.map((day) => [
        `retention${day}`,
        isDayView.value
          ? formatDayRetention(row, day)
          : formatRetention(row.retention[day]),
      ]),
    ),
  })),
);

function formatMoney(value: number, currency: string) {
  return new Intl.NumberFormat('en-US', {
    currency,
    maximumFractionDigits: 2,
    style: 'currency',
  }).format(value);
}

function formatRetention(value: null | number | undefined) {
  if (value == null) return '—';
  return `${value.toFixed(1)}%`;
}

/** CMS 后台「717(31.87%)」：人数 + 占首充人数的百分比。 */
function formatCountRate(
  count: null | number | undefined,
  rate: null | number | undefined,
) {
  if (rate == null) return '—';
  const users = count == null ? 0 : count;
  return `${users}(${rate.toFixed(2)}%)`;
}

function formatRepeatRecharge(row: ProjectDailyReportRow) {
  const firstUsers = row.firstDepositUsers || 0;
  const count = row.repeatRechargeUsers || 0;
  const rate = firstUsers === 0 ? 0 : (count / firstUsers) * 100;
  return formatCountRate(count, rate);
}

function formatDayRetention(
  row: ProjectDailyReportRow,
  day: ProjectDailyRetentionDay,
) {
  const rate = row.retention[day];
  if (rate == null) return '—';
  const users =
    row.retentionUsers?.[day] ??
    Math.round(((row.firstDepositUsers || 0) * rate) / 100);
  return formatCountRate(users, rate);
}

/** 跳到广告面板代理线 Tab。名称走 keyword，不能塞进 agent_line：同一级选中不会筛列表。 */
function openAdPanel(value: ProjectDailyReportRow | Record<string, unknown>) {
  const row = value as ProjectDailyReportRow;
  const name = row.agencyLineItemName.trim();
  if (!name || name === '合计') return;
  const query: Record<string, string> = {
    keyword: name,
    tab: 'agent_line',
  };
  if (row.date) query.date = `${row.date},${row.date}`;
  void router.push({ path: '/dashboard/ad-manager', query });
}

function currentQuery(
  extras: Partial<ProjectDailyReportQuery> = {},
): ProjectDailyReportQuery {
  return {
    agencyLineId: agencyLineId.value,
    agencyLineItemId: agencyLineItemId.value,
    endDate: dayjs(dateRange.value[1]).format('YYYY-MM-DD'),
    dimension: dimension.value,
    includeCatalogs: catalogs.value.projects.length === 0,
    page: currentPage.value,
    pageSize: PAGE_SIZE,
    projectId: projectId.value,
    startDate: dayjs(dateRange.value[0]).format('YYYY-MM-DD'),
    ...extras,
  };
}

function showRequestError(error: unknown, fallback: string) {
  message.error(
    error instanceof ProjectDailyReportRequestError ? error.message : fallback,
  );
}

function formatUpdatedAt(value: string) {
  if (!value) return '尚未同步';
  const parsed = dayjs(value);
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm') : value;
}

function rememberCatalogs(next: ProjectDailyReportResult) {
  if (next.projects.length > 0) {
    catalogs.value = {
      agencyLineItems: next.agencyLineItems,
      agencyLines: next.agencyLines,
      projects: next.projects,
    };
  }
}

function emptyResult(): ProjectDailyReportResult {
  return {
    agencyLineItems: catalogs.value.agencyLineItems,
    agencyLines: catalogs.value.agencyLines,
    projects: catalogs.value.projects,
    rows: [],
    summary: {
      averageRetention7: null,
      currency: result.value?.summary.currency || 'USD',
      firstDepositAmount: 0,
      firstDepositUsers: 0,
      rechargeAmount: 0,
      spendAmount: 0,
      withdrawalAmount: 0,
    },
    total: 0,
    updatedAt: result.value?.updatedAt ?? '',
  };
}

function stopSyncPoll() {
  if (syncTimer != null) {
    window.clearInterval(syncTimer);
    syncTimer = null;
  }
}

function startSyncPoll() {
  if (syncTimer != null) return;
  syncTimer = window.setInterval(() => {
    void refreshSyncStatus();
  }, SYNC_POLL_MS);
}

async function refreshSyncStatus() {
  try {
    const next = await projectDailyReportService.getSyncStatus();
    const wasRunning = syncStatus.value?.status === 'running';
    syncStatus.value = next;
    if (next.status === 'running') {
      startSyncPoll();
      return;
    }
    stopSyncPoll();
    if (wasRunning && next.status === 'succeeded') {
      message.success(
        next.rowCount > 0 ? `同步完成，已写入 ${next.rowCount} 行` : '同步完成',
      );
      await loadReport({ includeCatalogs: true });
    }
    if (wasRunning && next.status === 'failed') {
      message.error(next.errorMessage || '同步失败，请稍后重试');
    }
  } catch (error) {
    stopSyncPoll();
    showRequestError(error, '同步状态暂时无法读取');
  }
}

function openImportPicker() {
  if (importing.value || syncing.value) return;
  importInput.value?.click();
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  importing.value = true;
  try {
    const imported = await projectDailyReportService.importExcel(file);
    const names = imported.projects.map((item) => item.name).join('、');
    message.success(
      `已导入 ${imported.rowCount} 行${names ? `（${names}）` : ''}`,
    );
    await loadReport({ includeCatalogs: true });
  } catch (error) {
    showRequestError(error, '导入失败，请检查表格后重试');
  } finally {
    importing.value = false;
  }
}

async function handleManualSync() {
  if (syncing.value || startingSync.value) return;
  startingSync.value = true;
  try {
    const next = await projectDailyReportService.startSync();
    syncStatus.value = next;
    if (next.alreadyRunning || next.status === 'running') {
      message.info('已开始同步，全量拉取约需十余分钟，完成后会自动刷新');
      startSyncPoll();
      return;
    }
    if (next.status === 'succeeded') {
      message.success('同步完成');
      await loadReport({ includeCatalogs: true });
    }
  } catch (error) {
    showRequestError(error, '无法启动同步，请稍后重试');
  } finally {
    startingSync.value = false;
  }
}

async function loadReport(extras: Partial<ProjectDailyReportQuery> = {}) {
  await commitQueryState();
  loading.value = true;
  try {
    const next = await projectDailyReportService.query(currentQuery(extras));
    rememberCatalogs(next);
    result.value = next;
  } catch (error) {
    showRequestError(error, '项目运营面板暂时无法读取');
    result.value = emptyResult();
  } finally {
    loading.value = false;
    await nextTick();
    measureTableBody();
  }
}

function handleProjectChange() {
  if (
    agencyLineId.value &&
    !catalogs.value.agencyLines.some(
      (line) =>
        line.id === agencyLineId.value &&
        (!projectId.value || line.projectId === projectId.value),
    )
  ) {
    agencyLineId.value = undefined;
  }
  handleAgencyLineChange();
}

function handleAgencyLineChange() {
  if (
    agencyLineItemId.value &&
    !catalogs.value.agencyLineItems.some(
      (item) =>
        item.id === agencyLineItemId.value &&
        (!projectId.value || item.projectId === projectId.value) &&
        (!agencyLineId.value || item.agencyLineId === agencyLineId.value),
    )
  ) {
    agencyLineItemId.value = undefined;
  }
}

async function handleDimensionChange(next: string | number) {
  const value = next === 'day' ? 'day' : 'item';
  if (dimension.value === value) return;
  dimension.value = value;
  currentPage.value = 1;
  await loadReport();
}

async function handleSearch() {
  currentPage.value = 1;
  await loadReport();
}

async function handlePageChange(page: number) {
  currentPage.value = page;
  await loadReport({ includeCatalogs: false });
}

const handleTableChange: TableProps['onChange'] = (pagination) => {
  const nextPage = pagination.current ?? 1;
  if (nextPage === currentPage.value) return;
  void handlePageChange(nextPage);
};

async function resetFilters() {
  projectId.value = undefined;
  agencyLineId.value = undefined;
  agencyLineItemId.value = undefined;
  dateRange.value = gmt0TodayRange();
  currentPage.value = 1;
  await loadReport();
}

function csvField(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

function exportFileStamp(query: ProjectDailyReportQuery) {
  const parts = [query.startDate, query.endDate];
  if (query.dimension === 'day') parts.push('按天汇总');
  if (query.projectId) parts.push(query.projectId);
  if (query.agencyLineId) parts.push(query.agencyLineId);
  if (query.agencyLineItemId) parts.push(query.agencyLineItemId);
  return parts.join('_');
}

async function exportData() {
  loading.value = true;
  let rows: ProjectDailyReportRow[] = [];
  try {
    const exported = await projectDailyReportService.query(
      currentQuery({ includeCatalogs: false, page: 1, pageSize: 0 }),
    );
    rows = exported.rows;
  } catch (error) {
    showRequestError(error, '导出失败，请稍后重试');
    return;
  } finally {
    loading.value = false;
  }
  if (rows.length === 0) {
    message.warning('当前筛选条件下暂无可导出的数据');
    return;
  }
  const currency = result.value?.summary.currency || 'USD';
  const dayMode = dimension.value === 'day';
  const headers = dayMode
    ? [
        '项目',
        '代理线',
        '代理线项',
        '日期(GMT+0)',
        '消耗(USD)',
        '首充人数',
        '首充金额',
        '充值金额',
        '提现人数',
        '提现金额',
        '当日复充',
        ...PROJECT_DAILY_RETENTION_DAYS.map((day) => `${day}日留存`),
      ]
    : [
        '项目',
        '代理线',
        '代理线项',
        '日期(GMT+0)',
        '消耗(USD)',
        '首充人数',
        '首充金额',
        '充值金额',
        '提现人数',
        '提现金额',
        '重复充值人数',
        ...PROJECT_DAILY_RETENTION_DAYS.map((day) => `${day}日留存`),
      ];
  const csv = [
    headers.map((value) => csvField(value)).join(','),
    ...rows.map((row) =>
      (dayMode
        ? [
            row.projectName,
            row.agencyLineName,
            row.agencyLineItemName,
            row.date,
            String(row.spendAmount),
            String(row.firstDepositUsers),
            String(row.firstDepositAmount),
            String(row.rechargeAmount),
            String(row.withdrawalUsers),
            String(row.withdrawalAmount),
            formatRepeatRecharge(row),
            ...PROJECT_DAILY_RETENTION_DAYS.map(
              (day: ProjectDailyRetentionDay) => formatDayRetention(row, day),
            ),
          ]
        : [
            row.projectName,
            row.agencyLineName,
            row.agencyLineItemName,
            row.date,
            String(row.spendAmount),
            String(row.firstDepositUsers),
            String(row.firstDepositAmount),
            String(row.rechargeAmount),
            String(row.withdrawalUsers),
            String(row.withdrawalAmount),
            String(row.repeatRechargeUsers),
            ...PROJECT_DAILY_RETENTION_DAYS.map(
              (day: ProjectDailyRetentionDay) =>
                formatRetention(row.retention[day]),
            ),
          ]
      )
        .map((value) => csvField(value))
        .join(','),
    ),
  ].join('\n');
  const blob = new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `项目运营面板_${exportFileStamp(currentQuery())}_${currency}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  message.success(`已按当前筛选导出 ${rows.length} 条数据`);
}

onMounted(async () => {
  await restoreFromRoute();
  routeStateReady.value = true;
  void loadReport();
  void refreshSyncStatus();
  void nextTick(() => {
    measureTableBody();
    if (!tableHost.value || typeof ResizeObserver === 'undefined') return;
    tableResize = new ResizeObserver(() => {
      measureTableBody();
    });
    tableResize.observe(tableHost.value);
  });
});

onUnmounted(() => {
  stopSyncPoll();
  tableResize?.disconnect();
  tableResize = null;
});
</script>

<template>
  <Page
    auto-content-height
    class="adpulse-section-page project-daily-report-page bg-muted/40"
    content-class="flex h-full min-h-0 flex-col p-4"
  >
    <div class="flex min-h-0 min-w-0 flex-1 flex-col gap-4">
      <div class="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <h1 class="text-foreground m-0 text-xl font-semibold tracking-tight">
            项目运营面板
          </h1>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            数据来自 CMS 定时抓取或手动导入的 Excel。日期按 CMS 时区 GMT+0。
          </p>
          <p class="text-muted-foreground mb-0 mt-1 text-xs">
            最近入库 {{ formatUpdatedAt(result?.updatedAt || '') }}
          </p>
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <Tag class="whitespace-nowrap">
            {{ syncing ? '同步中' : '每小时更新' }}
          </Tag>
          <input
            ref="importInput"
            accept=".xlsx,.xlsm,.xls,.zip,application/zip,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            class="hidden"
            type="file"
            @change="handleImportFile"
          />
          <Button
            :disabled="loading || syncing || startingSync || importing"
            @click="openImportPicker"
          >
            {{ importing ? '导入中…' : '导入表格' }}
          </Button>
          <Button
            :disabled="loading || syncing || startingSync || importing"
            @click="handleManualSync"
          >
            {{ syncing || startingSync ? '同步中…' : '手动同步' }}
          </Button>
          <Button :disabled="loading || startingSync" @click="exportData">
            {{ isDayView ? '导出按天汇总' : '导出日报' }}
          </Button>
        </div>
      </div>

      <Card
        class="border-border shrink-0 shadow-none"
        :body-style="{ padding: '16px' }"
      >
        <div
          class="project-daily-report-filters flex w-full flex-wrap items-center gap-x-3 gap-y-3"
        >
          <div class="pdr-filter-control">
            <label class="pdr-filter-label">项目</label>
            <Select
              v-model:value="projectId"
              allow-clear
              option-filter-prop="label"
              placeholder="全部项目"
              show-search
              :options="projectOptions"
              @change="handleProjectChange"
            />
          </div>
          <div class="pdr-filter-control">
            <label class="pdr-filter-label">代理线</label>
            <Select
              v-model:value="agencyLineId"
              allow-clear
              option-filter-prop="label"
              placeholder="全部代理线"
              show-search
              :options="agencyLineOptions"
              @change="handleAgencyLineChange"
            />
          </div>
          <div class="pdr-filter-control">
            <label class="pdr-filter-label">代理线项</label>
            <Select
              v-model:value="agencyLineItemId"
              allow-clear
              option-filter-prop="label"
              placeholder="全部代理线项"
              show-search
              :options="agencyLineItemOptions"
            />
          </div>
          <div class="pdr-filter-control pdr-filter-control-date">
            <label class="pdr-filter-label">日期</label>
            <DatePicker.RangePicker
              :value="datePickerValue"
              format="YYYY-MM-DD"
              :presets="datePresets"
              :disabled-date="
                (current) => !!current && isGmt0DateDisabled(current.valueOf())
              "
              @change="handleDateRangeChange"
            />
          </div>
          <div class="ux-filter-actions">
            <Button :disabled="loading" type="primary" @click="handleSearch">
              查询
            </Button>
            <Button :disabled="loading" @click="resetFilters"> 重置 </Button>
          </div>
        </div>
      </Card>

      <Card
        class="pdr-table-card border-border flex min-h-0 flex-1 flex-col overflow-hidden shadow-none"
        :body-style="{
          padding: '0',
          display: 'flex',
          flexDirection: 'column',
          flex: '1',
          minHeight: '0',
        }"
      >
        <div
          class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b px-4 py-3"
        >
          <div class="min-w-0">
            <h2 class="text-foreground mb-0 text-base font-semibold">
              {{ isDayView ? '按天汇总' : '代理线项每日表现' }}
            </h2>
            <p class="text-muted-foreground mb-0 mt-0.5 text-xs">
              {{
                isDayView
                  ? '未选代理线项时列出该代理线下每一项的每日数据；选了具体项后按天看这一条。留存与当日复充展示人数和占比。'
                  : '金额已换算为主币种；未到期留存显示为 —。默认显示 GMT+0 今天。消耗按同一日期对齐日表。'
              }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <div class="flex items-center gap-1">
              <Button
                :type="dimension === 'item' ? 'primary' : 'default'"
                @click="handleDimensionChange('item')"
              >
                代理线项
              </Button>
              <Button
                :type="dimension === 'day' ? 'primary' : 'default'"
                @click="handleDimensionChange('day')"
              >
                按天汇总
              </Button>
            </div>
            <Tag class="whitespace-nowrap"> {{ tableTotal }} 条数据 </Tag>
          </div>
        </div>
        <div
          ref="tableHost"
          class="pdr-table-host min-h-0 flex-1 overflow-hidden"
        >
          <Table
            class="h-full"
            :columns="columns"
            :data-source="tableRows"
            :loading="loading"
            :locale="{ emptyText: '当前筛选条件下暂无项目运营数据' }"
            :pagination="tablePagination"
            :scroll="tableScroll"
            row-key="id"
            @change="handleTableChange"
          >
            <template #bodyCell="{ column, record, text }">
              <button
                v-if="column.key === 'agencyLineItemName'"
                class="adpulse-link ux-table-link focus-visible:ring-ring max-w-full truncate bg-transparent p-0 text-left font-medium focus-visible:outline-none focus-visible:ring-1"
                type="button"
                :title="record.agencyLineItemName"
                @click="openAdPanel(record)"
              >
                {{ record.agencyLineItemName }}
              </button>
              <template v-else-if="column.key === 'spendAmount'">
                {{
                  formatMoney(record.spendAmount, record.spendCurrency || 'USD')
                }}
              </template>
              <template v-else-if="column.key === 'firstDepositAmount'">
                {{ formatMoney(record.firstDepositAmount, record.currency) }}
              </template>
              <template v-else-if="column.key === 'rechargeAmount'">
                {{ formatMoney(record.rechargeAmount, record.currency) }}
              </template>
              <template v-else-if="column.key === 'withdrawalAmount'">
                {{ formatMoney(record.withdrawalAmount, record.currency) }}
              </template>
              <template
                v-else-if="
                  typeof column.key === 'string' &&
                  column.key.startsWith('retention')
                "
              >
                {{ record[column.key] ?? '—' }}
              </template>
              <template v-else>
                {{ text }}
              </template>
            </template>
          </Table>
        </div>
      </Card>
    </div>
  </Page>
</template>

<style scoped>
.pdr-filter-control {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  width: auto;
}

.pdr-filter-control-date {
  width: auto;
}

.pdr-filter-label {
  flex: 0 0 4em;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  line-height: var(--adpulse-control-height);
  white-space: nowrap;
}

@media (max-width: 767px) {
  .pdr-filter-control,
  .pdr-filter-control-date {
    width: 100%;
    flex-basis: 100%;
  }
}
</style>
