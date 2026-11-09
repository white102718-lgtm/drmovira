import { adpulseClient } from '#/api/request';
import { pollUploadTask } from '#/api/utils/poll-task';

/** 批量取产出素材缩略图 base64（验收页视口懒加载） */
export async function getMaterialOrderThumbs(ids: string[]) {
  return adpulseClient.post<Record<string, null | string>>(
    'material-orders/materials/thumbs',
    ids,
  );
}

// ==================== 统一状态映射 ====================
export const ORDER_STATUS_MAP: Record<string, string> = {
  paused: '已暂停',
  cancelled: '已取消',
  draft: '草稿',
  pending_review: '待审核',
  pending_assign: '待分配',
  is_submit: '已提交',
  in_production: '制作中',
  pending_accept: '待验收',
  rejected: '已打回',
  accepted: '已验收',
  is_complete: '已完成',
  archived: '已入库',
  demand_rejected: '已驳回',
  partially_completed: '部分完成',
};

// ==================== Types ====================

export interface UploadTaskResult {
  items: any[];
  skipped: any[];
  errors: { name: string; error: string }[];
  total: number;
  success: number;
  failed: number;
  duplicate_count: number;
  duplicate_names: string[];
}

/** 子需求以独立集合存储，id 在编辑、排序和上传期间保持不变。 */
export interface MaterialRequirement {
  id: string;
  description: string;
  duration: string;
  quantity: number | null | undefined;
  link: string;
  remark: string;
  compliance: string;
  attachments: Record<string, unknown>[];
  seq_label?: string;
  status?: string;
  designers?: string[];
  designer_user_ids?: string[];
  creative_planner_user_ids?: string[];
  completed_designer_ids?: string[];
}

export interface CreateOrderParams {
  status: string;
  title: string;
  project_id?: string;
  project: string;
  source_task_id?: string;
  requester_id?: string;
  requester_name?: string;
  task_scope: 'department' | 'personal';
  responsible_department_id: string | null;
  cc_user_id: string | null;
  /** 任务中心 MySQL biz_task 的稳定 ID；由双写完成后绑定到 Mongo 工单。 */
  task_center_task_id?: string;
  task_department?: string;
  demand_type: string;
  sizes: string[];
  quantity: number | null;
  priority: string;
  /** 预期交付日期，YYYY-MM-DD；历史响应可能带时间。 */
  expected_delivery_at: string;
  product_info: string;
  is_green_material: boolean | null;
  language: string;
  department?: string;
  tags: { country: string[]; theme: string[]; gameplay: string[] };
  requirements: MaterialRequirement[];
  references: OrderReference[];
}

export interface UpdateOrderParams extends CreateOrderParams {
  /** 素材负责人只保存内容，由服务端保留原状态。 */
  preserve_status?: boolean;
  version?: number;
}

export interface MaterialOrderDetail extends CreateOrderParams {
  created_at?: string;
  assignments: MaterialAssignment[];
  /** 有效制作分配的确认进度，不包含策划和已取消记录。 */
  assignment_count?: number;
  id: string;
  version: number;
  order_no: string;
  creator_id: string;
  creator: string;
  responsible_department?: string;
  execution_department: string;
  cc_user_name?: string;
  designers: string[];
  designer_user_ids: string[];
  shared_user_ids?: string[];
  shared_users?: {
    user_id: string;
    user_name: string;
    shared_by_id: string;
    shared_by_name: string;
    shared_at: string;
  }[];
  paused_from_status?: string;
  permissions: {
    pause?: boolean;
    resume?: boolean;
    cancel?: boolean;
    reedit?: boolean;
    share?: boolean;
    shared?: boolean;
    shared_read_only?: boolean;
    edit: boolean;
    assign: boolean;
    review: boolean;
    upload: boolean;
  };
}

export interface MaterialOrderOrganization {
  departments: { id: string; parent_id: string; name: string }[];
  users: {
    id: string;
    full_name: string;
    department_id: string;
    roles: string[];
  }[];
}

/** 素材工单持久化的编辑动态，按当前用户可见工单过滤。 */
export interface MaterialOrderActivity {
  id: string;
  order_id: string;
  title: string;
  project: string;
  status: string;
  operator_id: string;
  operator: string;
  content: string;
  created_at?: string;
}

