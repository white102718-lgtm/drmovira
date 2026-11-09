import type { MaterialInboundAdapter } from '../adapter';
import type {
  Material,
  MaterialFolderRelation,
  MaterialOrderInboundContext,
  MaterialOrderInboundStatus,
} from '../types';

import { listFolderMaterialsApi } from '#/api';
import {
  acceptMaterialOrder,
  assignMaterialsApi,
  getMaterialOrderDetail,
  getMaterialOrderMaterials,
} from '#/api/requirement';

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function unwrap(value: unknown): Record<string, unknown> | undefined {
  const record = asRecord(value);
  if (!record) return;
  return asRecord(record.data) ?? record;
}

function readText(value: unknown) {
  return typeof value === 'string' ? value.trim() : '';
}

function readNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : undefined;
}

function readItems(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const record = unwrap(value);
  for (const key of ['items', 'materials', 'results']) {
    if (Array.isArray(record?.[key])) return record[key] as unknown[];
  }
  if (Array.isArray(record?.groups)) {
    return record.groups.flatMap((group) => {
      const groupRecord = asRecord(group);
      return Array.isArray(groupRecord?.materials)
        ? (groupRecord.materials as unknown[])
        : [];
    });
  }
  return [];
}

function normalizeStatus(value: unknown): MaterialOrderInboundStatus {
  const status = readText(value).toLowerCase();
  if (status === 'accepted') return 'accepted';
  if (status === 'archived') return 'archived';
  if (status === 'pending_accept' || status === 'pending_acceptance') {
    return 'pending_accept';
  }
  return 'unknown';
}

function toMaterial(
  value: unknown,
  sourceOrderId?: string,
): Material | undefined {
  const record = asRecord(value);
  if (!record) return;
  const id =
    readText(record.id) ||
    readText(record._id) ||
    readText(record.material_id) ||
    readText(record.file_id);
  // A filename/basename may be shown, but must never become a stable ID.
  if (!id) return;
  const name =
    readText(record.filename) ||
    readText(record.name) ||
    readText(record.basename) ||
    id;
  const size = readNumber(record.size);
  return {
    ...(readText(record.basename)
      ? { basename: readText(record.basename) }
      : {}),
    ...(readText(record.content_type)
      ? { contentType: readText(record.content_type) }
      : {}),
    ...(readText(record.file_md5)
      ? { fileMd5: readText(record.file_md5) }
      : {}),
    ...(readText(record.filetype)
      ? { filetype: readText(record.filetype) }
      : {}),
    id,
    ...(readText(record.img) ? { img: readText(record.img) } : {}),
    name,
    ...(readText(record.object_key)
      ? { objectKey: readText(record.object_key) }
      : {}),
    ...(readText(record.sha3_256)
      ? { sha3_256: readText(record.sha3_256) }
      : {}),
    ...(size === undefined ? {} : { size }),
    ...(sourceOrderId ? { sourceOrderId } : {}),
    ...(readText(record.url) ? { url: readText(record.url) } : {}),
  };
}

function toOrderContext(
  response: unknown,
  fallbackOrderId: string,
): MaterialOrderInboundContext {
  const record = unwrap(response);
  const orderId =
    readText(record?.id) || readText(record?._id) || fallbackOrderId;
  return {
    orderId,
    status: normalizeStatus(record?.status),
    title: readText(record?.title) || orderId,
  };
}

/**
 * Bridges the established MaterialOrder and material-folder endpoints. It is
 * deliberately additive: the old route/API names remain the transport layer
 * until the backend publishes one atomic Material/FolderRelation endpoint.
 */
export class HttpMaterialInboundAdapter implements MaterialInboundAdapter {
  async acceptOrder(orderId: string, rating: number) {
    const response = await acceptMaterialOrder(orderId, {
      action: 'pass',
      rating,
    });
    const context = toOrderContext(response, orderId);
    return {
      ...context,
      // Legacy successful responses sometimes omit `status`; the accepted
      // action is still the established transition requested by this call.
      status: context.status === 'unknown' ? 'accepted' : context.status,
    };
  }

  async getOrder(orderId: string) {
    return toOrderContext(await getMaterialOrderDetail(orderId), orderId);
  }

  async listFolderMaterials(folderId: string, page: number, pageSize: number) {
    const response = await listFolderMaterialsApi(folderId, page, pageSize);
    const record = unwrap(response);
    const items = readItems(response).flatMap((item) => {
      const material = toMaterial(item);
      return material ? [material] : [];
    });
    const total = Number(record?.total);
    return {
      items,
      total: Number.isFinite(total) ? total : items.length,
    };
  }

  async listOrderMaterials(orderId: string) {
    const response = await getMaterialOrderMaterials(orderId);
    return readItems(response).flatMap((item) => {
      const material = toMaterial(item, orderId);
      return material ? [material] : [];
    });
  }

  async submitFolderRelations(input: {
    folderId: string;
    materialIds: readonly string[];
    orderId: string;
    scope: 'personal';
  }): Promise<readonly MaterialFolderRelation[]> {
    await assignMaterialsApi(input.orderId, {
      folder_id: input.folderId,
      ids: [...input.materialIds],
      scope: input.scope,
    });
    return input.materialIds.map((materialId) => ({
      folderId: input.folderId,
      materialId,
      sourceOrderId: input.orderId,
      writeStatus: 'submitted' as const,
    }));
  }
}

export const httpMaterialInboundAdapter = new HttpMaterialInboundAdapter();
