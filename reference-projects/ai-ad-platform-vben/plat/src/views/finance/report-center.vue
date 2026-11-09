<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import { computed, onMounted, reactive, ref, toRefs, watch } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Card,
  DatePicker,
  Empty,
  Input,
  Modal,
  Select,
  Table,
  Tag,
  message,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

defineOptions({ name: 'FinanceReportCenter' });

type ReportType = 'delivery' | 'material';

interface ApprovalReportRow {
  applicant: string;
  approvalComment: string;
  approvalProgress: string;
  approvalTime: string;
  approvalType: string;
  assignee: string;
  auditDate: string;
  duration: string;
  key: string;
  receivedAt: string;
  settlementMonth: string;
  spendAmount: string;
  taskNumber: string;
}

interface PerformanceDetailRow {
  adjustmentAmount: string;
  channelName: string;
  department: string;
  endDate: string;
  fbSpend: string;
  isSummary?: boolean;
  key: string;
  projectName: string;
  reporterName: string;
  returnAmount: string;
  startDate: string;
  taskName: string;
  workReportSpend: string;
}

const reportType = ref<ReportType>('delivery');
const filterDateRange = ref<[Dayjs, Dayjs]>();
const detailOpen = ref(false);
const selectedReport = ref<ApprovalReportRow>();
const filters = reactive({
  approvalProgress: undefined as string | undefined,
  name: '',
  taskNumber: '',
});
const routeStateReady = ref(false);
const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    fields: {
      date_range: {
        codec: {
          parse(value) {
            const dates = Array.isArray(value) ? value : [];
            return dates.length === 2 && dates[0] && dates[1]
              ? ([dayjs(dates[0]), dayjs(dates[1])] as [Dayjs, Dayjs])
              : undefined;
          },
          serialize(value) {
            return value?.map((date) => date.format('YYYY-MM-DD'));
          },
        },
      },
    },
    state: createListRouteStateTarget({
      ...toRefs(filters),
      date_range: filterDateRange,
      tab: reportType,
    }),
  });

watch(reportType, () => {
  if (routeStateReady.value) void commitQueryState();
});

onMounted(async () => {
  await restoreFromRoute();
  routeStateReady.value = true;
});

const deliveryRows: ApprovalReportRow[] = [
  {
    applicant: '苏智鹏',
    approvalComment: '日报与平台数据核验一致',
    approvalProgress: '已通过',
    approvalTime: '2026-08-26 10:18',
    approvalType: '投放花费审批',
    assignee: '周宁',
    auditDate: '2026-08-26',
    duration: '13分钟',
    key: 'delivery-report-1',
    receivedAt: '2026-08-26 10:05',
    settlementMonth: '',
    spendAmount: '$10.46',
    taskNumber: 'TF-20260826-0134',
  },
  {
    applicant: '周宁',
    approvalComment: '待财务复核调整金额',
    approvalProgress: '审批中',
    approvalTime: '—',
    approvalType: '投放花费审批',
    assignee: '苏智鹏',
    auditDate: '2026-08-25',
    duration: '2小时15分',
    key: 'delivery-report-2',
    receivedAt: '2026-08-25 15:40',
    settlementMonth: '',
    spendAmount: '$298.80',
    taskNumber: 'US-20260825-0021',
  },
  {
    applicant: '赵然',
    approvalComment: '等待项目负责人确认回流金额',
    approvalProgress: '待审批',
    approvalTime: '—',
    approvalType: '投放花费审批',
    assignee: '林悦',
    auditDate: '2026-08-24',
    duration: '46分钟',
    key: 'delivery-report-3',
    receivedAt: '2026-08-24 17:12',
    settlementMonth: '',
    spendAmount: '$164.20',
    taskNumber: 'SEA-20260824-0008',
  },
];

const materialRows: ApprovalReportRow[] = [
  {
    applicant: '周宁',
    approvalComment: '素材交付数量与结算单一致',
    approvalProgress: '已通过',
    approvalTime: '2026-08-26 11:02',
    approvalType: '素材月度结算',
    assignee: '赵然',
    auditDate: '2026-08-26',
    duration: '24分钟',
    key: 'material-report-1',
    receivedAt: '2026-08-26 10:38',
    settlementMonth: '2026-08',
    spendAmount: '',
    taskNumber: 'MT-202608-0041',
  },
  {
    applicant: '林悦',
    approvalComment: '正在核对素材修改次数',
    approvalProgress: '审批中',
    approvalTime: '—',
    approvalType: '素材月度结算',
    assignee: '陈墨',
    auditDate: '2026-08-25',
    duration: '1小时08分',
    key: 'material-report-2',
    receivedAt: '2026-08-25 16:20',
    settlementMonth: '2026-08',
    spendAmount: '',
    taskNumber: 'MT-202608-0037',
  },
  {
    applicant: '苏智鹏',
    approvalComment: '等待补充最终版素材链接',
    approvalProgress: '待审批',
    approvalTime: '—',
    approvalType: '素材月度结算',
    assignee: '许清',
    auditDate: '2026-08-24',
    duration: '35分钟',
    key: 'material-report-3',
    receivedAt: '2026-08-24 14:05',
    settlementMonth: '2026-07',
    spendAmount: '',
    taskNumber: 'MT-202607-0029',
  },
];

