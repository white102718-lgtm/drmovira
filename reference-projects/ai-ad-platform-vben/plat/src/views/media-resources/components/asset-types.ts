import type { MediaAssetType } from '#/api';

export type InventoryAssetCategory = 'advertising' | 'network' | 'personal';

export interface InventoryAssetFieldOption {
  label: string;
  value: string;
}

export interface InventoryAssetField {
  /** Excel 模板中的精确表头；带 * 的表头同时作为必填规则的唯一来源。 */
  excelHeader?: string;
  helpText?: string;
  key: string;
  label: string;
  options?: InventoryAssetFieldOption[];
  placeholder?: string;
  required?: boolean;
  type?: 'date' | 'password' | 'select' | 'text' | 'url';
}

export type InventoryAssetPresentationKey =
  | `detail.${string}`
  | 'projectName'
  | 'remark'
  | 'usageTeam';

export type InventoryAssetEditorFieldKey =
  | `detail.${string}`
  | 'channel'
  | 'inventoryStatus'
  | 'project'
  | 'remark'
  | 'usageTeam'
  | 'usageUsers';

/** 广告账户编辑抽屉与批量 Excel 共享的字段顺序和基础编辑方式。 */
export const AD_ACCOUNT_EDITOR_FIELDS = [
  {
    editable: false,
    key: 'accountId',
    label: '账户 ID',
    required: true,
    type: 'text',
  },
  { editable: false, key: 'accountName', label: '账户名称', type: 'text' },
  {
    editable: false,
    key: 'accountDailyLimit',
    label: '账户日限额',
    type: 'text',
  },
  { key: 'accountType', label: '账户类型', type: 'select' },
  { key: 'accountAttribute', label: '账户属性', type: 'select' },
  { key: 'channelId', label: '所属渠道', type: 'select' },
  { key: 'managedBm', label: '管理 BM', type: 'text' },
  { key: 'managedBmId', label: '管理 BM ID', type: 'text' },
  { key: 'backupManagedBm', label: '备份 BM', type: 'text' },
  { key: 'backupManagedBmId', label: '备份 BM ID', type: 'text' },
  { key: 'timezone', label: '时区', type: 'text' },
  { key: 'cardStation', label: '卡台', type: 'text' },
  { key: 'cardNumber', label: '卡号', type: 'textarea' },
  {
    key: 'inventoryStatus',
    label: '库存状态',
    required: true,
    type: 'select',
  },
  { key: 'userIds', label: '使用人', type: 'user' },
  { key: 'remark', label: '备注', type: 'textarea' },
] as const;

export interface InventoryAssetTypeMeta {
  aliases: readonly string[];
  assetType: MediaAssetType;
  category: InventoryAssetCategory;
  /** Excel 9.3 模板中的工作表名称。 */
  excelSheetName?: string;
  /** Excel 模板的字段顺序；未设置时沿用资产编辑的字段顺序。 */
  excelFieldKeys?: readonly string[];
  /** 不属于加密明细、但允许在 Excel 导入时填写的资产归属字段。 */
  importContextHeaders?: readonly string[];
  /** 跨列表、编辑、导入和导出的业务信息顺序。 */
  presentationKeys?: readonly InventoryAssetPresentationKey[];
  fields: readonly InventoryAssetField[];
  identifierKey: string;
  label: string;
  nameKey: string;
  requiresChannel: boolean;
  subtype: string;
  /** Excel 的“使用人”不属于资产明细字段，导入时用于建立库存分配关系。 */
  usageUserHeader?: string;
}

/**
 * 资产库存统一支持的业务资产目录。
 *
 * @remarks
 * 录入抽屉、批量导入和接口类型映射必须共用此目录，避免不同入口支持范围不一致。
 */
