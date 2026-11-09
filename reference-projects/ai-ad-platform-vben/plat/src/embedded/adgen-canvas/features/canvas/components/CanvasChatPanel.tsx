/** @jsxImportSource react */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Bot,
  Box,
  Check,
  ChevronDown,
  Image as ImageIcon,
  Loader2,
  MessageSquareText,
  Paperclip,
  Plus,
  Send,
  Sparkles,
  User,
  Workflow,
  X,
} from 'lucide-react';
import {
  createCanvasChatConversation,
  getCanvasChatConfig,
  getCanvasChatStatus,
  listCanvasChatConversations,
  listCanvasChatMessages,
  saveCanvasChatConfig,
  streamCanvasChatMessage,
  type CanvasChatConfig,
  type CanvasChatContextPayload,
  type CanvasChatContextScope,
  type CanvasChatConversation,
  type CanvasChatGenerationModel,
  type CanvasChatMessage,
  type CanvasChatReferenceImage,
  type CanvasChatStatus,
} from '../services/canvasChatService';

export interface CanvasChatAttachRequest {
  nonce: number;
  scope: CanvasChatContextScope;
  label: string;
  thumbnails?: Array<{
    id: string;
    title: string;
    url?: string;
    kind: string;
  }>;
}

interface CanvasChatImageAttachment {
  file: File;
  id: string;
  name: string;
  previewUrl: string;
}

export type CanvasChatMediaType = 'image' | 'video';

export interface CanvasChatGenerationRequest {
  prompt: string;
  model?: string;
  mediaType?: CanvasChatMediaType;
  useRecentSettings?: boolean;
  aspectRatio?: string;
  resolution?: string;
  duration?: number;
  count?: number;
}

const CHINESE_BATCH_COUNT: Record<string, number> = {
  一: 1,
  二: 2,
  两: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
  十: 10,
};

/**
 * Only accepts an explicit generation request. That prevents a phrase such
 * as "I uploaded two images" from accidentally becoming a batch request.
 */
const inferRequestedBatchCount = (
  userMessage: string | undefined,
  type: CanvasChatMediaType,
): number | undefined => {
  const source = String(userMessage || '').replace(/\s+/g, ' ').trim();
  if (!source) return undefined;

  const unit =
    type === 'image'
      ? '(?:张|幅)(?:图片|图像|图)?'
      : '(?:条|段|个)(?:视频|短片|片段)?';
  const verbalPattern = new RegExp(
    `(?:生成|输出|给我|来|做|制作|创建|画出?|要|需要|想要|请)[^。；;，,]{0,14}?(\\d{1,2}|[一二两三四五六七八九十])\\s*${unit}`,
    'i',
  );
  const englishPattern = new RegExp(
    `(?:generate|create|make|output)\\s+(\\d{1,2})\\s+${
      type === 'image' ? '(?:images?|pictures?)' : '(?:videos?|clips?)'
    }`,
    'i',
  );
  const matched = source.match(verbalPattern) || source.match(englishPattern);
  if (!matched?.[1]) return undefined;

  const rawCount = matched[1];
  const count = /^\d+$/.test(rawCount)
    ? Number(rawCount)
    : CHINESE_BATCH_COUNT[rawCount];
  return Number.isInteger(count) && count > 0 ? count : undefined;
};

interface CanvasChatPanelProps {
  canvasId: string;
  canvasTitle: string;
  enabledModelIds: string[];
  generationModels: CanvasChatGenerationModel[];
  hasSelectedNode: boolean;
  theme: 'light' | 'dark';
  attachRequest?: CanvasChatAttachRequest | null;
  onClose: () => void;
  buildContext: (
    scope: CanvasChatContextScope,
  ) => Promise<CanvasChatContextPayload>;
  onGenerateMedia: (
    type: CanvasChatMediaType,
    requests: CanvasChatGenerationRequest[],
  ) => Promise<void>;
}

const CONTEXT_OPTIONS: Array<{
  scope: CanvasChatContextScope;
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}> = [
  {
    scope: 'selected_node',
    label: '当前节点',
    description: '仅分析当前选中的节点',
    icon: Box,
  },
  {
    scope: 'whole_canvas',
    label: '整个画布',
    description: '读取节点、参数和连线顺序',
    icon: Workflow,
  },
  {
    scope: 'screenshot',
    label: '页面截图',
    description: '发送当前可见画布截图',
    icon: ImageIcon,
  },
];

type ChatModelProvider = 'gemini_proxy' | 'qwen';

interface ChatModelOption {
  value: string;
  label: string;
  description: string;
  provider: ChatModelProvider;
  baseUrl: string;
}

const DASHSCOPE_BASE_URL =
  'https://dashscope.aliyuncs.com/compatible-mode/v1';

const CHAT_MODEL_GROUPS: Array<{
  label: string;
  options: ChatModelOption[];
}> = [
  {
    label: 'Gemini 代理',
    options: [
      {
        value: 'gemini-3-flash-preview',
        label: 'Gemini 3 Flash（快速）',
        description: '响应更快，适合日常问答',
        provider: 'gemini_proxy',
        baseUrl: '',
      },
      {
        value: 'gemini-3.1-pro-preview',
        label: 'Gemini 3.1 Pro（高质量）',
        description: '理解更稳，适合复杂画布分析',
        provider: 'gemini_proxy',
        baseUrl: '',
      },
    ],
  },
  {
    label: '通义千问',
    options: [
      {
        value: 'qwen-vl-plus',
        label: 'Qwen VL Plus（推荐）',
        description: '识图与长对话更均衡',
        provider: 'qwen',
        baseUrl: DASHSCOPE_BASE_URL,
      },
      {
        value: 'qwen-vl-max',
        label: 'Qwen VL Max',
        description: '更强视觉理解',
        provider: 'qwen',
        baseUrl: DASHSCOPE_BASE_URL,
      },
      {
        value: 'qwen-plus',
        label: 'Qwen Plus',
        description: '文本对话更快',
        provider: 'qwen',
        baseUrl: DASHSCOPE_BASE_URL,
      },
      {
        value: 'qwen-max',
        label: 'Qwen Max',
        description: '更高质量文本',
        provider: 'qwen',
        baseUrl: DASHSCOPE_BASE_URL,
      },
    ],
  },
];

