/** 服务商返回的推广域名下拉选项。 */
export interface CloakDomainOption {
  genDomain: string;
  genId: string;
  label: string;
  value: string;
}

/** 服务商返回的投放地区下拉选项。 */
export interface CloakCountryOption {
  country: string;
  label: string;
  value: string;
}

export type CloakMode = 'all' | 'cloak' | 'off';

/** 批量创建中的单条代理线配置。 */
export interface CloakBatchItemInput {
  adUrl: string;
  agencyLineId: string;
  genDomain: string;
  genId: string;
}

/** 本系统批量创建请求，服务商字段转换由后端完成。 */
export interface CloakBatchCreateInput {
  blockedLanguage: boolean;
  blockedPc: boolean;
  blockedProxy: boolean;
  country?: string;
  countryLabel?: string;
  items: CloakBatchItemInput[];
  mode: CloakMode;
  projectId: string;
  requestId: string;
  reviewUrl: string;
}

export interface CloakBatchResult {
  batchId: string;
  reused: boolean;
  totalCount: number;
}

export interface CloakSheetWritebackFailure {
  agencyLineName: string;
  message: string;
  recordId: string;
}

export interface CloakSheetWritebackResult {
  batchId: string;
  failedCount: number;
  failures: CloakSheetWritebackFailure[];
  successCount: number;
  totalCount: number;
}

export interface CloakRecordSheetWritebackResult {
  failedCount: number;
  failures: CloakSheetWritebackFailure[];
  successCount: number;
  totalCount: number;
}

export interface CloakRecord {
  agencyLineId: string;
  agencyLineName: string;
  blockedLanguage: boolean;
  blockedPc: boolean;
  blockedProxy: boolean;
  country?: string;
  countryLabel?: string;
  createdAt: string;
  id: string;
  mode: CloakMode;
  projectId: string;
  projectName: string;
  promotionUrl: string;
  reviewUrl: string;
  sheetWritebackMessage?: null | string;
  sheetWritebackStatus: 'failed' | 'pending' | 'success';
  sourceUrl: string;
}

export interface CloakRecordQuery {
  country?: string;
  endDate?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  projectId?: string;
  startDate?: string;
}

export interface CloakRecordPage {
  items: CloakRecord[];
  page: number;
  pageSize: number;
  total: number;
}
