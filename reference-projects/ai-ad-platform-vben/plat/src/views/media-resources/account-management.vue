<script setup lang="ts">
import type { TableColumnsType } from 'ant-design-vue';

import {
  computed,
  onMounted,
  reactive,
  ref,
  shallowRef,
  toRef,
  toRefs,
} from 'vue';
import { useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import { useStorage } from '@vueuse/core';
import {
  Button,
  Card,
  Checkbox,
  DatePicker,
  Drawer,
  Dropdown,
  Empty,
  Form,
  FormItem,
  Input,
  Menu,
  MenuItem,
  message,
  Modal,
  Select,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  bindManagedAccountPitchers,
  classifyManagedAccounts,
  getManagedAccountChannels,
  getManagedAccountList,
  getManagedAccountPitchers,
  getManagedAccountStatusCounts,
  getManagedAccountSummary,
  getManagedAccountTypes,
  recycleManagedAccounts,
  renameManagedAccounts,
  updateManagedAccount,
} from '#/api';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

type AccountStatusKey =
  | 'active'
  | 'closed'
  | 'disabled'
  | 'idle'
  | 'payment_exception'
  | 'recycled'
  | 'review'
  | 'unbound'
  | 'unknown';

interface ManagedAccountRecord {
  [key: string]: unknown;
  accountId?: number | string;
  accountName?: string;
  accountStatus?: number | string;
  accountType?: string;
  actualDeduction?: number | string;
  adminCount?: number;
  amountSpent?: number | string;
  authTime?: string;
  balance?: number | string;
  banTime?: string;
  bmFromFeishu?: string;
  bmId?: string;
  businessName?: string;
  channelCode?: string;
  channelId?: number | string;
  channelName?: string;
  classifyStatus?: number | string;
  createTime?: string;
  disableReason?: string;
  displayString?: string;
  fbName?: string;
  fbTokenStatus?: number | string;
  fundingSourceType?: number | string;
  isPrepayAccount?: number | string;
  isRecycled?: number | string;
  operatorDeptName?: string;
  operatorId?: number | string;
  operatorName?: string;
  remainingSpendCap?: number | string;
  remark?: string;
  spendLimit?: number | string;
  stopStatus?: number | string;
  stopTime?: string;
  timezoneName?: string;
  timezoneOffsetHoursUtc?: number | string;
  totalSpend?: number | string;
  unbindTime?: string;
}

interface AccountSummary {
  [key: string]: unknown;
  actualDeduction?: number | string;
  amountSpent?: number | string;
  balance?: number | string;
  remainingSpendCap?: number | string;
  totalSpend?: number | string;
}

interface SelectOption {
  extra?: string;
  label: string;
  value: string;
}

type AccountColumnKey =
  | 'accountId'
  | 'accountName'
  | 'accountStatus'
  | 'actions'
  | 'actualDeduction'
  | 'amountSpent'
  | 'balance'
  | 'bm'
  | 'businessName'
  | 'channelName'
  | 'classifyStatus'
  | 'operatorName'
  | 'remainingSpendCap'
  | 'remark'
  | 'timezone'
  | 'totalSpend';

const statusMeta: Record<AccountStatusKey, { color: string; label: string }> = {
  active: { color: 'success', label: '活跃' },
  closed: { color: 'error', label: '封户' },
  disabled: { color: 'default', label: '停用' },
  idle: { color: 'blue', label: '闲置' },
  payment_exception: { color: 'warning', label: '支付异常' },
  recycled: { color: 'cyan', label: '回收' },
  review: { color: 'warning', label: '风险审查' },
  unbound: { color: 'purple', label: '掉绑' },
  unknown: { color: 'default', label: '未知' },
};

const statusTabDefinitions = [
  { countKey: 'total', label: '全部', value: 'all' },
  { countKey: 'active', label: '活跃', value: '1' },
  { countKey: 'suspended', label: '封户', value: '2' },
  { countKey: 'idle', label: '闲置', value: '99' },
  { countKey: 'paymentException', label: '支付异常', value: '3' },
  { countKey: 'stopped', label: '停用', value: '1001' },
  { countKey: 'offline', label: '掉绑', value: '97' },
  { countKey: 'recycled', label: '回收', value: 'recycled' },
] as const;

const accountColumnDefinitions: TableColumnsType<ManagedAccountRecord> = [
  { fixed: 'left', key: 'channelName', title: '渠道名称', width: 150 },
  {
    dataIndex: 'operatorName',
    key: 'operatorName',
    title: '投放师',
    width: 180,
  },
  {
    dataIndex: 'accountId',
    key: 'accountId',
    title: '广告账户 ID',
    width: 190,
  },
  {
    dataIndex: 'accountName',
    key: 'accountName',
    title: '广告账户名称',
    width: 240,
  },
  { align: 'right', key: 'balance', title: '账户余额', width: 130 },
  { align: 'right', key: 'amountSpent', title: '总花费', width: 130 },
  {
    align: 'right',
    key: 'remainingSpendCap',
    title: '剩余应付',
    width: 130,
  },
  { align: 'right', key: 'totalSpend', title: '花费金额', width: 130 },
  { align: 'right', key: 'actualDeduction', title: '卡扣金额', width: 130 },
  { key: 'timezone', title: '时区', width: 180 },
  {
    dataIndex: 'businessName',
    key: 'businessName',
    title: '所属主体',
    width: 220,
  },
  { key: 'bm', title: 'BM', width: 180 },
  { key: 'classifyStatus', title: '归类状态', width: 110 },
  { key: 'accountStatus', title: '账户状态', width: 110 },
  { dataIndex: 'remark', key: 'remark', title: '备注', width: 200 },
  { fixed: 'right', key: 'actions', title: '操作', width: 180 },
];

const defaultVisibleColumnKeys = accountColumnDefinitions.map((column) =>
  String(column.key),
) as AccountColumnKey[];
const fixedColumnKeys = new Set<AccountColumnKey>([
  'accountId',
  'accountName',
  'actions',
  'channelName',
]);

const router = useRouter();
const accounts = shallowRef<ManagedAccountRecord[]>([]);
const summary = ref<AccountSummary>({});
const statusCounts = ref<Record<string, number>>({});
const loading = ref(false);
const actionLoading = ref(false);
const exporting = ref(false);
const advancedFiltersOpen = ref(false);
const activeStatusTab = ref('all');
const selectedAccountIds = ref<string[]>([]);
const detailOpen = ref(false);
const selectedAccount = ref<ManagedAccountRecord>();
const categorizationModalOpen = ref(false);
const renameModalOpen = ref(false);
const renameUsesAccountValues = ref(false);
const bindingModalOpen = ref(false);
const columnDrawerOpen = ref(false);
const requestSequence = ref(0);
const paginationState = reactive({ current: 1, pageSize: 10, total: 0 });

const channelOptions = ref<SelectOption[]>([]);
const channelCodeById = ref<Record<string, string>>({});
const accountTypeOptions = ref<SelectOption[]>([]);
const pitcherOptions = ref<SelectOption[]>([]);

function createFilterState() {
  return {
    accountIds: '',
    authStatus: undefined as string | undefined,
    bmId: '',
    businessName: '',
    channelId: undefined as string | undefined,
    classifyStatus: undefined as number | undefined,
    deptId: undefined as string | undefined,
    displayString: '',
    fundingSourceType: undefined as string | undefined,
    operatorId: undefined as string | undefined,
    spendDateRange: undefined as [string, string] | undefined,
    timezoneOffsetHoursUtc: undefined as string | undefined,
  };
}

const filterForm = reactive(createFilterState());
const routeState = createListRouteStateTarget({
  ...toRefs(filterForm),
  status_tab: activeStatusTab,
});
const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    onRouteStateRestored: () => loadAccountList(),
    pagination: {
      defaultPageSize: 10,
      page: toRef(paginationState, 'current'),
      pageSize: toRef(paginationState, 'pageSize'),
      pageSizes: [10, 20, 50, 100],
    },
    state: routeState,
  });
