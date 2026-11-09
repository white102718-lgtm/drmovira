<script setup lang="ts">
import type {
  AdAccount,
  MetricWindow,
  NotificationRecord,
  PlatformConfig,
} from '#/api/advertisement/automated-rule';

import { computed, reactive, ref, watch } from 'vue';

import {
  Button,
  DatePicker,
  Dropdown,
  Input,
  InputNumber,
  Menu,
  message,
  Modal,
  Pagination,
  Select,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  approveRecord,
  batchAction,
  getAdAccounts,
  getPlatformConfigs,
  ignoreRecord,
  listNotificationRecords,
} from '#/api/advertisement/automated-rule';
import PerformanceComparisonModal from './PerformanceComparisonModal.vue';

interface Props {
  open: boolean;
  aiCount?: number;
  ruleCount?: number;
}
interface Emits {
  (e: 'closed'): void;
  (e: 'refresh'): void;
  (e: 'update:open', value: boolean): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const modalOpen = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val),
});

const loading = ref(false);
const records = ref<NotificationRecord[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const selectedIds = ref<string[]>([]);
const processingIds = ref<string[]>([]);
const targetValues = ref<Record<string, number>>({});
const expandedIds = ref<string[]>([]);

const displayRecords = computed(() => {
  const result: any[] = [];
  for (const r of records.value) {
    result.push(r);
    if (
      r.notification_item?.metric_window &&
      expandedIds.value.includes(r.id)
    ) {
      result.push({ id: `${r.id}__mw`, _isSubRow: true, _parent: r });
    }
  }
  return result;
});

function toggleExpand(id: string) {
  const idx = expandedIds.value.indexOf(id);
  if (idx === -1) expandedIds.value.push(id);
  else expandedIds.value.splice(idx, 1);
}
const agentLines = ref<string[]>([]);
const projectList = ref<PlatformConfig[]>([]);
const accountList = ref<AdAccount[]>([]);

const activeLevel = ref<'ad' | 'adset' | 'campaign'>('campaign');

const levelTabs = [
  { key: 'campaign', label: '广告系列' },
  { key: 'adset', label: '广告组' },
  { key: 'ad', label: '广告' },
] as const;

const filter = reactive({
  keyword: '',
  project_id: undefined as string | undefined,
  agent_line: undefined as string | undefined,
  account_id: undefined as string | undefined,
  source_type: undefined as string | undefined,
  action_filter: undefined as string | undefined,
  checked_range: undefined as [string, string] | undefined,
});

const sourceOptions = [
  { label: '自动化规则', value: 'rule' },
  { label: 'AI建议', value: 'ai' },
];

const actionFilterOptions = [
  { label: '增加预算', value: 'increase_budget' },
  { label: '降低预算', value: 'decrease_budget' },
  { label: '修改预算', value: 'set_budget' },
  { label: '关闭投放', value: 'pause' },
];

const BASE_COLUMNS = [
  { key: 'project', title: '项目名称', width: 130 },
  { key: 'agent_line', title: '代理线', width: 130, ellipsis: true },
  { key: 'campaign', title: '广告系列', width: 150, ellipsis: true },
];
const ADSET_COL = {
  key: 'adset_name',
  title: '广告组',
  width: 150,
  ellipsis: true,
};
const AD_COL = { key: 'ad_name', title: '广告', width: 150, ellipsis: true };
const ACCOUNT_COL = {
  key: 'account',
  title: '账户名称',
  width: 140,
  ellipsis: true,
};
const CAMPAIGN_ID_COL = {
  key: 'campaign_id',
  title: '系列ID',
  width: 160,
  ellipsis: true,
};
const ADSET_ID_COL = {
  key: 'adset_id',
  title: '广告组ID',
  width: 160,
  ellipsis: true,
};
const AD_ID_COL = { key: 'ad_id', title: '广告ID', width: 160, ellipsis: true };
const METRIC_COLUMNS = [
  { key: 'spend', title: '花费', width: 110 },
  { key: 'budget', title: '预算', width: 80 },
  { key: 'impression_cost', title: '千展成本', width: 80 },
  { key: 'click_cost', title: '点击成本', width: 80 },
  { key: 'registration_cost', title: '注册成本', width: 80 },
  { key: 'subscription_cost', title: '单次订阅成本', width: 100 },
  { key: 'purchase_cost', title: '单次购物成本', width: 100 },
  { key: 'roas', title: 'ROAS', width: 65 },
  { key: 'purchases', title: '购物', width: 55 },
  { key: 'subscriptions', title: '订阅', width: 55 },
  { key: 'source_type', title: '触发类型', width: 90 },
  { key: 'source', title: '触发规则', width: 150, ellipsis: true },
  { key: 'checked_at', title: '触发时间', width: 140 },
];
const ACTION_COLUMNS = [
  {
    key: 'action',
    title: '建议操作(可修改)',
    width: 240,
    fixed: 'right' as const,
  },
  { key: 'operate', title: '操作', width: 160, fixed: 'right' as const },
];

const tableColumns = computed(() => {
  const nameExtra =
    activeLevel.value === 'ad'
      ? [ADSET_COL, AD_COL]
      : activeLevel.value === 'adset'
        ? [ADSET_COL]
        : [];
  const rightIdExtra =
    activeLevel.value === 'ad'
      ? [ADSET_ID_COL, AD_ID_COL]
      : activeLevel.value === 'adset'
        ? [ADSET_ID_COL]
        : [];
  return [
    ...BASE_COLUMNS,
    ...nameExtra,
    ...METRIC_COLUMNS,
    ACCOUNT_COL,
    CAMPAIGN_ID_COL,
    ...rightIdExtra,
    ...ACTION_COLUMNS,
  ];
});

const projectOptions = computed(() => [
  ...projectList.value.map((c) => ({ label: c.name, value: c.id })),
]);

const agentLineOptions = computed(() => [
  ...agentLines.value.map((v) => ({ label: v, value: v })),
]);

const accountOptions = computed(() => [
  ...accountList.value.map((a) => ({
    label: a.account_name || a.account_id,
    value: a.account_id,
  })),
]);

const rowSelection = computed(() => ({
  selectedRowKeys: selectedIds.value,
  onChange: (keys: (number | string)[]) => {
    selectedIds.value = keys as string[];
  },
  getCheckboxProps: (r: any) => ({
    disabled:
      r._isSubRow ||
      r.status !== 'pending' ||
      r.notification_item?.handling_status !== 'pending',
    style: r._isSubRow ? { display: 'none' } : {},
  }),
}));

function isSelectable(r: NotificationRecord) {
  return (
    r.status === 'pending' && r.notification_item?.handling_status === 'pending'
  );
}

async function loadPage() {
  loading.value = true;
  try {
    const result = await listNotificationRecords({
      page: page.value,
      page_size: pageSize.value,
      keyword: filter.keyword || undefined,
      project_id: filter.project_id,
      agent_line: filter.agent_line,
      account_id: filter.account_id,
      source_type: filter.source_type,
      action_filter: filter.action_filter,
      checked_start: filter.checked_range?.[0]
        ? `${filter.checked_range[0]}T00:00`
        : undefined,
      checked_end: filter.checked_range?.[1]
        ? `${filter.checked_range[1]}T23:59`
        : undefined,
      level: activeLevel.value,
    });
    records.value = result.items ?? [];
    total.value = result.total ?? 0;
    expandedIds.value = records.value
      .filter((r) => r.notification_item?.metric_window)
      .map((r) => r.id);
    if ((result as any).filter_options?.agent_lines?.length) {
      agentLines.value = (result as any).filter_options.agent_lines;
    }
    for (const r of records.value) {
      const sa = r.notification_item?.suggested_action as any;
      const tv = sa?.target_value ?? sa?.value;
      if (tv !== null && tv !== undefined) targetValues.value[r.id] = tv;
    }
  } catch {
    // handled by interceptor
  } finally {
    loading.value = false;
  }
}

function resetAndLoad() {
  page.value = 1;
  loadPage();
}

function close() {
  modalOpen.value = false;
  selectedIds.value = [];
  page.value = 1;
  total.value = 0;
  activeLevel.value = 'campaign';
  Object.assign(filter, {
    keyword: '',
    project_id: undefined,
    agent_line: undefined,
    account_id: undefined,
    source_type: undefined,
    action_filter: undefined,
    checked_range: undefined,
  });
  emit('closed');
}

watch(activeLevel, (val) => {
  if (!val) {
    activeLevel.value = 'campaign';
    return;
  }
  selectedIds.value = [];
  page.value = 1;
  if (props.open) {
    loadPage();
    emit('refresh');
  }
});

watch(
  () => ({ ...filter }),
  () => {
    if (props.open) resetAndLoad();
  },
);

watch(
  () => props.open,
  async (val) => {
    if (!val) return;
    page.value = 1;
    const [, projects, accounts] = await Promise.allSettled([
      loadPage(),
      getPlatformConfigs(),
      getAdAccounts(),
    ]);
    if (projects.status === 'fulfilled') projectList.value = projects.value;
    if (accounts.status === 'fulfilled') accountList.value = accounts.value;
  },
);

async function handleApprove(record: NotificationRecord) {
  processingIds.value = [...processingIds.value, record.id];
  try {
    const updated = await approveRecord(record.id);
    const idx = records.value.findIndex((r) => r.id === record.id);
    if (idx !== -1) records.value[idx] = updated;
    message.success('已确认执行');
    emit('refresh');
  } finally {
    processingIds.value = processingIds.value.filter((x) => x !== record.id);
  }
}

async function handleIgnore(record: NotificationRecord) {
  processingIds.value = [...processingIds.value, record.id];
  try {
    const updated = await ignoreRecord(record.id);
    const idx = records.value.findIndex((r) => r.id === record.id);
    if (idx !== -1) records.value[idx] = updated;
    message.success('已忽略');
    emit('refresh');
  } finally {
    processingIds.value = processingIds.value.filter((x) => x !== record.id);
  }
}

async function handleBatchApprove() {
  const ids = selectedIds.value.filter((id) => {
    const r = records.value.find((r) => r.id === id);
    return r && isSelectable(r);
  });
  if (ids.length === 0) return;
  processingIds.value = [...processingIds.value, ...ids];
  try {
    await Promise.all(
      ids.map(async (id) => {
        const updated = await approveRecord(id);
        const idx = records.value.findIndex((r) => r.id === id);
        if (idx !== -1) records.value[idx] = updated;
      }),
    );
    message.success(`已批量确认 ${ids.length} 条`);
    selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id));
    emit('refresh');
  } finally {
    processingIds.value = processingIds.value.filter((x) => !ids.includes(x));
  }
}

