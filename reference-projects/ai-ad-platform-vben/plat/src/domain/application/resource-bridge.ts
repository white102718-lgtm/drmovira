import type { ResourceApplication } from './types';

import type {
  AuditActor,
  MediaPlatform,
  ResourceApplication as MediaResourceApplication,
} from '#/domain/resource';

import { ResourceService } from '#/domain/resource';

import { ApplicationService } from './service';

export interface ApplicationResourceBridgeResult {
  kind: 'created' | 'existing' | 'not-applicable';
  resourceApplication?: MediaResourceApplication;
}

function toMediaPlatform(platform?: string): MediaPlatform {
  const normalized = platform?.trim().toLowerCase();
  if (
    normalized === 'facebook' ||
    normalized === 'google' ||
    normalized === 'kwai' ||
    normalized === 'tiktok'
  ) {
    return normalized;
  }
  throw new Error('广告账号申请缺少受支持的媒体平台');
}

function requireResourceRequest(application: ResourceApplication) {
  const request = application.resourceRequest;
  if (
    !request?.assigneeId.trim() ||
    !request.assigneeName.trim() ||
    !request.teamId.trim() ||
    !request.teamName.trim()
  ) {
    throw new Error('广告账号申请缺少使用人或团队的稳定资源交付信息');
  }
  if (!application.projectId?.trim()) {
    throw new Error('广告账号申请缺少稳定项目 ID，不能进入资源生命周期');
  }
  if (!application.requesterId?.trim() || !application.requesterName?.trim()) {
    throw new Error('广告账号申请缺少稳定申请人，不能进入资源生命周期');
  }
  const requestedAccountCount = application.quantity;
  if (!requestedAccountCount || requestedAccountCount < 1) {
    throw new Error('广告账号申请数量必须大于 0');
  }
  return {
    projectId: application.projectId,
    requestedAccountCount,
    requesterId: application.requesterId,
    requesterName: application.requesterName,
    request,
  };
}

/**
 * Coordinates two legacy write owners without copying either object. The
 * generic application holds only the child ID; the media lifecycle retains
 * the source ID. A retry first recovers the child by source ID, so a failure
 * between the two compatible writes cannot create duplicate applications.
 */
export class ApplicationResourceBridgeService {
  constructor(
    private readonly applications: ApplicationService,
    private readonly resources: ResourceService,
  ) {}

  completeResourceApproval(
    resourceApplicationId: string,
    accountIds: readonly string[],
    actor: AuditActor,
  ) {
    const assignmentIds = this.resources.approveApplication(
      resourceApplicationId,
      accountIds,
      actor,
    );
    const resourceApplication = this.resources.getApplication(
      resourceApplicationId,
    );
    const parent = this.applications
      .list()
      .find(
        (application) =>
          application.resourceApplicationId === resourceApplicationId,
      );
    if (
      parent?.status === 'processing' &&
      resourceApplication?.status === 'approved'
    ) {
      this.applications.save({ ...parent, status: 'approved' });
    }
    return assignmentIds;
  }

  handoffAfterApproval(
    applicationId: string,
    actor: AuditActor,
  ): ApplicationResourceBridgeResult {
    const application = this.applications.get(applicationId);
    if (application.type !== 'account' || !application.resourceRequest) {
      return { kind: 'not-applicable' };
    }
    if (!['approved', 'processing'].includes(application.status)) {
      throw new Error('广告账号申请尚未完成业务审批，不能进入资源生命周期');
    }
    if (application.resourceApplicationId) {
      const existing = this.resources.getApplication(
        application.resourceApplicationId,
      );
      if (existing) return { kind: 'existing', resourceApplication: existing };
    }

    const recovered = this.resources.findBySourceApplication(application.id);
    if (recovered) {
      this.applications.save({
        ...application,
        resourceApplicationId: recovered.id,
        status: recovered.status === 'approved' ? 'approved' : 'processing',
      });
      return { kind: 'existing', resourceApplication: recovered };
    }

    const {
      projectId,
      requestedAccountCount,
      requesterId,
      requesterName,
      request,
    } = requireResourceRequest(application);
    const created = this.resources.createApplication(
      {
        assigneeId: request.assigneeId,
        assigneeName: request.assigneeName,
        expectedReturnAt: request.expectedReturnAt,
        platform: toMediaPlatform(application.platform),
        projectId,
        projectName: application.project,
        reason: application.description,
        requestedAccountCount,
        requestedById: requesterId,
        requestedByName: requesterName,
        sourceApplicationId: application.id,
        sourceTaskId: application.sourceTaskId,
        teamId: request.teamId,
        teamName: request.teamName,
        timezone: request.timezone,
        title: application.title,
        whitelistRequired: request.whitelistRequired,
      },
      actor,
    );
    this.applications.save({
      ...application,
      resourceApplicationId: created.id,
      status: 'processing',
    });
    return { kind: 'created', resourceApplication: created };
  }

  rejectResourceApplication(
    resourceApplicationId: string,
    reason: string,
    actor: AuditActor,
  ) {
    const rejected = this.resources.rejectApplication(
      resourceApplicationId,
      reason,
      actor,
    );
    const parent = this.applications
      .list()
      .find(
        (application) =>
          application.resourceApplicationId === resourceApplicationId,
      );
    if (parent?.status === 'processing') {
      this.applications.save({ ...parent, status: 'rejected' });
    }
    return rejected;
  }
}
