/**
 * File facts produced by the existing material-order upload endpoint. These
 * fields deliberately mirror the legacy delivery payload so the task domain
 * never invents a local object key, hash, or media dimension.
 */
export interface MaterialDeliveryFile {
  basename: string;
  contentType: string;
  duration: number;
  fileMd5: string;
  filetype: string;
  height: number;
  id: string;
  img: string;
  name: string;
  objectKey: string;
  sha3_256: string;
  size: number;
  url: string;
  width: number;
}

export interface MaterialDeliveryRequirementOption {
  designer?: string;
  creativePlanner?: string;
  remark?: string;
  label: string;
  value: string;
}

/** Read-only MaterialOrder context used to open the shared upload dialog. */
export interface MaterialOrderDeliveryContext {
  demandType: string;
  orderId: string;
  assignmentOptions: MaterialDeliveryRequirementOption[];
  status: string;
  title: string;
}

export interface MaterialDeliverySubmitInput {
  creativePlanner?: string;
  designer?: string;
  files: readonly MaterialDeliveryFile[];
  orderId: string;
  assignmentId?: string;
}

/**
 * A versioned delivery attempt. `formalDeliveryId` and `formalVersionNo` are
 * intentionally optional: the old endpoint has no documented response
 * contract for them, so the frontend must not manufacture stable IDs.
 */
export interface MaterialDeliverySubmission {
  creativePlanner?: string;
  designer?: string;
  files: MaterialDeliveryFile[];
  formalDeliveryId?: string;
  formalVersionNo?: number;
  orderId: string;
  assignmentId?: string;
  status: 'pending_accept';
  submittedAt: string;
}
