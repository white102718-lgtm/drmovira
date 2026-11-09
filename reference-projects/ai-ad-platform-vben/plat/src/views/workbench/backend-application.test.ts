import type { AssetApplication } from '#/api/asset-flow';

import { describe, expect, it } from 'vitest';

import { mapBackendApplication } from './backend-application';

function application(
  overrides: Partial<AssetApplication> = {},
): AssetApplication {
  return {
    applicationNo: 'APP-1001',
    approverId: '7',
    approverName: '审批人',
    assetType: 'PAYMENT',
    createdAt: '2026-09-15T09:00:00',
    handlerId: '8',
    handlerName: '办理人',
    id: '1001',
    quantity: 1,
    reason: '测试申请',
    requesterId: '6',
    requesterName: '申请人',
    status: 'APPROVED',
    title: '付款申请',
    updatedAt: '2026-09-15T11:00:00',
    ...overrides,
  };
}

describe('mapBackendApplication', () => {
  it('待审批申请保留抄送人但不伪造已抄送记录', () => {
    const result = mapBackendApplication(
      application({
        ccUsers: [
          {
            active: true,
            displayName: '张三',
            id: '11',
            resolved: true,
          },
        ],
        status: 'PENDING',
      }),
      { name: '当前用户', roleLabel: '审批人' },
    );

    expect(result.ccUsers).toEqual(['张三']);
    expect(result.approvalRecords).not.toContainEqual(
      expect.objectContaining({ action: 'copied' }),
    );
  });

  it('映射多人抄送并生成只读抄送记录', () => {
    const result = mapBackendApplication(
      application({
        ccUsers: [
          {
            active: true,
            displayName: '张三',
            id: '11',
            resolved: true,
          },
          {
            active: false,
            displayName: '李四',
            id: '12',
            resolved: true,
          },
        ],
      }),
      { name: '当前用户', roleLabel: '审批人' },
    );

    expect(result.ccUsers).toEqual(['张三', '李四（已停用）']);
    expect(result.approvalRecords).toContainEqual(
      expect.objectContaining({
        action: 'copied',
        actor: '系统通知',
        remark: '审批结果已抄送：张三、李四（已停用）',
      }),
    );
  });

  it('无人抄送时不生成抄送记录', () => {
    const result = mapBackendApplication(application({ ccUsers: [] }), {
      name: '当前用户',
      roleLabel: '审批人',
    });

    expect(result.ccUsers).toEqual([]);
    expect(result.approvalRecords).not.toContainEqual(
      expect.objectContaining({ action: 'copied' }),
    );
  });

  it('保留无法解析的历史用户 ID，避免误显示为无人抄送', () => {
    const result = mapBackendApplication(
      application({
        ccUsers: [
          {
            active: false,
            displayName: '用户 99',
            id: '99',
            resolved: false,
          },
        ],
      }),
      { name: '当前用户', roleLabel: '审批人' },
    );

    expect(result.ccUsers).toEqual(['用户 99（已无法解析）']);
    expect(result.approvalRecords.at(-1)?.remark).toContain(
      '用户 99（已无法解析）',
    );
  });
});
