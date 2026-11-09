import type { SiteNotification } from './asset-flow';

import { useAppConfig } from '@vben/hooks';
import { preferences } from '@vben/preferences';
import { useAccessStore } from '@vben/stores';

import { createParser } from 'eventsource-parser';

const { backendURL } = useAppConfig(import.meta.env, import.meta.env.PROD);
const STREAM_PATH = '/asset-flow-v2/notifications/stream';

export class SiteNotificationStreamResponseError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = 'SiteNotificationStreamResponseError';
  }
}

interface SiteNotificationStreamOptions {
  lastEventId?: string;
  onConnected?: () => void;
  onEventId?: (eventId: string) => void;
  onNotification: (notification: SiteNotification) => void;
  onRetry?: (milliseconds: number) => void;
  signal: AbortSignal;
}

/**
 * 使用 fetch 读取 SSE，以便继续携带现有 Bearer Token。
 * 原生 EventSource 无法设置 Authorization 请求头，不能用于当前认证方式。
 */
export async function consumeSiteNotificationStream(
  options: SiteNotificationStreamOptions,
) {
  const token = useAccessStore().accessToken;
  if (!token) {
    throw new SiteNotificationStreamResponseError('当前登录已失效', 401);
  }

  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    'Accept-Language': preferences.app.locale,
    Authorization: `Bearer ${token}`,
  };
  if (options.lastEventId !== undefined) {
    headers['Last-Event-ID'] = options.lastEventId;
  }

  const response = await fetch(`${backendURL}${STREAM_PATH}`, {
    cache: 'no-store',
    headers,
    signal: options.signal,
  });
  const contentType = response.headers.get('content-type') ?? '';
  if (!response.ok || !contentType.includes('text/event-stream')) {
    throw new SiteNotificationStreamResponseError(
      '站内通知实时连接未建立',
      response.status,
    );
  }
  if (!response.body) {
    throw new SiteNotificationStreamResponseError(
      '浏览器未返回站内通知事件流',
      response.status,
    );
  }

  const parser = createParser({
    onEvent(event) {
      if (event.id !== undefined) options.onEventId?.(event.id);
      if (event.event === 'connected') {
        options.onConnected?.();
        return;
      }
      if (event.event !== 'notification') return;
      options.onNotification(JSON.parse(event.data) as SiteNotification);
    },
    onRetry(milliseconds) {
      options.onRetry?.(milliseconds);
    },
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
    parser.feed(decoder.decode());
  } finally {
    reader.releaseLock();
  }
}
