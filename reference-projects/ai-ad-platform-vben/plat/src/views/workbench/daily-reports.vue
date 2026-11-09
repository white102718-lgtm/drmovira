<script lang="ts" setup>
import type {
  TableColumnsType,
  TableProps,
  UploadFile,
  UploadProps,
} from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import type {
  MonthlyReport,
  ReportField,
  ReportRule,
  ReportRuleSnapshot,
} from '#/domain/report-rules';

import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';

import {
  Alert,
  Skeleton,
  Button,
  Card,
  DatePicker,
  Empty,
  Input,
  message,
  Modal,
  Select,
  Table,
  Upload,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  REPORT_RULES_UPDATED_EVENT,
  saveMonthlyReports,
} from '#/domain/report-rules';
import { useListRouteState } from '#/composables/use-list-route-state';
import {
  DELIVERY_DAILY_REPORT_ID,
  getFixedDailyReportRules,
  isFixedDailyReportRule,
  MATERIAL_DESIGNER_DAILY_REPORT_ID,
  PERFORMANCE_REPORT_ID,
} from '#/domain/fixed-daily-report-rules';
import { notifyDailyReportSubmitted } from '#/domain/daily-report-notification';
import {
  dailyReportApi,
  uploadDailyReportAttachment,
} from '#/api/daily-report';

import DeliveryReportPanel from './components/DeliveryReportPanel.vue';
import { deliveryReportApi } from '#/api/delivery-report';
import PerformanceReportPanel from './components/PerformanceReportPanel.vue';

import MaterialSettlementReportDetailModal from './components/MaterialSettlementReportDetailModal.vue';

defineOptions({ name: 'WorkbenchDailyReports' });

interface ReportTypeOption {
  icon: string;
  label: string;
  value: string;
}
interface DeliveryReportRow extends Record<string, string> {
  key: string;
}
interface DeliveryReportDraft extends Record<string, string> {
  key: string;
}
interface PerformanceReportRow {
  adjustmentAmount: string;
  channelName: string;
  department: string;
  endDate: string;
  fbSpend: string;
  key: string;
  projectName: string;
  reporterName: string;
  returnAmount: string;
  startDate: string;
  taskName: string;
  workReportSpend: string;
}

interface ConfiguredReportRow {
  author: string;
  canEdit: boolean;
  createdAt: string;
  key: string;
  reportDate: string;
  report: MonthlyReport;
  [key: string]: unknown;
}
interface ReportUser {
  id: string;
  name: string;
}

const userStore = useUserStore();
const router = useRouter();
const mode = ref<'person' | 'summary'>('person');
const selectedReportTypeId = ref(DELIVERY_DAILY_REPORT_ID);
const performanceView = ref<'detail' | 'summary'>('detail');
const deliveryReportUsers = ref<ReportUser[]>([]);
const selectedReportUserId = ref('');
const personFilterKeyword = ref('');
const reportTypeFilterKeyword = ref('');
const showTemplates = ref(false);
const showForm = ref(false);
const showMaterialSettlementDetail = ref(false);
// 权限相关的规则与提交记录只使用服务端当前用户数据，不能回退到浏览器缓存。
const visibleRules = ref<ReportRule[]>([]);
const permissionsLoading = ref(true);
const permissionsReady = ref(false);
const permissionsFailed = ref(false);
const reportsLoading = ref(true);
const reportsFailed = ref(false);
const reports = ref<MonthlyReport[]>([]);
const selectedRule = ref<ReportRule>();
const editingReport = ref<MonthlyReport>();
const materialSettlementDetailReport = ref<MonthlyReport>();
const formValues = reactive<Record<string, string | string[]>>({});
const attachmentFiles = reactive<Record<string, UploadFile[]>>({});
const uploadedAttachmentIds = new Map<string, string>();
const deliveryFormRows = ref<DeliveryReportDraft[]>([]);
const filterDateRange = ref<[Dayjs, Dayjs]>();
const appliedDateRange = ref<[Dayjs, Dayjs]>();
const reportFilters = reactive({
  projectName: '',
  reporterName: '',
  taskLineName: '',
});
const appliedFilters = reactive({
  projectName: '',
  reporterName: '',
  taskLineName: '',
});
const reportPage = ref(1);
const reportPageSize = ref(10);
const listRouteReady = ref(false);
const reportRouteState = {
  get date_range() {
    return appliedDateRange.value;
  },
  set date_range(value: [Dayjs, Dayjs] | undefined) {
    appliedDateRange.value = value;
    filterDateRange.value = value ? [...value] : undefined;
  },
  get mode() {
    return mode.value;
  },
  set mode(value: 'person' | 'summary') {
    mode.value = value;
  },
  get performance_view() {
    return performanceView.value;
  },
  set performance_view(value: 'detail' | 'summary') {
    performanceView.value = value;
  },
  get project_name() {
    return appliedFilters.projectName;
  },
  set project_name(value: string) {
    appliedFilters.projectName = value;
    reportFilters.projectName = value;
  },
  get report_type() {
    return selectedReportTypeId.value;
  },
  set report_type(value: string) {
    selectedReportTypeId.value = value;
  },
  get reporter_name() {
    return appliedFilters.reporterName;
  },
  set reporter_name(value: string) {
    appliedFilters.reporterName = value;
    reportFilters.reporterName = value;
  },
  get task_line_name() {
    return appliedFilters.taskLineName;
  },
  set task_line_name(value: string) {
    appliedFilters.taskLineName = value;
    reportFilters.taskLineName = value;
  },
};
const { commitQueryState, restoreFromRoute } = useListRouteState({
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
  pagination: {
    defaultPageSize: 10,
    page: reportPage,
    pageSize: reportPageSize,
    pageSizes: [10, 20, 50, 100],
  },
  state: reportRouteState,
});
const reportPagination = computed(() => ({
  current: reportPage.value,
  pageSize: reportPageSize.value,
  showSizeChanger: true,
}));
const handleReportTableChange: NonNullable<TableProps['onChange']> = (
  pagination,
) => {
  const nextPageSize = pagination.pageSize ?? reportPageSize.value;
  reportPage.value =
    nextPageSize === reportPageSize.value ? (pagination.current ?? 1) : 1;
  reportPageSize.value = nextPageSize;
  void commitQueryState();
};
// 与日报接口的 reporterName 保持一致，统一优先使用用户展示姓名。
const userName = computed(() => {
  const userInfo = userStore.userInfo;
  return (
    [userInfo?.displayName, userInfo?.full_name, userInfo?.realName]
      .find((name) => typeof name === 'string' && name.trim())
      ?.trim() || '当前用户'
  );
});
const currentReportUser = computed<ReportUser>(() => {
  const userInfo = userStore.userInfo as Record<string, unknown> | undefined;
  const id = [userInfo?.userId, userInfo?.user_id, userInfo?._id]
    .map((value) =>
      typeof value === 'string' || typeof value === 'number'
        ? String(value)
        : '',
    )
    .find(Boolean);

  return { id: id ?? '__current-user__', name: userName.value };
});
const personReportUsers = computed<ReportUser[]>(() => {
  // 日报与绩效的人员范围由后端会话权限决定，其余报表保持原有规则。
  if (
    [DELIVERY_DAILY_REPORT_ID, PERFORMANCE_REPORT_ID].includes(
      selectedReportTypeId.value,
    )
  ) {
    return deliveryReportUsers.value;
  }
  return [currentReportUser.value];
});
const filteredPersonReportUsers = computed(() => {
  const keyword = personFilterKeyword.value.trim();
  if (!keyword) return personReportUsers.value;

  return personReportUsers.value.filter((user) => user.name.includes(keyword));
});
const selectedReportUser = computed(
  () =>
    personReportUsers.value.find(
      (user) => user.id === selectedReportUserId.value,
    ) ?? currentReportUser.value,
);
selectedReportUserId.value = currentReportUser.value.id;
watch(
  personReportUsers,
  (users) => {
    if (!users.some((user) => user.id === selectedReportUserId.value)) {
      selectedReportUserId.value = users[0]?.id ?? '';
    }
  },
  { immediate: true },
);
const fixedDailyReportRules = getFixedDailyReportRules();
// 固定汇报中间包含绩效报表，不能按数组位置取值；否则会将绩效报表误当作素材师月报。
const deliveryDailyReportConfig = fixedDailyReportRules.find(
  (rule) => rule.id === DELIVERY_DAILY_REPORT_ID,
);
const materialDesignerMonthlyReportConfig = fixedDailyReportRules.find(
  (rule) => rule.id === MATERIAL_DESIGNER_DAILY_REPORT_ID,
);
const fixedDailyReportNames = new Map(
  fixedDailyReportRules.map((rule) => [rule.id, rule.name]),
);

