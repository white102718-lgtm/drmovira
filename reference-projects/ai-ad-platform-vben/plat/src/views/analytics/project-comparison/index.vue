<script lang="ts" setup>
import type {
  ProjectComparisonMetric,
  ProjectComparisonMetricKey,
  ProjectComparisonOverview,
  ProjectComparisonQuery,
  ProjectComparisonReviewDraft,
} from '#/domain/project-comparison';

import {
  computed,
  nextTick,
  onMounted,
  reactive,
  ref,
  toRefs,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { EchartsUI, useEcharts } from '@vben/plugins/echarts';

import {
  Alert,
  Button,
  Card,
  DatePicker,
  Drawer,
  Empty,
  message,
  RadioButton,
  RadioGroup,
  Select,
  Spin,
  Table,
  Tag,
} from 'ant-design-vue';

import { isFusionDemoMode } from '#/api/fusion';
import { projectService } from '#/domain/project';
import {
  buildProjectComparisonReviewDraft,
  projectComparisonMetricConfigByKey,
  projectComparisonMetricConfigs,
  projectComparisonService,
} from '#/domain/project-comparison';
import { filterDemoProjects, getCurrentDemoActor } from '#/mock/demo-access';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

type RangeValue = [string, string];

const router = useRouter();
const route = useRoute();
const hasInitialComparisonState = [
  'comparison_date',
  'current_date',
  'granularity',
  'mode',
].some((key) => Object.hasOwn(route.query, key));
const overview = ref<null | ProjectComparisonOverview>(null);
const loading = ref(false);
const error = ref('');
const projectOptions = ref<Array<{ label: string; value: string }>>([]);
const availableAgencyLines = ref<
  Array<{ agencyLineId: string; name: string; platform: string }>
>([]);
const selectedAgencyLineIds = ref<string[]>([]);
const trendMetric = ref<ProjectComparisonMetricKey>('spend');
const creativeDirectionRankMetric = ref<ProjectComparisonMetricKey>('roas');
const creativeDirectionRankDirection = ref<'asc' | 'desc'>('desc');
const requestSerial = ref(0);
const reviewDrawerOpen = ref(false);
const chartRef = ref();
const { renderEcharts } = useEcharts(chartRef);

const filterState = reactive({
  comparisonRange: ['2026-08-13', '2026-08-13'] as RangeValue,
  currentRange: ['2026-08-14', '2026-08-14'] as RangeValue,
  granularity: 'hour' as 'day' | 'hour',
  mode: 'today' as 'custom' | 'last-7-days' | 'today',
  projectId: '',
});
const filterRefs = toRefs(filterState);
const routeStateReady = ref(false);
const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    comparisonRange: { key: 'comparison_date' },
    currentRange: { key: 'current_date' },
    projectId: { key: 'projectId' },
    selectedAgencyLineIds: { key: 'agency_line' },
  },
  onRouteStateRestored: () => {
    if (routeStateReady.value) return loadOverview();
  },
  state: createListRouteStateTarget({
    comparisonRange: filterRefs.comparisonRange,
    currentRange: filterRefs.currentRange,
    granularity: filterRefs.granularity,
    mode: filterRefs.mode,
    projectId: filterRefs.projectId,
    selectedAgencyLineIds,
  }),
});

const modeOptions = [
  { label: '今日 vs 昨日', value: 'today' },
  { label: '近 7 天 vs 前 7 天', value: 'last-7-days' },
  { label: '自定义对比', value: 'custom' },
];