const categorizationForm = reactive({
  accountType: undefined as string | undefined,
  channelId: undefined as string | undefined,
});
const renameForm = reactive({
  accountType: undefined as string | undefined,
  channelCode: undefined as string | undefined,
  customSuffix: '',
  deliverName: undefined as string | undefined,
});
const bindingForm = reactive({
  accountType: undefined as string | undefined,
  channelId: undefined as string | undefined,
  operatorId: undefined as string | undefined,
});

const visibleColumnKeys = useStorage<AccountColumnKey[]>(
  'fusion:managed-ad-accounts:visible-columns:v3',
  defaultVisibleColumnKeys,
);
const accountColumnOptions = accountColumnDefinitions.map((column) => ({
  disabled: fixedColumnKeys.has(String(column.key) as AccountColumnKey),
  label: String(column.title),
  value: String(column.key),
}));
const accountColumns = computed(() =>
  accountColumnDefinitions.filter((column) =>
    visibleColumnKeys.value.includes(String(column.key) as AccountColumnKey),
  ),
);
const accountTableScrollX = computed(() =>
  Math.max(
    1200,
    accountColumns.value.reduce(
      (width, column) => width + Number(column.width ?? 120),
      64,
    ),
  ),
);
const accountTableStyle = computed(() => ({
  '--account-table-min-width': `${accountTableScrollX.value}px`,
}));
const selectedAccounts = computed(() => {
  const selectedIds = new Set(selectedAccountIds.value);
  return accounts.value.filter((account) =>
    selectedIds.has(String(account.accountId)),
  );
});
const selectedAccountSummary = computed(() =>
  selectedAccounts.value
    .map((account) => account.accountName || String(account.accountId))
    .join('、'),
);
const rowSelection = computed(() => ({
  onChange: (keys: unknown[]) => {
    selectedAccountIds.value = keys.map(String);
  },
  selectedRowKeys: selectedAccountIds.value,
}));
const pagination = computed(() => ({
  current: paginationState.current,
  pageSize: paginationState.pageSize,
  pageSizeOptions: ['10', '20', '50', '100'],
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
  total: paginationState.total,
}));
const statusTabs = computed(() =>
  statusTabDefinitions.map((tab) => ({
    ...tab,
    count: statusCounts.value[tab.countKey] ?? 0,
  })),
);

function compactQuery(query: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(query).filter(
      ([, value]) => value !== '' && value !== null && value !== undefined,
    ),
  );
}

