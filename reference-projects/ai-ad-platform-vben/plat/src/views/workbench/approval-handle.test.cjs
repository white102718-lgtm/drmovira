const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

function getApplicationNotFoundGuard() {
  const source = readFileSync(join(__dirname, 'approval-handle.vue'), 'utf8');
  const script = source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const ast = ts.createSourceFile(
    'approval-handle.ts',
    script,
    ts.ScriptTarget.Latest,
    true,
  );
  const declaration = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) &&
      node.name?.text === 'isApplicationNotFound',
  );

  assert.ok(declaration, '应提供审批申请空状态判断函数');

  const { outputText } = ts.transpileModule(declaration.getText(ast), {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  });

  return new Function(`${outputText}; return isApplicationNotFound;`)();
}

test('审批申请仍在加载时不展示未找到状态', () => {
  const isApplicationNotFound = getApplicationNotFoundGuard();

  assert.equal(isApplicationNotFound(undefined, true), false);
});

test('审批申请加载完成且无数据时展示未找到状态', () => {
  const isApplicationNotFound = getApplicationNotFoundGuard();

  assert.equal(isApplicationNotFound(undefined, false), true);
});
