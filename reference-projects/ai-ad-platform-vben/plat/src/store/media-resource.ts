import type {
  ResourceLifecycleState,
  ResourceLifecycleTransition,
} from '#/domain/resource';

import { computed, toRaw } from 'vue';

import { useStorage } from '@vueuse/core';
import { defineStore } from 'pinia';

import { resourceLifecycleService } from '#/domain/resource';

export type MediaPlatform = 'facebook' | 'google' | 'kwai' | 'tiktok';

export type MediaPlatformStatus =
  | 'active'
  | 'closed'
  | 'disabled'
  | 'pending_review'
  | 'restricted'
  | 'unsettled';

export type MediaWhitelistStatus =
  | 'approved'
  | 'not_required'
  | 'pending'
  | 'rejected';

export type MediaResourceStatus =
  | 'assigned'
  | 'available'
  | 'exception'
  | 'maintenance'
  | 'pending_assignment'
  | 'pending_return'
  | 'retired';

export type ResourceApplicationStatus =
  | 'approved'
  | 'partially_approved'
  | 'pending'
  | 'rejected';

export type ResourceAssignmentStatus =
  | 'active'
  | 'return_requested'
  | 'returned';

export type ResourceReturnStatus = 'completed' | 'requested';

export type ResourceResolutionOutcome = 'available' | 'disabled';

export interface AuditActor {
  id: string;
  name: string;
}

export interface MediaAccount {
  accountId: string;
  agencyLineId?: string;
  agencyLineName?: string;
  assignedAt?: string;
  assigneeId?: string;
  assigneeName?: string;
  balance?: number;
  businessManagerId?: string;
  businessManagerName?: string;
  channelName?: string;
  createdAt: string;
  cumulativeSpend?: number;
  currency?: string;
  exceptionAt?: string;
  exceptionPreviousResourceStatus?: MediaResourceStatus;
  exceptionReason?: string;
  id: string;
  inboundAt?: string;
  lastSyncedAt?: string;
  legalEntityName?: string;
  name: string;
  notes?: string;
  platform: MediaPlatform;
  platformStatus: MediaPlatformStatus;
  projectId?: string;
  projectName?: string;
  resourceStatus: MediaResourceStatus;
  spendCap?: number;
  tags: string[];
  teamId?: string;
  teamName?: string;
  timezone?: string;
  todaySpend?: number;
  updatedAt: string;
  whitelistStatus?: MediaWhitelistStatus;
}

export interface ResourceApplication {
  applicationNo: string;
  approvedAccountIds: string[];
  assigneeId?: string;
  assigneeName?: string;
  createdAt: string;
  expectedReturnAt?: string;
  id: string;
  platform: MediaPlatform;
  projectId: string;
  projectName: string;
  reason: string;
  rejectedReason?: string;
  requestedAccountCount: number;
  requestedById: string;
  requestedByName: string;
  reviewedAt?: string;
  reviewedById?: string;
  reviewedByName?: string;
  /** 对应工作台审批申请，供审批完成后的资源发放页面幂等恢复。 */
  sourceApplicationId?: string;
  sourceTaskId?: string;
  status: ResourceApplicationStatus;
  teamId: string;
  teamName: string;
  timezone?: string;
  title: string;
  updatedAt: string;
  whitelistRequired?: boolean;
}

export interface ResourceAssignment {
  applicationId: string;
  assignedAt: string;
  assignedById: string;
  assignedByName: string;
  assigneeId: string;
  assigneeName: string;
  id: string;
  mediaAccountId: string;
  platformAccountId: string;
  projectId: string;
  projectName: string;
  returnedAt?: string;
  status: ResourceAssignmentStatus;
  teamId: string;
  teamName: string;
  updatedAt: string;
}

export interface ResourceReturn {
  accountName: string;
  completedAt?: string;
  completedById?: string;
  completedByName?: string;
  id: string;
  mediaAccountId: string;
  platformAccountId: string;
  projectId: string;
  projectName: string;
  reason: string;
  requestedAt: string;
  requestedById: string;
  requestedByName: string;
  resourceAssignmentId: string;
  status: ResourceReturnStatus;
  updatedAt: string;
}

export type MediaAuditAction =
  | 'account.created'
  | 'account.updated'
  | 'application.approved'
  | 'application.created'
  | 'application.rejected'
  | 'demo.reset'
  | 'exception.marked'
  | 'exception.resolved'
  | 'return.completed'
  | 'return.requested';

export interface MediaAuditLog {
  action: MediaAuditAction;
  actorId: string;
  actorName: string;
  after?: Record<string, unknown>;
  before?: Record<string, unknown>;
  createdAt: string;
  entityId: string;
  entityType: 'account' | 'application' | 'demo' | 'return';
  id: string;
  message: string;
  metadata?: Record<string, unknown>;
  result: 'failed' | 'success';
}

