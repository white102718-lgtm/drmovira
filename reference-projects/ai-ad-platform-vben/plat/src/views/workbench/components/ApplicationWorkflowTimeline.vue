<script setup lang="ts">
import type {
  ApplicationApprovalNode,
  ApprovalAction,
  ResourceApplication,
} from '#/store/resource-applications';
import type { ApplicationApprovalRecord } from '#/domain/application';

import { computed } from 'vue';

import Tag from 'ant-design-vue/es/tag';

type RecordTagColor = 'blue' | 'default' | 'error' | 'success';

interface WorkflowRecordRow {
  actor: string;
  actorRole?: string;
  id: string;
  nodeName: string;
  opinion: string;
  result: string;
  resultColor: RecordTagColor;
  time?: string;
}

/**
 * 将实际流转过的申请、审批和办理节点汇总为审批记录表，便于在审批中心直接追溯。
 */
const props = defineProps<{
  application: ResourceApplication;
}>();

const approvalActionMeta: Record<
  ApprovalAction,
  { color: RecordTagColor; label: string }
> = {
  approved: { color: 'success', label: '已同意' },
  completed: { color: 'success', label: '已完成' },
  copied: { color: 'default', label: '已抄送' },
  rejected: { color: 'error', label: '已驳回' },
  submitted: { color: 'success', label: '已提交' },
  transferred: { color: 'blue', label: '已转交' },
};

const approvalNodeMeta = {
  approved: { color: 'success', label: '已同意' },
  pending: { color: 'blue', label: '待处理' },
  rejected: { color: 'error', label: '已驳回' },
  waiting: { color: 'default', label: '未到达' },
} as const;

const handlerRecord = computed(() => {
  for (
    let index = props.application.approvalRecords.length - 1;
    index >= 0;
    index -= 1
  ) {
    const record = props.application.approvalRecords[index];
    if (
      record?.action === 'completed' ||
      (record?.action === 'rejected' &&
        (record.actorRole === '业务办理' ||
          record.nodeIndex === props.application.approvalNodes.length))
    ) {
      return record;
    }
  }
  return undefined;
});

const hasConfiguredHandlerStage = computed(() => {
  const handlerId = props.application.handlerId?.trim();
  // 后端读模型会把不存在的办理人 ID 投影为字符串“0”，不能据此生成办理节点。
  const hasValidHandlerId = Boolean(
    handlerId && !['0', 'null', 'undefined'].includes(handlerId),
  );

  return Boolean(
    props.application.handlerAction ||
      props.application.handlerName?.trim() ||
      hasValidHandlerId,
  );
});

const shouldShowHandlerStage = computed(() => {
  if (handlerRecord.value) return true;
  // PROCESSING 本身证明申请已经进入办理阶段，历史异常数据即使缺少办理人也需保留节点。
  if (props.application.status === 'processing') return true;

  return (
    props.application.status === 'approved' && hasConfiguredHandlerStage.value
  );
});

const handlerStage = computed(() => {
  if (handlerRecord.value) {
    const rejected = handlerRecord.value.action === 'rejected';
    return {
      color: rejected ? ('error' as const) : ('success' as const),
      opinion:
        handlerRecord.value.remark ||
        (rejected ? '已拒绝办理。' : '办理已完成。'),
      result: rejected ? '已拒绝办理' : '已完成',
      time: handlerRecord.value.at,
    };
  }
  if (props.application.status === 'processing') {
    return {
      color: 'blue' as const,
      opinion: '审批已完成，等待办理人处理。',
      result: '待处理',
      time: undefined,
    };
  }
  return {
    color: 'success' as const,
    opinion: '审批及后续办理已完成。',
    result: '已完成',
    time: undefined,
  };
});

const nodeRecords = computed(() => {
  const records = new Map<string, ApplicationApprovalRecord>();
  const usedRecordIds = new Set<string>();

  props.application.approvalNodes.forEach((node, nodeIndex) => {
    const expectedAction =
      node.status === 'approved'
        ? 'approved'
        : node.status === 'rejected'
          ? 'rejected'
          : undefined;
    if (!expectedAction) return;

    const matchingRecord = props.application.approvalRecords.find(
      (record) =>
        !usedRecordIds.has(record.id) &&
        (record.nodeIndex === undefined || record.nodeIndex === nodeIndex) &&
        record.action === expectedAction &&
        (record.at === node.actedAt || record.actor === node.approver),
    );
    const fallbackRecord = props.application.approvalRecords.find(
      (record) =>
        !usedRecordIds.has(record.id) &&
        (record.nodeIndex === undefined || record.nodeIndex === nodeIndex) &&
        record.action === expectedAction,
    );
    const record = matchingRecord ?? fallbackRecord;
    if (!record) return;

    records.set(node.id, record);
    usedRecordIds.add(record.id);
  });

  return records;
});

