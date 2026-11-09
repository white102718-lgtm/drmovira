<script lang="ts" setup>
import type { FormInstance, FormProps, TableColumnsType } from 'ant-design-vue';

import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  DescriptionsItem,
  Drawer,
  Empty,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  UploadDragger,
} from 'ant-design-vue';

import { useMediaResourceStore } from '#/store/media-resource';

import AssetManagementPanel from './components/AssetManagementPanel.vue';
import MediaResourcePage from './components/MediaResourcePage.vue';

type UnknownRecord = Record<string, unknown>;

const route = useRoute();
const router = useRouter();
const mediaStore = useMediaResourceStore();

type MediaAccount = (typeof mediaStore.accounts)[number];
type CreateAccountInput = Parameters<typeof mediaStore.createAccount>[0];

interface InboundFormState {
  accountId: string;
  agencyLineName: string;
  balance?: number;
  businessManagerId: string;
  channelName: string;
  currency: string;
  legalEntityName: string;
  name: string;
  notes: string;
  platform: string;
  platformStatus: string;
  resourceStatus: string;
  spendCap?: number;
  tags: string[];
  timezone: string;
  whitelistStatus: string;
}

interface BatchAccountRow {
  accountId: string;
  channelName: string;
  currency: string;
  issue: string;
  legalEntityName: string;
  line: number;
  name: string;
  platform: string;
  timezone: string;
  valid: boolean;
}

const platformMeta: Record<
  string,
  { color: string; icon: string; label: string }
> = {
  facebook: {
    color: 'blue',
    icon: 'simple-icons:facebook',
    label: 'Facebook',
  },
  google: {
    color: 'geekblue',
    icon: 'simple-icons:googleads',
    label: 'Google',
  },
  kwai: {
    color: 'orange',
    icon: 'simple-icons:kuaishou',
    label: 'Kwai',
  },
  tiktok: {
    color: 'default',
    icon: 'simple-icons:tiktok',
    label: 'TikTok',
  },
};

const platformStatusMeta: Record<string, { color: string; label: string }> = {
  active: { color: 'success', label: '正常' },
  closed: { color: 'default', label: '已关闭' },
  disabled: { color: 'error', label: '已禁用' },
  pending_review: { color: 'processing', label: '待审核' },
  restricted: { color: 'warning', label: '受限' },
  unsettled: { color: 'warning', label: '未结算' },
};

const resourceStatusMeta: Record<string, { color: string; label: string }> = {
  assigned: { color: 'blue', label: '已分配' },
  available: { color: 'success', label: '可用' },
  exception: { color: 'error', label: '异常' },
  maintenance: { color: 'default', label: '维护中' },
  pending_assignment: { color: 'cyan', label: '待分配 / 已预占' },
  pending_return: { color: 'warning', label: '待回收' },
  retired: { color: 'default', label: '已退役' },
};

const whitelistStatusMeta: Record<string, { color: string; label: string }> = {
  approved: { color: 'success', label: '已加白' },
  not_required: { color: 'default', label: '无需加白' },
  pending: { color: 'processing', label: '待确认' },
  rejected: { color: 'error', label: '未通过' },
};

const platformOptions = Object.entries(platformMeta).map(([value, item]) => ({
  label: item.label,
  value,
}));

const platformStatusOptions = Object.entries(platformStatusMeta).map(
  ([value, item]) => ({ label: item.label, value }),
);

const resourceStatusOptions = [
  { label: '全部库存状态', value: 'all' },
  ...Object.entries(resourceStatusMeta).map(([value, item]) => ({
    label: item.label,
    value,
  })),
  { label: '预占 / 已分配', value: 'reserved,allocated' },
  { label: '今日入库', value: 'today_inbound' },
  { label: '今日出库', value: 'today_outbound' },
  { label: '今日回收', value: 'today_returned' },
];

const whitelistStatusOptions = Object.entries(whitelistStatusMeta).map(
  ([value, item]) => ({ label: item.label, value }),
);

const filters = reactive({
  keyword: '',
  platform: 'all',
  platformStatus: 'all',
  resourceStatus: normalizeQueryStatus(route.query.status),
});

const inboundDrawerOpen = ref(false);
const inboundSaving = ref(false);
const inboundFormRef = ref<FormInstance>();
const detailDrawerOpen = ref(false);
const selectedAccount = ref<MediaAccount>();
const exceptionModalOpen = ref(false);
const exceptionTarget = ref<MediaAccount>();
const exceptionReason = ref('');
const markingException = ref(false);
const batchModalOpen = ref(false);
const batchSaving = ref(false);
const batchText = ref('');

function defaultInboundForm(): InboundFormState {
  return {
    accountId: '',
    balance: undefined,
    businessManagerId: '',
    channelName: '',
    currency: 'USD',
    agencyLineName: '',
    legalEntityName: '',
    name: '',
    platform: 'facebook',
    platformStatus: 'active',
    notes: '',
    resourceStatus: 'available',
    spendCap: undefined,
    tags: [],
    timezone: 'UTC+0',
    whitelistStatus: 'pending',
  };
}

const inboundForm = reactive<InboundFormState>(defaultInboundForm());

const inboundRules: FormProps['rules'] = {
  accountId: [
    { required: true, message: '请输入平台账户 ID', trigger: 'blur' },
  ],
  channelName: [{ required: true, message: '请输入资源渠道', trigger: 'blur' }],
  legalEntityName: [
    { required: true, message: '请输入授权主体', trigger: 'blur' },
  ],
  name: [{ required: true, message: '请输入账户名称', trigger: 'blur' }],
  platform: [{ required: true, message: '请选择投放平台', trigger: 'change' }],
  whitelistStatus: [
    { required: true, message: '请选择加白状态', trigger: 'change' },
  ],
};

