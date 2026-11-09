import type { MediaAsset, MediaAssetType } from '#/api';

export const SOCIAL_ASSET_TYPE_OPTIONS = [
  'TG号',
  '微信号',
  'Facebook 账号',
] as const;

export interface SocialAssetSelection {
  assetType: MediaAssetType;
  label: (typeof SOCIAL_ASSET_TYPE_OPTIONS)[number];
  subtype: 'fb' | 'telegram' | 'wechat';
}

/**
 * 将申请表中的社交资产类型转换为库存查询条件。
 *
 * @remarks
 * 微信号与 Facebook 账号暂时共用后端 PERSONAL 枚举，使用库存详情中的子类型继续区分。
 */
export function resolveSocialAssetSelection(
  value: unknown,
): SocialAssetSelection | undefined {
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase()
    .replaceAll(' ', '');
  if (['telegram', 'tg', 'tg号'].includes(normalized)) {
    return { assetType: 'TG', label: 'TG号', subtype: 'telegram' };
  }
  if (['wechat', '微信', '微信号'].includes(normalized)) {
    return { assetType: 'PERSONAL', label: '微信号', subtype: 'wechat' };
  }
  if (
    ['facebook', 'facebookaccount', 'facebook账号', '个号'].includes(normalized)
  ) {
    return {
      assetType: 'PERSONAL',
      label: 'Facebook 账号',
      subtype: 'fb',
    };
  }
}

function inventorySubtype(secretData?: string) {
  if (!secretData) return 'fb';
  try {
    const parsed: unknown = JSON.parse(secretData);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return 'fb';
    }
    const subtype = (parsed as Record<string, unknown>).inventorySubtype;
    return typeof subtype === 'string' && subtype.trim()
      ? subtype.trim()
      : 'fb';
  } catch {
    return 'fb';
  }
}

/** 过滤办理阶段的库存，确保 PERSONAL 库存仍按微信号与 Facebook 账号精确匹配。 */
export function matchesSocialInventoryAsset(
  asset: Pick<MediaAsset, 'assetType' | 'secretData'>,
  selection: SocialAssetSelection,
) {
  if (asset.assetType !== selection.assetType) return false;
  if (selection.assetType !== 'PERSONAL') return true;
  return inventorySubtype(asset.secretData) === selection.subtype;
}