const CHAT_MODEL_OPTIONS = CHAT_MODEL_GROUPS.flatMap(
  (group) => group.options,
);

const getChatModelOption = (model: string) =>
  CHAT_MODEL_OPTIONS.find((option) => option.value === model);

const getMissingCredentialMessage = (provider: string) =>
  provider === 'qwen'
    ? '模型已保存；请在 AdGen模型与运维 → 凭据池 → 百炼 中添加 API Key'
    : '模型已保存；请为本地后端配置画布对话 Gemini 独立密钥';

const formatTime = (value?: string) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const MAX_REFERENCE_IMAGE_COUNT = 4;
const MAX_REFERENCE_IMAGE_BYTES = 5 * 1024 * 1024;

// Keep image creation available through normal canvas image nodes, but do not
// expose or trigger it from the conversation assistant until it is reopened.
const ENABLE_CHAT_IMAGE_GENERATION = false;

const normalizeGenerationModelName = (value: unknown) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/(\d+)\.0(?=$|[^\d])/g, '$1')
    // The assistant can wrap an ID with Markdown `code` or **bold** markup.
    // Retain letters, numerals and Chinese model labels only.
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, '');

const matchGenerationModelLocally = (
  requestedModel: string,
  type: CanvasChatMediaType,
  generationModels: CanvasChatGenerationModel[],
) => {
  const normalizedRequested = normalizeGenerationModelName(requestedModel);
  if (!normalizedRequested) return undefined;
  return generationModels.find((model) =>
    model.type === type &&
    [model.id, model.label, ...(model.aliases || [])]
      .some(
        (candidate) =>
          normalizeGenerationModelName(candidate) === normalizedRequested,
      ),
  );
};

const parseMediaType = (value: unknown): CanvasChatMediaType | undefined => {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'image' || normalized === '图片' || normalized === '图像')
    return 'image';
  if (normalized === 'video' || normalized === '视频') return 'video';
  return undefined;
};

const inferGenerationMediaType = (
  request: CanvasChatGenerationRequest,
  sourceUserMessage: string | undefined,
  generationModels: CanvasChatGenerationModel[],
): CanvasChatMediaType | undefined => {
  if (request.mediaType) return request.mediaType;
  if (request.model) {
    const matched = generationModels.find((model) =>
      [model.id, model.label, ...(model.aliases || [])].some(
        (candidate) =>
          normalizeGenerationModelName(candidate) ===
          normalizeGenerationModelName(request.model),
      ),
    );
    if (matched) return matched.type;
  }
  if (request.duration) return 'video';
  const intent = `${sourceUserMessage || ''}\n${request.prompt}`.toLowerCase();
  if (/(?:视频|短片|片段|动画|video|veo|seedance|kling|可灵|万相)/i.test(intent))
    return 'video';
  if (/(?:图片|图像|海报|插画|image|gpt.?image|nano.?banana|seedream)/i.test(intent))
    return 'image';
  return undefined;
};

const hasCompleteGenerationRecipe = (value: string) =>
  /【生成模型】\s*[^\n【]+/u.test(value) &&
  /【生成描述】\s*\S/u.test(value);

const fileToDataUrl = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`无法读取图片“${file.name}”`));
    reader.onload = () => {
      if (typeof reader.result === 'string') resolve(reader.result);
      else reject(new Error(`无法读取图片“${file.name}”`));
    };
    reader.readAsDataURL(file);
  });

