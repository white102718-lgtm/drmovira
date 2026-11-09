/**
 * AI Backend Service
 * 通过后端 API 调用 AI 功能，代替前端直接调用 Gemini API
 */

import { AssetType } from '../types';
import type {
  Clarification,
  GeneratedResult,
  GenerationRequest,
  TodoItem,
  UploadedAsset,
} from '../types';
import { readCanvasModelApiResponse } from '../../../api/canvas-model-response';
import { OFFICIAL_ASSET_LIBRARY_ENABLED } from '../officialAssetLibrary';
import { fileToBase64 } from './storageService';
import { authService } from './authService';
import { BACKEND_URL } from './runtimeConfig';
import {
  isWan3ReferenceAudioFile,
  isWan3ReferenceDocumentFile,
  isWan3VideoModel,
  isSeedance25VideoModel,
  WAN3_MAX_OMNI_MEDIA,
  WAN3_MAX_REFERENCE_AUDIOS,
  WAN3_MAX_REFERENCE_FILES,
  WAN3_MAX_REFERENCE_IMAGES,
  WAN3_MAX_REFERENCE_LINKS,
  WAN3_MAX_REFERENCE_VIDEOS,
  WAN3_REFERENCE_AUDIO_MAX_BYTES,
  WAN3_REFERENCE_AUDIO_MAX_SECONDS,
  WAN3_REFERENCE_AUDIO_MIN_SECONDS,
  WAN3_REFERENCE_AUDIO_TOTAL_MAX_SECONDS,
  WAN3_REFERENCE_FILE_MAX_BYTES,
  WAN3_REFERENCE_VIDEO_MAX_BYTES,
  WAN3_REFERENCE_VIDEO_MAX_SECONDS,
  WAN3_REFERENCE_VIDEO_MIN_SECONDS,
  WAN3_REFERENCE_VIDEO_TOTAL_MAX_SECONDS,
} from '../utils/mediaModelConfig';
import {
  extractProviderErrorParts,
  formatProviderError,
  formatProviderErrorMessage,
  type ProviderErrorType,
} from './providerErrorMessage';

const API_BASE = `${BACKEND_URL}/api/ai`;

interface VideoBackendResult {
  aspect_ratio?: string;
  capability?: string;
  duration?: number | string;
  extension_count?: number;
  id?: string;
  history_record_id?: string;
  model_name?: string;
  object_name?: string;
  provider?: string;
  provider_model?: string;
  provider_video_url?: string;
  resolution?: string;
  task_id?: string;
  video_id?: string;
  video_url?: string;
}

const encodeObjectPath = (objectName: string) =>
  objectName.split('/').map(encodeURIComponent).join('/');

/** 优先通过当前站点的后端代理下载 MinIO 视频，避免供应商临时地址的跨域限制。 */
function resolveVideoDownloadUrl(result: VideoBackendResult): string {
  if (result.object_name) {
    return `${BACKEND_URL}/api/minio/stream/${encodeObjectPath(result.object_name)}`;
  }
  return result.video_url || '';
}

function getHeaders(): HeadersInit {
  const token = authService.getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function fetchReferenceImageAsBase64(
  url: string,
): Promise<{ data: string; mimeType: string }> {
  const resp = await fetch(url);
  const contentType = resp.headers.get('content-type') || '';

  if (!resp.ok) {
    const detail = await resp.text().catch(() => '');
    const cleanDetail = detail
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    throw new Error(
      `参考图片下载失败：HTTP ${resp.status} ${resp.statusText}${cleanDetail ? ` - ${cleanDetail.slice(0, 200)}` : ''}`,
    );
  }

  if (contentType && !contentType.toLowerCase().startsWith('image/')) {
    const detail = await resp.text().catch(() => '');
    const cleanDetail = detail
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    throw new Error(
      `参考图片链接返回的不是图片：${contentType}${cleanDetail ? ` - ${cleanDetail.slice(0, 200)}` : ''}`,
    );
  }

  const blob = await resp.blob();
  const mimeType = blob.type || contentType || 'image/jpeg';
  if (!mimeType.toLowerCase().startsWith('image/')) {
    throw new Error(`参考图片文件类型无效：${mimeType}`);
  }
  if (blob.size === 0) {
    throw new Error('参考图片下载失败：文件为空');
  }

  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
  return { data, mimeType };
}

function throwVideoGenerationErrorFromPayload(
  message: string,
  detail: string,
): never {
  const originalReason = [message, detail].filter(Boolean).join('\n');
  const formatted = formatProviderError(
    message,
    detail,
    '视频生成失败，请根据下方原因调整后重试',
  );
  const suggestions =
    formatted.suggestions.length > 0
      ? formatted.suggestions
      : [
          responseIsTimeoutMessage(originalReason)
            ? '这通常是同步请求超过网关等待时间导致的，请稍后重试或使用后台任务生成'
            : '请根据失败原因调整提示词、画幅或参考素材后重试',
        ];

  throw new VideoGenerationError(
    formatted.message,
    formatted.type,
    suggestions,
    originalReason,
  );
}

function responseIsTimeoutMessage(message: string): boolean {
  return (
    message.includes('504') ||
    message.toLowerCase().includes('timeout') ||
    message.includes('超时')
  );
}

function getLocalVideoDuration(file: File): Promise<number> {
  return new Promise((resolve) => {
    const video = document.createElement('video');
    const url = URL.createObjectURL(file);
    video.preload = 'metadata';
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(video.duration) ? video.duration : 0);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(0);
    };
    video.src = url;
  });
}

async function validateWanR2VReferenceVideo(file: File): Promise<void> {
  const maxBytes = 100 * 1024 * 1024;
  if (file.size > maxBytes) {
    throw new Error(
      '万相 2.7 参考生视频要求参考视频不超过 100MB，请压缩或裁剪后重试',
    );
  }
  const duration = await getLocalVideoDuration(file);
  if (duration > 0 && (duration < 1 || duration > 30)) {
    throw new Error(
      `万相 2.7 参考生视频要求参考视频时长为 1-30 秒，当前约 ${Math.round(duration)} 秒`,
    );
  }
}

async function validateWan3OmniReferenceVideos(files: File[]): Promise<void> {
  if (files.length > WAN3_MAX_REFERENCE_VIDEOS) {
    throw new Error(
      `万相 3.0 全能参考最多 ${WAN3_MAX_REFERENCE_VIDEOS} 段参考视频`,
    );
  }
  let totalDuration = 0;
  for (const file of files) {
    if (file.size > WAN3_REFERENCE_VIDEO_MAX_BYTES) {
      throw new Error('万相 3.0 参考视频不超过 100MB，请压缩或裁剪后重试');
    }
    const duration = await getLocalVideoDuration(file);
    if (
      duration > 0 &&
      (duration < WAN3_REFERENCE_VIDEO_MIN_SECONDS ||
        duration > WAN3_REFERENCE_VIDEO_MAX_SECONDS)
    ) {
      throw new Error(
        `万相 3.0 参考视频时长须为 ${WAN3_REFERENCE_VIDEO_MIN_SECONDS}-${WAN3_REFERENCE_VIDEO_MAX_SECONDS} 秒，当前约 ${Math.round(duration)} 秒`,
      );
    }
    totalDuration += duration;
  }
  if (totalDuration > WAN3_REFERENCE_VIDEO_TOTAL_MAX_SECONDS) {
    throw new Error(
      `万相 3.0 参考视频总时长不超过 ${WAN3_REFERENCE_VIDEO_TOTAL_MAX_SECONDS} 秒，当前约 ${Math.round(totalDuration)} 秒`,
    );
  }
}

