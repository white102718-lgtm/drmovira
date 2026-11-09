<script setup lang="ts">
import type { VxeGridProps } from '#/adapter/vxe-table';

import { computed, h, nextTick, onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Alert, Button, Form, Input, Modal, Select, Tag } from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  exportMaterialBoard,
  getMaterialAds,
  getMaterialBoardList,
} from '#/api/dashboard/material-statistics';
import { useMaterialFilterOptions } from '#/composables/useMaterialFilterOptions';
import { useListRouteState } from '#/composables/use-list-route-state';
import facebookCountries from '#/data/facebook_countries.json';
import DateRangePicker from '#/views/components/DateRangePicker.vue';
import OverflowTooltip from '#/views/components/OverflowTooltip.vue';

// 表格需展示历史素材国家，可能不在当前项目的公共筛选候选项中。
const countryNameMap = Object.fromEntries(
  (facebookCountries as { code: string; name: string }[]).map((c) => [
    c.code,
    c.name,
  ]),
);

function isNil(value: unknown): value is null | undefined {
  return value === null || value === undefined;
}

// ==================== 筛选 ====================
const today = dayjs().format('YYYY-MM-DD');
const todayRange: [number, number] = [
  dayjs().startOf('day').valueOf(),
  dayjs().endOf('day').valueOf(),
];

const filters = reactive({
  spend_start: today,
  spend_end: today,
  submit_start: '',
  submit_end: '',
  project: undefined as string | undefined,
  department: undefined as string | undefined,
  designers: [] as string[],
  filetype: '',
  country: undefined as string | undefined,
  basenames: '',
});

const dateRange = ref<[number, number] | null>(todayRange);
const submittedDateRange = ref<[number, number] | null>(null);

function onDateChange(v: [number, number] | null) {
  dateRange.value = v;
  filters.spend_start = v ? dayjs(v[0]).format('YYYY-MM-DD') : '';
  filters.spend_end = v ? dayjs(v[1]).format('YYYY-MM-DD') : '';
}

function onSubmittedDateChange(v: [number, number] | null) {
  submittedDateRange.value = v;
  filters.submit_start = v ? dayjs(v[0]).format('YYYY-MM-DD') : '';
  filters.submit_end = v ? dayjs(v[1]).format('YYYY-MM-DD') : '';
}

// ==================== 选项数据 ====================
const { filterOptions, optionsError, optionsLoading, reloadOptions } =
  useMaterialFilterOptions();
const projectOptions = computed(() =>
  (filterOptions.value?.projects ?? []).map((name) => ({
    label: name,
    value: name,
  })),
);
// 素材历史按姓名查询；公共接口的 value 是用户 ID，不能直接传给 designers。
const designerOptions = computed(() =>
  [
    ...new Set(
      (filterOptions.value?.designers ?? []).map((item) => item.label),
    ),
  ].map((name) => ({ label: name, value: name })),
);
const countryOptions = computed(
  () =>
    filterOptions.value?.region_options ??
    (filterOptions.value?.regions ?? []).map((code) => ({
      label: code,
      value: code,
    })),
);
const deptFilterOptions = computed(
  () =>
    filterOptions.value?.department_options ??
    (filterOptions.value?.departments ?? []).map((name) => ({
      label: name,
      value: name,
    })),
);

const demandTypeOptions = [
  { label: '全部', value: '' },
  { label: '视频', value: 'video' },
  { label: '图片', value: 'image' },
];

// ==================== 预览 ====================
const previewState = reactive({
  visible: false,
  url: '',
  filetype: '',
  name: '',
});

function openPreview(row: any) {
  if (!row.media) return;
  previewState.visible = true;
  previewState.url = row.media;
  previewState.filetype = row.filetype ?? '';
  previewState.name = row.basename ?? '';
}

// ==================== 关联广告内嵌表格 ====================
const adsOpenRow = ref<any>(null);
const adsCurrentPage = ref(1);
const adsPageSize = ref(20);