const deliveryDailyRule: ReportRule = {
  ...deliveryDailyReportConfig!,
  fields: [
    { id: 'date', label: '日期', required: true, type: 'date' },
    { id: 'reporterName', label: '投手姓名', required: true, type: 'text' },
    { id: 'projectName', label: '项目名称', required: true, type: 'text' },
    { id: 'channelCode', label: '渠道号', required: true, type: 'text' },
    { id: 'platform', label: '平台', required: true, type: 'single-select' },
    { id: 'dailySpend', label: '日报消耗', required: true, type: 'number' },
    { id: 'impressions', label: '展示', required: false, type: 'number' },
    { id: 'clicks', label: '点击', required: false, type: 'number' },
    {
      id: 'inAccountInstalls',
      label: '账户内安装',
      required: false,
      type: 'number',
    },
    {
      id: 'inAccountRegistrations',
      label: '账户内注册',
      required: false,
      type: 'number',
    },
    {
      id: 'firstPurchase',
      label: '账户内首购',
      required: false,
      type: 'number',
    },
    {
      id: 'adjustmentAmount',
      label: '调整金额',
      required: false,
      type: 'number',
    },
    {
      id: 'secondaryDeduction',
      label: '二次核减',
      required: false,
      type: 'number',
    },
    {
      id: 'adjustmentType',
      label: '调整额类型',
      required: false,
      type: 'single-select',
    },
    { id: 'returnSpend', label: '含回流消耗', required: false, type: 'number' },
    { id: 'actualSpend', label: '实际消耗', required: false, type: 'number' },
    {
      id: 'returnSpendIncrease',
      label: '回流增加额',
      required: false,
      type: 'number',
    },
    { id: 'remark', label: '备注', required: false, type: 'textarea' },
  ],
};

const materialDesignerMonthlyRule: ReportRule = {
  ...materialDesignerMonthlyReportConfig!,
  fields: [
    {
      id: 'materialDesignerName',
      label: '素材师名称',
      required: true,
      type: 'text',
    },
    { id: 'contactPerson', label: '对接人', required: true, type: 'text' },
    { id: 'platforms', label: '投放平台', required: true, type: 'textarea' },
    { id: 'projectNames', label: '项目', required: true, type: 'textarea' },
    { id: 'taskLineNames', label: '任务线', required: true, type: 'textarea' },
    { id: 'totalSpend', label: '总消耗', required: false, type: 'number' },
    { id: 'settlementMonth', label: '结算月份', required: true, type: 'date' },
    { id: 'commissionRate', label: '提成比例', required: true, type: 'number' },
    { id: 'createdAt', label: '创建时间', required: true, type: 'date' },
    {
      id: 'reviewStatus',
      label: '汇报状态',
      required: true,
      type: 'single-select',
    },
  ],
};
const fixedDailyReportTemplates = [
  {
    kind: 'delivery',
    description: '按项目和代理线确认投放数据，补充截图后直接保存。',
    rule: deliveryDailyRule,
  },
  {
    kind: 'material',
    description: '提交素材师结算月报，并关联投放师、项目和任务线。',
    rule: materialDesignerMonthlyRule,
  },
] as const;
type FixedDailyReportTemplate = (typeof fixedDailyReportTemplates)[number];
/**
 * 固定日报的字段由前端业务表单维护，但人员范围仍以服务端日报规则为准。
 * 因此汇报对象、抄送人与查看人也必须在类型导航中看到对应日报，不能只展示填写人。
 */
const visibleReportRules = computed<ReportRule[]>(() =>
  visibleRules.value.map((rule) => {
    const fixedTemplate = fixedDailyReportTemplates.find(
      (template) => template.rule.id === rule.id,
    );
    const fixedRuleName = fixedDailyReportNames.get(rule.id);

    return {
      ...rule,
      fields: fixedTemplate ? fixedTemplate.rule.fields : rule.fields,
      // 固定日报改名后仍须以业务定义展示，避免服务端遗留名称继续出现在日报页。
      name: fixedRuleName ?? rule.name,
    };
  }),
);
/**
 * 写汇报入口与左侧日报导航共用服务端返回的可见规则。
 * canWrite 已由服务端按当前登录账号解析角色、部门和人员范围，避免两套接口
 * 在规则更新或权限同步期间返回不一致的结果。
 */
const writableRuleIds = computed(
  () =>
    new Set(
      visibleRules.value.filter((rule) => rule.canWrite).map((rule) => rule.id),
    ),
);
const templateRules = computed(() =>
  visibleReportRules.value.filter(
    (rule) => rule.canWrite === true && !isFixedDailyReportRule(rule.id),
  ),
);
const writableFixedDailyReportTemplates = computed<FixedDailyReportTemplate[]>(
  () =>
    fixedDailyReportTemplates.filter((template) =>
      writableRuleIds.value.has(template.rule.id),
    ),
);
const canWriteReports = computed(
  () =>
    writableFixedDailyReportTemplates.value.length > 0 ||
    templateRules.value.length > 0,
);
const reportTypeOptions = computed<ReportTypeOption[]>(() => [
  ...visibleReportRules.value.map((rule) => ({
    icon:
      rule.id === deliveryDailyRule.id
        ? 'lucide:calendar-days'
        : rule.id === PERFORMANCE_REPORT_ID
          ? 'lucide:chart-no-axes-combined'
          : rule.id === materialDesignerMonthlyRule.id
            ? 'lucide:palette'
            : 'lucide:file-text',
    label: rule.name,
    value: rule.id,
  })),
]);
const filteredReportTypeOptions = computed(() => {
  const keyword = reportTypeFilterKeyword.value.trim();
  if (!keyword) return reportTypeOptions.value;

  return reportTypeOptions.value.filter((reportType) =>
    reportType.label.includes(keyword),
  );
});
const selectedReportType = computed(() =>
  visibleReportRules.value.find(
    (rule) => rule.id === selectedReportTypeId.value,
  ),
);
watch(
  reportTypeOptions,
  (options) => {
    if (!permissionsReady.value || permissionsLoading.value) return;
    if (options.some((option) => option.value === selectedReportTypeId.value)) {
      return;
    }
    selectedReportTypeId.value = options[0]?.value ?? '';
  },
  { immediate: true },
);
const isPerformanceReportView = computed(
  () => selectedReportTypeId.value === PERFORMANCE_REPORT_ID,
);
const isDeliveryReportView = computed(
  () => selectedReportTypeId.value === deliveryDailyRule.id,
);
const formRule = computed(() => selectedRule.value ?? deliveryDailyRule);
const reportFieldOptions: Record<string, { label: string; value: string }[]> = {
  adjustmentType: [
    { label: '增加', value: '增加' },
    { label: '减少', value: '减少' },
  ],
  platform: [
    { label: 'Facebook', value: 'Facebook' },
    { label: 'Google', value: 'Google' },
    { label: 'TikTok', value: 'TikTok' },
  ],
  reviewStatus: [
    { label: '待审核', value: '待审核' },
    { label: '审核通过', value: '审核通过' },
    { label: '审核驳回', value: '审核驳回' },
  ],
};

function scalarFormValue(fieldId: string) {
  const value = formValues[fieldId];
  return Array.isArray(value) ? value.join('、') : value;
}

function hasDateFormat(
  value: unknown,
): value is { format: (template: string) => string } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'format' in value &&
    typeof value.format === 'function'
  );
}

function updateScalarFormValue(fieldId: string, value: unknown) {
  if (typeof value === 'string' || typeof value === 'number') {
    formValues[fieldId] = String(value);
    return;
  }
  formValues[fieldId] = hasDateFormat(value) ? value.format('YYYY-MM-DD') : '';
}

function resolveReportFieldOptions(field: ReportField) {
  if (field.options?.length) {
    return field.options.map((option) => ({ label: option, value: option }));
  }
  return reportFieldOptions[field.id] ?? [];
}

function formatCommissionRate(value: unknown) {
  const rate = String(value ?? '').trim();
  if (!rate || rate === '-') return '-';

  // 兼容历史数据可能已携带百分号，避免明细表重复追加单位。
  return rate.endsWith('%') ? rate : `${rate}%`;
}

