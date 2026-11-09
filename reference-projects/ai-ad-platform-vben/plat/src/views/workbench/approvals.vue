<script lang="ts" setup>
import type { UploadFile, UploadProps } from 'ant-design-vue';

import type {
  ApprovalMetadata,
  ApprovalQueue,
  ApplicationDefinition,
  ApprovalTransferCandidate,
  DynamicFormField,
  MediaAsset,
  MediaAssetType,
  SelectablePixel,
} from '#/api/asset-flow';
import type { SystemDepartmentApi } from '#/api/system/department';
import type {
  ApplicationComment,
  ApplicationStatus,
  ApplicationType,
  ResourceApplication,
} from '#/store/resource-applications';

import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';

import {
  Button,
  Card,
  Checkbox,
  Image,
  Input,
  InputNumber,
  message,
  Modal,
  Pagination,
  Segmented,
  Select,
  Table,
  Tag,
  Tooltip,
  Upload,
} from 'ant-design-vue';
import { storeToRefs } from 'pinia';

import { assetFlowApi, isFusionDemoMode } from '#/api';
import { getSystemDepartmentTree } from '#/api/system/department';
import { uploadTaskFileApi } from '#/api/task-center';
import {
  createPositiveIntegerRouteQueryField,
  createStringRouteQueryField,
  useRouteListQuery,
} from '#/composables/use-route-list-query';
import {
  ApplicationResourceBridgeService,
  ApplicationService,
  LegacyApplicationStoreAdapter,
  matchesSocialInventoryAsset,
  resolveSocialAssetSelection,
} from '#/domain/application';
import { LegacyResourceStoreAdapter, ResourceService } from '#/domain/resource';
import { ApplicationWorkflowRuntimeAdapter } from '#/domain/workflow-runtime';
import { approvalApplicationTypeLabels } from '#/store/media-approval-config';
import { useMediaResourceStore } from '#/store/media-resource';
import {
  applicationTypeLabels,
  approvalRoleMeta,
  useResourceApplicationStore,
} from '#/store/resource-applications';
import { downloadBlob } from '#/utils/download';

import BusinessPageHeader from '../components/BusinessPageHeader.vue';
import AccountOpeningAccountSelector from './components/AccountOpeningAccountSelector.vue';
import ApplicationWorkflowTimeline from './components/ApplicationWorkflowTimeline.vue';
import ListLoading from '../components/ListLoading.vue';
import {
  mapBackendApplication as mapBackendApplicationRecord,
  mapBackendApprovalListItem,
} from './backend-application';
import {
  filterApprovalApplications,
  getApprovalDepartmentLabel,
} from './approval-listing';
import { isBatchDecisionEligible } from './approval-batch';
import {
  isLatestApprovalRequest,
  limitApprovalBatchRecords,
  paginateApprovalRecords,
  resolveApprovalPageChange,
} from './approval-pagination';
import ApplicationCollaborationPanel from './components/ApplicationCollaborationPanel.vue';
import ApplicationProcessingDetails from './components/ApplicationProcessingDetails.vue';

defineOptions({ name: 'WorkbenchApprovals' });

type ApprovalDecision = 'approved' | 'rejected';
type ApprovalHandlingAction = 'approve' | 'reject' | 'transfer';
type DemoProfileCode =
  | 'admin'
  | 'cc'
  | 'finance'
  | 'media'
  | 'office'
  | 'requester';

const DEFAULT_APPLICATION_LIST_PAGE_SIZE = 10;
const APPLICATION_LIST_PAGE_SIZE_OPTIONS = [
  '10',
  '20',
  '50',
  '100',
  '200',
  '500',
];
const BATCH_DECISION_LIMIT = 100;
const APPLICATION_FORM_TAG_LIMIT = 4;
const APPROVAL_LIST_UPDATED_RECORD_KEY = 'adpulse:approval-list:updated-record';

interface ApproverIdentity {
  id?: string;
  name: string;
  roleLabel: string;
}

const applicationStore = useResourceApplicationStore();
const mediaResourceStore = useMediaResourceStore();
const userStore = useUserStore();
const route = useRoute();
const router = useRouter();
const { applications } = storeToRefs(applicationStore);
const backendApplicationRecords = ref<ResourceApplication[]>([]);
const backendEligibleApprovalIds = ref<Set<string>>(new Set());
const backendApplicationDefinitions = ref<ApplicationDefinition[]>([]);
const systemDepartmentOptions = ref<Array<{ label: string; value: string }>>(
  [],
);
const departmentOptionsLoading = ref(false);
const hasLoadedDepartmentOptions = ref(false);
const hasLoadedApprovalList = ref(false);
const mergedApplications = computed(() => {
  if (demoMode) return applications.value;
  return [
    ...backendApplicationRecords.value,
    ...applications.value.filter((record) => !/^\d+$/.test(String(record.id))),
  ];
});
const applicationService = new ApplicationService(
  new LegacyApplicationStoreAdapter({
    applications: () => applications.value,
    remove: applicationStore.removeApplication,
    upsert: applicationStore.upsertApplication,
  }),
);
const workflowRuntime = new ApplicationWorkflowRuntimeAdapter({
  applications: () => mergedApplications.value,
});
const resourceService = new ResourceService(
  new LegacyResourceStoreAdapter({
    approveApplication: (applicationId, accountIds, actor) =>
      mediaResourceStore.approveApplication(applicationId, accountIds, actor),
    createApplication: (input, actor) =>
      mediaResourceStore.createApplication(input, actor),
    listApplications: () => mediaResourceStore.applications,
    rejectApplication: (applicationId, reason, actor) =>
      mediaResourceStore.rejectApplication(applicationId, reason, actor),
    requestReturn: (assignmentOrAccountId, reason, actor) =>
      mediaResourceStore.requestReturn(assignmentOrAccountId, reason, actor),
  }),
);
const applicationResourceBridge = new ApplicationResourceBridgeService(
  applicationService,
  resourceService,
);
const demoMode = isFusionDemoMode();
const approvalWorkspaceEnabled = true;

const activeQueue = ref<ApprovalQueue>('pending');
const activeDemoProfile = ref<DemoProfileCode>('media');
const keyword = ref('');
const approvalListLoading = ref(!demoMode);
const approvalListError = ref('');
const approvalDetailLoading = ref(false);
const approvalDetailError = ref('');
const approvalPage = ref(1);
const approvalPageSize = ref(DEFAULT_APPLICATION_LIST_PAGE_SIZE);
const approvalTotal = ref(0);
const approvalMetadata = ref<ApprovalMetadata>({
  departments: [],
  queueCounts: {
    copied: 0,
    handling: 0,
    initiated: 0,
    pending: 0,
    processed: 0,
  },
  requesters: [],
});
const typeFilter = ref('all');
const departmentFilter = ref('all');
const requesterFilter = ref('all');
const decisionResultFilter = ref<'all' | ApprovalDecision>('all');
const filtersExpanded = ref(false);
const batchOperationsExpanded = ref(false);
const expandedApplicationFormFields = ref(new Set<string>());
const applicationPixelDetails = ref(new Map<string, SelectablePixel>());
const selectedRecordId = ref<string>();
const selectedRecordDetail = ref<ResourceApplication>();
const applicationListRef = ref<HTMLElement>();
const decisionRecord = ref<ResourceApplication>();
const decisionAction = ref<ApprovalDecision>('approved');
const decisionSubmitting = ref(false);
const decisionError = ref('');
const decisionForm = reactive({ remark: '' });
const selectedApprovalIds = ref<string[]>([]);
const approvalExporting = ref(false);
const batchDecisionOpen = ref(false);
const batchDecisionAction = ref<ApprovalDecision>('approved');
const batchDecisionSubmitting = ref(false);
const batchDecisionError = ref('');
const batchDecisionForm = reactive({ remark: '' });
const transferRecord = ref<ResourceApplication>();
const transferSubmitting = ref(false);
const transferCandidates = ref<ApprovalTransferCandidate[]>([]);
const transferCandidatesLoading = ref(false);
const transferError = ref('');
const transferForm = reactive({ recipientId: '', remark: '' });
const processingRecord = ref<ResourceApplication>();
const processingSubmitting = ref(false);
const processingError = ref('');
const processingForm = reactive({ remark: '' });
const processingRejectionRecord = ref<ResourceApplication>();
const processingRejectionSubmitting = ref(false);
const processingRejectionError = ref('');
const processingRejectionForm = reactive({ reason: '' });
const processingActionData = ref<Record<string, unknown>>({});
const processingUploadFiles = ref<Record<string, UploadFile[]>>({});
const processingUploadingFields = ref<Set<string>>(new Set());
const processingFieldErrors = ref<Record<string, string>>({});
const availableAssets = ref<MediaAsset[]>([]);
const assetSelectionLoading = ref(false);
const selectedAssetIds = ref<string[]>([]);
const assetSelectionError = ref('');

const inventoryTypes = new Set<MediaAssetType>([
  'BM',
  'COMPUTER',
  'EMAIL',
  'MOBILE',
  'PAGE',
  'PERSONAL',
  'PIXEL',
  'STATIC_IP',
  'TG',
]);

function applicationInventorySelection(record: ResourceApplication) {
  const assignment = record.handlerAction?.resourceAssignment;
  const socialTypeFieldKey =
    assignment?.assetTypeFieldKey ??
    (record.type === 'tg' ? 'socialAssetType' : '');
  const socialSelection = socialTypeFieldKey
    ? resolveSocialAssetSelection(record.formData?.[socialTypeFieldKey])
    : undefined;
  if (socialSelection) return { ...socialSelection, social: true as const };

  const assetType = record.platform as MediaAssetType;
  if (!inventoryTypes.has(assetType)) return;
  return {
    assetType,
    label: approvalApplicationTypeLabels[assetType] ?? assetType,
    social: false as const,
  };
}

const processingInventorySelection = computed(() => {
  const record = processingRecord.value;
  return record ? applicationInventorySelection(record) : undefined;
});

const requiresAssetSelection = computed(() => {
  const record = processingRecord.value;
  if (!record) return false;
  if (!/^\d+$/.test(String(record.id))) return false;
  const configured = record.handlerAction?.resourceAssignment;
  if (configured && !configured.enabled) return false;
  return Boolean(applicationInventorySelection(record));
});

const expectedAssetQuantity = computed(() => {
  const record = processingRecord.value;
  if (!record || !requiresAssetSelection.value) return 0;
  const key =
    record.handlerAction?.resourceAssignment?.quantityFieldKey ??
    (record.platform === 'PAGE' ? 'pageCount' : 'quantity');
  const configuredValue = Number(record.formData?.[key]);
  return Math.max(
    1,
    Number.isFinite(configuredValue) ? configuredValue : (record.quantity ?? 1),
  );
});

/** 空渠道字段表示该库存类型按资产类型分配，不额外限制渠道或项目。 */
function assetChannelId(record: ResourceApplication) {
  const assignment = record.handlerAction?.resourceAssignment;
  if (assignment && !assignment.channelFieldKey?.trim()) return '';
  const channelKey = assignment?.channelFieldKey ?? 'channelId';
  return String(record.formData?.[channelKey] ?? record.projectId ?? '').trim();
}

const processingFormSchema = computed(
  () =>
    (processingRecord.value?.handlerAction?.formSchema ??
      []) as DynamicFormField[],
);

/** 已配置完整办理结果的账户流程不再重复录入通用处理说明。 */
const needsStandaloneProcessingRemark = computed(
  () =>
    !['ACCOUNT_OPENING', 'ACCOUNT_OPERATION'].includes(
      processingRecord.value?.platform ?? '',
    ),
);

const availableAssetOptions = computed(() =>
  availableAssets.value.map((asset) => ({
    disabled:
      selectedAssetIds.value.length >= expectedAssetQuantity.value &&
      !selectedAssetIds.value.includes(String(asset.id)),
    label: `${asset.assetName} · ${asset.assetCode} · ${assetStatusLabel(asset.status)}`,
    value: String(asset.id),
  })),
);

function assetStatusLabel(status: MediaAsset['status']) {
  const labels: Record<MediaAsset['status'], string> = {
    ASSIGNED: '已分配',
    AVAILABLE: '可用',
    DISABLED: '已停用',
    RETURN_PENDING: '待回收',
  };
  return labels[status];
}

const demoProfiles: Record<DemoProfileCode, ApproverIdentity> = {
  admin: {
    id: 'user-platform-admin',
    name: '平台管理员',
    roleLabel: '管理员',
  },
  cc: {
    id: 'user-project-owner',
    name: '项目负责人',
    roleLabel: '抄送人',
  },
  finance: {
    id: 'user-finance-lead',
    name: '王楠',
    roleLabel: '财务审批',
  },
  media: {
    id: 'user-media-lead',
    name: '周敏',
    roleLabel: '媒介审批',
  },
  office: {
    id: 'user-office-lead',
    name: '郑然',
    roleLabel: '行政与资产审批',
  },
  requester: {
    id: 'user-zhao-ning',
    name: '赵宁',
    roleLabel: '申请人',
  },
};

const demoProfileOptions = [
  { label: '周敏 · 媒介审批', value: 'media' },
  { label: '郑然 · 行政与资产审批', value: 'office' },
  { label: '王楠 · 财务审批', value: 'finance' },
  { label: '赵宁 · 申请人', value: 'requester' },
  { label: '项目负责人 · 抄送人', value: 'cc' },
  { label: '平台管理员 · 审批视角', value: 'admin' },
];

const demoTransferCandidates: Record<
  ResourceApplication['approvalRole'],
  ApprovalTransferCandidate[]
> = {
  finance: [
    {
      departmentId: 'dept-finance',
      departmentName: '财务部',
      id: 'user-finance-peer',
      name: '刘畅',
    },
  ],
  media: [
    {
      departmentId: 'dept-media',
      departmentName: '媒介部',
      id: 'user-media-peer',
      name: '李珊',
    },
  ],
  office: [
    {
      departmentId: 'dept-office',
      departmentName: '行政部',
      id: 'user-office-peer',
      name: '陈晓',
    },
  ],
};

const typeMeta: Record<
  ApplicationType,
  { color: string; icon: string; label: string }
> = {
  account: {
    color: 'blue',
    icon: 'lucide:badge-dollar-sign',
    label: applicationTypeLabels.account,
  },
  computer: {
    color: 'purple',
    icon: 'lucide:laptop',
    label: applicationTypeLabels.computer,
  },
  mobile: {
    color: 'magenta',
    icon: 'lucide:smartphone',
    label: applicationTypeLabels.mobile,
  },
  payment: {
    color: 'orange',
    icon: 'lucide:banknote',
    label: applicationTypeLabels.payment,
  },
  pixel: {
    color: 'cyan',
    icon: 'lucide:scan-line',
    label: applicationTypeLabels.pixel,
  },
  project: {
    color: 'default',
    icon: 'lucide:folder-check',
    label: applicationTypeLabels.project,
  },
  tg: {
    color: 'geekblue',
    icon: 'lucide:messages-square',
    label: applicationTypeLabels.tg,
  },
};

const statusMeta: Record<ApplicationStatus, { color: string; label: string }> =
  {
    approved: { color: 'success', label: '已通过' },
    draft: { color: 'default', label: '草稿' },
    pending: { color: 'processing', label: '待审批' },
    processing: { color: 'warning', label: '待办理' },
    rejected: { color: 'error', label: '已拒绝' },
  };

