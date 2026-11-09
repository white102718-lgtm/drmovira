import type {
  RequirementTaskAdapter,
  TaskAssignmentAdapter,
  TaskDeliverableAdapter,
  TaskReaderAdapter,
  TaskSourceRelationAdapter,
} from './adapter';
import type {
  CreateMaterialTaskContext,
  CreateResourceApplicationContext,
  MaterialOrderWriteResult,
  TaskAssignment,
  TaskAssignmentInput,
  TaskAssignmentProjection,
  TaskAssignmentUpdateResult,
  TaskDeliverableProjection,
  TaskDeliverableSubmitInput,
  TaskSourceRelation,
} from './types';

import type { CreateOrderParams } from '#/api/requirement';

function cloneRelation(relation: TaskSourceRelation): TaskSourceRelation {
  return { ...relation };
}

/**
 * The P0 wrapper validates a DeliveryTask source while leaving the existing
 * TaskCenter state machine and MaterialOrder API as their respective owners.
 */
export class TaskService {
  constructor(
    private readonly taskReader: TaskReaderAdapter,
    private readonly requirementAdapter: RequirementTaskAdapter,
    private readonly relationAdapter?: TaskSourceRelationAdapter,
    private readonly assignmentAdapter?: TaskAssignmentAdapter,
    private readonly deliverableAdapter?: TaskDeliverableAdapter,
  ) {}

  async acceptAssignment(
    taskId: string,
    assigneeId: string,
  ): Promise<TaskAssignmentUpdateResult> {
    return this.updateAssignment(taskId, assigneeId, (assignment) => ({
      ...assignment,
      progress: Math.max(1, assignment.progress),
      status: 'doing',
    }));
  }

  async acceptDeliverable(
    taskId: string,
    reviewer: { id?: string; name: string },
    comment = '',
  ): Promise<TaskDeliverableProjection> {
    const normalizedTaskId = taskId.trim();
    if (!normalizedTaskId || !reviewer.name.trim()) {
      throw new Error('验收交付时缺少任务或审核人');
    }
    if (!this.deliverableAdapter) throw new Error('任务交付关系暂不可用');
    const projection = await this.deliverableAdapter.acceptDeliverable(
      normalizedTaskId,
      reviewer,
      comment,
    );
    if (!projection) throw new Error('当前交付不可验收');
    return cloneDeliverableProjection(projection);
  }

  async assign(
    taskId: string,
    inputs: readonly TaskAssignmentInput[],
  ): Promise<TaskAssignmentUpdateResult> {
    const projection = await this.requireAssignments(taskId);
    const assignments = new Map<string, TaskAssignment>(
      projection.assignments.map((assignment) => [
        assignment.assigneeId,
        { ...assignment, teamCodes: [...(assignment.teamCodes ?? [])] },
      ]),
    );

    for (const input of inputs) {
      const assigneeId = input.assigneeId.trim();
      const assigneeName = input.assigneeName.trim();
      if (!assigneeId || !assigneeName) {
        throw new Error('任务参与人必须使用稳定用户 ID 与显示姓名');
      }
      const current = assignments.get(assigneeId);
      const teamCodes = new Set([
        ...(current?.teamCodes ?? []),
        ...(input.teamCode ? [input.teamCode] : []),
      ]);
      assignments.set(assigneeId, {
        alsoExecutor:
          current?.alsoExecutor ||
          input.alsoExecutor ||
          (current?.role === 'owner' && input.role === 'executor') ||
          (current?.role === 'executor' && input.role === 'owner'),
        assigneeId,
        assigneeName,
        departmentId: input.departmentId ?? current?.departmentId,
        dueAt: input.dueAt ?? current?.dueAt,
        id: current?.id ?? `assignment:${taskId}:${assigneeId}`,
        progress: input.progress ?? current?.progress ?? 0,
        role:
          current?.role === 'owner' || input.role === 'owner'
            ? 'owner'
            : input.role,
        status: input.status ?? current?.status ?? 'pending',
        taskId,
        teamCodes: teamCodes.size > 0 ? [...teamCodes] : undefined,
      });
    }
    return this.saveAssignments(taskId, [...assignments.values()]);
  }

  async completeAssignment(
    taskId: string,
    assigneeId: string,
  ): Promise<TaskAssignmentUpdateResult> {
    return this.updateAssignment(taskId, assigneeId, (assignment) => ({
      ...assignment,
      progress: 100,
      status: 'done',
    }));
  }

