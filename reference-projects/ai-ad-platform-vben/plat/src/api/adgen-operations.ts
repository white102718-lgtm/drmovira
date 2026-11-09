import type { OperationRecord } from './fusion/types';

import { useAccessStore } from '@vben/stores';

import { readCanvasModelApiResponse } from './canvas-model-response';

export type AdgenProviderKey =
  | 'all'
  | 'bailian'
  | 'byteplus'
  | 'gemini'
  | 'kling'
  | 'openai'
  | 'qwen';

export interface AdgenProviderOverview {
  calls: string;
  chart: number[];
  cost: string;
  latency: string;
  success: string;
}

export interface AdgenModelRow {
  calls: string;
  defaultDurationSeconds: null | number;
  description: string;
  durationParameterEnabled: boolean;
  extensionMode: 'bailian_continuation' | 'none' | 'veo_iterations';
  health: 'healthy' | 'warning';
  id: string;
  maxDurationSeconds: null | number;
  minDurationSeconds: null | number;
  modelId: string;
  name: string;
  provider: string;
  supportedAspectRatios: string[];
  supportedInputModes: AdgenVideoInputMode[];
  supportedResolutions: string[];
  supportsExtension: boolean;
  supportsImageEdit: boolean;
  supportsMultiShot: boolean;
  supportsNativeAudio: boolean;
  type: string;
  capabilityTags?: string[];
  usageTracked: boolean;
}

export type AdgenVideoInputMode =
  | 'first_frame'
  | 'first_last_frame'
  | 'reference_assets'
  | 'text_to_video';

export type AdgenModelPayload = Omit<
  AdgenModelRow,
  | 'calls'
  | 'capabilityTags'
  | 'defaultDurationSeconds'
  | 'health'
  | 'id'
  | 'maxDurationSeconds'
  | 'minDurationSeconds'
  | 'usageTracked'
> & {
  defaultDurationSeconds?: number;
  maxDurationSeconds?: number;
  minDurationSeconds?: number;
};

export interface AdgenRouteModel {
  config?: Record<string, any>;
  enabled: boolean;
  id: string;
  name: string;
}

export interface AdgenFeatureRoute {
  category: string;
  config?: Record<string, any>;
  defaultModel: string;
  featureKey: string;
  key: string;
  limit: number;
  limitField: string;
  limitLabel: string;
  models: AdgenRouteModel[];
  name: string;
  resolution?: string;
  resolutions?: string[];
}

export interface AdgenCredentialKey {
  errorCount: number;
  id: string;
  masked: string;
  status: 'healthy' | 'warning';
  usage: number;
}

export interface AdgenCredentialPool {
  available: number;
  environment: string;
  id: string;
  keys: AdgenCredentialKey[];
  name: string;
  provider: string;
  quota: number;
  serviceType: string;
  total: number;
}

export type AdgenUsageRankingPeriod =
  | 'month'
  | 'today'
  | 'week'
  | 'year'
  | 'yesterday';

export interface AdgenUsageRankingRow {
  calls: number;
  cost: number;
  displayName: string;
  nickname: string;
  rank: number;
  share: number;
  userId: string;
  username: string;
}

export interface AdgenUsageRanking {
  period: AdgenUsageRankingPeriod;
  rows: AdgenUsageRankingRow[];
}

export interface AdgenPersonnelConsumptionItem {
  amount: number;
  calls: number;
  cny_amount: number;
  department: string;
  input_tokens: number;
  name: string;
  output_tokens: number;
  total_cny: number;
  total_usd: number;
  tokens: number;
  user_id: string;
  usd_amount: number;
}

export interface AdgenPersonnelConsumption {
  calls_total: number;
  cny_total: number;
  currency: 'CNY' | 'USD';
  departments: string[];
  end_date: string;
  input_tokens_total: number;
  list: AdgenPersonnelConsumptionItem[];
  output_tokens_total: number;
  people: Array<{ label: string; value: string }>;
  spend_total: number;
  start_date: string;
  tokens_total: number;
  total_usd: number;
  total_cny: number;
  total: number;
  usd_total: number;
}

export interface AdgenPersonnelConsumptionParams {
  currency?: 'CNY' | 'USD';
  department?: string;
  end_date?: string;
  order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
  start_date?: string;
  user_id?: string;
}

export interface AdgenQuotaMetric {
  limit: null | number;
  percent: number;
  used: number;
}

export interface AdgenUserQuota {
  dailyLimit: null | number;
  department?: string;
  displayName: string;
  monthlyLimit: null | number;
  userId: string;
  weeklyLimit: null | number;
}

export interface AdgenQuotaSummary {
  daily: AdgenQuotaMetric;
  monthly: AdgenQuotaMetric;
  updatedAt?: null | string;
  updatedBy?: null | string;
  users: AdgenUserQuota[];
  weekly: AdgenQuotaMetric;
}

