import type { MpowerBody, MpowerPageQuery, MpowerRecord } from './types';

import { mainBackendClient } from '#/api/request';

export interface ManagedAccountPage<T = MpowerRecord> {
  count?: number;
  records: T[];
  total?: number;
}

export interface ManagedAccountStatusCount {
  count: number;
  name: string;
}

export interface ManagedAccountChannelOption extends MpowerRecord {
  channelCode: string;
  channelName: string;
  id: number | string;
}

export interface ManagedAccountTypeOption extends MpowerRecord {
  accountType: string;
  id: number | string;
}

export interface ManagedAccountPitcherOption extends MpowerRecord {
  nickName: string;
  userId: number | string;
}

export interface ManagedAccountSelectOption {
  label: string;
  value: string;
}

interface MainAccountPage<T> {
  items: T[];
  total: number;
}

interface MainAccountRecord extends MpowerRecord {
  status?: number;
  usageStatus?: number;
}

function body<T>(data: T): MpowerBody<T> {
  return { code: 200, data, msg: 'success' };
}

/**
 * 将账户管理页面的历史筛选字段转换为当前 Main 服务的查询参数。
 *
 * @remarks
 * 账户数据现在由 Main 服务统一提供；这里仅保留页面现有的 records/count 返回契约，
 * 避免页面层散落新旧字段兼容逻辑。
 */
function toMainAccountQuery(params: MpowerPageQuery = {}) {
  const {
    accountIds,
    accountStatus,
    balanceMax,
    balanceMin,
    channelId,
    endDate,
    fbadChannel: _fbadChannel,
    isRecycled,
    pageNum,
    pageSize,
    startDate,
    stopStatus,
    usageStatus: requestedUsageStatus,
    ...rest
  } = params;
  const selectedStatus = Number(accountStatus);
  const usageStatus =
    Number(isRecycled) === 1
      ? 3
      : Number(stopStatus) === 1
        ? 2
        : selectedStatus === 99
          ? 4
          : selectedStatus === 97
            ? 0
            : requestedUsageStatus;

  return {
    ...rest,
    accountIds:
      typeof accountIds === 'string'
        ? accountIds
            .split(',')
            .map((id) => id.trim())
            .filter(Boolean)
        : accountIds,
    balanceMax,
    balanceMin,
    channelId,
    endDate,
    page: pageNum ?? 1,
    pageSize,
    startDate,
    status:
      accountStatus === undefined || accountStatus === ''
        ? undefined
        : [1, 2].includes(selectedStatus)
          ? selectedStatus
          : undefined,
    usageStatus,
  };
}

function normalizeAccount<T extends MpowerRecord>(account: T): T {
  const source = account as T & MainAccountRecord;
  return {
    ...source,
    accountStatus: source.status,
    isRecycled: source.usageStatus === 3 ? 1 : 0,
    stopStatus: source.usageStatus === 2 ? 1 : 0,
  };
}

/** 查询当前系统的账户管理列表，并保持页面现有分页结构。 */
export async function getManagedAccountList<
  T extends MpowerRecord = MpowerRecord,
>(params: MpowerPageQuery = {}): Promise<MpowerBody<ManagedAccountPage<T>>> {
  const result = await mainBackendClient.post<MainAccountPage<T>>(
    '/channel-accounts/search',
    toMainAccountQuery(params),
  );
  return body({
    count: result.total,
    records: result.items.map(normalizeAccount),
    total: result.total,
  });
}

/** 查询当前筛选条件下的账户金额汇总。 */
export async function getManagedAccountSummary<T = MpowerRecord>(
  params: MpowerPageQuery = {},
): Promise<MpowerBody<T>> {
  const result = await mainBackendClient.post<T>(
    '/channel-accounts/statistics',
    toMainAccountQuery(params),
  );
  return body(result);
}