const adsGridOptions = reactive<VxeGridProps>({
  border: false,
  height: 600,
  treeConfig: { childrenField: 'daily' },
  cellConfig: { height: 52 },
  columns: [
    {
      field: 'ad_name',
      title: '广告名称',
      fixed: 'left',
      treeNode: true,
      minWidth: 120,
      slots: {
        default: ({ row, $table }: any) => {
          const name =
            row.ad_name ?? $table.getTreeParentRow(row)?.ad_name ?? '';
          return [h(OverflowTooltip, { text: name })];
        },
      },
    },
    {
      field: 'ad_id',
      title: '广告ID',
      fixed: 'left',
      width: 180,
      slots: {
        default: ({ row, $table }: any) => [
          row.ad_id ?? $table.getTreeParentRow(row)?.ad_id ?? '',
        ],
      },
    },
    {
      field: 'spend_start',
      title: '开始日期',
      width: 110,
      slots: {
        default: ({ row }: any) => [
          isNil(row.ad_id) ? (row.date ?? '') : (row.spend_start ?? ''),
        ],
      },
    },
    {
      field: 'spend_end',
      title: '结束日期',
      width: 110,
      slots: {
        default: ({ row }: any) => [
          isNil(row.ad_id) ? (row.date ?? '') : (row.spend_end ?? ''),
        ],
      },
    },
    { field: 'spend', title: '消耗', width: 80 },
    { field: 'impressions', title: '展示数', width: 85 },
    { field: 'cpm', title: '千展($)', width: 80 },
    { field: 'clicks', title: '点击数', width: 75 },
    {
      field: 'ctr',
      title: '点击率',
      width: 80,
      slots: {
        default: ({ row }: any) => [isNil(row.ctr) ? '—' : `${row.ctr}%`],
      },
    },
    { field: 'cpa', title: 'CPA($)', width: 80 },
    { field: 'subscriptions', title: '订阅数', width: 80 },
    {
      field: 'subscribe_rate',
      title: '订阅率',
      width: 80,
      slots: {
        default: ({ row }: any) => [
          isNil(row.subscribe_rate) ? '—' : `${row.subscribe_rate}%`,
        ],
      },
    },
    { field: 'subscribe_cost', title: '订阅成本', width: 90 },
    { field: 'subscribe_value', title: '订阅价值', width: 90 },
    { field: 'purchases', title: '购物数', width: 80 },
    {
      field: 'purchase_rate',
      title: '购物率',
      width: 80,
      slots: {
        default: ({ row }: any) => [
          isNil(row.purchase_rate) ? '—' : `${row.purchase_rate}%`,
        ],
      },
    },
    { field: 'purchase_cost', title: '购物成本', width: 90 },
    { field: 'purchase_value', title: '购物价值', width: 90 },
    {
      field: 'campaign_id',
      title: '广告系列ID',
      width: 180,
      slots: {
        default: ({ row, $table }: any) => [
          row.campaign_id ?? $table.getTreeParentRow(row)?.campaign_id ?? '',
        ],
      },
    },
    {
      field: 'ad_set_id',
      title: '广告组ID',
      width: 180,
      slots: {
        default: ({ row, $table }: any) => [
          row.ad_set_id ?? $table.getTreeParentRow(row)?.ad_set_id ?? '',
        ],
      },
    },
    {
      field: 'material_id',
      title: '素材ID',
      width: 140,
      slots: {
        default: ({ row, $table }: any) => {
          const id =
            row.material_id ?? $table.getTreeParentRow(row)?.material_id ?? '';
          return [
            h(OverflowTooltip, {
              text: id,
              'overlay-style': { maxWidth: '320px' },
            }),
          ];
        },
      },
    },
  ],
  data: [],
  pagerConfig: {
    enabled: true,
    currentPage: 1,
    pageSize: 20,
    total: 0,
  },
  headerCellStyle: () => ({ backgroundColor: 'hsl(var(--muted))' }),
  rowStyle: ({ row }: any) =>
    isNil(row.ad_id) ? { backgroundColor: 'hsl(var(--muted))' } : null,
});

const [AdsGrid, adsGridApi] = useVbenVxeGrid({
  gridClass: 'p-0',
  gridEvents: {
    pageChange({ currentPage: cp, pageSize: ps }: any) {
      adsCurrentPage.value = cp;
      adsPageSize.value = ps;
      fetchAds(cp, ps);
    },
  },
  gridOptions: adsGridOptions,
});

const adsModalOpened = ref(false);

