<script lang="ts" setup>
import DeliveryTaskItems from './components/DeliveryTaskItems.vue';
import type {
  MenuProps,
  TableColumnsType,
  UploadFile,
  UploadProps,
} from 'ant-design-vue';

import type {
  TaskActivityRecord,
  TaskCenterSummary,
  TaskDetail,
  TaskDraft,
  TaskSummary,
} from '#/api';
import type { ListOrderParams, MaterialOrderActivity } from '#/api/requirement';
import type { LegacyMaterialOrderSummary } from '#/domain/task';
import type { TaskActivityEvent } from '#/domain/task-activity';
import type { DeliverySourceCampaign } from '#/domain/task-delivery';
import type { MaterialOrderDeliveryContext } from '#/domain/task-material-delivery';
import type {
  AmCompletionEntryMode,
  AmDeliveryStatus,
  TaskAttachmentMeta,
  TaskCenterKind,
  TaskCenterStatus,
  TaskCenterTask,
  TaskCompletionInput,
  TaskCompletionRecord,
  TaskCompletionState,
} from '#/store/task-center';
import type { UploadFileItem } from '#/views/components/RequirementUploadModal.vue';

import { computed, onActivated, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';

import {
  Button,
  Card,
  Alert,
  Spin,
  DatePicker,
  Drawer,
  Dropdown,
  Empty,
  Input,
  InputNumber,
  Menu,
  MenuItem,
  message,
  Modal,
  Pagination,
  Popconfirm,
  Progress,
  Segmented,
  Select,
  Table,
  Tag,
  Upload,
} from 'ant-design-vue';

import {
  assignTaskApi,
  confirmTaskApi,
  declineTaskApi,
  deleteTaskDraftApi,
  followTaskApi,
  getDeliveryTaskSourceApi,
  getTaskApi,
  getCurrentUserRoleCodesApi,
  isFusionDemoMode,
  listTaskActivitiesApi,
  listTaskDraftsApi,
  listDeliveryTasksApi,
  reviewTaskSubmissionApi,
  submitDeliveryTaskApi,
  submitMaterialTaskApi,
  unfollowTaskApi,
  uploadTaskFileApi,
  withdrawTaskApi,
} from '#/api';
import { downloadStoredFileApi } from '#/api/file';
import {
  followMaterialOrder,
  unfollowMaterialOrder,
  listMaterialOrders,
  listMaterialOrderDrafts,
  listMaterialOrderActivities,
  batchDeleteMaterialOrders,
  batchRejectMaterialOrders,
} from '#/api/requirement';
import { useDeliveryTaskAccess } from '#/composables/useDeliveryTaskAccess';
import { useMaterialOrderAccess } from '#/composables/useMaterialOrderAccess';
import RequirementTemplateModal from '#/views/requirement/components/RequirementTemplateModal.vue';
import { deliverySourceService } from '#/domain/task-delivery';
import {
  canEditRejectedMaterialOrder,
  canReeditMaterialOrder,
  canResubmitMaterialOrder,
  createTaskService,
  projectLegacyMaterialOrderTask,
  readLegacyMaterialOrderSummaries,
} from '#/domain/task';
import { projectDeliveryTaskDetail } from '#/domain/task/adapters/task-detail';
import { loadAllTaskPages } from '#/domain/task/load-all-task-pages';
import { taskMaterialDeliveryService } from '#/domain/task-material-delivery';
import { TaskCenterWorkflowRuntimeAdapter } from '#/domain/workflow-runtime';
import {
  canDemoAction,
  filterDemoTasks,
  getCurrentDemoActor,
} from '#/mock/demo-access';
import { demoRoleProfiles } from '#/mock/demo-role-preview';
import {
  ASSIGNED_CONFIRMATION_EXAMPLE_TASK_ID,
  PENDING_ACCEPTANCE_EXAMPLE_TASK_ID,
  PENDING_ASSIGNMENT_AM_EXAMPLE_TASK_ID,
  PENDING_ASSIGNMENT_MATERIAL_EXAMPLE_TASK_ID,
  useTaskCenterStore,
} from '#/store/task-center';
import UploadMaterialModal from '#/views/components/RequirementUploadModal.vue';

import { useMaterialOrderLifecycle } from '#/composables/useMaterialOrderLifecycle';
import { useListRouteState } from '#/composables/use-list-route-state';
import MaterialTaskActionMenu from './components/MaterialTaskActionMenu.vue';
import MaterialTaskFilters from './components/MaterialTaskFilters.vue';
import {
  emptyMaterialTaskFilters,
  materialQuickStatuses,
  type MaterialTaskFilters as MaterialTaskFilterValues,
} from './components/material-task-filters';
import MaterialTaskDetailDrawer from './components/MaterialTaskDetailDrawer.vue';
import RelatedMaterialTasks from './components/RelatedMaterialTasks.vue';
import MaterialAcceptanceDrawer from './components/MaterialAcceptanceDrawer.vue';
import MaterialShareModal from './components/MaterialShareModal.vue';
import MaterialAssignmentModal from './components/MaterialAssignmentModal.vue';
import StableUserSelect from '../components/StableUserSelect.vue';

defineOptions({ name: 'WorkbenchTasks' });

type GroupBy = 'kind' | 'none' | 'project' | 'status';
type MainSection =
  | 'activity'
  | 'assigned'
  | 'drafts'
  | 'followed'
  | 'owned'
  | 'quick';
type QuickFilter =
  | 'paused'
  | 'cancelled'
  | 'acceptance'
  | 'all'
  | 'assigned'
  | 'completed'
  | 'created'
  | 'failed'
  | 'pending_assignment'
  | 'confirmation'
  | 'submission'
  | 'shared';
type SortBy = 'default' | 'progress-desc' | 'status' | 'title';
type TaskActionContext =
  | 'assigned'
  | 'completed'
  | 'created'
  | 'owned'
  | 'view-only';
type TaskEditMode = 'edit' | 'modify-submit';
type TaskKind = TaskCenterKind;
type TaskStatus = TaskCenterStatus;
type TaskTab = 'delivery' | 'material';
type ViewMode = 'board' | 'dashboard' | 'list';
type WorkbenchTask = TaskCenterTask & {
  materialUpload?: TaskSummary['materialUpload'];
  materialAssignments?: LegacyMaterialOrderSummary['assignments'];
  materialPermissions?: LegacyMaterialOrderSummary['permissions'];
  materialOrderVersion?: number;
};

interface TaskGroup {
  key: string;
  label: string;
  tasks: WorkbenchTask[];
}

interface CompletionFormState {
  accountIds: string[];
  actualBudget: number | undefined;
  actualSpend: number;
  actualStartAt: string;
  adCount: number | undefined;
  adsetCount: number | undefined;
  campaignCount: number | undefined;
  campaignIds: string[];
  currency: string;
  dailyReportSpend: number;
  deliveryStatus: '' | AmDeliveryStatus;
  entryMode: AmCompletionEntryMode;
  exceptionNote: string;
  note: string;
  platforms: string[];
  sourceAdIds: string[];
  sourceAdsetIds: string[];
  sourceDateRange: string[];
}

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();
const taskCenterStore = useTaskCenterStore();
const taskService = createTaskService(() => taskCenterStore.tasks, {
  acceptTask: taskCenterStore.acceptTask,
  completeTask: taskCenterStore.completeTask,
  patchTask: taskCenterStore.patchTask,
  rejectTask: taskCenterStore.rejectTask,
});
const demoMode = isFusionDemoMode();
const demoActor = computed(() =>
  demoMode ? getCurrentDemoActor() : undefined,
);
const workflowRuntime = new TaskCenterWorkflowRuntimeAdapter({
  tasks: () => taskCenterStore.tasks,
});
const downloadingOriginalFileIds = reactive(new Set<string>());
const pendingFollowTaskIds = reactive(new Set<string>());

async function downloadOriginalFile(file: TaskAttachmentMeta) {
  const fileId = String(file.serverFileId || file.id);
  if (!fileId || downloadingOriginalFileIds.has(fileId)) return;
  downloadingOriginalFileIds.add(fileId);
  try {
    const blob = await downloadStoredFileApi(fileId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = file.name;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    message.error(
      error instanceof Error
        ? `附件下载失败：${error.message}`
        : '附件下载失败',
    );
  } finally {
    downloadingOriginalFileIds.delete(fileId);
  }
}

const activeSection = ref<MainSection>('owned');
const activeTaskTab = ref<TaskTab>('delivery');
const quickFilter = ref<QuickFilter>('all');
const isSharedView = computed(
  () =>
    activeTaskTab.value === 'material' &&
    activeSection.value === 'quick' &&
    quickFilter.value === 'shared',
);
const viewMode = ref<ViewMode>('list');
// 看板和仪表盘加载筛选范围内的全部任务，每批大小保持在既有接口限制内。
const taskOverviewPageSize = 100;
const searchKeyword = ref('');
const deliveryPage = ref(1);
const deliveryPageSize = ref(20);
const deliveryTotal = ref(0);
const deliveryQuery = ref('');
const deliveryLoading = ref(false);
const deliveryError = ref('');
let taskRequestSequence = 0;
const isDeliveryList = computed(
  () =>
    activeTaskTab.value === 'delivery' &&
    !['activity', 'drafts'].includes(activeSection.value),
);
const isMaterialList = computed(
  () =>
    !demoMode &&
    activeTaskTab.value === 'material' &&
    !['activity', 'drafts'].includes(activeSection.value),
);
const materialFilters = ref(emptyMaterialTaskFilters());
const materialPage = ref(1);
const materialPageSize = ref(20);
const materialTotal = ref(0);
const materialQuantity = ref(0);
const materialLoading = ref(false);
const materialError = ref('');
const taskResultsLoading = computed(() =>
  isMaterialList.value
    ? materialLoading.value
    : isDeliveryList.value && deliveryLoading.value,
);
const taskResultsError = computed(() =>
  isMaterialList.value
    ? materialError.value
    : isDeliveryList.value
      ? deliveryError.value
      : '',
);
const materialFixedStatus = computed(() =>
  activeSection.value === 'quick'
    ? materialQuickStatuses[quickFilter.value]
    : undefined,
);
const sourceFilter = ref<'all' | TaskKind>('all');
const statusFilter = ref<'all' | TaskStatus>('all');
const sortBy = ref<SortBy>('default');
const groupBy = ref<GroupBy>('none');
const routeStateReady = ref(false);
let routeRestoreQueued = false;
function scheduleRouteReload() {
  if (!routeStateReady.value || routeRestoreQueued) return;
  routeRestoreQueued = true;
  queueMicrotask(() => {
    routeRestoreQueued = false;
    void loadServerTasks();
  });
}

const navigationRouteState = {
  get quick() {
    return quickFilter.value;
  },
  set quick(value: QuickFilter) {
    quickFilter.value = value;
  },
  get section() {
    return activeSection.value;
  },
  set section(value: MainSection) {
    activeSection.value = value;
  },
  get tab() {
    return activeTaskTab.value;
  },
  set tab(value: TaskTab) {
    activeTaskTab.value = value;
  },
  get view() {
    return viewMode.value;
  },
  set view(value: ViewMode) {
    viewMode.value = value;
  },
};
const deliveryRouteState = {
  get group_by() {
    return groupBy.value;
  },
  set group_by(value: GroupBy) {
    groupBy.value = value;
  },
  get keyword() {
    return deliveryQuery.value;
  },
  set keyword(value: string) {
    deliveryQuery.value = value;
    searchKeyword.value = value;
  },
  get sort_by() {
    return sortBy.value;
  },
  set sort_by(value: SortBy) {
    sortBy.value = value;
  },
  get source() {
    return sourceFilter.value;
  },
  set source(value: 'all' | TaskKind) {
    sourceFilter.value = value;
  },
  get status() {
    return statusFilter.value;
  },
  set status(value: 'all' | TaskStatus) {
    statusFilter.value = value;
  },
};
const materialRouteState = {
  get country() {
    return materialFilters.value.country;
  },
  set country(value: string | undefined) {
    materialFilters.value.country = value;
  },
  get creative_planners() {
    return materialFilters.value.creative_planners;
  },
  set creative_planners(value: string[]) {
    materialFilters.value.creative_planners = value;
  },
  get creator() {
    return materialFilters.value.creator;
  },
  set creator(value: string | undefined) {
    materialFilters.value.creator = value;
  },
  get demand_type() {
    return materialFilters.value.demand_type;
  },
  set demand_type(value: string | undefined) {
    materialFilters.value.demand_type = value;
  },
  get department() {
    return materialFilters.value.department;
  },
  set department(value: string | undefined) {
    materialFilters.value.department = value;
  },
  get designers() {
    return materialFilters.value.designers;
  },
  set designers(value: string[]) {
    materialFilters.value.designers = value;
  },
  get keyword() {
    return materialFilters.value.keyword;
  },
  get is_green_material() {
    return materialFilters.value.is_green_material;
  },
  set is_green_material(value: boolean | undefined) {
    materialFilters.value.is_green_material = value;
  },
  set keyword(value: string) {
    materialFilters.value.keyword = value;
  },
  get order() {
    return materialFilters.value.order;
  },
  set order(value: 'asc' | 'desc') {
    materialFilters.value.order = value;
  },
  get priority() {
    return materialFilters.value.priority;
  },
  set priority(value: string[]) {
    materialFilters.value.priority = value;
  },
  get project() {
    return materialFilters.value.project;
  },
  set project(value: string | undefined) {
    materialFilters.value.project = value;
  },
  get sort() {
    return materialFilters.value.sort;
  },
  set sort(value: string) {
    materialFilters.value.sort = value;
  },
  get status() {
    return materialFilters.value.status;
  },
  set status(value: string | undefined) {
    materialFilters.value.status = value;
  },
};
const {
  commitQueryState: commitNavigationQueryState,
  restoreFromRoute: restoreNavigationRoute,
} = useListRouteState({
  onRouteStateRestored: scheduleRouteReload,
  state: navigationRouteState,
});
const {
  commitQueryState: commitDeliveryQueryState,
  resetQueryState: resetDeliveryQueryState,
  restoreFromRoute: restoreDeliveryRoute,
} = useListRouteState({
  onRouteStateRestored: scheduleRouteReload,
  pagination: {
    defaultPageSize: 20,
    page: deliveryPage,
    pageSize: deliveryPageSize,
    pageSizes: [20, 50, 100],
  },
  scope: 'delivery',
  state: deliveryRouteState,
});
const {
  commitQueryState: commitMaterialQueryState,
  resetQueryState: resetMaterialQueryState,
  restoreFromRoute: restoreMaterialRoute,
} = useListRouteState({
  fields: {
    is_green_material: {
      codec: {
        parse(value) {
          const raw = Array.isArray(value) ? value[0] : value;
          if (raw === '1' || raw === 'true') return true;
          if (raw === '0' || raw === 'false') return false;
          return undefined;
        },
        serialize(value) {
          return value === undefined ? undefined : value ? '1' : '0';
        },
      },
    },
  },
  onRouteStateRestored: scheduleRouteReload,
  pagination: {
    defaultPageSize: 20,
    page: materialPage,
    pageSize: materialPageSize,
    pageSizes: [20, 50, 100],
  },
  scope: 'material',
  state: materialRouteState,
});
const taskCenterSummary = ref<TaskCenterSummary>();
const editModalOpen = ref(false);
const editMode = ref<TaskEditMode>('edit');
const editingTaskId = ref('');
const progressModalOpen = ref(false);
const progressTaskId = ref('');
const materialDetailOpen = ref(false);
const materialDetailOrderId = ref<string>();
const materialDetailInitialAction = ref<'view' | 'deliver'>('view');
const detailDrawerOpen = ref(false);
const detailTaskId = ref('');
const completionModalOpen = ref(false);
const completionTaskId = ref('');
const completionSubmitting = ref(false);
const completionFiles = ref<UploadFile[]>([]);
const materialDeliveryModalRef =
  ref<InstanceType<typeof UploadMaterialModal>>();
const materialDeliveryModalOpen = ref(false);
const materialDeliveryTaskId = ref('');
const materialDeliveryContext = ref<MaterialOrderDeliveryContext>();
const materialDeliverySubmitting = ref(false);
const materialTaskModalOpen = ref(false);
const materialTaskFiles = ref<UploadFile[]>([]);
const materialTaskQuantity = ref(1);
const materialTaskNote = ref('');
const deliveryCampaigns = ref<DeliverySourceCampaign[]>([]);
const deliveryCampaignsLoading = ref(false);
const deliveryCampaignsError = ref('');
const materialShareOpen = ref(false);
const materialShareOrderId = ref('');
const materialAcceptanceOpen = ref(false);
const materialAcceptanceOrderId = ref('');
const acceptanceModalOpen = ref(false);
const acceptanceTaskId = ref('');
const acceptanceSubmitting = ref(false);
const acceptanceReason = ref('');
const acceptanceError = ref('');
/** 当前验收弹窗中选中的投手交付版本；素材任务仍沿用单条交付。 */
const selectedAcceptanceSubmissionId = ref('');
const deliveryHistoryModalOpen = ref(false);
const deliveryHistoryRecords = ref<TaskCompletionRecord[]>([]);
const deliveryHistoryTitle = ref('');
const assignmentModalOpen = ref(false);
const materialAssignmentModalOpen = ref(false);
const materialAssignmentOrderId = ref<string>();
const assignmentSubmitting = ref(false);
const assignmentTaskId = ref('');
const assignmentAssigneeId = ref<string>();
const assignmentDesignerNames = ref<string[]>([]);
const assignmentCreativePlannerName = ref<string>();
const declineModalOpen = ref(false);
const declineSubmitting = ref(false);
const declineTaskId = ref('');
const declineReason = ref('');
const declineError = ref('');
const completionForm = reactive<CompletionFormState>({
  accountIds: [],
  actualBudget: undefined,
  actualSpend: 0,
  actualStartAt: '',
  adCount: undefined,
  adsetCount: undefined,
  campaignCount: undefined,
  campaignIds: [],
  currency: 'USD',
  dailyReportSpend: 0,
  deliveryStatus: '',
  entryMode: 'delivery-center',
  exceptionNote: '',
  note: '',
  platforms: [],
  sourceAdIds: [],
  sourceAdsetIds: [],
  sourceDateRange: [],
});

const completionErrors = reactive<Record<string, string>>({});

const editForm = reactive({
  dueAt: '',
  owner: '',
  summary: '',
  title: '',
});

const kindMeta: Record<
  TaskKind,
  { color: string; icon: string; label: string; shortLabel: string }
> = {
  am: {
    color: 'blue',
    icon: 'lucide:briefcase-business',
    label: 'AM 指派投放任务',
    shortLabel: '投放任务',
  },
  material: {
    color: 'purple',
    icon: 'lucide:images',
    label: '投放指派素材任务',
    shortLabel: '素材任务',
  },
  media: {
    color: 'orange',
    icon: 'lucide:badge-check',
    label: '媒介审批任务',
    shortLabel: '媒介审批',
  },
};

const statusMeta: Record<
  TaskStatus,
  { color: string; icon: string; label: string; tone: string }
> = {
  paused: {
    color: 'warning',
    icon: 'lucide:pause',
    label: '已暂停',
    tone: 'bg-orange-50 text-orange-600',
  },
  cancelled: {
    color: 'error',
    icon: 'lucide:ban',
    label: '已取消',
    tone: 'bg-rose-50 text-rose-600',
  },
  assigned_pending_confirmation: {
    color: 'cyan',
    icon: 'lucide:circle-dot-dashed',
    label: '待确认',
    tone: 'bg-cyan-50 text-cyan-600',
  },
  draft: {
    color: 'default',
    icon: 'lucide:file-pen-line',
    label: '草稿',
    tone: 'bg-slate-100 text-slate-600',
  },
  doing: {
    color: 'processing',
    icon: 'lucide:clock-3',
    label: '待提交',
    tone: 'bg-violet-50 text-violet-600',
  },
  done: {
    color: 'success',
    icon: 'lucide:circle-check-big',
    label: '已完成',
    tone: 'bg-emerald-50 text-emerald-600',
  },
  pending: {
    color: 'default',
    icon: 'lucide:inbox',
    label: '待处理',
    tone: 'bg-blue-50 text-blue-600',
  },
  pending_assignment: {
    color: 'purple',
    icon: 'lucide:user-round-plus',
    label: '待分配',
    tone: 'bg-purple-50 text-purple-600',
  },
  partially_completed: {
    color: 'processing',
    icon: 'lucide:circle-dot-dashed',
    label: '部分完成',
    tone: 'bg-fuchsia-50 text-fuchsia-600',
  },
  pending_acceptance: {
    color: 'warning',
    icon: 'lucide:clipboard-check',
    label: '待验收',
    tone: 'bg-orange-50 text-orange-600',
  },
  rejected: {
    color: 'error',
    icon: 'lucide:circle-x',
    label: '已驳回',
    tone: 'bg-rose-50 text-rose-600',
  },
  risk: {
    color: 'error',
    icon: 'lucide:triangle-alert',
    label: '即将超时',
    tone: 'bg-red-50 text-red-600',
  },
  withdrawn: {
    color: 'default',
    icon: 'lucide:undo-2',
    label: '已撤回',
    tone: 'bg-slate-100 text-slate-500',
  },
};

// 分配、确认及制作阶段尚未完成交付，只在部分完成及之后提示素材数量缺口。
const materialShortfallStatuses = new Set<TaskStatus>([
  'partially_completed',
  'pending_acceptance',
  'done',
]);

const tasks = computed<WorkbenchTask[]>(() => taskCenterStore.tasks);

const backendStatusMap: Record<TaskSummary['status'], TaskCenterStatus> = {
  COMPLETED: 'done',
  PENDING_ASSIGNMENT: 'pending_assignment',
  PENDING_ACCEPTANCE: 'pending_acceptance',
  PENDING_CONFIRMATION: 'assigned_pending_confirmation',
  PROCESSING: 'doing',
  REJECTED: 'rejected',
  WITHDRAWN: 'withdrawn',
};

/** 素材工单预期交付仅展示日期；投放任务沿用时间精度。 */
function formatTaskDueDate(
  task: Pick<WorkbenchTask, 'dueAt' | 'kind'>,
  emptyLabel = '—',
) {
  const value = formatTaskDateTime(task.dueAt, emptyLabel);
  return task.kind === 'material' ? value.slice(0, 10) : value;
}

function taskDeadline(task: Pick<WorkbenchTask, 'dueAt' | 'kind'>) {
  // 素材交付只选择日期，临期统计沿用北京时间交付日 19:00。
  const value =
    task.kind === 'material'
      ? `${formatTaskDueDate(task)}T19:00:00+08:00`
      : task.dueAt;
  return Date.parse(value);
}

function formatTaskDateTime(value?: string, emptyLabel = '—') {
  const raw = value?.trim() ?? '';
  if (!raw) return emptyLabel;
  const date = new Date(raw);
  // 非日期文本（例如“尚未提交”）保持原样；其余 UTC 时间固定按北京时间展示。
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat('zh-CN', {
    day: '2-digit',
    hour: '2-digit',
    hour12: false,
    minute: '2-digit',
    month: '2-digit',
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
  })
    .format(date)
    .replaceAll('/', '-');
}

function toWorkbenchTask(
  task: TaskSummary,
  materialOrder?: LegacyMaterialOrderSummary,
): WorkbenchTask {
  const previous = tasks.value.find((item) => item.id === task.id);
  const progress = ['COMPLETED', 'PENDING_ACCEPTANCE'].includes(task.status)
    ? 100
    : 0;
  const workbenchTask: WorkbenchTask = {
    actionLabel:
      task.status === 'PENDING_CONFIRMATION' ? '确认任务' : '查看任务',
    audiences: ['all'],
    assignedAt: task.assignedAt,
    assignerId: task.assignerId,
    assignerName: task.assignerName,
    amNames: task.amNames,
    completedAt: task.completedAt,
    createdAt: task.createdAt,
    createdBy: task.creatorName,
    creatorId: task.creatorId,
    deliveryOperator: task.deliveryOperator,
    dueAt: task.dueAt ?? '未设置',
    followed: task.followed || Boolean(demoMode && previous?.followed),
    id: task.id,
    kind: task.taskType === 'DELIVERY' ? 'am' : 'material',
    materialUpload: task.materialUpload,
    owner: task.ownerName ?? '待分配',
    ownerId: task.ownerId,
    ownerName: task.ownerName,
    progress,
    project: task.projectName || previous?.project || `项目 ${task.projectId}`,
    projectId: task.projectId,
    rejection: task.rejectionReason
      ? {
          reason: task.rejectionReason,
          rejectedAt: task.rejectedAt ?? task.updatedAt,
          rejectedBy: task.rejectedBy ?? task.ownerName ?? '任务负责人',
          rejectedById: task.rejectedBy,
        }
      : undefined,
    route: '/workbench/tasks',
    status:
      task.taskType === 'MATERIAL' &&
      task.materialUpload?.orderStatus === 'partially_completed'
        ? 'partially_completed'
        : backendStatusMap[task.status],
    summary: task.description || '暂无任务说明',
    title: task.title,
    updatedAt: task.updatedAt,
    withdrawnAt: task.withdrawnAt,
  };
  if (!materialOrder) return workbenchTask;

  const projection = projectLegacyMaterialOrderTask(materialOrder);
  return {
    ...workbenchTask,
    actionLabel: projection.actionLabel,
    dueAt: projection.dueAt || workbenchTask.dueAt,
    legacyMaterialOrderId: projection.legacyMaterialOrderId,
    legacyMaterialOrderStatus: projection.legacyMaterialOrderStatus,
    owner: projection.owner,
    ownerName: projection.owner,
    progress: projection.progress,
    project: projection.project || workbenchTask.project,
    projectId: materialOrder.project_id || workbenchTask.projectId,
    route: '/requirement/detail',
    source: materialOrder.source_task_id
      ? { id: materialOrder.source_task_id, kind: 'delivery-task' }
      : undefined,
    sourceId: projection.legacyMaterialOrderId,
    status: projection.status,
    summary: projection.summary,
    title: projection.title,
    updatedAt: projection.updatedAt || workbenchTask.updatedAt,
  };
}

function draftToWorkbenchTask(draft: TaskDraft): WorkbenchTask {
  return {
    actionLabel: '任务编辑',
    audiences: ['all'],
    createdAt: draft.createdAt,
    createdBy: draft.creatorName,
    creatorId: draft.creatorId,
    draftId: draft.id,
    dueAt: '尚未提交',
    id: `draft:${draft.id}`,
    kind: draft.taskType === 'DELIVERY' ? 'am' : 'material',
    owner: '未分配',
    progress: 0,
    project: draft.projectId ? `项目 ${draft.projectId}` : '未选择项目',
    projectId: draft.projectId,
    route:
      draft.taskType === 'DELIVERY'
        ? '/workbench/tasks/create-delivery'
        : '/workbench/tasks/create-material',
    status: 'draft',
    summary: '尚未提交的任务草稿',
    title: draft.title || '未命名草稿',
    updatedAt: draft.updatedAt,
  };
}

function activityToEvent(activity: TaskActivityRecord): TaskActivityEvent {
  const meta = {
    ACCEPTED: { icon: 'lucide:circle-check-big', level: 'low' },
    ALLOCATION_ACCEPTED: { icon: 'lucide:circle-check-big', level: 'low' },
    ALLOCATION_REJECTED: { icon: 'lucide:undo-2', level: 'high' },
    ASSIGNED: { icon: 'lucide:user-round-plus', level: 'medium' },
    CONFIRMED: { icon: 'lucide:badge-check', level: 'low' },
    CREATED: { icon: 'lucide:plus-circle', level: 'low' },
    DECLINED: { icon: 'lucide:circle-x', level: 'high' },
    DELIVERY_SUBMITTED: { icon: 'lucide:upload-cloud', level: 'high' },
    REJECTED: { icon: 'lucide:undo-2', level: 'high' },
    RESUBMITTED: { icon: 'lucide:rotate-ccw', level: 'medium' },
    WITHDRAWN: { icon: 'lucide:undo-2', level: 'low' },
  } as const satisfies Record<
    TaskActivityRecord['eventType'],
    Pick<TaskActivityEvent, 'icon' | 'level'>
  >;
  const eventKind = {
    ACCEPTED: 'accepted',
    ALLOCATION_ACCEPTED: 'accepted',
    ALLOCATION_REJECTED: 'rejected',
    ASSIGNED: 'stage-snapshot',
    CONFIRMED: 'stage-snapshot',
    CREATED: 'created',
    DECLINED: 'rejected',
    DELIVERY_SUBMITTED: 'delivery-submitted',
    REJECTED: 'rejected',
    RESUBMITTED: 'stage-snapshot',
    WITHDRAWN: 'withdrawn',
  } as const satisfies Record<
    TaskActivityRecord['eventType'],
    TaskActivityEvent['eventKind']
  >;
  // 兼容后端新增的事件类型，避免单条未知动态中断整个列表渲染。
  const activityMeta = meta[activity.eventType] ?? {
    icon: 'lucide:history',
    level: 'low',
  };
  return {
    actorId: activity.actorId,
    actorName: activity.actorName,
    description: activity.description,
    eventKind: eventKind[activity.eventType] ?? 'stage-snapshot',
    icon: activityMeta.icon,
    id: `task-activity:${activity.id}`,
    level: activityMeta.level,
    occurredAt: activity.occurredAt,
    projectId: activity.projectId,
    sourceId: activity.taskId,
    sourceType:
      activity.taskType === 'DELIVERY' ? 'delivery-task' : 'material-task',
    state: activity.state.toLowerCase(),
    targetPath: '/workbench/tasks',
    taskId: activity.taskId,
    title: activity.taskTitle,
  };
}

function materialActivityToEvent(
  activity: MaterialOrderActivity,
): TaskActivityEvent {
  return {
    actorId: activity.operator_id,
    actorName: activity.operator,
    description: activity.content,
    eventKind: 'updated',
    icon: 'lucide:file-pen-line',
    id: `material-activity:${activity.id}`,
    level: 'low',
    occurredAt: formatTaskDateTime(activity.created_at),
    projectId: '',
    sourceId: activity.order_id,
    sourceType: 'material-task',
    state: activity.status,
    targetPath: `/workbench/tasks?materialOrderId=${encodeURIComponent(activity.order_id)}&materialAction=view`,
    title: activity.title,
  };
}

async function loadServerTasks() {
  await commitNavigationQueryState();
  await (activeTaskTab.value === 'material'
    ? commitMaterialQueryState()
    : commitDeliveryQueryState());
  const requestSequence = ++taskRequestSequence;
  const loadAll = viewMode.value !== 'list';
  deliveryError.value = '';
  deliveryLoading.value = false;
  materialLoading.value = false;
  taskCenterSummary.value = undefined;
  if (demoMode) return;
  activityLoading.value = false;
  if (activeSection.value === 'activity') {
    activityLoading.value = true;
    activityError.value = '';
    taskActivities.value = [];
    try {
      if (activeTaskTab.value === 'material') {
        const [roles, activities] = await Promise.all([
          getCurrentUserRoleCodesApi(),
          listMaterialOrderActivities(),
        ]);
        if (requestSequence !== taskRequestSequence) return;
        materialUserRoles.value = roles;
        taskActivities.value = activities.items.map(materialActivityToEvent);
      } else {
        const activities = await listTaskActivitiesApi(100);
        if (requestSequence !== taskRequestSequence) return;
        taskActivities.value = activities
          .filter((activity) => activity.taskType === 'DELIVERY')
          .map(activityToEvent);
      }
    } catch {
      if (requestSequence === taskRequestSequence)
        activityError.value = '任务动态加载失败，请重试';
    } finally {
      if (requestSequence === taskRequestSequence)
        activityLoading.value = false;
    }
    return;
  }
  if (activeTaskTab.value === 'delivery') {
    if (activeSection.value === 'drafts') {
      const drafts = await listTaskDraftsApi();
      if (requestSequence !== taskRequestSequence) return;
      taskCenterStore.replaceTasks(
        drafts
          .filter((draft) => draft.taskType === 'DELIVERY')
          .map(draftToWorkbenchTask),
      );
      return;
    }
    const quickScope =
      quickFilter.value === 'created'
        ? 'CREATED'
        : quickFilter.value === 'assigned'
          ? 'ASSIGNED'
          : quickFilter.value === 'confirmation' ||
              quickFilter.value === 'acceptance'
            ? 'LEADER'
            : quickFilter.value === 'pending_assignment'
              ? 'PENDING_ASSIGNMENT'
              : quickFilter.value === 'all' && isSuperAdmin.value
                ? 'ALL'
                : 'RELATED';
    const quickStatus =
      quickFilter.value === 'confirmation'
        ? 'PENDING_CONFIRMATION'
        : quickFilter.value === 'acceptance'
          ? 'PENDING_ACCEPTANCE'
          : quickFilter.value === 'completed'
            ? 'COMPLETED'
            : quickFilter.value === 'submission'
              ? 'PROCESSING'
              : quickFilter.value === 'failed'
                ? 'FAILED'
                : undefined;
    deliveryLoading.value = true;
    taskCenterStore.replaceTasks([]);
    try {
      const query: Parameters<typeof listDeliveryTasksApi>[0] = {
        keyword: deliveryQuery.value || undefined,
        page: loadAll ? 1 : deliveryPage.value,
        pageSize: loadAll ? taskOverviewPageSize : deliveryPageSize.value,
        scope:
          activeSection.value === 'followed'
            ? 'FOLLOWED'
            : activeSection.value === 'assigned'
              ? 'ASSIGNED'
              : activeSection.value === 'quick'
                ? quickScope
                : 'OWNER',
        status: activeSection.value === 'quick' ? quickStatus : undefined,
      };
      const taskPage = await listDeliveryTasksApi(query);
      // 切换标签、视图或筛选后停止旧批次，全部取齐后才发布统计数据。
      if (requestSequence !== taskRequestSequence) return;
      const items = loadAll
        ? await loadAllTaskPages(
            taskPage,
            (page) => listDeliveryTasksApi({ ...query, page }),
            () => requestSequence === taskRequestSequence,
            taskOverviewPageSize,
          )
        : taskPage.items;
      if (!items || requestSequence !== taskRequestSequence) return;
      deliveryTotal.value = taskPage.total ?? items.length;
      const lastPage = Math.max(
        1,
        Math.ceil(deliveryTotal.value / deliveryPageSize.value),
      );
      if (!loadAll && deliveryPage.value > lastPage) {
        deliveryPage.value = lastPage;
        await loadServerTasks();
        return;
      }
      taskCenterStore.replaceTasks(items.map((task) => toWorkbenchTask(task)));
    } catch (error) {
      if (requestSequence !== taskRequestSequence) return;
      deliveryError.value =
        error instanceof Error ? error.message : '投放任务加载失败，请重试';
    } finally {
      if (requestSequence === taskRequestSequence)
        deliveryLoading.value = false;
    }
    return;
  }
  materialLoading.value = true;
  materialError.value = '';
  materialTotal.value = 0;
  materialQuantity.value = 0;
  taskCenterStore.replaceTasks([]);
  try {
    // 素材导航使用业务会话的角色编码，避免把中文角色名当作编码。
    const roleCodes = await getCurrentUserRoleCodesApi();
    if (requestSequence !== taskRequestSequence) return;
    materialUserRoles.value = roleCodes;
    if (activeSection.value === 'drafts') {
      const drafts = await listMaterialOrderDrafts();
      if (requestSequence !== taskRequestSequence) return;
      taskCenterStore.replaceTasks(drafts.map(draftToWorkbenchTask));
      return;
    }
    const materialOrders = await loadLegacyMaterialOrders(
      requestSequence,
      loadAll,
    );
    if (!materialOrders || requestSequence !== taskRequestSequence) return;
    materialTotal.value = materialOrders.total;
    materialQuantity.value = materialOrders.materialTotal;
    const lastPage = Math.max(
      1,
      Math.ceil(materialTotal.value / materialPageSize.value),
    );
    if (!loadAll && materialPage.value > lastPage) {
      materialPage.value = lastPage;
      await loadServerTasks();
      return;
    }
    taskCenterStore.replaceTasks(
      materialOrders.items.map(toLegacyMaterialOrderTask),
    );
  } catch (error) {
    if (requestSequence !== taskRequestSequence) return;
    materialError.value =
      error instanceof Error ? error.message : '素材工单加载失败，请重试';
    if (activeSection.value === 'drafts') message.error(materialError.value);
  } finally {
    if (requestSequence === taskRequestSequence) materialLoading.value = false;
  }
}

const currentUserName = computed(
  () =>
    userStore.userInfo?.realName || userStore.userInfo?.full_name || '当前用户',
);
const currentMaterialDesignerName = computed(() => {
  const user = userStore.userInfo as
    | { full_name?: string; realName?: string }
    | undefined;
  return user?.full_name?.trim() || currentUserName.value;
});
const currentUserId = computed(() => {
  const user = userStore.userInfo as Record<string, unknown> | undefined;
  const candidate = user?.userId ?? user?.user_id ?? user?._id;
  if (typeof candidate === 'string') return candidate.trim();
  if (typeof candidate === 'number') return String(candidate);
  return undefined;
});

const createdTaskIds = new Set([
  PENDING_ACCEPTANCE_EXAMPLE_TASK_ID,
  PENDING_ASSIGNMENT_AM_EXAMPLE_TASK_ID,
  PENDING_ASSIGNMENT_MATERIAL_EXAMPLE_TASK_ID,
  'TASK-AM-1042',
  'TASK-MAT-2079',
  'TASK-MED-3014',
]);
const assignedTaskIds = new Set([
  ASSIGNED_CONFIRMATION_EXAMPLE_TASK_ID,
  'TASK-AM-1038',
  'TASK-MAT-2088',
  'TASK-MED-3009',
]);

const materialUserRoles = ref<string[]>([]);
const requirementTemplateManagerOpen = ref(false);
const canManageRequirementTemplates = computed(() =>
  materialUserRoles.value.includes('creator_leader'),
);
const userRoles = computed(() => {
  if (!demoMode && activeTaskTab.value === 'material')
    return materialUserRoles.value;
  const roles =
    (userStore.userInfo as null | { roles?: string[] })?.roles ?? [];
  return roles.map((role) => role.toLowerCase());
});

const isSuperAdmin = computed(() => {
  const permissions =
    (
      userStore.userInfo as null | {
        permissions?: string[];
      }
    )?.permissions ?? [];
  return permissions.includes('ROLE_ADMIN');
});

const showAllRoles = computed(
  () =>
    (demoMode && demoActor.value?.roleId === 'admin') ||
    userRoles.value.includes('admin'),
);

function isLegacyMaterialOrderTask(task: WorkbenchTask) {
  return Boolean(task.legacyMaterialOrderId);
}

/** 新建工单会双写 ERP 任务和 Mongo 工单；任务中心以此识别其正式工单入口。 */
function materialOrderIds(task: WorkbenchTask) {
  const ids = task.materialUpload?.orderIds?.length
    ? task.materialUpload.orderIds
    : task.materialUpload?.orderId
      ? [task.materialUpload.orderId]
      : [];
  return [...new Set(ids.map((id) => id.trim()).filter(Boolean))];
}

function isFormalMaterialOrderTask(input: unknown) {
  const task = resolveTask(input);
  if (!task) return false;
  return task.kind === 'material' && materialOrderIds(task).length > 0;
}

function isMaterialOrderTask(input: unknown) {
  const task = resolveTask(input);
  if (!task) return false;
  return isLegacyMaterialOrderTask(task) || isFormalMaterialOrderTask(task);
}

function hasCompletedMaterialTask(task: WorkbenchTask) {
  const serverResult = task.materialUpload?.viewerCompletedDesigner;
  if (typeof serverResult === 'boolean') return serverResult;

  return Boolean(
    task.materialUpload?.completedDesigners?.some(
      (name) => name.trim() === currentMaterialDesignerName.value,
    ),
  );
}

/** 与 material-orders 的服务端鉴权保持一致：以 Mongo designers 为准。 */
function isAssignedMaterialDesigner(task: WorkbenchTask) {
  const serverResult = task.materialUpload?.viewerIsDesigner;
  if (typeof serverResult === 'boolean') return serverResult;

  return Boolean(
    task.materialUpload?.designers?.some(
      (name) => name.trim() === currentMaterialDesignerName.value,
    ),
  );
}

function toLegacyMaterialOrderTask(
  order: LegacyMaterialOrderSummary,
): WorkbenchTask {
  const projection = projectLegacyMaterialOrderTask(order);
  return {
    actionLabel: projection.actionLabel,
    audiences: ['all'],
    createdAt: projection.createdAt,
    createdBy: projection.createdBy,
    dueAt: projection.dueAt,
    followed: order.followed,
    id: `material-order:${projection.legacyMaterialOrderId}`,
    kind: 'material',
    legacyMaterialOrderId: projection.legacyMaterialOrderId,
    legacyMaterialOrderStatus: projection.legacyMaterialOrderStatus,
    creatorId: order.creator_id,
    materialPermissions: order.permissions,
    materialOrderVersion: order.version,
    materialAssignments: order.assignments,
    materialUpload: {
      orderId: order.id,
      orderIds: [order.id],
      orderNo: order.order_no,
      orderStatus: order.status,
      designers: order.designers,
      creativePlanners: order.creative_planners,
      completedDesigners: order.completed_designers,
      viewerIsDesigner:
        order.designer_user_ids?.includes(currentUserId.value ?? '') ?? false,
      viewerCompletedDesigner:
        order.completed_designer_ids?.includes(currentUserId.value ?? '') ??
        false,
      requiredQuantity: order.quantity ?? 0,
      uploadedQuantity: order.uploaded_quantity ?? 0,
      acceptedQuantity: order.accepted_quantity ?? 0,
      rejectedQuantity: order.rejected_quantity ?? 0,
      pendingReviewQuantity: order.pending_review_quantity ?? 0,
      remainingQuantity: Math.max(
        0,
        (order.quantity ?? 0) - (order.uploaded_quantity ?? 0),
      ),
      progress: order.progress ?? 0,
      lastUploadedAt: null,
    },
    owner: projection.owner,
    ownerName: projection.owner,
    progress: projection.progress,
    project: projection.project,
    route: '/requirement/detail',
    sourceId: projection.legacyMaterialOrderId,
    status: projection.status,
    summary: projection.summary,
    title: projection.title,
    updatedAt: projection.updatedAt,
  };
}

/** 素材列表负责人展示工单提交人；分配关系仍用于权限及侧栏筛选。 */
function taskProjectOwner(input: unknown) {
  const task = resolveTask(input);
  if (!task) return '—';
  return task.kind === 'material' ? task.createdBy || '未知创建人' : task.owner;
}

function materialParticipantNames(
  input: unknown,
  role: 'creativePlanner' | 'designer',
) {
  const task = resolveTask(input);
  const names =
    role === 'designer'
      ? task?.materialUpload?.designers
      : task?.materialUpload?.creativePlanners;
  return names?.join('、') || '未分配';
}

/** 素材任务使用制作状态文案，投放任务保留原状态名称。 */
function taskStatusLabel(input: unknown) {
  const task = resolveTask(input);
  if (!task) return '—';
  return task.kind === 'material' && task.status === 'doing'
    ? '制作中'
    : statusMeta[task.status].label;
}

/** 素材列表展示工单号，内部任务 ID 继续用于定位和操作。 */
function taskDisplayNumber(input: unknown) {
  const task = resolveTask(input);
  if (!task) return '—';
  return task.kind === 'material'
    ? task.materialUpload?.orderNo || '—'
    : task.id;
}

function isMaterialCreator() {
  return userRoles.value.includes('creator');
}

async function loadLegacyMaterialOrders(
  requestSequence: number,
  loadAll: boolean,
) {
  const scope = isSharedView.value
    ? 'SHARED'
    : activeSection.value === 'followed'
      ? 'FOLLOWED'
      : activeSection.value === 'assigned'
        ? 'ASSIGNED'
        : activeSection.value === 'quick' && quickFilter.value === 'created'
          ? 'CREATED'
          : activeSection.value === 'quick' && quickFilter.value === 'assigned'
            ? 'ASSIGNED'
            : activeSection.value === 'quick'
              ? 'ALL'
              : 'OWNER';
  // 固定本轮查询条件；后台逐页取齐不会受列表页码或中途修改筛选的影响。
  const query: ListOrderParams = {
    ...materialFilters.value,
    keyword: materialFilters.value.keyword || undefined,
    scope,
    status: materialFixedStatus.value?.value ?? materialFilters.value.status,
    page_size: loadAll ? taskOverviewPageSize : materialPageSize.value,
  };
  const readPage = async (pageNumber: number) => {
    const response = await listMaterialOrders({ ...query, page: pageNumber });
    const items = readLegacyMaterialOrderSummaries(response);
    const page = response?.data ?? response;
    return {
      items,
      total: typeof page?.total === 'number' ? page.total : items.length,
      materialTotal:
        typeof page?.material_total === 'number' ? page.material_total : 0,
    };
  };
  const firstPage = await readPage(loadAll ? 1 : materialPage.value);
  if (requestSequence !== taskRequestSequence) return;
  const items = loadAll
    ? await loadAllTaskPages(
        firstPage,
        readPage,
        () => requestSequence === taskRequestSequence,
        taskOverviewPageSize,
      )
    : firstPage.items;
  return items ? { ...firstPage, items } : undefined;
}

const availableTasks = computed(() => {
  if (demoMode) return filterDemoTasks(demoActor.value, tasks.value);
  return tasks.value.filter(
    (task) =>
      showAllRoles.value ||
      task.createdBy === currentUserName.value ||
      task.owner === currentUserName.value ||
      task.audiences.includes('all') ||
      task.audiences.some((audience) => userRoles.value.includes(audience)),
  );
});

/**
 * 优先展示服务端全量汇总。开发环境尚未更新任务中心接口、或接口暂时失败时，
 * 仍用已加载的任务生成页脚，避免汇总区被隐藏；该兜底仅代表当前已加载数据。
 */
const displayTaskSummary = computed<TaskCenterSummary | undefined>(() => {
  if (taskCenterSummary.value) return taskCenterSummary.value;
  if (!availableTasks.value.length) return undefined;

  const now = Date.now();
  const dueSoonAt = now + 24 * 60 * 60 * 1000;
  const activeStatuses: TaskStatus[] = [
    'assigned_pending_confirmation',
    'doing',
    'pending',
    'pending_acceptance',
    'pending_assignment',
    'partially_completed',
  ];
  const activeTasks = availableTasks.value.filter((task) =>
    activeStatuses.includes(task.status),
  );
  const dueSoonCount = activeTasks.filter((task) => {
    const deadline = taskDeadline(task);
    return !Number.isNaN(deadline) && deadline >= now && deadline <= dueSoonAt;
  }).length;
  const overdueCount = activeTasks.filter((task) => {
    const deadline = taskDeadline(task);
    return !Number.isNaN(deadline) && deadline < now;
  }).length;
  const materialTasks = availableTasks.value.filter(
    (task) => task.kind === 'material',
  );
  const materialUploads = materialTasks.flatMap((task) =>
    task.materialUpload ? [task.materialUpload] : [],
  );

  return {
    dueSoonCount,
    inProgressCount: activeTasks.length,
    material: {
      orderCount: new Set(materialUploads.map((upload) => upload.orderId)).size,
      requiredQuantity: materialUploads.reduce(
        (total, upload) => total + (upload.requiredQuantity ?? 0),
        0,
      ),
      syncedTaskCount: materialUploads.length,
      taskCount: materialTasks.length,
      uploadedQuantity: materialUploads.reduce(
        (total, upload) => total + upload.uploadedQuantity,
        0,
      ),
    },
    overdueCount,
    pendingAcceptanceCount: availableTasks.value.filter(
      (task) => task.status === 'pending_acceptance',
    ).length,
    riskCount: dueSoonCount + overdueCount,
    totalCount: availableTasks.value.length,
  };
});

const taskActivities = ref<TaskActivityEvent[]>([]);
const activityLoading = ref(false);
const activityError = ref('');

const { canCreateMaterialOrder } = useMaterialOrderAccess();
const { canCreateDeliveryTask } = useDeliveryTaskAccess();

const canCreateDeliveryTaskEntry = computed(() =>
  demoMode
    ? canDemoAction(demoActor.value, 'task.create')
    : canCreateDeliveryTask.value,
);

const canCreateTask = computed(
  () => canCreateMaterialOrder.value || canCreateDeliveryTaskEntry.value,
);

const deliveryDrafts = computed(() =>
  availableTasks.value.filter((task) => task.status === 'draft'),
);

const allowedKinds = computed<TaskKind[]>(() => [
  ...new Set(availableTasks.value.map((task) => task.kind)),
]);

const sourceOptions = computed(() => [
  { label: '全部来源', value: 'all' },
  ...allowedKinds.value.map((kind) => ({
    label: kindMeta[kind].label,
    value: kind,
  })),
]);

const statusOptions = computed(() => [
  { label: '全部状态', value: 'all' },
  { label: '待分配', value: 'pending_assignment' },
  { label: '部分完成', value: 'partially_completed' },
  ...(activeTaskTab.value === 'material'
    ? []
    : [{ label: '待确认', value: 'assigned_pending_confirmation' }]),
  { label: '待处理', value: 'pending' },
  { label: '待验收', value: 'pending_acceptance' },
  {
    label: activeTaskTab.value === 'material' ? '制作中' : '待提交',
    value: 'doing',
  },
  { label: '即将超时', value: 'risk' },
  { label: '已完成', value: 'done' },
  { label: '已驳回', value: 'rejected' },
  { label: '已撤回', value: 'withdrawn' },
]);

const sortOptions = [
  { label: '默认排序', value: 'default' },
  { label: '风险状态优先', value: 'status' },
  { label: '进度从高到低', value: 'progress-desc' },
  { label: '按任务名称', value: 'title' },
];

const groupOptions = [
  { label: '不分组', value: 'none' },
  { label: '按项目分组', value: 'project' },
  { label: '按任务来源分组', value: 'kind' },
  { label: '按状态分组', value: 'status' },
];

const platformLabels: Record<string, string> = {
  facebook: 'Facebook',
  google: 'Google',
  kwai: 'Kwai',
  tiktok: 'TikTok',
};

const completionPlatformOptions = computed(() => {
  const plannedPlatforms = completionTask.value?.delivery?.platforms ?? [];
  const platforms = plannedPlatforms.length
    ? plannedPlatforms
    : Object.keys(platformLabels);
  return [
    ...new Set(platforms.map((platform) => platform.trim()).filter(Boolean)),
  ].map((platform) => ({
    label: platformLabels[platform.toLowerCase()] ?? platform,
    value: platform,
  }));
});

const completionEntryModeOptions = [
  { label: '选择投放中心数据', value: 'delivery-center' },
  { label: '手动填写', value: 'manual' },
];

const currencyOptions = ['USD', 'EUR', 'JPY', 'BRL', 'IDR', 'THB'].map(
  (value) => ({ label: value, value }),
);

const deliveryStatusOptions: Array<{
  label: string;
  value: AmDeliveryStatus;
}> = [
  { label: '正常投放', value: 'active' },
  { label: '部分成功', value: 'partial' },
  { label: '已暂停', value: 'paused' },
  { label: '投放失败', value: 'failed' },
];

const deliveryStatusLabels: Record<AmDeliveryStatus, string> = {
  active: '正常投放',
  failed: '投放失败',
  partial: '部分成功',
  paused: '已暂停',
};

const viewOptions = [
  { label: '列表', value: 'list' },
  { label: '看板', value: 'board' },
  { label: '仪表盘', value: 'dashboard' },
];

const quickItems: Array<{
  icon: string;
  key: QuickFilter;
  label: string;
}> = [
  { icon: 'lucide:list-checks', key: 'all', label: '全部任务' },
  { icon: 'lucide:square-pen', key: 'created', label: '我创建的' },
  { icon: 'lucide:user-round-plus', key: 'assigned', label: '我分配的' },
  { icon: 'lucide:share-2', key: 'shared', label: '分享给我的' },
  {
    icon: 'lucide:users-round',
    key: 'pending_assignment',
    label: '待分配',
  },
  { icon: 'lucide:clipboard-check', key: 'confirmation', label: '待确认' },
  { icon: 'lucide:upload-cloud', key: 'submission', label: '待提交' },
  { icon: 'lucide:clipboard-check', key: 'acceptance', label: '待验收' },
  { icon: 'lucide:circle-check-big', key: 'completed', label: '已完成' },
  { icon: 'lucide:circle-x', key: 'failed', label: '已驳回' },
  { icon: 'lucide:pause', key: 'paused', label: '已暂停' },
  { icon: 'lucide:ban', key: 'cancelled', label: '已取消' },
];

// 投放任务在创建时直接指定投手，分配相关导航仅用于素材任务。
const visibleQuickItems = computed(() =>
  activeTaskTab.value === 'delivery'
    ? quickItems.filter(
        (item) =>
          ![
            'assigned',
            'pending_assignment',
            'shared',
            'paused',
            'cancelled',
          ].includes(item.key),
      )
    : quickItems.filter(
        (item) =>
          item.key !== 'confirmation' &&
          (item.key !== 'pending_assignment' ||
            userRoles.value.includes('creator_leader')) &&
          (item.key !== 'shared' || userRoles.value.includes('operator')),
      ),
);

const sectionTitle = computed(() => {
  if (activeSection.value === 'followed') return '我关注的';
  if (activeSection.value === 'assigned') return '我分配的';
  if (activeSection.value === 'activity') return '任务动态';
  if (activeSection.value === 'drafts') return '草稿箱';
  if (activeSection.value === 'owned') return '我负责的';
  return (
    quickItems.find((item) => item.key === quickFilter.value)?.label ??
    '我负责的'
  );
});

const baseTasks = computed(() => {
  // 素材的状态和可见范围已由服务端筛选，不能再按展示状态裁剪当前页。
  if (isMaterialList.value) return availableTasks.value;
  if (activeSection.value === 'followed') {
    return availableTasks.value.filter((task) => task.followed);
  }
  if (
    !demoMode &&
    activeSection.value === 'quick' &&
    quickFilter.value !== 'failed'
  ) {
    return availableTasks.value;
  }

  if (quickFilter.value === 'paused' || quickFilter.value === 'cancelled') {
    return availableTasks.value.filter(
      (task) => task.status === quickFilter.value,
    );
  }
  if (quickFilter.value === 'failed') {
    return availableTasks.value.filter(
      (task) => task.status === 'rejected' || task.status === 'withdrawn',
    );
  }

  if (quickFilter.value === 'created') {
    return availableTasks.value.filter(
      (task) =>
        createdTaskIds.has(task.id) || task.createdBy === currentUserName.value,
    );
  }
  if (quickFilter.value === 'assigned') {
    return availableTasks.value.filter(
      (task) =>
        assignedTaskIds.has(task.id) ||
        (task.createdBy === currentUserName.value &&
          task.owner !== currentUserName.value),
    );
  }
  if (quickFilter.value === 'acceptance') {
    return availableTasks.value.filter(
      (task) =>
        task.status === 'pending_acceptance' &&
        (createdTaskIds.has(task.id) ||
          task.createdBy === currentUserName.value),
    );
  }
  if (quickFilter.value === 'completed') {
    return availableTasks.value.filter((task) => task.status === 'done');
  }
  if (quickFilter.value === 'submission') {
    return availableTasks.value.filter(
      (task) =>
        task.status === 'doing' || task.status === 'partially_completed',
    );
  }
  if (quickFilter.value === 'confirmation') {
    return availableTasks.value.filter(
      (task) => task.status === 'assigned_pending_confirmation',
    );
  }
  return availableTasks.value;
});

const filteredTasks = computed(() => {
  const keyword =
    (isDeliveryList.value || isMaterialList.value) && !demoMode
      ? ''
      : searchKeyword.value.trim().toLocaleLowerCase();
  const statusPriority: Record<TaskStatus, number> = {
    risk: 0,
    rejected: 1,
    draft: 2,
    pending_assignment: 3,
    assigned_pending_confirmation: 4,
    pending_acceptance: 5,
    pending: 6,
    doing: 7,
    partially_completed: 8,
    done: 9,
    withdrawn: 10,
    paused: 11,
    cancelled: 12,
  };

  if (isMaterialList.value) return baseTasks.value;
  const result = baseTasks.value.filter((task) => {
    const matchesKeyword =
      !keyword ||
      [
        task.title,
        taskDisplayNumber(task),
        task.id,
        task.summary,
        task.project,
        task.owner,
        taskProjectOwner(task),
        ...(task.materialUpload?.designers ?? []),
        ...(task.materialUpload?.creativePlanners ?? []),
      ].some((value) => value.toLocaleLowerCase().includes(keyword));
    const matchesSource =
      sourceFilter.value === 'all' || task.kind === sourceFilter.value;
    const matchesStatus =
      statusFilter.value === 'all' || task.status === statusFilter.value;
    return matchesKeyword && matchesSource && matchesStatus;
  });

  if (sortBy.value === 'progress-desc') {
    return [...result].sort((left, right) => right.progress - left.progress);
  }
  if (sortBy.value === 'status') {
    return [...result].sort(
      (left, right) =>
        statusPriority[left.status] - statusPriority[right.status],
    );
  }
  if (sortBy.value === 'title') {
    return [...result].sort((left, right) =>
      left.title.localeCompare(right.title, 'zh-CN'),
    );
  }
  return result;
});

const groupedSections = computed<TaskGroup[]>(() => {
  if (groupBy.value === 'none') {
    return [
      { key: 'all', label: sectionTitle.value, tasks: filteredTasks.value },
    ];
  }

  const groups = new Map<string, WorkbenchTask[]>();
  for (const task of filteredTasks.value) {
    let key: string = task.status;
    if (groupBy.value === 'project') key = task.project;
    if (groupBy.value === 'kind') key = task.kind;
    groups.set(key, [...(groups.get(key) ?? []), task]);
  }

  return [...groups.entries()].map(([key, groupedTasks]) => {
    let label = key;
    if (groupBy.value === 'kind') label = kindMeta[key as TaskKind].label;
    if (groupBy.value === 'status')
      label =
        activeTaskTab.value === 'material' && key === 'doing'
          ? '制作中'
          : statusMeta[key as TaskStatus].label;
    return { key, label, tasks: groupedTasks };
  });
});

const boardColumns = computed(() =>
  (
    [
      'pending_assignment',
      ...(activeTaskTab.value === 'material'
        ? []
        : ['assigned_pending_confirmation']),
      'pending',
      'doing',
      'partially_completed',
      ...(activeTaskTab.value === 'material'
        ? (['paused', 'cancelled'] as const)
        : []),
      'risk',
      'pending_acceptance',
      'done',
      'rejected',
      'withdrawn',
    ] as TaskStatus[]
  ).map((status) => ({
    ...statusMeta[status],
    label:
      activeTaskTab.value === 'material' && status === 'doing'
        ? '制作中'
        : statusMeta[status].label,
    key: status,
    tasks: filteredTasks.value.filter((task) => task.status === status),
  })),
);

// 仪表盘复用看板的状态分组，保证所有状态（包括已驳回）统计一致。
const summaryCards = computed(() =>
  boardColumns.value.map(({ tasks: columnTasks, ...column }) => ({
    ...column,
    value: columnTasks.length,
  })),
);

const projectSummary = computed(() => {
  const projects = new Map<string, WorkbenchTask[]>();
  for (const task of filteredTasks.value) {
    projects.set(task.project, [...(projects.get(task.project) ?? []), task]);
  }
  return [...projects.entries()].map(([project, projectTasks]) => {
    const completed = projectTasks.filter(
      (task) => task.status === 'done',
    ).length;
    const total = projectTasks.length;
    // 未全部完成时最高显示 99%，避免四舍五入误显示为全部完成。
    const completionPercent =
      completed === total
        ? 100
        : Math.min(99, Math.round((completed / total) * 100));
    return {
      completed,
      // 素材项目按已完成工单占比统计，与右侧数量使用同一口径。
      percent:
        activeTaskTab.value === 'material'
          ? completionPercent
          : Math.round(
              projectTasks.reduce((sum, task) => sum + task.progress, 0) /
                total,
            ),
      project,
      total,
    };
  });
});

// 操作列按当前可用操作数分配宽度，确保按钮平铺且不被固定列裁切。
const materialActionColumnWidth = computed(() => {
  const count = filteredTasks.value.reduce(
    (maximum, task) => Math.max(maximum, materialTaskActions(task).length),
    0,
  );
  return Math.max(72, count * 40 + Math.max(0, count - 1) * 4 + 32);
});

const columns = computed<TableColumnsType<WorkbenchTask>>(() => [
  { key: 'task', title: '任务', width: 240 },
  ...(activeTaskTab.value === 'delivery'
    ? [{ key: 'am', title: '项目 / AM', width: 180 }]
    : []),
  {
    key: 'project',
    responsive: ['lg'],
    title: activeTaskTab.value === 'delivery' ? '投放负责人' : '项目 / 负责人',
    width: 132,
  },
  ...(activeTaskTab.value === 'material'
    ? [
        { key: 'materialParticipants', title: '创意策划 / 素材', width: 160 },
        { key: 'materialUpload', title: '需求 → 实际上传', width: 140 },
      ]
    : []),
  { key: 'dueAt', title: '截止时间', width: 110 },
  { key: 'status', title: '状态', width: 80 },
  {
    fixed: 'right',
    key: 'actions',
    title: '操作',
    width:
      activeTaskTab.value === 'material'
        ? materialActionColumnWidth.value
        : 176,
  },
]);

const tableScrollWidth = computed(() =>
  activeTaskTab.value === 'material'
    ? columns.value.reduce(
        (total, column) =>
          total + (typeof column.width === 'number' ? column.width : 0),
        0,
      )
    : 870,
);

const actionContext = computed<TaskActionContext>(() => {
  if (activeSection.value === 'followed' || isSharedView.value)
    return 'view-only';
  if (quickFilter.value === 'acceptance') return 'created';
  if (quickFilter.value === 'created') return 'created';
  if (quickFilter.value === 'assigned') return 'assigned';
  if (quickFilter.value === 'completed') return 'completed';
  return 'owned';
});

const editingTask = computed(() =>
  tasks.value.find((task) => task.id === editingTaskId.value),
);

const progressTask = computed(() =>
  tasks.value.find((task) => task.id === progressTaskId.value),
);

const detailTask = computed(() =>
  tasks.value.find((task) => task.id === detailTaskId.value),
);

const completionTask = computed(() =>
  tasks.value.find((task) => task.id === completionTaskId.value),
);

const deliverySourceRangeAdjustment = computed(() => {
  const plannedStart = completionTask.value?.delivery?.startAt?.slice(0, 10);
  const today = todayText();
  const [startDate, endDate] = completionForm.sourceDateRange;
  return plannedStart &&
    plannedStart > today &&
    startDate === today &&
    endDate === today
    ? plannedStart
    : '';
});

const materialDeliveryTask = computed(() =>
  tasks.value.find((task) => task.id === materialDeliveryTaskId.value),
);

const materialDeliveryPersistKey = computed(() => {
  const task = materialDeliveryTask.value;
  return task?.sourceId
    ? `task-center:material-order:${task.sourceId}:task:${task.id}`
    : 'task-center:material-order:unlinked';
});

const deliverySourceMetadata = computed(() => {
  const campaigns = deliveryCampaigns.value;
  const accountNames = [
    ...new Set(
      campaigns.map((campaign) => campaign.accountName).filter(Boolean),
    ),
  ];
  const agencyLineIds = [
    ...new Set(
      campaigns.map((campaign) => campaign.agencyLineId).filter(Boolean),
    ),
  ];
  const agencyLineNames = [
    ...new Set(
      campaigns.map((campaign) => campaign.agencyLineName).filter(Boolean),
    ),
  ];
  const syncedAt = campaigns
    .map((campaign) => campaign.syncedAt)
    .sort()
    .at(-1);
  const dataCutoffAt = campaigns
    .map((campaign) => campaign.dataCutoffAt ?? campaign.syncedAt)
    .sort()
    .at(-1);
  return {
    accountName: accountNames.length === 1 ? accountNames[0] : undefined,
    agencyLineId: agencyLineIds.length === 1 ? agencyLineIds[0] : undefined,
    agencyLineName:
      agencyLineNames.length === 1 ? agencyLineNames[0] : undefined,
    campaignName: campaigns.map((campaign) => campaign.name).join(' / '),
    dataCutoffAt,
    syncedAt,
  };
});

const acceptanceTask = computed(() =>
  tasks.value.find((task) => task.id === acceptanceTaskId.value),
);

const assignmentTask = computed(() =>
  tasks.value.find((task) => task.id === assignmentTaskId.value),
);

const declineTask = computed(() =>
  tasks.value.find((task) => task.id === declineTaskId.value),
);

const assignmentCandidates = computed(() => {
  const task = assignmentTask.value;
  if (!task) return [];
  const roleId = task.kind === 'material' ? 'creative-lead' : 'operator-lead';
  return demoRoleProfiles
    .filter((profile) => profile.id === roleId)
    .map((profile) => ({
      label: `${profile.realName} · ${profile.label}`,
      profile,
      value: profile.userId,
    }));
});

const acceptanceCompletion = computed(
  () => acceptanceTask.value?.completion?.current,
);

function completionRecords(task?: TaskCenterTask) {
  const completion = task?.completion;
  if (!completion) return [];
  return [
    ...(completion.current ? [completion.current] : []),
    ...[...completion.history].reverse(),
  ];
}

/** 每个团队—投手执行项仅取其最新一版交付，用于验收清单。 */
function currentDeliveryRecordsForTask(task?: TaskCenterTask) {
  const allocations = task?.delivery?.allocations ?? [];
  const records = completionRecords(task);
  return allocations.flatMap((allocation) =>
    records
      .filter(
        (record) =>
          record.kind === 'am' && record.allocationId === allocation.id,
      )
      .sort((left, right) => right.versionNo - left.versionNo)
      .slice(0, 1),
  );
}

const acceptanceDeliveryRecords = computed(() =>
  acceptanceTask.value?.kind === 'am'
    ? currentDeliveryRecordsForTask(acceptanceTask.value).filter(
        (record) => record.status === 'submitted',
      )
    : [],
);

const selectedAcceptanceCompletion = computed(() => {
  if (acceptanceTask.value?.kind !== 'am') return acceptanceCompletion.value;
  return (
    acceptanceDeliveryRecords.value.find(
      (record) => record.submissionId === selectedAcceptanceSubmissionId.value,
    ) ?? acceptanceDeliveryRecords.value[0]
  );
});

const detailCompletionRecords = computed(() => {
  return completionRecords(detailTask.value);
});

function deliveryRecordsForAllocation(allocationId?: string) {
  if (!allocationId) return [];
  return detailCompletionRecords.value
    .filter(
      (record) => record.kind === 'am' && record.allocationId === allocationId,
    )
    .sort((left, right) => right.versionNo - left.versionNo);
}

const currentDeliveryCompletionRecords = computed(() => {
  return currentDeliveryRecordsForTask(detailTask.value);
});

const displayedDetailCompletionRecords = computed(() =>
  detailTask.value?.kind === 'am'
    ? currentDeliveryCompletionRecords.value
    : detailCompletionRecords.value,
);

function deliveryAllocationNameForTask(
  record: TaskCompletionRecord,
  task?: TaskCenterTask,
) {
  if (record.kind !== 'am') return '';
  const allocation = task?.delivery?.allocations.find(
    (item) => item.id === record.allocationId,
  );
  if (!allocation) return record.submittedBy;
  return `${allocation.teamName || allocation.team} · ${allocation.owner}`;
}

function deliveryAllocationName(record: TaskCompletionRecord) {
  return deliveryAllocationNameForTask(record, detailTask.value);
}

function openDeliveryHistory(record: TaskCompletionRecord) {
  if (record.kind !== 'am') return;
  deliveryHistoryRecords.value = deliveryRecordsForAllocation(
    record.allocationId,
  ).slice(1);
  deliveryHistoryTitle.value = `${deliveryAllocationName(record)}的历史版本`;
  deliveryHistoryModalOpen.value = true;
}

const detailAcceptanceRecords = computed(() =>
  [...(detailTask.value?.completion?.acceptanceHistory ?? [])].reverse(),
);

const completionAccept = computed(() => {
  if (completionTask.value?.kind === 'material') {
    return '.png,.jpg,.jpeg,.webp,.gif,.mp4,.mov,.webm,.mkv,.avi,.zip,.7z';
  }
  if (completionTask.value?.kind === 'am') {
    return '.png,.jpg,.jpeg,.webp,.pdf,.csv,.xls,.xlsx,.zip,.7z';
  }
  return '.png,.jpg,.jpeg,.webp,.pdf,.doc,.docx,.xls,.xlsx,.zip,.7z';
});

function setSection(section: MainSection) {
  materialPage.value = 1;
  materialFilters.value.status = undefined;
  if (section === 'assigned' && activeTaskTab.value === 'material') {
    setQuickFilter('assigned');
    return;
  }
  deliveryPage.value = 1;
  activeSection.value = section;
  quickFilter.value = 'all';
  void loadServerTasks().catch((error) => {
    message.error(error instanceof Error ? error.message : '任务数据加载失败');
  });
}

function setTaskTab(tab: TaskTab) {
  if (activeTaskTab.value === tab) return;
  activeTaskTab.value = tab;
  materialPage.value = 1;
  deliveryPage.value = 1;
  deliveryQuery.value = '';
  activeSection.value = 'owned';
  quickFilter.value = 'all';
  taskActivities.value = [];
  resetFilters();
  void loadServerTasks().catch((error) => {
    message.error(error instanceof Error ? error.message : '任务数据加载失败');
  });
}

function setQuickFilter(filter: QuickFilter) {
  if (!visibleQuickItems.value.some((item) => item.key === filter)) return;
  materialPage.value = 1;
  materialFilters.value.status = undefined;
  deliveryPage.value = 1;
  activeSection.value = 'quick';
  quickFilter.value = filter;
  void loadServerTasks().catch((error) => {
    message.error(error instanceof Error ? error.message : '任务数据加载失败');
  });
}

function resetFilters() {
  materialFilters.value = emptyMaterialTaskFilters();
  searchKeyword.value = '';
  sourceFilter.value = 'all';
  statusFilter.value = 'all';
  sortBy.value = 'default';
  groupBy.value = 'none';
}

/** 投放关键词提交服务端查询；其他筛选作用于当前视图已加载的数据。 */
function searchDeliveryTasks() {
  if (!isDeliveryList.value) return;
  deliveryQuery.value = searchKeyword.value.trim();
  deliveryPage.value = 1;
  void loadServerTasks().catch((error) => {
    message.error(error instanceof Error ? error.message : '任务查询失败');
  });
}

function handleDeliveryFilterChange() {
  if (!isDeliveryList.value) return;
  deliveryPage.value = 1;
  void loadServerTasks().catch((error) => {
    message.error(error instanceof Error ? error.message : '任务筛选失败');
  });
}

function changeDeliveryPage(page: number, pageSize: number) {
  deliveryPage.value = pageSize === deliveryPageSize.value ? page : 1;
  deliveryPageSize.value = pageSize;
  void loadServerTasks().catch((error) => {
    message.error(error instanceof Error ? error.message : '任务数据加载失败');
  });
}

async function resetTaskFilters() {
  resetFilters();
  if (activeTaskTab.value === 'material') {
    await resetMaterialQueryState();
    void loadServerTasks();
  } else if (isDeliveryList.value) {
    await resetDeliveryQueryState();
    searchKeyword.value = deliveryQuery.value;
    searchDeliveryTasks();
  }
}

function applyMaterialFilters(
  filters: MaterialTaskFilterValues,
  nextGroupBy: GroupBy = 'none',
) {
  materialFilters.value = filters;
  groupBy.value = nextGroupBy;
  materialPage.value = 1;
  void loadServerTasks();
}

function changeMaterialPage(page: number, pageSize: number) {
  materialPage.value = pageSize === materialPageSize.value ? page : 1;
  materialPageSize.value = pageSize;
  void loadServerTasks();
}

async function refreshTaskCenter() {
  await loadServerTasks();
  if (taskResultsError.value) return;
  message.success('任务中心已刷新');
}

async function toggleFollow(taskId: string) {
  const task = tasks.value.find((item) => item.id === taskId);
  if (!task || pendingFollowTaskIds.has(taskId)) return;
  if (demoMode) {
    taskCenterStore.toggleFollow(taskId);
    return;
  }
  pendingFollowTaskIds.add(taskId);
  try {
    let followed = !task.followed;
    if (task.kind === 'material') {
      // 素材关注使用 Mongo 工单 ID，投放任务继续使用原任务接口。
      const orderId = task.legacyMaterialOrderId ?? materialOrderIds(task)[0];
      if (!orderId) throw new Error('缺少素材工单 ID，请刷新后重试');
      const result = followed
        ? await followMaterialOrder(orderId)
        : await unfollowMaterialOrder(orderId);
      followed = result.followed;
    } else if (followed) {
      await followTaskApi(taskId);
    } else {
      await unfollowTaskApi(taskId);
    }
    taskCenterStore.patchTask(taskId, { followed });
    message.success(followed ? '已添加到我的关注' : '已取消关注');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '关注状态更新失败');
  } finally {
    pendingFollowTaskIds.delete(taskId);
  }
}

function continueDeliveryDraft(draftId: string) {
  const draft = deliveryDrafts.value.find((task) => task.draftId === draftId);
  if (draft) void openTask(draft);
}

async function removeTaskDraft(draftId: string) {
  const draft = deliveryDrafts.value.find((item) => item.draftId === draftId);
  if (draft?.kind === 'material') {
    await batchDeleteMaterialOrders([draftId], 'draft');
  } else {
    await deleteTaskDraftApi(draftId);
  }
  await loadServerTasks();
  message.success('草稿已删除');
}

function isFollowed(taskId: string) {
  return Boolean(tasks.value.find((task) => task.id === taskId)?.followed);
}

function canCreateMaterialFromTask(task: undefined | WorkbenchTask) {
  return Boolean(
    task &&
      canCreateMaterialOrder.value &&
      task.kind === 'am' &&
      task.projectId?.trim() &&
      task.status !== 'withdrawn',
  );
}

function openMaterialTaskCreate(task: undefined | WorkbenchTask = undefined) {
  if (!canCreateMaterialOrder.value) {
    message.warning('没有新建素材工单权限');
    return;
  }
  const sourceTask = task && canCreateMaterialFromTask(task) ? task : undefined;
  void router.push({
    path: '/workbench/tasks/create-material',
    query: {
      new: '1',
      ...(sourceTask
        ? {
            projectId: sourceTask.projectId,
            sourceTaskId: sourceTask.id,
          }
        : {}),
      returnTo: '/workbench/tasks',
      source: 'task-center',
    },
  });
}

function canCreateResourceApplicationFromTask(task: undefined | WorkbenchTask) {
  return Boolean(
    task &&
      (!demoMode || canDemoAction(demoActor.value, 'resource.apply')) &&
      task.kind === 'am' &&
      task.projectId?.trim() &&
      task.status !== 'withdrawn',
  );
}

function openResourceApplicationCreate(task: undefined | WorkbenchTask) {
  if (!task || !canCreateResourceApplicationFromTask(task)) {
    message.warning('该任务缺少有效项目上下文，无法发起资源申请');
    return;
  }
  detailDrawerOpen.value = false;
  void router.push({
    path: '/workbench/applications/create',
    query: {
      new: '1',
      projectId: task.projectId,
      projectName: task.project,
      returnTo: '/workbench/tasks',
      source: 'task-center',
      sourceTaskId: task.id,
    },
  });
}

const handleCreateMenu: MenuProps['onClick'] = ({ key }) => {
  if (String(key) === 'material') {
    openMaterialTaskCreate();
    return;
  }
  void router.push('/workbench/tasks/create-delivery');
};

/** 查看素材任务使用独立全屏抽屉，关闭后直接回到当前列表和筛选状态。 */
function openMaterialTaskDetail(
  orderId: string,
  action: 'view' | 'deliver' = 'view',
) {
  if (!orderId.trim()) return;
  detailDrawerOpen.value = false;
  materialDetailOrderId.value = orderId;
  materialDetailInitialAction.value = action;
  materialDetailOpen.value = true;
}

function openRelatedMaterialOrder(orderId: string) {
  openMaterialTaskDetail(orderId);
}

function taskFileMeta(
  file: TaskDetail['taskFiles'][number],
): TaskAttachmentMeta {
  return {
    contentType: file.mimeType,
    id: file.id,
    name: file.originalName,
    objectKey: file.id,
    serverFileId: file.id,
    size: file.fileSize,
    type: file.extension || file.mimeType,
  };
}

function submissionFiles(
  detail: TaskDetail,
  targetType: string,
  targetId: string,
) {
  return detail.taskFiles
    .filter(
      (file) => file.targetType === targetType && file.targetId === targetId,
    )
    .map((file) => taskFileMeta(file));
}

function serverCompletion(detail: TaskDetail): TaskCompletionState {
  const reviewStatus = (status: 'ACCEPTED' | 'PENDING' | 'REJECTED') =>
    status === 'ACCEPTED'
      ? ('accepted' as const)
      : status === 'REJECTED'
        ? ('rejected' as const)
        : ('submitted' as const);
  const records: TaskCompletionRecord[] =
    detail.task.taskType === 'DELIVERY'
      ? detail.deliverySubmissions.map((submission) => ({
          accountId: submission.adAccountIds.join(' / '),
          accountName: submission.adAccountName,
          actualBudget: submission.actualBudget,
          actualSpend: submission.actualSpend,
          actualStartAt: submission.actualStartAt,
          adCount: submission.adCount,
          adsetCount: submission.adsetCount,
          allocationId: submission.allocationId,
          campaignCount: submission.campaignCount,
          campaignIds: submission.objects
            .filter((object) => object.objectType === 'CAMPAIGN')
            .map((object) => object.objectId),
          currency: submission.currency,
          dailyReportSpend: submission.dailyReportSpend,
          deliveryStatus:
            submission.deliveryStatus.toLowerCase() as AmDeliveryStatus,
          entryMode: 'manual' as const,
          exceptionNote: submission.exceptionNote ?? '',
          files: submissionFiles(detail, 'DELIVERY_SUBMISSION', submission.id),
          kind: 'am' as const,
          note: submission.submissionNote ?? '',
          platform: submission.platform,
          sourceAdIds: submission.objects
            .filter((object) => object.objectType === 'AD')
            .map((object) => object.objectId),
          sourceAdsetIds: submission.objects
            .filter((object) => object.objectType === 'AD_SET')
            .map((object) => object.objectId),
          status: reviewStatus(submission.reviewStatus),
          submissionId: submission.id,
          submittedAt: submission.submittedAt,
          submittedBy: submission.submittedByName,
          versionNo: submission.versionNo,
        }))
      : detail.materialSubmissions.map((submission) => ({
          deliveredQuantity: submission.deliveredQuantity,
          files: submissionFiles(detail, 'MATERIAL_SUBMISSION', submission.id),
          kind: 'material' as const,
          libraryStatus: submission.libraryStatus,
          note: submission.submissionNote ?? '',
          sourceOrderId: '',
          status: reviewStatus(submission.reviewStatus),
          submissionId: submission.id,
          submittedAt: submission.submittedAt,
          submittedBy: submission.submittedByName,
          versionNo: submission.versionNo,
        }));
  const submissions =
    detail.task.taskType === 'DELIVERY'
      ? detail.deliverySubmissions
      : detail.materialSubmissions;
  return {
    acceptanceHistory: submissions
      .filter((submission) => submission.reviewedAt && submission.reviewerName)
      .map((submission) => ({
        decision:
          submission.reviewStatus === 'ACCEPTED' ? 'accepted' : 'rejected',
        reason: submission.reviewComment ?? '',
        reviewedAt: submission.reviewedAt!,
        reviewer: submission.reviewerName!,
        reviewerId: submission.reviewerId,
        submissionId: submission.id,
        versionNo: submission.versionNo,
      })),
    current: records[0],
    history: records.slice(1).reverse(),
  };
}

/** 从列表或详情进入原工单编辑，提交后返回当前任务视图。 */
function openMaterialOrderEditor(orderId: string, preserveStatus = false) {
  materialDetailOpen.value = false;
  return router.push({
    path: '/workbench/tasks/create-material',
    query: {
      id: orderId,
      edit: '1',
      ...(preserveStatus ? { preserveStatus: '1' } : {}),
      source: 'task-center',
      returnTo: route.fullPath,
    },
  });
}

/** 原工单仅作为回填来源；不携带编辑 ID，保存时创建独立的新工单。 */
function openMaterialOrderResubmit(orderId: string) {
  if (!canCreateMaterialOrder.value) {
    message.warning('没有新建素材工单权限');
    return;
  }
  materialDetailOpen.value = false;
  return router.push({
    path: '/workbench/tasks/create-material',
    query: {
      resubmitOrderId: orderId,
      new: '1',
      source: 'task-center',
      returnTo: route.fullPath,
    },
  });
}

async function openTask(task: unknown) {
  const current = resolveTask(task);
  if (!current) return;
  if (isLegacyMaterialOrderTask(current)) {
    openLegacyMaterialOrder(current, 'view');
    return;
  }
  if (current.status === 'draft' && current.draftId) {
    await router.push({
      path: current.route,
      query: {
        draftId: current.draftId,
        ...(current.kind === 'material'
          ? { id: current.draftId, edit: '1', source: 'task-center' }
          : {}),
      },
    });
    return;
  }
  detailTaskId.value = current.id;
  detailDrawerOpen.value = true;
  if (!demoMode) {
    try {
      const detail = await getTaskApi(current.id);
      taskCenterStore.patchTask(current.id, {
        completion: serverCompletion(detail),
        delivery: projectDeliveryTaskDetail(detail, current.project),
      });
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : '任务交付详情加载失败',
      );
    }
  }
}

