import type { SystemPageResult } from './types';

import { backendClient } from '#/api/request';

export namespace SystemOperationLogApi {
  export interface OperationLog {
    clientIp: string;
    failureCode?: null | number;
    failureReason?: null | string;
    id: string;
    moduleCode: 'DEPARTMENT' | 'IP_RULE' | 'MENU' | 'ROLE' | 'USER' | string;
    operatedAt: string;
    operationName: string;
    operationResult: 0 | 1;
    operationType: string;
    operatorDisplayName?: null | string;
    operatorUserId?: null | string;
    requestMethod: string;
    requestPath: string;
    targetId?: null | string;
    targetType: string;
    userAgent?: null | string;
  }

  export interface PageParams {
    clientIp?: string;
    endedAt?: string;
    keyword?: string;
    moduleCode?: string;
    operationResult?: 0 | 1;
    operationType?: string;
    page?: number;
    pageSize?: number;
    startedAt?: string;
  }
}

function getOperationLogList(params: SystemOperationLogApi.PageParams) {
  return backendClient.get<
    SystemPageResult<SystemOperationLogApi.OperationLog>
  >('/operation-logs', { params });
}

export { getOperationLogList };
