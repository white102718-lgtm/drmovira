import type { ResourceCommandAdapter } from './adapter';
import type {
  AuditActor,
  CreateMediaAccountInput,
  CreateResourceApplicationInput,
  ExceptionActionOptions,
  MediaAccount,
  ResourceApplication,
  ResourceLifecycleClock,
  ResourceLifecycleState,
  ResourceLifecycleTransition,
  ResourceResolutionOutcome,
  ResourceReturn,
} from './types';

import { LegacyResourceLifecycleAdapter } from './adapters/legacy';

const browserClock: ResourceLifecycleClock = {
  createId(prefix) {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  },
  now() {
    return new Date().toISOString();
  },
};

function snapshot(account: MediaAccount): Record<string, unknown> {
  return {
    assigneeId: account.assigneeId,
    assigneeName: account.assigneeName,
    platformStatus: account.platformStatus,
    projectId: account.projectId,
    projectName: account.projectName,
    resourceStatus: account.resourceStatus,
    teamId: account.teamId,
    teamName: account.teamName,
  };
}

function requiredCount(application: ResourceApplication) {
  return Math.max(0, application.requestedAccountCount);
}

function fail(message: string): never {
  throw new Error(message);
}

/**
 * Pure lifecycle rules for Inventory → Assignment → Return. The Store remains
 * a compatibility persistence facade and writes its existing audit array.
 */
export class ResourceLifecycleService {
  constructor(
    private readonly clock: ResourceLifecycleClock = browserClock,
    private readonly adapter = new LegacyResourceLifecycleAdapter(),
  ) {}

  approveApplication(
    input: {
      accountIds: readonly string[];
      actor: AuditActor;
      applicationId: string;
    },
    source: ResourceLifecycleState,
  ): ResourceLifecycleTransition<readonly string[]> {
    const state = this.adapter.normalize(source);
    const application = state.applications.find(
      (item) => item.id === input.applicationId,
    );
    if (!application) fail('资源申请不存在');
    if (!['partially_approved', 'pending'].includes(application.status)) {
      fail('当前申请状态不可审批');
    }

    const accountIds = [
      ...new Set(input.accountIds.map((id) => id.trim()).filter(Boolean)),
    ];
    if (accountIds.length === 0) fail('请至少选择一个可用媒体账户');
    const previouslyApproved = new Set(application.approvedAccountIds);
    if (accountIds.some((id) => previouslyApproved.has(id))) {
      fail('不能重复分配已经批准的媒体账户');
    }
    const remaining = requiredCount(application) - previouslyApproved.size;
    if (remaining <= 0) fail('该申请已完成全部账户分配');
    if (accountIds.length > remaining) {
      fail(`本次最多可分配 ${remaining} 个媒体账户`);
    }

    const selectedAccounts = accountIds.map((id) =>
      state.accounts.find(
        (account) => account.id === id || account.accountId === id,
      ),
    );
    const missingIds = accountIds.filter(
      (_, index) => !selectedAccounts[index],
    );
    if (missingIds.length > 0) fail(`媒体账户不存在：${missingIds.join('、')}`);
    const accounts = selectedAccounts as MediaAccount[];
    const invalidAccount = accounts.find(
      (account) =>
        account.platform !== application.platform ||
        account.platformStatus !== 'active' ||
        account.resourceStatus !== 'available',
    );
    if (invalidAccount) {
      fail(`${invalidAccount.name} 与申请平台不匹配或当前不可分配`);
    }

    const before = {
      approvedAccountIds: [...application.approvedAccountIds],
      status: application.status,
    };
    const timestamp = this.clock.now();
    const assigneeId = application.assigneeId || application.requestedById;
    const assigneeName =
      application.assigneeName || application.requestedByName;
    const createdAssignmentIds = accounts.map((account) => {
      const assignmentId = this.clock.createId('resource-assignment');
      state.assignments.unshift({
        applicationId: application.id,
        assignedAt: timestamp,
        assignedById: input.actor.id,
        assignedByName: input.actor.name,
        assigneeId,
        assigneeName,
        id: assignmentId,
        mediaAccountId: account.id,
        platformAccountId: account.accountId,
        projectId: application.projectId,
        projectName: application.projectName,
        status: 'active',
        teamId: application.teamId,
        teamName: application.teamName,
        updatedAt: timestamp,
      });
      Object.assign(account, {
        assignedAt: timestamp,
        assigneeId,
        assigneeName,
        projectId: application.projectId,
        projectName: application.projectName,
        resourceStatus: 'assigned',
        teamId: application.teamId,
        teamName: application.teamName,
        updatedAt: timestamp,
      });
      return assignmentId;
    });
    const nextApprovedAccountIds = new Set(application.approvedAccountIds);
    for (const account of accounts) nextApprovedAccountIds.add(account.id);
    application.approvedAccountIds = [...nextApprovedAccountIds];
    application.reviewedAt = timestamp;
    application.reviewedById = input.actor.id;
    application.reviewedByName = input.actor.name;
    application.status =
      application.approvedAccountIds.length >= requiredCount(application)
        ? 'approved'
        : 'partially_approved';
    application.updatedAt = timestamp;
    return {
      audit: {
        action: 'application.approved',
        after: {
          approvedAccountIds: [...application.approvedAccountIds],
          status: application.status,
        },
        before,
        entityId: application.id,
        entityType: 'application',
        message: `批准 ${application.applicationNo}，分配 ${createdAssignmentIds.length} 个账户`,
        metadata: {
          accountIds: accounts.map((account) => account.id),
          assignmentIds: createdAssignmentIds,
          projectId: application.projectId,
          teamId: application.teamId,
        },
      },
      result: createdAssignmentIds,
      state,
    };
  }

