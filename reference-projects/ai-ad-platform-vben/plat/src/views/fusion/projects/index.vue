<script lang="ts" setup>
import type { FormInstance, FormProps, TableColumnsType } from 'ant-design-vue';

import type {
  ProjectPlatformCode,
  ProjectContextOption,
  ProjectListParams,
  ProjectOperatingOverview,
  ProjectPriority,
  ProjectStatus,
  ProjectSummary,
  ProjectType,
  ProjectUpsertPayload,
  ProjectUserAssignment,
} from '#/api';
import type { DepartmentScopeUserOption } from '#/api/system/user';
import type {
  AgencyLine,
  AgencyLineDeliveryUrlHistory,
  AgencyLineImportResult,
} from '#/domain/agency-line';
import type { ProjectAgencyLineBindingInput } from '#/domain/project';

import {
  computed,
  onDeactivated,
  onMounted,
  onBeforeUnmount,
  reactive,
  ref,
  toRefs,
  watch,
} from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Cascader,
  Checkbox,
  Col,
  Drawer,
  Dropdown,
  Form,
  FormItem,
  Input,
  InputNumber,
  Menu,
  MenuItem,
  message,
  Modal,
  Pagination,
  Popover,
  RadioGroup,
  Row,
  Select,
  Skeleton,
  Table,
  Tabs,
  Tag,
  theme,
} from 'ant-design-vue';

import { changeAgencyLineStatuses } from '#/api/agency-line-actions';
import { ApiBusinessError } from '#/api/backend-response';
import AgencyLineOptimizerQuickSelect from './components/AgencyLineOptimizerQuickSelect.vue';
import { isFusionDemoMode } from '#/api/fusion';
import { getUnboundAgencyLineOptions } from '#/api/project-agency-line-options';
import { getDictionaryOptions } from '#/api/system';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import { agencyLineService } from '#/domain/agency-line';
import {
  projectService,
  PROJECT_CLOSURE_APPLICATION_CODE,
} from '#/domain/project';
import {
  canDemoAction,
  canDemoEditProject,
  filterDemoProjects,
  getCurrentDemoActor,
} from '#/mock/demo-access';

import StableUserTreeSelect from '../../components/StableUserTreeSelect.vue';
import DepartmentTreeSelect from '../../components/DepartmentTreeSelect.vue';
import AgencyLineBatchImportDrawer from './components/AgencyLineBatchImportDrawer.vue';
import AgencyLineCreateDrawer from './components/AgencyLineCreateDrawer.vue';
import {
  validateProductInfo,
  PRODUCT_INFO_MAX_LENGTH,
} from '#/domain/project/validation';
import ProjectOperatingDetail from './components/ProjectOperatingDetail.vue';

const KPI_METRIC_OPTIONS = [
  { label: '单次购物费用', value: 'CPP' },
  { label: '单次成效费用', value: 'CPA' },
  { label: 'ROAS', value: 'ROAS' },
] as const;

const KPI_COMPARATOR_OPTIONS = [
  { label: '大于', value: '>' },
  { label: '小于', value: '<' },
  { label: '等于', value: '=' },
  { label: '大于等于', value: '>=' },
  { label: '小于等于', value: '<=' },
  { label: '介于 ... 之间', value: 'between' },
] as const;

const KPI_METRIC_LABELS = Object.fromEntries(
  KPI_METRIC_OPTIONS.map(({ label, value }) => [value, label]),
) as Record<string, string>;

const projectFormRef = ref<FormInstance>();
const { token } = theme.useToken();
// 代理线操作需高于项目详情抽屉，同时低于下拉选项等浮层（基础层级 + 50）。
const agencyLineDrawerZIndex = computed(() => token.value.zIndexPopupBase + 1);
const loading = ref(false);
const saving = ref(false);
const drawerOpen = ref(false);
const editingId = ref('');
const editingProject = ref<null | ProjectSummary>(null);
const walletOpen = ref(false);
const walletCreating = ref(false);
const walletRefreshing = ref(false);
const walletProject = ref<null | ProjectSummary>(null);
const walletAssets = computed(() => {
  const wallet = walletProject.value?.wallet;
  if (!wallet) return [];
  return [
    {
      address: wallet.ethAddress,
      feeUnit: 'Gwei',
      icon: 'logos:ethereum',
      name: 'Ethereum',
      symbol: 'ETH',
    },
    {
      address: wallet.usdtAddress,
      feeUnit: wallet.feeUnit || 'TRX',
      icon: 'cryptocurrency-color:usdt',
      name: 'Tether',
      symbol: 'USDT',
    },
  ];
});
const projects = ref<ProjectSummary[]>([]);
const projectOptions = ref<ProjectContextOption[]>([]);
const agencyLineOptions = ref<Array<{ label: string; value: string }>>([]);
const unboundAgencyLineOptions = ref<Array<{ label: string; value: string }>>(
  [],
);
const unboundAgencyLineLoading = ref(false);
let unboundAgencyLineRequest = 0;
let unboundAgencyLineTimer: ReturnType<typeof setTimeout> | undefined;
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const agencyLinePage = ref(1);
const agencyLinePageSize = ref(20);
const agencyLineTotal = ref(0);
const overviewOpen = ref(false);
const overviewLoading = ref(false);
const overviewError = ref('');
const projectOverview = ref<null | ProjectOperatingOverview>(null);
const agencyLineRevisions = reactive<Record<string, number>>({});
let overviewRequest = 0;
const overviewProject = ref<null | ProjectSummary>(null);
const agencyLineDrawerOpen = ref(false);
const editingAgencyLine = ref<AgencyLine>();
const deliveryUrlHistoryOpen = ref(false);
const deliveryUrlHistoryLoading = ref(false);
const deliveryUrlHistoryLine = ref<AgencyLine>();
const deliveryUrlHistory = ref<AgencyLineDeliveryUrlHistory[]>([]);

async function openDeliveryUrlHistory(line: AgencyLine) {
  deliveryUrlHistoryLine.value = line;
  deliveryUrlHistory.value = [];
  deliveryUrlHistoryOpen.value = true;
  deliveryUrlHistoryLoading.value = true;
  try {
    deliveryUrlHistory.value = await agencyLineService.getDeliveryUrlHistory(
      line.id,
    );
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '投放链接历史加载失败',
    );
  } finally {
    deliveryUrlHistoryLoading.value = false;
  }
}

function openAgencyLineEditor(line?: AgencyLine) {
  if (!canManageAgencyLines.value) return;
  const project = projectOptions.value.find(
    (item) => item.id === line?.projectId,
  );
  if (project && ['ended', 'archived'].includes(project.status)) {
    message.warning('结束或归档项目不允许修改代理线');
    return;
  }
  editingAgencyLine.value = line;
  agencyLineDrawerOpen.value = true;
}

async function handleAgencyLineSaved(line: AgencyLine) {
  if (line.projectId)
    agencyLineRevisions[line.projectId] =
      (agencyLineRevisions[line.projectId] ?? 0) + 1;
  await loadAgencyLines();
}
const agencyLineBatchImportOpen = ref(false);
const importFeedbackOpen = ref(false);
const importFeedback = ref({ total: 0, failures: [] as string[] });
// 同一批补绑重试复用短请求 ID，长度不随代理线数量增长。
const importBindingRequestIds = new Map<string, string>();
const agencyLineLoading = ref(false);
const dictionaryLoading = ref(false);
const agencyLines = ref<AgencyLine[]>([]);
const selectedAgencyLineIds = ref<string[]>([]);
const deleteAgencyLinesOpen = ref(false);
const deletingAgencyLines = ref(false);
const optimizerUpdating = ref(false);
const statusUpdating = ref(false);
const statusDialogOpen = ref(false);
const nextAgencyLineStatus = ref<'active' | 'stopped'>('active');
const statusTargets = ref<AgencyLine[]>([]);
const agencyLineActionBusy = computed(
  () =>
    optimizerUpdating.value || statusUpdating.value || statusDialogOpen.value,
);

function openAgencyLineStatusChange(status: 'active' | 'stopped') {
  if (
    agencyLineActionBusy.value ||
    deletingAgencyLines.value ||
    !canManageAgencyLines.value
  )
    return;
  const targets = agencyLines.value.filter((line) =>
    selectedAgencyLineIds.value.includes(line.id),
  );
  if (!targets.length || targets.length > 100) {
    message.warning('每次请选择1至100条代理线');
    return;
  }
  if (targets.some((line) => !canDeleteAgencyLine(line))) {
    message.warning('结束或归档项目不允许修改代理线');
    return;
  }
  statusTargets.value = targets;
  nextAgencyLineStatus.value = status;
  statusDialogOpen.value = true;
}

/** 整批成功后更新本地状态，失败保留原值。 */
async function confirmAgencyLineStatusChange() {
  if (statusUpdating.value || !canManageAgencyLines.value) return;
  statusUpdating.value = true;
  try {
    await changeAgencyLineStatuses(
      statusTargets.value.map((line) => line.id),
      nextAgencyLineStatus.value,
    );
    const ids = new Set(statusTargets.value.map((line) => line.id));
    agencyLines.value = agencyLines.value.map((line) =>
      ids.has(line.id) ? { ...line, status: nextAgencyLineStatus.value } : line,
    );
    for (const line of statusTargets.value)
      if (line.projectId)
        agencyLineRevisions[line.projectId] =
          (agencyLineRevisions[line.projectId] ?? 0) + 1;
    selectedAgencyLineIds.value = [];
    statusDialogOpen.value = false;
    message.success(
      '已' +
        (nextAgencyLineStatus.value === 'active' ? '开启' : '关闭') +
        ids.size +
        '条代理线',
    );
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '状态更新失败，请重试',
    );
  } finally {
    statusUpdating.value = false;
  }
}

function handleQuickOptimizerSaved(line: AgencyLine) {
  agencyLines.value = agencyLines.value.map((item) =>
    item.id === line.id
      ? {
          ...item,
          optimizerId: line.optimizerId,
          optimizerName: line.optimizerName,
          optimizerStatus: line.optimizerStatus,
        }
      : item,
  );
  if (line.projectId)
    agencyLineRevisions[line.projectId] =
      (agencyLineRevisions[line.projectId] ?? 0) + 1;
}

const deleteAgencyLineTargets = ref<AgencyLine[]>([]);
const deleteAgencyLineFailures = ref<Array<{ id: string; message: string }>>(
  [],
);

function canDeleteAgencyLine(line: AgencyLine) {
  const project = projectOptions.value.find(
    (item) => item.id === line.projectId,
  );
  return (
    canManageAgencyLines.value &&
    (!project || !['ended', 'archived'].includes(project.status))
  );
}

const agencyLineRowSelection = computed(() => ({
  selectedRowKeys: selectedAgencyLineIds.value,
  preserveSelectedRowKeys: true,
  onChange: (keys: Array<string | number>) => {
    if (
      !deletingAgencyLines.value &&
      !deleteAgencyLinesOpen.value &&
      !agencyLineActionBusy.value
    )
      selectedAgencyLineIds.value = keys.map(String);
  },
  getCheckboxProps: (record: AgencyLine) => ({
    disabled:
      agencyLineActionBusy.value ||
      deletingAgencyLines.value ||
      deleteAgencyLinesOpen.value ||
      !canDeleteAgencyLine(record),
  }),
}));

function toggleAgencyLineSelection(line: AgencyLine, checked: boolean) {
  if (
    agencyLineActionBusy.value ||
    deletingAgencyLines.value ||
    deleteAgencyLinesOpen.value ||
    !canDeleteAgencyLine(line)
  )
    return;
  selectedAgencyLineIds.value = checked
    ? [...new Set([...selectedAgencyLineIds.value, line.id])]
    : selectedAgencyLineIds.value.filter((id) => id !== line.id);
}

function openAgencyLineBatchDelete() {
  if (
    !canManageAgencyLines.value ||
    deletingAgencyLines.value ||
    agencyLineActionBusy.value
  )
    return;
  deleteAgencyLineTargets.value = agencyLines.value.filter(
    (line) =>
      selectedAgencyLineIds.value.includes(line.id) &&
      canDeleteAgencyLine(line),
  );
  if (!deleteAgencyLineTargets.value.length) {
    message.warning('请先选择可删除的代理线');
    return;
  }
  deleteAgencyLineFailures.value = [];
  deleteAgencyLinesOpen.value = true;
}

