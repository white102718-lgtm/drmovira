import type {
  ApplicationFormSchemaAdapter,
  ApplicationPersistenceAdapter,
} from './adapter';
import type {
  ApplicationActor,
  ApplicationCommentInput,
  ApplicationFormSchema,
  ApplicationResubmissionInput,
  ApplicationTransferInput,
  ApplicationType,
  ApprovalAction,
  ApprovalDecisionInput,
  ResourceApplication,
} from './types';

import { approvalRoleMeta } from './types';

export interface ApplicationWorkflowClock {
  createId(prefix: string): string;
  now(): string;
}

const browserClock: ApplicationWorkflowClock = {
  createId(prefix) {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  },
  now() {
    return new Date().toLocaleString('zh-CN', { hour12: false });
  },
};

function clone(application: ResourceApplication) {
  return JSON.parse(JSON.stringify(application)) as ResourceApplication;
}

function currentNode(application: ResourceApplication) {
  return application.approvalNodes.find((node) => node.status === 'pending');
}

function actorCanHandleNode(
  node: ResourceApplication['approvalNodes'][number],
  actor: ApplicationActor,
) {
  const actorId = actor.id?.trim();
  if (node.approverId) return actorId === node.approverId;
  return actor.name.trim() === node.approver;
}

function assertActor(actor: ApplicationActor) {
  if (!actor.name.trim()) throw new Error('审批参与人不能为空');
}

function decisionRecord(
  clock: ApplicationWorkflowClock,
  applicationId: string,
  action: ApprovalAction,
  actor: ApplicationActor,
  remark: string,
) {
  return {
    action,
    actor: actor.name.trim(),
    actorRole: actor.role.trim() || '流程参与人',
    at: clock.now(),
    id: clock.createId(`APR-${applicationId}`),
    remark,
  };
}

function copiedRecord(
  clock: ApplicationWorkflowClock,
  application: ResourceApplication,
) {
  return decisionRecord(
    clock,
    application.id,
    'copied',
    { name: '系统通知', role: '抄送' },
    `审批结果已抄送：${application.ccUsers.join('、')}`,
  );
}

/**
 * The former Store mutations live here. This service is pure: callers choose
 * the persistence adapter, keeping the legacy raw-array Store key intact.
 */
export class ApplicationWorkflowService {
  constructor(
    private readonly clock: ApplicationWorkflowClock = browserClock,
  ) {}

  approve(
    application: ResourceApplication,
    input: Omit<ApprovalDecisionInput, 'decision'>,
  ) {
    return this.decide(application, { ...input, decision: 'approved' });
  }

  canComment(application: ResourceApplication, actorName: string) {
    const actor = actorName.trim();
    if (!actor) return false;
    return new Set([
      application.requester,
      ...application.approvalNodes.map((node) => node.approver),
      ...application.approvalRecords.map((record) => record.actor),
      ...application.ccUsers,
    ]).has(actor);
  }

  comment(application: ResourceApplication, input: ApplicationCommentInput) {
    assertActor(input.actor);
    const content = input.content.trim();
    if (!content) throw new Error('请输入评论内容');
    if (!this.canComment(application, input.actor.name)) {
      throw new Error('当前身份不是该流程参与人');
    }
    const next = clone(application);
    const actor = input.actor.name.trim();
    next.comments.push({
      actor,
      actorRole: input.actor.role.trim() || '流程参与人',
      at: this.clock.now(),
      content,
      id: this.clock.createId(`COMMENT-${application.id}`),
      readBy: [actor],
    });
    next.updatedAt = this.clock.now();
    return next;
  }