  completeReturn(
    input: {
      actor: AuditActor;
      outcome: ResourceResolutionOutcome;
      returnId: string;
    },
    source: ResourceLifecycleState,
  ): ResourceLifecycleTransition<ResourceReturn> {
    const state = this.adapter.normalize(source);
    const returnRequest = state.returns.find(
      (item) => item.id === input.returnId,
    );
    if (!returnRequest) fail('回收申请不存在');
    if (returnRequest.status !== 'requested') fail('该回收申请已完成');
    const account = state.accounts.find(
      (item) => item.id === returnRequest.mediaAccountId,
    );
    const assignment = state.assignments.find(
      (item) => item.id === returnRequest.resourceAssignmentId,
    );
    if (!account || !assignment) fail('回收申请关联的账户或分配记录不存在');
    const before = snapshot(account);
    const timestamp = this.clock.now();
    Object.assign(returnRequest, {
      completedAt: timestamp,
      completedById: input.actor.id,
      completedByName: input.actor.name,
      status: 'completed',
      updatedAt: timestamp,
    });
    assignment.returnedAt = timestamp;
    assignment.status = 'returned';
    assignment.updatedAt = timestamp;
    account.platformStatus =
      input.outcome === 'disabled' ? 'disabled' : 'active';
    account.resourceStatus =
      input.outcome === 'disabled' ? 'retired' : 'available';
    account.updatedAt = timestamp;
    delete account.assignedAt;
    delete account.assigneeId;
    delete account.assigneeName;
    delete account.projectId;
    delete account.projectName;
    delete account.teamId;
    delete account.teamName;
    return {
      audit: {
        action: 'return.completed',
        after: snapshot(account),
        before,
        entityId: returnRequest.id,
        entityType: 'return',
        message: `完成 ${account.name} 回收并清空项目、团队和使用人关系`,
        metadata: {
          assignmentId: assignment.id,
          mediaAccountId: account.id,
          outcome: input.outcome,
        },
      },
      result: returnRequest,
      state,
    };
  }

  createAccount(
    input: CreateMediaAccountInput,
    _actor: AuditActor,
    source: ResourceLifecycleState,
  ): ResourceLifecycleTransition<MediaAccount> {
    const state = this.adapter.normalize(source);
    const accountId = input.accountId.trim();
    const name = input.name.trim();
    if (!accountId || !name) fail('媒体账户 ID 和名称不能为空');
    if (
      state.accounts.some(
        (account) =>
          account.platform === input.platform &&
          account.accountId === accountId,
      )
    ) {
      fail('同一媒体平台下已存在该账户 ID');
    }
    const timestamp = this.clock.now();
    const created: MediaAccount = {
      ...input,
      accountId,
      createdAt: timestamp,
      id: this.clock.createId('media-account'),
      inboundAt: timestamp,
      lastSyncedAt: timestamp,
      name,
      platformStatus: input.platformStatus ?? 'active',
      resourceStatus: input.resourceStatus ?? 'available',
      tags: [...(input.tags ?? [])],
      updatedAt: timestamp,
    };
    state.accounts.unshift(created);
    return {
      audit: {
        action: 'account.created',
        after: snapshot(created),
        entityId: created.id,
        entityType: 'account',
        message: `新增媒体账户 ${created.name}`,
        metadata: {
          platform: created.platform,
          platformAccountId: created.accountId,
        },
      },
      result: created,
      state,
    };
  }

