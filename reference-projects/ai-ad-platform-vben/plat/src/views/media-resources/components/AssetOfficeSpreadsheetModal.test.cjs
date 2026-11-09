const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

function getFunction(functionName, dependencyNames = [], dependencies = []) {
  const source = readFileSync(
    join(__dirname, 'AssetOfficeSpreadsheetModal.vue'),
    'utf8',
  );
  const script = source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const ast = ts.createSourceFile(
    'spreadsheet-modal.ts',
    script,
    ts.ScriptTarget.Latest,
    true,
  );
  const declaration = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) && node.name?.text === functionName,
  );
  assert.ok(declaration, `应提供 ${functionName} 函数`);
  const { outputText } = ts.transpileModule(declaration.getText(ast), {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  });
  return new Function(
    ...dependencyNames,
    `${outputText}; return ${functionName};`,
  )(...dependencies);
}

const splitMultipleValue = getFunction('splitMultipleValue');
const calculateWorksheetCapacity = getFunction('calculateWorksheetCapacity');
const displayCellValue = getFunction(
  'displayCellValue',
  ['optionMaps'],
  [
    () => ({
      displayByValue: new Map([
        ['user-1', '贺松'],
        ['user-2', '王珏'],
        ['ACTIVE', '已启用'],
      ]),
    }),
  ],
);
const parseCellValue = getFunction(
  'parseCellValue',
  ['dayjs', 'optionMaps', 'splitMultipleValue'],
  [
    () => undefined,
    () => ({
      valueByDisplay: new Map([
        ['贺松', 'user-1'],
        ['李四', 'user-2'],
      ]),
    }),
    splitMultipleValue,
  ],
);

test('多使用人初始值序列化为 Univer 合法的 JSON 数组', () => {
  assert.equal(
    displayCellValue(
      { values: { userIds: ['user-1', 'user-2'] } },
      { key: 'userIds', multiple: true, type: 'user' },
    ),
    '["贺松","王珏"]',
  );
});

test('单个多选值仍使用 JSON 数组格式', () => {
  assert.equal(
    displayCellValue(
      { values: { userIds: ['user-1'] } },
      { key: 'userIds', multiple: true, type: 'user' },
    ),
    '["贺松"]',
  );
});

test('空多选值和单选值保持原有显示格式', () => {
  assert.equal(
    displayCellValue(
      { values: { userIds: [] } },
      { key: 'userIds', multiple: true, type: 'user' },
    ),
    '',
  );
  assert.equal(
    displayCellValue(
      { values: { status: 'ACTIVE' } },
      { key: 'status', type: 'select' },
    ),
    '已启用',
  );
});

test('解析 Univer 多选生成的 JSON 数组字符串', () => {
  assert.deepEqual(splitMultipleValue('["贺松","李四"]'), ['贺松', '李四']);
});

test('解析真实数组并清理空值和重复值', () => {
  assert.deepEqual(splitMultipleValue([' 贺松 ', '', '李四', '贺松']), [
    '贺松',
    '李四',
  ]);
});

test('继续兼容常用分隔符和换行粘贴', () => {
  assert.deepEqual(splitMultipleValue('贺松、李四,王五；赵六\n钱七'), [
    '贺松',
    '李四',
    '王五',
    '赵六',
    '钱七',
  ]);
});

test('非数组 JSON 和空值按普通文本兼容', () => {
  assert.deepEqual(splitMultipleValue('[]'), []);
  assert.deepEqual(splitMultipleValue('贺松'), ['贺松']);
  assert.deepEqual(splitMultipleValue(undefined), []);
});

test('多选显示名称转换为稳定用户 ID', () => {
  assert.deepEqual(
    parseCellValue('["贺松","李四"]', {
      label: '使用人',
      multiple: true,
      type: 'user',
    }),
    { value: ['user-1', 'user-2'] },
  );
});

test('未知用户只提示完整选项名称', () => {
  assert.deepEqual(
    parseCellValue('["贺松","不存在"]', {
      label: '使用人',
      multiple: true,
      type: 'user',
    }),
    {
      error: '使用人包含无法识别的选项“不存在”',
      value: [],
    },
  );
});

test('expands rows for all loaded data and keeps one creation row', () => {
  assert.deepEqual(
    calculateWorksheetCapacity({
      allowCreate: true,
      currentColumnCount: 20,
      currentRowCount: 1000,
      dataRowCount: 3039,
      fieldCount: 15,
    }),
    { columnCount: 20, rowCount: 3041 },
  );
});

test('does not shrink the default worksheet capacity for small datasets', () => {
  assert.deepEqual(
    calculateWorksheetCapacity({
      allowCreate: true,
      currentColumnCount: 20,
      currentRowCount: 1000,
      dataRowCount: 10,
      fieldCount: 15,
    }),
    { columnCount: 20, rowCount: 1000 },
  );
});

test('expands columns for fields and the hidden technical id column', () => {
  assert.deepEqual(
    calculateWorksheetCapacity({
      allowCreate: false,
      currentColumnCount: 20,
      currentRowCount: 1000,
      dataRowCount: 10,
      fieldCount: 24,
    }),
    { columnCount: 25, rowCount: 1000 },
  );
});

test('does not reserve a creation row when creation is disabled', () => {
  assert.deepEqual(
    calculateWorksheetCapacity({
      allowCreate: false,
      currentColumnCount: 20,
      currentRowCount: 1000,
      dataRowCount: 3039,
      fieldCount: 15,
    }),
    { columnCount: 20, rowCount: 3040 },
  );
});
