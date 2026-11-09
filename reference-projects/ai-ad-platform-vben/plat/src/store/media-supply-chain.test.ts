import { nextTick } from 'vue';

import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  MEDIA_SUPPLY_CHAIN_STORAGE_KEY,
  useMediaSupplyChainStore,
} from './media-supply-chain';

describe('media supply chain store', () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it('seeds customers into an isolated versioned storage envelope', () => {
    const store = useMediaSupplyChainStore();

    expect(store.customers).toHaveLength(10);
    expect(
      JSON.parse(localStorage.getItem(MEDIA_SUPPLY_CHAIN_STORAGE_KEY) ?? '{}'),
    ).toMatchObject({ schemaVersion: 1 });
    expect(
      localStorage.getItem('fusion:media-resource:channels:v1'),
    ).toBeNull();
  });

  it('creates, updates, and removes a customer without affecting channel data', async () => {
    const store = useMediaSupplyChainStore();
    const customer = store.create({
      cooperationMode: 'prepaid',
      createWallet: true,
      endDate: '',
      name: '  新增测试客户群  ',
      note: '新增备注',
      policy: '2+1',
      sheetUrl: 'https://docs.example.com/test',
      startDate: '2026-08-28',
      status: 'not_started',
      walletAddress: '',
    });

    expect(customer).toMatchObject({
      createWallet: true,
      name: '新增测试客户群',
    });
    expect(customer.walletAddress).toMatch(/^0x[a-f\d]{40}$/i);
    expect(() => store.create({ ...customer, name: '新增测试客户群' })).toThrow(
      '客户群名已存在',
    );

    const updated = store.update(customer.id, {
      ...customer,
      endDate: '2026-12-31',
      name: '已更新客户群',
      status: 'active',
    });
    expect(updated).toMatchObject({
      endDate: '2026-12-31',
      name: '已更新客户群',
      status: 'active',
    });
    expect(store.remove(customer.id)).toBe(true);

    await nextTick();
    expect(
      localStorage.getItem('fusion:media-resource:channels:v1'),
    ).toBeNull();
  });
});
