<script lang="ts" setup>
import type {
  AccountTypeRecord,
  ChannelAccountRecord,
  ChannelRecord,
} from '#/api/mpower';
import type { AdAccountAsset } from '#/api/main';
import type { Dayjs } from 'dayjs';

import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { getAdAccountAssetsByIds } from '#/api';
import {
  Button,
  Card,
  Checkbox,
  CheckboxGroup,
  DatePicker,
  Dropdown,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Pagination,
  Select,
  Spin,
  Tag,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  assignPitcher,
  deleteChannelAccount,
  exportChannelAccounts,
  getAccountCountStats,
  getAccountTypes,
  getChannel,
  getChannelAccounts,
  getChannelAccountStatistics,
  getPitchers,
} from '#/api/mpower';

import SecondaryPageHeader from '#/components/SecondaryPageHeader.vue';
import MediaResourcePage from '../components/MediaResourcePage.vue';
import BatchAccountModal from './components/BatchAccountModal.vue';
import {
  ACCOUNT_STATUS_OPTIONS,
  downloadBlob,
  formatMoney,
  USAGE_STATUS_OPTIONS,
} from './constants';
import AntDataTable, {
  type AntDataTableColumn,
} from '#/components/ui/AntDataTable.vue';
import { createAdAccountAssetDataColumns } from '../components/ad-account-table-columns';

type AccountRow = ChannelAccountRecord &
  AdAccountAsset & {
    applicationId?: string;
    legacyAccountName?: string;
  } & Record<string, any>;

const PRIMARY_COLUMN_KEYS = new Set([
  'accountName',
  'accountId',
  'accountType',
  'accountAttribute',
  'channelName',
  'consumption',
  'balance',
  'status',
  'usageStatus',
  'operatorName',
]);

const route = useRoute();
const router = useRouter();
const inventoryStatusMeta = {
  ASSIGNED: { color: 'success', label: '已分配' },
  AVAILABLE: { color: 'default', label: '可用' },
  DISABLED: { color: 'error', label: '已停用' },
  RETURN_PENDING: { color: 'warning', label: '待回收' },
} as const;

function getInventoryStatusMeta(value: unknown) {
  return (
    inventoryStatusMeta[value as keyof typeof inventoryStatusMeta] ??
    inventoryStatusMeta.AVAILABLE
  );
}
const channelId = computed(() => String(route.params.id));
const channelName = ref(String(route.query.channelName ?? ''));
const channel = ref<ChannelRecord>();
const loading = ref(false);
const exporting = ref(false);
const rows = ref<AccountRow[]>([]);
const total = ref(0);
const stats = ref<Record<string, any>>({});
const counts = ref<Record<string, any>>({});
const accountTypes = ref<AccountTypeRecord[]>([]);
const pitcherOptions = ref<Array<{ label: string; value: string }>>([]);
const selectedKeys = ref<Array<number | string>>([]);
const expandedKeys = ref<Array<number | string>>([]);
const batchModal = ref<InstanceType<typeof BatchAccountModal>>();
const query = reactive({
  accountType: route.query.accountType as string | undefined,
  accountIdsText: '',
  pageNum: 1,
  pageSize: 10,
  spendDateRange: [dayjs(), dayjs()] as [Dayjs, Dayjs] | undefined,
  status: undefined as string | undefined,
  usageStatus: undefined as string | undefined,
});

const assetColumns: AntDataTableColumn[] =
  createAdAccountAssetDataColumns<AccountRow>().flatMap((column) => {
    if (
      !('dataIndex' in column) ||
      typeof column.key !== 'string' ||
      typeof column.title !== 'string'
    ) {
      return [];
    }
    return [
      {
        dataIndex:
          typeof column.dataIndex === 'string' ? column.dataIndex : column.key,
        key: column.key,
        title: column.title,
        width: column.width,
      },
    ];
  });
