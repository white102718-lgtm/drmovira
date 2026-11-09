import type { TaskActivityAdapter } from '../adapter';
import type {
  TaskActivityEvent,
  TaskActivityLevel,
  TaskActivityQuery,
} from '../types';

import type { AsyncTask, AsyncTaskStatus } from '#/api';

export interface GlobalTaskActivityAdapterOptions {
  tasks: () => readonly AsyncTask[];
}

const STATUS_META: Readonly<
  Record<
    AsyncTaskStatus,
    {
      description: string;
      icon: string;
      label: string;
      level: TaskActivityLevel;
    }
  >
> = {
  cancel_requested: {
    description: '已请求取消，等待任务平台确认。',
    icon: 'lucide:circle-pause',
    label: '取消确认中',
    level: 'medium',
  },
  cancelled: {
    description: '任务已取消。',
    icon: 'lucide:circle-x',
    label: '已取消',
    level: 'low',
  },
  failed: {
    description: '任务执行失败，需要处理。',
    icon: 'lucide:triangle-alert',
    label: '失败',
    level: 'high',
  },
  partial_success: {
    description: '任务部分成功，需要复核结果。',
    icon: 'lucide:circle-alert',
    label: '部分成功',
    level: 'high',
  },
  queued: {
    description: '任务已进入执行队列。',
    icon: 'lucide:clock-3',
    label: '排队中',
    level: 'low',
  },
  refund_pending: {
    description: '退款正在处理中。',
    icon: 'lucide:wallet-cards',
    label: '退款处理中',
    level: 'medium',
  },
  refunded: {
    description: '退款已完成。',
    icon: 'lucide:badge-dollar-sign',
    label: '已退款',
    level: 'low',
  },
  running: {
    description: '任务正在执行。',
    icon: 'lucide:loader-circle',
    label: '执行中',
    level: 'low',
  },
  success: {
    description: '任务已成功完成。',
    icon: 'lucide:circle-check-big',
    label: '已完成',
    level: 'low',
  },
};

function eventsForTask(task: AsyncTask): TaskActivityEvent[] {
  const statusMeta = STATUS_META[task.status];
  return [
    {
      description: '创建了异步任务。',
      eventKind: 'created',
      icon: 'lucide:plus-circle',
      id: `task-activity:async-created:${task.id}`,
      level: 'low',
      occurredAt: task.createdAt,
      platform: task.platform,
      progress: 0,
      projectId: task.projectId,
      sourceId: task.id,
      sourceType: 'async-task',
      state: 'created',
      targetPath: '/fusion/ai-tasks',
      title: task.title,
    },
    {
      description: statusMeta.description,
      eventKind: 'async-status',
      icon: statusMeta.icon,
      id: `task-activity:async-status:${task.id}`,
      level: statusMeta.level,
      occurredAt: task.updatedAt,
      platform: task.platform,
      progress: task.progress,
      projectId: task.projectId,
      sourceId: task.id,
      sourceType: 'async-task',
      state: task.status,
      targetPath: '/fusion/ai-tasks',
      title: task.title,
    },
  ];
}

/** Existing async-task API/store is an additional read source, never an owner. */
export class GlobalTaskActivityAdapter implements TaskActivityAdapter {
  constructor(private readonly options: GlobalTaskActivityAdapterOptions) {}

  listEvents(
    query: Omit<TaskActivityQuery, 'limit' | 'workspaceTodos'>,
  ): readonly TaskActivityEvent[] {
    const projectId = query.projectId?.trim();
    return this.options
      .tasks()
      .filter((task) => !projectId || task.projectId === projectId)
      .flatMap((task) => eventsForTask(task));
  }
}
