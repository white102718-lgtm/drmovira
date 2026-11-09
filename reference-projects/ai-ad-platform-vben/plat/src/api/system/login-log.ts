import type { SystemPageResult } from './types';

import { backendClient } from '#/api/request';

export namespace SystemLoginLogApi {
  export interface LoginLog {
    authStage: 1 | 2 | 3 | 4;
    clientIp: string;
    displayName?: null | string;
    failureCode?: null | number;
    failureReason?: null | string;
    id: string;
    loginAt: string;
    loginIdentifier?: null | string;
    loginResult: 0 | 1;
    userAgent?: null | string;
    userId?: null | string;
    username?: null | string;
  }

  export interface PageParams {
    authStage?: 1 | 2 | 3 | 4;
    clientIp?: string;
    endedAt?: string;
    keyword?: string;
    loginResult?: 0 | 1;
    page?: number;
    pageSize?: number;
    startedAt?: string;
  }
}

function getLoginLogList(params: SystemLoginLogApi.PageParams) {
  return backendClient.get<SystemPageResult<SystemLoginLogApi.LoginLog>>(
    '/login-logs',
    { params },
  );
}

export { getLoginLogList };
