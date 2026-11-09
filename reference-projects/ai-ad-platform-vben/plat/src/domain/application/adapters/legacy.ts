import type {
  ApplicationAdapter,
  ApplicationFormSchemaAdapter,
  ApplicationPersistenceAdapter,
} from '../adapter';
import type {
  ApplicationApprovalNode,
  ApplicationApprovalNodeStatus,
  ApplicationApprovalRecord,
  ApplicationApprovalRole,
  ApplicationFormSchema,
  ApplicationType,
  ApprovalAction,
  ResourceApplication,
  ResourceApplicationSeed,
} from '../types';

import {
  applicationTypeLabels,
  approvalRoleForType,
  approvalRoleMeta,
} from '../types';

function nowText() {
  return new Date().toLocaleString('zh-CN', { hour12: false });
}

/**
 * 将审批持久化字段复制为普通 JSON 数据。
 *
 * Vue 响应式对象的嵌套字段仍可能是 Proxy，直接 structuredClone 会抛出
 * DataCloneError；审批表单快照只允许 JSON 兼容值，因此逐层复制即可同时
 * 去除响应式代理并隔离调用方后续修改。
 */
function clonePersistedData<T>(value: T): T {
  if (value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) {
    return value.map((item) => clonePersistedData(item)) as T;
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, clonePersistedData(item)]),
  ) as T;
}

function legacyRecord(
  id: string,
  action: ApprovalAction,
  actor: string,
  actorRole: string,
  at: string,
  remark: string,
): ApplicationApprovalRecord {
  return { action, actor, actorRole, at, id, remark };
}

function legacyRecordId(applicationId: string) {
  return `APR-${applicationId}-${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 6)}`;
}

function defaultCcUsers(role: ApplicationApprovalRole) {
  if (role === 'finance') return ['项目负责人', '财务归档'];
  if (role === 'office') return ['申请人直属负责人', '资产管理员'];
  return ['项目负责人', '资源交付负责人'];
}

function defaultApprovalRemark(
  action: ApprovalAction,
  role: ApplicationApprovalRole,
) {
  if (action === 'approved') return '审批通过，进入后续资源交付流程。';
  if (action === 'rejected') return '申请资料不完整，请补充说明后重新提交。';
  return `申请已提交至${approvalRoleMeta[role].label}。`;
}

const legacyFormSchemas: Record<ApplicationType, ApplicationFormSchema> = {
  account: {
    fields: [
      { key: 'platform', required: true },
      { key: 'quantity' },
      { key: 'resourceAssignee', required: true },
      { key: 'resourceTeam', required: true },
    ],
    type: 'account',
  },
  computer: { fields: [{ key: 'quantity' }], type: 'computer' },
  mobile: { fields: [{ key: 'quantity' }], type: 'mobile' },
  payment: {
    fields: [
      { key: 'amount', required: true },
      { key: 'currency', required: true },
    ],
    type: 'payment',
  },
  pixel: {
    fields: [{ key: 'platform', required: true }, { key: 'quantity' }],
    type: 'pixel',
  },
  project: { fields: [{ key: 'projectId', required: true }], type: 'project' },
  tg: {
    fields: [{ key: 'platform', required: true }, { key: 'quantity' }],
    type: 'tg',
  },
};

function copiedRecord(applicationId: string, ccUsers: string[], at: string) {
  return legacyRecord(
    legacyRecordId(applicationId),
    'copied',
    '系统通知',
    '抄送',
    at,
    `审批结果已抄送：${ccUsers.join('、')}`,
  );
}

function normalizeNode(
  node: ApplicationApprovalNode,
  index: number,
  applicationId: string,
  defaultRole: ApplicationApprovalRole,
): ApplicationApprovalNode {
  return {
    actedAt: node.actedAt,
    approver: node.approver?.trim() || approvalRoleMeta[defaultRole].approver,
    approverId: node.approverId?.trim() || undefined,
    id: node.id || `NODE-${applicationId}-${index + 1}`,
    label: node.label?.trim() || `审批节点 ${index + 1}`,
    remark: node.remark?.trim() || undefined,
    role: node.role ?? defaultRole,
    status: node.status ?? (index === 0 ? 'pending' : 'waiting'),
  };
}

