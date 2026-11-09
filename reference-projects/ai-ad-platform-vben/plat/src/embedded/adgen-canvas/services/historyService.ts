/**
 * 历史记录服务
 * 用于自动保存和管理生成历史记录
 */

import { authService } from './authService';
import { API_BASE_URL as API_ROOT } from './runtimeConfig';
import { uploadFileToMinioObject } from './minioService';
import {
  getHistoryAssetFilename,
  getHistoryAssetObjectName,
  type HistoryAssetReference,
} from '../utils/historyAssetUtils';

const API_BASE_URL = `${API_ROOT}/history`;

const getAuthHeaders = () => {
  const token = authService.getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
};

export interface HistoryAsset extends HistoryAssetReference {}

const prepareHistoryAsset = async (
  asset: HistoryAsset,
  generationType: HistoryRecord['generation_type'],
  direction: 'input' | 'output',
  index: number,
): Promise<HistoryAsset> => {
  const existingObjectName = getHistoryAssetObjectName(asset);
  if (existingObjectName) {
    return {
      ...asset,
      url: asset.url.split('?')[0],
      object_name: existingObjectName,
    };
  }

  if (!asset.url?.startsWith('blob:')) return asset;

  try {
    const response = await fetch(asset.url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const blob = await response.blob();
    if (!blob.size) throw new Error('素材内容为空');

    const filename = getHistoryAssetFilename(asset, direction, index);
    const file = new File([blob], filename, {
      type: blob.type || 'application/octet-stream',
    });
    const upload = await uploadFileToMinioObject(
      file,
      `history/${generationType}/${direction}/`,
    );

    return {
      ...asset,
      url: upload.url,
      name: asset.name || filename,
      object_name: upload.object_name,
    };
  } catch (error) {
    console.warn(`[历史记录] 无法持久化${direction === 'input' ? '输入素材' : '生成结果'}:`, error);
    return asset;
  }
};

export interface HistoryRecord {
  generation_type: 'batch_images' | 'edit_image' | 'video_fission' | 'extend_video' | 'music_generation' | 'tts_generation';
  input_assets: HistoryAsset[];
  prompt: string;
  generated_assets: HistoryAsset[];
  status: 'success' | 'failed' | 'pending';
  error_message?: string;
  metadata?: Record<string, any>;
  session_id?: string;
}

export interface SaveHistoryResponse {
  success: boolean;
  message: string;
  data?: {
    record_id: number;
    session_id: string;
    input_assets?: HistoryAsset[];
    generated_assets?: HistoryAsset[];
  };
}

/**
 * 保存生成记录到历史
 */
export async function saveHistoryRecord(record: HistoryRecord): Promise<SaveHistoryResponse | null> {
  try {
    const [inputAssets, generatedAssets] = await Promise.all([
      Promise.all(record.input_assets.map((asset, index) =>
        prepareHistoryAsset(asset, record.generation_type, 'input', index))),
      Promise.all(record.generated_assets.map((asset, index) =>
        prepareHistoryAsset(asset, record.generation_type, 'output', index))),
    ]);

    const persistentRecord: HistoryRecord = {
      ...record,
      input_assets: inputAssets,
      generated_assets: generatedAssets,
    };

    const response = await fetch(`${API_BASE_URL}/save`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(persistentRecord)
    });

    const data = await response.json();

    if (data.success) {
      console.log('[历史记录] 保存成功:', data.data);
      return data;
    } else {
      console.error('[历史记录] 保存失败:', data.message);
      return null;
    }
  } catch (error) {
    console.error('[历史记录] 保存出错:', error);
    return null;
  }
}

/**
 * 保存批量图片生成记录
 */