const columns = [
  { key: 'application', title: '申请单', width: '30%' },
  { key: 'ownership', title: '归属与申请人', width: '25%' },
  { key: 'approval', title: '审批状态', width: '25%' },
  { key: 'actions', title: '操作', width: '20%' },
];

const currentIdentity = computed<ApproverIdentity>(() => {
  if (demoMode) return demoProfiles[activeDemoProfile.value];
  const user = userStore.userInfo as
    | undefined
    | {
        _id?: number | string;
        user_id?: number | string;
        userId?: number | string;
      };
  const candidate = user?.userId ?? user?.user_id ?? user?._id;
  const identityId =
    candidate === undefined || candidate === null
      ? ''
      : String(candidate).trim();
  return {
    id: identityId || undefined,
    name:
      userStore.userInfo?.realName ||
      userStore.userInfo?.full_name ||
      userStore.userInfo?.username ||
      '当前用户',
    roleLabel: '审批人',
  };
});

function mapBackendApplication(
  item: Parameters<typeof mapBackendApplicationRecord>[0],
  decision?: Parameters<typeof mapBackendApplicationRecord>[2],
) {
  return mapBackendApplicationRecord(item, currentIdentity.value, decision);
}

/**
 * 将办理页刚完成的审批结果合并回缓存的审批中心，避免已拒绝单因不再属于待审批接口而丢失。
 */
let approvalListRequestSequence = 0;
let approvalListAbortController: AbortController | undefined;
let approvalDetailRequestSequence = 0;
let approvalDetailAbortController: AbortController | undefined;
let keywordDebounceTimer: ReturnType<typeof setTimeout> | undefined;
let normalizingApprovalFilters = false;
const debouncedKeyword = ref('');