/**
 * Reads every pre-domain Store payload without changing its localStorage key
 * or envelope. It deliberately does not reseed missing user records.
 */
export class LegacyApplicationAdapter
  implements ApplicationAdapter, ApplicationFormSchemaAdapter
{
  getFormSchema(type: ApplicationType) {
    return structuredClone(legacyFormSchemas[type]);
  }

  normalize(application: ResourceApplicationSeed): ResourceApplication {
    const role =
      application.approvalRole ?? approvalRoleForType(application.type);
    const requester = application.requester?.trim() || '当前用户';
    const createdAt = application.createdAt ?? nowText();
    const approver =
      application.approver?.trim() || approvalRoleMeta[role].approver;
    let fallbackStatus: ApplicationApprovalNodeStatus = 'pending';
    if (application.status === 'rejected') fallbackStatus = 'rejected';
    if (['approved', 'processing'].includes(application.status)) {
      fallbackStatus = 'approved';
    }

    const approvalNodes =
      Array.isArray(application.approvalNodes) &&
      application.approvalNodes.length > 0
        ? application.approvalNodes.map((node, index) =>
            normalizeNode(node, index, application.id, role),
          )
        : [
            {
              actedAt:
                fallbackStatus === 'pending'
                  ? undefined
                  : (application.updatedAt ?? createdAt),
              approver,
              id: `NODE-${application.id}-1`,
              label: approvalRoleMeta[role].label,
              role,
              status: fallbackStatus,
            },
          ];
    const currentNode =
      approvalNodes.find((node) => node.status === 'pending') ??
      approvalNodes.find((node) => node.status === 'waiting');
    let approvalRecords: ApplicationApprovalRecord[] = Array.isArray(
      application.approvalRecords,
    )
      ? application.approvalRecords.map((record) => ({
          ...record,
          actionData: record.actionData
            ? clonePersistedData(record.actionData)
            : undefined,
          remark:
            record.remark?.trim() || defaultApprovalRemark(record.action, role),
        }))
      : [];
    const ccUsers = [
      ...new Set(
        (Array.isArray(application.ccUsers)
          ? application.ccUsers
          : defaultCcUsers(role)
        )
          .map((name) => name.trim())
          .filter(Boolean),
      ),
    ];
    const comments = Array.isArray(application.comments)
      ? application.comments.map((comment) => ({
          ...comment,
          content: comment.content?.trim() || '已参与流程讨论。',
          readBy: [
            ...new Set(
              (comment.readBy ?? [comment.actor])
                .map((name) => name.trim())
                .filter(Boolean),
            ),
          ],
        }))
      : [];

    if (application.id === 'REQ-20260811-001' && comments.length === 0) {
      comments.push(
        {
          actor: requester,
          actorRole: '申请人',
          at: '2026-08-11 09:36',
          content: '日本首发需要 GMT+9 账户，请优先匹配日本代理线。',
          id: 'COMMENT-REQ-20260811-001-1',
          readBy: [requester],
        },
        {
          actor: approver,
          actorRole: approvalRoleMeta[role].label,
          at: '2026-08-11 10:02',
          content: '已收到，正在核对账户库存与时区。',
          id: 'COMMENT-REQ-20260811-001-2',
          readBy: [approver],
        },
      );
    }

    if (application.status !== 'draft' && approvalRecords.length === 0) {
      approvalRecords = [
        legacyRecord(
          legacyRecordId(application.id),
          'submitted',
          requester,
          '申请人',
          createdAt,
          `申请已提交至${approvalRoleMeta[role].label}。`,
        ),
      ];
      if (['approved', 'processing', 'rejected'].includes(application.status)) {
        const rejected = application.status === 'rejected';
        approvalRecords.push(
          legacyRecord(
            legacyRecordId(application.id),
            rejected ? 'rejected' : 'approved',
            approver,
            approvalRoleMeta[role].label,
            application.updatedAt ?? createdAt,
            rejected
              ? '申请资料不完整，请补充说明后重新提交。'
              : '审批通过，进入后续资源交付流程。',
          ),
        );
      }
    }

    if (
      ['approved', 'processing', 'rejected'].includes(application.status) &&
      ccUsers.length > 0 &&
      !approvalRecords.some((record) => record.action === 'copied')
    ) {
      approvalRecords.push(
        copiedRecord(
          application.id,
          ccUsers,
          application.updatedAt ?? createdAt,
        ),
      );
    }

    return {
      allocatedAssets: application.allocatedAssets?.map((asset) => ({
        ...asset,
      })),
      amount: application.amount,
      approvalNodes,
      approvalRecords,
      approvalRole: currentNode?.role ?? role,
      approver: currentNode?.approver ?? approver,
      ccUsers,
      comments,
      createdAt,
      currency: application.currency,
      departmentId: application.departmentId?.trim() || undefined,
      departmentName: application.departmentName?.trim() || undefined,
      description: application.description ?? '',
      formData: application.formData
        ? clonePersistedData(application.formData)
        : undefined,
      formSchema: application.formSchema
        ? clonePersistedData(application.formSchema)
        : undefined,
      handlerAction: application.handlerAction
        ? clonePersistedData(application.handlerAction)
        : undefined,
      id: application.id,
      platform: application.platform,
      projectId: application.projectId?.trim() || undefined,
      project: application.project ?? '未设置归属',
      quantity: application.quantity,
      requesterId: application.requesterId?.trim() || undefined,
      requesterName: application.requesterName?.trim() || requester,
      resourceApplicationId:
        application.resourceApplicationId?.trim() || undefined,
      resourceRequest: application.resourceRequest
        ? {
            assigneeId: application.resourceRequest.assigneeId?.trim() || '',
            assigneeName:
              application.resourceRequest.assigneeName?.trim() || '',
            expectedReturnAt:
              application.resourceRequest.expectedReturnAt?.trim() || undefined,
            teamId: application.resourceRequest.teamId?.trim() || '',
            teamName: application.resourceRequest.teamName?.trim() || '',
            timezone: application.resourceRequest.timezone?.trim() || undefined,
            whitelistRequired: application.resourceRequest.whitelistRequired,
          }
        : undefined,
      requester,
      sourceTaskId: application.sourceTaskId?.trim() || undefined,
      sourceApplicationId: application.sourceApplicationId?.trim() || undefined,
      status: application.status,
      title:
        application.title ??
        `${applicationTypeLabels[application.type]}（未命名）`,
      type: application.type,
      updatedAt: application.updatedAt ?? createdAt,
    };
  }
}

export interface LegacyApplicationStoreAdapterOptions {
  applications: () => readonly ResourceApplication[];
  remove(applicationId: string): void;
  upsert(application: ResourceApplication): ResourceApplication;
}

/**
 * Small injected bridge so migrated pages never write the Store directly.
 * It intentionally owns no storage and keeps the original raw-array key.
 */
export class LegacyApplicationStoreAdapter
  extends LegacyApplicationAdapter
  implements ApplicationPersistenceAdapter
{
  constructor(private readonly options: LegacyApplicationStoreAdapterOptions) {
    super();
  }

  list() {
    return this.options
      .applications()
      .map((application) => this.normalize(application));
  }

  remove(applicationId: string) {
    this.options.remove(applicationId);
  }

  upsert(application: ResourceApplication) {
    return this.options.upsert(this.normalize(application));
  }
}
