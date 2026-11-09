import { backendClient } from '#/api/request';

// 任务管理项接口定义
export interface TaskDispatchItem {
  create_time: string;
  deadline: null | string;
  description: null | string;
  game_platform: null | string;
  id: null | string;
  related_users: string[];
  status: 'completed' | 'in_progress' | 'initiated';
  task_type: null | string;
}

// 获取任务列表参数接口
interface TaskListParams {
  endTime?: string;
  gamePlatform?: string;
  page?: number;
  pageSize?: number;
  startTime?: string;
  taskType?: string;
}

/**
 * 获取任务列表
 * @param params 查询参数
 */
export function getTaskList(params?: TaskListParams) {
  const queryParams = new URLSearchParams();
  if (params?.page) {
    queryParams.set('page', params.page.toString());
  }
  if (params?.pageSize) {
    queryParams.set('pageSize', params.pageSize.toString());
  }
  if (params?.taskType) {
    queryParams.set('taskType', params.taskType);
  }
  if (params?.gamePlatform) {
    queryParams.set('gamePlatform', params.gamePlatform);
  }
  if (params?.startTime) {
    queryParams.set('startTime', params.startTime);
  }
  if (params?.endTime) {
    queryParams.set('endTime', params.endTime);
  }

  const query = queryParams.toString() ? `?${queryParams.toString()}` : '';
  return backendClient.get(`tasks/${query}`);
}

/**
 * 创建新任务
 * @param data 任务数据
 */
export function createTask(data: TaskDispatchItem) {
  return backendClient.post('tasks/', data);
}

/**
 * 更新任务
 * @param id 任务ID
 * @param data 更新的任务数据
 */
export function updateTask(id: null | string, data: TaskDispatchItem) {
  if (id === null) {
    return Promise.reject(new Error('任务ID不能为空'));
  }
  return backendClient.put(`tasks/${id}`, data);
}

/**
 * 删除任务
 * @param id 任务ID
 */
export function deleteTask(id: null | string) {
  if (id === null) {
    return Promise.reject(new Error('任务ID不能为空'));
  }
  return backendClient.delete(`tasks/${id}`);
}
