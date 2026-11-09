<script lang="ts" setup>
import type {
  DashboardAccounts,
  DashboardActionKind,
  DashboardAnalyzeQuery,
  DashboardCampaignPerformance,
  DashboardOverview,
  DashboardRange,
  DashboardTrend,
} from '#/domain/my-dashboard';

import { computed, ref, watch } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';

import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
  InputNumber,
  message,
  Modal,
  Select,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { myDashboardService } from '#/domain/my-dashboard';

import DeliveryObjectWorkspace from './components/DeliveryObjectWorkspace.vue';
import { useMyDashboardAgent } from './use-my-dashboard-agent';
import { useMyDashboardCampaigns } from './use-my-dashboard-campaigns';

defineOptions({ name: 'MyDashboard' });

const userStore = useUserStore();
const range = ref<DashboardRange>('today');
const dashboardMode = ref<'objects' | 'overview'>('objects');
const automationDrawerOpen = ref(false);
const dashboardLoading = ref(false);
const refreshLoading = ref(false);
const dashboardError = ref('');
const selectedCurrency = ref('');
const analysisAccountId = ref<string>();
const overviewData = ref<DashboardOverview | null>(null);
const accountsData = ref<DashboardAccounts | null>(null);
const trendData = ref<DashboardTrend | null>(null);
const workspace = ref<InstanceType<typeof DeliveryObjectWorkspace>>();
const operatorName = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.full_name ||
    '当前投放人员',
);
function currentReportDate() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}
const anchorDate = ref(currentReportDate());

const dashboardDateRange = computed(() => {
  // 默认选择北京时间的日期；后端按各账户本地报表日期查询，不做 UTC 日界转换。
  const today = anchorDate.value;
  const start = new Date(`${today}T00:00:00Z`);
  const daysBefore = { month: 29, today: 0, week: 6 }[range.value];
  start.setUTCDate(start.getUTCDate() - daysBefore);
  return { endDate: today, startDate: start.toISOString().slice(0, 10) };
});
const agentQuery = computed<DashboardAnalyzeQuery>(() => ({
  end_date: dashboardDateRange.value.endDate,
  range: range.value,
  start_date: dashboardDateRange.value.startDate,
}));
const {
  analysis: agentAnalysis,
  analysisError,
  analysisLoading,
  hosting,
  hostingDraft,
  hostingError,
  hostingLoaded,
  hostingLoading,
  hostingSaving,
  loadAnalysis,
  loadHosting,
  saveHosting,
} = useMyDashboardAgent(
  agentQuery,
  computed(() => dashboardMode.value === 'overview'),
);
const {
  analyzeCampaign,
  changePage: changeDetailPage,
  error: detailError,
  loading: detailLoading,
  page: detailPage,
  pageSize: detailPageSize,
  recommendationCounts: detailRecommendationCounts,
  refreshPerformance: refreshDetails,
  rows: focusRows,
  total: detailTotal,
} = useMyDashboardCampaigns(dashboardDateRange, analysisAccountId, agentQuery);
const metricsLoading = computed(() =>
  dashboardMode.value === 'overview'
    ? analysisLoading.value
    : dashboardLoading.value,
);
const automation = computed(() => ({
  enabled: hosting.value?.enabled ?? false,
  spendChangeThreshold: hosting.value?.spend_change_threshold ?? 15,
}));
const rangeOptions = [
  { label: '今日', value: 'today' },
  { label: '近 7 天', value: 'week' },
  { label: '近 30 天', value: 'month' },
];
const currencyOptions = computed(() =>
  (overviewData.value?.summaries ?? []).map((row) => ({
    label: row.currency,
    value: row.currency,
  })),
);
const selectedSummary = computed(() =>
  overviewData.value?.summaries.find(
    (row) => row.currency === selectedCurrency.value,
  ),
);
const trendPoints = computed(() => {
  if (dashboardMode.value === 'overview') {
    const series = agentAnalysis.value?.fact.series;
    return (series?.labels ?? []).flatMap((label, index) => {
      const spend = series?.spend[index];
      const registrations = series?.registrations[index];
      return typeof spend === 'number' && typeof registrations === 'number'
        ? [{ label, spend, registrations }]
        : [];
    });
  }
  return (
    trendData.value?.series.find(
      (row) => row.currency === selectedCurrency.value,
    )?.points ?? []
  );
});
const snapshot = computed(() => {
  const fact = agentAnalysis.value?.fact;
  const isAnalysis = dashboardMode.value === 'overview';
  return {
    cpa: (isAnalysis ? fact?.cpa : selectedSummary.value?.cpa) ?? null,
    cpaChange:
      (isAnalysis ? fact?.cpa_change : selectedSummary.value?.cpaChange) ??
      null,
    registrations:
      (isAnalysis
        ? fact?.registrations
        : selectedSummary.value?.registrations) ?? null,
    registrationsChange:
      (isAnalysis
        ? fact?.registrations_change
        : selectedSummary.value?.registrationsChange) ?? null,
    spend: (isAnalysis ? fact?.spend : selectedSummary.value?.spend) ?? null,
    spendChange:
      (isAnalysis ? fact?.spend_change : selectedSummary.value?.spendChange) ??
      null,
    labels: trendPoints.value.map((point) => point.label),
    spendSeries: trendPoints.value.map((point) => point.spend),
    conversions: trendPoints.value.map((point) => point.registrations),
  };
});
const comparisonLabel = computed(() =>
  range.value === 'today' ? '较昨日' : '较上个等长周期',
);
const trendRangeLabel = computed(() => {
  if (dashboardMode.value === 'overview') {
    return `北京时间 · ${range.value === 'today' ? '小时走势' : '每日走势'} · USD`;
  }
  return trendData.value?.cumulative
    ? '账户本地时刻 · 当日累计快照'
    : '账户本地日期 · 每日汇总';
});
const accountActivity = computed(
  () =>
    accountsData.value?.activity ?? {
      active: 0,
      attention: 0,
      idle: 0,
      rate: 0,
      scopeLabel: '本人投放账户',
      total: 0,
      unknown: 0,
    },
);
const accountActivityDescription =
  '统计本人在所选日期有投放数据的账户；状态正常且有消耗为活跃，停用、账单未清、风控或关闭为需关注，未同步状态单独列为未知。';

