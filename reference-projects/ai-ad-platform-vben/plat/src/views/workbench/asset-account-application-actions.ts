import { accountOperationEntries } from './account-operation-entries';

/** 用于区分从“我的资产”进入的账户操作，申请页据此只加载当前用户已分配的账户。 */
export const MY_ASSET_ACCOUNT_APPLICATION_SOURCE = 'my-assets';

/** “我的资产”中广告账户可直接发起的申请操作。 */
export const assetAccountApplicationActions = [
  ...accountOperationEntries.map((entry) => ({
    applicationCode: entry.applicationCode,
    label:
      entry.operationType === '活跃清零'
        ? '清零'
        : entry.operationType === '活跃清零回收'
          ? '清零回收'
          : entry.operationType,
  })),
] as const;

export type AssetAccountApplicationAction =
  (typeof assetAccountApplicationActions)[number];

/** 创建资源申请深链，使用稳定申请编码并携带当前广告账户。 */
export function createAssetAccountApplicationRoute(
  asset: { account: string; name: string },
  action: AssetAccountApplicationAction,
) {
  return {
    path: '/workbench/applications/create',
    query: {
      adAccountId: asset.account,
      adAccountName: asset.name,
      applicationCode: action.applicationCode,
      new: '1',
      source: MY_ASSET_ACCOUNT_APPLICATION_SOURCE,
    },
  };
}
