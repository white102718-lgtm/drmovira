<script setup lang="ts">
import type {
  FilterOptions,
  PersonnelSpendItem,
  PersonnelSpendLevel,
  PersonnelSpendQuery,
  PersonnelSpendSummary,
} from '#/api/dashboard';
import type { AntDataTableColumn } from '#/components/ui/AntDataTable.vue';

import { computed, onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { useElementSize } from '@vueuse/core';
import { Button, Card, Form, message, Select, Tag } from 'ant-design-vue';
import dayjs from 'dayjs';
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  ChevronRight,
  Clock3,
  CreditCard,
  FolderOpen,
  Search,
  UsersRound,
  Wallet,
} from 'lucide-vue-next';

import { getFilterOptions, getPersonnelSpend } from '#/api/dashboard';
import AntDataTable from '#/components/ui/AntDataTable.vue';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import { formatAccountStatus } from '#/domain/ad-dashboard/normalize';
import DateRangePicker from '#/views/components/DateRangePicker.vue';

const contentRef = ref<HTMLDivElement>();
const panelHeaderRef = ref<HTMLDivElement>();
// 标题区会随下钻和窄屏换行改变高度，列头始终贴在其下方。
const { height: panelHeaderHeight } = useElementSize(
  panelHeaderRef,
  undefined,
  {
    box: 'border-box',
  },
);
const tableSticky = computed(() => ({
  getContainer: () => contentRef.value?.parentElement ?? window,
  offsetHeader: panelHeaderHeight.value,
}));

const today = dayjs.tz().format('YYYY-MM-DD');
const dateRange = ref<[number, number]>([
  dayjs(today).valueOf(),
  dayjs(today).endOf('day').valueOf(),
]);

const loading = ref(false);
const filterOptionsLoading = ref(false);
const data = ref<PersonnelSpendItem[]>([]);
// 公共表格插槽未透传行泛型，按稳定 ID 取回接口行，避免用类型断言绕过校验。
const itemsById = computed(
  () => new Map(data.value.map((item) => [item.id, item])),
);
const total = ref(0);
const recordCount = ref(0);
const missingSpendCount = ref(0);
const spendNote = computed(
  () =>
    `按原币种统计，未合并换算；— 表示无有效消耗${missingSpendCount.value ? `；另有 ${missingSpendCount.value} 条明细缺少消耗数据` : ''}`,
);
const summary = ref<PersonnelSpendSummary>();
const summaryUpdatedAt = ref<null | string>(null);
const summaryLoading = ref(false);
const loadFailed = ref(false);
const sortKey = ref('');
const sortDescending = ref(false);
let requestSequence = 0;
type PersonnelEntityLevel = 'ad' | 'adset' | 'campaign';
interface DrillContext {
  accountId?: string;
  adSetId?: string;
  adSetName?: string;
  campaignId?: string;
  campaignName?: string;
  gamePlatform?: string;
  placerId?: string;
  placerName?: string;
}
interface DrillStep {
  context: DrillContext;
  label: string;
  level: PersonnelSpendLevel;
}
const rootStep: DrillStep = {
  context: {},
  label: '全部人员',
  level: 'personnel',
};
// 记录真实进入路径，人员直接查看广告时，返回仍回到人员页，不虚构中间层级。
const drillPath = ref<DrillStep[]>([rootStep]);
const currentStep = computed(() => drillPath.value.at(-1) ?? rootStep);
const level = computed(() => currentStep.value.level);
const drill = computed(() => currentStep.value.context);
/** 首次进入与重置沿用旧人员面板默认部门，查询始终传原始部门值。 */
const emptyFilters = () => ({
  account_attribute: [] as string[],
  department: ['投放二组'],
  game_platform: [] as string[],
  placer_id: [] as string[],
});
const filters = ref(emptyFilters());
// 下钻始终使用已执行的筛选，编辑下拉但未点查询时不改变数据范围。
const appliedQuery = ref<PersonnelSpendQuery>({ date: '' });
const routeStateReady = ref(false);
const filterOptions = ref<FilterOptions>({
  channels: [],
  departments: [],
  placers: [],
  projects: [],
  regions: [],
});

const departmentOptions = computed(
  () =>
    filterOptions.value.department_options ??
    filterOptions.value.departments.map((item) => ({
      label: item === '投放二组' ? 'MP投放部' : item,
      value: item,
    })),
);
const accountAttributeOptions = computed(() =>
  (filterOptions.value.account_attributes ?? []).map((value) => ({
    label: value,
    value,
  })),
);
const placerOptions = computed(() => filterOptions.value.placers);
const projectOptions = computed(() =>
  filterOptions.value.projects.map((item) => ({ label: item, value: item })),
);

