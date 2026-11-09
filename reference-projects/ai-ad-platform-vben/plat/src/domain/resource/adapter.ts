import type {
  AuditActor,
  CreateResourceApplicationInput,
  ResourceApplication,
  ResourceLifecycleState,
  ResourceReturn,
} from './types';

/**
 * Read compatibility boundary for the original media-resource raw arrays.
 * A future HTTP adapter can replace this without changing the lifecycle rules.
 */
export interface ResourceLifecycleAdapter {
  normalize(state: ResourceLifecycleState): ResourceLifecycleState;
}

/**
 * Command boundary over the existing media-resource Store. It deliberately
 * retains its five raw-array keys and lifecycle audit trail during migration.
 */
export interface ResourceCommandAdapter {
  approveApplication(
    applicationId: string,
    accountIds: string[],
    actor: AuditActor,
  ): readonly string[];
  createApplication(
    input: CreateResourceApplicationInput,
    actor: AuditActor,
  ): ResourceApplication;
  listApplications(): readonly ResourceApplication[];
  rejectApplication(
    applicationId: string,
    reason: string,
    actor: AuditActor,
  ): ResourceApplication;
  requestReturn(
    assignmentOrAccountId: string,
    reason: string,
    actor: AuditActor,
  ): ResourceReturn;
}
