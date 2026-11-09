import type { RequestClientConfig } from '@vben/request';

import { mainBackendClient } from '#/api/request';

export type AdAccountInventoryStatus =
  | 'ASSIGNED'
  | 'AVAILABLE'
  | 'DISABLED'
  | 'RETURN_PENDING';

/** 广告账户资产信息主表中允许人工维护的字段。 */
export interface AdAccountAsset {
  accountId: string;
  accountName: string;
  /** Facebook平台账户状态，只读并由fb_ad_accounts提供。 */
  accountStatus?: number;
  /** 账户日限额，只读并由fb_ad_accounts的account_dsl提供。 */
  accountDailyLimit?: null | number;
  /** 统一账户资产台账中的库存状态。 */
  inventoryStatus?: AdAccountInventoryStatus;
  accountType: string;
  accountAttribute: string;
  backupManagedBm: string;
  backupManagedBmId: string;
  cardNumber: string;
  cardStation: string;
  /** 渠道管理中的稳定渠道 ID。 */
  channelId?: string;
  /** 广告账户当前所属渠道名称，由服务端根据 channelId 返回。 */
  channelName?: string;
  /** 广告账户资产首次进入统一台账的时间。 */
  createdAt?: string;
  /** 广告账户下户日期，由飞书同步表 delivery_date 提供。 */
  deliveryDate?: string;
  /** 广告账户资产人工备注，不参与平台或飞书同步。 */
  remark?: string;
  /** 业务资料是否已被人工锁定。 */
  manuallyUpdated?: boolean;
  managedBm: string;
  managedBmId: string;
  timezone: string;
  /** 广告户分配的使用人 ID，仅由服务端同步。 */
  usageUserId?: string;
  /** 广告户分配的使用人名称，仅由服务端同步。 */
  usageUserName?: string;
  /** 使用人的当前主部门，仅供展示且由服务端实时推导。 */
  usageDepartmentName?: string;
  /** 平台与资产台账的同步状态。 */
  syncStatus?: 'MANUAL_LOCKED' | 'PLATFORM_MISSING' | 'SYNCED';
  assignments?: Array<{
    applicationId?: string;
    assignedAt?: string;
    id: string;
    primary: boolean;
    source: string;
    status: string;
    userId: string;
    userName: string;
  }>;
}

/** 按渠道名称精准查询广告账户资产。 */
export function getAdAccountAssetsByChannel(channelName: string) {
  return mainBackendClient.get<AdAccountAsset[]>(
    '/asset-management/ad-accounts/by-channel',
    { params: { channelName } },
  );
}

/** 查询当前用户通过新分配关系获得的广告账户。 */
export function getMyAdAccountAssets() {
  return mainBackendClient.get<AdAccountAsset[]>(
    '/asset-management/ad-accounts/mine',
  );
}

/** 恢复飞书自动同步。 */
export function resumeAdAccountAssetSync(accountId: string) {
  return mainBackendClient.post<AdAccountAsset>(
    `/asset-management/ad-accounts/${encodeURIComponent(accountId)}/resume-sync`,
  );
}

/** 整体替换广告账户当前使用人，未保留的关系由服务端转为历史记录。 */
export function replaceAdAccountAssetAssignments(
  accountId: string,
  userIds: string[],
  inventoryStatus: AdAccountInventoryStatus,
) {
  return mainBackendClient.put<AdAccountAsset>(
    `/asset-management/ad-accounts/${encodeURIComponent(accountId)}/assignments`,
    {
      source: 'MANUAL',
      userIds,
      inventoryStatus,
    },
  );
}

export interface AdAccountAssetPage {
  items: AdAccountAsset[];
  page: number;
  pageSize: number;
  total: number;
}

/** 广告账户分页查询参数；全部筛选条件在服务端分页前处理。 */
export interface AdAccountAssetPageParams {
  accountAttribute?: string[];
  accountId?: string[];
  accountName?: string[];
  accountStatus?: number[];
  accountType?: string[];
  backupManagedBm?: string[];
  backupManagedBmId?: string[];
  cardNumber?: string[];
  cardStation?: string[];
  channelName?: string[];
  inventoryStatus?: AdAccountInventoryStatus[];
  inventoryAssigneeName?: string[];
  keyword?: string;
  managedBm?: string[];
  managedBmId?: string[];
  page: number;
  pageSize: number;
  timezone?: string[];
  usageDepartment?: string[];
  usageUsers?: string[];
}

/** 广告账户全量查询沿用列表筛选条件，但不包含分页参数。 */
export type AdAccountAssetSearchAllParams = Omit<
  AdAccountAssetPageParams,
  'page' | 'pageSize'
>;

export interface AdAccountAssetImportFailure {
  accountId: string;
  line: number;
  message: string;
}

export interface AdAccountAssetImportResult {
  failures: AdAccountAssetImportFailure[];
  successCount: number;
  totalCount: number;
}

