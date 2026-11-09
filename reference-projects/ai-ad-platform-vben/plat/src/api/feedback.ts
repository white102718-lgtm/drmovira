import type { SystemPageResult } from './system/types';

import { backendClient } from '#/api/request';

export type FeedbackCategory = 'BUG' | 'EXPERIENCE' | 'FEATURE';
export type FeedbackStatus = 'CLOSED' | 'PENDING' | 'PROCESSING' | 'RESOLVED';

export interface FeedbackConsoleEntry {
  level: 'error' | 'info' | 'log' | 'warn';
  message: string;
  timestamp: string;
}

export interface FeedbackDiagnostics {
  appVersion?: string;
  browser?: string;
  consoleLogs: FeedbackConsoleEntry[];
  deviceMemory?: number;
  devicePixelRatio?: number;
  deviceType?: string;
  hardwareConcurrency?: number;
  language?: string;
  networkType?: string;
  operatingSystem?: string;
  pageUrl?: string;
  routeName?: string;
  screenResolution?: string;
  timezone?: string;
  viewportSize?: string;
}

export interface FeedbackListItem {
  attachmentCount: number;
  category: FeedbackCategory;
  clientIp: string;
  content: string;
  createdAt: string;
  deviceType?: null | string;
  id: string;
  ownerId?: null | string;
  ownerName?: null | string;
  status: FeedbackStatus;
  submittedByName: string;
  submittedByUsername?: null | string;
  title: string;
  updatedAt: string;
}

export interface FeedbackSummary {
  closed: number;
  pending: number;
  processing: number;
  resolved: number;
  total: number;
}

export interface FeedbackAttachment {
  fileSize: number;
  id: string;
  mimeType: string;
  originalName: string;
  sortOrder: number;
}

export interface FeedbackDetail extends FeedbackListItem {
  adminReply?: null | string;
  attachments: FeedbackAttachment[];
  diagnostics?: FeedbackDiagnostics | null;
  pageUrl?: null | string;
  processedAt?: null | string;
  processedById?: null | string;
  processedByName?: null | string;
  submittedById: string;
  userAgent?: null | string;
}

export interface CreateFeedbackInput {
  attachmentFileIds: string[];
  category: FeedbackCategory;
  content: string;
  diagnostics?: FeedbackDiagnostics;
  title: string;
}

interface UploadedFeedbackFile {
  id: string;
  mimeType: string;
  originalName: string;
}

async function sha256(file: File) {
  const buffer = await file.arrayBuffer();
  let digest: Uint8Array;
  if (globalThis.crypto?.subtle) {
    digest = new Uint8Array(
      await globalThis.crypto.subtle.digest('SHA-256', buffer),
    );
  } else {
    // 测试环境可能不是安全上下文，使用项目已有的同等 SHA-256 实现。
    const { sha256: sha256Fallback } = await import('@noble/hashes/sha2.js');
    digest = sha256Fallback(new Uint8Array(buffer));
  }
  return [...digest]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
}

/** 上传反馈附件，返回提交反馈时需要绑定的稳定文件ID。 */
export async function uploadFeedbackAttachmentApi(file: File) {
  const data = new FormData();
  data.append('file', file);
  return backendClient.post<UploadedFeedbackFile>('/files/upload', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: { contentHash: await sha256(file) },
  });
}

/** 删除尚未绑定反馈的临时附件引用。 */
export function deleteFeedbackAttachmentApi(fileId: string) {
  return backendClient.delete(`/files/${fileId}`);
}

/** 提交产品反馈；账号和客户端IP由服务端按当前会话自动补充。 */
export function createFeedbackApi(data: CreateFeedbackInput) {
  return backendClient.post<FeedbackDetail>('/feedbacks', data);
}

export function getFeedbackListApi(params: {
  category?: FeedbackCategory;
  keyword?: string;
  page?: number;
  pageSize?: number;
  status?: FeedbackStatus;
}) {
  return backendClient.get<SystemPageResult<FeedbackListItem>>('/feedbacks', {
    params,
  });
}

export function getFeedbackDetailApi(id: string) {
  return backendClient.get<FeedbackDetail>(`/feedbacks/${id}`);
}

export function getFeedbackSummaryApi() {
  return backendClient.get<FeedbackSummary>('/feedbacks/summary');
}

export function updateFeedbackStatusApi(
  id: string,
  data: {
    adminReply?: string;
    ownerId: null | string;
    status: FeedbackStatus;
  },
) {
  return backendClient.put<FeedbackDetail>(`/feedbacks/${id}/status`, data);
}