/** 成功行立即移出选择和列表，失败行保留；刷新失败不能改写删除结果。 */
async function confirmAgencyLineBatchDelete() {
  if (deletingAgencyLines.value || !canManageAgencyLines.value) return;
  deletingAgencyLines.value = true;
  try {
    const targets = [...deleteAgencyLineTargets.value];
    const result = await agencyLineService.removeMany(
      targets.map((line) => line.id),
    );
    const removed = new Set(result.removedIds);
    for (const line of targets) {
      if (removed.has(line.id) && line.projectId)
        agencyLineRevisions[line.projectId] =
          (agencyLineRevisions[line.projectId] ?? 0) + 1;
    }
    agencyLines.value = agencyLines.value.filter(
      (line) => !removed.has(line.id),
    );
    agencyLineOptions.value = agencyLineOptions.value.filter(
      (option) => !removed.has(option.value),
    );
    selectedAgencyLineIds.value = result.failures.map((failure) => failure.id);
    deleteAgencyLineFailures.value = result.failures;
    deleteAgencyLineTargets.value = targets.filter(
      (line) => !removed.has(line.id),
    );
    if (removed.size) message.success('已删除 ' + removed.size + ' 条代理线');
    if (!result.failures.length) deleteAgencyLinesOpen.value = false;
    const refreshed = await Promise.allSettled([
      loadAgencyLines(),
      refreshPage(),
    ]);
    if (refreshed.some((item) => item.status === 'rejected'))
      message.warning('删除结果已保存，部分列表刷新失败，请刷新页面');
  } finally {
    deletingAgencyLines.value = false;
  }
}
const activeListTab = ref<'agency-lines' | 'projects'>('projects');
const pendingOverviewNavigation = ref<undefined | (() => void)>();
const router = useRouter();

const demoActor = computed(() =>
  isFusionDemoMode() ? getCurrentDemoActor() : undefined,
);
const canCreateProject = computed(
  () => !isFusionDemoMode() || canDemoAction(demoActor.value, 'project.create'),
);
const canManageAgencyLines = computed(
  () => !isFusionDemoMode() || canDemoAction(demoActor.value, 'project.edit'),
);

const agencyLineFilters = reactive({
  keyword: '',
  optimizerId: undefined as string | undefined,
  platform: undefined as ProjectPlatformCode | undefined,
  projectId: undefined as string | undefined,
});
const isAgencyLineKeywordExpanded = ref(false);

const filters = reactive<ProjectListParams>({
  keyword: '',
  platform: undefined,
  status: undefined,
});
const routeStateReady = ref(false);
const {
  commitQueryState: commitProjectQueryState,
  resetQueryState: resetProjectQueryState,
  restoreFromRoute: restoreProjectRoute,
} = useListRouteState({
  onRouteStateRestored: () => {
    if (routeStateReady.value) return loadProjects();
  },
  pagination: { defaultPageSize: 20, page, pageSize, pageSizes: [20, 50, 100] },
  state: createListRouteStateTarget({
    ...toRefs(filters),
    tab: activeListTab,
  }),
});
const {
  commitQueryState: commitAgencyLineQueryState,
  resetQueryState: resetAgencyLineQueryState,
  restoreFromRoute: restoreAgencyLineRoute,
} = useListRouteState({
  onRouteStateRestored: () => {
    if (routeStateReady.value && activeListTab.value === 'agency-lines') {
      return loadAgencyLines();
    }
  },
  pagination: {
    defaultPageSize: 20,
    page: agencyLinePage,
    pageSize: agencyLinePageSize,
    pageSizes: [20, 50, 100],
  },
  scope: 'agency',
  state: createListRouteStateTarget(toRefs(agencyLineFilters)),
});

const defaultProjectForm = (): ProjectUpsertPayload => ({
  agencyLineIds: [],
  agencyLineUrl: '',
  amName: '',
  amUsers: [],
  attributionWindow: '7 天点击 / 1 天浏览',
  countryRegions: [],
  createWallet: true,
  currency: 'USD',
  customerDailyReportUrl: '',
  dataSpecialist: '',
  dataSpecialistId: undefined,
  dataSpecialists: [],
  dailyBudget: 1000,
  endDate: '',
  isOutsourced: false,
  kpiRequirements: [{ comparator: '>=', metric: 'ROAS', target: 2 }],
  mediaChannelIds: [],
  name: '',
  outsourcingTeams: [],
  platforms: [],
  primaryKpi: 'ROAS',
  priority: 'normal',
  productInfo: '',
  productLinks: [''],
  productName: '',
  projectCode: '',
  projectType: 'game',
  responsibleTeam: '',
  serviceFeePercent: 10,
  startDate: '',
  status: 'active',
  timezone: 'UTC+8',
});

const formState = reactive<ProjectUpsertPayload>(defaultProjectForm());

const platformLabels = reactive<Record<string, string>>({});
const platformOptions = ref<
  Array<{ label: string; value: ProjectPlatformCode }>
>([]);
const regionLabels = reactive<Record<string, string>>({});
const countryRegionCodes = reactive<Record<string, string>>({});
const regionOptions = ref<
  Array<{
    children: Array<{ label: string; value: string }>;
    label: string;
    value: string;
  }>
>([]);

const selectedCountryPaths = computed({
  get: () =>
    formState.countryRegions
      .map((countryCode) => {
        const regionCode = countryRegionCodes[countryCode];
        return regionCode ? [regionCode, countryCode] : undefined;
      })
      .filter((path): path is string[] => Boolean(path)),
  set: (paths: string[][]) => {
    formState.countryRegions = paths
      .map((path) => path.at(-1))
      .filter((countryCode): countryCode is string => Boolean(countryCode));
  },
});

function getRegionLabel(value: string) {
  return regionLabels[value] ?? value;
}

function displayRegionPath({ labels }: { labels: string[] }) {
  return labels.join(' / ');
}

async function loadProjectDictionaries() {
  dictionaryLoading.value = true;
  try {
    const [mediaOptions, projectRegionOptions] = await Promise.all([
      getDictionaryOptions('AD_MEDIA'),
      projectService.listRegionOptions(),
    ]);
    platformOptions.value = mediaOptions.map(({ label, value }) => ({
      label,
      value: value.trim().toLowerCase() as ProjectPlatformCode,
    }));
    regionOptions.value = projectRegionOptions.map((region) => ({
      children: region.countries.map((country) => ({
        label: country.name,
        value: country.code,
      })),
      label: region.name,
      value: region.code,
    }));
    Object.keys(platformLabels).forEach((key) => delete platformLabels[key]);
    Object.keys(regionLabels).forEach((key) => delete regionLabels[key]);
    Object.keys(countryRegionCodes).forEach(
      (key) => delete countryRegionCodes[key],
    );
    platformOptions.value.forEach(({ label, value }) => {
      platformLabels[value] = label;
    });
    projectRegionOptions.forEach((region) => {
      region.countries.forEach((country) => {
        countryRegionCodes[country.code] = region.code;
        regionLabels[country.code] = `${region.name} / ${country.name}`;
      });
    });
  } catch (error) {
    platformOptions.value = [];
    regionOptions.value = [];
    message.error(
      error instanceof Error ? error.message : '项目投放字典加载失败',
    );
  } finally {
    dictionaryLoading.value = false;
  }
}

const priorityOptions: Array<{ label: string; value: ProjectPriority }> = [
  { label: '高优先级', value: 'high' },
  { label: '普通', value: 'normal' },
  { label: '低优先级', value: 'low' },
];

const projectTypeOptions: Array<{ label: string; value: ProjectType }> = [
  { label: '游戏', value: 'game' },
  { label: '应用', value: 'app' },
  { label: '电商', value: 'ecommerce' },
  { label: '网站', value: 'website' },
  { label: '其他', value: 'other' },
];

const projectStatusMeta: Record<
  ProjectStatus,
  { color: string; label: string }
> = {
  active: { color: 'green', label: '进行中' },
  archived: { color: 'default', label: '已归档' },
  draft: { color: 'default', label: '草稿' },
  ended: { color: 'red', label: '已结束' },
  paused: { color: 'orange', label: '已暂停' },
  pending: { color: 'blue', label: '待启动' },
};

const projectStatusOptions = Object.entries(projectStatusMeta)
  .filter(([value]) => value !== 'draft')
  .map(([value, item]) => ({ label: item.label, value }));

const PROJECT_ACTIONS_COLUMN_WIDTH = 160;

const columns: TableColumnsType<ProjectSummary> = [
  {
    key: 'project',
    title: '项目',
  },
  { key: 'market', title: '地区与平台' },
  { key: 'budget', title: '预算与 KPI' },
  {
    key: 'wallet',
    title: '钱包信息',
  },
  { key: 'status', title: '状态' },
  {
    dataIndex: 'updatedAt',
    key: 'updatedAt',
    title: '更新时间',
  },
  { key: 'actions', title: '操作', width: PROJECT_ACTIONS_COLUMN_WIDTH },
];

const agencyLineColumns: TableColumnsType<AgencyLine> = [
  { dataIndex: 'createdAt', key: 'createdAt', title: '创建日期', width: 128 },
  { dataIndex: 'name', key: 'name', title: '代理线', width: 190 },
  { dataIndex: 'platform', key: 'platform', title: '投放平台', width: 110 },
  { dataIndex: 'type', key: 'type', title: '类型', width: 120 },
  {
    dataIndex: 'deliveryUrl',
    key: 'deliveryUrl',
    title: '投放链接',
    width: 180,
  },
  { dataIndex: 'pixelName', key: 'pixelName', title: '像素名称', width: 190 },
  { dataIndex: 'pixelId', key: 'pixelId', title: '像素 ID', width: 160 },
  { dataIndex: 'token', key: 'token', title: 'Token', width: 110 },
  { dataIndex: 'testCode', key: 'testCode', title: '测试代码', width: 160 },
  { dataIndex: 'cloakUrl', key: 'cloakUrl', title: '斗篷链接', width: 220 },
  { dataIndex: 'status', key: 'status', title: '状态', width: 100 },
  {
    dataIndex: 'optimizerName',
    key: 'optimizerName',
    title: '优化师',
    width: 130,
  },
  { dataIndex: 'projectId', key: 'projectId', title: '关联项目', width: 190 },
  { key: 'agencyLineActions', title: '操作', width: 110 },
];

const filteredAgencyLines = computed(() => {
  return agencyLines.value;
});

const projectRules: FormProps['rules'] = {
  amUsers: [
    {
      async validator() {
        if (formState.amUsers.length === 0) {
          throw new Error('请至少选择一名 AM');
        }
      },
      trigger: 'change',
    },
  ],
  countryRegions: [
    { required: true, message: '请至少选择一个投放地区', trigger: 'change' },
  ],
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { max: 80, message: '项目名称最多 80 个字符', trigger: 'blur' },
  ],
  platforms: [
    { required: true, message: '请至少选择一个投放媒体', trigger: 'change' },
  ],
  priority: [{ required: true, message: '请选择优先级', trigger: 'change' }],
  productInfo: [
    { required: true, message: '请输入产品信息', trigger: 'blur' },
    {
      validator: async (_rule: unknown, value: string) =>
        validateProductInfo(value),
      trigger: 'blur',
    },
  ],
  projectType: [
    { required: true, message: '请选择项目类型', trigger: 'change' },
  ],
  responsibleTeam: [
    { required: true, message: '请选择负责团队', trigger: 'change' },
  ],
  serviceFeePercent: [
    {
      required: true,
      message: '请输入 0–100 的服务费比例',
      trigger: 'change',
    },
  ],
  deliveryLeaderId: [
    {
      async validator() {
        if (!editingId.value && !formState.deliveryLeaderId) {
          throw new Error('请为新项目选择稳定投放负责人');
        }
      },
      trigger: 'change',
    },
  ],
  outsourcingTeams: [
    {
      async validator() {
        if (formState.isOutsourced && formState.outsourcingTeams.length === 0) {
          throw new Error('请至少填写一个外包团队');
        }
      },
      trigger: 'change',
    },
  ],
  status: [{ required: true, message: '请选择项目状态', trigger: 'change' }],
};

function addKpiRequirement() {
  const selectedMetrics = new Set(
    formState.kpiRequirements.map(({ metric }) => metric),
  );
  const metric = KPI_METRIC_OPTIONS.find(
    ({ value }) => !selectedMetrics.has(value),
  )?.value;
  if (!metric) {
    message.info('每个 KPI 指标只能配置一次');
    return;
  }
  formState.kpiRequirements.push({
    comparator: '>=',
    metric,
    target: 1,
  });
}

function handleKpiComparatorChange(
  requirement: ProjectUpsertPayload['kpiRequirements'][number],
) {
  if (requirement.comparator !== 'between') requirement.targetMax = undefined;
}

function kpiMetricLabel(metric: string) {
  return KPI_METRIC_LABELS[metric] ?? metric;
}

function kpiRequirementValue(
  requirement: ProjectUpsertPayload['kpiRequirements'][number],
) {
  if (requirement.comparator === 'between') {
    return `${requirement.target} ≤ KPI ≤ ${requirement.targetMax}`;
  }
  return `${requirement.comparator} ${requirement.target}`;
}

function removeKpiRequirement(index: number) {
  if (formState.kpiRequirements.length === 1) {
    message.info('项目至少保留一项 KPI 要求');
    return;
  }
  formState.kpiRequirements.splice(index, 1);
}

function addProductLink() {
  formState.productLinks.push('');
}

function removeProductLink(index: number) {
  formState.productLinks.splice(index, 1);
}

function getProjectQuery(): ProjectListParams {
  return {
    keyword: filters.keyword?.trim() || undefined,
    page: page.value,
    pageSize: pageSize.value,
    platform: filters.platform || undefined,
    status: filters.status || undefined,
  };
}

