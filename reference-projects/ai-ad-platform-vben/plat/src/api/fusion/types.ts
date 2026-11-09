export type PlatformCode = 'facebook' | 'google' | 'tiktok';

/** 项目及代理线主数据媒体；不代表广告执行能力。 */
export type ProjectPlatformCode = PlatformCode | 'kwai';

export type AiCapabilityCode =
  | 'ad-crawler'
  | 'auto-edit'
  | 'batch-image'
  | 'batch-image-edit'
  | 'batch-video'
  | 'copy-script'
  | 'creative-batch'
  | 'fb-ad-scraper'
  | 'image-edit'
  | 'image-generate'
  | 'image-inpaint'
  | 'lip-sync'
  | 'material-replicate'
  | 'material-tagging'
  | 'music-generate'
  | 'new-creative'
  | 'news-trends'
  | 'seedance'
  | 'tts-generate'
  | 'tts-preview'
  | 'video-analyze'
  | 'video-concat'
  | 'video-edit'
  | 'video-extend'
  | 'video-fission'
  | 'video-generate'
  | 'video-mashup'
  | 'video-replicate'
  | 'video-splice'
  | 'video-split';

export type AsyncTaskStatus =
  | 'cancel_requested'
  | 'cancelled'
  | 'failed'
  | 'partial_success'
  | 'queued'
  | 'refund_pending'
  | 'refunded'
  | 'running'
  | 'success';

export type CustomerCooperationMode = 'POSTPAID' | 'PREPAID' | 'PREPAID_ACTUAL';

export type CustomerStatus = 0 | 1 | 2 | 3;

export interface CustomerOption {
  cooperationMode: CustomerCooperationMode;
  id: string;
  name: string;
  status: CustomerStatus;
}

export interface CustomerSummary extends CustomerOption {
  createdAt: string;
  endDate?: string;
  onlineSheetUrl?: string;
  policy?: string;
  projectCount: number;
  remark?: string;
  startDate?: string;
  updatedAt: string;
}

export interface CustomerListParams {
  cooperationMode?: CustomerCooperationMode;
  customerId?: string;
  endDate?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  startDate?: string;
  status?: CustomerStatus;
}

export interface CustomerListResult {
  items: CustomerSummary[];
  total: number;
}

export interface CustomerUpsertPayload {
  cooperationMode: CustomerCooperationMode;
  endDate?: string;
  id?: string;
  name: string;
  onlineSheetUrl?: string;
  policy?: string;
  remark?: string;
  startDate?: string;
  status: CustomerStatus;
}

export type ProjectStatus =
  | 'active'
  | 'archived'
  | 'draft'
  | 'ended'
  | 'paused'
  | 'pending';

export interface ProjectOption {
  /** @deprecated 仅供旧客户视图兼容；新项目流程不再要求客户归属。 */
  customerId?: string;
  /** @deprecated 仅供旧客户视图兼容；新项目流程不再展示客户归属。 */
  customerName?: string;
  deliveryLines: Array<{ id: string; name: string }>;
  id: string;
  name: string;
  productName: string;
  status: ProjectStatus;
}

export type ProjectPriority = 'high' | 'low' | 'normal';

export interface ProjectKpiRequirement {
  comparator: '<' | '<=' | '=' | '>' | '>=' | 'between';
  metric: 'CPA' | 'CPP' | 'ROAS';
  target: number;
  targetMax?: null | number;
}

export interface ProjectAgencyLineOption {
  id: string;
  name: string;
  platform: ProjectPlatformCode;
}

/** 项目代理线 Google Sheet 同步批次。 */
export interface ProjectAgencyLineSyncBatch {
  errorMessage?: string;
  failedRows: number;
  finishedAt?: string;
  id: string;
  linkSnapshot: string;
  projectId: string;
  sheetTitle?: string;
  startedAt: string;
  status: 'failed' | 'partial' | 'running' | 'success';
  successRows: number;
  totalRows: number;
  triggeredBy?: string;
  triggeredByName?: string;
  triggerType: 'manual' | 'scheduled';
}