// 修正 vxe-table 内部滚动同步缓存：只有在 Modal 动画结束
async function fixAdsGridScroll() {
  if (!adsModalOpened.value) return;
  await nextTick();
  await adsGridApi.grid?.recalculate(true);
  await adsGridApi.grid?.scrollTo(1, 0);
  await adsGridApi.grid?.scrollTo(0, 0);
}

async function fetchAds(page: number, ps: number) {
  adsCurrentPage.value = page;
  adsPageSize.value = ps;
  adsGridApi.setLoading(true);
  try {
    const res = await getMaterialAds({
      basename: adsOpenRow.value.basename,
      project: filters.project || undefined,
      // 项目名称同时约束素材归属和 Doris 广告成效，与列表、导出保持一致。
      game_platform: filters.project || undefined,
      spend_start: filters.spend_start || undefined,
      spend_end: filters.spend_end || undefined,
      page,
      page_size: ps,
    });
    adsGridApi.setGridOptions({
      data: res?.list ?? [],
      pagerConfig: { currentPage: page, pageSize: ps, total: res?.total ?? 0 },
    });

    await fixAdsGridScroll();
  } finally {
    adsGridApi.setLoading(false);
  }
}

function openAdsModal(row: any) {
  adsOpenRow.value = row;
  fetchAds(1, adsPageSize.value);
}

function onAdsModalAfterOpenChange(open: boolean) {
  adsModalOpened.value = open;
  if (open) {
    fixAdsGridScroll();
  }
}

// ==================== 表格 ====================
const currentPage = ref(1);
const pageSize = ref(50);
const sortState = reactive({ sort_by: 'spend', order: 'desc' });
const total = ref(0);
const spendTotal = ref(0);
const allSpendTotal = ref(0);
const currentPageRows = ref<any[]>([]);

const pagerSpendSlot = {
  left: () => [
    h(
      'span',
      { class: 'text-muted-foreground mt-1 text-xs' },
      `总消耗：${allSpendTotal.value}`,
    ),
  ],
};

function makeSortHeader(field: string, title: string) {
  return {
    header: () => {
      const isAsc = sortState.sort_by === field && sortState.order === 'asc';
      const isDesc = sortState.sort_by === field && sortState.order === 'desc';
      function handleSortClick() {
        if (sortState.sort_by === field) {
          sortState.order = sortState.order === 'desc' ? 'asc' : 'desc';
        } else {
          sortState.sort_by = field;
          sortState.order = 'desc';
        }
        currentPage.value = 1;
        loadData(false);
      }
      return [
        h(
          'button',
          {
            class:
              'flex w-full cursor-pointer items-center justify-end gap-1 border-0 bg-transparent p-0 text-inherit whitespace-nowrap select-none',
            onClick: handleSortClick,
            type: 'button',
          },
          [
            h('span', title),
            h('span', { class: 'flex flex-col' }, [
              h('i', {
                class: `icon-[ant-design--caret-up-filled] text-sm ${isAsc ? 'text-foreground' : 'text-muted-foreground/50'}`,
              }),
              h('i', {
                class: `icon-[ant-design--caret-down-filled] -mt-1 text-sm ${isDesc ? 'text-foreground' : 'text-muted-foreground/50'}`,
              }),
            ]),
          ],
        ),
      ];
    },
  };
}

