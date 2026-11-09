/** @jsxImportSource react */
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, ChevronRight, Crop, Grid3X3, Loader2, Scan, Sparkles, WandSparkles, X } from 'lucide-react';

import { ImageGridSplitTool } from './ImageGridSplitTool';
import { ImageMattingTool } from './ImageMattingTool';
import {
  GRID_SPLIT_PRESETS,
  MAX_CUSTOM_GRID,
  type GridHdScale,
  type GridSplitCell,
  type GridSplitSize,
} from './gridSplit';

export type ImageNodeAiToolMode = 'idle' | 'crop' | 'erase' | 'grid-split' | 'matting';

interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface ImageNodeAiToolsProps {
  busy?: boolean;
  floatingHidden?: boolean;
  imageUrl: string;
  layoutNonce?: number;
  mode: ImageNodeAiToolMode;
  nodeId: string;
  selected?: boolean;
  onApplyCrop: (file: File) => Promise<void> | void;
  onApplyErase: (maskDataUrl: string) => Promise<void> | void;
  onCancel: () => void;
  onError?: (message: string) => void;
  gridSize?: GridSplitSize | null;
  onRemoveBackground: () => void;
  onStartCrop: () => void;
  onStartErase?: () => void;
  onStartMatting: () => void;
  onStartGridSplit: (size: GridSplitSize) => void;
  onGenerateSmartMatte: (hintMaskDataUrl: string) => Promise<string>;
  onApplySmartMatting: (file: File) => Promise<void> | void;
  onSplitGridCells: (cells: GridSplitCell[]) => Promise<void> | void;
  onGenerateGridHd: (cells: GridSplitCell[], scale: GridHdScale) => Promise<void> | void;
}

const MIN_CROP_RATIO = 0.08;
const DEFAULT_CROP: CropRect = { x: 0.08, y: 0.08, width: 0.84, height: 0.84 };
const CROP_HANDLES = ['nw', 'ne', 'sw', 'se'] as const;
type CropHandle = 'move' | (typeof CROP_HANDLES)[number];
const CROP_HANDLE_HIT_PX = 40;
const ERASE_BRUSH_RATIO = 0.06;
const TOOLBAR_HEIGHT = 48;
const TOOLBAR_GAP = 10;
const TITLE_OFFSET = 32;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const normalizeCrop = (rect: CropRect): CropRect => {
  const x = clamp(rect.x, 0, 1 - MIN_CROP_RATIO);
  const y = clamp(rect.y, 0, 1 - MIN_CROP_RATIO);
  return {
    x,
    y,
    width: clamp(rect.width, MIN_CROP_RATIO, 1 - x),
    height: clamp(rect.height, MIN_CROP_RATIO, 1 - y),
  };
};

const applyCropDelta = (
  start: CropRect,
  handle: CropHandle,
  deltaX: number,
  deltaY: number,
): CropRect => {
  if (handle === 'move') {
    return normalizeCrop({
      ...start,
      x: start.x + deltaX,
      y: start.y + deltaY,
    });
  }
  const next = { ...start };
  if (handle.includes('w')) {
    const x = clamp(start.x + deltaX, 0, start.x + start.width - MIN_CROP_RATIO);
    next.width = start.width + (start.x - x);
    next.x = x;
  }
  if (handle.includes('e')) {
    next.width = start.width + deltaX;
  }
  if (handle.includes('n')) {
    const y = clamp(start.y + deltaY, 0, start.y + start.height - MIN_CROP_RATIO);
    next.height = start.height + (start.y - y);
    next.y = y;
  }
  if (handle.includes('s')) {
    next.height = start.height + deltaY;
  }
  return normalizeCrop(next);
};

