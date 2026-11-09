/**
 * A source reference is intentionally additive. Existing task records can
 * omit it and continue to use their legacy `sourceId` semantics.
 */
export interface TaskSourceRef {
  id: string;
  kind: 'delivery-task' | 'manual' | 'material-order';
}

export interface CreateMaterialTaskContext {
  projectId: string;
  requesterId: string;
  requesterName: string;
  sourceTaskId: string;
}

/** Context passed from a DeliveryTask into a resource application. */
export interface CreateResourceApplicationContext {
  projectId: string;
  projectName: string;
  requesterId: string;
  requesterName: string;
  sourceTaskId: string;
}

export interface DeliveryTaskSnapshot {
  id: string;
  kind: 'am';
  project: string;
  projectId: string;
  status: string;
  title: string;
}

export interface TaskSourceRelation {
  createdAt: string;
  materialOrderId: string;
  projectId: string;
  requesterId: string;
  requesterName: string;
  sourceTaskId: string;
  updatedAt: string;
}

/**
 * A task is still a single business record. People are attached to it through
 * stable user IDs, so duplicated display names can never collapse into one
 * assignee during the migration from legacy name arrays.
 */
export type TaskAssignmentRole = 'executor' | 'observer' | 'owner' | 'reviewer';

export type TaskAssignmentStatus =
  | 'cancelled'
  | 'doing'
  | 'done'
  | 'pending'
  | 'submitted';

export interface TaskAssignment {
  /** An owner may explicitly take part in delivery without a second row. */
  alsoExecutor?: boolean;
  assigneeId: string;
  assigneeName: string;
  departmentId?: string;
  dueAt?: string;
  id: string;
  progress: number;
  role: TaskAssignmentRole;
  status: TaskAssignmentStatus;
  taskId: string;
  /** Delivery team codes are metadata, not a substitute for the user ID. */
  teamCodes?: string[];
}

export interface TaskAssignmentInput {
  alsoExecutor?: boolean;
  assigneeId: string;
  assigneeName: string;
  departmentId?: string;
  dueAt?: string;
  progress?: number;
  role: TaskAssignmentRole;
  status?: TaskAssignmentStatus;
  teamCode?: string;
}

/** Names which cannot be resolved to a stable ID remain visible but inert. */
export interface UnresolvedLegacyTaskParticipant {
  name: string;
  role: TaskAssignmentRole;
  source: string;
  status?: TaskAssignmentStatus;
}

export interface TaskAssignmentProjection {
  assignments: TaskAssignment[];
  unresolvedLegacyParticipants: UnresolvedLegacyTaskParticipant[];
}

export interface TaskAssignmentUpdateResult extends TaskAssignmentProjection {
  /** Keeps the parent task state intact while exposing mixed executor state. */
  completionState: 'all_done' | 'partially_completed' | 'pending';
}

/** Immutable item fact within one submitted task deliverable version. */
export interface DeliverableItem {
  id: string;
  name: string;
  objectKey?: string;
  size?: number;
  type?: string;
  url?: string;
}

export type TaskDeliverableStatus =
  | 'accepted'
  | 'rejected'
  | 'submitted'
  | 'superseded';

/**
 * Read model for a concrete submission. `legacyDerived` makes it explicit
 * when an old submissionId is used because no formal deliverable entity exists
 * yet in the server response.
 */
export interface TaskDeliverable {
  assignmentId?: string;
  id: string;
  items: DeliverableItem[];
  legacyDerived: boolean;
  note?: string;
  status: TaskDeliverableStatus;
  submittedAt: string;
  submittedBy: string;
  taskId: string;
  version: number;
}

export interface AcceptanceRecord {
  actedAt: string;
  comment: string;
  deliverableId: string;
  id: string;
  legacyDerived: boolean;
  result: 'accepted' | 'rejected';
  reviewerId?: string;
  reviewerName: string;
  taskId: string;
}

export interface TaskDeliverableProjection {
  acceptanceRecords: AcceptanceRecord[];
  deliverables: TaskDeliverable[];
}

export interface TaskDeliverableSubmitInput {
  /** Existing TaskCenter submission payload; kept structurally opaque here. */
  legacyInput: unknown;
  taskId: string;
}

export type MaterialOrderSourceLinkState =
  | 'legacy-unlinked'
  | 'linked'
  | 'manual'
  | 'missing-order-id';

export interface MaterialOrderWriteResult {
  materialOrderId?: string;
  response: unknown;
  sourceLinkState: MaterialOrderSourceLinkState;
  taskCenterTaskCode?: string;
  taskCenterTaskId?: string;
}

export type MaterialTaskSourceQuery =
  | { kind: 'invalid'; reason: string }
  | {
      kind: 'linked';
      projectId: string;
      sourceTaskId: string;
    }
  | { kind: 'manual' };
