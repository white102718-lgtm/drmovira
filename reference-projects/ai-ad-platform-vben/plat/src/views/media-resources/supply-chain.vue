<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import type {
  SupplyChainCustomer,
  SupplyChainCustomerInput,
  SupplyChainStatus,
} from '#/store/media-supply-chain';

import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  DatePicker,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Pagination,
  Select,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { isFusionDemoMode } from '#/api';
import {
  createOptionalStringRouteQueryField,
  createPositiveIntegerRouteQueryField,
  createRouteQueryField,
  createStringRouteQueryField,
  readRouteQueryText,
  useRouteListQuery,
} from '#/composables/use-route-list-query';
import { canDemoAction, getCurrentDemoActor } from '#/mock/demo-access';
import { useMediaSupplyChainStore } from '#/store/media-supply-chain';

defineOptions({ name: 'MediaResourceSupplyChain' });

type DateRange = [Dayjs, Dayjs] | undefined;

const supplyChainStore = useMediaSupplyChainStore();
const keyword = ref('');
const cooperationMode = ref<string>();
const status = ref<string>();
const dateRange = ref<DateRange>();
const page = ref(1);
const pageSize = ref(10);
const modalOpen = ref(false);
const editingCustomer = ref<SupplyChainCustomer>();

const demoActor = computed(() =>
  isFusionDemoMode() ? getCurrentDemoActor() : undefined,
);
const canManageSupplyChain = computed(
  () =>
    !isFusionDemoMode() || canDemoAction(demoActor.value, 'resource.manage'),
);

const form = reactive<SupplyChainCustomerInput>(emptyForm());

const cooperationModeOptions = [
  { label: '预付', value: 'prepaid' },
  { label: '预付实销', value: 'prepaid_actual' },
];

const statusOptions = [
  { label: '未开始', value: 'not_started' },
  { label: '进行中', value: 'active' },
  { label: '已暂停', value: 'suspended' },
];

const statusMeta: Record<SupplyChainStatus, { color: string; label: string }> =
  {
    active: { color: 'green', label: '进行中' },
    not_started: { color: 'default', label: '未开始' },
    suspended: { color: 'orange', label: '已暂停' },
  };

const route = useRoute();
const router = useRouter();
const { isApplyingRoute } = useRouteListQuery({
  fields: {
    cooperationMode: createOptionalStringRouteQueryField(cooperationMode, {
      allowedValues: cooperationModeOptions.map((item) => item.value),
    }),
    dateRange: createRouteQueryField(dateRange, {
      defaultValue: undefined,
      parse: (value) => {
        const [start, end, ...rest] = readRouteQueryText(value).split(',');
        if (rest.length > 0 || !start || !end) return undefined;
        if (
          !/^\d{4}-\d{2}-\d{2}$/.test(start) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(end)
        ) {
          return undefined;
        }
        const startDate = dayjs(start);
        const endDate = dayjs(end);
        return startDate.isValid() &&
          endDate.isValid() &&
          startDate.format('YYYY-MM-DD') === start &&
          endDate.format('YYYY-MM-DD') === end &&
          !startDate.isAfter(endDate)
          ? [startDate, endDate]
          : undefined;
      },
      serialize: (value) => {
        if (!value) return undefined;
        const [start, end] = value;
        if (!start || !end) return undefined;
        return `${start.format('YYYY-MM-DD')},${end.format('YYYY-MM-DD')}`;
      },
    }),
    page: createPositiveIntegerRouteQueryField(page, { defaultValue: 1 }),
    pageSize: createPositiveIntegerRouteQueryField(pageSize, {
      allowedValues: [10, 20, 50, 100],
      defaultValue: 10,
    }),
    q: createStringRouteQueryField(keyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
    status: createOptionalStringRouteQueryField(status, {
      allowedValues: statusOptions.map((item) => item.value),
    }),
  },
  route,
  router,
});

const columns: TableColumnsType<SupplyChainCustomer> = [
  { dataIndex: 'name', key: 'name', title: '客户群名', width: 220 },
  { key: 'cooperationMode', title: '合作模式', width: 120 },
  { dataIndex: 'policy', key: 'policy', title: '政策', width: 150 },
  { key: 'status', title: '状态', width: 110 },
  { dataIndex: 'startDate', key: 'startDate', title: '开始时间', width: 136 },
  { dataIndex: 'endDate', key: 'endDate', title: '结束时间', width: 136 },
  { key: 'walletAddress', title: '钱包地址', width: 380 },
  { key: 'sheetUrl', title: '在线表', width: 120 },
  { dataIndex: 'note', key: 'note', title: '备注', width: 190 },
  { dataIndex: 'createdAt', key: 'createdAt', title: '创建时间', width: 180 },
  {
    dataIndex: 'updatedAt',
    key: 'updatedAt',
    title: '最近更新时间',
    width: 180,
  },
  { key: 'actions', title: '操作', width: 110, fixed: 'right' },
];

const filteredCustomers = computed(() => {
  const query = keyword.value.trim().toLowerCase();
  const [start, end] = dateRange.value ?? [];
  const startDate = start?.format('YYYY-MM-DD');
  const endDate = end?.format('YYYY-MM-DD');

  return supplyChainStore.customers.filter((customer) => {
    const matchesKeyword =
      !query ||
      [customer.name, customer.policy, customer.note]
        .join(' ')
        .toLowerCase()
        .includes(query);
    const matchesMode =
      !cooperationMode.value ||
      customer.cooperationMode === cooperationMode.value;
    const matchesStatus = !status.value || customer.status === status.value;
    const matchesDate =
      (!startDate || customer.startDate >= startDate) &&
      (!endDate || !customer.startDate || customer.startDate <= endDate);

    return matchesKeyword && matchesMode && matchesStatus && matchesDate;
  });
});

const pagedCustomers = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredCustomers.value.slice(start, start + pageSize.value);
});

