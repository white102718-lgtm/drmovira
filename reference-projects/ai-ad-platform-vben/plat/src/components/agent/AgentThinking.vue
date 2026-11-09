<script lang="ts" setup>
/**
 * 执行过程的工具调用链。
 *
 * 纯展示：步骤由父组件按 SSE 的 progress 事件折叠好传进来，这里只负责画和跳秒。
 * 计时器自己转，不靠父组件驱动，免得每 100ms 就把整条消息列表重渲染一遍。
 *
 * 两层：工具一行，工具内部的阶段（取数、写原因、出表）缩进挂在它下面。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

export interface ThinkingStep {
  /** 已写条数。慢阶段边跑边报，配 total 看。 */
  done?: number;
  /** 进行中的说法。慢步骤会说明在算什么，别让人以为卡住了。 */
  doing: string;
  elapsedMs?: number;
  error?: string;
  id: string;
  kind: 'llm' | 'phase' | 'tool';
  /** 做完之后的说法，短名词短语。 */
  label: string;
  name?: string;
  /** 阶段挂在哪一行工具下面。 */
  parentId?: string;
  /** 这一步开始的时间戳，用来给还在跑的那行走秒。 */
  startedAt?: number;
  state: 'done' | 'error' | 'running';
  total?: number;
}

interface Row {
  depth: number;
  step: ThinkingStep;
}

const props = withDefaults(
  defineProps<{
    /** 本轮开始的时间戳。父组件发起请求时记一次。 */
    startedAt: number;
    steps?: ThinkingStep[];
  }>(),
  { steps: () => [] },
);

const now = ref(Date.now());
let ticker: number | undefined;

onMounted(() => {
  // 100ms 一跳：够显示到 0.1 秒，又不至于烧 CPU
  ticker = window.setInterval(() => {
    now.value = Date.now();
  }, 100);
});

onBeforeUnmount(() => {
  if (ticker !== undefined) window.clearInterval(ticker);
});

const elapsed = computed(() =>
  Math.max(0, (now.value - props.startedAt) / 1000).toFixed(1),
);

const collapsed = ref(false);

/** 摊平成带缩进层级的行，阶段紧跟在它所属的工具后面。 */
const rows = computed<Row[]>(() => {
  const out: Row[] = [];
  for (const step of props.steps) {
    if (step.kind === 'phase') continue;
    out.push({ depth: 0, step });
    for (const phase of props.steps) {
      if (phase.kind === 'phase' && phase.parentId === step.id) {
        out.push({ depth: 1, step: phase });
      }
    }
  }
  return out;
});

/** 工具名 → 图标。认不出来的用通用图标，不影响可用。 */
const ICONS: Record<string, string> = {
  ask_user: 'lucide:circle-help',
  diagnose: 'lucide:activity',
  fetch: 'lucide:database',
  list_catalog: 'lucide:list',
  reasons: 'lucide:pen-line',
  render_chart: 'lucide:chart-column',
  resolve_scope: 'lucide:scan-search',
  workbook: 'lucide:file-spreadsheet',
};

function iconFor(step: ThinkingStep) {
  if (step.kind === 'llm') return 'lucide:brain';
  const name = step.name ?? '';
  if (ICONS[name]) return ICONS[name];
  if (name.startsWith('export_')) return 'lucide:file-down';
  if (name.startsWith('query_')) return 'lucide:database';
  return step.kind === 'phase' ? 'lucide:corner-down-right' : 'lucide:wrench';
}

/** 还在跑的那行走实时秒，跑完的定格在实际耗时。 */
function seconds(step: ThinkingStep) {
  const ms =
    step.state === 'running' && step.startedAt
      ? now.value - step.startedAt
      : step.elapsedMs;
  if (!ms || ms < 100) return '';
  return `${(ms / 1000).toFixed(1)}s`;
}

function counter(step: ThinkingStep) {
  if (!step.total) return '';
  return `${step.done ?? 0}/${step.total}`;
}

/** 竖线走到最后一行就收成半截，不然会往下悬空一段。 */
function lastRow(index: number) {
  return index === rows.value.length - 1;
}

function lastPhase(index: number) {
  const next = rows.value[index + 1];
  return !next || next.depth === 0;
}
</script>

<template>
  <div class="rounded-xl border border-slate-200 bg-slate-50/60">
    <button
      type="button"
      class="flex w-full items-center gap-2 px-3 py-2 text-left"
      :aria-expanded="!collapsed"
      @click="collapsed = !collapsed"
    >
      <IconifyIcon
        icon="lucide:loader-circle"
        class="shrink-0 animate-spin text-slate-400"
      />
      <span class="text-sm font-medium text-slate-700">正在执行</span>
      <!-- tabular-nums：跳秒时数字不左右抖 -->
      <span class="font-mono text-xs tabular-nums text-slate-500">
        {{ elapsed }} 秒
      </span>
      <IconifyIcon
        :icon="collapsed ? 'lucide:chevron-down' : 'lucide:chevron-up'"
        class="ml-auto shrink-0 text-slate-400"
      />
    </button>

    <ol v-if="!collapsed && rows.length > 0" class="m-0 list-none px-3 pb-2.5">
      <li
        v-for="(row, index) in rows"
        :key="row.step.id"
        class="relative flex items-center gap-2 py-1 text-xs"
        :class="row.depth === 1 ? 'pl-11' : 'pl-5'"
      >
        <!-- 外层竖线把工具串成一条链 -->
        <span
          class="absolute left-[7px] top-0 w-px bg-slate-200"
          :class="lastRow(index) ? 'h-1/2' : 'h-full'"
          aria-hidden="true"
        />
        <!-- 内层竖线把阶段挂在工具下面 -->
        <span
          v-if="row.depth === 1"
          class="absolute left-[30px] top-0 w-px bg-slate-200"
          :class="lastPhase(index) ? 'h-1/2' : 'h-full'"
          aria-hidden="true"
        />
        <span
          class="absolute flex items-center justify-center rounded-full"
          :class="[
            row.depth === 1 ? 'left-6 h-3 w-3' : 'left-0 h-3.5 w-3.5',
            {
              'bg-slate-100 text-slate-500': row.step.state === 'running',
              'bg-emerald-100 text-emerald-600': row.step.state === 'done',
              'bg-rose-100 text-rose-600': row.step.state === 'error',
            },
          ]"
        >
          <IconifyIcon
            v-if="row.step.state === 'running'"
            icon="lucide:loader-circle"
            class="animate-spin text-[9px]"
          />
          <IconifyIcon
            v-else-if="row.step.state === 'done'"
            icon="lucide:check"
            class="text-[9px]"
          />
          <IconifyIcon v-else icon="lucide:x" class="text-[9px]" />
        </span>

        <IconifyIcon
          :icon="iconFor(row.step)"
          class="shrink-0 text-slate-400"
          aria-hidden="true"
        />
        <span
          class="min-w-0 truncate"
          :class="
            row.step.state === 'error'
              ? 'text-rose-600'
              : row.step.state === 'running'
                ? 'text-slate-700'
                : 'text-slate-500'
          "
        >
          {{ row.step.state === 'running' ? row.step.doing : row.step.label }}
        </span>
        <span
          v-if="counter(row.step)"
          class="shrink-0 font-mono tabular-nums text-slate-400"
        >
          {{ counter(row.step) }}
        </span>
        <span
          v-if="seconds(row.step)"
          class="ml-auto shrink-0 font-mono tabular-nums text-slate-400"
        >
          {{ seconds(row.step) }}
        </span>
      </li>
    </ol>
  </div>
</template>
