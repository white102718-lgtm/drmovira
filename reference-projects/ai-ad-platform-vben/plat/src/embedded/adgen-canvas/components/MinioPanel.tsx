/** @jsxImportSource react */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  RefreshCw,
  Upload,
  Download,
  ExternalLink,
  X,
  FileText,
  Film,
  Music,
  Image as ImageIcon,
  Search,
  AlertCircle,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Eye,
  ArrowUpDown
} from 'lucide-react';
import {
  listFilesPaged,
  getPresignedUrl,
  clearPresignedUrlCache,
  downloadFileFromMinio,
  deleteFile,
  listFolders
} from '../services/minioService';
import { AssetType } from '../types';
import type { UploadedAsset } from '../types';
import { getCachedAsset, cacheAsset, deleteCachedAsset, ensureAssetCacheMaintenance } from '../services/assetCacheService';
import { BACKEND_URL } from '../services/runtimeConfig';
const MAX_PAGE_CACHE_ENTRIES = 120;

interface MinioPanelProps {
  onImportAsset: (asset: UploadedAsset) => void;
  generatedResults?: Array<{ url: string; type: AssetType; prompt: string }>;
}

const PAGE_SIZE_OPTIONS = [20, 50, 100, 200] as const;
const MEDIA_FILTER_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'image', label: '图片' },
  { value: 'video', label: '视频' },
  { value: 'audio', label: '音频' },
] as const;

const pruneBlobUrlMap = (
  map: Map<string, string>,
  keepKeys: Set<string>,
  maxEntries: number
): Map<string, string> => {
  const next = new Map(map);
  const removable = Array.from(next.entries()).filter(([key]) => !keepKeys.has(key));
  const overflow = Math.max(0, next.size - maxEntries);

  for (let i = 0; i < overflow && i < removable.length; i += 1) {
    const [key, url] = removable[i];
    if (url.startsWith('blob:')) {
      URL.revokeObjectURL(url);
    }
    next.delete(key);
  }

  return next;
};

const isUsableMediaUrl = (url?: string) => Boolean(url && /^(https?:|blob:|data:)/i.test(url));

const getFileMediaUrl = (file: any) => {
  if (isUsableMediaUrl(file?.presignedUrl)) return file.presignedUrl;
  if (isUsableMediaUrl(file?.url)) return file.url;
  return '';
};

const encodeObjectPath = (objectName: string) => objectName.split('/').map(encodeURIComponent).join('/');