/** 项目代理线同步失败行，不包含 Token 等原始敏感字段。 */
export interface ProjectAgencyLineSyncFailure {
  agencyLineName?: string;
  createdAt: string;
  failureReason: string;
  id: string;
  sheetRowNumber: number;
}

export interface ProjectAgencyLineSyncPage<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface ProjectRegionCountryOption {
  code: string;
  name: string;
}

export interface ProjectRegionOption {
  code: string;
  countries: ProjectRegionCountryOption[];
  name: string;
}

export interface ProjectWallet {
  /** 钱包记录中的账户名称；兼容旧接口未返回该字段。 */
  accountName?: string;
  ethAddress: string;
  feeUnit: string;
  id: string;
  key: string;
  usdtAddress: string;
}

export interface ProjectSummary extends ProjectOption {
  adAccountCount: number;
  agencyLineIds?: string[];
  agencyLineUrl?: string;
  /** @deprecated 使用 agencyLineIds；保留到旧表单和旧 API 调用迁移完成。 */
  agentLines?: string[];
  amName?: string;
  /** Stable AM user id. Old projects may only have amName. */
  amUserId?: string;
  amUsers?: ProjectUserAssignment[];
  attributionWindow: string;
  countryRegions: string[];
  createWallet?: boolean;
  currency: string;
  customerDailyReportUrl?: string;
  dailyBudget: number;
  dataSpecialist?: string;
  /** 数据专员稳定用户 ID，可不指定。 */
  dataSpecialistId?: string;
  dataSpecialists?: ProjectUserAssignment[];
  /** Stable delivery owner. New Project writes this pair together. */
  deliveryLeaderId?: string;
  deliveryLeaderName?: string;
  endDate?: string;
  isOutsourced?: boolean;
  kpiRequirements?: ProjectKpiRequirement[];
  materialCount: number;
  mediaChannelIds?: string[];
  /** @deprecated 项目不再定义“负责人”；仅供旧页面兼容展示。 */
  ownerName?: string;
  outsourcingTeams?: string[];
  platforms: ProjectPlatformCode[];
  primaryKpi: string;
  priority?: ProjectPriority;
  productInfo?: string;
  productLinks?: string[];
  projectType?: ProjectType;
  projectCode: string;
  responsibleTeam?: string;
  serviceFeePercent?: number;
  startDate: string;
  timezone: string;
  updatedAt: string;
  wallet?: ProjectWallet;
}

export type ProjectSettlementStatus = 'partial' | 'settled' | 'unsettled';

/**
 * 独立于项目主数据保存的经营指标快照。
 * realizedRoi 使用小数比率（0.38 = 38%），且只允许在归因完成后返回。
 */
export interface CustomerProjectOperationMetric {
  actualSpend: number;
  attributionCompleted: boolean;
  currency: string;
  metricCutoff: string;
  realizedRoi?: number;
  settledAmount: number;
  settlementPeriod?: string;
  settlementStatus: ProjectSettlementStatus;
}

export interface CustomerProjectOverviewItem
  extends CustomerProjectOperationMetric,
    ProjectSummary {
  projectId: string;
  projectName: string;
}

export interface CustomerProjectCurrencySummary {
  amount: number;
  currency: string;
}

export interface CustomerProjectOverview {
  customerId: string;
  customerName: string;
  metricCutoff: string;
  projects: CustomerProjectOverviewItem[];
  summary: {
    activeCount: number;
    pendingSettlementCount: number;
    projectCount: number;
    /** 仅包含已完成归因的项目；跨币种时不按原币消耗加权。 */
    realizedProjectCount: number;
    realizedRoi?: number;
    settledCount: number;
    spendByCurrency: CustomerProjectCurrencySummary[];
  };
}

export interface ProjectOperatingTask {
  taskCode?: string;
  completedAt: string;
  id: string;
  kind: 'delivery' | 'material' | 'media';
  ownerName: string;
  title: string;
}

export interface ProjectOperatingPlan {
  completedAt: string;
  id: string;
  name: string;
  platform: PlatformCode;
  result: string;
}

