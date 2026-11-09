import type {
  ApprovalCcUser,
  ApprovalListItem,
  AssetApplication,
} from '#/api/asset-flow';
import { PROJECT_CLOSURE_APPLICATION_CODE } from '#/domain/project';
import type {
  ApplicationStatus,
  ApplicationType,
  ApprovalAction,
  ResourceApplication,
} from '#/store/resource-applications';

interface BackendApplicationFallbackIdentity {
  name: string;
  roleLabel: string;
}

interface BackendApplicationDecision {
  action: 'approved' | 'rejected';
  remark: string;
}

function backendApprovalAction(action: string): ApprovalAction {
  if (action === 'SUBMITTED') return 'submitted';
  if (action === 'REJECTED') return 'rejected';
  if (action === 'COMPLETED') return 'completed';
  if (action === 'COPIED') return 'copied';
  return 'approved';
}

/** 保留停用或历史失效抄送人的可辨识状态，避免名单被静默隐藏。 */
function backendCcUserLabel(user: ApprovalCcUser) {
  const displayName = user.displayName.trim() || `用户 ${user.id}`;
  if (!user.resolved) return `${displayName}（已无法解析）`;
  if (!user.active) return `${displayName}（已停用）`;
  return displayName;
}

/**
 * 将后端审批申请转换成工作台统一申请模型。
 *
 * @remarks
 * 列表和详情页必须共用同一转换规则，避免路由快照让已驳回或已办理申请显示旧状态。
 */
