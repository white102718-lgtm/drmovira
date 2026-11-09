import { mainBackendClient } from '#/api/request';

export type ManualTaskStatus = 'FAILED' | 'PENDING' | 'RUNNING' | 'SUCCESS';

export interface ManualTaskAction {
  code: string;
  confirmationText?: string;
  dangerous: boolean;
  description: string;
  name: string;
}

export interface ManualTask {
  actions: ManualTaskAction[];
  code: string;
  description: string;
  name: string;
  running: boolean;
}

export interface ManualTaskExecution {
  actionCode: string;
  actionName: string;
  finishedAt?: string;
  id: string;
  logContent?: string;
  startedAt?: string;
  status: ManualTaskStatus;
  taskCode: string;
  taskName: string;
  triggeredAt: string;
  triggeredBy: string;
  triggeredByName: string;
}

export interface ManualTaskExecutionPage {
  items: ManualTaskExecution[];
  page: number;
  pageSize: number;
  total: number;
}

export function getManualTasks() {
  return mainBackendClient.get<ManualTask[]>('/manual-tasks');
}

export function triggerManualTask(
  taskCode: string,
  actionCode: string,
  confirmationText?: string,
) {
  return mainBackendClient.post<ManualTaskExecution>(
    `/manual-tasks/${taskCode}/executions`,
    { actionCode, confirmationText },
  );
}

export function getManualTaskExecutions(params: {
  page: number;
  pageSize: number;
  taskCode?: string;
}) {
  return mainBackendClient.get<ManualTaskExecutionPage>(
    '/manual-tasks/executions',
    { params },
  );
}

export function getManualTaskExecution(id: string) {
  return mainBackendClient.get<ManualTaskExecution>(
    `/manual-tasks/executions/${id}`,
  );
}
