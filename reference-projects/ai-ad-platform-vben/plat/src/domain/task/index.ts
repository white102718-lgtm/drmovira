import type { TaskCenterTaskAdapterOptions } from './adapters/task-center';

import type { TaskCenterTask } from '#/store/task-center';

import { MockTaskSourceRelationAdapter } from './adapters/mock';
import { LegacyRequirementTaskAdapter } from './adapters/requirement';
import { TaskCenterTaskAdapter } from './adapters/task-center';
import { TaskService } from './service';

export type * from './adapter';
export {
  canEditRejectedMaterialOrder,
  canReeditMaterialOrder,
  canResubmitMaterialOrder,
  materialOrderStatusToTaskStatus,
  projectLegacyMaterialOrderTask,
  readLegacyMaterialOrderSummaries,
} from './adapters/material-order-task-center';
export type {
  LegacyMaterialOrderSummary,
  LegacyMaterialOrderTaskProjection,
} from './adapters/material-order-task-center';
export {
  MockTaskSourceRelationAdapter,
  TASK_SOURCE_RELATIONS_STORAGE_KEY,
} from './adapters/mock';
export {
  LegacyRequirementTaskAdapter,
  readMaterialOrderParticipantProjection,
  serializeMaterialOrderParticipants,
} from './adapters/requirement';
export { TaskCenterTaskAdapter } from './adapters/task-center';
export { TaskService } from './service';
export {
  createMaterialTaskContext,
  parseMaterialTaskSourceQuery,
} from './source-context';
export type * from './types';

/**
 * Factory instead of a global store binding: legacy TaskCenter remains the
 * owner and each caller supplies its current reactive task collection.
 */
export function createTaskService(
  tasks: () => readonly TaskCenterTask[],
  options: Omit<TaskCenterTaskAdapterOptions, 'tasks'> = {},
) {
  const useDemoRelations = import.meta.env.VITE_FUSION_DEMO_MODE === 'true';
  const taskCenterAdapter = new TaskCenterTaskAdapter({ ...options, tasks });
  return new TaskService(
    taskCenterAdapter,
    new LegacyRequirementTaskAdapter(),
    useDemoRelations ? new MockTaskSourceRelationAdapter() : undefined,
    taskCenterAdapter,
    taskCenterAdapter,
  );
}