/**
 * 项目经营详情独立于 Project 主数据，正式环境由项目经营聚合接口返回。
 * realizedRoi 仅在 attributionCompleted=true 时可用。
 */
export interface ProjectOperatingOverview {
  actualSpend: number;
  attributionCompleted: boolean;
  completedPlanCount: number;
  completedPlans: ProjectOperatingPlan[];
  completedTaskCount: number;
  completedTasks: ProjectOperatingTask[];
  currency: string;
  dataQualityNote?: string;
  dataQualityStatus?: 'complete' | 'delayed' | 'estimated' | 'missing';
  metricCutoff: string;
  project: ProjectSummary;
  realizedRoi?: number;
  settledAmount: number;
  /** 已办理完成的结项记录按原币种汇总；缺失表示后端尚未提供该能力。 */
  settledAmounts?: { amount: number; currency: string }[];
  settlementPeriod?: string;
  settlementStatus: ProjectSettlementStatus;
  totalPlanCount: number;
  totalTaskCount: number;
}

export interface ProjectListParams {
  customerId?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  platform?: ProjectPlatformCode;
  status?: ProjectSummary['status'];
}

export interface ProjectUpsertPayload {
  agencyLineIds?: string[];
  agencyLineUrl?: string;
  /** @deprecated 使用 agencyLineIds；兼容旧 HTTP 契约。 */
  agentLines?: string[];
  amName: string;
  /** Stable AM user id; amName remains for old API and display compatibility. */
  amUserId?: string;
  amUsers: ProjectUserAssignment[];
  attributionWindow: string;
  countryRegions: string[];
  createWallet: boolean;
  currency: string;
  customerDailyReportUrl?: string;
  /** @deprecated 兼容旧客户入口；新建项目不再要求客户。 */
  customerId?: string;
  /** @deprecated 兼容旧客户入口。 */
  customerName?: string;
  dailyBudget: number;
  dataSpecialist: string;
  /** 数据专员稳定用户 ID，可不指定。 */
  dataSpecialistId?: string;
  dataSpecialists: ProjectUserAssignment[];
  /** Stable delivery owner. Must be paired with deliveryLeaderName. */
  deliveryLeaderId?: string;
  deliveryLeaderName?: string;
  endDate?: string;
  id?: string;
  isOutsourced: boolean;
  kpiRequirements: ProjectKpiRequirement[];
  mediaChannelIds: string[];
  name: string;
  /** @deprecated 项目不再定义“负责人”。 */
  ownerName?: string;
  outsourcingTeams: string[];
  platforms: ProjectPlatformCode[];
  primaryKpi: string;
  priority: ProjectPriority;
  productInfo: string;
  productLinks: string[];
  productName: string;
  projectCode: string;
  projectType: ProjectType;
  responsibleTeam: string;
  serviceFeePercent: number;
  startDate: string;
  status: ProjectStatus;
  timezone: string;
}

export interface ProjectUserAssignment {
  userId: string;
  userName: string;
}

export type ProjectType = 'app' | 'ecommerce' | 'game' | 'other' | 'website';

export interface ProjectListResult {
  items: ProjectSummary[];
  total: number;
}

export interface ProjectContextOption {
  id: string;
  name: string;
  platforms: ProjectPlatformCode[];
  projectCode: string;
  status: ProjectStatus;
}

export interface ProjectContext {
  options: ProjectContextOption[];
  statistics: {
    active: number;
    draftOrPending: number;
    endedOrArchived: number;
    total: number;
  };
}

export interface WorkspaceOverview {
  activeCampaigns: number;
  activeTasks: number;
  aiOutputs: number;
  conversions: number;
  currency: string;
  materialReady: number;
  projectId: string;
  roas: number;
  spend: number;
  todos: Array<{
    description: string;
    id: string;
    level: 'high' | 'low' | 'medium';
    targetPath: string;
    title: string;
  }>;
}

export interface AiCapability {
  code: AiCapabilityCode;
  description: string;
  inputKinds: Array<'audio' | 'image' | 'prompt' | 'text' | 'url' | 'video'>;
  name: string;
  outputKind: 'audio' | 'data' | 'image' | 'report' | 'text' | 'video';
}