export function listMaterialOrderActivities(limit = 100) {
  return adpulseClient.get<{ items: MaterialOrderActivity[] }>(
    'material-orders/activities',
    { params: { limit } },
  );
}

export function listMaterialOrderDrafts() {
  return adpulseClient.get<import('#/api/task-center').TaskDraft[]>(
    'material-orders/drafts',
  );
}

/** 分享只追加指定投手的阅读权限，不修改工单执行状态。 */
export function shareMaterialOrder(orderId: string, userId: string) {
  return adpulseClient.post<{
    id: string;
    user_id: string;
    shared: boolean;
    already_shared: boolean;
  }>(`material-orders/${orderId}/share`, { user_id: userId });
}

export function getMaterialOrderOrganization() {
  return adpulseClient.get<MaterialOrderOrganization>(
    'material-orders/options',
  );
}

/** MySQL 用户身份；display_name 对应 full_name，english_nickname 对应 real_name。 */
export interface MaterialOrderFilterUserOption {
  id: string;
  full_name: string;
  real_name: string;
}

export interface MaterialOrderFilterOptions {
  project: string[];
  department: string[];
  /** OPERATOR 投手选项；选中姓名传给列表的 creator（工单提交人）。 */
  operators: MaterialOrderFilterUserOption[];
  /** CREATOR 素材师选项。 */
  designers: MaterialOrderFilterUserOption[];
  /** CREATIVE_PLANNER 创意策划选项。 */
  creative_planners: MaterialOrderFilterUserOption[];
  /** pm_project_region 的国家名称用于展示，代码用于工单筛选。 */
  country: { code: string; name: string }[];
}

/** 创建表单保留数字项目 ID，国家与官方台子名称来自同一项目主数据。 */
export interface MaterialOrderProjectOption {
  id: string;
  name: string;
  status: string;
  product_info: string;
  country_regions: string[];
}

/** 筛选统一取 MySQL 主数据；创建表单可补齐项目 ID、官方台子与国家。 */
export function getMaterialOrderFilterOptions(params?: {
  include_project_details?: boolean;
}) {
  return adpulseClient.get<
    MaterialOrderFilterOptions & {
      project_details?: MaterialOrderProjectOption[];
    }
  >('material-orders/filter-options', { params });
}

export interface OrderReference {
  type: 'upload' | 'link';
  name: string;
  /** 参考资料缩略图，兼容纯 base64 和 data URI。 */
  img?: string | null;
  /** 带附件响应头的签名地址，用于跨域文件下载。 */
  download_url?: string;
  object_key?: string;
  size?: number;
  content_type?: string;
  filetype?: string;
  basename?: string;
  url?: string;
}

export interface ListOrderParams {
  scope?: 'ALL' | 'OWNER' | 'ASSIGNED' | 'CREATED' | 'FOLLOWED' | 'SHARED';
  page?: number;
  page_size?: number;
  project?: string;
  priority?: string | string[];
  demand_type?: string;
  status?: string;
  start_time?: string;
  end_time?: string;
  keyword?: string;
  sort?: string;
  order?: string;
  view?: string;
  operator?: string;
  /** 投手筛选使用素材工单提交人名称。 */
  creator?: string;
  is_green_material?: boolean;
  /** 查询从指定投放任务抽屉发起的素材工单。 */
  source_task_id?: string;
  /** Stable dispatcher identity, used by the task center's “我分配的” view. */
  assigned_by_id?: string;
  /** Include only legacy orders that have no dispatcher identity yet. */
  include_unassigned_assignments?: boolean;
  department?: string;
  designers?: string[];
  creative_planners?: string[];
  country?: string;
}

export type MaterialAssignmentStatus =
  | 'in_production'
  | 'submitted'
  | 'accepted'
  | 'rejected'
  | 'cancelled';
export const ASSIGNMENT_STATUS_MAP: Record<MaterialAssignmentStatus, string> = {
  in_production: '制作中',
  submitted: '待验收',
  accepted: '已验收',
  rejected: '待返工',
  cancelled: '已移除',
};
/** 每条分配绑定一个子需求、一位素材师和可选的一位创意策划。 */
export interface MaterialAssignmentInput {
  id: string;
  req_id: string;
  designer_user_id: string;
  creative_planner_user_id: string | null;
  quantity: number;
  remark: string;
}
export interface MaterialAssignment extends MaterialAssignmentInput {
  designer_name: string;
  creative_planner_name?: string | null;
  status: MaterialAssignmentStatus;
  sort_order: number;
  has_outputs?: boolean;
  started_at?: string | null;
  assigned_by_id: string;
  assigned_by_name: string;
}
export interface AssignItem {
  id: string;
  version: number;
  assignments: MaterialAssignmentInput[];
}

