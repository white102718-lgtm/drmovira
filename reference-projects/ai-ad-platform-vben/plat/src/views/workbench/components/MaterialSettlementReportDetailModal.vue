<script setup lang="ts">
import type { MonthlyReport } from '#/domain/report-rules';
import type { MaterialSettlementTaskLineSnapshot } from '#/domain/material-designer-settlement';
import type { ShadcnDataTableColumn } from '#/components/ui/ShadcnDataTable.vue';

import { computed } from 'vue';

import { Button, Modal } from 'ant-design-vue';

import ShadcnDataTable from '#/components/ui/ShadcnDataTable.vue';

interface MaterialSettlementSpendRow extends Record<string, string> {
  id: string;
  pitcherName: string;
  platform: string;
  projectName: string;
  settlementMonth: string;
  spend: string;
  taskLineName: string;
}

interface Props {
  modelValue: boolean;
  report?: MonthlyReport;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

const tableColumns: ShadcnDataTableColumn[] = [
  { dataIndex: 'projectName', key: 'projectName', title: '项目', width: 160 },
  {
    dataIndex: 'taskLineName',
    key: 'taskLineName',
    title: '任务线',
    width: 180,
  },
  { dataIndex: 'platform', key: 'platform', title: '投放平台', width: 120 },
  { dataIndex: 'pitcherName', key: 'pitcherName', title: '投放师', width: 120 },
  {
    align: 'center',
    dataIndex: 'settlementMonth',
    key: 'settlementMonth',
    title: '结算月份',
    width: 120,
  },
  {
    align: 'right',
    dataIndex: 'spend',
    key: 'spend',
    title: '花费金额',
    width: 150,
  },
];

const materialDesignerName = computed(
  () =>
    props.report?.fields.materialDesignerName || props.report?.author || '-',
);
const settlementMonth = computed(
  () => props.report?.fields.settlementMonth || '-',
);
const commissionRate = computed(() => {
  const rate = props.report?.fields.commissionRate?.trim();
  if (!rate || rate === '-') return '-';

  return rate.endsWith('%') ? rate : `${rate}%`;
});

function closeModal() {
  emit('update:modelValue', false);
}

function isTaskLineSnapshot(
  value: unknown,
): value is MaterialSettlementTaskLineSnapshot {
  if (!value || typeof value !== 'object') return false;

  const snapshot = value as Record<string, unknown>;
  return (
    typeof snapshot.id === 'string' &&
    typeof snapshot.name === 'string' &&
    typeof snapshot.pitcherName === 'string' &&
    typeof snapshot.platform === 'string' &&
    typeof snapshot.projectId === 'string' &&
    typeof snapshot.projectName === 'string'
  );
}

function parseTaskLineSnapshots(report: MonthlyReport) {
  const serializedSnapshot = report.fields.taskLineSnapshot;
  if (!serializedSnapshot) return [];

  try {
    const snapshot = JSON.parse(serializedSnapshot) as unknown;
    return Array.isArray(snapshot) ? snapshot.filter(isTaskLineSnapshot) : [];
  } catch {
    return [];
  }
}

function formatSpend(
  value: null | number | string | undefined,
  currency: string,
) {
  if (value === null || value === undefined || value === '') return '-';

  const amount = Number(value);
  if (!Number.isFinite(amount)) return '-';

  return `${currency || 'USD'} ${new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(amount)}`;
}

const spendRows = computed<MaterialSettlementSpendRow[]>(() => {
  const report = props.report;
  if (!report) return [];

  // 详情必须使用提交时固化的金额，避免底层广告数据变化后改写历史月报口径。
  return parseTaskLineSnapshots(report).map((taskLine) => ({
    id: taskLine.id,
    pitcherName: taskLine.pitcherName,
    platform: taskLine.platform,
    projectName: taskLine.projectName,
    settlementMonth: report.fields.settlementMonth ?? '-',
    spend: formatSpend(taskLine.spend, taskLine.currency ?? ''),
    taskLineName: taskLine.name,
  }));
});
</script>

<template>
  <Modal
    :footer="null"
    :open="modelValue"
    :width="'min(92vw, 960px)'"
    centered
    title="素材师月报详情"
    @cancel="closeModal"
  >
    <section class="space-y-4">
      <dl
        class="bg-muted/30 grid gap-3 rounded-lg border p-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        <div>
          <dt class="text-muted-foreground text-xs">素材师</dt>
          <dd class="mt-1 text-sm font-medium">{{ materialDesignerName }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground text-xs">结算月份</dt>
          <dd class="mt-1 text-sm font-medium">{{ settlementMonth }}</dd>
        </div>
        <div>
          <dt class="text-muted-foreground text-xs">提成比例</dt>
          <dd class="mt-1 text-sm font-medium">{{ commissionRate }}</dd>
        </div>
      </dl>

      <div>
        <h3 class="text-sm font-semibold">任务线月度花费</h3>
        <p class="text-muted-foreground mt-1 text-xs">
          展示月报提交时保存的任务线月度花费快照。
        </p>
      </div>

      <ShadcnDataTable
        :columns="tableColumns"
        :data="spendRows"
        empty-text="暂无提交时保存的任务线花费快照"
        :paginate="false"
        row-key="id"
      />

      <div class="flex justify-end border-t pt-4">
        <Button @click="closeModal">关闭</Button>
      </div>
    </section>
  </Modal>
</template>