const columns: TableColumnsType<MediaAccount> = [
  { key: 'account', title: '账户 / 平台', width: '24%' },
  { key: 'resourceProfile', title: '资源 / 状态', width: '29%' },
  { key: 'ownership', title: '项目 / 使用 / 消耗', width: '28%' },
  { key: 'actions', title: '更新 / 操作', width: '19%' },
];

const batchColumns: TableColumnsType<BatchAccountRow> = [
  { dataIndex: 'line', key: 'line', title: '行', width: '8%' },
  { key: 'account', title: '账户', width: '28%' },
  { key: 'source', title: '平台 / 渠道', width: '24%' },
  {
    dataIndex: 'legalEntityName',
    key: 'legalEntityName',
    title: '授权主体',
    width: '20%',
  },
  { key: 'validation', title: '校验结果', width: '20%' },
];

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' ? (value as UnknownRecord) : {};
}

function pick(value: unknown, ...keys: string[]) {
  const record = asRecord(value);
  for (const key of keys) {
    const current = record[key];
    if (current !== undefined && current !== null && current !== '') {
      return current;
    }
  }
}

function textOf(value: unknown, ...keys: string[]) {
  const selected = pick(value, ...keys);
  return selected === undefined ? '' : String(selected);
}

function normalizeQueryStatus(value: unknown) {
  const normalized = Array.isArray(value) ? value[0] : value;
  return typeof normalized === 'string' && normalized ? normalized : 'all';
}

function accountKey(account: unknown) {
  return textOf(account, 'id', 'accountId', 'externalAccountId');
}

function externalAccountId(account: unknown) {
  return textOf(account, 'accountId', 'externalAccountId', 'id') || '-';
}

function accountName(account: unknown) {
  return textOf(account, 'name', 'accountName') || '未命名账户';
}

function platformOf(account: unknown) {
  return textOf(account, 'platform').toLowerCase();
}

function platformStatusOf(account: unknown) {
  return textOf(account, 'platformStatus', 'accountStatus') || 'unknown';
}

function resourceStatusOf(account: unknown) {
  return (
    textOf(account, 'resourceStatus', 'inventoryStatus', 'status') || 'unknown'
  );
}

function timestampOf(value: unknown, ...keys: string[]) {
  const raw = pick(value, ...keys);
  if (!raw) return;
  const timestamp = new Date(String(raw));
  return Number.isNaN(timestamp.valueOf()) ? undefined : timestamp;
}

function isToday(timestamp?: Date) {
  if (!timestamp) return false;
  const now = new Date();
  return (
    timestamp.getFullYear() === now.getFullYear() &&
    timestamp.getMonth() === now.getMonth() &&
    timestamp.getDate() === now.getDate()
  );
}

function assignmentFor(account: unknown) {
  const ids = new Set(
    [accountKey(account), externalAccountId(account)].filter(Boolean),
  );
  return (mediaStore.activeAssignments as unknown[]).find((assignment) =>
    ids.has(textOf(assignment, 'accountId', 'mediaAccountId', 'resourceId')),
  );
}

function assignmentProject(account: unknown) {
  return (
    textOf(assignmentFor(account), 'projectName', 'projectId') ||
    textOf(account, 'projectName', 'projectId') ||
    '未分配'
  );
}

function assignmentTeam(account: unknown) {
  return (
    textOf(assignmentFor(account), 'teamName', 'teamId') ||
    textOf(account, 'teamName', 'teamId') ||
    '-'
  );
}

function assignmentUser(account: unknown) {
  return (
    textOf(
      assignmentFor(account),
      'assigneeName',
      'userName',
      'assigneeId',
      'userId',
    ) ||
    textOf(account, 'assigneeName', 'userName') ||
    '-'
  );
}

function todaySpend(account: unknown) {
  const raw = pick(account, 'todaySpend', 'spendToday', 'dailySpend');
  if (raw === undefined) return;
  const value = Number(raw);
  return Number.isFinite(value) ? value : undefined;
}

function currencyOf(account: unknown) {
  return textOf(account, 'currency') || 'USD';
}

function channelNameOf(account: unknown) {
  return textOf(account, 'channelName', 'channel', 'agencyLineName') || '-';
}

function legalEntityNameOf(account: unknown) {
  return (
    textOf(account, 'legalEntityName', 'legalEntity', 'subjectName') || '-'
  );
}

function whitelistStatusOf(account: unknown) {
  return textOf(account, 'whitelistStatus', 'whitelist_status') || 'pending';
}

function formatMoney(value: number | undefined, currency: string) {
  if (value === undefined) return '—';
  try {
    return new Intl.NumberFormat('zh-CN', {
      currency,
      maximumFractionDigits: 2,
      style: 'currency',
    }).format(value);
  } catch {
    return `${currency} ${value.toLocaleString('zh-CN')}`;
  }
}

function formatTime(value: unknown, ...keys: string[]) {
  const raw = pick(value, ...keys);
  if (!raw) return '-';
  const timestamp = new Date(String(raw));
  if (Number.isNaN(timestamp.valueOf())) return String(raw);
  return timestamp.toLocaleString('zh-CN', { hour12: false });
}

const platformAliases: Record<string, string> = {
  fb: 'facebook',
  facebook: 'facebook',
  gg: 'google',
  google: 'google',
  kwai: 'kwai',
  kuai: 'kwai',
  kuaishou: 'kwai',
  tk: 'tiktok',
  tiktok: 'tiktok',
};