export interface CreateMediaAccountInput {
  accountId: string;
  agencyLineId?: string;
  agencyLineName?: string;
  balance?: number;
  businessManagerId?: string;
  businessManagerName?: string;
  channelName?: string;
  cumulativeSpend?: number;
  currency?: string;
  legalEntityName?: string;
  name: string;
  notes?: string;
  platform: MediaPlatform;
  platformStatus?: MediaPlatformStatus;
  resourceStatus?: MediaResourceStatus;
  spendCap?: number;
  tags?: string[];
  timezone?: string;
  todaySpend?: number;
  whitelistStatus?: MediaWhitelistStatus;
}

export interface UpdateMediaAccountInput {
  accountId: string;
  agencyLineName?: string;
  businessManagerId?: string;
  businessManagerName?: string;
  channelName?: string;
  currency?: string;
  legalEntityName?: string;
  name: string;
  notes?: string;
  platform: MediaPlatform;
  spendCap?: number;
  tags?: string[];
  timezone?: string;
  whitelistStatus?: MediaWhitelistStatus;
}

export interface CreateResourceApplicationInput {
  assigneeId?: string;
  assigneeName?: string;
  expectedReturnAt?: string;
  platform: MediaPlatform;
  projectId: string;
  projectName: string;
  reason: string;
  requestedAccountCount: number;
  requestedById: string;
  requestedByName: string;
  sourceApplicationId?: string;
  sourceTaskId?: string;
  teamId: string;
  teamName: string;
  timezone?: string;
  title?: string;
  whitelistRequired?: boolean;
}

export interface ExceptionActionOptions {
  actor?: AuditActor;
  platformStatus?: MediaPlatformStatus;
}

interface MediaResourceDemoState {
  accounts: MediaAccount[];
  applications: ResourceApplication[];
  assignments: ResourceAssignment[];
  auditLogs: MediaAuditLog[];
  returns: ResourceReturn[];
}

const DEFAULT_ACTOR: AuditActor = {
  id: 'demo-current-user',
  name: '当前用户',
};

function nowIso() {
  return new Date().toISOString();
}

function createId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function toPlainPersistedValue(value: unknown): unknown {
  if (value === null || typeof value !== 'object') return value;
  const raw = toRaw(value);
  if (Array.isArray(raw)) return raw.map((item) => toPlainPersistedValue(item));
  return Object.fromEntries(
    Object.entries(raw).map(([key, item]) => [
      key,
      toPlainPersistedValue(item),
    ]),
  );
}

function clonePersistedArray<T>(value: readonly T[]): T[] {
  // The normalized value strips Vue proxies before it is cloned for the
  // lifecycle service, whose transitions must never mutate store state.
  return structuredClone(toPlainPersistedValue(value)) as T[];
}