function getLocalAudioDuration(file: File): Promise<number> {
  return new Promise((resolve) => {
    const audio = document.createElement('audio');
    const url = URL.createObjectURL(file);
    audio.preload = 'metadata';
    audio.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(Number.isFinite(audio.duration) ? audio.duration : 0);
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(0);
    };
    audio.src = url;
  });
}

function isPublicHttpUrl(value: string) {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

async function buildFileReferencePayload(asset: UploadedAsset) {
  const payload: { assetUri?: string; data?: string; mimeType?: string } = {};
  if (OFFICIAL_ASSET_LIBRARY_ENABLED && asset.officialAssetUri) {
    payload.assetUri = asset.officialAssetUri;
  }
  // 官方编号仅供 BytePlus 使用；保留原文件，由后端按实际模型路由选择输入。
  if (asset.file) {
    payload.data = await fileToBase64(asset.file);
    payload.mimeType = asset.file.type;
  }
  return payload.assetUri || payload.data ? payload : null;
}

async function validateWan3OmniReferenceAudios(files: File[]): Promise<void> {
  if (files.length > WAN3_MAX_REFERENCE_AUDIOS) {
    throw new Error(
      `万相 3.0 全能参考最多 ${WAN3_MAX_REFERENCE_AUDIOS} 段参考音频`,
    );
  }
  let totalDuration = 0;
  for (const file of files) {
    if (!isWan3ReferenceAudioFile(file)) {
      throw new Error('万相 3.0 参考音频仅支持 wav / mp3');
    }
    if (file.size > WAN3_REFERENCE_AUDIO_MAX_BYTES) {
      throw new Error('万相 3.0 参考音频不超过 15MB，请压缩或裁剪后重试');
    }
    const duration = await getLocalAudioDuration(file);
    if (
      duration > 0 &&
      (duration < WAN3_REFERENCE_AUDIO_MIN_SECONDS ||
        duration > WAN3_REFERENCE_AUDIO_MAX_SECONDS)
    ) {
      throw new Error(
        `万相 3.0 参考音频时长须为 ${WAN3_REFERENCE_AUDIO_MIN_SECONDS}-${WAN3_REFERENCE_AUDIO_MAX_SECONDS} 秒，当前约 ${Math.round(duration)} 秒`,
      );
    }
    totalDuration += duration;
  }
  if (totalDuration > WAN3_REFERENCE_AUDIO_TOTAL_MAX_SECONDS) {
    throw new Error(
      `万相 3.0 参考音频总时长不超过 ${WAN3_REFERENCE_AUDIO_TOTAL_MAX_SECONDS} 秒，当前约 ${Math.round(totalDuration)} 秒`,
    );
  }
}

/** Seedance 2.5 音频须符合供应商格式、大小与时长限制。 */
async function validateSeedance25ReferenceAudios(files: File[]): Promise<void> {
  let totalDuration = 0;
  for (const file of files) {
    if (
      !/\.(mp3|wav)$/i.test(file.name) &&
      ![
        'audio/mpeg',
        'audio/mp3',
        'audio/wav',
        'audio/x-wav',
        'audio/wave',
      ].includes(file.type)
    ) {
      throw new Error('Seedance 2.5 参考音频仅支持 wav / mp3');
    }
    if (file.size > 15 * 1024 * 1024)
      throw new Error('Seedance 2.5 单段参考音频不超过 15MB');
    const duration = await getLocalAudioDuration(file);
    if (duration <= 0 || duration < 2 || duration > 30)
      throw new Error(
        'Seedance 2.5 参考音频时长须为 2-30 秒，请检查或裁剪音频',
      );
    totalDuration += duration;
  }
  if (totalDuration > 30)
    throw new Error('Seedance 2.5 参考音频总时长不超过 30 秒');
}

function validateWan3OmniReferenceFiles(files: File[]): void {
  if (files.length > WAN3_MAX_REFERENCE_FILES) {
    throw new Error('万相 3.0 全能参考最多 1 份文档');
  }
  for (const file of files) {
    if (!isWan3ReferenceDocumentFile(file)) {
      throw new Error(
        '万相 3.0 文档参考仅支持 Word / Excel / PPT / PDF / TXT / Markdown / Keynote / Pages / Numbers',
      );
    }
    if (file.size > WAN3_REFERENCE_FILE_MAX_BYTES) {
      throw new Error('万相 3.0 文档参考不超过 100MB');
    }
  }
}

/**
 * 自定义错误类，包含详细的错误信息和建议
 */
export class VideoGenerationError extends Error {
  type: ProviderErrorType;
  suggestions: string[];
  originalReason?: string;

  constructor(
    message: string,
    type: ProviderErrorType,
    suggestions: string[] = [],
    originalReason?: string,
  ) {
    super(message);
    this.name = 'VideoGenerationError';
    this.type = type;
    this.suggestions = suggestions;
    this.originalReason = originalReason;
  }
}

export class VideoGenerationCancelledError extends Error {
  constructor() {
    super('视频任务已取消');
    this.name = 'VideoGenerationCancelledError';
  }
}

export interface VideoTaskProgress {
  message?: string;
  provider?: string;
  providerStatus?: string;
  providerTaskId?: string;
  canCancel?: boolean;
  cancelReason?: string;
}

type VideoGenerationProgressHandler = (
  message: string,
  progress?: VideoTaskProgress,
) => void;
type VideoTaskCreatedHandler = (
  taskId: string,
  canCancel?: boolean,
  isSubmitting?: boolean,
) => void;

/**
 * 在请求发出前创建不可猜测的本地视频任务标识。
 *
 * 后端可用它匹配先到达的取消请求，避免等待提交接口返回后才允许取消。
 */
export function createVideoGenerationTaskId(): string {
  const secureCrypto = globalThis.crypto;
  if (typeof secureCrypto?.randomUUID === 'function') {
    return `ai_video_${secureCrypto.randomUUID().replaceAll('-', '')}`;
  }

  if (typeof secureCrypto?.getRandomValues === 'function') {
    const randomBytes = new Uint8Array(16);
    secureCrypto.getRandomValues(randomBytes);
    const randomId = Array.from(randomBytes, (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('');
    return `ai_video_${randomId}`;
  }

  throw new Error('当前浏览器不支持安全任务标识，无法提交视频生成任务');
}

async function readVideoApiResponse<T>(response: Response): Promise<T> {
  try {
    return await readCanvasModelApiResponse<T>(response);
  } catch (error) {
    throwVideoGenerationErrorFromPayload(
      error instanceof Error ? error.message : '视频生成失败',
      '',
    );
  }
}

/**
 * 初始化 API Key Pool
 */
export const initializeKeyPool = async (keys: string[]): Promise<void> => {
  try {
    const response = await fetch(`${API_BASE}/key-pool/init`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ keys }),
    });

    await readCanvasModelApiResponse(response);

    console.log('[API Key Pool] Initialized successfully');
  } catch (error) {
    console.error('[API Key Pool] Initialization failed:', error);
    throw error;
  }
};