  decide(application: ResourceApplication, input: ApprovalDecisionInput) {
    assertActor(input.actor);
    const remark = input.remark.trim();
    // 通过只推进流程，驳回才需向申请人提供可追溯的处理原因。
    if (input.decision === 'rejected' && !remark) {
      throw new Error('请填写本节点审批备注');
    }
    if (application.status !== 'pending') throw new Error('该申请状态已变化');
    const node = currentNode(application);
    if (!node) throw new Error('当前申请没有可处理的审批节点');

    const next = clone(application);
    const nextNode = currentNode(next);
    if (!nextNode) throw new Error('当前申请没有可处理的审批节点');
    const at = this.clock.now();
    nextNode.status = input.decision;
    nextNode.actedAt = at;
    nextNode.remark = remark;
    next.approvalRecords.push({
      action: input.decision,
      actor: input.actor.name.trim(),
      actorRole:
        input.actor.role.trim() || approvalRoleMeta[nextNode.role].label,
      at,
      id: this.clock.createId(`APR-${application.id}`),
      remark,
    });
    next.updatedAt = at;

    if (input.decision === 'rejected') {
      next.status = 'rejected';
      if (next.ccUsers.length > 0)
        next.approvalRecords.push(copiedRecord(this.clock, next));
      return next;
    }

    const pendingNode = next.approvalNodes.find(
      (item) => item.status === 'waiting',
    );
    if (pendingNode) {
      pendingNode.status = 'pending';
      next.approver = pendingNode.approver;
      next.approvalRole = pendingNode.role;
      return next;
    }

    next.status = 'approved';
    if (next.ccUsers.length > 0)
      next.approvalRecords.push(copiedRecord(this.clock, next));
    return next;
  }

  markCommentsRead(application: ResourceApplication, actorName: string) {
    const actor = actorName.trim();
    if (!actor || !this.canComment(application, actor)) return application;
    let changed = false;
    const next = clone(application);
    next.comments = next.comments.map((comment) => {
      const readBy = new Set(comment.readBy ?? [comment.actor]);
      if (readBy.has(actor)) return { ...comment, readBy: [...readBy] };
      changed = true;
      readBy.add(actor);
      return { ...comment, readBy: [...readBy] };
    });
    return changed ? next : application;
  }

  reject(
    application: ResourceApplication,
    input: Omit<ApprovalDecisionInput, 'decision'>,
  ) {
    return this.decide(application, { ...input, decision: 'rejected' });
  }

  resubmit(
    application: ResourceApplication,
    input: ApplicationResubmissionInput,
  ) {
    assertActor(input.actor);
    const remark = input.remark.trim();
    if (application.status !== 'rejected')
      throw new Error('只有已驳回的申请可以重新提交');
    if (application.requester !== input.actor.name.trim()) {
      throw new Error('只有申请人可以重新提交该申请');
    }
    if (!remark) throw new Error('请说明本次补充或修改内容');
    const next = clone(application);
    next.approvalNodes = next.approvalNodes.map((node, index) => ({
      ...node,
      actedAt: undefined,
      remark: undefined,
      status: index === 0 ? 'pending' : 'waiting',
    }));
    const firstNode = next.approvalNodes[0];
    if (!firstNode) throw new Error('申请缺少审批节点，无法重新提交');
    next.approver = firstNode.approver;
    next.approvalRole = firstNode.role;
    next.status = 'pending';
    next.updatedAt = this.clock.now();
    next.approvalRecords.push({
      action: 'submitted',
      actor: input.actor.name.trim(),
      actorRole: input.actor.role.trim() || '申请人',
      at: next.updatedAt,
      id: this.clock.createId(`APR-${application.id}`),
      remark,
    });
    return next;
  }

  transfer(application: ResourceApplication, input: ApplicationTransferInput) {
    assertActor(input.actor);
    const remark = input.remark.trim();
    if (!remark) throw new Error('请填写转交原因');
    if (!['pending', 'processing'].includes(application.status)) {
      throw new Error('该申请状态已变化');
    }
    const isProcessing = application.status === 'processing';
    const node = currentNode(application);
    if (!isProcessing && !node) {
      throw new Error('当前申请没有可处理的审批节点');
    }
    if (
      isProcessing &&
      (application.handlerId
        ? application.handlerId !== input.actor.id?.trim()
        : application.handlerName !== input.actor.name.trim())
    ) {
      throw new Error('当前用户不是该流程的办理人');
    }
    if (!isProcessing && node && !actorCanHandleNode(node, input.actor)) {
      throw new Error('当前用户不是本审批节点的稳定审批人');
    }

    const recipientId = input.recipient.id.trim();
    const recipientName = input.recipient.name.trim();
    if (!recipientId || !recipientName) throw new Error('请选择有效的接收同事');
    if (recipientId === input.actor.id?.trim()) {
      throw new Error('不能转交给当前办理人');
    }

    const next = clone(application);
    const at = this.clock.now();
    const nodeIndex = isProcessing
      ? next.approvalNodes.length
      : next.approvalNodes.findIndex((item) => item.status === 'pending');
    if (isProcessing) {
      next.handlerId = recipientId;
      next.handlerName = recipientName;
    } else {
      const nextNode = next.approvalNodes[nodeIndex];
      if (!nextNode) throw new Error('当前申请没有可处理的审批节点');
      nextNode.approver = recipientName;
      nextNode.approverId = recipientId;
    }
    next.approver = recipientName;
    next.updatedAt = at;
    next.approvalRecords.push({
      action: 'transferred',
      actor: input.actor.name.trim(),
      actorId: input.actor.id?.trim() || undefined,
      actorRole:
        input.actor.role.trim() ||
        (isProcessing
          ? '办理人'
          : node
            ? approvalRoleMeta[node.role].label
            : '审批人'),
      at,
      id: this.clock.createId(`APR-${application.id}`),
      nodeIndex,
      recipientDepartmentId: input.recipient.departmentId.trim() || undefined,
      recipientDepartmentName:
        input.recipient.departmentName.trim() || undefined,
      recipientId,
      recipientName,
      remark,
    });
    return next;
  }

