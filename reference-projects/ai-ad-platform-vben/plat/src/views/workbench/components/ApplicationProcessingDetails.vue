<script setup lang="ts">
import type { ResourceApplication } from '#/store/resource-applications';

import { computed } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { resolveSocialAssetSelection } from '#/domain/application';
import Tag from 'ant-design-vue/es/tag';

import ProcessingResultDetails from './ProcessingResultDetails.vue';

/**
 * 申请办理信息的统一展示入口，供审批中心查看区和详情弹窗共同使用。
 *
 * @remarks
 * 仅存在办理完成记录时展示，避免把待办理要求误认为已经产生的办理结果。
 */
const props = defineProps<{
  application: ResourceApplication;
}>();

const processingRecord = computed(() => {
  for (
    let index = props.application.approvalRecords.length - 1;
    index >= 0;
    index -= 1
  ) {
    const history = props.application.approvalRecords[index];
    if (history?.action === 'completed') return history;
  }
  return undefined;
});

const stableHandlerId = computed(() => {
  const handlerId = (
    processingRecord.value?.actorId ?? props.application.handlerId
  )?.trim();
  if (!handlerId || ['0', 'null', 'undefined'].includes(handlerId)) return '';
  return handlerId;
});

const handlerSourceText = computed(() => {
  if (props.application.handlerSource !== 'approval-node') return '固定人员';
  const sourceNode = props.application.approvalNodes.find(
    (node) => node.id === props.application.handlerApprovalNodeId,
  );
  return sourceNode
    ? `关联审批节点：${sourceNode.label}`
    : '关联审批节点的审批人';
});

const hasConfiguredStage = computed(() =>
  Boolean(
    props.application.type === 'account' ||
      props.application.handlerAction ||
      props.application.handlerName?.trim() ||
      stableHandlerId.value ||
      processingRecord.value ||
      props.application.allocatedAssets?.length,
  ),
);

const processingRequirements = computed(() => {
  const requirements: string[] = [];
  const assignment = props.application.handlerAction?.resourceAssignment;
  // Inventory allocation is an explicit handler action.  Do not infer it from
  // the legacy display type: non-inventory workflows (such as project closure)
  // may currently share the same generic type.
  if (assignment?.enabled) {
    const quantityKey = assignment?.quantityFieldKey ?? 'quantity';
    const quantity = Number(
      props.application.formData?.[quantityKey] ??
        props.application.quantity ??
        1,
    );
    requirements.push(
      `从库存选择并分配 ${Number.isFinite(quantity) ? quantity : 1} 个${processingAssetTypeLabel.value}资源`,
    );
  }

  const fieldLabels = (props.application.handlerAction?.formSchema ?? [])
    .filter((field) => field.type !== 'section')
    .map((field) => field.label);
  if (fieldLabels.length > 0) {
    requirements.push(`办理时填写：${fieldLabels.join('、')}`);
  }
  return requirements;
});

const processingAssetTypeLabel = computed(() => {
  const socialSelection = resolveSocialAssetSelection(
    props.application.formData?.socialAssetType,
  );
  if (socialSelection) return socialSelection.label;
  const labels: Record<string, string> = {
    BM: 'BM',
    PERSONAL: 'Facebook 账号',
    PIXEL: '像素',
    TG: 'TG号',
  };
  return labels[props.application.platform ?? ''] ?? '广告账号';
});

const processingStageMeta = computed(() => {
  if (!hasConfiguredStage.value) {
    return { color: 'default', label: '未配置办理' };
  }
  if (processingRecord.value || props.application.status === 'approved') {
    return { color: 'success', label: '办理完成' };
  }
  if (props.application.status === 'processing') {
    return { color: 'processing', label: '待办理' };
  }
  return { color: 'default', label: '未开始' };
});

const processingSummary = computed(() => {
  if (processingRecord.value) return processingRecord.value.remark;
  if (!hasConfiguredStage.value) return '该申请未配置业务办理节点。';
  if (props.application.status === 'approved') {
    return '业务办理已完成，暂无补充说明。';
  }
  if (props.application.status === 'processing') {
    return `待 ${props.application.handlerName || '办理人'} 按办理要求完成处理。`;
  }
  return `审批通过后由 ${props.application.handlerName || '配置的办理人'} 完成业务办理。`;
});

const hasProcessingResult = computed(() => {
  if ((props.application.allocatedAssets?.length ?? 0) > 0) return true;
  const actionData = processingRecord.value?.actionData ?? {};
  if (
    Array.isArray(actionData._allocatedAssets) &&
    actionData._allocatedAssets.length > 0
  ) {
    return true;
  }
  return (props.application.handlerAction?.formSchema ?? []).some((field) => {
    if (field.type === 'section') return false;
    const value = actionData[field.key];
    if (Array.isArray(value)) return value.length > 0;
    return value !== undefined && value !== null && value !== '';
  });
});
</script>

<template>
  <section v-if="processingRecord" aria-label="办理信息">
    <h3 class="m-0 text-sm font-semibold text-slate-900">办理信息</h3>
    <div class="mt-3 rounded-lg border border-slate-100 bg-slate-50 p-3">
      <div
        class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
      >
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <Tag :color="processingStageMeta.color" class="!m-0">
              {{ processingStageMeta.label }}
            </Tag>
            <span class="break-words text-sm font-medium text-slate-800">
              {{
                processingRecord?.actor ||
                application.handlerName ||
                '未配置办理人'
              }}
            </span>
            <span
              v-if="processingRecord?.actorRole"
              class="text-xs text-slate-500"
            >
              {{ processingRecord.actorRole }}
            </span>
          </div>
          <dl v-if="stableHandlerId" class="mb-0 mt-2 text-xs">
            <div
              class="grid grid-cols-[64px_minmax(0,1fr)] gap-x-2 text-slate-600"
            >
              <dt class="text-slate-500">办理人 ID</dt>
              <dd class="m-0 break-all font-medium">{{ stableHandlerId }}</dd>
            </div>
            <div
              class="mt-1 grid grid-cols-[64px_minmax(0,1fr)] gap-x-2 text-slate-600"
            >
              <dt class="text-slate-500">办理来源</dt>
              <dd class="m-0 break-words font-medium">
                {{ handlerSourceText }}
              </dd>
            </div>
          </dl>
          <p
            class="mb-0 mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700"
          >
            {{ processingSummary }}
          </p>
          <ul
            v-if="processingRequirements.length > 0"
            class="mb-0 mt-2 space-y-1 p-0 text-xs text-slate-500"
          >
            <li
              v-for="requirement in processingRequirements"
              :key="requirement"
              class="flex list-none items-start gap-1.5"
            >
              <IconifyIcon
                aria-hidden="true"
                class="mt-0.5 shrink-0 text-teal-500"
                icon="lucide:check-circle-2"
              />
              <span class="break-words">{{ requirement }}</span>
            </li>
          </ul>
        </div>
        <time
          v-if="processingRecord"
          class="shrink-0 text-xs text-slate-400"
          :datetime="processingRecord.at"
        >
          {{ processingRecord.at }}
        </time>
      </div>
    </div>

    <ProcessingResultDetails
      v-if="hasProcessingResult"
      :action-data="processingRecord?.actionData"
      :application="application"
    />
    <p
      v-else
      class="mb-0 mt-3 rounded-lg border border-dashed border-slate-200 p-4 text-center text-sm text-slate-500"
    >
      {{
        processingStageMeta.label === '办理完成'
          ? '本次办理未填写结构化结果或分配资产'
          : '办理完成后将在此展示填写结果、凭证和分配资产'
      }}
    </p>
  </section>
</template>