async function loadProjects() {
  await commitProjectQueryState();
  loading.value = true;
  try {
    const result = await projectService.list(getProjectQuery());
    projects.value = filterDemoProjects(demoActor.value, result.items);
    total.value = isFusionDemoMode() ? projects.value.length : result.total;
  } finally {
    loading.value = false;
  }
}

async function loadProjectContext() {
  const context = await projectService.getContext();
  projectOptions.value = context.options;
}

function canEditProject(record: ProjectSummary | Record<string, unknown>) {
  return (
    !isFusionDemoMode() ||
    canDemoEditProject(demoActor.value, asProject(record))
  );
}

async function loadAgencyLines() {
  await commitAgencyLineQueryState();
  agencyLineLoading.value = true;
  try {
    const result = await agencyLineService.list({
      keyword: agencyLineFilters.keyword.trim() || undefined,
      optimizerId: agencyLineFilters.optimizerId,
      page: agencyLinePage.value,
      pageSize: agencyLinePageSize.value,
      platform: agencyLineFilters.platform,
      projectId: agencyLineFilters.projectId,
    });
    agencyLines.value = result.items;
    agencyLineTotal.value = result.total;
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '代理线列表加载失败',
    );
  } finally {
    agencyLineLoading.value = false;
  }
}

async function loadAgencyLineOptions() {
  try {
    const lines = await agencyLineService.listOptions({});
    agencyLineOptions.value = lines.map((line) => ({
      label: line.name,
      value: line.id,
    }));
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '代理线选项加载失败',
    );
  }
}

async function refreshPage() {
  await Promise.all([loadProjects(), loadProjectContext()]);
}

function searchProjects() {
  page.value = 1;
  void loadProjects();
}

async function resetFilters() {
  await resetProjectQueryState();
  void loadProjects();
}

async function resetAgencyLineFilters() {
  await resetAgencyLineQueryState();
  isAgencyLineKeywordExpanded.value = false;
  void loadAgencyLines();
}

function searchAgencyLines() {
  agencyLinePage.value = 1;
  void loadAgencyLines();
}

function handlePageChange(nextPage: number, nextPageSize: number) {
  page.value = nextPage;
  pageSize.value = nextPageSize;
  void loadProjects();
}

function handleAgencyLinePageChange(nextPage: number, nextPageSize: number) {
  agencyLinePage.value = nextPage;
  agencyLinePageSize.value = nextPageSize;
  void loadAgencyLines();
}

/** 输入防抖，并立即使旧请求失效，避免快速搜索时回填过期结果。 */
function searchUnboundAgencyLines(keyword = '', immediate = false) {
  clearTimeout(unboundAgencyLineTimer);
  const request = ++unboundAgencyLineRequest;
  unboundAgencyLineOptions.value = unboundAgencyLineOptions.value.filter(
    (option) => formState.agencyLineIds?.includes(option.value),
  );
  unboundAgencyLineLoading.value = true;
  unboundAgencyLineTimer = setTimeout(
    async () => {
      try {
        const normalizedKeyword = keyword.trim();
        const lines = isFusionDemoMode()
          ? (await agencyLineService.listOptions({}))
              .filter(
                (line) =>
                  !line.projectId &&
                  line.name
                    .toLowerCase()
                    .includes(normalizedKeyword.toLowerCase()),
              )
              .slice(0, 50)
          : await getUnboundAgencyLineOptions(normalizedKeyword);
        if (request !== unboundAgencyLineRequest) return;
        // 保留已选标签，切换关键词后仍可正确展示和移除已选项。
        const selected = unboundAgencyLineOptions.value.filter((option) =>
          formState.agencyLineIds?.includes(option.value),
        );
        unboundAgencyLineOptions.value = [
          ...selected,
          ...lines
            .filter(
              (line) => !selected.some((option) => option.value === line.id),
            )
            .map((line) => ({ label: line.name, value: line.id })),
        ];
      } catch {
        // 请求层统一展示失败原因，保留已选值以便用户重试。
      } finally {
        if (request === unboundAgencyLineRequest)
          unboundAgencyLineLoading.value = false;
      }
    },
    immediate ? 0 : 300,
  );
}

function cancelUnboundAgencyLineSearch() {
  clearTimeout(unboundAgencyLineTimer);
  ++unboundAgencyLineRequest;
  unboundAgencyLineLoading.value = false;
}

function openCreateDrawer() {
  editingId.value = '';
  editingProject.value = null;
  Object.assign(formState, defaultProjectForm());
  unboundAgencyLineOptions.value = [];
  searchUnboundAgencyLines('', true);
  drawerOpen.value = true;
  projectFormRef.value?.clearValidate();
}

function asProject(project: ProjectSummary | Record<string, unknown>) {
  return project as ProjectSummary;
}

function isInteractiveRowTarget(target: EventTarget | null) {
  return (
    target instanceof Element &&
    Boolean(
      target.closest(
        'a, button, input, select, textarea, [contenteditable="true"], [role="button"], [role="link"]',
      ),
    )
  );
}

function getProjectRowProps(record: ProjectSummary) {
  return {
    'aria-label': `查看项目 ${record.name}`,
    class: 'cursor-pointer',
    onClick: (event: MouseEvent) => {
      if (isInteractiveRowTarget(event.target)) return;
      void openProjectOverview(record);
    },
    onKeydown: (event: KeyboardEvent) => {
      if (
        event.target !== event.currentTarget ||
        ![' ', 'Enter'].includes(event.key)
      ) {
        return;
      }
      event.preventDefault();
      void openProjectOverview(record);
    },
    tabindex: 0,
  };
}

async function openEditDrawer(
  project: ProjectSummary | Record<string, unknown>,
) {
  // 列表不包含绑定关系，编辑前读取完整详情，避免误清空或遗漏解绑。
  const current = await projectService.get(asProject(project).id);
  void loadAgencyLineOptions();
  editingId.value = current.id;
  Object.assign(formState, {
    agencyLineIds: [...(current.agencyLineIds ?? [])],
    agencyLineUrl: current.agencyLineUrl ?? '',
    amUserId: current.amUserId,
    amName: current.amName ?? '',
    amUsers: [...(current.amUsers ?? [])],
    attributionWindow: current.attributionWindow,
    countryRegions: [...current.countryRegions],
    createWallet: current.createWallet ?? true,
    currency: current.currency,
    customerDailyReportUrl: current.customerDailyReportUrl ?? '',
    dataSpecialist: current.dataSpecialist ?? '',
    dataSpecialistId: current.dataSpecialistId,
    dataSpecialists: [...(current.dataSpecialists ?? [])],
    dailyBudget: current.dailyBudget,
    deliveryLeaderId: current.deliveryLeaderId,
    deliveryLeaderName: current.deliveryLeaderName ?? '',
    endDate: current.endDate ?? '',
    id: current.id,
    isOutsourced: current.isOutsourced ?? false,
    kpiRequirements: current.kpiRequirements?.length
      ? current.kpiRequirements.map((item) => ({ ...item }))
      : [{ comparator: '>=', metric: current.primaryKpi, target: 1 }],
    mediaChannelIds: [...(current.mediaChannelIds ?? [])],
    name: current.name,
    outsourcingTeams: [...(current.outsourcingTeams ?? [])],
    platforms: [...current.platforms],
    primaryKpi: current.primaryKpi,
    priority: current.priority ?? 'normal',
    productInfo: current.productInfo ?? current.productName,
    productLinks: current.productLinks?.length
      ? [...current.productLinks]
      : [''],
    productName: current.productName,
    projectCode: current.projectCode,
    projectType: current.projectType ?? 'game',
    responsibleTeam: current.responsibleTeam ?? 'MP',
    serviceFeePercent: current.serviceFeePercent ?? 10,
    startDate: current.startDate,
    status: current.status === 'draft' ? 'active' : current.status,
    timezone: current.timezone,
  });
  editingProject.value = current;
  drawerOpen.value = true;
  projectFormRef.value?.clearValidate();
}

/** 从项目列表发起结项时传递稳定 ID，申请表再按审批配置回填项目下拉。 */
function openProjectClosureApplication(project: ProjectSummary) {
  void router.push({
    path: '/workbench/applications/create',
    query: {
      applicationCode: PROJECT_CLOSURE_APPLICATION_CODE,
      new: '1',
      projectId: project.id,
      projectName: project.name,
    },
  });
}

function handleAmUserChange(
  _userId: string | string[] | undefined,
  _user?: DepartmentScopeUserOption,
  users: DepartmentScopeUserOption[] = [],
) {
  formState.amUsers = users.map(({ name, userId }) => ({
    userId,
    userName: name,
  }));
  formState.amUserId = formState.amUsers[0]?.userId;
  formState.amName = formState.amUsers[0]?.userName ?? '';
}

function handleDeliveryLeaderChange(
  userId: string | string[] | undefined,
  user?: DepartmentScopeUserOption,
) {
  formState.deliveryLeaderId = typeof userId === 'string' ? userId : undefined;
  formState.deliveryLeaderName = user?.name ?? '';
}

/** 数据专员为可选用户，清空时同步移除姓名。 */
function handleDataSpecialistChange(
  _userId: string | string[] | undefined,
  _user?: DepartmentScopeUserOption,
  users: DepartmentScopeUserOption[] = [],
) {
  formState.dataSpecialists = users.map(({ name, userId }) => ({
    userId,
    userName: name,
  }));
  formState.dataSpecialistId = formState.dataSpecialists[0]?.userId;
  formState.dataSpecialist = formState.dataSpecialists[0]?.userName ?? '';
}

function handleOutsourcedChange() {
  if (!formState.isOutsourced) formState.outsourcingTeams = [];
}

