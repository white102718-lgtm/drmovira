import type { ResourceApplication } from '#/domain/application';

import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import ApplicationWorkflowTimeline from './ApplicationWorkflowTimeline.vue';

function application(): ResourceApplication {
  return {
    approvalNodes: [
      {
        actedAt: '2026-09-15T10:00:00',
        approver: '周敏',
        id: 'NODE-1',
        label: '媒介审批',
        role: 'media',
        status: 'approved',
      },
      {
        actedAt: '2026-09-15T11:00:00',
        approver: '王楠',
        id: 'NODE-2',
        label: '财务审批',
        role: 'finance',
        status: 'approved',
      },
    ],
    // 故意打乱来源数组顺序，验证界面以业务发生时间为准。
    approvalRecords: [
      {
        action: 'approved',
        actor: '周敏',
        actorRole: '审批人',
        at: '2026-09-15T10:00:00',
        id: '3',
        nodeIndex: 0,
        remark: '通过',
      },
      {
        action: 'approved',
        actor: '王楠',
        actorRole: '审批人',
        at: '2026-09-15T11:00:00',
        id: '4',
        nodeIndex: 1,
        remark: '通过',
      },
      {
        action: 'transferred',
        actor: '王楠',
        actorRole: '办理人',
        at: '2026-09-15T11:30:00',
        id: '5',
        nodeIndex: 2,
        recipientName: '李珊',
        remark: '请协助办理',
      },
      {
        action: 'submitted',
        actor: '赵宁',
        actorRole: '申请人',
        at: '2026-09-15T09:00:00',
        id: '1',
        remark: '提交申请',
      },
      {
        action: 'transferred',
        actor: '张三',
        actorRole: '审批人',
        at: '2026-09-15T09:30:00',
        id: '2',
        nodeIndex: 0,
        recipientName: '周敏',
        remark: '请协助审批',
      },
    ],
    approvalRole: 'media',
    approver: '李珊',
    ccUsers: [],
    comments: [],
    createdAt: '2026-09-15T09:00:00',
    description: '申请说明',
    handlerId: 'user-li-shan',
    handlerName: '李珊',
    id: '60',
    project: '项目 A',
    requester: '赵宁',
    status: 'processing',
    title: '开户申请',
    type: 'account',
  };
}

