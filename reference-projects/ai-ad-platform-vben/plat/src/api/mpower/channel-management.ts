import type {
  MpowerBody,
  MpowerPageQuery,
  MpowerRecord,
  MpowerTable,
} from './types';

import { mainBackendClient } from '#/api/request';
import { getAdAccountAssetPage } from '#/api/main/ad-account-assets';
import { FULL_OPTION_PAGE_SIZE } from '#/constants/pagination';

export interface ChannelPage<T = MpowerRecord> {
  count: number;
  records: T[];
}

export interface ChannelRecord extends MpowerRecord {
  belongTeam?: string;
  channelCode?: string;
  channelName?: string;
  channelShortName?: string;
  channelType?: number | string;
  createTime?: string;
  id: number | string;
  loginUrl?: string;
  paymentAddress?: string;
  putawayStatus?: number;
  remark?: string;
  status?: number | string;
  tgGroupId?: number | string;
  tgGroupName?: string;
}

export interface ChannelOption {
  label: string;
  value: string;
}

export interface ChannelPaymentContext {
  channelId: string;
  channelName: string;
  channelYesterdayCost: number;
  paymentAddress: string;
}

export interface ChannelPeriodSpendQuery extends MpowerPageQuery {
  belongTeam?: string;
  endDate: string;
  startDate: string;
}

export interface ChannelPeriodSpendResult {
  items: Array<{
    channelId: string;
    totalConsumption: number | string;
  }>;
  page: number;
  pageSize: number;
  totalConsumption: number | string;
}

export interface AccountTypeRecord extends MpowerRecord {
  accountType: string;
  id: number | string;
}

export interface ChannelAccountRecord extends MpowerRecord {
  accountId: number | string;
  accountName?: string;
  accountType?: string;
  channelId?: number | string;
  fbAccountId?: number | string;
  operatorName?: string;
  status?: number | string;
  synced?: boolean;
  timezone?: number | string;
  usageStatus?: number | string;
}

export interface AdAccountOption {
  label: string;
  value: string;
}

/** 广告户申请办理时的可用渠道账户查询条件。 */
export interface AvailableChannelAccountQuery extends MpowerRecord {
  channelId: number | string;
}

function pageParams(params: MpowerPageQuery = {}) {
  const { fbadChannel, pageNum, tableType: _tableType, ...rest } = params;
  return {
    ...rest,
    channelName: params.channelName || fbadChannel || undefined,
    page: pageNum ?? 1,
  };
}

function body<T>(data: T): MpowerBody<T> {
  return { code: 200, data, msg: 'success' } as MpowerBody<T>;
}

export async function getChannelPage<T = ChannelRecord>(
  params: MpowerPageQuery = {},
): Promise<MpowerBody<ChannelPage<T>>> {
  const result: any = await mainBackendClient.get('/channels', {
    params: pageParams(params),
  });
  return body({ count: result.total, records: result.items });
}

/**
 * 获取资产归属等业务选择器使用的正常渠道，数据源与渠道管理列表一致。
 */
export async function getChannelOptions(): Promise<ChannelOption[]> {
  const response = await getChannelPage({
    pageNum: 1,
    pageSize: FULL_OPTION_PAGE_SIZE,
    status: '1',
  });
  return response.data.records
    .filter((channel) => Boolean(channel.channelName))
    .map((channel) => ({
      label: channel.channelName ?? String(channel.id),
      value: String(channel.id),
    }));
}

/**
 * 获取广告户申请与办理环节可开户的渠道分页。
 *
 * @remarks
 * MPower 的开户入口只展示正常且已上架的渠道商品。查询参数用于服务端过滤，
 * 客户端再次校验上架状态，避免旧版服务忽略参数时把未上架渠道带入申请表。
 */
export async function getAccountOpeningChannelPage(
  params: MpowerPageQuery = {},
): Promise<MpowerBody<ChannelPage<ChannelRecord>>> {
  const response = await getChannelPage<ChannelRecord>({
    ...params,
    putawayStatus: 1,
    status: '1',
  });
  return body({
    count: response.data.count,
    records: response.data.records.filter(
      (channel) =>
        Number(channel.putawayStatus) === 1 && Number(channel.status) === 1,
    ),
  });
}

/** 获取广告户申请选择器可开户的渠道选项。 */
export async function getAccountOpeningChannelOptions(): Promise<
  ChannelOption[]
> {
  const response = await getAccountOpeningChannelPage({
    pageNum: 1,
    pageSize: 1000,
  });
  return response.data.records
    .filter((channel) => Boolean(channel.channelName))
    .map((channel) => ({
      label: channel.channelName ?? String(channel.id),
      value: String(channel.id),
    }));
}

export async function getChannelSummary<T = MpowerRecord>(
  params: MpowerRecord = {},
): Promise<MpowerBody<T>> {
  const result = await mainBackendClient.get('/channels/summary', {
    params: pageParams(params),
  });
  return body(result as T);
}

