// @ts-nocheck -- 仓库当前未向 plat 的生产类型检查暴露 Vitest 类型。
import { describe, expect, it } from 'vitest';

import {
  AD_ACCOUNT_EDITOR_FIELDS,
  findInventoryAssetTypeBySubtype,
  getInventoryAssetEditorFieldKeys,
} from './asset-types';

const expectedAdAccountEditorFields = [
  'accountId',
  'accountName',
  'accountDailyLimit',
  'accountType',
  'accountAttribute',
  'channelId',
  'managedBm',
  'managedBmId',
  'backupManagedBm',
  'backupManagedBmId',
  'timezone',
  'cardStation',
  'cardNumber',
  'inventoryStatus',
  'userIds',
  'remark',
];

const expectedEditorFields = {
  bm: [
    'channel',
    'detail.date',
    'detail.usagePurpose',
    'detail.bmName',
    'detail.bmId',
    'detail.bmLink',
    'detail.operatorFbAccount',
    'detail.assignedDate',
    'detail.supplierRemoved',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
  computer: [
    'detail.assetCode',
    'detail.deviceName',
    'detail.brand',
    'detail.model',
    'detail.serialNumber',
    'detail.operatingSystem',
    'detail.purchaseDate',
    'detail.storageLocation',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
  email: [
    'detail.displayName',
    'detail.email',
    'detail.password',
    'detail.twoFa',
    'detail.emailLoginUrl',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
  fb: [
    'detail.createDate',
    'detail.accountName',
    'detail.email',
    'detail.password',
    'detail.twoFa',
    'detail.phoneNumber',
    'detail.birthday',
    'detail.gender',
    'detail.assignmentDate',
    'detail.cookie',
    'detail.emailLoginUrl',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
  mobile: [
    'detail.deviceCode',
    'detail.deviceName',
    'detail.brand',
    'detail.model',
    'detail.phoneNumber',
    'detail.operatingSystem',
    'detail.purchaseDate',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
  page: [
    'detail.pageId',
    'detail.pageName',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
  pixel: [
    'detail.bmName',
    'detail.bmId',
    'project',
    'detail.pixelName',
    'detail.pixelId',
    'detail.accessToken',
    'detail.pixelTestCode',
    'usageTeam',
    'remark',
  ],
  static_ip: [
    'detail.assetName',
    'detail.ipAddress',
    'detail.ipCountry',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
  telegram: [
    'detail.phoneNumber',
    'detail.link',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
  wechat: [
    'detail.wechatId',
    'detail.displayName',
    'detail.phoneNumber',
    'inventoryStatus',
    'usageUsers',
    'remark',
  ],
};

describe('inventory asset editor fields', () => {
  it('keeps advertising-account spreadsheet fields aligned with its editor drawer', () => {
    expect(AD_ACCOUNT_EDITOR_FIELDS.map((field) => field.key)).toEqual(
      expectedAdAccountEditorFields,
    );
  });

  it.each(Object.entries(expectedEditorFields))(
    'keeps %s spreadsheet fields aligned with its editor drawer',
    (subtype, expectedFields) => {
      const assetType = findInventoryAssetTypeBySubtype(subtype);

      expect(assetType).toBeDefined();
      expect(getInventoryAssetEditorFieldKeys(assetType!)).toEqual(
        expectedFields,
      );
    },
  );
});
