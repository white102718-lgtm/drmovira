<script setup lang="ts">
import type { NotificationRecord } from '#/api/advertisement/automated-rule';
import type {
  CompareMode,
  PerformanceComparisonResult,
} from '#/api/advertisement/performance-comparison';

import { computed, ref, watch } from 'vue';

import {
  Button,
  DatePicker,
  Input,
  Modal,
  Select,
  Spin,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { queryPerformanceComparison } from '#/api/advertisement/performance-comparison';
import AntDataTable from '#/components/ui/AntDataTable.vue';

interface Props {
  open: boolean;
  record: NotificationRecord | null;
}

interface Emits {
  (e: 'update:open', value: boolean): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const modalOpen = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val),
});

const METRIC_OPTIONS = [
  { code: 'cost', name: '花费', unit: 'USD' },
  { code: 'purchase_value', name: '购物金额', unit: 'USD' },
  { code: 'registrations', name: '注册', unit: 'count' },
  { code: 'purchases', name: '购物', unit: 'count' },
  { code: 'subscriptions', name: '订阅', unit: 'count' },
  { code: 'purchase_roas', name: '购物ROAS', unit: 'ratio' },
  { code: 'registration_cost', name: '注册成本', unit: 'USD' },
  { code: 'purchase_cost', name: '购物成本', unit: 'USD' },
  { code: 'subscription_cost', name: '订阅成本', unit: 'USD' },
  { code: 'budget', name: '预算', unit: 'USD' },
] as const;

type MetricCode = (typeof METRIC_OPTIONS)[number]['code'];

const MOM_OFFSETS = [
  { value: 1, label: '前1h' },
  { value: 2, label: '前2h' },
  { value: 3, label: '前3h' },
  { value: 6, label: '前6h' },
];
const YOY_OFFSETS = [
  { value: 1, label: '昨天' },
  { value: 2, label: '前天' },
  { value: 3, label: '3天前' },
  { value: 7, label: '7天前' },
];

const CHART_W = 880;
const CHART_H = 280;
const COLORS = [
  '#2563eb',
  '#0f766e',
  '#ef4444',
  '#f59e0b',
  '#7c3aed',
  '#16a34a',
];

const mode = ref<CompareMode>('mom');
const metric = ref<MetricCode>('cost');
const baseTime = ref(toLocalDatetimeStr(startOfHour()));
/** 按钮选中的偏移量 */
const offsetButtonValues = ref<number[]>([1, 2, 3]);
const loading = ref(false);
const result = ref<PerformanceComparisonResult | null>(null);

// ──────────── 高级筛选 ────────────
const showAdvanced = ref(false);
const customOffsetsText = ref('');
const accountId = ref('');
const objectIdOverride = ref('');
const customTimes = ref<string[]>([]);
const customTimeDraft = ref('');

/** 最终偏移量：文本框有值时覆盖按钮选择 */
const offsetValues = computed(() => {
  if (customOffsetsText.value.trim()) {
    return customOffsetsText.value
      .split(',')
      .map((v) => Number(v.trim()))
      .filter((v) => Number.isFinite(v) && v > 0);
  }
  return offsetButtonValues.value;
});

const offsetButtons = computed(() =>
  mode.value === 'mom' ? MOM_OFFSETS : YOY_OFFSETS,
);

const items = computed(() => result.value?.items ?? []);
const timePoints = computed(() => result.value?.time_points ?? []);
const compareTimePoints = computed(() => timePoints.value.slice(1));
const performanceColumns = computed(() => [
  { key: 'object', title: '对象', width: 220 },
  {
    key: 'base',
    title: timePoints.value[0]?.slice(5, 16) ?? '基准',
    width: 160,
  },
  ...compareTimePoints.value.map((point, index) => ({
    key: `compare-${index}`,
    title: mode.value === 'yoy' ? point.slice(0, 10) : point.slice(5, 16),
    width: 180,
  })),
]);
const chartTimePoints = computed(() =>
  [...timePoints.value].sort(
    (a, b) =>
      new Date(a.replace(' ', 'T')).getTime() -
      new Date(b.replace(' ', 'T')).getTime(),
  ),
);

const series = computed(() =>
  items.value.slice(0, 6).map((item, i) => ({
    item,
    color: COLORS[i % COLORS.length],
    values: chartTimePoints.value.map(
      (pt) =>
        item.points?.find((p) => p.time === pt)?.metrics?.[metric.value] ??
        null,
    ),
  })),
);