const matchedNodeRecordIds = computed(
  () => new Set(nodeRecords.value.values().map((record) => record.id)),
);

const additionalRecords = computed(() =>
  props.application.approvalRecords.filter(
    (record) =>
      record.action !== 'submitted' &&
      record.id !== handlerRecord.value?.id &&
      !matchedNodeRecordIds.value.has(record.id),
  ),
);

function additionalRecordRow(
  record: ApplicationApprovalRecord,
): WorkflowRecordRow {
  const meta = approvalActionMeta[record.action];
  const transferTarget =
    record.action === 'transferred' && record.recipientName
      ? `转交给 ${record.recipientName}${
          record.recipientDepartmentName
            ? ` · ${record.recipientDepartmentName}`
            : ''
        }`
      : '';
  return {
    actor: record.actor,
    actorRole: record.actorRole,
    id: record.id,
    nodeName:
      record.action === 'copied'
        ? '抄送'
        : record.action === 'transferred'
          ? (record.nodeIndex ?? -1) >= props.application.approvalNodes.length
            ? '办理转交'
            : '审批转交'
          : '审批',
    opinion:
      [transferTarget, record.remark].filter(Boolean).join('：') ||
      '暂无审批意见',
    result: meta.label,
    resultColor: meta.color,
    time: record.at,
  };
}

/** 已发生记录先按真实时间排序，同一时刻再用稳定日志 ID 避免顺序抖动。 */
function compareOccurredRows(
  left: WorkflowRecordRow,
  right: WorkflowRecordRow,
) {
  const leftTime = Date.parse((left.time ?? '').replace(' ', 'T'));
  const rightTime = Date.parse((right.time ?? '').replace(' ', 'T'));
  if (Number.isFinite(leftTime) && Number.isFinite(rightTime)) {
    const timeDifference = leftTime - rightTime;
    if (timeDifference !== 0) return timeDifference;
  } else {
    const timeComparison = (left.time ?? '').localeCompare(right.time ?? '');
    if (timeComparison !== 0) return timeComparison;
  }
  return left.id.localeCompare(right.id, 'zh-CN', { numeric: true });
}

const workflowRows = computed<WorkflowRecordRow[]>(() => {
  const submittedRecord = props.application.approvalRecords.find(
    (record) => record.action === 'submitted',
  );
  const occurredRows: WorkflowRecordRow[] = [
    {
      actor: submittedRecord?.actor || props.application.requester,
      actorRole: submittedRecord?.actorRole || '申请人',
      id: submittedRecord?.id || 'submitted',
      nodeName: '提交',
      opinion: submittedRecord?.remark || '提交申请',
      result: approvalActionMeta.submitted.label,
      resultColor: approvalActionMeta.submitted.color,
      time: submittedRecord?.at || props.application.createdAt,
    },
  ];
  const pendingRows: WorkflowRecordRow[] = [];

  const appendRow = (row: WorkflowRecordRow) => {
    if (row.time) occurredRows.push(row);
    else pendingRows.push(row);
  };

  const placedAdditionalRecordIds = new Set<string>();
  // 完整流程需保留未到达节点；无发生时间的当前及后续节点统一排在历史记录之后。
  props.application.approvalNodes.forEach((node, nodeIndex) => {
    additionalRecords.value
      .filter(
        (record) =>
          record.action === 'transferred' &&
          (record.nodeIndex === nodeIndex ||
            (record.nodeIndex === undefined && node.status === 'pending')),
      )
      .forEach((record) => {
        appendRow(additionalRecordRow(record));
        placedAdditionalRecordIds.add(record.id);
      });

    const record = findNodeRecord(node);
    const meta = approvalNodeMeta[node.status];
    appendRow({
      actor: record?.actor || node.approver,
      actorRole: record?.actorRole || '审批人',
      id: record?.id || node.id,
      nodeName: node.label || '审批',
      opinion: nodeDescription(node, record),
      result: meta.label,
      resultColor: meta.color,
      time: nodeTime(node, record),
    });
  });

  additionalRecords.value
    .filter(
      (record) =>
        record.action === 'transferred' &&
        (record.nodeIndex ?? -1) >= props.application.approvalNodes.length,
    )
    .forEach((record) => {
      appendRow(additionalRecordRow(record));
      placedAdditionalRecordIds.add(record.id);
    });

  if (shouldShowHandlerStage.value) {
    appendRow({
      actor:
        handlerRecord.value?.actor ||
        props.application.handlerName ||
        '未配置办理人',
      actorRole: handlerRecord.value?.actorRole || '办理人',
      id: handlerRecord.value?.id || 'handler-stage',
      nodeName: '办理',
      opinion: handlerStage.value.opinion,
      result: handlerStage.value.result,
      resultColor: handlerStage.value.color,
      time: handlerStage.value.time,
    });
  }

  // 待审批申请仅展示计划抄送节点，不生成“已抄送”记录或回写真实审批日志。
  if (
    props.application.ccUsers.length > 0 &&
    !props.application.approvalRecords.some(
      (record) => record.action === 'copied',
    )
  ) {
    appendRow({
      actor: props.application.ccUsers.join('、'),
      actorRole: '抄送人',
      id: `CC-PENDING-${props.application.id}`,
      nodeName: '抄送',
      opinion: `审批完成后抄送：${props.application.ccUsers.join('、')}`,
      result: '未到达',
      resultColor: 'default',
    });
  }

  additionalRecords.value
    .filter((record) => !placedAdditionalRecordIds.has(record.id))
    .forEach((record) => appendRow(additionalRecordRow(record)));

  return [...occurredRows.sort(compareOccurredRows), ...pendingRows];
});

