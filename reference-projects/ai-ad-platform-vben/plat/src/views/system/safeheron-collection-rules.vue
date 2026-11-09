<script setup lang="ts">
/* eslint-disable vue/html-closing-bracket-newline, vue/multiline-html-element-content-newline */
import type { TableColumnsType } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import type {
  SafeheronCoin,
  SafeheronDepartment,
  SafeheronRecord,
  SafeheronRule,
  SafeheronTeam,
  SafeheronUser,
  SafeheronWallet,
} from '#/api/safeheron';

import { computed, onMounted, reactive, ref, toRefs } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  DatePicker,
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

import {
  createSafeheronRule,
  deleteSafeheronRule,
  exportSafeheronRecords,
  getSafeheronDepartments,
  getSafeheronRecords,
  getSafeheronRecordStats,
  getSafeheronRules,
  getSafeheronTeams,
  getSafeheronUsers,
  getSafeheronWalletCoins,
  getSafeheronWallets,
  updateSafeheronApprovers,
  updateSafeheronRule,
  updateSafeheronRuleStatus,
} from '#/api/safeheron';
import { useListRouteState } from '#/composables/use-list-route-state';

defineOptions({ name: 'SafeheronCollectionRules' });

const loading = ref(false);
const ruleLoadError = ref('');
const optionLoadError = ref('');
const recordLoadError = ref('');
const rules = ref<SafeheronRule[]>([]);
const total = ref(0);
const page = reactive({ current: 1, pageSize: 10 });
const pageRefs = toRefs(page);
const { commitQueryState, restoreFromRoute } = useListRouteState({
  onRouteStateRestored: () => loadRules(),
  pagination: {
    defaultPageSize: 10,
    page: pageRefs.current,
    pageSize: pageRefs.pageSize,
    pageSizes: [10, 20, 50, 100],
  },
  state: {},
});
const ruleOpen = ref(false);
const ruleSaving = ref(false);
const editingRule = ref(false);
const ruleForm = reactive<Partial<SafeheronRule>>({});
const walletOptions = ref<SafeheronWallet[]>([]);
const coinOptions = ref<SafeheronCoin[]>([]);
const departmentOptions = ref<SafeheronDepartment[]>([]);

const approverOpen = ref(false);
const approverSaving = ref(false);
const teams = ref<SafeheronTeam[]>([]);
const userOptions = ref<SafeheronUser[]>([]);
const originalApprovers = ref<Record<string, unknown>>({});

const recordOpen = ref(false);
const recordLoading = ref(false);
const activeTeamId = ref<string>('');
const records = ref<SafeheronRecord[]>([]);
const recordTotal = ref(0);
const recordPage = reactive({ current: 1, pageSize: 10 });
const recordFilter = reactive({
  dateRange: undefined as [Dayjs, Dayjs] | undefined,
  deptId: undefined as string | undefined,
  status: undefined as number | undefined,
  taskId: '',
});
const recordStats = reactive({
  successRate: 0,
  todayAmountUsd: 0,
  todayCount: 0,
  todayGas: 0,
});