const allColumns: any[] = [
  ...assetColumns,
  { dataIndex: 'takeTime', title: '花费时间', width: 170 },
  { dataIndex: 'consumption', title: '花费金额 ($)', width: 130 },
  { dataIndex: 'balance', title: '账户余额 ($)', width: 130 },
  { dataIndex: 'status', title: '账户状态', width: 120 },
  { dataIndex: 'usageStatus', title: '使用情况', width: 140 },
  { dataIndex: 'operatorName', title: '使用人', width: 180 },
  { dataIndex: 'belongTeam', title: '使用团队', width: 140 },
  { dataIndex: 'subjectName', title: '所属主体', width: 220 },
  { dataIndex: 'openingBalance', title: '开户费 ($)', width: 120 },
  { dataIndex: 'byBalance', title: '买户费 (￥)', width: 120 },
  { dataIndex: 'byBalanceU', title: '买户费 ($)', width: 120 },
  { dataIndex: 'actualDeduction', title: '卡扣金额 ($)', width: 130 },
  { dataIndex: 'amountSpent', title: '历史花费金额', width: 140 },
  { dataIndex: 'remainingSpendCap', title: '剩余应付', width: 120 },
  { dataIndex: 'openDate', title: '开户日期', width: 160 },
  { dataIndex: 'createTime', title: '下户日期', width: 160 },
  { dataIndex: 'assignTime', title: '分配时间', width: 160 },
  { dataIndex: 'remark', title: '备注', width: 180 },
];
const accountTableColumns = [
  { key: 'expand', title: '', width: 48, align: 'center' as const },
  { key: 'select', title: '', width: 48, align: 'center' as const },
  ...assetColumns.filter((column) =>
    PRIMARY_COLUMN_KEYS.has(String(column.key)),
  ),
  {
    dataIndex: 'consumption',
    key: 'consumption',
    title: '花费金额 ($)',
    width: 130,
    align: 'right' as const,
  },
  {
    dataIndex: 'balance',
    key: 'balance',
    title: '账户余额 ($)',
    width: 130,
    align: 'right' as const,
  },
  { dataIndex: 'status', key: 'status', title: '账户状态', width: 110 },
  {
    dataIndex: 'usageStatus',
    key: 'usageStatus',
    title: '使用情况',
    width: 120,
  },
  {
    dataIndex: 'operatorName',
    key: 'operatorName',
    title: '使用人',
    width: 140,
  },
  { key: 'action', title: '操作', width: 160, align: 'right' as const },
];
const visibleKeys = ref(
  allColumns
    .filter((column: any) => column.dataIndex)
    .map((column: any) => String(column.dataIndex)),
);
const expandedColumns = computed(() =>
  allColumns.filter(
    (column: any) =>
      column.dataIndex &&
      !PRIMARY_COLUMN_KEYS.has(String(column.dataIndex)) &&
      visibleKeys.value.includes(String(column.dataIndex)),
  ),
);
const selectableRows = computed(() =>
  rows.value.filter((record) => String(record.usageStatus) === '0'),
);
const allCurrentRowsSelected = computed(
  () =>
    selectableRows.value.length > 0 &&
    selectableRows.value.every((record) =>
      selectedKeys.value.includes(record.accountId),
    ),
);
const someCurrentRowsSelected = computed(
  () =>
    !allCurrentRowsSelected.value &&
    selectableRows.value.some((record) =>
      selectedKeys.value.includes(record.accountId),
    ),
);
const accountTypeOptions = computed(() =>
  accountTypes.value.map((item) => ({
    label: item.accountType,
    value: item.accountType,
  })),
);
const detailMetrics = computed(() => [
  {
    label: '关联账户',
    suffix: '个',
    value: counts.value.allCount ?? total.value,
  },
  {
    label: '活跃账户',
    suffix: '个',
    value: counts.value.activeCount ?? 0,
  },
  {
    label: '账户花费',
    prefix: '$',
    value: formatMoney(stats.value.consumption),
  },
  {
    label: '账户余额',
    prefix: '$',
    value: formatMoney(stats.value.balance),
  },
]);

function buildParams() {
  const [startDate, endDate] = query.spendDateRange ?? [];
  return {
    ...query,
    accountIds: query.accountIdsText
      ? query.accountIdsText
          .split(/[\s,，]+/)
          .map((accountId) => accountId.trim().replace(/^act_/, ''))
          .filter(Boolean)
      : undefined,
    accountIdsText: undefined,
    channelId: channelId.value,
    endDate: endDate?.format('YYYY-MM-DD'),
    spendDateRange: undefined,
    startDate: startDate?.format('YYYY-MM-DD'),
  };
}

function validateSpendDateRange() {
  if (query.spendDateRange?.length === 2) return true;
  message.error('请选择消耗/花费时间');
  return false;
}

