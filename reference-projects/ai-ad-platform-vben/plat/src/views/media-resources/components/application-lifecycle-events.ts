import type {
  AccountLifecycleApplication,
  AssetLifecycleDetail,
} from '#/api/asset-flow';

function completedApplicationEventType(applicationCode: string) {
  if (applicationCode.includes('RECYCLE')) return 'RETURN_COMPLETED';
  if (applicationCode.includes('RECHARGE')) return 'RECHARGE_COMPLETED';
  return 'OPERATION_COMPLETED';
}

/** 每张申请仅在最终办理成功后生成一条生命周期事件。 */
export function successfulApplicationEvents(
  application: AccountLifecycleApplication,
): AssetLifecycleDetail['events'] {
  if (application.status !== 'APPROVED') return [];

  const reversedActions = [...(application.actions ?? [])].reverse();
  const completedAction = reversedActions.find(
    (action) => action.action === 'COMPLETED',
  );
  const legacyApproval = reversedActions.find(
    (action) => action.action === 'APPROVED',
  );
  const finalAction = completedAction ?? legacyApproval;
  const occurredAt =
    completedAction?.createdAt ??
    application.decidedAt ??
    legacyApproval?.createdAt;
  if (!occurredAt) return [];

  const applicationCode = (application.applicationCode ?? '').toUpperCase();
  return [
    {
      actorName: finalAction?.actorName,
      amount: application.amount,
      applicationId: application.applicationId,
      currency: application.currency,
      description: application.title,
      eventType: completedApplicationEventType(applicationCode),
      formFields: application.formFields,
      id: `application-${application.applicationId}-completed`,
      nodeName: finalAction?.nodeName,
      occurredAt,
      remark: finalAction?.remark,
      status: completedAction ? 'COMPLETED' : 'APPROVED',
    },
  ];
}
