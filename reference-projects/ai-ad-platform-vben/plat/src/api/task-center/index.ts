import type { DeliveryTaskItem } from '#/domain/task/delivery-items';
import { adpulseClient, backendClient, mainBackendClient } from '#/api/request';

export type TaskType = 'DELIVERY' | 'MATERIAL';
export type TaskStatus =
  | 'COMPLETED'
  | 'PENDING_ASSIGNMENT'
  | 'PENDING_ACCEPTANCE'
  | 'PENDING_CONFIRMATION'
  | 'PROCESSING'
  | 'REJECTED'
  | 'WITHDRAWN';

export interface TaskFileBindingInput {
  fileId: string;
  sortOrder: number;
  usageType: 'ATTACHMENT' | 'DATA' | 'MATERIAL' | 'PROOF' | 'REFERENCE';
}

export interface TaskSummary {
  /** 任务关联 AM 的姓名，多个姓名以顿号分隔。 */
  amNames?: string;
  acceptedAt?: string;
  assignedAt?: string;
  assignerId?: string;
  assignerName?: string;
  completedAt?: string;
  createdAt: string;
  creatorId: string;
  creatorName: string;
  description: string;
  /** 当前用户是否有尚未交付的投放执行项。 */
  deliveryOperator?: boolean;
  dueAt?: null | string;
  followed: boolean;
  id: string;
  ownerId?: string;
  ownerName?: string;
  priority: 'P0' | 'P1' | 'P2' | 'P3';
  projectId: string;
  /** ERP pm_project.project_name，由任务中心聚合接口返回。 */
  projectName?: string;
  status: TaskStatus;
  taskCode: string;
  taskType: TaskType;
  title: string;
  updatedAt: string;
  version: number;
  rejectedAt?: string;
  rejectedBy?: string;
  rejectionReason?: string;
  withdrawnAt?: string;
  withdrawReason?: string;
  /** 素材任务关联工单的需求与实际上传数量；投放任务为 null。 */
  materialUpload?: {
    acceptedQuantity: number;
    assignedAt?: string;
    completedDesigners?: string[];
    creativePlanners?: string[];
    designers?: string[];
    /** 当前 API 会话是否属于该工单被分配的素材师。 */
    viewerIsDesigner?: boolean;
    /** 当前 API 会话是否已完成自己负责的素材制作。 */
    viewerCompletedDesigner?: boolean;
    lastUploadedAt: null | string;
    orderId: string;
    orderIds?: string[];
    orderNo?: string;
    orderStatus?: string;
    pendingReviewQuantity: number;
    progress: number;
    rejectedQuantity: number;
    remainingQuantity: null | number;
    requiredQuantity: null | number;
    uploadedQuantity: number;
  } | null;
}

export interface TaskFileView {
  extension: string;
  fileSize: number;
  id: string;
  mimeType: string;
  originalName: string;
  sortOrder: number;
  targetId: string;
  targetType: string;
  usageType: string;
}

export interface TaskSubmissionBase {
  id: string;
  requestId: string;
  reviewComment?: string;
  reviewedAt?: string;
  reviewerId?: string;
  reviewerName?: string;
  reviewStatus: 'ACCEPTED' | 'PENDING' | 'REJECTED';
  submissionNote?: string;
  submittedAt: string;
  submittedBy: string;
  submittedByName: string;
  versionNo: number;
}

export interface DeliverySubmission extends TaskSubmissionBase {
  allocationId?: string;
  accountCount: number;
  actualBudget: number;
  actualSpend: number;
  actualStartAt: string;
  adAccountId: string;
  adAccountIds: string[];
  adAccountName?: string;
  adCount: number;
  adsetCount: number;
  campaignCount: number;
  currency: string;
  dailyReportSpend: number;
  deliveryStatus: 'ACTIVE' | 'FAILED' | 'PARTIAL' | 'PAUSED';
  exceptionNote?: string;
  objects: Array<{
    objectId: string;
    objectName?: string;
    objectType: 'ACCOUNT' | 'AD' | 'AD_SET' | 'CAMPAIGN';
    sortOrder: number;
  }>;
  platform: string;
  platforms: string[];
}

export interface DeliveryTaskSource {
  accountIds: string[];
  actualSpend: number;
  adIds: string[];
  adsetIds: string[];
  campaignIds: string[];
  dailyReportSpend: number;
  endDate: string;
  platforms: string[];
  startDate: string;
}

export interface MaterialSubmission extends TaskSubmissionBase {
  deliveredQuantity: number;
  libraryStatus: 'FAILED' | 'IMPORTED' | 'NOT_REQUIRED' | 'PENDING';
}

