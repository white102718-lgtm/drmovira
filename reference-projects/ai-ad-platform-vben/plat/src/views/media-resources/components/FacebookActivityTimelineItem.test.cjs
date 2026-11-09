const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

const componentPath = join(__dirname, 'FacebookActivityTimelineItem.vue');
const source = readFileSync(componentPath, 'utf8');
const script = source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];

function getFunction(functionName, dependencyNames = [], dependencies = []) {
  const ast = ts.createSourceFile(
    'FacebookActivityTimelineItem.ts',
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

test('Facebook 操作分类使用明确中文名称', () => {
  const labels = {
    ACCOUNT: '账户',
    ACCESS: '权限',
    AD: '广告',
    AD_SET: '广告组',
    AUDIENCE: '受众',
    BILLING: '支付与额度',
    CAMPAIGN: '广告系列',
    CREATIVE: '素材',
    DELIVERY: '投放',
    OTHER: '其他',
  };
  const categoryLabel = getFunction(
    'categoryLabel',
    ['categoryLabels'],
    [labels],
  );

  assert.equal(categoryLabel('ACCOUNT'), '账户');
  assert.equal(categoryLabel('BILLING'), '支付与额度');
  assert.equal(categoryLabel(undefined), '其他');
});

test('缺失的摘要值展示为未设置', () => {
  const displayValue = getFunction('displayValue');

  assert.equal(displayValue(null), '未设置');
  assert.equal(displayValue(''), '未设置');
  assert.equal(displayValue('等待支付'), '等待支付');
});

test('空前后值不作为字段变化展示', () => {
  const hasDisplayValue = getFunction('hasDisplayValue');
  const hasChange = getFunction(
    'hasChange',
    ['hasDisplayValue'],
    [hasDisplayValue],
  );

  assert.equal(hasChange({ before: null, after: null }), false);
  assert.equal(hasChange({ before: '使用中', after: '等待支付' }), true);
});

test('组件直接展示前后值并保留原始数据兜底', () => {
  assert.match(source, /item\.before/);
  assert.match(source, /item\.after/);
  assert.match(source, /Meta 未提供可识别的变更字段/);
  assert.match(source, /查看原始数据/);
  assert.match(source, /v-if="visibleSummaryItems\.length"/);
  assert.match(source, /v-if="event\.actorName"/);
  assert.match(source, /v-if="event\.objectName \|\| event\.objectId"/);
  assert.match(source, /break-words/);
  assert.match(source, /sm:grid-cols-\[112px_minmax\(0,1fr\)\]/);
});
