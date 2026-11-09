import type { MaterialFolderHttpAdapter } from '../adapter';
import type {
  MaterialFolderInput,
  MaterialFolderPatch,
  MaterialFolderQuery,
  MaterialFolderScope,
  MaterialFolderSummary,
  MaterialFolderVisibility,
} from '../types';

import {
  createFolderApi,
  deleteFolderApi,
  listFoldersApi,
  updateFolderApi,
  visitFolderApi,
} from '#/api';

const SCOPES = new Set<MaterialFolderScope>(['department', 'personal']);
const VISIBILITIES = new Set<MaterialFolderVisibility>([
  'department',
  'organization',
  'private',
]);

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function readText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function unwrap(value: unknown): Record<string, unknown> | undefined {
  const record = asRecord(value);
  return asRecord(record?.data) ?? record;
}

function listValue(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const record = unwrap(value);
  for (const key of ['items', 'results', 'folders']) {
    if (Array.isArray(record?.[key])) return record[key] as unknown[];
  }
  return [];
}

function readCount(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.trunc(parsed) : 0;
}

/**
 * Unknown or missing scope/visibility fall back to the most private reading —
 * a folder must never look more widely shared than the server said it was.
 */
function readScope(value: unknown): MaterialFolderScope {
  const text = readText(value) as MaterialFolderScope;
  return SCOPES.has(text) ? text : 'personal';
}

function readVisibility(value: unknown): MaterialFolderVisibility {
  const text = readText(value) as MaterialFolderVisibility;
  return VISIBILITIES.has(text) ? text : 'private';
}

function optional(value: unknown): string | undefined {
  return readText(value) || undefined;
}

/** 兼容层级字段上线前的旧数据：缺失或异常值一律按根目录展示。 */
function readFolderLevel(value: unknown): 0 | 1 | 2 {
  const parsed = typeof value === 'number' ? value : Number(value);
  return parsed === 1 || parsed === 2 ? parsed : 0;
}

function normalizeFolder(value: unknown): MaterialFolderSummary | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const id = readText(record.id) || readText(record._id);
  if (!id) return undefined;
  return {
    id,
    name: readText(record.name) || id,
    owner: readText(record.owner),
    isOwner: record.is_owner === true,
    level: readFolderLevel(record.level),
    scope: readScope(record.scope),
    visibility: readVisibility(record.visibility),
    materialCount: readCount(record.material_count),
    ...(record.matched_material_count !== undefined
      ? { matchedMaterialCount: readCount(record.matched_material_count) }
      : {}),
    path: Array.isArray(record.path)
      ? record.path.flatMap((entry) => {
          const part = asRecord(entry);
          const id = readText(part?.id);
          const name = readText(part?.name);
          return id && name ? [{ id, name }] : [];
        })
      : [],
    ...(optional(record.owner_department)
      ? { ownerDepartment: optional(record.owner_department) }
      : {}),
    ...(optional(record.parent_id)
      ? { parentId: optional(record.parent_id) }
      : {}),
    ...(optional(record.color) ? { color: optional(record.color) } : {}),
    ...(optional(record.last_visited_at)
      ? { lastVisitedAt: optional(record.last_visited_at) }
      : {}),
    ...(optional(record.created_at)
      ? { createdAt: optional(record.created_at) }
      : {}),
    ...(optional(record.updated_at)
      ? { updatedAt: optional(record.updated_at) }
      : {}),
  };
}

function requireFolderId(folderId: string): string {
  const normalized = folderId.trim();
  if (!normalized) throw new Error('文件夹缺少稳定 ID');
  return normalized;
}

function requireFolderName(name: string): string {
  const normalized = name.trim();
  if (!normalized) throw new Error('文件夹名称不能为空');
  return normalized;
}

export class HttpMaterialFolderAdapter implements MaterialFolderHttpAdapter {
  async createFolder(input: MaterialFolderInput): Promise<string> {
    const response = await createFolderApi({
      name: requireFolderName(input.name),
      scope: input.scope,
      visibility: input.visibility,
      color: input.color?.trim() || null,
      ...(input.parentId?.trim()
        ? { parent_id: requireFolderId(input.parentId) }
        : {}),
    });
    const id = readText(unwrap(response)?.id);
    if (!id) throw new Error('文件夹已创建，但未返回 ID，请刷新目录后选择');
    return id;
  }

  async deleteFolder(folderId: string): Promise<void> {
    await deleteFolderApi(requireFolderId(folderId));
  }

  async listFolders(
    query: MaterialFolderQuery = {},
  ): Promise<readonly MaterialFolderSummary[]> {
    // 空串会被后端当成有效筛选，统一转成不传
    const params = {
      ...(query.basenames?.length ? { basename: query.basenames } : {}),
      ...(query.folderId ? { folder_id: requireFolderId(query.folderId) } : {}),
      ...(query.keyword?.trim() ? { keyword: query.keyword.trim() } : {}),
      ...(query.owner?.trim() ? { owner: query.owner.trim() } : {}),
      ...(query.parentId?.trim()
        ? { parent_id: requireFolderId(query.parentId) }
        : {}),
      ...(query.scope ? { scope: query.scope } : {}),
    };
    const response = await listFoldersApi(params);
    return listValue(response)
      .map((item) => normalizeFolder(item))
      .filter(
        (folder): folder is MaterialFolderSummary => folder !== undefined,
      );
  }

  async recordVisit(folderId: string): Promise<void> {
    await visitFolderApi(requireFolderId(folderId));
  }

  async updateFolder(
    folderId: string,
    patch: MaterialFolderPatch,
  ): Promise<void> {
    const payload: Record<string, unknown> = {};
    if (patch.name !== undefined) payload.name = requireFolderName(patch.name);
    if (patch.scope !== undefined) payload.scope = patch.scope;
    if (patch.visibility !== undefined) payload.visibility = patch.visibility;
    if (patch.color !== undefined) payload.color = patch.color?.trim() || null;
    await updateFolderApi(requireFolderId(folderId), payload);
  }
}

export const httpMaterialFolderAdapter = new HttpMaterialFolderAdapter();
