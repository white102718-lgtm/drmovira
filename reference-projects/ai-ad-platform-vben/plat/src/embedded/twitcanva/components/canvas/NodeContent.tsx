/** @jsxImportSource react */
/**
 * NodeContent.tsx
 *
 * Displays the content area of a canvas node.
 * Handles result display (image/video) and placeholder states.
 */

import React, { useRef, useState, useEffect } from 'react';
import {
  Loader2,
  Maximize2,
  ImageIcon as ImageIcon,
  Film,
  Upload,
  Pencil,
  Video,
  GripVertical,
  Download,
  Expand,
  Shrink,
  HardDrive,
  BriefcaseBusiness,
  Box,
  Target,
  ClipboardList,
  ShieldCheck,
  Paperclip,
  LockKeyhole,
  Clapperboard,
  ExternalLink,
  Camera,
} from 'lucide-react';
import { type NodeData, NodeStatus, NodeType } from '../../types';
import { isBusinessContextNode } from '../../businessContext';

interface NodeContentProps {
  data: NodeData;
  inputUrl?: string;
  selected: boolean;
  isIdle: boolean;
  isLoading: boolean;
  isSuccess: boolean;
  getAspectRatioStyle: () => { aspectRatio: string };
  onUpload?: (nodeId: string, imageDataUrl: string) => void;
  onExpand?: (imageUrl: string) => void;
  onDragStart?: (nodeId: string, hasContent: boolean) => void;
  onDragEnd?: () => void;
  // Text node callbacks
  onWriteContent?: (nodeId: string) => void;
  onTextToVideo?: (nodeId: string) => void;
  onTextToImage?: (nodeId: string) => void;
  // Image node callbacks
  onImageToImage?: (nodeId: string) => void;
  onImageToVideo?: (nodeId: string) => void;
  onOpenDirectorDesk?: (nodeId: string) => void;
  onUpdate?: (nodeId: string, updates: Partial<NodeData>) => void;
  // Social sharing
  onPostToX?: (
    nodeId: string,
    mediaUrl: string,
    mediaType: 'image' | 'video',
  ) => void;
}

