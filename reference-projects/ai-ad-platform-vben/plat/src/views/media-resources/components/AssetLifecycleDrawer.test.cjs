const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');
const dayjs = require('dayjs');

function getLifecycleFunction(
  functionName,
  dependencyNames = [],
  dependencies = [],
) {
  const source = readFileSync(
    join(__dirname, 'AssetLifecycleDrawer.vue'),
    'utf8',
  );
  const script = source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const ast = ts.createSourceFile(
    'AssetLifecycleDrawer.ts',
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

test('生命周期时间隐藏 ISO 分隔符和毫秒', () => {
  const formatLifecycleDateTime = getLifecycleFunction(
    'formatLifecycleDateTime',
    ['dayjs'],
    [dayjs],
  );

  assert.equal(
    formatLifecycleDateTime('2026-09-11T17:45:10.302'),
    '2026-09-11 17:45:10',
  );
});

test('生命周期时间缺失时展示占位符', () => {
  const formatLifecycleDateTime = getLifecycleFunction(
    'formatLifecycleDateTime',
    ['dayjs'],
    [dayjs],
  );

  assert.equal(formatLifecycleDateTime(undefined), '—');
});

test('生命周期资产状态使用账户列表一致的中文名称', () => {
  const assetStatusLabel = getLifecycleFunction('assetStatusLabel');

  assert.equal(assetStatusLabel('AVAILABLE'), '可用');
  assert.equal(assetStatusLabel('ASSIGNED'), '已分配');
  assert.equal(assetStatusLabel('RETURN_PENDING'), '待回收');
  assert.equal(assetStatusLabel('DISABLED'), '已停用');
});

test('生命周期消耗按币种保留两位小数', () => {
  const formatLifecycleMoney = getLifecycleFunction('formatLifecycleMoney');

  assert.equal(formatLifecycleMoney(1234.5, 'USD'), 'USD 1,234.50');
  assert.equal(formatLifecycleMoney(undefined, 'USD'), '—');
});