const rows = computed(() => {
  const source = reportType.value === 'delivery' ? deliveryRows : materialRows;
  return source.filter((row) => {
    const rowDate = new Date(row.auditDate).getTime();
    const inDateRange = filterDateRange.value
      ? rowDate >= filterDateRange.value[0].startOf('day').valueOf() &&
        rowDate <= filterDateRange.value[1].endOf('day').valueOf()
      : true;
    return (
      inDateRange &&
      (!filters.taskNumber ||
        row.taskNumber.includes(filters.taskNumber.trim())) &&
      (!filters.name || row.assignee.includes(filters.name.trim())) &&
      (!filters.approvalProgress ||
        row.approvalProgress === filters.approvalProgress)
    );
  });
});

const commonColumns: TableColumnsType<ApprovalReportRow> = [
  { dataIndex: 'taskNumber', key: 'taskNumber', title: '任务编号', width: 150 },
  { dataIndex: 'assignee', key: 'assignee', title: '投放师', width: 120 },
  { dataIndex: 'auditDate', key: 'auditDate', title: '审核日期', width: 140 },
  {
    dataIndex: 'spendAmount',
    key: 'spendAmount',
    title: '花费金额',
    width: 130,
  },
  {
    dataIndex: 'approvalProgress',
    key: 'approvalProgress',
    title: '审批进度',
    width: 130,
  },
  {
    dataIndex: 'approvalType',
    key: 'approvalType',
    title: '审批类型',
    width: 130,
  },
  {
    dataIndex: 'approvalComment',
    key: 'approvalComment',
    title: '审批意见',
    width: 160,
  },
  { dataIndex: 'applicant', key: 'applicant', title: '申请人', width: 120 },
  { dataIndex: 'receivedAt', key: 'receivedAt', title: '接收时间', width: 170 },
  {
    dataIndex: 'approvalTime',
    key: 'approvalTime',
    title: '审批时间',
    width: 170,
  },
  { dataIndex: 'duration', key: 'duration', title: '耗时', width: 110 },
  { key: 'actions', fixed: 'right', title: '操作', width: 110 },
];

const columns = computed<TableColumnsType<ApprovalReportRow>>(() => {
  if (reportType.value === 'delivery') return commonColumns;
  return [
    {
      dataIndex: 'taskNumber',
      key: 'taskNumber',
      title: '任务编号',
      width: 150,
    },
    { dataIndex: 'assignee', key: 'assignee', title: '素材师', width: 120 },
    {
      dataIndex: 'settlementMonth',
      key: 'settlementMonth',
      title: '结算月份',
      width: 140,
    },
    ...commonColumns.slice(4),
  ];
});

const detailColumns: TableColumnsType<PerformanceDetailRow> = [
  { dataIndex: 'startDate', key: 'startDate', title: '开始日期', width: 130 },
  { dataIndex: 'endDate', key: 'endDate', title: '结束日期', width: 130 },
  { dataIndex: 'department', key: 'department', title: '所属部门', width: 130 },
  {
    dataIndex: 'reporterName',
    key: 'reporterName',
    title: '投放师',
    width: 120,
  },
  {
    dataIndex: 'projectName',
    key: 'projectName',
    title: '项目名称',
    width: 150,
  },
  {
    dataIndex: 'channelName',
    key: 'channelName',
    title: '渠道名称',
    width: 170,
  },
  { dataIndex: 'taskName', key: 'taskName', title: '任务名称', width: 170 },
  { dataIndex: 'fbSpend', key: 'fbSpend', title: '花费金额（FB）', width: 150 },
  {
    dataIndex: 'workReportSpend',
    key: 'workReportSpend',
    title: '花费金额（日 报）',
    width: 170,
  },
  {
    dataIndex: 'adjustmentAmount',
    key: 'adjustmentAmount',
    title: '调整额',
    width: 120,
  },
  {
    dataIndex: 'returnAmount',
    key: 'returnAmount',
    title: '回流金额',
    width: 130,
  },
];

