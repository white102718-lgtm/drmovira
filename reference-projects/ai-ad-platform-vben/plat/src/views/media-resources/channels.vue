<script lang="ts" setup>
import type { ChannelRecord } from '#/api/mpower';

import { computed, onMounted, reactive, ref, toRef } from 'vue';
import { useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';
import {
  Checkbox,
  CheckboxGroup,
  Form,
  FormItem,
  message,
  Modal,
  Pagination,
  RadioButton,
  RadioGroup,
  Select,
  Spin,
  Switch,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  deleteChannel,
  exportChannelAccounts,
  getChannelGoods,
  getChannelPage,
  getChannelPeriodSpend,
  getChannelSummary,
  getChannelTypePage,
  saveChannelGoods,
  setChannelPutaway,
  updateChannel,
} from '#/api/mpower';

import AccountTypeModal from './channel-management/components/AccountTypeModal.vue';
import AccountAttributeModal from './channel-management/components/AccountAttributeModal.vue';
import ImportFileModal from './channel-management/components/ImportFileModal.vue';
import RateSettingsModal from './channel-management/components/RateSettingsModal.vue';
import ShelfInfoModal from './channel-management/components/ShelfInfoModal.vue';
import TelegramModal from './channel-management/components/TelegramModal.vue';
import ChannelMigrationModal from './channel-management/components/ChannelMigrationModal.vue';
import {
  downloadBlob,
  formatMoney,
  TEAM_OPTIONS,
} from './channel-management/constants';
import MediaResourcePage from './components/MediaResourcePage.vue';
import {
  Button,
  Card,
  Dropdown,
  Input,
  Menu,
  MenuItem,
  Tag,
} from 'ant-design-vue';
import AntDataTable from '#/components/ui/AntDataTable.vue';
import DateRangePicker from '#/views/components/DateRangePicker.vue';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

type ChannelRow = ChannelRecord & Record<string, any>;
const router = useRouter();
const loading = ref(false);
const exporting = ref(false);
const rows = ref<ChannelRow[]>([]);
const total = ref(0);
const summary = ref<Record<string, any>>({});
const periodSpendError = ref(false);
const periodSpendTotal = ref<number | string | null>(null);
const refreshedAt = ref('');
const selectedKeys = ref<Array<number | string>>([]);
const expandedKeys = ref<Array<number | string>>([]);
const selectedRecords = new Map<string, ChannelRow>();
const rateModal = ref<InstanceType<typeof RateSettingsModal>>();
const importModal = ref<InstanceType<typeof ImportFileModal>>();
const accountTypeModal = ref<InstanceType<typeof AccountTypeModal>>();
const accountAttributeModal = ref<InstanceType<typeof AccountAttributeModal>>();
const shelfModal = ref<InstanceType<typeof ShelfInfoModal>>();
const telegramModal = ref<InstanceType<typeof TelegramModal>>();
const channelMigrationModal = ref<InstanceType<typeof ChannelMigrationModal>>();
const query = reactive({
  channelName: '',
  pageNum: 1,
  pageSize: 10,
  status: '1',
  tableType: 'Mpower',
});
function todayRange(): [number, number] {
  const today = dayjs(dayjs.tz().format('YYYY-MM-DD')).valueOf();
  return [today, today];
}
const spendDateRange = ref<[number, number]>(todayRange());
const appliedSpendDateRange = ref<[number, number]>([...spendDateRange.value]);
const routeState = createListRouteStateTarget({
  channel_name: toRef(query, 'channelName'),
  spend_date: appliedSpendDateRange,
  status: toRef(query, 'status'),
  table_type: toRef(query, 'tableType'),
});
const { commitQueryState, restoreFromRoute } = useListRouteState({
  onRouteStateRestored: async () => {
    spendDateRange.value = [...appliedSpendDateRange.value];
    await load();
  },
  pagination: {
    defaultPageSize: 10,
    page: toRef(query, 'pageNum'),
    pageSize: toRef(query, 'pageSize'),
    pageSizes: [10, 50, 100, 500, 1000],
  },
  state: routeState,
});
const isAccountType = computed(() => query.tableType === '账户类型');
const selectedRows = computed(
  () =>
    selectedKeys.value
      .map((key) => selectedRecords.get(String(key)))
      .filter(Boolean) as ChannelRow[],
);

const channelColumns: any[] = [
  { dataIndex: 'channelName', fixed: 'left', title: '渠道信息', width: 220 },
  { dataIndex: 'putawayStatus', fixed: 'left', title: '上架状态', width: 100 },
  { dataIndex: 'belongTeam', title: '所属团队', width: 110 },
  { dataIndex: 'channelShortName', title: '渠道简称', width: 140 },
  { dataIndex: 'channelCode', title: '渠道编码', width: 140 },
  { dataIndex: 'channelType', title: '渠道类型', width: 110 },
  { dataIndex: 'serviceFee', title: '服务费', width: 110 },
  { dataIndex: 'rebateRate', title: '返点/折扣', width: 120 },
  { dataIndex: 'settlementMethod', title: '结算方式/要求', width: 150 },
  { dataIndex: 'settlementCurrency', title: '结算货币', width: 110 },
  { dataIndex: 'buyoutAmount', title: '买断费', width: 120 },
  { dataIndex: 'totalConsumption', title: '账户总花费 ($)', width: 140 },
  { dataIndex: 'rechargeAmount', title: '充值金额', width: 120 },
  { dataIndex: 'totalBalance', title: '账户余额', width: 120 },
  { dataIndex: 'activationFee', title: '开户费 (￥)', width: 120 },
  { dataIndex: 'totalByBalance', title: '买户费 (￥)', width: 120 },
  { dataIndex: 'totalByBalanceU', title: '买户费 ($)', width: 120 },
  { dataIndex: 'usageStatus', title: '使用情况', width: 110 },
  { dataIndex: 'paymentAddress', title: '收款地址', width: 180 },
  { dataIndex: 'loginUrl', title: '登录/对接链接', width: 180 },
  { dataIndex: 'tgGroupName', title: 'Telegram 群组', width: 150 },
  { dataIndex: 'remark', title: '备注', width: 150 },
  { dataIndex: 'status', title: '状态', width: 100 },
  { dataIndex: 'createTime', title: '创建时间', width: 170 },
  { fixed: 'right', key: 'action', title: '操作', width: 220 },
];
const primaryChannelKeys = new Set([
  'belongTeam',
  'channelName',
  'channelType',
  'putawayStatus',
  'status',
  'totalBalance',
  'totalConsumption',
  'usageStatus',
]);
const channelListColumns = [
  { align: 'left' as const, key: 'select', title: '', width: 48 },
  ...[
    'channelName',
    'putawayStatus',
    'belongTeam',
    'channelType',
    'totalConsumption',
    'totalBalance',
    'usageStatus',
    'status',
  ].map((key) => {
    const column = channelColumns.find((item) => item.dataIndex === key)!;
    return {
      align: 'left' as const,
      dataIndex: key,
      key,
      title: column.title,
      width: column.width,
    };
  }),
  {
    align: 'left' as const,
    key: 'action',
    title: channelColumns.find((item) => item.key === 'action')!.title,
    width: 160,
  },
];
const accountTypeColumns = [
  {
    align: 'left' as const,
    dataIndex: 'accountType',
    key: 'accountType',
    title: '账户类型',
    width: 160,
  },
  {
    align: 'left' as const,
    dataIndex: 'subjectName',
    key: 'subjectName',
    title: '所属主体',
  },
  {
    align: 'left' as const,
    dataIndex: 'channelName',
    key: 'channelName',
    title: '渠道名称',
  },
  {
    align: 'left' as const,
    dataIndex: 'channelType',
    key: 'channelType',
    title: '渠道类型',
    width: 120,
  },
  {
    align: 'left' as const,
    dataIndex: 'totalConsumption',
    key: 'totalConsumption',
    title: '账户总花费 ($)',
    width: 170,
  },
  {
    align: 'left' as const,
    dataIndex: 'usageStatus',
    key: 'usageStatus',
    title: '使用情况',
    width: 140,
  },
];
const defaultVisibleKeys = [
  // 默认展开新增、编辑表单中的补充资料，避免必须手动勾选才能查看。
  'channelShortName',
  'channelCode',
  'settlementMethod',
  'buyoutAmount',
  'paymentAddress',
  'loginUrl',
  'remark',
  'channelName',
  'putawayStatus',
  'belongTeam',
  'channelType',
  'serviceFee',
  'rebateRate',
  'settlementCurrency',
  'totalConsumption',
  'rechargeAmount',
  'totalBalance',
  'usageStatus',
  'status',
  'createTime',
];
const visibleKeys = ref([...defaultVisibleKeys]);
const expandedColumns = computed(() => [
  { dataIndex: 'channelName', title: '渠道名称' },
  ...channelColumns.filter(
    (column) =>
      column.dataIndex &&
      !primaryChannelKeys.has(column.dataIndex) &&
      visibleKeys.value.includes(column.dataIndex),
  ),
]);
const summaryCards = computed(() => [
  {
    icon: 'lucide:radio-tower',
    iconClass: 'bg-blue-50 text-blue-700',
    label: '渠道数量',
    suffix: '个',
    value: summary.value.channelCount ?? total.value,
  },
  {
    icon: 'lucide:users-round',
    iconClass: 'bg-violet-50 text-violet-700',
    label: '关联账户',
    suffix: '个',
    value: summary.value.accountCount ?? 0,
  },
  {
    icon: 'lucide:chart-column-increasing',
    iconClass: 'bg-amber-50 text-amber-700',
    label: '累计账户总花费',
    prefix: '$',
    value: formatMoney(summary.value.totalConsumption),
  },
  {
    icon: 'lucide:circle-dollar-sign',
    iconClass: 'bg-emerald-50 text-emerald-700',
    label: '充值金额',
    prefix: '$',
    value: formatMoney(summary.value.rechargeAmount),
  },
  {
    icon: 'lucide:wallet',
    iconClass: 'bg-cyan-50 text-cyan-700',
    label: '账户余额',
    prefix: '$',
    value: formatMoney(summary.value.totalBalance),
  },
]);
const allCurrentRowsSelected = computed(
  () =>
    rows.value.length > 0 &&
    rows.value.every((record) => selectedKeys.value.includes(record.id)),
);
const someCurrentRowsSelected = computed(
  () =>
    !allCurrentRowsSelected.value &&
    rows.value.some((record) => selectedKeys.value.includes(record.id)),
);

function buildParams() {
  return {
    ...query,
    belongTeam: isAccountType.value ? undefined : query.tableType,
    fbadChannel: query.channelName || undefined,
  };
}

function buildPeriodSpendParams() {
  const [start, end] = appliedSpendDateRange.value;
  return {
    ...buildParams(),
    endDate: dayjs(end).format('YYYY-MM-DD'),
    startDate: dayjs(start).format('YYYY-MM-DD'),
  };
}

function formatPeriodSpend(value: unknown) {
  return value === null || value === undefined
    ? '--'
    : `$${formatMoney(value)}`;
}

async function load() {
  await commitQueryState();
  loading.value = true;
  try {
    const params = buildParams();
    if (isAccountType.value) {
      const response: any = await getChannelTypePage(params);
      rows.value = response.data?.records ?? response.rows ?? [];
      total.value = response.data?.count ?? response.total ?? 0;
      summary.value = {};
      periodSpendError.value = false;
      periodSpendTotal.value = null;
    } else {
      const [pageResult, summaryResult, periodSpendResult] =
        await Promise.allSettled([
          getChannelPage(params),
          getChannelSummary(params),
          getChannelPeriodSpend(buildPeriodSpendParams()),
        ]);
      if (pageResult.status === 'rejected') throw pageResult.reason;
      if (summaryResult.status === 'rejected') throw summaryResult.reason;
      const response: any = pageResult.value;
      const summaryResponse: any = summaryResult.value;
      rows.value = response.data?.records ?? response.rows ?? [];
      total.value = response.data?.count ?? response.total ?? 0;
      summary.value = summaryResponse.data ?? {};
      if (periodSpendResult.status === 'fulfilled') {
        const periodSpend = periodSpendResult.value;
        const spendByChannel = new Map(
          periodSpend.items.map((item) => [
            String(item.channelId),
            item.totalConsumption,
          ]),
        );
        rows.value = rows.value.map((record) => ({
          ...record,
          totalConsumption: spendByChannel.get(String(record.id)) ?? 0,
        }));
        periodSpendTotal.value = periodSpend.totalConsumption;
        periodSpendError.value = false;
      } else {
        rows.value = rows.value.map((record) => ({
          ...record,
          totalConsumption: null,
        }));
        periodSpendTotal.value = null;
        periodSpendError.value = true;
      }
    }
    refreshedAt.value = dayjs().format('HH:mm:ss');
  } finally {
    loading.value = false;
  }
}
function search() {
  query.pageNum = 1;
  appliedSpendDateRange.value = [...spendDateRange.value];
  clearSelection();
  void load();
}
function reset() {
  query.channelName = '';
  query.status = '1';
  query.pageNum = 1;
  spendDateRange.value = todayRange();
  appliedSpendDateRange.value = [...spendDateRange.value];
  clearSelection();
  void load();
}
function clearSelection() {
  selectedKeys.value = [];
  selectedRecords.clear();
}
function showTotal(value: number) {
  return `共 ${value} 条`;
}
function toggleExpanded(id: number | string) {
  expandedKeys.value = expandedKeys.value.includes(id)
    ? expandedKeys.value.filter((key) => key !== id)
    : [...expandedKeys.value, id];
}
function toggleSelection(record: Record<string, any>, checked: boolean) {
  if (record.id === undefined || record.id === null) return;
  const channelRecord = record as ChannelRow;
  if (checked) selectedRecords.set(String(channelRecord.id), channelRecord);
  else selectedRecords.delete(String(record.id));
  selectedKeys.value = checked
    ? [...new Set([channelRecord.id, ...selectedKeys.value])]
    : selectedKeys.value.filter((key) => key !== channelRecord.id);
}
function toggleCurrentPageSelection(checked: boolean) {
  const currentIds = rows.value.map((record) => record.id);
  rows.value.forEach((record) => {
    if (checked) selectedRecords.set(String(record.id), record);
    else selectedRecords.delete(String(record.id));
  });
  selectedKeys.value = checked
    ? [...new Set([...currentIds, ...selectedKeys.value])]
    : selectedKeys.value.filter((key) => !currentIds.includes(key));
}
function formatExpandedValue(record: ChannelRow, dataIndex: string) {
  const value = record[dataIndex];
  if (value === null || value === undefined || value === '') return '-';
  if (dataIndex === 'buyoutAmount') {
    return record.settlementMethod === '买断' ? formatMoney(value) : '-';
  }
  if (['activationFee', 'totalByBalance'].includes(dataIndex)) {
    return `￥${formatMoney(value)}`;
  }
  if (['rechargeAmount', 'totalByBalanceU'].includes(dataIndex)) {
    return `$${formatMoney(value)}`;
  }
  if (['rebateRate', 'serviceFee'].includes(dataIndex)) {
    return value === null || value === undefined ? '-' : `${value}%`;
  }
  return value ?? '-';
}
function openDetail(record: any) {
  void router.push({
    path: `/media-resources/channels/${record.id}`,
    query: {
      accountType: record.accountType || undefined,
      channelName: record.channelName,
    },
  });
}
function changeStatus(record: any, checked: boolean) {
  Modal.confirm({
    content: `确认${checked ? '启用' : '停用'}渠道“${record.channelName}”吗？`,
    title: '修改渠道状态',
    async onOk() {
      await updateChannel({ id: record.id, status: checked ? '1' : '0' });
      record.status = checked ? '1' : '0';
      message.success(`渠道已${checked ? '启用' : '停用'}`);
    },
  });
}
function remove(record: any) {
  Modal.confirm({
    content: `是否确认删除渠道“${record.channelName}”？`,
    okButtonProps: { danger: true },
    title: '删除渠道',
    async onOk() {
      await deleteChannel(record.id);
      message.success('删除成功');
      await load();
    },
  });
}
async function shelf(record: any) {
  const response = await getChannelGoods(record.id);
  if (!response.data) {
    await saveChannelGoods({
      channelId: record.id,
      goodsName: '-',
      launchRegion: '',
      minBugLimit: 1,
      rebateRate: 0,
      remark: '',
      serviceFeeRatio: 0,
      stockNum: 9999,
      timezone: '',
    });
  }
  await setChannelPutaway({ channelId: record.id, putawayStatus: 1 });
  message.success('上架成功');
  await load();
}
function unshelf(record: any) {
  Modal.confirm({
    content: `确认下架渠道“${record.channelName}”吗？`,
    title: '下架渠道',
    async onOk() {
      await setChannelPutaway({ channelId: record.id, putawayStatus: 2 });
      message.success('下架成功');
      await load();
    },
  });
}
async function exportSelected() {
  if (selectedRows.value.length === 0) return;
  exporting.value = true;
  const failed: string[] = [];
  const sheets = new Map<string, any[][]>();
  const spendDate = dayjs().format('YYYY-MM-DD');
  try {
    // Excel 解析库仅用于批量导出，按操作加载可显著缩小页面首个脚本。
    const XLSX = await import('xlsx');
    await Promise.all(
      selectedRows.value.map(async (channel) => {
        try {
          const result = await exportChannelAccounts({
            channelId: channel.id,
            consumptionMin: 0.01,
            displayType: '1',
            endDate: spendDate,
            pageNum: 1,
            pageSize: 99_999_999,
            startDate: spendDate,
          });
          const blob =
            result instanceof Blob
              ? result
              : new Blob([(result as any).data ?? result]);
          const workbook = XLSX.read(await blob.arrayBuffer(), {
            type: 'array',
          });
          const sheet = workbook.Sheets[workbook.SheetNames[0]!];
          sheets.set(
            String(channel.id),
            XLSX.utils.sheet_to_json(sheet!, {
              blankrows: false,
              defval: '',
              header: 1,
            }),
          );
        } catch {
          failed.push(channel.channelName ?? String(channel.id));
        }
      }),
    );
    const merged: any[][] = [];
    selectedRows.value.forEach((channel) => {
      const data = sheets.get(String(channel.id));
      if (!data?.length) return;
      if (merged.length === 0) merged.push(['渠道名称', ...(data[0] ?? [])]);
      data
        .slice(1)
        .forEach((line) => merged.push([channel.channelName, ...line]));
    });
    if (merged.length === 0) {
      message.error('所有渠道导出失败');
      return;
    }
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(
      workbook,
      XLSX.utils.aoa_to_sheet(merged),
      '明细汇总',
    );
    const output = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
    downloadBlob(
      new Blob([output], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
      `渠道明细汇总_${dayjs().format('YYYY-MM-DD')}.xlsx`,
    );
    if (failed.length > 0)
      message.warning(`以下渠道导出失败：${failed.join('、')}`);
    else message.success('导出成功');
    clearSelection();
  } finally {
    exporting.value = false;
  }
}
onMounted(async () => {
  await restoreFromRoute();
  spendDateRange.value = [...appliedSpendDateRange.value];
  await load();
});
</script>

<template>
  <MediaResourcePage content-class="!p-4">
    <header class="channel-page-header">
      <div class="channel-page-header__identity">
        <span aria-hidden="true" class="channel-page-header__icon">
          <IconifyIcon icon="lucide:radio-tower" />
        </span>
        <div class="min-w-0">
          <h1>渠道管理</h1>
          <p>统一管理渠道资料、费率配置、上架状态及关联广告账户。</p>
        </div>
      </div>
      <div aria-live="polite" class="channel-page-header__status">
        <span class="bg-success size-2 rounded-full"></span>
        <span>{{
          refreshedAt ? `数据更新于 ${refreshedAt}` : '正在获取最新数据'
        }}</span>
      </div>
    </header>

    <section v-if="!isAccountType" class="metrics-grid">
      <article
        v-for="item in summaryCards"
        :key="item.label"
        class="metric-card"
      >
        <div :class="item.iconClass" class="metric-icon">
          <IconifyIcon :icon="item.icon" aria-hidden="true" class="text-xl" />
        </div>
        <div class="min-w-0">
          <div class="metric-label">{{ item.label }}</div>
          <div class="metric-value">
            <small v-if="item.prefix">{{ item.prefix }}</small>
            <strong>{{ item.value }}</strong>
            <small v-if="item.suffix">{{ item.suffix }}</small>
          </div>
        </div>
      </article>
    </section>

    <Card
      class="section-card filter-card"
      :body-style="{ padding: '16px' }"
      :bordered="false"
    >
      <Form class="channel-filter ux-filter-form" layout="vertical">
        <FormItem class="ux-filter-field" label="渠道名称">
          <Input
            v-model:value="query.channelName"
            class="filter-control"
            placeholder="输入名称或简称"
            allow-clear
            @press-enter="search"
          />
        </FormItem>
        <FormItem class="ux-filter-field" label="状态">
          <Select
            v-model:value="query.status"
            :options="[
              { label: '正常', value: '1' },
              { label: '停用', value: '0' },
            ]"
            class="filter-control"
            placeholder="全部状态"
            allow-clear
          />
        </FormItem>
        <FormItem
          v-if="!isAccountType"
          class="date-filter-item ux-filter-field ux-filter-field-wide"
          label="花费周期"
        >
          <DateRangePicker
            v-model:value="spendDateRange"
            :clearable="false"
            width="100%"
          />
        </FormItem>
        <div class="filter-actions ux-filter-actions">
          <Button type="primary" @click="search">查询</Button>
          <Button @click="reset">重置</Button>
        </div>
      </Form>
    </Card>

    <Card
      class="section-card table-card"
      :body-style="{ padding: '16px' }"
      :bordered="false"
    >
      <div class="table-toolbar">
        <div class="min-w-0">
          <RadioGroup
            v-model:value="query.tableType"
            button-style="solid"
            @change="search"
          >
            <RadioButton
              v-for="team in TEAM_OPTIONS"
              :key="team.value"
              :value="team.value"
            >
              {{ team.label }}
            </RadioButton>
            <RadioButton value="账户类型">账户类型</RadioButton>
          </RadioGroup>
          <div class="table-result-meta">
            当前共 <strong>{{ total }}</strong> 条结果
            <template v-if="selectedKeys.length > 0">
              · 已选择 <strong>{{ selectedKeys.length }}</strong> 个渠道
              <Button type="link" @click="clearSelection"> 取消选择 </Button>
            </template>
          </div>
        </div>
        <div class="toolbar-actions">
          <Button
            v-if="!isAccountType"
            type="primary"
            @click="router.push('/media-resources/channels/create')"
          >
            添加渠道
          </Button>
          <Dropdown>
            <Button>更多操作</Button>
            <template #overlay>
              <Menu>
                <MenuItem @click="accountTypeModal?.show()">
                  账户类型管理
                </MenuItem>
                <MenuItem @click="accountAttributeModal?.show()">
                  账户属性管理
                </MenuItem>
                <MenuItem @click="importModal?.show()">批量导入账户</MenuItem>
                <MenuItem
                  v-if="!isAccountType"
                  @click="channelMigrationModal?.show()"
                >
                  渠道与账户同步
                </MenuItem>
                <MenuItem
                  v-if="!isAccountType"
                  :disabled="selectedKeys.length === 0 || exporting"
                  @click="exportSelected"
                >
                  导出已选明细
                </MenuItem>
              </Menu>
            </template>
          </Dropdown>
          <Dropdown v-if="!isAccountType" trigger="click">
            <Button>自定义列</Button>
            <template #overlay>
              <div class="column-panel">
                <div class="column-panel__header">
                  <strong>展开区域显示字段</strong>
                  <Button
                    type="link"
                    @click="visibleKeys = [...defaultVisibleKeys]"
                  >
                    恢复默认
                  </Button>
                </div>
                <CheckboxGroup
                  v-model:value="visibleKeys"
                  :options="
                    channelColumns
                      .filter(
                        (item) =>
                          item.dataIndex &&
                          !primaryChannelKeys.has(item.dataIndex),
                      )
                      .map((item) => ({
                        label: item.title,
                        value: item.dataIndex,
                      }))
                  "
                  class="column-options"
                />
              </div>
            </template>
          </Dropdown>
          <Button @click="load">刷新</Button>
        </div>
      </div>

      <div
        v-if="!isAccountType && periodSpendError"
        class="period-spend-alert"
        role="alert"
      >
        所选周期花费暂不可用，渠道资料仍可正常查看，请稍后重试。
      </div>

      <Spin :spinning="loading">
        <AntDataTable
          v-if="isAccountType"
          :columns="accountTypeColumns"
          :data="rows"
          :loading="loading"
          :paginate="false"
          row-key="id"
        >
          <template #cell-accountType="{ record }">
            <Button
              class="cell-link ux-table-link"
              type="link"
              @click="openDetail(record)"
            >
              {{ record.accountType || '-' }}
            </Button>
          </template>
          <template #cell-channelType="{ record }">
            {{ Number(record.channelType) === 1 ? '代理商' : '号商' }}
          </template>
          <template #cell-totalConsumption="{ record }">
            <span class="money-cell"
              >${{ formatMoney(record.totalConsumption) }}</span
            >
          </template>
        </AntDataTable>

        <div v-else-if="false" class="channel-list-scroll">
          <div class="account-type-grid list-header">
            <span>账户类型</span><span>所属主体</span><span>渠道名称</span>
            <span>渠道类型</span>
            <span>账户总花费 ($)</span>
            <span>使用情况</span>
          </div>
          <div
            v-for="record in rows"
            :key="record.id"
            class="account-type-grid list-row"
          >
            <Button class="cell-link" type="link" @click="openDetail(record)">
              {{ record.accountType || '-' }}
            </Button>
            <span>{{ record.subjectName || '-' }}</span>
            <span>{{ record.channelName || '-' }}</span>
            <span>{{
              Number(record.channelType) === 1 ? '代理商' : '号商'
            }}</span>
            <span class="money-cell">
              ${{ formatMoney(record.totalConsumption) }}
            </span>
            <span>{{ record.usageStatus ?? '-' }}</span>
          </div>
          <div v-if="rows.length === 0 && !loading" class="list-empty">
            没有符合当前条件的渠道数据
          </div>
        </div>

        <div v-else-if="false" class="channel-list-scroll">
          <div class="channel-list-grid list-header">
            <span></span>
            <Checkbox
              :checked="allCurrentRowsSelected"
              :indeterminate="someCurrentRowsSelected"
              aria-label="选择当前页全部渠道"
              @change="
                (event) =>
                  toggleCurrentPageSelection(Boolean(event.target.checked))
              "
            />
            <span>渠道信息</span><span>上架状态</span><span>所属团队</span>
            <span>渠道类型</span><span>账户总花费 ($)</span
            ><span>账户余额</span> <span>使用情况</span><span>状态</span
            ><span>操作</span>
          </div>
          <template v-for="record in rows" :key="record.id">
            <div class="channel-list-grid list-row">
              <button
                :aria-expanded="expandedKeys.includes(record.id)"
                class="list-expand-button"
                type="button"
                @click="toggleExpanded(record.id)"
              >
                <span
                  :class="{ 'is-expanded': expandedKeys.includes(record.id) }"
                >
                  ›
                </span>
              </button>
              <Checkbox
                :checked="selectedKeys.includes(record.id)"
                :aria-label="`选择渠道 ${record.channelName || record.id}`"
                @change="
                  (event) =>
                    toggleSelection(record, Boolean(event.target.checked))
                "
              />
              <button
                class="channel-name-button ux-table-link"
                type="button"
                @click="openDetail(record)"
              >
                {{ record.channelName || '-' }}
              </button>
              <span>
                <Tag
                  :color="
                    record.putawayStatus === 1
                      ? 'success'
                      : record.putawayStatus === 2
                        ? 'error'
                        : 'default'
                  "
                >
                  {{
                    record.putawayStatus === 1
                      ? '已上架'
                      : record.putawayStatus === 2
                        ? '已下架'
                        : '未上架'
                  }}
                </Tag>
              </span>
              <span>{{ record.belongTeam || '-' }}</span>
              <span>{{
                Number(record.channelType) === 1 ? '代理商' : '号商'
              }}</span>
              <span class="money-cell">
                {{ formatPeriodSpend(record.totalConsumption) }}
              </span>
              <span class="money-cell">
                ${{ formatMoney(record.totalBalance) }}
              </span>
              <span>{{ record.usageStatus ?? '-' }}</span>
              <span>
                <Switch
                  :checked="String(record.status) === '1'"
                  checked-children="正常"
                  un-checked-children="停用"
                  @change="(checked) => changeStatus(record, checked === true)"
                />
              </span>
              <div class="row-actions">
                <Button type="link" @click="openDetail(record)">详情</Button>
                <Dropdown>
                  <Button type="link">更多</Button>
                  <template #overlay>
                    <Menu>
                      <MenuItem
                        v-if="record.putawayStatus !== 1"
                        @click="shelf(record)"
                      >
                        上架
                      </MenuItem>
                      <MenuItem v-else danger @click="unshelf(record)">
                        下架
                      </MenuItem>
                      <MenuItem @click="shelfModal?.show(record)">
                        上架信息
                      </MenuItem>
                      <MenuItem
                        @click="
                          router.push(
                            `/media-resources/channels/${record.id}/edit`,
                          )
                        "
                      >
                        编辑渠道
                      </MenuItem>
                      <MenuItem @click="telegramModal?.show(record)">
                        设置 Telegram 群组
                      </MenuItem>
                      <MenuItem @click="rateModal?.show(record)">
                        费率设置
                      </MenuItem>
                      <MenuItem danger @click="remove(record)">
                        删除渠道
                      </MenuItem>
                    </Menu>
                  </template>
                </Dropdown>
              </div>
            </div>
            <div
              v-if="expandedKeys.includes(record.id)"
              class="channel-expanded-row"
            >
              <div class="expanded-channel-details">
                <div
                  v-for="column in expandedColumns"
                  :key="column.dataIndex"
                  class="expanded-channel-item"
                >
                  <span>{{ column.title }}</span>
                  <strong>{{
                    formatExpandedValue(record, column.dataIndex)
                  }}</strong>
                </div>
              </div>
            </div>
          </template>
          <div v-if="rows.length === 0 && !loading" class="list-empty">
            没有符合当前条件的渠道数据
          </div>
          <div v-if="rows.length > 0" class="channel-list-grid list-summary">
            <strong class="summary-label">合计</strong>
            <span>-</span><span>-</span><span>-</span><span>-</span>
            <span>{{ formatPeriodSpend(periodSpendTotal) }}</span>
            <span>${{ formatMoney(summary.totalBalance) }}</span>
            <span>-</span><span>-</span><span>-</span>
          </div>
        </div>
        <AntDataTable
          v-else
          :columns="channelListColumns"
          :data="rows"
          :loading="loading"
          :paginate="false"
          row-key="id"
        >
          <template #header-select>
            <Checkbox
              :checked="allCurrentRowsSelected"
              :indeterminate="someCurrentRowsSelected"
              aria-label="选择当前页全部渠道"
              @change="
                (event) =>
                  toggleCurrentPageSelection(Boolean(event.target.checked))
              "
            />
          </template>
          <template #cell-select="{ record }">
            <Checkbox
              :checked="selectedKeys.includes(record.id)"
              :aria-label="`选择渠道 ${record.channelName || record.id}`"
              @change="
                (event) =>
                  toggleSelection(record, Boolean(event.target.checked))
              "
            />
          </template>
          <template #cell-channelName="{ record }">
            <button
              class="channel-name-button ux-table-link"
              type="button"
              @click="openDetail(record)"
            >
              {{ record.channelName || '-' }}
            </button>
          </template>
          <template #cell-putawayStatus="{ record }">
            <Tag
              :color="
                record.putawayStatus === 1
                  ? 'success'
                  : record.putawayStatus === 2
                    ? 'error'
                    : 'default'
              "
            >
              {{
                record.putawayStatus === 1
                  ? '已上架'
                  : record.putawayStatus === 2
                    ? '已下架'
                    : '未上架'
              }}
            </Tag>
          </template>
          <template #cell-channelType="{ record }">
            {{ Number(record.channelType) === 1 ? '代理商' : '号商' }}
          </template>
          <template #cell-totalConsumption="{ record }">
            <span class="money-cell">{{
              formatPeriodSpend(record.totalConsumption)
            }}</span>
          </template>
          <template #cell-totalBalance="{ record }">
            <span class="money-cell"
              >${{ formatMoney(record.totalBalance) }}</span
            >
          </template>
          <template #cell-status="{ record }">
            <Switch
              :checked="String(record.status) === '1'"
              checked-children="正常"
              un-checked-children="停用"
              @change="(checked) => changeStatus(record, checked === true)"
            />
          </template>
          <template #cell-action="{ record }">
            <div class="row-actions">
              <Button type="link" @click="openDetail(record)">详情</Button>
              <Dropdown>
                <Button type="link">更多</Button>
                <template #overlay>
                  <Menu>
                    <MenuItem
                      v-if="record.putawayStatus !== 1"
                      @click="shelf(record)"
                    >
                      上架
                    </MenuItem>
                    <MenuItem v-else danger @click="unshelf(record)"
                      >下架</MenuItem
                    >
                    <MenuItem @click="shelfModal?.show(record)"
                      >上架信息</MenuItem
                    >
                    <MenuItem
                      @click="
                        router.push(
                          `/media-resources/channels/${record.id}/edit`,
                        )
                      "
                    >
                      编辑渠道
                    </MenuItem>
                    <MenuItem @click="telegramModal?.show(record)"
                      >设置 Telegram 群组</MenuItem
                    >
                    <MenuItem @click="rateModal?.show(record)"
                      >费率设置</MenuItem
                    >
                    <MenuItem danger @click="remove(record)">删除渠道</MenuItem>
                  </Menu>
                </template>
              </Dropdown>
            </div>
          </template>
          <template #row-after="{ record }">
            <div class="expanded-channel-details">
              <div
                v-for="column in expandedColumns"
                :key="column.dataIndex"
                class="expanded-channel-item"
              >
                <span>{{ column.title }}</span>
                <strong>{{
                  formatExpandedValue(record, column.dataIndex)
                }}</strong>
              </div>
            </div>
          </template>
          <template #footer>
            <div v-if="rows.length > 0" class="table-summary-bar">
              <strong>合计</strong>
              <span
                >所选周期总花费：{{ formatPeriodSpend(periodSpendTotal) }}</span
              >
              <span>总余额：${{ formatMoney(summary.totalBalance) }}</span>
            </div>
          </template>
        </AntDataTable>
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

    <RateSettingsModal ref="rateModal" @success="load" />
    <ImportFileModal ref="importModal" @success="search" />
    <AccountTypeModal ref="accountTypeModal" />
    <AccountAttributeModal ref="accountAttributeModal" />
    <ShelfInfoModal ref="shelfModal" @success="load" />
    <TelegramModal ref="telegramModal" @success="load" />
    <ChannelMigrationModal ref="channelMigrationModal" @success="load" />
  </MediaResourcePage>
</template>

<style scoped>
.channel-page-header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: hsl(var(--card));
  border-radius: var(--adpulse-card-radius);
  box-shadow: var(--adpulse-card-shadow);
}