export const INVENTORY_ASSET_TYPES: readonly InventoryAssetTypeMeta[] = [
  {
    aliases: ['ad account', 'ad_account', '广告账户', '广告户'],
    assetType: 'AD_ACCOUNT',
    category: 'advertising',
    fields: [
      { key: 'accountId', label: '账户 ID', required: true },
      { key: 'accountName', label: '账户名称' },
    ],
    identifierKey: 'accountId',
    label: '广告户',
    nameKey: 'accountName',
    requiresChannel: true,
    subtype: 'ad_account',
  },
  {
    aliases: [
      'fb',
      '个号',
      'facebook account',
      'facebook账号',
      'facebook 账号',
    ],
    assetType: 'PERSONAL',
    category: 'advertising',
    excelSheetName: '个号',
    fields: [
      {
        excelHeader: '*个号创建日期',
        key: 'createDate',
        label: '个号创建日期',
        required: true,
        type: 'date',
      },
      { key: 'accountName', label: '名字' },
      { excelHeader: '*邮箱', key: 'email', label: '邮箱', required: true },
      {
        excelHeader: '*密码',
        key: 'password',
        label: '密码',
        required: true,
        type: 'password',
      },
      {
        excelHeader: '*2fa',
        key: 'twoFa',
        label: '2fa',
        required: true,
        type: 'password',
      },
      { key: 'phoneNumber', label: '手机号' },
      { key: 'birthday', label: '生日', type: 'date' },
      {
        key: 'gender',
        label: '性别',
        options: [
          { label: '男', value: 'MALE' },
          { label: '女', value: 'FEMALE' },
        ],
        type: 'select',
      },
      { key: 'assignmentDate', label: '分配日期', type: 'date' },
      { key: 'cookie', label: 'Cookie', type: 'password' },
      {
        key: 'emailLoginUrl',
        label: '邮箱登录网址',
        placeholder: 'https://mail.example.com',
        type: 'url',
      },
    ],
    identifierKey: 'email',
    label: '个号',
    nameKey: 'accountName',
    requiresChannel: false,
    subtype: 'fb',
    usageUserHeader: '使用人',
  },
  {
    aliases: ['bm'],
    assetType: 'BM',
    category: 'advertising',
    excelSheetName: 'BM',
    fields: [
      { key: 'date', label: '日期', type: 'date' },
      { key: 'usagePurpose', label: '使用途径' },
      { key: 'bmName', label: 'BM 名称' },
      { excelHeader: '*BMID', key: 'bmId', label: 'BMID', required: true },
      {
        key: 'bmLink',
        label: 'BM 链接',
        placeholder: 'https://business.facebook.com/...',
        type: 'url',
      },
      {
        key: 'operatorFbAccount',
        label: '使用人个号',
      },
      { key: 'assignedDate', label: 'BM 挂日期', type: 'date' },
      {
        key: 'supplierRemoved',
        label: '是否移除供应商',
        options: [
          { label: '是', value: 'YES' },
          { label: '否', value: 'NO' },
        ],
        type: 'select',
      },
    ],
    identifierKey: 'bmId',
    label: 'BM',
    nameKey: 'bmName',
    requiresChannel: true,
    subtype: 'bm',
    usageUserHeader: '使用人',
  },
  {
    aliases: ['pixel', '像素'],
    assetType: 'PIXEL',
    category: 'advertising',
    excelSheetName: '像素',
    excelFieldKeys: [
      'bmName',
      'bmId',
      'pixelName',
      'pixelId',
      'accessToken',
      'pixelTestCode',
    ],
    fields: [
      {
        excelHeader: '*BM名称',
        key: 'bmName',
        label: 'BM 名称',
        required: true,
      },
      {
        excelHeader: '*创建BMID',
        key: 'bmId',
        label: '创建BMID',
        required: true,
      },
      {
        excelHeader: '*像素名称',
        key: 'pixelName',
        label: '像素名称',
        required: true,
      },
      {
        excelHeader: '*像素ID',
        key: 'pixelId',
        label: '像素 ID',
        required: true,
      },
      {
        key: 'accessToken',
        label: 'Access Token',
        type: 'password',
      },
      { key: 'pixelTestCode', label: '像素测试代码' },
    ],
    identifierKey: 'pixelId',
    importContextHeaders: ['所属项目', '使用团队'],
    label: '像素',
    nameKey: 'pixelName',
    presentationKeys: [
      'detail.bmName',
      'detail.bmId',
      'projectName',
      'detail.pixelName',
      'detail.pixelId',
      'detail.accessToken',
      'detail.pixelTestCode',
      'usageTeam',
      'remark',
    ],
    requiresChannel: false,
    subtype: 'pixel',
  },
  {
    aliases: ['telegram', 'tg', 'tg号', 'tg 号'],
    assetType: 'TG',
    category: 'personal',
    excelSheetName: 'TG号',
    fields: [
      {
        excelHeader: '*电话号码',
        key: 'phoneNumber',
        label: '电话号码',
        required: true,
      },
      {
        excelHeader: '*TG 链接',
        key: 'link',
        label: 'TG 链接',
        placeholder: 'https://t.me/...',
        required: true,
        type: 'url',
      },
    ],
    identifierKey: 'phoneNumber',
    label: 'TG号',
    nameKey: 'phoneNumber',
    requiresChannel: false,
    subtype: 'telegram',
  },
  {
    aliases: ['wechat', '微信', '微信号'],
    assetType: 'PERSONAL',
    category: 'personal',
    excelSheetName: '微信号',
    fields: [
      {
        excelHeader: '*微信号',
        key: 'wechatId',
        label: '微信号',
        required: true,
      },
      { key: 'displayName', label: '微信昵称' },
      { key: 'phoneNumber', label: '绑定手机号' },
    ],
    identifierKey: 'wechatId',
    label: '微信号',
    nameKey: 'displayName',
    requiresChannel: false,
    subtype: 'wechat',
    usageUserHeader: '使用人',
  },
  {
    aliases: ['page', '主页'],
    assetType: 'PAGE',
    category: 'advertising',
    excelSheetName: '主页',
    fields: [
      {
        excelHeader: '主页 ID',
        key: 'pageId',
        label: '主页 ID',
      },
      {
        excelHeader: '*主页名称',
        key: 'pageName',
        label: '主页名称',
        required: true,
      },
    ],
    identifierKey: 'pageName',
    label: '主页',
    nameKey: 'pageName',
    requiresChannel: false,
    subtype: 'page',
    usageUserHeader: '使用人',
  },
  {
    aliases: ['computer', '电脑'],
    assetType: 'COMPUTER',
    category: 'network',
    excelSheetName: '电脑',
    fields: [
      {
        excelHeader: '*资产编号',
        key: 'assetCode',
        label: '资产编号',
        required: true,
      },
      { key: 'deviceName', label: '电脑名称' },
      { key: 'brand', label: '品牌' },
      { key: 'model', label: '型号' },
      { key: 'serialNumber', label: '序列号' },
      { key: 'operatingSystem', label: '操作系统' },
      { key: 'purchaseDate', label: '购买日期', type: 'date' },
      { key: 'storageLocation', label: '存放位置' },
    ],
    identifierKey: 'assetCode',
    label: '电脑',
    nameKey: 'deviceName',
    requiresChannel: false,
    subtype: 'computer',
    usageUserHeader: '使用人',
  },
  {
    aliases: ['mobile', '手机'],
    assetType: 'MOBILE',
    category: 'network',
    excelSheetName: '手机',
    fields: [
      {
        excelHeader: '*IMEI / 序列号',
        key: 'deviceCode',
        label: 'IMEI / 序列号',
        required: true,
      },
      { key: 'deviceName', label: '手机名称' },
      { key: 'brand', label: '品牌' },
      { key: 'model', label: '型号' },
      { key: 'phoneNumber', label: '手机号' },
      { key: 'operatingSystem', label: '操作系统' },
      { key: 'purchaseDate', label: '购买日期', type: 'date' },
    ],
    identifierKey: 'deviceCode',
    label: '手机',
    nameKey: 'deviceName',
    requiresChannel: false,
    subtype: 'mobile',
    usageUserHeader: '使用人',
  },
  {
    aliases: ['static ip', 'static-ip', 'static_ip', '静态 ip', '静态ip'],
    assetType: 'STATIC_IP',
    category: 'network',
    excelSheetName: '静态 IP',
    fields: [
      { key: 'assetName', label: 'IP名称' },
      {
        excelHeader: '*IP 地址',
        key: 'ipAddress',
        label: 'IP 地址',
        required: true,
      },
      { key: 'ipCountry', label: 'IP 国家' },
    ],
    identifierKey: 'ipAddress',
    label: '静态 IP',
    nameKey: 'assetName',
    requiresChannel: false,
    subtype: 'static_ip',
    usageUserHeader: '使用人',
  },
  {
    aliases: ['email', '邮箱'],
    assetType: 'EMAIL',
    category: 'network',
    excelSheetName: '邮箱',
    fields: [
      { key: 'displayName', label: '邮箱名称' },
      {
        excelHeader: '*邮箱账号',
        key: 'email',
        label: '邮箱账号',
        required: true,
      },
      {
        excelHeader: '*邮箱密码',
        key: 'password',
        label: '邮箱密码',
        required: true,
        type: 'password',
      },
      { key: 'twoFa', label: '2FA 密钥', type: 'password' },
      {
        key: 'emailLoginUrl',
        label: '邮箱登录网址',
        placeholder: 'https://mail.example.com',
        type: 'url',
      },
    ],
    identifierKey: 'email',
    label: '邮箱',
    nameKey: 'displayName',
    requiresChannel: false,
    subtype: 'email',
    usageUserHeader: '使用人',
  },
];

