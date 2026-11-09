import type {
  AdDashboardCategory,
  AdDashboardDataType,
  AdDashboardField,
  AdDashboardSchema,
} from './types';

// 与后端 dashboard.py 的聚合排序白名单及旧版面板保持一致。
const SORTABLE_METRIC_FIELDS = new Set([
  '花费金额',
  '覆盖人数',
  '展示次数',
  '点击数',
  '点击率',
  '点击成本',
  '链接点击数',
  '落地页浏览',
  '落地页成本',
  '去重链接点击数',
  '去重点击成本',
  '千展',
  '安装数',
  '注册数',
  '注册转化率',
  '注册成本',
  '订阅数',
  '订阅率',
  '订阅成本',
  '订阅价值',
  '购物数',
  '购物率',
  '购物成本',
  '购物价值',
  '购物roas',
  '频次',
  '3d频次',
  '5d频次',
  '7d频次',
  '预算',
  '户余额',
  '户限额',
  '单日限额',
  '对话数',
  '对话成本',
  '1d安装数',
  '1d注册数',
  '1d注册成本',
  '1d订阅数',
  '1d订阅成本',
  '1d订阅价值',
  '1d购物数',
  '1d购物成本',
  '1d购物价值',
  '1d购物roas',
  'bi注册数',
  'bi首充人数',
  'bi首充金额',
  'bi首充成本',
  'bi首次roas',
  'bi首次arppu',
  'bi注册成本',
]);

interface FieldOptions {
  emptyText?: string;
  filterable?: boolean;
  fixed?: 'left' | 'right';
  sortable?: boolean;
  sortKey?: string;
  sourceKey?: string;
  summarizable?: boolean;
}

function field(
  key: string,
  label: string,
  dataType: AdDashboardDataType,
  width: number,
  options: FieldOptions = {},
): AdDashboardField {
  const sourceKey = options.sourceKey ?? label;
  const sortKey = options.sortKey ?? sourceKey;
  // 表头与请求共同使用白名单，防止名称、状态等字段触发后端排序校验错误。
  const sortable =
    options.sortable !== false && SORTABLE_METRIC_FIELDS.has(sortKey);
  return {
    dataType,
    emptyText: options.emptyText ?? '—',
    filterable:
      options.filterable ?? ['identifier', 'status', 'text'].includes(dataType),
    fixed: options.fixed,
    key,
    label,
    sortable,
    sortKey: sortable ? sortKey : undefined,
    sourceKey,
    summarizable: options.summarizable ?? false,
    width,
  };
}

const nameField = () =>
  field('name', '名称', 'text', 180, {
    fixed: 'left',
    sourceKey: 'name',
  });
const idField = () => field('id', 'ID', 'identifier', 168, { sourceKey: 'id' });

export const adDashboardSchemas: Record<
  AdDashboardCategory,
  AdDashboardSchema
