import type {
  ProjectAgencyLineSyncBatch,
  ProjectAgencyLineSyncFailure,
  ProjectAgencyLineSyncPage,
} from '#/api/fusion/types';

import { isFusionDemoMode } from '#/api/fusion/mode';
import { mainBackendClient } from '#/api/request';

/** 手动同步项目代理线；演示模式不连接正式 Google 服务账户。 */
export function synchronizeProjectAgencyLines(
  projectId: string,
): Promise<ProjectAgencyLineSyncBatch> {
  if (isFusionDemoMode()) {
    return Promise.reject(new Error('演示模式不支持代理线链接同步'));
  }
  return mainBackendClient.post(
    `/project/projects/${encodeURIComponent(projectId)}/agency-line-sync`,
    undefined,
    { skipErrorMessage: true },
  );
}

/** 分页读取项目代理线同步历史。 */
export function listProjectAgencyLineSyncBatches(
  projectId: string,
  page = 1,
  pageSize = 10,
): Promise<ProjectAgencyLineSyncPage<ProjectAgencyLineSyncBatch>> {
  if (isFusionDemoMode()) {
    return Promise.resolve({ items: [], page, pageSize, total: 0 });
  }
  return mainBackendClient.get(
    `/project/projects/${encodeURIComponent(projectId)}/agency-line-sync/batches`,
    { params: { page, pageSize }, skipErrorMessage: true },
  );
}

/** 分页读取一次同步中的失败行及原因。 */
export function listProjectAgencyLineSyncFailures(
  projectId: string,
  batchId: string,
  page = 1,
  pageSize = 20,
): Promise<ProjectAgencyLineSyncPage<ProjectAgencyLineSyncFailure>> {
  if (isFusionDemoMode()) {
    return Promise.resolve({ items: [], page, pageSize, total: 0 });
  }
  return mainBackendClient.get(
    `/project/projects/${encodeURIComponent(projectId)}/agency-line-sync/batches/${encodeURIComponent(batchId)}/failures`,
    { params: { page, pageSize }, skipErrorMessage: true },
  );
}
