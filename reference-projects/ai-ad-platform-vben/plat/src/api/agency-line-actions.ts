import type { AgencyLine } from '#/domain/agency-line';

import { mainBackendClient } from './request';
import { normalizeAgencyLine } from '#/domain/agency-line/adapters/http';

/** 批量修改代理线业务状态，整批成功或回滚，不触发媒体广告启停。 */
export function changeAgencyLineStatuses(
  agencyLineIds: string[],
  status: 'active' | 'stopped',
) {
  return mainBackendClient.request<void>('/project/agency-lines/status', {
    method: 'PATCH',
    data: { agencyLineIds, status },
    skipErrorMessage: true,
  });
}

/** 快捷修改仅提交优化师 ID，姓名及状态由服务端返回。 */
export async function changeAgencyLineOptimizer(
  id: string,
  optimizerId?: string,
) {
  const line = await mainBackendClient.request<AgencyLine>(
    `/project/agency-lines/${encodeURIComponent(id)}/optimizer`,
    {
      method: 'PATCH',
      data: { optimizerId: optimizerId || null },
      skipErrorMessage: true,
    },
  );
  return normalizeAgencyLine(line);
}
