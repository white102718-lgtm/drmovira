export interface AssetExportColumn {
  key: string;
  label: string;
  /** Excel 单选下拉展示值；顺序必须与页面编辑器保持一致。 */
  selectOptions?: readonly string[];
  width?: number;
}

type AssetExportCell = null | number | string | undefined;

export const ASSET_EXPORT_BATCH_SIZE = 1000;

/** 按后端批量查询上限切分稳定 ID，并保持首次出现顺序。 */
export function chunkAssetExportIds(ids: readonly string[]) {
  const normalizedIds = [
    ...new Set(ids.map((id) => id.trim()).filter(Boolean)),
  ];
  return Array.from(
    { length: Math.ceil(normalizedIds.length / ASSET_EXPORT_BATCH_SIZE) },
    (_, index) =>
      normalizedIds.slice(
        index * ASSET_EXPORT_BATCH_SIZE,
        (index + 1) * ASSET_EXPORT_BATCH_SIZE,
      ),
  );
}

function normalizeAssetExportCell(value: AssetExportCell) {
  if (typeof value === 'string' && value.trim() === '') return '';
  return value ?? '';
}

/** 资产导出文件统一使用本地时间，精确到秒且避免文件名非法字符。 */
export function formatAssetExportTimestamp(date = new Date()) {
  const pad = (value: number) => String(value).padStart(2, '0');
  return [
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    `${pad(date.getHours())}-${pad(date.getMinutes())}-${pad(date.getSeconds())}`,
  ].join('_');
}

function uniqueSelectOptions(options: readonly string[]) {
  return [...new Set(options.map((option) => option.trim()).filter(Boolean))];
}

function downloadWorkbook(content: Uint8Array, fileName: string) {
  const fileUrl = URL.createObjectURL(
    new Blob([content], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }),
  );
  const link = document.createElement('a');
  link.href = fileUrl;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(fileUrl), 0);
}

/**
 * 生成资产导出工作簿内容，供下载与回导兼容性测试共用。
 */
export async function buildAssetWorkbook(
  sheetName: string,
  columns: readonly AssetExportColumn[],
  rows: ReadonlyArray<Record<string, AssetExportCell>>,
) {
  const ExcelJS = await import('exceljs');
  const Workbook = ExcelJS.Workbook ?? ExcelJS.default.Workbook;
  const workbook = new Workbook();
  const worksheet = workbook.addWorksheet(sheetName);
  worksheet.addRow(columns.map((column) => column.label));
  rows.forEach((row) => {
    worksheet.addRow(
      columns.map((column) => normalizeAssetExportCell(row[column.key])),
    );
  });
  columns.forEach((column, index) => {
    worksheet.getColumn(index + 1).width =
      column.width ?? Math.max(12, column.label.length * 2 + 4);
  });

  const selectableColumns = columns
    .map((column, index) => ({
      columnIndex: index + 1,
      options: uniqueSelectOptions(column.selectOptions ?? []),
    }))
    .filter((column) => column.options.length > 0);
  if (selectableColumns.length > 0) {
    const optionSheet = workbook.addWorksheet('__asset_export_options');
    optionSheet.state = 'veryHidden';
    selectableColumns.forEach(({ columnIndex, options }, optionIndex) => {
      const optionColumnIndex = optionIndex + 1;
      options.forEach((option, rowIndex) => {
        optionSheet.getCell(rowIndex + 1, optionColumnIndex).value = option;
      });
      const optionColumnName = optionSheet.getColumn(optionColumnIndex).letter;
      const rangeName = `AssetExportOptions_${optionColumnIndex}`;
      workbook.definedNames.add(
        `'${optionSheet.name}'!$${optionColumnName}$1:$${optionColumnName}$${options.length}`,
        rangeName,
      );
      for (let rowIndex = 2; rowIndex <= rows.length + 1; rowIndex++) {
        worksheet.getCell(rowIndex, columnIndex).dataValidation = {
          allowBlank: true,
          error: '请选择下拉列表中的有效选项',
          errorStyle: 'stop',
          errorTitle: '选项无效',
          formulae: [rangeName],
          showErrorMessage: true,
          type: 'list',
        };
      }
    });
  }

  return new Uint8Array(await workbook.xlsx.writeBuffer());
}

/**
 * 将已加载的资产数据生成 Excel 文件。
 *
 * @remarks
 * 导出仅在浏览器端完成，避免为不同资产台账重复维护服务端导出接口；调用方必须
 * 显式声明允许写入工作簿的列，包含敏感字段时也不得依赖行对象中的额外属性。
 */
export async function downloadAssetWorkbook(
  fileName: string,
  sheetName: string,
  columns: readonly AssetExportColumn[],
  rows: ReadonlyArray<Record<string, AssetExportCell>>,
) {
  downloadWorkbook(
    await buildAssetWorkbook(sheetName, columns, rows),
    fileName,
  );
}
