// MinIO service that communicates with Flask backend API
// This replaces direct S3 API calls with HTTP requests to the backend
import { BACKEND_URL } from './runtimeConfig';

const API_BASE = `${BACKEND_URL}/api/minio`;

// Cache management
interface CacheEntry {
  presignedUrl: string;
  expiresAt: number;
}

const presignedUrlCache = new Map<string, CacheEntry>();

interface FileListCache {
  files: Array<{ name: string; size: number; lastModified: Date; url: string; presignedUrl?: string }>;
  timestamp: number;
}
const fileListCache = new Map<string, FileListCache>();

interface PagedFileListCache {
  files: Array<{ name: string; size: number; lastModified: Date; url: string; presignedUrl?: string }>;
  hasMore: boolean;
  totalCount: number;
  totalPages: number;
  timestamp: number;
}
const pagedFileListCache = new Map<string, PagedFileListCache>();

// Cache duration configuration
const PRESIGNED_URL_CACHE_DURATION = 50 * 60 * 1000; // 50 minutes
const FILE_LIST_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
const MAX_PRESIGNED_URL_CACHE_SIZE = 500;
const MAX_FILE_LIST_CACHE_SIZE = 20;

export interface MinioUploadResult {
  success: boolean;
  object_name: string;
  url: string;
  size?: number;
  error?: string;
}

const trimOldestEntries = <K, V>(cache: Map<K, V>, maxSize: number): void => {
  while (cache.size > maxSize) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey === undefined) break;
    cache.delete(oldestKey);
  }
};

/**
 * Ensure bucket exists (handled by backend)
 */
export const ensureBucketExists = async (): Promise<void> => {
  // Backend handles this automatically
  console.log('Bucket existence check handled by backend');
};

/**
 * Upload file to MinIO via backend API
 * @param file - File to upload
 * @param folder - Optional folder path (e.g., 'uploads/', 'generated/')
 * @returns URL of the uploaded file
 */
