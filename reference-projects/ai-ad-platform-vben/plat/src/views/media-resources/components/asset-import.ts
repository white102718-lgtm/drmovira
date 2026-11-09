import type { MediaAssetType } from '#/api';

import {
  getInventoryAssetTemplateFields,
  resolveInventoryAssetType,
  type InventoryAssetTypeMeta,
} from './asset-types';

export const ASSET_IMPORT_MAX_FILE_SIZE = 5 * 1024 * 1024;
export const ASSET_IMPORT_MAX_ROWS = 5000;

export interface AssetImportChannelOption {
  label: string;
  value: string;
}

export interface AssetImportUserOption {
  available: boolean;
  label: string;
  name: string;
  value: string;
}

export interface AssetImportRow {
  assigneeId: string;
  assetCode: string;
  assetName: string;
  assetType: MediaAssetType;
  birthday: string;
  channelId: string;
  channelName: string;
  createDate: string;
  details: Record<string, string>;
  emailLoginUrl: string;
  gender: string;
  issues: string[];
  line: number;
  owner: string;
  password: string;
  remark: string;
  subtype: string;
  status: 'allocated' | 'available';
  twoFactorKey: string;
  valid: boolean;
}

export interface AssetImportFailure {
  line: number;
  message: string;
}

export interface AssetImportSubmitResult {
  failures: AssetImportFailure[];
  successCount: number;
}

type ImportRecord = Record<string, unknown>;

const supportedAssetTypeMessage =
  '资产类型仅支持 FB、TG号、微信号、BM、像素、主页、电脑、手机、静态 IP 或邮箱；广告户请使用广告户台账导入更新';

const detailHeaderAliases: Record<string, string[]> = {
  accountName: ['个号名称'],
  createDate: ['创建日期', '个号创建日期'],
  email: ['邮箱账号'],
  twoFa: ['2FA密钥', 'twoFactorKey'],
};

const genderAliases: Record<string, string> = {
  female: 'FEMALE',
  male: 'MALE',
  女: 'FEMALE',
  男: 'MALE',
};

function cell(record: ImportRecord, ...headers: string[]) {
  for (const header of headers) {
    const value = record[header];
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value).trim();
    }
  }
  return '';
}

function findImportUser(
  usageUser: string,
  userOptions: AssetImportUserOption[],
) {
  const normalizedName = usageUser.trim();
  return userOptions.filter(
    (user) =>
      user.available &&
      (user.name.trim() === normalizedName ||
        user.label.trim() === normalizedName),
  );
}

function normalizeDate(value: string) {
  const matched = value.match(/^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$/);
  if (!matched) return value;
  const [, year, month, day] = matched;
  return `${year}-${month?.padStart(2, '0')}-${day?.padStart(2, '0')}`;
}

function isValidDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  if (year === undefined || month === undefined || day === undefined) {
    return false;
  }
  const date = new Date(year, month - 1, day);
  return (
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day
  );
}

/**
 * 将表格行转换成可提交资产，并在预览阶段完成字段、渠道与重复项校验。
 */