async function handleBatchIgnore() {
  const ids = selectedIds.value.filter((id) => {
    const r = records.value.find((r) => r.id === id);
    return r && isSelectable(r);
  });
  if (ids.length === 0) return;
  processingIds.value = [...processingIds.value, ...ids];
  try {
    await Promise.all(
      ids.map(async (id) => {
        const updated = await ignoreRecord(id);
        const idx = records.value.findIndex((r) => r.id === id);
        if (idx !== -1) records.value[idx] = updated;
      }),
    );
    message.success(`已忽略 ${ids.length} 条`);
    selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id));
    emit('refresh');
  } finally {
    processingIds.value = processingIds.value.filter((x) => !ids.includes(x));
  }
}

// ── 批量操作 ──────────────────────────────────────────────
const batchActionModal = reactive({
  open: false,
  value: undefined as number | undefined,
  loading: false,
});

const analysisRecord = ref<NotificationRecord | null>(null);
const analysisOpen = ref(false);

/** 打开分析弹窗 */
function handleAnalysis(record: NotificationRecord) {
  analysisRecord.value = record;
  analysisOpen.value = true;
}

/** 模板辅助：将 any 转为 NotificationRecord（避免模板中直接使用 as 语法） */
function asRecord(r: any): NotificationRecord {
  return r;
}