export interface AdgenQuotaPayload {
  dailyLimit: null | number;
  monthlyLimit: null | number;
  weeklyLimit: null | number;
}

export type AdgenUsageCostPeriod =
  | 'last_month'
  | 'last_week'
  | 'this_month'
  | 'this_week'
  | 'this_year'
  | 'today'
  | 'yesterday';

export interface AdgenUsageCostProvider {
  calls: number;
  completionTokens: number;
  currencies: AdgenUsageCurrencyTotal[];
  promptTokens: number;
  providerId: string;
  providerName: string;
  successCalls: number;
  totalUsd: number;
}

export interface AdgenUsageCurrencyTotal {
  currency: string;
  nativeCost: number;
  usdCost: number;
}

export interface AdgenUsageCostBreakdown {
  currencies: AdgenUsageCurrencyTotal[];
  endAt: string;
  label: string;
  period: AdgenUsageCostPeriod;
  providers: AdgenUsageCostProvider[];
  startAt: string;
  totalUsd: number;
}

export interface AdgenErrorRow {
  action: string;
  deployment: string;
  id: string;
  requestId: string;
  status: string;
  time: string;
  type: string;
}

export interface AdgenOperationsSnapshot {
  credentialPools: AdgenCredentialPool[];
  errorRows: AdgenErrorRow[];
  featureRoutes: AdgenFeatureRoute[];
  models: AdgenModelRow[];
  modelStats: Record<string, AdgenProviderOverview>;
  providerStats: Record<AdgenProviderKey, AdgenProviderOverview>;
  records: OperationRecord[];
}

export interface AdgenRuntimeConfig {
  currency?: {
    cnyToUsdRate?: number;
    code?: string;
  };
  featureRoutes: AdgenFeatureRoute[];
}

const API_BASE = '/adgen-api/api/admin/adgen-operations';

async function requestAdgen<T>(path: string, init?: RequestInit): Promise<T> {
  const token = useAccessStore().accessToken;
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'same-origin',
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  return readCanvasModelApiResponse<T>(response);
}

export function getAdgenOperationsSnapshotApi(periodDays: 'all' | number = 7) {
  return requestAdgen<AdgenOperationsSnapshot>(
    `/snapshot?period_days=${periodDays}`,
  );
}

export function getAdgenRuntimeConfigApi() {
  return requestAdgen<AdgenRuntimeConfig>(`/runtime-config?_=${Date.now()}`, {
    cache: 'no-store',
  });
}

export function getAdgenUsageRankingApi(period: AdgenUsageRankingPeriod) {
  return requestAdgen<AdgenUsageRanking>(
    `/usage-ranking?period=${encodeURIComponent(period)}`,
  );
}

export function getAdgenPersonnelConsumptionApi(
  params: AdgenPersonnelConsumptionParams,
) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value));
    }
  }
  return requestAdgen<AdgenPersonnelConsumption>(
    `/personnel-consumption?${search.toString()}`,
  );
}

export function getAdgenQuotaStatusApi() {
  return requestAdgen<AdgenQuotaSummary>('/quota-status');
}

export function getAdgenUsageCostBreakdownApi(period: AdgenUsageCostPeriod) {
  return requestAdgen<AdgenUsageCostBreakdown>(
    `/usage-cost-breakdown?period=${encodeURIComponent(period)}`,
  );
}

export function getAdgenQuotaSettingsApi() {
  return requestAdgen<AdgenQuotaSummary>('/quota-settings');
}

export function saveAdgenSystemQuotaApi(payload: AdgenQuotaPayload) {
  return requestAdgen<void>('/quota-settings/system', {
    body: JSON.stringify(payload),
    method: 'PUT',
  });
}

export function saveAdgenUserQuotaApi(
  userId: string,
  payload: AdgenQuotaPayload & { displayName: string },
) {
  return requestAdgen<void>(
    `/quota-settings/users/${encodeURIComponent(userId)}`,
    { body: JSON.stringify(payload), method: 'PUT' },
  );
}

export function saveAdgenUserQuotaBatchApi(
  userIds: string[],
  payload: AdgenQuotaPayload & { displayNames: Record<string, string> },
) {
  return requestAdgen<{ updated: number }>('/quota-settings/users/batch', {
    body: JSON.stringify({ ...payload, userIds }),
    method: 'PUT',
  });
}

export function saveAdgenModelApi(
  model: AdgenModelPayload,
  existingId?: string,
) {
  return requestAdgen<{ modelId: string }>(
    existingId ? `/models/${encodeURIComponent(existingId)}` : '/models',
    {
      body: JSON.stringify(model),
      method: existingId ? 'PUT' : 'POST',
    },
  );
}

