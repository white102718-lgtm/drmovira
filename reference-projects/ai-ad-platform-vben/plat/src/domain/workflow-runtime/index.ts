import type { ApplicationWorkflowRuntimeAdapterOptions } from './adapters/application';

import type { TaskCenterTask } from '#/store/task-center';

import { ApplicationWorkflowRuntimeAdapter } from './adapters/application';
import { TaskCenterWorkflowRuntimeAdapter } from './adapters/task-center';
import { WorkflowRuntimeService } from './service';

export type * from './adapter';
export { ApplicationWorkflowRuntimeAdapter } from './adapters/application';
export { TaskCenterWorkflowRuntimeAdapter } from './adapters/task-center';
export { WorkflowRuntimeService } from './service';
export type * from './types';

export function createTaskWorkflowRuntimeService(
  tasks: () => readonly TaskCenterTask[],
) {
  return new WorkflowRuntimeService(
    new TaskCenterWorkflowRuntimeAdapter({ tasks }),
  );
}

export function createApplicationWorkflowRuntimeService(
  applications: ApplicationWorkflowRuntimeAdapterOptions['applications'],
) {
  return new WorkflowRuntimeService(
    new ApplicationWorkflowRuntimeAdapter({ applications }),
  );
}
