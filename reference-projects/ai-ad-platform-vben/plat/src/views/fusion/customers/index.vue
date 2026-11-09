<script lang="ts" setup>
import type { FormProps, TableColumnsType } from 'ant-design-vue';

import type {
  CustomerCooperationMode,
  CustomerProjectOverview,
  CustomerStatus,
  CustomerSummary,
  CustomerUpsertPayload,
  PlatformCode,
  ProjectSettlementStatus,
  ProjectStatus,
} from '#/api';

import {
  computed,
  nextTick,
  onMounted,
  reactive,
  ref,
  toRef,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Drawer,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Pagination,
  Row,
  Select,
  Skeleton,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  getCustomerListApi,
  getCustomerProjectOverviewApi,
  saveCustomerApi,
} from '#/api';
import { useListRouteState } from '#/composables/use-list-route-state';

interface CustomerFormRef {
  clearValidate: () => void;
  validate: () => Promise<unknown>;
  validateFields: (fields: string[]) => Promise<unknown>;
}

interface CustomerFilterState {
  cooperationMode?: CustomerCooperationMode;
  dateRange?: [string, string];
  keyword: string;
  status?: CustomerStatus;
}

const route = useRoute();
const router = useRouter();
const customers = ref<CustomerSummary[]>([]);
const loading = ref(false);
const loadError = ref('');
const drawerOpen = ref(false);
const editingCustomer = ref<CustomerSummary | null>(null);
const overviewOpen = ref(false);
const overviewLoading = ref(false);
const overviewError = ref('');
const overviewCustomer = ref<CustomerSummary | null>(null);
const projectOverview = ref<CustomerProjectOverview | null>(null);
const formRef = ref<CustomerFormRef | null>(null);
const saving = ref(false);
const saveError = ref('');
const initialFormSnapshot = ref('');

const filters = reactive<CustomerFilterState>({
  cooperationMode: undefined,
  dateRange: undefined,
  keyword: '',
  status: undefined,
});

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
});

const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    onRouteStateRestored: () => loadCustomers(),
    pagination: {
      defaultPageSize: 20,
      page: toRef(pagination, 'current'),
      pageSize: toRef(pagination, 'pageSize'),
      pageSizes: [10, 20, 50, 100],
    },
    state: filters,
  });

const formState = reactive<CustomerUpsertPayload>(createDefaultForm());

const cooperationModeMeta: Record<
  CustomerCooperationMode,
  { color: string; label: string }
> = {
  POSTPAID: { color: 'purple', label: '后付' },
  PREPAID: { color: 'blue', label: '预付' },
  PREPAID_ACTUAL: { color: 'cyan', label: '预付实销' },
};

const statusMeta: Record<CustomerStatus, { color: string; label: string }> = {
  0: { color: 'default', label: '未开始' },
  1: { color: 'green', label: '进行中' },
  2: { color: 'orange', label: '已暂停' },
  3: { color: 'default', label: '已结束' },
};

const projectStatusMeta: Record<
  ProjectStatus,
  { color: string; label: string }
> = {
  active: { color: 'green', label: '进行中' },
  archived: { color: 'default', label: '已归档' },
  draft: { color: 'default', label: '草稿' },
  ended: { color: 'red', label: '已结束' },
  paused: { color: 'orange', label: '已暂停' },
  pending: { color: 'blue', label: '待启动' },
};

const settlementStatusMeta: Record<
  ProjectSettlementStatus,
  { color: string; label: string }
> = {
  partial: { color: 'orange', label: '部分结算' },
  settled: { color: 'green', label: '已结算' },
  unsettled: { color: 'default', label: '未结算' },
};

const platformLabels: Record<PlatformCode, string> = {
  facebook: 'Facebook',
  google: 'Google',
  tiktok: 'TikTok',
};

const cooperationModeOptions = Object.entries(cooperationModeMeta).map(
  ([value, item]) => ({
    label: item.label,
    value: value as CustomerCooperationMode,
  }),
);

