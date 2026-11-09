import type { MediaAssetType } from './asset-flow';
import type { SystemPageResult } from './system/types';

import { backendClient } from '#/api/request';

/** 回收单状态：待处理或已完成。 */
export type AssetReturnStatus = 'COMPLETED' | 'PENDING';

/** 回收结果：重新入库或停用。 */
export type AssetReturnOutcome = 'AVAILABLE' | 'DISABLED';

export interface AssetReturnRecord {
  applicationId?: string;
  assetCode: string;
  assetId: string;
  assetName: string;
  assetType: string;
  assigneeId?: string;
  assigneeName?: string;
  channelId?: string;
  channelName?: string;
  completedAt?: string;
  completedById?: string;
  completedByName?: string;
  createdAt: string;
  id: string;
  outcome?: AssetReturnOutcome;
  projectId?: string;
  projectName?: string;
  reason: string;
  requestedById: string;
  requestedByName: string;
  returnNo: string;
  status: AssetReturnStatus;
  updatedAt: string;
}

export interface AssetReturnSummary {
  completed: number;
  pending: number;
  total: number;
}

export interface AssetReturnPageParams {
  assetSubtype?: string;
  assetType?: MediaAssetType;
  keyword?: string;
  page: number;
  pageSize: number;
  status?: AssetReturnStatus;
}

/** 媒介资产回收的真实后端接口。 */
export const assetReturnApi = {
  complete: (id: string, outcome: AssetReturnOutcome) =>
    backendClient.post<AssetReturnRecord>(
      `/asset-returns/${id}/complete`,
      { outcome },
      { skipErrorMessage: true },
    ),
  create: (assetId: string, reason: string) =>
    backendClient.post<AssetReturnRecord>(
      `/asset-returns/assets/${assetId}`,
      { reason },
      { skipErrorMessage: true },
    ),
  page: (params: AssetReturnPageParams) =>
    backendClient.get<SystemPageResult<AssetReturnRecord>>('/asset-returns', {
      params,
      skipErrorMessage: true,
    }),
  summary: () =>
    backendClient.get<AssetReturnSummary>('/asset-returns/summary', {
      skipErrorMessage: true,
    }),
};