export interface TaskDetail {
  allocations: Array<{
    completedAt?: string;
    h5LineCount: number;
    id: string;
    pwaLineCount: number;
    sortOrder: number;
    status?: 'ASSIGNED' | 'COMPLETED' | 'SUBMITTED';
    submittedAt?: string;
    teamCode: string;
    teamName?: string;
    teamOwnerId: string;
    teamOwnerName: string;
  }>;
  delivery?: {
    items?: DeliveryTaskItem[];
    amUsers?: Array<{ userId: string; userName: string }>;
    amUserId?: string;
    amUserName?: string;
    plannedStartAt: string;
    productUrl: string;
    region: string;
    target: string;
  };
  deliverySubmissions: DeliverySubmission[];
  material?: {
    addToLibrary: boolean;
    countryTags: string[];
    demandType: string;
    departmentId?: string;
    departmentName?: string;
    gameplayTags: string[];
    greenMaterial: boolean;
    languageCode: string;
    productSubName?: string;
    quantity: number;
    themeTags: string[];
  };
  materialSubmissions: MaterialSubmission[];
  materialRequirements: Array<{
    compliance?: string;
    description: string;
    duration?: string;
    id: string;
    link?: string;
    quantity: number;
    remark?: string;
    sortOrder: number;
  }>;
  platforms: string[];
  referenceLinks: Array<{ name: string; sortOrder: number; url: string }>;
  sizes: string[];
  task: TaskSummary;
  taskFiles: TaskFileView[];
}

export interface TaskCenterSummary {
  dueSoonCount: number;
  inProgressCount: number;
  material: {
    orderCount: number;
    requiredQuantity: number;
    syncedTaskCount: number;
    taskCount: number;
    uploadedQuantity: number;
  };
  overdueCount: number;
  pendingAcceptanceCount: number;
  riskCount: number;
  totalCount: number;
}

export interface TaskPage {
  items: TaskSummary[];
  page: number;
  pageSize: number;
  summary?: TaskCenterSummary;
  /** 仅 includeSummary=true 时返回，普通翻页不做全量 COUNT。 */
  total?: number;
}

export interface TaskDraft<T = Record<string, unknown>> {
  createdAt: string;
  creatorId: string;
  creatorName: string;
  draftCode: string;
  id: string;
  payload: T;
  projectId?: string;
  taskType: TaskType;
  title?: string;
  updatedAt: string;
}

export interface TaskDraftSaveInput<T = Record<string, unknown>> {
  payload: T;
  projectId?: string;
  taskType: TaskType;
  title?: string;
}

export interface TaskActivityRecord {
  actorId: string;
  actorName: string;
  description: string;
  eventType:
    | 'ACCEPTED'
    | 'ALLOCATION_ACCEPTED'
    | 'ALLOCATION_REJECTED'
    | 'ASSIGNED'
    | 'CONFIRMED'
    | 'CREATED'
    | 'DECLINED'
    | 'DELIVERY_SUBMITTED'
    | 'REJECTED'
    | 'RESUBMITTED'
    | 'WITHDRAWN';
  id: string;
  occurredAt: string;
  projectId: string;
  state: string;
  taskId: string;
  taskTitle: string;
  taskType: TaskType;
}

export interface TaskNavigationCounts {
  acceptance: number;
  activities: number;
  all: number;
  assigned: number;
  completed: number;
  created: number;
  drafts: number;
  followed: number;
  owned: number;
  submission: number;
  failed: number;
}

export interface DeliveryTaskCreateInput {
  items: DeliveryTaskItem[];
  draftId?: string;
  files: TaskFileBindingInput[];
  plannedStartAt: string;
  platforms: string[];
  productUrl: string;
  region: string;
  target: string;
  task: {
    description: string;
    dueAt?: string;
    ownerId?: string;
    priority: 'P0' | 'P1' | 'P2' | 'P3';
    projectId: string;
    title: string;
  };
}

export interface DeliveryAllocationAssignInput {
  allocations: Array<{
    h5LineCount: number;
    pwaLineCount: number;
    teamCode: string;
    teamOwnerId: string;
  }>;
}

export interface UploadedTaskFile {
  id: string;
  mimeType: string;
  originalName: string;
}