const CanvasChatPanel: React.FC<CanvasChatPanelProps> = ({
  canvasId,
  canvasTitle,
  enabledModelIds,
  generationModels,
  hasSelectedNode,
  theme,
  attachRequest = null,
  onClose,
  buildContext,
  onGenerateMedia,
}) => {
  const [status, setStatus] = useState<CanvasChatStatus | null>(null);
  const [conversations, setConversations] = useState<CanvasChatConversation[]>(
    [],
  );
  const [activeConversationId, setActiveConversationId] = useState('');
  const [messages, setMessages] = useState<CanvasChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [contextScope, setContextScope] =
    useState<CanvasChatContextScope | null>(() => attachRequest?.scope ?? null);
  const [attachedPreview, setAttachedPreview] = useState<{
    label: string;
    thumbnails: NonNullable<CanvasChatAttachRequest['thumbnails']>;
  } | null>(() => (
    attachRequest
      ? { label: attachRequest.label, thumbnails: attachRequest.thumbnails || [] }
      : null
  ));
  const [contextMenuOpen, setContextMenuOpen] = useState(false);
  const [conversationMenuOpen, setConversationMenuOpen] = useState(false);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [modelGroupTab, setModelGroupTab] = useState<ChatModelProvider>('qwen');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [mediaGenerating, setMediaGenerating] = useState<
    CanvasChatMediaType | null
  >(null);
  const [pendingAutoGeneration, setPendingAutoGeneration] = useState<{
    assistantReply: string;
    sourceUserMessage: string;
  } | null>(null);
  const [imageAttachments, setImageAttachments] = useState<
    CanvasChatImageAttachment[]
  >([]);
  const [chatConfig, setChatConfig] = useState<CanvasChatConfig>({
    baseUrl: DASHSCOPE_BASE_URL,
    keyConfigured: false,
    keyMasked: '',
    model: 'qwen-vl-plus',
    provider: 'qwen',
  });
  const endRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const imageAttachmentsRef = useRef<CanvasChatImageAttachment[]>([]);
  const conversationMenuRef = useRef<HTMLDivElement | null>(null);
  const modelMenuRef = useRef<HTMLDivElement | null>(null);

  const isDark = theme === 'dark';
  const availableChatModelGroups = useMemo(() => {
    const enabled = new Set(enabledModelIds);
    return CHAT_MODEL_GROUPS
      .map((group) => ({
        ...group,
        options: group.options.filter((option) => enabled.has(option.value)),
      }))
      .filter((group) => group.options.length > 0);
  }, [enabledModelIds]);
  const selectedChatModel = getChatModelOption(chatConfig.model)
    || availableChatModelGroups[0]?.options[0]
    || CHAT_MODEL_OPTIONS[0];
  const activeModelGroup = availableChatModelGroups.find((group) => (
    group.options.some((option) => option.provider === modelGroupTab)
  )) || availableChatModelGroups[0];
  const selectedContext = CONTEXT_OPTIONS.find(
    (option) => option.scope === contextScope,
  );
  const chatGenerationModels = useMemo(
    () =>
      ENABLE_CHAT_IMAGE_GENERATION
        ? generationModels
        : generationModels.filter((model) => model.type !== 'image'),
    [generationModels],
  );
  const attachedLabel = attachedPreview?.label || selectedContext?.label || '';

  useEffect(() => {
    imageAttachmentsRef.current = imageAttachments;
  }, [imageAttachments]);

  useEffect(
    () => () => {
      imageAttachmentsRef.current.forEach((attachment) => {
        URL.revokeObjectURL(attachment.previewUrl);
      });
    },
    [],
  );

  useEffect(() => {
    if (!attachRequest?.nonce) return;
    setContextScope(attachRequest.scope);
    setAttachedPreview({
      label: attachRequest.label,
      thumbnails: attachRequest.thumbnails || [],
    });
    setContextMenuOpen(false);
    setModelMenuOpen(false);
  }, [attachRequest]);
  const activeConversation = conversations.find(
    (conversation) => conversation.conversation_id === activeConversationId,
  );

  const openModelMenu = async () => {
    const nextOpen = !modelMenuOpen;
    setContextMenuOpen(false);
    setConversationMenuOpen(false);
    setModelMenuOpen(nextOpen);
    if (!nextOpen) return;
    setModelGroupTab(chatConfig.provider);
    setConfigLoading(true);
    setError('');
    try {
      const nextConfig = await getCanvasChatConfig();
      setChatConfig(nextConfig);
      setModelGroupTab(nextConfig.provider);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '模型配置加载失败');
    } finally {
      setConfigLoading(false);
    }
  };

  const selectChatModel = async (option: ChatModelOption) => {
    if (configSaving || option.value === chatConfig.model) {
      setModelMenuOpen(false);
      return;
    }
    setChatConfig((current) => ({
      ...current,
      model: option.value,
      provider: option.provider,
      baseUrl: option.baseUrl,
    }));
    setConfigSaving(true);
    setError('');
    try {
      const result = await saveCanvasChatConfig({
        baseUrl: option.baseUrl,
        model: option.value,
        provider: option.provider,
      });
      setChatConfig(result.config);
      const nextStatus = await getCanvasChatStatus();
      setStatus(nextStatus);
      setModelMenuOpen(false);
      if (!nextStatus.configured) {
        setError(getMissingCredentialMessage(option.provider));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '模型配置保存失败');
    } finally {
      setConfigSaving(false);
    }
  };

  const loadMessages = useCallback(async (conversationId: string) => {
    const result = await listCanvasChatMessages(conversationId);
    setMessages(result.messages);
    setConversations((current) =>
      current.map((item) =>
        item.conversation_id === result.conversation.conversation_id
          ? result.conversation
          : item,
      ),
    );
  }, []);

  const createConversation = useCallback(async () => {
    const created = await createCanvasChatConversation(canvasId, '新对话');
    setConversations((current) => [created, ...current]);
    setActiveConversationId(created.conversation_id);
    setMessages([]);
    setError('');
    return created;
  }, [canvasId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getCanvasChatStatus(),
      listCanvasChatConversations(canvasId),
      getCanvasChatConfig(),
    ])
      .then(async ([nextStatus, items, nextConfig]) => {
        if (cancelled) return;
        setStatus(nextStatus);
        setChatConfig(nextConfig);
        setModelGroupTab(nextConfig.provider);
        let nextItems = items;
        if (nextItems.length === 0) {
          const created = await createCanvasChatConversation(
            canvasId,
            '新对话',
          );
          nextItems = [created];
        }
        if (cancelled) return;
        const firstConversation = nextItems[0];
        if (!firstConversation) return;
        setConversations(nextItems);
        setActiveConversationId(firstConversation.conversation_id);
        const result = await listCanvasChatMessages(
          firstConversation.conversation_id,
        );
        if (!cancelled) setMessages(result.messages);
      })
      .catch((reason) => {
        if (!cancelled)
          setError(reason instanceof Error ? reason.message : '对话加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [canvasId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: sending ? 'auto' : 'smooth' });
  }, [messages, sending]);

  useEffect(() => {
    if (!conversationMenuOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!conversationMenuRef.current?.contains(event.target as Node)) {
        setConversationMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [conversationMenuOpen]);

  useEffect(() => {
    if (!modelMenuOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (!modelMenuRef.current?.contains(event.target as Node)) {
        setModelMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => document.removeEventListener('pointerdown', handlePointerDown);
  }, [modelMenuOpen]);

  const handleConversationChange = async (conversationId: string) => {
    setConversationMenuOpen(false);
    if (!conversationId || conversationId === activeConversationId || sending)
      return;
    setActiveConversationId(conversationId);
    setLoading(true);
    setError('');
    try {
      await loadMessages(conversationId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '对话加载失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async () => {
    const content = input.trim();
    if (!content || sending) return;
    if (!status?.configured) {
      setError('对话模型尚未配置。配置供应商、模型与独立聊天密钥后即可发送。');
      return;
    }

    setSending(true);
    setError('');
    let conversationId = activeConversationId;
    try {
      if (!conversationId)
        conversationId = (await createConversation()).conversation_id;
      const selectedContextPayload = contextScope
        ? await buildContext(contextScope)
        : null;
      const sentAttachments = imageAttachmentsRef.current;
      const referenceImages: CanvasChatReferenceImage[] = await Promise.all(
        sentAttachments.map(async (attachment) => ({
          name: attachment.name,
          data_url: await fileToDataUrl(attachment.file),
        })),
      );
      const context: CanvasChatContextPayload | null = referenceImages.length
        ? {
            scope: selectedContextPayload?.scope || 'reference_images',
            label: selectedContextPayload
              ? `${selectedContextPayload.label} · ${referenceImages.length}张参考图片`
              : `参考图片（${referenceImages.length}张）`,
            snapshot:
              selectedContextPayload?.snapshot || {
                reference_images: referenceImages.map((image) => image.name),
              },
            screenshot_data_url: selectedContextPayload?.screenshot_data_url,
            reference_images: referenceImages,
          }
        : selectedContextPayload;
      setContextScope(null);
      setAttachedPreview(null);
      setContextMenuOpen(false);
      setInput('');

      const now = new Date().toISOString();
      const optimisticUserId = `pending-user-${Date.now()}`;
      const optimisticAssistantId = `pending-assistant-${Date.now()}`;
      setMessages((current) => [
        ...current,
        {
          message_id: optimisticUserId,
          conversation_id: conversationId,
          role: 'user',
          content,
          context_scope: context?.scope || 'none',
          context_label: context?.label || '',
          created_at: now,
        },
        {
          message_id: optimisticAssistantId,
          conversation_id: conversationId,
          role: 'assistant',
          content: '',
          created_at: now,
        },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      await streamCanvasChatMessage(
        conversationId,
        content,
        context,
        chatGenerationModels,
        {
          onUserSaved: (saved) =>
            setMessages((current) =>
              current.map((message) =>
                message.message_id === optimisticUserId ? saved : message,
              ),
            ),
          onChunk: (text) =>
            setMessages((current) =>
              current.map((message) =>
                message.message_id === optimisticAssistantId
                  ? { ...message, content: message.content + text }
                  : message,
              ),
            ),
          onDone: (saved) => {
            setMessages((current) =>
              current.map((message) =>
                message.message_id === optimisticAssistantId ? saved : message,
              ),
            );
            // Paid media creation is intentionally deferred until the stream
            // ends. Model and description make an explicit generation recipe;
            // missing parameters deliberately fall back to saved canvas settings.
            if (
              hasCompleteGenerationRecipe(saved.content || '') &&
              (ENABLE_CHAT_IMAGE_GENERATION ||
                /【生成类型】\s*视频/u.test(saved.content || ''))
            ) {
              setPendingAutoGeneration({
                assistantReply: saved.content,
                sourceUserMessage: content,
              });
            }
          },
        },
        controller.signal,
      );
      const refreshed = await listCanvasChatConversations(canvasId);
      setConversations(refreshed);
      sentAttachments.forEach((attachment) => {
        URL.revokeObjectURL(attachment.previewUrl);
      });
      setImageAttachments([]);
    } catch (reason) {
      setMessages((current) =>
        current.filter(
          (message) => !message.message_id.startsWith('pending-assistant-'),
        ),
      );
      setError(
        reason instanceof Error ? reason.message : '发送失败，请稍后重试',
      );
    } finally {
      abortRef.current = null;
      setSending(false);
    }
  };

  const removeImageAttachment = (attachmentId: string) => {
    const removed = imageAttachmentsRef.current.find(
      (item) => item.id === attachmentId,
    );
    if (removed) URL.revokeObjectURL(removed.previewUrl);
    setImageAttachments((current) =>
      current.filter((item) => item.id !== attachmentId),
    );
  };

  const handleImageAttachmentChange = (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    const images = files.filter((file) => file.type.startsWith('image/'));
    if (images.length === 0) return;

    const acceptedImages = images.filter(
      (file) => file.size <= MAX_REFERENCE_IMAGE_BYTES,
    );
    if (acceptedImages.length !== images.length) {
      setError('单张参考图片不能超过 5 MB');
    }
    const available = Math.max(
      0,
      MAX_REFERENCE_IMAGE_COUNT - imageAttachmentsRef.current.length,
    );
    if (available === 0) {
      setError(`最多可添加 ${MAX_REFERENCE_IMAGE_COUNT} 张参考图片`);
      return;
    }
    const accepted = acceptedImages.slice(0, available).map((file) => ({
      file,
      id:
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: file.name || '参考图片',
      previewUrl: URL.createObjectURL(file),
    }));
    if (acceptedImages.length > available)
      setError(`最多可添加 ${MAX_REFERENCE_IMAGE_COUNT} 张参考图片`);
    setImageAttachments((current) => [...current, ...accepted]);
  };

  const getGenerationRequest = (
    assistantReply: string,
  ): CanvasChatGenerationRequest => {
    const matched = assistantReply.match(
      /【生成描述】\s*([\s\S]*?)(?=\n\s*【[^】]+】|$)/,
    );
    const parameterMatch =
      assistantReply.match(
        /【生成参数】\s*```(?:json)?\s*([\s\S]*?)```/i,
      ) ||
      assistantReply.match(
        /【生成参数】\s*(\{[\s\S]*?\})(?=\s*\n\s*【[^】]+】|$)/,
      );
    let parameters: Record<string, unknown> = {};
    if (parameterMatch?.[1]) {
      try {
        const parsed = JSON.parse(parameterMatch[1]);
        if (parsed && typeof parsed === 'object') {
          parameters = parsed as Record<string, unknown>;
        }
      } catch {
        // A readable assistant response remains usable even if its metadata is malformed.
      }
    }
    const modelMatch = assistantReply.match(/【生成模型】\s*([^\n【]+)/);
    const mediaTypeMatch = assistantReply.match(/【生成类型】\s*([^\n【]+)/);
    const textValue = (value: unknown) =>
      typeof value === 'string' && value.trim() ? value.trim() : undefined;
    const numberValue = (value: unknown) => {
      const parsed = Number(value);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
    };
    const aspectRatio =
      textValue(parameters.aspectRatio) || textValue(parameters.aspect_ratio);
    const resolution = textValue(parameters.resolution);
    const count = numberValue(parameters.count);
    const duration = numberValue(parameters.duration);
    const mediaType =
      parseMediaType(mediaTypeMatch?.[1]) || parseMediaType(parameters.type);
    return {
      prompt: (matched?.[1] || assistantReply).trim(),
      model:
        modelMatch?.[1]?.trim().replace(/[；;，,。.]$/u, '') ||
        textValue(parameters.model),
      mediaType,
      // A partial recipe is still an explicit generation request. Reuse the
      // settings last saved in the canvas rather than guessing a mixture of
      // old and new values.
      useRecentSettings:
        !aspectRatio || !resolution || !count || (mediaType === 'video' && !duration),
      aspectRatio,
      resolution,
      duration,
      count,
    };
  };

  const getGenerationRequests = (
    assistantReply: string,
  ): CanvasChatGenerationRequest[] => {
    // A reply may contain separate recipes such as “风格一 / 风格二”. Each
    // model block must become its own canvas task; sending their text together
    // makes an image model compose both styles into one picture.
    const sections = assistantReply.includes('【生成类型】')
      ? assistantReply
          .split(/(?=【生成类型】)/u)
          .filter((section) => section.includes('【生成模型】'))
      : assistantReply
          .split(/(?=【生成模型】)/u)
          .filter((section) => section.includes('【生成模型】'));
    const candidates = sections.length > 0 ? sections : [assistantReply];
    const unique = new Set<string>();
    return candidates
      .map((section) => {
        const request = getGenerationRequest(section);
        const prompt = request.prompt
          // The following style heading belongs to the next model block, not
          // to this model's prompt.
          .replace(
            /(?:\r?\n|^)\s*(?:[-—–_]{2,}\s*)?\*{0,2}\s*(?:风格|方案|版本)\s*[一二两三四五六七八九十\d]+\s*(?:[：:][^\r\n]*)?\s*\*{0,2}\s*$/u,
            '',
          )
          .trim();
        return { ...request, prompt };
      })
      .filter((request) => {
        if (!request.prompt) return false;
        const key = [
          request.model || '',
          request.aspectRatio || '',
          request.resolution || '',
          request.duration || '',
          request.count || '',
          request.prompt,
        ].join('|');
        if (unique.has(key)) return false;
        unique.add(key);
        return true;
      });
  };

  const generateMediaRequests = async (
    type: CanvasChatMediaType,
    requests: CanvasChatGenerationRequest[],
    sourceUserMessage?: string,
  ) => {
    if (!generationModels.some((model) => model.type === type)) {
      setError(
        `数据库${type === 'image' ? '图片' : '视频'}模型配置尚未加载，请稍候重试`,
      );
      return;
    }
    if (requests.length === 0 || mediaGenerating || sending) return;
    // The source user request is authoritative for batch count. This stops a
    // chat reply from turning "generate two images" into a single prompt that
    // asks the provider to draw a two-up composite.
    const requestedCount = inferRequestedBatchCount(sourceUserMessage, type);
    const requestsWithUserCount =
      requests.length === 1 && requestedCount
        ? [{ ...requests[0], count: requestedCount }]
        : requests;
    setError('');
    setMediaGenerating(type);
    try {
      const resolvedRequests: CanvasChatGenerationRequest[] = [];
      for (const request of requestsWithUserCount) {
        let resolvedRequest = request;
        if (request.model) {
          const localMatch = matchGenerationModelLocally(
            request.model,
            type,
            generationModels,
          );
          if (localMatch) {
            resolvedRequest = { ...request, model: localMatch.id };
          } else {
            throw new Error(
              `对话中指定的模型“${request.model}”未在数据库当前已启用的${
                type === 'image' ? '图片' : '视频'
              }模型列表中，未创建生成任务。`,
            );
          }
        }
        resolvedRequests.push(resolvedRequest);
      }
      await onGenerateMedia(type, resolvedRequests);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : '无法创建生成任务，请稍后重试',
      );
    } finally {
      setMediaGenerating(null);
    }
  };

  const generateMediaFromReply = async (
    assistantReply: string,
    sourceUserMessage: string,
  ) => {
    if (!hasCompleteGenerationRecipe(assistantReply)) return;
    const requests = getGenerationRequests(assistantReply);
    if (requests.length === 0) return;

    const grouped: Record<CanvasChatMediaType, CanvasChatGenerationRequest[]> = {
      image: [],
      video: [],
    };
    for (const request of requests) {
      const type = inferGenerationMediaType(
        request,
        sourceUserMessage,
        chatGenerationModels,
      );
      if (!type) {
        setError(
          '对话回复缺少可识别的生成类型；请让助手返回“【生成类型】图片”或“【生成类型】视频”后重试。',
        );
        return;
      }
      if (!ENABLE_CHAT_IMAGE_GENERATION && type === 'image') continue;
      grouped[type].push(
        type === 'video' && !request.duration
          ? { ...request, useRecentSettings: true }
          : request,
      );
    }

    // Images and videos are submitted in separate groups. Each style/version
    // remains an independent canvas node rather than being combined into one.
    for (const type of ['image', 'video'] as const) {
      if (grouped[type].length > 0) {
        await generateMediaRequests(type, grouped[type], sourceUserMessage);
      }
    }
  };

  useEffect(() => {
    if (!pendingAutoGeneration || sending || mediaGenerating) return;
    setPendingAutoGeneration(null);
    void generateMediaFromReply(
      pendingAutoGeneration.assistantReply,
      pendingAutoGeneration.sourceUserMessage,
    );
  }, [mediaGenerating, pendingAutoGeneration, sending]);

  return (
    <aside
      aria-label="画布助手对话"
      className={`absolute bottom-0 right-0 top-0 z-40 flex w-full flex-col shadow-[-18px_0_40px_rgba(15,23,42,0.08)] sm:w-[400px] ${
        isDark
          ? 'bg-[#111827] text-slate-100'
          : 'bg-white text-slate-900'
      }`}
    >
      <div
        className="flex h-[60px] shrink-0 items-center gap-2 px-3"
      >
        <div
          ref={conversationMenuRef}
          className="relative min-w-0 flex-1"
        >
          <button
            type="button"
            title="选择对话"
            role="combobox"
            aria-label="选择历史对话"
            aria-controls="canvas-chat-conversation-list"
            aria-expanded={conversationMenuOpen}
            disabled={sending}
            onClick={() => setConversationMenuOpen((open) => !open)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') setConversationMenuOpen(false);
            }}
            className={`flex h-10 w-full cursor-pointer items-center gap-2 rounded-xl px-3 text-left text-sm font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-violet-400 disabled:cursor-not-allowed disabled:opacity-50 ${
              isDark
                ? 'bg-slate-800 text-slate-100 hover:bg-slate-700'
                : 'bg-slate-50 text-slate-800 hover:bg-slate-100'
            }`}
          >
            <MessageSquareText
              size={15}
              className={isDark ? 'text-violet-300' : 'text-violet-600'}
            />
            <span className="min-w-0 flex-1 truncate">
              {activeConversation?.title || '新对话'}
            </span>
            <ChevronDown
              size={14}
              className={`shrink-0 opacity-50 transition-transform duration-200 ${conversationMenuOpen ? 'rotate-180' : ''}`}
            />
          </button>

          {conversationMenuOpen && (
            <div
              id="canvas-chat-conversation-list"
              role="listbox"
              aria-label="历史对话"
              className={`absolute left-0 right-0 top-12 z-[60] max-h-80 overflow-y-auto rounded-2xl p-1.5 shadow-[0_18px_48px_rgba(15,23,42,0.18)] ${
                isDark ? 'bg-slate-800' : 'bg-white'
              }`}
            >
              <div
                className={`px-3 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${
                  isDark ? 'text-slate-500' : 'text-slate-400'
                }`}
              >
                最近对话 · {conversations.length}
              </div>
              <div className="space-y-0.5">
                {conversations.map((conversation) => {
                  const selected =
                    conversation.conversation_id === activeConversationId;
                  return (
                    <button
                      key={conversation.conversation_id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      onClick={() =>
                        void handleConversationChange(
                          conversation.conversation_id,
                        )
                      }
                      className={`flex w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-violet-400 ${
                        selected
                          ? isDark
                            ? 'bg-violet-500/15 text-violet-200'
                            : 'bg-violet-50 text-violet-700'
                          : isDark
                            ? 'text-slate-200 hover:bg-slate-700'
                            : 'text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      <span
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${
                          selected
                            ? isDark
                              ? 'bg-violet-500/20 text-violet-300'
                              : 'bg-violet-100 text-violet-700'
                            : isDark
                              ? 'bg-slate-700 text-slate-400'
                              : 'bg-slate-100 text-slate-500'
                        }`}
                      >
                        <MessageSquareText size={14} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-semibold">
                          {conversation.title || '新对话'}
                        </span>
                        <span
                          className={`mt-0.5 block text-[10px] ${
                            selected
                              ? 'opacity-70'
                              : isDark
                                ? 'text-slate-500'
                                : 'text-slate-400'
                          }`}
                        >
                          {conversation.message_count} 条消息 ·{' '}
                          {formatTime(conversation.updated_at) || '刚刚'}
                        </span>
                      </span>
                      {selected && <Check size={15} className="shrink-0" />}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => {
            setConversationMenuOpen(false);
            void createConversation();
          }}
          aria-label="新建对话"
          title="新建对话"
          className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 ${isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-100'}`}
        >
          <Plus size={17} />
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭画布助手"
          className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 ${isDark ? 'hover:bg-slate-800' : 'hover:bg-slate-100'}`}
        >
          <X size={18} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
        {loading ? (
          <div
            className="flex h-full items-center justify-center"
            aria-label="正在加载对话"
          >
            <Loader2 size={22} className="animate-spin text-violet-500" />
          </div>
        ) : messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-5 text-center">
            <div
              className={`flex h-12 w-12 items-center justify-center rounded-2xl ${isDark ? 'bg-violet-500/15 text-violet-300' : 'bg-violet-50 text-violet-600'}`}
            >
              <Sparkles size={21} />
            </div>
            <h3 className="mt-4 text-sm font-semibold">
              {contextScope ? '已附加到本轮对话' : '开始一段长对话'}
            </h3>
            <p
              className={`mt-2 max-w-[280px] text-xs leading-5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}
            >
              {contextScope
                ? `已附上${attachedLabel || '选中节点'}。发送消息时会一并分析，本轮有效。`
                : `默认只是普通对话，不会读取“${canvasTitle || '当前画布'}”。需要分析画布时，再为本轮附加节点、整个画布或截图。`}
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {messages.map((message) => {
              const isUser = message.role === 'user';
              return (
                <article
                  key={message.message_id}
                  className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                      isUser
                        ? 'bg-slate-900 text-white'
                        : 'bg-violet-600 text-white'
                    }`}
                  >
                    {isUser ? <User size={13} /> : <Bot size={14} />}
                  </div>
                  <div
                    className={`min-w-0 max-w-[82%] ${isUser ? 'text-right' : ''}`}
                  >
                    {message.context_scope &&
                      message.context_scope !== 'none' && (
                        <div
                          className={`mb-1 inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] ${
                            isDark
                              ? 'bg-violet-500/15 text-violet-300'
                              : 'bg-violet-50 text-violet-700'
                          }`}
                        >
                          <Paperclip size={10} />{' '}
                          {message.context_label || '画布上下文'} · 仅本轮
                        </div>
                      )}
                    <div
                      className={`rounded-2xl px-3.5 py-2.5 text-left text-[13px] leading-6 ${
                        isUser
                          ? 'rounded-tr-md bg-violet-600 text-white'
                          : isDark
                            ? 'rounded-tl-md bg-slate-800 text-slate-100'
                            : 'rounded-tl-md bg-slate-50 text-slate-700'
                      }`}
                    >
                      {message.content ? (
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => (
                              <p className="my-0 whitespace-pre-wrap break-words">
                                {children}
                              </p>
                            ),
                            ul: ({ children }) => (
                              <ul className="my-2 list-disc space-y-1 pl-5">
                                {children}
                              </ul>
                            ),
                            ol: ({ children }) => (
                              <ol className="my-2 list-decimal space-y-1 pl-5">
                                {children}
                              </ol>
                            ),
                            code: ({ children }) => (
                              <code className="rounded bg-black/10 px-1 py-0.5 text-[12px]">
                                {children}
                              </code>
                            ),
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 opacity-70">
                          <Loader2 size={13} className="animate-spin" />{' '}
                          正在思考
                        </span>
                      )}
                    </div>
                    <time
                      className={`mt-1 block px-1 text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}
                    >
                      {formatTime(message.created_at)}
                    </time>
                  </div>
                </article>
              );
            })}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div
          className={`shrink-0 p-3 ${isDark ? 'bg-slate-900/70' : 'bg-white'}`}
        >
          {error && (
            <div
              role="alert"
              className={`mb-2 rounded-xl px-3 py-2 text-xs leading-5 ${
                isDark
                  ? 'bg-amber-500/10 text-amber-200'
                  : 'bg-amber-50 text-amber-800'
              }`}
            >
              {error}
            </div>
          )}

          {selectedContext && (
            <div
              className={`mb-2 rounded-xl px-3 py-2 text-xs ${
                isDark
                  ? 'bg-violet-500/10 text-violet-200'
                  : 'bg-violet-50 text-violet-700'
              }`}
            >
              {attachedPreview?.thumbnails.length ? (
                <div className="mb-2 flex gap-1.5 overflow-x-auto pb-0.5">
                  {attachedPreview.thumbnails.slice(0, 8).map((thumb) => (
                    <div
                      key={thumb.id}
                      className="relative h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-slate-200"
                      title={thumb.title}
                    >
                      {thumb.url && (thumb.kind === 'video' || thumb.url.match(/\.(mp4|webm|mov)(\?|$)/i)) ? (
                        <video src={thumb.url} muted playsInline className="h-full w-full object-cover" />
                      ) : thumb.url ? (
                        <img src={thumb.url} alt={thumb.title} className="h-full w-full object-cover" />
                      ) : (
                        <span className="flex h-full w-full items-center justify-center px-1 text-center text-[9px] leading-3 text-slate-500">
                          {thumb.title}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : null}
              <div className="flex items-center gap-2">
                <selectedContext.icon size={13} />
                <span className="min-w-0 flex-1 truncate">
                  {attachedLabel} · 仅下一条消息
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setContextScope(null);
                    setAttachedPreview(null);
                  }}
                  aria-label="移除画布引用"
                  className="cursor-pointer rounded p-0.5 hover:bg-black/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400"
                >
                  <X size={13} />
                </button>
              </div>
            </div>
          )}

          {imageAttachments.length > 0 && (
            <div
              className={`mb-2 rounded-xl px-3 py-2 text-xs ${
                isDark
                  ? 'bg-sky-500/10 text-sky-100'
                  : 'bg-sky-50 text-sky-800'
              }`}
            >
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5">
                  <ImageIcon size={13} /> 已添加 {imageAttachments.length} 张图片
                </span>
                <span className={isDark ? 'text-slate-400' : 'text-slate-500'}>
                  将随本轮消息交给对话模型识别
                </span>
              </div>
              <div className="flex gap-1.5 overflow-x-auto pb-0.5">
                {imageAttachments.map((attachment) => (
                  <div
                    key={attachment.id}
                    className="relative h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-slate-200"
                    title={attachment.name}
                  >
                    <img
                      src={attachment.previewUrl}
                      alt={attachment.name}
                      className="h-full w-full object-cover"
                    />
                    <button
                      type="button"
                      onClick={() => removeImageAttachment(attachment.id)}
                      aria-label={`移除 ${attachment.name}`}
                      className="absolute right-0.5 top-0.5 flex h-4 w-4 cursor-pointer items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/80"
                    >
                      <X size={10} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div
            ref={modelMenuRef}
            className={`relative rounded-2xl p-2 shadow-sm transition-colors ${
              isDark
                ? 'bg-slate-800'
                : 'bg-slate-50'
            }`}
          >
            {modelMenuOpen && (
              <div
                role="listbox"
                aria-label="选择对话模型"
                className={`absolute bottom-[calc(100%+8px)] left-0 right-0 z-50 overflow-hidden rounded-2xl border p-3 shadow-[0_18px_50px_rgba(15,23,42,0.18)] ${
                  isDark
                    ? 'border-white/10 bg-slate-900'
                    : 'border-slate-200 bg-white'
                }`}
              >
                <p className={`text-sm font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                  选择模型
                </p>
                {availableChatModelGroups.length > 1 && (
                  <div className={`mt-3 grid grid-cols-2 gap-1 rounded-xl p-1 ${isDark ? 'bg-slate-800' : 'bg-slate-100'}`}>
                    {availableChatModelGroups.map((group) => {
                      const active = group.options.some((option) => option.provider === modelGroupTab);
                      return (
                        <button
                          key={group.label}
                          type="button"
                          onClick={() => setModelGroupTab(group.options[0]?.provider || modelGroupTab)}
                          className={`h-8 cursor-pointer rounded-lg text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 ${
                            active
                              ? isDark
                                ? 'bg-slate-700 text-white'
                                : 'bg-white text-slate-900 shadow-sm'
                              : isDark
                                ? 'text-slate-400 hover:text-slate-200'
                                : 'text-slate-500 hover:text-slate-800'
                          }`}
                        >
                          {group.label.replace('代理', '').trim()}
                        </button>
                      );
                    })}
                  </div>
                )}
                <div className="mt-2 max-h-64 overflow-y-auto">
                  {configLoading ? (
                    <div className="flex h-24 items-center justify-center">
                      <Loader2 size={18} className="animate-spin text-violet-500" />
                    </div>
                  ) : (
                    (activeModelGroup?.options || []).map((option) => {
                      const selected = option.value === chatConfig.model;
                      const OptionIcon = option.provider === 'qwen' ? Bot : Sparkles;
                      return (
                        <button
                          key={option.value}
                          type="button"
                          role="option"
                          aria-selected={selected}
                          disabled={configSaving}
                          onClick={() => void selectChatModel(option)}
                          className={`flex w-full cursor-pointer items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 disabled:cursor-wait ${
                            selected
                              ? isDark
                                ? 'bg-slate-800'
                                : 'bg-slate-50'
                              : isDark
                                ? 'hover:bg-slate-800'
                                : 'hover:bg-slate-50'
                          }`}
                        >
                          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${isDark ? 'bg-slate-800 text-slate-200' : 'bg-slate-100 text-slate-600'}`}>
                            <OptionIcon size={16} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className={`block truncate text-xs font-semibold ${isDark ? 'text-slate-100' : 'text-slate-900'}`}>
                              {option.label}
                            </span>
                            <span className={`mt-0.5 block truncate text-[10px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                              {option.description}
                            </span>
                          </span>
                          <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${
                            selected
                              ? 'border-violet-500 bg-violet-600 text-white'
                              : isDark
                                ? 'border-white/15 text-slate-400'
                                : 'border-slate-200 text-slate-400'
                          }`}
                          >
                            {selected ? <Check size={13} /> : <Plus size={13} />}
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            )}
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onFocus={() => setModelMenuOpen(false)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              rows={3}
              maxLength={12000}
              placeholder={
                status?.configured
                  ? '输入消息，Shift + Enter 换行'
                  : '模型密钥稍后配置，当前可浏览界面和历史'
              }
              className={`w-full resize-none border-0 bg-transparent px-1.5 py-1 text-sm leading-5 outline-none placeholder:text-slate-400 ${isDark ? 'text-slate-100' : 'text-slate-800'}`}
            />
            <div className="flex items-end justify-between gap-2 pt-1">
              <div className="flex min-w-0 flex-wrap items-center gap-1">
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => {
                      setModelMenuOpen(false);
                      setContextMenuOpen((open) => !open);
                    }}
                    aria-haspopup="menu"
                    aria-expanded={contextMenuOpen}
                    className={`flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 ${
                      contextScope
                        ? 'bg-violet-600 text-white'
                        : isDark
                          ? 'text-slate-300 hover:bg-slate-700'
                          : 'text-slate-500 hover:bg-slate-100'
                    }`}
                  >
                    <Paperclip size={14} /> 引用画布
                  </button>
                  {contextMenuOpen && (
                  <div
                    role="menu"
                    className={`absolute bottom-10 left-0 z-50 w-64 overflow-hidden rounded-2xl p-1.5 shadow-2xl ${
                      isDark
                        ? 'bg-slate-800'
                        : 'bg-white'
                    }`}
                  >
                    <div
                      className={`px-2.5 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-wider ${isDark ? 'text-slate-500' : 'text-slate-400'}`}
                    >
                      仅用于下一条消息
                    </div>
                    {CONTEXT_OPTIONS.map((option) => {
                      const Icon = option.icon;
                      const disabled =
                        option.scope === 'selected_node' && !hasSelectedNode;
                      return (
                        <button
                          key={option.scope}
                          type="button"
                          role="menuitem"
                          disabled={disabled}
                          onClick={() => {
                            setContextScope(option.scope);
                            setAttachedPreview({
                              label: option.label,
                              thumbnails: [],
                            });
                            setContextMenuOpen(false);
                          }}
                          className={`flex w-full cursor-pointer items-start gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 disabled:cursor-not-allowed disabled:opacity-40 ${
                            isDark ? 'hover:bg-slate-700' : 'hover:bg-slate-50'
                          }`}
                        >
                          <Icon
                            size={15}
                            className="mt-0.5 shrink-0 text-violet-500"
                          />
                          <span>
                            <span className="block text-xs font-medium">
                              {option.label}
                            </span>
                            <span
                              className={`mt-0.5 block text-[10px] ${isDark ? 'text-slate-400' : 'text-slate-500'}`}
                            >
                              {disabled
                                ? '请先选择一个节点'
                                : option.description}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => imageInputRef.current?.click()}
                  disabled={sending || Boolean(mediaGenerating)}
                  title="添加图片，让对话模型识别和分析"
                  className={`flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 disabled:cursor-not-allowed disabled:opacity-50 ${
                    isDark
                      ? 'text-slate-300 hover:bg-slate-700'
                      : 'text-slate-500 hover:bg-slate-100'
                  }`}
                >
                  <ImageIcon size={14} /> 加图片
                </button>
              </div>
              <div className="flex min-w-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => void openModelMenu()}
                  aria-haspopup="listbox"
                  aria-expanded={modelMenuOpen}
                  aria-label="选择对话模型"
                  title="选择对话模型"
                  className={`flex h-8 max-w-[168px] cursor-pointer items-center gap-1 rounded-lg px-2 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 ${
                    modelMenuOpen
                      ? isDark
                        ? 'bg-slate-700 text-slate-100'
                        : 'bg-white text-slate-900 shadow-sm'
                      : isDark
                        ? 'text-slate-300 hover:bg-slate-700'
                        : 'text-slate-500 hover:bg-white'
                  }`}
                >
                  {configSaving ? (
                    <Loader2 size={13} className="shrink-0 animate-spin" />
                  ) : (
                    <Box size={13} className="shrink-0" />
                  )}
                  <span className="min-w-0 truncate">
                    {selectedChatModel?.label.replace(/（.*?）/g, '') || '选择模型'}
                  </span>
                  <ChevronDown size={12} className="shrink-0 opacity-60" />
                </button>
                <button
                  type="button"
                  onClick={() => void handleSend()}
                  disabled={
                    !input.trim() ||
                    sending ||
                    !status?.configured
                  }
                  aria-label="发送消息"
                  className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl bg-transparent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed ${isDark ? 'text-slate-300 hover:bg-slate-700 disabled:text-slate-600' : 'text-slate-500 hover:bg-slate-100 disabled:text-slate-300'}`}
                >
                  {sending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Send size={16} />
                  )}
                </button>
              </div>
            </div>
          </div>
          <p
            className={`mt-2 text-center text-[9px] ${isDark ? 'text-slate-500' : 'text-slate-400'}`}
          >
            图片会先交给对话模型识别
          </p>
          <input
            ref={imageInputRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={handleImageAttachmentChange}
          />
        </div>
    </aside>
  );
};

export default CanvasChatPanel;
