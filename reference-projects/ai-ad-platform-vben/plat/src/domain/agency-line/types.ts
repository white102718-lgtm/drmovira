export interface AgencyLine {
  /** 项目业务状态，与媒体广告启停、自动投放配置相互独立。 */
  status?: 'active' | 'stopped';
  autoRun: boolean;
  budgetCap?: number;
  budgetFloor?: number;
  cloakUrl: string;
  createdAt: string;
  deliveryUrl: string;
  enabled: boolean;
  id: string;
  isSend: boolean;
  legacyGamePlatform?: string;
  name: string;
  objective: string;
  optimizerId?: string;
  optimizerName: string;
  /** 当前用户状态，缺失不代表停用。 */
  optimizerStatus?: null | number;
  packageName: string;
  packageType: string;
  pageId: string;
  pixelId: string;
  pixelName: string;
  platform: string;
  projectId?: string;
  testCode: string;
  token: string;
  type: string;
  updatedAt: string;
}

export interface AgencyLineDeliveryUrlHistory {
  agencyLineId: string;
  changedAt: string;
  changedBy?: null | string;
  changedByName?: null | string;
  deliveryUrl: string;
  id: string;
  versionNo: number;
}

export interface AgencyLineListQuery {
  /** 仅按代理线名称做包含匹配。 */
  lineName?: string;
  /** 支持换行输入多个关键词，任意关键词命中代理线的非敏感展示字段即可。 */
  keyword?: string;
  legacyGamePlatform?: string;
  optimizerId?: string;
  page?: number;
  pageSize?: number;
  platform?: string;
  projectId?: string;
}

export interface AgencyLineListResult {
  items: AgencyLine[];
  page: number;
  pageSize: number;
  total: number;
}

export type AgencyLineOption = Pick<
  AgencyLine,
  | 'enabled'
  | 'id'
  | 'legacyGamePlatform'
  | 'name'
  | 'objective'
  | 'pageId'
  | 'pixelName'
  | 'platform'
  | 'projectId'
>;

export type AgencyLineUpsertInput = Omit<
  AgencyLine,
  'createdAt' | 'id' | 'updatedAt'
> & {
  id?: string;
};

export type AgencyLineImportField =
  | 'autoRun'
  | 'budgetCap'
  | 'budgetFloor'
  | 'cloakUrl'
  | 'deliveryUrl'
  | 'enabled'
  | 'id'
  | 'isSend'
  | 'legacyGamePlatform'
  | 'name'
  | 'objective'
  | 'optimizerId'
  | 'optimizerName'
  | 'packageName'
  | 'packageType'
  | 'pageId'
  | 'pixelId'
  | 'pixelName'
  | 'platform'
  | 'projectId'
  | 'testCode'
  | 'token'
  | 'type'
  | 'row';

export type AgencyLineImportErrorCode =
  | 'duplicate'
  | 'invalid_type'
  | 'invalid_value'
  | 'preflight_failed'
  | 'required'
  | 'save_failed';

export interface AgencyLineImportError {
  code: AgencyLineImportErrorCode;
  field: AgencyLineImportField;
  lineId?: string;
  message: string;
  recoverable?: boolean;
  requestId?: string;
  /** One-based data-row number. Zero represents a batch-level failure. */
  row: number;
}

export interface AgencyLineParsedImportRow {
  input: AgencyLineUpsertInput;
  row: number;
}

export interface AgencyLineImportedItem {
  line: AgencyLine;
  /** Binding intent from the imported row; line.projectId is only a response projection. */
  requestedProjectId?: string;
  requestId: string;
  row: number;
}

export interface AgencyLineImportParseResult {
  errors: AgencyLineImportError[];
  rows: AgencyLineParsedImportRow[];
  total: number;
}

export type AgencyLineImportStatus =
  | 'failed'
  | 'partial'
  | 'success'
  | 'validation_failed';

export interface AgencyLineImportResult {
  errors: AgencyLineImportError[];
  importedItems: AgencyLineImportedItem[];
  items: AgencyLine[];
  status: AgencyLineImportStatus;
  total: number;
}

export interface AgencyLineSaveManyOptions {
  /** 按同名代理线更新；空项目保留原归属，其他模板字段的空值覆盖原值。 */
  overwriteExisting?: boolean;
  /** Stable idempotency keys indexed by the original one-based row number. */
  requestIdsByRow?: Readonly<Record<number, string>>;
  /** Replays prior ambiguous/failed writes with the same idempotency keys. */
  retry?: boolean;
  /** Original one-based row numbers when retrying only a subset. */
  rowNumbers?: readonly number[];
}

export interface AgencyLineCreateCommand {
  input: AgencyLineUpsertInput;
  requestId: string;
}