  createApplication(
    input: CreateResourceApplicationInput,
    _actor: AuditActor,
    source: ResourceLifecycleState,
  ): ResourceLifecycleTransition<ResourceApplication> {
    const state = this.adapter.normalize(source);
    if (
      !input.projectId.trim() ||
      !input.teamId.trim() ||
      input.requestedAccountCount < 1
    ) {
      fail('项目、团队和申请账户数量不能为空');
    }
    const timestamp = this.clock.now();
    const created: ResourceApplication = {
      ...input,
      applicationNo: `MR-${timestamp.slice(0, 10).replaceAll('-', '')}-${String(
        state.applications.length + 1,
      ).padStart(3, '0')}`,
      approvedAccountIds: [],
      createdAt: timestamp,
      id: this.clock.createId('resource-application'),
      status: 'pending',
      title:
        input.title?.trim() ||
        `${input.projectName} ${input.platform} 广告账户申请`,
      updatedAt: timestamp,
    };
    state.applications.unshift(created);
    return {
      audit: {
        action: 'application.created',
        after: {
          platform: created.platform,
          projectId: created.projectId,
          requestedAccountCount: created.requestedAccountCount,
          status: created.status,
          teamId: created.teamId,
        },
        entityId: created.id,
        entityType: 'application',
        message: `提交资源申请 ${created.applicationNo}`,
      },
      result: created,
      state,
    };
  }

  markException(
    accountId: string,
    reason: string,
    options: ExceptionActionOptions,
    source: ResourceLifecycleState,
  ): ResourceLifecycleTransition<MediaAccount> {
    const state = this.adapter.normalize(source);
    const account = state.accounts.find(
      (item) => item.id === accountId || item.accountId === accountId,
    );
    if (!account) fail('媒体账户不存在');
    if (account.resourceStatus === 'exception') fail('媒体账户已处于异常状态');
    const before = snapshot(account);
    const timestamp = this.clock.now();
    account.exceptionAt = timestamp;
    account.exceptionPreviousResourceStatus = account.resourceStatus;
    account.exceptionReason = reason;
    account.platformStatus = options.platformStatus ?? account.platformStatus;
    account.resourceStatus = 'exception';
    account.updatedAt = timestamp;
    return {
      audit: {
        action: 'exception.marked',
        after: snapshot(account),
        before,
        entityId: account.id,
        entityType: 'account',
        message: `${account.name} 被标记为异常`,
        metadata: { reason },
      },
      result: account,
      state,
    };
  }

  rejectApplication(
    input: { actor: AuditActor; applicationId: string; reason: string },
    source: ResourceLifecycleState,
  ): ResourceLifecycleTransition<ResourceApplication> {
    const state = this.adapter.normalize(source);
    const application = state.applications.find(
      (item) => item.id === input.applicationId,
    );
    if (!application) fail('资源申请不存在');
    if (application.status !== 'pending') fail('只有待审批申请可以驳回');
    const before = { status: application.status };
    const timestamp = this.clock.now();
    application.rejectedReason = input.reason;
    application.reviewedAt = timestamp;
    application.reviewedById = input.actor.id;
    application.reviewedByName = input.actor.name;
    application.status = 'rejected';
    application.updatedAt = timestamp;
    return {
      audit: {
        action: 'application.rejected',
        after: { rejectedReason: input.reason, status: application.status },
        before,
        entityId: application.id,
        entityType: 'application',
        message: `驳回 ${application.applicationNo}`,
        metadata: { reason: input.reason },
      },
      result: application,
      state,
    };
  }