const metricMap = computed(
  () => new Map(overview.value?.metrics.map((metric) => [metric.key, metric])),
);
const agencyLineOptions = computed(() =>
  availableAgencyLines.value.map((line) => ({
    label: `${line.name} · ${line.platform}`,
    value: line.agencyLineId,
  })),
);
const rankedAgencyLines = computed(() =>
  [...(overview.value?.agencyLines ?? [])].sort(
    (left, right) => (right.current.roas ?? 0) - (left.current.roas ?? 0),
  ),
);
const rankedCreativeDirections = computed(() => {
  const direction = creativeDirectionRankDirection.value === 'asc' ? 1 : -1;
  const key = creativeDirectionRankMetric.value;
  return [...(overview.value?.creativeDirections ?? [])].sort((left, right) => {
    const leftValue = left.current[key] ?? Number.NaN;
    const rightValue = right.current[key] ?? Number.NaN;
    if (Number.isNaN(leftValue)) return 1;
    if (Number.isNaN(rightValue)) return -1;
    if (leftValue === rightValue) return left.name.localeCompare(right.name);
    return (leftValue - rightValue) * direction;
  });
});
const trendPoints = computed(
  () => overview.value?.trends[trendMetric.value] ?? [],
);
const currentProject = computed(() => overview.value?.project);
const dataSourceDescription = computed(() => {
  const authority = overview.value?.dataQuality.authority;
  if (!authority) return '财务类指标当前为 Mock 演示投影。';
  return `正式 Read Model · ${authority.currency} · ${authority.timezone} · ${authority.attributionWindow} · ${authority.financialLedgerVersion}`;
});
const reviewDraft = computed<null | ProjectComparisonReviewDraft>(() =>
  overview.value ? buildProjectComparisonReviewDraft(overview.value) : null,
);

const rankingColumns = [
  { dataIndex: 'rank', key: 'rank', title: '排名', width: 72 },
  { dataIndex: 'name', key: 'name', title: '代理线' },
  { dataIndex: 'platform', key: 'platform', title: '平台', width: 110 },
  { dataIndex: 'spend', key: 'spend', title: '消耗', width: 130 },
  { dataIndex: 'roas', key: 'roas', title: 'ROAS', width: 100 },
  {
    dataIndex: 'firstPurchaseCost',
    key: 'firstPurchaseCost',
    title: '首充成本',
    width: 130,
  },
  {
    dataIndex: 'registrationCost',
    key: 'registrationCost',
    title: '注册成本',
    width: 130,
  },
];

const creativeDirectionRankingColumns = [
  { dataIndex: 'rank', key: 'rank', title: '排名', width: 72 },
  { dataIndex: 'name', key: 'name', title: '素材方向', width: 280 },
  { dataIndex: 'assetType', key: 'assetType', title: '类型', width: 90 },
  { dataIndex: 'agencyLineName', key: 'agencyLineName', title: '代理线' },
  {
    dataIndex: 'materialVersionCount',
    key: 'materialVersionCount',
    title: '素材版本',
    width: 104,
  },
  { dataIndex: 'spend', key: 'spend', title: '消耗', width: 130 },
  { dataIndex: 'roas', key: 'roas', title: 'ROAS', width: 100 },
  {
    dataIndex: 'firstPurchaseCost',
    key: 'firstPurchaseCost',
    title: '首充成本',
    width: 130,
  },
];

const creativeDirectionRankMetricOptions = [
  { label: '按 ROAS', value: 'roas' },
  { label: '按首充成本', value: 'firstPurchaseCost' },
  { label: '按注册成本', value: 'registrationCost' },
  { label: '按首充数', value: 'firstPurchases' },
  { label: '按消耗', value: 'spend' },
];

const creativeDirectionRankDirectionOptions = [
  { label: '由高到低', value: 'desc' },
  { label: '由低到高', value: 'asc' },
];

function metricConfig(key: ProjectComparisonMetricKey) {
  const config = projectComparisonMetricConfigByKey.get(key);
  if (!config) throw new Error(`未知环比指标：${key}`);
  return config;
}

function selectedMetric(
  key: ProjectComparisonMetricKey,
): ProjectComparisonMetric {
  return (
    metricMap.value.get(key) ?? {
      assessment: 'unknown',
      changeRate: null,
      comparison: null,
      current: null,
      difference: null,
      direction: 'flat',
      key,
      status: 'missing',
    }
  );
}

function directionMetric(
  metrics: Partial<Record<ProjectComparisonMetricKey, ProjectComparisonMetric>>,
  key: ProjectComparisonMetricKey,
) {
  return metrics[key] ?? selectedMetric(key);
}

function creativeAssetTypeLabel(type: 'image' | 'text' | 'video') {
  return { image: '图片', text: '文案', video: '视频' }[type];
}

