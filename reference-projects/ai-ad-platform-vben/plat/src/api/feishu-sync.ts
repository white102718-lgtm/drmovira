import { backendClient, mainBackendClient } from '#/api/request';

export interface FeishuAppConfig {
  appId: string;
  appName: string;
  appSecret?: string;
  id?: number | string;
}

export interface FeishuTask {
  appId?: string;
  appToken?: string;
  createTime?: string;
  id?: number | string;
  lastSyncTime?: string;
  status: number;
  tableId: string;
  tableName?: string;
  targetTableName?: string;
  taskId: number | string;
  taskName: string;
  taskType?: number;
}

export interface FeishuMapping {
  columnComment?: string;
  dataType?: string;
  feishuFieldName: string;
  fieldDesc?: string;
  id?: number | string;
  isRequired?: number;
  isSplit?: number;
  systemFieldName: string;
  taskId?: number | string;
}

export interface FeishuLog {
  endTime?: string;
  errMsg?: string;
  failCount?: number;
  id: number | string;
  startTime?: string;
  status?: number | string;
  successCount?: number;
  totalCount?: number;
}

export interface FeishuSheetConnection {
  appToken: string;
  tables: Array<{ name: string; tableId: string }>;
}

/** 飞书组织架构同步预览或执行结果。 */
export interface FeishuOrganizationSyncResult {
  conflictCount: number;
  conflicts: string[];
  departmentCreated: number;
  departmentDisabled: number;
  departmentTotal: number;
  departmentUpdated: number;
  userCreated: number;
  userDisabled: number;
  userTotal: number;
  userUpdated: number;
}

/** 飞书组织架构同步日志。 */
export interface FeishuOrganizationSyncLog {
  conflictCount: number;
  departmentCreated: number;
  departmentDisabled: number;
  departmentTotal: number;
  departmentUpdated: number;
  endedAt?: string;
  errorMessage?: string;
  id: string;
  startedAt: string;
  startedBy: null | string;
  status: 'FAILED' | 'PENDING' | 'REVIEW' | 'RUNNING' | 'SKIPPED' | 'SUCCESS';
  triggerType: 'MANUAL' | 'PREVIEW' | 'SCHEDULED';
  userCreated: number;
  userDisabled: number;
  userTotal: number;
  userUpdated: number;
}

export function getFeishuTaskList() {
  return mainBackendClient.get<FeishuTask[]>('/feishu/tasks');
}

export function createFeishuTask(data: Partial<FeishuTask>) {
  return mainBackendClient.post<FeishuTask>('/feishu/tasks', data);
}

export function updateFeishuTask(data: Partial<FeishuTask>) {
  const { taskId, ...payload } = data;
  return mainBackendClient.put<FeishuTask>(
    `/feishu/tasks/${encodeURIComponent(taskId as number | string)}`,
    payload,
  );
}

export function deleteFeishuTask(taskId: number | string) {
  return mainBackendClient.delete(
    `/feishu/tasks/${encodeURIComponent(taskId)}`,
  );
}

export function updateFeishuTaskStatus(
  taskId: number | string,
  status: number,
) {
  return mainBackendClient.request(
    `/feishu/tasks/${encodeURIComponent(taskId)}/status`,
    { data: { status }, method: 'PATCH' },
  );
}

export function triggerFeishuTask(taskId: number | string) {
  return mainBackendClient.post(
    `/feishu/tasks/${encodeURIComponent(taskId)}/sync`,
  );
}

export function getFeishuMappings(taskId: number | string) {
  return mainBackendClient.get<FeishuMapping[]>(
    `/feishu/tasks/${encodeURIComponent(taskId)}/mappings`,
  );
}

export function saveFeishuMappings(data: {
  mappings: FeishuMapping[];
  taskId: number | string;
}) {
  return mainBackendClient.put(
    `/feishu/tasks/${encodeURIComponent(data.taskId)}/mappings`,
    data.mappings,
  );
}

export function getFeishuLogs(taskId: number | string) {
  return mainBackendClient.get<FeishuLog[]>(
    `/feishu/tasks/${encodeURIComponent(taskId)}/logs`,
  );
}

export function testFeishuConnection(taskId: number | string) {
  return mainBackendClient.post(
    `/feishu/tasks/${encodeURIComponent(taskId)}/connection-test`,
  );
}

export function getFeishuAppConfig() {
  return mainBackendClient.get<FeishuAppConfig>('/feishu/config');
}

export function updateFeishuAppConfig(data: FeishuAppConfig) {
  return mainBackendClient.put<FeishuAppConfig>('/feishu/config', data);
}

export function getFeishuOrganizationAppConfig() {
  return backendClient.get<FeishuAppConfig>('/feishu/organization/config');
}

export function updateFeishuOrganizationAppConfig(data: FeishuAppConfig) {
  return backendClient.put<FeishuAppConfig>(
    '/feishu/organization/config',
    data,
  );
}

export function connectFeishuTables(data: {
  appId?: string;
  appTokenOrUrl: string;
  taskType: number;
}) {
  return mainBackendClient.post<FeishuSheetConnection>(
    '/feishu/tables/discover',
    data,
  );
}

export function getFeishuFields(taskId: number | string) {
  return mainBackendClient.get<Array<{ fieldName?: string; name?: string }>>(
    `/feishu/tasks/${encodeURIComponent(taskId)}/fields`,
  );
}

export function getFeishuTableColumns(tableName: string) {
  return mainBackendClient.get<
    Array<{ columnComment?: string; columnName: string }>
  >('/feishu/system-columns', { params: { tableName } });
}

/** 自动同步频率和缺失保护；nextRunAt 带明确时区偏移。 */
export interface FeishuOrganizationSchedule {
  dailyTime: string;
  enabled: boolean;
  intervalMinutes: number;
  missingCountLimit: number;
  missingPercentLimit: number;
  nextRunAt?: null | string;
}

/** 人工确认绑定本次预览，不能复用其他用户或已变化的快照。 */
export interface FeishuOrganizationPreview {
  previewId: string;
  requiresReview: boolean;
  result: FeishuOrganizationSyncResult;
}

export function previewFeishuOrganization() {
  return backendClient.post<FeishuOrganizationPreview>(
    '/feishu/organization/preview',
  );
}

export function syncFeishuOrganization(data: {
  acceptMissing: boolean;
  previewId: string;
}) {
  return backendClient.post<{ id: string; status: 'PENDING' }>(
    '/feishu/organization/sync',
    data,
  );
}

/** 查询自动同步计划。 */
export function getFeishuOrganizationSchedule() {
  return backendClient.get<FeishuOrganizationSchedule>(
    '/feishu/organization/schedule',
  );
}

/** 保存计划；开启时附带15分钟内成功预览的编号。 */
export function updateFeishuOrganizationSchedule(
  data: FeishuOrganizationSchedule & { previewId?: string },
) {
  return backendClient.put<FeishuOrganizationSchedule>(
    '/feishu/organization/schedule',
    data,
  );
}

export function getFeishuOrganizationLogs() {
  return backendClient.get<FeishuOrganizationSyncLog[]>(
    '/feishu/organization/logs',
  );
}