/**
 * 将页面筛选条件转换为 MPower 原账户管理接口参数。
 *
 * @remarks
 * MPower 使用 1001 表示“停用”筛选，但实际接口字段是 stopStatus；回收账户则
 * 独立使用 isRecycled，不能作为普通 accountStatus 下发。
 */
function buildListQuery(options?: { pageNum?: number; pageSize?: number }) {
  const [startDate, endDate] = filterForm.spendDateRange ?? [];
  const query: Record<string, unknown> = {
    ...filterForm,
    accountIds: filterForm.accountIds
      .split(/[\n,，]+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .join(','),
    endDate,
    isRecycled: activeStatusTab.value === 'recycled' ? 1 : 0,
    pageNum: options?.pageNum ?? paginationState.current,
    pageSize: options?.pageSize ?? paginationState.pageSize,
    spendDateRange: undefined,
    startDate,
  };

  if (activeStatusTab.value === '1001') {
    query.stopStatus = 1;
  } else if (!['all', 'recycled'].includes(activeStatusTab.value)) {
    query.accountStatus = Number(activeStatusTab.value);
  }
  return compactQuery(query);
}

async function loadAccountList() {
  await commitQueryState();
  const sequence = ++requestSequence.value;
  const query = buildListQuery();
  const {
    accountStatus: _accountStatus,
    pageNum: _pageNum,
    pageSize: _pageSize,
    stopStatus: _stopStatus,
    ...countQuery
  } = query;
  loading.value = true;

  try {
    const [listResponse, summaryResponse, statusResponse] = await Promise.all([
      getManagedAccountList<ManagedAccountRecord>(query),
      getManagedAccountSummary<AccountSummary>(query).catch(() => undefined),
      getManagedAccountStatusCounts(countQuery).catch(() => undefined),
    ]);
    if (sequence !== requestSequence.value) return;

    accounts.value = listResponse.data.records ?? [];
    paginationState.total =
      listResponse.data.count ?? listResponse.data.total ?? 0;
    summary.value = summaryResponse?.data ?? {};
    statusCounts.value = Object.fromEntries(
      (statusResponse?.data ?? []).map((item) => [item.name, item.count]),
    );
    if (!statusCounts.value.total) {
      statusCounts.value.total = paginationState.total;
    }
    selectedAccountIds.value = [];
  } finally {
    if (sequence === requestSequence.value) loading.value = false;
  }
}

async function loadAccountOptions() {
  const [channelsResult, typesResult, pitchersResult] =
    await Promise.allSettled([
      getManagedAccountChannels(),
      getManagedAccountTypes(),
      getManagedAccountPitchers({ pageNum: 1, pageSize: 100_000 }),
    ]);

  if (channelsResult.status === 'fulfilled') {
    channelOptions.value = channelsResult.value.data.map((channel) => ({
      extra: channel.channelCode,
      label: channel.channelName,
      value: String(channel.id),
    }));
    channelCodeById.value = Object.fromEntries(
      channelsResult.value.data.map((channel) => [
        String(channel.id),
        channel.channelCode,
      ]),
    );
  }
  if (typesResult.status === 'fulfilled') {
    accountTypeOptions.value = typesResult.value.data.map((accountType) => ({
      label: accountType.accountType,
      value: accountType.accountType,
    }));
  }
  if (pitchersResult.status === 'fulfilled') {
    pitcherOptions.value = pitchersResult.value.data.records.map((pitcher) => ({
      extra: pitcher.nickName,
      label: pitcher.nickName,
      value: String(pitcher.userId),
    }));
  }
}

function handleSearch() {
  paginationState.current = 1;
  void loadAccountList();
}

async function handleReset() {
  await resetQueryState();
  await loadAccountList();
}

function handleStatusTabChange() {
  paginationState.current = 1;
  void loadAccountList();
}

function handleTableChange(page: { current?: number; pageSize?: number }) {
  const pageSize = page.pageSize ?? paginationState.pageSize;
  paginationState.current =
    pageSize === paginationState.pageSize ? (page.current ?? 1) : 1;
  paginationState.pageSize = pageSize;
  void loadAccountList();
}

function getSelectedAccountsOrWarn() {
  if (selectedAccounts.value.length > 0) return selectedAccounts.value;
  message.warning('请先勾选需要操作的账户');
}

function showDetail(account: ManagedAccountRecord) {
  selectedAccount.value = account;
  detailOpen.value = true;
}

function openCategorization() {
  const selected = getSelectedAccountsOrWarn();
  if (!selected) return;
  categorizationForm.channelId = undefined;
  categorizationForm.accountType = undefined;
  categorizationModalOpen.value = true;
}

async function saveCategorization() {
  const selected = getSelectedAccountsOrWarn();
  if (
    !selected ||
    !categorizationForm.channelId ||
    !categorizationForm.accountType
  ) {
    message.warning('请选择渠道和账户类型');
    return;
  }
  actionLoading.value = true;
  try {
    await classifyManagedAccounts(
      selected.map((account) => ({
        accountId: String(account.accountId),
        accountType: categorizationForm.accountType,
        channelId: Number(categorizationForm.channelId),
      })),
    );
    categorizationModalOpen.value = false;
    message.success(`已归类 ${selected.length} 个账户`);
    await loadAccountList();
  } finally {
    actionLoading.value = false;
  }
}

function openRename() {
  const selected = getSelectedAccountsOrWarn();
  if (!selected) return;
  const allClassified = selected.every(
    (account) => Number(account.classifyStatus) === 1,
  );
  const allUnclassified = selected.every(
    (account) => Number(account.classifyStatus) !== 1,
  );
  if (!allClassified && !allUnclassified) {
    message.warning('已归类与未归类账户不能混合修改名称');
    return;
  }
  Object.assign(renameForm, {
    accountType: undefined,
    channelCode: undefined,
    customSuffix: '',
    deliverName: undefined,
  });
  renameUsesAccountValues.value = allClassified;
  renameModalOpen.value = true;
}

function generateAccountName(account: ManagedAccountRecord, index: number) {
  const now = new Date();
  const date = `${String(now.getFullYear()).slice(-2)}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const channelCode =
    account.channelCode ||
    channelCodeById.value[String(account.channelId ?? '')] ||
    renameForm.channelCode;
  const accountType = account.accountType || renameForm.accountType;
  const suffix = renameForm.customSuffix
    ? `-${renameForm.customSuffix.trim()}`
    : '';
  return `${channelCode}-${accountType}-${renameForm.deliverName}${suffix}-${date}-${String(index + 1).padStart(2, '0')}`;
}

async function saveRename() {
  const selected = getSelectedAccountsOrWarn();
  if (
    !selected ||
    (!renameUsesAccountValues.value &&
      (!renameForm.channelCode || !renameForm.accountType)) ||
    !renameForm.deliverName
  ) {
    message.warning('请选择渠道、账户类型和投手');
    return;
  }
  if (renameForm.customSuffix.trim().length > 10) {
    message.warning('自定义后缀不能超过 10 个字符');
    return;
  }
  actionLoading.value = true;
  try {
    await renameManagedAccounts(
      selected.map((account, index) => ({
        accountId: String(account.accountId),
        accountName: generateAccountName(account, index),
      })),
    );
    renameModalOpen.value = false;
    message.success('修改账户名指令已提交');
    await loadAccountList();
  } finally {
    actionLoading.value = false;
  }
}

function openBinding() {
  const selected = getSelectedAccountsOrWarn();
  if (!selected) return;
  Object.assign(bindingForm, {
    accountType: selected[0]?.accountType,
    channelId: selected[0]?.channelId
      ? String(selected[0].channelId)
      : undefined,
    operatorId: undefined,
  });
  bindingModalOpen.value = true;
}

async function saveBinding() {
  const selected = getSelectedAccountsOrWarn();
  if (
    !selected ||
    !bindingForm.channelId ||
    !bindingForm.operatorId ||
    !bindingForm.accountType
  ) {
    message.warning('请选择渠道、投手和账户类型');
    return;
  }
  actionLoading.value = true;
  try {
    await bindManagedAccountPitchers({
      accountList: selected.map((account) => ({
        accountId: String(account.accountId),
        accountType: bindingForm.accountType,
        operatorId: bindingForm.operatorId,
      })),
      channelId: bindingForm.channelId,
    });
    bindingModalOpen.value = false;
    message.success(`已关联 ${selected.length} 个账户`);
    await loadAccountList();
  } finally {
    actionLoading.value = false;
  }
}

function handleStop(account: ManagedAccountRecord) {
  Modal.confirm({
    content: `停用后账户将不能继续用于投放，确定停用“${account.accountName || account.accountId}”吗？`,
    okButtonProps: { danger: true },
    okText: '确认停用',
    title: '停用账户',
    async onOk() {
      await updateManagedAccount({
        accountId: String(account.accountId),
        stopStatus: 1,
      });
      message.success('账户已停用');
      await loadAccountList();
    },
  });
}

function handleRecycle(account: ManagedAccountRecord, isRecycled = 1) {
  const actionText = isRecycled ? '回收' : '恢复';
  Modal.confirm({
    content: `${actionText}会改变账户的可用范围，确定${actionText}“${account.accountName || account.accountId}”吗？`,
    okButtonProps: { danger: Boolean(isRecycled) },
    okText: `确认${actionText}`,
    title: `${actionText}账户`,
    async onOk() {
      await recycleManagedAccounts({
        accountIds: [String(account.accountId)],
        isRecycled,
      });
      message.success(`${actionText}成功`);
      await loadAccountList();
    },
  });
}

function handleRefresh() {
  Modal.confirm({
    content: '账户数据由当前系统统一维护，确认后重新加载最新列表数据。',
    okText: '确认刷新',
    title: '刷新账户',
    async onOk() {
      await loadAccountList();
      message.success('账户列表已刷新');
    },
  });
}

function csvCell(value: unknown) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`;
}

/** 部门由投放师的组织归属自动带入，台账中仅随使用人一并展示。 */
function formatOperatorWithDepartment(account: ManagedAccountRecord) {
  return [account.operatorName, account.operatorDeptName]
    .filter(
      (value): value is string | number =>
        value !== undefined && value !== null && String(value).trim() !== '',
    )
    .join(' · ');
}

async function exportAccounts() {
  exporting.value = true;
  try {
    const response = await getManagedAccountList<ManagedAccountRecord>(
      buildListQuery({ pageNum: 1, pageSize: 9_999_999 }),
    );
    const records = response.data.records ?? [];
    if (records.length === 0) {
      message.warning('暂无数据可导出');
      return;
    }
    const rows = records.map((account) => [
      formatOperatorWithDepartment(account),
      account.channelName,
      account.accountId,
      account.accountName,
      formatMoney(account.balance, true),
      formatMoney(account.amountSpent, true),
      formatMoney(account.remainingSpendCap, true),
      formatMoney(account.totalSpend),
      formatMoney(account.actualDeduction, true),
      formatTimezone(account),
      account.businessName,
      account.bmId,
      account.bmFromFeishu,
      statusMeta[getAccountStatus(account)].label,
      Number(account.classifyStatus) === 1 ? '已归类' : '未归类',
      account.remark,
    ]);
    const headers = [
      '投放师',
      '渠道名称',
      '广告账户 ID',
      '广告账户名称',
      '账户余额',
      '总花费',
      '剩余应付',
      '花费金额',
      '卡扣金额',
      '时区',
      '所属主体',
      'BM',
      '管理 BM',
      '账户状态',
      '归类状态',
      '备注',
    ];
    const content = [headers, ...rows]
      .map((row) => row.map((value) => csvCell(value)).join(','))
      .join('\n');
    const url = URL.createObjectURL(
      new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' }),
    );
    const link = document.createElement('a');
    link.download = `MPower账户管理-${new Date().toISOString().slice(0, 10)}.csv`;
    link.href = url;
    link.click();
    URL.revokeObjectURL(url);
    message.success(`已导出 ${records.length} 个账户`);
  } finally {
    exporting.value = false;
  }
}

function handleMoreAction(event: { key: number | string }) {
  switch (String(event.key)) {
    case 'categorize': {
      openCategorization();
      return;
    }
    case 'rename': {
      openRename();
      return;
    }
    case 'sync': {
      handleRefresh();
      return;
    }
    case 'feishu-sync': {
      void router.push('/media-resources/account-management/feishu-sync');
    }
  }
}

function resetColumnPreferences() {
  visibleColumnKeys.value = [...defaultVisibleColumnKeys];
  message.success('已恢复默认列表字段');
}

function numberValue(value: unknown) {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : 0;
}

/** MPower 的余额、扣款等字段以美分返回，totalSpend 则直接以美元返回。 */
function formatMoney(value: unknown, isCentAmount = false) {
  const amount = numberValue(value) / (isCentAmount ? 100 : 1);
  return `$${amount.toLocaleString('en-US', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })}`;
}

function formatTimezone(account: ManagedAccountRecord) {
  const name = account.timezoneName || '—';
  const offset = numberValue(account.timezoneOffsetHoursUtc);
  if (!account.timezoneOffsetHoursUtc) return name;
  return `${name} · UTC${offset >= 0 ? '+' : ''}${offset}`;
}

function getAccountStatus(account: ManagedAccountRecord): AccountStatusKey {
  if (Number(account.isRecycled) === 1) return 'recycled';
  if (Number(account.stopStatus) === 1) return 'disabled';
  const status = Number(account.accountStatus);
  if ([1, 201].includes(status)) return 'active';
  if ([2, 101, 202].includes(status)) return 'closed';
  if (status === 3) return 'payment_exception';
  if ([7, 8, 9, 100].includes(status)) return 'review';
  if (status === 97) return 'unbound';
  if (status === 99) return 'idle';
  return 'unknown';
}

onMounted(async () => {
  await restoreFromRoute();
  await Promise.all([loadAccountList(), loadAccountOptions()]);
});
</script>

<template>
  <div
    class="adpulse-section-page account-management-page mx-auto flex min-w-0 max-w-[1680px] flex-col"
  >
    <section
      class="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"
    >
      <div>
        <h1 class="m-0 font-semibold">账户管理</h1>
        <p class="mb-0 mt-2 text-sm text-slate-500">
          当前系统统一管理账户状态、归类、命名和投手关系。
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button type="primary" @click="handleRefresh">
          <IconifyIcon aria-hidden="true" icon="lucide:refresh-cw" />刷新账户
        </Button>
      </div>
    </section>

    <section class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Card>
        <div class="text-sm text-slate-500">账户总数</div>
        <strong class="account-statistic-value mt-1 block">{{
          statusCounts.total ?? paginationState.total
        }}</strong>
      </Card>
      <Card>
        <div class="text-sm text-slate-500">活跃账户</div>
        <strong class="account-statistic-value mt-1 block text-emerald-600">{{
          statusCounts.active ?? 0
        }}</strong>
      </Card>
      <Card>
        <div class="text-sm text-slate-500">封户账户</div>
        <strong class="account-statistic-value mt-1 block text-red-600">{{
          statusCounts.suspended ?? 0
        }}</strong>
      </Card>
      <Card>
        <div class="text-sm text-slate-500">当前筛选余额</div>
        <strong class="account-statistic-value mt-1 block">{{
          formatMoney(summary.balance, true)
        }}</strong>
      </Card>
    </section>

    <Card :body-style="{ padding: '16px' }">
      <form @submit.prevent="handleSearch">
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <FormItem class="mb-0" label="投放师">
            <Select
              v-model:value="filterForm.operatorId"
              allow-clear
              :options="pitcherOptions"
              placeholder="请选择投放师"
              show-search
            />
          </FormItem>
          <FormItem class="mb-0" label="账户">
            <Input.TextArea
              v-model:value="filterForm.accountIds"
              :auto-size="{ maxRows: 3, minRows: 1 }"
              allow-clear
              placeholder="换行分隔 ID 或名称"
            />
          </FormItem>
          <FormItem class="mb-0" label="花费时间">
            <DatePicker.RangePicker
              v-model:value="filterForm.spendDateRange"
              class="w-full"
              value-format="YYYY-MM-DD"
            />
          </FormItem>
          <FormItem class="mb-0" label="BM">
            <Input
              v-model:value="filterForm.bmId"
              allow-clear
              placeholder="请输入 BM ID"
            />
          </FormItem>
        </div>

        <div
          v-if="advancedFiltersOpen"
          class="mt-3 grid grid-cols-1 gap-3 border-t border-slate-100 pt-3 sm:grid-cols-2 xl:grid-cols-4"
        >
          <FormItem class="mb-0" label="授权状态">
            <Select
              v-model:value="filterForm.authStatus"
              allow-clear
              :options="[
                { label: '已授权', value: '1' },
                { label: '未授权', value: '0' },
              ]"
              placeholder="请选择"
            />
          </FormItem>
          <FormItem class="mb-0" label="是否归类">
            <Select
              v-model:value="filterForm.classifyStatus"
              allow-clear
              :options="[
                { label: '已归类', value: 1 },
                { label: '未归类', value: 0 },
              ]"
              placeholder="请选择"
            />
          </FormItem>
          <FormItem class="mb-0" label="所属主体">
            <Input
              v-model:value="filterForm.businessName"
              allow-clear
              placeholder="请输入所属主体"
            />
          </FormItem>
          <FormItem class="mb-0" label="渠道">
            <Select
              v-model:value="filterForm.channelId"
              allow-clear
              :options="channelOptions"
              placeholder="请选择渠道"
              show-search
            />
          </FormItem>
          <FormItem class="mb-0" label="付费详情">
            <Select
              v-model:value="filterForm.fundingSourceType"
              allow-clear
              :options="[
                { label: '信用卡', value: '1' },
                { label: '授信', value: '2' },
                { label: '预付', value: '3' },
              ]"
              placeholder="请选择"
            />
          </FormItem>
          <FormItem class="mb-0" label="卡号后四位">
            <Input
              v-model:value="filterForm.displayString"
              allow-clear
              :maxlength="4"
              placeholder="请输入卡号后四位"
            />
          </FormItem>
          <FormItem class="mb-0" label="时区">
            <Select
              v-model:value="filterForm.timezoneOffsetHoursUtc"
              allow-clear
              :options="
                Array.from({ length: 25 }, (_, index) => ({
                  label: `UTC${index - 12 >= 0 ? '+' : ''}${index - 12}`,
                  value: String(index - 12),
                }))
              "
              placeholder="请选择时区"
              show-search
            />
          </FormItem>
        </div>

        <div class="mt-3 flex flex-wrap justify-end gap-2">
          <Button html-type="submit" type="primary">
            <IconifyIcon aria-hidden="true" icon="lucide:search" />搜索
          </Button>
          <Button @click="handleReset">
            <IconifyIcon aria-hidden="true" icon="lucide:rotate-ccw" />重置
          </Button>
          <Button
            type="link"
            @click="advancedFiltersOpen = !advancedFiltersOpen"
          >
            {{ advancedFiltersOpen ? '收起' : '展开' }}
            <IconifyIcon
              aria-hidden="true"
              :icon="
                advancedFiltersOpen
                  ? 'lucide:chevron-up'
                  : 'lucide:chevron-down'
              "
            />
          </Button>
        </div>
      </form>
    </Card>

    <Card :body-style="{ padding: 0 }">
      <div
        class="flex flex-col gap-3 border-b border-slate-100 px-4 py-3 lg:flex-row lg:items-center lg:justify-between"
      >
        <Tabs
          v-model:active-key="activeStatusTab"
          class="account-status-tabs"
          @change="handleStatusTabChange"
        >
          <Tabs.TabPane
            v-for="tab in statusTabs"
            :key="tab.value"
            :tab="`${tab.label} (${tab.count})`"
          />
        </Tabs>
        <div class="flex flex-wrap items-center gap-2">
          <span
            v-if="selectedAccounts.length > 0"
            class="mr-1 text-sm text-slate-500"
          >
            已选 {{ selectedAccounts.length }} 个
          </span>
          <Button class="" @click="openBinding">账户关联投手</Button>
          <Button :loading="exporting" class="" @click="exportAccounts">
            <IconifyIcon aria-hidden="true" icon="lucide:download" />导出
          </Button>
          <Dropdown>
            <Button class="" type="primary">
              更多
              <IconifyIcon aria-hidden="true" icon="lucide:chevron-down" />
            </Button>
            <template #overlay>
              <Menu @click="handleMoreAction">
                <MenuItem key="categorize">归类账户</MenuItem>
                <MenuItem key="rename">修改账户名</MenuItem>
                <MenuItem key="sync">刷新账户</MenuItem>
                <MenuItem key="feishu-sync">飞书同步</MenuItem>
              </Menu>
            </template>
          </Dropdown>
          <Tooltip title="配置列表列">
            <Button
              aria-label="配置列表列"
              class="min-w-9"
              @click="columnDrawerOpen = true"
            >
              <IconifyIcon aria-hidden="true" icon="lucide:columns-3" />
            </Button>
          </Tooltip>
          <Tooltip title="刷新账户列表">
            <Button
              aria-label="刷新账户列表"
              class="min-w-9"
              :loading="loading"
              @click="loadAccountList"
            >
              <IconifyIcon aria-hidden="true" icon="lucide:refresh-cw" />
            </Button>
          </Tooltip>
        </div>
      </div>

      <Table
        class="account-management-table"
        :columns="accountColumns"
        :data-source="accounts"
        :loading="loading"
        :pagination="pagination"
        :row-selection="rowSelection"
        :scroll="{ x: accountTableScrollX }"
        :style="accountTableStyle"
        row-key="accountId"
        table-layout="fixed"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'channelName'">
            <span class="block truncate" :title="record.channelName">{{
              record.channelName || '—'
            }}</span>
          </template>
          <template v-else-if="column.key === 'accountName'">
            <strong class="block truncate" :title="record.accountName">{{
              record.accountName || '未命名账户'
            }}</strong>
          </template>
          <template v-else-if="column.key === 'operatorName'">
            <span
              class="block truncate"
              :title="formatOperatorWithDepartment(record)"
            >
              {{ formatOperatorWithDepartment(record) || '—' }}
            </span>
          </template>
          <template v-else-if="column.key === 'accountId'">
            <span class="font-mono text-xs">{{ record.accountId }}</span>
          </template>
          <template v-else-if="column.key === 'balance'">
            {{ formatMoney(record.balance, true) }}
          </template>
          <template v-else-if="column.key === 'amountSpent'">
            {{ formatMoney(record.amountSpent, true) }}
          </template>
          <template v-else-if="column.key === 'remainingSpendCap'">
            {{ formatMoney(record.remainingSpendCap, true) }}
          </template>
          <template v-else-if="column.key === 'totalSpend'">
            {{ formatMoney(record.totalSpend) }}
          </template>
          <template v-else-if="column.key === 'actualDeduction'">
            {{ formatMoney(record.actualDeduction, true) }}
          </template>
          <template v-else-if="column.key === 'timezone'">
            {{ formatTimezone(record) }}
          </template>
          <template v-else-if="column.key === 'bm'">
            <div class="min-w-0">
              <div class="truncate" :title="record.bmFromFeishu">
                {{ record.bmFromFeishu || '—' }}
              </div>
              <div class="mt-1 font-mono text-xs text-slate-500">
                {{ record.bmId || '—' }}
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'classifyStatus'">
            <Tag
              :color="
                Number(record.classifyStatus) === 1 ? 'success' : 'default'
              "
            >
              {{ Number(record.classifyStatus) === 1 ? '已归类' : '未归类' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'accountStatus'">
            <Tag :color="statusMeta[getAccountStatus(record)].color">
              {{ statusMeta[getAccountStatus(record)].label }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'remark'">
            <span class="block truncate" :title="record.remark">{{
              record.remark || '—'
            }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <div class="flex items-center gap-1 whitespace-nowrap">
              <Button type="link" @click="showDetail(record)"> 详情 </Button>
              <Button
                v-if="Number(record.isRecycled) !== 1"
                danger
                type="link"
                @click="handleStop(record)"
              >
                停用
              </Button>
              <Button
                type="link"
                :danger="Number(record.isRecycled) !== 1"
                @click="
                  handleRecycle(record, Number(record.isRecycled) === 1 ? 0 : 1)
                "
              >
                {{ Number(record.isRecycled) === 1 ? '恢复' : '回收' }}
              </Button>
            </div>
          </template>
        </template>
        <template #emptyText>
          <Empty description="暂无符合条件的账户" />
        </template>
      </Table>
    </Card>

    <Modal
      v-model:open="categorizationModalOpen"
      :confirm-loading="actionLoading"
      title="归类账户"
      :width="620"
      @ok="saveCategorization"
    >
      <Form class="pt-4" layout="vertical">
        <FormItem label="已选账户">
          <div
            class="max-h-24 overflow-y-auto rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600"
          >
            {{ selectedAccountSummary }}
          </div>
        </FormItem>
        <FormItem v-if="!renameUsesAccountValues" label="渠道" required>
          <Select
            v-model:value="categorizationForm.channelId"
            :options="
              channelOptions.map((option) => ({
                label: option.label,
                value: option.value,
              }))
            "
            placeholder="请选择渠道"
            show-search
          />
        </FormItem>
        <FormItem v-if="!renameUsesAccountValues" label="账户类型" required>
          <Select
            v-model:value="categorizationForm.accountType"
            :options="
              accountTypeOptions.map((option) => ({
                label: option.label,
                value: option.value,
              }))
            "
            placeholder="请选择账户类型"
            show-search
          />
        </FormItem>
      </Form>
    </Modal>

    <Modal
      v-model:open="renameModalOpen"
      :confirm-loading="actionLoading"
      title="修改账户名称"
      :width="620"
      @ok="saveRename"
    >
      <Form class="pt-4" layout="vertical">
        <FormItem label="渠道" required>
          <Select
            v-model:value="renameForm.channelCode"
            :options="
              channelOptions.map((option) => ({
                label: option.label,
                value: option.extra,
              }))
            "
            placeholder="请选择渠道"
            show-search
          />
        </FormItem>
        <FormItem label="账户类型" required>
          <Select
            v-model:value="renameForm.accountType"
            :options="accountTypeOptions"
            placeholder="请选择账户类型"
            show-search
          />
        </FormItem>
        <FormItem label="投手" required>
          <Select
            v-model:value="renameForm.deliverName"
            :options="
              pitcherOptions.map((option) => ({
                label: option.label,
                value: option.label,
              }))
            "
            placeholder="请选择投手"
            show-search
          />
        </FormItem>
        <FormItem label="自定义后缀">
          <Input
            v-model:value="renameForm.customSuffix"
            :maxlength="10"
            show-count
          />
        </FormItem>
        <p class="mb-0 text-xs leading-5 text-slate-500">
          名称将按“渠道-账户类型-投手-后缀-日期-序号”的 MPower 规则生成。
        </p>
      </Form>
    </Modal>

    <Modal
      v-model:open="bindingModalOpen"
      :confirm-loading="actionLoading"
      title="账户关联投手"
      :width="680"
      @ok="saveBinding"
    >
      <Form class="pt-4" layout="vertical">
        <FormItem label="已选账户">
          <div
            class="max-h-24 overflow-y-auto rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600"
          >
            {{ selectedAccountSummary }}
          </div>
        </FormItem>
        <FormItem label="渠道" required>
          <Select
            v-model:value="bindingForm.channelId"
            :options="channelOptions"
            placeholder="请选择渠道"
            show-search
          />
        </FormItem>
        <FormItem label="投手" required>
          <Select
            v-model:value="bindingForm.operatorId"
            :options="pitcherOptions"
            placeholder="请选择投手"
            show-search
          />
        </FormItem>
        <FormItem label="账户类型" required>
          <Select
            v-model:value="bindingForm.accountType"
            :options="accountTypeOptions"
            placeholder="请选择账户类型"
            show-search
          />
        </FormItem>
      </Form>
    </Modal>

    <Drawer v-model:open="columnDrawerOpen" title="配置列表列" :width="420">
      <p class="mb-4 text-sm text-slate-500">
        渠道、账户 ID、账户名称和操作列始终保留。
      </p>
      <Checkbox.Group
        v-model:value="visibleColumnKeys"
        :options="accountColumnOptions"
      />
      <template #footer>
        <div class="flex justify-end gap-2">
          <Button @click="resetColumnPreferences">恢复默认</Button>
          <Button type="primary" @click="columnDrawerOpen = false">完成</Button>
        </div>
      </template>
    </Drawer>

    <Drawer v-model:open="detailOpen" title="账户详情" :width="620">
      <template v-if="selectedAccount">
        <h2 class="mb-1 text-xl">
          {{ selectedAccount.accountName || '未命名账户' }}
        </h2>
        <div class="font-mono text-sm text-slate-500">
          {{ selectedAccount.accountId }}
        </div>
        <dl class="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div
            v-for="item in [
              ['投放师', formatOperatorWithDepartment(selectedAccount)],
              ['渠道', selectedAccount.channelName],
              ['账户类型', selectedAccount.accountType],
              ['账户状态', statusMeta[getAccountStatus(selectedAccount)].label],
              [
                '归类状态',
                Number(selectedAccount.classifyStatus) === 1
                  ? '已归类'
                  : '未归类',
              ],
              ['余额', formatMoney(selectedAccount.balance, true)],
              ['总花费', formatMoney(selectedAccount.amountSpent, true)],
              ['花费金额', formatMoney(selectedAccount.totalSpend)],
              ['卡扣金额', formatMoney(selectedAccount.actualDeduction, true)],
              ['时区', formatTimezone(selectedAccount)],
              ['所属主体', selectedAccount.businessName],
              ['BM ID', selectedAccount.bmId],
              ['管理 BM', selectedAccount.bmFromFeishu],
              ['授权时间', selectedAccount.authTime],
              ['创建时间', selectedAccount.createTime],
              ['停用时间', selectedAccount.stopTime],
              ['解绑时间', selectedAccount.unbindTime],
              ['封户时间', selectedAccount.banTime],
              ['被封原因', selectedAccount.disableReason],
            ]"
            :key="String(item[0])"
            class="rounded-lg bg-slate-50 p-3"
          >
            <dt class="text-xs text-slate-500">{{ item[0] }}</dt>
            <dd class="m-0 mt-1 break-words font-medium">
              {{ item[1] || '—' }}
            </dd>
          </div>
        </dl>
        <div class="mt-4 rounded-lg bg-slate-50 p-3">
          <div class="text-xs text-slate-500">备注</div>
          <div class="mt-1">{{ selectedAccount.remark || '—' }}</div>
        </div>
      </template>
    </Drawer>
  </div>
</template>

<style scoped>
.account-management-page {
  gap: var(--adpulse-section-gap);
  padding: var(--adpulse-page-gutter);
}

.account-management-page h1 {
  font-size: var(--adpulse-page-title-size);
  line-height: 1.35;
}

.account-statistic-value {
  font-size: calc(var(--adpulse-page-title-size) + 2px);
  line-height: 1.35;
}

.account-status-tabs {
  min-width: 0;
}

.account-management-table {
  min-width: 0;
  max-width: 100%;
}

@media (max-width: 1024px) {
  .account-status-tabs {
    width: 100%;
    overflow-x: auto;
  }
}
</style>
