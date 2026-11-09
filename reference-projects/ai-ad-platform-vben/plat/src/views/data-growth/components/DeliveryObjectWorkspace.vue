<script lang="ts" setup>
import type { TableProps } from 'ant-design-vue';

import type {
  AdDashboardCategory,
  AdDashboardField,
  AdDashboardListQuery,
  AdDashboardRow,
  AdDashboardSummaryRow,
} from '#/domain/ad-dashboard';
import type {
  DashboardAccount,
  DashboardObjectQuery,
} from '#/domain/my-dashboard';

import { computed, nextTick, onMounted, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Input,
  message,
  Pagination,
  Popover,
  Select,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { formatAdDashboardValue } from '#/domain/ad-dashboard';
import {
  formatAdDashboardStatus,
  getAdDashboardStatusOptions,
} from '#/domain/ad-dashboard/status';
import { myDashboardService } from '#/domain/my-dashboard';
import { downloadCsv } from '#/utils/csv';

defineOptions({ name: 'DeliveryObjectWorkspace' });

const props = defineProps<{
  accounts: DashboardAccount[];
  accountsError?: string;
  accountsLoading?: boolean;
  endDate: string;
  startDate: string;
}>();

const OBJECT_LEVELS = [
  {
    category: 'campaign',
    description: '当前可见广告系列',
    icon: 'lucide:megaphone',
    label: '广告系列',
    tabLabel: '广告系列',
  },
  {
    category: 'adSet',
    description: '当前可见广告组',
    icon: 'lucide:blocks',
    label: '广告组',
    tabLabel: '广告组',
  },
  {
    category: 'ad',
    description: '当前可见广告',
    icon: 'lucide:badge-play',
    label: '广告',
    tabLabel: '广告',
  },
] as const satisfies ReadonlyArray<{
  category: AdDashboardCategory;
  description: string;
  icon: string;
  label: string;
  tabLabel: string;
}>;

const VISIBLE_OBJECT_LEVELS = OBJECT_LEVELS;

type WorkspaceCategory = (typeof OBJECT_LEVELS)[number]['category'];
type WorkspaceStatus = NonNullable<AdDashboardListQuery['status']>;

const COLUMN_STORAGE_KEY = 'fusion:my-dashboard-object-columns:v1';
const DEFAULT_PAGE_SIZE = 10;

const activeCategory = ref<WorkspaceCategory>('campaign');
const dataCutoff = ref('');
const errorMessage = ref('');
const exporting = ref(false);
const keyword = ref('');
const selectedAccountId = defineModel<string>('accountId');
const loading = ref(false);
const page = ref(1);
const pageSize = ref(DEFAULT_PAGE_SIZE);
const rows = ref<AdDashboardRow[]>([]);
const selectedRowKeys = ref<string[]>([]);
const sortField = ref<string>();
const sortOrder = ref<'asc' | 'desc'>('desc');
const status = ref<WorkspaceStatus>('all');
const statusOptions = computed(() => [
  { label: '全部状态', value: 'all' },
  ...getAdDashboardStatusOptions(activeCategory.value),
]);
const summaryRows = ref<AdDashboardSummaryRow[]>([]);
const total = ref(0);

const visibleColumnKeysByCategory = ref<
  Partial<Record<WorkspaceCategory, string[]>>
>({});

let currentRequest = 0;

const activeLevel = computed(
  () =>
    OBJECT_LEVELS.find((level) => level.category === activeCategory.value) ??
    OBJECT_LEVELS[0],
);
const schema = computed(() =>
  myDashboardService.getSchema(activeCategory.value),
);

function normalizeVisibleColumnKeys(
  category: WorkspaceCategory,
  keys?: readonly string[],
) {
  const fields = myDashboardService.getSchema(category).fields;
  const defaults = fields
    .filter((field, index) => field.key === 'name' || index < 8)
    .map((field) => field.key);
  const selectedKeys = new Set(keys?.length ? keys : defaults);

  return fields
    .filter((field) => field.key === 'name' || selectedKeys.has(field.key))
    .map((field) => field.key);
}

const visibleColumnKeys = computed<string[]>({
  get: () =>
    normalizeVisibleColumnKeys(
      activeCategory.value,
      visibleColumnKeysByCategory.value[activeCategory.value],
    ),
  set: (keys) => {
    const category = activeCategory.value;
    const normalizedKeys = normalizeVisibleColumnKeys(category, keys);
    visibleColumnKeysByCategory.value = {
      ...visibleColumnKeysByCategory.value,
      [category]: normalizedKeys,
    };
    saveColumnSettings();
  },
});

const visibleFields = computed(() => {
  const visibleKeys = new Set(visibleColumnKeys.value);
  return schema.value.fields.filter((field) => visibleKeys.has(field.key));
});

const visibleColumnOptions = computed(() =>
  schema.value.fields.map((field) => ({
    ...field,
    disabled: field.key === 'name',
  })),
);

const tableColumns = computed(() => [
  {
    align: 'left' as const,
    dataIndex: '__deliveryToggle',
    fixed: 'left' as const,
    key: '__deliveryToggle',
    title: '开/关',
    width: 64,
  },
  {
    align: 'left' as const,
    dataIndex: '__deliveryState',
    fixed: 'left' as const,
    key: '__deliveryState',
    title: '数据状态',
    width: 118,
  },
  ...visibleFields.value.map((field) => ({
    align: 'left' as const,
    dataIndex: field.key,
    ellipsis: true,
    fixed: field.fixed,
    key: field.key,
    sorter: field.sortable,
    title: field.label,
    width: field.width,
  })),
]);

const tableWidth = computed(
  () =>
    48 +
    64 +
    118 +
    visibleFields.value.reduce(
      (totalWidth, field) => totalWidth + field.width,
      0,
    ),
);

const rowSelection = computed(() => ({
  columnWidth: 48,
  fixed: true,
  onChange: (keys: Array<number | string>) => {
    selectedRowKeys.value = keys.map(String);
  },
  selectedRowKeys: selectedRowKeys.value,
}));

function saveColumnSettings() {
  try {
    window.localStorage.setItem(
      COLUMN_STORAGE_KEY,
      JSON.stringify(visibleColumnKeysByCategory.value),
    );
  } catch {
    // 浏览器禁用本地存储时仍保留当前会话中的列配置。
  }
}

function restoreColumnSettings() {
  try {
    const rawValue = window.localStorage.getItem(COLUMN_STORAGE_KEY);
    if (!rawValue) return;
    const storedValue: unknown = JSON.parse(rawValue);
    if (!storedValue || typeof storedValue !== 'object') return;

    const restored: Partial<Record<WorkspaceCategory, string[]>> = {};
    for (const level of OBJECT_LEVELS) {
      const value = (storedValue as Record<string, unknown>)[level.category];
      if (!Array.isArray(value)) continue;
      restored[level.category] = normalizeVisibleColumnKeys(
        level.category,
        value.filter((key): key is string => typeof key === 'string'),
      );
    }
    visibleColumnKeysByCategory.value = restored;
  } catch {
    window.localStorage.removeItem(COLUMN_STORAGE_KEY);
  }
}

function resetVisibleColumns() {
  const category = activeCategory.value;
  const fields = myDashboardService.getSchema(category).fields;
  visibleColumnKeysByCategory.value = {
    ...visibleColumnKeysByCategory.value,
    [category]: fields
      .filter((field, index) => field.key === 'name' || index < 8)
      .map((field) => field.key),
  };
  saveColumnSettings();
}

function buildListQuery(
  pagination: Pick<AdDashboardListQuery, 'page' | 'pageSize'> = {},
): DashboardObjectQuery {
  return {
    category: activeCategory.value,
    accountId: selectedAccountId.value || undefined,
    endDate: props.endDate,
    name: keyword.value.trim() || undefined,
    page: pagination.page ?? page.value,
    pageSize: pagination.pageSize ?? pageSize.value,
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    startDate: props.startDate,
    status: status.value,
  };
}

async function loadRows() {
  const requestId = ++currentRequest;
  if (!selectedAccountId.value) {
    loading.value = false;
    errorMessage.value = '';
    rows.value = [];
    summaryRows.value = [];
    total.value = 0;
    dataCutoff.value = '';
    return true;
  }
  loading.value = true;
  errorMessage.value = '';

  try {
    const result = await myDashboardService.list(buildListQuery());
    if (requestId !== currentRequest) return false;
    dataCutoff.value = result.dataCutoff;
    rows.value = result.items;
    summaryRows.value = result.summaryRows;
    total.value = result.total;
    return true;
  } catch {
    if (requestId !== currentRequest) return false;
    rows.value = [];
    summaryRows.value = [];
    total.value = 0;
    dataCutoff.value = '';
    errorMessage.value = '暂时无法加载对象数据，请重试。';
    return false;
  } finally {
    if (requestId === currentRequest) loading.value = false;
  }
}

function clearSelection() {
  selectedRowKeys.value = [];
}

function handleAccountSelect(accountId: string) {
  selectedAccountId.value = accountId;
}

async function handleLevelChange(category: WorkspaceCategory) {
  if (category === activeCategory.value) return;
  activeCategory.value = category;
  keyword.value = '';
  status.value = 'all';
  page.value = 1;
  sortField.value = undefined;
  clearSelection();
  await loadRows();
}

async function handleLevelKeydown(
  event: KeyboardEvent,
  category: WorkspaceCategory,
) {
  const currentIndex = VISIBLE_OBJECT_LEVELS.findIndex(
    (level) => level.category === category,
  );
  if (currentIndex === -1) return;

  let nextIndex = currentIndex;
  switch (event.key) {
    case 'ArrowLeft': {
      nextIndex =
        (currentIndex - 1 + VISIBLE_OBJECT_LEVELS.length) %
        VISIBLE_OBJECT_LEVELS.length;
      break;
    }
    case 'ArrowRight': {
      nextIndex = (currentIndex + 1) % VISIBLE_OBJECT_LEVELS.length;
      break;
    }
    case 'End': {
      nextIndex = VISIBLE_OBJECT_LEVELS.length - 1;
      break;
    }
    case 'Home': {
      nextIndex = 0;
      break;
    }
    default: {
      return;
    }
  }

  const nextLevel = VISIBLE_OBJECT_LEVELS[nextIndex];
  if (!nextLevel) return;

  event.preventDefault();
  await handleLevelChange(nextLevel.category);
  await nextTick();
  document
    .querySelector<HTMLButtonElement>(
      `#delivery-object-tab-${nextLevel.category}`,
    )
    ?.focus();
}

async function applyFilters() {
  page.value = 1;
  clearSelection();
  await loadRows();
}

async function resetFilters() {
  keyword.value = '';
  status.value = 'all';
  sortField.value = undefined;
  sortOrder.value = 'desc';
  page.value = 1;
  clearSelection();
  await loadRows();
}

async function handlePageChange(nextPage: number, nextPageSize: number) {
  const pageSizeChanged = nextPageSize !== pageSize.value;
  pageSize.value = nextPageSize;
  page.value = pageSizeChanged ? 1 : nextPage;
  clearSelection();
  await loadRows();
}

const handleTableChange: NonNullable<TableProps['onChange']> = async (
  _pagination,
  _filters,
  sorter,
) => {
  const activeSorter = Array.isArray(sorter) ? sorter[0] : sorter;
  const rawField = activeSorter?.field;
  const resolvedField = Array.isArray(rawField) ? rawField.at(-1) : rawField;
  sortField.value = activeSorter?.order
    ? String(resolvedField ?? '')
    : undefined;
  sortOrder.value = activeSorter?.order === 'ascend' ? 'asc' : 'desc';
  page.value = 1;
  clearSelection();
  await loadRows();
};

function displayStatus(record: AdDashboardRow) {
  return formatAdDashboardStatus(
    activeCategory.value,
    deliveryStateValue(record),
  );
}

function deliveryStateValue(record: AdDashboardRow) {
  const values = [record.effectiveStatus, record.statusText];
  return values.find((value) => typeof value === 'string' && value.trim()) as
    | string
    | undefined;
}

function isDeliveryEnabled(record: AdDashboardRow) {
  const value = deliveryStateValue(record)?.toUpperCase() ?? '';
  return ['ACTIVE', 'IN_PROCESS', '处理中', '投放中', '正常'].includes(value);
}

function deliveryToggleTitle(record: AdDashboardRow) {
  const state = deliveryStateValue(record);
  const stateText = state ? `当前状态：${state}` : '当前投放状态未提供';
  return `${stateText}。此处仅支持查看，暂不支持直接启停。`;
}

function deliveryToggleAriaLabel(record: AdDashboardRow) {
  const name = String(record.name ?? record.id ?? '当前对象');
  if (!deliveryStateValue(record)) return `${name}：投放状态未提供`;
  const state = isDeliveryEnabled(record) ? '已开启' : '已关闭';
  return `${name}：${state}，只读开关`;
}

function statusColor(record: AdDashboardRow) {
  const value = displayStatus(record) ?? '';
  if (['2', '3', '7', '100', '101'].includes(String(record.accountStatus))) {
    return 'error';
  }
  if (
    value.includes('异常') ||
    ['已拒绝', '待结算信息', '有问题'].includes(value)
  )
    return 'error';
  if (value.includes('暂停')) return 'default';
  if (value.includes('投放中') || value.includes('正常')) return 'success';
  return 'default';
}

function statusText(record: AdDashboardRow) {
  return displayStatus(record) ?? '状态未提供';
}

function asDashboardRow(record: Record<string, unknown>) {
  return record as AdDashboardRow;
}

function asDashboardField(column: unknown) {
  return column as AdDashboardField;
}

function renderValue(
  value: AdDashboardRow[string],
  record: AdDashboardRow,
  field: AdDashboardField,
) {
  return formatAdDashboardValue(value, field, record.currency);
}

function summaryValue(summary: AdDashboardSummaryRow, field: AdDashboardField) {
  if (field.key === 'name') return `${summary.currency} 本页汇总`;
  if (!field.summarizable) return field.emptyText;
  return formatAdDashboardValue(
    summary.values[field.key] ?? 0,
    field,
    summary.currency,
  );
}

function rowClassName(record: AdDashboardRow) {
  return selectedRowKeys.value.includes(String(record.key))
    ? 'workspace-selected-row'
    : '';
}

async function exportData() {
  if (exporting.value || !selectedAccountId.value) return;
  exporting.value = true;

  try {
    const fields = [...visibleFields.value];
    const exportQuery = buildListQuery();
    const exportSchema = schema.value;
    const exportedRows: AdDashboardRow[] = [];
    const exportPageSize = 100;
    let exportPage = 1;
    let availableTotal = Number.POSITIVE_INFINITY;

    while (exportedRows.length < availableTotal) {
      const result = await myDashboardService.list({
        ...exportQuery,
        page: exportPage,
        pageSize: exportPageSize,
      });
      availableTotal = result.total;
      exportedRows.push(...result.items);
      if (result.items.length === 0) break;
      exportPage += 1;
    }

    if (exportedRows.length === 0) {
      message.info('当前筛选条件下没有可导出的数据');
      return;
    }

    downloadCsv(
      `投放对象-${exportSchema.sheetName}-${exportQuery.startDate}-${exportQuery.endDate}`,
      [
        ['币种', ...fields.map((field) => field.label)],
        ...exportedRows.map((row) => [
          row.currency,
          ...fields.map((field) =>
            formatAdDashboardValue(row[field.key], field, row.currency),
          ),
        ]),
      ],
    );
    message.success(
      `已导出 ${exportedRows.length} 条${exportSchema.label}数据`,
    );
  } catch {
    message.error('导出失败，请稍后重试');
  } finally {
    exporting.value = false;
  }
}

onMounted(async () => {
  restoreColumnSettings();
  await loadRows();
});

watch(
  [() => props.startDate, () => props.endDate, selectedAccountId],
  async () => {
    page.value = 1;
    clearSelection();
    await loadRows();
  },
);
// 页头刷新同时触发对象查询；日期或共享账户切换时重置分页。
defineExpose({ refresh: loadRows });
</script>

<template>
  <section
    class="delivery-workspace"
    aria-labelledby="delivery-workspace-title"
  >
    <header class="workspace-heading">
      <div>
        <h2 id="delivery-workspace-title">投放对象管理</h2>
        <p>
          在同一张工作表中查看账户与广告层级的投放数据；筛选、列配置和导出只作用于当前对象维度。
        </p>
      </div>
      <div class="workspace-meta">
        <span>数据截止：{{ dataCutoff || '—' }}</span>
      </div>
    </header>

    <div class="workspace-frame">
      <nav class="account-switcher" aria-label="广告账户切换">
        <div class="account-switcher-label">
          <IconifyIcon icon="lucide:wallet-cards" aria-hidden="true" />
          <span>广告账户</span>
        </div>
        <div
          v-if="props.accounts.length > 0"
          class="account-list"
          aria-label="当前可见广告账户"
          role="list"
        >
          <span
            v-for="account in props.accounts"
            :key="account.id"
            role="listitem"
          >
            <button
              :aria-pressed="selectedAccountId === account.id"
              class="account-list-item"
              :class="{
                'account-list-item-active': selectedAccountId === account.id,
              }"
              type="button"
              @click="handleAccountSelect(account.id)"
            >
              {{ account.name }}
            </button>
          </span>
        </div>
        <span v-else class="account-list-empty">{{
          props.accountsLoading
            ? '正在加载账户'
            : props.accountsError
              ? '账户加载失败，请点击页头重试'
              : '暂无可见广告账户'
        }}</span>
      </nav>

      <div class="workspace-context">
        <div class="context-copy">
          <IconifyIcon icon="lucide:layers-3" aria-hidden="true" />
          <div>
            <strong>正在浏览{{ activeLevel.label }}</strong>
            <span>{{ activeLevel.description }}；切换后刷新表格。</span>
          </div>
        </div>
        <div class="context-counts" aria-live="polite">
          <Tag>{{ total }} 条对象</Tag>
          <Tag v-if="selectedRowKeys.length > 0" color="blue">
            已选 {{ selectedRowKeys.length }} 项
          </Tag>
        </div>
      </div>

      <div class="workspace-filters">
        <div aria-label="投放对象层级" class="object-type-tabs" role="tablist">
          <button
            v-for="level in VISIBLE_OBJECT_LEVELS"
            :key="level.category"
            :aria-label="`切换到${level.tabLabel}`"
            :aria-selected="level.category === activeCategory"
            aria-controls="delivery-object-table"
            :id="`delivery-object-tab-${level.category}`"
            :tabindex="level.category === activeCategory ? 0 : -1"
            :title="level.description"
            class="object-type-tab"
            :class="{
              'object-type-tab-active': level.category === activeCategory,
            }"
            role="tab"
            type="button"
            @click="handleLevelChange(level.category)"
            @keydown="handleLevelKeydown($event, level.category)"
          >
            <IconifyIcon :icon="level.icon" aria-hidden="true" />
            <span>{{ level.tabLabel }}</span>
          </button>
        </div>

        <div class="filter-controls">
          <Input
            v-model:value="keyword"
            allow-clear
            aria-label="搜索对象名称或 ID"
            class="object-search"
            placeholder="搜索对象名称或完整 ID"
            @press-enter="applyFilters"
          >
            <template #prefix>
              <IconifyIcon icon="lucide:search" aria-hidden="true" />
            </template>
          </Input>
          <Select
            v-model:value="status"
            aria-label="对象状态"
            class="status-select"
            :options="statusOptions"
          />
          <Button type="primary" @click="applyFilters">查询</Button>
          <Button aria-label="重置对象筛选" @click="resetFilters">
            <IconifyIcon icon="lucide:rotate-ccw" aria-hidden="true" />
            重置
          </Button>
        </div>
      </div>

      <div class="workspace-actions">
        <div class="action-group" aria-label="对象批量操作">
          <Tooltip title="需接入投放平台写入权限后开放">
            <span>
              <Button disabled type="primary">
                <IconifyIcon icon="lucide:plus" aria-hidden="true" />
                创建
              </Button>
            </span>
          </Tooltip>
          <Tooltip title="需接入投放平台写入权限后开放">
            <span>
              <Button disabled>
                <IconifyIcon icon="lucide:copy" aria-hidden="true" />
                复制
              </Button>
            </span>
          </Tooltip>
          <Tooltip title="需接入投放平台写入权限后开放">
            <span>
              <Button disabled>
                <IconifyIcon icon="lucide:pencil" aria-hidden="true" />
                编辑
              </Button>
            </span>
          </Tooltip>
          <Tooltip title="需接入投放平台写入权限后开放">
            <span>
              <Button danger disabled>
                <IconifyIcon icon="lucide:trash-2" aria-hidden="true" />
                删除
              </Button>
            </span>
          </Tooltip>
        </div>

        <div class="action-group action-group-secondary">
          <Popover placement="bottomRight" trigger="click">
            <template #content>
              <div class="column-popover">
                <div class="column-popover-header">
                  <div>
                    <strong>展示列</strong>
                    <p>名称列固定展示，其余列按当前维度保存。</p>
                  </div>
                  <Button type="link" @click="resetVisibleColumns">
                    恢复默认
                  </Button>
                </div>
                <Checkbox.Group
                  v-model:value="visibleColumnKeys"
                  class="column-options"
                >
                  <Checkbox
                    v-for="field in visibleColumnOptions"
                    :key="field.key"
                    :disabled="field.disabled"
                    :value="field.key"
                  >
                    {{ field.label }}
                  </Checkbox>
                </Checkbox.Group>
              </div>
            </template>
            <Button :aria-label="`配置${schema.label}展示列`">
              <IconifyIcon icon="lucide:columns-3" aria-hidden="true" />
              列
            </Button>
          </Popover>
          <Tag class="column-count">{{ visibleFields.length }} 列</Tag>
          <Button
            :disabled="!selectedAccountId"
            :loading="exporting"
            @click="exportData"
          >
            <IconifyIcon icon="lucide:download" aria-hidden="true" />
            导出
          </Button>
        </div>
      </div>

      <div
        v-if="selectedRowKeys.length > 0"
        class="selection-notice"
        role="status"
      >
        <IconifyIcon icon="lucide:check-check" aria-hidden="true" />
        已选择 {{ selectedRowKeys.length }} 个{{
          activeLevel.label
        }}对象；当前仅支持查看、筛选和导出。
        <button type="button" @click="clearSelection">取消选择</button>
      </div>

      <div
        :aria-labelledby="`delivery-object-tab-${activeCategory}`"
        id="delivery-object-table"
        role="tabpanel"
      >
        <Alert
          v-if="errorMessage"
          class="workspace-error"
          :message="errorMessage"
          show-icon
          type="error"
        >
          <template #action>
            <Button @click="loadRows">重试</Button>
          </template>
        </Alert>

        <div
          v-else
          class="workspace-table"
          :style="{ '--workspace-table-width': `${tableWidth}px` }"
        >
          <Table
            :columns="tableColumns"
            :data-source="rows"
            :loading="loading"
            :pagination="false"
            :row-class-name="rowClassName"
            :row-selection="rowSelection"
            :scroll="{ x: tableWidth }"
            table-layout="fixed"
            row-key="key"
            @change="handleTableChange"
          >
            <template #headerCell="{ column }">
              <span
                v-if="column.key === 'budget'"
                class="budget-column-heading"
              >
                <span>预算</span>
                <Tooltip
                  title="广告系列或广告组的当前预算；写入权限接入后可编辑。"
                >
                  <button
                    aria-label="预算说明"
                    class="budget-help"
                    type="button"
                    @click.stop
                  >
                    <IconifyIcon icon="lucide:circle-help" aria-hidden="true" />
                  </button>
                </Tooltip>
              </span>
            </template>

            <template #bodyCell="{ column, record, text }">
              <template v-if="column.key === '__deliveryToggle'">
                <Tooltip :title="deliveryToggleTitle(asDashboardRow(record))">
                  <span
                    class="delivery-toggle-cell"
                    :class="{
                      'delivery-toggle-cell-unknown': !deliveryStateValue(
                        asDashboardRow(record),
                      ),
                    }"
                  >
                    <Switch
                      v-if="deliveryStateValue(asDashboardRow(record))"
                      :aria-label="
                        deliveryToggleAriaLabel(asDashboardRow(record))
                      "
                      :checked="isDeliveryEnabled(asDashboardRow(record))"
                      disabled
                    />
                    <span v-else aria-hidden="true">—</span>
                  </span>
                </Tooltip>
              </template>
              <template v-else-if="column.key === '__deliveryState'">
                <Tag
                  :color="statusColor(asDashboardRow(record))"
                  class="status-cell"
                >
                  <span class="status-dot" aria-hidden="true"></span>
                  {{ statusText(asDashboardRow(record)) }}
                </Tag>
              </template>
              <Tooltip
                v-else-if="column.key === 'name'"
                :title="
                  renderValue(
                    text,
                    asDashboardRow(record),
                    asDashboardField(column),
                  )
                "
              >
                <span class="object-name">{{
                  renderValue(
                    text,
                    asDashboardRow(record),
                    asDashboardField(column),
                  )
                }}</span>
              </Tooltip>
              <Tooltip
                v-else-if="column.dataIndex === 'id'"
                :title="
                  renderValue(
                    text,
                    asDashboardRow(record),
                    asDashboardField(column),
                  )
                "
              >
                <span class="object-id">{{
                  renderValue(
                    text,
                    asDashboardRow(record),
                    asDashboardField(column),
                  )
                }}</span>
              </Tooltip>
              <Tooltip
                v-else-if="column.key === 'budget'"
                title="预算编辑需接入投放平台写入权限后开放"
              >
                <span class="budget-cell">
                  <span>{{
                    renderValue(
                      text,
                      asDashboardRow(record),
                      asDashboardField(column),
                    )
                  }}</span>
                  <button
                    aria-label="预算编辑暂未开放"
                    class="budget-edit-affordance"
                    disabled
                    type="button"
                  >
                    <IconifyIcon icon="lucide:pencil" aria-hidden="true" />
                  </button>
                </span>
              </Tooltip>
              <span v-else>{{
                renderValue(
                  text,
                  asDashboardRow(record),
                  asDashboardField(column),
                )
              }}</span>
            </template>

            <template #emptyText>
              <Empty
                :description="
                  !selectedAccountId
                    ? props.accountsLoading
                      ? '正在加载广告账户'
                      : props.accountsError
                        ? '账户加载失败，请点击页头重试'
                        : '当前日期暂无本人广告账户'
                    : loading
                      ? '正在载入对象数据'
                      : '当前筛选条件下没有对象'
                "
              />
            </template>

            <template #summary>
              <Table.Summary fixed>
                <Table.Summary.Row
                  v-for="summary in summaryRows"
                  :key="summary.currency"
                >
                  <Table.Summary.Cell :index="0" />
                  <Table.Summary.Cell :index="1" />
                  <Table.Summary.Cell :index="2" />
                  <Table.Summary.Cell
                    v-for="(field, index) in visibleFields"
                    :key="field.key"
                    :index="index + 3"
                  >
                    <strong v-if="field.key === 'name'">
                      {{ summaryValue(summary, field) }}
                    </strong>
                    <span v-else>{{ summaryValue(summary, field) }}</span>
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              </Table.Summary>
            </template>
          </Table>
        </div>
      </div>

      <footer class="workspace-footer">
        <p>
          {{ total }} 条{{ activeLevel.label }}对象；横向滚动仅发生在数据表内。
        </p>
        <Pagination
          v-model:current="page"
          v-model:page-size="pageSize"
          :page-size-options="['10', '20', '50']"
          :total="total"
          show-less-items
          show-size-changer
          @change="handlePageChange"
        />
      </footer>
    </div>
  </section>
