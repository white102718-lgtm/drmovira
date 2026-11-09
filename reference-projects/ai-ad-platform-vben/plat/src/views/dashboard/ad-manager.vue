<script setup lang="ts">
import type { TableProps } from 'ant-design-vue';

import type { AdConfigLevel } from '#/api/management/ad-config';

import type {
  AdDashboardCategory,
  AdDashboardField,
  AdDashboardListQuery,
  AdDashboardRow,
  AdDashboardSummaryRow,
} from '#/domain/ad-dashboard';

import { computed, h, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import {
  Button,
  Card,
  Form,
  Input,
  message,
  Pagination,
  Select,
  Switch,
  Table,
  Tabs,
  Tag,
  theme,
  Tooltip,
  Typography,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import {
  AlertCircle,
  FileSearch,
  GripVertical,
  Landmark,
  X,
} from 'lucide-vue-next';

import { getUserNameOptions } from '#/api/system/user';
import {
  adDashboardService,
  formatAdDashboardValue,
  getAdDashboardStatusOptions,
} from '#/domain/ad-dashboard';
import { downloadAdDashboardCsv } from '#/domain/ad-dashboard/export';
import { summarizeAdDashboardRows } from '#/domain/ad-dashboard/normalize';
import DateRangePicker from '#/views/components/DateRangePicker.vue';
import ListLoading from '#/views/components/ListLoading.vue';

import AdColumnSettings from './components/AdColumnSettings.vue';
import AdInspectModal from './components/AdInspectModal.vue';
import AdStatusChangesModal from './components/AdStatusChangesModal.vue';
import BmListModal from './components/BmListModal.vue';
import { useAdDashboardColumns } from './use-ad-dashboard-columns';
import { useAdDashboardFixedColumns } from './use-ad-dashboard-fixed-columns';
import { useAdDashboardOperations } from './use-ad-dashboard-operations';

const route = useRoute();
const router = useRouter();
const AD_MANAGER_PATH = '/dashboard/ad-manager';
const { token: antThemeToken } = theme.useToken();
const categories = adDashboardService.getCategories();
const activeCategory = ref<AdDashboardCategory>('department');
const selectedIds = ref<Partial<Record<AdDashboardCategory, string[]>>>({});
const name = ref('');
const searchId = ref('');
const status = ref('all');
const placerIds = ref<string[]>([]);
const placerOptions = ref<Array<{ label: string; value: string }>>([]);
const placerOptionsLoading = ref(false);
const placerOptionsLoaded = ref(false);
const placerOptionsLoadFailed = ref(false);
// 默认今天。先按 CST 取日期字符串再转回时间戳，跟旧面板一致——
// 直接用 dayjs.tz().valueOf() 会带上当前时刻，日历里会选中错误的那一天
const todayTs = () => dayjs(dayjs.tz().format('YYYY-MM-DD')).valueOf();
const dateRange = ref<[number, number]>([todayTs(), todayTs()]);
const startDate = computed(() =>
  dayjs(dateRange.value[0]).format('YYYY-MM-DD'),
);
const endDate = computed(() => dayjs(dateRange.value[1]).format('YYYY-MM-DD'));
const page = ref(1);
const pageSize = ref(50);
const DEFAULT_TABLE_VISIBLE_ROW_COUNT = 7;
const total = ref(0);
const loading = ref(false);
const exporting = ref(false);
const rows = ref<AdDashboardRow[]>([]);
const summaryRows = ref<AdDashboardSummaryRow[]>([]);
type PageSpendFilter = 'all' | 'spent' | 'unspent';
const pageSpendFilter = ref<PageSpendFilter>('all');
const hasPageSpend = (row: AdDashboardRow) =>
  typeof row.spend === 'number' && row.spend > 0;
// 数量始终来自接口当前页；筛选只改变可见行，保留切换和恢复入口。
const pageSpendCounts = computed(() => {
  const spent = rows.value.filter(hasPageSpend).length;
  return { spent, unspent: rows.value.length - spent };
});
const pageSpendOptions = computed(() => [
  {
    value: 'spent' as const,
    label: '当前页有消耗',
    count: pageSpendCounts.value.spent,
  },
  {
    value: 'unspent' as const,
    label: '无消耗',
    count: pageSpendCounts.value.unspent,
  },
]);
const pageSpendSummary = computed(
  () =>
    `当前页有消耗 ${pageSpendCounts.value.spent} 条\n无消耗 ${pageSpendCounts.value.unspent} 条`,
);
const visibleRows = computed(() => {
  if (pageSpendFilter.value === 'all') return rows.value;
  return rows.value.filter(
    (row) => hasPageSpend(row) === (pageSpendFilter.value === 'spent'),
  );
});
function togglePageSpendFilter(value: Exclude<PageSpendFilter, 'all'>) {
  pageSpendFilter.value = pageSpendFilter.value === value ? 'all' : value;
}
const emptyTableRowCount = computed(() => {
  const occupiedRowCount =
    loading.value || visibleRows.value.length === 0
      ? 1
      : visibleRows.value.length;

  return Math.max(0, DEFAULT_TABLE_VISIBLE_ROW_COUNT - occupiedRowCount);
});
const dataCutoff = ref('');
const sortField = ref<string>();
const sortOrder = ref<'asc' | 'desc'>('desc');
const bmModalRef = ref<null | { openModal: (accountId: string) => void }>(null);
const inspectModalRef = ref<null | {
  openModal: (level: AdConfigLevel, objectId: string, date: string) => void;
}>(null);

// 账户只查看所属 BM；系列、组和广告还可查看配置、记录及半小时明细。
const inspectLevels: Partial<Record<AdDashboardCategory, AdConfigLevel>> = {
  campaign: 'campaign',
  adSet: 'adset',
  ad: 'ad',
};
const inspectLevel = computed(() => inspectLevels[activeCategory.value]);
const hasRowActions = computed(
  () => activeCategory.value === 'account' || Boolean(inspectLevel.value),
);

/**
 * 旧页面的名称下钻不是按当前九个 Tab 从左到右移动，以下映射保持其真实跳转行为。
 */
const nextDrillCategory: Partial<
  Record<AdDashboardCategory, AdDashboardCategory>
> = {
  account: 'campaign',
  adSet: 'ad',
  agencyLine: 'campaign',
  campaign: 'adSet',
  channel: 'account',
  department: 'project',
  platform: 'agencyLine',
  project: 'agencyLine',
};

/** 旧页面清空后续筛选时使用的业务顺序，与当前 Tab 展示顺序相互独立。 */
const legacyFilterOrder: AdDashboardCategory[] = [
  'department',
  'project',
  'platform',
  'agencyLine',
  'channel',
  'account',
  'campaign',
  'adSet',
  'ad',
];

const schema = computed(() =>
  adDashboardService.getSchema(activeCategory.value),
);
const visibleSummaryRows = computed(() => {
  if (pageSpendFilter.value === 'all') return summaryRows.value;
  const summaries = new Map(
    summarizeAdDashboardRows(visibleRows.value, schema.value).map((summary) => [
      summary.currency,
      summary,
    ]),
  );
  // 筛选为空时仍保留各币种汇总行，确保可以再次点击恢复当前页。
  return summaryRows.value.map(
    (summary) =>
      summaries.get(summary.currency) ?? {
        currency: summary.currency,
        values: {},
      },
  );
});
const {
  fields: orderedFields,
  load: loadColumnSettings,
  loadFailed: columnSettingsFailed,
  loading: columnSettingsLoading,
  reorder: reorderColumns,
  save: saveColumns,
  saving: columnSettingsSaving,
  visibleFields,
} = useAdDashboardColumns(schema);
const {
  cellStyle: fixedCellStyle,
  headerRow: fixedHeaderRow,
  isFixed: isFixedColumn,
  lastFixedKey,
} = useAdDashboardFixedColumns(visibleFields);
const {
  clearPending: clearPendingOperations,
  dialogOpen: operationDialogOpen,
  hasQueryError: operationQueryFailed,
  level: operationLevel,
  pendingChanges: pendingOperations,
  refreshing: operationStatusLoading,
  removePending: removePendingOperation,
  retryStatus: refreshOperationStatus,
  rowState: operationRowState,
  saving: operationsSaving,
  submit: submitOperations,
  timedOut: operationTimedOut,
  toggle: toggleOperation,
} = useAdDashboardOperations(activeCategory, rows, startDate, endDate);
const draggingColumn = ref('');
const columnDropTarget = ref('');
const columnReorderDisabled = computed(
  () =>
    columnSettingsLoading.value ||
    columnSettingsFailed.value ||
    columnSettingsSaving.value,
);

function clearColumnDrag() {
  draggingColumn.value = '';
  columnDropTarget.value = '';
}

/** 拖拽柄独立于指标排序按钮，移动列不会触发数据升降序查询。 */
function handleColumnDragStart(event: DragEvent, field: AdDashboardField) {
  if (columnReorderDisabled.value || field.fixed) {
    event.preventDefault();
    return;
  }
  draggingColumn.value = field.key;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', field.key);
  }
}

function handleColumnDragOver(event: DragEvent, field: AdDashboardField) {
  if (!draggingColumn.value || field.fixed || columnReorderDisabled.value) {
    columnDropTarget.value = '';
    return;
  }
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
  columnDropTarget.value = draggingColumn.value === field.key ? '' : field.key;
}

async function handleColumnDrop(event: DragEvent, field: AdDashboardField) {
  event.preventDefault();
  const key = draggingColumn.value;
  clearColumnDrag();
  if (key) await reorderColumns(key, field.key);
}

/** 表头手柄可用左右方向键移动，触屏也可使用自定义列弹窗的上下按钮。 */
async function moveHeaderColumn(key: string, offset: number) {
  const fields = visibleFields.value.filter((field) => !field.fixed);
  const index = fields.findIndex((field) => field.key === key);
  const target = fields[index + offset];
  if (index !== -1 && target) await reorderColumns(key, target.key);
}

watch(activeCategory, clearColumnDrag);
const statusLabel = computed(() =>
  activeCategory.value === 'account' ? '账户状态' : '投放状态',
);
const statusOptions = computed(() => [
  { label: '全部状态', value: 'all' },
  ...getAdDashboardStatusOptions(activeCategory.value),
]);
const statusFilterDisabled = computed(() => statusOptions.value.length === 1);

function statusColor(value: string) {
  if (
    value.includes('异常') ||
    ['已停用', '账单未结清', '有问题', '已拒绝'].includes(value)
  )
    return 'error';
  if (
    value.includes('暂停') ||
    ['待风险审核', '待结算', '宽限期', '待结算信息'].includes(value)
  )
    return 'warning';
  if (['待关闭', '已关闭', '已归档', '已删除'].includes(value))
    return 'default';
  if (value.includes('投放中') || value.includes('正常')) return 'success';
  return 'processing';
}

function renderCell(
  value: AdDashboardRow[string],
  row: AdDashboardRow,
  field: AdDashboardField,
) {
  const formatted = formatAdDashboardValue(value, field, row.currency);
  if (formatted === field.emptyText) {
    return h('span', { class: 'text-slate-400' }, formatted);
  }
  if (field.dataType === 'status') {
    return h(Tag, { color: statusColor(String(formatted)) }, () => formatted);
  }
  if (field.dataType === 'url') {
    return h(
      'a',
      {
        class: 'ux-table-link',
        href: String(value),
        rel: 'noreferrer',
        target: '_blank',
      },
      formatted,
    );
  }
  if (field.key === 'name' && nextDrillCategory[activeCategory.value]) {
    // 用 Typography.Link 而不是 Button type="link"：后者渲染成 <button>，
    // 会带出按钮的边框/焦点框，旧面板这里是纯文字链接
    return h(Tooltip, { placement: 'topLeft', title: String(formatted) }, () =>
      h(
        Typography.Link,
        {
          class: 'ux-table-link block truncate',
          onClick: () => handleNameDrill(row),
        },
        () => formatted,
      ),
    );
  }
  if (field.dataType === 'text' || field.dataType === 'identifier') {
    return h(Tooltip, { title: String(formatted) }, () =>
      h('span', { class: 'block truncate' }, formatted),
    );
  }
  return formatted;
}

function renderRowActions(row: AdDashboardRow) {
  return h('div', { class: 'flex items-center justify-start gap-1' }, [
    h(Tooltip, { title: '查看BM' }, () =>
      h(
        Button,
        {
          'aria-label': '查看BM',
          class: '!h-8 !w-8 !p-0',
          size: 'small',
          type: 'link',
          onClick: () => openBmModal(row),
        },
        () =>
          h('span', {
            'aria-hidden': 'true',
            class: 'icon-[ant-design--bank-outlined] text-base',
          }),
      ),
    ),
    inspectLevel.value
      ? h(Tooltip, { placement: 'topRight', title: '配置/记录/下钻' }, () =>
          h(
            Button,
            {
              'aria-label': '配置/记录/下钻',
              class: '!h-8 !w-8 !p-0',
              size: 'small',
              type: 'link',
              onClick: () => openInspectModal(row),
            },
            () =>
              h('span', {
                'aria-hidden': 'true',
                class: 'icon-[ant-design--file-search-outlined] text-base',
              }),
          ),
        )
      : null,
  ]);
}

const columns = computed(() => {
  const dataColumns = visibleFields.value.map((field) => ({
    customRender: ({
      record,
      text,
    }: {
      record: AdDashboardRow;
      text: AdDashboardRow[string];
    }) => renderCell(text, record, field),
    dataIndex: field.key,
    ellipsis: true,
    fixed: field.fixed,
    key: field.key,
    sorter: field.sortable,
    title: field.label,
    width: field.width,
  }));
  if (!hasRowActions.value) return dataColumns;
  return [
    ...dataColumns,
    {
      align: 'left' as const,
      customRender: ({ record }: { record: AdDashboardRow }) =>
        renderRowActions(record),
      dataIndex: 'actions',
      fixed: 'right' as const,
      key: 'actions',
      title: '操作',
      width: 104,
    },
  ];
});

const tableWidth = computed(
  () =>
    visibleFields.value.reduce((sum, field) => sum + field.width, 0) +
    (hasRowActions.value ? 104 : 0),
);

/** 列表和导出共用当前筛选；复制下钻 ID，导出期间切换维度不改变请求。 */
function buildListQuery(): AdDashboardListQuery {
  return {
    category: activeCategory.value,
    endDate: endDate.value || undefined,
    id: searchId.value.trim() || undefined,
    name: name.value.trim() || undefined,
    page: page.value,
    pageSize: pageSize.value,
    placerIds:
      activeCategory.value === 'agencyLine' ? [...placerIds.value] : undefined,
    selectedIds: Object.fromEntries(
      Object.entries(selectedIds.value).map(([category, ids]) => [
        category,
        [...ids],
      ]),
    ),
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    startDate: startDate.value || undefined,
    status: status.value,
  };
}

async function handleExport() {
  if (exporting.value) return;
  const query = buildListQuery();
  const exportSchema = schema.value;
  exporting.value = true;
  try {
    const items = await adDashboardService.listAll(query);
    if (items.length === 0) {
      message.info('当前筛选条件下没有可导出的数据');
      return;
    }
    downloadAdDashboardCsv(exportSchema, items);
    message.success(`已导出 ${items.length} 条${exportSchema.label}数据`);
  } catch {
    message.error('导出未完成，请重新查询后重试');
  } finally {
    exporting.value = false;
  }
}

let rowLoadVersion = 0;
/** 投手选项进入代理线时加载一次，展示名与业务筛选值分别绑定。 */
async function loadPlacerOptions() {
  if (placerOptionsLoading.value || placerOptionsLoaded.value) return;
  placerOptionsLoading.value = true;
  placerOptionsLoadFailed.value = false;
  try {
    const users = await getUserNameOptions(['operator', 'operator_leader']);
    placerOptions.value = users.map((user) => ({
      label: user.full_name,
      value: user.real_name,
    }));
    placerOptionsLoaded.value = true;
  } catch {
    // 请求层统一提示错误；保留未加载状态，下次展开可重试。
    placerOptionsLoadFailed.value = true;
  } finally {
    placerOptionsLoading.value = false;
  }
}

function handlePlacerDropdownChange(open: boolean) {
  if (open) void loadPlacerOptions();
}

async function loadRows() {
  const version = ++rowLoadVersion;
  const query = buildListQuery();
  loading.value = true;
  // 翻页、查询、排序和下钻均重新获取当前页，不沿用上一页的本地筛选。
  pageSpendFilter.value = 'all';
  rows.value = [];
  try {
    const result = await adDashboardService.list(query);
    if (version !== rowLoadVersion) return;
    rows.value = result.items;
    summaryRows.value = result.summaryRows;
    total.value = result.total;
    dataCutoff.value = result.dataCutoff;
  } finally {
    if (version === rowLoadVersion) loading.value = false;
  }
}

function currentQueryParams() {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(route.query)) {
    if (value == null) continue;
    params.set(
      key,
      Array.isArray(value) ? value.filter(Boolean).join(',') : String(value),
    );
  }
  return params;
}

