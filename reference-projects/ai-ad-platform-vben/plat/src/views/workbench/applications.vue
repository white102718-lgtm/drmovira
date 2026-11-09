<script lang="ts" setup>
import type { AccountOperationType } from './account-operation-entries';
import type { TablePaginationConfig } from 'ant-design-vue';

import type {
  ApplicationDefinition,
  ApplicationType as ApplicationTypeDefinition,
  ApprovalApplicationType,
  ApprovalConfig,
  AssetApplication,
  DynamicFieldOption,
  DynamicFormField,
} from '#/api';
import type { SystemDepartmentApi } from '#/api/system/department';
import type {
  ApplicationApprovalNode,
  ApplicationApprovalRole,
  ApplicationCategory,
  ApplicationStatus,
  ApplicationType,
  ApprovalAction,
  ResourceApplication,
} from '#/store/resource-applications';

import {
  computed,
  onActivated,
  onBeforeMount,
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
  DatePicker,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Pagination,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
} from 'ant-design-vue';
import { storeToRefs } from 'pinia';

import {
  assetFlowApi,
  getAccountOpeningChannelOptions,
  getChannelOptions,
  getChannelPaymentContext,
  getMyAdAccountAssets,
} from '#/api';
import { getSystemDepartmentTree } from '#/api/system/department';
import { getRoleList } from '#/api/system/role';
import { getUserList } from '#/api/system/user';
import {
  createPositiveIntegerRouteQueryField,
  createStringRouteQueryField,
  useRouteListQuery,
} from '#/composables/use-route-list-query';
import {
  applicationFormSchemaService,
  ApplicationService,
  approvalRoleForType,
  approvalRoleMeta,
  createDynamicFieldInitialValue,
  LegacyApplicationStoreAdapter,
  normalizeAccountOpeningFormSchema,
  resolveDynamicFieldPlaceholder,
  SOCIAL_ASSET_TYPE_OPTIONS,
} from '#/domain/application';
import {
  fixedDailyReportPreviewSchemas,
  isFixedDailyReportApplication,
} from '#/domain/daily-report-applications';
import {
  projectService,
  PROJECT_CLOSURE_APPLICATION_CODE,
} from '#/domain/project';
import { createTaskService } from '#/domain/task';
import { useResourceApplicationStore } from '#/store/resource-applications';
import { useTaskCenterStore } from '#/store/task-center';

import BusinessPageHeader from '../components/BusinessPageHeader.vue';
import ListLoading from '../components/ListLoading.vue';
import StableUserSelect from '../components/StableUserSelect.vue';
import {
  accountOperationEntries,
  findAccountOperationEntry,
  findAccountOperationEntryByCode,
} from './account-operation-entries';
import { MY_ASSET_ACCOUNT_APPLICATION_SOURCE } from './asset-account-application-actions';
import { buildMyAssetAdAccountOptions } from './my-asset-ad-account-options';
import ProcessingResultDetails from './components/ProcessingResultDetails.vue';
import PixelAssetSelector from './components/PixelAssetSelector.vue';

defineOptions({ name: 'WorkbenchApplications' });

const props = withDefaults(
  defineProps<{
    /** 申请填写页复用本组件的表单能力，避免与申请首页维护两套流程。 */
    pageMode?: 'create' | 'home';
  }>(),
  { pageMode: 'home' },
);

interface ResourceTypeMeta {
  category: ApplicationCategory;
  color: string;
  description: string;
  icon: string;
  iconClass: string;
  label: string;
  recommended?: boolean;
}

interface ApplicationEntry {
  applicationTypeId?: string;
  config: ApprovalConfig;
  definitionCode?: string;
  definitionId?: string;
  key: string;
  meta: ResourceTypeMeta & { applicationType: ApplicationType };
  operationType?: AccountOperationType;
}

/**
 * 资源申请首页以已确认原型的入口说明为展示基准。
 * 后端迁移完成前，仍可能返回历史文案，因此仅在展示层覆盖这些稳定申请编码。
 */
const prototypeApplicationDescriptions: Record<string, string> = {
  ACCOUNT_ACTIVE_CLEAR: '申请对广告账户执行活跃清零',
  ACCOUNT_ACTIVE_CLEAR_RECYCLE: '确认回流消耗数据后回收活跃清零账户',
  ACCOUNT_DEDUCTION: '申请从指定广告账户扣款并填写扣款金额',
  ACCOUNT_OPENING: '申请广告户并补充授权方式、开户数量与时区',
  ACCOUNT_REBIND: '申请将广告账户从原授权换绑到新授权',
  ACCOUNT_RECHARGE: '申请广告户充值，填写授权与开户信息',
  ACCOUNT_RECYCLE: '申请回收指定广告账户',
  ACCOUNT_UNBIND: '申请解除广告账户与邮箱或 BM 的绑定',
  BM: '申请 BM 并登记区域、数量与用途说明',
  BUNDLE: '申请账户绑包并提交绑定应用链接',
  COMPUTER: '申请办公电脑、剪辑工作站及配套设备',
  EMAIL: '申请业务邮箱和对应使用用途',
  MOBILE: '申请业务手机、验证手机及移动设备资源',
  PAGE: '申请主页并填写地区、数量和授权 BM',
  PAYMENT: '申请渠道打款并登记昨日消耗和收款信息',
  PIXEL: '申请网站或应用转化像素、事件及使用权限',
  PROJECT_CLOSURE: '申请项目结项并提交结算金额、周期与结项说明',
  STATIC_IP: '申请静态 IP，并指定地区与使用用途',
  TG: '申请 TG、Facebook、微信等社交资产',
};

function resolvePrototypeApplicationDescription(
  applicationCode: string | undefined,
  fallback: string,
) {
  return prototypeApplicationDescriptions[applicationCode ?? ''] ?? fallback;
}

const applicationStore = useResourceApplicationStore();
const taskCenterStore = useTaskCenterStore();
const userStore = useUserStore();
const route = useRoute();
const router = useRouter();
const isCreatePage = computed(() => props.pageMode === 'create');
const { applications } = storeToRefs(applicationStore);
const applicationService = new ApplicationService(
  new LegacyApplicationStoreAdapter({
    applications: () => applications.value,
    remove: applicationStore.removeApplication,
    upsert: applicationStore.upsertApplication,
  }),
);
const taskService = createTaskService(() => taskCenterStore.tasks, {
  acceptTask: taskCenterStore.acceptTask,
  completeTask: taskCenterStore.completeTask,
  patchTask: taskCenterStore.patchTask,
  rejectTask: taskCenterStore.rejectTask,
});

const typeMeta: Record<ApplicationType, ResourceTypeMeta> = {
  account: {
    category: 'advertising',
    color: 'blue',
    description: '申请个号或 BM 资源，并按对应动态表单进入审批流程',
    icon: 'lucide:badge-dollar-sign',
    iconClass: 'application-icon application-icon--blue',
    label: '个号 / BM 申请',
    recommended: true,
  },
  pixel: {
    category: 'advertising',
    color: 'cyan',
    description: '申请网站或应用转化像素、事件及使用权限',
    icon: 'lucide:scan-line',
    iconClass: 'application-icon application-icon--cyan',
    label: '像素申请',
    recommended: true,
  },
  tg: {
    category: 'social',
    color: 'geekblue',
    description: '申请 TG号、微信号或 Facebook 账号',
    icon: 'lucide:messages-square',
    iconClass: 'application-icon application-icon--indigo',
    label: '社交资产申请',
  },
  computer: {
    category: 'office',
    color: 'purple',
    description: '申请办公电脑、剪辑工作站及配套设备',
    icon: 'lucide:laptop',
    iconClass: 'application-icon application-icon--violet',
    label: '电脑申请',
  },
  mobile: {
    category: 'office',
    color: 'magenta',
    description: '申请业务手机号、验证手机及移动设备资源',
    icon: 'lucide:smartphone',
    iconClass: 'application-icon application-icon--pink',
    label: '手机号申请',
  },
  payment: {
    category: 'finance',
    color: 'orange',
    description: '申请充值、垫付、供应商结算及项目付款',
    icon: 'lucide:banknote',
    iconClass: 'application-icon application-icon--emerald',
    label: '项目付款申请',
    recommended: true,
  },
  project: {
    category: 'advertising',
    color: 'green',
    description: '提交项目结项材料并进入已配置的审批流程。',
    icon: 'lucide:circle-check-big',
    iconClass: 'application-icon application-icon--amber',
    label: '项目结项审批',
  },
};

const legacyConfigTypeMeta: Record<
  string,
  ResourceTypeMeta & { applicationType: ApplicationType }
> = {
  PERSONAL: {
    ...typeMeta.account,
    applicationType: 'account',
    description: '申请个号资源并按管理员配置的表单发起审批',
    icon: 'lucide:user-round',
    label: '个号申请',
  },
  BM: {
    ...typeMeta.account,
    applicationType: 'account',
    description: '申请 BM 资源并按管理员配置的表单发起审批',
    icon: 'lucide:building-2',
    label: 'BM 申请',
  },
  PIXEL: { ...typeMeta.pixel, applicationType: 'pixel' },
  [PROJECT_CLOSURE_APPLICATION_CODE]: {
    ...typeMeta.project,
    applicationType: 'project',
  },
  TG: { ...typeMeta.tg, applicationType: 'tg' },
};

const socialApplicationFormSchema: DynamicFormField[] = [
  {
    key: 'sectionDetails',
    label: '社交资产信息',
    required: false,
    type: 'section',
    width: 'full',
  },
  {
    key: 'socialAssetType',
    label: '社交资产类型',
    options: [...SOCIAL_ASSET_TYPE_OPTIONS],
    optionSource: 'custom',
    placeholder: '请选择社交资产类型',
    required: true,
    type: 'select',
    width: 'half',
  },
  {
    key: 'quantity',
    label: '数量',
    minValue: 1,
    required: true,
    type: 'number',
    width: 'half',
  },
  {
    key: 'region',
    label: '地区',
    options: [
      '新加坡',
      '马来西亚',
      '泰国',
      '越南',
      '印度尼西亚',
      '菲律宾',
      '印度',
      '美国',
      '日本',
      '香港',
    ],
    optionSource: 'custom',
    placeholder: '请选择地区',
    required: false,
    type: 'select',
    width: 'half',
  },
  {
    key: 'purpose',
    label: '说明',
    maxLength: 200,
    placeholder: '请输入使用说明',
    required: false,
    type: 'textarea',
    width: 'full',
  },
];

const socialApplicationFallbackConfig: ApprovalConfig = {
  applicationDefinitionIds: [],
  assetType: 'TG',
  category: 'social',
  description: '申请 TG号、微信号或 Facebook 账号，审批完成后分配对应类型资产',
  enabled: true,
  formSchema: socialApplicationFormSchema,
  handlerId: '',
  handlerName: '社交资产办理人',
  icon: 'lucide:messages-square',
  id: 'social-asset-fallback',
  name: '社交资产申请',
  nodes: [],
  settings: {
    handlerAction: {
      resourceAssignment: {
        assetTypeFieldKey: 'socialAssetType',
        assetTypeSource: 'application',
        channelFieldKey: '',
        enabled: true,
        quantityFieldKey: 'quantity',
      },
    },
  },
  sortOrder: 40,
  status: 'published',
  updatedAt: '',
  usageCount: 0,
  visibility: 'all',
};

const legacyAccountFieldApplications: Record<string, string[]> = {
  amount: ['ACCOUNT_RECHARGE', 'ACCOUNT_DEDUCTION'],
  applyReason: ['ACCOUNT_ACTIVE_CLEAR', 'ACCOUNT_ACTIVE_CLEAR_RECYCLE'],
  authAccount: ['ACCOUNT_UNBIND', 'ACCOUNT_REBIND'],
  originalAuthAccount: ['ACCOUNT_REBIND'],
  remark: [
    'ACCOUNT_ACTIVE_CLEAR',
    'ACCOUNT_ACTIVE_CLEAR_RECYCLE',
    'ACCOUNT_RECYCLE',
  ],
};

function normalizeAccountOperationSchema(fields: DynamicFormField[]) {
  return fields.flatMap((field) => {
    if (field.key === 'operationType') return [];
    const usesLegacyCondition =
      field.visibleWhen?.fieldKey === 'operationType' ||
      field.requiredWhen?.fieldKey === 'operationType';
    if (!usesLegacyCondition) return [field];
    return [
      {
        ...field,
        applicableApplicationCodes: legacyAccountFieldApplications[field.key],
        required: field.key === 'remark' ? field.required : true,
        requiredWhen: undefined,
        visibleWhen: undefined,
      },
    ];
  });
}

/** 兼容存量配置，在读取时转换为当前申请表单结构。 */
function normalizeApplicationConfig(config: ApprovalConfig): ApprovalConfig {
  if (config.assetType === 'ACCOUNT_OPENING') {
    return {
      ...config,
      formSchema: normalizeAccountOpeningFormSchema(config.formSchema),
    };
  }
  if (config.assetType === 'ACCOUNT_OPERATION') {
    return {
      ...config,
      formSchema: normalizeAccountOperationSchema(config.formSchema),
    };
  }
  if (config.assetType !== 'TG') return config;
  return {
    ...config,
    category: 'social',
    description: socialApplicationFallbackConfig.description,
    formSchema: socialApplicationFormSchema,
    icon: socialApplicationFallbackConfig.icon,
    name: socialApplicationFallbackConfig.name,
    settings: {
      ...config.settings,
      handlerAction: socialApplicationFallbackConfig.settings.handlerAction,
    },
  };
}

function configMeta(
  config: ApprovalConfig,
): ResourceTypeMeta & { applicationType: ApplicationType } {
  const legacy = legacyConfigTypeMeta[config.assetType];
  if (legacy) return legacy;
  let applicationType: ApplicationType = 'account';
  if (config.category === 'office') applicationType = 'computer';
  if (config.category === 'finance') applicationType = 'payment';
  if (config.category === 'social') applicationType = 'tg';
  return {
    ...typeMeta[applicationType],
    applicationType,
    description: `填写“${config.name}”动态表单并进入已配置的审批流程`,
    label: config.name,
  };
}