const gridOptions = reactive<VxeGridProps>({
  border: false,
  height: '100%',
  sortConfig: { remote: true },
  columns: [
    {
      field: 'basename',
      minWidth: 150,
      fixed: 'left',
      title: '名称',
      slots: {
        default: ({ row }: any) => [
          h('div', { class: 'flex items-center justify-between min-w-0' }, [
            row.img
              ? h(
                  'button',
                  {
                    'aria-label': `预览素材 ${row.basename ?? ''}`,
                    class:
                      'group relative flex-shrink-0 cursor-pointer overflow-hidden rounded border-0 bg-transparent p-0',
                    style: 'width:60px;height:60px',
                    onClick: () => openPreview(row),
                    type: 'button',
                  },
                  [
                    h('img', {
                      src: `data:image/jpeg;base64,${row.img}`,
                      style: 'width:100%;height:100%;object-fit:contain',
                    }),
                    row.filetype === 'video'
                      ? h(
                          'div',
                          {
                            class:
                              'pointer-events-none absolute inset-0 flex items-center justify-center',
                          },
                          [
                            h('span', {
                              class:
                                'icon-[ant-design--play-circle-filled] text-2xl text-white opacity-80',
                            }),
                          ],
                        )
                      : null,
                    h(
                      'div',
                      {
                        class:
                          'absolute inset-0 flex items-center justify-center bg-black bg-opacity-50 opacity-0 transition-opacity group-hover:opacity-100',
                      },
                      [
                        h('span', {
                          class:
                            'icon-[ant-design--eye-outlined] text-xl text-white',
                        }),
                      ],
                    ),
                  ],
                )
              : null,
            h(
              'span',
              { class: 'truncate text-sm', title: row.basename },
              row.basename ?? '',
            ),
          ]),
        ],
      },
    },
    {
      field: 'create_time',
      width: 110,
      title: '上传日期',
      slots: {
        default: ({ row }: any) => [row.create_time?.slice(0, 10) ?? ''],
      },
    },
    {
      field: 'delivery_start',
      width: 110,
      title: '开始日期',
      slots: {
        default: ({ row }: any) => [row.delivery_start?.slice(0, 10) ?? ''],
      },
    },
    { field: 'delivery_cutoff', width: 130, title: '结束日期' },
    { field: 'designer', minWidth: 90, align: 'center', title: '素材师' },
    {
      field: 'filetype',
      width: 80,
      align: 'center',
      title: '类型',
      slots: {
        default: ({ row }: any) => {
          const color = row.filetype === 'image' ? 'blue' : 'purple';
          let label = row.filetype ?? '';
          if (row.filetype === 'image') label = '图片';
          if (row.filetype === 'video') label = '视频';
          return [h(Tag, { color }, () => label)];
        },
      },
    },
    // ==================== 关联广告列 ====================
    {
      field: 'ads_count',
      width: 80,
      align: 'center',
      title: '关联广告',
      slots: {
        default: ({ row }: any) => {
          const count: number = row.ads_count ?? 0;
          if (!count) return [h('span', { class: 'text-foreground' }, '0')];
          return [
            h(
              'button',
              {
                'aria-label': `查看关联广告 ${count} 条`,
                class:
                  'text-primary cursor-pointer border-0 bg-transparent p-0 underline underline-offset-4',
                onClick: () => openAdsModal(row),
                type: 'button',
              },
              count,
            ),
          ];
        },
      },
    },
    {
      field: 'spend',
      width: 100,
      align: 'right',
      title: '消耗',
      slots: makeSortHeader('spend', '消耗'),
    },
    {
      field: 'reach',
      width: 110,
      align: 'right',
      title: '覆盖人数',
      slots: makeSortHeader('reach', '覆盖人数'),
    },
    {
      field: 'impressions',
      width: 110,
      align: 'right',
      title: '展示次数',
      slots: makeSortHeader('impressions', '展示次数'),
    },
    {
      field: 'frequency',
      width: 90,
      align: 'right',
      title: '频次',
      slots: makeSortHeader('frequency', '频次'),
    },
    {
      field: 'cpm',
      width: 190,
      align: 'right',
      title: 'CPM（千次展示费用）',
      slots: makeSortHeader('cpm', 'CPM（千次展示费用）'),
    },
    {
      field: 'clicks',
      width: 140,
      align: 'right',
      title: '点击量（全部）',
      slots: makeSortHeader('clicks', '点击量（全部）'),
    },
    {
      field: 'ctr',
      width: 165,
      align: 'right',
      title: '点击率（全部）(%)',
      slots: makeSortHeader('ctr', '点击率（全部）(%)'),
    },
    {
      field: 'cpc',
      width: 180,
      align: 'right',
      title: '单次点击费用（全部）',
      slots: makeSortHeader('cpc', '单次点击费用（全部）'),
    },
    {
      field: 'link_clicks',
      width: 120,
      align: 'right',
      title: '链接点击量',
      slots: makeSortHeader('link_clicks', '链接点击量'),
    },
    {
      field: 'link_ctr',
      width: 140,
      align: 'right',
      title: '链接点击率(%)',
      slots: makeSortHeader('link_ctr', '链接点击率(%)'),
    },
    {
      field: 'link_cpc',
      width: 160,
      align: 'right',
      title: '单次链接点击费用',
      slots: makeSortHeader('link_cpc', '单次链接点击费用'),
    },
    {
      field: 'purchases',
      width: 110,
      align: 'right',
      title: '购物次数',
      slots: makeSortHeader('purchases', '购物次数'),
    },
    {
      field: 'purchase_cost',
      width: 140,
      align: 'right',
      title: '单次购物费用',
      slots: makeSortHeader('purchase_cost', '单次购物费用'),
    },
    {
      field: 'purchase_value',
      width: 140,
      align: 'right',
      title: '购物转化价值',
      slots: makeSortHeader('purchase_value', '购物转化价值'),
    },
    {
      field: 'cvr',
      width: 100,
      align: 'right',
      title: 'CVR(%)',
      slots: makeSortHeader('cvr', 'CVR(%)'),
    },
    {
      field: 'ir',
      width: 100,
      align: 'right',
      title: 'IR(%)',
      slots: makeSortHeader('ir', 'IR(%)'),
    },
    {
      field: 'registrations',
      width: 100,
      align: 'right',
      title: '注册数',
      slots: makeSortHeader('registrations', '注册数'),
    },
    {
      field: 'country',
      width: 90,
      title: '投放地区',
      slots: {
        default: ({ row }: any) => [
          countryNameMap[row.country] ?? row.country ?? '',
        ],
      },
    },
    { field: 'department', minWidth: 100, align: 'center', title: '部门' },
    { field: 'creator', minWidth: 90, align: 'center', title: '需求方' },
    { field: 'project', minWidth: 120, title: '项目' },
    {
      field: 'product_info',
      align: 'center',
      width: 170,
      title: '官方台子名',
      slots: {
        default: ({ row }: any) => [
          h(OverflowTooltip, { text: row.product_info ?? '' }),
        ],
      },
    },
  ],
  data: [],
  headerCellStyle: () => ({ backgroundColor: 'hsl(var(--muted))' }),
  pagerConfig: {
    currentPage: 1,
    enabled: true,
    pageSize: 50,
    pageSizes: [50, 100, 200],
    total: 0,
    slots: pagerSpendSlot,
  },
  cellConfig: { height: 52 },
  showFooter: true,
  footerMethod: ({ columns }: any) => {
    if (total.value === 0) return [];
    const map: Record<string, number | string> = {
      basename: '页总计',
      spend: spendTotal.value,
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
      loadData(false);
    },
  },
  gridOptions,
});

