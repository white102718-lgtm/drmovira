export type TaskActivityEventKind =
  | 'accepted'
  | 'async-status'
  | 'created'
  | 'delivery-submitted'
  | 'rejected'
  | 'stage-snapshot'
  | 'updated'
  | 'withdrawn';

export type TaskActivityLevel = 'high' | 'low' | 'medium';

export type TaskActivitySourceType =
  | 'async-task'
  | 'delivery-task'
  | 'material-task'
  | 'media-task';

/**
 * A read-only, traceable projection. `id` is deterministic from the source
 * business ID and, where available, its immutable submission/acceptance ID.
 * It is not a replacement for a formal server-side event entity.
 */
export interface TaskActivityEvent {
  actorId?: string;
  actorName?: string;
  description: string;
  eventKind: TaskActivityEventKind;
  icon: string;
  id: string;
  level: TaskActivityLevel;
  occurredAt?: string;
  platform?: string;
  progress?: number;
  projectId: string;
  sourceId: string;
  sourceType: TaskActivitySourceType;
  state: string;
  targetPath: string;
  taskId?: string;
  title: string;
}

export interface TaskActivityTodo {
  description: string;
  id: string;
  level: TaskActivityLevel;
  sourceId: string;
  targetPath: string;
  title: string;
}

export interface TaskActivityTodoSource {
  description: string;
  id: string;
  level: TaskActivityLevel;
  targetPath: string;
  title: string;
}

export interface TaskActivityViewer {
  id?: string;
  name?: string;
  roleCodes: readonly string[];
}

export interface TaskActivityQuery {
  limit?: number;
  projectId?: string;
  viewer?: TaskActivityViewer;
  workspaceTodos?: readonly TaskActivityTodoSource[];
}

export interface ProjectStageActivitySummary {
  description: string;
  id: 'acceptance' | 'completed' | 'execution' | 'intake';
  label: string;
  value: number;
}

export interface TaskActivityReadModel {
  events: readonly TaskActivityEvent[];
  projectStages: readonly ProjectStageActivitySummary[];
  todos: readonly TaskActivityTodo[];
}