/** 查询与广告面板渠道维度一致的 campaign 层周期花费。 */
export function getChannelPeriodSpend(
  params: ChannelPeriodSpendQuery,
): Promise<ChannelPeriodSpendResult> {
  return mainBackendClient.get('/channels/period-spend', {
    params: pageParams(params),
    skipErrorMessage: true,
  });
}

export async function getChannelTypePage<T = MpowerRecord>(
  params: MpowerPageQuery = {},
): Promise<MpowerBody<ChannelPage<T>>> {
  const result: any = await mainBackendClient.get('/channels/type-summary', {
    params: pageParams(params),
  });
  return body({ count: result.total, records: result.items });
}

export async function getChannel<T = ChannelRecord>(
  id: number | string,
): Promise<MpowerBody<T>> {
  const result = await mainBackendClient.get(
    `/channels/${encodeURIComponent(id)}`,
  );
  return body(result as T);
}

/** 获取打款动态表单在选择渠道后自动回填的只读字段。 */
export async function getChannelPaymentContext(
  id: number | string,
): Promise<ChannelPaymentContext> {
  return mainBackendClient.get(
    `/channels/${encodeURIComponent(id)}/payment-context`,
  );
}

export async function createChannel<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  await mainBackendClient.post('/channels', data);
  return body(undefined);
}

export async function updateChannel<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  const { id, ...payload } = data;
  await mainBackendClient.request(
    `/channels/${encodeURIComponent(id as number | string)}`,
    { data: payload, method: 'PATCH' },
  );
  return body(undefined);
}

export async function deleteChannel(
  id: number | string,
): Promise<MpowerBody<void>> {
  await mainBackendClient.delete(`/channels/${encodeURIComponent(id)}`);
  return body(undefined);
}

export async function getRatePage<T = MpowerRecord>(
  params: MpowerPageQuery = {},
): Promise<MpowerTable<T>> {
  const result: any = await mainBackendClient.get(
    `/channels/${encodeURIComponent(params.channelId as number | string)}/rates`,
    { params: pageParams(params) },
  );
  return {
    code: 200,
    rows: result.items,
    total: result.total,
  } as MpowerTable<T>;
}

export async function createRate<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  const { channelId, id: _id, ...payload } = data;
  await mainBackendClient.post(
    `/channels/${encodeURIComponent(channelId as number | string)}/rates`,
    payload,
  );
  return body(undefined);
}

export async function updateRate<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  const { channelId, id, ...payload } = data;
  await mainBackendClient.put(
    `/channels/${encodeURIComponent(channelId as number | string)}/rates/${encodeURIComponent(id as number | string)}`,
    payload,
  );
  return body(undefined);
}

export async function getAccountTypes<T = AccountTypeRecord>(): Promise<
  MpowerBody<T[]>
> {
  const result = await mainBackendClient.get('/channel-account-types');
  return body(result as T[]);
}

export async function createAccountType<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  await mainBackendClient.post('/channel-account-types', data);
  return body(undefined);
}

export async function deleteAccountType(
  id: number | string,
): Promise<MpowerBody<void>> {
  await mainBackendClient.delete(
    `/channel-account-types/${encodeURIComponent(id)}`,
  );
  return body(undefined);
}

function accountQuery(data: MpowerRecord) {
  const { pageNum, ...rest } = data;
  return { ...rest, page: pageNum ?? 1 };
}

export async function getChannelAccounts<T = ChannelAccountRecord>(
  data: MpowerRecord,
): Promise<MpowerTable<T>> {
  const result: any = await mainBackendClient.post(
    '/channel-accounts/search',
    accountQuery(data),
  );
  return {
    code: 200,
    rows: result.items,
    total: result.total,
  } as MpowerTable<T>;
}

/** 查询广告户申请办理时的渠道账户，不需要传入花费时间。 */
export async function getAvailableChannelAccounts<T = ChannelAccountRecord>(
  data: AvailableChannelAccountQuery,
): Promise<MpowerTable<T>> {
  const result: any = await mainBackendClient.post(
    '/channel-accounts/available/search',
    accountQuery(data),
  );
  return {
    code: 200,
    rows: result.items,
    total: result.total,
  } as MpowerTable<T>;
}

/**
 * 获取审批表单使用的系统广告账户选项。
 *
 * @remarks
 * 数据由当前 Main 服务的渠道账户接口提供，不再依赖旧 MPower 服务。账户操作
 * 可能覆盖使用中、停用或回收等状态，因此这里不额外按状态过滤；表单保存平台
 * 账户 ID，名称仅作为快照展示。
 */