export interface MaterialOrderAssignmentPayload {
  also_executor?: boolean;
  assignee_id: string;
  assignee_name: string;
  department_id?: string;
  due_at?: string;
  id: string;
  progress: number;
  role: 'executor' | 'observer' | 'owner' | 'reviewer';
  status: 'cancelled' | 'doing' | 'done' | 'pending' | 'submitted';
}

export interface MaterialOrderLegacyParticipants {
  completed_designers?: string[];
  creative_planners?: string[];
  designers?: string[];
}

export interface CommentParams {
  content: string;
  version_no?: number;
  event?: string;
}

// ==================== API Functions ====================

const _paramsSerializer = (p: any) => {
  const parts: string[] = [];
  for (const [key, val] of Object.entries(p)) {
    if (val === undefined || val === null) continue;
    if (Array.isArray(val)) {
      (val as any[]).forEach((v) =>
        parts.push(`${key}=${encodeURIComponent(v)}`),
      );
    } else {
      parts.push(`${key}=${encodeURIComponent(String(val))}`);
    }
  }
  return parts.join('&');
};

/** 交付素材传 orderId 由后端生成业务名称；参考附件不传，保留原命名。 */
async function uploadMaterialOrderAttachment(
  file: File,
  isUnzip = true,
  onUploadProgress?: (percent: number) => void,
  signal?: AbortSignal,
  orderId?: string,
) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('is_unzip', String(isUnzip));
  if (orderId) formData.append('order_id', orderId);
  const res: any = await adpulseClient.post(
    'material-orders/attachments',
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60 * 60 * 1000,
      signal,
      onUploadProgress: (e) => {
        if (e.total) onUploadProgress?.(Math.round((e.loaded * 100) / e.total));
      },
    },
  );
  return pollUploadTask(res.task_id, file.size, signal, undefined, true, true);
}

async function createMaterialOrder(data: CreateOrderParams) {
  return adpulseClient.post('material-orders/', data);
}

async function listMaterialOrders(params: ListOrderParams) {
  return adpulseClient.get('material-orders/', {
    params,
    paramsSerializer: _paramsSerializer,
  });
}

/** 关注只绑定当前登录用户，不改变工单业务状态。 */
export interface MaterialOrderFollowState {
  id: string;
  followed: boolean;
}

export function followMaterialOrder(orderId: string) {
  return adpulseClient.post<MaterialOrderFollowState>(
    `material-orders/${orderId}/follow`,
  );
}

export function unfollowMaterialOrder(orderId: string) {
  return adpulseClient.delete<MaterialOrderFollowState>(
    `material-orders/${orderId}/follow`,
  );
}

/** 生命周期只由专用接口修改；版本防止旧列表覆盖最新状态。 */
export type MaterialOrderLifecycleAction = 'pause' | 'resume' | 'cancel';

export function changeMaterialOrderLifecycle(
  orderId: string,
  action: MaterialOrderLifecycleAction,
  version: number,
) {
  return adpulseClient.post<{ id: string; status: string; version: number }>(
    `material-orders/${orderId}/${action}`,
    { version },
  );
}

async function getMaterialOrderStats(params?: {
  start_time?: string;
  end_time?: string;
}) {
  return adpulseClient.get('material-orders/stats', { params });
}

async function batchAssignMaterialOrders(items: AssignItem[]) {
  return adpulseClient.post<{ count: number }>('material-orders/batch-assign', {
    items,
  });
}

async function getCreators() {
  return adpulseClient.get<
    {
      user_id: string;
      full_name: string;
      real_name?: string;
      in_production_count: number;
    }[]
  >('material-orders/creators');
}

async function getMyStats(params?: Record<string, any>) {
  return adpulseClient.get('material-orders/my-stats', {
    params,
    paramsSerializer: _paramsSerializer,
  });
}

async function getMaterialOrderDetail(orderId: string) {
  return adpulseClient.get<MaterialOrderDetail>(`material-orders/${orderId}`);
}

