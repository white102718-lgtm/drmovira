/**
 * AdPulse 智能体（和飞书机器人同一个进程）。
 *
 * 这里不走 requestClient：对话是 SSE，而且智能体返回的是裸 JSON，没有后端那层
 * { code, data } 信封。附件和成效图也要带上登录头，所以统一用 fetch。
 */
import { useAccessStore } from '@vben/stores';

const BASE = import.meta.env.VITE_GLOB_AGENT_API_URL || '/agent';

export interface AgentChoiceOption {
  hint?: string;
  id: string;
  label: string;
}

export interface AgentReportMetrics {
  first_recharge_cost?: null | number | string;
  first_recharge_users?: null | number | string;
  registration_cost?: null | number | string;
  registrations?: null | number | string;
  spend: number | string;
}

export interface AgentReportPayload {
  agent_line: string;
  caliber?: string;
  end_date: string;
  metrics: AgentReportMetrics;
  rows?: Record<string, any>[];
  source?: string;
  start_date: string;
  timezone: string;
}

/**
 * 块协议。飞书那边把同一份块渲染成卡片，网页这边渲染成 DOM，
 * 数字都来自 payload，不经模型的手。
 */
export type AgentBlock =
  | { caption?: string; type: 'image'; url: string }
  | { content: string; type: 'error' }
  | { content: string; type: 'text' }
  | { content?: string; type: 'demo_badge' }
  | { filename: string; size?: number; type: 'file'; url: string }
  | { payload: AgentReportPayload; title: string; type: 'report' }
  | { prompt?: string; type: 'feishu_bind' }
  | { text: string; type: 'link'; url: string }
  | { type: string; [key: string]: any }
  | {
      field?: string;
      options: AgentChoiceOption[];
      prompt: string;
      thread_id?: string;
      type: 'choice';
    }
  | {
      payload: {
        account?: string;
        confirm_label?: string;
        daily_budget?: string;
        kind?: string;
        preview_id: string;
        summary?: string;
        title?: string;
      };
      thread_id?: string;
      type: 'confirm';
    };

export interface AgentConversation {
  created_at: number;
  id: string;
  running?: boolean;
  title: string;
  updated_at: number;
}

export interface AgentMessage {
  at: number;
  blocks: AgentBlock[];
  id: string;
  role: 'assistant' | 'user';
}

export class AgentRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'AgentRequestError';
    this.status = status;
  }
}

function authHeaders(): Record<string, string> {
  const accessStore = useAccessStore();
  const token = accessStore.accessToken;
  rememberAgentDownloadCookie();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** <a href> 下载附件带不上 Authorization，把 token 写到 /agent 路径下的 cookie。 */
export function rememberAgentDownloadCookie() {
  const token = useAccessStore().accessToken;
  if (!token || typeof document === 'undefined') return;
  document.cookie = `agent_web_token=${encodeURIComponent(token)}; Path=/agent; SameSite=Lax`;
}

async function failure(response: Response): Promise<AgentRequestError> {
  let detail = '';
  try {
    const body = await response.json();
    detail = body?.detail ?? body?.message ?? '';
  } catch {
    detail = '';
  }
  if (response.status === 401) {
    return new AgentRequestError(detail || '登录已失效，请刷新页面重新登录。', 401);
  }
  if (response.status === 404) {
    return new AgentRequestError(detail || '内容不存在或已过期。', 404);
  }
  return new AgentRequestError(
    detail || '智能体暂时不可用，请稍后再试。',
    response.status,
  );
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers ?? {}) },
  });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as T;
}

export async function listConversations(): Promise<AgentConversation[]> {
  const body = await request<{ items: AgentConversation[] }>('/v1/conversations');
  return body.items ?? [];
}

export async function createConversation(): Promise<AgentConversation> {
  return request<AgentConversation>('/v1/conversations', { method: 'POST' });
}

export async function deleteConversation(id: string): Promise<void> {
  await request(`/v1/conversations/${id}`, { method: 'DELETE' });
}

export async function fetchMessages(id: string): Promise<AgentMessage[]> {
  const body = await request<{ items: AgentMessage[] }>(
    `/v1/conversations/${id}/messages`,
  );
  return body.items ?? [];
}

export interface AgentRun {
  blocks?: AgentBlock[];
  conversation_id: string;
  progress?: AgentProgress[];
  running: boolean;
  started_at?: number;
}

export async function fetchRun(id: string): Promise<AgentRun> {
  return request<AgentRun>(`/v1/conversations/${id}/run`);
}