const routeState = reactive({
  get basenames() {
    return filters.basenames;
  },
  set basenames(value: string) {
    filters.basenames = value;
  },
  get country() {
    return filters.country;
  },
  set country(value: string | undefined) {
    filters.country = value;
  },
  get department() {
    return filters.department;
  },
  set department(value: string | undefined) {
    filters.department = value;
  },
  get designers() {
    return filters.designers;
  },
  set designers(value: string[]) {
    filters.designers = value;
  },
  get filetype() {
    return filters.filetype;
  },
  set filetype(value: string) {
    filters.filetype = value;
  },
  get order() {
    return sortState.order;
  },
  set order(value: string) {
    sortState.order = value;
  },
  get project() {
    return filters.project;
  },
  set project(value: string | undefined) {
    filters.project = value;
  },
  get sort_by() {
    return sortState.sort_by;
  },
  set sort_by(value: string) {
    sortState.sort_by = value;
  },
  get spend_end() {
    return filters.spend_end;
  },
  set spend_end(value: string) {
    filters.spend_end = value;
  },
  get spend_start() {
    return filters.spend_start;
  },
  set spend_start(value: string) {
    filters.spend_start = value;
  },
  get submit_end() {
    return filters.submit_end;
  },
  set submit_end(value: string) {
    filters.submit_end = value;
  },
  get submit_start() {
    return filters.submit_start;
  },
  set submit_start(value: string) {
    filters.submit_start = value;
  },
});

function syncRestoredControls() {
  gridApi.setGridOptions({
    pagerConfig: {
      currentPage: currentPage.value,
      pageSize: pageSize.value,
      total: total.value,
    },
  });
  dateRange.value =
    filters.spend_start && filters.spend_end
      ? [
          dayjs(filters.spend_start).startOf('day').valueOf(),
          dayjs(filters.spend_end).endOf('day').valueOf(),
        ]
      : null;
  submittedDateRange.value =
    filters.submit_start && filters.submit_end
      ? [
          dayjs(filters.submit_start).startOf('day').valueOf(),
          dayjs(filters.submit_end).endOf('day').valueOf(),
        ]
      : null;
}