const levelLabels: Record<PersonnelSpendLevel, string> = {
  personnel: '投放人员',
  account: '账户名称',
  project: '项目',
  campaign: '系列名称',
  adset: '广告组名称',
  ad: '广告名称',
};
const nextLevel: Partial<Record<PersonnelSpendLevel, PersonnelSpendLevel>> = {
  personnel: 'account',
  account: 'project',
  project: 'campaign',
  campaign: 'adset',
  adset: 'ad',
};
const detailColumns = [
  { key: 'campaign_count', title: '系列明细', level: 'campaign' },
  { key: 'adset_count', title: '组明细', level: 'adset' },
  { key: 'ad_count', title: '广告明细', level: 'ad' },
] as const;
const visibleDetailColumns = computed(() => {
  if (level.value === 'personnel') return detailColumns;
  if (level.value === 'campaign') {
    return detailColumns.filter((column) => column.level !== 'campaign');
  }
  return [];
});
const isEntityLevel = computed(() =>
  ['campaign', 'adset', 'ad'].includes(level.value),
);

/** 表格和导出共用指标顺序与格式，分母为零显示空值。 */
const DRILL_METRICS = [
  { key: 'cpc', title: 'CPC', width: 100 },
  { key: 'cpm', title: 'CPM', width: 100 },
  { key: 'register_cost', title: '注册成本', width: 110 },
  { key: 'payment_cost', title: '付费成本', width: 110 },
] as const;
const formatMetric = (value?: null | number) =>
  value === null || value === undefined ? '—' : Number(value).toFixed(2);

interface PersonnelColumn extends AntDataTableColumn {
  drillLevel?: PersonnelEntityLevel;
  format?: (item: PersonnelSpendItem) => string;
  value?: (item: PersonnelSpendItem) => null | number | string | undefined;
}
const currencies = computed(() =>
  [
    ...new Set(
      data.value.flatMap((item) => item.spends.map((spend) => spend.currency)),
    ),
  ].sort(),
);
const spendAmount = (item: PersonnelSpendItem, currency: string) =>
  item.spends.find((spend) => spend.currency === currency)?.amount;
