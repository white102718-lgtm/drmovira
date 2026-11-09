import { backendClient } from '#/api/request';
import type { MonthlyReport, ReportRule } from '#/domain/report-rules';

/** 日报通知统一由服务端在同一事务中投递站内消息和飞书消息。 */
export interface DailyReportNotificationPayload {
  businessId: string;
  businessType: 'daily-report' | 'daily-report-application';
  channels: Array<'feishu' | 'system'>;
  reportName: string;
}

export const dailyReportApi = {
  deleteRule: (ruleId: string) => backendClient.delete(`/daily-report-rules/${ruleId}`),
  listManagedRules: () => backendClient.get<ReportRule[]>('/daily-report-rules'),
  listReports: () => backendClient.get<MonthlyReport[]>('/daily-reports'),
  listVisibleRules: () =>
    backendClient.get<ReportRule[]>('/daily-reports/visible-rules'),
  notify: (
    payload: DailyReportNotificationPayload,
    config?: { skipErrorMessage?: boolean },
  ) =>
    backendClient.post<void>('/daily-reports/notifications', payload, config),
  saveRule: (rule: ReportRule) =>
    backendClient.put<ReportRule>(`/daily-report-rules/${rule.id}`, rule),
  submit: (payload: {
    attachments?: Record<string, Array<{ id: string; name: string }>>;
    fields: Record<string, string>;
    ruleId: string;
  }) => backendClient.post<MonthlyReport>('/daily-reports', payload),
  update: (
    reportId: string,
    payload: {
      attachments?: Record<string, Array<{ id: string; name: string }>>;
      fields: Record<string, string>;
    },
  ) => backendClient.put<MonthlyReport>(`/daily-reports/${reportId}`, payload),
};

interface UploadedDailyReportFile {
  id: string;
  mimeType: string;
  originalName: string;
}

async function sha256(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const digest = new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', bytes));
  return [...digest].map((item) => item.toString(16).padStart(2, '0')).join('');
}

export async function uploadDailyReportAttachment(file: File) {
  const data = new FormData();
  data.append('file', file);
  return backendClient.post<UploadedDailyReportFile>('/files/upload', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: { contentHash: await sha256(file) },
  } as never);
}