function filenameFromDisposition(header: string | null): string {
  if (!header) return '';
  const encoded = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(header);
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1].trim());
    } catch {
      return encoded[1].trim();
    }
  }
  const quoted = /filename\s*=\s*"([^"]+)"/i.exec(header);
  if (quoted?.[1]) return quoted[1].trim();
  const plain = /filename\s*=\s*([^;]+)/i.exec(header);
  return (plain?.[1] || '').trim().replace(/^utf-8''/i, '');
}

/** 成效图和 Excel 也要带登录头，所以不能直接塞进 img src。 */
export async function fetchAttachment(url: string): Promise<File> {
  const response = await fetch(url, { headers: authHeaders() });
  if (!response.ok) throw await failure(response);
  const blob = await response.blob();
  const name =
    filenameFromDisposition(response.headers.get('content-disposition')) ||
    'download';
  return new File([blob], name, { type: blob.type || 'application/octet-stream' });
}

/**
 * 执行进度。只用来显示「在做什么」，数据一律走 blocks。
 * label 是后端给的人话名字（工具自带的 description 是写给模型的，太长）。
 *
 * kind='phase' 是能力内部的阶段（取数、写原因、出表），挂在 parent 那个工具下面。
 * 慢阶段会用 state='update' 边跑边报条数。
 */
export interface AgentProgress {
  /** 已写条数，配 total 看。 */
  done?: number;
  /** 进行中那句，例如「数据分析师正在汇总消耗数据」。 */
  doing?: string;
  elapsed_ms?: number;
  error?: null | string;
  kind: 'llm' | 'phase' | 'tool';
  /** 做完之后那句，例如「汇总消耗数据」。 */
  label?: string;
  name?: string;
  /** 阶段所属的工具名。 */
  parent?: string;
  state: 'done' | 'error' | 'start' | 'update';
  step?: number;
  total?: number;
}

export interface StreamHandlers {
  onBlocks: (blocks: AgentBlock[]) => void;
  onDone?: (conversationId: string) => void;
  onProgress?: (step: AgentProgress) => void;
}

function dispatchEvent(raw: string, handlers: StreamHandlers) {
  let event = 'message';
  const data: string[] = [];
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).trim());
  }
  if (data.length === 0) return;
  let parsed: any;
  try {
    parsed = JSON.parse(data.join('\n'));
  } catch {
    return;
  }
  if (event === 'blocks' && Array.isArray(parsed?.blocks)) {
    handlers.onBlocks(parsed.blocks);
  } else if (event === 'progress' && parsed?.kind) {
    handlers.onProgress?.(parsed as AgentProgress);
  } else if (event === 'done') {
    handlers.onDone?.(parsed?.conversation_id ?? '');
  }
}

async function readStream(response: Response, handlers: StreamHandlers): Promise<void> {
  if (!response.body) throw new AgentRequestError('浏览器不支持流式响应。', 0);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let split = buffer.indexOf('\n\n');
    while (split >= 0) {
      dispatchEvent(buffer.slice(0, split), handlers);
      buffer = buffer.slice(split + 2);
      split = buffer.indexOf('\n\n');
    }
  }
  if (buffer.trim()) dispatchEvent(buffer, handlers);
}

async function stream(
  path: string,
  body: Record<string, unknown>,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${BASE}${path}`, {
    body: JSON.stringify(body),
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    method: 'POST',
    signal,
  });
  if (!response.ok) throw await failure(response);
  await readStream(response, handlers);
}

export function streamFollow(
  conversationId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return fetch(`${BASE}/v1/conversations/${conversationId}/stream`, {
    headers: authHeaders(),
    method: 'GET',
    signal,
  }).then(async (response) => {
    if (!response.ok) throw await failure(response);
    await readStream(response, handlers);
  });
}

export interface AgentUpload {
  file_id: string;
  filename: string;
  kind: string;
  size: number;
  url: string;
}

export async function uploadAgentFile(file: File): Promise<AgentUpload> {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch(`${BASE}/v1/uploads`, {
    body,
    headers: authHeaders(),
    method: 'POST',
  });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as AgentUpload;
}

export function streamChat(
  params: { conversationId: string; fileIds?: string[]; text: string },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return stream(
    '/v1/chat',
    {
      conversation_id: params.conversationId,
      file_ids: params.fileIds ?? [],
      text: params.text,
    },
    handlers,
    signal,
  );
}

export function streamChoice(
  params: { conversationId: string; optionId: string },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return stream(
    '/v1/choice',
    { conversation_id: params.conversationId, option_id: params.optionId },
    handlers,
    signal,
  );
}

export function streamConfirm(
  params: { accept: boolean; conversationId: string; previewId: string },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return stream(
    '/v1/confirm',
    {
      accept: params.accept,
      conversation_id: params.conversationId,
      preview_id: params.previewId,
    },
    handlers,
    signal,
  );
}
