export type MaterialFolderScope = 'department' | 'personal';

export type MaterialFolderVisibility =
  | 'department'
  | 'organization'
  | 'private';

/**
 * One folder as the server owns it. A root folder is level 0; a folder can have
 * at most two nested levels below it. `scope` decides which section the folder
 * belongs to, `visibility` decides who can see it; the two are independent.
 */
export interface MaterialFolderSummary {
  color?: string;
  createdAt?: string;
  id: string;
  /** The caller owns this folder, so it is theirs to rename, re-scope, delete. */
  isOwner: boolean;
  lastVisitedAt?: string;
  /** 根目录为 0，最多允许到第 3 层（level = 2）。 */
  level: 0 | 1 | 2;
  materialCount: number;
  matchedMaterialCount?: number;
  /** 已授权的完整目录路径，不依赖历史 level 编码。 */
  path?: { id: string; name: string }[];
  name: string;
  /** full_name of the creator; doubles as the id the owner filter matches on. */
  owner: string;
  ownerDepartment?: string;
  /** 根目录为空；不支持跨目录移动。 */
  parentId?: string;
  scope: MaterialFolderScope;
  updatedAt?: string;
  visibility: MaterialFolderVisibility;
}

/** Server-side filters for the folder list. */
export interface MaterialFolderQuery {
  basenames?: readonly string[];
  folderId?: string;
  keyword?: string;
  owner?: string;
  /** 只取某个父目录的直属子目录。 */
  parentId?: string;
  scope?: MaterialFolderScope;
}

/** Everything the create form collects. `parentId` 为空时创建根目录。 */
export interface MaterialFolderInput {
  color?: string;
  name: string;
  parentId?: string;
  scope: MaterialFolderScope;
  visibility: MaterialFolderVisibility;
}

/** 文件夹设置不支持移动；仅允许更新创建参数中的非父级字段。 */
export type MaterialFolderPatch = Partial<
  Omit<MaterialFolderInput, 'parentId'>
>;

/**
 * The established folder-material endpoint contains display fields that have
 * not yet been formalized by the backend. Keep them lossless in `legacy` while
 * requiring a backend-provided stable material ID for all page actions.
 */
export interface MaterialLibraryFolderItem {
  id: string;
  legacy: Readonly<Record<string, unknown>>;
}

export interface MaterialLibraryFolderPage {
  items: readonly MaterialLibraryFolderItem[];
  total: number;
}

export interface MaterialLibraryFolderQuery {
  basename?: string | readonly string[];
  filetype?: string;
  folderId: string;
  page: number;
  pageSize: number;
}

export type MaterialApprovalStatus =
  | 'approved'
  | 'pending_review'
  | 'rejected'
  | 'unknown';

/** A material/version candidate that can be sent through the existing ad draft. */
export interface SelectableMaterial {
  approvalStatus: MaterialApprovalStatus;
  id: string;
  materialId?: string;
  name: string;
  projectId: string;
  ratio?: string;
  source: 'demo-workflow' | 'formal-material-api' | 'legacy-draft';
  type?: string;
}

export interface MaterialSelectionQuery {
  page?: number;
  pageSize?: number;
  projectId: string;
}

export interface MaterialSelectionPage {
  items: readonly SelectableMaterial[];
  total: number;
}

/**
 * Stable material facts returned by the existing MaterialOrder/material-library
 * HTTP APIs. A display name is never used as an identifier.
 */
export interface Material {
  basename?: string;
  contentType?: string;
  fileMd5?: string;
  filetype?: string;
  id: string;
  img?: string;
  name: string;
  objectKey?: string;
  sha3_256?: string;
  size?: number;
  sourceOrderId?: string;
  url?: string;
}

/**
 * The old assignment endpoint does not return a persisted relation ID. This
 * object records the stable IDs submitted to that endpoint, not a fabricated
 * database row or a claim that the server has made the write atomic.
 */
export interface MaterialFolderRelation {
  folderId: string;
  materialId: string;
  /** Only formal atomic responses provide this immutable relation ID. */
  relationId?: string;
  sourceOrderId: string;
  writeStatus: 'created' | 'submitted';
}

export interface MaterialFolderRelationFailure {
  folderId: string;
  message: string;
}

export type MaterialOrderInboundStatus =
  | 'accepted'
  | 'archived'
  | 'pending_accept'
  | 'unknown';

export interface MaterialOrderInboundContext {
  orderId: string;
  status: MaterialOrderInboundStatus;
  title: string;
}

export interface AssignAcceptedMaterialsInput {
  /** The legacy endpoint currently supports the established personal scope. */
  folderIds: readonly string[];
  materialIds: readonly string[];
  orderId: string;
  rating?: number;
  scope: 'personal';
}

export interface AssignAcceptedMaterialsResult {
  acceptanceSubmitted: boolean;
  failures: MaterialFolderRelationFailure[];
  materials: Material[];
  order: MaterialOrderInboundContext;
  relations: MaterialFolderRelation[];
}

/**
 * Additive request shape for the future server-side Material / FolderRelation
 * transaction. `idempotencyKey` identifies a client retry, not a database row
 * and must be echoed unchanged by the formal server response.
 */
export interface AtomicMaterialInboundInput {
  folderIds: readonly string[];
  idempotencyKey: string;
  materialIds: readonly string[];
  orderId: string;
  rating: number;
  scope: 'personal';
}

export type MaterialAtomicInboundStatus = 'completed' | 'failed' | 'pending';

/** Immutable audit fact returned by the formal server-side transaction. */
export interface MaterialInboundAuditRecord {
  action: 'accepted_and_assigned';
  id: string;
  occurredAt: string;
}

/**
 * A formal atomic operation is authoritative only when it has a stable
 * operation ID, echoing idempotency key and audit record. This is deliberately
 * separate from the old per-folder `submitted` projection.
 */
export interface AtomicMaterialInboundOperation {
  audit: MaterialInboundAuditRecord;
  idempotencyKey: string;
  operationId: string;
  order: MaterialOrderInboundContext;
  relations: MaterialFolderRelation[];
  status: MaterialAtomicInboundStatus;
}
