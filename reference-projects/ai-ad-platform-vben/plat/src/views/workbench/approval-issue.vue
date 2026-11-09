<script lang="ts" setup>
/* eslint-disable vue/html-closing-bracket-newline */
import type { MediaAccount } from '#/store/media-resource';

import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Alert, Button, Card, Table, Tag, message } from 'ant-design-vue';

import { isFusionDemoMode } from '#/api';
import { useApprovalResourceFlow } from '#/composables/use-approval-resource-flow';

defineOptions({ name: 'WorkbenchApprovalIssue' });

const route = useRoute();
const router = useRouter();
const { applications, bridge, mediaResourceStore } = useApprovalResourceFlow();

const applicationId = computed(() => String(route.params.id ?? ''));
const application = computed(() =>
  applications.value.find((item) => item.id === applicationId.value),
);
const resourceApplication = computed(() => {
  const record = application.value;
  if (!record) return;
  return mediaResourceStore.applications.find(
    (item) =>
      item.id === record.resourceApplicationId ||
      item.sourceApplicationId === record.id,
  );
});
const actor = computed(() => ({
  id: isFusionDemoMode() ? 'user-media-lead' : 'current-media-operator',
  name: isFusionDemoMode() ? '周敏' : '当前媒介办理人',
}));
const requestedCount = computed(
  () =>
    resourceApplication.value?.requestedAccountCount ??
    application.value?.quantity ??
    0,
);
const issuedCount = computed(
  () => resourceApplication.value?.approvedAccountIds.length ?? 0,
);
const remainingCount = computed(() =>
  Math.max(0, requestedCount.value - issuedCount.value),
);
const platform = computed(() =>
  (resourceApplication.value?.platform ?? application.value?.platform ?? '')
    .toLowerCase()
    .trim(),
);
const selectedAccountIds = ref<string[]>([]);
const submitting = ref(false);

const issuedAccounts = computed(() => {
  const ids = new Set(resourceApplication.value?.approvedAccountIds ?? []);
  return mediaResourceStore.accounts.filter((account) => ids.has(account.id));
});
const eligibleAccounts = computed(() =>
  mediaResourceStore.accounts.filter(
    (account) =>
      account.platform === platform.value &&
      account.platformStatus === 'active' &&
      account.resourceStatus === 'available',
  ),
);
const isComplete = computed(
  () => resourceApplication.value?.status === 'approved',
);
const isIssueReady = computed(
  () =>
    application.value?.type === 'account' &&
    ['approved', 'processing'].includes(application.value.status) &&
    !isComplete.value,
);

const columns = [
  { key: 'account', title: '账号', width: 220 },
  { key: 'channel', title: '渠道 / 代理线', width: 190 },
  { key: 'businessManager', title: 'BM', width: 170 },
  { key: 'timezone', title: '开户时区', width: 150 },
  { key: 'legalEntity', title: '所属主体', width: 210 },
  { key: 'balance', title: '账户余额', width: 130 },
  { key: 'whitelist', title: '白名单', width: 110 },
];

const rowSelection = computed(() => ({
  getCheckboxProps: (record: MediaAccount) => ({
    disabled:
      !isIssueReady.value ||
      (selectedAccountIds.value.length >= remainingCount.value &&
        !selectedAccountIds.value.includes(record.id)),
  }),
  onChange: (keys: unknown[]) => {
    selectedAccountIds.value = keys
      .filter((key): key is string => typeof key === 'string')
      .slice(0, remainingCount.value);
  },
  selectedRowKeys: selectedAccountIds.value,
}));

const whitelistMeta = {
  approved: { color: 'success', label: '已通过' },
  not_required: { color: 'default', label: '无需白名单' },
  pending: { color: 'warning', label: '待审核' },
  rejected: { color: 'error', label: '未通过' },
} as const;

function whitelistInfo(value?: string) {
  return (
    whitelistMeta[value as keyof typeof whitelistMeta] ?? whitelistMeta.pending
  );
}

function formatMoney(value?: number, currency = 'USD') {
  if (value === undefined) return '—';
  return new Intl.NumberFormat('zh-CN', {
    currency,
    maximumFractionDigits: 2,
    style: 'currency',
  }).format(value);
}

function platformLabel(value: string) {
  if (value === 'facebook') return 'Facebook';
  if (value === 'google') return 'Google';
  if (value === 'tiktok') return 'TikTok';
  if (value === 'kwai') return 'Kwai';
  return value || '—';
}

function goBack() {
  void router.push({
    path: `/workbench/approvals/${encodeURIComponent(applicationId.value)}`,
    query: route.query.profile ? { profile: route.query.profile } : undefined,
  });
}

