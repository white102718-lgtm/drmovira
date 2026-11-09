import type { WorkflowRuntimeAdapter } from './adapter';
import type {
  WorkflowRuntimeAction,
  WorkflowRuntimeActor,
  WorkflowRuntimeState,
} from './types';

export class WorkflowRuntimeService {
  constructor(private readonly adapter: WorkflowRuntimeAdapter) {}

  async can(
    businessId: string,
    action: WorkflowRuntimeAction,
    actor?: WorkflowRuntimeActor,
  ) {
    const state = await this.getState(businessId, actor);
    return state.allowedActions.some(
      (item) => item.action === action && item.allowed,
    );
  }

  async getState(
    businessId: string,
    actor?: WorkflowRuntimeActor,
  ): Promise<WorkflowRuntimeState> {
    const normalizedId = businessId.trim();
    if (!normalizedId) throw new Error('流程对象缺少稳定 ID');
    const state = await this.adapter.getState(normalizedId, actor);
    if (!state) throw new Error('流程对象不存在或当前用户无权读取');
    return {
      ...state,
      allowedActions: state.allowedActions.map((item) => ({ ...item })),
    };
  }
}
