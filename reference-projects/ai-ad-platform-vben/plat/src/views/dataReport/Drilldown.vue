<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { Page } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import { useVbenVxeGrid } from '#/adapter/vxe-table';

import AnimatedCount from '../components/AnimatedCount.vue';
import BaseButton from '../components/BaseButton.vue';
import {
  createDiagnosticAction,
  exportDrilldown,
  getDrilldown,
} from '#/api/advertisement/diagnostics';
import type {
  ChildrenItem,
  DrilldownData,
  DrilldownMetric,
  DrilldownPathItem,
  RootCause,
  SuggestedAction,
} from '#/api/advertisement/diagnostics';

const route = useRoute();

// ==================== 状态 ====================
const drilldownData = ref<DrilldownData | null>(null);
const pageContentRef = ref<HTMLElement | null>(null);

// ==================== 颜色常量 ====================
const severityColorMap: Record<string, string> = {
  critical: '#d43130',
  warning: '#d97706',
  info: '#3b82f6',
};

// ==================== 辅助函数 ====================

/** 格式化金额 */
function formatUSD(value: number | string, decimals = 0): string {
  // 后端可能将金额作为字符串返回，String.toLocaleString 会忽略小数位选项，需先转数字
  return `$${Number(value).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

/** 将字符串中所有超过两位小数的数字截断为两位 */
function fixDecimals(text: string): string {
  return text.replace(/\d+\.\d{3,}/g, (n) => Number(n).toFixed(2));
}

/** 构建路径节点副文本 */
function formatPathSub(item: DrilldownPathItem): string {
  const parts: string[] = [];
  if (item.primary_metric != null) {
    parts.push(formatUSD(item.primary_metric, 2));
  }
  if (item.secondary_text) {
    parts.push(item.secondary_text);
  }
  if (item.change_rate != null) parts.push(`↑${item.change_rate}%`);
  if (item.alert_count && item.alert_count > 0)
    parts.push(`${item.alert_count} 条预警`);
  // 兜底：将结果中所有超过两位的小数统一截断为两位
  return fixDecimals(parts.join(' · '));
}

/** 指标状态中文文案 */
const metricStatusLabelMap: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  normal: '正常',
};

/** 指标状态中文文案（默认回退到原始值） */
function getMetricStatusLabel(status?: string): string {
  if (!status) return '';
  return metricStatusLabelMap[status] ?? status;
}

/** 指标副文本颜色 */
function getMetricSubColor(status?: string): string {
  if (status === 'critical') return '#ef4444';
  if (status === 'warning') return '#f59e0b';
  if (status === 'normal') return '#22c55e';
  return '#9ca3af';
}

/** 判断是否为百分比类指标 */
function isRateMetric(metric: DrilldownMetric): boolean {
  return ['ctr', 'cvr'].includes(metric.code) || metric.code.includes('rate');
}

/** 指标值前缀 */
function getMetricPrefix(metric: DrilldownMetric): string {
  return metric.unit === 'USD' ? '$' : '';
}

/** 指标值后缀 */
function getMetricSuffix(metric: DrilldownMetric): string {
  if (isRateMetric(metric)) return '%';
  return '';
}

/** 指标小数位（count 计数类不保留小数，其余统一保留两位） */
function getMetricDecimals(metric: DrilldownMetric): number {
  if (metric.unit === 'count') return 0;
  return 2;
}

/** 根据 ROAS 获取颜色 */
function getRoasColor(roas: number): string {
  if (roas >= 1.5) return '#22c55e';
  if (roas >= 1.0) return '#f59e0b';
  return '#ef4444';
}

// ==================== 计算属性 ====================

const pathSteps = computed(
  () =>
    drilldownData.value?.path.slice(0, -1).map((item, index) => ({
      no: index + 1,
      label: item.level_name,
      name: item.object_name,
      sub: formatPathSub(item),
      current: item.is_current ?? false,
      warning: !!(item.alert_count && item.alert_count > 0 && !item.is_current),
    })) ?? [],
);

const currentMetrics = computed(() =>
  // 后端可能将 value 作为字符串返回，统一转为数字，否则 CountTo 动画无法插值会停在 0
  (drilldownData.value?.current_metrics ?? []).map(
    (metric: DrilldownMetric) => ({
      ...metric,
      value: Number(metric.value),
    }),
  ),
);

const rootCauses = computed(() => drilldownData.value?.root_causes ?? []);

const childrenLevel = computed(() => {
  const level = drilldownData.value?.children?.level ?? '';
  const names: Record<string, string> = {
    adset: 'AdSet',
    ad: '广告',
    campaign: 'Campaign',
    account: '账户',
    region: '地区',
  };
  return names[level] ?? level.toUpperCase();
});

const childrenRows = computed(() => {
  const children = drilldownData.value?.children;
  if (!children?.items?.length) return [];
  // 下一层数据列表直接取 children.items（接口文档 2.2）
  return children.items.map((item: ChildrenItem) => ({
    name: item.object_name,
    subtitle: item.description ?? '',
    spend: item.metrics.spend != null ? formatUSD(item.metrics.spend, 2) : '-',
    cpa:
      item.metrics.cpa != null
        ? `$${Number(item.metrics.cpa).toFixed(2)}`
        : '-',
    roas: item.metrics.roas ?? 0,
    registrations: item.metrics.registrations ?? 0,
  }));
});

/** 下一层合计行（由 items 累加计算） */
const childrenSummary = computed(() => {
  const children = drilldownData.value?.children;
  const items = children?.items;
  if (!items?.length) return null;

  // 累加各项指标，CPA/ROAS 由总量加权计算
  let spend = 0;
  let registrations = 0;
  let conversions = 0;
  let weightedRoas = 0;
  for (const item of items) {
    const itemSpend = Number(item.metrics.spend ?? 0);
    const itemCpa = Number(item.metrics.cpa ?? 0);
    const itemReg = Number(item.metrics.registrations ?? 0);
    spend += itemSpend;
    registrations += itemReg;
    // 优先用注册数作为转化数；缺失时由 spend/cpa 反推，保证 CPA 能正确合计
    conversions +=
      itemReg > 0 ? itemReg : itemCpa > 0 ? itemSpend / itemCpa : 0;
    weightedRoas += Number(item.metrics.roas ?? 0) * itemSpend;
  }
  // CPA = 总消耗 / 总转化数；ROAS = 按消耗加权平均
  const cpa = conversions > 0 ? spend / conversions : 0;
  const roas = spend > 0 ? weightedRoas / spend : 0;

  const hidden = children?.summary?.hidden_count ?? 0;
  return {
    label: hidden > 0 ? `+ ${hidden} 个 ${childrenLevel.value} · 合计` : '合计',
    spend: formatUSD(spend, 2),
    cpa: `$${cpa.toFixed(2)}`,
    roas: Number(roas.toFixed(2)),
    registrations,
  };
});
// ==================== 事件处理 ====================

/** 执行根因建议动作 */
async function handleSuggestedAction(
  cause: RootCause,
  action: SuggestedAction,
) {
  await createDiagnosticAction({
    source: 'drilldown',
    source_id: cause.id,
    action: {
      type: action.type,
      target_level: action.target_level,
      target_id: action.target_id,
      target_status: action.target_status,
    },
    reason: cause.title,
  });
}

/** 导出完整报告（截图转 PDF 下载） */
async function handleExportReport() {
  const el = pageContentRef.value;
  if (!el) return;

  // PDF 相关依赖体积较大，仅在用户实际导出时下载，避免拖慢页面首次打开。
  const [{ default: html2canvas }, { default: jsPDF }] = await Promise.all([
    import('html2canvas'),
    import('jspdf'),
  ]);
  const canvas = await html2canvas(el, {
    useCORS: true,
    scale: 2,
    backgroundColor: '#f9fafb',
    height: el.scrollHeight,
    width: el.scrollWidth,
    windowHeight: el.scrollHeight,
    windowWidth: el.scrollWidth,
    onclone: (_doc, clonedEl) => {
      // html2canvas 对 overflow:hidden 的渲染会裁掉文字底部，在克隆副本里统一解除
      clonedEl.querySelectorAll<HTMLElement>('.truncate').forEach((node) => {
        node.style.overflow = 'visible';
        node.style.whiteSpace = 'normal';
      });
    },
  });
  const imgData = canvas.toDataURL('image/png');
  const imgWidth = canvas.width;
  const imgHeight = canvas.height;

  // A4 尺寸（单位 px，72dpi）：595 × 842，按图片宽度等比缩放
  const pdfWidth = 595;
  const pdfHeight = Math.round((imgHeight / imgWidth) * pdfWidth);
  const pdf = new jsPDF({
    orientation: pdfHeight > pdfWidth ? 'portrait' : 'landscape',
    unit: 'px',
    format: [pdfWidth, pdfHeight],
  });
  pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
  const title = drilldownData.value?.title ?? 'drilldown_report';
  pdf.save(`${title}.pdf`);
}

/** 通过签名 URL 触发浏览器下载 */
function triggerDownload(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.target = '_blank';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/** 导出下一层 CSV（复用 export 接口，section=children，返回 MinIO 签名 URL） */
async function handleExportCsv() {
  const children = drilldownData.value?.children;
  const query = route.query;
  if (!children?.items?.length || !query.level || !query.object_id) return;
  const res = await exportDrilldown({
    level: query.level as string,
    object_id: query.object_id as string,
    format: 'csv',
    section: 'children',
  });
  if (res?.download_url) {
    triggerDownload(
      res.download_url,
      `drilldown_children_${query.object_id}.csv`,
    );
  }
}

// ==================== 数据加载 ====================

/** 构建下钻查询参数 */
function buildQuery() {
  const q = route.query as Record<string, string>;
  return {
    level: q.level ?? '',
    object_id: q.object_id ?? '',
    project_id: q.project_id,
    platform: q.platform,
    agent_line: q.agent_line,
    account_id: q.account_id,
    campaign_id: q.campaign_id,
    adset_id: q.adset_id,
    ad_id: q.ad_id,
    window: q.window,
    baseline_window: q.baseline_window,
  };
}

// ==================== VxeGrid: CHILDREN ====================
const childrenGridOptions: VxeGridProps = {
  border: false,
  showFooter: true,
  cellConfig: { height: 52 },
  pagerConfig: { enabled: false },
  sortConfig: { trigger: 'cell', remote: false },
  headerCellStyle: () => ({ backgroundColor: '#ffffff' }),
  cellStyle: () => ({ fontSize: '0.875rem' }),
  data: [],
  columns: [
    {
      title: '对象',
      field: 'name',
      minWidth: 180,
      align: 'center',
      slots: {
        default: ({ row }: any) => [
          h(
            'div',
            { class: 'py-1' },
            [
              h(
                'div',
                { class: 'font-medium text-gray-900 truncate' },
                row.name,
              ),
              row.subtitle
                ? h(
                    'div',
                    { class: 'text-xs text-gray-400 mt-0.5 truncate' },
                    row.subtitle,
                  )
                : null,
            ].filter(Boolean),
          ),
        ],
      },
    },
    { title: '消耗', field: 'spend', minWidth: 100 },
    { title: 'CPA', field: 'cpa', minWidth: 90 },
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
            String(row.roas),
          ),
        ],
      },
    },
    { title: '注册', field: 'registrations', minWidth: 80, sortable: true },
  ],
  footerMethod: ({ columns }: any) => {
    const s = childrenSummary.value;
    if (!s) return [columns.map(() => '')];
    const map: Record<string, string> = {
      name: s.label,
      spend: s.spend,
      cpa: s.cpa,
      roas: String(s.roas),
      registrations: String(s.registrations),
    };
    return [columns.map((col: any) => map[col.field] ?? '')];
  },
};

const [ChildrenGrid, childrenGridApi] = useVbenVxeGrid({
  gridOptions: childrenGridOptions,
  gridClass: 'p-0',
});

watch(childrenRows, (rows) => {
  childrenGridApi.setGridOptions({ data: rows });
});

onMounted(async () => {
  const params = buildQuery();
  if (!params.level || !params.object_id) return;
  drilldownData.value = await getDrilldown(params);
});
</script>

<template>
  <Page auto-content-height class="adpulse-section-page bg-muted/40 p-0">
    <div
      ref="pageContentRef"
      class="flex h-full flex-col gap-[var(--adpulse-section-gap)]"
    >
      <div
        class="border-border bg-card shrink-0 rounded-[var(--adpulse-card-radius)] border px-[var(--adpulse-card-padding)] py-[var(--adpulse-card-padding)] shadow-[var(--adpulse-card-shadow)]"
      >
        <div class="flex items-end justify-between">
          <div>
            <h1
              class="text-foreground mb-1 font-semibold text-[var(--adpulse-page-title-size)]"
            >
              {{ drilldownData?.title ?? '加载中...' }}
            </h1>
            <p class="text-sm text-gray-400">
              {{ drilldownData?.summary }}
            </p>
          </div>
          <div class="mt-1 flex gap-2" data-html2canvas-ignore>
            <BaseButton @click="handleExportReport">导出报告</BaseButton>
          </div>
        </div>
      </div>

      <!-- PATH 下钻路径 -->
      <div
        class="border-border bg-card shrink-0 rounded-[var(--adpulse-card-radius)] border p-[var(--adpulse-card-padding)] shadow-[var(--adpulse-card-shadow)]"
      >
        <h2 class="text-foreground mb-4 text-sm font-semibold">下钻路径</h2>
        <div class="flex divide-x divide-gray-100" v-if="pathSteps.length > 0">
          <div
            v-for="step in pathSteps"
            :key="step.no"
            class="flex min-w-0 flex-1 flex-col px-4 first:pl-0"
          >
            <div class="mb-1 text-xs text-gray-400">
              {{ step.no }} · {{ step.label }}
            </div>
            <div
              class="mb-1 truncate text-sm font-bold leading-snug"
              :class="step.current ? 'text-orange-500' : 'text-gray-900'"
              :title="step.name"
            >
              {{ step.name }}
            </div>
            <div
              class="text-xs"
              :class="
                step.current
                  ? 'font-medium text-orange-500'
                  : step.warning
                    ? 'text-orange-400'
                    : 'text-gray-400'
              "
            >
              {{ step.sub }}
            </div>
          </div>
        </div>
        <div v-else class="text-sm text-gray-400">暂无路径数据</div>
      </div>

      <!-- CURRENT 当前层级指标 -->
      <div
        class="border-border bg-card shrink-0 rounded-[var(--adpulse-card-radius)] border p-[var(--adpulse-card-padding)] shadow-[var(--adpulse-card-shadow)]"
      >
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-foreground m-0 text-sm font-semibold">
            当前层级指标
          </h2>
          <span class="text-xs text-gray-400">
            数据窗口: {{ drilldownData?.window?.label ?? '近 30 分钟' }} ·
            自动刷新
          </span>
        </div>
        <div
          class="grid gap-4"
          :style="{
            gridTemplateColumns: `repeat(${Math.min(currentMetrics.length, 5)}, 1fr)`,
          }"
        >
          <div
            v-for="metric in currentMetrics"
            :key="metric.code"
            class="rounded-xl bg-gray-50 p-4"
          >
            <div class="mb-2 text-xs text-gray-400">{{ metric.name }}</div>
            <AnimatedCount
              :value="metric.value"
              :prefix="getMetricPrefix(metric)"
              :suffix="getMetricSuffix(metric)"
              :decimals="getMetricDecimals(metric)"
              class="text-foreground text-[calc(var(--adpulse-page-title-size)+3px)] font-semibold leading-tight"
            />
            <div
              v-if="metric.status"
              class="mt-1 text-xs"
              :style="{ color: getMetricSubColor(metric.status) }"
            >
              {{ getMetricStatusLabel(metric.status) }}
            </div>
          </div>
        </div>
      </div>

      <div
        class="grid min-h-0 flex-1 gap-[var(--adpulse-section-gap)] xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]"
      >
        <!-- DIAGNOSIS 根因诊断 -->
        <div
          class="border-border bg-card flex min-h-0 flex-col rounded-[var(--adpulse-card-radius)] border p-[var(--adpulse-card-padding)] shadow-[var(--adpulse-card-shadow)]"
        >
          <div class="mb-4 flex shrink-0 items-center justify-between">
            <h2 class="text-foreground m-0 text-sm font-semibold">根因诊断</h2>
            <span class="rounded-full px-2 py-0.5 text-xs text-gray-500">
              {{ rootCauses.length }} 项命中
            </span>
          </div>
          <div class="min-h-0 flex-1 space-y-3 overflow-y-auto">
            <div
              v-for="cause in rootCauses"
              :key="cause.id"
              class="relative overflow-hidden rounded-xl border border-gray-100 bg-white p-4 pl-5"
            >
              <div
                class="absolute bottom-0 left-0 top-0 w-1 rounded-l-xl"
                :style="{
                  backgroundColor:
                    severityColorMap[cause.severity] ?? '#6b7280',
                }"
              ></div>
              <div class="mb-2 flex items-center justify-between">
                <span
                  class="text-xs font-semibold"
                  :style="{
                    color: severityColorMap[cause.severity] ?? '#6b7280',
                  }"
                >
                  {{ cause.severity_label }} · {{ cause.category }}
                </span>
              </div>
              <div class="mb-1 text-sm font-bold leading-snug text-gray-900">
                {{ cause.title }}
              </div>
              <div class="mb-3 text-xs text-gray-500">
                {{ cause.description }}
              </div>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="action in cause.suggested_actions"
                  :key="action.label"
                  class="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
                  @click="handleSuggestedAction(cause, action)"
                >
                  {{ action.label }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- CHILDREN -->
        <div
          class="border-border bg-card flex min-h-0 flex-col rounded-[var(--adpulse-card-radius)] border p-[var(--adpulse-card-padding)] shadow-[var(--adpulse-card-shadow)]"
        >
          <div class="mb-4 flex shrink-0 items-center justify-between">
            <h2 class="text-foreground m-0 text-sm font-semibold">
              下一层 · {{ childrenLevel }}
            </h2>
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-500">按 30 分钟消耗↑</span>
              <button
                class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-gray-50"
                @click="handleExportCsv"
              >
                导出 CSV
              </button>
            </div>
          </div>
          <div class="min-h-0 flex-1">
            <ChildrenGrid />
          </div>
        </div>
      </div>
    </div>
  </Page>
</template>
