import type { MaterialLibraryAdapter } from './adapter';
import type {
  MaterialLibraryFolderPage,
  MaterialLibraryFolderQuery,
} from './types';

import { HttpMaterialLibraryAdapter } from './adapters/library-http';
import { parseMaterialNames } from './name-filter';

function requiredStableId(value: string, field: string): string {
  const normalized = value.trim();
  if (!normalized) throw new Error(`${field}缺少稳定 ID`);
  return normalized;
}

function positiveInteger(value: number, field: string): number {
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${field}必须是正整数`);
  }
  return value;
}

function optionalText(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized || undefined;
}

/** Page-facing read service for folder material content. */
export class MaterialLibraryService {
  constructor(private readonly adapter: MaterialLibraryAdapter) {}

  async listFolderMaterials(
    query: MaterialLibraryFolderQuery,
  ): Promise<MaterialLibraryFolderPage> {
    return await this.adapter.listFolderMaterials({
      basename: parseMaterialNames(
        typeof query.basename === 'string'
          ? query.basename
          : (query.basename ?? []).join('\n'),
      ),
      filetype: optionalText(query.filetype),
      folderId: requiredStableId(query.folderId, '文件夹'),
      page: positiveInteger(query.page, '页码'),
      pageSize: positiveInteger(query.pageSize, '分页大小'),
    });
  }
}

export const httpMaterialLibraryService = new MaterialLibraryService(
  new HttpMaterialLibraryAdapter(),
);