async function saveProject() {
  try {
    await projectFormRef.value?.validate();
    if (formState.serviceFeePercent < 0 || formState.serviceFeePercent > 100) {
      message.warning('服务费必须在 0–100 之间');
      return;
    }
    const hasIncompleteKpi = formState.kpiRequirements.some(
      (item) =>
        !item.metric ||
        !item.comparator ||
        item.target === null ||
        (item.comparator === 'between' && item.targetMax == null),
    );
    if (hasIncompleteKpi) {
      message.warning('请完整填写每一项 KPI 要求');
      return;
    }
    const hasInvalidRange = formState.kpiRequirements.some(
      (item) =>
        item.comparator === 'between' &&
        item.targetMax != null &&
        item.target >= item.targetMax,
    );
    if (hasInvalidRange) {
      message.warning('KPI 区间下限必须小于上限');
      return;
    }
    const metrics = formState.kpiRequirements.map(({ metric }) => metric);
    if (new Set(metrics).size !== metrics.length) {
      message.warning('每个 KPI 指标只能配置一次');
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    const primaryKpi = formState.kpiRequirements[0]?.metric ?? 'ROAS';
    const projectCode =
      formState.projectCode || `PRJ-${Date.now().toString(36).toUpperCase()}`;
    const productName = formState.productInfo.trim().slice(0, 80);
    const productLinks = formState.productLinks
      .map((link) => link.trim())
      .filter(Boolean);

    saving.value = true;
    const requestedAgencyLineIds = [...(formState.agencyLineIds ?? [])];
    const savedProject = await projectService.save({
      ...formState,
      productLinks,
      agencyLineIds: undefined,
      countryRegions: [...formState.countryRegions],
      id: editingId.value || undefined,
      kpiRequirements: formState.kpiRequirements.map((item) => ({ ...item })),
      platforms: [...formState.platforms],
      primaryKpi,
      productName,
      projectCode,
      startDate: formState.startDate || today,
    });
    const previousAgencyLineIds = editingProject.value?.agencyLineIds ?? [];
    const add = requestedAgencyLineIds.filter(
      (lineId) => !previousAgencyLineIds.includes(lineId),
    );
    const remove = previousAgencyLineIds.filter(
      (lineId) => !requestedAgencyLineIds.includes(lineId),
    );
    if (add.length > 0 || remove.length > 0) {
      await applyAgencyLineBindingsWithCompatibilityProjection(
        savedProject.id,
        {
          add,
          remove,
          requestId: `project-agency-lines-${savedProject.id}-${Date.now()}`,
        },
      );
    }
    drawerOpen.value = false;
    const walletCreationFailed =
      !editingId.value && formState.createWallet && !savedProject.wallet;
    if (walletCreationFailed) {
      message.warning(
        '项目创建成功，但关联钱包创建失败，请稍后在项目详情中重试',
      );
    } else {
      message.success(editingId.value ? '项目已更新' : '项目已创建');
    }
    await refreshPage();
  } catch (error) {
    // 请求层已统一提示普通业务错误；仅补充全局静默错误和本地校验错误。
    if (error instanceof ApiBusinessError) {
      if (error.silent && error.message) message.error(error.message);
    } else if (
      error instanceof Error &&
      !('config' in error) &&
      error.message
    ) {
      message.error(error.message);
    }
  } finally {
    saving.value = false;
  }
}

async function openProjectOverview(
  project: ProjectSummary | Record<string, unknown>,
) {
  const current = asProject(project);
  const request = ++overviewRequest;
  overviewProject.value = current;
  projectOverview.value = null;
  overviewError.value = '';
  overviewOpen.value = true;
  overviewLoading.value = true;
  try {
    const result = await projectService.getOperatingOverview(current.id);
    if (request === overviewRequest) projectOverview.value = result;
  } catch (error) {
    if (request !== overviewRequest) return;
    overviewError.value =
      error instanceof Error ? error.message : '项目经营详情加载失败';
  } finally {
    if (request === overviewRequest) overviewLoading.value = false;
  }
}

function retryProjectOverview() {
  if (overviewProject.value) void openProjectOverview(overviewProject.value);
}

function formatProjectDateTime(value?: null | string) {
  if (!value) return '-';

  // 保留后端返回的墙上时间，不做时区换算；列表统一展示到秒。
  return value.replace('T', ' ').slice(0, 19);
}

function formatAgencyLineCreatedDate(value?: null | string) {
  return value ? value.slice(0, 10) : '-';
}

function getAgencyLineLabel(id: string) {
  return (
    unboundAgencyLineOptions.value.find((option) => option.value === id)
      ?.label ??
    agencyLineOptions.value.find((option) => option.value === id)?.label ??
    id
  );
}

function getAgencyLineProjectLabel(projectId?: string) {
  if (!projectId) return '未关联';
  return (
    projectOptions.value.find((project) => project.id === projectId)?.name ??
    projectId
  );
}

function asAgencyLine(line: AgencyLine | Record<string, unknown>) {
  return line as AgencyLine;
}

function getAgencyLineBoundProjects(lineId: string) {
  const projectId = agencyLines.value.find(
    (line) => line.id === lineId,
  )?.projectId;
  return projectOptions.value.filter((project) => project.id === projectId);
}

function getAgencyLineBoundProject(lineId: string) {
  return getAgencyLineBoundProjects(lineId)[0];
}

function getAgencyLineDisplayProjectId(
  rawLine: AgencyLine | Record<string, unknown>,
) {
  const line = asAgencyLine(rawLine);
  return getAgencyLineBoundProject(line.id)?.id ?? line.projectId;
}

function getAgencyLineProjectDisplayLabel(
  rawLine: AgencyLine | Record<string, unknown>,
) {
  const line = asAgencyLine(rawLine);
  const boundProjects = getAgencyLineBoundProjects(line.id);
  if (boundProjects.length > 0) {
    return boundProjects.map((project) => project.name).join('、');
  }
  return getAgencyLineProjectLabel(line.projectId);
}

function getAgencyLineBindingStatusLabel(
  rawLine: AgencyLine | Record<string, unknown>,
) {
  const line = asAgencyLine(rawLine);
  const count = getAgencyLineBoundProjects(line.id).length;
  if (count > 1) return `已绑定 ${count} 个项目`;
  return count === 1 ? '已绑定' : '待重试绑定';
}

function isAgencyLineProjectBound(
  rawLine: AgencyLine | Record<string, unknown>,
) {
  const line = asAgencyLine(rawLine);
  return Boolean(getAgencyLineBoundProject(line.id));
}

async function syncDemoAgencyLineProjectProjection(
  projectId: string,
  input: ProjectAgencyLineBindingInput,
) {
  if (!isFusionDemoMode()) return;

  const projectionFailures: string[] = [];
  let currentProjects: ProjectSummary[] = [];
  if ((input.remove?.length ?? 0) > 0) {
    const result = await projectService.list({ page: 1, pageSize: 1000 });
    currentProjects = result.items;
  }
  const updateProjection = async (lineId: string, nextProjectId?: string) => {
    try {
      const line =
        agencyLines.value.find((item) => item.id === lineId) ??
        (await agencyLineService.get(lineId));
      if (line.projectId === nextProjectId) return;
      const {
        createdAt: _createdAt,
        updatedAt: _updatedAt,
        ...lineInput
      } = line;
      await agencyLineService.save({
        ...lineInput,
        projectId: nextProjectId,
      });
    } catch {
      projectionFailures.push(lineId);
    }
  };

  for (const lineId of input.add ?? []) {
    const line = agencyLines.value.find((item) => item.id === lineId);
    await updateProjection(lineId, line?.projectId ?? projectId);
  }
  for (const lineId of input.remove ?? []) {
    const line = agencyLines.value.find((item) => item.id === lineId);
    if (!line || line.projectId === projectId) {
      const replacementProjectId = currentProjects.find(
        (project) =>
          project.id !== projectId && project.agencyLineIds?.includes(lineId),
      )?.id;
      await updateProjection(lineId, replacementProjectId);
    }
  }

  if (projectionFailures.length > 0) {
    message.warning(
      `项目绑定已生效，但 ${projectionFailures.length} 条旧代理线投影同步失败；请刷新后重试`,
    );
  }
}

async function applyAgencyLineBindingsWithCompatibilityProjection(
  projectId: string,
  input: ProjectAgencyLineBindingInput,
) {
  const project = await projectService.applyAgencyLineBindings(
    projectId,
    input,
  );
  for (const lineId of input.add ?? []) {
    const line = agencyLines.value.find((item) => item.id === lineId);
    if (line) line.projectId = projectId;
  }
  for (const lineId of input.remove ?? []) {
    const line = agencyLines.value.find((item) => item.id === lineId);
    if (line?.projectId === projectId) line.projectId = undefined;
  }
  // Project.agencyLineIds 是权威关系；Demo 仅同步旧 projectId 展示投影。
  await syncDemoAgencyLineProjectProjection(projectId, input);
  return project;
}

async function retryAgencyLineBinding(
  rawLine: AgencyLine | Record<string, unknown>,
) {
  const line = asAgencyLine(rawLine);
  if (!line.projectId) return;
  try {
    const project = await projectService.get(line.projectId);
    await applyAgencyLineBindingsWithCompatibilityProjection(project.id, {
      add: [line.id],
      requestId: `agency-line-retry-${project.id}-${line.id}`,
    });
    await refreshPage();
    message.success(`代理线 ${line.name} 已重新绑定项目`);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '代理线绑定失败');
  }
}

function maskWalletValue(value?: string) {
  if (!value) return '未创建';
  if (value.length <= 14) return value;
  return `${value.slice(0, 7)}••••••${value.slice(-6)}`;
}

async function copyWalletValue(value: string | undefined, label: string) {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    message.success(`${label}地址已复制`);
  } catch {
    message.error('复制失败，请稍后重试');
  }
}

function openWallet(project: ProjectSummary | Record<string, unknown>) {
  walletProject.value = asProject(project);
  walletOpen.value = true;
}

async function refreshWallet() {
  const project = walletProject.value;
  if (!project || walletRefreshing.value) return;
  walletRefreshing.value = true;
  try {
    const current = await projectService.get(project.id);
    walletProject.value = current;
    const listProject = projects.value.find((item) => item.id === current.id);
    if (listProject) {
      listProject.wallet = current.wallet;
      listProject.createWallet = current.createWallet;
    }
    message.success('钱包信息已刷新');
  } finally {
    walletRefreshing.value = false;
  }
}

async function createWalletForProject() {
  const project = walletProject.value;
  if (!project || walletCreating.value) return;
  walletCreating.value = true;
  try {
    const wallet = await projectService.createWallet(project.id);
    project.wallet = wallet;
    project.createWallet = true;
    const listProject = projects.value.find((item) => item.id === project.id);
    if (listProject) {
      listProject.wallet = wallet;
      listProject.createWallet = true;
    }
    message.success('钱包创建成功');
  } finally {
    walletCreating.value = false;
  }
}

async function copyAgencyLine(lineId: string) {
  const label = getAgencyLineLabel(lineId);
  try {
    await navigator.clipboard.writeText(label);
    message.success(`代理线 ${label} 已复制`);
  } catch {
    message.error('复制失败，请稍后重试');
  }
}

function navigateAfterOverviewClose(query: Record<string, string>) {
  navigateOverview('/dashboard/ad-manager', query);
}

/** 等抽屉离场后导航，避免 Teleport 遮罩遗留。 */
function navigateOverview(path: string, query: Record<string, string>) {
  const navigate = () => {
    void router.push({ path, query });
  };

  if (!overviewOpen.value) {
    navigate();
    return;
  }

  pendingOverviewNavigation.value = navigate;
  overviewOpen.value = false;
}

function openOverviewClosure() {
  if (!projectOverview.value) return;
  const project = projectOverview.value.project;
  pendingOverviewNavigation.value = () =>
    openProjectClosureApplication(project);
  overviewOpen.value = false;
}

function openOverviewAgencyAdPanel(id: string, name: string) {
  navigateAfterOverviewClose({
    agencyLineId: id,
    agent_line: name,
    tab: 'agent_line',
  });
}

function handleOverviewAfterOpenChange(open: boolean) {
  if (open) return;

  const navigate = pendingOverviewNavigation.value;
  pendingOverviewNavigation.value = undefined;
  if (navigate) navigate();
}

function openProjectAdPanel(project: ProjectSummary) {
  navigateAfterOverviewClose({
    game_platform: project.name,
    projectId: project.id,
    tab: 'game_platform',
  });
}

async function handleAgencyLineCreated(line: AgencyLine, projectId?: string) {
  const boundProjectId = projectId || line.projectId;
  if (boundProjectId) {
    try {
      // 正式创建接口已原子绑定项目；仅为未返回绑定结果的旧适配器补绑。
      if (line.projectId !== boundProjectId) {
        await applyAgencyLineBindingsWithCompatibilityProjection(
          boundProjectId,
          {
            add: [line.id],
            requestId: `agency-line-create-bind-${boundProjectId}-${line.id}`,
          },
        );
      }
      // 用项目级刷新信号驱动详情，不依赖组件 ref 或其他列表请求成功。
      agencyLineRevisions[boundProjectId] =
        (agencyLineRevisions[boundProjectId] ?? 0) + 1;
      message.success(`代理线 ${line.name} 已绑定到项目`);
    } catch (error) {
      message.error(
        error instanceof Error
          ? `代理线已创建，但项目绑定失败：${error.message}`
          : '代理线已创建，但项目绑定失败',
      );
    }
  } else {
    message.success(`代理线 ${line.name} 已创建，可稍后绑定项目`);
  }
  const results = await Promise.allSettled([loadAgencyLines(), refreshPage()]);
  if (results.some((result) => result.status === 'rejected')) {
    message.warning('代理线已创建，部分列表刷新失败，请稍后刷新页面');
  }
}

/** 已返回正确项目归属的行不再补绑，只为旧接口缺失的绑定执行兼容请求。 */
async function handleAgencyLinesImported(result: AgencyLineImportResult) {
  const lines = result.items;
  const bindFailures: string[] = [];
  const linesByProject = new Map<string, AgencyLine[]>();
  for (const imported of result.importedItems) {
    const projectId = imported.requestedProjectId || imported.line.projectId;
    if (!projectId) continue;
    linesByProject.set(projectId, [
      ...(linesByProject.get(projectId) ?? []),
      imported.line,
    ]);
  }
  if (result.importedItems.length === 0) {
    for (const line of lines) {
      if (!line.projectId) continue;
      linesByProject.set(line.projectId, [
        ...(linesByProject.get(line.projectId) ?? []),
        line,
      ]);
    }
  }

  for (const [projectId, projectLines] of linesByProject) {
    try {
      const unboundLines = projectLines.filter(
        (line) => line.projectId !== projectId,
      );
      if (unboundLines.length > 0) {
        const project = await projectService.get(projectId);
        const pendingLines = unboundLines.filter(
          (line) => !project.agencyLineIds?.includes(line.id),
        );
        if (pendingLines.length > 0) {
          const ids = pendingLines.map((line) => line.id).sort();
          const batchRequests = result.importedItems
            .map((item) => item.requestId)
            .sort();
          const key = JSON.stringify([projectId, ids, batchRequests]);
          let requestId = importBindingRequestIds.get(key);
          if (!requestId) {
            const suffix =
              typeof crypto.randomUUID === 'function'
                ? crypto.randomUUID()
                : Date.now().toString(36) +
                  '-' +
                  Math.random().toString(36).slice(2);
            requestId = 'agency-line-import-bind-' + suffix;
            importBindingRequestIds.set(key, requestId);
          }
          await applyAgencyLineBindingsWithCompatibilityProjection(projectId, {
            add: ids,
            requestId,
          });
        }
      }
      // 即使无需补绑也通知已打开的项目详情刷新，避免显示旧列表。
      agencyLineRevisions[projectId] =
        (agencyLineRevisions[projectId] ?? 0) + 1;
    } catch (error) {
      bindFailures.push(
        getAgencyLineProjectLabel(projectId) +
          '：' +
          (error instanceof Error ? error.message : '绑定失败'),
      );
    }
  }

  if (bindFailures.length > 0) {
    importFeedback.value = { total: lines.length, failures: bindFailures };
    importFeedbackOpen.value = true;
  } else {
    message.success(
      '已导入 ' +
        lines.length +
        ' 条代理线' +
        (linesByProject.size ? '并完成项目绑定' : ''),
    );
  }
  const refreshResults = await Promise.allSettled([
    loadAgencyLines(),
    refreshPage(),
  ]);
  activeListTab.value = 'agency-lines';
  if (refreshResults.some((item) => item.status === 'rejected')) {
    message.warning('导入结果已保存，部分列表刷新失败，请刷新页面查看');
  }
}

