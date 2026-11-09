// @ts-nocheck -- 仓库当前未向 plat 的生产类型检查暴露 Vitest 类型。
import ExcelJS from 'exceljs';
import { describe, expect, it } from 'vitest';
import * as XLSX from 'xlsx';

import { buildAssetWorkbook, formatAssetExportTimestamp } from './asset-export';

describe('asset export workbook', () => {
  it('formats export filenames with local time down to seconds', () => {
    expect(formatAssetExportTimestamp(new Date(2026, 8, 24, 17, 5, 9))).toBe(
      '2026-09-24_17-05-09',
    );
  });

  it('writes dropdowns through a hidden option sheet without changing import data', async () => {
    const content = await buildAssetWorkbook(
      '广告账户',
      [
        { key: 'accountId', label: '*账户ID' },
        {
          key: 'channelName',
          label: '所属渠道',
          selectOptions: ['渠道 A', '渠道 B', '渠道 A', '  '],
        },
        { key: 'usageUsers', label: '使用人' },
      ],
      [
        {
          accountId: '1001',
          channelName: '已停用历史渠道',
          usageUsers: '张三、李四',
        },
      ],
    );

    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.load(content);
    expect(workbook.worksheets.map((sheet) => sheet.name)).toEqual([
      '广告账户',
      '__asset_export_options',
    ]);
    expect(workbook.getWorksheet('__asset_export_options')?.state).toBe(
      'veryHidden',
    );
    expect(workbook.getWorksheet('广告账户')?.getCell('B2').value).toBe(
      '已停用历史渠道',
    );
    expect(
      workbook.getWorksheet('广告账户')?.getCell('B2').dataValidation,
    ).toMatchObject({
      allowBlank: true,
      formulae: ['AssetExportOptions_1'],
      showErrorMessage: true,
      type: 'list',
    });
    expect(
      workbook.getWorksheet('广告账户')?.getCell('C2').dataValidation.type,
    ).toBeUndefined();
    expect(
      workbook
        .getWorksheet('__asset_export_options')
        ?.getColumn(1)
        .values.slice(1),
    ).toEqual(['渠道 A', '渠道 B']);

    const parsed = XLSX.read(content, { type: 'array' });
    expect(parsed.SheetNames[0]).toBe('广告账户');
    expect(
      XLSX.utils.sheet_to_json(parsed.Sheets['广告账户']!, {
        defval: '',
        raw: false,
      }),
    ).toEqual([
      {
        '*账户ID': '1001',
        使用人: '张三、李四',
        所属渠道: '已停用历史渠道',
      },
    ]);
  });
});
