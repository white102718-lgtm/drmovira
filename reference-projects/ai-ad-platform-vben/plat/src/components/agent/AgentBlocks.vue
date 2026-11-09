<script lang="ts" setup>
import type { AgentBlock, AgentReportMetrics } from '#/api/agent';

import { ref } from 'vue';

import { IconifyIcon } from '@vben/icons';
import { Download, Eye, FileSpreadsheet } from 'lucide-vue-next';

import AgentBlobImage from '#/components/agent/AgentBlobImage.vue';
import AgentDownloadLink from '#/components/agent/AgentDownloadLink.vue';
import AgentExcelPreview from '#/components/agent/AgentExcelPreview.vue';

const props = defineProps<{
  blocks: AgentBlock[];
  disabled?: boolean;
}>();

const emit = defineEmits<{
  bind: [];
  choose: [optionId: string];
  confirm: [previewId: string, accept: boolean];
}>();

const METRIC_LABELS: [keyof AgentReportMetrics, string][] = [
  ['spend', '消耗'],
  ['registrations', '注册'],
  ['first_recharge_users', '首充'],
  ['registration_cost', '注册成本'],
  ['first_recharge_cost', '首充成本'],
];

const excelOpen = ref(false);
const excelUrl = ref('');
const excelName = ref('');

function metricEntries(metrics: AgentReportMetrics) {
  return METRIC_LABELS.filter(
    ([key]) => metrics?.[key] !== null && metrics?.[key] !== undefined,
  ).map(([key, label]) => ({
    label,
    value:
      typeof metrics[key] === 'number'
        ? (metrics[key] as number).toLocaleString('zh-CN')
        : String(metrics[key]),
  }));
}

function dateRange(start: string, end: string) {
  return start && end && start !== end ? `${start} ~ ${end}` : start || end;
}

function previewExcel(url: string, filename: string) {
  excelUrl.value = url;
  excelName.value = filename;
  excelOpen.value = true;
}

function onChoose(optionId: string) {
  if (props.disabled) return;
  emit('choose', optionId);
}

function onConfirm(previewId: string, accept: boolean) {
  if (props.disabled || !previewId) return;
  emit('confirm', previewId, accept);
}

function onBind() {
  if (props.disabled) return;
  emit('bind');
}
</script>

