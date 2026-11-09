import type { RequestClientConfig } from '@vben/request';

import type {
  AdAccountFacebookActivityCategory,
  AdAccountFacebookActivitySummaryItem,
} from './main/ad-account-assets';
import type { SystemPageResult } from './system/types';

import { backendClient } from '#/api/request';

const DYNAMIC_FLOW_PATH = '/asset-flow-v2';

/** 可入库、分配并在“我的资产”中持续追踪的资源类型。 */
export type MediaAssetType =
  | 'AD_ACCOUNT'
  | 'BM'
  | 'COMPUTER'
  | 'EMAIL'
  | 'MOBILE'
  | 'PAGE'
  | 'PERSONAL'
  | 'PIXEL'
  | 'STATIC_IP'
  | 'TG';
/** 审批配置的内部标识由系统生成，业务侧不再维护固定类型枚举。 */
export type ApprovalApplicationType = string;
export type ApprovalCategory = 'advertising' | 'finance' | 'office' | 'social';
export type AssetStatus =
  | 'ASSIGNED'
  | 'AVAILABLE'
  | 'DISABLED'
  | 'RETURN_PENDING';

export type DynamicFieldType =
  | 'date'
  | 'date-range'
  | 'image-upload'
  | 'multi-select'
  | 'number'
  | 'pixel-selector'
  | 'section'
  | 'select'
  | 'text'
  | 'textarea';

/** 下拉字段的数据来源；custom 使用配置内选项，其余来源在运行时读取系统数据。 */
export type DynamicFieldOptionSource =
  | 'ad-accounts'
  | 'available-pixels'
  | 'channels'
  | 'custom'
  | 'departments'
  | 'projects'
  | 'roles'
  | 'users';

export interface DynamicFieldOption {
  label: string;
  value: string;
}

/** 像素申请弹窗使用的脱敏库存摘要，不包含 Access Token 等凭据。 */
export interface SelectablePixel {
  bmId: string;
  bmName: string;
  createdAt?: string;
  id: string;
  pixelId: string;
  pixelName: string;
  pixelTestCode: string;
  remark: string;
}

export interface SelectablePixelSearch {
  filterValues?: Record<string, string[]>;
  page: number;
  pageSize: number;
}

export interface SelectablePixelPage {
  items: SelectablePixel[];
  page: number;
  pageSize: number;
  total: number;
}

export interface DynamicFieldCondition {
  fieldKey: string;
  operator: 'equals' | 'in' | 'not-equals';
  value: string | string[];
}

/** 受控的联动数据源；配置中只保存数据源键，禁止录入任意请求地址。 */
export type DynamicFieldAutoFillSource = 'channel-payment-context';

export interface DynamicFieldAutoFill {
  resultKey: 'channelYesterdayCost' | 'paymentAddress';
  source: DynamicFieldAutoFillSource;
  triggerFieldKey: string;
}

export interface DynamicFormField {
  accept?: string;
  /** 为空表示适用于该审批配置关联的全部申请。 */
  applicableApplicationCodes?: string[];
  autoFill?: DynamicFieldAutoFill;
  defaultValue?: number | string | string[];
  helpText?: string;
  key: string;
  label: string;
  maxCount?: number;
  maxFileSizeMb?: number;
  maxLength?: number;
  maxValue?: number;
  minValue?: number;
  options?: string[];
  optionSource?: DynamicFieldOptionSource;
  placeholder?: string;
  readOnly?: boolean;
  required: boolean;
  requiredWhen?: DynamicFieldCondition;
  type: DynamicFieldType;
  validationRule?:
    | 'digit-list'
    | 'email'
    | 'pixel-list'
    | 'positive-money'
    | 'url';
  visibleWhen?: DynamicFieldCondition;
  width?: 'full' | 'half';
}

export interface HandlerResourceAssignment {
  /** 可选；配置后从申请表字段解析实际库存类型，适用于一张表申请多种社交资产。 */
  assetTypeFieldKey?: string;
  assetTypeSource: 'application';
  channelFieldKey?: string;
  enabled: boolean;
  quantityFieldKey: string;
}