const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    onRouteStateRestored: async () => {
      syncRestoredControls();
      await loadData(true);
    },
    pagination: {
      defaultPageSize: 50,
      page: currentPage,
      pageSize,
      pageSizes: [50, 100, 200],
    },
    state: routeState,
  });

// ==================== 数据加载 ====================
async function loadData(withTotal = false) {
  await commitQueryState();
  gridApi.setLoading(true);
  try {
    const params = {
      ...buildFilterParams(),
      page: currentPage.value,
      page_size: pageSize.value,
      ...(withTotal && { with_total: true }),
    };
    const res = await getMaterialBoardList(params);
    const items: any[] = res?.list ?? res?.items ?? [];
    currentPageRows.value = items;
    total.value = res?.total ?? 0;
    spendTotal.value = Number.parseFloat(
      items
        .reduce((sum: number, row: any) => sum + (Number(row.spend) || 0), 0)
        .toFixed(2),
    );
    if (withTotal) {
      allSpendTotal.value = res?.spend_total ?? 0;
    }
    gridApi.setGridOptions({
      data: items,
      pagerConfig: {
        currentPage: currentPage.value,
        pageSize: pageSize.value,
        total: res?.total ?? 0,
        slots: pagerSpendSlot,
      },
    });
    await nextTick();
    setTimeout(() => gridApi.grid?.scrollTo(0, 0), 0);
  } finally {
    gridApi.setLoading(false);
  }
}

function buildFilterParams() {
  // 列表与导出共用排序，导出结果保持当前看板的指标顺序。
  const params: Record<string, any> = {
    sort_by: sortState.sort_by,
    order: sortState.order,
  };
  if (filters.spend_start) params.spend_start = filters.spend_start;
  if (filters.spend_end) params.spend_end = filters.spend_end;
  if (filters.submit_start) params.submit_start = filters.submit_start;
  if (filters.submit_end) params.submit_end = filters.submit_end;
  if (filters.project) {
    params.project = filters.project;
    params.game_platform = filters.project;
  }
  if (filters.department) params.department = filters.department;
  if (filters.designers.length > 0) params.designers = filters.designers;
  if (filters.filetype) params.demand_type = filters.filetype;
  if (filters.country) params.country = filters.country;
  if (filters.basenames) params.basenames = filters.basenames;
  return params;
}

const exportLoading = ref(false);

function handleSearch() {
  currentPage.value = 1;
  loadData(true);
}