/** 查询当前系统账户状态数量，用于状态页签。 */
export async function getManagedAccountStatusCounts(
  params: MpowerRecord = {},
): Promise<MpowerBody<ManagedAccountStatusCount[]>> {
  const count = async (overrides: MpowerRecord) => {
    const result = await mainBackendClient.post<MainAccountPage<MpowerRecord>>(
      '/channel-accounts/search',
      toMainAccountQuery({ ...params, ...overrides, pageNum: 1, pageSize: 1 }),
    );
    return result.total;
  };
  const [total, active, suspended, stopped, recycled, idle] = await Promise.all(
    [
      count({}),
      count({ accountStatus: 1 }),
      count({ accountStatus: 2 }),
      count({ stopStatus: 1 }),
      count({ isRecycled: 1 }),
      count({ usageStatus: 4 }),
    ],
  );
  return body([
    { count: total, name: 'total' },
    { count: active, name: 'active' },
    { count: suspended, name: 'suspended' },
    { count: stopped, name: 'stopped' },
    { count: recycled, name: 'recycled' },
    { count: idle, name: 'idle' },
  ]);
}

/** 修改账户停用状态。 */
export async function updateManagedAccount<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  const accountId = String(data.accountId ?? '');
  const usageStatus = Number(data.stopStatus) === 1 ? 2 : data.usageStatus;
  await mainBackendClient.request(
    `/channel-accounts/${encodeURIComponent(accountId)}/usage-status`,
    { data: { usageStatus }, method: 'PATCH' },
  );
  return body(undefined);
}

/** 批量修改广告账户名称。 */
export async function renameManagedAccounts<T extends MpowerRecord>(
  data: T[],
): Promise<MpowerBody<void>> {
  await mainBackendClient.request('/channel-accounts/names', {
    data,
    method: 'PATCH',
  });
  return body(undefined);
}

/** 批量归类广告账户。 */
export async function classifyManagedAccounts<T extends MpowerRecord>(
  data: T[],
): Promise<MpowerBody<void>> {
  await mainBackendClient.request('/channel-accounts/classifications', {
    data,
    method: 'PATCH',
  });
  return body(undefined);
}

/** 批量修改广告账户回收状态。 */
export async function recycleManagedAccounts<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  const accountIds = Array.isArray(data.accountIds) ? data.accountIds : [];
  const usageStatus = Number(data.isRecycled) === 1 ? 3 : 0;
  await Promise.all(
    accountIds.map((accountId) =>
      mainBackendClient.request(
        `/channel-accounts/${encodeURIComponent(String(accountId))}/usage-status`,
        { data: { usageStatus }, method: 'PATCH' },
      ),
    ),
  );
  return body(undefined);
}

/** 查询账户管理使用的渠道选项。 */
export async function getManagedAccountChannels(): Promise<
  MpowerBody<ManagedAccountChannelOption[]>
> {
  const result = await mainBackendClient.get<
    MainAccountPage<ManagedAccountChannelOption>
  >('/channels', { params: { page: 1, pageSize: 100_000 } });
  return body(result.items);
}

/** 查询当前系统账户类型字典。 */
export async function getManagedAccountTypes(): Promise<
  MpowerBody<ManagedAccountTypeOption[]>
> {
  const result = await mainBackendClient.get<ManagedAccountTypeOption[]>(
    '/channel-account-types',
  );
  return body(result);
}

/** 查询可绑定到广告账户的投手。 */
export async function getManagedAccountPitchers(
  params: MpowerPageQuery = {},
): Promise<MpowerBody<ManagedAccountPage<ManagedAccountPitcherOption>>> {
  const result = await mainBackendClient.get<
    MainAccountPage<ManagedAccountPitcherOption>
  >('/channel-support/pitchers', {
    params: { page: params.pageNum ?? 1, pageSize: params.pageSize ?? 20 },
  });
  return body({
    count: result.total,
    records: result.items,
    total: result.total,
  });
}

/** 管理员手动建立渠道、账户和投手关系。 */
export async function bindManagedAccountPitchers<T extends MpowerRecord>(
  data: T,
): Promise<MpowerBody<void>> {
  await mainBackendClient.request('/channel-accounts/manual-assignment', {
    data: {
      accounts: data.accountList,
      channelId: data.channelId,
      operatorId:
        data.operatorId ??
        (data.accountList as MpowerRecord[])?.[0]?.operatorId,
    },
    method: 'PATCH',
  });
  return body(undefined);
}