function formatNumber(value: null | number, digits = 0) {
  if (value === null || Number.isNaN(value)) return '—';
  return value.toLocaleString('zh-CN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatMetric(key: ProjectComparisonMetricKey, value: null | number) {
  const config = metricConfig(key);
  if (value === null || Number.isNaN(value)) return '—';
  if (config.format === 'currency') {
    return `${currentProject.value?.currency ?? 'USD'} ${formatNumber(value, 2)}`;
  }
  if (config.format === 'percent') return `${formatNumber(value * 100, 2)}%`;
  if (config.format === 'ratio') return `${formatNumber(value, 2)}x`;
  return formatNumber(value, 0);
}

function formatDelta(metric: ProjectComparisonMetric) {
  if (metric.status === 'new') return '新增基线';
  if (metric.status === 'missing') return '数据缺失';
  if (metric.changeRate === null) return '—';
  return `${metric.changeRate >= 0 ? '+' : ''}${(metric.changeRate * 100).toFixed(1)}%`;
}

function deltaClass(metric: ProjectComparisonMetric) {
  if (metric.assessment === 'good') return 'text-emerald-600';
  if (metric.assessment === 'bad') return 'text-destructive';
  return 'text-muted-foreground';
}

function tagColor(metric: ProjectComparisonMetric) {
  if (metric.assessment === 'good') return 'green';
  if (metric.assessment === 'bad') return 'red';
  return 'default';
}

function buildQuery(): ProjectComparisonQuery {
  return {
    ...(selectedAgencyLineIds.value.length > 0
      ? { agencyLineIds: [...selectedAgencyLineIds.value] }
      : {}),
    comparison: {
      endDate: filterState.comparisonRange[1],
      startDate: filterState.comparisonRange[0],
    },
    current: {
      endDate: filterState.currentRange[1],
      startDate: filterState.currentRange[0],
    },
    granularity: filterState.granularity,
    mode: filterState.mode,
    projectId: filterState.projectId,
  };
}

function applyDefaultQuery(projectId: string, mode = filterState.mode) {
  const query = projectComparisonService.getDefaultQuery(projectId, mode);
  filterState.mode = query.mode;
  filterState.granularity = query.granularity;
  filterState.currentRange = [query.current.startDate, query.current.endDate];
  filterState.comparisonRange = [
    query.comparison.startDate,
    query.comparison.endDate,
  ];
}

async function copyReviewDraft() {
  const markdown = reviewDraft.value?.markdown;
  if (!markdown) return;
  if (!navigator.clipboard) {
    message.warning('当前浏览器不支持复制，请手动选择报告内容。');
    return;
  }
  try {
    await navigator.clipboard.writeText(markdown);
    message.success('复盘草稿已复制，可粘贴到项目日报或协作工具中校对。');
  } catch {
    message.error('复制失败，请手动选择报告内容。');
  }
}

async function loadOverview() {
  if (!filterState.projectId) return;
  const serial = ++requestSerial.value;
  loading.value = true;
  error.value = '';
  try {
    const next = await projectComparisonService.getOverview(buildQuery());
    if (serial !== requestSerial.value) return;
    overview.value = next;
    if (selectedAgencyLineIds.value.length === 0) {
      availableAgencyLines.value = next.agencyLines.map((line) => ({
        agencyLineId: line.agencyLineId,
        name: line.name,
        platform: line.platform,
      }));
    }
    selectedAgencyLineIds.value = selectedAgencyLineIds.value.filter((id) =>
      next.agencyLines.some((line) => line.agencyLineId === id),
    );
    await nextTick();
    renderTrendChart();
  } catch (error_) {
    if (serial !== requestSerial.value) return;
    overview.value = null;
    error.value =
      error_ instanceof Error ? error_.message : '环比分析数据加载失败';
  } finally {
    if (serial === requestSerial.value) loading.value = false;
  }
}

function renderTrendChart() {
  const points = trendPoints.value;
  const config = metricConfig(trendMetric.value);
  const color = '#1677ff';
  renderEcharts({
    color: [color, '#94a3b8'],
    grid: { bottom: 28, left: 44, right: 18, top: 36 },
    legend: { data: ['当前周期', '对比周期'], top: 0 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => formatMetric(trendMetric.value, Number(value)),
    },
    xAxis: {
      axisLabel: {
        color: '#64748b',
        formatter: (value: string) => value.slice(5),
      },
      data: points.map((point) => point.bucket),
      type: 'category',
    },
    yAxis: {
      axisLabel: {
        color: '#64748b',
        formatter: (value: number) =>
          config.format === 'percent'
            ? `${(value * 100).toFixed(0)}%`
            : formatNumber(value),
      },
      splitLine: { lineStyle: { color: '#e2e8f0' } },
      type: 'value',
    },
    series: [
      {
        areaStyle: { color: 'rgba(22, 119, 255, 0.08)' },
        data: points.map((point) => point.current),
        name: '当前周期',
        smooth: true,
        symbol: 'circle',
        type: 'line',
      },
      {
        data: points.map((point) => point.comparison),
        lineStyle: { type: 'dashed' },
        name: '对比周期',
        smooth: true,
        symbol: 'none',
        type: 'line',
      },
    ],
  });
}

async function applyQueryState() {
  await commitQueryState();
  await loadOverview();
}

async function handleModeChange() {
  if (!filterState.projectId) return;
  if (filterState.mode !== 'custom') applyDefaultQuery(filterState.projectId);
  await applyQueryState();
}

function handleCreativeDirectionRankMetricChange() {
  creativeDirectionRankDirection.value = metricConfig(
    creativeDirectionRankMetric.value,
  ).lowerIsBetter
    ? 'asc'
    : 'desc';
}

async function handleProjectChange() {
  if (!filterState.projectId) return;
  selectedAgencyLineIds.value = [];
  availableAgencyLines.value = [];
  applyDefaultQuery(filterState.projectId);
  await applyQueryState();
}

async function loadProjectOptions() {
  const result = await projectService.list({ page: 1, pageSize: 100 });
  const actor = isFusionDemoMode() ? getCurrentDemoActor() : undefined;
  const available = filterDemoProjects(actor, result.items);
  projectOptions.value = available.map((project) => ({
    label: `${project.name} · ${project.productName}`,
    value: project.id,
  }));
  const requestedProjectId = filterState.projectId;
  filterState.projectId = projectOptions.value.some(
    (option) => option.value === requestedProjectId,
  )
    ? requestedProjectId
    : (projectOptions.value[0]?.value ?? '');
  if (!filterState.projectId) {
    error.value = '当前身份没有可查看的项目。';
    return;
  }
  if (!hasInitialComparisonState) applyDefaultQuery(filterState.projectId);
  await commitQueryState();
  await loadOverview();
}

watch(trendMetric, () => {
  void nextTick(renderTrendChart);
});

onMounted(async () => {
  await restoreFromRoute();
  await loadProjectOptions();
  routeStateReady.value = true;
});
</script>

<template>
  <Page
    auto-content-height
    class="adpulse-section-page project-comparison-page bg-muted/40"
    content-class="p-4"
  >
    <div class="flex w-full min-w-0 flex-col gap-4">
      <section class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <IconifyIcon
              class="text-muted-foreground size-5"
              icon="lucide:chart-no-axes-combined"
            />
            <h1
              class="text-foreground m-0 text-xl font-semibold tracking-tight"
            >
              项目环比分析
            </h1>
          </div>
          <p class="text-muted-foreground mb-0 mt-1 text-sm leading-6">
            按项目、代理线与同口径时间窗口比较投放结果；{{
              dataSourceDescription
            }}
          </p>
        </div>
        <div class="flex shrink-0 flex-wrap gap-2">
          <Button :disabled="!overview" @click="reviewDrawerOpen = true">
            <template #icon>
              <IconifyIcon icon="lucide:file-text" />
            </template>
            生成复盘草稿
          </Button>
          <Button @click="router.back()">
            <template #icon><IconifyIcon icon="lucide:arrow-left" /></template>
            返回
          </Button>
        </div>
      </section>

      <Card class="border-border shadow-none" :body-style="{ padding: '16px' }">
        <div class="pca-filter-form">
          <div class="pca-filter-item">
            <div class="pca-filter-label">项目</div>
            <Select
              v-model:value="filterState.projectId"
              class="pca-filter-control"
              placeholder="选择项目"
              :options="projectOptions"
              @change="handleProjectChange"
            />
          </div>
          <div class="pca-filter-item">
            <div class="pca-filter-label">对比方式</div>
            <Select
              v-model:value="filterState.mode"
              class="pca-filter-control"
              :options="modeOptions"
              @change="handleModeChange"
            />
          </div>
          <div class="pca-filter-item">
            <div class="pca-filter-label">当前周期</div>
            <DatePicker.RangePicker
              v-model:value="filterState.currentRange"
              class="pca-filter-control"
              value-format="YYYY-MM-DD"
              :disabled="filterState.mode !== 'custom'"
              @change="applyQueryState"
            />
          </div>
          <div class="pca-filter-item">
            <div class="pca-filter-label">对比周期</div>
            <DatePicker.RangePicker
              v-model:value="filterState.comparisonRange"
              class="pca-filter-control"
              value-format="YYYY-MM-DD"
              :disabled="filterState.mode !== 'custom'"
              @change="applyQueryState"
            />
          </div>
          <div class="pca-filter-item">
            <div class="pca-filter-label">代理线</div>
            <Select
              v-model:value="selectedAgencyLineIds"
              allow-clear
              class="pca-filter-control"
              mode="multiple"
              placeholder="全部已接入代理线"
              :options="agencyLineOptions"
              @change="applyQueryState"
            />
          </div>
          <div class="pca-filter-item">
            <div class="pca-filter-label">趋势粒度</div>
            <RadioGroup
              v-model:value="filterState.granularity"
              class="pca-filter-control"
              @change="applyQueryState"
            >
              <RadioButton value="hour">小时</RadioButton>
              <RadioButton value="day">天</RadioButton>
            </RadioGroup>
          </div>
          <div class="flex items-center">
            <Button type="primary" :loading="loading" @click="loadOverview">
              <template #icon>
                <IconifyIcon icon="lucide:refresh-cw" />
              </template>
              刷新分析
            </Button>
          </div>
        </div>
      </Card>

      <Alert v-if="error" show-icon type="error" :message="error">
        <template #action>
          <Button @click="loadOverview">重试</Button>
        </template>
      </Alert>

      <Spin :spinning="loading">
        <template v-if="overview">
          <Alert class="border-border bg-muted/50" show-icon type="info">
            <template #message>
              数据截至 {{ overview.dataQuality.asOf }} · 当前周期覆盖
              {{ (overview.dataQuality.currentCoverage * 100).toFixed(0) }}%
            </template>
            <template #description>
              <span v-if="overview.dataQuality.messages.length > 0">
                {{ overview.dataQuality.messages.join(' ') }}
              </span>
              <span v-else-if="overview.dataQuality.authority">
                正式来源：{{ dataSourceDescription }}。
              </span>
              <span v-else>
                当前查询窗口完整，指标均按项目币种与选定范围聚合。
              </span>
            </template>
          </Alert>

          <section
            class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
          >
            <Card
              v-for="config in projectComparisonMetricConfigs"
              :key="config.key"
              class="border-border min-w-0 shadow-none"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-muted-foreground text-sm">{{
                  config.label
                }}</span>
                <Tag v-if="config.isDemoProjection">演示口径</Tag>
              </div>
              <div class="text-foreground mt-2 truncate text-xl font-semibold">
                {{
                  formatMetric(config.key, selectedMetric(config.key).current)
                }}
              </div>
              <div class="mt-2 flex items-center justify-between gap-2 text-xs">
                <span>
                  {{
                    `对比 ${formatMetric(
                      config.key,
                      selectedMetric(config.key).comparison,
                    )}`
                  }}
                </span>
                <span :class="deltaClass(selectedMetric(config.key))">
                  {{ formatDelta(selectedMetric(config.key)) }}
                </span>
              </div>
            </Card>
          </section>

          <section class="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card
              class="border-border min-w-0 shadow-none xl:col-span-2"
              title="趋势对比"
            >
              <template #extra>
                <Select
                  v-model:value="trendMetric"
                  class="w-40"
                  :options="
                    projectComparisonMetricConfigs.map((item) => ({
                      label: item.label,
                      value: item.key,
                    }))
                  "
                />
              </template>
              <EchartsUI ref="chartRef" height="320px" width="100%" />
            </Card>

            <Card class="border-border min-w-0 shadow-none" title="自动分析">
              <div class="space-y-3">
                <div
                  v-for="insight in overview.insights"
                  :key="insight.id"
                  class="border-border rounded-lg border p-3"
                >
                  <div
                    class="text-foreground flex items-center gap-2 text-sm font-medium"
                  >
                    <IconifyIcon
                      :class="
                        insight.tone === 'negative'
                          ? 'text-destructive'
                          : insight.tone === 'positive'
                            ? 'text-emerald-500'
                            : 'text-primary'
                      "
                      :icon="
                        insight.tone === 'negative'
                          ? 'lucide:triangle-alert'
                          : insight.tone === 'positive'
                            ? 'lucide:circle-check-big'
                            : 'lucide:lightbulb'
                      "
                    />
                    {{ insight.title }}
                  </div>
                  <p class="text-muted-foreground mb-0 mt-2 text-sm leading-6">
                    {{ insight.body }}
                  </p>
                </div>
              </div>
            </Card>
          </section>

          <section class="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
            <Card
              class="border-border min-w-0 shadow-none xl:col-span-2"
              title="代理线排名"
            >
              <Table
                :columns="rankingColumns"
                :data-source="rankedAgencyLines"
                :pagination="false"
                row-key="agencyLineId"
                :scroll="{ x: 820 }"
              >
                <template #bodyCell="{ column, index, record }">
                  <template v-if="column.key === 'rank'">
                    {{ index + 1 }}
                  </template>
                  <template v-else-if="column.key === 'name'">
                    <div class="text-foreground font-medium">
                      {{ record.name }}
                    </div>
                    <div class="text-muted-foreground mt-1 text-xs">
                      {{ record.agencyLineId }}
                    </div>
                  </template>
                  <template v-else-if="column.key === 'platform'">
                    <Tag>{{ record.platform }}</Tag>
                  </template>
                  <template v-else-if="column.key === 'spend'">
                    {{ formatMetric('spend', record.current.spend ?? null) }}
                  </template>
                  <template v-else-if="column.key === 'roas'">
                    {{ formatMetric('roas', record.current.roas ?? null) }}
                    <Tag class="ml-1" :color="tagColor(record.metrics.roas)">
                      {{ formatDelta(record.metrics.roas) }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'firstPurchaseCost'">
                    {{
                      formatMetric(
                        'firstPurchaseCost',
                        record.current.firstPurchaseCost ?? null,
                      )
                    }}
                  </template>
                  <template v-else-if="column.key === 'registrationCost'">
                    {{
                      formatMetric(
                        'registrationCost',
                        record.current.registrationCost ?? null,
                      )
                    }}
                  </template>
                </template>
              </Table>
            </Card>

            <Card class="border-border min-w-0 shadow-none" title="异常与风险">
              <div v-if="overview.alerts.length > 0" class="space-y-3">
                <Alert
                  v-for="alert in overview.alerts"
                  :key="`${alert.agencyLineId ?? 'project'}-${alert.key}`"
                  show-icon
                  :type="alert.level === 'critical' ? 'error' : 'warning'"
                  :message="alert.title"
                  :description="alert.message"
                />
              </div>
              <Empty
                v-else
                description="当前范围未命中风险阈值"
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
              />
            </Card>
          </section>

          <section class="mt-4">
            <Card
              class="border-border min-w-0 shadow-none"
              title="素材方向排行"
            >
              <template #extra>
                <div class="flex flex-wrap justify-end gap-2">
                  <Select
                    v-model:value="creativeDirectionRankMetric"
                    class="w-36"
                    :options="creativeDirectionRankMetricOptions"
                    @change="handleCreativeDirectionRankMetricChange"
                  />
                  <Select
                    v-model:value="creativeDirectionRankDirection"
                    class="w-28"
                    :options="creativeDirectionRankDirectionOptions"
                  />
                </div>
              </template>
              <p class="text-muted-foreground mb-3 text-xs leading-5">
                以稳定素材版本组成的创意方向聚合，支持按指标及升降方向排序；当前为
                Mock 演示数据。
              </p>
              <Table
                :columns="creativeDirectionRankingColumns"
                :data-source="rankedCreativeDirections"
                :pagination="false"
                row-key="creativeDirectionId"
                :scroll="{ x: 1080 }"
              >
                <template #bodyCell="{ column, index, record }">
                  <template v-if="column.key === 'rank'">
                    {{ index + 1 }}
                  </template>
                  <template v-else-if="column.key === 'name'">
                    <div class="text-foreground font-medium">
                      {{ record.name }}
                    </div>
                    <div class="text-muted-foreground mt-1 text-xs">
                      {{ record.creativeDirectionId }}
                    </div>
                  </template>
                  <template v-else-if="column.key === 'assetType'">
                    <Tag>
                      {{ creativeAssetTypeLabel(record.assetType) }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'agencyLineName'">
                    <div class="text-foreground font-medium">
                      {{ record.agencyLineName }}
                    </div>
                    <div class="text-muted-foreground mt-1 text-xs">
                      {{ record.platform }}
                    </div>
                  </template>
                  <template v-else-if="column.key === 'materialVersionCount'">
                    {{ record.materialVersionCount }} 个版本
                  </template>
                  <template v-else-if="column.key === 'spend'">
                    {{ formatMetric('spend', record.current.spend ?? null) }}
                  </template>
                  <template v-else-if="column.key === 'roas'">
                    {{ formatMetric('roas', record.current.roas ?? null) }}
                    <Tag
                      class="ml-1"
                      :color="tagColor(directionMetric(record.metrics, 'roas'))"
                    >
                      {{ formatDelta(directionMetric(record.metrics, 'roas')) }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'firstPurchaseCost'">
                    {{
                      formatMetric(
                        'firstPurchaseCost',
                        record.current.firstPurchaseCost ?? null,
                      )
                    }}
                  </template>
                </template>
              </Table>
            </Card>
          </section>
        </template>
        <Empty v-else-if="!loading && !error" description="请选择可查看项目" />
      </Spin>

      <Drawer v-model:open="reviewDrawerOpen" :width="640" title="项目复盘草稿">
        <template v-if="reviewDraft">
          <Alert
            class="mb-4"
            show-icon
            type="warning"
            message="规则型草稿，需人工校对后使用"
            description="本草稿只反映当前筛选条件与数据截止时间，不会保存、发送或替代正式报表。"
          />
          <Card :title="reviewDraft.title">
            <template #extra>
              <Button type="primary" @click="copyReviewDraft">
                <template #icon>
                  <IconifyIcon icon="lucide:copy" />
                </template>
                复制 Markdown
              </Button>
            </template>
            <div class="space-y-4">
              <div class="text-muted-foreground text-sm leading-6">
                当前周期：{{ reviewDraft.currentPeriodLabel }}<br />
                对比周期：{{ reviewDraft.comparisonPeriodLabel }}<br />
                数据截至：{{ reviewDraft.generatedAt }}
              </div>
              <section
                v-for="section in reviewDraft.sections"
                :key="section.id"
                class="border-border rounded-lg border p-3"
              >
                <h3 class="text-foreground m-0 text-sm font-semibold">
                  {{ section.title }}
                </h3>
                <p class="text-muted-foreground mb-0 mt-2 text-sm leading-6">
                  {{ section.body }}
                </p>
              </section>
            </div>
          </Card>
        </template>
      </Drawer>
    </div>
  </Page>
</template>

<style scoped>
.pca-filter-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
}

.pca-filter-item {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.pca-filter-label {
  flex: 0 0 4em;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  font-weight: 500;
  line-height: var(--adpulse-control-height);
  white-space: nowrap;
}

.pca-filter-control {
  flex: 0 0 var(--adpulse-filter-search-width);
  width: var(--adpulse-filter-search-width) !important;
}

@media (max-width: 767px) {
  .pca-filter-item {
    width: 100%;
  }

  .pca-filter-control {
    flex: 1 1 0;
    width: auto !important;
  }
}
</style>
