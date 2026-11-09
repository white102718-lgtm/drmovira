import type { TaskDetail } from '#/api';

import { describe, expect, it } from 'vitest';

import { projectDeliveryTaskDetail } from './task-detail';

function deliveryDetail(): TaskDetail {
  return {
    allocations: [
      {
        h5LineCount: 0,
        id: 'allocation-1',
        pwaLineCount: 1,
        sortOrder: 0,
        teamCode: 'MP',
        teamOwnerId: '306',
        teamOwnerName: '张鑫（Davi）',
      },
    ],
    delivery: {
      plannedStartAt: '2026-09-01T09:00:00',
      productUrl: 'https://example.com/test',
      region: '巴西',
      target: '测试附件链路',
    },
    deliverySubmissions: [],
    materialSubmissions: [],
    materialRequirements: [],
    platforms: ['Facebook'],
    referenceLinks: [],
    sizes: [],
    task: {
      createdAt: '2026-08-31T15:00:00',
      creatorId: '1',
      creatorName: '测试用户',
      description: '测试附件链路',
      dueAt: '2026-09-02T18:00:00',
      followed: false,
      id: '14',
      priority: 'P1',
      projectId: '9',
      status: 'PENDING_ASSIGNMENT',
      taskCode: 'TASK-14',
      taskType: 'DELIVERY',
      title: '附件链路自动化测试',
      updatedAt: '2026-08-31T15:00:00',
      version: 0,
    },
    taskFiles: [
      {
        extension: 'xlsx',
        fileSize: 1024,
        id: 'file-1',
        mimeType:
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        originalName: '渠道账户数据_2026-08-31.xlsx',
        sortOrder: 0,
        targetId: '14',
        targetType: 'DELIVERY_TASK',
        usageType: 'ATTACHMENT',
      },
      {
        extension: 'xlsx',
        fileSize: 2048,
        id: 'submission-file',
        mimeType: 'application/octet-stream',
        originalName: '交付证明.xlsx',
        sortOrder: 0,
        targetId: '20',
        targetType: 'DELIVERY_SUBMISSION',
        usageType: 'PROOF',
      },
    ],
  };
}

describe('projectDeliveryTaskDetail', () => {
  it('投影投放计划并只保留任务创建附件', () => {
    const result = projectDeliveryTaskDetail(
      deliveryDetail(),
      'Starfall 全球增长',
    );

    expect(result).toMatchObject({
      allocations: [
        {
          assigneeId: '306',
          h5Count: 0,
          owner: '张鑫（Davi）',
          pwaCount: 1,
          team: 'MP',
        },
      ],
      attachments: [
        {
          id: 'file-1',
          name: '渠道账户数据_2026-08-31.xlsx',
          serverFileId: 'file-1',
          size: 1024,
        },
      ],
      dueAt: '2026-09-02 18:00',
      platforms: ['Facebook'],
      projectName: 'Starfall 全球增长',
      region: '巴西',
      startAt: '2026-09-01 09:00',
    });
  });

  it('非投放任务不生成投放计划', () => {
    const detail = deliveryDetail();
    detail.task.taskType = 'MATERIAL';

    expect(projectDeliveryTaskDetail(detail, '测试项目')).toBeUndefined();
  });

  it('截止时间未设置时返回空值而不抛出异常', () => {
    const detail = deliveryDetail();
    detail.task.dueAt = null;

    expect(projectDeliveryTaskDetail(detail, '测试项目')?.dueAt).toBe('');
  });
});
