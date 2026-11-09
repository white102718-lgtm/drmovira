const { readFileSync } = require('node:fs');
const { resolve, dirname } = require('node:path');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const ts = require('typescript');

/** 直接加载实际领域代码，用内存 HTTP 替身验证读写，不连接迁移数据库。 */
function load(relative, stubs = {}, cache = new Map()) {
  const filename = resolve(__dirname, relative);
  if (cache.has(filename)) return cache.get(filename);
  const source = readFileSync(filename, 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  });
  const module = { exports: {} };
  cache.set(filename, module.exports);
  new Function('require', 'module', 'exports', outputText)(
    (id) => {
      if (Object.hasOwn(stubs, id)) return stubs[id];
      if (id.startsWith('.'))
        return load(resolve(dirname(filename), `${id}.ts`), stubs, cache);
      throw new Error(`未声明的外部依赖：${id}`);
    },
    module,
    module.exports,
  );
  return module.exports;
}

const baseLine = {
  id: '2',
  name: '历史代理线',
  platform: 'facebook',
  projectId: '1',
  optimizerId: '3',
  optimizerName: '原优化师',
  optimizerStatus: 0,
  autoRun: false,
  enabled: true,
  isSend: false,
  deliveryUrl: '',
  pixelName: '',
  objective: '',
  packageName: '',
  packageType: '',
  pageId: '',
  updatedAt: '',
};

test('历史停用优化师不在候选列表时，编辑提交仍保留 ID 和原姓名', () => {
  const { withHistoricalOptimizer, selectedOptimizer } = load(
    '../agency-line/optimizer.ts',
  );
  const options = withHistoricalOptimizer(
    [{ value: '4', name: '启用人员', label: '启用人员' }],
    baseLine,
  );
  assert.match(options[0].label, /已停用/);
  assert.deepEqual(selectedOptimizer('3', options), {
    optimizerId: '3',
    optimizerName: '原优化师',
  });
  assert.deepEqual(selectedOptimizer(undefined, options), {
    optimizerId: undefined,
    optimizerName: '',
  });
  assert.deepEqual(selectedOptimizer('4', options), {
    optimizerId: '4',
    optimizerName: '启用人员',
  });
  assert.equal(withHistoricalOptimizer([], undefined).length, 0);
  assert.doesNotMatch(
    withHistoricalOptimizer([], { ...baseLine, optimizerStatus: undefined })[0]
      .label,
    /停用/,
  );
  assert.throws(() => selectedOptimizer('999', []), /不能|尚未加载/);
});

test('正式创建、列表、详情和编辑清空通过同一接口保存 NULL', async () => {
  let record = { ...baseLine };
  const calls = [];
  const client = {
    post: async (url, body) => {
      calls.push(url);
      record = { ...record, ...body.agencyLine };
      return record;
    },
    put: async (url, body) => {
      calls.push(url);
      record = { ...record, ...body };
      return record;
    },
    get: async (url) =>
      url.endsWith('/2') ? record : { items: [record], total: 1 },
  };
  const { HttpAgencyLineAdapter } = load('../agency-line/adapters/http.ts', {
    '#/api/request': { mainBackendClient: client },
  });
  const adapter = new HttpAgencyLineAdapter();
  const created = await adapter.create({
    requestId: 'test',
    input: { ...baseLine, optimizerId: undefined, optimizerName: '' },
  });
  assert.equal(created.optimizerName, '');
  assert.equal(record.optimizerId, null);
  assert.equal(record.optimizerName, null);
  await adapter.save({
    ...baseLine,
    optimizerId: undefined,
    optimizerName: '',
  });
  assert.equal(record.optimizerId, null);
  assert.equal(record.optimizerName, null);
  assert.equal((await adapter.get('2')).optimizerId, undefined);
  assert.equal((await adapter.list()).items[0].optimizerName, '');
  assert.deepEqual(calls, ['/project/agency-lines', '/project/agency-lines/2']);
});

test('批量导入允许未分配，姓名无 ID 和未知媒体仍拒绝', () => {
  const { parseAgencyLineImportRows } = load('../agency-line/bulk-import.ts');
  const result = parseAgencyLineImportRows([
    { 代理线: '未分配', 投放平台: 'facebook' },
    { 代理线: 'Kwai主数据', 投放平台: 'kwai' },
  ]);
  assert.equal(result.errors.length, 0);
  assert.equal(result.rows.length, 2);
  assert.equal(result.rows[0].input.optimizerName, '');
  assert.ok(
    parseAgencyLineImportRows([
      { 代理线: '非法', 投放平台: 'facebook', 优化师: '只有姓名' },
    ]).errors.length,
  );
  assert.ok(
    parseAgencyLineImportRows([{ 代理线: '非法', 投放平台: 'unknown' }]).errors
      .length,
  );
});

