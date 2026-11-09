import type { WorkflowRuntimeAdapter } from '../adapter';
import type {
  WorkflowActionAvailability,
  WorkflowRuntimeActor,
  WorkflowRuntimeState,
} from '../types';

import type { TaskCenterTask } from '#/store/task-center';

export interface TaskCenterWorkflowRuntimeAdapterOptions {
  tasks: () => readonly TaskCenterTask[];
}

function hasAction(
  actions: readonly WorkflowActionAvailability[],
  action: WorkflowActionAvailability['action'],
) {
  return actions.some((item) => item.action === action && item.allowed);
}

function isTaskReviewer(task: TaskCenterTask, actor?: WorkflowRuntimeActor) {
  const actorId = actor?.id?.trim();
  const actorName = actor?.name?.trim();
  if (actorId) {
    if (task.ownerId === actorId) return true;
    return Boolean(
      task.assignments?.some(
        (assignment) =>
          assignment.assigneeId === actorId && assignment.role === 'owner',
      ),
    );
  }
  // Name comparison remains only for records that do not yet have a stable
  // owner ID. It is a compatibility read, never a user-ID lookup.
  return Boolean(
    actorName &&
      !task.ownerId &&
      [task.createdBy, task.owner].includes(actorName),
  );
}

function businessTypeFor(
  task: TaskCenterTask,
): WorkflowRuntimeState['businessType'] {
  if (task.kind === 'am') return 'delivery-task';
  if (task.kind === 'material') return 'creative-task';
  return 'resource-application';
}

function nodeFor(task: TaskCenterTask) {
  if (task.status === 'pending_acceptance') return 'acceptance';
  if (task.status === 'done') return 'completed';
  if (task.status === 'withdrawn') return 'withdrawn';
  return 'execution';
}

export class TaskCenterWorkflowRuntimeAdapter
  implements WorkflowRuntimeAdapter
{
  constructor(
    private readonly options: TaskCenterWorkflowRuntimeAdapterOptions,
  ) {}

  can(
    businessId: string,
    action: WorkflowActionAvailability['action'],
    actor?: WorkflowRuntimeActor,
  ) {
    const state = this.getState(businessId, actor);
    return state ? hasAction(state.allowedActions, action) : false;
  }

  getState(
    businessId: string,
    actor?: WorkflowRuntimeActor,
  ): undefined | WorkflowRuntimeState {
    const task = this.options.tasks().find((item) => item.id === businessId);
    if (!task) return;
    const canReview =
      task.status === 'pending_acceptance' &&
      Boolean(task.completion?.current) &&
      isTaskReviewer(task, actor);
    const canSubmit = !['done', 'pending_acceptance', 'withdrawn'].includes(
      task.status,
    );
    const allowedActions: WorkflowActionAvailability[] = [
      {
        action: 'submit',
        allowed: canSubmit,
        reason: canSubmit ? undefined : '当前节点不允许继续提交交付',
      },
      {
        action: 'accept',
        allowed: canReview,
        reason: canReview
          ? undefined
          : '当前用户不具备验收权限或任务未进入验收节点',
      },
      {
        action: 'reject',
        allowed: canReview,
        reason: canReview
          ? undefined
          : '当前用户不具备打回权限或任务未进入验收节点',
      },
    ];
    return {
      allowedActions,
      businessId: task.id,
      businessType: businessTypeFor(task),
      currentNodeId: nodeFor(task),
    };
  }
}
