export type WorkflowBusinessType =
  | 'creative-task'
  | 'delivery-task'
  | 'resource-application';

export type WorkflowRuntimeAction =
  | 'accept'
  | 'approve'
  | 'reject'
  | 'submit'
  | 'transfer';

export interface WorkflowActionAvailability {
  action: WorkflowRuntimeAction;
  allowed: boolean;
  reason?: string;
}

/** Read-only runtime fact. It never owns task or approval mutations. */
export interface WorkflowRuntimeState {
  allowedActions: WorkflowActionAvailability[];
  businessId: string;
  businessType: WorkflowBusinessType;
  currentNodeId?: string;
}

export interface WorkflowRuntimeActor {
  id?: string;
  name?: string;
}
