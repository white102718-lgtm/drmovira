import type {
  AtomicMaterialInboundInput,
  AtomicMaterialInboundOperation,
  Material,
  MaterialFolderInput,
  MaterialFolderPatch,
  MaterialFolderQuery,
  MaterialFolderRelation,
  MaterialFolderSummary,
  MaterialLibraryFolderPage,
  MaterialLibraryFolderQuery,
  MaterialOrderInboundContext,
  MaterialSelectionPage,
  MaterialSelectionQuery,
} from './types';

/**
 * The formal folder endpoints. Folders are flat, so the adapter never derives
 * an ID from a name and always uses stable parent IDs for nested folders.
 */
export interface MaterialFolderHttpAdapter {
  /** 创建后返回服务端稳定 ID，供选择器直接选中新目录。 */
  createFolder(input: MaterialFolderInput): Promise<string>;
  deleteFolder(folderId: string): Promise<void>;
  /** Every folder the caller may see, already filtered server-side. */
  listFolders(
    query?: MaterialFolderQuery,
  ): Promise<readonly MaterialFolderSummary[]>;
  /** Records an open so the home page can show 最近访问. */
  recordVisit(folderId: string): Promise<void>;
  updateFolder(folderId: string, patch: MaterialFolderPatch): Promise<void>;
}

/**
 * Read-only compatibility contract for materials inside one folder. The old
 * transport remains intact while callers stop depending on its raw response.
 */
export interface MaterialLibraryAdapter {
  listFolderMaterials(
    query: MaterialLibraryFolderQuery,
  ): Promise<MaterialLibraryFolderPage>;
}

/** Read-only source for candidates eligible for the existing Fusion draft. */
export interface MaterialSelectionAdapter {
  listSelectable(query: MaterialSelectionQuery): Promise<MaterialSelectionPage>;
}

/**
 * Formal HTTP compatibility contract. Implementations must keep using stable
 * server material/folder IDs and must not derive either one from filenames.
 */
export interface MaterialInboundAdapter {
  acceptOrder(
    orderId: string,
    rating: number,
  ): Promise<MaterialOrderInboundContext>;
  getOrder(orderId: string): Promise<MaterialOrderInboundContext>;
  listFolderMaterials(
    folderId: string,
    page: number,
    pageSize: number,
  ): Promise<{ items: Material[]; total: number }>;
  listOrderMaterials(orderId: string): Promise<Material[]>;
  submitFolderRelations(input: {
    folderId: string;
    materialIds: readonly string[];
    orderId: string;
    scope: 'personal';
  }): Promise<readonly MaterialFolderRelation[]>;
}

/**
 * The HTTP client for the future formal endpoint is injected deliberately.
 * There is no guessed URL or automatic fallback to legacy writes: the backend
 * team must wire a documented transaction endpoint before this adapter is used
 * by a page.
 */
export interface AtomicMaterialInboundTransport {
  submit(input: AtomicMaterialInboundInput): Promise<unknown>;
}

/**
 * Server-backed Material / FolderRelation transaction contract. A successful
 * response must include immutable operation, relation and audit IDs.
 */
export interface AtomicMaterialInboundAdapter {
  acceptAndAssignAtomically(
    input: AtomicMaterialInboundInput,
  ): Promise<AtomicMaterialInboundOperation>;
}
