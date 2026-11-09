import { mainBackendClient } from './request';

/** 人工确认的日报指标；平台实际消耗不允许写入。 */
export interface DeliveryMetrics {
  dailySpend: number;
  impressions: number;
  clicks: number;
  installs: number;
  registrations: number;
  firstPurchases: number;
  adjustmentAmount: number;
  secondaryDeduction: number;
  adjustmentType: '公司承担' | '未设置' | '本人承担';
  remark: string;
}

/** 项目与代理线的稳定关联。 */
export interface DeliveryLineOption {
  projectId: string;
  projectName: string;
  agencyLineId: string;
  agencyLineName: string;
}

/** 一条日报最多五张本人截图。 */
export interface DeliveryAttachment {
  id: string;
  name: string;
  mimeType: string;
}

/** 服务端已合并平台来源与人工填写数据的日报行。 */
export interface DeliveryReportRow extends DeliveryLineOption {
  id: null | string;
  platform: string;
  actualSpend: null | number;
  metrics: DeliveryMetrics;
  attachments: DeliveryAttachment[];
  accountIds: string[];
  campaignIds: string[];
  saved: boolean;
}

/** 当前日期的本人日报，包含未匹配而隐藏的数据组数。 */
export interface DeliveryReportResult {
  date: string;
  reporterId: string;
  reporterName: string;
  departmentName?: string;
  unmatchedCount: number;
  rows: DeliveryReportRow[];
}

/** 可写入Google Sheet的投放日报字段。 */
export interface DeliveryGoogleFieldDefinition {
  field: string;
  label: string;
  required: boolean;
  type: 'date' | 'number' | 'string';
}

/** 一个日报字段到Google列的映射。 */
export interface DeliveryGoogleFieldMapping {
  required: boolean;
  systemField: string;
  targetColumn: string;
  targetHeader: string;
  uniqueKey: boolean;
}

/** 已共享给日报服务账户的Google Sheets文件。 */
export interface DeliveryGoogleDriveFile {
  id: string;
  modifiedTime?: string;
  name: string;
}

/** Spreadsheet中的一个目标页签。 */
export interface DeliveryGoogleSheetTab {
  id: string;
  title: string;
}

/** 日报目标表格需要共享给此服务账户。 */
export interface DeliveryGoogleServiceAccount {
  email: string;
}

/** 从项目客户日报链接解析出的Google写入目标。 */
export interface DeliveryGoogleProjectTarget {
  configured: boolean;
  dailyReportUrl?: string;
  message: string;
  sheetId?: string;
  sheets: DeliveryGoogleSheetTab[];
  spreadsheet?: DeliveryGoogleDriveFile;
}

/** 一个项目唯一的Google日报写入模板。 */
export interface DeliveryGoogleTemplate {
  enableFlag: number;
  fieldMappings: DeliveryGoogleFieldMapping[];
  headerRow: number;
  id: string;
  projectId: string;
  projectName: string;
  sheetId: string;
  sheetTitle: string;
  spreadsheetId: string;
  spreadsheetName: string;
  templateName: string;
  updatedAt?: string;
}

export interface DeliveryGoogleTemplatePayload {
  enableFlag: number;
  fieldMappings: DeliveryGoogleFieldMapping[];
  headerRow: number;
  projectId: string;
  templateName: string;
}

export interface DeliveryGooglePreviewGroup {
  fieldMappings: DeliveryGoogleFieldMapping[];
  projectId: string;
  projectName: string;
  rows: Array<{ reportId: string; values: Record<string, unknown> }>;
  sheetTitle: string;
  spreadsheetName: string;
  templateId: string;
  templateName: string;
}

export interface DeliveryGooglePreview {
  groups: DeliveryGooglePreviewGroup[];
  totalCount: number;
}

export interface DeliveryGooglePushBatch {
  createdAt?: string;
  errorMessage?: string;
  failedCount: number;
  finishedAt?: string;
  id: string;
  items: Array<{
    attemptCount: number;
    errorMessage?: string;
    id: string;
    projectId: string;
    reportId: string;
    status: number;
    targetRow?: number;
  }>;
  startedAt?: string;
  status: number;
  successCount: number;
  totalCount: number;
}