function openTaskActivity(activity: TaskActivityEvent) {
  if (activity.sourceType === 'material-task') {
    openMaterialTaskDetail(activity.sourceId);
    return;
  }
  const task = activity.taskId
    ? tasks.value.find((item) => item.id === activity.taskId)
    : undefined;
  if (task) {
    openTask(task);
    return;
  }
  void router.push(activity.targetPath);
}

function resolveTask(task: unknown) {
  if (!task || typeof task !== 'object') return;
  const taskId = (task as { id?: unknown }).id;
  if (typeof taskId !== 'string') return;
  return tasks.value.find((item) => item.id === taskId);
}

const { pendingOrderId: lifecyclePendingId, run: runMaterialLifecycle } =
  useMaterialOrderLifecycle(refreshAfterMaterialAssignment);

type MaterialTaskActionKey =
  | 'pause'
  | 'resume'
  | 'cancel'
  | 'share'
  | 'resubmit'
  | 'edit'
  | 'reedit'
  | 'view'
  | 'assign'
  | 'decline'
  | 'confirm'
  | 'upload'
  | 'complete'
  | 'accept';

/** 各素材操作独立判断，列表、移动列表、看板使用同一组入口。 */
function materialTaskActions(input: unknown) {
  const task = resolveTask(input);
  const actions: {
    key: MaterialTaskActionKey;
    label: string;
    shortLabel: string;
    danger?: boolean;
  }[] = [];
  if (!task || !isLegacyMaterialOrderTask(task)) return actions;
  actions.push({
    key: 'view',
    label: task.status === 'draft' ? '任务编辑' : '查看任务',
    shortLabel: task.status === 'draft' ? '编辑' : '查看',
  });
  if (task.status === 'draft' || task.status === 'cancelled') return actions;
  if (task.status === 'paused') {
    if (!isSharedView.value && task.materialPermissions?.resume)
      actions.push({ key: 'resume', label: '开启任务', shortLabel: '开启' });
    return actions;
  }
  if (isSharedView.value) {
    if (task.materialPermissions?.shared)
      actions.push({ key: 'accept', label: '验收任务', shortLabel: '验收' });
    return actions;
  }
  if (
    activeSection.value === 'quick' &&
    quickFilter.value === 'all' &&
    task.materialPermissions?.share
  ) {
    actions.push({ key: 'share', label: '分享工单', shortLabel: '分享' });
  }
  if (canResubmitTask(task))
    actions.push({ key: 'resubmit', label: '再次提交', shortLabel: '提交' });
  if (
    activeSection.value === 'quick' &&
    quickFilter.value === 'all' &&
    canReeditMaterialOrder({
      status: task.legacyMaterialOrderStatus ?? '',
      permissions: task.materialPermissions,
    })
  ) {
    actions.push({ key: 'reedit', label: '重新编辑', shortLabel: '编辑' });
  } else if (
    canEditRejectedMaterialOrder({
      status: task.legacyMaterialOrderStatus ?? '',
      permissions: task.materialPermissions,
    })
  ) {
    actions.push({ key: 'edit', label: '重新编辑', shortLabel: '编辑' });
  }
  if (canOperateAssignment(task))
    actions.push({ key: 'assign', label: '分配任务', shortLabel: '分配' });
  if (canDeclineTask(task))
    actions.push({
      key: 'decline',
      label: '驳回任务',
      shortLabel: '驳回',
      danger: true,
    });
  if (canConfirmTask(task))
    actions.push({ key: 'confirm', label: '确认任务', shortLabel: '确认' });
  if (task.materialPermissions?.upload)
    actions.push({ key: 'upload', label: '上传素材', shortLabel: '上传' });
  if (canChangeActiveStatus(task))
    actions.push({ key: 'complete', label: '完成任务', shortLabel: '完成' });
  if (canOperateAcceptance(task))
    actions.push({ key: 'accept', label: '验收任务', shortLabel: '验收' });
  if (task.materialPermissions?.pause)
    actions.push({ key: 'pause', label: '暂停任务', shortLabel: '暂停' });
  if (task.materialPermissions?.cancel)
    actions.push({
      key: 'cancel',
      label: '取消任务',
      shortLabel: '取消',
      danger: true,
    });
  return actions;
}