async function load() {
  if (!validateSpendDateRange()) return;
  loading.value = true;
  try {
    const params = buildParams();
    const [listResponse, statsResponse] = await Promise.all([
      getChannelAccounts<AccountRow>(params),
      getChannelAccountStatistics(params),
    ]);
    const accountIds = (listResponse.rows ?? []).map((account) =>
      String(account.accountId ?? '').trim(),
    );
    const assets =
      accountIds.length > 0 ? await getAdAccountAssetsByIds(accountIds) : [];
    const assetsByAccountId = new Map(
      assets.map((asset) => [asset.accountId.trim(), asset]),
    );
    const spendDateRange = `${params.startDate} - ${params.endDate}`;
    total.value = listResponse.total;
    rows.value = (listResponse.rows ?? []).map((item) => {
      const accountId = String(item.accountId ?? '').trim();
      const asset = assetsByAccountId.get(accountId);
      return {
        ...item,
        accountAttribute: asset?.accountAttribute ?? '',
        accountId,
        accountName: asset?.accountName ?? item.accountName ?? '',
        accountType: asset?.accountType ?? item.accountType ?? '',
        applicationId: undefined,
        backupManagedBm: asset?.backupManagedBm ?? '',
        backupManagedBmId: asset?.backupManagedBmId ?? '',
        balance: Number(item.balance ?? 0),
        cardNumber: asset?.cardNumber ?? '',
        cardStation: asset?.cardStation ?? '',
        channelId:
          asset?.channelId ?? String(item.channelId ?? channelId.value),
        channelName: asset?.channelName ?? channelName.value,
        id: accountId,
        inventoryStatus: asset?.inventoryStatus ?? 'AVAILABLE',
        legacyAccountName: item.accountName,
        managedBm: asset?.managedBm ?? '',
        managedBmId: asset?.managedBmId ?? '',
        operatorName: asset?.usageUserName ?? item.operatorName ?? '',
        status: asset?.accountStatus ?? item.status,
        // 资产台账会用 MongoDB 的 timezone_name 补齐时区名称。
        timezone: asset?.timezone || item.timezone || '',
        takeTime: spendDateRange,
        usageStatus: asset
          ? (asset.assignments?.length ?? 0) > 0
            ? 1
            : 0
          : item.usageStatus,
      };
    });
    stats.value = statsResponse.data ?? {};
  } finally {
    loading.value = false;
  }
}

async function loadMetadata() {
  const [countResponse, typeResponse, pitcherResponse] = await Promise.all([
    getAccountCountStats(channelId.value),
    getAccountTypes(),
    getPitchers({ pageNum: 1, pageSize: 1_000_000 }),
  ]);
  counts.value = countResponse.data ?? {};
  accountTypes.value = typeResponse.data ?? [];
  const pitchers = pitcherResponse.data?.records ?? [];
  pitcherOptions.value = pitchers.map((item: any) => ({
    label: item.nickName || item.userName || String(item.userId),
    value: String(item.userId),
  }));
}

async function loadChannel() {
  const response = await getChannel<ChannelRecord>(channelId.value);
  channel.value = response.data;
  channelName.value = response.data?.channelName ?? `渠道 ${channelId.value}`;
}

function search() {
  if (!validateSpendDateRange()) return;
  query.pageNum = 1;
  selectedKeys.value = [];
  void load();
}

function reset() {
  Object.assign(query, {
    accountType: undefined,
    accountIdsText: '',
    pageNum: 1,
    spendDateRange: [dayjs(), dayjs()],
    status: undefined,
    usageStatus: undefined,
  });
  void load();
}

function accountStatus(record: Record<string, unknown>) {
  if (record.synced === false) return '未同步';
  return (
    ACCOUNT_STATUS_OPTIONS.find((item) => item.value === String(record.status))
      ?.label ?? '未知'
  );
}

function accountStatusColor(record: Record<string, unknown>) {
  if (record.synced === false) return 'default';
  if ([1, 201].includes(Number(record.status))) return 'success';
  if ([2, 101, 202].includes(Number(record.status))) return 'error';
  return 'warning';
}

function usageMeta(status: unknown) {
  return (
    USAGE_STATUS_OPTIONS.find((item) => item.value === String(status)) ??
    USAGE_STATUS_OPTIONS[0]!
  );
}

function formatExpandedValue(record: AccountRow, dataIndex: string) {
  const value = record[dataIndex];
  if (dataIndex === 'byBalance') return `￥${formatMoney(value)}`;
  if (dataIndex === 'createTime') {
    return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
  }
  if (
    [
      'actualDeduction',
      'amountSpent',
      'byBalanceU',
      'openingBalance',
      'remainingSpendCap',
    ].includes(dataIndex)
  ) {
    return `$${formatMoney(value)}`;
  }
  return value === null || value === undefined || value === '' ? '-' : value;
}

function showTotal(value: number) {
  return `共 ${value} 个账户`;
}