/** 日报使用main业务服务，查询与保存均由服务端确定当前用户。 */
export const deliveryReportApi = {
  page: (params: {
    startDate: string;
    endDate: string;
    reporterId?: string;
    page: number;
    pageSize: number;
    reporter: string;
    project: string;
    line: string;
  }) =>
    mainBackendClient.get<{
      total: number;
      page: number;
      pageSize: number;
      days: DeliveryReportResult[];
    }>('/delivery-reports/page', { params }),
  stats: (params: {
    startDate: string;
    endDate: string;
    reporterId?: string;
    reporter: string;
    project: string;
    line: string;
  }) =>
    mainBackendClient.get<{
      count: number;
      dailySpend: number;
      actualSpend: number;
    }>('/delivery-reports/stats', { params }),
  reporters: () =>
    mainBackendClient.get<{ id: string; name: string }[]>(
      '/delivery-reports/reporters',
    ),
  read: (date: string, reporterId?: string) =>
    mainBackendClient.get<DeliveryReportResult[]>('/delivery-reports/read', {
      params: { date, reporterId },
    }),
  performance: (startDate: string, endDate: string, reporterId?: string) =>
    mainBackendClient.get<{
      startDate: string;
      endDate: string;
      departmentName: string;
      days: DeliveryReportResult[];
    }>('/delivery-reports/performance', {
      params: { startDate, endDate, reporterId },
    }),
  options: () =>
    mainBackendClient.get<DeliveryLineOption[]>('/delivery-reports/options'),
  query: (date: string) =>
    mainBackendClient.get<DeliveryReportResult>('/delivery-reports', {
      params: { date },
    }),
  save: (date: string, rows: DeliveryReportRow[]) =>
    mainBackendClient.put<DeliveryReportResult>('/delivery-reports', {
      date,
      rows: rows.map((row) => ({
        projectId: row.projectId,
        agencyLineId: row.agencyLineId,
        platform: row.platform,
        metrics: row.metrics,
        attachmentIds: row.attachments.map((file) => file.id),
      })),
    }),
  googleFields: () =>
    mainBackendClient.get<DeliveryGoogleFieldDefinition[]>(
      '/delivery-reports/google-push/fields',
    ),
  googleServiceAccount: () =>
    mainBackendClient.get<DeliveryGoogleServiceAccount>(
      '/delivery-reports/google-push/service-account',
    ),
  googleFiles: (keyword?: string) =>
    mainBackendClient.get<DeliveryGoogleDriveFile[]>(
      '/delivery-reports/google-push/files',
      { params: keyword ? { keyword } : undefined },
    ),
  googleSheets: (fileId: string) =>
    mainBackendClient.get<DeliveryGoogleSheetTab[]>(
      '/delivery-reports/google-push/sheets',
      { params: { fileId } },
    ),
  googleProjectTarget: (projectId: string) =>
    mainBackendClient.get<DeliveryGoogleProjectTarget>(
      '/delivery-reports/google-push/project-target',
      { params: { projectId } },
    ),
  googleColumns: (fileId: string, sheetName: string, headerRow = 1) =>
    mainBackendClient.get<string[]>(
      '/delivery-reports/google-push/columns',
      { params: { fileId, headerRow, sheetName } },
    ),
  googleTemplates: () =>
    mainBackendClient.get<DeliveryGoogleTemplate[]>(
      '/delivery-reports/google-push/templates',
    ),
  createGoogleTemplate: (payload: DeliveryGoogleTemplatePayload) =>
    mainBackendClient.post<string>(
      '/delivery-reports/google-push/templates',
      payload,
    ),
  updateGoogleTemplate: (
    id: string,
    payload: DeliveryGoogleTemplatePayload,
  ) =>
    mainBackendClient.put<void>(
      `/delivery-reports/google-push/templates/${encodeURIComponent(id)}`,
      payload,
    ),
  deleteGoogleTemplate: (id: string) =>
    mainBackendClient.delete<void>(
      `/delivery-reports/google-push/templates/${encodeURIComponent(id)}`,
    ),
  previewGooglePush: (reportIds: string[]) =>
    mainBackendClient.post<DeliveryGooglePreview>(
      '/delivery-reports/google-push/preview',
      { reportIds },
    ),
  createGooglePushBatch: (reportIds: string[]) =>
    mainBackendClient.post<DeliveryGooglePushBatch>(
      '/delivery-reports/google-push/batches',
      { reportIds },
    ),
  googlePushBatch: (id: string) =>
    mainBackendClient.get<DeliveryGooglePushBatch>(
      `/delivery-reports/google-push/batches/${encodeURIComponent(id)}`,
    ),
  recentGooglePushBatches: () =>
    mainBackendClient.get<DeliveryGooglePushBatch[]>(
      '/delivery-reports/google-push/batches',
    ),
  retryGooglePushBatch: (id: string) =>
    mainBackendClient.post<DeliveryGooglePushBatch>(
      `/delivery-reports/google-push/batches/${encodeURIComponent(id)}/retry`,
    ),
};