export const uploadFileToMinioObject = async (
  file: File,
  folder: string = 'uploads/',
  signal?: AbortSignal,
): Promise<MinioUploadResult> => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('folder', folder);

    const response = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
      signal,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Upload failed: ${response.statusText}`);
    }

    const result = await response.json();
    console.log(`File uploaded successfully: ${result.object_name}`);

    return result;
  } catch (error) {
    console.error('Error uploading file to MinIO:', error);
    throw error;
  }
};

export const uploadFileToMinio = async (
  file: File,
  folder: string = 'uploads/'
): Promise<string> => {
  const result = await uploadFileToMinioObject(file, folder);
  return result.url;
};

/**
 * Get file URL from MinIO
 * @param objectName - Object name
 * @returns Public URL of the file
 */
export const getFileUrl = async (objectName: string): Promise<string> => {
  try {
    const response = await fetch(`${API_BASE}/presigned-url/${encodeURIComponent(objectName)}`);

    if (!response.ok) {
      throw new Error(`Failed to get URL: ${response.statusText}`);
    }

    const result = await response.json();
    return result.url;
  } catch (error) {
    console.error('Error getting file URL:', error);
    throw error;
  }
};

/**
 * Generate presigned URL for temporary file access (with caching)
 * @param objectName - Object name
 * @param expiresIn - Expiration time in seconds (default 3600)
 * @returns Presigned URL
 */
export const getPresignedUrl = async (
  objectName: string,
  expiresIn: number = 3600
): Promise<string> => {
  try {
    const now = Date.now();

    // Check cache
    const cached = presignedUrlCache.get(objectName);
    if (cached && cached.expiresAt > now) {
      console.log(`[Cache Hit] Using cached presigned URL for: ${objectName}`);
      presignedUrlCache.delete(objectName);
      presignedUrlCache.set(objectName, cached);
      return cached.presignedUrl;
    }

    // Cache miss or expired, generate new presigned URL
    console.log(`[Cache Miss] Generating new presigned URL for: ${objectName}`);

    const expiresInHours = Math.ceil(expiresIn / 3600);
    const response = await fetch(
      `${API_BASE}/presigned-url/${encodeURIComponent(objectName)}?expires=${expiresInHours}`
    );

    if (!response.ok) {
      throw new Error(`Failed to generate presigned URL: ${response.statusText}`);
    }

    const result = await response.json();
    const presignedUrl = result.url;

    // Store in cache
    presignedUrlCache.set(objectName, {
      presignedUrl,
      expiresAt: now + PRESIGNED_URL_CACHE_DURATION,
    });
    trimOldestEntries(presignedUrlCache, MAX_PRESIGNED_URL_CACHE_SIZE);

    return presignedUrl;
  } catch (error) {
    console.error('Error generating presigned URL:', error);
    throw error;
  }
};

/**
 * Download file from MinIO
 * @param objectName - Object name
 * @returns File object
 */
export const downloadFileFromMinio = async (objectName: string): Promise<File> => {
  try {
    const response = await fetch(`${API_BASE}/download/${encodeURIComponent(objectName)}`);

    if (!response.ok) {
      throw new Error(`Download failed: ${response.statusText}`);
    }

    const blob = await response.blob();
    const contentType = response.headers.get('content-type') || 'application/octet-stream';
    const fileName = objectName.split('/').pop() || 'file';

    const file = new File([blob], fileName, { type: contentType });

    return file;
  } catch (error) {
    console.error('Error downloading file from MinIO:', error);
    throw error;
  }
};

/**
 * List all files in the bucket (with caching)
 * @param prefix - Optional prefix filter (e.g., 'uploads/', 'generated/')
 * @param maxResults - Maximum number of results
 * @param forceRefresh - Force refresh, skip cache
 * @returns List of files
 */
export const listFiles = async (
  prefix: string = '',
  maxResults: number = 100000,
  forceRefresh: boolean = false
): Promise<Array<{ name: string; size: number; lastModified: Date; url: string; presignedUrl?: string }>> => {
  try {
    const now = Date.now();
    const cacheKey = prefix;

    // Check file list cache
    if (!forceRefresh) {
      const cached = fileListCache.get(cacheKey);
      if (cached && now - cached.timestamp < FILE_LIST_CACHE_DURATION) {
        console.log(`[Cache Hit] Using cached file list for prefix: "${prefix}"`);
        fileListCache.delete(cacheKey);
        fileListCache.set(cacheKey, cached);
        return cached.files;
      }
    }

    console.log(`[Cache Miss] Fetching file list for prefix: "${prefix}"`);

    const params = new URLSearchParams();
    if (prefix) params.append('prefix', prefix);
    params.append('max_results', maxResults.toString());

    const response = await fetch(`${API_BASE}/list?${params.toString()}`);

    if (!response.ok) {
      throw new Error(`List failed: ${response.statusText}`);
    }

    const result = await response.json();

    // Convert lastModified strings to Date objects
    const files = result.files.map((file: any) => ({
      ...file,
      lastModified: new Date(file.last_modified),
    }));

    // Store in cache
    fileListCache.set(cacheKey, {
      files,
      timestamp: now,
    });
    trimOldestEntries(fileListCache, MAX_FILE_LIST_CACHE_SIZE);

    return files;
  } catch (error) {
    console.error('Error listing files from MinIO:', error);
    throw error;
  }
};

export const listFilesPaged = async (
  prefix: string = '',
  page: number = 1,
  pageSize: number = 50,
  sortOrder: 'asc' | 'desc' = 'desc',
  mediaType: 'all' | 'image' | 'video' | 'audio' = 'all',
  forceRefresh: boolean = false
): Promise<{
  files: Array<{ name: string; size: number; lastModified: Date; url: string; presignedUrl?: string }>;
  hasMore: boolean;
  totalCount: number;
  totalPages: number;
}> => {
  try {
    const now = Date.now();
    const cacheKey = `${prefix}::${page}::${pageSize}::${sortOrder}::${mediaType}`;

    if (!forceRefresh) {
      const cached = pagedFileListCache.get(cacheKey);
      if (cached && now - cached.timestamp < FILE_LIST_CACHE_DURATION) {
        pagedFileListCache.delete(cacheKey);
        pagedFileListCache.set(cacheKey, cached);
        return {
          files: cached.files,
          hasMore: cached.hasMore,
          totalCount: cached.totalCount,
          totalPages: cached.totalPages,
        };
      }
    }

    const params = new URLSearchParams();
    if (prefix) params.append('prefix', prefix);
    params.append('page', page.toString());
    params.append('page_size', pageSize.toString());
    params.append('sort_order', sortOrder);
    params.append('media_type', mediaType);

    const response = await fetch(`${API_BASE}/list?${params.toString()}`);
    if (!response.ok) {
      throw new Error(`List failed: ${response.statusText}`);
    }

    const result = await response.json();
    const files = result.files.map((file: any) => ({
      ...file,
      lastModified: new Date(file.last_modified),
    }));

    pagedFileListCache.set(cacheKey, {
      files,
      hasMore: Boolean(result.has_more),
      totalCount: Number(result.total_count ?? files.length),
      totalPages: Number(result.total_pages ?? 1),
      timestamp: now,
    });
    trimOldestEntries(pagedFileListCache, MAX_FILE_LIST_CACHE_SIZE);

    return {
      files,
      hasMore: Boolean(result.has_more),
      totalCount: Number(result.total_count ?? files.length),
      totalPages: Number(result.total_pages ?? 1),
    };
  } catch (error) {
    console.error('Error listing paged files from MinIO:', error);
    throw error;
  }
};

/**
 * Delete file from MinIO
 * @param objectName - Object name
 */
export const deleteFile = async (objectName: string): Promise<void> => {
  try {
    const response = await fetch(`${API_BASE}/delete/${encodeURIComponent(objectName)}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Delete failed: ${response.statusText}`);
    }

    console.log(`File deleted successfully: ${objectName}`);

    // Clear related cache
    presignedUrlCache.delete(objectName);
    // Clear all file list cache (since file was deleted)
    fileListCache.clear();
  } catch (error) {
    console.error('Error deleting file from MinIO:', error);
    throw error;
  }
};

/**
 * Clear presigned URL cache
 * @param objectName - Optional, only clear cache for specified object
 */
export const clearPresignedUrlCache = (objectName?: string): void => {
  if (objectName) {
    presignedUrlCache.delete(objectName);
    console.log(`Cleared presigned URL cache for: ${objectName}`);
  } else {
    presignedUrlCache.clear();
    console.log('Cleared all presigned URL cache');
  }
};

/**
 * Clear file list cache
 * @param prefix - Optional, only clear cache for specified prefix
 */
export const clearFileListCache = (prefix?: string): void => {
  if (prefix !== undefined) {
    fileListCache.delete(prefix);
    Array.from(pagedFileListCache.keys()).forEach((key) => {
      if (key.startsWith(`${prefix}::`)) {
        pagedFileListCache.delete(key);
      }
    });
    console.log(`Cleared file list cache for prefix: "${prefix}"`);
  } else {
    fileListCache.clear();
    pagedFileListCache.clear();
    console.log('Cleared all file list cache');
  }
};

/**
 * Clear all cache
 */
export const clearAllCache = (): void => {
  presignedUrlCache.clear();
  fileListCache.clear();
  pagedFileListCache.clear();
  console.log('Cleared all MinIO cache');
};

/**
 * Upload generated content to MinIO via backend API
 * @param blob - Blob data
 * @param fileName - File name
 * @param contentType - Content type
 * @returns URL of the uploaded file
 */
export const uploadGeneratedContent = async (
  blob: Blob,
  fileName: string,
  contentType: string
): Promise<string> => {
  try {
    // Convert blob to base64 for JSON transmission
    const arrayBuffer = await blob.arrayBuffer();
    const base64Data = btoa(
      new Uint8Array(arrayBuffer).reduce((data, byte) => data + String.fromCharCode(byte), '')
    );

    const response = await fetch(`${API_BASE}/upload-blob`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        data: base64Data,
        filename: fileName,
        folder: 'generated/',
        content_type: contentType,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Upload failed: ${response.statusText}`);
    }

    const result = await response.json();
    console.log(`Generated content uploaded successfully: ${result.object_name}`);

    return result.url;
  } catch (error) {
    console.error('Error uploading generated content to MinIO:', error);
    throw error;
  }
};

