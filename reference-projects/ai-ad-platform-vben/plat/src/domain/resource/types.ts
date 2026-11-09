export type MediaPlatform = 'facebook' | 'google' | 'kwai' | 'tiktok';

export type MediaPlatformStatus =
  | 'active'
  | 'closed'
  | 'disabled'
  | 'pending_review'
  | 'restricted'
  | 'unsettled';

export type MediaWhitelistStatus =
  | 'approved'
  | 'not_required'
  | 'pending'
  | 'rejected';

export type MediaResourceStatus =
  | 'assigned'
  | 'available'
  | 'exception'
  | 'maintenance'
  | 'pending_assignment'
  | 'pending_return'
  | 'retired';

export type ResourceApplicationStatus =
  | 'approved'
  | 'partially_approved'
  | 'pending'
  | 'rejected';

export type ResourceAssignmentStatus =
  | 'active'
  | 'return_requested'
  | 'returned';

export type ResourceReturnStatus = 'completed' | 'requested';

export type ResourceResolutionOutcome = 'available' | 'disabled';

export interface AuditActor {
  id: string;
  name: string;
}

export interface MediaAccount {
  accountId: string;
  agencyLineId?: string;
  agencyLineName?: string;
  assignedAt?: string;
  assigneeId?: string;
  assigneeName?: string;
  balance?: number;
  businessManagerId?: string;
  businessManagerName?: string;
  channelName?: string;
  createdAt: string;
  cumulativeSpend?: number;
  currency?: string;
  exceptionAt?: string;
  exceptionPreviousResourceStatus?: MediaResourceStatus;
  exceptionReason?: string;
  id: string;
  inboundAt?: string;
  lastSyncedAt?: string;
  legalEntityName?: string;
  name: string;
  notes?: string;
  platform: MediaPlatform;
  platformStatus: MediaPlatformStatus;
  projectId?: string;
  projectName?: string;
  resourceStatus: MediaResourceStatus;
  spendCap?: number;
  tags: string[];
  teamId?: string;
  teamName?: string;
  timezone?: string;
  todaySpend?: number;
  updatedAt: string;
  whitelistStatus?: MediaWhitelistStatus;
}

export interface ResourceApplication {
  applicationNo: string;
  approvedAccountIds: string[];
  assigneeId?: string;
  assigneeName?: string;
  createdAt: string;
  expectedReturnAt?: string;
  id: string;
  platform: MediaPlatform;
  projectId: string;
  projectName: string;
  reason: string;
  rejectedReason?: string;
  requestedAccountCount: number;
  requestedById: string;
  requestedByName: string;
  reviewedAt?: string;
  reviewedById?: string;
  reviewedByName?: string;
  /** Stable back-reference to the generic approval request, if any. */
  sourceApplicationId?: string;
  sourceTaskId?: string;
  status: ResourceApplicationStatus;
  teamId: string;
  teamName: string;
  timezone?: string;
  title: string;
  updatedAt: string;
  whitelistRequired?: boolean;
}

export interface ResourceAssignment {
  applicationId: string;
  assignedAt: string;
  assignedById: string;
  assignedByName: string;
  assigneeId: string;
  assigneeName: string;
  id: string;
  mediaAccountId: string;
  platformAccountId: string;
  projectId: string;
  projectName: string;
  returnedAt?: string;
  status: ResourceAssignmentStatus;
  teamId: string;
  teamName: string;
  updatedAt: string;
}

export interface ResourceReturn {
  accountName: string;
  completedAt?: string;
  completedById?: string;
  completedByName?: string;
  id: string;
  mediaAccountId: string;
  platformAccountId: string;
  projectId: string;
  projectName: string;
  reason: string;
  requestedAt: string;
  requestedById: string;
  requestedByName: string;
  resourceAssignmentId: string;
  status: ResourceReturnStatus;
  updatedAt: string;
}

export type MediaAuditAction =
  | 'account.created'
  | 'application.approved'
  | 'application.created'
  | 'application.rejected'
  | 'demo.reset'
  | 'exception.marked'
  | 'exception.resolved'
  | 'return.completed'
  | 'return.requested';

export interface MediaAuditLog {
  action: MediaAuditAction;
  actorId: string;
  actorName: string;
  after?: Record<string, unknown>;
  before?: Record<string, unknown>;
  createdAt: string;
  entityId: string;
  entityType: 'account' | 'application' | 'demo' | 'return';
  id: string;
  message: string;
  metadata?: Record<string, unknown>;
  result: 'failed' | 'success';
}

export interface CreateMediaAccountInput {
  accountId: string;
  agencyLineId?: string;
  agencyLineName?: string;
  balance?: number;
  businessManagerId?: string;
  businessManagerName?: string;
  channelName?: string;
  cumulativeSpend?: number;
  currency?: string;
  legalEntityName?: string;
  name: string;
  notes?: string;
  platform: MediaPlatform;
  platformStatus?: MediaPlatformStatus;
  resourceStatus?: MediaResourceStatus;
  spendCap?: number;
  tags?: string[];
  timezone?: string;
  todaySpend?: number;
  whitelistStatus?: MediaWhitelistStatus;
}

export interface CreateResourceApplicationInput {
  assigneeId?: string;
  assigneeName?: string;
  expectedReturnAt?: string;
  platform: MediaPlatform;
  projectId: string;
  projectName: string;
  reason: string;
  requestedAccountCount: number;
  requestedById: string;
  requestedByName: string;
  sourceApplicationId?: string;
  sourceTaskId?: string;
  teamId: string;
  teamName: string;
  timezone?: string;
  title?: string;
  whitelistRequired?: boolean;
}

export interface ExceptionActionOptions {
  actor?: AuditActor;
  platformStatus?: MediaPlatformStatus;
}

/** The five persisted legacy arrays are retained outside this domain. */
export interface ResourceLifecycleState {
  accounts: MediaAccount[];
  applications: ResourceApplication[];
  assignments: ResourceAssignment[];
  returns: ResourceReturn[];
}

export interface ResourceLifecycleClock {
  createId(prefix: string): string;
  now(): string;
}

export interface ResourceLifecycleAudit {
  action: Exclude<MediaAuditAction, 'demo.reset'>;
  after?: Record<string, unknown>;
  before?: Record<string, unknown>;
  entityId: string;
  entityType: 'account' | 'application' | 'return';
  message: string;
  metadata?: Record<string, unknown>;
}

export interface ResourceLifecycleTransition<T> {
  audit: ResourceLifecycleAudit;
  result: T;
  state: ResourceLifecycleState;
}
