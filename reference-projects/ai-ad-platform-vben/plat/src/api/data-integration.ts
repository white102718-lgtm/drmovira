import { mainBackendClient } from '#/api/request';

export type GoogleAccountId = number | string;
export type GoogleMappingId = number | string;

export interface GoogleMapping {
  conflictStrategy?: number;
  dateRangeConfig?: string;
  dateRangeType?: number;
  enableFlag?: number;
  fieldMappings?: string;
  googleAccountId: GoogleAccountId;
  id: GoogleMappingId;
  lastSyncTime?: string;
  name: string;
  reportType: number;
  reportTypeName?: string;
  sheetNames?: string;
  spreadsheetId: string;
  spreadsheetModifiedTime?: string;
  spreadsheetName: string;
  syncDirection?: number;
  syncFrequency?: number;
  syncTime?: string;
}

export interface GoogleAccount {
  authorizedAt?: string;
  authStatus: number;
  email: string;
  id: GoogleAccountId;
  mappings?: GoogleMapping[];
  picture?: string;
}

export interface GoogleDriveFile {
  id: string;
  modifiedTime?: string;
  name: string;
}

export interface GoogleSheetTab {
  id: string;
  title: string;
}

export interface GoogleSyncData {
  clicks?: number;
  id: string;
  impressions?: number;
  mediaPlacement?: string;
  purchases?: number;
  registrations?: number;
  returnAmount?: number;
  spendAmount?: number;
  startDate: string;
  subscriptions?: number;
  subtaskName: string;
  taskName: string;
  updatedAt?: string;
}

export interface GoogleSyncDataPage {
  items: GoogleSyncData[];
  page: number;
  pageSize: number;
  total: number;
}

export interface GoogleSyncLog {
  createdAt: string;
  errorMessage?: string;
  finishedAt?: string;
  fullSync: boolean;
  id: string;
  startedAt?: string;
  status: 0 | 1 | 2 | 3;
}

export interface GoogleSyncLogPage {
  items: GoogleSyncLog[];
  page: number;
  pageSize: number;
  total: number;
}

export interface GoogleFieldMappingPayload {
  sheetColumn: string;
  sheetColumnName: string;
  systemField: string;
}

export interface GoogleMappingPayload {
  conflictStrategy: number;
  dateRangeConfig: Record<string, number | string>;
  dateRangeType: number;
  fieldMappings: Record<string, GoogleFieldMappingPayload[]>;
  googleAccountId: GoogleAccountId;
  id?: GoogleMappingId;
  name: string;
  reportType: number;
  sheetNames: string[];
  spreadsheetId: string;
  spreadsheetModifiedTime?: string;
  spreadsheetName: string;
  syncDirection: number;
  syncFrequency: number;
  syncTime: string;
}

export function getGoogleAccountList() {
  return mainBackendClient.get<GoogleAccount[]>('/data-integration/accounts');
}

export function disconnectGoogleAccount(id: GoogleAccountId) {
  return mainBackendClient.post(
    `/data-integration/accounts/${encodeURIComponent(id)}/disconnect`,
  );
}

export function removeGoogleAccount(id: GoogleAccountId) {
  return mainBackendClient.delete(
    `/data-integration/accounts/${encodeURIComponent(id)}`,
  );
}

export function getGoogleOAuthUrl(state?: string) {
  return mainBackendClient.get<string>('/data-integration/oauth/authorize', {
    params: state ? { state } : undefined,
  });
}

export function reauthorizeGoogleAccount(id: GoogleAccountId, state?: string) {
  return mainBackendClient.post<string>(
    `/data-integration/accounts/${encodeURIComponent(id)}/reauthorize`,
    undefined,
    { params: state ? { state } : undefined },
  );
}

export function getGoogleDriveFiles(params: {
  accountId: GoogleAccountId;
  keyword?: string;
}) {
  return mainBackendClient.get<GoogleDriveFile[]>('/data-integration/files', {
    params,
  });
}

export function getGoogleSheetTabs(params: {
  accountId: GoogleAccountId;
  fileId: string;
}) {
  return mainBackendClient.get<GoogleSheetTab[]>('/data-integration/sheets', {
    params,
  });
}

export function getGoogleSheetColumns(params: {
  accountId: GoogleAccountId;
  fileId: string;
  sheetName: string;
}) {
  return mainBackendClient.get<string[]>('/data-integration/columns', {
    params,
  });
}

export function createGoogleMapping(data: GoogleMappingPayload) {
  return mainBackendClient.post<GoogleMappingId>(
    '/data-integration/mappings',
    data,
  );
}

export function getGoogleMappingDetail(id: GoogleMappingId) {
  return mainBackendClient.get<GoogleMapping>(
    `/data-integration/mappings/${encodeURIComponent(id)}`,
  );
}

export function updateGoogleMapping(data: GoogleMappingPayload) {
  const { id, ...payload } = data;
  return mainBackendClient.put(
    `/data-integration/mappings/${encodeURIComponent(id as GoogleMappingId)}`,
    payload,
  );
}

export function syncGoogleMapping(id: GoogleMappingId) {
  return mainBackendClient.post(
    `/data-integration/mappings/${encodeURIComponent(id)}/sync`,
  );
}

export function getGoogleSyncData(
  id: GoogleMappingId,
  params: {
    endDate?: string;
    page?: number;
    pageSize?: number;
    startDate?: string;
    taskName?: string;
  },
) {
  return mainBackendClient.get<GoogleSyncDataPage>(
    `/data-integration/mappings/${encodeURIComponent(id)}/sync-data`,
    { params },
  );
}

export function getGoogleSyncLogs(
  id: GoogleMappingId,
  params: { page?: number; pageSize?: number },
) {
  return mainBackendClient.get<GoogleSyncLogPage>(
    `/data-integration/mappings/${encodeURIComponent(id)}/sync-logs`,
    { params },
  );
}

export function updateGoogleMappingStatus(
  id: GoogleMappingId,
  enableFlag: number,
) {
  return mainBackendClient.request(
    `/data-integration/mappings/${encodeURIComponent(id)}/status`,
    { data: { enableFlag }, method: 'PATCH' },
  );
}

export function deleteGoogleMapping(id: GoogleMappingId) {
  return mainBackendClient.delete(
    `/data-integration/mappings/${encodeURIComponent(id)}`,
  );
}
