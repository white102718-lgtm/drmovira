<script setup lang="ts">
import type { VxeGridProps } from '#/adapter/vxe-table';

import { h, onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import Button from 'ant-design-vue/es/button';
import dayjs from 'dayjs';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getAdgenPersonnelConsumptionApi,
  type AdgenPersonnelConsumptionItem,
} from '#/api/adgen-operations';
import { useListRouteState } from '#/composables/use-list-route-state';
import DateRangePicker from '#/views/components/DateRangePicker.vue';
import FilterDropdown from '#/views/components/FilterDropdown.vue';

// ==================== 筛选 ====================
const _defaultStart = dayjs().subtract(6, 'day').startOf('day');
const _defaultEnd = dayjs().endOf('day');
const filters = reactive({
  user_id: '',
  start_date: _defaultStart.format('YYYY-MM-DD'),
  end_date: _defaultEnd.format('YYYY-MM-DD'),
  department: '',
});
const dateRange = ref<[number, number] | null>([
  _defaultStart.valueOf(),
  _defaultEnd.valueOf(),
]);
const creatorOptions = ref<{ label: string; value: string }[]>([]);
const creatorLoading = ref(false);
const departmentOptions = ref<{ label: string; value: string }[]>([]);
const departmentLoading = ref(false);

function onDateChange(v: [number, number] | null) {
  dateRange.value = v;
  filters.start_date = v ? dayjs(v[0]).format('YYYY-MM-DD') : '';
  filters.end_date = v ? dayjs(v[1]).format('YYYY-MM-DD') : '';
}

type PersonnelConsumptionCurrency = 'CNY' | 'USD';

type PersonnelConsumptionRow = AdgenPersonnelConsumptionItem & {
  total: number;
};

function normalizePersonnelItem(
  item: AdgenPersonnelConsumptionItem,
  currency: PersonnelConsumptionCurrency,
): PersonnelConsumptionRow {
  return {
    ...item,
    total:
      currency === 'CNY'
        ? (item.total_cny ?? 0)
        : (item.total_usd ?? item.amount),
  };
}

