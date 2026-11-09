// @ts-nocheck -- 仓库当前未向 plat 的生产类型检查暴露 Vitest 类型。
import { describe, expect, it } from 'vitest';

import { FACEBOOK_AD_ACCOUNT_STATUS_LABELS } from '#/constants/facebook-ad-account-status';

import {
  AD_ACCOUNT_ASSET_FILTER_FIELDS,
  isAssetFilterValueActive,
  matchesAssetFilterValue,
  normalizeAssetFilterValues,
} from './asset-filter';

describe('asset filters', () => {
  it('exposes every known platform status as an exact-match filter', () => {
    const field = AD_ACCOUNT_ASSET_FILTER_FIELDS.find(
      (item) => item.key === 'accountStatus',
    );

    expect(field).toMatchObject({ control: 'select', label: '平台状态' });
    expect(field?.options).toEqual(
      Object.entries(FACEBOOK_AD_ACCOUNT_STATUS_LABELS).map(
        ([value, label]) => ({ label, value }),
      ),
    );
    expect(matchesAssetFilterValue(1, ['1', '2'], 'select')).toBe(true);
    expect(matchesAssetFilterValue(10, ['1', '2'], 'select')).toBe(false);
  });

  it('splits text values by whitespace and removes duplicates', () => {
    expect(normalizeAssetFilterValues('A  B\nA\tC', 'text')).toEqual([
      'A',
      'B',
      'C',
    ]);
  });

  it('keeps spaces inside dropdown values', () => {
    expect(
      normalizeAssetFilterValues(
        ['Mpower SEA 核心代理', 'Firefly 拉美号商'],
        'select',
      ),
    ).toEqual(['Mpower SEA 核心代理', 'Firefly 拉美号商']);
  });

  it('matches any value inside one field', () => {
    expect(
      matchesAssetFilterValue('Alpha account', 'missing alpha', 'text'),
    ).toBe(true);
    expect(
      matchesAssetFilterValue(
        'Mpower SEA 核心代理',
        ['Firefly 拉美号商', 'Mpower SEA 核心代理'],
        'select',
      ),
    ).toBe(true);
    expect(
      matchesAssetFilterValue('2026-09-21T10:00:00', '2026-09-21', 'date'),
    ).toBe(true);
  });

  it('detects active scalar and array filters', () => {
    expect(isAssetFilterValueActive('  ')).toBe(false);
    expect(isAssetFilterValueActive([])).toBe(false);
    expect(isAssetFilterValueActive(['', '企业户'])).toBe(true);
  });
});