function runMaterialTaskAction(task: unknown, key: string) {
  if (!materialTaskActions(task).some((action) => action.key === key)) return;
  switch (key) {
    case 'pause':
    case 'resume':
    case 'cancel': {
      const current = resolveTask(task);
      if (current?.legacyMaterialOrderId)
        return runMaterialLifecycle(
          {
            id: current.legacyMaterialOrderId,
            title: current.title,
            version: current.materialOrderVersion ?? 0,
          },
          key,
        );
      return;
    }
    case 'share': {
      const current = resolveTask(task);
      if (current?.legacyMaterialOrderId) {
        materialShareOrderId.value = current.legacyMaterialOrderId;
        materialShareOpen.value = true;
      }
      return;
    }
    case 'resubmit':
      return resubmitTask(task);
    case 'view':
      return openTask(task);
    case 'reedit':
    case 'edit': {
      const current = resolveTask(task);
      if (current?.legacyMaterialOrderId) {
        return openMaterialOrderEditor(
          current.legacyMaterialOrderId,
          key === 'reedit',
        );
      }
      return;
    }
    case 'assign':
      return openAssignmentModal(task);
    case 'decline':
      return openDeclineModal(task);
    case 'confirm':
      return confirmAssignedTask(task);
    case 'upload':
      return openMaterialDelivery(task);
    case 'complete':
      return openCompletionForm(task);
    case 'accept':
      return openAcceptanceModal(task);
  }
}

function canAcceptTask(task: unknown) {
  const current = resolveTask(task);
  if (current && isLegacyMaterialOrderTask(current)) {
    return canOperateAcceptance(current);
  }
  return current?.status === 'pending_acceptance';
}

/** 已提交的子需求可独立验收，其他子需求返工不应阻断入口。 */
function hasPendingMaterialReview(task: WorkbenchTask) {
  const records = task.materialAssignments ?? [];
  return records.some(
    (record) =>
      record.status === 'submitted' &&
      records
        .filter(
          (row) => row.req_id === record.req_id && row.status !== 'cancelled',
        )
        .every((row) => ['submitted', 'accepted'].includes(row.status)),
  );
}

function canOperateAcceptance(task: unknown) {
  const current = resolveTask(task);
  if (!current) return false;
  if (isLegacyMaterialOrderTask(current)) {
    if (['paused', 'cancelled'].includes(current.status)) return false;
    // 分享列表始终提供素材浏览入口，暂无交付时显示空状态。
    if (isSharedView.value && current.materialPermissions?.shared) return true;
    // 制作中、部分完成可先查看已上传素材；实际通过、打回仍由抽屉和接口校验。
    return (
      ['in_production', 'partially_completed'].includes(
        current.legacyMaterialOrderStatus ?? '',
      ) ||
      current.status === 'done' ||
      current.status === 'pending_acceptance' ||
      current.materialAssignments?.some(
        (record) => record.status === 'accepted',
      ) ||
      (Boolean(current.materialPermissions?.review) &&
        hasPendingMaterialReview(current))
    );
  }
  if (current.status !== 'pending_acceptance') return false;
  if (!demoMode) {
    return current.kind === 'am'
      ? current.ownerId === currentUserId.value
      : current.creatorId === currentUserId.value;
  }
  return Boolean(
    canDemoAction(demoActor.value, 'task.accept') &&
      workflowRuntime.can(current.id, 'accept', {
        id: currentUserId.value,
        name: currentUserName.value,
      }),
  );
}

function isAwaitingTaskConfirmation(task: unknown) {
  const current = resolveTask(task);
  if (current?.kind === 'material') return false;
  return current?.status === 'assigned_pending_confirmation';
}

function canConfirmTask(task: unknown) {
  const current = resolveTask(task);
  if (current?.kind === 'material') return false;
  const isCurrentAssignee = Boolean(
    current &&
      (current.ownerId === currentUserId.value ||
        (current.kind !== 'am' &&
          current.assignments?.some(
            (assignment) => assignment.assigneeId === currentUserId.value,
          ))),
  );
  return Boolean(
    (!demoMode || canDemoAction(demoActor.value, 'task.process')) &&
      current?.status === 'assigned_pending_confirmation' &&
      isCurrentAssignee,
  );
}

function canDeclineTask(task: unknown) {
  const current = resolveTask(task);
  if (current && isLegacyMaterialOrderTask(current))
    return (
      current.status === 'pending_assignment' &&
      Boolean(current.materialPermissions?.assign)
    );

  return canConfirmTask(task);
}

function canWithdrawTask(task: unknown) {
  const current = resolveTask(task);
  if (!current || isLegacyMaterialOrderTask(current)) return false;
  if (
    !['pending_assignment', 'assigned_pending_confirmation'].includes(
      current.status,
    )
  ) {
    return false;
  }
  return demoMode
    ? current.creatorId === currentUserId.value ||
        current.createdBy === currentUserName.value
    : current.creatorId === currentUserId.value;
}

function canResubmitTask(task: unknown) {
  const current = resolveTask(task);
  if (current && isLegacyMaterialOrderTask(current)) {
    return (
      canCreateMaterialOrder.value &&
      canResubmitMaterialOrder({
        status: current.legacyMaterialOrderStatus ?? '',
      })
    );
  }
  return Boolean(
    current &&
      !isLegacyMaterialOrderTask(current) &&
      current.kind === 'am' &&
      ['rejected', 'withdrawn'].includes(current.status) &&
      (demoMode
        ? current.creatorId === currentUserId.value ||
          current.createdBy === currentUserName.value
        : current.creatorId === currentUserId.value),
  );
}

function canModifyMaterialAssignment(task: unknown) {
  const current = resolveTask(task);
  return Boolean(
    current &&
      isLegacyMaterialOrderTask(current) &&
      current.materialPermissions?.assign,
  );
}

function canAssignTask(task: unknown) {
  const current = resolveTask(task);
  if (current && isLegacyMaterialOrderTask(current))
    return (
      Boolean(current.materialPermissions?.assign) &&
      !current.materialPermissions?.upload
    );
  return current?.kind !== 'am' && current?.status === 'pending_assignment';
}

function canOperateAssignment(task: unknown) {
  const current = resolveTask(task);
  if (current && isLegacyMaterialOrderTask(current)) {
    return (
      [
        'pending_assignment',
        'assigned_pending_confirmation',
        'doing',
        'partially_completed',
        'rejected',
      ].includes(current.status) && Boolean(current.materialPermissions?.assign)
    );
  }
  if (current?.kind === 'am') return false;
  return Boolean(
    current &&
      current.status === 'pending_assignment' &&
      (demoMode
        ? canDemoAction(demoActor.value, 'task.assign')
        : current.creatorId === currentUserId.value),
  );
}

function openAssignmentModal(task: unknown) {
  const current = resolveTask(task);
  if (!current || !canOperateAssignment(current)) return;
  if (!demoMode && current.kind === 'material') {
    const orderId =
      current.legacyMaterialOrderId ?? materialOrderIds(current)[0];
    if (!orderId) {
      message.warning('该素材任务缺少工单关联，请刷新列表后重试');
      return;
    }
    materialAssignmentOrderId.value = orderId;
    materialAssignmentModalOpen.value = true;
    return;
  }

  assignmentTaskId.value = current.id;
  if (current.kind === 'material') {
    assignmentDesignerNames.value = [];
    assignmentCreativePlannerName.value = undefined;
  } else {
    assignmentAssigneeId.value = assignmentCandidates.value[0]?.value;
  }
  assignmentModalOpen.value = true;
}

async function refreshAfterMaterialAssignment() {
  try {
    await loadServerTasks();
  } catch (error) {
    message.error(
      error instanceof Error
        ? error.message
        : '操作已完成，列表刷新失败，请点击刷新',
    );
  }
}