const spendColumns = computed<PersonnelColumn[]>(() => [
  ...currencies.value.map((currency) => ({
    key: `spend_${currency}`,
    title: `消耗（${currency}）`,
    align: 'center' as const,
    width: 160,
    value: (item: PersonnelSpendItem) => spendAmount(item, currency),
    format: (item: PersonnelSpendItem) =>
      formatMetric(spendAmount(item, currency)),
  })),
  // 无数据或全部缺少有效消耗时仍保留表头，不猜测币种，也不将缺失金额视为零。
  ...(currencies.value.length === 0
    ? [
        {
          key: 'spend_empty',
          title: '消耗',
          align: 'center' as const,
          width: 160,
          value: () => undefined,
        },
      ]
    : []),
]);
const columns = computed<PersonnelColumn[]>(() => [
  {
    align: 'left',
    dataIndex: 'name',
    key: 'name',
    title: levelLabels[level.value],
    width: 220,
    value: (item) => item.name,
  },
  ...(level.value === 'personnel'
    ? [
        {
          key: 'account_count',
          title: '关联账户（未消耗/已消耗）',
          align: 'center' as const,
          width: 240,
          value: (item: PersonnelSpendItem) => item.account_count,
          format: formatAccountCount,
        },
      ]
    : []),
  ...(level.value === 'account' || isEntityLevel.value
    ? [
        {
          align: 'center' as const,
          dataIndex: 'account_id',
          key: 'account_id',
          title: '账户ID',
          width: 190,
          value: (item: PersonnelSpendItem) => item.account_id,
          format: (item: PersonnelSpendItem) =>
            formatAccountId(item.account_id || item.id),
        },
        ...(level.value === 'account'
          ? [
              {
                align: 'center' as const,
                dataIndex: 'account_status',
                key: 'account_status',
                title: '账户状态',
                width: 130,
                value: (item: PersonnelSpendItem) =>
                  formatAccountStatus(item.account_status),
              },
              ...spendColumns.value,
            ]
          : []),
        {
          align: 'center' as const,
          dataIndex: 'account_attribute',
          key: 'account_attribute',
          title: '账户类型',
          width: 130,
          value: (item: PersonnelSpendItem) => item.account_attribute,
        },
        ...(level.value === 'account'
          ? [
              {
                align: 'center' as const,
                dataIndex: 'tag',
                key: 'tag',
                title: '标识',
                width: 100,
                value: (item: PersonnelSpendItem) => item.tag,
              },
            ]
          : [
              {
                align: 'center' as const,
                key: 'game_platform',
                title: '项目',
                width: 150,
                value: (item: PersonnelSpendItem) => item.game_platform,
              },
            ]),
      ]
    : []),
  ...(['account', 'personnel'].includes(level.value)
    ? [
        {
          key: 'project_count',
          title: '关联项目',
          align: 'center' as const,
          width: 110,
          value: (item: PersonnelSpendItem) => item.project_count,
        },
      ]
    : []),
  ...(['adset', 'ad'].includes(level.value)
    ? [
        {
          align: 'center' as const,
          key: 'campaign_name',
          title: '所属系列',
          width: 220,
          value: (item: PersonnelSpendItem) =>
            item.campaign_name || item.campaign_id,
        },
      ]
    : []),
  ...(level.value === 'ad'
    ? [
        {
          align: 'center' as const,
          key: 'ad_set_name',
          title: '所属广告组',
          width: 220,
          value: (item: PersonnelSpendItem) =>
            item.ad_set_name || item.ad_set_id,
        },
      ]
    : []),
  ...(level.value === 'project' || isEntityLevel.value
    ? DRILL_METRICS.map(({ key, title, width }) => ({
        align: 'center' as const,
        dataIndex: key,
        key,
        title,
        width,
        value: (item: PersonnelSpendItem) => item[key],
        format: (item: PersonnelSpendItem) => formatMetric(item[key]),
      }))
    : []),
  ...(level.value === 'account' ? [] : spendColumns.value),
  ...(visibleDetailColumns.value.length > 0
    ? visibleDetailColumns.value.map((column) => ({
        key: column.key,
        title: column.title,
        align: 'center' as const,
        width: 110,
        drillLevel: column.level,
        value: (item: PersonnelSpendItem) => item[column.key],
      }))
    : [
        {
          key: 'record_count',
          title: '广告日记录数',
          align: 'center' as const,
          width: 130,
          value: (item: PersonnelSpendItem) => item.record_count,
        },
      ]),
  ...(canDrill.value
    ? [
        {
          key: 'action',
          title: '查看明细',
          align: 'center' as const,
          width: 130,
        },
      ]
    : []),
]);
const sortableColumns = computed(() =>
  columns.value.filter((column) => column.value),
);
const sortedData = computed(() => {
  const column = columns.value.find((item) => item.key === sortKey.value);
  if (!column?.value) return data.value;
  const value = column.value;
  return [...data.value].sort((left, right) => {
    const a = value(left);
    const b = value(right);
    // 空金额保持排在最后，不能将缺失数据当作零参与排序。
    if (a === null || a === undefined)
      return b === null || b === undefined ? 0 : 1;
    if (b === null || b === undefined) return -1;
    const order =
      typeof a === 'number' && typeof b === 'number'
        ? a - b
        : String(a).localeCompare(String(b), 'zh-CN');
    return (
      (sortDescending.value ? -order : order) || left.id.localeCompare(right.id)
    );
  });
});
function changeSort(key: string) {
  sortDescending.value = sortKey.value === key ? !sortDescending.value : false;
  sortKey.value = key;
}
function cellText(column: PersonnelColumn, itemId: string) {
  const item = itemsById.value.get(itemId);
  if (!item) return '—';
  return column.format?.(item) ?? String(column.value?.(item) ?? '—');
}
function formatAccountCount(item: PersonnelSpendItem) {
  return `${item.account_count}(${item.account_unspent_count ?? '—'}/${item.account_spent_count ?? '—'})`;
}
function spendState(column: PersonnelColumn, itemId: string) {
  if (!column.key.startsWith('spend_')) return;
  const item = itemsById.value.get(itemId);
  if (!item) return;
  const amount = column.value?.(item);
  const hasSpend = item.spent_currencies
    ? item.spent_currencies.includes(column.key.slice('spend_'.length))
    : typeof amount === 'number' && amount > 0;
  return hasSpend ? 'spent' : 'unspent';
}
function spendClass(column: PersonnelColumn, itemId: string) {
  const state = spendState(column, itemId);
  if (!state) return '';
  return state === 'spent' ? 'text-emerald-700' : 'text-neutral-600';
}
function cellHint(column: PersonnelColumn, itemId: string) {
  if (column.key === 'account_count') {
    return '关联账户总数（未消耗/已消耗），按所选日期范围内的账户累计消耗统计';
  }
  const state = spendState(column, itemId);
  if (state === 'spent') return '已消耗';
  if (state === 'unspent') return '未消耗';
}
function canOpenDetails(column: PersonnelColumn, itemId: string) {
  const item = itemsById.value.get(itemId);
  const count = item && column.value?.(item);
  return typeof count === 'number' && count > 0;
}
const canDrill = computed(() => Boolean(nextLevel[level.value]));
const panelTitle = computed(
  () =>
    ({
      personnel: '人员消耗明细',
      account: '账户消耗明细',
      project: '项目消耗明细',
      campaign: '系列记录',
      adset: '广告组记录',
      ad: '广告记录',
    })[level.value],
);
const panelHint = computed(
  () =>
    ({
      personnel:
        '点击人员查看账户；点击明细数量可直接查看有消耗的系列、广告组或广告，数量按所选日期范围内的 ID 去重。',
      account: '点击账户，继续查看关联项目。',
      project: '点击项目，继续查看系列记录。',
      campaign:
        '展示所选日期内累计有消耗的系列；点击组明细或广告明细数量可直接查看。',
      adset: '展示所选日期内累计有消耗的广告组；点击广告组查看广告。',
      ad: '展示所选日期内累计有消耗的广告，同一广告跨日期合并为一条。',
    })[level.value],
);
const drillLabel = computed(
  () =>
    ({
      personnel: '查看账户',
      account: '查看项目',
      project: '查看系列',
      campaign: '查看广告组',
      adset: '查看广告',
      ad: '',
    })[level.value],
);
const parentLevel = computed(() => drillPath.value.at(-2)?.level);
const summaryCards = computed(() => [
  {
    title: '投放人员',
    value: summary.value?.personnel_count,
    hint: '当前筛选范围内的人员',
    icon: UsersRound,
  },
  {
    title: '关联账户',
    value: summary.value?.account_count,
    hint: '按账户 ID 去重',
    icon: CreditCard,
  },
  {
    title: '关联项目',
    value: summary.value?.project_count,
    hint: '按项目名称去重',
    icon: FolderOpen,
  },
]);
const scopeLabel = computed(
  () =>
    drill.value.adSetName ||
    drill.value.campaignName ||
    drill.value.gamePlatform ||
    (drill.value.accountId
      ? formatAccountId(drill.value.accountId)
      : drill.value.placerName) ||
    '全部人员',
);
const appliedDateLabel = computed(() =>
  appliedQuery.value.date.replace(',', ' — '),
);
const appliedDepartmentLabel = computed(
  () =>
    (appliedQuery.value.department || '')
      .split(',')
      .filter(Boolean)
      .map((value) => (value === '投放二组' ? 'MP投放部' : value))
      .join('、') || '全部部门',
);
const formatAccountId = (accountId: string) =>
  accountId.startsWith('act_') ? accountId : `act_${accountId}`;