function openBatchBudgetModal() {
  batchActionModal.value = undefined;
  batchActionModal.open = true;
}

async function submitBatchBudget() {
  if (batchActionModal.value == null || batchActionModal.value <= 0) {
    message.warning('请输入有效预算值');
    return;
  }
  const selectedRecords = selectedIds.value
    .map((id) => records.value.find((r) => r.id === id))
    .filter((r) => r && isSelectable(r)) as NotificationRecord[];
  if (selectedRecords.length === 0) return;

  batchActionModal.loading = true;
  try {
    const calls = selectedRecords.map((r) => {
      // 原建议动作为 set（直接修改预算）时，direction 仍传 set，value 直接取输入值
      const isSet =
        (r.notification_item?.suggested_action as any)?.direction === 'set';
      const action = isSet
        ? {
            action_type: 'daily_budget',
            direction: 'set',
            unit: 'fixed',
            value: batchActionModal.value! * 100,
          }
        : (() => {
            // 其余情况计算与当前预算的差值，正数增加、负数减少
            const budget = r.notification_item?.budget ?? 0;
            const diff = batchActionModal.value! * 100 - budget;
            return {
              action_type: 'daily_budget',
              direction: diff >= 0 ? 'increase' : 'decrease',
              unit: 'fixed',
              value: Math.abs(diff),
            };
          })();
      return batchAction({ record_ids: [r.id], action: action as any });
    });
    await Promise.all(calls);
    message.success('建议操作已修改');
    batchActionModal.open = false;
    selectedIds.value = [];
    await loadPage();
  } finally {
    batchActionModal.loading = false;
  }
}