export interface AsyncTask {
  capability?: AiCapabilityCode;
  createdAt: string;
  id: string;
  message?: string;
  platform?: PlatformCode;
  progress: number;
  projectId: string;
  refundable: boolean;
  resultCount?: number;
  status: AsyncTaskStatus;
  title: string;
  updatedAt: string;
}

export interface AiJobPayload {
  capability: AiCapabilityCode;
  deliveryLineId?: string;
  expectedCount: number;
  inputMaterialIds?: string[];
  parameters: Record<string, boolean | number | string>;
  projectId: string;
  prompt?: string;
}

export interface PlatformCapability {
  adAccountLabel: string;
  adGroupLabel: string;
  conversionLabel: string;
  creativeIdentityLabel: string;
  name: string;
  platform: PlatformCode;
  supportedObjectives: string[];
}

export interface AdDraftPayload {
  adAccountId: string;
  /** Canonical inventory id; old drafts and old publish APIs may omit it. */
  adAccountInventoryId?: string;
  agencyLineId?: string;
  budget: number;
  campaignName: string;
  conversionTargetId: string;
  creativeIdentityId: string;
  deliveryLineId?: string;
  destinationUrl: string;
  materialIds: string[];
  objective: string;
  platform: PlatformCode;
  projectId: string;
  scheduleEnd?: string;
  scheduleStart: string;
  targeting: {
    ageMax?: number;
    ageMin?: number;
    countries: string[];
    languages?: string[];
  };
}

export interface PreflightResult {
  checks: Array<{
    code: string;
    message: string;
    passed: boolean;
    severity: 'error' | 'info' | 'warning';
  }>;
  passed: boolean;
  /** Short-lived server proof for the exact preflight snapshot. */
  token?: string;
  tokenExpiresAt?: string;
}

export interface PublishJobResult {
  jobId: string;
  /**
   * Optional until the formal publishing backend returns immutable platform
   * objects. The frontend must never infer these IDs from a job or a name.
   */
  platformObjectIds?: {
    adIds: string[];
    adSetIds: string[];
    campaignIds: string[];
    creativeIds: string[];
  };
  status: AsyncTaskStatus;
}

export type CreativeAssetKind = 'audio' | 'image' | 'text' | 'video';

export interface GenerationAsset {
  id: string;
  kind: CreativeAssetKind;
  name: string;
  url?: string;
}

export interface GenerationRecord {
  assets: GenerationAsset[];
  capability: AiCapabilityCode;
  createdAt: string;
  errorMessage?: string;
  id: string;
  inputCount: number;
  parameters: Record<string, boolean | number | string>;
  projectId: string;
  prompt: string;
  resultCount: number;
  sessionId: string;
  status: 'failed' | 'pending' | 'success';
  title: string;
}

export interface GenerationHistoryParams {
  capability?: AiCapabilityCode;
  keyword?: string;
  page?: number;
  pageSize?: number;
  status?: GenerationRecord['status'];
}

export interface GenerationHistoryResult {
  items: GenerationRecord[];
  total: number;
}

export type TemplateCategory =
  | 'game'
  | 'general'
  | 'lifestyle'
  | 'product'
  | 'script'
  | 'video';

export interface CreativeTemplate {
  category: TemplateCategory;
  description: string;
  id: string;
  name: string;
  prompt: string;
  status: 'draft' | 'published';
  structure: string;
  tags: string[];
  updatedAt: string;
  usageCount: number;
}

export interface StorageBucket {
  id: string;
  lifecycleDays: number;
  name: string;
  objectCount: number;
  region: string;
  status: 'healthy' | 'warning';
  usedSize: string;
}

export interface StorageObject {
  bucketId: string;
  folder: string;
  id: string;
  kind: 'folder' | 'other' | CreativeAssetKind;
  name: string;
  size: string;
  updatedAt: string;
}

export interface OperationRecord {
  category: string;
  health: 'healthy' | 'offline' | 'warning';
  id: string;
  metric: string;
  name: string;
  owner: string;
  status: string;
  updatedAt: string;
}