export interface AdAccountAssetImportHistory {
  createdAt: string;
  failures: AdAccountAssetImportFailure[];
  fileName: string;
  id: string;
  successCount: number;
  totalCount: number;
}

export interface AdAccountAssetImportFailedFile {
  contentBase64: string;
  fileName: string;
}

export type AdAccountAssetBatchField =
  | 'ACCOUNT_ATTRIBUTE'
  | 'ACCOUNT_TYPE'
  | 'BACKUP_MANAGED_BM'
  | 'BACKUP_MANAGED_BM_ID'
  | 'CARD_NUMBER'
  | 'CARD_STATION'
  | 'CHANNEL_ID'
  | 'INVENTORY_STATUS'
  | 'MANAGED_BM'
  | 'MANAGED_BM_ID'
  | 'REMARK'
  | 'TIMEZONE'
  | 'USAGE_USER_IDS';

/** 广告账户批量修改请求；changedFields 之外的字段不会被服务端覆盖。 */
export interface AdAccountAssetBatchUpdatePayload {
  accountAttribute?: string;
  accountIds: string[];
  accountType?: string;
  backupManagedBm?: string;
  backupManagedBmId?: string;
  cardNumber?: string;
  cardStation?: string;
  changedFields: AdAccountAssetBatchField[];
  channelId?: string;
  inventoryStatus?: AdAccountInventoryStatus;
  managedBm?: string;
  managedBmId?: string;
  remark?: string;
  timezone?: string;
  userIds?: string[];
}

export interface AdAccountAssetSpreadsheetRow
  extends Omit<AdAccountAssetBatchUpdatePayload, 'accountIds'> {
  accountId: string;
  accountName?: string;
}

export interface AdAccountAssetSpreadsheetSaveResult {
  createdCount: number;
  items: AdAccountAsset[];
  updatedCount: number;
}

export interface AdAccountLifecycleDetail {
  account: AdAccountAsset;
  events: Array<{
    actorName?: string;
    applicationId?: string;
    description?: string;
    eventType: string;
    extraData?: string;
    id: string;
    occurredAt: string;
    source?: 'FACEBOOK' | 'FACEBOOK_BAN_EVENT';
    status?: string;
    targetUserName?: string;
    teamName?: string;
    updateSource?: string;
    changes?: Array<{
      after?: {
        display?: string;
        redacted?: boolean;
        references?: Array<{ id?: string; name?: string }>;
      };
      before?: {
        display?: string;
        redacted?: boolean;
        references?: Array<{ id?: string; name?: string }>;
      };
      fieldKey: string;
      fieldLabel: string;
    }>;
  }>;
  usagePeriods: Array<{
    applicationId?: string;
    endedAt?: string;
    source?: string;
    startedAt: string;
    status: string;
    teamName?: string;
    userId: string;
    userName: string;
  }>;
}

export type AdAccountFacebookActivityCategory =
  | 'ACCOUNT'
  | 'ACCESS'
  | 'AD'
  | 'AD_SET'
  | 'AUDIENCE'
  | 'BILLING'
  | 'CAMPAIGN'
  | 'CREATIVE'
  | 'DELIVERY'
  | 'OTHER';

/** Facebook 操作中可直接展示的一项变更或属性摘要。 */
export interface AdAccountFacebookActivitySummaryItem {
  after?: null | string;
  before?: null | string;
  label: string;
  value?: null | string;
}

/** Facebook 广告账户的一条平台操作记录。 */
export interface AdAccountFacebookActivity {
  actorId?: string;
  actorName?: string;
  applicationId?: string;
  applicationName?: string;
  category: AdAccountFacebookActivityCategory;
  eventType: string;
  extraData?: string;
  id: string;
  localOccurredAt?: string;
  objectId?: string;
  objectName?: string;
  objectType?: string;
  occurredAt: string;
  summaryItems: AdAccountFacebookActivitySummaryItem[];
  tool?: string;
  translatedEventType?: string;
}

export interface AdAccountFacebookActivityPage {
  hasMore: boolean;
  items: AdAccountFacebookActivity[];
  nextAfter?: string;
  since: number;
  until: number;
}

export type AdAccountDailyLimitChangeType =
  | 'CLEAR'
  | 'DECREASE'
  | 'INCREASE'
  | 'SET';

/** Facebook 平台同步产生的一条广告账户日限额变化记录。 */
export interface AdAccountDailyLimitChange {
  changeType: AdAccountDailyLimitChangeType;
  changedAt: string;
  currentLimit?: null | number;
  id: string;
  previousLimit?: null | number;
  source: 'FACEBOOK';
}

export interface AdAccountDailyLimitChangePage {
  accountId: string;
  accountName?: string;
  currency?: string;
  currentLimit?: null | number;
  items: AdAccountDailyLimitChange[];
  lastSyncedAt?: string;
  page: number;
  pageSize: number;
  total: number;
}

