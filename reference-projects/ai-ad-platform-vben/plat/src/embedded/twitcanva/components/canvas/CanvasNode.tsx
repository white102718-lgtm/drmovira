/** @jsxImportSource react */
/**
 * CanvasNode.tsx
 *
 * Main canvas node component.
 * Orchestrates NodeContent, NodeControls, and NodeConnectors sub-components.
 */

import React from 'react';
import { type NodeData, NodeStatus, NodeType } from '../../types';
import { NodeConnectors } from './NodeConnectors';
import { NodeContent } from './NodeContent';
import { NodeControls } from './NodeControls';
import { ChangeAnglePanel } from './ChangeAnglePanel';
import { isBusinessContextNode } from '../../businessContext';

const nodeTypeLabels: Record<NodeType, string> = {
  [NodeType.PROJECT]: '项目',
  [NodeType.PRODUCT]: '产品',
  [NodeType.KPI]: '指标',
  [NodeType.REQUIREMENT]: '素材需求',
  [NodeType.BRAND_GUIDELINE]: '品牌规范',
  [NodeType.REFERENCE]: '参考素材',
  [NodeType.TEXT]: '文本',
  [NodeType.IMAGE]: '图片',
  [NodeType.VIDEO]: '视频',
  [NodeType.AUDIO]: '音频',
  [NodeType.IMAGE_EDITOR]: '图片编辑',
  [NodeType.VIDEO_EDITOR]: '视频编辑',
  [NodeType.STORYBOARD]: '分镜管理',
  [NodeType.CAMERA_ANGLE]: '镜头角度',
  [NodeType.DIRECTOR_DESK_3D]: '3D 导演台',
  [NodeType.LOCAL_IMAGE_MODEL]: '本地图片模型',
  [NodeType.LOCAL_VIDEO_MODEL]: '本地视频模型',
};

const getNodeTitle = (data: NodeData) =>
  data.title || nodeTypeLabels[data.type] || data.type;

interface CanvasNodeProps {
  data: NodeData;
  inputUrl?: string;
  connectedImageNodes?: { id: string; url: string; type?: NodeType }[]; // For frame-to-frame video mode and motion control
  onUpdate: (id: string, updates: Partial<NodeData>) => void;
  onGenerate: (id: string) => void;
  onAddNext: (id: string, type: 'left' | 'right') => void;
  selected: boolean;
  showControls?: boolean; // Only show controls when single node is selected (not in group selection)
  onSelect: (id: string) => void;
  onNodePointerDown: (e: React.PointerEvent, id: string) => void;
  onContextMenu: (e: React.MouseEvent, id: string) => void;
  onConnectorDown: (
    e: React.PointerEvent,
    id: string,
    side: 'left' | 'right',
  ) => void;
  isHoveredForConnection?: boolean;
  onOpenEditor?: (nodeId: string) => void;
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
  onChangeAngleGenerate?: (nodeId: string) => void;
  onOpenDirectorDesk?: (nodeId: string) => void;
  zoom: number;
  // Mouse event callbacks for chat panel drag functionality
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  // Theme
  canvasTheme?: 'dark' | 'light';
  // Social sharing
  onPostToX?: (
    nodeId: string,
    mediaUrl: string,
    mediaType: 'image' | 'video',
  ) => void;
  onPostToTikTok?: (nodeId: string, mediaUrl: string) => void;
}