/** 办理节点的业务动作随审批配置保存，并快照到申请单。 */
export interface HandlerActionConfig {
  formSchema?: DynamicFormField[];
  resourceAssignment?: HandlerResourceAssignment;
}

/** 办理人可固定指定，也可复用流程内某个审批节点的审批人。 */
export type HandlerSource = 'approval-node' | 'fixed-user';

export interface ApprovalNodeConfig {
  actionPermissions?: {
    allowAddApprover: boolean;
    allowComment: boolean;
    allowReturn: boolean;
    allowTransfer: boolean;
  };
  approverId: string;
  approverIds?: string[];
  approverName: string;
  approverNames?: string[];
  approverType?: 'DEPARTMENTS' | 'ROLES' | 'USERS';
  assigneeMode?: 'department' | 'member' | 'role';
  departmentIds?: string[];
  departmentNames?: string[];
  editableFieldKeys?: string[];
  id?: string;
  kind?: 'approval';
  name: string;
  roleIds?: string[];
  roleNames?: string[];
}

export interface MediaAsset {
  applicationId?: string;
  assetCode: string;
  assetName: string;
  assetType: MediaAssetType;
  /** 使用人的当前主部门，由服务端根据组织架构实时推导。 */
  assigneeDepartmentName?: string;
  /** 多使用人的当前主部门列表，由服务端根据组织架构实时推导。 */
  usageDepartmentNames?: string;
  assigneeId?: string;
  assigneeName?: string;
  /** 广告账户和像素由全部有效共享分配关系汇总出的使用人名称。 */
  usageUserNames?: string;
  /** 像素共享使用人的稳定 ID 列表，使用英文逗号分隔，供资产编辑页回填。 */
  usageUserIds?: string;
  /** @deprecated 后端灰度升级期间兼容旧字段；界面统一按“使用人”展示。 */
  applicantNames?: string;
  channelId?: string;
  channelName?: string;
  createdAt: string;
  id: string;
  projectId?: string;
  projectName?: string;
  /** 像素办理分配时固化的申请表所选使用团队；结项释放后为空。 */
  usageTeam?: string;
  remark?: string;
  secretData?: string;
  status: AssetStatus;
  updatedAt?: string;
}

/** 资产管理列表的服务端筛选条件。 */
export interface MediaAssetSearchParams {
  assetType?: MediaAssetType;
  filterControls?: Record<string, 'date' | 'select' | 'text'>;
  /** @deprecated 兼容旧客户端的单值筛选；新调用使用 filterValues。 */
  filters?: Record<string, string>;
  filterValues?: Record<string, string[]>;
  keyword?: string;
  mine: boolean;
  page: number;
  pageSize: number;
  subtype?: string;
}

/** 资产导出沿用列表筛选条件，但由服务端一次返回全部命中记录。 */
export type MediaAssetSearchAllParams = Omit<
  MediaAssetSearchParams,
  'page' | 'pageSize'
>;

export interface MediaAssetPage {
  items: MediaAsset[];
  page: number;
  pageSize: number;
  total: number;
}

/** 手工创建或编辑库存资产时允许保存的字段。 */
export interface MediaAssetSavePayload {
  assetCode: string;
  assetName: string;
  assetType: MediaAssetType;
  assigneeId?: string;
  /** 广告账户支持多人共享；像素的归属由项目字段决定。 */
  assigneeIds?: string[];
  channelId?: string;
  channelName?: string;
  projectId?: string;
  projectName?: string;
  remark?: string;
  secretData?: string;
  status: Extract<AssetStatus, 'ASSIGNED' | 'AVAILABLE' | 'DISABLED'>;
  /** 像素使用团队的系统部门稳定 ID。 */
  usageTeamId?: string;
}

export type MediaAssetBatchField =
  | 'CHANNEL'
  | 'INVENTORY_STATUS'
  | 'PROJECT'
  | 'REMARK'
  | 'USAGE_TEAM'
  | 'USAGE_USERS';