/**
 * Download from URL and upload to MinIO via backend API
 * @param sourceUrl - Source URL
 * @param fileName - File name
 * @param folder - Optional folder path
 * @returns URL of the uploaded file
 */
export const uploadFromUrl = async (
  sourceUrl: string,
  fileName: string,
  folder: string = 'imported/'
): Promise<string> => {
  try {
    const response = await fetch(`${API_BASE}/upload-from-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: sourceUrl,
        filename: fileName,
        folder: folder,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Upload from URL failed: ${response.statusText}`);
    }

    const result = await response.json();
    console.log(`Content from URL uploaded successfully: ${result.object_name}`);

    return result.url;
  } catch (error) {
    console.error('Error uploading from URL to MinIO:', error);
    throw error;
  }
};

/**
 * Get folder structure as a tree
 * @param prefix - Root prefix to start from
 * @returns Tree structure
 */
export const getFolderTree = async (prefix: string = ''): Promise<any> => {
  try {
    const params = new URLSearchParams();
    if (prefix) params.append('prefix', prefix);

    const response = await fetch(`${API_BASE}/tree?${params.toString()}`);

    if (!response.ok) {
      throw new Error(`Failed to get folder tree: ${response.statusText}`);
    }

    const tree = await response.json();
    return tree;
  } catch (error) {
    console.error('Error getting folder tree:', error);
    throw error;
  }
};

