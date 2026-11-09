/* eslint-disable @typescript-eslint/no-non-null-assertion, unicorn/consistent-existence-index-check, unicorn/explicit-length-check, unicorn/no-array-callback-reference, unicorn/no-array-reduce, unicorn/no-nested-ternary, unicorn/numeric-separators-style */
type DemoRecord = Record<string, any>;

interface DemoRequestConfig {
  params?: DemoRecord;
  responseType?: string;
}

const now = '2026-08-18 15:30:00';

const channels: DemoRecord[] = [
  {
    activationFee: 680,
    belongTeam: 'Mpower',
    channelCode: 'MPSEA01',
    channelName: 'Mpower SEA 核心代理',
    channelShortName: 'MPower SEA',
    channelType: 1,
    createTime: '2026-01-08 10:20:00',
    id: '1001',
    loginUrl: 'https://www.tango-game.com/channel/mpsea01',
    paymentAddress: 'USDT-TRC20 · TQ8X...DEMO',
    putawayStatus: 1,
    rebateRate: 3.5,
    rechargeAmount: 86_000,
    remark: '东南亚主力渠道，支持 Meta 企业户与不限额户',
    serviceFee: 2.5,
    settlementCurrency: 'USD',
    settlementMethod: '预付实消',
    status: 1,
    tgGroupId: '-1001888001001',
    tgGroupName: 'AdPulse × MPower SEA',
    totalBalance: 3_824_050,
    totalByBalance: 21_600,
    totalByBalanceU: 3_020,
    totalConsumption: 47_759.5,
    usageStatus: '合作中',
  },
  {
    activationFee: 420,
    belongTeam: 'ZCLINK',
    channelCode: 'ZCUS02',
    channelName: 'ZCLINK 北美企业户',
    channelShortName: 'ZC North America',
    channelType: 1,
    createTime: '2026-02-16 09:10:00',
    id: '1002',
    loginUrl: 'https://partner.example.com/zc-us',
    paymentAddress: 'Bank Wire · Demo Commerce LLC',
    putawayStatus: 1,
    rebateRate: 2.8,
    rechargeAmount: 58_000,
    remark: '北美电商及游戏企业户，账期稳定',
    serviceFee: 3,
    settlementCurrency: 'USD',
    settlementMethod: '周结',
    status: 1,
    tgGroupId: '-1001888001002',
    tgGroupName: 'AdPulse × ZCLINK US',
    totalBalance: 2_116_000,
    totalByBalance: 8_800,
    totalByBalanceU: 1_240,
    totalConsumption: 31_870.2,
    usageStatus: '合作中',
  },
  {
    activationFee: 300,
    belongTeam: 'Firefly',
    channelCode: 'FFLATAM',
    channelName: 'Firefly 拉美号商',
    channelShortName: 'Firefly LATAM',
    channelType: 2,
    createTime: '2026-03-22 14:05:00',
    id: '1003',
    loginUrl: 'https://partner.example.com/firefly-latam',
    paymentAddress: 'USDT-TRC20 · TV7M...DEMO',
    putawayStatus: 2,
    rebateRate: 4.2,
    rechargeAmount: 42_500,
    remark: '巴西、墨西哥本地主体户，适合游戏发行',
    serviceFee: 4,
    settlementCurrency: 'U',
    settlementMethod: '日结',
    status: 1,
    tgGroupName: 'Firefly LATAM Support',
    totalBalance: 1_328_500,
    totalByBalance: 16_200,
    totalByBalanceU: 2_270,
    totalConsumption: 24_402.8,
    usageStatus: '合作中',
  },
  {
    activationFee: 520,
    belongTeam: 'Mpower',
    channelCode: 'MPEU04',
    channelName: 'Mpower 欧洲白名单户',
    channelShortName: 'MPower EU',
    channelType: 1,
    createTime: '2026-05-11 16:40:00',
    id: '1004',
    loginUrl: 'https://www.tango-game.com/channel/mpeu04',
    paymentAddress: 'USDT-ERC20 · 0x83...DEMO',
    putawayStatus: 0,
    rebateRate: 2,
    rechargeAmount: 28_000,
    remark: '欧洲合规素材专用，暂未上架',
    serviceFee: 3.8,
    settlementCurrency: 'USD',
    settlementMethod: '预充值',
    status: 1,
    totalBalance: 945_000,
    totalByBalance: 4_300,
    totalByBalanceU: 610,
    totalConsumption: 16_908.4,
    usageStatus: '测试中',
  },
  {
    activationFee: 180,
    belongTeam: 'ZCLINK',
    channelCode: 'ZCOLD05',
    channelName: 'ZCLINK 历史备用号商',
    channelShortName: 'ZC Legacy',
    channelType: 2,
    createTime: '2025-11-03 11:25:00',
    id: '1005',
    loginUrl: 'https://partner.example.com/zc-legacy',
    paymentAddress: '已停止结算',
    putawayStatus: 2,
    rebateRate: 0,
    rechargeAmount: 9_000,
    remark: '历史存量渠道，仅保留查询',
    serviceFee: 5,
    settlementCurrency: 'USD',
    settlementMethod: '预结算',
    status: 0,
    totalBalance: 185_000,
    totalByBalance: 2_100,
    totalByBalanceU: 295,
    totalConsumption: 8_615.75,
    usageStatus: '已停用',
  },
];