function queryParamsSignature(params: URLSearchParams) {
  return [...params.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join('&');
}

let lastWrittenQuerySignature = '';

async function syncLegacyQuery() {
  if (route.path !== AD_MANAGER_PATH) return;
  const params = currentQueryParams();
  params.set('tab', schema.value.legacyTabKey);
  if (startDate.value && endDate.value) {
    params.set('date', `${startDate.value},${endDate.value}`);
  }
  if (name.value.trim()) params.set('keyword', name.value.trim());
  else params.delete('keyword');
  if (searchId.value.trim()) params.set('id', searchId.value.trim());
  else params.delete('id');
  params.set('page', String(page.value));
  params.set('page_size', String(pageSize.value));
  if (status.value !== 'all') params.set('status', status.value);
  else params.delete('status');
  if (sortField.value) {
    params.set('sort_by', sortField.value);
    params.set('sort_order', sortOrder.value);
  } else {
    params.delete('sort_by');
    params.delete('sort_order');
  }
  if (activeCategory.value === 'agencyLine' && placerIds.value.length > 0) {
    params.set('placer_id', placerIds.value.join(','));
  } else {
    params.delete('placer_id');
  }
  for (const category of categories) {
    const legacyTabKey = adDashboardService.getSchema(
      category.value,
    ).legacyTabKey;
    const ids = selectedIds.value[category.value] ?? [];
    if (ids.length > 0) params.set(legacyTabKey, ids.join(','));
    else params.delete(legacyTabKey);
  }
  const nextSignature = queryParamsSignature(params);
  if (nextSignature === queryParamsSignature(currentQueryParams())) {
    lastWrittenQuerySignature = '';
    return;
  }
  lastWrittenQuerySignature = nextSignature;
  await router.replace({
    path: AD_MANAGER_PATH,
    query: Object.fromEntries(params.entries()),
  });
}

function restoreLegacySelections(params: URLSearchParams) {
  for (const category of categories) {
    const legacyTabKey = adDashboardService.getSchema(
      category.value,
    ).legacyTabKey;
    const ids = (params.get(legacyTabKey) ?? '')
      .split(',')
      .filter((id) => id.length > 0);
    if (ids.length > 0) selectedIds.value[category.value] = ids;
  }
}

/** 项目日报等入口会带 date=开始,结束。两端都要用当天起止，午夜当结束会被收成前一天。 */
function restoreDateParams(params: URLSearchParams) {
  const dateParam = params.get('date');
  if (!dateParam) return;
  const [startText, endText] = dateParam.split(',');
  if (!startText) return;
  const start = dayjs(startText);
  const end = dayjs(endText || startText);
  if (!start.isValid() || !end.isValid()) return;
  dateRange.value = [
    start.startOf('day').valueOf(),
    end.endOf('day').valueOf(),
  ];
}

async function applyRouteQuery() {
  const params = currentQueryParams();
  selectedIds.value = {};
  name.value = (params.get('keyword') ?? '').trim();
  searchId.value = (params.get('id') ?? '').trim();
  restoreLegacySelections(params);
  restoreDateParams(params);
  const requestedCategory = adDashboardService.resolveCategory(
    params.get('tab') ?? params.get('category'),
  );
  if (requestedCategory) activeCategory.value = requestedCategory;
  placerIds.value =
    activeCategory.value === 'agencyLine'
      ? [
          ...new Set(
            (params.get('placer_id') ?? '')
              .split(',')
              .map((value) => value.trim())
              .filter(Boolean),
          ),
        ]
      : [];
  status.value = params.get('status') ?? 'all';
  const restoredPage = Number(params.get('page'));
  const restoredPageSize = Number(params.get('page_size'));
  page.value =
    Number.isInteger(restoredPage) && restoredPage > 0 ? restoredPage : 1;
  pageSize.value = [10, 50, 100].includes(restoredPageSize)
    ? restoredPageSize
    : 50;
  sortField.value = params.get('sort_by') || undefined;
  sortOrder.value = params.get('sort_order') === 'asc' ? 'asc' : 'desc';
  await syncLegacyQuery();
  await loadRows();
}

async function handleNameDrill(row: AdDashboardRow) {
  const currentCategory = activeCategory.value;
  const nextCategory = nextDrillCategory[currentCategory];
  if (!nextCategory) return;

  const currentIndex = legacyFilterOrder.indexOf(currentCategory);
  for (const category of legacyFilterOrder.slice(currentIndex)) {
    selectedIds.value[category] = category === currentCategory ? [row.id] : [];
  }

  // 当前对象 ID 已转为上级筛选，不能继续拿它匹配下一级对象。
  searchId.value = '';
  activeCategory.value = nextCategory;
  // 下钻保留上级对象范围，但状态只作用于当前层级。
  status.value = 'all';
  page.value = 1;
  sortField.value = undefined;
  await syncLegacyQuery();
  await loadRows();
}

async function handleSelectionClose(
  category: AdDashboardCategory,
  event: Event,
) {
  event.preventDefault();
  event.stopPropagation();
  selectedIds.value[category] = [];
  page.value = 1;
  await syncLegacyQuery();
  await loadRows();
}

function openBmModal(row: AdDashboardRow) {
  const accountId = String(
    (activeCategory.value === 'account' ? row.id : row.accountId) ?? '',
  );
  if (!accountId) {
    message.warning('该行没有账户ID');
    return;
  }
  bmModalRef.value?.openModal(accountId);
}

function openInspectModal(row: AdDashboardRow) {
  const level = inspectLevel.value;
  if (!level) return;
  const selectedDate =
    endDate.value || startDate.value || new Date().toISOString().slice(0, 10);
  inspectModalRef.value?.openModal(level, row.id, selectedDate);
}

/** 页签支持方向键和首尾定位，清除筛选按钮保持独立操作。 */
function handleCategoryKeydown(
  event: KeyboardEvent,
  category: AdDashboardCategory,
) {
  const currentIndex = categories.findIndex((item) => item.value === category);
  let nextIndex = currentIndex;
  switch (event.key) {
    case 'ArrowLeft':
      nextIndex = (currentIndex - 1 + categories.length) % categories.length;
      break;
    case 'ArrowRight':
      nextIndex = (currentIndex + 1) % categories.length;
      break;
    case 'Home':
      nextIndex = 0;
      break;
    case 'End':
      nextIndex = categories.length - 1;
      break;
    default:
      return;
  }
  event.preventDefault();
  const nextCategory = categories[nextIndex];
  if (!nextCategory) return;
  const tabList = (event.currentTarget as HTMLElement).closest(
    '[role="tablist"]',
  );
  tabList
    ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
    [nextIndex]?.focus();
  if (activeCategory.value === nextCategory.value) return;
  activeCategory.value = nextCategory.value;
  void handleCategoryChange();
}

async function handleCategoryChange() {
  searchId.value = '';
  status.value = 'all';
  page.value = 1;
  sortField.value = undefined;
  await syncLegacyQuery();
  await loadRows();
}

async function applyFilters() {
  page.value = 1;
  await syncLegacyQuery();
  await loadRows();
}

// 用 @update:value 而不是 @confirm：confirm 触发时 v-model 可能还没更新完
async function handleDateUpdate(value: [number, number] | null) {
  if (!value) return;
  page.value = 1;
  await syncLegacyQuery();
  await loadRows();
}

async function resetFilters() {
  name.value = '';
  searchId.value = '';
  status.value = 'all';
  placerIds.value = [];
  dateRange.value = [todayTs(), todayTs()];
  sortField.value = undefined;
  sortOrder.value = 'desc';
  page.value = 1;
  await syncLegacyQuery();
  await loadRows();
}

async function handlePageChange(nextPage: number, nextPageSize: number) {
  const sizeChanged = nextPageSize !== pageSize.value;
  pageSize.value = nextPageSize;
  page.value = sizeChanged ? 1 : nextPage;
  await syncLegacyQuery();
  await loadRows();
}

const handleTableChange: NonNullable<TableProps['onChange']> = async (
  _pagination,
  _filters,
  sorter,
) => {
  const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter;
  const rawField = activeSorter?.field;
  const resolvedField = Array.isArray(rawField) ? rawField.at(-1) : rawField;
  sortField.value = activeSorter?.order
    ? String(resolvedField ?? '')
    : undefined;
  sortOrder.value = activeSorter?.order === 'ascend' ? 'asc' : 'desc';
  page.value = 1;
  await syncLegacyQuery();
  await loadRows();
};

function tableCellValue(row: AdDashboardRow, field: AdDashboardField) {
  return formatAdDashboardValue(row[field.key], field, row.currency);
}

function tableStatusClass(value: string) {
  if (
    value.includes('异常') ||
    ['已停用', '账单未结清', '有问题', '已拒绝'].includes(value)
  ) {
    return 'border-destructive/30 bg-destructive/10 text-destructive';
  }
  if (
    value.includes('暂停') ||
    ['待风险审核', '待结算', '宽限期', '待结算信息'].includes(value)
  ) {
    return 'border-amber-600/25 bg-amber-50 text-amber-700';
  }
  if (['待关闭', '已关闭', '已归档', '已删除'].includes(value))
    return 'border-border bg-muted text-muted-foreground';
  if (value.includes('投放中') || value.includes('正常')) {
    return 'border-emerald-600/25 bg-emerald-50 text-emerald-700';
  }
  return 'border-primary/25 bg-primary/10 text-primary';
}

function tableSortLabel(field: AdDashboardField) {
  if (sortField.value !== field.key) return '';
  return sortOrder.value === 'asc' ? '↑' : '↓';
}

async function handleTableSort(field: AdDashboardField) {
  if (!field.sortable) return;

  if (sortField.value !== field.key) {
    sortField.value = field.key;
    sortOrder.value = 'desc';
  } else if (sortOrder.value === 'desc') {
    sortOrder.value = 'asc';
  } else {
    sortField.value = undefined;
    sortOrder.value = 'desc';
  }

  page.value = 1;
  await loadRows();
}

function summaryValue(summary: AdDashboardSummaryRow, field: AdDashboardField) {
  if (field.key === 'name') return pageSpendSummary.value;
  if (!field.summarizable) return field.emptyText;
  return formatAdDashboardValue(
    summary.values[field.key] ?? 0,
    field,
    summary.currency,
  );
}

onMounted(async () => {
  await Promise.all([applyRouteQuery(), loadColumnSettings()]);
});

watch(
  activeCategory,
  (category) => {
    if (category === 'agencyLine') {
      void loadPlacerOptions();
    } else {
      // 切出代理线即清空，避免隐藏的投手条件影响其他维度。
      placerIds.value = [];
    }
  },
  { immediate: true },
);

watch(
  () => route.fullPath,
  async () => {
    if (route.path !== AD_MANAGER_PATH) return;
    const currentSignature = queryParamsSignature(currentQueryParams());
    if (currentSignature === lastWrittenQuerySignature) {
      lastWrittenQuerySignature = '';
      return;
    }
    await applyRouteQuery();
  },
);
</script>

<template>
  <div class="contents">
    <main
      v-if="false"
      class="adpulse-section-page adpulse-dashboard-page ad-panel-page h-full overflow-hidden bg-slate-50 p-[var(--adpulse-page-gap)]"
    >
      <section class="flex h-full min-w-0 flex-col gap-3">
        <header class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="text-xs font-medium tracking-[0.14em] text-blue-600">
              DELIVERY PERFORMANCE
            </p>
            <h1 class="mt-1 text-xl font-semibold text-slate-900">广告面板</h1>
            <p class="mt-1 text-sm text-slate-500">
              九个业务粒度按广告面板工作簿独立定义字段、格式与汇总规则。
            </p>
          </div>
          <div class="text-right text-xs text-slate-500">
            <p>横向滚动仅发生在表格内部</p>
            <p class="mt-1">数据截止：{{ dataCutoff || '—' }}</p>
          </div>
        </header>

        <div class="flex-none border-b bg-white px-4">
          <Tabs
            v-model:active-key="activeCategory"
            class="pt-1"
            @change="handleCategoryChange"
          >
            <Tabs.TabPane v-for="category in categories" :key="category.value">
              <template #tab>
                <span class="flex items-center gap-1.5">
                  <span>{{ category.label }}</span>
                  <Tag
                    v-if="selectedIds[category.value]?.length"
                    class="mr-0"
                    color="blue"
                    closable
                    @close="
                      (event) => handleSelectionClose(category.value, event)
                    "
                  >
                    {{ selectedIds[category.value]?.length }}项
                  </Tag>
                </span>
              </template>
            </Tabs.TabPane>
          </Tabs>
          <div
            class="grid gap-2 border-t border-slate-100 p-3 sm:grid-cols-2 xl:grid-cols-[240px_repeat(3,minmax(160px,1fr))_auto]"
          >
            <DateRangePicker
              v-model:value="dateRange"
              type="daterange"
              width="240px"
              format="yyyy-MM-dd"
              :clearable="false"
              @update:value="handleDateUpdate"
            />
            <label class="flex min-w-0 items-center gap-2">
              <span class="text-muted-foreground shrink-0 text-sm">名称</span>
              <Input
                v-model:value="name"
                aria-label="名称"
                placeholder="名称模糊匹配"
                allow-clear
                @press-enter="applyFilters"
              />
            </label>
            <label class="flex min-w-0 items-center gap-2">
              <span class="text-muted-foreground shrink-0 text-sm">ID</span>
              <Input.TextArea
                v-if="activeCategory === 'account'"
                v-model:value="searchId"
                class="ad-panel-account-ids"
                aria-label="账户 ID，每行一个"
                placeholder="每行一个 ID，精确匹配"
                :auto-size="false"
                :rows="1"
                allow-clear
              />
              <Input
                v-else
                v-model:value="searchId"
                aria-label="ID"
                placeholder="ID 精确匹配"
                allow-clear
                @press-enter="applyFilters"
              />
            </label>
            <Select
              v-model:value="status"
              :aria-label="statusLabel"
              :disabled="statusFilterDisabled"
              :options="statusOptions"
            />
            <div class="flex gap-2">
              <Button type="primary" @click="applyFilters">查询</Button>
              <Button @click="resetFilters">重置</Button>
            </div>
          </div>
        </div>

        <Card
          class="min-h-0 flex-1"
          :body-style="{ height: '100%', padding: '0' }"
        >
          <div class="flex h-full min-h-0 flex-col">
            <div
              class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3"
            >
              <div>
                <h2 class="font-semibold text-slate-900">
                  {{ schema.label }}数据
                </h2>
                <p class="mt-0.5 text-xs text-slate-500">
                  共 {{ total }} 条；当前页 {{ rows.length }} 条；字段来自“{{
                    schema.sheetName
                  }}”Sheet
                </p>
              </div>
              <Tag color="blue">{{ schema.fields.length }} 个独立字段</Tag>
            </div>

            <div
              class="ad-panel-table min-h-0 flex-1"
              :style="{ '--ad-table-width': `${tableWidth}px` }"
            >
              <Table
                :columns="columns"
                :data-source="rows"
                :loading="loading"
                :pagination="false"
                :scroll="{ x: tableWidth, y: 420 }"
                table-layout="fixed"
                row-key="key"
                @change="handleTableChange"
              >
                <template #summary>
                  <Table.Summary fixed>
                    <Table.Summary.Row
                      v-for="summary in summaryRows.filter(
                        (item) => item.currency !== 'EUR',
                      )"
                      :key="summary.currency"
                    >
                      <Table.Summary.Cell
                        v-for="(field, fieldIndex) in schema.fields"
                        :key="field.key"
                        :index="fieldIndex"
                      >
                        <strong
                          v-if="field.key === 'name'"
                          class="whitespace-pre-line"
                        >
                          {{ summaryValue(summary, field) }}
                        </strong>
                        <span v-else>
                          {{ summaryValue(summary, field) }}
                        </span>
                      </Table.Summary.Cell>
                      <Table.Summary.Cell
                        v-if="hasRowActions"
                        :index="schema.fields.length"
                      />
                    </Table.Summary.Row>
                  </Table.Summary>
                </template>
              </Table>
            </div>

            <div
              class="flex flex-none justify-end border-t border-slate-100 px-4 py-3"
            >
              <Pagination
                v-model:current="page"
                v-model:page-size="pageSize"
                :page-size-options="['10', '50', '100']"
                :total="total"
                show-less-items
                show-size-changer
                @change="handlePageChange"
              />
            </div>
          </div>
        </Card>
      </section>
      <BmListModal ref="bmModalRef" />
      <AdInspectModal ref="inspectModalRef" />
    </main>

    <main
      class="adpulse-section-page adpulse-dashboard-page bg-background flex h-full min-w-0 flex-col gap-4 overflow-y-auto overflow-x-hidden p-[var(--adpulse-page-gap)] md:overflow-hidden"
    >
      <header
        class="business-page-header flex flex-wrap items-start justify-between gap-4 border px-[var(--adpulse-card-padding)] py-[var(--adpulse-page-header-padding-block)]"
      >
        <div class="min-w-0">
          <h1 class="text-foreground text-xl font-semibold tracking-tight">
            广告面板
          </h1>
          <p class="text-muted-foreground mt-1 text-sm">
            按业务维度查看投放表现，并快速下钻到关联对象。
          </p>
        </div>
        <div class="text-muted-foreground flex shrink-0 items-center text-xs">
          数据截止：{{ dataCutoff || '—' }}
        </div>
      </header>

      <Card
        class="flex-none overflow-hidden md:min-h-0 md:flex-1"
        :body-style="{ height: '100%', padding: 0 }"
      >
        <div class="flex min-h-0 flex-col md:h-full">
          <div
            class="bg-card border-b px-4 pt-2"
            :style="{
              '--ad-tab-color': antThemeToken.colorPrimary,
              '--ad-tab-idle-background': '#32363905',
              '--ad-tab-tag-font-size': `${antThemeToken.fontSizeSM}px`,
              '--ad-tab-tag-radius': `${antThemeToken.borderRadius}px`,
            }"
          >
            <div
              class="flex gap-0.5 overflow-x-auto"
              role="tablist"
              aria-label="广告数据维度"
            >
              <div
                v-for="category in categories"
                :key="category.value"
                class="ad-panel-tab flex shrink-0 items-center justify-center gap-1.5 rounded-t-xl border"
                :class="
                  activeCategory === category.value
                    ? 'bg-card'
                    : 'bg-[var(--ad-tab-idle-background)]'
                "
              >
                <button
                  :aria-selected="activeCategory === category.value"
                  class="ad-panel-tab-label flex h-full min-w-0 flex-1 items-center justify-center whitespace-nowrap font-normal transition-colors"
                  role="tab"
                  :tabindex="activeCategory === category.value ? 0 : -1"
                  type="button"
                  @keydown="handleCategoryKeydown($event, category.value)"
                  @click="
                    activeCategory = category.value;
                    handleCategoryChange();
                  "
                >
                  {{ category.label }}
                </button>
                <Tag
                  v-if="selectedIds[category.value]?.length"
                  class="ad-panel-tab-selection"
                  color="blue"
                >
                  {{ selectedIds[category.value]?.length }}项
                  <button
                    :aria-label="`清除${category.label}筛选`"
                    class="hover:bg-accent flex size-5 items-center justify-center rounded-sm transition-colors"
                    type="button"
                    @click="handleSelectionClose(category.value, $event)"
                  >
                    <X class="size-3" aria-hidden="true" />
                  </button>
                </Tag>
              </div>
            </div>
          </div>

          <section class="border-b p-4" aria-label="广告数据筛选">
            <Form class="ux-filter-form" layout="vertical">
              <Form.Item class="ux-filter-field" label="日期">
                <DateRangePicker
                  v-model:value="dateRange"
                  type="daterange"
                  width="100%"
                  format="yyyy-MM-dd"
                  :clearable="false"
                  @update:value="handleDateUpdate"
                />
              </Form.Item>
              <Form.Item class="ux-filter-field" label="名称">
                <Input
                  v-model:value="name"
                  placeholder="名称模糊匹配"
                  allow-clear
                  @keyup.enter="applyFilters"
                />
              </Form.Item>
              <Form.Item class="ux-filter-field" label="ID">
                <Input.TextArea
                  v-if="activeCategory === 'account'"
                  v-model:value="searchId"
                  class="ad-panel-account-ids"
                  aria-label="账户 ID，每行一个"
                  placeholder="每行一个 ID，精确匹配"
                  :auto-size="false"
                  :rows="1"
                  allow-clear
                />
                <Input
                  v-else
                  v-model:value="searchId"
                  placeholder="ID 精确匹配"
                  allow-clear
                  @keyup.enter="applyFilters"
                />
              </Form.Item>
              <Form.Item
                v-if="activeCategory === 'agencyLine'"
                class="ux-filter-field"
                label="投手"
              >
                <Select
                  v-model:value="placerIds"
                  allow-clear
                  aria-label="投手"
                  class="w-full"
                  mode="multiple"
                  option-filter-prop="label"
                  placeholder="全部投手"
                  show-search
                  :loading="placerOptionsLoading"
                  :max-tag-count="1"
                  :not-found-content="
                    placerOptionsLoadFailed
                      ? '加载失败，请重新展开重试'
                      : undefined
                  "
                  :options="placerOptions"
                  @dropdown-visible-change="handlePlacerDropdownChange"
                />
              </Form.Item>
              <Form.Item class="ux-filter-field" :label="statusLabel">
                <Select
                  v-model:value="status"
                  class="w-full"
                  :aria-label="statusLabel"
                  :disabled="statusFilterDisabled"
                  :options="statusOptions"
                />
              </Form.Item>
              <div class="ux-filter-actions">
                <Button type="primary" @click="applyFilters">查询</Button>
                <Button @click="resetFilters">重置</Button>
              </div>
            </Form>
          </section>

          <section class="flex min-h-0 flex-1 flex-col" aria-live="polite">
            <div
              class="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3"
            >
              <div class="min-w-0">
                <h2 class="text-foreground text-sm font-semibold">
                  {{ schema.label }}数据
                </h2>
                <p class="text-muted-foreground mt-0.5 text-xs">
                  共 {{ total }} 条，当前页 {{ rows.length }} 条<span
                    v-if="pageSpendFilter !== 'all'"
                    >（当前显示 {{ visibleRows.length }} 条）</span
                  >。拖动表头手柄调整列顺序，自动保存。
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <span
                  v-if="columnSettingsSaving"
                  class="text-muted-foreground text-xs"
                  role="status"
                  >列配置保存中…</span
                >
                <span
                  v-if="operationQueryFailed || operationTimedOut"
                  class="text-destructive text-xs"
                  role="status"
                >
                  {{
                    operationTimedOut
                      ? '执行结果待确认，请刷新状态或查看操作记录'
                      : '操作状态获取失败，请重试'
                  }}
                </span>
                <Button
                  v-if="
                    operationLevel || operationQueryFailed || operationTimedOut
                  "
                  :loading="operationStatusLoading"
                  :disabled="operationsSaving"
                  @click="refreshOperationStatus"
                  >刷新操作状态</Button
                >
                <Button
                  v-if="pendingOperations.length > 0"
                  :disabled="operationsSaving"
                  @click="clearPendingOperations"
                  >撤销变更</Button
                >
                <Button
                  v-if="pendingOperations.length > 0"
                  type="primary"
                  :loading="operationsSaving"
                  @click="operationDialogOpen = true"
                >
                  变更确认（{{ pendingOperations.length }}）
                </Button>
                <Tag class="shrink-0"
                  >{{ visibleFields.length }} /
                  {{ schema.fields.length }} 个字段</Tag
                >
                <Button
                  v-if="columnSettingsFailed"
                  :loading="columnSettingsLoading"
                  @click="loadColumnSettings"
                  >重试列配置</Button
                >
                <AdColumnSettings
                  :schema="schema"
                  :fields="orderedFields"
                  :visible-fields="visibleFields"
                  :loading="columnSettingsLoading"
                  :disabled="columnReorderDisabled"
                  :save="saveColumns"
                />
                <Button
                  :loading="exporting"
                  :disabled="loading"
                  @click="handleExport"
                  >导出表格</Button
                >
              </div>
            </div>

            <div
              class="ux-native-table-viewport ad-panel-table-viewport min-h-0 min-w-0 flex-none md:flex-1"
              :class="{ 'bg-muted flex': loading }"
              :aria-busy="loading"
              :style="{
                '--ad-table-width': `${tableWidth}px`,
              }"
            >
              <!-- 加载提示占满可见视区，不随宽表的总列宽偏移到屏幕外。 -->
              <ListLoading v-if="loading" fill />
              <!-- 自动列宽结合数值不换行，让明细与汇总共同撑开列宽，横向滚动限制在表格内。 -->
              <table
                v-show="!loading"
                class="w-full min-w-[var(--ad-table-width)] table-auto border-collapse text-left text-sm"
              >
                <!-- 固定表头、汇总栏及操作列使用不透明背景，避免滚动内容透出。 -->
                <thead class="bg-muted sticky top-0 z-30">
                  <tr ref="fixedHeaderRow" class="border-b">
                    <th
                      v-for="field in visibleFields"
                      :key="field.key"
                      :data-field-key="field.key"
                      :style="fixedCellStyle(field)"
                      class="text-muted-foreground h-11 px-4 text-xs font-semibold"
                      :class="{
                        'bg-accent ring-primary ring-1 ring-inset':
                          columnDropTarget === field.key,
                        'bg-muted sticky z-10': isFixedColumn(field),
                        'ad-panel-fixed-edge': field.key === lastFixedKey,
                      }"
                      @dragover="handleColumnDragOver($event, field)"
                      @drop="handleColumnDrop($event, field)"
                    >
                      <div class="inline-flex items-center gap-1">
                        <button
                          :class="[
                            'inline-flex items-center gap-1 whitespace-nowrap rounded text-left transition-colors',
                            field.sortable
                              ? 'hover:text-foreground focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-1'
                              : 'cursor-default',
                          ]"
                          :disabled="!field.sortable"
                          type="button"
                          @click="handleTableSort(field)"
                        >
                          {{ field.label }}
                          <span
                            v-if="tableSortLabel(field)"
                            aria-hidden="true"
                            >{{ tableSortLabel(field) }}</span
                          >
                        </button>
                        <button
                          v-if="!field.fixed"
                          type="button"
                          :draggable="!columnReorderDisabled"
                          :disabled="columnReorderDisabled"
                          :aria-label="`调整${field.label}列的位置，可拖动或按左右方向键`"
                          title="拖动调整列顺序，自动保存"
                          class="text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-ring inline-flex size-6 shrink-0 cursor-grab items-center justify-center rounded focus-visible:outline-none focus-visible:ring-1 active:cursor-grabbing disabled:cursor-default disabled:opacity-40"
                          @click.stop
                          @dragstart="handleColumnDragStart($event, field)"
                          @dragend="clearColumnDrag"
                          @keydown.left.prevent="
                            moveHeaderColumn(field.key, -1)
                          "
                          @keydown.right.prevent="
                            moveHeaderColumn(field.key, 1)
                          "
                        >
                          <GripVertical class="size-3.5" aria-hidden="true" />
                        </button>
                      </div>
                    </th>
                    <th
                      v-if="hasRowActions"
                      class="bg-muted text-muted-foreground sticky right-0 h-11 w-[104px] min-w-[104px] border-l px-4 text-left text-xs font-semibold"
                    >
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody class="bg-card">
                  <tr v-if="visibleRows.length === 0">
                    <td
                      :colspan="visibleFields.length + (hasRowActions ? 1 : 0)"
                      class="text-muted-foreground h-[52px] text-center"
                    >
                      {{
                        pageSpendFilter === 'all'
                          ? '暂无匹配数据'
                          : '当前页没有符合消耗条件的数据，点击已选项可恢复全部'
                      }}
                    </td>
                  </tr>
                  <tr
                    v-for="row in visibleRows"
                    v-else
                    :key="row.key"
                    class="hover:bg-muted group h-[52px] border-b transition-colors"
                  >
                    <td
                      v-for="field in visibleFields"
                      :key="field.key"
                      :data-field-key="field.key"
                      :style="fixedCellStyle(field)"
                      :class="[
                        ['identifier', 'text', 'url'].includes(field.dataType)
                          ? 'max-w-0'
                          : 'whitespace-nowrap',
                        {
                          'bg-card group-hover:bg-muted sticky z-10':
                            isFixedColumn(field),
                          'ad-panel-fixed-edge': field.key === lastFixedKey,
                        },
                      ]"
                      class="px-4 py-2.5 align-middle"
                    >
                      <div
                        v-if="field.key === 'statusText' && operationLevel"
                        class="flex items-center gap-2 whitespace-nowrap"
                      >
                        <Tag
                          :class="
                            tableStatusClass(String(tableCellValue(row, field)))
                          "
                          class="m-0 shrink-0 rounded-full font-medium"
                        >
                          {{ tableCellValue(row, field) }}
                        </Tag>
                        <Tooltip
                          :title="
                            operationRowState(row).disabledReason ||
                            (operationRowState(row).pending
                              ? '待确认提交'
                              : '切换后需确认提交')
                          "
                        >
                          <span class="inline-flex">
                            <Switch
                              :aria-label="`${row.name || row.id}的开启状态`"
                              :checked="operationRowState(row).checked"
                              :disabled="
                                Boolean(operationRowState(row).disabledReason)
                              "
                              :loading="
                                operationRowState(row).busy &&
                                !operationRowState(row).uncertain
                              "
                              :checked-children="
                                operationRowState(row).uncertain
                                  ? '待确认'
                                  : operationRowState(row).busy
                                    ? '开启中'
                                    : '已开启'
                              "
                              :un-checked-children="
                                operationRowState(row).uncertain
                                  ? '待确认'
                                  : operationRowState(row).busy
                                    ? '暂停中'
                                    : '已暂停'
                              "
                              @change="
                                (checked) =>
                                  toggleOperation(row, checked === true)
                              "
                            />
                          </span>
                        </Tooltip>
                        <Tooltip
                          v-if="operationRowState(row).error"
                          :title="operationRowState(row).error"
                        >
                          <span
                            tabindex="0"
                            :aria-label="operationRowState(row).error"
                            ><AlertCircle
                              class="text-destructive size-4"
                              aria-hidden="true"
                          /></span>
                        </Tooltip>
                        <Tooltip
                          v-else-if="operationRowState(row).pending"
                          title="待确认提交"
                        >
                          <span
                            class="text-muted-foreground text-xs"
                            aria-label="待确认提交"
                            >待提交</span
                          >
                        </Tooltip>
                      </div>
                      <span
                        v-else-if="
                          tableCellValue(row, field) === field.emptyText
                        "
                        class="text-muted-foreground"
                        >{{ field.emptyText }}</span
                      >
                      <Tag
                        v-else-if="field.dataType === 'status'"
                        :class="
                          tableStatusClass(String(tableCellValue(row, field)))
                        "
                        class="max-w-full truncate rounded-full font-medium"
                        >{{ tableCellValue(row, field) }}</Tag
                      >
                      <a
                        v-else-if="field.dataType === 'url'"
                        :href="String(row[field.key])"
                        class="ux-table-link block truncate"
                        :title="String(tableCellValue(row, field))"
                        rel="noreferrer"
                        target="_blank"
                        >{{ tableCellValue(row, field) }}</a
                      >
                      <Tooltip
                        v-else-if="
                          field.key === 'name' &&
                          nextDrillCategory[activeCategory]
                        "
                        :title="String(tableCellValue(row, field))"
                        :trigger="['hover', 'focus']"
                        placement="topLeft"
                      >
                        <Typography.Link
                          class="ux-table-link block max-w-full truncate text-left text-sm font-normal"
                          role="button"
                          :tabindex="0"
                          @click="handleNameDrill(row)"
                          @keydown.enter.prevent="handleNameDrill(row)"
                          @keydown.space.prevent="handleNameDrill(row)"
                        >
                          {{ tableCellValue(row, field) }}
                        </Typography.Link>
                      </Tooltip>
                      <span
                        v-else
                        :class="
                          ['identifier', 'text'].includes(field.dataType)
                            ? 'truncate'
                            : 'whitespace-nowrap tabular-nums'
                        "
                        class="block"
                        :title="String(tableCellValue(row, field))"
                        >{{ tableCellValue(row, field) }}</span
                      >
                    </td>
                    <td
                      v-if="hasRowActions"
                      class="bg-card group-hover:bg-muted sticky right-0 z-10 border-l px-2 py-2 text-left"
                    >
                      <div class="flex justify-start gap-1">
                        <Button
                          aria-label="查看 BM"
                          title="查看 BM"
                          type="text"
                          @click="openBmModal(row)"
                        >
                          <Landmark class="size-4" aria-hidden="true" />
                        </Button>
                        <Button
                          v-if="inspectLevel"
                          aria-label="配置、记录与下钻"
                          title="配置、记录与下钻"
                          type="text"
                          @click="openInspectModal(row)"
                        >
                          <FileSearch class="size-4" aria-hidden="true" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                  <tr
                    v-for="emptyRow in emptyTableRowCount"
                    :key="`empty-${emptyRow}`"
                    aria-hidden="true"
                    class="h-[52px] border-b"
                  >
                    <td
                      :colspan="visibleFields.length + (hasRowActions ? 1 : 0)"
                    ></td>
                  </tr>
                </tbody>
                <tfoot class="bg-muted sticky bottom-0 z-20">
                  <tr
                    v-for="summary in visibleSummaryRows.filter(
                      (item) => item.currency !== 'EUR',
                    )"
                    :key="summary.currency"
                    class="border-t-2 text-xs"
                  >
                    <td
                      v-for="field in visibleFields"
                      :key="field.key"
                      :style="fixedCellStyle(field)"
                      :class="{
                        'sticky z-10': isFixedColumn(field),
                        'ad-panel-fixed-edge': field.key === lastFixedKey,
                      }"
                      class="bg-muted h-[52px] whitespace-nowrap px-4 py-2 font-medium tabular-nums"
                    >
                      <div
                        v-if="field.key === 'name'"
                        class="flex flex-col items-start"
                      >
                        <button
                          v-for="option in pageSpendOptions"
                          :key="option.value"
                          type="button"
                          class="focus-visible:ring-ring cursor-pointer rounded-sm p-0 text-left text-xs leading-5 underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50"
                          :class="{
                            'font-semibold underline':
                              pageSpendFilter === option.value,
                          }"
                          :style="{ color: antThemeToken.colorLink }"
                          :aria-pressed="pageSpendFilter === option.value"
                          :aria-label="`${option.label} ${option.count} 条，${pageSpendFilter === option.value ? '点击恢复当前页全部数据' : '点击筛选当前页数据'}`"
                          :title="
                            pageSpendFilter === option.value
                              ? '再次点击恢复当前页全部数据'
                              : '仅显示当前页匹配的数据'
                          "
                          :disabled="loading"
                          @click="togglePageSpendFilter(option.value)"
                        >
                          {{ option.label }} {{ option.count }} 条
                        </button>
                      </div>
                      <span v-else>
                        {{ summaryValue(summary, field) }}
                      </span>
                    </td>
                    <td
                      v-if="hasRowActions"
                      class="bg-muted sticky bottom-0 right-0 z-20 border-l"
                    ></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </section>

          <footer
            class="bg-card flex flex-wrap items-center justify-end gap-3 border-t px-4 py-3"
          >
            <Pagination
              :current="page"
              :page-size="pageSize"
              :page-size-options="['10', '50', '100']"
              :total="total"
              show-less-items
              show-size-changer
              @change="handlePageChange"
            />
          </footer>
        </div>
      </Card>
      <AdStatusChangesModal
        v-model:open="operationDialogOpen"
        :changes="pendingOperations"
        :saving="operationsSaving"
        @remove="removePendingOperation"
        @submit="submitOperations"
      />
      <BmListModal ref="bmModalRef" />
      <AdInspectModal ref="inspectModalRef" />
    </main>
  </div>