function formatAmount(value: number) {
  return Number(value ?? 0).toLocaleString('zh-CN', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

// ==================== 表格 ====================
const currentPage = ref(1);
const pageSize = ref(20);
const total = ref(0);
const callsTotal = ref(0);
const inputTokensTotal = ref(0);
const outputTokensTotal = ref(0);
const totalCny = ref(0);
const totalUsd = ref(0);
const order = ref<'asc' | 'desc'>('desc');
const totalCurrency = ref<PersonnelConsumptionCurrency>('CNY');

function totalTitle() {
  return totalCurrency.value === 'CNY' ? '总额（¥）' : '总额（US$）';
}

function createTotalHeader() {
  const isAscending = order.value === 'asc';
  return [
    h(
      'div',
      { class: 'flex w-full items-center justify-start gap-1' },
      [
        h(
          'button',
          {
            class:
              'cursor-pointer border-0 bg-transparent p-0 text-inherit transition-colors hover:text-primary',
            title:
              totalCurrency.value === 'CNY'
                ? '点击切换为美元总额'
                : '点击切换为人民币总额',
            type: 'button',
            onClick: (event: MouseEvent) => {
              event.stopPropagation();
              toggleTotalCurrency();
            },
          },
          totalTitle(),
        ),
        h(
          'button',
          {
            class:
              'inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded border-0 bg-transparent p-0 text-inherit transition-colors hover:bg-gray-100 hover:text-primary',
            title: isAscending
              ? '当前升序，点击改为降序'
              : '当前降序，点击改为升序',
            type: 'button',
            onClick: (event: MouseEvent) => {
              event.stopPropagation();
              toggleOrder();
            },
          },
          h(IconifyIcon, {
            class: 'h-3.5 w-3.5',
            icon: isAscending ? 'lucide:arrow-up' : 'lucide:arrow-down',
          }),
        ),
      ],
    ),
  ];
}

function createPersonnelColumns(): VxeGridProps<PersonnelConsumptionRow>['columns'] {
  return [
    {
      field: 'user_id',
      minWidth: 150,
      title: '用户 ID',
      slots: { default: ({ row }: any) => [row.user_id || '-'] },
    },
    { field: 'name', minWidth: 120, title: '人员' },
    {
      field: 'department',
      minWidth: 120,
      title: '部门',
      slots: { default: ({ row }: any) => [row.department || '-'] },
    },
    {
      field: 'calls',
      minWidth: 140,
      title: '调用次数',
      slots: {
        default: ({ row }: any) => [
          row.calls === undefined || row.calls === null
            ? '-'
            : Number(row.calls).toLocaleString(),
        ],
      },
    },
    {
      field: 'input_tokens',
      minWidth: 140,
      title: '输入 Token',
      slots: {
        default: ({ row }: any) => [
          Number(row.input_tokens ?? 0).toLocaleString(),
        ],
      },
    },
    {
      field: 'output_tokens',
      minWidth: 140,
      title: '输出 Token',
      slots: {
        default: ({ row }: any) => [
          Number(row.output_tokens ?? 0).toLocaleString(),
        ],
      },
    },
    {
      field: 'total',
      minWidth: 150,
      title: totalTitle(),
      slots: {
        header: createTotalHeader,
        default: ({ row }: any) => [formatAmount(row.total)],
      },
    },
  ];
}

const gridOptions = reactive<VxeGridProps<PersonnelConsumptionRow>>({
  align: 'left',
  border: false,
  height: '100%',
  footerAlign: 'left',
  headerAlign: 'left',
  columns: createPersonnelColumns(),
  data: [],
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  pagerConfig: {
    currentPage: 1,
    enabled: true,
    pageSize: 20,
    pageSizes: [20, 50, 100],
    total: 0,
  },
  cellConfig: { height: 52 },
  showFooter: true,
  footerMethod: ({ columns }: any) => {
    if (total.value === 0) return [];
    const map: Record<string, string | number> = {
      name: '总计',
      calls: callsTotal.value.toLocaleString(),
      input_tokens: inputTokensTotal.value.toLocaleString(),
      output_tokens: outputTokensTotal.value.toLocaleString(),
      total: formatAmount(
        totalCurrency.value === 'CNY' ? totalCny.value : totalUsd.value,
      ),
    };
    return [columns.map((col: any) => map[col.field] ?? '')];
  },
});

const [Grid, gridApi] = useVbenVxeGrid({
  gridClass: 'p-0',
  gridEvents: {
    pageChange({ currentPage: cp, pageSize: ps }: any) {
      currentPage.value = cp;
      pageSize.value = ps;
      loadData();
    },
  },
  gridOptions,
  tableTitle: '人员消耗汇总',
});

const routeState = reactive({
  get currency() {
    return totalCurrency.value;
  },
  set currency(value: PersonnelConsumptionCurrency) {
    totalCurrency.value = value;
  },
  get department() {
    return filters.department;
  },
  set department(value: string) {
    filters.department = value;
  },
  get end_date() {
    return filters.end_date;
  },
  set end_date(value: string) {
    filters.end_date = value;
  },
  get order() {
    return order.value;
  },
  set order(value: 'asc' | 'desc') {
    order.value = value;
  },
  get start_date() {
    return filters.start_date;
  },
  set start_date(value: string) {
    filters.start_date = value;
  },
  get user_id() {
    return filters.user_id;
  },
  set user_id(value: string) {
    filters.user_id = value;
  },
});

function syncRestoredControls() {
  gridApi.setGridOptions({
    columns: createPersonnelColumns(),
    pagerConfig: {
      currentPage: currentPage.value,
      pageSize: pageSize.value,
      total: total.value,
    },
  });
  dateRange.value =
    filters.start_date && filters.end_date
      ? [
          dayjs(filters.start_date).startOf('day').valueOf(),
          dayjs(filters.end_date).endOf('day').valueOf(),
        ]
      : null;
}

const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    onRouteStateRestored: async () => {
      syncRestoredControls();
      await loadData();
    },
    pagination: {
      defaultPageSize: 20,
      page: currentPage,
      pageSize,
      pageSizes: [20, 50, 100],
    },
    state: routeState,
  });