async function updateMaterialOrder(orderId: string, data: UpdateOrderParams) {
  if (typeof data.version !== 'number')
    throw new Error('缺少任务版本，请刷新后再保存');
  return adpulseClient.put(`material-orders/${orderId}`, data);
}

/**
 * 将已创建的任务中心 MySQL biz_task 绑定到 Mongo 素材工单。
 * 服务端只允许首次绑定或同一 ID 重试，避免网络重试把两个任务串到一张工单。
 */
async function bindMaterialOrderTaskCenterTask(
  orderId: string,
  taskCenterTaskId: string,
) {
  return adpulseClient.post(`material-orders/${orderId}/task-center-link`, {
    task_center_task_id: taskCenterTaskId,
  });
}

/** 交付记录只保留名称和稳定关联，避免详情加载预览链接与素材内容。 */
export interface MaterialOrderOutputSummary {
  id: string;
  req_id: string | null;
  assignment_id: string | null;
  name: string;
  created_at?: string | null;
  review_status?: string | null;
  superseded: boolean;
}
export interface MaterialOrderReviewRecord {
  id: string;
  event: string;
  operator: string;
  created_at?: string | null;
  content: string;
}
export function getMaterialOrderOutputs(orderId: string) {
  return adpulseClient.get<{ items: MaterialOrderOutputSummary[] }>(
    `material-orders/${orderId}/outputs`,
  );
}
export function getMaterialOrderReviewRecords(orderId: string) {
  return adpulseClient.get<{ items: MaterialOrderReviewRecord[] }>(
    `material-orders/${orderId}/review-records`,
  );
}

/** 子需求验收卡片。分页不携带 base64 缩略图，预览地址仅为当前页生成。 */
export interface MaterialReviewAsset {
  id: string;
  req_id: string;
  assignment_id: string;
  name: string;
  filetype: string;
  size: number;
  width?: number | null;
  height?: number | null;
  /** 视频时长，单位秒。图片或未解析时为空。 */
  duration?: number | null;
  review_status?: string | null;
  url?: string | null;
}
export function getMaterialReviewSummary(orderId: string) {
  return adpulseClient.get<{ counts: Record<string, number>; total: number }>(
    `material-orders/${orderId}/review-summary`,
  );
}
export function getMaterialReviewAssets(
  orderId: string,
  reqId: string,
  cursor: string | null,
) {
  return adpulseClient.get<{
    items: MaterialReviewAsset[];
    next_cursor: string | null;
  }>(`material-orders/${orderId}/review-materials`, {
    params: { req_id: reqId, page_size: 32, ...(cursor ? { cursor } : {}) },
  });
}
export function getMaterialRequirementSelection(
  orderId: string,
  reqId: string,
) {
  return adpulseClient.get<{ items: MaterialReviewAsset[] }>(
    `material-orders/${orderId}/requirements/${encodeURIComponent(reqId)}/material-selection`,
  );
}
export function reviewMaterialRequirement(
  orderId: string,
  reqId: string,
  data: { action: 'pass' | 'reject'; version: number; reason?: string },
) {
  return adpulseClient.post<{
    id: string;
    req_id: string;
    status: string;
    version: number;
  }>(
    `material-orders/${orderId}/requirements/${encodeURIComponent(reqId)}/review`,
    data,
  );
}

async function getMaterialOrderMaterials(orderId: string, status?: string) {
  const params: Record<string, string> = {};
  if (status && status !== 'all') params.status = status;
  return adpulseClient.get(`material-orders/${orderId}/materials`, { params });
}

async function acceptMaterialOrder(
  orderId: string,
  data: { action: 'pass'; rating: number },
) {
  return adpulseClient.post(`material-orders/${orderId}/accept`, data);
}

async function getMaterialOrderComments(orderId: string) {
  return adpulseClient.get(`material-orders/${orderId}/comments`);
}

async function postMaterialOrderComment(orderId: string, data: CommentParams) {
  return adpulseClient.post(`material-orders/${orderId}/comments`, data);
}

async function completeMaterialOrder(orderId: string, assignmentIds: string[]) {
  return adpulseClient.post(`material-orders/${orderId}/complete`, {
    assignment_ids: assignmentIds,
  });
}

