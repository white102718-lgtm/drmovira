/**
 * 宫格切分：把一张宫格合成图按行列切开，生成接回原节点、也可再往下连的图片节点。
 * 交互对齐 LibTV：预设 2×2～5×5，自定义从左上角框选。
 */

export interface GridSplitSize {
  cols: number;
  rows: number;
}

export interface GridSplitCell {
  col: number;
  row: number;
}

export const GRID_SPLIT_PRESETS: Array<GridSplitSize & { label: string }> = [
  { cols: 2, rows: 2, label: '4宫格 (2×2)' },
  { cols: 3, rows: 3, label: '9宫格 (3×3)' },
  { cols: 4, rows: 4, label: '16宫格 (4×4)' },
  { cols: 5, rows: 5, label: '25宫格 (5×5)' },
];

export const MAX_CUSTOM_GRID = 5;
export const GRID_HD_SCALES = [2, 4] as const;
export type GridHdScale = (typeof GRID_HD_SCALES)[number];

export const cellKey = (cell: GridSplitCell) => `${cell.row + 1}-${cell.col + 1}`;

export const parseCellKey = (key: string): GridSplitCell => {
  const [rowLabel, colLabel] = key.split('-');
  return {
    row: Math.max(0, Number(rowLabel) - 1),
    col: Math.max(0, Number(colLabel) - 1),
  };
};

export const listGridCells = (size: GridSplitSize): GridSplitCell[] => {
  const cells: GridSplitCell[] = [];
  for (let row = 0; row < size.rows; row += 1) {
    for (let col = 0; col < size.cols; col += 1) {
      cells.push({ row, col });
    }
  }
  return cells;
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

const cropRectToFile = async (
  image: HTMLImageElement,
  rect: { x: number; y: number; width: number; height: number },
  filename: string,
) => {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, rect.width);
  canvas.height = Math.max(1, rect.height);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('无法切分图片');
  context.drawImage(
    image,
    rect.x,
    rect.y,
    rect.width,
    rect.height,
    0,
    0,
    rect.width,
    rect.height,
  );
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((next) => (next ? resolve(next) : reject(new Error('切分结果为空'))), 'image/png');
  });
  return new File([blob], filename, { type: 'image/png' });
};

/**
 * 按行列均分原图。行/列从 0 起算，输出文件名带 1-based 宫格坐标。
 */
export const sliceImageGridCells = async (
  url: string,
  size: GridSplitSize,
  cells: GridSplitCell[],
): Promise<Array<GridSplitCell & { file: File }>> => {
  if (cells.length === 0) return [];
  const { image, revoke } = await loadImageElement(url);
  try {
    const cellWidth = image.width / size.cols;
    const cellHeight = image.height / size.rows;
    const slices: Array<GridSplitCell & { file: File }> = [];
    for (const cell of cells) {
      const x = Math.round(cell.col * cellWidth);
      const y = Math.round(cell.row * cellHeight);
      const nextX = Math.round((cell.col + 1) * cellWidth);
      const nextY = Math.round((cell.row + 1) * cellHeight);
      const file = await cropRectToFile(
        image,
        {
          x,
          y,
          width: Math.max(1, nextX - x),
          height: Math.max(1, nextY - y),
        },
        `grid-${cellKey(cell)}.png`,
      );
      slices.push({ ...cell, file });
    }
    return slices;
  } finally {
    revoke();
  }
};