// 项目首屏不预取全部代理线，切换到代理线页签时再加载。
watch(
  () => filteredAgencyLines.value.map((line) => line.id),
  (ids) => {
    // 筛选或刷新后清理不可见选择，避免误删已隐藏的行；确认弹框内保留固定快照。
    if (deletingAgencyLines.value || deleteAgencyLinesOpen.value) return;
    const visible = new Set(ids);
    selectedAgencyLineIds.value = selectedAgencyLineIds.value.filter((id) =>
      visible.has(id),
    );
  },
);

watch(activeListTab, (tab) => {
  if (!routeStateReady.value) return;
  void commitProjectQueryState();
  if (tab === 'agency-lines') void loadAgencyLines();
});

watch(drawerOpen, (open) => {
  if (!open) cancelUnboundAgencyLineSearch();
});
onBeforeUnmount(cancelUnboundAgencyLineSearch);

onMounted(async () => {
  await restoreProjectRoute();
  await restoreAgencyLineRoute();
  routeStateReady.value = true;
  await Promise.all([loadProjectDictionaries(), refreshPage()]);
  if (activeListTab.value === 'agency-lines') await loadAgencyLines();
});

onDeactivated(() => {
  cancelUnboundAgencyLineSearch();
  overviewOpen.value = false;
  pendingOverviewNavigation.value = undefined;
});
</script>