function findNodeRecord(node: ApplicationApprovalNode) {
  return nodeRecords.value.get(node.id);
}

function nodeDescription(
  node: ApplicationApprovalNode,
  record?: ApplicationApprovalRecord,
) {
  return record?.remark || node.remark || '暂无审批意见';
}

function nodeTime(
  node: ApplicationApprovalNode,
  record?: ApplicationApprovalRecord,
) {
  return record?.at || node.actedAt;
}

function getActorInitial(name: string) {
  return name.trim().slice(0, 1) || '人';
}

function formatDateTime(value?: string) {
  if (!value) return '—';
  return value
    .replace('T', ' ')
    .replace(/\.\d+(?=Z?$)/, '')
    .replace(/Z$/, '');
}
</script>

<template>
  <section
    aria-labelledby="selected-application-workflow-heading"
    class="rounded-xl border border-slate-200 p-4"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3
        id="selected-application-workflow-heading"
        class="m-0 text-sm font-semibold text-slate-900"
      >
        审批流程与记录
      </h3>
      <span class="text-xs text-slate-500"
        >共 {{ workflowRows.length }} 项</span
      >
    </div>

    <div class="ux-native-table-viewport mt-4">
      <table class="w-full min-w-[700px] border-collapse text-left text-sm">
        <thead
          class="border-y border-slate-200 text-xs font-medium text-slate-500"
        >
          <tr>
            <th scope="col" class="h-11 px-3 font-medium">节点名称</th>
            <th scope="col" class="h-11 px-3 font-medium">审批人</th>
            <th scope="col" class="h-11 px-3 font-medium">审批结果</th>
            <th scope="col" class="h-11 px-3 font-medium">审批意见</th>
            <th scope="col" class="h-11 px-3 font-medium">审批时间</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in workflowRows"
            :key="row.id"
            class="border-b border-slate-100 align-top last:border-b-0"
          >
            <td class="px-3 py-3 font-medium text-slate-800">
              {{ row.nodeName }}
            </td>
            <td class="px-3 py-3">
              <div class="flex min-w-[132px] items-center gap-2">
                <span
                  aria-hidden="true"
                  class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-medium text-slate-600"
                >
                  {{ getActorInitial(row.actor) }}
                </span>
                <div class="min-w-0">
                  <p class="m-0 truncate font-medium text-slate-800">
                    {{ row.actor }}
                  </p>
                  <p
                    v-if="row.actorRole"
                    class="m-0 mt-0.5 truncate text-xs text-slate-500"
                  >
                    {{ row.actorRole }}
                  </p>
                </div>
              </div>
            </td>
            <td class="px-3 py-3">
              <Tag :color="row.resultColor" class="!m-0 whitespace-nowrap">
                {{ row.result }}
              </Tag>
            </td>
            <td class="max-w-52 px-3 py-3 text-slate-600">
              <p class="m-0 whitespace-pre-wrap break-words leading-5">
                {{ row.opinion }}
              </p>
            </td>
            <td class="px-3 py-3 text-xs text-slate-500">
              <time v-if="row.time" :datetime="row.time">
                {{ formatDateTime(row.time) }}
              </time>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
