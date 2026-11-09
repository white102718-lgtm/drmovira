import { adpulseClient } from '#/api/request';

export interface AccountUsage {
  insights_pull: boolean;
  facebook_login: boolean;
  sync_personal: boolean;
  sync_bm: boolean;
  sync_pixels: boolean;
}

// 开发者接口类型
export interface Developer {
  _id: string;
  ad_platform: string;
  agent_lines: string[];
  app_name: string;
  description?: string;
  placer_id: string;
  proxy?: string;
  status: number;
  department?: string[];

  // Facebook 字段
  access_token?: string;
  app_id?: string;
  app_secret?: string;
  dev_id?: string;
  account_usage?: AccountUsage;
  config_id?: string;

  // Google 字段
  customer_id?: string;
  developer_token?: string;
  login_customer_id?: string;
  service_account_json?: string;
}

export interface DeveloperListResult {
  items: Developer[];
  page: number;
  pageSize: number;
  total: number;
}

export const getDeveloperList = (
  currentPage: number,
  pageSize: number,
  dev_id?: string,
  ad_platform?: string,
  agent_lines?: string[],
  placer_id?: string,
  status?: number,
) => {
  const params: Record<string, any> = {
    limit: pageSize,
    skip: (currentPage - 1) * pageSize,
  };

  if (dev_id) params.dev_id = dev_id;
  if (ad_platform) params.ad_platform = ad_platform;
  if (agent_lines) params.agent_lines = agent_lines;
  if (placer_id) params.placer_id = placer_id;
  if (status !== undefined) params.status = status;

  return adpulseClient.get<DeveloperListResult>(
    `/developers/?${new URLSearchParams(params as Record<string, string>).toString()}`,
  );
};

export const getDeveloper = (id: string) => {
  return adpulseClient.get<Developer>(`/developers/${id}`);
};

export const createDeveloper = (data: Omit<Developer, '_id'>) => {
  return adpulseClient.post<{ _id: string; message: string }>(
    '/developers/',
    data,
  );
};

export const updateDeveloper = (
  id: string,
  data: Partial<Omit<Developer, '_id'>>,
) => {
  return adpulseClient.put<{ message: string }>(`/developers/${id}`, data);
};

export const deleteDeveloper = (id: string) => {
  return adpulseClient.delete<{ message: string }>(`/developers/${id}`);
};

export const restartConsumer = (id: string, date: string) => {
  return adpulseClient.post<{ message: string }>(
    '/developers/restart_consumer',
    { _id: id, date },
  );
};

export interface AdSyncHistoryParams {
  ad_platform?: string;
  agent_lines?: string[];
  day: string;
  dev_id?: string;
  hour?: number;
  page: number;
  page_size: number;
  run_status?: string;
}

export interface AdSyncHistoryResponse {
  items: any[];
  page: number;
  page_size: number;
  pages: number;
  total: number;
}

export const getAdSyncHistory = (params: AdSyncHistoryParams) => {
  return adpulseClient.get<AdSyncHistoryResponse>(
    '/developers/ad_sync_history',
    { params },
  );
};
