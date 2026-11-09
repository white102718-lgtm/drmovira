<script lang="ts" setup>
import type { AssetApplication, DynamicFormField } from '#/api/asset-flow';
import type {
  ApplicationComment,
  ApplicationStatus,
  ResourceApplication,
} from '#/store/resource-applications';

import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';

import {
  Alert,
  Button,
  Card,
  Input,
  message,
  Modal,
  Skeleton,
  Tabs,
  Tag,
} from 'ant-design-vue';

import { assetFlowApi, isFusionDemoMode } from '#/api';
import { useApprovalResourceFlow } from '#/composables/use-approval-resource-flow';
import { ApplicationWorkflowRuntimeAdapter } from '#/domain/workflow-runtime';

import { mapBackendApplication } from './backend-application';
import ApplicationCollaborationPanel from './components/ApplicationCollaborationPanel.vue';
import ApplicationProcessingDetails from './components/ApplicationProcessingDetails.vue';

defineOptions({ name: 'WorkbenchApprovalHandle' });

const APPROVAL_LIST_UPDATED_RECORD_KEY = 'adpulse:approval-list:updated-record';

type DemoProfileCode =
  | 'admin'
  | 'cc'
  | 'finance'
  | 'media'
  | 'office'
  | 'requester';

interface ApprovalIdentity {
  id?: string;
  name: string;
  roleLabel: string;
}

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const { applicationService, applications, bridge, mediaResourceStore } =
  useApprovalResourceFlow();
const workflowRuntime = new ApplicationWorkflowRuntimeAdapter({
  applications: () => applications.value,
});

const demoProfiles: Record<DemoProfileCode, ApprovalIdentity> = {
  admin: { id: 'user-platform-admin', name: '平台管理员', roleLabel: '管理员' },
  cc: { id: 'user-project-owner', name: '项目负责人', roleLabel: '抄送人' },
  finance: { id: 'user-finance-lead', name: '王楠', roleLabel: '财务审批' },
  media: { id: 'user-media-lead', name: '周敏', roleLabel: '媒介审批' },
  office: {
    id: 'user-office-lead',
    name: '郑然',
    roleLabel: '行政与资产审批',
  },
  requester: { id: 'user-zhao-ning', name: '赵宁', roleLabel: '申请人' },
};

const applicationId = computed(() => String(route.params.id ?? ''));
const cachedApplication = ref<ResourceApplication>();
const cachedRoutePermission = ref<'handle' | 'view'>('view');
try {
  const cached = sessionStorage.getItem(
    `adpulse:approval-route:${applicationId.value}`,
  );
  if (cached) cachedApplication.value = JSON.parse(cached);
  cachedRoutePermission.value =
    sessionStorage.getItem(
      `adpulse:approval-route-permission:${applicationId.value}`,
    ) === 'handle'
      ? 'handle'
      : 'view';
} catch {
  // 路由快照损坏时回退到 Store；快照从不作为审批写入来源。
}
const isBackendApplication = computed(() => /^\d+$/.test(applicationId.value));
const application = computed(() => {
  if (isBackendApplication.value) return cachedApplication.value;
  return (
    applications.value.find((item) => item.id === applicationId.value) ??
    cachedApplication.value
  );
});
const demoProfile = computed<DemoProfileCode>(() => {
  const profile = String(route.query.profile ?? 'media') as DemoProfileCode;
  return profile in demoProfiles ? profile : 'media';
});
const currentIdentity = computed<ApprovalIdentity>(() => {
  if (isFusionDemoMode()) return demoProfiles[demoProfile.value];
  const user = userStore.userInfo as
    | undefined
    | {
        _id?: number | string;
        user_id?: number | string;
        userId?: number | string;
      };
  const candidate = user?.userId ?? user?.user_id ?? user?._id;
  const identityId =
    candidate === undefined || candidate === null
      ? ''
      : String(candidate).trim();
  return {
    id: identityId || undefined,
    name:
      userStore.userInfo?.realName ||
      userStore.userInfo?.full_name ||
      userStore.userInfo?.username ||
      '当前用户',
    roleLabel: '审批人',
  };
});

