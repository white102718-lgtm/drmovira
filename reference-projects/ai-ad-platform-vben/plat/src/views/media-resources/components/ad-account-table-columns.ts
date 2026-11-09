import type { TableColumnsType } from 'ant-design-vue';

import type { AdAccountAsset } from '#/api';

/** 为资产管理与我的资产生成同一套广告账户台账数据列。 */
export function createAdAccountAssetDataColumns<
  Row extends AdAccountAsset,
>(): TableColumnsType<Row> {
  return [
    {
      dataIndex: 'accountId',
      className: 'ad-account-asset-table__identity-cell',
      fixed: 'left',
      key: 'accountId',
      title: '账户 ID',
      width: 165,
    },
    {
      dataIndex: 'accountName',
      fixed: 'left',
      key: 'accountName',
      title: '账户名称',
      width: 180,
    },
    {
      dataIndex: 'deliveryDate',
      fixed: 'left',
      key: 'deliveryDate',
      title: '下户日期',
      width: 128,
    },
    {
      dataIndex: 'channelName',
      fixed: 'left',
      key: 'channelName',
      title: '所属渠道',
      width: 160,
    },
    {
      dataIndex: 'accountType',
      fixed: 'left',
      key: 'accountType',
      title: '账户类型',
      width: 130,
    },
    {
      dataIndex: 'accountStatus',
      fixed: 'left',
      key: 'accountStatus',
      title: '平台状态',
      width: 110,
    },
    {
      dataIndex: 'inventoryStatus',
      key: 'inventoryStatus',
      title: '库存状态',
      width: 110,
    },
    {
      dataIndex: 'accountAttribute',
      key: 'accountAttribute',
      title: '账户属性',
      width: 130,
    },
    { dataIndex: 'managedBm', key: 'managedBm', title: '管理 BM', width: 180 },
    {
      dataIndex: 'managedBmId',
      key: 'managedBmId',
      title: '管理 BM ID',
      width: 165,
    },
    {
      dataIndex: 'backupManagedBm',
      key: 'backupManagedBm',
      title: '备份 BM',
      width: 180,
    },
    {
      dataIndex: 'backupManagedBmId',
      key: 'backupManagedBmId',
      title: '备份 BM ID',
      width: 165,
    },
    {
      className: 'ad-account-asset-table__identity-cell',
      dataIndex: 'timezone',
      key: 'timezone',
      title: '时区',
      width: 240,
    },
    { dataIndex: 'cardStation', key: 'cardStation', title: '卡台', width: 160 },
    { dataIndex: 'cardNumber', key: 'cardNumber', title: '卡号', width: 150 },
  ];
}