/**
 * 添加 API Key 到池中
 */
export const addKeyToPool = async (key: string): Promise<void> => {
  try {
    const response = await fetch(`${API_BASE}/key-pool/add`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ key }),
    });

    await readCanvasModelApiResponse(response);

    console.log('[API Key Pool] Key added successfully');
  } catch (error) {
    console.error('[API Key Pool] Add key failed:', error);
    throw error;
  }
};

/**
 * 获取 Key Pool 状态
 */
export const getKeyPoolStatus = async (): Promise<any> => {
  try {
    const response = await fetch(`${API_BASE}/key-pool/status`);

    return await readCanvasModelApiResponse(response);
  } catch (error) {
    console.error('[API Key Pool] Get status failed:', error);
    throw error;
  }
};

/**
 * 智能追问 - 生成后续问题
 */
export const generateFollowUpQuestions = async (
  userPrompt: string,
  previousAnswers: Record<string, string>,
  round: number,
): Promise<{
  clarifications: Clarification[];
  isComplete: boolean;
  completenessScore: number;
}> => {
  try {
    const response = await fetch(`${API_BASE}/follow-up-questions`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        userPrompt,
        previousAnswers,
        round,
      }),
    });

    const data = await readCanvasModelApiResponse<{
      clarifications?: Clarification[];
      completenessScore?: number;
      isComplete?: boolean;
    }>(response);
    return {
      clarifications: data.clarifications || [],
      isComplete: data.isComplete || false,
      completenessScore: data.completenessScore || 0,
    };
  } catch (error) {
    console.error('[generateFollowUpQuestions] Error:', error);
    return {
      clarifications: [],
      isComplete: false,
      completenessScore: 0,
    };
  }
};

/**
 * 生成需求计划（Todo List）
 */
export const planDemand = async (
  prompt: string,
  assetsCount: number,
  generationType: 'image' | 'video' = 'image',
  batchCount: number = 1,
  videoExtensionCount: number = 0,
  videoDurationSeconds?: number,
  retryCount: number = 0,
): Promise<{ todos: TodoItem[]; clarifications: Clarification[] }> => {
  try {
    const response = await fetch(`${API_BASE}/plan-demand`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        prompt,
        assetsCount,
        generationType,
        batchCount,
        videoExtensionCount,
        videoDurationSeconds,
      }),
    });

    const data = await readCanvasModelApiResponse<{
      clarifications?: Clarification[];
      todos?: TodoItem[];
    }>(response);
    return {
      todos: data.todos || [],
      clarifications: data.clarifications || [],
    };
  } catch (error) {
    console.error('[planDemand] Error:', error);
    // 返回默认计划
    const contentType = generationType === 'image' ? '图片' : '视频';
    return {
      todos: [
        {
          id: '1',
          task: '分析需求和目标',
          description: `分析${contentType}制作需求`,
          status: 'pending',
        },
        {
          id: '2',
          task: `设计${contentType}方案`,
          description: `设计${contentType}的视觉和创意方案`,
          status: 'pending',
        },
        {
          id: '3',
          task: `生成${batchCount}个${contentType}`,
          description: `使用AI并行生成${batchCount}个${contentType}变体`,
          status: 'pending',
        },
        {
          id: '4',
          task: '优化和输出',
          description: `优化${contentType}质量并准备交付`,
          status: 'pending',
        },
      ],
      clarifications: [],
    };
  }
};

/**
 * 批量生成图片
 * 通过后端API调用图片生成
 */
export const generateBatchImages = async (
  request: GenerationRequest,
): Promise<GeneratedResult[]> => {
  console.log('[generateBatchImages] 通过后端API生成图片...');

  try {
    // 准备参考图片
    const imageAssets = request.assets.filter(
      (a) => a.type === AssetType.IMAGE,
    );
    const referenceImages = [];
    const referenceImageErrors: string[] = [];

    for (const imageAsset of imageAssets) {
      try {
        if (imageAsset.file) {
          // 有 File 对象，直接转 base64
          const base64 = await fileToBase64(imageAsset.file);
          referenceImages.push({
            data: base64,
            mimeType: imageAsset.file.type,
          });
        } else if (imageAsset.url) {
          // 只有 URL（从 MinIO/历史恢复），fetch 后转 base64
          console.log(
            `[generateBatchImages] 从 URL 获取参考图片: ${imageAsset.url.substring(0, 80)}...`,
          );
          referenceImages.push(
            await fetchReferenceImageAsBase64(imageAsset.url),
          );
        }
      } catch (err) {
        console.error(`[generateBatchImages] 参考图片处理失败:`, err);
        referenceImageErrors.push(
          err instanceof Error ? err.message : String(err),
        );
      }
    }

    if (imageAssets.length > 0 && referenceImages.length === 0) {
      throw new Error(
        `参考图片处理失败：${referenceImageErrors[0] || '无法读取参考图片'}`,
      );
    }

    console.log(`[generateBatchImages] 准备生成 ${request.batchCount} 张图片`);
    console.log(
      `[generateBatchImages] 参考图片数量: ${referenceImages.length}`,
    );

    // 调用后端API
    const response = await fetch(`${API_BASE}/generate-images`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        prompt: request.prompt,
        batchCount: request.batchCount,
        referenceImages,
        aspectRatio: request.aspectRatio,
        imageSize: request.imageSize,
        model: request.imageModel,
        generationMode: request.imageGenerationMode,
      }),
    });

    const responseData = await readCanvasModelApiResponse<{
      results?: Array<Record<string, unknown>>;
    }>(response);
    const results = responseData?.results;
    if (!Array.isArray(results) || results.length === 0) {
      throw new Error('图片生成失败：后端未返回有效结果');
    }
    console.log(`[generateBatchImages] 后端返回 ${results.length} 张图片`);

    // 转换为前端可用的格式
    const generatedResults: GeneratedResult[] = results
      .filter((result: any) => result?.id && result?.image_url)
      .map((result: any) => ({
        id: result.id,
        type: AssetType.IMAGE,
        url: result.image_url, // 已经是 data URL 格式
        prompt: result.prompt,
        createdAt: new Date(),
      }));

    return generatedResults;
  } catch (error) {
    console.error('[generateBatchImages] Error:', error);
    throw new Error(
      toFormattedGenerationMessage(error, '图片生成失败，请根据提示调整后重试'),
    );
  }
};

/**
 * 分析视频内容
 *
 * 这个功能通过后端调用，因为它只需要文本分析
 */
