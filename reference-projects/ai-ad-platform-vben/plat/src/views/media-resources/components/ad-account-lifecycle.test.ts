import type { AccountLifecycleApplication } from '#/api';

import { describe, expect, it } from 'vitest';

import { successfulApplicationEvents } from './application-lifecycle-events';

function application(
  overrides: Partial<AccountLifecycleApplication> = {},
): AccountLifecycleApplication {
  return {
    actions: [],
    applicationCode: 'ACCOUNT_RECHARGE',
    applicationId: 'application-1',
    createdAt: '2026-09-18T10:00:00',
    status: 'APPROVED',
    title: '广告账户充值申请',
    ...overrides,
  };
}

describe('successfulApplicationEvents', () => {
  it('compresses an approval trail into the final completed event', () => {
    const formFields = [
      {
        fullWidth: false,
        key: 'rechargeAmount',
        label: '充值金额',
        value: 'USD 200.00',
      },
    ];
    const events = successfulApplicationEvents(
      application({
        actions: [
          {
            action: 'SUBMITTED',
            actorName: '申请人',
            createdAt: '2026-09-18T10:00:00',
            id: '1',
          },
          {
            action: 'APPROVED',
            actorName: '审批人',
            createdAt: '2026-09-18T11:00:00',
            id: '2',
            nodeName: '财务审批',
          },
          {
            action: 'COMPLETED',
            actorName: '办理人',
            createdAt: '2026-09-18T12:00:00',
            id: '3',
            nodeName: '业务办理',
            remark: '已充值',
          },
        ],
        formFields,
      }),
    );

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      actorName: '办理人',
      eventType: 'RECHARGE_COMPLETED',
      formFields,
      nodeName: '业务办理',
      occurredAt: '2026-09-18T12:00:00',
      remark: '已充值',
    });
  });

  it.each(['PENDING', 'PROCESSING', 'REJECTED'])(
    'hides %s applications',
    (status: string) => {
      expect(successfulApplicationEvents(application({ status }))).toEqual([]);
    },
  );

  it('supports legacy approved applications without a completed action', () => {
    const events = successfulApplicationEvents(
      application({
        actions: [
          {
            action: 'APPROVED',
            actorName: '历史审批人',
            createdAt: '2026-09-18T11:00:00',
            id: '2',
            nodeName: '历史审批',
          },
        ],
        decidedAt: '2026-09-18T11:30:00',
      }),
    );

    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      actorName: '历史审批人',
      eventType: 'RECHARGE_COMPLETED',
      occurredAt: '2026-09-18T11:30:00',
      status: 'APPROVED',
    });
  });

  it.each([
    ['ACCOUNT_RECHARGE', 'RECHARGE_COMPLETED'],
    ['ACCOUNT_RECYCLE', 'RETURN_COMPLETED'],
    ['ACCOUNT_DEDUCTION', 'OPERATION_COMPLETED'],
    ['ACCOUNT_ACTIVE_CLEAR', 'OPERATION_COMPLETED'],
    ['ACCOUNT_UNBIND', 'OPERATION_COMPLETED'],
    ['ACCOUNT_REBIND', 'OPERATION_COMPLETED'],
  ])('maps %s to %s', (applicationCode: string, eventType: string) => {
    const events = successfulApplicationEvents(
      application({
        applicationCode,
        decidedAt: '2026-09-18T11:00:00',
      }),
    );

    expect(events[0]?.eventType).toBe(eventType);
  });
});