</template>

<style scoped>
.delivery-workspace {
  min-width: 0;
}

.workspace-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.workspace-heading h2 {
  margin: 0;
  color: #17233a;
  font-size: 20px;
  font-weight: 650;
  line-height: 1.25;
}

.workspace-heading p {
  max-width: 760px;
  margin: 5px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

.workspace-meta {
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  padding-top: 3px;
  color: #7c8798;
  font-size: 12px;
  white-space: nowrap;
}

.workspace-frame {
  overflow: hidden;
  border: 1px solid #dbe4f0;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(15 23 42 / 5%);
}

.account-switcher {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  min-height: 54px;
  padding: 8px 16px;
  border-bottom: 1px solid #e6edf5;
  background: #f8fbff;
}

.account-switcher-label {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 6px;
  color: #526277;
  font-size: 12px;
  font-weight: 600;
}

.account-switcher-label > svg {
  color: #2563eb;
  font-size: 16px;
}

.account-list {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 8px;
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}

.account-list::-webkit-scrollbar {
  display: none;
}

.account-list-item {
  display: inline-flex;
  flex: none;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border: 1px solid #dbe4f0;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.account-list-item:hover {
  border-color: #93c5fd;
  background: #eff6ff;
  color: #1d4ed8;
}

.account-list-item:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.account-list-item-active {
  border-color: #60a5fa;
  background: #dbeafe;
  color: #1d4ed8;
}

.account-list-empty {
  color: #7c8798;
  font-size: 12px;
  line-height: 1.45;
  white-space: nowrap;
}

.object-type-tabs {
  display: flex;
  min-width: 0;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.object-type-tab {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 30px;
  padding: 6px 9px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: #526277;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  transition:
    background-color 140ms ease,
    border-color 140ms ease,
    color 140ms ease;
}

.object-type-tab:hover {
  background: #edf5ff;
  color: #1d4ed8;
}

.object-type-tab-active {
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 650;
}

.object-type-tab:focus-visible,
.budget-help:focus-visible,
.selection-notice button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

.workspace-context,
.workspace-filters,
.workspace-actions,
.workspace-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid #e9eef5;
}

.workspace-context {
  background: #fff;
}

.context-copy {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  min-width: 0;
}

.context-copy > svg {
  flex: none;
  margin-top: 2px;
  color: #2563eb;
  font-size: 16px;
}

.context-copy strong,
.context-copy span {
  display: block;
}

.context-copy strong {
  color: #27364b;
  font-size: 13px;
  font-weight: 600;
}

.context-copy span {
  margin-top: 2px;
  color: #7c8798;
  font-size: 12px;
  line-height: 1.45;
}

.context-counts,
.filter-controls,
.action-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.context-counts {
  flex: none;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.workspace-filters {
  flex-wrap: wrap;
  background: #fbfdff;
}

.filter-controls {
  flex: 1;
  justify-content: flex-end;
  min-width: min(100%, 540px);
  flex-wrap: wrap;
}

.object-search {
  width: min(100%, 260px);
}

.status-select {
  width: 126px;
}

.workspace-actions {
  flex-wrap: wrap;
  background: #fff;
}

.action-group {
  flex-wrap: wrap;
}

.action-group-secondary {
  margin-left: auto;
}

.action-group > span {
  display: inline-flex;
}

.column-count {
  margin: 0;
}

.column-popover {
  width: min(320px, calc(100vw - 32px));
}

.column-popover-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.column-popover-header strong {
  color: #27364b;
  font-size: 13px;
}

.column-popover-header p {
  margin: 3px 0 0;
  color: #7c8798;
  font-size: 12px;
  line-height: 1.45;
}

.column-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
  max-height: 280px;
  overflow-y: auto;
}

.selection-notice {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-bottom: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1e40af;
  font-size: 12px;
  line-height: 1.45;
}

.selection-notice button {
  margin-left: auto;
  border: 0;
  background: transparent;
  color: #1d4ed8;
  cursor: pointer;
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.workspace-error {
  margin: 16px;
}

.workspace-table {
  min-width: 0;
}

.workspace-table :deep(.workspace-selected-row > td) {
  background: #eff6ff !important;
}

.status-cell {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

.delivery-toggle-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
}

.delivery-toggle-cell-unknown {
  color: #94a3b8;
  font-size: 16px;
  font-weight: 600;
}

.status-dot {
  width: 6px;
  height: 6px;
  flex: none;
  border-radius: 50%;
  background: currentcolor;
}

.budget-column-heading,
.budget-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  white-space: nowrap;
}

.budget-help,
.budget-edit-affordance {
  display: inline-grid;
  width: 24px;
  height: 24px;
  flex: none;
  place-items: center;
  padding: 0;
  border: 0;
  background: transparent;
}

.budget-help {
  color: #94a3b8;
  cursor: help;
}

.budget-help:hover {
  color: #2563eb;
}

.budget-edit-affordance {
  color: #94a3b8;
  cursor: not-allowed;
}

.budget-edit-affordance:disabled {
  opacity: 1;
}

.object-name,
.object-id {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.object-name {
  color: #1d4ed8;
  font-weight: 600;
}

.object-id {
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
}

.summary-label {
  color: #526277;
  font-size: 12px;
  font-weight: 650;
}

.workspace-footer {
  min-height: 58px;
  border-bottom: 0;
  background: #fff;
}

.workspace-footer p {
  margin: 0;
  color: #7c8798;
  font-size: 12px;
}

@media (max-width: 900px) {
  .workspace-heading,
  .workspace-context,
  .workspace-footer {
    align-items: flex-start;
    flex-direction: column;
  }

  .workspace-meta,
  .context-counts {
    align-items: flex-start;
  }

  .workspace-meta {
    padding-top: 0;
  }

  .filter-controls {
    justify-content: flex-start;
  }

  .action-group-secondary {
    margin-left: 0;
  }
}

@media (max-width: 640px) {
  .workspace-heading h2 {
    font-size: 18px;
  }

  .account-switcher,
  .workspace-context,
  .workspace-filters,
  .workspace-actions,
  .workspace-footer,
  .selection-notice {
    padding-right: 12px;
    padding-left: 12px;
  }

  .account-switcher {
    gap: 8px;
  }

  .object-type-tabs {
    flex-wrap: wrap;
    overflow-x: visible;
  }

  .filter-controls,
  .object-search,
  .status-select {
    width: 100%;
  }

  .column-options {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .object-type-tab {
    transition: none;
  }
}
</style>