export function getAdAccountLifecycle(accountId: string) {
  return mainBackendClient.get<AdAccountLifecycleDetail>(
    `/asset-management/ad-accounts/${encodeURIComponent(accountId)}/lifecycle`,
  );
}

/** 分页查询广告账户自入库以来的 Facebook 平台操作记录。 */
export function getAdAccountFacebookActivities(
  accountId: string,
  params: { after?: string; pageSize?: number; until?: number },
  config?: RequestClientConfig,
) {
  return mainBackendClient.get<AdAccountFacebookActivityPage>(
    `/asset-management/ad-accounts/${encodeURIComponent(accountId)}/facebook-activities`,
    { ...config, params },
  );
}

/** 分页查询广告账户的日限额变化记录。 */
export function getAdAccountDailyLimitChanges(
  accountId: string,
  params: { page?: number; pageSize?: number },
  config?: RequestClientConfig,
) {
  return mainBackendClient.get<AdAccountDailyLimitChangePage>(
    `/asset-management/ad-accounts/${encodeURIComponent(accountId)}/daily-limit-changes`,
    { ...config, params },
  );
}

/** 渠道管理维护的广告账户属性配置。 */
export interface AdAccountAttribute {
  accountAttribute: string;
  createTime: string;
  id: string;
}

export function getAdAccountAssetPage(params: AdAccountAssetPageParams) {
  return mainBackendClient.get<AdAccountAssetPage>(
    '/asset-management/ad-accounts',
    { params, paramsSerializer: 'repeat' },
  );
}

/** 按资产管理页当前筛选条件一次返回全部广告账户。 */
export function searchAllAdAccountAssets(
  params: AdAccountAssetSearchAllParams,
) {
  const { accountStatus, keyword, ...filter } = params;
  return mainBackendClient.post<AdAccountAsset[]>(
    '/asset-management/ad-accounts/search-all',
    {
      filter: { ...filter, accountStatuses: accountStatus },
      keyword,
    },
  );
}

/** 按广告账户 ID 批量获取与资产管理页面一致的台账展示数据。 */
export function getAdAccountAssetsByIds(accountIds: string[]) {
  return mainBackendClient.post<AdAccountAsset[]>(
    '/asset-management/ad-accounts/batch',
    { accountIds },
  );
}

export function updateAdAccountAsset(
  accountId: string,
  payload: Omit<AdAccountAsset, 'accountId'>,
  config?: RequestClientConfig,
) {
  // 展示快照和平台只读字段不参与人工维护，避免编辑表单把 Mongo 数据回写到资产台账。
  const {
    accountDailyLimit: _accountDailyLimit,
    channelName: _channelName,
    inventoryStatus: _inventoryStatus,
    ...request
  } = payload;
  return mainBackendClient.put<AdAccountAsset>(
    `/asset-management/ad-accounts/${encodeURIComponent(accountId)}`,
    request,
    config,
  );
}

export function batchUpdateAdAccountAssets(
  payload: AdAccountAssetBatchUpdatePayload,
) {
  return mainBackendClient.request<AdAccountAsset[]>(
    '/asset-management/ad-accounts/batch',
    { data: payload, method: 'PATCH' },
  );
}

export function saveAdAccountAssetSpreadsheet(
  rows: AdAccountAssetSpreadsheetRow[],
) {
  return mainBackendClient.post<AdAccountAssetSpreadsheetSaveResult>(
    '/asset-management/ad-accounts/spreadsheet',
    { rows },
  );
}

export function importAdAccountAssets(file: File) {
  const data = new FormData();
  data.append('file', file);
  return mainBackendClient.post<AdAccountAssetImportResult>(
    '/asset-management/ad-accounts/import-file',
    data,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
}

export function getAdAccountImportHistory() {
  return mainBackendClient.get<AdAccountAssetImportHistory[]>(
    '/asset-management/ad-accounts/import-records',
  );
}

export function getAdAccountImportFailedFile(id: string) {
  return mainBackendClient.get<AdAccountAssetImportFailedFile>(
    `/asset-management/ad-accounts/import-records/${encodeURIComponent(id)}/failed-file`,
  );
}

export function getAdAccountAttributes() {
  return mainBackendClient.get<AdAccountAttribute[]>(
    '/asset-management/ad-accounts/attributes',
  );
}

export function createAdAccountAttribute(
  data: Pick<AdAccountAttribute, 'accountAttribute'>,
) {
  return mainBackendClient.post<AdAccountAttribute>(
    '/asset-management/ad-accounts/attributes',
    data,
  );
}

export function updateAdAccountAttribute(
  id: string,
  data: Pick<AdAccountAttribute, 'accountAttribute'>,
) {
  return mainBackendClient.put<AdAccountAttribute>(
    `/asset-management/ad-accounts/attributes/${encodeURIComponent(id)}`,
    data,
  );
}

export function deleteAdAccountAttribute(id: string) {
  return mainBackendClient.delete<void>(
    `/asset-management/ad-accounts/attributes/${encodeURIComponent(id)}`,
  );
}