const hitCropHandle = (
  clientX: number,
  clientY: number,
  bounds: DOMRect,
  rect: CropRect,
): CropHandle | null => {
  if (bounds.width < 1 || bounds.height < 1) return null;
  const pxX = clientX - bounds.left;
  const pxY = clientY - bounds.top;
  const corners: Array<[(typeof CROP_HANDLES)[number], number, number]> = [
    ['nw', rect.x * bounds.width, rect.y * bounds.height],
    ['ne', (rect.x + rect.width) * bounds.width, rect.y * bounds.height],
    ['sw', rect.x * bounds.width, (rect.y + rect.height) * bounds.height],
    ['se', (rect.x + rect.width) * bounds.width, (rect.y + rect.height) * bounds.height],
  ];
  for (const [name, cornerX, cornerY] of corners) {
    if (Math.hypot(pxX - cornerX, pxY - cornerY) <= CROP_HANDLE_HIT_PX) return name;
  }
  const x = pxX / bounds.width;
  const y = pxY / bounds.height;
  if (x >= rect.x && x <= rect.x + rect.width && y >= rect.y && y <= rect.y + rect.height) {
    return 'move';
  }
  return null;
};

const loadImageElement = async (url: string) => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`无法读取图片（HTTP ${response.status}）`);
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const element = new Image();
    element.onload = () => resolve(element);
    element.onerror = () => reject(new Error('图片加载失败'));
    element.src = objectUrl;
  });
  return { image, revoke: () => URL.revokeObjectURL(objectUrl) };
};

const cropImageToFile = async (url: string, rect: CropRect) => {
  const { image, revoke } = await loadImageElement(url);
  try {
    const sourceX = Math.round(rect.x * image.width);
    const sourceY = Math.round(rect.y * image.height);
    const sourceWidth = Math.max(1, Math.round(rect.width * image.width));
    const sourceHeight = Math.max(1, Math.round(rect.height * image.height));
    const canvas = document.createElement('canvas');
    canvas.width = sourceWidth;
    canvas.height = sourceHeight;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('无法裁剪图片');
    context.drawImage(image, sourceX, sourceY, sourceWidth, sourceHeight, 0, 0, sourceWidth, sourceHeight);
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((next) => (next ? resolve(next) : reject(new Error('裁剪结果为空'))), 'image/png');
    });
    return new File([blob], 'canvas-crop.png', { type: 'image/png' });
  } finally {
    revoke();
  }
};

const toolbarButtonClass = 'flex h-9 cursor-pointer items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent';