const allChartValues = computed(() =>
  series.value.flatMap((s) =>
    s.values.filter((v): v is number => isFiniteNum(v)).map(Number),
  ),
);
const chartMax = computed(() =>
  allChartValues.value.length ? Math.max(...allChartValues.value) : 1,
);
const chartMin = computed(() =>
  allChartValues.value.length ? Math.min(...allChartValues.value) : 0,
);
const chartRange = computed(() => chartMax.value - chartMin.value || 1);

const objectLabel = computed(() => {
  if (!props.record) return '';
  const item = props.record.notification_item;
  const level = props.record.level;
  if (level === 'ad') return item?.ad_name || item?.campaign_name || '';
  if (level === 'adset') return item?.adset_name || item?.campaign_name || '';
  return item?.campaign_name || '';
});

const levelLabel = computed(() => {
  const map: Record<string, string> = {
    campaign: '系列',
    adset: '广告组',
    ad: '广告',
    agent_line: '代理线',
  };
  return map[props.record?.level ?? ''] ?? '';
});

watch(
  () => props.open,
  (val) => {
    if (val && props.record) {
      initFromRecord();
      loadData();
    }
  },
);

watch(mode, (val) => {
  offsetButtonValues.value = val === 'mom' ? [1, 2, 3] : [1, 2];
  customOffsetsText.value = '';
});

/** 重置所有筛选条件 */
function resetFilters() {
  mode.value = 'mom';
  metric.value = 'cost';
  baseTime.value = toLocalDatetimeStr(startOfHour());
  offsetButtonValues.value = [1, 2, 3];
  customOffsetsText.value = '';
  accountId.value = '';
  objectIdOverride.value = '';
  customTimes.value = [];
  customTimeDraft.value = '';
  result.value = null;
}

/** 从记录初始化查询参数 */
function initFromRecord() {
  const checkedAt = props.record?.checked_at;
  if (checkedAt) {
    baseTime.value = checkedAt.replace(' ', 'T').slice(0, 16);
  } else {
    baseTime.value = toLocalDatetimeStr(startOfHour());
  }
  offsetButtonValues.value = mode.value === 'mom' ? [1, 2, 3] : [1, 2];
  customOffsetsText.value = '';
  accountId.value = '';
  objectIdOverride.value = '';
  customTimes.value = [];
  customTimeDraft.value = '';
  result.value = null;
}

/** 切换同比/环比模式 */
function setMode(val: string) {
  mode.value = val as CompareMode;
}

/** 切换指标 */
function setMetric(val: any) {
  if (val) metric.value = val as MetricCode;
}

/** 切换偏移量选中状态（文本框有值时同步更新文本，否则更新按钮状态） */
function toggleOffset(val: number) {
  if (customOffsetsText.value.trim()) {
    const current = offsetValues.value;
    const next = current.includes(val)
      ? current.filter((v) => v !== val)
      : [...current, val].sort((a, b) => a - b);
    customOffsetsText.value = next.join(',');
  } else {
    const idx = offsetButtonValues.value.indexOf(val);
    if (idx === -1) {
      offsetButtonValues.value = [...offsetButtonValues.value, val].sort(
        (a, b) => a - b,
      );
    } else {
      offsetButtonValues.value = offsetButtonValues.value.filter(
        (v) => v !== val,
      );
    }
  }
}

/** 更新额外时间点草稿（DatePicker 返回 string | Dayjs，取 string） */
function onCustomTimeDraftChange(val: any) {
  customTimeDraft.value = typeof val === 'string' ? val : '';
}

/** 添加额外时间点 */
function addCustomTime() {
  if (
    !customTimeDraft.value ||
    customTimes.value.includes(customTimeDraft.value)
  )
    return;
  customTimes.value = [...customTimes.value, customTimeDraft.value].sort(
    (a, b) => new Date(a).getTime() - new Date(b).getTime(),
  );
  customTimeDraft.value = '';
}

/** 删除额外时间点 */
function removeCustomTime(val: string) {
  customTimes.value = customTimes.value.filter((v) => v !== val);
}

/** 格式化时间点显示 */
function fmtCustomTime(val: string) {
  return val.replace('T', ' ').slice(0, 16);
}

