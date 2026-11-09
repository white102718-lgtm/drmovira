import { mainBackendClient } from '#/api/request';

export type CardPlatform = 'arrivalx' | 'photonpay';

export interface CardStationPage<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export interface ArrivalxCard {
  [key: string]: unknown;
  balance?: number | string;
  cardId: string;
  cardName?: string;
  createdAt?: string;
  currency?: string;
  id?: number | string;
  maskedPan?: string;
  periodMaxConsumeAmount?: number | string;
  status?: string;
  transactionMaxAmount?: number | string;
  transactionMinAmount?: number | string;
  utilizationLimitAmount?: number | string;
  utilizationLimitPreset?: string;
}

export interface PhotonPayCard {
  [key: string]: unknown;
  advertisementAccountId?: string;
  cardBalance?: number | string;
  cardCurrency?: string;
  cardNo?: string;
  cardNumber?: string;
  cardStatus?: string;
  id: number | string;
  nickname?: string;
}

export interface CardStationBalance {
  balance: number;
  currency: string;
  frozenBalance: number;
  productCode: string;
}

export interface CardStationStatistics {
  active: number;
  balance: number;
  frozen: number;
  total: number;
}

export interface CardStationLimitRule {
  adjustAmount?: number | string;
  autoAdjustEnabled: boolean;
  configured: boolean;
  dailyPeriod?: number;
  minAmount?: number | string;
  updatedAt?: string;
}

export interface CardStationLimitRulePayload {
  adjustAmount: number;
  autoAdjustEnabled: boolean;
  dailyPeriod: number;
  minAmount: number;
}

type Params = Record<string, unknown>;

function pageQuery(params: Params) {
  const { pageNum, ...query } = params;
  return { ...query, page: pageNum ?? 1 };
}

export function getCardStationCards<T = ArrivalxCard | PhotonPayCard>(
  platform: CardPlatform,
  params: Params,
) {
  return mainBackendClient.get<CardStationPage<T>>('/card-station/cards', {
    params: { ...pageQuery(params), platform },
  });
}

export function getCardStationBalance(platform: CardPlatform) {
  return mainBackendClient.get<CardStationBalance[]>('/card-station/balances', {
    params: { platform },
  });
}

export function getCardStationStatistics(platform: CardPlatform) {
  return mainBackendClient.get<CardStationStatistics>(
    '/card-station/statistics',
    { params: { platform } },
  );
}

export function getCardStationLimitRule() {
  return mainBackendClient.get<CardStationLimitRule>(
    '/card-station/limit-rule',
  );
}

export function updateCardStationLimitRule(data: CardStationLimitRulePayload) {
  return mainBackendClient.put<CardStationLimitRule>(
    '/card-station/limit-rule',
    data,
  );
}

export function updateCardStationAutoAdjust(enabled: boolean) {
  return mainBackendClient.request<CardStationLimitRule>(
    '/card-station/limit-rule/auto-adjust',
    { data: { enabled }, method: 'PATCH' },
  );
}

export function syncCardStation(platform: CardPlatform) {
  return mainBackendClient.post(
    `/card-station/${encodeURIComponent(platform)}/sync`,
    undefined,
    { timeout: 60_000 },
  );
}

export function getCardStationDetail(
  platform: CardPlatform,
  id: number | string,
) {
  return mainBackendClient.get<Record<string, unknown>>(
    `/card-station/${encodeURIComponent(platform)}/cards/${encodeURIComponent(id)}`,
  );
}

export function getCardStationLimitRecords(
  platform: CardPlatform,
  params: Params,
) {
  return mainBackendClient.get<CardStationPage<Record<string, unknown>>>(
    '/card-station/limit-records',
    { params: { ...pageQuery(params), platform } },
  );
}

export function setCardStationBatchLimit(platform: CardPlatform, data: Params) {
  return mainBackendClient.post(
    `/card-station/${encodeURIComponent(platform)}/limits`,
    data,
  );
}

export function updateCardStationStatus(platform: CardPlatform, data: Params) {
  return mainBackendClient.request(
    `/card-station/${encodeURIComponent(platform)}/status`,
    { data, method: 'PATCH' },
  );
}

export function exportCardStationCards(platform: CardPlatform, params: Params) {
  return mainBackendClient.post<Blob>('/card-station/cards/export', undefined, {
    params: { ...pageQuery(params), platform },
    responseType: 'blob',
  });
}
