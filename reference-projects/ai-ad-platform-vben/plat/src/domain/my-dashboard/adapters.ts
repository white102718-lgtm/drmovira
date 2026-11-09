import type { AdDashboardListResult } from '../ad-dashboard';
import type {
  DashboardAccounts,
  DashboardAnalyzeQuery,
  DashboardDateQuery,
  DashboardHosting,
  DashboardHostingQuery,
  DashboardObjectQuery,
  DashboardOverview,
  DashboardTrend,
  MyDashboardAdapter,
} from './types';

import {
  analyzeMyDashboardApi,
  getMyDashboardHostingApi,
  saveMyDashboardHostingApi,
} from '#/api/my-dashboard-agent';
import { adpulseClient } from '#/api/request';

import { MockAdDashboardAdapter } from '../ad-dashboard/adapters/mock';
import {
  normalizeAdDashboardRow,
  summarizeAdDashboardRows,
} from '../ad-dashboard/normalize';
import { getAdDashboardSchema } from '../ad-dashboard/schema';

const endpoint = '/dashboard/my-dashboard';

function dateParams(query: DashboardDateQuery) {
  return { end_date: query.endDate, start_date: query.startDate };
}

function normalizeAgentCtr(value: null | number) {
  if (value === null) return null;
  return Math.abs(value) <= 1 ? value * 100 : value;
}

/** 指挥台查询与托管配置；失败直接反馈，不回退到演示数据。 */
export class HttpMyDashboardAdapter implements MyDashboardAdapter {
  accounts(query: DashboardDateQuery) {
    return adpulseClient.get<DashboardAccounts>(`${endpoint}/accounts`, {
      params: dateParams(query),
      skipErrorMessage: true,
    });
  }

  async analyze(query: DashboardAnalyzeQuery, signal?: AbortSignal) {
    const result = await analyzeMyDashboardApi(query, signal);
    const accountId = query.account_id?.replace(/^act_/, '');
    if (
      accountId &&
      result.fact.account_id?.replace(/^act_/, '') !== accountId
    ) {
      throw new Error('智能体返回的账户与当前选择不一致，请重新查询。');
    }
    return {
      ...result,
      fact: {
        ...result.fact,
        objects: result.fact.objects.map((row) => ({
          ...row,
          // 契约兼容比率和百分数，仅规范单位，不推算判断与下一步。
          ctr: normalizeAgentCtr(row.ctr),
        })),
      },
    };
  }

  getHosting() {
    return getMyDashboardHostingApi();
  }

  async list(query: DashboardObjectQuery): Promise<AdDashboardListResult> {
    const schema = getAdDashboardSchema(query.category);
    const sort = schema.fields.find(
      (field) => field.key === query.sortField && field.sortable,
    );
    const response = await adpulseClient.get<{
      data: Record<string, unknown>[];
      pagination: { page: number; page_size: number; total: number };
    }>(`${endpoint}/objects/${query.category}`, {
      params: {
        account_id: query.accountId,
        end_date: query.endDate,
        name: query.name,
        page: query.page,
        page_size: query.pageSize,
        sort_by: sort?.sortKey,
        sort_order: query.sortOrder,
        start_date: query.startDate,
        status: query.status,
      },
      skipErrorMessage: true,
    });
    const items = response.data.map((row, index) =>
      normalizeAdDashboardRow(row, schema, index),
    );
    let dataCutoff = '';
    for (const row of items) {
      const updatedAt = String(row.updatedAt ?? '');
      if (updatedAt > dataCutoff) dataCutoff = updatedAt;
    }
    return {
      dataCutoff,
      items,
      page: response.pagination.page,
      pageSize: response.pagination.page_size,
      schema,
      // 旧指标适配器只汇总当前页，页面明确标注，不能当成全量汇总。
      summaryRows: summarizeAdDashboardRows(items, schema),
      total: response.pagination.total,
    };
  }

  overview(query: DashboardDateQuery) {
    return adpulseClient.get<DashboardOverview>(`${endpoint}/overview`, {
      params: dateParams(query),
      skipErrorMessage: true,
    });
  }

  saveHosting(query: DashboardHostingQuery) {
    return saveMyDashboardHostingApi(query);
  }

  trend(query: DashboardDateQuery) {
    return adpulseClient.get<DashboardTrend>(`${endpoint}/trend`, {
      params: dateParams(query),
      skipErrorMessage: true,
    });
  }
}

/** 仅用于显式演示模式，复用演示对象，不参与正式接口降级。 */
export class MockMyDashboardAdapter implements MyDashboardAdapter {
  private readonly objects = new MockAdDashboardAdapter();

  async accounts(): Promise<DashboardAccounts> {
    const { items } = await this.objects.list({
      category: 'account',
      pageSize: 100,
    });
    return {
      activity: {
        active: items.length,
        attention: 0,
        idle: 0,
        rate: items.length > 0 ? 100 : 0,
        scopeLabel: '演示账户',
        total: items.length,
        unknown: 0,
      },
      items: items.map((row) => ({
        accountStatus: '1',
        activity: 'active',
        cpa:
          typeof row.registrationCost === 'number'
            ? row.registrationCost
            : null,
        ctr: typeof row.ctr === 'number' ? row.ctr : null,
        currency: row.currency,
        id: row.id,
        name: String(row.name ?? row.id),
        registrations: Number(row.registrations ?? 0),
        spend: Number(row.spend ?? 0),
      })),
    };
  }

  async analyze(_query: DashboardAnalyzeQuery): Promise<never> {
    // 演示对象不能冒充智能体真实判断，也不能在演示模式调用正式服务。
    throw new Error('演示模式不提供智能体分析，请切换到正式数据环境。');
  }

  async getHosting(): Promise<DashboardHosting> {
    return { enabled: false, feishu_bound: false };
  }

  list(query: DashboardObjectQuery) {
    // 演示数据使用固定日期，只在此去掉真实日期筛选。
    return this.objects.list({
      ...query,
      endDate: undefined,
      id: query.category === 'account' ? query.accountId : undefined,
      startDate: undefined,
    });
  }

  async overview(query: DashboardDateQuery): Promise<DashboardOverview> {
    const { items } = await this.accounts();
    return {
      dataCutoff: '',
      dateBasis: 'account_local',
      previousEndDate: query.startDate,
      previousStartDate: query.startDate,
      summaries: [...new Set(items.map((row) => row.currency))].map(
        (currency) => {
          const rows = items.filter((row) => row.currency === currency);
          const spend = rows.reduce((sum, row) => sum + row.spend, 0);
          const registrations = rows.reduce(
            (sum, row) => sum + row.registrations,
            0,
          );
          return {
            cpa: registrations ? spend / registrations : null,
            cpaChange: null,
            ctr: null,
            currency,
            registrations,
            registrationsChange: null,
            spend,
            spendChange: null,
          };
        },
      ),
    };
  }

  async saveHosting(_query: DashboardHostingQuery): Promise<never> {
    throw new Error('演示模式不能保存真实托管设置。');
  }

  async trend(query: DashboardDateQuery): Promise<DashboardTrend> {
    const { summaries } = await this.overview(query);
    return {
      cumulative: false,
      granularity: 'day',
      series: summaries.map((summary) => ({
        currency: summary.currency,
        points: [{ ...summary, label: query.endDate }],
      })),
    };
  }
}
