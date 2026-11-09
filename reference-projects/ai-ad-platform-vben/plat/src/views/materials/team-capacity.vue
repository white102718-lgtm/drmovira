<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import type {
  CapacityRow,
  TeamCapacityParams,
  TeamCapacityReport,
} from '#/api/materials/team-capacity';

import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  toRefs,
  watch,
} from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  DatePicker,
  Form,
  FormItem,
  message,
  Select,
  Table,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  getAllTeamCapacityRows,
  getTeamCapacity,
} from '#/api/materials/team-capacity';
import { useMaterialFilterOptions } from '#/composables/useMaterialFilterOptions';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import { $t } from '#/locales';

const t = (key: string) => $t(`teamCapacity.${key}`);
const defaultRange = (): [Dayjs, Dayjs] => [
  dayjs().subtract(6, 'day'),
  dayjs(),
];
const dateRange = ref<[Dayjs, Dayjs]>(defaultRange());
const filters = reactive<
  Pick<TeamCapacityParams, 'person_id' | 'project_id' | 'task_type'>
>({});
const report = ref<null | TeamCapacityReport>(null);
const loading = ref(false);
const error = ref('');
const page = ref(1);
const pageSize = ref<50 | 100 | 200>(50);
const isExporting = ref(false);
let exportController: AbortController | undefined;
const { filterOptions, optionsError, optionsLoading, reloadOptions } =
  useMaterialFilterOptions();
const options = computed(() => ({
  people: filterOptions.value?.designers ?? [],
  projects: filterOptions.value?.project_options ?? [],
}));
const sortField = ref<'delivered' | 'hours' | 'rework_count'>('delivered');
let requestId = 0;
let controller: AbortController | undefined;
let routeStateReady = false;
const routeState = createListRouteStateTarget({
  ...toRefs(filters),
  date_range: dateRange,
  sort_by: sortField,
});
const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    date_range: {
      codec: {
        parse(value) {
          const values = Array.isArray(value) ? value : [value];
          return values.length === 2 && values[0] && values[1]
            ? ([dayjs(values[0]), dayjs(values[1])] as [Dayjs, Dayjs])
            : defaultRange();
        },
        serialize(value) {
          return value.map((item) => item.format('YYYY-MM-DD'));
        },
      },
    },
  },
  onRouteStateRestored: () => (routeStateReady ? loadReport() : undefined),
  pagination: {
    defaultPageSize: 50,
    page,
    pageSize,
    pageSizes: [50, 100, 200],
  },
  state: routeState,
});

const taskOptions = computed(() => [
  { label: t('image'), value: 'image' },
  { label: t('video'), value: 'video' },
]);
const sortOptions = computed(() => [
  { label: t('sortDelivered'), value: 'delivered' },
  { label: t('sortHours'), value: 'hours' },
  { label: t('sortRework'), value: 'rework_count' },
]);
const dateLabel = computed(() =>
  dateRange.value.map((value) => value.format('YYYY-MM-DD')).join(' ~ '),
);
// 服务端对全量结果排序后分页，不能再只对当前页重排。
const rows = computed(() =>
  (report.value?.items ?? []).map((row, index) => ({
    ...row,
    rank: (page.value - 1) * pageSize.value + index + 1,
    key: JSON.stringify([row.project_id, row.person_id]),
  })),
);
const pagination = computed(() => ({
  current: page.value,
  pageSize: pageSize.value,
  total: report.value?.total ?? 0,
  pageSizeOptions: ['50', '100', '200'],
  showSizeChanger: true,
  showQuickJumper: true,
  hideOnSinglePage: false,
  responsive: true,
  disabled: loading.value,
  showTotal: (total: number) => $t('teamCapacity.paginationTotal', { total }),
  onChange: handlePageChange,
}));

function number(value: null | number | undefined, digits = 0) {
  return value === null || value === undefined
    ? '—'
    : value.toLocaleString(undefined, { maximumFractionDigits: digits });
}
function percent(value: null | number) {
  return value === null || value === undefined ? '—' : `${number(value, 1)}%`;
}
function taskLabel(type: string) {
  // 历史接口可能返回 IMAGE / VIDEO，列表与导出共用大小写兼容映射。
  const normalizedType = type.trim().toLowerCase();
  if (normalizedType === 'image') return t('image');
  if (normalizedType === 'video') return t('video');
  return t('unknownType');
}
function taskLabels(types: string[]) {
  return types.map((type) => taskLabel(type)).join(' / ');
}