const deliveryColumns = computed<TableColumnsType<DeliveryReportRow>>(() =>
  deliveryDailyRule.fields.map((field) => ({
    dataIndex: field.id,
    ellipsis: false,
    fixed: ['date', 'reporterName'].includes(field.id) ? 'left' : undefined,
    key: field.id,
    title: field.label,
    width: batchFieldWidth(field),
  })),
);
const performanceColumns: TableColumnsType<PerformanceReportRow> = [
  { dataIndex: 'startDate', key: 'startDate', title: '开始日期', width: 130 },
  { dataIndex: 'endDate', key: 'endDate', title: '结束日期', width: 130 },
  { dataIndex: 'department', key: 'department', title: '所属部门', width: 130 },
  {
    dataIndex: 'reporterName',
    key: 'reporterName',
    title: '投放师',
    width: 130,
  },
  {
    dataIndex: 'projectName',
    key: 'projectName',
    title: '项目名称',
    width: 160,
  },
  {
    dataIndex: 'channelName',
    key: 'channelName',
    title: '渠道名称',
    width: 140,
  },
  { dataIndex: 'taskName', key: 'taskName', title: '任务名称', width: 180 },
  { dataIndex: 'fbSpend', key: 'fbSpend', title: '花费金额（FB）', width: 150 },
  {
    dataIndex: 'workReportSpend',
    key: 'workReportSpend',
    title: '花费金额（日 报）',
    width: 165,
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
const displayedConfiguredReportFields = computed(() =>
  // 素材师名称与提交人一致，保留在汇报数据中，但不在明细表重复展示。
  (selectedReportType.value?.fields ?? []).filter(
    (field) => field.id !== 'materialDesignerName',
  ),
);
const configuredReportColumns = computed<TableColumnsType<ConfiguredReportRow>>(
  () => [
    { dataIndex: 'reportDate', key: 'reportDate', title: '日期', width: 130 },
    { dataIndex: 'author', key: 'author', title: '提交人', width: 130 },
    ...displayedConfiguredReportFields.value.map((field) => ({
      dataIndex: field.id,
      key: field.id,
      title: field.label,
      width: batchFieldWidth(field),
    })),
    { fixed: 'right', key: 'actions', title: '操作', width: 100 },
  ],
);

const submittedDeliveryReports = computed(() => {
  const submitted = reports.value.filter(
    (report) => report.ruleId === deliveryDailyRule.id,
  );
  return submitted;
});
function matchesSelectedReportUser(report: MonthlyReport) {
  if (mode.value !== 'person') return true;

  if (report.authorId) return report.authorId === selectedReportUser.value.id;
  const reporterName = report.fields.reporterName || report.author;
  return reporterName === selectedReportUser.value.name;
}
function canEditReport(report: MonthlyReport) {
  // 编辑权限只由服务端的提交人 ID 认定；姓名相同不能视为同一账号。
  return report.authorId === currentReportUser.value.id;
}

function openMaterialSettlementDetail(report: MonthlyReport) {
  materialSettlementDetailReport.value = report;
  showMaterialSettlementDetail.value = true;
}
const filteredDeliveryReports = computed(() =>
  submittedDeliveryReports.value.filter((report) => {
    const reportDate = report.fields.date
      ? new Date(report.fields.date).getTime()
      : 0;
    const inDateRange = appliedDateRange.value
      ? reportDate >= appliedDateRange.value[0].startOf('day').valueOf() &&
        reportDate <= appliedDateRange.value[1].endOf('day').valueOf()
      : true;
    return (
      inDateRange &&
      matchesSelectedReportUser(report) &&
      includesText(
        report.fields.reporterName || report.author,
        appliedFilters.reporterName,
      ) &&
      includesText(report.fields.projectName, appliedFilters.projectName) &&
      includesText(report.fields.taskLineName, appliedFilters.taskLineName)
    );
  }),
);
const deliveryReportRows = computed<DeliveryReportRow[]>(() =>
  filteredDeliveryReports.value.map((report) => ({
    key: report.id,
    ...Object.fromEntries(
      deliveryDailyRule.fields.map((field) => [
        field.id,
        report.fields[field.id] || '-',
      ]),
    ),
  })),
);
const performanceReportRows = computed<PerformanceReportRow[]>(() =>
  filteredDeliveryReports.value.map((report) => ({
    adjustmentAmount: report.fields.adjustmentAmount || '0',
    channelName: report.fields.channelCode || '-',
    department: report.fields.department || '-',
    endDate: report.fields.date || '-',
    fbSpend: report.fields.dailySpend || '0',
    key: report.id,
    projectName: report.fields.projectName || '-',
    reporterName: report.fields.reporterName || report.author,
    returnAmount: report.fields.returnSpendIncrease || '0',
    startDate: report.fields.date || '-',
    taskName: report.fields.taskName || report.fields.taskLineName || '-',
    workReportSpend: report.fields.dailySpend || '0',
  })),
);

function createRuleSnapshot(rule: ReportRule): ReportRuleSnapshot {
  return {
    deadline: rule.deadline,
    fields: rule.fields.map((field) => ({
      ...field,
      options: field.options?.map((option) => option),
    })),
    name: rule.name,
    period: rule.period,
  };
}

function getConfiguredReportDateValue(report: MonthlyReport) {
  const dateField = selectedReportType.value?.fields.find(
    (field) => field.type === 'date',
  );
  return dateField ? report.fields[dateField.id] : report.createdAt;
}

function getConfiguredReportDate(report: MonthlyReport) {
  const value = getConfiguredReportDateValue(report);
  return value ? new Date(value).getTime() : 0;
}

function formatConfiguredReportDate(report: MonthlyReport) {
  const value = getConfiguredReportDateValue(report);
  if (!value) return '-';

  const hasConfiguredDateField = selectedReportType.value?.fields.some(
    (field) => field.type === 'date',
  );
  return hasConfiguredDateField
    ? value
    : new Date(value).toLocaleDateString('zh-CN');
}

const configuredReportRows = computed<ConfiguredReportRow[]>(() =>
  reports.value
    .filter((report) => report.ruleId === selectedReportTypeId.value)
    .filter((report) => matchesSelectedReportUser(report))
    .filter((report) =>
      includesText(report.author, appliedFilters.reporterName),
    )
    .filter((report) => {
      if (!appliedDateRange.value) return true;

      const reportDate = getConfiguredReportDate(report);
      return (
        reportDate >= appliedDateRange.value[0].startOf('day').valueOf() &&
        reportDate <= appliedDateRange.value[1].endOf('day').valueOf()
      );
    })
    .map((report) => {
      return {
        author: report.author,
        // 固定汇报必须回到专用业务表单处理，不能用通用字段弹窗覆盖关联 ID 快照。
        canEdit:
          canEditReport(report) && !isFixedDailyReportRule(report.ruleId),
        createdAt: new Date(report.createdAt).toLocaleString('zh-CN', {
          hour12: false,
        }),
        key: report.id,
        report,
        reportDate: formatConfiguredReportDate(report),
        ...Object.fromEntries(
          (selectedReportType.value?.fields ?? []).map((field) => [
            field.id,
            report.fields[field.id] || '-',
          ]),
        ),
      };
    }),
);

function includesText(value: string | undefined, search: string) {
  return !search.trim() || (value ?? '').includes(search.trim());
}
/** 权限决定导航；只有请求成功后才校验当前标签，避免初始空列表覆盖默认选择。 */
async function loadReportPermissions() {
  permissionsLoading.value = true;
  permissionsFailed.value = false;
  try {
    const rules = await dailyReportApi.listVisibleRules();
    visibleRules.value = rules;
    if (!rules.some((rule) => rule.id === selectedReportTypeId.value)) {
      selectedReportTypeId.value = rules[0]?.id ?? '';
    }
    permissionsReady.value = true;
  } catch {
    permissionsFailed.value = true;
  } finally {
    permissionsLoading.value = false;
  }
}

/** 普通日报读取失败仅影响内容区，不清空已取得的导航权限。 */
async function loadReportData() {
  reportsLoading.value = true;
  reportsFailed.value = false;
  try {
    const persistedReports = await dailyReportApi.listReports();
    reports.value = persistedReports;
    saveMonthlyReports(persistedReports);
  } catch {
    reportsFailed.value = true;
  } finally {
    reportsLoading.value = false;
  }
}
async function syncRules() {
  await loadReportPermissions();
}

let deliveryDraftSequence = 0;

function defaultFieldValue(field: ReportField) {
  if (field.type === 'multi-select') return [];
  if (field.id === 'reporterName') return userName.value;
  if (field.id === 'date') return new Date().toISOString().slice(0, 10);
  return '';
}

function createDeliveryFormRow(rule = deliveryDailyRule): DeliveryReportDraft {
  deliveryDraftSequence += 1;
  return {
    key: `delivery-draft-${Date.now()}-${deliveryDraftSequence}`,
    ...(Object.fromEntries(
      rule.fields.map((field) => [field.id, defaultFieldValue(field)]),
    ) as Record<string, string>),
  };
}

function addDeliveryFormRow() {
  deliveryFormRows.value.push(createDeliveryFormRow(formRule.value));
}

function removeDeliveryFormRow(key: string) {
  if (deliveryFormRows.value.length === 1) {
    message.info('至少保留一条日报数据');
    return;
  }
  deliveryFormRows.value = deliveryFormRows.value.filter(
    (row) => row.key !== key,
  );
}

function batchFieldWidth(field: ReportField) {
  if (field.id === 'remark') return 220;
  if (field.id === 'channelCode' || field.id === 'projectName') return 180;
  if (field.id === 'reporterName') return 140;
  if (field.id === 'date') return 145;
  return 132;
}

function isAttachmentField(field: ReportField) {
  return field.type === 'image' || field.type === 'upload';
}

function beforeAttachmentUpload(
  field: ReportField,
): UploadProps['beforeUpload'] {
  return (file) => {
    if (field.type === 'image' && !file.type.startsWith('image/')) {
      message.warning(`${field.label} 仅支持图片文件`);
      return Upload.LIST_IGNORE;
    }
    const files = attachmentFiles[field.id] ?? [];
    if (files.length >= 10) {
      message.warning('每个日报字段最多上传 10 个附件');
      return Upload.LIST_IGNORE;
    }
    attachmentFiles[field.id] = [
      ...files,
      {
        name: file.name,
        originFileObj: file,
        size: file.size,
        status: 'done',
        type: file.type,
        uid: file.uid,
      },
    ];
    return Upload.LIST_IGNORE;
  };
}

function removeAttachment(fieldId: string, file: UploadFile) {
  attachmentFiles[fieldId] = (attachmentFiles[fieldId] ?? []).filter(
    (item) => item.uid !== file.uid,
  );
  uploadedAttachmentIds.delete(file.uid);
  return true;
}

async function uploadAttachments(rule: ReportRule) {
  const attachments: Record<string, Array<{ id: string; name: string }>> = {};
  for (const field of rule.fields.filter(isAttachmentField)) {
    const files = attachmentFiles[field.id] ?? [];
    if (field.required && files.length === 0) {
      throw new Error(`请上传${field.label}`);
    }
    if (files.length === 0) continue;
    attachments[field.id] = await Promise.all(
      files.map(async (file) => {
        const cachedId = uploadedAttachmentIds.get(file.uid);
        if (cachedId) return { id: cachedId, name: file.name };
        const original = file.originFileObj;
        if (!original)
          throw new Error(`附件“${file.name}”读取失败，请重新选择`);
        const uploaded = await uploadDailyReportAttachment(original);
        uploadedAttachmentIds.set(file.uid, uploaded.id);
        return { id: uploaded.id, name: uploaded.originalName };
      }),
    );
  }
  return attachments;
}

function openForm(rule: ReportRule, report?: MonthlyReport) {
  selectedRule.value = rule;
  editingReport.value = report;
  Object.keys(formValues).forEach((key) => delete formValues[key]);
  Object.keys(attachmentFiles).forEach((key) => delete attachmentFiles[key]);
  uploadedAttachmentIds.clear();
  deliveryFormRows.value = [];
  if (rule.id === deliveryDailyRule.id) {
    deliveryFormRows.value = [createDeliveryFormRow(rule)];
  }
  rule.fields.forEach((field) => {
    formValues[field.id] = defaultFieldValue(field);
    if (field.id === 'materialDesignerName') {
      formValues[field.id] = userName.value;
    }
    if (field.id === 'createdAt') {
      formValues[field.id] = new Date().toISOString().slice(0, 10);
    }
    if (report) {
      const value = report.fields[field.id] ?? '';
      formValues[field.id] =
        field.type === 'multi-select' && value
          ? value.split('、').filter(Boolean)
          : value;
    }
  });
  if (report?.attachments) {
    Object.entries(report.attachments).forEach(([fieldId, files]) => {
      attachmentFiles[fieldId] = files.map((file) => {
        const uid = `saved-${report.id}-${file.id}`;
        uploadedAttachmentIds.set(uid, file.id);
        return {
          name: file.name,
          status: 'done',
          uid,
        };
      });
    });
  }
  showTemplates.value = false;
  showForm.value = true;
}
async function submitReport() {
  const rule = selectedRule.value;
  if (!rule) return;

  if (rule.id === deliveryDailyRule.id) {
    for (const [index, row] of deliveryFormRows.value.entries()) {
      const missing = rule.fields.find(
        (field) => field.required && !row[field.id]?.trim(),
      );
      if (missing) {
        message.warning(`第 ${index + 1} 行请填写${missing.label}`);
        return;
      }
    }
    const createdAt = new Date().toISOString();
    const submitted = deliveryFormRows.value.map(
      (row, index): MonthlyReport => ({
        author: userName.value,
        createdAt,
        fields: Object.fromEntries(
          rule.fields.map((field) => [field.id, row[field.id] ?? '']),
        ),
        id: `report-${Date.now()}-${index}`,
        ruleId: rule.id,
        ruleSnapshot: createRuleSnapshot(rule),
      }),
    );
    reports.value.unshift(...submitted);
    saveMonthlyReports(reports.value);
    const notificationResults = await Promise.all(
      submitted.map((report) =>
        notifyDailyReportSubmitted({
          businessId: report.id,
          businessType: 'daily-report',
          reportName: rule.name,
        }),
      ),
    );
    showForm.value = false;
    selectedReportTypeId.value = deliveryDailyRule.id;
    if (notificationResults.every(Boolean)) {
      message.success(`已提交 ${submitted.length} 条投放日报`);
    } else {
      message.warning(
        `已提交 ${submitted.length} 条投放日报，但通知同步失败，请稍后重试。`,
      );
    }
    return;
  }

  const missing = rule.fields.find((field) => {
    if (!field.required) return false;
    const value = formValues[field.id];
    return Array.isArray(value) ? value.length === 0 : !value?.trim();
  });
  if (missing) {
    message.warning(`请填写${missing.label}`);
    return;
  }
  try {
    const attachments = await uploadAttachments(rule);
    const reportBeingEdited = editingReport.value;
    const isResubmission = Boolean(reportBeingEdited);
    const fields = Object.fromEntries(
      Object.entries(formValues).map(([key, value]) => [
        key,
        Array.isArray(value) ? value.join('、') : value,
      ]),
    );
    Object.entries(attachments).forEach(([fieldId, files]) => {
      fields[fieldId] = files.map((file) => file.name).join('、');
    });
    const report = reportBeingEdited
      ? await dailyReportApi.update(reportBeingEdited.id, {
          attachments,
          fields,
        })
      : await dailyReportApi.submit({
          attachments,
          fields,
          ruleId: rule.id,
        });
    if (isResubmission) {
      reports.value = reports.value.map((item) =>
        item.id === report.id ? report : item,
      );
    } else {
      reports.value.unshift(report);
    }
    saveMonthlyReports(reports.value);
    showForm.value = false;
    editingReport.value = undefined;
    selectedReportTypeId.value = rule.id;
    message.success(
      isResubmission
        ? '日报已重新提交并通知相关人员'
        : '汇报已提交，服务端已校验人员范围并投递通知',
    );
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '汇报提交失败，请稍后重试',
    );
  }
}
async function applyReportFilters() {
  appliedDateRange.value = filterDateRange.value
    ? [...filterDateRange.value]
    : undefined;
  Object.assign(appliedFilters, reportFilters);
  reportPage.value = 1;
  await commitQueryState();
}
async function resetReportFilters() {
  filterDateRange.value = undefined;
  appliedDateRange.value = undefined;
  Object.assign(reportFilters, {
    projectName: '',
    reporterName: '',
    taskLineName: '',
  });
  Object.assign(appliedFilters, reportFilters);
  reportPage.value = 1;
  await commitQueryState();
}
async function refreshData() {
  await Promise.all([loadReportPermissions(), loadReportData()]);
  if (!permissionsFailed.value && !reportsFailed.value)
    message.success('数据已更新');
}

function csvCell(value: unknown) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`;
}
function exportReport() {
  if (
    !selectedReportType.value ||
    isDeliveryReportView.value ||
    isPerformanceReportView.value
  ) {
    message.info('请先选择一个已配置的日报类型后导出');
    return;
  }
  const fields = selectedReportType.value.fields;
  const rows = [
    ['日期', '提交人', ...fields.map((field) => field.label)],
    ...configuredReportRows.value.map((row) => [
      row.reportDate,
      row.author,
      ...fields.map((field) => row[field.id] ?? ''),
    ]),
  ];
  const blob = new Blob(
    [`\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\n')}`],
    {
      type: 'text/csv;charset=utf-8',
    },
  );
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${selectedReportType.value.name}-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  // Keep the Blob URL alive briefly: some browsers begin downloading after the click task completes.
  window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  message.success(`已导出 ${configuredReportRows.value.length} 条当前筛选记录`);
}
onMounted(async () => {
  await restoreFromRoute();
  listRouteReady.value = true;
  window.addEventListener(REPORT_RULES_UPDATED_EVENT, syncRules);
  void deliveryReportApi
    .reporters()
    .then((users) => {
      deliveryReportUsers.value = users;
    })
    .catch(() => {
      deliveryReportUsers.value = [];
      message.error('日报可查看人员加载失败，请刷新重试');
    });
  await Promise.all([loadReportPermissions(), loadReportData()]);
});
watch([mode, selectedReportTypeId, performanceView], () => {
  if (!listRouteReady.value) return;
  reportPage.value = 1;
  void commitQueryState();
});
onBeforeUnmount(() =>
  window.removeEventListener(REPORT_RULES_UPDATED_EVENT, syncRules),
);
</script>