/**
 * List all folders in the bucket
 * @param prefix - Root prefix to filter from
 * @returns List of folder paths
 */
export const listFolders = async (prefix: string = ''): Promise<string[]> => {
  try {
    const params = new URLSearchParams();
    if (prefix) params.append('prefix', prefix);

    const response = await fetch(`${API_BASE}/folders?${params.toString()}`);

    if (!response.ok) {
      throw new Error(`Failed to list folders: ${response.statusText}`);
    }

    const result = await response.json();
    return result.folders;
  } catch (error) {
    console.error('Error listing folders:', error);
    throw error;
  }
};

/**
 * Move a file from source to destination
 * @param source - Source object path
 * @param destination - Destination object path
 * @returns Result with new URL
 */
export const moveFile = async (source: string, destination: string): Promise<any> => {
  try {
    const response = await fetch(`${API_BASE}/move`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ source, destination }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Move failed: ${response.statusText}`);
    }

    const result = await response.json();
    console.log(`File moved from ${source} to ${destination}`);

    // Clear cache since file structure changed
    fileListCache.clear();

    return result;
  } catch (error) {
    console.error('Error moving file:', error);
    throw error;
  }
};

/**
 * Create a new folder
 * @param folderPath - Path for the new folder
 * @returns Result
 */
export const createFolder = async (folderPath: string): Promise<any> => {
  try {
    const response = await fetch(`${API_BASE}/create-folder`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ folder_path: folderPath }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Create folder failed: ${response.statusText}`);
    }

    const result = await response.json();
    console.log(`Folder created: ${result.folder_path}`);

    // Clear cache since folder structure changed
    fileListCache.clear();

    return result;
  } catch (error) {
    console.error('Error creating folder:', error);
    throw error;
  }
};
