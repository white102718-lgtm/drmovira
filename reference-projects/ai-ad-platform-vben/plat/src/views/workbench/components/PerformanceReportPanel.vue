<script setup lang="ts">
import type { DeliveryReportResult } from '#/api/delivery-report';
import type { TableColumnsType } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Input,
  Modal,
  message,
  Table,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import { deliveryReportApi } from '#/api/delivery-report';
import DeliveryReportPanel from './DeliveryReportPanel.vue';
import { createReportWorkbook, downloadReportWorkbook } from './report-excel';
import type { ReportExportRow } from './report-excel';

const props = defineProps<{ reporterId?: string }>();
const range = ref<[Dayjs, Dayjs]>([dayjs().startOf('month'), dayjs()]);
const project = ref('');
const reporter = ref('');
const loading = ref(false);
const exporting = ref(false);
let disposed = false;
onBeforeUnmount(() => {
  disposed = true;
});
const failed = ref(false);
const result = ref<Awaited<ReturnType<typeof deliveryReportApi.performance>>>();
const filters = ref({ project: '', reporter: '' });
const detailDays = ref<DeliveryReportResult[]>([]);
const detailTitle = ref('关联日报');
const detailOpen = ref(false);
const fields = [
  { key: 'dailySpend', title: '日报消耗', money: true },
  { key: 'impressions', title: '展示' },
  { key: 'clicks', title: '点击' },
  { key: 'installs', title: '账户内安装' },
  { key: 'registrations', title: '账户内注册' },
  { key: 'firstPurchases', title: '账户内首购' },
  { key: 'adjustmentAmount', title: '调整金额', money: true },
  { key: 'secondaryDeduction', title: '二次核减', money: true },
] as const;
type MetricKey = (typeof fields)[number]['key'];
interface SummaryRow {
  key: string;
  projectId: string;
  projectName: string;
  reporterId: string;
  reporterName: string;
  departmentName: string;
  startDate: string;
  endDate: string;
  platforms: string[];
  lines: string[];
  adjustments: string[];
  actualSpend: number;
  metrics: Record<MetricKey, number>;
  days: DeliveryReportResult[];
}
/** 汇总与展开共用已保存日报；金额以分累加，避免小数浮点误差。 */
const summaries = computed(() => {
  const groups = new Map<string, SummaryRow>();
  const data = result.value;
  if (!data) return [];
  for (const day of data.days) {
    for (const row of day.rows) {
      if (!row.saved) continue;
      const key = JSON.stringify([day.reporterId, row.projectId]);
      let group = groups.get(key);
      if (!group) {
        group = {
          key,
          projectId: row.projectId,
          projectName: row.projectName,
          reporterId: day.reporterId,
          reporterName: day.reporterName,
          departmentName: day.departmentName || data.departmentName || '未设置',
          startDate: data.startDate,
          endDate: data.endDate,
          platforms: [],
          lines: [],
          adjustments: [],
          actualSpend: 0,
          metrics: {
            dailySpend: 0,
            impressions: 0,
            clicks: 0,
            installs: 0,
            registrations: 0,
            firstPurchases: 0,
            adjustmentAmount: 0,
            secondaryDeduction: 0,
          },
          days: [],
        };
        groups.set(key, group);
      }
      group.actualSpend += Math.round(Number(row.actualSpend || 0) * 100);
      for (const field of fields) {
        const amount = Number(row.metrics[field.key] || 0);
        group.metrics[field.key] +=
          'money' in field ? Math.round(amount * 100) : amount;
      }
      if (!group.platforms.includes(row.platform))
        group.platforms.push(row.platform);
      if (!group.lines.includes(row.agencyLineName))
        group.lines.push(row.agencyLineName);
      if (!group.adjustments.includes(row.metrics.adjustmentType))
        group.adjustments.push(row.metrics.adjustmentType);
      let detail = group.days.find(
        (item) => item.date === day.date && item.reporterId === day.reporterId,
      );
      if (!detail) {
        detail = { ...day, rows: [] };
        group.days.push(detail);
      }
      detail.rows.push(row);
    }
  }
  return [...groups.values()].filter(
    (row) =>
      row.projectName.toLowerCase().includes(filters.value.project) &&
      row.reporterName.toLowerCase().includes(filters.value.reporter),
  );
});
const columns: TableColumnsType<SummaryRow> = [
  {
    key: 'startDate',
    dataIndex: 'startDate',
    title: '开始日期',
    width: 130,
    fixed: 'left',
  },
  { key: 'endDate', dataIndex: 'endDate', title: '结束日期', width: 130 },
  {
    key: 'departmentName',
    dataIndex: 'departmentName',
    title: '所属部门',
    width: 160,
  },
  {
    key: 'reporterName',
    dataIndex: 'reporterName',
    title: '投放师',
    width: 140,
  },
  { key: 'projectName', dataIndex: 'projectName', title: '项目', width: 200 },
  { key: 'platforms', title: '平台', width: 160 },
  { key: 'actualSpend', title: '实际消耗', width: 140 },
  ...fields.map((field) => ({
    key: field.key,
    title: field.title,
    width: 140,
  })),
  { key: 'adjustments', title: '调整承担', width: 160 },
  { key: 'returnSpend', title: '含回流消耗', width: 140 },
  { key: 'returnIncrease', title: '回流增加额', width: 140 },
  { key: 'actions', title: '操作', width: 90, fixed: 'right' },
];
function displayValue(row: SummaryRow, key: string) {
  if (key === 'actualSpend') return (row.actualSpend / 100).toFixed(2);
  if (key === 'returnSpend')
    return ((row.actualSpend - row.metrics.adjustmentAmount) / 100).toFixed(2);
  if (key === 'returnIncrease')
    return ((row.actualSpend - row.metrics.dailySpend) / 100).toFixed(2);
  if (key === 'lines' || key === 'platforms' || key === 'adjustments')
    return row[key].join('、');
  const field = fields.find((item) => item.key === key);
  if (field)
    return 'money' in field
      ? (row.metrics[field.key] / 100).toFixed(2)
      : row.metrics[field.key];
  return row[key as keyof SummaryRow];
}
async function exportExcel() {
  if (
    loading.value ||
    exporting.value ||
    failed.value ||
    !result.value ||
    !summaries.value.length
  )
    return;
  exporting.value = true;
  const selected = result.value;
  try {
    const moneyKeys = new Set([
      'actualSpend',
      'dailySpend',
      'adjustmentAmount',
      'secondaryDeduction',
      'returnSpend',
      'returnIncrease',
    ]);
    const numericKeys = new Set(fields.map((field) => String(field.key)));
    const exportColumns = columns
      .filter((column) => column.key !== 'actions')
      .map((column) => ({
        key: String(column.key),
        title: String(column.title),
        money: moneyKeys.has(String(column.key)),
      }));
    const data: ReportExportRow[] = summaries.value.map((row) =>
      Object.fromEntries(
        exportColumns.map((column) => {
          const value = displayValue(row, column.key);
          return [
            column.key,
            moneyKeys.has(column.key) || numericKeys.has(column.key)
              ? Number(value)
              : String(value ?? ''),
          ];
        }),
      ),
    );
    const workbook = await createReportWorkbook(
      exportColumns,
      data,
      '绩效明细',
    );
    if (disposed) return;
    await downloadReportWorkbook(
      workbook,
      '绩效报表_' + selected.startDate + '_' + selected.endDate + '.xlsx',
    );
    message.success('已导出 ' + data.length + ' 条绩效明细');
  } catch {
    if (!disposed) message.error('导出失败，请重试');
  } finally {
    exporting.value = false;
  }
}
async function search() {
  if (loading.value || !range.value?.[0] || !range.value?.[1]) return;
  loading.value = true;
  failed.value = false;
  try {
    const data = await deliveryReportApi.performance(
      range.value[0].format('YYYY-MM-DD'),
      range.value[1].format('YYYY-MM-DD'),
      props.reporterId,
    );
    result.value = data;
    filters.value = {
      project: project.value.trim().toLowerCase(),
      reporter: reporter.value.trim().toLowerCase(),
    };
  } catch {
    failed.value = true;
    result.value = undefined;
  } finally {
    loading.value = false;
  }
}
function reset() {
  range.value = [dayjs().startOf('month'), dayjs()];
  project.value = '';
  reporter.value = '';
  void search();
}
function expand(row: SummaryRow) {
  detailDays.value = row.days;
  detailTitle.value = `${row.projectName} · ${row.reporterName} · ${row.startDate} 至 ${row.endDate}`;
  detailOpen.value = true;
}
onMounted(search);
</script>