/** 通用库存批量修改请求；detailUpdates 中出现的键即为要覆盖的明细字段。 */
export interface MediaAssetBatchUpdatePayload {
  assetIds: string[];
  assigneeId?: string;
  assigneeIds?: string[];
  changedFields: MediaAssetBatchField[];
  channelId?: string;
  channelName?: string;
  detailUpdates: Record<string, string>;
  projectId?: string;
  projectName?: string;
  remark?: string;
  status?: Extract<AssetStatus, 'ASSIGNED' | 'AVAILABLE' | 'DISABLED'>;
  usageTeamId?: string;
}

export interface MediaAssetSpreadsheetRow {
  assetId?: string;
  assigneeIds?: string[];
  changedFields: MediaAssetBatchField[];
  detailUpdates: Record<string, string>;
  usageTeamId?: string;
  values: MediaAssetSavePayload;
}

export interface MediaAssetSpreadsheetSaveResult {
  createdCount: number;
  items: MediaAsset[];
  updatedCount: number;
}

/** 资产 Excel 由服务端解析后的导入结果。 */
export interface AssetFileImportResult {
  failedFileBase64?: string | null;
  failedFileName?: string | null;
  failures: Array<{
    line: number;
    message: string;
  }>;
  successCount: number;
  totalCount: number;
}

/** 当前用户发起的资产 Excel 导入记录。 */
export interface AssetImportHistoryRecord {
  assetSubtype: string;
  createdAt: string;
  failures: Array<{
    line: number;
    message: string;
  }>;
  fileName: string;
  id: string;
  successCount: number;
  totalCount: number;
}

/** 当前用户下载自己导入时生成的失败工作簿。 */
export interface AssetImportFailedFile {
  contentBase64: string;
  fileName: string;
}

export interface AssetApprovalLog {
  action: 'APPROVED' | 'COMPLETED' | 'REJECTED' | 'SUBMITTED';
  actionData?: Record<string, unknown>;
  actorId: string;
  actorName: string;
  createdAt: string;
  id: string;
  nodeIndex?: number;
  nodeName?: string;
  remark?: string;
}

/** 审批流程评论；评论人身份由服务端根据流程参与关系生成。 */
export interface AssetApprovalComment {
  actor: string;
  actorRole: string;
  at: string;
  content: string;
  id: string;
}

/** 审批详情只返回已分配资产的非敏感摘要。 */
export interface AllocatedAssetSummary {
  assetCode: string;
  assetName: string;
  assetType: MediaAssetType;
  channelName?: string;
  id: string;
  projectName?: string;
}

/** 审批抄送人由后端按稳定用户 ID 解析；历史无效 ID 会保留但标记为未解析。 */
export interface ApprovalCcUser {
  active: boolean;
  displayName: string;
  id: string;
  resolved: boolean;
}

export interface AssetApplication {
  allocatedAssets?: AllocatedAssetSummary[];
  applicationNo: string;
  approvalLogs?: AssetApprovalLog[];
  approverId: string;
  approverName: string;
  assetType: ApprovalApplicationType;
  ccUsers?: ApprovalCcUser[];
  createdAt: string;
  currentNodeIndex?: number;
  decisionRemark?: string;
  departmentId?: string;
  departmentName?: string;
  formData?: Record<string, unknown>;
  formSchema?: DynamicFormField[];
  handlerAction?: HandlerActionConfig;
  handlerApprovalNodeId?: string;
  handlerId: string;
  handlerName: string;
  handlerSource?: HandlerSource;
  id: string;
  nodes?: ApprovalNodeConfig[];
  quantity: number;
  reason: string;
  requesterId: string;
  requesterName: string;
  /** 重提时关联的上一张已驳回申请，仅重提单返回。 */
  sourceApplicationId?: string;
  status: 'APPROVED' | 'PENDING' | 'PROCESSING' | 'REJECTED';
  title: string;
  transferRecords?: AssetApprovalTransferRecord[];
  updatedAt?: string;
}