<template>
  <Page
    auto-content-height
    class="report-center-page bg-white"
    content-class="!min-h-0 !overflow-hidden"
  >
    <div
      v-if="!permissionsReady && permissionsLoading"
      class="space-y-4 p-4"
      role="status"
      aria-label="正在加载日报"
    >
      <Skeleton active :paragraph="{ rows: 1 }" />
      <Skeleton active :paragraph="{ rows: 6 }" />
    </div>
    <Alert
      v-else-if="!permissionsReady && permissionsFailed"
      type="error"
      show-icon
      message="日报权限加载失败"
    >
      <template #action
        ><Button @click="loadReportPermissions">重试</Button></template
      >
    </Alert>
    <div v-else class="report-center-shell">
      <aside class="report-side">
        <div class="mode-toggle">
          <button
            :aria-pressed="mode === 'person'"
            :class="{ active: mode === 'person' }"
            type="button"
            @click="mode = 'person'"
          >
            <IconifyIcon icon="lucide:users-round" />按人看
          </button>
          <button
            :aria-pressed="mode === 'summary'"
            :class="{ active: mode === 'summary' }"
            type="button"
            @click="mode = 'summary'"
          >
            <IconifyIcon icon="lucide:list-filter" />汇总看
          </button>
        </div>
        <Input
          v-if="mode === 'person'"
          v-model:value="personFilterKeyword"
          allow-clear
          class="report-side-filter"
          placeholder="筛选人员"
        >
          <template #prefix
            ><IconifyIcon aria-hidden="true" icon="lucide:search"
          /></template>
        </Input>
        <nav
          v-if="mode === 'person'"
          class="report-user-nav"
          aria-label="汇报人员"
        >
          <button
            v-for="reportUser in filteredPersonReportUsers"
            :key="reportUser.id"
            :aria-current="
              selectedReportUserId === reportUser.id ? 'page' : undefined
            "
            :class="{ active: selectedReportUserId === reportUser.id }"
            class="report-user-item"
            type="button"
            @click="selectedReportUserId = reportUser.id"
          >
            <span class="avatar-dot">{{ reportUser.name.slice(0, 1) }}</span>
            <span>{{ reportUser.name }}</span>
          </button>
          <span
            v-if="filteredPersonReportUsers.length === 0"
            class="report-side-empty"
            >未找到匹配人员</span
          >
        </nav>
        <template v-else>
          <Input
            v-model:value="reportTypeFilterKeyword"
            allow-clear
            class="report-side-filter"
            placeholder="筛选日报类型"
          >
            <template #prefix
              ><IconifyIcon aria-hidden="true" icon="lucide:search"
            /></template>
          </Input>
          <div class="report-side-divider" aria-hidden="true"></div>
          <nav class="report-type-nav" aria-label="日报类型">
            <button
              v-for="reportType in filteredReportTypeOptions"
              :key="reportType.value"
              :aria-current="
                selectedReportTypeId === reportType.value ? 'page' : undefined
              "
              :class="{ active: selectedReportTypeId === reportType.value }"
              class="report-type-item"
              type="button"
              @click="selectedReportTypeId = reportType.value"
            >
              <IconifyIcon :icon="reportType.icon" aria-hidden="true" />
              <span>{{ reportType.label }}</span>
            </button>
            <span
              v-if="filteredReportTypeOptions.length === 0"
              class="report-side-empty"
              >未找到匹配日报类型</span
            >
          </nav>
        </template>
      </aside>

      <main class="report-content">
        <Alert
          v-if="permissionsFailed"
          type="error"
          show-icon
          message="日报权限更新失败，请重试"
        >
          <template #action
            ><Button
              :loading="permissionsLoading"
              @click="loadReportPermissions"
              >重试</Button
            ></template
          >
        </Alert>
        <header class="report-page-actions">
          <h1 v-if="mode === 'summary'" class="report-page-title">
            {{ selectedReportType?.name ?? '日报类型' }}
          </h1>
          <div v-else class="person-heading">
            <span class="avatar-dot large">{{
              selectedReportUser.name.slice(0, 1)
            }}</span
            ><span>{{ selectedReportUser.name }}</span>
          </div>

          <div class="report-actions">
            <Button
              v-if="!isDeliveryReportView && !isPerformanceReportView"
              @click="refreshData"
              ><IconifyIcon
                icon="lucide:refresh-cw"
                class="mr-1"
              />更新数据</Button
            >
            <Button
              v-if="canWriteReports"
              type="primary"
              @click="showTemplates = true"
              ><IconifyIcon icon="lucide:pen-line" class="mr-1" />写汇报</Button
            >
          </div>
        </header>
        <nav
          v-if="mode === 'person'"
          class="report-tabs"
          aria-label="日报类型"
          role="tablist"
        >
          <button
            v-for="reportType in reportTypeOptions"
            :key="reportType.value"
            :aria-selected="selectedReportTypeId === reportType.value"
            :class="{ active: selectedReportTypeId === reportType.value }"
            role="tab"
            type="button"
            @click="selectedReportTypeId = reportType.value"
          >
            {{ reportType.label }}
          </button>
        </nav>
        <Empty
          v-if="reportTypeOptions.length === 0"
          description="暂无可查看的日报类型"
        />
        <Empty
          v-else-if="
            mode === 'person' &&
            (isDeliveryReportView || isPerformanceReportView) &&
            personReportUsers.length === 0
          "
          description="暂无可查看的投放师"
        />
        <template v-else-if="isDeliveryReportView || isPerformanceReportView"
          ><component
            :is="
              isPerformanceReportView
                ? PerformanceReportPanel
                : DeliveryReportPanel
            "
            read-only
            :reporter-id="mode === 'person' ? selectedReportUser.id : undefined"
            :key="
              selectedReportTypeId + ':' + mode + ':' + selectedReportUser.id
            "
        /></template>
        <Skeleton
          v-else-if="reportsLoading"
          active
          :paragraph="{ rows: 6 }"
          class="mt-4"
        />
        <Alert
          v-else-if="reportsFailed"
          type="error"
          show-icon
          message="日报数据加载失败，请重试"
          class="mt-4"
        >
          <template #action
            ><Button @click="loadReportData">重试</Button></template
          >
        </Alert>
        <template v-else>
          <Card class="filter-card" :bordered="false">
            <div class="filter-grid">
              <label
                ><span>日期</span
                ><DatePicker.RangePicker
                  v-model:value="filterDateRange"
                  class="filter-control"
              /></label>
              <label
                ><span>{{ isDeliveryReportView ? '投手姓名' : '提交人' }}</span
                ><Input
                  v-model:value="reportFilters.reporterName"
                  allow-clear
                  class="filter-control"
                  :placeholder="`请输入${isDeliveryReportView ? '投手姓名' : '提交人'}`"
                  @press-enter="applyReportFilters"
              /></label>
              <label v-if="isDeliveryReportView"
                ><span>项目名称</span
                ><Input
                  v-model:value="reportFilters.projectName"
                  allow-clear
                  class="filter-control"
                  placeholder="请输入项目名称"
                  @press-enter="applyReportFilters"
              /></label>
              <label v-if="isDeliveryReportView"
                ><span>任务线名称</span
                ><Input
                  v-model:value="reportFilters.taskLineName"
                  allow-clear
                  class="filter-control"
                  placeholder="请输入任务线名称"
                  @press-enter="applyReportFilters"
              /></label>
              <div class="filter-buttons">
                <Button type="primary" @click="applyReportFilters">搜索</Button
                ><Button @click="resetReportFilters">重置</Button>
              </div>
            </div>
          </Card>

          <Card class="report-table-card" :bordered="false">
            <template #title
              ><span>{{
                isPerformanceReportView
                  ? '绩效明细'
                  : `${selectedReportType?.name ?? '日报'}明细`
              }}</span></template
            >
            <template
              v-if="!isDeliveryReportView && !isPerformanceReportView"
              #extra
            >
              <div class="table-actions">
                <Button @click="exportReport"
                  ><IconifyIcon icon="lucide:upload" class="mr-1" />导出</Button
                >
              </div>
            </template>
            <template v-else #extra>
              <div v-if="isPerformanceReportView" class="table-actions">
                <Button @click="message.info('已展开全部明细')"
                  >一键展开</Button
                >
                <Button
                  :type="performanceView === 'detail' ? 'primary' : 'default'"
                  @click="performanceView = 'detail'"
                  >按明细</Button
                >
                <Button
                  :type="performanceView === 'summary' ? 'primary' : 'default'"
                  @click="performanceView = 'summary'"
                  >按汇总</Button
                >
                <Button @click="message.info('绩效审核功能待接入')"
                  >绩效审核</Button
                ><Button @click="message.info('暂无绩效提交记录')"
                  >绩效提交记录</Button
                ><Button @click="message.info('比例设置功能待接入')"
                  >比例设置</Button
                >
                <Button @click="exportReport"
                  ><IconifyIcon icon="lucide:upload" class="mr-1" />导出</Button
                >
              </div>
              <div v-else class="table-actions">
                <Button @click="exportReport"
                  ><IconifyIcon icon="lucide:upload" class="mr-1" />导出</Button
                >
              </div>
            </template>
            <Table
              v-if="isDeliveryReportView"
              class="wide-data-table"
              :columns="deliveryColumns"
              :data-source="deliveryReportRows"
              :pagination="reportPagination"
              :scroll="{ x: 2920 }"
              :sticky="{ offsetScroll: 8 }"
              table-layout="fixed"
              @change="handleReportTableChange"
              ><template #emptyText
                ><Empty
                  description="暂无投放日报，请点击右上角“写汇报”开始填写" /></template
            ></Table>
            <Table
              v-else-if="!isPerformanceReportView"
              class="custom-report-table"
              :columns="configuredReportColumns"
              :data-source="configuredReportRows"
              :pagination="reportPagination"
              :scroll="{ x: 1180 }"
              @change="handleReportTableChange"
            >
              <template #bodyCell="{ column, record }">
                <Button
                  v-if="
                    column.key === 'actions' &&
                    selectedReportTypeId === materialDesignerMonthlyRule.id
                  "
                  type="link"
                  @click="openMaterialSettlementDetail(record.report)"
                >
                  详情
                </Button>
                <Button
                  v-else-if="column.key === 'actions' && record.canEdit"
                  type="link"
                  @click="openForm(selectedReportType!, record.report)"
                >
                  编辑
                </Button>
                <span v-else-if="column.key === 'actions'">-</span>
                <span v-else-if="column.key === 'commissionRate'">
                  {{ formatCommissionRate(record.commissionRate) }}
                </span>
              </template>
              <template #emptyText
                ><Empty
                  :description="`暂无${selectedReportType?.name ?? '日报'}，请点击右上角“写汇报”开始填写`" /></template
            ></Table>
            <Table
              v-else
              :columns="performanceColumns"
              :data-source="performanceReportRows"
              :pagination="reportPagination"
              :scroll="{ x: 1600 }"
              @change="handleReportTableChange"
              ><template #emptyText
                ><Empty description="当前筛选条件下暂无绩效数据" /></template
            ></Table>
          </Card>
        </template>
      </main>
    </div>

    <Modal
      v-model:open="showTemplates"
      :footer="null"
      :width="1180"
      centered
      title="写汇报"
      wrap-class-name="write-report-modal"
    >
      <template #closeIcon
        ><IconifyIcon icon="lucide:x" class="size-7 text-slate-500"
      /></template>
      <template #title
        ><div class="write-report-title">
          <div>
            <b>写汇报</b>
            <p>请选择需要提交的日报或已配置的汇报模板。</p>
          </div>
        </div></template
      >
      <div class="template-picker-intro">
        <div>
          <span class="template-picker-icon"
            ><IconifyIcon aria-hidden="true" icon="lucide:clipboard-pen-line"
          /></span>
          <div>
            <strong>选择日报类型</strong>
            <p>投放日报填写后直接保存；素材师月报和其他模板按日报配置提交。</p>
          </div>
        </div>
        <span class="template-count">
          {{ writableFixedDailyReportTemplates.length + templateRules.length }}
          个可用模板
        </span>
      </div>
      <div class="template-cards">
        <button
          v-for="template in writableFixedDailyReportTemplates"
          :key="template.kind"
          :aria-label="`填写${template.rule.name}`"
          class="report-template"
          type="button"
          @click="
            router.push(
              template.kind === 'material'
                ? '/workbench/material-designer-monthly-report'
                : '/workbench/delivery-daily-report',
            )
          "
        >
          <div class="template-glow">
            <div class="template-card-heading">
              <span class="template-kind">
                <IconifyIcon
                  aria-hidden="true"
                  icon="lucide:shield-check"
                />固定业务表单
              </span>
              <IconifyIcon
                aria-hidden="true"
                class="template-arrow"
                icon="lucide:arrow-up-right"
              />
            </div>
            <h2>{{ template.rule.name }}</h2>
            <p class="template-frequency">{{ template.description }}</p>
            <span class="template-action"
              >填写汇报<IconifyIcon
                aria-hidden="true"
                icon="lucide:arrow-right"
            /></span>
          </div>
        </button>
        <button
          v-for="rule in templateRules"
          :key="rule.id"
          :aria-label="`填写${rule.name}`"
          class="report-template"
          type="button"
          @click="openForm(rule)"
        >
          <div class="template-glow">
            <div class="template-card-heading">
              <span class="template-kind template-kind-configured">
                <IconifyIcon
                  aria-hidden="true"
                  icon="lucide:sliders-horizontal"
                />配置模板
              </span>
              <IconifyIcon
                aria-hidden="true"
                class="template-arrow"
                icon="lucide:arrow-up-right"
              />
            </div>
            <h2>{{ rule.name }}</h2>
            <p class="template-frequency">
              {{ rule.period }}填写 · {{ rule.fields.length }} 个字段
            </p>
            <span class="template-action"
              >填写汇报<IconifyIcon
                aria-hidden="true"
                icon="lucide:arrow-right"
            /></span>
          </div>
        </button>
      </div>
    </Modal>
    <Modal
      v-model:open="showForm"
      :footer="null"
      :width="formRule.id === deliveryDailyRule.id ? 'min(88vw, 1280px)' : 760"
      centered
      wrap-class-name="report-form-modal"
    >
      <template #title
        ><div class="text-2xl font-semibold">
          {{ editingReport ? `编辑${formRule.name}` : formRule.name }}
        </div></template
      >
      <div
        v-if="formRule.id === deliveryDailyRule.id"
        class="report-batch-editor"
      >
        <div class="report-batch-hint">
          <div>
            <strong>批量填写投放日报</strong>
            <p>横向滚动可填写全部指标，每一行将生成一条日报记录。</p>
          </div>
          <span>共 {{ deliveryFormRows.length }} 条</span>
        </div>
        <div class="ux-native-table-viewport report-batch-scroll">
          <table class="report-batch-table">
            <thead>
              <tr>
                <th
                  v-for="field in formRule.fields"
                  :key="field.id"
                  :style="{ minWidth: `${batchFieldWidth(field)}px` }"
                >
                  {{ field.label }}<i v-if="field.required">*</i>
                </th>
                <th class="report-batch-action-column">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in deliveryFormRows" :key="row.key">
                <td
                  v-for="field in formRule.fields"
                  :key="field.id"
                  :style="{ minWidth: `${batchFieldWidth(field)}px` }"
                >
                  <Select
                    v-if="field.type === 'single-select'"
                    v-model:value="row[field.id]"
                    allow-clear
                    class="w-full"
                    :aria-label="`${field.label}，第 ${rowIndex + 1} 行`"
                    placeholder="请选择"
                    :options="resolveReportFieldOptions(field)"
                  />
                  <DatePicker
                    v-else-if="field.type === 'date'"
                    v-model:value="row[field.id]"
                    allow-clear
                    class="w-full"
                    format="YYYY-MM-DD"
                    :aria-label="`${field.label}，第 ${rowIndex + 1} 行`"
                    placeholder="请选择日期"
                    value-format="YYYY-MM-DD"
                  />
                  <Input
                    v-else
                    v-model:value="row[field.id]"
                    :aria-label="`${field.label}，第 ${rowIndex + 1} 行`"
                    :readonly="field.id === 'reporterName'"
                    :type="field.type === 'number' ? 'number' : 'text'"
                    placeholder="请输入"
                  />
                </td>
                <td class="report-batch-action-column">
                  <Button
                    danger
                    type="text"
                    :aria-label="`删除第 ${rowIndex + 1} 行日报`"
                    @click="removeDeliveryFormRow(row.key)"
                  >
                    <IconifyIcon icon="lucide:trash-2" />
                  </Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="report-batch-footer">
          <Button @click="addDeliveryFormRow">
            <template #icon>
              <IconifyIcon icon="lucide:plus" />
            </template>
            添加日报数据
          </Button>
          <div class="flex gap-3">
            <Button @click="showForm = false">取消</Button>
            <Button type="primary" @click="submitReport">
              提交 {{ deliveryFormRows.length }} 条汇报
            </Button>
          </div>
        </div>
      </div>
      <div v-else class="report-form-fields">
        <div
          v-for="field in formRule.fields"
          :key="field.id"
          class="report-form-field"
        >
          <label>{{ field.label }}<i v-if="field.required">*</i></label>
          <Input.TextArea
            v-if="field.type === 'textarea'"
            :value="scalarFormValue(field.id)"
            :rows="5"
            placeholder="请输入"
            @update:value="updateScalarFormValue(field.id, $event)"
          />
          <Select
            v-else-if="['multi-select', 'single-select'].includes(field.type)"
            v-model:value="formValues[field.id]"
            allow-clear
            class="w-full"
            :mode="field.type === 'multi-select' ? 'multiple' : undefined"
            placeholder="请选择"
            :options="resolveReportFieldOptions(field)"
          />
          <Upload.Dragger
            v-else-if="isAttachmentField(field)"
            :accept="field.type === 'image' ? 'image/*' : undefined"
            :before-upload="beforeAttachmentUpload(field)"
            :file-list="attachmentFiles[field.id] ?? []"
            :multiple="true"
            :on-remove="(file) => removeAttachment(field.id, file)"
          >
            <p class="mb-2">
              <IconifyIcon
                aria-hidden="true"
                class="size-6 text-slate-500"
                icon="lucide:paperclip"
              />
            </p>
            <p class="ant-upload-text">
              点击或拖拽上传{{ field.type === 'image' ? '图片' : '附件' }}
            </p>
            <p class="ant-upload-hint">
              文件将上传并绑定到本条日报，最多 10 个。
            </p>
          </Upload.Dragger>
          <DatePicker
            v-else-if="field.type === 'date'"
            :value="scalarFormValue(field.id)"
            allow-clear
            class="w-full"
            format="YYYY-MM-DD"
            placeholder="请选择日期"
            value-format="YYYY-MM-DD"
            @update:value="updateScalarFormValue(field.id, $event)"
          />
          <Input
            v-else
            :value="scalarFormValue(field.id)"
            :readonly="
              field.id === 'reporterName' || field.id === 'materialDesignerName'
            "
            :type="field.type === 'number' ? 'number' : 'text'"
            placeholder="请输入"
            @update:value="updateScalarFormValue(field.id, $event)"
          />
        </div>
      </div>
      <div
        v-if="formRule.id !== deliveryDailyRule.id"
        class="mt-6 flex justify-end gap-3"
      >
        <Button @click="showForm = false">取消</Button>
        <Button type="primary" @click="submitReport">
          {{ editingReport ? '重新提交' : '提交汇报' }}
        </Button>
      </div>
    </Modal>
    <MaterialSettlementReportDetailModal
      v-model="showMaterialSettlementDetail"
      :report="materialSettlementDetailReport"
    />
  </Page>