.channel-page-header__identity {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
}

.channel-page-header__icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: none;
  place-items: center;
  border-radius: 10px;
  background: hsl(var(--muted));
  color: hsl(var(--foreground));
  font-size: 20px;
}

.channel-page-header h1 {
  margin: 0;
  color: hsl(var(--foreground));
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
}

.channel-page-header p {
  margin: 2px 0 0;
  color: hsl(var(--muted-foreground));
  font-size: 14px;
  line-height: 20px;
}

.channel-page-header__status {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
  color: hsl(var(--muted-foreground));
  font-size: 14px;
}

@media (max-width: 640px) {
  .channel-page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .channel-page-header__status {
    flex: initial;
  }
}

.page-heading {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  overflow: hidden;
  padding: 26px 30px;
  border: 1px solid hsl(var(--border));
  border-radius: 16px;
  background: hsl(var(--card));
  box-shadow: 0 6px 24px rgb(15 23 42 / 5%);
}

.page-heading::after {
  position: absolute;
  right: -45px;
  bottom: -72px;
  width: 190px;
  height: 190px;
  border: 34px solid hsl(var(--muted));
  border-radius: 999px;
  content: '';
}

.eyebrow {
  margin-bottom: 6px;
  color: #18181b;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.page-heading h1 {
  margin: 0;
  color: #0f172a;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.page-heading p {
  margin: 7px 0 0;
  color: #64748b;
  font-size: 14px;
}