const mediaApplication = computed(() => {
  const record = application.value;
  if (!record) return;
  return mediaResourceStore.applications.find(
    (item) =>
      item.id === record.resourceApplicationId ||
      item.sourceApplicationId === record.id,
  );
});
const canHandle = computed(() => {
  const record = application.value;
  if (!record) return false;
  // 后端申请只沿用审批中心已校验的节点权限，不能仅凭待审批状态展示办理按钮。
  if (isBackendApplication.value) {
    return (
      record.status === 'pending' && cachedRoutePermission.value === 'handle'
    );
  }
  const state = workflowRuntime.getState(record.id, currentIdentity.value);
  return Boolean(
    state?.allowedActions.some(
      (item) => item.action === 'approve' && item.allowed,
    ),
  );
});
const isCurrentHandler = computed(() => {
  const record = application.value;
  if (!record) return false;
  const identityId = currentIdentity.value.id?.trim();
  if (identityId && record.handlerId?.trim()) {
    return identityId === record.handlerId.trim();
  }
  return record.handlerName === currentIdentity.value.name;
});
const canIssueAccount = computed(
  () =>
    !isBackendApplication.value &&
    application.value?.type === 'account' &&
    (mediaApplication.value?.status === 'approved' ||
      (application.value.status === 'processing' && isCurrentHandler.value)),
);
const canComment = computed(() => {
  const record = application.value;
  if (!record) return false;
  const identityId = currentIdentity.value.id?.trim();
  const participantIds = [
    record.requesterId,
    record.handlerId,
    ...record.approvalNodes.map((node) => node.approverId),
  ].filter(Boolean);
  if (identityId && participantIds.includes(identityId)) return true;
  return (
    canHandle.value ||
    record.requester === currentIdentity.value.name ||
    record.handlerName === currentIdentity.value.name ||
    record.ccUsers.includes(currentIdentity.value.name) ||
    record.approvalNodes.some(
      (node) => node.approver === currentIdentity.value.name,
    )
  );
});
const decisionForm = reactive({ remark: '' });
const decisionError = ref('');
const decisionAction = ref<'approved' | 'rejected'>('approved');
const decisionDialogOpen = ref(false);
const submitting = ref(false);
const activeTab = ref('info');
// 后端详情在首次请求完成前不能被判定为“不存在”，避免路由跳转时闪现错误态。
const isApplicationLoading = ref(
  isBackendApplication.value && !cachedApplication.value,
);

const statusMeta: Record<ApplicationStatus, { color: string; label: string }> =
  {
    approved: { color: 'success', label: '已完成' },
    draft: { color: 'default', label: '草稿' },
    pending: { color: 'processing', label: '待审批' },
    processing: { color: 'warning', label: '待办理' },
    rejected: { color: 'error', label: '已驳回' },
  };

const approvalNodeMeta = {
  approved: { color: 'success', label: '已通过' },
  pending: { color: 'processing', label: '当前审批' },
  rejected: { color: 'error', label: '已驳回' },
  waiting: { color: 'default', label: '等待中' },
} as const;

const approvalActionMeta = {
  approved: { color: 'success', label: '审批通过' },
  completed: { color: 'success', label: '办理完成' },
  copied: { color: 'default', label: '完成抄送' },
  rejected: { color: 'error', label: '审批驳回' },
  submitted: { color: 'blue', label: '提交申请' },
  transferred: { color: 'warning', label: '审批转交' },
} as const;

const configuredFields = computed(
  () => (application.value?.formSchema ?? []) as DynamicFormField[],
);

const handlerStageMeta = computed(() => {
  const status = application.value?.status;
  if (status === 'approved') return { color: 'success', label: '已完成' };
  if (status === 'processing') return { color: 'processing', label: '待办理' };
  if (status === 'rejected') return { color: 'default', label: '已终止' };
  return { color: 'default', label: '未开始' };
});

function optionSnapshotBase(fieldKey: string) {
  if (fieldKey.endsWith('Ids')) return fieldKey.slice(0, -3);
  if (fieldKey.endsWith('Id')) return fieldKey.slice(0, -2);
  return fieldKey;
}