export function mapBackendApplication(
  item: AssetApplication,
  fallbackIdentity: BackendApplicationFallbackIdentity,
  decision?: BackendApplicationDecision,
): ResourceApplication {
  let type: ApplicationType = 'account';
  if (item.assetType === PROJECT_CLOSURE_APPLICATION_CODE) type = 'project';
  if (item.assetType === 'PIXEL') type = 'pixel';
  if (item.assetType === 'TG') type = 'tg';
  if (item.formData?.configCategory === 'office') type = 'computer';
  if (item.formData?.configCategory === 'finance') type = 'payment';

  let status: ApplicationStatus = 'pending';
  if (item.status === 'APPROVED') status = 'approved';
  if (item.status === 'PROCESSING') status = 'processing';
  if (item.status === 'REJECTED') status = 'rejected';

  const currentIndex = item.currentNodeIndex ?? 0;
  // 办理阶段驳回不应回写成审批节点驳回；此时全部审批节点已经通过。
  const rejectedDuringHandling = item.approvalLogs?.some(
    (log) => log.action === 'REJECTED' && log.nodeName === '业务办理',
  );
  const resolvedDecision =
    decision ??
    (item.status === 'APPROVED' || item.status === 'REJECTED'
      ? {
          action:
            item.status === 'APPROVED'
              ? ('approved' as const)
              : ('rejected' as const),
          remark: item.decisionRemark ?? '审批流程已处理',
        }
      : undefined);
  const nodeStatus = (
    index: number,
  ): ResourceApplication['approvalNodes'][number]['status'] => {
    if (
      status === 'approved' ||
      status === 'processing' ||
      rejectedDuringHandling ||
      index < currentIndex
    ) {
      return 'approved';
    }
    if (status === 'rejected' && index === currentIndex) return 'rejected';
    if (index === currentIndex) return 'pending';
    return 'waiting';
  };
  const nodes = item.nodes?.length
    ? item.nodes.map((node, index) => ({
        approver: node.approverName,
        approverId: String(node.approverId),
        id: node.id ?? `NODE-${item.id}-${index}`,
        label: node.name,
        role: 'media' as const,
        status: nodeStatus(index),
      }))
    : [
        {
          approver: item.approverName,
          approverId: String(item.approverId),
          id: `NODE-${item.id}`,
          label: '资产审批',
          role: 'media' as const,
          status: nodeStatus(0),
        },
      ];
  const approvalRecords: ResourceApplication['approvalRecords'] = [];
  if (item.approvalLogs?.length) {
    approvalRecords.push(
      ...item.approvalLogs.map((log) => ({
        action: backendApprovalAction(log.action),
        actionData: log.actionData,
        actor: log.actorName,
        actorId: String(log.actorId),
        actorRole:
          log.nodeName ||
          (log.action === 'COMPLETED' ? '资产处理与分配' : '审批流程'),
        at: log.createdAt,
        id: String(log.id),
        nodeIndex: log.nodeIndex,
        remark:
          log.action === 'COMPLETED'
            ? `处理完成：${log.remark || '资产已分配'}`
            : log.remark || '流程状态已更新',
      })),
    );
  }
  if (item.transferRecords?.length) {
    approvalRecords.push(
      ...item.transferRecords.map((record) => ({
        action: 'transferred' as const,
        actor: record.actorName,
        actorId: String(record.actorId),
        actorRole: record.nodeIndex >= nodes.length ? '办理人' : '审批人',
        at: record.at,
        id: String(record.id),
        nodeIndex: record.nodeIndex,
        recipientDepartmentId: record.recipientDepartmentId,
        recipientDepartmentName: record.recipientDepartmentName,
        recipientId: String(record.recipientId),
        recipientName: record.recipientName,
        remark: record.remark,
      })),
    );
  }
  if (approvalRecords.length === 0 && resolvedDecision) {
    approvalRecords.push({
      action: resolvedDecision.action,
      actor: item.approverName || fallbackIdentity.name,
      actorRole: fallbackIdentity.roleLabel,
      at: item.updatedAt ?? new Date().toISOString(),
      id: `APR-${item.id}-${Date.now()}`,
      remark: resolvedDecision.remark,
    });
  }
  const ccUsers = (item.ccUsers ?? []).map(backendCcUserLabel);
  if (
    ['approved', 'processing', 'rejected'].includes(status) &&
    ccUsers.length > 0 &&
    !approvalRecords.some((record) => record.action === 'copied')
  ) {
    // 这是从申请快照派生的只读展示记录，不会回写审批日志或补发历史通知。
    approvalRecords.push({
      action: 'copied',
      actor: '系统通知',
      actorRole: '抄送',
      at: item.updatedAt ?? item.createdAt,
      id: `CC-${item.id}`,
      remark: `审批结果已抄送：${ccUsers.join('、')}`,
    });
  }

  return {
    allocatedAssets: item.allocatedAssets?.map((asset) => ({
      assetCode: asset.assetCode,
      assetName: asset.assetName,
      assetType: asset.assetType,
      channelName: asset.channelName,
      id: String(asset.id),
      projectName: asset.projectName,
    })),
    approvalNodes: nodes,
    approvalRecords,
    approvalRole: 'media',
    approver:
      item.status === 'PROCESSING' ? item.handlerName : item.approverName,
    ccUsers,
    comments: [],
    createdAt: item.createdAt,
    departmentId: item.departmentId,
    departmentName: item.departmentName,
    description: item.reason,
    formData: item.formData,
    formSchema: item.formSchema,
    handlerAction: item.handlerAction,
    handlerApprovalNodeId: item.handlerApprovalNodeId,
    handlerId: String(item.handlerId),
    handlerName: item.handlerName,
    handlerSource: item.handlerSource,
    id: String(item.id),
    platform: item.assetType,
    project: String(
      item.formData?.channelName ??
        item.formData?.projectName ??
        item.formData?.project ??
        '未指定归属',
    ),
    projectId: String(
      item.formData?.channelId ?? item.formData?.projectId ?? '',
    ),
    quantity: item.quantity,
    requester: item.requesterName,
    requesterId: String(item.requesterId),
    requesterName: item.requesterName,
    sourceApplicationId: item.sourceApplicationId,
    status,
    title: item.title,
    type,
    updatedAt: item.updatedAt ?? item.createdAt,
  };
}

/** 将分页接口的轻量摘要映射为列表卡片模型，不伪造详情数据。 */
export function mapBackendApprovalListItem(
  item: ApprovalListItem,
  fallbackIdentity: BackendApplicationFallbackIdentity,
): ResourceApplication {
  return mapBackendApplication(
    {
      applicationNo: item.applicationNo,
      approverId: item.approverId ?? '',
      approverName: item.approverName ?? '',
      assetType: item.assetType,
      ccUsers: item.ccUsers,
      createdAt: item.createdAt,
      departmentId: item.departmentId,
      departmentName: item.departmentName,
      formData: {
        applicationDefinitionId: item.applicationDefinitionId,
        configCategory: item.configCategory,
        projectName: item.projectName,
      },
      handlerId: '',
      handlerName: '',
      id: item.id,
      quantity: item.quantity,
      reason: item.reason,
      requesterId: item.requesterId,
      requesterName: item.requesterName,
      status: item.status,
      title: item.title,
      updatedAt: item.updatedAt,
    },
    fallbackIdentity,
  );
}