export const NodeContent: React.FC<NodeContentProps> = ({
  data,
  inputUrl,
  selected,
  isIdle,
  isLoading,
  isSuccess,
  getAspectRatioStyle,
  onUpload,
  onExpand,
  onDragStart,
  onDragEnd,
  onWriteContent,
  onTextToVideo,
  onTextToImage,
  onImageToImage,
  onImageToVideo,
  onOpenDirectorDesk,
  onUpdate,
  onPostToX,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Local state for text node textarea to prevent lag
  const [localPrompt, setLocalPrompt] = useState(data.prompt || '');
  const updateTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastSentPromptRef = useRef<string | undefined>(data.prompt); // Track what we sent

  // Helper: Check if node is image-type (includes local image model)
  const isImageType =
    data.type === NodeType.IMAGE || data.type === NodeType.LOCAL_IMAGE_MODEL;
  // Helper: Check if node is video-type (includes local video model)
  const isVideoType =
    data.type === NodeType.VIDEO || data.type === NodeType.LOCAL_VIDEO_MODEL;
  // Helper: Check if node is local model
  const isLocalModel =
    data.type === NodeType.LOCAL_IMAGE_MODEL ||
    data.type === NodeType.LOCAL_VIDEO_MODEL;
  const businessIconMap: Partial<
    Record<NodeType, React.ComponentType<{ size?: number }>>
  > = {
    [NodeType.PROJECT]: BriefcaseBusiness,
    [NodeType.PRODUCT]: Box,
    [NodeType.KPI]: Target,
    [NodeType.REQUIREMENT]: ClipboardList,
    [NodeType.BRAND_GUIDELINE]: ShieldCheck,
    [NodeType.REFERENCE]: Paperclip,
  };
  const BusinessIcon = businessIconMap[data.type];

  // Sync local state ONLY when data.prompt changes externally (not from our own update)
  useEffect(() => {
    if (data.prompt !== lastSentPromptRef.current) {
      setLocalPrompt(data.prompt || '');
      lastSentPromptRef.current = data.prompt;
    }
  }, [data.prompt]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
      }
    };
  }, []);

  if (data.type === NodeType.DIRECTOR_DESK_3D) {
    const stateLabel = {
      idle: '等待打开',
      opening: '正在打开',
      ready: '已连接',
      'local-draft': '本地草稿',
      'capture-uploading': '截图上传中',
      error: '需要处理',
    }[data.directorDeskState || 'idle'];

    return (
      <div
        className={`relative min-h-[220px] overflow-hidden rounded-2xl border p-5 ${selected ? 'border-violet-400/60 ring-1 ring-violet-400/30' : 'border-violet-500/25'} bg-gradient-to-br from-violet-950 via-slate-950 to-slate-950 text-slate-100`}
      >
        <div className="absolute -right-8 -top-8 h-28 w-28 rounded-full bg-violet-500/15 blur-2xl" />
        <div className="relative flex h-full flex-col">
          <div className="flex items-start justify-between gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-violet-400/30 bg-violet-400/15 text-violet-200">
              <Clapperboard size={21} />
            </span>
            <span
              className={`rounded-full border px-2 py-1 text-[10px] ${data.directorDeskState === 'error' ? 'border-rose-400/40 bg-rose-400/10 text-rose-200' : 'border-violet-400/30 bg-violet-400/10 text-violet-200'}`}
            >
              {stateLabel}
            </span>
          </div>
          <div className="mt-4">
            <div className="text-sm font-semibold text-white">
              空间预演与候选机位
            </div>
            <div className="mt-1 text-xs leading-5 text-slate-400">
              在 3D
              场景中完成角色站位、布景和机位确认，再把截图送入图片或视频生成。
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between rounded-lg border border-white/10 bg-black/15 px-3 py-2 text-xs text-slate-300">
            <span className="inline-flex items-center gap-1.5">
              <Camera size={13} /> 已回传 {data.directorCaptureCount || 0}{' '}
              张截图
            </span>
            {data.directorStale ? (
              <span className="text-amber-300">上游已更新</span>
            ) : null}
          </div>
          {data.errorMessage ? (
            <p className="mt-2 text-xs text-rose-200">{data.errorMessage}</p>
          ) : null}
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenDirectorDesk?.(data.id);
            }}
            onPointerDown={(event) => event.stopPropagation()}
            className="mt-auto inline-flex w-full items-center justify-center gap-2 rounded-lg bg-violet-500 px-3 py-2.5 text-sm font-medium text-white transition-colors hover:bg-violet-400"
          >
            <ExternalLink size={15} /> 打开 3D 导演台
          </button>
        </div>
      </div>
    );
  }

  const handleTextChange = (value: string) => {
    setLocalPrompt(value); // Update local state immediately
    lastSentPromptRef.current = value; // Track that we're about to send this

    // Debounce parent update
    if (updateTimeoutRef.current) {
      clearTimeout(updateTimeoutRef.current);
    }
    updateTimeoutRef.current = setTimeout(() => {
      onUpdate?.(data.id, { prompt: value });
    }, 150);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !onUpload) return;

    const reader = new FileReader();
    reader.onloadend = () => {
      onUpload(data.id, reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  return (
    <div
      className={`transition-all duration-200 ${!selected ? 'overflow-hidden rounded-2xl p-0' : 'p-1'}`}
    >
      {/* Hidden File Input - Always rendered for upload functionality (image types only) */}
      {isImageType && onUpload && (
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileChange}
        />
      )}

      {/* Result View - Show when successful OR when regenerating (loading with existing content) */}
      {(isSuccess || isLoading) && data.resultUrl ? (
        <div
          className={`group/image relative w-full bg-black ${!selected ? '' : 'overflow-hidden rounded-xl'}`}
          style={getAspectRatioStyle()}
        >
          {isVideoType ? (
            <video
              src={data.resultUrl}
              controls
              loop
              className="h-full w-full object-cover"
            />
          ) : (
            <img
              src={data.resultUrl}
              alt="Generated"
              className="pointer-events-none h-full w-full object-cover"
            />
          )}

          {/* Regenerating Overlay - Shows when loading with existing content */}
          {isLoading && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm">
              <Loader2 size={40} className="animate-spin text-blue-400" />
              <span className="mt-3 text-sm font-medium text-white">
                Regenerating...
              </span>
            </div>
          )}
        </div>
      ) : isBusinessContextNode(data.type) ? (
        <div
          className={`relative min-h-[170px] w-full overflow-hidden rounded-2xl border ${selected ? 'border-blue-500/50 ring-1 ring-blue-500/20' : 'border-slate-700'} bg-slate-950 p-5 text-slate-100`}
        >
          <div className="mb-4 flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-500/15 text-blue-300">
                {BusinessIcon ? <BusinessIcon size={20} /> : null}
              </span>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-white">
                  {data.title || data.type}
                </div>
                <div className="mt-0.5 truncate text-xs text-slate-400">
                  {data.businessSource}
                </div>
              </div>
            </div>
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] text-slate-400">
              <LockKeyhole size={10} /> 只读
            </span>
          </div>
          <div className="space-y-2">
            {(data.businessFields || []).map((field) => (
              <div
                key={`${field.label}-${field.value}`}
                className="grid grid-cols-[72px_minmax(0,1fr)] gap-2 text-xs"
              >
                <span className="text-slate-500">{field.label}</span>
                <span className="truncate text-slate-200" title={field.value}>
                  {field.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : data.type === NodeType.TEXT ? (
        /* Text Node - Menu or Editing Mode */
        <div
          className={`relative w-full overflow-hidden rounded-2xl bg-[#1a1a1a] ${selected ? 'ring-1 ring-blue-500/30' : ''}`}
        >
          {data.textMode === 'editing' ? (
            /* Editing Mode - Text Area */
            <div className="p-4">
              <textarea
                value={localPrompt}
                onChange={(e) => handleTextChange(e.target.value)}
                onPointerDown={(e) => e.stopPropagation()}
                onWheel={(e) => e.stopPropagation()}
                onBlur={() => {
                  // Ensure final value is saved on blur
                  if (updateTimeoutRef.current) {
                    clearTimeout(updateTimeoutRef.current);
                  }
                  if (localPrompt !== data.prompt) {
                    onUpdate?.(data.id, { prompt: localPrompt });
                  }
                }}
                placeholder="在此输入文本内容…"
                className="w-full resize-none bg-transparent text-sm text-white outline-none placeholder:text-neutral-600"
                style={{ minHeight: data.isPromptExpanded ? '300px' : '150px' }}
                autoFocus
              />
              {/* Expand/Shrink Button */}
              <div className="mt-2 flex justify-end">
                <button
                  onClick={() =>
                    onUpdate?.(data.id, {
                      isPromptExpanded: !data.isPromptExpanded,
                    })
                  }
                  onPointerDown={(e) => e.stopPropagation()}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-neutral-500 transition-colors hover:bg-neutral-700 hover:text-white"
                  title={data.isPromptExpanded ? '收起文本框' : '展开文本框'}
                >
                  {data.isPromptExpanded ? (
                    <Shrink size={12} />
                  ) : (
                    <Expand size={12} />
                  )}
                  <span>{data.isPromptExpanded ? '收起' : '展开'}</span>
                </button>
              </div>
            </div>
          ) : (
            /* Menu Mode - Show Options */
            <div className="flex flex-col gap-4 p-5">
              {/* Header */}
              <div className="text-sm font-medium text-neutral-500">
                请选择操作
              </div>

              {/* Menu Options */}
              <div className="flex flex-col gap-1">
                <TextNodeMenuItem
                  icon={<Pencil size={16} />}
                  label="编写文本内容"
                  onClick={() => onWriteContent?.(data.id)}
                />
                <TextNodeMenuItem
                  icon={<Video size={16} />}
                  label="文生视频"
                  onClick={() => onTextToVideo?.(data.id)}
                />
                <TextNodeMenuItem
                  icon={<ImageIcon size={16} />}
                  label="文生图片"
                  onClick={() => onTextToImage?.(data.id)}
                />
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Placeholder / Empty State for Image/Video */
        <div
          className={`relative flex aspect-[4/3] w-full flex-col items-center justify-center gap-3 overflow-hidden bg-[#141414] ${isLoading ? 'animate-pulse' : ''} ${!selected ? 'rounded-2xl' : 'rounded-xl border border-dashed border-neutral-800'}`}
        >
          {/* Input Image Preview for Video Nodes */}
          {isVideoType && inputUrl && (
            <div className="absolute inset-0 z-0">
              <img
                src={inputUrl}
                alt="输入帧"
                className="h-full w-full object-cover opacity-30 blur-sm"
              />
              <div className="absolute inset-0 bg-black/40" />
              <div className="absolute left-2 top-2 flex items-center gap-1 rounded bg-black/60 px-2 py-1 text-[10px] font-medium text-white">
                <ImageIcon size={10} />
                输入帧
              </div>
            </div>
          )}

          {isLoading ? (
            <div className="relative z-10 flex flex-col items-center gap-2">
              <Loader2 size={32} className="animate-spin text-blue-400" />
              <span className="text-xs font-medium text-neutral-500">
                生成中…
              </span>
            </div>
          ) : (
            <div className="relative z-10 flex flex-col items-center gap-3">
              {/* Upload Button for Image Nodes (including local image models) */}
              {isImageType && onUpload && (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    onPointerDown={(e) => e.stopPropagation()}
                    className="flex items-center gap-2 rounded-lg bg-neutral-800/80 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-700"
                  >
                    <Upload size={16} />
                    上传
                  </button>
                </>
              )}

              <div className="text-neutral-700">
                {isVideoType ? (
                  isLocalModel ? (
                    <>
                      <Film size={40} />
                      <HardDrive
                        size={16}
                        className="absolute -bottom-1 -right-1 text-purple-400"
                      />
                    </>
                  ) : (
                    <Film size={40} />
                  )
                ) : isLocalModel ? (
                  <>
                    <ImageIcon size={40} />
                    <HardDrive
                      size={16}
                      className="absolute -bottom-1 -right-1 text-purple-400"
                    />
                  </>
                ) : (
                  <ImageIcon size={40} />
                )}
              </div>
              {selected && (
                <>
                  <div className="text-sm font-medium text-neutral-500">
                    {isVideoType && inputUrl
                      ? '已准备生成动画'
                      : isVideoType
                        ? '等待输入…'
                        : isLocalModel
                          ? '选择模型并输入提示词'
                          : '请选择操作'}
                  </div>
                  {!isVideoType && !isLocalModel && (
                    <div className="flex w-full flex-col gap-1 px-2">
                      <TextNodeMenuItem
                        icon={<ImageIcon size={16} />}
                        label="图生图"
                        onClick={() => onImageToImage?.(data.id)}
                      />
                      <TextNodeMenuItem
                        icon={<Film size={16} />}
                        label="图生视频"
                        onClick={() => onImageToVideo?.(data.id)}
                      />
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// HELPER COMPONENTS
// ============================================================================

interface TextNodeMenuItemProps {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}

/**
 * Menu item component for Text node options
 */
const TextNodeMenuItem: React.FC<TextNodeMenuItemProps> = ({
  icon,
  label,
  onClick,
}) => (
  <button
    className="flex w-full items-center gap-3 rounded-lg p-2.5 text-left text-neutral-400 transition-colors hover:bg-[#252525] hover:text-white"
    onPointerDown={(e) => e.stopPropagation()}
    onClick={onClick}
  >
    <span className="text-neutral-500">{icon}</span>
    <span className="text-sm font-medium">{label}</span>
  </button>
);
