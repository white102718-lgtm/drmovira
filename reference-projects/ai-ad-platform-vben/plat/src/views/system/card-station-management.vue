<script setup lang="ts">
/* eslint-disable vue/html-closing-bracket-newline, vue/multiline-html-element-content-newline */
import type { TableColumnsType } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import type {
  ArrivalxCard,
  CardPlatform,
  CardStationBalance,
  CardStationLimitRule,
  PhotonPayCard,
} from '#/api/card-station';

import { computed, onMounted, reactive, ref, toRefs, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Checkbox,
  DatePicker,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Radio,
  Select,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  exportCardStationCards,
  getCardStationBalance,
  getCardStationCards,
  getCardStationDetail,
  getCardStationLimitRecords,
  getCardStationLimitRule,
  getCardStationStatistics,
  setCardStationBatchLimit,
  syncCardStation,
  updateCardStationAutoAdjust,
  updateCardStationLimitRule,
  updateCardStationStatus,
} from '#/api/card-station';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';

defineOptions({ name: 'CardStationManagement' });

type CardStationTab = 'limit-rule' | CardPlatform;
type LimitPeriodPreset = 7 | 15 | 'custom';

const activeTab = ref<CardStationTab>('photonpay');
const activePlatform = computed<CardPlatform>(() =>
  activeTab.value === 'arrivalx' ? 'arrivalx' : 'photonpay',
);
const loading = ref(false);
const loadError = ref('');
const rows = ref<Array<ArrivalxCard | PhotonPayCard>>([]);
const total = ref(0);
const selectedRowKeys = ref<Array<number | string>>([]);
const balanceItems = ref<CardStationBalance[]>([]);
const statistics = reactive({ active: 0, balance: 0, frozen: 0, total: 0 });
const query = reactive({
  cardId: '',
  cardNo: '',
  keyword: '',
  onlyZero: false,
  pageNum: 1,
  pageSize: 10,
  status: '',
  timeRange: undefined as [Dayjs, Dayjs] | undefined,
});
const queryRefs = toRefs(query);
const routeStateReady = ref(false);
const { commitQueryState, restoreFromRoute } = useListRouteState({
  fields: {
    tab: {
      always: true,
      codec: {
        parse(value) {
          const tab = Array.isArray(value) ? value[0] : value;
          return ['arrivalx', 'limit-rule', 'photonpay'].includes(tab ?? '')
            ? (tab as CardStationTab)
            : undefined;
        },
        serialize: (value) => value,
      },
    },
    timeRange: {
      key: 'date',
      codec: {
        parse(value) {
          const values = Array.isArray(value) ? value : [value];
          const dates = values.flatMap((item) => item?.split(',') ?? []);
          if (dates.length !== 2 || !dates[0] || !dates[1]) return undefined;
          const start = dayjs(dates[0]);
          const end = dayjs(dates[1]);
          return start.isValid() && end.isValid()
            ? ([start, end] as [Dayjs, Dayjs])
            : undefined;
        },
        serialize: (value) => value?.map((date) => date.format('YYYY-MM-DD')),
      },
    },
  },
  onRouteStateRestored: async () => {
    if (!routeStateReady.value) return;
    if (activeTab.value === 'limit-rule') await loadLimitRule();
    else await loadData();
  },
  pagination: {
    defaultPageSize: 10,
    enabled: () => activeTab.value !== 'limit-rule',
    page: queryRefs.pageNum,
    pageSize: queryRefs.pageSize,
    pageSizes: [10, 20, 50, 100],
  },
  state: createListRouteStateTarget({
    cardId: queryRefs.cardId,
    cardNo: queryRefs.cardNo,
    keyword: queryRefs.keyword,
    onlyZero: queryRefs.onlyZero,
    status: queryRefs.status,
    tab: activeTab,
    timeRange: queryRefs.timeRange,
  }),
});
const detailOpen = ref(false);
const detailLoading = ref(false);
const detailData = ref<Record<string, any>>({});
const limitOpen = ref(false);
const limitSaving = ref(false);
const limitForm = reactive({ amount: 1000, preset: 'daily' });
const recordOpen = ref(false);
const limitRecords = ref<any[]>([]);
const ruleLoading = ref(false);
const ruleSaving = ref(false);
const ruleSwitchSaving = ref(false);
const ruleError = ref('');
const ruleConfigured = ref(false);
const ruleEditing = ref(false);
const rulePeriodPreset = ref<LimitPeriodPreset>('custom');
const ruleForm = reactive({
  adjustAmount: undefined as number | undefined,
  autoAdjustEnabled: false,
  customPeriod: undefined as number | undefined,
  dailyPeriod: undefined as number | undefined,
  minAmount: undefined as number | undefined,
});

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '可用 / 激活', value: 'active' },
  { label: '冻结', value: 'frozen' },
  { label: '已注销', value: 'closed' },
];