/** 加载分析数据 */
async function loadData() {
  if (!props.record) return;
  const item = props.record.notification_item;
  loading.value = true;
  try {
    result.value = await queryPerformanceComparison({
      mode: mode.value,
      level: (props.record.level as any) || 'campaign',
      base_time: baseTime.value,
      compare_offsets: offsetValues.value.length
        ? offsetValues.value
        : undefined,
      compare_times: customTimes.value.length ? customTimes.value : undefined,
      project_id: item?.project_id || undefined,
      game_platform: item?.project_id || undefined,
      agent_line: item?.agent_line || undefined,
      account_id: accountId.value.trim() || undefined,
      object_id:
        objectIdOverride.value.trim() || props.record.object_id || undefined,
      limit: 10,
    });
  } finally {
    loading.value = false;
  }
}

function close() {
  modalOpen.value = false;
}

// ──────────── 图表工具函数 ────────────

function isFiniteNum(v: any): v is number {
  return v !== null && v !== undefined && Number.isFinite(Number(v));
}

function gridY(ratio: number) {
  return 24 + (CHART_H - 52) * (ratio / 100);
}

function pointX(idx: number) {
  const pts = chartTimePoints.value;
  return pts.length > 1
    ? 44 + (CHART_W - 60) * (idx / (pts.length - 1))
    : CHART_W / 2;
}

function pointY(val: number) {
  return 24 + ((chartMax.value - val) / chartRange.value) * (CHART_H - 52);
}

function seriesPath(values: Array<null | number>) {
  return values
    .map((v, i) =>
      isFiniteNum(v) ? `${pointX(i)},${pointY(Number(v))}` : null,
    )
    .filter(Boolean)
    .join(' ');
}

function axisLabel(pt: string) {
  const s = pt.replace('T', ' ');
  return mode.value === 'yoy'
    ? { primary: s.slice(5, 10), secondary: s.slice(11, 16) }
    : { primary: s.slice(11, 16), secondary: s.slice(5, 10) };
}

function fmtMetric(code: string, value: any): string {
  const unit = METRIC_OPTIONS.find((m) => m.code === code)?.unit;
  if (value === null || value === undefined || !Number.isFinite(Number(value)))
    return '-';
  const n = Number(value);
  if (unit === 'USD')
    return `$${n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;
  if (unit === 'ratio')
    return n.toLocaleString('zh-CN', { maximumFractionDigits: 4 });
  return n.toLocaleString('zh-CN', { maximumFractionDigits: 0 });
}

function baseMetric(item: any) {
  return item.points?.find((p: any) => p.time === timePoints.value[0])
    ?.metrics?.[metric.value];
}

function cmpMetric(item: any, cmpIdx: number, key: string) {
  return item.comparisons?.[cmpIdx]?.metrics?.[metric.value]?.[key];
}

function deltaColor(val: any): string {
  if (!isFiniteNum(val) || val === 0) return 'text-gray-400';
  return val > 0 ? 'text-green-600' : 'text-red-500';
}

// ──────────── 时间工具 ────────────

function startOfHour(d = new Date()) {
  const c = new Date(d);
  c.setMinutes(0, 0, 0);
  return c;
}

function toLocalDatetimeStr(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:00`;
}
</script>