export const analyzeVideoContent = async (
  videoAsset: UploadedAsset,
): Promise<string> => {
  if (!videoAsset.file) {
    throw new Error('视频文件不存在');
  }

  try {
    const videoBase64 = await fileToBase64(videoAsset.file);

    const response = await fetch(`${API_BASE}/analyze-video`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        videoData: `data:${videoAsset.file.type};base64,${videoBase64}`,
        mimeType: videoAsset.file.type,
      }),
    });

    const data = await readCanvasModelApiResponse<{ analysis?: string }>(
      response,
    );
    return data.analysis || '无法分析视频内容';
  } catch (error) {
    console.error('[analyzeVideoContent] Error:', error);
    throw error instanceof Error ? error : new Error('视频分析失败');
  }
};

/** 画布视频分析：服务端把 MinIO 私有素材转换为模型可访问的临时 HTTPS 地址。 */
export const analyzeCanvasVideo = async (request: {
  videoUrl: string;
  prompt?: string;
}): Promise<{ analysis: string; model: string }> => {
  const response = await fetch(`${BACKEND_URL}/api/canvas-chat/analyze-video`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      video_url: request.videoUrl,
      prompt: request.prompt || '',
    }),
  });
  const data = await readCanvasModelApiResponse<{
    analysis?: string;
    model?: string;
  }>(response);
  const analysis = String(data?.analysis || '').trim();
  if (!analysis) throw new Error('视频分析接口未返回有效结果');
  return {
    analysis,
    model: String(data?.model || 'qwen3.8-omni-flash'),
  };
};

// 轮询节奏：视频生成是"提交—等待—取结果"的离散长任务，且后端自身也是每 10 秒
// 才向上游查一次状态（ai_service.py 的 time.sleep(10)），所以轮询拿不到比这更细的粒度。
// 之前这里还并行开了一条 SSE 长连接，在 thread-per-request 的 gunicorn 上会整个任务时长
// 占住一个线程槽，多工作区并发时线程池被占满导致全站请求排队。
const VIDEO_TASK_FAST_INTERVAL_MS = 2000;
const VIDEO_TASK_SLOW_INTERVAL_MS = 5000;
const VIDEO_TASK_FAST_PHASE_MS = 30000;
// 百炼 Wan 3.0 实测会超过 30 分钟才成功，前端多等一会儿以免任务已在跑却被本地掐断。
const VIDEO_TASK_MAX_WAIT_MS = 60 * 60 * 1000;

function toFormattedGenerationMessage(
  error: unknown,
  fallback: string,
): string {
  const parts = extractProviderErrorParts(error);
  return formatProviderErrorMessage(
    parts.message || (error instanceof Error ? error.message : ''),
    parts.detail,
    fallback,
  );
}

const FAILED_VIDEO_TASK_STATUSES = new Set([
  'failed',
  'error',
  'failure',
  'fail',
  'canceled',
  'cancelled',
]);

function readVideoTaskPayload(
  snapshot: unknown,
): Record<string, unknown> | null {
  if (!snapshot || typeof snapshot !== 'object') return null;
  const raw = snapshot as Record<string, unknown>;
  const nested = raw.data;
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const task = nested as Record<string, unknown>;
    if (
      'status' in task ||
      'error' in task ||
      'result' in task ||
      'results' in task
    ) {
      return task;
    }
  }
  return raw;
}