const arrivalColumns: TableColumnsType = [
  { dataIndex: 'cardId', title: '卡 ID', width: 180 },
  { dataIndex: 'cardName', title: '卡片名称', width: 150 },
  { dataIndex: 'maskedPan', title: '卡号', width: 180 },
  { dataIndex: 'status', title: '卡状态', width: 110 },
  { dataIndex: 'balance', title: '剩余额度', width: 130 },
  { dataIndex: 'transactionLimit', title: '单笔消费限制', width: 150 },
  { dataIndex: 'utilizationLimit', title: '卡台限额', width: 150 },
  {
    dataIndex: 'periodMaxConsumeAmount',
    title: '周期内日最高消耗',
    width: 170,
  },
  { dataIndex: 'createdAt', title: '创建时间', width: 180 },
  { fixed: 'right', key: 'action', title: '操作', width: 150 },
];
const photonColumns: TableColumnsType = [
  { dataIndex: 'nickname', title: '卡片名称', width: 180 },
  { dataIndex: 'cardNumber', title: '卡号', width: 190 },
  { dataIndex: 'cardStatus', title: '卡状态', width: 110 },
  { dataIndex: 'cardBalance', title: '余额', width: 130 },
  { dataIndex: 'advertisementAccountId', title: '广告账户 ID', width: 180 },
  { dataIndex: 'companyEntity', title: '公司主体', width: 190 },
  { dataIndex: 'dailyLimit', title: '日限额', width: 130 },
  { dataIndex: 'monthlyLimit', title: '月限额', width: 130 },
  { dataIndex: 'updatedAt', title: '更新时间', width: 180 },
  { fixed: 'right', key: 'action', title: '操作', width: 190 },
];

const columns = computed(() =>
  activePlatform.value === 'arrivalx' ? arrivalColumns : photonColumns,
);
const rowKey = computed(() =>
  activePlatform.value === 'arrivalx' ? 'cardId' : 'id',
);

function applyLimitRule(rule: CardStationLimitRule) {
  ruleConfigured.value = rule.configured;
  ruleForm.autoAdjustEnabled = rule.autoAdjustEnabled;
  ruleForm.dailyPeriod = rule.dailyPeriod;
  ruleForm.adjustAmount =
    rule.adjustAmount === undefined ? undefined : Number(rule.adjustAmount);
  ruleForm.minAmount =
    rule.minAmount === undefined ? undefined : Number(rule.minAmount);
  if (rule.dailyPeriod === 7 || rule.dailyPeriod === 15) {
    rulePeriodPreset.value = rule.dailyPeriod;
    ruleForm.customPeriod = undefined;
  } else {
    rulePeriodPreset.value = 'custom';
    ruleForm.customPeriod = rule.dailyPeriod;
  }
}

async function loadLimitRule() {
  ruleLoading.value = true;
  try {
    applyLimitRule(await getCardStationLimitRule());
    ruleError.value = '';
  } catch {
    ruleError.value = '限额规则暂时无法加载，请稍后重试。';
  } finally {
    ruleLoading.value = false;
  }
}

function editLimitRule() {
  ruleEditing.value = true;
}

async function cancelLimitRuleEdit() {
  ruleEditing.value = false;
  await loadLimitRule();
}

async function saveLimitRule() {
  const dailyPeriod =
    rulePeriodPreset.value === 'custom'
      ? ruleForm.customPeriod
      : rulePeriodPreset.value;
  if (!dailyPeriod || dailyPeriod < 1 || dailyPeriod > 365) {
    message.warning('请输入 1 至 365 天的历史消耗周期');
    return;
  }
  if (ruleForm.adjustAmount === undefined || ruleForm.adjustAmount < 0) {
    message.warning('请输入不小于 0 的加权额度');
    return;
  }
  if (ruleForm.minAmount === undefined || ruleForm.minAmount < 0) {
    message.warning('请输入不小于 0 的最低限额');
    return;
  }

  ruleSaving.value = true;
  try {
    const saved = await updateCardStationLimitRule({
      adjustAmount: ruleForm.adjustAmount,
      autoAdjustEnabled: ruleForm.autoAdjustEnabled,
      dailyPeriod,
      minAmount: ruleForm.minAmount,
    });
    applyLimitRule(saved);
    ruleEditing.value = false;
    message.success('限额规则已保存');
  } finally {
    ruleSaving.value = false;
  }
}