const crumbs = computed(() => drillPath.value);

const dateParam = () =>
  `${dayjs(dateRange.value[0]).format('YYYY-MM-DD')},${dayjs(
    dateRange.value[1],
  ).format('YYYY-MM-DD')}`;

const dateRouteState = computed({
  get: dateParam,
  set(value: string) {
    const [start, end] = value.split(',');
    if (!start || !end) return;
    dateRange.value = [
      dayjs(start).valueOf(),
      dayjs(end).endOf('day').valueOf(),
    ];
  },
});
const accountAttributeRouteState = computed({
  get: () => filters.value.account_attribute,
  set: (value: string[]) => (filters.value.account_attribute = value),
});
const departmentRouteState = computed({
  get: () => filters.value.department,
  set: (value: string[]) => (filters.value.department = value),
});
const gamePlatformRouteState = computed({
  get: () => filters.value.game_platform,
  set: (value: string[]) => (filters.value.game_platform = value),
});
const placerRouteState = computed({
  get: () => filters.value.placer_id,
  set: (value: string[]) => (filters.value.placer_id = value),
});
const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    date: {
      always: true,
      codec: {
        parse(value) {
          const raw = Array.isArray(value) ? value[0] : value;
          if (!raw) return undefined;
          const [start, end] = raw.split(',');
          return start && end && dayjs(start).isValid() && dayjs(end).isValid()
            ? `${start},${end}`
            : undefined;
        },
        serialize: (value) => value,
      },
    },
    department: {
      // 默认部门非空；用空字符串区分“用户明确清空”和“URL 未提供”。
      codec: {
        parse(value) {
          const values = Array.isArray(value) ? value : [value];
          return values.flatMap((item) =>
            typeof item === 'string' ? item.split(',').filter(Boolean) : [],
          );
        },
        serialize: (value) => (value.length > 0 ? value : ''),
      },
    },
  },
  onRouteStateRestored: async () => {
    if (!routeStateReady.value) return;
    drillPath.value = [rootStep];
    applyFilters();
    await fetchPersonnelSpend(true);
  },
  state: createListRouteStateTarget({
    account_attribute: accountAttributeRouteState,
    date: dateRouteState,
    department: departmentRouteState,
    game_platform: gamePlatformRouteState,
    placer_id: placerRouteState,
  }),
});