<template>
  <div class="space-y-3">
    <template v-for="(block, index) in blocks" :key="index">
      <p
        v-if="block.type === 'text'"
        class="m-0 whitespace-pre-wrap text-sm leading-7 text-slate-700"
      >
        {{ block.content }}
      </p>

      <div
        v-else-if="block.type === 'error'"
        class="flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-2 text-sm leading-6 text-rose-700"
      >
        <IconifyIcon icon="lucide:circle-alert" class="mt-1 shrink-0" />
        <span class="whitespace-pre-wrap">{{ block.content }}</span>
      </div>

      <div
        v-else-if="block.type === 'report'"
        class="rounded-xl border border-slate-200 bg-slate-50/60 p-4"
      >
        <p class="m-0 text-sm font-medium text-slate-800">{{ block.title }}</p>
        <p class="m-0 mt-0.5 text-xs text-slate-400">
          {{ block.payload.agent_line }}
          <span v-if="dateRange(block.payload.start_date, block.payload.end_date)">
            · {{ dateRange(block.payload.start_date, block.payload.end_date) }}
          </span>
          <span v-if="block.payload.timezone"> · {{ block.payload.timezone }}</span>
        </p>
        <dl class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div v-for="item in metricEntries(block.payload.metrics)" :key="item.label">
            <dt class="text-xs text-slate-500">{{ item.label }}</dt>
            <dd class="m-0 text-base font-semibold text-slate-900">
              {{ item.value }}
            </dd>
          </div>
        </dl>
        <p v-if="block.payload.caliber" class="m-0 mt-3 text-xs text-slate-400">
          口径：{{ block.payload.caliber }}
        </p>
      </div>

      <div v-else-if="block.type === 'choice'" class="space-y-2">
        <p class="m-0 text-sm leading-7 text-slate-700">{{ block.prompt }}</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="option in block.options"
            :key="option.id"
            type="button"
            :disabled="disabled"
            :title="option.hint || ''"
            class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-500 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            @click="onChoose(option.id)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <div
        v-else-if="block.type === 'confirm'"
        class="max-w-lg rounded-xl border border-slate-200 bg-white p-4"
      >
        <p class="m-0 text-sm font-medium text-slate-800">
          {{ block.payload?.title || '确认操作' }}
        </p>
        <dl class="mt-3 space-y-1 text-sm text-slate-600">
          <div v-if="block.payload?.account" class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-400">推送到</dt>
            <dd class="m-0">{{ block.payload.account }}</dd>
          </div>
          <div v-if="block.payload?.daily_budget" class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-400">频率</dt>
            <dd class="m-0">{{ block.payload.daily_budget }}</dd>
          </div>
          <div v-if="block.payload?.summary" class="flex gap-2">
            <dt class="w-16 shrink-0 text-slate-400">说明</dt>
            <dd class="m-0">{{ block.payload.summary }}</dd>
          </div>
        </dl>
        <div class="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            :disabled="disabled"
            class="rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            @click="onConfirm(block.payload?.preview_id, true)"
          >
            {{ block.payload?.confirm_label || '确认' }}
          </button>
          <button
            type="button"
            :disabled="disabled"
            class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            @click="onConfirm(block.payload?.preview_id, false)"
          >
            取消
          </button>
        </div>
      </div>

      <div
        v-else-if="block.type === 'feishu_bind'"
        class="max-w-lg rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
      >
        <p class="m-0 text-sm leading-6 text-slate-700">
          {{
            block.prompt ||
            '订时报会发到你的飞书私聊。请先绑定飞书，并在飞书里打开 AdPulse 机器人。'
          }}
        </p>
        <button
          type="button"
          :disabled="disabled"
          class="mt-3 rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          @click="onBind"
        >
          绑定飞书
        </button>
      </div>

      <AgentBlobImage
        v-else-if="block.type === 'image'"
        :url="block.url"
        :caption="block.caption"
      />

      <div
        v-else-if="block.type === 'file'"
        class="flex w-full max-w-lg items-center gap-2.5 rounded-lg border border-slate-200 bg-white px-3 py-2.5"
      >
        <span
          class="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-emerald-50 text-emerald-600"
          aria-hidden="true"
        >
          <FileSpreadsheet class="h-5 w-5" />
        </span>
        <button
          type="button"
          class="min-w-0 flex-1 text-left"
          @click="previewExcel(block.url, block.filename)"
        >
          <span class="block truncate text-sm text-slate-800">
            {{ block.filename }}
          </span>
          <span class="block text-xs text-slate-400">点击预览</span>
        </button>
        <button
          type="button"
          class="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
          @click="previewExcel(block.url, block.filename)"
        >
          <Eye class="h-3.5 w-3.5" />
          预览
        </button>
        <AgentDownloadLink
          class="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
          :url="block.url"
          :filename="block.filename || 'adpulse-export.xlsx'"
        >
          <Download class="h-3.5 w-3.5" />
          下载
        </AgentDownloadLink>
      </div>

      <a
        v-else-if="block.type === 'link'"
        :href="block.url"
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
      >
        {{ block.text }}
        <IconifyIcon icon="lucide:external-link" class="text-xs" />
      </a>

      <span
        v-else-if="block.type === 'demo_badge'"
        class="inline-block rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-700"
      >
        {{ block.content || '演示，非真实经营数据' }}
      </span>
    </template>

    <AgentExcelPreview
      v-model:open="excelOpen"
      :url="excelUrl"
      :filename="excelName"
    />
  </div>
</template>