async function changeAutoAdjust(enabled: boolean) {
  const previous = ruleForm.autoAdjustEnabled;
  ruleForm.autoAdjustEnabled = enabled;
  ruleSwitchSaving.value = true;
  try {
    applyLimitRule(await updateCardStationAutoAdjust(enabled));
    message.success(enabled ? '已开启自动调整' : '已关闭自动调整');
  } catch {
    ruleForm.autoAdjustEnabled = previous;
  } finally {
    ruleSwitchSaving.value = false;
  }
}

function buildQuery() {
  return {
    cardId: query.cardId || undefined,
    cardName: query.keyword || undefined,
    cardNo: query.cardNo.trim().split(/\s+/).filter(Boolean).join(','),
    endDate: query.timeRange?.[1]?.format?.('YYYY-MM-DD'),
    pageNum: query.pageNum,
    pageSize: query.pageSize,
    periodMaxConsumeAmount: query.onlyZero ? 0 : undefined,
    startDate: query.timeRange?.[0]?.format?.('YYYY-MM-DD'),
    status: query.status || undefined,
  };
}

async function loadData(showMessage = false) {
  loading.value = true;
  selectedRowKeys.value = [];
  try {
    if (activePlatform.value === 'arrivalx') {
      const [list, balances] = await Promise.all([
        getCardStationCards<ArrivalxCard>('arrivalx', buildQuery()),
        getCardStationBalance('arrivalx'),
      ]);
      rows.value = list.items;
      total.value = list.total;
      balanceItems.value = balances;
    } else {
      const [list, summary] = await Promise.all([
        getCardStationCards<PhotonPayCard>('photonpay', buildQuery()),
        getCardStationStatistics('photonpay'),
      ]);
      rows.value = list.items;
      total.value = list.total;
      Object.assign(statistics, summary);
    }
    loadError.value = '';
    if (showMessage) message.success('卡台数据已刷新');
  } catch {
    rows.value = [];
    total.value = 0;
    balanceItems.value = [];
    Object.assign(statistics, { active: 0, balance: 0, frozen: 0, total: 0 });
    loadError.value = '卡台数据暂时无法加载，请稍后重试。';
  } finally {
    loading.value = false;
  }
}

async function runQuery(resetPage = false) {
  if (resetPage) query.pageNum = 1;
  await commitQueryState();
  await loadData();
}

async function resetQuery() {
  Object.assign(query, {
    cardId: '',
    cardNo: '',
    keyword: '',
    onlyZero: false,
    pageNum: 1,
    pageSize: 10,
    status: '',
    timeRange: undefined,
  });
  await commitQueryState();
  await loadData();
}

async function handlePageChange(page: { current?: number; pageSize?: number }) {
  const sizeChanged =
    page.pageSize !== undefined && page.pageSize !== query.pageSize;
  query.pageSize = page.pageSize || 10;
  query.pageNum = sizeChanged ? 1 : page.current || 1;
  await commitQueryState();
  await loadData();
}

async function syncData() {
  await syncCardStation(activePlatform.value);
  message.success('卡台同步任务已触发');
  window.setTimeout(() => void loadData(), 800);
}

async function viewDetail(record: any) {
  detailData.value = { ...record };
  detailOpen.value = true;
  detailLoading.value = true;
  try {
    detailData.value = await getCardStationDetail(
      activePlatform.value,
      record[rowKey.value],
    );
  } finally {
    detailLoading.value = false;
  }
}

function openLimitModal(record?: any) {
  const key = record?.[rowKey.value];
  if (key && !selectedRowKeys.value.includes(key))
    selectedRowKeys.value = [key];
  if (selectedRowKeys.value.length === 0)
    return void message.warning('请先勾选需要修改限额的卡');
  limitOpen.value = true;
}

