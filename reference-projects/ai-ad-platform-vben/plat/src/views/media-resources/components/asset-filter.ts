import { FACEBOOK_AD_ACCOUNT_STATUS_LABELS } from '#/constants/facebook-ad-account-status';

export type AssetFilterControl =
  | 'date'
  | 'department'
  | 'password'
  | 'select'
  | 'text'
  | 'user';

export interface AssetFilterOption {
  label: string;
  value: string;
}

export interface AssetFilterField {
  control?: AssetFilterControl;
  key: string;
  label: string;
  options?: readonly AssetFilterOption[];
  placeholder?: string;
}

export type AssetFilterValue = string | string[];

export type AssetFilterValues = Record<string, AssetFilterValue>;

export const AD_ACCOUNT_ASSET_FILTER_FIELDS: readonly AssetFilterField[] = [
  { key: 'accountName', label: '账户名称' },
  { key: 'accountId', label: '账户 ID' },
  {
    control: 'select',
    key: 'accountStatus',
    label: '平台状态',
    options: Object.entries(FACEBOOK_AD_ACCOUNT_STATUS_LABELS).map(
      ([value, label]) => ({ label, value }),
    ),
  },
  { control: 'select', key: 'accountType', label: '账户类型' },
  { control: 'select', key: 'accountAttribute', label: '账户属性' },
  { control: 'select', key: 'channelName', label: '所属渠道' },
  { key: 'managedBm', label: '管理 BM' },
  { key: 'managedBmId', label: '管理 BM ID' },
  { key: 'backupManagedBm', label: '备份 BM' },
  { key: 'backupManagedBmId', label: '备份 BM ID' },
  { key: 'timezone', label: '时区' },
  { key: 'cardStation', label: '卡台' },
  { key: 'cardNumber', label: '卡号' },
  { control: 'user', key: 'usageUsers', label: '使用人' },
  { control: 'department', key: 'usageDepartment', label: '使用团队' },
  {
    control: 'select',
    key: 'inventoryStatus',
    label: '库存状态',
    options: [
      { label: '已分配', value: 'ASSIGNED' },
      { label: '可用', value: 'AVAILABLE' },
      { label: '已停用', value: 'DISABLED' },
      { label: '待回收', value: 'RETURN_PENDING' },
    ],
  },
  { control: 'user', key: 'inventoryAssigneeName', label: '库存使用人' },
];

function appendSearchableValues(value: unknown, values: string[]) {
  if (value === undefined || value === null) return;

  if (Array.isArray(value)) {
    value.forEach((item) => appendSearchableValues(item, values));
    return;
  }

  if (typeof value === 'object') {
    Object.values(value).forEach((item) =>
      appendSearchableValues(item, values),
    );
    return;
  }

  values.push(String(value));
}

/**
 * 将筛选控件值规范为去重后的候选值列表。
 *
 * @remarks
 * 文本框按空格或换行拆分；下拉、人员和部门选项可能包含空格，必须保留完整值。
 */
export function normalizeAssetFilterValues(
  value: AssetFilterValue | null | undefined,
  control: AssetFilterControl = 'text',
) {
  const sourceValues = Array.isArray(value) ? value : [value ?? ''];
  const shouldSplitWhitespace = control === 'password' || control === 'text';
  const values = sourceValues.flatMap((item) =>
    shouldSplitWhitespace ? item.split(/\s+/) : [item],
  );

  return [...new Set(values.map((item) => item.trim()).filter(Boolean))];
}

export function isAssetFilterValueActive(
  value: AssetFilterValue | null | undefined,
) {
  return Array.isArray(value)
    ? value.some((item) => Boolean(item.trim()))
    : Boolean(value?.trim());
}

/** 将资产的嵌套详情、数组和基础字段统一纳入关键词匹配。 */
export function matchesAssetKeyword(
  values: readonly unknown[],
  keyword: string,
) {
  const query = keyword.trim().toLocaleLowerCase();
  if (!query) return true;

  const searchableValues: string[] = [];
  values.forEach((value) => appendSearchableValues(value, searchableValues));
  return searchableValues.join(' ').toLocaleLowerCase().includes(query);
}

/** 文本筛选使用包含匹配，枚举使用精确匹配，日期同时兼容日期时间值。 */
export function matchesAssetFilterValue(
  actualValue: unknown,
  expectedValue: AssetFilterValue,
  control: AssetFilterControl = 'text',
) {
  const expectedValues = normalizeAssetFilterValues(expectedValue, control).map(
    (value) => value.toLocaleLowerCase(),
  );
  if (expectedValues.length === 0) return true;

  const actualValues: string[] = [];
  appendSearchableValues(actualValue, actualValues);
  const normalizedActualValues = actualValues.map((value) =>
    value.trim().toLocaleLowerCase(),
  );

  return expectedValues.some((expected) =>
    normalizedActualValues.some((actual) => {
      if (control === 'select') return actual === expected;
      if (control === 'date') return actual.startsWith(expected);
      return actual.includes(expected);
    }),
  );
}