export const CanvasNode: React.FC<CanvasNodeProps> = ({
  data,
  inputUrl,
  connectedImageNodes,
  onUpdate,
  onGenerate,
  onAddNext,
  selected,
  showControls = true, // Default to true for backward compatibility
  onSelect,
  onNodePointerDown,
  onContextMenu,
  onConnectorDown,
  isHoveredForConnection,
  onOpenEditor,
  onUpload,
  onExpand,
  onDragStart,
  onDragEnd,
  onWriteContent,
  onTextToVideo,
  onTextToImage,
  onImageToImage,
  onImageToVideo,
  onChangeAngleGenerate,
  onOpenDirectorDesk,
  zoom,
  onMouseEnter,
  onMouseLeave,
  canvasTheme = 'dark',
  onPostToX,
  onPostToTikTok,
}) => {
  // ============================================================================
  // STATE
  // ============================================================================

  const [isEditingTitle, setIsEditingTitle] = React.useState(false);
  const [editedTitle, setEditedTitle] = React.useState(getNodeTitle(data));
  const titleInputRef = React.useRef<HTMLInputElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const isIdle =
    data.status === NodeStatus.IDLE || data.status === NodeStatus.ERROR;
  const isLoading = data.status === NodeStatus.LOADING;
  const isSuccess = data.status === NodeStatus.SUCCESS;

  // Theme helper
  const isDark = canvasTheme === 'dark';

  // Inverse scaling for toolbar to keep it readable when zooming out
  // Same logic as NodeControls prompt bar
  const minEffectiveScale = 0.8;
  const effectiveScale = Math.max(zoom, minEffectiveScale);
  const localScale = effectiveScale / zoom;

  // ============================================================================
  // EFFECTS
  // ============================================================================

  // Focus input when entering edit mode
  React.useEffect(() => {
    if (isEditingTitle && titleInputRef.current) {
      titleInputRef.current.focus();
      titleInputRef.current.select();
    }
  }, [isEditingTitle]);

  // Update local state when data.title changes
  React.useEffect(() => {
    setEditedTitle(getNodeTitle(data));
  }, [data.title, data.type]);

  // Auto-detect aspect ratio for legacy images/videos that don't have resultAspectRatio
  React.useEffect(() => {
    // Only detect if we have a result but no stored aspect ratio
    if (!isSuccess || !data.resultUrl || data.resultAspectRatio) return;

    if (data.type === NodeType.VIDEO) {
      // Detect video dimensions
      const video = document.createElement('video');
      video.onloadedmetadata = () => {
        if (video.videoWidth && video.videoHeight) {
          onUpdate(data.id, {
            resultAspectRatio: `${video.videoWidth}/${video.videoHeight}`,
          });
        }
      };
      video.src = data.resultUrl;
    } else {
      // Detect image dimensions
      const img = new Image();
      img.onload = () => {
        if (img.naturalWidth && img.naturalHeight) {
          onUpdate(data.id, {
            resultAspectRatio: `${img.naturalWidth}/${img.naturalHeight}`,
          });
        }
      };
      img.src = data.resultUrl;
    }
  }, [
    isSuccess,
    data.resultUrl,
    data.resultAspectRatio,
    data.type,
    data.id,
    onUpdate,
  ]);

  // ============================================================================
  // HELPERS
  // ============================================================================

  const getAspectRatioStyle = () => {
    // When there's a successful result, ALWAYS use the result's aspect ratio (lock the node size)
    // This prevents the node from resizing when user selects a different ratio for regeneration
    if (isSuccess && data.resultUrl) {
      // Use stored result aspect ratio if available
      if (data.resultAspectRatio) {
        return { aspectRatio: data.resultAspectRatio };
      }
      // If no stored ratio, use default (shouldn't happen for new content, but handles legacy)
      if (data.type === NodeType.VIDEO) {
        return { aspectRatio: '16/9' };
      }
      // Keep current shape for images without stored ratio (legacy)
      return { aspectRatio: '1/1' };
    }

    // Video nodes without result - use default 16:9
    if (data.type === NodeType.VIDEO) {
      return { aspectRatio: '16/9' };
    }

    // Image nodes without result - use the selected aspect ratio for preview
    const ratio = data.aspectRatio || 'Auto';
    // Auto defaults to 16:9 for video-ready format
    if (ratio === 'Auto') return { aspectRatio: '16/9' };

    const [w, h] = ratio.split(':');
    return { aspectRatio: `${w}/${h}` };
  };

  const handleTitleSave = () => {
    setIsEditingTitle(false);
    const trimmed = editedTitle.trim();
    if (trimmed && trimmed !== nodeTypeLabels[data.type]) {
      onUpdate(data.id, { title: trimmed });
    } else if (!trimmed) {
      setEditedTitle(getNodeTitle(data));
    }
  };

  // ============================================================================
  // RENDER
  // ============================================================================

  // Special rendering for Image Editor node
  if (data.type === NodeType.IMAGE_EDITOR) {
    return (
      <div
        className={`group/node pointer-events-auto absolute flex touch-none items-center`}
        data-node-id={data.id}
        data-node-type={data.type}
        style={{
          transform: `translate(${data.x}px, ${data.y}px)`,
          transition: 'box-shadow 0.2s',
          zIndex: selected ? 50 : 10,
        }}
        onPointerDown={(e) => onNodePointerDown(e, data.id)}
        onContextMenu={(e) => onContextMenu(e, data.id)}
      >
        <NodeConnectors
          nodeId={data.id}
          onConnectorDown={onConnectorDown}
          canvasTheme={canvasTheme}
        />

        {/* Image Editor Node Card */}
        <div
          className={`relative flex flex-col rounded-2xl transition-all duration-200 ${inputUrl ? '' : isDark ? 'border border-neutral-700 bg-[#0f0f0f] shadow-2xl' : 'border border-neutral-200 bg-white shadow-lg'} ${selected ? 'ring-1 ring-blue-500/30' : ''}`}
          style={{
            width: inputUrl ? 'auto' : '340px',
            maxWidth: inputUrl ? '500px' : 'none',
          }}
          onDoubleClick={(e) => {
            e.stopPropagation();
            if (onOpenEditor) {
              onOpenEditor(data.id);
            }
          }}
        >
          {/* Header */}
          <div className="absolute -top-8 left-0 rounded px-2 py-0.5 text-sm font-medium text-neutral-600">
            Image Editor
          </div>

          {/* Content Area */}
          <div
            className={`flex flex-col items-center justify-center ${inputUrl || data.resultUrl ? 'p-0' : 'p-6'}`}
            style={{ minHeight: inputUrl || data.resultUrl ? 'auto' : '380px' }}
          >
            {inputUrl || data.resultUrl ? (
              <img
                src={data.resultUrl || inputUrl}
                alt="Content"
                className={`h-full w-full rounded-xl object-cover ${selected ? 'shadow-2xl ring-2 ring-blue-500' : ''}`}
                style={{ maxHeight: '500px' }}
                draggable={false}
              />
            ) : (
              <div className="text-center text-sm text-neutral-500">
                Double click to open editor
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Special rendering for Camera Angle node (result view)
  if (data.type === NodeType.CAMERA_ANGLE) {
    return (
      <div
        className={`group/node pointer-events-auto absolute flex touch-none items-center`}
        data-node-id={data.id}
        data-node-type={data.type}
        style={{
          transform: `translate(${data.x}px, ${data.y}px)`,
          transition: 'box-shadow 0.2s',
          zIndex: selected ? 50 : 10,
        }}
        onPointerDown={(e) => onNodePointerDown(e, data.id)}
        onContextMenu={(e) => onContextMenu(e, data.id)}
      >
        <NodeConnectors
          nodeId={data.id}
          onConnectorDown={onConnectorDown}
          canvasTheme={canvasTheme}
        />

        {/* Relative wrapper for the Card */}
        <div className="group/nodecard relative">
          {/* Unified Toolbar - Appears above the card on hover */}
          {data.resultUrl && (
            <div
              className="absolute -top-20 left-0 right-0 z-20 flex justify-center opacity-0 transition-opacity group-hover/nodecard:opacity-100"
              style={{
                transform: `scale(${localScale})`,
                transformOrigin: 'bottom center',
              }}
            >
              <div className="flex items-center gap-1 rounded-full border border-neutral-700 bg-neutral-900/95 px-2 py-1.5 shadow-xl backdrop-blur-md">
                {/* Change Angle Button - Re-enable tweaking */}
                <button
                  onClick={() =>
                    onUpdate(data.id, {
                      angleMode: !data.angleMode,
                      angleSettings: data.angleSettings || {
                        rotation: 0,
                        tilt: 0,
                        scale: 0,
                        wideAngle: false,
                      },
                    })
                  }
                  onPointerDown={(e) => e.stopPropagation()}
                  className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                    data.angleMode
                      ? 'bg-blue-500 text-white'
                      : 'text-neutral-300 hover:bg-neutral-700 hover:text-white'
                  }`}
                >
                  <svg
                    viewBox="0 0 24 24"
                    className="h-3.5 w-3.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                    <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                    <line x1="12" y1="22.08" x2="12" y2="12" />
                  </svg>
                  Change Angle
                </button>
                {/* Separator */}
                <div className="mx-1 h-4 w-px bg-neutral-600" />

                {/* Expand Button */}
                <button
                  onClick={() => onExpand?.(data.resultUrl!)}
                  onPointerDown={(e) => e.stopPropagation()}
                  className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                  title="View full size"
                >
                  <svg
                    viewBox="0 0 24 24"
                    className="h-3.5 w-3.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <polyline points="15 3 21 3 21 9" />
                    <polyline points="9 21 3 21 3 15" />
                    <line x1="21" y1="3" x2="14" y2="10" />
                    <line x1="3" y1="21" x2="10" y2="14" />
                  </svg>
                </button>
                {/* Post to X Button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onPostToX?.(data.id, data.resultUrl!, 'image');
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                  className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                  title="Post to X"
                >
                  <svg
                    viewBox="0 0 24 24"
                    className="h-3.5 w-3.5"
                    fill="currentColor"
                  >
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                  </svg>
                </button>
                {/* Download Button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (data.resultUrl) {
                      const filename = `image_${data.id}.png`;
                      const cleanUrl = data.resultUrl.split('?')[0];
                      if (data.resultUrl.startsWith('data:')) {
                        const link = document.createElement('a');
                        link.href = data.resultUrl;
                        link.download = filename;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                      } else {
                        fetch(cleanUrl, { cache: 'no-store' })
                          .then((res) => res.blob())
                          .then((blob) => {
                            const url = window.URL.createObjectURL(blob);
                            const link = document.createElement('a');
                            link.href = url;
                            link.download = filename;
                            document.body.appendChild(link);
                            link.click();
                            document.body.removeChild(link);
                            window.URL.revokeObjectURL(url);
                          })
                          .catch(() => {
                            const link = document.createElement('a');
                            link.href = cleanUrl;
                            link.download = filename;
                            link.target = '_blank';
                            document.body.appendChild(link);
                            link.click();
                            document.body.removeChild(link);
                          });
                      }
                    }
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                  className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                  title="Download"
                >
                  <svg
                    viewBox="0 0 24 24"
                    className="h-3.5 w-3.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                </button>
                {/* Drag to Chat Handle */}
                <div
                  draggable
                  onPointerDown={(e) => e.stopPropagation()}
                  onDragStart={(e) => {
                    e.dataTransfer.setData(
                      'application/json',
                      JSON.stringify({
                        nodeId: data.id,
                        url: data.resultUrl,
                        type: 'image',
                      }),
                    );
                    e.dataTransfer.effectAllowed = 'copy';
                    onDragStart?.(data.id, true);
                  }}
                  onDragEnd={() => onDragEnd?.()}
                  className="cursor-grab rounded-full bg-cyan-500/80 p-1.5 text-white hover:bg-cyan-400 active:cursor-grabbing"
                  title="Drag to chat"
                >
                  <svg
                    viewBox="0 0 24 24"
                    className="h-3.5 w-3.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <circle cx="9" cy="5" r="1" fill="currentColor" />
                    <circle cx="9" cy="12" r="1" fill="currentColor" />
                    <circle cx="9" cy="19" r="1" fill="currentColor" />
                    <circle cx="15" cy="5" r="1" fill="currentColor" />
                    <circle cx="15" cy="12" r="1" fill="currentColor" />
                    <circle cx="15" cy="19" r="1" fill="currentColor" />
                  </svg>
                </div>
              </div>
            </div>
          )}

          {/* Node Card */}
          <div
            className={`relative flex flex-col rounded-2xl transition-all duration-200 ${isDark ? 'border border-neutral-700 bg-[#0f0f0f] shadow-2xl' : 'border border-neutral-200 bg-white shadow-lg'} ${selected ? 'ring-1 ring-blue-500/30' : ''}`}
            style={{
              width: '340px',
            }}
          >
            {/* Header */}
            <div className="absolute -top-8 left-0 rounded px-2 py-0.5 text-sm font-medium text-blue-400">
              Camera Angle
            </div>

            {/* Content Area */}
            <div
              className={`flex flex-col items-center justify-center ${data.resultUrl ? 'p-0' : 'p-6'}`}
              style={{ minHeight: data.resultUrl ? 'auto' : '340px' }}
            >
              {data.resultUrl ? (
                <img
                  src={data.resultUrl}
                  alt="Content"
                  className={`h-auto w-full rounded-xl object-cover ${selected ? 'shadow-2xl ring-2 ring-blue-500' : ''}`}
                  draggable={false}
                />
              ) : (
                <div className="flex flex-col items-center gap-3 text-neutral-500">
                  <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-blue-500"></div>
                  <span className="text-sm">Generating new angle...</span>
                </div>
              )}
            </div>
          </div>

          {/* Control Panel (Only for re-adjusting angle if needed) */}
          {selected && showControls && data.angleMode && data.resultUrl && (
            <div className="absolute left-1/2 top-[calc(100%+12px)] z-[100] flex -translate-x-1/2 justify-center">
              <div
                style={{
                  transform: `scale(${localScale})`,
                  transformOrigin: 'top center',
                  transition: 'transform 0.1s ease-out',
                }}
                onPointerDown={(e) => e.stopPropagation()}
              >
                <ChangeAnglePanel
                  imageUrl={data.resultUrl}
                  settings={
                    data.angleSettings || {
                      rotation: 0,
                      tilt: 0,
                      scale: 0,
                      wideAngle: false,
                    }
                  }
                  onSettingsChange={(settings) =>
                    onUpdate(data.id, { angleSettings: settings })
                  }
                  onClose={() => onUpdate(data.id, { angleMode: false })}
                  onGenerate={
                    onChangeAngleGenerate
                      ? () => onChangeAngleGenerate(data.id)
                      : () => {}
                  }
                  isLoading={isLoading}
                  canvasTheme={canvasTheme}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Special rendering for Video Editor node
  if (data.type === NodeType.VIDEO_EDITOR) {
    // Get video URL from parent node or own resultUrl
    const videoUrl = inputUrl || data.resultUrl;

    return (
      <div
        className={`group/node pointer-events-auto absolute flex touch-none items-center`}
        data-node-id={data.id}
        data-node-type={data.type}
        style={{
          transform: `translate(${data.x}px, ${data.y}px)`,
          transition: 'box-shadow 0.2s',
          zIndex: selected ? 50 : 10,
        }}
        onPointerDown={(e) => onNodePointerDown(e, data.id)}
        onContextMenu={(e) => onContextMenu(e, data.id)}
      >
        <NodeConnectors
          nodeId={data.id}
          onConnectorDown={onConnectorDown}
          canvasTheme={canvasTheme}
        />

        {/* Video Editor Node Card */}
        <div
          className={`relative flex flex-col rounded-2xl transition-all duration-200 ${videoUrl ? '' : isDark ? 'border border-neutral-700 bg-[#0f0f0f] shadow-2xl' : 'border border-neutral-200 bg-white shadow-lg'} ${selected ? 'ring-1 ring-purple-500/30' : ''}`}
          style={{
            width: videoUrl ? 'auto' : '340px',
            maxWidth: videoUrl ? '500px' : 'none',
          }}
          onDoubleClick={(e) => {
            e.stopPropagation();
            if (onOpenEditor) {
              onOpenEditor(data.id);
            }
          }}
        >
          {/* Header */}
          <div className="absolute -top-8 left-0 rounded px-2 py-0.5 text-sm font-medium text-purple-400">
            Video Editor
          </div>

          {/* Content Area */}
          <div
            className={`flex flex-col items-center justify-center ${videoUrl ? 'p-0' : 'p-6'}`}
            style={{ minHeight: videoUrl ? 'auto' : '380px' }}
          >
            {videoUrl ? (
              <video
                src={videoUrl}
                className={`h-auto w-full rounded-xl object-cover ${selected ? 'shadow-2xl ring-2 ring-purple-500' : ''}`}
                style={{ maxHeight: '500px', aspectRatio: '16/9' }}
                muted
                playsInline
                onMouseEnter={(e) =>
                  (e.currentTarget as HTMLVideoElement).play()
                }
                onMouseLeave={(e) => {
                  const video = e.currentTarget as HTMLVideoElement;
                  video.pause();
                  video.currentTime = 0;
                }}
              />
            ) : (
              <div className="text-center text-sm text-neutral-500">
                <p>Connect a Video node</p>
                <p className="mt-1 text-xs text-neutral-600">
                  Double click to open editor
                </p>
              </div>
            )}
          </div>

          {/* Trim indicator (if trimmed) */}
          {data.trimStart !== undefined && data.trimEnd !== undefined && (
            <div className="absolute bottom-2 left-2 right-2 flex justify-between rounded-lg bg-black/70 px-2 py-1 text-xs text-purple-300">
              <span>
                Trimmed: {data.trimStart.toFixed(1)}s -{' '}
                {data.trimEnd.toFixed(1)}s
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`group/node pointer-events-auto absolute touch-none`}
      data-node-id={data.id}
      data-node-type={data.type}
      style={{
        transform: `translate(${data.x}px, ${data.y}px)`,
        transition: 'box-shadow 0.2s',
        zIndex: selected ? 50 : 10,
        transformOrigin: 'top left',
      }}
      onPointerDown={(e) => onNodePointerDown(e, data.id)}
      onContextMenu={(e) => onContextMenu(e, data.id)}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <NodeConnectors
        nodeId={data.id}
        onConnectorDown={onConnectorDown}
        canvasTheme={canvasTheme}
      />

      {/* Relative wrapper for the Image Card to allow absolute positioning of controls below it */}
      <div className="group/nodecard relative">
        {/* Unified Toolbar - Appears above the card for Image nodes on hover */}
        {data.type === NodeType.IMAGE && isSuccess && data.resultUrl && (
          <div
            className="absolute -top-12 left-0 right-0 z-20 flex justify-center opacity-0 transition-opacity group-hover/nodecard:opacity-100"
            style={{
              transform: `scale(${localScale})`,
              transformOrigin: 'bottom center',
            }}
          >
            <div className="flex items-center gap-1 rounded-full border border-neutral-700 bg-neutral-900/95 px-2 py-1.5 shadow-xl backdrop-blur-md">
              {/* Change Angle and Upload buttons - Hidden for storyboard-generated scenes */}
              {!(data.prompt && data.prompt.startsWith('Extract panel #')) && (
                <>
                  {/* Change Angle Button */}
                  <button
                    onClick={() =>
                      onUpdate(data.id, {
                        angleMode: !data.angleMode,
                        angleSettings: data.angleSettings || {
                          rotation: 0,
                          tilt: 0,
                          scale: 0,
                          wideAngle: false,
                        },
                      })
                    }
                    onPointerDown={(e) => e.stopPropagation()}
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                      data.angleMode
                        ? 'bg-blue-500 text-white'
                        : 'text-neutral-300 hover:bg-neutral-700 hover:text-white'
                    }`}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      className="h-3.5 w-3.5"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                      <line x1="12" y1="22.08" x2="12" y2="12" />
                    </svg>
                    Change Angle
                  </button>
                  {/* Separator */}
                  <div className="mx-1 h-4 w-px bg-neutral-600" />
                  {/* Upload Button */}
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    onPointerDown={(e) => e.stopPropagation()}
                    className="flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs font-medium text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                    title="Upload image"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      className="h-3.5 w-3.5"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    Upload
                  </button>
                  {/* Hidden file input for upload */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file && onUpload) {
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                          const dataUrl = ev.target?.result as string;
                          onUpload(data.id, dataUrl);
                        };
                        reader.readAsDataURL(file);
                      }
                      e.target.value = ''; // Reset for re-upload
                    }}
                  />
                </>
              )}
              {/* Expand Button */}
              <button
                onClick={() => onExpand?.(data.resultUrl!)}
                onPointerDown={(e) => e.stopPropagation()}
                className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                title="View full size"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <polyline points="15 3 21 3 21 9" />
                  <polyline points="9 21 3 21 3 15" />
                  <line x1="21" y1="3" x2="14" y2="10" />
                  <line x1="3" y1="21" x2="10" y2="14" />
                </svg>
              </button>
              {/* Post to X Button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onPostToX?.(data.id, data.resultUrl!, 'image');
                }}
                onPointerDown={(e) => e.stopPropagation()}
                className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                title="Post to X"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="currentColor"
                >
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                </svg>
              </button>
              {/* Download Button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (data.resultUrl) {
                    const filename = `image_${data.id}.png`;
                    const cleanUrl = data.resultUrl.split('?')[0];
                    if (data.resultUrl.startsWith('data:')) {
                      const link = document.createElement('a');
                      link.href = data.resultUrl;
                      link.download = filename;
                      document.body.appendChild(link);
                      link.click();
                      document.body.removeChild(link);
                    } else {
                      fetch(cleanUrl, { cache: 'no-store' })
                        .then((res) => res.blob())
                        .then((blob) => {
                          const url = window.URL.createObjectURL(blob);
                          const link = document.createElement('a');
                          link.href = url;
                          link.download = filename;
                          document.body.appendChild(link);
                          link.click();
                          document.body.removeChild(link);
                          window.URL.revokeObjectURL(url);
                        })
                        .catch(() => {
                          const link = document.createElement('a');
                          link.href = cleanUrl;
                          link.download = filename;
                          link.target = '_blank';
                          document.body.appendChild(link);
                          link.click();
                          document.body.removeChild(link);
                        });
                    }
                  }
                }}
                onPointerDown={(e) => e.stopPropagation()}
                className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                title="Download"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
              </button>
              {/* Drag to Chat Handle */}
              <div
                draggable
                onPointerDown={(e) => e.stopPropagation()}
                onDragStart={(e) => {
                  e.dataTransfer.setData(
                    'application/json',
                    JSON.stringify({
                      nodeId: data.id,
                      url: data.resultUrl,
                      type: 'image',
                    }),
                  );
                  e.dataTransfer.effectAllowed = 'copy';
                  onDragStart?.(data.id, true);
                }}
                onDragEnd={() => onDragEnd?.()}
                className="cursor-grab rounded-full bg-cyan-500/80 p-1.5 text-white hover:bg-cyan-400 active:cursor-grabbing"
                title="Drag to chat"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="9" cy="5" r="1" fill="currentColor" />
                  <circle cx="9" cy="12" r="1" fill="currentColor" />
                  <circle cx="9" cy="19" r="1" fill="currentColor" />
                  <circle cx="15" cy="5" r="1" fill="currentColor" />
                  <circle cx="15" cy="12" r="1" fill="currentColor" />
                  <circle cx="15" cy="19" r="1" fill="currentColor" />
                </svg>
              </div>
            </div>
          </div>
        )}

        {/* Video Toolbar - Appears above the card for Video nodes on hover */}
        {data.type === NodeType.VIDEO && isSuccess && data.resultUrl && (
          <div
            className="absolute -top-20 left-0 right-0 z-20 flex justify-center opacity-0 transition-opacity group-hover/nodecard:opacity-100"
            style={{
              transform: `scale(${localScale})`,
              transformOrigin: 'bottom center',
            }}
          >
            <div className="flex items-center gap-1 rounded-full border border-neutral-700 bg-neutral-900/95 px-2 py-1.5 shadow-xl backdrop-blur-md">
              {/* Expand Button */}
              <button
                onClick={() => onExpand?.(data.resultUrl!)}
                onPointerDown={(e) => e.stopPropagation()}
                className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                title="View full size"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <polyline points="15 3 21 3 21 9" />
                  <polyline points="9 21 3 21 3 15" />
                  <line x1="21" y1="3" x2="14" y2="10" />
                  <line x1="3" y1="21" x2="10" y2="14" />
                </svg>
              </button>
              {/* Post to X Button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onPostToX?.(data.id, data.resultUrl!, 'video');
                }}
                onPointerDown={(e) => e.stopPropagation()}
                className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                title="Post to X"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="currentColor"
                >
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
                </svg>
              </button>
              {/* Post to TikTok Button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onPostToTikTok?.(data.id, data.resultUrl!);
                }}
                onPointerDown={(e) => e.stopPropagation()}
                className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                title="Post to TikTok"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="currentColor"
                >
                  <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64 2.93 2.93 0 0 1 .88.13V9.4a6.84 6.84 0 0 0-1-.05A6.33 6.33 0 0 0 5 20.1a6.34 6.34 0 0 0 10.86-4.43v-7a8.16 8.16 0 0 0 4.77 1.52v-3.4a4.85 4.85 0 0 1-1-.1z" />
                </svg>
              </button>
              {/* Download Button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (data.resultUrl) {
                    const filename = `video_${data.id}.mp4`;
                    const cleanUrl = data.resultUrl.split('?')[0];
                    fetch(cleanUrl, { cache: 'no-store' })
                      .then((res) => res.blob())
                      .then((blob) => {
                        const url = window.URL.createObjectURL(blob);
                        const link = document.createElement('a');
                        link.href = url;
                        link.download = filename;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        window.URL.revokeObjectURL(url);
                      })
                      .catch(() => {
                        const link = document.createElement('a');
                        link.href = cleanUrl;
                        link.download = filename;
                        link.target = '_blank';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                      });
                  }
                }}
                onPointerDown={(e) => e.stopPropagation()}
                className="rounded-full p-1.5 text-neutral-300 transition-colors hover:bg-neutral-700 hover:text-white"
                title="Download"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
              </button>
              {/* Drag to Chat Handle */}
              <div
                draggable
                onPointerDown={(e) => e.stopPropagation()}
                onDragStart={(e) => {
                  e.dataTransfer.setData(
                    'application/json',
                    JSON.stringify({
                      nodeId: data.id,
                      url: data.resultUrl,
                      type: 'video',
                    }),
                  );
                  e.dataTransfer.effectAllowed = 'copy';
                  onDragStart?.(data.id, true);
                }}
                onDragEnd={() => onDragEnd?.()}
                className="cursor-grab rounded-full bg-cyan-500/80 p-1.5 text-white hover:bg-cyan-400 active:cursor-grabbing"
                title="Drag to chat"
              >
                <svg
                  viewBox="0 0 24 24"
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="9" cy="5" r="1" fill="currentColor" />
                  <circle cx="9" cy="12" r="1" fill="currentColor" />
                  <circle cx="9" cy="19" r="1" fill="currentColor" />
                  <circle cx="15" cy="5" r="1" fill="currentColor" />
                  <circle cx="15" cy="12" r="1" fill="currentColor" />
                  <circle cx="15" cy="19" r="1" fill="currentColor" />
                </svg>
              </div>
            </div>
          </div>
        )}

        {/* Main Node Card - Video nodes are wider to fit more controls */}
        <div
          className={`relative ${data.type === NodeType.VIDEO ? 'w-[385px]' : 'w-[365px]'} flex flex-col rounded-2xl border shadow-2xl transition-all duration-300 ${isDark ? 'bg-[#0f0f0f]' : 'bg-white'} ${selected ? 'border-blue-500/50 ring-1 ring-blue-500/30' : isDark ? 'border-neutral-800' : 'border-neutral-200'}`}
        >
          {/* Header (Editable Title) - Positioned horizontally on top-left side */}
          {isEditingTitle ? (
            <input
              ref={titleInputRef}
              type="text"
              value={editedTitle}
              onChange={(e) => setEditedTitle(e.target.value)}
              onBlur={handleTitleSave}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleTitleSave();
                } else if (e.key === 'Escape') {
                  setEditedTitle(getNodeTitle(data));
                  setIsEditingTitle(false);
                }
              }}
              onClick={(e) => e.stopPropagation()}
              onPointerDown={(e) => e.stopPropagation()}
              className="absolute top-2 whitespace-nowrap rounded border border-blue-400 bg-blue-500/20 px-2 py-0.5 text-sm font-medium text-blue-200 outline-none"
              style={{ right: 'calc(100% + 8px)', minWidth: '60px' }}
            />
          ) : (
            <div
              className={`absolute top-2 cursor-text whitespace-nowrap rounded px-2 py-0.5 text-sm font-medium transition-colors ${selected ? 'bg-blue-500/20 text-blue-200' : 'text-neutral-600'}`}
              style={{ right: 'calc(100% + 8px)' }}
              onDoubleClick={(e) => {
                e.stopPropagation();
                setIsEditingTitle(true);
              }}
              title="双击编辑名称"
            >
              {getNodeTitle(data)}
            </div>
          )}

          {/* Content Area */}
          <NodeContent
            data={data}
            inputUrl={inputUrl}
            selected={selected}
            isIdle={isIdle}
            isLoading={isLoading}
            isSuccess={isSuccess}
            getAspectRatioStyle={getAspectRatioStyle}
            onUpload={onUpload}
            onExpand={onExpand}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            onWriteContent={onWriteContent}
            onTextToVideo={onTextToVideo}
            onTextToImage={onTextToImage}
            onImageToImage={onImageToImage}
            onImageToVideo={onImageToVideo}
            onOpenDirectorDesk={onOpenDirectorDesk}
            onUpdate={onUpdate}
            onPostToX={onPostToX}
          />
        </div>

        {/* Control Panel - Only show when single node is selected (not in group selection) */}
        {/* Hide controls for storyboard-generated scenes */}
        {selected &&
          showControls &&
          data.type !== NodeType.TEXT &&
          data.type !== NodeType.DIRECTOR_DESK_3D &&
          !isBusinessContextNode(data.type) &&
          !(data.prompt && data.prompt.startsWith('Extract panel #')) && (
            <div className="absolute left-1/2 top-[calc(100%+12px)] z-[100] flex w-[600px] -translate-x-1/2 justify-center">
              <NodeControls
                data={data}
                inputUrl={inputUrl}
                isLoading={isLoading}
                isSuccess={isSuccess}
                connectedImageNodes={connectedImageNodes}
                onUpdate={onUpdate}
                onGenerate={onGenerate}
                onChangeAngleGenerate={onChangeAngleGenerate}
                onSelect={onSelect}
                zoom={zoom}
                canvasTheme={canvasTheme}
              />
            </div>
          )}
      </div>
    </div>
  );
};
