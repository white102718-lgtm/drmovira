import type { CanvasNodeResult } from '../types';
import {
  getHistoryAssetDownloadUrl,
  getHistoryAssetFilename,
  getHistoryAssetPreviewUrl,
} from '../../../utils/historyAssetUtils';

export const getCanvasImageDownloadName = (name: string) => (
  /\.(?:avif|bmp|gif|jpe?g|png|webp)$/i.test(name) ? name : `${name || 'canvas-image'}.png`
);

export const getCanvasVideoDownloadName = (name: string) => (
  /\.(?:m4v|mov|mp4|webm)$/i.test(name) ? name : `${name || 'canvas-video'}.mp4`
);

export const getStableCanvasMediaUrl = (
  url: string,
  type: CanvasNodeResult['type'],
  name?: string,
) => getHistoryAssetPreviewUrl({ url, type: type.toUpperCase(), name });

export const getCanvasMediaPreviewUrl = (
  url: string,
  type: CanvasNodeResult['type'] = 'image',
  name?: string,
) => (
  getHistoryAssetPreviewUrl({ url, type: type.toUpperCase(), name })
);

export const downloadCanvasMedia = async (
  url: string,
  name: string,
  type: CanvasNodeResult['type'],
): Promise<string> => {
  const asset = { url, type: type.toUpperCase(), name };
  const response = await fetch(getHistoryAssetDownloadUrl(asset));
  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const blob = await response.blob();
  if (!blob.size) throw new Error('媒体内容为空');

  const filename = getHistoryAssetFilename(asset, `canvas-${type}`, 0);
  const typedBlob = type === 'image' && /\.png$/i.test(filename) && blob.type !== 'image/png'
    ? blob.slice(0, blob.size, 'image/png')
    : blob;
  const objectUrl = URL.createObjectURL(typedBlob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  return filename;
};

export const downloadCanvasImage = (url: string, name: string): Promise<string> => (
  downloadCanvasMedia(url, getCanvasImageDownloadName(name), 'image')
);
