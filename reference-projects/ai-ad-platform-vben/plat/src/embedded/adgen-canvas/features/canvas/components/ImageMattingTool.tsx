/** @jsxImportSource react */
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Eraser, Loader2, Scan, X } from 'lucide-react';

import {
  compositeCutoutFile,
  createHintMaskDataUrl,
  createSmartMattingFilename,
  drawCutoutPreview,
  extractMatteData,
  hasMattingSelection,
  loadImageElement,
  normalizeBox,
  paintMatteStroke,
  type MattingBox,
  type MattingPoint,
} from './imageMatting';

type MattingStep = 'select' | 'refine';

interface ImageMattingToolProps {
  busy?: boolean;
  imageUrl: string;
  nodeId: string;
  onCancel: () => void;
  onCommit: (file: File) => Promise<void> | void;
  onError?: (message: string) => void;
  onGenerateMatte: (hintMaskDataUrl: string) => Promise<string>;
}

const MIN_BRUSH_RATIO = 0.012;
const MAX_BRUSH_RATIO = 0.12;
const DEFAULT_BRUSH_RATIO = 0.045;
const DRAG_THRESHOLD = 6;
const CHECKERBOARD_CLASS = '[background-image:linear-gradient(45deg,#cbd5e1_25%,transparent_25%),linear-gradient(-45deg,#cbd5e1_25%,transparent_25%),linear-gradient(45deg,transparent_75%,#cbd5e1_75%),linear-gradient(-45deg,transparent_75%,#cbd5e1_75%)] [background-position:0_0,0_8px,8px_-8px,-8px_0] [background-size:16px_16px] bg-white';

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const toolbarButtonClass = 'flex h-9 cursor-pointer items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-300 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent';

const eventToPoint = (event: PointerEvent | React.PointerEvent, bounds: DOMRect): MattingPoint => ({
  x: clamp((event.clientX - bounds.left) / Math.max(1, bounds.width), 0, 1),
  y: clamp((event.clientY - bounds.top) / Math.max(1, bounds.height), 0, 1),
});

const measureContainedImage = (
  stage: HTMLElement,
  image: HTMLImageElement,
) => {
  if (!image.naturalWidth || !image.naturalHeight) return null;
  const stageWidth = stage.clientWidth;
  const stageHeight = stage.clientHeight;
  const imageRatio = image.naturalWidth / image.naturalHeight;
  const stageRatio = stageWidth / Math.max(1, stageHeight);
  const width = imageRatio > stageRatio ? stageWidth : stageHeight * imageRatio;
  const height = imageRatio > stageRatio ? stageWidth / imageRatio : stageHeight;
  return {
    left: (stageWidth - width) / 2,
    top: (stageHeight - height) / 2,
    width,
    height,
  };
};

