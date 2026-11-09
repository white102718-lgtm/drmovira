/** @jsxImportSource react */
import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import html2canvas from 'html2canvas';
import {
  AlignHorizontalJustifyCenter,
  AlignVerticalJustifyCenter,
  AlertTriangle,
  ArrowLeft,
  ArrowUp,
  Box,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDollarSign,
  CircleDot,
  ClipboardPaste,
  Cloud,
  Copy,
  CopyPlus,
  Download,
  Eye,
  FileImage,
  FileText,
  Focus,
  Grid3X3,
  GripVertical,
  Hand,
  History,
  Image as ImageIcon,
  Keyboard,
  Layers,
  LayoutGrid,
  Link2,
  Loader2,
  Map as MapIcon,
  Maximize2,
  MessageSquareText,
  Mic2,
  Minimize2,
  Moon,
  MousePointer2,
  Music2,
  Play,
  Plus,
  Redo2,
  Save,
  Scissors,
  SlidersHorizontal,
  Sparkles,
  Star,
  Sun,
  TextCursorInput,
  Trash2,
  Unlink,
  Undo2,
  Upload,
  Video,
  X,
  ZoomOut,
} from 'lucide-react';
import type {
  CanvasDraft,
  CanvasEdgeData,
  CanvasGenerationConfig,
  CanvasNodeData,
  CanvasNodeKind,
  CanvasNodeResult,
  CanvasViewport,
  ImageGenerationMode,
  VideoGenerationMode,
} from './types';
import {
  generateBatchImages,
  generateMusic,
  generateTTS,
  generateVideoFission,
  analyzeCanvasVideo,
  createVideoGenerationTaskId,
  cancelVideoGenerationTask,
  editImageWithMask,
  VideoGenerationCancelledError,
} from '../../services/aiBackendService';
import { toUserFacingGenerationError } from '../../services/providerErrorMessage';
import { registerByteplusAsset } from '../../services/byteplusAssetService';
import {
  DEFAULT_MEDIA_GENERATION_CONFIG,
  getEnabledModels,
  getMediaFeatureConfig,
  getMediaModelCatalog,
  getImagePricePerImage,
  getVideoPricePerSecond,
  isWan3ReferenceAudioFile,
  isWan3ReferenceDocumentFile,
  isWan3VideoModel,
  isSeedance25VideoModel,
  TTS_VOICE_OPTIONS,
  WAN3_MAX_OMNI_MEDIA,
  WAN3_MAX_REFERENCE_AUDIOS,
  WAN3_MAX_REFERENCE_FILES,
  WAN3_MAX_REFERENCE_IMAGES,
  WAN3_MAX_REFERENCE_LINKS,
  WAN3_MAX_REFERENCE_VIDEOS,
  WAN3_REFERENCE_FILE_EXTENSIONS,
} from '../../utils/mediaModelConfig';
import { AssetType, type UploadedAsset } from '../../types';
import MinioPanel from '../../components/MinioPanel';
import { uploadToStorage } from '../../services/storageService';
import {
  generateSessionId,
  saveBatchImagesRecord,
  saveEditImageRecord,
  saveMusicGenerationRecord,
  saveTTSGenerationRecord,
  saveVideoFissionRecord,
  type SaveHistoryResponse,
} from '../../services/historyService';
import { authService } from '../../services/authService';
import {
  createPersistedCanvas,
  loadPersistedCanvas,
  savePersistedCanvas,
} from '../../services/canvasPersistenceService';
import {
  downloadCanvasMedia,
  downloadCanvasImage,
  getCanvasImageDownloadName,
  getCanvasMediaPreviewUrl,
  getCanvasVideoDownloadName,
  getStableCanvasMediaUrl,
} from './services/canvasMediaService';
import CanvasChatPanel, {
  type CanvasChatAttachRequest,
  type CanvasChatGenerationRequest,
  type CanvasChatMediaType,
} from './components/CanvasChatPanel';
import type { CanvasChatGenerationModel } from './services/canvasChatService';
import { OFFICIAL_ASSET_LIBRARY_ENABLED } from '../../officialAssetLibrary';
import { OfficialAssetCardToggle } from './components/OfficialAssetCardToggle';
import {
  ImageNodeAiTools,
  type ImageNodeAiToolMode,
} from './components/ImageNodeAiTools';
import {
  imageBlobHasTransparency,
  SMART_MATTING_MODEL,
  SMART_MATTING_PROMPT,
} from './components/imageMatting';
import {
  cellKey,
  sliceImageGridCells,
  type GridHdScale,
  type GridSplitCell,
  type GridSplitSize,
} from './components/gridSplit';
import GenerationHistoryPage, {
  type HistoryRestoreData,
  type HistoryUsePayload,
} from './components/GenerationHistoryPage';
import type {
  CanvasChatContextPayload,
  CanvasChatContextScope,
} from './services/canvasChatService';
import PromptMentionEditor from './components/PromptMentionEditor';
import { useImageHoverPreview } from './components/ImageHoverPreview';

interface CanvasCreationPageProps {
  canvasId?: string;
  initialTitle?: string;
  onBack?: () => void;
  mediaConfig?: any;
}

interface ImageHoverActionsProps {
  label: string;
  onPreview: () => void;
  onDownload: () => void;
  compact?: boolean;
  corner?: boolean;
  className?: string;
}

const ImageHoverActions: React.FC<ImageHoverActionsProps> = ({
  label,
  onPreview,
  onDownload,
  compact = false,
  corner = false,
  className,
}) => (
  <div
    className={`${
      corner
        ? 'pointer-events-none absolute right-2 top-2 z-40 flex items-center gap-1 opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100'
        : 'pointer-events-none absolute inset-0 z-20 flex items-center justify-center gap-2 bg-slate-950/0 opacity-0 backdrop-blur-0 transition-[background-color,opacity,backdrop-filter] duration-200 group-focus-within:bg-slate-950/45 group-focus-within:opacity-100 group-focus-within:backdrop-blur-[1px] group-hover:bg-slate-950/45 group-hover:opacity-100 group-hover:backdrop-blur-[1px]'
    } ${className || ''}`}
  >
    <button
      type="button"
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        onPreview();
      }}
      aria-label={`预览${label}`}
      title="预览"
      className={`pointer-events-auto flex cursor-pointer items-center justify-center border border-white/45 bg-slate-950/65 text-white shadow-lg backdrop-blur-md transition-colors duration-200 hover:bg-violet-600 focus:outline-none focus:ring-2 focus:ring-white ${corner ? 'h-7 w-7 rounded-lg' : compact ? 'h-8 w-8 rounded-xl' : 'h-10 w-10 rounded-xl'}`}
    >
      <Eye size={corner ? 13 : compact ? 15 : 18} />
    </button>
    <button
      type="button"
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        onDownload();
      }}
      aria-label={`下载${label}`}
      title="下载"
      className={`pointer-events-auto flex cursor-pointer items-center justify-center border border-white/45 bg-slate-950/65 text-white shadow-lg backdrop-blur-md transition-colors duration-200 hover:bg-violet-600 focus:outline-none focus:ring-2 focus:ring-white ${corner ? 'h-7 w-7 rounded-lg' : compact ? 'h-8 w-8 rounded-xl' : 'h-10 w-10 rounded-xl'}`}
    >
      <Download size={corner ? 13 : compact ? 15 : 18} />
    </button>
  </div>
);

const MEDIA_STACK_LAYER_OFFSET = 6;
const MEDIA_RESULT_GRID_GAP = 6;
const MEDIA_RESULT_GRID_PAD = 6;
const IMAGE_BATCH_COUNT_PRESETS = [1, 2, 4, 8, 10];
const VIDEO_BATCH_COUNT_PRESETS = [1, 2, 4];
const MEDIA_OVERLAY_PILL_CLASS =
  'canvas-media-tile-action canvas-media-tile-action--pill pointer-events-auto';
const MEDIA_TILE_ACTION_CLASS = 'canvas-media-tile-action pointer-events-auto';
const TRANSPARENT_MEDIA_CHECKERBOARD_CLASS =
  'bg-white [background-image:linear-gradient(45deg,#cbd5e1_25%,transparent_25%),linear-gradient(-45deg,#cbd5e1_25%,transparent_25%),linear-gradient(45deg,transparent_75%,#cbd5e1_75%),linear-gradient(-45deg,transparent_75%,#cbd5e1_75%)] [background-position:0_0,0_8px,8px_-8px,-8px_0] [background-size:16px_16px]';

const nodeShowsTransparentBackground = (node: CanvasNodeData) =>
  Boolean(node.hasTransparentBackground) || node.title === '智能抠图';

const getBatchCountOptions = (maxCount: number, presets: number[]) => {
  const options = presets.filter((value) => value <= maxCount);
  if (maxCount > 1 && !options.includes(maxCount)) options.push(maxCount);
  return options.length > 0 ? options : [1];
};

const clampBatchCount = (value: unknown, maxCount: number) => {
  const parsed = Math.round(Number(value) || 1);
  const max = Math.max(1, maxCount);
  return Math.min(max, Math.max(1, parsed));
};

const getOwnMediaResultUrls = (node: CanvasNodeData) => {
  // 输出/素材节点不叠卡；生成节点只展示最近一次批量结果。
  if (node.kind === 'output' || node.kind === 'asset') return [] as string[];
  const type = getNodeResultType(node);
  if (type !== 'image' && type !== 'video') return [] as string[];
  const urls = node.resultUrls?.length
    ? node.resultUrls
    : node.resultUrl
      ? [node.resultUrl]
      : [];
  return Array.from(new Set(urls.filter(Boolean)));
};

const getExpandedMediaNodeDimensions = (
  tileSize: { width: number; height: number },
  count: number,
) => {
  const cols = 2;
  const rows = Math.max(1, Math.ceil(Math.max(count, 1) / cols));
  return {
    width:
      tileSize.width * cols +
      MEDIA_RESULT_GRID_GAP * (cols - 1) +
      MEDIA_RESULT_GRID_PAD * 2,
    height:
      tileSize.height * rows +
      MEDIA_RESULT_GRID_GAP * (rows - 1) +
      MEDIA_RESULT_GRID_PAD * 2,
  };
};

interface CanvasMediaResultBoardProps {
  urls: string[];
  mediaType: 'image' | 'video';
  label: string;
  expanded: boolean;
  generating?: boolean;
  transparentBackground?: boolean;
  onExpand: () => void;
  onCollapse: () => void;
  onSetMain: (url: string) => void;
  onDownload: (url: string, index: number) => void;
  onAspectRatio?: (ratio: number) => void;
}

/**
 * 多结果媒体节点：折叠时叠卡并显示「展开 N张/条」，展开后为网格，可设为主图或收起。
 * 主图始终是 urls[0]，下游连线只使用主图。
 */
const CanvasMediaResultBoard: React.FC<CanvasMediaResultBoardProps> = ({
  urls,
  mediaType,
  label,
  expanded,
  generating = false,
  transparentBackground = false,
  onExpand,
  onCollapse,
  onSetMain,
  onDownload,
  onAspectRatio,
}) => {
  const mainUrl = urls[0];
  const unitLabel = mediaType === 'video' ? '条' : '张';
  const stackCount = Math.min(urls.length, 3);
  const { showPreview, hidePreview, previewNode } = useImageHoverPreview();

  const renderMedia = (
    url: string,
    options?: {
      fill?: boolean;
      captureAspect?: boolean;
      preview?: boolean;
      showPlay?: boolean;
    },
  ) => {
    const fill = options?.fill !== false;
    if (mediaType === 'video') {
      return (
        <>
          <video
            data-node-video-preview={options?.preview ? '' : undefined}
            src={url}
            aria-label={label}
            muted
            playsInline
            loop
            preload="auto"
            onLoadedMetadata={(event) => {
              if (!options?.captureAspect) return;
              const { videoWidth, videoHeight } = event.currentTarget;
              if (!videoWidth || !videoHeight) return;
              onAspectRatio?.(videoWidth / videoHeight);
            }}
            onLoadedData={(event) => {
              resetNodeVideoPreview(event.currentTarget);
            }}
            className={
              fill
                ? 'relative h-full w-full object-cover'
                : 'relative h-full w-full object-contain'
            }
          />
          {options?.showPlay && (
            <span className="pointer-events-none absolute left-1/2 top-1/2 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-white/55 bg-slate-950/55 text-white shadow-lg backdrop-blur-sm">
              <Play size={15} fill="currentColor" />
            </span>
          )}
        </>
      );
    }

    return (
      <>
        {transparentBackground ? (
          <div
            className={`absolute inset-0 ${TRANSPARENT_MEDIA_CHECKERBOARD_CLASS}`}
            aria-hidden="true"
          />
        ) : (
          <img
            src={url}
            alt=""
            aria-hidden="true"
            draggable={false}
            className="absolute inset-0 h-full w-full scale-110 select-none object-cover opacity-50 blur-xl"
          />
        )}
        <img
          src={url}
          alt={label}
          draggable={false}
          onLoad={(event) => {
            if (!options?.captureAspect) return;
            const { naturalWidth, naturalHeight } = event.currentTarget;
            if (!naturalWidth || !naturalHeight) return;
            onAspectRatio?.(naturalWidth / naturalHeight);
          }}
          className="relative h-full w-full select-none object-contain"
        />
      </>
    );
  };

  if (expanded) {
    return (
      <div
        className="absolute inset-0 grid grid-cols-2 gap-1.5 overflow-hidden rounded-[5px] bg-slate-950 p-1.5"
        style={{ gridAutoRows: '1fr' }}
      >
        {urls.map((url, index) => {
          const isMain = index === 0;
          return (
            <div
              key={`${url}-${index}`}
              className="group/tile relative min-h-0 overflow-hidden rounded-md bg-slate-900"
              onMouseEnter={(event) => {
                if (!generating) {
                  showPreview(
                    event.currentTarget,
                    url,
                    `${label} ${index + 1}${isMain ? ' · 主图' : ''}`,
                    mediaType,
                  );
                }
                if (mediaType !== 'video') return;
                const video = event.currentTarget.querySelector('video');
                void video?.play().catch(() => undefined);
              }}
              onMouseLeave={(event) => {
                hidePreview();
                if (mediaType !== 'video') return;
                const video = event.currentTarget.querySelector('video');
                if (video) resetNodeVideoPreview(video);
              }}
            >
              {renderMedia(url, {
                captureAspect: isMain,
                preview: false,
                showPlay: true,
              })}
              {!generating && (
                <div className="pointer-events-none absolute right-1.5 top-1.5 z-20 flex items-center gap-1">
                  <button
                    type="button"
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      onDownload(url, index);
                    }}
                    aria-label={`下载${label} ${index + 1}`}
                    className={`pointer-events-auto ${MEDIA_TILE_ACTION_CLASS}`}
                  >
                    <Download size={12} />
                    下载
                  </button>
                  {isMain ? (
                    <button
                      type="button"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={(event) => {
                        event.stopPropagation();
                        onCollapse();
                      }}
                      aria-label="收起结果"
                      className={`pointer-events-auto ${MEDIA_TILE_ACTION_CLASS}`}
                    >
                      <Minimize2 size={12} />
                      收起
                    </button>
                  ) : (
                    <button
                      type="button"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={(event) => {
                        event.stopPropagation();
                        onSetMain(url);
                      }}
                      aria-label={
                        mediaType === 'video' ? '设为主视频' : '设为主图'
                      }
                      className={`pointer-events-auto ${MEDIA_TILE_ACTION_CLASS}`}
                    >
                      <ImageIcon size={12} />
                      设为主图
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {previewNode}
      </div>
    );
  }

  return (
    <>
      {urls.length > 1 &&
        Array.from({ length: stackCount - 1 }, (_, index) => {
          const offset = (stackCount - 1 - index) * MEDIA_STACK_LAYER_OFFSET;
          return (
            <div
              key={`stack-${offset}`}
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 rounded-[5px] border border-white/40 bg-slate-800/90"
              style={{ transform: `translate(${offset}px, ${offset}px)` }}
            />
          );
        })}
      <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[5px]">
        {renderMedia(mainUrl, {
          captureAspect: true,
          preview: mediaType === 'video',
        })}
      </div>
      {urls.length > 1 && !generating && (
        <button
          type="button"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            onExpand();
          }}
          aria-label={`展开 ${urls.length}${unitLabel}`}
          className={`absolute right-2 top-2 z-40 ${MEDIA_OVERLAY_PILL_CLASS}`}
        >
          <Maximize2 size={12} />
          展开 {urls.length}
          {unitLabel}
        </button>
      )}
    </>
  );
};

/** 重新生成时盖住旧结果，避免多任务并行时分不清哪张图还在跑。 */
const NodeGeneratingOverlay: React.FC<{ label?: string }> = ({
  label = '生成中',
}) => (
  <div
    className="canvas-node-generating-overlay"
    role="status"
    aria-live="polite"
    aria-label={label}
  >
    <span className="canvas-node-generating-overlay__label">{label}</span>
    <Loader2 size={22} className="animate-spin" aria-hidden="true" />
  </div>
);

const ImageReferenceHoverChip: React.FC<{
  alias: string;
  url: string;
  sourceTitle: string;
  mediaType?: 'image' | 'video' | 'audio' | 'file' | 'link';
  onClick: () => void;
  onRemove?: () => void;
}> = ({ alias, url, sourceTitle, mediaType = 'image', onClick, onRemove }) => {
  const { showPreview, hidePreview, previewNode } = useImageHoverPreview();
  return (
    <>
      <div className="group relative inline-flex max-w-[180px]">
        <button
          type="button"
          onMouseEnter={(event) => {
            if (mediaType !== 'image' && mediaType !== 'video') return;
            showPreview(
              event.currentTarget,
              url,
              `@${alias} · ${sourceTitle}`,
              mediaType,
            );
          }}
          onMouseLeave={hidePreview}
          onClick={onClick}
          title={`插入 @${alias} · 来源：${sourceTitle}`}
          className="group flex h-8 max-w-[180px] cursor-pointer items-center gap-1.5 overflow-hidden rounded-lg border border-violet-200 bg-white pr-2 text-[10px] font-semibold text-violet-700 shadow-sm transition-colors hover:border-violet-400 hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
        >
          <span className="flex h-full w-8 shrink-0 items-center justify-center bg-slate-100 p-0.5">
            {mediaType === 'video' ? (
              <video
                src={url}
                muted
                playsInline
                preload="metadata"
                className="max-h-full max-w-full object-contain"
              />
            ) : mediaType === 'audio' ? (
              <Music2 size={14} className="text-violet-600" />
            ) : mediaType === 'file' ? (
              <FileText size={14} className="text-violet-600" />
            ) : mediaType === 'link' ? (
              <Link2 size={14} className="text-violet-600" />
            ) : (
              <img
                src={url}
                alt=""
                className="max-h-full max-w-full object-contain"
              />
            )}
          </span>
          <span className="shrink-0">@{alias}</span>
          <span className="truncate font-normal text-slate-400 group-hover:text-slate-600">
            {sourceTitle}
          </span>
        </button>
        {onRemove && (
          <button
            type="button"
            aria-label={`移除 @${alias} 的参考连接`}
            title={`移除 @${alias}，并断开对应连线`}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              hidePreview();
              onRemove();
            }}
            className="absolute -right-1.5 -top-1.5 z-[1] inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-white bg-slate-900 text-white opacity-80 transition-opacity hover:bg-slate-700 hover:opacity-100 focus-visible:opacity-100"
          >
            <X size={8} strokeWidth={2.5} />
          </button>
        )}
      </div>
      {previewNode}
    </>
  );
};

const resetNodeVideoPreview = (video: HTMLVideoElement) => {
  video.pause();
  if (video.readyState < HTMLMediaElement.HAVE_METADATA) return;
  const previewTime = Math.min(
    0.5,
    Math.max(0, (video.duration || 0.5) - 0.05),
  );
  if (Math.abs(video.currentTime - previewTime) > 0.01) {
    video.currentTime = previewTime;
  }
};

interface VideoResultCardProps {
  url: string;
  label: string;
  onPreview: () => void;
  onDownload: () => void;
  onRemove?: () => void;
}

const VideoResultCard: React.FC<VideoResultCardProps> = ({
  url,
  label,
  onPreview,
  onDownload,
  onRemove,
}) => (
  <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
    <div className="relative aspect-video overflow-hidden bg-slate-950">
      <video
        src={url}
        aria-hidden="true"
        muted
        playsInline
        preload="auto"
        className="absolute inset-0 h-full w-full scale-110 object-cover opacity-40 blur-xl"
      />
      <video
        src={url}
        aria-label={label}
        muted
        playsInline
        preload="auto"
        className="relative h-full w-full object-contain"
      />
      <span className="pointer-events-none absolute left-1/2 top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-white/60 bg-slate-950/55 text-white shadow-lg backdrop-blur-sm">
        <Play size={16} fill="currentColor" />
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`移除${label}`}
          className="absolute right-2 top-2 flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg bg-slate-950/70 text-white backdrop-blur transition-colors duration-200 hover:bg-red-600 focus:outline-none focus:ring-2 focus:ring-white"
        >
          <X size={15} />
        </button>
      )}
    </div>
    <div className="grid grid-cols-2 gap-2 p-2">
      <button
        type="button"
        onClick={onPreview}
        className="flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-violet-200 bg-violet-50 text-xs font-semibold text-violet-700 transition-colors duration-200 hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
      >
        <Eye size={14} /> 预览
      </button>
      <button
        type="button"
        onClick={onDownload}
        className="flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 text-xs font-semibold text-slate-700 transition-colors duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-400"
      >
        <Download size={14} /> 下载
      </button>
    </div>
  </div>
);

interface DeferredNumberInputProps {
  value: number;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
  ariaLabel: string;
  onCommit: (value: number) => void;
  className?: string;
}

/**
 * 数字输入在编辑期间保留原始文本，避免输入两位数或清空重输时被即时范围修正打断。
 * 只有失焦或按下 Enter 后，才将整数值收敛到模型支持的范围并提交。
 */
const DeferredNumberInput: React.FC<DeferredNumberInputProps> = ({
  value,
  min,
  max,
  step = 1,
  disabled = false,
  ariaLabel,
  onCommit,
  className,
}) => {
  const [draftValue, setDraftValue] = useState(String(value));
  const isEditingRef = useRef(false);

  useEffect(() => {
    if (!isEditingRef.current) setDraftValue(String(value));
  }, [value]);

  const commitValue = () => {
    isEditingRef.current = false;
    const parsedValue = Number(draftValue);
    const nextValue = Number.isFinite(parsedValue)
      ? clamp(Math.round(parsedValue), min, max)
      : clamp(Math.round(value), min, max);
    setDraftValue(String(nextValue));
    onCommit(nextValue);
  };

  return (
    <input
      type="text"
      inputMode="numeric"
      pattern="[0-9]*"
      value={draftValue}
      disabled={disabled}
      aria-label={ariaLabel}
      data-min={min}
      data-max={max}
      data-step={step}
      onFocus={() => {
        isEditingRef.current = true;
      }}
      onChange={(event) => setDraftValue(event.target.value)}
      onBlur={commitValue}
      onKeyDown={(event) => {
        if (event.key === 'Enter') event.currentTarget.blur();
      }}
      className={className}
    />
  );
};

interface VideoCostEstimateProps {
  modelLabel: string;
  resolution: string;
  duration: number;
  count: number;
  pricePerSecond: number;
  priceCurrency?: string;
  cnyToUsdRate: number;
  theme: 'dark' | 'light';
  compact?: boolean;
}

const DEFAULT_CNY_TO_USD_RATE = 0.14;

const getCnyToUsdRate = (config: any): number => {
  const rate = Number(config?.currency?.cnyToUsdRate);
  return Number.isFinite(rate) && rate > 0 ? rate : DEFAULT_CNY_TO_USD_RATE;
};

const getModelPricingCurrency = (modelConfig: any): string => {
  const configuredCurrency = String(
    modelConfig?.pricing?.currency || '',
  ).trim();
  if (configuredCurrency) return configuredCurrency.toUpperCase();
  // Backward compatibility for persisted Bailian prices created before the
  // currency field was introduced. Those official rate values are RMB.
  return String(modelConfig?.provider || '').toLowerCase() === 'bailian'
    ? 'CNY'
    : 'USD';
};

const convertPricingAmountToUsd = (
  amount: number,
  currency: string,
  cnyToUsdRate: number,
): number =>
  String(currency || 'USD').toUpperCase() === 'CNY'
    ? amount * cnyToUsdRate
    : amount;

const convertPricingAmountToCny = (
  amount: number,
  currency: string,
  cnyToUsdRate: number,
): number =>
  String(currency || 'USD').toUpperCase() === 'CNY'
    ? amount
    : amount / cnyToUsdRate;

const formatCnyEstimate = (
  total: number,
  currency: string,
  cnyToUsdRate: number,
): string => {
  if (!Number.isFinite(total) || total <= 0) return '待配置';
  return `¥${convertPricingAmountToCny(total, currency, cnyToUsdRate).toFixed(2)}`;
};

const VideoCostEstimate: React.FC<VideoCostEstimateProps> = ({
  modelLabel,
  resolution,
  duration,
  count,
  pricePerSecond,
  priceCurrency = 'USD',
  cnyToUsdRate,
  theme,
  compact = false,
}) => {
  const total = pricePerSecond * duration * count;
  const hasConfiguredPrice = Number.isFinite(total) && pricePerSecond > 0;
  const detail = `${modelLabel} · ${resolution} · ${duration} 秒 · ${count} 条`;
  const displayPrice = formatCnyEstimate(total, priceCurrency, cnyToUsdRate);
  const dark = theme === 'dark';
  return (
    <div
      className={`shrink-0 border text-left ${
        compact
          ? 'flex h-11 min-w-[128px] flex-col items-start justify-center rounded-lg px-2.5 py-1'
          : 'min-w-[112px] rounded-xl px-3 py-1.5'
      } ${
        dark
          ? 'border-fuchsia-300/30 bg-fuchsia-400/10'
          : 'border-fuchsia-100 bg-fuchsia-50'
      }`}
      data-testid="canvas-video-cost-estimate"
      aria-label={`预估生成费用：${displayPrice}`}
      title={`${detail}；预估费用 ${displayPrice}`}
    >
      {compact ? (
        <>
          <span
            className={
              dark
                ? 'text-[10px] leading-3 text-slate-300'
                : 'text-[10px] leading-3 text-slate-500'
            }
          >
            预估生成费用
          </span>
          <span
            className={
              dark
                ? 'text-xs font-bold leading-4 text-fuchsia-300'
                : 'text-xs font-bold leading-4 text-fuchsia-700'
            }
          >
            {displayPrice}
          </span>
        </>
      ) : (
        <>
          <div
            className={
              dark
                ? 'text-[10px] leading-4 text-slate-300'
                : 'text-[10px] leading-4 text-slate-500'
            }
          >
            预估生成费用
          </div>
          <div
            className={
              dark
                ? 'text-sm font-bold leading-5 text-fuchsia-300'
                : 'text-sm font-bold leading-5 text-fuchsia-700'
            }
          >
            {hasConfiguredPrice ? displayPrice : '待配置'}
          </div>
        </>
      )}
    </div>
  );
};

interface ImageCostEstimateProps {
  modelLabel: string;
  resolution: string;
  count: number;
  pricePerImage: number;
  priceCurrency?: string;
  cnyToUsdRate: number;
  theme: 'dark' | 'light';
  compact?: boolean;
}

const ImageCostEstimate: React.FC<ImageCostEstimateProps> = ({
  modelLabel,
  resolution,
  count,
  pricePerImage,
  priceCurrency = 'USD',
  cnyToUsdRate,
  theme,
  compact = false,
}) => {
  const total = pricePerImage * count;
  const hasConfiguredPrice = Number.isFinite(total) && pricePerImage > 0;
  const detail = `${modelLabel} · ${resolution} · ${count} 张`;
  const displayPrice = formatCnyEstimate(total, priceCurrency, cnyToUsdRate);
  const dark = theme === 'dark';
  return (
    <div
      className={`shrink-0 border text-left ${
        compact
          ? 'flex h-11 min-w-[128px] flex-col items-start justify-center rounded-lg px-2.5 py-1'
          : 'min-w-[112px] rounded-xl px-3 py-1.5'
      } ${
        dark
          ? 'border-violet-300/30 bg-violet-400/10'
          : 'border-violet-100 bg-violet-50'
      }`}
      data-testid="canvas-image-cost-estimate"
      aria-label={`预估生成费用：${displayPrice}`}
      title={`${detail}；预估费用 ${displayPrice}`}
    >
      {compact ? (
        <>
          <span
            className={
              dark
                ? 'text-[10px] leading-3 text-slate-300'
                : 'text-[10px] leading-3 text-slate-500'
            }
          >
            预估生成费用
          </span>
          <span
            className={
              dark
                ? 'text-xs font-bold leading-4 text-violet-300'
                : 'text-xs font-bold leading-4 text-violet-700'
            }
          >
            {displayPrice}
          </span>
        </>
      ) : (
        <>
          <div
            className={
              dark
                ? 'text-[10px] leading-4 text-slate-300'
                : 'text-[10px] leading-4 text-slate-500'
            }
          >
            预估生成费用
          </div>
          <div
            className={
              dark
                ? 'text-sm font-bold leading-5 text-violet-300'
                : 'text-sm font-bold leading-5 text-violet-700'
            }
          >
            {hasConfiguredPrice ? displayPrice : '待配置'}
          </div>
        </>
      )}
    </div>
  );
};

const STORAGE_KEY_PREFIX = 'adpulse:adgen-canvas:draft:';
const THEME_STORAGE_KEY = 'adgen-canvas-creation-theme';
const CUSTOM_IMAGE_COMMANDS_STORAGE_KEY =
  'adgen-canvas-custom-image-commands-v1';
const LAST_GENERATION_SETTINGS_STORAGE_KEY =
  'adgen-canvas-last-generation-settings-v1';
const FAVORITE_MODELS_STORAGE_KEY = 'adgen-canvas-favorite-models-v1';
const NODE_WIDTH = 286;
const NODE_HEIGHT = 182;
const TIDY_ORIGIN_X = 80;
const TIDY_ORIGIN_Y = 96;
const TIDY_COLUMN_GAP = 80;
const TIDY_ROW_GAP = 56;
const SELECTION_LAYOUT_GAP = 24;
const TEXT_PROMPT_NODE_HEIGHT = 150;
const NODE_TITLE_OUTSET = 32;
const SELECTION_GROUP_PADDING_X = 22;
const SELECTION_GROUP_PADDING_Y = 18;
const MIN_MEDIA_DISPLAY_SCALE = 0.5;
const MAX_MEDIA_DISPLAY_SCALE = 4;
const QUICK_SETTINGS_WIDTH = 760;
const QUICK_SETTINGS_GAP = 10;
const QUICK_SETTINGS_FALLBACK_HEIGHT = 208;

type VideoTaskCancelState = {
  taskId?: string;
  canCancel: boolean;
  reason: string;
  /** 提交请求仍在传输，取消请求可由后端按本地任务 ID 暂存。 */
  isSubmitting?: boolean;
  isCancelling?: boolean;
};

const IMAGE_GENERATION_MODE_OPTIONS: Array<{
  value: ImageGenerationMode;
  label: string;
}> = [
  { value: 'text_to_image', label: '文生图' },
  { value: 'reference_image', label: '参考图' },
];

const getSupportedImageGenerationModes = (
  modelConfig: any,
): ImageGenerationMode[] => {
  const capabilities: string[] = Array.isArray(modelConfig?.capabilities)
    ? modelConfig.capabilities
    : [];
  if (capabilities.length === 0) return ['text_to_image', 'reference_image'];

  const modes: ImageGenerationMode[] = [];
  if (
    capabilities.includes('image_generation') ||
    capabilities.includes('text_to_image')
  )
    modes.push('text_to_image');
  if (
    capabilities.includes('image_edit') ||
    capabilities.includes('image_to_image')
  )
    modes.push('reference_image');
  return modes.length > 0 ? modes : ['text_to_image'];
};

const resolveImageGenerationMode = (
  modelConfig: any,
  currentMode?: ImageGenerationMode,
  preferredMode: ImageGenerationMode = 'reference_image',
): ImageGenerationMode => {
  const supportedModes = getSupportedImageGenerationModes(modelConfig);
  if (currentMode && supportedModes.includes(currentMode)) return currentMode;
  if (supportedModes.includes(preferredMode)) return preferredMode;
  return supportedModes[0] || 'text_to_image';
};

const VIDEO_GENERATION_MODE_OPTIONS: Array<{
  value: VideoGenerationMode;
  label: string;
}> = [
  { value: 'text_to_video', label: '文生视频' },
  { value: 'reference_assets', label: '全能参考' },
  { value: 'reference_image', label: '图片参考' },
  { value: 'reference_video', label: '视频参考' },
  { value: 'first_frame', label: '首帧' },
  { value: 'first_last_frame', label: '首尾帧' },
];

const VIDEO_ANALYSIS_PROMPT_PRESETS = [
  {
    value: 'spoken-copy-and-chinese-translation',
    label: '识别口播文案与中文翻译',
    prompt:
      '请识别视频中的全部口播文案，完整转写原始语言内容；请在原文后提供准确、自然的中文翻译。若视频没有可识别的口播，请明确说明。',
  },
] as const;

const getAspectRatioPreviewStyle = (ratio: string): React.CSSProperties => {
  const [rawWidth, rawHeight] = ratio.split(':').map(Number);
  const width =
    Number.isFinite(rawWidth) && Number(rawWidth) > 0 ? Number(rawWidth) : 1;
  const height =
    Number.isFinite(rawHeight) && Number(rawHeight) > 0 ? Number(rawHeight) : 1;
  if (width >= height) {
    return { width: 28, height: Math.max(8, (28 * height) / width) };
  }
  return { width: Math.max(8, (24 * width) / height), height: 24 };
};

const getSupportedVideoGenerationModes = (
  modelConfig: any,
): VideoGenerationMode[] => {
  const expandConfiguredMode = (mode: unknown): VideoGenerationMode[] => {
    // 后台把图+视频组合记成 reference_assets。画布同时给出全能参考，
    // 并保留单独的图片/视频参考，方便只连一类素材时使用。
    if (mode === 'reference_assets') {
      return ['reference_assets', 'reference_image', 'reference_video'];
    }
    return VIDEO_GENERATION_MODE_OPTIONS.some((option) => option.value === mode)
      ? [mode as VideoGenerationMode]
      : [];
  };
  const configured = Array.isArray(modelConfig?.supported_input_modes)
    ? [
        ...new Set(
          modelConfig.supported_input_modes.flatMap(expandConfiguredMode),
        ),
      ]
    : [];
  if (configured.length > 0) return configured;

  const capabilities: string[] = Array.isArray(modelConfig?.capabilities)
    ? modelConfig.capabilities
    : [];
  const modes: VideoGenerationMode[] = [];
  if (capabilities.includes('text_to_video')) modes.push('text_to_video');
  if (capabilities.includes('reference_to_video')) {
    if (isWan3VideoModel(modelConfig?.provider_model)) {
      modes.push('reference_assets');
    }
    modes.push('reference_image', 'reference_video');
  }
  if (capabilities.includes('image_to_video')) {
    modes.push('first_frame');
    if (isWan3VideoModel(modelConfig?.provider_model)) {
      modes.push('first_last_frame');
    }
  }
  return modes;
};

const resolveVideoGenerationMode = (
  modelConfig: any,
  currentMode?: VideoGenerationMode,
  preferredMode: VideoGenerationMode = 'first_frame',
): VideoGenerationMode => {
  const supportedModes = getSupportedVideoGenerationModes(modelConfig);
  if (currentMode && supportedModes.includes(currentMode)) return currentMode;
  if (supportedModes.includes(preferredMode)) return preferredMode;
  return supportedModes[0] || 'text_to_video';
};
const MIN_ZOOM = 0.1;
/** 画布最大缩放，对标 LibTV 800%。 */
const MAX_ZOOM = 8;
const IMAGE_ASPECT_RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4'];
const VIDEO_ASPECT_RATIOS = ['16:9', '9:16'];
const DEFAULT_IMAGE_MODEL =
  DEFAULT_MEDIA_GENERATION_CONFIG.features.workspace_image.default_model;
const DEFAULT_VIDEO_MODEL =
  DEFAULT_MEDIA_GENERATION_CONFIG.features.workspace_video.default_model;
const DEFAULT_VIDEO_ANALYSIS_MODEL = 'qwen3.8-omni-flash';
const DEFAULT_MUSIC_MODEL =
  DEFAULT_MEDIA_GENERATION_CONFIG.features.workspace_music.default_model;
const DEFAULT_TTS_MODEL =
  DEFAULT_MEDIA_GENERATION_CONFIG.features.workspace_tts.default_model;
const LEGACY_IMAGE_MODELS: Record<string, string> = {
  'Nano Banana': 'gemini-2.5-flash-image',
  'Imagen 3': DEFAULT_IMAGE_MODEL,
  'GPT Image': DEFAULT_IMAGE_MODEL,
};
const LEGACY_VIDEO_MODELS: Record<string, string> = {
  'Veo 3.1': DEFAULT_VIDEO_MODEL,
  'Seedance 2.0': DEFAULT_VIDEO_MODEL,
  'Kling 2.1': DEFAULT_VIDEO_MODEL,
};

const normalizeChatModelAlias = (value: unknown) =>
  String(value || '')
    .trim()
    .toLowerCase()
    // Treat “2.0” and “2” as the same display version, while preserving
    // the database model ID selected below.
    .replace(/(\d+)\.0(?=$|[^\d])/g, '$1')
    .replace(/[\s_.-]+/g, '');

const resolveChatGenerationModelId = (
  requestedModel: string,
  availableModels: string[],
  modelCatalog: Record<string, any>,
) => {
  if (availableModels.includes(requestedModel)) return requestedModel;
  const normalizedRequested = normalizeChatModelAlias(requestedModel);
  if (!normalizedRequested) return undefined;
  return availableModels.find((modelId) => {
    const config = modelCatalog[modelId] || {};
    return [modelId, config.label, config.provider_model]
      .filter(Boolean)
      .some(
        (candidate) =>
          normalizeChatModelAlias(candidate) === normalizedRequested,
      );
  });
};

const fingerprintValue = (value: string) => {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
};

/**
 * 为浏览器草稿生成用户级命名空间，避免不同账号复用同一个 canvasId 时互相污染。
 * 命名空间只保存用户标识或令牌的短指纹，不把 JWT、用户 ID 原文写入 localStorage 键名。
 */
const getCanvasDraftStorageScope = () => {
  const token = authService.getToken();
  if (!token) return 'anonymous';

  try {
    const payloadPart = token.split('.')[1];
    if (payloadPart) {
      const normalized = payloadPart.replace(/-/g, '+').replace(/_/g, '/');
      const padded = normalized.padEnd(
        Math.ceil(normalized.length / 4) * 4,
        '=',
      );
      const payload = JSON.parse(window.atob(padded)) as Record<
        string,
        unknown
      >;
      const subject =
        payload.sub ||
        payload.adpulse_user_id ||
        payload.user_id ||
        payload.userId;
      if (subject !== undefined && subject !== null && String(subject).trim()) {
        return `user-${fingerprintValue(String(subject).trim())}`;
      }
    }
  } catch {
    return `token-${fingerprintValue(token)}`;
  }

  return `token-${fingerprintValue(token)}`;
};

// 比较时忽略更新时间，防止页面仅因重新加载就产生一次无内容变化的 PUT 保存。
const getDraftContentSignature = (draft: CanvasDraft) =>
  JSON.stringify({
    version: draft.version,
    title: draft.title,
    nodes: draft.nodes,
    edges: draft.edges,
    viewport: draft.viewport,
  });

const GENERATION_TYPE_LABELS: Record<string, string> = {
  batch_images: '批量图片生成',
  edit_image: '图片编辑',
  video_fission: '视频裂变',
  video_replicate: '视频复刻',
  extend_video: '视频延长',
  music_generation: '音乐生成',
  tts_generation: 'TTS 配音',
};

const generationTypeLabel = (generationType: string) =>
  GENERATION_TYPE_LABELS[generationType] || '历史生成记录';

type CanvasToolMode = 'select' | 'hand';
type CanvasTheme = 'light' | 'dark';
type MediaResizeCorner = 'ne' | 'nw' | 'se' | 'sw';

const CANVAS_SHORTCUT_GROUPS = [
  {
    title: '创建',
    items: [
      { label: '新建节点', keys: ['Tab'] },
      { label: '粘贴图片 / 文本', keys: ['Ctrl/⌘', 'V'] },
      { label: '复制节点', keys: ['Ctrl/⌘', 'D'] },
      { label: '拖出副本', keys: ['Alt/⌥', '拖动'] },
      { label: '拖出多个副本', keys: ['Alt/⌥', 'Shift', '拖动'] },
      { label: '生成内容', keys: ['Ctrl/⌘', 'Enter'] },
      { label: '删除节点 / 连线', keys: ['Delete'] },
    ],
  },
  {
    title: '缩放',
    items: [
      { label: '放大', keys: ['Ctrl/⌘', '+'] },
      { label: '缩小', keys: ['Ctrl/⌘', '−'] },
      { label: '适应画布', keys: ['Ctrl/⌘', '0'] },
    ],
  },
  {
    title: '移动画布',
    items: [
      { label: '选择 / 移动', keys: ['V'] },
      { label: '抓手工具', keys: ['H'] },
      { label: '临时抓手', keys: ['Space', '拖动'] },
    ],
  },
  {
    title: '其他',
    items: [
      { label: '撤销', keys: ['Ctrl/⌘', 'Z'] },
      { label: '重做', keys: ['Ctrl/⌘', 'Shift', 'Z'] },
      { label: '保存画布', keys: ['Ctrl/⌘', 'S'] },
      { label: '关闭 / 取消', keys: ['Esc'] },
      { label: '快捷键面板', keys: ['?'] },
    ],
  },
] as const;

interface NodeMenuState {
  left: number;
  top: number;
  nodePosition: { x: number; y: number };
}

interface CanvasContextMenuState extends NodeMenuState {
  targetNodeId?: string;
  targetEdgeId?: string;
  quickMenuLeft: number;
  quickMenuTop: number;
}

interface CanvasQuickImageCommand {
  id: string;
  label: string;
  description: string;
  prompt: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  badge?: string;
}

interface CanvasCustomImageCommand {
  id: string;
  label: string;
  prompt: string;
  createdAt: string;
}

interface CanvasImageReference {
  id: string;
  alias: string;
  url: string;
  sourceNodeId: string;
  sourceTitle: string;
  mediaType?: 'image' | 'video' | 'audio' | 'file' | 'link';
}

interface CanvasLastGenerationSettings {
  image?: Pick<
    CanvasGenerationConfig,
    'model' | 'aspectRatio' | 'resolution' | 'count'
  >;
  video?: Pick<
    CanvasGenerationConfig,
    'model' | 'aspectRatio' | 'resolution' | 'duration' | 'count'
  >;
}

interface CanvasHistorySnapshot {
  nodes: CanvasNodeData[];
  edges: CanvasEdgeData[];
}

const NODE_META: Record<
  CanvasNodeKind,
  {
    label: string;
    description: string;
    icon: React.ComponentType<{ size?: number; className?: string }>;
    accent: string;
    surface: string;
    defaultTitle: string;
    defaultModel?: string;
  }
> = {
  text: {
    label: '文本提示词',
    description: '编写创意、镜头或产品描述',
    icon: TextCursorInput,
    accent: 'text-slate-700',
    surface: 'bg-slate-100',
    defaultTitle: '创意提示词',
  },
  asset: {
    label: '云素材',
    description: '引用图片、视频、音频、文档或网页',
    icon: FileImage,
    accent: 'text-cyan-700',
    surface: 'bg-cyan-50',
    defaultTitle: '参考素材',
  },
  image: {
    label: '图片生成',
    description: '根据提示词和参考图生成图片',
    icon: ImageIcon,
    accent: 'text-violet-700',
    surface: 'bg-violet-50',
    defaultTitle: '图片生成',
    defaultModel: DEFAULT_IMAGE_MODEL,
  },
  video: {
    label: '视频生成',
    description: '将提示词或参考素材转成视频',
    icon: Video,
    accent: 'text-fuchsia-700',
    surface: 'bg-fuchsia-50',
    defaultTitle: '视频生成',
    defaultModel: DEFAULT_VIDEO_MODEL,
  },
  video_analysis: {
    label: '视频分析',
    description: '识别主体、镜头、音频与可复用提示词',
    icon: MessageSquareText,
    accent: 'text-cyan-700',
    surface: 'bg-cyan-50',
    defaultTitle: '视频分析',
    defaultModel: DEFAULT_VIDEO_ANALYSIS_MODEL,
  },
  music: {
    label: '音乐创作',
    description: '根据氛围、风格和节奏描述生成音乐',
    icon: Music2,
    accent: 'text-pink-700',
    surface: 'bg-pink-50',
    defaultTitle: '音乐创作',
  },
  tts: {
    label: 'TTS 配音',
    description: '将文案转换为自然流畅的语音',
    icon: Mic2,
    accent: 'text-sky-700',
    surface: 'bg-sky-50',
    defaultTitle: 'TTS 配音',
  },
  output: {
    label: '输出结果',
    description: '汇总和导出工作流最终结果',
    icon: Box,
    accent: 'text-emerald-700',
    surface: 'bg-emerald-50',
    defaultTitle: '最终输出',
  },
};

// Keep rendering existing analysis nodes, but hide this unfinished capability
// from every new-node menu until it is ready to be reopened.
const ENABLE_VIDEO_ANALYSIS_NODE = false;

const UNKNOWN_NODE_META = {
  ...NODE_META.asset,
  label: '未识别节点',
  description: '该历史节点类型暂不受当前版本支持',
  defaultTitle: '未识别节点',
};

/**
 * 历史画布可能由比当前页面更新的版本保存。不能因某个节点类型尚未发布，
 * 就让整张画布在读取 `label` 等展示字段时中断渲染。
 */
const getNodeMeta = (kind: string | undefined) =>
  NODE_META[kind as CanvasNodeKind] || UNKNOWN_NODE_META;

const MULTI_ANGLE_CHARACTER_SHEET_PROMPT = `Create a professional character reference sheet based strictly on the
uploaded reference image. Use a clean, uniform light gray-white background
(#F2F2F2 plain backdrop) throughout the entire sheet, and present the sheet
as a technical model turnaround while matching the exact visual style of the
reference (same realism level, rendering approach, texture, color treatment,
and overall aesthetic). 16:9 widescreen composition.
LEFT HALF — Full body turnaround:
Three full body standing views of the same character arranged in a row in
this order: front view, left profile view (facing left), back view.
Keep the subject in a relaxed A-pose, with consistent scale and alignment
between views, accurate anatomy, and clear silhouette. Full body visible
from head to toe, no cropping. Uniform framing and consistent head height
across the full-body lineup.
RIGHT HALF — Expression close-up grid:
A 2x2 grid of highly detailed head-and-shoulder bust portraits of the same
character, in this order (top-left to bottom-right):
1. neutral, no expression  2. gentle smile  3. angry, furrowed brows
4. crying, tears.
Same character, same hairstyle and outfit, face fills the frame, consistent
facial scale across all portraits, identical framing in every cell.
Global requirements:
Maintain perfect identity consistency across every panel.
One single uniform light gray-white background across all panels, no
gradients, no vignettes, no visible seams between panels.
Lighting should be consistent across all panels (same direction, intensity,
and softness), with natural, controlled shadows that preserve detail without
dramatic mood shifts.
Even spacing and clean panel separation. Orthographic projection, no
perspective distortion.
Output a clean, smooth, noise-free render with refined detail and soft
natural gradients: no over-sharpening, no film grain, no JPEG artifacts,
no chromatic aberration, no ringing or aliasing, no harsh pixelated edges.
No extra props, no watermark, no text labels.`;

const QUICK_IMAGE_COMMANDS: CanvasQuickImageCommand[] = [
  {
    id: 'portrait-texture',
    label: '人像质感调节',
    description: '自然优化肤质、细节与层次',
    prompt:
      '保持原图人物身份、五官、发型、服装、姿态和构图不变，自然优化人像肤质、皮肤纹理、面部细节与明暗层次。去除塑料感和过度磨皮，呈现真实高级、细腻通透的商业人像质感。',
    icon: Sparkles,
    badge: 'NEW',
  },
  {
    id: 'panorama-expand',
    label: '全景扩图',
    description: '智能延展画面与环境',
    prompt:
      '以原图为中心进行自然的全景扩图，保持主体、风格、透视、光线和色彩完全一致，智能补全画面四周环境，扩展出更宽广且连续可信的场景，不裁切或改变主体。',
    icon: Maximize2,
  },
  {
    id: 'multi-angle',
    label: '多角度生成',
    description: '生成统一主体的多视角设定',
    prompt: MULTI_ANGLE_CHARACTER_SHEET_PROMPT,
    icon: Focus,
  },
  {
    id: 'studio-lighting',
    label: '专业打光',
    description: '升级为商业摄影布光',
    prompt:
      '保持原图主体、构图和内容不变，将光线优化为专业商业摄影棚布光：清晰主光、柔和补光、自然轮廓光，控制高光与阴影层次，提升立体感、材质表现和高级感。',
    icon: Sun,
  },
  {
    id: 'nine-grid-storyboard',
    label: '九宫格分镜',
    description: '生成 3×3 连贯镜头方案',
    prompt:
      '以原图主体为核心生成3×3九宫格电影分镜，包含全景、中景、近景、特写、俯拍、仰拍、侧面和动态镜头。九个画面保持主体身份、造型、场景与色彩统一，镜头语言丰富且叙事连贯。',
    icon: Grid3X3,
  },
  {
    id: 'character-sheet',
    label: '角色设定图',
    description: '角色全身、侧面与细节设定',
    prompt:
      '将原图角色整理为专业角色设定图，包含正面全身、侧面、背面、三分之二视角、面部表情和服装细节。保持人物身份与造型严格一致，背景简洁，排版清晰。',
    icon: CircleDot,
  },
  {
    id: 'scene-sheet',
    label: '场景设定图',
    description: '统一风格的环境概念设定',
    prompt:
      '基于原图的视觉风格生成专业场景设定图，展示场景全貌、主要区域、关键道具、材质细节、不同景别与光照氛围。保持空间逻辑、透视、色彩和世界观统一。',
    icon: ImageIcon,
  },
  {
    id: 'product-sheet',
    label: '产品设定图',
    description: '产品多角度与材质细节',
    prompt:
      '将原图产品生成专业产品设定图，包含正面、侧面、背面、俯视、三分之二视角、结构拆解和材质细节。保持产品形态、比例、品牌元素和颜色严格一致，使用高级商业排版。',
    icon: Box,
  },
  {
    id: 'cinematic-light',
    label: '电影级光影校正',
    description: '优化曝光、色彩与电影氛围',
    prompt:
      '保持原图内容和主体完全不变，进行电影级光影与色彩校正：恢复高光和暗部细节，改善曝光、白平衡、对比度和色彩层次，增加自然景深与空气感，呈现克制高级的电影质感。',
    icon: Video,
  },
  {
    id: 'hd-restore',
    label: '高清修复',
    description: '增强清晰度并修复细节',
    prompt:
      '对原图进行高质量高清修复，保持人物身份、主体结构、构图和风格不变。修复模糊、噪点、压缩痕迹和破损细节，增强纹理、边缘与微小细节，避免过度锐化和虚假纹理。',
    icon: FileImage,
  },
];

const REMOVE_BACKGROUND_COMMAND: CanvasQuickImageCommand = {
  id: 'remove-background',
  label: '去背景',
  description: '抠出主体并去掉背景',
  prompt:
    '将图片主体完整抠出，彻底删除原背景，主体边缘干净利落并保留发丝与细节。主体放在纯白背景上，不要改变主体身份、姿态、服装、颜色、比例和构图。',
  icon: Sparkles,
};

const ERASE_OBJECT_PROMPT =
  'Remove the objects marked by the white mask. Fill the removed area naturally so it matches the surrounding background, lighting, perspective and texture. Keep all unmasked content completely unchanged.';

const SAMPLE_NODES: CanvasNodeData[] = [
  {
    id: 'sample-text',
    kind: 'text',
    title: '夏季广告创意',
    x: 110,
    y: 150,
    prompt: '为轻盈、通透的夏季护肤产品制作一支具有高级感的广告。',
    textGenerationMode: 'image',
    textImageConfig: {
      model: DEFAULT_IMAGE_MODEL,
      count: 1,
      aspectRatio: '16:9',
      resolution: '1K',
    },
    model: DEFAULT_IMAGE_MODEL,
    count: 1,
    aspectRatio: '16:9',
    resolution: '1K',
    status: 'ready',
  },
  {
    id: 'sample-image',
    kind: 'image',
    title: '生成主视觉',
    x: 470,
    y: 150,
    prompt: '自然光、玻璃质感、蓝紫色渐变背景，产品位于画面中心。',
    model: DEFAULT_IMAGE_MODEL,
    count: 1,
    aspectRatio: '16:9',
    resolution: '1K',
    imageGenerationMode: 'reference_image',
    status: 'draft',
  },
  {
    id: 'sample-video',
    kind: 'video',
    title: '生成动态广告',
    x: 830,
    y: 150,
    prompt: '镜头缓慢推进，水珠沿瓶身滑落，柔和光线在背景中流动。',
    model: DEFAULT_VIDEO_MODEL,
    count: 1,
    aspectRatio: '16:9',
    resolution:
      DEFAULT_MEDIA_GENERATION_CONFIG.features.workspace_video
        .default_resolution,
    extensionCount: 0,
    videoGenerationMode: 'first_frame',
    status: 'draft',
  },
];

const SAMPLE_EDGES: CanvasEdgeData[] = [
  { id: 'sample-edge-1', source: 'sample-text', target: 'sample-image' },
  { id: 'sample-edge-2', source: 'sample-image', target: 'sample-video' },
];

const createId = (prefix: string) => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
};

/**
 * 去掉历史「副本」后缀和末尾数字，得到复制时的基础名。
 * 「视频生成 副本 副本」和「视频生成 3」都会收成「视频生成」。
 */
const getDuplicatedNodeTitleBase = (title: string) =>
  title
    .replace(/(?:\s+副本)+$/u, '')
    .replace(/\s+\d+$/u, '')
    .trimEnd();

const getDuplicatedNodeIndex = (title: string, base: string): number | null => {
  if (title === base) return 1;
  const prefix = `${base} `;
  if (!title.startsWith(prefix)) return null;
  const suffix = title.slice(prefix.length);
  return /^\d+$/u.test(suffix) ? Number(suffix) : null;
};

/** 在已有标题里取同基础名的最大序号，再 +1，例如 视频生成 → 视频生成 2。 */
const nextDuplicatedNodeTitle = (
  sourceTitle: string,
  usedTitles: Iterable<string>,
) => {
  const base =
    getDuplicatedNodeTitleBase(sourceTitle) || sourceTitle.trim() || '未命名';
  let maxIndex = 1;
  for (const title of usedTitles) {
    const index = getDuplicatedNodeIndex(title, base);
    if (index !== null) maxIndex = Math.max(maxIndex, index);
  }
  return `${base} ${maxIndex + 1}`;
};

const cloneCanvasNode = (
  source: CanvasNodeData,
  newId: string,
  offsetX = 0,
  offsetY = 0,
  usedTitles: string[] = [],
): CanvasNodeData => ({
  ...source,
  id: newId,
  title: nextDuplicatedNodeTitle(source.title, usedTitles),
  x: Math.round(source.x + offsetX),
  y: Math.round(source.y + offsetY),
  textImageConfig: source.textImageConfig
    ? { ...source.textImageConfig }
    : undefined,
  textVideoConfig: source.textVideoConfig
    ? { ...source.textVideoConfig }
    : undefined,
  count: source.count,
  resultUrls: source.resultUrls ? [...source.resultUrls] : undefined,
  resultHistory: source.resultHistory?.map((result) => ({ ...result })),
  imageReferenceSourceOrder: source.imageReferenceSourceOrder
    ? [...source.imageReferenceSourceOrder]
    : undefined,
  // 副本是新节点，不能沿用源节点的官方素材库登记。
  officialAssetEnabled: false,
  officialAssetId: undefined,
  officialAssetStatus: 'idle',
  officialAssetError: undefined,
  // Alt 拖出或复制出的节点不进入原分组，避免误带上分组框。
  groupId: undefined,
});

/** Ctrl/⌘+D 或「创建副本」时保留连线：选中组内部的边，以及连到组外上下游的边。 */
const cloneEdgesForDuplication = (
  edges: CanvasEdgeData[],
  idMap: Record<string, string>,
): CanvasEdgeData[] => {
  const existing = new Set(
    edges.map((edge) => `${edge.source}->${edge.target}`),
  );
  const next: CanvasEdgeData[] = [];
  const add = (source: string, target: string) => {
    if (!source || !target || source === target) return;
    const key = `${source}->${target}`;
    if (existing.has(key)) return;
    existing.add(key);
    next.push({
      id: createId('edge'),
      source,
      target,
    });
  };
  for (const edge of edges) {
    const mappedSource = idMap[edge.source];
    const mappedTarget = idMap[edge.target];
    if (mappedSource && mappedTarget) {
      add(mappedSource, mappedTarget);
      continue;
    }
    if (mappedTarget) add(edge.source, mappedTarget);
    if (mappedSource) add(mappedSource, edge.target);
  }
  return next;
};

const moveArrayItem = <T,>(list: T[], fromIndex: number, toIndex: number) => {
  if (
    fromIndex === toIndex ||
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= list.length ||
    toIndex >= list.length
  ) {
    return list;
  }
  const next = [...list];
  const [item] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, item);
  return next;
};

/** 删掉某个 @图片N / @视频N 后，去掉提示词里的引用，避免残留旧编号。 */
const stripPromptImageMention = (prompt: string, alias: string) =>
  prompt
    .replace(new RegExp(`@${alias}(?!\\d)`, 'g'), '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/ *\n{3,}/g, '\n\n')
    .replace(/ +\n/g, '\n')
    .replace(/\n +/g, '\n');

/** 参考素材换序后，按来源把提示词里的 @图片N / @视频N 改成新编号，避免用户手改关键词。 */
const remapPromptImageMentions = (
  prompt: string,
  fromReferences: CanvasImageReference[],
  toReferences: CanvasImageReference[],
) => {
  const nextAliasBySource = new Map(
    toReferences.map((reference) => [
      `${reference.sourceNodeId}:${reference.url}`,
      reference.alias,
    ]),
  );
  const aliasMap = new Map<string, string>();
  fromReferences.forEach((reference) => {
    const nextAlias = nextAliasBySource.get(
      `${reference.sourceNodeId}:${reference.url}`,
    );
    if (nextAlias) aliasMap.set(reference.alias, nextAlias);
  });
  return prompt.replace(
    /@(图片|视频|音频|文档|网页)(\d+)/g,
    (match, prefix: string, digits: string) => {
      const nextAlias = aliasMap.get(`${prefix}${digits}`);
      return nextAlias ? `@${nextAlias}` : match;
    },
  );
};

const applyImageReferenceOrder = (
  references: Omit<CanvasImageReference, 'alias'>[],
  order?: string[],
) => {
  if (!order?.length) return references;
  const remaining = [...references];
  const ordered: Omit<CanvasImageReference, 'alias'>[] = [];
  order.forEach((sourceNodeId) => {
    const index = remaining.findIndex(
      (item) => item.sourceNodeId === sourceNodeId,
    );
    if (index >= 0) ordered.push(remaining.splice(index, 1)[0]);
  });
  return [...ordered, ...remaining];
};

const isCanvasAudioReferenceSource = (incomingNode: CanvasNodeData) =>
  incomingNode.kind === 'music' ||
  incomingNode.kind === 'tts' ||
  incomingNode.resultAssetType === 'audio' ||
  incomingNode.assetType === 'audio';

const isCanvasFileReferenceSource = (incomingNode: CanvasNodeData) =>
  incomingNode.assetType === 'file' || incomingNode.resultAssetType === 'file';

const isCanvasLinkReferenceSource = (incomingNode: CanvasNodeData) =>
  incomingNode.assetType === 'link' || incomingNode.resultAssetType === 'link';

const isCanvasVideoReferenceSource = (incomingNode: CanvasNodeData) =>
  incomingNode.kind === 'video' ||
  incomingNode.resultAssetType === 'video' ||
  (incomingNode.kind === 'asset' && incomingNode.assetType === 'video');

const isCanvasImageReferenceSource = (incomingNode: CanvasNodeData) => {
  if (
    isCanvasVideoReferenceSource(incomingNode) ||
    isCanvasAudioReferenceSource(incomingNode) ||
    isCanvasFileReferenceSource(incomingNode) ||
    isCanvasLinkReferenceSource(incomingNode)
  ) {
    return false;
  }
  return (
    incomingNode.kind === 'image' ||
    incomingNode.kind === 'text' ||
    (incomingNode.kind === 'asset' &&
      (incomingNode.assetType === 'image' || !incomingNode.assetType))
  );
};

/**
 * 收藏模型排在列表最前，顺序以用户收藏先后为准；未收藏的保持原目录顺序。
 */
const sortModelsByFavorite = (models: string[], favoriteIds: string[]) => {
  const available = new Set(models);
  const favorites = favoriteIds.filter((id) => available.has(id));
  const favoriteSet = new Set(favorites);
  return [...favorites, ...models.filter((id) => !favoriteSet.has(id))];
};

const readStoredFavoriteModels = (): string[] => {
  try {
    const raw = window.localStorage.getItem(FAVORITE_MODELS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (id): id is string => typeof id === 'string' && id.trim().length > 0,
    );
  } catch {
    return [];
  }
};

const writeStoredFavoriteModels = (models: string[]) => {
  try {
    window.localStorage.setItem(
      FAVORITE_MODELS_STORAGE_KEY,
      JSON.stringify(models),
    );
  } catch {
    // 浏览器禁用存储时仅保留当前会话收藏。
  }
};

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));
const MINIMAP_WIDTH = 200;
const MINIMAP_HEIGHT = 132;

const rectsOverlap = (
  a: { height: number; width: number; x: number; y: number },
  b: { height: number; width: number; x: number; y: number },
) =>
  a.x < b.x + b.width &&
  a.x + a.width > b.x &&
  a.y < b.y + b.height &&
  a.y + a.height > b.y;

const getViewportWorldRect = (
  viewport: CanvasViewport,
  canvasSize: { height: number; width: number },
) => {
  const zoom = Math.max(viewport.zoom, 0.01);
  return {
    height: Math.max(1, canvasSize.height / zoom),
    width: Math.max(1, canvasSize.width / zoom),
    x: -viewport.x / zoom,
    y: -viewport.y / zoom,
  };
};

const unionWorldBounds = (
  current: { maxX: number; maxY: number; minX: number; minY: number } | null,
  next: { maxX: number; maxY: number; minX: number; minY: number } | null,
) => {
  if (!current) return next;
  if (!next) return current;
  const merged = {
    maxX: Math.max(current.maxX, next.maxX),
    maxY: Math.max(current.maxY, next.maxY),
    minX: Math.min(current.minX, next.minX),
    minY: Math.min(current.minY, next.minY),
  };
  if (
    merged.minX === current.minX &&
    merged.minY === current.minY &&
    merged.maxX === current.maxX &&
    merged.maxY === current.maxY
  ) {
    return current;
  }
  return merged;
};

const buildCanvasMinimapLayout = (
  nodes: CanvasNodeData[],
  selectedNodeIds: Set<string>,
  viewport: CanvasViewport,
  canvasSize: { height: number; width: number },
  getDimensions: (node: CanvasNodeData) => { height: number; width: number },
  exploredWorld: {
    maxX: number;
    maxY: number;
    minX: number;
    minY: number;
  } | null,
  includeViewport = true,
) => {
  const view = getViewportWorldRect(viewport, canvasSize);

  let contentMinX = Number.POSITIVE_INFINITY;
  let contentMinY = Number.POSITIVE_INFINITY;
  let contentMaxX = Number.NEGATIVE_INFINITY;
  let contentMaxY = Number.NEGATIVE_INFINITY;
  const nodeRects = nodes.map((node) => {
    const size = getDimensions(node);
    contentMinX = Math.min(contentMinX, node.x);
    contentMinY = Math.min(contentMinY, node.y);
    contentMaxX = Math.max(contentMaxX, node.x + size.width);
    contentMaxY = Math.max(contentMaxY, node.y + size.height);
    return {
      height: size.height,
      id: node.id,
      selected: selectedNodeIds.has(node.id),
      width: size.width,
      x: node.x,
      y: node.y,
    };
  });

  const hasNodes = Number.isFinite(contentMinX);
  if (!hasNodes) {
    contentMinX = view.x;
    contentMinY = view.y;
    contentMaxX = view.x + view.width;
    contentMaxY = view.y + view.height;
  }

  const pad = 64;
  let minX = contentMinX - pad;
  let minY = contentMinY - pad;
  let maxX = contentMaxX + pad;
  let maxY = contentMaxY + pad;
  if (exploredWorld) {
    minX = Math.min(minX, exploredWorld.minX);
    minY = Math.min(minY, exploredWorld.minY);
    maxX = Math.max(maxX, exploredWorld.maxX);
    maxY = Math.max(maxY, exploredWorld.maxY);
  }
  if (includeViewport) {
    minX = Math.min(minX, view.x);
    minY = Math.min(minY, view.y);
    maxX = Math.max(maxX, view.x + view.width);
    maxY = Math.max(maxY, view.y + view.height);
  }

  const worldWidth = Math.max(1, maxX - minX);
  const worldHeight = Math.max(1, maxY - minY);
  const scale = Math.min(
    MINIMAP_WIDTH / worldWidth,
    MINIMAP_HEIGHT / worldHeight,
  );
  const offsetX = (MINIMAP_WIDTH - worldWidth * scale) / 2;
  const offsetY = (MINIMAP_HEIGHT - worldHeight * scale) / 2;
  const toMini = (x: number, y: number, width = 0, height = 0) => ({
    height: height * scale,
    width: width * scale,
    x: (x - minX) * scale + offsetX,
    y: (y - minY) * scale + offsetY,
  });

  return {
    content: toMini(
      contentMinX,
      contentMinY,
      Math.max(1, contentMaxX - contentMinX),
      Math.max(1, contentMaxY - contentMinY),
    ),
    minX,
    minY,
    nodes: nodeRects.map((node) => ({
      id: node.id,
      selected: node.selected,
      ...toMini(node.x, node.y, node.width, node.height),
    })),
    offsetX,
    offsetY,
    scale,
    viewport: toMini(view.x, view.y, view.width, view.height),
  };
};

const detailsHoverCloseTimers = new WeakMap<HTMLDetailsElement, number>();

const openDetailsOnHover = (event: React.MouseEvent<HTMLDetailsElement>) => {
  const details = event.currentTarget;
  const closeTimer = detailsHoverCloseTimers.get(details);
  if (closeTimer !== undefined) {
    window.clearTimeout(closeTimer);
    detailsHoverCloseTimers.delete(details);
  }
  details.open = true;
};

const closeDetailsOnHover = (event: React.MouseEvent<HTMLDetailsElement>) => {
  const details = event.currentTarget;
  const previousTimer = detailsHoverCloseTimers.get(details);
  if (previousTimer !== undefined) window.clearTimeout(previousTimer);

  const closeTimer = window.setTimeout(() => {
    detailsHoverCloseTimers.delete(details);
    if (
      !details.matches(':hover') &&
      !details.contains(document.activeElement)
    ) {
      details.open = false;
    }
  }, 220);
  detailsHoverCloseTimers.set(details, closeTimer);
};

const areAnchorMapsEqual = (
  current: Record<string, { x: number; y: number }>,
  next: Record<string, { x: number; y: number }>,
) => {
  const currentKeys = Object.keys(current);
  const nextKeys = Object.keys(next);
  return (
    currentKeys.length === nextKeys.length &&
    nextKeys.every((key) => {
      const currentAnchor = current[key];
      const nextAnchor = next[key];
      return Boolean(
        currentAnchor &&
          nextAnchor &&
          Math.abs(currentAnchor.x - nextAnchor.x) < 0.05 &&
          Math.abs(currentAnchor.y - nextAnchor.y) < 0.05,
      );
    })
  );
};

const parseConfiguredAspectRatio = (value?: string) => {
  const match = value?.trim().match(/^(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)$/);
  if (!match) return undefined;
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  )
    return undefined;
  return width / height;
};

const getNodeDimensions = (node: CanvasNodeData) => {
  // 尚未生成时使用配置比例，生成后再以媒体真实比例校准，确保节点边框始终贴合内容。
  const aspectRatio =
    node.mediaAspectRatio || parseConfiguredAspectRatio(node.aspectRatio);
  if (!aspectRatio || !Number.isFinite(aspectRatio) || aspectRatio <= 0) {
    return { width: NODE_WIDTH, height: NODE_HEIGHT };
  }

  const storedScale = node.mediaDisplayScale;
  const scale =
    storedScale && Number.isFinite(storedScale)
      ? clamp(storedScale, MIN_MEDIA_DISPLAY_SCALE, MAX_MEDIA_DISPLAY_SCALE)
      : 1;
  const dimensions =
    aspectRatio >= 1
      ? { width: NODE_WIDTH, height: NODE_WIDTH / aspectRatio }
      : { width: NODE_WIDTH * aspectRatio, height: NODE_WIDTH };

  return {
    width: dimensions.width * scale,
    height: dimensions.height * scale,
  };
};

const getSelectionGroupBounds = (
  selectedNodes: CanvasNodeData[],
  getDimensions: (node: CanvasNodeData) => { width: number; height: number },
) => {
  if (selectedNodes.length < 2) return null;
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  selectedNodes.forEach((node) => {
    const { width, height } = getDimensions(node);
    minX = Math.min(minX, node.x);
    minY = Math.min(minY, node.y - NODE_TITLE_OUTSET);
    maxX = Math.max(maxX, node.x + width);
    maxY = Math.max(maxY, node.y + height);
  });
  return {
    left: minX - SELECTION_GROUP_PADDING_X,
    top: minY - SELECTION_GROUP_PADDING_Y,
    width: maxX - minX + SELECTION_GROUP_PADDING_X * 2,
    height: maxY - minY + SELECTION_GROUP_PADDING_Y * 2,
  };
};

const pruneSingletonGroups = (canvasNodes: CanvasNodeData[]) => {
  const memberCount = new Map<string, number>();
  canvasNodes.forEach((node) => {
    if (!node.groupId) return;
    memberCount.set(node.groupId, (memberCount.get(node.groupId) || 0) + 1);
  });
  return canvasNodes.map((node) =>
    node.groupId && (memberCount.get(node.groupId) || 0) < 2
      ? { ...node, groupId: undefined }
      : node,
  );
};

/** 当前选区正好是某一个持久分组的全部成员时，视为“选中了这个组”。 */
const findExactSelectedGroupId = (
  canvasNodes: CanvasNodeData[],
  selectedIds: Set<string>,
) => {
  if (selectedIds.size < 2) return null;
  let groupId: string | undefined;
  for (const node of canvasNodes) {
    if (!selectedIds.has(node.id)) continue;
    if (!node.groupId) return null;
    if (!groupId) groupId = node.groupId;
    else if (node.groupId !== groupId) return null;
  }
  if (!groupId) return null;
  const memberCount = canvasNodes.filter(
    (node) => node.groupId === groupId,
  ).length;
  return memberCount === selectedIds.size ? groupId : null;
};

const listPersistentNodeGroups = (
  canvasNodes: CanvasNodeData[],
  getDimensions: (node: CanvasNodeData) => { width: number; height: number },
) => {
  const membersByGroup = new Map<string, CanvasNodeData[]>();
  canvasNodes.forEach((node) => {
    if (!node.groupId) return;
    const members = membersByGroup.get(node.groupId) || [];
    members.push(node);
    membersByGroup.set(node.groupId, members);
  });
  return Array.from(membersByGroup.entries())
    .map(([id, members]) => ({
      id,
      members,
      bounds: getSelectionGroupBounds(members, getDimensions),
    }))
    .filter(
      (
        group,
      ): group is {
        id: string;
        members: CanvasNodeData[];
        bounds: NonNullable<ReturnType<typeof getSelectionGroupBounds>>;
      } => Boolean(group.bounds),
    );
};

const areNodePositionsEqual = (
  first: CanvasNodeData[],
  second: CanvasNodeData[],
) => {
  if (first.length !== second.length) return false;
  const secondById = new Map(second.map((node) => [node.id, node]));
  return first.every((node) => {
    const other = secondById.get(node.id);
    return Boolean(other && node.x === other.x && node.y === other.y);
  });
};

/**
 * 按连线把节点排成从左到右的分层网格，类似 libtv 的整理画布。
 * 只改坐标，不改连接和卡片内容。
 */
const layoutCanvasNodes = (
  nodes: CanvasNodeData[],
  edges: CanvasEdgeData[],
  getDimensions: (node: CanvasNodeData) => { width: number; height: number },
): CanvasNodeData[] => {
  if (nodes.length === 0) return nodes;

  const nodeIds = new Set(nodes.map((node) => node.id));
  const layerById = new Map<string, number>();
  const resolveLayer = (nodeId: string, visiting: Set<string>): number => {
    const cached = layerById.get(nodeId);
    if (cached !== undefined) return cached;
    if (visiting.has(nodeId)) return 0;
    visiting.add(nodeId);
    const parentIds = edges
      .filter((edge) => edge.target === nodeId && nodeIds.has(edge.source))
      .map((edge) => edge.source);
    const layer =
      parentIds.length === 0
        ? 0
        : Math.max(
            ...parentIds.map((parentId) => resolveLayer(parentId, visiting)),
          ) + 1;
    visiting.delete(nodeId);
    layerById.set(nodeId, layer);
    return layer;
  };
  nodes.forEach((node) => resolveLayer(node.id, new Set()));

  const columns = new Map<number, CanvasNodeData[]>();
  nodes.forEach((node) => {
    const column = layerById.get(node.id) || 0;
    const columnNodes = columns.get(column) || [];
    columnNodes.push(node);
    columns.set(column, columnNodes);
  });

  const sortedColumns = Array.from(columns.keys()).sort(
    (left, right) => left - right,
  );
  sortedColumns.forEach((column) => {
    columns
      .get(column)
      ?.sort((left, right) => left.y - right.y || left.x - right.x);
  });

  const positions = new Map<string, { x: number; y: number }>();
  let columnX = TIDY_ORIGIN_X;
  sortedColumns.forEach((column) => {
    const columnNodes = columns.get(column) || [];
    const columnWidth = Math.max(
      ...columnNodes.map((node) => getDimensions(node).width),
      NODE_WIDTH,
    );
    let columnY = TIDY_ORIGIN_Y;
    columnNodes.forEach((node) => {
      positions.set(node.id, {
        x: Math.round(columnX),
        y: Math.round(columnY),
      });
      columnY += getDimensions(node).height + TIDY_ROW_GAP;
    });
    columnX += columnWidth + TIDY_COLUMN_GAP;
  });

  return nodes.map((node) => {
    const nextPosition = positions.get(node.id);
    return nextPosition
      ? { ...node, x: nextPosition.x, y: nextPosition.y }
      : node;
  });
};

type SelectionLayoutMode = 'grid' | 'horizontal' | 'vertical';

/**
 * 框选后的局部排列：以当前选区左上角为原点，只移动选中节点。
 */
const arrangeSelectedNodes = (
  nodes: CanvasNodeData[],
  selectedIds: Set<string>,
  getDimensions: (node: CanvasNodeData) => { width: number; height: number },
  mode: SelectionLayoutMode,
): CanvasNodeData[] => {
  const selected = nodes
    .filter((node) => selectedIds.has(node.id))
    .sort((left, right) => left.y - right.y || left.x - right.x);
  if (selected.length < 2) return nodes;

  const dimensions = new Map(
    selected.map((node) => [node.id, getDimensions(node)]),
  );
  const minX = Math.min(...selected.map((node) => node.x));
  const minY = Math.min(...selected.map((node) => node.y));
  const positions = new Map<string, { x: number; y: number }>();

  if (mode === 'horizontal') {
    const rowHeight = Math.max(
      ...selected.map((node) => dimensions.get(node.id)?.height || NODE_HEIGHT),
    );
    let nextX = minX;
    selected.forEach((node) => {
      const size = dimensions.get(node.id) || {
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      };
      positions.set(node.id, {
        x: Math.round(nextX),
        y: Math.round(minY + (rowHeight - size.height) / 2),
      });
      nextX += size.width + SELECTION_LAYOUT_GAP;
    });
  } else if (mode === 'vertical') {
    const columnWidth = Math.max(
      ...selected.map((node) => dimensions.get(node.id)?.width || NODE_WIDTH),
    );
    let nextY = minY;
    selected.forEach((node) => {
      const size = dimensions.get(node.id) || {
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      };
      positions.set(node.id, {
        x: Math.round(minX + (columnWidth - size.width) / 2),
        y: Math.round(nextY),
      });
      nextY += size.height + SELECTION_LAYOUT_GAP;
    });
  } else {
    const columns = Math.max(1, Math.round(Math.sqrt(selected.length)));
    const cellWidth = Math.max(
      ...selected.map((node) => dimensions.get(node.id)?.width || NODE_WIDTH),
    );
    const rows: CanvasNodeData[][] = [];
    for (let index = 0; index < selected.length; index += columns) {
      rows.push(selected.slice(index, index + columns));
    }
    let nextY = minY;
    rows.forEach((row) => {
      const rowHeight = Math.max(
        ...row.map((node) => dimensions.get(node.id)?.height || NODE_HEIGHT),
      );
      let nextX = minX;
      row.forEach((node) => {
        const size = dimensions.get(node.id) || {
          width: NODE_WIDTH,
          height: NODE_HEIGHT,
        };
        positions.set(node.id, {
          x: Math.round(nextX),
          y: Math.round(nextY + (rowHeight - size.height) / 2),
        });
        nextX += cellWidth + SELECTION_LAYOUT_GAP;
      });
      nextY += rowHeight + SELECTION_LAYOUT_GAP;
    });
  }

  return nodes.map((node) => {
    const nextPosition = positions.get(node.id);
    return nextPosition
      ? { ...node, x: nextPosition.x, y: nextPosition.y }
      : node;
  });
};

const isImageFile = (file: File) =>
  file.type.startsWith('image/') ||
  /\.(avif|bmp|gif|heic|heif|jpe?g|png|svg|webp)$/i.test(file.name);

const isVideoFile = (file: File) =>
  file.type.startsWith('video/') ||
  /\.(avi|m4v|mkv|mov|mp4|mpeg|mpg|webm)$/i.test(file.name);

const isAudioFile = (file: File) => isWan3ReferenceAudioFile(file);

const isDocumentFile = (file: File) => isWan3ReferenceDocumentFile(file);

type CanvasImportMediaType = 'image' | 'video' | 'audio' | 'file';

const getFileMediaType = (file: File): CanvasImportMediaType | null => {
  if (isImageFile(file)) return 'image';
  if (isVideoFile(file)) return 'video';
  if (isAudioFile(file)) return 'audio';
  if (isDocumentFile(file)) return 'file';
  return null;
};

const isPublicHttpUrl = (value: string) => {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

const getCanvasAssetTypeLabel = (
  assetType?: CanvasNodeData['assetType'] | string,
) => {
  if (assetType === 'video') return '视频';
  if (assetType === 'audio' || assetType === 'music' || assetType === 'tts') {
    return '音频';
  }
  if (assetType === 'file') return '文档';
  if (assetType === 'link') return '网页';
  return '图片';
};

const getReferenceAliasPrefix = (
  mediaType?: 'image' | 'video' | 'audio' | 'file' | 'link',
) => {
  if (mediaType === 'video') return '视频';
  if (mediaType === 'audio') return '音频';
  if (mediaType === 'file') return '文档';
  if (mediaType === 'link') return '网页';
  return '图片';
};

/** 节点卡片当前可接收的素材类型。空素材节点可收图/视频/音频/文档。 */
const getNodeAcceptedMediaType = (
  node: CanvasNodeData,
): CanvasImportMediaType | 'all' | null => {
  if (node.kind === 'image') return 'image';
  if (node.kind === 'video') return 'video';
  if (node.kind === 'music' || node.kind === 'tts') return 'audio';
  if (node.kind === 'asset') {
    if (!node.resultUrl && !node.assetType) return 'all';
    if (node.assetType === 'link') return null;
    if (
      node.assetType === 'audio' ||
      node.assetType === 'file' ||
      node.assetType === 'video' ||
      node.assetType === 'image'
    ) {
      return node.assetType;
    }
    return node.resultAssetType === 'video' ? 'video' : 'image';
  }
  if (node.kind === 'text') {
    if (node.resultAssetType === 'video' || node.textGenerationMode === 'video')
      return 'video';
    return 'image';
  }
  return null;
};

const nodeAcceptsMediaType = (
  node: CanvasNodeData,
  mediaType: CanvasImportMediaType,
) => {
  const accepted = getNodeAcceptedMediaType(node);
  return accepted === 'all' || accepted === mediaType;
};

const nodeHasGeneratedMedia = (node: CanvasNodeData) =>
  ['image', 'video', 'text'].includes(node.kind) &&
  Boolean(
    node.resultUrl || node.resultUrls?.length || node.resultHistory?.length,
  );

const isEditingElement = (target: EventTarget | null) => {
  const element = target as HTMLElement | null;
  return (
    element?.tagName === 'INPUT' ||
    element?.tagName === 'TEXTAREA' ||
    element?.tagName === 'SELECT' ||
    Boolean(element?.isContentEditable)
  );
};

const readStoredCustomImageCommands = (): CanvasCustomImageCommand[] => {
  try {
    const raw = window.localStorage.getItem(CUSTOM_IMAGE_COMMANDS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (command): command is CanvasCustomImageCommand =>
          typeof command?.id === 'string' &&
          typeof command?.label === 'string' &&
          typeof command?.prompt === 'string' &&
          Boolean(command.label.trim()) &&
          Boolean(command.prompt.trim()),
      )
      .slice(0, 30);
  } catch {
    return [];
  }
};

const readLastGenerationSettings = (): CanvasLastGenerationSettings => {
  try {
    const raw = window.localStorage.getItem(
      LAST_GENERATION_SETTINGS_STORAGE_KEY,
    );
    if (!raw) return {};
    const parsed = JSON.parse(raw) as CanvasLastGenerationSettings;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const saveLastGenerationSettings = (
  current: CanvasLastGenerationSettings,
  kind: 'image' | 'video',
  updates: Partial<CanvasGenerationConfig>,
) => {
  const next = { ...current, [kind]: { ...(current[kind] || {}), ...updates } };
  try {
    window.localStorage.setItem(
      LAST_GENERATION_SETTINGS_STORAGE_KEY,
      JSON.stringify(next),
    );
  } catch {
    // 浏览器禁用存储时仅退化为当前会话记忆，不影响画布编辑。
  }
  return next;
};

const areCanvasSnapshotsEqual = (
  first: CanvasHistorySnapshot,
  second: CanvasHistorySnapshot,
) => JSON.stringify(first) === JSON.stringify(second);

const getAssetNameFromUrl = (url?: string) => {
  if (!url) return '';
  try {
    const pathname = new URL(url, window.location.origin).pathname;
    const name = pathname.split('/').filter(Boolean).pop();
    return name ? decodeURIComponent(name) : '';
  } catch {
    return url.split('/').filter(Boolean).pop() || '';
  }
};

const getNodeResultType = (node: CanvasNodeData): CanvasNodeResult['type'] => {
  if (node.resultAssetType) return node.resultAssetType;
  if (node.kind === 'asset') {
    if (node.assetType === 'video') return 'video';
    if (node.assetType === 'audio') return 'audio';
    if (node.assetType === 'file') return 'file';
    if (node.assetType === 'link') return 'link';
    return 'image';
  }
  if (node.kind === 'video') return 'video';
  if (node.kind === 'music' || node.kind === 'tts') return 'audio';
  return 'image';
};

const getNodeResultHistory = (node: CanvasNodeData): CanvasNodeResult[] => {
  if (node.resultHistory?.length) {
    const seen = new Set<string>();
    return node.resultHistory.filter((result) => {
      const key = `${result.type}:${result.url}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }
  const urls = node.resultUrls?.length
    ? node.resultUrls
    : node.resultUrl
      ? [node.resultUrl]
      : [];
  const type = getNodeResultType(node);
  return Array.from(new Set(urls)).map((url, index) => ({
    id: `legacy-${node.id}-${type}-${index}`,
    url,
    type,
    createdAt: '',
  }));
};

const getNodeResultUrls = (
  node: CanvasNodeData,
  type?: CanvasNodeResult['type'],
) =>
  Array.from(
    new Set(
      getNodeResultHistory(node)
        .filter((result) => !type || result.type === type)
        .map((result) => result.url),
    ),
  );

/** 下游参考只取当前主结果；多图节点由「设为主图」决定，默认第一张。 */
const getNodeMainResultUrl = (
  node: CanvasNodeData,
  type?: CanvasNodeResult['type'],
) => {
  const urls = getNodeResultUrls(node, type);
  if (urls.length === 0) return undefined;
  if (node.resultUrl && urls.includes(node.resultUrl)) return node.resultUrl;
  const ownUrls = getOwnMediaResultUrls(node);
  if (ownUrls[0] && urls.includes(ownUrls[0])) return ownUrls[0];
  return urls[0];
};

const getPersistedResultUrls = (
  historyResult: SaveHistoryResponse | null,
  fallbackUrls: string[],
  type: CanvasNodeResult['type'],
) => {
  const persistedUrls = historyResult?.data?.generated_assets
    ?.map((asset) => asset.url)
    .filter((url): url is string => Boolean(url));
  const urls =
    persistedUrls?.length === fallbackUrls.length
      ? persistedUrls
      : fallbackUrls;
  return Array.from(
    new Set(urls.map((url) => getStableCanvasMediaUrl(url, type))),
  );
};

const normalizeCanvasNode = (node: CanvasNodeData): CanvasNodeData => {
  const resultType = getNodeResultType(node);
  const rawResultUrls = node.resultUrls?.length
    ? node.resultUrls
    : node.resultUrl
      ? [node.resultUrl]
      : [];
  const resultUrls = rawResultUrls.map((url) =>
    getStableCanvasMediaUrl(url, resultType, node.assetName),
  );
  const resultUrl = node.resultUrl
    ? getStableCanvasMediaUrl(node.resultUrl, resultType, node.assetName)
    : resultUrls[0];
  const resultHistory = node.resultHistory?.length
    ? node.resultHistory.map((result) => ({
        ...result,
        url: getStableCanvasMediaUrl(result.url, result.type, node.assetName),
      }))
    : undefined;

  return {
    ...node,
    textGenerationMode:
      node.kind === 'text'
        ? node.textGenerationMode || 'image'
        : node.textGenerationMode,
    textImageConfig:
      node.kind === 'text'
        ? {
            ...(node.textImageConfig || {
              model: node.model || DEFAULT_IMAGE_MODEL,
              aspectRatio: node.aspectRatio || '16:9',
              resolution: node.resolution || '1K',
            }),
            count: Math.max(1, Number(node.textImageConfig?.count) || 1),
          }
        : node.textImageConfig,
    textVideoConfig:
      node.kind === 'text'
        ? {
            ...(node.textVideoConfig || {
              model: DEFAULT_VIDEO_MODEL,
              aspectRatio: '16:9',
              resolution:
                DEFAULT_MEDIA_GENERATION_CONFIG.features.workspace_video
                  .default_resolution,
              extensionCount: 0,
              videoGenerationMode: 'text_to_video',
            }),
            count: Math.max(1, Number(node.textVideoConfig?.count) || 1),
            videoGenerationMode:
              node.textVideoConfig?.videoGenerationMode || 'text_to_video',
          }
        : node.textVideoConfig,
    imageGenerationMode:
      node.kind === 'image'
        ? node.imageGenerationMode || 'reference_image'
        : node.imageGenerationMode,
    videoGenerationMode:
      node.kind === 'video'
        ? node.videoGenerationMode || 'first_frame'
        : node.videoGenerationMode,
    model:
      (node.kind === 'text' || node.kind === 'image') && node.model
        ? LEGACY_IMAGE_MODELS[node.model] || node.model
        : node.kind === 'video' && node.model
          ? LEGACY_VIDEO_MODELS[node.model] || node.model
          : node.kind === 'video_analysis'
            ? DEFAULT_VIDEO_ANALYSIS_MODEL
            : node.model,
    count: ['text', 'image', 'video', 'music', 'tts'].includes(node.kind)
      ? Math.max(1, Number(node.count) || 1)
      : node.count,
    voiceName: node.kind === 'tts' ? node.voiceName || 'Kore' : node.voiceName,
    speechRate:
      node.kind === 'tts' ? node.speechRate || 'normal' : node.speechRate,
    assetType:
      node.kind === 'asset' ? node.assetType || 'image' : node.assetType,
    resultUrl,
    resultUrls: resultUrls.length > 0 ? resultUrls : undefined,
    resultHistory,
    groupId: node.groupId?.trim() || undefined,
  };
};

const getAssetFileExtension = (mimeType: string, type: AssetType) => {
  const subtype = mimeType.split('/')[1]?.split(';')[0];
  if (subtype) {
    if (subtype === 'quicktime') return 'mov';
    if (subtype === 'mpeg') return type === AssetType.AUDIO ? 'mp3' : subtype;
    if (subtype.includes('wordprocessingml')) return 'docx';
    if (subtype.includes('spreadsheetml')) return 'xlsx';
    if (subtype.includes('presentationml')) return 'pptx';
    if (subtype === 'msword') return 'doc';
    return subtype;
  }
  if (type === AssetType.VIDEO) return 'mp4';
  if (type === AssetType.AUDIO) return 'mp3';
  if (type === AssetType.FILE) return 'pdf';
  return 'png';
};

const createFileBackedAsset = async (
  url: string,
  type: AssetType.IMAGE | AssetType.VIDEO | AssetType.AUDIO | AssetType.FILE,
  index: number,
  officialAssetUri?: string,
): Promise<UploadedAsset> => {
  const response = await fetch(url);
  if (!response.ok) {
    const kindLabel =
      type === AssetType.VIDEO
        ? '视频'
        : type === AssetType.AUDIO
          ? '音频'
          : type === AssetType.FILE
            ? '文档'
            : '图片';
    throw new Error(`无法读取参考${kindLabel}（HTTP ${response.status}）`);
  }
  const blob = await response.blob();
  const fallbackMimeType =
    type === AssetType.VIDEO
      ? 'video/mp4'
      : type === AssetType.AUDIO
        ? 'audio/mpeg'
        : type === AssetType.FILE
          ? 'application/octet-stream'
          : 'image/png';
  const mimeType = blob.type || fallbackMimeType;
  const extension = getAssetFileExtension(mimeType, type);
  const label =
    type === AssetType.VIDEO
      ? '参考视频'
      : type === AssetType.AUDIO
        ? '参考音频'
        : type === AssetType.FILE
          ? '参考文档'
          : '参考图片';
  const file = new File(
    [blob],
    `canvas-${type.toLowerCase()}-${index + 1}.${extension}`,
    { type: mimeType },
  );
  return {
    id: `canvas-${type.toLowerCase()}-${index + 1}-${Date.now()}`,
    type,
    url,
    name: `${label} ${index + 1}`,
    file,
    officialAssetUri,
  };
};

const canConnect = (source: CanvasNodeKind, target: CanvasNodeKind) => {
  if (source === 'output' || target === 'text' || target === 'asset')
    return false;
  if (source === 'text')
    return ['image', 'video', 'music', 'tts', 'output'].includes(target);
  if (source === 'asset')
    return ['image', 'video', 'video_analysis', 'music', 'output'].includes(
      target,
    );
  if (source === 'image')
    return ['image', 'video', 'music', 'output'].includes(target);
  if (source === 'video')
    return ['video', 'video_analysis', 'output'].includes(target);
  if (source === 'video_analysis')
    return ['image', 'video', 'music', 'tts', 'output'].includes(target);
  if (source === 'music' || source === 'tts')
    return ['video', 'output'].includes(target);
  return false;
};

const CONNECTION_DROP_MARQUEE_PADDING = 6;
/** 输入圆点很小，按屏幕像素给磁吸半径，避免必须对准圆心。 */
const CONNECTION_SNAP_RADIUS_PX = 72;

const getWheelDeltaPx = (
  event: WheelEvent,
  lineHeight = 16,
  pageHeight = 480,
) => {
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) {
    return { x: event.deltaX * lineHeight, y: event.deltaY * lineHeight };
  }
  if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    return { x: event.deltaX * pageHeight, y: event.deltaY * pageHeight };
  }
  return { x: event.deltaX, y: event.deltaY };
};

const findVerticalScrollableAncestor = (
  target: EventTarget | null,
  root: HTMLElement,
) => {
  if (!(target instanceof Element)) return null;
  let current: Element | null = target;
  while (current && current !== root) {
    const overflowY = window.getComputedStyle(current).overflowY;
    if (
      (overflowY === 'auto' || overflowY === 'scroll') &&
      current.scrollHeight > current.clientHeight + 1
    ) {
      return current;
    }
    current = current.parentElement;
  }
  return null;
};

type ConnectionSnapContext = {
  clientX: number;
  clientY: number;
  sourceId: string;
  /** 分组拖线时包含组内全部来源，命中规则按“任一可连”判断。 */
  sourceIds?: string[];
  canvasNodes: CanvasNodeData[];
  canvasRect: DOMRect | null;
  viewport: CanvasViewport;
  getDimensions: (node: CanvasNodeData) => { width: number; height: number };
  inputAnchors: Record<string, { x: number; y: number }>;
};

const getNodeInputAnchor = (
  node: CanvasNodeData,
  dimensions: { width: number; height: number },
  inputAnchors: Record<string, { x: number; y: number }>,
) =>
  inputAnchors[node.id] ?? {
    x: node.x,
    y: node.y + dimensions.height / 2,
  };

const getCubicBezierPoint = (
  t: number,
  p0: { x: number; y: number },
  p1: { x: number; y: number },
  p2: { x: number; y: number },
  p3: { x: number; y: number },
) => {
  const mt = 1 - t;
  const mt2 = mt * mt;
  const t2 = t * t;
  return {
    x:
      mt2 * mt * p0.x + 3 * mt2 * t * p1.x + 3 * mt * t2 * p2.x + t2 * t * p3.x,
    y:
      mt2 * mt * p0.y + 3 * mt2 * t * p1.y + 3 * mt * t2 * p2.y + t2 * t * p3.y,
  };
};

/**
 * 拖线落点：先命中节点本体，再按输入圆点磁吸。
 * 现有连线有加宽命中区，不能只用 elementFromPoint。
 */
const resolveConnectionDropTargetId = ({
  clientX,
  clientY,
  sourceId,
  sourceIds,
  canvasNodes,
  canvasRect,
  viewport,
  getDimensions,
  inputAnchors,
}: ConnectionSnapContext): string | null => {
  const sourceIdSet = new Set(sourceIds?.length ? sourceIds : [sourceId]);
  const sourceNodes = canvasNodes.filter((node) => sourceIdSet.has(node.id));
  if (sourceNodes.length === 0) return null;
  const canConnectToTarget = (target: CanvasNodeData) =>
    sourceNodes.some(
      (source) =>
        source.id !== target.id && canConnect(source.kind, target.kind),
    );

  for (const element of document.elementsFromPoint(clientX, clientY)) {
    if (!(element instanceof Element)) continue;
    const hoveredNodeId =
      element.closest<HTMLElement>('[data-canvas-node]')?.dataset.canvasNode;
    if (!hoveredNodeId) continue;
    const targetNode = canvasNodes.find((node) => node.id === hoveredNodeId);
    if (!targetNode) continue;
    if (canConnectToTarget(targetNode)) return hoveredNodeId;
    // 组内其他来源节点不算“无法连接”，继续找真正的落点。
    if (sourceIdSet.has(hoveredNodeId)) continue;
    return null;
  }

  if (!canvasRect || viewport.zoom <= 0) return null;

  const pointerCanvasX =
    (clientX - canvasRect.left - viewport.x) / viewport.zoom;
  const pointerCanvasY =
    (clientY - canvasRect.top - viewport.y) / viewport.zoom;
  const snapRadiusCanvas = CONNECTION_SNAP_RADIUS_PX / viewport.zoom;
  let nearestId: string | null = null;
  let nearestDistance = snapRadiusCanvas;

  canvasNodes.forEach((node) => {
    if (!canConnectToTarget(node)) return;
    const dimensions = getDimensions(node);
    const anchor = getNodeInputAnchor(node, dimensions, inputAnchors);
    const distance = Math.hypot(
      pointerCanvasX - anchor.x,
      pointerCanvasY - anchor.y,
    );
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestId = node.id;
    }
  });

  return nearestId;
};

/** 拖线时指针下的节点（含不兼容目标），用来提示无法连接。 */
const resolveConnectionHoverNodeId = (
  clientX: number,
  clientY: number,
  sourceId: string,
  sourceIds?: string[],
): string | null => {
  const sourceIdSet = new Set(sourceIds?.length ? sourceIds : [sourceId]);
  for (const element of document.elementsFromPoint(clientX, clientY)) {
    if (!(element instanceof Element)) continue;
    const hoveredNodeId =
      element.closest<HTMLElement>('[data-canvas-node]')?.dataset.canvasNode;
    if (!hoveredNodeId || sourceIdSet.has(hoveredNodeId)) continue;
    return hoveredNodeId;
  }
  return null;
};

/**
 * 收集选中节点（或连线两端）的上游祖先、下游后代，以及这些节点之间的连线。
 * 脉冲只画在这条任务链路上，避免复杂画布里所有连线同时闪动。
 */
const collectLineageEdgeIds = (
  edges: CanvasEdgeData[],
  seedNodeIds: Iterable<string>,
): Set<string> => {
  const seeds = Array.from(new Set(Array.from(seedNodeIds).filter(Boolean)));
  if (seeds.length === 0 || edges.length === 0) return new Set();

  const outgoing: Record<string, string[]> = {};
  const incoming: Record<string, string[]> = {};
  const addLink = (
    store: Record<string, string[]>,
    from: string,
    to: string,
  ) => {
    const list = store[from];
    if (list) list.push(to);
    else store[from] = [to];
  };
  edges.forEach((edge) => {
    addLink(outgoing, edge.source, edge.target);
    addLink(incoming, edge.target, edge.source);
  });

  const relatedNodeIds = new Set(seeds);
  const walk = (adjacency: Record<string, string[]>) => {
    const visited = new Set(seeds);
    const stack = [...seeds];
    while (stack.length > 0) {
      const nodeId = stack.pop()!;
      const nextIds = adjacency[nodeId];
      if (!nextIds) continue;
      nextIds.forEach((nextId) => {
        if (visited.has(nextId)) return;
        visited.add(nextId);
        relatedNodeIds.add(nextId);
        stack.push(nextId);
      });
    }
  };
  walk(incoming);
  walk(outgoing);

  return new Set(
    edges
      .filter(
        (edge) =>
          relatedNodeIds.has(edge.source) && relatedNodeIds.has(edge.target),
      )
      .map((edge) => edge.id),
  );
};

const getDefaultDraft = (initialTitle = '未命名画布'): CanvasDraft => ({
  version: 1,
  title: initialTitle,
  nodes: SAMPLE_NODES,
  edges: SAMPLE_EDGES,
  viewport: { x: 40, y: 80, zoom: 0.9 },
  updatedAt: new Date().toISOString(),
});

const readStoredDraft = (
  storageKey: string,
  initialTitle?: string,
): CanvasDraft | null => {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CanvasDraft;
    if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
      return null;
    }
    return {
      ...getDefaultDraft(initialTitle),
      ...parsed,
      nodes: parsed.nodes.map(normalizeCanvasNode),
      viewport: parsed.viewport || { x: 40, y: 80, zoom: 0.9 },
    };
  } catch {
    return null;
  }
};

const CanvasCreationPage: React.FC<CanvasCreationPageProps> = ({
  canvasId = 'default',
  initialTitle,
  onBack,
  mediaConfig = DEFAULT_MEDIA_GENERATION_CONFIG,
}) => {
  const normalizedCanvasId = canvasId.trim() || 'default';
  const storageScope = useMemo(() => getCanvasDraftStorageScope(), []);
  const storageKey = `${STORAGE_KEY_PREFIX}${storageScope}:${encodeURIComponent(normalizedCanvasId)}`;
  const storedDraftRef = useRef<CanvasDraft | null>(null);
  const initialDraftRef = useRef<CanvasDraft | null>(null);
  if (!initialDraftRef.current) {
    storedDraftRef.current = readStoredDraft(storageKey, initialTitle);
    initialDraftRef.current =
      storedDraftRef.current || getDefaultDraft(initialTitle);
  }
  const initialDraft = initialDraftRef.current as CanvasDraft;

  const [title, setTitle] = useState(initialDraft.title);
  const [titleDraft, setTitleDraft] = useState(initialDraft.title);
  const [isTitleEditing, setIsTitleEditing] = useState(false);
  const [nodes, setNodes] = useState<CanvasNodeData[]>(initialDraft.nodes);
  const [edges, setEdges] = useState<CanvasEdgeData[]>(initialDraft.edges);
  const [viewport, setViewport] = useState<CanvasViewport>(
    initialDraft.viewport,
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    initialDraft.nodes[0]?.id || null,
  );
  const [selectedNodeIds, setSelectedNodeIds] = useState<Set<string>>(
    () => new Set(initialDraft.nodes[0]?.id ? [initialDraft.nodes[0].id] : []),
  );
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [selectionBox, setSelectionBox] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);
  const [pendingSourceId, setPendingSourceId] = useState<string | null>(null);
  const [pendingSourceIds, setPendingSourceIds] = useState<string[]>([]);
  const [connectionOrigin, setConnectionOrigin] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [connectionPointer, setConnectionPointer] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [connectionHoverTargetId, setConnectionHoverTargetId] = useState<
    string | null
  >(null);
  const [connectionRejectTargetId, setConnectionRejectTargetId] = useState<
    string | null
  >(null);
  const [connectionCursor, setConnectionCursor] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(
    initialDraft.updatedAt ? new Date(initialDraft.updatedAt) : null,
  );
  const [serverSyncReady, setServerSyncReady] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [hasSaveConflict, setHasSaveConflict] = useState(false);
  const [isSaveConflictNoticeOpen, setIsSaveConflictNoticeOpen] =
    useState(false);
  const [isForceSaving, setIsForceSaving] = useState(false);
  const [generatingNodeIds, setGeneratingNodeIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [nodeErrors, setNodeErrors] = useState<Record<string, string>>({});
  const [nodeProgress, setNodeProgress] = useState<Record<string, string>>({});
  const [videoTaskCancelStates, setVideoTaskCancelStates] = useState<
    Record<string, VideoTaskCancelState>
  >({});
  const [localAssetNodeId, setLocalAssetNodeId] = useState<string | null>(null);
  const [cloudAssetNodeId, setCloudAssetNodeId] = useState<string | null>(null);
  const [isImportingAsset, setIsImportingAsset] = useState(false);
  const [webpageLinkDraft, setWebpageLinkDraft] = useState('');
  const [isFileDragActive, setIsFileDragActive] = useState(false);
  const [isDroppingImages, setIsDroppingImages] = useState(false);
  const [droppedImageCount, setDroppedImageCount] = useState(0);
  const [fileDropTargetNodeId, setFileDropTargetNodeId] = useState<
    string | null
  >(null);
  const [fileDropTargetRejected, setFileDropTargetRejected] = useState(false);
  const [replaceMediaConfirm, setReplaceMediaConfirm] = useState<{
    nodeId: string;
    asset: UploadedAsset;
    mediaType: 'image' | 'video';
  } | null>(null);
  const [previewMedia, setPreviewMedia] = useState<{
    url: string;
    name: string;
    type: 'image' | 'video';
    transparent?: boolean;
  } | null>(null);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const [altDuplicateModifier, setAltDuplicateModifier] = useState(false);
  const [toolMode, setToolMode] = useState<CanvasToolMode>('select');
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatAttachRequest, setChatAttachRequest] =
    useState<CanvasChatAttachRequest | null>(null);
  const [selectionGroupMenuOpen, setSelectionGroupMenuOpen] = useState(false);
  const [selectionLayoutMenuOpen, setSelectionLayoutMenuOpen] = useState(false);
  const [selectionToolbarLayout, setSelectionToolbarLayout] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const [quickSettingsLayout, setQuickSettingsLayout] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const quickSettingsRef = useRef<HTMLElement | null>(null);
  const [toolbarOffset, setToolbarOffset] = useState({ x: 0, y: 0 });
  const [historyPageOpen, setHistoryPageOpen] = useState(false);
  const [todayUsage, setTodayUsage] = useState<{
    dailyCost: number;
    dailyLimit: number | null;
    monthlyCost: number;
    monthlyLimit: number | null;
    weeklyCost: number;
    weeklyLimit: number | null;
  } | null>(null);
  const [todayUsageLoading, setTodayUsageLoading] = useState(false);
  const [promptEditorExpanded, setPromptEditorExpanded] = useState(false);
  const [minimapOpen, setMinimapOpen] = useState(false);
  const [minimapDragging, setMinimapDragging] = useState(false);
  const [exploredWorld, setExploredWorld] = useState<{
    maxX: number;
    maxY: number;
    minX: number;
    minY: number;
  } | null>(null);
  const [emptyViewportHintDismissed, setEmptyViewportHintDismissed] =
    useState(false);
  const [canvasSize, setCanvasSize] = useState({ height: 600, width: 800 });
  const [tidyConfirm, setTidyConfirm] = useState<{
    previousNodes: CanvasNodeData[];
  } | null>(null);
  const [imageAiTool, setImageAiTool] = useState<{
    mode: Exclude<ImageNodeAiToolMode, 'idle'>;
    nodeId: string;
    gridSize?: GridSplitSize;
  } | null>(null);
  const imageAiToolRef = useRef(imageAiTool);
  imageAiToolRef.current = imageAiTool;
  const [nodeMenu, setNodeMenu] = useState<NodeMenuState | null>(null);
  const [contextMenu, setContextMenu] = useState<CanvasContextMenuState | null>(
    null,
  );
  const [quickCommandsOpen, setQuickCommandsOpen] = useState(false);
  const [customImageCommands, setCustomImageCommands] = useState<
    CanvasCustomImageCommand[]
  >(readStoredCustomImageCommands);
  const [favoriteModels, setFavoriteModels] = useState<string[]>(
    readStoredFavoriteModels,
  );
  const lastGenerationSettingsRef = useRef<CanvasLastGenerationSettings>(
    readLastGenerationSettings(),
  );
  const [pendingQuickGeneration, setPendingQuickGeneration] = useState<{
    nodeId: string;
    commandLabel: string;
  } | null>(null);
  const [pendingChatGenerations, setPendingChatGenerations] = useState<
    {
      kind: CanvasChatMediaType;
      nodeId: string;
    }[]
  >([]);
  const [pendingGridHdNodeIds, setPendingGridHdNodeIds] = useState<string[]>(
    [],
  );
  const [historyRevision, setHistoryRevision] = useState(0);
  const [connectionAnchors, setConnectionAnchors] = useState<{
    inputs: Record<string, { x: number; y: number }>;
    outputs: Record<string, { x: number; y: number }>;
  }>({ inputs: {}, outputs: {} });
  const [theme, setTheme] = useState<CanvasTheme>(() => {
    try {
      return window.localStorage.getItem(THEME_STORAGE_KEY) === 'dark'
        ? 'dark'
        : 'light';
    } catch {
      return 'light';
    }
  });
  const [expandedMediaNodeIds, setExpandedMediaNodeIds] = useState<Set<string>>(
    () => new Set(),
  );

  const getCanvasNodeDimensions = useCallback(
    (node: CanvasNodeData) => {
      const customWidth =
        typeof node.width === 'number' && node.width > 0
          ? node.width
          : undefined;
      const customHeight =
        typeof node.height === 'number' && node.height > 0
          ? node.height
          : undefined;
      const mediaSourceNode =
        node.kind === 'output'
          ? edges
              .filter((edge) => edge.target === node.id)
              .map((edge) =>
                nodes.find((candidate) => candidate.id === edge.source),
              )
              .find((candidate): candidate is CanvasNodeData =>
                Boolean(candidate?.resultUrl || candidate?.resultUrls?.length),
              )
          : node;
      if (!mediaSourceNode) return { width: NODE_WIDTH, height: NODE_HEIGHT };

      const mediaUrl =
        mediaSourceNode.resultUrls?.[0] || mediaSourceNode.resultUrl;
      const mediaType =
        mediaSourceNode.kind === 'text'
          ? mediaSourceNode.resultAssetType ||
            (mediaSourceNode.textGenerationMode === 'video' ? 'video' : 'image')
          : mediaSourceNode.kind === 'asset'
            ? mediaSourceNode.assetType || 'image'
            : mediaSourceNode.kind;

      if (
        (mediaUrl && (mediaType === 'image' || mediaType === 'video')) ||
        (!mediaUrl && (node.kind === 'image' || node.kind === 'video'))
      ) {
        const base = getNodeDimensions(node);
        const ownUrls = getOwnMediaResultUrls(node);
        if (expandedMediaNodeIds.has(node.id) && ownUrls.length > 1) {
          return getExpandedMediaNodeDimensions(base, ownUrls.length);
        }
        return base;
      }

      return {
        width: customWidth || NODE_WIDTH,
        height:
          customHeight ||
          (node.kind === 'text' && !mediaUrl
            ? TEXT_PROMPT_NODE_HEIGHT
            : NODE_HEIGHT),
      };
    },
    [edges, expandedMediaNodeIds, nodes],
  );

  const findNodeAtClientPoint = useCallback(
    (clientX: number, clientY: number) => {
      const canvas = canvasRef.current;
      if (!canvas || viewport.zoom <= 0) return null;
      const rect = canvas.getBoundingClientRect();
      const worldX = (clientX - rect.left - viewport.x) / viewport.zoom;
      const worldY = (clientY - rect.top - viewport.y) / viewport.zoom;
      for (let index = nodes.length - 1; index >= 0; index -= 1) {
        const node = nodes[index];
        if (!node) continue;
        const size = getCanvasNodeDimensions(node);
        if (
          worldX >= node.x &&
          worldX <= node.x + size.width &&
          worldY >= node.y &&
          worldY <= node.y + size.height
        ) {
          return node;
        }
      }
      return null;
    },
    [getCanvasNodeDimensions, nodes, viewport],
  );

  const imageFeatureConfig = useMemo(
    () => getMediaFeatureConfig(mediaConfig, 'workspace_image'),
    [mediaConfig],
  );
  const mediaModelCatalog = useMemo(
    () => getMediaModelCatalog(mediaConfig),
    [mediaConfig],
  );
  const cnyToUsdRate = useMemo(
    () => getCnyToUsdRate(mediaConfig),
    [mediaConfig],
  );
  const refreshTodayUsage = useCallback(async () => {
    setTodayUsageLoading(true);
    try {
      const result = await authService.getMyUsage();
      const toCost = (value: unknown) => {
        const cost = Number(value);
        return Number.isFinite(cost) && cost >= 0 ? cost : 0;
      };
      const toLimit = (value: unknown) => {
        if (value === null || value === undefined || value === '') return null;
        const limit = Number(value);
        return Number.isFinite(limit) && limit > 0 ? limit : null;
      };
      setTodayUsage({
        dailyCost: toCost(result?.usage?.daily_cost),
        dailyLimit: toLimit(result?.limits?.daily),
        monthlyCost: toCost(result?.usage?.monthly_cost),
        monthlyLimit: toLimit(result?.limits?.monthly),
        weeklyCost: toCost(result?.usage?.weekly_cost),
        weeklyLimit: toLimit(result?.limits?.weekly),
      });
    } catch {
      setTodayUsage(null);
    } finally {
      setTodayUsageLoading(false);
    }
  }, []);
  const todayUsageDisplay = useMemo(() => {
    if (todayUsage === null) return '暂无法获取';
    return `¥${(todayUsage.dailyCost / cnyToUsdRate).toFixed(2)}`;
  }, [cnyToUsdRate, todayUsage]);
  const todayUsageQuotaProgress = useMemo(() => {
    if (todayUsage === null) return [];
    return [
      {
        label: '今日',
        limit: todayUsage.dailyLimit,
        used: todayUsage.dailyCost,
      },
      {
        label: '本周',
        limit: todayUsage.weeklyLimit,
        used: todayUsage.weeklyCost,
      },
      {
        label: '本月',
        limit: todayUsage.monthlyLimit,
        used: todayUsage.monthlyCost,
      },
    ].map((item) => ({
      ...item,
      percent: item.limit ? Math.min((item.used / item.limit) * 100, 100) : 0,
    }));
  }, [todayUsage]);

  useEffect(() => {
    void refreshTodayUsage();
  }, [refreshTodayUsage]);

  const availableImageModels = useMemo(
    () => getEnabledModels(mediaConfig, 'workspace_image'),
    [mediaConfig],
  );
  const defaultImageModel = availableImageModels.includes(
    imageFeatureConfig.default_model,
  )
    ? imageFeatureConfig.default_model
    : availableImageModels[0] || DEFAULT_IMAGE_MODEL;
  const videoFeatureConfig = useMemo(
    () => getMediaFeatureConfig(mediaConfig, 'workspace_video'),
    [mediaConfig],
  );
  const availableVideoModels = useMemo(() => {
    const enabledModels = getEnabledModels(mediaConfig, 'workspace_video');
    const imageDrivenModels = enabledModels.filter((model) => {
      const capabilities: string[] =
        mediaModelCatalog[model]?.capabilities || [];
      return (
        capabilities.includes('image_to_video') ||
        capabilities.includes('reference_to_video')
      );
    });
    return imageDrivenModels.length > 0 ? imageDrivenModels : enabledModels;
  }, [mediaConfig, mediaModelCatalog]);
  const availableTextVideoModels = useMemo(() => {
    const enabledModels = getEnabledModels(mediaConfig, 'workspace_video');
    const textDrivenModels = enabledModels.filter((model) => {
      const capabilities: string[] =
        mediaModelCatalog[model]?.capabilities || [];
      return capabilities.includes('text_to_video');
    });
    return textDrivenModels.length > 0 ? textDrivenModels : enabledModels;
  }, [mediaConfig, mediaModelCatalog]);
  const maxVideoExtensionCount = Math.max(
    0,
    Number(videoFeatureConfig.max_extension_count || 20),
  );
  const maxImageBatchCount = Math.max(
    1,
    Number(imageFeatureConfig.max_batch_count) || 10,
  );
  const maxVideoBatchCount = Math.max(
    1,
    Number(videoFeatureConfig.max_batch_count) || 4,
  );
  const defaultChatVideoModel = availableTextVideoModels.includes(
    videoFeatureConfig.default_model,
  )
    ? videoFeatureConfig.default_model
    : availableTextVideoModels[0];
  const availableChatGenerationModels = useMemo<CanvasChatGenerationModel[]>(
    () => [
      ...availableImageModels.map((id) => ({
        id,
        label: mediaModelCatalog[id]?.label || id,
        aliases: [
          id,
          mediaModelCatalog[id]?.label,
          mediaModelCatalog[id]?.provider_model,
        ].filter(
          (value): value is string =>
            typeof value === 'string' && Boolean(value.trim()),
        ),
        isDefault: id === defaultImageModel,
        type: 'image' as const,
        resolutions: mediaModelCatalog[id]?.supported_resolutions || [
          imageFeatureConfig.default_resolution || '1K',
        ],
        aspectRatios:
          mediaModelCatalog[id]?.supported_aspect_ratios || IMAGE_ASPECT_RATIOS,
        maxCount: maxImageBatchCount,
      })),
      ...availableTextVideoModels.map((id) => ({
        id,
        label: mediaModelCatalog[id]?.label || id,
        aliases: [
          id,
          mediaModelCatalog[id]?.label,
          mediaModelCatalog[id]?.provider_model,
        ].filter(
          (value): value is string =>
            typeof value === 'string' && Boolean(value.trim()),
        ),
        isDefault: id === defaultChatVideoModel,
        type: 'video' as const,
        resolutions: mediaModelCatalog[id]?.supported_resolutions || [
          videoFeatureConfig.default_resolution || '720p',
        ],
        aspectRatios:
          mediaModelCatalog[id]?.supported_aspect_ratios || VIDEO_ASPECT_RATIOS,
        durationRangeSeconds: mediaModelCatalog[id]?.duration_range_seconds || [
          2, 15,
        ],
        maxCount: maxVideoBatchCount,
      })),
    ],
    [
      availableImageModels,
      availableTextVideoModels,
      defaultChatVideoModel,
      imageFeatureConfig.default_resolution,
      defaultImageModel,
      maxImageBatchCount,
      maxVideoBatchCount,
      mediaModelCatalog,
      videoFeatureConfig.default_resolution,
    ],
  );
  const defaultVideoModel = availableVideoModels.includes(
    videoFeatureConfig.default_model,
  )
    ? videoFeatureConfig.default_model
    : availableVideoModels[0] || DEFAULT_VIDEO_MODEL;
  const defaultTextVideoModel = availableTextVideoModels.includes(
    videoFeatureConfig.default_model,
  )
    ? videoFeatureConfig.default_model
    : availableTextVideoModels[0] || DEFAULT_VIDEO_MODEL;
  const musicFeatureConfig = useMemo(
    () => getMediaFeatureConfig(mediaConfig, 'workspace_music'),
    [mediaConfig],
  );
  const availableMusicModels = useMemo(
    () => getEnabledModels(mediaConfig, 'workspace_music'),
    [mediaConfig],
  );
  const defaultMusicModel = availableMusicModels.includes(
    musicFeatureConfig.default_model,
  )
    ? musicFeatureConfig.default_model
    : availableMusicModels[0] || DEFAULT_MUSIC_MODEL;
  const ttsFeatureConfig = useMemo(
    () => getMediaFeatureConfig(mediaConfig, 'workspace_tts'),
    [mediaConfig],
  );
  const availableTTSModels = useMemo(
    () => getEnabledModels(mediaConfig, 'workspace_tts'),
    [mediaConfig],
  );
  const availableChatModels = useMemo(
    () => getEnabledModels(mediaConfig, 'workspace_chat'),
    [mediaConfig],
  );
  const defaultTTSModel = availableTTSModels.includes(
    ttsFeatureConfig.default_model,
  )
    ? ttsFeatureConfig.default_model
    : availableTTSModels[0] || DEFAULT_TTS_MODEL;
  const defaultTTSVoice = String(ttsFeatureConfig.default_voice || 'Kore');

  const rememberGenerationSettings = useCallback(
    (kind: 'image' | 'video', settings: Partial<CanvasGenerationConfig>) => {
      lastGenerationSettingsRef.current = saveLastGenerationSettings(
        lastGenerationSettingsRef.current,
        kind,
        settings,
      );
    },
    [],
  );

  const openImagePreview = useCallback(
    (url: string, name: string, options?: { transparent?: boolean }) => {
      setPreviewMedia({
        url: getCanvasMediaPreviewUrl(url, 'image', name),
        name,
        type: 'image',
        transparent: options?.transparent,
      });
    },
    [],
  );

  const openVideoPreview = useCallback((url: string, name: string) => {
    setPreviewMedia({
      url: getCanvasMediaPreviewUrl(url, 'video', name),
      name,
      type: 'video',
    });
  }, []);

  const downloadImage = useCallback(async (url: string, name: string) => {
    try {
      const filename = await downloadCanvasImage(url, name);
      setToast(`已下载 ${filename}`);
    } catch (error) {
      console.error('[Canvas] 图片下载失败:', error);
      setToast('图片下载失败，请稍后重试');
    }
  }, []);

  const downloadVideo = useCallback(async (url: string, name: string) => {
    try {
      const filename = await downloadCanvasMedia(
        url,
        getCanvasVideoDownloadName(name),
        'video',
      );
      setToast(`已下载 ${filename}`);
    } catch (error) {
      console.error('[Canvas] 视频下载失败:', error);
      setToast('视频下载失败，请稍后重试');
    }
  }, []);

  const downloadSelectedMedia = useCallback(async () => {
    const seenMedia = new Set<string>();
    const selectedMedia = nodes
      .filter((node) => selectedNodeIds.has(node.id))
      .flatMap((node) =>
        getNodeResultHistory(node).map((result, index) => ({
          ...result,
          name: `${node.title}-${index + 1}`,
        })),
      )
      .filter((result) => {
        const key = `${result.type}:${result.url}`;
        if (seenMedia.has(key)) return false;
        seenMedia.add(key);
        return true;
      });
    if (selectedMedia.length === 0) {
      setToast('所选节点中没有可下载的生成内容');
      return;
    }

    let downloadedCount = 0;
    for (const media of selectedMedia) {
      try {
        if (media.type === 'image')
          await downloadCanvasImage(media.url, media.name);
        else await downloadCanvasMedia(media.url, media.name, media.type);
        downloadedCount += 1;
      } catch (error) {
        console.error('[Canvas] 批量下载单个媒体失败:', error);
      }
    }
    setToast(
      downloadedCount === selectedMedia.length
        ? `已下载所选的 ${downloadedCount} 个文件`
        : `已下载 ${downloadedCount}/${selectedMedia.length} 个文件`,
    );
  }, [nodes, selectedNodeIds]);

  const canvasRef = useRef<HTMLDivElement>(null);
  const selectedNodeIdRef = useRef<string | null>(selectedNodeId);
  const selectedNodeIdsRef = useRef(selectedNodeIds);
  selectedNodeIdRef.current = selectedNodeId;
  selectedNodeIdsRef.current = selectedNodeIds;
  const lastCanvasPointerRef = useRef<{
    clientX: number;
    clientY: number;
  } | null>(null);
  const minimapDragRef = useRef<{
    minX: number;
    minY: number;
    moved: boolean;
    offsetX: number;
    offsetY: number;
    pointerId: number;
    scale: number;
    startMiniX: number;
    startMiniY: number;
    startViewLeft: number;
    startViewTop: number;
  } | null>(null);
  const nodeMenuRef = useRef<HTMLDivElement>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const quickCommandsRef = useRef<HTMLDivElement>(null);
  const shortcutsButtonRef = useRef<HTMLButtonElement>(null);
  const shortcutsCloseButtonRef = useRef<HTMLButtonElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const toolbarDragRef = useRef<{
    pointerId: number;
    startClientX: number;
    startClientY: number;
    startOffsetX: number;
    startOffsetY: number;
    minDeltaX: number;
    maxDeltaX: number;
    minDeltaY: number;
    maxDeltaY: number;
  } | null>(null);
  const temporaryHandRef = useRef(false);
  const assetInputRef = useRef<HTMLInputElement>(null);
  const fileDragDepthRef = useRef(0);
  const isImportingCanvasImagesRef = useRef(false);
  const historyCommitTimerRef = useRef<number | null>(null);
  const quickCommandsCloseTimerRef = useRef<number | null>(null);
  const isApplyingHistoryRef = useRef(false);
  const historySnapshotRef = useRef<CanvasHistorySnapshot>({
    nodes: initialDraft.nodes,
    edges: initialDraft.edges,
  });
  const undoStackRef = useRef<CanvasHistorySnapshot[]>([]);
  const redoStackRef = useRef<CanvasHistorySnapshot[]>([]);
  const serverRevisionRef = useRef(1);
  const serverSyncReadyRef = useRef(false);
  const serverSaveInFlightRef = useRef(false);
  const forceSaveInFlightRef = useRef(false);
  const hasSaveConflictRef = useRef(false);
  const isSaveConflictNoticeOpenRef = useRef(false);
  const queuedServerDraftRef = useRef<CanvasDraft | null>(null);
  const lastServerDraftRef = useRef('');
  const latestCanvasStateRef = useRef({ edges, nodes, title, viewport });
  const dragRef = useRef<{
    nodeIds: string[];
    startClientX: number;
    startClientY: number;
    startPositions: Record<string, { x: number; y: number }>;
  } | null>(null);
  const selectionRef = useRef<{
    startLocalX: number;
    startLocalY: number;
    baseNodeIds: Set<string>;
  } | null>(null);
  const suppressMarqueeReleaseRef = useRef(false);
  const mediaResizeRef = useRef<{
    nodeId: string;
    corner: MediaResizeCorner;
    startClientX: number;
    startClientY: number;
    startNodeX: number;
    startNodeY: number;
    startWidth: number;
    startHeight: number;
    startScale: number;
  } | null>(null);
  const panRef = useRef<{
    startClientX: number;
    startClientY: number;
    startViewportX: number;
    startViewportY: number;
  } | null>(null);
  const connectionDragRef = useRef<{
    sourceId: string;
    sourceIds: string[];
    origin?: { x: number; y: number };
    startClientX: number;
    startClientY: number;
    moved: boolean;
  } | null>(null);
  const altDuplicateDragRef = useRef<{
    sourceIds: string[];
    startClientX: number;
    startClientY: number;
    startPositions: Record<string, { x: number; y: number }>;
    committed: boolean;
  } | null>(null);

  const measureConnectionAnchors = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || viewport.zoom <= 0) return;

    const canvasRect = canvas.getBoundingClientRect();
    const inputs: Record<string, { x: number; y: number }> = {};
    const outputs: Record<string, { x: number; y: number }> = {};

    canvas
      .querySelectorAll<HTMLElement>(
        '[data-canvas-input-node-id], [data-canvas-output-node-id]',
      )
      .forEach((handle) => {
        const handleRect = handle.getBoundingClientRect();
        const anchor = {
          x:
            (handleRect.left +
              handleRect.width / 2 -
              canvasRect.left -
              viewport.x) /
            viewport.zoom,
          y:
            (handleRect.top +
              handleRect.height / 2 -
              canvasRect.top -
              viewport.y) /
            viewport.zoom,
        };
        const inputNodeId = handle.dataset.canvasInputNodeId;
        const outputNodeId = handle.dataset.canvasOutputNodeId;
        if (inputNodeId) inputs[inputNodeId] = anchor;
        if (outputNodeId) outputs[outputNodeId] = anchor;
      });

    setConnectionAnchors((current) =>
      areAnchorMapsEqual(current.inputs, inputs) &&
      areAnchorMapsEqual(current.outputs, outputs)
        ? current
        : { inputs, outputs },
    );
  }, [viewport.x, viewport.y, viewport.zoom]);

  useLayoutEffect(() => {
    measureConnectionAnchors();
    const canvas = canvasRef.current;
    if (!canvas) return undefined;

    const resizeObserver =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(measureConnectionAnchors);
    canvas
      .querySelectorAll<HTMLElement>('[data-canvas-node]')
      .forEach((nodeElement) => resizeObserver?.observe(nodeElement));
    window.addEventListener('resize', measureConnectionAnchors);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener('resize', measureConnectionAnchors);
    };
  }, [measureConnectionAnchors, nodes, selectedNodeId, expandedMediaNodeIds]);

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const updateSize = () => {
      const next = { height: canvas.clientHeight, width: canvas.clientWidth };
      setCanvasSize((current) =>
        current.width === next.width && current.height === next.height
          ? current
          : next,
      );
    };
    updateSize();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateSize);
      return () => window.removeEventListener('resize', updateSize);
    }
    const observer = new ResizeObserver(updateSize);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) || null,
    [nodes, selectedNodeId],
  );

  useEffect(() => {
    if (
      selectedNode?.kind === 'asset' &&
      selectedNode.assetType === 'link' &&
      selectedNode.resultUrl
    ) {
      setWebpageLinkDraft(selectedNode.resultUrl);
      return;
    }
    if (!selectedNode || selectedNode.kind !== 'asset') {
      setWebpageLinkDraft('');
    }
  }, [
    selectedNode?.assetType,
    selectedNode?.id,
    selectedNode?.kind,
    selectedNode?.resultUrl,
  ]);

  const relatedConnectionEdgeIds = useMemo(() => {
    const seedNodeIds: Set<string> = new Set();
    if (selectedNodeIds.size > 0) {
      selectedNodeIds.forEach((nodeId) => seedNodeIds.add(nodeId));
    } else if (selectedEdgeId) {
      const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId);
      if (selectedEdge) {
        seedNodeIds.add(selectedEdge.source);
        seedNodeIds.add(selectedEdge.target);
      }
    }
    return collectLineageEdgeIds(edges, seedNodeIds);
  }, [edges, selectedEdgeId, selectedNodeIds]);

  const selectedEdgeCutLayout = useMemo(() => {
    if (!selectedEdgeId) return null;
    const edge = edges.find((item) => item.id === selectedEdgeId);
    if (!edge) return null;
    const source = nodes.find((node) => node.id === edge.source);
    const target = nodes.find((node) => node.id === edge.target);
    if (!source || !target) return null;
    const sourceDimensions = getCanvasNodeDimensions(source);
    const targetDimensions = getCanvasNodeDimensions(target);
    const sourceAnchor = connectionAnchors.outputs[source.id];
    const targetAnchor = connectionAnchors.inputs[target.id];
    const startX = sourceAnchor?.x ?? source.x + sourceDimensions.width;
    const startY = sourceAnchor?.y ?? source.y + sourceDimensions.height / 2;
    const endX = targetAnchor?.x ?? target.x;
    const endY = targetAnchor?.y ?? target.y + targetDimensions.height / 2;
    const controlOffset = Math.max(90, Math.abs(endX - startX) * 0.42);
    const mid = getCubicBezierPoint(
      0.5,
      { x: startX, y: startY },
      { x: startX + controlOffset, y: startY },
      { x: endX - controlOffset, y: endY },
      { x: endX, y: endY },
    );
    return {
      left: mid.x * viewport.zoom + viewport.x,
      top: mid.y * viewport.zoom + viewport.y,
    };
  }, [
    connectionAnchors,
    edges,
    getCanvasNodeDimensions,
    nodes,
    selectedEdgeId,
    viewport,
  ]);

  const selectedPersistedGroupId = useMemo(
    () => findExactSelectedGroupId(nodes, selectedNodeIds),
    [nodes, selectedNodeIds],
  );

  const persistentNodeGroups = useMemo(
    () => listPersistentNodeGroups(nodes, getCanvasNodeDimensions),
    [getCanvasNodeDimensions, nodes],
  );

  const selectionGroupBounds = useMemo(() => {
    // 框选拖动过程中仍用选区矩形；松开后才用虚线容器包住多选节点。
    // 已经打组的选区由持久分组框绘制，避免叠两层。
    if (selectedNodeIds.size < 2 || selectionBox || selectedPersistedGroupId)
      return null;
    const selectedNodes = nodes.filter((node) => selectedNodeIds.has(node.id));
    return getSelectionGroupBounds(selectedNodes, getCanvasNodeDimensions);
  }, [
    getCanvasNodeDimensions,
    nodes,
    selectedNodeIds,
    selectedPersistedGroupId,
    selectionBox,
  ]);

  const hideNodeFloatingTools = Boolean(
    historyPageOpen ||
      previewMedia ||
      cloudAssetNodeId ||
      shortcutsOpen ||
      promptEditorExpanded ||
      replaceMediaConfirm,
  );
  const showSelectionToolbar =
    selectedNodeIds.size >= 2 && !selectionBox && !hideNodeFloatingTools;

  useLayoutEffect(() => {
    if (!showSelectionToolbar) {
      setSelectionToolbarLayout(null);
      return;
    }

    const updateLayout = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const canvasRect = canvas.getBoundingClientRect();
      const group = canvas.querySelector(
        '[data-canvas-selection-group]',
      ) as HTMLElement | null;
      const toolbarHeight = 48;
      const gap = 8;
      let left = canvasRect.left + canvasRect.width / 2;
      let top = canvasRect.top + 12;

      if (group) {
        const groupRect = group.getBoundingClientRect();
        const groupVisible =
          groupRect.bottom > canvasRect.top &&
          groupRect.top < canvasRect.bottom;
        if (groupVisible) {
          left = groupRect.left + groupRect.width / 2;
          const above = groupRect.top - toolbarHeight - gap;
          top =
            above >= canvasRect.top + 8
              ? above
              : Math.min(
                  groupRect.bottom + gap,
                  canvasRect.bottom - toolbarHeight - 8,
                );
        }
      }

      left = clamp(left, canvasRect.left + 24, canvasRect.right - 24);
      top = clamp(
        top,
        canvasRect.top + 8,
        Math.max(canvasRect.top + 8, canvasRect.bottom - toolbarHeight - 8),
      );
      setSelectionToolbarLayout((current) =>
        current &&
        Math.abs(current.left - left) < 0.5 &&
        Math.abs(current.top - top) < 0.5
          ? current
          : { left, top },
      );
    };

    updateLayout();
    window.addEventListener('resize', updateLayout);
    window.addEventListener('scroll', updateLayout, true);
    return () => {
      window.removeEventListener('resize', updateLayout);
      window.removeEventListener('scroll', updateLayout, true);
    };
  }, [
    expandedMediaNodeIds,
    nodes,
    selectedNodeIds,
    selectionGroupBounds,
    showSelectionToolbar,
    viewport,
  ]);

  const showCompactQuickSettings = Boolean(
    selectedNode &&
      selectedNodeIds.size === 1 &&
      !promptEditorExpanded &&
      !historyPageOpen &&
      !previewMedia &&
      !cloudAssetNodeId &&
      !shortcutsOpen &&
      !selectionBox,
  );

  useLayoutEffect(() => {
    if (!showCompactQuickSettings || !selectedNode) {
      setQuickSettingsLayout(null);
      return;
    }

    const updateLayout = () => {
      const canvas = canvasRef.current;
      const nodeEl = canvas?.querySelector(
        `[data-canvas-node="${selectedNode.id}"]`,
      ) as HTMLElement | null;
      if (!canvas || !nodeEl) return;
      const canvasRect = canvas.getBoundingClientRect();
      const nodeRect = nodeEl.getBoundingClientRect();
      const cardHeight =
        quickSettingsRef.current?.offsetHeight ||
        QUICK_SETTINGS_FALLBACK_HEIGHT;
      const maxLeft = Math.max(
        canvasRect.left + 12,
        canvasRect.right - QUICK_SETTINGS_WIDTH - 12,
      );
      const left = clamp(
        nodeRect.left + nodeRect.width / 2 - QUICK_SETTINGS_WIDTH / 2,
        canvasRect.left + 12,
        maxLeft,
      );
      const below = nodeRect.bottom + QUICK_SETTINGS_GAP;
      const above = nodeRect.top - cardHeight - QUICK_SETTINGS_GAP;
      const fitsBelow = below + cardHeight <= canvasRect.bottom - 12;
      const fitsAbove = above >= canvasRect.top + 12;
      const top = fitsBelow
        ? below
        : fitsAbove
          ? above
          : clamp(
              below,
              canvasRect.top + 12,
              Math.max(
                canvasRect.top + 12,
                canvasRect.bottom - cardHeight - 12,
              ),
            );
      setQuickSettingsLayout((current) =>
        current &&
        Math.abs(current.left - left) < 0.5 &&
        Math.abs(current.top - top) < 0.5
          ? current
          : { left, top },
      );
    };

    updateLayout();
    const frame = window.requestAnimationFrame(updateLayout);
    const observer = quickSettingsRef.current
      ? new ResizeObserver(() => updateLayout())
      : null;
    if (quickSettingsRef.current) observer?.observe(quickSettingsRef.current);
    window.addEventListener('resize', updateLayout);
    window.addEventListener('scroll', updateLayout, true);
    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener('resize', updateLayout);
      window.removeEventListener('scroll', updateLayout, true);
    };
  }, [
    cloudAssetNodeId,
    expandedMediaNodeIds,
    historyPageOpen,
    nodes,
    previewMedia,
    promptEditorExpanded,
    selectedNode,
    selectedNodeIds,
    selectionBox,
    shortcutsOpen,
    showCompactQuickSettings,
    viewport,
  ]);

  useEffect(() => {
    setSelectionGroupMenuOpen(false);
    setSelectionLayoutMenuOpen(false);
  }, [selectedNodeIds]);

  useEffect(() => {
    setPromptEditorExpanded(false);
  }, [selectedNodeId]);

  useEffect(() => {
    // 框选会先把 selectedNodeId 置空；不能因此把已经框上的多选清掉。
    if (!selectedNodeId) return;
    setSelectedNodeIds((current) =>
      current.has(selectedNodeId) ? current : new Set([selectedNodeId]),
    );
  }, [selectedNodeId]);

  useEffect(() => {
    const nodeIds = new Set(nodes.map((node) => node.id));
    setSelectedNodeIds((current) => {
      const next = new Set(
        Array.from(current).filter((nodeId) => nodeIds.has(nodeId)),
      );
      return next.size === current.size ? current : next;
    });
    setExpandedMediaNodeIds((current) => {
      const next = new Set(
        Array.from(current).filter((nodeId) => {
          const node = nodes.find((item) => item.id === nodeId);
          return Boolean(node && getOwnMediaResultUrls(node).length > 1);
        }),
      );
      return next.size === current.size ? current : next;
    });
  }, [nodes]);

  const buildCanvasChatContext = useCallback(
    async (
      scope: CanvasChatContextScope,
    ): Promise<CanvasChatContextPayload> => {
      const serializeNode = (node: CanvasNodeData) => ({
        id: node.id,
        kind: node.kind,
        title: node.title,
        prompt: node.prompt,
        status: node.status,
        position: { x: Math.round(node.x), y: Math.round(node.y) },
        parameters: {
          model: node.model,
          aspect_ratio: node.aspectRatio,
          resolution: node.resolution,
          duration: node.duration,
          voice: node.voiceName,
          speech_rate: node.speechRate,
          asset_type: node.assetType,
          asset_name: node.assetName,
        },
        result_count: getNodeResultHistory(node).length,
        result_types: Array.from(
          new Set(getNodeResultHistory(node).map((result) => result.type)),
        ),
      });
      const serializedEdges = edges.map((edge, index) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        connection_order: index + 1,
        input_order:
          edges
            .filter((candidate) => candidate.target === edge.target)
            .findIndex((candidate) => candidate.id === edge.id) + 1,
      }));
      const canvasSnapshot = {
        canvas: { id: 'local-default', title },
        viewport: {
          x: Math.round(viewport.x),
          y: Math.round(viewport.y),
          zoom: Number(viewport.zoom.toFixed(2)),
        },
        nodes: nodes.map(serializeNode),
        edges: serializedEdges,
      };
      const captureElement = async (element: HTMLElement) => {
        const screenshot = await html2canvas(element, {
          backgroundColor: theme === 'dark' ? '#080f1a' : '#eaf0f9',
          scale: Math.min(window.devicePixelRatio || 1, 1.5),
          useCORS: true,
          allowTaint: false,
          logging: false,
        });
        return screenshot.toDataURL('image/jpeg', 0.82);
      };

      if (scope === 'selected_node') {
        const selectedNodes = nodes.filter((node) =>
          selectedNodeIds.has(node.id),
        );
        const targetNodes =
          selectedNodes.length > 0
            ? selectedNodes
            : selectedNode
              ? [selectedNode]
              : [];
        if (targetNodes.length === 0) throw new Error('请先选择一个节点');
        const primaryNode = targetNodes[0];
        const incoming = serializedEdges.filter((edge) =>
          targetNodes.some((node) => edge.target === node.id),
        );
        const outgoing = serializedEdges.filter((edge) =>
          targetNodes.some((node) => edge.source === node.id),
        );
        const groupElement = document.querySelector<HTMLElement>(
          '[data-canvas-selection-group]',
        );
        const nodeElement = Array.from(
          document.querySelectorAll<HTMLElement>('[data-canvas-node]'),
        ).find((element) => element.dataset.canvasNode === primaryNode.id);
        const captureTarget =
          targetNodes.length > 1 ? groupElement : nodeElement;
        return {
          scope,
          label:
            targetNodes.length > 1
              ? `已选 ${targetNodes.length} 个节点`
              : `当前节点 · ${primaryNode.title}`,
          snapshot: {
            canvas: canvasSnapshot.canvas,
            node: serializeNode(primaryNode),
            nodes: targetNodes.map(serializeNode),
            incoming_connections: incoming,
            outgoing_connections: outgoing,
          },
          screenshot_data_url: captureTarget
            ? await captureElement(captureTarget)
            : undefined,
        };
      }

      if (scope === 'screenshot') {
        if (!canvasRef.current) throw new Error('画布尚未准备好，请稍后重试');
        return {
          scope,
          label: '页面截图',
          snapshot: {
            canvas: canvasSnapshot.canvas,
            visible_viewport: canvasSnapshot.viewport,
            node_count: nodes.length,
            edge_count: edges.length,
          },
          screenshot_data_url: await captureElement(canvasRef.current),
        };
      }

      return {
        scope,
        label: '整个画布',
        snapshot: canvasSnapshot,
      };
    },
    [edges, nodes, selectedNode, selectedNodeIds, theme, title, viewport],
  );

  const attachSelectedNodesToChat = useCallback(() => {
    const selectedNodes = nodes.filter((node) => selectedNodeIds.has(node.id));
    if (selectedNodes.length === 0) {
      setToast('请先选择要添加到对话的节点');
      return;
    }
    const label =
      selectedNodes.length > 1
        ? `已选 ${selectedNodes.length} 个节点`
        : `当前节点 · ${selectedNodes[0].title}`;
    setChatAttachRequest({
      nonce: Date.now(),
      scope: 'selected_node',
      label,
      thumbnails: selectedNodes.map((node) => ({
        id: node.id,
        title: node.title,
        url:
          getOwnMediaResultUrls(node)[0] ||
          node.resultUrl ||
          node.resultUrls?.[0],
        kind: node.kind,
      })),
    });
    setSelectionGroupMenuOpen(false);
    setChatOpen(true);
  }, [nodes, selectedNodeIds]);

  const contextMenuTargetNode = contextMenu?.targetNodeId
    ? nodes.find((node) => node.id === contextMenu.targetNodeId)
    : undefined;
  const contextMenuTargetEdge = contextMenu?.targetEdgeId
    ? edges.find((edge) => edge.id === contextMenu.targetEdgeId)
    : undefined;
  const canCreateSameGenerationNode = Boolean(
    contextMenuTargetNode &&
      ['text', 'image', 'video', 'music', 'tts'].includes(
        contextMenuTargetNode.kind,
      ) &&
      getNodeResultHistory(contextMenuTargetNode).length > 0,
  );
  const quickCommandSourceNode =
    contextMenuTargetNode &&
    canConnect(contextMenuTargetNode.kind, 'image') &&
    getNodeResultUrls(contextMenuTargetNode, 'image').length > 0
      ? contextMenuTargetNode
      : null;

  const canUndo = useMemo(
    () =>
      undoStackRef.current.length > 0 ||
      !areCanvasSnapshotsEqual({ nodes, edges }, historySnapshotRef.current),
    [edges, historyRevision, nodes],
  );
  const canRedo = useMemo(
    () =>
      redoStackRef.current.length > 0 &&
      areCanvasSnapshotsEqual({ nodes, edges }, historySnapshotRef.current),
    [edges, historyRevision, nodes],
  );

  const undoCanvas = useCallback(() => {
    if (historyCommitTimerRef.current !== null) {
      window.clearTimeout(historyCommitTimerRef.current);
      historyCommitTimerRef.current = null;
    }

    const currentSnapshot = { nodes, edges };
    const committedSnapshot = historySnapshotRef.current;
    const hasPendingChange = !areCanvasSnapshotsEqual(
      currentSnapshot,
      committedSnapshot,
    );
    const previousSnapshot = hasPendingChange
      ? committedSnapshot
      : undoStackRef.current.pop();
    if (!previousSnapshot) return;

    redoStackRef.current.push(currentSnapshot);
    isApplyingHistoryRef.current = true;
    historySnapshotRef.current = previousSnapshot;
    setNodes(previousSnapshot.nodes);
    setEdges(previousSnapshot.edges);
    setSelectedNodeId(null);
    setSelectedNodeIds(new Set());
    setSelectedEdgeId(null);
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setConnectionPointer(null);
    setNodeMenu(null);
    setContextMenu(null);
    setHistoryRevision((current) => current + 1);
    setToast('已撤销上一步操作');
  }, [edges, nodes]);

  const redoCanvas = useCallback(() => {
    if (historyCommitTimerRef.current !== null) {
      window.clearTimeout(historyCommitTimerRef.current);
      historyCommitTimerRef.current = null;
    }

    const currentSnapshot = { nodes, edges };
    if (!areCanvasSnapshotsEqual(currentSnapshot, historySnapshotRef.current)) {
      redoStackRef.current = [];
      setHistoryRevision((current) => current + 1);
      return;
    }
    const nextSnapshot = redoStackRef.current.pop();
    if (!nextSnapshot) return;
    undoStackRef.current.push(currentSnapshot);
    if (undoStackRef.current.length > 60) undoStackRef.current.shift();
    isApplyingHistoryRef.current = true;
    historySnapshotRef.current = nextSnapshot;
    setNodes(nextSnapshot.nodes);
    setEdges(nextSnapshot.edges);
    setSelectedNodeId(null);
    setSelectedNodeIds(new Set());
    setSelectedEdgeId(null);
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setConnectionPointer(null);
    setNodeMenu(null);
    setContextMenu(null);
    setHistoryRevision((current) => current + 1);
    setToast('已重做上一步操作');
  }, [edges, nodes]);

  const openQuickCommands = () => {
    if (!quickCommandSourceNode) return;
    if (quickCommandsCloseTimerRef.current !== null) {
      window.clearTimeout(quickCommandsCloseTimerRef.current);
      quickCommandsCloseTimerRef.current = null;
    }
    setQuickCommandsOpen(true);
  };

  const scheduleQuickCommandsClose = () => {
    if (quickCommandsCloseTimerRef.current !== null) {
      window.clearTimeout(quickCommandsCloseTimerRef.current);
    }
    quickCommandsCloseTimerRef.current = window.setTimeout(() => {
      setQuickCommandsOpen(false);
      quickCommandsCloseTimerRef.current = null;
    }, 140);
  };

  const clearPendingConnection = useCallback(() => {
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setConnectionOrigin(null);
    setConnectionPointer(null);
    setConnectionHoverTargetId(null);
    setConnectionRejectTargetId(null);
    setConnectionCursor(null);
  }, []);

  const connectManyNodes = useCallback(
    (sourceIds: string[], targetId: string) => {
      const uniqueSourceIds = Array.from(new Set(sourceIds)).filter(
        (sourceId) => sourceId !== targetId,
      );
      const targetNode = nodes.find((node) => node.id === targetId);
      if (!targetNode || uniqueSourceIds.length === 0) {
        clearPendingConnection();
        return false;
      }

      const existingPairs = new Set(
        edges.map((edge) => `${edge.source}->${edge.target}`),
      );
      const nextEdges: CanvasEdgeData[] = [];
      let incompatibleCount = 0;
      uniqueSourceIds.forEach((sourceId) => {
        const sourceNode = nodes.find((node) => node.id === sourceId);
        if (!sourceNode) return;
        if (!canConnect(sourceNode.kind, targetNode.kind)) {
          incompatibleCount += 1;
          return;
        }
        if (existingPairs.has(`${sourceId}->${targetId}`)) return;
        nextEdges.push({
          id: createId('edge'),
          source: sourceId,
          target: targetId,
        });
      });

      if (nextEdges.length === 0) {
        if (incompatibleCount === uniqueSourceIds.length) {
          const firstSource = nodes.find(
            (node) => node.id === uniqueSourceIds[0],
          );
          setToast(
            firstSource
              ? `${getNodeMeta(firstSource.kind).label}不能连接到${getNodeMeta(targetNode.kind).label}`
              : '无法连接到该节点',
          );
        } else {
          setToast(
            uniqueSourceIds.length > 1
              ? '这些素材已经连接'
              : '两个节点已经连接',
          );
        }
        clearPendingConnection();
        return false;
      }

      setEdges((current) => [...current, ...nextEdges]);
      setToast(
        nextEdges.length > 1
          ? `已将 ${nextEdges.length} 个素材连接到${getNodeMeta(targetNode.kind).label}`
          : '节点连接成功',
      );
      clearPendingConnection();
      return true;
    },
    [clearPendingConnection, edges, nodes],
  );

  useLayoutEffect(() => {
    latestCanvasStateRef.current = { edges, nodes, title, viewport };
  }, [edges, nodes, title, viewport]);

  const buildPersistentDraft = useCallback(
    (draftNodes = nodes): CanvasDraft => {
      const updatedAt = new Date();
      const latestState = latestCanvasStateRef.current;
      const persistedNodes = draftNodes.map((node) => {
        const resultType = getNodeResultType(node);
        const persistentResultUrls = (node.resultUrls || [])
          .filter(
            (url) =>
              url && !url.startsWith('data:') && !url.startsWith('blob:'),
          )
          .map((url) =>
            getStableCanvasMediaUrl(url, resultType, node.assetName),
          );
        const persistentResultHistory = getNodeResultHistory(node)
          .filter(
            (result) =>
              result.url &&
              !result.url.startsWith('data:') &&
              !result.url.startsWith('blob:'),
          )
          .map((result) => ({
            ...result,
            url: getStableCanvasMediaUrl(
              result.url,
              result.type,
              node.assetName,
            ),
          }));
        const persistentResultUrl =
          node.resultUrl &&
          !node.resultUrl.startsWith('data:') &&
          !node.resultUrl.startsWith('blob:')
            ? getStableCanvasMediaUrl(
                node.resultUrl,
                resultType,
                node.assetName,
              )
            : persistentResultUrls[0];
        return {
          ...node,
          resultUrl: persistentResultUrl,
          resultUrls:
            persistentResultUrls.length > 0 ? persistentResultUrls : undefined,
          resultHistory:
            persistentResultHistory.length > 0
              ? persistentResultHistory
              : undefined,
        };
      });
      return {
        version: 1,
        title: latestState.title,
        nodes: persistedNodes,
        edges: latestState.edges,
        viewport: latestState.viewport,
        updatedAt: updatedAt.toISOString(),
      };
    },
    [nodes],
  );

  useLayoutEffect(() => {
    serverSyncReadyRef.current = serverSyncReady;
  }, [serverSyncReady]);

  const persistDraftToServer = useCallback(
    async (draft: CanvasDraft, showMessage = false) => {
      if (!serverSyncReadyRef.current) return;
      if (isSaveConflictNoticeOpenRef.current) return;
      queuedServerDraftRef.current = draft;
      if (serverSaveInFlightRef.current) return;

      serverSaveInFlightRef.current = true;
      try {
        while (queuedServerDraftRef.current) {
          const nextDraft = queuedServerDraftRef.current;
          queuedServerDraftRef.current = null;
          const contentSignature = getDraftContentSignature(nextDraft);
          if (contentSignature === lastServerDraftRef.current) continue;

          const record = await savePersistedCanvas(
            normalizedCanvasId,
            nextDraft,
            serverRevisionRef.current,
          );
          serverRevisionRef.current = record.revision;
          lastServerDraftRef.current = contentSignature;
          if (hasSaveConflictRef.current) {
            hasSaveConflictRef.current = false;
            setHasSaveConflict(false);
            isSaveConflictNoticeOpenRef.current = false;
            setIsSaveConflictNoticeOpen(false);
          }
          const savedAt = record.updatedAt
            ? new Date(record.updatedAt)
            : new Date();
          setLastSavedAt(savedAt);
          if (showMessage) setToast('画布已保存到服务器');
        }
      } catch (error) {
        const syncError = error as Error & { reason?: string };
        if (syncError.reason === 'revision_conflict') {
          hasSaveConflictRef.current = true;
          queuedServerDraftRef.current = null;
          setHasSaveConflict(true);
          isSaveConflictNoticeOpenRef.current = true;
          setIsSaveConflictNoticeOpen(true);
        } else {
          setToast('服务器保存失败，已保留本地草稿');
        }
      } finally {
        serverSaveInFlightRef.current = false;
      }
    },
    [normalizedCanvasId],
  );

  const forceSaveDraft = useCallback(async () => {
    if (!serverSyncReadyRef.current || forceSaveInFlightRef.current) return;

    forceSaveInFlightRef.current = true;
    setIsForceSaving(true);
    const draft = buildPersistentDraft(latestCanvasStateRef.current.nodes);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(draft));
      const record = await savePersistedCanvas(
        normalizedCanvasId,
        draft,
        serverRevisionRef.current,
        true,
      );
      serverRevisionRef.current = record.revision;
      lastServerDraftRef.current = getDraftContentSignature(draft);
      queuedServerDraftRef.current = null;
      hasSaveConflictRef.current = false;
      setHasSaveConflict(false);
      isSaveConflictNoticeOpenRef.current = false;
      setIsSaveConflictNoticeOpen(false);
      setLastSavedAt(
        record.updatedAt ? new Date(record.updatedAt) : new Date(),
      );
      setToast('已覆盖保存到服务器');
    } catch (error) {
      console.error('[Canvas] 覆盖保存失败:', error);
      setToast('覆盖保存失败，请稍后重试');
    } finally {
      forceSaveInFlightRef.current = false;
      setIsForceSaving(false);
    }
  }, [buildPersistentDraft, normalizedCanvasId, storageKey]);

  const saveDraft = useCallback(
    (showMessage = true) => {
      if (!serverSyncReadyRef.current) {
        if (showMessage) setToast('服务器画布仍在加载，请稍后保存');
        return;
      }
      if (isSaveConflictNoticeOpenRef.current) return;
      const draft = buildPersistentDraft();
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(draft));
        void persistDraftToServer(draft, showMessage);
      } catch {
        if (showMessage) setToast('画布保存失败，请导出工作流后重试');
      }
    },
    [buildPersistentDraft, persistDraftToServer, storageKey],
  );

  /**
   * 立即持久化生成结果等关键节点字段，避免等待自动保存期间刷新页面导致结果关联丢失。
   * 常规自动保存仍会继续执行，负责兜底同步生成完成后的其他画布变更。
   */
  const persistNodePatchImmediately = useCallback(
    (nodeId: string, patch: Partial<CanvasNodeData>) => {
      if (!serverSyncReadyRef.current) return;

      const latestState = latestCanvasStateRef.current;
      const nextNodes = latestState.nodes.map((node) =>
        node.id === nodeId ? { ...node, ...patch } : node,
      );
      latestCanvasStateRef.current = { ...latestState, nodes: nextNodes };
      const draft = buildPersistentDraft(nextNodes);

      try {
        window.localStorage.setItem(storageKey, JSON.stringify(draft));
        void persistDraftToServer(draft, false);
      } catch {
        // 浏览器存储暂时不可用时仍保留正常自动保存，不能因此把生成成功误报为失败。
      }
    },
    [buildPersistentDraft, persistDraftToServer, storageKey],
  );

  useEffect(() => {
    let disposed = false;
    serverSyncReadyRef.current = false;
    setServerSyncReady(false);
    queuedServerDraftRef.current = null;
    lastServerDraftRef.current = '';
    hasSaveConflictRef.current = false;
    setHasSaveConflict(false);
    isSaveConflictNoticeOpenRef.current = false;
    setIsSaveConflictNoticeOpen(false);

    void loadPersistedCanvas(normalizedCanvasId)
      .then((record) => {
        if (disposed) return;
        serverRevisionRef.current = Math.max(1, Number(record.revision || 1));
        const remoteDraft = record.draft;
        // 服务端只要存在记录（包括有意保存的空画布）就始终为权威数据，禁止浏览器缓存静默回写。
        const authoritativeDraft: CanvasDraft = remoteDraft
          ? {
              ...remoteDraft,
              title: remoteDraft.title || record.name || '未命名画布',
              nodes: Array.isArray(remoteDraft.nodes)
                ? remoteDraft.nodes.map(normalizeCanvasNode)
                : [],
              edges: Array.isArray(remoteDraft.edges) ? remoteDraft.edges : [],
              viewport: remoteDraft.viewport || { x: 0, y: 0, zoom: 1 },
              updatedAt:
                remoteDraft.updatedAt ||
                record.updatedAt ||
                new Date().toISOString(),
            }
          : {
              version: 1,
              title: record.name || '未命名画布',
              nodes: [],
              edges: [],
              viewport: { x: 0, y: 0, zoom: 1 },
              updatedAt: record.updatedAt || new Date().toISOString(),
            };

        setTitle(authoritativeDraft.title);
        setNodes(authoritativeDraft.nodes);
        setEdges(authoritativeDraft.edges);
        setViewport(authoritativeDraft.viewport);
        setSelectedNodeId(authoritativeDraft.nodes[0]?.id || null);
        setLastSavedAt(new Date(authoritativeDraft.updatedAt));
        historySnapshotRef.current = {
          nodes: authoritativeDraft.nodes,
          edges: authoritativeDraft.edges,
        };
        undoStackRef.current = [];
        redoStackRef.current = [];
        lastServerDraftRef.current =
          getDraftContentSignature(authoritativeDraft);
        try {
          window.localStorage.setItem(
            storageKey,
            JSON.stringify(authoritativeDraft),
          );
        } catch {
          // 浏览器存储不可用时仍以服务端数据为准。
        }
        setServerSyncReady(true);
      })
      .catch(async (error) => {
        if (disposed) return;
        const loadError = error as Error & { status?: number };
        if (loadError.status === 404) {
          const localDraft = initialDraftRef.current as CanvasDraft;
          try {
            const record = await createPersistedCanvas(
              normalizedCanvasId,
              localDraft,
            );
            if (disposed) return;
            serverRevisionRef.current = Math.max(
              1,
              Number(record.revision || 1),
            );
            lastServerDraftRef.current = getDraftContentSignature(localDraft);
            setServerSyncReady(true);
            setLastSavedAt(new Date(localDraft.updatedAt));
            if (
              storedDraftRef.current &&
              (localDraft.nodes.length || localDraft.edges.length)
            ) {
              setToast('已将本地旧画布恢复到服务器');
            }
            return;
          } catch (migrationError) {
            console.error('[Canvas] 本地画布迁移失败:', migrationError);
          }
        }
        console.error('[Canvas] 服务端画布加载失败:', error);
        setToast('服务器画布加载失败，本地内容仅供查看，自动保存已暂停');
      });

    return () => {
      disposed = true;
      serverSyncReadyRef.current = false;
    };
  }, [normalizedCanvasId, storageKey]);

  useEffect(() => {
    if (!serverSyncReady) return undefined;
    const timer = window.setTimeout(() => saveDraft(false), 700);
    return () => window.clearTimeout(timer);
  }, [saveDraft, serverSyncReady]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const syncMotionPreference = () =>
      setPrefersReducedMotion(mediaQuery.matches);
    syncMotionPreference();
    mediaQuery.addEventListener('change', syncMotionPreference);
    return () => mediaQuery.removeEventListener('change', syncMotionPreference);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Theme persistence is optional when storage is unavailable.
    }
  }, [theme]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        CUSTOM_IMAGE_COMMANDS_STORAGE_KEY,
        JSON.stringify(customImageCommands),
      );
    } catch {
      // Custom command persistence is optional when storage is unavailable.
    }
  }, [customImageCommands]);

  useEffect(() => {
    const nextSnapshot = { nodes, edges };
    if (isApplyingHistoryRef.current) {
      isApplyingHistoryRef.current = false;
      historySnapshotRef.current = nextSnapshot;
      return;
    }
    if (areCanvasSnapshotsEqual(nextSnapshot, historySnapshotRef.current))
      return;

    if (historyCommitTimerRef.current !== null) {
      window.clearTimeout(historyCommitTimerRef.current);
    }
    historyCommitTimerRef.current = window.setTimeout(() => {
      const previousSnapshot = historySnapshotRef.current;
      if (!areCanvasSnapshotsEqual(nextSnapshot, previousSnapshot)) {
        undoStackRef.current.push(previousSnapshot);
        if (undoStackRef.current.length > 60) undoStackRef.current.shift();
        redoStackRef.current = [];
        historySnapshotRef.current = nextSnapshot;
        setHistoryRevision((current) => current + 1);
      }
      historyCommitTimerRef.current = null;
    }, 280);

    return () => {
      if (historyCommitTimerRef.current !== null) {
        window.clearTimeout(historyCommitTimerRef.current);
        historyCommitTimerRef.current = null;
      }
    };
  }, [edges, nodes]);

  useEffect(() => {
    if (!nodeMenu) return;
    const frame = window.requestAnimationFrame(() => {
      nodeMenuRef.current
        ?.querySelector<HTMLButtonElement>('button:not(:disabled)')
        ?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [nodeMenu]);

  useEffect(() => {
    if (!contextMenu) return;
    const frame = window.requestAnimationFrame(() => {
      contextMenuRef.current
        ?.querySelector<HTMLButtonElement>('button:not(:disabled)')
        ?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [contextMenu]);

  useEffect(() => {
    if (contextMenu) return;
    setQuickCommandsOpen(false);
    if (quickCommandsCloseTimerRef.current !== null) {
      window.clearTimeout(quickCommandsCloseTimerRef.current);
      quickCommandsCloseTimerRef.current = null;
    }
  }, [contextMenu]);

  useEffect(() => {
    if (!shortcutsOpen) return;
    const frame = window.requestAnimationFrame(() =>
      shortcutsCloseButtonRef.current?.focus(),
    );
    return () => window.cancelAnimationFrame(frame);
  }, [shortcutsOpen]);

  useEffect(() => {
    if (!nodeMenu && !contextMenu) return;
    const closeOpenMenus = (event: PointerEvent) => {
      const target = event.target as Node;
      if (nodeMenuRef.current?.contains(target)) return;
      if (contextMenuRef.current?.contains(target)) return;
      if (quickCommandsRef.current?.contains(target)) return;
      setNodeMenu(null);
      setContextMenu(null);
    };
    window.addEventListener('pointerdown', closeOpenMenus, true);
    return () =>
      window.removeEventListener('pointerdown', closeOpenMenus, true);
  }, [contextMenu, nodeMenu]);

  useEffect(() => {
    if (!toolMenuOpen) return;
    const closeToolMenu = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[data-canvas-tool-menu]')) return;
      setToolMenuOpen(false);
    };
    window.addEventListener('pointerdown', closeToolMenu, true);
    return () => window.removeEventListener('pointerdown', closeToolMenu, true);
  }, [toolMenuOpen]);

  useEffect(() => {
    if (!previewMedia) return;
    const handlePreviewKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPreviewMedia(null);
    };
    window.addEventListener('keydown', handlePreviewKeyDown);
    return () => window.removeEventListener('keydown', handlePreviewKeyDown);
  }, [previewMedia]);

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      // 裁剪和智能抠图都在独立弹窗里完成，不要带动画布节点。
      if (
        imageAiToolRef.current?.mode === 'crop' ||
        imageAiToolRef.current?.mode === 'matting'
      )
        return;
      if (mediaResizeRef.current) {
        const resize = mediaResizeRef.current;
        const horizontalDirection = resize.corner.includes('w') ? -1 : 1;
        const verticalDirection = resize.corner.includes('n') ? -1 : 1;
        const deltaX =
          ((event.clientX - resize.startClientX) / viewport.zoom) *
          horizontalDirection;
        const deltaY =
          ((event.clientY - resize.startClientY) / viewport.zoom) *
          verticalDirection;
        const normalizedX = deltaX / resize.startWidth;
        const normalizedY = deltaY / resize.startHeight;
        const normalizedDelta =
          Math.abs(normalizedX) >= Math.abs(normalizedY)
            ? normalizedX
            : normalizedY;
        const nextScale = clamp(
          resize.startScale * (1 + normalizedDelta),
          MIN_MEDIA_DISPLAY_SCALE,
          MAX_MEDIA_DISPLAY_SCALE,
        );
        const scaleRatio = nextScale / resize.startScale;
        const nextWidth = resize.startWidth * scaleRatio;
        const nextHeight = resize.startHeight * scaleRatio;

        setNodes((current) =>
          current.map((node) =>
            node.id === resize.nodeId
              ? {
                  ...node,
                  x: resize.corner.includes('w')
                    ? resize.startNodeX + resize.startWidth - nextWidth
                    : resize.startNodeX,
                  y: resize.corner.includes('n')
                    ? resize.startNodeY + resize.startHeight - nextHeight
                    : resize.startNodeY,
                  mediaDisplayScale: nextScale,
                }
              : node,
          ),
        );
        return;
      }

      if (connectionDragRef.current) {
        const connection = connectionDragRef.current;
        const deltaX = event.clientX - connection.startClientX;
        const deltaY = event.clientY - connection.startClientY;
        if (Math.hypot(deltaX, deltaY) >= 4) connection.moved = true;

        const rect = canvasRef.current?.getBoundingClientRect();
        if (rect) {
          setConnectionPointer({
            x: (event.clientX - rect.left - viewport.x) / viewport.zoom,
            y: (event.clientY - rect.top - viewport.y) / viewport.zoom,
          });
        }

        const nextHoverTargetId = resolveConnectionDropTargetId({
          clientX: event.clientX,
          clientY: event.clientY,
          sourceId: connection.sourceId,
          sourceIds: connection.sourceIds,
          canvasNodes: nodes,
          canvasRect: rect ?? null,
          viewport,
          getDimensions: getCanvasNodeDimensions,
          inputAnchors: connectionAnchors.inputs,
        });
        const hoveredNodeId = resolveConnectionHoverNodeId(
          event.clientX,
          event.clientY,
          connection.sourceId,
          connection.sourceIds,
        );
        setConnectionCursor({ x: event.clientX, y: event.clientY });
        setConnectionHoverTargetId((current) =>
          current === nextHoverTargetId ? current : nextHoverTargetId,
        );
        setConnectionRejectTargetId(
          hoveredNodeId && hoveredNodeId !== nextHoverTargetId
            ? hoveredNodeId
            : null,
        );
        return;
      }

      if (selectionRef.current) {
        const selection = selectionRef.current;
        const rect = canvasRef.current?.getBoundingClientRect();
        if (!rect) return;
        const currentLocalX = clamp(event.clientX - rect.left, 0, rect.width);
        const currentLocalY = clamp(event.clientY - rect.top, 0, rect.height);
        const left = Math.min(selection.startLocalX, currentLocalX);
        const top = Math.min(selection.startLocalY, currentLocalY);
        const right = Math.max(selection.startLocalX, currentLocalX);
        const bottom = Math.max(selection.startLocalY, currentLocalY);
        setSelectionBox({
          left,
          top,
          width: right - left,
          height: bottom - top,
        });

        const canvasLeft = (left - viewport.x) / viewport.zoom;
        const canvasTop = (top - viewport.y) / viewport.zoom;
        const canvasRight = (right - viewport.x) / viewport.zoom;
        const canvasBottom = (bottom - viewport.y) / viewport.zoom;
        const hitNodeIds = nodes
          .filter((node) => {
            const dimensions = getCanvasNodeDimensions(node);
            return (
              node.x < canvasRight &&
              node.x + dimensions.width > canvasLeft &&
              node.y < canvasBottom &&
              node.y + dimensions.height > canvasTop
            );
          })
          .map((node) => node.id);
        const nextNodeIds = new Set([...selection.baseNodeIds, ...hitNodeIds]);
        setSelectedNodeIds(nextNodeIds);
        setSelectedNodeId(
          hitNodeIds[0] || Array.from(selection.baseNodeIds)[0] || null,
        );
        if (nextNodeIds.size > 0) setSelectedEdgeId(null);
        return;
      }

      if (
        altDuplicateDragRef.current &&
        !altDuplicateDragRef.current.committed
      ) {
        const pending = altDuplicateDragRef.current;
        const pixelDistance = Math.hypot(
          event.clientX - pending.startClientX,
          event.clientY - pending.startClientY,
        );
        if (pixelDistance < 4) return;

        const idMap: Record<string, string> = {};
        pending.sourceIds.forEach((sourceId) => {
          idMap[sourceId] = createId('node');
        });
        const newIds = pending.sourceIds
          .map((sourceId) => idMap[sourceId])
          .filter(Boolean);
        const deltaX = (event.clientX - pending.startClientX) / viewport.zoom;
        const deltaY = (event.clientY - pending.startClientY) / viewport.zoom;

        pending.committed = true;
        dragRef.current = {
          nodeIds: newIds,
          startClientX: pending.startClientX,
          startClientY: pending.startClientY,
          startPositions: Object.fromEntries(
            pending.sourceIds
              .filter(
                (sourceId) =>
                  pending.startPositions[sourceId] && idMap[sourceId],
              )
              .map((sourceId) => [
                idMap[sourceId],
                pending.startPositions[sourceId],
              ]),
          ),
        };

        setNodes((current) => {
          const usedTitles = current.map((node) => node.title);
          const clones = pending.sourceIds
            .map((sourceId) => current.find((node) => node.id === sourceId))
            .filter((node): node is CanvasNodeData => Boolean(node))
            .map((node) => {
              const clone = cloneCanvasNode(
                node,
                idMap[node.id],
                deltaX,
                deltaY,
                usedTitles,
              );
              if (clone.imageReferenceSourceOrder) {
                clone.imageReferenceSourceOrder =
                  clone.imageReferenceSourceOrder.map(
                    (sourceId) => idMap[sourceId] || sourceId,
                  );
              }
              usedTitles.push(clone.title);
              return clone;
            });
          return clones.length > 0 ? [...current, ...clones] : current;
        });
        // Alt/⌥ 拖出副本只复制节点，不带连线；Ctrl/⌘+D 才会连上上下游。
        setSelectedNodeIds(new Set(newIds));
        setSelectedNodeId(newIds[0] || null);
        setPendingSourceId(null);
        setPendingSourceIds([]);
        setToast(
          pending.sourceIds.length > 1
            ? `已复制 ${pending.sourceIds.length} 个节点`
            : '节点已复制',
        );
        return;
      }

      if (dragRef.current) {
        const drag = dragRef.current;
        const deltaX = (event.clientX - drag.startClientX) / viewport.zoom;
        const deltaY = (event.clientY - drag.startClientY) / viewport.zoom;
        setNodes((current) =>
          current.map((node) => {
            const startPosition = drag.startPositions[node.id];
            return startPosition
              ? {
                  ...node,
                  x: Math.round(startPosition.x + deltaX),
                  y: Math.round(startPosition.y + deltaY),
                }
              : node;
          }),
        );
        return;
      }

      if (panRef.current) {
        const pan = panRef.current;
        setViewport((current) => ({
          ...current,
          x: pan.startViewportX + event.clientX - pan.startClientX,
          y: pan.startViewportY + event.clientY - pan.startClientY,
        }));
      }
    };

    const handlePointerUp = (event: PointerEvent) => {
      const connection = connectionDragRef.current;
      if (connection) {
        if (connection.moved) {
          const rect = canvasRef.current?.getBoundingClientRect();
          const snappedTargetId = resolveConnectionDropTargetId({
            clientX: event.clientX,
            clientY: event.clientY,
            sourceId: connection.sourceId,
            sourceIds: connection.sourceIds,
            canvasNodes: nodes,
            canvasRect: rect ?? null,
            viewport,
            getDimensions: getCanvasNodeDimensions,
            inputAnchors: connectionAnchors.inputs,
          });
          if (snappedTargetId) {
            connectManyNodes(connection.sourceIds, snappedTargetId);
          } else {
            const hitElement = document.elementFromPoint(
              event.clientX,
              event.clientY,
            );
            const isInsideCanvas = Boolean(
              rect &&
                event.clientX >= rect.left &&
                event.clientX <= rect.right &&
                event.clientY >= rect.top &&
                event.clientY <= rect.bottom,
            );
            const isOverNode = Boolean(
              hitElement?.closest('[data-canvas-node]'),
            );
            if (rect && isInsideCanvas && !isOverNode) {
              const localX = event.clientX - rect.left;
              const localY = event.clientY - rect.top;
              setPendingSourceId(connection.sourceId);
              setPendingSourceIds(connection.sourceIds);
              setConnectionOrigin(connection.origin || null);
              setShortcutsOpen(false);
              setContextMenu(null);
              setNodeMenu({
                left: clamp(localX + 10, 12, Math.max(12, rect.width - 316)),
                top: clamp(localY + 10, 12, Math.max(12, rect.height - 516)),
                nodePosition: {
                  x: Math.round(
                    (localX - viewport.x) / viewport.zoom - NODE_WIDTH / 2,
                  ),
                  y: Math.round(
                    (localY - viewport.y) / viewport.zoom - NODE_HEIGHT / 2,
                  ),
                },
              });
            } else {
              clearPendingConnection();
            }
          }
        }
        connectionDragRef.current = null;
        setConnectionPointer(null);
        setConnectionHoverTargetId(null);
        setConnectionRejectTargetId(null);
        setConnectionCursor(null);
      }
      mediaResizeRef.current = null;
      dragRef.current = null;
      altDuplicateDragRef.current = null;
      if (selectionRef.current) {
        // 框选松开后浏览器常会再补一次 pointerdown/click，不能让它把多选清掉。
        suppressMarqueeReleaseRef.current = true;
        window.setTimeout(() => {
          suppressMarqueeReleaseRef.current = false;
        }, 400);
      }
      selectionRef.current = null;
      setSelectionBox(null);
      panRef.current = null;
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
    };
  }, [
    clearPendingConnection,
    connectManyNodes,
    connectionAnchors.inputs,
    getCanvasNodeDimensions,
    nodes,
    viewport,
  ]);

  const deleteNodes = useCallback((nodeIds: string[]) => {
    if (nodeIds.length === 0) return;
    const idSet = new Set(nodeIds);
    setNodes((current) =>
      pruneSingletonGroups(current.filter((node) => !idSet.has(node.id))),
    );
    setEdges((current) =>
      current.filter(
        (edge) => !idSet.has(edge.source) && !idSet.has(edge.target),
      ),
    );
    setSelectedNodeId((current) =>
      current && idSet.has(current) ? null : current,
    );
    setSelectedNodeIds((current) => {
      const next = new Set(
        Array.from(current).filter((nodeId) => !idSet.has(nodeId)),
      );
      return next.size === current.size ? current : next;
    });
    setPendingSourceId((current) =>
      current && idSet.has(current) ? null : current,
    );
    setPendingSourceIds((current) =>
      current.filter((sourceId) => !idSet.has(sourceId)),
    );
  }, []);

  const deleteNode = useCallback(
    (nodeId: string) => {
      deleteNodes([nodeId]);
    },
    [deleteNodes],
  );

  const deleteNodeFromContextMenu = () => {
    const targetNode = contextMenu?.targetNodeId
      ? nodes.find((node) => node.id === contextMenu.targetNodeId)
      : null;
    if (!targetNode) return;

    deleteNode(targetNode.id);
    setContextMenu(null);
    setQuickCommandsOpen(false);
    setToast(`已删除节点“${targetNode.title}”`);
  };

  const duplicateNode = useCallback(
    (nodeId: string) => {
      const source = nodes.find((node) => node.id === nodeId);
      if (!source) return;
      const duplicate = cloneCanvasNode(
        source,
        createId('node'),
        32,
        32,
        nodes.map((node) => node.title),
      );
      setNodes((current) => [...current, duplicate]);
      setEdges((current) => {
        const clonedEdges = cloneEdgesForDuplication(current, {
          [source.id]: duplicate.id,
        });
        return clonedEdges.length > 0 ? [...current, ...clonedEdges] : current;
      });
      setSelectedNodeIds(new Set([duplicate.id]));
      setSelectedNodeId(duplicate.id);
      setPendingSourceId(null);
      setPendingSourceIds([]);
      setToast('节点已复制');
    },
    [nodes],
  );

  const duplicateSelectedNodes = useCallback(() => {
    const sourceIds = Array.from(selectedNodeIds);
    if (sourceIds.length === 0) return;
    const idMap: Record<string, string> = {};
    sourceIds.forEach((sourceId) => {
      idMap[sourceId] = createId('node');
    });
    const newIds = sourceIds.map((sourceId) => idMap[sourceId]).filter(Boolean);
    setNodes((current) => {
      const usedTitles = current.map((node) => node.title);
      const clones = sourceIds
        .map((sourceId) => current.find((node) => node.id === sourceId))
        .filter((node): node is CanvasNodeData => Boolean(node))
        .map((node) => {
          const clone = cloneCanvasNode(
            node,
            idMap[node.id],
            36,
            36,
            usedTitles,
          );
          if (clone.imageReferenceSourceOrder) {
            clone.imageReferenceSourceOrder =
              clone.imageReferenceSourceOrder.map(
                (sourceId) => idMap[sourceId] || sourceId,
              );
          }
          usedTitles.push(clone.title);
          return clone;
        });
      return clones.length > 0 ? [...current, ...clones] : current;
    });
    setEdges((current) => {
      const clonedEdges = cloneEdgesForDuplication(current, idMap);
      return clonedEdges.length > 0 ? [...current, ...clonedEdges] : current;
    });
    setSelectedNodeIds(new Set(newIds));
    setSelectedNodeId(newIds[0] || null);
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setSelectionGroupMenuOpen(false);
    setSelectionLayoutMenuOpen(false);
    setToast(
      newIds.length > 1 ? `已创建 ${newIds.length} 个副本` : '节点已复制',
    );
  }, [selectedNodeIds]);

  const groupSelectedNodes = useCallback(() => {
    const sourceIds = Array.from(selectedNodeIds);
    if (sourceIds.length < 2) return;
    const groupId = createId('group');
    setNodes((current) =>
      pruneSingletonGroups(
        current.map((node) =>
          sourceIds.includes(node.id) ? { ...node, groupId } : node,
        ),
      ),
    );
    setSelectionGroupMenuOpen(false);
    setSelectionLayoutMenuOpen(false);
    setToast(`已将 ${sourceIds.length} 个节点打组`);
  }, [selectedNodeIds]);

  const ungroupSelectedNodes = useCallback(() => {
    const groupIds = new Set(
      nodes
        .filter((node) => selectedNodeIds.has(node.id) && node.groupId)
        .map((node) => node.groupId as string),
    );
    if (groupIds.size === 0) return;
    setNodes((current) =>
      current.map((node) =>
        node.groupId && groupIds.has(node.groupId)
          ? { ...node, groupId: undefined }
          : node,
      ),
    );
    setSelectionGroupMenuOpen(false);
    setSelectionLayoutMenuOpen(false);
    setToast('已取消打组');
  }, [nodes, selectedNodeIds]);

  const applySelectionLayout = (mode: SelectionLayoutMode) => {
    setSelectionLayoutMenuOpen(false);
    setSelectionGroupMenuOpen(false);
    if (selectedNodeIds.size < 2) return;
    const nextNodes = arrangeSelectedNodes(
      nodes,
      selectedNodeIds,
      getCanvasNodeDimensions,
      mode,
    );
    if (areNodePositionsEqual(nodes, nextNodes)) {
      setToast('所选节点已经是该排列');
      return;
    }
    setNodes(nextNodes);
    const labels: Record<SelectionLayoutMode, string> = {
      grid: '已宫格排列',
      horizontal: '已水平排列',
      vertical: '已垂直排列',
    };
    setToast(labels[mode]);
  };

  const createSameGenerationNode = useCallback(
    (nodeId: string) => {
      const source = nodes.find((node) => node.id === nodeId);
      if (
        !source ||
        !['text', 'image', 'video', 'music', 'tts'].includes(source.kind)
      )
        return;
      const sameStyleNode: CanvasNodeData = {
        ...source,
        id: createId('node'),
        title: `${source.title} 同款`,
        x: source.x + 40,
        y: source.y + 40,
        count: source.count,
        textImageConfig: source.textImageConfig
          ? { ...source.textImageConfig }
          : undefined,
        textVideoConfig: source.textVideoConfig
          ? { ...source.textVideoConfig }
          : undefined,
        resultUrl: undefined,
        resultUrls: undefined,
        resultHistory: undefined,
        resultAssetType: undefined,
        mediaAspectRatio: undefined,
        mediaDisplayScale: undefined,
        officialAssetEnabled: false,
        officialAssetId: undefined,
        officialAssetStatus: 'idle',
        officialAssetError: undefined,
        status: 'draft',
      };
      setNodes((current) => [...current, sameStyleNode]);
      setSelectedNodeIds(new Set([sameStyleNode.id]));
      setSelectedNodeId(sameStyleNode.id);
      setContextMenu(null);
      setQuickCommandsOpen(false);
      setToast('已创建同款节点，参数已复制，尚未开始生成');
    },
    [nodes],
  );

  const updateNode = useCallback(
    (nodeId: string, updates: Partial<CanvasNodeData>) => {
      setNodes((current) =>
        current.map((node) =>
          node.id === nodeId ? { ...node, ...updates } : node,
        ),
      );
    },
    [],
  );

  const appendNodeResults = useCallback(
    (nodeId: string, urls: string[], type: CanvasNodeResult['type']) => {
      const createdAt = new Date().toISOString();
      const node = latestCanvasStateRef.current.nodes.find(
        (item) => item.id === nodeId,
      );
      if (!node) return;

      const stableUrls = Array.from(
        new Set(urls.map((url) => getStableCanvasMediaUrl(url, type))),
      );
      const newResults = stableUrls.map((url, index) => ({
        id: createId(`result-${index + 1}`),
        url,
        type,
        createdAt,
      }));
      const newUrls = new Set(stableUrls);
      const resultPatch: Partial<CanvasNodeData> = {
        resultUrl: stableUrls[0],
        resultUrls: stableUrls,
        resultHistory: [
          ...newResults,
          ...getNodeResultHistory(node).filter(
            (result) => !newUrls.has(result.url),
          ),
        ],
        resultAssetType: type,
        mediaAspectRatio: undefined,
        mediaDisplayScale: undefined,
        status: 'ready',
      };

      // 节点卡片只展示最近一次批量结果；完整历史仍保留在 resultHistory 中。
      updateNode(nodeId, resultPatch);
      persistNodePatchImmediately(nodeId, resultPatch);
    },
    [persistNodePatchImmediately, updateNode],
  );

  const setMainNodeResult = useCallback(
    (nodeId: string, url: string) => {
      const node = nodes.find((item) => item.id === nodeId);
      if (!node) return;
      const currentUrls = getOwnMediaResultUrls(node);
      if (!currentUrls.includes(url) || currentUrls[0] === url) return;
      const resultUrls = [url, ...currentUrls.filter((item) => item !== url)];
      const history = getNodeResultHistory(node);
      updateNode(nodeId, {
        resultUrl: url,
        resultUrls,
        resultHistory: [
          ...history.filter((result) => result.url === url),
          ...history.filter((result) => result.url !== url),
        ],
        mediaAspectRatio: undefined,
      });
      setToast(
        getNodeResultType(node) === 'video' ? '已设为主视频' : '已设为主图',
      );
    },
    [nodes, updateNode],
  );

  const setMediaNodeExpanded = useCallback(
    (nodeId: string, expanded: boolean) => {
      setExpandedMediaNodeIds((current) => {
        const isExpanded = current.has(nodeId);
        if (expanded === isExpanded) return current;
        const next = new Set(current);
        if (expanded) next.add(nodeId);
        else next.delete(nodeId);
        return next;
      });
    },
    [],
  );

  const removeNodeResult = useCallback((nodeId: string, resultId: string) => {
    setNodes((current) =>
      current.map((node) => {
        if (node.id !== nodeId) return node;
        const existingHistory = getNodeResultHistory(node);
        const removedResult = existingHistory.find(
          (result) => result.id === resultId,
        );
        const resultHistory = existingHistory.filter(
          (result) => result.id !== resultId,
        );
        const preferredType = node.resultAssetType || getNodeResultType(node);
        const preferredResults = resultHistory.filter(
          (result) => result.type === preferredType,
        );
        const activeResult = preferredResults[0] || resultHistory[0];
        const activeType = activeResult?.type || preferredType;
        const activeResults = resultHistory.filter(
          (result) => result.type === activeType,
        );

        if (
          removedResult?.url.startsWith('blob:') &&
          !resultHistory.some((result) => result.url === removedResult.url)
        ) {
          URL.revokeObjectURL(removedResult.url);
        }

        return {
          ...node,
          resultUrl: activeResult?.url,
          resultUrls:
            activeResults.length > 0
              ? activeResults.map((result) => result.url)
              : undefined,
          resultHistory: resultHistory.length > 0 ? resultHistory : undefined,
          resultAssetType: activeResult?.type,
          mediaAspectRatio: undefined,
          mediaDisplayScale: undefined,
          status: resultHistory.length > 0 ? 'ready' : 'draft',
        };
      }),
    );
    setToast('已移除所选生成结果');
  }, []);

  const clearNodeError = useCallback((nodeId: string) => {
    setNodeErrors((current) => {
      if (!current[nodeId]) return current;
      const next = { ...current };
      delete next[nodeId];
      return next;
    });
  }, []);

  const applyImportedAsset = useCallback(
    async (nodeId: string, asset: UploadedAsset, source: 'local' | 'cloud') => {
      if (
        asset.type !== AssetType.IMAGE &&
        asset.type !== AssetType.VIDEO &&
        asset.type !== AssetType.AUDIO &&
        asset.type !== AssetType.FILE &&
        asset.type !== AssetType.TEXT
      ) {
        setToast('画布素材节点支持图片、视频、音频和文档');
        return false;
      }

      const resultType: CanvasNodeData['assetType'] =
        asset.type === AssetType.VIDEO
          ? 'video'
          : asset.type === AssetType.AUDIO
            ? 'audio'
            : asset.type === AssetType.FILE || asset.type === AssetType.TEXT
              ? 'file'
              : 'image';
      const stableAssetUrl = getStableCanvasMediaUrl(
        asset.url,
        resultType,
        asset.name,
      );
      clearNodeError(nodeId);
      const hasTransparentBackground =
        resultType === 'image' && asset.file
          ? await imageBlobHasTransparency(asset.file)
          : false;
      updateNode(nodeId, {
        assetType: resultType,
        assetName: asset.name,
        assetStorageKey: asset.storageKey,
        assetSource: source,
        officialAssetEnabled: false,
        officialAssetId: undefined,
        officialAssetStatus: 'idle',
        officialAssetError: undefined,
        hasTransparentBackground,
        resultUrl: stableAssetUrl,
        resultUrls: [stableAssetUrl],
        resultHistory: [
          {
            id: createId('result'),
            url: stableAssetUrl,
            type: resultType,
            storageKey: asset.storageKey,
            createdAt: new Date().toISOString(),
          },
        ],
        mediaAspectRatio: undefined,
        mediaDisplayScale: undefined,
        status: 'ready',
      });
      setSelectedNodeId(nodeId);
      setToast(
        source === 'local'
          ? asset.url.startsWith('blob:')
            ? '本地素材已导入；云端上传失败，本次打开期间可用'
            : '本地素材导入成功'
          : '云素材导入成功',
      );
      return true;
    },
    [clearNodeError, updateNode],
  );

  const applyWebpageLinkToAsset = useCallback(
    (nodeId: string, rawUrl: string) => {
      const url = rawUrl.trim();
      if (!isPublicHttpUrl(url)) {
        setToast('请输入公开的 http(s) 网页链接');
        return false;
      }
      let hostname = url;
      try {
        hostname = new URL(url).hostname;
      } catch {
        hostname = url;
      }
      clearNodeError(nodeId);
      const createdAt = new Date().toISOString();
      updateNode(nodeId, {
        assetType: 'link',
        assetName: hostname,
        assetStorageKey: undefined,
        assetSource: 'local',
        officialAssetEnabled: false,
        officialAssetId: undefined,
        officialAssetStatus: 'idle',
        officialAssetError: undefined,
        hasTransparentBackground: false,
        resultUrl: url,
        resultUrls: [url],
        resultHistory: [
          {
            id: createId('result'),
            url,
            type: 'link',
            createdAt,
          },
        ],
        mediaAspectRatio: undefined,
        mediaDisplayScale: undefined,
        status: 'ready',
      });
      setWebpageLinkDraft(url);
      setSelectedNodeId(nodeId);
      setToast('网页链接已作为参考素材');
      return true;
    },
    [clearNodeError, updateNode],
  );

  const applyDroppedMediaToNode = useCallback(
    async (node: CanvasNodeData, asset: UploadedAsset) => {
      if (node.kind === 'asset') {
        await applyImportedAsset(node.id, asset, 'local');
        setToast(`已替换“${node.title}”的素材`);
        return;
      }

      const mediaType =
        asset.type === AssetType.VIDEO
          ? 'video'
          : asset.type === AssetType.AUDIO
            ? 'audio'
            : 'image';
      const mediaUrl = getStableCanvasMediaUrl(
        asset.url,
        mediaType,
        asset.name,
      );
      const hasTransparentBackground =
        mediaType === 'image' && asset.file
          ? await imageBlobHasTransparency(asset.file)
          : false;
      appendNodeResults(node.id, [mediaUrl], mediaType);
      updateNode(node.id, {
        hasTransparentBackground,
        ...(node.kind === 'text'
          ? { textGenerationMode: mediaType === 'video' ? 'video' : 'image' }
          : {}),
      });
      setSelectedNodeId(node.id);
      setSelectedNodeIds(new Set([node.id]));
      setToast(
        `已替换“${node.title}”的${mediaType === 'video' ? '视频' : mediaType === 'audio' ? '音频' : '图片'}`,
      );
    },
    [appendNodeResults, applyImportedAsset, updateNode],
  );

  const openLocalAssetPicker = (nodeId: string) => {
    setLocalAssetNodeId(nodeId);
    assetInputRef.current?.click();
  };

  const handleLocalAssetImport = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    const nodeId = localAssetNodeId;
    if (!file || !nodeId) return;
    if (!getFileMediaType(file)) {
      setToast(
        `请选择图片、视频、音频（mp3/wav）或文档（${WAN3_REFERENCE_FILE_EXTENSIONS.join('、')}）`,
      );
      return;
    }

    setIsImportingAsset(true);
    try {
      const asset = await uploadToStorage(file);
      await applyImportedAsset(nodeId, asset, 'local');
    } catch (error) {
      setToast(
        error instanceof Error
          ? `导入失败：${error.message}`
          : '本地素材导入失败',
      );
    } finally {
      setIsImportingAsset(false);
      setLocalAssetNodeId(null);
    }
  };

  const importCanvasImages = useCallback(
    async (
      mediaFiles: File[],
      position: { x: number; y: number },
      source: 'drop' | 'paste',
      ignoredCount = 0,
    ) => {
      if (isImportingCanvasImagesRef.current) {
        setToast('素材正在导入，请稍候');
        return;
      }
      if (mediaFiles.length === 0) return;

      isImportingCanvasImagesRef.current = true;
      setNodeMenu(null);
      setShortcutsOpen(false);
      setDroppedImageCount(mediaFiles.length);
      setIsDroppingImages(true);

      try {
        const uploadResults = await Promise.all(
          mediaFiles.map(async (file) => {
            try {
              return { file, asset: await uploadToStorage(file) };
            } catch (error) {
              console.error(
                `[Canvas] ${source === 'paste' ? '粘贴' : '拖入'}素材失败:`,
                error,
              );
              return { file, asset: null };
            }
          }),
        );
        const successfulUploads = uploadResults.filter(
          (result) => result.asset,
        );
        const createdAt = new Date().toISOString();
        const importedNodes = await Promise.all(
          successfulUploads.map(
            async ({ file, asset }, index): Promise<CanvasNodeData> => {
              const mediaType = getFileMediaType(file) || 'image';
              const stableAssetUrl = getStableCanvasMediaUrl(
                asset!.url,
                mediaType,
                file.name,
              );
              const hasTransparentBackground =
                mediaType === 'image'
                  ? await imageBlobHasTransparency(file)
                  : false;
              return {
                id: createId('node'),
                kind: 'asset',
                title:
                  file.name.replace(/\.[^.]+$/, '') ||
                  NODE_META.asset.defaultTitle,
                x: position.x + (index % 3) * (NODE_WIDTH + 24),
                y: position.y + Math.floor(index / 3) * (NODE_HEIGHT + 24),
                prompt: '',
                assetType: mediaType,
                assetName: file.name,
                assetStorageKey: asset!.storageKey,
                assetSource: 'local',
                resultAssetType: mediaType,
                hasTransparentBackground,
                resultUrl: stableAssetUrl,
                resultUrls: [stableAssetUrl],
                resultHistory: [
                  {
                    id: createId('result'),
                    url: stableAssetUrl,
                    type: mediaType,
                    storageKey: asset!.storageKey,
                    createdAt,
                  },
                ],
                status: 'ready',
              };
            },
          ),
        );

        if (importedNodes.length > 0) {
          setNodes((current) => [...current, ...importedNodes]);
          const lastImportedNode = importedNodes[importedNodes.length - 1];
          if (lastImportedNode) setSelectedNodeId(lastImportedNode.id);
        }

        const failedCount = mediaFiles.length - importedNodes.length;
        if (importedNodes.length === 0) {
          setToast('素材导入失败，请稍后重试');
        } else if (ignoredCount > 0 || failedCount > 0) {
          setToast(
            `已导入 ${importedNodes.length} 个素材，忽略或失败 ${ignoredCount + failedCount} 个文件`,
          );
        } else {
          setToast(
            source === 'paste'
              ? `已粘贴 ${importedNodes.length} 个素材`
              : `已将 ${importedNodes.length} 个素材拖入画布`,
          );
        }
      } finally {
        isImportingCanvasImagesRef.current = false;
        setIsDroppingImages(false);
        setDroppedImageCount(0);
      }
    },
    [],
  );

  const resetFileDragState = () => {
    fileDragDepthRef.current = 0;
    setIsFileDragActive(false);
    setFileDropTargetNodeId(null);
    setFileDropTargetRejected(false);
  };

  const handleCanvasDragEnter = (event: React.DragEvent<HTMLDivElement>) => {
    if (!Array.from(event.dataTransfer.types).includes('Files')) return;
    event.preventDefault();
    event.stopPropagation();
    fileDragDepthRef.current += 1;
    setIsFileDragActive(true);
  };

  const handleCanvasDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    if (!Array.from(event.dataTransfer.types).includes('Files')) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'copy';
    const hoverNode = findNodeAtClientPoint(event.clientX, event.clientY);
    if (!hoverNode) {
      if (fileDropTargetNodeId) setFileDropTargetNodeId(null);
      if (fileDropTargetRejected) setFileDropTargetRejected(false);
      return;
    }
    const hoverMediaTypes = Array.from(event.dataTransfer.items)
      .filter((item) => item.kind === 'file')
      .map((item) => item.type);
    const accepted = getNodeAcceptedMediaType(hoverNode);
    const rejected =
      accepted === null ||
      (hoverMediaTypes.length > 0 &&
        !hoverMediaTypes.some((type) => {
          if (type.startsWith('image/'))
            return nodeAcceptsMediaType(hoverNode, 'image');
          if (type.startsWith('video/'))
            return nodeAcceptsMediaType(hoverNode, 'video');
          return false;
        }));
    if (fileDropTargetNodeId !== hoverNode.id)
      setFileDropTargetNodeId(hoverNode.id);
    if (fileDropTargetRejected !== rejected)
      setFileDropTargetRejected(rejected);
  };

  const handleCanvasDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    if (fileDragDepthRef.current === 0) return;
    event.preventDefault();
    event.stopPropagation();
    fileDragDepthRef.current = Math.max(0, fileDragDepthRef.current - 1);
    if (fileDragDepthRef.current === 0) resetFileDragState();
  };

  const handleCanvasImageDrop = async (
    event: React.DragEvent<HTMLDivElement>,
  ) => {
    if (!Array.from(event.dataTransfer.types).includes('Files')) return;
    event.preventDefault();
    event.stopPropagation();
    const targetNode = findNodeAtClientPoint(event.clientX, event.clientY);
    resetFileDragState();

    const droppedFiles = Array.from(event.dataTransfer.files);
    if (droppedFiles.length === 0) return;

    if (targetNode) {
      if (replaceMediaConfirm) {
        setToast('请先处理当前的替换确认');
        return;
      }
      if (generatingNodeIds.has(targetNode.id)) {
        setToast('该节点正在生成，请稍后再替换素材');
        return;
      }
      const acceptedType = getNodeAcceptedMediaType(targetNode);
      if (!acceptedType) {
        setToast('该节点不支持拖入替换素材');
        return;
      }
      const matchedFile = droppedFiles.find((file) => {
        const mediaType = getFileMediaType(file);
        return mediaType ? nodeAcceptsMediaType(targetNode, mediaType) : false;
      });
      if (!matchedFile) {
        setToast(
          acceptedType === 'all'
            ? '请将图片、视频、音频或文档拖到该素材节点上'
            : acceptedType === 'video'
              ? '请将视频文件拖到该节点上'
              : acceptedType === 'audio'
                ? '请将音频文件拖到该节点上'
                : acceptedType === 'file'
                  ? '请将文档文件拖到该节点上'
                  : '请将图片文件拖到该节点上',
        );
        return;
      }

      setIsDroppingImages(true);
      setDroppedImageCount(1);
      try {
        const asset = await uploadToStorage(matchedFile);
        const importType = getFileMediaType(matchedFile);
        if (
          nodeHasGeneratedMedia(targetNode) &&
          (importType === 'image' || importType === 'video')
        ) {
          setReplaceMediaConfirm({
            nodeId: targetNode.id,
            asset,
            mediaType: importType,
          });
          setSelectedNodeId(targetNode.id);
          setSelectedNodeIds(new Set([targetNode.id]));
        } else {
          await applyDroppedMediaToNode(targetNode, asset);
        }
      } catch (error) {
        setToast(
          error instanceof Error
            ? `替换失败：${error.message}`
            : '替换素材失败',
        );
      } finally {
        setIsDroppingImages(false);
        setDroppedImageCount(0);
      }
      return;
    }

    const importableFiles = droppedFiles.filter((file) => {
      const mediaType = getFileMediaType(file);
      return (
        mediaType === 'image' ||
        mediaType === 'video' ||
        mediaType === 'audio' ||
        mediaType === 'file'
      );
    });
    if (importableFiles.length === 0) {
      setToast('仅支持将图片、视频、音频或文档拖入画布');
      return;
    }

    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const dropPosition = {
      x: Math.round(
        (event.clientX - rect.left - viewport.x) / viewport.zoom -
          NODE_WIDTH / 2,
      ),
      y: Math.round(
        (event.clientY - rect.top - viewport.y) / viewport.zoom -
          NODE_HEIGHT / 2,
      ),
    };

    await importCanvasImages(
      importableFiles,
      dropPosition,
      'drop',
      droppedFiles.length - importableFiles.length,
    );
  };

  const clearImportedAsset = (nodeId: string) => {
    clearNodeError(nodeId);
    updateNode(nodeId, {
      assetName: undefined,
      assetStorageKey: undefined,
      assetSource: undefined,
      officialAssetEnabled: false,
      officialAssetId: undefined,
      officialAssetStatus: 'idle',
      officialAssetError: undefined,
      resultUrl: undefined,
      resultUrls: undefined,
      resultHistory: undefined,
      mediaAspectRatio: undefined,
      mediaDisplayScale: undefined,
      status: 'draft',
    });
    setToast('已移除当前素材');
  };

  const officialAssetUriOf = (node: CanvasNodeData) =>
    OFFICIAL_ASSET_LIBRARY_ENABLED &&
    node.officialAssetEnabled &&
    node.officialAssetStatus === 'active' &&
    node.officialAssetId
      ? `asset://${node.officialAssetId}`
      : undefined;

  const toggleOfficialAsset = async (nodeId: string, enabled: boolean) => {
    if (!OFFICIAL_ASSET_LIBRARY_ENABLED) return;
    const node = nodes.find((item) => item.id === nodeId);
    const mediaUrl = node?.resultUrl;
    if (!node || !mediaUrl) {
      setToast('请先导入素材再登记到官方素材库');
      return;
    }
    if (!enabled) {
      updateNode(nodeId, { officialAssetEnabled: false });
      setToast('已取消使用官方素材库，生成时仍走普通参考图');
      return;
    }
    updateNode(nodeId, {
      officialAssetEnabled: true,
      officialAssetStatus: 'uploading',
      officialAssetError: undefined,
    });
    try {
      const result = await registerByteplusAsset({
        url: mediaUrl,
        assetType:
          node.assetType === 'video' || node.kind === 'video'
            ? 'video'
            : 'image',
        name: node.assetName || node.title,
      });
      updateNode(nodeId, {
        officialAssetEnabled: true,
        officialAssetId: result.id,
        officialAssetStatus: 'active',
        officialAssetError: undefined,
      });
      setToast(`已入库官方素材库（${result.used}/${result.limit}）`);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : '官方素材入库失败';
      updateNode(nodeId, {
        officialAssetEnabled: false,
        officialAssetStatus: 'failed',
        officialAssetError: message,
      });
      setToast(message);
    }
  };

  const getCanvasCenter = () => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return { x: 160, y: 160 };
    return {
      x: Math.round(
        (rect.width / 2 - viewport.x) / viewport.zoom - NODE_WIDTH / 2,
      ),
      y: Math.round(
        (rect.height / 2 - viewport.y) / viewport.zoom - NODE_HEIGHT / 2,
      ),
    };
  };

  const addNode = (
    kind: CanvasNodeKind,
    position?: { x: number; y: number },
    overrides?: Partial<Omit<CanvasNodeData, 'id' | 'kind' | 'x' | 'y'>>,
  ) => {
    const meta = getNodeMeta(kind);
    const center = position || getCanvasCenter();
    const offset = position ? 0 : (nodes.length % 5) * 18;
    const connectionSourceIds =
      pendingSourceIds.length > 0
        ? pendingSourceIds
        : pendingSourceId
          ? [pendingSourceId]
          : [];
    const connectionSources = connectionSourceIds
      .map((sourceId) =>
        nodes.find((existingNode) => existingNode.id === sourceId),
      )
      .filter((existingNode): existingNode is CanvasNodeData =>
        Boolean(existingNode && canConnect(existingNode.kind, kind)),
      );
    const shouldConnect = connectionSources.length > 0;
    const rememberedImage = lastGenerationSettingsRef.current.image || {};
    const rememberedImageModel = availableImageModels.includes(
      rememberedImage.model || '',
    )
      ? rememberedImage.model!
      : defaultImageModel;
    const rememberedImageModelConfig =
      mediaModelCatalog[rememberedImageModel] || {};
    const rememberedImageRatios: string[] =
      rememberedImageModelConfig.supported_aspect_ratios || IMAGE_ASPECT_RATIOS;
    const rememberedImageResolutions: string[] =
      rememberedImageModelConfig.supported_resolutions || [
        imageFeatureConfig.default_resolution || '1K',
      ];
    const rememberedVideo = lastGenerationSettingsRef.current.video || {};
    const candidateVideoModels =
      kind === 'text' ? availableTextVideoModels : availableVideoModels;
    const rememberedVideoModel = candidateVideoModels.includes(
      rememberedVideo.model || '',
    )
      ? rememberedVideo.model!
      : kind === 'text'
        ? defaultTextVideoModel
        : defaultVideoModel;
    const rememberedVideoModelConfig =
      mediaModelCatalog[rememberedVideoModel] || {};
    const rememberedVideoRatios: string[] =
      rememberedVideoModelConfig.supported_aspect_ratios || VIDEO_ASPECT_RATIOS;
    const rememberedVideoResolutions: string[] =
      rememberedVideoModelConfig.supported_resolutions || [
        videoFeatureConfig.default_resolution || '720p',
      ];
    const rememberedVideoDurationRange: number[] =
      rememberedVideoModelConfig.duration_range_seconds || [2, 15];
    const rememberedVideoDuration = clamp(
      Number(rememberedVideo.duration) ||
        Number(rememberedVideoModelConfig.default_duration_seconds || 5),
      Number(rememberedVideoDurationRange[0] || 2),
      Number(rememberedVideoDurationRange[1] || 15),
    );
    const rememberedImageCount = clampBatchCount(
      rememberedImage.count,
      maxImageBatchCount,
    );
    const rememberedVideoCount = clampBatchCount(
      rememberedVideo.count,
      maxVideoBatchCount,
    );
    const node: CanvasNodeData = {
      id: createId('node'),
      kind,
      title: meta.defaultTitle,
      x: center.x + offset,
      y: center.y + offset,
      prompt: '',
      textGenerationMode: kind === 'text' ? 'image' : undefined,
      textImageConfig:
        kind === 'text'
          ? {
              model: rememberedImageModel,
              count: rememberedImageCount,
              aspectRatio: rememberedImageRatios.includes(
                rememberedImage.aspectRatio || '',
              )
                ? rememberedImage.aspectRatio
                : rememberedImageRatios[0],
              resolution: rememberedImageResolutions.includes(
                rememberedImage.resolution || '',
              )
                ? rememberedImage.resolution
                : rememberedImageResolutions[0],
            }
          : undefined,
      textVideoConfig:
        kind === 'text'
          ? {
              model: rememberedVideoModel,
              count: rememberedVideoCount,
              aspectRatio: rememberedVideoRatios.includes(
                rememberedVideo.aspectRatio || '',
              )
                ? rememberedVideo.aspectRatio
                : rememberedVideoRatios[0],
              resolution: rememberedVideoResolutions.includes(
                rememberedVideo.resolution || '',
              )
                ? rememberedVideo.resolution
                : rememberedVideoResolutions[0],
              duration: rememberedVideoDuration,
              extensionCount: 0,
              videoGenerationMode: 'text_to_video',
            }
          : undefined,
      model:
        kind === 'image' || kind === 'text'
          ? rememberedImageModel
          : kind === 'video'
            ? rememberedVideoModel
            : kind === 'video_analysis'
              ? DEFAULT_VIDEO_ANALYSIS_MODEL
              : kind === 'music'
                ? defaultMusicModel
                : kind === 'tts'
                  ? defaultTTSModel
                  : meta.defaultModel,
      count:
        kind === 'image' || kind === 'text'
          ? rememberedImageCount
          : kind === 'video'
            ? rememberedVideoCount
            : ['music', 'tts'].includes(kind)
              ? 1
              : undefined,
      aspectRatio:
        kind === 'image' || kind === 'text'
          ? rememberedImageRatios.includes(rememberedImage.aspectRatio || '')
            ? rememberedImage.aspectRatio
            : rememberedImageRatios[0]
          : kind === 'video'
            ? rememberedVideoRatios.includes(rememberedVideo.aspectRatio || '')
              ? rememberedVideo.aspectRatio
              : rememberedVideoRatios[0]
            : undefined,
      resolution:
        kind === 'image' || kind === 'text'
          ? rememberedImageResolutions.includes(
              rememberedImage.resolution || '',
            )
            ? rememberedImage.resolution
            : rememberedImageResolutions[0]
          : kind === 'video'
            ? rememberedVideoResolutions.includes(
                rememberedVideo.resolution || '',
              )
              ? rememberedVideo.resolution
              : rememberedVideoResolutions[0]
            : undefined,
      imageGenerationMode: kind === 'image' ? 'reference_image' : undefined,
      duration: kind === 'video' ? rememberedVideoDuration : undefined,
      extensionCount: kind === 'video' ? 0 : undefined,
      videoGenerationMode: kind === 'video' ? 'first_frame' : undefined,
      voiceName: kind === 'tts' ? defaultTTSVoice : undefined,
      voiceStyle: kind === 'tts' ? '' : undefined,
      speechRate: kind === 'tts' ? 'normal' : undefined,
      assetType: kind === 'asset' ? 'image' : undefined,
      status: 'draft',
      ...overrides,
    };
    setNodes((current) => [...current, node]);
    if (shouldConnect) {
      setEdges((current) => [
        ...current,
        ...connectionSources.map((source) => ({
          id: createId('edge'),
          source: source.id,
          target: node.id,
        })),
      ]);
    }
    setSelectedNodeId(node.id);
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setConnectionOrigin(null);
    setConnectionPointer(null);
    setNodeMenu(null);
    setContextMenu(null);
    setToast(
      shouldConnect
        ? connectionSources.length > 1
          ? `已创建${meta.label}节点，并连上 ${connectionSources.length} 个素材`
          : `已创建并连接${meta.label}节点`
        : `已添加${meta.label}节点`,
    );
    return node.id;
  };

  const restoreHistoryRecord = (restoreData: HistoryRestoreData) => {
    const firstAsset = restoreData.generatedAssets.find((asset) =>
      Boolean(asset.url),
    );
    const resultType: CanvasNodeResult['type'] = firstAsset
      ? (firstAsset.type || '').toUpperCase() === 'VIDEO'
        ? 'video'
        : (firstAsset.type || '').toUpperCase() === 'AUDIO'
          ? 'audio'
          : 'image'
      : restoreData.generationType === 'music_generation' ||
          restoreData.generationType === 'tts_generation'
        ? 'audio'
        : restoreData.generationType.includes('video')
          ? 'video'
          : 'image';
    const kind: CanvasNodeKind =
      restoreData.generationType === 'music_generation'
        ? 'music'
        : restoreData.generationType === 'tts_generation'
          ? 'tts'
          : resultType === 'video'
            ? 'video'
            : 'text';
    const resultHistory: CanvasNodeResult[] = restoreData.generatedAssets
      .filter((asset) => Boolean(asset.url))
      .map((asset, index) => ({
        id: `history-${restoreData.sessionId}-${index}`,
        url: getStableCanvasMediaUrl(asset.url, resultType, asset.name),
        type: resultType,
        createdAt: new Date().toISOString(),
      }));

    addNode(kind, undefined, {
      title: generationTypeLabel(restoreData.generationType),
      prompt: restoreData.prompt,
      textGenerationMode:
        kind === 'text'
          ? resultType === 'video'
            ? 'video'
            : 'image'
          : undefined,
      resultAssetType: resultHistory.length > 0 ? resultType : undefined,
      resultUrl: resultHistory[0]?.url,
      resultUrls: resultHistory.map((result) => result.url),
      resultHistory: resultHistory.length > 0 ? resultHistory : undefined,
      status: resultHistory.length > 0 ? 'ready' : 'draft',
    });
    setHistoryPageOpen(false);
    setToast('已从生成历史恢复到画布');
  };

  const openNodeMenuAtPoint = (clientX: number, clientY: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    setShortcutsOpen(false);
    setContextMenu(null);
    setNodeMenu({
      left: clamp(localX + 10, 12, Math.max(12, rect.width - 316)),
      top: clamp(localY + 10, 12, Math.max(12, rect.height - 516)),
      nodePosition: {
        x: Math.round((localX - viewport.x) / viewport.zoom - NODE_WIDTH / 2),
        y: Math.round((localY - viewport.y) / viewport.zoom - NODE_HEIGHT / 2),
      },
    });
  };

  const openCenteredNodeMenu = () => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    setShortcutsOpen(false);
    setContextMenu(null);
    setNodeMenu({
      left: clamp(rect.width / 2 - 152, 12, Math.max(12, rect.width - 316)),
      top: Math.max(12, rect.height - 548),
      nodePosition: getCanvasCenter(),
    });
  };

  const openNodeMenuAtCursor = () => {
    const pointer = lastCanvasPointerRef.current;
    const rect = canvasRef.current?.getBoundingClientRect();
    const isInsideCanvas = Boolean(
      pointer &&
        rect &&
        pointer.clientX >= rect.left &&
        pointer.clientX <= rect.right &&
        pointer.clientY >= rect.top &&
        pointer.clientY <= rect.bottom,
    );
    if (pointer && isInsideCanvas) {
      openNodeMenuAtPoint(pointer.clientX, pointer.clientY);
      return;
    }
    openCenteredNodeMenu();
  };

  const addConnectedGenerationNode = (
    sourceId: string,
    kind: 'image' | 'video',
    settings: Partial<
      Pick<
        CanvasNodeData,
        | 'model'
        | 'aspectRatio'
        | 'resolution'
        | 'duration'
        | 'extensionCount'
        | 'prompt'
        | 'title'
      >
    > = {},
  ) => {
    const sourceNode = nodes.find((node) => node.id === sourceId);
    if (!sourceNode || !canConnect(sourceNode.kind, kind)) return;

    const outgoingCount = edges.filter(
      (edge) => edge.source === sourceId,
    ).length;
    const sourceDimensions = getCanvasNodeDimensions(sourceNode);
    const availableModels =
      kind === 'image' ? availableImageModels : availableVideoModels;
    const fallbackModel =
      kind === 'image' ? defaultImageModel : defaultVideoModel;
    const rememberedSettings: Partial<CanvasGenerationConfig> =
      lastGenerationSettingsRef.current[kind] || {};
    const preferredModel = settings.model || rememberedSettings.model;
    const model = availableModels.includes(preferredModel || '')
      ? preferredModel!
      : fallbackModel;
    const modelConfig = mediaModelCatalog[model] || {};
    const supportedResolutions: string[] =
      modelConfig.supported_resolutions || [
        kind === 'image'
          ? imageFeatureConfig.default_resolution || '1K'
          : videoFeatureConfig.default_resolution || '720p',
      ];
    const supportedRatios: string[] =
      kind === 'video'
        ? modelConfig.supported_aspect_ratios || VIDEO_ASPECT_RATIOS
        : modelConfig.supported_aspect_ratios || IMAGE_ASPECT_RATIOS;
    const node: CanvasNodeData = {
      id: createId('node'),
      kind,
      title: settings.title || getNodeMeta(kind).defaultTitle,
      x: sourceNode.x + sourceDimensions.width + 74,
      y: sourceNode.y + outgoingCount * 72,
      prompt: settings.prompt || '',
      model,
      count: clampBatchCount(
        rememberedSettings.count,
        kind === 'image' ? maxImageBatchCount : maxVideoBatchCount,
      ),
      aspectRatio: supportedRatios.includes(
        settings.aspectRatio || rememberedSettings.aspectRatio || '',
      )
        ? settings.aspectRatio || rememberedSettings.aspectRatio
        : supportedRatios[0],
      resolution: supportedResolutions.includes(
        settings.resolution || rememberedSettings.resolution || '',
      )
        ? settings.resolution || rememberedSettings.resolution
        : supportedResolutions[0],
      duration:
        kind === 'video'
          ? Number(
              settings.duration ||
                rememberedSettings.duration ||
                modelConfig.default_duration_seconds ||
                5,
            )
          : undefined,
      extensionCount:
        kind === 'video' ? Number(settings.extensionCount) || 0 : undefined,
      status: 'draft',
    };
    setNodes((current) => [...current, node]);
    setEdges((current) => [
      ...current,
      {
        id: createId('edge'),
        source: sourceId,
        target: node.id,
      },
    ]);
    setSelectedNodeId(node.id);
    setToast(`已创建并连接${getNodeMeta(kind).label}节点`);
    return node.id;
  };

  const runImageAiCommandOnNode = (
    sourceNode: CanvasNodeData,
    command: CanvasQuickImageCommand,
  ) => {
    if (
      !canConnect(sourceNode.kind, 'image') ||
      getNodeResultUrls(sourceNode, 'image').length === 0
    ) {
      setToast('当前节点没有可处理的图片');
      return;
    }
    const usesSquareLayout = [
      'nine-grid-storyboard',
      'character-sheet',
      'product-sheet',
    ].includes(command.id);
    const usesWidescreenLayout = command.id === 'multi-angle';
    const nodeId = addConnectedGenerationNode(sourceNode.id, 'image', {
      title: command.label,
      prompt: command.prompt,
      aspectRatio: usesSquareLayout
        ? '1:1'
        : usesWidescreenLayout
          ? '16:9'
          : sourceNode.aspectRatio || '16:9',
      resolution:
        sourceNode.resolution || imageFeatureConfig.default_resolution || '1K',
    });
    if (!nodeId) return;

    setPendingQuickGeneration({ nodeId, commandLabel: command.label });
    setQuickCommandsOpen(false);
    setContextMenu(null);
    setImageAiTool(null);
    setToast(`已应用“${command.label}”，AI 正在修改图片`);
  };

  const runQuickImageCommand = (command: CanvasQuickImageCommand) => {
    if (!quickCommandSourceNode) {
      setToast('请先右键一张已生成或已导入的图片');
      return;
    }
    runImageAiCommandOnNode(quickCommandSourceNode, command);
  };

  const closeImageAiTool = () => setImageAiTool(null);

  const applyCroppedImage = async (nodeId: string, file: File) => {
    const asset = await uploadToStorage(file);
    appendNodeResults(
      nodeId,
      [getStableCanvasMediaUrl(asset.url, 'image')],
      'image',
    );
    setImageAiTool(null);
    setToast('已裁剪图片');
  };

  const applyErasedImage = async (nodeId: string, maskDataUrl: string) => {
    const node = nodes.find((item) => item.id === nodeId);
    const imageUrl = node
      ? getNodeResultUrls(node, 'image')[0] || node.resultUrl
      : undefined;
    if (!node || !imageUrl) {
      setToast('当前节点没有可处理的图片');
      return;
    }
    const maskBase64 = maskDataUrl.includes(',')
      ? maskDataUrl.split(',')[1]
      : maskDataUrl;
    if (!maskBase64) {
      setToast('请先涂抹要去掉的区域');
      return;
    }

    setGeneratingNodeIds((current) => new Set(current).add(nodeId));
    try {
      const originalAsset = await createFileBackedAsset(
        imageUrl,
        AssetType.IMAGE,
        0,
      );
      const result = await editImageWithMask(
        originalAsset,
        maskBase64,
        ERASE_OBJECT_PROMPT,
        undefined,
        defaultImageModel,
      );
      if (!result.url) throw new Error('去图未返回可用图片');
      const sourceDimensions = getCanvasNodeDimensions(node);
      const outgoingCount = edges.filter(
        (edge) => edge.source === nodeId,
      ).length;
      const resultNodeId = createId('node');
      const createdAt = new Date().toISOString();
      const resultUrl = getStableCanvasMediaUrl(result.url, 'image');
      const resultNode: CanvasNodeData = {
        id: resultNodeId,
        kind: 'image',
        title: '去图',
        x: node.x + sourceDimensions.width + 74,
        y: node.y + outgoingCount * 72,
        prompt: '去除涂抹区域中的物体，并自然补全背景。',
        model: defaultImageModel,
        count: 1,
        aspectRatio: node.aspectRatio || '16:9',
        resolution:
          node.resolution || imageFeatureConfig.default_resolution || '1K',
        imageGenerationMode: 'reference_image',
        resultUrl,
        resultUrls: [resultUrl],
        resultAssetType: 'image',
        resultHistory: [
          {
            id: createId('result'),
            url: resultUrl,
            type: 'image',
            createdAt,
          },
        ],
        status: 'ready',
      };
      setNodes((current) => [...current, resultNode]);
      setEdges((current) => [
        ...current,
        {
          id: createId('edge'),
          source: nodeId,
          target: resultNodeId,
        },
      ]);
      setSelectedNodeId(resultNodeId);
      setSelectedNodeIds(new Set([resultNodeId]));
      setImageAiTool(null);
      void saveEditImageRecord(
        { url: imageUrl, type: 'IMAGE', name: node.assetName || node.title },
        ERASE_OBJECT_PROMPT,
        [{ url: resultUrl, type: 'IMAGE', name: '去图' }],
      );
      setToast('去图完成');
    } finally {
      setGeneratingNodeIds((current) => {
        const next = new Set(current);
        next.delete(nodeId);
        return next;
      });
    }
  };

  const generateSmartMatte = async (
    nodeId: string,
    hintMaskDataUrl: string,
  ) => {
    const node = nodes.find((item) => item.id === nodeId);
    const imageUrl = node
      ? getNodeResultUrls(node, 'image')[0] || node.resultUrl
      : undefined;
    if (!node || !imageUrl) {
      throw new Error('当前节点没有可处理的图片');
    }
    const maskBase64 = hintMaskDataUrl.includes(',')
      ? hintMaskDataUrl.split(',')[1]
      : hintMaskDataUrl;
    if (!maskBase64) {
      throw new Error('请先点击或框选要抠出的主体');
    }
    const originalAsset = await createFileBackedAsset(
      imageUrl,
      AssetType.IMAGE,
      0,
    );
    if (!availableImageModels.includes(SMART_MATTING_MODEL)) {
      throw new Error('当前环境未启用 gpt-image-2，无法使用智能抠图');
    }
    const model = SMART_MATTING_MODEL;
    const supportedResolutions = mediaModelCatalog[model]
      ?.supported_resolutions || ['1K'];
    const imageSize = supportedResolutions.includes(node.resolution || '')
      ? (node.resolution as string)
      : supportedResolutions[0] || '1K';
    const result = await editImageWithMask(
      originalAsset,
      maskBase64,
      SMART_MATTING_PROMPT,
      undefined,
      model,
      imageSize,
    );
    if (!result.url) throw new Error('智能抠图未返回可用蒙版');
    return result.url;
  };

  const applySmartMatting = async (nodeId: string, file: File) => {
    const node = nodes.find((item) => item.id === nodeId);
    const imageUrl = node
      ? getNodeResultUrls(node, 'image')[0] || node.resultUrl
      : undefined;
    if (!node || !imageUrl) {
      setToast('当前节点没有可处理的图片');
      return;
    }
    const uniqueName = `canvas-smart-matting-${createId('matte')}.png`;
    const pngFile = new File([file], uniqueName, {
      type: 'image/png',
      lastModified: Date.now(),
    });
    const asset = await uploadToStorage(pngFile);
    const resultUrl = getStableCanvasMediaUrl(asset.url, 'image', uniqueName);
    const sourceDimensions = getCanvasNodeDimensions(node);
    const outgoingCount = edges.filter((edge) => edge.source === nodeId).length;
    const resultNodeId = createId('node');
    const createdAt = new Date().toISOString();
    const resultNode: CanvasNodeData = {
      id: resultNodeId,
      kind: 'image',
      title: '智能抠图',
      assetName: '智能抠图.png',
      x: node.x + sourceDimensions.width + 74,
      y: node.y + outgoingCount * 72,
      prompt: '按所选主体抠图，并保留原图像素与 PNG 透明通道。',
      model: SMART_MATTING_MODEL,
      count: 1,
      aspectRatio: node.aspectRatio || '16:9',
      resolution:
        node.resolution || imageFeatureConfig.default_resolution || '1K',
      imageGenerationMode: 'reference_image',
      hasTransparentBackground: true,
      resultUrl,
      resultUrls: [resultUrl],
      resultAssetType: 'image',
      resultHistory: [
        {
          id: createId('result'),
          url: resultUrl,
          type: 'image',
          createdAt,
        },
      ],
      status: 'ready',
    };
    setNodes((current) => [...current, resultNode]);
    setEdges((current) => [
      ...current,
      {
        id: createId('edge'),
        source: nodeId,
        target: resultNodeId,
      },
    ]);
    setSelectedNodeId(resultNodeId);
    setSelectedNodeIds(new Set([resultNodeId]));
    setImageAiTool(null);
    void saveEditImageRecord(
      { url: imageUrl, type: 'IMAGE', name: node.assetName || node.title },
      SMART_MATTING_PROMPT,
      [{ url: resultUrl, type: 'IMAGE', name: '智能抠图.png' }],
    );
    setToast('智能抠图完成');
  };

  const applyGridSplitCells = async (
    sourceNodeId: string,
    size: GridSplitSize,
    cells: GridSplitCell[],
    options?: { hd?: boolean; scale?: GridHdScale },
  ) => {
    const sourceNode = nodes.find((item) => item.id === sourceNodeId);
    const imageUrl = sourceNode
      ? getNodeResultUrls(sourceNode, 'image')[0] || sourceNode.resultUrl
      : undefined;
    if (!sourceNode || !imageUrl) {
      setToast('当前节点没有可切分的图片');
      return;
    }
    if (cells.length === 0) {
      setToast('请先选择要切分的宫格');
      return;
    }

    setGeneratingNodeIds((current) => new Set(current).add(sourceNodeId));
    try {
      const slices = await sliceImageGridCells(imageUrl, size, cells);
      const sourceDimensions = getCanvasNodeDimensions(sourceNode);
      const sourceAspect =
        sourceNode.mediaAspectRatio ||
        parseConfiguredAspectRatio(sourceNode.aspectRatio) ||
        16 / 9;
      const cellAspect = sourceAspect * (size.rows / size.cols);
      const cellSize = getNodeDimensions({
        ...sourceNode,
        mediaAspectRatio: cellAspect,
        mediaDisplayScale: 1,
      });
      const originX = sourceNode.x + sourceDimensions.width + 74;
      const originY = sourceNode.y;
      const gap = 12;
      const createdAt = new Date().toISOString();
      const hdResolution = options?.scale === 4 ? '4K' : '2K';
      const sliceNodes: CanvasNodeData[] = [];
      const hdNodes: CanvasNodeData[] = [];
      const nextEdges: CanvasEdgeData[] = [];

      for (const slice of slices) {
        const asset = await uploadToStorage(slice.file);
        const sliceId = createId('node');
        const gridLabel = cellKey(slice);
        const resultUrl = getStableCanvasMediaUrl(
          asset.url,
          'image',
          slice.file.name,
        );
        const sliceX = Math.round(originX + slice.col * (cellSize.width + gap));
        const sliceY = Math.round(
          originY + slice.row * (cellSize.height + gap),
        );
        // 切出来的图要接回原节点，同时自己也能再往下连当参考图。
        sliceNodes.push({
          id: sliceId,
          kind: 'image',
          title: `${sourceNode.title} ${gridLabel}`,
          x: sliceX,
          y: sliceY,
          prompt: '',
          model: sourceNode.model || defaultImageModel,
          count: 1,
          aspectRatio: sourceNode.aspectRatio || '16:9',
          resolution:
            sourceNode.resolution ||
            imageFeatureConfig.default_resolution ||
            '1K',
          imageGenerationMode: 'reference_image',
          resultAssetType: 'image',
          resultUrl,
          resultUrls: [resultUrl],
          resultHistory: [
            {
              id: createId('result'),
              url: resultUrl,
              type: 'image',
              createdAt,
            },
          ],
          mediaAspectRatio: cellAspect,
          gridSplitSourceNodeId: sourceNodeId,
          status: 'ready',
        });
        nextEdges.push({
          id: createId('edge'),
          source: sourceNodeId,
          target: sliceId,
        });

        if (options?.hd) {
          const hdId = createId('node');
          hdNodes.push({
            id: hdId,
            kind: 'image',
            title: `高清 ${gridLabel}`,
            x: Math.round(sliceX + cellSize.width + 74),
            y: sliceY,
            prompt:
              QUICK_IMAGE_COMMANDS.find(
                (command) => command.id === 'hd-restore',
              )?.prompt || '',
            model: sourceNode.model || defaultImageModel,
            count: 1,
            aspectRatio: sourceNode.aspectRatio || '16:9',
            resolution: hdResolution,
            imageGenerationMode: 'reference_image',
            status: 'draft',
          });
          nextEdges.push({
            id: createId('edge'),
            source: sliceId,
            target: hdId,
          });
        }
      }

      setNodes((current) => [...current, ...sliceNodes, ...hdNodes]);
      setEdges((current) => [...current, ...nextEdges]);
      const selectedIds = sliceNodes.map((node) => node.id);
      setSelectedNodeIds(new Set(selectedIds));
      setSelectedNodeId(selectedIds[0] || null);
      setSelectedEdgeId(null);
      setImageAiTool(null);
      if (hdNodes.length > 0)
        setPendingGridHdNodeIds(hdNodes.map((node) => node.id));
      setToast(
        options?.hd
          ? `已切出 ${sliceNodes.length} 张图片，正在生成高清图`
          : `已切出 ${sliceNodes.length} 张图片，并已连接到原节点`,
      );
    } catch (error) {
      setToast(error instanceof Error ? error.message : '宫格切分失败');
    } finally {
      setGeneratingNodeIds((current) => {
        const next = new Set(current);
        next.delete(sourceNodeId);
        return next;
      });
    }
  };

  const createCustomQuickImageNode = () => {
    if (!quickCommandSourceNode) {
      setToast('请先右键一张已生成或已导入的图片');
      return;
    }
    const nodeId = addConnectedGenerationNode(
      quickCommandSourceNode.id,
      'image',
      {
        title: '自定义修改',
        prompt: '',
        aspectRatio: quickCommandSourceNode.aspectRatio || '16:9',
        resolution:
          quickCommandSourceNode.resolution ||
          imageFeatureConfig.default_resolution ||
          '1K',
      },
    );
    if (!nodeId) return;

    setQuickCommandsOpen(false);
    setContextMenu(null);
    setToast('已创建自定义修改节点，请输入名称和描述后保存');
  };

  const saveImageNodeAsQuickCommand = (node: CanvasNodeData) => {
    const prompt = node.prompt.trim();
    if (!prompt) {
      setToast('请先输入快捷指令描述');
      return;
    }
    const fallbackLabel = prompt.replace(/\s+/g, ' ').slice(0, 18);
    const label = (
      node.title.trim() && node.title.trim() !== NODE_META.image.defaultTitle
        ? node.title.trim()
        : fallbackLabel || '自定义指令'
    ).slice(0, 30);
    const now = new Date().toISOString();

    setCustomImageCommands((current) => {
      const existing = current.find((command) => command.label === label);
      if (existing) {
        return current.map((command) =>
          command.id === existing.id
            ? { ...command, prompt, createdAt: now }
            : command,
        );
      }
      return [
        { id: createId('quick-command'), label, prompt, createdAt: now },
        ...current,
      ].slice(0, 30);
    });
    setToast(`“${label}”已保存到快捷指令`);
  };

  const deleteCustomImageCommand = (commandId: string, label: string) => {
    setCustomImageCommands((current) =>
      current.filter((command) => command.id !== commandId),
    );
    setToast(`已删除快捷指令“${label}”`);
  };

  const startMediaResize = (
    event: React.PointerEvent<HTMLButtonElement>,
    node: CanvasNodeData,
    corner: MediaResizeCorner,
    dimensions: { width: number; height: number },
  ) => {
    if (event.button !== 0 || toolMode === 'hand') return;
    event.preventDefault();
    event.stopPropagation();
    setSelectedNodeId(node.id);
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setConnectionPointer(null);
    setConnectionHoverTargetId(null);
    setConnectionRejectTargetId(null);
    setConnectionCursor(null);
    dragRef.current = null;
    panRef.current = null;
    connectionDragRef.current = null;
    altDuplicateDragRef.current = null;
    mediaResizeRef.current = {
      nodeId: node.id,
      corner,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startNodeX: node.x,
      startNodeY: node.y,
      startWidth: dimensions.width,
      startHeight: dimensions.height,
      startScale: clamp(
        node.mediaDisplayScale || 1,
        MIN_MEDIA_DISPLAY_SCALE,
        MAX_MEDIA_DISPLAY_SCALE,
      ),
    };
  };

  const beginAltDuplicateDrag = (
    event: React.PointerEvent,
    node: CanvasNodeData,
  ) => {
    if (!event.altKey) return false;
    event.preventDefault();
    // Windows 的 Alt、Mac 的 Option（⌥）都会把 altKey 置为 true。
    // 只按修饰键复制当前节点；再加 Shift 把当前节点并入选择后一起复制。
    const sourceIds = event.shiftKey
      ? Array.from(new Set([...selectedNodeIds, node.id]))
      : [node.id];
    setSelectedNodeIds(new Set(sourceIds));
    setSelectedNodeId(node.id);
    altDuplicateDragRef.current = {
      sourceIds,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startPositions: Object.fromEntries(
        nodes
          .filter((candidate) => sourceIds.includes(candidate.id))
          .map((candidate) => [
            candidate.id,
            { x: candidate.x, y: candidate.y },
          ]),
      ),
      committed: false,
    };
    dragRef.current = null;
    return true;
  };

  const beginSelectionFrameDrag = (
    event: React.PointerEvent,
    memberIds: string[],
  ) => {
    if (toolMode === 'hand' || event.button !== 0) return;
    if (suppressMarqueeReleaseRef.current) {
      event.stopPropagation();
      return;
    }
    event.stopPropagation();
    const idSet = new Set(memberIds);
    setSelectedNodeIds(idSet);
    setSelectedNodeId(memberIds[0] || null);
    setSelectedEdgeId(null);
    const startPositions = Object.fromEntries(
      nodes
        .filter((candidate) => idSet.has(candidate.id))
        .map((candidate) => [candidate.id, { x: candidate.x, y: candidate.y }]),
    );
    if (event.altKey) {
      event.preventDefault();
      altDuplicateDragRef.current = {
        sourceIds: memberIds,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startPositions,
        committed: false,
      };
      dragRef.current = null;
      return;
    }
    dragRef.current = {
      nodeIds: memberIds,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startPositions,
    };
  };

  const startConnection = (
    event: React.PointerEvent<HTMLButtonElement>,
    nodeId: string,
  ) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    if (pendingSourceId === nodeId && pendingSourceIds.length <= 1) {
      clearPendingConnection();
      connectionDragRef.current = null;
      return;
    }

    const sourceNode = nodes.find((node) => node.id === nodeId);
    if (!sourceNode) return;
    const sourceDimensions = getCanvasNodeDimensions(sourceNode);
    const origin = {
      x: sourceNode.x + sourceDimensions.width,
      y: sourceNode.y + sourceDimensions.height / 2,
    };
    connectionDragRef.current = {
      sourceId: nodeId,
      sourceIds: [nodeId],
      origin,
      startClientX: event.clientX,
      startClientY: event.clientY,
      moved: false,
    };
    setPendingSourceId(nodeId);
    setPendingSourceIds([nodeId]);
    setConnectionOrigin(null);
    setConnectionPointer(origin);
    setSelectedNodeId(nodeId);
  };

  /** 从分组/多选框右侧拖线，松手后把组内可连接素材一次性接到目标节点。 */
  const startGroupConnection = (
    event: React.PointerEvent<HTMLButtonElement>,
    memberIds: string[],
    origin: { x: number; y: number },
  ) => {
    if (event.button !== 0 || memberIds.length === 0) return;
    event.preventDefault();
    event.stopPropagation();
    const sourceIds = memberIds.filter((memberId) => {
      const member = nodes.find((node) => node.id === memberId);
      return Boolean(member && member.kind !== 'output');
    });
    const primarySourceId = sourceIds[0];
    if (!primarySourceId) return;
    connectionDragRef.current = {
      sourceId: primarySourceId,
      sourceIds,
      origin,
      startClientX: event.clientX,
      startClientY: event.clientY,
      moved: false,
    };
    setPendingSourceId(primarySourceId);
    setPendingSourceIds(sourceIds);
    setConnectionOrigin(origin);
    setConnectionPointer(origin);
    setSelectedNodeIds(new Set(memberIds));
    setSelectedNodeId(memberIds[0] || null);
    setSelectedEdgeId(null);
  };

  const renderGroupConnectionPort = (
    memberIds: string[],
    bounds: { left: number; top: number; width: number; height: number },
  ) => {
    const origin = {
      x: bounds.left + bounds.width,
      y: bounds.top + bounds.height / 2,
    };
    const isPendingGroup =
      pendingSourceIds.length > 1 &&
      pendingSourceIds.length === memberIds.length &&
      memberIds.every((id) => pendingSourceIds.includes(id));
    return (
      <button
        type="button"
        data-canvas-group-output="true"
        aria-label={`从分组连接 ${memberIds.length} 个素材`}
        title="拖到目标节点，组内素材将全部连上"
        onPointerDown={(event) =>
          startGroupConnection(event, memberIds, origin)
        }
        onClick={(event) => {
          if (event.detail !== 0) return;
          event.stopPropagation();
          setPendingSourceId(memberIds[0] || null);
          setPendingSourceIds(memberIds);
          setConnectionOrigin(origin);
        }}
        className={`canvas-group-output-port ${isPendingGroup ? 'is-pending' : ''}`}
      >
        <Plus size={10} className="text-white" />
      </button>
    );
  };

  const startConnectionWithKeyboard = (
    event: React.MouseEvent<HTMLButtonElement>,
    nodeId: string,
  ) => {
    if (event.detail !== 0) return;
    event.stopPropagation();
    setPendingSourceId((current) => {
      const next = current === nodeId ? null : nodeId;
      setPendingSourceIds(next ? [nodeId] : []);
      setConnectionOrigin(null);
      return next;
    });
    setConnectionPointer(null);
    setSelectedNodeId(nodeId);
  };

  const completeConnection = (event: React.MouseEvent, targetId: string) => {
    event.stopPropagation();
    const sourceIds =
      pendingSourceIds.length > 0
        ? pendingSourceIds
        : pendingSourceId
          ? [pendingSourceId]
          : [];
    if (
      sourceIds.length === 0 ||
      (sourceIds.length === 1 && sourceIds[0] === targetId)
    )
      return;
    connectManyNodes(sourceIds, targetId);
  };

  const completePointerConnection = (
    event: React.PointerEvent<HTMLButtonElement>,
    targetId: string,
  ) => {
    if (event.button !== 0) return;
    const sourceIds = connectionDragRef.current?.sourceIds?.length
      ? connectionDragRef.current.sourceIds
      : pendingSourceIds.length > 0
        ? pendingSourceIds
        : pendingSourceId
          ? [pendingSourceId]
          : [];
    if (sourceIds.length === 0) return;

    event.preventDefault();
    event.stopPropagation();
    connectionDragRef.current = null;
    setConnectionPointer(null);
    setConnectionHoverTargetId(null);
    setConnectionRejectTargetId(null);
    setConnectionCursor(null);
    connectManyNodes(sourceIds, targetId);
  };

  const handleCanvasPointerDown = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
    if (imageAiTool?.mode === 'crop' || imageAiTool?.mode === 'matting') return;
    if (event.button !== 0 && event.button !== 1) return;
    if (event.button === 0 && suppressMarqueeReleaseRef.current) {
      event.preventDefault();
      return;
    }
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setNodeMenu(null);
    setShortcutsOpen(false);
    setToolMenuOpen(false);
    const clickedInteractiveElement = (event.target as HTMLElement).closest(
      '[data-canvas-node], [data-canvas-edge], [data-canvas-selection-group], [data-canvas-node-group], [data-canvas-group-output], [data-canvas-selection-toolbar], [data-canvas-grid-split-toolbar], [data-canvas-grid-split-overlay], [data-canvas-image-ai-toolbar], [data-canvas-image-matting], [data-canvas-matting-dialog], [data-canvas-crop-dialog], button, input, textarea, select, [contenteditable="true"]',
    );
    if (
      event.button === 0 &&
      toolMode === 'select' &&
      !clickedInteractiveElement
    ) {
      if (imageAiTool?.mode === 'grid-split') {
        setImageAiTool(null);
        if (!event.shiftKey) {
          setSelectedNodeId(null);
          setSelectedNodeIds(new Set());
          setSelectedEdgeId(null);
        }
        return;
      }
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;
      const localX = event.clientX - rect.left;
      const localY = event.clientY - rect.top;
      const baseNodeIds = event.shiftKey
        ? new Set(selectedNodeIds)
        : new Set<string>();
      if (!event.shiftKey) {
        setSelectedNodeId(null);
        setSelectedNodeIds(new Set());
        setSelectedEdgeId(null);
      }
      selectionRef.current = {
        startLocalX: localX,
        startLocalY: localY,
        baseNodeIds,
      };
      setSelectionBox({ left: localX, top: localY, width: 0, height: 0 });
      event.currentTarget.setPointerCapture(event.pointerId);
      return;
    }
    if (event.button !== 1 && toolMode !== 'hand') return;
    setSelectedNodeId(null);
    panRef.current = {
      startClientX: event.clientX,
      startClientY: event.clientY,
      startViewportX: viewport.x,
      startViewportY: viewport.y,
    };
  };

  const handleCanvasDoubleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('[data-canvas-node]')) return;
    openNodeMenuAtPoint(event.clientX, event.clientY);
  };

  const handleCanvasContextMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    if (isEditingElement(event.target)) return;
    event.preventDefault();
    event.stopPropagation();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    const clickedNode = (event.target as HTMLElement).closest<HTMLElement>(
      '[data-canvas-node]',
    );
    // 只有实际右键点到节点时才提供节点操作，防止在画布空白处误删当前选中节点。
    const targetNodeId = clickedNode?.dataset.canvasNode || undefined;
    if (clickedNode?.dataset.canvasNode)
      setSelectedNodeId(clickedNode.dataset.canvasNode);
    const menuLeft = clamp(localX, 12, Math.max(12, rect.width - 220));
    const menuHeight = targetNodeId ? 408 : 312;
    const menuTop = clamp(localY, 12, Math.max(12, rect.height - menuHeight));
    const quickMenuWidth = 296;
    const quickMenuLeft =
      menuLeft + 216 + quickMenuWidth <= rect.width
        ? menuLeft + 216
        : Math.max(12, menuLeft - quickMenuWidth - 8);

    setPendingSourceId(null);
    setPendingSourceIds([]);
    setConnectionPointer(null);
    setNodeMenu(null);
    setShortcutsOpen(false);
    setQuickCommandsOpen(false);
    setContextMenu({
      left: menuLeft,
      top: menuTop,
      nodePosition: {
        x: Math.round((localX - viewport.x) / viewport.zoom - NODE_WIDTH / 2),
        y: Math.round((localY - viewport.y) / viewport.zoom - NODE_HEIGHT / 2),
      },
      targetNodeId,
      quickMenuLeft,
      quickMenuTop: clamp(localY - 48, 12, Math.max(12, rect.height - 430)),
    });
  };

  const selectConnectionEdge = useCallback((edgeId: string) => {
    setSelectedEdgeId(edgeId);
    setSelectedNodeId(null);
    setSelectedNodeIds(new Set());
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setConnectionPointer(null);
    setConnectionHoverTargetId(null);
    setConnectionRejectTargetId(null);
    setConnectionCursor(null);
    setNodeMenu(null);
    setShortcutsOpen(false);
    setQuickCommandsOpen(false);
  }, []);

  const handleEdgePointerDown = (
    event: React.PointerEvent<SVGPathElement>,
    edgeId: string,
  ) => {
    if (event.button !== 0) return;
    event.stopPropagation();
    if (toolMode === 'hand') return;
    selectConnectionEdge(edgeId);
    setContextMenu(null);
  };

  const handleEdgeContextMenu = (
    event: React.MouseEvent<SVGPathElement>,
    edgeId: string,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    const menuLeft = clamp(localX, 12, Math.max(12, rect.width - 188));
    const menuTop = clamp(localY, 12, Math.max(12, rect.height - 104));

    selectConnectionEdge(edgeId);
    setContextMenu({
      left: menuLeft,
      top: menuTop,
      nodePosition: {
        x: Math.round((localX - viewport.x) / viewport.zoom),
        y: Math.round((localY - viewport.y) / viewport.zoom),
      },
      targetEdgeId: edgeId,
      quickMenuLeft: menuLeft,
      quickMenuTop: menuTop,
    });
  };

  const cancelConnection = (edgeId: string) => {
    const edge = edges.find((candidate) => candidate.id === edgeId);
    const sourceTitle = nodes.find((node) => node.id === edge?.source)?.title;
    const targetTitle = nodes.find((node) => node.id === edge?.target)?.title;
    setEdges((current) =>
      current.filter((candidate) => candidate.id !== edgeId),
    );
    setSelectedEdgeId((current) => (current === edgeId ? null : current));
    setContextMenu(null);
    setToast(
      sourceTitle && targetTitle
        ? `已取消“${sourceTitle}”到“${targetTitle}”的连接`
        : '已取消节点连接',
    );
  };

  const toCanvasScreenPoint = (left: number, top: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    return {
      left: (rect?.left ?? 0) + left,
      top: (rect?.top ?? 0) + top,
    };
  };

  const portalCanvasFloatingMenu = (menu: React.ReactNode) => {
    if (typeof document === 'undefined') return null;
    return createPortal(
      <div className="adgen-canvas-scope adgen-canvas-floating-portal">
        <div
          data-canvas-theme={theme}
          className={`canvas-theme-shell ${theme === 'dark' ? 'canvas-theme-dark' : ''}`}
        >
          {menu}
        </div>
      </div>,
      document.body,
    );
  };

  const openNodeMenuFromContextMenu = () => {
    if (!contextMenu) return;
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    setNodeMenu({
      left: clamp(contextMenu.left, 12, Math.max(12, rect.width - 316)),
      top: clamp(contextMenu.top, 12, Math.max(12, rect.height - 516)),
      nodePosition: contextMenu.nodePosition,
    });
    setContextMenu(null);
  };

  const uploadFromContextMenu = () => {
    if (!contextMenu) return;
    const nodeId = addNode('asset', contextMenu.nodePosition);
    setContextMenu(null);
    setLocalAssetNodeId(nodeId);
    window.requestAnimationFrame(() => assetInputRef.current?.click());
  };

  const pasteFromContextMenu = async () => {
    if (!contextMenu) return;
    const pastePosition = contextMenu.nodePosition;
    setContextMenu(null);

    try {
      if (!navigator.clipboard) throw new Error('Clipboard API unavailable');
      const imageFiles: File[] = [];
      if (typeof navigator.clipboard.read === 'function') {
        try {
          const clipboardItems = await navigator.clipboard.read();
          for (const [itemIndex, item] of clipboardItems.entries()) {
            const imageType = item.types.find((type) =>
              type.startsWith('image/'),
            );
            if (!imageType) continue;
            const blob = await item.getType(imageType);
            const extension =
              imageType
                .split('/')[1]
                ?.replace('jpeg', 'jpg')
                .replace('svg+xml', 'svg') || 'png';
            imageFiles.push(
              new File(
                [blob],
                `clipboard-${Date.now()}-${itemIndex + 1}.${extension}`,
                { type: imageType },
              ),
            );
          }
        } catch (error) {
          console.debug('[Canvas] 无法从剪贴板读取图片，尝试读取文本:', error);
        }
      }

      if (imageFiles.length > 0) {
        await importCanvasImages(imageFiles, pastePosition, 'paste');
        return;
      }

      const pastedText = (await navigator.clipboard.readText()).trim();
      if (!pastedText) {
        setToast('剪贴板中没有可粘贴的图片或文本');
        return;
      }
      addNode('text', pastePosition, {
        title: '粘贴文本',
        prompt: pastedText,
        status: 'draft',
      });
      setToast('已粘贴文本并创建文本生成节点');
    } catch (error) {
      console.error('[Canvas] 读取剪贴板失败:', error);
      setToast('无法读取剪贴板，请使用 Ctrl/⌘ + V 粘贴');
    }
  };

  useEffect(() => {
    const canvasElement = canvasRef.current;
    if (!canvasElement) return;

    const handleCanvasWheel = (event: WheelEvent) => {
      const eventTarget = event.target;
      const interactiveControl =
        eventTarget instanceof Element
          ? eventTarget.closest(
              'textarea, input, select, [contenteditable="true"], [role="textbox"], [role="listbox"], [role="menu"]',
            )
          : null;
      const pinchZoom = event.ctrlKey || event.metaKey;
      const scrollableRegion = findVerticalScrollableAncestor(
        eventTarget,
        canvasElement,
      );

      if (interactiveControl || scrollableRegion) {
        // 表单和自身已有滚动条的区域先吃掉滚轮；Ctrl/⌘ 仍拦截，避免整页被浏览器缩放。
        if (pinchZoom) event.preventDefault();
        return;
      }

      event.preventDefault();
      const delta = getWheelDeltaPx(event, 16, canvasElement.clientHeight);
      if (delta.x === 0 && delta.y === 0) return;

      // 单选节点并打开设置卡片时，滚轮平移画布而不是缩放，便于看完整设置。
      if (
        selectedNodeIdRef.current &&
        selectedNodeIdsRef.current.size <= 1 &&
        !pinchZoom
      ) {
        setViewport((current) => ({
          ...current,
          x: current.x - (event.shiftKey ? delta.y : delta.x),
          y: current.y - (event.shiftKey ? 0 : delta.y),
        }));
        return;
      }

      if (delta.y === 0) return;

      const rect = canvasElement.getBoundingClientRect();
      const pointerX = event.clientX - rect.left;
      const pointerY = event.clientY - rect.top;
      const factor = delta.y > 0 ? 0.9 : 1.1;

      setViewport((current) => {
        const worldX = (pointerX - current.x) / current.zoom;
        const worldY = (pointerY - current.y) / current.zoom;
        const zoom = clamp(current.zoom * factor, MIN_ZOOM, MAX_ZOOM);
        return {
          x: pointerX - worldX * zoom,
          y: pointerY - worldY * zoom,
          zoom,
        };
      });
    };

    canvasElement.addEventListener('wheel', handleCanvasWheel, {
      passive: false,
    });
    return () => canvasElement.removeEventListener('wheel', handleCanvasWheel);
  }, []);

  const zoomAtCenter = (factor: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const pointerX = rect.width / 2;
    const pointerY = rect.height / 2;
    setViewport((current) => {
      const worldX = (pointerX - current.x) / current.zoom;
      const worldY = (pointerY - current.y) / current.zoom;
      const zoom = clamp(current.zoom * factor, MIN_ZOOM, MAX_ZOOM);
      return {
        x: pointerX - worldX * zoom,
        y: pointerY - worldY * zoom,
        zoom,
      };
    });
  };

  const setZoomAtCenter = (nextZoom: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const pointerX = rect.width / 2;
    const pointerY = rect.height / 2;
    setViewport((current) => {
      const worldX = (pointerX - current.x) / current.zoom;
      const worldY = (pointerY - current.y) / current.zoom;
      const zoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
      return {
        x: pointerX - worldX * zoom,
        y: pointerY - worldY * zoom,
        zoom,
      };
    });
  };

  const handleToolbarPointerDown = (
    event: React.PointerEvent<HTMLButtonElement>,
  ) => {
    const toolbar = toolbarRef.current;
    const canvas = canvasRef.current;
    if (!toolbar || !canvas) return;
    event.preventDefault();
    event.stopPropagation();
    const toolbarRect = toolbar.getBoundingClientRect();
    const canvasRect = canvas.getBoundingClientRect();
    toolbarDragRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startOffsetX: toolbarOffset.x,
      startOffsetY: toolbarOffset.y,
      minDeltaX: canvasRect.left + 12 - toolbarRect.left,
      maxDeltaX: canvasRect.right - 12 - toolbarRect.right,
      minDeltaY: canvasRect.top + 84 - toolbarRect.top,
      maxDeltaY: canvasRect.bottom - 12 - toolbarRect.bottom,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handleToolbarPointerMove = (
    event: React.PointerEvent<HTMLButtonElement>,
  ) => {
    const drag = toolbarDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = clamp(
      event.clientX - drag.startClientX,
      drag.minDeltaX,
      drag.maxDeltaX,
    );
    const deltaY = clamp(
      event.clientY - drag.startClientY,
      drag.minDeltaY,
      drag.maxDeltaY,
    );
    setToolbarOffset({
      x: drag.startOffsetX + deltaX,
      y: drag.startOffsetY + deltaY,
    });
  };

  const handleToolbarPointerUp = (
    event: React.PointerEvent<HTMLButtonElement>,
  ) => {
    if (toolbarDragRef.current?.pointerId !== event.pointerId) return;
    toolbarDragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const handleToolbarKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
  ) => {
    const toolbar = toolbarRef.current;
    const canvas = canvasRef.current;
    if (!toolbar || !canvas) return;
    const step = event.shiftKey ? 48 : 12;
    const movement = {
      ArrowDown: { x: 0, y: step },
      ArrowLeft: { x: -step, y: 0 },
      ArrowRight: { x: step, y: 0 },
      ArrowUp: { x: 0, y: -step },
    }[event.key];
    if (!movement) return;
    event.preventDefault();
    event.stopPropagation();
    const toolbarRect = toolbar.getBoundingClientRect();
    const canvasRect = canvas.getBoundingClientRect();
    setToolbarOffset((current) => ({
      x:
        current.x +
        clamp(
          movement.x,
          canvasRect.left + 12 - toolbarRect.left,
          canvasRect.right - 12 - toolbarRect.right,
        ),
      y:
        current.y +
        clamp(
          movement.y,
          canvasRect.top + 84 - toolbarRect.top,
          canvasRect.bottom - 12 - toolbarRect.bottom,
        ),
    }));
  };

  const fitViewToNodes = (targetNodes: CanvasNodeData[]) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || targetNodes.length === 0) {
      setViewport({ x: 40, y: 80, zoom: 1 });
      return;
    }
    const minX = Math.min(...targetNodes.map((node) => node.x));
    const minY = Math.min(...targetNodes.map((node) => node.y));
    const maxX = Math.max(
      ...targetNodes.map(
        (node) => node.x + getCanvasNodeDimensions(node).width,
      ),
    );
    const maxY = Math.max(
      ...targetNodes.map(
        (node) => node.y + getCanvasNodeDimensions(node).height,
      ),
    );
    const contentWidth = Math.max(1, maxX - minX);
    const contentHeight = Math.max(1, maxY - minY);
    const zoom = clamp(
      Math.min(
        (rect.width - 120) / contentWidth,
        (rect.height - 120) / contentHeight,
      ),
      MIN_ZOOM,
      1.15,
    );
    setViewport({
      x: (rect.width - contentWidth * zoom) / 2 - minX * zoom,
      y: (rect.height - contentHeight * zoom) / 2 - minY * zoom,
      zoom,
    });
  };

  const fitView = () => {
    fitViewToNodes(nodes);
  };

  const resolveHistoryResultType = (
    payload: HistoryUsePayload,
  ): CanvasNodeResult['type'] => {
    const assetType = (payload.asset.type || '').toUpperCase();
    if (assetType === 'VIDEO') return 'video';
    if (assetType === 'AUDIO') return 'audio';
    if (
      payload.generationType === 'music_generation' ||
      payload.generationType === 'tts_generation'
    ) {
      return 'audio';
    }
    if (payload.generationType.includes('video')) return 'video';
    return 'image';
  };

  const findHistoryAssetUrlOnNode = (
    node: CanvasNodeData,
    payload: HistoryUsePayload,
  ) => {
    const resultType = resolveHistoryResultType(payload);
    const assetUrl = getStableCanvasMediaUrl(
      payload.asset.url,
      resultType,
      payload.asset.name,
    );
    const candidates = [
      assetUrl,
      payload.asset.url,
      getStableCanvasMediaUrl(payload.asset.url, resultType),
    ].filter(Boolean);
    const nodeUrls = [
      ...getNodeResultHistory(node).map((result) => result.url),
      ...(node.resultUrls || []),
      node.resultUrl,
    ].filter(Boolean) as string[];
    return nodeUrls.find((url) => {
      if (candidates.includes(url)) return true;
      const stableUrl = getStableCanvasMediaUrl(url, resultType);
      return candidates.includes(stableUrl);
    });
  };

  const useHistoryAsset = (payload: HistoryUsePayload) => {
    const nodeId =
      typeof payload.metadata?.canvas_node_id === 'string'
        ? payload.metadata.canvas_node_id.trim()
        : '';
    const matchedById = nodeId
      ? nodes.find((node) => node.id === nodeId)
      : undefined;
    const matchedByUrl = nodes.find((node) =>
      Boolean(findHistoryAssetUrlOnNode(node, payload)),
    );
    const targetNode = matchedById || matchedByUrl;

    if (targetNode) {
      const matchedUrl = findHistoryAssetUrlOnNode(targetNode, payload);
      if (matchedUrl) setMainNodeResult(targetNode.id, matchedUrl);
      setSelectedNodeId(targetNode.id);
      setSelectedNodeIds(new Set([targetNode.id]));
      setHistoryPageOpen(false);
      requestAnimationFrame(() => fitViewToNodes([targetNode]));
      setToast('已定位到对应节点');
      return;
    }

    restoreHistoryRecord({
      prompt: payload.prompt,
      inputAssets: payload.inputAssets,
      generatedAssets: [payload.asset],
      generationType: payload.generationType,
      sessionId: payload.sessionId,
      metadata: payload.metadata,
    });
    setToast('原节点已不在画布上，已新建节点');
  };

  const keepTidyResult = () => {
    setTidyConfirm(null);
  };

  const revertTidyResult = () => {
    if (!tidyConfirm) return;
    isApplyingHistoryRef.current = true;
    setNodes(tidyConfirm.previousNodes);
    setTidyConfirm(null);
    fitViewToNodes(tidyConfirm.previousNodes);
    setToast('已还原整理前的布局');
  };

  const tidyCanvas = () => {
    if (nodes.length === 0) {
      setToast('画布上还没有节点');
      return;
    }
    const nextNodes = layoutCanvasNodes(nodes, edges, getCanvasNodeDimensions);
    if (areNodePositionsEqual(nodes, nextNodes)) {
      setToast('画布已经很整齐');
      fitViewToNodes(nextNodes);
      return;
    }
    setTidyConfirm({ previousNodes: nodes.map((node) => ({ ...node })) });
    setNodeMenu(null);
    setContextMenu(null);
    setShortcutsOpen(false);
    setNodes(nextNodes);
    fitViewToNodes(nextNodes);
  };

  const openHistoryPage = () => {
    setTidyConfirm(null);
    setShortcutsOpen(false);
    setMinimapOpen(false);
    setImageAiTool(null);
    setNodeMenu(null);
    setContextMenu(null);
    setHistoryPageOpen(true);
  };

  const minimapLayout = useMemo(() => {
    if (!minimapOpen) return null;
    return buildCanvasMinimapLayout(
      nodes,
      selectedNodeIds,
      viewport,
      canvasSize,
      getCanvasNodeDimensions,
      exploredWorld,
      true,
    );
  }, [
    canvasSize,
    exploredWorld,
    getCanvasNodeDimensions,
    minimapOpen,
    nodes,
    selectedNodeIds,
    viewport,
  ]);

  const viewportContainsNode = useMemo(() => {
    if (nodes.length === 0) return true;
    const view = getViewportWorldRect(viewport, canvasSize);
    return nodes.some((node) => {
      const size = getCanvasNodeDimensions(node);
      return rectsOverlap(
        { height: size.height, width: size.width, x: node.x, y: node.y },
        view,
      );
    });
  }, [canvasSize, getCanvasNodeDimensions, nodes, viewport]);

  const [emptyHintReady, setEmptyHintReady] = useState(false);
  const emptyHintShownAtRef = useRef(0);
  const showEmptyViewportHint = emptyHintReady && !emptyViewportHintDismissed;

  useEffect(() => {
    if (viewportContainsNode) setEmptyViewportHintDismissed(false);
  }, [viewportContainsNode]);

  useEffect(() => {
    if (minimapDragging || nodes.length === 0 || viewportContainsNode) {
      setEmptyHintReady(false);
      return undefined;
    }
    const timer = window.setTimeout(() => {
      emptyHintShownAtRef.current = Date.now();
      setEmptyHintReady(true);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [minimapDragging, nodes.length, viewportContainsNode]);

  useEffect(() => {
    const view = getViewportWorldRect(viewport, canvasSize);
    const viewBounds = {
      maxX: view.x + view.width,
      maxY: view.y + view.height,
      minX: view.x,
      minY: view.y,
    };
    let nodeBounds: {
      maxX: number;
      maxY: number;
      minX: number;
      minY: number;
    } | null = null;
    if (nodes.length > 0) {
      nodeBounds = {
        maxX: Math.max(
          ...nodes.map((node) => node.x + getCanvasNodeDimensions(node).width),
        ),
        maxY: Math.max(
          ...nodes.map((node) => node.y + getCanvasNodeDimensions(node).height),
        ),
        minX: Math.min(...nodes.map((node) => node.x)),
        minY: Math.min(...nodes.map((node) => node.y)),
      };
    }
    setExploredWorld((current) =>
      unionWorldBounds(unionWorldBounds(current, nodeBounds), viewBounds),
    );
  }, [canvasSize, getCanvasNodeDimensions, nodes, viewport]);

  const handleMinimapPointerDown = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
    if (!minimapLayout) return;
    event.stopPropagation();
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.setPointerCapture(event.pointerId);
    setMinimapDragging(true);
    minimapDragRef.current = {
      minX: minimapLayout.minX,
      minY: minimapLayout.minY,
      moved: false,
      offsetX: minimapLayout.offsetX,
      offsetY: minimapLayout.offsetY,
      pointerId: event.pointerId,
      scale: minimapLayout.scale,
      startMiniX: event.clientX - rect.left,
      startMiniY: event.clientY - rect.top,
      startViewLeft: -viewport.x / Math.max(viewport.zoom, 0.01),
      startViewTop: -viewport.y / Math.max(viewport.zoom, 0.01),
    };
  };

  const handleMinimapPointerMove = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
    const drag = minimapDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const miniX = event.clientX - rect.left;
    const miniY = event.clientY - rect.top;
    if (Math.hypot(miniX - drag.startMiniX, miniY - drag.startMiniY) > 2)
      drag.moved = true;
    if (!drag.moved) return;
    const viewLeft =
      drag.startViewLeft + (miniX - drag.startMiniX) / drag.scale;
    const viewTop = drag.startViewTop + (miniY - drag.startMiniY) / drag.scale;
    setViewport((current) => ({
      ...current,
      x: -viewLeft * current.zoom,
      y: -viewTop * current.zoom,
    }));
  };

  const handleMinimapPointerUp = (
    event: React.PointerEvent<HTMLDivElement>,
  ) => {
    const drag = minimapDragRef.current;
    if (drag?.pointerId === event.pointerId) {
      minimapDragRef.current = null;
      setMinimapDragging(false);
    }
    if (!drag || drag.moved) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const worldX =
      (event.clientX - rect.left - drag.offsetX) / drag.scale + drag.minX;
    const worldY =
      (event.clientY - rect.top - drag.offsetY) / drag.scale + drag.minY;
    setViewport((current) => ({
      ...current,
      x: canvas.clientWidth / 2 - worldX * current.zoom,
      y: canvas.clientHeight / 2 - worldY * current.zoom,
    }));
  };

  const returnViewportToNodes = () => {
    if (Date.now() - emptyHintShownAtRef.current < 500) return;
    setEmptyHintReady(false);
    setEmptyViewportHintDismissed(false);
    setExploredWorld(null);
    fitView();
  };

  const clearCanvas = () => {
    if (!window.confirm('确定清空画布吗？当前所有节点和连接线都会被移除。'))
      return;
    setTitle('未命名画布');
    setNodes([]);
    setEdges([]);
    setViewport({ x: 40, y: 80, zoom: 1 });
    setSelectedNodeId(null);
    setSelectedNodeIds(new Set());
    setSelectedEdgeId(null);
    setPendingSourceId(null);
    setPendingSourceIds([]);
    setExploredWorld(null);
    setEmptyViewportHintDismissed(false);
    setToast('画布已清空');
  };

  const commitCanvasTitle = () => {
    const nextTitle = titleDraft.trim().slice(0, 80);
    setIsTitleEditing(false);
    if (!nextTitle) {
      setTitleDraft(title);
      setToast('画布名称不能为空');
      return;
    }
    if (nextTitle === title) return;

    setTitle(nextTitle);
    setTitleDraft(nextTitle);
    setToast('画布名称已修改');
  };

  const getIncomingNodes = useCallback(
    (nodeId: string) => {
      const sourceIds = edges
        .filter((edge) => edge.target === nodeId)
        .map((edge) => edge.source);
      return sourceIds
        .map((sourceId) => nodes.find((node) => node.id === sourceId))
        .filter((node): node is CanvasNodeData => Boolean(node));
    },
    [edges, nodes],
  );

  const resolveGenerationPrompt = useCallback(
    (node: CanvasNodeData) => {
      const promptParts = [
        ...getIncomingNodes(node.id).map((incomingNode) =>
          incomingNode.kind === 'video_analysis'
            ? incomingNode.analysisResult?.trim() || ''
            : incomingNode.kind === 'text'
              ? incomingNode.prompt.trim()
              : '',
        ),
        node.prompt.trim(),
      ].filter(Boolean);
      return Array.from(new Set(promptParts)).join('\n\n');
    },
    [getIncomingNodes],
  );

  const getOrderedImageReferences = useCallback(
    (nodeId: string): CanvasImageReference[] => {
      const seenReferences = new Set<string>();
      const references: Omit<CanvasImageReference, 'alias'>[] = [];
      const node = nodes.find((item) => item.id === nodeId);

      const pushReference = (
        sourceNodeId: string,
        url: string | undefined,
        sourceTitle: string,
      ) => {
        const referenceKey = `${sourceNodeId}:${url}`;
        if (!url || seenReferences.has(referenceKey) || references.length >= 14)
          return;
        seenReferences.add(referenceKey);
        references.push({
          id: `canvas-reference-${nodeId}-${sourceNodeId}`,
          url,
          sourceNodeId,
          sourceTitle,
          mediaType: 'image',
        });
      };

      // 宫格切分结果：自身切图是这张素材，上一个节点是原图，两张都要进参考图。
      const ownImageUrl =
        node?.kind === 'image'
          ? getNodeMainResultUrl(node, 'image')
          : undefined;
      const isGridSplitResult =
        Boolean(node?.gridSplitSourceNodeId) ||
        (node?.kind === 'image' &&
          Boolean(ownImageUrl) &&
          /\s\d+-\d+$/.test(node.title));
      if (node && isGridSplitResult) {
        pushReference(node.id, ownImageUrl, node.title);
      }

      getIncomingNodes(nodeId).forEach((incomingNode) => {
        if (!isCanvasImageReferenceSource(incomingNode)) return;
        // 多图节点只传主图；需要多张参考时请分别连线多个节点。
        pushReference(
          incomingNode.id,
          getNodeMainResultUrl(incomingNode, 'image'),
          incomingNode.title,
        );
      });

      return applyImageReferenceOrder(
        references,
        node?.imageReferenceSourceOrder,
      ).map((reference, index) => ({
        ...reference,
        alias: `图片${index + 1}`,
        mediaType: 'image' as const,
      }));
    },
    [getIncomingNodes, nodes],
  );

  const getOrderedVideoReferences = useCallback(
    (nodeId: string): CanvasImageReference[] => {
      const seenReferences = new Set<string>();
      const references: Omit<CanvasImageReference, 'alias'>[] = [];
      const node = nodes.find((item) => item.id === nodeId);

      getIncomingNodes(nodeId).forEach((incomingNode) => {
        if (!isCanvasVideoReferenceSource(incomingNode)) return;
        const url =
          getNodeMainResultUrl(incomingNode, 'video') ||
          incomingNode.resultUrl ||
          incomingNode.resultUrls?.[0];
        const referenceKey = `${incomingNode.id}:${url}`;
        if (!url || seenReferences.has(referenceKey) || references.length >= 14)
          return;
        seenReferences.add(referenceKey);
        references.push({
          id: `canvas-video-reference-${nodeId}-${incomingNode.id}`,
          url,
          sourceNodeId: incomingNode.id,
          sourceTitle: incomingNode.title,
          mediaType: 'video',
        });
      });

      return applyImageReferenceOrder(
        references,
        node?.imageReferenceSourceOrder,
      ).map((reference, index) => ({
        ...reference,
        alias: `视频${index + 1}`,
        mediaType: 'video' as const,
      }));
    },
    [getIncomingNodes, nodes],
  );

  const getOrderedAudioReferences = useCallback(
    (nodeId: string): CanvasImageReference[] => {
      const seenReferences = new Set<string>();
      const references: Omit<CanvasImageReference, 'alias'>[] = [];
      const node = nodes.find((item) => item.id === nodeId);

      getIncomingNodes(nodeId).forEach((incomingNode) => {
        if (!isCanvasAudioReferenceSource(incomingNode)) return;
        const url =
          getNodeMainResultUrl(incomingNode, 'audio') ||
          incomingNode.resultUrl ||
          incomingNode.resultUrls?.[0];
        const referenceKey = `${incomingNode.id}:${url}`;
        if (!url || seenReferences.has(referenceKey) || references.length >= 5)
          return;
        seenReferences.add(referenceKey);
        references.push({
          id: `canvas-audio-reference-${nodeId}-${incomingNode.id}`,
          url,
          sourceNodeId: incomingNode.id,
          sourceTitle: incomingNode.title,
          mediaType: 'audio',
        });
      });

      return applyImageReferenceOrder(
        references,
        node?.imageReferenceSourceOrder,
      ).map((reference, index) => ({
        ...reference,
        alias: `音频${index + 1}`,
        mediaType: 'audio' as const,
      }));
    },
    [getIncomingNodes, nodes],
  );

  const getOrderedFileReferences = useCallback(
    (nodeId: string): CanvasImageReference[] => {
      const incoming = getIncomingNodes(nodeId).find((node) =>
        isCanvasFileReferenceSource(node),
      );
      const url = incoming
        ? incoming.resultUrl || incoming.resultUrls?.[0]
        : undefined;
      if (!incoming || !url) return [];
      return [
        {
          id: `canvas-file-reference-${nodeId}-${incoming.id}`,
          alias: '文档1',
          url,
          sourceNodeId: incoming.id,
          sourceTitle: incoming.title,
          mediaType: 'file',
        },
      ];
    },
    [getIncomingNodes],
  );

  const getOrderedLinkReferences = useCallback(
    (nodeId: string): CanvasImageReference[] => {
      const incoming = getIncomingNodes(nodeId).find((node) =>
        isCanvasLinkReferenceSource(node),
      );
      const url = incoming
        ? incoming.resultUrl || incoming.resultUrls?.[0]
        : undefined;
      if (!incoming || !url) return [];
      return [
        {
          id: `canvas-link-reference-${nodeId}-${incoming.id}`,
          alias: '网页1',
          url,
          sourceNodeId: incoming.id,
          sourceTitle: incoming.title,
          mediaType: 'link',
        },
      ];
    },
    [getIncomingNodes],
  );

  const resolveImageReferenceAssets = useCallback(
    (nodeId: string): UploadedAsset[] =>
      getOrderedImageReferences(nodeId).map((reference) => ({
        id: reference.id,
        type: AssetType.IMAGE,
        url: reference.url,
        name: reference.alias,
      })),
    [getOrderedImageReferences],
  );

  const addImageReferenceGuide = useCallback(
    (prompt: string, references: CanvasImageReference[]) => {
      if (references.length === 0) return prompt;
      const referenceGuide = references
        .map((reference, index) => {
          const sourceTitle =
            reference.sourceTitle.replace(/\s+/g, ' ').trim().slice(0, 40) ||
            `来源节点 ${index + 1}`;
          const kindLabel =
            reference.mediaType === 'video'
              ? '参考视频'
              : reference.mediaType === 'audio'
                ? '参考音频'
                : reference.mediaType === 'file'
                  ? '参考文档'
                  : reference.mediaType === 'link'
                    ? '参考网页'
                    : '参考图';
          return `@${reference.alias} = ${kindLabel}（来源：${sourceTitle}）`;
        })
        .join('\n');
      const header =
        '参考素材已按当前编号顺序传入，请按以下编号理解描述中的引用：';
      return `${header}\n${referenceGuide}\n\n${prompt}`;
    },
    [],
  );

  const reorderImageReferences = useCallback(
    (
      nodeId: string,
      fromIndex: number,
      toIndex: number,
      livePrompt?: string,
      mediaType: 'image' | 'video' | 'audio' = 'image',
    ) => {
      const node = nodes.find((item) => item.id === nodeId);
      if (!node || fromIndex === toIndex) return;
      const currentReferences =
        mediaType === 'video'
          ? getOrderedVideoReferences(nodeId)
          : mediaType === 'audio'
            ? getOrderedAudioReferences(nodeId)
            : getOrderedImageReferences(nodeId);
      const nextReferences = moveArrayItem(
        currentReferences,
        fromIndex,
        toIndex,
      ).map((reference, index) => ({
        ...reference,
        alias: `${getReferenceAliasPrefix(mediaType)}${index + 1}`,
      }));
      if (nextReferences.length === 0 || nextReferences === currentReferences)
        return;

      const nextOrder = nextReferences.map(
        (reference) => reference.sourceNodeId,
      );
      const sourcePrompt = livePrompt ?? node.prompt;
      // @图片N 是固定的图片引用槽位：换序时替换槽位内图片，不改用户提示词。
      // 其余素材类型沿用 test 分支已有的编号同步逻辑。
      const nextPrompt =
        mediaType === 'image'
          ? sourcePrompt
          : remapPromptImageMentions(
              sourcePrompt,
              currentReferences,
              nextReferences,
            );
      updateNode(nodeId, {
        prompt: nextPrompt,
        imageReferenceSourceOrder: nextOrder,
        status: 'draft',
      });
      setEdges((current) => {
        const imageSourceIds = new Set(nextOrder);
        const slotIndexes: number[] = [];
        current.forEach((edge, index) => {
          if (edge.target !== nodeId || !imageSourceIds.has(edge.source))
            return;
          const sourceNode = nodes.find((item) => item.id === edge.source);
          if (
            !sourceNode ||
            (mediaType === 'video'
              ? !isCanvasVideoReferenceSource(sourceNode)
              : mediaType === 'audio'
                ? !isCanvasAudioReferenceSource(sourceNode)
                : !isCanvasImageReferenceSource(sourceNode))
          )
            return;
          slotIndexes.push(index);
        });
        if (slotIndexes.length === 0) return current;
        const edgeBySource = new Map(
          current
            .filter(
              (edge) =>
                edge.target === nodeId && imageSourceIds.has(edge.source),
            )
            .map((edge) => [edge.source, edge]),
        );
        const reorderedEdges = nextOrder
          .map((sourceId) => edgeBySource.get(sourceId))
          .filter((edge): edge is CanvasEdgeData => Boolean(edge));
        if (reorderedEdges.length === 0) return current;
        const next = [...current];
        reorderedEdges.forEach((edge, index) => {
          const slot = slotIndexes[index];
          if (slot != null) next[slot] = edge;
        });
        return next;
      });
      setToast(
        mediaType === 'image'
          ? '已调整参考图顺序，@图片编号保持不变'
          : `已调整参考${getCanvasAssetTypeLabel(mediaType)}顺序，提示词中的 @${getReferenceAliasPrefix(mediaType)}编号已同步`,
      );
    },
    [
      getOrderedAudioReferences,
      getOrderedImageReferences,
      getOrderedVideoReferences,
      nodes,
      updateNode,
    ],
  );

  /** 删除缩略图：断开对应连线，并重排提示词里剩余的 @图片N / @视频N / @音频N。 */
  const removeImageReference = useCallback(
    (
      nodeId: string,
      sourceNodeId: string,
      livePrompt?: string,
      mediaType: 'image' | 'video' | 'audio' | 'file' | 'link' = 'image',
    ) => {
      const node = nodes.find((item) => item.id === nodeId);
      if (!node) return;
      if (sourceNodeId === nodeId) {
        setToast('当前节点自身切图不能从参考中移除');
        return;
      }

      const currentReferences =
        mediaType === 'video'
          ? getOrderedVideoReferences(nodeId)
          : mediaType === 'audio'
            ? getOrderedAudioReferences(nodeId)
            : mediaType === 'file'
              ? getOrderedFileReferences(nodeId)
              : mediaType === 'link'
                ? getOrderedLinkReferences(nodeId)
                : getOrderedImageReferences(nodeId);
      const removed = currentReferences.find(
        (reference) => reference.sourceNodeId === sourceNodeId,
      );
      if (!removed) return;

      const remainingCurrent = currentReferences.filter(
        (reference) => reference.sourceNodeId !== sourceNodeId,
      );
      const nextReferences = remainingCurrent.map((reference, index) => ({
        ...reference,
        alias: `${getReferenceAliasPrefix(mediaType)}${index + 1}`,
      }));
      const nextPrompt = remapPromptImageMentions(
        stripPromptImageMention(livePrompt ?? node.prompt, removed.alias),
        remainingCurrent,
        nextReferences,
      );
      updateNode(nodeId, {
        prompt: nextPrompt,
        imageReferenceSourceOrder: nextReferences.map(
          (reference) => reference.sourceNodeId,
        ),
        status: 'draft',
      });
      setEdges((current) =>
        current.filter(
          (edge) => !(edge.target === nodeId && edge.source === sourceNodeId),
        ),
      );
      setToast(`已移除 @${removed.alias} 的参考连接`);
    },
    [
      getOrderedAudioReferences,
      getOrderedFileReferences,
      getOrderedImageReferences,
      getOrderedLinkReferences,
      getOrderedVideoReferences,
      nodes,
      updateNode,
    ],
  );

  const applyCopiedImageOrder = useCallback(
    (nodeId: string, imageUrls: string[]) => {
      if (imageUrls.length === 0) return;
      const imageReferences = getOrderedImageReferences(nodeId);
      const videoReferences = getOrderedVideoReferences(nodeId);
      const countHits = (
        references: CanvasImageReference[],
        mediaType: 'image' | 'video',
      ) =>
        imageUrls.filter((url) => {
          const stableUrl = getStableCanvasMediaUrl(url, mediaType);
          return references.some(
            (item) =>
              item.url === url ||
              getStableCanvasMediaUrl(item.url, mediaType) === stableUrl,
          );
        }).length;
      const useVideo =
        countHits(videoReferences, 'video') >
        countHits(imageReferences, 'image');
      const currentReferences = useVideo ? videoReferences : imageReferences;
      const mediaType = useVideo ? 'video' : 'image';
      if (currentReferences.length === 0) return;
      const remaining = [...currentReferences];
      const ordered: CanvasImageReference[] = [];
      imageUrls.forEach((url) => {
        const stableUrl = getStableCanvasMediaUrl(url, mediaType);
        const index = remaining.findIndex(
          (item) =>
            item.url === url ||
            getStableCanvasMediaUrl(item.url, mediaType) === stableUrl,
        );
        if (index >= 0) {
          const next = remaining.splice(index, 1)[0];
          if (next) ordered.push(next);
        }
      });
      const nextReferences = [...ordered, ...remaining];
      const nextOrder = nextReferences.map(
        (reference) => reference.sourceNodeId,
      );
      const currentOrder = currentReferences.map(
        (reference) => reference.sourceNodeId,
      );
      if (nextOrder.join('\0') === currentOrder.join('\0')) return;
      updateNode(nodeId, {
        imageReferenceSourceOrder: nextOrder,
        status: 'draft',
      });
      setEdges((current) => {
        const imageSourceIds = new Set(nextOrder);
        const slotIndexes: number[] = [];
        current.forEach((edge, index) => {
          if (edge.target !== nodeId || !imageSourceIds.has(edge.source))
            return;
          const sourceNode = nodes.find((item) => item.id === edge.source);
          if (
            !sourceNode ||
            (useVideo
              ? !isCanvasVideoReferenceSource(sourceNode)
              : !isCanvasImageReferenceSource(sourceNode))
          )
            return;
          slotIndexes.push(index);
        });
        if (slotIndexes.length === 0) return current;
        const edgeBySource = new Map(
          current
            .filter(
              (edge) =>
                edge.target === nodeId && imageSourceIds.has(edge.source),
            )
            .map((edge) => [edge.source, edge]),
        );
        const reorderedEdges = nextOrder
          .map((sourceId) => edgeBySource.get(sourceId))
          .filter((edge): edge is CanvasEdgeData => Boolean(edge));
        if (reorderedEdges.length === 0) return current;
        const next = [...current];
        reorderedEdges.forEach((edge, index) => {
          const slot = slotIndexes[index];
          if (slot != null) next[slot] = edge;
        });
        return next;
      });
      setToast(
        useVideo
          ? '已按复制的提示词对齐参考视频顺序'
          : '已按复制的提示词对齐参考图顺序',
      );
    },
    [getOrderedImageReferences, getOrderedVideoReferences, nodes, updateNode],
  );

  const getVideoReferenceSources = useCallback(
    (nodeId: string) => {
      const sources = getIncomingNodes(nodeId).flatMap((incomingNode) => {
        const mediaKind = isCanvasVideoReferenceSource(incomingNode)
          ? 'video'
          : isCanvasAudioReferenceSource(incomingNode)
            ? 'audio'
            : isCanvasFileReferenceSource(incomingNode)
              ? 'file'
              : isCanvasLinkReferenceSource(incomingNode)
                ? 'link'
                : isCanvasImageReferenceSource(incomingNode)
                  ? 'image'
                  : null;
        if (!mediaKind) return [];
        const type =
          mediaKind === 'video'
            ? AssetType.VIDEO
            : mediaKind === 'audio'
              ? AssetType.AUDIO
              : mediaKind === 'file'
                ? AssetType.FILE
                : mediaKind === 'link'
                  ? AssetType.LINK
                  : AssetType.IMAGE;
        const url =
          getNodeMainResultUrl(
            incomingNode,
            mediaKind === 'file' || mediaKind === 'link'
              ? undefined
              : mediaKind,
          ) ||
          incomingNode.resultUrl ||
          incomingNode.resultUrls?.[0];
        if (!url) return [];
        return [
          {
            url,
            type,
            sourceNodeId: incomingNode.id,
            officialAssetUri: officialAssetUriOf(incomingNode),
          },
        ];
      });
      return Array.from(
        new Map(
          sources
            .filter((source) => source.url)
            .map((source) => [
              `${source.sourceNodeId}:${source.type}:${source.url}`,
              source,
            ]),
        ).values(),
      ).slice(0, 14);
    },
    [getIncomingNodes],
  );

  const blockGenerationForSaveConflict = () => {
    if (!hasSaveConflictRef.current) return false;
    isSaveConflictNoticeOpenRef.current = true;
    setIsSaveConflictNoticeOpen(true);
    setToast('请先保持当前画布为最新版本，可刷新页面或覆盖保存');
    return true;
  };

  const generateImageNode = async (nodeId: string) => {
    if (blockGenerationForSaveConflict()) return;
    const node = nodes.find((item) => item.id === nodeId);
    if (
      !node ||
      !['text', 'image'].includes(node.kind) ||
      generatingNodeIds.has(nodeId)
    )
      return;

    const basePrompt = resolveGenerationPrompt(node);
    if (!basePrompt) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '请填写提示词，或连接一个已有描述的文本提示词节点。',
      }));
      setToast('描述配置完成后才能生成图片');
      return;
    }

    const generationConfig =
      node.kind === 'text' ? node.textImageConfig || node : node;
    const model = availableImageModels.includes(generationConfig.model || '')
      ? generationConfig.model!
      : defaultImageModel;
    const modelConfig = mediaModelCatalog[model] || {};
    const imageGenerationMode: ImageGenerationMode =
      node.kind === 'text'
        ? 'text_to_image'
        : resolveImageGenerationMode(
            modelConfig,
            node.imageGenerationMode,
            'reference_image',
          );
    const supportedResolutions: string[] =
      modelConfig.supported_resolutions || ['1K'];
    const resolution = supportedResolutions.includes(
      generationConfig.resolution || '',
    )
      ? generationConfig.resolution!
      : supportedResolutions[0] || '720p';
    const supportedAspectRatios: string[] =
      modelConfig.supported_aspect_ratios || IMAGE_ASPECT_RATIOS;
    const aspectRatio = supportedAspectRatios.includes(
      generationConfig.aspectRatio || '',
    )
      ? generationConfig.aspectRatio!
      : supportedAspectRatios[0];
    const count = clampBatchCount(generationConfig.count, maxImageBatchCount);
    const estimatedCost = convertPricingAmountToUsd(
      getImagePricePerImage(model, resolution, mediaConfig) * count,
      getModelPricingCurrency(modelConfig),
      cnyToUsdRate,
    );
    const orderedImageReferences =
      imageGenerationMode === 'reference_image'
        ? getOrderedImageReferences(nodeId)
        : [];
    const referenceAssets =
      imageGenerationMode === 'reference_image'
        ? resolveImageReferenceAssets(nodeId)
        : [];
    const prompt =
      imageGenerationMode === 'reference_image'
        ? addImageReferenceGuide(basePrompt, orderedImageReferences)
        : basePrompt;

    if (
      node.kind === 'image' &&
      imageGenerationMode === 'reference_image' &&
      referenceAssets.length === 0
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]:
          '图片生成节点需要一张输入图片，请连接云素材图片或已有文生图结果。',
      }));
      setToast('请先连接云素材图片或文生图结果');
      return;
    }

    setGeneratingNodeIds((current) => new Set(current).add(nodeId));
    setNodeErrors((current) => {
      const next = { ...current };
      delete next[nodeId];
      return next;
    });
    rememberGenerationSettings('image', {
      model,
      resolution,
      aspectRatio,
      count,
    });
    updateNode(
      nodeId,
      node.kind === 'text'
        ? {
            textImageConfig: { model, resolution, aspectRatio, count },
            status: 'ready',
          }
        : {
            model,
            resolution,
            aspectRatio,
            count,
            imageGenerationMode,
            status: 'ready',
          },
    );
    const generationSessionId = generateSessionId();

    try {
      const results = await generateBatchImages({
        type: 'batch',
        assets: referenceAssets,
        prompt,
        batchCount: count,
        aspectRatio,
        imageSize: resolution,
        imageModel: model,
        imageGenerationMode,
      });
      const resultUrls = results.map((result) => result.url).filter(Boolean);
      if (resultUrls.length === 0)
        throw new Error('图片生成接口未返回可用图片');

      const historyResult = await saveBatchImagesRecord(
        referenceAssets.map((asset) => ({
          url: asset.url,
          type: asset.type,
          name: asset.name,
        })),
        prompt,
        results.map((result, index) => ({
          url: result.url,
          type: result.type,
          name: `${node.title} ${index + 1}`,
        })),
        {
          source: 'canvas',
          canvas_id: normalizedCanvasId,
          canvas_title: title,
          canvas_node_id: node.id,
          canvas_node_title: node.title,
          canvas_node_kind: node.kind,
          model_name: model,
          image_generation_mode: imageGenerationMode,
          image_size: resolution,
          aspect_ratio: aspectRatio,
          batch_count: count,
          estimated_cost_usd: Number(estimatedCost.toFixed(8)),
        },
        generationSessionId,
      );
      appendNodeResults(
        nodeId,
        getPersistedResultUrls(historyResult, resultUrls, 'image'),
        'image',
      );
      setToast(
        historyResult
          ? `“${node.title}”已新增 ${resultUrls.length} 张图片，历史记录已保存`
          : `“${node.title}”已新增 ${resultUrls.length} 张图片，但历史记录保存失败`,
      );
    } catch (error) {
      const message = toUserFacingGenerationError(
        error,
        '图片生成失败，请稍后重试',
        {
          imageCount: referenceAssets.length,
        },
      );
      updateNode(nodeId, { status: 'error' });
      setNodeErrors((current) => ({ ...current, [nodeId]: message }));
      setToast('图片生成失败，请查看节点设置');
    } finally {
      setGeneratingNodeIds((current) => {
        const next = new Set(current);
        next.delete(nodeId);
        return next;
      });
    }
  };

  useEffect(() => {
    if (!pendingQuickGeneration) return;
    const nodeReady = nodes.some(
      (node) => node.id === pendingQuickGeneration.nodeId,
    );
    const connectionReady = edges.some(
      (edge) => edge.target === pendingQuickGeneration.nodeId,
    );
    if (!nodeReady || !connectionReady) return;

    const frame = window.requestAnimationFrame(() => {
      const { nodeId } = pendingQuickGeneration;
      setPendingQuickGeneration(null);
      void generateImageNode(nodeId);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [edges, nodes, pendingQuickGeneration]);

  useEffect(() => {
    if (pendingGridHdNodeIds.length === 0) return;
    const ready = pendingGridHdNodeIds.every(
      (nodeId) =>
        nodes.some((node) => node.id === nodeId) &&
        edges.some((edge) => edge.target === nodeId),
    );
    if (!ready) return;

    const frame = window.requestAnimationFrame(() => {
      const nodeIds = pendingGridHdNodeIds;
      setPendingGridHdNodeIds([]);
      nodeIds.forEach((nodeId) => {
        void generateImageNode(nodeId);
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [edges, nodes, pendingGridHdNodeIds]);

  const generateVideoNode = async (nodeId: string) => {
    if (blockGenerationForSaveConflict()) return;
    const node = nodes.find((item) => item.id === nodeId);
    if (
      !node ||
      !['text', 'video'].includes(node.kind) ||
      generatingNodeIds.has(nodeId)
    )
      return;

    const basePrompt = resolveGenerationPrompt(node);
    if (!basePrompt) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '请填写视频描述，或连接一个已有描述的文本提示词节点。',
      }));
      setToast('描述配置完成后才能生成视频');
      return;
    }
    const generationConfig =
      node.kind === 'text' ? node.textVideoConfig || {} : node;
    const selectableModels =
      node.kind === 'text' ? availableTextVideoModels : availableVideoModels;
    const fallbackModel =
      node.kind === 'text' ? defaultTextVideoModel : defaultVideoModel;
    const model = selectableModels.includes(generationConfig.model || '')
      ? generationConfig.model!
      : fallbackModel;
    const modelConfig = mediaModelCatalog[model] || {};
    const supportedResolutions: string[] =
      modelConfig.supported_resolutions || ['720p'];
    const resolution = supportedResolutions.includes(
      generationConfig.resolution || '',
    )
      ? generationConfig.resolution!
      : supportedResolutions[0] || '720p';
    const supportedAspectRatios: string[] =
      modelConfig.supported_aspect_ratios || VIDEO_ASPECT_RATIOS;
    const aspectRatio = supportedAspectRatios.includes(
      generationConfig.aspectRatio || '',
    )
      ? generationConfig.aspectRatio!
      : supportedAspectRatios[0] || '16:9';
    const count = clampBatchCount(generationConfig.count, maxVideoBatchCount);
    const usesTargetDuration = modelConfig.duration_parameter_enabled === true;
    const durationRange: number[] = modelConfig.duration_range_seconds || [
      2, 15,
    ];
    const minimumDuration = Number(durationRange[0] || 2);
    const maximumDuration = Number(durationRange[1] || 15);
    const duration = clamp(
      Number(generationConfig.duration) ||
        Number(modelConfig.default_duration_seconds || minimumDuration),
      minimumDuration,
      maximumDuration,
    );
    const isLiteModel = model === 'veo-3.1-lite-generate-preview';
    const extensionCount =
      modelConfig.supports_extension === false || isLiteModel
        ? 0
        : clamp(
            Number(generationConfig.extensionCount) || 0,
            0,
            maxVideoExtensionCount,
          );
    const effectiveDuration = usesTargetDuration
      ? duration
      : isLiteModel
        ? Number(modelConfig.max_duration_seconds || 8)
        : 8 + extensionCount * 7;
    const supportedModes = getSupportedVideoGenerationModes(modelConfig);
    const generationMode: VideoGenerationMode =
      node.kind === 'text'
        ? 'text_to_video'
        : resolveVideoGenerationMode(
            modelConfig,
            generationConfig.videoGenerationMode,
            'first_frame',
          );
    const allReferenceSources =
      node.kind === 'video' ? getVideoReferenceSources(nodeId) : [];
    const imageReferenceSources = allReferenceSources.filter(
      (source) => source.type === AssetType.IMAGE,
    );
    const videoReferenceSources = allReferenceSources.filter(
      (source) => source.type === AssetType.VIDEO,
    );
    const estimatedCostInPricingCurrency =
      getVideoPricePerSecond(
        model,
        resolution,
        mediaConfig,
        videoReferenceSources.length > 0,
      ) *
      effectiveDuration *
      count;
    // History stores USD consistently. The preview converts this value back to
    // CNY for display, while CNY-priced models retain their native amount here.
    const estimatedCost = convertPricingAmountToUsd(
      estimatedCostInPricingCurrency,
      getModelPricingCurrency(modelConfig),
      cnyToUsdRate,
    );
    const audioReferenceSources = allReferenceSources.filter(
      (source) => source.type === AssetType.AUDIO,
    );
    const fileReferenceSources = allReferenceSources.filter(
      (source) => source.type === AssetType.FILE,
    );
    const linkReferenceSources = allReferenceSources.filter(
      (source) => source.type === AssetType.LINK,
    );
    const referenceSources =
      generationMode === 'text_to_video'
        ? []
        : generationMode === 'reference_image'
          ? imageReferenceSources
          : generationMode === 'reference_video'
            ? videoReferenceSources
            : generationMode === 'first_frame'
              ? imageReferenceSources.slice(0, 1)
              : generationMode === 'first_last_frame'
                ? imageReferenceSources.slice(0, 2)
                : allReferenceSources;
    const allOrderedImageReferences =
      node.kind === 'video' ? getOrderedImageReferences(nodeId) : [];
    const orderedImageReferences =
      generationMode === 'text_to_video'
        ? []
        : generationMode === 'reference_video'
          ? []
          : generationMode === 'first_frame'
            ? allOrderedImageReferences.slice(0, 1)
            : generationMode === 'first_last_frame'
              ? allOrderedImageReferences.slice(0, 2)
              : allOrderedImageReferences;
    const orderedVideoReferences =
      node.kind === 'video' &&
      (generationMode === 'reference_video' ||
        generationMode === 'reference_assets')
        ? getOrderedVideoReferences(nodeId)
        : [];
    const orderedAudioReferences =
      node.kind === 'video' && generationMode === 'reference_assets'
        ? getOrderedAudioReferences(nodeId)
        : [];
    const orderedFileReferences =
      node.kind === 'video' && generationMode === 'reference_assets'
        ? getOrderedFileReferences(nodeId)
        : [];
    const orderedLinkReferences =
      node.kind === 'video' && generationMode === 'reference_assets'
        ? getOrderedLinkReferences(nodeId)
        : [];
    const promptGuideReferences = [
      ...orderedImageReferences,
      ...orderedVideoReferences,
      ...orderedAudioReferences,
      ...orderedFileReferences,
      ...orderedLinkReferences,
    ];
    const prompt =
      promptGuideReferences.length > 0
        ? addImageReferenceGuide(basePrompt, promptGuideReferences)
        : basePrompt;

    if (!supportedModes.includes(generationMode)) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '当前模型不支持所选视频生成模式，请切换模式或模型。',
      }));
      return;
    }
    if (
      generationMode === 'reference_image' &&
      imageReferenceSources.length === 0
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '参考图片生成需要至少连接一张图片。',
      }));
      setToast('请先连接参考图片');
      return;
    }
    if (
      generationMode === 'reference_video' &&
      videoReferenceSources.length === 0
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '参考视频生成需要至少连接一条视频。',
      }));
      setToast('请先连接参考视频');
      return;
    }
    if (
      generationMode === 'reference_assets' &&
      referenceSources.length === 0
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]:
          '全能参考需要至少连接一张图片、一条视频、一段音频、一份文档或一个网页。',
      }));
      setToast('请先连接参考素材');
      return;
    }
    if (
      ((fileReferenceSources.length > 0 || linkReferenceSources.length > 0) &&
        (!isWan3VideoModel(model) || generationMode !== 'reference_assets')) ||
      (audioReferenceSources.length > 0 &&
        ((!isWan3VideoModel(model) && !isSeedance25VideoModel(model)) ||
          generationMode !== 'reference_assets'))
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]:
          '音频参考支持万相 3.0 或 Seedance 2.5 全能参考；文档和网页仅支持万相 3.0 全能参考。',
      }));
      setToast('请使用支持该素材的全能参考模型，或移除不支持的连接');
      return;
    }
    if (
      generationMode === 'reference_assets' &&
      isWan3VideoModel(model) &&
      fileReferenceSources.length + linkReferenceSources.length > 1
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '万相 3.0 文档参考与网页参考不能同时使用。',
      }));
      setToast('请只保留一份文档或一个网页');
      return;
    }
    if (
      generationMode === 'reference_assets' &&
      isWan3VideoModel(model) &&
      fileReferenceSources.length > WAN3_MAX_REFERENCE_FILES
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '万相 3.0 全能参考最多连接 1 份文档。',
      }));
      setToast('请只保留一份文档');
      return;
    }
    if (
      generationMode === 'reference_assets' &&
      isWan3VideoModel(model) &&
      linkReferenceSources.length > WAN3_MAX_REFERENCE_LINKS
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '万相 3.0 全能参考最多连接 1 个网页。',
      }));
      setToast('请只保留一个网页链接');
      return;
    }
    if (
      generationMode === 'reference_assets' &&
      isWan3VideoModel(model) &&
      audioReferenceSources.length > WAN3_MAX_REFERENCE_AUDIOS
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: `万相 3.0 全能参考最多连接 ${WAN3_MAX_REFERENCE_AUDIOS} 段参考音频。`,
      }));
      setToast(`请减少参考音频，最多 ${WAN3_MAX_REFERENCE_AUDIOS} 段`);
      return;
    }
    if (
      generationMode === 'reference_assets' &&
      isWan3VideoModel(model) &&
      referenceSources.length > WAN3_MAX_OMNI_MEDIA
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: `万相 3.0 全能参考最多连接 ${WAN3_MAX_OMNI_MEDIA} 个素材。`,
      }));
      setToast(`请减少参考素材，最多 ${WAN3_MAX_OMNI_MEDIA} 个`);
      return;
    }
    if (
      generationMode === 'reference_assets' &&
      isWan3VideoModel(model) &&
      imageReferenceSources.length > WAN3_MAX_REFERENCE_IMAGES
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: `万相 3.0 全能参考最多连接 ${WAN3_MAX_REFERENCE_IMAGES} 张参考图。`,
      }));
      setToast(`请减少参考图，最多 ${WAN3_MAX_REFERENCE_IMAGES} 张`);
      return;
    }
    if (
      (generationMode === 'reference_assets' ||
        generationMode === 'reference_video') &&
      isWan3VideoModel(model) &&
      videoReferenceSources.length > WAN3_MAX_REFERENCE_VIDEOS
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: `万相 3.0 全能参考最多连接 ${WAN3_MAX_REFERENCE_VIDEOS} 段参考视频。`,
      }));
      setToast(`请减少参考视频，最多 ${WAN3_MAX_REFERENCE_VIDEOS} 段`);
      return;
    }
    if (generationMode === 'first_frame' && imageReferenceSources.length < 1) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '首帧生成需要连接一张输入图片。',
      }));
      setToast('请先连接首帧图片');
      return;
    }
    if (
      generationMode === 'first_last_frame' &&
      imageReferenceSources.length < 2
    ) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '首尾帧生成需要按顺序连接两张图片。',
      }));
      setToast('请先连接首帧和尾帧图片');
      return;
    }
    const clientTaskId = createVideoGenerationTaskId();
    setGeneratingNodeIds((current) => new Set(current).add(nodeId));
    setNodeErrors((current) => {
      const next = { ...current };
      delete next[nodeId];
      return next;
    });
    setNodeProgress((current) => ({
      ...current,
      [nodeId]:
        referenceSources.length > 0
          ? '正在读取参考素材...'
          : '正在提交视频生成任务...',
    }));
    setVideoTaskCancelStates((current) => ({
      ...current,
      [nodeId]: {
        taskId: clientTaskId,
        canCancel: true,
        reason: '正在提交任务，可取消本次提交',
        isSubmitting: true,
      },
    }));
    const normalizedVideoConfig = {
      model,
      resolution,
      aspectRatio,
      count,
      duration,
      extensionCount,
      videoGenerationMode: generationMode,
    };
    rememberGenerationSettings('video', normalizedVideoConfig);
    updateNode(
      nodeId,
      node.kind === 'text'
        ? { textVideoConfig: normalizedVideoConfig, status: 'ready' }
        : { ...normalizedVideoConfig, status: 'ready' },
    );
    const generationSessionId = generateSessionId();

    try {
      const referenceAssets = await Promise.all(
        referenceSources.map(async (source, index) => {
          if (source.type === AssetType.LINK) {
            return {
              id: `canvas-link-${index + 1}-${Date.now()}`,
              type: AssetType.LINK,
              url: source.url,
              name: `网页 ${index + 1}`,
            } satisfies UploadedAsset;
          }
          const fileType =
            source.type === AssetType.VIDEO
              ? AssetType.VIDEO
              : source.type === AssetType.AUDIO
                ? AssetType.AUDIO
                : source.type === AssetType.FILE
                  ? AssetType.FILE
                  : AssetType.IMAGE;
          // BytePlus 后端租约负责恢复旧编号；其他模型提交原文件，无需重新入库。
          return createFileBackedAsset(
            source.url,
            fileType,
            index,
            source.officialAssetUri,
          );
        }),
      );
      const results = await generateVideoFission(
        {
          type: 'batch',
          assets: referenceAssets,
          prompt,
          batchCount: count,
          extensionCount: usesTargetDuration ? undefined : extensionCount,
          duration: usesTargetDuration ? duration : undefined,
          aspectRatio,
          resolution,
          videoModel: model,
          videoGenerationMode: generationMode,
          clientTaskId,
        },
        (message, progress) => {
          if (message) {
            setNodeProgress((current) => ({ ...current, [nodeId]: message }));
          }
          if (progress) {
            setVideoTaskCancelStates((current) => {
              const currentTask = current[nodeId];
              if (currentTask?.isCancelling) {
                return current;
              }
              return {
                ...current,
                [nodeId]: {
                  taskId: currentTask?.taskId,
                  canCancel: progress.canCancel === true,
                  isSubmitting: currentTask?.isSubmitting,
                  reason:
                    progress.cancelReason ||
                    (progress.canCancel ? '' : '当前任务暂不支持取消'),
                },
              };
            });
          }
        },
        (taskId, canCancel, isSubmitting) => {
          setVideoTaskCancelStates((current) => {
            const currentTask = current[nodeId];
            if (currentTask?.isCancelling) {
              return {
                ...current,
                [nodeId]: {
                  ...currentTask,
                  taskId,
                  canCancel: false,
                  isSubmitting: false,
                  reason: '取消请求已登记，正在终止任务提交',
                },
              };
            }
            return {
              ...current,
              [nodeId]: {
                taskId,
                canCancel: canCancel === true,
                isSubmitting: isSubmitting === true,
                reason:
                  isSubmitting === true
                    ? '正在提交任务，可取消本次提交'
                    : canCancel === true
                      ? '任务已提交，可在厂商开始处理前取消'
                      : '当前厂商任务不支持取消',
              },
            };
          });
        },
      );
      const resultUrls = results.map((result) => result.url).filter(Boolean);
      if (resultUrls.length === 0)
        throw new Error('视频生成接口未返回可用视频');

      const backendResultsPersisted =
        results.length > 0 &&
        results.every(
          (result) =>
            Boolean(result.videoData?.historyRecordId) &&
            Boolean(result.persistentUrl),
        );
      const historyResult = backendResultsPersisted
        ? null
        : await saveVideoFissionRecord(
            referenceAssets.map((asset) => ({
              url: asset.url,
              type: asset.type,
              name: asset.name,
            })),
            prompt,
            results.map((result, index) => ({
              url: result.url,
              type: result.type,
              name: `${node.title} ${index + 1}`,
            })),
            usesTargetDuration ? 0 : extensionCount,
            {
              source: 'canvas',
              canvas_id: normalizedCanvasId,
              canvas_title: title,
              canvas_node_id: node.id,
              canvas_node_title: node.title,
              canvas_node_kind: node.kind,
              model_name: model,
              resolution,
              aspect_ratio: aspectRatio,
              duration,
              batch_count: count,
              estimated_cost_usd: Number(estimatedCost.toFixed(2)),
              video_generation_mode: generationMode,
            },
            generationSessionId,
          );
      appendNodeResults(
        nodeId,
        backendResultsPersisted
          ? results
              .map((result) => result.persistentUrl)
              .filter((url): url is string => Boolean(url))
          : getPersistedResultUrls(historyResult, resultUrls, 'video'),
        'video',
      );
      setToast(
        backendResultsPersisted || historyResult
          ? `“${node.title}”已新增 ${resultUrls.length} 条视频，历史记录已保存`
          : `“${node.title}”已新增 ${resultUrls.length} 条视频，但历史记录保存失败`,
      );
    } catch (error) {
      if (error instanceof VideoGenerationCancelledError) {
        updateNode(nodeId, { status: 'draft' });
        setToast('视频任务已取消');
        return;
      }
      const message = toUserFacingGenerationError(
        error,
        '视频生成失败，请稍后重试',
        {
          imageCount: imageReferenceSources.length,
          videoCount: videoReferenceSources.length,
        },
      );
      updateNode(nodeId, { status: 'error' });
      setNodeErrors((current) => ({ ...current, [nodeId]: message }));
      setToast('视频生成失败，请查看节点设置');
    } finally {
      setVideoTaskCancelStates((current) => {
        const next = { ...current };
        delete next[nodeId];
        return next;
      });
      setGeneratingNodeIds((current) => {
        const next = new Set(current);
        next.delete(nodeId);
        return next;
      });
      setNodeProgress((current) => {
        const next = { ...current };
        delete next[nodeId];
        return next;
      });
    }
  };

  const generateVideoAnalysisNode = async (nodeId: string) => {
    const node = nodes.find((item) => item.id === nodeId);
    if (
      !node ||
      node.kind !== 'video_analysis' ||
      generatingNodeIds.has(nodeId)
    )
      return;

    const source = getVideoReferenceSources(nodeId).find(
      (item) => item.type === AssetType.VIDEO,
    );
    if (!source) {
      const message = '视频分析节点需要连接一条已导入或已生成的视频。';
      setNodeErrors((current) => ({ ...current, [nodeId]: message }));
      setToast('请先连接一条视频');
      return;
    }
    // 结果节点的 prompt 要保留分析文本以便下游生成；分析前填写的提示词另存，
    // 供节点下方回看，避免重复显示分析结果。
    const sourceGenerationPrompt = node.prompt.trim();

    setGeneratingNodeIds((current) => new Set(current).add(nodeId));
    setNodeProgress((current) => ({ ...current, [nodeId]: '正在分析视频...' }));
    setNodeErrors((current) => {
      const next = { ...current };
      delete next[nodeId];
      return next;
    });
    updateNode(nodeId, {
      model: DEFAULT_VIDEO_ANALYSIS_MODEL,
      status: 'ready',
    });

    try {
      const result = await analyzeCanvasVideo({
        videoUrl: source.url,
        prompt: node.prompt.trim(),
      });
      updateNode(nodeId, {
        kind: 'text',
        title: '视频分析结果',
        prompt: result.analysis,
        model: undefined,
        analysisResult: undefined,
        sourceGenerationPrompt,
        width: NODE_WIDTH * 2,
        height: TEXT_PROMPT_NODE_HEIGHT * 2,
        status: 'ready',
      });
      setToast('视频分析完成，已转换为可编辑文本节点');
    } catch (error) {
      const message = toUserFacingGenerationError(
        error,
        '视频分析失败，请稍后重试',
      );
      updateNode(nodeId, { status: 'error' });
      setNodeErrors((current) => ({ ...current, [nodeId]: message }));
      setToast('视频分析失败，请查看节点设置');
    } finally {
      setGeneratingNodeIds((current) => {
        const next = new Set(current);
        next.delete(nodeId);
        return next;
      });
      setNodeProgress((current) => {
        const next = { ...current };
        delete next[nodeId];
        return next;
      });
    }
  };

  const generateMediaFromCanvasChat = useCallback(
    async (
      kind: CanvasChatMediaType,
      requests: CanvasChatGenerationRequest[],
    ) => {
      const generationRequests = requests.filter((request) =>
        Boolean(request.prompt.trim()),
      );
      if (generationRequests.length === 0)
        throw new Error('对话回复中没有可用于生成的描述');

      const availableModels =
        kind === 'image' ? availableImageModels : availableTextVideoModels;
      if (availableModels.length === 0) {
        throw new Error(
          kind === 'image'
            ? '当前没有可用的图片生成模型'
            : '当前没有可用的视频生成模型',
        );
      }

      const remembered = lastGenerationSettingsRef.current[kind] || {};
      const fallbackModel =
        kind === 'image' ? defaultImageModel : defaultTextVideoModel;
      const center = getCanvasCenter();
      const isImage = kind === 'image';
      const imageGenerationMode: ImageGenerationMode | undefined = isImage
        ? 'text_to_image'
        : undefined;
      const videoGenerationMode: VideoGenerationMode | undefined = isImage
        ? undefined
        : 'text_to_video';
      const generationNodes = generationRequests.map((request, index) => {
        const useRecentSettings = Boolean(request.useRecentSettings);
        const requestedModel = request.model?.trim();
        const resolvedRequestedModel = requestedModel
          ? resolveChatGenerationModelId(
              requestedModel,
              availableModels,
              mediaModelCatalog,
            )
          : undefined;
        if (requestedModel && !resolvedRequestedModel) {
          const availableLabels = availableModels
            .map((modelId) => mediaModelCatalog[modelId]?.label || modelId)
            .join('、');
          throw new Error(
            `对话中指定的模型“${requestedModel}”不在数据库当前已启用的${kind === 'image' ? '图片' : '视频'}模型列表中。当前可用：${availableLabels}`,
          );
        }
        const rememberedModel = availableModels.includes(remembered.model || '')
          ? remembered.model!
          : undefined;
        const model =
          (useRecentSettings && rememberedModel) ||
          resolvedRequestedModel ||
          (kind === 'image' && availableModels.includes('gpt-image-2')
            ? 'gpt-image-2'
            : rememberedModel || fallbackModel);
        const modelConfig = mediaModelCatalog[model] || {};
        const supportedResolutions: string[] =
          modelConfig.supported_resolutions || [
            kind === 'image'
              ? imageFeatureConfig.default_resolution || '1K'
              : videoFeatureConfig.default_resolution || '720p',
          ];
        const supportedAspectRatios: string[] =
          modelConfig.supported_aspect_ratios ||
          (kind === 'image' ? IMAGE_ASPECT_RATIOS : VIDEO_ASPECT_RATIOS);
        if (
          !useRecentSettings &&
          request.resolution &&
          !supportedResolutions.includes(request.resolution)
        ) {
          throw new Error(
            `模型“${mediaModelCatalog[model]?.label || model}”不支持清晰度 ${request.resolution}`,
          );
        }
        if (
          !useRecentSettings &&
          request.aspectRatio &&
          !supportedAspectRatios.includes(request.aspectRatio)
        ) {
          throw new Error(
            `模型“${mediaModelCatalog[model]?.label || model}”不支持比例 ${request.aspectRatio}`,
          );
        }
        const resolution =
          (useRecentSettings &&
          supportedResolutions.includes(remembered.resolution || '')
            ? remembered.resolution
            : undefined) ||
          request.resolution ||
          (kind === 'image'
            ? supportedResolutions[0]
            : supportedResolutions.includes(remembered.resolution || '')
              ? remembered.resolution!
              : supportedResolutions[0]);
        const aspectRatio =
          (useRecentSettings &&
          supportedAspectRatios.includes(remembered.aspectRatio || '')
            ? remembered.aspectRatio
            : undefined) ||
          request.aspectRatio ||
          (kind === 'image' && supportedAspectRatios.includes('1:1')
            ? '1:1'
            : supportedAspectRatios.includes(remembered.aspectRatio || '')
              ? remembered.aspectRatio!
              : supportedAspectRatios[0]);
        const durationRange: number[] = modelConfig.duration_range_seconds || [
          2, 15,
        ];
        const duration = clamp(
          Number(useRecentSettings ? remembered.duration : request.duration) ||
            Number(request.duration) ||
            Number(remembered.duration) ||
            Number(
              modelConfig.default_duration_seconds || durationRange[0] || 5,
            ),
          Number(durationRange[0] || 2),
          Number(durationRange[1] || 15),
        );
        const row = Math.floor(index / 2);
        const column = index % 2;
        return {
          id: createId('node'),
          kind,
          title:
            generationRequests.length > 1
              ? `${isImage ? '对话生成图片' : '对话生成视频'} ${index + 1}`
              : isImage
                ? '对话生成图片'
                : '对话生成视频',
          x: Math.round(center.x + column * (NODE_WIDTH + 56)),
          y: Math.round(center.y + row * (NODE_HEIGHT + 72)),
          prompt: request.prompt.trim(),
          model,
          count: clampBatchCount(
            useRecentSettings
              ? remembered.count || 1
              : (request.count ?? (isImage ? 1 : remembered.count)),
            isImage ? maxImageBatchCount : maxVideoBatchCount,
          ),
          aspectRatio,
          resolution,
          imageGenerationMode,
          duration: isImage ? undefined : duration,
          extensionCount: isImage ? undefined : 0,
          videoGenerationMode,
          status: 'draft',
        } satisfies CanvasNodeData;
      });

      setNodes((current) => [...current, ...generationNodes]);
      setSelectedNodeId(generationNodes[0].id);
      setSelectedNodeIds(new Set([generationNodes[0].id]));
      setPendingChatGenerations(
        generationNodes.map((node) => ({ kind, nodeId: node.id })),
      );
      setToast(
        generationNodes.length > 1
          ? `已按对话回复创建 ${generationNodes.length} 个独立${isImage ? '图片' : '视频'}任务`
          : `已按对话回复的模型与配置创建${isImage ? '图片' : '视频'}任务`,
      );
    },
    [
      availableImageModels,
      availableTextVideoModels,
      defaultImageModel,
      defaultTextVideoModel,
      getCanvasCenter,
      imageFeatureConfig.default_resolution,
      maxImageBatchCount,
      maxVideoBatchCount,
      mediaModelCatalog,
      videoFeatureConfig.default_resolution,
    ],
  );

  useEffect(() => {
    if (pendingChatGenerations.length === 0) return;
    const nodeReady = pendingChatGenerations.every((pending) =>
      nodes.some((node) => node.id === pending.nodeId),
    );
    if (!nodeReady) return;

    const frame = window.requestAnimationFrame(() => {
      const pending = pendingChatGenerations;
      setPendingChatGenerations([]);
      void (async () => {
        for (const item of pending) {
          if (item.kind === 'image') await generateImageNode(item.nodeId);
          else await generateVideoNode(item.nodeId);
        }
      })();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [nodes, pendingChatGenerations]);

  const cancelVideoNodeGeneration = async (nodeId: string) => {
    const task = videoTaskCancelStates[nodeId];
    const canCancelDuringSubmission = task?.isSubmitting === true;
    if (
      !task?.taskId ||
      (!task.canCancel && !canCancelDuringSubmission) ||
      task.isCancelling
    ) {
      setToast(task?.reason || '当前视频任务暂不支持取消');
      return;
    }

    setVideoTaskCancelStates((current) => ({
      ...current,
      [nodeId]: {
        ...task,
        canCancel: false,
        isCancelling: true,
        reason: '正在取消视频任务...',
      },
    }));
    setNodeProgress((current) => ({
      ...current,
      [nodeId]: '正在取消视频任务...',
    }));
    try {
      const cancellation = await cancelVideoGenerationTask(task.taskId);
      setToast(
        cancellation.status === 'submission_cancellation_requested'
          ? '取消请求已登记，将在提交到厂商前终止'
          : cancellation.status === 'cancellation_requested'
            ? '取消请求已登记，正在等待厂商确认'
            : '厂商已确认取消视频任务',
      );
    } catch (error) {
      const reason = toUserFacingGenerationError(
        error,
        '视频任务取消失败，请等待当前任务完成',
      );
      setVideoTaskCancelStates((current) => ({
        ...current,
        [nodeId]: { ...task, canCancel: false, reason },
      }));
      setNodeProgress((current) => ({ ...current, [nodeId]: reason }));
      setToast('视频任务无法取消');
    }
  };

  const confirmReplaceNodeMedia = (regenerate: boolean) => {
    const pending = replaceMediaConfirm;
    if (!pending) return;
    const node = nodes.find((item) => item.id === pending.nodeId);
    setReplaceMediaConfirm(null);
    if (!node) {
      setToast('目标节点已不存在');
      return;
    }
    void applyDroppedMediaToNode(node, pending.asset);
    if (!regenerate) return;
    if (pending.mediaType === 'video') {
      void generateVideoNode(node.id);
      return;
    }
    void generateImageNode(node.id);
  };

  const generateMusicNode = async (nodeId: string) => {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node || node.kind !== 'music' || generatingNodeIds.has(nodeId)) return;
    const prompt = resolveGenerationPrompt(node);
    if (!prompt) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '请填写音乐描述，或连接一个已有描述的文本提示词节点。',
      }));
      setToast('描述配置完成后才能生成音乐');
      return;
    }

    const model = availableMusicModels.includes(node.model || '')
      ? node.model!
      : defaultMusicModel;
    const count = 1;
    const referenceSources = resolveImageReferenceAssets(nodeId);
    setGeneratingNodeIds((current) => new Set(current).add(nodeId));
    setNodeErrors((current) => {
      const next = { ...current };
      delete next[nodeId];
      return next;
    });
    setNodeProgress((current) => ({ ...current, [nodeId]: '正在生成音乐...' }));
    updateNode(nodeId, { model, count, status: 'ready' });
    const generationSessionId = generateSessionId();

    try {
      const referenceAssets = await Promise.all(
        referenceSources.map((source, index) =>
          createFileBackedAsset(source.url, AssetType.IMAGE, index),
        ),
      );
      const results = await generateMusic({
        type: 'batch',
        assets: referenceAssets,
        prompt,
        batchCount: count,
        musicModel: model,
      });
      const resultUrls = results.map((result) => result.url).filter(Boolean);
      if (resultUrls.length === 0)
        throw new Error('音乐生成接口未返回可用音频');
      const historyResult = await saveMusicGenerationRecord(
        referenceAssets.map((asset) => ({
          url: asset.url,
          type: asset.type,
          name: asset.name,
        })),
        prompt,
        results.map((result, index) => ({
          url: result.url,
          type: result.type,
          name: `${node.title} ${index + 1}`,
        })),
        {
          source: 'canvas',
          canvas_id: normalizedCanvasId,
          canvas_title: title,
          canvas_node_id: node.id,
          canvas_node_title: node.title,
          canvas_node_kind: node.kind,
          model_name: model,
          batch_count: count,
        },
        generationSessionId,
      );
      appendNodeResults(
        nodeId,
        getPersistedResultUrls(historyResult, resultUrls, 'audio'),
        'audio',
      );
      setToast(
        historyResult
          ? `“${node.title}”已新增 ${resultUrls.length} 首音乐，历史记录已保存`
          : `“${node.title}”已新增 ${resultUrls.length} 首音乐，但历史记录保存失败`,
      );
    } catch (error) {
      const message = toUserFacingGenerationError(
        error,
        '音乐生成失败，请稍后重试',
      );
      updateNode(nodeId, { status: 'error' });
      setNodeErrors((current) => ({ ...current, [nodeId]: message }));
      setToast('音乐生成失败，请查看节点设置');
    } finally {
      setGeneratingNodeIds((current) => {
        const next = new Set(current);
        next.delete(nodeId);
        return next;
      });
      setNodeProgress((current) => {
        const next = { ...current };
        delete next[nodeId];
        return next;
      });
    }
  };

  const generateTTSNode = async (nodeId: string) => {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node || node.kind !== 'tts' || generatingNodeIds.has(nodeId)) return;
    const prompt = resolveGenerationPrompt(node);
    if (!prompt) {
      setNodeErrors((current) => ({
        ...current,
        [nodeId]: '请填写配音文案，或连接一个已有文案的文本提示词节点。',
      }));
      setToast('文案配置完成后才能生成配音');
      return;
    }

    const model = availableTTSModels.includes(node.model || '')
      ? node.model!
      : defaultTTSModel;
    const count = 1;
    const voiceName = TTS_VOICE_OPTIONS.includes(node.voiceName || '')
      ? node.voiceName!
      : defaultTTSVoice;
    const speechRate = node.speechRate || 'normal';
    setGeneratingNodeIds((current) => new Set(current).add(nodeId));
    setNodeErrors((current) => {
      const next = { ...current };
      delete next[nodeId];
      return next;
    });
    setNodeProgress((current) => ({ ...current, [nodeId]: '正在生成配音...' }));
    updateNode(nodeId, {
      model,
      count,
      voiceName,
      speechRate,
      status: 'ready',
    });
    const generationSessionId = generateSessionId();

    try {
      const results = await generateTTS({
        type: 'batch',
        assets: [],
        prompt,
        batchCount: count,
        ttsModel: model,
        parameters: {
          speakerMode: 'single',
          voiceName,
          voiceStyle: node.voiceStyle || '',
          speechRate,
        },
      });
      const resultUrls = results.map((result) => result.url).filter(Boolean);
      if (resultUrls.length === 0) throw new Error('TTS 接口未返回可用音频');
      const historyResult = await saveTTSGenerationRecord(
        [],
        prompt,
        results.map((result, index) => ({
          url: result.url,
          type: result.type,
          name: `${node.title} ${index + 1}`,
        })),
        {
          source: 'canvas',
          canvas_id: normalizedCanvasId,
          canvas_title: title,
          canvas_node_id: node.id,
          canvas_node_title: node.title,
          canvas_node_kind: node.kind,
          model_name: model,
          batch_count: count,
          voice_name: voiceName,
          voice_style: node.voiceStyle || '',
          speech_rate: speechRate,
        },
        generationSessionId,
      );
      appendNodeResults(
        nodeId,
        getPersistedResultUrls(historyResult, resultUrls, 'audio'),
        'audio',
      );
      setToast(
        historyResult
          ? `“${node.title}”已新增 ${resultUrls.length} 条配音，历史记录已保存`
          : `“${node.title}”已新增 ${resultUrls.length} 条配音，但历史记录保存失败`,
      );
    } catch (error) {
      const message = toUserFacingGenerationError(
        error,
        '配音生成失败，请稍后重试',
      );
      updateNode(nodeId, { status: 'error' });
      setNodeErrors((current) => ({ ...current, [nodeId]: message }));
      setToast('配音生成失败，请查看节点设置');
    } finally {
      setGeneratingNodeIds((current) => {
        const next = new Set(current);
        next.delete(nodeId);
        return next;
      });
      setNodeProgress((current) => {
        const next = { ...current };
        delete next[nodeId];
        return next;
      });
    }
  };

  const renderNodeBody = (node: CanvasNodeData) => {
    const usesExpandedTextBox =
      node.kind === 'text' &&
      ((typeof node.width === 'number' && node.width > NODE_WIDTH) ||
        (typeof node.height === 'number' &&
          node.height > TEXT_PROMPT_NODE_HEIGHT));
    const ownResultUrls = getNodeResultUrls(node, getNodeResultType(node));
    const inheritedResults =
      node.kind === 'output'
        ? getIncomingNodes(node.id).flatMap((incomingNode) => {
            return getNodeResultHistory(incomingNode).map((result) => ({
              url: result.url,
              kind: result.type === 'audio' ? incomingNode.kind : result.type,
            }));
          })
        : [];
    const visibleResults =
      ownResultUrls.length > 0
        ? ownResultUrls.map((url) => ({
            url,
            kind:
              node.kind === 'text'
                ? node.resultAssetType || 'image'
                : node.kind === 'asset'
                  ? node.assetType || 'image'
                  : node.kind,
          }))
        : inheritedResults;
    const firstVisibleResult = visibleResults[0];

    if (
      generatingNodeIds.has(node.id) &&
      ['text', 'image', 'video', 'video_analysis', 'music', 'tts'].includes(
        node.kind,
      )
    ) {
      const isVideo =
        node.kind === 'video' ||
        (node.kind === 'text' && node.textGenerationMode === 'video');
      const isAudio = node.kind === 'music' || node.kind === 'tts';
      if (node.kind === 'image' || node.kind === 'video') {
        return (
          <div className="relative h-full w-full overflow-hidden rounded-[5px] bg-[#242424]">
            <NodeGeneratingOverlay label={nodeProgress[node.id] || '生成中'} />
          </div>
        );
      }
      return (
        <div
          className={`flex h-20 items-center justify-center gap-2 rounded-xl border px-3 text-center text-xs font-semibold ${isAudio ? 'border-sky-100 bg-sky-50 text-sky-700' : isVideo ? 'border-fuchsia-100 bg-fuchsia-50 text-fuchsia-700' : 'border-violet-100 bg-violet-50 text-violet-700'}`}
        >
          <Loader2 size={16} className="shrink-0 animate-spin" />
          <span className="line-clamp-2">
            {nodeProgress[node.id] ||
              (node.kind === 'video_analysis'
                ? '正在分析视频...'
                : isAudio
                  ? '正在生成音频...'
                  : isVideo
                    ? '正在生成视频...'
                    : '正在生成图片...')}
          </span>
        </div>
      );
    }
    if (
      firstVisibleResult &&
      (firstVisibleResult.kind === 'music' || firstVisibleResult.kind === 'tts')
    ) {
      return (
        <div className="flex h-20 flex-col justify-center rounded-xl border border-sky-100 bg-sky-50 px-3">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold text-sky-700">
            {firstVisibleResult.kind === 'music' ? (
              <Music2 size={12} />
            ) : (
              <Mic2 size={12} />
            )}
            {firstVisibleResult.kind === 'music' ? '音乐结果' : '配音结果'}
            {visibleResults.length > 1 && (
              <span>· 共 {visibleResults.length} 条</span>
            )}
          </div>
          <audio
            src={firstVisibleResult.url}
            aria-label={node.title}
            controls
            className="h-8 w-full"
          />
        </div>
      );
    }
    if (firstVisibleResult && firstVisibleResult.kind === 'audio') {
      return (
        <div className="flex h-20 flex-col justify-center rounded-xl border border-sky-100 bg-sky-50 px-3">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold text-sky-700">
            <Music2 size={12} />
            参考音频
          </div>
          <audio
            src={firstVisibleResult.url}
            aria-label={node.title}
            controls
            className="h-8 w-full"
          />
        </div>
      );
    }
    if (firstVisibleResult && firstVisibleResult.kind === 'file') {
      return (
        <div className="flex h-20 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3">
          <FileText size={16} className="shrink-0 text-violet-600" />
          <p className="min-w-0 truncate text-xs font-semibold text-slate-700">
            {node.assetName ||
              getAssetNameFromUrl(firstVisibleResult.url) ||
              '参考文档'}
          </p>
        </div>
      );
    }
    if (firstVisibleResult && firstVisibleResult.kind === 'link') {
      return (
        <div className="flex h-20 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3">
          <Link2 size={16} className="shrink-0 text-violet-600" />
          <p
            className="min-w-0 truncate text-xs font-semibold text-slate-700"
            title={firstVisibleResult.url}
          >
            {node.assetName || firstVisibleResult.url}
          </p>
        </div>
      );
    }
    if (firstVisibleResult && firstVisibleResult.kind === 'video') {
      return (
        <div className="relative h-20 overflow-hidden rounded-xl bg-slate-950">
          <video
            src={firstVisibleResult.url}
            aria-label={node.title}
            className="h-full w-full object-cover"
            controls
          />
          {visibleResults.length > 1 && (
            <span className="pointer-events-none absolute right-1.5 top-1.5 rounded-full bg-slate-950/80 px-2 py-0.5 text-[10px] font-semibold text-white">
              共 {visibleResults.length} 条
            </span>
          )}
        </div>
      );
    }
    if (
      firstVisibleResult &&
      (firstVisibleResult.kind === 'text' ||
        firstVisibleResult.kind === 'image' ||
        node.kind === 'output')
    ) {
      return (
        <div className="relative h-20 overflow-hidden rounded-xl bg-slate-100">
          <img
            src={firstVisibleResult.url}
            alt={node.title}
            className="h-full w-full object-cover"
          />
          {visibleResults.length > 1 && (
            <span className="absolute bottom-1.5 right-1.5 rounded-full bg-slate-950/80 px-2 py-0.5 text-[10px] font-semibold text-white">
              共 {visibleResults.length} 个
            </span>
          )}
        </div>
      );
    }
    if (node.kind === 'video_analysis') {
      return (
        <div className="flex h-20 flex-col justify-center rounded-xl border border-cyan-100 bg-cyan-50/80 px-3 text-left">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold text-cyan-700">
            <MessageSquareText size={12} /> Qwen3.8 Omni Flash
          </div>
          <p className="line-clamp-3 whitespace-pre-line text-xs leading-5 text-slate-600">
            {node.analysisResult ||
              '连接一条视频后，分析主体、镜头、声音与可复用提示词'}
          </p>
        </div>
      );
    }
    if (node.kind === 'text') {
      return (
        <textarea
          value={node.prompt}
          onChange={(event) =>
            updateNode(node.id, { prompt: event.target.value, status: 'draft' })
          }
          onClick={(event) => event.stopPropagation()}
          aria-label={`${node.title}内容`}
          placeholder="输入创意提示词..."
          className={`${
            usesExpandedTextBox
              ? 'h-full min-h-0 flex-1 px-4 py-3 text-sm leading-6'
              : 'h-20 px-3 py-2 text-xs leading-5'
          } w-full resize-none rounded-xl border border-slate-200 bg-slate-50/90 text-slate-700 outline-none transition-colors focus:border-violet-400 focus:bg-white focus:ring-2 focus:ring-violet-100`}
        />
      );
    }
    if (node.kind === 'image' || node.kind === 'video') {
      const isVideoPlaceholder = node.kind === 'video';
      return (
        <div className="relative h-full w-full overflow-hidden rounded-[5px] bg-[#242424]">
          <div
            aria-hidden="true"
            className="absolute inset-0 flex items-center justify-center text-white/20"
          >
            {isVideoPlaceholder ? (
              <Play size={34} fill="currentColor" strokeWidth={0} />
            ) : (
              <ImageIcon size={42} fill="currentColor" strokeWidth={1.25} />
            )}
          </div>
          <span className="absolute bottom-3 left-3 text-[10px] font-medium text-white/45">
            等待生成
          </span>
        </div>
      );
    }
    return (
      <div className="flex h-20 min-w-0 items-center justify-center overflow-hidden rounded-xl bg-slate-50/70 px-4 text-center text-xs leading-5 text-slate-500">
        <p className="line-clamp-3 max-w-full whitespace-pre-line break-words [overflow-wrap:anywhere]">
          {node.prompt ||
            (node.kind === 'asset'
              ? '导入图片、视频、音频、文档，或粘贴网页链接'
              : '选中节点后，在下方简易设置中配置')}
        </p>
      </div>
    );
  };

  const selectedTextMode =
    selectedNode?.kind === 'text'
      ? selectedNode.textGenerationMode || 'image'
      : 'image';
  const selectedResultHistory = selectedNode
    ? getNodeResultHistory(selectedNode)
    : [];
  const selectedTextResults = selectedResultHistory.filter(
    (result) => result.type === selectedTextMode,
  );
  const selectedImageResults = selectedResultHistory.filter(
    (result) => result.type === 'image',
  );
  const selectedVideoResults = selectedResultHistory.filter(
    (result) => result.type === 'video',
  );
  const selectedAudioResults = selectedResultHistory.filter(
    (result) => result.type === 'audio',
  );
  const selectedTextImageConfig =
    selectedNode?.kind === 'text' ? selectedNode.textImageConfig || {} : {};
  const selectedTextImageModel =
    selectedNode?.kind === 'text'
      ? availableImageModels.includes(selectedTextImageConfig.model || '')
        ? selectedTextImageConfig.model!
        : defaultImageModel
      : defaultImageModel;
  const selectedTextImageModelConfig =
    mediaModelCatalog[selectedTextImageModel] || {};
  const selectedTextImageResolutions: string[] =
    selectedTextImageModelConfig.supported_resolutions || ['1K'];
  const selectedTextImageAspectRatios: string[] =
    selectedTextImageModelConfig.supported_aspect_ratios || IMAGE_ASPECT_RATIOS;
  const selectedTextImageResolution = selectedTextImageResolutions.includes(
    selectedTextImageConfig.resolution || '',
  )
    ? selectedTextImageConfig.resolution!
    : selectedTextImageResolutions[0] || '1K';
  const selectedTextImageCount = clampBatchCount(
    selectedTextImageConfig.count,
    maxImageBatchCount,
  );
  const selectedTextImagePricePerImage = getImagePricePerImage(
    selectedTextImageModel,
    selectedTextImageResolution,
    mediaConfig,
  );
  const selectedTextImagePriceCurrency = getModelPricingCurrency(
    selectedTextImageModelConfig,
  );
  const selectedTextVideoConfig =
    selectedNode?.kind === 'text' ? selectedNode.textVideoConfig || {} : {};
  const selectedTextVideoModel =
    selectedNode?.kind === 'text'
      ? availableTextVideoModels.includes(selectedTextVideoConfig.model || '')
        ? selectedTextVideoConfig.model!
        : defaultTextVideoModel
      : defaultTextVideoModel;
  const selectedTextVideoModelConfig =
    mediaModelCatalog[selectedTextVideoModel] || {};
  const selectedTextVideoResolutions: string[] =
    selectedTextVideoModelConfig.supported_resolutions || ['720p'];
  const selectedTextVideoAspectRatios: string[] =
    selectedTextVideoModelConfig.supported_aspect_ratios || VIDEO_ASPECT_RATIOS;
  const selectedTextVideoUsesTargetDuration =
    selectedTextVideoModelConfig.duration_parameter_enabled === true;
  const selectedTextVideoDurationRange: number[] =
    selectedTextVideoModelConfig.duration_range_seconds || [2, 15];
  const selectedTextVideoIsLite =
    selectedTextVideoModel === 'veo-3.1-lite-generate-preview';
  const selectedTextVideoExtensionCount =
    selectedTextVideoModelConfig.supports_extension === false ||
    selectedTextVideoIsLite
      ? 0
      : clamp(
          Number(selectedTextVideoConfig.extensionCount) || 0,
          0,
          maxVideoExtensionCount,
        );
  const selectedTextVideoDuration = clamp(
    Number(selectedTextVideoConfig.duration) ||
      Number(
        selectedTextVideoModelConfig.default_duration_seconds ||
          selectedTextVideoDurationRange[0] ||
          5,
      ),
    Number(selectedTextVideoDurationRange[0] || 2),
    Number(selectedTextVideoDurationRange[1] || 15),
  );
  const selectedTextVideoEffectiveDuration = selectedTextVideoUsesTargetDuration
    ? selectedTextVideoDuration
    : selectedTextVideoIsLite
      ? Number(selectedTextVideoModelConfig.max_duration_seconds || 8)
      : 8 + selectedTextVideoExtensionCount * 7;
  const selectedTextVideoResolution = selectedTextVideoResolutions.includes(
    selectedTextVideoConfig.resolution || '',
  )
    ? selectedTextVideoConfig.resolution!
    : selectedTextVideoResolutions[0] || '720p';
  const selectedTextVideoCount = clampBatchCount(
    selectedTextVideoConfig.count,
    maxVideoBatchCount,
  );
  const selectedTextVideoPricePerSecond = getVideoPricePerSecond(
    selectedTextVideoModel,
    selectedTextVideoResolution,
    mediaConfig,
  );
  const selectedTextVideoPriceCurrency = getModelPricingCurrency(
    selectedTextVideoModelConfig,
  );
  const selectedTextImageIsGenerating =
    selectedNode?.kind === 'text'
      ? generatingNodeIds.has(selectedNode.id)
      : false;
  const selectedTextVideoIsGenerating =
    selectedNode?.kind === 'text'
      ? generatingNodeIds.has(selectedNode.id)
      : false;
  const selectedImageModel =
    selectedNode?.kind === 'image'
      ? availableImageModels.includes(selectedNode.model || '')
        ? selectedNode.model!
        : defaultImageModel
      : defaultImageModel;
  const selectedImageModelConfig = mediaModelCatalog[selectedImageModel] || {};
  const selectedImageSupportedModes = getSupportedImageGenerationModes(
    selectedImageModelConfig,
  );
  const selectedImageGenerationMode = resolveImageGenerationMode(
    selectedImageModelConfig,
    selectedNode?.kind === 'image'
      ? selectedNode.imageGenerationMode
      : undefined,
    'reference_image',
  );
  const selectedImageResolutions: string[] =
    selectedImageModelConfig.supported_resolutions || ['1K'];
  const selectedImageAspectRatios: string[] =
    selectedImageModelConfig.supported_aspect_ratios || IMAGE_ASPECT_RATIOS;
  const selectedImageResolution = selectedImageResolutions.includes(
    selectedNode?.resolution || '',
  )
    ? selectedNode!.resolution!
    : selectedImageResolutions[0] || '1K';
  const selectedImageCount = clampBatchCount(
    selectedNode?.count,
    maxImageBatchCount,
  );
  const selectedImagePricePerImage = getImagePricePerImage(
    selectedImageModel,
    selectedImageResolution,
    mediaConfig,
  );
  const selectedImagePriceCurrency = getModelPricingCurrency(
    selectedImageModelConfig,
  );
  const selectedImagePrompt =
    selectedNode?.kind === 'image' ? resolveGenerationPrompt(selectedNode) : '';
  const selectedImageReferences =
    selectedNode?.kind === 'image'
      ? getOrderedImageReferences(selectedNode.id)
      : [];
  const selectedImageReferenceCount = selectedImageReferences.length;
  const selectedImageIsGenerating =
    selectedNode?.kind === 'image'
      ? generatingNodeIds.has(selectedNode.id)
      : false;
  const selectedVideoModel =
    selectedNode?.kind === 'video'
      ? availableVideoModels.includes(selectedNode.model || '')
        ? selectedNode.model!
        : defaultVideoModel
      : defaultVideoModel;
  const selectedVideoModelConfig = mediaModelCatalog[selectedVideoModel] || {};
  const selectedVideoSupportedModes = getSupportedVideoGenerationModes(
    selectedVideoModelConfig,
  );
  const selectedVideoGenerationMode = resolveVideoGenerationMode(
    selectedVideoModelConfig,
    selectedNode?.kind === 'video'
      ? selectedNode.videoGenerationMode
      : undefined,
    'first_frame',
  );
  const selectedVideoResolutions: string[] =
    selectedVideoModelConfig.supported_resolutions || ['720p'];
  const selectedVideoAspectRatios: string[] =
    selectedVideoModelConfig.supported_aspect_ratios || VIDEO_ASPECT_RATIOS;
  const selectedVideoUsesTargetDuration =
    selectedVideoModelConfig.duration_parameter_enabled === true;
  const selectedVideoDurationRange: number[] =
    selectedVideoModelConfig.duration_range_seconds || [2, 15];
  const selectedVideoIsLite =
    selectedVideoModel === 'veo-3.1-lite-generate-preview';
  const selectedVideoExtensionCount =
    selectedVideoModelConfig.supports_extension === false || selectedVideoIsLite
      ? 0
      : clamp(
          Number(selectedNode?.extensionCount) || 0,
          0,
          maxVideoExtensionCount,
        );
  const selectedVideoDuration = clamp(
    Number(selectedNode?.duration) ||
      Number(
        selectedVideoModelConfig.default_duration_seconds ||
          selectedVideoDurationRange[0] ||
          5,
      ),
    Number(selectedVideoDurationRange[0] || 2),
    Number(selectedVideoDurationRange[1] || 15),
  );
  const selectedVideoEffectiveDuration = selectedVideoUsesTargetDuration
    ? selectedVideoDuration
    : selectedVideoIsLite
      ? Number(selectedVideoModelConfig.max_duration_seconds || 8)
      : 8 + selectedVideoExtensionCount * 7;
  const selectedVideoResolution = selectedVideoResolutions.includes(
    selectedNode?.resolution || '',
  )
    ? selectedNode!.resolution!
    : selectedVideoResolutions[0] || '720p';
  const selectedVideoCount = clampBatchCount(
    selectedNode?.count,
    maxVideoBatchCount,
  );
  const selectedVideoPricePerSecond = getVideoPricePerSecond(
    selectedVideoModel,
    selectedVideoResolution,
    mediaConfig,
    selectedNode?.kind === 'video' &&
      getVideoReferenceSources(selectedNode.id).some(
        (source) => source.type === AssetType.VIDEO,
      ),
  );
  const selectedVideoPriceCurrency = getModelPricingCurrency(
    selectedVideoModelConfig,
  );
  const selectedVideoPrompt =
    selectedNode?.kind === 'video' ? resolveGenerationPrompt(selectedNode) : '';
  const selectedVideoReferences =
    selectedNode?.kind === 'video'
      ? getVideoReferenceSources(selectedNode.id)
      : [];
  const selectedVideoImageReferenceCount = selectedVideoReferences.filter(
    (source) => source.type === AssetType.IMAGE,
  ).length;
  const selectedVideoReferenceVideoCount = selectedVideoReferences.filter(
    (source) => source.type === AssetType.VIDEO,
  ).length;
  const selectedVideoHasRequiredReferences =
    selectedVideoGenerationMode === 'text_to_video' ||
    (selectedVideoGenerationMode === 'reference_image' &&
      selectedVideoImageReferenceCount > 0) ||
    (selectedVideoGenerationMode === 'reference_video' &&
      selectedVideoReferenceVideoCount > 0) ||
    (selectedVideoGenerationMode === 'reference_assets' &&
      selectedVideoReferences.length > 0) ||
    (selectedVideoGenerationMode === 'first_frame' &&
      selectedVideoImageReferenceCount >= 1) ||
    (selectedVideoGenerationMode === 'first_last_frame' &&
      selectedVideoImageReferenceCount >= 2);
  const selectedVideoIsGenerating =
    selectedNode?.kind === 'video'
      ? generatingNodeIds.has(selectedNode.id)
      : false;
  const selectedMusicModel =
    selectedNode?.kind === 'music'
      ? availableMusicModels.includes(selectedNode.model || '')
        ? selectedNode.model!
        : defaultMusicModel
      : defaultMusicModel;
  const selectedMusicModelConfig = mediaModelCatalog[selectedMusicModel] || {};
  const selectedMusicPrompt =
    selectedNode?.kind === 'music' ? resolveGenerationPrompt(selectedNode) : '';
  const selectedMusicReferenceCount =
    selectedNode?.kind === 'music'
      ? resolveImageReferenceAssets(selectedNode.id).length
      : 0;
  const selectedMusicIsGenerating =
    selectedNode?.kind === 'music'
      ? generatingNodeIds.has(selectedNode.id)
      : false;
  const selectedTTSModel =
    selectedNode?.kind === 'tts'
      ? availableTTSModels.includes(selectedNode.model || '')
        ? selectedNode.model!
        : defaultTTSModel
      : defaultTTSModel;
  const selectedTTSModelConfig = mediaModelCatalog[selectedTTSModel] || {};
  const selectedTTSPrompt =
    selectedNode?.kind === 'tts' ? resolveGenerationPrompt(selectedNode) : '';
  const selectedTTSIsGenerating =
    selectedNode?.kind === 'tts'
      ? generatingNodeIds.has(selectedNode.id)
      : false;

  const insertImageReferenceMention = (node: CanvasNodeData, alias: string) => {
    const mention = `@${alias}`;
    const trailingMention = /@[^\s@]*$/;
    const nextPrompt = trailingMention.test(node.prompt)
      ? node.prompt.replace(trailingMention, `${mention} `)
      : `${node.prompt}${node.prompt && !/\s$/.test(node.prompt) ? ' ' : ''}${mention} `;
    clearNodeError(node.id);
    updateNode(node.id, { prompt: nextPrompt, status: 'draft' });
  };

  const renderImageReferenceMentions = (
    node: CanvasNodeData,
    compact = false,
  ) => {
    const references =
      node.kind === 'video' && selectedVideoGenerationMode === 'reference_video'
        ? getOrderedVideoReferences(node.id)
        : node.kind === 'video' &&
            selectedVideoGenerationMode === 'reference_assets'
          ? [
              ...getOrderedImageReferences(node.id),
              ...getOrderedVideoReferences(node.id),
              ...getOrderedAudioReferences(node.id),
              ...getOrderedFileReferences(node.id),
              ...getOrderedLinkReferences(node.id),
            ]
          : getOrderedImageReferences(node.id);
    if (references.length === 0) return null;

    const mixedOmni = references.some(
      (item) => item.mediaType && item.mediaType !== references[0]?.mediaType,
    );

    return (
      <div
        className={`${compact ? 'mt-2' : ''} rounded-xl border border-violet-100 bg-violet-50/55 p-2`}
      >
        <div className="flex items-center justify-between gap-2 px-0.5">
          <span className="text-[10px] font-semibold text-violet-700">
            {mixedOmni
              ? '全能参考顺序'
              : `参考${getCanvasAssetTypeLabel(references[0]?.mediaType)}顺序`}
          </span>
          <span className="text-[10px] text-slate-400">
            {mixedOmni
              ? '按连线顺序编号；提示词可用 @图片N / @视频N / @音频N / @文档1 / @网页1'
              : references[0]?.mediaType === 'video'
                ? '按连线顺序编号，视频用主结果'
                : '按连线顺序编号，多图节点仅用主图'}
          </span>
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {references.map((reference) => (
            <ImageReferenceHoverChip
              key={reference.id}
              alias={reference.alias}
              url={reference.url}
              sourceTitle={reference.sourceTitle}
              mediaType={reference.mediaType}
              onClick={() => insertImageReferenceMention(node, reference.alias)}
              onRemove={
                reference.sourceNodeId !== node.id
                  ? () =>
                      removeImageReference(
                        node.id,
                        reference.sourceNodeId,
                        undefined,
                        reference.mediaType || 'image',
                      )
                  : undefined
              }
            />
          ))}
        </div>
      </div>
    );
  };

  const renderQuickNodeSettings = () => {
    if (!selectedNode) return null;

    const node = selectedNode;
    const meta = getNodeMeta(node.kind);
    const isVideoAnalysisResultNode =
      node.kind === 'text' &&
      node.title === '视频分析结果' &&
      (typeof node.width === 'number' || typeof node.height === 'number');
    const sourceGenerationPrompt = node.sourceGenerationPrompt?.trim() || '';

    // 视频分析的正文已经显示在扩大后的节点中；下方不再复用文本生成参数，
    // 只回显分析前填写的提示词，并与节点一起移动。
    if (isVideoAnalysisResultNode) {
      const nodeDimensions = getCanvasNodeDimensions(node);
      return (
        <section
          data-canvas-node-settings={node.id}
          aria-label="视频分析结果的分析提示词"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
          onDoubleClick={(event) => event.stopPropagation()}
          className={`canvas-quick-settings ${theme === 'dark' ? 'canvas-quick-settings--dark' : ''}`}
          style={{
            position: 'absolute',
            zIndex: 180,
            left: node.x,
            top: node.y + nodeDimensions.height + QUICK_SETTINGS_GAP,
            width: nodeDimensions.width,
          }}
        >
          <div className="max-h-36 overflow-y-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50/90 px-3 py-2.5 text-sm leading-6 text-slate-700">
            {sourceGenerationPrompt || '未保存分析前的提示词'}
          </div>
        </section>
      );
    }

    const Icon = meta.icon;
    const isGenerating = generatingNodeIds.has(node.id);
    const isTextImage = node.kind === 'text' && selectedTextMode === 'image';
    const isTextVideo = node.kind === 'text' && selectedTextMode === 'video';
    const isImageGeneration = isTextImage || node.kind === 'image';
    const isVideoGeneration = isTextVideo || node.kind === 'video';
    const isVideoAnalysis = node.kind === 'video_analysis';
    const videoCancelState = isVideoGeneration
      ? videoTaskCancelStates[node.id]
      : undefined;
    const canCancelVideoTask = Boolean(
      videoCancelState?.canCancel || videoCancelState?.isSubmitting,
    );
    const showGenerationCancel =
      isGenerating && (isImageGeneration || isVideoGeneration);
    const videoCancelTitle = isImageGeneration
      ? '当前图片生成接口为同步请求，无法在提交后取消'
      : videoCancelState?.isCancelling
        ? '正在取消视频任务'
        : canCancelVideoTask
          ? '取消生成'
          : videoCancelState?.reason || '当前厂商任务不支持取消';
    const isGenerative = [
      'text',
      'image',
      'video',
      'video_analysis',
      'music',
      'tts',
    ].includes(node.kind);
    const videoUsesTargetDuration = isTextVideo
      ? selectedTextVideoUsesTargetDuration
      : selectedVideoUsesTargetDuration;
    const videoDurationRange = isTextVideo
      ? selectedTextVideoDurationRange
      : selectedVideoDurationRange;
    const videoIsLite = isTextVideo
      ? selectedTextVideoIsLite
      : selectedVideoIsLite;
    const videoInputValue = videoUsesTargetDuration
      ? isTextVideo
        ? selectedTextVideoDuration
        : selectedVideoDuration
      : isTextVideo
        ? selectedTextVideoExtensionCount
        : selectedVideoExtensionCount;
    const videoInputMax = videoUsesTargetDuration
      ? videoDurationRange[1]
      : videoIsLite
        ? 0
        : maxVideoExtensionCount;
    const videoDurationStep =
      (isTextVideo
        ? selectedTextVideoModelConfig.duration_options_seconds
        : selectedVideoModelConfig.duration_options_seconds) || [];
    const activeVideoModelConfig = isTextVideo
      ? selectedTextVideoModelConfig
      : selectedVideoModelConfig;
    const activeVideoModel = isTextVideo
      ? selectedTextVideoModel
      : selectedVideoModel;
    const activeVideoResolution = isTextVideo
      ? selectedTextVideoResolution
      : selectedVideoResolution;
    const activeVideoEffectiveDuration = isTextVideo
      ? selectedTextVideoEffectiveDuration
      : selectedVideoEffectiveDuration;
    const activeVideoPricePerSecond = isTextVideo
      ? selectedTextVideoPricePerSecond
      : selectedVideoPricePerSecond;
    const activeVideoPriceCurrency = isTextVideo
      ? selectedTextVideoPriceCurrency
      : selectedVideoPriceCurrency;
    const activeImageModelConfig = isTextImage
      ? selectedTextImageModelConfig
      : selectedImageModelConfig;
    const activeImageModel = isTextImage
      ? selectedTextImageModel
      : selectedImageModel;
    const activeImageResolution = isTextImage
      ? selectedTextImageResolution
      : selectedImageResolution;
    const activeImageCount = isTextImage
      ? selectedTextImageCount
      : selectedImageCount;
    const activeImagePricePerImage = isTextImage
      ? selectedTextImagePricePerImage
      : selectedImagePricePerImage;
    const activeImagePriceCurrency = isTextImage
      ? selectedTextImagePriceCurrency
      : selectedImagePriceCurrency;
    const activeVideoGenerationMode: VideoGenerationMode = isTextVideo
      ? 'text_to_video'
      : selectedVideoGenerationMode;
    const activeImageGenerationMode: ImageGenerationMode = isTextImage
      ? 'text_to_image'
      : selectedImageGenerationMode;
    const promptReferences =
      node.kind === 'image'
        ? getOrderedImageReferences(node.id)
        : node.kind === 'video'
          ? activeVideoGenerationMode === 'reference_video'
            ? getOrderedVideoReferences(node.id)
            : activeVideoGenerationMode === 'text_to_video'
              ? []
              : activeVideoGenerationMode === 'reference_assets'
                ? [
                    ...getOrderedImageReferences(node.id),
                    ...getOrderedVideoReferences(node.id),
                    ...getOrderedAudioReferences(node.id),
                    ...getOrderedFileReferences(node.id),
                    ...getOrderedLinkReferences(node.id),
                  ]
                : getOrderedImageReferences(node.id)
          : [];

    const activeConfig =
      node.kind === 'text'
        ? (selectedTextMode === 'video'
            ? node.textVideoConfig
            : node.textImageConfig) || {}
        : node;
    const modelOptions = isImageGeneration
      ? availableImageModels
      : isTextVideo
        ? availableTextVideoModels
        : node.kind === 'video'
          ? availableVideoModels
          : isVideoAnalysis
            ? [DEFAULT_VIDEO_ANALYSIS_MODEL]
            : node.kind === 'music'
              ? availableMusicModels
              : node.kind === 'tts'
                ? availableTTSModels
                : [];
    const sortedModelOptions = sortModelsByFavorite(
      modelOptions,
      favoriteModels,
    );
    const toggleFavoriteModel = (model: string) => {
      setFavoriteModels((current) => {
        const next = current.includes(model)
          ? current.filter((id) => id !== model)
          : [...current, model];
        writeStoredFavoriteModels(next);
        return next;
      });
    };
    const activeModel = isTextImage
      ? selectedTextImageModel
      : isTextVideo
        ? selectedTextVideoModel
        : node.kind === 'image'
          ? selectedImageModel
          : node.kind === 'video'
            ? selectedVideoModel
            : isVideoAnalysis
              ? DEFAULT_VIDEO_ANALYSIS_MODEL
              : node.kind === 'music'
                ? selectedMusicModel
                : node.kind === 'tts'
                  ? selectedTTSModel
                  : '';
    const resolutionOptions = isTextImage
      ? selectedTextImageResolutions
      : isTextVideo
        ? selectedTextVideoResolutions
        : node.kind === 'image'
          ? selectedImageResolutions
          : node.kind === 'video'
            ? selectedVideoResolutions
            : [];
    const aspectOptions = isVideoGeneration
      ? isTextVideo
        ? selectedTextVideoAspectRatios
        : selectedVideoAspectRatios
      : isImageGeneration
        ? isTextImage
          ? selectedTextImageAspectRatios
          : selectedImageAspectRatios
        : [];
    const updateGenerationSettings = (
      updates: Partial<
        Pick<
          CanvasNodeData,
          | 'model'
          | 'aspectRatio'
          | 'resolution'
          | 'duration'
          | 'extensionCount'
          | 'imageGenerationMode'
          | 'videoGenerationMode'
          | 'count'
        >
      >,
    ) => {
      clearNodeError(node.id);
      if (isVideoGeneration)
        rememberGenerationSettings('video', { ...activeConfig, ...updates });
      else if (isImageGeneration)
        rememberGenerationSettings('image', { ...activeConfig, ...updates });
      if (node.kind === 'text') {
        if (selectedTextMode === 'video') {
          updateNode(node.id, {
            textVideoConfig: { ...(node.textVideoConfig || {}), ...updates },
            status: 'draft',
          });
        } else {
          updateNode(node.id, {
            textImageConfig: { ...(node.textImageConfig || {}), ...updates },
            status: 'draft',
          });
        }
        return;
      }
      updateNode(node.id, { ...updates, status: 'draft' });
    };

    const generationPrompt =
      node.kind === 'text'
        ? node.prompt.trim()
        : node.kind === 'image'
          ? selectedImagePrompt
          : node.kind === 'video'
            ? selectedVideoPrompt
            : node.kind === 'music'
              ? selectedMusicPrompt
              : node.kind === 'tts'
                ? selectedTTSPrompt
                : isVideoAnalysis
                  ? node.prompt.trim()
                  : '';
    const missingReference =
      node.kind === 'image'
        ? activeImageGenerationMode === 'reference_image' &&
          selectedImageReferenceCount === 0
        : node.kind === 'video'
          ? activeVideoGenerationMode === 'reference_image'
            ? selectedVideoImageReferenceCount < 1
            : activeVideoGenerationMode === 'reference_video'
              ? selectedVideoReferenceVideoCount < 1
              : activeVideoGenerationMode === 'reference_assets'
                ? selectedVideoReferences.length === 0
                : activeVideoGenerationMode === 'first_frame'
                  ? selectedVideoImageReferenceCount < 1
                  : activeVideoGenerationMode === 'first_last_frame'
                    ? selectedVideoImageReferenceCount < 2
                    : false
          : false;
    const hasVideoAnalysisSource =
      isVideoAnalysis &&
      getVideoReferenceSources(node.id).some(
        (source) => source.type === AssetType.VIDEO,
      );
    const generateDisabled = isVideoAnalysis
      ? !hasVideoAnalysisSource || isGenerating
      : !generationPrompt ||
        missingReference ||
        isGenerating ||
        ((isImageGeneration || isVideoGeneration) && hasSaveConflict);
    const runGeneration = () => {
      if (isImageGeneration) void generateImageNode(node.id);
      else if (isVideoGeneration) void generateVideoNode(node.id);
      else if (isVideoAnalysis) void generateVideoAnalysisNode(node.id);
      else if (node.kind === 'music') void generateMusicNode(node.id);
      else if (node.kind === 'tts') void generateTTSNode(node.id);
    };
    const GenerateIcon = isVideoAnalysis
      ? MessageSquareText
      : isVideoGeneration
        ? Video
        : node.kind === 'music'
          ? Music2
          : node.kind === 'tts'
            ? Mic2
            : Sparkles;
    const generateBatchCount = clampBatchCount(
      activeConfig.count,
      isVideoGeneration ? maxVideoBatchCount : maxImageBatchCount,
    );
    const generateLabel = isGenerating
      ? isVideoAnalysis
        ? '正在分析视频...'
        : isVideoGeneration
          ? '正在生成视频...'
          : node.kind === 'music'
            ? '正在生成音乐...'
            : node.kind === 'tts'
              ? '正在生成配音...'
              : '正在生成图片...'
      : isVideoAnalysis
        ? node.analysisResult
          ? '重新分析视频'
          : '分析视频'
        : isVideoGeneration
          ? generateBatchCount > 1
            ? `生成 ${generateBatchCount} 条视频`
            : node.resultUrl
              ? '重新生成'
              : '生成视频'
          : node.kind === 'music'
            ? node.resultUrl
              ? '重新生成'
              : '生成音乐'
            : node.kind === 'tts'
              ? node.resultUrl
                ? '重新生成'
                : '生成配音'
              : generateBatchCount > 1
                ? `生成 ${generateBatchCount} 张图片`
                : node.resultUrl
                  ? '重新生成'
                  : '生成图片';
    const generateButtonClass = isVideoAnalysis
      ? 'bg-cyan-600 hover:bg-cyan-700 focus:ring-cyan-400'
      : isVideoGeneration
        ? 'bg-fuchsia-600 hover:bg-fuchsia-700 focus:ring-fuchsia-400'
        : node.kind === 'music'
          ? 'bg-pink-600 hover:bg-pink-700 focus:ring-pink-400'
          : node.kind === 'tts'
            ? 'bg-sky-600 hover:bg-sky-700 focus:ring-sky-400'
            : 'bg-violet-600 hover:bg-violet-700 focus:ring-violet-400';
    const promptPlaceholder =
      node.kind === 'text'
        ? '输入创意提示词，描述想要生成的画面或视频...'
        : node.kind === 'image'
          ? activeImageGenerationMode === 'reference_image'
            ? '描述如何基于参考图生成新图片；输入 @ 可引用指定图片...'
            : '描述希望生成的图片内容、风格、构图和细节...'
          : node.kind === 'video'
            ? activeVideoGenerationMode === 'reference_video'
              ? '描述镜头、运动、主体和声音；输入 @ 可引用指定视频...'
              : activeVideoGenerationMode === 'reference_assets'
                ? '描述镜头、运动、主体和声音；输入 @ 可引用图片、视频、音频、文档或网页...'
                : '描述镜头、运动、主体和声音；输入 @ 可引用指定图片...'
            : isVideoAnalysis
              ? '可选：说明需要重点分析的主体、镜头、节奏、口播或可复用提示词...'
              : node.kind === 'music'
                ? '描述音乐风格、情绪、节奏和乐器...'
                : '输入需要转换为语音的文案...';
    const referenceHint =
      isVideoAnalysis && !hasVideoAnalysisSource
        ? '请先连接一条已导入或已生成的视频'
        : node.kind === 'image' &&
            activeImageGenerationMode === 'reference_image' &&
            selectedImageReferenceCount === 0
          ? '请先连接一张图片或文生图结果'
          : node.kind === 'video' && missingReference
            ? activeVideoGenerationMode === 'reference_image'
              ? '参考图片生成需要至少连接一张图片'
              : activeVideoGenerationMode === 'reference_video'
                ? '参考视频生成需要至少连接一条视频'
                : activeVideoGenerationMode === 'reference_assets'
                  ? '全能参考需要至少连接一张图片、一条视频、一段音频、一份文档或一个网页'
                  : activeVideoGenerationMode === 'first_last_frame'
                    ? '首尾帧生成需要按顺序连接两张图片'
                    : '首帧生成需要连接一张输入图片'
            : null;
    const generationModeOptions: Array<{ value: string; label: string }> =
      node.kind === 'video'
        ? VIDEO_GENERATION_MODE_OPTIONS
        : IMAGE_GENERATION_MODE_OPTIONS;
    const supportedGenerationModes: string[] =
      node.kind === 'video'
        ? selectedVideoSupportedModes
        : selectedImageSupportedModes;
    const activeGenerationMode =
      node.kind === 'video'
        ? activeVideoGenerationMode
        : activeImageGenerationMode;
    const activeGenerationModeLabel =
      generationModeOptions.find(
        (option) => option.value === activeGenerationMode,
      )?.label || '生成模式';
    const activeModelLabel = isVideoAnalysis
      ? 'Qwen3.8 Omni Flash'
      : mediaModelCatalog[activeModel]?.label || activeModel || '选择模型';
    const activeVideoAnalysisPromptPreset = isVideoAnalysis
      ? VIDEO_ANALYSIS_PROMPT_PRESETS.find(
          (preset) => preset.prompt === node.prompt.trim(),
        )
      : undefined;
    const activeVideoAnalysisPromptLabel =
      activeVideoAnalysisPromptPreset?.label || '固定提示词';
    const activeAspectRatio = aspectOptions.includes(
      activeConfig.aspectRatio || '',
    )
      ? activeConfig.aspectRatio!
      : aspectOptions[0];
    const activeResolution = resolutionOptions.includes(
      activeConfig.resolution || '',
    )
      ? activeConfig.resolution!
      : resolutionOptions[0];
    const maxBatchCount = isVideoGeneration
      ? maxVideoBatchCount
      : maxImageBatchCount;
    const activeBatchCount = clampBatchCount(activeConfig.count, maxBatchCount);
    const batchCountOptions = getBatchCountOptions(
      maxBatchCount,
      isVideoGeneration ? VIDEO_BATCH_COUNT_PRESETS : IMAGE_BATCH_COUNT_PRESETS,
    );
    const batchUnitLabel = isVideoGeneration ? '条' : '张';
    const videoInputMin = videoUsesTargetDuration ? videoDurationRange[0] : 0;
    const videoInputStep =
      videoDurationStep.length > 1
        ? Math.max(
            1,
            Number(videoDurationStep[1] ?? 1) -
              Number(videoDurationStep[0] ?? 0),
          )
        : 1;
    const renderGenerationModeIcon = (mode: string, size = 14) => {
      if (mode === 'text_to_image' || mode === 'text_to_video')
        return <TextCursorInput size={size} />;
      if (mode === 'reference_assets') return <Layers size={size} />;
      if (mode === 'reference_video') return <Video size={size} />;
      return <ImageIcon size={size} />;
    };
    const selectGenerationModel = (nextModel: string) => {
      const nextModelConfig = mediaModelCatalog[nextModel] || {};
      const nextResolutions: string[] =
        nextModelConfig.supported_resolutions || resolutionOptions;
      const nextAspectRatios: string[] =
        nextModelConfig.supported_aspect_ratios || aspectOptions;
      const nextDurationRange: number[] =
        nextModelConfig.duration_range_seconds || videoDurationRange;
      const nextDurationOptions: number[] =
        nextModelConfig.duration_options_seconds || [];
      updateGenerationSettings({
        model: nextModel,
        ...(isImageGeneration
          ? {
              imageGenerationMode: resolveImageGenerationMode(
                nextModelConfig,
                activeImageGenerationMode,
                'reference_image',
              ),
              aspectRatio: nextAspectRatios.includes(
                activeConfig.aspectRatio || '',
              )
                ? activeConfig.aspectRatio
                : nextAspectRatios[0],
              resolution: nextResolutions.includes(
                activeConfig.resolution || '',
              )
                ? activeConfig.resolution
                : nextResolutions[0],
            }
          : {}),
        ...(isVideoGeneration
          ? {
              videoGenerationMode: resolveVideoGenerationMode(
                nextModelConfig,
                activeVideoGenerationMode,
                'first_frame',
              ),
              aspectRatio: nextAspectRatios.includes(
                activeConfig.aspectRatio || '',
              )
                ? activeConfig.aspectRatio
                : nextAspectRatios[0],
              resolution: nextResolutions.includes(
                activeConfig.resolution || '',
              )
                ? activeConfig.resolution
                : nextResolutions[0],
              duration:
                nextDurationOptions.length > 0
                  ? nextDurationOptions.includes(Number(activeConfig.duration))
                    ? Number(activeConfig.duration)
                    : Number(
                        nextModelConfig.default_duration_seconds ||
                          nextDurationOptions[0],
                      )
                  : clamp(
                      Number(activeConfig.duration) ||
                        Number(
                          nextModelConfig.default_duration_seconds ||
                            nextDurationRange[0] ||
                            5,
                        ),
                      Number(nextDurationRange[0] || 2),
                      Number(nextDurationRange[1] || 15),
                    ),
              extensionCount:
                nextModelConfig.supports_extension === false
                  ? 0
                  : Number(activeConfig.extensionCount) || 0,
            }
          : {}),
      });
    };

    const settingsSummary = [
      activeAspectRatio,
      activeResolution === '4k' ? '4K' : activeResolution,
      isVideoGeneration ? `${activeVideoEffectiveDuration}s` : '',
      isImageGeneration || isVideoGeneration
        ? `${activeBatchCount}${batchUnitLabel}`
        : '',
    ]
      .filter(Boolean)
      .join(' · ');
    const compactCard = !promptEditorExpanded;
    const settingsCard = (
      <section
        ref={quickSettingsRef}
        data-canvas-node-settings={node.id}
        aria-label={`${node.title}简易设置`}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => event.stopPropagation()}
        onDoubleClick={(event) => event.stopPropagation()}
        className={
          promptEditorExpanded
            ? `canvas-prompt-expand-panel ${theme === 'dark' ? 'canvas-prompt-expand-panel--dark' : ''}`
            : `canvas-quick-settings ${theme === 'dark' ? 'canvas-quick-settings--dark' : ''}`
        }
        style={
          promptEditorExpanded
            ? undefined
            : {
                left: quickSettingsLayout?.left ?? -9999,
                top: quickSettingsLayout?.top ?? -9999,
                width: QUICK_SETTINGS_WIDTH,
                visibility: quickSettingsLayout ? 'visible' : 'hidden',
              }
        }
      >
        {!compactCard && (
          <div className="flex items-center gap-2">
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${meta.surface} ${meta.accent}`}
            >
              <Icon size={15} />
            </span>
            <input
              value={node.title}
              onChange={(event) =>
                updateNode(node.id, {
                  title: event.target.value,
                  status: 'draft',
                })
              }
              aria-label="节点名称"
              className="min-w-0 flex-1 border-0 bg-transparent px-1 text-sm font-semibold text-slate-900 outline-none focus:ring-0"
            />
            <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-500">
              {meta.label}
            </span>
            <button
              type="button"
              onClick={() => {
                setSelectedNodeId(null);
                setSelectedNodeIds(new Set());
                setSelectedEdgeId(null);
              }}
              aria-label="关闭简易设置"
              className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition-colors duration-200 hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-violet-400"
            >
              <X size={15} />
            </button>
          </div>
        )}

        {!compactCard && node.kind === 'text' && (
          <div
            role="tablist"
            aria-label="文本生成类型"
            className="mt-3 flex items-center gap-1 rounded-xl bg-slate-100 p-1"
          >
            <button
              type="button"
              role="tab"
              aria-selected={selectedTextMode === 'image'}
              onClick={() => {
                clearNodeError(node.id);
                updateNode(node.id, {
                  textGenerationMode: 'image',
                  status: 'draft',
                });
              }}
              className={`flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-lg text-xs font-semibold transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${selectedTextMode === 'image' ? 'bg-white text-violet-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              <ImageIcon size={13} /> 图片
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={selectedTextMode === 'video'}
              onClick={() => {
                clearNodeError(node.id);
                updateNode(node.id, {
                  textGenerationMode: 'video',
                  status: 'draft',
                });
              }}
              className={`flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-lg text-xs font-semibold transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-fuchsia-400 ${selectedTextMode === 'video' ? 'bg-white text-fuchsia-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              <Video size={13} /> 视频
            </button>
          </div>
        )}

        {node.kind === 'asset' && (
          <div
            className={`${compactCard ? 'mt-0' : 'mt-3'} grid grid-cols-2 gap-2`}
          >
            <button
              type="button"
              onClick={() => openLocalAssetPicker(node.id)}
              disabled={isImportingAsset}
              className="flex h-10 cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-cyan-200 bg-cyan-50 text-xs font-semibold text-cyan-800 transition-colors duration-200 hover:bg-cyan-100 focus:outline-none focus:ring-2 focus:ring-cyan-400 disabled:cursor-wait disabled:opacity-60"
            >
              {isImportingAsset && localAssetNodeId === node.id ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Upload size={15} />
              )}
              {node.resultUrl ? '更换本地素材' : '本地导入'}
            </button>
            <button
              type="button"
              onClick={() => setCloudAssetNodeId(node.id)}
              className="flex h-10 cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50 text-xs font-semibold text-violet-800 transition-colors duration-200 hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
            >
              <Cloud size={15} /> {node.resultUrl ? '更换云素材' : '云素材库'}
            </button>
            {node.resultUrl && (
              <button
                type="button"
                onClick={() => clearImportedAsset(node.id)}
                className="col-span-2 flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-lg text-xs font-medium text-slate-500 transition-colors duration-200 hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-300"
              >
                <Trash2 size={13} /> 移除当前素材
              </button>
            )}
          </div>
        )}

        {node.kind === 'output' && (
          <div
            className={`${compactCard ? 'mt-0' : 'mt-3'} rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs leading-5 text-emerald-700`}
          >
            输出节点会自动汇总已连接的上游生成结果。
          </div>
        )}

        {compactCard && !isGenerative && (
          <div className="mb-2 flex items-center gap-2">
            <span
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${meta.surface} ${meta.accent}`}
            >
              <Icon size={14} />
            </span>
            <span className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800">
              {node.title}
            </span>
            <button
              type="button"
              onClick={() => deleteNode(node.id)}
              aria-label="删除节点"
              className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-300"
            >
              <Trash2 size={15} />
            </button>
          </div>
        )}

        {isGenerative && (
          <>
            <PromptMentionEditor
              compact={compactCard}
              expanded={promptEditorExpanded}
              value={node.prompt}
              references={promptReferences}
              ariaLabel={`${meta.label}提示词`}
              placeholder={promptPlaceholder}
              showReferenceTools={
                node.kind === 'image' || node.kind === 'video'
              }
              toolbarExtra={
                compactCard && node.kind === 'text' ? (
                  <div
                    role="tablist"
                    aria-label="文本生成类型"
                    className="flex items-center gap-1"
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={selectedTextMode === 'image'}
                      onClick={() => {
                        clearNodeError(node.id);
                        updateNode(node.id, {
                          textGenerationMode: 'image',
                          status: 'draft',
                        });
                      }}
                      className={`canvas-prompt-chip-btn ${selectedTextMode === 'image' ? 'is-open' : ''}`}
                    >
                      <ImageIcon size={13} />
                      图片
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={selectedTextMode === 'video'}
                      onClick={() => {
                        clearNodeError(node.id);
                        updateNode(node.id, {
                          textGenerationMode: 'video',
                          status: 'draft',
                        });
                      }}
                      className={`canvas-prompt-chip-btn ${selectedTextMode === 'video' ? 'is-open' : ''}`}
                    >
                      <Video size={13} />
                      视频
                    </button>
                  </div>
                ) : null
              }
              tone={theme}
              onToggleExpand={() => setPromptEditorExpanded((open) => !open)}
              onChange={(prompt) => {
                clearNodeError(node.id);
                updateNode(node.id, { prompt, status: 'draft' });
              }}
              onReorderReferences={(fromIndex, toIndex, currentValue) => {
                clearNodeError(node.id);
                reorderImageReferences(
                  node.id,
                  fromIndex,
                  toIndex,
                  currentValue,
                  promptReferences[fromIndex]?.mediaType === 'video'
                    ? 'video'
                    : promptReferences[fromIndex]?.mediaType === 'audio'
                      ? 'audio'
                      : 'image',
                );
              }}
              onRemoveReference={(reference, currentValue) => {
                if (!reference.sourceNodeId) return;
                clearNodeError(node.id);
                removeImageReference(
                  node.id,
                  reference.sourceNodeId,
                  currentValue,
                  reference.mediaType || 'image',
                );
              }}
              onApplyCopiedImageOrder={(imageUrls) =>
                applyCopiedImageOrder(node.id, imageUrls)
              }
              onCopiedPrompt={() =>
                setToast(
                  promptReferences.length > 0
                    ? promptReferences.some(
                        (item) =>
                          item.mediaType &&
                          item.mediaType !== promptReferences[0]?.mediaType,
                      )
                      ? '已复制提示词和全能参考顺序'
                      : `已复制提示词和参考${getCanvasAssetTypeLabel(promptReferences[0]?.mediaType)}顺序`
                    : '已复制提示词',
                )
              }
            />

            <div
              className={
                compactCard
                  ? 'canvas-quick-settings__bar mt-2'
                  : 'mt-2 flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/80 p-2'
              }
            >
              <details
                className="group/model relative min-w-0 flex-1"
                onMouseEnter={openDetailsOnHover}
                onMouseLeave={closeDetailsOnHover}
              >
                <summary
                  aria-label="生成模型"
                  onClick={(event) => event.preventDefault()}
                  className={`flex h-9 w-full cursor-pointer list-none items-center gap-2 rounded-lg px-2.5 text-xs font-semibold text-slate-700 outline-none transition-colors hover:bg-slate-50 [&::-webkit-details-marker]:hidden ${compactCard ? 'border border-slate-200 bg-white' : 'bg-white'}`}
                >
                  <Box size={14} className="shrink-0 text-slate-500" />
                  <span className="min-w-0 flex-1 truncate text-left">
                    {activeModelLabel}
                  </span>
                  <ChevronDown
                    size={13}
                    className="shrink-0 text-slate-400 transition-transform group-open/model:rotate-180"
                  />
                </summary>
                <div
                  role="menu"
                  aria-label="生成模型选项"
                  className="absolute bottom-[calc(100%+8px)] left-0 z-[70] max-h-72 w-72 overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-[0_18px_50px_rgba(15,23,42,0.22)]"
                >
                  <p className="px-2 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                    生成模型
                  </p>
                  {sortedModelOptions.map((model) => {
                    const isActive = model === activeModel;
                    const isFavorite = favoriteModels.includes(model);
                    const modelLabel =
                      isVideoAnalysis && model === DEFAULT_VIDEO_ANALYSIS_MODEL
                        ? 'Qwen3.8 Omni Flash'
                        : mediaModelCatalog[model]?.label || model;
                    return (
                      <div
                        key={model}
                        role="menuitemradio"
                        aria-checked={isActive}
                        className={`canvas-model-menu-option mt-1 flex h-10 w-full items-center rounded-lg transition-colors ${isActive ? 'canvas-menu-option-active bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
                      >
                        <button
                          type="button"
                          onClick={(event) => {
                            selectGenerationModel(model);
                            event.currentTarget
                              .closest('details')
                              ?.removeAttribute('open');
                          }}
                          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 rounded-lg px-3 text-left text-xs font-semibold focus:outline-none"
                        >
                          <Box size={14} />
                          <span className="min-w-0 flex-1 truncate">
                            {modelLabel}
                          </span>
                          {isActive && (
                            <CheckCircle2 size={13} className="shrink-0" />
                          )}
                        </button>
                        <button
                          type="button"
                          aria-label={
                            isFavorite
                              ? `取消收藏 ${modelLabel}`
                              : `收藏 ${modelLabel}`
                          }
                          aria-pressed={isFavorite}
                          title={isFavorite ? '取消收藏' : '收藏到常用'}
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            toggleFavoriteModel(model);
                          }}
                          className={`canvas-model-favorite-btn mr-1 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md hover:bg-black/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 ${isFavorite ? 'is-on' : ''}`}
                        >
                          <Star
                            size={13}
                            fill={isFavorite ? 'currentColor' : 'none'}
                          />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </details>
              {isVideoAnalysis && (
                <details
                  className="group/analysis-preset relative shrink-0"
                  onMouseEnter={openDetailsOnHover}
                  onMouseLeave={closeDetailsOnHover}
                >
                  <summary
                    aria-label="视频分析固定提示词"
                    onClick={(event) => event.preventDefault()}
                    className="flex h-9 min-w-[156px] max-w-[200px] cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-700 outline-none transition-colors hover:border-slate-300 hover:bg-slate-50 focus:ring-2 focus:ring-cyan-100 [&::-webkit-details-marker]:hidden"
                  >
                    <MessageSquareText
                      size={13}
                      className="shrink-0 text-cyan-600"
                    />
                    <span className="min-w-0 flex-1 truncate text-left">
                      {activeVideoAnalysisPromptLabel}
                    </span>
                    <ChevronDown
                      size={13}
                      className="shrink-0 text-slate-400 transition-transform group-open/analysis-preset:rotate-180"
                    />
                  </summary>
                  <div
                    role="menu"
                    aria-label="视频分析固定提示词选项"
                    className="absolute bottom-[calc(100%+8px)] left-0 z-[70] w-64 rounded-xl border border-slate-200 bg-white p-2 shadow-[0_18px_50px_rgba(15,23,42,0.22)]"
                  >
                    <p className="px-2 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      固定提示词
                    </p>
                    {VIDEO_ANALYSIS_PROMPT_PRESETS.map((preset) => {
                      const isActive =
                        preset.value === activeVideoAnalysisPromptPreset?.value;
                      return (
                        <button
                          key={preset.value}
                          type="button"
                          role="menuitemradio"
                          aria-checked={isActive}
                          onClick={(event) => {
                            clearNodeError(node.id);
                            updateNode(node.id, {
                              prompt: preset.prompt,
                              status: 'draft',
                            });
                            event.currentTarget
                              .closest('details')
                              ?.removeAttribute('open');
                          }}
                          className={`canvas-generation-mode-menu-option mt-1 flex min-h-10 w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs font-semibold transition-colors focus:outline-none ${isActive ? 'canvas-menu-option-active bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
                        >
                          <MessageSquareText size={14} />
                          <span className="flex-1">{preset.label}</span>
                          {isActive && <CheckCircle2 size={13} />}
                        </button>
                      );
                    })}
                  </div>
                </details>
              )}
              {(node.kind === 'image' || node.kind === 'video') && (
                <details
                  className="group/mode relative shrink-0"
                  onMouseEnter={openDetailsOnHover}
                  onMouseLeave={closeDetailsOnHover}
                >
                  <summary
                    aria-label={
                      node.kind === 'video' ? '视频生成模式' : '图片生成模式'
                    }
                    onClick={(event) => event.preventDefault()}
                    className="flex h-9 min-w-[118px] cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-700 outline-none transition-colors hover:border-slate-300 hover:bg-slate-50 focus:ring-2 focus:ring-violet-100 [&::-webkit-details-marker]:hidden"
                  >
                    <span
                      className={
                        node.kind === 'video'
                          ? 'text-fuchsia-600'
                          : 'text-violet-600'
                      }
                    >
                      {renderGenerationModeIcon(activeGenerationMode)}
                    </span>
                    <span className="flex-1 whitespace-nowrap text-left">
                      {activeGenerationModeLabel}
                    </span>
                    <ChevronDown
                      size={13}
                      className="text-slate-400 transition-transform group-open/mode:rotate-180"
                    />
                  </summary>
                  <div
                    role="menu"
                    aria-label="生成模式选项"
                    className="absolute bottom-[calc(100%+8px)] left-0 z-[70] w-52 rounded-xl border border-slate-200 bg-white p-2 shadow-[0_18px_50px_rgba(15,23,42,0.22)]"
                  >
                    <p className="px-2 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      生成模式
                    </p>
                    {generationModeOptions.map((option) => {
                      const isSupported = supportedGenerationModes.includes(
                        option.value,
                      );
                      const isActive = option.value === activeGenerationMode;
                      return (
                        <button
                          key={option.value}
                          type="button"
                          role="menuitemradio"
                          aria-checked={isActive}
                          disabled={!isSupported}
                          onClick={(event) => {
                            if (node.kind === 'video') {
                              updateGenerationSettings({
                                videoGenerationMode:
                                  option.value as VideoGenerationMode,
                              });
                            } else {
                              updateGenerationSettings({
                                imageGenerationMode:
                                  option.value as ImageGenerationMode,
                              });
                            }
                            event.currentTarget
                              .closest('details')
                              ?.removeAttribute('open');
                          }}
                          className={`canvas-generation-mode-menu-option mt-1 flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 text-left text-xs font-semibold transition-colors focus:outline-none disabled:cursor-not-allowed disabled:text-slate-300 ${isActive ? 'canvas-menu-option-active bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
                        >
                          {renderGenerationModeIcon(option.value)}
                          <span className="flex-1">{option.label}</span>
                          {!isSupported && (
                            <span className="text-[9px] font-medium">
                              暂不支持
                            </span>
                          )}
                          {isActive && <CheckCircle2 size={13} />}
                        </button>
                      );
                    })}
                  </div>
                </details>
              )}

              {(aspectOptions.length > 0 ||
                resolutionOptions.length > 0 ||
                isVideoGeneration ||
                isImageGeneration ||
                node.kind === 'tts') && (
                <details
                  className="group/config relative shrink-0"
                  onMouseEnter={openDetailsOnHover}
                  onMouseLeave={closeDetailsOnHover}
                >
                  <summary
                    aria-label="生成参数"
                    onClick={(event) => event.preventDefault()}
                    className="flex h-9 min-w-[140px] max-w-[200px] cursor-pointer list-none items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-700 outline-none transition-colors hover:border-slate-300 hover:bg-slate-50 focus:ring-2 focus:ring-violet-100 [&::-webkit-details-marker]:hidden"
                  >
                    <SlidersHorizontal size={13} className="text-slate-500" />
                    <span className="min-w-0 flex-1 truncate text-left">
                      {settingsSummary ||
                        (node.kind === 'tts'
                          ? `${TTS_VOICE_OPTIONS.includes(node.voiceName || '') ? node.voiceName : defaultTTSVoice} · ${node.speechRate === 'slow' ? '慢速' : node.speechRate === 'fast' ? '快速' : '正常'}`
                          : '参数')}
                    </span>
                    <ChevronDown
                      size={13}
                      className="text-slate-400 transition-transform group-open/config:rotate-180"
                    />
                  </summary>
                  <div className="canvas-generation-config-menu absolute bottom-[calc(100%+8px)] right-0 z-[70] w-[348px] rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_22px_60px_rgba(15,23,42,0.24)]">
                    {aspectOptions.length > 0 && (
                      <fieldset>
                        <legend className="text-xs font-semibold text-slate-700">
                          比例
                        </legend>
                        <div className="mt-2 grid grid-cols-4 gap-2">
                          {aspectOptions.map((ratio) => {
                            const isActive = ratio === activeAspectRatio;
                            return (
                              <button
                                key={ratio}
                                type="button"
                                aria-pressed={isActive}
                                onClick={() =>
                                  updateGenerationSettings({
                                    aspectRatio: ratio,
                                  })
                                }
                                className={`flex h-16 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border text-[11px] font-semibold outline-none transition-colors focus:ring-2 focus:ring-violet-200 ${isActive ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:bg-white'}`}
                              >
                                <span className="flex h-7 items-center justify-center">
                                  <span
                                    className={`block rounded-[3px] border ${isActive ? 'border-white/80 bg-white/15' : 'border-slate-500 bg-white'}`}
                                    style={getAspectRatioPreviewStyle(ratio)}
                                  />
                                </span>
                                {ratio}
                              </button>
                            );
                          })}
                        </div>
                      </fieldset>
                    )}

                    {resolutionOptions.length > 0 && (
                      <fieldset
                        className={aspectOptions.length > 0 ? 'mt-4' : ''}
                      >
                        <legend className="text-xs font-semibold text-slate-700">
                          清晰度
                        </legend>
                        <div className="mt-2 grid grid-cols-4 gap-2">
                          {resolutionOptions.map((resolution) => {
                            const isActive = resolution === activeResolution;
                            return (
                              <button
                                key={resolution}
                                type="button"
                                aria-pressed={isActive}
                                onClick={() =>
                                  updateGenerationSettings({ resolution })
                                }
                                className={`h-9 cursor-pointer rounded-lg border text-xs font-semibold outline-none transition-colors focus:ring-2 focus:ring-violet-200 ${isActive ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-slate-300 hover:bg-white'}`}
                              >
                                {resolution === '4k' ? '4K' : resolution}
                              </button>
                            );
                          })}
                        </div>
                      </fieldset>
                    )}

                    {isVideoGeneration && (
                      <label className="mt-4 block">
                        <span className="flex items-center justify-between text-xs font-semibold text-slate-700">
                          <span>
                            {videoUsesTargetDuration ? '视频时长' : '延长次数'}
                          </span>
                          <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-700">
                            {videoInputValue}
                            {videoUsesTargetDuration ? ' s' : ' 次'}
                          </span>
                        </span>
                        <input
                          type="range"
                          min={videoInputMin}
                          max={videoInputMax}
                          step={videoInputStep}
                          value={videoInputValue}
                          disabled={!videoUsesTargetDuration && videoIsLite}
                          aria-label={
                            videoUsesTargetDuration
                              ? '视频时长（秒）'
                              : '视频延长次数'
                          }
                          onChange={(event) =>
                            videoUsesTargetDuration
                              ? updateGenerationSettings({
                                  duration: Number(event.target.value),
                                })
                              : updateGenerationSettings({
                                  extensionCount: Number(event.target.value),
                                })
                          }
                          className="mt-3 h-2 w-full cursor-pointer accent-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
                        />
                        <span className="mt-1 flex justify-between text-[10px] text-slate-400">
                          <span>{videoInputMin}</span>
                          <span>{videoInputMax}</span>
                        </span>
                      </label>
                    )}

                    {(isImageGeneration || isVideoGeneration) && (
                      <fieldset className="mt-4">
                        <legend className="text-xs font-semibold text-slate-700">
                          {isVideoGeneration ? '生成条数' : '生成张数'}
                        </legend>
                        <div className="mt-2 grid grid-cols-4 gap-2">
                          {batchCountOptions.map((value) => {
                            const isActive = value === activeBatchCount;
                            return (
                              <button
                                key={value}
                                type="button"
                                aria-pressed={isActive}
                                onClick={() =>
                                  updateGenerationSettings({ count: value })
                                }
                                className={`h-9 cursor-pointer rounded-lg border text-xs font-semibold outline-none transition-colors focus:ring-2 focus:ring-violet-200 ${isActive ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-slate-300 hover:bg-white'}`}
                              >
                                {value}
                                {batchUnitLabel}
                              </button>
                            );
                          })}
                        </div>
                      </fieldset>
                    )}

                    {node.kind === 'tts' && (
                      <div className="mt-4 grid grid-cols-2 gap-2">
                        <label className="block">
                          <span className="mb-1.5 block text-xs font-semibold text-slate-700">
                            配音声音
                          </span>
                          <select
                            value={
                              TTS_VOICE_OPTIONS.includes(node.voiceName || '')
                                ? node.voiceName
                                : defaultTTSVoice
                            }
                            onChange={(event) =>
                              updateNode(node.id, {
                                voiceName: event.target.value,
                                status: 'draft',
                              })
                            }
                            aria-label="配音声音"
                            className="h-9 w-full cursor-pointer rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                          >
                            {TTS_VOICE_OPTIONS.map((voice) => (
                              <option key={voice} value={voice}>
                                {voice}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="block">
                          <span className="mb-1.5 block text-xs font-semibold text-slate-700">
                            配音语速
                          </span>
                          <select
                            value={node.speechRate || 'normal'}
                            onChange={(event) =>
                              updateNode(node.id, {
                                speechRate: event.target.value as
                                  | 'slow'
                                  | 'normal'
                                  | 'fast',
                                status: 'draft',
                              })
                            }
                            aria-label="配音语速"
                            className="h-9 w-full cursor-pointer rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                          >
                            <option value="slow">慢速</option>
                            <option value="normal">正常</option>
                            <option value="fast">快速</option>
                          </select>
                        </label>
                      </div>
                    )}
                  </div>
                </details>
              )}

              {compactCard && (
                <>
                  {isVideoGeneration && (
                    <VideoCostEstimate
                      compact
                      modelLabel={
                        activeVideoModelConfig.label || activeVideoModel
                      }
                      resolution={activeVideoResolution}
                      duration={activeVideoEffectiveDuration}
                      count={activeBatchCount}
                      pricePerSecond={activeVideoPricePerSecond}
                      priceCurrency={activeVideoPriceCurrency}
                      cnyToUsdRate={cnyToUsdRate}
                      theme={theme}
                    />
                  )}
                  {isImageGeneration && (
                    <ImageCostEstimate
                      compact
                      modelLabel={
                        activeImageModelConfig.label || activeImageModel
                      }
                      resolution={activeImageResolution}
                      count={activeImageCount}
                      pricePerImage={activeImagePricePerImage}
                      priceCurrency={activeImagePriceCurrency}
                      cnyToUsdRate={cnyToUsdRate}
                      theme={theme}
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => deleteNode(node.id)}
                    aria-label="删除节点"
                    className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-300"
                  >
                    <Trash2 size={15} />
                  </button>
                  {node.kind === 'image' && (
                    <button
                      type="button"
                      onClick={() => saveImageNodeAsQuickCommand(node)}
                      disabled={!node.prompt.trim()}
                      title="将当前节点名称和描述保存为快捷指令"
                      aria-label="保存指令"
                      className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-violet-50 hover:text-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-300 disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      <Save size={15} />
                    </button>
                  )}
                  {showGenerationCancel && (
                    <span title={videoCancelTitle}>
                      <button
                        type="button"
                        onClick={() => void cancelVideoNodeGeneration(node.id)}
                        disabled={
                          !isVideoGeneration ||
                          !canCancelVideoTask ||
                          videoCancelState?.isCancelling === true
                        }
                        aria-label="取消生成"
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:cursor-not-allowed disabled:text-slate-300"
                      >
                        {videoCancelState?.isCancelling ? (
                          <Loader2 size={15} className="animate-spin" />
                        ) : (
                          <X size={16} />
                        )}
                      </button>
                    </span>
                  )}
                  <span
                    className="ml-auto inline-flex"
                    title={
                      hasSaveConflict &&
                      (isImageGeneration || isVideoGeneration)
                        ? '请先保持当前画布为最新版本，可刷新页面或覆盖保存'
                        : undefined
                    }
                  >
                    <button
                      type="button"
                      onClick={runGeneration}
                      disabled={generateDisabled}
                      title={
                        hasSaveConflict &&
                        (isImageGeneration || isVideoGeneration)
                          ? undefined
                          : isVideoGeneration
                            ? `${generateLabel}；预估费用 ${formatCnyEstimate(activeVideoPricePerSecond * activeVideoEffectiveDuration * activeBatchCount, activeVideoPriceCurrency, cnyToUsdRate)}`
                            : isImageGeneration
                              ? `${generateLabel}；预估费用 ${formatCnyEstimate(activeImagePricePerImage * activeImageCount, activeImagePriceCurrency, cnyToUsdRate)}`
                              : generateLabel
                      }
                      aria-label={generateLabel}
                      className={`canvas-quick-settings__generate ${generateButtonClass}`}
                    >
                      {isGenerating ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <ArrowUp size={16} />
                      )}
                    </button>
                  </span>
                </>
              )}
            </div>

            {isVideoAnalysis && node.analysisResult && (
              <div
                className={
                  compactCard
                    ? 'canvas-quick-settings__status whitespace-pre-line bg-cyan-50 text-cyan-900'
                    : 'mt-2 max-h-52 overflow-y-auto whitespace-pre-line rounded-lg bg-cyan-50 px-2.5 py-2 text-[11px] leading-5 text-cyan-900'
                }
              >
                {node.analysisResult}
              </div>
            )}

            {(referenceHint ||
              nodeProgress[node.id] ||
              nodeErrors[node.id]) && (
              <div
                role={nodeErrors[node.id] ? 'alert' : 'status'}
                className={
                  compactCard
                    ? `canvas-quick-settings__status ${nodeErrors[node.id] ? 'bg-red-50 text-red-700' : referenceHint ? 'bg-amber-50 text-amber-800' : 'bg-violet-50 text-violet-700'}`
                    : `mt-2 rounded-lg px-2.5 py-2 text-[11px] leading-5 ${nodeErrors[node.id] ? 'whitespace-pre-line break-words bg-red-50 text-red-700' : referenceHint ? 'bg-amber-50 text-amber-800' : 'bg-violet-50 text-violet-700'}`
                }
              >
                {nodeErrors[node.id] || nodeProgress[node.id] || referenceHint}
              </div>
            )}
          </>
        )}

        {!compactCard && (
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-200 pt-3">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => deleteNode(node.id)}
                aria-label="删除节点"
                className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition-colors duration-200 hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-300"
              >
                <Trash2 size={15} />
              </button>
              {node.kind === 'image' && (
                <button
                  type="button"
                  onClick={() => saveImageNodeAsQuickCommand(node)}
                  disabled={!node.prompt.trim()}
                  title="将当前节点名称和描述保存为快捷指令"
                  className="flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-violet-200 bg-violet-50 px-2.5 text-[11px] font-semibold text-violet-700 transition-colors hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-300 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
                >
                  <Save size={13} /> 保存指令
                </button>
              )}
            </div>
            {isGenerative && (
              <div className="ml-auto flex items-center gap-2">
                {isVideoGeneration && (
                  <VideoCostEstimate
                    modelLabel={
                      activeVideoModelConfig.label || activeVideoModel
                    }
                    resolution={activeVideoResolution}
                    duration={activeVideoEffectiveDuration}
                    count={activeBatchCount}
                    pricePerSecond={activeVideoPricePerSecond}
                    priceCurrency={activeVideoPriceCurrency}
                    cnyToUsdRate={cnyToUsdRate}
                    theme={theme}
                  />
                )}
                {isImageGeneration && (
                  <ImageCostEstimate
                    modelLabel={
                      activeImageModelConfig.label || activeImageModel
                    }
                    resolution={activeImageResolution}
                    count={activeImageCount}
                    pricePerImage={activeImagePricePerImage}
                    priceCurrency={activeImagePriceCurrency}
                    cnyToUsdRate={cnyToUsdRate}
                    theme={theme}
                  />
                )}
                {showGenerationCancel && (
                  <span title={videoCancelTitle}>
                    <button
                      type="button"
                      onClick={() => void cancelVideoNodeGeneration(node.id)}
                      disabled={
                        !isVideoGeneration ||
                        !canCancelVideoTask ||
                        videoCancelState?.isCancelling === true
                      }
                      aria-label="取消生成"
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:cursor-not-allowed disabled:border-slate-100 disabled:text-slate-300"
                    >
                      {videoCancelState?.isCancelling ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <X size={16} />
                      )}
                    </button>
                  </span>
                )}
                <button
                  type="button"
                  onClick={runGeneration}
                  disabled={generateDisabled}
                  className={`flex h-9 min-w-32 cursor-pointer items-center justify-center gap-1.5 rounded-xl px-4 text-xs font-semibold text-white transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 ${generateButtonClass}`}
                >
                  {isGenerating ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <GenerateIcon size={15} />
                  )}
                  {generateLabel}
                </button>
              </div>
            )}
          </div>
        )}
      </section>
    );

    if (promptEditorExpanded && typeof document !== 'undefined') {
      return createPortal(
        <div
          className="canvas-prompt-expand-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="扩大提示词"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget)
              setPromptEditorExpanded(false);
          }}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          {settingsCard}
        </div>,
        document.body,
      );
    }

    if (!showCompactQuickSettings || typeof document === 'undefined')
      return null;

    return createPortal(settingsCard, document.body);
  };

  useEffect(() => {
    const closeShortcuts = () => {
      setShortcutsOpen(false);
      window.requestAnimationFrame(() => shortcutsButtonRef.current?.focus());
    };
    const runSelectedGeneration = () => {
      if (!selectedNode) return;
      if (selectedNode.kind === 'text') {
        if ((selectedNode.textGenerationMode || 'image') === 'video')
          void generateVideoNode(selectedNode.id);
        else void generateImageNode(selectedNode.id);
      } else if (selectedNode.kind === 'image') {
        void generateImageNode(selectedNode.id);
      } else if (selectedNode.kind === 'video') {
        void generateVideoNode(selectedNode.id);
      } else if (selectedNode.kind === 'video_analysis') {
        void generateVideoAnalysisNode(selectedNode.id);
      } else if (selectedNode.kind === 'music') {
        void generateMusicNode(selectedNode.id);
      } else if (selectedNode.kind === 'tts') {
        void generateTTSNode(selectedNode.id);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      const isEditing = isEditingElement(event.target);
      const key = event.key.toLowerCase();
      const commandKey = event.ctrlKey || event.metaKey;

      if (event.key === 'Escape') {
        if (replaceMediaConfirm) {
          setReplaceMediaConfirm(null);
          setToast('已取消替换素材');
          return;
        }
        if (promptEditorExpanded) {
          setPromptEditorExpanded(false);
          return;
        }
        if (toolMenuOpen) {
          setToolMenuOpen(false);
          return;
        }
        if (imageAiTool) {
          closeImageAiTool();
          return;
        }
        if (tidyConfirm) {
          keepTidyResult();
          return;
        }
        if (shortcutsOpen) {
          closeShortcuts();
          return;
        }
        if (minimapOpen) {
          setMinimapOpen(false);
          return;
        }
        setSelectionLayoutMenuOpen(false);
        setSelectionGroupMenuOpen(false);
        setPendingSourceId(null);
        setPendingSourceIds([]);
        setSelectedNodeId(null);
        setSelectedNodeIds(new Set());
        setSelectedEdgeId(null);
        setNodeMenu(null);
        setContextMenu(null);
        return;
      }

      if (!isEditing && event.key === '?') {
        event.preventDefault();
        setNodeMenu(null);
        if (shortcutsOpen) closeShortcuts();
        else setShortcutsOpen(true);
        return;
      }

      if (commandKey && key === 's') {
        event.preventDefault();
        saveDraft(true);
        return;
      }

      if (commandKey && event.key === 'Enter' && selectedNode) {
        event.preventDefault();
        runSelectedGeneration();
        return;
      }

      if (isEditing || shortcutsOpen) return;

      if (commandKey && key === 'z') {
        event.preventDefault();
        if (event.shiftKey) redoCanvas();
        else undoCanvas();
        return;
      }

      if (commandKey && key === 'y') {
        event.preventDefault();
        redoCanvas();
        return;
      }

      if (commandKey && key === 'd' && selectedNode) {
        event.preventDefault();
        duplicateNode(selectedNode.id);
        return;
      }

      if (commandKey && (event.key === '+' || event.key === '=')) {
        event.preventDefault();
        zoomAtCenter(1.15);
        return;
      }

      if (commandKey && (event.key === '-' || event.key === '_')) {
        event.preventDefault();
        zoomAtCenter(0.85);
        return;
      }

      if (commandKey && event.key === '0') {
        event.preventDefault();
        fitView();
        return;
      }

      if (event.key === 'Tab') {
        event.preventDefault();
        openNodeMenuAtCursor();
        return;
      }

      if (event.key === 'Delete' || event.key === 'Backspace') {
        if (selectedEdgeId) {
          event.preventDefault();
          cancelConnection(selectedEdgeId);
          return;
        }
        if (selectedPersistedGroupId || selectedNodeIds.size > 1) {
          // 选中分组框或多选框时删掉框内全部节点，而不是只删 selectedNode 那一个。
          event.preventDefault();
          const memberIds = selectedPersistedGroupId
            ? nodes
                .filter((node) => node.groupId === selectedPersistedGroupId)
                .map((node) => node.id)
            : Array.from(selectedNodeIds);
          deleteNodes(memberIds);
          setToast(
            memberIds.length > 1
              ? `已删除 ${memberIds.length} 个节点`
              : '节点已删除',
          );
          return;
        }
        if (selectedNode) {
          event.preventDefault();
          deleteNode(selectedNode.id);
          return;
        }
      }

      if (!commandKey && !event.altKey) {
        if (key === 'v') {
          setToolMode('select');
          setToolMenuOpen(false);
        } else if (key === 'h') {
          setToolMode('hand');
          setToolMenuOpen(false);
        } else if (
          event.code === 'Space' &&
          !event.repeat &&
          toolMode !== 'hand'
        ) {
          event.preventDefault();
          temporaryHandRef.current = true;
          setToolMode('hand');
        }
      }

      if (
        event.key === 'Alt' ||
        event.code === 'AltLeft' ||
        event.code === 'AltRight'
      ) {
        setAltDuplicateModifier(true);
      }
    };
    const handleKeyUp = (event: KeyboardEvent) => {
      if (
        event.key === 'Alt' ||
        event.code === 'AltLeft' ||
        event.code === 'AltRight'
      ) {
        setAltDuplicateModifier(false);
      }
      if (event.code !== 'Space' || !temporaryHandRef.current) return;
      temporaryHandRef.current = false;
      setToolMode('select');
    };
    const clearAltDuplicateModifier = () => setAltDuplicateModifier(false);

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', clearAltDuplicateModifier);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', clearAltDuplicateModifier);
    };
  }, [
    cancelConnection,
    deleteNode,
    deleteNodes,
    duplicateNode,
    fitView,
    generateImageNode,
    generateMusicNode,
    generateTTSNode,
    generateVideoAnalysisNode,
    generateVideoNode,
    openNodeMenuAtCursor,
    redoCanvas,
    saveDraft,
    nodes,
    selectedEdgeId,
    selectedNode,
    selectedNodeIds,
    selectedPersistedGroupId,
    shortcutsOpen,
    tidyConfirm,
    imageAiTool,
    minimapOpen,
    toolMenuOpen,
    promptEditorExpanded,
    replaceMediaConfirm,
    toolMode,
    undoCanvas,
    zoomAtCenter,
  ]);

  useEffect(() => {
    const handleCanvasPaste = (event: ClipboardEvent) => {
      if (
        isEditingElement(event.target) ||
        shortcutsOpen ||
        previewMedia ||
        cloudAssetNodeId
      )
        return;
      const clipboardData = event.clipboardData;
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!clipboardData || !rect) return;

      const clipboardItemImages = Array.from(clipboardData.items)
        .filter(
          (item) => item.kind === 'file' && item.type.startsWith('image/'),
        )
        .map((item) => item.getAsFile())
        .filter((file): file is File => Boolean(file));
      const imageFiles =
        clipboardItemImages.length > 0
          ? clipboardItemImages
          : Array.from(clipboardData.files).filter(isImageFile);
      const offset = (nodes.length % 5) * 18;
      const pastePosition = contextMenu?.nodePosition || {
        x: Math.round(
          (rect.width / 2 - viewport.x) / viewport.zoom -
            NODE_WIDTH / 2 +
            offset,
        ),
        y: Math.round(
          (rect.height / 2 - viewport.y) / viewport.zoom -
            NODE_HEIGHT / 2 +
            offset,
        ),
      };

      if (imageFiles.length > 0) {
        event.preventDefault();
        setContextMenu(null);
        void importCanvasImages(imageFiles, pastePosition, 'paste');
        return;
      }

      const pastedText = clipboardData.getData('text/plain').trim();
      if (!pastedText) return;
      event.preventDefault();
      setContextMenu(null);
      addNode('text', pastePosition, {
        title: '粘贴文本',
        prompt: pastedText,
        status: 'draft',
      });
      setToast('已粘贴文本并创建文本生成节点');
    };

    window.addEventListener('paste', handleCanvasPaste);
    return () => window.removeEventListener('paste', handleCanvasPaste);
  }, [
    addNode,
    cloudAssetNodeId,
    contextMenu,
    importCanvasImages,
    nodes.length,
    previewMedia,
    shortcutsOpen,
    viewport.x,
    viewport.y,
    viewport.zoom,
  ]);

  return (
    <div
      data-canvas-theme={theme}
      className={`canvas-theme-shell ${theme === 'dark' ? 'canvas-theme-dark' : ''} relative flex h-screen min-h-[680px] flex-col overflow-hidden bg-[#eef3fb] text-slate-900`}
    >
      <header className="pointer-events-none absolute inset-x-0 top-0 z-30 flex h-[72px] items-center justify-between bg-transparent px-3 sm:px-5 lg:px-7">
        <div className="pointer-events-auto flex min-w-0 items-center">
          <button
            type="button"
            onClick={onBack}
            aria-label="返回工作室"
            className="flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition-colors duration-200 hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-400"
          >
            <ArrowLeft size={18} />
          </button>
          <div className="ml-3 min-w-[140px] max-w-[min(55vw,640px)]">
            {isTitleEditing ? (
              <input
                type="text"
                value={titleDraft}
                maxLength={80}
                autoFocus
                aria-label="画布名称"
                data-testid="canvas-title-input"
                onChange={(event) => setTitleDraft(event.target.value)}
                onBlur={commitCanvasTitle}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    event.currentTarget.blur();
                  }
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    setTitleDraft(title);
                    setIsTitleEditing(false);
                  }
                }}
                style={{
                  width: `${Math.max(10, Math.min(titleDraft.length + 1, 80))}ch`,
                }}
                className="canvas-title-editor h-9 max-w-[min(55vw,640px)] bg-transparent px-1 text-sm font-semibold text-slate-800 sm:text-base"
              />
            ) : (
              <button
                type="button"
                onClick={() => {
                  setTitleDraft(title || '未命名画布');
                  setIsTitleEditing(true);
                }}
                aria-label="修改画布名称"
                title="点击修改画布名称"
                data-testid="canvas-title-button"
                className="-ml-1 block max-w-[min(55vw,640px)] cursor-text whitespace-nowrap rounded-lg px-1 py-1 text-left text-sm font-semibold text-slate-800 transition-colors duration-150 hover:bg-white/80 focus:outline-none focus:ring-2 focus:ring-violet-300 sm:text-base"
              >
                {title || '未命名画布'}
              </button>
            )}
          </div>
        </div>

        <div
          className={`pointer-events-auto flex items-center gap-2 transition-[margin] duration-200 ease-out ${chatOpen ? 'sm:mr-[400px]' : ''}`}
        >
          <div className="mr-1 hidden items-center gap-2 rounded-xl bg-white/80 px-2.5 py-2 text-xs text-slate-500 shadow-sm backdrop-blur-md lg:flex">
            <CheckCircle2 size={14} className="text-emerald-500" />
            {lastSavedAt
              ? `${lastSavedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} 已保存`
              : '尚未保存'}
          </div>
          <div className="group relative">
            <button
              type="button"
              onMouseEnter={() => void refreshTodayUsage()}
              onFocus={() => void refreshTodayUsage()}
              aria-label={`今日已用：${
                todayUsageLoading ? '正在读取' : todayUsageDisplay
              }`}
              aria-describedby="canvas-today-usage-tip"
              className={`flex h-10 w-10 cursor-default items-center justify-center rounded-xl border transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${
                theme === 'dark'
                  ? 'border-slate-700 bg-slate-900 text-violet-300 hover:border-violet-400 hover:bg-slate-800'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700'
              }`}
            >
              {todayUsageLoading ? (
                <Loader2 size={17} className="animate-spin" />
              ) : (
                <CircleDollarSign size={17} />
              )}
            </button>
            <div
              id="canvas-today-usage-tip"
              role="tooltip"
              className={`pointer-events-none absolute right-0 top-[calc(100%+8px)] z-50 w-64 rounded-lg px-3 py-2.5 text-xs font-medium opacity-0 shadow-lg transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100 ${
                theme === 'dark'
                  ? 'bg-slate-800 text-slate-100'
                  : 'bg-slate-900 text-white'
              }`}
            >
              <div className="mb-2 flex items-center justify-between">
                <span>今日已用</span>
                <span className="font-semibold">
                  {todayUsageLoading ? '读取中…' : todayUsageDisplay}
                </span>
              </div>
              {todayUsageQuotaProgress.map((item) => {
                const used = `¥${(item.used / cnyToUsdRate).toFixed(2)}`;
                const limit = item.limit
                  ? `¥${(item.limit / cnyToUsdRate).toFixed(2)}`
                  : '不限额';
                return (
                  <div key={item.label} className="mt-2 first:mt-0">
                    <div className="mb-1 flex items-center justify-between text-[11px] text-slate-300">
                      <span>{item.label}额度</span>
                      <span>
                        {used} / {limit}
                      </span>
                    </div>
                    <div
                      className={`h-1.5 overflow-hidden rounded-full ${
                        theme === 'dark' ? 'bg-slate-700' : 'bg-white/25'
                      }`}
                    >
                      <div
                        className="h-full rounded-full bg-violet-400 transition-[width] duration-300"
                        style={{ width: `${item.percent}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <button
            type="button"
            onClick={openHistoryPage}
            aria-label="打开生成历史"
            title="生成历史"
            className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition-colors duration-200 hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700 focus:outline-none focus:ring-2 focus:ring-violet-400"
          >
            <CalendarDays size={17} />
          </button>
          <button
            type="button"
            onClick={clearCanvas}
            aria-label="清空画布"
            title="清空画布"
            className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl border border-red-200 bg-white text-red-600 transition-colors duration-200 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-400"
          >
            <Trash2 size={17} />
          </button>
          <button
            type="button"
            onClick={() => saveDraft(true)}
            aria-label="保存画布"
            title="保存画布"
            className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl bg-slate-950 text-white transition-colors duration-200 hover:bg-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2"
          >
            <Save size={17} />
          </button>
          <input
            ref={assetInputRef}
            type="file"
            accept={`image/*,video/*,audio/mpeg,audio/wav,audio/mp3,.mp3,.wav,${WAN3_REFERENCE_FILE_EXTENSIONS.join(',')}`}
            onChange={handleLocalAssetImport}
            className="hidden"
          />
        </div>
      </header>

      <main className="flex min-h-0 flex-1">
        <section className="relative min-w-0 flex-1 overflow-hidden bg-[#eaf0f9]">
          <div
            className={`pointer-events-none absolute left-1/2 top-3 z-20 hidden -translate-x-1/2 items-center gap-2 rounded-full border px-3 py-2 text-xs shadow-md backdrop-blur-lg lg:flex ${
              pendingSourceId && connectionRejectTargetId
                ? 'border-rose-200 bg-rose-50/90 text-rose-700'
                : 'border-white/90 bg-white/85 text-slate-500'
            }`}
          >
            {pendingSourceId ? (
              connectionRejectTargetId ? (
                <>
                  <Unlink size={14} /> 无法连接
                </>
              ) : (
                <>
                  <Link2 size={14} className="text-violet-600" />{' '}
                  {pendingSourceIds.length > 1
                    ? `拖到目标节点，组内 ${pendingSourceIds.length} 个素材将全部连上`
                    : '拖到目标节点即可连接'}
                </>
              )
            ) : toolMode === 'hand' ? (
              <>
                <Hand size={14} /> 抓手模式 · 拖动画布平移 · 按 V 返回选择
              </>
            ) : (
              <>
                <MousePointer2 size={14} /> 选择模式 · 拖动节点移动 ·
                双击选择节点
              </>
            )}
          </div>

          <div
            ref={canvasRef}
            onPointerDown={handleCanvasPointerDown}
            onPointerMove={(event) => {
              lastCanvasPointerRef.current = {
                clientX: event.clientX,
                clientY: event.clientY,
              };
            }}
            onPointerLeave={() => {
              lastCanvasPointerRef.current = null;
            }}
            onDoubleClick={handleCanvasDoubleClick}
            onContextMenu={handleCanvasContextMenu}
            onDragEnter={handleCanvasDragEnter}
            onDragOver={handleCanvasDragOver}
            onDragLeave={handleCanvasDragLeave}
            onDrop={handleCanvasImageDrop}
            className={`relative h-full w-full touch-none overflow-hidden ${toolMode === 'hand' ? 'cursor-grab active:cursor-grabbing' : 'cursor-default'}`}
            style={{
              backgroundImage:
                theme === 'dark'
                  ? 'radial-gradient(circle, rgba(148,163,184,0.23) 1px, transparent 1px)'
                  : 'radial-gradient(circle, rgba(100,116,139,0.34) 1px, transparent 1px)',
              backgroundPosition: `${viewport.x}px ${viewport.y}px`,
              backgroundSize: `${24 * viewport.zoom}px ${24 * viewport.zoom}px`,
            }}
          >
            {selectionBox && (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute z-[80] border border-violet-500 bg-violet-200/20"
                style={selectionBox}
              />
            )}
            <div
              className="absolute left-0 top-0 h-0 w-0 origin-top-left"
              style={{
                transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
              }}
            >
              {persistentNodeGroups.map((group) => {
                const isActiveGroup = group.id === selectedPersistedGroupId;
                return (
                  <div
                    key={group.id}
                    data-canvas-node-group={group.id}
                    data-canvas-selection-group={
                      isActiveGroup ? 'true' : undefined
                    }
                    aria-label={`节点分组，共 ${group.members.length} 个节点`}
                    onPointerDown={(event) =>
                      beginSelectionFrameDrag(
                        event,
                        group.members.map((member) => member.id),
                      )
                    }
                    className={`canvas-selection-group absolute z-0 ${
                      isActiveGroup
                        ? 'canvas-selection-group--active'
                        : 'canvas-selection-group--idle'
                    } ${
                      altDuplicateModifier
                        ? 'cursor-copy'
                        : toolMode === 'hand'
                          ? 'cursor-grab'
                          : 'cursor-move'
                    }`}
                    style={{
                      left: group.bounds.left,
                      top: group.bounds.top,
                      width: group.bounds.width,
                      height: group.bounds.height,
                    }}
                  >
                    {renderGroupConnectionPort(
                      group.members.map((member) => member.id),
                      group.bounds,
                    )}
                  </div>
                );
              })}
              {selectionGroupBounds && (
                <div
                  data-canvas-selection-group="true"
                  aria-label={`已框选 ${selectedNodeIds.size} 个节点`}
                  onPointerDown={(event) =>
                    beginSelectionFrameDrag(event, Array.from(selectedNodeIds))
                  }
                  className={`canvas-selection-group canvas-selection-group--active absolute z-0 ${
                    altDuplicateModifier
                      ? 'cursor-copy'
                      : toolMode === 'hand'
                        ? 'cursor-grab'
                        : 'cursor-move'
                  }`}
                  style={{
                    left: selectionGroupBounds.left,
                    top: selectionGroupBounds.top,
                    width: selectionGroupBounds.width,
                    height: selectionGroupBounds.height,
                  }}
                >
                  {renderGroupConnectionPort(
                    Array.from(selectedNodeIds),
                    selectionGroupBounds,
                  )}
                </div>
              )}
              <svg
                width="4000"
                height="2600"
                viewBox="0 0 4000 2600"
                className="pointer-events-none absolute left-0 top-0 z-[1] max-w-none overflow-visible"
                role="img"
                aria-label={`画布中有${edges.length}条节点连接`}
              >
                <defs>
                  <filter
                    id="canvas-connection-pulse-glow"
                    filterUnits="userSpaceOnUse"
                    x="0"
                    y="0"
                    width="4000"
                    height="2600"
                    colorInterpolationFilters="sRGB"
                  >
                    <feGaussianBlur
                      in="SourceGraphic"
                      stdDeviation="2.6"
                      result="blur"
                    />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>
                {pendingSourceId &&
                  connectionPointer &&
                  (() => {
                    const source = nodes.find(
                      (node) => node.id === pendingSourceId,
                    );
                    const sourceDimensions = source
                      ? getCanvasNodeDimensions(source)
                      : null;
                    const sourceAnchor = source
                      ? connectionAnchors.outputs[source.id]
                      : undefined;
                    const startX =
                      connectionOrigin?.x ??
                      sourceAnchor?.x ??
                      (source && sourceDimensions
                        ? source.x + sourceDimensions.width
                        : null);
                    const startY =
                      connectionOrigin?.y ??
                      sourceAnchor?.y ??
                      (source && sourceDimensions
                        ? source.y + sourceDimensions.height / 2
                        : null);
                    if (startX == null || startY == null) return null;
                    const snapTarget = connectionHoverTargetId
                      ? nodes.find(
                          (node) => node.id === connectionHoverTargetId,
                        )
                      : undefined;
                    const snapAnchor = snapTarget
                      ? getNodeInputAnchor(
                          snapTarget,
                          getCanvasNodeDimensions(snapTarget),
                          connectionAnchors.inputs,
                        )
                      : null;
                    const endX = snapAnchor?.x ?? connectionPointer.x;
                    const endY = snapAnchor?.y ?? connectionPointer.y;
                    const controlOffset = Math.max(
                      70,
                      Math.abs(endX - startX) * 0.42,
                    );
                    const path = `M ${startX} ${startY} C ${startX + controlOffset} ${startY}, ${endX - controlOffset} ${endY}, ${endX} ${endY}`;
                    const rejected = Boolean(connectionRejectTargetId);
                    return (
                      <path
                        aria-hidden="true"
                        d={path}
                        fill="none"
                        stroke={
                          rejected ? '#e11d48' : 'var(--canvas-drop-target)'
                        }
                        strokeWidth={snapAnchor ? 2.25 : 2}
                        strokeDasharray={snapAnchor ? undefined : '6 5'}
                      />
                    );
                  })()}
                {edges.map((edge, index) => {
                  const source = nodes.find((node) => node.id === edge.source);
                  const target = nodes.find((node) => node.id === edge.target);
                  if (!source || !target) return null;
                  const sourceDimensions = getCanvasNodeDimensions(source);
                  const targetDimensions = getCanvasNodeDimensions(target);
                  const sourceAnchor = connectionAnchors.outputs[source.id];
                  const targetAnchor = connectionAnchors.inputs[target.id];
                  const startX =
                    sourceAnchor?.x ?? source.x + sourceDimensions.width;
                  const startY =
                    sourceAnchor?.y ?? source.y + sourceDimensions.height / 2;
                  const endX = targetAnchor?.x ?? target.x;
                  const endY =
                    targetAnchor?.y ?? target.y + targetDimensions.height / 2;
                  const controlOffset = Math.max(
                    90,
                    Math.abs(endX - startX) * 0.42,
                  );
                  const path = `M ${startX} ${startY} C ${startX + controlOffset} ${startY}, ${endX - controlOffset} ${endY}, ${endX} ${endY}`;
                  const isRelatedConnection = relatedConnectionEdgeIds.has(
                    edge.id,
                  );
                  const isSelectedConnection = selectedEdgeId === edge.id;
                  return (
                    <g
                      key={edge.id}
                      data-canvas-edge={edge.id}
                      data-canvas-edge-selected={
                        isSelectedConnection ? 'true' : undefined
                      }
                      style={
                        {
                          '--canvas-pulse-delay': `${(index * 0.37) % 2.8}s`,
                        } as React.CSSProperties
                      }
                    >
                      <path
                        d={path}
                        fill="none"
                        stroke={
                          theme === 'dark'
                            ? 'rgba(255,255,255,0.78)'
                            : 'rgba(71,85,105,0.58)'
                        }
                        strokeWidth={isSelectedConnection ? 2.15 : 1.5}
                      />
                      {isRelatedConnection && !prefersReducedMotion && (
                        <>
                          <path
                            d={path}
                            pathLength={1}
                            className="canvas-connection-pulse-glow"
                            filter="url(#canvas-connection-pulse-glow)"
                          />
                          <path
                            d={path}
                            pathLength={1}
                            className="canvas-connection-pulse-core"
                          />
                        </>
                      )}
                      <path
                        d={path}
                        fill="none"
                        stroke="transparent"
                        strokeWidth="16"
                        aria-label={`连接：${source.title}到${target.title}，点击后可剪断，Delete 可删除`}
                        aria-current={isSelectedConnection ? 'true' : undefined}
                        data-canvas-edge={edge.id}
                        onPointerDown={(event) =>
                          handleEdgePointerDown(event, edge.id)
                        }
                        onContextMenu={(event) =>
                          handleEdgeContextMenu(event, edge.id)
                        }
                        style={{
                          pointerEvents: 'stroke',
                          cursor: toolMode === 'hand' ? 'grab' : 'pointer',
                        }}
                      />
                    </g>
                  );
                })}
              </svg>

              {nodes.map((node) => {
                const meta = getNodeMeta(node.kind);
                const isSelected = selectedNodeIds.has(node.id);
                const isPending =
                  pendingSourceIds.includes(node.id) ||
                  pendingSourceId === node.id;
                const isConnectionDropTarget =
                  connectionHoverTargetId === node.id;
                const isFileDropTarget = fileDropTargetNodeId === node.id;
                const isFileDropRejected =
                  isFileDropTarget && fileDropTargetRejected;
                const outputMediaSource =
                  node.kind === 'output'
                    ? getIncomingNodes(node.id).find((incomingNode) =>
                        Boolean(
                          incomingNode.resultUrl ||
                            incomingNode.resultUrls?.length,
                        ),
                      )
                    : undefined;
                const mediaSourceNode = outputMediaSource || node;
                const fullMediaUrl =
                  mediaSourceNode.resultUrls?.[0] || mediaSourceNode.resultUrl;
                const fullMediaType =
                  mediaSourceNode.kind === 'text'
                    ? mediaSourceNode.resultAssetType ||
                      (mediaSourceNode.textGenerationMode === 'video'
                        ? 'video'
                        : 'image')
                    : mediaSourceNode.kind === 'asset'
                      ? mediaSourceNode.assetType || 'image'
                      : mediaSourceNode.kind;
                const isFullImageCard =
                  Boolean(fullMediaUrl) && fullMediaType === 'image';
                const isFullVideoCard =
                  Boolean(fullMediaUrl) && fullMediaType === 'video';
                const isFullMediaCard = isFullImageCard || isFullVideoCard;
                // 完整媒体被选中时临时提升到最前，避免被相交节点遮挡；取消选中后回到原本层级。
                const elevateSelectedMedia = isSelected && isFullMediaCard;
                const isEmptyGenerationMediaCard =
                  !fullMediaUrl &&
                  (node.kind === 'image' || node.kind === 'video');
                const isMediaPreviewCard =
                  isFullMediaCard || isEmptyGenerationMediaCard;
                const ownMediaUrls = getOwnMediaResultUrls(node);
                const canExpandMedia = ownMediaUrls.length > 1;
                const isMediaExpanded =
                  canExpandMedia && expandedMediaNodeIds.has(node.id);
                const boardMediaUrls = canExpandMedia
                  ? ownMediaUrls
                  : fullMediaUrl
                    ? [fullMediaUrl]
                    : [];
                const isNodeGenerating = generatingNodeIds.has(node.id);
                const nodeDimensions = getCanvasNodeDimensions(node);
                // 视频分析完成后会转换为加大的文本节点；为它提供结果阅读的专用布局，
                // 但仍然保留文本框，方便用户直接修订分析内容。
                const isExpandedVideoAnalysisResult =
                  node.kind === 'text' &&
                  node.title === '视频分析结果' &&
                  nodeDimensions.width > NODE_WIDTH;
                return (
                  <React.Fragment key={node.id}>
                    <article
                      data-canvas-node={node.id}
                      aria-label={`${node.title}，${meta.label}`}
                      onPointerDownCapture={(event) => {
                        if (
                          imageAiToolRef.current?.mode === 'crop' ||
                          imageAiToolRef.current?.mode === 'matting'
                        )
                          return;
                        if (
                          imageAiToolRef.current?.mode === 'grid-split' &&
                          imageAiToolRef.current.nodeId === node.id
                        )
                          return;
                        if (
                          imageAiToolRef.current?.mode === 'grid-split' &&
                          imageAiToolRef.current.nodeId !== node.id
                        ) {
                          setImageAiTool(null);
                        }
                        if (
                          (event.target as HTMLElement | null)?.closest?.(
                            '[data-canvas-crop-dialog], [data-canvas-matting-dialog]',
                          )
                        )
                          return;
                        if (toolMode === 'hand' || event.button !== 0) return;
                        if (suppressMarqueeReleaseRef.current) {
                          event.stopPropagation();
                          return;
                        }
                        const target = event.target as HTMLElement | null;
                        const nonDraggableTarget = target?.closest(
                          'button, input, textarea, select, option, label, a, [role="button"], [role="textbox"], [role="combobox"], [role="listbox"], [contenteditable="true"]',
                        );
                        if (nonDraggableTarget) return;
                        // 在捕获阶段接管现有节点的拖动，避免媒体预览层把指针事件继续交给画布平移。
                        event.stopPropagation();
                        event.currentTarget.setPointerCapture(event.pointerId);
                        if (beginAltDuplicateDrag(event, node)) return;
                        const nextSelectedNodeIds = event.shiftKey
                          ? new Set(selectedNodeIds)
                          : isSelected
                            ? new Set(selectedNodeIds)
                            : new Set([node.id]);
                        if (event.shiftKey) {
                          if (nextSelectedNodeIds.has(node.id))
                            nextSelectedNodeIds.delete(node.id);
                          else nextSelectedNodeIds.add(node.id);
                        }
                        setSelectedNodeIds(nextSelectedNodeIds);
                        setSelectedNodeId(
                          nextSelectedNodeIds.has(node.id)
                            ? node.id
                            : Array.from(nextSelectedNodeIds)[0] || null,
                        );
                        setSelectedEdgeId(null);
                        if (!nextSelectedNodeIds.has(node.id)) return;
                        const draggedNodeIds = Array.from(nextSelectedNodeIds);
                        dragRef.current = {
                          nodeIds: draggedNodeIds,
                          startClientX: event.clientX,
                          startClientY: event.clientY,
                          startPositions: Object.fromEntries(
                            nodes
                              .filter((candidate) =>
                                nextSelectedNodeIds.has(candidate.id),
                              )
                              .map((candidate) => [
                                candidate.id,
                                { x: candidate.x, y: candidate.y },
                              ]),
                          ),
                        };
                      }}
                      onDragStart={(event) => event.preventDefault()}
                      onClick={(event) => {
                        event.stopPropagation();
                        if (toolMode === 'hand') return;
                        if (event.shiftKey) {
                          const next = new Set(selectedNodeIds);
                          if (next.has(node.id)) next.delete(node.id);
                          else next.add(node.id);
                          setSelectedNodeIds(next);
                          setSelectedNodeId(
                            next.has(node.id)
                              ? node.id
                              : Array.from(next)[0] || null,
                          );
                          setSelectedEdgeId(null);
                        } else if (!selectedNodeIds.has(node.id)) {
                          setSelectedNodeIds(new Set([node.id]));
                          setSelectedNodeId(node.id);
                          setSelectedEdgeId(null);
                        }
                      }}
                      onMouseEnter={(event) => {
                        if (!isFullVideoCard || isMediaExpanded) return;
                        const video =
                          event.currentTarget.querySelector<HTMLVideoElement>(
                            'video[data-node-video-preview]',
                          );
                        void video?.play().catch(() => undefined);
                      }}
                      onMouseLeave={(event) => {
                        if (!isFullVideoCard || isMediaExpanded) return;
                        const video =
                          event.currentTarget.querySelector<HTMLVideoElement>(
                            'video[data-node-video-preview]',
                          );
                        if (!video) return;
                        resetNodeVideoPreview(video);
                      }}
                      className={`group absolute z-[1] overflow-visible backdrop-blur transition-[border-color,box-shadow] duration-200 ${
                        altDuplicateModifier ? 'cursor-copy' : 'cursor-default'
                      } ${
                        isFullMediaCard
                          ? 'rounded-md border-0 bg-slate-950 p-0 shadow-sm'
                          : isMediaPreviewCard
                            ? 'rounded-md border border-slate-300/70 bg-slate-950 p-0 shadow-sm hover:border-slate-400'
                            : isExpandedVideoAnalysisResult
                              ? 'flex flex-col rounded-[22px] border border-white/90 bg-white/95 p-0 shadow-[0_18px_48px_rgba(15,23,42,0.14)] hover:border-violet-200'
                              : 'rounded-[22px] border border-white/90 bg-white/95 p-3 shadow-[0_18px_48px_rgba(15,23,42,0.14)] hover:border-violet-200'
                      } ${
                        isFileDropRejected
                          ? 'ring-2 ring-red-400 ring-offset-2 ring-offset-white'
                          : isFileDropTarget
                            ? 'ring-2 ring-violet-500 ring-offset-2 ring-offset-white'
                            : isSelected && selectedNodeIds.size === 1
                              ? isFullMediaCard
                                ? isFullVideoCard
                                  ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-white'
                                  : 'ring-0'
                                : isMediaPreviewCard
                                  ? 'border-blue-500 ring-1 ring-blue-500'
                                  : 'canvas-node-selected border-violet-400 ring-4 ring-violet-100/80'
                              : ''
                      }`}
                      style={{
                        left: node.x,
                        top: node.y,
                        width: nodeDimensions.width,
                        height: nodeDimensions.height,
                        margin: 0,
                        zIndex: elevateSelectedMedia ? 20 : undefined,
                      }}
                    >
                      {isFullMediaCard &&
                        boardMediaUrls.length > 0 &&
                        (fullMediaType === 'image' ||
                          fullMediaType === 'video') && (
                          <CanvasMediaResultBoard
                            urls={boardMediaUrls}
                            mediaType={fullMediaType}
                            label={mediaSourceNode.assetName || node.title}
                            expanded={isMediaExpanded}
                            generating={isNodeGenerating}
                            transparentBackground={nodeShowsTransparentBackground(
                              mediaSourceNode,
                            )}
                            onExpand={() => setMediaNodeExpanded(node.id, true)}
                            onCollapse={() =>
                              setMediaNodeExpanded(node.id, false)
                            }
                            onSetMain={(url) => setMainNodeResult(node.id, url)}
                            onDownload={(url, index) => {
                              const downloadName = `${mediaSourceNode.assetName || node.title}-${index + 1}`;
                              if (fullMediaType === 'video')
                                void downloadVideo(url, downloadName);
                              else
                                void downloadImage(
                                  url,
                                  getCanvasImageDownloadName(downloadName),
                                );
                            }}
                            onAspectRatio={(mediaAspectRatio) => {
                              if (
                                Math.abs(
                                  (node.mediaAspectRatio || 0) -
                                    mediaAspectRatio,
                                ) < 0.001
                              )
                                return;
                              updateNode(node.id, { mediaAspectRatio });
                            }}
                          />
                        )}

                      {isFullMediaCard && isNodeGenerating && (
                        <NodeGeneratingOverlay
                          label={nodeProgress[node.id] || '生成中'}
                        />
                      )}

                      {isFullImageCard &&
                        isSelected &&
                        !isMediaExpanded &&
                        !isNodeGenerating &&
                        toolMode !== 'hand' &&
                        imageAiTool?.nodeId !== node.id && (
                          <>
                            {(['nw', 'ne', 'sw', 'se'] as const).map(
                              (corner) => {
                                const positionClass =
                                  corner === 'nw'
                                    ? '-left-2 -top-2 cursor-nwse-resize'
                                    : corner === 'ne'
                                      ? '-right-2 -top-2 cursor-nesw-resize'
                                      : corner === 'sw'
                                        ? '-bottom-2 -left-2 cursor-nesw-resize'
                                        : '-bottom-2 -right-2 cursor-nwse-resize';
                                return (
                                  <button
                                    key={corner}
                                    type="button"
                                    aria-label={`按原比例缩放${node.title}`}
                                    title="拖动并按原比例缩放"
                                    onPointerDown={(event) =>
                                      startMediaResize(
                                        event,
                                        node,
                                        corner,
                                        nodeDimensions,
                                      )
                                    }
                                    onClick={(event) => event.stopPropagation()}
                                    className={`absolute z-50 h-4 w-4 touch-none rounded-full border-2 border-white bg-violet-500 shadow-[0_2px_8px_rgba(15,23,42,0.45)] outline-none transition-colors hover:bg-violet-700 focus:ring-2 focus:ring-violet-300 ${positionClass}`}
                                  />
                                );
                              },
                            )}
                          </>
                        )}

                      {isFullImageCard &&
                        fullMediaUrl &&
                        !isMediaExpanded &&
                        !isNodeGenerating &&
                        imageAiTool?.nodeId !== node.id && (
                          <ImageHoverActions
                            label={node.title}
                            onPreview={() =>
                              openImagePreview(
                                fullMediaUrl,
                                mediaSourceNode.assetName || node.title,
                                {
                                  transparent:
                                    nodeShowsTransparentBackground(
                                      mediaSourceNode,
                                    ),
                                },
                              )
                            }
                            onDownload={() =>
                              void downloadImage(
                                fullMediaUrl,
                                getCanvasImageDownloadName(
                                  mediaSourceNode.assetName || node.title,
                                ),
                              )
                            }
                            corner
                            className={canExpandMedia ? '!top-11' : undefined}
                          />
                        )}

                      {isFullImageCard &&
                        fullMediaUrl &&
                        !isMediaExpanded &&
                        !isNodeGenerating &&
                        node.kind !== 'output' && (
                          <ImageNodeAiTools
                            nodeId={node.id}
                            imageUrl={fullMediaUrl}
                            selected={isSelected && selectedNodeIds.size === 1}
                            busy={generatingNodeIds.has(node.id)}
                            floatingHidden={hideNodeFloatingTools}
                            layoutNonce={
                              viewport.x + viewport.y + viewport.zoom
                            }
                            mode={
                              imageAiTool?.nodeId === node.id
                                ? imageAiTool.mode
                                : 'idle'
                            }
                            gridSize={
                              imageAiTool?.nodeId === node.id
                                ? imageAiTool.gridSize
                                : null
                            }
                            onRemoveBackground={() =>
                              runImageAiCommandOnNode(
                                node,
                                REMOVE_BACKGROUND_COMMAND,
                              )
                            }
                            onStartCrop={() => {
                              dragRef.current = null;
                              panRef.current = null;
                              altDuplicateDragRef.current = null;
                              mediaResizeRef.current = null;
                              setContextMenu(null);
                              setShortcutsOpen(false);
                              setImageAiTool({ nodeId: node.id, mode: 'crop' });
                            }}
                            onStartMatting={() => {
                              dragRef.current = null;
                              panRef.current = null;
                              altDuplicateDragRef.current = null;
                              mediaResizeRef.current = null;
                              setContextMenu(null);
                              setShortcutsOpen(false);
                              setImageAiTool({
                                nodeId: node.id,
                                mode: 'matting',
                              });
                            }}
                            onGenerateSmartMatte={(hintMaskDataUrl) =>
                              generateSmartMatte(node.id, hintMaskDataUrl)
                            }
                            onApplySmartMatting={(file) =>
                              applySmartMatting(node.id, file)
                            }
                            onStartGridSplit={(size) => {
                              dragRef.current = null;
                              panRef.current = null;
                              altDuplicateDragRef.current = null;
                              mediaResizeRef.current = null;
                              setContextMenu(null);
                              setShortcutsOpen(false);
                              setImageAiTool({
                                nodeId: node.id,
                                mode: 'grid-split',
                                gridSize: size,
                              });
                            }}
                            onSplitGridCells={(cells) =>
                              applyGridSplitCells(
                                node.id,
                                imageAiTool?.gridSize || { cols: 3, rows: 3 },
                                cells,
                              )
                            }
                            onGenerateGridHd={(cells, scale) =>
                              applyGridSplitCells(
                                node.id,
                                imageAiTool?.gridSize || { cols: 3, rows: 3 },
                                cells,
                                { hd: true, scale },
                              )
                            }
                            onCancel={closeImageAiTool}
                            onApplyCrop={(file) =>
                              applyCroppedImage(node.id, file)
                            }
                            onApplyErase={(maskDataUrl) =>
                              applyErasedImage(node.id, maskDataUrl)
                            }
                            onError={setToast}
                          />
                        )}

                      {isFullVideoCard &&
                        fullMediaUrl &&
                        !isMediaExpanded &&
                        !isNodeGenerating && (
                          <ImageHoverActions
                            label={node.title}
                            onPreview={() =>
                              openVideoPreview(
                                fullMediaUrl,
                                mediaSourceNode.assetName || node.title,
                              )
                            }
                            onDownload={() =>
                              void downloadVideo(
                                fullMediaUrl,
                                mediaSourceNode.assetName || node.title,
                              )
                            }
                            corner
                            className={canExpandMedia ? '!top-11' : undefined}
                          />
                        )}

                      {OFFICIAL_ASSET_LIBRARY_ENABLED &&
                        isFullMediaCard &&
                        fullMediaUrl &&
                        node.kind !== 'output' &&
                        !isMediaExpanded &&
                        !isNodeGenerating && (
                          <OfficialAssetCardToggle
                            node={node}
                            onToggle={(enabled) =>
                              void toggleOfficialAsset(node.id, enabled)
                            }
                          />
                        )}

                      {isConnectionDropTarget && (
                        <svg
                          aria-hidden="true"
                          className="canvas-connection-drop-target pointer-events-none absolute z-20 overflow-visible"
                          width={
                            nodeDimensions.width +
                            CONNECTION_DROP_MARQUEE_PADDING * 2
                          }
                          height={
                            nodeDimensions.height +
                            CONNECTION_DROP_MARQUEE_PADDING * 2
                          }
                          viewBox={`0 0 ${nodeDimensions.width + CONNECTION_DROP_MARQUEE_PADDING * 2} ${nodeDimensions.height + CONNECTION_DROP_MARQUEE_PADDING * 2}`}
                          style={{
                            left: -CONNECTION_DROP_MARQUEE_PADDING,
                            top: -CONNECTION_DROP_MARQUEE_PADDING,
                          }}
                        >
                          <rect
                            className="canvas-connection-drop-target__halo"
                            x="3"
                            y="3"
                            width={
                              nodeDimensions.width +
                              CONNECTION_DROP_MARQUEE_PADDING * 2 -
                              6
                            }
                            height={
                              nodeDimensions.height +
                              CONNECTION_DROP_MARQUEE_PADDING * 2 -
                              6
                            }
                            rx={isMediaPreviewCard ? 12 : 28}
                            ry={isMediaPreviewCard ? 12 : 28}
                          />
                          <rect
                            className="canvas-connection-drop-target__track"
                            x="3"
                            y="3"
                            width={
                              nodeDimensions.width +
                              CONNECTION_DROP_MARQUEE_PADDING * 2 -
                              6
                            }
                            height={
                              nodeDimensions.height +
                              CONNECTION_DROP_MARQUEE_PADDING * 2 -
                              6
                            }
                            rx={isMediaPreviewCard ? 12 : 28}
                            ry={isMediaPreviewCard ? 12 : 28}
                          />
                          <rect
                            className="canvas-connection-drop-target__path"
                            x="3"
                            y="3"
                            width={
                              nodeDimensions.width +
                              CONNECTION_DROP_MARQUEE_PADDING * 2 -
                              6
                            }
                            height={
                              nodeDimensions.height +
                              CONNECTION_DROP_MARQUEE_PADDING * 2 -
                              6
                            }
                            rx={isMediaPreviewCard ? 12 : 28}
                            ry={isMediaPreviewCard ? 12 : 28}
                          />
                        </svg>
                      )}

                      {node.kind !== 'text' && node.kind !== 'asset' && (
                        <button
                          type="button"
                          onPointerUp={(event) =>
                            completePointerConnection(event, node.id)
                          }
                          onClick={(event) => {
                            if (event.detail === 0)
                              completeConnection(event, node.id);
                          }}
                          data-canvas-input-node-id={node.id}
                          aria-label={`连接到${node.title}`}
                          className={`absolute -left-3 top-1/2 z-30 flex h-6 w-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border-[3px] border-white shadow-md transition-[background-color,box-shadow,transform] duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${
                            isConnectionDropTarget
                              ? 'canvas-connection-snap-port scale-125'
                              : pendingSourceId
                                ? 'bg-violet-500 hover:bg-violet-700'
                                : 'bg-slate-300 hover:bg-violet-500'
                          }`}
                        >
                          <span className="sr-only">输入连接点</span>
                        </button>
                      )}

                      {node.kind !== 'output' && (
                        <button
                          type="button"
                          onPointerDown={(event) =>
                            startConnection(event, node.id)
                          }
                          onClick={(event) =>
                            startConnectionWithKeyboard(event, node.id)
                          }
                          data-canvas-output-node-id={node.id}
                          aria-label={`从${node.title}开始连接`}
                          className={`absolute -right-3 top-1/2 z-30 flex h-6 w-6 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border-[3px] border-white shadow-md transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${
                            isPending
                              ? 'bg-violet-700 ring-4 ring-violet-200'
                              : 'bg-violet-500 hover:bg-violet-700'
                          }`}
                        >
                          <Plus size={10} className="text-white" />
                        </button>
                      )}

                      <div
                        onPointerDown={(event) => {
                          if (toolMode === 'hand') return;
                          event.stopPropagation();
                          if (beginAltDuplicateDrag(event, node)) return;
                          const draggedNodeIds = selectedNodeIds.has(node.id)
                            ? Array.from(selectedNodeIds)
                            : [node.id];
                          setSelectedNodeIds(new Set(draggedNodeIds));
                          setSelectedNodeId(node.id);
                          dragRef.current = {
                            nodeIds: draggedNodeIds,
                            startClientX: event.clientX,
                            startClientY: event.clientY,
                            startPositions: Object.fromEntries(
                              nodes
                                .filter((candidate) =>
                                  draggedNodeIds.includes(candidate.id),
                                )
                                .map((candidate) => [
                                  candidate.id,
                                  { x: candidate.x, y: candidate.y },
                                ]),
                            ),
                          };
                        }}
                        className={`z-10 flex items-center gap-2 rounded-xl ${toolMode === 'hand' ? 'cursor-grab active:cursor-grabbing' : 'cursor-move'} ${
                          isMediaPreviewCard
                            ? 'absolute -top-7 left-0 m-0 max-w-full p-0 text-slate-600'
                            : isExpandedVideoAnalysisResult
                              ? 'relative mb-0 flex-none rounded-b-none border-b border-slate-200/80 px-4 py-3'
                              : 'relative mb-2 px-1 py-1'
                        }`}
                      >
                        {isExpandedVideoAnalysisResult && (
                          <span className="flex h-6 w-6 flex-none items-center justify-center rounded-lg bg-violet-100 text-violet-600">
                            <Sparkles size={14} />
                          </span>
                        )}
                        <div className="min-w-0 flex-1">
                          <h3
                            className={`truncate font-semibold ${isMediaPreviewCard ? 'text-xs text-slate-600' : 'text-sm text-slate-900'}`}
                          >
                            {node.title}
                          </h3>
                        </div>
                      </div>

                      {!isFullMediaCard &&
                        (isExpandedVideoAnalysisResult ? (
                          <div className="flex min-h-0 flex-1 px-4 py-3">
                            {renderNodeBody(node)}
                          </div>
                        ) : (
                          renderNodeBody(node)
                        ))}
                    </article>
                    {isSelected &&
                      selectedNodeIds.size === 1 &&
                      renderQuickNodeSettings()}
                  </React.Fragment>
                );
              })}
            </div>

            {selectedEdgeCutLayout && selectedEdgeId && (
              <button
                type="button"
                aria-label="剪断连接"
                title="剪断连接（Delete）"
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  cancelConnection(selectedEdgeId);
                }}
                className="canvas-edge-cut-btn absolute z-[45] flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border border-slate-600 bg-slate-800 text-white shadow-[0_6px_16px_rgba(15,23,42,0.28)] outline-none transition-colors hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-violet-400"
                style={{
                  left: selectedEdgeCutLayout.left,
                  top: selectedEdgeCutLayout.top,
                }}
              >
                <Scissors size={13} />
              </button>
            )}

            {(isFileDragActive || isDroppingImages) && fileDropTargetNodeId && (
              <div
                role="status"
                aria-live="polite"
                className={`pointer-events-none absolute left-1/2 top-4 z-50 -translate-x-1/2 rounded-full border px-4 py-2 text-sm font-semibold shadow-lg backdrop-blur-md ${
                  fileDropTargetRejected
                    ? 'border-red-200 bg-red-50 text-red-700'
                    : 'border-violet-200 bg-white/95 text-violet-800'
                }`}
              >
                {isDroppingImages
                  ? '正在上传并替换素材...'
                  : fileDropTargetRejected
                    ? '该节点不支持拖入替换素材'
                    : '释放以替换该节点素材'}
              </div>
            )}

            {(isFileDragActive || isDroppingImages) &&
              !fileDropTargetNodeId && (
                <div
                  role="status"
                  aria-live="polite"
                  className="pointer-events-none absolute inset-4 z-50 flex items-center justify-center rounded-[28px] border-2 border-dashed border-violet-400 bg-slate-950/60 p-6 text-center text-white shadow-[0_24px_80px_rgba(15,23,42,0.28)] backdrop-blur-sm"
                >
                  <div className="flex max-w-sm flex-col items-center rounded-2xl border border-white/15 bg-slate-950/70 px-8 py-6 shadow-2xl backdrop-blur-xl">
                    <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-600 text-white shadow-lg shadow-violet-950/30">
                      {isDroppingImages ? (
                        <Loader2 size={23} className="animate-spin" />
                      ) : (
                        <ImageIcon size={23} />
                      )}
                    </span>
                    <p className="mt-4 text-sm font-semibold">
                      {isDroppingImages
                        ? `正在导入 ${droppedImageCount} 张图片`
                        : '释放鼠标，将图片添加到画布'}
                    </p>
                    <p className="mt-1.5 text-xs text-slate-300">
                      拖到空白处新建素材节点，或拖到已有图片/视频节点上替换
                    </p>
                  </div>
                </div>
              )}
          </div>

          {contextMenu &&
            contextMenu.targetEdgeId &&
            contextMenuTargetEdge &&
            portalCanvasFloatingMenu(
              <div
                ref={contextMenuRef}
                role="menu"
                aria-label="连线右键菜单"
                className="fixed z-[300] w-[180px] rounded-2xl border border-slate-200 bg-white/95 p-1.5 text-slate-800 shadow-[0_22px_60px_rgba(15,23,42,0.16)] backdrop-blur-xl"
                style={toCanvasScreenPoint(contextMenu.left, contextMenu.top)}
              >
                <div className="truncate px-3 pb-1.5 pt-1 text-[10px] font-medium text-slate-500">
                  {nodes.find(
                    (node) => node.id === contextMenuTargetEdge.source,
                  )?.title || '上游节点'}
                  <span className="px-1">→</span>
                  {nodes.find(
                    (node) => node.id === contextMenuTargetEdge.target,
                  )?.title || '下游节点'}
                </div>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => cancelConnection(contextMenuTargetEdge.id)}
                  className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-red-600 transition-colors duration-150 hover:bg-red-50 hover:text-red-700 focus:outline-none focus:ring-2 focus:ring-red-400"
                >
                  <Unlink size={15} />
                  <span className="flex-1">取消连接</span>
                  <kbd className="text-[11px] font-normal text-slate-400">
                    Delete
                  </kbd>
                </button>
              </div>,
            )}

          {contextMenu &&
            !contextMenu.targetEdgeId &&
            portalCanvasFloatingMenu(
              <div
                ref={contextMenuRef}
                role="menu"
                aria-label="画布右键菜单"
                className="canvas-floating-choice-menu fixed z-[300] w-[208px] rounded-2xl border border-slate-200 bg-white/95 p-1.5 text-slate-800 shadow-[0_22px_60px_rgba(15,23,42,0.16)] backdrop-blur-xl"
                style={toCanvasScreenPoint(contextMenu.left, contextMenu.top)}
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={uploadFromContextMenu}
                  className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                >
                  <Upload size={15} className="text-slate-500" />
                  <span className="flex-1">上传</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  disabled
                  title="即将开放"
                  className="flex h-10 w-full cursor-not-allowed items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-400"
                >
                  <Cloud size={15} />
                  <span className="flex-1">保存到我的资产</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={openNodeMenuFromContextMenu}
                  className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                >
                  <Plus size={15} className="text-slate-500" />
                  <span className="flex-1">添加节点</span>
                  <ChevronRight size={14} className="text-slate-500" />
                </button>
                <div
                  onMouseEnter={openQuickCommands}
                  onMouseLeave={scheduleQuickCommandsClose}
                >
                  <button
                    type="button"
                    role="menuitem"
                    aria-haspopup="menu"
                    aria-expanded={quickCommandsOpen}
                    disabled={!quickCommandSourceNode}
                    onFocus={openQuickCommands}
                    onClick={openQuickCommands}
                    title={
                      quickCommandSourceNode
                        ? '使用 AI 快速修改当前图片'
                        : '请先右键图片节点'
                    }
                    className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent"
                  >
                    <Sparkles size={15} />
                    <span className="flex-1">快捷指令</span>
                    <ChevronRight
                      size={14}
                      className={
                        quickCommandSourceNode
                          ? 'text-slate-400'
                          : 'text-slate-700'
                      }
                    />
                  </button>
                </div>

                <div className="mx-2 my-1 border-t border-slate-200" />

                <button
                  type="button"
                  role="menuitem"
                  disabled={!canUndo}
                  onClick={undoCanvas}
                  className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent"
                >
                  <Undo2 size={15} />
                  <span className="flex-1">撤销</span>
                  <kbd className="text-[11px] font-normal text-slate-500">
                    Ctrl/⌘ Z
                  </kbd>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  disabled={!canRedo}
                  onClick={redoCanvas}
                  className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent"
                >
                  <Redo2 size={15} />
                  <span className="flex-1">重做</span>
                  <kbd className="text-[11px] font-normal text-slate-500">
                    ⇧ Ctrl/⌘ Z
                  </kbd>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => void pasteFromContextMenu()}
                  className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                >
                  <ClipboardPaste size={15} className="text-slate-500" />
                  <span className="flex-1">粘贴</span>
                  <kbd className="text-[11px] font-normal text-slate-500">
                    Ctrl/⌘ V
                  </kbd>
                </button>
                {contextMenuTargetNode && (
                  <>
                    <div className="mx-2 my-1 border-t border-slate-200" />
                    {canCreateSameGenerationNode && (
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() =>
                          createSameGenerationNode(contextMenuTargetNode.id)
                        }
                        className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                      >
                        <CopyPlus size={15} className="text-violet-600" />
                        <span className="flex-1">生成同款</span>
                      </button>
                    )}
                    <button
                      type="button"
                      role="menuitem"
                      onClick={deleteNodeFromContextMenu}
                      className="flex h-10 w-full cursor-pointer items-center gap-2.5 rounded-xl px-3 text-left text-sm font-medium text-slate-700 transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                    >
                      <Trash2 size={15} />
                      <span className="flex-1">删除节点</span>
                      <kbd className="text-[11px] font-normal text-slate-400">
                        Delete
                      </kbd>
                    </button>
                  </>
                )}
              </div>,
            )}

          {contextMenu &&
            quickCommandsOpen &&
            quickCommandSourceNode &&
            portalCanvasFloatingMenu(
              <div
                ref={quickCommandsRef}
                role="menu"
                aria-label="图片快捷指令"
                onMouseEnter={openQuickCommands}
                onMouseLeave={scheduleQuickCommandsClose}
                className="fixed z-[300] flex max-h-[418px] w-[288px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white/95 text-slate-800 shadow-[0_24px_70px_rgba(15,23,42,0.16)] backdrop-blur-xl"
                style={toCanvasScreenPoint(
                  contextMenu.quickMenuLeft,
                  contextMenu.quickMenuTop,
                )}
              >
                <div className="shrink-0 border-b border-slate-200 px-3.5 py-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
                    <Sparkles size={14} className="text-violet-600" /> AI
                    图片快捷指令
                  </div>
                  <p className="mt-1 text-[11px] text-slate-400">
                    基于“{quickCommandSourceNode.title}”创建修改分支并自动生成
                  </p>
                </div>
                <div className="min-h-0 overflow-y-auto p-1.5">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={createCustomQuickImageNode}
                    className="group flex min-h-12 w-full cursor-pointer items-center gap-3 rounded-xl border border-dashed border-violet-400/45 bg-violet-400/5 px-2.5 py-2 text-left transition-colors duration-150 hover:bg-violet-400/15 focus:outline-none focus:ring-2 focus:ring-violet-400"
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-violet-200 bg-violet-50 text-violet-600">
                      <Plus size={16} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-semibold text-slate-800">
                        自定义指令
                      </span>
                      <span className="mt-0.5 block text-[10px] text-slate-400">
                        创建连接节点，输入名称与描述后保存
                      </span>
                    </span>
                    <ChevronRight
                      size={13}
                      className="shrink-0 text-violet-500"
                    />
                  </button>

                  {customImageCommands.length > 0 && (
                    <div className="mt-2 border-t border-slate-200 pt-1.5">
                      <p className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                        我的指令
                      </p>
                      {customImageCommands.map((command) => (
                        <div
                          key={command.id}
                          role="none"
                          className="group flex items-center rounded-xl transition-colors focus-within:bg-slate-100 hover:bg-slate-100"
                        >
                          <button
                            type="button"
                            role="menuitem"
                            onClick={() =>
                              runQuickImageCommand({
                                id: `custom-${command.id}`,
                                label: command.label,
                                description: '我的快捷指令',
                                prompt: command.prompt,
                                icon: Sparkles,
                              })
                            }
                            className="flex min-h-12 min-w-0 flex-1 cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2 text-left focus:outline-none focus:ring-2 focus:ring-violet-400"
                          >
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-violet-600">
                              <Sparkles size={16} />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-xs font-semibold text-slate-800">
                                {command.label}
                              </span>
                              <span className="mt-0.5 block truncate text-[10px] text-slate-500">
                                {command.prompt}
                              </span>
                            </span>
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              deleteCustomImageCommand(
                                command.id,
                                command.label,
                              );
                            }}
                            aria-label={`删除快捷指令 ${command.label}`}
                            title="删除快捷指令"
                            className="mr-1 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-slate-400 opacity-0 transition-all hover:bg-red-50 hover:text-red-600 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-red-400 group-hover:opacity-100"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="mt-2 border-t border-slate-200 pt-1.5">
                    <p className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                      内置指令
                    </p>
                    {QUICK_IMAGE_COMMANDS.map((command) => {
                      const CommandIcon = command.icon;
                      return (
                        <button
                          key={command.id}
                          type="button"
                          role="menuitem"
                          onClick={() => runQuickImageCommand(command)}
                          className="group flex min-h-12 w-full cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2 text-left transition-colors duration-150 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                        >
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-500 group-hover:text-violet-600">
                            <CommandIcon size={16} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="flex items-center gap-2 text-xs font-semibold text-slate-800">
                              {command.label}
                              {command.badge && (
                                <span className="rounded bg-cyan-50 px-1.5 py-0.5 text-[9px] font-bold text-cyan-700">
                                  {command.badge}
                                </span>
                              )}
                            </span>
                            <span className="mt-0.5 block truncate text-[10px] text-slate-500">
                              {command.description}
                            </span>
                          </span>
                          <ChevronRight
                            size={13}
                            className="shrink-0 text-slate-300 group-hover:text-violet-500"
                          />
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>,
            )}

          {nodeMenu &&
            portalCanvasFloatingMenu(
              <div
                ref={nodeMenuRef}
                role="menu"
                aria-label="添加节点"
                className="canvas-floating-choice-menu fixed z-[300] w-[304px] overflow-y-auto rounded-2xl border border-slate-200 bg-white/95 p-2 shadow-2xl backdrop-blur-xl"
                style={{
                  ...toCanvasScreenPoint(nodeMenu.left, nodeMenu.top),
                  maxHeight: 'min(516px, calc(100vh - 24px))',
                }}
              >
                <div className="px-2.5 pb-2 pt-1.5">
                  <p className="text-xs font-semibold text-slate-900">
                    {pendingSourceId ? '添加并连接节点' : '添加节点'}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {pendingSourceIds.length > 1
                      ? `选择节点类型，创建后会连上组内 ${pendingSourceIds.length} 个素材`
                      : pendingSourceId
                        ? '选择可连接的节点类型，创建后自动连线'
                        : '选择要放在当前位置的节点类型'}
                  </p>
                </div>
                <div className="space-y-1">
                  {(Object.keys(NODE_META) as CanvasNodeKind[])
                    .filter(
                      (kind) =>
                        kind !== 'output' &&
                        (ENABLE_VIDEO_ANALYSIS_NODE ||
                          kind !== 'video_analysis'),
                    )
                    .map((kind) => {
                      const meta = getNodeMeta(kind);
                      const Icon = meta.icon;
                      const connectionSources = (
                        pendingSourceIds.length > 0
                          ? pendingSourceIds
                          : pendingSourceId
                            ? [pendingSourceId]
                            : []
                      )
                        .map((sourceId) =>
                          nodes.find((item) => item.id === sourceId),
                        )
                        .filter((item): item is CanvasNodeData =>
                          Boolean(item),
                        );
                      const isCompatible =
                        connectionSources.length === 0 ||
                        connectionSources.some((source) =>
                          canConnect(source.kind, kind),
                        );
                      return (
                        <button
                          key={kind}
                          type="button"
                          role="menuitem"
                          disabled={!isCompatible}
                          onClick={() => addNode(kind, nodeMenu.nodePosition)}
                          className="group flex w-full cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2 text-left transition-colors duration-200 hover:bg-violet-50 focus:outline-none focus:ring-2 focus:ring-violet-400 disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:bg-transparent"
                        >
                          <span
                            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${meta.surface} ${meta.accent}`}
                          >
                            <Icon size={17} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block text-sm font-semibold text-slate-800 group-hover:text-violet-800">
                              {meta.label}
                            </span>
                            <span className="block truncate text-[11px] text-slate-500">
                              {meta.description}
                            </span>
                          </span>
                          <ChevronRight
                            size={14}
                            className="shrink-0 text-slate-300 group-hover:text-violet-500"
                          />
                        </button>
                      );
                    })}
                </div>
              </div>,
            )}

          {shortcutsOpen && (
            <section
              role="dialog"
              aria-label="画布快捷键"
              onPointerDown={(event) => event.stopPropagation()}
              className="absolute bottom-20 left-1/2 z-50 max-h-[calc(100%_-_104px)] w-[min(960px,calc(100%_-_32px))] -translate-x-1/2 overflow-y-auto rounded-2xl border border-slate-700/80 bg-slate-950/95 p-5 text-white shadow-[0_28px_80px_rgba(2,6,23,0.48)] backdrop-blur-xl sm:p-6"
            >
              <div className="mb-5 flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-semibold text-white">
                    画布快捷键
                  </h2>
                  <p className="mt-1 text-xs text-slate-400">
                    输入文字时仅保留保存与生成快捷键，避免误操作节点。
                  </p>
                </div>
                <button
                  ref={shortcutsCloseButtonRef}
                  type="button"
                  onClick={() => {
                    setShortcutsOpen(false);
                    shortcutsButtonRef.current?.focus();
                  }}
                  aria-label="关闭快捷键面板"
                  className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-xl text-slate-400 transition-colors duration-200 hover:bg-white/10 hover:text-white focus:outline-none focus:ring-2 focus:ring-violet-400"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4 xl:divide-x xl:divide-slate-800">
                {CANVAS_SHORTCUT_GROUPS.map((group) => (
                  <div
                    key={group.title}
                    className="min-w-0 xl:pl-6 xl:first:pl-0"
                  >
                    <h3 className="mb-3 text-xs font-semibold tracking-wide text-cyan-400">
                      {group.title}
                    </h3>
                    <div className="space-y-3">
                      {group.items.map((item) => (
                        <div
                          key={item.label}
                          className="flex items-center justify-between gap-3 text-xs"
                        >
                          <span className="text-slate-400">{item.label}</span>
                          <span className="flex shrink-0 items-center gap-1">
                            {item.keys.map((key, index) => (
                              <React.Fragment key={key}>
                                {index > 0 && (
                                  <span className="text-slate-600">+</span>
                                )}
                                <kbd className="rounded-md border border-slate-700 bg-slate-900 px-1.5 py-1 font-medium text-slate-200 shadow-sm">
                                  {key}
                                </kbd>
                              </React.Fragment>
                            ))}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {minimapOpen && minimapLayout && (
            <div
              className="absolute z-50"
              onPointerDown={(event) => event.stopPropagation()}
              style={{
                left: '50%',
                bottom: '4.75rem',
                transform: `translate(calc(-50% + ${toolbarOffset.x}px), ${toolbarOffset.y}px)`,
              }}
            >
              <div className="relative">
                <div
                  role="dialog"
                  aria-label="画布地图"
                  className={`rounded-2xl border p-1.5 shadow-lg backdrop-blur-xl ${
                    theme === 'dark'
                      ? 'bg-slate-900/92 border-white/15'
                      : 'border-slate-200 bg-white/95'
                  }`}
                >
                  <div
                    className="relative cursor-pointer overflow-hidden rounded-xl"
                    onPointerCancel={handleMinimapPointerUp}
                    onPointerDown={handleMinimapPointerDown}
                    onPointerMove={handleMinimapPointerMove}
                    onPointerUp={handleMinimapPointerUp}
                    style={{
                      width: MINIMAP_WIDTH,
                      height: MINIMAP_HEIGHT,
                      backgroundImage:
                        theme === 'dark'
                          ? 'radial-gradient(circle, rgba(148,163,184,0.28) 1px, transparent 1px)'
                          : 'radial-gradient(circle, rgba(100,116,139,0.28) 1px, transparent 1px)',
                      backgroundColor:
                        theme === 'dark'
                          ? 'rgba(15,23,42,0.88)'
                          : 'rgba(248,250,252,0.96)',
                      backgroundSize: '12px 12px',
                    }}
                  >
                    <div
                      aria-hidden="true"
                      className={`pointer-events-none absolute rounded-sm border ${
                        theme === 'dark'
                          ? 'border-white/35'
                          : 'border-slate-300'
                      }`}
                      style={{
                        left: minimapLayout.content.x,
                        top: minimapLayout.content.y,
                        width: minimapLayout.content.width,
                        height: minimapLayout.content.height,
                      }}
                    />
                    {minimapLayout.nodes.map((node) => (
                      <div
                        aria-hidden="true"
                        className={`pointer-events-none absolute rounded-[2px] ${
                          node.selected
                            ? 'bg-violet-500/80'
                            : theme === 'dark'
                              ? 'bg-slate-500/80'
                              : 'bg-slate-300'
                        }`}
                        key={node.id}
                        style={{
                          left: node.x,
                          top: node.y,
                          width: Math.max(4, node.width),
                          height: Math.max(4, node.height),
                        }}
                      />
                    ))}
                    <div
                      aria-hidden="true"
                      className={`pointer-events-none absolute rounded-sm border ${
                        theme === 'dark'
                          ? 'border-white/55 bg-white/15'
                          : 'border-slate-500/70 bg-slate-400/20'
                      }`}
                      style={{
                        left: minimapLayout.viewport.x,
                        top: minimapLayout.viewport.y,
                        width: Math.max(12, minimapLayout.viewport.width),
                        height: Math.max(12, minimapLayout.viewport.height),
                      }}
                    />
                  </div>
                </div>
                {showEmptyViewportHint && (
                  <div
                    role="status"
                    className="canvas-empty-viewport-hint absolute bottom-1.5 left-[calc(100%+8px)] z-10"
                  >
                    <span>当前视窗没有节点</span>
                    <button
                      onClick={returnViewportToNodes}
                      onPointerDown={(event) => event.stopPropagation()}
                      type="button"
                    >
                      返回节点
                    </button>
                    <button
                      aria-label="关闭提示"
                      className="canvas-empty-viewport-hint__close"
                      onClick={() => setEmptyViewportHintDismissed(true)}
                      onPointerDown={(event) => event.stopPropagation()}
                      type="button"
                    >
                      <X size={14} />
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {replaceMediaConfirm &&
            typeof document !== 'undefined' &&
            createPortal(
              <div
                className="fixed inset-0 z-[240] flex items-center justify-center bg-slate-950/40 p-4"
                role="presentation"
                onMouseDown={(event) => {
                  if (event.target === event.currentTarget) {
                    setReplaceMediaConfirm(null);
                    setToast('已取消替换素材');
                  }
                }}
              >
                <div
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="canvas-replace-media-title"
                  className="w-[min(400px,calc(100vw-32px))] rounded-2xl border border-slate-200 bg-white p-5 text-slate-900 shadow-[0_24px_64px_rgba(15,23,42,0.22)]"
                  onPointerDown={(event) => event.stopPropagation()}
                >
                  <h2
                    id="canvas-replace-media-title"
                    className="text-base font-semibold"
                  >
                    替换素材
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    该节点已有生成结果。替换素材后是否重新生成？
                  </p>
                  <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setReplaceMediaConfirm(null);
                        setToast('已取消替换素材');
                      }}
                      className="flex h-9 cursor-pointer items-center rounded-lg px-3 text-sm text-slate-600 transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={() => confirmReplaceNodeMedia(false)}
                      className="flex h-9 cursor-pointer items-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-violet-300"
                    >
                      仅替换
                    </button>
                    <button
                      type="button"
                      onClick={() => confirmReplaceNodeMedia(true)}
                      className="flex h-9 cursor-pointer items-center rounded-lg bg-violet-600 px-3 text-sm font-semibold text-white transition-colors hover:bg-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-300"
                    >
                      替换并重新生成
                    </button>
                  </div>
                </div>
              </div>,
              document.body,
            )}

          {tidyConfirm && (
            <div
              role="dialog"
              aria-modal="true"
              aria-label="是否保留此次整理结果"
              onPointerDown={(event) => event.stopPropagation()}
              className="absolute z-50 w-[228px] rounded-2xl border border-white/10 bg-slate-900/95 p-3 text-white shadow-[0_18px_40px_rgba(2,6,23,0.48)] backdrop-blur-xl"
              style={{
                left: '50%',
                bottom: '4.75rem',
                transform: `translate(calc(-50% + ${toolbarOffset.x}px), ${toolbarOffset.y}px)`,
              }}
            >
              <p className="px-1 text-sm font-medium leading-6 text-white">
                是否保留此次整理结果?
              </p>
              <div className="mt-3 flex items-center justify-end gap-1">
                <button
                  type="button"
                  onClick={revertTidyResult}
                  className="flex h-8 cursor-pointer items-center rounded-lg px-3 text-sm text-slate-200 transition-colors duration-200 hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-white/40"
                >
                  还原
                </button>
                <button
                  type="button"
                  onClick={keepTidyResult}
                  className="flex h-8 cursor-pointer items-center rounded-lg bg-white/15 px-3 text-sm font-medium text-white transition-colors duration-200 hover:bg-white/25 focus:outline-none focus:ring-2 focus:ring-white/40"
                >
                  保留
                </button>
              </div>
            </div>
          )}

          <div
            ref={toolbarRef}
            className="absolute bottom-4 left-1/2 z-20 flex items-center gap-1 overflow-visible rounded-2xl border border-white/90 bg-white/90 p-1.5 shadow-lg backdrop-blur-xl"
            style={{
              transform: `translate(calc(-50% + ${toolbarOffset.x}px), ${toolbarOffset.y}px)`,
            }}
          >
            <button
              type="button"
              onPointerDown={handleToolbarPointerDown}
              onPointerMove={handleToolbarPointerMove}
              onPointerUp={handleToolbarPointerUp}
              onPointerCancel={handleToolbarPointerUp}
              onKeyDown={handleToolbarKeyDown}
              aria-label="拖动画布工具栏"
              title="拖动工具栏（方向键可微调）"
              className="flex h-9 w-6 cursor-grab touch-none items-center justify-center rounded-lg text-slate-400 transition-colors duration-200 hover:bg-slate-100 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-violet-400 active:cursor-grabbing"
            >
              <GripVertical size={16} />
            </button>
            <span className="mx-1 h-5 w-px bg-slate-200" />
            <button
              type="button"
              onClick={() => {
                setToolMenuOpen(false);
                openCenteredNodeMenu();
              }}
              aria-label="打开添加节点菜单"
              aria-haspopup="menu"
              aria-expanded={Boolean(nodeMenu)}
              className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${nodeMenu ? 'bg-violet-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
            >
              <Plus size={18} />
            </button>
            <div className="relative" data-canvas-tool-menu="true">
              <button
                type="button"
                onClick={() => {
                  setNodeMenu(null);
                  setShortcutsOpen(false);
                  setToolMenuOpen((open) => !open);
                }}
                aria-label={toolMode === 'hand' ? '抓手工具' : '移动工具'}
                aria-haspopup="menu"
                aria-expanded={toolMenuOpen}
                title={toolMode === 'hand' ? '抓手工具 (H)' : '移动 (V)'}
                className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${
                  toolMenuOpen || toolMode === 'select' || toolMode === 'hand'
                    ? 'bg-violet-600 text-white'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {toolMode === 'hand' ? (
                  <Hand size={17} />
                ) : (
                  <MousePointer2 size={17} />
                )}
              </button>
              {toolMenuOpen && (
                <div
                  role="menu"
                  aria-label="画布工具"
                  className="canvas-floating-toolbar absolute bottom-[calc(100%+8px)] left-1/2 z-50 min-w-[168px] -translate-x-1/2 rounded-xl border border-slate-200 bg-white p-1 text-slate-700 shadow-[0_16px_40px_rgba(15,23,42,0.16)]"
                >
                  {(
                    [
                      {
                        mode: 'select',
                        label: '移动',
                        shortcut: 'V',
                        icon: MousePointer2,
                      },
                      {
                        mode: 'hand',
                        label: '抓手工具',
                        shortcut: 'H',
                        icon: Hand,
                      },
                    ] as const
                  ).map((item) => {
                    const Icon = item.icon;
                    const active = toolMode === item.mode;
                    return (
                      <button
                        key={item.mode}
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setToolMode(item.mode);
                          setToolMenuOpen(false);
                          setNodeMenu(null);
                          setShortcutsOpen(false);
                        }}
                        className={`flex h-9 w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 text-left text-xs font-medium focus:outline-none focus:ring-2 focus:ring-violet-300 ${
                          active
                            ? 'bg-slate-100 text-slate-900'
                            : 'text-slate-700 hover:bg-slate-100'
                        }`}
                      >
                        <Icon size={14} className="shrink-0 text-slate-500" />
                        <span className="flex-1 whitespace-nowrap">
                          {item.label}
                        </span>
                        <span className="whitespace-nowrap text-[11px] font-semibold text-slate-400">
                          {item.shortcut}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            <span className="mx-1 h-5 w-px bg-slate-200" />
            <button
              type="button"
              onClick={() =>
                setTheme((current) => (current === 'light' ? 'dark' : 'light'))
              }
              aria-label={
                theme === 'light' ? '切换到黑色主题' : '切换到白色主题'
              }
              title={theme === 'light' ? '切换到黑色主题' : '切换到白色主题'}
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-slate-600 transition-colors duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
            >
              {theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}
            </button>
            <span className="mx-1 h-5 w-px bg-slate-200" />
            <div
              className="flex h-9 items-center gap-2 px-2"
              role="group"
              aria-label="画布缩放"
            >
              <ZoomOut
                size={16}
                className="shrink-0 text-slate-400"
                aria-hidden="true"
              />
              <input
                type="range"
                min={MIN_ZOOM}
                max={MAX_ZOOM}
                step={0.05}
                value={viewport.zoom}
                onChange={(event) =>
                  setZoomAtCenter(Number(event.target.value))
                }
                aria-label="调整画布缩放"
                className="h-1.5 w-24 cursor-pointer accent-violet-600"
              />
              <button
                type="button"
                onClick={() => setZoomAtCenter(1)}
                aria-label="重置缩放为百分之百"
                title="重置为 100%"
                className="min-w-11 cursor-pointer rounded-lg px-1.5 py-1 text-xs font-semibold text-slate-600 transition-colors duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
              >
                {Math.round(viewport.zoom * 100)}%
              </button>
            </div>
            <span className="mx-1 h-5 w-px bg-slate-200" />
            <button
              type="button"
              onClick={fitView}
              aria-label="适应全部节点"
              title="适应全部节点"
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-slate-600 transition-colors duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
            >
              <Focus size={17} />
            </button>
            <button
              type="button"
              onClick={() => setViewport({ x: 40, y: 80, zoom: 1 })}
              aria-label="重置视图"
              title="重置视图"
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-slate-600 transition-colors duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
            >
              <Maximize2 size={17} />
            </button>
            <span className="mx-1 h-5 w-px bg-slate-200" />
            <button
              type="button"
              onClick={tidyCanvas}
              aria-label="整理画布"
              title="整理画布"
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-slate-600 transition-colors duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
            >
              <LayoutGrid size={17} />
            </button>
            <button
              type="button"
              onClick={openHistoryPage}
              aria-label="打开历史记录"
              title="历史记录"
              className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${historyPageOpen ? 'bg-violet-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
            >
              <History size={17} />
            </button>
            <button
              type="button"
              onClick={() => {
                setNodeMenu(null);
                setShortcutsOpen(false);
                setMinimapOpen((open) => !open);
              }}
              aria-label="打开画布地图"
              aria-pressed={minimapOpen}
              title="画布地图"
              className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${minimapOpen ? 'bg-violet-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
            >
              <MapIcon size={17} />
            </button>
            <span className="mx-1 h-5 w-px bg-slate-200" />
            <button
              ref={shortcutsButtonRef}
              type="button"
              onClick={() => {
                setNodeMenu(null);
                setMinimapOpen(false);
                setToolMenuOpen(false);
                setShortcutsOpen((open) => !open);
              }}
              aria-label="打开画布快捷键"
              aria-haspopup="dialog"
              aria-expanded={shortcutsOpen}
              title="画布快捷键 (?)"
              className={`flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${shortcutsOpen ? 'bg-violet-600 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
            >
              <Keyboard size={17} />
            </button>
          </div>
        </section>

        {chatOpen && (
          <CanvasChatPanel
            canvasId={normalizedCanvasId}
            canvasTitle={title}
            enabledModelIds={availableChatModels}
            generationModels={availableChatGenerationModels}
            hasSelectedNode={selectedNodeIds.size > 0}
            theme={theme}
            attachRequest={chatAttachRequest}
            onClose={() => setChatOpen(false)}
            buildContext={buildCanvasChatContext}
            onGenerateMedia={generateMediaFromCanvasChat}
          />
        )}

        {showSelectionToolbar &&
          selectionToolbarLayout &&
          typeof document !== 'undefined' &&
          createPortal(
            <div
              role="toolbar"
              aria-label="多选节点操作"
              data-canvas-selection-toolbar="true"
              onPointerDown={(event) => event.stopPropagation()}
              className="canvas-floating-toolbar fixed z-[200] flex items-center gap-0.5 rounded-2xl border border-slate-200 bg-white px-1.5 py-1 text-slate-700 shadow-[0_12px_36px_rgba(15,23,42,0.16)]"
              style={{
                left: selectionToolbarLayout.left,
                top: selectionToolbarLayout.top,
                transform: 'translateX(-50%)',
              }}
            >
              <div className="relative">
                <button
                  type="button"
                  aria-label="排列选中节点"
                  aria-haspopup="menu"
                  aria-expanded={selectionLayoutMenuOpen}
                  title="排列"
                  onClick={() => {
                    setSelectionGroupMenuOpen(false);
                    setSelectionLayoutMenuOpen((open) => !open);
                  }}
                  className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-slate-700 transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
                >
                  <Grid3X3 size={15} />
                </button>
                {selectionLayoutMenuOpen && (
                  <div
                    role="menu"
                    className="absolute bottom-[calc(100%+6px)] left-0 z-50 min-w-[148px] rounded-xl border border-slate-200 bg-white p-1 shadow-[0_16px_40px_rgba(15,23,42,0.16)]"
                  >
                    {(
                      [
                        { mode: 'grid', label: '宫格排列', icon: Grid3X3 },
                        {
                          mode: 'horizontal',
                          label: '水平排列',
                          icon: AlignHorizontalJustifyCenter,
                        },
                        {
                          mode: 'vertical',
                          label: '垂直排列',
                          icon: AlignVerticalJustifyCenter,
                        },
                      ] as const
                    ).map((item) => {
                      const Icon = item.icon;
                      return (
                        <button
                          key={item.mode}
                          type="button"
                          role="menuitem"
                          onClick={() => applySelectionLayout(item.mode)}
                          className="flex h-9 w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 text-left text-xs font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
                        >
                          <Icon size={14} className="shrink-0 text-slate-500" />
                          {item.label}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
              <span
                className="mx-0.5 h-5 w-px bg-slate-200"
                aria-hidden="true"
              />
              <button
                type="button"
                disabled
                title="即将开放"
                className="flex h-9 cursor-not-allowed items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-400"
              >
                <Cloud size={14} />
                保存到资产
              </button>
              <button
                type="button"
                onClick={duplicateSelectedNodes}
                className="flex h-9 cursor-pointer items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
              >
                <Copy size={14} />
                创建副本
              </button>
              <span
                className="mx-0.5 h-5 w-px bg-slate-200"
                aria-hidden="true"
              />
              <button
                type="button"
                onClick={() => void downloadSelectedMedia()}
                aria-label="批量下载"
                title="批量下载"
                className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-slate-700 transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
              >
                <Download size={15} />
              </button>
              <div className="relative">
                <button
                  type="button"
                  aria-haspopup="menu"
                  aria-expanded={selectionGroupMenuOpen}
                  onClick={() => {
                    setSelectionLayoutMenuOpen(false);
                    if (selectedPersistedGroupId) {
                      setSelectionGroupMenuOpen((open) => !open);
                      return;
                    }
                    groupSelectedNodes();
                  }}
                  className="flex h-9 cursor-pointer items-center gap-1 rounded-lg px-2.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
                >
                  <Link2 size={14} />
                  {selectedPersistedGroupId ? '已打组' : '打组'}
                  <ChevronDown
                    size={12}
                    className={`text-slate-400 transition-transform ${selectionGroupMenuOpen ? 'rotate-180' : ''}`}
                  />
                </button>
                {selectionGroupMenuOpen && (
                  <div
                    role="menu"
                    className="absolute left-0 top-[calc(100%+6px)] z-50 min-w-[132px] rounded-xl border border-slate-200 bg-white p-1 shadow-[0_16px_40px_rgba(15,23,42,0.16)]"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      onClick={ungroupSelectedNodes}
                      className="flex h-9 w-full cursor-pointer items-center rounded-lg px-2.5 text-left text-xs font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
                    >
                      取消打组
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setSelectionGroupMenuOpen(false);
                        setSelectedNodeId(null);
                        setSelectedNodeIds(new Set());
                        setSelectedEdgeId(null);
                      }}
                      className="flex h-9 w-full cursor-pointer items-center rounded-lg px-2.5 text-left text-xs font-medium text-slate-700 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
                    >
                      取消选择
                    </button>
                  </div>
                )}
              </div>
              <span
                className="mx-0.5 h-5 w-px bg-slate-200"
                aria-hidden="true"
              />
              <button
                type="button"
                onClick={attachSelectedNodesToChat}
                className="flex h-9 cursor-pointer items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300"
              >
                <MessageSquareText size={14} />
                添加到 Chat
              </button>
            </div>,
            document.body,
          )}

        {typeof document !== 'undefined' &&
          createPortal(
            <button
              type="button"
              onClick={() => setChatOpen((open) => !open)}
              aria-label={chatOpen ? '关闭画布助手' : '打开画布助手'}
              aria-pressed={chatOpen}
              title="画布助手"
              data-chat-open={chatOpen}
              className={`canvas-theme-accent-portal fixed bottom-24 z-[100] flex h-12 w-12 cursor-pointer items-center justify-center rounded-full border shadow-lg backdrop-blur-xl transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 ${chatOpen ? 'right-4 text-white sm:right-[416px]' : 'right-4 border-white/90 bg-white/90 hover:-translate-y-0.5 hover:bg-white'}`}
            >
              <MessageSquareText size={21} />
            </button>,
            document.body,
          )}

        <aside className="hidden" aria-hidden="true">
          {selectedNode ? (
            <>
              <div className="mb-5 flex items-start justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-500">
                    Node Settings
                  </p>
                  <h2 className="mt-1 text-lg font-semibold text-slate-900">
                    节点设置
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => deleteNode(selectedNode.id)}
                  aria-label="删除节点"
                  className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl border border-red-100 bg-red-50 text-red-600 transition-colors duration-200 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-400"
                >
                  <Trash2 size={16} />
                </button>
              </div>

              <div className="space-y-4">
                {selectedNode.kind === 'text' && (
                  <div
                    role="tablist"
                    aria-label="文本生成类型"
                    className="grid grid-cols-2 rounded-xl border border-slate-200 bg-slate-100 p-1"
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={selectedTextMode === 'image'}
                      onClick={() => {
                        clearNodeError(selectedNode.id);
                        updateNode(selectedNode.id, {
                          textGenerationMode: 'image',
                          status: 'draft',
                        });
                      }}
                      className={`flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg text-xs font-semibold transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-violet-400 ${selectedTextMode === 'image' ? 'bg-white text-violet-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
                    >
                      <ImageIcon size={14} /> 图片生成
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={selectedTextMode === 'video'}
                      onClick={() => {
                        clearNodeError(selectedNode.id);
                        updateNode(selectedNode.id, {
                          textGenerationMode: 'video',
                          status: 'draft',
                        });
                      }}
                      className={`flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg text-xs font-semibold transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-fuchsia-400 ${selectedTextMode === 'video' ? 'bg-white text-fuchsia-700 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
                    >
                      <Video size={14} /> 视频生成
                    </button>
                  </div>
                )}

                <label className="block">
                  <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                    节点名称
                  </span>
                  <input
                    value={selectedNode.title}
                    onChange={(event) =>
                      updateNode(selectedNode.id, {
                        title: event.target.value,
                        status: 'draft',
                      })
                    }
                    className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                  />
                </label>

                {selectedNode.kind === 'asset' && (
                  <section aria-label="素材导入" className="space-y-3">
                    {selectedNode.resultUrl ? (
                      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
                        <div
                          className={`group relative overflow-hidden ${
                            selectedNode.assetType === 'audio' ||
                            selectedNode.assetType === 'file' ||
                            selectedNode.assetType === 'link'
                              ? 'bg-slate-100 px-4 py-6'
                              : 'aspect-video bg-slate-950'
                          }`}
                        >
                          {selectedNode.assetType === 'video' ? (
                            <>
                              <video
                                src={selectedNode.resultUrl}
                                aria-hidden="true"
                                muted
                                playsInline
                                preload="metadata"
                                className="absolute inset-0 h-full w-full scale-110 object-cover opacity-45 blur-xl"
                              />
                              <video
                                src={selectedNode.resultUrl}
                                aria-label={
                                  selectedNode.assetName || selectedNode.title
                                }
                                controls
                                className="relative h-full w-full object-contain"
                              />
                            </>
                          ) : selectedNode.assetType === 'audio' ? (
                            <div className="flex flex-col items-center gap-3">
                              <Music2 size={22} className="text-violet-600" />
                              <audio
                                src={selectedNode.resultUrl}
                                aria-label={
                                  selectedNode.assetName || selectedNode.title
                                }
                                controls
                                className="w-full"
                              />
                            </div>
                          ) : selectedNode.assetType === 'file' ? (
                            <div className="flex flex-col items-center gap-2 text-center">
                              <FileText size={22} className="text-violet-600" />
                              <p className="text-sm font-semibold text-slate-800">
                                {selectedNode.assetName || '参考文档'}
                              </p>
                            </div>
                          ) : selectedNode.assetType === 'link' ? (
                            <div className="flex flex-col items-center gap-2 text-center">
                              <Link2 size={22} className="text-violet-600" />
                              <p
                                className="max-w-full truncate text-sm font-semibold text-slate-800"
                                title={selectedNode.resultUrl}
                              >
                                {selectedNode.assetName ||
                                  selectedNode.resultUrl}
                              </p>
                              <a
                                href={selectedNode.resultUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="text-xs font-semibold text-violet-700 hover:underline"
                              >
                                打开网页
                              </a>
                            </div>
                          ) : (
                            <>
                              <img
                                src={selectedNode.resultUrl}
                                alt=""
                                aria-hidden="true"
                                className="absolute inset-0 h-full w-full scale-110 object-cover opacity-50 blur-xl"
                              />
                              <img
                                src={selectedNode.resultUrl}
                                alt={
                                  selectedNode.assetName || selectedNode.title
                                }
                                className="relative h-full w-full object-contain"
                              />
                            </>
                          )}
                          {selectedNode.assetType !== 'video' &&
                            selectedNode.assetType !== 'audio' &&
                            selectedNode.assetType !== 'file' &&
                            selectedNode.assetType !== 'link' && (
                              <ImageHoverActions
                                label={
                                  selectedNode.assetName || selectedNode.title
                                }
                                onPreview={() =>
                                  openImagePreview(
                                    selectedNode.resultUrl!,
                                    selectedNode.assetName ||
                                      selectedNode.title,
                                  )
                                }
                                onDownload={() =>
                                  void downloadImage(
                                    selectedNode.resultUrl!,
                                    getCanvasImageDownloadName(
                                      selectedNode.assetName ||
                                        selectedNode.title,
                                    ),
                                  )
                                }
                              />
                            )}
                        </div>
                        {selectedNode.assetType === 'video' && (
                          <div className="grid grid-cols-2 gap-2 border-t border-slate-200 p-2">
                            <button
                              type="button"
                              onClick={() =>
                                openVideoPreview(
                                  selectedNode.resultUrl!,
                                  selectedNode.assetName || selectedNode.title,
                                )
                              }
                              className="flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-violet-200 bg-violet-50 text-xs font-semibold text-violet-700 transition-colors duration-200 hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                            >
                              <Eye size={14} /> 预览
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                void downloadVideo(
                                  selectedNode.resultUrl!,
                                  selectedNode.assetName || selectedNode.title,
                                )
                              }
                              className="flex h-9 cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 text-xs font-semibold text-slate-700 transition-colors duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-400"
                            >
                              <Download size={14} /> 下载
                            </button>
                          </div>
                        )}
                        {(selectedNode.assetType === 'audio' ||
                          selectedNode.assetType === 'file') && (
                          <div className="border-t border-slate-200 p-2">
                            <button
                              type="button"
                              onClick={() =>
                                void downloadCanvasMedia(
                                  selectedNode.resultUrl!,
                                  selectedNode.assetName || selectedNode.title,
                                  selectedNode.assetType === 'audio'
                                    ? 'audio'
                                    : 'file',
                                )
                              }
                              className="flex h-9 w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 text-xs font-semibold text-slate-700 transition-colors duration-200 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-400"
                            >
                              <Download size={14} /> 下载
                            </button>
                          </div>
                        )}
                        <div className="space-y-2 p-3">
                          <div className="flex items-center gap-2">
                            <span
                              className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-semibold ${
                                selectedNode.assetType === 'link'
                                  ? 'bg-slate-200 text-slate-700'
                                  : selectedNode.assetSource === 'local'
                                    ? 'bg-cyan-100 text-cyan-800'
                                    : 'bg-violet-100 text-violet-800'
                              }`}
                            >
                              {selectedNode.assetType === 'link'
                                ? '网页链接'
                                : selectedNode.assetSource === 'local'
                                  ? '本地导入'
                                  : '云素材库'}
                            </span>
                            <span className="rounded-full bg-white px-2 py-1 text-[10px] font-semibold text-slate-600">
                              {getCanvasAssetTypeLabel(selectedNode.assetType)}
                            </span>
                          </div>
                          <p
                            className="truncate text-xs font-medium text-slate-700"
                            title={
                              selectedNode.assetName ||
                              getAssetNameFromUrl(selectedNode.resultUrl)
                            }
                          >
                            {selectedNode.assetName ||
                              getAssetNameFromUrl(selectedNode.resultUrl) ||
                              '已导入素材'}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-2xl border border-dashed border-violet-200 bg-gradient-to-br from-cyan-50/80 to-violet-50/80 px-4 py-5 text-center">
                        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-violet-600 shadow-sm">
                          <FileImage size={20} />
                        </div>
                        <p className="mt-3 text-sm font-semibold text-slate-800">
                          选择参考素材
                        </p>
                        <p className="mt-1 text-xs leading-5 text-slate-500">
                          可导入图片、视频、音频、文档，或粘贴公开网页链接
                        </p>
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => openLocalAssetPicker(selectedNode.id)}
                        disabled={isImportingAsset}
                        className="flex h-10 cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-cyan-200 bg-cyan-50 px-2 text-xs font-semibold text-cyan-800 transition-colors duration-200 hover:bg-cyan-100 focus:outline-none focus:ring-2 focus:ring-cyan-400 disabled:cursor-wait disabled:opacity-60"
                      >
                        {isImportingAsset &&
                        localAssetNodeId === selectedNode.id ? (
                          <Loader2 size={15} className="animate-spin" />
                        ) : (
                          <Upload size={15} />
                        )}
                        {selectedNode.resultUrl ? '更换本地素材' : '本地导入'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setCloudAssetNodeId(selectedNode.id)}
                        className="flex h-10 cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50 px-2 text-xs font-semibold text-violet-800 transition-colors duration-200 hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                      >
                        <Cloud size={15} />
                        {selectedNode.resultUrl ? '更换云素材' : '云素材库'}
                      </button>
                    </div>

                    <label className="block">
                      <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                        网页参考
                      </span>
                      <div className="flex gap-2">
                        <input
                          value={webpageLinkDraft}
                          onChange={(event) =>
                            setWebpageLinkDraft(event.target.value)
                          }
                          onKeyDown={(event) => {
                            if (event.key !== 'Enter') return;
                            event.preventDefault();
                            applyWebpageLinkToAsset(
                              selectedNode.id,
                              webpageLinkDraft,
                            );
                          }}
                          placeholder="粘贴公开 http(s) 链接"
                          className="h-10 min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none transition-colors focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            applyWebpageLinkToAsset(
                              selectedNode.id,
                              webpageLinkDraft,
                            )
                          }
                          className="flex h-10 shrink-0 cursor-pointer items-center justify-center rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-violet-400"
                        >
                          使用链接
                        </button>
                      </div>
                      <p className="mt-1 text-[11px] leading-4 text-slate-400">
                        万相 3.0 全能参考每次只能使用一份文档或一个网页
                      </p>
                    </label>

                    {selectedNode.resultUrl && (
                      <button
                        type="button"
                        onClick={() => clearImportedAsset(selectedNode.id)}
                        className="flex h-9 w-full cursor-pointer items-center justify-center gap-1.5 rounded-xl text-xs font-semibold text-slate-500 transition-colors duration-200 hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-300"
                      >
                        <Trash2 size={14} /> 移除当前素材
                      </button>
                    )}
                  </section>
                )}

                {selectedNode.kind !== 'asset' && (
                  <label className="block">
                    <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                      {selectedNode.kind === 'image'
                        ? '图片描述'
                        : selectedNode.kind === 'video'
                          ? '视频描述'
                          : selectedNode.kind === 'video_analysis'
                            ? '分析要求（可选）'
                            : selectedNode.kind === 'music'
                              ? '音乐描述'
                              : selectedNode.kind === 'tts'
                                ? '配音文案'
                                : '提示词'}
                    </span>
                    <textarea
                      value={selectedNode.prompt}
                      onChange={(event) => {
                        clearNodeError(selectedNode.id);
                        updateNode(selectedNode.id, {
                          prompt: event.target.value,
                          status: 'draft',
                        });
                      }}
                      rows={
                        [
                          'image',
                          'video',
                          'video_analysis',
                          'music',
                          'tts',
                        ].includes(selectedNode.kind)
                          ? 5
                          : 7
                      }
                      placeholder={
                        selectedNode.kind === 'image'
                          ? selectedImageGenerationMode === 'reference_image'
                            ? '描述希望生成的图片；输入 @ 可按连线顺序引用指定图片...'
                            : '描述希望生成的图片内容、风格、构图和细节...'
                          : selectedNode.kind === 'video'
                            ? selectedVideoGenerationMode === 'reference_video'
                              ? '描述镜头、运动、主体和声音；输入 @ 可按连线顺序引用指定视频...'
                              : selectedVideoGenerationMode ===
                                  'reference_assets'
                                ? '描述镜头、运动、主体和声音；输入 @ 可按连线顺序引用图片、视频、音频、文档或网页...'
                                : '描述镜头、运动、主体和声音；输入 @ 可按连线顺序引用指定图片...'
                            : selectedNode.kind === 'video_analysis'
                              ? '可选：说明需要重点分析的主体、镜头、节奏、口播或可复用提示词...'
                              : selectedNode.kind === 'music'
                                ? '描述音乐风格、情绪、节奏、乐器和结构；也可以连接文本提示词节点...'
                                : selectedNode.kind === 'tts'
                                  ? '输入需要配音的文案；也可以连接文本提示词节点自动带入文案...'
                                  : '描述希望生成的内容...'
                      }
                      className="w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm leading-6 text-slate-800 outline-none transition-colors focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                    />
                  </label>
                )}

                {((selectedNode.kind === 'image' &&
                  selectedImageGenerationMode === 'reference_image') ||
                  selectedNode.kind === 'video') &&
                  renderImageReferenceMentions(selectedNode, true)}

                {selectedNode.kind === 'text' && (
                  <>
                    {selectedTextMode === 'image' ? (
                      <>
                        <div>
                          <label className="block">
                            <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                              模型
                            </span>
                            <select
                              value={selectedTextImageModel}
                              onChange={(event) => {
                                const nextModel = event.target.value;
                                const nextConfig =
                                  mediaModelCatalog[nextModel] || {};
                                const nextResolutions: string[] =
                                  nextConfig.supported_resolutions || ['1K'];
                                const nextAspectRatios: string[] =
                                  nextConfig.supported_aspect_ratios ||
                                  IMAGE_ASPECT_RATIOS;
                                clearNodeError(selectedNode.id);
                                updateNode(selectedNode.id, {
                                  textImageConfig: {
                                    ...selectedTextImageConfig,
                                    model: nextModel,
                                    aspectRatio: nextAspectRatios.includes(
                                      selectedTextImageConfig.aspectRatio || '',
                                    )
                                      ? selectedTextImageConfig.aspectRatio
                                      : nextAspectRatios[0],
                                    resolution: nextResolutions.includes(
                                      selectedTextImageConfig.resolution || '',
                                    )
                                      ? selectedTextImageConfig.resolution
                                      : nextResolutions[0],
                                  },
                                  status: 'draft',
                                });
                              }}
                              className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                            >
                              {availableImageModels.map((model) => (
                                <option key={model} value={model}>
                                  {mediaModelCatalog[model]?.label || model}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <label className="block">
                            <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                              比例
                            </span>
                            <select
                              value={
                                selectedTextImageAspectRatios.includes(
                                  selectedTextImageConfig.aspectRatio || '',
                                )
                                  ? selectedTextImageConfig.aspectRatio
                                  : selectedTextImageAspectRatios[0]
                              }
                              onChange={(event) =>
                                updateNode(selectedNode.id, {
                                  textImageConfig: {
                                    ...selectedTextImageConfig,
                                    aspectRatio: event.target.value,
                                  },
                                  status: 'draft',
                                })
                              }
                              className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                            >
                              {selectedTextImageAspectRatios.map((ratio) => (
                                <option key={ratio} value={ratio}>
                                  {ratio}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="block">
                            <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                              画质
                            </span>
                            <select
                              value={
                                selectedTextImageResolutions.includes(
                                  selectedTextImageConfig.resolution || '',
                                )
                                  ? selectedTextImageConfig.resolution
                                  : selectedTextImageResolutions[0]
                              }
                              onChange={(event) =>
                                updateNode(selectedNode.id, {
                                  textImageConfig: {
                                    ...selectedTextImageConfig,
                                    resolution: event.target.value,
                                  },
                                  status: 'draft',
                                })
                              }
                              className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                            >
                              {selectedTextImageResolutions.map(
                                (resolution) => (
                                  <option key={resolution} value={resolution}>
                                    {resolution}
                                  </option>
                                ),
                              )}
                            </select>
                          </label>
                        </div>

                        <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-600">
                          {selectedTextImageModelConfig.description ||
                            '根据文本提示词直接生成图片'}
                          <div className="mt-1 font-medium text-slate-700">
                            纯文本生成 · {selectedTextImageCount} 张
                          </div>
                        </div>

                        <ImageCostEstimate
                          modelLabel={
                            selectedTextImageModelConfig.label ||
                            selectedTextImageModel
                          }
                          resolution={selectedTextImageResolution}
                          count={selectedTextImageCount}
                          pricePerImage={selectedTextImagePricePerImage}
                          priceCurrency={selectedTextImagePriceCurrency}
                          cnyToUsdRate={cnyToUsdRate}
                          theme={theme}
                        />

                        <button
                          type="button"
                          onClick={() =>
                            void generateImageNode(selectedNode.id)
                          }
                          disabled={
                            hasSaveConflict ||
                            !selectedNode.prompt.trim() ||
                            selectedTextImageIsGenerating
                          }
                          className="flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 text-sm font-semibold text-white transition-colors duration-200 hover:bg-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                        >
                          {selectedTextImageIsGenerating ? (
                            <Loader2 size={17} className="animate-spin" />
                          ) : (
                            <Sparkles size={17} />
                          )}
                          {selectedTextImageIsGenerating
                            ? '正在生成图片...'
                            : selectedNode.resultAssetType === 'image'
                              ? '重新生成图片'
                              : '生成图片'}
                        </button>
                      </>
                    ) : (
                      <>
                        <div>
                          <label className="block">
                            <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                              模型
                            </span>
                            <select
                              value={selectedTextVideoModel}
                              onChange={(event) => {
                                const nextModel = event.target.value;
                                const nextConfig =
                                  mediaModelCatalog[nextModel] || {};
                                const nextResolutions: string[] =
                                  nextConfig.supported_resolutions || ['720p'];
                                const nextRatios: string[] =
                                  nextConfig.supported_aspect_ratios ||
                                  VIDEO_ASPECT_RATIOS;
                                const nextDurationRange: number[] =
                                  nextConfig.duration_range_seconds || [2, 15];
                                const nextDurationOptions: number[] =
                                  nextConfig.duration_options_seconds || [];
                                clearNodeError(selectedNode.id);
                                updateNode(selectedNode.id, {
                                  textVideoConfig: {
                                    ...selectedTextVideoConfig,
                                    model: nextModel,
                                    resolution: nextResolutions.includes(
                                      selectedTextVideoConfig.resolution || '',
                                    )
                                      ? selectedTextVideoConfig.resolution
                                      : nextResolutions[0],
                                    aspectRatio: nextRatios.includes(
                                      selectedTextVideoConfig.aspectRatio || '',
                                    )
                                      ? selectedTextVideoConfig.aspectRatio
                                      : nextRatios[0],
                                    duration:
                                      nextDurationOptions.length > 0 &&
                                      !nextDurationOptions.includes(
                                        Number(
                                          selectedTextVideoConfig.duration,
                                        ),
                                      )
                                        ? Number(
                                            nextConfig.default_duration_seconds ||
                                              nextDurationOptions[0],
                                          )
                                        : clamp(
                                            Number(
                                              selectedTextVideoConfig.duration,
                                            ) ||
                                              Number(
                                                nextConfig.default_duration_seconds ||
                                                  nextDurationRange[0] ||
                                                  5,
                                              ),
                                            Number(nextDurationRange[0] || 2),
                                            Number(nextDurationRange[1] || 15),
                                          ),
                                    extensionCount:
                                      nextConfig.supports_extension === false
                                        ? 0
                                        : selectedTextVideoConfig.extensionCount ||
                                          0,
                                  },
                                  status: 'draft',
                                });
                              }}
                              className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100"
                            >
                              {availableTextVideoModels.map((model) => (
                                <option key={model} value={model}>
                                  {mediaModelCatalog[model]?.label || model}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <label className="block">
                            <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                              比例
                            </span>
                            <select
                              value={
                                selectedTextVideoAspectRatios.includes(
                                  selectedTextVideoConfig.aspectRatio || '',
                                )
                                  ? selectedTextVideoConfig.aspectRatio
                                  : selectedTextVideoAspectRatios[0]
                              }
                              onChange={(event) =>
                                updateNode(selectedNode.id, {
                                  textVideoConfig: {
                                    ...selectedTextVideoConfig,
                                    aspectRatio: event.target.value,
                                  },
                                  status: 'draft',
                                })
                              }
                              className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100"
                            >
                              {selectedTextVideoAspectRatios.map((ratio) => (
                                <option key={ratio} value={ratio}>
                                  {ratio}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="block">
                            <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                              分辨率
                            </span>
                            <select
                              value={
                                selectedTextVideoResolutions.includes(
                                  selectedTextVideoConfig.resolution || '',
                                )
                                  ? selectedTextVideoConfig.resolution
                                  : selectedTextVideoResolutions[0]
                              }
                              onChange={(event) =>
                                updateNode(selectedNode.id, {
                                  textVideoConfig: {
                                    ...selectedTextVideoConfig,
                                    resolution: event.target.value,
                                  },
                                  status: 'draft',
                                })
                              }
                              className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100"
                            >
                              {selectedTextVideoResolutions.map(
                                (resolution) => (
                                  <option key={resolution} value={resolution}>
                                    {resolution === '4k' ? '4K' : resolution}
                                  </option>
                                ),
                              )}
                            </select>
                          </label>
                        </div>

                        <label className="block">
                          <span className="mb-1.5 flex items-center justify-between text-xs font-semibold text-slate-600">
                            <span>
                              {selectedTextVideoUsesTargetDuration
                                ? '时长（秒）'
                                : '延长次数'}
                            </span>
                            <span className="font-medium text-slate-400">
                              总时长约 {selectedTextVideoEffectiveDuration} 秒
                            </span>
                          </span>
                          <DeferredNumberInput
                            min={
                              selectedTextVideoUsesTargetDuration
                                ? Number(selectedTextVideoDurationRange[0] || 2)
                                : 0
                            }
                            max={
                              selectedTextVideoUsesTargetDuration
                                ? Number(
                                    selectedTextVideoDurationRange[1] || 15,
                                  )
                                : selectedTextVideoIsLite
                                  ? 0
                                  : maxVideoExtensionCount
                            }
                            step={
                              selectedTextVideoModelConfig
                                .duration_options_seconds?.length > 1
                                ? Math.max(
                                    1,
                                    Number(
                                      selectedTextVideoModelConfig
                                        .duration_options_seconds[1] ?? 1,
                                    ) -
                                      Number(
                                        selectedTextVideoModelConfig
                                          .duration_options_seconds[0] ?? 0,
                                      ),
                                  )
                                : 1
                            }
                            value={
                              selectedTextVideoUsesTargetDuration
                                ? selectedTextVideoDuration
                                : selectedTextVideoExtensionCount
                            }
                            disabled={
                              !selectedTextVideoUsesTargetDuration &&
                              selectedTextVideoIsLite
                            }
                            ariaLabel={
                              selectedTextVideoUsesTargetDuration
                                ? '视频时长（秒）'
                                : '视频延长次数'
                            }
                            onCommit={(value) =>
                              updateNode(selectedNode.id, {
                                textVideoConfig:
                                  selectedTextVideoUsesTargetDuration
                                    ? {
                                        ...selectedTextVideoConfig,
                                        duration: value,
                                      }
                                    : {
                                        ...selectedTextVideoConfig,
                                        extensionCount: value,
                                      },
                                status: 'draft',
                              })
                            }
                            className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100 disabled:bg-slate-100 disabled:text-slate-400"
                          />
                        </label>

                        <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-600">
                          {selectedTextVideoModelConfig.description ||
                            '根据文本提示词直接生成视频'}
                          <div className="mt-1 font-medium text-slate-700">
                            纯文本单次生成
                          </div>
                        </div>

                        {nodeProgress[selectedNode.id] && (
                          <div
                            role="status"
                            className="flex items-start gap-2 rounded-xl border border-fuchsia-100 bg-fuchsia-50 px-3 py-2.5 text-xs leading-5 text-fuchsia-700"
                          >
                            <Loader2
                              size={14}
                              className="mt-0.5 shrink-0 animate-spin"
                            />{' '}
                            {nodeProgress[selectedNode.id]}
                          </div>
                        )}

                        <div className="flex items-center gap-3">
                          <VideoCostEstimate
                            modelLabel={
                              selectedTextVideoModelConfig.label ||
                              selectedTextVideoModel
                            }
                            resolution={selectedTextVideoResolution}
                            duration={selectedTextVideoEffectiveDuration}
                            count={selectedTextVideoCount}
                            pricePerSecond={selectedTextVideoPricePerSecond}
                            priceCurrency={selectedTextVideoPriceCurrency}
                            cnyToUsdRate={cnyToUsdRate}
                            theme={theme}
                          />
                          <button
                            type="button"
                            onClick={() =>
                              void generateVideoNode(selectedNode.id)
                            }
                            disabled={
                              hasSaveConflict ||
                              !selectedNode.prompt.trim() ||
                              selectedTextVideoIsGenerating
                            }
                            className="flex h-11 min-w-0 flex-1 cursor-pointer items-center justify-center gap-2 rounded-xl bg-fuchsia-600 px-4 text-sm font-semibold text-white transition-colors duration-200 hover:bg-fuchsia-700 focus:outline-none focus:ring-2 focus:ring-fuchsia-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                          >
                            {selectedTextVideoIsGenerating ? (
                              <Loader2 size={17} className="animate-spin" />
                            ) : (
                              <Video size={17} />
                            )}
                            {selectedTextVideoIsGenerating
                              ? '正在生成视频...'
                              : selectedNode.resultAssetType === 'video'
                                ? '重新生成视频'
                                : '生成视频'}
                          </button>
                        </div>
                      </>
                    )}

                    {nodeErrors[selectedNode.id] && (
                      <div
                        role="alert"
                        className="whitespace-pre-line break-words rounded-xl border border-red-100 bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700"
                      >
                        {nodeErrors[selectedNode.id]}
                      </div>
                    )}

                    {selectedTextResults.length > 0 && (
                      <>
                        {selectedTextMode === 'image' ? (
                          <div className="grid grid-cols-2 gap-2">
                            {selectedTextResults.map((result, index) => (
                              <div
                                key={result.id}
                                className="group relative overflow-hidden rounded-xl border border-slate-200 bg-slate-100"
                              >
                                <img
                                  src={result.url}
                                  alt={`${selectedNode.title} 文生图结果 ${index + 1}`}
                                  className="aspect-square w-full object-cover"
                                />
                                <ImageHoverActions
                                  compact
                                  label={`${selectedNode.title}文生图结果${index + 1}`}
                                  onPreview={() =>
                                    openImagePreview(
                                      result.url,
                                      `${selectedNode.title}-文生图-${index + 1}`,
                                    )
                                  }
                                  onDownload={() =>
                                    void downloadImage(
                                      result.url,
                                      getCanvasImageDownloadName(
                                        `${selectedNode.title}-文生图-${index + 1}`,
                                      ),
                                    )
                                  }
                                />
                                <button
                                  type="button"
                                  onClick={() =>
                                    removeNodeResult(selectedNode.id, result.id)
                                  }
                                  aria-label={`移除文生图结果 ${index + 1}`}
                                  className="absolute right-1.5 top-1.5 z-30 flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg bg-slate-950/70 text-white opacity-0 backdrop-blur transition-opacity duration-200 hover:bg-red-600 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-white group-hover:opacity-100"
                                >
                                  <X size={14} />
                                </button>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="space-y-2">
                            {selectedTextResults.map((result, index) => (
                              <VideoResultCard
                                key={result.id}
                                url={result.url}
                                label={`${selectedNode.title} 文生视频结果 ${index + 1}`}
                                onPreview={() =>
                                  openVideoPreview(
                                    result.url,
                                    `${selectedNode.title}-文生视频-${index + 1}`,
                                  )
                                }
                                onDownload={() =>
                                  void downloadVideo(
                                    result.url,
                                    `${selectedNode.title}-文生视频-${index + 1}`,
                                  )
                                }
                                onRemove={() =>
                                  removeNodeResult(selectedNode.id, result.id)
                                }
                              />
                            ))}
                          </div>
                        )}
                        {selectedTextMode === 'image' && (
                          <div className="grid grid-cols-2 gap-2">
                            <button
                              type="button"
                              onClick={() =>
                                addConnectedGenerationNode(
                                  selectedNode.id,
                                  'image',
                                  {
                                    model: selectedTextImageModel,
                                    aspectRatio:
                                      selectedTextImageConfig.aspectRatio,
                                    resolution:
                                      selectedTextImageConfig.resolution,
                                  },
                                )
                              }
                              className="flex h-10 cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50 text-xs font-semibold text-violet-700 transition-colors duration-200 hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-400"
                            >
                              <ImageIcon size={15} /> 再次生图
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                addConnectedGenerationNode(
                                  selectedNode.id,
                                  'video',
                                )
                              }
                              className="flex h-10 cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-fuchsia-200 bg-fuchsia-50 text-xs font-semibold text-fuchsia-700 transition-colors duration-200 hover:bg-fuchsia-100 focus:outline-none focus:ring-2 focus:ring-fuchsia-400"
                            >
                              <Video size={15} /> 制作视频
                            </button>
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}

                {selectedNode.kind === 'image' && (
                  <>
                    {selectedImageGenerationMode === 'reference_image' &&
                      selectedImageReferenceCount === 0 && (
                        <div
                          role="status"
                          className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-800"
                        >
                          需要连接一张输入图片：可使用云素材图片，或上游文本节点生成的图片。
                        </div>
                      )}
                    {selectedImagePrompt &&
                      selectedImagePrompt !== selectedNode.prompt.trim() && (
                        <div className="rounded-xl border border-cyan-100 bg-cyan-50 px-3 py-2.5 text-xs leading-5 text-cyan-800">
                          已合并上游文本提示词；生成时会与本节点描述一起提交。
                        </div>
                      )}

                    <div>
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          生成模式
                        </span>
                        <select
                          value={selectedImageGenerationMode}
                          onChange={(event) => {
                            clearNodeError(selectedNode.id);
                            updateNode(selectedNode.id, {
                              imageGenerationMode: event.target
                                .value as ImageGenerationMode,
                              status: 'draft',
                            });
                          }}
                          aria-label="图片生成模式"
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        >
                          {IMAGE_GENERATION_MODE_OPTIONS.map((option) => (
                            <option
                              key={option.value}
                              value={option.value}
                              disabled={
                                !selectedImageSupportedModes.includes(
                                  option.value,
                                )
                              }
                            >
                              {option.label}
                              {selectedImageSupportedModes.includes(
                                option.value,
                              )
                                ? ''
                                : '（不支持）'}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div>
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          模型
                        </span>
                        <select
                          value={selectedImageModel}
                          onChange={(event) => {
                            const nextModel = event.target.value;
                            const nextConfig =
                              mediaModelCatalog[nextModel] || {};
                            const nextResolutions: string[] =
                              nextConfig.supported_resolutions || ['1K'];
                            const nextAspectRatios: string[] =
                              nextConfig.supported_aspect_ratios ||
                              IMAGE_ASPECT_RATIOS;
                            clearNodeError(selectedNode.id);
                            updateNode(selectedNode.id, {
                              model: nextModel,
                              imageGenerationMode: resolveImageGenerationMode(
                                nextConfig,
                                selectedImageGenerationMode,
                                'reference_image',
                              ),
                              aspectRatio: nextAspectRatios.includes(
                                selectedNode.aspectRatio || '',
                              )
                                ? selectedNode.aspectRatio
                                : nextAspectRatios[0],
                              resolution: nextResolutions.includes(
                                selectedNode.resolution || '',
                              )
                                ? selectedNode.resolution
                                : nextResolutions[0],
                              status: 'draft',
                            });
                          }}
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        >
                          {availableImageModels.map((model) => (
                            <option key={model} value={model}>
                              {mediaModelCatalog[model]?.label || model}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          比例
                        </span>
                        <select
                          value={
                            selectedImageAspectRatios.includes(
                              selectedNode.aspectRatio || '',
                            )
                              ? selectedNode.aspectRatio
                              : selectedImageAspectRatios[0]
                          }
                          onChange={(event) =>
                            updateNode(selectedNode.id, {
                              aspectRatio: event.target.value,
                              status: 'draft',
                            })
                          }
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        >
                          {selectedImageAspectRatios.map((ratio) => (
                            <option key={ratio} value={ratio}>
                              {ratio}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          画质
                        </span>
                        <select
                          value={
                            selectedImageResolutions.includes(
                              selectedNode.resolution || '',
                            )
                              ? selectedNode.resolution
                              : selectedImageResolutions[0]
                          }
                          onChange={(event) =>
                            updateNode(selectedNode.id, {
                              resolution: event.target.value,
                              status: 'draft',
                            })
                          }
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        >
                          {selectedImageResolutions.map((resolution) => (
                            <option key={resolution} value={resolution}>
                              {resolution}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-600">
                      {selectedImageModelConfig.description || '图片生成模型'}
                      <div className="mt-1 font-medium text-slate-700">
                        {selectedImageGenerationMode === 'reference_image'
                          ? `已连接 ${selectedImageReferenceCount} 张参考图 · 生成 ${selectedImageCount} 张`
                          : `纯文本生成 · ${selectedImageCount} 张`}
                      </div>
                    </div>

                    <ImageCostEstimate
                      modelLabel={
                        selectedImageModelConfig.label || selectedImageModel
                      }
                      resolution={selectedImageResolution}
                      count={selectedImageCount}
                      pricePerImage={selectedImagePricePerImage}
                      priceCurrency={selectedImagePriceCurrency}
                      cnyToUsdRate={cnyToUsdRate}
                      theme={theme}
                    />

                    {nodeErrors[selectedNode.id] && (
                      <div
                        role="alert"
                        className="whitespace-pre-line break-words rounded-xl border border-red-100 bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700"
                      >
                        {nodeErrors[selectedNode.id]}
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() => void generateImageNode(selectedNode.id)}
                      disabled={
                        hasSaveConflict ||
                        !selectedImagePrompt ||
                        (selectedImageGenerationMode === 'reference_image' &&
                          selectedImageReferenceCount === 0) ||
                        selectedImageIsGenerating
                      }
                      className="flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 text-sm font-semibold text-white transition-colors duration-200 hover:bg-violet-700 focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                    >
                      {selectedImageIsGenerating ? (
                        <Loader2 size={17} className="animate-spin" />
                      ) : (
                        <Sparkles size={17} />
                      )}
                      {selectedImageIsGenerating
                        ? '正在生成图片...'
                        : selectedNode.resultUrl
                          ? '重新生成图片'
                          : '生成图片'}
                    </button>

                    {selectedImageResults.length > 0 && (
                      <div className="grid grid-cols-2 gap-2">
                        {selectedImageResults.map((result, index) => (
                          <div
                            key={result.id}
                            className="group relative overflow-hidden rounded-xl border border-slate-200 bg-slate-100"
                          >
                            <img
                              src={result.url}
                              alt={`${selectedNode.title} 结果 ${index + 1}`}
                              className="aspect-square w-full object-cover"
                            />
                            <ImageHoverActions
                              compact
                              label={`${selectedNode.title}结果${index + 1}`}
                              onPreview={() =>
                                openImagePreview(
                                  result.url,
                                  `${selectedNode.title}-${index + 1}`,
                                )
                              }
                              onDownload={() =>
                                void downloadImage(
                                  result.url,
                                  getCanvasImageDownloadName(
                                    `${selectedNode.title}-${index + 1}`,
                                  ),
                                )
                              }
                            />
                            <button
                              type="button"
                              onClick={() =>
                                removeNodeResult(selectedNode.id, result.id)
                              }
                              aria-label={`移除图片结果 ${index + 1}`}
                              className="absolute right-1.5 top-1.5 z-30 flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg bg-slate-950/70 text-white opacity-0 backdrop-blur transition-opacity duration-200 hover:bg-red-600 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-white group-hover:opacity-100"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() =>
                        addConnectedGenerationNode(selectedNode.id, 'video')
                      }
                      disabled={
                        !selectedNode.resultUrl || selectedImageIsGenerating
                      }
                      className="flex h-10 w-full cursor-pointer items-center justify-center gap-2 rounded-xl border border-fuchsia-200 bg-fuchsia-50 text-xs font-semibold text-fuchsia-700 transition-colors duration-200 hover:bg-fuchsia-100 focus:outline-none focus:ring-2 focus:ring-fuchsia-400 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
                    >
                      <Video size={15} /> 用生成图片制作视频
                    </button>
                  </>
                )}

                {selectedNode.kind === 'video' && (
                  <>
                    {!selectedVideoHasRequiredReferences && (
                      <div
                        role="status"
                        className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-800"
                      >
                        {selectedVideoGenerationMode === 'reference_image'
                          ? '参考图片生成需要至少连接一张图片。'
                          : selectedVideoGenerationMode === 'reference_video'
                            ? '参考视频生成需要至少连接一条视频。'
                            : selectedVideoGenerationMode === 'reference_assets'
                              ? '全能参考需要至少连接一张图片、一条视频、一段音频、一份文档或一个网页。'
                              : selectedVideoGenerationMode ===
                                  'first_last_frame'
                                ? '首尾帧生成需要按顺序连接两张图片。'
                                : '首帧生成需要连接一张输入图片。'}
                      </div>
                    )}
                    {selectedVideoPrompt &&
                      selectedVideoPrompt !== selectedNode.prompt.trim() && (
                        <div className="rounded-xl border border-cyan-100 bg-cyan-50 px-3 py-2.5 text-xs leading-5 text-cyan-800">
                          已合并上游文本提示词；生成时会与本节点视频描述一起提交。
                        </div>
                      )}

                    <div>
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          模型
                        </span>
                        <select
                          value={selectedVideoModel}
                          onChange={(event) => {
                            const nextModel = event.target.value;
                            const nextConfig =
                              mediaModelCatalog[nextModel] || {};
                            const nextResolutions: string[] =
                              nextConfig.supported_resolutions || ['720p'];
                            const nextRatios: string[] =
                              nextConfig.supported_aspect_ratios ||
                              VIDEO_ASPECT_RATIOS;
                            const nextDurationRange: number[] =
                              nextConfig.duration_range_seconds || [2, 15];
                            const nextDurationOptions: number[] =
                              nextConfig.duration_options_seconds || [];
                            clearNodeError(selectedNode.id);
                            updateNode(selectedNode.id, {
                              model: nextModel,
                              videoGenerationMode: resolveVideoGenerationMode(
                                nextConfig,
                                selectedVideoGenerationMode,
                                'first_frame',
                              ),
                              resolution: nextResolutions.includes(
                                selectedNode.resolution || '',
                              )
                                ? selectedNode.resolution
                                : nextResolutions[0],
                              aspectRatio: nextRatios.includes(
                                selectedNode.aspectRatio || '',
                              )
                                ? selectedNode.aspectRatio
                                : nextRatios[0],
                              duration:
                                nextDurationOptions.length > 0 &&
                                !nextDurationOptions.includes(
                                  Number(selectedNode.duration),
                                )
                                  ? Number(
                                      nextConfig.default_duration_seconds ||
                                        nextDurationOptions[0],
                                    )
                                  : clamp(
                                      Number(selectedNode.duration) ||
                                        Number(
                                          nextConfig.default_duration_seconds ||
                                            nextDurationRange[0] ||
                                            5,
                                        ),
                                      Number(nextDurationRange[0] || 2),
                                      Number(nextDurationRange[1] || 15),
                                    ),
                              extensionCount:
                                nextConfig.supports_extension === false
                                  ? 0
                                  : selectedNode.extensionCount || 0,
                              status: 'draft',
                            });
                          }}
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100"
                        >
                          {availableVideoModels.map((model) => (
                            <option key={model} value={model}>
                              {mediaModelCatalog[model]?.label || model}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <label className="block">
                      <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                        生成模式
                      </span>
                      <select
                        value={selectedVideoGenerationMode}
                        onChange={(event) =>
                          updateNode(selectedNode.id, {
                            videoGenerationMode: event.target
                              .value as VideoGenerationMode,
                            status: 'draft',
                          })
                        }
                        aria-label="视频生成模式"
                        className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100"
                      >
                        {VIDEO_GENERATION_MODE_OPTIONS.map((option) => (
                          <option
                            key={option.value}
                            value={option.value}
                            disabled={
                              !selectedVideoSupportedModes.includes(
                                option.value,
                              )
                            }
                          >
                            {option.label}
                            {selectedVideoSupportedModes.includes(option.value)
                              ? ''
                              : '（不支持）'}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="grid grid-cols-2 gap-3">
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          比例
                        </span>
                        <select
                          value={
                            selectedVideoAspectRatios.includes(
                              selectedNode.aspectRatio || '',
                            )
                              ? selectedNode.aspectRatio
                              : selectedVideoAspectRatios[0]
                          }
                          onChange={(event) =>
                            updateNode(selectedNode.id, {
                              aspectRatio: event.target.value,
                              status: 'draft',
                            })
                          }
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100"
                        >
                          {selectedVideoAspectRatios.map((ratio) => (
                            <option key={ratio} value={ratio}>
                              {ratio}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          分辨率
                        </span>
                        <select
                          value={
                            selectedVideoResolutions.includes(
                              selectedNode.resolution || '',
                            )
                              ? selectedNode.resolution
                              : selectedVideoResolutions[0]
                          }
                          onChange={(event) =>
                            updateNode(selectedNode.id, {
                              resolution: event.target.value,
                              status: 'draft',
                            })
                          }
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100"
                        >
                          {selectedVideoResolutions.map((resolution) => (
                            <option key={resolution} value={resolution}>
                              {resolution === '4k' ? '4K' : resolution}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <label className="block">
                      <span className="mb-1.5 flex items-center justify-between text-xs font-semibold text-slate-600">
                        <span>
                          {selectedVideoUsesTargetDuration
                            ? '时长（秒）'
                            : '延长次数'}
                        </span>
                        <span className="font-medium text-slate-400">
                          总时长约 {selectedVideoEffectiveDuration} 秒
                        </span>
                      </span>
                      <DeferredNumberInput
                        min={
                          selectedVideoUsesTargetDuration
                            ? Number(selectedVideoDurationRange[0] || 2)
                            : 0
                        }
                        max={
                          selectedVideoUsesTargetDuration
                            ? Number(selectedVideoDurationRange[1] || 15)
                            : selectedVideoIsLite
                              ? 0
                              : maxVideoExtensionCount
                        }
                        step={
                          selectedVideoModelConfig.duration_options_seconds
                            ?.length > 1
                            ? Math.max(
                                1,
                                Number(
                                  selectedVideoModelConfig
                                    .duration_options_seconds[1] ?? 1,
                                ) -
                                  Number(
                                    selectedVideoModelConfig
                                      .duration_options_seconds[0] ?? 0,
                                  ),
                              )
                            : 1
                        }
                        value={
                          selectedVideoUsesTargetDuration
                            ? selectedVideoDuration
                            : selectedVideoExtensionCount
                        }
                        disabled={
                          !selectedVideoUsesTargetDuration &&
                          selectedVideoIsLite
                        }
                        ariaLabel={
                          selectedVideoUsesTargetDuration
                            ? '视频时长（秒）'
                            : '视频延长次数'
                        }
                        onCommit={(value) =>
                          selectedVideoUsesTargetDuration
                            ? updateNode(selectedNode.id, {
                                duration: value,
                                status: 'draft',
                              })
                            : updateNode(selectedNode.id, {
                                extensionCount: value,
                                status: 'draft',
                              })
                        }
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-fuchsia-400 focus:ring-2 focus:ring-fuchsia-100 disabled:bg-slate-100 disabled:text-slate-400"
                      />
                    </label>

                    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-600">
                      {selectedVideoModelConfig.description || '视频生成模型'}
                      <div className="mt-1 font-medium text-slate-700">
                        已连接 {selectedVideoImageReferenceCount} 张参考图 ·{' '}
                        {selectedVideoReferenceVideoCount} 条参考视频 · 单次生成
                      </div>
                    </div>

                    {nodeProgress[selectedNode.id] && (
                      <div
                        role="status"
                        className="flex items-start gap-2 rounded-xl border border-fuchsia-100 bg-fuchsia-50 px-3 py-2.5 text-xs leading-5 text-fuchsia-700"
                      >
                        <Loader2
                          size={14}
                          className="mt-0.5 shrink-0 animate-spin"
                        />{' '}
                        {nodeProgress[selectedNode.id]}
                      </div>
                    )}

                    {nodeErrors[selectedNode.id] && (
                      <div
                        role="alert"
                        className="whitespace-pre-line break-words rounded-xl border border-red-100 bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700"
                      >
                        {nodeErrors[selectedNode.id]}
                      </div>
                    )}

                    <div className="flex items-center gap-3">
                      <VideoCostEstimate
                        modelLabel={
                          selectedVideoModelConfig.label || selectedVideoModel
                        }
                        resolution={selectedVideoResolution}
                        duration={selectedVideoEffectiveDuration}
                        count={selectedVideoCount}
                        pricePerSecond={selectedVideoPricePerSecond}
                        priceCurrency={selectedVideoPriceCurrency}
                        cnyToUsdRate={cnyToUsdRate}
                        theme={theme}
                      />
                      <button
                        type="button"
                        onClick={() => void generateVideoNode(selectedNode.id)}
                        disabled={
                          hasSaveConflict ||
                          !selectedVideoPrompt ||
                          !selectedVideoHasRequiredReferences ||
                          selectedVideoIsGenerating
                        }
                        className="flex h-11 min-w-0 flex-1 cursor-pointer items-center justify-center gap-2 rounded-xl bg-fuchsia-600 px-4 text-sm font-semibold text-white transition-colors duration-200 hover:bg-fuchsia-700 focus:outline-none focus:ring-2 focus:ring-fuchsia-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                      >
                        {selectedVideoIsGenerating ? (
                          <Loader2 size={17} className="animate-spin" />
                        ) : (
                          <Video size={17} />
                        )}
                        {selectedVideoIsGenerating
                          ? '正在生成视频...'
                          : selectedNode.resultUrl
                            ? '重新生成视频'
                            : '生成视频'}
                      </button>
                    </div>

                    {selectedVideoResults.length > 0 && (
                      <div className="space-y-2">
                        {selectedVideoResults.map((result, index) => (
                          <VideoResultCard
                            key={result.id}
                            url={result.url}
                            label={`${selectedNode.title} 结果 ${index + 1}`}
                            onPreview={() =>
                              openVideoPreview(
                                result.url,
                                `${selectedNode.title}-${index + 1}`,
                              )
                            }
                            onDownload={() =>
                              void downloadVideo(
                                result.url,
                                `${selectedNode.title}-${index + 1}`,
                              )
                            }
                            onRemove={() =>
                              removeNodeResult(selectedNode.id, result.id)
                            }
                          />
                        ))}
                      </div>
                    )}
                  </>
                )}

                {selectedNode.kind === 'music' && (
                  <>
                    {selectedMusicPrompt &&
                      selectedMusicPrompt !== selectedNode.prompt.trim() && (
                        <div className="rounded-xl border border-cyan-100 bg-cyan-50 px-3 py-2.5 text-xs leading-5 text-cyan-800">
                          已合并上游文本提示词；生成时会与本节点音乐描述一起提交。
                        </div>
                      )}

                    <div>
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          模型
                        </span>
                        <select
                          value={selectedMusicModel}
                          onChange={(event) => {
                            clearNodeError(selectedNode.id);
                            updateNode(selectedNode.id, {
                              model: event.target.value,
                              status: 'draft',
                            });
                          }}
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-pink-400 focus:ring-2 focus:ring-pink-100"
                        >
                          {availableMusicModels.map((model) => (
                            <option key={model} value={model}>
                              {mediaModelCatalog[model]?.label || model}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="rounded-xl border border-pink-100 bg-pink-50 px-3 py-2.5 text-xs leading-5 text-slate-600">
                      {selectedMusicModelConfig.description ||
                        '根据文本描述生成原创音乐'}
                      <div className="mt-1 font-medium text-slate-700">
                        已连接 {selectedMusicReferenceCount} 张灵感图片 ·
                        单次生成
                      </div>
                      <div className="mt-1 text-slate-500">
                        Clip 固定约 30 秒；Pro
                        可在描述中指定歌曲时长与段落结构。
                      </div>
                    </div>

                    {nodeProgress[selectedNode.id] && (
                      <div
                        role="status"
                        className="flex items-start gap-2 rounded-xl border border-pink-100 bg-pink-50 px-3 py-2.5 text-xs leading-5 text-pink-700"
                      >
                        <Loader2
                          size={14}
                          className="mt-0.5 shrink-0 animate-spin"
                        />{' '}
                        {nodeProgress[selectedNode.id]}
                      </div>
                    )}
                    {nodeErrors[selectedNode.id] && (
                      <div
                        role="alert"
                        className="whitespace-pre-line break-words rounded-xl border border-red-100 bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700"
                      >
                        {nodeErrors[selectedNode.id]}
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() => void generateMusicNode(selectedNode.id)}
                      disabled={
                        !selectedMusicPrompt || selectedMusicIsGenerating
                      }
                      className="flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-pink-600 px-4 text-sm font-semibold text-white transition-colors duration-200 hover:bg-pink-700 focus:outline-none focus:ring-2 focus:ring-pink-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                    >
                      {selectedMusicIsGenerating ? (
                        <Loader2 size={17} className="animate-spin" />
                      ) : (
                        <Music2 size={17} />
                      )}
                      {selectedMusicIsGenerating
                        ? '正在生成音乐...'
                        : selectedNode.resultUrl
                          ? '重新生成音乐'
                          : '生成音乐'}
                    </button>

                    {selectedAudioResults.length > 0 && (
                      <div className="space-y-2">
                        {selectedAudioResults.map((result, index) => (
                          <div
                            key={result.id}
                            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2"
                          >
                            <audio
                              src={result.url}
                              controls
                              aria-label={`${selectedNode.title} 音乐结果 ${index + 1}`}
                              className="min-w-0 flex-1"
                            />
                            <button
                              type="button"
                              onClick={() =>
                                removeNodeResult(selectedNode.id, result.id)
                              }
                              aria-label={`移除音乐结果 ${index + 1}`}
                              className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-slate-500 transition-colors duration-200 hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-300"
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}

                {selectedNode.kind === 'tts' && (
                  <>
                    {selectedTTSPrompt &&
                      selectedTTSPrompt !== selectedNode.prompt.trim() && (
                        <div className="rounded-xl border border-cyan-100 bg-cyan-50 px-3 py-2.5 text-xs leading-5 text-cyan-800">
                          已合并上游文本提示词；生成时会与本节点配音文案一起提交。
                        </div>
                      )}

                    <div>
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          模型
                        </span>
                        <select
                          value={selectedTTSModel}
                          onChange={(event) => {
                            clearNodeError(selectedNode.id);
                            updateNode(selectedNode.id, {
                              model: event.target.value,
                              status: 'draft',
                            });
                          }}
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none transition-colors focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                        >
                          {availableTTSModels.map((model) => (
                            <option key={model} value={model}>
                              {mediaModelCatalog[model]?.label || model}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          声音
                        </span>
                        <select
                          value={
                            TTS_VOICE_OPTIONS.includes(
                              selectedNode.voiceName || '',
                            )
                              ? selectedNode.voiceName
                              : defaultTTSVoice
                          }
                          onChange={(event) =>
                            updateNode(selectedNode.id, {
                              voiceName: event.target.value,
                              status: 'draft',
                            })
                          }
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                        >
                          {TTS_VOICE_OPTIONS.map((voice) => (
                            <option key={voice} value={voice}>
                              {voice}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="block">
                        <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                          语速
                        </span>
                        <select
                          value={selectedNode.speechRate || 'normal'}
                          onChange={(event) =>
                            updateNode(selectedNode.id, {
                              speechRate: event.target.value as
                                | 'slow'
                                | 'normal'
                                | 'fast',
                              status: 'draft',
                            })
                          }
                          className="w-full cursor-pointer rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                        >
                          <option value="slow">慢速</option>
                          <option value="normal">正常</option>
                          <option value="fast">快速</option>
                        </select>
                      </label>
                    </div>

                    <label className="block">
                      <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                        音色风格（可选）
                      </span>
                      <input
                        value={selectedNode.voiceStyle || ''}
                        onChange={(event) =>
                          updateNode(selectedNode.id, {
                            voiceStyle: event.target.value,
                            status: 'draft',
                          })
                        }
                        placeholder="例如：温暖、专业、有亲和力的广告旁白"
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                      />
                    </label>

                    <div className="rounded-xl border border-sky-100 bg-sky-50 px-3 py-2.5 text-xs leading-5 text-slate-600">
                      {selectedTTSModelConfig.description ||
                        '将文本转换为自然语音'}
                      <div className="mt-1 font-medium text-slate-700">
                        单人配音 · WAV · 单次生成
                      </div>
                    </div>

                    {nodeProgress[selectedNode.id] && (
                      <div
                        role="status"
                        className="flex items-start gap-2 rounded-xl border border-sky-100 bg-sky-50 px-3 py-2.5 text-xs leading-5 text-sky-700"
                      >
                        <Loader2
                          size={14}
                          className="mt-0.5 shrink-0 animate-spin"
                        />{' '}
                        {nodeProgress[selectedNode.id]}
                      </div>
                    )}
                    {nodeErrors[selectedNode.id] && (
                      <div
                        role="alert"
                        className="whitespace-pre-line break-words rounded-xl border border-red-100 bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700"
                      >
                        {nodeErrors[selectedNode.id]}
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() => void generateTTSNode(selectedNode.id)}
                      disabled={!selectedTTSPrompt || selectedTTSIsGenerating}
                      className="flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-sky-600 px-4 text-sm font-semibold text-white transition-colors duration-200 hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                    >
                      {selectedTTSIsGenerating ? (
                        <Loader2 size={17} className="animate-spin" />
                      ) : (
                        <Mic2 size={17} />
                      )}
                      {selectedTTSIsGenerating
                        ? '正在生成配音...'
                        : selectedNode.resultUrl
                          ? '重新生成配音'
                          : '生成配音'}
                    </button>

                    {selectedAudioResults.length > 0 && (
                      <div className="space-y-2">
                        {selectedAudioResults.map((result, index) => (
                          <div
                            key={result.id}
                            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2"
                          >
                            <audio
                              src={result.url}
                              controls
                              aria-label={`${selectedNode.title} 配音结果 ${index + 1}`}
                              className="min-w-0 flex-1"
                            />
                            <button
                              type="button"
                              onClick={() =>
                                removeNodeResult(selectedNode.id, result.id)
                              }
                              aria-label={`移除配音结果 ${index + 1}`}
                              className="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-slate-500 transition-colors duration-200 hover:bg-red-50 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-300"
                            >
                              <Trash2 size={15} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}

                <div className="rounded-2xl border border-violet-100 bg-violet-50/70 p-4 text-xs leading-5 text-violet-800">
                  <div className="mb-1 flex items-center gap-2 font-semibold">
                    <Sparkles size={14} /> 节点运行说明
                  </div>
                  {selectedNode.kind === 'image'
                    ? '连接云素材图片或文生图结果，再配置描述、模型、比例和画质，即可根据图片再次生成。'
                    : selectedNode.kind === 'asset'
                      ? '从本地或云素材库导入图片、视频、音频、文档，或粘贴公开网页链接；素材可连接到万相 3.0 全能参考。'
                      : selectedNode.kind === 'video'
                        ? '连接图片、视频、音频、文档或网页参考，再配置视频描述、模型和时长。万相 3.0 全能参考支持混合素材。'
                        : selectedNode.kind === 'video_analysis'
                          ? '连接一条已导入或已生成的视频，使用 Qwen3.8 Omni Flash 分析主体、镜头、音频和可复用提示词；分析结果可继续连接到图片或视频生成节点。'
                          : selectedNode.kind === 'music'
                            ? '填写音乐描述或连接文本节点，可选连接图片作为灵感参考，再配置模型生成音乐。'
                            : selectedNode.kind === 'tts'
                              ? '填写配音文案或连接文本节点，再配置模型、声音、语速和音色风格生成配音。'
                              : selectedNode.kind === 'text'
                                ? selectedTextMode === 'video'
                                  ? '文本提示词使用主页同款文生视频模型、比例、分辨率和时长参数直接生成视频。'
                                  : '文本提示词使用主页同款模型、比例和画质参数直接生成图片；结果可继续连接到图片或视频生成节点。'
                                : '节点、连接和参数会保存在当前浏览器中，生成结果可继续连接到下游节点。'}
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
                <MousePointer2 size={24} />
              </div>
              <h2 className="mt-4 text-sm font-semibold text-slate-800">
                选择一个节点
              </h2>
              <p className="mt-1 max-w-48 text-xs leading-5 text-slate-500">
                点击画布中的节点，在这里编辑名称、提示词和生成参数。
              </p>
            </div>
          )}
        </aside>
      </main>

      {historyPageOpen && (
        <GenerationHistoryPage
          onBack={() => setHistoryPageOpen(false)}
          onRestore={restoreHistoryRecord}
          onUseAsset={useHistoryAsset}
        />
      )}

      {cloudAssetNodeId && (
        <div
          className="canvas-cloud-library-overlay fixed inset-0 z-[80] flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="canvas-cloud-library-title"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setCloudAssetNodeId(null);
          }}
        >
          <div className="w-full max-w-5xl overflow-hidden rounded-[24px] border border-white/80 bg-white p-4 shadow-2xl sm:p-5">
            <div className="mb-4 flex items-start justify-between gap-4 px-1">
              <div>
                <div className="flex items-center gap-2 text-violet-700">
                  <Cloud size={18} />
                  <h2
                    id="canvas-cloud-library-title"
                    className="text-base font-semibold text-slate-900"
                  >
                    从云素材库导入
                  </h2>
                </div>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  选择一张图片或一个视频，导入后可直接连接到下游生成节点。
                </p>
              </div>
              <button
                type="button"
                onClick={() => setCloudAssetNodeId(null)}
                aria-label="关闭云素材库"
                className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-xl text-slate-500 transition-colors duration-200 hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-400"
              >
                <X size={18} />
              </button>
            </div>
            <MinioPanel
              onImportAsset={(asset) => {
                void applyImportedAsset(cloudAssetNodeId, asset, 'cloud').then(
                  (ok) => {
                    if (ok) setCloudAssetNodeId(null);
                  },
                );
              }}
            />
          </div>
        </div>
      )}

      {previewMedia &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            id="canvas-media-preview-overlay"
            className="canvas-media-preview-overlay fixed inset-0 z-[9999] flex items-center justify-center p-4"
            role="dialog"
            aria-modal="true"
            aria-label={`预览 ${previewMedia.name}`}
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setPreviewMedia(null);
            }}
          >
            <div
              className="canvas-media-preview-panel flex max-h-[calc(100vh-32px)] flex-col overflow-hidden rounded-[24px] border border-white/15 bg-slate-950/95 shadow-2xl"
              style={{ width: 'min(1184px, calc(100vw - 32px))' }}
            >
              <div className="canvas-media-preview-header flex items-center justify-between gap-4 border-b border-white/10 bg-slate-950/95 px-4 py-3 sm:px-5">
                <div className="min-w-0">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-violet-300">
                    {previewMedia.type === 'video'
                      ? 'Video Preview'
                      : 'Image Preview'}
                  </div>
                  <div className="mt-0.5 truncate text-sm font-semibold text-white">
                    {previewMedia.name}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      previewMedia.type === 'video'
                        ? void downloadVideo(
                            previewMedia.url,
                            previewMedia.name,
                          )
                        : void downloadImage(
                            previewMedia.url,
                            getCanvasImageDownloadName(previewMedia.name),
                          )
                    }
                    className="canvas-media-preview-action flex h-9 cursor-pointer items-center gap-2 rounded-xl border px-3 text-xs font-semibold transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-white"
                  >
                    <Download size={15} />{' '}
                    <span className="hidden sm:inline">下载</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setPreviewMedia(null)}
                    aria-label={`关闭${previewMedia.type === 'video' ? '视频' : '图片'}预览`}
                    title="关闭"
                    className="canvas-media-preview-action flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl border transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-white"
                  >
                    <X size={17} />
                  </button>
                </div>
              </div>
              <div
                className={`flex min-h-0 w-full shrink-0 items-center justify-center overflow-hidden p-4 sm:p-6 ${
                  previewMedia.transparent
                    ? TRANSPARENT_MEDIA_CHECKERBOARD_CLASS
                    : 'bg-slate-950/90'
                }`}
                style={{ height: 'min(784px, calc(100vh - 96px))' }}
              >
                {previewMedia.type === 'video' ? (
                  <video
                    src={previewMedia.url}
                    aria-label={previewMedia.name}
                    controls
                    autoPlay={!prefersReducedMotion}
                    playsInline
                    preload="auto"
                    className="h-full w-full rounded-xl bg-black object-contain shadow-2xl"
                  />
                ) : (
                  <img
                    src={previewMedia.url}
                    alt={previewMedia.name}
                    className="h-full w-full rounded-xl object-contain"
                  />
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}

      {pendingSourceId &&
        connectionRejectTargetId &&
        connectionCursor &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            role="status"
            className="pointer-events-none fixed z-[220] rounded-lg bg-slate-900 px-2.5 py-1 text-[11px] font-medium text-white shadow-[0_8px_24px_rgba(15,23,42,0.28)]"
            style={{
              left: connectionCursor.x,
              top: connectionCursor.y,
              transform: 'translate(-50%, calc(-100% - 12px))',
            }}
          >
            无法连接
          </div>,
          document.body,
        )}

      {toast && (
        <div
          role="status"
          className="fixed bottom-6 right-6 z-50 flex max-w-sm items-center gap-2 rounded-2xl border border-slate-200 bg-slate-950 px-4 py-3 text-sm font-medium text-white shadow-2xl"
        >
          <CheckCircle2 size={17} className="shrink-0 text-emerald-400" />
          {toast}
        </div>
      )}

      {hasSaveConflict && isSaveConflictNoticeOpen && (
        <div
          role="alert"
          aria-live="assertive"
          className="fixed right-6 top-6 z-[250] w-[min(360px,calc(100vw-3rem))] rounded-2xl border border-red-200 bg-white p-4 text-slate-900 shadow-[0_18px_50px_rgba(15,23,42,0.18)]"
        >
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600">
              <AlertTriangle size={17} aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">保存失败</p>
              <p className="mt-1 text-sm leading-5 text-slate-600">
                当前页面不是最新版本，请刷新页面后重试。
              </p>
              <p className="mt-2 text-xs leading-5 text-slate-500">
                覆盖保存会用当前页面内容替换服务器画布，其他页面尚未合并的修改可能丢失。
              </p>
              <button
                type="button"
                disabled={isForceSaving}
                onClick={() => void forceSaveDraft()}
                className="mt-3 inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-red-600 px-3.5 text-sm font-semibold text-white transition-colors hover:bg-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isForceSaving && (
                  <Loader2
                    size={15}
                    className="animate-spin"
                    aria-hidden="true"
                  />
                )}
                {isForceSaving ? '正在覆盖保存' : '覆盖保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CanvasCreationPage;
