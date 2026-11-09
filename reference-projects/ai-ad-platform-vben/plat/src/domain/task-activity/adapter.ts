import type { TaskActivityEvent, TaskActivityQuery } from './types';

/** A source adapter only reads existing task/job facts; it never writes them. */
export interface TaskActivityAdapter {
  listEvents(
    query: Omit<TaskActivityQuery, 'limit' | 'workspaceTodos'>,
  ): Promise<readonly TaskActivityEvent[]> | readonly TaskActivityEvent[];
}