async function waitForVideoGenerationTask(
  taskId: string,
  onProgress?: VideoGenerationProgressHandler,
): Promise<any> {
  const startedAt = Date.now();
  let lastProgressMessage = '';
  let consecutiveFailures = 0;

  while (true) {
    const elapsed = Date.now() - startedAt;
    if (elapsed > VIDEO_TASK_MAX_WAIT_MS) {
      throw new VideoGenerationError(
        '视频生成等待超时，任务可能仍在后台运行',
        'general',
        ['请到历史记录中检查是否已生成', '如未生成请重新提交任务'],
      );
    }

    try {
      const polled = await getVideoGenerationTaskResult(taskId);
      consecutiveFailures = 0;

      if (polled) {
        if (polled.result || polled.results) return polled;

        if (polled.status === 'running') {
          const message = polled.progress?.message;
          const progress = polled.progress as VideoTaskProgress | undefined;
          if (message && message !== lastProgressMessage) {
            lastProgressMessage = message;
            console.log('[generateVideoFission] 后台进度:', message);
            onProgress?.(message, progress);
          } else if (progress) {
            onProgress?.('', progress);
          }
        } else if (
          polled.status === 'cancelled' ||
          polled.status === 'canceled'
        ) {
          throw new VideoGenerationCancelledError();
        } else {
          const parts = extractProviderErrorParts(polled);
          throwVideoGenerationErrorFromPayload(
            parts.message || polled.error || '视频生成失败',
            parts.detail || polled.detail || '',
          );
        }
      }
    } catch (err: any) {
      // 业务错误（后端已判定失败）直接抛出；网络抖动则重试，任务在后端仍在跑。
      if (
        err instanceof VideoGenerationError ||
        err instanceof VideoGenerationCancelledError
      )
        throw err;
      consecutiveFailures += 1;
      console.warn(
        `[generateVideoFission] 轮询视频生成结果失败(第 ${consecutiveFailures} 次):`,
        err,
      );
      if (consecutiveFailures >= 10) {
        const parts = extractProviderErrorParts(err);
        throwVideoGenerationErrorFromPayload(
          parts.message || '无法获取视频生成进度，请检查网络连接',
          parts.detail,
        );
      }
    }

    const interval =
      elapsed < VIDEO_TASK_FAST_PHASE_MS
        ? VIDEO_TASK_FAST_INTERVAL_MS
        : VIDEO_TASK_SLOW_INTERVAL_MS;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}

async function getVideoGenerationTaskResult(
  taskId: string,
): Promise<any | null> {
  const response = await fetch(`${API_BASE}/generate-videos/result/${taskId}`, {
    method: 'GET',
    headers: getHeaders(),
  });

  // 测试环境可能仍返回旧协议：HTTP 202 且 success=false 表示任务尚未完成，
  // 不能交给通用错误解包器，否则前端会把正常轮询累计成“网络连接失败”。
  const responseSnapshot: unknown = await response
    .clone()
    .json()
    .catch(() => null);
  const taskPayload = readVideoTaskPayload(responseSnapshot);
  const snapshotRecord =
    responseSnapshot && typeof responseSnapshot === 'object'
      ? (responseSnapshot as Record<string, unknown>)
      : null;
  const envelopeCode =
    typeof snapshotRecord?.code === 'number' ? snapshotRecord.code : null;
  const taskStatus =
    typeof taskPayload?.status === 'string'
      ? taskPayload.status.toLowerCase()
      : '';
  const hasResult = Boolean(taskPayload?.result || taskPayload?.results);
  const isPending =
    ['running', 'pending', 'queued', 'processing'].includes(taskStatus) ||
    (response.status === 202 && !FAILED_VIDEO_TASK_STATUSES.has(taskStatus));

  // 旧协议：HTTP 202 且 success=false 只表示尚未完成，必须继续轮询。
  if (isPending && !hasResult) {
    return taskPayload || { status: 'running' };
  }

  const isBusinessFailure = Boolean(
    !hasResult &&
      (FAILED_VIDEO_TASK_STATUSES.has(taskStatus) ||
        (snapshotRecord?.success === false && !isPending) ||
        (envelopeCode !== null && envelopeCode !== 200 && envelopeCode !== 0)),
  );

  if (isBusinessFailure) {
    if (taskStatus === 'cancelled' || taskStatus === 'canceled') {
      throw new VideoGenerationCancelledError();
    }
    const parts = extractProviderErrorParts(taskPayload, responseSnapshot);
    throwVideoGenerationErrorFromPayload(
      parts.message || '视频生成失败',
      parts.detail,
    );
  }

  try {
    return await readCanvasModelApiResponse(response);
  } catch (error) {
    // 能解析出服务商/业务失败时立即抛出，避免被当成网络抖动重试 10 次后变成泛化提示。
    if (responseSnapshot) {
      const parts = extractProviderErrorParts(responseSnapshot, error);
      throwVideoGenerationErrorFromPayload(
        parts.message ||
          (error instanceof Error ? error.message : '获取视频生成状态失败'),
        parts.detail,
      );
    }
    if (!response.ok) {
      throwVideoGenerationErrorFromPayload(
        error instanceof Error ? error.message : '获取视频生成状态失败',
        '',
      );
    }
    throw error;
  }
}

export async function cancelVideoGenerationTask(
  taskId: string,
): Promise<{ status?: string }> {
  const response = await fetch(
    `${API_BASE}/generate-videos/cancel/${encodeURIComponent(taskId)}`,
    {
      method: 'POST',
      headers: getHeaders(),
    },
  );
  return await readVideoApiResponse<{ status?: string }>(response);
}

/**
 * 视频裂变/生成
 * 通过后端API调用Veo视频生成
 */
export const generateVideoFission = async (
  request: GenerationRequest,
  onProgress?: VideoGenerationProgressHandler,
  onTaskCreated?: VideoTaskCreatedHandler,
): Promise<GeneratedResult[]> => {
  console.log('[generateVideoFission] 通过后端API生成视频...');
  const clientTaskId = request.clientTaskId || createVideoGenerationTaskId();
  // 提交接口仍在传输时即可点击取消；后端会先暂存该任务 ID 的取消意图。
  onTaskCreated?.(clientTaskId, true, true);

  try {
    // 按画布连线顺序准备参考素材；首尾帧模式由调用方先裁成前两张图。
    const imageAssets = request.assets.filter(
      (a) => a.type === AssetType.IMAGE,
    );
    const videoAssets = request.assets.filter(
      (a) => a.type === AssetType.VIDEO,
    );
    const audioAssets = request.assets.filter(
      (a) => a.type === AssetType.AUDIO,
    );
    const fileAssets = request.assets.filter((a) => a.type === AssetType.FILE);
    const linkAssets = request.assets.filter((a) => a.type === AssetType.LINK);
    if (
      (fileAssets.length > 0 || linkAssets.length > 0) &&
      !isWan3VideoModel(request.videoModel)
    ) {
      throw new Error('文档和网页参考仅万相 3.0 全能参考支持');
    }
    if (
      audioAssets.length > 0 &&
      !isWan3VideoModel(request.videoModel) &&
      !isSeedance25VideoModel(request.videoModel)
    ) {
      throw new Error('音频参考请使用万相 3.0 或 Seedance 2.5 全能参考');
    }
    if (isSeedance25VideoModel(request.videoModel)) {
      if (audioAssets.length > 10)
        throw new Error('Seedance 2.5 最多 10 段参考音频');
      await validateSeedance25ReferenceAudios(
        audioAssets
          .map((asset) => asset.file)
          .filter((file): file is File => Boolean(file)),
      );
    }
    if (fileAssets.length > 0 && linkAssets.length > 0) {
      throw new Error('万相 3.0 文档参考与网页参考不能同时使用');
    }
    if (fileAssets.length > WAN3_MAX_REFERENCE_FILES) {
      throw new Error('万相 3.0 全能参考最多 1 份文档');
    }
    if (linkAssets.length > WAN3_MAX_REFERENCE_LINKS) {
      throw new Error('万相 3.0 全能参考最多 1 个网页');
    }
    const omniTotal =
      imageAssets.length +
      videoAssets.length +
      audioAssets.length +
      fileAssets.length +
      linkAssets.length;
    if (isWan3VideoModel(request.videoModel)) {
      if (imageAssets.length > WAN3_MAX_REFERENCE_IMAGES) {
        throw new Error(
          `万相 3.0 全能参考最多 ${WAN3_MAX_REFERENCE_IMAGES} 张参考图`,
        );
      }
      if (videoAssets.length > WAN3_MAX_REFERENCE_VIDEOS) {
        throw new Error(
          `万相 3.0 全能参考最多 ${WAN3_MAX_REFERENCE_VIDEOS} 段参考视频`,
        );
      }
      if (omniTotal > WAN3_MAX_OMNI_MEDIA) {
        throw new Error(`万相 3.0 全能参考最多 ${WAN3_MAX_OMNI_MEDIA} 个素材`);
      }
      await validateWan3OmniReferenceVideos(
        videoAssets
          .map((asset) => asset.file)
          .filter((file): file is File => Boolean(file)),
      );
      await validateWan3OmniReferenceAudios(
        audioAssets
          .map((asset) => asset.file)
          .filter((file): file is File => Boolean(file)),
      );
      validateWan3OmniReferenceFiles(
        fileAssets
          .map((asset) => asset.file)
          .filter((file): file is File => Boolean(file)),
      );
    }
    const referenceImages = [];
    for (const imageAsset of imageAssets) {
      // 同时携带编号和原图，后端只选择一种输入，避免重复首帧或跨提供方丢图。
      const payload = await buildFileReferencePayload(imageAsset);
      if (payload) referenceImages.push(payload);
    }
    const referenceImage = referenceImages[0] || null;

    const referenceVideos = [];
    for (const videoAsset of videoAssets) {
      if (videoAsset.file && request.videoModel === 'wan2.7-r2v') {
        await validateWanR2VReferenceVideo(videoAsset.file);
      }
      if (videoAsset.file) {
        onProgress?.(
          `正在读取参考视频：${videoAsset.file.name || '未命名视频'}...`,
        );
      }
      const payload = await buildFileReferencePayload(videoAsset);
      if (payload) referenceVideos.push(payload);
    }

    const referenceAudios = [];
    for (const audioAsset of audioAssets) {
      if (audioAsset.file) {
        onProgress?.(
          `正在读取参考音频：${audioAsset.file.name || '未命名音频'}...`,
        );
      }
      const payload = await buildFileReferencePayload(audioAsset);
      if (payload) referenceAudios.push(payload);
    }

    let referenceFile: {
      assetUri?: string;
      data?: string;
      mimeType?: string;
    } | null = null;
    for (const fileAsset of fileAssets) {
      if (fileAsset.file) {
        onProgress?.(
          `正在读取参考文档：${fileAsset.file.name || '未命名文档'}...`,
        );
      }
      const payload = await buildFileReferencePayload(fileAsset);
      if (payload) {
        referenceFile = payload;
        break;
      }
    }

    const referenceLink = linkAssets
      .map((asset) => asset.url.trim())
      .find((url) => isPublicHttpUrl(url));
    if (linkAssets.length > 0 && !referenceLink) {
      throw new Error('网页参考需要公开的 http(s) 链接');
    }

    const payload = {
      prompt: request.prompt,
      batchCount: request.batchCount,
      generationMode: request.videoGenerationMode,
      referenceImage,
      referenceImages,
      referenceVideos,
      referenceAudios,
      referenceFile,
      referenceLink: referenceLink || undefined,
      extensionCount: request.extensionCount || 0,
      duration: request.duration,
      aspectRatio: request.aspectRatio || '16:9',
      resolution: request.resolution || '1080p',
      model: request.videoModel || 'veo-3.1-fast-generate-preview',
      clientTaskId,
    };

    let responseData: any | null = null;
    let shouldFallbackToSync = false;

    try {
      onProgress?.(
        referenceVideos.length > 0 ||
          referenceAudios.length > 0 ||
          Boolean(referenceFile) ||
          Boolean(referenceLink)
          ? '正在上传参考素材并提交百炼任务...'
          : '正在提交视频生成任务...',
      );
      const submitResponse = await fetch(`${API_BASE}/generate-videos/submit`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload),
      });

      const submitData = await readVideoApiResponse<{
        can_cancel?: boolean;
        task_id?: string;
      }>(submitResponse);
      if (submitData?.task_id) {
        console.log(
          `[generateVideoFission] 已提交后台任务: ${submitData.task_id}`,
        );
        onTaskCreated?.(
          submitData.task_id,
          submitData.can_cancel === true,
          false,
        );
        responseData = await waitForVideoGenerationTask(
          submitData.task_id,
          onProgress,
        );
      } else {
        shouldFallbackToSync = true;
      }
    } catch (err) {
      if (err instanceof VideoGenerationError) throw err;
      console.warn(
        '[generateVideoFission] 后台任务通道不可用，回退同步接口:',
        err,
      );
      shouldFallbackToSync = true;
    }

    if (shouldFallbackToSync) {
      // 同步兼容接口没有任务取消通道，不能继续把提交阶段的 X 误显示为可用。
      onTaskCreated?.(clientTaskId, false, false);
      onProgress?.('后台进度通道不可用，正在使用同步生成接口...');
      const response = await fetch(`${API_BASE}/generate-videos`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(payload),
      });

      responseData = await readVideoApiResponse(response);
    }

    const results = responseData?.results;
    if (!Array.isArray(results) || results.length === 0) {
      throw new Error('视频生成失败：后端未返回有效结果');
    }

    console.log(`[generateVideoFission] 后端返回 ${results.length} 个视频`);

    // 处理视频并转换为前端可用的格式
    const generatedResults: GeneratedResult[] = [];
    for (const result of results) {
      try {
        let videoUrl: string;
        const downloadUrl = resolveVideoDownloadUrl(result);
        if (!downloadUrl) {
          console.error(
            `[generateVideoFission] 后端未返回视频地址: ${result.id}`,
          );
          continue;
        }

        // 检查是否是data URL (base64编码)
        if (downloadUrl.startsWith('data:')) {
          // 直接使用base64数据创建Blob
          const response = await fetch(downloadUrl);
          const videoBlob = await response.blob();
          videoUrl = URL.createObjectURL(videoBlob);
          console.log(
            `[generateVideoFission] 视频 ${result.id} 从base64转换完成`,
          );
        } else {
          // MinIO 对象优先走同源后端流接口，供应商地址仅作为旧数据兼容。
          const videoResponse = await fetch(downloadUrl);
          if (!videoResponse.ok) {
            console.error(
              `[generateVideoFission] 下载视频失败: ${result.id}, status: ${videoResponse.status}`,
            );
            continue;
          }

          const videoBlob = await videoResponse.blob();
          videoUrl = URL.createObjectURL(videoBlob);
          console.log(`[generateVideoFission] 视频 ${result.id} 从URL下载完成`);
        }

        generatedResults.push({
          id: result.id,
          type: AssetType.VIDEO,
          // videoUrl 是当前页面播放用的 blob: 地址；画布持久化必须使用对象键对应的稳定流地址。
          persistentUrl: result.object_name ? downloadUrl : undefined,
          url: videoUrl,
          prompt: result.prompt,
          createdAt: new Date(),
          videoData: {
            operation: { name: result.operation_name },
            extensionCount: result.extension_count || 0,
            videoId: result.video_id,
            aspectRatio: result.aspect_ratio,
            modelName: result.model_name,
            resolution: result.resolution,
            provider: result.provider,
            providerModel: result.provider_model,
            providerVideoUrl: result.provider_video_url,
            duration: Number(result.duration) || undefined,
            extensionMode: result.extension_mode,
            extensionMaxDuration:
              Number(result.extension_max_duration) || undefined,
            capability: result.capability,
            historyRecordId: result.history_record_id,
          },
        });

        console.log(
          `[generateVideoFission] 视频 ${generatedResults.length} 处理完成`,
        );
      } catch (downloadError) {
        console.error(`[generateVideoFission] 处理视频失败:`, downloadError);
      }
    }

    if (generatedResults.length === 0) {
      throw new Error('所有视频下载失败');
    }

    return generatedResults;
  } catch (error) {
    console.error('[generateVideoFission] Error:', error);
    throw error;
  }
};