.heading-meta {
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgb(226 232 240 / 80%);
  border-radius: 999px;
  background: rgb(255 255 255 / 78%);
  color: #64748b;
  font-size: 12px;
  backdrop-filter: blur(8px);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 0 4px rgb(16 185 129 / 12%);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
}

.metric-card {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 13px;
  padding: 18px;
  border: 1px solid #e9eef5;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 3px 14px rgb(15 23 42 / 4%);
}

.metric-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 12px;
}

.metric-label {
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-value {
  display: flex;
  align-items: baseline;
  gap: 3px;
  margin-top: 5px;
  color: #0f172a;
}

.metric-value strong {
  overflow: hidden;
  font-size: 21px;
  font-variant-numeric: tabular-nums;
  text-overflow: ellipsis;
}

.metric-value small {
  color: #64748b;
  font-size: 12px;
}

.section-card {
  border: 1px solid #e9eef5;
  border-radius: 14px;
  box-shadow: 0 3px 16px rgb(15 23 42 / 4%);
}

.table-toolbar,
.column-panel__header,
.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.channel-filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--adpulse-filter-row-gap) var(--adpulse-filter-column-gap);
}

.date-filter-item {
  margin-bottom: 0;
}

.filter-control {
  width: 100%;
}

.period-spend-alert {
  margin-bottom: 16px;
  padding: 10px 12px;
  border: 1px solid hsl(var(--warning) / 35%);
  border-radius: var(--radius);
  color: hsl(var(--foreground));
  background: hsl(var(--warning) / 8%);
  font-size: 13px;
}

