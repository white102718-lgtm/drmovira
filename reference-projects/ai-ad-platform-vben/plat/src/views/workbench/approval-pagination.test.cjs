const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

function loadPaginationHelpers() {
  const source = readFileSync(
    join(__dirname, 'approval-pagination.ts'),
    'utf8',
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const module = { exports: {} };
  new Function('exports', 'module', outputText)(module.exports, module);
  return module.exports;
}

test('changing page size resets the approval list to page one', () => {
  const { resolveApprovalPageChange } = loadPaginationHelpers();

  assert.deepEqual(resolveApprovalPageChange(10, 3, 50), {
    page: 1,
    pageSize: 50,
  });
});

test('changing only the page preserves the requested page', () => {
  const { resolveApprovalPageChange } = loadPaginationHelpers();

  assert.deepEqual(resolveApprovalPageChange(50, 3, 50), {
    page: 3,
    pageSize: 50,
  });
});

test('demo approvals use the selected page and page size', () => {
  const { paginateApprovalRecords } = loadPaginationHelpers();
  const records = Array.from({ length: 620 }, (_, index) => index + 1);

  for (const pageSize of [10, 20, 50, 100, 200, 500]) {
    assert.deepEqual(
      paginateApprovalRecords(records, 2, pageSize),
      records.slice(pageSize, pageSize * 2),
    );
  }
});

test('batch selection remains limited to one hundred records', () => {
  const { limitApprovalBatchRecords } = loadPaginationHelpers();
  const records = Array.from({ length: 500 }, (_, index) => index + 1);

  assert.deepEqual(
    limitApprovalBatchRecords(records, 100),
    records.slice(0, 100),
  );
});

test('过期请求序号不会被识别为当前响应', () => {
  const { isLatestApprovalRequest } = loadPaginationHelpers();

  assert.equal(isLatestApprovalRequest(2, 3), false);
  assert.equal(isLatestApprovalRequest(3, 3), true);
});