function toggleExpanded(accountId: number | string) {
  expandedKeys.value = expandedKeys.value.includes(accountId)
    ? expandedKeys.value.filter((key) => key !== accountId)
    : [...expandedKeys.value, accountId];
}

function toggleRowSelection(accountId: number | string, checked: boolean) {
  selectedKeys.value = checked
    ? [...new Set([accountId, ...selectedKeys.value])]
    : selectedKeys.value.filter((key) => key !== accountId);
}

function toggleCurrentPageSelection(checked: boolean) {
  const currentIds = selectableRows.value.map((record) =>
    String(record.accountId),
  );
  selectedKeys.value = checked
    ? [...new Set([...currentIds, ...selectedKeys.value])]
    : selectedKeys.value.filter((key) => !currentIds.includes(String(key)));
}

async function distribute(userId: any) {
  userId = String(userId ?? '');
  if (selectedKeys.value.length === 0) {
    message.warning('请先勾选广告账户');
    return;
  }
  const pitcher = pitcherOptions.value.find(
    (item) => item.value === userId,
  )?.label;
  Modal.confirm({
    content: `确认将 ${selectedKeys.value.length} 个账户分配给投手“${pitcher}”？`,
    title: '分配投手',
    async onOk() {
      await assignPitcher({
        channelAccountIds: selectedKeys.value,
        operatorId: userId,
      });
      selectedKeys.value = [];
      message.success('分配投手成功');
      await load();
    },
  });
}

function remove(record: any) {
  Modal.confirm({
    content: `是否确认删除账户“${record.accountName || record.fbAccountId}”？`,
    okButtonProps: { danger: true },
    title: '删除账户',
    async onOk() {
      await deleteChannelAccount(record.accountId);
      message.success('删除成功');
      await Promise.all([load(), loadMetadata()]);
    },
  });
}

/** 渠道账户存在来源申请单时，保留审批详情的可追溯入口。 */
function openApplicationDetail(applicationId: string) {
  void router.push({
    path: `/workbench/approvals/${encodeURIComponent(applicationId)}`,
  });
}

async function exportData() {
  if (!validateSpendDateRange()) return;
  exporting.value = true;
  try {
    const blob = await exportChannelAccounts({
      ...buildParams(),
      includeFields: visibleKeys.value,
      pageSize: 99_999_999,
    });
    downloadBlob(blob, `渠道账户数据_${dayjs().format('YYYY-MM-DD')}.xlsx`);
    message.success('导出成功');
  } finally {
    exporting.value = false;
  }
}

onMounted(async () => {
  await loadChannel();
  await Promise.all([load(), loadMetadata()]);
});
</script>

