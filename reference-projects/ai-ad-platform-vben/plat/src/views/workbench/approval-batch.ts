import type { ResourceApplication } from '#/domain/application';

/** 仅将可由服务端在同一事务中处理的申请纳入批量审批。 */
export function isBatchDecisionEligible(
  application: ResourceApplication,
  canApprove: boolean,
  isBackendApplication: boolean,
) {
  return (
    application.status === 'pending' &&
    canApprove &&
    isBackendApplication &&
    /^\d+$/.test(application.id)
  );
}
