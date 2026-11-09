import { API_BASE_URL as API_ROOT } from '../services/runtimeConfig';

export interface HistoryAssetReference {
  url: string;
  type: string;
  name?: string;
  object_name?: string;
}

const decodePath = (value: string): string => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};

const cleanObjectName = (value?: string | null): string | null => {
  if (!value) return null;
  const cleaned = decodePath(value)
    .split('?')[0]
    .split('#')[0]
    .replace(/^\/+/, '')
    .trim();

  if (!cleaned || /^(?:https?:|blob:|data:)/i.test(cleaned)) return null;

  // 旧版画布曾把 API 路由本身写成对象名，例如
  // `adgen-api/api/minio/stream/generated/...`。这不是 MinIO 对象键，
  // 需要移除路由前缀，才能继续读取历史画布的媒体。
  const streamPathMatch = cleaned.match(
    /(?:^|\/)(?:adgen-api\/)?api\/minio\/(?:stream|download|presigned-url)\/(.+)$/i,
  );
  if (streamPathMatch?.[1]) return streamPathMatch[1].replace(/^\/+/, '');

  return cleaned;
};

const extractObjectNameFromUrl = (rawUrl?: string): string | null => {
  if (!rawUrl || /^(?:blob:|data:)/i.test(rawUrl)) return null;

  try {
    const parsed = new URL(rawUrl, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    const pathname = decodePath(parsed.pathname);

    const proxyMatch = pathname.match(/\/minio-proxy\/[^/]+\/(.+)$/i);
    if (proxyMatch?.[1]) return cleanObjectName(proxyMatch[1]);

    // 测试/生产后端会把内部 MinIO 的预签名地址转发为
    // /api/minio/presigned-proxy/<bucket>/<object>。跳过 bucket，避免把它
    // 误拼入后续稳定的 /minio/stream/<object> 地址。
    const presignedProxyMatch = pathname.match(
      // Older canvas records used BACKEND_PUBLIC_URL ending in /adgen-api and
      // therefore persisted /adgen-api/minio/... (without the current /api
      // segment).  Both forms identify the same MinIO object and must be
      // converted to the stable stream URL instead of retaining an expiring
      // presigned link.
      /\/(?:api\/|adgen-api\/(?:api\/)?){0,1}minio\/presigned-proxy\/[^/]+\/(.+)$/i,
    );
    if (presignedProxyMatch?.[1]) {
      return cleanObjectName(presignedProxyMatch[1]);
    }

    const apiMatch = pathname.match(/\/api\/minio\/(?:stream|download|presigned-url)\/(.+)$/i);
    if (apiMatch?.[1]) return cleanObjectName(apiMatch[1]);

    const bucketMatch = pathname.match(/\/agent-img-video\/(.+)$/i);
    if (bucketMatch?.[1]) return cleanObjectName(bucketMatch[1]);
  } catch {
    // A plain object path is handled below.
  }

  if (/^(?:uploads|generated|imported|history)\//i.test(rawUrl)) {
    return cleanObjectName(rawUrl);
  }

  return null;
};

export const getHistoryAssetObjectName = (asset: HistoryAssetReference): string | null => {
  const explicitObjectName = cleanObjectName(asset.object_name);
  if (explicitObjectName) return explicitObjectName;

  const urlObjectName = extractObjectNameFromUrl(asset.url);
  if (urlObjectName) return urlObjectName;

  if (asset.name?.includes('/')) return cleanObjectName(asset.name);
  return null;
};

export const encodeHistoryObjectName = (objectName: string): string =>
  objectName.split('/').map((part) => encodeURIComponent(part)).join('/');

export const getHistoryAssetPreviewUrl = (asset: HistoryAssetReference): string => {
  const objectName = getHistoryAssetObjectName(asset);
  if (objectName) {
    return `${API_ROOT}/minio/stream/${encodeHistoryObjectName(objectName)}`;
  }
  return asset.url;
};

export const getHistoryAssetDownloadUrl = (asset: HistoryAssetReference): string => {
  const objectName = getHistoryAssetObjectName(asset);
  if (objectName) {
    return `${API_ROOT}/minio/download/${encodeHistoryObjectName(objectName)}`;
  }
  return asset.url;
};

const defaultExtensionForType = (type: string): string => {
  const normalized = (type || '').toUpperCase();
  if (normalized === 'VIDEO') return '.mp4';
  if (normalized === 'AUDIO') return '.mp3';
  if (normalized === 'FILE') return '.pdf';
  if (normalized === 'LINK') return '';
  return '.png';
};

// 兼容旧版本下载时附加的 UUID，避免旧文件名在再次下载或重新入库后持续叠加。
const LEGACY_HISTORY_UUID_SUFFIX =
  /(?:_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})+$/i;

const removeLegacyHistoryUuidSuffix = (filenameStem: string): string =>
  filenameStem.replace(LEGACY_HISTORY_UUID_SUFFIX, '');

export const getHistoryAssetFilename = (
  asset: HistoryAssetReference,
  fallbackPrefix: string,
  index: number,
): string => {
  const objectName = getHistoryAssetObjectName(asset);
  const candidate = asset.name?.split(/[\\/]/).pop() || objectName?.split('/').pop();
  const defaultExtension = defaultExtensionForType(asset.type);
  const extensionMatch = candidate?.match(/(\.[A-Za-z0-9]{1,10})$/);
  const candidateExtension = extensionMatch?.[1] || defaultExtension;
  const candidateStem = candidate
    ? extensionMatch ? candidate.slice(0, -candidateExtension.length) : candidate
    : `${fallbackPrefix}_${index + 1}`;
  // 对象存储已使用独立 UUID 目录区分同名文件，下载名必须保留用户可见原名。
  const safeStem = removeLegacyHistoryUuidSuffix(candidateStem) || `${fallbackPrefix}_${index + 1}`;
  return `${safeStem}${candidateExtension}`;
};

export const isTransientHistoryAsset = (asset: HistoryAssetReference): boolean =>
  /^blob:/i.test(asset.url) && !getHistoryAssetObjectName(asset);
