/** 资产表格使用统一的表头、行高与固定数据视口，避免不同台账在翻页时跳动。 */
export const ASSET_TABLE_HEADER_HEIGHT = 40;
export const ASSET_TABLE_ROW_HEIGHT = 44;
export const ASSET_TABLE_VISIBLE_ROW_COUNT = 12;
export const ASSET_TABLE_BODY_HEIGHT =
  ASSET_TABLE_VISIBLE_ROW_COUNT * ASSET_TABLE_ROW_HEIGHT;

/** 原生资产表格的滚动容器需要在数据区之外保留标准表头高度。 */
export const ASSET_TABLE_VIEWPORT_HEIGHT =
  ASSET_TABLE_BODY_HEIGHT + ASSET_TABLE_HEADER_HEIGHT;

/** 弹窗与抽屉内的次级表格固定显示 6 行，兼顾可读性与可操作空间。 */
export const ASSET_MODAL_TABLE_BODY_HEIGHT = 6 * ASSET_TABLE_ROW_HEIGHT;

/** 导入预览固定显示 5 行，与单页校验数量保持一致。 */
export const ASSET_PREVIEW_TABLE_BODY_HEIGHT = 5 * ASSET_TABLE_ROW_HEIGHT;
