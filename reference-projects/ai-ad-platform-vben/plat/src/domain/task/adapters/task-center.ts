import type {
  TaskAssignmentAdapter,
  TaskDeliverableAdapter,
  TaskReaderAdapter,
} from '../adapter';
import type {
  AcceptanceRecord,
  DeliveryTaskSnapshot,
  TaskAssignment,
  TaskAssignmentProjection,
  TaskAssignmentStatus,
  TaskDeliverable,
  TaskDeliverableProjection,
  TaskDeliverableSubmitInput,
  UnresolvedLegacyTaskParticipant,
} from '../types';

import type {
  TaskCenterTask,
  TaskCompletionInput,
  TaskCompletionRecord,
} from '#/store/task-center';

export interface TaskCenterTaskAdapterOptions {
  acceptTask?: (
    taskId: string,
    reviewer: string,
    reason?: string,
    reviewerId?: string,
  ) => TaskCenterTask | undefined;
  completeTask?: (
    taskId: string,
    input: TaskCompletionInput,
  ) => TaskCenterTask | undefined;
  patchTask?: (
    taskId: string,
    patch: Partial<TaskCenterTask>,
  ) => TaskCenterTask | undefined;
  rejectTask?: (
    taskId: string,
    reviewer: string,
    reason: string,
    reviewerId?: string,
  ) => TaskCenterTask | undefined;
  tasks: () => readonly TaskCenterTask[];
}

function assignmentStatusFromTask(
  status: TaskCenterTask['status'],
): TaskAssignmentStatus {
  if (status === 'done') return 'done';
  if (status === 'pending_acceptance') return 'submitted';
  if (status === 'withdrawn') return 'cancelled';
  if (status === 'doing' || status === 'risk') return 'doing';
  return 'pending';
}

function cloneAssignment(assignment: TaskAssignment): TaskAssignment {
  return {
    ...assignment,
    teamCodes: assignment.teamCodes ? [...assignment.teamCodes] : undefined,
  };
}

function createAssignmentId(taskId: string, assigneeId: string) {
  return `assignment:${taskId}:${assigneeId}`;
}

function toDeliverable(
  taskId: string,
  record: TaskCompletionRecord,
): TaskDeliverable {
  const formalId =
    record.kind === 'material' ? record.formalDeliveryId?.trim() : undefined;
  return {
    id: formalId || record.submissionId,
    items: record.files.map((file) => ({
      id: file.serverFileId ?? file.id,
      name: file.name,
      objectKey: file.objectKey,
      size: file.size,
      type: file.type,
      url: file.url,
    })),
    legacyDerived: !formalId,
    note: record.note,
    status: record.status,
    submittedAt: record.submittedAt,
    submittedBy: record.submittedBy,
    taskId,
    version:
      record.kind === 'material'
        ? (record.formalVersionNo ?? record.versionNo)
        : record.versionNo,
  };
}

function toDeliverableProjection(
  task: TaskCenterTask,
): TaskDeliverableProjection {
  const completion = task.completion;
  if (!completion) return { acceptanceRecords: [], deliverables: [] };
  const records = [
    ...completion.history,
    ...(completion.current ? [completion.current] : []),
  ];
  const deliverables = records.map((record) => toDeliverable(task.id, record));
  const deliverableIdBySubmission = new Map<string, string>();
  for (const [index, record] of records.entries()) {
    const deliverable = deliverables[index];
    if (deliverable) {
      deliverableIdBySubmission.set(record.submissionId, deliverable.id);
    }
  }
  const acceptanceRecords: AcceptanceRecord[] =
    completion.acceptanceHistory.map((record) => ({
      actedAt: record.reviewedAt,
      comment: record.reason,
      deliverableId:
        deliverableIdBySubmission.get(record.submissionId) ??
        record.submissionId,
      id: `acceptance:${task.id}:${record.submissionId}:${record.reviewedAt}`,
      legacyDerived: !record.reviewerId,
      result: record.decision,
      reviewerId: record.reviewerId,
      reviewerName: record.reviewer,
      taskId: task.id,
    }));
  return { acceptanceRecords, deliverables };
}