const batchRows = computed<BatchAccountRow[]>(() => {
  const existingKeys = new Set(
    mediaStore.accounts.map(
      (account) => `${platformOf(account)}:${externalAccountId(account)}`,
    ),
  );
  const seen = new Set<string>();
  return batchText.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line, index) => {
      if (index !== 0) return true;
      return !/平台|platform/i.test(line);
    })
    .map((line, index) => {
      const [
        rawPlatform,
        accountId = '',
        name = '',
        channelName = '',
        legalEntityName = '',
        currency = 'USD',
        timezone = 'UTC+0',
      ] = line.split(/[,\t]/).map((item) => item.trim());
      const platform = platformAliases[(rawPlatform ?? '').toLowerCase()] ?? '';
      const key = `${platform}:${accountId}`;
      let issue = '';
      if (!platform) issue = '平台不支持';
      else if (!accountId || !name || !channelName || !legalEntityName) {
        issue = '存在必填项为空';
      } else if (existingKeys.has(key)) issue = '账户已存在';
      else if (seen.has(key)) issue = '文件内重复';
      seen.add(key);
      return {
        accountId,
        channelName,
        currency: currency || 'USD',
        issue,
        legalEntityName,
        line: index + 1,
        name,
        platform,
        timezone: timezone || 'UTC+0',
        valid: !issue,
      };
    });
});

const validBatchRows = computed(() =>
  batchRows.value.filter((row) => row.valid),
);

function openBatchModal() {
  batchText.value = '';
  batchModalOpen.value = true;
}

function beforeBatchUpload(file: File) {
  void file
    .text()
    .then((content) => {
      batchText.value = content;
    })
    .catch(() => message.error('文件读取失败，请重试'));
  return false;
}

function downloadBatchTemplate() {
  const content = [
    '平台,账户ID,账户名称,资源渠道,授权主体,币种,时区',
    'facebook,act_100001,Starfall US 01,Meta Direct,Northstar Games,USD,UTC-8',
    'google,100-200-3000,Project Ark Google 01,Google Direct,Ocean Studio,USD,UTC-8',
  ].join('\n');
  const url = URL.createObjectURL(
    new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = '广告账户批量入库模板.csv';
  link.click();
  URL.revokeObjectURL(url);
}

async function submitBatchInbound() {
  if (validBatchRows.value.length === 0) {
    message.warning('没有可入库的有效账户，请先修正校验问题');
    return;
  }
  batchSaving.value = true;
  let successCount = 0;
  let failureCount = 0;
  try {
    for (const row of validBatchRows.value) {
      try {
        await Promise.resolve(
          mediaStore.createAccount({
            accountId: row.accountId,
            channelName: row.channelName,
            currency: row.currency,
            legalEntityName: row.legalEntityName,
            name: row.name,
            platform: row.platform as CreateAccountInput['platform'],
            platformStatus: 'active',
            resourceStatus: 'available',
            tags: ['批量入库'],
            timezone: row.timezone,
            whitelistStatus: 'pending',
          }),
        );
        successCount += 1;
      } catch {
        failureCount += 1;
      }
    }
    if (failureCount) {
      message.warning(`成功入库 ${successCount} 个，失败 ${failureCount} 个`);
    } else {
      message.success(`已批量入库 ${successCount} 个账户`);
    }
    if (successCount) batchModalOpen.value = false;
  } finally {
    batchSaving.value = false;
  }
}

const todayOutboundAccountIds = computed(() => {
  const ids = new Set<string>();
  for (const assignment of mediaStore.assignments as unknown[]) {
    if (
      isToday(timestampOf(assignment, 'assignedAt', 'outboundAt', 'createdAt'))
    ) {
      ids.add(textOf(assignment, 'accountId', 'mediaAccountId', 'resourceId'));
    }
  }
  return ids;
});

const todayReturnedAccountIds = computed(() => {
  const ids = new Set<string>();
  for (const item of mediaStore.returns as unknown[]) {
    if (
      isToday(
        timestampOf(
          item,
          'completedAt',
          'returnedAt',
          'updatedAt',
          'createdAt',
        ),
      )
    ) {
      ids.add(textOf(item, 'accountId', 'mediaAccountId', 'resourceId'));
    }
  }
  return ids;
});

function matchesResourceStatus(account: unknown) {
  const selected = filters.resourceStatus;
  if (selected === 'all') return true;
  if (selected === 'today_inbound') {
    return isToday(
      timestampOf(account, 'inboundAt', 'createdAt', 'created_at'),
    );
  }
  if (selected === 'today_outbound') {
    return [accountKey(account), externalAccountId(account)].some((id) =>
      todayOutboundAccountIds.value.has(id),
    );
  }
  if (selected === 'today_returned') {
    return [accountKey(account), externalAccountId(account)].some((id) =>
      todayReturnedAccountIds.value.has(id),
    );
  }
  if (selected === 'in_use') {
    return [accountKey(account), externalAccountId(account)].some((id) =>
      (mediaStore.activeAssignments as unknown[]).some((assignment) =>
        [
          textOf(assignment, 'mediaAccountId'),
          textOf(assignment, 'platformAccountId'),
        ].includes(id),
      ),
    );
  }
  const statusAliases: Record<string, string> = {
    allocated: 'assigned',
    reserved: 'pending_assignment',
  };
  return selected
    .split(',')
    .map((status) => statusAliases[status] ?? status)
    .includes(resourceStatusOf(account));
}

const filteredAccounts = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase();
  return mediaStore.accounts.filter((account) => {
    const searchable = [
      accountName(account),
      externalAccountId(account),
      textOf(account, 'channelName', 'channelId'),
      textOf(account, 'legalEntityName', 'legalEntityId'),
      textOf(account, 'businessManagerName', 'businessManagerId', 'bmId'),
      textOf(account, 'agencyLineName', 'deliveryLineName', 'agentLineName'),
      assignmentProject(account),
      assignmentTeam(account),
      assignmentUser(account),
    ]
      .join(' ')
      .toLowerCase();
    return (
      (!keyword || searchable.includes(keyword)) &&
      (filters.platform === 'all' ||
        platformOf(account) === filters.platform) &&
      (filters.platformStatus === 'all' ||
        platformStatusOf(account) === filters.platformStatus) &&
      matchesResourceStatus(account)
    );
  });
});

const selectedAssignment = computed(() =>
  selectedAccount.value ? assignmentFor(selectedAccount.value) : undefined,
);

