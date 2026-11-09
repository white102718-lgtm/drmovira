const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { createRequire } = require('node:module');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const XLSX = createRequire(join(__dirname, '../../../package.json'))('xlsx');
const { outputText } = ts.transpileModule(
  readFileSync(join(__dirname, 'delivery-items.ts'), 'utf8'),
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
);
const api = {};
new Function('exports', outputText)(api);
const item = () => ({
  ...api.emptyDeliveryItem(),
  type: 'PWA',
  pixelName: '像素',
  pixelId: '9007199254740993',
  token: 'REDACTED_REFERENCE_SECRET',
  testCode: 'code',
  agencyLineName: '代理线',
  agencyLineId: '21',
  deliveryUrl: 'https://example.com',
  operatorId: '11',
});

test('同一投手可分配多行，斗篷链接允许为空', () => {
  assert.equal(api.validateDeliveryItems([item(), item()]), '');
});

test('代理线匹配系统记录并保存稳定 ID', () => {
  const rows = [
    { ...item(), agencyLineName: ' 代理线 ', agencyLineId: undefined },
  ];
  const result = api.matchDeliveryAgencyLines(rows, [
    { id: '21', name: '代理线' },
  ]);
  assert.equal(result[0].agencyLineId, '21');
  assert.equal(result[0].agencyLineName, '代理线');
  assert.equal(rows[0].agencyLineId, undefined);
});
test('导入拒绝未匹配和重名代理线，并定位错误行', () => {
  assert.throws(
    () => api.matchDeliveryAgencyLines([item()], []),
    /第 1 行.*未匹配/,
  );
  assert.throws(
    () =>
      api.matchDeliveryAgencyLines(
        [item()],
        [
          { id: '21', name: '代理线' },
          { id: '22', name: '代理线' },
        ],
      ),
    /第 1 行.*重名/,
  );
  assert.ok(
    api.validateDeliveryItems([{ ...item(), agencyLineId: undefined }]),
  );
});
test('正式提交拒绝缺失明细、投手、像素 ID', () => {
  assert.ok(api.validateDeliveryItems([]));
  assert.match(
    api.validateDeliveryItems([{ ...item(), operatorId: '' }]),
    /投手/,
  );
  assert.match(
    api.validateDeliveryItems([{ ...item(), pixelId: '' }]),
    /像素 ID/,
  );
});
test('错误定位到行号且不回显令牌', () => {
  assert.equal(
    api.validateDeliveryItems([
      item(),
      { ...item(), token: 'x'.repeat(10001) },
    ]),
    '第 2 行：Token最多 10000 个字符',
  );
});
function workbook(pixelId = '9007199254740993') {
  const book = XLSX.utils.book_new();
  for (const name of ['一', '二'])
    XLSX.utils.book_append_sheet(
      book,
      XLSX.utils.aoa_to_sheet([
        api.deliveryItemFields.map(([, label]) =>
          label === '投手 ID' ? '投手' : `${label}*`,
        ),
        [
          'PWA',
          '像素',
          pixelId,
          'test-token',
          'code',
          '代理线',
          'https://example.com',
          '11',
          '',
        ],
      ]),
      name,
    );
  return book;
}
test('XLSX 多工作表汇总，保留超长文本 ID，接受截图表头', () => {
  const book = XLSX.read(
    XLSX.write(workbook(), { type: 'buffer', bookType: 'xlsx' }),
    { type: 'buffer' },
  );
  const rows = api.parseDeliveryWorkbook(book, XLSX.utils);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].pixelId, '9007199254740993');
});

test('旧渠道表头不能当成代理线导入', () => {
  const book = workbook();
  for (const sheet of Object.values(book.Sheets)) sheet.F1.v = '渠道名称';
  assert.throws(() => api.parseDeliveryWorkbook(book, XLSX.utils), /完整表头/);
  assert.ok(
    api.validateDeliveryItems([
      { ...item(), agencyLineId: undefined, channelId: '21' },
    ]),
  );
});
test('拒绝精度已不安全的数值 ID', () => {
  assert.throws(
    () => api.parseDeliveryWorkbook(workbook(9007199254740992), XLSX.utils),
    /可能已丢失精度/,
  );
});
test('CSV 引号内逗号和长 ID 正确读取', () => {
  const csv =
    api.deliveryItemFields.map(([, label]) => label).join(',') +
    '\nPWA,"像素,一",9007199254740993,test-token,code,代理线,https://example.com,11,';
  const rows = api.parseDeliveryWorkbook(
    XLSX.read(csv, { type: 'string', raw: true }),
    XLSX.utils,
  );
  assert.equal(rows[0].pixelName, '像素,一');
  assert.equal(rows[0].pixelId, '9007199254740993');
});