const ruleColumns: TableColumnsType = [
  { dataIndex: 'coinKey', title: '区块网络', width: 150 },
  { dataIndex: 'deptName', title: '所属部门', width: 170 },
  { dataIndex: 'collectAccountName', title: '归集目标钱包', width: 190 },
  { dataIndex: 'thresholdUsd', title: '触发条件', width: 150 },
  { dataIndex: 'frequency', title: '归集频率', width: 150 },
  { dataIndex: 'effectiveStatus', title: '生效状态', width: 120 },
  { dataIndex: 'status', title: '启用状态', width: 110 },
  { fixed: 'right', key: 'action', title: '操作', width: 140 },
];
const recordColumns: TableColumnsType = [
  { dataIndex: 'createTime', title: '时间', width: 180 },
  { dataIndex: 'deptName', title: '部门 / 任务', width: 170 },
  { dataIndex: 'sourceAccountName', title: '被归集钱包', width: 160 },
  { dataIndex: 'destAccountName', title: '目标钱包', width: 160 },
  { dataIndex: 'coinName', title: '币种', width: 100 },
  { dataIndex: 'amount', title: '金额', width: 140 },
  { dataIndex: 'gasFee', title: 'Gas 费', width: 110 },
  { dataIndex: 'status', title: '状态', width: 100 },
  { dataIndex: 'transactionType', title: '交易类型', width: 150 },
  { dataIndex: 'approverName', title: '审批人', width: 120 },
  { dataIndex: 'approveResult', title: '审批状态', width: 120 },
  { dataIndex: 'txHash', title: 'TxHash', width: 220 },
  { dataIndex: 'remark', title: '备注', width: 180 },
];

const frequencyOptions = [
  { label: '每 10 分钟一次', value: 10 },
  { label: '每 30 分钟一次', value: 30 },
  { label: '每 1 小时一次', value: 60 },
  { label: '每 6 小时一次', value: 360 },
  { label: '每天一次', value: 1440 },
];

const departmentSelectOptions = computed(() =>
  flattenDepartments(departmentOptions.value),
);
const loadError = computed(() => ruleLoadError.value || optionLoadError.value);

function flattenDepartments(
  nodes: SafeheronDepartment[],
  prefix = '',
): Array<{ label: string; value: string }> {
  return (nodes ?? []).flatMap((node) => {
    const label = `${prefix}${node.label}`;
    return [
      { label, value: String(node.id) },
      ...flattenDepartments(node.children ?? [], `${prefix}— `),
    ];
  });
}

function formatFrequency(minutes: number) {
  if (minutes < 60) return `每 ${minutes} 分钟一次`;
  if (minutes % 1440 === 0) return `每 ${minutes / 1440} 天一次`;
  if (minutes % 60 === 0) return `每 ${minutes / 60} 小时一次`;
  return `每 ${minutes} 分钟一次`;
}

function effectText(status?: number) {
  if (status === 1) return '已生效';
  if (status === 2) return '异常';
  return '已关闭';
}

function effectColor(status?: number) {
  if (status === 1) return 'success';
  if (status === 2) return 'error';
  return 'default';
}