async function submitTaskAssignment() {
  const task = assignmentTask.value;
  const isMaterialTask = task?.kind === 'material';
  const assignee = assignmentCandidates.value.find(
    (candidate) => candidate.value === assignmentAssigneeId.value,
  )?.profile;
  const demoAssignees = isMaterialTask
    ? assignmentCandidates.value
        .filter((candidate) =>
          assignmentDesignerNames.value.includes(candidate.value),
        )
        .map((candidate) => candidate.profile)
    : assignee
      ? [assignee]
      : [];
  if (
    !task ||
    (isMaterialTask
      ? assignmentDesignerNames.value.length === 0
      : !assignmentAssigneeId.value) ||
    (demoMode && demoAssignees.length === 0)
  ) {
    message.warning('请选择对应负责人');
    return;
  }

  assignmentSubmitting.value = true;
  try {
    if (isMaterialTask && !demoMode) {
      const orderIds = task.materialUpload?.orderIds?.length
        ? task.materialUpload.orderIds
        : task.materialUpload?.orderId
          ? [task.materialUpload.orderId]
          : [];
      if (orderIds.length === 0) {
        message.error('该素材任务未关联素材工单，无法分配任务');
        return;
      }
      openFormalMaterialOrder(task, 'assign');
      assignmentModalOpen.value = false;
      return;
    } else if (demoMode) {
      await taskService.assign(task.id, [
        ...demoAssignees.map((candidate) => ({
          assigneeId: candidate.userId,
          assigneeName: candidate.realName,
          role: 'owner' as const,
          status: 'pending' as const,
        })),
      ]);
    } else {
      await assignTaskApi(task.id, assignmentAssigneeId.value!);
      await loadServerTasks();
    }
    if (demoMode && demoAssignees.length > 0) {
      const assigneeNames = demoAssignees.map(
        (candidate) => candidate.realName,
      );
      taskCenterStore.patchTask(task.id, {
        actionLabel: isMaterialTask ? '素材制作中' : '等待负责人确认',
        audiences: [
          ...new Set([
            ...demoAssignees.flatMap((candidate) => candidate.roles),
            ...task.audiences,
          ]),
        ],
        owner: assigneeNames.join('、'),
        ownerId: isMaterialTask ? undefined : demoAssignees[0]?.userId,
        ownerName: assigneeNames.join('、'),
        status: isMaterialTask ? 'doing' : 'assigned_pending_confirmation',
      });
    }
    assignmentModalOpen.value = false;
    message.success(
      isMaterialTask
        ? `已分配 ${assignmentDesignerNames.value.length || demoAssignees.length} 位素材师`
        : demoMode && assignee
          ? `已分配给${assignee.realName}，等待负责人确认任务`
          : '负责人已分配，等待确认任务',
    );
  } catch (error) {
    message.error(error instanceof Error ? error.message : '任务分配失败');
  } finally {
    assignmentSubmitting.value = false;
  }
}

async function confirmAssignedTask(task: unknown) {
  const current = resolveTask(task);
  if (!current || !canConfirmTask(current)) return;
  if (!demoMode) {
    await confirmTaskApi(current.id);
    await loadServerTasks();
    message.success(`已确认任务“${current.title}”，现可开始处理`);
    return;
  }
  const updated = taskCenterStore.confirmAssignedTask(current.id);
  if (!updated) {
    message.warning('当前任务无需确认或状态已变化');
    return;
  }
  message.success(`已确认任务“${current.title}”，现可开始处理`);
}

function openDeclineModal(task: unknown) {
  const current = resolveTask(task);
  if (!current || !canDeclineTask(current)) return;
  declineTaskId.value = current.id;
  declineReason.value = '';
  declineError.value = '';
  declineModalOpen.value = true;
}

async function submitTaskDecline() {
  const current = declineTask.value;
  const reason = declineReason.value.trim();
  if (!current || !reason) {
    declineError.value = '请填写驳回原因';
    return;
  }
  declineSubmitting.value = true;
  declineError.value = '';
  try {
    if (!demoMode) {
      if (isLegacyMaterialOrderTask(current)) {
        await batchRejectMaterialOrders([
          { id: current.legacyMaterialOrderId!, reason },
        ]);
      } else {
        await declineTaskApi(current.id, reason);
      }
      await loadServerTasks();
    } else {
      const updated = taskCenterStore.rejectActiveTask(
        current.id,
        currentUserName.value,
        reason,
        currentUserId.value,
      );
      if (!updated) throw new Error('当前任务状态不可驳回');
    }
    declineModalOpen.value = false;
    message.success(`已驳回任务“${current.title}”`);
  } catch (error) {
    declineError.value =
      error instanceof Error ? error.message : '任务驳回失败';
  } finally {
    declineSubmitting.value = false;
  }
}

function canChangeActiveStatus(task: unknown) {
  const current = resolveTask(task);
  if (current && isLegacyMaterialOrderTask(current))
    return (
      Boolean(current.materialPermissions?.upload) &&
      Boolean(
        current.materialAssignments?.some(
          (record) =>
            record.designer_user_id === currentUserId.value &&
            ['in_production', 'rejected'].includes(record.status),
        ),
      )
    );
  if (
    !current ||
    (current.status !== 'doing' && current.status !== 'partially_completed')
  ) {
    return false;
  }
  if (isFormalMaterialOrderTask(current)) {
    return (
      isAssignedMaterialDesigner(current) && !hasCompletedMaterialTask(current)
    );
  }
  if (isLegacyMaterialOrderTask(current)) return isMaterialCreator();
  if (!demoMode && current.kind === 'am') {
    return Boolean(
      current.deliveryOperator ||
        current.delivery?.allocations.some(
          (allocation) =>
            allocation.assigneeId === currentUserId.value &&
            allocation.status === 'ASSIGNED',
        ),
    );
  }
  if (!demoMode) return current.ownerId === currentUserId.value;
  return Boolean(
    canDemoAction(demoActor.value, 'task.process') &&
      workflowRuntime.can(current.id, 'submit', {
        id: currentUserId.value,
        name: currentUserName.value,
      }),
  );
}

function isProcessingTask(task: unknown) {
  const status = resolveTask(task)?.status;
  return status === 'doing' || status === 'partially_completed';
}

function openEditTask(task: unknown, mode: TaskEditMode = 'edit') {
  const current = resolveTask(task);
  if (!current) return;
  if (isLegacyMaterialOrderTask(current)) {
    openLegacyMaterialOrder(current, 'view');
    return;
  }
  if (current.status === 'pending_acceptance') {
    message.warning('任务正在等待验收，暂不可编辑');
    return;
  }
  editingTaskId.value = current.id;
  editMode.value = mode;
  Object.assign(editForm, {
    dueAt: current.dueAt,
    owner: current.owner,
    summary: current.summary,
    title: current.title,
  });
  editModalOpen.value = true;
}

function saveTaskEdit() {
  const task = editingTask.value;
  const title = editForm.title.trim();
  const summary = editForm.summary.trim();
  if (!task || !title || !summary) {
    message.warning('请补全任务标题和需求说明');
    return;
  }

  const patch: Partial<WorkbenchTask> = {
    dueAt: editForm.dueAt.trim() || task.dueAt,
    owner: editForm.owner.trim() || task.owner,
    summary,
    title,
  };
  const updated =
    editMode.value === 'modify-submit'
      ? taskCenterStore.resubmitTask(task.id, patch)
      : taskCenterStore.patchTask(task.id, patch);
  if (!updated) {
    message.warning('任务状态已变化，请刷新后重试');
    return;
  }
  editModalOpen.value = false;
  message.success(
    editMode.value === 'modify-submit'
      ? '任务已修改并重新提交'
      : '任务信息已保存',
  );
}

async function withdrawTask(task: unknown) {
  const current = resolveTask(task);
  if (!current || !canWithdrawTask(current)) return;
  if (isLegacyMaterialOrderTask(current)) {
    message.info('素材工单请在素材需求页处理撤回或编辑');
    openLegacyMaterialOrder(current, 'view');
    return;
  }
  if (!demoMode) {
    await withdrawTaskApi(current.id, '创建者从任务中心撤回');
    await loadServerTasks();
    message.success(`任务“${current.title}”已撤回`);
    return;
  }
  const updated = taskCenterStore.withdrawTask(current.id);
  if (!updated) {
    message.warning('当前状态不可撤回');
    return;
  }
  message.success(`任务“${current.title}”已撤回`);
}

function openTaskProgress(task: unknown) {
  const current = resolveTask(task);
  if (!current) return;
  if (isLegacyMaterialOrderTask(current)) {
    openLegacyMaterialOrder(current, 'view');
    return;
  }
  progressTaskId.value = current.id;
  progressModalOpen.value = true;
}

function openProgressTaskDetail() {
  const task = progressTask.value;
  if (!task) return;
  progressModalOpen.value = false;
  openTask(task);
}

function resubmitTask(task: unknown) {
  const current = resolveTask(task);
  if (!current || !canResubmitTask(current)) return;
  if (current.legacyMaterialOrderId) {
    void openMaterialOrderResubmit(current.legacyMaterialOrderId);
    return;
  }
  if (!demoMode) {
    void router.push({
      path: '/workbench/tasks/create-delivery',
      query: { resubmitTaskId: current.id },
    });
    return;
  }
  const updated = taskCenterStore.resubmitTask(current.id);
  if (!updated) return message.warning('当前任务状态不可再次提交');
  message.success(`任务“${current.title}”已再次提交，等待重新分配`);
}

async function openAcceptanceModal(task: unknown) {
  const current = resolveTask(task);
  if (!current || !canOperateAcceptance(current)) return;
  if (isMaterialOrderTask(current)) {
    openLegacyMaterialOrder(current, 'accept');
    return;
  }
  if (
    demoMode &&
    current?.kind === 'material' &&
    current.status === 'pending_acceptance'
  ) {
    openFormalMaterialOrder(current, 'accept');
    return;
  }
  acceptanceTaskId.value = current.id;
  acceptanceReason.value = '';
  acceptanceError.value = '';
  selectedAcceptanceSubmissionId.value = '';
  if (!demoMode) {
    try {
      const detail = await getTaskApi(current.id);
      taskCenterStore.patchTask(current.id, {
        completion: serverCompletion(detail),
        delivery: projectDeliveryTaskDetail(detail, current.project),
      });
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : '任务交付详情加载失败',
      );
      return;
    }
  }
  const completion =
    current.kind === 'am'
      ? acceptanceDeliveryRecords.value[0]
      : acceptanceCompletion.value;
  if (!completion) {
    message.warning('未找到待验收的交付内容，请刷新任务列表后重试');
    return;
  }
  selectedAcceptanceSubmissionId.value = completion.submissionId;
  acceptanceModalOpen.value = true;
}

async function submitAcceptance(decision: 'accepted' | 'rejected') {
  const task = acceptanceTask.value;
  if (!task || acceptanceSubmitting.value) return;

  const reason = acceptanceReason.value.trim();
  if (decision === 'rejected' && !reason) {
    acceptanceError.value = '打回任务时必须填写原因';
    return;
  }

  acceptanceSubmitting.value = true;
  try {
    if (!demoMode) {
      const detail = await getTaskApi(task.id);
      const submissions =
        detail.task.taskType === 'DELIVERY'
          ? detail.deliverySubmissions
          : detail.materialSubmissions;
      const submission =
        detail.task.taskType === 'DELIVERY'
          ? submissions.find(
              (item) => item.id === selectedAcceptanceSubmissionId.value,
            )
          : submissions[0];
      if (!submission) throw new Error('未找到待验收的交付版本');
      await reviewTaskSubmissionApi(
        task.id,
        detail.task.taskType,
        submission.id,
        decision === 'accepted' ? 'accept' : 'reject',
        reason,
      );
      await loadServerTasks();
      if (decision === 'accepted') {
        const latestDetail = await getTaskApi(task.id);
        taskCenterStore.patchTask(task.id, {
          completion: serverCompletion(latestDetail),
          delivery: projectDeliveryTaskDetail(latestDetail, task.project),
        });
        const nextSubmission = acceptanceDeliveryRecords.value[0];
        if (nextSubmission) {
          selectedAcceptanceSubmissionId.value = nextSubmission.submissionId;
          acceptanceReason.value = '';
          message.success('该投手的交付已验收通过，可继续验收其他投手');
          return;
        }
      }
      acceptanceModalOpen.value = false;
      message.success(
        decision === 'accepted'
          ? `任务“${task.title}”已验收通过`
          : `任务“${task.title}”已打回，负责人可重新交付`,
      );
      return;
    }
    const projection =
      decision === 'accepted'
        ? await taskService.acceptDeliverable(
            task.id,
            { id: currentUserId.value, name: currentUserName.value },
            reason,
          )
        : await taskService.rejectDeliverable(
            task.id,
            { id: currentUserId.value, name: currentUserName.value },
            reason,
          );
    if (projection.deliverables.length === 0) {
      message.warning('任务状态已变化，请刷新后重试');
      return;
    }
    acceptanceModalOpen.value = false;
    detailTaskId.value = task.id;
    detailDrawerOpen.value = true;
    message.success(
      decision === 'accepted'
        ? `任务“${task.title}”已验收通过`
        : `任务“${task.title}”已打回，负责人可重新交付`,
    );
  } finally {
    acceptanceSubmitting.value = false;
  }
}

onMounted(async () => {
  if (!demoMode) {
    taskCenterStore.replaceTasks([]);
    taskActivities.value = [];
  }
  await restoreNavigationRoute();
  await restoreDeliveryRoute();
  await restoreMaterialRoute();
  if (route.query.materialOrderId) activeTaskTab.value = 'material';
  routeStateReady.value = true;
  void loadServerTasks().catch((error) => {
    message.error(error instanceof Error ? error.message : '任务数据加载失败');
  });
});

// 首次加载由 onMounted 负责；从新建、详情等页面返回时只刷新数据，不重置当前视图。
let hasActivated = false;
onActivated(() => {
  if (hasActivated) {
    void loadServerTasks().catch((error) => {
      message.error(
        error instanceof Error ? error.message : '任务数据加载失败',
      );
    });
  }
  hasActivated = true;
});

// 列表与全量视图切换时重新加载；看板和仪表盘共用同一份完整数据。
watch(
  () => viewMode.value === 'list',
  () => {
    if (!demoMode && (isDeliveryList.value || isMaterialList.value)) {
      void loadServerTasks();
    }
  },
  { flush: 'sync' },
);

// 主分支已把旧验收页迁移到任务中心；消费链接参数，避免返回列表时重复打开抽屉。
watch(
  () =>
    [
      route.path,
      route.query.materialOrderId,
      route.query.materialAction,
    ] as const,
  ([path, value, action], previous) => {
    const orderId = Array.isArray(value) ? value[0] : value;
    if (
      path !== '/workbench/tasks' ||
      typeof orderId !== 'string' ||
      !orderId.trim()
    )
      return;
    activeTaskTab.value = 'material';
    if (action === 'view') {
      openMaterialTaskDetail(orderId.trim());
    } else {
      materialAcceptanceOrderId.value = orderId.trim();
      materialAcceptanceOpen.value = true;
    }
    const query = { ...route.query };
    delete query.materialOrderId;
    delete query.materialAction;
    void router.replace({ path, query });
    // 首次进入和跨页面返回由挂载钩子加载；当前页更换链接参数时单独刷新。
    if (previous?.[0] === path) {
      void loadServerTasks().catch((error) => {
        message.error(
          error instanceof Error ? error.message : '任务数据加载失败',
        );
      });
    }
  },
  { immediate: true, flush: 'sync' },
);

function clearCompletionErrors() {
  for (const key of Object.keys(completionErrors)) {
    delete completionErrors[key];
  }
}

function clearCompletionError(field: string) {
  delete completionErrors[field];
}

function resetCompletionForm() {
  Object.assign(completionForm, {
    accountIds: [],
    actualBudget: undefined,
    actualSpend: 0,
    actualStartAt: '',
    adCount: undefined,
    adsetCount: undefined,
    campaignCount: undefined,
    campaignIds: [],
    currency: 'USD',
    dailyReportSpend: 0,
    deliveryStatus: '',
    entryMode: 'delivery-center',
    exceptionNote: '',
    note: '',
    platforms: [],
    sourceAdIds: [],
    sourceAdsetIds: [],
    sourceDateRange: [],
  });
  deliveryCampaigns.value = [];
  deliveryCampaignsError.value = '';
  completionFiles.value = [];
  clearCompletionErrors();
}

function clearAmCompletionFields() {
  const { sourceDateRange } = completionForm;
  Object.assign(completionForm, {
    accountIds: [],
    actualBudget: undefined,
    actualSpend: 0,
    actualStartAt: '',
    adCount: undefined,
    adsetCount: undefined,
    campaignCount: undefined,
    campaignIds: [],
    currency: 'USD',
    dailyReportSpend: 0,
    deliveryStatus: '',
    exceptionNote: '',
    platforms: [],
    sourceAdIds: [],
    sourceAdsetIds: [],
    sourceDateRange,
  });
  clearCompletionErrors();
}

function changeCompletionEntryMode(value: number | string) {
  const mode = value as AmCompletionEntryMode;
  if (completionForm.entryMode === mode) return;
  clearAmCompletionFields();
  completionForm.entryMode = mode;
  if (mode === 'manual') {
    completionForm.platforms = responsibleDeliveryPlatforms(
      completionTask.value,
    );
    return;
  }
  const task = completionTask.value;
  if (!task) return;
  if (deliveryCampaigns.value.length > 0) {
    applyDeliveryCenterCampaigns(task, deliveryCampaigns.value);
  } else {
    void loadDeliveryCenterCampaigns(task);
  }
}

function aggregateDeliveryStatus(campaigns: DeliverySourceCampaign[]) {
  const statuses = [...new Set(campaigns.map((campaign) => campaign.status))];
  return statuses.length === 1 ? statuses[0]! : ('partial' as const);
}

function applyDeliveryCenterCampaigns(
  task: WorkbenchTask,
  campaigns: DeliverySourceCampaign[],
) {
  const responsiblePlatforms = new Set(
    responsibleDeliveryPlatforms(task).map((platform) =>
      platform.toLowerCase(),
    ),
  );
  const matchedCampaigns = campaigns.filter(
    (campaign) =>
      responsiblePlatforms.size === 0 ||
      responsiblePlatforms.has(campaign.platform.toLowerCase()),
  );
  if (matchedCampaigns.length === 0) {
    throw new Error('未找到当前投手负责平台的投放中心数据');
  }
  const currencies = [
    ...new Set(matchedCampaigns.map((campaign) => campaign.currency)),
  ];
  if (currencies.length !== 1) {
    throw new Error('同步数据包含多个币种，请改为手动填写');
  }
  deliveryCampaigns.value = matchedCampaigns;
  const adSets = matchedCampaigns.flatMap((campaign) => campaign.adSets);
  const ads = adSets.flatMap((adSet) => adSet.ads);
  const campaignIds = [
    ...new Set(matchedCampaigns.map((campaign) => campaign.id)),
  ];
  const adsetIds = [...new Set(adSets.map((adSet) => adSet.id))];
  const adIds = [...new Set(ads.map((ad) => ad.id))];
  const actualBudget =
    adSets.length > 0
      ? adSets.reduce((total, adSet) => total + adSet.dailyBudget, 0)
      : matchedCampaigns.reduce(
          (total, campaign) => total + campaign.dailyBudget,
          0,
        );
  Object.assign(completionForm, {
    accountIds: [
      ...new Set(matchedCampaigns.map((campaign) => campaign.accountId)),
    ],
    actualBudget,
    actualStartAt: matchedCampaigns
      .map((campaign) => campaign.startedAt)
      .filter(Boolean)
      .sort()[0],
    adCount: adIds.length,
    adsetCount: adsetIds.length,
    campaignCount: campaignIds.length,
    campaignIds,
    currency: currencies[0],
    deliveryStatus: aggregateDeliveryStatus(matchedCampaigns),
    platforms: [
      ...new Set(matchedCampaigns.map((campaign) => campaign.platform)),
    ],
    sourceAdIds: adIds,
    sourceAdsetIds: adsetIds,
  });
  clearCompletionErrors();
}

async function loadDeliveryCenterCampaigns(
  task: WorkbenchTask,
  forceSync = false,
) {
  deliveryCampaignsLoading.value = true;
  deliveryCampaignsError.value = '';
  try {
    if (!demoMode) {
      const [startDate, endDate] = completionForm.sourceDateRange;
      const source = await getDeliveryTaskSourceApi(task.id, {
        endDate,
        startDate,
      });
      if (
        completionTaskId.value !== task.id ||
        completionForm.entryMode !== 'delivery-center'
      ) {
        return;
      }
      Object.assign(completionForm, {
        accountIds: source.accountIds,
        actualSpend: source.actualSpend,
        adCount: source.adIds.length,
        adsetCount: source.adsetIds.length,
        campaignCount: source.campaignIds.length,
        campaignIds: source.campaignIds,
        dailyReportSpend: source.dailyReportSpend,
        platforms: source.platforms,
        sourceAdIds: source.adIds,
        sourceAdsetIds: source.adsetIds,
        sourceDateRange: [source.startDate, source.endDate],
      });
      clearCompletionErrors();
      return;
    }
    const campaigns = await deliverySourceService.listCampaigns({
      forceSync,
      projectId: task.projectId,
      projectName: task.project,
    });
    applyDeliveryCenterCampaigns(task, campaigns);
  } catch (error) {
    deliveryCampaignsError.value =
      error instanceof Error ? error.message : '投放中心数据加载失败';
  } finally {
    deliveryCampaignsLoading.value = false;
  }
}

function openLegacyMaterialOrder(
  task: WorkbenchTask,
  target: 'accept' | 'assign' | 'deliver' | 'view',
) {
  const orderId =
    task.legacyMaterialOrderId ?? materialOrderIds(task)[0] ?? task.sourceId;
  if (!orderId) {
    message.warning('该历史素材任务缺少正式素材订单关联，请在原工作台处理');
    void router.push(task.route);
    return;
  }
  if (target === 'accept') {
    materialAcceptanceOrderId.value = orderId;
    materialAcceptanceOpen.value = true;
    return;
  }
  if (target === 'assign') {
    openAssignmentModal(task);
    return;
  }
  openMaterialTaskDetail(orderId, target === 'deliver' ? 'deliver' : 'view');
}

function openFormalMaterialOrder(
  task: WorkbenchTask,
  target: 'accept' | 'assign' | 'deliver',
) {
  openLegacyMaterialOrder(task, target);
}

async function openMaterialDelivery(input: unknown) {
  const task = resolveTask(input);
  if (!task) return;
  const orderIds = materialOrderIds(task);
  if (orderIds.length > 0) {
    const orderId = orderIds[0]!;
    materialDeliverySubmitting.value = true;
    try {
      const context = await taskMaterialDeliveryService.getContext(orderId);
      if (context.orderId !== orderId) {
        throw new Error('素材订单稳定 ID 不一致，无法从任务中心上传素材');
      }
      if (!context.assignmentOptions.length) {
        message.info('暂无您已确认且可上传的分配记录，请刷新任务后重试');
        return;
      }
      materialDeliveryTaskId.value = task.id;
      materialDeliveryContext.value = context;
      materialDeliveryModalOpen.value = true;
    } catch (error) {
      message.error(
        error instanceof Error
          ? error.message
          : '素材订单信息加载失败，请稍后重试',
      );
    } finally {
      materialDeliverySubmitting.value = false;
    }
    return;
  }
  if (isLegacyMaterialOrderTask(task)) {
    openLegacyMaterialOrder(task, 'deliver');
    return;
  }
  if (!demoMode) {
    const detail = await getTaskApi(task.id);
    materialDeliveryTaskId.value = task.id;
    materialTaskQuantity.value = detail.material?.quantity ?? 1;
    materialTaskNote.value = '';
    materialTaskFiles.value = [];
    materialTaskModalOpen.value = true;
    return;
  }
  if (!task.sourceId) {
    openFormalMaterialOrder(task, 'deliver');
    return;
  }

  materialDeliverySubmitting.value = true;
  try {
    const context = await taskMaterialDeliveryService.getContext(task.sourceId);
    if (context.orderId !== task.sourceId) {
      throw new Error('素材订单稳定 ID 不一致，无法从任务中心提交交付');
    }
    if (
      ['accepted', 'archived', 'is_complete', 'pending_accept'].includes(
        context.status,
      )
    ) {
      message.info('该素材订单已进入验收或归档阶段，请在素材订单中继续处理');
      openFormalMaterialOrder(task, 'accept');
      return;
    }
    if (['demand_rejected', 'rejected'].includes(context.status)) {
      const synced = taskCenterStore.syncMaterialOrderRejection(
        task.id,
        task.sourceId,
      );
      if (!synced) {
        throw new Error('素材订单退回状态无法同步到当前任务，请刷新后重试');
      }
    }
    materialDeliveryTaskId.value = task.id;
    materialDeliveryContext.value = context;
    materialDeliveryModalOpen.value = true;
  } catch (error) {
    message.error(
      error instanceof Error
        ? error.message
        : '素材订单信息加载失败，请稍后重试',
    );
  } finally {
    materialDeliverySubmitting.value = false;
  }
}

const beforeMaterialTaskUpload: UploadProps['beforeUpload'] = (file) => {
  if (file.size > 10 * 1024 * 1024) {
    message.error(`${file.name} 超过 10 MB，无法上传`);
    return Upload.LIST_IGNORE;
  }
  materialTaskFiles.value = [...materialTaskFiles.value, file];
  return false;
};

const removeMaterialTaskFile: UploadProps['onRemove'] = (file) => {
  materialTaskFiles.value = materialTaskFiles.value.filter(
    (item) => item.uid !== file.uid,
  );
  return true;
};

async function submitMaterialTaskDelivery() {
  const task = materialDeliveryTask.value;
  if (!task || materialTaskFiles.value.length === 0) {
    message.warning('请至少选择一个素材交付文件');
    return;
  }
  if (materialTaskFiles.value.length !== materialTaskQuantity.value) {
    message.warning('交付文件数量必须与本次交付数量一致');
    return;
  }
  materialDeliverySubmitting.value = true;
  try {
    const files = await Promise.all(
      materialTaskFiles.value.map(async (item, sortOrder) => {
        const file = item.originFileObj;
        if (!file)
          throw new Error(`文件“${item.name}”缺少原始文件，请重新选择`);
        const uploaded = await uploadTaskFileApi(file);
        return {
          fileId: uploaded.id,
          sortOrder,
          usageType: 'MATERIAL' as const,
        };
      }),
    );
    await submitMaterialTaskApi(task.id, {
      deliveredQuantity: materialTaskQuantity.value,
      files,
      note: materialTaskNote.value.trim(),
      requestId: globalThis.crypto.randomUUID(),
    });
    await loadServerTasks();
    materialTaskModalOpen.value = false;
    message.success(`素材任务“${task.title}”已提交验收`);
  } finally {
    materialDeliverySubmitting.value = false;
  }
}

function toNonNegativeNumber(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

function toMaterialDeliveryFile(file: UploadFileItem) {
  const uploaded = file.uploadData;
  if (!uploaded) return;
  return {
    basename: uploaded.basename,
    contentType: uploaded.content_type,
    duration: toNonNegativeNumber(uploaded.duration),
    fileMd5: uploaded.file_md5,
    filetype: uploaded.filetype,
    height: toNonNegativeNumber(uploaded.height),
    id: uploaded.id ?? uploaded.object_key,
    img: uploaded.img ?? '',
    name: uploaded.name,
    objectKey: uploaded.object_key,
    sha3_256: uploaded.sha3_256,
    size: toNonNegativeNumber(uploaded.size),
    url: uploaded.url,
    width: toNonNegativeNumber(uploaded.width),
  };
}

async function submitMaterialDelivery(
  key: string,
  doneFiles: UploadFileItem[],
  designer?: string,
  assignmentId?: string,
  creativePlanner?: string,
) {
  const task = materialDeliveryTask.value;
  const context = materialDeliveryContext.value;
  const orderId = task ? materialOrderIds(task)[0] : undefined;
  if (
    !task ||
    !context ||
    !orderId ||
    key !== materialDeliveryPersistKey.value ||
    materialDeliverySubmitting.value
  ) {
    return;
  }
  const files = doneFiles.flatMap((file) => {
    const result = toMaterialDeliveryFile(file);
    return result ? [result] : [];
  });
  if (files.length !== doneFiles.length) {
    message.warning('存在未完成服务端上传的素材，请处理后再提交');
    return;
  }

  materialDeliverySubmitting.value = true;
  try {
    const submission = await taskMaterialDeliveryService.deliver({
      creativePlanner,
      designer,
      files,
      orderId,
      assignmentId,
    });
    materialDeliveryModalRef.value?.showDeliverResult(key, '素材上传成功');
    materialDeliveryModalRef.value?.initFiles(key, []);
    materialDeliveryModalOpen.value = false;
    await loadServerTasks();
    message.success(
      `已上传 ${submission.files.length} 个素材；可继续上传，全部完成后请点击“完成任务”`,
    );
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '素材交付提交失败，请稍后重试',
    );
  } finally {
    materialDeliverySubmitting.value = false;
  }
}

function completeMaterialTask(task: WorkbenchTask) {
  // 抽屉中选择本人已完成的分配记录，避免把其他未完成分配一起提交。
  openFormalMaterialOrder(task, 'deliver');
}

function responsibleDeliveryPlatforms(task?: WorkbenchTask) {
  const items = task?.delivery?.items ?? [];
  const ownedItems = items.filter(
    (item) => item.operatorId === currentUserId.value,
  );
  const responsiblePlatforms = (ownedItems.length ? ownedItems : items)
    .map((item) => item.platform.trim())
    .filter(Boolean);
  return [
    ...new Set(
      (responsiblePlatforms.length
        ? responsiblePlatforms
        : (task?.delivery?.platforms ?? [])
      ).map((platform) => platform.trim()),
    ),
  ];
}

