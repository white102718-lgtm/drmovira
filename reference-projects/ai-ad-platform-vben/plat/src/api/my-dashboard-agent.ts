import type {
  DashboardAnalysis,
  DashboardAnalyzeQuery,
  DashboardHosting,
  DashboardHostingQuery,
} from '#/domain/my-dashboard/types';

import { useAccessStore } from '@vben/stores';

import { AgentRequestError } from './agent';

const base = import.meta.env.VITE_GLOB_AGENT_API_URL || '/agent';

/** 智能体返回裸 JSON；独立超时和取消信号，不能使用 Java 的信封拦截器。 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  const timeout = window.setTimeout(() => controller.abort('timeout'), 60_000);
  if (init.signal?.aborted) cancel();
  else init.signal?.addEventListener('abort', cancel, { once: true });
  try {
    const headers = new Headers(init.headers);
    const token = useAccessStore().accessToken;
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(
      `${base.replace(/\/$/, '')}/v1/my-dashboard/${path}`,
      {
        ...init,
        credentials: 'include',
        headers,
        signal: controller.signal,
      },
    );
    if (!response.ok) {
      let detail: unknown;
      try {
        const body: { detail?: unknown } = await response.json();
        detail = body.detail;
      } catch {
        detail = undefined;
      }
      throw new AgentRequestError(
        typeof detail === 'string' && detail ? detail : '智能体分析暂时不可用',
        response.status,
      );
    }
    return (await response.json()) as T;
  } catch (error) {
    if (controller.signal.reason === 'timeout') {
      throw new Error('智能体请求超过 60 秒，请稍后重试。');
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    init.signal?.removeEventListener('abort', cancel);
  }
}

export function analyzeMyDashboardApi(
  query: DashboardAnalyzeQuery,
  signal?: AbortSignal,
) {
  // 显式白名单，不能把浏览器身份、指标或对象列表当作智能体事实来源。
  return request<DashboardAnalysis>('analyze', {
    body: JSON.stringify({
      account_id: query.account_id?.replace(/^act_/, '') || undefined,
      end_date: query.end_date,
      focus_id: query.focus_id,
      grain: query.grain,
      range: query.range,
      start_date: query.start_date,
    }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
    signal,
  });
}

export function getMyDashboardHostingApi() {
  return request<DashboardHosting>('hosting');
}

export function saveMyDashboardHostingApi(query: DashboardHostingQuery) {
  const body = query.enabled
    ? {
        enabled: true,
        cadence: query.cadence,
        range: query.range,
        spend_change_threshold: query.spend_change_threshold,
      }
    : { enabled: false };
  return request<DashboardHosting>('hosting', {
    body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
}
