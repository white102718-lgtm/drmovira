import type { TaskDetail } from '#/api';
import type {
  DeliveryTaskFormData,
  TaskAttachmentMeta,
} from '#/store/task-center';

function formatTaskDateTime(value?: null | string) {
  return value ? value.replace('T', ' ').slice(0, 16) : '';
}

function toAttachmentMeta(
  file: TaskDetail['taskFiles'][number],
): TaskAttachmentMeta {
  return {
    contentType: file.mimeType,
    id: file.id,
    name: file.originalName,
    objectKey: file.id,
    serverFileId: file.id,
    size: file.fileSize,
    type: file.extension || file.mimeType,
  };
}

/**
 * 将正式任务详情投影为任务中心现有的投放计划模型。
 *
 * 列表接口只返回任务摘要，投放计划和创建附件必须以详情接口为准，避免页面刷新后丢失。
 */
export function projectDeliveryTaskDetail(
  detail: TaskDetail,
  projectName: string,
): DeliveryTaskFormData | undefined {
  if (detail.task.taskType !== 'DELIVERY' || !detail.delivery) return;

  return {
    items: detail.delivery.items ?? [],
    allocations: detail.allocations.map((allocation) => ({
      assigneeId: allocation.teamOwnerId,
      assigneeName: allocation.teamOwnerName,
      h5Count: allocation.h5LineCount,
      id: allocation.id,
      owner: allocation.teamOwnerName,
      pwaCount: allocation.pwaLineCount,
      status: allocation.status,
      submittedAt: allocation.submittedAt,
      completedAt: allocation.completedAt,
      team: allocation.teamCode,
      teamName: allocation.teamName,
    })),
    amOwner:
      detail.delivery.amUsers?.map((user) => user.userName).join('、') ||
      detail.delivery.amUserName ||
      '',
    amUsers: detail.delivery.amUsers ?? [],
    attachments: detail.taskFiles
      .filter(
        (file) =>
          file.targetType === 'DELIVERY_TASK' &&
          file.targetId === detail.task.id,
      )
      .map((file) => toAttachmentMeta(file)),
    dueAt: formatTaskDateTime(detail.task.dueAt),
    ownerId: detail.task.ownerId,
    ownerName: detail.task.ownerName,
    platforms: [...detail.platforms],
    productUrl: detail.delivery.productUrl,
    projectId: detail.task.projectId,
    projectName,
    region: detail.delivery.region,
    startAt: formatTaskDateTime(detail.delivery.plannedStartAt),
    target: detail.delivery.target,
    title: detail.task.title,
  };
}
