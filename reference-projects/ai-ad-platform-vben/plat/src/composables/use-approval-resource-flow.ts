import { storeToRefs } from 'pinia';

import {
  ApplicationResourceBridgeService,
  ApplicationService,
  LegacyApplicationStoreAdapter,
} from '#/domain/application';
import { LegacyResourceStoreAdapter, ResourceService } from '#/domain/resource';
import { useMediaResourceStore } from '#/store/media-resource';
import { useResourceApplicationStore } from '#/store/resource-applications';

/**
 * Shared page adapter for the approval → media-resource handoff. Both pages
 * keep the existing Pinia/localStorage owners and only coordinate them through
 * the domain services, so retries remain idempotent.
 */
export function useApprovalResourceFlow() {
  const applicationStore = useResourceApplicationStore();
  const mediaResourceStore = useMediaResourceStore();
  const { applications } = storeToRefs(applicationStore);

  const applicationService = new ApplicationService(
    new LegacyApplicationStoreAdapter({
      applications: () => applications.value,
      remove: applicationStore.removeApplication,
      upsert: applicationStore.upsertApplication,
    }),
  );
  const resourceService = new ResourceService(
    new LegacyResourceStoreAdapter({
      approveApplication: (applicationId, accountIds, actor) =>
        mediaResourceStore.approveApplication(applicationId, accountIds, actor),
      createApplication: (input, actor) =>
        mediaResourceStore.createApplication(input, actor),
      listApplications: () => mediaResourceStore.applications,
      rejectApplication: (applicationId, reason, actor) =>
        mediaResourceStore.rejectApplication(applicationId, reason, actor),
      requestReturn: (assignmentOrAccountId, reason, actor) =>
        mediaResourceStore.requestReturn(assignmentOrAccountId, reason, actor),
    }),
  );
  const bridge = new ApplicationResourceBridgeService(
    applicationService,
    resourceService,
  );

  return {
    applicationService,
    applicationStore,
    applications,
    bridge,
    mediaResourceStore,
    resourceService,
  };
}
