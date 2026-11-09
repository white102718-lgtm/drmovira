import { LegacyResourceLifecycleAdapter } from './adapters/legacy';
import { ResourceLifecycleService } from './service';

export type {
  ResourceCommandAdapter,
  ResourceLifecycleAdapter,
} from './adapter';
export {
  LegacyResourceLifecycleAdapter,
  LegacyResourceStoreAdapter,
} from './adapters/legacy';
export { ResourceLifecycleService, ResourceService } from './service';
export type * from './types';

export const legacyResourceLifecycleAdapter =
  new LegacyResourceLifecycleAdapter();
export const resourceLifecycleService = new ResourceLifecycleService();
