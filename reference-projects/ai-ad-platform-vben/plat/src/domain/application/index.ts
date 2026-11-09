import { LegacyApplicationAdapter } from './adapters/legacy';
import {
  ApplicationFormSchemaService,
  ApplicationWorkflowService,
} from './service';

export {
  ACCOUNT_OPENING_APPLICATION_CODE,
  ACCOUNT_OPENING_ASSET_TYPE,
  createAccountOpeningFormSchema,
  createAccountOpeningHandlerAction,
  normalizeAccountOpeningFormSchema,
} from './account-opening';
export type {
  ApplicationAdapter,
  ApplicationPersistenceAdapter,
} from './adapter';
export {
  LegacyApplicationAdapter,
  LegacyApplicationStoreAdapter,
} from './adapters/legacy';
export {
  createDynamicFieldInitialValue,
  DEFAULT_SELECT_PLACEHOLDER,
  resolveDynamicFieldPlaceholder,
} from './dynamic-form';
export { ApplicationResourceBridgeService } from './resource-bridge';
export {
  ApplicationFormSchemaService,
  ApplicationService,
  ApplicationWorkflowService,
} from './service';
export {
  matchesSocialInventoryAsset,
  resolveSocialAssetSelection,
  SOCIAL_ASSET_TYPE_OPTIONS,
} from './social-assets';
export type * from './types';
export {
  applicationTypeLabels,
  approvalRoleForType,
  approvalRoleMeta,
} from './types';

/**
 * Compatibility-only adapter: it normalizes the existing Store payload while
 * retaining the legacy `adpulse-workbench-resource-applications` raw array.
 */
export const legacyApplicationAdapter = new LegacyApplicationAdapter();
export const applicationWorkflowService = new ApplicationWorkflowService();
export const applicationFormSchemaService = new ApplicationFormSchemaService(
  legacyApplicationAdapter,
);
