import type { MaterialSelectionAdapter } from '../adapter';
import type {
  MaterialApprovalStatus,
  MaterialSelectionPage,
  MaterialSelectionQuery,
  SelectableMaterial,
} from '../types';

import { listMaterialApi } from '#/api/materials';

type UnknownRecord = Record<string, unknown>;

function object(value: unknown): undefined | UnknownRecord {
  return value && typeof value === 'object'
    ? (value as UnknownRecord)
    : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stableId(record: UnknownRecord): string | undefined {
  for (const key of ['id', '_id', 'material_id', 'file_id'] as const) {
    const id = text(record[key]);
    if (id) return id;
  }
  return undefined;
}

function approvalStatus(record: UnknownRecord): MaterialApprovalStatus {
  const raw = text(
    record.approval_status ??
      record.audit_status ??
      record.review_status ??
      record.status,
  )?.toLowerCase();
  if (!raw) return 'unknown';
  if (['accepted', 'approved', 'passed', '审核通过', '已审核'].includes(raw)) {
    return 'approved';
  }
  if (['failed', 'rejected', '审核拒绝', '已拒绝'].includes(raw)) {
    return 'rejected';
  }
  if (['pending', 'pending_review', 'reviewing', '待审核'].includes(raw)) {
    return 'pending_review';
  }
  return 'unknown';
}

function responseItems(response: unknown): unknown[] {
  const root = object(response);
  const data = object(root?.data);
  return array(root?.items ?? root?.results ?? data?.items ?? data?.results);
}

function responseTotal(response: unknown, fallback: number): number {
  const root = object(response);
  const data = object(root?.data);
  const total = root?.total ?? data?.total;
  return typeof total === 'number' && Number.isFinite(total) ? total : fallback;
}

function normalize(
  raw: unknown,
  projectId: string,
): SelectableMaterial | undefined {
  const record = object(raw);
  if (!record) return;
  const id = stableId(record);
  const returnedProjectId = text(record.project_id ?? record.projectId);
  // Old material API responses without a stable project relation are unsafe
  // for ad creation. Do not use a filename or a display label as a fallback.
  if (!id || returnedProjectId !== projectId) return;
  const status = approvalStatus(record);
  if (status !== 'approved') return;
  return {
    approvalStatus: status,
    id,
    materialId: text(record.material_id ?? record.materialId),
    name:
      text(record.name ?? record.filename ?? record.basename) ?? `素材 ${id}`,
    projectId,
    ratio: text(record.ratio ?? record.aspect_ratio),
    source: 'formal-material-api',
    type: text(record.filetype ?? record.type ?? record.content_type),
  };
}

/** Uses the preserved `materials/` facade; no new endpoint is guessed. */
export class HttpMaterialSelectionAdapter implements MaterialSelectionAdapter {
  async listSelectable(
    query: MaterialSelectionQuery,
  ): Promise<MaterialSelectionPage> {
    const projectId = query.projectId.trim();
    if (!projectId) throw new Error('素材选择缺少稳定项目 ID');
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 100;
    const response = await listMaterialApi({
      page,
      pageSize,
      project_id: projectId,
    });
    const items = responseItems(response)
      .map((item) => normalize(item, projectId))
      .filter(Boolean) as SelectableMaterial[];
    return { items, total: responseTotal(response, items.length) };
  }
}