async function handleExport() {
  exportLoading.value = true;
  try {
    const res = await exportMaterialBoard(buildFilterParams());
    if (res?.content && res?.filename) {
      const mime =
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      const blob = await fetch(`data:${mime};base64,${res.content}`).then((r) =>
        r.blob(),
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = res.filename;
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }
  } finally {
    exportLoading.value = false;
  }
}

async function resetFilters() {
  await resetQueryState();
  syncRestoredControls();
  await loadData(true);
}

onMounted(async () => {
  await restoreFromRoute();
  syncRestoredControls();
  await loadData(true);
});
</script>

<template>
  <Page
    class="material-board-page bg-muted/40 flex h-full min-h-0 flex-col"
    content-class="!h-auto min-h-0 flex-1 overflow-hidden p-4 max-md:overflow-y-auto"
    description="按素材、人员和投放时间查看素材表现与使用情况。"
    title="素材看板"
  >
    <div
      class="flex h-full min-w-0 flex-col gap-4 overflow-hidden max-md:h-auto max-md:overflow-visible"
    >
      <Alert
        v-if="optionsError"
        type="error"
        show-icon
        message="筛选项加载失败，请重新加载。"
      >
        <template #action>
          <Button :loading="optionsLoading" @click="reloadOptions">
            重新加载
          </Button>
        </template>
      </Alert>
      <!-- 筛选栏 -->
      <div class="border-border bg-card flex-shrink-0 rounded-lg border p-4">
        <Form class="ux-filter-form" layout="vertical">
          <Form.Item class="ux-filter-search mb-0 w-full" label="素材">
            <Input
              v-model:value="filters.basenames"
              allow-clear
              placeholder="素材名，逗号分隔"
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="上传">
            <DateRangePicker
              :value="submittedDateRange"
              :clearable="true"
              type="daterange"
              width="100%"
              format="yyyy-MM-dd"
              @update:value="onSubmittedDateChange"
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="投放">
            <DateRangePicker
              :value="dateRange"
              :clearable="false"
              type="daterange"
              width="100%"
              format="yyyy-MM-dd"
              @update:value="onDateChange"
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="素材师">
            <Select
              v-model:value="filters.designers"
              class="w-full"
              :loading="optionsLoading"
              mode="multiple"
              :options="designerOptions"
              option-filter-prop="label"
              placeholder="请搜索"
              show-search
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="类型">
            <Select
              v-model:value="filters.filetype"
              class="w-full"
              :options="demandTypeOptions"
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="投放地区">
            <Select
              v-model:value="filters.country"
              allow-clear
              class="w-full"
              :loading="optionsLoading"
              :options="countryOptions"
              option-filter-prop="label"
              placeholder="请搜索"
              show-search
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="部门">
            <Select
              v-model:value="filters.department"
              allow-clear
              class="w-full"
              :loading="optionsLoading"
              :options="deptFilterOptions"
              option-filter-prop="label"
              placeholder="请搜索"
              show-search
            />
          </Form.Item>
          <Form.Item class="ux-filter-search mb-0 w-full" label="项目">
            <Select
              v-model:value="filters.project"
              allow-clear
              class="w-full"
              :loading="optionsLoading"
              :options="projectOptions"
              option-filter-prop="label"
              placeholder="请搜索"
              show-search
            />
          </Form.Item>
          <div class="ux-filter-actions">
            <Button type="primary" @click="handleSearch">搜索</Button>
            <Button @click="resetFilters">重置</Button>
          </div>
        </Form>
      </div>

      <!-- 表格 -->
      <div
        class="border-border bg-card flex min-h-0 min-w-0 flex-1 flex-col rounded-lg border p-4 max-md:flex-none"
      >
        <div class="mb-3 flex flex-shrink-0 items-center justify-between">
          <span class="text-foreground text-sm font-semibold">素材明细</span>
          <Button type="primary" :loading="exportLoading" @click="handleExport">
            导出
          </Button>
        </div>
        <div
          class="ux-fill-grid-host min-h-0 min-w-0 flex-1 overflow-hidden max-md:h-[var(--adpulse-table-viewport-height)] max-md:flex-none"
        >
          <Grid class="h-full" />
        </div>
      </div>

      <!-- 预览弹窗 -->
      <Modal
        v-model:open="previewState.visible"
        :title="previewState.name"
        :footer="null"
        destroy-on-close
      >
        <div class="flex justify-center">
          <video
            v-if="previewState.filetype === 'video'"
            :src="previewState.url"
            controls
            autoplay
            style="width: 100%; max-height: 68vh"
          ></video>
          <img
            v-else
            alt="素材预览"
            :src="previewState.url"
            style="
              width: auto;
              max-width: 100%;
              max-height: 68vh;
              object-fit: contain;
            "
          />
        </div>
      </Modal>

      <!-- 关联广告弹窗 -->
      <Modal
        :open="!!adsOpenRow"
        :width="1400"
        :footer="null"
        destroy-on-close
        @cancel="adsOpenRow = null"
        @after-open-change="onAdsModalAfterOpenChange"
      >
        <template #title>
          <div class="flex items-center gap-2">
            <span>关联广告 ——— {{ adsOpenRow?.basename ?? '' }}</span>
            <Button
              class="flex items-center justify-center"
              type="text"
              @click="fetchAds(adsCurrentPage, adsPageSize)"
            >
              <span class="icon-[lucide--refresh-cw]"></span>
            </Button>
          </div>
        </template>
        <AdsGrid v-if="!!adsOpenRow" />
      </Modal>
    </div>
  </Page>
</template>

<style>
.material-board-page .vxe-table--render-default .vxe-row-group-cell,
.material-board-page .vxe-table--render-default .vxe-tree-cell {
  padding-left: 0 !important;
}
</style>