const statusOptions = Object.entries(statusMeta).map(([value, item]) => ({
  label: item.label,
  value: Number(value) as CustomerStatus,
}));

const columns: TableColumnsType<CustomerSummary> = [
  { dataIndex: 'name', key: 'name', title: '客户名称', width: 190 },
  { key: 'cooperationMode', title: '合作模式', width: 120 },
  { dataIndex: 'policy', key: 'policy', title: '政策', width: 220 },
  { key: 'status', title: '状态', width: 110 },
  { key: 'cooperationPeriod', title: '合作周期', width: 210 },
  { key: 'projectCount', title: '关联项目', width: 120 },
  { dataIndex: 'remark', key: 'remark', title: '备注', width: 240 },
  { dataIndex: 'createdAt', key: 'createdAt', title: '创建时间', width: 170 },
  { dataIndex: 'updatedAt', key: 'updatedAt', title: '更新时间', width: 170 },
  { fixed: 'right', key: 'actions', title: '操作', width: 170 },
];

const overviewColumns: TableColumnsType<
  CustomerProjectOverview['projects'][number]
> = [
  { key: 'project', title: '项目', width: 260 },
  { key: 'spend', title: '累计消耗', width: 150 },
  { key: 'settlement', title: '结算状态', width: 180 },
  { key: 'roi', title: '已完成 ROI', width: 120 },
  { key: 'attribution', title: '归因', width: 110 },
  {
    dataIndex: 'metricCutoff',
    key: 'metricCutoff',
    title: '数据截止',
    width: 160,
  },
];

