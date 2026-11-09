import type {
  MaterialDeliverySubmission,
  MaterialDeliverySubmitInput,
  MaterialOrderDeliveryContext,
} from './types';

/**
 * Compatibility boundary around the existing MaterialOrder read/deliver APIs.
 * Uploading continues to use the shared formal upload component and endpoint.
 */
export interface TaskMaterialDeliveryAdapter {
  deliver(
    input: MaterialDeliverySubmitInput,
  ): Promise<MaterialDeliverySubmission>;
  getContext(orderId: string): Promise<MaterialOrderDeliveryContext>;
}