function syncBackendApplications(items: AssetApplication[]) {
  for (const item of items) {
    const normalizedId = String(item.id);
    const existing = applications.value.find(
      (application) => String(application.id) === normalizedId,
    );
    const meta = legacyConfigTypeMeta[item.assetType];
    let type = meta?.applicationType ?? 'account';
    if (item.formData?.configCategory === 'office') type = 'computer';
    if (item.formData?.configCategory === 'finance') type = 'payment';
    if (item.formData?.configCategory === 'social') type = 'tg';
    let status: ApplicationStatus = 'pending';
    if (item.status === 'APPROVED') status = 'approved';
    if (item.status === 'PROCESSING') status = 'processing';
    if (item.status === 'REJECTED') status = 'rejected';
    const currentIndex = item.currentNodeIndex ?? 0;
    const nodes = (item.nodes ?? []).map((node, index) => {
      let nodeStatus: ApplicationApprovalNode['status'] = 'waiting';
      if (
        status === 'approved' ||
        status === 'processing' ||
        index < currentIndex
      ) {
        nodeStatus = 'approved';
      } else if (status === 'rejected' && index === currentIndex) {
        nodeStatus = 'rejected';
      } else if (index === currentIndex) {
        nodeStatus = 'pending';
      }
      return {
        approver: node.approverName,
        approverId: String(node.approverId),
        id: `NODE-${item.id}-${index}`,
        label: node.name,
        role: 'media' as const,
        status: nodeStatus,
      };
    });
    const formSchema = isFixedDailyReportApplication(item.assetType)
      ? fixedDailyReportPreviewSchemas[item.assetType]
      : item.formSchema;
    applicationService.save({
      approvalNodes: nodes.length > 0 ? nodes : (existing?.approvalNodes ?? []),
      approvalRecords:
        item.approvalLogs?.map((log) => ({
          action: backendApprovalAction(log.action),
          actionData: log.actionData,
          actor: log.actorName,
          actorRole:
            log.nodeName ||
            (log.action === 'COMPLETED' ? '资产处理与分配' : '审批流程'),
          at: log.createdAt,
          id: String(log.id),
          remark:
            log.action === 'COMPLETED'
              ? `处理完成：${log.remark || '资产已分配'}`
              : log.remark || '流程状态已更新',
        })) ??
        existing?.approvalRecords ??
        [],
      approvalRole: existing?.approvalRole ?? 'media',
      allocatedAssets: item.allocatedAssets?.map((asset) => ({
        assetCode: asset.assetCode,
        assetName: asset.assetName,
        assetType: asset.assetType,
        channelName: asset.channelName,
        id: String(asset.id),
        projectName: asset.projectName,
      })),
      approver:
        item.status === 'PROCESSING' ? item.handlerName : item.approverName,
      ccUsers: existing?.ccUsers ?? [],
      comments: existing?.comments ?? [],
      createdAt: item.createdAt,
      description:
        item.reason ||
        String(
          item.formData?.purpose ??
            item.formData?.description ??
            item.formData?.remark ??
            existing?.description ??
            '',
        ),
      formData: item.formData,
      formSchema,
      handlerAction: item.handlerAction,
      handlerApprovalNodeId: item.handlerApprovalNodeId,
      handlerId: String(item.handlerId),
      handlerName: item.handlerName,
      handlerSource: item.handlerSource,
      id: normalizedId,
      platform: item.assetType,
      project:
        String(
          item.formData?.channelName ??
            item.formData?.projectName ??
            item.formData?.project ??
            existing?.project ??
            '',
        ).trim() || '未关联归属',
      projectId: String(
        item.formData?.channelId ??
          item.formData?.projectId ??
          existing?.projectId ??
          '',
      ),
      quantity: item.quantity,
      requester: item.requesterName,
      requesterId: String(item.requesterId),
      requesterName: item.requesterName,
      sourceApplicationId: item.sourceApplicationId,
      status,
      title: item.title,
      type,
      updatedAt: item.updatedAt ?? item.createdAt,
    });
  }
}

function backendApprovalAction(action: string): ApprovalAction {
  if (action === 'SUBMITTED') return 'submitted';
  if (action === 'REJECTED') return 'rejected';
  if (action === 'COMPLETED') return 'completed';
  return 'approved';
}

const fallbackCategories: Array<{
  description: string;
  icon: string;
  key: 'all' | ApplicationCategory;
  label: string;
}> = [
  {
    key: 'all',
    label: '全部申请',
    description: '查看所有资源类型',
    icon: 'lucide:layout-grid',
  },
  {
    key: 'social',
    label: '社交资产',
    description: 'TG号、微信号、Facebook 账号',
    icon: 'lucide:messages-square',
  },
  {
    key: 'advertising',
    label: '广告资产',
    description: '广告户、像素、BM 与主页',
    icon: 'lucide:badge-dollar-sign',
  },
  {
    key: 'office',
    label: '办公资产',
    description: '电脑、手机、邮箱与静态 IP',
    icon: 'lucide:laptop',
  },
  {
    key: 'finance',
    label: '财务申请',
    description: '项目充值与付款',
    icon: 'lucide:wallet-cards',
  },
];

const statusMeta: Record<ApplicationStatus, { color: string; label: string }> =
  {
    approved: { color: 'success', label: '已通过' },
    draft: { color: 'default', label: '草稿' },
    pending: { color: 'processing', label: '待审批' },
    processing: { color: 'warning', label: '处理中' },
    rejected: { color: 'error', label: '已驳回' },
  };

const approvalActionMeta = {
  approved: {
    icon: 'lucide:circle-check-big',
    label: '审批通过',
    tone: 'bg-muted text-foreground',
  },
  completed: {
    icon: 'lucide:package-check',
    label: '办理完成',
    tone: 'bg-muted text-foreground',
  },
  copied: {
    icon: 'lucide:send-to-back',
    label: '完成抄送',
    tone: 'bg-muted text-foreground',
  },
  rejected: {
    icon: 'lucide:circle-x',
    label: '审批驳回',
    tone: 'bg-muted text-foreground',
  },
  submitted: {
    icon: 'lucide:send',
    label: '提交申请',
    tone: 'bg-muted text-foreground',
  },
  transferred: {
    icon: 'lucide:arrow-right-left',
    label: '转交办理',
    tone: 'bg-amber-50 text-amber-700',
  },
};

const applicationTypes = ref<ApplicationTypeDefinition[]>([]);
const activeApplicationTypeId = ref('all');
const activeType = ref<'all' | ApplicationType>('all');
const statusFilter = ref<'all' | ApplicationStatus>('all');
const keyword = ref('');
const entryKeyword = ref('');
const entryPage = ref(1);
const historyPage = ref(1);
const historyPageSize = ref(8);
const applicationListLoading = ref(true);
// 旧深链先进入表单加载态，避免在路由迁移前短暂渲染资源申请主页。
const formMode = ref(isCreatePage.value || route.query.new === '1');
const submitting = ref(false);
const editingId = ref<string>();
/** 重提时仅保存来源单 ID，提交后由后端创建一张全新的审批申请。 */
const resubmissionSourceApplicationId = ref<string>();
const detailRecord = ref<ResourceApplication>();
const detailActiveTab = ref('info');
const currentUserName = computed(
  () =>
    userStore.userInfo?.realName || userStore.userInfo?.full_name || '当前用户',
);
const currentUserId = computed(() => {
  const user = userStore.userInfo as
    | undefined
    | { _id?: string; user_id?: string; userId?: string };
  const candidate = user?.userId ?? user?.user_id ?? user?._id;
  return typeof candidate === 'string' ? candidate.trim() : '';
});
const form = reactive({
  approvalNodes: [] as ApplicationApprovalNode[],
  amount: undefined as number | undefined,
  currency: 'USD',
  ccUsers: [] as string[],
  description: '',
  platform: '',
  project: '',
  projectId: '',
  quantity: 1,
  resourceAssigneeId: '',
  resourceAssigneeName: '',
  resourceTeamId: '',
  resourceTeamName: '',
  specifications: '',
  title: '',
  type: 'account' as ApplicationType,
  sourceTaskId: '',
});

const baseProjectOptions = [
  {
    label: 'Starfall 全球增长',
    projectId: 'project-starfall',
    value: 'Starfall 全球增长',
  },
  {
    label: 'Pixel Quest 日本首发',
    projectId: 'project-pixel',
    value: 'Pixel Quest 日本首发',
  },
  {
    label: 'Project Ark 美国市场',
    projectId: 'project-ark',
    value: 'Project Ark 美国市场',
  },
];

const resolvedProjectOptions = ref([...baseProjectOptions]);
const resolvedChannelOptions = ref<DynamicFieldOption[]>([]);
const channelOptionsLoading = ref(false);
const channelOptionsLoadAttempted = ref(false);

const platformOptions = computed(() => {
  if (form.type === 'account') {
    return [
      { label: '个号', value: 'PERSONAL' },
      { label: 'BM', value: 'BM' },
    ];
  }
  if (form.type === 'tg') {
    return [
      { label: 'Telegram', value: 'Telegram' },
      { label: 'WhatsApp', value: 'WhatsApp' },
      { label: '其他社交媒体', value: '其他社交媒体' },
    ];
  }
  return [
    { label: 'Facebook', value: 'Facebook' },
    { label: 'Google', value: 'Google' },
    { label: 'TikTok', value: 'TikTok' },
    { label: 'Kwai', value: 'Kwai' },
  ];
});

const currencyOptions = [
  { label: 'USD - 美元', value: 'USD' },
  { label: 'CNY - 人民币', value: 'CNY' },
  { label: 'JPY - 日元', value: 'JPY' },
];

const ccUserOptions = [
  { label: '项目负责人', value: '项目负责人' },
  { label: '资源交付负责人', value: '资源交付负责人' },
  { label: '申请人直属负责人', value: '申请人直属负责人' },
  { label: '资产管理员', value: '资产管理员' },
  { label: '财务归档', value: '财务归档' },
];

const approverOptions: Array<{
  id: string;
  label: string;
  role: ApplicationApprovalRole;
  value: string;
}> = [
  {
    id: 'user-media-lead',
    label: '周敏 · 媒介审批',
    role: 'media',
    value: '周敏',
  },
  {
    id: 'user-chen-hang',
    label: '陈航 · 媒介负责人',
    role: 'media',
    value: '陈航',
  },
  {
    id: 'user-office-lead',
    label: '郑然 · 行政与资产审批',
    role: 'office',
    value: '郑然',
  },
  {
    id: 'user-finance-lead',
    label: '王楠 · 财务审批',
    role: 'finance',
    value: '王楠',
  },
  {
    id: 'user-lin-qi',
    label: '林琦 · 财务负责人',
    role: 'finance',
    value: '林琦',
  },
];

const backendMediaApprover = ref<{ id: string; name: string }>();
const backendConfigs = ref<ApprovalConfig[]>([]);
const backendApplicationDefinitions = ref<ApplicationDefinition[]>([]);
const selectedConfigType = ref<ApprovalApplicationType>('PERSONAL');
const selectedApplicationDefinitionId = ref<string>();
const selectedApplicationDefinitionCode = ref<string>();
const selectedApplicationDefinitionName = ref<string>();
const selectedAccountOperation = ref<AccountOperationType>();
const dynamicFormData = reactive<Record<string, any>>({});
const dynamicDepartmentOptions = ref<Array<{ label: string; value: string }>>(
  [],
);
const dynamicRoleOptions = ref<Array<{ label: string; value: string }>>([]);
const dynamicUserOptions = ref<Array<{ label: string; value: string }>>([]);
const departmentOptionsLoading = ref(false);
const departmentOptionsLoaded = ref(false);
const roleOptionsLoading = ref(false);
const roleOptionsLoaded = ref(false);
const userOptionsLoading = ref(false);
const userOptionsLoaded = ref(false);
const dynamicAdAccountOptions = ref<Array<{ label: string; value: string }>>(
  [],
);
const dynamicAdAccountOptionsLoading = ref(false);
const projectOptionsLoading = ref(false);
const projectOptionsLoaded = ref(false);
const dynamicAutoFillLoadingKeys = ref<Set<string>>(new Set());
let dynamicAutoFillRequestSequence = 0;
const channelScopedAssetTypes = new Set<ApprovalApplicationType>([
  'BM',
  'PERSONAL',
  'PIXEL',
]);

const activeBackendConfig = computed(() => {
  return backendConfigs.value.find(
    (item) => item.assetType === selectedConfigType.value && item.enabled,
  );
});

const isChannelScopedApplication = computed(
  () =>
    selectedConfigType.value !== PROJECT_CLOSURE_APPLICATION_CODE &&
    (activeBackendConfig.value?.category === 'advertising' ||
      channelScopedAssetTypes.has(selectedConfigType.value)),
);
function matchesDynamicCondition(field: DynamicFormField) {
  const condition = field.visibleWhen;
  if (!condition) return true;
  const current = dynamicFormData[condition.fieldKey];
  if (condition.operator === 'equals') return current === condition.value;
  if (condition.operator === 'not-equals') return current !== condition.value;
  const expected = Array.isArray(condition.value)
    ? condition.value
    : [condition.value];
  return expected.includes(String(current ?? ''));
}

function matchesApplicationScope(field: DynamicFormField) {
  const codes = field.applicableApplicationCodes;
  if (!codes?.length) return true;
  return Boolean(
    selectedApplicationDefinitionCode.value &&
      codes.includes(selectedApplicationDefinitionCode.value),
  );
}

const applicationScopedFormSchema = computed(() =>
  (activeBackendConfig.value?.formSchema ?? []).filter(
    (field) =>
      matchesApplicationScope(field) &&
      !(
        selectedConfigType.value === 'ACCOUNT_OPERATION' &&
        field.key === 'operationType'
      ),
  ),
);

const dynamicFields = computed<DynamicFormField[]>(() => {
  return applicationScopedFormSchema.value.filter((field) =>
    matchesDynamicCondition(field),
  );
});

const rechargeCurrencyField = computed(() =>
  dynamicFields.value.find((field) => field.key === 'amountType'),
);

/** MPower 将币种作为充值金额的后缀控件，不再单独占用一个表单网格。 */
const renderedDynamicFields = computed(() =>
  dynamicFields.value.filter(
    (field) =>
      field.key !== 'amountType' ||
      !dynamicFields.value.some((item) => item.key === 'rechargeAmount'),
  ),
);