const cards = computed(() => {
  const summary = report.value?.summary;
  return [
    {
      label: t('totalDelivered'),
      value: number(summary?.delivered),
      icon: 'lucide:package-check',
    },
    {
      label: t('imageCount'),
      value: number(summary?.image_count),
      icon: 'lucide:image',
    },
    {
      label: t('videoCount'),
      value: number(summary?.video_count),
      icon: 'lucide:video',
    },
    {
      label: t('submittedOrders'),
      value: number(summary?.unique_order_count),
      icon: 'lucide:files',
    },
    {
      label: t('hours'),
      value: number(summary?.hours, 2),
      icon: 'lucide:clock-3',
    },
  ];
});
const columns = computed<TableColumnsType<CapacityRow>>(() =>
  [
    { key: 'rank', title: t('rank'), width: 68 },
    { key: 'project', title: t('project'), width: 200 },
    { key: 'person', title: t('person'), width: 120 },
    { key: 'task_types', title: t('taskType'), width: 120 },
    { key: 'order_count', title: t('orderCount'), align: 'right', width: 110 },
    { key: 'delivered', title: t('delivered'), align: 'right', width: 110 },
    { key: 'approved', title: t('approved'), align: 'right', width: 110 },
    {
      key: 'first_pass_rate',
      title: t('firstPassRate'),
      align: 'right',
      width: 130,
    },
    {
      key: 'rework_count',
      title: t('reworkCount'),
      align: 'right',
      width: 110,
    },
    {
      key: 'rework_orders',
      title: t('reworkOrders'),
      align: 'right',
      width: 140,
    },
    {
      key: 'on_time_orders',
      title: t('onTimeOrders'),
      align: 'right',
      width: 140,
    },
    { key: 'hours', title: t('hours'), align: 'right', width: 110 },
    { key: 'avg_hours', title: t('avgHours'), align: 'right', width: 130 },
  ].map((column) => ({
    ...column,
    dataIndex: column.key,
    align: column.align as 'right' | undefined,
  })),
);
const incomplete = computed(() => {
  const summary = report.value?.summary;
  return (
    summary &&
    (summary.quality_order_count < summary.order_count ||
      summary.timed_order_count < summary.order_count)
  );
});

function reportParams(): TeamCapacityParams {
  return {
    ...filters,
    start_date: dateRange.value[0].format('YYYY-MM-DD'),
    end_date: dateRange.value[1].format('YYYY-MM-DD'),
    page: page.value,
    page_size: pageSize.value,
    sort_by: sortField.value,
  };
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  if (nextPageSize !== 50 && nextPageSize !== 100 && nextPageSize !== 200)
    return;
  const targetPage = nextPageSize === pageSize.value ? nextPage : 1;
  if (targetPage === page.value && nextPageSize === pageSize.value) return;
  page.value = targetPage;
  pageSize.value = nextPageSize;
  void loadReport();
}

/** 请求变更即清空旧报表；旧请求完成或失败都不能覆盖新筛选结果。 */
async function loadReport() {
  await commitQueryState();
  const id = ++requestId;
  exportController?.abort();
  controller?.abort();
  controller = new AbortController();
  const signal = controller.signal;
  report.value = null;
  error.value = '';
  loading.value = true;
  try {
    const result = await getTeamCapacity(reportParams(), signal);
    if (id === requestId) {
      const lastPage = Math.max(1, Math.ceil(result.total / pageSize.value));
      // 数据减少后恢复到有效页码，避免停留在一个空的末页。
      if (page.value > lastPage) {
        page.value = lastPage;
        await loadReport();
        return;
      }
      report.value = result;
    }
  } catch {
    if (id === requestId && !signal.aborted) error.value = t('loadError');
  } finally {
    if (id === requestId) loading.value = false;
  }
}

function resetFilters() {
  dateRange.value = defaultRange();
  filters.project_id = undefined;
  filters.person_id = undefined;
  filters.task_type = undefined;
}

