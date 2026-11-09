import { beforeEach, describe, expect, it, vi } from 'vitest';

import { mainBackendClient } from '#/api/request';

import { searchAllAdAccountAssets } from './ad-account-assets';

vi.mock('#/api/request', () => ({
  mainBackendClient: { post: vi.fn() },
}));

describe('ad account asset API', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads all matching accounts with one filtered request', async () => {
    await searchAllAdAccountAssets({
      accountAttribute: ['企业户'],
      inventoryStatus: ['AVAILABLE'],
      keyword: 'BM',
    });

    expect(mainBackendClient.post).toHaveBeenCalledWith(
      '/asset-management/ad-accounts/search-all',
      {
        filter: {
          accountAttribute: ['企业户'],
          inventoryStatus: ['AVAILABLE'],
        },
        keyword: 'BM',
      },
    );
  });
});
