// @ts-nocheck -- 仓库当前未向 plat 的生产类型检查暴露 Vitest 类型。
import { describe, expect, it } from 'vitest';

import {
  filterMyAdAccountAssets,
  mapMyAdAccountAssets,
  paginateMyAdAccountAssets,
} from './my-ad-account-assets';

describe('my ad account assets', () => {
  const accounts = [
    {
      accountId: '9452456651525146',
      accountName: '已开户账户',
      accountType: '企业户',
      accountAttribute: '稳定户',
      backupManagedBm: '',
      backupManagedBmId: '',
      cardNumber: '',
      cardStation: '',
      channelName: 'MP045-FB',
      managedBm: '',
      managedBmId: '',
      timezone: 'Asia/Shanghai',
      usageUserName: '申请人、共享人',
      inventoryStatus: 'ASSIGNED' as const,
      assignments: [
        {
          applicationId: '88',
          assignedAt: '2026-09-15T12:07:11',
          id: '1',
          primary: true,
          source: 'APPLICATION',
          status: 'ACTIVE',
          userId: '7',
          userName: '申请人',
        },
        {
          applicationId: '99',
          assignedAt: '2026-09-15T13:00:00',
          id: '2',
          primary: false,
          source: 'APPLICATION',
          status: 'ACTIVE',
          userId: '9',
          userName: '共享人',
        },
      ],
    },
  ];

  it('uses the current user assignment without dropping shared users', () => {
    const [record] = mapMyAdAccountAssets(accounts, '7');

    expect(record).toMatchObject({
      applicationId: '88',
      createdAt: '2026-09-15T12:07:11',
      identifier: '9452456651525146',
      name: '已开户账户',
      owner: '申请人、共享人',
      status: 'allocated',
    });
  });

  it('keeps empty exportable values blank instead of injecting display placeholders', () => {
    const [record] = mapMyAdAccountAssets(
      [
        {
          accountId: '10001',
          accountName: '   ',
          inventoryStatus: 'AVAILABLE',
          usageUserName: '   ',
        },
      ],
      '7',
    );

    expect(record).toMatchObject({
      details: { accountId: '10001', accountName: '' },
      owner: '',
    });
  });

  it('filters and paginates the main ledger result', () => {
    const records = mapMyAdAccountAssets(accounts, '7');
    const matched = filterMyAdAccountAssets(
      records,
      '9452456651525146',
      { accountType: ['个人户', '企业户'] },
      { accountType: 'select' },
    );

    expect(paginateMyAdAccountAssets(matched, 1, 10)).toHaveLength(1);
    expect(
      filterMyAdAccountAssets(
        records,
        '',
        {
          accountType: ['个人户', '企业户'],
          channelName: ['OTHER-CHANNEL'],
        },
        { accountType: 'select', channelName: 'select' },
      ),
    ).toHaveLength(0);
    expect(filterMyAdAccountAssets(records, '不存在', {}, {})).toHaveLength(0);
  });
});
