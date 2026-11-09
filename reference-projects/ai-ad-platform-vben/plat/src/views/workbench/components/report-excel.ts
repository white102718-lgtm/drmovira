import type { WorkBook } from 'xlsx';

export interface ReportExportColumn {
  key: string;
  title: string;
  money?: boolean;
}
export type ReportExportRow = Record<string, string | number>;

/** 仅写入声明的展示列；字符串按文本存储，金额按数值存储并保留两位格式。 */
export async function createReportWorkbook(
  columns: ReportExportColumn[],
  rows: ReportExportRow[],
  sheetName: string,
): Promise<WorkBook> {
  const XLSX = await import('xlsx');
  const sheet = XLSX.utils.aoa_to_sheet([
    columns.map((column) => column.title),
    ...rows.map((row) => columns.map((column) => row[column.key] ?? '')),
  ]);
  sheet['!cols'] = columns.map((column) => ({
    wch: Math.max(14, column.title.length * 2 + 4),
  }));
  sheet['!autofilter'] = {
    ref: XLSX.utils.encode_range({
      s: { r: 0, c: 0 },
      e: { r: rows.length, c: columns.length - 1 },
    }),
  };
  for (let c = 0; c < columns.length; c++) {
    if (!columns[c]?.money) continue;
    for (let r = 1; r <= rows.length; r++) {
      const cell = sheet[XLSX.utils.encode_cell({ r, c })];
      if (cell?.t === 'n') cell.z = '0.00';
    }
  }
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, sheetName);
  return workbook;
}

/** 返回前保留调用方检查页面是否仍在展示，避免离开页面后意外下载。 */
export async function downloadReportWorkbook(
  workbook: WorkBook,
  fileName: string,
) {
  const XLSX = await import('xlsx');
  XLSX.writeFileXLSX(workbook, fileName);
}
