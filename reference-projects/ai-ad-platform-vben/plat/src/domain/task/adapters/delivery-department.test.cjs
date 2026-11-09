// 使用现有 TypeScript 编译器和 Node 测试运行器验证真实详情投影，无需新增依赖。
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');

const { outputText } = ts.transpileModule(
  readFileSync(join(__dirname, 'task-detail.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
);
const moduleExports = {};
new Function('exports', outputText)(moduleExports);

function projectAllocation(teamCode, teamName) {
  return moduleExports.projectDeliveryTaskDetail(
    {
      task: { taskType: 'DELIVERY' },
      delivery: {},
      allocations: [{ teamCode, teamName, pwaLineCount: 2, h5LineCount: 1 }],
      platforms: [],
      taskFiles: [],
    },
    '项目',
  ).allocations[0];
}

test('部门 ID 与展示名称分别保留，同名部门不会混为同一团队', () => {
  const first = projectAllocation('9007199254740993', '投放部');
  const second = projectAllocation('9007199254740994', '投放部');
  assert.notEqual(first.team, second.team);
  assert.equal(first.teamName, '投放部');
  assert.equal(first.team, '9007199254740993');
  assert.equal(first.pwaCount, 2);
  assert.equal(first.h5Count, 1);
});

test('旧任务保留历史团队编码，不猜测其对应部门', () => {
  const row = projectAllocation('MP');
  assert.equal(row.team, 'MP');
  assert.equal(row.teamName, undefined);
});