const accountTypes: DemoRecord[] = [
  { accountType: 'BM 不限额户', id: 'type-1' },
  { accountType: '企业户', id: 'type-2' },
  { accountType: '个人户', id: 'type-3' },
  { accountType: '白名单户', id: 'type-4' },
];

const accountNames = [
  'Starfall 印尼主投 01',
  'Starfall 泰国 AEO 02',
  'Orbit 越南扩量 03',
  'Pixel Quest 马来西亚 04',
  'Nova 菲律宾素材测试 05',
  'Starfall 新加坡高价值 06',
  'Orbit 印尼再营销 07',
  'Pixel Quest 泰国备用户 08',
  'Nova 越南冷启动 09',
  'Starfall SEA 备用 10',
  'Orbit 菲律宾主投 11',
  'Pixel Quest 印尼 DPA 12',
];

const accounts: DemoRecord[] = accountNames.map((accountName, index) => ({
  accountId: `ca-${index + 1}`,
  accountName,
  accountType: ['BM 不限额户', '企业户', '个人户', '白名单户'][index % 4],
  actualDeduction: 18_500 + index * 1_230,
  amountSpent: 248_000 + index * 31_500,
  assignTime:
    index % 3 === 0
      ? ''
      : `2026-08-${String(4 + index).padStart(2, '0')} 10:00:00`,
  balance: 185_000 + index * 17_600,
  belongTeam: index % 2 ? '全球发行部' : '增长一部',
  belongTeamId: index % 2 ? 'dept-2' : 'dept-1',
  bmFromFeishu: index % 2 ? 'BM-SEA-9002' : 'BM-SEA-9001',
  bmId: `BM-${88_000 + index}`,
  byBalance: 1_200 + index * 120,
  byBalanceU: 168 + index * 18,
  channelId: '1001',
  consumption: 1_620.5 + index * 263.75,
  createTime: `2026-07-${String(6 + index).padStart(2, '0')} 09:30:00`,
  fbAccountId: String(1_208_400_100_000 + index),
  openDate: `2026-07-${String(5 + index).padStart(2, '0')}`,
  openingBalance: 50 + (index % 3) * 25,
  operatorId: index % 3 === 0 ? '' : index % 2 ? 'u-102' : 'u-101',
  operatorName: index % 3 === 0 ? '' : index % 2 ? '赵优化' : '王投手',
  remainingSpendCap: 82_000 + index * 7_500,
  remark: index % 3 === 0 ? '待分配投手' : '演示账户，可测试状态与分配操作',
  status: index === 4 || index === 9 ? 2 : index === 7 ? 3 : 1,
  subjectName: index % 2 ? 'AdPulse Global Pte. Ltd.' : '星瀚互动科技有限公司',
  takeTime: `2026-08-18 ${String(8 + (index % 10)).padStart(2, '0')}:00:00`,
  timezone: index % 3 === 0 ? 'UTC+7' : index % 3 === 1 ? 'UTC+8' : 'UTC+9',
  usageStatus:
    index % 5 === 0 ? 0 : index % 5 === 4 ? 2 : index % 5 === 3 ? 3 : 1,
}));

