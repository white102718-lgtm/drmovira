import type { MaterialAssignment } from '#/api/requirement';
import type { TaskCenterStatus } from '#/store/task-center';

/** backend_new material-orders 接口列表项中与任务中心相关的最小字段集合。 */
export interface LegacyMaterialOrderSummary {
  assignments?: MaterialAssignment[];
  followed?: boolean;
  creator_id?: string;
  designer_user_ids?: string[];
  completed_designer_ids?: string[];
  progress?: number;
  uploaded_quantity?: number;
  accepted_quantity?: number;
  rejected_quantity?: number;
  pending_review_quantity?: number;
  version?: number;
  permissions?: {
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
  completed_designers?: string[];
  created_at?: string;
  creator?: string;
  demand_type?: string;
  department?: string;
  designers?: string[];
  creative_planners?: string[];
  expected_delivery_at?: string;
  id: string;
  order_no?: string;
  priority?: string;
  project?: string;
  project_id?: string;
  quantity?: number;
  requester_id?: string;
  requester_name?: string;
  source_task_id?: string;
  status: string;
  task_center_task_id?: string;
  title?: string;
  updated_at?: string;
}

/** 已驳回需求由原提交人重新编辑；验收打回仍走素材返工流程。 */
export function canEditRejectedMaterialOrder(
  order?: Pick<LegacyMaterialOrderSummary, 'permissions' | 'status'> | null,
): boolean {
  return (
    order?.status === 'demand_rejected' && Boolean(order.permissions?.edit)
  );
}

/** 素材负责人重新编辑在途工单；权限由后端角色与可见范围共同确定。 */
export function canReeditMaterialOrder(
  order?: Pick<LegacyMaterialOrderSummary, 'permissions' | 'status'> | null,
): boolean {
  return Boolean(
    order?.permissions?.reedit &&
      !order.permissions.shared_read_only &&
      ![
        'paused',
        'cancelled',
        'draft',
        'pending_accept',
        'accepted',
        'archived',
        'is_complete',
      ].includes(order.status),
  );
}

/** 已完成工单可复用需求内容新建，原单的执行和验收状态不参与复制。 */
export function canResubmitMaterialOrder(
  order?: Pick<LegacyMaterialOrderSummary, 'status'> | null,
): boolean {
  return order?.status === 'accepted' || order?.status === 'archived';
}

export interface LegacyMaterialOrderTaskProjection {
  actionLabel: string;
  createdAt: string;
  createdBy: string;
  dueAt: string;
  legacyMaterialOrderId: string;
  legacyMaterialOrderStatus: string;
  owner: string;
  progress: number;
  project: string;
  status: TaskCenterStatus;
  summary: string;
  title: string;
  updatedAt: string;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : undefined;
}

function asString(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function asStringArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string =>
          typeof item === 'string' && Boolean(item.trim()),
      )
    : [];
}

function asPositiveNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

/** 素材分配后直接制作；操作权限由本人的分配记录决定。 */
export function materialOrderStatusToTaskStatus(
  status: string,
): TaskCenterStatus {
  switch (status) {
    case 'paused':
    case 'cancelled': {
      return status;
    }
    case 'accepted':
    case 'archived': {
      return 'done';
    }
    case 'in_production':
    case 'rejected': {
      return 'doing';
    }
    case 'partially_completed': {
      return 'partially_completed';
    }
    case 'demand_rejected': {
      return 'withdrawn';
    }
    case 'draft': {
      return 'draft';
    }
    case 'is_submit': {
      return 'pending_assignment';
    }
    case 'pending_accept': {
      return 'pending_acceptance';
    }
    case 'pending_assign': {
      return 'pending_assignment';
    }
    default: {
      return 'pending';
    }
  }
}

/**
 * 解析 material-orders 列表响应。接口正处于迁移期，兼容直接数组与
 * { items } / { data: { items } } 两种响应，非法项会被忽略。
 */