function todayText() {
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${today.getFullYear()}-${month}-${day}`;
}

function defaultDeliverySourceRange(startAt?: string) {
  const today = todayText();
  const plannedStart = startAt?.slice(0, 10) || today;
  return [plannedStart > today ? today : plannedStart, today];
}

function disableFutureDeliveryDate(current: {
  format: (value: string) => string;
}) {
  return current.format('YYYY-MM-DD') > todayText();
}

function changeDeliverySourceDateRange() {
  const task = completionTask.value;
  if (
    task &&
    completionForm.entryMode === 'delivery-center' &&
    completionForm.sourceDateRange.length === 2
  ) {
    void loadDeliveryCenterCampaigns(task, true);
  }
}

async function openCompletionForm(task: unknown) {
  const current = resolveTask(task);
  if (!current || !canChangeActiveStatus(current)) return;
  if (isFormalMaterialOrderTask(current)) {
    void completeMaterialTask(current);
    return;
  }
  if (isLegacyMaterialOrderTask(current)) {
    openLegacyMaterialOrder(current, 'deliver');
    return;
  }
  if (current.kind === 'material') {
    void openMaterialDelivery(current);
    return;
  }
  completionTaskId.value = current.id;
  resetCompletionForm();
  if (!demoMode && current.kind === 'am') {
    try {
      const detail = await getTaskApi(current.id);
      const delivery = projectDeliveryTaskDetail(detail, current.project);
      taskCenterStore.patchTask(current.id, {
        completion: serverCompletion(detail),
        delivery,
      });
      completionForm.platforms = responsibleDeliveryPlatforms({
        ...current,
        delivery,
      });
      completionForm.actualStartAt = delivery?.startAt ?? '';
      completionForm.sourceDateRange = defaultDeliverySourceRange(
        delivery?.startAt,
      );
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : '任务投放明细加载失败',
      );
      return;
    }
  } else {
    completionForm.platforms = responsibleDeliveryPlatforms(current);
    completionForm.actualStartAt = current.delivery?.startAt ?? '';
    completionForm.sourceDateRange = defaultDeliverySourceRange(
      current.delivery?.startAt,
    );
  }
  completionModalOpen.value = true;
  if (current.kind === 'am') void loadDeliveryCenterCampaigns(current);
}

function completionFileExtension(fileName: string) {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

function allowedCompletionExtensions(kind: TaskKind) {
  if (kind === 'material') {
    return new Set([
      '.7z',
      '.avi',
      '.gif',
      '.jpeg',
      '.jpg',
      '.mkv',
      '.mov',
      '.mp4',
      '.png',
      '.webm',
      '.webp',
      '.zip',
    ]);
  }
  if (kind === 'am') {
    return new Set([
      '.7z',
      '.csv',
      '.jpeg',
      '.jpg',
      '.pdf',
      '.png',
      '.webp',
      '.xls',
      '.xlsx',
      '.zip',
    ]);
  }
  return new Set([
    '.7z',
    '.doc',
    '.docx',
    '.jpeg',
    '.jpg',
    '.pdf',
    '.png',
    '.webp',
    '.xls',
    '.xlsx',
    '.zip',
  ]);
}

const beforeCompletionUpload: UploadProps['beforeUpload'] = (file) => {
  const task = completionTask.value;
  if (!task) return Upload.LIST_IGNORE;
  if (task.kind === 'material') {
    message.warning('素材任务请使用素材订单上传，不支持在任务中心本地添加附件');
    return Upload.LIST_IGNORE;
  }
  if (
    !allowedCompletionExtensions(task.kind).has(
      completionFileExtension(file.name),
    )
  ) {
    message.error(`文件“${file.name}”格式不符合当前交付要求`);
    return Upload.LIST_IGNORE;
  }
  if (file.size > 10 * 1024 * 1024) {
    message.error(`文件“${file.name}”超过 10 MB`);
    return Upload.LIST_IGNORE;
  }
  if (
    completionFiles.value.some(
      (item) => item.name === file.name && item.size === file.size,
    )
  ) {
    message.warning(`文件“${file.name}”已在交付列表中`);
    return Upload.LIST_IGNORE;
  }
  completionFiles.value = [
    ...completionFiles.value,
    {
      name: file.name,
      originFileObj: file,
      size: file.size,
      status: 'done',
      type: file.type,
      uid: file.uid,
    },
  ];
  clearCompletionError('files');
  return false;
};

const removeCompletionFile: UploadProps['onRemove'] = (file) => {
  completionFiles.value = completionFiles.value.filter(
    (item) => item.uid !== file.uid,
  );
  return true;
};

function completionFileMetadata(taskId: string): TaskAttachmentMeta[] {
  const uploadedAt = new Date().toLocaleString('zh-CN', { hour12: false });
  return completionFiles.value.map((file) => ({
    id: String(file.uid),
    name: file.name,
    objectKey: `task-completion/${taskId}/${String(file.uid)}-${file.name}`,
    size: Number(file.size) || 0,
    source: 'task-center-local',
    type: file.type || 'application/octet-stream',
    uploadedAt,
  }));
}

function validateCompletionForm() {
  clearCompletionErrors();
  const task = completionTask.value;
  if (!task) return false;
  if (task.kind === 'am') {
    const normalizeIds = (ids: string[]) => [
      ...new Set(ids.map((id) => id.trim()).filter(Boolean)),
    ];
    completionForm.accountIds = normalizeIds(completionForm.accountIds);
    completionForm.campaignIds = normalizeIds(completionForm.campaignIds);
    completionForm.sourceAdsetIds = normalizeIds(completionForm.sourceAdsetIds);
    completionForm.sourceAdIds = normalizeIds(completionForm.sourceAdIds);
    completionForm.campaignCount = completionForm.campaignIds.length;
    completionForm.adsetCount = completionForm.sourceAdsetIds.length;
    completionForm.adCount = completionForm.sourceAdIds.length;
  }
  if (task.kind === 'media' && !completionForm.note.trim()) {
    completionErrors.note = '请填写处理结果备注';
  }

  if (task.kind === 'am') {
    if (completionForm.platforms.length === 0) {
      completionErrors.platforms = '请至少选择一个投放平台';
    }
    if (completionForm.accountIds.length === 0) {
      completionErrors.accountIds = '请至少填写 1 个 Account ID';
    }
    if (!completionForm.actualStartAt) {
      completionErrors.actualStartAt = '请选择实际开始时间';
    }
    const campaignIds = completionForm.campaignIds
      .map((id) => id.trim())
      .filter(Boolean);
    if (campaignIds.length === 0) {
      completionErrors.campaignIds = '请至少填写 1 个 Campaign ID';
    }
    if (
      completionForm.actualBudget === undefined ||
      !Number.isFinite(completionForm.actualBudget) ||
      completionForm.actualBudget <= 0
    ) {
      completionErrors.actualBudget = '请填写大于 0 的实际预算';
    }
    if (
      !Number.isFinite(completionForm.actualSpend) ||
      completionForm.actualSpend < 0
    ) {
      completionErrors.actualSpend = '请填写不小于 0 的实际消耗';
    }
    if (
      !Number.isFinite(completionForm.dailyReportSpend) ||
      completionForm.dailyReportSpend < 0
    ) {
      completionErrors.dailyReportSpend = '请填写不小于 0 的日报花费';
    }
    if (!completionForm.currency) completionErrors.currency = '请选择币种';
    if (!completionForm.deliveryStatus) {
      completionErrors.deliveryStatus = '请选择实际投放状态';
    }
    if (
      completionForm.deliveryStatus === 'partial' &&
      !completionForm.exceptionNote.trim()
    ) {
      completionErrors.exceptionNote = '部分成功时必须说明异常情况';
    }
    if (completionForm.entryMode === 'manual' && !completionForm.note.trim()) {
      completionErrors.note = '手动补录时必须填写说明';
    }
  }
  return Object.keys(completionErrors).length === 0;
}

async function submitCompletion() {
  const task = completionTask.value;
  if (task?.kind === 'material') {
    message.warning('素材任务请通过素材订单上传并提交交付');
    return;
  }
  if (!task || !validateCompletionForm()) {
    message.warning('请先补全交付表单中的必填内容');
    return;
  }

  completionSubmitting.value = true;
  try {
    if (!demoMode && task.kind === 'am') {
      const files = await Promise.all(
        completionFiles.value.map(async (item, sortOrder) => {
          const file = item.originFileObj;
          if (!file)
            throw new Error(`文件“${item.name}”缺少原始文件，请重新选择`);
          const uploaded = await uploadTaskFileApi(file);
          return {
            fileId: uploaded.id,
            sortOrder,
            usageType: 'PROOF' as const,
          };
        }),
      );
      const campaignIds = completionForm.campaignIds.map((id) => id.trim());
      const adsetIds = completionForm.sourceAdsetIds.map((id) => id.trim());
      const adIds = completionForm.sourceAdIds.map((id) => id.trim());
      const makeObjects = (type: 'AD' | 'AD_SET' | 'CAMPAIGN', ids: string[]) =>
        ids.map((objectId) => ({
          objectId,
          objectType: type,
        }));
      await submitDeliveryTaskApi(task.id, {
        actualBudget: Number(completionForm.actualBudget),
        actualSpend: completionForm.actualSpend,
        actualStartAt: `${completionForm.actualStartAt.replace(' ', 'T')}:00`,
        accountIds: [...completionForm.accountIds],
        adCount: adIds.length,
        adsetCount: adsetIds.length,
        campaignCount: campaignIds.length,
        currency: completionForm.currency,
        dailyReportSpend: completionForm.dailyReportSpend,
        deliveryStatus: completionForm.deliveryStatus.toUpperCase() as
          | 'ACTIVE'
          | 'FAILED'
          | 'PARTIAL'
          | 'PAUSED',
        exceptionNote: completionForm.exceptionNote.trim(),
        files,
        note: completionForm.note.trim(),
        objects: [
          ...makeObjects('CAMPAIGN', campaignIds),
          ...makeObjects('AD_SET', adsetIds),
          ...makeObjects('AD', adIds),
        ],
        platforms: [...completionForm.platforms],
        requestId: globalThis.crypto.randomUUID(),
      });
      await loadServerTasks();
      completionModalOpen.value = false;
      message.success(`交付已保存，任务“${task.title}”已进入待验收`);
      return;
    }
    const common = {
      files: completionFileMetadata(task.id),
      note: completionForm.note.trim(),
      submittedBy: currentUserName.value,
    };
    let input: TaskCompletionInput;
    if (task.kind === 'media') {
      input = { ...common, kind: 'media' };
    } else {
      const sourceMetadata =
        completionForm.entryMode === 'delivery-center'
          ? deliverySourceMetadata.value
          : undefined;
      input = {
        ...common,
        accountId: completionForm.accountIds.join(' / '),
        accountName: sourceMetadata?.accountName,
        actualBudget: Number(completionForm.actualBudget),
        actualSpend: completionForm.actualSpend,
        actualStartAt: completionForm.actualStartAt,
        adCount: Number(completionForm.adCount),
        adsetCount: Number(completionForm.adsetCount),
        agencyLineId: sourceMetadata?.agencyLineId,
        agencyLineName: sourceMetadata?.agencyLineName,
        campaignCount: Number(completionForm.campaignCount),
        campaignIds: completionForm.campaignIds,
        currency: completionForm.currency,
        dailyReportSpend: completionForm.dailyReportSpend,
        dataCutoffAt: sourceMetadata?.dataCutoffAt,
        deliveryStatus: completionForm.deliveryStatus as AmDeliveryStatus,
        entryMode: completionForm.entryMode,
        exceptionNote: completionForm.exceptionNote.trim(),
        kind: 'am',
        platform: completionForm.platforms.join(' / '),
        sourceAdIds: [...completionForm.sourceAdIds],
        sourceAdsetIds: [...completionForm.sourceAdsetIds],
        sourceCampaignName: sourceMetadata?.campaignName,
        sourceSyncedAt: sourceMetadata?.syncedAt,
      };
    }

    const projection = await taskService.submitDeliverable({
      legacyInput: input,
      taskId: task.id,
    });
    if (projection.deliverables.length === 0) {
      message.warning('交付信息未通过校验，请检查后重试');
      return;
    }
    completionModalOpen.value = false;
    detailTaskId.value = task.id;
    detailDrawerOpen.value = true;
    message.success(`交付已保存，任务“${task.title}”已进入待验收`);
  } finally {
    completionSubmitting.value = false;
  }
}

function formatCompletionFileSize(size: number) {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(size / 1024))} KB`;
}

function deliveryAllocationStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    ASSIGNED: '待交付',
    COMPLETED: '已验收',
    SUBMITTED: '待验收',
  };
  return labels[status ?? ''] ?? '未分配';
}

function deliveryAllocationStatusColor(status?: string) {
  const colors: Record<string, string> = {
    ASSIGNED: 'processing',
    COMPLETED: 'success',
    SUBMITTED: 'warning',
  };
  return colors[status ?? ''] ?? 'default';
}

function completionRecordTitle(record: TaskCompletionRecord) {
  return `${kindMeta[record.kind].shortLabel} 交付 v${record.versionNo}`;
}
</script>