.table-toolbar {
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.table-result-meta {
  margin-top: 9px;
  color: #94a3b8;
  font-size: 12px;
}

.table-result-meta strong {
  color: #334155;
}

.toolbar-actions,
.row-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.row-actions {
  flex-wrap: nowrap;
  gap: 0;
}
.column-panel {
  width: 280px;
  max-height: 420px;
  overflow: auto;
  padding: 14px;
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 14px 34px rgb(15 23 42 / 14%);
}

.column-panel__header {
  margin-bottom: 12px;
}
.column-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 8px;
}

.channel-list-scroll {
  max-height: 640px;
  overflow: auto;
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.channel-list-grid,
.account-type-grid {
  display: grid;
  min-width: 1320px;
  align-items: center;
}

.channel-list-grid {
  grid-template-columns:
    48px 48px 220px minmax(100px, 0.7fr) minmax(120px, 0.9fr)
    minmax(100px, 0.7fr) minmax(130px, 0.9fr) minmax(120px, 0.85fr)
    minmax(100px, 0.75fr) 110px 150px;
}

.account-type-grid {
  grid-template-columns: 160px 1fr 1fr 120px 170px 140px;
}

.list-header {
  position: sticky;
  z-index: 2;
  top: 0;
  min-height: var(--adpulse-table-header-height);
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  font-weight: 600;
}

.list-header > *,
.list-row > *,
.list-summary > * {
  min-width: 0;
  padding: var(--adpulse-table-cell-padding-block)
    var(--adpulse-table-cell-padding-inline);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.channel-list-grid > :nth-child(1),
.channel-list-grid > :nth-child(2) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.list-row {
  min-height: var(--adpulse-table-row-height);
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--card));
  color: hsl(var(--foreground));
  font-size: 13px;
}

