import type { TaskActivityAdapter } from './adapter';
import type {
  ProjectStageActivitySummary,
  TaskActivityEvent,
  TaskActivityQuery,
  TaskActivityReadModel,
  TaskActivityTodo,
} from './types';

const ACTIONABLE_STATES = new Set([
  'assigned_pending_confirmation',
  'cancel_requested',
  'doing',
  'failed',
  'partial_success',
  'pending',
  'pending_acceptance',
  'pending_assignment',
  'queued',
  'refund_pending',
  'risk',
  'running',
]);

function cloneEvent(event: TaskActivityEvent): TaskActivityEvent {
  return { ...event };
}

function timestamp(value?: string): number {
  if (!value) return 0;
  const result = Date.parse(value);
  return Number.isNaN(result) ? 0 : result;
}

function sortEvents(events: readonly TaskActivityEvent[]) {
  return [...events].sort((left, right) => {
    const difference = timestamp(right.occurredAt) - timestamp(left.occurredAt);
    if (difference !== 0) return difference;
    return left.id.localeCompare(right.id);
  });
}

function toTodo(event: TaskActivityEvent): TaskActivityTodo {
  return {
    description: event.description,
    id: `task-activity:todo:${event.id}`,
    level: event.level,
    sourceId: event.sourceId,
    targetPath: event.targetPath,
    title: event.title,
  };
}

function projectStages(
  events: readonly TaskActivityEvent[],
): ProjectStageActivitySummary[] {
  const currentStages = events.filter(
    (event) =>
      event.eventKind === 'stage-snapshot' ||
      event.eventKind === 'async-status',
  );
  const count = (states: readonly string[]) =>
    currentStages.filter((event) => states.includes(event.state)).length;
  return [
    {
      description: '待分配、待确认或待处理的任务',
      id: 'intake',
      label: '需求与分配',
      value: count([
        'assigned_pending_confirmation',
        'pending',
        'pending_assignment',
      ]),
    },
    {
      description: '正在处理、排队或执行中的任务',
      id: 'execution',
      label: '执行中',
      value: count(['doing', 'queued', 'risk', 'running']),
    },
    {
      description: '已提交、等待验收的交付',
      id: 'acceptance',
      label: '交付验收',
      value: count(['pending_acceptance']),
    },
    {
      description: '任务或异步作业已完成',
      id: 'completed',
      label: '完成',
      value: count(['done', 'success']),
    },
  ];
}

function normalizeLimit(query: TaskActivityQuery): number {
  const limit = query.limit ?? 24;
  if (!Number.isInteger(limit) || limit < 1 || limit > 200) {
    throw new Error('活动列表条数必须在 1 到 200 之间');
  }
  return limit;
}

function createReadModel(
  query: TaskActivityQuery,
  results: readonly (readonly TaskActivityEvent[])[],
): TaskActivityReadModel {
  const limit = normalizeLimit(query);
  const events = sortEvents(results.flatMap((items) => [...items])).slice(
    0,
    limit,
  );
  const workspaceTodos = query.workspaceTodos ?? [];
  const todos = [
    ...workspaceTodos.map((todo) => ({
      ...todo,
      id: `task-activity:workspace-todo:${todo.id}`,
      sourceId: todo.id,
    })),
    ...events
      .filter((event) => ACTIONABLE_STATES.has(event.state))
      .map((event) => toTodo(event)),
  ];
  const uniqueTodos = new Map<string, TaskActivityTodo>();
  for (const todo of todos) uniqueTodos.set(todo.id, { ...todo });
  return {
    events: events.map((event) => cloneEvent(event)),
    projectStages: projectStages(events),
    todos: [...uniqueTodos.values()],
  };
}

function adapterInput(query: TaskActivityQuery) {
  return {
    projectId: query.projectId?.trim() || undefined,
    viewer: query.viewer,
  };
}

function isPromiseLike<T>(
  value: Promise<T> | readonly TaskActivityEvent[],
): value is Promise<T> {
  return typeof (value as Promise<T>).then === 'function';
}

/**
 * Joins existing task/job read sources into a presentation model. It is
 * intentionally read-only: TaskCenter and the async-task API remain writers.
 */
export class TaskActivityService {
  constructor(private readonly adapters: readonly TaskActivityAdapter[]) {}

  async read(query: TaskActivityQuery = {}): Promise<TaskActivityReadModel> {
    normalizeLimit(query);
    const results = await Promise.all(
      this.adapters.map((adapter) => adapter.listEvents(adapterInput(query))),
    );
    return createReadModel(query, results);
  }

  /**
   * For reactive legacy stores. Do not use this with a future HTTP event
   * adapter; callers that need HTTP must await `read()` instead.
   */
  readSync(query: TaskActivityQuery = {}): TaskActivityReadModel {
    const results = this.adapters.map((adapter) =>
      adapter.listEvents(adapterInput(query)),
    );
    const syncResults: TaskActivityEvent[][] = [];
    for (const result of results) {
      if (isPromiseLike(result)) {
        throw new Error('当前活动数据源为异步读取，请使用 read()');
      }
      syncResults.push([...result]);
    }
    return createReadModel(query, syncResults);
  }
}