<template>
  <Page auto-content-height class="bg-slate-50">
    <div class="task-page">
      <div
        class="mb-3 inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm"
        role="tablist"
        aria-label="任务类型"
      >
        <button
          class="rounded-md px-5 py-2 text-sm font-medium transition-colors"
          :class="
            activeTaskTab === 'delivery'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
          "
          role="tab"
          :aria-selected="activeTaskTab === 'delivery'"
          type="button"
          @click="setTaskTab('delivery')"
        >
          投放任务
        </button>
        <button
          class="rounded-md px-5 py-2 text-sm font-medium transition-colors"
          :class="
            activeTaskTab === 'material'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
          "
          role="tab"
          :aria-selected="activeTaskTab === 'material'"
          type="button"
          @click="setTaskTab('material')"
        >
          素材任务
        </button>
      </div>
      <div
        class="task-shell overflow-hidden rounded-xl border border-slate-200 bg-white"
      >
        <aside
          :key="activeTaskTab"
          class="task-inner-sidebar"
          :aria-label="`${activeTaskTab === 'delivery' ? '投放' : '素材'}任务二级导航`"
        >
          <div class="task-sidebar-heading">
            <div class="flex min-w-0 items-center gap-2">
              <span class="task-sidebar-icon" aria-hidden="true">
                <IconifyIcon icon="lucide:list-todo" />
              </span>
              <h2 class="m-0 truncate text-base font-semibold text-slate-900">
                {{ activeTaskTab === 'delivery' ? '投放任务' : '素材任务' }}
              </h2>
            </div>
          </div>

          <nav class="task-primary-nav" aria-label="任务范围">
            <button
              class="task-nav-button"
              :class="{ 'is-active': activeSection === 'owned' }"
              type="button"
              @click="setSection('owned')"
            >
              <IconifyIcon icon="lucide:user-round" aria-hidden="true" />
              <span>我负责的</span>
            </button>
            <button
              class="task-nav-button"
              :class="{ 'is-active': activeSection === 'followed' }"
              type="button"
              @click="setSection('followed')"
            >
              <IconifyIcon icon="lucide:bookmark" aria-hidden="true" />
              <span>我关注的</span>
            </button>
            <button
              class="task-nav-button"
              :class="{ 'is-active': activeSection === 'activity' }"
              type="button"
              @click="setSection('activity')"
            >
              <IconifyIcon icon="lucide:history" aria-hidden="true" />
              <span>动态</span>
            </button>
            <button
              class="task-nav-button"
              :class="{ 'is-active': activeSection === 'drafts' }"
              type="button"
              @click="setSection('drafts')"
            >
              <IconifyIcon icon="lucide:file-pen-line" aria-hidden="true" />
              <span>草稿箱</span>
            </button>
            <button
              v-if="
                activeTaskTab === 'material' && canManageRequirementTemplates
              "
              type="button"
              class="task-nav-button"
              :class="{ 'is-active': requirementTemplateManagerOpen }"
              aria-haspopup="dialog"
              @click="requirementTemplateManagerOpen = true"
            >
              <IconifyIcon icon="lucide:layout-template" aria-hidden="true" />
              <span>子需求模板</span>
            </button>
          </nav>

          <div class="task-sidebar-divider"></div>

          <div class="task-quick-access">
            <div class="task-sidebar-label">快速访问</div>
            <div class="task-quick-list">
              <button
                v-for="item in visibleQuickItems"
                :key="item.key"
                class="task-nav-button"
                :class="{
                  'is-active':
                    activeSection === 'quick' && quickFilter === item.key,
                }"
                type="button"
                @click="setQuickFilter(item.key)"
              >
                <IconifyIcon :icon="item.icon" aria-hidden="true" />
                <span>{{ item.label }}</span>
              </button>
            </div>
          </div>
        </aside>

        <main
          class="flex min-h-0 min-w-0 flex-col bg-slate-50 p-3 md:p-4"
          :class="{ 'material-task-main': isMaterialList }"
        >
          <section class="task-page-header">
            <div class="min-w-0">
              <h1 class="m-0 truncate text-xl font-semibold text-slate-900">
                {{ sectionTitle }}
              </h1>
              <p class="mb-0 mt-1 text-sm text-slate-500">
                <template v-if="activeSection === 'activity'">
                  汇总任务状态、评论和交付进展，及时跟进上下游协作。
                </template>
                <template v-else>
                  <template v-if="activeTaskTab === 'delivery'">
                    管理投放任务的确认、交付与验收。
                  </template>
                  <template v-else>管理素材任务。</template>
                </template>
              </p>
            </div>

            <div class="flex items-center gap-2">
              <Button class="" @click="refreshTaskCenter">
                <template #icon>
                  <IconifyIcon icon="lucide:refresh-cw" aria-hidden="true" />
                </template>
                刷新
              </Button>
              <Dropdown
                v-if="canCreateTask"
                :trigger="['click']"
                placement="bottomRight"
              >
                <Button
                  aria-label="新建任务，选择任务类型"
                  class="shrink-0"
                  type="primary"
                >
                  <template #icon>
                    <IconifyIcon icon="lucide:plus" aria-hidden="true" />
                  </template>
                  新建
                  <IconifyIcon
                    class="ml-1"
                    icon="lucide:chevron-down"
                    aria-hidden="true"
                  />
                </Button>
                <template #overlay>
                  <Menu class="min-w-52" @click="handleCreateMenu">
                    <MenuItem v-if="canCreateMaterialOrder" key="material">
                      <span class="flex min-h-9 items-center gap-2">
                        <IconifyIcon
                          class="text-violet-600"
                          icon="lucide:images"
                        />
                        <span>
                          <strong class="block font-medium"
                            >新建素材任务</strong
                          >
                          <small class="text-slate-400">创建素材生产需求</small>
                        </span>
                      </span>
                    </MenuItem>
                    <MenuItem v-if="canCreateDeliveryTaskEntry" key="delivery">
                      <span class="flex min-h-9 items-center gap-2">
                        <IconifyIcon
                          class="text-blue-600"
                          icon="lucide:rocket"
                        />
                        <span>
                          <strong class="block font-medium"
                            >新建投放任务</strong
                          >
                          <small class="text-slate-400"
                            >填写投放明细并指定投手</small
                          >
                        </span>
                      </span>
                    </MenuItem>
                  </Menu>
                </template>
              </Dropdown>
            </div>
          </section>

          <div
            v-if="activeSection === 'activity'"
            class="task-activity-scroll mt-3"
            role="region"
            aria-label="最近动态"
            tabindex="0"
          >
            <Spin :spinning="activityLoading">
              <Card :body-style="{ padding: 0 }">
                <div class="border-b border-slate-100 px-4 py-3">
                  <div class="font-medium text-slate-900">最近动态</div>
                  <div class="mt-1 text-xs text-slate-500">
                    {{
                      activeTaskTab === 'material'
                        ? '展示你有权查看的素材工单最近 100 条修改记录'
                        : '展示你负责与关注任务的最新变化'
                    }}
                  </div>
                </div>
                <Alert
                  v-if="activityError"
                  :message="activityError"
                  type="error"
                  show-icon
                >
                  <template #action
                    ><Button @click="loadServerTasks">重试</Button></template
                  >
                </Alert>
                <div v-else class="divide-y divide-slate-100">
                  <article
                    v-for="activity in taskActivities"
                    :key="activity.id"
                    class="flex w-full gap-3 px-4 py-4 text-left transition-colors hover:bg-slate-50"
                  >
                    <span class="task-activity-icon" aria-hidden="true">
                      <IconifyIcon :icon="activity.icon" />
                    </span>
                    <button
                      type="button"
                      class="min-w-0 flex-1 text-left"
                      @click="openTaskActivity(activity)"
                    >
                      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <strong class="font-medium text-slate-900">
                          {{ activity.actorName || '任务系统' }}
                        </strong>
                        <span class="text-xs text-slate-400">{{
                          activity.occurredAt || '当前状态'
                        }}</span>
                      </div>
                      <div class="mt-1 text-sm text-slate-600">
                        {{ activity.description }}
                      </div>
                      <div class="mt-1.5 text-xs font-medium text-blue-600">
                        {{ activity.title }}
                      </div>
                    </button>
                  </article>
                  <Empty
                    v-if="!activityLoading && !taskActivities.length"
                    class="py-10"
                    description="暂无任务动态"
                  />
                </div>
              </Card>
            </Spin>
          </div>

          <template v-else-if="activeSection === 'drafts'">
            <div class="mt-3 space-y-3">
              <Card title="任务草稿" :body-style="{ padding: 0 }">
                <div
                  v-if="deliveryDrafts.length > 0"
                  class="divide-y divide-slate-100"
                >
                  <article
                    v-for="draft in deliveryDrafts"
                    :key="draft.id"
                    class="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center"
                  >
                    <span class="task-activity-icon" aria-hidden="true">
                      <IconifyIcon icon="lucide:rocket" />
                    </span>
                    <div class="min-w-0 flex-1">
                      <strong class="block truncate font-medium text-slate-900">
                        {{ draft.title }}
                      </strong>
                      <div class="mt-1 text-xs text-slate-500">
                        {{ kindMeta[draft.kind].shortLabel }} ·
                        {{ draft.project }} · 更新于
                        {{ draft.updatedAt }}
                      </div>
                    </div>
                    <div class="flex shrink-0 items-center gap-2">
                      <Button
                        class=""
                        type="primary"
                        @click="continueDeliveryDraft(draft.draftId!)"
                      >
                        继续编辑
                      </Button>
                      <Popconfirm
                        cancel-text="取消"
                        ok-text="删除"
                        ok-type="danger"
                        title="确定删除这份任务草稿吗？"
                        @confirm="removeTaskDraft(draft.draftId!)"
                      >
                        <Button class="" danger>删除</Button>
                      </Popconfirm>
                    </div>
                  </article>
                </div>
                <Empty v-else class="py-10" description="暂无任务草稿" />
              </Card>
            </div>
          </template>

          <template v-else>
            <Card class="mt-3 shrink-0" :body-style="{ padding: '12px 14px' }">
              <div class="task-view-toolbar">
                <Segmented
                  v-model:value="viewMode"
                  class="task-view-switch"
                  :options="viewOptions"
                />
                <span class="text-xs text-slate-500" role="status">
                  <template v-if="taskResultsLoading">正在加载任务…</template>
                  <template v-else-if="taskResultsError"
                    >加载失败，请重试</template
                  >
                  <template v-else>
                    {{
                      viewMode === 'list' && (isDeliveryList || isMaterialList)
                        ? '当前页'
                        : '当前筛选共'
                    }}
                    {{ filteredTasks.length }} 项
                  </template>
                </span>
              </div>

              <MaterialTaskFilters
                v-if="isMaterialList"
                :group-by="groupBy"
                :group-options="groupOptions"
                :filters="materialFilters"
                :loading="materialLoading"
                :fixed-status="materialFixedStatus"
                @apply="applyMaterialFilters"
              />
              <div
                v-else
                class="task-filter-toolbar"
                :class="{ 'task-delivery-filter-toolbar': isDeliveryList }"
              >
                <Input.Search
                  v-if="isDeliveryList"
                  v-model:value="searchKeyword"
                  allow-clear
                  aria-label="搜索投放任务"
                  class="task-search-input"
                  placeholder="搜索任务、项目、负责人或编号"
                  :loading="deliveryLoading"
                  @search="searchDeliveryTasks"
                >
                  <template #enterButton>
                    <Button
                      class="min-w-10"
                      aria-label="查询投放任务"
                      :loading="deliveryLoading"
                    >
                      <template #icon>
                        <IconifyIcon
                          class="size-5"
                          icon="lucide:search"
                          aria-hidden="true"
                        />
                      </template>
                    </Button>
                  </template>
                </Input.Search>
                <Input
                  v-else
                  v-model:value="searchKeyword"
                  allow-clear
                  aria-label="搜索任务"
                  class="task-search-input"
                  placeholder="搜索任务、项目、负责人或编号"
                >
                  <template #prefix>
                    <IconifyIcon
                      class="text-slate-400"
                      icon="lucide:search"
                      aria-hidden="true"
                    />
                  </template>
                </Input>
                <Select
                  v-model:value="sourceFilter"
                  aria-label="按任务来源筛选"
                  class="task-filter-select"
                  :options="sourceOptions"
                  @change="handleDeliveryFilterChange"
                />
                <Select
                  v-model:value="statusFilter"
                  aria-label="按任务状态筛选"
                  class="task-filter-select"
                  :options="statusOptions"
                  @change="handleDeliveryFilterChange"
                />
                <Select
                  v-model:value="sortBy"
                  aria-label="任务排序方式"
                  class="task-filter-select"
                  :options="sortOptions"
                  @change="handleDeliveryFilterChange"
                />
                <Select
                  v-model:value="groupBy"
                  aria-label="任务分组方式"
                  class="task-filter-select"
                  :options="groupOptions"
                  @change="handleDeliveryFilterChange"
                />
                <Button @click="resetTaskFilters">
                  <template #icon>
                    <IconifyIcon icon="lucide:rotate-ccw" aria-hidden="true" />
                  </template>
                  重置
                </Button>
              </div>
            </Card>

            <Alert
              v-if="taskResultsError"
              class="mt-3"
              type="error"
              show-icon
              :message="taskResultsError"
            >
              <template #action
                ><Button @click="loadServerTasks">重试</Button></template
              >
            </Alert>
            <div
              v-else-if="taskResultsLoading"
              class="flex min-h-0 flex-1 items-center justify-center"
              role="status"
              aria-live="polite"
            >
              <Spin
                :tip="
                  viewMode === 'list' ? '正在加载任务…' : '正在加载全部任务…'
                "
              />
            </div>
            <div
              v-else
              :class="
                isMaterialList
                  ? 'material-task-results-flow'
                  : isDeliveryList || viewMode !== 'list'
                    ? 'task-results-scroll'
                    : 'contents'
              "
              :aria-busy="taskResultsLoading"
            >
              <div v-if="viewMode === 'list'" class="task-list-section mt-3">
                <div class="task-list-scroll space-y-3">
                  <Card
                    v-for="group in groupedSections"
                    :key="group.key"
                    class="task-list-card"
                    :body-style="{ padding: 0 }"
                  >
                    <div
                      v-if="groupBy !== 'none'"
                      class="flex items-center justify-between border-b border-slate-100 px-4 py-3"
                    >
                      <div class="font-medium text-slate-800">
                        {{ group.label }}
                      </div>
                      <Tag>{{ group.tasks.length }} 项</Tag>
                    </div>
                    <template v-if="group.tasks.length > 0">
                      <Table
                        class="task-desktop-table"
                        :columns="columns"
                        :data-source="group.tasks"
                        :pagination="false"
                        :row-key="(record) => record.id"
                        :scroll="{ x: tableScrollWidth }"
                        size="middle"
                        table-layout="fixed"
                      >
                        <template #bodyCell="{ column, record }">
                          <template v-if="column.key === 'task'">
                            <div class="min-w-0 py-1">
                              <div class="flex min-w-0 items-start gap-2">
                                <Button
                                  :aria-label="
                                    isFollowed(record.id)
                                      ? `取消关注${record.title}`
                                      : `关注${record.title}`
                                  "
                                  :loading="pendingFollowTaskIds.has(record.id)"
                                  :aria-pressed="isFollowed(record.id)"
                                  class="task-follow-button"
                                  type="text"
                                  @click="toggleFollow(record.id)"
                                >
                                  <IconifyIcon
                                    :class="
                                      isFollowed(record.id)
                                        ? 'fill-amber-400 text-amber-500'
                                        : 'text-slate-400'
                                    "
                                    icon="lucide:star"
                                  />
                                </Button>
                                <div class="min-w-0 flex-1">
                                  <button
                                    class="task-title-button ux-table-link line-clamp-2"
                                    type="button"
                                    @click="openTask(record)"
                                  >
                                    {{ record.title }}
                                  </button>
                                  <div
                                    class="mt-1 flex min-w-0 items-center gap-1 text-xs text-slate-500"
                                  >
                                    <span class="task-kind-pill">
                                      {{
                                        kindMeta[record.kind as TaskKind]
                                          .shortLabel
                                      }}
                                    </span>
                                    <span class="truncate">{{
                                      taskDisplayNumber(record)
                                    }}</span>
                                  </div>
                                  <div
                                    class="mt-1 line-clamp-2 text-xs leading-5 text-slate-500"
                                  >
                                    {{ record.summary }}
                                  </div>
                                </div>
                              </div>
                            </div>
                          </template>
                          <template v-else-if="column.key === 'project'">
                            <div
                              v-if="activeTaskTab === 'delivery'"
                              class="text-sm text-slate-700"
                            >
                              {{ taskProjectOwner(record) }}
                            </div>
                            <div v-else class="min-w-0">
                              <div class="truncate text-sm text-slate-700">
                                {{ record.project }}
                              </div>
                              <div class="mt-1 truncate text-xs text-slate-500">
                                {{ taskProjectOwner(record) }}
                              </div>
                            </div>
                          </template>
                          <template v-else-if="column.key === 'am'">
                            <div class="min-w-0">
                              <div
                                class="truncate text-sm text-slate-700"
                                :title="record.project"
                              >
                                {{ record.project }}
                              </div>
                              <div
                                class="mt-1 break-words text-xs text-slate-500"
                              >
                                {{
                                  record.amNames ||
                                  record.delivery?.amOwner ||
                                  '未配置'
                                }}
                              </div>
                            </div>
                          </template>
                          <template
                            v-else-if="column.key === 'materialParticipants'"
                          >
                            <div class="min-w-0 text-xs text-slate-600">
                              <div
                                class="truncate"
                                :title="
                                  materialParticipantNames(
                                    record,
                                    'creativePlanner',
                                  )
                                "
                              >
                                创意策划：{{
                                  materialParticipantNames(
                                    record,
                                    'creativePlanner',
                                  )
                                }}
                              </div>
                              <div
                                class="mt-1 truncate"
                                :title="
                                  materialParticipantNames(record, 'designer')
                                "
                              >
                                素材师：{{
                                  materialParticipantNames(record, 'designer')
                                }}
                              </div>
                            </div>
                          </template>
                          <template v-else-if="column.key === 'materialUpload'">
                            <div
                              v-if="record.materialUpload"
                              class="min-w-0 text-xs"
                            >
                              <div
                                class="whitespace-nowrap text-sm text-slate-700"
                              >
                                <span class="font-semibold text-slate-900">
                                  {{
                                    record.materialUpload.requiredQuantity ??
                                    '—'
                                  }}
                                </span>
                                <span class="px-1 text-slate-400">→</span>
                                <span class="font-semibold text-slate-900">
                                  {{ record.materialUpload.uploadedQuantity }}
                                </span>
                                <span class="ml-1 text-slate-500">条</span>
                              </div>
                              <div
                                v-if="
                                  materialShortfallStatuses.has(
                                    record.status,
                                  ) &&
                                  record.materialUpload.requiredQuantity !==
                                    null &&
                                  record.materialUpload.uploadedQuantity <
                                    record.materialUpload.requiredQuantity
                                "
                                class="mt-1 truncate text-rose-500"
                              >
                                还差
                                {{
                                  record.materialUpload.requiredQuantity -
                                  record.materialUpload.uploadedQuantity
                                }}
                              </div>
                              <div
                                v-else-if="
                                  record.materialUpload.requiredQuantity !==
                                    null &&
                                  record.materialUpload.uploadedQuantity >=
                                    record.materialUpload.requiredQuantity
                                "
                                class="mt-1 text-slate-400"
                              >
                                已达需求
                              </div>
                            </div>
                            <span v-else class="text-slate-300">—</span>
                          </template>
                          <template v-else-if="column.key === 'dueAt'">
                            <div class="truncate text-xs text-slate-500">
                              {{
                                formatTaskDueDate({
                                  dueAt: record.dueAt,
                                  kind: record.kind,
                                })
                              }}
                            </div>
                          </template>
                          <template v-else-if="column.key === 'status'">
                            <Tag
                              :color="
                                statusMeta[record.status as TaskStatus].color
                              "
                            >
                              {{ taskStatusLabel(record) }}
                            </Tag>
                          </template>
                          <template v-else-if="column.key === 'actions'">
                            <div class="task-row-actions">
                              <template v-if="record.legacyMaterialOrderId">
                                <MaterialTaskActionMenu
                                  inline
                                  :actions="materialTaskActions(record)"
                                  :loading="
                                    lifecyclePendingId ===
                                    record.legacyMaterialOrderId
                                  "
                                  :disabled="!!lifecyclePendingId"
                                  @select="
                                    runMaterialTaskAction(record, $event)
                                  "
                                />
                              </template>
                              <template v-else-if="record.status === 'draft'">
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  任务编辑
                                </Button>
                              </template>
                              <template v-else-if="canResubmitTask(record)">
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  查看任务
                                </Button>
                                <Popconfirm
                                  cancel-text="取消"
                                  ok-text="再次提交"
                                  :title="`确定再次提交“${record.title}”吗？`"
                                  @confirm="resubmitTask(record)"
                                >
                                  <Button
                                    class="task-action-button"
                                    type="link"
                                  >
                                    再次提交
                                  </Button>
                                </Popconfirm>
                              </template>
                              <template
                                v-else-if="record.status === 'rejected'"
                              >
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  查看任务
                                </Button>
                              </template>
                              <template
                                v-else-if="
                                  canAssignTask(record) &&
                                  !canWithdrawTask(record)
                                "
                              >
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  查看任务
                                </Button>
                                <Button
                                  class="task-action-button"
                                  :disabled="!canOperateAssignment(record)"
                                  type="link"
                                  @click="openAssignmentModal(record)"
                                >
                                  {{
                                    isMaterialOrderTask(record)
                                      ? record.materialAssignments?.length
                                        ? '修改分配'
                                        : '分配任务'
                                      : '分配任务'
                                  }}
                                </Button>
                                <Button
                                  v-if="canDeclineTask(record)"
                                  class="task-action-button"
                                  danger
                                  type="link"
                                  @click="openDeclineModal(record)"
                                >
                                  驳回任务
                                </Button>
                              </template>
                              <template v-else-if="canAcceptTask(record)">
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  查看任务
                                </Button>
                                <Button
                                  class="task-action-button"
                                  :disabled="!canOperateAcceptance(record)"
                                  type="link"
                                  @click="openAcceptanceModal(record)"
                                >
                                  {{
                                    record.legacyMaterialOrderId
                                      ? '验收素材'
                                      : '验收任务'
                                  }}
                                </Button>
                              </template>
                              <template v-else-if="canWithdrawTask(record)">
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  查看任务
                                </Button>
                                <Popconfirm
                                  cancel-text="取消"
                                  ok-text="确认撤回"
                                  ok-type="danger"
                                  :title="`确定撤回“${record.title}”吗？`"
                                  @confirm="withdrawTask(record)"
                                >
                                  <Button
                                    class="task-action-button"
                                    danger
                                    type="link"
                                  >
                                    撤回任务
                                  </Button>
                                </Popconfirm>
                              </template>
                              <template
                                v-else-if="isAwaitingTaskConfirmation(record)"
                              >
                                <Button
                                  v-if="canModifyMaterialAssignment(record)"
                                  type="link"
                                  @click="openAssignmentModal(record)"
                                  >修改分配</Button
                                >
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  查看任务
                                </Button>
                                <Button
                                  class="task-action-button"
                                  :disabled="!canConfirmTask(record)"
                                  type="link"
                                  @click="confirmAssignedTask(record)"
                                >
                                  确认任务
                                </Button>
                                <Button
                                  v-if="canDeclineTask(record)"
                                  class="task-action-button"
                                  danger
                                  :disabled="!canDeclineTask(record)"
                                  type="link"
                                  @click="openDeclineModal(record)"
                                >
                                  驳回任务
                                </Button>
                              </template>
                              <template v-else-if="isProcessingTask(record)">
                                <Button
                                  v-if="canModifyMaterialAssignment(record)"
                                  type="link"
                                  @click="openAssignmentModal(record)"
                                  >修改分配</Button
                                >
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  查看任务
                                </Button>
                                <template
                                  v-if="isFormalMaterialOrderTask(record)"
                                >
                                  <Button
                                    class="task-action-button"
                                    :disabled="!canChangeActiveStatus(record)"
                                    type="link"
                                    @click="openMaterialDelivery(record)"
                                  >
                                    上传素材
                                  </Button>
                                  <Button
                                    class="task-action-button"
                                    :disabled="!canChangeActiveStatus(record)"
                                    type="link"
                                    @click="openCompletionForm(record)"
                                  >
                                    完成任务
                                  </Button>
                                </template>
                                <Button
                                  v-else-if="canChangeActiveStatus(record)"
                                  class="task-action-button"
                                  type="link"
                                  @click="openCompletionForm(record)"
                                >
                                  {{
                                    record.legacyMaterialOrderId
                                      ? '提交交付'
                                      : '完成任务'
                                  }}
                                </Button>
                              </template>
                              <template v-else-if="actionContext === 'created'">
                                <template
                                  v-if="record.status === 'pending_acceptance'"
                                >
                                  <Button
                                    class="task-action-button"
                                    type="link"
                                    @click="openTask(record)"
                                  >
                                    查看任务
                                  </Button>
                                  <Button
                                    class="task-action-button"
                                    type="link"
                                    @click="openAcceptanceModal(record)"
                                  >
                                    验收任务
                                  </Button>
                                </template>
                                <template v-else>
                                  <Button
                                    class="task-action-button"
                                    type="link"
                                    @click="openEditTask(record)"
                                  >
                                    编辑任务
                                  </Button>
                                  <Popconfirm
                                    cancel-text="取消"
                                    :disabled="!canWithdrawTask(record)"
                                    ok-text="确认撤回"
                                    ok-type="danger"
                                    :title="`确定撤回“${record.title}”吗？`"
                                    @confirm="withdrawTask(record)"
                                  >
                                    <Button
                                      class="task-action-button"
                                      danger
                                      :disabled="!canWithdrawTask(record)"
                                      type="link"
                                    >
                                      撤回任务
                                    </Button>
                                  </Popconfirm>
                                </template>
                              </template>
                              <Button
                                v-else-if="actionContext === 'assigned'"
                                class="task-action-button"
                                type="link"
                                @click="openTaskProgress(record)"
                              >
                                查看任务进度
                              </Button>
                              <template
                                v-else-if="actionContext === 'completed'"
                              >
                                <Popconfirm
                                  cancel-text="取消"
                                  ok-text="再次提交"
                                  :title="`确定再次提交“${record.title}”吗？`"
                                  @confirm="resubmitTask(record)"
                                >
                                  <Button
                                    class="task-action-button"
                                    type="link"
                                  >
                                    再次提交
                                  </Button>
                                </Popconfirm>
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openEditTask(record, 'modify-submit')"
                                >
                                  修改提交
                                </Button>
                              </template>
                              <template v-else>
                                <Button
                                  class="task-action-button"
                                  type="link"
                                  @click="openTask(record)"
                                >
                                  查看任务
                                </Button>
                                <Button
                                  v-if="
                                    actionContext === 'owned' &&
                                    canChangeActiveStatus(record)
                                  "
                                  class="task-action-button"
                                  type="link"
                                  @click="openCompletionForm(record)"
                                >
                                  完成任务
                                </Button>
                              </template>
                            </div>
                          </template>
                        </template>
                      </Table>

                      <div class="task-mobile-list">
                        <article
                          v-for="task in group.tasks"
                          :key="task.id"
                          class="task-mobile-card"
                        >
                          <div class="flex min-w-0 items-start gap-2">
                            <Button
                              :aria-label="
                                isFollowed(task.id)
                                  ? `取消关注${task.title}`
                                  : `关注${task.title}`
                              "
                              :loading="pendingFollowTaskIds.has(task.id)"
                              :aria-pressed="isFollowed(task.id)"
                              class="task-follow-button"
                              type="text"
                              @click="toggleFollow(task.id)"
                            >
                              <IconifyIcon
                                :class="
                                  isFollowed(task.id)
                                    ? 'fill-amber-400 text-amber-500'
                                    : 'text-slate-400'
                                "
                                icon="lucide:star"
                              />
                            </Button>
                            <div class="min-w-0 flex-1">
                              <button
                                class="task-title-button"
                                type="button"
                                @click="openTask(task)"
                              >
                                {{ task.title }}
                              </button>
                              <div
                                class="mt-1 break-all text-xs text-slate-500"
                              >
                                {{ taskDisplayNumber(task) }}
                              </div>
                            </div>
                            <Tag :color="statusMeta[task.status].color">
                              {{ taskStatusLabel(task) }}
                            </Tag>
                          </div>

                          <p class="mb-0 mt-3 text-sm leading-6 text-slate-600">
                            {{ task.summary }}
                          </p>
                          <div class="mt-3 flex min-w-0 flex-wrap gap-2">
                            <Tag :color="kindMeta[task.kind].color">
                              {{ kindMeta[task.kind].shortLabel }}
                            </Tag>
                            <Tag>{{ task.project }}</Tag>
                            <Tag>{{ taskProjectOwner(task) }}</Tag>
                          </div>
                          <div
                            v-if="task.kind === 'material'"
                            class="mt-2 space-y-1 break-words text-xs text-slate-600"
                          >
                            <div>
                              创意策划：{{
                                materialParticipantNames(
                                  task,
                                  'creativePlanner',
                                )
                              }}
                            </div>
                            <div>
                              素材师：{{
                                materialParticipantNames(task, 'designer')
                              }}
                            </div>
                          </div>
                          <div
                            class="mt-3 flex items-center justify-between gap-2 text-xs text-slate-500"
                          >
                            <span>截止时间</span>
                            <span class="truncate">{{
                              formatTaskDueDate(task)
                            }}</span>
                          </div>

                          <div class="task-mobile-actions">
                            <template v-if="task.legacyMaterialOrderId">
                              <MaterialTaskActionMenu
                                :actions="materialTaskActions(task)"
                                :loading="
                                  lifecyclePendingId ===
                                  task.legacyMaterialOrderId
                                "
                                :disabled="!!lifecyclePendingId"
                                @select="runMaterialTaskAction(task, $event)"
                              />
                            </template>
                            <template v-else-if="task.status === 'draft'">
                              <Button type="link" @click="openTask(task)">
                                任务编辑
                              </Button>
                            </template>
                            <template v-else-if="canResubmitTask(task)">
                              <Button block @click="openTask(task)"
                                >查看任务</Button
                              >
                              <Popconfirm
                                cancel-text="取消"
                                ok-text="再次提交"
                                :title="`确定再次提交“${task.title}”吗？`"
                                @confirm="resubmitTask(task)"
                              >
                                <Button block>再次提交</Button>
                              </Popconfirm>
                            </template>
                            <template v-else-if="task.status === 'rejected'">
                              <Button block @click="openTask(task)">
                                查看任务
                              </Button>
                            </template>
                            <template
                              v-else-if="
                                canAssignTask(task) && !canWithdrawTask(task)
                              "
                            >
                              <Button block @click="openTask(task)">
                                查看任务
                              </Button>
                              <Button
                                block
                                :disabled="!canOperateAssignment(task)"
                                type="primary"
                                @click="openAssignmentModal(task)"
                              >
                                {{
                                  task.legacyMaterialOrderId
                                    ? task.materialAssignments?.length
                                      ? '修改分配'
                                      : '分配任务'
                                    : '分配任务'
                                }}
                              </Button>
                              <Button
                                v-if="canDeclineTask(task)"
                                block
                                danger
                                @click="openDeclineModal(task)"
                              >
                                驳回任务
                              </Button>
                            </template>
                            <template v-else-if="canAcceptTask(task)">
                              <Button block @click="openTask(task)">
                                查看任务
                              </Button>
                              <Button
                                block
                                :disabled="!canOperateAcceptance(task)"
                                type="primary"
                                @click="openAcceptanceModal(task)"
                              >
                                {{
                                  task.legacyMaterialOrderId
                                    ? '验收素材'
                                    : '验收任务'
                                }}
                              </Button>
                            </template>
                            <template v-else-if="canWithdrawTask(task)">
                              <Button block @click="openTask(task)">
                                查看任务
                              </Button>
                              <Popconfirm
                                cancel-text="取消"
                                ok-text="确认撤回"
                                ok-type="danger"
                                :title="`确定撤回“${task.title}”吗？`"
                                @confirm="withdrawTask(task)"
                              >
                                <Button block danger>撤回任务</Button>
                              </Popconfirm>
                            </template>
                            <template
                              v-else-if="isAwaitingTaskConfirmation(task)"
                            >
                              <Button
                                v-if="canModifyMaterialAssignment(task)"
                                type="link"
                                @click="openAssignmentModal(task)"
                                >修改分配</Button
                              >
                              <Button block @click="openTask(task)">
                                查看任务
                              </Button>
                              <Button
                                block
                                :disabled="!canConfirmTask(task)"
                                type="primary"
                                @click="confirmAssignedTask(task)"
                              >
                                确认任务
                              </Button>
                              <Button
                                v-if="canDeclineTask(task)"
                                block
                                danger
                                :disabled="!canDeclineTask(task)"
                                @click="openDeclineModal(task)"
                              >
                                驳回任务
                              </Button>
                            </template>
                            <template v-else-if="isProcessingTask(task)">
                              <Button
                                v-if="canModifyMaterialAssignment(task)"
                                type="link"
                                @click="openAssignmentModal(task)"
                                >修改分配</Button
                              >
                              <Button block @click="openTask(task)">
                                查看任务
                              </Button>
                              <template v-if="isFormalMaterialOrderTask(task)">
                                <Button
                                  block
                                  :disabled="!canChangeActiveStatus(task)"
                                  @click="openMaterialDelivery(task)"
                                >
                                  上传素材
                                </Button>
                                <Button
                                  block
                                  :disabled="!canChangeActiveStatus(task)"
                                  type="primary"
                                  @click="openCompletionForm(task)"
                                >
                                  完成任务
                                </Button>
                              </template>
                              <Button
                                v-else-if="canChangeActiveStatus(task)"
                                block
                                type="primary"
                                @click="openCompletionForm(task)"
                              >
                                {{
                                  task.legacyMaterialOrderId
                                    ? '提交交付'
                                    : '完成任务'
                                }}
                              </Button>
                            </template>
                            <template v-else-if="actionContext === 'created'">
                              <template
                                v-if="task.status === 'pending_acceptance'"
                              >
                                <Button block @click="openTask(task)">
                                  查看任务
                                </Button>
                                <Button
                                  block
                                  type="primary"
                                  @click="openAcceptanceModal(task)"
                                >
                                  验收任务
                                </Button>
                              </template>
                              <template v-else>
                                <Button block @click="openEditTask(task)">
                                  编辑任务
                                </Button>
                                <Popconfirm
                                  cancel-text="取消"
                                  :disabled="!canWithdrawTask(task)"
                                  ok-text="确认撤回"
                                  ok-type="danger"
                                  :title="`确定撤回“${task.title}”吗？`"
                                  @confirm="withdrawTask(task)"
                                >
                                  <Button
                                    block
                                    danger
                                    :disabled="!canWithdrawTask(task)"
                                  >
                                    撤回任务
                                  </Button>
                                </Popconfirm>
                              </template>
                            </template>
                            <Button
                              v-else-if="actionContext === 'assigned'"
                              block
                              class="col-span-2"
                              @click="openTaskProgress(task)"
                            >
                              查看任务进度
                            </Button>
                            <template v-else-if="actionContext === 'completed'">
                              <Popconfirm
                                cancel-text="取消"
                                ok-text="再次提交"
                                :title="`确定再次提交“${task.title}”吗？`"
                                @confirm="resubmitTask(task)"
                              >
                                <Button block>再次提交</Button>
                              </Popconfirm>
                              <Button
                                block
                                @click="openEditTask(task, 'modify-submit')"
                              >
                                修改提交
                              </Button>
                            </template>
                            <template v-else>
                              <Button block @click="openTask(task)">
                                查看任务
                              </Button>
                              <Button
                                v-if="
                                  actionContext === 'owned' &&
                                  canChangeActiveStatus(task)
                                "
                                block
                                type="primary"
                                @click="openCompletionForm(task)"
                              >
                                完成任务
                              </Button>
                            </template>
                          </div>
                        </article>
                      </div>
                    </template>
                    <Empty
                      v-else
                      class="py-14"
                      description="当前筛选条件下暂无任务"
                    />
                  </Card>
                </div>
                <footer
                  v-if="activeTaskTab === 'material' && displayTaskSummary"
                  class="task-summary-footer"
                  aria-live="polite"
                >
                  <div class="task-summary-title">
                    <IconifyIcon icon="lucide:sigma" aria-hidden="true" />
                    <span>当前任务汇总</span>
                  </div>
                  <div class="task-summary-metrics">
                    <span>共 {{ displayTaskSummary.totalCount }} 项</span>
                    <span
                      >进行中 {{ displayTaskSummary.inProgressCount }} 项</span
                    >
                    <span>
                      待验收 {{ displayTaskSummary.pendingAcceptanceCount }} 项
                    </span>
                    <span>风险 {{ displayTaskSummary.riskCount }} 项</span>
                    <span>
                      素材工单
                      {{ displayTaskSummary.material.syncedTaskCount }}/{{
                        displayTaskSummary.material.taskCount
                      }}
                      已同步
                    </span>
                    <span>
                      素材需求 → 实传
                      {{ displayTaskSummary.material.requiredQuantity }} →
                      {{ displayTaskSummary.material.uploadedQuantity }} 条
                    </span>
                  </div>
                </footer>
              </div>

              <div
                v-else-if="viewMode === 'board'"
                class="task-board"
                aria-label="任务看板"
              >
                <section
                  v-for="column in boardColumns"
                  :key="column.key"
                  class="task-board-column"
                >
                  <header class="task-board-header">
                    <span
                      class="flex items-center gap-2 font-medium text-slate-800"
                    >
                      <span
                        class="h-2 w-2 rounded-full"
                        :class="column.tone"
                      ></span>
                      {{ column.label }}
                    </span>
                    <span class="task-board-count">{{
                      column.tasks.length
                    }}</span>
                  </header>
                  <div class="space-y-2.5 p-3">
                    <article
                      v-for="task in column.tasks"
                      :key="task.id"
                      class="task-board-card"
                    >
                      <div class="flex items-start justify-between gap-2">
                        <Tag :color="kindMeta[task.kind].color">
                          {{ kindMeta[task.kind].shortLabel }}
                        </Tag>
                        <Button
                          :aria-label="
                            isFollowed(task.id)
                              ? `取消关注${task.title}`
                              : `关注${task.title}`
                          "
                          :loading="pendingFollowTaskIds.has(task.id)"
                          :aria-pressed="isFollowed(task.id)"
                          class="task-follow-button"
                          type="text"
                          @click="toggleFollow(task.id)"
                        >
                          <IconifyIcon
                            :class="
                              isFollowed(task.id)
                                ? 'fill-amber-400 text-amber-500'
                                : 'text-slate-400'
                            "
                            icon="lucide:star"
                          />
                        </Button>
                      </div>
                      <button
                        class="task-title-button mt-2"
                        type="button"
                        @click="openTask(task)"
                      >
                        {{ task.title }}
                      </button>
                      <div class="mt-1 text-xs text-slate-500">
                        {{ task.project }}
                      </div>
                      <Progress class="mt-3" :percent="task.progress" />
                      <div
                        class="mt-3 flex items-center justify-between gap-2 text-xs text-slate-500"
                      >
                        <span class="truncate">{{
                          taskProjectOwner(task)
                        }}</span>
                        <span class="shrink-0">{{
                          formatTaskDueDate(task)
                        }}</span>
                      </div>
                      <div
                        v-if="task.kind === 'material'"
                        class="mt-2 space-y-1 break-words text-xs text-slate-600"
                      >
                        <div>
                          创意策划：{{
                            materialParticipantNames(task, 'creativePlanner')
                          }}
                        </div>
                        <div>
                          素材师：{{
                            materialParticipantNames(task, 'designer')
                          }}
                        </div>
                      </div>
                      <div class="task-card-actions">
                        <template v-if="task.legacyMaterialOrderId">
                          <MaterialTaskActionMenu
                            :actions="materialTaskActions(task)"
                            :loading="
                              lifecyclePendingId === task.legacyMaterialOrderId
                            "
                            :disabled="!!lifecyclePendingId"
                            @select="runMaterialTaskAction(task, $event)"
                          />
                        </template>
                        <template v-else-if="task.status === 'draft'">
                          <Button type="link" @click="openTask(task)">
                            任务编辑
                          </Button>
                        </template>
                        <template v-else-if="canResubmitTask(task)">
                          <Button @click="openTask(task)"> 查看任务 </Button>
                          <Popconfirm
                            cancel-text="取消"
                            ok-text="再次提交"
                            :title="`确定再次提交“${task.title}”吗？`"
                            @confirm="resubmitTask(task)"
                          >
                            <Button>再次提交</Button>
                          </Popconfirm>
                        </template>
                        <template v-else-if="task.status === 'rejected'">
                          <Button @click="openTask(task)"> 查看任务 </Button>
                        </template>
                        <template
                          v-else-if="
                            canAssignTask(task) && !canWithdrawTask(task)
                          "
                        >
                          <Button @click="openTask(task)"> 查看任务 </Button>
                          <Button
                            :disabled="!canOperateAssignment(task)"
                            type="primary"
                            @click="openAssignmentModal(task)"
                          >
                            分配任务
                          </Button>
                          <Button
                            v-if="canDeclineTask(task)"
                            danger
                            @click="openDeclineModal(task)"
                          >
                            驳回任务
                          </Button>
                        </template>
                        <template v-else-if="canAcceptTask(task)">
                          <Button @click="openTask(task)"> 查看任务 </Button>
                          <Button
                            :disabled="!canOperateAcceptance(task)"
                            type="primary"
                            @click="openAcceptanceModal(task)"
                          >
                            验收任务
                          </Button>
                        </template>
                        <template v-else-if="canWithdrawTask(task)">
                          <Button @click="openTask(task)"> 查看任务 </Button>
                          <Popconfirm
                            cancel-text="取消"
                            ok-text="确认撤回"
                            ok-type="danger"
                            :title="`确定撤回“${task.title}”吗？`"
                            @confirm="withdrawTask(task)"
                          >
                            <Button danger>撤回任务</Button>
                          </Popconfirm>
                        </template>
                        <template v-else-if="isAwaitingTaskConfirmation(task)">
                          <Button
                            v-if="canModifyMaterialAssignment(task)"
                            type="link"
                            @click="openAssignmentModal(task)"
                            >修改分配</Button
                          >
                          <Button @click="openTask(task)"> 查看任务 </Button>
                          <Button
                            :disabled="!canConfirmTask(task)"
                            type="primary"
                            @click="confirmAssignedTask(task)"
                          >
                            确认任务
                          </Button>
                          <Button
                            v-if="canDeclineTask(task)"
                            danger
                            :disabled="!canDeclineTask(task)"
                            @click="openDeclineModal(task)"
                          >
                            驳回任务
                          </Button>
                        </template>
                        <template v-else-if="isProcessingTask(task)">
                          <Button
                            v-if="canModifyMaterialAssignment(task)"
                            type="link"
                            @click="openAssignmentModal(task)"
                            >修改分配</Button
                          >
                          <Button @click="openTask(task)"> 查看任务 </Button>
                          <template v-if="isFormalMaterialOrderTask(task)">
                            <Button
                              :disabled="!canChangeActiveStatus(task)"
                              @click="openMaterialDelivery(task)"
                            >
                              上传素材
                            </Button>
                            <Button
                              :disabled="!canChangeActiveStatus(task)"
                              type="primary"
                              @click="openCompletionForm(task)"
                            >
                              完成任务
                            </Button>
                          </template>
                          <Button
                            v-else-if="canChangeActiveStatus(task)"
                            type="primary"
                            @click="openCompletionForm(task)"
                          >
                            完成任务
                          </Button>
                        </template>
                        <template v-else-if="actionContext === 'created'">
                          <template v-if="task.status === 'pending_acceptance'">
                            <Button @click="openTask(task)"> 查看任务 </Button>
                            <Button
                              type="primary"
                              @click="openAcceptanceModal(task)"
                            >
                              验收任务
                            </Button>
                          </template>
                          <template v-else>
                            <Button @click="openEditTask(task)">
                              编辑任务
                            </Button>
                            <Popconfirm
                              cancel-text="取消"
                              :disabled="!canWithdrawTask(task)"
                              ok-text="确认撤回"
                              ok-type="danger"
                              :title="`确定撤回“${task.title}”吗？`"
                              @confirm="withdrawTask(task)"
                            >
                              <Button danger :disabled="!canWithdrawTask(task)">
                                撤回任务
                              </Button>
                            </Popconfirm>
                          </template>
                        </template>
                        <Button
                          v-else-if="actionContext === 'assigned'"
                          block
                          @click="openTaskProgress(task)"
                        >
                          查看任务进度
                        </Button>
                        <template v-else-if="actionContext === 'completed'">
                          <Popconfirm
                            cancel-text="取消"
                            ok-text="再次提交"
                            :title="`确定再次提交“${task.title}”吗？`"
                            @confirm="resubmitTask(task)"
                          >
                            <Button>再次提交</Button>
                          </Popconfirm>
                          <Button @click="openEditTask(task, 'modify-submit')">
                            修改提交
                          </Button>
                        </template>
                        <template v-else>
                          <Button @click="openTask(task)"> 查看任务 </Button>
                          <Button
                            v-if="
                              actionContext === 'owned' &&
                              canChangeActiveStatus(task)
                            "
                            type="primary"
                            @click="openCompletionForm(task)"
                          >
                            完成任务
                          </Button>
                        </template>
                      </div>
                    </article>
                    <Empty
                      v-if="column.tasks.length === 0"
                      :image="Empty.PRESENTED_IMAGE_SIMPLE"
                      description="暂无任务"
                    />
                  </div>
                </section>
              </div>

              <div v-else class="space-y-3">
                <section
                  class="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6"
                >
                  <Card v-for="item in summaryCards" :key="item.key">
                    <div class="flex items-center gap-3">
                      <span
                        class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
                        :class="item.tone"
                      >
                        <IconifyIcon :icon="item.icon" class="text-lg" />
                      </span>
                      <div>
                        <div class="text-xs text-slate-500">
                          {{ item.label }}
                        </div>
                        <div
                          class="mt-0.5 text-2xl font-semibold tabular-nums text-slate-900"
                        >
                          {{ item.value }}
                        </div>
                      </div>
                    </div>
                  </Card>
                </section>

                <div class="grid gap-3 xl:grid-cols-6">
                  <Card class="xl:col-span-4" title="项目任务进度">
                    <div v-if="projectSummary.length > 0" class="space-y-5">
                      <div
                        v-for="project in projectSummary"
                        :key="project.project"
                      >
                        <div
                          class="mb-2 flex items-center justify-between gap-3"
                        >
                          <span class="truncate font-medium text-slate-800">
                            {{ project.project }}
                          </span>
                          <span class="shrink-0 text-xs text-slate-500">
                            {{ project.completed }}/{{ project.total }} 已完成
                          </span>
                        </div>
                        <Progress :percent="project.percent" />
                      </div>
                    </div>
                    <Empty v-else description="暂无项目任务" />
                  </Card>

                  <Card class="xl:col-span-2" title="优先处理">
                    <div class="space-y-2.5">
                      <button
                        v-for="task in filteredTasks.filter(
                          (item) =>
                            item.status === 'risk' ||
                            item.status === 'pending_assignment' ||
                            item.status === 'assigned_pending_confirmation' ||
                            item.status === 'pending' ||
                            item.status === 'pending_acceptance',
                        )"
                        :key="task.id"
                        class="task-priority-item"
                        type="button"
                        @click="openTask(task)"
                      >
                        <Tag :color="statusMeta[task.status].color">
                          {{ taskStatusLabel(task) }}
                        </Tag>
                        <span class="min-w-0 flex-1 text-left">
                          <strong
                            class="block truncate font-medium text-slate-800"
                          >
                            {{ task.title }}
                          </strong>
                          <small class="mt-0.5 block truncate text-slate-500">
                            {{ taskProjectOwner(task) }} ·
                            {{ formatTaskDueDate(task) }}
                          </small>
                        </span>
                        <IconifyIcon
                          class="shrink-0 text-slate-400"
                          icon="lucide:chevron-right"
                        />
                      </button>
                    </div>
                  </Card>
                </div>
              </div>

              <Empty
                v-if="filteredTasks.length === 0 && viewMode !== 'list'"
                class="mt-3 rounded-xl border border-slate-200 bg-white py-16"
                description="当前筛选条件下暂无任务"
              />
            </div>
            <footer v-if="isDeliveryList" class="task-delivery-pagination">
              <span class="text-muted-foreground text-xs" role="status">
                {{
                  deliveryLoading
                    ? '正在加载…'
                    : deliveryError
                      ? '加载失败，请重试'
                      : viewMode === 'list'
                        ? `共 ${deliveryTotal} 项，当前页筛选后 ${filteredTasks.length} 项`
                        : `当前筛选共 ${filteredTasks.length} 项`
                }}
              </span>
              <Pagination
                v-if="viewMode === 'list'"
                :current="deliveryPage"
                :page-size="deliveryPageSize"
                :total="deliveryTotal"
                :page-size-options="['10', '20', '50', '100']"
                :disabled="deliveryLoading"
                show-size-changer
                show-less-items
                @change="changeDeliveryPage"
              />
            </footer>
            <footer v-else-if="isMaterialList" class="task-delivery-pagination">
              <span class="text-muted-foreground text-xs" role="status">
                {{
                  materialLoading
                    ? '正在加载…'
                    : materialError
                      ? '加载失败，请重试'
                      : `共 ${materialTotal} 个工单 · ${materialQuantity} 个素材`
                }}
              </span>
              <Pagination
                v-if="viewMode === 'list'"
                :current="materialPage"
                :page-size="materialPageSize"
                :total="materialTotal"
                :page-size-options="['10', '20', '50', '100', '200']"
                :disabled="materialLoading"
                show-size-changer
                show-less-items
                @change="changeMaterialPage"
              />
            </footer>
          </template>
        </main>
      </div>
    </div>

    <Modal
      v-model:open="editModalOpen"
      cancel-text="取消"
      :ok-text="editMode === 'modify-submit' ? '确认修改并提交' : '保存修改'"
      :title="editMode === 'modify-submit' ? '修改提交' : '编辑任务'"
      :width="560"
      @ok="saveTaskEdit"
    >
      <div v-if="editingTask" class="space-y-4 pt-2">
        <div
          v-if="editMode === 'modify-submit'"
          class="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm leading-6 text-blue-700"
        >
          保存后任务将重新进入待处理状态，进度从 0% 开始。
        </div>
        <div>
          <label
            class="mb-1.5 block text-sm font-medium text-slate-700"
            for="task-edit-title"
          >
            任务标题
          </label>
          <Input
            id="task-edit-title"
            v-model:value="editForm.title"
            :maxlength="80"
            placeholder="请输入任务标题"
            show-count
          />
        </div>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label
              class="mb-1.5 block text-sm font-medium text-slate-700"
              for="task-edit-owner"
            >
              负责人
            </label>
            <Input
              id="task-edit-owner"
              v-model:value="editForm.owner"
              placeholder="请输入负责人"
            />
          </div>
          <div>
            <label
              class="mb-1.5 block text-sm font-medium text-slate-700"
              for="task-edit-due-at"
            >
              截止时间
            </label>
            <Input
              id="task-edit-due-at"
              v-model:value="editForm.dueAt"
              placeholder="例如：8 月 13 日 18:00"
            />
          </div>
        </div>
        <div>
          <label
            class="mb-1.5 block text-sm font-medium text-slate-700"
            for="task-edit-summary"
          >
            需求说明
          </label>
          <Input.TextArea
            id="task-edit-summary"
            v-model:value="editForm.summary"
            :auto-size="{ minRows: 4, maxRows: 8 }"
            :maxlength="500"
            placeholder="请输入需求说明"
            show-count
          />
        </div>
      </div>
    </Modal>

    <Modal
      v-model:open="progressModalOpen"
      :footer="null"
      title="任务进度"
      :width="560"
    >
      <div v-if="progressTask" class="pt-2">
        <div class="flex min-w-0 items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="m-0 text-base font-semibold text-slate-900">
              {{ progressTask.title }}
            </h3>
            <p class="mb-0 mt-1 break-all text-xs text-slate-500">
              {{ progressTask.id }} · {{ progressTask.project }}
            </p>
          </div>
          <Tag :color="statusMeta[progressTask.status].color">
            {{ taskStatusLabel(progressTask) }}
          </Tag>
        </div>

        <div class="mt-5 rounded-xl bg-slate-50 p-4">
          <div
            class="mb-2 flex items-center justify-between gap-3 text-sm text-slate-600"
          >
            <span>当前进度</span>
            <strong class="text-lg tabular-nums text-slate-900">
              {{ progressTask.progress }}%
            </strong>
          </div>
          <Progress :percent="progressTask.progress" />
        </div>

        <dl class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div class="task-progress-detail">
            <dt>负责人</dt>
            <dd>{{ progressTask.owner }}</dd>
          </div>
          <div class="task-progress-detail">
            <dt>截止时间</dt>
            <dd>{{ formatTaskDueDate(progressTask) }}</dd>
          </div>
          <div class="task-progress-detail sm:col-span-2">
            <dt>最近更新</dt>
            <dd>{{ progressTask.updatedAt }}</dd>
          </div>
        </dl>

        <div class="mt-4 rounded-lg border border-slate-200 p-3">
          <div class="text-xs font-medium text-slate-500">需求摘要</div>
          <p class="mb-0 mt-1 text-sm leading-6 text-slate-700">
            {{ progressTask.summary }}
          </p>
        </div>

        <div class="mt-5 flex justify-end gap-2">
          <Button @click="progressModalOpen = false">关闭</Button>
          <Button type="primary" @click="openProgressTaskDetail">
            打开任务详情
          </Button>
        </div>
      </div>
    </Modal>

    <MaterialShareModal
      v-model:open="materialShareOpen"
      :order-id="materialShareOrderId"
      @shared="refreshAfterMaterialAssignment"
    />
    <MaterialAcceptanceDrawer
      :read-only="isSharedView"
      v-model:open="materialAcceptanceOpen"
      :order-id="materialAcceptanceOrderId"
      @changed="refreshAfterMaterialAssignment"
    />
    <MaterialTaskDetailDrawer
      :read-only="isSharedView"
      v-model:open="materialDetailOpen"
      :order-id="materialDetailOrderId"
      :initial-action="materialDetailInitialAction"
      @changed="refreshAfterMaterialAssignment"
      @edit="openMaterialOrderEditor"
      @reedit="openMaterialOrderEditor($event, true)"
      @resubmit="openMaterialOrderResubmit"
    />

    <Drawer
      v-model:open="detailDrawerOpen"
      placement="right"
      width="min(720px, 100vw)"
    >
      <template #title>
        <div v-if="detailTask" class="min-w-0">
          <div class="truncate text-base font-semibold text-slate-900">
            {{ detailTask.title }}
          </div>
          <div class="mt-0.5 text-xs font-normal text-slate-500">
            {{ detailTask.id }}
          </div>
        </div>
      </template>

      <div v-if="detailTask" class="task-detail-content">
        <section class="task-detail-section">
          <div class="task-detail-section-title">
            <IconifyIcon icon="lucide:file-text" />
            原始需求
          </div>
          <p class="mb-0 whitespace-pre-wrap text-sm leading-7 text-slate-700">
            {{ detailTask.summary }}
          </p>
          <dl class="task-detail-grid mt-4">
            <div>
              <dt>项目</dt>
              <dd>{{ detailTask.project }}</dd>
            </div>
            <div>
              <dt>负责人</dt>
              <dd>{{ detailTask.owner }}</dd>
            </div>
            <div>
              <dt>截止时间</dt>
              <dd>{{ formatTaskDueDate(detailTask, '未设置') }}</dd>
            </div>
            <div>
              <dt>任务来源</dt>
              <dd>{{ kindMeta[detailTask.kind].label }}</dd>
            </div>
            <div>
              <dt>来源 ID</dt>
              <dd>{{ detailTask.sourceId || '未关联' }}</dd>
            </div>
            <div v-if="detailTask.source?.kind === 'delivery-task'">
              <dt>来源投放任务</dt>
              <dd>{{ detailTask.source.id }}</dd>
            </div>
            <div>
              <dt>创建人 / 创建时间</dt>
              <dd>{{ detailTask.createdBy }} · {{ detailTask.createdAt }}</dd>
            </div>
          </dl>
        </section>

        <section v-if="detailTask.rejection" class="task-detail-section">
          <div class="task-detail-section-title text-rose-600">
            <IconifyIcon icon="lucide:circle-x" />
            驳回原因
          </div>
          <p class="mb-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">
            {{ detailTask.rejection.reason }}
          </p>
          <div class="text-xs text-slate-500">
            {{ detailTask.rejection.rejectedBy }} ·
            {{ detailTask.rejection.rejectedAt }}
          </div>
        </section>

        <RelatedMaterialTasks
          v-if="detailDrawerOpen && detailTask.kind === 'am' && !demoMode"
          :task-id="detailTask.id"
          @open="openRelatedMaterialOrder"
        />

        <section class="task-detail-section">
          <div class="task-detail-section-title">
            <IconifyIcon icon="lucide:route" />
            投放计划与原始附件
          </div>
          <template v-if="detailTask.delivery">
            <dl class="task-detail-grid">
              <div>
                <dt>任务负责人 / AM</dt>
                <dd>{{ detailTask.delivery.amOwner || '未配置' }}</dd>
              </div>
              <div>
                <dt>投放负责人</dt>
                <dd>
                  {{ detailTask.ownerName || detailTask.owner || '未配置' }}
                </dd>
              </div>
              <div>
                <dt>投放地区</dt>
                <dd>{{ detailTask.delivery.region }}</dd>
              </div>
              <div>
                <dt>平台</dt>
                <dd>{{ detailTask.delivery.platforms.join(' / ') }}</dd>
              </div>
              <div>
                <dt>计划开始</dt>
                <dd>{{ detailTask.delivery.startAt }}</dd>
              </div>
              <div>
                <dt>计划截止</dt>
                <dd>
                  {{ formatTaskDateTime(detailTask.delivery.dueAt, '未设置') }}
                </dd>
              </div>
              <div class="sm:col-span-2">
                <dt>产品信息</dt>
                <dd class="whitespace-pre-line break-all">
                  {{ detailTask.delivery.productUrl || '未配置' }}
                </dd>
              </div>
              <div class="sm:col-span-2">
                <dt>投放目标</dt>
                <dd class="whitespace-pre-wrap">
                  {{ detailTask.delivery.target }}
                </dd>
              </div>
            </dl>

            <div
              v-if="detailTask.delivery.attachments.length > 0"
              class="task-file-list mt-3"
            >
              <div
                v-for="file in detailTask.delivery.attachments"
                :key="file.id"
                class="task-file-row"
              >
                <IconifyIcon icon="lucide:paperclip" />
                <span class="min-w-0 flex-1 truncate">{{ file.name }}</span>
                <span>{{ formatCompletionFileSize(file.size) }}</span>
                <Button
                  :aria-label="`下载附件 ${file.name}`"
                  :loading="
                    downloadingOriginalFileIds.has(
                      String(file.serverFileId || file.id),
                    )
                  "
                  type="link"
                  @click="downloadOriginalFile(file)"
                >
                  下载
                </Button>
              </div>
            </div>
            <div v-else class="mt-3 text-sm text-slate-400">无原始附件</div>
          </template>
          <Empty
            v-else
            :image="Empty.PRESENTED_IMAGE_SIMPLE"
            description="当前任务无关联投放计划"
          />
        </section>

        <section
          v-if="detailTask.delivery?.items?.length"
          class="task-detail-section"
        >
          <div class="task-detail-section-title">投放任务明细</div>
          <DeliveryTaskItems
            :model-value="detailTask.delivery.items"
            read-only
            :operator-names="
              Object.fromEntries(
                detailTask.delivery.allocations.map((item) => [
                  item.assigneeId,
                  item.owner,
                ]),
              )
            "
          />
        </section>
        <section v-if="detailTask.delivery" class="task-detail-section">
          <div class="task-detail-section-title">
            <IconifyIcon icon="lucide:users-round" />
            投手执行情况
            <Tag>{{ detailTask.delivery.allocations.length }} 条</Tag>
          </div>
          <div
            v-if="detailTask.delivery.allocations.length > 0"
            class="grid gap-3 sm:grid-cols-2"
          >
            <article
              v-for="allocation in detailTask.delivery.allocations"
              :key="allocation.id"
              class="rounded-lg border border-slate-200 bg-slate-50 p-3"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <strong class="block truncate text-sm text-slate-800">
                    {{ allocation.owner || '投手' }}
                  </strong>
                  <span class="mt-1 block truncate text-xs text-slate-500">
                    投手：{{ allocation.owner || '未分配' }}
                  </span>
                </div>
                <Tag :color="deliveryAllocationStatusColor(allocation.status)">
                  {{ deliveryAllocationStatusLabel(allocation.status) }}
                </Tag>
              </div>
            </article>
          </div>
          <Empty
            v-else
            :image="Empty.PRESENTED_IMAGE_SIMPLE"
            description="暂无投手执行项"
          />
        </section>

        <section class="task-detail-section">
          <div class="task-detail-section-title">
            <IconifyIcon icon="lucide:package-check" />
            交付记录
            <Tag>{{ displayedDetailCompletionRecords.length }} 条当前交付</Tag>
          </div>

          <div
            v-if="displayedDetailCompletionRecords.length > 0"
            class="space-y-3"
          >
            <article
              v-for="record in displayedDetailCompletionRecords"
              :key="record.submissionId"
              class="task-delivery-record"
            >
              <header class="flex min-w-0 items-start justify-between gap-3">
                <div class="min-w-0">
                  <strong class="block truncate text-sm text-slate-900">
                    {{ completionRecordTitle(record) }}
                  </strong>
                  <div
                    v-if="record.kind === 'am'"
                    class="mt-1 text-xs font-medium text-slate-600"
                  >
                    {{ deliveryAllocationName(record) }}
                  </div>
                  <div class="mt-1 break-all text-xs text-slate-500">
                    {{ record.submissionId }} · {{ record.submittedBy }} ·
                    {{ record.submittedAt }}
                  </div>
                </div>
                <div class="flex shrink-0 items-center gap-2">
                  <Button
                    v-if="
                      record.kind === 'am' &&
                      deliveryRecordsForAllocation(record.allocationId).length >
                        1
                    "
                    size="small"
                    type="link"
                    @click="openDeliveryHistory(record)"
                  >
                    历史版本
                  </Button>
                  <Tag
                    :color="
                      record.kind === 'am' ||
                      detailTask.completion?.current?.submissionId ===
                        record.submissionId
                        ? 'success'
                        : 'default'
                    "
                  >
                    {{
                      record.kind === 'am' ||
                      detailTask.completion?.current?.submissionId ===
                        record.submissionId
                        ? '当前版本'
                        : '历史版本'
                    }}
                  </Tag>
                </div>
              </header>

              <p
                v-if="record.note"
                class="mb-0 mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700"
              >
                {{ record.note }}
              </p>

              <dl v-if="record.kind === 'am'" class="task-detail-grid mt-3">
                <div>
                  <dt>数据来源</dt>
                  <dd>
                    {{
                      record.entryMode === 'delivery-center'
                        ? '投放中心自动抓取'
                        : '手动填写'
                    }}
                    <span
                      v-if="record.sourceSyncedAt"
                      class="block text-xs text-slate-400"
                    >
                      同步于 {{ record.sourceSyncedAt }}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>平台 / 账号</dt>
                  <dd>
                    {{ record.platform }} ·
                    {{ record.accountName || record.accountId }}
                    <span
                      v-if="record.accountName"
                      class="block text-xs text-slate-400"
                    >
                      {{ record.accountId }}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>实际开始</dt>
                  <dd>{{ record.actualStartAt }}</dd>
                </div>
                <div>
                  <dt>Campaign IDs</dt>
                  <dd class="break-all">{{ record.campaignIds.join(', ') }}</dd>
                </div>
                <div v-if="record.sourceAdsetIds?.length">
                  <dt>Ad Set IDs</dt>
                  <dd class="break-all">
                    {{ record.sourceAdsetIds.join(', ') }}
                  </dd>
                </div>
                <div v-if="record.sourceAdIds?.length">
                  <dt>Ad IDs</dt>
                  <dd class="break-all">{{ record.sourceAdIds.join(', ') }}</dd>
                </div>
                <div v-if="record.agencyLineName || record.agencyLineId">
                  <dt>代理线</dt>
                  <dd>{{ record.agencyLineName || record.agencyLineId }}</dd>
                </div>
                <div v-if="record.materialVersion || record.dataCutoffAt">
                  <dt>素材版本 / 数据截止</dt>
                  <dd>
                    {{ record.materialVersion || '—' }}
                    <span class="block text-xs text-slate-400">
                      {{ record.dataCutoffAt || '—' }}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Campaign / Ad Set / Ad</dt>
                  <dd>
                    {{ record.campaignCount }} / {{ record.adsetCount }} /
                    {{ record.adCount }}
                  </dd>
                </div>
                <div>
                  <dt>实际预算</dt>
                  <dd>{{ record.actualBudget }} {{ record.currency }}</dd>
                </div>
                <div>
                  <dt>投放状态</dt>
                  <dd>{{ deliveryStatusLabels[record.deliveryStatus] }}</dd>
                </div>
                <div v-if="record.exceptionNote" class="sm:col-span-2">
                  <dt>异常说明</dt>
                  <dd class="whitespace-pre-wrap">
                    {{ record.exceptionNote }}
                  </dd>
                </div>
              </dl>

              <dl
                v-else-if="record.kind === 'material'"
                class="task-detail-grid mt-3"
              >
                <div>
                  <dt>实际交付数量</dt>
                  <dd>{{ record.deliveredQuantity ?? record.files.length }}</dd>
                </div>
                <div>
                  <dt>素材入库状态</dt>
                  <dd>{{ record.libraryStatus || '无需入库' }}</dd>
                </div>
              </dl>

              <div v-if="record.files.length > 0" class="task-file-list mt-3">
                <div
                  v-for="file in record.files"
                  :key="`${record.submissionId}-${file.id}`"
                  class="task-file-row"
                >
                  <IconifyIcon icon="lucide:file-check-2" />
                  <span class="min-w-0 flex-1 truncate">{{ file.name }}</span>
                  <span>{{ formatCompletionFileSize(file.size) }}</span>
                  <Button
                    v-if="file.serverFileId"
                    :aria-label="`下载交付文件 ${file.name}`"
                    :loading="
                      downloadingOriginalFileIds.has(String(file.serverFileId))
                    "
                    type="link"
                    @click="downloadOriginalFile(file)"
                  >
                    下载
                  </Button>
                </div>
              </div>
              <div v-else class="mt-3 text-xs text-slate-400">本版无附件</div>
            </article>
          </div>
          <Empty
            v-else
            :image="Empty.PRESENTED_IMAGE_SIMPLE"
            description="暂无交付记录"
          />
        </section>

        <section class="task-detail-section">
          <div class="task-detail-section-title">
            <IconifyIcon icon="lucide:clipboard-check" />
            验收记录
            <Tag>{{ detailAcceptanceRecords.length }} 条</Tag>
          </div>
          <div v-if="detailAcceptanceRecords.length > 0" class="space-y-2">
            <div
              v-for="record in detailAcceptanceRecords"
              :key="`${record.submissionId}-${record.reviewedAt}`"
              class="task-acceptance-record"
            >
              <div class="flex min-w-0 items-start justify-between gap-3">
                <div class="min-w-0">
                  <strong class="text-sm text-slate-800">
                    交付 v{{ record.versionNo }} · {{ record.reviewer }}
                  </strong>
                  <div class="mt-1 break-all text-xs text-slate-500">
                    {{ record.reviewedAt }} · {{ record.submissionId }}
                  </div>
                </div>
                <Tag
                  :color="record.decision === 'accepted' ? 'success' : 'error'"
                >
                  {{ record.decision === 'accepted' ? '验收通过' : '已打回' }}
                </Tag>
              </div>
              <p
                v-if="record.reason"
                class="mb-0 mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600"
              >
                {{ record.reason }}
              </p>
            </div>
          </div>
          <Empty
            v-else
            :image="Empty.PRESENTED_IMAGE_SIMPLE"
            description="暂无验收记录"
          />
        </section>

        <div class="task-detail-footer">
          <Button @click="detailDrawerOpen = false">关闭</Button>
          <Button
            v-if="canCreateMaterialFromTask(detailTask)"
            @click="openMaterialTaskCreate(detailTask)"
          >
            发起素材需求
          </Button>
          <Button
            v-if="canCreateResourceApplicationFromTask(detailTask)"
            @click="openResourceApplicationCreate(detailTask)"
          >
            发起资源申请
          </Button>
          <Popconfirm
            v-if="canResubmitTask(detailTask)"
            cancel-text="取消"
            ok-text="再次提交"
            :title="`确定再次提交“${detailTask.title}”吗？`"
            @confirm="resubmitTask(detailTask)"
          >
            <Button>再次提交</Button>
          </Popconfirm>
          <Button
            v-if="
              canAssignTask(detailTask) ||
              canModifyMaterialAssignment(detailTask)
            "
            :disabled="!canOperateAssignment(detailTask)"
            type="primary"
            @click="openAssignmentModal(detailTask)"
          >
            分配任务
          </Button>
          <Button
            v-if="canDeclineTask(detailTask)"
            danger
            @click="openDeclineModal(detailTask)"
          >
            驳回任务
          </Button>
          <Button
            v-if="canAcceptTask(detailTask)"
            :disabled="!canOperateAcceptance(detailTask)"
            type="primary"
            @click="openAcceptanceModal(detailTask)"
          >
            验收任务
          </Button>
          <Button
            v-else-if="canWithdrawTask(detailTask)"
            danger
            @click="withdrawTask(detailTask)"
          >
            撤回任务
          </Button>
          <Button
            v-else-if="isAwaitingTaskConfirmation(detailTask)"
            :disabled="!canConfirmTask(detailTask)"
            type="primary"
            @click="confirmAssignedTask(detailTask)"
          >
            确认任务
          </Button>
          <Button
            v-if="
              isProcessingTask(detailTask) && canChangeActiveStatus(detailTask)
            "
            type="primary"
            @click="openCompletionForm(detailTask)"
          >
            完成任务
          </Button>
          <Button
            v-if="
              isProcessingTask(detailTask) &&
              isFormalMaterialOrderTask(detailTask)
            "
            :disabled="!canChangeActiveStatus(detailTask)"
            @click="openMaterialDelivery(detailTask)"
          >
            上传素材
          </Button>
        </div>
      </div>
    </Drawer>

    <Modal
      v-model:open="deliveryHistoryModalOpen"
      :footer="null"
      :title="deliveryHistoryTitle"
      :width="760"
    >
      <div v-if="deliveryHistoryRecords.length > 0" class="space-y-3 pt-2">
        <article
          v-for="record in deliveryHistoryRecords"
          :key="record.submissionId"
          class="rounded-lg border border-slate-200 p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <strong class="block text-sm text-slate-900">
                {{ completionRecordTitle(record) }}
              </strong>
              <span class="mt-1 block text-xs text-slate-500">
                {{ record.submittedBy }} · {{ record.submittedAt }}
              </span>
            </div>
            <Tag v-if="record.status === 'rejected'" color="error">已打回</Tag>
            <Tag v-else-if="record.status === 'accepted'" color="success"
              >已验收</Tag
            >
            <Tag v-else color="warning">待验收</Tag>
          </div>
          <p
            v-if="record.note"
            class="mb-0 mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700"
          >
            {{ record.note }}
          </p>
          <dl v-if="record.kind === 'am'" class="task-detail-grid mt-3">
            <div>
              <dt>平台 / 账号</dt>
              <dd>
                {{ record.platform }} ·
                {{ record.accountName || record.accountId }}
              </dd>
            </div>
            <div>
              <dt>实际开始 / 预算</dt>
              <dd>
                {{ record.actualStartAt }} · {{ record.actualBudget }}
                {{ record.currency }}
              </dd>
            </div>
            <div>
              <dt>Campaign / Ad Set / Ad</dt>
              <dd>
                {{ record.campaignCount }} / {{ record.adsetCount }} /
                {{ record.adCount }}
              </dd>
            </div>
            <div>
              <dt>投放状态</dt>
              <dd>{{ deliveryStatusLabels[record.deliveryStatus] }}</dd>
            </div>
            <div v-if="record.exceptionNote" class="sm:col-span-2">
              <dt>异常说明</dt>
              <dd class="whitespace-pre-wrap">{{ record.exceptionNote }}</dd>
            </div>
          </dl>
          <div v-if="record.files.length > 0" class="task-file-list mt-3">
            <div
              v-for="file in record.files"
              :key="`${record.submissionId}-${file.id}`"
              class="task-file-row"
            >
              <IconifyIcon icon="lucide:file-check-2" />
              <span class="min-w-0 flex-1 truncate">{{ file.name }}</span>
              <span>{{ formatCompletionFileSize(file.size) }}</span>
              <Button
                v-if="file.serverFileId"
                type="link"
                @click="downloadOriginalFile(file)"
              >
                下载
              </Button>
            </div>
          </div>
          <div v-else class="mt-3 text-xs text-slate-400">本版无附件</div>
        </article>
      </div>
      <Empty v-else description="暂无历史版本" />
    </Modal>

    <MaterialAssignmentModal
      v-model:open="materialAssignmentModalOpen"
      :order-id="materialAssignmentOrderId"
      @assigned="refreshAfterMaterialAssignment"
    />

    <Modal
      v-model:open="assignmentModalOpen"
      cancel-text="取消"
      :confirm-loading="assignmentSubmitting"
      ok-text="确认分配"
      title="分配任务"
      :width="520"
      @ok="submitTaskAssignment"
    >
      <div v-if="assignmentTask" class="space-y-4 pt-2">
        <div class="rounded-lg border border-violet-100 bg-violet-50 px-3 py-2">
          <div class="text-sm font-medium text-violet-950">
            {{ assignmentTask.title }}
          </div>
          <div class="mt-1 text-xs leading-5 text-violet-700">
            {{
              assignmentTask.kind === 'material'
                ? '素材师（可多选）与创意策划（可选）'
                : '投放负责人'
            }}
            {{
              assignmentTask.kind === 'material'
                ? '确认后只更新素材工单的素材师名单，并开始制作。'
                : '确认后任务将进入“待确认”，由被分配负责人确认后开始处理。'
            }}
          </div>
        </div>
        <div>
          <label class="mb-1.5 block text-sm font-medium text-slate-700">
            分配给
          </label>
          <Select
            v-if="demoMode && assignmentTask.kind === 'material'"
            v-model:value="assignmentDesignerNames"
            mode="multiple"
            :options="assignmentCandidates"
            placeholder="请选择素材师，可多选"
          />
          <Select
            v-else-if="demoMode"
            v-model:value="assignmentAssigneeId"
            :options="assignmentCandidates"
            placeholder="请选择对应负责人"
          />
          <StableUserSelect
            v-else-if="assignmentTask.kind === 'material'"
            v-model="assignmentDesignerNames"
            multiple
            assignment-role="creator"
            placeholder="请选择素材师，可多选"
          />
          <StableUserSelect
            v-else
            v-model="assignmentAssigneeId"
            assignment-role="operator"
            placeholder="请选择对应负责人"
          />
        </div>
        <div v-if="assignmentTask.kind === 'material' && !demoMode">
          <label class="mb-1.5 block text-sm font-medium text-slate-700">
            创意策划（可选）
          </label>
          <StableUserSelect
            v-model="assignmentCreativePlannerName"
            assignment-role="operator"
            placeholder="请选择创意策划"
          />
          <p class="mt-1 text-xs leading-5 text-slate-500">
            上传素材时会默认带入这里的创意策划，可在上传弹窗内调整。
          </p>
        </div>
      </div>
    </Modal>

    <Modal
      v-model:open="declineModalOpen"
      cancel-text="取消"
      :confirm-loading="declineSubmitting"
      ok-text="确认驳回"
      ok-type="danger"
      title="驳回任务"
      :width="520"
      @ok="submitTaskDecline"
    >
      <div v-if="declineTask" class="space-y-4 pt-2">
        <div class="rounded-lg border border-rose-100 bg-rose-50 px-3 py-2">
          <div class="text-sm font-medium text-rose-950">
            {{ declineTask.title }}
          </div>
          <div class="mt-1 text-xs leading-5 text-rose-700">
            驳回后任务会进入“已驳回”列表，创建者可查看驳回原因。
          </div>
        </div>
        <div>
          <label class="mb-1.5 block text-sm font-medium text-slate-700">
            驳回原因 <span class="text-rose-500">*</span>
          </label>
          <Input.TextArea
            v-model:value="declineReason"
            :maxlength="500"
            placeholder="请说明为什么驳回，以及需要如何修改"
            :rows="4"
            show-count
          />
          <p v-if="declineError" class="mb-0 mt-1 text-xs text-rose-500">
            {{ declineError }}
          </p>
        </div>
      </div>
    </Modal>

    <Modal
      v-model:open="acceptanceModalOpen"
      :body-style="{
        maxHeight: '72dvh',
        overflowX: 'hidden',
        overflowY: 'auto',
      }"
      :closable="!acceptanceSubmitting"
      :footer="null"
      :mask-closable="!acceptanceSubmitting"
      title="验收任务交付"
      :width="720"
      wrap-class-name="task-completion-modal task-acceptance-modal"
    >
      <div
        v-if="acceptanceTask && selectedAcceptanceCompletion"
        class="task-completion-form"
      >
        <div class="rounded-lg border border-orange-100 bg-orange-50 px-3 py-2">
          <div class="text-sm font-medium text-orange-900">
            {{ acceptanceTask.title }}
          </div>
          <div class="mt-1 break-all text-xs text-orange-700">
            {{ acceptanceTask.id }} · 交付 v{{
              selectedAcceptanceCompletion.versionNo
            }}
            · {{ selectedAcceptanceCompletion.submittedBy }} ·
            {{ selectedAcceptanceCompletion.submittedAt }}
          </div>
        </div>

        <section
          v-if="acceptanceTask.kind === 'am'"
          class="task-delivery-record"
        >
          <div class="task-detail-section-title">
            <IconifyIcon icon="lucide:clipboard-check" />
            待验收投手交付
            <Tag class="ml-1">{{ acceptanceDeliveryRecords.length }} 项</Tag>
          </div>
          <div class="mt-3 grid gap-2 sm:grid-cols-2">
            <button
              v-for="record in acceptanceDeliveryRecords"
              :key="record.submissionId"
              class="rounded-md border px-3 py-2 text-left transition-colors"
              :class="
                selectedAcceptanceSubmissionId === record.submissionId
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-slate-200 bg-slate-50 hover:border-slate-300'
              "
              type="button"
              @click="selectedAcceptanceSubmissionId = record.submissionId"
            >
              <div
                class="flex items-center justify-between gap-2 text-sm font-medium text-slate-800"
              >
                <span class="truncate">{{
                  deliveryAllocationNameForTask(record, acceptanceTask)
                }}</span>
                <Tag color="processing">v{{ record.versionNo }}</Tag>
              </div>
              <div class="mt-1 text-xs text-slate-500">
                {{ record.submittedAt }}
              </div>
            </button>
          </div>
          <p class="mb-0 mt-3 text-xs text-slate-500">
            请选择一位投手查看其本次交付，并单独通过或打回；其余投手的交付不会受影响。
          </p>
        </section>

        <section class="task-delivery-record">
          <div class="task-detail-section-title">
            <IconifyIcon icon="lucide:package-check" />
            本次交付数据
          </div>
          <p
            v-if="selectedAcceptanceCompletion.note"
            class="mb-0 whitespace-pre-wrap text-sm leading-6 text-slate-700"
          >
            {{ selectedAcceptanceCompletion.note }}
          </p>

          <dl
            v-if="selectedAcceptanceCompletion.kind === 'am'"
            class="task-detail-grid mt-3"
          >
            <div>
              <dt>数据来源</dt>
              <dd>
                {{
                  selectedAcceptanceCompletion.entryMode === 'delivery-center'
                    ? '投放中心自动抓取'
                    : '手动填写'
                }}
                <span
                  v-if="selectedAcceptanceCompletion.sourceSyncedAt"
                  class="block text-xs text-slate-400"
                >
                  同步于 {{ selectedAcceptanceCompletion.sourceSyncedAt }}
                </span>
              </dd>
            </div>
            <div>
              <dt>平台 / 账号</dt>
              <dd>
                {{ selectedAcceptanceCompletion.platform }} ·
                {{
                  selectedAcceptanceCompletion.accountName ||
                  selectedAcceptanceCompletion.accountId
                }}
                <span
                  v-if="selectedAcceptanceCompletion.accountName"
                  class="block text-xs text-slate-400"
                >
                  {{ selectedAcceptanceCompletion.accountId }}
                </span>
              </dd>
            </div>
            <div>
              <dt>实际开始</dt>
              <dd>{{ selectedAcceptanceCompletion.actualStartAt }}</dd>
            </div>
            <div>
              <dt>Campaign IDs</dt>
              <dd class="break-all">
                {{ selectedAcceptanceCompletion.campaignIds.join(', ') }}
              </dd>
            </div>
            <div v-if="selectedAcceptanceCompletion.sourceAdsetIds?.length">
              <dt>Ad Set IDs</dt>
              <dd class="break-all">
                {{ selectedAcceptanceCompletion.sourceAdsetIds.join(', ') }}
              </dd>
            </div>
            <div v-if="selectedAcceptanceCompletion.sourceAdIds?.length">
              <dt>Ad IDs</dt>
              <dd class="break-all">
                {{ selectedAcceptanceCompletion.sourceAdIds.join(', ') }}
              </dd>
            </div>
            <div
              v-if="
                selectedAcceptanceCompletion.agencyLineName ||
                selectedAcceptanceCompletion.agencyLineId
              "
            >
              <dt>代理线</dt>
              <dd>
                {{
                  selectedAcceptanceCompletion.agencyLineName ||
                  selectedAcceptanceCompletion.agencyLineId
                }}
              </dd>
            </div>
            <div
              v-if="
                selectedAcceptanceCompletion.materialVersion ||
                selectedAcceptanceCompletion.dataCutoffAt
              "
            >
              <dt>素材版本 / 数据截止</dt>
              <dd>
                {{ selectedAcceptanceCompletion.materialVersion || '—' }}
                <span class="block text-xs text-slate-400">
                  {{ selectedAcceptanceCompletion.dataCutoffAt || '—' }}
                </span>
              </dd>
            </div>
            <div>
              <dt>Campaign / Ad Set / Ad</dt>
              <dd>
                {{ selectedAcceptanceCompletion.campaignCount }} /
                {{ selectedAcceptanceCompletion.adsetCount }} /
                {{ selectedAcceptanceCompletion.adCount }}
              </dd>
            </div>
            <div>
              <dt>实际预算</dt>
              <dd>
                {{ selectedAcceptanceCompletion.actualBudget }}
                {{ selectedAcceptanceCompletion.currency }}
              </dd>
            </div>
            <div>
              <dt>投放状态</dt>
              <dd>
                {{
                  deliveryStatusLabels[
                    selectedAcceptanceCompletion.deliveryStatus
                  ]
                }}
              </dd>
            </div>
            <div
              v-if="selectedAcceptanceCompletion.exceptionNote"
              class="sm:col-span-2"
            >
              <dt>异常说明</dt>
              <dd class="whitespace-pre-wrap">
                {{ selectedAcceptanceCompletion.exceptionNote }}
              </dd>
            </div>
          </dl>

          <div
            v-if="selectedAcceptanceCompletion.files.length > 0"
            class="task-file-list mt-3"
          >
            <div
              v-for="file in selectedAcceptanceCompletion.files"
              :key="file.id"
              class="task-file-row"
            >
              <IconifyIcon icon="lucide:file-check-2" />
              <span class="min-w-0 flex-1 truncate">{{ file.name }}</span>
              <span>{{ formatCompletionFileSize(file.size) }}</span>
              <Button
                v-if="file.serverFileId"
                :aria-label="`下载交付文件 ${file.name}`"
                :loading="
                  downloadingOriginalFileIds.has(String(file.serverFileId))
                "
                type="link"
                @click="downloadOriginalFile(file)"
              >
                下载
              </Button>
            </div>
          </div>
          <div v-else class="mt-3 text-xs text-slate-400">本次交付无附件</div>
        </section>

        <div class="task-completion-field">
          <label for="task-acceptance-reason">
            验收意见
            <small class="font-normal text-slate-400">（打回时必填）</small>
          </label>
          <Input.TextArea
            id="task-acceptance-reason"
            v-model:value="acceptanceReason"
            :aria-invalid="Boolean(acceptanceError)"
            :auto-size="{ minRows: 3, maxRows: 6 }"
            :maxlength="500"
            placeholder="填写验收结论；若需打回，请说明问题与修改要求"
            show-count
            @change="acceptanceError = ''"
          />
          <p v-if="acceptanceError" class="task-field-error">
            {{ acceptanceError }}
          </p>
        </div>

        <div class="task-completion-footer">
          <Button
            :disabled="acceptanceSubmitting"
            @click="acceptanceModalOpen = false"
          >
            取消
          </Button>
          <Button
            danger
            :loading="acceptanceSubmitting"
            @click="submitAcceptance('rejected')"
          >
            打回重新交付
          </Button>
          <Button
            :loading="acceptanceSubmitting"
            type="primary"
            @click="submitAcceptance('accepted')"
          >
            验收通过
          </Button>
        </div>
      </div>
    </Modal>

    <Modal
      v-model:open="completionModalOpen"
      :body-style="{
        maxHeight: '72dvh',
        overflowX: 'hidden',
        overflowY: 'auto',
      }"
      :closable="!completionSubmitting"
      :mask-closable="!completionSubmitting"
      title="提交任务交付"
      :width="720"
      wrap-class-name="task-completion-modal"
    >
      <div v-if="completionTask" class="task-completion-form">
        <div class="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2">
          <div class="text-sm font-medium text-blue-900">
            {{ completionTask.title }}
          </div>
          <div class="mt-1 text-xs text-blue-700">
            {{ completionTask.id }} · {{ kindMeta[completionTask.kind].label }}
          </div>
        </div>

        <template v-if="completionTask.kind === 'am'">
          <section
            class="task-delivery-mode"
            aria-labelledby="delivery-mode-title"
          >
            <div class="min-w-0">
              <h3
                id="delivery-mode-title"
                class="m-0 text-sm font-semibold text-slate-800"
              >
                交付数据填写方式
              </h3>
              <p class="mb-0 mt-1 text-xs leading-5 text-slate-500">
                选择投放中心数据可按负责明细和日期自动回填投放对象及花费；无法关联时可手动填写。
              </p>
            </div>
            <Segmented
              :value="completionForm.entryMode"
              :options="completionEntryModeOptions"
              @change="changeCompletionEntryMode"
            />
          </section>

          <section
            v-if="completionForm.entryMode === 'delivery-center'"
            class="task-delivery-source"
            aria-label="从投放中心选择交付数据"
          >
            <div
              class="flex min-w-0 items-start justify-between gap-3 rounded-lg bg-blue-50 px-3 py-2 text-xs leading-5 text-blue-700"
            >
              <div class="flex min-w-0 items-start gap-2">
                <IconifyIcon
                  class="mt-0.5 shrink-0 text-base"
                  icon="lucide:database-zap"
                />
                <span>
                  数据来源于投放中心最近一次同步，并自动回填到下方交付字段。
                </span>
              </div>
              <Button
                class="shrink-0"
                :loading="deliveryCampaignsLoading"
                @click="
                  completionTask &&
                  loadDeliveryCenterCampaigns(completionTask, true)
                "
              >
                重新同步
              </Button>
            </div>

            <div
              v-if="deliveryCampaignsError"
              class="task-source-error"
              role="alert"
            >
              <span>{{ deliveryCampaignsError }}</span>
              <Button @click="changeCompletionEntryMode('manual')">
                改为手动填写
              </Button>
            </div>
            <div class="task-completion-field mt-3">
              <label>数据日期范围</label>
              <DatePicker.RangePicker
                v-model:value="completionForm.sourceDateRange"
                class="w-full"
                :disabled-date="disableFutureDeliveryDate"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                @change="changeDeliverySourceDateRange"
              />
              <p
                v-if="deliverySourceRangeAdjustment"
                class="mb-0 mt-2 text-xs leading-5 text-amber-600"
              >
                计划开始日期
                {{ deliverySourceRangeAdjustment }}
                晚于今天，数据日期范围已暂按今天至今天查询。
              </p>
            </div>
          </section>

          <div class="contents">
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div class="task-completion-field sm:col-span-2">
                <label>投放平台 <span aria-hidden="true">*</span></label>
                <Select
                  v-model:value="completionForm.platforms"
                  :aria-invalid="Boolean(completionErrors.platforms)"
                  mode="multiple"
                  :options="completionPlatformOptions"
                  placeholder="选择一个或多个平台"
                  @change="clearCompletionError('platforms')"
                />
                <p v-if="completionErrors.platforms" class="task-field-error">
                  {{ completionErrors.platforms }}
                </p>
              </div>
              <div class="task-completion-field sm:col-span-2">
                <label>实际开始时间 <span aria-hidden="true">*</span></label>
                <DatePicker
                  v-model:value="completionForm.actualStartAt"
                  :aria-invalid="Boolean(completionErrors.actualStartAt)"
                  class="w-full"
                  format="YYYY-MM-DD HH:mm"
                  :show-time="{ format: 'HH:mm' }"
                  value-format="YYYY-MM-DD HH:mm"
                  @change="clearCompletionError('actualStartAt')"
                />
                <p
                  v-if="completionErrors.actualStartAt"
                  class="task-field-error"
                >
                  {{ completionErrors.actualStartAt }}
                </p>
              </div>
              <div class="task-completion-field sm:col-span-2">
                <label>Account ID <span aria-hidden="true">*</span></label>
                <Select
                  v-model:value="completionForm.accountIds"
                  :aria-invalid="Boolean(completionErrors.accountIds)"
                  mode="tags"
                  placeholder="输入 Account ID 后回车，至少 1 个"
                  :token-separators="[',', ' ', '\n']"
                  @change="clearCompletionError('accountIds')"
                />
                <p v-if="completionErrors.accountIds" class="task-field-error">
                  {{ completionErrors.accountIds }}
                </p>
              </div>
              <div class="task-completion-field sm:col-span-2">
                <label>Campaign ID <span aria-hidden="true">*</span></label>
                <Select
                  v-model:value="completionForm.campaignIds"
                  :aria-invalid="Boolean(completionErrors.campaignIds)"
                  mode="tags"
                  placeholder="输入 Campaign ID 后回车，至少 1 个"
                  :token-separators="[',', ' ', '\n']"
                  @change="clearCompletionError('campaignIds')"
                />
                <p v-if="completionErrors.campaignIds" class="task-field-error">
                  {{ completionErrors.campaignIds }}
                </p>
              </div>
              <div class="task-completion-field sm:col-span-2">
                <label>Ad Set ID</label>
                <Select
                  v-model:value="completionForm.sourceAdsetIds"
                  mode="tags"
                  placeholder="输入 Ad Set ID 后回车；没有则留空"
                  :token-separators="[',', ' ', '\n']"
                />
              </div>
              <div class="task-completion-field sm:col-span-2">
                <label>Ad ID</label>
                <Select
                  v-model:value="completionForm.sourceAdIds"
                  mode="tags"
                  placeholder="输入 Ad ID 后回车；没有则留空"
                  :token-separators="[',', ' ', '\n']"
                />
              </div>
            </div>

            <div class="grid grid-cols-1 gap-4 sm:grid-cols-4">
              <div class="task-completion-field">
                <label>Account 数量</label>
                <InputNumber
                  :value="completionForm.accountIds.length"
                  class="w-full"
                  disabled
                />
              </div>
              <div class="task-completion-field">
                <label>Campaign 数量</label>
                <InputNumber
                  :value="completionForm.campaignIds.length"
                  class="w-full"
                  disabled
                />
              </div>
              <div class="task-completion-field">
                <label>Ad Set 数量</label>
                <InputNumber
                  :value="completionForm.sourceAdsetIds.length"
                  class="w-full"
                  disabled
                />
              </div>
              <div class="task-completion-field">
                <label>Ad 数量</label>
                <InputNumber
                  :value="completionForm.sourceAdIds.length"
                  class="w-full"
                  disabled
                />
              </div>
            </div>

            <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div class="task-completion-field sm:col-span-2">
                <label>实际预算 <span aria-hidden="true">*</span></label>
                <InputNumber
                  v-model:value="completionForm.actualBudget"
                  :aria-invalid="Boolean(completionErrors.actualBudget)"
                  class="w-full"
                  :min="0"
                  :precision="2"
                  @change="clearCompletionError('actualBudget')"
                />
                <p
                  v-if="completionErrors.actualBudget"
                  class="task-field-error"
                >
                  {{ completionErrors.actualBudget }}
                </p>
              </div>
              <div class="task-completion-field">
                <label>币种 <span aria-hidden="true">*</span></label>
                <Select
                  v-model:value="completionForm.currency"
                  :aria-invalid="Boolean(completionErrors.currency)"
                  :options="currencyOptions"
                  @change="clearCompletionError('currency')"
                />
                <p v-if="completionErrors.currency" class="task-field-error">
                  {{ completionErrors.currency }}
                </p>
              </div>
            </div>

            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div class="task-completion-field">
                <label>
                  实际消耗（USD） <span aria-hidden="true">*</span>
                </label>
                <InputNumber
                  v-model:value="completionForm.actualSpend"
                  :aria-invalid="Boolean(completionErrors.actualSpend)"
                  class="w-full"
                  :disabled="completionForm.entryMode !== 'manual'"
                  :min="0"
                  :precision="2"
                  @change="clearCompletionError('actualSpend')"
                />
                <p v-if="completionErrors.actualSpend" class="task-field-error">
                  {{ completionErrors.actualSpend }}
                </p>
              </div>
              <div class="task-completion-field">
                <label>
                  日报花费（USD） <span aria-hidden="true">*</span>
                </label>
                <InputNumber
                  v-model:value="completionForm.dailyReportSpend"
                  :aria-invalid="Boolean(completionErrors.dailyReportSpend)"
                  class="w-full"
                  :disabled="completionForm.entryMode !== 'manual'"
                  :min="0"
                  :precision="2"
                  @change="clearCompletionError('dailyReportSpend')"
                />
                <p
                  v-if="completionErrors.dailyReportSpend"
                  class="task-field-error"
                >
                  {{ completionErrors.dailyReportSpend }}
                </p>
              </div>
            </div>

            <div class="task-completion-field">
              <label>实际投放状态 <span aria-hidden="true">*</span></label>
              <Select
                v-model:value="completionForm.deliveryStatus"
                :aria-invalid="Boolean(completionErrors.deliveryStatus)"
                :options="deliveryStatusOptions"
                placeholder="选择状态"
                @change="clearCompletionError('deliveryStatus')"
              />
              <p
                v-if="completionErrors.deliveryStatus"
                class="task-field-error"
              >
                {{ completionErrors.deliveryStatus }}
              </p>
            </div>
          </div>

          <div
            v-if="completionForm.deliveryStatus === 'partial'"
            class="task-completion-field"
          >
            <label for="completion-exception-note">
              异常说明 <span aria-hidden="true">*</span>
            </label>
            <Input.TextArea
              id="completion-exception-note"
              v-model:value="completionForm.exceptionNote"
              :aria-invalid="Boolean(completionErrors.exceptionNote)"
              :auto-size="{ minRows: 3, maxRows: 6 }"
              placeholder="说明未成功部分、原因与后续处理"
              @change="clearCompletionError('exceptionNote')"
            />
            <p v-if="completionErrors.exceptionNote" class="task-field-error">
              {{ completionErrors.exceptionNote }}
            </p>
          </div>

          <div class="task-completion-field">
            <label for="am-completion-note">
              交付备注
              <span
                v-if="completionForm.entryMode === 'manual'"
                aria-hidden="true"
              >
                *
              </span>
            </label>
            <Input.TextArea
              id="am-completion-note"
              v-model:value="completionForm.note"
              :aria-invalid="Boolean(completionErrors.note)"
              :auto-size="{ minRows: 2, maxRows: 5 }"
              :maxlength="500"
              placeholder="可选：补充投放说明与数据口径"
              show-count
            />
            <p v-if="completionErrors.note" class="task-field-error">
              {{ completionErrors.note }}
            </p>
          </div>
        </template>

        <template v-else>
          <div class="task-completion-field">
            <label for="media-completion-note">
              处理结果备注 <span aria-hidden="true">*</span>
            </label>
            <Input.TextArea
              id="media-completion-note"
              v-model:value="completionForm.note"
              :aria-invalid="Boolean(completionErrors.note)"
              :auto-size="{ minRows: 4, maxRows: 8 }"
              :maxlength="800"
              placeholder="说明审批、出库、替换或异常处理结果"
              show-count
              @change="clearCompletionError('note')"
            />
            <p v-if="completionErrors.note" class="task-field-error">
              {{ completionErrors.note }}
            </p>
          </div>
        </template>

        <div
          v-if="completionTask.kind !== 'material'"
          class="task-completion-field"
        >
          <label>
            {{
              completionTask.kind === 'am'
                ? '成功证明 / 数据文件（可选）'
                : '处理附件（可选）'
            }}
          </label>
          <Upload.Dragger
            :accept="completionAccept"
            :before-upload="beforeCompletionUpload"
            class="task-completion-upload"
            :multiple="true"
            :show-upload-list="false"
          >
            <div class="py-4">
              <IconifyIcon
                class="text-primary mx-auto text-2xl"
                icon="lucide:cloud-upload"
              />
              <p class="mb-1 mt-2 text-sm font-medium text-slate-700">
                点击或拖拽文件到此处
              </p>
              <p class="m-0 text-xs text-slate-400">
                {{
                  completionTask.kind === 'am' &&
                  completionForm.entryMode === 'delivery-center'
                    ? '系统已保存投放中心数据快照，附件为可选补充证明'
                    : '单个文件不超过 10 MB，提交前可随时移除'
                }}
              </p>
            </div>
          </Upload.Dragger>
          <div
            v-if="completionFiles.length > 0"
            aria-live="polite"
            class="task-completion-selected-files task-file-list mt-2"
          >
            <div
              v-for="file in completionFiles"
              :key="file.uid"
              class="task-file-row"
            >
              <IconifyIcon
                aria-hidden="true"
                class="shrink-0 text-blue-500"
                icon="lucide:file-check-2"
              />
              <span class="min-w-0 flex-1 truncate" :title="file.name">
                {{ file.name }}
              </span>
              <span class="shrink-0">
                {{ formatCompletionFileSize(Number(file.size) || 0) }}
              </span>
              <Button
                :aria-label="`移除文件 ${file.name}`"
                danger
                type="link"
                @click="removeCompletionFile(file)"
              >
                移除
              </Button>
            </div>
          </div>
          <p v-if="completionErrors.files" class="task-field-error">
            {{ completionErrors.files }}
          </p>
        </div>
      </div>
      <template #footer>
        <Button
          :disabled="completionSubmitting"
          @click="completionModalOpen = false"
        >
          取消
        </Button>
        <Button
          :loading="completionSubmitting"
          type="primary"
          @click="submitCompletion"
        >
          提交交付，等待验收
        </Button>
      </template>
    </Modal>

    <Modal
      v-model:open="materialTaskModalOpen"
      :closable="!materialDeliverySubmitting"
      :footer="null"
      title="提交素材交付"
      width="640px"
    >
      <div class="space-y-4 pt-2">
        <div class="task-completion-field">
          <label>本次交付数量 <span aria-hidden="true">*</span></label>
          <InputNumber
            v-model:value="materialTaskQuantity"
            class="w-full"
            :min="1"
            :precision="0"
          />
        </div>
        <div class="task-completion-field">
          <label>素材文件 <span aria-hidden="true">*</span></label>
          <Upload.Dragger
            :before-upload="beforeMaterialTaskUpload"
            :file-list="materialTaskFiles"
            multiple
            @remove="removeMaterialTaskFile"
          >
            <div class="py-4">
              <IconifyIcon
                class="text-primary mx-auto text-2xl"
                icon="lucide:cloud-upload"
              />
              <p class="mb-1 mt-2 text-sm font-medium text-slate-700">
                点击或拖拽素材文件到此处
              </p>
              <p class="m-0 text-xs text-slate-400">
                文件数量需要与本次交付数量一致
              </p>
            </div>
          </Upload.Dragger>
        </div>
        <div class="task-completion-field">
          <label for="material-task-note">交付备注</label>
          <Input.TextArea
            id="material-task-note"
            v-model:value="materialTaskNote"
            :auto-size="{ minRows: 3, maxRows: 6 }"
            :maxlength="500"
            show-count
          />
        </div>
        <div class="flex justify-end gap-3">
          <Button
            :disabled="materialDeliverySubmitting"
            @click="materialTaskModalOpen = false"
          >
            取消
          </Button>
          <Button
            :loading="materialDeliverySubmitting"
            type="primary"
            @click="submitMaterialTaskDelivery"
          >
            提交交付，等待验收
          </Button>
        </div>
      </div>
    </Modal>

    <UploadMaterialModal
      ref="materialDeliveryModalRef"
      :creative-planner-options="
        materialDeliveryTask?.materialUpload?.creativePlanners
      "
      :default-creative-planner="
        materialDeliveryTask?.materialUpload?.creativePlanners?.[0]
      "
      :default-designer="currentMaterialDesignerName"
      :open="materialDeliveryModalOpen"
      :demand-type="materialDeliveryContext?.demandType ?? ''"
      :order-id="materialDeliveryContext?.orderId"
      :designer-options="materialDeliveryTask?.materialUpload?.designers"
      :description-options="materialDeliveryContext?.assignmentOptions"
      assignment-mode
      :persist-key="materialDeliveryPersistKey"
      :show-designer="true"
      title="提交素材订单交付"
      @all-done="submitMaterialDelivery"
      @update:open="materialDeliveryModalOpen = $event"
    />
    <RequirementTemplateModal
      v-if="canManageRequirementTemplates"
      v-model:open="requirementTemplateManagerOpen"
      mode="manage"
      :can-manage="canManageRequirementTemplates"
    />
  </Page>