test('产品长度按 UTF-16 校验，986 原文和 2000 边界均可保存', () => {
  const { validateProductInfo } = load('./validation.ts');
  for (const value of [
    '中'.repeat(986),
    '中'.repeat(2000),
    '😀'.repeat(1000),
  ]) {
    assert.doesNotThrow(() => validateProductInfo(value));
  }
  for (const value of ['中'.repeat(2001), '😀'.repeat(1000) + '中', ' \n\t']) {
    assert.throws(() => validateProductInfo(value));
  }
});

test('项目原文、三媒体、多人关系和 KPI 比较符完整往返', async () => {
  let stored;
  const client = {
    put: async (_url, input) => {
      stored = structuredClone(input);
      return stored;
    },
    get: async () => structuredClone(stored),
  };
  const { HttpProjectAdapter } = load('./adapters/http.ts', {
    '#/api/request': { mainBackendClient: client },
    '#/domain/agency-line': { agencyLineService: {} },
  });
  const { ProjectService } = load('./service.ts');
  const service = new ProjectService(new HttpProjectAdapter());
  const productInfo = ' \n' + '中'.repeat(979) + '😀\n  ';
  assert.equal(productInfo.length, 986);
  const input = {
    id: '1',
    productInfo,
    platforms: ['facebook', 'tiktok', 'kwai'],
    serviceFeePercent: 9,
    amName: '第一人',
    amUserId: '9',
    amUsers: [
      { userId: '9', userName: '第一人' },
      { userId: '10', userName: '第二人' },
    ],
    dataSpecialists: [
      { userId: '10', userName: '第二人' },
      { userId: '9', userName: '第一人' },
    ],
    projectType: 'other',
    responsibleTeam: 'MP投放部',
    status: 'pending',
    kpiRequirements: [{ metric: 'CPP', comparator: '<', target: 9 }],
  };
  await service.save(input);
  assert.deepEqual(await service.get('1'), input);
  await service.save({ ...input, dataSpecialists: [] });
  assert.deepEqual(stored.dataSpecialists, []);
});

test('Kwai 主数据不能进入广告预检或发布适配器', async () => {
  let calls = 0;
  const { AdPublishingService } = load('../ad-publishing/service.ts');
  const service = new AdPublishingService({
    preflight: () => {
      calls++;
    },
    publish: () => {
      calls++;
    },
  });
  for (const platform of ['kwai', 'unknown']) {
    await assert.rejects(service.preflight({ platform }), /不支持/);
    await assert.rejects(
      service.publish({ platform }, { passed: true }),
      /不支持/,
    );
  }
  assert.equal(calls, 0);
});

test('执行真实编辑表单提交：选项缺席保留历史 ID，再次清空提交为空', async () => {
  const source = readFileSync(
    resolve(
      __dirname,
      '../../views/fusion/projects/components/AgencyLineCreateDrawer.vue',
    ),
    'utf8',
  );
  const script = source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const ast = ts.createSourceFile(
    'drawer.ts',
    script,
    ts.ScriptTarget.Latest,
    true,
  );
  const declaration = ast.statements.find(
    (node) => ts.isFunctionDeclaration(node) && node.name.text === 'submitForm',
  );
  const { outputText } = ts.transpileModule(declaration.getText(ast), {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  });
  const { selectedOptimizer, withHistoricalOptimizer } = load(
    '../agency-line/optimizer.ts',
  );
  const saved = [];
  const state = {
    formRef: { value: { validate: async () => {} } },
    selectedProject: { value: undefined },
    formState: { ...baseLine, deliveryUrl: 'https://example.com/edited' },
    selectedOptimizer,
    displayedOptimizerOptions: { value: withHistoricalOptimizer([], baseLine) },
    saving: { value: false },
    props: { editingLine: baseLine },
    agencyLineService: {
      save: async (input) => {
        saved.push(input);
        return input;
      },
    },
    message: {
      success() {},
      error(text) {
        throw new Error(text);
      },
    },
    emit() {},
    isFormValidationError: () => false,
  };
  const submit = new Function(
    ...Object.keys(state),
    `${outputText}; return submitForm;`,
  )(...Object.values(state));
  await submit();
  assert.equal(saved[0].optimizerId, '3');
  assert.equal(saved[0].optimizerName, '原优化师');
  assert.equal(saved[0].projectId, '1');
  state.formState.optimizerId = undefined;
  await submit();
  assert.equal(saved[1].optimizerId, undefined);
  assert.equal(saved[1].optimizerName, '');
  assert.equal(state.saving.value, false);
});
