import type { AdAccountSelectionAdapter } from '../adapter';
import type { AdAccountSelectionQuery, SelectableAdAccount } from '../types';

import { backendClient } from '#/api/request';

export const SELECTABLE_AD_ACCOUNT_ENDPOINT = '/fusion/ad-accounts/selectable';

export type SelectableAdAccountRequestParams = Pick<
  AdAccountSelectionQuery,
  | 'accountIds'
  | 'accountNames'
  | 'agencyLineId'
  | 'keyword'
  | 'pixelName'
  | 'platform'
  | 'projectId'
  | 'userId'
>;

export type SelectableAdAccountFetcher = (
  endpoint: string,
  params: SelectableAdAccountRequestParams,
) => Promise<SelectableAdAccount[] | { items: SelectableAdAccount[] }>;

export interface HttpAdAccountSelectionAdapterOptions {
  fetcher?: SelectableAdAccountFetcher;
}

export class HttpAdAccountSelectionAdapter
  implements AdAccountSelectionAdapter
{
  private readonly fetcher: SelectableAdAccountFetcher;

  constructor(options: HttpAdAccountSelectionAdapterOptions = {}) {
    this.fetcher =
      options.fetcher ??
      ((endpoint, params) =>
        backendClient.get<
          SelectableAdAccount[] | { items: SelectableAdAccount[] }
        >(endpoint, { params }));
  }

  async listCandidates(
    query?: AdAccountSelectionQuery,
  ): Promise<SelectableAdAccount[]> {
    if (!query?.projectId || !query.platform || !query.agencyLineId) {
      throw new Error('正式账户查询必须提供项目、平台和代理线稳定 ID');
    }
    const params: SelectableAdAccountRequestParams = {
      accountIds: query.accountIds,
      accountNames: query.accountNames,
      agencyLineId: query.agencyLineId,
      keyword: query.keyword,
      pixelName: query.pixelName,
      platform: query.platform,
      projectId: query.projectId,
      userId: query.userId,
    };
    const response = await this.fetcher(SELECTABLE_AD_ACCOUNT_ENDPOINT, params);
    return Array.isArray(response) ? response : response.items;
  }
}
