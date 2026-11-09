import { mainBackendClient } from '#/api/request';

export interface SafeheronPage<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface SafeheronRule {
  coinKey: string;
  collectAccountKey: string;
  collectAccountName?: string;
  createTime?: string;
  deptId: number | string;
  deptName?: string;
  effectiveStatus?: number;
  frequency: number;
  gasStationEnabled: number;
  id: number | string;
  maxTxFee?: number | string;
  reserveGas?: number | string;
  signer?: string;
  status: number;
  thresholdUsd: number | string;
  updatedAt?: string;
}

export interface SafeheronWallet {
  accountKey: string;
  accountName: string;
  teamId?: string;
}

export interface SafeheronCoin {
  coinKey: string;
  coinName: string;
}

export interface SafeheronTeam {
  approverId?: string;
  approverName?: string;
  status?: number;
  teamId: string;
  teamName: string;
}

export interface SafeheronUser {
  nickName?: string;
  userId: string;
  userName?: string;
}

export interface SafeheronDepartment {
  children?: SafeheronDepartment[];
  id: string;
  label: string;
}

export interface SafeheronRecordQuery {
  deptId?: number | string;
  endDate?: string;
  pageNum?: number;
  pageSize?: number;
  startDate?: string;
  status?: number;
  taskId?: string;
  teamId?: string;
}

export interface SafeheronRecord {
  amount?: number | string;
  amountUsd?: number | string;
  approveResult?: number;
  approverId?: string;
  approverName?: string;
  coinKey?: string;
  coinName?: string;
  createTime?: string;
  deptId?: string;
  deptName?: string;
  destAccountName?: string;
  gasFee?: number | string;
  id: string;
  remark?: string;
  sourceAccountName?: string;
  status: number;
  taskId?: string;
  teamId?: string;
  transactionType?: string;
  txHash?: string;
}

export interface SafeheronRecordStatistics {
  successRate: number;
  todayAmountUsd: number;
  todayCount: number;
  todayGas: number;
}

type RulePayload = Partial<SafeheronRule>;

function pageQuery<T extends { pageNum?: number }>(params: T) {
  const { pageNum, ...query } = params;
  return { ...query, page: pageNum ?? 1 };
}

function rulePayload(data: RulePayload) {
  return {
    coinKey: data.coinKey,
    collectAccountKey: data.collectAccountKey,
    deptId: data.deptId,
    frequency: data.frequency,
    gasStationEnabled: data.gasStationEnabled,
    maxTxFee: data.maxTxFee,
    reserveGas: data.reserveGas,
    signer: data.signer,
    status: data.status,
    thresholdUsd: data.thresholdUsd,
  };
}

export function getSafeheronRules(params: {
  pageNum?: number;
  pageSize?: number;
}) {
  return mainBackendClient.get<SafeheronPage<SafeheronRule>>(
    '/safeheron/rules',
    { params: pageQuery(params) },
  );
}

export function createSafeheronRule(data: RulePayload) {
  return mainBackendClient.post<SafeheronRule>(
    '/safeheron/rules',
    rulePayload(data),
  );
}

export function updateSafeheronRule(data: RulePayload) {
  return mainBackendClient.put<SafeheronRule>(
    `/safeheron/rules/${encodeURIComponent(data.id as number | string)}`,
    rulePayload(data),
  );
}

export function updateSafeheronRuleStatus(id: number | string, status: number) {
  return mainBackendClient.request(
    `/safeheron/rules/${encodeURIComponent(id)}/status`,
    { data: { status }, method: 'PATCH' },
  );
}

export function deleteSafeheronRule(id: number | string) {
  return mainBackendClient.delete(`/safeheron/rules/${encodeURIComponent(id)}`);
}

export function getSafeheronWallets() {
  return mainBackendClient.get<SafeheronWallet[]>('/safeheron/wallets');
}

export function getSafeheronWalletCoins(accountKey: string) {
  return mainBackendClient.get<SafeheronCoin[]>(
    `/safeheron/wallets/${encodeURIComponent(accountKey)}/coins`,
  );
}

export function getSafeheronTeams() {
  return mainBackendClient.get<SafeheronTeam[]>('/safeheron/teams');
}

export function updateSafeheronApprovers(
  data: Array<{ approverId: number | string; teamId: string }>,
) {
  return mainBackendClient.put('/safeheron/teams/approvers', data);
}

export function getSafeheronUsers() {
  return mainBackendClient.get<SafeheronUser[]>('/safeheron/users');
}

export function getSafeheronDepartments() {
  return mainBackendClient.get<SafeheronDepartment[]>('/safeheron/departments');
}

export function getSafeheronRecords(params: SafeheronRecordQuery) {
  return mainBackendClient.get<SafeheronPage<SafeheronRecord>>(
    '/safeheron/records',
    { params: pageQuery(params) },
  );
}

export function getSafeheronRecordStats(params: SafeheronRecordQuery) {
  return mainBackendClient.get<SafeheronRecordStatistics>(
    '/safeheron/records/statistics',
    { params: pageQuery(params) },
  );
}

export function exportSafeheronRecords(params: SafeheronRecordQuery) {
  return mainBackendClient.post<Blob>('/safeheron/records/export', undefined, {
    params: pageQuery(params),
    responseType: 'blob',
  });
}
