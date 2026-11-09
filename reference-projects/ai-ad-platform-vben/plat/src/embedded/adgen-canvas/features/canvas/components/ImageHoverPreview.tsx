/** @jsxImportSource react */
import { useCallback, useEffect, useRef, useState, type SyntheticEvent } from 'react';
import { createPortal } from 'react-dom';

const PREVIEW_MAX_WIDTH = 320;
const PREVIEW_MAX_HEIGHT = 360;
const PREVIEW_GAP = 10;
const SHOW_DELAY_MS = 120;
const HIDE_DELAY_MS = 60;

export type ImageHoverPreviewKind = 'image' | 'video';

interface ImageHoverPreviewState {
  url: string;
  label: string;
  kind: ImageHoverPreviewKind;
  left: number;
  top: number;
  width: number;
}

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

const getPreviewBox = (contentWidth: number, contentHeight: number) => {
  const width = Math.min(PREVIEW_MAX_WIDTH, window.innerWidth - 16);
  const height = Math.min(
    Math.max(contentHeight + 36, 120),
    PREVIEW_MAX_HEIGHT + 40,
    window.innerHeight - 16,
  );
  return { width, height };
};

const getPreviewPosition = (
  anchor: DOMRect,
  contentWidth = PREVIEW_MAX_WIDTH,
  contentHeight = PREVIEW_MAX_HEIGHT,
) => {
  const { width, height } = getPreviewBox(contentWidth, contentHeight);
  let left = anchor.left + anchor.width / 2 - width / 2;
  let top = anchor.top - height - PREVIEW_GAP;
  if (top < 8) top = anchor.bottom + PREVIEW_GAP;
  left = clamp(left, 8, window.innerWidth - width - 8);
  top = clamp(top, 8, window.innerHeight - height - 8);
  return { left, top, width };
};

/**
 * 小缩略图悬停时在屏幕坐标弹出大图，方便辨认多张参考图或批量结果。
 */
export const useImageHoverPreview = () => {
  const [preview, setPreview] = useState<ImageHoverPreviewState | null>(null);
  const previewVisibleRef = useRef(false);
  const showTimerRef = useRef<number | null>(null);
  const hideTimerRef = useRef<number | null>(null);
  const anchorRectRef = useRef<DOMRect | null>(null);

  const clearTimers = () => {
    if (showTimerRef.current !== null) {
      window.clearTimeout(showTimerRef.current);
      showTimerRef.current = null;
    }
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  };

  useEffect(() => () => clearTimers(), []);

  const showPreview = useCallback((
    anchor: DOMRect | HTMLElement,
    url: string,
    label: string,
    kind: ImageHoverPreviewKind = 'image',
  ) => {
    if (!url) return;
    clearTimers();
    const rect = anchor instanceof HTMLElement ? anchor.getBoundingClientRect() : anchor;
    anchorRectRef.current = rect;
    const apply = () => {
      previewVisibleRef.current = true;
      setPreview({ url, label, kind, ...getPreviewPosition(rect) });
    };
    // 已在预览时立刻换图，避免扫过多张缩略图时闪一下空白。
    if (previewVisibleRef.current) {
      apply();
      return;
    }
    showTimerRef.current = window.setTimeout(() => {
      apply();
      showTimerRef.current = null;
    }, SHOW_DELAY_MS);
  }, []);

  const hidePreview = useCallback(() => {
    if (showTimerRef.current !== null) {
      window.clearTimeout(showTimerRef.current);
      showTimerRef.current = null;
    }
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
    }
    hideTimerRef.current = window.setTimeout(() => {
      previewVisibleRef.current = false;
      setPreview(null);
      hideTimerRef.current = null;
    }, HIDE_DELAY_MS);
  }, []);

  const handleMediaLoad = useCallback((
    event: SyntheticEvent<HTMLImageElement | HTMLVideoElement>,
  ) => {
    const target = event.currentTarget;
    const naturalWidth = 'naturalWidth' in target ? target.naturalWidth : target.videoWidth;
    const naturalHeight = 'naturalHeight' in target ? target.naturalHeight : target.videoHeight;
    const anchor = anchorRectRef.current;
    if (!anchor || !naturalWidth || !naturalHeight) return;
    const maxW = Math.min(PREVIEW_MAX_WIDTH, window.innerWidth - 16);
    const maxH = Math.min(PREVIEW_MAX_HEIGHT, window.innerHeight * 0.56);
    const scale = Math.min(maxW / naturalWidth, maxH / naturalHeight, 1);
    setPreview((current) => {
      if (!current) return current;
      return {
        ...current,
        ...getPreviewPosition(anchor, naturalWidth * scale, naturalHeight * scale),
      };
    });
  }, []);

  const previewNode = preview && typeof document !== 'undefined'
    ? createPortal(
        <div
          className="canvas-image-hover-preview"
          role="img"
          aria-label={preview.label}
          style={{ left: preview.left, top: preview.top, width: preview.width }}
        >
          {preview.kind === 'video' ? (
            <video
              src={preview.url}
              muted
              playsInline
              autoPlay
              loop
              onLoadedMetadata={handleMediaLoad}
            />
          ) : (
            <img
              src={preview.url}
              alt={preview.label}
              onLoad={handleMediaLoad}
            />
          )}
          <p>{preview.label}</p>
        </div>,
        document.body,
      )
    : null;

  return { showPreview, hidePreview, previewNode };
};

export default useImageHoverPreview;