function applyFilters() {
  appliedQuery.value = {
    date: dateParam(),
    ...Object.fromEntries(
      Object.entries(filters.value)
        .filter(([, values]) => values.length > 0)
        .map(([key, values]) => [key, values.join(',')]),
    ),
  };
}

function requestParams(includeSummary: boolean): PersonnelSpendQuery {
  return {
    ...appliedQuery.value,
    ...(drill.value.placerId ? { placer_id: drill.value.placerId } : {}),
    ...(drill.value.accountId ? { account_id: drill.value.accountId } : {}),
    ...(drill.value.campaignId ? { campaign_id: drill.value.campaignId } : {}),
    ...(drill.value.adSetId ? { ad_set_id: drill.value.adSetId } : {}),
    ...(drill.value.gamePlatform
      ? { game_platform: drill.value.gamePlatform }
      : {}),
    level: level.value,
    include_summary: includeSummary,
  };
}

async function fetchPersonnelSpend(includeSummary = false) {
  const sequence = ++requestSequence;
  loading.value = true;
  loadFailed.value = false;
  summaryLoading.value = includeSummary;
  data.value = [];
  total.value = 0;
  recordCount.value = 0;
  missingSpendCount.value = 0;
  sortKey.value = '';
  if (includeSummary) {
    summary.value = undefined;
    summaryUpdatedAt.value = null;
  }
  try {
    const result = await getPersonnelSpend(requestParams(includeSummary));
    // 快速修改日期时只接收最后一次结果，防止旧响应覆盖新筛选。
    if (sequence !== requestSequence) return;
    data.value = result.data || [];
    total.value = result.total || 0;
    recordCount.value = result.record_count || 0;
    missingSpendCount.value = result.missing_spend_count || 0;
    if (includeSummary) {
      summary.value = result.summary;
      summaryUpdatedAt.value = result.data_updated_at;
    }
  } catch {
    if (sequence !== requestSequence) return;
    loadFailed.value = true;
  } finally {
    if (sequence === requestSequence) {
      loading.value = false;
      summaryLoading.value = false;
    }
  }
}

async function loadFilterOptions() {
  filterOptionsLoading.value = true;
  try {
    filterOptions.value = await getFilterOptions({
      include_account_attributes: true,
    });
  } catch {
    message.error('筛选项加载失败，请稍后重试');
  } finally {
    filterOptionsLoading.value = false;
  }
}

async function handleDateUpdate(value: [number, number] | null) {
  if (!value) return;
  dateRange.value = value;
  await handleSearch();
}

async function handleSearch() {
  drillPath.value = [rootStep];
  applyFilters();
  await commitQueryState();
  await fetchPersonnelSpend(true);
}

async function resetFilters() {
  filters.value = emptyFilters();
  await handleSearch();
}

async function enterDrill(id: string, name: string) {
  if (loading.value) return;
  const target = nextLevel[level.value];
  if (!target) return;

  let context: DrillContext = { ...drill.value };
  switch (level.value) {
    case 'account': {
      context.accountId = id;
      break;
    }
    case 'adset': {
      context.adSetId = id;
      context.adSetName = name;
      break;
    }
    case 'campaign': {
      context.campaignId = id;
      context.campaignName = name;
      break;
    }
    case 'personnel': {
      context = { placerId: id, placerName: name };
      break;
    }
    case 'project': {
      context.gamePlatform = id;
      break;
    }
    default: {
      return;
    }
  }
  drillPath.value.push({
    context,
    label: level.value === 'account' ? formatAccountId(id) : name,
    level: target,
  });
  await fetchPersonnelSpend();
}