export function deleteAdgenModelApi(modelId: string) {
  return requestAdgen<void>(`/models/${encodeURIComponent(modelId)}`, {
    method: 'DELETE',
  });
}

export interface AdgenModelSyncResult {
  added: Array<{ id: string; name: string }>;
  ignoredDeleted: string[];
  provider: string;
  skipped: string[];
}

export function syncAdgenModelsApi(provider: Exclude<AdgenProviderKey, 'all'>) {
  return requestAdgen<AdgenModelSyncResult>('/models/sync', {
    body: JSON.stringify({ provider }),
    method: 'POST',
  });
}

export function saveAdgenFeatureRouteApi(route: AdgenFeatureRoute) {
  return requestAdgen<void>(`/routes/${encodeURIComponent(route.featureKey)}`, {
    body: JSON.stringify({
      defaultModel: route.defaultModel,
      enabledModelIds: route.models
        .filter((model) => model.enabled)
        .map((model) => model.id),
      limit: route.limit,
      resolution: route.resolution,
    }),
    method: 'PUT',
  });
}

export function addAdgenCredentialApi(serviceType: string, key: string) {
  return requestAdgen<{ id: string }>(
    `/credentials/${encodeURIComponent(serviceType)}`,
    { body: JSON.stringify({ key }), method: 'POST' },
  );
}

export function addAdgenKlingCredentialApi(apiKey: string) {
  return requestAdgen<{ id: string }>('/credentials/kling', {
    body: JSON.stringify({ apiKey }),
    method: 'POST',
  });
}

export function deleteAdgenCredentialApi(serviceType: string, keyId: string) {
  return requestAdgen<void>(
    `/credentials/${encodeURIComponent(serviceType)}/${encodeURIComponent(keyId)}`,
    { method: 'DELETE' },
  );
}

export function resetAdgenCredentialPoolApi(serviceType: string) {
  return requestAdgen<{ serviceType: string }>(
    `/credentials/${encodeURIComponent(serviceType)}/reset`,
    { method: 'POST' },
  );
}

export interface AdgenByteplusAssetRow {
  associationStatus: 'Linked' | 'Missing' | 'Unlinked';
  canPreview: boolean;
  groupId: string;
  assetType: string;
  assetUri: string;
  id: string;
  name: string;
  status: null | string;
}

export interface AdgenByteplusAssetLibrary {
  checkedAt: null | string;
  localCount: number;
  officialCount: null | number;
  scope: string;
  configured: boolean;
  items: AdgenByteplusAssetRow[];
  limit: number;
  used: number;
}

export function listAdgenByteplusAssetsApi() {
  return requestAdgen<AdgenByteplusAssetLibrary>('/byteplus-assets');
}

/** 完整核对官方分页列表并导入未关联记录。 */
export function reconcileAdgenByteplusAssetsApi() {
  return requestAdgen<AdgenByteplusAssetLibrary>('/byteplus-assets/reconcile', {
    method: 'POST',
  });
}

export interface AdgenByteplusAssetPreview {
  assetType: string;
  contentType: string;
  id: string;
  name: string;
  previewUrl: string;
}

export function getAdgenByteplusAssetPreviewApi(assetId: string) {
  return requestAdgen<AdgenByteplusAssetPreview>(
    `/byteplus-assets/${encodeURIComponent(assetId)}/preview`,
  );
}

/** 删除结果未知时让批量操作停止，避免网关故障期间继续发送请求。 */
export class AdgenAssetDeleteUncertainError extends Error {}

/** 仅明确的 429 会自动重试，限流等待留在浏览器而不是网关请求中。 */
export async function deleteAdgenByteplusAssetApi(assetId: string) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    let response: Response;
    try {
      const token = useAccessStore().accessToken;
      response = await fetch(
        `${API_BASE}/byteplus-assets/${encodeURIComponent(assetId)}`,
        {
          method: 'DELETE',
          credentials: 'same-origin',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      );
    } catch {
      throw new AdgenAssetDeleteUncertainError(
        '删除请求连接失败，结果尚未确认，请先核对官方素材',
      );
    }
    if (response.status === 429) {
      const retryAfter = Number(response.headers.get('Retry-After'));
      const delaySeconds =
        Number.isFinite(retryAfter) && retryAfter > 0
          ? Math.min(Math.ceil(retryAfter), 65)
          : 60;
      await new Promise((resolve) => setTimeout(resolve, delaySeconds * 1000));
      continue;
    }
    if (response.status >= 500) {
      throw new AdgenAssetDeleteUncertainError(
        `删除接口返回 ${response.status}，结果尚未确认，请先核对官方素材`,
      );
    }
    return readCanvasModelApiResponse<{ limit: number; used: number }>(
      response,
    );
  }
  throw new AdgenAssetDeleteUncertainError(
    '官方素材接口持续繁忙，已停止删除，请稍后核对并重试',
  );
}