export const editVideoWithProvider = async (
  sourceVideo: UploadedAsset,
  prompt: string,
  model: string = 'wan2.7-videoedit',
  resolution: string = '720P',
  aspectRatio?: string,
  referenceAssets: UploadedAsset[] = [],
  onProgress?: (message: string) => void,
): Promise<GeneratedResult> => {
  if (!sourceVideo.file) {
    throw new Error('原始视频文件不存在');
  }

  onProgress?.(`正在读取原视频：${sourceVideo.file.name || '未命名视频'}...`);
  const videoBase64 = await fileToBase64(sourceVideo.file);
  const referenceImages = [];
  const referenceVideos = [];
  for (const asset of referenceAssets) {
    if (!asset.file) continue;
    onProgress?.(
      `正在读取参考素材：${asset.file.name || asset.name || '未命名素材'}...`,
    );
    const data = await fileToBase64(asset.file);
    if (asset.type === AssetType.IMAGE) {
      referenceImages.push({ data, mimeType: asset.file.type });
    } else if (asset.type === AssetType.VIDEO) {
      referenceVideos.push({ data, mimeType: asset.file.type });
    }
  }

  const payload = {
    prompt,
    model,
    resolution,
    aspectRatio,
    video: {
      data: videoBase64,
      mimeType: sourceVideo.file.type || 'video/mp4',
    },
    referenceImages,
    referenceVideos,
  };

  let data: any | null = null;
  let shouldFallbackToSync = false;

  try {
    onProgress?.('正在提交百炼视频编辑后台任务...');
    const submitResponse = await fetch(`${API_BASE}/edit-video/submit`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });

    const submitData = await readVideoApiResponse<{ task_id?: string }>(
      submitResponse,
    );
    if (submitData?.task_id) {
      data = await waitForVideoGenerationTask(submitData.task_id, onProgress);
    } else {
      shouldFallbackToSync = true;
    }
  } catch (err) {
    if (err instanceof VideoGenerationError) throw err;
    console.warn(
      '[editVideoWithProvider] 后台任务通道不可用，回退同步接口:',
      err,
    );
    shouldFallbackToSync = true;
  }

  if (shouldFallbackToSync) {
    onProgress?.('后台进度通道不可用，正在使用同步视频编辑接口...');
    const response = await fetch(`${API_BASE}/edit-video`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(payload),
    });

    data = await readVideoApiResponse(response);
  }

  const result = data?.result;
  if (!result?.video_url) {
    throw new Error('视频编辑失败：后端未返回有效结果');
  }

  onProgress?.('视频编辑完成，正在下载结果...');
  const videoResponse = await fetch(result.video_url);
  if (!videoResponse.ok) {
    throw new Error(`视频编辑成功但下载失败：HTTP ${videoResponse.status}`);
  }
  const videoBlob = await videoResponse.blob();
  const videoUrl = URL.createObjectURL(videoBlob);

  return {
    id: result.id || `video_edit_${Date.now()}`,
    type: AssetType.VIDEO,
    url: videoUrl,
    prompt,
    createdAt: new Date(),
    videoData: {
      operation: { name: result.task_id },
      extensionCount: 0,
      videoId: result.video_id || result.task_id,
      aspectRatio: result.aspect_ratio,
      modelName: result.model_name,
      resolution: result.resolution,
      provider: result.provider,
      providerModel: result.provider_model,
      providerVideoUrl: result.provider_video_url,
      duration: Number(result.duration) || undefined,
      capability: result.capability,
    },
  };
};

