import type {
  ApplicationApprovalRecord,
  ApprovalAction,
  ResourceApplication,
  ResourceApplicationSeed,
} from '#/domain/application';

import { toRaw } from 'vue';

import { useStorage } from '@vueuse/core';
import { defineStore } from 'pinia';

import {
  applicationWorkflowService,
  legacyApplicationAdapter,
} from '#/domain/application';

export {
  applicationTypeLabels,
  approvalRoleForType,
  approvalRoleMeta,
} from '#/domain/application';
export type {
  ApplicationApprovalNode,
  ApplicationApprovalNodeStatus,
  ApplicationApprovalRole,
  ApplicationCategory,
  ApplicationComment,
  ApplicationStatus,
  ApplicationType,
  ApprovalAction,
  ResourceApplication,
} from '#/domain/application';

export const RESOURCE_APPLICATION_STORAGE_KEY =
  'adpulse-workbench-resource-applications';

const STORE_MIGRATION_KEY = 'adpulse-workbench-resource-applications:v3';

function historyRecord(
  id: string,
  action: ApprovalAction,
  actor: string,
  actorRole: string,
  at: string,
  remark: string,
): ApplicationApprovalRecord {
  return { action, actor, actorRole, at, id, remark };
}

function createInitialApplications(): ResourceApplicationSeed[] {
  return [
    {
      id: 'REQ-20260811-001',
      type: 'account',
      title: 'TikTok 日本首发账户 2 个',
      project: 'Pixel Quest 日本首发',
      requester: '赵宁',
      createdAt: '2026-08-11 09:30',
      updatedAt: '2026-08-11 09:30',
      status: 'pending',
      description: 'JPY 账户，GMT+9，需绑定日本代理线。',
      platform: 'TikTok',
      quantity: 2,
      approvalRole: 'media',
      approver: '周敏',
      approvalRecords: [
        historyRecord(
          'APR-20260811-001',
          'submitted',
          '赵宁',
          '申请人',
          '2026-08-11 09:30',
          '申请已提交至媒介审批。',
        ),
      ],
    },
    {
      id: 'REQ-20260810-016',
      type: 'pixel',
      title: 'Starfall 官网 Purchase 像素',
      project: 'Starfall 全球增长',
      requester: '陈航',
      createdAt: '2026-08-10 16:42',
      updatedAt: '2026-08-10 17:08',
      status: 'processing',
      description: '需开通 Purchase、Install、CompleteRegistration 事件。',
      platform: 'Facebook',
      approvalRole: 'media',
      approver: '周敏',
      approvalRecords: [
        historyRecord(
          'APR-20260810-016-1',
          'submitted',
          '陈航',
          '申请人',
          '2026-08-10 16:42',
          '申请已提交至媒介审批。',
        ),
        historyRecord(
          'APR-20260810-016-2',
          'approved',
          '周敏',
          '媒介审批',
          '2026-08-10 17:08',
          '事件范围与项目归属清晰，同意开通。',
        ),
      ],
    },
    {
      id: 'REQ-20260810-009',
      type: 'tg',
      title: 'Project Ark TG 运营账号',
      project: 'Project Ark 美国市场',
      requester: '林琦',
      createdAt: '2026-08-10 11:18',
      updatedAt: '2026-08-10 13:05',
      status: 'approved',
      description: '用于异常告警和素材审批通知。',
      platform: 'Telegram',
      approvalRole: 'media',
      approver: '周敏',
      approvalRecords: [
        historyRecord(
          'APR-20260810-009-1',
          'submitted',
          '林琦',
          '申请人',
          '2026-08-10 11:18',
          '申请已提交至媒介审批。',
        ),
        historyRecord(
          'APR-20260810-009-2',
          'approved',
          '周敏',
          '媒介审批',
          '2026-08-10 13:05',
          '用途符合项目通知规范，同意申请。',
        ),
      ],
    },
    {
      id: 'REQ-20260809-021',
      type: 'computer',
      title: '素材组剪辑电脑',
      project: '内部资源 / 非项目',
      requester: '李想',
      createdAt: '2026-08-09 14:05',
      updatedAt: '2026-08-09 14:05',
      status: 'pending',
      description: '需满足 4K 视频剪辑和本地 AI 推理。',
      quantity: 1,
      approvalRole: 'office',
      approver: '郑然',
      approvalRecords: [
        historyRecord(
          'APR-20260809-021',
          'submitted',
          '李想',
          '申请人',
          '2026-08-09 14:05',
          '申请已提交至行政与资产审批。',
        ),
      ],
    },
    {
      id: 'REQ-20260808-008',
      type: 'mobile',
      title: 'Facebook 验证手机号',
      project: 'Starfall 全球增长',
      requester: '媒介二组',
      createdAt: '2026-08-08 10:22',
      updatedAt: '2026-08-08 15:30',
      status: 'approved',
      description: '用于新广告账户安全验证。',
      quantity: 3,
      approvalRole: 'office',
      approver: '郑然',
      approvalRecords: [
        historyRecord(
          'APR-20260808-008-1',
          'submitted',
          '媒介二组',
          '申请人',
          '2026-08-08 10:22',
          '申请已提交至行政与资产审批。',
        ),
        historyRecord(
          'APR-20260808-008-2',
          'approved',
          '郑然',
          '行政与资产审批',
          '2026-08-08 15:30',
          '库存可满足，领用人和项目归属清晰。',
        ),
      ],
    },
    {
      id: 'REQ-20260807-003',
      type: 'payment',
      title: 'Google Ads 8 月预算充值',
      project: 'Project Ark 美国市场',
      requester: '林琦',
      createdAt: '2026-08-07 09:12',
      updatedAt: '2026-08-07 10:16',
      currency: 'USD',
      status: 'rejected',
      description: '申请 Google Ads 8 月扩量预算充值。',
      amount: 6800,
      platform: 'Google',
      approvalRole: 'finance',
      approver: '王楠',
      approvalRecords: [
        historyRecord(
          'APR-20260807-003-1',
          'submitted',
          '林琦',
          '申请人',
          '2026-08-07 09:12',
          '申请已提交至财务审批。',
        ),
        historyRecord(
          'APR-20260807-003-2',
          'rejected',
          '王楠',
          '财务审批',
          '2026-08-07 10:16',
          '预算附件不完整，请补充投放计划与余额截图。',
        ),
      ],
    },
    {
      id: 'REQ-20260811-024',
      type: 'payment',
      title: 'Starfall Meta 周预算补充',
      project: 'Starfall 全球增长',
      requester: '陈航',
      createdAt: '2026-08-11 10:06',
      updatedAt: '2026-08-11 10:06',
      currency: 'USD',
      status: 'pending',
      description: '补充美国与加拿大两组广告账户未来 7 天预算。',
      amount: 12_000,
      platform: 'Facebook',
      approvalRole: 'finance',
      approver: '王楠',
      approvalRecords: [
        historyRecord(
          'APR-20260811-024',
          'submitted',
          '陈航',
          '申请人',
          '2026-08-11 10:06',
          '申请已提交至财务审批。',
        ),
      ],
    },
    {
      id: 'REQ-20260806-014',
      type: 'payment',
      title: 'Pixel Quest 日本代理服务结算',
      project: 'Pixel Quest 日本首发',
      requester: '赵宁',
      createdAt: '2026-08-06 09:26',
      updatedAt: '2026-08-06 11:40',
      currency: 'JPY',
      status: 'approved',
      description: '结算日本区域 7 月代理服务费用。',
      amount: 460_000,
      approvalRole: 'finance',
      approver: '王楠',
      approvalRecords: [
        historyRecord(
          'APR-20260806-014-1',
          'submitted',
          '赵宁',
          '申请人',
          '2026-08-06 09:26',
          '申请已提交至财务审批。',
        ),
        historyRecord(
          'APR-20260806-014-2',
          'approved',
          '王楠',
          '财务审批',
          '2026-08-06 11:40',
          '合同与结算金额一致，同意付款。',
        ),
      ],
    },
  ];
}

