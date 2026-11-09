import type { MaterialFolderHttpAdapter } from './adapter';
import type {
  MaterialFolderInput,
  MaterialFolderPatch,
  MaterialFolderQuery,
} from './types';

import { HttpMaterialFolderAdapter } from './adapters/folder-http';

/** Page-facing formal folder API service. */
export class HttpFolderService {
  constructor(private readonly adapter: MaterialFolderHttpAdapter) {}

  create(input: MaterialFolderInput) {
    return this.adapter.createFolder(input);
  }

  delete(folderId: string) {
    return this.adapter.deleteFolder(folderId);
  }

  list(query?: MaterialFolderQuery) {
    return this.adapter.listFolders(query);
  }

  recordVisit(folderId: string) {
    return this.adapter.recordVisit(folderId);
  }

  update(folderId: string, patch: MaterialFolderPatch) {
    return this.adapter.updateFolder(folderId, patch);
  }
}

export const httpFolderService = new HttpFolderService(
  new HttpMaterialFolderAdapter(),
);
