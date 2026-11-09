// 使用仓库已有 TypeScript 编译器和 Node 测试运行器，不新增测试依赖。
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');

/** 仅替换传输依赖，执行实际领域模块与 API 模块。 */
function loadSource(path, mocks) {
  const source = readFileSync(path, 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const exports = {};
  new Function('require', 'exports', outputText)((name) => {
    if (!(name in mocks)) throw new Error(`未声明测试依赖 ${name}`);
    return mocks[name];
  }, exports);
  return exports;
}

function domain({ demo = false, api = {}, lines = {}, project = {} } = {}) {
  return loadSource(join(__dirname, 'operating-detail.ts'), {
    '#/api/fusion/mode': { isFusionDemoMode: () => demo },
    '#/api/project-operating': api,
    '#/domain/agency-line': { agencyLineService: lines },
    './index': { projectService: project },
  });
}

test('正式状态变更只调用项目状态接口，去重且不调用旧广告配置', async () => {
  const calls = [];
  const service = domain({
    api: { changeProjectAgencyLineStatus: (...args) => calls.push(args) },
  });
  await service.setProjectAgencyLineStatus('123', ['2', '2', '3'], 'stopped');
  assert.deepEqual(calls, [['123', ['2', '3'], 'stopped']]);
  await assert.rejects(service.setProjectAgencyLineStatus('123', [], 'active'));
  await assert.rejects(
    service.setProjectAgencyLineStatus('123', ['2'], 'invalid'),
  );
  await assert.rejects(
    service.setProjectAgencyLineStatus('123', Array(101).fill('2'), 'active'),
  );
});

test('演示已完成任务排除媒介任务后分页', async () => {
  const service = domain({
    demo: true,
    project: {
      getOperatingOverview: async () => ({
        completedTasks: [
          { id: '1', kind: 'media' },
          { id: '2', kind: 'delivery' },
          { id: '3', kind: 'material' },
        ],
      }),
    },
  });
  const result = await service.listCompletedProjectTasks('p1', 2, 1);
  assert.equal(result.total, 2);
  assert.deepEqual(result.items, [{ id: '3', kind: 'material' }]);
});

test('正式任务查询保留项目和分页参数', async () => {
  const service = domain({
    api: { getCompletedProjectTasks: async (...args) => args },
  });
  assert.deepEqual(await service.listCompletedProjectTasks('p1', 3, 10), [
    'p1',
    3,
    10,
  ]);
});

test('导出读取全部页且始终限制当前项目', async () => {
  const calls = [];
  const service = domain({
    lines: {
      list: async (query) => {
        calls.push(query);
        return { items: [{ id: String(query.page) }], total: 2 };
      },
    },
  });
  assert.equal((await service.listAllProjectAgencyLines('p1')).length, 2);
  assert.deepEqual(
    calls.map((query) => query.projectId),
    ['p1', 'p1'],
  );
  assert.deepEqual(
    calls.map((query) => query.page),
    [1, 2],
  );
});

test('导出不接受中途空页导致静默缺失', async () => {
  const service = domain({
    lines: { list: async () => ({ items: [], total: 5 }) },
  });
  await assert.rejects(service.listAllProjectAgencyLines('p1'), /发生变化/);
});

test('CSV保留中文状态并转义公式、逗号与引号', () => {
  const csv = domain().agencyLinesCsv([
    {
      optimizerName: '=SUM(1,2)',
      platform: 'facebook',
      name: '甲"乙',
      pixelName: '',
      status: 'stopped',
    },
  ]);
  assert.ok(csv.startsWith('\uFEFF'));
  assert.ok(csv.includes('"\'=SUM(1,2)"'));
  assert.ok(csv.includes('"甲""乙"'));
  assert.ok(csv.includes('"已停投"'));
});

test('API使用项目级路径和PATCH请求，不改旧代理线API', async () => {
  const calls = [];
  const api = loadSource(join(__dirname, '../../api/project-operating.ts'), {
    './request': {
      mainBackendClient: {
        get: (...args) => calls.push(['get', ...args]),
        request: (...args) => calls.push(['request', ...args]),
      },
    },
  });
  await api.changeProjectAgencyLineStatus('p/1', ['2'], 'active');
  await api.getCompletedProjectTasks('p/1', 2, 10);
  assert.equal(calls[0][1], '/project/projects/p%2F1/agency-line-status');
  assert.equal(calls[0][2].method, 'PATCH');
  assert.deepEqual(calls[1][2].params, { page: 2, pageSize: 10 });
});