/** 按当前用户获准的数据范围查询任务。 */
export function listTasksApi(
  params: {
    /** 首屏需要页脚汇总时传 true；后续翻页请省略。 */
    includeSummary?: boolean;
    keyword?: string;
    page?: number;
    pageSize?: number;
    status?: TaskStatus;
    scope?:
      | 'ASSIGNED'
      | 'CREATED'
      | 'FOLLOWED'
      | 'OWNER'
      | 'LEADER'
      | 'PENDING_ASSIGNMENT'
      | 'RELATED'
      | 'ALL';
    taskType?: TaskType;
  } = {},
) {
  // 任务中心聚合列表由广告数据服务读取 ERP biz_task，并补齐 Mongo 素材工单上传量。
  // 其他任务详情/写操作仍由主业务服务负责。
  return adpulseClient.get<TaskPage>('task-center/tasks', { params });
}

/**
 * 投放任务由主业务后端维护；素材任务继续使用原广告数据服务，避免两类任务互相混入。
 */
export function listDeliveryTasksApi(
  params: Omit<
    NonNullable<Parameters<typeof listTasksApi>[0]>,
    'includeSummary' | 'status' | 'taskType'
  > & { status?: TaskStatus | 'FAILED' } = {},
) {
  return mainBackendClient.get<TaskPage>('/tasks', {
    params: { ...params, taskType: 'DELIVERY' },
  });
}

export function getTaskNavigationCountsApi() {
  return mainBackendClient.get<TaskNavigationCounts>(
    '/tasks/navigation-counts',
  );
}

/** 查询任务的类型化详情、文件和交付版本。 */
export function getTaskApi(taskId: string) {
  return mainBackendClient.get<TaskDetail>(`/tasks/${taskId}`);
}

export function listTaskDraftsApi() {
  return mainBackendClient.get<TaskDraft[]>('/tasks/drafts');
}

export function listTaskActivitiesApi(limit = 50) {
  return mainBackendClient.get<TaskActivityRecord[]>('/tasks/activities', {
    params: { limit },
  });
}

export function getTaskDraftApi<T = Record<string, unknown>>(draftId: string) {
  return mainBackendClient.get<TaskDraft<T>>(`/tasks/drafts/${draftId}`);
}

export function createTaskDraftApi<T = Record<string, unknown>>(
  payload: TaskDraftSaveInput<T>,
) {
  return mainBackendClient.post<TaskDraft<T>>('/tasks/drafts', payload);
}

export function updateTaskDraftApi<T = Record<string, unknown>>(
  draftId: string,
  payload: TaskDraftSaveInput<T>,
) {
  return mainBackendClient.put<TaskDraft<T>>(
    `/tasks/drafts/${draftId}`,
    payload,
  );
}

export function deleteTaskDraftApi(draftId: string) {
  return mainBackendClient.delete<void>(`/tasks/drafts/${draftId}`);
}

export function listFollowedTaskIdsApi() {
  return mainBackendClient.get<string[]>('/tasks/follows');
}

export function followTaskApi(taskId: string) {
  return mainBackendClient.post<void>(`/tasks/${taskId}/follow`);
}

export function unfollowTaskApi(taskId: string) {
  return mainBackendClient.delete<void>(`/tasks/${taskId}/follow`);
}

export function createDeliveryTaskApi(payload: DeliveryTaskCreateInput) {
  return mainBackendClient.post<TaskDetail>('/tasks/delivery', payload);
}

export function assignDeliveryAllocationsApi(
  taskId: string,
  payload: DeliveryAllocationAssignInput,
) {
  return mainBackendClient.post<TaskDetail>(
    `/tasks/${taskId}/delivery-allocations`,
    payload,
  );
}

export function confirmTaskApi(taskId: string) {
  return mainBackendClient.post<TaskDetail>(`/tasks/${taskId}/confirm`);
}

export function declineTaskApi(taskId: string, reason: string) {
  return mainBackendClient.post<TaskDetail>(`/tasks/${taskId}/decline`, {
    reason,
  });
}

export function assignTaskApi(taskId: string, ownerId: string) {
  return mainBackendClient.post<TaskDetail>(`/tasks/${taskId}/assign`, {
    ownerId,
  });
}

export function submitDeliveryTaskApi(
  taskId: string,
  payload: {
    actualBudget: number;
    actualSpend: number;
    actualStartAt: string;
    accountIds: string[];
    adAccountName?: string;
    adCount: number;
    adsetCount: number;
    campaignCount: number;
    currency: string;
    dailyReportSpend: number;
    deliveryStatus: 'ACTIVE' | 'FAILED' | 'PARTIAL' | 'PAUSED';
    exceptionNote?: string;
    files: TaskFileBindingInput[];
    note?: string;
    objects: Array<{
      objectId: string;
      objectName?: string;
      objectType: 'AD' | 'AD_SET' | 'CAMPAIGN';
    }>;
    platforms: string[];
    requestId: string;
  },
) {
  return mainBackendClient.post<TaskDetail>(
    `/tasks/${taskId}/delivery-submissions`,
    payload,
  );
}

