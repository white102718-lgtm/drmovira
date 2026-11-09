export type AdDashboardCategory =
  | 'account'
  | 'ad'
  | 'adSet'
  | 'agencyLine'
  | 'campaign'
  | 'channel'
  | 'department'
  | 'pixel'
  | 'platform'
  | 'project';

export type AdDashboardDataType =
  | 'currency'
  | 'datetime'
  | 'identifier'
  | 'number'
  | 'percent'
  | 'status'
  | 'text'
  | 'url';

export interface AdDashboardField {
  dataType: AdDashboardDataType;
  emptyText: string;
  filterable: boolean;
  fixed?: 'left' | 'right';
  key: string;
  label: string;
  sortable: boolean;
  /** 旧接口使用的排序指标名，与页面字段 key、展示标题独立。 */
  sortKey?: string;
  sourceKey: string;
  summarizable: boolean;
  width: number;
}

export interface AdDashboardSchema {
  category: AdDashboardCategory;
  fields: AdDashboardField[];
  label: string;
  legacyTabKey: string;
  sheetName: string;
}

export type AdDashboardValue = null | number | string;

export interface AdDashboardRow {
  [key: string]: AdDashboardValue;
  currency: string;
  id: string;
  key: string;
}

export interface AdDashboardSummaryRow {
  currency: string;
  values: Record<string, number>;
}

export interface AdDashboardListQuery {
  category: AdDashboardCategory;
  endDate?: string;
  /** 当前维度的对象 ID；账户支持换行或逗号分隔，与名称、下钻条件取交集。 */
  id?: string;
  name?: string;
  page?: number;
  pageSize?: number;
  /** 仅代理线支持投手多选，值为 ERP english_nickname（Doris placer_id）。 */
  placerIds?: string[];
  /** 旧广告面板逐层下钻选中的业务对象 ID，接口层会转换为旧 Tab 参数名。 */
  selectedIds?: Partial<Record<AdDashboardCategory, string[]>>;
  sortField?: string;
  sortOrder?: 'asc' | 'desc';
  startDate?: string;
  /** 当前维度的真实状态码：账户使用数字字符串，其他对象使用 ACTIVE 等投放状态。 */
  status?: string;
}

export interface AdDashboardListResult {
  dataCutoff: string;
  items: AdDashboardRow[];
  page: number;
  pageSize: number;
  schema: AdDashboardSchema;
  summaryRows: AdDashboardSummaryRow[];
  total: number;
}