const dynamicAutoFillFields = computed(() =>
  applicationScopedFormSchema.value.filter(
    (field) => field.type !== 'section' && field.autoFill,
  ),
);

const dynamicAutoFillTriggerSignature = computed(() =>
  dynamicAutoFillFields.value
    .map((field) => {
      const triggerKey = field.autoFill?.triggerFieldKey ?? '';
      return `${field.autoFill?.source ?? ''}:${triggerKey}:${String(
        dynamicFormData[triggerKey] ?? '',
      )}`;
    })
    .join('|'),
);

function isDynamicAutoFillLoading(field: DynamicFormField) {
  return dynamicAutoFillLoadingKeys.value.has(field.key);
}

/** 按配置中的受控数据源和依赖字段回填只读数据，避免表单写死业务接口。 */
async function refreshDynamicAutoFill() {
  const requestSequence = ++dynamicAutoFillRequestSequence;
  const fields = dynamicAutoFillFields.value;
  const grouped = new Map<string, DynamicFormField[]>();
  for (const field of fields) {
    const binding = field.autoFill;
    if (!binding) continue;
    const triggerValue = String(
      dynamicFormData[binding.triggerFieldKey] ?? '',
    ).trim();
    if (!triggerValue) {
      dynamicFormData[field.key] = '';
      continue;
    }
    const groupKey = `${binding.source}:${binding.triggerFieldKey}:${triggerValue}`;
    grouped.set(groupKey, [...(grouped.get(groupKey) ?? []), field]);
  }
  dynamicAutoFillLoadingKeys.value = new Set(
    [...grouped.values()].flatMap((items) => items.map((field) => field.key)),
  );
  try {
    for (const group of grouped.values()) {
      const binding = group[0]?.autoFill;
      if (!binding || binding.source !== 'channel-payment-context') continue;
      const triggerValue = String(
        dynamicFormData[binding.triggerFieldKey] ?? '',
      ).trim();
      const context = await getChannelPaymentContext(triggerValue);
      if (requestSequence !== dynamicAutoFillRequestSequence) return;
      for (const field of group) {
        const resultKey = field.autoFill?.resultKey;
        if (resultKey) dynamicFormData[field.key] = context[resultKey] ?? '';
      }
    }
  } finally {
    if (requestSequence === dynamicAutoFillRequestSequence) {
      dynamicAutoFillLoadingKeys.value = new Set();
    }
  }
}

watch(dynamicAutoFillTriggerSignature, () => {
  void refreshDynamicAutoFill().catch(() => {
    // 请求层统一提示错误；必填的自动回填字段保持为空并阻止提交。
  });
});

function isDynamicFieldRequired(field: DynamicFormField) {
  if (field.type === 'section') return false;
  if (field.required) return true;
  const condition = field.requiredWhen;
  if (!condition) return false;
  const current = dynamicFormData[condition.fieldKey];
  if (condition.operator === 'equals') return current === condition.value;
  if (condition.operator === 'not-equals') return current !== condition.value;
  const expected = Array.isArray(condition.value)
    ? condition.value
    : [condition.value];
  return expected.includes(String(current ?? ''));
}

function dynamicOptions(field: DynamicFormField) {
  if (field.optionSource === 'ad-accounts')
    return dynamicAdAccountOptions.value;
  if (field.optionSource === 'departments')
    return dynamicDepartmentOptions.value;
  if (field.optionSource === 'users') return dynamicUserOptions.value;
  if (field.optionSource === 'roles') return dynamicRoleOptions.value;
  if (field.optionSource === 'projects') {
    return resolvedProjectOptions.value.map((option) => ({
      label: option.label,
      value: option.projectId,
    }));
  }
  if (field.optionSource === 'channels') {
    return resolvedChannelOptions.value;
  }
  return (field.options ?? []).map((option) => ({
    label: option,
    value: option,
  }));
}

function isDynamicOptionLoading(field: DynamicFormField) {
  if (field.optionSource === 'ad-accounts') {
    return dynamicAdAccountOptionsLoading.value;
  }
  if (field.optionSource === 'channels') return channelOptionsLoading.value;
  if (field.optionSource === 'departments') {
    return departmentOptionsLoading.value;
  }
  if (field.optionSource === 'projects') return projectOptionsLoading.value;
  if (field.optionSource === 'roles') return roleOptionsLoading.value;
  if (field.optionSource === 'users') return userOptionsLoading.value;
  return false;
}

function routeQueryText(value: unknown) {
  return typeof value === 'string' ? value.trim() : '';
}

function isMyAssetAccountApplicationRoute() {
  return (
    routeQueryText(route.query.source) === MY_ASSET_ACCOUNT_APPLICATION_SOURCE
  );
}

/** 保留非本人资产入口带入的账户，避免其尚未同步到账户管理时下拉框只显示裸值。 */
function ensureRouteAdAccountOption() {
  if (isMyAssetAccountApplicationRoute()) return;
  const accountId = routeQueryText(route.query.adAccountId);
  if (
    !accountId ||
    dynamicAdAccountOptions.value.some((option) => option.value === accountId)
  ) {
    return;
  }
  const accountName = routeQueryText(route.query.adAccountName);
  dynamicAdAccountOptions.value = [
    {
      label: accountName ? `${accountName}（${accountId}）` : accountId,
      value: accountId,
    },
    ...dynamicAdAccountOptions.value,
  ];
}