<template>
  <Page auto-content-height class="bg-slate-50">
    <div class="min-w-0 space-y-4">
      <section
        class="flex flex-col justify-between gap-3 lg:flex-row lg:items-center"
      >
        <div class="min-w-0">
          <h1 class="m-0 text-xl font-semibold text-slate-900">项目管理</h1>
          <p class="mb-0 mt-1 text-sm text-slate-500">
            统一维护项目经营配置、钱包、代理线与投放范围。
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            v-if="canManageAgencyLines"
            class="!inline-flex flex-none items-center justify-center whitespace-nowrap"
            @click="openAgencyLineEditor()"
          >
            <IconifyIcon
              icon="lucide:git-branch-plus"
              class="shrink-0 text-base"
            />
            <span>新建代理线</span>
          </Button>
          <Button
            v-if="canCreateProject"
            class="!inline-flex flex-none items-center justify-center whitespace-nowrap"
            type="primary"
            @click="openCreateDrawer"
          >
            <IconifyIcon icon="lucide:plus" class="shrink-0 text-base" />
            <span>新建项目</span>
          </Button>
        </div>
      </section>

      <Card class="border-slate-200" :body-style="{ padding: '16px' }">
        <Form
          v-if="activeListTab === 'projects'"
          class="ux-filter-form"
          layout="vertical"
          @submit.prevent="searchProjects"
        >
          <FormItem class="ux-filter-field" label="关键词">
            <Input
              v-model:value="filters.keyword"
              allow-clear
              placeholder="项目名称、编码或产品"
              @press-enter="searchProjects"
            />
          </FormItem>
          <FormItem class="ux-filter-field" label="投放平台">
            <Select
              v-model:value="filters.platform"
              :options="platformOptions"
              allow-clear
              placeholder="全部平台"
            />
          </FormItem>
          <FormItem class="ux-filter-field" label="项目状态">
            <Select
              v-model:value="filters.status"
              :options="projectStatusOptions"
              allow-clear
              placeholder="全部状态"
            />
          </FormItem>
          <div class="ux-filter-actions">
            <Button @click="resetFilters">重置</Button>
            <Button type="primary" html-type="submit"> 搜索 </Button>
          </div>
        </Form>

        <Form
          v-else
          class="ux-filter-form"
          layout="vertical"
          @submit.prevent="searchAgencyLines"
        >
          <FormItem class="ux-filter-field" label="关键词">
            <Input.TextArea
              v-model:value="agencyLineFilters.keyword"
              :rows="isAgencyLineKeywordExpanded ? 4 : 1"
              allow-clear
              :class="[
                'agency-line-keyword',
                {
                  'agency-line-keyword--expanded': isAgencyLineKeywordExpanded,
                },
              ]"
              placeholder="代理线、链接、像素或投手；多个关键词请换行"
              @focus="isAgencyLineKeywordExpanded = true"
            />
          </FormItem>
          <FormItem class="ux-filter-field" label="投放平台">
            <Select
              v-model:value="agencyLineFilters.platform"
              :options="platformOptions"
              allow-clear
              placeholder="全部平台"
            />
          </FormItem>
          <FormItem class="ux-filter-field" label="关联项目">
            <Select
              v-model:value="agencyLineFilters.projectId"
              :options="
                projectOptions.map((project) => ({
                  label: project.name,
                  value: project.id,
                }))
              "
              allow-clear
              show-search
              option-filter-prop="label"
              placeholder="全部项目（含未关联）"
            />
          </FormItem>
          <FormItem class="ux-filter-field" label="投手">
            <StableUserTreeSelect
              :model-value="agencyLineFilters.optimizerId"
              class="w-full"
              placeholder="全部投手"
              @change="
                agencyLineFilters.optimizerId =
                  typeof $event === 'string' ? $event : undefined
              "
            />
          </FormItem>
          <div class="ux-filter-actions">
            <Button @click="resetAgencyLineFilters"> 重置 </Button>
            <Button
              type="primary"
              html-type="submit"
              :loading="agencyLineLoading"
            >
              搜索
            </Button>
          </div>
        </Form>
      </Card>

      <Card class="border-slate-200" :body-style="{ padding: '0' }">
        <Tabs
          v-model:active-key="activeListTab"
          class="project-list-tabs"
          :tab-bar-style="{ paddingInline: '16px' }"
        >
          <Tabs.TabPane key="projects" tab="项目列表">
            <div class="hidden min-w-0 xl:block">
              <Table
                :columns="columns"
                :custom-row="getProjectRowProps"
                :data-source="projects"
                :loading="loading"
                :pagination="false"
                row-key="id"
                table-layout="fixed"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'project'">
                    <div class="py-1">
                      <div class="font-medium text-slate-900">
                        {{ record.name }}
                      </div>
                      <div class="mt-0.5 text-xs text-slate-500">
                        {{ record.projectCode }}
                      </div>
                      <div class="mt-1 truncate text-xs text-slate-500">
                        产品：{{ record.productName }}
                      </div>
                      <div class="mt-1 truncate text-xs text-slate-500">
                        AM：
                        {{
                          record.amUsers
                            ?.map(
                              (user: ProjectUserAssignment) => user.userName,
                            )
                            .join('、') ||
                          record.amName ||
                          '历史未记录'
                        }}
                      </div>
                      <div class="mt-1 truncate text-xs text-slate-500">
                        投放负责人：{{
                          record.deliveryLeaderName || '历史未记录'
                        }}
                      </div>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'market'">
                    <div class="space-y-2 py-1">
                      <div class="flex min-w-0 items-start gap-2">
                        <span
                          class="w-8 shrink-0 pt-0.5 text-xs text-slate-400"
                        >
                          地区
                        </span>
                        <div class="flex min-w-0 flex-1 flex-wrap gap-1">
                          <Tag
                            v-for="region in record.countryRegions"
                            :key="region"
                          >
                            {{ getRegionLabel(region) }}
                          </Tag>
                        </div>
                      </div>
                      <div class="flex min-w-0 items-start gap-2">
                        <span
                          class="w-8 shrink-0 pt-0.5 text-xs text-slate-400"
                        >
                          平台
                        </span>
                        <div class="flex min-w-0 flex-1 flex-wrap gap-1">
                          <Tag
                            v-for="platform in record.platforms"
                            :key="platform"
                            color="blue"
                          >
                            {{
                              platformLabels[platform as ProjectPlatformCode]
                            }}
                          </Tag>
                        </div>
                      </div>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'budget'">
                    <div class="font-medium text-slate-800">
                      {{ record.currency }}
                      {{ record.dailyBudget.toLocaleString() }} / 日
                    </div>
                    <div class="mt-0.5 text-xs text-slate-500">
                      主 KPI：{{ record.primaryKpi }}
                    </div>
                    <Popover placement="bottomRight" trigger="click">
                      <template #content>
                        <div class="w-72 space-y-3">
                          <div>
                            <div class="text-xs text-slate-400">日预算</div>
                            <div class="mt-1 font-medium text-slate-800">
                              {{ record.currency }}
                              {{ record.dailyBudget.toLocaleString() }} / 日
                            </div>
                          </div>
                          <div>
                            <div class="text-xs text-slate-400">KPI 要求</div>
                            <div
                              v-if="record.kpiRequirements?.length"
                              class="mt-1.5 space-y-1.5"
                            >
                              <div
                                v-for="(kpi, index) in record.kpiRequirements"
                                :key="`${kpi.metric}-${index}`"
                                class="flex items-center justify-between gap-4 rounded-md bg-slate-50 px-2.5 py-2 text-sm"
                              >
                                <span class="font-medium text-slate-700">
                                  {{ kpiMetricLabel(kpi.metric) }}
                                </span>
                                <span class="text-slate-500">
                                  {{ kpiRequirementValue(kpi) }}
                                </span>
                              </div>
                            </div>
                            <div v-else class="mt-1.5 text-sm text-slate-500">
                              {{ record.primaryKpi }}（旧项目未配置目标值）
                            </div>
                          </div>
                        </div>
                      </template>
                      <Button type="link" class="mt-1 !px-0">
                        查看更多
                        <IconifyIcon
                          icon="lucide:chevron-down"
                          class="ml-1 size-3.5"
                        />
                      </Button>
                    </Popover>
                  </template>
                  <template v-else-if="column.key === 'wallet'">
                    <div class="space-y-1.5 py-1 font-mono text-xs">
                      <div class="flex min-w-0 items-center gap-1">
                        <span class="w-10 shrink-0 text-slate-500">ETH</span>
                        <span class="min-w-0 flex-1 truncate text-slate-700">
                          {{ maskWalletValue(record.wallet?.ethAddress) }}
                        </span>
                        <Button
                          type="text"
                          class="!inline-flex !size-7 shrink-0 items-center justify-center"
                          :disabled="!record.wallet?.ethAddress"
                          aria-label="复制 ETH 地址"
                          @click="
                            copyWalletValue(record.wallet?.ethAddress, 'ETH')
                          "
                        >
                          <IconifyIcon icon="lucide:copy" class="size-3.5" />
                        </Button>
                      </div>
                      <div class="flex min-w-0 items-center gap-1">
                        <span class="w-10 shrink-0 text-slate-500">USDT</span>
                        <span class="min-w-0 flex-1 truncate text-slate-700">
                          {{ maskWalletValue(record.wallet?.usdtAddress) }}
                        </span>
                        <Button
                          type="text"
                          class="!inline-flex !size-7 shrink-0 items-center justify-center"
                          :disabled="!record.wallet?.usdtAddress"
                          aria-label="复制 USDT 地址"
                          @click="
                            copyWalletValue(record.wallet?.usdtAddress, 'USDT')
                          "
                        >
                          <IconifyIcon icon="lucide:copy" class="size-3.5" />
                        </Button>
                      </div>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'status'">
                    <Tag
                      :color="
                        projectStatusMeta[record.status as ProjectStatus].color
                      "
                    >
                      {{
                        projectStatusMeta[record.status as ProjectStatus].label
                      }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'updatedAt'">
                    <span class="whitespace-nowrap">
                      {{ formatProjectDateTime(record.updatedAt) }}
                    </span>
                  </template>
                  <template v-else-if="column.key === 'actions'">
                    <div
                      class="flex flex-nowrap items-center whitespace-nowrap"
                    >
                      <Button
                        class="!px-1"
                        type="link"
                        @click="openProjectOverview(record)"
                      >
                        查看
                      </Button>
                      <Button
                        v-if="canEditProject(record)"
                        class="!px-1"
                        type="link"
                        @click="openEditDrawer(record)"
                      >
                        编辑
                      </Button>
                      <Dropdown
                        v-if="canEditProject(record)"
                        :trigger="['click']"
                        placement="bottomRight"
                      >
                        <Button class="!px-1" type="link">
                          更多
                          <IconifyIcon
                            icon="lucide:chevron-down"
                            class="ml-0.5 size-3.5"
                            aria-hidden="true"
                          />
                        </Button>
                        <template #overlay>
                          <Menu>
                            <MenuItem
                              @click="
                                openProjectClosureApplication(asProject(record))
                              "
                            >
                              结项
                            </MenuItem>
                            <MenuItem @click="openWallet(record)">
                              钱包
                            </MenuItem>
                          </Menu>
                        </template>
                      </Dropdown>
                      <Button
                        v-else
                        class="!px-1"
                        type="link"
                        @click="
                          openProjectClosureApplication(asProject(record))
                        "
                      >
                        结项
                      </Button>
                    </div>
                  </template>
                </template>
              </Table>
            </div>

            <div class="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 xl:hidden">
              <Card
                v-for="project in projects"
                :key="project.id"
                class="border-slate-200"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="truncate font-semibold text-slate-900">
                      {{ project.name }}
                    </div>
                    <div class="mt-0.5 text-xs text-slate-500">
                      {{ project.projectCode }}
                    </div>
                  </div>
                  <Tag
                    :color="projectStatusMeta[project.status].color"
                    class="shrink-0"
                  >
                    {{ projectStatusMeta[project.status].label }}
                  </Tag>
                </div>
                <dl
                  class="mt-4 grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm"
                >
                  <dt class="text-slate-500">关联产品</dt>
                  <dd class="m-0 truncate text-slate-800">
                    {{ project.productName }}
                  </dd>
                  <dt class="text-slate-500">AM</dt>
                  <dd class="m-0 truncate text-slate-800">
                    {{
                      project.amUsers
                        ?.map((user) => user.userName)
                        .join('、') ||
                      project.amName ||
                      '历史未记录'
                    }}
                  </dd>
                  <dt class="text-slate-500">投放负责人</dt>
                  <dd class="m-0 truncate text-slate-800">
                    {{ project.deliveryLeaderName || '历史未记录' }}
                  </dd>
                  <dt class="text-slate-500">投放地区</dt>
                  <dd class="m-0 flex flex-wrap gap-1">
                    <Tag v-for="region in project.countryRegions" :key="region">
                      {{ getRegionLabel(region) }}
                    </Tag>
                  </dd>
                  <dt class="text-slate-500">投放平台</dt>
                  <dd class="m-0 flex flex-wrap gap-1">
                    <Tag
                      v-for="platform in project.platforms"
                      :key="platform"
                      color="blue"
                    >
                      {{ platformLabels[platform] }}
                    </Tag>
                  </dd>
                  <dt class="text-slate-500">日预算</dt>
                  <dd class="m-0 text-slate-800">
                    {{ project.currency }}
                    {{ project.dailyBudget.toLocaleString() }}
                  </dd>
                  <dt class="text-slate-500">钱包地址</dt>
                  <dd class="m-0 min-w-0 space-y-2 font-mono text-xs">
                    <div class="flex min-w-0 items-center gap-2">
                      <span class="w-10 shrink-0 text-slate-500">ETH</span>
                      <span class="min-w-0 flex-1 truncate text-slate-800">
                        {{ maskWalletValue(project.wallet?.ethAddress) }}
                      </span>
                      <Button
                        type="text"
                        class="!inline-flex !size-8 shrink-0 items-center justify-center"
                        :disabled="!project.wallet?.ethAddress"
                        aria-label="复制 ETH 地址"
                        @click="
                          copyWalletValue(project.wallet?.ethAddress, 'ETH')
                        "
                      >
                        <IconifyIcon icon="lucide:copy" class="size-3.5" />
                      </Button>
                    </div>
                    <div class="flex min-w-0 items-center gap-2">
                      <span class="w-10 shrink-0 text-slate-500">USDT</span>
                      <span class="min-w-0 flex-1 truncate text-slate-800">
                        {{ maskWalletValue(project.wallet?.usdtAddress) }}
                      </span>
                      <Button
                        type="text"
                        class="!inline-flex !size-8 shrink-0 items-center justify-center"
                        :disabled="!project.wallet?.usdtAddress"
                        aria-label="复制 USDT 地址"
                        @click="
                          copyWalletValue(project.wallet?.usdtAddress, 'USDT')
                        "
                      >
                        <IconifyIcon icon="lucide:copy" class="size-3.5" />
                      </Button>
                    </div>
                  </dd>
                </dl>
                <div
                  class="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3"
                >
                  <Button
                    class=""
                    @click="openProjectClosureApplication(project)"
                  >
                    结项
                  </Button>
                  <Button
                    v-if="canEditProject(project)"
                    class=""
                    @click="openEditDrawer(project)"
                  >
                    编辑
                  </Button>
                  <Button class="" @click="openProjectOverview(project)">
                    查看
                  </Button>
                </div>
              </Card>
            </div>

            <div
              v-if="!loading && projects.length === 0"
              class="p-10 text-center text-slate-500"
            >
              没有符合条件的项目。可调整筛选条件或新建项目。
            </div>

            <div class="flex justify-end border-t border-slate-100 px-4 py-3">
              <Pagination
                :current="page"
                :page-size="pageSize"
                :total="total"
                show-size-changer
                show-less-items
                @change="handlePageChange"
              />
            </div>
          </Tabs.TabPane>

          <Tabs.TabPane key="agency-lines" tab="代理线列表">
            <div
              v-if="canManageAgencyLines"
              class="flex flex-wrap items-center gap-3 border-b p-4"
            >
              <span>已选 {{ selectedAgencyLineIds.length }} 条</span>
              <Button
                :disabled="
                  !selectedAgencyLineIds.length ||
                  agencyLineLoading ||
                  deletingAgencyLines ||
                  agencyLineActionBusy
                "
                @click="openAgencyLineStatusChange('active')"
                >批量开启</Button
              >
              <Button
                :disabled="
                  !selectedAgencyLineIds.length ||
                  agencyLineLoading ||
                  deletingAgencyLines ||
                  agencyLineActionBusy
                "
                @click="openAgencyLineStatusChange('stopped')"
                >批量关闭</Button
              >
              <Button
                danger
                :disabled="
                  !selectedAgencyLineIds.length ||
                  agencyLineLoading ||
                  deletingAgencyLines
                "
                :loading="deletingAgencyLines"
                @click="openAgencyLineBatchDelete"
                >批量删除</Button
              >
              <Button
                v-if="selectedAgencyLineIds.length"
                :disabled="deletingAgencyLines"
                @click="selectedAgencyLineIds = []"
                >取消选择</Button
              >
              <span class="text-muted-foreground text-sm"
                >结束或归档项目下的代理线不可删除</span
              >
            </div>

            <div class="hidden min-w-0 lg:block">
              <Table
                :columns="agencyLineColumns"
                :row-selection="
                  canManageAgencyLines ? agencyLineRowSelection : undefined
                "
                :data-source="filteredAgencyLines"
                :loading="agencyLineLoading"
                :pagination="false"
                row-key="id"
                :scroll="{ x: 2100 }"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'createdAt'">
                    <span class="whitespace-nowrap">
                      {{ formatAgencyLineCreatedDate(record.createdAt) }}
                    </span>
                  </template>
                  <template v-else-if="column.key === 'name'">
                    <div class="min-w-0 py-1">
                      <div class="truncate font-medium text-slate-900">
                        {{ record.name }}
                      </div>
                      <div class="mt-0.5 truncate text-xs text-slate-400">
                        {{ record.id }}
                      </div>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'platform'">
                    <Tag color="blue">
                      {{
                        platformLabels[
                          record.platform as ProjectPlatformCode
                        ] ?? record.platform
                      }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'deliveryUrl'">
                    <div class="min-w-0 overflow-hidden">
                      <a
                        v-if="record.deliveryUrl"
                        :href="record.deliveryUrl"
                        :title="record.deliveryUrl"
                        target="_blank"
                        rel="noreferrer"
                        class="block max-w-full truncate"
                      >
                        {{ record.deliveryUrl }}
                      </a>
                      <span v-else class="text-slate-400">—</span>
                      <Button
                        type="link"
                        class="!p-0"
                        @click="openDeliveryUrlHistory(asAgencyLine(record))"
                      >
                        历史版本
                      </Button>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'pixelName'">
                    <span class="block truncate">{{ record.pixelName }}</span>
                  </template>
                  <template v-else-if="column.key === 'token'">
                    <span>{{ record.token ? '••••••••' : '—' }}</span>
                  </template>
                  <template v-else-if="column.key === 'cloakUrl'">
                    <a
                      v-if="record.cloakUrl"
                      :href="record.cloakUrl"
                      target="_blank"
                      rel="noreferrer"
                      class="block truncate"
                      >{{ record.cloakUrl }}</a
                    >
                    <span v-else class="text-slate-400">—</span>
                  </template>
                  <template v-else-if="column.key === 'status'"
                    ><Tag
                      :color="record.status === 'active' ? 'green' : undefined"
                      >{{
                        record.status === 'active'
                          ? '开启'
                          : record.status === 'stopped'
                            ? '关闭'
                            : '未知'
                      }}</Tag
                    ></template
                  >
                  <template v-else-if="column.key === 'optimizerName'"
                    ><AgencyLineOptimizerQuickSelect
                      :line="asAgencyLine(record)"
                      :disabled="
                        agencyLineActionBusy ||
                        deletingAgencyLines ||
                        deleteAgencyLinesOpen ||
                        !canDeleteAgencyLine(asAgencyLine(record))
                      "
                      @busy="optimizerUpdating = $event"
                      @saved="handleQuickOptimizerSaved"
                  /></template>
                  <template v-else-if="column.key === 'projectId'">
                    <div class="min-w-0 space-y-1">
                      <span
                        class="block truncate"
                        :class="
                          getAgencyLineDisplayProjectId(record)
                            ? 'text-slate-700'
                            : 'text-slate-400'
                        "
                      >
                        {{ getAgencyLineProjectDisplayLabel(record) }}
                      </span>
                      <Tag
                        v-if="getAgencyLineDisplayProjectId(record)"
                        :color="
                          isAgencyLineProjectBound(record) ? 'green' : 'orange'
                        "
                      >
                        {{ getAgencyLineBindingStatusLabel(record) }}
                      </Tag>
                    </div>
                  </template>
                  <template v-else-if="column.key === 'agencyLineActions'">
                    <div class="flex flex-col items-start">
                      <Button
                        type="link"
                        @click="openAgencyLineEditor(asAgencyLine(record))"
                        v-if="canManageAgencyLines"
                        >编辑</Button
                      >
                      <Button type="link" @click="copyAgencyLine(record.id)">
                        复制
                      </Button>
                      <Button
                        v-if="
                          getAgencyLineDisplayProjectId(record) &&
                          !isAgencyLineProjectBound(record)
                        "
                        type="link"
                        @click="retryAgencyLineBinding(record)"
                      >
                        重试绑定
                      </Button>
                    </div>
                  </template>
                </template>
              </Table>
            </div>

            <div class="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 lg:hidden">
              <Card
                v-for="line in filteredAgencyLines"
                :key="line.id"
                class="border-slate-200"
              >
                <div class="flex min-w-0 items-start justify-between gap-3">
                  <Checkbox
                    v-if="canManageAgencyLines"
                    :checked="selectedAgencyLineIds.includes(line.id)"
                    :disabled="
                      deletingAgencyLines ||
                      deleteAgencyLinesOpen ||
                      !canDeleteAgencyLine(line)
                    "
                    :aria-label="'选择代理线 ' + line.name"
                    @change="
                      toggleAgencyLineSelection(line, $event.target.checked)
                    "
                  />
                  <div class="min-w-0">
                    <div class="truncate font-semibold text-slate-900">
                      {{ line.name }}
                    </div>
                    <div class="mt-0.5 truncate text-xs text-slate-400">
                      {{ line.id }}
                    </div>
                  </div>
                  <Tag color="blue" class="shrink-0">
                    {{
                      platformLabels[line.platform as ProjectPlatformCode] ??
                      line.platform
                    }}
                  </Tag>
                </div>
                <dl
                  class="mt-4 grid grid-cols-[76px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm"
                >
                  <dt class="text-slate-500">投放链接</dt>
                  <dd class="m-0 min-w-0 text-slate-800">
                    <div class="truncate">{{ line.deliveryUrl || '—' }}</div>
                    <Button
                      type="link"
                      class="!p-0"
                      @click="openDeliveryUrlHistory(line)"
                      >历史版本</Button
                    >
                  </dd>
                  <dt class="text-slate-500">创建日期</dt>
                  <dd class="m-0 text-slate-800">
                    {{ formatAgencyLineCreatedDate(line.createdAt) }}
                  </dd>
                  <dt class="text-slate-500">类型</dt>
                  <dd class="m-0 min-w-0 truncate text-slate-800">
                    {{ line.type || '—' }}
                  </dd>
                  <dt class="text-slate-500">像素名称</dt>
                  <dd class="m-0 min-w-0 truncate text-slate-800">
                    {{ line.pixelName }}
                  </dd>
                  <dt class="text-slate-500">像素 ID</dt>
                  <dd class="m-0 min-w-0 truncate text-slate-800">
                    {{ line.pixelId || '—' }}
                  </dd>
                  <dt class="text-slate-500">Token</dt>
                  <dd class="m-0 text-slate-800">
                    {{ line.token ? '••••••••' : '—' }}
                  </dd>
                  <dt class="text-slate-500">测试代码</dt>
                  <dd class="m-0 min-w-0 truncate text-slate-800">
                    {{ line.testCode || '—' }}
                  </dd>
                  <dt class="text-slate-500">斗篷链接</dt>
                  <dd class="m-0 min-w-0 truncate text-slate-800">
                    {{ line.cloakUrl || '—' }}
                  </dd>
                  <dt class="text-slate-500">状态</dt>
                  <dd class="m-0">
                    <Tag
                      :color="line.status === 'active' ? 'green' : undefined"
                      >{{
                        line.status === 'active'
                          ? '开启'
                          : line.status === 'stopped'
                            ? '关闭'
                            : '未知'
                      }}</Tag
                    >
                  </dd>
                  <dt class="text-slate-500">优化师</dt>
                  <dd class="m-0 truncate text-slate-800">
                    <AgencyLineOptimizerQuickSelect
                      :line="line"
                      :disabled="
                        agencyLineActionBusy ||
                        deletingAgencyLines ||
                        deleteAgencyLinesOpen ||
                        !canDeleteAgencyLine(line)
                      "
                      @busy="optimizerUpdating = $event"
                      @saved="handleQuickOptimizerSaved"
                    />
                  </dd>
                  <dt class="text-slate-500">关联项目</dt>
                  <dd class="m-0 min-w-0 text-slate-800">
                    <span class="block truncate">
                      {{ getAgencyLineProjectDisplayLabel(line) }}
                    </span>
                    <Tag
                      v-if="getAgencyLineDisplayProjectId(line)"
                      class="mt-1"
                      :color="
                        isAgencyLineProjectBound(line) ? 'green' : 'orange'
                      "
                    >
                      {{ getAgencyLineBindingStatusLabel(line) }}
                    </Tag>
                  </dd>
                </dl>
                <div class="mt-4 border-t border-slate-100 pt-3">
                  <Button
                    v-if="canManageAgencyLines"
                    class=""
                    @click="openAgencyLineEditor(line)"
                    >编辑</Button
                  >
                  <Button class="" @click="copyAgencyLine(line.id)">
                    <IconifyIcon icon="lucide:copy" class="mr-1 size-4" />
                    复制代理线
                  </Button>
                  <Button
                    v-if="
                      getAgencyLineDisplayProjectId(line) &&
                      !isAgencyLineProjectBound(line)
                    "
                    class="ml-2"
                    @click="retryAgencyLineBinding(line)"
                  >
                    重试绑定
                  </Button>
                </div>
              </Card>
            </div>

            <div
              v-if="agencyLineTotal > 0"
              class="flex justify-end border-t border-slate-100 px-4 py-3"
            >
              <Pagination
                :current="agencyLinePage"
                :page-size="agencyLinePageSize"
                :total="agencyLineTotal"
                show-size-changer
                show-less-items
                @change="handleAgencyLinePageChange"
              />
            </div>

            <div
              v-if="!agencyLineLoading && filteredAgencyLines.length === 0"
              class="p-10 text-center text-slate-500"
            >
              没有符合条件的代理线。可调整筛选条件或新建代理线。
            </div>
          </Tabs.TabPane>
        </Tabs>
      </Card>
    </div>

    <AgencyLineCreateDrawer
      v-model:open="agencyLineDrawerOpen"
      :z-index="agencyLineDrawerZIndex"
      :initial-project-id="overviewOpen ? overviewProject?.id : undefined"
      :projects="projectOptions"
      :editing-line="editingAgencyLine"
      :platform-options="platformOptions"
      @saved="handleAgencyLineSaved"
      @created="handleAgencyLineCreated"
      @open-batch-import="agencyLineBatchImportOpen = true"
    />

    <AgencyLineBatchImportDrawer
      v-model:open="agencyLineBatchImportOpen"
      :z-index="agencyLineDrawerZIndex"
      :projects="projectOptions"
      @imported="handleAgencyLinesImported"
    />

    <Modal
      v-model:open="statusDialogOpen"
      title="批量修改代理线状态"
      :closable="!statusUpdating"
      :keyboard="!statusUpdating"
      :mask-closable="false"
      :confirm-loading="statusUpdating"
      ok-text="确认修改"
      cancel-text="取消"
      :cancel-button-props="{ disabled: statusUpdating }"
      @ok="confirmAgencyLineStatusChange"
    >
      <p>
        确认{{ nextAgencyLineStatus === 'active' ? '开启' : '关闭' }}以下
        {{ statusTargets.length }} 条代理线？
      </p>
      <div class="max-h-[50vh] overflow-y-auto">
        <p v-for="line in statusTargets" :key="line.id">{{ line.name }}</p>
      </div>
    </Modal>
    <Modal
      v-model:open="deleteAgencyLinesOpen"
      title="批量删除代理线"
      width="min(640px, 100vw)"
      :closable="!deletingAgencyLines"
      :keyboard="!deletingAgencyLines"
      :mask-closable="false"
    >
      <p>
        将删除以下
        {{ deleteAgencyLineTargets.length }}
        条代理线，并从关联项目中移除，请确认。
      </p>
      <div class="max-h-[50vh] space-y-2 overflow-y-auto break-words">
        <div
          v-for="line in deleteAgencyLineTargets"
          :key="line.id"
          class="rounded border p-3"
        >
          <div>{{ line.name }}</div>
          <div class="text-muted-foreground text-sm">{{ line.id }}</div>
          <p
            v-if="
              deleteAgencyLineFailures.some((failure) => failure.id === line.id)
            "
            class="text-destructive m-0 mt-2 text-sm"
          >
            {{
              deleteAgencyLineFailures.find((failure) => failure.id === line.id)
                ?.message
            }}
          </p>
        </div>
      </div>
      <template #footer>
        <Button
          :disabled="deletingAgencyLines"
          @click="deleteAgencyLinesOpen = false"
          >{{ deleteAgencyLineFailures.length ? '关闭' : '取消' }}</Button
        >
        <Button
          type="primary"
          danger
          :loading="deletingAgencyLines"
          :disabled="!deleteAgencyLineTargets.length"
          @click="confirmAgencyLineBatchDelete"
          >{{
            deleteAgencyLineFailures.length ? '重试失败项' : '确认删除'
          }}</Button
        >
      </template>
    </Modal>

    <Modal
      v-model:open="importFeedbackOpen"
      :z-index="agencyLineDrawerZIndex + 1"
      title="导入结果"
      width="min(640px, 100vw)"
      :mask-closable="false"
    >
      <p>
        已导入 {{ importFeedback.total }} 条代理线；{{
          importFeedback.failures.length
        }}
        个项目绑定未完成。已导入的数据无需重复上传。
      </p>
      <div class="max-h-[50vh] space-y-2 overflow-y-auto break-words">
        <Alert
          v-for="(failure, index) in importFeedback.failures"
          :key="index"
          type="warning"
          show-icon
          :message="failure"
        />
      </div>
      <template #footer>
        <Button type="primary" @click="importFeedbackOpen = false">确定</Button>
      </template>
    </Modal>

    <Modal
      v-model:open="walletOpen"
      :confirm-loading="walletCreating"
      title="钱包信息"
      width="min(920px, calc(100vw - 32px))"
    >
      <div v-if="walletProject?.wallet" class="wallet-modal-content">
        <article class="wallet-summary-card">
          <div class="wallet-summary-icon" aria-hidden="true">
            <IconifyIcon icon="lucide:wallet-cards" class="size-5" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-foreground break-all text-sm font-semibold">
              {{ walletProject.wallet.accountName || '未提供' }}
            </div>
            <div class="wallet-summary-key">
              <span class="wallet-key-badge">Key</span>
              <span class="text-muted-foreground break-all font-mono text-xs">
                {{ walletProject.wallet.key }}
              </span>
            </div>
          </div>
        </article>

        <section aria-labelledby="wallet-assets-heading">
          <div class="wallet-assets-toolbar">
            <div class="wallet-assets-title">
              <IconifyIcon
                icon="lucide:database"
                class="text-primary size-4"
                aria-hidden="true"
              />
              <h3 id="wallet-assets-heading">币种明细</h3>
              <span>共 {{ walletAssets.length }} 种</span>
            </div>
            <Button
              :loading="walletRefreshing"
              :disabled="walletRefreshing"
              aria-label="刷新钱包信息"
              @click="refreshWallet"
            >
              <IconifyIcon icon="lucide:refresh-cw" class="size-4" />
              刷新
            </Button>
          </div>

          <Table
            class="wallet-assets-table"
            :data-source="walletAssets"
            :pagination="false"
            row-key="symbol"
            :scroll="{ x: 700 }"
          >
            <Table.Column title="币种" key="symbol" :width="120">
              <template #default="{ record }">
                <div class="wallet-asset-cell">
                  <IconifyIcon :icon="record.icon" class="size-5" />
                  <div>
                    <div class="text-foreground font-medium">
                      {{ record.symbol }}
                    </div>
                    <div class="text-muted-foreground text-xs">
                      {{ record.symbol }}
                    </div>
                  </div>
                </div>
              </template>
            </Table.Column>
            <Table.Column title="币种全称" data-index="name" key="name" />
            <Table.Column
              title="手续费单位"
              data-index="feeUnit"
              key="feeUnit"
              align="center"
              :width="130"
            />
            <Table.Column title="地址" key="address" :width="160">
              <template #default="{ record }">
                <div class="wallet-address-cell">
                  <span class="wallet-address-mask">
                    {{ record.address ? '••••••' : '未同步' }}
                  </span>
                  <Button
                    type="text"
                    :disabled="!record.address"
                    :aria-label="`复制 ${record.symbol} 地址`"
                    @click="copyWalletValue(record.address, record.symbol)"
                  >
                    <IconifyIcon icon="lucide:copy" class="size-4" />
                  </Button>
                </div>
              </template>
            </Table.Column>
          </Table>
        </section>
      </div>
      <div v-else class="project-form-empty py-8">
        <IconifyIcon icon="lucide:wallet-cards" class="mx-auto mb-3 size-8" />
        <div>该项目尚未创建钱包</div>
        <div class="mt-1 text-xs">
          点击“创建钱包”后将调用 Safeheron 创建入金币钱包。
        </div>
      </div>

      <template #footer>
        <div class="flex justify-end gap-2">
          <Button
            v-if="!walletProject?.wallet"
            :disabled="walletCreating"
            @click="walletOpen = false"
          >
            取消
          </Button>
          <Button
            v-if="!walletProject?.wallet"
            type="primary"
            :loading="walletCreating"
            @click="createWalletForProject"
          >
            创建钱包
          </Button>
          <Button v-else @click="walletOpen = false">关闭</Button>
        </div>
      </template>
    </Modal>

    <Drawer
      v-model:open="overviewOpen"
      destroy-on-close
      :title="`${overviewProject?.name ?? '项目'} · 项目经营详情`"
      width="min(960px, 100vw)"
      @after-open-change="handleOverviewAfterOpenChange"
    >
      <Skeleton v-if="overviewLoading" active :paragraph="{ rows: 10 }" />

      <Alert
        v-else-if="overviewError"
        type="error"
        show-icon
        :message="overviewError"
      >
        <template #action>
          <Button @click="retryProjectOverview">重新加载</Button>
        </template>
      </Alert>

      <ProjectOperatingDetail
        v-else-if="projectOverview"
        :agency-line-revision="
          agencyLineRevisions[projectOverview.project.id] ?? 0
        "
        :overview="projectOverview"
        :can-manage="canManageAgencyLines"
        :region-label="getRegionLabel"
        @ad-panel="openProjectAdPanel(projectOverview.project)"
        @agency-ad-panel="openOverviewAgencyAdPanel"
        @closure="openOverviewClosure"
        @comparison="
          navigateOverview('/analytics/project-comparison', {
            projectId: projectOverview.project.id,
          })
        "
        @create-line="openAgencyLineEditor()"
        @create-task="
          navigateOverview('/workbench/tasks/create-delivery', {
            projectId: projectOverview.project.id,
          })
        "
        @status-changed="loadAgencyLines"
      />

      <template #footer>
        <div class="flex justify-end">
          <Button class="min-w-20" @click="overviewOpen = false"> 关闭 </Button>
        </div>
      </template>
    </Drawer>

    <Modal
      v-model:open="deliveryUrlHistoryOpen"
      :title="`${deliveryUrlHistoryLine?.name ?? '代理线'} · 投放链接历史`"
      :footer="null"
      width="min(820px, 100vw)"
    >
      <Table
        :data-source="deliveryUrlHistory"
        :loading="deliveryUrlHistoryLoading"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 700 }"
      >
        <Table.Column
          title="版本"
          data-index="versionNo"
          key="versionNo"
          width="80"
        />
        <Table.Column
          title="投放链接"
          data-index="deliveryUrl"
          key="deliveryUrl"
        >
          <template #default="{ text }">
            <a
              v-if="text"
              :href="text"
              target="_blank"
              rel="noreferrer"
              class="block max-w-md truncate"
              >{{ text }}</a
            >
            <span v-else class="text-slate-400">已清空</span>
          </template>
        </Table.Column>
        <Table.Column
          title="修改人"
          data-index="changedByName"
          key="changedByName"
          width="140"
        />
        <Table.Column
          title="修改时间"
          data-index="changedAt"
          key="changedAt"
          width="190"
        />
      </Table>
    </Modal>

    <Drawer
      v-model:open="drawerOpen"
      :closable="!saving"
      :keyboard="!saving"
      :mask-closable="!saving"
      :title="editingId ? '编辑项目' : '新建项目'"
      width="min(900px, 100vw)"
    >
      <Form
        ref="projectFormRef"
        :model="formState"
        :rules="projectRules"
        layout="vertical"
      >
        <div class="project-form-section-title">项目信息</div>
        <Row :gutter="16">
          <Col :xs="24" :md="12">
            <FormItem label="项目名称" name="name" required>
              <Input
                v-model:value.trim="formState.name"
                placeholder="请输入项目名称"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="负责团队" name="responsibleTeam" required>
              <DepartmentTreeSelect
                v-model="formState.responsibleTeam"
                placeholder="请选择负责团队"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="AM" name="amUsers" required>
              <StableUserTreeSelect
                :model-value="formState.amUsers.map((item) => item.userId)"
                :legacy-label="formState.amName"
                multiple
                placeholder="请选择 AM"
                @change="handleAmUserChange"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="投放负责人" name="deliveryLeaderId">
              <StableUserTreeSelect
                v-model="formState.deliveryLeaderId"
                :legacy-label="formState.deliveryLeaderName"
                placeholder="请选择投放负责人"
                @change="handleDeliveryLeaderChange"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="数据专员" name="dataSpecialistId">
              <StableUserTreeSelect
                :model-value="
                  formState.dataSpecialists.map((item) => item.userId)
                "
                :legacy-label="formState.dataSpecialist"
                multiple
                placeholder="请选择数据专员"
                @change="handleDataSpecialistChange"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="是否外包" required>
              <RadioGroup
                v-model:value="formState.isOutsourced"
                :options="[
                  { label: '无外包', value: false },
                  { label: '有外包', value: true },
                ]"
                @change="handleOutsourcedChange"
              />
            </FormItem>
          </Col>
          <Col v-if="formState.isOutsourced" :xs="24" :md="12">
            <FormItem label="外包团队" name="outsourcingTeams">
              <DepartmentTreeSelect
                v-model="formState.outsourcingTeams"
                multiple
                placeholder="请选择外包团队，可多选"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="优先级" name="priority" required>
              <Select
                v-model:value="formState.priority"
                :options="priorityOptions"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="投放媒体" name="platforms" required>
              <Select
                v-model:value="formState.platforms"
                :options="platformOptions"
                :loading="dictionaryLoading"
                mode="multiple"
                placeholder="请选择投放媒体"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="投放地区" name="countryRegions" required>
              <Cascader
                v-model:value="selectedCountryPaths"
                :multiple="true"
                :display-render="displayRegionPath"
                expand-trigger="hover"
                show-search
                popup-class-name="project-region-cascader-popup"
                placeholder="搜索或选择投放地区 / 国家"
                :options="regionOptions"
                :loading="dictionaryLoading"
                class="project-region-cascader w-full"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="服务费" name="serviceFeePercent" required>
              <InputNumber
                v-model:value="formState.serviceFeePercent"
                :min="0"
                :max="100"
                :precision="2"
                class="w-full"
                addon-after="%"
                placeholder="0–100"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="项目状态" name="status" required>
              <Select
                v-model:value="formState.status"
                :options="projectStatusOptions"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="项目类型" name="projectType" required>
              <Select
                v-model:value="formState.projectType"
                :options="projectTypeOptions"
              />
            </FormItem>
          </Col>
          <Col :xs="24">
            <FormItem label="项目基础信息" name="productInfo" required>
              <Input.TextArea
                v-model:value="formState.productInfo"
                :maxlength="PRODUCT_INFO_MAX_LENGTH"
                :rows="3"
                :show-count="{
                  formatter: ({ value }) =>
                    `${value?.length ?? 0}/${PRODUCT_INFO_MAX_LENGTH}`,
                }"
                placeholder="请输入项目背景、核心卖点、目标用户与投放目标"
              />
            </FormItem>
          </Col>
          <Col :xs="24">
            <FormItem label="产品链接（可多个）">
              <div class="space-y-2">
                <div
                  v-for="(_, index) in formState.productLinks"
                  :key="index"
                  class="flex items-center gap-2"
                >
                  <Input
                    v-model:value.trim="formState.productLinks[index]"
                    placeholder="https://example.com/product"
                  />
                  <Button danger type="text" @click="removeProductLink(index)">
                    删除
                  </Button>
                </div>
                <Button type="dashed" @click="addProductLink">
                  + 添加产品链接
                </Button>
              </div>
            </FormItem>
          </Col>
          <Col :xs="24">
            <FormItem label="客户日报链接">
              <Input
                v-model:value.trim="formState.customerDailyReportUrl"
                :maxlength="1000"
                placeholder="请输入 http/https 日报链接（选填）"
              />
            </FormItem>
          </Col>
          <Col :xs="24">
            <FormItem label="代理线链接">
              <Input
                v-model:value.trim="formState.agencyLineUrl"
                :maxlength="1000"
                placeholder="请输入 http/https 代理线链接（选填）"
              />
            </FormItem>
          </Col>
          <Col v-if="!editingId" :xs="24">
            <FormItem label="创建钱包" required>
              <RadioGroup
                v-model:value="formState.createWallet"
                :options="[
                  { label: '是', value: true },
                  { label: '否', value: false },
                ]"
              />
            </FormItem>
          </Col>
        </Row>

        <section v-if="editingId" class="mt-3">
          <div class="project-form-section-title">钱包信息</div>
          <div v-if="editingProject?.wallet" class="wallet-detail-grid">
            <article class="wallet-identity-card">
              <div class="wallet-card-label">钱包名称</div>
              <div class="mt-2 break-all text-sm text-slate-800">
                {{ editingProject.wallet.accountName || '未提供' }}
              </div>
            </article>
            <article class="wallet-identity-card">
              <div class="wallet-card-label">Wallet Key</div>
              <div class="mt-2 break-all font-mono text-sm text-slate-800">
                {{ maskWalletValue(editingProject.wallet.key) }}
              </div>
            </article>
            <div class="wallet-address-panel md:col-span-2">
              <div
                v-for="asset in [
                  {
                    address: editingProject.wallet.ethAddress,
                    label: 'ETH',
                  },
                  {
                    address: editingProject.wallet.usdtAddress,
                    label: 'USDT',
                  },
                ]"
                :key="asset.label"
                class="wallet-address-row"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-semibold text-slate-900">
                      {{ asset.label }}
                    </span>
                    <Tag>手续费单位：{{ editingProject.wallet.feeUnit }}</Tag>
                  </div>
                  <div class="mt-1 truncate font-mono text-sm text-slate-600">
                    {{ maskWalletValue(asset.address) }}
                  </div>
                </div>
                <Button
                  class="!inline-flex shrink-0 items-center gap-1"
                  @click="copyWalletValue(asset.address, asset.label)"
                >
                  <IconifyIcon icon="lucide:copy" class="size-4" />
                  复制
                </Button>
              </div>
            </div>
          </div>
          <div v-else class="project-form-empty">该项目尚未创建钱包。</div>
        </section>

        <div class="project-form-section-title mt-3">
          <span>KPI 要求</span>
          <Button
            v-if="formState.kpiRequirements.length < KPI_METRIC_OPTIONS.length"
            type="link"
            class=""
            @click="addKpiRequirement"
          >
            <IconifyIcon icon="lucide:plus" class="mr-1 size-4" />
            添加 KPI
          </Button>
        </div>
        <div class="space-y-3">
          <div
            v-for="(item, index) in formState.kpiRequirements"
            :key="index"
            class="kpi-requirement-row"
          >
            <Select
              v-model:value="item.metric"
              aria-label="KPI 指标"
              :options="
                KPI_METRIC_OPTIONS.map((option) => ({
                  ...option,
                  disabled: formState.kpiRequirements.some(
                    (requirement, requirementIndex) =>
                      requirementIndex !== index &&
                      requirement.metric === option.value,
                  ),
                }))
              "
            />
            <Select
              v-model:value="item.comparator"
              aria-label="KPI 判断方式"
              :options="[...KPI_COMPARATOR_OPTIONS]"
              @change="handleKpiComparatorChange(item)"
            />
            <div class="kpi-value-fields">
              <InputNumber
                v-model:value="item.target"
                :aria-label="
                  item.comparator === 'between' ? 'KPI 区间下限' : 'KPI 目标值'
                "
                :min="0"
                class="w-full"
                :placeholder="item.comparator === 'between' ? '下限' : '目标值'"
              />
              <template v-if="item.comparator === 'between'">
                <span aria-hidden="true" class="text-muted-foreground">至</span>
                <InputNumber
                  :value="item.targetMax ?? undefined"
                  aria-label="KPI 区间上限"
                  :min="0"
                  class="w-full"
                  placeholder="上限"
                  @update:value="
                    item.targetMax =
                      $event === null ? undefined : Number($event)
                  "
                />
              </template>
            </div>
            <Button
              danger
              type="text"
              class="min-w-11"
              aria-label="删除 KPI"
              @click="removeKpiRequirement(index)"
            >
              <IconifyIcon icon="lucide:trash-2" class="size-4" />
            </Button>
          </div>
        </div>

        <div class="project-form-section-title mt-6">代理线绑定</div>
        <FormItem label="选择代理线">
          <Select
            v-model:value="formState.agencyLineIds"
            :options="editingId ? agencyLineOptions : unboundAgencyLineOptions"
            :loading="!editingId && unboundAgencyLineLoading"
            :filter-option="editingId ? undefined : false"
            mode="multiple"
            allow-clear
            show-search
            option-filter-prop="label"
            max-tag-count="responsive"
            placeholder="可多选需要绑定的代理线"
            class="w-full"
            @search="
              (keyword) => {
                if (!editingId) searchUnboundAgencyLines(keyword);
              }
            "
          />
        </FormItem>
      </Form>

      <template #footer>
        <div class="flex justify-end gap-2">
          <Button
            class="min-w-20"
            :disabled="saving"
            @click="drawerOpen = false"
          >
            取消
          </Button>
          <Button
            class="min-w-24"
            type="primary"
            :loading="saving"
            @click="saveProject"
          >
            {{ editingId ? '保存修改' : '创建项目' }}
          </Button>
        </div>
      </template>
    </Drawer>
  </Page>
