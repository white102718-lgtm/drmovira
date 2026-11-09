import type { AdAccountAsset } from '#/api';
import type { AssetFilterControl, AssetFilterValues } from './asset-filter';

import { matchesAssetFilterValue, matchesAssetKeyword } from './asset-filter';

export interface MyAdAccountAssetRecord {
  accountAttribute?: string;
  accountType?: string;
  applicationId?: string;
  backupManagedBm?: string;
  backupManagedBmId?: string;
  cardNumber?: string;
  cardStation?: string;
  category: 'advertising';
  channelId?: string;
  channelName?: string;
  createdAt: string;
  details: Record<string, string>;
  id: string;
  identifier: string;
  inventoryAssigneeName?: string;
  inventoryStatus: string;
  managedBm?: string;
  managedBmId?: string;
  name: string;
  owner: string;
  status: 'allocated' | 'available' | 'exception' | 'return_pending';
  subtype: 'ad_account';
  timezone?: string;
  usageDepartment?: string;
  usageUsers?: string;
}

function accountStatus(status?: string): MyAdAccountAssetRecord['status'] {
  if (status === 'ASSIGNED') return 'allocated';
  if (status === 'AVAILABLE') return 'available';
  if (status === 'RETURN_PENDING') return 'return_pending';
  return 'exception';
}

/** 将 main 广告账户台账转换为“我的资产”现有列表模型。 */
export function mapMyAdAccountAssets(
  accounts: readonly AdAccountAsset[],
  currentUserId: string,
): MyAdAccountAssetRecord[] {
  return accounts.map((account) => {
    const currentAssignment = account.assignments?.find(
      (assignment) => assignment.userId === currentUserId,
    );
    const accountId = account.accountId.trim();
    const rawAccountName = account.accountName.trim();
    const accountName = rawAccountName || `广告账户 ${accountId}`;
    const inventoryStatus = account.inventoryStatus ?? 'ASSIGNED';

    return {
      accountAttribute: account.accountAttribute,
      accountType: account.accountType,
      applicationId: currentAssignment?.applicationId,
      backupManagedBm: account.backupManagedBm,
      backupManagedBmId: account.backupManagedBmId,
      cardNumber: account.cardNumber,
      cardStation: account.cardStation,
      category: 'advertising',
      channelId: account.channelId,
      channelName: account.channelName,
      createdAt:
        currentAssignment?.assignedAt ??
        account.createdAt ??
        account.deliveryDate ??
        '',
      details: { accountId, accountName: rawAccountName },
      id: accountId,
      identifier: accountId,
      inventoryAssigneeName: account.usageUserName,
      inventoryStatus,
      managedBm: account.managedBm,
      managedBmId: account.managedBmId,
      name: accountName,
      owner: account.usageUserName?.trim() || '',
      status: accountStatus(inventoryStatus),
      subtype: 'ad_account',
      timezone: account.timezone,
      usageDepartment: account.usageDepartmentName,
      usageUsers: account.usageUserName,
    };
  });
}

/** 个人广告户接口返回全量数据，列表在浏览器端沿用当前筛选语义。 */
export function filterMyAdAccountAssets(
  records: readonly MyAdAccountAssetRecord[],
  keyword: string,
  filters: AssetFilterValues,
  filterControls: Readonly<Record<string, AssetFilterControl | undefined>>,
) {
  return records.filter(
    (record) =>
      matchesAssetKeyword([record], keyword) &&
      Object.entries(filters).every(([key, expected]) =>
        matchesAssetFilterValue(
          Reflect.get(record, key),
          expected,
          filterControls[key],
        ),
      ),
  );
}

export function paginateMyAdAccountAssets(
  records: readonly MyAdAccountAssetRecord[],
  page: number,
  pageSize: number,
) {
  const start = (page - 1) * pageSize;
  return records.slice(start, start + pageSize);
}