</template>

<style scoped>
.task-page {
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  overflow: hidden;
}

.task-shell {
  display: grid;
  min-height: 0;
  flex: 1;
  grid-template-columns: 220px minmax(0, 1fr);
}

.material-task-main {
  overflow-y: auto;
  overscroll-behavior: contain;
}

.task-inner-sidebar {
  min-width: 0;
  min-height: 0;
  padding: 12px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  border-right: 1px solid rgb(226 232 240);
  background: #fff;
}

.task-sidebar-heading {
  display: flex;
  min-height: 44px;
  align-items: center;
  padding: 0 8px 10px;
}

.task-sidebar-icon,
.task-activity-icon {
  display: inline-flex;
  width: 36px;
  height: 36px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: hsl(var(--primary));
  background: hsl(var(--muted));
}

.task-primary-nav,
.task-quick-list {
  display: grid;
  gap: 4px;
}

.task-nav-button {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  min-height: 44px;
  width: 100%;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  color: rgb(71 85 105);
  background: transparent;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition:
    color 0.15s ease,
    background-color 0.15s ease;
}

.task-nav-button:hover {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 6%);
}

.task-nav-button:focus-visible,
.task-title-button:focus-visible,
.task-priority-item:focus-visible {
  outline: 2px solid hsl(var(--primary));
  outline-offset: 2px;
}