for (let channelIndex = 1; channelIndex < channels.length; channelIndex += 1) {
  for (let index = 0; index < 3; index += 1) {
    const number = channelIndex * 10 + index;
    accounts.push({
      ...accounts[index],
      accountId: `ca-${number + 1}`,
      accountName: `${channels[channelIndex]!.channelShortName} 测试账户 ${index + 1}`,
      channelId: channels[channelIndex]!.id,
      fbAccountId: String(1_208_500_200_000 + number),
      subjectName:
        channelIndex % 2 ? 'AdPulse Global Pte. Ltd.' : '星瀚互动科技有限公司',
    });
  }
}

const rates: DemoRecord[] = [
  {
    channelId: '1001',
    createTime: '2026-01-08 10:20:00',
    effectiveDate: '2026-01-01',
    expiryDate: '2026-06-30',
    id: 'rate-1',
    rebateRate: 3,
    serviceFee: 3,
    status: 0,
    updateTime: '2026-06-20 12:00:00',
  },
  {
    channelId: '1001',
    createTime: '2026-07-01 09:00:00',
    effectiveDate: '2026-07-01',
    expiryDate: null,
    id: 'rate-2',
    rebateRate: 3.5,
    serviceFee: 2.5,
    status: 1,
    updateTime: '2026-07-01 09:00:00',
  },
  {
    channelId: '1002',
    createTime: '2026-02-16 09:10:00',
    effectiveDate: '2026-02-16',
    expiryDate: null,
    id: 'rate-3',
    rebateRate: 2.8,
    serviceFee: 3,
    status: 1,
    updateTime: '2026-02-16 09:10:00',
  },
];

const goods = new Map<string, DemoRecord>([
  [
    '1001',
    {
      channelId: '1001',
      goodsName: 'Meta SEA 企业广告账户',
      launchRegion: '东南亚,东亚',
      minBugLimit: 2,
      rebateRate: 3.5,
      remark: '开户后 24 小时内完成授权，请使用合规素材。',
      serviceFeeRatio: 2.5,
      stockNum: 86,
      timezone: 'UTC+7,UTC+8',
    },
  ],
  [
    '1002',
    {
      channelId: '1002',
      goodsName: 'Meta 北美企业白名单户',
      launchRegion: '北美',
      minBugLimit: 1,
      rebateRate: 2.8,
      remark: '需提前提交落地页与素材审核。',
      serviceFeeRatio: 3,
      stockNum: 32,
      timezone: 'UTC-8,UTC-5',
    },
  ],
]);

const pitchers = [
  {
    deptName: '增长一部',
    nickName: '王投手',
    userId: 'u-101',
    userName: 'wang.pitcher',
  },
  {
    deptName: '全球发行部',
    nickName: '赵优化',
    userId: 'u-102',
    userName: 'zhao.optimizer',
  },
  {
    deptName: '增长一部',
    nickName: '李媒介',
    userId: 'u-103',
    userName: 'li.media',
  },
];

function ok<T>(data?: T) {
  return { code: 200, data, msg: '操作成功' };
}