async function handleBatchPause() {
  const ids = selectedIds.value.filter((id) => {
    const r = records.value.find((r) => r.id === id);
    return r && isSelectable(r);
  });
  if (ids.length === 0) return;
  Modal.confirm({
    title: '批量关闭投放',
    content: `确定关闭选中的 ${ids.length} 条记录的投放吗？`,
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      await batchAction({
        record_ids: ids,
        action: { action_type: 'status', status: 'paused' },
      });
      message.success('建议操作已修改');
      selectedIds.value = [];
      await loadPage();
    },
  });
}

const filterOptionFn = (input: string, opt: any) =>
  ((opt?.label as string) ?? '').toLowerCase().includes(input.toLowerCase());

function actionTagColor(label: string): string {
  if (!label) return 'default';
  if (
    label.includes('暂停') ||
    label.includes('关闭') ||
    label.includes('停止')
  )
    return 'orange';
  if (
    label.includes('开启') ||
    label.includes('恢复') ||
    label.includes('启动')
  )
    return 'green';
  if (
    label.includes('提高') ||
    label.includes('增加') ||
    label.includes('上调')
  )
    return 'blue';
  if (
    label.includes('降低') ||
    label.includes('减少') ||
    label.includes('下调')
  )
    return 'gold';
  return 'purple';
}

// ── metric_window 折叠行 ──────────────────────────────────
function mwOf(record: NotificationRecord): MetricWindow | null | undefined {
  return record.notification_item?.metric_window;
}