  async createMaterialOrder(
    payload: CreateOrderParams,
    context?: CreateMaterialTaskContext,
  ): Promise<MaterialOrderWriteResult> {
    const verifiedContext = context
      ? await this.resolveMaterialTaskContext(context)
      : undefined;
    const result = await this.requirementAdapter.create(
      payload,
      verifiedContext,
    );
    return this.persistRelation(result, verifiedContext);
  }

  async listAssignments(taskId: string): Promise<TaskAssignmentProjection> {
    return this.requireAssignments(taskId);
  }

  async listDeliverables(taskId: string): Promise<TaskDeliverableProjection> {
    const normalizedTaskId = taskId.trim();
    if (!normalizedTaskId || !this.deliverableAdapter) {
      throw new Error('任务交付关系暂不可用');
    }
    const projection =
      await this.deliverableAdapter.getTaskDeliverableProjection(
        normalizedTaskId,
      );
    if (!projection) throw new Error('任务不存在，无法读取交付记录');
    return cloneDeliverableProjection(projection);
  }

  async listMaterialOrderRelations(sourceTaskId: string) {
    if (!sourceTaskId.trim() || !this.relationAdapter) return [];
    const relations = await this.relationAdapter.listBySourceTask(
      sourceTaskId.trim(),
    );
    return relations.map((relation) => cloneRelation(relation));
  }

  async rejectDeliverable(
    taskId: string,
    reviewer: { id?: string; name: string },
    comment: string,
  ): Promise<TaskDeliverableProjection> {
    const normalizedTaskId = taskId.trim();
    if (!normalizedTaskId || !reviewer.name.trim() || !comment.trim()) {
      throw new Error('打回交付时缺少任务、审核人或原因');
    }
    if (!this.deliverableAdapter) throw new Error('任务交付关系暂不可用');
    const projection = await this.deliverableAdapter.rejectDeliverable(
      normalizedTaskId,
      reviewer,
      comment,
    );
    if (!projection) throw new Error('当前交付不可打回');
    return cloneDeliverableProjection(projection);
  }

  async resolveMaterialTaskContext(
    context: CreateMaterialTaskContext,
  ): Promise<CreateMaterialTaskContext> {
    const sourceTaskId = context.sourceTaskId.trim();
    const projectId = context.projectId.trim();
    const requesterId = context.requesterId.trim();
    const requesterName = context.requesterName.trim();
    if (!sourceTaskId || !projectId || !requesterId || !requesterName) {
      throw new Error('素材任务来源上下文不完整，无法保存');
    }

    const task = await this.taskReader.getDeliveryTask(sourceTaskId);
    if (!task) throw new Error('来源投放任务不存在、类型不符或缺少项目 ID');
    if (task.status === 'withdrawn') {
      throw new Error('来源投放任务已撤回，不能继续发起素材需求');
    }
    if (task.projectId !== projectId) {
      throw new Error('来源投放任务与项目 ID 不匹配，已阻断保存');
    }
    return { projectId, requesterId, requesterName, sourceTaskId };
  }

  /**
   * Uses the same stable DeliveryTask lookup as material-task creation. The
   * legacy task route keeps working, but an application may never claim a
   * project/source relation that the source task does not actually own.
   */
  async resolveResourceApplicationContext(
    context: CreateResourceApplicationContext,
  ): Promise<CreateResourceApplicationContext> {
    const sourceTaskId = context.sourceTaskId.trim();
    const projectId = context.projectId.trim();
    const projectName = context.projectName.trim();
    const requesterId = context.requesterId.trim();
    const requesterName = context.requesterName.trim();
    if (
      !sourceTaskId ||
      !projectId ||
      !projectName ||
      !requesterId ||
      !requesterName
    ) {
      throw new Error('资源申请来源上下文不完整，无法保存');
    }
    const task = await this.taskReader.getDeliveryTask(sourceTaskId);
    if (!task) throw new Error('来源投放任务不存在、类型不符或缺少项目 ID');
    if (task.status === 'withdrawn') {
      throw new Error('来源投放任务已撤回，不能继续发起资源申请');
    }
    if (task.projectId !== projectId) {
      throw new Error('来源投放任务与项目 ID 不匹配，已阻断保存');
    }
    return {
      projectId,
      projectName: task.project,
      requesterId,
      requesterName,
      sourceTaskId,
    };
  }