const assetTypesByAlias = new Map<string, InventoryAssetTypeMeta>();
for (const assetType of INVENTORY_ASSET_TYPES) {
  for (const alias of assetType.aliases) {
    assetTypesByAlias.set(alias.toLowerCase(), assetType);
  }
}

export function findInventoryAssetTypeByAssetType(assetType: MediaAssetType) {
  return INVENTORY_ASSET_TYPES.find((item) => item.assetType === assetType);
}

export function findInventoryAssetTypeBySubtype(subtype: string) {
  return INVENTORY_ASSET_TYPES.find((item) => item.subtype === subtype);
}

/**
 * 返回与 Excel 9.3 模板完全一致的字段顺序，供模板下载、导入和列表共用。
 */
export function getInventoryAssetTemplateFields(
  assetType: InventoryAssetTypeMeta,
) {
  if (!assetType.excelFieldKeys?.length) return assetType.fields;

  const fieldsByKey = new Map(
    assetType.fields.map((field) => [field.key, field]),
  );
  return assetType.excelFieldKeys
    .map((key) => fieldsByKey.get(key))
    .filter((field): field is InventoryAssetField => Boolean(field));
}

/**
 * 返回资产的业务信息顺序；未单独配置的类型沿用明细字段顺序。
 */
export function getInventoryAssetPresentationKeys(
  assetType: InventoryAssetTypeMeta,
) {
  return (
    assetType.presentationKeys ??
    assetType.fields.map((field) => `detail.${field.key}` as const)
  );
}