export const ImageNodeAiTools: React.FC<ImageNodeAiToolsProps> = ({
  busy,
  floatingHidden,
  imageUrl,
  layoutNonce,
  mode,
  nodeId,
  selected,
  onApplyCrop,
  onApplyErase,
  onCancel,
  onError,
  gridSize,
  onRemoveBackground,
  onStartCrop,
  onStartMatting,
  onStartGridSplit,
  onSplitGridCells,
  onGenerateGridHd,
  onGenerateSmartMatte,
  onApplySmartMatting,
}) => {
  const overlayRef = useRef<HTMLDivElement>(null);
  const brushCanvasRef = useRef<HTMLCanvasElement>(null);
  const drawingRef = useRef(false);
  const lastPointRef = useRef<{ x: number; y: number } | null>(null);
  const [crop, setCrop] = useState<CropRect>(DEFAULT_CROP);
  const [hasEraseStroke, setHasEraseStroke] = useState(false);
  const [applying, setApplying] = useState(false);
  const [toolbarLayout, setToolbarLayout] = useState<{ left: number; top: number } | null>(null);
  const [gridMenuOpen, setGridMenuOpen] = useState(false);
  const [customHover, setCustomHover] = useState<GridSplitSize>({ cols: 0, rows: 0 });

  const cropHostRef = useRef<HTMLDivElement>(null);
  const cropImageRef = useRef<HTMLImageElement>(null);
  const cropStageRef = useRef<HTMLDivElement>(null);
  const cropRef = useRef(crop);
  const cropDragRef = useRef<{
    handle: CropHandle;
    startClientX: number;
    startClientY: number;
    start: CropRect;
    bounds: DOMRect;
  } | null>(null);
  const [cropImageBox, setCropImageBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  cropRef.current = crop;

  const toolBusy = Boolean(busy || applying);
  const showToolbar = !floatingHidden
    && mode !== 'grid-split'
    && mode !== 'matting'
    && Boolean(selected || (mode !== 'idle' && mode !== 'crop'));

  useEffect(() => {
    if (mode !== 'crop') setCrop(DEFAULT_CROP);
    if (mode !== 'erase') {
      setHasEraseStroke(false);
      const canvas = brushCanvasRef.current;
      const context = canvas?.getContext('2d');
      if (canvas && context) context.clearRect(0, 0, canvas.width, canvas.height);
    }
  }, [mode, imageUrl]);

  useEffect(() => {
    if (mode !== 'idle') setGridMenuOpen(false);
  }, [mode]);

  useEffect(() => {
    if (!gridMenuOpen) {
      setCustomHover({ cols: 0, rows: 0 });
      return;
    }
    const closeMenu = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[data-canvas-image-ai-toolbar]')) return;
      setGridMenuOpen(false);
    };
    window.addEventListener('pointerdown', closeMenu, true);
    return () => window.removeEventListener('pointerdown', closeMenu, true);
  }, [gridMenuOpen]);

  const syncBrushCanvasSize = () => {
    const canvas = brushCanvasRef.current;
    const host = overlayRef.current;
    if (!canvas || !host) return;
    const width = Math.max(1, Math.round(host.clientWidth));
    const height = Math.max(1, Math.round(host.clientHeight));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      setHasEraseStroke(false);
    }
  };

  useLayoutEffect(() => {
    if (mode !== 'erase') return;
    syncBrushCanvasSize();
    const host = overlayRef.current;
    if (!host || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => syncBrushCanvasSize());
    observer.observe(host);
    return () => observer.disconnect();
  }, [mode]);

  useLayoutEffect(() => {
    if (!showToolbar) {
      setToolbarLayout(null);
      return;
    }

    const updateLayout = () => {
      const node = document.querySelector(`[data-canvas-node="${nodeId}"]`) as HTMLElement | null;
      if (!node) return;
      const nodeRect = node.getBoundingClientRect();
      const canvas = node.closest('section');
      const canvasRect = canvas?.getBoundingClientRect();
      const left = nodeRect.left + nodeRect.width / 2;
      const above = nodeRect.top - TITLE_OFFSET - TOOLBAR_HEIGHT - TOOLBAR_GAP;
      const below = nodeRect.bottom + TOOLBAR_GAP;
      const minTop = (canvasRect?.top ?? 8) + 8;
      const maxTop = Math.max(minTop, (canvasRect?.bottom ?? window.innerHeight) - TOOLBAR_HEIGHT - 8);
      const top = clamp(above >= minTop ? above : below, minTop, maxTop);
      setToolbarLayout((current) => (
        current && Math.abs(current.left - left) < 0.5 && Math.abs(current.top - top) < 0.5
          ? current
          : { left, top }
      ));
    };

    updateLayout();
    window.addEventListener('resize', updateLayout);
    window.addEventListener('scroll', updateLayout, true);
    return () => {
      window.removeEventListener('resize', updateLayout);
      window.removeEventListener('scroll', updateLayout, true);
    };
  }, [layoutNonce, mode, nodeId, showToolbar]);

  const paintErase = (clientX: number, clientY: number) => {
    const canvas = brushCanvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    const bounds = canvas.getBoundingClientRect();
    const x = ((clientX - bounds.left) / bounds.width) * canvas.width;
    const y = ((clientY - bounds.top) / bounds.height) * canvas.height;
    const radius = Math.max(10, Math.min(canvas.width, canvas.height) * ERASE_BRUSH_RATIO);
    const previous = lastPointRef.current;
    context.lineCap = 'round';
    context.lineJoin = 'round';
    context.strokeStyle = '#ffffff';
    context.fillStyle = '#ffffff';
    context.lineWidth = radius * 2;
    context.beginPath();
    if (previous) {
      context.moveTo(previous.x, previous.y);
      context.lineTo(x, y);
      context.stroke();
    } else {
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
    }
    lastPointRef.current = { x, y };
    setHasEraseStroke(true);
  };

  useLayoutEffect(() => {
    if (mode !== 'crop') {
      setCropImageBox(null);
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const updateImageBox = () => {
      const stage = cropStageRef.current;
      const image = cropImageRef.current;
      if (!stage || !image || !image.naturalWidth || !image.naturalHeight) return;
      const stageWidth = stage.clientWidth;
      const stageHeight = stage.clientHeight;
      const imageRatio = image.naturalWidth / image.naturalHeight;
      const stageRatio = stageWidth / Math.max(1, stageHeight);
      const width = imageRatio > stageRatio ? stageWidth : stageHeight * imageRatio;
      const height = imageRatio > stageRatio ? stageWidth / imageRatio : stageHeight;
      setCropImageBox({
        left: (stageWidth - width) / 2,
        top: (stageHeight - height) / 2,
        width,
        height,
      });
    };

    updateImageBox();
    window.addEventListener('resize', updateImageBox);
    const stage = cropStageRef.current;
    const observer = stage && typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(updateImageBox)
      : null;
    if (stage && observer) observer.observe(stage);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('resize', updateImageBox);
      observer?.disconnect();
    };
  }, [imageUrl, mode]);

  useEffect(() => {
    if (mode !== 'crop' || !cropImageBox) return;

    const onPointerDown = (event: PointerEvent | MouseEvent) => {
      if (event.button !== 0) return;
      const host = cropHostRef.current;
      if (!host) return;
      const bounds = host.getBoundingClientRect();
      const handle = hitCropHandle(event.clientX, event.clientY, bounds, cropRef.current);
      if (!handle) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      cropDragRef.current = {
        handle,
        startClientX: event.clientX,
        startClientY: event.clientY,
        start: { ...cropRef.current },
        bounds,
      };
      if ('pointerId' in event) {
        try {
          host.setPointerCapture(event.pointerId);
        } catch {
          // 窗口捕获监听仍然能拖动裁剪框。
        }
      }
    };

    const onPointerMove = (event: PointerEvent | MouseEvent) => {
      const drag = cropDragRef.current;
      const host = cropHostRef.current;
      if (drag) {
        event.preventDefault();
        event.stopPropagation();
        const deltaX = (event.clientX - drag.startClientX) / drag.bounds.width;
        const deltaY = (event.clientY - drag.startClientY) / drag.bounds.height;
        setCrop(applyCropDelta(drag.start, drag.handle, deltaX, deltaY));
        return;
      }
      if (!host) return;
      const handle = hitCropHandle(
        event.clientX,
        event.clientY,
        host.getBoundingClientRect(),
        cropRef.current,
      );
      host.style.cursor = handle === 'move'
        ? 'move'
        : handle === 'nw' || handle === 'se'
          ? 'nwse-resize'
          : handle === 'ne' || handle === 'sw'
            ? 'nesw-resize'
            : 'crosshair';
    };

    const onPointerUp = () => {
      cropDragRef.current = null;
    };

    // 必须挂在 window 捕获阶段：画布节点的 pointerdown 也会在捕获期抢走拖动。
    window.addEventListener('pointerdown', onPointerDown, { capture: true, passive: false });
    window.addEventListener('pointermove', onPointerMove, { capture: true, passive: false });
    window.addEventListener('pointerup', onPointerUp, true);
    window.addEventListener('pointercancel', onPointerUp, true);
    window.addEventListener('mousedown', onPointerDown, { capture: true, passive: false });
    window.addEventListener('mousemove', onPointerMove, { capture: true, passive: false });
    window.addEventListener('mouseup', onPointerUp, true);
    return () => {
      cropDragRef.current = null;
      window.removeEventListener('pointerdown', onPointerDown, true);
      window.removeEventListener('pointermove', onPointerMove, true);
      window.removeEventListener('pointerup', onPointerUp, true);
      window.removeEventListener('pointercancel', onPointerUp, true);
      window.removeEventListener('mousedown', onPointerDown, true);
      window.removeEventListener('mousemove', onPointerMove, true);
      window.removeEventListener('mouseup', onPointerUp, true);
    };
  }, [cropImageBox, mode]);

  const handleApply = async () => {
    if (applying || busy) return;
    setApplying(true);
    try {
      if (mode === 'crop') {
        await onApplyCrop(await cropImageToFile(imageUrl, crop));
        return;
      }
      const canvas = brushCanvasRef.current;
      if (!canvas || !hasEraseStroke) return;
      const mask = document.createElement('canvas');
      mask.width = canvas.width;
      mask.height = canvas.height;
      const context = mask.getContext('2d');
      if (!context) throw new Error('无法生成去图蒙版');
      context.fillStyle = '#000000';
      context.fillRect(0, 0, mask.width, mask.height);
      context.drawImage(canvas, 0, 0);
      await onApplyErase(mask.toDataURL('image/png'));
    } catch (error) {
      onError?.(error instanceof Error ? error.message : '处理失败');
    } finally {
      setApplying(false);
    }
  };

  const toolbar = showToolbar && toolbarLayout && typeof document !== 'undefined'
    ? createPortal(
      <div
        role="toolbar"
        aria-label="图片 AI 功能"
        data-canvas-image-ai-toolbar="true"
        onPointerDown={(event) => event.stopPropagation()}
        className="canvas-floating-toolbar fixed z-[200] flex items-center gap-0.5 overflow-visible rounded-2xl border border-slate-200 bg-white px-1.5 py-1 text-slate-700 shadow-[0_12px_36px_rgba(15,23,42,0.16)]"
        style={{
          left: toolbarLayout.left,
          top: toolbarLayout.top,
          transform: 'translateX(-50%)',
        }}
      >
        <span className="flex h-9 w-9 items-center justify-center text-slate-500" aria-hidden="true">
          <Sparkles size={15} />
        </span>
        <span className="mx-0.5 h-5 w-px bg-slate-200" aria-hidden="true" />
        {mode === 'idle' ? (
          <>
            <button type="button" disabled={toolBusy} onClick={onRemoveBackground} className={toolbarButtonClass}>
              {toolBusy ? <Loader2 size={14} className="animate-spin" /> : <WandSparkles size={14} />}
              去背景
            </button>
            <button
              type="button"
              disabled={toolBusy}
              title="点选主体后用 image-2 抠图，再用画笔修边"
              onClick={onStartMatting}
              className={toolbarButtonClass}
            >
              <Scan size={14} />
              智能抠图
            </button>
            <button type="button" disabled={toolBusy} onClick={onStartCrop} className={toolbarButtonClass}>
              <Crop size={14} />
              裁剪
            </button>
            <div className="relative">
              <button
                type="button"
                disabled={toolBusy}
                aria-expanded={gridMenuOpen}
                aria-haspopup="menu"
                title="把宫格合成图切成独立分镜"
                onClick={() => setGridMenuOpen((open) => !open)}
                className={toolbarButtonClass}
              >
                <Grid3X3 size={14} />
                宫格切分
                <ChevronDown size={13} />
              </button>
              {gridMenuOpen && (
                <div
                  role="menu"
                  aria-label="选择宫格"
                  className="canvas-grid-split-menu"
                  onPointerDown={(event) => event.stopPropagation()}
                >
                  {GRID_SPLIT_PRESETS.map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setGridMenuOpen(false);
                        onStartGridSplit(preset);
                      }}
                      className="canvas-grid-split-menu__item"
                    >
                      {preset.label}
                    </button>
                  ))}
                  <span className="canvas-grid-split-menu__divider" aria-hidden="true" />
                  <div
                    className="canvas-grid-split-custom"
                    onMouseLeave={() => setCustomHover({ cols: 0, rows: 0 })}
                  >
                    <span className="canvas-grid-split-menu__item canvas-grid-split-custom__label">
                      自定义
                      <ChevronRight size={13} />
                    </span>
                    <div className="canvas-grid-split-custom__panel" role="group" aria-label="自定义宫格">
                      <div className="canvas-grid-split-custom__head">
                        <span>自定义宫格</span>
                        <strong>
                          {customHover.cols > 0 ? `${customHover.cols} × ${customHover.rows}` : '选择尺寸'}
                        </strong>
                      </div>
                      <div
                        className="canvas-grid-split-custom__grid"
                        style={{ gridTemplateColumns: `repeat(${MAX_CUSTOM_GRID}, 18px)` }}
                      >
                        {Array.from({ length: MAX_CUSTOM_GRID * MAX_CUSTOM_GRID }, (_, index) => {
                          const col = (index % MAX_CUSTOM_GRID) + 1;
                          const row = Math.floor(index / MAX_CUSTOM_GRID) + 1;
                          const active = customHover.cols >= col && customHover.rows >= row;
                          return (
                            <button
                              key={`${row}-${col}`}
                              type="button"
                              aria-label={`${col} × ${row}`}
                              onMouseEnter={() => setCustomHover({ cols: col, rows: row })}
                              onClick={() => {
                                setGridMenuOpen(false);
                                onStartGridSplit({ cols: col, rows: row });
                              }}
                              className={`canvas-grid-split-custom__cell ${active ? 'is-active' : ''}`}
                            />
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <span className="px-2 text-xs font-medium text-slate-500">
              涂抹要去掉的区域
            </span>
            <span className="mx-0.5 h-5 w-px bg-slate-200" aria-hidden="true" />
            <button type="button" disabled={toolBusy} onClick={onCancel} className={toolbarButtonClass}>
              <X size={14} />
              取消
            </button>
            <button
              type="button"
              disabled={toolBusy || (mode === 'erase' && !hasEraseStroke)}
              onClick={() => void handleApply()}
              className={`${toolbarButtonClass} bg-slate-900 text-white hover:bg-slate-800 hover:text-white disabled:bg-slate-200 disabled:text-slate-400`}
            >
              {toolBusy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              完成
            </button>
          </>
        )}
      </div>,
      document.body,
    )
    : null;

  const cropModal = !floatingHidden && mode === 'crop' && typeof document !== 'undefined'
    ? createPortal(
      <div
        className="fixed inset-0 z-[240] flex items-center justify-center bg-slate-950/50 p-4"
        data-canvas-crop-dialog="true"
        role="dialog"
        aria-modal="true"
        aria-labelledby="canvas-crop-dialog-title"
        onPointerDown={(event) => {
          event.stopPropagation();
          if (event.target === event.currentTarget && !toolBusy) onCancel();
        }}
      >
        <div
          className="flex w-[min(920px,calc(100vw-32px))] max-h-[calc(100vh-32px)] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.28)]"
          onPointerDown={(event) => event.stopPropagation()}
        >
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-3">
            <div>
              <h2 id="canvas-crop-dialog-title" className="text-sm font-semibold text-slate-900">裁剪图片</h2>
              <p className="mt-0.5 text-xs text-slate-500">拖动裁剪框或四角手柄，确认后只保留框内画面</p>
            </div>
            <button
              type="button"
              aria-label="关闭裁剪"
              disabled={toolBusy}
              onClick={onCancel}
              className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-300"
            >
              <X size={17} />
            </button>
          </div>
          <div
            ref={cropStageRef}
            className="relative flex min-h-[320px] flex-1 items-center justify-center bg-slate-100"
            style={{ height: 'min(560px, calc(100vh - 220px))' }}
          >
            <img
              ref={cropImageRef}
              src={imageUrl}
              alt="待裁剪图片"
              draggable={false}
              onLoad={() => {
                const stage = cropStageRef.current;
                const image = cropImageRef.current;
                if (!stage || !image || !image.naturalWidth) return;
                const stageWidth = stage.clientWidth;
                const stageHeight = stage.clientHeight;
                const imageRatio = image.naturalWidth / image.naturalHeight;
                const stageRatio = stageWidth / Math.max(1, stageHeight);
                const width = imageRatio > stageRatio ? stageWidth : stageHeight * imageRatio;
                const height = imageRatio > stageRatio ? stageWidth / imageRatio : stageHeight;
                setCropImageBox({
                  left: (stageWidth - width) / 2,
                  top: (stageHeight - height) / 2,
                  width,
                  height,
                });
              }}
              className="max-h-full max-w-full select-none object-contain"
            />
            {cropImageBox && (
              <div
                ref={cropHostRef}
                className="absolute touch-none"
                style={{
                  left: cropImageBox.left,
                  top: cropImageBox.top,
                  width: cropImageBox.width,
                  height: cropImageBox.height,
                }}
              >
                <div
                  className="pointer-events-none absolute bg-slate-950/45"
                  style={{ left: 0, top: 0, right: 0, height: `${crop.y * 100}%` }}
                />
                <div
                  className="pointer-events-none absolute bg-slate-950/45"
                  style={{
                    left: 0,
                    top: `${crop.y * 100}%`,
                    width: `${crop.x * 100}%`,
                    height: `${crop.height * 100}%`,
                  }}
                />
                <div
                  className="pointer-events-none absolute bg-slate-950/45"
                  style={{
                    left: `${(crop.x + crop.width) * 100}%`,
                    top: `${crop.y * 100}%`,
                    right: 0,
                    height: `${crop.height * 100}%`,
                  }}
                />
                <div
                  className="pointer-events-none absolute bg-slate-950/45"
                  style={{
                    left: 0,
                    top: `${(crop.y + crop.height) * 100}%`,
                    right: 0,
                    bottom: 0,
                  }}
                />
                <div
                  className="pointer-events-none absolute cursor-move border-2 border-white"
                  style={{
                    left: `${crop.x * 100}%`,
                    top: `${crop.y * 100}%`,
                    width: `${crop.width * 100}%`,
                    height: `${crop.height * 100}%`,
                  }}
                >
                  {CROP_HANDLES.map((handle) => (
                    <span
                      key={handle}
                      data-crop-handle={handle}
                      className={`absolute z-10 flex h-8 w-8 items-center justify-center ${
                        handle === 'nw'
                          ? 'left-0 top-0 cursor-nwse-resize'
                          : handle === 'ne'
                            ? 'right-0 top-0 cursor-nesw-resize'
                            : handle === 'sw'
                              ? 'bottom-0 left-0 cursor-nesw-resize'
                              : 'bottom-0 right-0 cursor-nwse-resize'
                      }`}
                    >
                      <span className="h-3.5 w-3.5 rounded-sm border-2 border-violet-500 bg-white shadow-sm" />
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
            <button
              type="button"
              disabled={toolBusy}
              onClick={onCancel}
              className={toolbarButtonClass}
            >
              取消
            </button>
            <button
              type="button"
              disabled={toolBusy}
              onClick={() => void handleApply()}
              className={`${toolbarButtonClass} bg-slate-900 text-white hover:bg-slate-800 hover:text-white`}
            >
              {toolBusy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              完成裁剪
            </button>
          </div>
        </div>
      </div>,
      document.body,
    )
    : null;

  return (
    <>
      <div
        ref={overlayRef}
        className={`absolute inset-0 z-40 ${mode === 'erase' ? 'pointer-events-auto' : 'pointer-events-none'}`}
        onPointerDown={(event) => event.stopPropagation()}
      >
        {mode === 'erase' && (
          <canvas
            ref={brushCanvasRef}
            className="absolute inset-0 h-full w-full cursor-crosshair touch-none"
            onPointerDown={(event) => {
              event.preventDefault();
              drawingRef.current = true;
              lastPointRef.current = null;
              event.currentTarget.setPointerCapture(event.pointerId);
              paintErase(event.clientX, event.clientY);
            }}
            onPointerMove={(event) => {
              if (!drawingRef.current) return;
              paintErase(event.clientX, event.clientY);
            }}
            onPointerUp={() => {
              drawingRef.current = false;
              lastPointRef.current = null;
            }}
            onPointerCancel={() => {
              drawingRef.current = false;
              lastPointRef.current = null;
            }}
          />
        )}
      </div>
      {toolbar}
      {cropModal}
      {mode === 'matting' && (
        <ImageMattingTool
          nodeId={nodeId}
          imageUrl={imageUrl}
          busy={busy}
          onCancel={onCancel}
          onError={onError}
          onGenerateMatte={onGenerateSmartMatte}
          onCommit={onApplySmartMatting}
        />
      )}
      {mode === 'grid-split' && gridSize && (
        <ImageGridSplitTool
          nodeId={nodeId}
          size={gridSize}
          busy={busy}
          floatingHidden={floatingHidden}
          layoutNonce={layoutNonce}
          onCancel={onCancel}
          onSplitCells={onSplitGridCells}
          onGenerateHd={onGenerateGridHd}
        />
      )}
    </>
  );
};
