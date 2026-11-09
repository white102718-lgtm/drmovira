const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const assert = require('node:assert/strict');
const { describe, it } = require('node:test');
const ts = require('typescript');

function loadRouteStateHelpers() {
  const source = readFileSync(join(__dirname, 'list-route-state.ts'), 'utf8');
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

describe('list route state', () => {
  const { listRouteCodecs, parseListRouteState, serializeListRouteState } =
    loadRouteStateHelpers();
  const defaults = { enabled: false, keyword: '', tags: [] };

  it('恢复筛选和显式分页参数', () => {
    assert.deepEqual(
      parseListRouteState({
        defaults,
        pagination: { defaultPageSize: 20, pageSizes: [20, 50] },
        query: {
          enabled: '1',
          keyword: '广告账户',
          page: '3',
          page_size: '50',
          tags: ['facebook', 'google'],
        },
      }),
      {
        pagination: { page: 3, pageSize: 50 },
        state: {
          enabled: true,
          keyword: '广告账户',
          tags: ['facebook', 'google'],
        },
      },
    );
  });

  it('非法分页值回落到默认值', () => {
    assert.deepEqual(
      parseListRouteState({
        defaults,
        pagination: { defaultPageSize: 20, pageSizes: [20, 50] },
        query: { page: '-1', page_size: '999' },
      }).pagination,
      { page: 1, pageSize: 20 },
    );
  });

  it('写入状态时保留无关查询参数并始终输出分页', () => {
    assert.deepEqual(
      serializeListRouteState({
        currentQuery: { customerId: '42', keyword: 'old' },
        defaults,
        pagination: { defaultPageSize: 20 },
        paginationState: { page: 1, pageSize: 20 },
        state: defaults,
      }),
      {
        customerId: '42',
        page: '1',
        page_size: '20',
      },
    );
  });

  it('主 Tab 等导航字段可在默认值下仍显式写入', () => {
    assert.deepEqual(
      serializeListRouteState({
        currentQuery: {},
        defaults: { tab: 'all' },
        fields: { tab: { always: true } },
        state: { tab: 'all' },
      }),
      { tab: 'all' },
    );
  });

  it('支持多列表作用域和旧逗号数组链接', () => {
    const parsed = parseListRouteState({
      defaults,
      fields: { tags: { codec: listRouteCodecs.stringArray } },
      pagination: { defaultPageSize: 10 },
      query: {
        delivery_page: '2',
        delivery_page_size: '10',
        delivery_tags: 'facebook,google',
      },
      scope: 'delivery',
    });

    assert.deepEqual(parsed.pagination, { page: 2, pageSize: 10 });
    assert.deepEqual(parsed.state.tags, ['facebook', 'google']);
  });
});