async function assignMaterialsApi(
  orderId: string,
  data: { ids: string[]; scope: string; folder_id?: string },
) {
  return adpulseClient.post(
    `material-orders/${orderId}/assign-materials`,
    data,
  );
}

/**
 * 服务端已确认上传的素材文件。`deliverMaterialOrder` 只能接收这类
 * 文件事实，不能由调用方根据本地文件名伪造 object key 或哈希。
 */
export interface MaterialOrderDeliverableFilePayload {
  filename: string;
  object_key: string;
  basename: string;
  size: number;
  content_type: string;
  filetype: string;
  file_md5: string;
  sha3_256: string;
  width: number;
  height: number;
  duration: number;
  url: string;
  img: string;
  assignment_id: string;
  req_id?: string;
}

async function deliverMaterialOrder(
  orderId: string,
  materials: MaterialOrderDeliverableFilePayload[],
  designer?: string,
  creativePlanner?: string,
) {
  return adpulseClient.post(`material-orders/${orderId}/deliver`, {
    materials,
    ...(designer ? { designer } : {}),
    ...(creativePlanner ? { creative_planner: creativePlanner } : {}),
  });
}

async function listDraftMaterialOrders(params: ListOrderParams) {
  return adpulseClient.get('material-orders/drafts', {
    params,
    paramsSerializer: _paramsSerializer,
  });
}

async function batchDeleteMaterialOrders(ids: string[], status?: string) {
  return adpulseClient.post('material-orders/batch-delete-cascade', {
    ids,
    ...(status ? { status } : {}),
  });
}

async function deleteMaterials(orderId: string, ids: string[]) {
  return adpulseClient.post(`material-orders/${orderId}/materials/delete`, {
    ids,
  });
}

async function rejectMaterials(orderId: string, ids: string[]) {
  return adpulseClient.post(`material-orders/${orderId}/materials/reject`, {
    ids,
  });
}

async function cancelRejectMaterials(orderId: string, ids: string[]) {
  return adpulseClient.post(
    `material-orders/${orderId}/materials/cancel-reject`,
    { ids },
  );
}

async function acceptMaterials(orderId: string, ids: string[]) {
  return adpulseClient.post(`material-orders/${orderId}/materials/accept`, {
    ids,
  });
}

export interface RejectItem {
  id: string;
  reason: string;
}

async function batchRejectMaterialOrders(items: RejectItem[]) {
  return adpulseClient.post<{ count: number }>('material-orders/batch-reject', {
    items,
  });
}

// ==================== 修改记录 ====================

export interface ChangeLogEntry {
  id: string;
  order_id: string;
  operator: string;
  created_at: string;
  changes: {
    assignment_id?: string;
    req_id?: string;
    field: string;
    old: any;
    new: any;
  }[];
}

async function getMaterialOrderChangelog(
  orderId: string,
): Promise<ChangeLogEntry[]> {
  return adpulseClient.get(`material-orders/${orderId}/histories`);
}

async function downloadMaterialOrderZip(ids: string[]) {
  const res: any = await adpulseClient.post('material-orders/zip', ids, {
    timeout: 300_000,
  });
  return pollUploadTask(res.task_id, 0, undefined, 6000, true);
}

async function downloadAttachmentsZip(objectKeys: string[]) {
  const res: any = await adpulseClient.post(
    'material-orders/zip-attachments',
    objectKeys,
    {
      timeout: 300_000,
    },
  );
  return pollUploadTask(res.task_id, 0, undefined, 6000, true);
}

export {
  assignMaterialsApi,
  batchAssignMaterialOrders,
  bindMaterialOrderTaskCenterTask,
  cancelRejectMaterials,
  completeMaterialOrder,
  createMaterialOrder,
  deleteMaterials,
  rejectMaterials,
  deliverMaterialOrder,
  downloadAttachmentsZip,
  downloadMaterialOrderZip,
  getMaterialOrderChangelog,
  getMaterialOrderComments,
  getMaterialOrderDetail,
  getMaterialOrderMaterials,
  getMaterialOrderStats,
  getMyStats,
  listMaterialOrders,
  postMaterialOrderComment,
  acceptMaterials,
  acceptMaterialOrder,
  updateMaterialOrder,
  uploadMaterialOrderAttachment,
  listDraftMaterialOrders,
  batchDeleteMaterialOrders,
  batchRejectMaterialOrders,
  getCreators,
};