</template>

<style scoped>
.report-center-shell {
  display: flex;
}
.report-side {
  width: 250px;
  flex: none;
  border-right: 1px solid #e3e6ea;
  padding: 18px 16px;
}
.mode-toggle {
  display: grid;
  grid-template-columns: 1fr 1fr;
  overflow: hidden;
  border: 1px solid #cdd3dc;
  border-radius: 7px;
}
.mode-toggle button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 10px 5px;
  color: #343b45;
  font-size: 15px;
}
.mode-toggle button + button {
  border-left: 1px solid #cdd3dc;
}
.mode-toggle .active {
  color: #356dff;
  box-shadow: inset 0 0 0 1px #356dff;
}
.report-side p {
  margin: 34px 12px 14px;
  color: #7f8792;
  font-size: 14px;
}
.person-item {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 12px;
  border-radius: 6px;
  padding: 10px 12px;
  color: #356dff;
  font-size: 15px;
  text-align: left;
}
.person-item.active {
  background: #e9efff;
}
.avatar-dot {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(145deg, #744eff, #12b6ec);
  color: #fff;
  font-size: 14px;
}
.avatar-dot.large {
  width: 44px;
  height: 44px;
}
.report-content {
  min-width: 0;
  flex: 1;
  padding: 22px 32px 44px;
}
.person-heading {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 20px;
  font-weight: 600;
}
.report-tabs {
  display: flex;
  gap: 30px;
  margin-top: 30px;
  border-bottom: 1px solid #e1e4e8;
}
.report-tabs button {
  position: relative;
  padding: 0 2px 14px;
  color: #5f6b7a;
  font-size: 17px;
}
.report-tabs button:hover,
.report-tabs button.active {
  color: #356dff;
}
.report-tabs .active::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 3px;
  border-radius: 2px;
  background: #356dff;
  content: '';
}
.report-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 22px 0 18px;
}
.report-title-row h1 {
  margin: 0;
  color: #252b35;
  font-size: 22px;
  font-weight: 600;
}
.report-actions,
.table-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.dashboard {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  padding: 16px;
  border-radius: 10px;
  background: #f2f3f5;
}
.dashboard h3 {
  margin: 6px 0 16px;
  font-size: 16px;
}
.legend {
  color: #7f8792;
}
.legend i {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 6px;
  border-radius: 50%;
  background: #356dff;
}
.legend .teal {
  margin-left: 14px;
  background: #24c6bd;
}
.legend .yellow {
  margin-left: 14px;
  background: #ffbe0b;
}
.donut {
  display: grid;
  width: 142px;
  height: 142px;
  place-items: center;
  margin: 48px auto 0;
  border: 21px solid #356dff;
  border-radius: 50%;
}
.donut div {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.donut strong {
  font-size: 30px;
}
.donut span {
  color: #7f8792;
}
.simple-chart {
  position: relative;
  display: flex;
  height: 166px;
  flex-direction: column;
  justify-content: space-between;
  margin: 30px 18px 0 30px;
  border-bottom: 1px solid #dce0e6;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0,
    transparent 54px,
    #e4e6eb 55px
  );
  color: #9aa2ad;
}
.simple-chart b {
  position: absolute;
  top: 42px;
  left: 52%;
  color: #356dff;
  font-size: 18px;
}
.simple-chart em {
  position: absolute;
  right: 6px;
  bottom: -28px;
  font-style: normal;
}
.interaction b {
  color: #e3be00;
}
.filter-card,
.report-table-card {
  margin-top: 16px;
  border: 1px solid #eef0f3;
  border-radius: 10px;
  box-shadow: 0 5px 14px rgb(15 23 42 / 4%);
}
.filter-grid {
  display: grid;
  align-items: end;
  gap: 14px 18px;
  grid-template-columns: repeat(4, minmax(180px, 1fr)) auto;
}
.filter-grid label {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
  color: #4b5563;
  font-weight: 500;
}
.filter-control {
  width: 100%;
}
.filter-buttons {
  display: flex;
  gap: 8px;
}
.template-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  padding: 20px 28px 180px;
}
.report-template {
  min-height: 330px;
  overflow: hidden;
  border-radius: 12px;
  background: linear-gradient(145deg, #d4e2ff, #f9fbff 45%, #fff);
  box-shadow: 0 8px 18px rgb(15 23 42 / 5%);
  text-align: left;
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
}
.report-template:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 26px rgb(53 109 255 / 15%);
}
.template-glow {
  padding: 38px 30px;
}
.template-glow h2 {
  margin: 0 0 18px;
  color: #283142;
  font-size: 24px;
}
.template-frequency {
  min-height: 20px;
  margin: 0 0 18px;
  color: #4e73c8;
  font-size: 13px;
}
.template-glow div {
  border-bottom: 1px solid #e6e9ee;
  padding: 13px 0;
}
.template-glow b,
.template-glow span {
  display: block;
}
.template-glow span {
  margin-top: 8px;
  color: #9da5af;
}
.report-form-fields {
  display: grid;
  max-height: min(60vh, 640px);
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
  overflow-y: auto;
  padding-right: 4px;
}
.report-form-field {
  margin-top: 22px;
}
.report-form-field label {
  display: block;
  margin-bottom: 8px;
  color: #303743;
  font-weight: 600;
}
.report-form-field i {
  margin-left: 3px;
  color: #ff4d4f;
  font-style: normal;
}
.report-batch-editor {
  display: grid;
  gap: 14px;
}
.report-batch-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #eff6ff;
  padding: 12px 16px;
}
.report-batch-hint strong {
  color: #1e3a8a;
  font-size: 14px;
}
.report-batch-hint p {
  margin: 3px 0 0;
  color: #64748b;
  font-size: 12px;
}
.report-batch-hint > span {
  flex: none;
  border-radius: 999px;
  background: #dbeafe;
  padding: 4px 10px;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
}
.report-batch-scroll {
  scrollbar-color: #94a3b8 #edf1f5;
  scrollbar-gutter: stable;
}
.report-batch-table {
  width: max-content;
  min-width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: white;
}
.report-batch-table th,
.report-batch-table td {
  border-right: 1px solid #edf0f4;
  border-bottom: 1px solid #edf0f4;
  padding: var(--adpulse-table-cell-padding-block)
    var(--adpulse-table-cell-padding-inline);
  text-align: left;
  vertical-align: middle;
}
.report-batch-table th {
  position: sticky;
  z-index: 3;
  top: 0;
  background: #f8fafc;
  color: #526071;
  height: var(--adpulse-table-header-height);
  font-size: var(--adpulse-control-font-size);
  font-weight: 600;
  white-space: nowrap;
}
.report-batch-table th i {
  margin-left: 2px;
  color: #ef4444;
  font-style: normal;
}
.report-batch-table tbody tr:hover td {
  background: #f8fbff;
}
.report-batch-action-column {
  position: sticky;
  z-index: 2;
  right: 0;
  width: 70px;
  min-width: 70px;
  background: white;
  box-shadow: -2px 0 8px rgb(15 23 42 / 5%);
  text-align: center !important;
}
.report-batch-table th.report-batch-action-column {
  z-index: 4;
  background: #f8fafc;
}
.report-batch-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
@media (max-width: 1400px) {
  .filter-grid {
    grid-template-columns: repeat(2, minmax(220px, 1fr));
  }
  .filter-buttons {
    grid-column: 1/-1;
  }
}
@media (max-width: 1100px) {
  .dashboard {
    grid-template-columns: 1fr;
  }
  .template-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .report-side {
    width: 210px;
  }
  .report-content {
    padding: 22px;
  }
}
@media (max-width: 720px) {
  .report-side {
    display: none;
  }
  .report-content {
    padding: 16px;
  }
  .report-title-row {
    align-items: flex-start;
    flex-direction: column;
  }
  .report-actions,
  .table-actions {
    width: 100%;
  }
  .filter-grid {
    grid-template-columns: 1fr;
  }
  .filter-buttons {
    grid-column: auto;
  }
  .template-cards,
  .report-form-fields {
    grid-template-columns: 1fr;
  }
  .template-cards {
    padding: 12px;
  }
  .report-batch-footer {
    align-items: stretch;
    flex-direction: column;
  }
  .report-batch-footer > div {
    justify-content: flex-end;
  }
}

