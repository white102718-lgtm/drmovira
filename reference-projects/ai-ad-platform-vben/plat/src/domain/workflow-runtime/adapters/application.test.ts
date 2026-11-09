import type { ResourceApplication } from '#/domain/application';

import { describe, expect, it } from 'vitest';

import { ApplicationWorkflowRuntimeAdapter } from './application';

function application(patch: Partial<ResourceApplication> = {}) {
  return {
    approvalNodes: [
      {
        approver: '周敏',
        approverId: 'user-media-lead',
        id: 'NODE-1',
        label: '媒介审批',
        role: 'media',
        status: 'pending',
      },
    ],
    approvalRecords: [],
    approvalRole: 'media',
    approver: '周敏',
    ccUsers: [],
    comments: [],
    createdAt: '2026-08-13T09:00:00.000Z',
    description: '测试',
    id: 'application-1',
    project: 'Starfall',
    requester: '赵宁',
    status: 'pending',
    title: '账户申请',
    type: 'account',
    ...patch,
  } satisfies ResourceApplication;
}

describe('application workflow runtime adapter', () => {
  it('allows only the stable current-node approver to decide', () => {
    const adapter = new ApplicationWorkflowRuntimeAdapter({
      applications: () => [application()],
    });

    const approved = adapter.getState('application-1', {
      id: 'user-media-lead',
    });
    const denied = adapter.getState('application-1', { id: 'user-same-name' });
    expect(approved?.allowedActions).toEqual(
      expect.arrayContaining([
        { action: 'approve', allowed: true, reason: undefined },
        { action: 'reject', allowed: true, reason: undefined },
      ]),
    );
    expect(denied?.allowedActions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ action: 'approve', allowed: false }),
        expect.objectContaining({ action: 'reject', allowed: false }),
      ]),
    );
  });

  it('keeps name comparison only for legacy nodes without stable IDs', () => {
    const adapter = new ApplicationWorkflowRuntimeAdapter({
      applications: () => [
        application({
          approvalNodes: [
            {
              approver: '周敏',
              id: 'NODE-legacy',
              label: '媒介审批',
              role: 'media',
              status: 'pending',
            },
          ],
        }),
      ],
    });

    expect(
      adapter.getState('application-1', { name: '周敏' })?.allowedActions,
    ).toEqual(
      expect.arrayContaining([
        { action: 'approve', allowed: true, reason: undefined },
        { action: 'reject', allowed: true, reason: undefined },
      ]),
    );
  });

  it('moves transfer authority to the recipient after the current node changes', () => {
    const adapter = new ApplicationWorkflowRuntimeAdapter({
      applications: () => [
        application({
          approver: '李珊',
          approvalNodes: [
            {
              approver: '李珊',
              approverId: 'user-media-peer',
              id: 'NODE-1',
              label: '媒介审批',
              role: 'media',
              status: 'pending',
            },
          ],
        }),
      ],
    });

    expect(
      adapter.getState('application-1', { id: 'user-media-lead' })
        ?.allowedActions,
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ action: 'transfer', allowed: false }),
      ]),
    );
    expect(
      adapter.getState('application-1', { id: 'user-media-peer' })
        ?.allowedActions,
    ).toEqual(expect.arrayContaining([{ action: 'transfer', allowed: true }]));
  });
});