  async submitDeliverable(
    input: TaskDeliverableSubmitInput,
  ): Promise<TaskDeliverableProjection> {
    const taskId = input.taskId.trim();
    if (!taskId || !input.legacyInput || !this.deliverableAdapter) {
      throw new Error('任务交付信息不完整');
    }
    const projection = await this.deliverableAdapter.submitDeliverable({
      ...input,
      taskId,
    });
    if (!projection) throw new Error('交付信息未通过校验，请检查后重试');
    return cloneDeliverableProjection(projection);
  }

  async updateMaterialOrder(
    orderId: string,
    payload: CreateOrderParams,
    context?: CreateMaterialTaskContext,
  ): Promise<MaterialOrderWriteResult> {
    const normalizedOrderId = orderId.trim();
    if (!normalizedOrderId) throw new Error('素材订单缺少稳定 ID，无法更新');
    const verifiedContext = context
      ? await this.resolveMaterialTaskContext(context)
      : undefined;
    const result = await this.requirementAdapter.update(
      normalizedOrderId,
      payload,
      verifiedContext,
    );
    return this.persistRelation(result, verifiedContext);
  }

  private async persistRelation(
    result: MaterialOrderWriteResult,
    context: CreateMaterialTaskContext | undefined,
  ): Promise<MaterialOrderWriteResult> {
    if (
      !context ||
      !result.materialOrderId ||
      result.sourceLinkState !== 'linked' ||
      !this.relationAdapter
    ) {
      return result;
    }
    const timestamp = new Date().toISOString();
    await this.relationAdapter.save({
      createdAt: timestamp,
      materialOrderId: result.materialOrderId,
      projectId: context.projectId,
      requesterId: context.requesterId,
      requesterName: context.requesterName,
      sourceTaskId: context.sourceTaskId,
      updatedAt: timestamp,
    });
    return result;
  }

  private async requireAssignments(
    taskId: string,
  ): Promise<TaskAssignmentProjection> {
    const normalizedTaskId = taskId.trim();
    if (!normalizedTaskId || !this.assignmentAdapter) {
      throw new Error('任务参与人关系暂不可用');
    }
    const projection =
      await this.assignmentAdapter.getTaskAssignmentProjection(
        normalizedTaskId,
      );
    if (!projection) throw new Error('任务不存在，无法更新参与人');
    return {
      assignments: projection.assignments.map((assignment) => ({
        ...assignment,
        teamCodes: assignment.teamCodes ? [...assignment.teamCodes] : undefined,
      })),
      unresolvedLegacyParticipants: projection.unresolvedLegacyParticipants.map(
        (participant) => ({ ...participant }),
      ),
    };
  }

  private async saveAssignments(
    taskId: string,
    assignments: readonly TaskAssignment[],
  ): Promise<TaskAssignmentUpdateResult> {
    if (!this.assignmentAdapter) throw new Error('任务参与人关系暂不可用');
    const projection = await this.assignmentAdapter.replaceTaskAssignments(
      taskId,
      assignments,
    );
    if (!projection) throw new Error('任务不存在，无法保存参与人');
    const executors = projection.assignments.filter(
      (assignment) => assignment.role === 'executor' || assignment.alsoExecutor,
    );
    let completionState: TaskAssignmentUpdateResult['completionState'] =
      'pending';
    if (
      executors.length > 0 &&
      executors.every((item) => item.status === 'done')
    ) {
      completionState = 'all_done';
    } else if (executors.some((item) => item.status === 'done')) {
      completionState = 'partially_completed';
    }
    return { ...projection, completionState };
  }

  private async updateAssignment(
    taskId: string,
    assigneeId: string,
    update: (assignment: TaskAssignment) => TaskAssignment,
  ): Promise<TaskAssignmentUpdateResult> {
    const projection = await this.requireAssignments(taskId);
    const normalizedAssigneeId = assigneeId.trim();
    const assignment = projection.assignments.find(
      (item) => item.assigneeId === normalizedAssigneeId,
    );
    if (!assignment) throw new Error('当前用户没有该任务的稳定参与人关系');
    return this.saveAssignments(
      taskId,
      projection.assignments.map((item) =>
        item.assigneeId === normalizedAssigneeId ? update(item) : item,
      ),
    );
  }
}

function cloneDeliverableProjection(
  projection: TaskDeliverableProjection,
): TaskDeliverableProjection {
  return {
    acceptanceRecords: projection.acceptanceRecords.map((record) => ({
      ...record,
    })),
    deliverables: projection.deliverables.map((deliverable) => ({
      ...deliverable,
      items: deliverable.items.map((item) => ({ ...item })),
    })),
  };
}