const tablePagination = computed(() => ({
  current: pagination.current,
  pageSize: pagination.pageSize,
  pageSizeOptions: ['10', '20', '50', '100'],
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条客户记录`,
  total: pagination.total,
}));

const isFormDirty = computed(
  () => serializeForm() !== initialFormSnapshot.value,
);

const formRules: FormProps['rules'] = {
  cooperationMode: [
    { required: true, message: '请选择合作模式', trigger: 'change' },
  ],
  endDate: [{ trigger: 'change', validator: validateEndDate }],
  name: [
    {
      required: true,
      message: '请输入客户名称',
      trigger: ['blur', 'change'],
      whitespace: true,
    },
    { max: 50, message: '客户名称最多 50 个字符', trigger: 'blur' },
  ],
  remark: [{ max: 200, message: '备注最多 200 个字符', trigger: 'blur' }],
  status: [{ required: true, message: '请选择客户状态', trigger: 'change' }],
};

function createDefaultForm(): CustomerUpsertPayload {
  return {
    cooperationMode: 'PREPAID',
    endDate: undefined,
    name: '',
    policy: undefined,
    remark: undefined,
    startDate: undefined,
    status: 0,
  };
}

function serializeForm() {
  return JSON.stringify({
    cooperationMode: formState.cooperationMode,
    endDate: formState.endDate ?? '',
    id: formState.id ?? '',
    name: formState.name,
    policy: formState.policy ?? '',
    remark: formState.remark ?? '',
    startDate: formState.startDate ?? '',
    status: formState.status,
  });
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

async function validateEndDate() {
  if (
    formState.startDate &&
    formState.endDate &&
    formState.endDate < formState.startDate
  ) {
    throw new Error('结束日期不能早于开始日期');
  }
}

function revalidateEndDate() {
  formRef.value?.validateFields(['endDate']).catch(() => undefined);
}

async function loadCustomers() {
  await commitQueryState();
  loading.value = true;
  loadError.value = '';
  try {
    const result = await getCustomerListApi({
      cooperationMode: filters.cooperationMode,
      customerId: String(route.query.customerId || '') || undefined,
      endDate: filters.dateRange?.[1] || undefined,
      keyword: filters.keyword.trim() || undefined,
      page: pagination.current,
      pageSize: pagination.pageSize,
      startDate: filters.dateRange?.[0] || undefined,
      status: filters.status,
    });
    customers.value = result.items;
    pagination.total = result.total;
  } catch (error) {
    loadError.value = getErrorMessage(error, '客户列表加载失败，请稍后重试');
  } finally {
    loading.value = false;
  }
}

function searchCustomers() {
  pagination.current = 1;
  loadCustomers();
}

async function resetFilters() {
  Object.assign(filters, {
    cooperationMode: undefined,
    dateRange: undefined,
    keyword: '',
    status: undefined,
  });
  if (route.query.customerId) {
    const query = { ...route.query };
    delete query.customerId;
    await router.replace({ path: route.path, query });
  }
  await resetQueryState();
  await loadCustomers();
}

function handleTableChange(nextPagination: {
  current?: number;
  pageSize?: number;
}) {
  const nextPageSize = nextPagination.pageSize ?? pagination.pageSize;
  pagination.current =
    nextPageSize === pagination.pageSize ? (nextPagination.current ?? 1) : 1;
  pagination.pageSize = nextPageSize;
  loadCustomers();
}

function handlePageChange(current: number, currentPageSize: number) {
  handleTableChange({ current, pageSize: currentPageSize });
}

function prepareDrawer(customer?: CustomerSummary | Record<string, any>) {
  const current = customer as CustomerSummary | undefined;
  editingCustomer.value = current ?? null;
  saveError.value = '';
  Object.assign(
    formState,
    current
      ? {
          cooperationMode: current.cooperationMode,
          endDate: current.endDate,
          id: current.id,
          name: current.name,
          policy: current.policy,
          remark: current.remark,
          startDate: current.startDate,
          status: current.status,
        }
      : createDefaultForm(),
  );
  if (!current) delete formState.id;
  initialFormSnapshot.value = serializeForm();
  drawerOpen.value = true;
  nextTick(() => formRef.value?.clearValidate());
}

function closeDrawer() {
  drawerOpen.value = false;
  saveError.value = '';
}

function requestCloseDrawer() {
  if (saving.value) return;
  if (!isFormDirty.value) {
    closeDrawer();
    return;
  }
  Modal.confirm({
    cancelText: '继续编辑',
    content: '关闭后，本次未保存的客户信息将丢失。',
    okText: '放弃修改',
    okType: 'danger',
    onOk: closeDrawer,
    title: '确认放弃未保存内容？',
  });
}

function normalizeOptionalValue(value?: string) {
  const normalized = value?.trim();
  return normalized || undefined;
}

async function saveCustomer() {
  saveError.value = '';
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }

  saving.value = true;
  try {
    await saveCustomerApi({
      cooperationMode: formState.cooperationMode,
      endDate: normalizeOptionalValue(formState.endDate),
      id: formState.id,
      name: formState.name.trim(),
      policy: normalizeOptionalValue(formState.policy),
      remark: normalizeOptionalValue(formState.remark),
      startDate: normalizeOptionalValue(formState.startDate),
      status: formState.status,
    });
    message.success(editingCustomer.value ? '客户信息已更新' : '客户创建成功');
    initialFormSnapshot.value = serializeForm();
    closeDrawer();
    if (!editingCustomer.value) pagination.current = 1;
    await loadCustomers();
  } catch (error) {
    saveError.value = getErrorMessage(error, '保存失败，请检查信息后重试');
  } finally {
    saving.value = false;
  }
}

function formatMoney(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat('zh-CN', {
      currency,
      maximumFractionDigits: currency === 'JPY' ? 0 : 2,
      style: 'currency',
    }).format(amount);
  } catch {
    return `${currency} ${amount.toLocaleString('zh-CN')}`;
  }
}

function formatRoi(value?: number) {
  if (value === undefined) return '待归因';
  return `${(value * 100).toFixed(1)}%`;
}

function formatOverviewRoi(overview: CustomerProjectOverview) {
  if (overview.summary.realizedRoi !== undefined) {
    return formatRoi(overview.summary.realizedRoi);
  }
  if (
    overview.summary.realizedProjectCount > 0 &&
    overview.summary.spendByCurrency.length > 1
  ) {
    return '按币种查看';
  }
  return '待归因';
}

async function openCustomerProjects(
  customer: CustomerSummary | Record<string, any>,
) {
  const current = customer as CustomerSummary;
  overviewCustomer.value = current;
  projectOverview.value = null;
  overviewError.value = '';
  overviewOpen.value = true;
  overviewLoading.value = true;
  try {
    projectOverview.value = await getCustomerProjectOverviewApi(current.id);
  } catch (error) {
    overviewError.value = getErrorMessage(
      error,
      '客户经营数据加载失败，请稍后重试',
    );
  } finally {
    overviewLoading.value = false;
  }
}

function retryCustomerOverview() {
  if (overviewCustomer.value) void openCustomerProjects(overviewCustomer.value);
}

function goToCustomerProjects() {
  if (!overviewCustomer.value) return;
  overviewOpen.value = false;
  void router.push({
    path: '/fusion/projects',
    query: { customerId: overviewCustomer.value.id },
  });
}

watch(
  () => route.query.customerId,
  () => {
    pagination.current = 1;
    void loadCustomers();
  },
);

onMounted(async () => {
  await restoreFromRoute();
  await loadCustomers();
});
</script>

<template>
  <Page class="overflow-x-hidden bg-slate-50" content-class="pb-6">
    <div class="flex w-full min-w-0 flex-col gap-4">
      <section
        class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"
      >
        <div class="min-w-0">
          <h1 class="m-0 text-2xl font-semibold text-slate-950">客户管理</h1>
          <p class="mb-0 mt-2 text-sm leading-6 text-slate-600">
            独立维护广告服务客户主数据；项目创建时选择所属客户，不在此混合创建项目。
          </p>
        </div>
        <Button
          class="!inline-flex flex-none items-center justify-center whitespace-nowrap"
          type="primary"
          @click="prepareDrawer()"
        >
          <IconifyIcon icon="lucide:plus" class="shrink-0" />
          <span>新建客户</span>
        </Button>
      </section>

      <Alert v-if="loadError" :message="loadError" type="error" show-icon>
        <template #action>
          <Button @click="loadCustomers">重新加载</Button>
        </template>
      </Alert>

      <Card class="min-w-0 border-slate-200" :body-style="{ padding: 0 }">
        <div class="border-b border-slate-200 p-4">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-4">
            <Input.Search
              v-model:value="filters.keyword"
              allow-clear
              placeholder="搜索客户名称、政策或备注"
              @search="searchCustomers"
            />
            <Select
              v-model:value="filters.cooperationMode"
              allow-clear
              :options="cooperationModeOptions"
              placeholder="全部合作模式"
            />
            <Select
              v-model:value="filters.status"
              allow-clear
              :options="statusOptions"
              placeholder="全部状态"
            />
            <DatePicker.RangePicker
              v-model:value="filters.dateRange"
              class="w-full"
              :placeholder="['合作开始日期', '合作结束日期']"
              value-format="YYYY-MM-DD"
            />
          </div>
          <div class="mt-3 flex flex-wrap justify-end gap-2">
            <Button class="" @click="resetFilters">重置</Button>
            <Button class="" type="primary" @click="searchCustomers">
              搜索
            </Button>
          </div>
        </div>

        <div class="hidden min-w-0 overflow-hidden xl:block">
          <Table
            :columns="columns"
            :data-source="customers"
            :loading="loading"
            :locale="{ emptyText: '暂无客户，请先新建客户' }"
            :pagination="tablePagination"
            :scroll="{ x: 1830 }"
            row-key="id"
            @change="handleTableChange"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <button
                  class="ux-table-link focus-visible:outline-primary cursor-pointer border-0 bg-transparent p-0 text-left font-medium focus-visible:outline focus-visible:outline-2"
                  type="button"
                  @click="prepareDrawer(record)"
                >
                  {{ record.name }}
                </button>
              </template>
              <template v-else-if="column.key === 'cooperationMode'">
                <Tag
                  :color="
                    cooperationModeMeta[
                      record.cooperationMode as CustomerCooperationMode
                    ].color
                  "
                >
                  {{
                    cooperationModeMeta[
                      record.cooperationMode as CustomerCooperationMode
                    ].label
                  }}
                </Tag>
              </template>
              <template v-else-if="column.key === 'policy'">
                <Tooltip :title="record.policy || '未填写'">
                  <div class="max-w-[200px] truncate text-slate-700">
                    {{ record.policy || '-' }}
                  </div>
                </Tooltip>
              </template>
              <template v-else-if="column.key === 'status'">
                <Tag :color="statusMeta[record.status as CustomerStatus].color">
                  {{ statusMeta[record.status as CustomerStatus].label }}
                </Tag>
              </template>
              <template v-else-if="column.key === 'cooperationPeriod'">
                <span class="whitespace-nowrap text-slate-700">
                  {{ record.startDate || '未设置' }}
                  <span class="px-1 text-slate-400">—</span>
                  {{ record.endDate || '长期' }}
                </span>
              </template>
              <template v-else-if="column.key === 'projectCount'">
                <Button type="link" @click="openCustomerProjects(record)">
                  {{ record.projectCount }} 个项目
                </Button>
              </template>
              <template v-else-if="column.key === 'remark'">
                <Tooltip :title="record.remark || '未填写'">
                  <div class="max-w-[220px] truncate text-slate-600">
                    {{ record.remark || '-' }}
                  </div>
                </Tooltip>
              </template>
              <template v-else-if="column.key === 'actions'">
                <div class="flex items-center whitespace-nowrap">
                  <Button type="link" @click="prepareDrawer(record)">
                    编辑
                  </Button>
                  <Button type="link" @click="openCustomerProjects(record)">
                    查看项目
                  </Button>
                </div>
              </template>
            </template>
          </Table>
        </div>

        <div class="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 xl:hidden">
          <Card
            v-for="customer in customers"
            :key="customer.id"
            class="border-slate-200"
          >
            <div class="flex items-start justify-between gap-3">
              <button
                class="hover:text-primary focus-visible:outline-primary min-w-0 cursor-pointer truncate border-0 bg-transparent p-0 text-left font-semibold text-slate-900 focus-visible:outline focus-visible:outline-2"
                type="button"
                @click="prepareDrawer(customer)"
              >
                {{ customer.name }}
              </button>
              <Tag :color="statusMeta[customer.status].color" class="shrink-0">
                {{ statusMeta[customer.status].label }}
              </Tag>
            </div>
            <dl
              class="mt-4 grid grid-cols-[76px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm"
            >
              <dt class="text-slate-500">合作模式</dt>
              <dd class="m-0 text-slate-800">
                {{ cooperationModeMeta[customer.cooperationMode].label }}
              </dd>
              <dt class="text-slate-500">合作周期</dt>
              <dd class="m-0 text-slate-800">
                {{ customer.startDate || '未设置' }} —
                {{ customer.endDate || '长期' }}
              </dd>
              <dt class="text-slate-500">关联项目</dt>
              <dd class="m-0 text-slate-800">{{ customer.projectCount }} 个</dd>
              <dt class="text-slate-500">合作政策</dt>
              <dd class="m-0 line-clamp-2 text-slate-800">
                {{ customer.policy || '未填写' }}
              </dd>
            </dl>
            <div
              class="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3"
            >
              <Button class="" @click="prepareDrawer(customer)">
                编辑客户
              </Button>
              <Button
                class=""
                type="primary"
                ghost
                @click="openCustomerProjects(customer)"
              >
                查看项目
              </Button>
            </div>
          </Card>

          <div
            v-if="!loading && customers.length === 0"
            class="col-span-full py-10 text-center text-slate-500"
          >
            暂无客户，请先新建客户。
          </div>
        </div>

        <div
          class="flex justify-end border-t border-slate-100 px-4 py-3 xl:hidden"
        >
          <Pagination
            :current="pagination.current"
            :page-size="pagination.pageSize"
            :total="pagination.total"
            show-less-items
            show-size-changer
            @change="handlePageChange"
          />
        </div>
      </Card>
    </div>

    <Drawer
      v-model:open="overviewOpen"
      destroy-on-close
      width="min(1120px, 100vw)"
    >
      <template #title>
        <div class="min-w-0 pr-8">
          <div class="truncate text-base font-semibold text-slate-950">
            {{ overviewCustomer?.name || '客户' }} · 项目经营概览
          </div>
          <div class="mt-1 text-xs font-normal text-slate-500">
            查看该客户旗下项目的消耗、结算与已完成归因 ROI
          </div>
        </div>
      </template>

      <Skeleton
        v-if="overviewLoading"
        active
        :paragraph="{ rows: 10 }"
        :title="{ width: '42%' }"
      />

      <Alert
        v-else-if="overviewError"
        :message="overviewError"
        show-icon
        type="error"
      >
        <template #action>
          <Button @click="retryCustomerOverview">重新加载</Button>
        </template>
      </Alert>

      <template v-else-if="projectOverview">
        <Alert
          class="mb-4"
          message="累计消耗与结算金额按币种分别统计，不跨币种相加；ROI 仅统计已完成归因的数据。"
          show-icon
          type="info"
        />

        <section
          class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-4"
          aria-label="客户项目经营摘要"
        >
          <Card class="h-full border-slate-200">
            <div class="text-sm text-slate-500">旗下项目</div>
            <div
              class="mt-2 text-2xl font-semibold tabular-nums text-slate-950"
            >
              {{ projectOverview.summary.projectCount }}
            </div>
            <div class="mt-2 text-xs text-slate-500">
              进行中 {{ projectOverview.summary.activeCount }} 个
            </div>
          </Card>

          <Card class="h-full border-slate-200">
            <div class="text-sm text-slate-500">累计消耗</div>
            <div
              v-if="projectOverview.summary.spendByCurrency.length > 0"
              class="mt-2 space-y-1"
            >
              <div
                v-for="item in projectOverview.summary.spendByCurrency"
                :key="item.currency"
                class="truncate text-lg font-semibold tabular-nums text-slate-950"
                :title="formatMoney(item.amount, item.currency)"
              >
                {{ formatMoney(item.amount, item.currency) }}
              </div>
            </div>
            <div v-else class="mt-2 text-lg font-semibold text-slate-400">
              —
            </div>
            <div class="mt-2 text-xs text-slate-500">按项目实际消耗汇总</div>
          </Card>

          <Card class="h-full border-slate-200">
            <div class="text-sm text-slate-500">结算进度</div>
            <div
              class="mt-2 text-2xl font-semibold tabular-nums text-slate-950"
            >
              {{ projectOverview.summary.settledCount }} /
              {{ projectOverview.summary.projectCount }}
            </div>
            <div class="mt-2 text-xs leading-5 text-slate-500">
              待结或部分结算
              {{ projectOverview.summary.pendingSettlementCount }} 个项目
            </div>
          </Card>

          <Card class="h-full border-slate-200">
            <div class="text-sm text-slate-500">已完成归因 ROI</div>
            <div
              class="mt-2 text-2xl font-semibold tabular-nums text-slate-950"
            >
              {{ formatOverviewRoi(projectOverview) }}
            </div>
            <div class="mt-2 text-xs text-slate-500">
              已完成归因
              {{ projectOverview.summary.realizedProjectCount }} 个项目
            </div>
          </Card>
        </section>

        <Card class="border-slate-200" :body-style="{ padding: 0 }">
          <template #title>
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span>项目经营明细</span>
              <span class="text-xs font-normal text-slate-500">
                最近更新 {{ projectOverview.metricCutoff }}；各项目水位见明细
              </span>
            </div>
          </template>

          <div class="hidden min-w-0 lg:block">
            <Table
              :columns="overviewColumns"
              :data-source="projectOverview.projects"
              :pagination="false"
              table-layout="fixed"
              row-key="id"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'project'">
                  <div class="min-w-0 py-1">
                    <div class="truncate font-medium text-slate-900">
                      {{ record.name }}
                    </div>
                    <div class="mt-1 flex flex-wrap items-center gap-1">
                      <Tag :color="projectStatusMeta[record.status].color">
                        {{ projectStatusMeta[record.status].label }}
                      </Tag>
                      <Tag v-for="platform in record.platforms" :key="platform">
                        {{ platformLabels[platform as PlatformCode] }}
                      </Tag>
                    </div>
                    <div class="mt-1 truncate text-xs text-slate-500">
                      {{ record.ownerName }} · {{ record.projectCode }}
                    </div>
                  </div>
                </template>
                <template v-else-if="column.key === 'spend'">
                  <div class="font-medium tabular-nums text-slate-900">
                    {{ formatMoney(record.actualSpend, record.currency) }}
                  </div>
                </template>
                <template v-else-if="column.key === 'settlement'">
                  <Tag
                    :color="settlementStatusMeta[record.settlementStatus].color"
                  >
                    {{ settlementStatusMeta[record.settlementStatus].label }}
                  </Tag>
                  <div
                    class="mt-1 truncate text-xs tabular-nums text-slate-500"
                  >
                    已结
                    {{ formatMoney(record.settledAmount, record.currency) }}
                  </div>
                  <div
                    v-if="record.settlementPeriod"
                    class="mt-1 text-xs text-slate-400"
                  >
                    账期 {{ record.settlementPeriod }}
                  </div>
                </template>
                <template v-else-if="column.key === 'roi'">
                  <span class="font-medium tabular-nums text-slate-900">
                    {{ formatRoi(record.realizedRoi) }}
                  </span>
                </template>
                <template v-else-if="column.key === 'attribution'">
                  <Tag :color="record.attributionCompleted ? 'green' : 'blue'">
                    {{ record.attributionCompleted ? '已完成' : '归因中' }}
                  </Tag>
                </template>
              </template>
            </Table>
          </div>

          <div class="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2 lg:hidden">
            <article
              v-for="project in projectOverview.projects"
              :key="project.id"
              class="rounded-lg border border-slate-200 bg-white p-4"
            >
              <div class="flex min-w-0 items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="font-semibold text-slate-900">
                    {{ project.name }}
                  </div>
                  <div class="mt-1 text-xs text-slate-500">
                    {{ project.ownerName }} · {{ project.projectCode }}
                  </div>
                </div>
                <Tag
                  :color="projectStatusMeta[project.status].color"
                  class="shrink-0"
                >
                  {{ projectStatusMeta[project.status].label }}
                </Tag>
              </div>
              <dl
                class="mt-4 grid grid-cols-[84px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm"
              >
                <dt class="text-slate-500">累计消耗</dt>
                <dd class="m-0 font-medium tabular-nums text-slate-900">
                  {{ formatMoney(project.actualSpend, project.currency) }}
                </dd>
                <dt class="text-slate-500">结算状态</dt>
                <dd class="m-0">
                  <Tag
                    :color="
                      settlementStatusMeta[project.settlementStatus].color
                    "
                  >
                    {{ settlementStatusMeta[project.settlementStatus].label }}
                  </Tag>
                </dd>
                <dt class="text-slate-500">已结金额</dt>
                <dd class="m-0 tabular-nums text-slate-800">
                  {{ formatMoney(project.settledAmount, project.currency) }}
                </dd>
                <dt class="text-slate-500">已完成 ROI</dt>
                <dd class="m-0 font-medium tabular-nums text-slate-900">
                  {{ formatRoi(project.realizedRoi) }}
                </dd>
                <dt class="text-slate-500">归因状态</dt>
                <dd class="m-0 text-slate-800">
                  {{ project.attributionCompleted ? '已完成' : '归因中' }}
                </dd>
                <dt class="text-slate-500">数据截止</dt>
                <dd class="m-0 text-slate-800">{{ project.metricCutoff }}</dd>
              </dl>
            </article>
          </div>

          <div
            v-if="projectOverview.projects.length === 0"
            class="px-6 py-12 text-center text-slate-500"
          >
            当前客户尚未创建项目。
          </div>
        </Card>
      </template>

      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <Button class="" @click="overviewOpen = false">关闭</Button>
          <Button
            class=""
            type="primary"
            :disabled="!overviewCustomer"
            @click="goToCustomerProjects"
          >
            进入项目管理
          </Button>
        </div>
      </template>
    </Drawer>

    <Drawer
      :closable="!saving"
      :keyboard="!saving"
      :mask-closable="!saving"
      :open="drawerOpen"
      :title="editingCustomer ? '编辑客户' : '新建客户'"
      width="min(640px, 100vw)"
      @close="requestCloseDrawer"
    >
      <Alert
        class="mb-5"
        message="客户与项目是独立主数据。保存客户后，可在项目管理中选择该客户作为所属客户。"
        show-icon
        type="info"
      />
      <Alert
        v-if="saveError"
        class="mb-5"
        :message="saveError"
        show-icon
        type="error"
      />

      <Form
        ref="formRef"
        layout="vertical"
        :model="formState"
        :rules="formRules"
      >
        <FormItem label="客户名称" name="name" required>
          <Input
            v-model:value="formState.name"
            :maxlength="50"
            placeholder="请输入客户名称"
            show-count
          />
        </FormItem>

        <Row :gutter="16">
          <Col :xs="24" :md="12">
            <FormItem label="合作模式" name="cooperationMode" required>
              <Select
                v-model:value="formState.cooperationMode"
                :options="cooperationModeOptions"
                placeholder="请选择合作模式"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="状态" name="status" required>
              <Select
                v-model:value="formState.status"
                :options="statusOptions"
                placeholder="请选择客户状态"
              />
            </FormItem>
          </Col>
        </Row>

        <FormItem label="政策" name="policy">
          <Input
            v-model:value="formState.policy"
            placeholder="请输入合作政策"
          />
        </FormItem>

        <Row :gutter="16">
          <Col :xs="24" :md="12">
            <FormItem label="开始日期" name="startDate">
              <DatePicker
                v-model:value="formState.startDate"
                class="w-full"
                placeholder="选择开始日期"
                value-format="YYYY-MM-DD"
                @change="revalidateEndDate"
              />
            </FormItem>
          </Col>
          <Col :xs="24" :md="12">
            <FormItem label="结束日期" name="endDate">
              <DatePicker
                v-model:value="formState.endDate"
                class="w-full"
                placeholder="选择结束日期"
                value-format="YYYY-MM-DD"
              />
            </FormItem>
          </Col>
        </Row>

        <FormItem label="备注" name="remark">
          <Input.TextArea
            v-model:value="formState.remark"
            :maxlength="200"
            :rows="4"
            placeholder="请输入备注信息"
            show-count
          />
        </FormItem>
      </Form>

      <template #footer>
        <div class="flex justify-end gap-2">
          <Button class="" :disabled="saving" @click="requestCloseDrawer">
            取消
          </Button>
          <Button
            class=""
            :loading="saving"
            type="primary"
            @click="saveCustomer"
          >
            保存客户
          </Button>
        </div>
      </template>
    </Drawer>
  </Page>
</template>