function table(rows: DemoRecord[], total = rows.length) {
  return { code: 200, msg: '查询成功', rows, total };
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function toText(value: unknown) {
  return String(value ?? '')
    .trim()
    .toLowerCase();
}

function paginate(items: DemoRecord[], params: DemoRecord = {}) {
  const pageNum = Math.max(1, Number(params.pageNum ?? 1));
  const pageSize = Math.max(1, Number(params.pageSize ?? 10));
  return {
    count: items.length,
    records: items.slice((pageNum - 1) * pageSize, pageNum * pageSize),
  };
}

function filteredChannels(params: DemoRecord = {}) {
  const keyword = toText(params.channelName);
  return channels.filter(
    (item) =>
      (!keyword ||
        toText(item.channelName).includes(keyword) ||
        toText(item.channelShortName).includes(keyword) ||
        toText(item.channelCode).includes(keyword)) &&
      (params.status === undefined ||
        params.status === '' ||
        String(item.status) === String(params.status)),
  );
}

function filteredAccounts(params: DemoRecord = {}) {
  const rawKeywords = Array.isArray(params.accountIds)
    ? params.accountIds
    : params.accountIds
      ? [params.accountIds]
      : [];
  const keywords = rawKeywords.map(toText).filter(Boolean);
  return accounts.filter((item) => {
    if (params.channelId && String(item.channelId) !== String(params.channelId))
      return false;
    if (params.accountType && item.accountType !== params.accountType)
      return false;
    if (
      params.status !== undefined &&
      params.status !== '' &&
      String(item.status) !== String(params.status)
    )
      return false;
    if (
      params.usageStatus !== undefined &&
      params.usageStatus !== '' &&
      String(item.usageStatus) !== String(params.usageStatus)
    )
      return false;
    if (
      params.belongTeamId &&
      String(item.belongTeamId) !== String(params.belongTeamId)
    )
      return false;
    if (
      params.operatorName &&
      !toText(item.operatorName).includes(toText(params.operatorName))
    )
      return false;
    if (params.bmId && !toText(item.bmId).includes(toText(params.bmId)))
      return false;
    if (
      params.subjectName &&
      !toText(item.subjectName).includes(toText(params.subjectName))
    )
      return false;
    if (
      params.balanceMin !== undefined &&
      Number(item.balance) < Number(params.balanceMin)
    )
      return false;
    if (
      params.balanceMax !== undefined &&
      Number(item.balance) > Number(params.balanceMax)
    )
      return false;
    if (
      params.consumptionMin !== undefined &&
      Number(item.consumption) < Number(params.consumptionMin)
    )
      return false;
    if (
      params.consumptionMax !== undefined &&
      Number(item.consumption) > Number(params.consumptionMax)
    )
      return false;
    if (
      keywords.length &&
      !keywords.includes(toText(item.fbAccountId).replace(/^act_/, ''))
    )
      return false;
    return true;
  });
}

function sum(items: DemoRecord[], field: string) {
  return items.reduce((total, item) => total + Number(item[field] ?? 0), 0);
}

function accountStats(items: DemoRecord[]) {
  return [
    'openingBalance',
    'byBalance',
    'byBalanceU',
    'consumption',
    'balance',
    'actualDeduction',
    'amountSpent',
    'remainingSpendCap',
  ].reduce<DemoRecord>((result, field) => {
    result[field] = sum(items, field);
    return result;
  }, {});
}

function blob(filename: string, rows: DemoRecord[]) {
  const columns = rows.length ? Object.keys(rows[0]!) : ['说明'];
  const csv = [
    columns.join(','),
    ...rows.map((row) =>
      columns.map((key) => JSON.stringify(row[key] ?? '')).join(','),
    ),
  ].join('\n');
  return new Blob([`\uFEFF${csv}`], {
    type: filename.endsWith('.xlsx')
      ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      : 'text/csv;charset=utf-8',
  });
}

async function wait<T>(value: T): Promise<T> {
  await new Promise((resolve) => globalThis.setTimeout(resolve, 90));
  return clone(value);
}

async function get(url: string, config: DemoRequestConfig = {}): Promise<any> {
  const params = config.params ?? {};
  if (url === '/fbad/channel/list')
    return wait(ok(paginate(filteredChannels(params), params)));
  if (url === '/fbad/channel/list/total') {
    const items = filteredChannels(params);
    return wait(
      ok({
        activationFee: sum(items, 'activationFee'),
        totalBalance: sum(items, 'totalBalance'),
        totalByBalance: sum(items, 'totalByBalance'),
        totalByBalanceU: sum(items, 'totalByBalanceU'),
        totalConsumption: sum(items, 'totalConsumption'),
      }),
    );
  }
  if (url === '/fbad/channel/type/list') {
    const grouped = accountTypes.map((type) => {
      const related = accounts.filter(
        (item) => item.accountType === type.accountType,
      );
      return {
        ...type,
        channelName: '全部渠道',
        channelType: 1,
        subjectName: related[0]?.subjectName ?? '-',
        totalConsumption: sum(related, 'consumption'),
        usageStatus: `${related.filter((item) => Number(item.usageStatus) === 1).length}/${related.length} 使用中`,
      };
    });
    return wait(ok(paginate(grouped, params)));
  }
  if (url === '/fbad/channel/rate/list') {
    return wait(
      table(
        rates.filter(
          (item) => String(item.channelId) === String(params.channelId),
        ),
      ),
    );
  }
  if (url === '/fbad/channel/accountType/list') return wait(ok(accountTypes));
  if (url === '/fbad/task/pitcherList')
    return wait(ok(paginate(pitchers, params)));
  if (url === '/system/user/deptTree') {
    return wait(
      ok([
        {
          id: 'dept-1',
          label: '增长一部',
          children: [{ id: 'dept-1-1', label: 'SEA 投放组' }],
        },
        {
          id: 'dept-2',
          label: '全球发行部',
          children: [{ id: 'dept-2-1', label: '北美增长组' }],
        },
        { id: 'dept-3', label: '媒介资源中心' },
      ]),
    );
  }
  if (url.startsWith('/fbad/channelAccount/accountCountStats/')) {
    const channelId = decodeURIComponent(url.split('/').at(-1) ?? '');
    const items = accounts.filter(
      (item) => String(item.channelId) === channelId,
    );
    return wait(
      ok({
        activeCount: items.filter((item) => Number(item.status) === 1).length,
        allCount: items.length,
        closedCount: items.filter((item) => Number(item.status) === 2).length,
        idleCount: items.filter((item) => !item.operatorId).length,
        recycledCount: items.filter((item) => Number(item.usageStatus) === 3)
          .length,
        stopCount: items.filter((item) => Number(item.usageStatus) === 2)
          .length,
        unusedCount: items.filter((item) => Number(item.usageStatus) === 0)
          .length,
        usingCount: items.filter((item) => Number(item.usageStatus) === 1)
          .length,
      }),
    );
  }
  if (url.startsWith('/fbad/channel/goods/getByChannelId/')) {
    const channelId = decodeURIComponent(url.split('/').at(-1) ?? '');
    return wait(ok(goods.get(channelId) ?? null));
  }
  if (url === '/fbad/fbStatsCampaign/campaignSpend') {
    const accountId = String(params.accountId ?? '');
    const records = Array.from({ length: 4 }, (_, index) => ({
      campaignId: `${accountId || '1208400100000'}-${index + 1}`,
      campaignName: [
        'SEA_AEO_RewardHook',
        'SEA_Broad_Value',
        'SEA_Retarget_7D',
        'SEA_Creative_Test',
      ][index],
      returnAmount: 180 + index * 73.5,
      spendAmount: 620.25 + index * 286.4,
    }));
    return wait(ok(paginate(records, params)));
  }
  if (url === '/fbad/channelAccount/importTemplate') {
    return blob('渠道账户导入模板.xlsx', [
      { accountId: '1208400100999', accountType: '企业户' },
    ]);
  }
  if (/^\/fbad\/channel\/[^/]+$/.test(url)) {
    const id = decodeURIComponent(url.split('/').at(-1) ?? '');
    return wait(ok(channels.find((item) => String(item.id) === id) ?? null));
  }
  return wait(ok());
}

async function post(
  url: string,
  data: DemoRecord = {},
  _config: DemoRequestConfig = {},
): Promise<any> {
  if (url === '/fbad/channel') {
    channels.unshift({
      ...data,
      createTime: now,
      id: String(1000 + channels.length + 1),
      putawayStatus: 0,
      totalBalance: 0,
      totalConsumption: 0,
    });
    return wait(ok());
  }
  if (url === '/fbad/channel/rate') {
    rates.push({
      ...data,
      createTime: now,
      id: `rate-${rates.length + 1}`,
      status: 1,
      updateTime: now,
    });
    return wait(ok());
  }
  if (url === '/fbad/channel/accountType') {
    accountTypes.push({ ...data, id: `type-${accountTypes.length + 1}` });
    return wait(ok());
  }
  if (url === '/fbad/channelAccount/list') {
    const items = filteredAccounts(data);
    const pageNum = Math.max(1, Number(data.pageNum ?? 1));
    const pageSize = Math.max(1, Number(data.pageSize ?? 10));
    return wait(
      table(
        items.slice((pageNum - 1) * pageSize, pageNum * pageSize),
        items.length,
      ),
    );
  }
  if (url === '/fbad/channelAccount/statistics')
    return wait(ok(accountStats(filteredAccounts(data))));
  if (url === '/fbad/channelAccount/batchCreateAccount') {
    for (const [index, item] of (data.accountList ?? []).entries()) {
      const accountId = String(item.accountId);
      if (accounts.some((account) => String(account.fbAccountId) === accountId))
        continue;
      accounts.unshift({
        ...accounts[0],
        accountId: `ca-demo-${Date.now()}-${index}`,
        accountName: `新导入账户 ${accountId.slice(-6)}`,
        accountType: item.accountType,
        channelId: String(data.channelId),
        fbAccountId: accountId,
        operatorId: '',
        operatorName: '',
        remark: '通过批量导入新增的演示账户',
        usageStatus: 0,
      });
    }
    return wait(ok());
  }
  if (url === '/fbad/channelAccount/importData') return wait(ok([]));
  if (url === '/fbad/channelAccount/export')
    return blob('渠道账户数据.xlsx', filteredAccounts(data));
  if (url === '/fbad/channel/goods') {
    goods.set(String(data.channelId), { ...data });
    return wait(ok());
  }
  if (url === '/fbad/channel/goods/putaway') {
    const channel = channels.find(
      (item) => String(item.id) === String(data.channelId),
    );
    if (channel) channel.putawayStatus = Number(data.putawayStatus);
    return wait(ok());
  }
  return wait(ok());
}

async function put(url: string, data: DemoRecord = {}): Promise<any> {
  if (url === '/fbad/channel') {
    const target = channels.find((item) => String(item.id) === String(data.id));
    if (target) Object.assign(target, data);
    return wait(ok());
  }
  if (url === '/fbad/channel/rate') {
    const target = rates.find((item) => String(item.id) === String(data.id));
    if (target) Object.assign(target, data, { updateTime: now });
    return wait(ok());
  }
  if (url === '/fbad/channelAccount') {
    const target = accounts.find(
      (item) => String(item.accountId) === String(data.accountId),
    );
    if (target) Object.assign(target, data);
    return wait(ok());
  }
  if (url === '/fbad/channelAccount/assignPitcher') {
    const pitcher = pitchers.find(
      (item) => String(item.userId) === String(data.operatorId),
    );
    accounts
      .filter((item) =>
        (data.channelAccountIds ?? [])
          .map(String)
          .includes(String(item.accountId)),
      )
      .forEach((item) =>
        Object.assign(item, {
          assignTime: now,
          operatorId: String(data.operatorId),
          operatorName: pitcher?.nickName ?? pitcher?.userName ?? '演示投手',
          usageStatus: 1,
        }),
      );
    return wait(ok());
  }
  return wait(ok());
}

async function remove(url: string): Promise<any> {
  if (url.startsWith('/fbad/channel/accountType/')) {
    const id = decodeURIComponent(url.split('/').at(-1) ?? '');
    const index = accountTypes.findIndex((item) => String(item.id) === id);
    if (index >= 0) accountTypes.splice(index, 1);
    return wait(ok());
  }
  if (url.startsWith('/fbad/channelAccount/')) {
    const id = decodeURIComponent(url.split('/').at(-1) ?? '');
    const index = accounts.findIndex((item) => String(item.accountId) === id);
    if (index >= 0) accounts.splice(index, 1);
    return wait(ok());
  }
  if (/^\/fbad\/channel\/[^/]+$/.test(url)) {
    const id = decodeURIComponent(url.split('/').at(-1) ?? '');
    const index = channels.findIndex((item) => String(item.id) === id);
    if (index >= 0) channels.splice(index, 1);
    return wait(ok());
  }
  return wait(ok());
}

export const demoChannelManagementClient = {
  delete: remove,
  get,
  post,
  put,
};