async function loadRules(showMessage = false) {
  loading.value = true;
  try {
    const result = await getSafeheronRules({
      pageNum: page.current,
      pageSize: page.pageSize,
    });
    rules.value = result.items;
    total.value = result.total;
    ruleLoadError.value = '';
    if (showMessage) message.success('归集规则已刷新');
  } catch {
    rules.value = [];
    total.value = 0;
    ruleLoadError.value = '归集规则暂时无法加载，请稍后重试。';
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  try {
    const [wallets, departments] = await Promise.all([
      getSafeheronWallets(),
      getSafeheronDepartments(),
    ]);
    walletOptions.value = wallets;
    departmentOptions.value = departments;
    optionLoadError.value = '';
  } catch {
    walletOptions.value = [];
    departmentOptions.value = [];
    optionLoadError.value = '钱包或部门选项暂时无法加载，请稍后重试。';
  }
}

function resetRuleForm() {
  Object.keys(ruleForm).forEach((key) => delete (ruleForm as any)[key]);
  Object.assign(ruleForm, {
    frequency: 30,
    gasStationEnabled: 1,
    status: 1,
    thresholdUsd: 10,
  });
  coinOptions.value = [];
}

async function openRule(rule?: Record<string, any> | SafeheronRule) {
  resetRuleForm();
  editingRule.value = Boolean(rule);
  if (rule) Object.assign(ruleForm, rule);
  ruleOpen.value = true;
  if (ruleForm.collectAccountKey)
    await loadCoins(String(ruleForm.collectAccountKey), false);
}

async function loadCoins(accountKey?: string, reset = true) {
  if (reset) ruleForm.coinKey = undefined;
  if (!accountKey) return void (coinOptions.value = []);
  try {
    coinOptions.value = await getSafeheronWalletCoins(accountKey);
  } catch {
    coinOptions.value = [];
  }
  const wallet = walletOptions.value.find(
    (item) => item.accountKey === accountKey,
  );
  ruleForm.collectAccountName = wallet?.accountName;
}

async function saveRule() {
  if (
    !ruleForm.deptId ||
    !ruleForm.collectAccountKey ||
    !ruleForm.coinKey ||
    !ruleForm.frequency ||
    ruleForm.thresholdUsd === undefined
  ) {
    return void message.warning(
      '请完整填写部门、目标钱包、区块网络、触发条件和频率',
    );
  }
  ruleSaving.value = true;
  try {
    await (editingRule.value
      ? updateSafeheronRule(ruleForm)
      : createSafeheronRule(ruleForm));
    ruleOpen.value = false;
    message.success(editingRule.value ? '归集规则已保存' : '归集规则已创建');
    await loadRules();
  } finally {
    ruleSaving.value = false;
  }
}

async function toggleRule(
  rule: Record<string, any> | SafeheronRule,
  checked: boolean,
) {
  const previous = rule.status;
  rule.status = checked ? 1 : 0;
  try {
    await updateSafeheronRuleStatus(rule.id, rule.status);
    message.success(checked ? '规则已启用' : '规则已停用');
    await loadRules();
  } catch {
    rule.status = previous;
  }
}

function removeRule(rule: Record<string, any> | SafeheronRule) {
  Modal.confirm({
    cancelText: '取消',
    content: '删除后无法恢复，已产生的归集记录不会被删除。',
    okButtonProps: { danger: true },
    okText: '删除',
    title: `删除 ${rule.coinKey} 归集规则？`,
    async onOk() {
      await deleteSafeheronRule(rule.id);
      rules.value = rules.value.filter((item) => item.id !== rule.id);
      message.success('归集规则已删除');
    },
  });
}

async function openApprovers() {
  approverOpen.value = true;
  try {
    const [teamList, users] = await Promise.all([
      getSafeheronTeams(),
      getSafeheronUsers(),
    ]);
    teams.value = teamList;
    userOptions.value = users;
  } catch {
    teams.value = [];
    userOptions.value = [];
  }
  originalApprovers.value = Object.fromEntries(
    teams.value.map((item) => [String(item.teamId), item.approverId]),
  );
}

async function saveApprovers() {
  if (teams.value.some((team) => !team.approverId))
    return void message.warning('请为每个团队选择审批人');
  const changed = teams.value.filter(
    (team) =>
      String(team.approverId) !==
      String(originalApprovers.value[String(team.teamId)]),
  );
  if (changed.length === 0) return void (approverOpen.value = false);
  approverSaving.value = true;
  try {
    await updateSafeheronApprovers(
      changed.map(({ teamId, approverId }) => ({
        approverId: approverId as string,
        teamId,
      })),
    );
    approverOpen.value = false;
    message.success('归集审批人已保存');
  } finally {
    approverSaving.value = false;
  }
}

function recordQuery() {
  return {
    deptId: recordFilter.deptId,
    endDate: recordFilter.dateRange?.[1]?.format?.('YYYY-MM-DD'),
    includeAllType: true,
    startDate: recordFilter.dateRange?.[0]?.format?.('YYYY-MM-DD'),
    status: recordFilter.status,
    taskId: recordFilter.taskId || undefined,
    teamId: activeTeamId.value,
  };
}

async function openRecords() {
  recordOpen.value = true;
  try {
    teams.value = await getSafeheronTeams();
    activeTeamId.value ||= String(teams.value[0]?.teamId ?? '');
  } catch {
    teams.value = [];
    activeTeamId.value = '';
  }
  await loadRecords();
}

async function loadRecords() {
  recordLoading.value = true;
  try {
    const [listResult, statistics] = await Promise.all([
      getSafeheronRecords({
        ...recordQuery(),
        pageNum: recordPage.current,
        pageSize: recordPage.pageSize,
      }),
      getSafeheronRecordStats(recordQuery()),
    ]);
    records.value = listResult.items;
    recordTotal.value = listResult.total;
    Object.assign(recordStats, statistics);
    recordLoadError.value = '';
  } catch {
    records.value = [];
    recordTotal.value = 0;
    Object.assign(recordStats, {
      successRate: 0,
      todayAmountUsd: 0,
      todayCount: 0,
      todayGas: 0,
    });
    recordLoadError.value = '归集记录暂时无法加载，请稍后重试。';
  } finally {
    recordLoading.value = false;
  }
}

function resetRecordFilter() {
  Object.assign(recordFilter, {
    dateRange: undefined,
    deptId: undefined,
    status: undefined,
    taskId: '',
  });
  recordPage.current = 1;
  void loadRecords();
}

async function exportRecords() {
  const blob = await exportSafeheronRecords(recordQuery());
  const url = URL.createObjectURL(blob as Blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `Safeheron归集记录_${Date.now()}.xlsx`;
  link.click();
  URL.revokeObjectURL(url);
}

function recordStatusText(status: number) {
  if (status === 1) return '成功';
  if (status === 2) return '失败';
  return '进行中';
}

function transactionText(type: string) {
  return (
    (
      {
        AUTO_FUEL: 'Gas 加油',
        AUTO_SWEEP: 'Safeheron 自动归集',
        NORMAL: '系统归集',
      } as Record<string, string>
    )[type] ??
    type ??
    '—'
  );
}

async function handleRulePageChange(pagination: {
  current?: number;
  pageSize?: number;
}) {
  const sizeChanged =
    pagination.pageSize !== undefined && pagination.pageSize !== page.pageSize;
  page.pageSize = pagination.pageSize || 10;
  page.current = sizeChanged ? 1 : pagination.current || 1;
  await commitQueryState();
  await loadRules();
}

onMounted(async () => {
  await restoreFromRoute();
  await Promise.all([loadRules(), loadOptions()]);
});
</script>

<template>
  <main
    class="adpulse-section-page system-management-page safeheron-rules-page min-h-full text-slate-700"
  >
    <section class="mx-auto max-w-[1700px]">
      <header
        class="business-page-header flex flex-col rounded-xl border border-slate-200 bg-white lg:flex-row lg:items-center lg:justify-between"
      >
        <div>
          <h1 class="m-0 font-semibold text-slate-900">Safeheron 归集规则</h1>
          <p class="mb-0 mt-1 text-sm text-slate-500">
            配置归集阈值、频率、链上费用与审批责任人，完整追踪每笔归集。
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button :loading="loading" @click="loadRules(true)">
            <IconifyIcon icon="lucide:refresh-cw" /> 刷新 </Button
          ><Button @click="openRecords">
            <IconifyIcon icon="lucide:receipt-text" /> 归集记录 </Button
          ><Button @click="openApprovers">
            <IconifyIcon icon="lucide:user-check" /> 审批人设置 </Button
          ><Button type="primary" @click="openRule()">
            <IconifyIcon icon="lucide:plus" /> 新增规则
          </Button>
        </div>
      </header>

      <Alert
        v-if="loadError"
        banner
        :message="loadError"
        show-icon
        type="error"
      >
        <template #action>
          <Button
            @click="
              loadRules();
              loadOptions();
            "
          >
            重新加载
          </Button>
        </template>
      </Alert>

      <div class="grid gap-3 md:grid-cols-3">
        <Card>
          <Statistic title="规则总数" :value="total" />
          <div class="mt-2 text-xs text-slate-500">覆盖部门级自动归集策略</div>
        </Card>
        <Card>
          <Statistic
            title="启用规则"
            :value="rules.filter((item) => item.status === 1).length"
            :value-style="{ color: '#059669' }"
          />
          <div class="mt-2 text-xs text-slate-500">任务会按设定频率执行</div>
        </Card>
        <Card>
          <Statistic
            title="异常规则"
            :value="rules.filter((item) => item.effectiveStatus === 2).length"
            :value-style="{ color: '#e11d48' }"
          />
          <div class="mt-2 text-xs text-slate-500">
            请及时检查钱包、网络和审批人
          </div>
        </Card>
      </div>

      <Card
        :body-style="{ padding: 0 }"
        class="overflow-hidden border-0 shadow-sm"
      >
        <div class="border-b border-slate-100 p-5">
          <div class="font-semibold text-slate-900">规则列表</div>
          <div class="mt-1 text-sm text-slate-500">
            所有规则由 Mpower 服务统一保存和管理
          </div>
        </div>
        <Table
          :columns="ruleColumns"
          :data-source="rules"
          :loading="loading"
          :pagination="{
            current: page.current,
            pageSize: page.pageSize,
            showSizeChanger: true,
            total,
          }"
          :scroll="{ x: 1200 }"
          row-key="id"
          @change="handleRulePageChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'coinKey'">
              <span class="font-semibold text-slate-900">{{
                record.coinKey
              }}</span>
            </template>
            <template v-else-if="column.dataIndex === 'thresholdUsd'">
              价值 ≥ {{ record.thresholdUsd }} USD
            </template>
            <template v-else-if="column.dataIndex === 'frequency'">
              {{ formatFrequency(Number(record.frequency)) }}
            </template>
            <template v-else-if="column.dataIndex === 'effectiveStatus'">
              <Tag :color="effectColor(record.effectiveStatus)">
                {{ effectText(record.effectiveStatus) }}
              </Tag>
            </template>
            <template v-else-if="column.dataIndex === 'status'">
              <Switch
                :checked="Number(record.status) === 1"
                @change="(checked) => toggleRule(record, Boolean(checked))"
              />
            </template>
            <template v-else-if="column.key === 'action'">
              <Button type="link" @click="openRule(record)"> 编辑 </Button
              ><Button danger type="link" @click="removeRule(record)">
                删除
              </Button>
            </template>
          </template>
        </Table>
      </Card>
    </section>

    <Modal
      v-model:open="ruleOpen"
      :confirm-loading="ruleSaving"
      ok-text="保存规则"
      :title="editingRule ? '编辑归集规则' : '新增归集规则'"
      width="680px"
      @ok="saveRule"
    >
      <Form layout="vertical">
        <div class="grid gap-x-4 sm:grid-cols-2">
          <Form.Item label="所属部门" required>
            <Select
              v-model:value="ruleForm.deptId"
              :options="departmentSelectOptions"
              placeholder="请选择部门"
              show-search
            /> </Form.Item
          ><Form.Item label="归集目标钱包" required>
            <Select
              v-model:value="ruleForm.collectAccountKey"
              :options="
                walletOptions.map((item) => ({
                  label: item.accountName,
                  value: item.accountKey,
                }))
              "
              placeholder="请选择目标钱包"
              @change="(value) => loadCoins(String(value))"
            /> </Form.Item
          ><Form.Item label="区块网络" required>
            <Select
              v-model:value="ruleForm.coinKey"
              :disabled="!ruleForm.collectAccountKey"
              :options="
                coinOptions.map((item) => ({
                  label: item.coinName || item.coinKey,
                  value: item.coinKey,
                }))
              "
              placeholder="请先选择目标钱包"
            /> </Form.Item
          ><Form.Item label="归集频率" required>
            <Select
              v-model:value="ruleForm.frequency"
              :options="frequencyOptions"
            /> </Form.Item
          ><Form.Item label="触发条件" required>
            <InputNumber
              v-model:value="ruleForm.thresholdUsd"
              class="w-full"
              :min="0"
              :precision="2"
              addon-before="价值 ≥"
              addon-after="USD"
            /> </Form.Item
          ><Form.Item label="交易审批及签名人">
            <Input
              v-model:value="ruleForm.signer"
              placeholder="请输入审批及签名人"
            /> </Form.Item
          ><Form.Item label="网络费用上限">
            <InputNumber
              v-model:value="ruleForm.maxTxFee"
              class="w-full"
              :min="0"
              :precision="6"
              addon-before="≤"
              :addon-after="
                String(ruleForm.coinKey || '').includes('TRC') ? 'TRX' : 'ETH'
              "
            /> </Form.Item
          ><Form.Item label="预留 Gas 费">
            <InputNumber
              v-model:value="ruleForm.reserveGas"
              class="w-full"
              :min="0"
              :precision="6"
              :addon-after="
                String(ruleForm.coinKey || '').includes('TRC') ? 'TRX' : 'ETH'
              "
            />
          </Form.Item>
        </div>
        <Form.Item label="Gas Station">
          <Radio.Group v-model:value="ruleForm.gasStationEnabled">
            <Radio :value="1">开启，自动设置合理 Gas</Radio
            ><Radio :value="0">关闭</Radio>
          </Radio.Group>
        </Form.Item>
      </Form>
    </Modal>

    <Modal
      v-model:open="approverOpen"
      :confirm-loading="approverSaving"
      ok-text="保存设置"
      title="归集审批人设置"
      width="720px"
      @ok="saveApprovers"
    >
      <Alert
        class="mb-4"
        message="每个 Safeheron 团队必须设置一名自动审批责任人。"
        show-icon
        type="info"
      />
      <Table
        :columns="[
          { title: '团队', dataIndex: 'teamName', width: 220 },
          { title: '审批人', key: 'approver' },
        ]"
        :data-source="teams"
        :pagination="false"
        row-key="teamId"
      >
        <template #bodyCell="{ column, record }">
          <Select
            v-if="column.key === 'approver'"
            v-model:value="record.approverId"
            class="w-full"
            :options="
              userOptions.map((user) => ({
                label: user.nickName || user.userName,
                value: user.userId,
              }))
            "
            placeholder="请选择审批人"
            show-search
          />
        </template>
      </Table>
    </Modal>

    <Modal
      v-model:open="recordOpen"
      :footer="null"
      title="Safeheron 归集记录"
      width="min(1500px, 96vw)"
    >
      <Tabs
        v-model:active-key="activeTeamId"
        @change="
          recordPage.current = 1;
          loadRecords();
        "
      >
        <Tabs.TabPane
          v-for="team in teams"
          :key="String(team.teamId)"
          :tab="team.teamName"
        />
      </Tabs>
      <Alert
        v-if="recordLoadError"
        class="mb-4"
        :message="recordLoadError"
        show-icon
        type="error"
      >
        <template #action>
          <Button @click="loadRecords">重新加载</Button>
        </template>
      </Alert>
      <div class="mb-4 rounded-lg bg-slate-50 p-4">
        <Form layout="vertical">
          <div class="grid gap-x-3 md:grid-cols-3 xl:grid-cols-6">
            <Form.Item label="部门">
              <Select
                v-model:value="recordFilter.deptId"
                allow-clear
                :options="departmentSelectOptions"
                placeholder="全部部门"
                show-search
              /> </Form.Item
            ><Form.Item label="项目 / 任务 ID">
              <Input
                v-model:value="recordFilter.taskId"
                allow-clear
                placeholder="请输入"
              /> </Form.Item
            ><Form.Item label="状态">
              <Select
                v-model:value="recordFilter.status"
                allow-clear
                :options="[
                  { label: '进行中', value: 0 },
                  { label: '成功', value: 1 },
                  { label: '失败', value: 2 },
                ]"
                placeholder="全部状态"
              /> </Form.Item
            ><Form.Item class="xl:col-span-2" label="时间范围">
              <DatePicker.RangePicker
                v-model:value="recordFilter.dateRange"
                class="w-full"
              /> </Form.Item
            ><Form.Item label="操作">
              <div class="flex gap-2">
                <Button
                  type="primary"
                  @click="
                    recordPage.current = 1;
                    loadRecords();
                  "
                >
                  查询 </Button
                ><Button @click="resetRecordFilter">重置</Button>
              </div>
            </Form.Item>
          </div>
        </Form>
      </div>
      <div class="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <Statistic
            title="今日归集笔数"
            :value="recordStats.todayCount"
          /> </Card
        ><Card>
          <Statistic
            prefix="$"
            title="今日归集总额"
            :value="recordStats.todayAmountUsd"
            :precision="2"
          /> </Card
        ><Card>
          <Statistic
            suffix="%"
            title="成功率"
            :value="recordStats.successRate"
            :value-style="{ color: '#059669' }"
          /> </Card
        ><Card>
          <Statistic title="今日 Gas 消耗" :value="recordStats.todayGas" />
        </Card>
      </div>
      <div class="mb-3 flex justify-end">
        <Button @click="exportRecords">
          <IconifyIcon icon="lucide:download" /> 导出记录
        </Button>
      </div>
      <Table
        :columns="recordColumns"
        :data-source="records"
        :loading="recordLoading"
        :pagination="{
          current: recordPage.current,
          pageSize: recordPage.pageSize,
          showSizeChanger: true,
          total: recordTotal,
        }"
        :scroll="{ x: 1900 }"
        row-key="id"
        @change="
          (pagination) => {
            recordPage.current = pagination.current || 1;
            recordPage.pageSize = pagination.pageSize || 10;
            loadRecords();
          }
        "
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'deptName'">
            <div>{{ record.deptName || '—' }}</div>
            <div class="text-xs text-slate-400">
              {{ record.taskName }}
            </div> </template
          ><template v-else-if="column.dataIndex === 'amount'">
            <div>{{ record.amount }}</div>
            <div class="text-xs text-slate-400">
              ≈ ${{ record.amountUsd }}
            </div> </template
          ><template v-else-if="column.dataIndex === 'status'">
            <Tag
              :color="
                record.status === 1
                  ? 'success'
                  : record.status === 2
                    ? 'error'
                    : 'processing'
              "
            >
              {{ recordStatusText(record.status) }}
            </Tag> </template
          ><template v-else-if="column.dataIndex === 'transactionType'">
            {{ transactionText(record.transactionType) }} </template
          ><template v-else-if="column.dataIndex === 'approveResult'">
            <Tag
              :color="
                record.approveResult === 1
                  ? 'success'
                  : record.approveResult === 0
                    ? 'error'
                    : 'warning'
              "
            >
              {{
                record.approveResult === 1
                  ? '通过'
                  : record.approveResult === 0
                    ? '拒绝'
                    : record.approveResult === 2
                      ? '审批中'
                      : '未发送'
              }}
            </Tag>
          </template>
        </template>
      </Table>
    </Modal>
  </main>
</template>

<style scoped>
.safeheron-rules-page {
  padding: var(--adpulse-page-gutter);
  background: hsl(var(--background));
}

.safeheron-rules-page > section {
  display: flex;
  flex-direction: column;
  gap: var(--adpulse-section-gap);
}

.safeheron-rules-page h1 {
  font-size: var(--adpulse-page-title-size);
  line-height: 1.35;
}

.safeheron-rules-page .business-page-header {
  min-height: var(--adpulse-page-header-min-height);
  gap: var(--adpulse-action-gap);
  padding: var(--adpulse-page-header-padding-block) var(--adpulse-page-gutter);
}
</style>