export function readLegacyMaterialOrderSummaries(
  response: unknown,
): LegacyMaterialOrderSummary[] {
  const outer = asRecord(response);
  const nested = asRecord(outer?.data);
  let items: unknown[] = [];
  if (Array.isArray(response)) {
    items = response;
  } else if (Array.isArray(outer?.items)) {
    items = outer.items;
  } else if (Array.isArray(nested?.items)) {
    items = nested.items;
  }

  return items.flatMap((item) => {
    const record = asRecord(item);
    const id = asString(record?.id ?? record?._id);
    const status = asString(record?.status);
    if (!id || !status) return [];

    return [
      {
        creator_id: asString(record?.creator_id),
        assignments: Array.isArray(record?.assignments)
          ? (record.assignments as MaterialAssignment[])
          : [],
        followed: record?.followed === true,
        designer_user_ids: asStringArray(record?.designer_user_ids),
        completed_designer_ids: asStringArray(record?.completed_designer_ids),
        progress: asPositiveNumber(record?.progress),
        uploaded_quantity: asPositiveNumber(record?.uploaded_quantity),
        accepted_quantity: asPositiveNumber(record?.accepted_quantity),
        rejected_quantity: asPositiveNumber(record?.rejected_quantity),
        pending_review_quantity: asPositiveNumber(
          record?.pending_review_quantity,
        ),
        permissions:
          record?.permissions as LegacyMaterialOrderSummary['permissions'],
        completed_designers: asStringArray(record?.completed_designers),
        created_at: asString(record?.created_at),
        creator: asString(record?.creator, '未知创建人'),
        demand_type: asString(record?.demand_type),
        department: asString(record?.department),
        designers: asStringArray(record?.designers),
        creative_planners: asStringArray(record?.creative_planners),
        expected_delivery_at: asString(record?.expected_delivery_at, '未设置'),
        id,
        version: asPositiveNumber(record?.version),
        order_no: asString(record?.order_no),
        priority: asString(record?.priority),
        project: asString(record?.project, '未关联项目'),
        project_id: asString(record?.project_id),
        quantity: asPositiveNumber(record?.quantity),
        requester_id: asString(record?.requester_id),
        requester_name: asString(record?.requester_name),
        source_task_id: asString(record?.source_task_id),
        status,
        task_center_task_id: asString(record?.task_center_task_id),
        title: asString(record?.title, '未命名素材需求'),
        updated_at: asString(record?.updated_at),
      },
    ];
  });
}

function progressOf(order: LegacyMaterialOrderSummary) {
  if (typeof order.progress === 'number') return order.progress;
  const status = materialOrderStatusToTaskStatus(order.status);
  if (status === 'done' || status === 'pending_acceptance') return 100;
  if (order.status !== 'partially_completed' || !order.designers?.length) {
    return 0;
  }
  return Math.round(
    (asStringArray(order.completed_designers).length / order.designers.length) *
      100,
  );
}

function actionLabelOf(status: TaskCenterStatus) {
  if (status === 'pending_assignment') return '分配任务';
  if (status === 'doing') return '提交交付';
  if (status === 'partially_completed') return '继续上传';
  if (status === 'pending_acceptance') return '验收素材';
  return '查看工单';
}

/** 将旧工单投影成任务中心可展示的素材任务，不生成新的业务 ID。 */
export function projectLegacyMaterialOrderTask(
  order: LegacyMaterialOrderSummary,
): LegacyMaterialOrderTaskProjection {
  const status = materialOrderStatusToTaskStatus(order.status);
  const designerNames = asStringArray(order.designers);
  const owner =
    designerNames.join('、') ||
    (status === 'pending_assignment' ? '待分配' : '素材中台');
  const details = [
    order.demand_type,
    order.quantity ? `${order.quantity} 个素材` : '',
    order.priority,
  ].filter(Boolean);

  return {
    actionLabel: actionLabelOf(status),
    createdAt: order.created_at || order.updated_at || '',
    createdBy: order.creator || '未知创建人',
    dueAt: order.expected_delivery_at || '未设置',
    legacyMaterialOrderId: order.id,
    legacyMaterialOrderStatus: order.status,
    owner,
    progress: progressOf(order),
    project: order.project || '未关联项目',
    status,
    summary: details.join(' · ') || '素材需求工单',
    title: order.title || '未命名素材需求',
    updatedAt: order.updated_at || order.created_at || '',
  };
}