/** 优先展示申请提交时固化的选项名称，避免详情页只显示内部 ID。 */
function configuredFieldValue(field: DynamicFormField) {
  const formData = application.value?.formData;
  const value = formData?.[field.key];
  if (field.optionSource && field.optionSource !== 'custom') {
    const snapshotBase = optionSnapshotBase(field.key);
    const snapshot =
      formData?.[`${snapshotBase}${Array.isArray(value) ? 'Names' : 'Name'}`];
    if (Array.isArray(snapshot)) return snapshot.join('、') || '—';
    if (snapshot !== undefined && snapshot !== null && snapshot !== '') {
      return String(snapshot);
    }
  }
  if (Array.isArray(value)) return value.map(String).join('、') || '—';
  if (value === undefined || value === null || value === '') return '—';
  return String(value);
}

function goBack() {
  router.back();
}

/** 保留接口原始时间值，仅在界面展示时转换 ISO 分隔符以提高可读性。 */
function formatApplicationDateTime(value: string) {
  return value
    .replace('T', ' ')
    .replace(/\.\d+(?=Z?$)/, '')
    .replace(/Z$/, '');
}

function isApplicationNotFound(
  record: ResourceApplication | undefined,
  loading: boolean,
) {
  return !loading && !record;
}

/** 重提审批单在工作区新标签追溯上一张被驳回申请，当前详情页保持不变。 */
function openSourceApplicationDetail(sourceApplicationId: string) {
  void router.push({
    path: `/workbench/approvals/${encodeURIComponent(sourceApplicationId)}`,
  });
}

function ensureHandoff() {
  const record = application.value;
  const actorId = currentIdentity.value.id?.trim();
  if (!record) throw new Error('申请不存在');
  if (!actorId) throw new Error('当前办理人缺少稳定用户 ID');
  return bridge.handoffAfterApproval(record.id, {
    id: actorId,
    name: currentIdentity.value.name,
  });
}

function goIssue() {
  try {
    if (!mediaApplication.value) ensureHandoff();
    void router.push({
      path: `/workbench/approvals/${encodeURIComponent(applicationId.value)}/issue`,
      query: isFusionDemoMode() ? { profile: demoProfile.value } : undefined,
    });
  } catch (error) {
    message.error(error instanceof Error ? error.message : '无法进入账号发放');
  }
}

function addLocalComment(comment: ApplicationComment) {
  const record = application.value;
  if (!record || record.comments.some((item) => item.id === comment.id)) return;
  record.comments.push(comment);
}

async function loadBackendApplication() {
  if (!isBackendApplication.value) return;
  if (!application.value) isApplicationLoading.value = true;
  try {
    const detail = await assetFlowApi.application(applicationId.value, {
      skipErrorMessage: true,
    });
    cachedApplication.value = mapBackendApplication(
      detail,
      currentIdentity.value,
    );
    sessionStorage.setItem(
      `adpulse:approval-route:${applicationId.value}`,
      JSON.stringify(cachedApplication.value),
    );
  } catch (error) {
    message.error(
      error instanceof Error
        ? `申请详情刷新失败：${error.message}`
        : '申请详情刷新失败，请返回审批中心重试',
    );
  } finally {
    isApplicationLoading.value = false;
  }
}

async function loadApplicationComments() {
  const record = application.value;
  if (!record || !isBackendApplication.value) return;
  try {
    const comments = await assetFlowApi.comments(record.id);
    // 评论接口异常或返回非列表数据时，详情页仍须保留可读和可返回的状态。
    record.comments = Array.isArray(comments) ? comments : [];
  } catch {
    record.comments = [];
    message.warning('审批评论加载失败，申请详情仍可正常查看');
  }
}

async function publishApplicationComment(content: string) {
  return assetFlowApi.comment(applicationId.value, content);
}

onMounted(async () => {
  await loadBackendApplication();
  await loadApplicationComments();
});

function resetDecisionDialog() {
  decisionDialogOpen.value = false;
  decisionForm.remark = '';
  decisionError.value = '';
}

function openDecision(action: 'approved' | 'rejected') {
  if (!canHandle.value || submitting.value) return;
  decisionAction.value = action;
  decisionForm.remark = '';
  decisionError.value = '';
  decisionDialogOpen.value = true;
}

function closeDecision() {
  if (submitting.value) return;
  resetDecisionDialog();
}

