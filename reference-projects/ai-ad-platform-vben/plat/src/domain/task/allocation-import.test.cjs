const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');
const source = ts.transpileModule(
  readFileSync(join(__dirname, 'allocation-import.ts'), 'utf8'),
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  },
);
const exported = {};
new Function('exports', source.outputText)(exported);
const departments = [
  { id: '9007199254740993', deptName: '投放部', status: 1 },
  { id: '2', deptName: '设计部', status: 1 },
  { id: '3', deptName: '停用部', status: 0 },
];
const users = [
  { id: '10', displayName: '张三', username: 'zhangsan', status: 1 },
  { id: '11', displayName: '李四', status: 0 },
];
const parse = (text, existing = [], deps = departments) =>
  exported.parseAllocationImport(text, deps, users, existing);

test('Excel 表头、CRLF、空行及账号匹配，保留大整数 ID', () => {
  const result = parse(
    '部门名称或ID\t负责人姓名或ID\tPWA线路数\tH5线路数\r\n投放部\tzhangsan\t2\t0\r\n\r\n2\t10\t0\t3',
  );
  assert.deepEqual(result.errors, []);
  assert.equal(result.rows.length, 2);
  assert.equal(result.rows[0].team, '9007199254740993');
  assert.equal(result.rows[1].line, 4);
});

test('重复部门与已有分配冲突均报错且不修改输入', () => {
  const existing = ['2'];
  assert.equal(
    parse(
      '投放部\t张三\t1\t0\n投放部\t张三\t1\t0\n设计部\t张三\t1\t0',
      existing,
    ).errors.length,
    2,
  );
  assert.deepEqual(existing, ['2']);
});

test('重名要求 ID，停用、未知部门及负责人拒绝导入', () => {
  assert.match(
    parse(
      '投放部\t张三\t1\t0',
      [],
      [...departments, { id: '4', deptName: '投放部', status: 1 }],
    ).errors[0],
    /重名/,
  );
  for (const row of [
    '停用部\t张三\t1\t0',
    '不存在\t张三\t1\t0',
    '投放部\t李四\t1\t0',
    '投放部\t不存在\t1\t0',
  ])
    assert.equal(parse(row).errors.length, 1);
});

test('负数、小数、空数量、科学计数、零合计及溢出全部拒绝', () => {
  for (const count of [
    '-1',
    '1.5',
    '',
    '1e3',
    '2147483648',
    '9007199254740993',
  ])
    assert.equal(parse(`投放部\t张三\t${count}\t0`).errors.length, 1);
  assert.equal(parse('投放部\t张三\t0\t0').errors.length, 1);
  assert.equal(parse('投放部\t张三\t2147483647\t1').errors.length, 1);
});

test('空内容、只有表头、列数错误和超过 200 行均有反馈', () => {
  for (const text of [
    '',
    '部门\t负责人\tPWA线路数\tH5线路数',
    '投放部,张三,1,0',
    Array(201).fill('投放部\t张三\t1\t0').join('\n'),
  ])
    assert.equal(parse(text).errors.length, 1);
});
