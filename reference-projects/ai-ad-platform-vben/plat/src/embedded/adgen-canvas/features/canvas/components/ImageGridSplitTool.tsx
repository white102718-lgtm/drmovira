/** @jsxImportSource react */
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ChevronDown,
  Grid3X3,
  Images,
  Loader2,
  Sparkles,
  X,
} from 'lucide-react';

import {
  cellKey,
  GRID_HD_SCALES,
  listGridCells,
  parseCellKey,
  type GridHdScale,
  type GridSplitCell,
  type GridSplitSize,
} from './gridSplit';

interface ImageGridSplitToolProps {
  busy?: boolean;
  floatingHidden?: boolean;
  layoutNonce?: number;
  nodeId: string;
  size: GridSplitSize;
  onCancel: () => void;
  onSplitCells: (cells: GridSplitCell[]) => Promise<void> | void;
  onGenerateHd: (cells: GridSplitCell[], scale: GridHdScale) => Promise<void> | void;
}

const ACTION_BAR_HEIGHT = 48;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

export const ImageGridSplitTool: React.FC<ImageGridSplitToolProps> = ({
  busy,
  floatingHidden,
  layoutNonce,
  nodeId,
  size,
  onCancel,
  onSplitCells,
  onGenerateHd,
}) => {
  const gridRef = useRef<HTMLDivElement>(null);
  const paintRef = useRef<{ originKey: string } | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
  const [hdScale, setHdScale] = useState<GridHdScale>(2);
  const [scaleMenuOpen, setScaleMenuOpen] = useState(false);
  const [applying, setApplying] = useState(false);
  const [actionBarLayout, setActionBarLayout] = useState<{ left: number; top: number } | null>(null);

  const cells = useMemo(() => listGridCells(size), [size]);
  const selectedCells = useMemo(
    () => Array.from(selectedKeys).map(parseCellKey).sort((a, b) => a.row - b.row || a.col - b.col),
    [selectedKeys],
  );
  const toolBusy = Boolean(busy || applying);
  const canSubmit = selectedCells.length > 0 && !toolBusy;

  useEffect(() => {
    setSelectedKeys(new Set());
    setScaleMenuOpen(false);
  }, [size.cols, size.rows, nodeId]);

  useEffect(() => {
    if (!scaleMenuOpen) return;
    const closeMenu = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest('[data-canvas-grid-split-toolbar]')) return;
      setScaleMenuOpen(false);
    };
    window.addEventListener('pointerdown', closeMenu, true);
    return () => window.removeEventListener('pointerdown', closeMenu, true);
  }, [scaleMenuOpen]);

  useLayoutEffect(() => {
    const updateLayout = () => {
      const node = document.querySelector(`[data-canvas-node="${nodeId}"]`) as HTMLElement | null;
      if (!node) return;
      const nodeRect = node.getBoundingClientRect();
      const canvas = node.closest('section');
      const canvasRect = canvas?.getBoundingClientRect();
      const left = nodeRect.left + nodeRect.width / 2;
      const below = nodeRect.bottom + 10;
      const minTop = (canvasRect?.top ?? 8) + 8;
      const maxTop = Math.max(minTop, (canvasRect?.bottom ?? window.innerHeight) - ACTION_BAR_HEIGHT - 8);
      const top = clamp(below, minTop, maxTop);
      setActionBarLayout((current) => (
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
  }, [layoutNonce, nodeId, selectedKeys.size]);

  const cellFromPoint = (clientX: number, clientY: number): GridSplitCell | null => {
    const grid = gridRef.current;
    if (!grid) return null;
    const rect = grid.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) return null;
    const col = Math.floor(((clientX - rect.left) / rect.width) * size.cols);
    const row = Math.floor(((clientY - rect.top) / rect.height) * size.rows);
    if (col < 0 || row < 0 || col >= size.cols || row >= size.rows) return null;
    return { col, row };
  };

  const beginPaint = (event: React.PointerEvent) => {
    if (toolBusy || event.button !== 0) return;
    const cell = cellFromPoint(event.clientX, event.clientY);
    if (!cell) return;
    event.preventDefault();
    event.stopPropagation();
    const key = cellKey(cell);
    paintRef.current = { originKey: key };
    if (event.shiftKey) {
      setSelectedKeys((current) => {
        const next = new Set(current);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
      return;
    }
    setSelectedKeys(new Set([key]));
  };

  useEffect(() => {
    const onPointerMove = (event: PointerEvent) => {
      const paint = paintRef.current;
      if (!paint) return;
      const grid = gridRef.current;
      if (!grid) return;
      const rect = grid.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return;
      const col = Math.floor(((event.clientX - rect.left) / rect.width) * size.cols);
      const row = Math.floor(((event.clientY - rect.top) / rect.height) * size.rows);
      if (col < 0 || row < 0 || col >= size.cols || row >= size.rows) return;
      const key = cellKey({ col, row });
      if (paint.originKey === key) return;
      paint.originKey = '';
      setSelectedKeys((current) => {
        if (current.has(key)) return current;
        const next = new Set(current);
        next.add(key);
        return next;
      });
    };
    const onPointerUp = () => {
      paintRef.current = null;
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
    };
  }, [size.cols, size.rows]);

  const runAction = async (action: () => Promise<void> | void) => {
    if (!canSubmit) return;
    setScaleMenuOpen(false);
    setApplying(true);
    try {
      await action();
    } finally {
      setApplying(false);
    }
  };

  const actionBar = !floatingHidden && actionBarLayout && typeof document !== 'undefined'
    ? createPortal(
      <div
        role="toolbar"
        aria-label="宫格切分操作"
        data-canvas-grid-split-toolbar="true"
        onPointerDown={(event) => event.stopPropagation()}
        className="canvas-grid-split-actionbar canvas-floating-toolbar fixed z-[210] flex items-center gap-1 rounded-2xl px-1.5 py-1"
        style={{
          left: actionBarLayout.left,
          top: actionBarLayout.top,
          transform: 'translateX(-50%)',
        }}
      >
        <button
          type="button"
          disabled={toolBusy}
          aria-label="退出宫格切分"
          onClick={onCancel}
          className="canvas-grid-split-actionbar__btn"
        >
          <X size={15} />
        </button>
        <span className="canvas-grid-split-actionbar__divider" aria-hidden="true" />
        <span className="flex items-center gap-1.5 px-2 text-xs font-medium">
          <Grid3X3 size={14} />
          已选 {selectedCells.length} 个宫格
        </span>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => void runAction(() => onSplitCells(selectedCells))}
          className="canvas-grid-split-actionbar__btn canvas-grid-split-actionbar__btn--primary"
        >
          {applying ? <Loader2 size={14} className="animate-spin" /> : <Images size={14} />}
          切出选中
        </button>
        <span className="canvas-grid-split-actionbar__divider" aria-hidden="true" />
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => void runAction(() => onGenerateHd(selectedCells, hdScale))}
          className="canvas-grid-split-actionbar__btn canvas-grid-split-actionbar__btn--primary"
        >
          {applying ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          生成高清图片
        </button>
        <div className="relative">
          <button
            type="button"
            disabled={toolBusy}
            aria-expanded={scaleMenuOpen}
            aria-haspopup="listbox"
            onClick={() => setScaleMenuOpen((open) => !open)}
            className="canvas-grid-split-actionbar__btn"
          >
            {hdScale}倍
            <ChevronDown size={13} />
          </button>
          {scaleMenuOpen && (
            <div role="listbox" aria-label="高清倍率" className="canvas-grid-split-menu canvas-grid-split-menu--compact">
              {GRID_HD_SCALES.map((scale) => (
                <button
                  key={scale}
                  type="button"
                  role="option"
                  aria-selected={hdScale === scale}
                  onClick={() => {
                    setHdScale(scale);
                    setScaleMenuOpen(false);
                  }}
                  className={`canvas-grid-split-menu__item ${hdScale === scale ? 'is-active' : ''}`}
                >
                  {scale}倍
                </button>
              ))}
            </div>
          )}
        </div>
      </div>,
      document.body,
    )
    : null;

  return (
    <>
      <div
        className="canvas-grid-split-overlay absolute inset-0 z-40 touch-none"
        data-canvas-grid-split-overlay="true"
        onPointerDown={beginPaint}
      >
        <p className="canvas-grid-split-hint">按住 Shift 键可批量选择</p>
        <div
          ref={gridRef}
          className="absolute inset-0 grid"
          style={{
            gridTemplateColumns: `repeat(${size.cols}, minmax(0, 1fr))`,
            gridTemplateRows: `repeat(${size.rows}, minmax(0, 1fr))`,
          }}
        >
          {cells.map((cell) => {
            const key = cellKey(cell);
            const selected = selectedKeys.has(key);
            return (
              <div
                key={key}
                aria-pressed={selected}
                aria-label={`宫格 ${key}`}
                className={`canvas-grid-split-cell ${selected ? 'is-selected' : ''}`}
              >
                <span>{key}</span>
              </div>
            );
          })}
        </div>
      </div>
      {actionBar}
    </>
  );
};
