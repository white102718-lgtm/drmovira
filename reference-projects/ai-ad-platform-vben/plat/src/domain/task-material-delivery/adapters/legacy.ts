import { useUserStore } from '@vben/stores';

import type { TaskMaterialDeliveryAdapter } from '../adapter';
import type {
  MaterialDeliveryFile,
  MaterialDeliverySubmission,
  MaterialDeliverySubmitInput,
  MaterialOrderDeliveryContext,
} from '../types';

import {
  deliverMaterialOrder,
  getMaterialOrderDetail,
} from '#/api/requirement';

function asObject(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : undefined;
}

function unwrap(value: unknown): Record<string, unknown> | undefined {
  const candidate = asObject(value);
  if (!candidate) return;
  return asObject(candidate.data) ?? candidate;
}

function readText(value: unknown) {
  return typeof value === 'string' ? value.trim() : '';
}

function readNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function toLegacyMaterial(file: MaterialDeliveryFile, assignmentId?: string) {
  return {
    basename: file.basename,
    content_type: file.contentType,
    duration: file.duration,
    filename: file.name,
    file_md5: file.fileMd5,
    filetype: file.filetype,
    height: file.height,
    img: file.img,
    object_key: file.objectKey,
    assignment_id: assignmentId ?? '',
    sha3_256: file.sha3_256,
    size: file.size,
    url: file.url,
    width: file.width,
  };
}

function readAssignmentOptions(
  detail: Record<string, unknown>,
): MaterialOrderDeliveryContext['assignmentOptions'] {
  if (asObject(detail.permissions)?.upload === false) return [];
  const records = Array.isArray(detail.assignments) ? detail.assignments : [];
  const requirements = Array.isArray(detail.requirements)
    ? detail.requirements
    : [];
  const userId = String(useUserStore().userInfo?.userId ?? '');
  return records.flatMap((value) => {
    const record = asObject(value);
    if (
      !record ||
      record.designer_user_id !== userId ||
      !['in_production', 'rejected', 'submitted', 'accepted'].includes(
        readText(record.status),
      )
    )
      return [];
    const requirement = requirements
      .map(asObject)
      .find((item) => item?.id === record.req_id);
    const id = readText(record.id);
    if (!id) return [];
    return [
      {
        value: id,
        label: `${readText(requirement?.seq_label) || '子需求'} · ${Number(record.quantity) || 0} 条`,
        designer: readText(record.designer_name),
        creativePlanner: readText(record.creative_planner_name),
        remark: readText(record.remark),
      },
    ];
  });
}

/**
 * Preserves the current `/material-orders/*` API surface. A future formal
 * task-deliverable API can replace this adapter without changing Task Center
 * routes, storage keys, or MaterialOrder pages.
 */
export class LegacyTaskMaterialDeliveryAdapter
  implements TaskMaterialDeliveryAdapter
{
  async deliver(
    input: MaterialDeliverySubmitInput,
  ): Promise<MaterialDeliverySubmission> {
    const response = await deliverMaterialOrder(
      input.orderId,
      input.files.map((file) => toLegacyMaterial(file, input.assignmentId)),
      input.designer,
      input.creativePlanner,
    );
    const result = unwrap(response);
    const id =
      readText(result?.delivery_id) ||
      readText(result?.deliverable_id) ||
      readText(result?.id);
    const version = readNumber(result?.version_no);

    return {
      creativePlanner: input.creativePlanner,
      designer: input.designer,
      files: input.files.map((file) => ({ ...file })),
      ...(id ? { formalDeliveryId: id } : {}),
      ...(version === undefined ? {} : { formalVersionNo: version }),
      orderId: input.orderId,
      assignmentId: input.assignmentId,
      status: 'pending_accept',
      submittedAt: new Date().toLocaleString('zh-CN', { hour12: false }),
    };
  }

  async getContext(orderId: string): Promise<MaterialOrderDeliveryContext> {
    const detail = unwrap(await getMaterialOrderDetail(orderId));
    if (!detail) throw new Error('素材订单详情格式无效');

    const resolvedOrderId =
      readText(detail.id) || readText(detail._id) || orderId;
    return {
      demandType: readText(detail.demand_type) || readText(detail.type),
      orderId: resolvedOrderId,
      assignmentOptions: readAssignmentOptions(detail),
      status: readText(detail.status),
      title: readText(detail.title) || resolvedOrderId,
    };
  }
}