function ensureResourceApplication() {
  const record = application.value;
  if (!record) throw new Error('审批申请不存在');
  const result = bridge.handoffAfterApproval(record.id, actor.value);
  return result.resourceApplication;
}

async function confirmIssue() {
  if (!isIssueReady.value) {
    message.warning('业务审批完成后才可确认发放账号');
    return;
  }
  if (selectedAccountIds.value.length === 0) {
    message.warning('请至少选择一个可用账号');
    return;
  }
  submitting.value = true;
  try {
    const target = resourceApplication.value ?? ensureResourceApplication();
    if (!target) throw new Error('未能创建媒介资源发放任务');
    bridge.completeResourceApproval(
      target.id,
      selectedAccountIds.value,
      actor.value,
    );
    selectedAccountIds.value = [];
    if (resourceApplication.value?.status === 'approved') {
      message.success('账号已全部发放，申请流程完成');
    } else {
      message.success('账号已发放，剩余数量可继续办理');
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : '账号发放失败');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Page class="bg-slate-50 dark:bg-slate-950" content-class="pb-8">
    <div class="mx-auto w-full max-w-[1580px] space-y-4 p-3 sm:p-4 lg:p-5">
      <header
        class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div
          class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"
        >
          <div class="flex min-w-0 items-start gap-3">
            <Button aria-label="返回审批办理" class="shrink-0" @click="goBack">
              <IconifyIcon icon="lucide:arrow-left" />
            </Button>
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h1
                  class="m-0 text-xl font-semibold text-slate-900 dark:text-white"
                >
                  发放媒介账号
                </h1>
                <Tag
                  :color="
                    isComplete
                      ? 'success'
                      : application?.status === 'pending'
                        ? 'warning'
                        : 'processing'
                  "
                  class="!m-0"
                >
                  {{
                    isComplete
                      ? '发放完成'
                      : application?.status === 'pending'
                        ? '审批未完成'
                        : '待选账号'
                  }}
                </Tag>
              </div>
              <p class="mb-0 mt-1 text-sm text-slate-500">
                {{ application?.title || applicationId }}
              </p>
            </div>
          </div>
          <div
            class="rounded-lg bg-slate-50 px-4 py-2 text-sm dark:bg-slate-800"
          >
            办理人：<strong>{{ actor.name }}</strong>
          </div>
        </div>
      </header>

      <Alert
        v-if="!application"
        message="未找到对应的审批申请"
        show-icon
        type="error"
      />
      <Alert
        v-if="application?.status === 'pending'"
        message="业务审批尚未完成"
        description="当前为可发放账号预览；请返回办理页面完成审批后再确认发放。"
        show-icon
        type="warning"
      />

      <template v-if="application">
        <section
          aria-label="发放概览"
          class="grid grid-cols-2 gap-3 lg:grid-cols-4"
        >
          <Card>
            <div class="text-sm text-slate-500">申请数量</div>
            <strong class="mt-1 block text-2xl">{{ requestedCount }}</strong>
          </Card>
          <Card>
            <div class="text-sm text-slate-500">已发放</div>
            <strong class="mt-1 block text-2xl text-emerald-600">{{
              issuedCount
            }}</strong>
          </Card>
          <Card>
            <div class="text-sm text-slate-500">待发放</div>
            <strong class="mt-1 block text-2xl text-amber-600">{{
              remainingCount
            }}</strong>
          </Card>
          <Card>
            <div class="text-sm text-slate-500">可选库存</div>
            <strong class="mt-1 block text-2xl text-blue-600">{{
              eligibleAccounts.length
            }}</strong>
          </Card>
        </section>

        <Card title="发放要求">
          <dl class="m-0 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
              <dt class="text-xs text-slate-500">平台</dt>
              <dd class="m-0 mt-1 font-medium">
                {{ platformLabel(platform) }}
              </dd>
            </div>
            <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
              <dt class="text-xs text-slate-500">使用人</dt>
              <dd class="m-0 mt-1 font-medium">
                {{
                  resourceApplication?.assigneeName ||
                  application.resourceRequest?.assigneeName ||
                  '—'
                }}
              </dd>
            </div>
            <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
              <dt class="text-xs text-slate-500">使用团队</dt>
              <dd class="m-0 mt-1 font-medium">
                {{
                  resourceApplication?.teamName ||
                  application.resourceRequest?.teamName ||
                  '—'
                }}
              </dd>
            </div>
            <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-800">
              <dt class="text-xs text-slate-500">要求时区</dt>
              <dd class="m-0 mt-1 font-medium">
                {{
                  resourceApplication?.timezone ||
                  application.resourceRequest?.timezone ||
                  '不限'
                }}
              </dd>
            </div>
          </dl>
        </Card>

        <Card v-if="issuedAccounts.length > 0" title="已发放账号">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            <article
              v-for="account in issuedAccounts"
              :key="account.id"
              class="rounded-xl border border-emerald-200 bg-emerald-50 p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <strong class="block truncate" :title="account.name">{{
                    account.name
                  }}</strong>
                  <span
                    class="mt-1 block truncate font-mono text-xs text-slate-500"
                    >{{ account.accountId }}</span
                  >
                </div>
                <Tag color="success" class="!m-0 shrink-0">已发放</Tag>
              </div>
              <p class="mb-0 mt-3 text-sm text-slate-600">
                {{ account.channelName || '未设置渠道' }} ·
                {{ account.timezone || '未设置时区' }}
              </p>
            </article>
          </div>
        </Card>

        <Card v-if="!isComplete" :body-style="{ padding: 0 }">
          <div
            class="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800"
          >
            <div>
              <h2 class="m-0 text-base font-semibold">选择媒介资源中心账号</h2>
              <p class="mb-0 mt-1 text-sm text-slate-500">
                仅展示平台正常且库存状态为“可用”的账号，最多再选
                {{ remainingCount }} 个。
              </p>
            </div>
            <Button
              :disabled="!isIssueReady || selectedAccountIds.length === 0"
              :loading="submitting"
              type="primary"
              @click="confirmIssue"
            >
              <IconifyIcon icon="lucide:send" />
              确认发放
              {{
                selectedAccountIds.length > 0 ? selectedAccountIds.length : ''
              }}
            </Button>
          </div>

          <div class="hidden md:block">
            <Table
              :columns="columns"
              :data-source="eligibleAccounts"
              :pagination="false"
              :row-key="(record) => record.id"
              :row-selection="rowSelection"
              :scroll="{ x: 1200 }"
              table-layout="fixed"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'account'">
                  <div class="min-w-0">
                    <strong class="block truncate" :title="record.name">{{
                      record.name
                    }}</strong>
                    <span
                      class="mt-1 block truncate font-mono text-xs text-slate-500"
                      >{{ record.accountId }}</span
                    >
                  </div>
                </template>
                <template v-else-if="column.key === 'channel'">
                  <div class="truncate" :title="record.channelName">
                    {{ record.channelName || '—' }}
                  </div>
                  <div
                    class="mt-1 truncate text-xs text-slate-500"
                    :title="record.agencyLineName"
                  >
                    {{ record.agencyLineName || '—' }}
                  </div>
                </template>
                <template v-else-if="column.key === 'businessManager'">
                  <div class="truncate" :title="record.businessManagerName">
                    {{ record.businessManagerName || '—' }}
                  </div>
                  <div class="mt-1 truncate font-mono text-xs text-slate-500">
                    {{ record.businessManagerId || '—' }}
                  </div>
                </template>
                <template v-else-if="column.key === 'timezone'">
                  {{ record.timezone || '—' }}
                </template>
                <template v-else-if="column.key === 'legalEntity'">
                  <span
                    class="block truncate"
                    :title="record.legalEntityName"
                    >{{ record.legalEntityName || '—' }}</span
                  >
                </template>
                <template v-else-if="column.key === 'balance'">
                  {{ formatMoney(record.balance, record.currency) }}
                </template>
                <template v-else-if="column.key === 'whitelist'">
                  <Tag
                    :color="whitelistInfo(record.whitelistStatus).color"
                    class="!m-0"
                  >
                    {{ whitelistInfo(record.whitelistStatus).label }}
                  </Tag>
                </template>
              </template>
            </Table>
          </div>

          <div class="grid grid-cols-1 gap-3 p-3 md:hidden">
            <label
              v-for="account in eligibleAccounts"
              :key="account.id"
              class="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 p-4"
            >
              <input
                v-model="selectedAccountIds"
                class="mt-1"
                type="checkbox"
                :value="account.id"
                :disabled="
                  !isIssueReady ||
                  (selectedAccountIds.length >= remainingCount &&
                    !selectedAccountIds.includes(account.id))
                "
              />
              <span class="min-w-0 flex-1">
                <strong class="block truncate">{{ account.name }}</strong>
                <span
                  class="mt-1 block truncate font-mono text-xs text-slate-500"
                  >{{ account.accountId }}</span
                >
                <span class="mt-2 block text-xs text-slate-500"
                  >{{ account.channelName }} · {{ account.timezone }}</span
                >
              </span>
            </label>
          </div>
        </Card>
      </template>
    </div>
  </Page>
</template>
