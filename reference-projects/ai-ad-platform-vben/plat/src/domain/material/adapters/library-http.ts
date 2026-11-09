import type { MaterialLibraryAdapter } from '../adapter';
import type {
  MaterialLibraryFolderItem,
  MaterialLibraryFolderPage,
  MaterialLibraryFolderQuery,
} from '../types';

import { listFolderMaterialsApi } from '#/api';

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

function readItems(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const record = unwrap(value);
  for (const key of ['items', 'materials', 'results']) {
    if (Array.isArray(record?.[key])) return record[key] as unknown[];
  }
  return [];
}

function readStableMaterialId(record: Record<string, unknown>): string {
  return (
    readText(record.id) ||
    readText(record._id) ||
    readText(record.material_id) ||
    readText(record.file_id)
  );
}

function normalizePage(value: unknown): MaterialLibraryFolderPage {
  const record = unwrap(value);
  const items: MaterialLibraryFolderItem[] = [];
  for (const valueItem of readItems(value)) {
    const legacy = asRecord(valueItem);
    if (!legacy) continue;
    const id = readStableMaterialId(legacy);
    // A filename/basename is presentation data, never an ID substitute.
    if (!id) continue;
    items.push({ id, legacy: structuredClone(legacy) });
  }
  const total = Number(record?.total);
  return { items, total: Number.isFinite(total) ? total : items.length };
}

/**
 * Formal page boundary over the established `material-folders/:id/materials`
 * route. It is read-only and deliberately does not infer FolderRelation rows.
 */
export class HttpMaterialLibraryAdapter implements MaterialLibraryAdapter {
  async listFolderMaterials(
    query: MaterialLibraryFolderQuery,
  ): Promise<MaterialLibraryFolderPage> {
    return normalizePage(
      await listFolderMaterialsApi(query.folderId, query.page, query.pageSize, {
        basename: query.basename,
        filetype: query.filetype,
      }),
    );
  }
}

export const httpMaterialLibraryAdapter = new HttpMaterialLibraryAdapter();