watch([keyword, cooperationMode, status, dateRange, pageSize], () => {
  if (!isApplyingRoute.value) page.value = 1;
});

watch([() => filteredCustomers.value.length, pageSize], ([total]) => {
  const lastPage = Math.max(1, Math.ceil(total / pageSize.value));
  if (page.value > lastPage) page.value = lastPage;
});

function emptyForm(): SupplyChainCustomerInput {
  return {
    cooperationMode: 'prepaid',
    createWallet: false,
    endDate: '',
    name: '',
    note: '',
    policy: '',
    sheetUrl: '',
    startDate: '',
    status: 'not_started',
    walletAddress: '',
  };
}

function resetForm() {
  Object.assign(form, emptyForm());
}

function search() {
  page.value = 1;
}

function resetFilters() {
  keyword.value = '';
  cooperationMode.value = undefined;
  status.value = undefined;
  dateRange.value = undefined;
  page.value = 1;
}

function openCreate() {
  if (!canManageSupplyChain.value) {
    message.warning('当前演示角色没有供应链管理权限');
    return;
  }
  editingCustomer.value = undefined;
  resetForm();
  modalOpen.value = true;
}

function openEdit(customer: SupplyChainCustomer) {
  if (!canManageSupplyChain.value) {
    message.warning('当前演示角色没有供应链管理权限');
    return;
  }
  editingCustomer.value = customer;
  Object.assign(form, {
    cooperationMode: customer.cooperationMode,
    createWallet: Boolean(customer.createWallet),
    endDate: customer.endDate,
    name: customer.name,
    note: customer.note,
    policy: customer.policy,
    sheetUrl: customer.sheetUrl,
    startDate: customer.startDate,
    status: customer.status,
    walletAddress: customer.walletAddress || '',
  });
  modalOpen.value = true;
}

function saveCustomer() {
  try {
    if (editingCustomer.value) {
      supplyChainStore.update(editingCustomer.value.id, form);
      message.success('客户信息已更新');
    } else {
      supplyChainStore.create(form);
      message.success('客户已添加');
    }
    modalOpen.value = false;
  } catch (error) {
    message.error(error instanceof Error ? error.message : '保存客户失败');
  }
}

function removeCustomer(customer: SupplyChainCustomer) {
  if (!canManageSupplyChain.value) {
    message.warning('当前演示角色没有供应链管理权限');
    return;
  }
  Modal.confirm({
    centered: true,
    content: `删除“${customer.name}”后将无法恢复，确定继续吗？`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除客户',
    onOk: () => {
      supplyChainStore.remove(customer.id);
      message.success('客户已删除');
    },
  });
}

async function copySheetUrl(customer: SupplyChainCustomer) {
  if (!customer.sheetUrl) {
    message.info('该客户暂未填写在线表链接');
    return;
  }
  try {
    await navigator.clipboard.writeText(customer.sheetUrl);
    message.success('在线表链接已复制');
  } catch {
    message.info('在线表链接：' + customer.sheetUrl);
  }
}