function normalizeApplication(application: ResourceApplicationSeed) {
  return legacyApplicationAdapter.normalize(application);
}

function migrateApplications(records: ResourceApplication[]) {
  const normalizedById = new Map<string, ResourceApplication>();
  for (const record of records) {
    const normalizedId = String(record.id);
    if (!normalizedById.has(normalizedId)) {
      normalizedById.set(
        normalizedId,
        normalizeApplication({ ...record, id: normalizedId }),
      );
    }
  }
  const normalized = [...normalizedById.values()];

  try {
    const existingIds = new Set(normalized.map((record) => record.id));
    const financeExamples = createInitialApplications().filter((record) =>
      ['REQ-20260806-014', 'REQ-20260811-024'].includes(record.id),
    );
    for (const record of financeExamples) {
      if (!existingIds.has(record.id)) {
        normalized.push(normalizeApplication(record));
      }
    }
    localStorage.setItem(STORE_MIGRATION_KEY, 'done');
  } catch {
    // Local storage is optional; normalized in-memory data remains usable.
  }

  return normalized;
}

export const useResourceApplicationStore = defineStore(
  'adpulse-resource-applications',
  () => {
    const applications = useStorage<ResourceApplication[]>(
      RESOURCE_APPLICATION_STORAGE_KEY,
      createInitialApplications().map((record) => normalizeApplication(record)),
    );

    applications.value = migrateApplications(applications.value);

    function upsertApplication(application: ResourceApplication) {
      const normalized = normalizeApplication(application);
      const index = applications.value.findIndex(
        (item) => item.id === normalized.id,
      );
      if (index === -1) {
        applications.value.unshift(normalized);
      } else {
        applications.value[index] = normalized;
      }
      return normalized;
    }

    function removeApplication(applicationId: string) {
      applications.value = applications.value.filter(
        (application) => application.id !== applicationId,
      );
    }

    /**
     * Retains object identity for open legacy detail panels while persisting to
     * the original raw-array key through Pinia/useStorage.
     */
    function applyWorkflowResult(
      applicationId: string,
      transform: (application: ResourceApplication) => ResourceApplication,
    ) {
      const application = applications.value.find(
        (item) => item.id === applicationId,
      );
      if (!application) return false;
      try {
        Object.assign(
          application,
          transform(structuredClone(toRaw(application))),
        );
        return true;
      } catch {
        return false;
      }
    }

    function approveApplication(
      applicationId: string,
      actor: string,
      actorRole: string,
      remark: string,
    ) {
      return applyWorkflowResult(applicationId, (application) =>
        applicationWorkflowService.approve(application, {
          actor: { name: actor, role: actorRole },
          remark,
        }),
      );
    }

    function rejectApplication(
      applicationId: string,
      actor: string,
      actorRole: string,
      remark: string,
    ) {
      return applyWorkflowResult(applicationId, (application) =>
        applicationWorkflowService.reject(application, {
          actor: { name: actor, role: actorRole },
          remark,
        }),
      );
    }

    function isParticipant(applicationId: string, actor: string) {
      const application = applications.value.find(
        (item) => item.id === applicationId,
      );
      return application
        ? applicationWorkflowService.canComment(application, actor)
        : false;
    }

    function addComment(
      applicationId: string,
      actor: string,
      actorRole: string,
      content: string,
    ) {
      return applyWorkflowResult(applicationId, (application) =>
        applicationWorkflowService.comment(application, {
          actor: { name: actor, role: actorRole },
          content,
        }),
      );
    }

    function markCommentsRead(applicationId: string, actor: string) {
      return applyWorkflowResult(applicationId, (application) =>
        applicationWorkflowService.markCommentsRead(application, actor),
      );
    }

    function resubmitApplication(
      applicationId: string,
      actor: string,
      actorRole: string,
      remark: string,
    ) {
      return applyWorkflowResult(applicationId, (application) =>
        applicationWorkflowService.resubmit(application, {
          actor: { name: actor, role: actorRole },
          remark,
        }),
      );
    }

    function unreadCommentCount(applicationId: string, actor: string) {
      const application = applications.value.find(
        (item) => item.id === applicationId,
      );
      return application
        ? applicationWorkflowService.unreadCommentCount(application, actor)
        : 0;
    }

    return {
      applications,
      addComment,
      approveApplication,
      isParticipant,
      markCommentsRead,
      rejectApplication,
      removeApplication,
      resubmitApplication,
      unreadCommentCount,
      upsertApplication,
    };
  },
);