async function openDetails(id: string, target: PersonnelEntityLevel) {
  if (loading.value) return;
  const item = itemsById.value.get(id);
  const column = visibleDetailColumns.value.find(
    (entry) => entry.level === target,
  );
  if (!item || !column) return;
  const count = item[column.key];
  if (count === undefined || count <= 0) return;
  let context: DrillContext;
  if (level.value === 'personnel') {
    context = { placerId: id, placerName: item.name };
  } else if (level.value === 'campaign') {
    // 系列直达广告时保留人员和所有已执行筛选，并限定当前系列。
    context = { ...drill.value, campaignId: id, campaignName: item.name };
  } else {
    return;
  }
  drillPath.value.push({
    context,
    label: `${item.name} · ${column.title}`,
    level: target,
  });
  await fetchPersonnelSpend();
}

async function goToLevel(target: PersonnelSpendLevel) {
  if (loading.value || target === level.value) return;
  const index = drillPath.value.findIndex((step) => step.level === target);
  if (index < 0) return;
  drillPath.value = drillPath.value.slice(0, index + 1);
  await fetchPersonnelSpend();
}

function csvField(value: string) {
  return `"${value.replaceAll('"', '""')}"`;
}

function exportData() {
  if (data.value.length === 0) {
    message.warning('暂无可导出的数据');
    return;
  }
  // 导出复用表格列、币种顺序和当前排序，并保留名称下方展示的部门/对象 ID。
  const exportColumns: PersonnelColumn[] = [...sortableColumns.value];
  if (level.value === 'personnel')
    exportColumns.splice(1, 0, {
      key: 'department',
      title: '所属部门',
      value: (item) => item.department,
    });
  if (isEntityLevel.value)
    exportColumns.splice(1, 0, {
      key: 'id',
      title: `${levelLabels[level.value].replace('名称', '')} ID`,
      value: (item) => item.id,
    });
  const csv = [
    exportColumns.map((column) => csvField(column.title)).join(','),
    ...sortedData.value.map((item) =>
      exportColumns
        .map((column) => csvField(cellText(column, item.id)))
        .join(','),
    ),
  ].join('\n');
  const blob = new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${panelTitle.value}_${appliedQuery.value.date.replace(',', '_')}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  message.success(`已导出 ${data.value.length} 条数据`);
}

onMounted(async () => {
  await restoreFromRoute();
  applyFilters();
  routeStateReady.value = true;
  await Promise.all([loadFilterOptions(), fetchPersonnelSpend(true)]);
});
</script>