async function copyWalletAddress(customer: SupplyChainCustomer) {
  if (!customer.walletAddress) {
    message.info('该客户暂未创建钱包');
    return;
  }
  try {
    await navigator.clipboard.writeText(customer.walletAddress);
    message.success('钱包地址已复制');
  } catch {
    message.error('复制失败，请检查浏览器的剪贴板权限');
  }
}

function updatePagination(nextPage: number, nextPageSize: number) {
  page.value = nextPageSize === pageSize.value ? nextPage : 1;
  pageSize.value = nextPageSize;
}

function toCustomer(value: unknown): SupplyChainCustomer {
  return value as SupplyChainCustomer;
}

function customerStatus(value: unknown) {
  return statusMeta[toCustomer(value).status];
}
</script>

<template>
  <Page auto-content-height content-class="p-4 md:p-6">
    <div class="mx-auto flex min-w-0 max-w-[1800px] flex-col gap-4">
      <section
        class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"
      >
        <div>
          <div class="mb-2 flex items-center gap-2 text-sm text-slate-500">
            <IconifyIcon icon="lucide:warehouse" />
            <span>媒介资源中心</span><span>/</span><span>供应链管理</span>
          </div>
          <h1 class="m-0 text-2xl font-semibold text-slate-950 dark:text-white">
            供应链管理
          </h1>
          <p class="mb-0 mt-2 text-sm text-slate-600 dark:text-slate-400">
            集中维护合作客户群、政策、在线表与合作状态。
          </p>
        </div>
        <Button
          v-if="canManageSupplyChain"
          class="!inline-flex items-center"
          type="primary"
          @click="openCreate"
        >
          <IconifyIcon icon="lucide:plus" />添加客户
        </Button>
      </section>

      <section
        class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <div
          class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-[1.2fr_1fr_1fr_1.3fr_auto]"
        >
          <Input
            v-model:value="keyword"
            allow-clear
            placeholder="请输入客户群名"
            @press-enter="search"
          />
          <Select
            v-model:value="cooperationMode"
            allow-clear
            :options="cooperationModeOptions"
            placeholder="全部合作模式"
          />
          <Select
            v-model:value="status"
            allow-clear
            :options="statusOptions"
            placeholder="全部状态"
          />
          <DatePicker.RangePicker
            v-model:value="dateRange"
            class="w-full"
            :placeholder="['开始日期', '结束日期']"
          />
          <div class="flex gap-2">
            <Button class="" type="primary" @click="search"> 搜索 </Button>
            <Button class="" @click="resetFilters">重置</Button>
          </div>
        </div>
      </section>

      <section
        class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <Table
          class="supply-chain-table"
          :columns="columns"
          :data-source="pagedCustomers"
          :locale="{ emptyText: '暂无客户，请先添加客户' }"
          :pagination="false"
          :scroll="{ x: 2032 }"
          table-layout="fixed"
          row-key="id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <Tooltip :title="record.name">
                <button
                  class="ux-table-link block w-full cursor-pointer truncate border-0 bg-transparent p-0 text-left font-medium"
                  type="button"
                  @click="openEdit(toCustomer(record))"
                >
                  {{ record.name }}
                </button>
              </Tooltip>
            </template>
            <template v-else-if="column.key === 'cooperationMode'">
              {{
                record.cooperationMode === 'prepaid_actual'
                  ? '预付实销'
                  : '预付'
              }}
            </template>
            <template v-else-if="column.key === 'status'">
              <Tag :color="customerStatus(record).color" class="!m-0">
                {{ customerStatus(record).label }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'sheetUrl'">
              <Button
                class="!flex !w-full !items-center !overflow-hidden !px-0"
                type="link"
                @click="copySheetUrl(toCustomer(record))"
              >
                <span class="truncate">查看链接</span>
                <IconifyIcon icon="lucide:copy" class="ml-1 shrink-0" />
              </Button>
            </template>
            <template v-else-if="column.key === 'walletAddress'">
              <div class="flex min-w-[350px] items-center gap-2">
                <Button
                  v-if="record.walletAddress"
                  :aria-label="`复制 ${record.name} 的钱包地址`"
                  class="!shrink-0 !px-1"
                  type="text"
                  @click="copyWalletAddress(toCustomer(record))"
                >
                  <IconifyIcon icon="lucide:copy" />
                </Button>
                <span
                  v-if="record.walletAddress"
                  class="min-w-0 font-mono text-xs text-slate-700 dark:text-slate-300"
                >
                  {{ record.walletAddress }}
                </span>
                <span v-else class="text-slate-300">—</span>
              </div>
            </template>
            <template v-else-if="column.key === 'note'">
              <Tooltip :title="record.note || '—'">
                <span class="block w-full truncate">{{
                  record.note || '—'
                }}</span>
              </Tooltip>
            </template>
            <template v-else-if="column.key === 'actions'">
              <div v-if="canManageSupplyChain" class="flex items-center gap-1">
                <Button type="link" @click="openEdit(toCustomer(record))">
                  编辑
                </Button>
                <Button
                  danger
                  type="link"
                  @click="removeCustomer(toCustomer(record))"
                >
                  删除
                </Button>
              </div>
              <span v-else class="text-xs text-slate-400">仅查看</span>
            </template>
            <template v-else-if="column.key === 'endDate'">
              {{ record.endDate || '—' }}
            </template>
          </template>
        </Table>
        <div
          class="flex flex-col items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 sm:flex-row dark:border-slate-800"
        >
          <span class="text-sm text-slate-500"
            >共 {{ filteredCustomers.length }} 条</span
          >
          <Pagination
            :current="page"
            :page-size="pageSize"
            :total="filteredCustomers.length"
            show-less-items
            show-size-changer
            @change="updatePagination"
          />
        </div>
      </section>
    </div>

    <Modal
      v-model:open="modalOpen"
      :width="900"
      cancel-text="取消"
      destroy-on-close
      :ok-text="editingCustomer ? '保存' : '确定'"
      :title="editingCustomer ? '编辑客户' : '添加客户'"
      @ok="saveCustomer"
    >
      <Form class="pt-4" layout="vertical">
        <div class="grid grid-cols-1 gap-x-8 md:grid-cols-2">
          <FormItem label="客户群名" required>
            <Input
              v-model:value="form.name"
              :maxlength="50"
              placeholder="请输入客户群名"
              show-count
            />
          </FormItem>
          <FormItem label="合作模式" required>
            <Select
              v-model:value="form.cooperationMode"
              :options="cooperationModeOptions"
              placeholder="请选择"
            />
          </FormItem>
          <FormItem label="政策">
            <Input
              v-model:value="form.policy"
              :maxlength="80"
              placeholder="请输入政策"
            />
          </FormItem>
          <FormItem label="状态" required>
            <Select
              v-model:value="form.status"
              :options="statusOptions"
              placeholder="请选择"
            />
          </FormItem>
          <FormItem label="是否创建钱包">
            <div class="flex items-center gap-3">
              <Switch
                v-model:checked="form.createWallet"
                aria-label="是否创建钱包"
                checked-children="是"
                un-checked-children="否"
              />
              <span class="text-xs text-slate-500">
                {{
                  form.createWallet ? '保存后自动生成钱包地址' : '不创建钱包'
                }}
              </span>
            </div>
          </FormItem>
          <FormItem label="开始日期">
            <Input v-model:value="form.startDate" type="date" />
          </FormItem>
          <FormItem label="结束日期">
            <Input v-model:value="form.endDate" type="date" />
          </FormItem>
          <FormItem class="md:col-span-2" label="在线表格">
            <Input
              v-model:value="form.sheetUrl"
              placeholder="请输入在线表格链接"
            />
          </FormItem>
          <FormItem
            v-if="form.walletAddress"
            class="md:col-span-2"
            label="钱包地址"
          >
            <Input :value="form.walletAddress" readonly>
              <template #suffix>
                <Button
                  :aria-label="`复制 ${form.name || '客户'} 的钱包地址`"
                  type="link"
                  @click="copyWalletAddress(toCustomer(form))"
                >
                  <IconifyIcon icon="lucide:copy" class="mr-1" />复制
                </Button>
              </template>
            </Input>
          </FormItem>
          <FormItem class="md:col-span-2" label="备注">
            <Input.TextArea
              v-model:value="form.note"
              :maxlength="200"
              :rows="3"
              placeholder="请输入备注信息"
              show-count
            />
          </FormItem>
        </div>
      </Form>
    </Modal>
  </Page>
</template>

<style scoped>
@media (prefers-color-scheme: dark) {
}
</style>