async function submitDecision() {
  const record = application.value;
  const action = decisionAction.value;
  const remark = decisionForm.remark.trim();
  if (!record) return;
  if (action === 'rejected' && !remark) {
    decisionError.value = '请填写本节点审批意见';
    return;
  }
  if (!canHandle.value) {
    message.warning('当前审批节点或权限已变化，请返回审批中心刷新');
    return;
  }

  submitting.value = true;
  try {
    if (isBackendApplication.value) {
      let updatedApplication: AssetApplication;
      if (action === 'approved') {
        updatedApplication = await assetFlowApi.approve(record.id, remark);
        message.success('本节点审批已通过，流程已流转');
      } else {
        updatedApplication = await assetFlowApi.reject(record.id, remark);
        message.success('申请已驳回并完成留痕');
      }
      sessionStorage.setItem(
        APPROVAL_LIST_UPDATED_RECORD_KEY,
        JSON.stringify(updatedApplication),
      );
      resetDecisionDialog();
      sessionStorage.removeItem(`adpulse:approval-route:${record.id}`);
      goBack();
      return;
    }
    const input = {
      actor: {
        id: currentIdentity.value.id,
        name: currentIdentity.value.name,
        role: currentIdentity.value.roleLabel,
      },
      remark,
    };
    const decided =
      action === 'approved'
        ? applicationService.approve(record.id, input)
        : applicationService.reject(record.id, input);
    resetDecisionDialog();

    if (
      action === 'approved' &&
      decided.status === 'approved' &&
      decided.type === 'account'
    ) {
      ensureHandoff();
      message.success('审批已通过，申请已进入账号发放环节');
      goIssue();
      return;
    }
    message.success(
      action === 'approved' ? '本节点审批已通过' : '申请已驳回并完成留痕',
    );
  } catch (error) {
    message.error(error instanceof Error ? error.message : '审批办理失败');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Page
    auto-content-height
    class="adpulse-section-page bg-muted/40"
    content-class="pb-0"
  >
    <div class="flex min-h-0 w-full min-w-0 flex-col gap-3 p-3 sm:p-4">
      <header
        class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div
          class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"
        >
          <div class="flex min-w-0 items-start gap-3">
            <Button aria-label="返回审批中心" class="shrink-0" @click="goBack">
              <IconifyIcon icon="lucide:arrow-left" />
            </Button>
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h1
                  class="m-0 text-xl font-semibold text-slate-900 dark:text-white"
                >
                  {{
                    application?.title ||
                    (isApplicationLoading
                      ? '正在加载审批申请…'
                      : '审批申请不存在')
                  }}
                </h1>
                <Tag
                  v-if="application"
                  :color="statusMeta[application.status].color"
                  class="!m-0"
                >
                  {{ statusMeta[application.status].label }}
                </Tag>
              </div>
              <p class="mb-0 mt-1 font-mono text-xs text-slate-500">
                {{ applicationId }}
              </p>
            </div>
          </div>
        </div>
      </header>

      <Card v-if="isApplicationLoading" aria-busy="true" aria-live="polite">
        <Skeleton active :paragraph="{ rows: 4 }" />
      </Card>

      <Alert
        v-else-if="isApplicationNotFound(application, isApplicationLoading)"
        message="未找到该审批申请"
        description="该申请可能已被删除，请返回审批中心重新选择。"
        show-icon
        type="warning"
      />

      <template v-else-if="application">
        <main class="min-h-0 min-w-0 flex-1 overflow-y-auto">
          <Card :body-style="{ padding: '0 20px 20px' }">
            <Tabs v-model:active-key="activeTab">
              <Tabs.TabPane key="info" tab="申请信息">
                <div class="space-y-5 pt-1">
                  <section aria-labelledby="approval-application-info-heading">
                    <h2
                      id="approval-application-info-heading"
                      class="m-0 text-base font-semibold text-slate-900 dark:text-white"
                    >
                      申请信息
                    </h2>
                    <dl
                      class="mb-0 mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
                    >
                      <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
                        <dt class="text-xs text-slate-500">申请人</dt>
                        <dd class="m-0 mt-1 font-medium">
                          {{ application.requester }}
                        </dd>
                      </div>
                      <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
                        <dt class="text-xs text-slate-500">当前审批人</dt>
                        <dd class="m-0 mt-1 font-medium">
                          {{ application.approver || '—' }}
                        </dd>
                      </div>
                      <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
                        <dt class="text-xs text-slate-500">申请时间</dt>
                        <dd class="m-0 mt-1 font-medium">
                          {{ formatApplicationDateTime(application.createdAt) }}
                        </dd>
                      </div>
                      <div
                        v-if="application.sourceApplicationId"
                        class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800"
                      >
                        <dt class="text-xs text-slate-500">原申请</dt>
                        <dd class="m-0 mt-1">
                          <Button
                            class="!px-0"
                            type="link"
                            @click="
                              openSourceApplicationDetail(
                                application.sourceApplicationId,
                              )
                            "
                          >
                            查看原申请
                          </Button>
                        </dd>
                      </div>
                    </dl>

                    <div
                      v-if="configuredFields.length > 0"
                      class="mt-4 rounded-lg border border-slate-100 p-4 dark:border-slate-800"
                    >
                      <h3 class="m-0 text-sm font-semibold">申请明细</h3>
                      <div
                        class="mt-3 grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2"
                      >
                        <template
                          v-for="field in configuredFields"
                          :key="field.key"
                        >
                          <section
                            v-if="field.type === 'section'"
                            class="rounded-lg bg-slate-50 px-3 py-2 sm:col-span-2 dark:bg-slate-800"
                          >
                            <h4 class="m-0 text-sm font-semibold">
                              {{ field.label }}
                            </h4>
                            <p
                              v-if="field.helpText"
                              class="mb-0 mt-1 text-xs text-slate-500"
                            >
                              {{ field.helpText }}
                            </p>
                          </section>
                          <dl
                            v-else
                            class="mb-0"
                            :class="
                              field.width === 'full' ? 'sm:col-span-2' : ''
                            "
                          >
                            <dt class="text-xs text-slate-500">
                              {{ field.label }}
                            </dt>
                            <dd
                              class="mb-0 mt-1 whitespace-pre-wrap break-words text-sm text-slate-700 dark:text-slate-200"
                            >
                              {{ configuredFieldValue(field) }}
                            </dd>
                          </dl>
                        </template>
                      </div>
                    </div>
                  </section>

                  <ApplicationProcessingDetails
                    class="border-t border-slate-100 pt-5 dark:border-slate-800"
                    :application="application"
                  />

                  <div
                    class="space-y-5 border-t border-slate-100 pt-5 dark:border-slate-800"
                  >
                    <ApplicationCollaborationPanel
                      :actor-name="currentIdentity.name"
                      :actor-role="currentIdentity.roleLabel"
                      :allow-comment="canComment"
                      :application="application"
                      :submit-comment-request="
                        isBackendApplication
                          ? publishApplicationComment
                          : undefined
                      "
                      @comment-added="addLocalComment"
                    />
                  </div>
                </div>
              </Tabs.TabPane>

              <Tabs.TabPane key="flow" tab="审核流程">
                <div class="space-y-6 pt-1">
                  <section aria-labelledby="approval-flow-heading">
                    <h2
                      id="approval-flow-heading"
                      class="m-0 text-base font-semibold text-slate-900 dark:text-white"
                    >
                      审核流程
                    </h2>
                    <ol class="mb-0 mt-3 space-y-2 p-0">
                      <li
                        class="flex list-none items-center gap-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-800"
                      >
                        <span
                          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600"
                        >
                          <IconifyIcon aria-hidden="true" icon="lucide:send" />
                        </span>
                        <div class="min-w-0 flex-1">
                          <p class="m-0 text-sm font-medium">发起申请</p>
                          <p class="mb-0 mt-0.5 text-xs text-slate-500">
                            {{ application.requester }} ·
                            {{
                              formatApplicationDateTime(application.createdAt)
                            }}
                          </p>
                        </div>
                        <Tag color="success" class="!m-0 shrink-0">已发起</Tag>
                      </li>
                      <li
                        v-for="(node, index) in application.approvalNodes"
                        :key="node.id"
                        class="flex list-none items-start gap-3 rounded-lg border border-slate-100 p-3 dark:border-slate-800"
                      >
                        <span
                          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-50 text-sm font-semibold text-amber-600"
                        >
                          {{ index + 1 }}
                        </span>
                        <div class="min-w-0 flex-1">
                          <p class="m-0 break-words text-sm font-medium">
                            {{ node.label }}
                          </p>
                          <p
                            class="mb-0 mt-0.5 break-words text-xs text-slate-500"
                          >
                            {{ node.approver }}
                          </p>
                          <p
                            v-if="node.remark"
                            class="mb-0 mt-1 break-words text-xs text-slate-600"
                          >
                            节点备注：{{ node.remark }}
                          </p>
                        </div>
                        <Tag
                          :color="approvalNodeMeta[node.status].color"
                          class="!m-0 shrink-0"
                        >
                          {{ approvalNodeMeta[node.status].label }}
                        </Tag>
                      </li>
                      <li
                        class="flex list-none items-center gap-3 rounded-lg border border-slate-100 p-3 dark:border-slate-800"
                      >
                        <span
                          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-teal-50 text-teal-600"
                        >
                          <IconifyIcon
                            aria-hidden="true"
                            icon="lucide:briefcase-business"
                          />
                        </span>
                        <div class="min-w-0 flex-1">
                          <p class="m-0 text-sm font-medium">业务办理</p>
                          <p
                            class="mb-0 mt-0.5 break-words text-xs text-slate-500"
                          >
                            {{ application.handlerName || '未配置办理人' }}
                          </p>
                        </div>
                        <Tag
                          :color="handlerStageMeta.color"
                          class="!m-0 shrink-0"
                        >
                          {{ handlerStageMeta.label }}
                        </Tag>
                      </li>
                    </ol>
                  </section>

                  <section aria-labelledby="workflow-participants-heading">
                    <h2
                      id="workflow-participants-heading"
                      class="m-0 text-base font-semibold text-slate-900 dark:text-white"
                    >
                      流程参与人
                    </h2>
                    <div
                      class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3"
                    >
                      <div
                        class="rounded-lg border border-slate-100 p-3 dark:border-slate-800"
                      >
                        <p class="m-0 text-xs text-slate-500">申请人</p>
                        <p class="mb-0 mt-1 break-words font-medium">
                          {{ application.requester }}
                        </p>
                      </div>
                      <div
                        v-for="node in application.approvalNodes"
                        :key="`participant-${node.id}`"
                        class="rounded-lg border border-slate-100 p-3 dark:border-slate-800"
                      >
                        <p class="m-0 text-xs text-slate-500">
                          {{ node.label }}
                        </p>
                        <p class="mb-0 mt-1 break-words font-medium">
                          {{ node.approver }}
                        </p>
                      </div>
                      <div
                        class="rounded-lg border border-slate-100 p-3 dark:border-slate-800"
                      >
                        <p class="m-0 text-xs text-slate-500">办理人</p>
                        <p class="mb-0 mt-1 break-words font-medium">
                          {{ application.handlerName || '未配置办理人' }}
                        </p>
                      </div>
                      <div
                        class="rounded-lg border border-slate-100 p-3 dark:border-slate-800"
                      >
                        <p class="m-0 text-xs text-slate-500">抄送人</p>
                        <p class="mb-0 mt-1 break-words font-medium">
                          {{ application.ccUsers.join('、') || '未设置抄送人' }}
                        </p>
                      </div>
                    </div>
                  </section>
                </div>
              </Tabs.TabPane>

              <Tabs.TabPane key="records">
                <template #tab>
                  审批记录
                  <span class="ml-1 text-xs text-slate-400">
                    {{ application.approvalRecords.length }}
                  </span>
                </template>
                <section
                  aria-labelledby="approval-records-heading"
                  class="pt-1"
                >
                  <h2
                    id="approval-records-heading"
                    class="m-0 text-base font-semibold text-slate-900 dark:text-white"
                  >
                    审批记录
                  </h2>
                  <ol
                    v-if="application.approvalRecords.length > 0"
                    class="mb-0 mt-3 space-y-3 p-0"
                  >
                    <li
                      v-for="record in application.approvalRecords"
                      :key="record.id"
                      class="list-none rounded-lg border border-slate-100 p-4 dark:border-slate-800"
                    >
                      <div
                        class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
                      >
                        <div class="min-w-0">
                          <p class="m-0 break-words text-sm font-medium">
                            {{ record.actor }} · {{ record.actorRole }}
                          </p>
                          <time
                            class="mt-1 block text-xs text-slate-400"
                            :datetime="record.at"
                          >
                            {{ formatApplicationDateTime(record.at) }}
                          </time>
                        </div>
                        <Tag
                          :color="approvalActionMeta[record.action].color"
                          class="!m-0 w-fit shrink-0"
                        >
                          {{ approvalActionMeta[record.action].label }}
                        </Tag>
                      </div>
                      <p
                        class="mb-0 mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-slate-700 dark:text-slate-200"
                      >
                        {{ record.remark || '暂无备注' }}
                      </p>
                    </li>
                  </ol>
                  <p
                    v-else
                    class="mb-0 mt-3 rounded-lg border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500 dark:border-slate-700"
                  >
                    暂无审批记录
                  </p>
                </section>
              </Tabs.TabPane>
            </Tabs>
          </Card>
        </main>

        <div
          v-if="canHandle || canIssueAccount"
          class="z-20 w-full shrink-0"
          role="region"
          aria-label="审批办理操作"
        >
          <div
            class="flex w-full flex-wrap items-center justify-end gap-2 rounded-xl border border-slate-200 bg-white/95 px-4 py-3 shadow-[0_-8px_24px_rgb(15_23_42_/_0.10)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/95"
          >
            <span class="mr-auto text-sm text-slate-500 sm:mr-2">
              {{ canHandle ? '当前节点可审批' : '当前节点可办理' }}
            </span>
            <template v-if="canHandle">
              <Button
                danger
                class="!text-red-600"
                :disabled="submitting"
                :loading="submitting"
                @click="openDecision('rejected')"
              >
                驳回
              </Button>
              <Button
                type="primary"
                :disabled="submitting"
                :loading="submitting"
                @click="openDecision('approved')"
              >
                通过
              </Button>
            </template>
            <Button v-else type="primary" @click="goIssue">
              {{
                mediaApplication?.status === 'approved'
                  ? '查看发放结果'
                  : '办理'
              }}
            </Button>
          </div>
        </div>
      </template>
    </div>

    <Modal
      :cancel-button-props="{ disabled: submitting }"
      cancel-text="取消"
      :closable="!submitting"
      :confirm-loading="submitting"
      destroy-on-close
      :keyboard="!submitting"
      :mask-closable="!submitting"
      :ok-button-props="{ danger: decisionAction === 'rejected' }"
      :ok-text="decisionAction === 'approved' ? '确认通过' : '确认驳回'"
      :open="decisionDialogOpen"
      :title="decisionAction === 'approved' ? '通过申请' : '驳回申请'"
      wrap-class-name="approval-decision-modal"
      @cancel="closeDecision"
      @ok="submitDecision"
    >
      <div v-if="application">
        <div
          class="mb-4 rounded-lg p-3 text-sm leading-6"
          :class="
            decisionAction === 'approved'
              ? 'bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300'
              : 'bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300'
          "
        >
          <template v-if="decisionAction === 'approved'">
            将通过“{{
              application.title
            }}”。若这是最后一个审批节点，申请将转交办理人继续处理；填写的本节点意见会永久留痕。
          </template>
          <template v-else>
            将驳回“{{
              application.title
            }}”。本节点意见会同步给申请人并永久留痕。
          </template>
        </div>
        <label
          for="approval-handle-remark"
          class="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-200"
        >
          本节点审批意见
          <template v-if="decisionAction === 'rejected'">
            <span aria-hidden="true" class="text-red-500">*</span>
            <span class="sr-only">（必填）</span>
          </template>
        </label>
        <Input.TextArea
          id="approval-handle-remark"
          v-model:value="decisionForm.remark"
          :aria-describedby="
            decisionError ? 'approval-handle-remark-error' : undefined
          "
          :aria-invalid="Boolean(decisionError)"
          :aria-required="decisionAction === 'rejected'"
          autofocus
          :maxlength="300"
          :placeholder="
            decisionAction === 'approved'
              ? '请说明核验结论、通过依据或后续交付要求'
              : '请说明缺少的资料、需调整的内容或不通过原因'
          "
          :rows="5"
          show-count
          @update:value="decisionError = ''"
        />
        <p
          v-if="decisionError"
          id="approval-handle-remark-error"
          class="mb-0 mt-2 text-sm text-red-600 dark:text-red-400"
          role="alert"
        >
          {{ decisionError }}
        </p>
      </div>
    </Modal>
  </Page>
</template>
