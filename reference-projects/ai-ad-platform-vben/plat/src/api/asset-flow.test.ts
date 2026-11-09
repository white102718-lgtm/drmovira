import { beforeEach, describe, expect, it, vi } from 'vitest';

import { backendClient } from '#/api/request';

import { assetFlowApi } from './asset-flow';

vi.mock('#/api/request', () => ({
  backendClient: { get: vi.fn(), post: vi.fn() },
}));

describe('asset flow approval API', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads only server-authorized colleagues for an approval transfer', async () => {
    await assetFlowApi.transferCandidates('9007199254740993');

    expect(backendClient.get).toHaveBeenCalledWith(
      '/asset-flow-v2/approvals/9007199254740993/transfer-candidates',
    );
  });

  it('submits a stable recipient id and audit reason to transfer an approval', async () => {
    await assetFlowApi.transfer('42', {
      recipientId: 'user-media-peer',
      remark: '下午外出，请协助办理。',
    });

    expect(backendClient.post).toHaveBeenCalledWith(
      '/asset-flow-v2/approvals/42/transfer',
      {
        recipientId: 'user-media-peer',
        remark: '下午外出，请协助办理。',
      },
    );
  });

  it('sends one atomic batch decision request', async () => {
    const payload = {
      action: 'APPROVE' as const,
      ids: ['31', '32'],
      remark: '库存核对无误',
    };

    await assetFlowApi.batchDecide(payload);

    expect(backendClient.post).toHaveBeenCalledWith(
      '/asset-flow-v2/approvals/batch-decide',
      payload,
    );
  });

  it('exports selected approval ids as an xlsx blob', async () => {
    const payload = { ids: ['31', '9007199254740993'] };

    await assetFlowApi.exportApprovals(payload);

    expect(backendClient.post).toHaveBeenCalledWith(
      '/asset-flow-v2/approvals/export',
      payload,
      { responseReturn: 'body', responseType: 'blob' },
    );
  });

  it('loads all matching assets for export with one filtered request', async () => {
    const filters = {
      assetType: 'PIXEL' as const,
      filterControls: { status: 'select' as const },
      filterValues: { status: ['allocated'] },
      keyword: '品牌',
      mine: false,
      subtype: 'pixel',
    };

    await assetFlowApi.searchAllAssets(filters);

    expect(backendClient.post).toHaveBeenCalledWith(
      '/asset-flow/assets/search-all',
      filters,
    );
  });
});