function csvCell(value: number | string) {
  // 防止项目名称、人员名称被表格软件当成公式；正确转义换行、逗号与双引号。
  let text = String(value);
  if (/^\s*[+=@-]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function exportValues(
  row: CapacityRow & { rank: number },
): Array<number | string> {
  return [
    row.rank,
    row.project,
    row.person,
    taskLabels(row.task_types),
    row.order_count,
    row.delivered,
    row.approved,
    percent(row.first_pass_rate),
    number(row.rework_count),
    number(row.rework_orders),
    percent(row.rework_rate),
    row.on_time_orders,
    percent(row.on_time_rate),
    number(row.hours, 2),
    number(row.avg_hours, 2),
    row.quality_order_count,
    row.reviewed_order_count,
    row.timed_order_count,
  ];
}

/** 导出当前筛选的全部行，顺序与页面一致，不受表格分页影响。 */
async function exportCsv() {
  if (
    !report.value ||
    loading.value ||
    isExporting.value ||
    rows.value.length === 0
  )
    return;
  const currentExport = new AbortController();
  exportController = currentExport;
  isExporting.value = true;
  try {
    const allRows = await getAllTeamCapacityRows(
      reportParams(),
      currentExport.signal,
    );
    if (!currentExport.signal.aborted) downloadCsv(allRows);
  } catch {
    if (!currentExport.signal.aborted) message.error(t('exportError'));
  } finally {
    if (exportController === currentExport) {
      isExporting.value = false;
      exportController = undefined;
    }
  }
}

function downloadCsv(exportRows: CapacityRow[]) {
  const values: Array<Array<number | string>> = [
    [t('title')],
    [t('period'), dateLabel.value],
    [
      t('project'),
      options.value.projects.find((item) => item.value === filters.project_id)
        ?.label ?? t('allProjects'),
    ],
    [
      t('person'),
      options.value.people.find((item) => item.value === filters.person_id)
        ?.label ?? t('allPeople'),
    ],
    [
      t('taskType'),
      filters.task_type ? taskLabel(filters.task_type) : t('allTypes'),
    ],
    [t('hoursRule')],
    [t('qualityRule')],
    [t('incompleteDescription')],
    [],
    [
      'rank',
      'project',
      'person',
      'taskType',
      'orderCount',
      'delivered',
      'approved',
      'firstPassRate',
      'reworkCount',
      'reworkOrderCount',
      'reworkRate',
      'onTimeOrderCount',
      'onTimeRate',
      'hours',
      'avgHours',
      'qualityCoverage',
      'reviewCoverage',
      'timeCoverage',
    ].map((key) => t(key)),
    ...exportRows.map((row, index) =>
      exportValues({ ...row, rank: index + 1 }),
    ),
  ];
  const csv = values
    .map((row) => row.map((cell) => csvCell(cell)).join(','))
    .join('\r\n');
  const url = URL.createObjectURL(
    new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = `${t('title')}_${dateRange.value[0].format('YYYYMMDD')}_${dateRange.value[1].format('YYYYMMDD')}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

watch(
  [
    dateRange,
    () => filters.project_id,
    () => filters.person_id,
    () => filters.task_type,
    sortField,
  ],
  () => {
    if (!routeStateReady) return;
    page.value = 1;
    void loadReport();
  },
);
onMounted(async () => {
  await restoreFromRoute();
  routeStateReady = true;
  await loadReport();
});
onBeforeUnmount(() => {
  requestId += 1;
  controller?.abort();
  exportController?.abort();
});
</script>

<template>
  <main
    class="bg-background text-foreground h-full min-w-0 overflow-y-auto p-4"
  >
    <div class="flex min-w-0 flex-col gap-4">
      <header class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="m-0 text-xl font-semibold">{{ t('title') }}</h2>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            {{ t('description') }}
          </p>
        </div>
        <Button
          type="primary"
          :loading="isExporting"
          :disabled="loading || rows.length === 0"
          @click="exportCsv"
        >
          <template #icon><IconifyIcon icon="lucide:download" /></template>
          {{ t('export') }}
        </Button>
      </header>

      <Alert
        v-if="optionsError"
        type="error"
        show-icon
        :message="t('optionsError')"
      >
        <template #action>
          <Button :loading="optionsLoading" @click="reloadOptions">
            {{ t('retry') }}
          </Button>
        </template>
      </Alert>
      <section class="bg-card rounded-lg border p-4" :aria-label="t('filters')">
        <Form
          class="ux-filter-form"
          layout="vertical"
          :aria-label="t('filters')"
        >
          <FormItem
            :label="t('period')"
            html-for="capacity-period"
            class="ux-filter-search"
          >
            <DatePicker.RangePicker
              id="capacity-period"
              v-model:value="dateRange"
              class="w-full"
              :allow-clear="false"
              format="YYYY-MM-DD"
              :aria-label="t('period')"
            />
          </FormItem>
          <FormItem
            :label="t('project')"
            html-for="capacity-project"
            class="ux-filter-field"
          >
            <Select
              id="capacity-project"
              v-model:value="filters.project_id"
              class="w-full"
              :options="options.projects"
              :loading="optionsLoading"
              :placeholder="t('allProjects')"
              allow-clear
              show-search
              option-filter-prop="label"
            />
          </FormItem>
          <FormItem
            :label="t('person')"
            html-for="capacity-person"
            class="ux-filter-field"
          >
            <Select
              id="capacity-person"
              v-model:value="filters.person_id"
              class="w-full"
              :options="options.people"
              :loading="optionsLoading"
              :placeholder="t('allPeople')"
              allow-clear
              show-search
              option-filter-prop="label"
            />
          </FormItem>
          <FormItem
            :label="t('taskType')"
            html-for="capacity-type"
            class="ux-filter-field"
          >
            <Select
              id="capacity-type"
              v-model:value="filters.task_type"
              class="w-full"
              :options="taskOptions"
              :placeholder="t('allTypes')"
              allow-clear
            />
          </FormItem>
          <div class="ux-filter-actions">
            <Button @click="resetFilters">{{ t('reset') }}</Button>
          </div>
        </Form>
      </section>

      <Alert v-if="error" type="error" show-icon :message="error">
        <template #action>
          <Button @click="loadReport">
            {{ t('retry') }}
          </Button>
        </template>
      </Alert>
      <Alert
        v-if="incomplete"
        type="warning"
        show-icon
        :message="t('incompleteTitle')"
        :description="t('incompleteDescription')"
      />

      <section
        class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5"
        :aria-label="t('summary')"
        :aria-busy="loading"
      >
        <div
          v-for="card in cards"
          :key="card.label"
          class="bg-card flex items-center gap-3 rounded-lg border p-4"
        >
          <IconifyIcon
            :icon="card.icon"
            class="text-muted-foreground size-5 shrink-0"
            aria-hidden="true"
          />
          <div>
            <div class="text-muted-foreground text-sm">{{ card.label }}</div>
            <div class="mt-2 text-xl font-semibold tabular-nums">
              {{ card.value }}
            </div>
          </div>
        </div>
      </section>

      <section
        class="bg-card min-w-0 rounded-lg border"
        :aria-label="t('details')"
      >
        <div
          class="flex flex-wrap items-center justify-between gap-3 border-b p-4"
        >
          <div>
            <h3 class="m-0 text-sm font-semibold">{{ t('details') }}</h3>
            <p
              class="text-muted-foreground mb-0 mt-1 text-xs"
              aria-live="polite"
            >
              {{ dateLabel }} · {{ number(report?.summary.person_count) }}
              {{ t('peopleUnit') }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <label for="capacity-sort" class="text-sm">{{ t('sort') }}</label>
            <Select
              id="capacity-sort"
              v-model:value="sortField"
              class="w-[220px] max-w-full"
              :options="sortOptions"
            />
          </div>
        </div>
        <Table
          :columns="columns"
          :data-source="rows"
          row-key="key"
          :loading="loading"
          :pagination="pagination"
          :scroll="{ x: 1680 }"
        >
          <template #emptyText>
            {{ error ? t('loadError') : t('empty') }}
          </template>
          <template #bodyCell="{ column, record }">
            <div
              v-if="column.key === 'project'"
              class="max-w-[240px] whitespace-normal break-words font-medium"
            >
              {{ record.project }}
            </div>
            <template v-else-if="column.key === 'task_types'">
              {{ taskLabels(record.task_types) }}
            </template>
            <template v-else-if="column.key === 'first_pass_rate'">
              <div>{{ percent(record.first_pass_rate) }}</div>
              <div class="text-muted-foreground text-xs">
                {{ record.first_pass_orders }} /
                {{ record.reviewed_order_count }} {{ t('ordersUnit') }}
              </div>
            </template>
            <template v-else-if="column.key === 'rework_count'">
              {{ number(record.rework_count) }}
            </template>
            <template v-else-if="column.key === 'rework_orders'">
              <div>
                {{ number(record.rework_orders) }} /
                {{ record.quality_order_count }} {{ t('ordersUnit') }}
              </div>
              <div class="text-muted-foreground text-xs">
                {{ percent(record.rework_rate) }}
              </div>
            </template>
            <template v-else-if="column.key === 'on_time_orders'">
              <div>
                {{ record.on_time_orders }} / {{ record.deadline_order_count }}
                {{ t('ordersUnit') }}
              </div>
              <div class="text-muted-foreground text-xs">
                {{ percent(record.on_time_rate) }}
              </div>
            </template>
            <template v-else-if="column.key === 'hours'">
              {{ number(record.hours, 2) }}
            </template>
            <template v-else-if="column.key === 'avg_hours'">
              {{ number(record.avg_hours, 2) }}
            </template>
          </template>
        </Table>
      </section>
      <details class="text-muted-foreground rounded-lg border p-4 text-sm">
        <summary class="text-foreground cursor-pointer font-medium">
          {{ t('metricRules') }}
        </summary>
        <ul class="mb-0 mt-3 list-disc space-y-2 pl-5">
          <li>{{ t('dateRule') }}</li>
          <li>{{ t('deliveryRule') }}</li>
          <li>{{ t('hoursRule') }}</li>
          <li>{{ t('qualityRule') }}</li>
          <li>{{ t('firstPassRule') }}</li>
          <li>{{ t('onTimeRule') }}</li>
        </ul>
      </details>
    </div>
  </main>
</template>