  requestReturn(
    input: { actor: AuditActor; assignmentOrAccountId: string; reason: string },
    source: ResourceLifecycleState,
  ): ResourceLifecycleTransition<ResourceReturn> {
    const state = this.adapter.normalize(source);
    const assignment = state.assignments.find(
      (item) =>
        item.status === 'active' &&
        [item.id, item.mediaAccountId, item.platformAccountId].includes(
          input.assignmentOrAccountId,
        ),
    );
    if (!assignment) fail('未找到可回收的有效资源分配');
    const account = state.accounts.find(
      (item) => item.id === assignment.mediaAccountId,
    );
    if (!account) fail('分配记录对应的媒体账户不存在');
    const timestamp = this.clock.now();
    const created: ResourceReturn = {
      accountName: account.name,
      id: this.clock.createId('resource-return'),
      mediaAccountId: account.id,
      platformAccountId: account.accountId,
      projectId: assignment.projectId,
      projectName: assignment.projectName,
      reason: input.reason,
      requestedAt: timestamp,
      requestedById: input.actor.id,
      requestedByName: input.actor.name,
      resourceAssignmentId: assignment.id,
      status: 'requested',
      updatedAt: timestamp,
    };
    const before = snapshot(account);
    assignment.status = 'return_requested';
    assignment.updatedAt = timestamp;
    account.resourceStatus = 'pending_return';
    account.updatedAt = timestamp;
    state.returns.unshift(created);
    return {
      audit: {
        action: 'return.requested',
        after: snapshot(account),
        before,
        entityId: created.id,
        entityType: 'return',
        message: `申请回收 ${account.name}`,
        metadata: {
          assignmentId: assignment.id,
          mediaAccountId: account.id,
          reason: input.reason,
        },
      },
      result: created,
      state,
    };
  }

  resolveException(
    input: {
      accountId: string;
      actor: AuditActor;
      note: string;
      outcome: ResourceResolutionOutcome;
    },
    source: ResourceLifecycleState,
  ): ResourceLifecycleTransition<MediaAccount> {
    const state = this.adapter.normalize(source);
    const account = state.accounts.find(
      (item) =>
        item.id === input.accountId || item.accountId === input.accountId,
    );
    if (!account) fail('媒体账户不存在');
    if (account.resourceStatus !== 'exception')
      fail('媒体账户当前不是异常状态');
    const before = snapshot(account);
    const previousStatus = account.exceptionPreviousResourceStatus;
    const hasActiveAssignment = state.assignments.some(
      (assignment) =>
        assignment.mediaAccountId === account.id &&
        assignment.status === 'active',
    );
    account.platformStatus =
      input.outcome === 'disabled' ? 'disabled' : 'active';
    if (input.outcome === 'disabled') {
      account.resourceStatus = 'retired';
    } else if (previousStatus === 'assigned' && hasActiveAssignment) {
      account.resourceStatus = 'assigned';
    } else {
      account.resourceStatus = 'available';
    }
    account.updatedAt = this.clock.now();
    delete account.exceptionAt;
    delete account.exceptionPreviousResourceStatus;
    delete account.exceptionReason;
    return {
      audit: {
        action: 'exception.resolved',
        after: snapshot(account),
        before,
        entityId: account.id,
        entityType: 'account',
        message: `${account.name} 的异常已解除`,
        metadata: { note: input.note, outcome: input.outcome },
      },
      result: account,
      state,
    };
  }
}

/**
 * Application-facing resource service. Existing Store methods remain the
 * compatibility mutations, while pages call this single domain facade.
 */
function cloneResourceValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export class ResourceService {
  constructor(private readonly adapter: ResourceCommandAdapter) {}

  approveApplication(
    applicationId: string,
    accountIds: readonly string[],
    actor: AuditActor,
  ) {
    return [
      ...this.adapter.approveApplication(applicationId, [...accountIds], actor),
    ];
  }

  createApplication(input: CreateResourceApplicationInput, actor: AuditActor) {
    return cloneResourceValue(this.adapter.createApplication(input, actor));
  }

  findBySourceApplication(sourceApplicationId: string) {
    const normalizedId = sourceApplicationId.trim();
    if (!normalizedId) return undefined;
    const application = this.adapter
      .listApplications()
      .find((item) => item.sourceApplicationId === normalizedId);
    return application ? cloneResourceValue(application) : undefined;
  }

  getApplication(applicationId: string) {
    const normalizedId = applicationId.trim();
    const application = this.adapter
      .listApplications()
      .find((item) => item.id === normalizedId);
    return application ? cloneResourceValue(application) : undefined;
  }

  rejectApplication(applicationId: string, reason: string, actor: AuditActor) {
    return cloneResourceValue(
      this.adapter.rejectApplication(applicationId, reason, actor),
    );
  }

  requestReturn(
    assignmentOrAccountId: string,
    reason: string,
    actor: AuditActor,
  ) {
    return cloneResourceValue(
      this.adapter.requestReturn(assignmentOrAccountId, reason, actor),
    );
  }
}
