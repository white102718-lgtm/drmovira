const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');

/** 执行实际页面成功回调，避免复制一份实现使回归测试失效。 */
function callback(overrides = {}) {
  const source = readFileSync(
    join(__dirname, '../../views/fusion/projects/index.vue'),
    'utf8',
  );
  const script = source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const ast = ts.createSourceFile(
    'index.ts',
    script,
    ts.ScriptTarget.Latest,
    true,
  );
  const declaration = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) &&
      node.name.text === 'handleAgencyLineCreated',
  );
  const { outputText } = ts.transpileModule(declaration.getText(ast), {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  });
  const state = {
    agencyLineRevisions: {},
    message: { success() {}, error() {}, warning() {} },
    loadAgencyLines: async () => {},
    refreshPage: async () => {},
    applyAgencyLineBindingsWithCompatibilityProjection: async () => {},
    ...overrides,
  };
  return {
    state,
    run: new Function(
      ...Object.keys(state),
      `${outputText}; return handleAgencyLineCreated;`,
    )(...Object.values(state)),
  };
}

test('已原子绑定的新代理线立即通知详情，不等待整页刷新也不重复绑定', async () => {
  let release;
  let binds = 0;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  const { state, run } = callback({
    refreshPage: () => pending,
    applyAgencyLineBindingsWithCompatibilityProjection: async () => {
      binds += 1;
    },
  });
  const operation = run({ id: 'line-1', projectId: 'p1', name: '新增' }, 'p1');
  assert.equal(state.agencyLineRevisions.p1, 1);
  assert.equal(binds, 0);
  release();
  await operation;
});

test('列表刷新失败不能阻断详情刷新或误报绑定失败', async () => {
  const errors = [];
  const warnings = [];
  const { state, run } = callback({
    refreshPage: async () => {
      throw new Error('列表超时');
    },
    message: {
      success() {},
      error: (value) => errors.push(value),
      warning: (value) => warnings.push(value),
    },
  });
  await run({ id: 'line-1', projectId: 'p1', name: '新增' }, 'p1');
  assert.equal(state.agencyLineRevisions.p1, 1);
  assert.equal(errors.length, 0);
  assert.equal(warnings.length, 1);
});

test('兼容接口未绑定时先绑定，成功后再通知详情', async () => {
  const { state, run } = callback({
    applyAgencyLineBindingsWithCompatibilityProjection: async (id) => {
      assert.equal(id, 'p1');
      assert.equal(state.agencyLineRevisions.p1, undefined);
    },
  });
  await run({ id: 'line-1', name: '新增' }, 'p1');
  assert.equal(state.agencyLineRevisions.p1, 1);
});

test('绑定失败不通知错误项目，仍刷新总代理线列表', async () => {
  let refreshed = 0;
  const { state, run } = callback({
    applyAgencyLineBindingsWithCompatibilityProjection: async () => {
      throw new Error('归属冲突');
    },
    loadAgencyLines: async () => {
      refreshed += 1;
    },
  });
  await run({ id: 'line-1', name: '新增' }, 'p1');
  assert.deepEqual(state.agencyLineRevisions, {});
  assert.equal(refreshed, 1);
});

test('缺少事件项目参数时使用创建响应的绑定项目；连续创建递增通知', async () => {
  const { state, run } = callback();
  await run({ id: 'line-1', projectId: 'p1', name: '新增' });
  await run({ id: 'line-2', projectId: 'p1', name: '新增二' });
  assert.equal(state.agencyLineRevisions.p1, 2);
});

test('未关联项目的创建不污染任何详情刷新信号', async () => {
  const { state, run } = callback();
  await run({ id: 'line-1', name: '未关联' });
  assert.deepEqual(state.agencyLineRevisions, {});
});
