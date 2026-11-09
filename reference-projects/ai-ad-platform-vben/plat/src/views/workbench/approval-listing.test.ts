import type { ResourceApplication } from '#/domain/application';

import { describe, expect, it } from 'vitest';

import {
  filterApprovalApplications,
  getApprovalDepartmentLabel,
} from './approval-listing';

type ApprovalRecord = ResourceApplication & {
  departmentName?: string;
};

function application(overrides: Partial<ApprovalRecord> = {}): ApprovalRecord {
  return {
    approvalNodes: [],
    approvalRecords: [],
    approvalRole: 'media',
    approver: '周敏',
    ccUsers: [],
    comments: [],
    createdAt: '2026-09-11 10:00:00',
    description: '申请说明',
    id: 'REQ-1',
    project: 'Starfall 全球增长',
    requester: '赵宁',
    requesterId: 'user-zhao',
    requesterName: '赵宁',
    status: 'pending',
    title: '账户申请',
    type: 'account',
    ...overrides,
  };
}

describe('approval listing', () => {
  it('filters approval records by stable department and requester IDs together', () => {
    const result = filterApprovalApplications(
      [
        application({
          departmentId: 'dept-growth',
          departmentName: '增长部',
          id: 'REQ-1',
          requesterId: 'user-zhao',
        }),
        application({
          departmentId: 'dept-growth',
          departmentName: '增长部',
          id: 'REQ-2',
          requester: '陈航',
          requesterId: 'user-chen',
          requesterName: '陈航',
        }),
        application({
          departmentId: 'dept-media',
          departmentName: '媒介部',
          id: 'REQ-3',
        }),
      ],
      { departmentId: 'dept-growth', requesterId: 'user-zhao' },
    );

    expect(result.map((record) => record.id)).toEqual(['REQ-1']);
  });

  it('labels historical approvals without a department as unconfigured', () => {
    expect(getApprovalDepartmentLabel(application())).toBe('未设置');
  });
});