const MinioPanel: React.FC<MinioPanelProps> = ({ onImportAsset, generatedResults = [] }) => {
  const [files, setFiles] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFolder, setSelectedFolder] = useState<string>('');
  const [availableFolders, setAvailableFolders] = useState<string[]>([]);
  const [cachedUrls, setCachedUrls] = useState<Map<string, string>>(new Map());
  const [videoThumbnails, setVideoThumbnails] = useState<Map<string, string>>(new Map());
  const [thumbnailLoading, setThumbnailLoading] = useState<Set<string>>(new Set());
  const [previewFile, setPreviewFile] = useState<any | null>(null);
  const [pageSize, setPageSize] = useState<number>(50);
  const [currentPage, setCurrentPage] = useState(1);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [mediaFilter, setMediaFilter] = useState<'all' | 'image' | 'video' | 'audio'>('all');
  const [hasMore, setHasMore] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const cachedUrlsRef = useRef(cachedUrls);
  const videoThumbnailsRef = useRef(videoThumbnails);

  useEffect(() => {
    cachedUrlsRef.current = cachedUrls;
  }, [cachedUrls]);

  useEffect(() => {
    videoThumbnailsRef.current = videoThumbnails;
  }, [videoThumbnails]);

  const isImage = useCallback((name: string) => /\.(jpg|jpeg|png|webp|gif)$/i.test(name), []);
  const isVideo = useCallback((name: string) => /\.(mp4|webm|ogg|mov)$/i.test(name), []);
  const isAudio = useCallback((name: string) => /\.(mp3|wav|ogg|m4a|aac|flac)$/i.test(name), []);
  const isMedia = useCallback((name: string) => isImage(name) || isVideo(name) || isAudio(name), [isImage, isVideo, isAudio]);
  const getPlayableUrl = useCallback((file: any) => getFileMediaUrl(file), []);

  const safePage = currentPage;
  const pagedFiles = files;

  // Lightbox navigation (across all files, not just current page)
  const mediaFiles = files.filter(f => isMedia(f.name));
  const previewIndex = previewFile ? mediaFiles.findIndex(f => f.name === previewFile.name) : -1;

  const navigatePreview = useCallback((dir: 1 | -1) => {
    if (previewIndex < 0 || mediaFiles.length === 0) return;
    const next = (previewIndex + dir + mediaFiles.length) % mediaFiles.length;
    setPreviewFile(mediaFiles[next]);
  }, [previewIndex, mediaFiles]);

  // Keyboard: ESC to close, arrow keys to navigate
  useEffect(() => {
    if (!previewFile) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPreviewFile(null);
      else if (e.key === 'ArrowLeft') navigatePreview(-1);
      else if (e.key === 'ArrowRight') navigatePreview(1);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [previewFile, navigatePreview]);

  const loadFolders = async () => {
    try {
      const folders = await listFolders();
      setAvailableFolders(folders);
    } catch (err) {
      console.error('加载文件夹列表失败', err);
    }
  };

  const loadFiles = async (forceRefresh: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = await listFilesPaged(selectedFolder, currentPage, pageSize, sortOrder === 'asc' ? 'asc' : 'desc', mediaFilter, forceRefresh);
      setFiles(result.files);
      setHasMore(result.hasMore);
      setTotalCount(result.totalCount);
      setTotalPages(result.totalPages);
    } catch (err) {
      setError('加载失败');
    } finally {
      setLoading(false);
    }
  };

  const refreshImageUrl = useCallback(async (fileName: string) => {
    await deleteCachedAsset(`img:${fileName}`);
    clearPresignedUrlCache(fileName);

    setCachedUrls(prev => {
      const next = new Map(prev);
      const existing = next.get(fileName);
      if (existing?.startsWith('blob:')) {
        URL.revokeObjectURL(existing);
      }
      next.delete(fileName);
      return next;
    });

    try {
      const freshUrl = await getPresignedUrl(fileName);
      setFiles(prev => prev.map(file => (
        file.name === fileName
          ? { ...file, url: freshUrl, presignedUrl: freshUrl }
          : file
      )));
    } catch {
      // 保持原状态，避免额外报错
    }
  }, []);

  useEffect(() => {
    ensureAssetCacheMaintenance();
    loadFolders();
  }, []);

  useEffect(() => {
    return () => {
      cachedUrlsRef.current.forEach((url) => {
        if (url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      videoThumbnailsRef.current.forEach((url) => {
        if (url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
    };
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [selectedFolder]);

  // Reset to page 1 when page size changes
  useEffect(() => {
    setCurrentPage(1);
  }, [pageSize, sortOrder, mediaFilter]);

  useEffect(() => {
    loadFiles();
  }, [selectedFolder, currentPage, pageSize, sortOrder, mediaFilter]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  // Cache image blob URLs — only for current page, revoke old ones on page change
  useEffect(() => {
    let cancelled = false;
    const currentPageKeys = new Set(
      pagedFiles.filter(file => isImage(file.name)).map(file => file.name)
    );

    setCachedUrls(prev => {
      const keep = new Map<string, string>();
      prev.forEach((url, key) => {
        if (currentPageKeys.has(key)) {
          keep.set(key, url);
        } else if (url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      return keep;
    });

    const loadCachedUrls = async () => {
      for (const file of pagedFiles) {
        if (cancelled) break;
        if (!isImage(file.name)) continue;

        // 已在 map 中则跳过，不重复创建
        if (cachedUrls.has(file.name)) continue;

        const cacheKey = `img:${file.name}`;
        const cached = await getCachedAsset(cacheKey);
        if (cached) {
          if (!cancelled) {
            setCachedUrls(prev => {
              const next = new Map(prev);
              next.set(file.name, cached);
              return pruneBlobUrlMap(next, currentPageKeys, MAX_PAGE_CACHE_ENTRIES);
            });
          }
        } else {
          try {
            let url = getFileMediaUrl(file);
            if (!url) {
              url = await getPresignedUrl(file.name);
            }
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const blob = await response.blob();
            if (!blob.type.toLowerCase().startsWith('image/')) {
              throw new Error('Invalid image blob');
            }
            await cacheAsset(cacheKey, blob);
            const blobUrl = URL.createObjectURL(blob);
            if (!cancelled) {
              setCachedUrls(prev => {
                const next = new Map(prev);
                next.set(file.name, blobUrl);
                return pruneBlobUrlMap(next, currentPageKeys, MAX_PAGE_CACHE_ENTRIES);
              });
            } else {
              URL.revokeObjectURL(blobUrl);
            }
          } catch {
            // Fall back to direct URL
          }
        }
      }
    };

    if (pagedFiles.length > 0) {
      loadCachedUrls();
    }

    return () => {
      cancelled = true;
    };
  }, [pagedFiles, isImage]);

  // Load video thumbnails — only for current page
  useEffect(() => {
    if (pagedFiles.length === 0) {
      setVideoThumbnails(prev => {
        prev.forEach((url) => {
          if (url.startsWith('blob:')) {
            URL.revokeObjectURL(url);
          }
        });
        return new Map();
      });
      setThumbnailLoading(new Set());
      return;
    }

    const videoFiles = pagedFiles.filter(f => isVideo(f.name));
    if (videoFiles.length === 0) {
      setVideoThumbnails(prev => {
        prev.forEach((url) => {
          if (url.startsWith('blob:')) {
            URL.revokeObjectURL(url);
          }
        });
        return new Map();
      });
      setThumbnailLoading(new Set());
      return;
    }

    let cancelled = false;
    const currentVideoKeys = new Set(videoFiles.map(f => f.name));

    setVideoThumbnails(prev => {
      const keep = new Map<string, string>();
      prev.forEach((url, key) => {
        if (currentVideoKeys.has(key)) {
          keep.set(key, url);
        } else if (url.startsWith('blob:')) {
          URL.revokeObjectURL(url);
        }
      });
      return keep;
    });

    const loadThumbnails = async () => {
      setThumbnailLoading(new Set(videoFiles.map(f => f.name)));

      const batchSize = 4;

      for (let i = 0; i < videoFiles.length; i += batchSize) {
        if (cancelled) break;
        const batch = videoFiles.slice(i, i + batchSize);

        const results = await Promise.allSettled(
          batch.map(async (file) => {
            const cacheKey = `thumb:${file.name}`;
            const cached = await getCachedAsset(cacheKey);
            if (cached) {
              return { name: file.name, url: cached };
            }

            const thumbUrl = `${BACKEND_URL}/api/minio/thumbnail/${encodeObjectPath(file.name)}`;
            const res = await fetch(thumbUrl);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const blob = await res.blob();
            await cacheAsset(cacheKey, blob);
            return { name: file.name, url: URL.createObjectURL(blob) };
          })
        );

        for (const result of results) {
          if (result.status === 'fulfilled' && result.value) {
            if (!cancelled) {
              setVideoThumbnails(prev => {
                const next = new Map(prev);
                next.set(result.value.name, result.value.url);
                return pruneBlobUrlMap(next, currentVideoKeys, MAX_PAGE_CACHE_ENTRIES);
              });
            } else if (result.value.url.startsWith('blob:')) {
              URL.revokeObjectURL(result.value.url);
            }
          }
        }

        if (!cancelled) {
          setThumbnailLoading(prev => {
            const next = new Set(prev);
            batch.forEach(f => next.delete(f.name));
            return next;
          });
        }
      }
    };

    loadThumbnails();
    return () => {
      cancelled = true;
      setThumbnailLoading(prev => {
        const next = new Set(prev);
        videoFiles.forEach(file => next.delete(file.name));
        return next;
      });
    };
  }, [pagedFiles, isVideo]);

  // 导入文件到工作区
  const handleImport = async (file: any) => {
    try {
      setLoading(true);
      const downloadedFile = await downloadFileFromMinio(file.name);
      const id = Math.random().toString(36).substring(7);
      let type = AssetType.FILE;

      if (downloadedFile.type.startsWith('image/')) type = AssetType.IMAGE;
      else if (downloadedFile.type.startsWith('video/')) type = AssetType.VIDEO;
      else if (downloadedFile.type.startsWith('audio/')) type = AssetType.AUDIO;
      else if (downloadedFile.type.startsWith('text/')) type = AssetType.TEXT;

      onImportAsset({
        id,
        type,
        url: getPlayableUrl(file),
        name: downloadedFile.name,
        file: downloadedFile
      });
      setError(null);
    } catch (err) {
      setError('导入失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  // 删除文件
  const handleDelete = async (fileName: string) => {
    if (!window.confirm(`确定要删除 ${fileName} 吗?`)) return;
    try {
      setLoading(true);
      await deleteFile(fileName);
      if (files.length === 1 && currentPage > 1) {
        setCurrentPage(prev => prev - 1);
      } else {
        await loadFiles(true);
      }
    } catch (err) {
      setError('删除失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col h-[600px]">
      {/* Header */}
      <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50 rounded-t-xl">
        <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2">
          <Search className="w-4 h-4 text-indigo-500" /> 云素材库
        </h3>
        <div className="flex gap-1">
          <button
            onClick={() => { setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc'); setCurrentPage(1); }}
            className="p-1.5 hover:bg-white rounded-md transition-all border border-transparent hover:border-slate-200 flex items-center gap-1"
            title={sortOrder === 'asc' ? '当前：正序（旧→新），点击切换倒序' : '当前：倒序（新→旧），点击切换正序'}
          >
            <ArrowUpDown className="w-3.5 h-3.5" />
            <span className="text-[10px] text-slate-500">{sortOrder === 'asc' ? '旧→新' : '新→旧'}</span>
          </button>
          <button
            onClick={() => loadFiles(true)}
            className="p-1.5 hover:bg-white rounded-md transition-all border border-transparent hover:border-slate-200"
            title="刷新（强制重新加载）"
            disabled={loading}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Tabs - Dynamic folders */}
      <div className="px-4 py-2 flex gap-2 overflow-x-auto no-scrollbar border-b border-slate-50">
        <button
          onClick={() => setSelectedFolder('')}
          className={`text-[11px] px-3 py-1 rounded-full whitespace-nowrap transition-colors ${
            selectedFolder === '' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
          }`}
        >
          全部
        </button>
        {availableFolders.map((folder) => (
          <button
            key={folder}
            onClick={() => setSelectedFolder(folder)}
            className={`text-[11px] px-3 py-1 rounded-full whitespace-nowrap transition-colors ${
              selectedFolder === folder ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
            }`}
          >
            {folder.replace(/\//g, '')}
          </button>
        ))}
      </div>

      <div className="px-4 py-2 flex gap-2 border-b border-slate-50 bg-slate-50/40">
        {MEDIA_FILTER_OPTIONS.map((option) => (
          <button
            key={option.value}
            onClick={() => setMediaFilter(option.value)}
            className={`text-[11px] px-3 py-1 rounded-full whitespace-nowrap transition-colors ${
              mediaFilter === option.value ? 'bg-slate-900 text-white' : 'bg-white text-slate-500 hover:bg-slate-100 border border-slate-200'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Error Message */}
      {error && (
        <div className="mx-4 mt-3 p-2 bg-red-50 border border-red-100 rounded-lg flex items-center gap-2 text-red-600 text-xs">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Grid Content */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {files.length === 0 && !loading ? (
          <div className="h-full flex items-center justify-center text-slate-400 text-xs">暂无素材</div>
        ) : (
          <div className={`grid grid-cols-3 sm:grid-cols-4 gap-3${previewFile ? ' pointer-events-none' : ''}`}>
            {pagedFiles.map((file) => (
              <div key={file.name} className="group relative aspect-square bg-slate-50 rounded-lg border border-slate-100 overflow-hidden hover:shadow-md transition-shadow">

                {/* 1. 缩略图预览区 — 点击可预览 */}
                <div
                  className={`w-full h-full flex items-center justify-center overflow-hidden bg-slate-100 ${isMedia(file.name) ? 'cursor-pointer' : ''}`}
                  onClick={() => isMedia(file.name) && setPreviewFile(file)}
                >
                  {isImage(file.name) ? (
                    <img
                      src={cachedUrls.get(file.name) || getPlayableUrl(file)}
                      alt=""
                      className="w-full h-full object-cover"
                      loading="lazy"
                      onError={() => { void refreshImageUrl(file.name); }}
                    />
                  ) : isVideo(file.name) ? (
                    videoThumbnails.get(file.name) ? (
                      <div className="relative w-full h-full">
                        <img src={videoThumbnails.get(file.name)} alt="" className="w-full h-full object-cover" />
                        <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                          <div className="w-8 h-8 bg-white/90 rounded-full flex items-center justify-center">
                            <Film className="w-4 h-4 text-slate-700" />
                          </div>
                        </div>
                      </div>
                    ) : thumbnailLoading.has(file.name) ? (
                      <div className="flex flex-col items-center gap-1.5">
                        <Loader2 className="w-5 h-5 text-slate-300 animate-spin" />
                        <span className="text-[9px] text-slate-300">生成缩略图...</span>
                      </div>
                    ) : (
                      <Film className="w-6 h-6 text-slate-300" />
                    )
                  ) : isAudio(file.name) ? (
                    <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-pink-50 via-orange-50 to-rose-100 p-3">
                      <div className="w-10 h-10 rounded-full bg-white shadow-sm flex items-center justify-center mb-2">
                        <Music className="w-5 h-5 text-pink-500" />
                      </div>
                      <div className="text-[10px] font-semibold text-slate-600 mb-2">音频素材</div>
                      <audio
                        src={getPlayableUrl(file)}
                        controls
                        className="w-full max-w-[160px]"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                  ) : (
                    <FileText className="w-6 h-6 text-slate-300" />
                  )}
                </div>

                {/* 2. 右上角删除叉号 (仅在悬浮时显示) */}
                <button
                  onClick={() => handleDelete(file.name)}
                  className="absolute top-1 right-1 p-1 bg-black/40 hover:bg-red-500 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity z-10"
                  title="删除文件"
                >
                  <X className="w-3 h-3" />
                </button>

                {/* 3. 底部操作遮罩 */}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-1.5 flex justify-center gap-3 translate-y-full group-hover:translate-y-0 transition-transform">
                  {isMedia(file.name) && (
                    <button
                      onClick={() => setPreviewFile(file)}
                      className="p-1.5 bg-white/20 hover:bg-white/40 rounded text-white transition-colors"
                      title="预览"
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <button
                    onClick={() => handleImport(file)}
                    className="p-1.5 bg-white/20 hover:bg-white/40 rounded text-white transition-colors"
                    title="导入到工作区"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>
                  <a
                    href={getPlayableUrl(file) || `${BACKEND_URL}/api/minio/presigned-url/${encodeObjectPath(file.name)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="p-1.5 bg-white/20 hover:bg-white/40 rounded text-white transition-colors"
                    title="在新窗口打开"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>

                {/* 4. 文件名 (简短显示) */}
                <div className="absolute bottom-0 inset-x-0 bg-white/90 px-1 py-0.5 group-hover:hidden">
                   <p className="text-[10px] text-slate-600 truncate text-center leading-tight">
                     {file.name.split('/').pop()}
                   </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer: pagination + page size selector */}
      <div className="px-3 py-2 border-t border-slate-100 bg-slate-50 flex items-center justify-between gap-2">
        {/* Page size selector */}
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-slate-400">每页</span>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="text-[11px] bg-white border border-slate-200 rounded-md px-1.5 py-0.5 text-slate-600 focus:outline-none focus:ring-1 focus:ring-indigo-300 cursor-pointer"
          >
            {PAGE_SIZE_OPTIONS.map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>

        {/* Page navigation */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={safePage <= 1}
            className="p-0.5 rounded hover:bg-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="w-3.5 h-3.5 text-slate-500" />
          </button>
          <span className="text-[10px] text-slate-500 min-w-[60px] text-center">
            {safePage} / {Math.max(1, totalPages)}
          </span>
          <button
            onClick={() => setCurrentPage(p => p + 1)}
            disabled={!hasMore}
            className="p-0.5 rounded hover:bg-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
          </button>
        </div>

        {/* Total count */}
        <span className="text-[10px] text-slate-400">
          共 {totalCount} 个
        </span>
      </div>

      {/* Lightbox Preview Modal — rendered via portal to avoid stacking context / repaint conflicts */}
      {previewFile && createPortal(
        <LightboxModal
          file={previewFile}
          isImage={isImage}
          isVideo={isVideo}
          isAudio={isAudio}
          cachedUrls={cachedUrls}
          mediaFiles={mediaFiles}
          previewIndex={previewIndex}
          onClose={() => setPreviewFile(null)}
          onNavigate={navigatePreview}
          onImport={handleImport}
          onImageError={refreshImageUrl}
        />,
        document.body
      )}
    </div>
  );
};

// Separate component so video element unmounts cleanly on close/navigate
const LightboxModal: React.FC<{
  file: any;
  isImage: (n: string) => boolean;
  isVideo: (n: string) => boolean;
  cachedUrls: Map<string, string>;
  isAudio?: (n: string) => boolean;
  mediaFiles: any[];
  previewIndex: number;
  onClose: () => void;
  onNavigate: (dir: 1 | -1) => void;
  onImport: (f: any) => void;
  onImageError: (fileName: string) => Promise<void>;
}> = ({ file, isImage, isVideo, isAudio = () => false, cachedUrls, mediaFiles, previewIndex, onClose, onNavigate, onImport, onImageError }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoReady, setVideoReady] = useState(false);

  const videoStreamUrl = isVideo(file.name)
    ? `${BACKEND_URL}/api/minio/stream/${encodeObjectPath(file.name)}`
    : '';

  // Cleanup: pause & release video src on unmount or file change
  useEffect(() => {
    setVideoReady(false);
    return () => {
      if (videoRef.current) {
        videoRef.current.pause();
        videoRef.current.removeAttribute('src');
        videoRef.current.load(); // force release network connection
      }
    };
  }, [file.name]);

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Close */}
      <button
        className="absolute top-4 right-4 p-2 bg-white/10 hover:bg-white/20 rounded-full text-white transition-colors z-10"
        onClick={onClose}
      >
        <X className="w-5 h-5" />
      </button>

      {/* Arrows */}
      {mediaFiles.length > 1 && (
        <>
          <button
            className="absolute left-4 top-1/2 -translate-y-1/2 p-2 bg-white/10 hover:bg-white/20 rounded-full text-white transition-colors z-10"
            onClick={(e) => { e.stopPropagation(); onNavigate(-1); }}
          >
            <ChevronLeft className="w-6 h-6" />
          </button>
          <button
            className="absolute right-4 top-1/2 -translate-y-1/2 p-2 bg-white/10 hover:bg-white/20 rounded-full text-white transition-colors z-10"
            onClick={(e) => { e.stopPropagation(); onNavigate(1); }}
          >
            <ChevronRight className="w-6 h-6" />
          </button>
        </>
      )}

      {/* Content */}
      <div className="max-w-[90vw] max-h-[85vh] flex flex-col items-center" onClick={(e) => e.stopPropagation()}>
        {isImage(file.name) ? (
          <img
            src={cachedUrls.get(file.name) || getFileMediaUrl(file)}
            alt={file.name}
            className="max-w-full max-h-[80vh] object-contain rounded-lg shadow-2xl"
            onError={() => { void onImageError(file.name); }}
          />
        ) : isVideo(file.name) ? (
          <div className="relative">
            {!videoReady && (
              <div className="absolute inset-0 flex flex-col items-center justify-center bg-black rounded-lg z-10">
                <Loader2 className="w-8 h-8 text-white/60 animate-spin" />
                <span className="text-white/50 text-xs mt-2">加载视频...</span>
              </div>
            )}
            <video
              ref={videoRef}
              key={file.name}
              src={videoStreamUrl}
              controls
              autoPlay
              preload="metadata"
              onCanPlay={() => setVideoReady(true)}
              className="max-w-full max-h-[80vh] rounded-lg shadow-2xl"
            />
          </div>
        ) : isAudio(file.name) ? (
          <div className="w-[min(90vw,720px)] rounded-2xl bg-white p-10 shadow-2xl">
            <div className="max-w-xl mx-auto text-center">
              <div className="w-20 h-20 rounded-full bg-pink-50 flex items-center justify-center mx-auto mb-6">
                <Music className="w-10 h-10 text-pink-500" />
              </div>
              <div className="text-lg font-bold text-slate-800 mb-2">音频预览</div>
              <div className="text-sm text-slate-500 mb-6 break-all">{file.name.split('/').pop()}</div>
              <audio
                src={getFileMediaUrl(file)}
                controls
                autoPlay
                className="w-full"
              />
            </div>
          </div>
        ) : null}

        {/* Bottom info bar */}
        <div className="mt-3 flex items-center gap-3">
          <span className="text-white/70 text-xs truncate max-w-[50vw]">{file.name.split('/').pop()}</span>
          {mediaFiles.length > 1 && (
            <span className="text-white/40 text-xs">{previewIndex + 1} / {mediaFiles.length}</span>
          )}
          <button
            onClick={() => onImport(file)}
            className="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs rounded-md transition-colors flex items-center gap-1"
          >
            <Download className="w-3 h-3" /> 导入
          </button>
        </div>
      </div>
    </div>
  );
};

export default React.memo(MinioPanel);
