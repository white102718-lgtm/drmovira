import type { WorkflowRuntimeAdapter } from '../adapter';
import type { WorkflowRuntimeActor, WorkflowRuntimeState } from '../types';

import type { ResourceApplication } from '#/domain/application';

export interface ApplicationWorkflowRuntimeAdapterOptions {
  applications: () => readonly ResourceApplication[];
}

function currentNode(application: ResourceApplication) {
  return application.approvalNodes.find((node) => node.status === 'pending');
}

function actorCanHandle(
  application: ResourceApplication,
  actor?: WorkflowRuntimeActor,
) {
  const node = currentNode(application);
  if (!node) return false;
  const actorId = actor?.id?.trim();
  if (node.approverId) return actorId === node.approverId;
  // Historic nodes lack an approver ID. This is a display-name compatibility
  // read only; it never turns a name into a stable user relation.
  return Boolean(!node.approverId && actor?.name?.trim() === node.approver);
}

function stateFor(application: ResourceApplication) {
  if (application.status === 'approved') return 'completed';
  if (application.status === 'rejected') return 'rejected';
  if (application.status === 'draft') return 'draft';
  return currentNode(application)?.id ?? 'processing';
}

/** Read-only projection of the existing application approval nodes. */
export class ApplicationWorkflowRuntimeAdapter
  implements WorkflowRuntimeAdapter
{
  constructor(
    private readonly options: ApplicationWorkflowRuntimeAdapterOptions,
  ) {}

  getState(
    businessId: string,
    actor?: WorkflowRuntimeActor,
  ): undefined | WorkflowRuntimeState {
    const application = this.options
      .applications()
      .find((item) => item.id === businessId);
    if (!application) return;
    const canHandle =
      application.status === 'pending' && actorCanHandle(application, actor);
    return {
      allowedActions: [
        {
          action: 'submit',
          allowed: application.status === 'draft',
          reason:
            application.status === 'draft' ? undefined : '当前申请不能再次提交',
        },
        {
          action: 'approve',
          allowed: canHandle,
          reason: canHandle ? undefined : '当前用户不是本审批节点的稳定审批人',
        },
        {
          action: 'reject',
          allowed: canHandle,
          reason: canHandle ? undefined : '当前用户不是本审批节点的稳定审批人',
        },
        {
          action: 'transfer',
          allowed: canHandle,
          reason: canHandle ? undefined : '当前用户不是本审批节点的稳定审批人',
        },
      ],
      businessId: application.id,
      businessType: 'resource-application',
      currentNodeId: stateFor(application),
    };
  }
}