const detailRows = computed<PerformanceDetailRow[]>(() => {
  const report = selectedReport.value;
  if (!report) return [];
  const startDate = `${report.auditDate.slice(0, 7)}-01`;
  const base = {
    department: reportType.value === 'material' ? '素材协作组' : '投放组',
    endDate: report.auditDate,
    reporterName: report.assignee,
    startDate,
  };
  return [
    {
      ...base,
      adjustmentAmount: '$0',
      channelName: '—',
      fbSpend: '$263.12',
      key: 'detail-b14-summary',
      projectName: 'B14',
      returnAmount: '$72.29',
      taskName: 'B14-FB-10-2',
      workReportSpend: '$263.12',
    },
    {
      ...base,
      adjustmentAmount: '\\',
      channelName: 'BONU7-TF-TR-134',
      fbSpend: '$263.12',
      key: 'detail-b14-channel',
      projectName: 'B14',
      returnAmount: '$72.29',
      taskName: 'B14-FB-10-2',
      workReportSpend: '\\',
    },
    {
      ...base,
      adjustmentAmount: '$0',
      channelName: '—',
      fbSpend: '$26.41',
      key: 'detail-come-summary',
      projectName: 'come',
      returnAmount: '$0.19',
      taskName: 'come-nyc-313',
      workReportSpend: '$26.41',
    },
    {
      ...base,
      adjustmentAmount: '\\',
      channelName: 'NOVA-US-FB-021',
      fbSpend: '$26.41',
      key: 'detail-come-channel',
      projectName: 'come',
      returnAmount: '$0.19',
      taskName: 'come-nyc-313',
      workReportSpend: '\\',
    },
    {
      ...base,
      adjustmentAmount: '$0',
      channelName: 'SEA-TT-APP-008',
      fbSpend: '$146.54',
      key: 'detail-sea-channel',
      projectName: 'Aurora SEA',
      returnAmount: '$70.24',
      taskName: 'SEA-TT-APP-008',
      workReportSpend: '$146.54',
    },
    {
      adjustmentAmount: '$0',
      channelName: '\\',
      department: '\\',
      endDate: '\\',
      fbSpend: '$436.07',
      isSummary: true,
      key: 'detail-total',
      projectName: '\\',
      reporterName: '\\',
      returnAmount: '$142.72',
      startDate: '总计',
      taskName: '\\',
      workReportSpend: '$436.07',
    },
  ];
});

async function resetFilters() {
  await resetQueryState();
}

function progressColor(progress: string) {
  if (progress === '已通过') return 'success';
  if (progress === '审批中') return 'processing';
  if (progress === '已驳回') return 'error';
  return 'warning';
}

async function searchReports() {
  await commitQueryState();
  message.success('已按当前条件筛选报表');
}

function openDetails(report: ApprovalReportRow) {
  selectedReport.value = report;
  detailOpen.value = true;
}

function asApprovalReport(
  report: ApprovalReportRow | Record<string, unknown>,
): ApprovalReportRow {
  return report as ApprovalReportRow;
}

function detailRowClassName(record: PerformanceDetailRow) {
  return record.isSummary ? 'detail-summary-row' : '';
}

function exportReports() {
  message.success('报表导出任务已创建');
}
</script>