<template>
  <Page
    auto-content-height
    class="adpulse-section-page personnel-data-page bg-muted/40"
    content-class="p-0"
  >
    <!-- 留白随内容滚走，避免滚动容器的顶部内边距在吸顶区域上方露出表体。 -->
    <div ref="contentRef" class="flex min-w-0 flex-col gap-4 p-4">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <UsersRound class="text-primary size-6 shrink-0" aria-hidden="true" />
          <div>
            <h1 class="text-foreground m-0 text-xl font-semibold">人员数据</h1>
            <p class="text-muted-foreground mb-0 mt-1 text-sm">
              按人员查看消耗，逐级定位账户、项目、系列、广告组与广告
            </p>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-4">
          <span class="text-muted-foreground flex items-center gap-1 text-xs">
            <Clock3 class="size-3.5" aria-hidden="true" />
            最近采集 {{ summaryUpdatedAt || '—' }}
          </span>
          <Button
            class="flex items-center"
            :disabled="loading || data.length === 0"
            @click="exportData"
          >
            <template #icon>
              <IconifyIcon icon="lucide:download" aria-hidden="true" />
            </template>
            导出当前明细
          </Button>
        </div>
      </div>

      <Card class="border-border shadow-none" :body-style="{ padding: '16px' }">
        <h2 class="text-foreground mb-4 text-sm font-semibold">筛选条件</h2>
        <Form class="ux-filter-form" layout="vertical">
          <Form.Item class="ux-filter-search mb-0 w-full" label="日期">
            <DateRangePicker
              v-model:value="dateRange"
              format="yyyy-MM-dd"
              type="daterange"
              width="100%"
              @update:value="handleDateUpdate"
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="部门">
            <Select
              v-model:value="filters.department"
              allow-clear
              class="w-full"
              mode="multiple"
              option-filter-prop="label"
              placeholder="全部部门"
              show-search
              :loading="filterOptionsLoading"
              :options="departmentOptions"
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="投放人员">
            <Select
              v-model:value="filters.placer_id"
              allow-clear
              class="w-full"
              mode="multiple"
              option-filter-prop="label"
              placeholder="全部投放人员"
              show-search
              :loading="filterOptionsLoading"
              :options="placerOptions"
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="项目">
            <Select
              v-model:value="filters.game_platform"
              allow-clear
              class="w-full"
              mode="multiple"
              option-filter-prop="label"
              placeholder="全部项目"
              show-search
              :loading="filterOptionsLoading"
              :options="projectOptions"
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="账户类型">
            <Select
              v-model:value="filters.account_attribute"
              allow-clear
              aria-label="账户类型"
              class="w-full"
              mode="multiple"
              option-filter-prop="label"
              placeholder="全部账户类型"
              show-search
              :loading="filterOptionsLoading"
              :options="accountAttributeOptions"
            />
          </Form.Item>
          <div class="ux-filter-actions">
            <Button
              type="primary"
              :loading="summaryLoading"
              :disabled="loading"
              @click="handleSearch"
            >
              <Search class="mr-1 inline-block size-4" aria-hidden="true" />查询
            </Button>
            <Button :disabled="loading" @click="resetFilters"> 重置 </Button>
          </div>
        </Form>
      </Card>

      <div
        class="grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5"
        :aria-busy="summaryLoading"
      >
        <Card
          class="border-border shadow-none sm:col-span-2"
          :body-style="{ padding: '20px' }"
        >
          <div
            class="text-muted-foreground flex items-center justify-between text-sm"
          >
            <span>消耗汇总</span><Wallet class="size-4" aria-hidden="true" />
          </div>
          <div
            class="text-foreground my-3 flex min-h-9 flex-wrap items-baseline gap-x-6 gap-y-2 tabular-nums"
          >
            <p v-if="summaryLoading" class="text-muted-foreground m-0 text-sm">
              加载中…
            </p>
            <template v-else-if="summary?.spends.length">
              <span
                v-for="spend in summary.spends"
                :key="spend.currency"
                class="flex items-baseline gap-2"
              >
                <span class="text-muted-foreground text-xs">{{
                  spend.currency
                }}</span>
                <strong class="text-2xl font-semibold">{{
                  formatMetric(spend.amount)
                }}</strong>
              </span>
            </template>
            <strong v-else class="text-2xl font-semibold">—</strong>
          </div>
          <p class="text-muted-foreground mb-0 text-xs">
            按人员归属汇总，各币种分别统计
          </p>
        </Card>
        <Card
          v-for="card in summaryCards"
          :key="card.title"
          class="border-border shadow-none"
          :body-style="{ padding: '20px' }"
        >
          <div
            class="text-muted-foreground flex items-center justify-between text-sm"
          >
            <span>{{ card.title }}</span>
            <component :is="card.icon" class="size-4" aria-hidden="true" />
          </div>
          <div
            class="text-foreground my-3 flex min-h-9 items-baseline tabular-nums"
          >
            <p v-if="summaryLoading" class="text-muted-foreground m-0 text-sm">
              加载中…
            </p>
            <strong v-else class="text-2xl font-semibold">{{
              card.value ?? '—'
            }}</strong>
          </div>
          <p class="text-muted-foreground mb-0 text-xs">{{ card.hint }}</p>
        </Card>
      </div>

      <Card
        class="personnel-data-panel border-border shadow-none"
        :body-style="{ padding: 0 }"
      >
        <div
          ref="panelHeaderRef"
          class="personnel-panel-header bg-card sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3"
        >
          <div>
            <nav
              aria-label="人员数据下钻层级"
              class="flex flex-wrap items-center gap-1 text-sm"
            >
              <template v-for="(crumb, index) in crumbs" :key="crumb.level">
                <span v-if="index > 0" class="text-muted-foreground">/</span>
                <button
                  class="focus-visible:ring-ring rounded-sm p-0 text-left focus-visible:outline-none focus-visible:ring-2"
                  :class="
                    crumb.level === level
                      ? 'text-muted-foreground cursor-default'
                      : 'text-primary cursor-pointer hover:underline'
                  "
                  :disabled="loading || crumb.level === level"
                  type="button"
                  @click="goToLevel(crumb.level)"
                >
                  {{ crumb.label }}
                </button>
              </template>
            </nav>
            <div class="mt-2 flex items-center gap-2">
              <h2 class="text-foreground m-0 text-base font-semibold">
                {{ panelTitle }}
              </h2>
              <Tag class="m-0">{{ total }} 条</Tag>
            </div>
            <p class="text-muted-foreground mb-0 mt-1 text-xs">
              {{ panelHint }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <div class="text-muted-foreground text-right text-xs">
              <div>{{ appliedDateLabel }}</div>
              <div class="mt-1">{{ appliedDepartmentLabel }}</div>
            </div>
            <Button
              v-if="parentLevel"
              :disabled="loading"
              @click="goToLevel(parentLevel)"
            >
              <ArrowLeft
                class="mr-1 inline-block size-4"
                aria-hidden="true"
              />返回上一级
            </Button>
          </div>
        </div>

        <AntDataTable
          class="personnel-data-table"
          :columns="columns"
          :data="sortedData"
          :loading="loading"
          :paginate="false"
          :scroll="{ x: 'max-content' }"
          :sticky="tableSticky"
          empty-text="当前筛选条件下暂无人员消耗数据"
          row-key="id"
        >
          <template
            v-for="column in sortableColumns"
            :key="`header-${column.key}`"
            #[`header-${column.key}`]
          >
            <button
              type="button"
              class="focus-visible:ring-ring flex w-full items-center gap-2 rounded-sm focus-visible:outline-none focus-visible:ring-2"
              :class="
                column.align === 'left'
                  ? 'justify-start text-left'
                  : 'justify-center text-center'
              "
              :aria-label="`${column.title}，${sortKey === column.key ? (sortDescending ? '当前降序' : '当前升序') : '未排序'}，点击排序`"
              :disabled="loading"
              @click="changeSort(column.key)"
            >
              <span class="whitespace-nowrap">{{ column.title }}</span>
              <component
                :is="sortDescending ? ArrowDown : ArrowUp"
                v-if="sortKey === column.key"
                class="text-muted-foreground size-3 shrink-0"
                aria-hidden="true"
              />
            </button>
          </template>
          <template #cell-name="{ record }">
            <button
              class="focus-visible:ring-ring rounded-sm p-0 text-left focus-visible:outline-none focus-visible:ring-2"
              :class="
                canDrill
                  ? 'ux-table-link cursor-pointer'
                  : 'text-foreground cursor-default'
              "
              :disabled="loading || !canDrill"
              type="button"
              @click="enterDrill(record.id, record.name)"
            >
              {{ record.name }}
            </button>
            <div
              v-if="level === 'personnel'"
              class="text-muted-foreground mt-1 text-xs"
            >
              {{ record.department || '—' }}
            </div>
            <div
              v-if="isEntityLevel"
              class="text-muted-foreground mt-1 text-xs"
            >
              {{ record.id }}
            </div>
          </template>
          <template
            v-for="column in sortableColumns.filter(
              (item) => item.key !== 'name',
            )"
            :key="column.key"
            #[`cell-${column.key}`]="{ record }"
          >
            <Button
              v-if="column.drillLevel"
              type="link"
              class="px-0 tabular-nums"
              :aria-label="`查看${record.name}的${column.title}`"
              :disabled="loading || !canOpenDetails(column, record.id)"
              @click="openDetails(record.id, column.drillLevel)"
            >
              {{ cellText(column, record.id) }}
            </Button>
            <div
              v-else
              class="tabular-nums"
              :class="[
                column.key.startsWith('spend_')
                  ? 'whitespace-nowrap font-semibold'
                  : '',
                spendClass(column, record.id),
              ]"
              :title="cellHint(column, record.id)"
            >
              {{ cellText(column, record.id) }}
            </div>
          </template>
          <template #cell-action="{ record }">
            <Button
              type="link"
              class="px-0"
              :disabled="loading"
              @click="enterDrill(record.id, record.name)"
            >
              {{ drillLabel
              }}<ChevronRight
                class="ml-1 inline-block size-3"
                aria-hidden="true"
              />
            </Button>
          </template>
          <template #empty>
            <div
              class="text-muted-foreground flex flex-col items-center gap-3 py-10"
            >
              <span>{{
                loadFailed
                  ? '人员消耗数据加载失败，请重试'
                  : '当前筛选条件下暂无人员消耗数据'
              }}</span>
              <Button
                v-if="loadFailed"
                @click="fetchPersonnelSpend(level === 'personnel' && !summary)"
              >
                重新加载
              </Button>
            </div>
          </template>
        </AntDataTable>
        <div
          class="text-muted-foreground flex flex-wrap justify-between gap-2 border-t px-4 py-3 text-xs"
        >
          <div
            title="广告日记录数按天累计，不等同于按 ID 去重的系列、组或广告数量"
          >
            当前范围：{{ scopeLabel }} · {{ recordCount }} 条广告日记录
          </div>
          <div>{{ spendNote }}</div>
        </div>
      </Card>
    </div>
  </Page>
</template>

<style scoped>
/* 解除卡片和表格外层的滚动裁剪，让吸顶相对 Page 内容区生效；横向滚动仍由表体承接。 */
.personnel-data-panel {
  overflow: visible;
}

.personnel-panel-header {
  border-start-start-radius: var(--adpulse-radius);
  border-start-end-radius: var(--adpulse-radius);
}
</style>
