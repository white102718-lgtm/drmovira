import { LegacyTaskMaterialDeliveryAdapter } from './adapters/legacy';
import { TaskMaterialDeliveryService } from './service';

export type { TaskMaterialDeliveryAdapter } from './adapter';
export { LegacyTaskMaterialDeliveryAdapter } from './adapters/legacy';
export { TaskMaterialDeliveryService } from './service';
export type * from './types';

/**
 * Additive compatibility facade for Task Center material delivery. Existing
 * MaterialOrder routes, APIs, and upload persistence stay authoritative.
 */
export const taskMaterialDeliveryService = new TaskMaterialDeliveryService(
  new LegacyTaskMaterialDeliveryAdapter(),
);
