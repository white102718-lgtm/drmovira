import type { ResourceApplication } from './types';

import { describe, expect, it } from 'vitest';

import { LegacyApplicationStoreAdapter } from './adapters/legacy';
import { ApplicationService, ApplicationWorkflowService } from './service';

const clock = {
  createId(prefix: string) {
    return `${prefix}-fixed`;
  },
  now() {
    return '2026-08-13 12:00:00';
  },
};

function application(
  patch: Partial<ResourceApplication> = {},
): ResourceApplication {
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
      {
        approver: '王楠',
        id: 'NODE-2',
        label: '财务审批',
        role: 'finance',
        status: 'waiting',
      },
    ],
    approvalRecords: [
      {
        action: 'submitted',
        actor: '赵宁',
        actorRole: '申请人',
        at: '2026-08-13 09:00:00',
        id: 'APR-1',
        remark: '申请已提交',
      },
    ],
    approvalRole: 'media',
    approver: '周敏',
    ccUsers: ['项目负责人'],
    comments: [],
    createdAt: '2026-08-13 09:00:00',
    description: '申请说明',
    id: 'REQ-1',
    project: 'Starfall',
    requester: '赵宁',
    status: 'pending',
    title: '测试申请',
    type: 'account',
    ...patch,
  };
}

describe('application workflow service', () => {
  it('activates one ordered node at a time and copies only after the final approval', () => {
    const service = new ApplicationWorkflowService(clock);
    const first = service.approve(application(), {
      actor: { name: '周敏', role: '媒介审批' },
      remark: '媒介范围已核验',
    });
    const final = service.approve(first, {
      actor: { name: '王楠', role: '财务审批' },
      remark: '预算已确认',
    });

    expect(first).toMatchObject({
      approver: '王楠',
      approvalRole: 'finance',
      status: 'pending',
    });
    expect(first.approvalNodes.map((node) => node.status)).toEqual([
      'approved',
      'pending',
    ]);
    expect(final.status).toBe('approved');
    expect(final.approvalRecords.at(-1)).toMatchObject({ action: 'copied' });
  });

  it('requires a decision comment and preserves the rejected history on resubmission', () => {
    const service = new ApplicationWorkflowService(clock);
    expect(() =>
      service.reject(application(), {
        actor: { name: '周敏', role: '媒介审批' },
        remark: ' ',
      }),
    ).toThrow('请填写本节点审批备注');

    const rejected = service.reject(application(), {
      actor: { name: '周敏', role: '媒介审批' },
      remark: '请补充账号用途',
    });
    const resubmitted = service.resubmit(rejected, {
      actor: { name: '赵宁', role: '申请人' },
      remark: '已补充用途与代理线信息',
    });

    expect(rejected.status).toBe('rejected');
    expect(resubmitted.status).toBe('pending');
    expect(resubmitted.approvalNodes.map((node) => node.status)).toEqual([
      'pending',
      'waiting',
    ]);
    expect(resubmitted.approvalRecords.slice(1)).toMatchObject([
      { action: 'rejected', remark: '请补充账号用途' },
      { action: 'copied' },
      { action: 'submitted', remark: '已补充用途与代理线信息' },
    ]);
  });

  it('keeps comments separate from decisions and tracks read receipts by the shared application ID', () => {
    const service = new ApplicationWorkflowService(clock);
    const commented = service.comment(application(), {
      actor: { name: '赵宁', role: '申请人' },
      content: '请优先匹配日本代理线。',
    });
    const unread = service.unreadCommentCount(commented, '周敏');
    const read = service.markCommentsRead(commented, '周敏');

    expect(commented.comments).toMatchObject([
      { actor: '赵宁', content: '请优先匹配日本代理线。', readBy: ['赵宁'] },
    ]);
    expect(commented.approvalRecords).toHaveLength(1);
    expect(unread).toBe(1);
    expect(service.unreadCommentCount(read, '周敏')).toBe(0);
  });

  it('does not let a waiting node decide before it becomes current', () => {
    const service = new ApplicationWorkflowService(clock);
    const waitingOnly = application({
      approvalNodes: [
        {
          approver: '王楠',
          id: 'NODE-2',
          label: '财务审批',
          role: 'finance',
          status: 'waiting',
        },
      ],
    });
    expect(() =>
      service.approve(waitingOnly, {
        actor: { name: '王楠', role: '财务审批' },
        remark: '不应通过',
      }),
    ).toThrow('当前申请没有可处理的审批节点');
  });

  it('transfers the pending node to another colleague without deciding it', () => {
    const service = new ApplicationWorkflowService(clock);

    const transferred = service.transfer(application(), {
      actor: {
        id: 'user-media-lead',
        name: '周敏',
        role: '媒介审批',
      },
      recipient: {
        departmentId: 'dept-media',
        departmentName: '媒介部',
        id: 'user-media-peer',
        name: '李珊',
      },
      remark: '下午外出，请协助办理。',
    });

    expect(transferred.status).toBe('pending');
    expect(transferred.approver).toBe('李珊');
    expect(transferred.approvalNodes[0]).toMatchObject({
      approver: '李珊',
      approverId: 'user-media-peer',
      status: 'pending',
    });
    expect(transferred.approvalRecords.at(-1)).toMatchObject({
      action: 'transferred',
      actor: '周敏',
      recipientId: 'user-media-peer',
      recipientName: '李珊',
      remark: '下午外出，请协助办理。',
    });
  });

  it('transfers the processing stage without changing approved nodes', () => {
    const service = new ApplicationWorkflowService(clock);
    const processing = application({
      approvalNodes: application().approvalNodes.map((node) => ({
        ...node,
        status: 'approved' as const,
      })),
      handlerId: 'user-media-lead',
      handlerName: '周敏',
      status: 'processing',
    });

    const transferred = service.transfer(processing, {
      actor: {
        id: 'user-media-lead',
        name: '周敏',
        role: '办理人',
      },
      recipient: {
        departmentId: 'dept-media',
        departmentName: '媒介部',
        id: 'user-media-peer',
        name: '李珊',
      },
      remark: '请协助完成资源办理。',
    });

    expect(transferred).toMatchObject({
      approver: '李珊',
      handlerId: 'user-media-peer',
      handlerName: '李珊',
      status: 'processing',
    });
    expect(transferred.approvalNodes).toEqual(processing.approvalNodes);
    expect(transferred.approvalRecords.at(-1)).toMatchObject({
      action: 'transferred',
      nodeIndex: processing.approvalNodes.length,
      recipientId: 'user-media-peer',
    });
  });

  it('rejects a transfer initiated by someone other than the current approver', () => {
    const service = new ApplicationWorkflowService(clock);

    expect(() =>
      service.transfer(application(), {
        actor: { id: 'user-other', name: '王楠', role: '财务审批' },
        recipient: {
          departmentId: 'dept-media',
          departmentName: '媒介部',
          id: 'user-media-peer',
          name: '李珊',
        },
        remark: '不应允许转交。',
      }),
    ).toThrow('当前用户不是本审批节点的稳定审批人');
  });
});

describe('application service compatibility facade', () => {
  it('writes stable source and requester fields through the legacy array adapter', () => {
    const records = [application()];
    const adapter = new LegacyApplicationStoreAdapter({
      applications: () => records,
      remove: (id) => {
        records.splice(
          records.findIndex((item) => item.id === id),
          1,
        );
      },
      upsert: (value) => {
        const index = records.findIndex((item) => item.id === value.id);
        if (index === -1) records.unshift(value);
        else records[index] = value;
        return value;
      },
    });
    const service = new ApplicationService(
      adapter,
      new ApplicationWorkflowService(clock),
    );

    service.save({
      ...application(),
      id: 'REQ-source-1',
      projectId: 'project-starfall',
      requesterId: 'user-chen-hang',
      requesterName: '陈航',
      sourceTaskId: 'TASK-AM-1042',
    });

    expect(service.get('REQ-source-1')).toMatchObject({
      projectId: 'project-starfall',
      requesterId: 'user-chen-hang',
      requesterName: '陈航',
      sourceTaskId: 'TASK-AM-1042',
    });
  });
});