export function normalizeAssetImportRows(
  records: ImportRecord[],
  channelOptions: AssetImportChannelOption[],
  existingAssetKeys: ReadonlySet<string> = new Set(),
  userOptions: AssetImportUserOption[] = [],
  selectedAssetType?: InventoryAssetTypeMeta,
) {
  const channelsById = new Map(
    channelOptions.map((channel) => [channel.value, channel]),
  );
  const channelsByName = new Map<string, AssetImportChannelOption[]>();
  for (const channel of channelOptions) {
    const channels = channelsByName.get(channel.label) ?? [];
    channels.push(channel);
    channelsByName.set(channel.label, channels);
  }

  const seenAssetKeys = new Set<string>();
  return records.map<AssetImportRow>((record, index) => {
    const line = index + 2;
    const issues: string[] = [];
    const rawAssetType = cell(record, '资产类型', 'assetType').toLowerCase();
    // 单类型模板不再要求“资产类型”列，以下拉框中明确选择的类型作为唯一规则来源。
    const typeMeta =
      selectedAssetType ?? resolveInventoryAssetType(rawAssetType);
    const details = Object.fromEntries(
      (typeMeta ? getInventoryAssetTemplateFields(typeMeta) : []).map(
        (field) => {
          const aliases = detailHeaderAliases[field.key] ?? [];
          let value = cell(
            record,
            field.excelHeader ?? field.label,
            field.label,
            field.key,
            ...aliases,
          );
          if (field.type === 'date') value = normalizeDate(value);
          const selectedOption = field.options?.find(
            (option) =>
              option.value.toLowerCase() === value.toLowerCase() ||
              option.label.toLowerCase() === value.toLowerCase(),
          );
          if (selectedOption) value = selectedOption.value;
          return [field.key, value];
        },
      ),
    );
    const genericAssetCode = cell(record, '唯一标识', '资产编码', 'assetCode');
    const genericAssetName = cell(record, '资产名称', 'assetName');
    if (typeMeta) {
      details[typeMeta.identifierKey] ||= genericAssetCode;
      details[typeMeta.nameKey] ||= genericAssetName;
    }
    const assetCode =
      genericAssetCode ||
      (typeMeta ? details[typeMeta.identifierKey] : '') ||
      '';
    const assetName =
      genericAssetName ||
      (typeMeta ? details[typeMeta.nameKey] : '') ||
      assetCode;
    const rawChannelId = cell(record, '渠道ID', 'channelId');
    const rawChannelName = cell(record, '渠道名称', '归属渠道', 'channelName');
    const matchedByName = channelsByName.get(rawChannelName) ?? [];
    let channel: AssetImportChannelOption | undefined;
    if (rawChannelId) channel = channelsById.get(rawChannelId);
    else if (matchedByName.length === 1) channel = matchedByName[0];
    const createDate = details.createDate ?? '';
    const password = details.password ?? '';
    const twoFactorKey = details.twoFa ?? '';
    const rawGender = (details.gender ?? '').toLowerCase();
    const gender = rawGender ? (genderAliases[rawGender] ?? '') : '';
    if (details.gender !== undefined) details.gender = gender;
    const usageUser = cell(record, typeMeta?.usageUserHeader ?? '使用人');
    const matchedUsers = usageUser
      ? findImportUser(usageUser, userOptions)
      : [];
    const assigneeId = matchedUsers[0]?.value ?? '';
    const owner = matchedUsers[0]?.name ?? '';
    const status = usageUser ? 'allocated' : 'available';

    if (!typeMeta || typeMeta.assetType === 'AD_ACCOUNT') {
      issues.push(supportedAssetTypeMessage);
    }
    if (!assetName) issues.push('资产名称不能为空');
    if (!assetCode) issues.push('唯一标识不能为空');
    if (typeMeta?.requiresChannel && !rawChannelId && !rawChannelName) {
      issues.push('渠道 ID 或渠道名称不能为空');
    } else if ((rawChannelId || rawChannelName) && !channel) {
      issues.push(
        !rawChannelId && matchedByName.length > 1
          ? '渠道名称重复，请填写渠道 ID'
          : '渠道不存在或已停用',
      );
    }
    if (rawGender && !gender) issues.push('性别仅支持男、女或未填写');
    if (usageUser && matchedUsers.length === 0) {
      issues.push('使用人不存在、已停用或未加载用户列表');
    } else if (matchedUsers.length > 1) {
      issues.push('使用人重名，请使用系统内唯一的姓名');
    }

    for (const field of typeMeta?.fields ?? []) {
      const value = details[field.key] ?? '';
      if (field.required && !value) issues.push(`${field.label}不能为空`);
      if (value && field.type === 'date' && !isValidDate(value)) {
        issues.push(`${field.label}格式应为 YYYY-MM-DD`);
      }
      if (
        value &&
        field.options &&
        !field.options.some((option) => option.value === value)
      ) {
        issues.push(
          `${field.label}仅支持${field.options.map((option) => option.label).join('、')}`,
        );
      }
    }

    if (typeMeta && assetCode) {
      const assetKey = `${typeMeta.assetType}:${assetCode.toLowerCase()}`;
      if (existingAssetKeys.has(assetKey)) issues.push('资产已存在');
      if (seenAssetKeys.has(assetKey)) issues.push('文件内资产重复');
      seenAssetKeys.add(assetKey);
    }

    return {
      assigneeId,
      assetCode,
      assetName,
      assetType: typeMeta?.assetType ?? 'PERSONAL',
      birthday: normalizeDate(cell(record, '生日', 'birthday')),
      channelId: channel?.value ?? rawChannelId,
      channelName: channel?.label ?? rawChannelName,
      createDate,
      details,
      emailLoginUrl: cell(record, '邮箱登录网址', 'emailLoginUrl'),
      gender,
      issues,
      line,
      owner,
      password,
      remark: cell(record, '备注', 'remark'),
      subtype: typeMeta?.subtype ?? '',
      status,
      twoFactorKey,
      valid: issues.length === 0,
    };
  });
}