const { isApplyingRoute } = useRouteListQuery({
  fields: {
    decision: createStringRouteQueryField(decisionResultFilter, {
      allowedValues: ['all', 'approved', 'rejected'],
      defaultValue: 'all',
    }),
    department: createStringRouteQueryField(departmentFilter, {
      defaultValue: 'all',
    }),
    page: createPositiveIntegerRouteQueryField(approvalPage, {
      defaultValue: 1,
    }),
    pageSize: createPositiveIntegerRouteQueryField(approvalPageSize, {
      allowedValues: APPLICATION_LIST_PAGE_SIZE_OPTIONS.map(Number),
      defaultValue: DEFAULT_APPLICATION_LIST_PAGE_SIZE,
    }),
    q: createStringRouteQueryField(keyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
    queue: createStringRouteQueryField(activeQueue, {
      allowedValues: [
        'pending',
        'handling',
        'processed',
        'copied',
        'initiated',
      ],
      defaultValue: 'pending',
    }),
    requester: createStringRouteQueryField(requesterFilter, {
      defaultValue: 'all',
    }),
    type: createStringRouteQueryField(typeFilter, {
      defaultValue: 'all',
    }),
  },
  onRouteApplied: () => {
    if (keywordDebounceTimer) clearTimeout(keywordDebounceTimer);
    debouncedKeyword.value = keyword.value;
    if (demoMode) {
      selectedRecordId.value = paginatedApplications.value[0]?.id;
      return;
    }
    if (hasLoadedApprovalList.value) {
      void loadApprovalPageFromRoute(approvalPage.value);
    }
  },
  route,
  router,
});
debouncedKeyword.value = keyword.value;

function approvalPageParams(page: number) {
  const selectedDefinition = backendApplicationDefinitions.value.find(
    (definition) => String(definition.id) === typeFilter.value,
  );
  return {
    applicationDefinitionId: selectedDefinition
      ? String(selectedDefinition.id)
      : undefined,
    assetType:
      typeFilter.value !== 'all' && !selectedDefinition
        ? typeFilter.value
        : undefined,
    decisionResult:
      activeQueue.value === 'processed' && decisionResultFilter.value !== 'all'
        ? (decisionResultFilter.value.toUpperCase() as 'APPROVED' | 'REJECTED')
        : undefined,
    departmentId:
      departmentFilter.value === 'all' ? undefined : departmentFilter.value,
    keyword: debouncedKeyword.value.trim() || undefined,
    page,
    pageSize: approvalPageSize.value,
    queue: activeQueue.value,
    requesterId:
      requesterFilter.value === 'all' ? undefined : requesterFilter.value,
  };
}

async function loadApprovalMetadata() {
  if (demoMode) return;
  approvalMetadata.value = await assetFlowApi.approvalMetadata();
}

async function loadApprovalList(requestedPage = 1) {
  if (demoMode) return;
  approvalListError.value = '';
  approvalListAbortController?.abort();
  approvalListAbortController = new AbortController();
  approvalDetailAbortController?.abort();
  approvalDetailRequestSequence += 1;
  approvalDetailLoading.value = false;
  approvalDetailError.value = '';
  approvalListLoading.value = true;
  approvalPage.value = requestedPage;
  backendApplicationRecords.value = [];
  backendEligibleApprovalIds.value = new Set();
  selectedApprovalIds.value = [];
  selectedRecordId.value = undefined;
  selectedRecordDetail.value = undefined;
  applicationListRef.value?.scrollTo({ top: 0 });
  const requestSequence = ++approvalListRequestSequence;
  const signal = approvalListAbortController?.signal;
  try {
    const result = await assetFlowApi.approvalPage(
      approvalPageParams(requestedPage),
      { signal },
    );
    if (!isLatestApprovalRequest(requestSequence, approvalListRequestSequence))
      return;
    const lastPage = Math.max(1, Math.ceil(result.total / result.pageSize));
    if (requestedPage > lastPage) {
      await loadApprovalList(lastPage);
      return;
    }
    const mappedItems = result.items.map((item) =>
      mapBackendApprovalListItem(item, currentIdentity.value),
    );
    backendApplicationRecords.value = mappedItems;
    backendEligibleApprovalIds.value =
      activeQueue.value === 'pending'
        ? new Set(backendApplicationRecords.value.map((record) => record.id))
        : new Set();
    approvalPage.value = result.page;
    approvalPageSize.value = result.pageSize;
    approvalTotal.value = result.total;
    selectedRecordId.value = backendApplicationRecords.value[0]?.id;
  } catch (error) {
    if (!signal?.aborted) approvalListError.value = '审批列表加载失败，请重试';
  } finally {
    if (isLatestApprovalRequest(requestSequence, approvalListRequestSequence)) {
      approvalListLoading.value = false;
      hasLoadedApprovalList.value = true;
    }
  }
}

function normalizeApprovalFilters() {
  let changed = false;
  const validTypes = new Set(
    backendApplicationDefinitions.value.length > 0
      ? backendApplicationDefinitions.value.map((item) => String(item.id))
      : Object.keys(approvalApplicationTypeLabels),
  );
  const validDepartments = new Set(
    approvalMetadata.value.departments.map((item) => item.value),
  );
  const validRequesters = new Set(
    approvalMetadata.value.requesters.map((item) => item.value),
  );
  if (typeFilter.value !== 'all' && !validTypes.has(typeFilter.value)) {
    typeFilter.value = 'all';
    changed = true;
  }
  if (
    departmentFilter.value !== 'all' &&
    !validDepartments.has(departmentFilter.value)
  ) {
    departmentFilter.value = 'all';
    changed = true;
  }
  if (
    requesterFilter.value !== 'all' &&
    !validRequesters.has(requesterFilter.value)
  ) {
    requesterFilter.value = 'all';
    changed = true;
  }
  return changed;
}

async function refreshApprovalWorkspace(page = approvalPage.value) {
  if (demoMode) return;
  await loadApprovalMetadata();
  await loadApprovalPageFromRoute(page);
}

async function loadApprovalPageFromRoute(page: number) {
  normalizingApprovalFilters = true;
  const filtersChanged = normalizeApprovalFilters();
  await nextTick();
  normalizingApprovalFilters = false;
  await loadApprovalList(filtersChanged ? 1 : page);
}

function consumeApprovalListUpdate() {
  if (!sessionStorage.getItem(APPROVAL_LIST_UPDATED_RECORD_KEY)) return;
  sessionStorage.removeItem(APPROVAL_LIST_UPDATED_RECORD_KEY);
  void refreshApprovalWorkspace();
}

function flattenDepartmentOptions(
  departments: readonly SystemDepartmentApi.Department[],
  parentName = '',
): Array<{ label: string; value: string }> {
  return departments.flatMap((department) => {
    const label = parentName
      ? `${parentName} / ${department.deptName}`
      : department.deptName;
    return [
      ...(department.status === 1 ? [{ label, value: department.id }] : []),
      ...flattenDepartmentOptions(department.children ?? [], label),
    ];
  });
}

/** 部门筛选以系统组织架构为准，已归档审批单的旧部门仅用于兼容回显。 */
async function loadSystemDepartmentOptions() {
  if (hasLoadedDepartmentOptions.value || departmentOptionsLoading.value)
    return;

  departmentOptionsLoading.value = true;
  try {
    systemDepartmentOptions.value = flattenDepartmentOptions(
      await getSystemDepartmentTree(),
    );
    hasLoadedDepartmentOptions.value = true;
  } catch {
    // 组织接口短暂不可用时，仍可按审批记录中的历史部门筛选；请求层已提示失败原因。
  } finally {
    departmentOptionsLoading.value = false;
  }
}

onMounted(async () => {
  void loadSystemDepartmentOptions();
  if (!demoMode) {
    backendApplicationDefinitions.value = await assetFlowApi
      .applicationDefinitions()
      .catch(() => []);
    await refreshApprovalWorkspace();
  } else {
    hasLoadedApprovalList.value = true;
  }
  consumeApprovalListUpdate();
});

let hasActivatedApprovalsPage = false;
onActivated(() => {
  if (!hasActivatedApprovalsPage) {
    hasActivatedApprovalsPage = true;
    return;
  }
  if (!hasLoadedApprovalList.value || demoMode) return;
  void loadSystemDepartmentOptions();
  void refreshApprovalWorkspace().then(consumeApprovalListUpdate);
});

function canHandle(value: unknown, action: ApprovalHandlingAction) {
  const record = value as ResourceApplication;
  // 数字 ID 来自后端动态流程；审批资格已按多人或角色在服务端完成校验。
  if (
    /^\d+$/.test(record.id) &&
    backendEligibleApprovalIds.value.has(record.id)
  ) {
    return true;
  }
  const state = workflowRuntime.getState(record.id, currentIdentity.value);
  return Boolean(
    state?.allowedActions.some(
      (item) => item.action === action && item.allowed,
    ),
  );
}

function canProcess(value: unknown) {
  const record = value as ResourceApplication;
  return Boolean(
    record.status === 'processing' &&
      record.handlerId &&
      record.handlerId === currentIdentity.value.id,
  );
}

/** 转交权限跟随当前流程阶段，不允许已离开队列的原负责人继续操作。 */
function canTransfer(value: unknown) {
  const record = toApplication(value);
  if (record.status === 'processing') return canProcess(record);
  return record.status === 'pending' && canHandle(record, 'transfer');
}

/** 只有当前审批节点或办理节点的负责人才显示“办理”语义。 */
function applicationActionLabel(value: unknown, viewLabel = '查看') {
  // 审批节点只提供通过/拒绝；“办理”仅表示已进入后续业务办理节点。
  return canProcess(value) ? '办理' : viewLabel;
}

/** 申请人、节点审批人、办理人和抄送人可参与流程评论。 */
function canCommentOnApplication(value: unknown) {
  const record = toApplication(value);
  const identityId = currentIdentity.value.id?.trim();
  const participantIds = [
    record.requesterId,
    record.handlerId,
    ...record.approvalNodes.map((node) => node.approverId),
  ].filter(Boolean);
  if (identityId && participantIds.includes(identityId)) return true;
  if (
    record.requester === currentIdentity.value.name ||
    record.handlerName === currentIdentity.value.name ||
    record.ccUsers.includes(currentIdentity.value.name) ||
    record.approvalNodes.some(
      (node) => node.approver === currentIdentity.value.name,
    )
  ) {
    return true;
  }
  return (
    /^\d+$/.test(record.id) && backendEligibleApprovalIds.value.has(record.id)
  );
}

function addLocalComment(
  record: ResourceApplication,
  comment: ApplicationComment,
) {
  if (record.comments.some((item) => item.id === comment.id)) return;
  record.comments.push(comment);
}

async function loadApplicationComments(record: ResourceApplication) {
  if (!/^\d+$/.test(record.id)) return;
  record.comments = await assetFlowApi.comments(record.id);
}

async function publishApplicationComment(
  record: ResourceApplication,
  content: string,
) {
  return assetFlowApi.comment(record.id, content);
}

function commentSubmitRequest(record: ResourceApplication) {
  if (!/^\d+$/.test(record.id)) return undefined;
  return (content: string) => publishApplicationComment(record, content);
}

function hasProcessed(record: ResourceApplication) {
  return record.approvalRecords.some(
    (history) =>
      ['approved', 'rejected'].includes(history.action) &&
      ((history.actorId && history.actorId === currentIdentity.value.id) ||
        history.actor === currentIdentity.value.name),
  );
}

function hasBeenCopied(record: ResourceApplication) {
  return (
    record.ccUsers.includes(currentIdentity.value.name) ||
    record.approvalRecords.some(
      (history) =>
        history.action === 'copied' &&
        history.remark.includes(currentIdentity.value.name),
    )
  );
}

const submittedApplications = computed(() =>
  mergedApplications.value.filter((record) => record.status !== 'draft'),
);

const pendingApplications = computed(() =>
  submittedApplications.value.filter(
    (record) => record.status === 'pending' && canHandle(record, 'approve'),
  ),
);

function canBatchDecide(record: ResourceApplication) {
  return isBatchDecisionEligible(
    record,
    canHandle(record, 'approve'),
    backendEligibleApprovalIds.value.has(record.id),
  );
}

const selectedBatchRecords = computed(() =>
  pendingApplications.value.filter(
    (record) =>
      selectedApprovalIds.value.includes(record.id) && canBatchDecide(record),
  ),
);

function canSelectForBatchOperation(record: ResourceApplication) {
  if (demoMode || !/^\d+$/.test(record.id)) return false;
  return activeQueue.value !== 'pending' || canBatchDecide(record);
}

const selectedOperationRecords = computed(() =>
  paginatedApplications.value.filter(
    (record) =>
      selectedApprovalIds.value.includes(record.id) &&
      canSelectForBatchOperation(record),
  ),
);

const approvalRowSelection = computed(() => ({
  getCheckboxProps: (record: ResourceApplication) => {
    const selected = selectedApprovalIds.value.includes(record.id);
    return {
      disabled:
        !canSelectForBatchOperation(record) ||
        (!selected &&
          selectedOperationRecords.value.length >= BATCH_DECISION_LIMIT),
    };
  },
  onChange: (keys: Array<number | string>) => {
    const eligibleIds = keys
      .map(String)
      .filter((id) =>
        paginatedApplications.value.some(
          (record) => record.id === id && canSelectForBatchOperation(record),
        ),
      );
    if (eligibleIds.length > BATCH_DECISION_LIMIT) {
      message.warning(`单次最多选择 ${BATCH_DECISION_LIMIT} 条申请`);
    }
    selectedApprovalIds.value = eligibleIds.slice(0, BATCH_DECISION_LIMIT);
  },
  selectedRowKeys: selectedApprovalIds.value,
}));

// 办理队列必须同时校验办理状态与稳定用户 ID，避免只因看过或发起过申请就进入列表。
const handlingApplications = computed(() =>
  submittedApplications.value.filter((record) => canProcess(record)),
);

const processedApplications = computed(() =>
  submittedApplications.value.filter((record) => hasProcessed(record)),
);

const copiedApplications = computed(() =>
  submittedApplications.value.filter((record) => hasBeenCopied(record)),
);

function isCurrentRequester(record: ResourceApplication) {
  const currentUserId = currentIdentity.value.id;
  const requesterId = record.requesterId?.trim();

  // 后端申请按稳定用户 ID 归属；姓名仅用于兼容缺少 requesterId 的旧本地数据。
  if (currentUserId && requesterId) return requesterId === currentUserId;
  return record.requester === currentIdentity.value.name;
}

/** 已拒绝的申请由发起人补充信息后，以新审批单重新进入流程。 */
function canResubmit(value: unknown) {
  const record = toApplication(value);
  return record.status === 'rejected' && isCurrentRequester(record);
}

const initiatedApplications = computed(() =>
  submittedApplications.value.filter((record) => isCurrentRequester(record)),
);

const queueOptions = computed(() => [
  {
    label: `待我审批 ${queueCount('pending')}`,
    value: 'pending',
  },
  {
    label: `待办理 ${queueCount('handling')}`,
    value: 'handling',
  },
  {
    label: `已经审批 ${queueCount('processed')}`,
    value: 'processed',
  },
  { label: `抄送我 ${queueCount('copied')}`, value: 'copied' },
  { label: `已发起 ${queueCount('initiated')}`, value: 'initiated' },
]);

function queueCount(queue: ApprovalQueue) {
  if (!demoMode) return approvalMetadata.value.queueCounts[queue];
  if (queue === 'pending') return pendingApplications.value.length;
  if (queue === 'handling') return handlingApplications.value.length;
  if (queue === 'processed') return processedApplications.value.length;
  if (queue === 'copied') return copiedApplications.value.length;
  return initiatedApplications.value.length;
}

const typeOptions = computed(() => {
  const applicationOptions = [...backendApplicationDefinitions.value]
    .sort(
      (left, right) =>
        left.sortOrder - right.sortOrder ||
        left.applicationName.localeCompare(right.applicationName, 'zh-CN'),
    )
    .map((definition) => ({
      label: definition.applicationName,
      value: String(definition.id),
    }));
  const fallbackOptions = Object.entries(approvalApplicationTypeLabels).map(
    ([value, label]) => ({ label, value }),
  );
  return [
    { label: '全部类型', value: 'all' },
    ...(applicationOptions.length > 0 ? applicationOptions : fallbackOptions),
  ];
});

const legacyApplicationTypeAssets: Record<ApplicationType, string[]> = {
  account: ['BM', 'PERSONAL'],
  computer: ['COMPUTER'],
  mobile: ['MOBILE'],
  payment: ['PAYMENT'],
  pixel: ['PIXEL'],
  project: [],
  tg: ['TG'],
};

/** 后端记录按申请入口 ID 精确筛选，旧本地记录按历史大类兼容。 */
function matchesTypeFilter(record: ResourceApplication) {
  if (typeFilter.value === 'all') return true;
  const selectedDefinition = backendApplicationDefinitions.value.find(
    (definition) => String(definition.id) === typeFilter.value,
  );
  if (selectedDefinition) {
    const applicationDefinitionId = String(
      record.formData?.applicationDefinitionId ?? '',
    ).trim();
    return applicationDefinitionId === String(selectedDefinition.id);
  }
  if (record.platform === typeFilter.value) return true;
  return legacyApplicationTypeAssets[record.type].includes(typeFilter.value);
}

const departmentOptions = computed(() => {
  const options = new Map(
    [
      ...approvalMetadata.value.departments,
      ...systemDepartmentOptions.value,
    ].map((option) => [option.value, option]),
  );

  for (const record of submittedApplications.value) {
    if (!record.departmentId || !record.departmentName) continue;
    if (!options.has(record.departmentId)) {
      options.set(record.departmentId, {
        label: `${record.departmentName}（历史部门）`,
        value: record.departmentId,
      });
    }
  }

  return [{ label: '全部部门', value: 'all' }, ...options.values()];
});

const requesterOptions = computed(() => [
  { label: '全部申请人', value: 'all' },
  ...[
    ...new Map([
      ...approvalMetadata.value.requesters.map(
        (option) => [option.value, option.label] as const,
      ),
      ...submittedApplications.value
        .filter((record) => Boolean(record.requesterId))
        .map(
          (record) =>
            [
              record.requesterId!,
              record.requesterName || record.requester,
            ] as const,
        ),
    ]),
  ]
    .sort(([, left], [, right]) => left.localeCompare(right, 'zh-CN'))
    .map(([value, label]) => ({ label, value })),
]);

const decisionResultOptions = [
  { label: '全部审批结果', value: 'all' },
  { label: '已通过', value: 'approved' },
  { label: '已拒绝', value: 'rejected' },
];

const queueTitle = computed(() => {
  if (activeQueue.value === 'handling') return '待办理';
  if (activeQueue.value === 'processed') return '已经审批';
  if (activeQueue.value === 'copied') return '抄送我';
  if (activeQueue.value === 'initiated') return '已发起';
  return '待我审批';
});

const queueDescription = computed(() => {
  if (activeQueue.value === 'handling') {
    return '仅显示已完成审批、需要当前用户办理的申请。';
  }
  if (activeQueue.value === 'processed') {
    return '仅显示由当前审批人通过或拒绝的申请。';
  }
  if (activeQueue.value === 'copied') {
    return '显示审批完成后抄送给当前用户的申请。';
  }
  if (activeQueue.value === 'initiated') {
    return '显示当前用户已经发起并提交的申请。';
  }
  return '仅显示当前审批节点需要当前用户审批的申请。';
});

const filteredApplications = computed(() => {
  if (!demoMode) return backendApplicationRecords.value;
  let source = pendingApplications.value;
  if (activeQueue.value === 'handling') source = handlingApplications.value;
  if (activeQueue.value === 'processed') source = processedApplications.value;
  if (activeQueue.value === 'copied') source = copiedApplications.value;
  if (activeQueue.value === 'initiated') source = initiatedApplications.value;
  const query = keyword.value.trim().toLowerCase();

  return filterApprovalApplications(source, {
    departmentId:
      departmentFilter.value === 'all' ? undefined : departmentFilter.value,
    requesterId:
      requesterFilter.value === 'all' ? undefined : requesterFilter.value,
  })
    .filter(
      (record) =>
        matchesTypeFilter(record) &&
        (activeQueue.value !== 'processed' ||
          decisionResultFilter.value === 'all' ||
          record.approvalRecords.some(
            (history) =>
              history.actor === currentIdentity.value.name &&
              history.action === decisionResultFilter.value,
          )) &&
        (!query ||
          [
            record.id,
            record.title,
            record.project,
            record.requester,
            record.requesterName,
            getApprovalDepartmentLabel(record),
            record.description,
            record.approver,
          ]
            .join(' ')
            .toLowerCase()
            .includes(query)),
    )
    .sort((left, right) => {
      return right.createdAt.localeCompare(left.createdAt);
    });
});

const paginatedApplications = computed(() => {
  if (!demoMode) return filteredApplications.value;
  return paginateApprovalRecords(
    filteredApplications.value,
    approvalPage.value,
    approvalPageSize.value,
  );
});

const approvalPaginationTotal = computed(() =>
  demoMode ? filteredApplications.value.length : approvalTotal.value,
);

watch([approvalPaginationTotal, approvalPageSize], ([total]) => {
  if (!demoMode) return;
  const lastPage = Math.max(1, Math.ceil(total / approvalPageSize.value));
  if (approvalPage.value > lastPage) approvalPage.value = lastPage;
});

const loadedBatchRecords = computed(() =>
  paginatedApplications.value.filter(canSelectForBatchOperation),
);

const selectableLoadedBatchRecords = computed(() =>
  limitApprovalBatchRecords(loadedBatchRecords.value, BATCH_DECISION_LIMIT),
);

const selectedLoadedBatchRecordCount = computed(() => {
  const selectedIds = new Set(selectedApprovalIds.value);
  return selectableLoadedBatchRecords.value.filter((record) =>
    selectedIds.has(record.id),
  ).length;
});

const areAllLoadedBatchRecordsSelected = computed(
  () =>
    selectableLoadedBatchRecords.value.length > 0 &&
    selectedLoadedBatchRecordCount.value ===
      selectableLoadedBatchRecords.value.length,
);

const areSomeLoadedBatchRecordsSelected = computed(
  () =>
    selectedLoadedBatchRecordCount.value > 0 &&
    !areAllLoadedBatchRecordsSelected.value,
);

function resetApplicationPage() {
  approvalPage.value = 1;
  approvalTotal.value = 0;
  selectedApprovalIds.value = [];
  selectedRecordId.value = undefined;
  selectedRecordDetail.value = undefined;
  applicationListRef.value?.scrollTo({ top: 0 });
}

function changeApprovalPage(page: number, pageSize: number) {
  const next = resolveApprovalPageChange(
    approvalPageSize.value,
    page,
    pageSize,
  );
  approvalPageSize.value = next.pageSize;
  approvalPage.value = next.page;
  selectedApprovalIds.value = [];
  selectedRecordId.value = undefined;
  selectedRecordDetail.value = undefined;
  applicationListRef.value?.scrollTo({ top: 0 });
  if (demoMode) {
    selectedRecordId.value = paginatedApplications.value[0]?.id;
    return;
  }
  void loadApprovalList(next.page);
}

watch(keyword, (value) => {
  if (isApplyingRoute.value) return;
  if (keywordDebounceTimer) clearTimeout(keywordDebounceTimer);
  keywordDebounceTimer = setTimeout(() => {
    debouncedKeyword.value = value;
  }, 300);
});

watch(
  [
    activeQueue,
    decisionResultFilter,
    departmentFilter,
    debouncedKeyword,
    requesterFilter,
    typeFilter,
  ],
  () => {
    if (isApplyingRoute.value || normalizingApprovalFilters) return;
    resetApplicationPage();
    if (demoMode) {
      selectedRecordId.value = paginatedApplications.value[0]?.id;
      return;
    }
    if (hasLoadedApprovalList.value) void loadApprovalList(1);
  },
);

watch(
  paginatedApplications,
  (records) => {
    const eligibleIds = new Set(
      records.filter(canSelectForBatchOperation).map((record) => record.id),
    );
    selectedApprovalIds.value = selectedApprovalIds.value.filter((id) =>
      eligibleIds.has(id),
    );
  },
  { deep: true },
);

const selectedRecordSummary = computed(
  () =>
    paginatedApplications.value.find(
      (record) => record.id === selectedRecordId.value,
    ) ?? paginatedApplications.value[0],
);

const selectedRecord = computed(() => {
  if (demoMode) return selectedRecordSummary.value;
  return selectedRecordDetail.value?.id === selectedRecordSummary.value?.id
    ? selectedRecordDetail.value
    : undefined;
});

async function loadApplicationDetail(recordId: string) {
  if (demoMode || !/^\d+$/.test(recordId)) return;
  approvalDetailAbortController?.abort();
  approvalDetailAbortController = new AbortController();
  const requestSequence = ++approvalDetailRequestSequence;
  const signal = approvalDetailAbortController.signal;
  approvalDetailLoading.value = true;
  approvalDetailError.value = '';
  selectedRecordDetail.value = undefined;
  try {
    const item = await assetFlowApi.application(recordId, {
      signal,
    });
    if (
      !isLatestApprovalRequest(requestSequence, approvalDetailRequestSequence)
    )
      return;
    const record = mapBackendApplication(item);
    selectedRecordDetail.value = record;
    await loadApplicationComments(record);
  } catch (error) {
    if (!signal.aborted) approvalDetailError.value = '审批详情加载失败，请重试';
  } finally {
    if (
      isLatestApprovalRequest(requestSequence, approvalDetailRequestSequence)
    ) {
      approvalDetailLoading.value = false;
    }
  }
}

watch(
  () => selectedRecordSummary.value?.id,
  (recordId) => {
    if (!recordId) {
      selectedRecordDetail.value = undefined;
      return;
    }
    if (demoMode) {
      if (selectedRecordSummary.value)
        void loadApplicationComments(selectedRecordSummary.value);
      return;
    }
    void loadApplicationDetail(recordId);
  },
  { immediate: true },
);

const summaryCards = computed(() => [
  {
    icon: 'lucide:inbox',
    label: '待我审批',
    queue: 'pending' as ApprovalQueue,
    tone: 'bg-blue-50 text-blue-600',
    value: queueCount('pending'),
  },
  {
    icon: 'lucide:package-check',
    label: '待办理',
    queue: 'handling' as ApprovalQueue,
    tone: 'bg-amber-50 text-amber-600',
    value: queueCount('handling'),
  },
  {
    icon: 'lucide:badge-check',
    label: '已经审批',
    queue: 'processed' as ApprovalQueue,
    tone: 'bg-emerald-50 text-emerald-600',
    value: queueCount('processed'),
  },
  {
    icon: 'lucide:copy-check',
    label: '抄送我',
    queue: 'copied' as ApprovalQueue,
    tone: 'bg-cyan-50 text-cyan-600',
    value: queueCount('copied'),
  },
  {
    icon: 'lucide:send',
    label: '已发起',
    queue: 'initiated' as ApprovalQueue,
    tone: 'bg-violet-50 text-violet-600',
    value: queueCount('initiated'),
  },
]);

watch(activeDemoProfile, () => {
  if (activeDemoProfile.value === 'requester') {
    activeQueue.value = 'initiated';
    return;
  }
  activeQueue.value = activeDemoProfile.value === 'cc' ? 'copied' : 'pending';
});

function selectQueue(queue: ApprovalQueue) {
  activeQueue.value = queue;
}

function selectRecord(record: ResourceApplication) {
  selectedRecordId.value = record.id;
}

function toApplication(value: unknown) {
  return value as ResourceApplication;
}

function formatApplicationDateTime(value: string) {
  return value
    .replace('T', ' ')
    .replace(/\.\d+(?=Z?$)/, '')
    .replace(/Z$/, '');
}

function approvalListMeta(record: ResourceApplication) {
  return [
    getApprovalDepartmentLabel(record),
    record.requesterName || record.requester,
    formatApplicationDateTime(record.createdAt),
  ].join(' · ');
}

function approvalRoleInfo(value: unknown) {
  return approvalRoleMeta[toApplication(value).approvalRole];
}

function lastDecision(value: unknown) {
  const record = toApplication(value);
  for (let index = record.approvalRecords.length - 1; index >= 0; index -= 1) {
    const history = record.approvalRecords[index];
    if (history && ['approved', 'rejected'].includes(history.action)) {
      return history;
    }
  }
  return undefined;
}

function requestDetail(value: unknown) {
  const record = toApplication(value);
  if (record.amount) {
    return `${record.currency ?? 'USD'} ${record.amount.toLocaleString()}`;
  }
  if (record.quantity) return `数量 ${record.quantity}`;
  return record.platform ?? '按申请说明配置';
}

function applicationFormFields(record: ResourceApplication) {
  return (record.formSchema ?? []) as DynamicFormField[];
}

function optionSnapshotBase(fieldKey: string) {
  if (fieldKey.endsWith('Ids')) return fieldKey.slice(0, -3);
  if (fieldKey.endsWith('Id')) return fieldKey.slice(0, -2);
  return fieldKey;
}

/**
 * 审批详情必须使用提交时的表单快照，避免审批配置更新后把历史申请解释为新字段。
 * 关联选择项优先展示提交时同步保存的名称，避免向审批人暴露内部 ID。
 */
function applicationFormValue(
  record: ResourceApplication,
  field: DynamicFormField,
) {
  const value = record.formData?.[field.key];
  if (value === undefined || value === null || value === '') return '-';

  if (field.type === 'image-upload') {
    const count = Array.isArray(value) ? value.length : 1;
    return `已上传 ${count} 张图片`;
  }

  if (field.optionSource && field.optionSource !== 'custom') {
    const snapshotBase = optionSnapshotBase(field.key);
    const snapshotKey = `${snapshotBase}${
      Array.isArray(value) ? 'Names' : 'Name'
    }`;
    const snapshot = record.formData?.[snapshotKey];
    if (Array.isArray(snapshot)) return snapshot.join('、') || '-';
    if (snapshot !== undefined && snapshot !== null && snapshot !== '') {
      return String(snapshot);
    }
  }

  if (field.type === 'date-range' && Array.isArray(value)) {
    const [startDate, endDate] = value.map(String);
    return startDate && endDate ? `${startDate} 至 ${endDate}` : '-';
  }

  return (Array.isArray(value) ? value : [value]).map(String).join('、');
}

interface ApplicationFormTagValue {
  key: string;
  label: string;
}

function applicationFormTagValues(
  record: ResourceApplication,
  field: DynamicFormField,
): ApplicationFormTagValue[] {
  const value = record.formData?.[field.key];
  if (value === undefined || value === null || value === '') return [];
  return (Array.isArray(value) ? value : [value])
    .map(String)
    .filter(Boolean)
    .map((assetRecordId) => {
      const pixel = applicationPixelDetails.value.get(assetRecordId);
      const label = [pixel?.pixelName, pixel?.pixelId]
        .filter(Boolean)
        .join(' · ');
      return {
        key: assetRecordId,
        label: label || assetRecordId,
      };
    });
}

async function loadApplicationPixelDetails(record?: ResourceApplication) {
  if (!record) return;
  const assetRecordIds = [
    ...new Set(
      applicationFormFields(record)
        .filter((field) => field.type === 'pixel-selector')
        .flatMap((field) => {
          const value = record.formData?.[field.key];
          return (Array.isArray(value) ? value : [value])
            .filter(
              (item) => item !== undefined && item !== null && item !== '',
            )
            .map(String);
        }),
    ),
  ];
  const missingIds = assetRecordIds.filter(
    (id) => !applicationPixelDetails.value.has(id),
  );
  if (missingIds.length === 0) return;

  try {
    const result = await assetFlowApi.selectablePixels({
      filterValues: { id: missingIds },
      page: 1,
      pageSize: Math.min(100, Math.max(missingIds.length, 10)),
    });
    const next = new Map(applicationPixelDetails.value);
    result.items.forEach((pixel) => next.set(pixel.id, pixel));
    applicationPixelDetails.value = next;
  } catch {
    message.warning('像素详情加载失败，暂时显示资产记录 ID');
  }
}

function applicationFormFieldExpansionKey(
  record: ResourceApplication,
  field: DynamicFormField,
) {
  return `${record.id}:${field.key}`;
}

function isApplicationFormFieldExpanded(
  record: ResourceApplication,
  field: DynamicFormField,
) {
  return expandedApplicationFormFields.value.has(
    applicationFormFieldExpansionKey(record, field),
  );
}

function visibleApplicationFormTags(
  record: ResourceApplication,
  field: DynamicFormField,
) {
  const values = applicationFormTagValues(record, field);
  return isApplicationFormFieldExpanded(record, field)
    ? values
    : values.slice(0, APPLICATION_FORM_TAG_LIMIT);
}

function toggleApplicationFormField(
  record: ResourceApplication,
  field: DynamicFormField,
) {
  const key = applicationFormFieldExpansionKey(record, field);
  const next = new Set(expandedApplicationFormFields.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  expandedApplicationFormFields.value = next;
}

watch(
  selectedRecord,
  async (record) => {
    await loadApplicationPixelDetails(record);
  },
  { immediate: true },
);

function openHandlePage(value: unknown) {
  const record = toApplication(value);
  if (canProcess(record)) {
    openProcessing(record);
    return;
  }
  selectRecord(record);
}

function openResubmit(value: unknown) {
  const record = toApplication(value);
  const applicationCode = String(
    record.formData?.applicationCode ?? record.platform ?? '',
  ).trim();
  if (!applicationCode) {
    message.warning('该申请缺少申请入口信息，暂时无法重新提交');
    return;
  }

  // 审批中心读取的是后端快照；先同步到申请表单的数据源，才能回填原申请字段。
  applicationStore.upsertApplication(record);
  void router.push({
    path: '/workbench/applications/create',
    query: {
      applicationCode,
      new: '1',
      resubmitId: record.id,
    },
  });
}

async function loadAvailableAssets(record: ResourceApplication) {
  if (!requiresAssetSelection.value) return;
  const inventorySelection = applicationInventorySelection(record);
  if (!inventorySelection) return;
  const applicationChannelId = assetChannelId(record);
  assetSelectionLoading.value = true;
  const recordId = String(record.id);
  try {
    const assets = await assetFlowApi.assets(
      inventorySelection.assetType,
      applicationChannelId,
    );
    if (String(processingRecord.value?.id) === recordId) {
      availableAssets.value = assets.filter(
        (asset) =>
          (!inventorySelection.social ||
            matchesSocialInventoryAsset(asset, inventorySelection)) &&
          asset.status === 'AVAILABLE' &&
          (!applicationChannelId ||
            String(asset.channelId || asset.projectId) ===
              applicationChannelId),
      );
    }
  } finally {
    if (String(processingRecord.value?.id) === recordId) {
      assetSelectionLoading.value = false;
    }
  }
}

function openDecision(value: unknown, action: ApprovalDecision) {
  const record = toApplication(value);
  decisionAction.value = action;
  decisionForm.remark = '';
  decisionError.value = '';
  availableAssets.value = [];
  selectedAssetIds.value = [];
  assetSelectionError.value = '';
  decisionRecord.value = record;
}

function approve(value: unknown) {
  openDecision(value, 'approved');
}

function openReject(value: unknown) {
  openDecision(value, 'rejected');
}

function closeDecision() {
  if (decisionSubmitting.value) return;
  decisionRecord.value = undefined;
  decisionForm.remark = '';
  decisionError.value = '';
  availableAssets.value = [];
  selectedAssetIds.value = [];
  assetSelectionError.value = '';
}

function clearDecisionError() {
  if (decisionForm.remark.trim()) decisionError.value = '';
}

function openBatchDecision(action: ApprovalDecision) {
  if (selectedBatchRecords.value.length === 0) return;
  batchDecisionAction.value = action;
  batchDecisionForm.remark = '';
  batchDecisionError.value = '';
  batchDecisionOpen.value = true;
}

function closeBatchDecision() {
  if (batchDecisionSubmitting.value) return;
  batchDecisionOpen.value = false;
  batchDecisionForm.remark = '';
  batchDecisionError.value = '';
}

function clearBatchDecisionError() {
  if (batchDecisionForm.remark.trim()) batchDecisionError.value = '';
}

function toggleBatchSelection(record: ResourceApplication, checked: boolean) {
  if (!canSelectForBatchOperation(record)) return;
  if (
    checked &&
    !selectedApprovalIds.value.includes(record.id) &&
    selectedOperationRecords.value.length >= BATCH_DECISION_LIMIT
  ) {
    message.warning(`单次最多选择 ${BATCH_DECISION_LIMIT} 条申请`);
    return;
  }
  selectedApprovalIds.value = checked
    ? [...new Set([...selectedApprovalIds.value, record.id])]
    : selectedApprovalIds.value.filter((id) => id !== record.id);
}

function toggleLoadedBatchSelection(checked: boolean) {
  if (!checked) {
    selectedApprovalIds.value = [];
    return;
  }

  if (loadedBatchRecords.value.length > BATCH_DECISION_LIMIT) {
    message.warning(`单次最多选择 ${BATCH_DECISION_LIMIT} 条申请`);
  }
  selectedApprovalIds.value = selectableLoadedBatchRecords.value.map(
    (record) => record.id,
  );
}

function approvalExportFileName() {
  const timestamp = new Date()
    .toLocaleString('zh-CN', {
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
    .replaceAll(/\D/g, '');
  return `审批中心_${timestamp}.xlsx`;
}

async function exportSelectedApprovals() {
  if (selectedOperationRecords.value.length === 0) {
    message.warning('请先选择要导出的审批单');
    return;
  }
  if (approvalExporting.value) return;
  approvalExporting.value = true;
  try {
    const blob = await assetFlowApi.exportApprovals({
      ids: selectedOperationRecords.value.map((record) => record.id),
    });
    await downloadBlob(blob, approvalExportFileName(), { mode: 'browser' });
    message.success(
      `已生成 ${selectedOperationRecords.value.length} 条审批单，浏览器正在下载`,
    );
  } finally {
    approvalExporting.value = false;
  }
}

async function submitBatchDecision() {
  const records = selectedBatchRecords.value;
  const remark = batchDecisionForm.remark.trim();
  if (records.length === 0) {
    message.warning('请先选择可审批的申请');
    return;
  }
  if (batchDecisionAction.value === 'rejected' && !remark) {
    batchDecisionError.value = '请填写统一审批备注';
    return;
  }

  batchDecisionSubmitting.value = true;
  try {
    const action = batchDecisionAction.value;
    await assetFlowApi.batchDecide({
      action: action === 'approved' ? 'APPROVE' : 'REJECT',
      ids: records.map((record) => record.id),
      remark,
    });
    const processedIds = new Set(records.map((record) => record.id));
    backendEligibleApprovalIds.value = new Set(
      [...backendEligibleApprovalIds.value].filter(
        (id) => !processedIds.has(id),
      ),
    );
    backendApplicationRecords.value = backendApplicationRecords.value.filter(
      (record) => !processedIds.has(String(record.id)),
    );
    selectedApprovalIds.value = [];
    batchDecisionOpen.value = false;
    batchDecisionForm.remark = '';
    batchDecisionError.value = '';
    if (!demoMode) await refreshApprovalWorkspace();
    message.success(
      `已批量${action === 'approved' ? '通过' : '拒绝'} ${records.length} 条申请`,
    );
  } finally {
    batchDecisionSubmitting.value = false;
  }
}

async function openTransfer(value: unknown) {
  const record = toApplication(value);
  if (!canTransfer(record)) {
    message.warning('当前负责人或申请状态已变化，请刷新后重试');
    return;
  }
  transferRecord.value = record;
  transferForm.recipientId = '';
  transferForm.remark = '';
  transferCandidates.value = [];
  transferError.value = '';
  transferCandidatesLoading.value = true;
  try {
    transferCandidates.value = demoMode
      ? demoTransferCandidates[record.approvalRole]
      : await assetFlowApi.transferCandidates(String(record.id));
  } catch {
    transferError.value = '无法加载可转交同事，请稍后重试';
  } finally {
    transferCandidatesLoading.value = false;
  }
}

function closeTransfer(force = false) {
  if (transferSubmitting.value && !force) return;
  transferRecord.value = undefined;
  transferForm.recipientId = '';
  transferForm.remark = '';
  transferCandidates.value = [];
  transferCandidatesLoading.value = false;
  transferError.value = '';
}

function clearTransferError() {
  if (transferForm.recipientId && transferForm.remark.trim()) {
    transferError.value = '';
  }
}

async function submitTransfer() {
  const record = transferRecord.value;
  const remark = transferForm.remark.trim();
  const recipient = transferCandidates.value.find(
    (candidate) => candidate.id === transferForm.recipientId,
  );
  if (!record) return;
  if (!recipient) {
    transferError.value = '请选择接收转交的同事';
    return;
  }
  if (!remark) {
    transferError.value = '请填写转交原因';
    return;
  }
  if (!canTransfer(record)) {
    transferError.value = '当前负责人或申请状态已变化，请刷新后重试';
    return;
  }
  transferSubmitting.value = true;
  try {
    if (/^\d+$/.test(String(record.id))) {
      await assetFlowApi.transfer(String(record.id), {
        recipientId: recipient.id,
        remark,
      });
    } else {
      applicationService.transfer(record.id, {
        actor: {
          id: currentIdentity.value.id,
          name: currentIdentity.value.name,
          role: currentIdentity.value.roleLabel,
        },
        recipient,
        remark,
      });
    }
    selectedRecordId.value = undefined;
    closeTransfer(true);
    if (!demoMode) await refreshApprovalWorkspace();
    message.success(`申请已转交给${recipient.name}`);
  } finally {
    transferSubmitting.value = false;
  }
}

function clearAssetSelectionError() {
  if (selectedAssetIds.value.length === expectedAssetQuantity.value) {
    assetSelectionError.value = '';
  }
}

function releaseProcessingUploadUrl(file: UploadFile) {
  if (file.thumbUrl?.startsWith('blob:')) {
    URL.revokeObjectURL(file.thumbUrl);
  }
}

function resetProcessingUploads() {
  for (const files of Object.values(processingUploadFiles.value)) {
    files.forEach((file) => releaseProcessingUploadUrl(file));
  }
  processingUploadFiles.value = {};
  processingUploadingFields.value = new Set();
}

function isProcessingFieldUploading(fieldKey: string) {
  return processingUploadingFields.value.has(fieldKey);
}

function processingUploadCount(fieldKey: string) {
  return processingUploadFiles.value[fieldKey]?.length ?? 0;
}

function openProcessing(value: unknown) {
  const record = toApplication(value);
  resetProcessingUploads();
  processingRecord.value = record;
  processingForm.remark = '';
  processingActionData.value = {};
  processingFieldErrors.value = {};
  processingError.value = '';
  availableAssets.value = [];
  selectedAssetIds.value = [];
  assetSelectionError.value = '';
  void loadAvailableAssets(record);
}

function closeProcessing() {
  if (processingSubmitting.value) return;
  processingRecord.value = undefined;
  processingForm.remark = '';
  processingActionData.value = {};
  resetProcessingUploads();
  processingFieldErrors.value = {};
  processingError.value = '';
  availableAssets.value = [];
  selectedAssetIds.value = [];
  assetSelectionError.value = '';
}

function openProcessingRejection(value: unknown) {
  const record = toApplication(value);
  if (!canProcess(record)) {
    message.warning('办理人或申请状态已变化，请刷新后重试');
    return;
  }
  processingRejectionForm.reason = '';
  processingRejectionError.value = '';
  processingRejectionRecord.value = record;
}

function closeProcessingRejection() {
  if (processingRejectionSubmitting.value) return;
  processingRejectionRecord.value = undefined;
  processingRejectionForm.reason = '';
  processingRejectionError.value = '';
}

function clearProcessingFieldError(key: string) {
  delete processingFieldErrors.value[key];
}

function processingNumberValue(key: string) {
  const value = processingActionData.value[key];
  return typeof value === 'number' ? value : undefined;
}

function processingTextValue(key: string) {
  const value = processingActionData.value[key];
  return typeof value === 'string' ? value : '';
}

function updateProcessingField(key: string, value: unknown) {
  processingActionData.value[key] = value;
  clearProcessingFieldError(key);
}

function validateProcessingActionData() {
  const errors: Record<string, string> = {};
  for (const field of processingFormSchema.value) {
    const value = processingActionData.value[field.key];
    const empty =
      value === undefined ||
      value === null ||
      value === '' ||
      (Array.isArray(value) && value.length === 0);
    if (field.required && empty) {
      errors[field.key] = `请填写${field.label}`;
      continue;
    }
    if (empty) continue;
    if (field.validationRule === 'digit-list') {
      const ids = String(value)
        .replaceAll('；', ';')
        .split(/[;\n\r]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      if (ids.length === 0 || ids.some((id) => !/^\d+$/.test(id))) {
        errors[field.key] = `${field.label}仅支持数字，每行一个或用分号分隔`;
        continue;
      }
      if (
        processingRecord.value?.platform === 'ACCOUNT_OPENING' &&
        field.key === 'openedAccountIds'
      ) {
        const expectedQuantity = Math.max(
          1,
          Number(
            processingRecord.value.formData?.quantity ??
              processingRecord.value.quantity ??
              1,
          ),
        );
        if (ids.length !== expectedQuantity) {
          errors[field.key] = `请填写 ${expectedQuantity} 个广告账户 ID`;
          continue;
        }
      }
    }
    if (field.type === 'number') {
      const numberValue = Number(value);
      if (!Number.isFinite(numberValue)) {
        errors[field.key] = `${field.label}格式不正确`;
      } else if (field.minValue !== undefined && numberValue < field.minValue) {
        errors[field.key] = `${field.label}不能小于 ${field.minValue}`;
      } else if (field.maxValue !== undefined && numberValue > field.maxValue) {
        errors[field.key] = `${field.label}不能大于 ${field.maxValue}`;
      }
    }
    if (
      field.type === 'image-upload' &&
      Array.isArray(value) &&
      value.length > (field.maxCount ?? 1)
    ) {
      errors[field.key] = `${field.label}最多上传 ${field.maxCount ?? 1} 张`;
    }
  }
  processingFieldErrors.value = errors;
  return Object.keys(errors).length === 0;
}

function processingUploadRequest(
  field: DynamicFormField,
): NonNullable<UploadProps['customRequest']> {
  return async (options) => {
    const file = options.file as File;
    const processingRecordId = String(processingRecord.value?.id ?? '');
    const maxSizeMb = field.maxFileSizeMb ?? 3;
    if (!file.type.startsWith('image/')) {
      const error = new Error('只能上传图片文件');
      processingFieldErrors.value[field.key] = error.message;
      options.onError?.(error);
      return;
    }
    if (file.size > maxSizeMb * 1024 * 1024) {
      const error = new Error(`单张图片不能超过 ${maxSizeMb}MB`);
      processingFieldErrors.value[field.key] = error.message;
      options.onError?.(error);
      return;
    }
    if (processingUploadCount(field.key) >= (field.maxCount ?? 1)) {
      const error = new Error(
        `${field.label}最多上传 ${field.maxCount ?? 1} 张`,
      );
      processingFieldErrors.value[field.key] = error.message;
      options.onError?.(error);
      return;
    }

    const temporaryUid = `${field.key}-${Date.now()}-${file.name}`;
    const previewUrl = URL.createObjectURL(file);
    processingUploadFiles.value[field.key] = [
      ...(processingUploadFiles.value[field.key] ?? []),
      {
        name: file.name,
        status: 'uploading',
        thumbUrl: previewUrl,
        uid: temporaryUid,
      },
    ];
    processingUploadingFields.value = new Set([
      field.key,
      ...processingUploadingFields.value,
    ]);

    try {
      const uploaded = await uploadTaskFileApi(file);
      const isCurrentProcessingRecord =
        String(processingRecord.value?.id ?? '') === processingRecordId;
      const hasPendingPreview = (
        processingUploadFiles.value[field.key] ?? []
      ).some((item) => item.uid === temporaryUid);
      if (!isCurrentProcessingRecord || !hasPendingPreview) {
        URL.revokeObjectURL(previewUrl);
        return;
      }

      const fileId = String(uploaded.id);
      const fieldValue = processingActionData.value[field.key];
      const currentIds = Array.isArray(fieldValue)
        ? fieldValue.map(String)
        : [];
      processingActionData.value[field.key] = [...currentIds, fileId];
      processingUploadFiles.value[field.key] = (
        processingUploadFiles.value[field.key] ?? []
      ).map((item) =>
        item.uid === temporaryUid
          ? {
              ...item,
              name: uploaded.originalName || file.name,
              response: uploaded,
              status: 'done',
              uid: fileId,
            }
          : item,
      );
      clearProcessingFieldError(field.key);
      options.onSuccess?.(uploaded);
    } catch (error) {
      if (String(processingRecord.value?.id ?? '') === processingRecordId) {
        processingUploadFiles.value[field.key] = (
          processingUploadFiles.value[field.key] ?? []
        ).filter((item) => item.uid !== temporaryUid);
        processingFieldErrors.value[field.key] =
          error instanceof Error && error.message
            ? `图片上传失败：${error.message}，请重试`
            : '图片上传失败，请检查网络后重试';
      }
      URL.revokeObjectURL(previewUrl);
      options.onError?.(error as Error);
    } finally {
      const nextUploadingFields = new Set(processingUploadingFields.value);
      nextUploadingFields.delete(field.key);
      processingUploadingFields.value = nextUploadingFields;
    }
  };
}

function removeProcessingUpload(field: DynamicFormField, file: UploadFile) {
  if (file.status === 'uploading') return false;
  const ids = Array.isArray(processingActionData.value[field.key])
    ? (processingActionData.value[field.key] as string[])
    : [];
  processingActionData.value[field.key] = ids.filter(
    (id) => id !== String(file.uid),
  );
  processingUploadFiles.value[field.key] = (
    processingUploadFiles.value[field.key] ?? []
  ).filter((item) => item.uid !== file.uid);
  releaseProcessingUploadUrl(file);
  clearProcessingFieldError(field.key);
  return true;
}

function processingRemark(record: ResourceApplication) {
  const processingResult = processingActionData.value.processingResult;
  if (
    record.platform === 'ACCOUNT_OPERATION' &&
    typeof processingResult === 'string'
  ) {
    return processingResult.trim();
  }

  const openedAccountIds = processingActionData.value.openedAccountIds;
  if (
    record.platform === 'ACCOUNT_OPENING' &&
    typeof openedAccountIds === 'string'
  ) {
    const normalizedIds = openedAccountIds
      .replaceAll('；', ';')
      .split(/[;\n\r]+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .join(';');
    return `已开户广告账户：${normalizedIds}`;
  }

  return processingForm.remark.trim();
}

async function submitProcessing() {
  const record = processingRecord.value;
  if (!record) return;

  const remark = processingRemark(record);
  if (needsStandaloneProcessingRemark.value && !remark) {
    processingError.value = '请填写办理说明';
    return;
  }
  if (!canProcess(record)) {
    message.warning('办理人或申请状态已变化，请刷新后重试');
    return;
  }
  if (!validateProcessingActionData()) return;
  if (
    requiresAssetSelection.value &&
    selectedAssetIds.value.length !== expectedAssetQuantity.value
  ) {
    assetSelectionError.value = `请选择 ${expectedAssetQuantity.value} 个资产`;
    return;
  }
  if (requiresAssetSelection.value) {
    const applicationChannelId = assetChannelId(record);
    const selectedAssets = availableAssets.value.filter((asset) =>
      selectedAssetIds.value.includes(String(asset.id)),
    );
    const hasCrossChannelAsset = selectedAssets.some(
      (asset) =>
        Boolean(applicationChannelId) &&
        String(asset.channelId || asset.projectId) !== applicationChannelId,
    );
    if (
      selectedAssets.length !== selectedAssetIds.value.length ||
      hasCrossChannelAsset
    ) {
      assetSelectionError.value = applicationChannelId
        ? '所选资产不属于申请渠道，请刷新后重新选择'
        : '所选资产与申请的社交资产类型不匹配，请刷新后重新选择';
      return;
    }
  }
  processingSubmitting.value = true;
  try {
    await assetFlowApi.complete(
      String(record.id),
      remark,
      selectedAssetIds.value,
      processingActionData.value,
    );
    processingRecord.value = undefined;
    processingForm.remark = '';
    processingActionData.value = {};
    resetProcessingUploads();
    processingFieldErrors.value = {};
    processingError.value = '';
    availableAssets.value = [];
    selectedAssetIds.value = [];
    assetSelectionError.value = '';
    await refreshApprovalWorkspace();
    message.success('申请已处理，办理结果已保存');
  } finally {
    processingSubmitting.value = false;
  }
}

async function submitProcessingRejection() {
  const record = processingRejectionRecord.value;
  const reason = processingRejectionForm.reason.trim();
  if (!record) return;
  if (!reason) {
    processingRejectionError.value = '请填写拒绝原因';
    return;
  }
  if (!canProcess(record)) {
    message.warning('办理人或申请状态已变化，请刷新后重试');
    return;
  }

  processingRejectionSubmitting.value = true;
  try {
    const result = await assetFlowApi.reject(String(record.id), reason);
    const mappedResult = mapBackendApplication(result, {
      action: 'rejected',
      remark: reason,
    });
    backendApplicationRecords.value = [
      mappedResult,
      ...backendApplicationRecords.value.filter(
        (item) => String(item.id) !== String(record.id),
      ),
    ];
    processingRejectionRecord.value = undefined;
    processingRejectionForm.reason = '';
    processingRejectionError.value = '';
    await refreshApprovalWorkspace();
    message.success('申请已拒绝，拒绝原因已写入办理记录');
  } finally {
    processingRejectionSubmitting.value = false;
  }
}

onBeforeUnmount(() => {
  resetProcessingUploads();
  approvalListAbortController?.abort();
  approvalDetailAbortController?.abort();
  if (keywordDebounceTimer) clearTimeout(keywordDebounceTimer);
});

async function submitDecision() {
  const record = decisionRecord.value;
  const remark = decisionForm.remark.trim();
  if (!record) return;
  if (decisionAction.value === 'rejected' && !remark) {
    decisionError.value = '请填写拒绝原因';
    return;
  }
  decisionSubmitting.value = true;
  try {
    await new Promise((resolve) => setTimeout(resolve, 250));
    const action =
      decisionAction.value === 'approved'
        ? ('approve' as const)
        : ('reject' as const);
    if (!canHandle(record, action)) {
      message.warning('当前审批节点或权限已变化，请刷新后重试');
      return;
    }
    if (/^\d+$/.test(String(record.id))) {
      const backendResult =
        action === 'approve'
          ? await assetFlowApi.approve(String(record.id), remark)
          : await assetFlowApi.reject(String(record.id), remark);
      decisionRecord.value = undefined;
      decisionForm.remark = '';
      decisionError.value = '';
      availableAssets.value = [];
      selectedAssetIds.value = [];
      assetSelectionError.value = '';
      await refreshApprovalWorkspace();
      let successMessage = '申请已拒绝，拒绝原因已写入审批记录';
      if (action === 'approve') {
        successMessage =
          backendResult.status === 'PROCESSING'
            ? `全部审批节点已通过，已转交${backendResult.handlerName}办理`
            : '当前节点已通过，申请已流转到下一审批节点';
      }
      message.success(successMessage);
      return;
    }
    const input = {
      actor: {
        id: currentIdentity.value.id,
        name: currentIdentity.value.name,
        role: currentIdentity.value.roleLabel,
      },
      remark,
    };
    const decided =
      action === 'approve'
        ? applicationService.approve(record.id, input)
        : applicationService.reject(record.id, input);
    let handoffCreated = false;
    if (action === 'approve' && decided.status === 'approved') {
      const actorId = input.actor.id?.trim();
      if (actorId) {
        try {
          const handoff = applicationResourceBridge.handoffAfterApproval(
            record.id,
            { id: actorId, name: input.actor.name },
          );
          handoffCreated = handoff.kind === 'created';
        } catch (error) {
          message.warning(
            `业务审批已通过，但资源交接待补偿：${error instanceof Error ? error.message : '请稍后重试'}`,
          );
        }
      } else {
        message.warning('业务审批已通过，但审批人缺少稳定 ID，资源交接待补偿');
      }
    }
    decisionRecord.value = undefined;
    decisionForm.remark = '';
    decisionError.value = '';
    let successMessage = remark
      ? '审批已通过，节点备注已写入审批记录'
      : '审批已通过，流程已流转';
    if (decisionAction.value === 'rejected') {
      successMessage = '申请已拒绝，拒绝原因已写入审批记录';
    } else if (handoffCreated) {
      successMessage = '业务审批已通过，已转入媒介资源选户队列';
    }
    message.success(successMessage);
  } finally {
    decisionSubmitting.value = false;
  }
}
</script>

<template>
  <Page
    auto-content-height
    class="bg-muted/40"
    content-class="flex h-full min-h-0 flex-col p-4"
  >
    <div
      v-if="approvalWorkspaceEnabled"
      class="border-border bg-card flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden rounded-[var(--adpulse-radius)] border"
    >
      <header
        class="border-border flex shrink-0 items-center justify-between border-b px-4 py-3"
      >
        <div class="flex min-w-0 items-center gap-3">
          <span
            class="bg-muted text-foreground flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-lg"
          >
            <IconifyIcon icon="lucide:clipboard-check" />
          </span>
          <div class="min-w-0">
            <h1 class="text-foreground m-0 truncate text-lg font-semibold">
              审批中心
            </h1>
            <p
              class="text-muted-foreground mb-0 mt-0.5 hidden text-xs sm:block"
            >
              集中处理资源审批，记录全程可追溯。
            </p>
          </div>
        </div>
        <Select
          v-if="demoMode"
          v-model:value="activeDemoProfile"
          :options="demoProfileOptions"
          aria-label="演示审批身份"
          class="w-[190px] sm:w-[230px]"
        />
        <div
          v-else
          class="bg-muted text-foreground rounded-md px-3 py-2 text-sm font-medium"
        >
          {{ currentIdentity.name }} · {{ currentIdentity.roleLabel }}
        </div>
      </header>

      <div
        class="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[200px_minmax(290px,0.8fr)_minmax(380px,1.25fr)]"
      >
        <aside
          class="border-border bg-card border-b p-3 xl:border-b-0 xl:border-r xl:p-4"
        >
          <Input
            v-model:value="keyword"
            allow-clear
            placeholder="搜索申请单、所属部门、申请人"
          >
            <template #prefix>
              <IconifyIcon icon="lucide:search" class="text-muted-foreground" />
            </template>
          </Input>
          <nav
            aria-label="审批队列"
            class="mt-4 grid grid-cols-2 gap-2 xl:grid-cols-1"
          >
            <button
              v-for="item in summaryCards"
              :key="item.queue"
              :aria-pressed="activeQueue === item.queue"
              type="button"
              class="focus-visible:ring-ring flex cursor-pointer items-center gap-3 rounded-md px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2"
              :class="
                activeQueue === item.queue
                  ? 'bg-accent text-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              "
              @click="selectQueue(item.queue)"
            >
              <span
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                :class="item.tone"
              >
                <IconifyIcon :icon="item.icon" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-medium">{{ item.label }}</span>
                <span class="block text-xs opacity-70">
                  {{ item.value }} 条申请
                </span>
              </span>
            </button>
          </nav>
        </aside>

        <section
          class="border-border bg-muted/40 flex min-h-0 flex-col border-b xl:border-b-0 xl:border-r"
        >
          <div class="border-border bg-card shrink-0 border-b p-4">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h2 class="text-foreground m-0 text-base font-semibold">
                  {{ queueTitle }}
                </h2>
                <p class="text-muted-foreground mb-0 mt-1 text-xs">
                  {{ queueDescription }}
                </p>
              </div>
              <span
                class="bg-muted text-muted-foreground shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-xs"
              >
                {{ demoMode ? filteredApplications.length : approvalTotal }} 条
              </span>
            </div>
            <div class="mt-3">
              <div class="flex items-center justify-end gap-2">
                <button
                  :aria-expanded="filtersExpanded"
                  aria-controls="approval-filter-panel"
                  type="button"
                  class="focus-visible:ring-ring text-muted-foreground hover:bg-muted hover:text-foreground flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2"
                  @click="filtersExpanded = !filtersExpanded"
                >
                  筛选
                  <IconifyIcon
                    :icon="
                      filtersExpanded
                        ? 'lucide:chevron-up'
                        : 'lucide:chevron-down'
                    "
                  />
                </button>
                <button
                  v-if="!demoMode"
                  :aria-expanded="batchOperationsExpanded"
                  aria-controls="approval-batch-actions"
                  type="button"
                  class="focus-visible:ring-ring text-muted-foreground hover:bg-muted hover:text-foreground flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2"
                  @click="batchOperationsExpanded = !batchOperationsExpanded"
                >
                  批量操作
                  <IconifyIcon
                    :icon="
                      batchOperationsExpanded
                        ? 'lucide:chevron-up'
                        : 'lucide:chevron-down'
                    "
                  />
                </button>
              </div>
              <div
                v-show="filtersExpanded"
                id="approval-filter-panel"
                class="mt-2 grid grid-cols-1 gap-2"
              >
                <Select
                  v-model:value="typeFilter"
                  aria-label="申请类型"
                  :options="typeOptions"
                  not-found-content="未找到申请类型"
                  option-filter-prop="label"
                  show-search
                />
                <Select
                  v-model:value="departmentFilter"
                  aria-label="所属部门"
                  :loading="departmentOptionsLoading"
                  :options="departmentOptions"
                  not-found-content="未找到所属部门"
                  option-filter-prop="label"
                  show-search
                />
                <Select
                  v-model:value="requesterFilter"
                  aria-label="申请人"
                  :options="requesterOptions"
                  not-found-content="未找到申请人"
                  option-filter-prop="label"
                  show-search
                />
                <Select
                  v-if="activeQueue === 'processed'"
                  v-model:value="decisionResultFilter"
                  aria-label="审批结果"
                  :options="decisionResultOptions"
                />
              </div>
              <div
                v-if="!demoMode"
                v-show="batchOperationsExpanded"
                id="approval-batch-actions"
                class="mt-2 flex flex-wrap items-center justify-between gap-2"
              >
                <div class="flex flex-wrap items-center gap-3">
                  <Checkbox
                    :aria-label="`选择当前页可操作审批申请，最多 ${BATCH_DECISION_LIMIT} 条`"
                    :checked="areAllLoadedBatchRecordsSelected"
                    :disabled="selectableLoadedBatchRecords.length === 0"
                    :indeterminate="areSomeLoadedBatchRecordsSelected"
                    @update:checked="
                      (checked) => toggleLoadedBatchSelection(Boolean(checked))
                    "
                  >
                    选择当前页（最多 {{ BATCH_DECISION_LIMIT }} 条）
                  </Checkbox>
                  <span
                    class="text-muted-foreground text-xs"
                    aria-live="polite"
                  >
                    已选择 {{ selectedOperationRecords.length }} 条
                  </span>
                </div>
                <div class="flex gap-2">
                  <Button
                    :loading="approvalExporting"
                    :disabled="selectedOperationRecords.length === 0"
                    @click="exportSelectedApprovals"
                  >
                    批量导出
                  </Button>
                  <Button
                    v-if="activeQueue === 'pending'"
                    danger
                    :disabled="selectedBatchRecords.length === 0"
                    @click="openBatchDecision('rejected')"
                  >
                    批量拒绝
                  </Button>
                  <Button
                    v-if="activeQueue === 'pending'"
                    type="primary"
                    :disabled="selectedBatchRecords.length === 0"
                    @click="openBatchDecision('approved')"
                  >
                    批量通过
                  </Button>
                </div>
              </div>
            </div>
          </div>
          <ListLoading v-if="approvalListLoading" fill />
          <div
            v-else
            ref="applicationListRef"
            :aria-busy="approvalListLoading"
            aria-label="审批申请列表"
            class="min-h-0 flex-1 space-y-2 overflow-y-auto p-3"
            tabindex="0"
          >
            <div
              v-for="record in paginatedApplications"
              :key="record.id"
              class="relative"
            >
              <Checkbox
                v-if="
                  batchOperationsExpanded && canSelectForBatchOperation(record)
                "
                :aria-label="`选择 ${record.title}`"
                :checked="selectedApprovalIds.includes(record.id)"
                class="absolute left-2 top-2 z-10 flex h-8 items-center"
                @click.stop
                @update:checked="
                  (checked) => toggleBatchSelection(record, Boolean(checked))
                "
              />
              <button
                type="button"
                class="focus-visible:ring-ring w-full rounded-[var(--adpulse-radius)] border p-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2"
                :class="[
                  selectedRecordSummary?.id === record.id
                    ? 'border-border bg-accent text-foreground'
                    : 'border-border bg-card hover:bg-muted',
                  batchOperationsExpanded && canSelectForBatchOperation(record)
                    ? 'pl-11'
                    : '',
                ]"
                @click="selectRecord(record)"
              >
                <span class="flex min-w-0 items-center gap-2">
                  <span
                    class="text-foreground min-w-0 flex-1 truncate text-sm font-semibold"
                  >
                    {{ record.title }}
                  </span>
                  <Tag
                    :color="statusMeta[record.status].color"
                    class="m-0 shrink-0"
                  >
                    {{ statusMeta[record.status].label }}
                  </Tag>
                </span>
                <span
                  class="text-muted-foreground mt-1 block truncate text-xs"
                  :title="approvalListMeta(record)"
                >
                  {{ approvalListMeta(record) }}
                </span>
              </button>
            </div>
            <div
              v-if="approvalListError"
              role="alert"
              class="border-border bg-card flex items-center justify-between gap-3 rounded-[var(--adpulse-radius)] border p-3 text-sm"
            >
              <span class="text-muted-foreground">{{ approvalListError }}</span>
              <Button @click="loadApprovalList(approvalPage)"> 重试 </Button>
            </div>
            <div
              v-if="
                !approvalListLoading &&
                !approvalListError &&
                filteredApplications.length === 0
              "
              class="border-border bg-card flex min-h-48 flex-col items-center justify-center rounded-[var(--adpulse-radius)] border border-dashed p-6 text-center"
            >
              <IconifyIcon
                icon="lucide:inbox"
                class="text-muted-foreground text-2xl"
              />
              <p class="text-muted-foreground mb-0 mt-3 text-sm">
                当前队列暂无申请事项
              </p>
            </div>
          </div>
          <div
            v-if="approvalPaginationTotal > 0"
            class="border-border bg-card flex shrink-0 flex-nowrap items-center justify-between gap-1 border-t px-2 py-2"
          >
            <span
              class="text-muted-foreground shrink-0 whitespace-nowrap text-xs"
              role="status"
            >
              共 {{ approvalPaginationTotal }} 条
            </span>
            <Pagination
              :current="approvalPage"
              :disabled="approvalListLoading"
              :page-size="approvalPageSize"
              :page-size-options="APPLICATION_LIST_PAGE_SIZE_OPTIONS"
              :total="approvalPaginationTotal"
              class="shrink-0 whitespace-nowrap"
              show-less-items
              show-size-changer
              @change="changeApprovalPage"
            />
          </div>
        </section>

        <section
          :aria-busy="approvalDetailLoading"
          class="bg-card flex min-h-0 flex-col"
        >
          <div class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
            <ListLoading v-if="approvalDetailLoading" fill />
            <div
              v-else-if="approvalDetailError && selectedRecordSummary"
              role="alert"
              class="flex h-full min-h-80 flex-col items-center justify-center gap-3 text-center"
            >
              <p class="text-muted-foreground m-0 text-sm">
                {{ approvalDetailError }}
              </p>
              <Button @click="loadApplicationDetail(selectedRecordSummary.id)">
                重新加载
              </Button>
            </div>
            <template v-else-if="selectedRecord">
              <div class="border-border border-b pb-4">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <Tag
                      :color="typeMeta[selectedRecord.type].color"
                      class="m-0"
                    >
                      {{ typeMeta[selectedRecord.type].label }}
                    </Tag>
                    <Tag
                      :color="statusMeta[selectedRecord.status].color"
                      class="m-0"
                    >
                      {{ statusMeta[selectedRecord.status].label }}
                    </Tag>
                  </div>
                  <h2 class="text-foreground mb-0 mt-3 text-lg font-semibold">
                    {{ selectedRecord.title }}
                  </h2>
                  <p
                    class="text-muted-foreground mb-0 mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
                  >
                    <span class="break-all"
                      >申请单 ID：{{ selectedRecord.id }}</span
                    >
                    <span
                      >所属部门：{{
                        getApprovalDepartmentLabel(selectedRecord)
                      }}</span
                    >
                    <span
                      >申请人：{{
                        selectedRecord.requesterName || selectedRecord.requester
                      }}</span
                    >
                    <span>
                      申请时间：{{
                        formatApplicationDateTime(selectedRecord.createdAt)
                      }}
                    </span>
                  </p>
                </div>
              </div>

              <section
                aria-labelledby="selected-application-info-heading"
                class="border-border mt-5 rounded-[var(--adpulse-radius)] border p-4"
              >
                <h3
                  id="selected-application-info-heading"
                  class="text-foreground m-0 text-sm font-semibold"
                >
                  申请信息
                </h3>
                <div
                  v-if="applicationFormFields(selectedRecord).length > 0"
                  class="mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2"
                >
                  <template
                    v-for="field in applicationFormFields(selectedRecord)"
                    :key="field.key"
                  >
                    <section
                      v-if="field.type === 'section'"
                      class="bg-muted rounded-md px-3 py-2 sm:col-span-2"
                    >
                      <h4 class="m-0 text-sm font-semibold text-slate-700">
                        {{ field.label }}
                      </h4>
                      <p
                        v-if="field.helpText"
                        class="mb-0 mt-1 text-xs text-slate-500"
                      >
                        {{ field.helpText }}
                      </p>
                    </section>
                    <dl
                      v-else
                      class="bg-muted/60 mb-0 rounded-md p-3"
                      :class="field.width === 'full' ? 'sm:col-span-2' : ''"
                    >
                      <dt class="text-xs text-slate-500">
                        {{ field.label }}
                      </dt>
                      <dd
                        v-if="field.type === 'pixel-selector'"
                        class="mb-0 mt-2 flex flex-wrap items-center gap-1.5"
                      >
                        <template
                          v-if="
                            applicationFormTagValues(selectedRecord, field)
                              .length > 0
                          "
                        >
                          <Tag
                            v-for="(item, index) in visibleApplicationFormTags(
                              selectedRecord,
                              field,
                            )"
                            :key="`${field.key}-${item.key}-${index}`"
                            class="!m-0 max-w-full !whitespace-normal"
                          >
                            <span class="break-all">{{ item.label }}</span>
                          </Tag>
                          <Button
                            v-if="
                              applicationFormTagValues(selectedRecord, field)
                                .length > APPLICATION_FORM_TAG_LIMIT
                            "
                            :aria-expanded="
                              isApplicationFormFieldExpanded(
                                selectedRecord,
                                field,
                              )
                            "
                            size="small"
                            type="link"
                            @click="
                              toggleApplicationFormField(selectedRecord, field)
                            "
                          >
                            {{
                              isApplicationFormFieldExpanded(
                                selectedRecord,
                                field,
                              )
                                ? '收起'
                                : `展开其余 ${
                                    applicationFormTagValues(
                                      selectedRecord,
                                      field,
                                    ).length - APPLICATION_FORM_TAG_LIMIT
                                  } 个`
                            }}
                          </Button>
                        </template>
                        <span v-else class="font-medium text-slate-800">-</span>
                      </dd>
                      <dd
                        v-else
                        class="mb-0 mt-1 whitespace-pre-wrap break-words font-medium leading-6 text-slate-800"
                      >
                        {{ applicationFormValue(selectedRecord, field) }}
                      </dd>
                    </dl>
                  </template>
                </div>
                <dl
                  v-else
                  class="mb-0 mt-3 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2"
                >
                  <div class="rounded-lg bg-slate-50 p-3">
                    <dt class="text-xs text-slate-500">资源要求</dt>
                    <dd class="mb-0 mt-1 font-medium text-slate-800">
                      {{ requestDetail(selectedRecord) }}
                    </dd>
                  </div>
                </dl>
              </section>

              <ApplicationWorkflowTimeline
                class="mt-5"
                :application="selectedRecord"
              />

              <ApplicationProcessingDetails
                class="mt-5"
                :application="selectedRecord"
              />

              <div class="mt-5 space-y-5 border-t border-slate-100 pt-5">
                <ApplicationCollaborationPanel
                  :actor-name="currentIdentity.name"
                  :actor-role="currentIdentity.roleLabel"
                  :allow-comment="canCommentOnApplication(selectedRecord)"
                  :application="selectedRecord"
                  :submit-comment-request="commentSubmitRequest(selectedRecord)"
                  @comment-added="addLocalComment(selectedRecord, $event)"
                />
              </div>
            </template>
            <div
              v-else
              class="flex h-full min-h-80 flex-col items-center justify-center text-center"
            >
              <IconifyIcon
                icon="lucide:clipboard-list"
                class="text-2xl text-slate-400"
              />
              <p class="mb-0 mt-3 text-sm text-slate-500">
                选择一项申请查看详情
              </p>
            </div>
          </div>
          <div
            v-if="selectedRecord"
            class="border-border bg-card shrink-0 border-t px-4 py-3"
          >
            <div class="flex flex-wrap items-center justify-end gap-2">
              <Button
                v-if="canProcess(selectedRecord)"
                @click="openHandlePage(selectedRecord)"
              >
                办理
              </Button>
              <Button
                v-if="canProcess(selectedRecord)"
                danger
                @click="openProcessingRejection(selectedRecord)"
              >
                拒绝办理
              </Button>
              <Button
                v-if="
                  selectedRecord.status === 'pending' &&
                  canHandle(selectedRecord, 'reject')
                "
                danger
                class="!text-red-600"
                @click="openReject(selectedRecord)"
              >
                拒绝
              </Button>
              <Button
                v-if="canTransfer(selectedRecord)"
                @click="openTransfer(selectedRecord)"
              >
                转交
              </Button>
              <Button
                v-if="
                  selectedRecord.status === 'pending' &&
                  canHandle(selectedRecord, 'approve')
                "
                type="primary"
                @click="approve(selectedRecord)"
              >
                通过
              </Button>
              <Button
                v-if="canResubmit(selectedRecord)"
                type="primary"
                @click="openResubmit(selectedRecord)"
              >
                <IconifyIcon icon="lucide:rotate-ccw" />
                重新提交
              </Button>
            </div>
          </div>
        </section>
      </div>
    </div>

    <div v-else class="w-full min-w-0 space-y-4">
      <BusinessPageHeader
        description="集中处理资源申请，审批决定与理由全程留痕。"
        icon="lucide:clipboard-check"
        title="审批中心"
      >
        <template #extra>
          <div class="flex flex-col items-stretch gap-1.5 sm:items-end">
            <label
              v-if="demoMode"
              for="demo-approver-profile"
              class="text-xs font-medium text-slate-500"
            >
              演示审批身份
            </label>
            <Select
              v-if="demoMode"
              id="demo-approver-profile"
              v-model:value="activeDemoProfile"
              :options="demoProfileOptions"
              class="w-full sm:w-[230px]"
            />
            <div
              v-else
              class="flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-2"
            >
              <IconifyIcon icon="lucide:user-check" class="text-blue-600" />
              <span class="text-sm font-medium text-slate-700">
                {{ currentIdentity.name }}
              </span>
            </div>
          </div>
        </template>
      </BusinessPageHeader>

      <section
        aria-label="审批统计"
        class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5"
      >
        <button
          v-for="item in summaryCards"
          :key="item.queue"
          :aria-pressed="activeQueue === item.queue"
          type="button"
          class="relative flex min-h-24 items-center gap-4 overflow-hidden rounded-xl border bg-white p-4 text-left shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          :class="
            activeQueue === item.queue
              ? 'border-blue-500 bg-blue-50/80 shadow-md ring-2 ring-blue-100'
              : 'border-slate-200 hover:border-blue-200 hover:shadow-md'
          "
          @click="selectQueue(item.queue)"
        >
          <span
            v-if="activeQueue === item.queue"
            aria-hidden="true"
            class="absolute inset-x-0 top-0 h-1 bg-blue-600"
          ></span>
          <span
            v-if="activeQueue === item.queue"
            class="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-blue-600 px-2 py-0.5 text-xs font-semibold text-white"
          >
            <IconifyIcon
              aria-hidden="true"
              class="h-3.5 w-3.5"
              icon="lucide:check"
            />
            当前
          </span>
          <span
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-xl"
            :class="item.tone"
          >
            <IconifyIcon :icon="item.icon" aria-hidden="true" />
          </span>
          <span class="min-w-0">
            <span class="block text-2xl font-semibold text-slate-900">{{
              item.value
            }}</span>
            <span
              class="mt-0.5 block text-sm"
              :class="
                activeQueue === item.queue
                  ? 'font-semibold text-blue-700'
                  : 'text-slate-500'
              "
            >
              {{ item.label }}
            </span>
          </span>
        </button>
      </section>

      <Card :body-style="{ padding: 0 }" class="overflow-hidden">
        <div class="border-b border-slate-100 p-4 sm:p-5">
          <div
            class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"
          >
            <div>
              <h2 class="m-0 text-lg font-semibold text-slate-900">
                {{ queueTitle }}
              </h2>
              <p class="mb-0 mt-1 text-sm text-slate-500">
                {{ queueDescription }}
              </p>
            </div>
            <Segmented
              v-model:value="activeQueue"
              :options="queueOptions"
              class="max-w-full overflow-hidden"
            />
          </div>

          <div
            class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2"
            :class="
              activeQueue === 'processed' ? 'xl:grid-cols-5' : 'xl:grid-cols-4'
            "
          >
            <Input
              v-model:value="keyword"
              allow-clear
              class="w-full"
              placeholder="搜索申请单、归属、申请人"
            >
              <template #prefix>
                <IconifyIcon icon="lucide:search" class="text-slate-400" />
              </template>
            </Input>
            <Select
              v-model:value="typeFilter"
              aria-label="申请类型"
              :options="typeOptions"
              class="w-full"
              not-found-content="未找到申请类型"
              option-filter-prop="label"
              show-search
            />
            <Select
              v-model:value="departmentFilter"
              aria-label="所属部门"
              :loading="departmentOptionsLoading"
              :options="departmentOptions"
              class="w-full"
              not-found-content="未找到所属部门"
              option-filter-prop="label"
              placeholder="所属部门"
              show-search
            />
            <Select
              v-model:value="requesterFilter"
              aria-label="申请人"
              :options="requesterOptions"
              class="w-full"
              not-found-content="未找到申请人"
              option-filter-prop="label"
              placeholder="申请人"
              show-search
            />
            <Select
              v-if="activeQueue === 'processed'"
              v-model:value="decisionResultFilter"
              aria-label="审批结果"
              :options="decisionResultOptions"
              class="w-full"
            />
          </div>
        </div>

        <div
          v-if="activeQueue === 'pending'"
          class="flex flex-col gap-2 border-b border-slate-100 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5"
        >
          <span class="text-sm text-slate-600" aria-live="polite">
            已选择 {{ selectedBatchRecords.length }} 条可批量审批申请
          </span>
          <div class="flex flex-wrap gap-2">
            <Button
              danger
              :disabled="selectedBatchRecords.length === 0"
              @click="openBatchDecision('rejected')"
            >
              批量拒绝
            </Button>
            <Button
              type="primary"
              :disabled="selectedBatchRecords.length === 0"
              @click="openBatchDecision('approved')"
            >
              批量通过
            </Button>
          </div>
        </div>

        <ListLoading v-if="approvalListLoading" />
        <div
          v-show="!approvalListLoading"
          class="hidden xl:block"
          :aria-busy="approvalListLoading"
        >
          <Table
            :columns="columns"
            :data-source="filteredApplications"
            :row-key="(record) => record.id"
            :row-selection="
              activeQueue === 'pending' ? approvalRowSelection : undefined
            "
            :pagination="{ pageSize: 8, showSizeChanger: false }"
            class=""
            table-layout="fixed"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'application'">
                <div class="flex min-w-0 items-start gap-2.5">
                  <span
                    class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600"
                  >
                    <IconifyIcon
                      :icon="typeMeta[record.type as ApplicationType].icon"
                    />
                  </span>
                  <div class="min-w-0">
                    <div class="line-clamp-2 font-medium text-slate-800">
                      {{ record.title }}
                    </div>
                    <div class="mt-1 flex flex-wrap items-center gap-1.5">
                      <Tag
                        :color="typeMeta[record.type as ApplicationType].color"
                        class="m-0"
                      >
                        {{ typeMeta[record.type as ApplicationType].label }}
                      </Tag>
                      <span class="break-all text-xs text-slate-500">{{
                        record.id
                      }}</span>
                    </div>
                  </div>
                </div>
              </template>

              <template v-else-if="column.key === 'ownership'">
                <div class="line-clamp-2 text-sm text-slate-700">
                  {{ record.project }}
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  所属部门：{{
                    getApprovalDepartmentLabel(toApplication(record))
                  }}
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  申请人：{{ record.requesterName || record.requester }} ·
                  {{ requestDetail(record) }}
                </div>
              </template>

              <template v-else-if="column.key === 'approval'">
                <div class="flex flex-wrap items-center gap-1.5">
                  <Tag
                    :color="
                      statusMeta[record.status as ApplicationStatus].color
                    "
                    class="m-0"
                  >
                    {{ statusMeta[record.status as ApplicationStatus].label }}
                  </Tag>
                  <Tag :color="approvalRoleInfo(record).color" class="m-0">
                    {{ approvalRoleInfo(record).label }}
                  </Tag>
                </div>
                <div class="mt-1 text-xs leading-5 text-slate-500">
                  {{ record.approver }} ·
                  {{ formatApplicationDateTime(record.createdAt) }}
                </div>
                <div
                  v-if="lastDecision(record)"
                  class="mt-0.5 line-clamp-1 text-xs text-slate-400"
                >
                  {{ lastDecision(record)?.actor }}：{{
                    lastDecision(record)?.remark
                  }}
                </div>
              </template>

              <template v-else-if="column.key === 'actions'">
                <div class="flex flex-wrap items-center gap-x-1">
                  <Button type="link" @click="openHandlePage(record)">
                    {{ applicationActionLabel(record, '详情') }}
                  </Button>
                  <Button
                    v-if="canResubmit(record)"
                    type="link"
                    @click="openResubmit(record)"
                  >
                    重新提交
                  </Button>
                </div>
              </template>
            </template>
          </Table>
        </div>

        <div
          v-show="!approvalListLoading"
          class="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 xl:hidden"
          :aria-busy="approvalListLoading"
        >
          <article
            v-for="record in filteredApplications"
            :key="record.id"
            class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex min-w-0 items-start gap-2.5">
                <Checkbox
                  v-if="activeQueue === 'pending' && canBatchDecide(record)"
                  :aria-label="`选择 ${record.title}`"
                  :checked="selectedApprovalIds.includes(record.id)"
                  class="mt-1"
                  @update:checked="
                    (checked) => toggleBatchSelection(record, Boolean(checked))
                  "
                />
                <span
                  class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600"
                >
                  <IconifyIcon :icon="typeMeta[record.type].icon" />
                </span>
                <div class="min-w-0">
                  <h3
                    class="m-0 line-clamp-2 text-sm font-semibold text-slate-900"
                  >
                    {{ record.title }}
                  </h3>
                  <p class="mb-0 mt-1 break-all text-xs text-slate-500">
                    {{ record.id }}
                  </p>
                </div>
              </div>
              <Tag
                :color="statusMeta[record.status].color"
                class="m-0 shrink-0"
              >
                {{ statusMeta[record.status].label }}
              </Tag>
            </div>

            <div class="mt-3 flex flex-wrap gap-2">
              <Tag :color="typeMeta[record.type].color" class="m-0">
                {{ typeMeta[record.type].label }}
              </Tag>
              <Tag
                :color="approvalRoleMeta[record.approvalRole].color"
                class="m-0"
              >
                {{ approvalRoleMeta[record.approvalRole].label }}
              </Tag>
            </div>

            <dl
              class="mb-0 mt-3 grid grid-cols-[70px_minmax(0,1fr)] gap-y-2 text-sm"
            >
              <dt class="text-slate-500">归属</dt>
              <dd class="m-0 break-words text-slate-700">
                {{ record.project }}
              </dd>
              <dt class="text-slate-500">所属部门</dt>
              <dd class="m-0 text-slate-700">
                {{ getApprovalDepartmentLabel(record) }}
              </dd>
              <dt class="text-slate-500">申请人</dt>
              <dd class="m-0 text-slate-700">
                {{ record.requesterName || record.requester }}
              </dd>
              <dt class="text-slate-500">
                {{ record.status === 'processing' ? '办理人' : '审批人' }}
              </dt>
              <dd class="m-0 text-slate-700">{{ record.approver }}</dd>
              <dt class="text-slate-500">申请时间</dt>
              <dd class="m-0 text-slate-700">
                {{ formatApplicationDateTime(record.createdAt) }}
              </dd>
            </dl>

            <div
              class="mt-4 flex items-center justify-end gap-1 border-t border-slate-100 pt-3"
            >
              <Button type="link" @click="openHandlePage(record)">
                {{ applicationActionLabel(record, '查看详情') }}
              </Button>
              <Button
                v-if="canResubmit(record)"
                type="link"
                @click="openResubmit(record)"
              >
                重新提交
              </Button>
            </div>
          </article>

          <div
            v-if="!approvalListLoading && filteredApplications.length === 0"
            class="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-500 sm:col-span-2"
          >
            当前身份下暂无符合条件的申请
          </div>
        </div>
      </Card>
    </div>

    <Modal
      :confirm-loading="batchDecisionSubmitting"
      :ok-button-props="{ danger: batchDecisionAction === 'rejected' }"
      :ok-text="
        batchDecisionAction === 'approved' ? '确认批量通过' : '确认批量拒绝'
      "
      :open="batchDecisionOpen"
      cancel-text="取消"
      :title="
        batchDecisionAction === 'approved' ? '批量通过申请' : '批量拒绝申请'
      "
      wrap-class-name="approval-center-modal"
      @cancel="closeBatchDecision"
      @ok="submitBatchDecision"
    >
      <div>
        <div
          class="mb-4 rounded-lg p-3 text-sm leading-6"
          :class="
            batchDecisionAction === 'approved'
              ? 'bg-blue-50 text-blue-700'
              : 'bg-red-50 text-red-700'
          "
        >
          本次将{{ batchDecisionAction === 'approved' ? '通过' : '拒绝' }}
          {{ selectedBatchRecords.length }}
          条申请。若任一申请状态、权限或库存发生变化，服务端会回滚整批操作。
        </div>
        <label
          for="batch-approval-decision-remark"
          class="mb-2 block text-sm font-medium text-slate-700"
        >
          统一审批备注
          <template v-if="batchDecisionAction === 'rejected'">
            <span class="text-red-500" aria-hidden="true">*</span>
            <span class="sr-only">（必填）</span>
          </template>
          <span v-else class="ml-1 font-normal text-slate-500">（选填）</span>
        </label>
        <Input.TextArea
          id="batch-approval-decision-remark"
          v-model:value="batchDecisionForm.remark"
          :aria-describedby="
            batchDecisionError
              ? 'batch-approval-decision-remark-error'
              : undefined
          "
          :aria-invalid="Boolean(batchDecisionError)"
          :maxlength="300"
          :rows="5"
          :aria-required="batchDecisionAction === 'rejected'"
          :placeholder="
            batchDecisionAction === 'approved'
              ? '可填写统一通过的核验依据或后续交付要求'
              : '请说明统一拒绝的原因或需补充的资料'
          "
          show-count
          @update:value="clearBatchDecisionError"
        />
        <p
          v-if="batchDecisionError"
          id="batch-approval-decision-remark-error"
          class="mb-0 mt-2 text-sm text-red-600"
          role="alert"
        >
          {{ batchDecisionError }}
        </p>
      </div>
    </Modal>

    <Modal
      :confirm-loading="decisionSubmitting"
      :ok-button-props="{ danger: decisionAction === 'rejected' }"
      :ok-text="decisionAction === 'approved' ? '确认通过' : '确认拒绝'"
      :open="Boolean(decisionRecord)"
      cancel-text="取消"
      :title="decisionAction === 'approved' ? '通过申请' : '拒绝申请'"
      wrap-class-name="approval-center-modal"
      @cancel="closeDecision"
      @ok="submitDecision"
    >
      <div v-if="decisionRecord">
        <div
          class="mb-4 rounded-lg p-3 text-sm leading-6"
          :class="
            decisionAction === 'approved'
              ? 'bg-blue-50 text-blue-700'
              : 'bg-red-50 text-red-700'
          "
        >
          <template v-if="decisionAction === 'approved'">
            将通过“{{
              decisionRecord.title
            }}”。若这是最后一个审批节点，申请将转交唯一流程办理人进行资产分配；填写的本节点备注会永久留痕。
          </template>
          <template v-else>
            将拒绝“{{
              decisionRecord.title
            }}”。拒绝原因会同步给申请人并永久留痕。
          </template>
        </div>
        <label
          for="approval-decision-remark"
          class="mb-2 block text-sm font-medium text-slate-700"
        >
          {{ decisionAction === 'rejected' ? '拒绝原因' : '本节点审批备注' }}
          <template v-if="decisionAction === 'rejected'">
            <span class="text-red-500" aria-hidden="true">*</span>
            <span class="sr-only">（必填）</span>
          </template>
        </label>
        <Input.TextArea
          id="approval-decision-remark"
          v-model:value="decisionForm.remark"
          :aria-describedby="
            decisionError ? 'approval-decision-remark-error' : undefined
          "
          :aria-invalid="Boolean(decisionError)"
          :maxlength="300"
          :rows="5"
          :aria-required="decisionAction === 'rejected'"
          :placeholder="
            decisionAction === 'approved'
              ? '请说明核验结论、通过依据或后续交付要求'
              : '请说明缺少的资料、需调整的内容或不通过原因'
          "
          show-count
          @update:value="clearDecisionError"
        />
        <p
          v-if="decisionError"
          id="approval-decision-remark-error"
          class="mb-0 mt-2 text-sm text-red-600"
          role="alert"
        >
          {{ decisionError }}
        </p>
      </div>
    </Modal>

    <Modal
      :confirm-loading="transferSubmitting"
      :ok-button-props="{ disabled: transferCandidatesLoading }"
      ok-text="确认转交"
      :open="Boolean(transferRecord)"
      cancel-text="取消"
      :title="transferRecord?.status === 'processing' ? '转交办理' : '转交审批'"
      wrap-class-name="approval-center-modal"
      @cancel="() => closeTransfer()"
      @ok="submitTransfer"
    >
      <div v-if="transferRecord" class="space-y-4">
        <div
          class="rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-800"
        >
          将“{{ transferRecord.title }}”转交给当前{{
            transferRecord.status === 'processing' ? '办理人' : '审批人'
          }}主部门内的其他同事。转交原因会写入审批流程与记录。
        </div>
        <div>
          <label
            for="approval-transfer-recipient"
            class="mb-2 block text-sm font-medium text-slate-700"
          >
            接收同事 <span class="text-red-500" aria-hidden="true">*</span>
          </label>
          <Select
            id="approval-transfer-recipient"
            v-model:value="transferForm.recipientId"
            :disabled="transferCandidatesLoading"
            :loading="transferCandidatesLoading"
            :options="
              transferCandidates.map((candidate) => ({
                label: `${candidate.name} · ${candidate.departmentName}`,
                value: candidate.id,
              }))
            "
            placeholder="请选择同部门同事"
            class="w-full"
            @update:value="clearTransferError"
          />
        </div>
        <div>
          <label
            for="approval-transfer-remark"
            class="mb-2 block text-sm font-medium text-slate-700"
          >
            转交原因 <span class="text-red-500" aria-hidden="true">*</span>
          </label>
          <Input.TextArea
            id="approval-transfer-remark"
            v-model:value="transferForm.remark"
            :maxlength="300"
            :rows="4"
            placeholder="请说明转交原因"
            show-count
            @update:value="clearTransferError"
          />
        </div>
        <p v-if="transferError" class="mb-0 text-sm text-red-600" role="alert">
          {{ transferError }}
        </p>
      </div>
    </Modal>

    <Modal
      :confirm-loading="processingRejectionSubmitting"
      :ok-button-props="{ danger: true }"
      ok-text="确认拒绝办理"
      :open="Boolean(processingRejectionRecord)"
      cancel-text="取消"
      title="拒绝办理"
      wrap-class-name="approval-center-modal"
      @cancel="closeProcessingRejection"
      @ok="submitProcessingRejection"
    >
      <div v-if="processingRejectionRecord">
        <div
          class="mb-4 rounded-lg bg-red-50 p-3 text-sm leading-6 text-red-700"
        >
          将拒绝办理“{{
            processingRejectionRecord.title
          }}”。拒绝原因会同步给申请人并永久留痕，不会执行资产分配或其他办理操作。
        </div>
        <label
          for="processing-rejection-reason"
          class="mb-2 block text-sm font-medium text-slate-700"
        >
          拒绝原因
          <span class="text-red-500" aria-hidden="true">*</span>
          <span class="sr-only">（必填）</span>
        </label>
        <Input.TextArea
          id="processing-rejection-reason"
          v-model:value="processingRejectionForm.reason"
          :aria-describedby="
            processingRejectionError
              ? 'processing-rejection-reason-error'
              : undefined
          "
          :aria-invalid="Boolean(processingRejectionError)"
          aria-required="true"
          :maxlength="300"
          :rows="4"
          placeholder="请说明无法办理的原因或需要补充的资料"
          show-count
          @update:value="processingRejectionError = ''"
        />
        <p
          v-if="processingRejectionError"
          id="processing-rejection-reason-error"
          class="mb-0 mt-2 text-sm text-red-600"
          role="alert"
        >
          {{ processingRejectionError }}
        </p>
      </div>
    </Modal>

    <Modal
      :confirm-loading="processingSubmitting"
      ok-text="确认办理"
      :open="Boolean(processingRecord)"
      cancel-text="取消"
      title="办理"
      :width="processingRecord?.platform === 'ACCOUNT_OPENING' ? 1200 : 520"
      wrap-class-name="approval-center-modal"
      @cancel="closeProcessing"
      @ok="submitProcessing"
    >
      <div v-if="processingRecord">
        <div
          class="mb-4 rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-800"
        >
          “{{
            processingRecord.title
          }}”已完成全部审批。以下业务操作仅由办理人执行，审批人不会看到或填写这些内容。
        </div>
        <div
          v-for="field in processingFormSchema"
          :key="field.key"
          class="mb-4"
        >
          <label
            :for="
              field.type === 'image-upload' ||
              (processingRecord.platform === 'ACCOUNT_OPENING' &&
                field.key === 'openedAccountIds')
                ? undefined
                : `processing-action-${field.key}`
            "
            class="mb-2 block text-sm font-medium text-slate-700"
          >
            {{ field.label }}
            <span v-if="field.required" class="text-red-500" aria-hidden="true">
              *
            </span>
          </label>
          <AccountOpeningAccountSelector
            v-if="
              processingRecord.platform === 'ACCOUNT_OPENING' &&
              field.key === 'openedAccountIds'
            "
            :application-channel-id="assetChannelId(processingRecord)"
            :application-channel-name="
              String(
                processingRecord.formData?.channelName ??
                  processingRecord.project ??
                  '',
              )
            "
            :application-timezone="
              String(processingRecord.formData?.timezone ?? '')
            "
            :expected-quantity="
              expectedAssetQuantity ||
              Number(
                processingRecord.formData?.quantity ??
                  processingRecord.quantity ??
                  1,
              )
            "
            :model-value="processingTextValue(field.key)"
            @update:model-value="updateProcessingField(field.key, $event)"
          />
          <InputNumber
            v-else-if="field.type === 'number'"
            :id="`processing-action-${field.key}`"
            :value="processingNumberValue(field.key)"
            class="w-full"
            :max="field.maxValue"
            :min="field.minValue"
            :placeholder="field.placeholder || `请输入${field.label}`"
            @update:value="updateProcessingField(field.key, $event)"
          />
          <Input.TextArea
            v-else-if="field.type === 'textarea'"
            :id="`processing-action-${field.key}`"
            :value="processingTextValue(field.key)"
            :maxlength="field.maxLength"
            :placeholder="field.placeholder || `请输入${field.label}`"
            :rows="3"
            @update:value="updateProcessingField(field.key, $event)"
          />
          <div
            v-else-if="field.type === 'image-upload'"
            class="rounded-lg border border-slate-200 bg-slate-50/70 p-3 sm:p-4"
          >
            <div
              class="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs"
            >
              <span class="font-medium text-slate-600">
                已上传 {{ processingUploadCount(field.key) }} /
                {{ field.maxCount || 1 }} 张
              </span>
              <span class="text-slate-500">点击缩略图可放大查看</span>
            </div>

            <div
              v-if="processingUploadCount(field.key) > 0"
              class="mb-3 flex flex-wrap gap-3"
            >
              <article
                v-for="file in processingUploadFiles[field.key] || []"
                :key="file.uid"
                class="relative w-32 overflow-hidden rounded-lg border border-slate-200 bg-white"
              >
                <div
                  class="relative flex h-24 items-center justify-center overflow-hidden bg-slate-100"
                >
                  <Image
                    v-if="file.thumbUrl"
                    :alt="file.name"
                    :height="96"
                    :src="file.thumbUrl"
                    :width="128"
                    class="object-cover"
                  />
                  <IconifyIcon
                    v-else
                    aria-hidden="true"
                    class="text-2xl text-slate-400"
                    icon="lucide:image"
                  />
                  <div
                    v-if="file.status === 'uploading'"
                    class="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-slate-900/55 text-xs text-white"
                    role="status"
                  >
                    <IconifyIcon
                      aria-hidden="true"
                      class="animate-spin text-xl"
                      icon="lucide:loader-circle"
                    />
                    上传中
                  </div>
                  <Tooltip v-else title="移除图片">
                    <Button
                      :aria-label="`移除图片 ${file.name}`"
                      class="!absolute !right-2 !top-2 !z-10 !flex !w-8 !items-center !justify-center !rounded-full !border !border-red-100 !bg-white/95 !p-0 !text-red-500 shadow-sm transition hover:!border-red-200 hover:!bg-red-50 hover:!text-red-600"
                      danger
                      type="text"
                      @click="removeProcessingUpload(field, file)"
                    >
                      <IconifyIcon
                        aria-hidden="true"
                        class="block size-4"
                        icon="lucide:trash-2"
                      />
                    </Button>
                  </Tooltip>
                </div>
                <div class="px-2 py-2">
                  <p
                    class="m-0 truncate text-xs text-slate-600"
                    :title="file.name"
                  >
                    {{ file.name }}
                  </p>
                </div>
              </article>
            </div>

            <Upload
              v-if="processingUploadCount(field.key) < (field.maxCount || 1)"
              :accept="field.accept || 'image/*'"
              class="block w-full"
              :custom-request="processingUploadRequest(field)"
              :disabled="isProcessingFieldUploading(field.key)"
              :file-list="processingUploadFiles[field.key] || []"
              :max-count="field.maxCount || 1"
              :show-upload-list="false"
            >
              <Button
                :aria-label="
                  processingUploadCount(field.key) > 0
                    ? `继续添加${field.label}`
                    : `上传${field.label}`
                "
                class="!flex !h-auto w-full !items-center !justify-start !rounded-lg border-dashed !px-4 !py-3 text-left"
                :disabled="isProcessingFieldUploading(field.key)"
              >
                <span
                  class="mr-3 inline-grid size-10 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-600"
                >
                  <IconifyIcon
                    aria-hidden="true"
                    class="block size-5"
                    :class="{
                      'animate-spin': isProcessingFieldUploading(field.key),
                    }"
                    :icon="
                      isProcessingFieldUploading(field.key)
                        ? 'lucide:loader-circle'
                        : 'lucide:image-plus'
                    "
                  />
                </span>
                <span class="min-w-0">
                  <span class="block text-sm font-medium text-slate-700">
                    {{
                      processingUploadCount(field.key) > 0
                        ? '继续添加图片'
                        : `选择${field.label}`
                    }}
                  </span>
                  <span class="mt-0.5 block text-xs font-normal text-slate-500">
                    还可上传
                    {{
                      (field.maxCount || 1) - processingUploadCount(field.key)
                    }}
                    张
                  </span>
                </span>
              </Button>
            </Upload>

            <div
              v-else
              class="flex items-center gap-2 rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-700"
              role="status"
            >
              <IconifyIcon aria-hidden="true" icon="lucide:circle-check" />
              已达到最多上传数量
            </div>
          </div>
          <Input
            v-else
            :id="`processing-action-${field.key}`"
            :value="processingTextValue(field.key)"
            :maxlength="field.maxLength"
            :placeholder="field.placeholder || `请输入${field.label}`"
            @update:value="updateProcessingField(field.key, $event)"
          />
          <p v-if="field.helpText" class="mb-0 mt-1 text-xs text-slate-500">
            {{ field.helpText }}
          </p>
          <p
            v-if="processingFieldErrors[field.key]"
            class="mb-0 mt-1 text-sm text-red-600"
            role="alert"
          >
            {{ processingFieldErrors[field.key] }}
          </p>
        </div>
        <div v-if="requiresAssetSelection" class="mb-4">
          <label
            for="processing-asset-selection"
            class="mb-2 block text-sm font-medium text-slate-700"
          >
            分配资产
            <span class="text-red-500" aria-hidden="true">*</span>
            <span class="ml-1 text-xs font-normal text-slate-500">
              请选择 {{ expectedAssetQuantity }} 个
            </span>
          </label>
          <Select
            id="processing-asset-selection"
            v-model:value="selectedAssetIds"
            :aria-invalid="Boolean(assetSelectionError)"
            :loading="assetSelectionLoading"
            mode="multiple"
            :options="availableAssetOptions"
            option-filter-prop="label"
            :placeholder="`请选择 ${expectedAssetQuantity} 个资产`"
            show-search
            class="w-full"
            @update:value="clearAssetSelectionError"
          />
          <p class="mb-0 mt-2 text-xs text-slate-500">
            <template v-if="assetChannelId(processingRecord)">
              仅展示关联渠道“{{ processingRecord.project }}”下的
            </template>
            <template v-else>
              仅展示与申请的“{{ processingInventorySelection?.label }}”匹配的
            </template>
            <template
              v-if="processingInventorySelection?.assetType === 'PIXEL'"
            >
              未分配像素库存；当前可选
            </template>
            <template v-else>可分配库存；当前可选</template>
            {{ availableAssetOptions.length }}
            个，提交时会再次校验渠道和资产类型。
          </p>
          <p
            v-if="assetSelectionError"
            class="mb-0 mt-2 text-sm text-red-600"
            role="alert"
          >
            {{ assetSelectionError }}
          </p>
        </div>
        <div v-if="needsStandaloneProcessingRemark">
          <label
            for="processing-remark"
            class="mb-2 block text-sm font-medium text-slate-700"
          >
            处理说明
            <span class="text-red-500" aria-hidden="true">*</span>
          </label>
          <Input.TextArea
            id="processing-remark"
            v-model:value="processingForm.remark"
            :aria-invalid="Boolean(processingError)"
            :maxlength="300"
            :rows="4"
            placeholder="请填写资产分配结果或其他处理说明"
            show-count
            @update:value="processingError = ''"
          />
          <p
            v-if="processingError"
            class="mb-0 mt-2 text-sm text-red-600"
            role="alert"
          >
            {{ processingError }}
          </p>
        </div>
      </div>
    </Modal>
  </Page>
</template>