function normalizeProjection(task: TaskCenterTask): TaskAssignmentProjection {
  const assignments = new Map<string, TaskAssignment>();
  const unresolvedLegacyParticipants: UnresolvedLegacyTaskParticipant[] = [];
  const defaultStatus = assignmentStatusFromTask(task.status);

  const addStable = (
    source: Partial<TaskAssignment>,
    role: TaskAssignment['role'],
    teamCode?: string,
  ) => {
    const assigneeId = source.assigneeId?.trim();
    const assigneeName = source.assigneeName?.trim();
    if (!assigneeId || !assigneeName) return false;
    const current = assignments.get(assigneeId);
    const teamCodes = new Set([
      ...(current?.teamCodes ?? []),
      ...(teamCode ? [teamCode] : []),
    ]);
    assignments.set(assigneeId, {
      alsoExecutor:
        current?.alsoExecutor ||
        source.alsoExecutor ||
        (current?.role === 'owner' && role === 'executor') ||
        (current?.role === 'executor' && role === 'owner'),
      assigneeId,
      assigneeName,
      departmentId: source.departmentId ?? current?.departmentId,
      dueAt: source.dueAt ?? current?.dueAt ?? task.dueAt,
      id: current?.id ?? createAssignmentId(task.id, assigneeId),
      progress: Math.max(current?.progress ?? 0, source.progress ?? 0),
      role: current?.role === 'owner' || role === 'owner' ? 'owner' : role,
      status: current?.status ?? source.status ?? defaultStatus,
      taskId: task.id,
      teamCodes: teamCodes.size > 0 ? [...teamCodes] : undefined,
    });
    return true;
  };

  for (const assignment of task.assignments ?? []) {
    addStable(assignment, assignment.role);
  }

  if (
    !addStable(
      {
        assigneeId: task.ownerId,
        assigneeName: task.ownerName ?? task.owner,
        dueAt: task.dueAt,
        progress: task.progress,
        status: defaultStatus,
      },
      'owner',
    ) &&
    task.owner.trim()
  ) {
    unresolvedLegacyParticipants.push({
      name: task.owner,
      role: 'owner',
      source: 'task.owner',
      status: defaultStatus,
    });
  }

  for (const allocation of task.delivery?.allocations ?? []) {
    if (
      addStable(
        {
          assigneeId: allocation.assigneeId,
          assigneeName: allocation.assigneeName ?? allocation.owner,
          dueAt: task.delivery?.dueAt ?? task.dueAt,
          status: defaultStatus,
        },
        'executor',
        allocation.team || undefined,
      )
    ) {
      continue;
    }
    if (allocation.owner.trim()) {
      unresolvedLegacyParticipants.push({
        name: allocation.owner,
        role: 'executor',
        source: `delivery.allocation:${allocation.id}`,
        status: defaultStatus,
      });
    }
  }

  return {
    assignments: [...assignments.values()].map((assignment) =>
      cloneAssignment(assignment),
    ),
    unresolvedLegacyParticipants,
  };
}

/**
 * Keeps TaskCenter as the write owner during migration. This adapter only
 * exposes the minimum immutable facts needed to validate a source task.
 */
export class TaskCenterTaskAdapter
  implements TaskAssignmentAdapter, TaskDeliverableAdapter, TaskReaderAdapter
{
  constructor(private readonly options: TaskCenterTaskAdapterOptions) {}

  acceptDeliverable(
    taskId: string,
    reviewer: { id?: string; name: string },
    comment = '',
  ): TaskDeliverableProjection | undefined {
    if (!this.options.acceptTask) {
      throw new Error('任务交付验收适配器未配置');
    }
    const task = this.options.acceptTask(
      taskId,
      reviewer.name,
      comment,
      reviewer.id,
    );
    return task ? toDeliverableProjection(task) : undefined;
  }

  getDeliveryTask(id: string): DeliveryTaskSnapshot | undefined {
    const task = this.options.tasks().find((item) => item.id === id);
    if (!task || task.kind !== 'am' || !task.projectId?.trim()) return;
    return {
      id: task.id,
      kind: 'am',
      project: task.project,
      projectId: task.projectId,
      status: task.status,
      title: task.title,
    };
  }

  getTaskAssignmentProjection(
    taskId: string,
  ): TaskAssignmentProjection | undefined {
    const task = this.options.tasks().find((item) => item.id === taskId);
    return task ? normalizeProjection(task) : undefined;
  }

  getTaskDeliverableProjection(
    taskId: string,
  ): TaskDeliverableProjection | undefined {
    const task = this.options.tasks().find((item) => item.id === taskId);
    return task ? toDeliverableProjection(task) : undefined;
  }

  rejectDeliverable(
    taskId: string,
    reviewer: { id?: string; name: string },
    comment: string,
  ): TaskDeliverableProjection | undefined {
    if (!this.options.rejectTask) {
      throw new Error('任务交付验收适配器未配置');
    }
    const task = this.options.rejectTask(
      taskId,
      reviewer.name,
      comment,
      reviewer.id,
    );
    return task ? toDeliverableProjection(task) : undefined;
  }

  replaceTaskAssignments(
    taskId: string,
    assignments: readonly TaskAssignment[],
  ): TaskAssignmentProjection | undefined {
    if (!this.options.patchTask) {
      throw new Error('任务参与人写入适配器未配置');
    }
    const task = this.options.patchTask(taskId, {
      assignments: assignments.map((assignment) => cloneAssignment(assignment)),
    });
    return task ? normalizeProjection(task) : undefined;
  }

  submitDeliverable(
    input: TaskDeliverableSubmitInput,
  ): TaskDeliverableProjection | undefined {
    if (!this.options.completeTask) {
      throw new Error('任务交付提交适配器未配置');
    }
    const task = this.options.completeTask(
      input.taskId,
      input.legacyInput as TaskCompletionInput,
    );
    return task ? toDeliverableProjection(task) : undefined;
  }
}
