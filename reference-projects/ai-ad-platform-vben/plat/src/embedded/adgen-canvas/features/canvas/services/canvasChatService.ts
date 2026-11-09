import { authService } from '../../../services/authService';
import { API_BASE_URL } from '../../../services/runtimeConfig';
import { readCanvasModelApiResponse } from '../../../../../api/canvas-model-response';

const CHAT_API_URL = `${API_BASE_URL}/canvas-chat`;

export type CanvasChatRole = 'user' | 'assistant';
export type CanvasChatContextScope =
  | 'selected_node'
  | 'whole_canvas'
  | 'screenshot'
  | 'reference_images';

export interface CanvasChatReferenceImage {
  name: string;
  data_url: string;
}

export interface CanvasChatGenerationModel {
  id: string;
  label: string;
  /** Database-backed aliases are supplied to the chat model for recognition.
   * Only `id` may be returned as the generation target. */
  aliases?: string[];
  isDefault?: boolean;
  type: 'image' | 'video';
  resolutions: string[];
  aspectRatios: string[];
  durationRangeSeconds?: number[];
  maxCount: number;
}

export interface CanvasChatConversation {
  conversation_id: string;
  canvas_id: string;
  title: string;
  summary?: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface CanvasChatMessage {
  message_id: string;
  conversation_id: string;
  role: CanvasChatRole;
  content: string;
  context_scope?: CanvasChatContextScope | 'none';
  context_label?: string;
  created_at: string;
}

export interface CanvasChatContextPayload {
  scope: CanvasChatContextScope;
  label: string;
  snapshot: unknown;
  screenshot_data_url?: string;
  reference_images?: CanvasChatReferenceImage[];
}

export interface CanvasChatStatus {
  configured: boolean;
  key_configured: boolean;
  provider: string;
  provider_label: string;
  model: string;
  supported_providers: Record<string, string>;
}

export interface CanvasChatConfig {
  baseUrl: string;
  keyConfigured: boolean;
  keyMasked: string;
  model: string;
  provider: string;
}

export interface SaveCanvasChatConfigPayload {
  baseUrl: string;
  model: string;
  provider: string;
}

const authHeaders = (json = false): Record<string, string> => {
  const headers: Record<string, string> = {};
  const token = authService.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (json) headers['Content-Type'] = 'application/json';
  return headers;
};

export const getCanvasChatStatus = async (): Promise<CanvasChatStatus> => {
  const response = await fetch(`${CHAT_API_URL}/status`, {
    headers: authHeaders(),
  });
  return readCanvasModelApiResponse<CanvasChatStatus>(response);
};

export const getCanvasChatConfig = async (): Promise<CanvasChatConfig> => {
  const response = await fetch(`${CHAT_API_URL}/config`, {
    headers: authHeaders(),
  });
  const data = await readCanvasModelApiResponse<{ config: CanvasChatConfig }>(
    response,
  );
  return data.config;
};

export const saveCanvasChatConfig = async (
  payload: SaveCanvasChatConfigPayload,
): Promise<{ config: CanvasChatConfig; configured: boolean }> => {
  const response = await fetch(`${CHAT_API_URL}/config`, {
    method: 'PUT',
    headers: authHeaders(true),
    body: JSON.stringify(payload),
  });
  return readCanvasModelApiResponse(response);
};

export const listCanvasChatConversations = async (
  canvasId: string,
): Promise<CanvasChatConversation[]> => {
  const response = await fetch(
    `${CHAT_API_URL}/conversations?canvas_id=${encodeURIComponent(canvasId)}`,
    { headers: authHeaders() },
  );
  const data = await readCanvasModelApiResponse<{
    conversations: CanvasChatConversation[];
  }>(response);
  return data.conversations || [];
};

export const createCanvasChatConversation = async (
  canvasId: string,
  title = '新对话',
): Promise<CanvasChatConversation> => {
  const response = await fetch(`${CHAT_API_URL}/conversations`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({ canvas_id: canvasId, title }),
  });
  const data = await readCanvasModelApiResponse<{
    conversation: CanvasChatConversation;
  }>(response);
  return data.conversation;
};

export const listCanvasChatMessages = async (
  conversationId: string,
): Promise<{
  conversation: CanvasChatConversation;
  messages: CanvasChatMessage[];
}> => {
  const response = await fetch(
    `${CHAT_API_URL}/conversations/${conversationId}/messages`,
    {
      headers: authHeaders(),
    },
  );
  return readCanvasModelApiResponse(response);
};

export const deleteCanvasChatConversation = async (
  conversationId: string,
): Promise<void> => {
  const response = await fetch(
    `${CHAT_API_URL}/conversations/${conversationId}`,
    {
      method: 'DELETE',
      headers: authHeaders(),
    },
  );
  await readCanvasModelApiResponse(response);
};

/**
 * Ask the configured canvas chat model to map an unmatched display name to a
 * database-backed generation model ID. The backend validates the answer
 * against `generationModels` before returning it.
 */
export const resolveCanvasChatGenerationModel = async (
  type: 'image' | 'video',
  requestedModel: string,
  generationModels: CanvasChatGenerationModel[],
): Promise<string> => {
  const response = await fetch(`${CHAT_API_URL}/resolve-generation-model`, {
    method: 'POST',
    headers: authHeaders(true),
    body: JSON.stringify({
      type,
      requested_model: requestedModel,
      generation_models: generationModels,
    }),
  });
  const data = await readCanvasModelApiResponse<{ model_id: string }>(response);
  if (!data.model_id) throw new Error('对话模型未能匹配到数据库中可用的生成模型');
  return data.model_id;
};

interface StreamCallbacks {
  onStart?: () => void;
  onUserSaved?: (message: CanvasChatMessage) => void;
  onChunk?: (text: string) => void;
  onDone?: (message: CanvasChatMessage) => void;
}

export const streamCanvasChatMessage = async (
  conversationId: string,
  message: string,
  context: CanvasChatContextPayload | null,
  generationModels: CanvasChatGenerationModel[],
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> => {
  const body: Record<string, unknown> = {
    message,
    generation_models: generationModels,
  };
  // Deliberately omit canvas_context for ordinary chat.
  if (context) body.canvas_context = context;

  const response = await fetch(
    `${CHAT_API_URL}/conversations/${conversationId}/stream`,
    {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify(body),
      signal,
    },
  );
  const responseType = response.headers.get('content-type') || '';
  if (responseType.includes('application/json')) {
    await readCanvasModelApiResponse(response);
    throw new Error('对话接口未返回事件流');
  }
  if (!response.ok) {
    throw new Error('网络异常或服务不可用，请稍后重试');
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error('无法读取对话响应');

  const decoder = new TextDecoder();
  let buffer = '';
  const handleBlock = (block: string) => {
    let eventName = '';
    let dataText = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      if (line.startsWith('data:')) dataText += line.slice(5).trim();
    }
    if (!dataText) return;
    const data = JSON.parse(dataText);
    if (eventName === 'start') callbacks.onStart?.();
    else if (eventName === 'user_saved') callbacks.onUserSaved?.(data.message);
    else if (eventName === 'chunk') callbacks.onChunk?.(data.text || '');
    else if (eventName === 'done') callbacks.onDone?.(data.message);
    else if (eventName === 'error')
      throw new Error(data.error || '对话生成失败');
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() || '';
    for (const block of blocks) handleBlock(block);
  }
  if (buffer.trim()) handleBlock(buffer);
};