export type AssetBatchDecisionAction = 'APPROVE' | 'REJECT';

export interface AssetBatchDecisionPayload {
  action: AssetBatchDecisionAction;
  ids: string[];
  remark: string;
}

/** 审批中心批量导出请求；ID 保持字符串以避免大整数精度丢失。 */
export interface AssetApprovalExportPayload {
  ids: string[];
}

export interface AssetApprovalTransferRecord {
  actorDepartmentId?: string;
  actorDepartmentName?: string;
  actorId: string;
  actorName: string;
  at: string;
  id: string;
  nodeIndex: number;
  recipientDepartmentId: string;
  recipientDepartmentName: string;
  recipientId: string;
  recipientName: string;
  remark: string;
}

/** Candidates are constrained on the server by the current handler's primary department. */
export interface ApprovalTransferCandidate {
  departmentId: string;
  departmentName: string;
  id: string;
  name: string;
}

export type ApprovalQueue =
  | 'copied'
  | 'handling'
  | 'initiated'
  | 'pending'
  | 'processed';

/** 审批中心列表卡片摘要；完整动态表单、节点和轨迹由详情接口按需返回。 */
export interface ApprovalListItem {
  applicationDefinitionId?: string;
  applicationNo: string;
  approverId?: string;
  approverName?: string;
  assetType: ApprovalApplicationType;
  ccUsers?: ApprovalCcUser[];
  configCategory?: ApprovalCategory;
  createdAt: string;
  departmentId?: string;
  departmentName?: string;
  id: string;
  projectName?: string;
  quantity: number;
  reason: string;
  requesterId: string;
  requesterName: string;
  status: AssetApplication['status'];
  title: string;
  updatedAt?: string;
}

export interface ApprovalPageParams {
  applicationDefinitionId?: string;
  assetType?: string;
  decisionResult?: 'APPROVED' | 'REJECTED';
  departmentId?: string;
  keyword?: string;
  page: number;
  pageSize?: number;
  queue: ApprovalQueue;
  requesterId?: string;
}

export interface ApprovalPage {
  hasMore: boolean;
  items: ApprovalListItem[];
  page: number;
  pageSize: number;
  total: number;
}

export interface ApprovalMetadata {
  departments: Array<{ label: string; value: string }>;
  queueCounts: Record<ApprovalQueue, number>;
  requesters: Array<{ label: string; value: string }>;
}

/** 资产列表补齐申请状态时使用的轻量摘要，避免获取审批轨迹等详情。 */
export interface AssetApplicationSummary {
  id: string;
  requesterName: string;
  status: AssetApplication['status'];
}

export interface AssetLifecycleDetail {
  asset: {
    assetCode?: string;
    assetName: string;
    assetType: string;
    currentUserName?: string;
    id: string;
    projectName?: string;
    status: string;
    teamName?: string;
    spend?: {
      cumulative?: number;
      currency?: string;
      dataCutoff?: string;
      today?: number;
      unavailable?: boolean;
    };
  };
  events: Array<{
    actorName?: string;
    amount?: number;
    applicationId?: string;
    extraData?: string;
    currency?: string;
    description?: string;
    eventType: string;
    facebookCategory?: AdAccountFacebookActivityCategory;
    facebookSummaryItems?: AdAccountFacebookActivitySummaryItem[];
    formFields?: AccountLifecycleFormField[];
    id: string;
    nodeName?: string;
    localOccurredAt?: string;
    objectId?: string;
    objectName?: string;
    objectType?: string;
    occurredAt: string;
    platformApplicationName?: string;
    projectName?: string;
    remark?: string;
    source?: 'FACEBOOK' | 'FACEBOOK_BAN_EVENT';
    status?: string;
    targetUserName?: string;
    teamName?: string;
    tool?: string;
    updateSource?: LifecycleUpdateSource;
    changes?: LifecycleFieldChange[];
  }>;
  usagePeriods: Array<{
    applicationId?: string;
    endedAt?: string;
    projectName?: string;
    spend?: number;
    spendCurrency?: string;
    spendUnavailable?: boolean;
    startedAt: string;
    status: string;
    teamName?: string;
    userId: string;
    userName: string;
  }>;
}