// ==================== 数据加载 ====================
async function loadData() {
  await commitQueryState();
  gridApi.setLoading(true);
  creatorLoading.value = true;
  departmentLoading.value = true;
  try {
    const params = {
      currency: totalCurrency.value,
      order: order.value,
      page: currentPage.value,
      page_size: pageSize.value,
      start_date: filters.start_date,
      end_date: filters.end_date,
      user_id: filters.user_id || undefined,
      department: filters.department || undefined,
    };
    const res = await getAdgenPersonnelConsumptionApi(params);
    const items: PersonnelConsumptionRow[] = (res.list ?? []).map(
      (item) => normalizePersonnelItem(item, totalCurrency.value),
    );
    creatorOptions.value = res.people ?? [];
    departmentOptions.value = (res.departments ?? []).map((name) => ({
      label: name,
      value: name,
    }));
    total.value = res.total ?? 0;
    callsTotal.value =
      res.calls_total ??
      items.reduce((sum, item) => sum + Number(item.calls || 0), 0);
    inputTokensTotal.value =
      res.input_tokens_total ??
      items.reduce((sum, item) => sum + Number(item.input_tokens || 0), 0);
    outputTokensTotal.value =
      res.output_tokens_total ??
      items.reduce((sum, item) => sum + Number(item.output_tokens || 0), 0);
    totalUsd.value = res.total_usd ?? res.spend_total ?? 0;
    totalCny.value = res.total_cny ?? 0;
    gridApi.setGridOptions({
      data: items,
      pagerConfig: {
        currentPage: currentPage.value,
        pageSize: pageSize.value,
        total: res.total ?? 0,
      },
    });
  } finally {
    creatorLoading.value = false;
    departmentLoading.value = false;
    gridApi.setLoading(false);
  }
}

function toggleOrder() {
  order.value = order.value === 'asc' ? 'desc' : 'asc';
  currentPage.value = 1;
  gridApi.setGridOptions({ columns: createPersonnelColumns() });
  loadData();
}

function toggleTotalCurrency() {
  totalCurrency.value = totalCurrency.value === 'CNY' ? 'USD' : 'CNY';
  currentPage.value = 1;
  gridApi.setGridOptions({ columns: createPersonnelColumns() });
  loadData();
}

function handleSearch() {
  currentPage.value = 1;
  loadData();
}

async function resetFilters() {
  await resetQueryState();
  syncRestoredControls();
  await loadData();
}

onMounted(async () => {
  await restoreFromRoute();
  syncRestoredControls();
  await loadData();
});
</script>

<template>
  <Page
    class="flex h-full min-h-0 flex-col bg-gray-50"
    content-class="!h-auto min-h-0 flex flex-1 flex-col overflow-hidden"
    description="按人员汇总所选日期范围内的调用与 Token；总额默认按人民币展示，可切换美元并排序。"
    title="人员消耗排行"
  >
    <div class="flex h-full min-h-0 min-w-0 flex-col gap-4">
      <!-- 筛选栏 -->
      <div class="flex-shrink-0 rounded-md border border-gray-100 bg-white p-4">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-sm text-gray-400">筛选</span>

          <FilterDropdown
            label="人员"
            :model-value="filters.user_id"
            :options="creatorOptions"
            :loading="creatorLoading"
            placeholder="请搜索"
            empty-text="无匹配人员"
            @update:model-value="(v: any) => (filters.user_id = v || '')"
          />

          <FilterDropdown
            label="部门"
            :model-value="filters.department"
            :options="departmentOptions"
            :loading="departmentLoading"
            placeholder="请搜索"
            empty-text="无匹配部门"
            @update:model-value="(v: any) => (filters.department = v || '')"
          />

          <!-- 日期范围 -->
          <DateRangePicker
            :value="dateRange"
            :clearable="false"
            type="daterange"
            width="260px"
            format="yyyy/MM/dd"
            @update:value="onDateChange"
          />

          <Button type="primary" @click="handleSearch">搜索</Button>
          <Button @click="resetFilters">重置</Button>
        </div>
      </div>

      <!-- 表格 -->
      <div class="ux-fill-grid-host min-h-0 flex-1 rounded-xl bg-white p-4">
        <Grid class="h-full" />
      </div>
    </div>
  </Page>
</template>