function resetFilters() {
  filters.keyword = '';
  filters.platform = 'all';
  filters.platformStatus = 'all';
  filters.resourceStatus = 'all';
  const query = { ...route.query };
  delete query.status;
  void router.replace({ query });
}

function openInboundDrawer() {
  Object.assign(inboundForm, defaultInboundForm());
  inboundDrawerOpen.value = true;
}

function closeInboundDrawer() {
  if (inboundSaving.value) return;
  inboundDrawerOpen.value = false;
  inboundFormRef.value?.clearValidate();
}

async function submitInbound() {
  try {
    await inboundFormRef.value?.validate();
    inboundSaving.value = true;
    await mediaStore.createAccount({
      ...inboundForm,
      businessManagerId: inboundForm.businessManagerId || undefined,
      agencyLineName: inboundForm.agencyLineName || undefined,
      channelName: inboundForm.channelName || undefined,
      legalEntityName: inboundForm.legalEntityName || undefined,
      notes: inboundForm.notes || undefined,
      tags: inboundForm.tags.length > 0 ? inboundForm.tags : undefined,
    } as CreateAccountInput);
    message.success('账户已入库');
    inboundDrawerOpen.value = false;
    filters.resourceStatus = 'all';
  } catch (error) {
    if (error instanceof Error) message.error(error.message || '账户入库失败');
  } finally {
    inboundSaving.value = false;
  }
}

function openDetails(account: MediaAccount | UnknownRecord) {
  selectedAccount.value = account as MediaAccount;
  detailDrawerOpen.value = true;
}

function openException(account: MediaAccount | UnknownRecord) {
  exceptionTarget.value = account as MediaAccount;
  exceptionReason.value = '';
  exceptionModalOpen.value = true;
}

async function confirmException() {
  if (!exceptionTarget.value) return;
  const reason = exceptionReason.value.trim();
  if (!reason) {
    message.warning('请填写异常原因');
    return;
  }
  markingException.value = true;
  try {
    await mediaStore.markException(accountKey(exceptionTarget.value), reason);
    message.success('已标记为异常账户');
    exceptionModalOpen.value = false;
  } catch (error) {
    message.error(error instanceof Error ? error.message : '标记异常失败');
  } finally {
    markingException.value = false;
  }
}

watch(
  () => route.query.status,
  (status) => {
    filters.resourceStatus = normalizeQueryStatus(status);
  },
);
</script>

