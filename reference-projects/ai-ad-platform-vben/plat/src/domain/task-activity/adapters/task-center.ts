import type { TaskActivityAdapter } from '../adapter';
import type {
  TaskActivityEvent,
  TaskActivityLevel,
  TaskActivityQuery,
  TaskActivitySourceType,
} from '../types';

import type { TaskCenterStatus, TaskCenterTask } from '#/store/task-center';

export interface TaskCenterActivityAdapterOptions {
  tasks: () => readonly TaskCenterTask[];
}

const ADMIN_ROLE_CODES = new Set(['admin', 'super']);

const STATUS_META: Readonly<
  Record<
    TaskCenterStatus,
    {
      description: string;
      icon: string;
      label: string;
      level: TaskActivityLevel;
    }
  >
> = {
  draft: {
    description: '任务内容已暂存，等待继续编辑并提交。',
    icon: 'lucide:file-pen-line',
    label: '草稿',
    level: 'low',
  },
  assigned_pending_confirmation: {
    description: '任务已分配，等待负责人确认接收。',
    icon: 'lucide:circle-dot-dashed',
    label: '待确认',
    level: 'medium',
  },
  doing: {
    description: '任务正在处理中。',
    icon: 'lucide:clock-3',
    label: '处理中',
    level: 'low',
  },
  partially_completed: {
    description: '部分素材师已完成，仍等待其余素材师交付。',
    icon: 'lucide:circle-dot-dashed',
    label: '部分完成',
    level: 'medium',
  },
  done: {
    description: '任务已完成。',
    icon: 'lucide:circle-check-big',
    label: '已完成',
    level: 'low',
  },
  pending: {
    description: '任务等待处理。',
    icon: 'lucide:inbox',
    label: '待处理',
    level: 'medium',
  },
  pending_assignment: {
    description: '任务等待分配稳定负责人。',
    icon: 'lucide:user-round-plus',
    label: '待分配',
    level: 'high',
  },
  pending_acceptance: {
    description: '交付已提交，等待验收。',
    icon: 'lucide:clipboard-check',
    label: '待验收',
    level: 'high',
  },
  rejected: {
    description: '任务已被驳回，等待根据原因调整。',
    icon: 'lucide:circle-x',
    label: '已驳回',
    level: 'high',
  },
  risk: {
    description: '任务存在超时或风险信号。',
    icon: 'lucide:triangle-alert',
    label: '风险',
    level: 'high',
  },
  withdrawn: {
    description: '任务已撤回。',
    icon: 'lucide:undo-2',
    label: '已撤回',
    level: 'low',
  },
};

function sourceTypeFor(task: TaskCenterTask): TaskActivitySourceType {
  if (task.kind === 'am') return 'delivery-task';
  if (task.kind === 'material') return 'material-task';
  return 'media-task';
}

function hasAllScope(viewer: TaskActivityQuery['viewer']): boolean {
  return Boolean(
    viewer?.roleCodes.some((role) => ADMIN_ROLE_CODES.has(role.toLowerCase())),
  );
}

function canReadTask(
  task: TaskCenterTask,
  viewer: TaskActivityQuery['viewer'],
) {
  if (!viewer || hasAllScope(viewer)) return true;
  const viewerId = viewer.id?.trim();
  const viewerName = viewer.name?.trim();
  const roles = new Set(viewer.roleCodes.map((role) => role.toLowerCase()));

  if (viewerId) {
    if (task.ownerId === viewerId) return true;
    if (task.assignments?.some((item) => item.assigneeId === viewerId)) {
      return true;
    }
  }
  // Compatibility reads use a display name only where the old record has no
  // stable owner id. It never turns a name into a stable user relationship.
  if (viewerName && !task.ownerId && task.owner === viewerName) return true;
  if (viewerName && task.createdBy === viewerName) return true;
  return (
    task.audiences.includes('all') ||
    task.audiences.some((audience) => roles.has(audience.toLowerCase()))
  );
}

