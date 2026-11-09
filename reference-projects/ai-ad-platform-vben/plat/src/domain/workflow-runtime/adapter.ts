import type { WorkflowRuntimeActor, WorkflowRuntimeState } from './types';

export interface WorkflowRuntimeAdapter {
  getState(
    businessId: string,
    actor?: WorkflowRuntimeActor,
  ):
    | Promise<undefined | WorkflowRuntimeState>
    | undefined
    | WorkflowRuntimeState;
}
