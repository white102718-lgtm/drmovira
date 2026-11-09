import { backendClient } from '#/api/request';

export namespace SystemIpRuleApi {
  export interface Rule {
    createdAt: string;
    id: string;
    ipCidr: string;
    remark?: null | string;
    ruleName?: null | string;
    scopeType: number;
    status: 0 | 1;
    updatedAt: string;
    userId?: null | string;
  }

  export interface SaveRequest {
    ipCidr: string;
    remark?: string;
    ruleName?: string;
    status: 0 | 1;
  }
}

function getGlobalIpRules() {
  return backendClient.get<SystemIpRuleApi.Rule[]>('/ip-rules/global');
}

function createGlobalIpRule(data: SystemIpRuleApi.SaveRequest) {
  return backendClient.post<SystemIpRuleApi.Rule>('/ip-rules/global', data);
}

function updateGlobalIpRule(id: string, data: SystemIpRuleApi.SaveRequest) {
  return backendClient.put<SystemIpRuleApi.Rule>(
    `/ip-rules/global/${id}`,
    data,
  );
}

function deleteGlobalIpRule(id: string) {
  return backendClient.delete(`/ip-rules/global/${id}`);
}

export {
  createGlobalIpRule,
  deleteGlobalIpRule,
  getGlobalIpRules,
  updateGlobalIpRule,
};