/**
 * 返回编辑抽屉对应的业务字段顺序，供批量编辑和 Excel 编辑器共用。
 *
 * @remarks 资产分类和资产类型由当前页面上下文固定，不属于单个资产的批量编辑字段。
 */
export function getInventoryAssetEditorFieldKeys(
  assetType: InventoryAssetTypeMeta,
): InventoryAssetEditorFieldKey[] {
  if (assetType.assetType === 'PIXEL') {
    return getInventoryAssetPresentationKeys(assetType).map((key) => {
      if (key === 'projectName') return 'project';
      return key;
    });
  }

  return [
    ...(assetType.requiresChannel ? (['channel'] as const) : []),
    ...assetType.fields.map((field) => `detail.${field.key}` as const),
    'inventoryStatus',
    'usageUsers',
    'remark',
  ];
}

export function resolveInventoryAssetType(alias: string) {
  return assetTypesByAlias.get(alias.trim().toLowerCase());
}

const INVENTORY_ASSET_TYPE_LABELS: Record<MediaAssetType, string> = {
  AD_ACCOUNT: '广告账户',
  BM: 'BM',
  COMPUTER: '电脑',
  EMAIL: '邮箱',
  MOBILE: '手机',
  PAGE: '主页',
  PERSONAL: '个号',
  PIXEL: '像素',
  STATIC_IP: '静态 IP',
  TG: 'TG',
};

/**
 * 解析库存资产的业务子类型，并在列表中显示比后端主类型更准确的名称。
 *
 * @remarks
 * 微信号与 FB 账号共用 PERSONAL 主类型，必须读取持久化的
 * inventorySubtype 才能避免在分配和回收记录中把微信号误标为“FB”。
 */
export function resolveInventoryAssetTypeLabel(
  assetType: string,
  secretData?: string,
) {
  if (secretData) {
    try {
      const details: unknown = JSON.parse(secretData);
      if (details && typeof details === 'object' && !Array.isArray(details)) {
        const subtype = Reflect.get(details, 'inventorySubtype');
        if (typeof subtype === 'string') {
          const subtypeMeta = findInventoryAssetTypeBySubtype(subtype);
          const sharedMainType =
            INVENTORY_ASSET_TYPES.filter((item) => item.assetType === assetType)
              .length > 1;
          if (sharedMainType && subtypeMeta?.assetType === assetType) {
            return subtypeMeta.label;
          }
        }
      }
    } catch {
      // 历史资产可能没有结构化详情，继续使用主类型名称回显。
    }
  }

  return INVENTORY_ASSET_TYPE_LABELS[assetType as MediaAssetType] ?? assetType;
}