export type LifecycleUpdateSource =
  | 'BATCH_EDIT'
  | 'CHANNEL_IMPORT'
  | 'CHANNEL_MANUAL'
  | 'EXCEL_BATCH'
  | 'EXCEL_IMPORT'
  | 'FEISHU_SYNC'
  | 'MANUAL_CREATE'
  | 'MANUAL_EDIT'
  | 'MONGO_SYNC'
  | 'OPEN_ACCOUNT'
  | 'SPREADSHEET_CREATE'
  | string;

export interface LifecycleValueReference {
  id?: string;
  name?: string;
}

export interface LifecycleChangeValue {
  display?: string;
  redacted?: boolean;
  references?: LifecycleValueReference[];
}

export interface LifecycleFieldChange {
  after?: LifecycleChangeValue;
  before?: LifecycleChangeValue;
  fieldKey: string;
  fieldLabel: string;
}

export interface AccountLifecycleApplication {
  actions: Array<{
    action: string;
    actorName?: string;
    createdAt: string;
    id: string;
    nodeName?: string;
    remark?: string;
  }>;
  amount?: number;
  applicationCode?: string;
  applicationId: string;
  createdAt: string;
  currency?: string;
  decidedAt?: string;
  formFields?: AccountLifecycleFormField[];
  requesterName?: string;
  status: string;
  title: string;
}

export interface AccountLifecycleFormField {
  fullWidth: boolean;
  key: string;
  label: string;
  value: string;
}

export interface ApprovalConfig {
  applicationDefinitionIds?: string[];
  assetType: ApprovalApplicationType;
  category: ApprovalCategory;
  ccUserIds?: string;
  description: string;
  enabled: boolean;
  formSchema: DynamicFormField[];
  handlerApprovalNodeId?: string;
  handlerId: string;
  handlerName: string;
  handlerSource?: HandlerSource;
  icon: string;
  id: string;
  name: string;
  nodes: ApprovalNodeConfig[];
  settings: Record<string, unknown> & {
    completionMode?: 'handler' | 'pixel-auto-assign';
    handlerAction?: HandlerActionConfig;
  };
  sortOrder: number;
  status: 'published';
  updatedAt: string;
  usageCount: number;
  visibility: 'admins' | 'all';
}

/** 资源申请中心左侧展示的申请类型。 */
export interface ApplicationType {
  description: string;
  icon: string;
  id: string;
  sortOrder: number;
  status: 0 | 1;
  typeName: string;
  updatedAt: string;
}

export interface ApplicationTypeSaveRequest {
  description?: string;
  icon: string;
  sortOrder: number;
  status: 0 | 1;
  typeName: string;
}

/** 申请入口定义；多个入口可关联同一审批配置，表单仍由审批配置维护。 */
export interface ApplicationDefinition {
  applicationCode: string;
  applicationName: string;
  approvalAssetType?: string;
  approvalConfigEnabled?: boolean;
  approvalConfigId?: string;
  approvalConfigName?: string;
  applicationTypeId: string;
  applicationTypeName: string;
  createdAt: string;
  description: string;
  icon: string;
  id: string;
  sortOrder: number;
  showInResourceApplication: boolean;
  status: 0 | 1;
  updatedAt: string;
  visibility: 'admins' | 'all';
}

export interface ApplicationDefinitionSaveRequest {
  applicationCode?: string;
  applicationName: string;
  applicationTypeId: string;
  description?: string;
  icon: string;
  sortOrder: number;
  showInResourceApplication: boolean;
  status: 0 | 1;
  visibility: 'admins' | 'all';
}