export const generateMusic = async (
  request: GenerationRequest,
): Promise<GeneratedResult[]> => {
  try {
    const imageAssets = request.assets.filter(
      (a) => a.type === AssetType.IMAGE,
    );
    const referenceImages = [];

    for (const imageAsset of imageAssets) {
      try {
        if (imageAsset.file) {
          const base64 = await fileToBase64(imageAsset.file);
          referenceImages.push({
            data: base64,
            mimeType: imageAsset.file.type,
          });
        }
      } catch (err) {
        console.error('[generateMusic] 参考图片处理失败:', err);
      }
    }

    const response = await fetch(`${API_BASE}/generate-music`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        prompt: request.prompt,
        batchCount: request.batchCount,
        model: request.musicModel || 'lyria-3-clip-preview',
        referenceImages,
      }),
    });

    const responseData = await readCanvasModelApiResponse<{
      results?: Array<Record<string, unknown>>;
    }>(response);
    const results = responseData?.results;
    if (!Array.isArray(results) || results.length === 0) {
      throw new Error('音乐生成失败：后端未返回有效结果');
    }

    return results.map((result: any) => ({
      id: result.id,
      type: AssetType.AUDIO,
      url: result.audio_url,
      prompt: result.prompt,
      createdAt: new Date(),
      audioData: {
        mimeType: result.mime_type,
        modelName: result.model_name,
        text: result.text,
      },
    }));
  } catch (error) {
    console.error('[generateMusic] Error:', error);
    throw new Error(
      toFormattedGenerationMessage(error, '音乐生成失败，请根据提示调整后重试'),
    );
  }
};

export const generateTTS = async (
  request: GenerationRequest,
): Promise<GeneratedResult[]> => {
  try {
    const response = await fetch(`${API_BASE}/generate-tts`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        prompt: request.prompt,
        batchCount: request.batchCount,
        model: request.ttsModel,
        speakerMode: request.parameters?.speakerMode || 'single',
        voiceName: request.parameters?.voiceName || 'Kore',
        speakerConfigs: request.parameters?.speakerConfigs || [],
        voiceStyle: request.parameters?.voiceStyle || '',
        speechRate: request.parameters?.speechRate || 'normal',
      }),
    });

    const responseData = await readCanvasModelApiResponse<{
      results?: Array<Record<string, unknown>>;
    }>(response);
    const results = responseData?.results;
    if (!Array.isArray(results) || results.length === 0) {
      throw new Error('TTS 生成失败：后端未返回有效结果');
    }

    return results.map((result: any) => ({
      id: result.id,
      type: AssetType.AUDIO,
      url: result.audio_url,
      prompt: result.prompt,
      createdAt: new Date(),
      audioData: {
        mimeType: result.mime_type,
        modelName: result.model_name,
        text: result.text,
        speakerMode: result.speaker_mode,
        voiceName: result.voice_name,
        speakerConfigs: result.speaker_configs,
        voiceStyle: result.voice_style,
        speechRate: result.speech_rate,
      },
    }));
  } catch (error) {
    console.error('[generateTTS] Error:', error);
    throw new Error(
      toFormattedGenerationMessage(error, '配音生成失败，请根据提示调整后重试'),
    );
  }
};

export const generateTTSStylePrompt = async (
  description: string,
): Promise<string> => {
  const response = await fetch(`${API_BASE}/generate-tts-style-prompt`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ description }),
  });

  const data = await readCanvasModelApiResponse<{ style_prompt?: string }>(
    response,
  );
  if (!data?.style_prompt) {
    throw new Error('音色提示词生成失败：后端未返回有效结果');
  }

  return data.style_prompt;
};

export const getTTSPreview = async (request: {
  prompt: string;
  model?: string;
  voiceName: string;
  voiceStyle: string;
  speechRate?: string;
}): Promise<{
  audioUrl: string;
  cached: boolean;
  objectName?: string;
  cacheKey?: string;
}> => {
  const response = await fetch(`${API_BASE}/tts-preview`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      prompt: request.prompt,
      model: request.model,
      voiceName: request.voiceName,
      voiceStyle: request.voiceStyle,
      speechRate: request.speechRate || 'normal',
    }),
  });

  const data = await readCanvasModelApiResponse<{
    audio_url?: string;
    cache_key?: string;
    cached?: boolean;
    object_name?: string;
  }>(response);
  if (!data?.audio_url) {
    throw new Error('音色试听失败：后端未返回音频');
  }

  return {
    audioUrl: data.audio_url,
    cached: Boolean(data.cached),
    objectName: data.object_name,
    cacheKey: data.cache_key,
  };
};

/**
 * 延长视频
 * 注意：这个功能可能需要额外的后端实现
 */