function createDemoState(): MediaResourceDemoState {
  const accounts: MediaAccount[] = [
    {
      accountId: 'act_120240810001',
      agencyLineId: 'agency-meta-sea',
      agencyLineName: 'Meta SEA 代理线',
      assignedAt: '2026-07-18T03:20:00.000Z',
      assigneeId: 'user-wang-min',
      assigneeName: '王敏',
      balance: 18_240,
      businessManagerId: 'bm-99810001',
      businessManagerName: 'Starfall SEA BM',
      channelName: 'Meta SEA 渠道',
      createdAt: '2026-05-08T02:10:00.000Z',
      cumulativeSpend: 386_420.5,
      currency: 'USD',
      id: 'media-account-meta-001',
      inboundAt: '2026-05-08T02:10:00.000Z',
      lastSyncedAt: '2026-08-10T09:30:00.000Z',
      legalEntityName: 'MPOWER MEDIA PTE. LTD.',
      name: 'Starfall SEA 主投账户',
      platform: 'facebook',
      platformStatus: 'active',
      projectId: 'project-starfall-sea',
      projectName: 'Starfall 东南亚增长',
      resourceStatus: 'assigned',
      spendCap: 50_000,
      tags: ['主投', '预付', 'SEA'],
      teamId: 'team-growth-sea',
      teamName: '增长一部',
      todaySpend: 3820.42,
      timezone: 'Asia/Singapore',
      updatedAt: '2026-08-10T09:30:00.000Z',
      whitelistStatus: 'approved',
    },
    {
      accountId: 'act_120240810002',
      agencyLineId: 'agency-meta-sea',
      agencyLineName: 'Meta SEA 代理线',
      balance: 31_600,
      businessManagerId: 'bm-99810001',
      businessManagerName: 'Starfall SEA BM',
      channelName: 'Meta SEA 渠道',
      createdAt: '2026-06-12T06:20:00.000Z',
      cumulativeSpend: 128_600,
      currency: 'USD',
      id: 'media-account-meta-002',
      inboundAt: '2026-06-12T06:20:00.000Z',
      lastSyncedAt: '2026-08-10T09:31:00.000Z',
      legalEntityName: 'MPOWER MEDIA PTE. LTD.',
      name: 'Meta SEA 备用账户 02',
      platform: 'facebook',
      platformStatus: 'active',
      resourceStatus: 'available',
      spendCap: 40_000,
      tags: ['备用', '预付', 'SEA'],
      todaySpend: 0,
      timezone: 'Asia/Singapore',
      updatedAt: '2026-08-10T09:31:00.000Z',
      whitelistStatus: 'approved',
    },
    {
      accountId: 'act_120240810004',
      agencyLineId: 'agency-meta-sea',
      agencyLineName: 'Meta SEA 代理线',
      balance: 26_800,
      businessManagerId: 'bm-99810001',
      businessManagerName: 'Starfall SEA BM',
      channelName: 'Meta SEA 渠道',
      createdAt: '2026-07-02T04:20:00.000Z',
      cumulativeSpend: 75_400,
      currency: 'USD',
      id: 'media-account-meta-004',
      inboundAt: '2026-07-02T04:20:00.000Z',
      lastSyncedAt: '2026-08-20T08:20:00.000Z',
      legalEntityName: 'MPOWER MEDIA PTE. LTD.',
      name: 'Meta SEA 备用账户 04',
      platform: 'facebook',
      platformStatus: 'active',
      resourceStatus: 'available',
      spendCap: 35_000,
      tags: ['备用', '预付', 'SEA'],
      todaySpend: 0,
      timezone: 'Asia/Singapore',
      updatedAt: '2026-08-20T08:20:00.000Z',
      whitelistStatus: 'approved',
    },
    {
      accountId: 'act_120240810005',
      agencyLineId: 'agency-meta-sea',
      agencyLineName: 'Meta SEA 代理线',
      balance: 19_450,
      businessManagerId: 'bm-99810001',
      businessManagerName: 'Starfall SEA BM',
      channelName: 'Meta SEA 渠道',
      createdAt: '2026-07-16T03:40:00.000Z',
      cumulativeSpend: 103_800,
      currency: 'USD',
      id: 'media-account-meta-005',
      inboundAt: '2026-07-16T03:40:00.000Z',
      lastSyncedAt: '2026-08-20T08:22:00.000Z',
      legalEntityName: 'MPOWER MEDIA PTE. LTD.',
      name: 'Meta SEA 备用账户 05',
      platform: 'facebook',
      platformStatus: 'active',
      resourceStatus: 'available',
      spendCap: 30_000,
      tags: ['备用', '信用', 'SEA'],
      todaySpend: 0,
      timezone: 'Asia/Singapore',
      updatedAt: '2026-08-20T08:22:00.000Z',
      whitelistStatus: 'approved',
    },
    {
      accountId: 'act_120240810006',
      agencyLineId: 'agency-meta-sea',
      agencyLineName: 'Meta SEA 代理线',
      balance: 42_100,
      businessManagerId: 'bm-99810001',
      businessManagerName: 'Starfall SEA BM',
      channelName: 'Meta SEA 渠道',
      createdAt: '2026-08-02T05:15:00.000Z',
      cumulativeSpend: 245_700,
      currency: 'USD',
      id: 'media-account-meta-006',
      inboundAt: '2026-08-02T05:15:00.000Z',
      lastSyncedAt: '2026-08-20T08:25:00.000Z',
      legalEntityName: 'MPOWER MEDIA PTE. LTD.',
      name: 'Meta SEA 高额度账户 06',
      platform: 'facebook',
      platformStatus: 'active',
      resourceStatus: 'available',
      spendCap: 60_000,
      tags: ['备用', '高额度', 'SEA'],
      todaySpend: 0,
      timezone: 'Asia/Singapore',
      updatedAt: '2026-08-20T08:25:00.000Z',
      whitelistStatus: 'approved',
    },
    {
      accountId: 'act_120240810003',
      agencyLineId: 'agency-meta-jp',
      agencyLineName: 'Meta 日本代理线',
      businessManagerId: 'bm-99810009',
      businessManagerName: 'Japan Growth BM',
      channelName: 'Meta 日本渠道',
      createdAt: '2026-06-23T05:10:00.000Z',
      cumulativeSpend: 18_200_000,
      currency: 'JPY',
      exceptionAt: '2026-08-09T02:20:00.000Z',
      exceptionPreviousResourceStatus: 'available',
      exceptionReason: '媒体平台风控，账户投放功能受限',
      id: 'media-account-meta-003',
      inboundAt: '2026-06-23T05:10:00.000Z',
      lastSyncedAt: '2026-08-09T02:20:00.000Z',
      legalEntityName: 'MPOWER JAPAN GK',
      name: 'Meta JP 增长账户',
      platform: 'facebook',
      platformStatus: 'restricted',
      resourceStatus: 'exception',
      spendCap: 6_000_000,
      tags: ['日本', '待解限'],
      todaySpend: 0,
      timezone: 'Asia/Tokyo',
      updatedAt: '2026-08-09T02:20:00.000Z',
      whitelistStatus: 'pending',
    },
    {
      accountId: '751-820-4100',
      agencyLineId: 'agency-google-global',
      agencyLineName: 'Google Global MCC',
      assignedAt: '2026-07-26T08:00:00.000Z',
      assigneeId: 'user-li-yan',
      assigneeName: '李岩',
      balance: 9850,
      businessManagerId: 'mcc-9001100200',
      businessManagerName: 'Global Growth MCC',
      channelName: 'Google Global 渠道',
      createdAt: '2026-05-17T08:00:00.000Z',
      cumulativeSpend: 142_860.2,
      currency: 'USD',
      id: 'media-account-google-001',
      inboundAt: '2026-05-17T08:00:00.000Z',
      lastSyncedAt: '2026-08-10T08:40:00.000Z',
      legalEntityName: 'MPOWER MEDIA PTE. LTD.',
      name: 'Solar Quest 全球账户',
      platform: 'google',
      platformStatus: 'active',
      projectId: 'project-solar-global',
      projectName: 'Solar Quest 全球发行',
      resourceStatus: 'assigned',
      spendCap: 30_000,
      tags: ['全球', '信用账户'],
      teamId: 'team-google-global',
      teamName: '海外增长二部',
      todaySpend: 2140.8,
      timezone: 'America/Los_Angeles',
      updatedAt: '2026-08-10T08:40:00.000Z',
      whitelistStatus: 'not_required',
    },
    {
      accountId: '751-820-4199',
      agencyLineId: 'agency-google-global',
      agencyLineName: 'Google Global MCC',
      balance: 15_000,
      businessManagerId: 'mcc-9001100200',
      businessManagerName: 'Global Growth MCC',
      channelName: 'Google Global 渠道',
      createdAt: '2026-07-03T04:30:00.000Z',
      cumulativeSpend: 74_200,
      currency: 'USD',
      id: 'media-account-google-002',
      inboundAt: '2026-07-03T04:30:00.000Z',
      lastSyncedAt: '2026-08-10T08:42:00.000Z',
      legalEntityName: 'MPOWER MEDIA PTE. LTD.',
      name: 'Google Global 储备账户',
      platform: 'google',
      platformStatus: 'active',
      resourceStatus: 'available',
      spendCap: 25_000,
      tags: ['储备', '信用账户'],
      todaySpend: 0,
      timezone: 'America/Los_Angeles',
      updatedAt: '2026-08-10T08:42:00.000Z',
      whitelistStatus: 'not_required',
    },
    {
      accountId: 'tt-709881001',
      agencyLineId: 'agency-tiktok-sea',
      agencyLineName: 'TikTok SEA 代理线',
      balance: 12_800,
      businessManagerId: 'bc-7188001',
      businessManagerName: 'Neon SEA BC',
      channelName: 'TikTok SEA 渠道',
      createdAt: '2026-07-14T01:20:00.000Z',
      cumulativeSpend: 168_400,
      currency: 'USD',
      id: 'media-account-tiktok-001',
      inboundAt: '2026-07-14T01:20:00.000Z',
      lastSyncedAt: '2026-08-10T07:50:00.000Z',
      legalEntityName: 'MPOWER MEDIA PTE. LTD.',
      name: 'TikTok SEA 资源账户 01',
      platform: 'tiktok',
      platformStatus: 'active',
      resourceStatus: 'available',
      spendCap: 20_000,
      tags: ['SEA', '预付'],
      todaySpend: 0,
      timezone: 'Asia/Singapore',
      updatedAt: '2026-08-10T07:50:00.000Z',
      whitelistStatus: 'approved',
    },
    {
      accountId: 'tt-709881008',
      agencyLineId: 'agency-tiktok-jp',
      agencyLineName: 'TikTok 日本代理线',
      assignedAt: '2026-07-02T02:00:00.000Z',
      assigneeId: 'user-zhao-ning',
      assigneeName: '赵宁',
      balance: 7420,
      businessManagerId: 'bc-7188009',
      businessManagerName: 'Japan Launch BC',
      channelName: 'TikTok 日本渠道',
      createdAt: '2026-06-28T06:10:00.000Z',
      cumulativeSpend: 2_740_800,
      currency: 'JPY',
      id: 'media-account-tiktok-002',
      inboundAt: '2026-06-28T06:10:00.000Z',
      lastSyncedAt: '2026-08-10T08:10:00.000Z',
      legalEntityName: 'MPOWER JAPAN GK',
      name: 'TikTok 日本首发账户',
      platform: 'tiktok',
      platformStatus: 'active',
      projectId: 'project-neon-jp',
      projectName: 'Neon Drift 日本首发',
      resourceStatus: 'pending_return',
      spendCap: 3_000_000,
      tags: ['日本', '待回收'],
      teamId: 'team-japan-launch',
      teamName: '日本发行组',
      todaySpend: 980_000,
      timezone: 'Asia/Tokyo',
      updatedAt: '2026-08-10T08:10:00.000Z',
      whitelistStatus: 'approved',
    },
    {
      accountId: 'kwai-64001288',
      agencyLineId: 'agency-kwai-br',
      agencyLineName: 'Kwai 巴西代理线',
      balance: 44_500,
      channelName: 'Kwai Brasil 渠道',
      createdAt: '2026-07-20T04:30:00.000Z',
      cumulativeSpend: 900_000,
      currency: 'BRL',
      id: 'media-account-kwai-001',
      inboundAt: '2026-07-20T04:30:00.000Z',
      lastSyncedAt: '2026-08-10T07:20:00.000Z',
      legalEntityName: 'MPOWER BRASIL LTDA.',
      name: 'Kwai BR 资源账户',
      platform: 'kwai',
      platformStatus: 'active',
      resourceStatus: 'available',
      spendCap: 80_000,
      tags: ['巴西', '本地币'],
      todaySpend: 0,
      timezone: 'America/Sao_Paulo',
      updatedAt: '2026-08-10T07:20:00.000Z',
      whitelistStatus: 'not_required',
    },
  ];

  const applications: ResourceApplication[] = [
    {
      applicationNo: 'MR-20260718-001',
      approvedAccountIds: ['media-account-meta-001'],
      assigneeId: 'user-wang-min',
      assigneeName: '王敏',
      createdAt: '2026-07-17T08:30:00.000Z',
      expectedReturnAt: '2026-10-31T15:59:59.000Z',
      id: 'resource-application-001',
      platform: 'facebook',
      projectId: 'project-starfall-sea',
      projectName: 'Starfall 东南亚增长',
      reason: '东南亚首发阶段需要独立主投账户承接预算。',
      requestedAccountCount: 1,
      requestedById: 'user-lin-yue',
      requestedByName: '林悦',
      reviewedAt: '2026-07-18T03:20:00.000Z',
      reviewedById: 'user-media-lead',
      reviewedByName: '周媒介',
      status: 'approved',
      teamId: 'team-growth-sea',
      teamName: '增长一部',
      title: 'Starfall SEA 广告账户申请',
      updatedAt: '2026-07-18T03:20:00.000Z',
    },
    {
      applicationNo: 'MR-20260810-002',
      approvedAccountIds: [],
      assigneeId: 'user-chen-hao',
      assigneeName: '陈昊',
      createdAt: '2026-08-10T02:15:00.000Z',
      expectedReturnAt: '2026-11-30T15:59:59.000Z',
      id: 'resource-application-002',
      platform: 'tiktok',
      projectId: 'project-neon-sea',
      projectName: 'Neon Drift 东南亚预热',
      reason: 'TikTok 预热与正式上线需要两个相互隔离的投放账户。',
      requestedAccountCount: 2,
      requestedById: 'user-lin-yue',
      requestedByName: '林悦',
      status: 'pending',
      teamId: 'team-growth-sea',
      teamName: '增长一部',
      title: 'Neon Drift TikTok SEA 账户申请',
      updatedAt: '2026-08-10T02:15:00.000Z',
    },
    {
      applicationNo: 'MR-20260726-003',
      approvedAccountIds: ['media-account-google-001'],
      assigneeId: 'user-li-yan',
      assigneeName: '李岩',
      createdAt: '2026-07-25T05:40:00.000Z',
      id: 'resource-application-003',
      platform: 'google',
      projectId: 'project-solar-global',
      projectName: 'Solar Quest 全球发行',
      reason: '全球搜索与 UAC 投放需要独立信用账户。',
      requestedAccountCount: 1,
      requestedById: 'user-zhao-ning',
      requestedByName: '赵宁',
      reviewedAt: '2026-07-26T08:00:00.000Z',
      reviewedById: 'user-media-lead',
      reviewedByName: '周媒介',
      status: 'approved',
      teamId: 'team-google-global',
      teamName: '海外增长二部',
      title: 'Solar Quest Google Ads 账户申请',
      updatedAt: '2026-07-26T08:00:00.000Z',
    },
    {
      applicationNo: 'MR-20260806-004',
      approvedAccountIds: ['media-account-tiktok-002'],
      assigneeId: 'user-zhao-ning',
      assigneeName: '赵宁',
      createdAt: '2026-06-30T03:10:00.000Z',
      id: 'resource-application-004',
      platform: 'tiktok',
      projectId: 'project-neon-jp',
      projectName: 'Neon Drift 日本首发',
      reason: '日本首发专项投放。',
      requestedAccountCount: 1,
      requestedById: 'user-zhao-ning',
      requestedByName: '赵宁',
      reviewedAt: '2026-07-02T02:00:00.000Z',
      reviewedById: 'user-media-lead',
      reviewedByName: '周媒介',
      status: 'approved',
      teamId: 'team-japan-launch',
      teamName: '日本发行组',
      title: 'Neon Drift TikTok 日本账户申请',
      updatedAt: '2026-07-02T02:00:00.000Z',
    },
  ];

  const assignments: ResourceAssignment[] = [
    {
      applicationId: 'resource-application-001',
      assignedAt: '2026-07-18T03:20:00.000Z',
      assignedById: 'user-media-lead',
      assignedByName: '周媒介',
      assigneeId: 'user-wang-min',
      assigneeName: '王敏',
      id: 'resource-assignment-001',
      mediaAccountId: 'media-account-meta-001',
      platformAccountId: 'act_120240810001',
      projectId: 'project-starfall-sea',
      projectName: 'Starfall 东南亚增长',
      status: 'active',
      teamId: 'team-growth-sea',
      teamName: '增长一部',
      updatedAt: '2026-07-18T03:20:00.000Z',
    },
    {
      applicationId: 'resource-application-003',
      assignedAt: '2026-07-26T08:00:00.000Z',
      assignedById: 'user-media-lead',
      assignedByName: '周媒介',
      assigneeId: 'user-li-yan',
      assigneeName: '李岩',
      id: 'resource-assignment-002',
      mediaAccountId: 'media-account-google-001',
      platformAccountId: '751-820-4100',
      projectId: 'project-solar-global',
      projectName: 'Solar Quest 全球发行',
      status: 'active',
      teamId: 'team-google-global',
      teamName: '海外增长二部',
      updatedAt: '2026-07-26T08:00:00.000Z',
    },
    {
      applicationId: 'resource-application-004',
      assignedAt: '2026-07-02T02:00:00.000Z',
      assignedById: 'user-media-lead',
      assignedByName: '周媒介',
      assigneeId: 'user-zhao-ning',
      assigneeName: '赵宁',
      id: 'resource-assignment-003',
      mediaAccountId: 'media-account-tiktok-002',
      platformAccountId: 'tt-709881008',
      projectId: 'project-neon-jp',
      projectName: 'Neon Drift 日本首发',
      status: 'return_requested',
      teamId: 'team-japan-launch',
      teamName: '日本发行组',
      updatedAt: '2026-08-10T08:10:00.000Z',
    },
  ];

  const returns: ResourceReturn[] = [
    {
      accountName: 'TikTok 日本首发账户',
      id: 'resource-return-001',
      mediaAccountId: 'media-account-tiktok-002',
      platformAccountId: 'tt-709881008',
      projectId: 'project-neon-jp',
      projectName: 'Neon Drift 日本首发',
      reason: '首发阶段结束，账户交回媒介资源池。',
      requestedAt: '2026-08-10T08:10:00.000Z',
      requestedById: 'user-zhao-ning',
      requestedByName: '赵宁',
      resourceAssignmentId: 'resource-assignment-003',
      status: 'requested',
      updatedAt: '2026-08-10T08:10:00.000Z',
    },
  ];

  const auditLogs: MediaAuditLog[] = [
    {
      action: 'return.requested',
      actorId: 'user-zhao-ning',
      actorName: '赵宁',
      createdAt: '2026-08-10T08:10:00.000Z',
      entityId: 'resource-return-001',
      entityType: 'return',
      id: 'media-audit-demo-001',
      message: '提交 TikTok 日本首发账户回收申请',
      metadata: { mediaAccountId: 'media-account-tiktok-002' },
      result: 'success',
    },
    {
      action: 'exception.marked',
      actorId: 'user-media-lead',
      actorName: '周媒介',
      createdAt: '2026-08-09T02:20:00.000Z',
      entityId: 'media-account-meta-003',
      entityType: 'account',
      id: 'media-audit-demo-002',
      message: 'Meta JP 增长账户被标记为异常',
      metadata: { reason: '媒体平台风控，账户投放功能受限' },
      result: 'success',
    },
    {
      action: 'application.approved',
      actorId: 'user-media-lead',
      actorName: '周媒介',
      createdAt: '2026-07-26T08:00:00.000Z',
      entityId: 'resource-application-003',
      entityType: 'application',
      id: 'media-audit-demo-003',
      message: '批准 Solar Quest Google Ads 账户申请并完成分配',
      metadata: { accountIds: ['media-account-google-001'] },
      result: 'success',
    },
  ];

  return { accounts, applications, assignments, auditLogs, returns };
}