export interface SiteNotification {
  businessId: string;
  businessType: string;
  createdAt: string;
  id: string;
  isRead: boolean | number;
  message: string;
  targetPath: string;
  title: string;
}

/** 站内通知分页结果。 */
export interface SiteNotificationPage {
  hasMore: boolean;
  items: SiteNotification[];
  page: number;
  pageSize: number;
  total: number;
}

/** 顶部导航红点所需的轻量未读状态。 */
export interface SiteNotificationUnreadStatus {
  hasUnread: boolean;
}

export const assetFlowApi = {
  applications: (config?: RequestClientConfig) =>
    backendClient.get<AssetApplication[]>(
      `${DYNAMIC_FLOW_PATH}/applications/mine`,
      config,
    ),
  applicationSummaries: (ids: string[], config?: RequestClientConfig) =>
    backendClient.get<AssetApplicationSummary[]>(
      `${DYNAMIC_FLOW_PATH}/applications/summaries`,
      {
        ...config,
        params: { ids: ids.join(',') },
      },
    ),
  application: (id: string, config?: RequestClientConfig) =>
    backendClient.get<AssetApplication>(
      `${DYNAMIC_FLOW_PATH}/applications/${id}`,
      config,
    ),
  approvalPage: (params: ApprovalPageParams, config?: RequestClientConfig) =>
    backendClient.get<ApprovalPage>(`${DYNAMIC_FLOW_PATH}/approvals/page`, {
      ...config,
      params,
    }),
  approvalMetadata: (config?: RequestClientConfig) =>
    backendClient.get<ApprovalMetadata>(
      `${DYNAMIC_FLOW_PATH}/approvals/metadata`,
      config,
    ),
  approvals: () =>
    backendClient.get<AssetApplication[]>(`${DYNAMIC_FLOW_PATH}/approvals`),
  processedApprovals: (config?: RequestClientConfig) =>
    backendClient.get<AssetApplication[]>(
      `${DYNAMIC_FLOW_PATH}/approvals/processed`,
      config,
    ),
  comments: (id: string) =>
    backendClient.get<AssetApprovalComment[]>(
      `${DYNAMIC_FLOW_PATH}/applications/${id}/comments`,
    ),
  comment: (id: string, content: string) =>
    backendClient.post<AssetApprovalComment>(
      `${DYNAMIC_FLOW_PATH}/applications/${id}/comments`,
      { content },
      { skipErrorMessage: true },
    ),
  approve: (id: string, remark = '') =>
    backendClient.post<AssetApplication>(
      `${DYNAMIC_FLOW_PATH}/approvals/${id}/approve`,
      { remark },
    ),
  batchDecide: (payload: AssetBatchDecisionPayload) =>
    backendClient.post<AssetApplication[]>(
      `${DYNAMIC_FLOW_PATH}/approvals/batch-decide`,
      payload,
    ),
  exportApprovals: (payload: AssetApprovalExportPayload) =>
    backendClient.post<Blob>(`${DYNAMIC_FLOW_PATH}/approvals/export`, payload, {
      responseReturn: 'body',
      responseType: 'blob',
    }),
  transferCandidates: (id: string, config?: RequestClientConfig) =>
    config
      ? backendClient.get<ApprovalTransferCandidate[]>(
          `${DYNAMIC_FLOW_PATH}/approvals/${id}/transfer-candidates`,
          config,
        )
      : backendClient.get<ApprovalTransferCandidate[]>(
          `${DYNAMIC_FLOW_PATH}/approvals/${id}/transfer-candidates`,
        ),
  transfer: (
    id: string,
    payload: { recipientId: string; remark: string },
    config?: RequestClientConfig,
  ) =>
    config
      ? backendClient.post<AssetApplication>(
          `${DYNAMIC_FLOW_PATH}/approvals/${id}/transfer`,
          payload,
          config,
        )
      : backendClient.post<AssetApplication>(
          `${DYNAMIC_FLOW_PATH}/approvals/${id}/transfer`,
          payload,
        ),
  assets: (
    assetType?: MediaAssetType,
    channelId?: string,
    config?: RequestClientConfig,
  ) =>
    backendClient.get<MediaAsset[]>('/asset-flow/assets', {
      ...config,
      params: { assetType, channelId },
    }),
  lifecycle: (id: string) =>
    backendClient.get<AssetLifecycleDetail>(
      `/asset-flow/assets/${id}/lifecycle`,
    ),
  accountLifecycleApplications: (accountId: string) =>
    backendClient.get<AccountLifecycleApplication[]>(
      `${DYNAMIC_FLOW_PATH}/account-lifecycle/${encodeURIComponent(accountId)}/applications`,
    ),
  searchAssets: (params: MediaAssetSearchParams) =>
    backendClient.post<MediaAssetPage>('/asset-flow/assets/search', params),
  searchAllAssets: (params: MediaAssetSearchAllParams) =>
    backendClient.post<MediaAsset[]>('/asset-flow/assets/search-all', params),
  selectablePixels: (params: SelectablePixelSearch) =>
    backendClient.post<SelectablePixelPage>(
      `${DYNAMIC_FLOW_PATH}/selectable-pixels/search`,
      params,
    ),
  configs: (config?: RequestClientConfig) =>
    backendClient.get<ApprovalConfig[]>(
      `${DYNAMIC_FLOW_PATH}/approval-configs`,
      config,
    ),
  managedConfigs: (config?: RequestClientConfig) =>
    backendClient.get<ApprovalConfig[]>(
      `${DYNAMIC_FLOW_PATH}/approval-configs/manage`,
      config,
    ),
  applicationTypes: (config?: RequestClientConfig) =>
    backendClient.get<ApplicationType[]>(
      `${DYNAMIC_FLOW_PATH}/application-types`,
      config,
    ),
  managedApplicationTypes: (config?: RequestClientConfig) =>
    backendClient.get<ApplicationType[]>(
      `${DYNAMIC_FLOW_PATH}/application-types/manage`,
      config,
    ),
  applicationDefinitions: (config?: RequestClientConfig) =>
    backendClient.get<ApplicationDefinition[]>(
      `${DYNAMIC_FLOW_PATH}/application-definitions`,
      config,
    ),
  managedApplicationDefinitions: (
    params?: {
      approvalConfigId?: string;
      category?: ApprovalCategory;
      keyword?: string;
      status?: 0 | 1;
    },
    config?: RequestClientConfig,
  ) =>
    backendClient.get<ApplicationDefinition[]>(
      `${DYNAMIC_FLOW_PATH}/application-definitions/manage`,
      { ...config, params },
    ),
  createApplicationDefinition: (payload: ApplicationDefinitionSaveRequest) =>
    backendClient.post<ApplicationDefinition>(
      `${DYNAMIC_FLOW_PATH}/application-definitions`,
      payload,
    ),
  updateApplicationDefinition: (
    id: string,
    payload: ApplicationDefinitionSaveRequest,
  ) =>
    backendClient.put<ApplicationDefinition>(
      `${DYNAMIC_FLOW_PATH}/application-definitions/${id}`,
      payload,
    ),
  deleteApplicationDefinition: (id: string) =>
    backendClient.delete(`${DYNAMIC_FLOW_PATH}/application-definitions/${id}`),
  createApplicationType: (payload: ApplicationTypeSaveRequest) =>
    backendClient.post<ApplicationType>(
      `${DYNAMIC_FLOW_PATH}/application-types`,
      payload,
    ),
  updateApplicationType: (id: string, payload: ApplicationTypeSaveRequest) =>
    backendClient.put<ApplicationType>(
      `${DYNAMIC_FLOW_PATH}/application-types/${id}`,
      payload,
    ),
  createApplication: (payload: {
    assetType: ApprovalApplicationType;
    formData: Record<string, unknown>;
    sourceApplicationId?: string;
    title: string;
  }) =>
    backendClient.post<AssetApplication>(
      `${DYNAMIC_FLOW_PATH}/applications`,
      payload,
    ),
  createAsset: (payload: MediaAssetSavePayload, config?: RequestClientConfig) =>
    backendClient.post<MediaAsset>('/asset-flow/assets', payload, config),
  batchUpdateAssets: (payload: MediaAssetBatchUpdatePayload) =>
    backendClient.request<MediaAsset[]>('/asset-flow/assets/batch', {
      data: payload,
      method: 'PATCH',
    }),
  batchQueryAssets: (assetIds: string[]) =>
    backendClient.post<MediaAsset[]>('/asset-flow/assets/batch-query', {
      assetIds,
    }),
  batchQueryAssetsByIdentifiers: (
    assetType: MediaAssetType,
    identifiers: string[],
  ) =>
    backendClient.post<MediaAsset[]>(
      '/asset-flow/assets/batch-query-by-identifiers',
      { assetType, identifiers },
    ),
  saveAssetSpreadsheet: (payload: {
    rows: MediaAssetSpreadsheetRow[];
    subtype: string;
  }) =>
    backendClient.post<MediaAssetSpreadsheetSaveResult>(
      '/asset-flow/assets/spreadsheet',
      payload,
    ),
  importAssetFile: (file: File, subtype: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('subtype', subtype);
    return backendClient.post<AssetFileImportResult>(
      '/asset-flow/assets/import',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
  },
  importHistory: (params: { page: number; pageSize: number }) =>
    backendClient.get<SystemPageResult<AssetImportHistoryRecord>>(
      '/asset-flow/assets/import-records',
      { params },
    ),
  importFailedFile: (id: string) =>
    backendClient.get<AssetImportFailedFile>(
      `/asset-flow/assets/import-records/${id}/failed-file`,
    ),
  updateUsageUser: (
    id: string,
    usageUserId: string,
    config?: RequestClientConfig,
  ) =>
    backendClient.put<MediaAsset>(
      `/asset-flow/assets/${id}/usage-user`,
      { usageUserId },
      config,
    ),
  deleteAsset: (id: string) => backendClient.delete(`/asset-flow/assets/${id}`),
  deleteConfig: (id: string) =>
    backendClient.delete(`${DYNAMIC_FLOW_PATH}/approval-configs/${id}`),
  mine: () => backendClient.get<MediaAsset[]>('/asset-flow/assets/mine'),
  complete: (
    id: string,
    remark = '',
    assetIds: string[] = [],
    actionData: Record<string, unknown> = {},
  ) =>
    backendClient.post<AssetApplication>(
      `${DYNAMIC_FLOW_PATH}/approvals/${id}/complete`,
      { actionData, assetIds, remark },
    ),
  reject: (id: string, remark: string) =>
    backendClient.post<AssetApplication>(
      `${DYNAMIC_FLOW_PATH}/approvals/${id}/reject`,
      {
        remark,
      },
    ),
  notificationUnreadStatus: () =>
    backendClient.get<SiteNotificationUnreadStatus>(
      `${DYNAMIC_FLOW_PATH}/notifications/unread-status`,
    ),
  notifications: (params: { page: number; pageSize: number }) =>
    backendClient.get<SiteNotificationPage>(
      `${DYNAMIC_FLOW_PATH}/notifications`,
      { params },
    ),
  readAllNotifications: () =>
    backendClient.put(`${DYNAMIC_FLOW_PATH}/notifications/read-all`),
  readNotification: (id: string) =>
    backendClient.put(`${DYNAMIC_FLOW_PATH}/notifications/${id}/read`),
  saveConfig: (
    payload: Omit<ApprovalConfig, 'id' | 'updatedAt' | 'usageCount'>,
  ) =>
    backendClient.put<ApprovalConfig>(
      `${DYNAMIC_FLOW_PATH}/approval-configs`,
      payload,
    ),
  updateAsset: (id: string, payload: MediaAssetSavePayload) =>
    backendClient.put<MediaAsset>(`/asset-flow/assets/${id}`, payload),
};
