import { readCanvasModelApiResponse } from '../../../api/canvas-model-response';
import { OFFICIAL_ASSET_LIBRARY_ENABLED } from '../officialAssetLibrary';
import { authService } from './authService';
import { BACKEND_URL } from './runtimeConfig';

export interface ByteplusAssetRecord {
  assetType: string;
  assetUri: string;
  contentHash?: string;
  id: string;
  limit: number;
  name: string;
  status: string;
  used: number;
}

export interface ByteplusAssetLibrarySnapshot {
  configured: boolean;
  items: ByteplusAssetRecord[];
  limit: number;
  used: number;
}

function getHeaders(): HeadersInit {
  const token = authService.getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function registerByteplusAsset(payload: {
  assetType: 'image' | 'video';
  name?: string;
  url: string;
}): Promise<ByteplusAssetRecord> {
  if (!OFFICIAL_ASSET_LIBRARY_ENABLED) {
    throw new Error('官方素材库暂未开放');
  }
  const response = await fetch(`${BACKEND_URL}/api/ai/byteplus-assets`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(payload),
  });
  return readCanvasModelApiResponse<ByteplusAssetRecord>(response);
}