<template>
  <Page auto-content-height class="bg-slate-50" content-class="p-4 pb-6">
    <div class="mx-auto flex max-w-[1780px] flex-col gap-4">
      <Card :bordered="false" class="page-head-card">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 class="m-0 text-xl font-semibold text-slate-900">报表中心</h1>
            <p class="mb-0 mt-1 text-sm text-slate-500">
              集中查看投放花费与素材结算审批进度，支持筛选和导出。
            </p>
          </div>
          <Tag color="blue">审批报表</Tag>
        </div>
        <nav class="report-tabs" aria-label="报表类别">
          <button
            :class="{ active: reportType === 'delivery' }"
            type="button"
            @click="reportType = 'delivery'"
          >
            投放花费报表
          </button>
          <button
            :class="{ active: reportType === 'material' }"
            type="button"
            @click="reportType = 'material'"
          >
            素材结算报表
          </button>
        </nav>
      </Card>

      <Card :bordered="false" class="filter-card">
        <div class="filter-grid">
          <label
            ><span>日期</span
            ><DatePicker.RangePicker
              v-model:value="filterDateRange"
              class="w-full"
          /></label>
          <label
            ><span>任务编号</span
            ><Input
              v-model:value="filters.taskNumber"
              allow-clear
              placeholder="请输入任务编号"
              @press-enter="searchReports"
          /></label>
          <label
            ><span>{{ reportType === 'delivery' ? '投放师' : '素材师' }}</span
            ><Input
              v-model:value="filters.name"
              allow-clear
              :placeholder="`请输入${reportType === 'delivery' ? '投放师' : '素材师'}姓名`"
              @press-enter="searchReports"
          /></label>
          <label
            ><span>审批进度</span
            ><Select
              v-model:value="filters.approvalProgress"
              allow-clear
              placeholder="请选择审批进度"
              :options="[
                { label: '待审批', value: '待审批' },
                { label: '审批中', value: '审批中' },
                { label: '已通过', value: '已通过' },
                { label: '已驳回', value: '已驳回' },
              ]"
          /></label>
          <div class="filter-actions">
            <Button type="primary" @click="searchReports">搜索</Button
            ><Button @click="resetFilters">重置</Button>
          </div>
        </div>
      </Card>

      <Card :bordered="false" class="table-card">
        <template #title>{{
          reportType === 'delivery' ? '投放花费审批明细' : '素材结算审批明细'
        }}</template>
        <template #extra>
          <div class="flex gap-2">
            <Button @click="message.success('数据已刷新')"
              ><IconifyIcon icon="lucide:refresh-cw" class="mr-1" />刷新</Button
            >
            <Button @click="exportReports"
              ><IconifyIcon icon="lucide:upload" class="mr-1" />导出</Button
            >
          </div>
        </template>
        <Table
          :columns="columns"
          :data-source="rows"
          :pagination="{ pageSize: 10, showSizeChanger: true }"
          :row-selection="{}"
          :scroll="{ x: reportType === 'delivery' ? 1750 : 1600 }"
          row-key="key"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'approvalProgress'">
              <Tag :color="progressColor(record.approvalProgress)">
                {{ record.approvalProgress }}
              </Tag>
            </template>
            <template v-if="column.key === 'actions'"
              ><Button
                type="link"
                @click="openDetails(asApprovalReport(record))"
                >查看</Button
              ></template
            >
          </template>
          <template #emptyText><Empty description="暂无数据" /></template>
        </Table>
      </Card>
    </div>

    <Modal
      v-model:open="detailOpen"
      :footer="null"
      centered
      destroy-on-close
      title="绩效审核详情"
      :width="1600"
      wrap-class-name="performance-detail-modal"
    >
      <div class="detail-toolbar">
        <span class="detail-task-number">
          任务编号：{{ selectedReport?.taskNumber }}
        </span>
        <Button type="primary" @click="exportReports">
          <IconifyIcon icon="lucide:upload" class="mr-1" />导出
        </Button>
      </div>
      <Table
        class="performance-detail-table"
        :columns="detailColumns"
        :data-source="detailRows"
        :pagination="false"
        :row-class-name="detailRowClassName"
        :scroll="{ x: 1570, y: '56vh' }"
        row-key="key"
        table-layout="fixed"
      >
        <template #bodyCell="{ column, record }">
          <template
            v-if="
              column.key === 'startDate' &&
              !record.isSummary &&
              record.channelName === '—'
            "
          >
            <span class="detail-expand-cell">
              <IconifyIcon icon="lucide:chevron-down" />
              {{ record.startDate }}
            </span>
          </template>
        </template>
      </Table>
      <div class="detail-footer">
        <Button @click="detailOpen = false">关闭</Button>
      </div>
    </Modal>
  </Page>
</template>

<style scoped>
.page-head-card,
.filter-card,
.table-card {
  border: 1px solid #edf0f4;
  border-radius: 10px;
  box-shadow: 0 4px 14px rgb(15 23 42 / 4%);
}
.report-tabs {
  display: flex;
  gap: 32px;
  margin-top: 24px;
  border-bottom: 1px solid #e6e9ee;
}
.report-tabs button {
  position: relative;
  padding: 0 2px 13px;
  color: #647084;
  font-size: 15px;
}
.report-tabs button:hover,
.report-tabs button.active {
  color: #1677ff;
}
.report-tabs .active::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 3px;
  border-radius: 2px;
  background: #1677ff;
  content: '';
}
.filter-grid {
  display: grid;
  align-items: end;
  gap: 16px 20px;
  grid-template-columns: repeat(4, minmax(190px, 1fr)) auto;
}
.filter-grid label {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
  color: #4b5563;
  font-weight: 500;
}
.filter-actions {
  display: flex;
  gap: 8px;
}
.detail-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}
.detail-task-number {
  color: #64748b;
  font-size: 14px;
}
.detail-expand-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.detail-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  border-top: 1px solid #edf0f4;
  padding-top: 14px;
}
.performance-detail-table {
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}
.performance-detail-table :deep(.detail-summary-row > td) {
  background: #f5f7fa !important;
  font-weight: 600;
}
@media (max-width: 1200px) {
  .filter-grid {
    grid-template-columns: repeat(2, minmax(220px, 1fr));
  }
  .filter-actions {
    grid-column: 1/-1;
  }
}
@media (max-width: 640px) {
  .filter-grid {
    grid-template-columns: 1fr;
  }
  .filter-actions {
    grid-column: auto;
  }
}
</style>
