import type {
  CreateMaterialTaskContext,
  DeliveryTaskSnapshot,
  MaterialOrderWriteResult,
  TaskAssignment,
  TaskAssignmentProjection,
  TaskDeliverableProjection,
  TaskDeliverableSubmitInput,
  TaskSourceRelation,
} from './types';

import type { CreateOrderParams } from '#/api/requirement';

/** Read-only facade over the existing TaskCenter Pinia store. */
export interface TaskReaderAdapter {
  getDeliveryTask(
    id: string,
  ):
    | DeliveryTaskSnapshot
    | Promise<DeliveryTaskSnapshot | undefined>
    | undefined;
}

/**
 * Compatibility facade over the established `material-orders` endpoint.
 * No new endpoint is introduced by this first task-domain slice.
 */
export interface RequirementTaskAdapter {
  create(
    payload: CreateOrderParams,
    context?: CreateMaterialTaskContext,
  ): Promise<MaterialOrderWriteResult>;
  update(
    orderId: string,
    payload: CreateOrderParams,
    context?: CreateMaterialTaskContext,
  ): Promise<MaterialOrderWriteResult>;
}

/** Demo-only bridge. Formal API success remains the authoritative relation. */
export interface TaskSourceRelationAdapter {
  listBySourceTask(
    sourceTaskId: string,
  ): Promise<TaskSourceRelation[]> | TaskSourceRelation[];
  save(
    relation: TaskSourceRelation,
  ): Promise<TaskSourceRelation> | TaskSourceRelation;
}

/**
 * Additive persistence boundary for stable task participants. Legacy task
 * fields remain owned by their existing store/API and are only projected.
 */
export interface TaskAssignmentAdapter {
  getTaskAssignmentProjection(
    taskId: string,
  ):
    | Promise<TaskAssignmentProjection | undefined>
    | TaskAssignmentProjection
    | undefined;
  replaceTaskAssignments(
    taskId: string,
    assignments: readonly TaskAssignment[],
  ):
    | Promise<TaskAssignmentProjection | undefined>
    | TaskAssignmentProjection
    | undefined;
}

/** Bridges the existing completion state without adding a parallel task key. */
export interface TaskDeliverableAdapter {
  acceptDeliverable(
    taskId: string,
    reviewer: { id?: string; name: string },
    comment?: string,
  ):
    | Promise<TaskDeliverableProjection | undefined>
    | TaskDeliverableProjection
    | undefined;
  getTaskDeliverableProjection(
    taskId: string,
  ):
    | Promise<TaskDeliverableProjection | undefined>
    | TaskDeliverableProjection
    | undefined;
  rejectDeliverable(
    taskId: string,
    reviewer: { id?: string; name: string },
    comment: string,
  ):
    | Promise<TaskDeliverableProjection | undefined>
    | TaskDeliverableProjection
    | undefined;
  submitDeliverable(
    input: TaskDeliverableSubmitInput,
  ):
    | Promise<TaskDeliverableProjection | undefined>
    | TaskDeliverableProjection
    | undefined;
}