  unreadCommentCount(application: ResourceApplication, actorName: string) {
    const actor = actorName.trim();
    if (!actor || !this.canComment(application, actor)) return 0;
    return application.comments.filter((comment) => {
      const readBy = new Set(comment.readBy ?? [comment.actor]);
      return !readBy.has(actor);
    }).length;
  }
}

/** Page-facing read service for type-specific application fields. */
export class ApplicationFormSchemaService {
  constructor(private readonly adapter: ApplicationFormSchemaAdapter) {}

  get(type: ApplicationType): ApplicationFormSchema {
    return structuredClone(this.adapter.getFormSchema(type));
  }
}

/**
 * Single service entry for migrated application pages. It wraps the legacy
 * Store through an injected adapter and leaves the old mutations available to
 * all still-unmigrated callers.
 */
export class ApplicationService {
  constructor(
    private readonly adapter: ApplicationPersistenceAdapter,
    private readonly workflow = new ApplicationWorkflowService(),
  ) {}

  approve(
    applicationId: string,
    input: Omit<ApprovalDecisionInput, 'decision'>,
  ) {
    return this.persist(applicationId, (application) =>
      this.workflow.approve(application, input),
    );
  }

  canComment(applicationId: string, actor: ApplicationActor) {
    const application = this.require(applicationId);
    return this.workflow.canComment(application, actor.name);
  }

  comment(applicationId: string, input: ApplicationCommentInput) {
    return this.persist(applicationId, (application) =>
      this.workflow.comment(application, input),
    );
  }

  get(applicationId: string) {
    return clone(this.require(applicationId));
  }

  list() {
    return this.adapter.list().map((application) => clone(application));
  }

  markCommentsRead(applicationId: string, actor: ApplicationActor) {
    return this.persist(applicationId, (application) =>
      this.workflow.markCommentsRead(application, actor.name),
    );
  }

  reject(
    applicationId: string,
    input: Omit<ApprovalDecisionInput, 'decision'>,
  ) {
    return this.persist(applicationId, (application) =>
      this.workflow.reject(application, input),
    );
  }

  remove(applicationId: string) {
    const normalizedId = applicationId.trim();
    this.require(normalizedId);
    this.adapter.remove(normalizedId);
  }

  resubmit(applicationId: string, input: ApplicationResubmissionInput) {
    return this.persist(applicationId, (application) =>
      this.workflow.resubmit(application, input),
    );
  }

  transfer(applicationId: string, input: ApplicationTransferInput) {
    return this.persist(applicationId, (application) =>
      this.workflow.transfer(application, input),
    );
  }

  save(application: ResourceApplication) {
    return clone(this.adapter.upsert(application));
  }

  unreadCommentCount(applicationId: string, actor: ApplicationActor) {
    const application = this.require(applicationId);
    return this.workflow.unreadCommentCount(application, actor.name);
  }

  private persist(
    applicationId: string,
    transform: (application: ResourceApplication) => ResourceApplication,
  ) {
    return clone(this.adapter.upsert(transform(this.require(applicationId))));
  }

  private require(applicationId: string) {
    const normalizedId = applicationId.trim();
    if (!normalizedId) throw new Error('申请缺少稳定 ID');
    const application = this.adapter
      .list()
      .find((item) => item.id === normalizedId);
    if (!application) throw new Error('申请不存在或已被移除');
    return clone(application);
  }
}
