import { adpulseClient } from '#/api/request';

/** Facebook 资源选择项，供创建广告时解析和选择账户使用。 */
export interface FbAssetRef {
  id: string;
  name: string;
}

// 通用分页查询参数
export interface BaseQueryParams {
  id?: string | string[];
  name?: string;
  page: number;
  page_size: number;
  status?: string;
}

export interface AdAccountQueryParams extends BaseQueryParams {
  sort_by?: string;
  sort_order?: string;
}

// BM 查询参数
export interface BusinessQueryParams extends BaseQueryParams {
  personal_id?: string;
}

// 分页响应数据结构
export interface PaginatedResponse<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdAccountPaginatedResponse<T> extends PaginatedResponse<T> {
  matched_ids: string[];
  missing_ids: string[];
}

// 个号数据结构
export interface PersonalAccount {
  [key: string]: any;
  _id: string;
  accounts?: any[];
  app_id?: string;
  business?: any[];
  name?: string;
  pages?: any[];
  updated_at?: string;
}

// 系统开发者数据结构
export interface SystemAccount {
  [key: string]: any;
  _id: string;
  accounts?: any[];
  app_id?: string;
  pages?: any[];
  status?: number;
  update_time?: string;
}

// 系统开发者查询参数（无 name 字段）
export interface SystemAccountQueryParams {
  id?: string;
  page: number;
  page_size: number;
  status?: boolean;
}

// 广告账户数据结构
export interface AdAccount {
  [key: string]: any;
  _id: string;
  account_status?: number;
  age?: number;
  amount_spent?: string;
  balance?: string;
  created_time?: string;
  currency?: string;
  disable_reason?: number;
  is_prepay_account?: boolean;
  name?: string;
  owner?: string;
  pixels?: any[];
  spend_cap?: string;
  tax_id_status?: number;
  timezone_name?: string;
  updated_at?: string;
}

// BM 数据结构
export interface Business {
  [key: string]: any;
  _id: string;
  accounts?: any[];
  business_id?: string;
  business_name?: string;
  facebook_id?: string;
  pages?: any[];
  pixels?: any[];
  updated_at?: string;
}

// 主页数据结构
export interface FbPage {
  [key: string]: any;
  _id: string;
  can_post?: boolean;
  category?: string;
  fan_count?: number;
  followers_count?: number;
  is_published?: boolean;
  is_unclaimed?: boolean;
  link?: string;
  name?: string;
  new_like_count?: number;
  talking_about_count?: number;
  updated_at?: string;
  username?: string;
  verification_status?: string;
}

// 像素数据结构
export interface FbPixel {
  [key: string]: any;
  _id: string;
  creation_time?: string;
  data_use_setting?: string;
  is_unavailable?: boolean;
  last_fired_time?: string;
  name?: string;
  owner_business?: string;
  updated_at?: string;
}

// 查询个号列表
export const getPersonalAccounts = (params: BaseQueryParams) => {
  return adpulseClient.get<PaginatedResponse<PersonalAccount>>(
    '/fb_resource/personal_accounts',
    { params },
  );
};

// 查询系统开发者列表
export const getSystemAccounts = (params: SystemAccountQueryParams) => {
  return adpulseClient.get<PaginatedResponse<SystemAccount>>(
    '/fb_resource/system_accounts',
    { params },
  );
};

// 查询广告账户列表
export const getAdAccounts = (params: AdAccountQueryParams) => {
  return adpulseClient.get<AdAccountPaginatedResponse<AdAccount>>(
    '/fb_resource/ad_accounts',
    {
      params,
      paramsSerializer: (p: any) => {
        const parts: string[] = [];
        for (const [key, val] of Object.entries(p)) {
          if (val === undefined || val === null || val === '') continue;
          if (Array.isArray(val)) {
            (val as any[]).forEach((item) =>
              parts.push(`${key}=${encodeURIComponent(String(item))}`),
            );
          } else {
            parts.push(`${key}=${encodeURIComponent(String(val))}`);
          }
        }
        return parts.join('&');
      },
    },
  );
};

// 查询 BM 列表
export const getBusinesses = (params: BusinessQueryParams) => {
  return adpulseClient.get<PaginatedResponse<Business>>(
    '/fb_resource/businesss',
    { params },
  );
};

// 查询主页列表
export const getPages = (params: BaseQueryParams) => {
  return adpulseClient.get<PaginatedResponse<FbPage>>('/fb_resource/pages', {
    params,
  });
};

// 查询像素列表
export const getPixels = (
  params: BaseQueryParams & { personal_only?: boolean },
) => {
  return adpulseClient.get<PaginatedResponse<FbPixel>>('/fb_resource/pixels', {
    params,
  });
};

export interface SyncTargetAccount {
  account_id: string;
  pixel_ids?: string[]; // 缺省只拉户本身;指定则合并进该户像素列表
}

// 定向同步目标,非空时只拉指定资产,不做全量同步
export interface SyncTargets {
  accounts?: SyncTargetAccount[];
  page_ids?: string[];
}

// 手动同步个号/系统资产
export const syncPersonalAccount = (
  personal_id: string,
  personal_type: 'personal' | 'system' = 'personal',
  targets?: SyncTargets,
) => {
  return adpulseClient.post<string>('/fb_resource/sync/push', {
    personal_id,
    personal_type,
    targets,
  });
};

export interface SyncProgressData {
  [personal_id: string]: {
    total: number;
    processed: number;
  };
}

export const getSyncProgress = (personal_ids: string[]) => {
  return adpulseClient.post<SyncProgressData>('/fb_resource/sync/progress', {
    personal_ids,
  });
};

// 可用广告账户
export interface AvailableAdAccount {
  id: string;
  name: string;
}

export interface AvailablePersonalGroup {
  ad_accounts: AvailableAdAccount[];
  personal_id: string;
  personal_name: string;
}

export const getAvailableAdAccounts = () => {
  return adpulseClient.get<{ items: AvailablePersonalGroup[]; total: number }>(
    '/fb_resource/ad_accounts/available',
  );
};

export interface FbPost {
  name: string;
  page_id: string;
  post_id: string;
  unique_name: string;
  thumbnail: string;
}

export const getPosts = (params: {
  id?: string[];
  name?: null | string;
  page: number;
  page_size: number;
  status?: boolean | null;
}) => {
  return adpulseClient.get<PaginatedResponse<FbPost>>('/fb_resource/posts', {
    params,
    paramsSerializer: (p: any) => {
      const parts: string[] = [];
      for (const [key, val] of Object.entries(p)) {
        if (val === undefined || val === null) continue;
        if (Array.isArray(val)) {
          (val as any[]).forEach((v) =>
            parts.push(`${key}=${encodeURIComponent(v)}`),
          );
        } else {
          parts.push(`${key}=${encodeURIComponent(String(val))}`);
        }
      }
      return parts.join('&');
    },
  });
};
