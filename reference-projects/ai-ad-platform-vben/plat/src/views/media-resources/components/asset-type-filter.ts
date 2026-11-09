import type { MediaAssetType } from '#/api';

import {
  findInventoryAssetTypeBySubtype,
  INVENTORY_ASSET_TYPES,
  resolveInventoryAssetTypeLabel,
} from './asset-types';

export const inventoryAssetTypeFilterOptions = [
  { label: '全部资产类型', value: 'all' },
  ...INVENTORY_ASSET_TYPES.map((item) => ({
    label: item.label,
    value: item.subtype,
  })),
];

export interface InventoryAssetTypeFilterParams {
  assetSubtype?: string;
  assetType?: MediaAssetType;
}

/**
 * 将前端十类业务资产筛选值转换为后端主类型与必要的子类型参数。
 *
 * @remarks
 * 个号与微信号共用 PERSONAL 主类型，必须同时传 inventorySubtype 才能在分页查询中准确区分。
 */
export function resolveInventoryAssetTypeFilter(
  subtype: string,
): InventoryAssetTypeFilterParams {
  const assetType = findInventoryAssetTypeBySubtype(subtype);
  if (!assetType) return {};

  const sharesMainType =
    INVENTORY_ASSET_TYPES.filter(
      (item) => item.assetType === assetType.assetType,
    ).length > 1;

  return {
    assetSubtype: sharesMainType ? assetType.subtype : undefined,
    assetType: assetType.assetType,
  };
}

/** 判断资产是否符合十类业务资产筛选，兼容缺少子类型的历史个号。 */
export function matchesInventoryAssetTypeFilter(
  assetType: string,
  secretData: string | undefined,
  subtype: string,
) {
  const selectedType = findInventoryAssetTypeBySubtype(subtype);
  if (!selectedType) return true;
  if (selectedType.assetType !== assetType) return false;

  const sharesMainType =
    INVENTORY_ASSET_TYPES.filter((item) => item.assetType === assetType)
      .length > 1;
  if (!sharesMainType) return true;

  return (
    resolveInventoryAssetTypeLabel(assetType, secretData) === selectedType.label
  );
}