/* 保持日报中心为数据工作台，而不是装饰性看板。 */
.report-center-shell {
  gap: 16px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: hsl(var(--muted) / 0.4);
}
.report-side {
  width: 232px;
  min-height: 0;
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
  padding: 20px 14px;
}
.mode-toggle {
  border-color: #e5e5e5;
  border-radius: 9px;
  background: #fafafa;
}
.mode-toggle button {
  min-height: 40px;
  padding: 8px 5px;
  color: #525252;
  font-size: 13px;
}
.mode-toggle button + button {
  border-left-color: #e5e5e5;
}
.mode-toggle .active {
  background: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
  box-shadow: none;
}
.report-side p {
  margin: 28px 10px 10px;
  color: #737373;
  font-size: 12px;
  font-weight: 500;
}
.person-item {
  border-radius: 9px;
  padding: 10px;
  color: #404040;
  font-size: 14px;
}
.person-item.active {
  background: #f5f5f5;
}
.avatar-dot {
  width: 32px;
  height: 32px;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
}
.report-content {
  min-height: 0;
  overflow-y: auto;
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
  padding: 16px;
}
.report-page-actions {
  display: flex;
  min-height: 40px;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
}
.report-page-title,
.report-page-actions > .person-heading {
  margin: 0 auto 0 0;
}
.report-page-title {
  color: #171717;
  font-size: 24px;
  font-weight: 600;
  white-space: nowrap;
}
.report-page-actions > .text-slate-400 {
  white-space: nowrap;
}
.report-page-actions .report-actions {
  width: auto;
  margin-top: 0;
}
.person-heading {
  gap: 10px;
  color: hsl(var(--primary));
  font-size: 18px;
}
.report-tabs {
  gap: 24px;
  margin-top: 26px;
  border-bottom-color: #e5e5e5;
}
.report-tabs button {
  padding-bottom: 12px;
  color: #737373;
  font-size: 14px;
  font-weight: 500;
}
.report-tabs button:hover,
.report-tabs button.active {
  color: hsl(var(--primary));
}
.report-tabs .active::after {
  height: 2px;
  border-radius: 0;
  background: hsl(var(--primary));
}
.report-title-row {
  margin: 24px 0 16px;
  align-items: stretch;
  flex-direction: column;
}
.report-title-row h1 {
  color: #171717;
  font-size: 24px;
  white-space: nowrap;
}
.report-actions {
  width: 100%;
  justify-content: flex-end;
  margin-top: 16px;
}
.report-actions > .text-slate-400 {
  margin-right: auto;
}
.dashboard {
  gap: 12px;
  padding: 0;
  background: transparent;
}

