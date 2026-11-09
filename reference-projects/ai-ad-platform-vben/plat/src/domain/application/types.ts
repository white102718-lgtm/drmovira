/**
 * Canonical, compatibility-first model for the existing resource application
 * and approval-centre records.  During the migration an ApprovalInstance uses
 * the same stable ID as its ResourceApplication; this preserves every old
 * route and persisted record while giving actions and comments one owner.
 */
export type ApplicationApprovalRole = 'finance' | 'media' | 'office';

export type ApplicationCategory =
  | 'advertising'
  | 'finance'
  | 'office'
  | 'social';

export type ApplicationStatus =
  | 'approved'
  | 'draft'
  | 'pending'
  | 'processing'
  | 'rejected';

export type ApplicationType =
  | 'account'
  | 'computer'
  | 'mobile'
  | 'payment'
  | 'pixel'
  | 'project'
  | 'tg';

/** Legacy record names remain supported by the compatibility Store. */
export type ApprovalAction =
  | 'approved'
  | 'completed'
  | 'copied'
  | 'rejected'
  | 'submitted'
  | 'transferred';

export type ApplicationApprovalNodeStatus =
  | 'approved'
  | 'pending'
  | 'rejected'
  | 'waiting';

export interface ApplicationComment {
  actor: string;
  actorRole: string;
  at: string;
  content: string;
  id: string;
  /**
   * Additive read receipts. Older records simply omit it and are treated as
   * unread by everyone except their author.
   */
  readBy?: string[];
}

export interface ApplicationApprovalRecord {
  action: ApprovalAction;
  /** 业务办理完成时固化的办理表单值。 */
  actionData?: Record<string, unknown>;
  actor: string;
  /** Stable directory ID; legacy locally persisted records may omit it. */
  actorId?: string;
  actorRole: string;
  at: string;
  id: string;
  /** Zero-based approval node index for events such as transfer. */
  nodeIndex?: number;
  /** Recipient details are populated only for a transfer action. */
  recipientDepartmentId?: string;
  recipientDepartmentName?: string;
  recipientId?: string;
  recipientName?: string;
  remark: string;
}

/** 办理人实际分配的非敏感资产摘要。 */
export interface ApplicationAllocatedAsset {
  assetCode: string;
  assetName: string;
  assetType: string;
  channelName?: string;
  id: string;
  projectName?: string;
}

export interface ApplicationApprovalNode {
  actedAt?: string;
  approver: string;
  /** Stable when the formal directory was available at write time. */
  approverId?: string;
  id: string;
  label: string;
  remark?: string;
  role: ApplicationApprovalRole;
  status: ApplicationApprovalNodeStatus;
}

/**
 * Compatibility projection of ResourceApplication + ApprovalInstance.
 * `id` is deliberately shared by the application, decisions, comments and
 * copy records until the formal backend returns a separate approval ID.
 */
/**
 * Account applications do not infer a user/team from their requester or task.
 * This payload is collected explicitly and mapped into the legacy resource
 * lifecycle only after the business approval completes.
 */
export interface ApplicationResourceRequest {
  assigneeId: string;
  assigneeName: string;
  expectedReturnAt?: string;
  teamId: string;
  teamName: string;
  timezone?: string;
  whitelistRequired?: boolean;
}