async function saveLimit() {
  limitSaving.value = true;
  try {
    await setCardStationBatchLimit(activePlatform.value, {
      amount: limitForm.amount,
      cardIds: selectedRowKeys.value,
      limitAmount: limitForm.amount,
      preset: limitForm.preset,
    });
    limitOpen.value = false;
    message.success(`已提交 ${selectedRowKeys.value.length} 张卡的限额调整`);
    await loadData();
  } finally {
    limitSaving.value = false;
  }
}

function changePhotonStatus(record: any, status: 'freeze' | 'unfreeze') {
  Modal.confirm({
    cancelText: '取消',
    content: `确认${status === 'freeze' ? '冻结' : '解冻'}卡号 ${record.cardNumber || record.cardNo}？`,
    okText: '确认',
    async onOk() {
      await updateCardStationStatus('photonpay', {
        ids: [record.id],
        status,
      });
      message.success('卡状态指令已提交');
      await loadData();
    },
    title: '卡状态确认',
  });
}

async function viewLimitRecords(record: any) {
  recordOpen.value = true;
  limitRecords.value = [];
  const data = await getCardStationLimitRecords('arrivalx', {
    cardId: record.cardId,
    pageNum: 1,
    pageSize: 50,
  });
  limitRecords.value = data.items;
}

