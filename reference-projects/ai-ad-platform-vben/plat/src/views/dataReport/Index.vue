<script setup lang="ts">
import type { VxeGridProps } from '#/adapter/vxe-table';
import type { FilterTemplate } from '#/api/dashboard';

import { computed, h, onMounted, onUnmounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { EchartsUI, useEcharts } from '@vben/plugins/echarts';
import { getPopupContainer } from '@vben/utils';

import {
  DatePicker,
  Dropdown,
  Input,
  message,
  Popconfirm,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import FilterDropdown from '#/views/components/FilterDropdown.vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import type { AlertAction, AlertFeedResult, AlertItem } from '#/api/dashboard';

import {
  applyFilterTemplate,
  createFilterTemplate,
  deleteFilterTemplate,
  doAlertAction,
  getAlertFeed,
  getChannelOverview,
  getIntradayTrend,
  getPlacerLeaderboard,
  getPlacerOverview,
  getProjectOverview,
  getSpendSummary,
  listFilterTemplates,
} from '#/api/dashboard';

import type { FilterOptions } from '#/api/dashboard';
import { getFilterOptions } from '#/api/dashboard';

import facebookCountries from '#/data/facebook_countries.json';

import AnimatedCount from '../components/AnimatedCount.vue';
import BaseButton from '../components/BaseButton.vue';
import SectionHeader from './components/SectionHeader.vue';

const _countryMap = new Map(
  (facebookCountries as Array<{ code: string; name: string }>).map((c) => [
    c.code,
    c.name,
  ]),
);

const router = useRouter();
const route = useRoute();

// ==================== 筛选 ====================
const filters = reactive<{
  date: string;
  game_platform: string;
  placer: string;
  region: string;
  channel: string;
  department: string[];
}>({
  date: '',
  game_platform: '',
  placer: '',
  region: '',
  channel: '',
  department: [],
});

const dateOpen = ref(false);

function dateFooter() {
  return h('div', { class: 'ant-picker-footer-custom-btns' }, [
    h(
      'button',
      {
        onClick: () => {
          filters.date = dayjs().format('YYYY-MM-DD');
          dateOpen.value = false;
        },
      },
      '今天',
    ),
    h(
      'button',
      {
        onClick: () => {
          filters.date = dayjs().subtract(1, 'day').format('YYYY-MM-DD');
          dateOpen.value = false;
        },
      },
      '昨天',
    ),
  ]);
}

function filterVal(s: string): string | undefined {
  return s || undefined;
}

/** 多选筛选 → 接口值; 空数组视为不筛选 (axios paramsSerializer:'comma' 会自动逗号拼接) */
function filterArr(a: string[]): string[] | undefined {
  return a.length ? a : undefined;
}

function setDate(v: string | unknown) {
  filters.date = typeof v === 'string' ? v : '';
}

// 筛选项 ↔ URL query
function syncFiltersToUrl() {
  router.replace({
    query: {
      ...(filters.date ? { date: filters.date } : {}),
      ...(filters.game_platform
        ? { game_platform: filters.game_platform }
        : {}),
      ...(filters.region ? { region: filters.region } : {}),
      ...(filters.placer ? { placer: filters.placer } : {}),
      ...(filters.channel ? { channel: filters.channel } : {}),
      ...(filters.department.length ? { department: filters.department } : {}),
    },
  });
}

/** 从 URL 还原筛选 */
function readFiltersFromUrl(): boolean {
  const pick = (k: string): string =>
    typeof route.query[k] === 'string' ? (route.query[k] as string) : '';
  const pickArr = (k: string): string[] => {
    const v = route.query[k];
    if (Array.isArray(v))
      return v.filter((x): x is string => typeof x === 'string');
    return typeof v === 'string' ? [v] : [];
  };
  const date = pick('date');
  const gp = pick('game_platform');
  const region = pick('region');
  const placer = pick('placer');
  const channel = pick('channel');
  const department = pickArr('department');
  if (!date && !gp && !region && !placer && !channel && !department.length)
    return false;
  filters.date = date;
  filters.game_platform = gp;
  filters.region = region;
  filters.placer = placer;
  filters.channel = channel;
  filters.department = department;
  return true;
}

// ==================== 下拉选项 ====================
const projectOptions = ref<Array<{ label: string; value: string }>>([]);
const placerOptions = ref<Array<{ label: string; value: string }>>([]);
const regionOptions = ref<Array<{ label: string; value: string }>>([]);
const channelOptions = ref<Array<{ label: string; value: string }>>([]);
const departmentOptions = ref<Array<{ label: string; value: string }>>([]);
const filterOptionsLoading = ref(true);

// ==================== 颜色/格式化辅助 ====================
const PALETTE = [
  '#6366f1',
  '#f59e0b',
  '#22c55e',
  '#8b5cf6',
  '#ef4444',
  '#06b6d4',
  '#ec4899',
  '#14b8a6',
];

function colorFor(key: string): string {
  let hash = 0;
  for (let i = 0; i < (key || '').length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return PALETTE[hash % PALETTE.length]!;
}

function money(n: any, decimals = 0): string {
  if (n == null || n === '') return '-';
  return `$${Number(n).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

function num(n: any): string {
  if (n == null || n === '') return '-';
  return Number(n).toLocaleString('en-US');
}

/** 金额缩略: $xx万 / $xx千 (用于图表标签) */
function abbrMoney(v: any): string {
  const n = Number(v) || 0;
  const a = Math.abs(n);
  if (a >= 10_000) return `$${(n / 10_000).toFixed(a >= 1_000_000 ? 0 : 1)}万`;
  if (a >= 1000) return `$${(n / 1000).toFixed(1)}千`;
  return `$${n}`;
}

/** 后端环比字段形如 "+12.3%" / "-5.0%" / null → 数值 */
function parsePct(s: any): number {
  if (s == null) return 0;
  const n = Number.parseFloat(String(s).replace('%', ''));
  return Number.isNaN(n) ? 0 : n;
}

function getRoasColor(roas: number): string {
  if (roas >= 1.5) return '#22c55e';
  if (roas >= 1) return '#f59e0b';
  return '#ef4444';
}

function getVsColor(vs: number): string {
  if (vs > 0) return '#22c55e';
  if (vs < 0) return '#ef4444';
  return '#9ca3af';
}

/** 后端原样字符串环比 ("+x%"/"-x%"/"—") 的着色 */
function getVsColorStr(s: string): string {
  if (!s || s === '—') return '#9ca3af';
  if (s.startsWith('-')) return '#ef4444';
  if (s.startsWith('+')) return '#22c55e';
  return '#9ca3af';
}

function formatVs(vs: number): string {
  if (vs === 0) return '—';
  return `${vs > 0 ? '▲' : '▼'}${Math.abs(vs)}%`;
}

function getBlockRateColor(rate: number): string {
  if (rate < 5) return '#22c55e';
  if (rate < 15) return '#f59e0b';
  return '#ef4444';
}

// ==================== 行映射 (后端中文字段 → 表格行) ====================
function mapProjectRow(r: Record<string, any>) {
  return {
    name: r['项目'],
    subtitle: `${r['地区'] ?? '—'}·${r['投手数量'] ?? 0}位投手`,
    spend: Number(r['消耗']) || 0,
    roas: Number(r.roas ?? 0),
    cpa: Number(r.cpa ?? 0),
    registrations: Number(r['注册']) || 0,
    paymentCost: Number(r['付费成本']) || 0,
    subscriptionCost: Number(r['订阅成本']) || 0,
    vs7d: parsePct(r['vs7日']),
  };
}

function mapPlacerRow(r: Record<string, any>) {
  return {
    name: r['投手'],
    avatarColor: colorFor(r.real_name || r['投手'] || ''),
    subtitle: `${r['组'] ?? '—'}·${r['在投代理线'] ?? 0}条在投代理线`,
    spend: Number(r['消耗']) || 0,
    roas: Number(r.ROAS ?? 0),
    cpi: Number(r.CPI) || 0,
    paymentCost: Number(r['付费成本']) || 0,
    subscriptionCost: Number(r['订阅成本']) || 0,
  };
}

function mapTeamRow(r: Record<string, any>) {
  const rank = Number(r['排名']) || 0;
  return {
    rank,
    color: PALETTE[(rank - 1 + PALETTE.length) % PALETTE.length],
    name: r['组'],
    group: '',
    spend: Number(r['消耗']) || 0,
    vs: r['同比上月'] ?? '—',
    vsNum: parsePct(r['同比上月']),
  };
}

function mapChannelRow(r: Record<string, any>) {
  return {
    name: r['渠道商'],
    subtitle: `${r['账户数'] ?? 0}个账户`,
    spend: r['总消耗'],
    clients: r['账户数'],
    blocked: r['封户数'],
    blockRate: parsePct(r['封户率']),
    vs7d: parsePct(r['VS7日']),
  };
}

// ==================== VxeGrid: 项目维度 ====================
const REPORT_GRID_HEIGHTS = {
  large: 520,
  medium: 480,
  small: 460,
  xlarge: 560,
  xsmall: 440,
} as const;

function getReportGridHeight() {
  if (typeof document === 'undefined') return REPORT_GRID_HEIGHTS.medium;
  const scale = document.documentElement.dataset.uiScale;
  return REPORT_GRID_HEIGHTS[scale as keyof typeof REPORT_GRID_HEIGHTS] ?? 480;
}

const projectTotal = ref<{ registrations: number; spend: number }>({
  registrations: 0,
  spend: 0,
});

const projectGridOptions: VxeGridProps = {
  border: false,
  height: getReportGridHeight(),
  toolbarConfig: { enabled: false },
  showFooter: true,
  sortConfig: { trigger: 'cell', remote: false },
  pagerConfig: { enabled: false },
  cellConfig: { height: 52 },
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  cellStyle: () => ({ fontSize: '0.875rem' }),
  proxyConfig: {
    autoLoad: false, // 首屏统一在 onMounted 里决定查询时机(等模板应用后), 避免空筛选先查一次
    response: { result: 'items', total: 'total' },
    ajax: {
      query: async () => {
        projectTotal.value = { spend: 0, registrations: 0 };
        const res = await getProjectOverview({
          page_size: 1000,
          date: filterVal(filters.date),
          game_platform: filterVal(filters.game_platform),
          region: filterVal(filters.region),
          placer: filterVal(filters.placer),
          channel: filterVal(filters.channel),
          department: filterArr(filters.department),
        });
        const rows = res?.data ?? [];
        projectTotal.value = {
          spend: rows.reduce((s, r) => s + (Number(r['消耗']) || 0), 0),
          registrations: rows.reduce((s, r) => s + (Number(r['注册']) || 0), 0),
        };
        return rows
          .map(mapProjectRow)
          .filter((row: ReturnType<typeof mapProjectRow>) => row.name != null);
      },
    },
  },
  columns: [
    {
      title: '项目',
      field: 'name',
      minWidth: 180,
      align: 'left',
      slots: {
        default: ({ row }: any) => [
          h('div', { class: 'py-1' }, [
            h('div', { class: 'font-medium text-gray-900' }, row.name),
            h('div', { class: 'text-xs text-gray-400 mt-0.5' }, row.subtitle),
          ]),
        ],
      },
    },
    {
      title: '消耗',
      field: 'spend',
      minWidth: 100,
      sortable: true,
      slots: { default: ({ row }: any) => [h('span', money(row.spend, 2))] },
    },
    {
      title: 'ROAS',
      field: 'roas',
      minWidth: 80,
      sortable: true,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { style: { color: getRoasColor(row.roas) } },
            `${row.roas}`,
          ),
        ],
      },
    },
    {
      title: 'CPA',
      field: 'cpa',
      minWidth: 90,
      sortable: true,
      slots: {
        default: ({ row }: any) => [h('span', `$${row.cpa.toFixed(2)}`)],
      },
    },
    {
      title: '注册',
      field: 'registrations',
      minWidth: 90,
      sortable: true,
      slots: { default: ({ row }: any) => [h('span', num(row.registrations))] },
    },
    {
      title: '付费成本',
      field: 'paymentCost',
      minWidth: 90,
      sortable: true,
      slots: {
        default: ({ row }: any) => [h('span', money(row.paymentCost, 2))],
      },
    },
    {
      title: '订阅成本',
      field: 'subscriptionCost',
      minWidth: 90,
      sortable: true,
      slots: {
        default: ({ row }: any) => [h('span', money(row.subscriptionCost, 2))],
      },
    },
    {
      title: 'VS 7日',
      field: 'vs7d',
      minWidth: 90,
      sortable: true,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { style: { color: getVsColor(row.vs7d) } },
            formatVs(row.vs7d),
          ),
        ],
      },
    },
  ],
  footerMethod: ({ columns }: any) => {
    const t = projectTotal.value;
    const map: Record<string, string> = {
      name: '总计',
      spend: money(t.spend, 2),
      registrations: num(t.registrations),
    };
    return [columns.map((col: any) => map[col.field] ?? '')];
  },
};

const [ProjectGrid, projectGridApi] = useVbenVxeGrid({
  gridOptions: projectGridOptions,
  gridClass: 'p-0',
  class: 'report-dimension-grid',
});

// ==================== VxeGrid: 投手维度 ====================
const placerGridOptions: VxeGridProps = {
  border: false,
  height: getReportGridHeight(),
  toolbarConfig: { enabled: false },
  sortConfig: { trigger: 'cell', remote: false },
  pagerConfig: { enabled: false },
  cellConfig: { height: 52 },
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  cellStyle: () => ({ fontSize: '0.875rem' }),
  proxyConfig: {
    autoLoad: false, // 首屏统一在 onMounted 里决定查询时机(等模板应用后), 避免空筛选先查一次
    response: { result: 'items', total: 'total' },
    ajax: {
      query: async () => {
        const res = await getPlacerOverview({
          page_size: 1000,
          date: filterVal(filters.date),
          game_platform: filterVal(filters.game_platform),
          region: filterVal(filters.region),
          placer: filterVal(filters.placer),
          channel: filterVal(filters.channel),
          department: filterArr(filters.department),
        });
        const rows = res?.data ?? [];
        return rows.map(mapPlacerRow);
      },
    },
  },
  columns: [
    {
      title: '投手',
      field: 'name',
      minWidth: 180,
      align: 'left',
      slots: {
        default: ({ row }: any) => [
          h('div', { class: 'flex items-center gap-2 py-1' }, [
            h(
              'div',
              {
                class:
                  'w-8 h-8 rounded-full flex items-center justify-center text-white font-bold flex-shrink-0',
                style: { backgroundColor: row.avatarColor },
              },
              (row.name || '?').charAt(0),
            ),
            h('div', [
              h('div', { class: 'font-medium text-gray-900' }, row.name),
              h('div', { class: 'text-xs text-gray-400' }, row.subtitle),
            ]),
          ]),
        ],
      },
    },
    {
      title: '消耗',
      field: 'spend',
      minWidth: 100,
      sortable: true,
      slots: { default: ({ row }: any) => [h('span', money(row.spend, 2))] },
    },
    {
      title: 'ROAS',
      field: 'roas',
      minWidth: 80,
      sortable: true,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { style: { color: getRoasColor(row.roas) } },
            `${row.roas}`,
          ),
        ],
      },
    },
    {
      title: 'CPI',
      field: 'cpi',
      minWidth: 80,
      sortable: true,
      slots: { default: ({ row }: any) => [h('span', money(row.cpi, 2))] },
    },
    {
      title: '付费成本',
      field: 'paymentCost',
      minWidth: 90,
      sortable: true,
      slots: {
        default: ({ row }: any) => [h('span', money(row.paymentCost, 2))],
      },
    },
    {
      title: '订阅成本',
      field: 'subscriptionCost',
      minWidth: 90,
      sortable: true,
      slots: {
        default: ({ row }: any) => [h('span', money(row.subscriptionCost, 2))],
      },
    },
  ],
};

const [PlacerGrid, placerGridApi] = useVbenVxeGrid({
  gridOptions: placerGridOptions,
  gridClass: 'p-0',
  class: 'report-dimension-grid',
});

// ==================== VxeGrid: 团队排行榜 (本月消耗) ====================
const teamRankGridOptions: VxeGridProps = {
  border: false,
  height: getReportGridHeight(),
  toolbarConfig: { enabled: false },
  sortConfig: { trigger: 'cell', remote: false },
  pagerConfig: { enabled: false },
  cellConfig: { height: 52, keyField: 'rank' },
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  cellStyle: () => ({ fontSize: '0.875rem' }),
  proxyConfig: {
    autoLoad: false, // 首屏统一在 onMounted 里决定查询时机(等模板应用后), 避免空筛选先查一次
    response: { result: 'items', total: 'total' },
    ajax: {
      query: async () => {
        const res = await getPlacerLeaderboard({
          group_by: 'department',
          page_size: 1000,
          date: filterVal(filters.date),
          game_platform: filterVal(filters.game_platform),
          region: filterVal(filters.region),
          placer: filterVal(filters.placer),
          channel: filterVal(filters.channel),
          department: filterArr(filters.department),
        });
        const rows = res?.data ?? [];
        return rows.map(mapTeamRow);
      },
    },
  },
  columns: [
    {
      title: '排名',
      field: 'rank',
      width: 52,
      align: 'center',
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            {
              class: 'text-xl font-black',
              style: { color: row.rank === 1 ? '#facc15' : '#6b7280' },
            },
            String(row.rank),
          ),
        ],
      },
    },
    {
      title: '组别',
      field: 'group',
      minWidth: 120,
      slots: {
        default: ({ row }: any) => [
          h('div', { class: 'flex items-center gap-2 py-1' }, [
            h(
              'div',
              {
                class:
                  'w-8 h-8 rounded-full flex items-center justify-center text-white font-bold flex-shrink-0',
                style: { backgroundColor: row.color },
              },
              (row.name || '?').charAt(0),
            ),
            h('div', [
              h('div', { class: 'font-medium text-gray-900' }, row.name),
              h('div', { class: 'text-xs text-gray-400 mt-0.5' }, row.group),
            ]),
          ]),
        ],
      },
    },
    {
      title: '本月消耗',
      field: 'spend',
      minWidth: 120,
      sortable: true,
      slots: {
        default: ({ row }: any) => [
          h('span', { class: 'font-bold text-gray-900' }, money(row.spend, 2)),
        ],
      },
    },
    {
      title: '同比上月',
      field: 'vsNum',
      minWidth: 100,
      sortable: true,
      slots: {
        default: ({ row }: any) => [
          h('span', { style: { color: getVsColorStr(row.vs) } }, row.vs),
        ],
      },
    },
  ],
};

const [TeamRankGrid, teamRankGridApi] = useVbenVxeGrid({
  gridOptions: teamRankGridOptions,
  gridClass: 'p-0',
  class: 'report-dimension-grid',
});

// ==================== VxeGrid: 渠道商维度 ====================
const channelTotal = ref<Record<string, any>>({});

const channelGridOptions: VxeGridProps = {
  border: false,
  height: getReportGridHeight(),
  toolbarConfig: { enabled: false },
  showFooter: true,
  sortConfig: { trigger: 'cell', remote: false },
  pagerConfig: { enabled: false },
  cellConfig: { height: 52 },
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  cellStyle: () => ({ fontSize: '0.875rem' }),
  proxyConfig: {
    autoLoad: false,
    response: { result: 'items', total: 'total' },
    ajax: {
      query: async () => {
        channelTotal.value = {};
        const res = await getChannelOverview({
          page_size: 1000,
          date: filterVal(filters.date),
          game_platform: filterVal(filters.game_platform),
          region: filterVal(filters.region),
          placer: filterVal(filters.placer),
          channel: filterVal(filters.channel),
          department: filterArr(filters.department),
        });
        const rows = res?.data ?? [];
        channelTotal.value = res?.total_row ?? {};
        const mapped = rows.map(mapChannelRow);
        return mapped;
      },
    },
  },
  columns: [
    {
      title: '渠道商',
      field: 'name',
      minWidth: 160,
      align: 'left',
      slots: {
        default: ({ row }: any) => [
          h('div', { class: 'flex items-center gap-2 py-1' }, [
            h('div', [
              h('div', { class: 'font-medium text-gray-900' }, row.name),
              h('div', { class: 'text-xs text-gray-400' }, row.subtitle),
            ]),
          ]),
        ],
      },
    },
    {
      title: '总消耗',
      field: 'spend',
      minWidth: 110,
      sortable: true,
      slots: { default: ({ row }: any) => [h('span', money(row.spend, 2))] },
    },
    {
      title: '账户数',
      field: 'clients',
      minWidth: 90,
      sortable: true,
      slots: { default: ({ row }: any) => [h('span', row.clients)] },
    },
    {
      title: '封户数',
      field: 'blocked',
      minWidth: 90,
      sortable: true,
      slots: {
        default: ({ row }: any) => {
          const color =
            row.blocked === 0
              ? '#22c55e'
              : row.blockRate >= 15
                ? '#ef4444'
                : '#f59e0b';
          return [h('span', { style: { color } }, row.blocked)];
        },
      },
    },
    {
      title: '封户率',
      field: 'blockRate',
      minWidth: 90,
      sortable: true,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { style: { color: getBlockRateColor(row.blockRate) } },
            `${row.blockRate}%`,
          ),
        ],
      },
    },
    {
      title: 'VS 7日',
      field: 'vs7d',
      minWidth: 100,
      sortable: true,
      slots: {
        default: ({ row }: any) => [
          h(
            'span',
            { style: { color: getVsColor(row.vs7d) } },
            formatVs(row.vs7d),
          ),
        ],
      },
    },
  ],
  footerMethod: ({ columns }: any) => {
    const t = channelTotal.value;
    const map: Record<string, string> = {
      name: '总计',
      spend: money(t['总消耗'], 2),
      clients: num(t['账户数']),
      blocked: num(t['封户数']),
    };
    return [columns.map((col: any) => map[col.field] ?? '')];
  },
};

const [ChannelGrid, channelGridApi] = useVbenVxeGrid({
  gridOptions: channelGridOptions,
  gridClass: 'p-0',
  class: 'report-dimension-grid',
});

function syncReportGridHeights() {
  const height = getReportGridHeight();
  for (const gridApi of [
    projectGridApi,
    placerGridApi,
    teamRankGridApi,
    channelGridApi,
  ]) {
    gridApi.setGridOptions({ height });
  }
}

// ==================== ECharts: hero + 分时趋势 ====================
const heroChartRef = ref();
const trendChartRef = ref();

const trendModes = [
  { label: '24时', period: '24h' },
  { label: '7日', period: '7d' },
  { label: '30日', period: '30d' },
];
const trendMode = ref(trendModes[0]!);
const summary = ref({
  今日总消耗: 0,
  昨日: 0,
  环比昨日: null as null | string,
  本月: 0,
  消耗趋势: [] as Array<{ date: string; 消耗: number }>,
  近7日平均: 0,
});

const { renderEcharts: renderHeroChart } = useEcharts(heroChartRef);
const { renderEcharts: renderTrendChart } = useEcharts(trendChartRef);

function buildHeroOption(
  dates: string[],
  data: number[],
  inProgressIdx: null | number = null,
) {
  const hasPartial = inProgressIdx != null;
  // 进行中的点不参与纵轴定标, 否则当天的小值会把完整日全压到顶部;
  // 显示时钉在上/下边缘, 真实值看标签与 tooltip
  const completeVals = hasPartial
    ? data.filter((_, i) => i !== inProgressIdx)
    : data;
  const lo = Math.min(...completeVals);
  const hi = Math.max(...completeVals);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.15;
  const yMin = Math.max(0, lo - pad);
  const yMax = hi + pad;
  const baseSeries = {
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 5,
    emphasis: { disabled: true },
  };
  const baseLabel = {
    show: true,
    position: 'top',
    color: '#6b7280',
    fontSize: 10,
  };
  const series: any[] = [
    {
      ...baseSeries,
      data: data.map((v, i) => (hasPartial && i === inProgressIdx ? null : v)),
      itemStyle: { color: '#3b82f6' },
      lineStyle: { color: '#3b82f6', width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(59,130,246,0.25)' },
            { offset: 1, color: 'rgba(59,130,246,0.02)' },
          ],
        },
      },
      label: { ...baseLabel, formatter: (p: any) => abbrMoney(p.value) },
    },
  ];
  if (hasPartial) {
    series.push({
      ...baseSeries,
      data: data.map((v, i) => {
        if (i === inProgressIdx) return Math.min(Math.max(v, yMin), yMax);
        return i === inProgressIdx - 1 ? v : null; // 与前一天虚线相连
      }),
      itemStyle: { color: '#9ca3af' },
      lineStyle: { color: '#9ca3af', width: 2, type: 'dashed' },
      label: {
        ...baseLabel,
        color: '#9ca3af',
        formatter: (p: any) =>
          p.dataIndex === inProgressIdx ? abbrMoney(data[p.dataIndex]) : '',
      },
    });
  }
  return {
    grid: { top: 36, right: 24, bottom: 24, left: 20 },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#9ca3af', fontSize: 11 },
    },
    yAxis: hasPartial
      ? { type: 'value', show: false, min: yMin, max: yMax }
      : { type: 'value', show: false, scale: true },
    series,
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = (Array.isArray(params) ? params : [params]).find(
          (x: any) => x.value != null,
        );
        if (!p) return '';
        const tag =
          hasPartial && p.dataIndex === inProgressIdx ? ' (进行中)' : '';
        return `${p.name}<br/>${money(data[p.dataIndex], 2)}${tag}`;
      },
    },
  };
}

function buildTrendOption(
  axis: string[],
  spend: number[],
  payment: number[],
  subscription: number[],
  pts: Array<{
    时间: string;
    消耗: null | number;
    付费成本: null | number;
    订阅成本?: null | number;
    项目明细?: Array<{ 项目: string; 消耗: number }>;
  }> = [],
) {
  const legend = ['消耗', '付费成本', '订阅成本'];
  const series: any[] = [
    {
      name: '消耗',
      type: 'line',
      data: spend,
      showSymbol: false,
      smooth: true,
      // lineStyle: { color: '#3b82f6', width: 2 },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(59,130,246,0.2)' },
            { offset: 1, color: 'rgba(59,130,246,0.02)' },
          ],
        },
      },
    },
    {
      name: '付费成本',
      type: 'line',
      yAxisIndex: 1,
      data: payment,
      showSymbol: false,
      smooth: true,
      // lineStyle: { color: '#22c55e', width: 2 },
    },
    {
      name: '订阅成本',
      type: 'line',
      yAxisIndex: 1,
      data: subscription,
      showSymbol: false,
      smooth: true,
      // lineStyle: { color: '#8b5cf6', width: 2 },
    },
  ];
  return {
    legend: {
      top: 0,
      left: 0,
      data: legend,
      itemGap: 24,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: '#6b7280', fontSize: 12 },
    },
    grid: { top: 50, right: 70, bottom: 30, left: 60 },
    series,
    xAxis: {
      type: 'category',
      data: axis,
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#9ca3af', fontSize: 11 },
      boundaryGap: false,
    },
    yAxis: [
      {
        type: 'value',
        name: '消耗',
        axisLabel: {
          color: '#9ca3af',
          formatter: (v: number) => `$${(v / 1000).toFixed(0)}K`,
        },
        splitLine: { lineStyle: { color: '#f3f4f6' } },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'value',
        name: '付费成本',
        position: 'right',
        axisLabel: {
          color: '#9ca3af',
          formatter: (v: number) => `$${Number(v).toFixed(0)}`,
        },
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
      },
    ],
    tooltip: {
      trigger: 'axis',
      enterable: true,
      extraCssText: 'min-width:260px;',
      formatter: (params: any) => {
        const list = Array.isArray(params) ? params : [params];
        const idx = list[0]?.dataIndex ?? 0;
        const pt = pts[idx];
        let html = `<div style="font-size:12px;font-weight:600;margin-bottom:4px">${list[0]?.axisValueLabel ?? ''}</div>`;
        for (const p of list) {
          const v =
            p.value == null ? '-' : `$${Number(p.value).toLocaleString()}`;
          html += `<div style="display:flex;align-items:center;gap:6px">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>
            <span style="color:#6b7280">${p.seriesName}</span>
            <span style="margin-left:auto;font-weight:600">${v}</span>
          </div>`;
        }
        const details = (pt?.['项目明细'] ?? []).filter(
          (d) => d['项目'] != null && d['项目'] !== '未知',
        );
        if (details && details.length > 0) {
          html += `<div style="margin-top:6px;border-top:1px solid #f3f4f6;padding-top:4px">`;
          html += `<div style="display:grid;grid-template-columns:1fr 72px 72px 72px;gap:4px;font-size:11px;color:#9ca3af;padding-bottom:3px;border-bottom:1px solid #f3f4f6;text-align:center">
            <span>项目</span><span>消耗</span><span style="text-align:right">付费成本</span><span style="text-align:right">订阅成本</span>
          </div>`;
          html += `<div style="max-height:160px;overflow-y:auto">`;
          for (const d of details) {
            html += `<div style="display:grid;grid-template-columns:1fr 72px 72px 72px;gap:4px;font-size:12px;margin-top:4px;align-items:center">
              <span style="color:#6b7280;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${d['项目']}</span>
              <span style="text-align:right;font-weight:500">$${Number(d['消耗']).toLocaleString()}</span>
              <span style="text-align:right;color:#6b7280">${d['付费成本'] != null ? '$' + Number(d['付费成本']).toLocaleString() : '-'}</span>
              <span style="text-align:right;color:#6b7280">${d['订阅成本'] != null ? '$' + Number(d['订阅成本']).toLocaleString() : '-'}</span>
            </div>`;
          }
          html += `</div></div>`;
        }
        return html;
      },
    },
  };
}

async function loadSummary(signal?: AbortSignal) {
  const res = await getSpendSummary(
    {
      date: filters.date,
      trend_days: 7,
      game_platform: filterVal(filters.game_platform),
      region: filterVal(filters.region),
      placer: filterVal(filters.placer),
      channel: filterVal(filters.channel),
      department: filterArr(filters.department),
    } as any,
    { signal },
  );
  if (res) summary.value = res;
  const pts = res?.['消耗趋势'] ?? [];
  const dates = pts.map((p) => String(p.date).slice(5)); // MM-DD
  const trend = pts.map((p) => Number(p['消耗']) || 0);
  const inProgressIdx = pts.findIndex((p) => p['进行中']);
  renderHeroChart(
    buildHeroOption(dates, trend, inProgressIdx === -1 ? null : inProgressIdx),
  );
}

/** 重载所有图表与表格; 再次调用会中止上一次仍在飞的请求, 只保留最新一次 */
const querying = ref(false); // 搜索按钮转圈
const summaryLoading = ref(false); // 第一个 card (今日总消耗 + hero 图) 的加载态
const trendLoading = ref(false); // 03 消耗与转化趋势图的加载态

async function loadTrend(signal?: AbortSignal) {
  trendLoading.value = true;
  try {
    const res = await getIntradayTrend(
      {
        date: filters.date,
        period: trendMode.value.period,
        game_platform: filterVal(filters.game_platform),
        region: filterVal(filters.region),
        placer: filterVal(filters.placer),
        channel: filterVal(filters.channel),
        department: filterArr(filters.department),
      } as any,
      { signal },
    );
    const pts = res?.data ?? [];
    const axis = pts.map((p) => p['时间']);
    const spend = pts.map((p) => Number(p['消耗']) || 0);
    const payment = pts.map((p) => Number(p['付费成本']) || 0);
    const subscription = pts.map((p) => Number(p['订阅成本']) || 0);
    renderTrendChart(buildTrendOption(axis, spend, payment, subscription, pts));
  } finally {
    trendLoading.value = false;
  }
}
let dataAbort: AbortController | null = null;
let dataSeq = 0;
async function reloadData(opts: { spin?: boolean } = {}) {
  syncFiltersToUrl(); // URL 始终反映本次查询的筛选
  dataAbort?.abort(); // 终止上一次在途请求
  const ac = new AbortController();
  dataAbort = ac;
  const seq = ++dataSeq;
  if (opts.spin) querying.value = true;
  summaryLoading.value = true;

  // 第一个 card 的遮罩只跟随两个图表, 图表数据出来就退出(不等表格)
  const chartsDone = Promise.all([loadSummary(ac.signal), loadTrend(ac.signal)])
    .catch(() => {})
    .finally(() => {
      if (seq === dataSeq) summaryLoading.value = false;
    });

  try {
    await Promise.all([
      chartsDone,
      projectGridApi.reload(),
      placerGridApi.reload(),
      teamRankGridApi.reload(),
      channelGridApi.reload(),
    ]);
  } catch {
    // 被中止或出错: 交给更新的那次处理
  } finally {
    if (seq === dataSeq && opts.spin) querying.value = false;
  }
}

/** 搜索按钮: 带按钮转圈 */
function applyFilters() {
  reloadData({ spin: true });
}

function resetFilters() {
  filters.date = '';
  filters.game_platform = '';
  filters.region = '';
  filters.placer = '';
  filters.channel = '';
  filters.department = [];
  activeTplId.value = null;
  syncFiltersToUrl();
}

// ==================== 筛选模板 (个人私有) ====================
const templates = ref<FilterTemplate[]>([]);
const newTplName = ref('');
const tplSaving = ref(false);
const tplDeletingId = ref<null | string>(null);
const activeTplId = ref<null | string>(null); // 当前已应用的模板
const applyingTplId = ref<null | string>(null); // 正在应用(查询)的模板
const activeTplName = computed(
  () => templates.value.find((t) => t.id === activeTplId.value)?.name ?? '',
);

async function loadTemplates() {
  templates.value = (await listFilterTemplates()) ?? [];
}

// 上次使用时间展示: 后端给 "YYYY-MM-DD HH:MM:SS", 这里简化成 "MM-DD HH:MM"
function fmtUseTime(s: null | string): string {
  if (!s) return '未使用';
  const m = s.match(/^\d{4}-(\d{2}-\d{2}) (\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]}` : s;
}

// 应用模板: 模板转圈只覆盖"取参数"这一步; 拿到参数即停转、显示模板名,
// 数据重载在后台进行(不带搜索按钮转圈), 且会中止上一次在途请求
async function applyTemplate(t: FilterTemplate) {
  applyingTplId.value = t.id;
  let detail;
  try {
    detail = await applyFilterTemplate(t.id);
  } finally {
    applyingTplId.value = null;
  }
  if (!detail) return;
  filters.game_platform = detail.filters.game_platform?.[0] ?? '';
  filters.region = detail.filters.region?.[0] ?? '';
  filters.placer = detail.filters.placer?.[0] ?? '';
  activeTplId.value = t.id; // 立即显示模板名
  loadTemplates(); // 刷新列表顺序(使用时间已变)
  reloadData(); // 后台重载数据, 不转搜索按钮
}

async function saveTemplate() {
  const name = newTplName.value.trim();
  if (!name || tplSaving.value) return;
  tplSaving.value = true;
  try {
    await createFilterTemplate({
      name,
      filters: {
        game_platform: filters.game_platform ? [filters.game_platform] : [],
        region: filters.region ? [filters.region] : [],
        placer: filters.placer ? [filters.placer] : [],
      },
    });
    newTplName.value = '';
    await loadTemplates();
    message.success('模板已保存');
  } finally {
    tplSaving.value = false;
  }
}

// 返回 Promise 给 Popconfirm, 确认按钮自动 loading 直到删完
async function removeTemplate(t: FilterTemplate) {
  if (tplDeletingId.value) return;
  tplDeletingId.value = t.id;
  try {
    await deleteFilterTemplate(t.id);
    if (activeTplId.value === t.id) activeTplId.value = null;
    await loadTemplates();
  } finally {
    tplDeletingId.value = null;
  }
}

onMounted(async () => {
  document.documentElement.classList.add('data-report-wide-scrollbar');
  window.addEventListener('adpulse:ui-scale-change', syncReportGridHeights);
  syncReportGridHeights();

  // 加载筛选下拉选项
  getFilterOptions()
    .then((res: FilterOptions | undefined) => {
      projectOptions.value = (res?.projects ?? []).map((v: string) => ({
        label: v,
        value: v,
      }));
      placerOptions.value = Array.isArray(res?.placers) ? res.placers : [];
      regionOptions.value =
        res?.region_options ??
        (res?.regions ?? []).map((code: string) => ({
          label: _countryMap.get(code) ?? code,
          value: code,
        }));
      channelOptions.value = Array.isArray(res?.channels) ? res.channels : [];
      departmentOptions.value =
        res?.department_options ??
        (res?.departments ?? []).map((v: string) => ({
          label: v,
          value: v,
        }));
    })
    .catch(() => {})
    .finally(() => {
      filterOptionsLoading.value = false;
    });

  await loadTemplates();
  readFiltersFromUrl();
  reloadData();
  loadAlertFeed();
});

onUnmounted(() => {
  document.documentElement.classList.remove('data-report-wide-scrollbar');
  window.removeEventListener('adpulse:ui-scale-change', syncReportGridHeights);
});

// ==================== 实时预警 ====================
const alertFeed = ref<AlertFeedResult | null>(null);
const alertLoading = ref(false);

const alertSummary = computed(() => {
  const s = alertFeed.value?.summary;
  if (!s) return [];
  return [
    { label: `${s.critical}条严重` },
    { label: `${s.warning}条观察` },
    { label: `${s.info}条提示` },
  ];
});

const severeAlerts = computed(() =>
  (alertFeed.value?.items ?? []).filter((a) => a.severity === 'critical'),
);

const observeAlerts = computed(() =>
  (alertFeed.value?.items ?? []).filter((a) => a.severity !== 'critical'),
);

function alertContext(alert: AlertItem): string {
  const parts = [
    alert.project_name,
    alert.platform,
    alert.placer_id ? `@${alert.placer_id}` : '',
  ].filter(Boolean);
  return parts.join(' · ');
}

async function loadAlertFeed() {
  alertLoading.value = true;
  try {
    // const res = await getAlertFeed({ minutes: 30, mock: true });
    const res = await getAlertFeed({ minutes: 30 });
    if (res) alertFeed.value = res;
  } finally {
    alertLoading.value = false;
  }
}

async function ignoreAlert(alert: AlertItem) {
  if (alertFeed.value) {
    alertFeed.value = {
      ...alertFeed.value,
      items: alertFeed.value.items.filter((a: AlertItem) => a.id !== alert.id),
    };
  }
  try {
    await doAlertAction(alert.id, { action_type: 'handled' });
  } catch {
    loadAlertFeed();
  }
}

async function handleAlertAction(alert: AlertItem, action: AlertAction) {
  if (action.type === 'view') {
    doAlertAction(alert.id, { action_type: 'view' });
    if (alert.level && alert.object_id) {
      router.push(
        `/data-report/drilldown?level=${alert.level}&object_id=${alert.object_id}`,
      );
    }
    return;
  }
  if (action.type === 'open_account') {
    doAlertAction(alert.id, { action_type: 'open_account' });
    return;
  }
  await doAlertAction(alert.id, {
    action_type: action.type,
    snooze_minutes: action.type === 'snooze' ? 30 : undefined,
  });
  loadAlertFeed();
}
</script>

<template>
  <Page
    class="adpulse-section-page adpulse-report-page bg-muted/40"
    content-class="p-4"
    description="汇总经营与投放表现，支持按项目、投手、地区和渠道交叉分析。"
    title="经营与投放报表"
  >
    <div class="space-y-4">
      <div class="border-border bg-card rounded-lg border p-4">
        <!-- ===== 筛选 ===== -->
        <div
          class="report-filter-bar flex flex-wrap items-center gap-2 text-sm"
        >
          <!-- 日期与其他筛选字段共用同一标签槽位，确保换行后列起点一致。 -->
          <label class="inline-flex min-w-0 items-center gap-2 text-sm">
            <span class="ux-filter-label text-muted-foreground w-16 shrink-0">
              筛选
            </span>
            <DatePicker
              :value="filters.date"
              value-format="YYYY-MM-DD"
              placeholder="今日"
              variant="filled"
              class="filter-chip-date"
              :open="dateOpen"
              :show-today="false"
              :render-extra-footer="dateFooter"
              :disabled-date="(d) => d && d.isAfter(dayjs(), 'day')"
              @update:value="setDate"
              @open-change="(o) => (dateOpen = o)"
            />
          </label>
          <!-- 项目 -->
          <FilterDropdown
            label="项目"
            variant="pill"
            :model-value="filters.game_platform || undefined"
            :options="projectOptions"
            :loading="filterOptionsLoading"
            placeholder="搜索项目"
            empty-text="无匹配项目"
            @update:model-value="(v) => (filters.game_platform = v || '')"
          />
          <!-- 投手 -->
          <FilterDropdown
            label="投手"
            variant="pill"
            :model-value="filters.placer || undefined"
            :options="placerOptions"
            :loading="filterOptionsLoading"
            placeholder="搜索投手"
            empty-text="无匹配投手"
            @update:model-value="(v) => (filters.placer = v || '')"
          />
          <!-- 地区 -->
          <FilterDropdown
            label="地区"
            variant="pill"
            :model-value="filters.region || undefined"
            :options="regionOptions"
            :loading="filterOptionsLoading"
            placeholder="搜索地区"
            empty-text="无匹配地区"
            @update:model-value="(v) => (filters.region = v || '')"
          />
          <FilterDropdown
            label="渠道"
            variant="pill"
            :model-value="filters.channel || undefined"
            :options="channelOptions"
            :loading="filterOptionsLoading"
            placeholder="搜索渠道"
            empty-text="无匹配渠道"
            @update:model-value="(v) => (filters.channel = v || '')"
          />
          <FilterDropdown
            label="部门"
            variant="pill"
            multiple
            :model-value="filters.department"
            :options="departmentOptions"
            :loading="filterOptionsLoading"
            placeholder="搜索部门"
            empty-text="无匹配部门"
            @update:model-value="
              (v) => (filters.department = Array.isArray(v) ? v : [])
            "
          />
          <button
            class="bg-primary text-primary-foreground hover:bg-primary/90 flex h-10 w-10 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            title="搜索"
            :disabled="querying"
            @click="applyFilters"
          >
            <svg
              v-if="querying"
              viewBox="0 0 24 24"
              class="h-3.5 w-3.5 animate-spin"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
            >
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            <svg
              v-else
              viewBox="0 0 24 24"
              class="h-3.5 w-3.5"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <circle cx="11" cy="11" r="7" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
          <button
            class="bg-muted text-muted-foreground hover:bg-accent min-h-10 rounded-md px-3 text-sm font-medium transition-colors"
            @click="resetFilters"
          >
            重置
          </button>
          <!-- 筛选模板 -->
          <Dropdown
            trigger="click"
            @open-change="
              (open: boolean) => {
                if (open) newTplName = '';
              }
            "
          >
            <button
              class="inline-flex min-h-10 max-w-[180px] items-center gap-1 rounded-md px-3 text-sm font-medium transition-colors"
              :class="
                activeTplName
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'bg-muted text-muted-foreground hover:bg-accent'
              "
            >
              <span class="truncate">{{
                activeTplName ? `模板·${activeTplName}` : '筛选模板'
              }}</span>
              <span class="shrink-0">▾</span>
            </button>
            <template #overlay>
              <div>
                <div
                  class="tpl-pop-host border-border bg-card min-w-56 rounded-lg border p-2"
                  data-popup-scroll-host
                  @click.stop
                >
                  <div class="text-muted-foreground px-2 py-1 text-xs">
                    我的模板
                  </div>
                  <div class="max-h-60 overflow-auto">
                    <div
                      v-for="t in templates"
                      :key="t.id"
                      class="hover:bg-accent group flex items-center justify-between gap-2 rounded-md px-2 py-1.5"
                      :class="activeTplId === t.id ? 'bg-accent' : ''"
                    >
                      <span
                        class="min-w-0 flex-1 cursor-pointer"
                        @click="applyTemplate(t)"
                      >
                        <span class="flex items-center gap-1">
                          <span
                            class="block truncate text-sm"
                            :class="
                              activeTplId === t.id
                                ? 'text-foreground font-medium'
                                : 'text-foreground'
                            "
                            >{{ t.name }}</span
                          >
                          <svg
                            v-if="applyingTplId === t.id"
                            viewBox="0 0 24 24"
                            class="text-primary h-3 w-3 shrink-0 animate-spin"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2.5"
                            stroke-linecap="round"
                          >
                            <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                          </svg>
                        </span>
                        <span class="text-muted-foreground block text-xs"
                          >上次使用 {{ fmtUseTime(t.use_time) }}</span
                        >
                      </span>
                      <Popconfirm
                        title="确定删除该模板?"
                        ok-text="删除"
                        cancel-text="取消"
                        placement="top"
                        overlay-class-name="tpl-del-pop"
                        :ok-button-props="{ loading: tplDeletingId === t.id }"
                        :get-popup-container="getPopupContainer"
                        @confirm="removeTemplate(t)"
                      >
                        <span
                          class="text-muted-foreground hover:text-destructive px-1 text-sm opacity-0 group-hover:opacity-100"
                          title="删除"
                          @click.stop
                          >×</span
                        >
                      </Popconfirm>
                    </div>
                    <div
                      v-if="templates.length === 0"
                      class="text-muted-foreground px-2 py-3 text-center text-xs"
                    >
                      暂无模板, 选好条件后保存
                    </div>
                  </div>
                  <div
                    class="border-border mt-1 flex items-center gap-1 border-t pt-2"
                  >
                    <Input
                      v-model:value="newTplName"
                      placeholder="输入名称, 保存为模板"
                      :disabled="tplSaving"
                      @press-enter="saveTemplate"
                    />
                    <button
                      class="bg-primary text-primary-foreground hover:bg-primary/90 min-h-10 shrink-0 rounded-md px-3 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40"
                      :disabled="!newTplName.trim() || tplSaving"
                      @click="saveTemplate"
                    >
                      {{ tplSaving ? '保存中…' : '保存' }}
                    </button>
                  </div>
                </div>
              </div>
            </template>
          </Dropdown>
          <!-- <BaseButton class="ml-auto">导出</BaseButton> -->
        </div>
      </div>

      <!-- ===== 今日总消耗 ===== -->
      <div
        class="border-border bg-card relative min-h-[150px] rounded-lg border p-4"
      >
        <div
          v-if="summaryLoading"
          class="bg-card/70 absolute inset-0 z-10 flex items-center justify-center"
        >
          <span
            class="text-muted-foreground icon-[ant-design--loading-outlined] animate-spin text-2xl"
          />
        </div>
        <div
          class="flex min-h-[118px] flex-wrap items-stretch justify-between gap-4 lg:flex-nowrap"
        >
          <div
            class="flex min-w-0 flex-1 flex-col justify-between py-1"
            style="container-type: inline-size"
          >
            <div>
              <div class="text-muted-foreground mb-1 text-xs">今日总消耗</div>
              <div class="flex flex-wrap items-baseline gap-3">
                <AnimatedCount
                  :value="summary.今日总消耗"
                  :duration="1500"
                  :decimals="2"
                  prefix="$"
                  class="text-foreground text-[clamp(2.5rem,11cqw,5.5rem)] font-bold leading-none tracking-tight"
                />
                <span
                  v-if="summary.环比昨日"
                  class="inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-medium"
                  :class="
                    summary.环比昨日.startsWith('-')
                      ? 'bg-destructive/10 text-destructive'
                      : 'bg-muted text-foreground'
                  "
                >
                  {{ summary.环比昨日.startsWith('-') ? '▼' : '▲'
                  }}{{ summary.环比昨日.replace(/^[+-]/, '') }} 环比昨日
                </span>
              </div>
            </div>
            <div
              class="text-muted-foreground flex flex-wrap items-center gap-2 text-sm"
            >
              <span
                >昨日
                <span class="text-foreground font-medium">{{
                  money(summary.昨日, 2)
                }}</span></span
              >
              <span class="text-muted-foreground">·</span>
              <span
                >近7日平均
                <span class="text-foreground font-medium">{{
                  money(summary.近7日平均, 2)
                }}</span></span
              >
              <span class="text-muted-foreground">·</span>
              <span
                >本月
                <span class="text-foreground font-medium">{{
                  money(summary.本月, 2)
                }}</span></span
              >
            </div>
          </div>
          <div class="h-[118px] min-w-0 flex-1">
            <EchartsUI ref="heroChartRef" height="118px" width="100%" />
          </div>
        </div>
      </div>
      <!-- ===== 01 项目维度 & 渠道商维度 ===== -->
      <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div class="border-border bg-card min-w-0 rounded-lg border p-4">
          <SectionHeader no="01" title="项目维度" />
          <ProjectGrid />
        </div>
        <div class="border-border bg-card min-w-0 rounded-lg border p-4">
          <SectionHeader no="02" title="渠道商维度" />
          <ChannelGrid />
        </div>
      </div>

      <!-- ===== 02 投手维度 ===== -->
      <div class="border-border bg-card rounded-lg border p-4">
        <SectionHeader no="03" title="投手维度" subtitle="数据化表现">
          <!-- <template #right>
            <a
              href="#"
              class="text-sm font-medium text-blue-500 hover:text-blue-600"
              >查看全部投手 →</a
            >
          </template> -->
        </SectionHeader>
        <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div class="col-span-2 min-w-0">
            <div class="text-foreground mb-1 text-lg font-bold">投手排行</div>
            <PlacerGrid />
          </div>
          <div class="min-w-0">
            <div class="text-foreground mb-1 text-lg font-bold">团队消耗</div>
            <TeamRankGrid />
          </div>
        </div>
      </div>

      <!-- ===== 03 消耗与转化趋势 ===== -->
      <div class="border-border bg-card rounded-lg border p-4">
        <SectionHeader no="04" :title="`消耗与转化趋势·${trendMode.label}`">
          <template #right>
            <div class="border-border flex overflow-hidden rounded-md border">
              <button
                v-for="m in trendModes"
                :key="m.label"
                class="min-h-10 px-3 text-sm font-medium transition-colors"
                :class="
                  trendMode.period === m.period
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-card text-muted-foreground hover:bg-accent'
                "
                @click="
                  trendMode = m;
                  loadTrend();
                "
              >
                {{ m.label }}
              </button>
            </div>
          </template>
        </SectionHeader>
        <div class="relative">
          <div
            v-if="trendLoading"
            class="bg-card/70 absolute inset-0 z-10 flex items-center justify-center"
          >
            <span
              class="text-muted-foreground icon-[ant-design--loading-outlined] animate-spin text-2xl"
            />
          </div>
          <EchartsUI ref="trendChartRef" height="300px" width="100%" />
        </div>
      </div>

      <!-- ===== 04 实时预警 ===== -->
      <div
        class="border-border bg-card flex flex-col gap-4 rounded-lg border p-4"
      >
        <SectionHeader
          no="05"
          title="实时预警"
          :subtitle="`自动预警异常·近${alertFeed?.minutes ?? 30}分钟`"
          mb="mb-0"
        >
          <template #title-action>
            <button
              class="bg-muted text-muted-foreground hover:bg-accent inline-flex min-h-10 min-w-10 items-center justify-center rounded-md transition-colors"
              :class="{ 'cursor-not-allowed opacity-60': alertLoading }"
              :disabled="alertLoading"
              title="刷新"
              @click="loadAlertFeed"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-4 w-4"
                :class="{ 'animate-spin': alertLoading }"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path
                  d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"
                />
              </svg>
            </button>
          </template>
          <template #right>
            <div class="flex flex-col items-end gap-3">
              <span class="text-muted-foreground text-xs">
                <span v-for="(s, i) in alertSummary" :key="s.label">
                  <span v-if="i > 0">·</span>{{ s.label }}
                </span>
              </span>
              <!-- <BaseButton variant="black" 
                @click="router.push('/data-report/alert-rules?tab=records')"
              >
                触发记录
              </BaseButton> -->
            </div>
          </template>
        </SectionHeader>

        <!-- 严重卡片 -->
        <div class="grid grid-cols-4 gap-4">
          <div
            v-for="alert in severeAlerts"
            :key="alert.id"
            class="border-destructive bg-card relative flex flex-col gap-3 overflow-hidden rounded-lg border p-4 pl-5"
          >
            <div
              class="bg-destructive absolute bottom-0 left-0 top-0 w-1 rounded-l-lg"
            ></div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
                  class="bg-destructive text-destructive-foreground rounded px-2 py-0.5 text-xs font-semibold"
                  >{{ alert.severity_label }}</span
                >
                <span class="text-muted-foreground text-xs"
                  >{{ alert.checked_at }} · {{ alert.minutes_ago }}分钟前</span
                >
              </div>
              <span
                class="border-border bg-card text-muted-foreground rounded border px-2 py-0.5 text-xs"
                >{{ alert.tag }}</span
              >
            </div>
            <div class="text-foreground text-sm font-semibold leading-snug">
              {{ alert.title }}
            </div>
            <div class="text-muted-foreground text-xs">
              {{ alertContext(alert) }}
            </div>
            <div v-if="alert.metrics.length > 0" class="grid grid-cols-2 gap-2">
              <div class="rounded-lg p-2">
                <div class="text-muted-foreground mb-1 text-xs">
                  {{ alert.metrics[0]?.label }}
                </div>
                <div class="text-foreground text-sm font-bold">
                  {{ alert.metrics[0]?.display }}
                  <span
                    v-if="alert.metrics[0]?.change_display"
                    class="text-destructive ml-1 text-xs"
                    >{{ alert.metrics[0]?.change_display }}</span
                  >
                </div>
              </div>
              <div class="bg-muted rounded-md p-2">
                <div class="text-muted-foreground mb-1 text-xs">
                  {{ alert.metrics[1]?.label }}
                </div>
                <div class="text-destructive text-sm font-bold">
                  {{ alert.metrics[1]?.display
                  }}<span
                    v-if="alert.metrics[1]?.target_display"
                    class="text-muted-foreground ml-1 text-xs"
                    >/ {{ alert.metrics[1]?.target_display }}</span
                  >
                </div>
              </div>
            </div>
            <div class="mt-auto flex gap-2">
              <Popconfirm
                title="确定暂停此广告？"
                ok-text="暂停"
                cancel-text="取消"
                @confirm="
                  handleAlertAction(alert, {
                    type: 'pause',
                    label: '暂停广告',
                    style: 'danger',
                  })
                "
              >
                <button
                  class="bg-destructive text-destructive-foreground hover:bg-destructive/90 flex-1 rounded-md py-2 text-xs font-semibold transition-colors"
                >
                  暂停广告
                </button>
              </Popconfirm>
              <button
                class="border-border bg-card text-foreground hover:bg-accent flex-1 rounded-md border py-2 text-xs font-semibold transition-colors"
                @click="
                  handleAlertAction(alert, {
                    type: 'view',
                    label: '去查看',
                    style: 'secondary',
                  })
                "
              >
                去查看
              </button>
              <Popconfirm
                title="确定忽略此预警？"
                ok-text="忽略"
                cancel-text="取消"
                @confirm="ignoreAlert(alert)"
              >
                <button
                  class="border-border bg-card text-foreground hover:bg-accent flex-1 rounded-md border px-3 py-2 text-xs font-semibold transition-colors"
                >
                  忽略
                </button>
              </Popconfirm>
            </div>
          </div>
        </div>

        <!-- 观察卡片 -->
        <div class="grid grid-cols-4 gap-4">
          <div
            v-for="alert in observeAlerts"
            :key="alert.id"
            class="border-border bg-card relative flex flex-col gap-2 overflow-hidden rounded-lg border p-4 pl-5"
          >
            <div
              class="bg-muted-foreground absolute bottom-0 left-0 top-0 w-1 rounded-l-lg"
            ></div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span
                  class="bg-muted text-foreground rounded px-2 py-0.5 text-xs font-semibold"
                  >{{ alert.severity_label }}</span
                >
                <span class="text-muted-foreground text-xs"
                  >{{ alert.checked_at }} · {{ alert.minutes_ago }}分钟前</span
                >
              </div>
              <span
                class="border-border bg-card text-muted-foreground rounded border px-2 py-0.5 text-xs"
                >{{ alert.tag }}</span
              >
            </div>
            <div class="text-foreground text-sm font-semibold leading-snug">
              {{ alert.title }}
            </div>
            <div class="text-muted-foreground flex-1 text-xs">
              {{ alertContext(alert) }}
            </div>
            <div class="mt-auto flex gap-2">
              <button
                class="border-border bg-card text-foreground hover:bg-accent flex-1 rounded-md border py-2 text-xs font-semibold transition-colors"
                @click="
                  handleAlertAction(alert, {
                    type: 'view',
                    label: '去查看',
                    style: 'secondary',
                  })
                "
              >
                去查看
              </button>
              <Popconfirm
                title="确定忽略此预警？"
                ok-text="忽略"
                cancel-text="取消"
                @confirm="ignoreAlert(alert)"
              >
                <button
                  class="border-border bg-card text-foreground hover:bg-accent flex-1 rounded-md border px-3 py-2 text-xs font-semibold transition-colors"
                >
                  忽略
                </button>
              </Popconfirm>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Page>
</template>
<style>
html.data-report-wide-scrollbar ::-webkit-scrollbar {
  width: 12px;
  height: 12px;
}

html.data-report-wide-scrollbar ::-webkit-scrollbar-thumb {
  background-color: rgb(148 163 184 / 50%);
  background-clip: content-box;
  border: 3px solid transparent;
  border-radius: 9999px;
}

html.data-report-wide-scrollbar ::-webkit-scrollbar-thumb:hover {
  background-color: rgb(100 116 139 / 60%);
  background-clip: content-box;
}

/* 删除确认气泡: 挂在窄容器内时, 强制标题不换行、按钮横向一行 */

.adpulse-report-page .report-filter-bar .filter-chip-date {
  width: var(--adpulse-filter-field-width);
}

.adpulse-report-page .report-filter-bar > button {
  height: var(--adpulse-control-height);
  min-height: var(--adpulse-control-height);
}

.adpulse-report-page .report-dimension-grid {
  height: var(--adpulse-table-viewport-height);
}

.adpulse-report-page .report-dimension-grid > .vxe-grid {
  height: 100% !important;
}

.adpulse-report-page .report-dimension-grid .vxe-grid--form-wrapper:empty {
  display: none;
}
</style>