export interface ResourceApplication {
  /** 办理阶段实际分配的资产，不得包含密码等敏感数据。 */
  allocatedAssets?: ApplicationAllocatedAsset[];
  amount?: number;
  approvalNodes: ApplicationApprovalNode[];
  approvalRecords: ApplicationApprovalRecord[];
  approvalRole: ApplicationApprovalRole;
  approver: string;
  ccUsers: string[];
  comments: ApplicationComment[];
  createdAt: string;
  currency?: string;
  /** Optional department scope; old applications keep their display fields. */
  departmentId?: string;
  /** Submission-time department snapshot used by approval list filtering. */
  departmentName?: string;
  description: string;
  /** Submitted values produced by the published dynamic approval form. */
  formData?: Record<string, unknown>;
  /** Immutable form snapshot used to render the application exactly as submitted. */
  formSchema?: Array<{
    helpText?: string;
    key: string;
    label: string;
    optionSource?: string;
    type: string;
    width?: 'full' | 'half';
  }>;
  /** Immutable business actions executed only by the workflow handler. */
  handlerAction?: {
    formSchema?: Array<{
      accept?: string;
      helpText?: string;
      key: string;
      label: string;
      maxCount?: number;
      maxFileSizeMb?: number;
      maxValue?: number;
      minValue?: number;
      placeholder?: string;
      required: boolean;
      type: string;
      width?: 'full' | 'half';
    }>;
    resourceAssignment?: {
      assetTypeFieldKey?: string;
      assetTypeSource: 'application';
      channelFieldKey?: string;
      enabled: boolean;
      quantityFieldKey: string;
    };
  };
  /** Workflow-level executor responsible for delivery after all approvals. */
  handlerApprovalNodeId?: string;
  handlerId?: string;
  handlerName?: string;
  handlerSource?: 'approval-node' | 'fixed-user';
  id: string;
  platform?: string;
  project: string;
  /** Stable project reference. `project` remains the legacy display field. */
  projectId?: string;
  quantity?: number;
  /** Stable requester reference. Never inferred from the legacy name. */
  requester: string;
  requesterId?: string;
  requesterName?: string;
  /** Stable child ID in the existing media-resource application lifecycle. */
  resourceApplicationId?: string;
  /** Explicit resource-delivery target; required only for account requests. */
  resourceRequest?: ApplicationResourceRequest;
  /** Originating delivery task, when this application was launched in context. */
  sourceTaskId?: string;
  /** 上一张被驳回申请的稳定 ID；仅由重新提交生成的新申请保留。 */
  sourceApplicationId?: string;
  status: ApplicationStatus;
  title: string;
  type: ApplicationType;
  updatedAt?: string;
}

export type ResourceApplicationSeed = Partial<ResourceApplication> &
  Pick<ResourceApplication, 'id' | 'status' | 'type'>;

export interface ApplicationActor {
  /** A formal adapter can supply this stable user ID without changing UI. */
  id?: string;
  name: string;
  role: string;
}

/** Additive source context shared by task detail and the application form. */
export interface ApplicationSourceContext {
  projectId: string;
  projectName: string;
  requesterId: string;
  requesterName: string;
  sourceTaskId: string;
}

export type ApplicationFormFieldKey =
  | 'amount'
  | 'currency'
  | 'platform'
  | 'quantity'
  | 'resourceAssignee'
  | 'resourceTeam';

/** Read-only form contract; old payload serialization remains unchanged. */
export interface ApplicationFormFieldSchema {
  key: ApplicationFormFieldKey;
  required?: boolean;
}

export interface ApplicationFormSchema {
  fields: ApplicationFormFieldSchema[];
  type: ApplicationType;
}

export interface ApprovalDecisionInput {
  actor: ApplicationActor;
  decision: Extract<ApprovalAction, 'approved' | 'rejected'>;
  remark: string;
}

export interface ApplicationCommentInput {
  actor: ApplicationActor;
  content: string;
}

export interface ApplicationResubmissionInput {
  actor: ApplicationActor;
  remark: string;
}

export interface ApplicationTransferRecipient {
  departmentId: string;
  departmentName: string;
  id: string;
  name: string;
}

export interface ApplicationTransferInput {
  actor: ApplicationActor;
  recipient: ApplicationTransferRecipient;
  remark: string;
}

export const approvalRoleMeta: Record<
  ApplicationApprovalRole,
  { approver: string; color: string; label: string }
> = {
  finance: { approver: '王楠', color: 'green', label: '财务审批' },
  media: { approver: '周敏', color: 'blue', label: '媒介审批' },
  office: { approver: '郑然', color: 'purple', label: '行政与资产审批' },
};

export const applicationTypeLabels: Record<ApplicationType, string> = {
  account: '广告账号申请',
  computer: '电脑申请',
  mobile: '手机号申请',
  payment: '项目付款申请',
  pixel: '像素申请',
  project: '项目结项审批',
  tg: '社交资产申请',
};

export function approvalRoleForType(
  type: ApplicationType,
): ApplicationApprovalRole {
  if (type === 'payment') return 'finance';
  if (type === 'computer' || type === 'mobile') return 'office';
  return 'media';
}