function eventTarget(task: TaskCenterTask) {
  return task.route || '/workbench/tasks';
}

function baseEvent(
  task: TaskCenterTask,
  patch: Omit<
    TaskActivityEvent,
    | 'id'
    | 'projectId'
    | 'sourceId'
    | 'sourceType'
    | 'targetPath'
    | 'taskId'
    | 'title'
  >,
): Omit<TaskActivityEvent, 'id'> {
  return {
    ...patch,
    projectId: task.projectId ?? '',
    sourceId: task.id,
    sourceType: sourceTypeFor(task),
    targetPath: eventTarget(task),
    taskId: task.id,
    title: task.title,
  };
}

function eventsForTask(task: TaskCenterTask): TaskActivityEvent[] {
  const statusMeta = STATUS_META[task.status];
  const events: TaskActivityEvent[] = [
    {
      ...baseEvent(task, {
        actorName: task.createdBy,
        description: '创建了任务。',
        eventKind: 'created',
        icon: 'lucide:plus-circle',
        level: 'low',
        occurredAt: task.createdAt,
        platform: undefined,
        progress: 0,
        state: 'created',
      }),
      id: `task-activity:created:${task.id}`,
    },
    {
      ...baseEvent(task, {
        actorId: task.ownerId,
        actorName: task.ownerName ?? task.owner,
        description: statusMeta.description,
        eventKind: task.status === 'withdrawn' ? 'withdrawn' : 'stage-snapshot',
        icon: statusMeta.icon,
        level: statusMeta.level,
        occurredAt: task.updatedAt,
        platform: undefined,
        progress: task.progress,
        state: task.status,
      }),
      // This is the current legacy task-stage projection, not invented
      // history. A formal event stream may replace it later by the same ID.
      id: `task-activity:stage:${task.id}`,
    },
  ];

  const current = task.completion?.current;
  if (current) {
    events.push({
      ...baseEvent(task, {
        actorName: current.submittedBy,
        description: `已提交交付 v${current.versionNo}。`,
        eventKind: 'delivery-submitted',
        icon: 'lucide:upload-cloud',
        level: task.status === 'pending_acceptance' ? 'high' : 'low',
        occurredAt: current.submittedAt,
        platform: current.kind === 'am' ? current.platform : undefined,
        progress: 100,
        state: current.status,
      }),
      id: `task-activity:delivery:${task.id}:${current.submissionId}`,
    });
  }

  for (const record of task.completion?.acceptanceHistory ?? []) {
    events.push({
      ...baseEvent(task, {
        actorId: record.reviewerId,
        actorName: record.reviewer,
        description:
          record.decision === 'accepted'
            ? `已验收交付 v${record.versionNo}。`
            : `已打回交付 v${record.versionNo}：${record.reason || '请补充后重新提交'}`,
        eventKind: record.decision,
        icon:
          record.decision === 'accepted'
            ? 'lucide:badge-check'
            : 'lucide:rotate-ccw',
        level: record.decision === 'accepted' ? 'low' : 'high',
        occurredAt: record.reviewedAt,
        platform: undefined,
        progress: record.decision === 'accepted' ? 100 : 0,
        state: record.decision,
      }),
      id: `task-activity:acceptance:${task.id}:${record.submissionId}:${record.decision}:${record.versionNo}`,
    });
  }
  return events;
}

/** Wraps the existing TaskCenter Store as a read-only compatibility source. */
export class TaskCenterActivityAdapter implements TaskActivityAdapter {
  constructor(private readonly options: TaskCenterActivityAdapterOptions) {}

  listEvents(
    query: Omit<TaskActivityQuery, 'limit' | 'workspaceTodos'>,
  ): readonly TaskActivityEvent[] {
    const projectId = query.projectId?.trim();
    return this.options
      .tasks()
      .filter(
        (task) =>
          (!projectId || task.projectId === projectId) &&
          canReadTask(task, query.viewer),
      )
      .flatMap((task) => eventsForTask(task));
  }
}