export const useMediaResourceStore = defineStore(
  'fusion-media-resource',
  () => {
    const initialState = createDemoState();
    const accounts = useStorage<MediaAccount[]>(
      'fusion:media-resource:accounts',
      initialState.accounts,
    );
    const applications = useStorage<ResourceApplication[]>(
      'fusion:media-resource:applications',
      initialState.applications,
    );
    const assignments = useStorage<ResourceAssignment[]>(
      'fusion:media-resource:assignments',
      initialState.assignments,
    );
    const returns = useStorage<ResourceReturn[]>(
      'fusion:media-resource:returns',
      initialState.returns,
    );
    const auditLogs = useStorage<MediaAuditLog[]>(
      'fusion:media-resource:audit-logs',
      initialState.auditLogs,
    );

    // Keep persisted demo records compatible when the front-end model gains
    // new platform-fact fields. Business assignment state is never restored
    // from fixtures here, so completed returns remain completed.
    const demoAccountsById = new Map(
      initialState.accounts.map((account) => [account.id, account]),
    );
    accounts.value = accounts.value.map((account) => {
      const demo = demoAccountsById.get(account.id);
      if (!demo) return account;
      return {
        ...account,
        channelName: account.channelName ?? demo.channelName,
        cumulativeSpend: account.cumulativeSpend ?? demo.cumulativeSpend,
        inboundAt: account.inboundAt ?? demo.inboundAt,
        lastSyncedAt: account.lastSyncedAt ?? demo.lastSyncedAt,
        legalEntityName: account.legalEntityName ?? demo.legalEntityName,
        todaySpend: account.todaySpend ?? demo.todaySpend,
        whitelistStatus: account.whitelistStatus ?? demo.whitelistStatus,
      };
    });
    const persistedAccountIds = new Set(
      accounts.value.map((account) => account.id),
    );
    const missingDemoAccounts = initialState.accounts.filter(
      (account) => !persistedAccountIds.has(account.id),
    );
    if (missingDemoAccounts.length > 0) {
      accounts.value = [...accounts.value, ...missingDemoAccounts];
    }

    const availableAccounts = computed(() =>
      accounts.value.filter(
        (account) =>
          account.platformStatus === 'active' &&
          account.resourceStatus === 'available',
      ),
    );
    const pendingApplications = computed(() =>
      applications.value.filter((application) =>
        ['partially_approved', 'pending'].includes(application.status),
      ),
    );
    const activeAssignments = computed(() =>
      assignments.value.filter((assignment) => assignment.status === 'active'),
    );
    const pendingReturns = computed(() =>
      returns.value.filter((item) => item.status === 'requested'),
    );
    const exceptionAccounts = computed(() =>
      accounts.value.filter(
        (account) => account.resourceStatus === 'exception',
      ),
    );
    const returnRequests = computed(() => returns.value);
    const exceptions = computed(() => exceptionAccounts.value);

    function writeAudit(
      input: Omit<MediaAuditLog, 'createdAt' | 'id'> & { createdAt?: string },
    ) {
      const entry: MediaAuditLog = {
        ...input,
        createdAt: input.createdAt ?? nowIso(),
        id: createId('media-audit'),
      };
      auditLogs.value = [entry, ...auditLogs.value].slice(0, 500);
      return entry;
    }

    function failAction(
      action: MediaAuditAction,
      entityType: MediaAuditLog['entityType'],
      entityId: string,
      message: string,
      actor: AuditActor = DEFAULT_ACTOR,
      metadata?: Record<string, unknown>,
    ): never {
      writeAudit({
        action,
        actorId: actor.id,
        actorName: actor.name,
        entityId,
        entityType,
        message,
        metadata,
        result: 'failed',
      });
      throw new Error(message);
    }

    function lifecycleState(): ResourceLifecycleState {
      return {
        accounts: clonePersistedArray(accounts.value),
        applications: clonePersistedArray(applications.value),
        assignments: clonePersistedArray(assignments.value),
        returns: clonePersistedArray(returns.value),
      };
    }

    function commitLifecycle<T>(
      transition: ResourceLifecycleTransition<T>,
      actor: AuditActor,
    ) {
      accounts.value = transition.state.accounts;
      applications.value = transition.state.applications;
      assignments.value = transition.state.assignments;
      returns.value = transition.state.returns;
      writeAudit({
        ...transition.audit,
        actorId: actor.id,
        actorName: actor.name,
        result: 'success',
      });
      return transition.result;
    }

    function runLifecycle<T>(
      action: MediaAuditAction,
      entityType: MediaAuditLog['entityType'],
      entityId: string,
      actor: AuditActor,
      operation: () => ResourceLifecycleTransition<T>,
    ) {
      try {
        return commitLifecycle(operation(), actor);
      } catch (error) {
        return failAction(
          action,
          entityType,
          entityId,
          error instanceof Error ? error.message : '资源生命周期操作失败',
          actor,
        );
      }
    }

    function resetDemo(actor: AuditActor = DEFAULT_ACTOR) {
      const demo = createDemoState();
      accounts.value = demo.accounts;
      applications.value = demo.applications;
      assignments.value = demo.assignments;
      returns.value = demo.returns;
      auditLogs.value = demo.auditLogs;
      writeAudit({
        action: 'demo.reset',
        actorId: actor.id,
        actorName: actor.name,
        entityId: 'media-resource-demo',
        entityType: 'demo',
        message: '已重置媒介资源 Demo 数据',
        result: 'success',
      });
    }

    function createAccount(
      input: CreateMediaAccountInput,
      actor: AuditActor = DEFAULT_ACTOR,
    ) {
      return runLifecycle(
        'account.created',
        'account',
        input.accountId.trim() || 'new-account',
        actor,
        () =>
          resourceLifecycleService.createAccount(
            input,
            actor,
            lifecycleState(),
          ),
      );
    }

    function updateAccount(
      mediaAccountId: string,
      input: UpdateMediaAccountInput,
      actor: AuditActor = DEFAULT_ACTOR,
    ) {
      const account = accounts.value.find((item) => item.id === mediaAccountId);
      if (!account) {
        return failAction(
          'account.updated',
          'account',
          mediaAccountId,
          '未找到要编辑的媒体账户',
          actor,
        );
      }

      const accountId = input.accountId.trim();
      const name = input.name.trim();
      if (!accountId || !name) {
        return failAction(
          'account.updated',
          'account',
          mediaAccountId,
          '请填写账户名称和账户 ID',
          actor,
        );
      }
      const duplicate = accounts.value.find(
        (item) => item.id !== mediaAccountId && item.accountId === accountId,
      );
      if (duplicate) {
        return failAction(
          'account.updated',
          'account',
          mediaAccountId,
          `账户 ID ${accountId} 已存在`,
          actor,
        );
      }

      const updated: MediaAccount = {
        ...account,
        ...input,
        accountId,
        name,
        tags: input.tags ?? account.tags,
        updatedAt: nowIso(),
      };
      accounts.value = accounts.value.map((item) =>
        item.id === mediaAccountId ? updated : item,
      );
      writeAudit({
        action: 'account.updated',
        actorId: actor.id,
        actorName: actor.name,
        after: {
          accountId: updated.accountId,
          name: updated.name,
          platform: updated.platform,
        },
        before: {
          accountId: account.accountId,
          name: account.name,
          platform: account.platform,
        },
        entityId: mediaAccountId,
        entityType: 'account',
        message: `已编辑媒体账户 ${updated.name}`,
        result: 'success',
      });
      return updated;
    }

    function createApplication(
      input: CreateResourceApplicationInput,
      actor?: AuditActor,
    ) {
      const resolvedActor = actor ?? {
        id: input.requestedById,
        name: input.requestedByName,
      };
      return runLifecycle(
        'application.created',
        'application',
        'new-application',
        resolvedActor,
        () =>
          resourceLifecycleService.createApplication(
            input,
            resolvedActor,
            lifecycleState(),
          ),
      );
    }

    function approveApplication(
      applicationId: string,
      accountIds: string[],
      actor: AuditActor = DEFAULT_ACTOR,
    ) {
      return runLifecycle(
        'application.approved',
        'application',
        applicationId,
        actor,
        () =>
          resourceLifecycleService.approveApplication(
            { accountIds, actor, applicationId },
            lifecycleState(),
          ),
      );
    }

    function rejectApplication(
      applicationId: string,
      reason = '未通过媒介资源审批',
      actor: AuditActor = DEFAULT_ACTOR,
    ) {
      return runLifecycle(
        'application.rejected',
        'application',
        applicationId,
        actor,
        () =>
          resourceLifecycleService.rejectApplication(
            { actor, applicationId, reason },
            lifecycleState(),
          ),
      );
    }

    function requestReturn(
      assignmentOrAccountId: string,
      reason = '项目阶段结束，申请回收媒体账户',
      actor: AuditActor = DEFAULT_ACTOR,
    ) {
      return runLifecycle(
        'return.requested',
        'return',
        assignmentOrAccountId,
        actor,
        () =>
          resourceLifecycleService.requestReturn(
            { actor, assignmentOrAccountId, reason },
            lifecycleState(),
          ),
      );
    }

    function completeReturn(
      returnId: string,
      outcomeOrActor: AuditActor | ResourceResolutionOutcome = 'available',
      actionActor: AuditActor = DEFAULT_ACTOR,
    ) {
      const outcome =
        typeof outcomeOrActor === 'string' ? outcomeOrActor : 'available';
      const actor =
        typeof outcomeOrActor === 'string' ? actionActor : outcomeOrActor;
      return runLifecycle('return.completed', 'return', returnId, actor, () =>
        resourceLifecycleService.completeReturn(
          { actor, outcome, returnId },
          lifecycleState(),
        ),
      );
    }

    function markException(
      accountId: string,
      reason = '人工标记异常',
      options: ExceptionActionOptions = {},
    ) {
      const actor = options.actor ?? DEFAULT_ACTOR;
      return runLifecycle('exception.marked', 'account', accountId, actor, () =>
        resourceLifecycleService.markException(
          accountId,
          reason,
          options,
          lifecycleState(),
        ),
      );
    }

    function resolveException(
      accountId: string,
      outcome: ResourceResolutionOutcome = 'available',
      note = '异常已处理',
      actor: AuditActor = DEFAULT_ACTOR,
    ) {
      return runLifecycle(
        'exception.resolved',
        'account',
        accountId,
        actor,
        () =>
          resourceLifecycleService.resolveException(
            { accountId, actor, note, outcome },
            lifecycleState(),
          ),
      );
    }

    return {
      accounts,
      activeAssignments,
      applications,
      approveApplication,
      assignments,
      auditLogs,
      availableAccounts,
      completeReturn,
      createAccount,
      createApplication,
      exceptionAccounts,
      exceptions,
      markException,
      pendingApplications,
      pendingReturns,
      rejectApplication,
      requestReturn,
      resetDemo,
      resolveException,
      returnRequests,
      returns,
      updateAccount,
    };
  },
);