.task-nav-button.is-active {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  font-weight: 600;
}

.task-board-count {
  display: inline-flex;
  min-width: 24px;
  height: 22px;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  border-radius: 999px;
  color: rgb(100 116 139);
  background: rgb(241 245 249);
  font-size: 12px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.task-sidebar-divider {
  height: 1px;
  margin: 12px 6px;
  background: rgb(226 232 240);
}

.task-sidebar-label {
  padding: 2px 10px 8px;
  color: rgb(148 163 184);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.task-page-header,
.task-view-toolbar {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.task-filter-toolbar {
  display: grid;
  min-width: 0;
  width: 100%;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 140px), 1fr));
  gap: 8px;
  margin-top: 12px;
}

.task-search-input,
.task-filter-select {
  min-width: 0;
  width: 100%;
}

.task-search-input {
  grid-column: span 2;
}

.task-filter-toolbar > * {
  min-width: 0;
  max-width: 100%;
}

/* 投放筛选沿用全局控件高度，搜索组合框不再按 table-cell 的基线定位按钮。 */
.task-delivery-filter-toolbar {
  align-items: center;
}

.task-follow-button {
  display: inline-flex;
  width: 44px;
  min-width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  margin: -8px 0 -8px -8px;
}

.task-list-section {
  /*
   * Page 会计算并提供工作台可用高度。列表直接填满筛选栏以下的剩余空间，
   * 避免使用依赖顶栏和标签页高度的固定视口扣减值。
  */
  min-width: 0;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/*
 * 看板、仪表盘与投放列表共用剩余高度内的滚动区域，避免内容被外层截断。
 * 投放分页保持在滚动区域之外。
 */
.task-results-scroll {
  flex: 1;
  min-width: 0;
  min-height: 0;
  margin-top: 12px;
  overflow: auto;
}

.task-results-scroll > .task-list-section {
  height: 100%;
  margin-top: 0;
}

.task-results-scroll .task-list-scroll {
  overflow-y: auto;
}

.material-task-results-flow {
  flex: none;
  min-width: 0;
  min-height: 0;
  margin-top: 12px;
  overflow: visible;
}

.material-task-results-flow > .task-list-section {
  height: auto;
  min-height: 0;
  margin-top: 0;
}

.material-task-results-flow .task-list-scroll {
  flex: none;
  overflow: visible;
}

.task-delivery-pagination {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
}

.task-activity-scroll,
.task-list-scroll {
  min-height: 0;
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

/*
 * 列表滚动由 task-list-scroll 承担。卡片和 Ant Table 的默认 overflow
 * 会截断 sticky 定位上下文，因此在桌面列表中释放它们，让表头始终锚定
 * 到这个滚动区域；移动端继续使用卡片列表。
 */
.task-list-card {
  overflow: visible !important;
}

.task-summary-footer {
  display: flex;
  min-height: 46px;
  align-items: center;
  justify-content: space-between;
  gap: 12px 20px;
  padding: 8px 16px;
  border: 1px solid rgb(147 197 253);
  border-radius: 8px;
  background: rgb(239 246 255);
}

.task-summary-title {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
  color: rgb(30 64 175);
  font-weight: 600;
}

.task-summary-metrics {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px 20px;
  color: rgb(51 65 85);
  font-size: 12px;
}

.task-desktop-table {
  display: block;
  min-width: 0;
  width: 100%;
}

.task-mobile-list {
  display: none;
}

.task-row-actions {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 4px;
}

.task-action-button {
  height: 32px;
  padding-inline: 0;
  white-space: nowrap;
}

.task-kind-pill {
  display: inline-flex;
  flex: none;
  align-items: center;
  padding: 1px 5px;
  border-radius: 4px;
  color: rgb(79 70 229);
  background: rgb(238 242 255);
  font-size: 11px;
  line-height: 18px;
}

.task-title-button {
  display: block;
  max-width: 100%;
  padding: 0;
  border: 0;
  color: rgb(30 41 59);
  background: transparent;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.task-title-button:hover {
  color: rgb(37 99 235);
}

.task-board {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.task-board-column {
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgb(226 232 240);
  border-radius: 12px;
  background: rgb(248 250 252);
}

.task-board-header {
  display: flex;
  min-height: 48px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 14px;
  border-bottom: 1px solid rgb(226 232 240);
  background: #fff;
}

.task-board-card {
  min-width: 0;
  padding: 12px;
  border: 1px solid rgb(226 232 240);
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 1px 2px rgb(15 23 42 / 4%);
}

.task-card-actions,
.task-mobile-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgb(241 245 249);
}

.task-card-actions > *,
.task-mobile-actions > * {
  min-width: 0;
}

.task-progress-detail {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgb(248 250 252);
}

.task-progress-detail dt {
  color: rgb(100 116 139);
  font-size: 12px;
}

.task-progress-detail dd {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
  color: rgb(30 41 59);
  font-size: 14px;
  font-weight: 500;
}

.task-detail-content,
.task-completion-form {
  min-width: 0;
}

.task-detail-content {
  display: grid;
  gap: 16px;
}

.task-detail-section {
  min-width: 0;
  padding: 16px;
  border: 1px solid rgb(226 232 240);
  border-radius: 12px;
  background: #fff;
}

.task-detail-section-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  color: rgb(30 41 59);
  font-size: 14px;
  font-weight: 600;
}

.task-detail-grid {
  display: grid;
  min-width: 0;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
  margin-bottom: 0;
}

.task-detail-grid > div {
  min-width: 0;
}

.task-detail-grid dt {
  color: rgb(100 116 139);
  font-size: 12px;
}

.task-detail-grid dd {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
  color: rgb(30 41 59);
  font-size: 13px;
  line-height: 20px;
}

.task-file-list {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.task-file-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  color: rgb(71 85 105);
  background: rgb(248 250 252);
  font-size: 12px;
}

.task-acceptance-record,
.task-delivery-record {
  min-width: 0;
  padding: 14px;
  border: 1px solid rgb(226 232 240);
  border-radius: 10px;
  background: rgb(248 250 252 / 55%);
}

.task-detail-footer,
.task-completion-footer {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.task-detail-footer {
  position: sticky;
  z-index: 1;
  bottom: -24px;
  margin: 0 -24px -24px;
  padding: 12px 24px;
  border-top: 1px solid rgb(226 232 240);
  background: rgb(255 255 255 / 96%);
  backdrop-filter: blur(8px);
}

.task-completion-form {
  display: grid;
  gap: 16px;
}

.task-delivery-mode {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px;
  border: 1px solid rgb(226 232 240);
  border-radius: 10px;
  background: rgb(248 250 252);
}

.task-delivery-source {
  display: grid;
  min-width: 0;
  gap: 14px;
  padding: 14px;
  border: 1px solid rgb(191 219 254);
  border-radius: 10px;
  background: rgb(248 250 252 / 65%);
}

.task-source-error {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid rgb(254 202 202);
  border-radius: 8px;
  color: rgb(185 28 28);
  background: rgb(254 242 242);
  font-size: 12px;
}

.task-source-snapshot {
  display: grid;
  min-width: 0;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.task-source-snapshot > div {
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 3px;
  padding: 10px;
  border: 1px solid rgb(226 232 240);
  border-radius: 8px;
  background: #fff;
}

.task-source-snapshot span,
.task-source-snapshot small {
  overflow-wrap: anywhere;
  color: rgb(100 116 139);
  font-size: 11px;
  line-height: 17px;
}

.task-source-snapshot strong {
  overflow-wrap: anywhere;
  color: rgb(30 41 59);
  font-size: 13px;
  font-weight: 600;
  line-height: 19px;
}

.task-completion-field {
  min-width: 0;
}

.task-completion-field > label {
  display: block;
  margin-bottom: 6px;
  color: rgb(51 65 85);
  font-size: 13px;
  font-weight: 500;
}

.task-completion-field > label span {
  color: rgb(239 68 68);
}

.task-completion-selected-files {
  max-height: 144px;
  padding-right: 2px;
  overflow-y: auto;
}

.task-field-error {
  margin: 5px 0 0;
  color: rgb(220 38 38);
  font-size: 12px;
  line-height: 18px;
}

.task-completion-footer {
  position: static;
  margin: 0;
  padding: 12px 0 0;
  border-top: 1px solid rgb(226 232 240);
  background: #fff;
}

@media (max-width: 767px) {
  .task-delivery-mode {
    align-items: stretch;
    flex-direction: column;
  }

  .task-source-error {
    align-items: stretch;
    flex-direction: column;
  }

  .task-source-snapshot {
    grid-template-columns: 1fr;
  }
}

.task-priority-item {
  display: flex;
  min-height: 56px;
  width: 100%;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border: 1px solid rgb(226 232 240);
  border-radius: 9px;
  background: #fff;
  cursor: pointer;
}

.task-priority-item:hover {
  border-color: rgb(147 197 253);
  background: rgb(248 250 252);
}

@media (max-width: 1535px) {
  .task-board {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 1279px) {
  .task-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .task-inner-sidebar {
    border-right: 0;
    border-bottom: 1px solid rgb(226 232 240);
  }

  .task-sidebar-heading,
  .task-sidebar-divider,
  .task-sidebar-label {
    display: none;
  }

  .task-primary-nav {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .task-quick-access {
    margin-top: 8px;
  }

  .task-quick-list {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .task-quick-list .task-nav-button {
    width: 100%;
  }
}

@media (max-width: 767px) {
  .task-page {
    padding: 8px;
  }

  .task-page-header {
    align-items: flex-start;
  }

  .task-view-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .task-filter-toolbar {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .task-filter-toolbar > * {
    grid-column: auto !important;
    grid-row: auto !important;
  }

  .task-search-input {
    grid-column: 1 / -1 !important;
  }

  .task-board {
    grid-template-columns: minmax(0, 1fr);
  }

  .task-list-section {
    height: auto;
    min-height: 0;
  }

  .task-list-scroll {
    min-height: 0;
    overflow: visible;
  }

  .task-summary-footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .task-summary-metrics {
    justify-content: flex-start;
  }

  .task-desktop-table {
    display: none;
  }

  .task-mobile-list {
    display: grid;
  }

  .task-mobile-card {
    min-width: 0;
    padding: 16px 14px;
    border-bottom: 1px solid rgb(226 232 240);
  }

  .task-mobile-card:last-child {
    border-bottom: 0;
  }
}

@media (max-width: 479px) {
  .task-primary-nav {
    grid-template-columns: minmax(0, 1fr);
  }

  .task-quick-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .task-filter-toolbar {
    grid-template-columns: minmax(0, 1fr);
  }

  .task-search-input {
    grid-column: auto !important;
  }

  .task-view-switch {
    width: 100%;
  }

  .task-detail-section {
    padding: 12px;
  }

  .task-detail-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .task-detail-grid :deep(.sm\:col-span-2) {
    grid-column: auto;
  }

  .task-detail-footer {
    bottom: -24px;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }

  .task-detail-footer > *,
  .task-completion-footer > * {
    width: 100%;
  }

  .task-completion-footer {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