.filter-card,
.report-table-card {
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  box-shadow: none;
}
.dashboard h3 {
  margin: 2px 0 12px;
  color: #262626;
  font-size: 14px;
}
.legend,
.donut span {
  color: #737373;
  font-size: 13px;
}
.legend i {
  background: #171717;
}
.legend .teal {
  background: #737373;
}
.legend .yellow {
  background: #a3a3a3;
}
.donut {
  width: 124px;
  height: 124px;
  margin-top: 32px;
  border-width: 14px;
  border-color: #171717;
}
.donut strong,
.simple-chart b {
  color: #171717;
}
.simple-chart {
  height: 130px;
  margin: 24px 18px 0 26px;
  border-bottom-color: #e5e5e5;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0,
    transparent 43px,
    #ececec 44px
  );
  color: #a3a3a3;
}
.interaction b {
  color: #525252;
}
.filter-card,
.report-table-card {
  margin-top: 20px;
}
.filter-grid {
  gap: 14px 16px;
}
.filter-grid label {
  gap: 7px;
  color: #525252;
  font-size: 13px;
}
.write-report-title {
  display: flex;
  min-height: 48px;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding-right: 38px;
}
.write-report-title b {
  color: #171717;
  font-size: 22px;
  line-height: 1.3;
}
.write-report-title p {
  margin: 4px 0 0;
  color: #737373;
  font-size: 13px;
  font-weight: 400;
  line-height: 1.5;
}
.template-picker-intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid #e5e5e5;
  border-radius: 10px;
  background: #fafafa;
  padding: 14px 16px;
}
.template-picker-intro > div {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
}
.template-picker-icon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: none;
  place-items: center;
  border-radius: 8px;
  background: #e5e5e5;
  color: #404040;
}
.template-picker-intro strong {
  display: block;
  color: #262626;
  font-size: 14px;
}
.template-picker-intro p {
  margin: 3px 0 0;
  color: #737373;
  font-size: 12px;
  line-height: 1.5;
}
.template-count {
  flex: none;
  border-radius: 999px;
  background: #e5e5e5;
  padding: 4px 8px;
  color: #525252;
  font-size: 12px;
  white-space: nowrap;
}
.template-cards {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  padding: 16px 0 28px;
}
.report-template {
  position: relative;
  min-height: 208px;
  border: 1px solid #e5e5e5;
  border-radius: 10px;
  background: #fff;
  box-shadow: none;
  cursor: pointer;
  touch-action: manipulation;
  transition:
    border-color 150ms ease,
    box-shadow 150ms ease,
    transform 150ms ease;
}
.report-template:hover {
  transform: translateY(-2px);
  border-color: #a3a3a3;
  background: #fff;
  box-shadow: 0 8px 20px rgb(23 23 23 / 8%);
}
.report-template:active {
  transform: translateY(-1px) scale(0.99);
}
.report-template:focus-visible {
  outline: 3px solid rgb(23 23 23 / 24%);
  outline-offset: 2px;
}
.template-glow {
  display: flex;
  min-height: 206px;
  flex-direction: column;
  padding: 20px;
}
.template-card-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.template-glow .template-kind {
  display: inline-flex;
  width: fit-content;
  min-width: 0;
  flex: none;
  align-items: center;
  gap: 5px;
  border-radius: 999px;
  background: #f5f5f5;
  padding: 4px 7px;
  color: #525252;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.25;
  white-space: nowrap;
}
.template-glow .template-kind :deep(svg) {
  flex: none;
}
.template-glow .template-kind-configured {
  background: #f0f0f0;
}
.template-glow h2 {
  margin: 14px 0 6px;
  overflow: hidden;
  color: #171717;
  font-size: 18px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.template-arrow {
  flex: none;
  color: #737373;
  font-size: 16px;
  transition:
    transform 150ms ease,
    color 150ms ease;
}
.report-template:hover .template-arrow {
  transform: translate(2px, -2px);
  color: #171717;
}
.template-frequency {
  min-height: auto;
  margin: 0 0 13px;
  color: #737373;
  font-size: 12px;
}
.template-glow .template-preview {
  border-bottom-color: #e5e5e5;
  padding: 9px 0;
}
.template-glow .template-preview b {
  color: #404040;
  font-size: 13px;
}
.template-glow .template-preview span {
  margin-top: 3px;
  color: #737373;
  font-size: 12px;
}
.template-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: auto;
  padding-top: 14px;
  color: #262626;
  font-size: 13px;
  font-weight: 600;
}
@media (max-width: 1100px) {
  .template-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 640px) {
  .report-page-actions {
    align-items: flex-start;
    flex-direction: column;
  }
  .report-page-actions .report-actions {
    width: 100%;
  }
  .write-report-title,
  .template-picker-intro {
    align-items: flex-start;
    flex-direction: column;
  }
  .write-report-title {
    padding-right: 30px;
  }
  .template-cards {
    grid-template-columns: 1fr;
  }
}
@media (prefers-reduced-motion: reduce) {
  .report-template,
  .template-arrow {
    transition: none;
  }
}
.report-batch-hint {
  border-color: #e5e5e5;
  background: #fafafa;
}
.report-batch-hint strong {
  color: #262626;
}
.report-batch-hint p {
  color: #737373;
}
.report-batch-hint > span {
  background: #e5e5e5;
  color: #404040;
}
@media (max-width: 1100px) {
  .report-side {
    width: 210px;
  }
}

