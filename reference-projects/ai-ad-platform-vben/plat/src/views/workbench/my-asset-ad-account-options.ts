import type { AdAccountAsset } from '#/api/main';

/** 将“我的资产”中的广告账户转换为申请表单选项，去重后保留后端提供的稳定账户 ID。 */
export function buildMyAssetAdAccountOptions(
  assets: readonly Pick<AdAccountAsset, 'accountId' | 'accountName'>[],
): Array<{ label: string; value: string }> {
  const seen = new Set<string>();

  return assets.flatMap((asset) => {
    const accountId = asset.accountId.trim();
    if (!accountId || seen.has(accountId)) return [];
    seen.add(accountId);
    return [
      {
        label: `${asset.accountName || '未命名账户'}（${accountId}）`,
        value: accountId,
      },
    ];
  });
}