export const extendVideo = async (
  video: GeneratedResult,
  additionalExtensions: number,
  prompt: string,
): Promise<GeneratedResult> => {
  const videoId = video.videoData?.videoId;
  const isBailianContinuation =
    video.videoData?.provider === 'bailian' &&
    video.videoData?.extensionMode === 'bailian_continuation';
  if (!isBailianContinuation && !videoId) {
    throw new Error(
      '该视频没有可用的延长引用（videoId），请重新生成视频后再延长',
    );
  }
  if (isBailianContinuation && !video.videoData?.providerVideoUrl) {
    throw new Error('该百炼视频缺少可续写的供应商结果地址，请重新生成后再试');
  }

  console.log(
    `[extendVideo] videoId=${videoId}, additionalExtensions=${additionalExtensions}`,
  );
  console.log(
    `[extendVideo] prompt: ${prompt ? prompt.substring(0, 100) : '(using original prompt)'}`,
  );

  const response = await fetch(`${API_BASE}/extend-video`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(
      isBailianContinuation
        ? {
            provider: 'bailian',
            model: video.videoData?.modelName,
            sourceVideoUrl: video.videoData?.providerVideoUrl,
            currentDuration: video.videoData?.duration,
            targetDuration: additionalExtensions,
            resolution: video.videoData?.resolution,
            prompt: prompt || video.prompt,
          }
        : {
            videoId,
            additionalExtensions,
            prompt: prompt || video.prompt,
          },
    ),
  });

  const responseData = await readVideoApiResponse<{
    result?: VideoBackendResult;
  }>(response);
  const result = responseData?.result;
  if (!result?.video_url) {
    throw new Error('视频延长失败：后端未返回有效结果');
  }

  // 将 base64 视频转换为 blob URL
  let videoUrl: string;
  try {
    const videoResponse = await fetch(result.video_url);
    const videoBlob = await videoResponse.blob();
    videoUrl = URL.createObjectURL(videoBlob);
  } catch (blobError) {
    console.error('[extendVideo] 视频下载/转换失败:', blobError);
    throw new Error('视频延长成功但下载失败，请重试');
  }

  return {
    id: `ext_${Date.now()}`,
    type: AssetType.VIDEO,
    url: videoUrl,
    prompt: prompt || video.prompt,
    createdAt: new Date(),
    videoData: {
      operation: video.videoData?.operation,
      extensionCount: isBailianContinuation ? 0 : result.extension_count,
      videoId: result.video_id,
      aspectRatio: result.aspect_ratio || video.videoData?.aspectRatio,
      modelName: result.model_name || video.videoData?.modelName,
      resolution: result.resolution || video.videoData?.resolution,
      provider: result.provider || video.videoData?.provider,
      providerModel: result.provider_model || video.videoData?.providerModel,
      providerVideoUrl: result.provider_video_url,
      duration: Number(result.duration) || video.videoData?.duration,
      extensionMode: isBailianContinuation
        ? 'bailian_continuation'
        : video.videoData?.extensionMode,
      extensionMaxDuration: video.videoData?.extensionMaxDuration,
      capability: result.capability || video.videoData?.capability,
    },
  };
};

/**
 * 图片编辑（使用蒙版）
 * 注意：这个功能可能需要额外的后端实现
 */
export const editImageWithMask = async (
  originalAsset: UploadedAsset,
  maskBase64: string,
  instruction: string,
  referenceImage?: File,
  imageModel?: string,
  imageSize?: string,
): Promise<GeneratedResult> => {
  if (!originalAsset.file) {
    throw new Error('原始文件不存在');
  }

  // 将原始图片转换为 base64
  const originalBase64 = await fileToBase64(originalAsset.file);

  // 构建参考图片数组
  const referenceImages: { data: string; mimeType: string }[] = [
    { data: originalBase64, mimeType: originalAsset.file.type },
    { data: maskBase64, mimeType: 'image/png' },
  ];

  // 如果有参考图片，添加到数组
  if (referenceImage) {
    const referenceBase64 = await fileToBase64(referenceImage);
    referenceImages.push({
      data: referenceBase64,
      mimeType: referenceImage.type,
    });
  }

  // 根据原图实际尺寸计算最匹配的 aspectRatio
  const detectAspectRatio = (): Promise<string> => {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const w = img.width;
        const h = img.height;
        const ratio = w / h;
        // 支持的比例及其数值
        const ratios: [string, number][] = [
          ['1:1', 1],
          ['2:3', 2 / 3],
          ['3:2', 3 / 2],
          ['3:4', 3 / 4],
          ['4:3', 4 / 3],
          ['4:5', 4 / 5],
          ['5:4', 5 / 4],
          ['9:16', 9 / 16],
          ['16:9', 16 / 9],
          ['21:9', 21 / 9],
        ];
        let best = '1:1';
        let minDiff = Infinity;
        for (const [name, val] of ratios) {
          const diff = Math.abs(ratio - val);
          if (diff < minDiff) {
            minDiff = diff;
            best = name;
          }
        }
        resolve(best);
      };
      img.onerror = () => resolve('1:1');
      img.src = originalAsset.url;
    });
  };

  const aspectRatio = await detectAspectRatio();
  console.log(`[editImageWithMask] 检测到原图比例: ${aspectRatio}`);

  const response = await fetch(`${API_BASE}/edit-image`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      prompt: instruction,
      referenceImages: referenceImages,
      aspectRatio,
      imageSize: imageSize || '1K',
      model: imageModel,
    }),
  });

  const data = await readCanvasModelApiResponse<{
    result?: { id: string; url: string };
  }>(response);

  if (!data.result) {
    throw new Error('图片编辑失败：未返回结果');
  }

  return {
    id: data.result.id,
    url: data.result.url,
    type: AssetType.IMAGE,
    prompt: instruction,
    createdAt: new Date(),
  };
};

/**
 * 批量编辑图片
 * 一次性对多张图片应用相同的提示词和参考图片
 */
export const batchEditImages = async (
  images: UploadedAsset[],
  prompt: string,
  referenceImage?: File | null,
  imageModel?: string,
  imageSize?: string,
  onProgress?: (progress: number) => void,
): Promise<GeneratedResult[]> => {
  console.log('[batchEditImages] 开始批量编辑图片...');
  console.log(`[batchEditImages] 图片数量: ${images.length}`);

  try {
    // 准备所有图片的 base64 数据
    const imageDataList = [];
    for (const image of images) {
      if (image.file) {
        const base64 = await fileToBase64(image.file);
        imageDataList.push({
          data: base64,
          mimeType: image.file.type,
        });
      } else {
        throw new Error(`图片 ${image.id} 缺少文件数据`);
      }
    }

    // 准备参考图片（如果有）
    let referenceImageData = null;
    if (referenceImage) {
      const refBase64 = await fileToBase64(referenceImage);
      referenceImageData = {
        data: refBase64,
        mimeType: referenceImage.type,
      };
    }

    console.log(`[batchEditImages] 准备编辑 ${imageDataList.length} 张图片`);
    console.log(
      `[batchEditImages] 参考图片: ${referenceImageData ? '是' : '否'}`,
    );

    // 调用后端API
    const response = await fetch(`${API_BASE}/batch-edit-images`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({
        images: imageDataList,
        prompt,
        referenceImage: referenceImageData,
        model: imageModel,
        imageSize,
      }),
    });

    const { results } = await readCanvasModelApiResponse<{
      results: Array<Record<string, unknown>>;
    }>(response);
    console.log(`[batchEditImages] 后端返回 ${results.length} 张编辑后的图片`);

    // 转换为前端可用的格式
    const generatedResults: GeneratedResult[] = results.map((result: any) => ({
      id: result.id,
      type: AssetType.IMAGE,
      url: result.image_url,
      prompt: prompt,
      createdAt: new Date(),
    }));

    if (onProgress) {
      onProgress(100);
    }

    return generatedResults;
  } catch (error) {
    console.error('[batchEditImages] Error:', error);
    throw error;
  }
};
