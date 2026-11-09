import { LegacyDeliverySourceAdapter } from './adapters/legacy';
import { DeliverySourceService, DeliveryWorkflowService } from './service';

export type { DeliverySourceAdapter } from './adapter';
export { LegacyDeliverySourceAdapter } from './adapters/legacy';
export { DeliverySourceService, DeliveryWorkflowService } from './service';
export type * from './types';

/**
 * First task-domain slice. It intentionally reads through the legacy endpoint
 * and leaves existing task-center routes and local-storage records untouched.
 */
export const deliverySourceService = new DeliverySourceService(
  new LegacyDeliverySourceAdapter(),
);

export const deliveryWorkflowService = new DeliveryWorkflowService();