</template>

<style scoped>
.project-form-section-title {
  display: flex;
  min-height: 44px;
  align-items: center;
  justify-content: flex-start;
  margin-bottom: 12px;
  border-bottom: 1px solid hsl(var(--border));
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 600;
}

.project-form-section-title::before {
  width: 3px;
  height: 18px;
  margin-right: 8px;
  border-radius: 999px;
  background: hsl(var(--primary));
  content: '';
}

.project-form-section-title > span {
  margin-right: auto;
}

.kpi-requirement-row {
  display: grid;
  grid-template-columns:
    minmax(140px, 1fr) minmax(140px, 1fr) minmax(140px, 1fr)
    44px;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
  background: hsl(var(--card));
}

.kpi-value-fields {
  display: flex;
  align-items: center;
  gap: 8px;
}

.wallet-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.wallet-identity-card,
.wallet-address-panel,
.project-form-empty {
  padding: 16px;
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
  background: hsl(var(--card));
}

.wallet-card-label {
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.wallet-modal-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.wallet-summary-card {
  position: relative;
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
  padding: 16px 20px 16px 24px;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
  background: hsl(var(--card));
  box-shadow: 0 1px 3px hsl(var(--foreground) / 6%);
}

.wallet-summary-card::before {
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  width: 4px;
  background: hsl(var(--primary));
  content: '';
}

.wallet-summary-icon {
  display: inline-flex;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: hsl(var(--primary));
  color: hsl(var(--primary-foreground));
}

.wallet-summary-key {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.wallet-key-badge {
  flex: 0 0 auto;
  padding: 1px 5px;
  border-radius: 4px;
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
}

.wallet-assets-toolbar {
  display: flex;
  min-height: 40px;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.wallet-assets-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.wallet-assets-title h3 {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: 14px;
  font-weight: 600;
}

.wallet-assets-title span {
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.wallet-asset-cell,
.wallet-address-cell {
  display: flex;
  align-items: center;
}

.wallet-asset-cell {
  gap: 10px;
}

.wallet-address-cell {
  justify-content: space-between;
  gap: 8px;
}

.wallet-address-mask {
  color: hsl(var(--muted-foreground));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  letter-spacing: 1px;
}

.wallet-address-row {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid hsl(var(--border));
}

.wallet-address-row:first-child {
  padding-top: 0;
}

.wallet-address-row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.project-form-empty {
  border-style: dashed;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

@media (max-width: 767px) {
  .kpi-requirement-row,
  .wallet-detail-grid {
    grid-template-columns: 1fr;
  }

  .kpi-requirement-row > :last-child {
    justify-self: end;
  }

  .wallet-address-row {
    align-items: flex-start;
  }

  .wallet-summary-card {
    align-items: flex-start;
    padding-inline: 20px 16px;
  }

  .wallet-summary-key {
    align-items: flex-start;
  }
}
</style>