async function exportCards() {
  const blob = await exportCardStationCards(activePlatform.value, buildQuery());
  const url = URL.createObjectURL(blob as Blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${activePlatform.value}_卡列表_${Date.now()}.xlsx`;
  link.click();
  URL.revokeObjectURL(url);
}

watch(activeTab, async (tab) => {
  if (!routeStateReady.value) return;
  if (tab === 'limit-rule') {
    await commitQueryState();
    await loadLimitRule();
    return;
  }
  query.pageNum = 1;
  await commitQueryState();
  await loadData();
});
onMounted(async () => {
  await restoreFromRoute();
  routeStateReady.value = true;
  if (activeTab.value === 'limit-rule') await loadLimitRule();
  else await loadData();
});
</script>

<template>
  <main
    class="adpulse-section-page system-management-page card-station-page min-h-full text-slate-700"
  >
    <section class="mx-auto max-w-[1900px]">
      <header
        class="business-page-header rounded-xl border border-slate-200 bg-white"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 class="m-0 font-semibold text-slate-900">卡台管理</h1>
            <p class="mb-4 mt-1 text-sm text-slate-500">
              统一管理 PhotonPay 与 ArrivalX 卡片、余额、限额和状态。
            </p>
          </div>
          <div v-if="activeTab !== 'limit-rule'" class="flex flex-wrap gap-2">
            <Button @click="syncData">
              <IconifyIcon icon="lucide:refresh-cw" /> 同步数据 </Button
            ><Button @click="exportCards">
              <IconifyIcon icon="lucide:download" /> 导出 </Button
            ><Button type="primary" @click="openLimitModal()">
              <IconifyIcon icon="lucide:gauge" /> 批量修改限额
            </Button>
          </div>
        </div>
        <Tabs v-model:active-key="activeTab">
          <Tabs.TabPane key="photonpay" tab="PhotonPay" /><Tabs.TabPane
            key="arrivalx"
            tab="ArrivalX"
          /><Tabs.TabPane key="limit-rule" tab="限额规则" />
        </Tabs>
      </header>

      <Alert
        v-if="activeTab !== 'limit-rule' && loadError"
        banner
        :message="loadError"
        show-icon
        type="error"
      >
        <template #action>
          <Button @click="() => loadData()">重新加载</Button>
        </template>
      </Alert>

      <Card v-if="activeTab === 'limit-rule'" :loading="ruleLoading" class="">
        <template #title>
          <div>
            <div class="font-semibold text-slate-900">卡日授权额度规则</div>
            <div class="mt-1 text-sm font-normal text-slate-500">
              PhotonPay 与 ArrivalX 共用；自动调额只影响日限额，不影响手工调整。
            </div>
          </div>
        </template>

        <Alert v-if="ruleError" :message="ruleError" show-icon type="error">
          <template #action>
            <Button @click="loadLimitRule">重新加载</Button>
          </template>
        </Alert>

        <Empty
          v-else-if="!ruleConfigured && !ruleEditing"
          description="尚未配置卡台限额规则"
        >
          <template #default>
            <Button type="primary" @click="editLimitRule">立即配置</Button>
          </template>
        </Empty>

        <div v-else-if="!ruleEditing" class="max-w-3xl space-y-4">
          <Descriptions :column="1" bordered>
            <Descriptions.Item label="历史消耗周期">
              最近 {{ ruleForm.dailyPeriod }} 天
            </Descriptions.Item>
            <Descriptions.Item label="加权额度">
              {{ Number(ruleForm.adjustAmount || 0).toFixed(2) }} USD
            </Descriptions.Item>
            <Descriptions.Item label="最低日限额">
              {{ Number(ruleForm.minAmount || 0).toFixed(2) }} USD
            </Descriptions.Item>
            <Descriptions.Item label="加权额度自动调整">
              <div class="flex flex-wrap items-center gap-3">
                <Switch
                  :checked="ruleForm.autoAdjustEnabled"
                  :loading="ruleSwitchSaving"
                  checked-children="开启"
                  un-checked-children="关闭"
                  @change="(checked) => changeAutoAdjust(Boolean(checked))"
                />
                <span class="text-sm text-slate-500">
                  关闭后仍展示周期最高消耗，但不会自动修改日限额。
                </span>
              </div>
            </Descriptions.Item>
          </Descriptions>
          <Alert
            message="调整后日限额 = 历史消耗周期内单日最高消耗金额 + 加权额度，且不低于最低日限额。"
            show-icon
            type="info"
          />
          <Button type="primary" @click="editLimitRule">
            <IconifyIcon icon="lucide:pencil" /> 编辑规则
          </Button>
        </div>

        <Form v-else class="max-w-3xl" layout="vertical">
          <Form.Item label="历史消耗周期" required>
            <Radio.Group v-model:value="rulePeriodPreset">
              <div class="flex flex-col gap-3">
                <Radio :value="7">最近 7 天</Radio>
                <Radio :value="15">最近 15 天</Radio>
                <Radio value="custom">
                  <span class="mr-2">最近</span>
                  <InputNumber
                    v-model:value="ruleForm.customPeriod"
                    aria-label="自定义历史消耗周期天数"
                    :controls="false"
                    :max="365"
                    :min="1"
                    :precision="0"
                    style="width: 96px"
                    @focus="rulePeriodPreset = 'custom'"
                  />
                  <span class="ml-2">天</span>
                </Radio>
              </div>
            </Radio.Group>
          </Form.Item>
          <div class="grid gap-x-4 md:grid-cols-2">
            <Form.Item label="加权额度" required>
              <InputNumber
                v-model:value="ruleForm.adjustAmount"
                class="w-full"
                :controls="false"
                :min="0"
                :precision="2"
                addon-after="USD"
                placeholder="请输入加权额度"
              />
            </Form.Item>
            <Form.Item label="最低日限额" required>
              <InputNumber
                v-model:value="ruleForm.minAmount"
                class="w-full"
                :controls="false"
                :min="0"
                :precision="2"
                addon-after="USD"
                placeholder="请输入最低日限额"
              />
            </Form.Item>
          </div>
          <Form.Item label="加权额度自动调整">
            <Switch
              v-model:checked="ruleForm.autoAdjustEnabled"
              checked-children="开启"
              un-checked-children="关闭"
            />
            <div class="mt-2 text-sm text-slate-500">
              开启后，新服务将按照该规则生成自动调额任务。
            </div>
          </Form.Item>
          <Alert
            class="mb-4"
            message="调整后日限额 = 历史消耗周期内单日最高消耗金额 + 加权额度，且不低于最低日限额。"
            show-icon
            type="info"
          />
          <div class="flex flex-wrap gap-2">
            <Button :loading="ruleSaving" type="primary" @click="saveLimitRule">
              保存规则
            </Button>
            <Button :disabled="ruleSaving" @click="cancelLimitRuleEdit">
              取消
            </Button>
          </div>
        </Form>
      </Card>

      <div
        v-if="activeTab !== 'limit-rule' && activePlatform === 'arrivalx'"
        class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <Card
          v-for="(item, index) in balanceItems"
          :key="index"
          class="border-0 shadow-sm"
        >
          <Statistic
            :precision="2"
            :suffix="item.currency"
            :title="`${item.productCode || '通用'}卡账户可用资金`"
            :value="Number(item.balance || 0)"
          />
          <div class="mt-2 text-xs text-rose-500">
            冻结 {{ item.frozenBalance || 0 }} {{ item.currency }}
          </div>
        </Card>
        <Card
          v-if="balanceItems.length === 0"
          class="sm:col-span-2 xl:col-span-4"
        >
          <Empty description="暂无资金数据" />
        </Card>
      </div>
      <div
        v-else-if="activeTab !== 'limit-rule'"
        class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <Card class="border-0 shadow-sm">
          <Statistic
            title="卡片总数"
            :value="statistics.total || total"
          /> </Card
        ><Card class="border-0 shadow-sm">
          <Statistic
            title="可用卡"
            :value="statistics.active"
            :value-style="{ color: '#059669' }"
          /> </Card
        ><Card class="border-0 shadow-sm">
          <Statistic
            title="冻结卡"
            :value="statistics.frozen"
            :value-style="{ color: '#e11d48' }"
          /> </Card
        ><Card class="border-0 shadow-sm">
          <Statistic
            prefix="$"
            title="卡台余额"
            :value="statistics.balance"
            :precision="2"
          />
        </Card>
      </div>

      <Card v-if="activeTab !== 'limit-rule'" class="border-0 shadow-sm">
        <Form layout="vertical">
          <div class="grid gap-x-4 md:grid-cols-2 xl:grid-cols-6">
            <Form.Item label="卡片名称 / 广告账户">
              <Input
                v-model:value="query.keyword"
                allow-clear
                placeholder="输入名称或广告账户 ID"
                @press-enter="runQuery(true)"
              />
            </Form.Item>
            <Form.Item label="卡 ID">
              <Input
                v-model:value="query.cardId"
                allow-clear
                placeholder="输入卡 ID"
              />
            </Form.Item>
            <Form.Item label="卡号">
              <Input
                v-model:value="query.cardNo"
                allow-clear
                placeholder="支持空格或换行分隔"
              />
            </Form.Item>
            <Form.Item label="卡状态">
              <Select v-model:value="query.status" :options="statusOptions" />
            </Form.Item>
            <Form.Item label="创建时间">
              <DatePicker.RangePicker
                v-model:value="query.timeRange"
                class="w-full"
              />
            </Form.Item>
            <Form.Item label="操作">
              <div class="flex gap-2">
                <Button type="primary" @click="runQuery(true)">
                  <IconifyIcon icon="lucide:search" /> 查询 </Button
                ><Button @click="resetQuery">重置</Button>
              </div>
            </Form.Item>
          </div>
          <Checkbox
            v-if="activePlatform === 'arrivalx'"
            v-model:checked="query.onlyZero"
            @change="runQuery(true)"
          >
            仅显示周期内日最高消耗为 0 的卡
          </Checkbox>
        </Form>
      </Card>

      <Card
        v-if="activeTab !== 'limit-rule'"
        :body-style="{ padding: '0' }"
        class="overflow-hidden border-0 shadow-sm"
      >
        <div
          class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4"
        >
          <div>
            <span class="font-semibold text-slate-900">卡片列表</span
            ><span class="ml-2 text-sm text-slate-500"
              >共 {{ total }} 张，已选择 {{ selectedRowKeys.length }} 张</span
            >
          </div>
          <Button
            :disabled="selectedRowKeys.length === 0"
            @click="openLimitModal()"
          >
            修改所选卡限额
          </Button>
        </div>
        <Table
          :columns="columns"
          :data-source="rows"
          :loading="loading"
          :pagination="{
            current: query.pageNum,
            pageSize: query.pageSize,
            showSizeChanger: true,
            total,
          }"
          :row-key="rowKey"
          :row-selection="{
            selectedRowKeys,
            onChange: (keys) => (selectedRowKeys = keys),
          }"
          :scroll="{ x: 1450 }"
          @change="handlePageChange"
        >
          <template #bodyCell="{ column, record }">
            <template
              v-if="
                column.dataIndex === 'status' ||
                column.dataIndex === 'cardStatus'
              "
            >
              <Tag
                :color="
                  String(record.status || record.cardStatus)
                    .toLowerCase()
                    .includes('active')
                    ? 'success'
                    : String(record.status || record.cardStatus)
                          .toLowerCase()
                          .includes('frozen')
                      ? 'error'
                      : 'default'
                "
              >
                {{ record.status || record.cardStatus || '—' }}
              </Tag>
            </template>
            <template v-else-if="column.dataIndex === 'balance'">
              {{ record.balance ?? '—' }} {{ record.currency }}
            </template>
            <template v-else-if="column.dataIndex === 'cardBalance'">
              {{ record.cardBalance ?? '—' }}
              {{ record.cardCurrency }}
            </template>
            <template v-else-if="column.dataIndex === 'transactionLimit'">
              {{ record.transactionMinAmount || 0 }} /
              {{ record.transactionMaxAmount || '—' }}
            </template>
            <template v-else-if="column.dataIndex === 'utilizationLimit'">
              {{ record.utilizationLimitPreset || '' }}
              {{ record.utilizationLimitAmount ?? '—' }}
              {{ record.currency }}
            </template>
            <template v-else-if="column.dataIndex === 'periodMaxConsumeAmount'">
              {{ record.periodMaxConsumeAmount ?? '—' }}
              {{ record.currency }}
            </template>
            <template v-else-if="column.key === 'action'">
              <div class="flex whitespace-nowrap">
                <Button type="link" @click="viewDetail(record)"> 详情 </Button
                ><Button
                  v-if="activePlatform === 'arrivalx'"
                  type="link"
                  @click="viewLimitRecords(record)"
                >
                  修改记录 </Button
                ><template v-else>
                  <Button type="link" @click="openLimitModal(record)">
                    限额 </Button
                  ><Button
                    type="link"
                    @click="
                      changePhotonStatus(
                        record,
                        String(record.cardStatus)
                          .toLowerCase()
                          .includes('frozen')
                          ? 'unfreeze'
                          : 'freeze',
                      )
                    "
                  >
                    {{
                      String(record.cardStatus).toLowerCase().includes('frozen')
                        ? '解冻'
                        : '冻结'
                    }}
                  </Button>
                </template>
              </div>
            </template>
          </template>
        </Table>
      </Card>
    </section>

    <Modal
      v-model:open="limitOpen"
      :confirm-loading="limitSaving"
      ok-text="提交调整"
      title="批量修改卡台限额"
      @ok="saveLimit"
    >
      <Alert
        class="mb-4"
        :message="`将修改 ${selectedRowKeys.length} 张卡，请核对额度和周期。`"
        show-icon
        type="info"
      /><Form layout="vertical">
        <Form.Item label="限额周期" required>
          <Select
            v-model:value="limitForm.preset"
            :options="[
              { label: '每日', value: 'daily' },
              { label: '每月', value: 'monthly' },
              { label: '取消限额', value: 'cancel' },
            ]"
          /> </Form.Item
        ><Form.Item
          v-if="limitForm.preset !== 'cancel'"
          label="限额金额"
          required
        >
          <InputNumber
            v-model:value="limitForm.amount"
            class="w-full"
            :min="0"
            :precision="2"
            addon-after="USD"
          />
        </Form.Item>
      </Form>
    </Modal>

    <Modal
      v-model:open="detailOpen"
      :footer="null"
      title="卡片详情"
      width="860px"
    >
      <Descriptions :column="{ xs: 1, sm: 2 }" bordered>
        <Descriptions.Item
          v-for="(value, key) in detailData"
          :key="key"
          :label="String(key)"
        >
          {{ value ?? '—' }}
        </Descriptions.Item>
      </Descriptions>
      <div v-if="detailLoading" class="py-4 text-center text-slate-500">
        正在加载详情…
      </div>
    </Modal>
    <Modal
      v-model:open="recordOpen"
      :footer="null"
      title="限额修改记录"
      width="900px"
    >
      <Table
        :columns="[
          { title: '时间', dataIndex: 'createTime' },
          { title: '修改前', dataIndex: 'beforeLimit' },
          { title: '修改后', dataIndex: 'afterLimit' },
          { title: '操作人', dataIndex: 'createBy' },
          { title: '状态', dataIndex: 'status' },
        ]"
        :data-source="limitRecords"
        :pagination="false"
        :scroll="{ x: 700 }"
      /><Empty v-if="limitRecords.length === 0" description="暂无修改记录" />
    </Modal>
  </main>
</template>

<style scoped>
.card-station-page {
  padding: var(--adpulse-page-gutter);
  background: hsl(var(--background));
}

.card-station-page > section {
  display: flex;
  flex-direction: column;
  gap: var(--adpulse-section-gap);
}

.card-station-page h1 {
  font-size: var(--adpulse-page-title-size);
  line-height: 1.35;
}

.card-station-page .business-page-header {
  min-height: var(--adpulse-page-header-min-height);
  padding: var(--adpulse-page-header-padding-block) var(--adpulse-page-gutter) 0;
}
</style>
