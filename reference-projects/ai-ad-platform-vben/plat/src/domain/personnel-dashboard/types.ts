export type PersonnelDashboardCategory =
  | 'account'
  | 'agencyLine'
  | 'gamePlatform'
  | 'placer'
  | 'runningSeries';

export type PersonnelDashboardDataType =
  | 'currency'
  | 'datetime'
  | 'number'
  | 'percent'
  | 'status'
  | 'text';

export interface PersonnelDashboardField {
  dataType: PersonnelDashboardDataType;
  emptyText: string;
  filterable: boolean;
  fixed?: 'left' | 'right';
  key: string;
  label: string;
  sortable: boolean;
  sourceKey: string;
  summarizable: boolean;
  width: number;
}

export interface PersonnelDashboardSchema {
  category: PersonnelDashboardCategory;
  fields: PersonnelDashboardField[];
  label: string;
  legacyTabKey: string;
  sheetName: string;
}

export type PersonnelDashboardValue = null | number | string;

export interface PersonnelDashboardRow {
  [key: string]: PersonnelDashboardValue;
  currency: string;
  departmentId: string;
  departmentName: string;
  id: string;
  key: string;
}

export interface PersonnelDashboardSummaryRow {
  currency: string;
  values: Record<string, number>;
}

export interface PersonnelDepartmentOption {
  label: string;
  value: string;
}

export interface PersonnelDashboardListQuery {
  category: PersonnelDashboardCategory;
  departmentId?: string;
  endDate?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  sortField?: string;
  sortOrder?: 'asc' | 'desc';
  startDate?: string;
  status?: 'abnormal' | 'all' | 'paused' | 'running';
}

export interface PersonnelDashboardListResult {
  dataCutoff: string;
  departmentOptions: PersonnelDepartmentOption[];
  items: PersonnelDashboardRow[];
  page: number;
  pageSize: number;
  schema: PersonnelDashboardSchema;
  summaryRows: PersonnelDashboardSummaryRow[];
  total: number;
}

export interface PersonnelDashboardCsvExport {
  content: string;
  fileName: string;
  rowCount: number;
}