export const ImageMattingTool: React.FC<ImageMattingToolProps> = ({
  busy,
  imageUrl,
  nodeId,
  onCancel,
  onCommit,
  onError,
  onGenerateMatte,
}) => {
  const stageRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);
  const originalRef = useRef<HTMLImageElement | null>(null);
  const modelRef = useRef<HTMLImageElement | null>(null);
  const originalObjectUrlRef = useRef<(() => void) | null>(null);
  const modelObjectUrlRef = useRef<(() => void) | null>(null);
  const baseMatteRef = useRef<ImageData | null>(null);
  const matteRef = useRef<ImageData | null>(null);
  const drawingRef = useRef(false);
  const lastPointRef = useRef<MattingPoint | null>(null);
  const dragStartRef = useRef<{ point: MattingPoint; clientX: number; clientY: number } | null>(null);
  const [step, setStep] = useState<MattingStep>('select');
  const [points, setPoints] = useState<MattingPoint[]>([]);
  const [box, setBox] = useState<MattingBox | null>(null);
  const [draftBox, setDraftBox] = useState<MattingBox | null>(null);
  const [applying, setApplying] = useState(false);
  const [imageBox, setImageBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [brushRatio, setBrushRatio] = useState(DEFAULT_BRUSH_RATIO);
  const [cursor, setCursor] = useState<MattingPoint | null>(null);
  const toolBusy = Boolean(busy || applying);
  const brushRatioRef = useRef(brushRatio);
  brushRatioRef.current = brushRatio;

  useEffect(() => {
    setStep('select');
    setPoints([]);
    setBox(null);
    setDraftBox(null);
    originalRef.current = null;
    modelRef.current = null;
    originalObjectUrlRef.current?.();
    originalObjectUrlRef.current = null;
    modelObjectUrlRef.current?.();
    modelObjectUrlRef.current = null;
    baseMatteRef.current = null;
    matteRef.current = null;
  }, [imageUrl, nodeId]);

  useEffect(() => () => {
    originalObjectUrlRef.current?.();
    modelObjectUrlRef.current?.();
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || toolBusy) return;
      event.preventDefault();
      onCancel();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel, toolBusy]);

  const updateImageBox = () => {
    const stage = stageRef.current;
    const image = imageRef.current;
    if (!stage || !image) return;
    const next = measureContainedImage(stage, image);
    if (!next) return;
    setImageBox((current) => (
      current
      && Math.abs(current.left - next.left) < 0.5
      && Math.abs(current.top - next.top) < 0.5
      && Math.abs(current.width - next.width) < 0.5
      && Math.abs(current.height - next.height) < 0.5
        ? current
        : next
    ));
  };

  useLayoutEffect(() => {
    updateImageBox();
    window.addEventListener('resize', updateImageBox);
    return () => window.removeEventListener('resize', updateImageBox);
  }, [imageUrl, step]);

  const paintPreview = () => {
    const canvas = previewRef.current;
    const source = modelRef.current || originalRef.current;
    const matte = matteRef.current;
    const host = overlayRef.current;
    if (!canvas || !source || !matte || !host) return;
    canvas.width = Math.max(1, Math.round(host.clientWidth));
    canvas.height = Math.max(1, Math.round(host.clientHeight));
    drawCutoutPreview(canvas, source, matte);
  };

  useLayoutEffect(() => {
    if (step !== 'refine') return;
    paintPreview();
  }, [step, imageBox]);

  const handleStartMatting = async () => {
    if (toolBusy || !hasMattingSelection(points, box)) return;
    setApplying(true);
    try {
      const originalLoaded = await loadImageElement(imageUrl);
      originalObjectUrlRef.current?.();
      originalObjectUrlRef.current = originalLoaded.revoke;
      originalRef.current = originalLoaded.image;
      const hintMask = createHintMaskDataUrl(
        originalLoaded.image.naturalWidth || originalLoaded.image.width,
        originalLoaded.image.naturalHeight || originalLoaded.image.height,
        points,
        box,
      );
      const matteUrl = await onGenerateMatte(hintMask);
      const modelLoaded = await loadImageElement(matteUrl);
      modelObjectUrlRef.current?.();
      modelObjectUrlRef.current = modelLoaded.revoke;
      modelRef.current = modelLoaded.image;
      const matte = extractMatteData(modelLoaded.image);
      baseMatteRef.current = new ImageData(new Uint8ClampedArray(matte.data), matte.width, matte.height);
      matteRef.current = matte;
      setStep('refine');
    } catch (error) {
      onError?.(error instanceof Error ? error.message : '智能抠图失败');
    } finally {
      setApplying(false);
    }
  };

  const handleCommit = async () => {
    const source = modelRef.current || originalRef.current;
    const matte = matteRef.current;
    if (!source || !matte || toolBusy) return;
    setApplying(true);
    try {
      await onCommit(await compositeCutoutFile(source, matte, createSmartMattingFilename()));
    } catch (error) {
      onError?.(error instanceof Error ? error.message : '保存抠图失败');
    } finally {
      setApplying(false);
    }
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const bounds = event.currentTarget.getBoundingClientRect();
    const point = eventToPoint(event, bounds);
    event.currentTarget.setPointerCapture(event.pointerId);
    if (step === 'select') {
      dragStartRef.current = { point, clientX: event.clientX, clientY: event.clientY };
      setDraftBox(null);
      return;
    }
    drawingRef.current = true;
    lastPointRef.current = point;
    const matte = matteRef.current;
    if (!matte) return;
    paintMatteStroke(matte, point, point, brushRatioRef.current, event.shiftKey ? 'restore' : 'erase', baseMatteRef.current || undefined);
    paintPreview();
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const point = eventToPoint(event, bounds);
    if (step === 'refine') setCursor(point);
    if (step === 'select' && dragStartRef.current) {
      const dragged = Math.hypot(
        event.clientX - dragStartRef.current.clientX,
        event.clientY - dragStartRef.current.clientY,
      ) >= DRAG_THRESHOLD;
      if (dragged) setDraftBox(normalizeBox(dragStartRef.current.point, point));
      return;
    }
    if (!drawingRef.current || !lastPointRef.current || !matteRef.current) return;
    paintMatteStroke(
      matteRef.current,
      lastPointRef.current,
      point,
      brushRatioRef.current,
      event.shiftKey ? 'restore' : 'erase',
      baseMatteRef.current || undefined,
    );
    lastPointRef.current = point;
    paintPreview();
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (step === 'select' && dragStartRef.current) {
      const bounds = event.currentTarget.getBoundingClientRect();
      const point = eventToPoint(event, bounds);
      const dragged = Math.hypot(
        event.clientX - dragStartRef.current.clientX,
        event.clientY - dragStartRef.current.clientY,
      ) >= DRAG_THRESHOLD;
      if (dragged) {
        setBox(normalizeBox(dragStartRef.current.point, point));
        setDraftBox(null);
      } else {
        setPoints((current) => [...current, dragStartRef.current!.point]);
      }
    }
    dragStartRef.current = null;
    drawingRef.current = false;
    lastPointRef.current = null;
  };

  const selectionBox = draftBox || box;
  const canStart = hasMattingSelection(points, box) && !toolBusy;

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[240] flex items-center justify-center bg-slate-950/50 p-4"
      data-canvas-matting-dialog="true"
      role="dialog"
      aria-modal="true"
      aria-labelledby="canvas-matting-dialog-title"
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
            <h2 id="canvas-matting-dialog-title" className="text-sm font-semibold text-slate-900">智能抠图</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {step === 'select'
                ? '点击选择主体，拖动可框选。'
                : '画笔继续去掉多余区域，按住 Shift 可恢复被擦掉的部分。'}
            </p>
          </div>
          <button
            type="button"
            aria-label="关闭智能抠图"
            disabled={toolBusy}
            onClick={onCancel}
            className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-violet-300"
          >
            <X size={17} />
          </button>
        </div>

        <div
          ref={stageRef}
          className="relative flex min-h-[320px] flex-1 items-center justify-center bg-slate-100"
          style={{ height: 'min(560px, calc(100vh - 220px))' }}
        >
          <img
            ref={imageRef}
            src={imageUrl}
            alt="待抠图图片"
            draggable={false}
            onLoad={updateImageBox}
            className={`max-h-full max-w-full select-none object-contain ${step === 'refine' ? 'invisible' : ''}`}
          />
          {imageBox && (
            <div
              ref={overlayRef}
              data-canvas-image-matting="true"
              className={`absolute cursor-crosshair touch-none ${step === 'refine' ? CHECKERBOARD_CLASS : ''}`}
              style={{
                left: imageBox.left,
                top: imageBox.top,
                width: imageBox.width,
                height: imageBox.height,
              }}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              onPointerLeave={() => setCursor(null)}
            >
              {step === 'refine' && (
                <canvas
                  ref={previewRef}
                  className="pointer-events-none absolute inset-0 h-full w-full"
                />
              )}
              {step === 'refine' && cursor && imageBox && (
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute rounded-full border border-white shadow-[0_0_0_1px_rgba(15,23,42,0.35)]"
                  style={{
                    left: `${cursor.x * 100}%`,
                    top: `${cursor.y * 100}%`,
                    width: Math.max(8, Math.min(imageBox.width, imageBox.height) * brushRatio * 2),
                    height: Math.max(8, Math.min(imageBox.width, imageBox.height) * brushRatio * 2),
                    transform: 'translate(-50%, -50%)',
                  }}
                />
              )}
              {step === 'select' && selectionBox && (
                <div
                  className="pointer-events-none absolute border-2 border-violet-500 bg-violet-500/10"
                  style={{
                    left: `${selectionBox.x * 100}%`,
                    top: `${selectionBox.y * 100}%`,
                    width: `${selectionBox.width * 100}%`,
                    height: `${selectionBox.height * 100}%`,
                  }}
                />
              )}
              {step === 'select' && points.map((point, index) => (
                <span
                  key={`${point.x}-${point.y}-${index}`}
                  className="pointer-events-none absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-violet-500 shadow-sm"
                  style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }}
                />
              ))}
            </div>
          )}
          {toolBusy && (
            <div
              className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-white/70 text-slate-700"
              role="status"
              aria-live="polite"
            >
              <Loader2 size={22} className="animate-spin" aria-hidden="true" />
              <span className="text-xs font-medium">
                {step === 'select' ? '正在生成抠图蒙版…' : '正在保存透明 PNG…'}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-5 py-3">
          {step === 'select' ? (
            <span className="flex min-w-0 items-center gap-1.5 text-xs text-slate-500">
              <Scan size={14} />
              <span className="truncate">可点多个位置，或拖出一个框</span>
            </span>
          ) : (
            <label className="flex min-w-0 items-center gap-2 text-xs text-slate-500">
              <Eraser size={14} />
              <span className="shrink-0">画笔</span>
              <input
                type="range"
                min={MIN_BRUSH_RATIO}
                max={MAX_BRUSH_RATIO}
                step={0.002}
                value={brushRatio}
                disabled={toolBusy}
                aria-label="画笔大小"
                onChange={(event) => setBrushRatio(Number(event.target.value))}
                className="h-9 w-[128px] cursor-pointer accent-slate-900 disabled:cursor-not-allowed"
              />
              <span className="w-6 shrink-0 text-right tabular-nums text-slate-400">
                {Math.round(((brushRatio - MIN_BRUSH_RATIO) / (MAX_BRUSH_RATIO - MIN_BRUSH_RATIO)) * 100)}
              </span>
            </label>
          )}
          <div className="flex items-center gap-2">
            {step === 'select' && (
              <button
                type="button"
                disabled={toolBusy || (points.length === 0 && !box)}
                onClick={() => {
                  setPoints([]);
                  setBox(null);
                  setDraftBox(null);
                }}
                className={toolbarButtonClass}
              >
                清除
              </button>
            )}
            <button type="button" disabled={toolBusy} onClick={onCancel} className={toolbarButtonClass}>
              取消
            </button>
            {step === 'select' ? (
              <button
                type="button"
                disabled={!canStart}
                onClick={() => void handleStartMatting()}
                className={`${toolbarButtonClass} bg-slate-900 text-white hover:bg-slate-800 hover:text-white disabled:bg-slate-200 disabled:text-slate-400`}
              >
                {toolBusy ? <Loader2 size={14} className="animate-spin" /> : <Scan size={14} />}
                开始抠图
              </button>
            ) : (
              <button
                type="button"
                disabled={toolBusy}
                onClick={() => void handleCommit()}
                className={`${toolbarButtonClass} bg-slate-900 text-white hover:bg-slate-800 hover:text-white disabled:bg-slate-200 disabled:text-slate-400`}
              >
                {toolBusy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                完成
              </button>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
};
