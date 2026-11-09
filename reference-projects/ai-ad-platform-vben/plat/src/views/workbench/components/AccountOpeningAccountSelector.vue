<script lang="ts" setup>
import type {
  ChannelAccountRecord,
  ChannelOption,
} from '#/api/mpower/channel-management';

import { computed, onMounted, reactive, ref, watch } from 'vue';

import { Button, Input, Select, Table, Tag, message } from 'ant-design-vue';

import {
  getAccountOpeningChannelOptions,
  getAccountTypes,
  getAvailableChannelAccounts,
} from '#/api/mpower/channel-management';

interface Props {
  applicationChannelId?: string;
  applicationChannelName?: string;
  applicationTimezone?: string;
  expectedQuantity: number;
  modelValue?: string;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  'update:modelValue': [value: string];
}>();

const filters = reactive({
  accountIds: '',
  accountType: undefined as string | undefined,
  channelId: props.applicationChannelId || undefined,
  status: 1 as 1 | 2 | undefined,
  usageStatus: undefined as 0 | 1 | undefined,
});
const accountPage = reactive({ current: 1, pageSize: 10, total: 0 });
const accounts = ref<ChannelAccountRecord[]>([]);
const accountTypeOptions = ref<Array<{ label: string; value: string }>>([]);
const channelOptions = ref<ChannelOption[]>([]);
const selectedAccounts = ref(new Map<string, ChannelAccountRecord>());
const accountLoading = ref(false);
let accountRequestId = 0;

type AccountTableRecord = Partial<ChannelAccountRecord> &
  Record<string, unknown>;

const accountColumns = [
  { key: 'channel', title: '渠道', width: 160 },
  { dataIndex: 'accountType', title: '账户类型', width: 120 },
  { key: 'account', title: '账户名称 / ID', width: 230 },
  { dataIndex: 'timezone', title: '时区', width: 100 },
  { key: 'accountStatus', title: '账户状态', width: 110 },
  { key: 'assignmentStatus', title: '是否分配', width: 110 },
  { key: 'assignee', title: '分配人', width: 160 },
];

const selectedAccountIds = computed(() => [...selectedAccounts.value.keys()]);
const channelNameById = computed(
  () => new Map(channelOptions.value.map((item) => [item.value, item.label])),
);

function accountBusinessId(account: AccountTableRecord) {
  return String(account.fbAccountId ?? account.accountId ?? '').trim();
}

function channelName(account: AccountTableRecord) {
  return (
    channelNameById.value.get(String(account.channelId ?? '')) ??
    (String(account.channelId ?? '').trim() || '—')
  );
}

function isAssigned(account: AccountTableRecord) {
  return Number(account.usageStatus) === 1;
}

function isSelectable(account: AccountTableRecord) {
  return Number(account.status) === 1;
}

function accountIdsFilter() {
  const accountIds = filters.accountIds
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  return accountIds.length > 0 ? accountIds : undefined;
}

function syncModelValue() {
  emit('update:modelValue', selectedAccountIds.value.join(';'));
}

/** 加载可办理的渠道账户；已分配广告账户保留在列表中，支持共享申请。 */
async function loadAccounts() {
  const requestId = ++accountRequestId;
  const channelId = String(filters.channelId ?? '').trim();
  if (!channelId) {
    accounts.value = [];
    accountPage.total = 0;
    accountLoading.value = false;
    return;
  }

  accountLoading.value = true;
  try {
    const response = await getAvailableChannelAccounts<ChannelAccountRecord>({
      accountIds: accountIdsFilter(),
      accountType: filters.accountType,
      channelId,
      pageNum: accountPage.current,
      pageSize: accountPage.pageSize,
      status: filters.status,
      usageStatus: filters.usageStatus,
    });
    if (requestId !== accountRequestId) return;
    accounts.value = response.rows.filter((account) =>
      accountBusinessId(account),
    );
    accountPage.total = response.total;
  } finally {
    if (requestId === accountRequestId) accountLoading.value = false;
  }
}

/** 筛选条件变更后从第一页重新查询。 */
function handleFilterChange() {
  accountPage.current = 1;
  void loadAccounts();
}

function handleAccountSelectionChange(
  _keys: (number | string)[],
  rows: ChannelAccountRecord[],
) {
  const currentPageIds = new Set(accounts.value.map(accountBusinessId));
  for (const id of currentPageIds) selectedAccounts.value.delete(id);
  for (const row of rows) {
    const id = accountBusinessId(row);
    if (id) selectedAccounts.value.set(id, row);
  }
  if (selectedAccounts.value.size > props.expectedQuantity) {
    for (const id of [...selectedAccounts.value.keys()].slice(
      props.expectedQuantity,
    )) {
      selectedAccounts.value.delete(id);
    }
    message.warning(`最多只能选择 ${props.expectedQuantity} 个账户`);
  }
  selectedAccounts.value = new Map(selectedAccounts.value);
  syncModelValue();
}

function removeSelectedAccount(id: string) {
  selectedAccounts.value.delete(id);
  selectedAccounts.value = new Map(selectedAccounts.value);
  syncModelValue();
}