<template>
  <MediaResourcePage>
    <SecondaryPageHeader
      back-to="/media-resources/channels"
      :description="`${channel?.channelCode || `渠道 ID：${channelId}`} · ${channel?.belongTeam || '未设置团队'} · ${Number(channel?.channelType) === 1 ? '代理商' : '号商'}`"
      :title="channelName"
    >
      <template #extra>
        <Tag :color="String(channel?.status) === '1' ? 'success' : 'default'">
          {{ String(channel?.status) === '1' ? '正常' : '停用' }}
        </Tag>
        <Button
          type="primary"
          @click="router.push(`/media-resources/channels/${channelId}/edit`)"
        >
          编辑渠道
        </Button>
      </template>
    </SecondaryPageHeader>

    <section class="detail-metrics">
      <article v-for="(item, index) in detailMetrics" :key="item.label">
        <div class="metric-copy">
          <span>{{ item.label }}</span>
          <div>
            <small v-if="item.prefix">{{ item.prefix }}</small>
            <strong>{{ item.value }}</strong>
            <small v-if="item.suffix">{{ item.suffix }}</small>
          </div>
        </div>
        <div class="metric-spark" :class="`metric-spark--${index + 1}`">
          <i></i><i></i><i></i>
        </div>
      </article>
    </section>

    <Card class="detail-card filter-section" :bordered="false">
      <div class="section-title-row">
        <div>
          <h2>账户筛选</h2>
          <p>按账户类型、账户 ID 和消耗/花费时间查找渠道关联账户</p>
        </div>
      </div>
      <Form
        :model="query"
        layout="vertical"
        class="channel-filter ux-filter-form"
      >
        <FormItem class="ux-filter-field" label="账户类型">
          <Select
            v-model:value="query.accountType"
            :options="accountTypeOptions"
            class="filter-control"
            allow-clear
          />
        </FormItem>
        <FormItem class="ux-filter-field" label="账户 ID">
          <Input.TextArea
            v-model:value="query.accountIdsText"
            :auto-size="{ minRows: 1, maxRows: 3 }"
            class="filter-control filter-textarea"
            placeholder="多个 ID 可用换行、空格或逗号分隔"
            allow-clear
          />
        </FormItem>
        <FormItem class="ux-filter-field" label="消耗/花费时间">
          <DatePicker.RangePicker
            v-model:value="query.spendDateRange"
            :allow-clear="true"
            class="filter-control"
          />
        </FormItem>
        <div class="filter-actions ux-filter-actions">
          <Button type="primary" @click="search">查询</Button>
          <Button @click="reset">重置</Button>
        </div>
      </Form>
    </Card>

    <Card class="detail-card account-section" :bordered="false">
      <div class="account-toolbar">
        <div class="account-actions">
          <Button type="primary" @click="batchModal?.show()">
            批量导入账户
          </Button>
          <Select
            :options="pitcherOptions"
            class="w-40"
            placeholder="分配投手"
            show-search
            @change="distribute"
          />
          <Button :loading="exporting" @click="exportData">导出</Button>
          <Button @click="load">刷新</Button>
          <Dropdown trigger="click">
            <Button>自定义列</Button>
            <template #overlay>
              <div class="column-panel">
                <div class="column-panel-title">展开区域显示字段</div>
                <CheckboxGroup
                  v-model:value="visibleKeys"
                  :options="
                    allColumns
                      .filter(
                        (item: any) =>
                          item.dataIndex &&
                          !PRIMARY_COLUMN_KEYS.has(String(item.dataIndex)),
                      )
                      .map((item: any) => ({
                        label: item.title,
                        value: item.dataIndex,
                      }))
                  "
                  class="column-options"
                />
              </div>
            </template>
          </Dropdown>
        </div>
      </div>

      <div v-if="selectedKeys.length > 0" class="selection-bar">
        <span>
          已选择 <strong>{{ selectedKeys.length }}</strong> 个可分配账户
        </span>
        <span class="selection-hint">可使用右上角“分配投手”完成批量分配</span>
        <Button type="link" @click="selectedKeys = []"> 取消选择 </Button>
      </div>

      <Spin :spinning="loading">
        <AntDataTable
          :columns="accountTableColumns"
          :data="rows"
          :loading="loading"
          :paginate="false"
          :expanded-row-keys="expandedKeys"
          row-key="accountId"
        >
          <template #header-select>
            <Checkbox
              :checked="allCurrentRowsSelected"
              :disabled="selectableRows.length === 0"
              :indeterminate="someCurrentRowsSelected"
              aria-label="选择当前页全部可分配账户"
              @change="
                (event) =>
                  toggleCurrentPageSelection(Boolean(event.target.checked))
              "
            />
          </template>
          <template #cell-expand="{ record }">
            <Button
              :aria-expanded="expandedKeys.includes(record.accountId)"
              :aria-label="`${expandedKeys.includes(record.accountId) ? '收起' : '展开'}账户 ${record.accountName || record.fbAccountId}`"
              class="account-expand-button"
              type="text"
              @click="toggleExpanded(record.accountId)"
            >
              <span
                :class="{
                  'is-expanded': expandedKeys.includes(record.accountId),
                }"
                >›</span
              >
            </Button>
          </template>
          <template #cell-select="{ record }">
            <Checkbox
              :checked="selectedKeys.includes(record.accountId)"
              :disabled="String(record.usageStatus) !== '0'"
              :aria-label="`选择账户 ${record.accountName || record.fbAccountId}`"
              @change="
                (event) =>
                  toggleRowSelection(
                    record.accountId,
                    Boolean(event.target.checked),
                  )
              "
            />
          </template>
          <template #cell-accountName="{ record }">
            <span class="account-name-text" :title="record.accountName || '-'">
              {{ record.accountName || '-' }}
            </span>
          </template>
          <template #cell-accountId="{ record }">
            <span :title="String(record.accountId || '-')">
              {{ record.accountId || '-' }}
            </span>
          </template>
          <template #cell-inventoryStatus="{ record }">
            <Tag :color="getInventoryStatusMeta(record.inventoryStatus).color">
              {{ getInventoryStatusMeta(record.inventoryStatus).label }}
            </Tag>
          </template>
          <template #cell-consumption="{ record }">
            ${{ formatMoney(record.consumption) }}
          </template>
          <template #cell-balance="{ record }">
            ${{ formatMoney(record.balance) }}
          </template>
          <template #cell-status="{ record }">
            <Tag :color="accountStatusColor(record)">
              {{ accountStatus(record) }}
            </Tag>
          </template>
          <template #cell-usageStatus="{ record }">
            <Tag :color="usageMeta(record.usageStatus).color">
              {{ usageMeta(record.usageStatus).label }}
            </Tag>
          </template>
          <template #cell-operatorName="{ record }">
            <span :title="record.operatorName || '-'">
              {{ record.operatorName || '-' }}
            </span>
          </template>
          <template #cell-action="{ record }">
            <div class="flex items-center justify-end gap-1 whitespace-nowrap">
              <Button
                v-if="record.applicationId"
                type="link"
                @click="openApplicationDetail(record.applicationId)"
              >
                查看申请单
              </Button>
              <Button danger type="link" @click="remove(record)"> 删除 </Button>
            </div>
          </template>
          <template #row-after="{ record }">
            <div class="expanded-account-details">
              <div
                v-for="column in expandedColumns"
                :key="String(column.dataIndex)"
                class="expanded-detail-item"
              >
                <span>{{ column.title }}</span>
                <strong>{{
                  formatExpandedValue(record, String(column.dataIndex))
                }}</strong>
              </div>
            </div>
          </template>
          <template #footer>
            <div v-if="rows.length" class="table-summary-bar">
              <strong>合计</strong>
              <span>花费：${{ formatMoney(stats.consumption) }}</span>
              <span>余额：${{ formatMoney(stats.balance) }}</span>
            </div>
          </template>
        </AntDataTable>

        <div v-if="false" class="account-list-scroll">
          <div class="account-list-grid account-list-header" role="row">
            <span aria-hidden="true"></span>
            <Checkbox
              :checked="allCurrentRowsSelected"
              :disabled="selectableRows.length === 0"
              :indeterminate="someCurrentRowsSelected"
              aria-label="选择当前页全部可分配账户"
              @change="
                (event) =>
                  toggleCurrentPageSelection(Boolean(event.target.checked))
              "
            />
            <span>账户名称</span>
            <span>账户类型</span>
            <span>账户 ID (FB)</span>
            <span>花费金额 ($)</span>
            <span>账户余额 ($)</span>
            <span>账户状态</span>
            <span>使用情况</span>
            <span>使用人</span>
            <span>操作</span>
          </div>

          <template v-for="record in rows" :key="record.accountId">
            <div class="account-list-grid account-list-row" role="row">
              <button
                :aria-expanded="expandedKeys.includes(record.accountId)"
                :aria-label="`${expandedKeys.includes(record.accountId) ? '收起' : '展开'}账户 ${record.accountName || record.fbAccountId}`"
                class="account-expand-button"
                type="button"
                @click="toggleExpanded(record.accountId)"
              >
                <span
                  :class="{
                    'is-expanded': expandedKeys.includes(record.accountId),
                  }"
                >
                  ›
                </span>
              </button>
              <Checkbox
                :checked="selectedKeys.includes(record.accountId)"
                :disabled="String(record.usageStatus) !== '0'"
                :aria-label="`选择账户 ${record.accountName || record.fbAccountId}`"
                @change="
                  (event) =>
                    toggleRowSelection(
                      record.accountId,
                      Boolean(event.target.checked),
                    )
                "
              />
              <span
                class="account-name-text"
                :title="record.accountName || '-'"
              >
                {{ record.accountName || '-' }}
              </span>
              <span>{{ record.accountType || '-' }}</span>
              <span :title="String(record.fbAccountId || '-')">
                {{ record.fbAccountId || '-' }}
              </span>
              <span>${{ formatMoney(record.consumption) }}</span>
              <span>${{ formatMoney(record.balance) }}</span>
              <span>
                <Tag :color="accountStatusColor(record)">
                  {{ accountStatus(record) }}
                </Tag>
              </span>
              <span>
                <Tag :color="usageMeta(record.usageStatus).color">
                  {{ usageMeta(record.usageStatus).label }}
                </Tag>
              </span>
              <span :title="record.operatorName || '-'">
                {{ record.operatorName || '-' }}
              </span>
              <span
                class="flex items-center justify-end gap-2 whitespace-nowrap"
              >
                <Button
                  v-if="record.applicationId"
                  type="link"
                  @click="openApplicationDetail(record.applicationId)"
                >
                  查看申请单
                </Button>
                <Button danger type="link" @click="remove(record)">
                  删除
                </Button>
              </span>
            </div>
            <div
              v-if="expandedKeys.includes(record.accountId)"
              class="account-expanded-row"
            >
              <div class="expanded-account-details">
                <div
                  v-for="column in expandedColumns"
                  :key="String(column.dataIndex)"
                  class="expanded-detail-item"
                >
                  <span>{{ column.title }}</span>
                  <strong>{{
                    formatExpandedValue(record, String(column.dataIndex))
                  }}</strong>
                </div>
              </div>
            </div>
          </template>

          <div v-if="rows.length === 0 && !loading" class="account-list-empty">
            没有符合当前条件的广告账户
          </div>

          <div
            v-if="rows.length > 0"
            class="account-list-grid account-list-summary"
          >
            <span class="summary-label">合计</span>
            <span>/</span>
            <span>/</span>
            <span>/</span>
            <span>${{ formatMoney(stats.consumption) }}</span>
            <span>${{ formatMoney(stats.balance) }}</span>
            <span>/</span>
            <span>/</span>
            <span>/</span>
            <span>/</span>
          </div>
        </div>
      </Spin>
      <div class="pagination-row">
        <Pagination
          v-model:current="query.pageNum"
          v-model:page-size="query.pageSize"
          :page-size-options="['10', '50', '100', '500', '1000']"
          :show-total="showTotal"
          :total="total"
          show-size-changer
          show-quick-jumper
          @change="load"
        />
      </div>
    </Card>

    <BatchAccountModal
      ref="batchModal"
      :channel-id="channelId"
      @success="
        load();
        loadMetadata();
      "
    />
  </MediaResourcePage>
