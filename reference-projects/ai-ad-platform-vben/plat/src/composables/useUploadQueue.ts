import { computed, ref } from 'vue';

/**
 * 上传并发队列 composable
 * @param limit 最大并发数，默认 5
 * @param onAllDone 所有任务完成后的回调（每次从有任务变为全部完成都会触发）
 */
export function useUploadQueue(limit = 5, onAllDone?: () => void) {
  const activeUploads = ref(0);
  const queue = ref<Array<() => Promise<void>>>([]);

  function processQueue() {
    while (queue.value.length > 0 && activeUploads.value < limit) {
      const task = queue.value.shift()!;
      activeUploads.value++;
      task().finally(() => {
        activeUploads.value--;
        if (activeUploads.value === 0 && queue.value.length === 0) {
          onAllDone?.();
        } else {
          processQueue();
        }
      });
    }
  }

  /** 将一个异步任务加入队列并尝试立即执行 */
  function enqueue(task: () => Promise<void>) {
    queue.value.push(task);
    processQueue();
  }

  /** 清空等待队列 */
  function reset() {
    queue.value = [];
  }

  const pendingCount = computed(() => queue.value.length);
  const isIdle = computed(() => activeUploads.value === 0 && queue.value.length === 0);

  return { activeUploads, pendingCount, isIdle, enqueue, reset };
}