watch(
  () => props.applicationChannelId,
  (value) => {
    const channelId = String(value ?? '').trim() || undefined;
    if (filters.channelId === channelId) return;
    filters.channelId = channelId;
    accountPage.current = 1;
    void loadAccounts();
  },
);

onMounted(async () => {
  const [channels, accountTypes] = await Promise.all([
    getAccountOpeningChannelOptions(),
    getAccountTypes(),
  ]);
  channelOptions.value = channels;
  accountTypeOptions.value = accountTypes.data.map((item) => ({
    label: item.accountType,
    value: item.accountType,
  }));
  await loadAccounts();
});
</script>

<template>
  <div class="space-y-4">
    <section class="rounded-lg border border-slate-200 p-3">
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Select
          v-model:value="filters.channelId"
          aria-label="渠道筛选"
          :options="channelOptions"
          placeholder="请选择渠道"
          show-search
          @change="handleFilterChange"
        />
        <Select
          v-model:value="filters.accountType"
          allow-clear
          aria-label="账户类型筛选"
          :options="accountTypeOptions"
          placeholder="全部账户类型"
          show-search
          @change="handleFilterChange"
        />
        <Select
          v-model:value="filters.status"
          allow-clear
          aria-label="账户状态筛选"
          :options="[
            { label: '正常', value: 1 },
            { label: '停用', value: 2 },
          ]"
          placeholder="全部账户状态"
          @change="handleFilterChange"
        />
        <Select
          v-model:value="filters.usageStatus"
          allow-clear
          aria-label="是否分配筛选"
          :options="[
            { label: '未分配', value: 0 },
            { label: '已分配', value: 1 },
          ]"
          placeholder="是否分配"
          @change="handleFilterChange"
        />
        <div class="flex gap-2">
          <Input.TextArea
            v-model:value="filters.accountIds"
            aria-label="账户 ID 筛选"
            :auto-size="{ minRows: 1, maxRows: 2 }"
            placeholder="账户 ID，一行一个"
            @press-enter="handleFilterChange"
          />
          <Button type="primary" @click="handleFilterChange">查询</Button>
        </div>
      </div>
      <p class="mb-0 mt-3 text-xs text-slate-500">
        申请渠道仅作为默认筛选，可切换渠道选择其他账户；已分配给其他人的广告账户仍可共享，已分配给当前申请人的账户不可重复分配，停用账户不可选择。
      </p>
    </section>

    <section class="min-w-0 rounded-lg border border-slate-200 p-3">
      <Table
        class="account-opening-account-table"
        :columns="accountColumns"
        :data-source="accounts"
        :loading="accountLoading"
        :locale="{
          emptyText: filters.channelId ? '暂无可用账户' : '请先选择渠道',
        }"
        :pagination="{
          current: accountPage.current,
          pageSize: accountPage.pageSize,
          total: accountPage.total,
          showSizeChanger: true,
        }"
        :row-key="accountBusinessId"
        :row-selection="{
          preserveSelectedRowKeys: true,
          selectedRowKeys: selectedAccountIds,
          onChange: handleAccountSelectionChange,
          getCheckboxProps: (record) => ({
            disabled:
              !isSelectable(record) ||
              (selectedAccounts.size >= expectedQuantity &&
                !selectedAccounts.has(accountBusinessId(record))),
          }),
        }"
        :scroll="{
          x: 1100,
          y: 'var(--account-opening-table-body-height)',
        }"
        size="small"
        @change="
          (pagination) => {
            accountPage.current = pagination.current || 1;
            accountPage.pageSize = pagination.pageSize || 10;
            void loadAccounts();
          }
        "
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'channel'">
            {{ channelName(record) }}
          </template>
          <template v-else-if="column.key === 'account'">
            <div class="min-w-0">
              <div class="truncate" :title="record.accountName">
                {{ record.accountName || '未命名账户' }}
              </div>
              <div class="truncate font-mono text-xs text-slate-500">
                {{ accountBusinessId(record) }}
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'accountStatus'">
            <Tag :color="Number(record.status) === 1 ? 'success' : 'error'">
              {{ Number(record.status) === 1 ? '正常' : '停用' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'assignmentStatus'">
            <Tag :color="isAssigned(record) ? 'processing' : 'default'">
              {{ isAssigned(record) ? '已分配' : '未分配' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'assignee'">
            {{ record.operatorName || '—' }}
          </template>
        </template>
      </Table>
    </section>

    <section class="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div class="mb-2 flex items-center justify-between text-sm">
        <span class="font-medium text-slate-700">已选账户</span>
        <span class="text-slate-500">
          {{ selectedAccounts.size }} / {{ expectedQuantity }} 个
        </span>
      </div>
      <div v-if="selectedAccounts.size" class="flex flex-wrap gap-2">
        <Tag
          v-for="entry in Array.from(selectedAccounts.entries())"
          :key="entry[0]"
          closable
          color="blue"
          @close="removeSelectedAccount(entry[0])"
        >
          {{ entry[1].accountName || entry[0] }} · {{ entry[0] }}
        </Tag>
      </div>
      <span v-else class="text-sm text-slate-400">暂未选择账户</span>
    </section>
  </div>
</template>

<style scoped>
.account-opening-account-table {
  --account-opening-table-body-height: clamp(360px, 60vh, 520px);
}
</style>