<template>
  <MediaResourcePage content-class="!p-4">
    <AssetManagementPanel />
    <template v-if="false">
      <div class="flex w-full min-w-0 flex-col gap-4">
        <section
          class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"
        >
          <div class="min-w-0">
            <h1
              class="m-0 text-2xl font-semibold text-slate-950 dark:text-white"
            >
              广告账户库存
            </h1>
            <p
              class="mb-0 mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400"
            >
              账户平台状态反映渠道可用性，库存状态反映内部流转；两者独立展示与筛选。
            </p>
          </div>
          <Space wrap>
            <Button
              class="!inline-flex flex-none items-center justify-center"
              @click="openBatchModal"
            >
              <IconifyIcon icon="lucide:file-up" />
              批量入库
            </Button>
            <Button
              class="!inline-flex flex-none items-center justify-center"
              type="primary"
              @click="openInboundDrawer"
            >
              <IconifyIcon icon="lucide:package-plus" />
              单个入库
            </Button>
          </Space>
        </section>

        <Card
          class="min-w-0 border-slate-200 dark:border-slate-800"
          :body-style="{ padding: '16px' }"
        >
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            <Input.Search
              v-model:value="filters.keyword"
              allow-clear
              placeholder="搜索账户、项目、团队或使用人"
            />
            <Select
              v-model:value="filters.platform"
              :options="[
                { label: '全部平台', value: 'all' },
                ...platformOptions,
              ]"
            />
            <Select
              v-model:value="filters.platformStatus"
              :options="[
                { label: '全部平台状态', value: 'all' },
                ...platformStatusOptions,
              ]"
            />
            <Select
              v-model:value="filters.resourceStatus"
              :options="resourceStatusOptions"
            />
          </div>
          <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span class="text-sm text-slate-500">
              共 {{ filteredAccounts.length }} 个账户
            </span>
            <Button class="" @click="resetFilters">
              <IconifyIcon icon="lucide:rotate-ccw" />
              重置筛选
            </Button>
          </div>
        </Card>

        <Card
          class="min-w-0 border-slate-200 dark:border-slate-800"
          :body-style="{ padding: 0 }"
        >
          <div class="hidden min-w-0 2xl:block">
            <Table
              :columns="columns"
              :data-source="filteredAccounts"
              :pagination="{
                defaultPageSize: 10,
                hideOnSinglePage: true,
                showSizeChanger: true,
              }"
              :row-key="accountKey"
              table-layout="fixed"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'account'">
                  <button
                    class="block w-full min-w-0 cursor-pointer border-0 bg-transparent p-0 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
                    type="button"
                    @click="openDetails(record)"
                  >
                    <span
                      class="ux-table-link block truncate font-medium"
                      :title="accountName(record)"
                    >
                      {{ accountName(record) }}
                    </span>
                    <span
                      class="mt-1 block truncate font-mono text-xs text-slate-500"
                      :title="externalAccountId(record)"
                    >
                      {{ externalAccountId(record) }}
                    </span>
                    <Tag
                      :color="
                        platformMeta[platformOf(record)]?.color || 'default'
                      "
                      class="!mb-0 !mr-0 !mt-2"
                    >
                      {{
                        platformMeta[platformOf(record)]?.label ||
                        platformOf(record)
                      }}
                    </Tag>
                  </button>
                </template>
                <template v-else-if="column.key === 'resourceProfile'">
                  <div class="min-w-0 text-sm">
                    <div
                      class="truncate font-medium text-slate-800 dark:text-slate-200"
                      :title="channelNameOf(record)"
                    >
                      {{ channelNameOf(record) }}
                    </div>
                    <div
                      class="mt-1 min-w-0 truncate text-xs text-slate-500"
                      :title="legalEntityNameOf(record)"
                    >
                      {{ legalEntityNameOf(record) }}
                    </div>
                    <div class="mt-2 flex flex-wrap gap-1">
                      <Tag
                        class="!m-0"
                        :color="
                          platformStatusMeta[platformStatusOf(record)]?.color ||
                          'default'
                        "
                      >
                        平台 ·
                        {{
                          platformStatusMeta[platformStatusOf(record)]?.label ||
                          platformStatusOf(record)
                        }}
                      </Tag>
                      <Tag
                        class="!m-0"
                        :color="
                          resourceStatusMeta[resourceStatusOf(record)]?.color ||
                          'default'
                        "
                      >
                        库存 ·
                        {{
                          resourceStatusMeta[resourceStatusOf(record)]?.label ||
                          resourceStatusOf(record)
                        }}
                      </Tag>
                      <Tag
                        class="!m-0"
                        :color="
                          whitelistStatusMeta[whitelistStatusOf(record)]
                            ?.color || 'default'
                        "
                      >
                        {{
                          whitelistStatusMeta[whitelistStatusOf(record)]
                            ?.label || whitelistStatusOf(record)
                        }}
                      </Tag>
                    </div>
                  </div>
                </template>
                <template v-else-if="column.key === 'ownership'">
                  <div class="min-w-0 text-sm">
                    <div
                      class="truncate font-medium text-slate-800 dark:text-slate-200"
                    >
                      {{ assignmentProject(record) }}
                    </div>
                    <div class="mt-1 truncate text-xs text-slate-500">
                      {{ assignmentTeam(record) }} ·
                      {{ assignmentUser(record) }}
                    </div>
                    <div
                      class="mt-2 font-medium text-slate-900 dark:text-white"
                    >
                      今日
                      {{ formatMoney(todaySpend(record), currencyOf(record)) }}
                    </div>
                  </div>
                </template>
                <template v-else-if="column.key === 'actions'">
                  <div class="min-w-0">
                    <div class="truncate text-xs text-slate-500">
                      {{
                        formatTime(
                          record,
                          'updatedAt',
                          'lastSyncAt',
                          'createdAt',
                        )
                      }}
                    </div>
                    <div class="mt-1 flex flex-wrap items-center gap-x-1">
                      <Button type="link" @click="openDetails(record)">
                        详情
                      </Button>
                      <Button
                        danger
                        type="link"
                        :disabled="resourceStatusOf(record) === 'exception'"
                        @click="openException(record)"
                      >
                        {{
                          resourceStatusOf(record) === 'exception'
                            ? '已异常'
                            : '标异常'
                        }}
                      </Button>
                    </div>
                  </div>
                </template>
              </template>
              <template #emptyText>
                <Empty
                  description="没有符合筛选条件的账户"
                  :image="Empty.PRESENTED_IMAGE_SIMPLE"
                />
              </template>
            </Table>
          </div>

          <div
            class="grid grid-cols-1 gap-3 p-3 md:grid-cols-2 xl:grid-cols-3 2xl:hidden"
          >
            <Card
              v-for="account in filteredAccounts"
              :key="accountKey(account)"
              class="min-w-0 border-slate-200 dark:border-slate-800"
            >
              <div class="flex min-w-0 items-start justify-between gap-3">
                <button
                  class="min-w-0 cursor-pointer border-0 bg-transparent p-0 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500"
                  type="button"
                  @click="openDetails(account)"
                >
                  <span
                    class="block truncate font-semibold text-slate-900 dark:text-white"
                  >
                    {{ accountName(account) }}
                  </span>
                  <span
                    class="mt-1 block truncate font-mono text-xs text-slate-500"
                  >
                    {{ externalAccountId(account) }}
                  </span>
                </button>
                <Tag
                  :color="platformMeta[platformOf(account)]?.color || 'default'"
                  class="shrink-0"
                >
                  {{
                    platformMeta[platformOf(account)]?.label ||
                    platformOf(account)
                  }}
                </Tag>
              </div>

              <div class="mt-4 flex flex-wrap gap-2">
                <Tag
                  :color="
                    platformStatusMeta[platformStatusOf(account)]?.color ||
                    'default'
                  "
                >
                  平台 ·
                  {{
                    platformStatusMeta[platformStatusOf(account)]?.label ||
                    platformStatusOf(account)
                  }}
                </Tag>
                <Tag
                  :color="
                    resourceStatusMeta[resourceStatusOf(account)]?.color ||
                    'default'
                  "
                >
                  库存 ·
                  {{
                    resourceStatusMeta[resourceStatusOf(account)]?.label ||
                    resourceStatusOf(account)
                  }}
                </Tag>
              </div>

              <dl
                class="mt-4 grid grid-cols-[72px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm"
              >
                <dt class="text-slate-500">渠道 / 主体</dt>
                <dd class="m-0 min-w-0 text-slate-800 dark:text-slate-200">
                  <div class="truncate">{{ channelNameOf(account) }}</div>
                  <div class="mt-1 flex items-center gap-2">
                    <span class="min-w-0 truncate text-xs text-slate-500">
                      {{ legalEntityNameOf(account) }}
                    </span>
                    <Tag
                      class="!m-0 shrink-0"
                      :color="
                        whitelistStatusMeta[whitelistStatusOf(account)]
                          ?.color || 'default'
                      "
                    >
                      {{
                        whitelistStatusMeta[whitelistStatusOf(account)]
                          ?.label || whitelistStatusOf(account)
                      }}
                    </Tag>
                  </div>
                </dd>
                <dt class="text-slate-500">项目</dt>
                <dd class="m-0 truncate text-slate-800 dark:text-slate-200">
                  {{ assignmentProject(account) }}
                </dd>
                <dt class="text-slate-500">团队 / 人</dt>
                <dd class="m-0 truncate text-slate-800 dark:text-slate-200">
                  {{ assignmentTeam(account) }} · {{ assignmentUser(account) }}
                </dd>
                <dt class="text-slate-500">今日消耗</dt>
                <dd class="m-0 font-semibold text-slate-950 dark:text-white">
                  {{ formatMoney(todaySpend(account), currencyOf(account)) }}
                </dd>
                <dt class="text-slate-500">更新时间</dt>
                <dd class="m-0 truncate text-slate-800 dark:text-slate-200">
                  {{
                    formatTime(account, 'updatedAt', 'lastSyncAt', 'createdAt')
                  }}
                </dd>
              </dl>

              <div
                class="mt-4 grid grid-cols-2 gap-2 border-t border-slate-100 pt-3 dark:border-slate-800"
              >
                <Button class="" @click="openDetails(account)">
                  查看详情
                </Button>
                <Button
                  class=""
                  danger
                  :disabled="resourceStatusOf(account) === 'exception'"
                  @click="openException(account)"
                >
                  {{
                    resourceStatusOf(account) === 'exception'
                      ? '已异常'
                      : '标记异常'
                  }}
                </Button>
              </div>
            </Card>

            <div
              v-if="filteredAccounts.length === 0"
              class="col-span-full py-10"
            >
              <Empty
                description="没有符合筛选条件的账户"
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
              />
            </div>
          </div>
        </Card>
      </div>

      <Drawer
        :open="inboundDrawerOpen"
        title="广告账户入库"
        width="min(640px, 100vw)"
        :closable="!inboundSaving"
        :keyboard="!inboundSaving"
        :mask-closable="!inboundSaving"
        @close="closeInboundDrawer"
      >
        <Alert
          class="mb-5"
          message="入库只建立资源主数据，不代表已分配给项目或投手。"
          show-icon
          type="info"
        />
        <Form
          ref="inboundFormRef"
          layout="vertical"
          :model="inboundForm"
          :rules="inboundRules"
        >
          <Row :gutter="16">
            <Col :xs="24" :md="12">
              <FormItem label="投放平台" name="platform" required>
                <Select
                  v-model:value="inboundForm.platform"
                  :options="platformOptions"
                />
              </FormItem>
            </Col>
            <Col :xs="24" :md="12">
              <FormItem label="账户 ID" name="accountId" required>
                <Input
                  v-model:value="inboundForm.accountId"
                  placeholder="平台侧广告账户 ID"
                />
              </FormItem>
            </Col>
          </Row>

          <FormItem label="账户名称" name="name" required>
            <Input
              v-model:value="inboundForm.name"
              :maxlength="80"
              placeholder="便于业务识别的账户名称"
              show-count
            />
          </FormItem>

          <Row :gutter="16">
            <Col :xs="24" :md="12">
              <FormItem label="平台状态" name="platformStatus">
                <Select
                  v-model:value="inboundForm.platformStatus"
                  :options="platformStatusOptions"
                />
              </FormItem>
            </Col>
            <Col :xs="24" :md="12">
              <FormItem label="库存状态" name="resourceStatus">
                <Select
                  v-model:value="inboundForm.resourceStatus"
                  :options="
                    resourceStatusOptions.filter(
                      (item) =>
                        !item.value.includes(',') &&
                        !item.value.startsWith('today_') &&
                        item.value !== 'all',
                    )
                  "
                  size="large"
                />
              </FormItem>
            </Col>
          </Row>

          <Row :gutter="16">
            <Col :xs="24" :md="12">
              <FormItem label="币种" name="currency">
                <Select
                  v-model:value="inboundForm.currency"
                  :options="
                    ['USD', 'EUR', 'GBP', 'JPY', 'CNY'].map((value) => ({
                      label: value,
                      value,
                    }))
                  "
                  show-search
                  size="large"
                />
              </FormItem>
            </Col>
            <Col :xs="24" :md="12">
              <FormItem label="时区" name="timezone">
                <Select
                  v-model:value="inboundForm.timezone"
                  :options="
                    ['UTC-8', 'UTC-5', 'UTC+0', 'UTC+8', 'UTC+9'].map(
                      (value) => ({ label: value, value }),
                    )
                  "
                  show-search
                  size="large"
                />
              </FormItem>
            </Col>
          </Row>

          <Row :gutter="16">
            <Col :xs="24" :md="12">
              <FormItem label="账户余额" name="balance">
                <InputNumber
                  v-model:value="inboundForm.balance"
                  class="!w-full"
                  :min="0"
                  :precision="2"
                />
              </FormItem>
            </Col>
            <Col :xs="24" :md="12">
              <FormItem label="消耗上限" name="spendCap">
                <InputNumber
                  v-model:value="inboundForm.spendCap"
                  class="!w-full"
                  :min="0"
                  :precision="2"
                />
              </FormItem>
            </Col>
          </Row>

          <Row :gutter="16">
            <Col :xs="24" :md="12">
              <FormItem label="资源渠道" name="channelName" required>
                <Input
                  v-model:value="inboundForm.channelName"
                  placeholder="例如 Meta SEA 渠道"
                />
              </FormItem>
            </Col>
            <Col :xs="24" :md="12">
              <FormItem label="授权主体" name="legalEntityName" required>
                <Input
                  v-model:value="inboundForm.legalEntityName"
                  placeholder="账户所属公司或开户主体"
                />
              </FormItem>
            </Col>
          </Row>

          <Row :gutter="16">
            <Col :xs="24" :md="12">
              <FormItem label="BM ID" name="businessManagerId">
                <Input
                  v-model:value="inboundForm.businessManagerId"
                  placeholder="可选"
                />
              </FormItem>
            </Col>
            <Col :xs="24" :md="12">
              <FormItem label="代理线" name="agencyLineName">
                <Input
                  v-model:value="inboundForm.agencyLineName"
                  placeholder="可选"
                />
              </FormItem>
            </Col>
          </Row>

          <FormItem label="加白状态" name="whitelistStatus" required>
            <Select
              v-model:value="inboundForm.whitelistStatus"
              :options="whitelistStatusOptions"
            />
            <div class="mt-1 text-xs leading-5 text-slate-500">
              加白状态属于资源事实，不会随项目分配自动改变。
            </div>
          </FormItem>

          <FormItem label="标签" name="tags">
            <Select
              v-model:value="inboundForm.tags"
              mode="tags"
              placeholder="输入标签后回车"
            />
          </FormItem>
          <FormItem label="备注" name="notes">
            <Input.TextArea
              v-model:value="inboundForm.notes"
              :maxlength="300"
              :rows="4"
              show-count
            />
          </FormItem>
        </Form>

        <template #footer>
          <div class="flex justify-end gap-2">
            <Button
              class=""
              :disabled="inboundSaving"
              @click="closeInboundDrawer"
            >
              取消
            </Button>
            <Button
              class=""
              :loading="inboundSaving"
              type="primary"
              @click="submitInbound"
            >
              确认入库
            </Button>
          </div>
        </template>
      </Drawer>

      <Drawer
        :open="detailDrawerOpen"
        title="账户详情"
        width="min(620px, 100vw)"
        @close="detailDrawerOpen = false"
      >
        <template v-if="selectedAccount">
          <div class="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div
              class="rounded-xl border border-slate-200 p-4 dark:border-slate-800"
            >
              <div class="text-xs text-slate-500">平台状态</div>
              <Tag
                class="!mt-2"
                :color="
                  platformStatusMeta[platformStatusOf(selectedAccount)]
                    ?.color || 'default'
                "
              >
                {{
                  platformStatusMeta[platformStatusOf(selectedAccount)]
                    ?.label || platformStatusOf(selectedAccount)
                }}
              </Tag>
            </div>
            <div
              class="rounded-xl border border-slate-200 p-4 dark:border-slate-800"
            >
              <div class="text-xs text-slate-500">库存状态</div>
              <Tag
                class="!mt-2"
                :color="
                  resourceStatusMeta[resourceStatusOf(selectedAccount)]
                    ?.color || 'default'
                "
              >
                {{
                  resourceStatusMeta[resourceStatusOf(selectedAccount)]
                    ?.label || resourceStatusOf(selectedAccount)
                }}
              </Tag>
            </div>
          </div>

          <Descriptions bordered :column="1">
            <DescriptionsItem label="账户名称">
              {{ accountName(selectedAccount) }}
            </DescriptionsItem>
            <DescriptionsItem label="账户 ID">
              {{ externalAccountId(selectedAccount) }}
            </DescriptionsItem>
            <DescriptionsItem label="投放平台">
              {{
                platformMeta[platformOf(selectedAccount)]?.label ||
                platformOf(selectedAccount)
              }}
            </DescriptionsItem>
            <DescriptionsItem label="资源渠道">
              {{ channelNameOf(selectedAccount) }}
            </DescriptionsItem>
            <DescriptionsItem label="授权主体">
              {{ legalEntityNameOf(selectedAccount) }}
            </DescriptionsItem>
            <DescriptionsItem label="加白状态">
              <Tag
                :color="
                  whitelistStatusMeta[whitelistStatusOf(selectedAccount)]
                    ?.color || 'default'
                "
              >
                {{
                  whitelistStatusMeta[whitelistStatusOf(selectedAccount)]
                    ?.label || whitelistStatusOf(selectedAccount)
                }}
              </Tag>
            </DescriptionsItem>
            <DescriptionsItem label="项目">
              {{ assignmentProject(selectedAccount) }}
            </DescriptionsItem>
            <DescriptionsItem label="团队">
              {{ assignmentTeam(selectedAccount) }}
            </DescriptionsItem>
            <DescriptionsItem label="使用人">
              {{ assignmentUser(selectedAccount) }}
            </DescriptionsItem>
            <DescriptionsItem label="今日消耗">
              {{
                formatMoney(
                  todaySpend(selectedAccount),
                  currencyOf(selectedAccount),
                )
              }}
            </DescriptionsItem>
            <DescriptionsItem label="时区">
              {{ textOf(selectedAccount, 'timezone') || '-' }}
            </DescriptionsItem>
            <DescriptionsItem label="BM / 代理线">
              {{
                textOf(
                  selectedAccount,
                  'businessManagerName',
                  'businessManagerId',
                  'bmId',
                ) || '-'
              }}
              <span class="px-1 text-slate-300">/</span>
              {{
                textOf(
                  selectedAccount,
                  'agencyLineName',
                  'deliveryLineName',
                  'agentLineName',
                ) || '-'
              }}
            </DescriptionsItem>
            <DescriptionsItem label="异常原因">
              {{ textOf(selectedAccount, 'exceptionReason') || '-' }}
            </DescriptionsItem>
            <DescriptionsItem label="备注">
              {{ textOf(selectedAccount, 'notes', 'remark') || '-' }}
            </DescriptionsItem>
            <DescriptionsItem label="更新时间">
              {{
                formatTime(
                  selectedAccount,
                  'updatedAt',
                  'lastSyncAt',
                  'createdAt',
                )
              }}
            </DescriptionsItem>
          </Descriptions>

          <Alert
            v-if="selectedAssignment"
            class="mt-5"
            message="当前账户关系来自资源分配记录；不会反写覆盖账户主数据。"
            show-icon
            type="info"
          />
        </template>

        <template #footer>
          <div class="flex justify-end gap-2">
            <Button class="" @click="detailDrawerOpen = false"> 关闭 </Button>
            <Button
              v-if="selectedAccount"
              class=""
              danger
              :disabled="resourceStatusOf(selectedAccount) === 'exception'"
              @click="openException(selectedAccount)"
            >
              标记异常
            </Button>
          </div>
        </template>
      </Drawer>

      <Modal
        v-model:open="exceptionModalOpen"
        :confirm-loading="markingException"
        ok-text="确认标记"
        title="标记异常账户"
        @ok="confirmException"
      >
        <Alert
          class="mb-4"
          :message="`将 ${exceptionTarget ? accountName(exceptionTarget) : '该账户'} 标记为异常，后续分配应暂停。`"
          show-icon
          type="warning"
        />
        <label
          class="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-200"
          for="exception-reason"
        >
          异常原因
        </label>
        <Input.TextArea
          id="exception-reason"
          v-model:value="exceptionReason"
          :maxlength="200"
          :rows="4"
          placeholder="例如：平台限制投放，等待申诉"
          show-count
        />
      </Modal>

      <Modal
        v-model:open="batchModalOpen"
        :confirm-loading="batchSaving"
        :ok-button-props="{ disabled: validBatchRows.length === 0 }"
        :width="920"
        cancel-text="取消"
        ok-text="确认入库"
        title="批量导入广告账户"
        @ok="submitBatchInbound"
      >
        <Alert
          class="mb-4"
          message="支持 CSV 或制表符文件，导入前会校验必填项、平台和重复账户。"
          show-icon
          type="info"
        >
          <template #action>
            <Button type="link" @click="downloadBatchTemplate">
              下载模板
            </Button>
          </template>
        </Alert>
        <UploadDragger
          accept=".csv,.txt"
          :before-upload="beforeBatchUpload"
          :file-list="[]"
          :multiple="false"
        >
          <p class="ant-upload-drag-icon">
            <IconifyIcon
              icon="lucide:file-spreadsheet"
              class="text-primary mx-auto text-2xl"
            />
          </p>
          <p class="ant-upload-text">点击或拖拽 CSV 文件到此处</p>
          <p class="ant-upload-hint">
            文件只在浏览器内解析，确认后才写入账户库存。
          </p>
        </UploadDragger>
        <Input.TextArea
          v-model:value="batchText"
          class="mt-3 font-mono"
          :rows="5"
          placeholder="也可以直接粘贴模板内容"
        />
        <div v-if="batchRows.length > 0" class="mt-4">
          <div
            class="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm"
          >
            <span class="font-medium text-slate-700">导入预览</span>
            <span class="text-slate-500">
              共 {{ batchRows.length }} 行，可入库
              {{ validBatchRows.length }} 行
            </span>
          </div>
          <div class="hidden min-w-0 md:block">
            <Table
              :columns="batchColumns"
              :data-source="batchRows"
              :pagination="false"
              :row-key="(record) => `${record.line}-${record.accountId}`"
              :scroll="{ y: 260 }"
              size="small"
              table-layout="fixed"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'account'">
                  <div class="min-w-0">
                    <div class="truncate font-medium" :title="record.name">
                      {{ record.name || '-' }}
                    </div>
                    <div
                      class="mt-1 truncate font-mono text-xs text-slate-500"
                      :title="record.accountId"
                    >
                      {{ record.accountId || '-' }}
                    </div>
                  </div>
                </template>
                <template v-else-if="column.key === 'source'">
                  <div class="min-w-0">
                    <div class="truncate">
                      {{
                        platformMeta[record.platform]?.label ||
                        record.platform ||
                        '-'
                      }}
                    </div>
                    <div
                      class="mt-1 truncate text-xs text-slate-500"
                      :title="record.channelName"
                    >
                      {{ record.channelName || '-' }}
                    </div>
                  </div>
                </template>
                <template v-else-if="column.key === 'legalEntityName'">
                  <div class="truncate" :title="record.legalEntityName">
                    {{ record.legalEntityName || '-' }}
                  </div>
                </template>
                <template v-else-if="column.key === 'validation'">
                  <Tag :color="record.valid ? 'success' : 'error'">
                    {{ record.valid ? '校验通过' : record.issue }}
                  </Tag>
                </template>
              </template>
            </Table>
          </div>

          <div class="grid gap-2 md:hidden">
            <div
              v-for="record in batchRows"
              :key="`${record.line}-${record.accountId}`"
              class="min-w-0 rounded-lg border border-slate-200 p-3"
            >
              <div class="flex items-start justify-between gap-2">
                <span class="text-xs text-slate-500">
                  第 {{ record.line }} 行
                </span>
                <Tag
                  class="!m-0 shrink-0"
                  :color="record.valid ? 'success' : 'error'"
                >
                  {{ record.valid ? '校验通过' : record.issue }}
                </Tag>
              </div>
              <div class="mt-2 min-w-0">
                <div class="truncate font-medium" :title="record.name">
                  {{ record.name || '-' }}
                </div>
                <div
                  class="mt-1 truncate font-mono text-xs text-slate-500"
                  :title="record.accountId"
                >
                  {{ record.accountId || '-' }}
                </div>
              </div>
              <dl
                class="mt-3 grid grid-cols-[64px_minmax(0,1fr)] gap-x-2 gap-y-1.5 text-xs"
              >
                <dt class="text-slate-500">平台</dt>
                <dd class="m-0 truncate">
                  {{
                    platformMeta[record.platform]?.label ||
                    record.platform ||
                    '-'
                  }}
                </dd>
                <dt class="text-slate-500">资源渠道</dt>
                <dd class="m-0 truncate">{{ record.channelName || '-' }}</dd>
                <dt class="text-slate-500">授权主体</dt>
                <dd class="m-0 truncate">
                  {{ record.legalEntityName || '-' }}
                </dd>
              </dl>
            </div>
          </div>
        </div>
      </Modal>
    </template>
  </MediaResourcePage>
</template>