function formatCurrency(
  value: null | number,
  compact = false,
  currency = dashboardMode.value === 'overview'
    ? 'USD'
    : selectedCurrency.value,
) {
  if (value === null) return '—';
  const amount = new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: 2,
    notation: compact ? 'compact' : 'standard',
  }).format(value);
  return `${currency || '未知币种'} ${amount}`;
}
function formatSignedPercent(value: null | number, digits = 1) {
  return value === null
    ? '无可比基数'
    : `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
}
const metrics = computed(() => [
  {
    label: '消耗',
    value: formatCurrency(snapshot.value.spend, true),
    change: `${comparisonLabel.value} ${formatSignedPercent(snapshot.value.spendChange)}`,
    icon: 'lucide:wallet-cards',
    tone: 'blue',
    changeTone: 'blue',
  },
  {
    label: '注册',
    value: snapshot.value.registrations?.toLocaleString('en-US') ?? '—',
    change: `${comparisonLabel.value} ${formatSignedPercent(snapshot.value.registrationsChange)}`,
    icon: 'lucide:user-round-plus',
    tone: 'emerald',
    changeTone: 'emerald',
  },
  {
    label: 'CPA（注册成本）',
    value: formatCurrency(snapshot.value.cpa),
    change: `${comparisonLabel.value} ${formatSignedPercent(snapshot.value.cpaChange)}`,
    icon: 'lucide:target',
    tone: 'orange',
    changeTone: (snapshot.value.cpaChange ?? 0) <= 0 ? 'emerald' : 'orange',
  },
]);
const detailEmptyDescription = computed(() => {
  if (!analysisAccountId.value) {
    if (dashboardLoading.value) return '正在加载广告账户…';
    return dashboardError.value
      ? '账户加载失败，请点击页头重试'
      : '当前日期暂无本人广告账户';
  }
  if (detailError.value) return '系列成效加载失败，请重试';
  return detailLoading.value
    ? '正在加载系列成效…'
    : '该账户在当前窗口暂无系列数据';
});
const recommendationStyles = {
  bid_review: { tone: 'orange', icon: 'lucide:sliders-horizontal' },
  budget: { tone: 'emerald', icon: 'lucide:badge-dollar-sign' },
  observe: { tone: 'blue', icon: 'lucide:timer-reset' },
};
const recommendations = computed(() =>
  (agentAnalysis.value?.analysis.actions ?? []).map((action, index) => ({
    ...action,
    ...recommendationStyles[action.kind],
    key: `${index}-${action.target}`,
    account: action.target,
    evidence: action.reason,
    rule: action.expected,
  })),
);
const attentionCount = computed(
  () => recommendations.value.filter((row) => row.kind === 'bid_review').length,
);

function toSvgPoints(values: number[], max: number) {
  return values
    .map(
      (value, index) =>
        `${((index / Math.max(values.length - 1, 1)) * 720).toFixed(1)},${(211 - (value / Math.max(max, 1)) * 202).toFixed(1)}`,
    )
    .join(' ');
}
const trendChart = computed(() => {
  const spendMax = Math.max(0, ...snapshot.value.spendSeries);
  const conversionMax = Math.max(0, ...snapshot.value.conversions);
  const spendPoints = toSvgPoints(snapshot.value.spendSeries, spendMax);
  return {
    conversionPoints: toSvgPoints(snapshot.value.conversions, conversionMax),
    spendArea: `${spendPoints} 720,230 0,230`,
    spendPoints,
    ticks: [1, 0.75, 0.5, 0.25, 0].map((part) =>
      formatCurrency(part * spendMax, true),
    ),
    conversionTicks: [1, 0.75, 0.5, 0.25, 0].map((part) =>
      Math.round(part * conversionMax).toLocaleString(),
    ),
  };
});
function getFocusStatusColor(status: unknown) {
  if (status === '需处理') return 'error';
  if (status === '表现良好') return 'success';
  return 'default';
}
function getRecommendationColor(kind?: DashboardActionKind) {
  if (kind === 'budget') return 'success';
  if (kind === 'bid_review') return 'warning';
  return kind === 'observe' ? 'processing' : 'default';
}
function showEvidence(name: string, reason?: string) {
  Modal.info({
    title: `${name} · 分析依据`,
    content: reason || '智能体未提供依据。',
    okText: '知道了',
  });
}
const focusColumns = [
  {
    align: 'left' as const,
    dataIndex: 'name',
    key: 'name',
    title: '代理线（广告系列）',
    width: 240,
  },
  {
    align: 'left' as const,
    dataIndex: 'spend',
    key: 'spend',
    title: '消耗',
    customRender: ({
      text,
      record,
    }: {
      record: DashboardCampaignPerformance;
      text: null | number;
    }) => formatCurrency(text, false, record.currency),
  },
  {
    align: 'left' as const,
    dataIndex: 'ctr',
    key: 'ctr',
    title: 'CTR',
    customRender: ({ text }: { text: null | number }) =>
      text === null ? '—' : `${(text * 100).toFixed(2)}%`,
  },
  {
    align: 'left' as const,
    dataIndex: 'cpa',
    key: 'cpa',
    title: 'CPA',
    customRender: ({
      text,
      record,
    }: {
      record: DashboardCampaignPerformance;
      text: null | number;
    }) => formatCurrency(text, false, record.currency),
  },
  {
    align: 'left' as const,
    dataIndex: 'status',
    key: 'status',
    title: '投放状态',
  },
  { align: 'left' as const, key: 'decision', title: '下一步' },
  { align: 'left' as const, key: 'analysis', title: '操作', width: 180 },
];
let requestId = 0;
async function loadDashboard() {
  const currentRequest = ++requestId;
  dashboardLoading.value = true;
  dashboardError.value = '';
  overviewData.value = null;
  accountsData.value = null;
  trendData.value = null;
  try {
    const [overview, accounts, trend] = await Promise.all([
      myDashboardService.overview(dashboardDateRange.value),
      myDashboardService.accounts(dashboardDateRange.value),
      myDashboardService.trend(dashboardDateRange.value),
    ]);
    if (currentRequest !== requestId) return false;
    overviewData.value = overview;
    accountsData.value = accounts;
    if (!accounts.items.some((row) => row.id === analysisAccountId.value)) {
      analysisAccountId.value = accounts.items[0]?.id;
    }
    trendData.value = trend;
    if (
      !overview.summaries.some((row) => row.currency === selectedCurrency.value)
    ) {
      selectedCurrency.value =
        overview.summaries.find((row) => row.currency === 'USD')?.currency ??
        overview.summaries[0]?.currency ??
        '';
    }
    return true;
  } catch {
    if (currentRequest === requestId)
      dashboardError.value = '指挥台数据加载失败，请重试。';
    return false;
  } finally {
    if (currentRequest === requestId) dashboardLoading.value = false;
  }
}
async function refreshDashboard() {
  if (refreshLoading.value) return;
  const today = currentReportDate();
  if (anchorDate.value !== today) {
    anchorDate.value = today;
    return;
  }
  refreshLoading.value = true;
  try {
    const results = await Promise.all([
      loadDashboard(),
      loadAnalysis(),
      refreshDetails(),
      workspace.value?.refresh() ?? true,
    ]);
    if (results.every(Boolean)) message.success('投放数据已刷新');
  } finally {
    refreshLoading.value = false;
  }
}
async function saveAutomation() {
  if (await saveHosting()) {
    automationDrawerOpen.value = false;
    message.success('托管设置已保存');
  }
}
watch(automationDrawerOpen, (open) => {
  if (open) void loadHosting();
});
watch(dashboardDateRange, loadDashboard, { immediate: true });
</script>

<template>
  <Page auto-content-height class="my-dashboard-page bg-slate-50">
    <main class="mx-auto flex max-w-[1680px] flex-col gap-4 px-1 pb-7">
      <section
        class="flex flex-col justify-between gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm lg:flex-row lg:items-center"
        aria-labelledby="my-dashboard-title"
      >
        <div class="min-w-0">
          <div class="mb-2 flex items-center gap-2 text-sm text-slate-500">
            <IconifyIcon icon="lucide:chart-no-axes-combined" />
            <span>数据复盘</span><span>/</span><span>我的看板</span>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <h1
              id="my-dashboard-title"
              class="m-0 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white"
            >
              我的投放指挥台
            </h1>
            <Tag color="blue" class="!m-0 !rounded-full !px-3 !py-0.5">
              {{ operatorName }} · {{ accountActivity.scopeLabel }}
            </Tag>
          </div>
          <p class="mb-0 mt-2 text-sm text-slate-600 dark:text-slate-400">
            先看当前投放结果，再按证据决定复核出价策略、提交预算建议或继续观察；所有动作均需你确认后执行。
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Select
            v-model:value="range"
            :options="rangeOptions"
            aria-label="查询日期范围"
            class="w-28"
          />
          <Select
            v-if="dashboardMode === 'objects'"
            v-model:value="selectedCurrency"
            :options="currencyOptions"
            :disabled="currencyOptions.length === 0"
            aria-label="指标币种"
            placeholder="指标币种"
            class="w-32"
          />
          <Button
            :loading="refreshLoading || metricsLoading || detailLoading"
            @click="refreshDashboard"
          >
            <IconifyIcon icon="lucide:refresh-cw" class="mr-1" />刷新数据
          </Button>
          <Button type="primary" @click="automationDrawerOpen = true">
            <IconifyIcon icon="lucide:settings-2" class="mr-1" />托管设置
          </Button>
        </div>
      </section>

      <Alert
        v-if="dashboardError"
        :message="dashboardError"
        show-icon
        type="error"
      >
        <template #action>
          <Button :loading="dashboardLoading" @click="refreshDashboard">
            重试
          </Button>
        </template>
      </Alert>
      <Alert
        v-if="dashboardMode === 'overview' && analysisError"
        :message="analysisError"
        type="error"
        show-icon
      >
        <template #action>
          <Button :loading="analysisLoading" @click="loadAnalysis">
            重试分析
          </Button>
        </template>
      </Alert>
      <p class="text-muted-foreground m-0 text-xs" role="status">
        数据范围：仅本人投放数据（所有角色适用） ·
        {{
          dashboardMode === 'overview'
            ? '态势分析按北京时间、美元统计；账户活跃度按账户本地日期统计'
            : '按账户本地日期统计，金额按币种分别展示'
        }}
      </p>
      <section aria-label="当前投放核心指标" :aria-busy="metricsLoading">
        <div class="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          <Card
            v-for="metric in metrics"
            :key="metric.label"
            :bordered="false"
            :loading="metricsLoading"
            class="metric-card"
            :class="`metric-${metric.tone}`"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <span class="text-sm text-slate-500">{{ metric.label }}</span>
                <strong
                  class="mt-2 block text-2xl font-semibold text-slate-900"
                >
                  {{ metric.value }}
                </strong>
              </div>
              <span class="metric-icon"
                ><IconifyIcon :icon="metric.icon"
              /></span>
            </div>
            <span
              class="mt-4 inline-flex items-center gap-1 text-xs"
              :class="`metric-change-${metric.changeTone}`"
            >
              <IconifyIcon
                :icon="
                  metric.change.includes('-')
                    ? 'lucide:trending-down'
                    : 'lucide:trending-up'
                "
              />
              {{ metric.change }}
            </span>
          </Card>

          <Card
            :bordered="false"
            :loading="dashboardLoading"
            aria-labelledby="account-activity-title"
            class="account-activity-card metric-card metric-violet"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-center gap-1.5">
                  <span
                    id="account-activity-title"
                    class="text-sm text-slate-500"
                  >
                    账户活跃度
                  </span>
                  <Tooltip :title="accountActivityDescription">
                    <button
                      :aria-label="`账户活跃度计算说明：${accountActivityDescription}`"
                      class="activity-help-button"
                      type="button"
                    >
                      <IconifyIcon icon="lucide:circle-help" />
                    </button>
                  </Tooltip>
                </div>
                <strong
                  class="mt-1.5 block text-2xl font-semibold text-slate-900"
                >
                  {{ accountActivity.rate
                  }}<span class="ml-0.5 text-base">%</span>
                </strong>
              </div>
              <span class="metric-icon" aria-hidden="true">
                <IconifyIcon icon="lucide:activity" />
              </span>
            </div>
            <div
              :aria-label="`账户活跃度 ${accountActivity.rate}%`"
              :aria-valuenow="accountActivity.rate"
              :aria-valuetext="`${accountActivity.active} / ${accountActivity.total} 个账户有消耗且状态正常`"
              aria-valuemax="100"
              aria-valuemin="0"
              class="activity-meter mt-3"
              role="progressbar"
            >
              <span
                :style="{ transform: `scaleX(${accountActivity.rate / 100})` }"
              ></span>
            </div>
            <p
              class="mb-0 mt-2 text-xs leading-5 text-slate-600"
              aria-live="polite"
            >
              {{ accountActivity.active }} /
              {{ accountActivity.total }} 个账户有消耗且状态正常
            </p>
            <div
              class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
            >
              <span class="activity-status activity-status-attention">
                需关注 {{ accountActivity.attention }}
              </span>
              <span class="activity-status activity-status-idle">
                无消耗 {{ accountActivity.idle }} · 未知
                {{ accountActivity.unknown }}
              </span>
            </div>
          </Card>
        </div>
      </section>

      <nav
        aria-label="我的看板内容"
        class="mb-4 flex items-center gap-5 border-b border-slate-200"
      >
        <button
          :aria-pressed="dashboardMode === 'objects'"
          class="border-b-2 border-transparent px-1 pb-2 text-sm font-medium text-slate-500 transition-colors hover:text-blue-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          :class="{
            'border-blue-600 text-blue-600': dashboardMode === 'objects',
          }"
          type="button"
          @click="dashboardMode = 'objects'"
        >
          投放对象
        </button>
        <button
          :aria-pressed="dashboardMode === 'overview'"
          class="border-b-2 border-transparent px-1 pb-2 text-sm font-medium text-slate-500 transition-colors hover:text-blue-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          :class="{
            'border-blue-600 text-blue-600': dashboardMode === 'overview',
          }"
          type="button"
          @click="dashboardMode = 'overview'"
        >
          态势与建议
        </button>
      </nav>

      <DeliveryObjectWorkspace
        v-if="dashboardMode === 'objects'"
        ref="workspace"
        v-model:account-id="analysisAccountId"
        :accounts="accountsData?.items ?? []"
        :accounts-loading="dashboardLoading"
        :accounts-error="dashboardError"
        :end-date="dashboardDateRange.endDate"
        :start-date="dashboardDateRange.startDate"
      />

      <section
        v-if="dashboardMode === 'overview'"
        class="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.85fr)]"
        aria-label="投放数据与优先动作"
      >
        <Card
          :bordered="false"
          :loading="metricsLoading"
          class="min-w-0 overflow-hidden shadow-sm"
        >
          <template #title>
            <div class="flex items-center gap-2">
              <IconifyIcon icon="lucide:chart-spline" class="text-blue-600" />
              <span>当前投放态势</span>
            </div>
          </template>
          <template #extra>
            <span class="text-xs text-slate-400">{{ trendRangeLabel }}</span>
          </template>

          <Alert
            v-if="agentAnalysis?.analysis.headline"
            :message="agentAnalysis.analysis.headline"
            :description="
              [agentAnalysis.analysis.anomaly, agentAnalysis.analysis.locate]
                .filter(Boolean)
                .join(' · ')
            "
            type="info"
            show-icon
            class="mb-4"
          />
          <div class="grid gap-3 sm:grid-cols-3">
            <div class="snapshot-cell">
              <span>当前范围消耗</span>
              <strong>{{ formatCurrency(snapshot.spend, true) }}</strong>
              <small
                >{{ comparisonLabel }}
                {{ formatSignedPercent(snapshot.spendChange) }}</small
              >
            </div>
            <div class="snapshot-cell">
              <span>当前范围注册</span>
              <strong>{{
                snapshot.registrations?.toLocaleString('en-US') ?? '—'
              }}</strong>
              <small
                >{{ comparisonLabel }}
                {{ formatSignedPercent(snapshot.registrationsChange) }}</small
              >
            </div>
            <div class="snapshot-cell snapshot-cell-violet">
              <span>本轮判断基准 CPA</span>
              <strong>{{ formatCurrency(snapshot.cpa) }}</strong>
              <small>智能体返回的本期注册成本</small>
            </div>
          </div>

          <Empty
            v-if="trendPoints.length === 0"
            description="当前日期范围暂无趋势数据"
          />
          <div v-else class="trend-wrap mt-5">
            <div class="trend-labels" aria-hidden="true">
              <span v-for="(tick, index) in trendChart.ticks" :key="index">{{
                tick
              }}</span>
            </div>
            <div
              class="trend-area"
              :aria-label="`${trendRangeLabel}：消耗与注册走势`"
              role="img"
            >
              <svg
                viewBox="0 0 720 230"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <defs>
                  <linearGradient
                    id="spend-gradient"
                    x1="0"
                    x2="0"
                    y1="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stop-color="#3b82f6"
                      stop-opacity="0.25"
                    />
                    <stop offset="100%" stop-color="#3b82f6" stop-opacity="0" />
                  </linearGradient>
                </defs>
                <polygon
                  :points="trendChart.spendArea"
                  fill="url(#spend-gradient)"
                />
                <polyline
                  :points="trendChart.spendPoints"
                  fill="none"
                  stroke="#2563eb"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="4"
                />
                <polyline
                  :points="trendChart.conversionPoints"
                  fill="none"
                  stroke="#10b981"
                  stroke-dasharray="7 7"
                  stroke-linecap="round"
                  stroke-width="3"
                />
                <circle
                  v-for="(point, index) in trendPoints"
                  :key="point.label"
                  :cx="(index / Math.max(trendPoints.length - 1, 1)) * 720"
                  :cy="
                    211 -
                    (point.spend / Math.max(1, ...snapshot.spendSeries)) * 202
                  "
                  r="4"
                  fill="#2563eb"
                >
                  <title>
                    {{ point.label }}：{{ formatCurrency(point.spend) }}，{{
                      point.registrations
                    }}
                    注册
                  </title>
                </circle>
              </svg>
              <div class="trend-x-axis">
                <span v-for="label in snapshot.labels" :key="label">{{
                  label
                }}</span>
              </div>
            </div>
          </div>
          <div
            v-if="trendPoints.length > 0"
            class="text-muted-foreground mt-2 flex flex-wrap gap-2 text-xs"
          >
            <span
              v-for="point in trendPoints"
              :key="point.label"
              :title="`${point.label}：消耗 ${formatCurrency(point.spend)}，注册 ${point.registrations}`"
              >{{ point.label }}：{{ formatCurrency(point.spend) }} /
              {{ point.registrations }} 注册</span
            >
          </div>
          <div class="mt-5 flex flex-wrap gap-5 text-sm text-slate-500">
            <span><i class="legend-dot legend-blue"></i>消耗</span>
            <span><i class="legend-dot legend-green"></i>注册走势</span>
            <span class="ml-auto text-xs text-slate-400"
              >注册曲线使用独立刻度；具体数值见趋势明细</span
            >
          </div>
        </Card>

        <aside class="flex min-w-0 flex-col gap-4" aria-label="优先动作与托管">
          <Card
            :bordered="false"
            :loading="metricsLoading"
            class="action-queue-card overflow-hidden"
          >
            <template #title>
              <div class="flex flex-wrap items-center gap-2">
                <IconifyIcon icon="lucide:radar" class="text-violet-600" />
                <span>优先动作队列</span>
                <Tag color="purple" class="!m-0">
                  {{ attentionCount }} 项先诊断
                </Tag>
              </div>
            </template>
            <template #extra>
              <span class="text-xs text-slate-400">基于当前看板数据</span>
            </template>
            <p class="mb-3 text-xs leading-5 text-slate-500">
              先按数据证据判断，再复核出价策略、提交预算建议或保持观察；系统不会自动执行账户变更。
            </p>
            <Empty
              v-if="!analysisLoading && recommendations.length === 0"
              :description="
                analysisError ? '本轮分析未完成' : '当前窗口暂无分析建议'
              "
            />
            <article
              v-for="recommendation in recommendations.slice(0, 3)"
              :key="recommendation.key"
              class="action-item"
              :class="`action-item-${recommendation.tone}`"
            >
              <span class="action-icon"
                ><IconifyIcon :icon="recommendation.icon"
              /></span>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <strong>{{ recommendation.action }}</strong>
                  <Tag
                    :color="
                      recommendation.tone === 'emerald'
                        ? 'success'
                        : recommendation.tone === 'orange'
                          ? 'warning'
                          : 'processing'
                    "
                    class="!m-0"
                  >
                    {{ recommendation.label }}
                  </Tag>
                </div>
                <p class="action-account">{{ recommendation.account }}</p>
                <p>{{ recommendation.evidence }}</p>
                <div class="action-rule">{{ recommendation.rule }}</div>

                <Button
                  type="link"
                  class="!p-0"
                  @click="
                    showEvidence(recommendation.target, recommendation.reason)
                  "
                >
                  查看分析依据 →
                </Button>
              </div>
            </article>
          </Card>

          <Card
            :bordered="false"
            :loading="metricsLoading"
            class="automation-card overflow-hidden"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="flex items-center gap-2">
                <span class="automation-icon"
                  ><IconifyIcon icon="lucide:bot"
                /></span>
                <div>
                  <strong class="block text-base text-slate-900"
                    >自动化托管</strong
                  >
                  <span class="text-xs text-slate-500"
                    >整窗监测，飞书私聊提醒</span
                  >
                </div>
              </div>
              <Switch
                v-if="hosting"
                disabled
                :checked="automation.enabled"
                checked-children="已开启"
                un-checked-children="已关闭"
              />
            </div>
            <div
              class="mt-4 rounded-xl border p-3"
              :class="
                automation.enabled
                  ? 'border-blue-100 bg-blue-50/70'
                  : 'border-slate-100 bg-slate-50'
              "
            >
              <div class="flex items-center justify-between gap-3 text-sm">
                <span class="text-slate-600">当前状态</span>
                <Tag
                  :color="automation.enabled ? 'processing' : 'default'"
                  class="!m-0"
                >
                  {{
                    hosting
                      ? automation.enabled
                        ? '托管中 · 飞书提醒'
                        : '人工监测'
                      : '打开设置查看'
                  }}
                </Tag>
              </div>
              <p class="mb-0 mt-2 text-xs leading-5 text-slate-500">
                {{
                  automation.enabled
                    ? `消耗环比绝对值达到 ${automation.spendChangeThreshold}%，或出现复核出价策略的建议时，会推送飞书提醒；不会自动修改预算或出价。`
                    : '打开托管设置查看当前配置；开启后按所选节奏推送飞书提醒。'
                }}
              </p>
            </div>
            <Button class="mt-4 w-full" @click="automationDrawerOpen = true">
              配置托管规则
            </Button>
          </Card>
        </aside>
      </section>

      <section
        class="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.85fr)]"
        aria-label="账户分析与投放建议"
      >
        <Card
          :bordered="false"
          class="min-w-0 shadow-sm"
          aria-labelledby="account-detail-title"
        >
          <template #title>
            <div class="flex flex-wrap items-center gap-2">
              <IconifyIcon icon="lucide:crosshair" class="text-blue-600" />
              <span id="account-detail-title">账户与代理线投放明细</span>
              <Tag color="blue" class="!m-0">
                当前范围 {{ detailTotal }} 项
              </Tag>
            </div>
          </template>
          <template #extra>
            <div class="flex flex-wrap items-center justify-end gap-2">
              <span class="text-xs text-slate-400"
                >账户时区 · 账户原币种 · 按消耗排序</span
              >
              <Button
                v-if="analysisAccountId"
                :loading="detailLoading"
                @click="refreshDetails"
              >
                刷新成效
              </Button>
            </div>
          </template>
          <Alert
            v-if="detailError"
            :message="detailError"
            type="error"
            show-icon
            class="mb-3"
          />
          <Table
            :columns="focusColumns"
            :data-source="focusRows"
            :pagination="{
              current: detailPage,
              pageSize: detailPageSize,
              total: detailTotal,
              showSizeChanger: true,
              onChange: changeDetailPage,
            }"
            :loading="detailLoading"
            :scroll="{ x: 1000 }"
            row-key="id"
          >
            <template #emptyText>
              <Empty :description="detailEmptyDescription" />
            </template>
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <Tag
                  v-if="record.analysisState === 'loading'"
                  color="processing"
                  class="!m-0"
                >
                  分析中
                </Tag>
                <Tag
                  v-else-if="record.analysisState === 'error'"
                  color="warning"
                  class="!m-0"
                >
                  分析失败
                </Tag>
                <Tag
                  v-else-if="record.status"
                  :color="getFocusStatusColor(record.status)"
                  class="!m-0"
                >
                  {{ record.status }}
                </Tag>
                <span v-else class="text-slate-500">{{
                  record.analysisState === 'success' ? '未提供' : '待分析'
                }}</span>
              </template>
              <div
                v-else-if="column.key === 'decision'"
                class="flex flex-col items-start gap-1"
              >
                <Tag
                  v-if="record.action"
                  :color="getRecommendationColor(record.kind)"
                  class="!m-0"
                >
                  {{ record.action }}
                </Tag>
                <span v-else>—</span>
                <Button
                  v-if="record.reason"
                  type="link"
                  class="!p-0 !text-xs"
                  @click="showEvidence(record.name, record.reason)"
                >
                  查看依据
                </Button>
              </div>
              <div
                v-else-if="column.key === 'analysis'"
                class="flex flex-col items-start gap-1"
              >
                <Button
                  :loading="record.analysisState === 'loading'"
                  :aria-label="`分析 ${record.name}`"
                  @click="analyzeCampaign(record.id)"
                >
                  {{
                    record.analysisState === 'error'
                      ? '重试'
                      : record.analysisState === 'success'
                        ? '重新分析'
                        : '分析'
                  }}
                </Button>
                <span
                  v-if="record.analysisError"
                  class="text-xs text-red-600"
                  role="alert"
                  >{{ record.analysisError }}</span
                >
              </div>
            </template>
          </Table>
        </Card>

        <aside class="flex min-w-0 flex-col gap-4" aria-label="投放决策护栏">
          <Card :bordered="false" class="guardrail-card shadow-sm">
            <template #title>
              <div class="flex items-center gap-2">
                <IconifyIcon
                  icon="lucide:shield-check"
                  class="text-emerald-600"
                />
                <span>出价与预算决策护栏</span>
              </div>
            </template>
            <div class="guardrail-item guardrail-bid">
              <span><IconifyIcon icon="lucide:sliders-horizontal" /></span>
              <div>
                <strong>什么时候复核出价策略</strong>
                <p>
                  CPA 高于看板基准 ≥20%，且 CTR
                  低于账户中位数时，进入诊断；任何调整仍需人工确认。
                </p>
              </div>
            </div>
            <div class="guardrail-item guardrail-budget">
              <span><IconifyIcon icon="lucide:badge-dollar-sign" /></span>
              <div>
                <strong>什么时候提交预算建议</strong>
                <p>
                  CPA 低于基准 ≥5%、CTR 不低于中位数时，可提交单次 20%、最多 30%
                  的加额建议。
                </p>
              </div>
            </div>
            <div class="guardrail-item guardrail-observe">
              <span><IconifyIcon icon="lucide:timer-reset" /></span>
              <div>
                <strong>什么时候先不动</strong>
                <p>
                  未达到阈值或仍在学习期时，不同时调整出价和预算；等待学习期后复核。
                </p>
              </div>
            </div>
          </Card>

          <Card :bordered="false" :loading="detailLoading" class="shadow-sm">
            <div class="mb-3 flex items-center justify-between">
              <div>
                <strong class="text-base text-slate-800">本轮建议概览</strong>
                <p class="mb-0 mt-1 text-xs text-slate-500">
                  已分析 {{ detailRecommendationCounts.analyzed }} /
                  {{ detailTotal }} 条系列
                </p>
              </div>
              <span
                v-if="detailRecommendationCounts.analyzed"
                class="text-sm font-medium"
                >{{ detailRecommendationCounts.total }} 项</span
              >
            </div>

            <Empty
              v-if="detailTotal === 0 || detailError"
              :description="detailEmptyDescription"
            />
            <Empty
              v-else-if="detailRecommendationCounts.analyzed === 0"
              description="点击系列行的“分析”，生成投放建议"
            />
            <div v-else class="mt-4 space-y-3 text-sm">
              <div class="flex items-center justify-between gap-4">
                <span class="text-slate-500">优先复核出价策略</span>
                <span class="font-medium text-amber-600"
                  >{{ detailRecommendationCounts.bidReview }} 项</span
                >
              </div>
              <div class="flex items-center justify-between gap-4">
                <span class="text-slate-500">可提交预算建议</span>
                <span class="font-medium text-emerald-600"
                  >{{ detailRecommendationCounts.budget }} 项</span
                >
              </div>
              <div class="flex items-center justify-between gap-4">
                <span class="text-slate-500">保持观察</span>
                <span class="font-medium text-slate-700"
                  >{{ detailRecommendationCounts.observe }} 项</span
                >
              </div>
            </div>
          </Card>
        </aside>
      </section>
    </main>

    <Drawer
      v-model:open="automationDrawerOpen"
      root-class-name="ux-fixed-drawer"
      :width="440"
      :closable="!hostingSaving"
      :mask-closable="!hostingSaving"
      :keyboard="!hostingSaving"
      title="自动化托管设置"
    >
      <div class="space-y-6" :aria-busy="hostingLoading || hostingSaving">
        <p class="text-sm leading-6 text-slate-600">
          监测本人所选时间窗口，不受明细表账户筛选影响。达到提醒条件时推送飞书私聊，不会自动修改预算或出价。
        </p>
        <Alert
          v-if="hostingError"
          :message="hostingError"
          type="error"
          show-icon
        >
          <template v-if="!hostingLoaded" #action>
            <Button :loading="hostingLoading" @click="loadHosting">
              重新读取
            </Button>
          </template>
        </Alert>
        <Alert
          v-if="hosting?.feishu_bound === false"
          message="需要先绑定飞书，才能把托管分析推给你。"
          type="warning"
          show-icon
        />
        <p v-if="hostingLoading" role="status">正在读取托管设置…</p>
        <div class="flex items-center justify-between gap-4">
          <label for="dashboard-hosting-enabled" class="font-medium"
            >开启自动化托管</label
          >
          <Switch
            id="dashboard-hosting-enabled"
            v-model:checked="hostingDraft.enabled"
            :disabled="
              !hostingLoaded ||
              hostingSaving ||
              (hosting?.feishu_bound === false && !hostingDraft.enabled)
            "
          />
        </div>
        <div class="space-y-2 text-sm font-medium text-slate-700">
          <label for="dashboard-hosting-range">监测窗口</label>
          <Select
            id="dashboard-hosting-range"
            v-model:value="hostingDraft.range"
            :options="rangeOptions"
            :disabled="!hostingLoaded || hostingSaving || !hostingDraft.enabled"
            class="w-full"
          />
        </div>
        <div class="space-y-2 text-sm font-medium text-slate-700">
          <label for="dashboard-hosting-threshold">消耗波动提醒阈值</label>
          <InputNumber
            id="dashboard-hosting-threshold"
            v-model:value="hostingDraft.spend_change_threshold"
            :disabled="!hostingLoaded || hostingSaving || !hostingDraft.enabled"
            :max="100"
            :min="5"
            :precision="0"
            addon-after="%"
            class="w-full"
          />
        </div>
        <div class="space-y-2 text-sm font-medium text-slate-700">
          <label for="dashboard-hosting-cadence">提醒节奏</label>
          <Select
            id="dashboard-hosting-cadence"
            v-model:value="hostingDraft.cadence"
            :disabled="!hostingLoaded || hostingSaving || !hostingDraft.enabled"
            :options="[
              { label: '实时提醒', value: 'realtime' },
              { label: '每小时汇总', value: 'hourly' },
            ]"
            class="w-full"
          />
        </div>
        <Button
          type="primary"
          class="w-full"
          :loading="hostingSaving"
          :disabled="
            !hostingLoaded ||
            hostingLoading ||
            (hostingDraft.enabled && hosting?.feishu_bound === false)
          "
          @click="saveAutomation"
        >
          保存托管设置
        </Button>
      </div>
    </Drawer>
  </Page>
</template>

<style scoped>
.metric-card {
  min-height: 154px;
  border: 1px solid #eef2f7;
  border-radius: 16px;
  box-shadow: 0 6px 20px rgb(15 23 42 / 4%);
}
.metric-icon,
.automation-icon,
.action-icon,
.guardrail-item > span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
}
.metric-icon {
  width: 42px;
  height: 42px;
  font-size: 20px;
}
.metric-blue .metric-icon {
  background: #e9f1ff;
  color: #2563eb;
}
.metric-emerald .metric-icon {
  background: #e8fbf2;
  color: #059669;
}
.metric-orange .metric-icon {
  background: #fff5e8;
  color: #d97706;
}
.metric-violet .metric-icon {
  background: #f2edff;
  color: #7c3aed;
}
.metric-change-blue {
  color: #2563eb;
}
.metric-change-emerald {
  color: #059669;
}
.metric-change-orange {
  color: #d97706;
}
.account-activity-card {
  min-height: 154px;
}
.activity-help-button {
  display: inline-flex;
  width: 18px;
  height: 18px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #64748b;
  cursor: help;
  font-size: 15px;
}
.activity-help-button:hover {
  color: #5b21b6;
}
.activity-help-button:focus-visible {
  outline: 2px solid #7c3aed;
  outline-offset: 2px;
}
.activity-meter {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #ede9fe;
}
.activity-meter > span {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #7c3aed, #a78bfa);
  transform-origin: left center;
  transition: transform 180ms ease-out;
}
.activity-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.activity-status::before {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  content: '';
}
.activity-status-attention {
  color: #c2410c;
}
.activity-status-attention::before {
  background: #f97316;
}
.activity-status-idle {
  color: #64748b;
}
.activity-status-idle::before {
  background: #94a3b8;
}
.snapshot-cell {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid #e8edf5;
  border-radius: 12px;
  background: #f8fbff;
}
.snapshot-cell > span,
.snapshot-cell > small {
  display: block;
  color: #64748b;
  font-size: 12px;
}
.snapshot-cell > strong {
  display: block;
  margin: 5px 0 2px;
  color: #1e3a5f;
  font-size: 19px;
  line-height: 1.25;
}
.snapshot-cell-violet {
  border-color: #e9e1ff;
  background: #fbfaff;
}
.snapshot-cell-violet > strong {
  color: #6d28d9;
}
.trend-wrap {
  display: flex;
  min-height: 255px;
  gap: 12px;
}
.trend-labels {
  display: flex;
  flex: none;
  flex-direction: column;
  justify-content: space-between;
  padding-bottom: 32px;
  color: #94a3b8;
  font-size: 12px;
}
.trend-area {
  position: relative;
  flex: 1;
  min-width: 0;
  border-bottom: 1px solid #e2e8f0;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0,
    transparent 56px,
    #edf2f7 57px
  );
}
.trend-area svg {
  display: block;
  width: 100%;
  height: 225px;
}
.trend-x-axis {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding-top: 7px;
  color: #94a3b8;
  font-size: 11px;
}
.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 999px;
}
.legend-blue {
  background: #2563eb;
}
.legend-green {
  background: #10b981;
}
.action-queue-card {
  border: 1px solid #eeeafe;
  box-shadow: 0 8px 24px rgb(76 29 149 / 5%);
}
.action-item {
  display: flex;
  gap: 11px;
  padding: 14px 0;
  border-top: 1px solid #edf0f5;
}
.action-item:first-of-type {
  padding-top: 4px;
  border-top: 0;
}
.action-icon {
  width: 30px;
  height: 30px;
  flex: none;
  margin-top: 1px;
}
.action-item-orange .action-icon {
  background: #fff3e5;
  color: #d97706;
}
.action-item-emerald .action-icon {
  background: #e8fbf2;
  color: #059669;
}
.action-item-blue .action-icon {
  background: #eaf3ff;
  color: #2563eb;
}
.action-item strong {
  color: #27364b;
  font-size: 14px;
}
.action-item p {
  margin: 5px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}
.action-item .action-account {
  margin-top: 3px;
  color: #334155;
  font-weight: 600;
}
.action-rule {
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  background: #f8fafc;
  color: #526277;
  font-size: 12px;
  line-height: 1.5;
}
.action-next {
  color: #334155 !important;
}
.automation-card {
  border: 1px solid #dbeafe;
  background: linear-gradient(145deg, #fff 20%, #f4f8ff);
}
.automation-icon {
  width: 38px;
  height: 38px;
  background: #e9f1ff;
  color: #2563eb;
}
.guardrail-card {
  border: 1px solid #e2f3eb;
}
.guardrail-item {
  display: flex;
  gap: 11px;
  padding: 12px 0;
  border-top: 1px solid #edf2f5;
}
.guardrail-item:first-of-type {
  padding-top: 2px;
  border-top: 0;
}
.guardrail-item > span {
  width: 30px;
  height: 30px;
  flex: none;
}
.guardrail-bid > span {
  background: #fff3e5;
  color: #d97706;
}
.guardrail-budget > span {
  background: #e8fbf2;
  color: #059669;
}
.guardrail-observe > span {
  background: #eaf3ff;
  color: #2563eb;
}
.guardrail-item strong {
  display: block;
  color: #334155;
  font-size: 13px;
}
.guardrail-item p {
  margin: 3px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}
:deep(.focus-account-row > td) {
  background: #eff6ff !important;
}
@media (max-width: 640px) {
  .trend-wrap {
    min-height: 210px;
  }
  .trend-area svg {
    height: 180px;
  }
  .trend-x-axis {
    overflow: hidden;
    white-space: nowrap;
  }
}
</style>
