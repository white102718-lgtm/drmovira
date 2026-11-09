import { adpulseClient } from '#/api/request';

async function getUploadTaskApi(taskId: string, skipErrorMessage = false) {
  return adpulseClient.get(`upload-tasks/${taskId}`, skipErrorMessage ? { skipErrorMessage: true } : undefined);
}

function getPollingInterval(fileSizeBytes: number): number {
  if (fileSizeBytes < 1 * 1024 * 1024) return 1000;
  if (fileSizeBytes < 10 * 1024 * 1024) return 2000;
  if (fileSizeBytes < 50 * 1024 * 1024) return 4000;
  if (fileSizeBytes < 200 * 1024 * 1024) return 8000;
  if (fileSizeBytes < 350 * 1024 * 1024) return 12000;
  if (fileSizeBytes < 1 * 1024 * 1024 * 1024) return 15000;
  if (fileSizeBytes < 3 * 1024 * 1024 * 1024) return 20000;
  if (fileSizeBytes < 10 * 1024 * 1024 * 1024) return 30000;
  return 30_000;
}

export async function pollUploadTask(taskId: string, fileSizeBytes = 0, signal?: AbortSignal, interval?: number, returnRaw = false, skipErrorMessage = false): Promise<any> {
  if (interval === undefined) interval = getPollingInterval(fileSizeBytes);
  return new Promise((resolve, reject) => {
    const poll = async () => {
      if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
      try {
        const res: any = await getUploadTaskApi(taskId, skipErrorMessage);
        if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
        if (res.status === 'done') return resolve(returnRaw ? res.result : (res.result?.items ?? []));
        if (res.status === 'failed') return reject(new Error(res.error || '任务失败'));
        setTimeout(poll, interval);
      } catch (e: any) {
        if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
        // HTTP 4xx 或业务 code 4xx 属于明确失败，不重试
        const httpStatus = e?.response?.status;
        const bodyCode = e?.data?.code ?? e?.response?.data?.code;
        const is4xx =
          (httpStatus !== undefined && httpStatus >= 400 && httpStatus < 500) ||
          (bodyCode !== undefined && bodyCode >= 400 && bodyCode < 500);
        if (is4xx) {
          reject(new Error(e?.data?.message ?? e?.response?.data?.message ?? e?.message ?? '任务失败'));
          return;
        }
        setTimeout(poll, interval);
      }
    };
    poll();
  });
}