</template>

<style scoped>
@media (min-width: 768px) {
  .ad-panel-table-viewport {
    --ad-panel-viewport-height: auto;
  }
}

/* 固定区域边界使用内阴影，不增加列宽，也不会随横向滚动留下透明缝隙。 */
.ad-panel-fixed-edge {
  box-shadow: inset -1px 0 hsl(var(--border));
}

/* 批量 ID 保持筛选控件高度，换行只在框内滚动，不撑高整行。 */
:deep(textarea.ad-panel-account-ids) {
  height: var(--adpulse-control-height);
  min-height: var(--adpulse-control-height);
  max-height: var(--adpulse-control-height);
  padding-block: calc((var(--adpulse-control-height) - 1.5em - 2px) / 2);
  overflow-y: auto;
  line-height: 1.5;
  resize: none;
}

.ad-panel-table :deep(tfoot > tr > td) {
  font-size: 12px;
  white-space: nowrap;
  background: #f8fafc;
}

.ad-panel-table-viewport {
  height: var(--adpulse-table-viewport-height);
}

/* 页签蓝色沿用 Ant Design 的语义色，避免跟随 Vben 的黑色主按钮主题。 */
.ad-panel-tab-selection {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
  align-items: center;
  padding-inline: 6px 2px;
  margin-inline-end: 0;
  font-size: var(--ad-tab-tag-font-size);
  border-radius: var(--ad-tab-tag-radius);
}

.ad-panel-tab {
  height: var(--adpulse-control-height);
  min-width: calc(var(--adpulse-control-height) + 56px);
  padding: 0 var(--adpulse-action-gap);
}

.ad-panel-tab-label {
  color: var(--adpulse-text-muted);
  font-size: var(--adpulse-control-font-size);
}

.ad-panel-tab-label:focus-visible {
  outline-offset: -2px;
}

.ad-panel-tab-label[aria-selected='true'],
.ad-panel-tab-label:hover {
  color: var(--ad-tab-color);
}
</style>