export async function saveBatchImagesRecord(
  inputAssets: Array<{ url: string; type: string; name?: string }>,
  prompt: string,
  generatedAssets: Array<{ url: string; type: string; name?: string }>,
  metadata?: Record<string, any>,
  sessionId?: string
): Promise<SaveHistoryResponse | null> {
  return saveHistoryRecord({
    generation_type: 'batch_images',
    input_assets: inputAssets,
    prompt,
    generated_assets: generatedAssets,
    status: 'success',
    session_id: sessionId,
    metadata: {
      batch_count: generatedAssets.length,
      ...(metadata || {})
    }
  });
}

/**
 * 保存图片编辑记录
 */
export async function saveEditImageRecord(
  inputAsset: { url: string; type: string; name?: string },
  prompt: string,
  generatedAssets: Array<{ url: string; type: string; name?: string }>,
  sessionId?: string
): Promise<void> {
  await saveHistoryRecord({
    generation_type: 'edit_image',
    input_assets: [inputAsset],
    prompt,
    generated_assets: generatedAssets,
    status: 'success',
    session_id: sessionId
  });
}

/**
 * 保存视频裂变记录
 */
export async function saveVideoFissionRecord(
  inputAssets: Array<{ url: string; type: string; name?: string }>,
  prompt: string,
  generatedAssets: Array<{ url: string; type: string; name?: string }>,
  extensionCount: number,
  extraMetadata?: Record<string, any>,
  sessionId?: string
): Promise<SaveHistoryResponse | null> {
  return saveHistoryRecord({
    generation_type: 'video_fission',
    input_assets: inputAssets,
    prompt,
    generated_assets: generatedAssets,
    status: 'success',
    session_id: sessionId,
    metadata: {
      extension_count: extensionCount,
      ...(extraMetadata || {})
    }
  });
}

/**
 * 保存视频延长记录
 */
export async function saveExtendVideoRecord(
  inputAsset: { url: string; type: string; name?: string },
  prompt: string,
  generatedAssets: Array<{ url: string; type: string; name?: string }>,
  extensionCount: number,
  sessionId?: string
): Promise<void> {
  await saveHistoryRecord({
    generation_type: 'extend_video',
    input_assets: [inputAsset],
    prompt,
    generated_assets: generatedAssets,
    status: 'success',
    session_id: sessionId,
    metadata: {
      extension_count: extensionCount
    }
  });
}

/**
 * 保存失败记录
 */
export async function saveFailedRecord(
  generationType: 'batch_images' | 'edit_image' | 'video_fission' | 'extend_video' | 'music_generation' | 'tts_generation',
  inputAssets: Array<{ url: string; type: string; name?: string }>,
  prompt: string,
  errorMessage: string,
  sessionId?: string
): Promise<void> {
  await saveHistoryRecord({
    generation_type: generationType,
    input_assets: inputAssets,
    prompt,
    generated_assets: [],
    status: 'failed',
    error_message: errorMessage,
    session_id: sessionId
  });
}

export async function saveMusicGenerationRecord(
  inputAssets: Array<{ url: string; type: string; name?: string }>,
  prompt: string,
  generatedAssets: Array<{ url: string; type: string; name?: string }>,
  metadata?: Record<string, any>,
  sessionId?: string
): Promise<SaveHistoryResponse | null> {
  return saveHistoryRecord({
    generation_type: 'music_generation',
    input_assets: inputAssets,
    prompt,
    generated_assets: generatedAssets,
    status: 'success',
    session_id: sessionId,
    metadata: metadata || {}
  });
}

export async function saveTTSGenerationRecord(
  inputAssets: Array<{ url: string; type: string; name?: string }>,
  prompt: string,
  generatedAssets: Array<{ url: string; type: string; name?: string }>,
  metadata?: Record<string, any>,
  sessionId?: string
): Promise<SaveHistoryResponse | null> {
  return saveHistoryRecord({
    generation_type: 'tts_generation',
    input_assets: inputAssets,
    prompt,
    generated_assets: generatedAssets,
    status: 'success',
    session_id: sessionId,
    metadata: metadata || {}
  });
}

/**
 * 生成唯一的会话ID
 */
export function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}
