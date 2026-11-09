import type { ProjectOperatingTask } from './fusion/types';

import { mainBackendClient } from './request';

/** 项目只读任务摘要分页，不扩大任务中心详情及交付权限。 */
export interface ProjectTaskPage {
  items: ProjectOperatingTask[];
  page: number;
  pageSize: number;
  total: number;
}

/** 按项目查询已完成任务，服务端分页覆盖全部项目成员的摘要。 */
export function getCompletedProjectTasks(
  id: string,
  page: number,
  pageSize: number,
) {
  return mainBackendClient.get<ProjectTaskPage>(
    `/project/projects/${encodeURIComponent(id)}/completed-tasks`,
    { params: { page, pageSize } },
  );
}

/** 业务状态变更接口不触发媒体平台广告启停。 */
export function changeProjectAgencyLineStatus(
  id: string,
  agencyLineIds: string[],
  status: 'active' | 'stopped',
) {
  return mainBackendClient.request<void>(
    `/project/projects/${encodeURIComponent(id)}/agency-line-status`,
    { data: { agencyLineIds, status }, method: 'PATCH' },
  );
}
