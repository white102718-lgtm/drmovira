import type { SiteNotification } from '#/api/asset-flow';

import { onMounted, onUnmounted, watch } from 'vue';

import { useAccessStore } from '@vben/stores';

import {
  consumeSiteNotificationStream,
  SiteNotificationStreamResponseError,
} from '#/api/site-notification-stream';

interface UseSiteNotificationStreamOptions {
  onConnectionRejected?: () => Promise<void> | void;
  onNotification: (notification: SiteNotification) => void;
}

const MAX_RETRY_DELAY = 30_000;

/** 管理站内通知 SSE 生命周期、指数退避重连和 Last-Event-ID 续传。 */
export function useSiteNotificationStream(
  options: UseSiteNotificationStreamOptions,
) {
  const accessStore = useAccessStore();
  let active = false;
  let controller: AbortController | undefined;
  let lastEventId: string | undefined;
  let retryAttempt = 0;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let serverRetryDelay = 1_000;
  let rejectionReported = false;

  function clearRetryTimer() {
    if (retryTimer === undefined) return;
    clearTimeout(retryTimer);
    retryTimer = undefined;
  }

  function stopConnection(resetCursor = false) {
    clearRetryTimer();
    controller?.abort();
    controller = undefined;
    retryAttempt = 0;
    rejectionReported = false;
    if (resetCursor) lastEventId = undefined;
  }

  function scheduleReconnect() {
    if (!active || !accessStore.accessToken || retryTimer !== undefined) return;
    const exponentialDelay = Math.min(
      MAX_RETRY_DELAY,
      serverRetryDelay * 2 ** retryAttempt,
    );
    const jitter = Math.floor(Math.random() * 400);
    retryAttempt += 1;
    retryTimer = setTimeout(() => {
      retryTimer = undefined;
      void connect();
    }, exponentialDelay + jitter);
  }

  async function connect() {
    if (!active || !accessStore.accessToken || controller) return;
    const currentController = new AbortController();
    controller = currentController;
    try {
      await consumeSiteNotificationStream({
        lastEventId,
        onConnected() {
          retryAttempt = 0;
          rejectionReported = false;
        },
        onEventId(eventId) {
          lastEventId = eventId;
        },
        onNotification: options.onNotification,
        onRetry(milliseconds) {
          serverRetryDelay = Math.max(1_000, milliseconds);
        },
        signal: currentController.signal,
      });
    } catch (error) {
      if (currentController.signal.aborted) return;
      if (
        error instanceof SiteNotificationStreamResponseError &&
        !rejectionReported
      ) {
        rejectionReported = true;
        await options.onConnectionRejected?.();
      }
    } finally {
      if (controller === currentController) controller = undefined;
      if (!currentController.signal.aborted) scheduleReconnect();
    }
  }

  function handleOnline() {
    if (!active || controller) return;
    clearRetryTimer();
    void connect();
  }

  watch(
    () => accessStore.accessToken,
    (token, previousToken) => {
      if (!active || token === previousToken) return;
      stopConnection(true);
      if (token) void connect();
    },
  );

  onMounted(() => {
    active = true;
    window.addEventListener('online', handleOnline);
    if (accessStore.accessToken) void connect();
  });

  onUnmounted(() => {
    active = false;
    window.removeEventListener('online', handleOnline);
    stopConnection(true);
  });
}