function mwTimeRange(record: NotificationRecord): string {
  const mw = mwOf(record);
  if (!mw?.hours || !record.checked_at) return '';
  try {
    const end = new Date(record.checked_at.replace(' ', 'T'));
    const start = new Date(end.getTime() - mw.hours * 3_600_000);
    const fmt = (d: Date) =>
      `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    return `${fmt(start)} – ${fmt(end)}`;
  } catch {
    return '';
  }
}

function mwSpendPct(record: NotificationRecord): null | number {
  const mw = mwOf(record);
  const base = mw?.baseline?.spend;
  const curr = mw?.current?.spend;
  if (base == null || base === 0 || curr == null) return null;
  return Math.round(((curr - base) / base) * 100);
}
</script>

<template>
  <!-- eslint-disable vue/html-closing-bracket-newline -->
  <Modal
    :open="modalOpen"
    :footer="null"
    width="1700px"
    destroy-on-close
    @update:open="
      (v) => {
        if (!v) close();
      }
    "
  >
    <template #title>
      <div class="flex items-center gap-2">
        <span>自动化通知</span>
        <Tag color="cyan">AI 建议 {{ aiCount ?? 0 }}</Tag>
        <Tag color="orange">规则触发 {{ ruleCount ?? 0 }}</Tag>
      </div>
    </template>

    <div>
      <p class="mb-2 text-xs text-gray-400">
        规则命中后生成的执行建议，可用于确认、忽略或后续批量处理。
      </p>

      <!-- 筛选栏 -->
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <Input
          v-model:value="filter.keyword"
          allow-clear
          class="w-52"
          placeholder="系列/组/广告搜索"
          @change="resetAndLoad"
        >
          <template #prefix>
            <span
              aria-hidden="true"
              class="icon-[ant-design--search-outlined] text-sm text-gray-400"
            ></span>
          </template>
        </Input>
        <Select
          v-model:value="filter.project_id"
          :options="projectOptions"
          :filter-option="filterOptionFn"
          allow-clear
          show-search
          class="w-32"
          placeholder="项目"
        />
        <Select
          v-model:value="filter.agent_line"
          :options="agentLineOptions"
          :filter-option="filterOptionFn"
          allow-clear
          show-search
          class="w-36"
          placeholder="代理线"
        />
        <Select
          v-model:value="filter.account_id"
          :options="accountOptions"
          :filter-option="filterOptionFn"
          allow-clear
          show-search
          class="w-36"
          placeholder="账户"
        />
        <Select
          v-model:value="filter.source_type"
          :options="sourceOptions"
          :filter-option="filterOptionFn"
          allow-clear
          show-search
          class="w-28"
          placeholder="触发类型"
        />
        <Select
          v-model:value="filter.action_filter"
          :options="actionFilterOptions"
          allow-clear
          class="w-28"
          placeholder="建议操作"
        />
        <DatePicker.RangePicker
          :value="filter.checked_range as any"
          value-format="YYYY-MM-DD"
          class="w-56"
          :placeholder="['触发开始', '触发结束']"
          allow-clear
          @change="
            (_, strs) => {
              filter.checked_range =
                strs[0] && strs[1] ? [strs[0], strs[1]] : undefined;
            }
          "
        />
        <Button
          type="link"
          class="!px-0"
          @click="
            Object.assign(filter, {
              keyword: '',
              project_id: undefined,
              agent_line: undefined,
              account_id: undefined,
              source_type: undefined,
              action_filter: undefined,
              checked_range: undefined,
            })
          "
        >
          清空筛选
        </Button>
      </div>

      <!-- 层级 Tab + 批量操作 -->
      <div class="relative mb-1">
        <Tabs v-model:active-key="activeLevel" class="w-full">
          <Tabs.TabPane
            v-for="tab in levelTabs"
            :key="tab.key"
            :tab="tab.label"
          />
        </Tabs>
        <div class="absolute right-0 top-3 flex items-center gap-2">
          <Button
            :disabled="selectedIds.length === 0"
            @click="handleBatchIgnore"
          >
            批量忽略
          </Button>
          <Dropdown :disabled="selectedIds.length === 0">
            <Button :disabled="selectedIds.length === 0"> 批量操作 ▾ </Button>
            <template #overlay>
              <Menu>
                <Menu.Item key="budget" @click="openBatchBudgetModal">
                  批量调整预算
                </Menu.Item>
                <Menu.Item key="pause" @click="handleBatchPause">
                  批量关闭投放
                </Menu.Item>
              </Menu>
            </template>
          </Dropdown>
          <Button
            :disabled="selectedIds.length === 0"
            type="primary"
            @click="handleBatchApprove"
          >
            批量确认执行
          </Button>
        </div>
      </div>

      <!-- 批量调整预算弹窗 -->
      <Modal
        :open="batchActionModal.open"
        title="批量调整预算"
        :confirm-loading="batchActionModal.loading"
        ok-text="确认"
        cancel-text="取消"
        @ok="submitBatchBudget"
        @cancel="batchActionModal.open = false"
      >
        <div class="flex items-center gap-3 py-4">
          <span class="shrink-0 text-sm">每日预算：</span>
          <InputNumber
            v-model:value="batchActionModal.value"
            :min="0"
            class="flex-1"
            placeholder="请输入预算金额"
            prefix="$"
          />
        </div>
      </Modal>

      <!-- 表格 -->
      <Table
        :columns="tableColumns"
        :data-source="displayRecords"
        :loading="loading"
        :pagination="false"
        :row-key="(r: any) => r.id"
        :row-selection="rowSelection"
        :scroll="{ x: 1800, y: 480 }"
        :custom-row="
          (r: any) => (r._isSubRow ? { style: { background: '#f0f7ff' } } : {})
        "
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <!-- ── sub-row ── -->
          <template v-if="(record as any)._isSubRow">
            <template v-if="column.key === 'project'">
              <span class="text-xs font-medium text-blue-500">
                {{
                  (record as any)._parent.notification_item.metric_window.label
                }}
                <span class="ml-1 text-[11px] font-normal text-blue-400">{{
                  mwTimeRange((record as any)._parent)
                }}</span>
              </span>
            </template>
            <template
              v-else-if="
                [
                  'account',
                  'agent_line',
                  'campaign',
                  'campaign_id',
                  'adset_name',
                  'adset_id',
                  'ad_name',
                  'ad_id',
                  'source_type',
                  'source',
                  'checked_at',
                  'action',
                  'operate',
                ].includes(String(column.key ?? ''))
              "
            >
              <span class="text-gray-300">/</span>
            </template>
            <template v-else-if="column.key === 'spend'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.spend != null
                  "
                >
                  ${{
                    Number(
                      (record as any)._parent.notification_item.metric_window
                        .delta.spend,
                    ).toFixed(2)
                  }}
                  <template
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.spend !== 0
                    "
                  >
                    <span
                      :class="
                        (record as any)._parent.notification_item.metric_window
                          .delta.spend > 0
                          ? 'text-green-500'
                          : 'text-red-500'
                      "
                      >{{
                        (record as any)._parent.notification_item.metric_window
                          .delta.spend > 0
                          ? '↑'
                          : '↓'
                      }}</span
                    ><template
                      v-if="mwSpendPct((record as any)._parent) != null"
                      >{{
                        Math.abs(mwSpendPct((record as any)._parent)!)
                      }}%</template
                    >
                  </template>
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else-if="column.key === 'budget'">
              <span class="text-gray-300">/</span>
            </template>
            <template v-else-if="column.key === 'registration_cost'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.registration_cost != null
                  "
                >
                  ${{
                    Number(
                      (record as any)._parent.notification_item.metric_window
                        .delta.registration_cost,
                    ).toFixed(2)
                  }}
                  <span
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.registration_cost !== 0
                    "
                    :class="
                      (record as any)._parent.notification_item.metric_window
                        .delta.registration_cost > 0
                        ? 'text-green-500'
                        : 'text-red-500'
                    "
                    >{{
                      (record as any)._parent.notification_item.metric_window
                        .delta.registration_cost > 0
                        ? '↑'
                        : '↓'
                    }}</span
                  >
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else-if="column.key === 'roas'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.purchase_roas != null
                  "
                >
                  {{
                    Number(
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchase_roas,
                    ).toFixed(2)
                  }}
                  <span
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchase_roas !== 0
                    "
                    :class="
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchase_roas > 0
                        ? 'text-green-500'
                        : 'text-red-500'
                    "
                    >{{
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchase_roas > 0
                        ? '↑'
                        : '↓'
                    }}</span
                  >
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else-if="column.key === 'purchases'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.purchases != null
                  "
                >
                  {{
                    (record as any)._parent.notification_item.metric_window
                      .delta.purchases
                  }}
                  <span
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchases !== 0
                    "
                    :class="
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchases > 0
                        ? 'text-green-500'
                        : 'text-red-500'
                    "
                    >{{
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchases > 0
                        ? '↑'
                        : '↓'
                    }}</span
                  >
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else-if="column.key === 'subscriptions'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.subscriptions != null
                  "
                >
                  {{
                    (record as any)._parent.notification_item.metric_window
                      .delta.subscriptions
                  }}
                  <span
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.subscriptions !== 0
                    "
                    :class="
                      (record as any)._parent.notification_item.metric_window
                        .delta.subscriptions > 0
                        ? 'text-green-500'
                        : 'text-red-500'
                    "
                    >{{
                      (record as any)._parent.notification_item.metric_window
                        .delta.subscriptions > 0
                        ? '↑'
                        : '↓'
                    }}</span
                  >
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else-if="column.key === 'purchase_cost'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.purchase_cost != null
                  "
                >
                  ${{
                    Number(
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchase_cost,
                    ).toFixed(2)
                  }}
                  <span
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchase_cost !== 0
                    "
                    :class="
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchase_cost > 0
                        ? 'text-green-500'
                        : 'text-red-500'
                    "
                    >{{
                      (record as any)._parent.notification_item.metric_window
                        .delta.purchase_cost > 0
                        ? '↑'
                        : '↓'
                    }}</span
                  >
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else-if="column.key === 'click_cost'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.click_cost != null
                  "
                >
                  ${{
                    Number(
                      (record as any)._parent.notification_item.metric_window
                        .delta.click_cost,
                    ).toFixed(2)
                  }}
                  <span
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.click_cost !== 0
                    "
                    :class="
                      (record as any)._parent.notification_item.metric_window
                        .delta.click_cost > 0
                        ? 'text-green-500'
                        : 'text-red-500'
                    "
                    >{{
                      (record as any)._parent.notification_item.metric_window
                        .delta.click_cost > 0
                        ? '↑'
                        : '↓'
                    }}</span
                  >
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else-if="column.key === 'impression_cost'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.impression_cost != null
                  "
                >
                  ${{
                    Number(
                      (record as any)._parent.notification_item.metric_window
                        .delta.impression_cost,
                    ).toFixed(2)
                  }}
                  <span
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.impression_cost !== 0
                    "
                    :class="
                      (record as any)._parent.notification_item.metric_window
                        .delta.impression_cost > 0
                        ? 'text-green-500'
                        : 'text-red-500'
                    "
                    >{{
                      (record as any)._parent.notification_item.metric_window
                        .delta.impression_cost > 0
                        ? '↑'
                        : '↓'
                    }}</span
                  >
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else-if="column.key === 'subscription_cost'">
              <span class="text-xs">
                <template
                  v-if="
                    (record as any)._parent.notification_item.metric_window
                      .delta?.subscription_cost != null
                  "
                >
                  ${{
                    Number(
                      (record as any)._parent.notification_item.metric_window
                        .delta.subscription_cost,
                    ).toFixed(2)
                  }}
                  <span
                    v-if="
                      (record as any)._parent.notification_item.metric_window
                        .delta.subscription_cost !== 0
                    "
                    :class="
                      (record as any)._parent.notification_item.metric_window
                        .delta.subscription_cost > 0
                        ? 'text-green-500'
                        : 'text-red-500'
                    "
                    >{{
                      (record as any)._parent.notification_item.metric_window
                        .delta.subscription_cost > 0
                        ? '↑'
                        : '↓'
                    }}</span
                  >
                </template>
                <span v-else class="text-gray-300">/</span>
              </span>
            </template>
            <template v-else>
              <span class="text-gray-300">/</span>
            </template>
          </template>

          <!-- ── main row ── -->
          <template v-else-if="column.key === 'project'">
            <div class="flex items-center gap-1">
              <button
                v-if="(record as any).notification_item?.metric_window"
                class="shrink-0 text-gray-400 hover:text-blue-500"
                @click.stop="toggleExpand((record as any).id)"
              >
                {{ expandedIds.includes((record as any).id) ? '▾' : '▸' }}
              </button>
              <span class="text-xs">{{
                record.notification_item?.project_name || '-'
              }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'account'">
            <span class="text-xs">{{
              record.notification_item?.account_name || '-'
            }}</span>
          </template>
          <template v-else-if="column.key === 'agent_line'">
            <span class="text-xs">{{
              record.notification_item?.agent_line || '-'
            }}</span>
          </template>
          <template v-else-if="column.key === 'campaign'">
            <Tooltip :title="record.notification_item?.campaign_name">
              <span class="text-xs">{{
                record.notification_item?.campaign_name || '-'
              }}</span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'campaign_id'">
            <Tooltip :title="record.notification_item?.campaign_id">
              <span class="text-xs text-gray-500">{{
                record.notification_item?.campaign_id || '-'
              }}</span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'adset_name'">
            <Tooltip :title="record.notification_item?.adset_name">
              <span class="text-xs">{{
                record.notification_item?.adset_name || '-'
              }}</span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'adset_id'">
            <Tooltip :title="record.notification_item?.adset_id">
              <span class="text-xs text-gray-500">{{
                record.notification_item?.adset_id || '-'
              }}</span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'ad_name'">
            <Tooltip :title="record.notification_item?.ad_name">
              <span class="text-xs">{{
                record.notification_item?.ad_name || '-'
              }}</span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'ad_id'">
            <Tooltip :title="record.notification_item?.ad_id">
              <span class="text-xs text-gray-500">{{
                record.notification_item?.ad_id || '-'
              }}</span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'spend'">
            <span class="text-xs">
              {{
                record.notification_item?.spend != null
                  ? `$${Number(record.notification_item.spend).toFixed(2)}`
                  : '-'
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'budget'">
            <span class="text-xs">
              {{
                record.notification_item?.budget != null
                  ? `$${Number(record.notification_item.budget).toFixed(2)}`
                  : '-'
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'impression_cost'">
            <span class="text-xs">
              {{
                record.notification_item?.impression_cost != null
                  ? `$${Number(record.notification_item.impression_cost).toFixed(2)}`
                  : '-'
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'click_cost'">
            <span class="text-xs">
              {{
                record.notification_item?.click_cost != null
                  ? `$${Number(record.notification_item.click_cost).toFixed(2)}`
                  : '-'
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'subscription_cost'">
            <span class="text-xs">
              {{
                record.notification_item?.subscription_cost != null
                  ? `$${Number(record.notification_item.subscription_cost).toFixed(2)}`
                  : '-'
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'purchase_cost'">
            <span class="text-xs">
              {{
                record.notification_item?.purchase_cost != null
                  ? `$${Number(record.notification_item.purchase_cost).toFixed(2)}`
                  : '-'
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'roas'">
            <span class="text-xs">{{
              record.notification_item?.purchase_roas != null
                ? Number(record.notification_item.purchase_roas).toFixed(2)
                : '-'
            }}</span>
          </template>
          <template v-else-if="column.key === 'purchases'">
            <span class="text-xs">{{
              record.notification_item?.purchases ?? '-'
            }}</span>
          </template>
          <template v-else-if="column.key === 'subscriptions'">
            <span class="text-xs">{{
              record.notification_item?.subscriptions ?? '-'
            }}</span>
          </template>
          <template v-else-if="column.key === 'registration_cost'">
            <span class="text-xs">
              {{
                record.notification_item?.registration_cost != null
                  ? `$${Number(record.notification_item.registration_cost).toFixed(2)}`
                  : '-'
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'source_type'">
            <Tag
              v-if="
                sourceOptions.find(
                  (o) => o.value === record.notification_item?.source_type,
                )
              "
              :color="
                record.notification_item?.source_type === 'ai'
                  ? 'cyan'
                  : 'orange'
              "
            >
              {{
                sourceOptions.find(
                  (o) => o.value === record.notification_item?.source_type,
                )?.label
              }}
            </Tag>
            <span v-else class="text-xs text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'source'">
            <Tooltip v-if="record.rule_name" :title="record.rule_name">
              <span class="truncate text-xs text-gray-600">{{
                record.rule_name
              }}</span>
            </Tooltip>
            <span v-else class="text-xs text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'checked_at'">
            <span class="text-xs">
              {{ record.checked_at || '-' }}
            </span>
          </template>
          <template v-else-if="column.key === 'action'">
            <span
              v-if="record?.level != activeLevel"
              class="text-xs text-gray-400"
              >--</span
            >
            <div
              v-else-if="record.notification_item?.suggested_action"
              class="flex flex-wrap items-center gap-1 text-xs"
            >
              <Tag
                :color="
                  actionTagColor(
                    record.notification_item.suggested_action.label,
                  )
                "
                class="mr-0"
              >
                {{ record.notification_item.suggested_action.label }}
              </Tag>
              <template
                v-if="
                  record.notification_item.suggested_action.type !== 'status'
                "
              >
                <span class="text-gray-800">
                  ${{
                    record.notification_item.budget ??
                    record.notification_item.suggested_action.current_value
                  }}
                </span>
                <span class="text-gray-400">→</span>
                <InputNumber
                  v-if="isSelectable(record as NotificationRecord)"
                  :min="0"
                  :value="
                    targetValues[record.id] ??
                    (record.notification_item.suggested_action as any)
                      .target_value ??
                    (record.notification_item.suggested_action as any).value
                  "
                  class="!w-20"
                  prefix="$"
                  @update:value="
                    (v) => {
                      if (v != null) targetValues[record.id] = v as number;
                    }
                  "
                />
                <span v-else class="font-medium text-teal-600">
                  ${{ Number(targetValues[record.id]).toFixed(2) }}
                </span>
              </template>
            </div>
          </template>
          <template v-else-if="column.key === 'operate'">
            <div class="flex items-center gap-1">
              <template v-if="isSelectable(asRecord(record))">
                <Button
                  :loading="processingIds.includes(record.id)"
                  @click="handleIgnore(asRecord(record))"
                >
                  忽略
                </Button>
                <Button
                  :loading="processingIds.includes(record.id)"
                  type="primary"
                  @click="handleApprove(asRecord(record))"
                >
                  执行
                </Button>
              </template>
              <Button v-else disabled>已处理</Button>
              <Button
                type="link"
                class="!px-1"
                @click="handleAnalysis(asRecord(record))"
              >
                分析
              </Button>
            </div>
          </template>
        </template>
      </Table>

      <!-- 分析弹窗 -->
      <PerformanceComparisonModal
        :open="analysisOpen"
        :record="analysisRecord"
        @update:open="(v) => (analysisOpen = v)"
      />

      <!-- 底部信息栏 -->
      <div class="mt-3 flex items-center justify-between">
        <span class="text-xs text-gray-400"
          >已选 {{ selectedIds.length }} 条</span
        >
        <div class="flex items-center gap-3">
          <Pagination
            v-model:current="page"
            v-model:page-size="pageSize"
            :total="total"
            :show-size-changer="true"
            :page-size-options="['10', '20', '50']"
            show-quick-jumper
            :show-total="(t) => `共 ${t} 条`"
            @change="loadPage"
            @show-size-change="
              () => {
                page = 1;
                loadPage();
              }
            "
          />
          <Button @click="close">关闭</Button>
        </div>
      </div>
    </div>
  </Modal>
</template>
