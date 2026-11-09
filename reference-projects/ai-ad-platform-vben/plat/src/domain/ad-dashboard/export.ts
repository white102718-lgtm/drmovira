import type { AdDashboardRow, AdDashboardSchema } from './types';

import { formatAdDashboardValue } from './format';
import { formatAdDashboardStatus } from './status';

/** 固定为 Excel 文本单元格；双层转义保护长 ID、前导零、引号与换行。 */
function excelTextCell(value: string) {
  const literal = `="${value.replaceAll('"', '""')}"`;
  return `"${literal.replaceAll('"', '""')}"`;
}

/** 沿用旧版导出全部业务列，隐藏列不影响导出，操作按钮不导出。 */
export function buildAdDashboardCsv(
  schema: AdDashboardSchema,
  rows: AdDashboardRow[],
) {
  const extraStatusColumns = [
    { key: 'effectiveStatus', label: '实际投放状态' },
    { key: 'accountStatus', label: '账户状态' },
  ].filter((field) =>
    rows.some((row) => row[field.key] !== null && row[field.key] !== undefined),
  );
  const headers = [
    ...schema.fields.map((field) => field.label),
    '币种',
    ...extraStatusColumns.map((field) => field.label),
  ];
  const lines = [
    headers.map((value) => `"${value.replaceAll('"', '""')}"`).join(','),
  ];
  for (const row of rows) {
    const values = schema.fields.map((field) => {
      const value = row[field.key];
      if (value === null || value === undefined) return '';
      // 新模型的百分比为小数，导出时还原为页面百分比；金额保留原始精度。
      return String(
        field.dataType === 'percent'
          ? formatAdDashboardValue(value, field, row.currency)
          : value,
      );
    });
    // 金额导出原始数值，独立保留币种，避免多币种行失去上下文。
    values.push(row.currency);
    for (const field of extraStatusColumns) {
      values.push(
        formatAdDashboardStatus(
          field.key === 'accountStatus' ? 'account' : schema.category,
          row[field.key],
        ) ?? '',
      );
    }
    lines.push(values.map((value) => excelTextCell(value)).join(','));
  }
  return `\uFEFF${lines.join('\r\n')}`;
}

/** 浏览器端生成 CSV，数据查询仍使用广告面板的鉴权接口。 */
export function downloadAdDashboardCsv(
  schema: AdDashboardSchema,
  rows: AdDashboardRow[],
) {
  const blob = new Blob([buildAdDashboardCsv(schema, rows)], {
    type: 'text/csv;charset=utf-8;',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${schema.label}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  // 留出浏览器接收下载的时间，再释放文件地址。
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
