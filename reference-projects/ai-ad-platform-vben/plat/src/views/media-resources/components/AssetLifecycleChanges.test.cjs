const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const ts = require('typescript');

function getFunction(functionName, dependencyNames = [], dependencies = []) {
  const source = readFileSync(
    join(__dirname, 'AssetLifecycleDrawer.vue'),
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

test('清空值展示为未设置', () => {
  const format = getFunction('changeValuePrimary');
  assert.equal(format({ display: '' }), '未设置');
  assert.equal(format(undefined), '未设置');
});

test('选项名称为主信息且 ID 为次级信息', () => {
  const primary = getFunction('changeValuePrimary');
  const secondary = getFunction('changeValueSecondary');
  const value = {
    display: '华东团队',
    references: [{ id: '9007199254740993', name: '华东团队' }],
  };
  assert.equal(primary(value), '华东团队');
  assert.equal(secondary(value), '9007199254740993');
});

test('新增、导入、绑定和同步来源均显示明确中文', () => {
  const labels = {
    BATCH_EDIT: '批量编辑',
    CHANNEL_IMPORT: '渠道导入',
    CHANNEL_MANUAL: '渠道手工绑定',
    EXCEL_BATCH: 'Excel 批量处理',
    EXCEL_IMPORT: 'Excel 导入',
    FEISHU_SYNC: '飞书同步',
    MANUAL_CREATE: '手工新增',
    MANUAL_EDIT: '编辑抽屉',
    MONGO_SYNC: 'Mongo 同步',
    OPEN_ACCOUNT: '开户办理',
    SPREADSHEET_CREATE: '电子表格新增',
  };
  const format = getFunction(
    'updateSourceLabel',
    ['updateSourceLabels'],
    [labels],
  );
  assert.equal(format('MANUAL_EDIT'), '编辑抽屉');
  assert.equal(format('EXCEL_IMPORT'), 'Excel 导入');
  assert.equal(format('EXCEL_BATCH'), 'Excel 批量处理');
  assert.equal(format('CHANNEL_MANUAL'), '渠道手工绑定');
  assert.equal(format('OPEN_ACCOUNT'), '开户办理');
  assert.equal(format('FEISHU_SYNC'), '飞书同步');
  assert.equal(format('MONGO_SYNC'), 'Mongo 同步');
});

test('入库与资料更新只展示表单可见字段并使用业务标签', () => {
  const filterLifecycleChanges = getFunction('filterLifecycleChanges');
  const changes = [
    { fieldKey: 'assetType' },
    { fieldKey: 'assetSubtype' },
    { fieldKey: 'assetName' },
    { fieldKey: 'assetCode' },
    { fieldKey: 'phoneNumber', fieldLabel: '旧电话号码' },
    { fieldKey: 'link', fieldLabel: '旧链接' },
    { fieldKey: 'status', fieldLabel: '旧库存状态' },
    { fieldKey: 'remark', fieldLabel: '旧备注' },
  ];
  const visibleFields = [
    { fieldKey: 'phoneNumber', label: '电话号码' },
    { fieldKey: 'link', label: 'TG 链接' },
    { fieldKey: 'status', label: '库存状态' },
    { fieldKey: 'remark', label: '备注' },
  ];

  for (const eventType of ['STOCKED', 'UPDATED']) {
    const displayed = filterLifecycleChanges(
      { eventType, changes },
      visibleFields,
    );
    assert.deepEqual(
      displayed.map((change) => change.fieldKey),
      ['phoneNumber', 'link', 'status', 'remark'],
    );
    assert.deepEqual(
      displayed.map((change) => change.fieldLabel),
      ['电话号码', 'TG 链接', '库存状态', '备注'],
    );
  }
});

test('同名字段保留后出现的业务值，且不改变敏感字段脱敏状态', () => {
  const filterLifecycleChanges = getFunction('filterLifecycleChanges');
  const redactedAfter = { display: '已设置', redacted: true };
  const displayed = filterLifecycleChanges(
    {
      eventType: 'UPDATED',
      changes: [
        { after: { display: '派生名称' }, fieldKey: 'assetName' },
        { after: { display: 'IP 业务名称' }, fieldKey: 'assetName' },
        { after: redactedAfter, fieldKey: 'password' },
      ],
    },
    [
      { fieldKey: 'assetName', label: 'IP 名称' },
      { fieldKey: 'password', label: '密码' },
    ],
  );

  assert.equal(displayed.length, 2);
  assert.equal(displayed[0].fieldLabel, 'IP 名称');
  assert.equal(displayed[0].after.display, 'IP 业务名称');
  assert.equal(displayed[1].after, redactedAfter);
});

test('未知子类型和非资料事件保持原始审计字段', () => {
  const filterLifecycleChanges = getFunction('filterLifecycleChanges');
  const changes = [{ fieldKey: 'assetType' }, { fieldKey: 'assetName' }];

  assert.equal(
    filterLifecycleChanges({ eventType: 'STOCKED', changes }),
    changes,
  );
  assert.equal(
    filterLifecycleChanges({ eventType: 'ASSIGNED', changes }, []),
    changes,
  );
});

test('资产列表打开生命周期时传入当前资产子类型', () => {
  const source = readFileSync(
    join(__dirname, 'AssetManagementPanel.vue'),
    'utf8',
  );

  assert.match(source, /lifecycleAssetSubtype\.value = asset\.subtype/);
  assert.match(source, /:asset-subtype="lifecycleAssetSubtype"/);
});

test('入库与资料更新事件共用紧凑箭头明细，旧入库事件不显示空占位', () => {
  const source = readFileSync(
    join(__dirname, 'AssetLifecycleDrawer.vue'),
    'utf8',
  );

  assert.match(
    source,
    /\['STOCKED', 'UPDATED'\]\.includes\(event\.eventType\)/,
  );
  assert.match(source, /lucide:arrow-right/);
  assert.match(source, /event\.eventType === 'STOCKED' \? '初始资料' : '变更'/);
  assert.match(
    source,
    /v-else-if="event\.eventType === 'UPDATED'"[^]*历史资料更新事件暂无字段明细/,
  );
});