</template>

<style scoped>
.detail-heading {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  padding: 24px 28px;
  border: 1px solid hsl(var(--border));
  border-radius: 16px;
  background: hsl(var(--card));
  box-shadow: 0 6px 24px rgb(15 23 42 / 5%);
}

.back-button {
  color: #475569;
}

.channel-identity {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 14px;
}

.channel-mark {
  display: grid;
  width: 48px;
  height: 48px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid hsl(var(--border));
  border-radius: 14px;
  background: hsl(var(--muted));
  color: hsl(var(--foreground));
  font-size: 18px;
  font-weight: 750;
}

.identity-topline {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.identity-topline h1 {
  margin: 0;
  overflow: hidden;
  color: #0f172a;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.identity-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.identity-meta i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #cbd5e1;
}

.detail-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.detail-metrics article {
  display: flex;
  min-width: 0;
  align-items: flex-end;
  justify-content: space-between;
  padding: 17px 18px;
  border: 1px solid #e9eef5;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 3px 14px rgb(15 23 42 / 4%);
}

.metric-copy > span {
  color: #64748b;
  font-size: 12px;
}

.metric-copy > div {
  display: flex;
  align-items: baseline;
  gap: 3px;
  margin-top: 6px;
}

.metric-copy strong {
  color: #0f172a;
  font-size: 21px;
  font-variant-numeric: tabular-nums;
}

.metric-copy small {
  color: #64748b;
}

.metric-spark {
  display: flex;
  height: 30px;
  align-items: flex-end;
  gap: 3px;
  opacity: 0.72;
}

.metric-spark i {
  display: block;
  width: 4px;
  border-radius: 3px;
  background: #60a5fa;
}

.metric-spark i:nth-child(1) {
  height: 13px;
}
.metric-spark i:nth-child(2) {
  height: 22px;
}
.metric-spark i:nth-child(3) {
  height: 29px;
}
.metric-spark--2 i {
  background: #8b5cf6;
}
.metric-spark--3 i {
  background: #f97316;
}
.metric-spark--4 i {
  background: #10b981;
}

.detail-card {
  border: 1px solid #e9eef5;
  border-radius: 14px;
  box-shadow: 0 3px 16px rgb(15 23 42 / 4%);
}

.section-title-row,
.account-toolbar,
.selection-bar,
.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title-row {
  margin-bottom: 18px;
}
.section-title-row h2 {
  margin: 0;
  color: #0f172a;
  font-size: 16px;
  font-weight: 650;
}
.section-title-row p {
  margin: 3px 0 0;
  color: #94a3b8;
  font-size: 12px;
}

.channel-filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--adpulse-filter-row-gap) var(--adpulse-filter-column-gap);
  align-items: center;
}