export async function getAdAccountOptions(): Promise<AdAccountOption[]> {
  const firstPage = await getAdAccountAssetPage({ page: 1, pageSize: 100 });
  const pageCount = Math.ceil(firstPage.total / firstPage.pageSize);
  const remainingPages = await Promise.all(
    Array.from({ length: Math.max(pageCount - 1, 0) }, (_, index) =>
      getAdAccountAssetPage({ page: index + 2, pageSize: 100 }),
    ),
  );
  const accounts = [
    ...firstPage.items,
    ...remainingPages.flatMap((page) => page.items),
  ];
  const seen = new Set<string>();
  return accounts.flatMap((account) => {
    const accountId = String(account.accountId ?? '').trim();
    if (!accountId || seen.has(accountId)) return [];
    seen.add(accountId);
    const accountName =
      String(account.accountName ?? '').trim() || '未命名账户';
    const accountType = String(account.accountType ?? '').trim();
    return [
      {
        label: `${accountName} · ${accountId}${accountType ? ` · ${accountType}` : ''}`,
        value: accountId,
      },
    ];
  });
}

export async function getChannelAccountStatistics<T = MpowerRecord>(
  data: MpowerRecord,
): Promise<MpowerBody<T>> {
  const result = await mainBackendClient.post(
    '/channel-accounts/statistics',
    accountQuery(data),
  );
  return body(result as T);
}

export async function getAccountCountStats<T = MpowerRecord>(
  channelId: number | string,
): Promise<MpowerBody<T>> {
  const result = await mainBackendClient.get(
    `/channels/${encodeURIComponent(channelId)}/account-counts`,
  );
  return body(result as T);
}

export async function deleteChannelAccount(
  accountId: number | string,
): Promise<MpowerBody<void>> {
  await mainBackendClient.delete(
    `/channel-accounts/${encodeURIComponent(accountId)}`,
  );
  return body(undefined);
}

export async function assignPitcher<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  await mainBackendClient.request('/channel-accounts/assignment', {
    data: {
      accountIds: data.channelAccountIds,
      operatorId: data.operatorId,
    },
    method: 'PATCH',
  });
  return body(undefined);
}

export async function getPitchers<T = MpowerRecord>(
  params: MpowerPageQuery = {},
): Promise<MpowerBody<ChannelPage<T>>> {
  const result: any = await mainBackendClient.get('/channel-support/pitchers', {
    params: pageParams(params),
  });
  return body({ count: result.total, records: result.items });
}

export async function getMpowerDepartmentTree<T = MpowerRecord>(): Promise<
  MpowerBody<T[]>
> {
  const result = await mainBackendClient.get('/channel-support/departments');
  return body(result as T[]);
}

export async function batchCreateChannelAccounts<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  const channelId = data.channelId as number | string;
  await mainBackendClient.post(
    `/channels/${encodeURIComponent(channelId)}/accounts/batch`,
    { accounts: data.accountList, channelId },
  );
  return body(undefined);
}

export async function importChannelAccounts(
  data: FormData,
): Promise<MpowerBody<string[]>> {
  const result = await mainBackendClient.post(
    '/channel-accounts/import',
    data,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
    },
  );
  return body(result as string[]);
}

export function downloadChannelImportTemplate(): Promise<Blob> {
  return mainBackendClient.get('/channel-accounts/import-template', {
    responseReturn: 'body',
    responseType: 'blob',
  });
}

export function exportChannelAccounts(data: MpowerRecord): Promise<Blob> {
  return mainBackendClient.post(
    '/channel-accounts/export',
    accountQuery(data),
    { responseReturn: 'body', responseType: 'blob' },
  );
}

export async function getChannelGoods<T = MpowerRecord>(
  channelId: number | string,
): Promise<MpowerBody<null | T>> {
  const result = await mainBackendClient.get(
    `/channels/${encodeURIComponent(channelId)}/goods`,
  );
  return body(result as null | T);
}

export async function saveChannelGoods<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  const { channelId, minBugLimit, ...rest } = data;
  await mainBackendClient.put(
    `/channels/${encodeURIComponent(channelId as number | string)}/goods`,
    { ...rest, minBuyLimit: minBugLimit },
  );
  return body(undefined);
}

export async function setChannelPutaway<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  await mainBackendClient.request(
    `/channels/${encodeURIComponent(data.channelId as number | string)}/goods/putaway`,
    { data: { putawayStatus: data.putawayStatus }, method: 'PATCH' },
  );
  return body(undefined);
}

export async function getCampaignSpend<T = MpowerRecord>(
  params: MpowerPageQuery = {},
): Promise<MpowerBody<ChannelPage<T>>> {
  const accountId = params.accountId as number | string;
  const query = pageParams(params) as MpowerRecord;
  delete query.accountId;
  const result: any = await mainBackendClient.get(
    `/channel-accounts/${encodeURIComponent(accountId as number | string)}/campaigns`,
    { params: query },
  );
  return body({ count: result.total, records: result.items });
}