describe('ApplicationWorkflowTimeline', () => {
  it('按流程顺序展示当前节点及尚未到达的后续节点', () => {
    const record = application();
    record.status = 'pending';
    record.approvalNodes = [
      {
        approver: '周敏',
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
    ];
    record.approvalRecords = record.approvalRecords.filter(
      (item) => item.action === 'submitted',
    );

    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: record },
    });
    const rows = wrapper.findAll('tbody tr');

    expect(
      rows.map((row: { find: (selector: string) => { text: () => string } }) =>
        row.find('td').text(),
      ),
    ).toEqual(['提交', '媒介审批', '财务审批']);
    expect(wrapper.text()).toContain('共 3 项');
    expect(rows.at(-1)?.text()).toContain('未到达');
  });

  it('待审批申请在流程末尾展示计划抄送节点及人员名单', () => {
    const record = application();
    record.status = 'pending';
    record.ccUsers = ['张三'];
    record.approvalNodes = [
      {
        approver: '周敏',
        id: 'NODE-1',
        label: '媒介审批',
        role: 'media',
        status: 'pending',
      },
    ];
    record.approvalRecords = record.approvalRecords.filter(
      (item) => item.action === 'submitted',
    );

    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: record },
    });
    const copiedRow = wrapper
      .findAll('tbody tr')
      .find(
        (row: { find: (selector: string) => { text: () => string } }) =>
          row.find('td').text() === '抄送',
      );

    expect(copiedRow?.text()).toContain('未到达');
    expect(copiedRow?.text()).toContain('审批完成后抄送：张三');
    expect(copiedRow?.text()).not.toContain('已抄送');
  });

  it('按发生时间排列审批和办理转交，待办理节点放在最后', () => {
    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: application() },
    });

    const nodeNames = wrapper
      .findAll('tbody tr')
      .map((row: { find: (selector: string) => { text: () => string } }) =>
        row.find('td').text(),
      );

    expect(nodeNames).toEqual([
      '提交',
      '审批转交',
      '媒介审批',
      '财务审批',
      '办理转交',
      '办理',
    ]);
  });

  it('自动完成且未配置办理阶段的申请不展示办理节点', () => {
    const record = application();
    record.status = 'approved';
    record.formData = { _completionMode: 'pixel-auto-assign' };
    record.handlerAction = undefined;
    record.handlerId = '0';
    record.handlerName = '';
    record.approvalRecords = record.approvalRecords.filter((item) =>
      ['approved', 'submitted'].includes(item.action),
    );

    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: record },
    });
    const nodeNames = wrapper
      .findAll('tbody tr')
      .map((row: { find: (selector: string) => { text: () => string } }) =>
        row.find('td').text(),
      );

    expect(nodeNames).not.toContain('办理');
    expect(wrapper.text()).not.toContain('未配置办理人');
  });

  it('普通已完成申请存在办理配置时保留办理节点', () => {
    const record = application();
    record.status = 'approved';
    record.approvalRecords = record.approvalRecords.filter(
      (item) => item.action !== 'transferred',
    );

    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: record },
    });
    const handlerRow = wrapper
      .findAll('tbody tr')
      .find(
        (row: { find: (selector: string) => { text: () => string } }) =>
          row.find('td').text() === '办理',
      );

    expect(handlerRow?.text()).toContain('李珊');
    expect(handlerRow?.text()).toContain('已完成');
  });

  it('存在真实办理记录时不依赖当前办理配置展示节点', () => {
    const record = application();
    record.status = 'approved';
    record.handlerAction = undefined;
    record.handlerId = '0';
    record.handlerName = '';
    record.approvalRecords = record.approvalRecords.filter(
      (item) => item.action !== 'transferred',
    );
    record.approvalRecords.push({
      action: 'completed',
      actor: '历史办理人',
      actorRole: '业务办理',
      at: '2026-09-15T12:00:00',
      id: 'HANDLER-60',
      nodeIndex: record.approvalNodes.length,
      remark: '已完成业务办理',
    });

    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: record },
    });
    const handlerRow = wrapper
      .findAll('tbody tr')
      .find(
        (row: { find: (selector: string) => { text: () => string } }) =>
          row.find('td').text() === '办理',
      );

    expect(handlerRow?.text()).toContain('历史办理人');
    expect(handlerRow?.text()).toContain('已完成业务办理');
  });

  it('拒绝办理的历史记录在当前办理配置缺失时仍展示节点', () => {
    const record = application();
    record.status = 'rejected';
    record.handlerAction = undefined;
    record.handlerId = '0';
    record.handlerName = '';
    record.approvalRecords = record.approvalRecords.filter(
      (item) => item.action !== 'transferred',
    );
    record.approvalRecords.push({
      action: 'rejected',
      actor: '历史办理人',
      actorRole: '业务办理',
      at: '2026-09-15T12:00:00',
      id: 'HANDLER-REJECTED-60',
      nodeIndex: record.approvalNodes.length,
      remark: '资源条件不满足',
    });

    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: record },
    });
    const handlerRow = wrapper
      .findAll('tbody tr')
      .find(
        (row: { find: (selector: string) => { text: () => string } }) =>
          row.find('td').text() === '办理',
      );

    expect(handlerRow?.text()).toContain('历史办理人');
    expect(handlerRow?.text()).toContain('已拒绝办理');
    expect(handlerRow?.text()).toContain('资源条件不满足');
  });

  it('处理中申请缺少办理人时仍保留办理节点以兼容历史异常数据', () => {
    const record = application();
    record.handlerAction = undefined;
    record.handlerId = '0';
    record.handlerName = '';

    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: record },
    });

    expect(wrapper.text()).toContain('办理');
    expect(wrapper.text()).toContain('未配置办理人');
    expect(wrapper.text()).toContain('待处理');
  });

  it('清晰展示抄送节点及多人名单', () => {
    const record = application();
    record.ccUsers = ['张三', '李四（已停用）'];
    record.approvalRecords.push({
      action: 'copied',
      actor: '系统通知',
      actorRole: '抄送',
      at: '2026-09-15T12:00:00',
      id: 'CC-60',
      remark: '审批结果已抄送：张三、李四（已停用）',
    });

    const wrapper = mount(ApplicationWorkflowTimeline, {
      global: { stubs: { Tag: true } },
      props: { application: record },
    });
    const copiedRow = wrapper
      .findAll('tbody tr')
      .find(
        (row: { find: (selector: string) => { text: () => string } }) =>
          row.find('td').text() === '抄送',
      );

    expect(copiedRow?.text()).toContain('已抄送');
    expect(copiedRow?.text()).toContain('张三、李四（已停用）');
  });
});
