import type { CloakRecord } from '#/domain/cloak';

const MODE_LABELS: Record<CloakRecord['mode'], string> = {
  all: '全开',
  cloak: '斗篷',
  off: '全关',
};

const WRITEBACK_STATUS_LABELS: Record<
  CloakRecord['sheetWritebackStatus'],
  string
> = {
  failed: '回填失败',
  pending: '未回填',
  success: '已回填',
};

function formatDateTime(value: string) {
  return value ? value.replace('T', ' ').slice(0, 19) : '';
}

function formatFileTimestamp(date: Date) {
  const parts = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
    String(date.getHours()).padStart(2, '0'),
    String(date.getMinutes()).padStart(2, '0'),
    String(date.getSeconds()).padStart(2, '0'),
  ];
  return `${parts.slice(0, 3).join('')}_${parts.slice(3).join('')}`;
}

/** 将用户选中的斗篷记录导出为带筛选表头的 Excel 文件。 */
export async function exportCloakRecords(records: CloakRecord[]) {
  const XLSX = await import('xlsx');
  const headers = [
    '所属项目',
    '代理线',
    '投放链接',
    '审核链接',
    '斗篷链接',
    '模式',
    '投放地区',
    '禁止空语言',
    '禁止PC',
    '禁止代理',
    'Google回填',
    '回填结果',
    '创建时间',
  ];
  const rows = records.map((record) => [
    record.projectName,
    record.agencyLineName,
    record.sourceUrl,
    record.reviewUrl,
    record.promotionUrl,
    MODE_LABELS[record.mode],
    record.countryLabel || record.country || '',
    record.blockedLanguage ? '开' : '关',
    record.blockedPc ? '开' : '关',
    record.blockedProxy ? '开' : '关',
    WRITEBACK_STATUS_LABELS[record.sheetWritebackStatus],
    record.sheetWritebackMessage || '',
    formatDateTime(record.createdAt),
  ]);
  const sheet = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  sheet['!cols'] = [24, 24, 52, 52, 52, 12, 18, 14, 12, 12, 16, 36, 22].map(
    (wch) => ({ wch }),
  );
  sheet['!autofilter'] = {
    ref: XLSX.utils.encode_range({
      e: { c: headers.length - 1, r: records.length },
      s: { c: 0, r: 0 },
    }),
  };
  sheet['!freeze'] = { xSplit: 0, ySplit: 1 };

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, '斗篷管理');
  XLSX.writeFileXLSX(
    workbook,
    `斗篷管理_${formatFileTimestamp(new Date())}.xlsx`,
  );
}
