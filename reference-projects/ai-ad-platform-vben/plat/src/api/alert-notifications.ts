import type { RequestClientConfig } from '@vben/request';

import { mainBackendClient } from '#/api/request';

export type AlertRecipientType = 'CHAT' | 'USER';
export type AlertWindowUnit = 'DAYS' | 'HOURS';
export type AlertLimitPollInterval = 5 | 10 | 15 | 30 | 60;

export interface AlertRecipient {
  id?: string;
  recipientKey: string;
  recipientName: string;
  recipientType: AlertRecipientType;
}

export interface AlertConfig {
  banEnabled: boolean;
  banThreshold: number;
  banWindowUnit: AlertWindowUnit;
  banWindowValue: number;
  enabled: boolean;
  limitChangeEnabled: boolean;
  limitPollIntervalMinutes: AlertLimitPollInterval;
  updatedAt?: string;
}

export interface AlertSettings {
  config: AlertConfig;
  recipients: AlertRecipient[];
}

export interface AlertTestDeliveryResult {
  failedCount: number;
  successCount: number;
}

export interface AlertBanRecord {
  accountId?: string;
  accountName?: string;
  currency?: string;
  currentStatus?: number;
  disableReason?: string;
  id: string;
  occurredAt: string;
  previousStatus?: number;
  source: 'FACEBOOK';
}

export type AlertLimitChangeType = 'CLEAR' | 'DECREASE' | 'INCREASE' | 'SET';

export interface AlertLimitChangeRecord {
  accountId?: string;
  accountName?: string;
  changeType: AlertLimitChangeType;
  currency?: string;
  currentLimit?: null | number;
  id: string;
  occurredAt: string;
  previousLimit?: null | number;
  source: 'FACEBOOK';
}

export interface AlertEventRecordQuery {
  endDate?: string;
  keyword?: string;
  page: number;
  pageSize: number;
  startDate?: string;
}

export interface AlertLimitChangeRecordQuery extends AlertEventRecordQuery {
  changeType?: AlertLimitChangeType;
}

export interface AlertEventRecordPage<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}

export function getAlertSettings() {
  return mainBackendClient.get<AlertSettings>('/alert-notifications/settings');
}

export function saveAlertSettings(
  data: AlertConfig & {
    recipients: AlertRecipient[];
  },
) {
  return mainBackendClient.put<AlertSettings>(
    '/alert-notifications/settings',
    data,
  );
}

export function sendAlertTestNotification(recipients: AlertRecipient[]) {
  return mainBackendClient.post<AlertTestDeliveryResult>(
    '/alert-notifications/test-delivery',
    { recipients },
  );
}

export function getAlertBanRecords(
  params: AlertEventRecordQuery,
  config?: RequestClientConfig,
) {
  return mainBackendClient.get<AlertEventRecordPage<AlertBanRecord>>(
    '/alert-notifications/ban-records',
    { ...config, params },
  );
}

export function getAlertLimitChangeRecords(
  params: AlertLimitChangeRecordQuery,
  config?: RequestClientConfig,
) {
  return mainBackendClient.get<AlertEventRecordPage<AlertLimitChangeRecord>>(
    '/alert-notifications/limit-change-records',
    { ...config, params },
  );
}