.list-row:hover {
  background: hsl(var(--muted));
}

.list-expand-button {
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

.list-expand-button > span {
  line-height: 1;
  transition: transform 0.2s ease;
}

.list-expand-button > .is-expanded {
  transform: rotate(90deg);
}

.channel-name-button {
  padding: 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  color: hsl(var(--primary));
  cursor: pointer;
  font-weight: 600;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.channel-expanded-row {
  min-width: 1320px;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--muted));
}

.expanded-channel-details {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px 24px;
  padding: 20px 24px;
}

.expanded-channel-item {
  min-width: 0;
}

.expanded-channel-item > span,
.expanded-channel-item > strong {
  display: block;
}

.expanded-channel-item > span {
  margin-bottom: 4px;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
}

.expanded-channel-item > strong {
  color: hsl(var(--foreground));
  font-size: 13px;
  font-weight: 500;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.list-summary {
  min-height: var(--adpulse-table-row-height);
  background: hsl(var(--muted) / 55%);
}

.list-summary .summary-label {
  grid-column: 1 / 3;
}

.list-empty {
  display: grid;
  min-height: 160px;
  color: #94a3b8;
  font-size: 13px;
  place-items: center;
}

.cell-link {
  height: auto;
  max-width: 150px;
  padding: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.channel-code {
  max-width: 150px;
  margin-top: 2px;
  overflow: hidden;
  color: #94a3b8;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.money-cell {
  color: #0f172a;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

.external-link {
  white-space: nowrap;
}
.pagination-row {
  justify-content: flex-end;
  margin-top: 18px;
}

:global(.dark) .page-heading {
  border-color: #263248;
  background: linear-gradient(120deg, #111827, #172033);
}
:global(.dark) .page-heading h1,
:global(.dark) .metric-value {
  color: #f8fafc;
}
:global(.dark) .metric-card,
:global(.dark) .column-panel {
  border-color: #263248;
  background: #111827;
}
:global(.dark) .section-card {
  border-color: #263248;
}

@media (max-width: 1200px) {
  .metrics-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .table-toolbar {
    flex-direction: column;
  }
  .toolbar-actions {
    width: 100%;
  }
  .expanded-channel-details {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .page-heading {
    min-height: auto;
    align-items: flex-start;
    padding: 20px;
  }
  .heading-meta {
    display: none;
  }
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .metric-card {
    padding: 14px;
  }
  .channel-filter {
    flex-direction: column;
    align-items: stretch;
  }

  /* DateRangePicker 写入内联宽度，窄屏下需覆盖为当前字段的可用宽度。 */

  .expanded-channel-details {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
