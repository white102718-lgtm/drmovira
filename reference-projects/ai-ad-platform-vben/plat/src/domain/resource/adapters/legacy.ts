import type {
  ResourceCommandAdapter,
  ResourceLifecycleAdapter,
} from '../adapter';
import type {
  AuditActor,
  CreateResourceApplicationInput,
  ResourceApplication,
  ResourceLifecycleState,
  ResourceReturn,
} from '../types';

function clone(state: ResourceLifecycleState): ResourceLifecycleState {
  return JSON.parse(JSON.stringify(state)) as ResourceLifecycleState;
}

function cloneApplication(application: ResourceApplication) {
  return JSON.parse(JSON.stringify(application)) as ResourceApplication;
}

/**
 * Keeps the five historical `fusion:media-resource:*` arrays untouched. Old
 * assignments may carry only the platform account ID, so repair that link only
 * when it is unambiguous; names are deliberately never used as a fallback.
 */
export class LegacyResourceLifecycleAdapter
  implements ResourceLifecycleAdapter
{
  normalize(state: ResourceLifecycleState): ResourceLifecycleState {
    const normalized = clone(state);
    const accountsByExternalId = new Map<string, string[]>();
    for (const account of normalized.accounts) {
      const ids = accountsByExternalId.get(account.accountId) ?? [];
      ids.push(account.id);
      accountsByExternalId.set(account.accountId, ids);
    }

    normalized.assignments = normalized.assignments.map((assignment) => {
      if (
        normalized.accounts.some(
          (account) => account.id === assignment.mediaAccountId,
        )
      ) {
        return assignment;
      }
      const matchedIds =
        accountsByExternalId.get(assignment.platformAccountId) ?? [];
      const [matchedId] = matchedIds;
      return matchedId && matchedIds.length === 1
        ? { ...assignment, mediaAccountId: matchedId }
        : assignment;
    });

    normalized.applications = normalized.applications.map((application) => ({
      ...application,
      approvedAccountIds: [
        ...new Set(
          application.approvedAccountIds.flatMap((id) => {
            if (normalized.accounts.some((account) => account.id === id))
              return [id];
            const matchedIds = accountsByExternalId.get(id) ?? [];
            return matchedIds.length === 1 ? matchedIds : [id];
          }),
        ),
      ],
    }));
    return normalized;
  }
}

export interface LegacyResourceStoreAdapterOptions {
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

/** Page-safe command facade over the existing Pinia lifecycle mutations. */
export class LegacyResourceStoreAdapter implements ResourceCommandAdapter {
  constructor(private readonly options: LegacyResourceStoreAdapterOptions) {}

  approveApplication(
    applicationId: string,
    accountIds: string[],
    actor: AuditActor,
  ) {
    return this.options.approveApplication(applicationId, accountIds, actor);
  }

  createApplication(input: CreateResourceApplicationInput, actor: AuditActor) {
    return this.options.createApplication(input, actor);
  }

  listApplications() {
    return this.options
      .listApplications()
      .map((application) => cloneApplication(application));
  }

  rejectApplication(applicationId: string, reason: string, actor: AuditActor) {
    return this.options.rejectApplication(applicationId, reason, actor);
  }

  requestReturn(
    assignmentOrAccountId: string,
    reason: string,
    actor: AuditActor,
  ) {
    return this.options.requestReturn(assignmentOrAccountId, reason, actor);
  }
}
