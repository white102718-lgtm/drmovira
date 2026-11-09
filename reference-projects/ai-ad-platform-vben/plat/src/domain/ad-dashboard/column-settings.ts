import type { AdDashboardField, AdDashboardSchema } from './types';

import type { DashboardColumnSetting } from '#/api/dashboard';

// 旧版按 dataIndex 保存，不能直接用新页面的英文 key 覆盖，否则旧配置无法恢复。
const legacyColumnKeys: Record<string, string> = {
  cpc: '点击成本',
  ctr: '点击率',
  ecpm: '千展',
  // 像素页同时有像素 ID 和通用 ID，配置必须能独立控制这两列。
  pixelId: '像素ID',
  statusText: 'status',
};

function columnKey(field: AdDashboardField) {
  return legacyColumnKeys[field.key] ?? field.sourceKey;
}

function aliases(field: AdDashboardField) {
  if (field.key === 'pixelId') return [columnKey(field), field.key];
  return [columnKey(field), field.key, field.sourceKey, field.label];
}

/** 固定列始终显示；旧可见列配置不能隐藏本次新增的固定字段。 */
export function resolveDashboardColumns(
  schema: AdDashboardSchema,
  setting?: DashboardColumnSetting,
) {
  const order = setting?.column_order ?? [];
  // 固定列以当前 schema 为准，旧偏好中的位置只作用于可移动列。
  const remaining = schema.fields.filter((field) => !field.fixed);
  const ordered: AdDashboardField[] = [];
  for (const key of order) {
    const index = remaining.findIndex((field) => aliases(field).includes(key));
    if (index !== -1) ordered.push(...remaining.splice(index, 1));
  }
  ordered.push(...remaining);
  // 固定列保持在两侧；已移除的字段忽略，新字段保留在配置列表末尾。
  const fields = [
    ...schema.fields.filter((field) => field.fixed === 'left'),
    ...ordered,
    ...schema.fields.filter((field) => field.fixed === 'right'),
  ];
  const visible = setting?.visible_columns;
  return {
    fields,
    visibleFields: fields.filter(
      (field) =>
        Boolean(field.fixed) ||
        visible === undefined ||
        aliases(field).some((key) => visible.includes(key)),
    ),
  };
}

/** 写回旧字段名，并保留当前新页面未展示的旧字段配置。 */
export function serializeDashboardColumns(
  schema: AdDashboardSchema,
  fields: AdDashboardField[],
  visibleKeys: string[],
  previous?: DashboardColumnSetting,
): DashboardColumnSetting {
  const knownKeys = new Set(schema.fields.flatMap((field) => aliases(field)));
  const keepUnknown = (keys: string[] = []) =>
    keys.filter((key) => !knownKeys.has(key));
  return {
    column_order: [
      ...fields
        .filter((field) => !field.fixed)
        .map((field) => columnKey(field)),
      ...keepUnknown(previous?.column_order),
    ],
    visible_columns: [
      ...fields
        .filter((field) => field.fixed || visibleKeys.includes(field.key))
        .map((field) => columnKey(field)),
      ...keepUnknown(previous?.visible_columns),
    ],
  };
}