export function getDeliveryTaskSourceApi(
  taskId: string,
  params?: { endDate?: string; startDate?: string },
) {
  return mainBackendClient.get<DeliveryTaskSource>(
    `/tasks/${taskId}/delivery-source`,
    { params },
  );
}

export function submitMaterialTaskApi(
  taskId: string,
  payload: {
    deliveredQuantity: number;
    files: TaskFileBindingInput[];
    note?: string;
    requestId: string;
  },
) {
  return mainBackendClient.post<TaskDetail>(
    `/tasks/${taskId}/material-submissions`,
    payload,
  );
}

export function withdrawTaskApi(taskId: string, reason: string) {
  return mainBackendClient.post<TaskDetail>(`/tasks/${taskId}/withdraw`, {
    reason,
  });
}

export function resubmitTaskApi(taskId: string) {
  return mainBackendClient.post<TaskDetail>(`/tasks/${taskId}/resubmit`);
}

export function resubmitDeliveryTaskApi(
  taskId: string,
  payload: DeliveryTaskCreateInput,
) {
  return mainBackendClient.put<TaskDetail>(
    `/tasks/${taskId}/delivery/resubmit`,
    payload,
  );
}

export function reviewTaskSubmissionApi(
  taskId: string,
  taskType: TaskType,
  submissionId: string,
  decision: 'accept' | 'reject',
  comment: string,
) {
  const type = taskType === 'DELIVERY' ? 'delivery' : 'material';
  return mainBackendClient.post<TaskDetail>(
    `/tasks/${taskId}/${type}-submissions/${submissionId}/${decision}`,
    { comment },
  );
}

async function sha256(file: File) {
  const buffer = await file.arrayBuffer();
  let digest: Uint8Array;
  if (globalThis.crypto?.subtle) {
    digest = new Uint8Array(
      await globalThis.crypto.subtle.digest('SHA-256', buffer),
    );
  } else {
    // 测试环境使用 HTTP，Web Crypto 在非安全上下文不可用，需使用同等 SHA-256 实现。
    const { sha256: sha256Fallback } = await import('@noble/hashes/sha2.js');
    digest = sha256Fallback(new Uint8Array(buffer));
  }
  return [...digest]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
}

/** 上传任务文件并返回可写入 biz_task_file_binding 的稳定 sys_file.id。 */
export async function uploadTaskFileApi(file: File) {
  const data = new FormData();
  data.append('file', file);
  return backendClient.post<UploadedTaskFile>('/files/upload', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: { contentHash: await sha256(file) },
  });
}

/** 新建投放任务使用的代理线主数据；选择后复制为任务快照。 */
export interface DeliveryAgencyLineOption {
  cloakUrl: string;
  deliveryUrl: string;
  id: string;
  name: string;
  optimizerId: string;
  optimizerName: string;
  pixelId: string;
  pixelName: string;
  testCode: string;
  token: string;
  type: string;
}

export function searchDeliveryAgencyLinesApi(keyword: string, page = 1) {
  return mainBackendClient.get<DeliveryAgencyLineOption[]>(
    '/tasks/delivery-agency-lines',
    { params: { keyword, page } },
  );
}

/** 导入仅查询文件涉及的代理线名称，不拉取完整代理线目录。 */
export function matchDeliveryAgencyLinesApi(names: string[]) {
  return mainBackendClient.post<DeliveryAgencyLineOption[]>(
    '/tasks/delivery-agency-lines/match',
    { names },
  );
}

/** MongoDB 中以 source_task_id 关联当前投放任务的素材任务摘要。 */
export interface RelatedMaterialTask {
  id: string;
  taskCode: null | string;
  orderNo: null | string;
  title: null | string;
  status: null | string;
  ownerName: null | string;
  requesterName: null | string;
  quantity: null | number;
  completedQuantity: null | number;
  createdAt: null | string;
  expectedDeliveryAt: null | string;
}

/** 按投放任务查看权限查询关联素材任务，错误由详情区提供重试。 */
export function listRelatedMaterialTasksApi(
  taskId: string,
  page = 1,
  pageSize = 20,
) {
  return mainBackendClient.get<{
    items: RelatedMaterialTask[];
    total: number;
    page: number;
    pageSize: number;
  }>(`/tasks/${taskId}/material-tasks`, {
    params: { page, pageSize },
    skipErrorMessage: true,
  });
}