> = {
  department: {
    category: 'department',
    fields: [
      nameField(),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('runningBudget', '在跑预算', 'currency', 112, {
        summarizable: true,
      }),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('stoppedSpend', '已关停消耗', 'currency', 118, {
        summarizable: true,
      }),
      field('runningSpend', '在跑消耗', 'currency', 112, {
        summarizable: true,
      }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      // 部门 ID 由数据归一化保留用于下钻，不加入展示列。
    ],
    label: '部门',
    legacyTabKey: 'department',
    sheetName: '部门',
  },
  project: {
    category: 'project',
    fields: [
      nameField(),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('runningBudget', '在跑预算', 'currency', 112, {
        summarizable: true,
      }),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('stoppedSpend', '已关停消耗', 'currency', 118, {
        summarizable: true,
      }),
      field('runningSpend', '在跑消耗', 'currency', 112, {
        summarizable: true,
      }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      idField(),
    ],
    label: '项目',
    legacyTabKey: 'game_platform',
    sheetName: '项目',
  },
  platform: {
    category: 'platform',
    fields: [
      nameField(),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('runningBudget', '在跑预算', 'currency', 112, {
        summarizable: true,
      }),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('stoppedSpend', '已关停消耗', 'currency', 118, {
        summarizable: true,
      }),
      field('runningSpend', '在跑消耗', 'currency', 112, {
        summarizable: true,
      }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      idField(),
    ],
    label: '投放平台',
    legacyTabKey: 'ad_platform',
    sheetName: '投放平台',
  },
  channel: {
    category: 'channel',
    fields: [
      nameField(),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('runningBudget', '在跑预算', 'currency', 112, {
        summarizable: true,
      }),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('stoppedSpend', '已关停消耗', 'currency', 118, {
        summarizable: true,
      }),
      field('runningSpend', '在跑消耗', 'currency', 112, {
        summarizable: true,
      }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      idField(),
    ],
    label: '渠道',
    legacyTabKey: 'channel',
    sheetName: '渠道',
  },
  agencyLine: {
    category: 'agencyLine',
    fields: [
      nameField(),
      field('placerName', '投手', 'text', 126),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('runningBudget', '在跑预算', 'currency', 112, {
        summarizable: true,
      }),
      field('budgetRange', '预算上下限', 'text', 126),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('stoppedSpend', '已关停消耗', 'currency', 118, {
        summarizable: true,
      }),
      field('runningSpend', '在跑消耗', 'currency', 112, {
        summarizable: true,
      }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      idField(),
    ],
    label: '代理线',
    legacyTabKey: 'agent_line',
    sheetName: '代理线',
  },
  account: {
    category: 'account',
    fields: [
      nameField(),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('runningBudget', '在跑预算', 'currency', 112, {
        summarizable: true,
      }),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('statusText', '状态', 'status', 102, {
        sourceKey: 'account_status',
      }),
      field('accountAttribute', '账户属性', 'text', 144, {
        sortable: false,
        sourceKey: 'account_attribute',
      }),
      field('balance', '户余额', 'currency', 104, { summarizable: true }),
      field('spendingCap', '户限额', 'currency', 104),
      field('dailyCap', '单日限额', 'currency', 104),
      field('stoppedSpend', '已关停消耗', 'currency', 118, {
        summarizable: true,
      }),
      field('runningSpend', '在跑消耗', 'currency', 112, {
        summarizable: true,
      }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      idField(),
    ],
    label: '账户',
    legacyTabKey: 'account_id',
    sheetName: '账户',
  },
  pixel: {
    category: 'pixel',
    fields: [
      field('name', '像素名称', 'text', 180, {
        fixed: 'left',
        sourceKey: 'name',
      }),
      field('pixelId', '像素ID', 'identifier', 168, {
        sourceKey: 'id',
      }),
      field('adId', '广告ID', 'identifier', 168, { sortable: false }),
      field('adName', '广告名称', 'text', 180, { sortable: false }),
      field('accountName', '关联账户', 'text', 164, {
        sourceKey: '账户名称',
      }),
      field('accountId', '账户ID', 'identifier', 168),
      field('channelName', '渠道', 'text', 136),
      field('departmentName', '部门', 'text', 126),
      field('projectName', '项目', 'text', 136, { sourceKey: '游戏平台' }),
      field('agencyLineName', '代理线', 'text', 164),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('createdAt', '创建时间', 'datetime', 126),
      field('statusText', '投放状态', 'status', 102, {
        sourceKey: 'effective_status',
      }),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('runningSpend', '在跑消耗', 'currency', 112, {
        summarizable: true,
      }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      idField(),
    ],
    label: '像素',
    legacyTabKey: 'pixel_id',
    sheetName: '像素ID',
  },
  campaign: {
    category: 'campaign',
    fields: [
      nameField(),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('createdAt', '创建时间', 'datetime', 126),
      field('statusText', '投放状态', 'status', 102, {
        sourceKey: 'effective_status',
      }),
      field('budget', '预算', 'currency', 104, { summarizable: true }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('cpm', '千展', 'currency', 88),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('uniqueLinkClicks', '去重链接点击数', 'number', 126, {
        summarizable: true,
      }),
      field('uniqueCpc', '去重点击成本', 'currency', 118),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('frequency', '频次', 'number', 82),
      field('frequency3d', '3d频次', 'number', 88),
      field('frequency5d', '5d频次', 'number', 88),
      field('frequency7d', '7d频次', 'number', 88),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      field('accountName', '账户名', 'text', 164),
      field('accountId', '账户ID', 'identifier', 168),
      field('channelName', '渠道', 'text', 136),
      field('departmentName', '部门', 'text', 126),
      field('projectName', '项目', 'text', 136),
      idField(),
    ],
    label: '广告系列',
    legacyTabKey: 'campaign_id',
    sheetName: '广告系列',
  },
  adSet: {
    category: 'adSet',
    fields: [
      nameField(),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('createdAt', '创建时间', 'datetime', 126),
      field('statusText', '投放状态', 'status', 102, {
        sourceKey: 'effective_status',
      }),
      field('budget', '预算', 'currency', 104, { summarizable: true }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('cpm', '千展', 'currency', 88),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('uniqueLinkClicks', '去重链接点击数', 'number', 126, {
        summarizable: true,
      }),
      field('uniqueCpc', '去重点击成本', 'currency', 118),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('frequency', '频次', 'number', 82),
      field('frequency3d', '3d频次', 'number', 88),
      field('frequency5d', '5d频次', 'number', 88),
      field('frequency7d', '7d频次', 'number', 88),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      idField(),
    ],
    label: '广告组',
    legacyTabKey: 'ad_set_id',
    sheetName: '广告组',
  },
  ad: {
    category: 'ad',
    fields: [
      nameField(),
      field('spend', '花费金额', 'currency', 112, { summarizable: true }),
      field('updatedAt', '最新时间', 'datetime', 126),
      field('createdAt', '创建时间', 'datetime', 126),
      field('statusText', '投放状态', 'status', 102, {
        sourceKey: 'effective_status',
      }),
      field('reach', '覆盖人数', 'number', 104, { summarizable: true }),
      field('impressions', '展示次数', 'number', 104, {
        summarizable: true,
      }),
      field('cpm', '千展', 'currency', 88),
      field('clicks', '点击数', 'number', 90, { summarizable: true }),
      field('ctr', '点击率', 'percent', 92),
      field('cpc', '点击成本', 'currency', 102),
      field('linkClicks', '链接点击数', 'number', 108, {
        summarizable: true,
      }),
      field('uniqueLinkClicks', '去重链接点击数', 'number', 126, {
        summarizable: true,
      }),
      field('uniqueCpc', '去重点击成本', 'currency', 118),
      field('landingViews', '落地页浏览', 'number', 108, {
        summarizable: true,
      }),
      field('landingCost', '落地页成本', 'currency', 108),
      field('installs', '安装数', 'number', 90, { summarizable: true }),
      field('registrations', '注册数', 'number', 90, { summarizable: true }),
      field('registrationRate', '注册转化率', 'percent', 112),
      field('registrationCost', '注册成本', 'currency', 108),
      field('subscriptions', '订阅数', 'number', 90, { summarizable: true }),
      field('subscriptionRate', '订阅率', 'percent', 92),
      field('subscriptionCost', '订阅成本', 'currency', 108),
      field('subscriptionValue', '订阅价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchases', '购物数', 'number', 90, { summarizable: true }),
      field('purchaseRate', '购物率', 'percent', 92),
      field('purchaseCost', '购物成本', 'currency', 108),
      field('purchaseValue', '购物价值', 'currency', 108, {
        summarizable: true,
      }),
      field('purchaseRoas', '购物roas', 'number', 104),
      field('frequency', '频次', 'number', 82),
      field('frequency3d', '3d频次', 'number', 88),
      field('frequency5d', '5d频次', 'number', 88),
      field('frequency7d', '7d频次', 'number', 88),
      field('conversations', '对话数', 'number', 90, { summarizable: true }),
      field('conversationCost', '对话成本', 'currency', 108),
      field('uniqueName', 'unique_name', 'identifier', 154),
      field('pageId', '主页ID', 'identifier', 168),
      field('postId', '帖子ID', 'identifier', 168),
      field('originalPostCount', '原帖数量', 'number', 96, {
        summarizable: true,
      }),
      field('deliveryUrl', '投放链接', 'url', 220),
      field('accountId', '账户ID', 'identifier', 168),
      field('accountName', '账户名称', 'text', 164),
      field('departmentName', '部门', 'text', 126),
      field('projectName', '项目', 'text', 136),
      idField(),
    ],
    label: '广告',
    legacyTabKey: 'ad_id',
    sheetName: '广告',
  },
};

// 固定字段按业务维度定义，不随用户拖动或历史列配置改变；广告组预算仍参与横向滚动。
const summaryFixedKeys = ['name', 'spend', 'runningBudget', 'updatedAt'];
const objectFixedKeys = [
  'name',
  'spend',
  'updatedAt',
  'createdAt',
  'statusText',
];
const fixedKeysByCategory: Record<AdDashboardCategory, string[]> = {
  department: summaryFixedKeys,
  project: summaryFixedKeys,
  platform: summaryFixedKeys,
  channel: summaryFixedKeys,
  agencyLine: [
    'name',
    'placerName',
    'spend',
    'runningBudget',
    'budgetRange',
    'updatedAt',
  ],
  account: [...summaryFixedKeys, 'statusText', 'accountAttribute'],
  campaign: [...objectFixedKeys, 'budget'],
  adSet: objectFixedKeys,
  ad: objectFixedKeys,
  pixel: objectFixedKeys,
};

for (const schema of Object.values(adDashboardSchemas)) {
  const fixedKeys = fixedKeysByCategory[schema.category];
  const fixedFields = fixedKeys.flatMap((key) => {
    const item = schema.fields.find((candidate) => candidate.key === key);
    return item ? [{ ...item, fixed: 'left' as const }] : [];
  });
  schema.fields = [
    ...fixedFields,
    ...schema.fields.filter((item) => !fixedKeys.includes(item.key)),
  ];
  if (['campaign', 'adSet', 'ad'].includes(schema.category)) {
    const status = schema.fields.find((item) => item.key === 'statusText');
    if (status) status.width = 224;
  }
}

const deliveryEfficiencyMetricKeys = new Set([
  'cpc',
  'cpm',
  'ctr',
  'ecpm',
  'firstPurchaseCost',
  'firstPurchaseRate',
  'registrationCost',
  'registrationRate',
]);

// 首充沿用当前展示口径：成本 = 花费 / 购物数，转化率 = 购物数 / 注册数。
function deliveryEfficiencyFields() {
  return [
    field('ecpm', 'ECPM', 'currency', 102, { sortKey: '千展' }),
    field('cpc', '点击成本 CPC', 'currency', 112, { sortKey: '点击成本' }),
    field('registrationCost', '注册成本', 'currency', 108),
    field('firstPurchaseCost', '首充成本', 'currency', 108, {
      sortKey: '购物成本',
    }),
    field('ctr', '点击率 CTR', 'percent', 102, { sortKey: '点击率' }),
    field('registrationRate', '注册转化率', 'percent', 112),
    field('firstPurchaseRate', '首充转化率', 'percent', 112, {
      sortKey: '购物率',
    }),
  ];
}

for (const schema of Object.values(adDashboardSchemas)) {
  schema.fields = [
    ...schema.fields.filter(
      (item) => !deliveryEfficiencyMetricKeys.has(item.key),
    ),
    ...deliveryEfficiencyFields(),
  ];
}

const legacyCategoryAliases: Record<string, AdDashboardCategory> = {
  account: 'account',
  account_id: 'account',
  ad: 'ad',
  ad_id: 'ad',
  ad_set_id: 'adSet',
  adSet: 'adSet',
  agencyLine: 'agencyLine',
  agent_line: 'agencyLine',
  campaign: 'campaign',
  campaign_id: 'campaign',
  channel: 'channel',
  department: 'department',
  pixel: 'pixel',
  pixel_id: 'pixel',
  game: 'project',
  game_platform: 'project',
  platform: 'platform',
  ad_platform: 'platform',
  project: 'project',
};

export const adDashboardCategoryOrder: AdDashboardCategory[] = [
  'department',
  'project',
  'platform',
  'agencyLine',
  'channel',
  'account',
  'campaign',
  'adSet',
  'ad',
  'pixel',
];

export function resolveAdDashboardCategory(value?: null | string) {
  return value ? legacyCategoryAliases[value] : undefined;
}

export function getAdDashboardSchema(category: AdDashboardCategory) {
  return adDashboardSchemas[category];
}