.filter-control {
  width: 100%;
}

.filter-textarea {
  width: 100%;
  min-height: 36px;
  resize: vertical;
}

.account-toolbar {
  align-items: flex-start;
  justify-content: flex-end;
  gap: 16px;
  margin-bottom: 12px;
}

.account-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.selection-bar {
  justify-content: flex-start;
  gap: 10px;
  margin-bottom: 12px;
  padding: 9px 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--muted));
  color: hsl(var(--foreground));
  font-size: 12px;
}

.selection-hint {
  color: #64748b;
}

.column-panel {
  width: 260px;
  max-height: 420px;
  overflow: auto;
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 14px 34px rgb(15 23 42 / 14%);
}

.column-panel-title {
  margin-bottom: 12px;
  color: #334155;
  font-size: 13px;
  font-weight: 650;
}

.column-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 8px;
}

.account-list-scroll {
  max-height: 640px;
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.account-list-grid {
  display: grid;
  min-width: 1430px;
  grid-template-columns:
    48px 48px 240px minmax(110px, 0.75fr) minmax(160px, 1fr)
    minmax(130px, 0.85fr) minmax(130px, 0.85fr) minmax(110px, 0.75fr)
    minmax(120px, 0.8fr) minmax(140px, 0.9fr) 160px;
  align-items: center;
}

.account-list-header {
  position: sticky;
  z-index: 2;
  top: 0;
  min-height: 52px;
  border-bottom: 1px solid #dbe5f0;
  background: hsl(var(--muted));
  color: #475569;
  font-size: 12px;
  font-weight: 600;
}

.account-list-header > *,
.account-list-row > *,
.account-list-summary > * {
  min-width: 0;
  padding: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-list-header > :nth-child(1),
.account-list-header > :nth-child(2),
.account-list-row > :nth-child(1),
.account-list-row > :nth-child(2) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.account-list-row {
  min-height: 64px;
  border-bottom: 1px solid #edf1f6;
  background: #fff;
  color: #334155;
  font-size: 13px;
  transition: background-color 0.15s ease;
}

.account-list-row:hover {
  background: hsl(var(--accent));
}

.account-expand-button {
  display: grid;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 23px;
  place-items: center;
}

.account-expand-button:hover,
.account-expand-button:focus-visible {
  background: hsl(var(--accent));
  color: hsl(var(--foreground));
  outline: none;
}

.account-expand-button > span {
  line-height: 1;
  transform: translateY(-1px);
  transition: transform 0.2s ease;
}

.account-expand-button > .is-expanded {
  transform: rotate(90deg) translateX(-1px);
}

.account-expanded-row {
  min-width: 1360px;
  border-bottom: 1px solid #dbe5f0;
  background: #f8fafc;
}

.account-list-summary {
  min-height: 52px;
  background: #fbfcfe;
  color: #334155;
  font-size: 13px;
}

.summary-label {
  grid-column: 1 / 3;
  font-weight: 600;
}

.account-list-empty {
  display: grid;
  min-height: 160px;
  color: #94a3b8;
  font-size: 13px;
  place-items: center;
}

.expanded-account-details {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px 24px;
  padding: 8px 16px;
}

.expanded-detail-item {
  min-width: 0;
}

.expanded-detail-item > span {
  display: block;
  margin-bottom: 4px;
  color: #94a3b8;
  font-size: 12px;
}

.expanded-detail-item > strong {
  display: block;
  overflow: hidden;
  color: #334155;
  font-size: 13px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-name-text {
  display: block;
  width: 100%;
  overflow: hidden;
  color: #334155;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pagination-row {
  justify-content: flex-end;
  margin-top: 18px;
}

:global(.dark) .detail-heading {
  border-color: #263248;
  background: linear-gradient(120deg, #111827, #172033);
}
:global(.dark) .identity-topline h1,
:global(.dark) .metric-copy strong,
:global(.dark) .section-title-row h2 {
  color: #f8fafc;
}
:global(.dark) .detail-metrics article,
:global(.dark) .column-panel {
  border-color: #263248;
  background: #111827;
}
:global(.dark) .detail-card {
  border-color: #263248;
}

@media (max-width: 1100px) {
  .detail-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .account-toolbar {
    justify-content: flex-end;
  }
  .expanded-account-details {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .detail-heading {
    grid-template-columns: auto minmax(0, 1fr);
    padding: 18px;
  }
  .detail-heading > :last-child {
    display: none;
  }
  .channel-mark {
    display: none;
  }
  .identity-meta i,
  .identity-meta span:nth-of-type(n + 2) {
    display: none;
  }
  .detail-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .detail-metrics article {
    padding: 14px;
  }
  .selection-hint {
    display: none;
  }
  .expanded-account-details {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