.report-side {
  display: flex;
  flex-direction: column;
}
.report-side-heading {
  margin: 0 0 8px;
  color: #737373;
  font-size: 12px;
  font-weight: 500;
}
.report-type-nav {
  display: grid;
  gap: 4px;
}
.report-side-filter {
  margin-top: 16px;
}
.report-user-nav {
  display: grid;
  min-height: 0;
  flex: 1 1 0%;
  align-content: start;
  gap: 4px;
  margin-top: 16px;
  overflow-y: auto;
}
.report-side-empty {
  padding: 10px;
  color: #737373;
  font-size: 13px;
}
.report-type-item {
  display: flex;
  min-height: 40px;
  align-items: center;
  gap: 8px;
  border-radius: 8px;
  padding: 8px 10px;
  color: #404040;
  font-size: 14px;
  text-align: left;
  transition:
    background-color 150ms ease,
    color 150ms ease;
}
.report-user-item {
  display: flex;
  min-height: 48px;
  align-items: center;
  gap: 10px;
  border-radius: 8px;
  padding: 8px 10px;
  color: #404040;
  font-size: 14px;
  text-align: left;
  transition:
    background-color 150ms ease,
    color 150ms ease;
}
.report-type-item:hover {
  background: hsl(var(--primary) / 6%);
  color: hsl(var(--primary));
}
.report-user-item:hover {
  background: hsl(var(--primary) / 6%);
  color: hsl(var(--primary));
}
.report-type-item.active,
.report-user-item.active {
  background: hsl(var(--primary) / 10%);
  color: hsl(var(--primary));
  font-weight: 600;
}
.report-type-item:focus-visible,
.report-user-item:focus-visible,
.mode-toggle button:focus-visible {
  outline: 2px solid hsl(var(--primary));
  outline-offset: 2px;
}
.report-side-divider {
  height: 1px;
  margin: 20px 0;
  background: hsl(var(--border));
}
.mode-toggle {
  margin: 0;
}
@media (max-width: 720px) {
  .report-center-shell {
    gap: 12px;
    flex-direction: column;
  }
  .report-side {
    display: flex;
    width: 100%;
    border: 1px solid hsl(var(--border));
    padding: 16px;
  }
  .report-type-nav {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .report-user-nav {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    max-height: 192px;
  }
  .report-type-item {
    justify-content: center;
    padding-inline: 8px;
  }
  .report-side-divider {
    margin: 16px 0;
  }
  .mode-toggle {
    max-width: 240px;
  }
}
</style>