<template>
  <div class="performance-report-panel min-w-0 space-y-4 pt-4">
    <Card>
      <form class="flex flex-wrap items-end gap-4" @submit.prevent="search">
        <label class="flex w-[300px] max-w-full flex-col gap-2"
          ><span>时间段</span
          ><DatePicker.RangePicker
            v-model:value="range"
            :allow-clear="false"
            :disabled="loading"
            class="w-full"
        /></label>
        <label class="flex w-[220px] max-w-full flex-col gap-2"
          ><span>投放师</span
          ><Input
            v-model:value="reporter"
            placeholder="请输入投放师姓名"
            allow-clear
        /></label>
        <label class="flex w-[220px] max-w-full flex-col gap-2"
          ><span>项目名称</span
          ><Input
            v-model:value="project"
            placeholder="请输入项目名称"
            allow-clear
        /></label>
        <div class="flex gap-2">
          <Button type="primary" html-type="submit" :loading="loading"
            >搜索</Button
          ><Button :disabled="loading" @click="reset">重置</Button>
        </div>
      </form>
    </Card>
    <Alert
      v-if="failed"
      type="error"
      show-icon
      message="绩效查询失败，请重新搜索。"
    />
    <Card title="绩效明细">
      <template #extra
        ><Button
          :loading="exporting"
          :disabled="loading || exporting || failed || summaries.length === 0"
          @click="exportExcel"
          >导出 Excel</Button
        ></template
      >
      <Table
        :columns="columns"
        :data-source="summaries"
        :loading="loading"
        row-key="key"
        :scroll="{ x: 2880 }"
        :pagination="{ pageSize: 20, showSizeChanger: true }"
      >
        <template #emptyText>所选时间段及筛选条件下暂无已保存的日报。</template>
        <template #bodyCell="{ column, record }">
          <Button
            v-if="column.key === 'actions'"
            type="link"
            @click="expand(record as SummaryRow)"
            >展开</Button
          >
          <template v-else>{{
            displayValue(record as SummaryRow, String(column.key))
          }}</template>
        </template>
      </Table>
    </Card>
    <Modal
      v-model:open="detailOpen"
      :title="detailTitle"
      :footer="null"
      width="94vw"
      destroy-on-close
    >
      <DeliveryReportPanel
        v-if="detailOpen"
        read-only
        :detail-days="detailDays"
      />
    </Modal>
  </div>
</template>

<style scoped></style>
