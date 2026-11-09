import type { AdPublishingAdapter, AdPublishingJob } from '../types';

import {
  getAsyncTasksApi,
  preflightAdDraftApi,
  publishAdDraftApi,
} from '#/api';

function requiredId(value: string, label: string) {
  const normalized = value.trim();
  if (!normalized) throw new Error(`${label}缺少稳定 ID`);
  return normalized;
}

/**
 * Compatibility adapter over the established Fusion endpoints. It does not
 * invent a job query route: exact lookup remains a stable-ID filter over the
 * existing async-task query until the backend exposes one.
 */
export class HttpAdPublishingAdapter implements AdPublishingAdapter {
  async getJob(
    jobId: string,
    projectId?: string,
  ): Promise<AdPublishingJob | undefined> {
    const stableJobId = requiredId(jobId, '发布任务');
    const tasks = await getAsyncTasksApi(projectId?.trim() || undefined);
    const task = tasks.find((item) => item.id === stableJobId);
    if (!task) return undefined;
    return {
      createdAt: task.createdAt,
      id: task.id,
      message: task.message,
      platform: task.platform,
      progress: task.progress,
      projectId: task.projectId,
      status: task.status,
      title: task.title,
      updatedAt: task.updatedAt,
    };
  }

  async preflight(payload: Parameters<AdPublishingAdapter['preflight']>[0]) {
    return await preflightAdDraftApi(payload);
  }

  async publish(
    payload: Parameters<AdPublishingAdapter['publish']>[0],
    preflightToken?: string,
  ) {
    return await publishAdDraftApi(payload, preflightToken);
  }
}