async function loadAdAccountOptions() {
  if (dynamicAdAccountOptionsLoading.value) return;
  dynamicAdAccountOptionsLoading.value = true;
  try {
    dynamicAdAccountOptions.value = buildMyAssetAdAccountOptions(
      await getMyAdAccountAssets(),
    );
    ensureRouteAdAccountOption();
  } finally {
    dynamicAdAccountOptionsLoading.value = false;
  }
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

async function loadDepartmentOptions() {
  if (departmentOptionsLoaded.value || departmentOptionsLoading.value) return;

  departmentOptionsLoading.value = true;
  try {
    dynamicDepartmentOptions.value = flattenDepartmentOptions(
      (await getSystemDepartmentTree()) ?? [],
    );
    departmentOptionsLoaded.value = true;
  } finally {
    departmentOptionsLoading.value = false;
  }
}

async function loadUserOptions() {
  if (userOptionsLoaded.value || userOptionsLoading.value) return;

  userOptionsLoading.value = true;
  try {
    const users = await getUserList({ page: 1, pageSize: 500, status: 1 });
    dynamicUserOptions.value = (users.items ?? [])
      .filter((user) => user.status === 1)
      .map((user) => ({
        label: user.realName || user.displayName,
        value: user.id,
      }));
    userOptionsLoaded.value = true;
  } finally {
    userOptionsLoading.value = false;
  }
}

async function loadRoleOptions() {
  if (roleOptionsLoaded.value || roleOptionsLoading.value) return;

  roleOptionsLoading.value = true;
  try {
    const roles = await getRoleList({ page: 1, pageSize: 500, status: 1 });
    dynamicRoleOptions.value = (roles.items ?? [])
      .filter((role) => role.status === 1)
      .map((role) => ({ label: role.roleName, value: role.id }));
    roleOptionsLoaded.value = true;
  } finally {
    roleOptionsLoading.value = false;
  }
}

/** 仅加载当前表单实际使用的远程选项，避免申请首页被大体量通讯录请求阻塞。 */
function loadRequiredDynamicOptions(fields: readonly DynamicFormField[]) {
  const optionSources = new Set(fields.map((field) => field.optionSource));
  const requests: Promise<void>[] = [];
  if (optionSources.has('departments')) requests.push(loadDepartmentOptions());
  if (optionSources.has('users')) requests.push(loadUserOptions());
  if (optionSources.has('roles')) requests.push(loadRoleOptions());
  if (optionSources.has('projects')) requests.push(loadProjectOptions());
  if (optionSources.has('channels')) requests.push(loadChannelOptions());
  if (optionSources.has('ad-accounts')) requests.push(loadAdAccountOptions());

  // 请求层已提供错误反馈；单个选项源失败不应影响其他字段继续加载。
  void Promise.allSettled(requests);
}

function resetDynamicForm() {
  Object.keys(dynamicFormData).forEach((key) => delete dynamicFormData[key]);
  for (const field of applicationScopedFormSchema.value) {
    if (field.type === 'section') continue;
    dynamicFormData[field.key] = createDynamicFieldInitialValue(field);
  }
  const config = activeBackendConfig.value;
  if (config) {
    form.approvalNodes = config.nodes.map((node, index) => ({
      approver: node.approverName,
      approverId: node.approverId,
      id: `NODE-DRAFT-${Date.now()}-${index}`,
      label: node.name,
      role: 'media',
      status: index === 0 ? 'pending' : 'waiting',
    }));
  }
}

function createApprovalNode(
  role: ApplicationApprovalRole,
  index: number,
): ApplicationApprovalNode {
  if (role === 'media' && backendMediaApprover.value) {
    return {
      approver: backendMediaApprover.value.name,
      approverId: backendMediaApprover.value.id,
      id: `NODE-DRAFT-${Date.now()}-${index}`,
      label: approvalRoleMeta[role].label,
      role,
      status: index === 0 ? 'pending' : 'waiting',
    };
  }
  const approver = approverOptions.find(
    (item) => item.value === approvalRoleMeta[role].approver,
  );
  return {
    approver: approver?.value ?? approvalRoleMeta[role].approver,
    approverId: approver?.id,
    id: `NODE-DRAFT-${Date.now()}-${index}`,
    label: approvalRoleMeta[role].label,
    role,
    status: index === 0 ? 'pending' : 'waiting',
  };
}

function resetApprovalNodes(type: ApplicationType) {
  const role = approvalRoleForType(type);
  form.approvalNodes = [createApprovalNode(role, 0)];
}

function removeApprovalNode(index: number) {
  if (form.approvalNodes.length <= 1) {
    message.warning('至少保留一个审批节点');
    return;
  }
  form.approvalNodes.splice(index, 1);
}

function handleApproverChange(index: number, approver: string) {
  const option = approverOptions.find((item) => item.value === approver);
  const node = form.approvalNodes[index];
  if (!node || !option) return;
  node.role = option.role;
  node.approverId = option.id;
  node.label = approvalRoleMeta[option.role].label;
}

const statusOptions = [
  { label: '全部状态', value: 'all' },
  ...Object.entries(statusMeta).map(([value, item]) => ({
    label: item.label,
    value,
  })),
];

const { isApplyingRoute } = useRouteListQuery({
  fields: {
    category: createStringRouteQueryField(activeApplicationTypeId, {
      defaultValue: 'all',
    }),
    historyPage: createPositiveIntegerRouteQueryField(historyPage, {
      defaultValue: 1,
    }),
    historyPageSize: createPositiveIntegerRouteQueryField(historyPageSize, {
      allowedValues: [8, 20, 50, 100],
      defaultValue: 8,
    }),
    historyQ: createStringRouteQueryField(keyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
    historyStatus: createStringRouteQueryField(statusFilter, {
      allowedValues: statusOptions.map((item) => item.value),
      defaultValue: 'all',
    }),
    historyType: createStringRouteQueryField(activeType, {
      allowedValues: ['all', ...Object.keys(typeMeta)] as Array<
        'all' | ApplicationType
      >,
      defaultValue: 'all',
    }),
    page: createPositiveIntegerRouteQueryField(entryPage, {
      defaultValue: 1,
    }),
    q: createStringRouteQueryField(entryKeyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
  },
  route,
  router,
});

const publishedConfigs = computed(() =>
  backendConfigs.value.filter((config) => config.enabled),
);

const hiddenApplicationAssetTypes = new Set<ApprovalApplicationType>([
  'PERSONAL',
]);

/** 将申请定义映射到其审批配置；后端升级前继续兼容按配置生成入口。 */
const publishedEntries = computed<ApplicationEntry[]>(() => {
  if (backendApplicationDefinitions.value.length > 0) {
    return backendApplicationDefinitions.value.flatMap((definition) => {
      if (
        definition.showInResourceApplication === false ||
        isFixedDailyReportApplication(definition.applicationCode)
      ) {
        return [];
      }
      const config = publishedConfigs.value.find(
        (item) => String(item.id) === String(definition.approvalConfigId),
      );
      // 个号继续保留存量审批和历史记录能力，但不再允许从资源申请首页发起。
      if (!config || hiddenApplicationAssetTypes.has(config.assetType)) {
        return [];
      }
      const baseMeta = configMeta(config);
      const operation = findAccountOperationEntryByCode(
        definition.applicationCode,
      );
      return [
        {
          config,
          definitionCode: definition.applicationCode,
          definitionId: definition.id,
          applicationTypeId: definition.applicationTypeId,
          key: String(definition.id),
          meta: {
            ...baseMeta,
            description: resolvePrototypeApplicationDescription(
              definition.applicationCode,
              definition.description,
            ),
            icon: definition.icon,
            iconClass: operation?.iconClass ?? baseMeta.iconClass,
            label: definition.applicationName,
            recommended: operation?.recommended ?? baseMeta.recommended,
          },
          operationType: operation?.operationType,
        },
      ];
    });
  }
  return publishedConfigs.value.flatMap((config) => {
    if (hiddenApplicationAssetTypes.has(config.assetType)) return [];
    if (config.assetType !== 'ACCOUNT_OPERATION') {
      const meta = configMeta(config);
      return [
        {
          config,
          key: String(config.id),
          meta: {
            ...meta,
            description: resolvePrototypeApplicationDescription(
              config.assetType,
              meta.description,
            ),
          },
        },
      ];
    }
    return accountOperationEntries.map((operation) => ({
      config,
      definitionCode: operation.applicationCode,
      key: `${config.id}:${operation.key}`,
      meta: {
        ...typeMeta.payment,
        applicationType: 'payment' as const,
        category: 'finance' as const,
        description: resolvePrototypeApplicationDescription(
          operation.applicationCode,
          operation.description,
        ),
        icon: operation.icon,
        iconClass: operation.iconClass,
        label: operation.label,
        recommended: operation.recommended,
      },
      operationType: operation.operationType,
    }));
  });
});

/**
 * 申请分类只在存在可发起的已发布入口时展示，避免用户进入没有可用申请的空分类。
 */
const categories = computed(() => {
  const availableApplicationTypeIds = new Set(
    publishedEntries.value
      .map((entry) => entry.applicationTypeId)
      .filter((id): id is string => Boolean(id)),
  );
  return [
    fallbackCategories[0]!,
    ...applicationTypes.value
      .filter(
        (type) => type.status === 1 && availableApplicationTypeIds.has(type.id),
      )
      .map((type) => ({
        description: type.description,
        icon: type.icon,
        key: type.id,
        label: type.typeName,
      })),
  ];
});

const recommendedEntries = computed(() =>
  publishedEntries.value
    .filter((entry) => entry.meta.recommended)
    .sort(
      (left, right) =>
        (right.config.usageCount ?? 0) - (left.config.usageCount ?? 0) ||
        left.meta.label.localeCompare(right.meta.label, 'zh-CN'),
    )
    .slice(0, 3),
);

/**
 * 资源申请首页只保留申请入口；旧记录列表通过历史参数兼容已有书签和问题排查。
 */
const showApplicationHistory = computed(() => route.query.history === '1');

const visibleEntries = computed(() =>
  publishedEntries.value.filter(
    (entry) =>
      activeApplicationTypeId.value === 'all' ||
      entry.applicationTypeId === activeApplicationTypeId.value,
  ),
);

const APPLICATION_ENTRY_PAGE_SIZE = 6;

const filteredEntries = computed(() => {
  const query = entryKeyword.value.trim().toLowerCase();
  if (!query) return visibleEntries.value;

  return visibleEntries.value.filter((entry) =>
    [
      entry.config.name,
      entry.definitionCode,
      entry.meta.description,
      entry.meta.label,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(query),
  );
});

const paginatedEntries = computed(() => {
  const start = (entryPage.value - 1) * APPLICATION_ENTRY_PAGE_SIZE;
  return filteredEntries.value.slice(
    start,
    start + APPLICATION_ENTRY_PAGE_SIZE,
  );
});

watch([activeApplicationTypeId, entryKeyword], () => {
  if (!isApplyingRoute.value) entryPage.value = 1;
});

watch(
  () => filteredEntries.value.length,
  (total) => {
    const lastPage = Math.max(
      1,
      Math.ceil(total / APPLICATION_ENTRY_PAGE_SIZE),
    );
    if (entryPage.value > lastPage) entryPage.value = lastPage;
  },
);

watch(categories, (availableCategories) => {
  if (
    !availableCategories.some(
      (category) => category.key === activeApplicationTypeId.value,
    )
  ) {
    activeApplicationTypeId.value = 'all';
  }
});

const activeEntryMeta = computed(() => {
  const operation = findAccountOperationEntry(selectedAccountOperation.value);
  if (operation) {
    return {
      ...typeMeta.payment,
      description: operation.description,
      icon: operation.icon,
      iconClass: operation.iconClass,
      label: operation.label,
    };
  }
  if (selectedApplicationDefinitionName.value) {
    const definition = backendApplicationDefinitions.value.find(
      (item) => item.id === selectedApplicationDefinitionId.value,
    );
    if (definition) {
      return {
        ...configMeta(activeBackendConfig.value!),
        description: resolvePrototypeApplicationDescription(
          definition.applicationCode,
          definition.description,
        ),
        icon: definition.icon,
        label: definition.applicationName,
      };
    }
  }
  return activeBackendConfig.value
    ? configMeta(activeBackendConfig.value)
    : typeMeta[form.type];
});

const currentCategoryLabel = computed(
  () =>
    categories.value.find(
      (category) => category.key === activeApplicationTypeId.value,
    )?.label ?? '全部申请',
);

const filteredApplications = computed(() => {
  const query = keyword.value.trim().toLowerCase();
  return applications.value.filter(
    (item) =>
      (activeType.value === 'all' || item.type === activeType.value) &&
      (statusFilter.value === 'all' || item.status === statusFilter.value) &&
      (!query ||
        [item.id, item.title, item.project, item.requester, item.description]
          .join(' ')
          .toLowerCase()
          .includes(query)),
  );
});

const historyPagination = computed<TablePaginationConfig>(() => ({
  current: historyPage.value,
  pageSize: historyPageSize.value,
  pageSizeOptions: ['8', '20', '50', '100'],
  showSizeChanger: true,
  total: filteredApplications.value.length,
}));

const paginatedHistoryApplications = computed(() => {
  const start = (historyPage.value - 1) * historyPageSize.value;
  return filteredApplications.value.slice(start, start + historyPageSize.value);
});

function handleHistoryTableChange(next: TablePaginationConfig) {
  const nextPageSize = next.pageSize ?? historyPageSize.value;
  historyPage.value =
    nextPageSize === historyPageSize.value ? (next.current ?? 1) : 1;
  historyPageSize.value = nextPageSize;
}

function changeHistoryPage(nextPage: number) {
  historyPage.value = nextPage;
}

watch([keyword, statusFilter, activeType], () => {
  if (!isApplyingRoute.value) historyPage.value = 1;
});

watch([() => filteredApplications.value.length, historyPageSize], ([total]) => {
  const lastPage = Math.max(1, Math.ceil(total / historyPageSize.value));
  if (historyPage.value > lastPage) historyPage.value = lastPage;
});

const columns = [
  { key: 'application', title: '申请单', width: '28%' },
  { key: 'ownership', title: '归属与申请人', width: '24%' },
  { key: 'approval', title: '审批状态', width: '21%' },
  { key: 'createdAt', title: '申请时间', width: '14%' },
  { key: 'actions', title: '操作', width: '13%' },
];

const formSchema = computed(() => applicationFormSchemaService.get(form.type));

function schemaHasField(
  key:
    | 'amount'
    | 'currency'
    | 'platform'
    | 'quantity'
    | 'resourceAssignee'
    | 'resourceTeam',
) {
  return formSchema.value.fields.some((field) => field.key === key);
}

const showAmountField = computed(() => schemaHasField('amount'));
const showCurrencyField = computed(() => schemaHasField('currency'));
const showPlatformField = computed(() => schemaHasField('platform'));
const showQuantityField = computed(() => schemaHasField('quantity'));
const showResourceAssigneeField = computed(() =>
  schemaHasField('resourceAssignee'),
);
const showResourceTeamField = computed(() => schemaHasField('resourceTeam'));

function resetForm(type: ApplicationType) {
  Object.assign(form, {
    amount: undefined,
    ccUsers: [],
    currency: 'USD',
    description: '',
    platform: type === 'account' ? 'PERSONAL' : '',
    project: '',
    projectId: '',
    quantity: 1,
    resourceAssigneeId: '',
    resourceAssigneeName: '',
    resourceTeamId: '',
    resourceTeamName: '',
    sourceTaskId: '',
    specifications: '',
    title: '',
    type,
  });
  resetApprovalNodes(type);
  editingId.value = undefined;
}

function handleResourceAssigneeChange(
  assigneeId: string | string[] | undefined,
  user?: { label?: string },
) {
  form.resourceAssigneeId = Array.isArray(assigneeId)
    ? (assigneeId[0] ?? '')
    : (assigneeId ?? '');
  form.resourceAssigneeName = user?.label ?? '';
}

function initializeApplicationEntry(entry: ApplicationEntry) {
  const { config, definitionCode, definitionId, meta, operationType } = entry;
  selectedConfigType.value = config.assetType;
  selectedApplicationDefinitionId.value = definitionId;
  selectedApplicationDefinitionCode.value = definitionCode;
  selectedApplicationDefinitionName.value = meta.label;
  selectedAccountOperation.value = operationType;
  resetForm(meta.applicationType);
  if (config.assetType === 'PERSONAL' || config.assetType === 'BM') {
    form.platform = config.assetType;
  }
  resetDynamicForm();
  if (operationType) dynamicFormData.operationType = operationType;
  formMode.value = true;
  if (config.formSchema.some((field) => field.optionSource === 'ad-accounts')) {
    void loadAdAccountOptions().catch(() => {
      // 接口层已展示错误；保留上一次成功加载的账户选项供用户重试。
    });
  }
  if (config.formSchema.some((field) => field.optionSource === 'channels')) {
    void loadChannelOptions().catch(() => {
      // 接口层已展示错误；保留上一次成功加载的渠道选项供用户重试。
    });
  }
  window.scrollTo({ behavior: 'smooth', top: 0 });
}

/** 从申请首页进入独立填写页，并通过申请编码定位对应配置。 */
function openApplicationEntry(entry: ApplicationEntry) {
  void router.push({
    path: '/workbench/applications/create',
    query: {
      applicationCode: entry.definitionCode ?? entry.config.assetType,
      new: '1',
    },
  });
}

function loadDraft(value: unknown) {
  const record = value as ResourceApplication;
  const configType = record.platform as ApprovalApplicationType | undefined;
  const matchingConfig = backendConfigs.value.find(
    (item) => item.assetType === configType,
  );
  selectedConfigType.value =
    matchingConfig?.assetType ??
    publishedConfigs.value.find(
      (item) => configMeta(item).applicationType === record.type,
    )?.assetType ??
    'PERSONAL';
  selectedAccountOperation.value =
    selectedConfigType.value === 'ACCOUNT_OPERATION'
      ? findAccountOperationEntry(record.formData?.operationType)?.operationType
      : undefined;
  selectedApplicationDefinitionId.value =
    String(record.formData?.applicationDefinitionId ?? '').trim() || undefined;
  selectedApplicationDefinitionCode.value =
    String(record.formData?.applicationCode ?? '').trim() || undefined;
  selectedApplicationDefinitionName.value =
    String(record.formData?.applicationName ?? '').trim() || record.title;
  resetDynamicForm();
  Object.assign(dynamicFormData, record.formData ?? {});
  Object.assign(form, {
    amount: record.amount,
    approvalNodes: record.approvalNodes.map((node) => ({ ...node })),
    ccUsers: [...record.ccUsers],
    currency: record.currency ?? 'USD',
    description: record.description,
    platform: record.platform ?? '',
    project: record.project,
    projectId: record.projectId ?? '',
    quantity: record.quantity ?? 1,
    resourceAssigneeId: record.resourceRequest?.assigneeId ?? '',
    resourceAssigneeName: record.resourceRequest?.assigneeName ?? '',
    resourceTeamId: record.resourceRequest?.teamId ?? '',
    resourceTeamName: record.resourceRequest?.teamName ?? '',
    specifications: '',
    title: record.title,
    type: record.type,
    sourceTaskId: record.sourceTaskId ?? '',
  });
  editingId.value = record.id;
  formMode.value = true;
  window.scrollTo({ behavior: 'smooth', top: 0 });
}

function editDraft(value: unknown) {
  const record = value as ResourceApplication;
  if (isCreatePage.value) {
    loadDraft(record);
    return;
  }
  void router.push({
    path: '/workbench/applications/create',
    query: { editId: record.id },
  });
}

function showDetails(value: unknown) {
  detailActiveTab.value = 'info';
  detailRecord.value = value as ResourceApplication;
}

/** 重提单在工作区新标签查看来源审批，避免详情弹窗覆盖当前填写上下文。 */
function openSourceApplicationDetail(applicationId: string) {
  void router.push({
    path: `/workbench/approvals/${encodeURIComponent(applicationId)}`,
  });
}

function detailConfiguredFields(record: ResourceApplication) {
  return (record.formSchema ?? []) as DynamicFormField[];
}

function optionSnapshotBase(fieldKey: string) {
  if (fieldKey.endsWith('Ids')) return fieldKey.slice(0, -3);
  if (fieldKey.endsWith('Id')) return fieldKey.slice(0, -2);
  return fieldKey;
}

function detailConfiguredValue(
  record: ResourceApplication,
  field: DynamicFormField,
) {
  const value = record.formData?.[field.key];
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
  return formatConfiguredValue(field, value);
}

function approvalRoleLabel(value: unknown) {
  const role = (value as ResourceApplication)
    .approvalRole as ApplicationApprovalRole;
  return approvalRoleMeta[role].label;
}

function closeForm() {
  resubmissionSourceApplicationId.value = undefined;
  if (isCreatePage.value) {
    void router.push('/workbench/applications');
    return;
  }
  formMode.value = false;
  editingId.value = undefined;
  selectedAccountOperation.value = undefined;
  selectedApplicationDefinitionId.value = undefined;
  selectedApplicationDefinitionCode.value = undefined;
  selectedApplicationDefinitionName.value = undefined;
}

function formatNow() {
  return new Intl.DateTimeFormat('zh-CN', {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
    .format(new Date())
    .replaceAll('/', '-');
}

function dynamicValidationError(field: DynamicFormField) {
  if (field.type === 'section') return '';
  const value = String(dynamicFormData[field.key] ?? '')
    .replaceAll('：', ':')
    .replaceAll('；', ';');
  if (field.maxLength && value.length > field.maxLength) {
    return `${field.label}不能超过${field.maxLength}个字符`;
  }
  if (!value.trim() || !field.validationRule) return '';
  if (field.validationRule === 'digit-list') {
    const ids = value
      .split(';')
      .map((item) => item.trim())
      .filter(Boolean);
    return ids.length > 0 && ids.every((id) => /^\d+$/.test(id))
      ? ''
      : `${field.label}仅支持数字，多个值请用分号分隔`;
  }
  if (field.validationRule === 'email') {
    return /^[^\s@]+@[^\s@][^\s.@]*\.[^\s@]+$/.test(value)
      ? ''
      : `${field.label}格式不正确`;
  }
  if (field.validationRule === 'url') {
    try {
      const url = new URL(value);
      return ['http:', 'https:'].includes(url.protocol)
        ? ''
        : `${field.label}仅支持 http 或 https 链接`;
    } catch {
      return `${field.label}格式不正确`;
    }
  }
  if (field.validationRule === 'positive-money') {
    return Number(value) > 0 ? '' : `${field.label}必须大于 0`;
  }
  const pixels = value
    .split(/[;\n\r]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  const invalidIndex = pixels.findIndex((pixel) => {
    const parts = pixel.split(':').map((item) => item.trim());
    return parts.length !== 2 || !parts[0] || !parts[1];
  });
  return invalidIndex === -1
    ? ''
    : `${field.label}第 ${invalidIndex + 1} 项格式错误，请按“像素名称:像素ID”填写`;
}

function isDynamicFieldEmpty(field: DynamicFormField) {
  if (field.type === 'section') return false;
  const value = dynamicFormData[field.key];
  if (Array.isArray(value)) return value.length === 0;
  return !String(value ?? '').trim();
}

/** 按旧 MPower 表单规则规范化动态字段，保证中英文标点与前后空格的入库口径一致。 */
function normalizedDynamicFormValues() {
  const result: Record<string, unknown> = {};
  for (const field of dynamicFields.value) {
    if (field.type === 'section') continue;
    const sourceValue = dynamicFormData[field.key];
    let normalizedValue = sourceValue;
    if (
      field.validationRule &&
      sourceValue !== null &&
      sourceValue !== undefined
    ) {
      const normalized = String(sourceValue)
        .replaceAll('：', ':')
        .replaceAll('；', ';');
      if (field.validationRule === 'digit-list') {
        normalizedValue = normalized
          .split(';')
          .map((item) => item.trim())
          .filter(Boolean)
          .join(';');
      } else if (field.validationRule === 'pixel-list') {
        normalizedValue = normalized
          .split(/[;\n\r]+/)
          .map((item) =>
            item
              .split(':')
              .map((part) => part.trim())
              .join(':'),
          )
          .filter(Boolean)
          .join(';');
      }
    }
    result[field.key] = normalizedValue;

    if (
      !field.optionSource ||
      field.optionSource === 'custom' ||
      !['multi-select', 'select'].includes(field.type)
    ) {
      continue;
    }
    const selectedValues = Array.isArray(sourceValue)
      ? sourceValue.map(String)
      : [String(sourceValue ?? '')];
    const selectedLabels = dynamicOptions(field)
      .filter((option) => selectedValues.includes(String(option.value)))
      .map((option) => option.label);
    const snapshotBase = optionSnapshotBase(field.key);
    result[`${snapshotBase}${Array.isArray(sourceValue) ? 'Names' : 'Name'}`] =
      Array.isArray(sourceValue) ? selectedLabels : (selectedLabels[0] ?? '');
  }
  return result;
}

function formatConfiguredValue(field: DynamicFormField, value: unknown) {
  if (value === undefined || value === null || value === '') return '-';
  if (field.type === 'date-range' && Array.isArray(value)) {
    const [startDate, endDate] = value.map(String);
    return startDate && endDate ? `${startDate} 至 ${endDate}` : '-';
  }
  const values = Array.isArray(value) ? value.map(String) : [String(value)];
  if (['multi-select', 'select'].includes(field.type)) {
    const labels = dynamicOptions(field)
      .filter((option) => values.includes(String(option.value)))
      .map((option) => option.label);
    if (labels.length > 0) return labels.join('、');
  }
  return values.join('、');
}

function buildApplicationTitle() {
  return activeEntryMeta.value.label.slice(0, 100);
}

function validateForSave(status: 'draft' | 'pending') {
  if (status === 'draft') return true;
  if (!activeBackendConfig.value) {
    message.warning('当前资源类型尚未发布动态表单');
    return false;
  }
  // 旧审批配置生成的兼容入口没有申请定义 ID，但仍是申请中心可正常发起的入口。
  if (
    backendApplicationDefinitions.value.length > 0 &&
    !selectedApplicationDefinitionId.value
  ) {
    message.warning('请返回申请中心选择具体申请');
    return false;
  }
  const missingField = dynamicFields.value.find(
    (field) => isDynamicFieldRequired(field) && isDynamicFieldEmpty(field),
  );
  if (missingField) {
    message.warning(`请填写${missingField.label}`);
    return false;
  }
  const invalidMessage = dynamicFields.value
    .map((field) => dynamicValidationError(field))
    .find(Boolean);
  if (invalidMessage) {
    message.warning(invalidMessage);
    return false;
  }
  if (isMyAssetAccountApplicationRoute()) {
    if (dynamicAdAccountOptionsLoading.value) {
      message.warning('正在核验本人广告账户，请稍后提交');
      return false;
    }
    const ownedAccountIds = new Set(
      dynamicAdAccountOptions.value.map((option) => option.value),
    );
    const selectedAccountIds = dynamicFields.value
      .filter((field) => field.optionSource === 'ad-accounts')
      .flatMap((field) => {
        const value = dynamicFormData[field.key];
        return Array.isArray(value) ? value : [value];
      })
      .map((value) => String(value ?? '').trim())
      .filter(Boolean);
    if (
      selectedAccountIds.some((accountId) => !ownedAccountIds.has(accountId))
    ) {
      message.error('只能选择本人已分配的广告账户，请重新选择');
      return false;
    }
  }
  if (!activeBackendConfig.value && !form.title.trim()) {
    message.warning('请填写申请标题');
    return false;
  }
  if (!activeBackendConfig.value && showPlatformField.value && !form.platform) {
    message.warning('请选择申请平台');
    return false;
  }
  if (
    !activeBackendConfig.value &&
    showAmountField.value &&
    (!form.amount || form.amount <= 0)
  ) {
    message.warning('请填写有效的付款金额');
    return false;
  }
  if (
    !activeBackendConfig.value &&
    showResourceAssigneeField.value &&
    (!form.resourceAssigneeId.trim() || !form.resourceAssigneeName.trim())
  ) {
    message.warning('请选择具有稳定用户 ID 的资源使用人');
    return false;
  }
  if (
    !activeBackendConfig.value &&
    showResourceTeamField.value &&
    (!form.resourceTeamId.trim() || !form.resourceTeamName.trim())
  ) {
    message.warning('请填写资源使用团队的稳定 ID 和名称');
    return false;
  }
  if (
    form.approvalNodes.length === 0 ||
    form.approvalNodes.some((node) => !node.approver.trim())
  ) {
    message.warning('请完整配置审批节点和审批人');
    return false;
  }
  return true;
}

async function saveApplication(status: 'draft' | 'pending') {
  if (!validateForSave(status)) return;
  if (!currentUserId.value) {
    message.error('当前用户缺少稳定用户 ID，不能创建或更新申请');
    return;
  }

  submitting.value = true;
  try {
    if (
      status === 'pending' &&
      selectedConfigType.value === 'ACCOUNT_OPENING'
    ) {
      const selectedChannelId = String(dynamicFormData.channelId ?? '').trim();
      const currentOptions = await getAccountOpeningChannelOptions();
      resolvedChannelOptions.value = currentOptions;
      if (
        !currentOptions.some((option) => option.value === selectedChannelId)
      ) {
        message.warning('所选渠道未上架或已停用，请重新选择可开户渠道');
        dynamicFormData.channelId = '';
        return;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
    const existing = editingId.value
      ? applications.value.find((item) => item.id === editingId.value)
      : undefined;
    const approvalRole = approvalRoleForType(form.type);
    const firstApprovalNode = form.approvalNodes[0];
    const configuredFormData = normalizedDynamicFormValues();
    const configuredProjectId = String(configuredFormData.projectId ?? '');
    const configuredProjectName = String(configuredFormData.projectName ?? '');
    const sourceContext = form.sourceTaskId
      ? await taskService.resolveResourceApplicationContext({
          projectId: configuredProjectId,
          projectName: configuredProjectName,
          requesterId: currentUserId.value,
          requesterName: currentUserName.value,
          sourceTaskId: form.sourceTaskId,
        })
      : undefined;
    const requestAssetType = selectedConfigType.value;
    const backendApplication =
      status === 'pending'
        ? await assetFlowApi.createApplication({
            assetType: requestAssetType,
            formData: {
              ...configuredFormData,
              applicationDefinitionId:
                selectedApplicationDefinitionId.value || undefined,
              configCategory: activeBackendConfig.value?.category,
              configName: activeBackendConfig.value?.name,
              sourceTaskId: form.sourceTaskId || undefined,
            },
            sourceApplicationId: resubmissionSourceApplicationId.value,
            title: buildApplicationTitle(),
          })
        : undefined;
    if (backendApplication) {
      syncBackendApplications([backendApplication]);
      closeForm();
      activeType.value = form.type;
      statusFilter.value = 'pending';
      editingId.value = undefined;
      message.success(
        backendApplication.sourceApplicationId
          ? '申请已重新提交，已创建新的审批单'
          : '申请已提交，已进入审批流程',
      );
      return;
    }
    let recordId: string | undefined;
    if (!recordId) {
      recordId =
        status === 'draft'
          ? (existing?.id ?? `DRAFT-${Date.now()}`)
          : `REQ-${Date.now()}`;
    }
    const record: ResourceApplication = {
      approvalNodes: form.approvalNodes.map((node, index) => ({
        ...node,
        id: `NODE-${existing?.id ?? Date.now()}-${index + 1}`,
        status: index === 0 ? 'pending' : 'waiting',
      })),
      approvalRecords: existing?.approvalRecords ?? [],
      approvalRole: firstApprovalNode?.role ?? approvalRole,
      approver:
        firstApprovalNode?.approver ?? approvalRoleMeta[approvalRole].approver,
      ccUsers: [...form.ccUsers],
      comments: existing?.comments ?? [],
      handlerApprovalNodeId: activeBackendConfig.value?.handlerApprovalNodeId,
      handlerId: activeBackendConfig.value?.handlerId,
      handlerName: activeBackendConfig.value?.handlerName,
      handlerSource: activeBackendConfig.value?.handlerSource,
      id: String(recordId),
      type: form.type,
      title: form.title.trim() || `${typeMeta[form.type].label}（未命名草稿）`,
      project: form.project || '未关联归属',
      requester:
        userStore.userInfo?.realName ||
        userStore.userInfo?.full_name ||
        '当前用户',
      createdAt: formatNow(),
      updatedAt: formatNow(),
      currency: showCurrencyField.value ? form.currency : undefined,
      status,
      description: [form.description.trim(), form.specifications.trim()]
        .filter(Boolean)
        .join('；'),
      amount: form.amount,
      platform: selectedConfigType.value,
      projectId: sourceContext?.projectId || form.projectId || undefined,
      requesterId: currentUserId.value,
      requesterName: currentUserName.value,
      resourceRequest:
        !activeBackendConfig.value && showResourceAssigneeField.value
          ? {
              assigneeId: form.resourceAssigneeId.trim(),
              assigneeName: form.resourceAssigneeName.trim(),
              teamId: form.resourceTeamId.trim(),
              teamName: form.resourceTeamName.trim(),
            }
          : undefined,
      quantity: form.quantity,
      sourceTaskId: sourceContext?.sourceTaskId,
    };

    if (existing && existing.id !== record.id) {
      applicationService.remove(existing.id);
    }
    applicationService.save(record);

    closeForm();
    activeType.value = form.type;
    statusFilter.value = status;
    editingId.value = undefined;
    message.success(
      status === 'draft'
        ? '草稿已保存，可稍后继续填写'
        : '申请已提交，审批中心将同步处理状态',
    );
  } finally {
    submitting.value = false;
  }
}

function withdraw(value: unknown) {
  const record = value as ResourceApplication;
  Modal.confirm({
    title: record.status === 'draft' ? '确认删除草稿？' : '确认撤回申请？',
    content: `操作后“${record.title}”将从申请记录中移除。`,
    okText: record.status === 'draft' ? '删除草稿' : '确认撤回',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => {
      applicationService.remove(record.id);
      message.success(record.status === 'draft' ? '草稿已删除' : '申请已撤回');
    },
  });
}

function canResubmit(record: Record<string, unknown> | ResourceApplication) {
  const application = record as ResourceApplication;
  return (
    application.status === 'rejected' &&
    (application.requesterId
      ? application.requesterId === currentUserId.value
      : application.requester === currentUserName.value)
  );
}

function openResubmit(value: unknown) {
  const record = value as ResourceApplication;
  const applicationCode = String(
    record.formData?.applicationCode ?? record.platform ?? '',
  ).trim();
  if (!applicationCode) {
    message.warning('该申请缺少申请入口信息，暂时无法重新提交');
    return;
  }
  void router.push({
    path: '/workbench/applications/create',
    query: {
      applicationCode,
      new: '1',
      resubmitId: record.id,
    },
  });
}

async function applySourceContextFromRoute() {
  if (isChannelScopedApplication.value) return false;
  const sourceTaskId =
    typeof route.query.sourceTaskId === 'string'
      ? route.query.sourceTaskId.trim()
      : '';
  const projectId =
    typeof route.query.projectId === 'string'
      ? route.query.projectId.trim()
      : '';
  const projectName =
    typeof route.query.projectName === 'string'
      ? route.query.projectName.trim()
      : '';
  if (!projectId || !projectName) return false;

  const projectField = applicationScopedFormSchema.value.find(
    (field) => field.key === 'projectId' && field.type !== 'section',
  );
  if (!sourceTaskId) {
    form.project = projectName;
    form.projectId = projectId;
    if (projectField) dynamicFormData.projectId = projectId;
    if (form.type === 'payment') {
      const amount = Number(route.query.amount);
      if (Number.isFinite(amount) && amount > 0) form.amount = amount;
      form.title = `${projectName} 结项结算申请`;
      form.description = `发起 ${projectName} 的项目结项结算审批。`;
    }
    return true;
  }
  if (!currentUserId.value) {
    message.error('当前用户缺少稳定用户 ID，不能使用任务上下文发起申请');
    return false;
  }
  try {
    const context = await taskService.resolveResourceApplicationContext({
      projectId,
      projectName,
      requesterId: currentUserId.value,
      requesterName: currentUserName.value,
      sourceTaskId,
    });
    form.project = context.projectName;
    form.projectId = context.projectId;
    if (projectField) dynamicFormData.projectId = context.projectId;
    form.sourceTaskId = context.sourceTaskId;
    return true;
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '任务来源上下文无效',
    );
    return false;
  }
}

function applyAdAccountContextFromRoute() {
  const accountId = routeQueryText(route.query.adAccountId);
  if (!accountId) return false;
  const accountField = applicationScopedFormSchema.value.find(
    (field) => field.optionSource === 'ad-accounts',
  );
  if (!accountField) return false;
  dynamicFormData[accountField.key] =
    accountField.type === 'multi-select' ? [accountId] : accountId;
  ensureRouteAdAccountOption();
  return true;
}

let lastHandledApplicationRoute = '';

/** 根据深链参数打开指定申请，并把来源广告账户回填到动态表单。 */
async function openApplicationFromRoute() {
  const editId = routeQueryText(route.query.editId);
  if (editId) {
    const draft = applications.value.find((item) => item.id === editId);
    if (!draft) {
      message.warning('未找到待继续填写的申请草稿');
      return false;
    }
    loadDraft(draft);
    return true;
  }
  if (route.query.new !== '1' || applicationListLoading.value) return false;
  const applicationCode = routeQueryText(route.query.applicationCode);
  const resubmitId = routeQueryText(route.query.resubmitId);
  const routeSignature = [
    applicationCode,
    routeQueryText(route.query.adAccountId),
    routeQueryText(route.query.adAccountName),
    routeQueryText(route.query.sourceTaskId),
    routeQueryText(route.query.projectId),
    resubmitId,
  ].join('|');
  if (lastHandledApplicationRoute === routeSignature) return true;

  const operation = findAccountOperationEntryByCode(applicationCode);
  const entry = applicationCode
    ? publishedEntries.value.find(
        (item) =>
          item.definitionCode === applicationCode ||
          item.config.assetType === applicationCode ||
          (operation && item.operationType === operation.operationType),
      )
    : (recommendedEntries.value[0] ?? publishedEntries.value[0]);
  if (!entry) {
    message.warning('对应申请入口当前未启用，请联系管理员检查审批配置');
    return false;
  }

  initializeApplicationEntry(entry);
  if (resubmitId) {
    const source = applications.value.find((item) => item.id === resubmitId);
    if (!source || !canResubmit(source)) {
      message.warning('仅可重新提交本人已驳回的申请');
      return false;
    }
    // 仅回填动态表单字段；审批记录和节点属于旧单，不能复制到新单。
    Object.assign(dynamicFormData, source.formData ?? {});
    resubmissionSourceApplicationId.value = source.id;
  } else {
    resubmissionSourceApplicationId.value = undefined;
  }
  applyAdAccountContextFromRoute();
  await applySourceContextFromRoute();
  formMode.value = true;
  lastHandledApplicationRoute = routeSignature;
  return true;
}

onBeforeMount(() => {
  if (isCreatePage.value || route.query.new !== '1') return;

  // 兼容已收藏或由旧版本生成的链接，统一切换到独立填写页。
  void router.replace({
    path: '/workbench/applications/create',
    query: route.query,
  });
});

async function loadChannelOptions() {
  if (channelOptionsLoading.value) return;

  channelOptionsLoading.value = true;
  try {
    // 动态表单保存渠道管理的稳定 ID，渠道名称仅用于选项展示和快照。
    resolvedChannelOptions.value =
      selectedConfigType.value === 'ACCOUNT_OPENING'
        ? await getAccountOpeningChannelOptions()
        : await getChannelOptions();
  } finally {
    channelOptionsLoadAttempted.value = true;
    channelOptionsLoading.value = false;
  }
}

/**
 * 仅在当前动态表单展示项目字段时加载项目选项，避免停留在申请列表时请求完整项目集。
 */
async function loadProjectOptions() {
  if (projectOptionsLoaded.value || projectOptionsLoading.value) return;

  projectOptionsLoading.value = true;
  try {
    const options = await projectService.listOptions();
    if (options.length > 0) {
      resolvedProjectOptions.value = options.map((project) => ({
        label: project.name,
        projectId: project.id,
        value: project.name,
      }));
    }
  } catch {
    // 项目读模型不可用时保留静态兼容选项，接口层会统一提示具体错误。
  } finally {
    projectOptionsLoaded.value = true;
    projectOptionsLoading.value = false;
  }
}

async function loadApplicationWorkspace() {
  applicationListLoading.value = true;
  try {
    const shouldLoadApplications =
      showApplicationHistory.value ||
      Boolean(routeQueryText(route.query.resubmitId));
    const [configs, definitions, types, backendApplications] =
      await Promise.all([
        assetFlowApi.configs(),
        assetFlowApi.applicationDefinitions().catch(() => []),
        assetFlowApi.applicationTypes().catch(() => []),
        shouldLoadApplications ? assetFlowApi.applications() : undefined,
      ]);
    backendConfigs.value = configs.map((config) =>
      normalizeApplicationConfig(config),
    );
    if (!backendConfigs.value.some((config) => config.assetType === 'TG')) {
      backendConfigs.value.push(socialApplicationFallbackConfig);
    }
    backendApplicationDefinitions.value = definitions;
    applicationTypes.value = types;
    if (backendApplications) syncBackendApplications(backendApplications);
  } catch {
    // 后端配置暂不可用时保留社交资产申请入口，恢复后仍以服务端配置为准。
    backendConfigs.value = [socialApplicationFallbackConfig];
  } finally {
    applicationListLoading.value = false;
  }
  await openApplicationFromRoute();
}

onMounted(loadApplicationWorkspace);

let hasActivatedApplicationsPage = false;
onActivated(() => {
  const shouldRefreshList = hasActivatedApplicationsPage && !formMode.value;
  hasActivatedApplicationsPage = true;
  if (shouldRefreshList) void loadApplicationWorkspace();
  else void openApplicationFromRoute();
  if (formMode.value) loadRequiredDynamicOptions(dynamicFields.value);
  if (channelOptionsLoadAttempted.value) {
    void loadChannelOptions().catch(() => {
      // 保留上一次成功加载的渠道，接口层会统一展示错误提示。
    });
  }
  if (
    formMode.value &&
    activeBackendConfig.value?.formSchema.some(
      (field) => field.optionSource === 'ad-accounts',
    )
  ) {
    void loadAdAccountOptions().catch(() => {
      // 保留上一次成功加载的账户选项，避免激活页面时清空用户已选内容。
    });
  }
});

watch(
  () => route.fullPath,
  () => {
    void openApplicationFromRoute();
  },
);

watch(applicationListLoading, (isLoading) => {
  if (!isLoading) {
    // 路由先于审批配置加载完成时，必须在配置就绪后重新按深链选择申请入口。
    void openApplicationFromRoute();
  }
});

watch(
  [formMode, dynamicFields],
  ([isFormMode, fields]) => {
    if (!isFormMode) return;
    loadRequiredDynamicOptions(fields);
  },
  { immediate: true },
);
</script>

<template>
  <Page
    auto-content-height
    class="bg-muted/40"
    :content-class="formMode ? 'p-0' : undefined"
  >
    <ListLoading v-if="isCreatePage && applicationListLoading" />

    <div v-else-if="!formMode" class="w-full min-w-0 space-y-4">
      <BusinessPageHeader
        compact
        description="按业务用途选择申请入口，提交后由审批中心统一跟进处理状态。"
        icon="lucide:file-plus-2"
        title="资源申请"
      />

      <ListLoading v-if="applicationListLoading" />
      <section
        v-show="!applicationListLoading"
        aria-labelledby="recommended-heading"
        :aria-busy="applicationListLoading"
      >
        <div class="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2
              id="recommended-heading"
              class="text-foreground m-0 text-lg font-semibold"
            >
              推荐使用
            </h2>
          </div>
        </div>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          <button
            v-for="entry in recommendedEntries"
            :key="entry.key"
            type="button"
            class="border-border bg-card hover:border-foreground/30 hover:bg-muted focus-visible:ring-ring group flex min-h-20 items-center gap-4 rounded-[var(--adpulse-radius)] border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2"
            :aria-label="`发起${entry.meta.label}`"
            @click="openApplicationEntry(entry)"
          >
            <span
              class="border-border bg-muted text-foreground flex h-12 w-12 shrink-0 items-center justify-center rounded-[var(--adpulse-radius)] border text-xl"
            >
              <IconifyIcon :icon="entry.meta.icon" aria-hidden="true" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="text-foreground block text-base font-semibold">
                {{ entry.meta.label }}
              </span>
              <span class="text-muted-foreground mt-1 block text-xs">
                已发起 {{ entry.config.usageCount ?? 0 }} 次
              </span>
            </span>
            <IconifyIcon
              icon="lucide:chevron-right"
              class="text-muted-foreground group-hover:text-foreground shrink-0 text-lg transition-colors"
            />
          </button>
        </div>
      </section>

      <section
        v-show="!applicationListLoading"
        aria-labelledby="all-applications-heading"
        :aria-busy="applicationListLoading"
      >
        <div class="mb-3">
          <h2
            id="all-applications-heading"
            class="text-foreground m-0 text-lg font-semibold"
          >
            全部申请
          </h2>
          <p class="text-muted-foreground mb-0 mt-1 text-sm">
            按资源类型选择对应申请表
          </p>
        </div>

        <Card :body-style="{ padding: 0 }" class="overflow-hidden">
          <div class="grid grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)]">
            <nav
              aria-label="资源申请分类"
              class="border-border bg-muted border-b p-3 lg:border-b-0 lg:border-r lg:p-4"
            >
              <div
                class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:flex lg:flex-col"
              >
                <button
                  v-for="category in categories"
                  :key="category.key"
                  type="button"
                  class="focus-visible:ring-ring flex min-h-12 min-w-0 items-center gap-3 rounded-lg px-3 py-2 text-left transition focus-visible:outline-none focus-visible:ring-2 lg:w-full"
                  :class="
                    activeApplicationTypeId === category.key
                      ? 'bg-card text-foreground'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                  "
                  :aria-current="
                    activeApplicationTypeId === category.key
                      ? 'page'
                      : undefined
                  "
                  @click="activeApplicationTypeId = category.key"
                >
                  <IconifyIcon :icon="category.icon" class="shrink-0 text-lg" />
                  <span>
                    <span class="block text-sm font-medium">{{
                      category.label
                    }}</span>
                    <span class="hidden text-xs opacity-70 lg:block">{{
                      category.description
                    }}</span>
                  </span>
                </button>
              </div>
            </nav>

            <div class="flex min-w-0 flex-col p-4">
              <h3 class="text-foreground m-0 text-base font-semibold">
                {{ currentCategoryLabel }}
              </h3>
              <p class="text-muted-foreground mb-4 mt-1 text-sm">
                选择一项进入申请表，按审批配置填写对应的资源申请信息。
              </p>
              <label
                class="text-foreground mb-2 block text-sm font-medium"
                for="application-entry-search"
              >
                搜索申请
              </label>
              <Input
                id="application-entry-search"
                v-model:value="entryKeyword"
                allow-clear
                class="mb-4 w-full"
                placeholder="搜索申请名称、说明"
              >
                <template #prefix>
                  <IconifyIcon icon="lucide:search" aria-hidden="true" />
                </template>
              </Input>
              <div
                class="grid grid-cols-1 content-start gap-4 sm:grid-cols-2 xl:grid-cols-3"
              >
                <button
                  v-for="entry in paginatedEntries"
                  :key="entry.key"
                  type="button"
                  class="border-border bg-card hover:border-foreground/30 hover:bg-muted focus-visible:ring-ring group flex min-h-32 flex-col rounded-[var(--adpulse-radius)] border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2"
                  :aria-label="`发起${entry.meta.label}`"
                  @click="openApplicationEntry(entry)"
                >
                  <span class="flex w-full items-start gap-3">
                    <span
                      class="border-border bg-muted text-foreground flex h-10 w-10 shrink-0 items-center justify-center rounded-md border text-lg"
                    >
                      <IconifyIcon :icon="entry.meta.icon" aria-hidden="true" />
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="text-foreground block text-sm font-semibold">
                        {{ entry.meta.label }}
                      </span>
                      <span
                        class="text-muted-foreground mt-1 line-clamp-2 block text-xs leading-5"
                      >
                        {{ entry.meta.description }}
                      </span>
                    </span>
                  </span>
                  <span
                    class="text-foreground mt-auto flex w-full items-center justify-end gap-1 pt-3 text-sm font-medium"
                  >
                    发起申请
                    <IconifyIcon
                      icon="lucide:arrow-right"
                      class="transition-colors"
                    />
                  </span>
                </button>
                <div
                  v-if="!applicationListLoading && filteredEntries.length === 0"
                  class="border-border bg-muted text-muted-foreground rounded-[var(--adpulse-radius)] border border-dashed px-5 py-10 text-center text-sm sm:col-span-2 xl:col-span-3"
                >
                  该分类暂无已发布的审批配置
                </div>
              </div>
              <div
                class="border-border mt-4 flex flex-col gap-2 border-t pt-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <span class="text-muted-foreground text-sm">
                  共 {{ filteredEntries.length }} 项申请
                </span>
                <Pagination
                  v-model:current="entryPage"
                  :hide-on-single-page="true"
                  :page-size="APPLICATION_ENTRY_PAGE_SIZE"
                  :show-size-changer="false"
                  :total="filteredEntries.length"
                />
              </div>
            </div>
          </div>
        </Card>
      </section>

      <section
        v-if="showApplicationHistory"
        aria-labelledby="my-applications-heading"
      >
        <Card :body-style="{ padding: 0 }">
          <div class="border-b border-slate-100 p-4 sm:p-5">
            <div>
              <h2
                id="my-applications-heading"
                class="m-0 text-lg font-semibold text-slate-900"
              >
                我的申请
              </h2>
              <p class="mb-0 mt-1 text-sm text-slate-500">
                草稿、审批与资源交付状态统一留痕
              </p>
            </div>
            <div class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
              <Input
                v-model:value="keyword"
                allow-clear
                class="w-full"
                placeholder="搜索申请单、归属或申请人"
              >
                <template #prefix>
                  <IconifyIcon icon="lucide:search" class="text-slate-400" />
                </template>
              </Input>
              <Select
                v-model:value="statusFilter"
                :options="statusOptions"
                class="w-full"
              />
              <Select
                v-model:value="activeType"
                :options="[
                  { label: '全部类型', value: 'all' },
                  ...Object.entries(typeMeta).map(([value, item]) => ({
                    label: item.label,
                    value,
                  })),
                ]"
                class="w-full"
                size="large"
              />
            </div>
          </div>

          <div
            v-show="!applicationListLoading"
            class="hidden xl:block"
            :aria-busy="applicationListLoading"
          >
            <Table
              :columns="columns"
              :data-source="filteredApplications"
              :row-key="(record) => record.id"
              :pagination="historyPagination"
              class=""
              table-layout="fixed"
              @change="handleHistoryTableChange"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'application'">
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
                </template>
                <template v-else-if="column.key === 'ownership'">
                  <div class="line-clamp-2 text-sm text-slate-700">
                    {{ record.project }}
                  </div>
                  <div class="mt-1 text-xs text-slate-500">
                    申请人：{{ record.requester }}
                  </div>
                </template>
                <template v-else-if="column.key === 'approval'">
                  <Tag
                    :color="
                      statusMeta[record.status as ApplicationStatus].color
                    "
                    class="m-0"
                  >
                    {{ statusMeta[record.status as ApplicationStatus].label }}
                  </Tag>
                  <div
                    v-if="record.status !== 'draft'"
                    class="mt-1 line-clamp-2 text-xs text-slate-500"
                  >
                    {{ record.approver }} ·
                    {{ approvalRoleLabel(record) }}
                  </div>
                </template>
                <template v-else-if="column.key === 'createdAt'">
                  <span class="text-xs leading-5 text-slate-600">
                    {{ record.createdAt }}
                  </span>
                </template>
                <template v-else-if="column.key === 'actions'">
                  <div class="flex flex-wrap items-center gap-x-1">
                    <Button
                      v-if="record.status === 'draft'"
                      type="link"
                      @click="editDraft(record)"
                    >
                      继续填写
                    </Button>
                    <Button v-else type="link" @click="showDetails(record)">
                      详情
                    </Button>
                    <Button
                      v-if="canResubmit(record)"
                      type="link"
                      @click="openResubmit(record)"
                    >
                      补充并重提
                    </Button>
                    <Button
                      v-if="
                        record.status === 'pending' || record.status === 'draft'
                      "
                      danger
                      type="link"
                      @click="withdraw(record)"
                    >
                      {{ record.status === 'draft' ? '删除' : '撤回' }}
                    </Button>
                  </div>
                </template>
              </template>
            </Table>
          </div>

          <div
            v-show="!applicationListLoading"
            class="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 xl:hidden"
            :aria-busy="applicationListLoading"
          >
            <article
              v-for="record in paginatedHistoryApplications"
              :key="record.id"
              class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div class="flex items-start justify-between gap-3">
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
                <span class="text-xs text-slate-500">{{
                  record.createdAt
                }}</span>
              </div>

              <dl
                class="mb-0 mt-3 grid grid-cols-[64px_minmax(0,1fr)] gap-y-2 text-sm"
              >
                <dt class="text-slate-500">归属</dt>
                <dd class="m-0 break-words text-slate-700">
                  {{ record.project }}
                </dd>
                <dt class="text-slate-500">申请人</dt>
                <dd class="m-0 text-slate-700">{{ record.requester }}</dd>
                <template v-if="record.status !== 'draft'">
                  <dt class="text-slate-500">审批人</dt>
                  <dd class="m-0 text-slate-700">
                    {{ record.approver }} ·
                    {{ approvalRoleMeta[record.approvalRole].label }}
                  </dd>
                </template>
              </dl>

              <div
                class="mt-4 flex items-center justify-end gap-1 border-t border-slate-100 pt-3"
              >
                <Button
                  v-if="record.status === 'draft'"
                  type="link"
                  @click="editDraft(record)"
                >
                  继续填写
                </Button>
                <Button v-else type="link" @click="showDetails(record)">
                  查看详情
                </Button>
                <Button
                  v-if="canResubmit(record)"
                  type="link"
                  @click="openResubmit(record)"
                >
                  补充并重提
                </Button>
                <Button
                  v-if="
                    record.status === 'pending' || record.status === 'draft'
                  "
                  danger
                  type="link"
                  @click="withdraw(record)"
                >
                  {{ record.status === 'draft' ? '删除' : '撤回' }}
                </Button>
              </div>
            </article>

            <div
              v-if="
                !applicationListLoading && filteredApplications.length === 0
              "
              class="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-500 sm:col-span-2"
            >
              暂无符合条件的申请
            </div>
            <div
              v-if="filteredApplications.length > historyPageSize"
              class="flex justify-end sm:col-span-2"
            >
              <Pagination
                :current="historyPage"
                :page-size="historyPageSize"
                :show-size-changer="false"
                :total="filteredApplications.length"
                @change="changeHistoryPage"
              />
            </div>
          </div>
        </Card>
      </section>
    </div>

    <div v-else class="application-form-shell min-h-full bg-slate-50">
      <header
        class="application-form-header sticky z-10 border-b border-slate-200 bg-white/95 px-3 py-3 backdrop-blur sm:px-5"
      >
        <div
          class="grid w-full min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3 md:grid-cols-[180px_minmax(0,1fr)_260px]"
        >
          <Button type="text" class="justify-self-start" @click="closeForm">
            <template #icon><IconifyIcon icon="lucide:arrow-left" /></template>
            返回申请中心
          </Button>
          <div class="min-w-0 md:text-center">
            <div class="truncate text-base font-semibold text-slate-900">
              {{ activeEntryMeta.label }}
            </div>
          </div>
          <div class="col-span-2 flex justify-end gap-2 md:col-span-1">
            <Button
              :loading="submitting"
              type="primary"
              @click="saveApplication('pending')"
            >
              <template #icon><IconifyIcon icon="lucide:send" /></template>
              提交申请
            </Button>
          </div>
        </div>
      </header>

      <main class="w-full min-w-0 p-4">
        <div class="mb-5 flex items-start gap-3">
          <span
            class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-xl text-slate-900 shadow-sm"
          >
            <IconifyIcon :icon="activeEntryMeta.icon" aria-hidden="true" />
          </span>
          <div>
            <h1 class="m-0 text-xl font-semibold text-slate-900">
              {{ activeEntryMeta.label }}
            </h1>
            <Tag v-if="selectedAccountOperation" class="mt-2" color="blue">
              共用“{{ activeBackendConfig?.name }}”审批配置
            </Tag>
          </div>
        </div>

        <Card
          class="shadow-sm"
          :body-style="{ padding: 'clamp(16px, 3vw, 32px)' }"
        >
          <Form layout="vertical">
            <section class="flex flex-col">
              <h2 class="m-0 text-base font-semibold text-slate-900">
                表单信息
              </h2>
              <p
                v-if="selectedAccountOperation"
                class="mb-1 mt-1 text-sm text-slate-500"
              >
                当前操作已固定为“{{
                  selectedAccountOperation
                }}”，仅展示该操作所需字段。
              </p>

              <section
                class="approval-flow order-last mt-5 rounded-xl border border-slate-200 bg-white p-4 sm:p-5"
                aria-labelledby="approval-flow-heading"
              >
                <div
                  class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <h3
                      id="approval-flow-heading"
                      class="m-0 text-base font-semibold text-slate-900"
                    >
                      审批流程
                    </h3>
                    <p class="mb-0 mt-1 text-xs text-slate-500">
                      申请将按节点顺序流转，上一节点通过后才进入下一节点。
                    </p>
                  </div>
                  <Tag color="blue">流程由管理员统一配置</Tag>
                </div>

                <ol class="approval-flow-list mb-0 mt-5 p-0">
                  <li class="approval-flow-item list-none">
                    <span class="approval-flow-dot bg-foreground"></span>
                    <div class="min-w-0 flex-1 pb-5">
                      <p class="m-0 text-sm font-semibold text-slate-900">
                        发起申请
                      </p>
                      <p class="mb-0 mt-1 text-sm text-slate-500">
                        {{
                          userStore.userInfo?.realName ||
                          userStore.userInfo?.full_name ||
                          '当前用户'
                        }}
                      </p>
                    </div>
                  </li>

                  <li
                    v-for="(node, index) in form.approvalNodes"
                    :key="node.id"
                    class="approval-flow-item list-none"
                  >
                    <span class="approval-flow-dot bg-foreground"></span>
                    <div class="mb-4 min-w-0 flex-1 rounded-lg bg-slate-50 p-3">
                      <div class="flex items-center justify-between gap-3">
                        <p class="m-0 text-sm font-semibold text-slate-900">
                          审批节点 {{ index + 1 }}
                        </p>
                        <Button
                          v-if="false"
                          type="text"
                          danger
                          class="min-w-10"
                          :aria-label="`删除审批节点 ${index + 1}`"
                          @click="removeApprovalNode(index)"
                        >
                          <IconifyIcon icon="lucide:trash-2" />
                        </Button>
                      </div>
                      <div class="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
                        <label class="block min-w-0">
                          <span class="mb-1 block text-xs text-slate-500">
                            节点名称
                          </span>
                          <Input
                            v-model:value="node.label"
                            disabled
                            :maxlength="30"
                            placeholder="例如：媒介负责人审批"
                          />
                        </label>
                        <label class="block min-w-0">
                          <span class="mb-1 block text-xs text-slate-500">
                            审批人
                          </span>
                          <Select
                            v-model:value="node.approver"
                            disabled
                            :options="approverOptions"
                            class="w-full"
                            placeholder="请选择审批人"
                            @change="
                              (value) =>
                                handleApproverChange(index, String(value))
                            "
                          />
                        </label>
                      </div>
                    </div>
                  </li>

                  <li
                    v-if="activeBackendConfig?.handlerName"
                    class="approval-flow-item list-none"
                  >
                    <span class="approval-flow-dot bg-foreground"></span>
                    <div class="mb-4 min-w-0 flex-1 rounded-lg bg-slate-50 p-3">
                      <p class="m-0 text-sm font-semibold text-slate-900">
                        办理节点
                      </p>
                      <div class="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
                        <label class="block min-w-0">
                          <span class="mb-1 block text-xs text-slate-500">
                            节点名称
                          </span>
                          <Input value="资源办理" disabled />
                        </label>
                        <label class="block min-w-0">
                          <span class="mb-1 block text-xs text-slate-500">
                            办理人
                          </span>
                          <Input
                            :value="activeBackendConfig.handlerName"
                            disabled
                          />
                        </label>
                      </div>
                      <p class="mb-0 mt-2 text-xs text-slate-500">
                        所有审批节点通过后，由办理人完成资源处理与交付。
                      </p>
                    </div>
                  </li>

                  <li class="approval-flow-item list-none">
                    <span class="approval-flow-dot bg-foreground"></span>
                    <div class="min-w-0 flex-1">
                      <p class="m-0 text-sm font-semibold text-slate-900">
                        结束并抄送
                      </p>
                      <template v-if="form.ccUsers.length > 0">
                        <Select
                          v-model:value="form.ccUsers"
                          disabled
                          :options="ccUserOptions"
                          class="mt-2 w-full"
                          mode="tags"
                          placeholder="选择或输入抄送人；审批完成后自动通知"
                        />
                        <p class="mb-0 mt-1 text-xs text-slate-500">
                          抄送人可查看完整流程并参与评论，但不能执行审批。
                        </p>
                      </template>
                    </div>
                  </li>
                </ol>
              </section>

              <div
                class="mt-4 grid grid-cols-1 gap-x-5 md:grid-cols-2"
                :class="activeBackendConfig ? 'gap-y-4' : ''"
              >
                <FormItem
                  v-if="!activeBackendConfig"
                  label="申请标题"
                  required
                  class="md:col-span-2"
                >
                  <Input
                    v-model:value="form.title"
                    :maxlength="60"
                    placeholder="请用一句话说明所需资源"
                    show-count
                  />
                </FormItem>
                <FormItem
                  v-if="showPlatformField && !activeBackendConfig"
                  :label="form.type === 'account' ? '资源类型' : '平台'"
                  required
                >
                  <Select
                    v-model:value="form.platform"
                    :options="platformOptions"
                    :placeholder="
                      form.type === 'account' ? '请选择个号或 BM' : '请选择平台'
                    "
                    @change="resetDynamicForm"
                  />
                </FormItem>
                <template
                  v-for="field in renderedDynamicFields"
                  :key="field.key"
                >
                  <div v-if="field.type === 'section'" class="md:col-span-2">
                    <div
                      class="rounded-lg bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700"
                    >
                      {{ field.label }}
                    </div>
                    <p
                      v-if="field.helpText"
                      class="mb-0 mt-1 px-1 text-xs leading-5 text-slate-500"
                    >
                      {{ field.helpText }}
                    </p>
                  </div>
                  <FormItem
                    v-else
                    class="mb-0"
                    :label="
                      field.type === 'pixel-selector' ? undefined : field.label
                    "
                    :required="isDynamicFieldRequired(field)"
                    :class="field.width === 'full' ? 'md:col-span-2' : ''"
                    :extra="field.helpText"
                  >
                    <Input.TextArea
                      v-if="field.type === 'textarea'"
                      v-model:value="dynamicFormData[field.key]"
                      :disabled="field.readOnly"
                      :placeholder="field.placeholder"
                      :maxlength="field.maxLength"
                      :rows="3"
                      :show-count="field.maxLength !== undefined"
                    />
                    <Space.Compact
                      v-else-if="
                        field.key === 'rechargeAmount' && rechargeCurrencyField
                      "
                      class="w-full"
                    >
                      <InputNumber
                        v-model:value="dynamicFormData[field.key]"
                        class="min-w-0"
                        :disabled="field.readOnly"
                        :max="field.maxValue"
                        :min="field.minValue"
                        :placeholder="field.placeholder"
                        :precision="0"
                        style="width: calc(100% - 96px)"
                      />
                      <Select
                        v-model:value="
                          dynamicFormData[rechargeCurrencyField.key]
                        "
                        aria-label="币种"
                        :disabled="rechargeCurrencyField.readOnly"
                        :options="dynamicOptions(rechargeCurrencyField)"
                        style="width: 96px; flex: 0 0 96px"
                      />
                    </Space.Compact>
                    <InputNumber
                      v-else-if="field.type === 'number'"
                      v-model:value="dynamicFormData[field.key]"
                      class="w-full"
                      :disabled="field.readOnly"
                      :placeholder="
                        isDynamicAutoFillLoading(field)
                          ? '正在读取渠道数据…'
                          : field.placeholder
                      "
                      :min="field.minValue"
                      :max="field.maxValue"
                      :precision="field.key === 'quantity' ? 0 : undefined"
                    />
                    <DatePicker.RangePicker
                      v-else-if="field.type === 'date-range'"
                      v-model:value="dynamicFormData[field.key]"
                      class="w-full"
                      :disabled="field.readOnly"
                      format="YYYY-MM-DD"
                      :placeholder="['开始日期', '结束日期']"
                      value-format="YYYY-MM-DD"
                    />
                    <PixelAssetSelector
                      v-else-if="field.type === 'pixel-selector'"
                      :disabled="field.readOnly"
                      :label="field.label"
                      :model-value="
                        Array.isArray(dynamicFormData[field.key])
                          ? (dynamicFormData[field.key] as string[])
                          : []
                      "
                      :placeholder="resolveDynamicFieldPlaceholder(field)"
                      :required="isDynamicFieldRequired(field)"
                      @update:model-value="dynamicFormData[field.key] = $event"
                    />
                    <Select
                      v-else-if="
                        ['multi-select', 'select'].includes(field.type)
                      "
                      v-model:value="dynamicFormData[field.key]"
                      :mode="
                        field.type === 'multi-select' ? 'multiple' : undefined
                      "
                      :options="dynamicOptions(field)"
                      :placeholder="resolveDynamicFieldPlaceholder(field)"
                      :loading="isDynamicOptionLoading(field)"
                      :not-found-content="
                        field.optionSource === 'ad-accounts' &&
                        !dynamicAdAccountOptionsLoading
                          ? isMyAssetAccountApplicationRoute()
                            ? '暂无本人已分配的广告账户'
                            : '暂无系统广告账户'
                          : field.optionSource === 'channels' &&
                              !channelOptionsLoading
                            ? selectedConfigType === 'ACCOUNT_OPENING'
                              ? '暂无可开户渠道，请先在渠道管理中完成上架'
                              : '暂无可用渠道，请先到渠道管理中启用渠道'
                            : undefined
                      "
                      allow-clear
                      :disabled="field.readOnly"
                      option-filter-prop="label"
                      show-search
                    />
                    <Input
                      v-else
                      v-model:value="dynamicFormData[field.key]"
                      :disabled="field.readOnly"
                      :type="field.type === 'date' ? 'date' : 'text'"
                      :placeholder="
                        isDynamicAutoFillLoading(field)
                          ? '正在读取渠道数据…'
                          : field.placeholder
                      "
                      :maxlength="field.maxLength"
                    />
                  </FormItem>
                </template>
                <FormItem
                  v-if="showQuantityField && !activeBackendConfig"
                  label="数量"
                >
                  <InputNumber
                    v-model:value="form.quantity"
                    :min="1"
                    :max="100"
                    class="w-full"
                  />
                </FormItem>
                <FormItem
                  v-if="showResourceAssigneeField && !activeBackendConfig"
                  label="资源使用人"
                  required
                >
                  <StableUserSelect
                    v-model="form.resourceAssigneeId"
                    :legacy-label="form.resourceAssigneeName"
                    placeholder="请选择资源使用人"
                    @change="handleResourceAssigneeChange"
                  />
                  <p class="mb-0 mt-1 text-xs text-slate-500">
                    使用稳定用户 ID 交付广告账户；不会按姓名推断人员关系。
                  </p>
                </FormItem>
                <FormItem
                  v-if="showResourceTeamField && !activeBackendConfig"
                  label="资源使用团队"
                  required
                >
                  <Input
                    v-model:value="form.resourceTeamName"
                    :maxlength="60"
                    placeholder="例如：海外增长一组"
                  />
                </FormItem>
                <FormItem
                  v-if="showResourceTeamField && !activeBackendConfig"
                  label="资源团队 ID"
                  required
                >
                  <Input
                    v-model:value="form.resourceTeamId"
                    :maxlength="80"
                    placeholder="填写目录中的稳定团队 ID"
                  />
                </FormItem>
                <FormItem
                  v-if="showAmountField && !activeBackendConfig"
                  label="付款金额"
                  required
                >
                  <InputNumber
                    v-model:value="form.amount"
                    :min="0.01"
                    :precision="2"
                    class="w-full"
                    placeholder="请输入付款金额"
                  />
                </FormItem>
                <FormItem
                  v-if="showCurrencyField && !activeBackendConfig"
                  label="币种"
                  required
                >
                  <Select
                    v-model:value="form.currency"
                    :options="currencyOptions"
                  />
                </FormItem>
                <FormItem
                  v-if="!activeBackendConfig"
                  label="用途说明"
                  required
                  class="md:col-span-2"
                >
                  <Input.TextArea
                    v-model:value="form.description"
                    :maxlength="500"
                    :rows="5"
                    placeholder="说明资源用途、使用周期、期望交付时间和审批人需要知道的信息"
                    show-count
                  />
                </FormItem>
                <FormItem
                  v-if="!activeBackendConfig"
                  label="规格与补充要求"
                  class="md:col-span-2"
                >
                  <Input.TextArea
                    v-model:value="form.specifications"
                    :maxlength="300"
                    :rows="3"
                    placeholder="例如时区、币种、账号权限、设备配置、像素事件或收款信息"
                    show-count
                  />
                </FormItem>
              </div>
            </section>
          </Form>
        </Card>

        <div
          class="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"
        >
          <Button @click="closeForm">取消</Button>
          <Button
            :loading="submitting"
            type="primary"
            @click="saveApplication('pending')"
          >
            提交申请
          </Button>
        </div>
      </main>
    </div>

    <Modal
      :open="Boolean(detailRecord)"
      title="申请详情"
      :footer="null"
      :width="680"
      @cancel="detailRecord = undefined"
    >
      <div v-if="detailRecord" class="space-y-4 text-sm">
        <section class="rounded-xl bg-slate-50 p-4">
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
              <h3
                class="m-0 break-words text-base font-semibold text-slate-900"
              >
                {{ detailRecord.title }}
              </h3>
              <p class="mb-0 mt-1 break-all text-xs text-slate-500">
                {{ detailRecord.id }} · {{ detailRecord.createdAt }}
              </p>
            </div>
            <Tag :color="statusMeta[detailRecord.status].color">
              {{ statusMeta[detailRecord.status].label }}
            </Tag>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <Tag :color="typeMeta[detailRecord.type].color">
              {{ typeMeta[detailRecord.type].label }}
            </Tag>
            <span class="text-xs text-slate-500">
              {{
                detailRecord.status === 'approved'
                  ? '流程已完成并分配资产'
                  : detailRecord.status === 'rejected'
                    ? '流程已驳回'
                    : `当前由 ${detailRecord.approver} 处理`
              }}
            </span>
            <Button
              v-if="detailRecord.sourceApplicationId"
              class="!px-0"
              type="link"
              @click="
                openSourceApplicationDetail(detailRecord.sourceApplicationId)
              "
            >
              查看原申请
            </Button>
          </div>
        </section>

        <Tabs
          v-model:active-key="detailActiveTab"
          class="application-detail-tabs"
        >
          <Tabs.TabPane key="info" tab="申请信息">
            <div v-if="detailRecord.formSchema?.length" class="space-y-4 py-2">
              <div class="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2">
                <template
                  v-for="field in detailConfiguredFields(detailRecord)"
                  :key="field.key"
                >
                  <section
                    v-if="field.type === 'section'"
                    class="rounded-lg bg-slate-100 px-4 py-2 sm:col-span-2"
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
                    class="mb-0"
                    :class="field.width === 'full' ? 'sm:col-span-2' : ''"
                  >
                    <dt class="text-xs text-slate-400">{{ field.label }}</dt>
                    <dd
                      class="mb-0 mt-1 whitespace-pre-wrap break-words text-slate-700"
                    >
                      {{ detailConfiguredValue(detailRecord, field) }}
                    </dd>
                  </dl>
                </template>
              </div>
              <dl
                class="mb-0 grid grid-cols-1 gap-x-8 gap-y-5 border-t border-slate-100 pt-4 sm:grid-cols-2"
              >
                <div>
                  <dt class="text-xs text-slate-400">申请人</dt>
                  <dd class="mb-0 mt-1 text-slate-700">
                    {{ detailRecord.requester }}
                  </dd>
                </div>
                <div>
                  <dt class="text-xs text-slate-400">审批环节</dt>
                  <dd class="mb-0 mt-1 text-slate-700">
                    {{ approvalRoleMeta[detailRecord.approvalRole].label }}
                  </dd>
                </div>
                <div v-if="detailRecord.handlerName">
                  <dt class="text-xs text-slate-400">办理节点</dt>
                  <dd class="mb-0 mt-1 text-slate-700">
                    资源办理 · {{ detailRecord.handlerName }}
                  </dd>
                </div>
              </dl>
            </div>
            <dl
              v-else
              class="mb-0 grid min-h-40 grid-cols-1 content-start gap-x-8 gap-y-5 py-2 sm:grid-cols-2"
            >
              <div>
                <dt class="text-xs text-slate-400">资源归属</dt>
                <dd class="mb-0 mt-1 break-words text-slate-700">
                  {{ detailRecord.project }}
                </dd>
              </div>
              <div>
                <dt class="text-xs text-slate-400">申请人</dt>
                <dd class="mb-0 mt-1 text-slate-700">
                  {{ detailRecord.requester }}
                </dd>
              </div>
              <div>
                <dt class="text-xs text-slate-400">审批环节</dt>
                <dd class="mb-0 mt-1 text-slate-700">
                  {{ approvalRoleMeta[detailRecord.approvalRole].label }}
                </dd>
              </div>
              <div v-if="detailRecord.handlerName">
                <dt class="text-xs text-slate-400">办理节点</dt>
                <dd class="mb-0 mt-1 text-slate-700">
                  资源办理 · {{ detailRecord.handlerName }}
                </dd>
              </div>
              <div v-if="detailRecord.amount !== undefined">
                <dt class="text-xs text-slate-400">付款金额</dt>
                <dd class="mb-0 mt-1 font-medium text-slate-700">
                  {{ detailRecord.currency ?? 'USD' }}
                  {{ detailRecord.amount.toLocaleString() }}
                </dd>
              </div>
            </dl>
          </Tabs.TabPane>

          <Tabs.TabPane key="description" tab="申请说明">
            <div class="min-h-40 py-2">
              <p
                v-if="detailRecord.description"
                class="mb-0 whitespace-pre-wrap break-words rounded-lg bg-slate-50 px-4 py-3 leading-6 text-slate-600"
              >
                {{ detailRecord.description }}
              </p>
              <div
                v-else
                class="flex min-h-32 items-center justify-center text-slate-400"
              >
                暂无申请说明
              </div>
            </div>
          </Tabs.TabPane>

          <Tabs.TabPane key="progress">
            <template #tab>
              审批进度
              <span class="ml-1 text-xs text-slate-400">
                {{ detailRecord.approvalRecords.length }}
              </span>
            </template>
            <ol
              v-if="detailRecord.approvalRecords.length > 0"
              class="mb-0 min-h-40 space-y-3 p-0 py-2"
            >
              <li
                v-for="history in detailRecord.approvalRecords"
                :key="history.id"
                class="flex list-none items-start gap-3"
              >
                <span
                  class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                  :class="approvalActionMeta[history.action].tone"
                >
                  <IconifyIcon
                    :icon="approvalActionMeta[history.action].icon"
                  />
                </span>
                <div class="min-w-0 flex-1">
                  <div
                    class="flex flex-wrap items-center justify-between gap-1"
                  >
                    <span class="font-medium text-slate-800">
                      {{ approvalActionMeta[history.action].label }}
                    </span>
                    <span class="text-xs text-slate-400">{{ history.at }}</span>
                  </div>
                  <p class="mb-0 mt-0.5 text-xs text-slate-500">
                    {{ history.actor }} · {{ history.actorRole }}
                  </p>
                  <p
                    v-if="
                      history.action === 'transferred' && history.recipientName
                    "
                    class="mb-0 mt-0.5 text-xs text-slate-500"
                  >
                    转交给 {{ history.recipientName
                    }}<span v-if="history.recipientDepartmentName">
                      · {{ history.recipientDepartmentName }}</span
                    >
                  </p>
                  <p class="mb-0 mt-1 break-words text-sm text-slate-600">
                    {{ history.remark }}
                  </p>
                  <ProcessingResultDetails
                    v-if="history.action === 'completed'"
                    :action-data="history.actionData"
                    :application="detailRecord"
                  />
                </div>
              </li>
            </ol>
            <div
              v-else
              class="flex min-h-40 items-center justify-center text-slate-400"
            >
              暂无审批记录
            </div>
          </Tabs.TabPane>
        </Tabs>
      </div>
    </Modal>
  </Page>
</template>

<style scoped>
.application-form-shell {
  min-height: calc(100% + var(--adpulse-page-gutter));
  margin-block-start: calc(var(--adpulse-page-gutter) * -1);
  margin-inline: calc(var(--adpulse-page-gutter) * -1);
}

.application-form-header {
  top: calc(var(--adpulse-page-gutter) * -1);
}

.application-icon {
  color: hsl(var(--primary-foreground));
}

.application-icon--amber {
  background-color: hsl(38 92% 50%);
}

.application-icon--blue {
  background-color: hsl(217 91% 60%);
}

.application-icon--cyan {
  background-color: hsl(189 94% 43%);
}

.application-icon--emerald {
  background-color: hsl(var(--success));
}

.application-icon--indigo {
  background-color: hsl(239 84% 67%);
}

.application-icon--orange {
  background-color: hsl(var(--warning));
}

.application-icon--pink {
  background-color: hsl(329 86% 57%);
}

.application-icon--rose {
  background-color: hsl(var(--destructive));
}

.application-icon--violet {
  background-color: hsl(262 83% 58%);
}

.approval-flow-item {
  position: relative;
  display: flex;
  gap: 14px;
}

.approval-flow-item:not(:last-child)::before {
  position: absolute;
  top: 18px;
  bottom: -2px;
  left: 7px;
  width: 1px;
  content: '';
  background: #cbd5e1;
}

.approval-flow-dot {
  position: relative;
  z-index: 1;
  width: 15px;
  height: 15px;
  margin-top: 3px;
  border: 3px solid white;
  border-radius: 999px;
  box-shadow: 0 0 0 1px #cbd5e1;
  flex: none;
}
</style>