<template>
  <Modal
    :open="modalOpen"
    :footer="null"
    width="1100px"
    destroy-on-close
    @update:open="
      (v) => {
        if (!v) close();
      }
    "
  >
    <template #title>
      <div class="flex items-center gap-2">
        <span class="font-semibold">同比环比分析</span>
        <Tag v-if="levelLabel" color="blue">{{ levelLabel }}</Tag>
        <Tag v-if="objectLabel" color="cyan" class="max-w-xs truncate">{{
          objectLabel
        }}</Tag>
      </div>
    </template>

    <div class="flex flex-col gap-3 py-1">
      <!-- ── 筛选卡片 ── -->
      <div class="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3">
        <!-- 主筛选行 -->
        <div class="flex flex-wrap items-center gap-2">
          <!-- 环比/同比 -->
          <div class="flex overflow-hidden rounded border border-gray-200">
            <Button
              v-for="opt in [
                { value: 'mom', label: '环比' },
                { value: 'yoy', label: '同比' },
              ]"
              :key="opt.value"
              :type="mode === opt.value ? 'primary' : 'default'"
              @click="setMode(opt.value)"
            >
              {{ opt.label }}
            </Button>
          </div>

          <!-- 指标 -->
          <Select
            :value="metric"
            class="w-28"
            :options="
              METRIC_OPTIONS.map((m) => ({ label: m.name, value: m.code }))
            "
            @update:value="setMetric"
          />

          <!-- 基准时间 -->
          <DatePicker
            v-model="baseTime"
            show-time
            value-format="YYYY-MM-DDTHH:mm"
            format="MM-DD HH:mm"
            :show-second="false"
            placeholder="基准时间"
            class="w-36"
            :allow-clear="false"
          />

          <!-- 分隔 -->
          <span class="select-none text-gray-200">|</span>

          <!-- 对比点 -->
          <span class="text-xs text-gray-500">对比：</span>
          <Button
            v-for="btn in offsetButtons"
            :key="btn.value"
            :type="offsetValues.includes(btn.value) ? 'primary' : 'default'"
            @click="toggleOffset(btn.value)"
          >
            {{ btn.label }}
          </Button>

          <!-- 操作组 右对齐 -->
          <div class="ml-auto flex items-center gap-2">
            <Button type="text" @click="showAdvanced = !showAdvanced">
              高级筛选 {{ showAdvanced ? '▲' : '▼' }}
            </Button>
            <Button @click="resetFilters">重置</Button>
            <Button type="primary" :loading="loading" @click="loadData"
              >查询</Button
            >
          </div>
        </div>

        <!-- 高级筛选（折叠） -->
        <div v-if="showAdvanced" class="mt-3 border-t border-gray-200 pt-3">
          <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
            <!-- 自定义偏移 -->
            <div class="flex items-center gap-1.5">
              <span class="whitespace-nowrap text-xs text-gray-600"
                >自定义偏移</span
              >
              <Input
                :value="customOffsetsText"
                :placeholder="
                  mode === 'mom' ? '如 1,2,6（h）' : '如 1,2,7（天）'
                "
                class="w-32"
                allow-clear
                @change="customOffsetsText = $event.target.value || ''"
                @clear="customOffsetsText = ''"
              />
            </div>

            <!-- 账户ID -->
            <div class="flex items-center gap-1.5">
              <span class="whitespace-nowrap text-xs text-gray-600"
                >账户 ID</span
              >
              <Input
                :value="accountId"
                placeholder="广告账户ID"
                class="w-36"
                allow-clear
                @change="accountId = $event.target.value || ''"
                @clear="accountId = ''"
              />
            </div>

            <!-- 对象ID -->
            <div class="flex items-center gap-1.5">
              <span class="whitespace-nowrap text-xs text-gray-600"
                >对象 ID</span
              >
              <Input
                :value="objectIdOverride"
                placeholder="系列/组/广告ID"
                class="w-40"
                allow-clear
                @change="objectIdOverride = $event.target.value || ''"
                @clear="objectIdOverride = ''"
              />
            </div>

            <!-- 额外时间点 -->
            <div class="flex items-center gap-1.5">
              <span class="whitespace-nowrap text-xs text-gray-600"
                >额外时间点</span
              >
              <DatePicker
                :value="customTimeDraft"
                show-time
                value-format="YYYY-MM-DDTHH:mm"
                format="MM-DD HH:mm"
                :show-second="false"
                placeholder="选择时间点"
                class="w-36"
                @update:value="onCustomTimeDraftChange"
              />
              <Button :disabled="!customTimeDraft" @click="addCustomTime"
                >添加</Button
              >
            </div>
          </div>

          <!-- 已添加时间点 tags -->
          <div v-if="customTimes.length" class="mt-2 flex flex-wrap gap-1.5">
            <Button
              v-for="t in customTimes"
              :key="t"
              class="gap-1"
              title="点击删除"
              type="default"
              @click="removeCustomTime(t)"
            >
              {{ fmtCustomTime(t) }}
              <svg
                width="10"
                height="10"
                viewBox="0 0 10 10"
                fill="currentColor"
              >
                <path
                  d="M1 1l8 8M9 1l-8 8"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                />
              </svg>
            </Button>
          </div>
        </div>
      </div>

      <!-- ── 图表卡片 ── -->
      <div class="rounded-lg border border-gray-100 bg-white">
        <Spin :spinning="loading">
          <!-- 未查询 -->
          <div
            v-if="!result && !loading"
            class="flex h-48 flex-col items-center justify-center gap-2 text-gray-300"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="36"
              height="36"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            <span class="text-sm">请设置筛选条件后点击查询</span>
          </div>

          <!-- 空结果 -->
          <div
            v-else-if="result && !items.length"
            class="flex h-48 flex-col items-center justify-center gap-2 text-gray-300"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="36"
              height="36"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
              <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
            </svg>
            <span class="text-sm">无匹配数据</span>
          </div>

          <!-- 图表 -->
          <template v-else-if="result && items.length">
            <div
              class="flex items-center justify-between border-b border-gray-50 px-4 py-2.5"
            >
              <span class="text-sm font-medium text-gray-700">
                {{ METRIC_OPTIONS.find((m) => m.code === metric)?.name }} 趋势
              </span>
              <span class="text-xs text-gray-400">
                基准 {{ timePoints[0]?.slice(5, 16) }}
                <template v-if="compareTimePoints.length">
                  · 对比
                  {{ compareTimePoints.map((p) => p.slice(5, 16)).join(' / ') }}
                </template>
              </span>
            </div>

            <svg
              class="block w-full px-2"
              :viewBox="`0 0 ${CHART_W} ${CHART_H}`"
              style="height: 240px"
            >
              <rect :width="CHART_W" :height="CHART_H" fill="#fff" />
              <g v-for="ratio in [0, 25, 50, 75, 100]" :key="ratio">
                <line
                  x1="44"
                  :x2="CHART_W - 16"
                  :y1="gridY(ratio)"
                  :y2="gridY(ratio)"
                  stroke="#f1f5f9"
                  stroke-dasharray="4,3"
                />
                <text x="4" :y="gridY(ratio) + 4" font-size="10" fill="#cbd5e1">
                  {{ fmtMetric(metric, chartMax - chartRange * (ratio / 100)) }}
                </text>
              </g>
              <g v-for="(pt, idx) in chartTimePoints" :key="pt">
                <line
                  :x1="pointX(idx)"
                  :x2="pointX(idx)"
                  y1="24"
                  :y2="CHART_H - 28"
                  stroke="#f8fafc"
                />
                <text
                  :x="pointX(idx)"
                  :y="CHART_H - 14"
                  text-anchor="middle"
                  font-size="10"
                  fill="#64748b"
                >
                  {{ axisLabel(pt).primary }}
                </text>
                <text
                  :x="pointX(idx)"
                  :y="CHART_H - 2"
                  text-anchor="middle"
                  font-size="9"
                  fill="#94a3b8"
                >
                  {{ axisLabel(pt).secondary }}
                </text>
              </g>
              <g v-for="s in series" :key="s.item.object_id">
                <polyline
                  :points="seriesPath(s.values)"
                  fill="none"
                  :stroke="s.color"
                  stroke-width="2"
                  stroke-linejoin="round"
                  stroke-linecap="round"
                />
                <circle
                  v-for="(v, idx) in s.values"
                  v-show="isFiniteNum(v)"
                  :key="idx"
                  :cx="pointX(idx)"
                  :cy="pointY(Number(v))"
                  r="3.5"
                  :fill="s.color"
                  stroke="#fff"
                  stroke-width="1.5"
                />
              </g>
            </svg>

            <!-- 图例 -->
            <div class="flex flex-wrap gap-3 px-4 pb-3 pt-1">
              <span
                v-for="s in series"
                :key="s.item.object_id"
                class="flex items-center gap-1.5 text-xs text-gray-500"
              >
                <i
                  class="inline-block size-2.5 shrink-0 rounded-full"
                  :style="{ backgroundColor: s.color }"
                ></i>
                {{ s.item.object_name }}
              </span>
            </div>
          </template>
        </Spin>
      </div>

      <!-- ── 明细表卡片 ── -->
      <div
        v-if="items.length"
        class="overflow-hidden rounded-lg border border-gray-100"
      >
        <!-- 表头栏 -->
        <div
          class="flex items-center justify-between border-b border-gray-100 bg-white px-4 py-2.5"
        >
          <span class="text-sm font-medium text-gray-700">数据明细</span>
          <span class="text-xs text-gray-400">
            共 {{ result?.total ?? items.length }} 个对象
            <template v-if="result?.total && result.total > 10"
              >，仅显示前 10 条</template
            >
          </span>
        </div>

        <AntDataTable
          :columns="performanceColumns"
          :data="items.slice(0, 10)"
          :paginate="false"
          row-key="object_id"
        >
          <template #cell-object="{ record }">
            <Tooltip :title="record.object_id">
              <span class="text-foreground font-medium">{{
                record.object_name
              }}</span>
            </Tooltip>
          </template>
          <template #cell-base="{ record }">
            <span class="text-foreground font-semibold">
              {{ fmtMetric(metric, baseMetric(record)) }}
            </span>
          </template>
          <template
            v-for="(_, cmpIdx) in compareTimePoints"
            :key="cmpIdx"
            v-slot:[`cell-compare-${cmpIdx}`]="{ record }"
          >
            <div class="text-foreground">
              {{ fmtMetric(metric, cmpMetric(record, cmpIdx, 'compare')) }}
            </div>
            <div
              class="text-muted-foreground mt-0.5 flex items-center gap-1 text-xs"
            >
              <span :class="deltaColor(cmpMetric(record, cmpIdx, 'delta'))">
                {{
                  (cmpMetric(record, cmpIdx, 'delta') ?? 0) > 0
                    ? '↑'
                    : (cmpMetric(record, cmpIdx, 'delta') ?? 0) < 0
                      ? '↓'
                      : ''
                }}
                {{
                  fmtMetric(
                    metric,
                    Math.abs(Number(cmpMetric(record, cmpIdx, 'delta'))),
                  )
                }}
              </span>
              <span
                v-if="cmpMetric(record, cmpIdx, 'delta_rate') != null"
                :class="deltaColor(cmpMetric(record, cmpIdx, 'delta_rate'))"
              >
                ({{
                  (cmpMetric(record, cmpIdx, 'delta_rate') ?? 0) > 0 ? '+' : ''
                }}{{
                  Number(cmpMetric(record, cmpIdx, 'delta_rate')).toFixed(1)
                }}%)
              </span>
            </div>
          </template>
        </AntDataTable>

        <div v-if="false" class="overflow-auto">
          <table class="w-full border-collapse text-xs">
            <thead>
              <tr class="bg-gray-50">
                <th
                  class="border-b border-gray-100 px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400"
                >
                  对象
                </th>
                <th
                  class="border-b border-gray-100 px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400"
                >
                  <span class="font-normal normal-case text-gray-400">{{
                    timePoints[0]?.slice(5, 16)
                  }}</span>
                </th>
                <th
                  v-for="pt in compareTimePoints"
                  :key="pt"
                  class="border-b border-gray-100 px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400"
                >
                  {{ mode === 'yoy' ? pt.slice(0, 10) : pt.slice(5, 16) }}
                  <span
                    v-if="mode === 'yoy'"
                    class="ml-1 font-normal normal-case text-gray-300"
                    >{{ pt.slice(11, 16) }}</span
                  >
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in items.slice(0, 10)"
                :key="item.object_id"
                class="border-b border-gray-50 transition-colors hover:bg-blue-50/30"
              >
                <td class="px-4 py-2.5">
                  <Tooltip :title="item.object_id">
                    <span class="font-medium text-gray-800">{{
                      item.object_name
                    }}</span>
                  </Tooltip>
                </td>
                <td class="px-4 py-2.5 font-semibold text-gray-800">
                  {{ fmtMetric(metric, baseMetric(item)) }}
                </td>
                <td
                  v-for="(_, cmpIdx) in item.comparisons ?? []"
                  :key="cmpIdx"
                  class="px-4 py-2.5"
                >
                  <div class="text-gray-700">
                    {{ fmtMetric(metric, cmpMetric(item, cmpIdx, 'compare')) }}
                  </div>
                  <div class="mt-0.5 flex items-center gap-1 text-[11px]">
                    <span :class="deltaColor(cmpMetric(item, cmpIdx, 'delta'))">
                      {{
                        (cmpMetric(item, cmpIdx, 'delta') ?? 0) > 0
                          ? '▲'
                          : (cmpMetric(item, cmpIdx, 'delta') ?? 0) < 0
                            ? '▼'
                            : ''
                      }}
                      {{
                        fmtMetric(
                          metric,
                          Math.abs(Number(cmpMetric(item, cmpIdx, 'delta'))),
                        )
                      }}
                    </span>
                    <span
                      v-if="cmpMetric(item, cmpIdx, 'delta_rate') != null"
                      :class="deltaColor(cmpMetric(item, cmpIdx, 'delta_rate'))"
                    >
                      ({{
                        (cmpMetric(item, cmpIdx, 'delta_rate') ?? 0) > 0
                          ? '+'
                          : ''
                      }}{{
                        Number(cmpMetric(item, cmpIdx, 'delta_rate')).toFixed(
                          1,
                        )
                      }}%)
                    </span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </Modal>
</template>
