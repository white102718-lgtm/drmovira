<script lang="ts" setup>
import type { TableColumnsType, UploadFile, UploadProps } from 'ant-design-vue';
import type { AssetExportColumn } from './asset-export';
import type { AssetFilterValues } from './asset-filter';

import type {
  AdAccountAsset,
  AdAccountAssetBatchField,
  AdAccountAssetImportFailure,
  AdAccountAssetImportHistory,
  AdAccountAssetPageParams,
  AdAccountInventoryStatus,
  AssetLifecycleDetail,
} from '#/api';
import type { TableCopyColumn } from '#/views/components/useTableRangeSelection';

import {
  computed,
  defineAsyncComponent,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import { useDebounceFn } from '@vueuse/core';
import {
  Alert,
  Button,
  Card,
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
  Tag,
  Upload,
  UploadDragger,
} from 'ant-design-vue';
import {
  getAdAccountAssetsByIds,
  getAdAccountAssetPage,
  getAdAccountImportFailedFile,
  getAdAccountImportHistory,
  importAdAccountAssets,
  replaceAdAccountAssetAssignments,
  saveAdAccountAssetSpreadsheet,
  searchAllAdAccountAssets,
  updateAdAccountAsset,
} from '#/api';
import { ApiBusinessError } from '#/api/backend-response';
import { FACEBOOK_AD_ACCOUNT_STATUS_LABELS } from '#/constants/facebook-ad-account-status';
import OverflowTooltip from '#/views/components/OverflowTooltip.vue';
import { useTableRangeSelection } from '#/views/components/useTableRangeSelection';

import { loadAdAccountLifecycleDetail } from './ad-account-lifecycle';
import { createAdAccountAssetDataColumns } from './ad-account-table-columns';
import {
  ensureAdAccountOptions,
  useAssetOptionCache,
} from './asset-option-cache';
import {
  ASSET_MODAL_TABLE_BODY_HEIGHT,
  ASSET_TABLE_BODY_HEIGHT,
} from './asset-table-layout';
import AssetBatchEditModal, {
  type AssetBatchEditField,
  type AssetBatchEditSubmission,
  type AssetSpreadsheetSourceRow,
} from './AssetBatchEditModal.vue';
import {
  chunkAssetExportIds,
  downloadAssetWorkbook,
  formatAssetExportTimestamp,
} from './asset-export';
import {
  AD_ACCOUNT_ASSET_FILTER_FIELDS,
  matchesAssetFilterValue,
  matchesAssetKeyword,
  normalizeAssetFilterValues,
} from './asset-filter';
import StableUserSelect from '../../components/StableUserSelect.vue';
import { AD_ACCOUNT_EDITOR_FIELDS } from './asset-types';
import AdAccountDailyLimitHistoryModal from './AdAccountDailyLimitHistoryModal.vue';
import AssetLifecycleDrawer from './AssetLifecycleDrawer.vue';

interface AdAccountAssetRow extends AdAccountAsset {
  usageDepartment?: string;
  usageUsers?: string;
}

type AccountSelectionScope = 'all-data' | 'current-page' | 'manual';

// Univer 仅在打开 Office 式批量编辑器时加载，避免增加广告户列表首屏体积。
const AssetOfficeSpreadsheetModal = defineAsyncComponent(
  () => import('./AssetOfficeSpreadsheetModal.vue'),
);

const props = defineProps<{
  canManage: boolean;
  filters: AssetFilterValues;
  keyword: string;
  page: number;
  pageSize: number;
  pageSizeOptions: string[];
  restoring: boolean;
  neumorphic?: boolean;
}>();
const emit = defineEmits<{
  paginationChange: [page: number, pageSize: number];
}>();
const router = useRouter();

const lifecycleOpen = ref(false);
const lifecycleLoading = ref(false);
const lifecycleAccountId = ref<string>();
const lifecycleDetail = ref<AssetLifecycleDetail>();
let lifecycleRequestVersion = 0;
const dailyLimitHistoryOpen = ref(false);
const dailyLimitHistoryAccountId = ref<string>();

const ACCOUNT_ROWS_CACHE_MAX_AGE = 15_000;
const IMPORT_MAX_FILE_SIZE = 5 * 1024 * 1024;
const AD_ACCOUNT_IMPORT_HEADERS = [
  '*账户ID',
  '账户名称',
  '账户类型',
  '账户属性',
  '所属渠道',
  '管理BM',
  '管理BM ID',
  '备份BM',
  '备份BM ID',
  '时区',
  '卡台',
  '卡号',
  '备注',
] as const;
const AD_ACCOUNT_IMPORT_OPTIONAL_HEADERS = ['使用人'] as const;
const ACCOUNT_TABLE_SCROLL_X = 3779;

const selectableColumns: TableColumnsType<AdAccountAssetRow> = [
  ...createAdAccountAssetDataColumns<AdAccountAssetRow>().flatMap((column) => [
    column,
    ...(column.key === 'accountStatus'
      ? [
          {
            align: 'left' as const,
            dataIndex: 'accountDailyLimit',
            key: 'accountDailyLimit',
            title: '账户日限额',
            width: 140,
          },
        ]
      : []),
  ]),
  {
    dataIndex: 'remark',
    key: 'remark',
    title: '备注',
    width: 180,
  },
  {
    dataIndex: 'usageUsers',
    key: 'usageUsers',
    title: '使用人',
    width: 150,
  },
  {
    dataIndex: 'usageDepartment',
    key: 'usageDepartment',
    title: '使用部门',
    width: 150,
  },
];
const columns: TableColumnsType<AdAccountAssetRow> = [
  ...selectableColumns.map((column, columnIndex) => ({
    ...column,
    customCell: (_record: AdAccountAssetRow, rowIndex?: number) =>
      createSelectableCell(rowIndex, columnIndex),
  })),
  { fixed: 'right', key: 'actions', title: '操作', width: 148 },
];
const importFailureColumns: TableColumnsType<AdAccountAssetImportFailure> = [
  { dataIndex: 'line', key: 'line', title: '行号', width: 88 },
  { dataIndex: 'message', key: 'message', title: '失败原因' },
];
const importHistoryColumns: TableColumnsType<AdAccountAssetImportHistory> = [
  { dataIndex: 'createdAt', key: 'createdAt', title: '导入时间', width: 172 },
  { dataIndex: 'fileName', key: 'fileName', title: '导入文件', width: 220 },
  { dataIndex: 'totalCount', key: 'totalCount', title: '总数', width: 88 },
  { dataIndex: 'successCount', key: 'successCount', title: '成功', width: 88 },
  { key: 'failureCount', title: '失败', width: 88 },
  { key: 'actions', title: '操作', width: 220 },
];

const platformStatusMeta: Record<string, { color: string; label: string }> = {
  '1': { color: 'success', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[1]! },
  '2': { color: 'error', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[2]! },
  '3': { color: 'warning', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[3]! },
  '7': { color: 'warning', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[7]! },
  '8': { color: 'warning', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[8]! },
  '9': { color: 'warning', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[9]! },
  '100': { color: 'error', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[100]! },
  '101': { color: 'error', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[101]! },
  '201': { color: 'success', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[201]! },
  '202': { color: 'error', label: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[202]! },
};
const syncStatusMeta: Record<
  NonNullable<AdAccountAsset['syncStatus']>,
  { color: string; label: string }
> = {
  MANUAL_LOCKED: { color: 'warning', label: '人工锁定' },
  PLATFORM_MISSING: { color: 'default', label: '平台未同步' },
  SYNCED: { color: 'success', label: '已同步' },
};
const inventoryStatusMeta: Record<
  AdAccountInventoryStatus,
  { color: string; label: string }
> = {
  ASSIGNED: { color: 'success', label: '已分配' },
  AVAILABLE: { color: 'default', label: '可用' },
  DISABLED: { color: 'error', label: '已停用' },
  RETURN_PENDING: { color: 'warning', label: '待回收' },
};
const editableInventoryStatusOptions = Object.entries(inventoryStatusMeta).map(
  ([value, meta]) => ({
    disabled: value === 'RETURN_PENDING',
    label: meta.label,
    value,
  }),
);

function getPlatformStatusMeta(value: unknown) {
  if (value === undefined || value === null || String(value).trim() === '') {
    return { color: 'default', label: '-' };
  }
  return (
    platformStatusMeta[String(value)] ?? {
      color: 'default',
      label: '未知',
    }
  );
}

function getInventoryStatusMeta(value: unknown) {
  const status = String(value ?? 'AVAILABLE') as AdAccountInventoryStatus;
  return inventoryStatusMeta[status] ?? inventoryStatusMeta.AVAILABLE;
}

const accountDailyLimitFormatter = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 2,
});

function formatAccountDailyLimit(value: null | number | undefined) {
  return value === undefined || value === null
    ? '-'
    : accountDailyLimitFormatter.format(value);
}

function assetTableRawText(value: unknown) {
  if (value === undefined || value === null) return '';
  return typeof value === 'string' ? value.trim() : String(value);
}

function assetTableDisplayText(value: unknown) {
  return assetTableRawText(value) || '-';
}

function adAccountColumnDisplayText(account: object, columnKey: unknown) {
  return assetTableDisplayText(Reflect.get(account, String(columnKey)));
}

const accountRows = ref<AdAccountAssetRow[]>([]);
const { accountAttributeOptions, accountTypeOptions, channelOptions } =
  useAssetOptionCache();
const selectedAccountIds = ref<string[]>([]);
const accountSelectionScope = ref<AccountSelectionScope>('manual');
const currentPage = ref(props.page);
const pageSize = ref(props.pageSize);
const isPointerTableFocus = ref(false);
const drawerOpen = ref(false);
const batchEditOpen = ref(false);
const batchEditSubmitting = ref(false);
const officeSpreadsheetOpen = ref(false);
const officeSpreadsheetSubmitting = ref(false);
const editingAccountId = ref('');
const editingUsageUserIds = ref<string[]>([]);
const editingUsageUserLabel = ref('');
const inventoryStatus = ref<AdAccountInventoryStatus>('AVAILABLE');
const exporting = ref(false);
const importError = ref('');
const importFailureModalOpen = ref(false);
const importFailures = ref<AdAccountAssetImportFailure[]>([]);
const importHistoryLoading = ref(false);
const importHistoryModalOpen = ref(false);
const importHistoryRecords = ref<AdAccountAssetImportHistory[]>([]);
const importModalOpen = ref(false);
const importing = ref(false);
const loading = ref(false);
const saving = ref(false);
const total = ref(0);
const uploadFiles = ref<UploadFile[]>([]);
const selectedImportFile = ref<File>();
let latestLoadRequestId = 0;
let resettingForFilters = false;
let allAccountRowsCache:
  | { createdAt: number; key: string; rows: AdAccountAssetRow[] }
  | undefined;
let allAccountRowsCacheRequest:
  | { key: string; request: Promise<AdAccountAssetRow[]> }
  | undefined;
let allAccountRowsCacheVersion = 0;
const form = reactive<Omit<AdAccountAsset, 'accountId'>>({
  accountName: '',
  accountType: '',
  accountAttribute: '',
  backupManagedBm: '',
  backupManagedBmId: '',
  cardNumber: '',
  cardStation: '',
  channelId: undefined,
  channelName: undefined,
  inventoryStatus: 'AVAILABLE',
  managedBm: '',
  managedBmId: '',
  remark: '',
  timezone: '',
});

const canEditUsageUser = computed(() => inventoryStatus.value === 'ASSIGNED');
const selectedAccountCount = computed(() =>
  accountSelectionScope.value === 'all-data'
    ? total.value
    : selectedAccountIds.value.length,
);
const selectedAccountSummary = computed(() => {
  if (selectedAccountCount.value === 0) return '';
  if (accountSelectionScope.value === 'all-data') {
    return `已选择全部 ${selectedAccountCount.value} 条`;
  }
  if (accountSelectionScope.value === 'current-page') {
    return `已选择当前页 ${selectedAccountCount.value} 条`;
  }
  return `已选择 ${selectedAccountCount.value} 条`;
});
const batchEditRows = ref<AssetSpreadsheetSourceRow[]>([]);
const batchEditLoading = ref(false);
const officeSpreadsheetRows = ref<AssetSpreadsheetSourceRow[]>([]);
const officeSpreadsheetLoading = ref(false);
const adAccountEditorFields: AssetBatchEditField[] =
  AD_ACCOUNT_EDITOR_FIELDS.map((field) =>
    field.key === 'userIds'
      ? {
          ...field,
          helpText: '库存状态为“已分配”时必须选择使用人。',
          multiple: true,
          requiredWhen: {
            fieldKey: 'inventoryStatus',
            hint: '库存状态为“已分配”时必填',
            incompatibleMessage: '选择使用人时，库存状态必须为“已分配”',
            values: ['ASSIGNED'],
          },
        }
      : { ...field },
  );
const batchEditFields = computed<AssetBatchEditField[]>(() =>
  adAccountEditorFields.map((field) => {
    if (field.key === 'accountType') {
      return {
        ...field,
        options: accountTypeOptions.value,
      };
    }
    if (field.key === 'accountAttribute') {
      return {
        ...field,
        options: accountAttributeOptions.value,
      };
    }
    if (field.key === 'channelId') {
      return { ...field, options: channelOptions.value };
    }
    if (field.key === 'inventoryStatus') {
      return {
        ...field,
        options: editableInventoryStatusOptions.filter(
          (option) => !option.disabled,
        ),
      };
    }
    return field;
  }),
);
const officeSpreadsheetFields = computed<AssetBatchEditField[]>(() =>
  batchEditFields.value
    .filter((field) => field.key !== 'inventoryStatus')
    .map((field) =>
      field.key === 'userIds'
        ? {
            ...field,
            helpText:
              '填写一位或多位使用人自动设为已使用；留空自动设为可分配。',
            requiredWhen: undefined,
          }
        : field,
    ),
);
const batchFieldNames: Record<string, AdAccountAssetBatchField> = {
  accountAttribute: 'ACCOUNT_ATTRIBUTE',
  accountType: 'ACCOUNT_TYPE',
  backupManagedBm: 'BACKUP_MANAGED_BM',
  backupManagedBmId: 'BACKUP_MANAGED_BM_ID',
  cardNumber: 'CARD_NUMBER',
  cardStation: 'CARD_STATION',
  channelId: 'CHANNEL_ID',
  inventoryStatus: 'INVENTORY_STATUS',
  managedBm: 'MANAGED_BM',
  managedBmId: 'MANAGED_BM_ID',
  remark: 'REMARK',
  timezone: 'TIMEZONE',
  userIds: 'USAGE_USER_IDS',
};
const accountFilterFieldsByKey = new Map(
  AD_ACCOUNT_ASSET_FILTER_FIELDS.map((field) => [field.key, field]),
);
const currentPageAccountKeys = computed(() =>
  accountRows.value.map(accountRowKey),
);

function hasSameAccountKeys(left: string[], right: string[]) {
  if (left.length !== right.length) return false;
  const rightKeys = new Set(right);
  return left.every((key) => rightKeys.has(key));
}

function selectCurrentPageAccounts(currentRowKeys: unknown[]) {
  accountSelectionScope.value = 'current-page';
  selectedAccountIds.value = currentRowKeys.map(String);
}

function selectAllAccounts() {
  accountSelectionScope.value = 'all-data';
  selectedAccountIds.value = currentPageAccountKeys.value;
}

const rowSelection = computed(() => ({
  columnWidth: 48,
  fixed: true,
  onChange: (keys: unknown[]) => {
    const selectedKeys = keys.map(String);
    accountSelectionScope.value = hasSameAccountKeys(
      selectedKeys,
      currentPageAccountKeys.value,
    )
      ? 'current-page'
      : 'manual';
    selectedAccountIds.value = selectedKeys;
  },
  preserveSelectedRowKeys: true,
  selectedRowKeys:
    accountSelectionScope.value === 'all-data'
      ? currentPageAccountKeys.value
      : selectedAccountIds.value,
  selections: [
    {
      key: 'current-page',
      onSelect: selectCurrentPageAccounts,
      text: '全选当前页',
    },
    {
      key: 'all-data',
      onSelect: selectAllAccounts,
      text: '全选所有数据',
    },
  ],
}));
const tableCopyTextByColumnKey: Record<
  string,
  TableCopyColumn<AdAccountAssetRow>['getText']
> = {
  accountAttribute: (account) => assetTableRawText(account.accountAttribute),
  accountDailyLimit: (account) => assetTableRawText(account.accountDailyLimit),
  accountId: (account) => assetTableRawText(account.accountId),
  accountName: (account) => assetTableRawText(account.accountName),
  accountStatus: (account) =>
    assetTableRawText(account.accountStatus)
      ? getPlatformStatusMeta(account.accountStatus).label
      : '',
  accountType: (account) => assetTableRawText(account.accountType),
  backupManagedBm: (account) => assetTableRawText(account.backupManagedBm),
  backupManagedBmId: (account) => assetTableRawText(account.backupManagedBmId),
  cardNumber: (account) => assetTableRawText(account.cardNumber),
  cardStation: (account) => assetTableRawText(account.cardStation),
  channelName: (account) => assetTableRawText(account.channelName),
  deliveryDate: (account) => assetTableRawText(account.deliveryDate),
  inventoryStatus: (account) =>
    assetTableRawText(account.inventoryStatus)
      ? getInventoryStatusMeta(account.inventoryStatus).label
      : '',
  managedBm: (account) => assetTableRawText(account.managedBm),
  managedBmId: (account) => assetTableRawText(account.managedBmId),
  remark: (account) => assetTableRawText(account.remark),
  timezone: (account) => assetTableRawText(account.timezone),
  usageDepartment: (account) => assetTableRawText(account.usageDepartment),
  usageUsers: (account) => assetTableRawText(account.usageUsers),
};
const tableCopyColumns = computed<TableCopyColumn<AdAccountAssetRow>[]>(() =>
  selectableColumns.map((column) => {
    const key = String(column.key);
    const getText = tableCopyTextByColumnKey[key];
    if (!getText) {
      throw new Error(`广告账户表格列缺少复制映射：${key}`);
    }

    // 复制顺序必须直接来自展示列，避免调整列后账户 ID 错复制成账户属性。
    return { getText, key };
  }),
);
const tableSelection = useTableRangeSelection({
  columns: tableCopyColumns,
  rows: accountRows,
});

function createSelectableCell(
  rowIndex: number | undefined,
  columnIndex: number,
) {
  if (rowIndex === undefined) return {};

  return {
    'data-column-index': columnIndex,
    'data-row-index': rowIndex,
    'data-table-selection-cell': '',
    class: [
      'cursor-cell',
      tableSelection.isCellSelected(rowIndex, columnIndex)
        ? 'table-range-selected'
        : '',
    ],
  };
}

function getTableCellCoordinates(target: EventTarget | null) {
  const cell =
    target instanceof Element
      ? target.closest<HTMLElement>('[data-table-selection-cell]')
      : null;
  if (!cell) return;

  const columnIndex = Number(cell.dataset.columnIndex);
  const rowIndex = Number(cell.dataset.rowIndex);
  return Number.isInteger(columnIndex) && Number.isInteger(rowIndex)
    ? { columnIndex, rowIndex }
    : undefined;
}

function beginTableSelection(event: PointerEvent) {
  // 需求是桌面端鼠标框选；触摸操作继续交给宽表横向滚动，避免手势冲突。
  if (event.button !== 0 || event.pointerType !== 'mouse') return;

  const coordinates = getTableCellCoordinates(event.target);
  if (!coordinates) return;

  isPointerTableFocus.value = true;
  (event.currentTarget as HTMLElement).focus({ preventScroll: true });
  tableSelection.beginSelection(coordinates.rowIndex, coordinates.columnIndex);
  event.preventDefault();
}

function extendTableSelection(event: PointerEvent) {
  if (!tableSelection.isSelecting.value) return;

  const coordinates = getTableCellCoordinates(event.target);
  if (!coordinates) return;

  tableSelection.extendSelection(coordinates.rowIndex, coordinates.columnIndex);
  event.preventDefault();
}

function stopTableSelection() {
  tableSelection.endSelection();
}

function handleTableKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && tableSelection.selection.value) {
    isPointerTableFocus.value = false;
    tableSelection.clearSelection();
    event.preventDefault();
    return;
  }

  const offsetByKey: Partial<
    Record<string, { columnOffset: number; rowOffset: number }>
  > = {
    ArrowDown: { columnOffset: 0, rowOffset: 1 },
    ArrowLeft: { columnOffset: -1, rowOffset: 0 },
    ArrowRight: { columnOffset: 1, rowOffset: 0 },
    ArrowUp: { columnOffset: 0, rowOffset: -1 },
  };
  const offset = offsetByKey[event.key];
  if (!offset) return;

  isPointerTableFocus.value = false;
  if (
    tableSelection.moveSelection(
      offset.rowOffset,
      offset.columnOffset,
      event.shiftKey,
    )
  ) {
    event.preventDefault();
  }
}

function handleTableBlur() {
  isPointerTableFocus.value = false;
}

/** 账户ID与名称共同组成前端稳定行键，与数据库联合唯一键保持一致。 */
function accountRowKey(
  account: Pick<AdAccountAsset, 'accountId' | 'accountName'>,
) {
  return `${account.accountId}\u0000${account.accountName}`;
}

function resetForm(account: Partial<AdAccountAsset>) {
  editingAccountId.value = account.accountId ?? '';
  inventoryStatus.value = account.inventoryStatus ?? 'AVAILABLE';
  Object.assign(form, {
    accountDailyLimit: account.accountDailyLimit,
    accountName: account.accountName ?? '',
    accountType: account.accountType ?? '',
    accountAttribute: account.accountAttribute ?? '',
    backupManagedBm: account.backupManagedBm ?? '',
    backupManagedBmId: account.backupManagedBmId ?? '',
    cardNumber: account.cardNumber ?? '',
    cardStation: account.cardStation ?? '',
    channelId: account.channelId,
    channelName: account.channelName,
    inventoryStatus: account.inventoryStatus ?? 'AVAILABLE',
    managedBm: account.managedBm ?? '',
    managedBmId: account.managedBmId ?? '',
    remark: account.remark ?? '',
    timezone: account.timezone ?? '',
  });
}

/** 合并申请分配与直接指定的使用人，避免同一人因两种来源重复展示。 */
function getUsageUsers(...values: Array<string | undefined>) {
  return [
    ...new Set(
      values
        .flatMap((value) => value?.split(/[、,，;；]/) ?? [])
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  ].join('、');
}

/** 账户编辑、筛选和模板导入共用缓存后的有效选项。 */
async function ensureAccountOptionsReady() {
  await ensureAdAccountOptions();
  syncFormChannelName();
}

/** 渠道名称作为展示字段保存，始终由下拉选择的稳定渠道 ID 推导。 */
function syncFormChannelName() {
  if (!form.channelId) {
    form.channelName = undefined;
    return;
  }

  const channel = channelOptions.value.find(
    (item) => item.value === form.channelId,
  );
  if (channel) form.channelName = channel.label;
}

/** 列表与导出直接使用统一资产接口返回的使用人关系。 */
async function enrichAccountRows(accounts: AdAccountAsset[]) {
  return accounts.map((account) => ({
    ...account,
    usageDepartment: account.usageDepartmentName || '',
    usageUsers: getUsageUsers(account.usageUserName),
  }));
}

function matchesAccountKeyword(row: AdAccountAssetRow, keyword: string) {
  return matchesAssetKeyword(
    [row, getInventoryStatusMeta(row.inventoryStatus).label],
    keyword,
  );
}

function parseBatchAccountIds(keyword: string) {
  const accountIds = [
    ...new Set(
      keyword
        .trim()
        .split(/[\s,;，；]+/)
        .filter(Boolean),
    ),
  ];
  const isAccountId = /^(?:act_)?\d+(?:-\d+)*$/i;

  return accountIds.length > 1 && accountIds.every((id) => isAccountId.test(id))
    ? accountIds
    : undefined;
}

function accountFilterValue(row: AdAccountAssetRow, key: string) {
  if (key === 'applicationId') return undefined;
  if (key === 'inventoryAssigneeName') return row.usageUsers;
  return Reflect.get(row, key);
}

function matchesAccountFilters(row: AdAccountAssetRow) {
  return Object.entries(props.filters).every(([key, expected]) => {
    const field = accountFilterFieldsByKey.get(key);
    if (!field) return true;
    return matchesAssetFilterValue(
      accountFilterValue(row, key),
      expected,
      field.control,
    );
  });
}

function normalizeInventoryStatusFilter(
  values: readonly string[],
): AdAccountInventoryStatus[] | undefined {
  const statuses = values.filter(
    (value): value is AdAccountInventoryStatus =>
      value === 'ASSIGNED' ||
      value === 'AVAILABLE' ||
      value === 'DISABLED' ||
      value === 'RETURN_PENDING',
  );
  return statuses.length > 0 ? statuses : undefined;
}

function normalizePlatformStatusFilter(values: readonly string[]) {
  const statuses = values
    .filter((value) => value in FACEBOOK_AD_ACCOUNT_STATUS_LABELS)
    .map(Number);
  return statuses.length > 0 ? statuses : undefined;
}

function accountFilterValues(key: string) {
  const field = accountFilterFieldsByKey.get(key);
  const values = normalizeAssetFilterValues(props.filters[key], field?.control);
  return values.length > 0 ? values : undefined;
}

/** 所有列表筛选统一传给服务端，在数据库分页前完成组合匹配。 */
function pageFilterParams(): Omit<
  AdAccountAssetPageParams,
  'page' | 'pageSize'
> {
  return {
    accountAttribute: accountFilterValues('accountAttribute'),
    accountId: accountFilterValues('accountId'),
    accountName: accountFilterValues('accountName'),
    accountStatus: normalizePlatformStatusFilter(
      accountFilterValues('accountStatus') ?? [],
    ),
    accountType: accountFilterValues('accountType'),
    backupManagedBm: accountFilterValues('backupManagedBm'),
    backupManagedBmId: accountFilterValues('backupManagedBmId'),
    cardNumber: accountFilterValues('cardNumber'),
    cardStation: accountFilterValues('cardStation'),
    channelName: accountFilterValues('channelName'),
    inventoryStatus: normalizeInventoryStatusFilter(
      accountFilterValues('inventoryStatus') ?? [],
    ),
    inventoryAssigneeName: accountFilterValues('inventoryAssigneeName'),
    managedBm: accountFilterValues('managedBm'),
    managedBmId: accountFilterValues('managedBmId'),
    timezone: accountFilterValues('timezone'),
    usageDepartment: accountFilterValues('usageDepartment'),
    usageUsers: accountFilterValues('usageUsers'),
  };
}

function filterAccountRows(rows: AdAccountAssetRow[]) {
  return rows.filter(
    (row) =>
      matchesAccountKeyword(row, props.keyword) && matchesAccountFilters(row),
  );
}

function filterBatchAccountRows(rows: AdAccountAssetRow[]) {
  return rows.filter(matchesAccountFilters);
}

function invalidateAllAccountRowsCache() {
  allAccountRowsCache = undefined;
  allAccountRowsCacheRequest = undefined;
  allAccountRowsCacheVersion += 1;
}

/** 全量操作由服务端按列表相同口径一次查询；缓存键包含全部条件，避免跨筛选复用。 */
async function loadAllAccountRows() {
  const serverFilters = {
    ...pageFilterParams(),
    keyword: props.keyword.trim() || undefined,
  };
  const cacheKey = JSON.stringify(serverFilters);
  const now = Date.now();
  if (
    allAccountRowsCache &&
    allAccountRowsCache.key === cacheKey &&
    now - allAccountRowsCache.createdAt < ACCOUNT_ROWS_CACHE_MAX_AGE
  ) {
    return allAccountRowsCache.rows;
  }
  if (allAccountRowsCacheRequest?.key === cacheKey) {
    return allAccountRowsCacheRequest.request;
  }

  const cacheVersion = allAccountRowsCacheVersion;
  const request =
    searchAllAdAccountAssets(serverFilters).then(enrichAccountRows);
  allAccountRowsCacheRequest = { key: cacheKey, request };

  try {
    const rows = await request;
    if (cacheVersion === allAccountRowsCacheVersion) {
      allAccountRowsCache = { createdAt: Date.now(), key: cacheKey, rows };
    }
    return rows;
  } finally {
    if (allAccountRowsCacheRequest?.request === request) {
      allAccountRowsCacheRequest = undefined;
    }
  }
}

async function loadAccounts(page = currentPage.value) {
  const requestId = ++latestLoadRequestId;
  loading.value = true;
  try {
    const batchAccountIds = parseBatchAccountIds(props.keyword);
    if (batchAccountIds) {
      const rows = filterBatchAccountRows(
        await enrichAccountRows(await getAdAccountAssetsByIds(batchAccountIds)),
      );
      if (requestId !== latestLoadRequestId) return;

      const lastPage = Math.max(1, Math.ceil(rows.length / pageSize.value));
      const resolvedPage = Math.min(page, lastPage);
      accountRows.value = rows.slice(
        (resolvedPage - 1) * pageSize.value,
        resolvedPage * pageSize.value,
      );
      currentPage.value = resolvedPage;
      total.value = rows.length;
      emit('paginationChange', currentPage.value, pageSize.value);
      return;
    }

    const result = await getAdAccountAssetPage({
      ...pageFilterParams(),
      keyword: props.keyword.trim() || undefined,
      page,
      pageSize: pageSize.value,
    });
    const rows = await enrichAccountRows(result.items);
    if (requestId !== latestLoadRequestId) return;

    accountRows.value = rows;
    currentPage.value = result.page;
    total.value = result.total;
    emit('paginationChange', currentPage.value, pageSize.value);
  } finally {
    if (requestId === latestLoadRequestId) loading.value = false;
  }
}

// 统一使用资产页顶部搜索，防抖请求并忽略过期响应，避免输入过程中旧结果覆盖新结果。
const reloadAccountsForKeyword = useDebounceFn(() => void loadAccounts(1), 300);

function handleAccountFiltersChange() {
  accountSelectionScope.value = 'manual';
  selectedAccountIds.value = [];
  if (props.restoring) return;
  resettingForFilters = true;
  currentPage.value = 1;
  emit('paginationChange', 1, pageSize.value);
  reloadAccountsForKeyword();
  queueMicrotask(() => {
    resettingForFilters = false;
  });
}

function changeAccountPage(page: number, nextPageSize: number) {
  const isPageSizeChanged = nextPageSize !== pageSize.value;
  pageSize.value = nextPageSize;
  const nextPage = isPageSizeChanged ? 1 : page;
  currentPage.value = nextPage;
  emit('paginationChange', nextPage, nextPageSize);
  void loadAccounts(nextPage);
}

watch(() => props.keyword, handleAccountFiltersChange);
watch(() => props.filters, handleAccountFiltersChange, { deep: true });
watch([() => props.page, () => props.pageSize], ([nextPage, nextPageSize]) => {
  if (nextPage === currentPage.value && nextPageSize === pageSize.value) {
    return;
  }
  currentPage.value = nextPage;
  pageSize.value = nextPageSize;
  if (props.restoring || resettingForFilters) return;
  void loadAccounts(nextPage);
});
watch(accountRows, () => tableSelection.clearSelection());

/** 勾选操作按账户 ID 读取最新台账，避免为少量选择先拉取全部筛选结果。 */
async function loadSelectedAccountsForExport() {
  const accountIds = selectedAccountIds.value.map(
    (rowKey) => rowKey.split('\u0000', 1)[0] ?? '',
  );
  const accounts: AdAccountAsset[] = [];
  for (const batch of chunkAssetExportIds(accountIds)) {
    accounts.push(...(await getAdAccountAssetsByIds(batch)));
  }
  return enrichAccountRows(accounts);
}

/** 按当前搜索与筛选条件读取全部账户，供“全选所有数据”的批量操作共用。 */
async function loadAllFilteredAccounts() {
  const batchAccountIds = parseBatchAccountIds(props.keyword);
  if (batchAccountIds) {
    return filterBatchAccountRows(
      await enrichAccountRows(await getAdAccountAssetsByIds(batchAccountIds)),
    );
  }

  return filterAccountRows(await loadAllAccountRows());
}

/** 导出严格服从选择范围；保留未勾选时导出全部筛选结果的既有行为。 */
async function getAccountsForExport() {
  if (
    accountSelectionScope.value !== 'all-data' &&
    selectedAccountIds.value.length > 0
  ) {
    return loadSelectedAccountsForExport();
  }

  return loadAllFilteredAccounts();
}

async function exportAccounts() {
  exporting.value = true;
  try {
    await ensureAccountOptionsReady();
    const accounts = await getAccountsForExport();
    if (accounts.length === 0) {
      message.warning('暂无可导出的广告账户数据');
      return;
    }

    const columns: AssetExportColumn[] = [
      { key: 'accountName', label: '账户名称', width: 24 },
      { key: 'accountId', label: '*账户ID', width: 22 },
      { key: 'accountStatus', label: '平台状态', width: 14 },
      { key: 'accountDailyLimit', label: '账户日限额', width: 16 },
      { key: 'inventoryStatus', label: '库存状态', width: 14 },
      { key: 'syncStatus', label: '同步状态', width: 14 },
      {
        key: 'accountType',
        label: '账户类型',
        selectOptions: accountTypeOptions.value.map((item) => item.value),
        width: 16,
      },
      {
        key: 'accountAttribute',
        label: '账户属性',
        selectOptions: accountAttributeOptions.value.map((item) => item.value),
        width: 16,
      },
      { key: 'channelId', label: '渠道 ID', width: 16 },
      {
        key: 'channelName',
        label: '所属渠道',
        selectOptions: channelOptions.value.map((item) => item.label),
        width: 20,
      },
      { key: 'managedBm', label: '管理BM', width: 22 },
      { key: 'managedBmId', label: '管理BM ID', width: 20 },
      { key: 'backupManagedBm', label: '备份BM', width: 22 },
      { key: 'backupManagedBmId', label: '备份BM ID', width: 20 },
      { key: 'timezone', label: '时区', width: 16 },
      { key: 'cardStation', label: '卡台', width: 18 },
      { key: 'cardNumber', label: '卡号', width: 20 },
      { key: 'remark', label: '备注', width: 32 },
      { key: 'usageUsers', label: '使用人', width: 18 },
      { key: 'usageDepartment', label: '使用部门', width: 24 },
    ];
    const rows = accounts.map((account) => ({
      accountAttribute: account.accountAttribute,
      accountDailyLimit: account.accountDailyLimit ?? undefined,
      accountId: account.accountId,
      accountName: account.accountName,
      accountStatus:
        assetTableRawText(account.accountStatus) === ''
          ? ''
          : getPlatformStatusMeta(account.accountStatus).label,
      inventoryStatus:
        assetTableRawText(account.inventoryStatus) === ''
          ? ''
          : getInventoryStatusMeta(account.inventoryStatus).label,
      accountType: account.accountType,
      backupManagedBm: account.backupManagedBm,
      backupManagedBmId: account.backupManagedBmId,
      cardStation: account.cardStation,
      cardNumber: account.cardNumber,
      channelId: account.channelId || '',
      channelName: account.channelName || '',
      managedBm: account.managedBm,
      managedBmId: account.managedBmId,
      remark: account.remark ?? '',
      syncStatus: account.syncStatus
        ? syncStatusMeta[account.syncStatus].label
        : '',
      timezone: account.timezone,
      usageUsers: account.usageUsers || '',
      usageDepartment: account.usageDepartment || '',
    }));
    await downloadAssetWorkbook(
      `广告账户台账_${formatAssetExportTimestamp()}.xlsx`,
      '广告账户',
      columns,
      rows,
    );
    message.success(`已导出 ${rows.length} 条广告账户数据`);
  } finally {
    exporting.value = false;
  }
}

function openEditor(account: Partial<AdAccountAssetRow>) {
  if (!props.canManage) {
    message.warning('当前角色没有广告账户维护权限');
    return;
  }
  resetForm(account);
  editingUsageUserIds.value =
    account.assignments?.map((assignment) => assignment.userId) ?? [];
  editingUsageUserLabel.value = account.usageUserName ?? '';
  drawerOpen.value = true;
  void ensureAccountOptionsReady();
}

function openDailyLimitHistory(account: Partial<AdAccountAssetRow>) {
  const accountId = account.accountId?.trim();
  if (!accountId) {
    message.warning('该行缺少广告账户 ID，无法查看日限额记录');
    return;
  }
  dailyLimitHistoryAccountId.value = accountId;
  dailyLimitHistoryOpen.value = true;
}

async function openLifecycle(account: Partial<AdAccountAssetRow>) {
  const accountId = account.accountId?.trim();
  if (!accountId) {
    message.warning('该行缺少广告账户 ID，无法查看生命周期');
    return;
  }
  const requestVersion = ++lifecycleRequestVersion;
  lifecycleAccountId.value = accountId;
  lifecycleOpen.value = true;
  lifecycleLoading.value = true;
  lifecycleDetail.value = undefined;
  try {
    const detail = await loadAdAccountLifecycleDetail(accountId);
    if (requestVersion !== lifecycleRequestVersion) return;
    lifecycleDetail.value = detail;
  } finally {
    if (requestVersion === lifecycleRequestVersion) {
      lifecycleLoading.value = false;
    }
  }
}

function openApplicationDetail(applicationId: string) {
  void router.push({
    path: `/workbench/approvals/${encodeURIComponent(applicationId)}`,
  });
}

async function saveAccount() {
  if (inventoryStatus.value === 'RETURN_PENDING') {
    message.warning('待回收状态请在资源回收流程中变更');
    return;
  }
  if (
    inventoryStatus.value === 'ASSIGNED' &&
    editingUsageUserIds.value.length === 0
  ) {
    message.error('已分配状态必须指定至少一位使用人');
    return;
  }

  saving.value = true;
  try {
    await updateAdAccountAsset(editingAccountId.value, form, {
      skipErrorMessage: true,
    });
    await replaceAdAccountAssetAssignments(
      editingAccountId.value,
      inventoryStatus.value === 'ASSIGNED' ? editingUsageUserIds.value : [],
      inventoryStatus.value,
    );
    message.success('广告账户已更新');
    drawerOpen.value = false;
    invalidateAllAccountRowsCache();
    await loadAccounts();
  } catch (error) {
    const errorMessage =
      error instanceof ApiBusinessError
        ? error.message
        : '广告账户保存失败，请稍后重试';
    message.error(errorMessage);
  } finally {
    saving.value = false;
  }
}

function selectedAccountBusinessIds() {
  return [
    ...new Set(
      selectedAccountIds.value.map(
        (rowKey) => rowKey.split('\u0000', 1)[0] ?? '',
      ),
    ),
  ].filter(Boolean);
}

function visibleAccountsForSelection(accountIds: string[]) {
  if (accountSelectionScope.value === 'all-data') return accountRows.value;
  const selectedIdSet = new Set(accountIds);
  return accountRows.value.filter((account) =>
    selectedIdSet.has(account.accountId),
  );
}

/** Excel 与批量修改共用选择范围，确保“当前页”和“所有数据”的加载口径一致。 */
async function loadAccountsForBatchSelection(
  visibleAccounts: AdAccountAssetRow[],
  accountIds: string[],
) {
  if (accountSelectionScope.value === 'all-data') {
    return loadAllFilteredAccounts();
  }
  if (accountIds.length === 0) return [];

  const rows = await getAdAccountAssetsByIds(accountIds);
  const accountsById = new Map(
    visibleAccounts.map((account) => [account.accountId, account]),
  );
  rows.forEach((account) => accountsById.set(account.accountId, account));
  return accountIds
    .map((accountId) => accountsById.get(accountId))
    .filter((account): account is AdAccountAssetRow => Boolean(account));
}

async function openBatchEdit() {
  if (!props.canManage) {
    message.warning('当前角色没有广告账户维护权限');
    return;
  }
  const accountIds = selectedAccountBusinessIds();
  const visibleSelectedAccounts = visibleAccountsForSelection(accountIds);

  // 先使用列表中已经勾选的数据打开编辑器，避免批量查询失败或后端未热更新时出现空弹窗。
  batchEditRows.value = visibleSelectedAccounts.map(toBatchEditRow);
  batchEditOpen.value = true;
  batchEditLoading.value = true;
  try {
    await ensureAccountOptionsReady();
    const rows = await loadAccountsForBatchSelection(
      visibleSelectedAccounts,
      accountIds,
    );
    batchEditRows.value = rows.map(toBatchEditRow);

    if (selectedAccountCount.value > 0 && batchEditRows.value.length === 0) {
      message.error('未能加载已勾选的广告账户，请刷新列表后重试');
      batchEditOpen.value = false;
    }
  } finally {
    batchEditLoading.value = false;
  }
}

async function openOfficeSpreadsheet() {
  if (!props.canManage) {
    message.warning('当前角色没有广告账户维护权限');
    return;
  }
  const accountIds = selectedAccountBusinessIds();
  const visibleSelectedAccounts = visibleAccountsForSelection(accountIds);

  // Excel 入口必须读取广告户表格自身的勾选状态，不能复用父页面普通资产的选中 ID。
  officeSpreadsheetRows.value = visibleSelectedAccounts.map(toBatchEditRow);
  officeSpreadsheetOpen.value = true;
  officeSpreadsheetLoading.value = true;
  try {
    await ensureAccountOptionsReady();
    const rows = await loadAccountsForBatchSelection(
      visibleSelectedAccounts,
      accountIds,
    );
    officeSpreadsheetRows.value = rows.map(toBatchEditRow);

    if (
      selectedAccountCount.value > 0 &&
      officeSpreadsheetRows.value.length === 0
    ) {
      message.error('未能加载已勾选的广告账户，请刷新列表后重试');
      officeSpreadsheetOpen.value = false;
    }
  } finally {
    officeSpreadsheetLoading.value = false;
  }
}

/** 将列表或批量查询结果转换为电子表格的稳定暂存模型。 */
function toBatchEditRow(account: AdAccountAsset): AssetSpreadsheetSourceRow {
  return {
    id: account.accountId,
    values: {
      accountAttribute: account.accountAttribute ?? '',
      accountDailyLimit:
        account.accountDailyLimit == null
          ? ''
          : String(account.accountDailyLimit),
      accountId: account.accountId,
      accountName: account.accountName ?? '',
      accountStatus: getPlatformStatusMeta(account.accountStatus).label,
      accountType: account.accountType ?? '',
      backupManagedBm: account.backupManagedBm ?? '',
      backupManagedBmId: account.backupManagedBmId ?? '',
      cardNumber: account.cardNumber ?? '',
      cardStation: account.cardStation ?? '',
      channelId: account.channelId ?? '',
      deliveryDate: account.deliveryDate ?? '',
      inventoryStatus: account.inventoryStatus ?? 'AVAILABLE',
      managedBm: account.managedBm ?? '',
      managedBmId: account.managedBmId ?? '',
      remark: account.remark ?? '',
      syncStatus: account.syncStatus ?? '',
      timezone: account.timezone ?? '',
      userIds: (account.assignments ?? [])
        .filter((assignment) => assignment.status === 'ACTIVE')
        .map((assignment) => assignment.userId),
    },
  };
}

async function resolveBatchEditIdentifiers(identifiers: string[]) {
  if (identifiers.length === 0) return [];
  const accounts = await getAdAccountAssetsByIds(identifiers);
  return accounts.map(toBatchEditRow);
}

async function saveSpreadsheetSubmission(
  submission: AssetBatchEditSubmission,
  deriveInventoryStatus = false,
) {
  const result = await saveAdAccountAssetSpreadsheet(
    submission.rows.map((row) => {
      const stringValue = (key: string) => {
        const value = row.values[key];
        return Array.isArray(value) ? '' : (value ?? '');
      };
      const userValue = row.values.userIds;
      const userIds = Array.isArray(userValue)
        ? userValue
        : userValue
          ? [userValue]
          : [];
      const changedFields = new Set(
        row.changedFields
          .map((key) => batchFieldNames[key])
          .filter((field): field is AdAccountAssetBatchField => Boolean(field)),
      );
      if (deriveInventoryStatus) {
        changedFields.add('INVENTORY_STATUS');
        changedFields.add('USAGE_USER_IDS');
      }
      return {
        accountAttribute: stringValue('accountAttribute'),
        accountId: stringValue('accountId'),
        accountName: stringValue('accountName'),
        accountType: stringValue('accountType'),
        backupManagedBm: stringValue('backupManagedBm'),
        backupManagedBmId: stringValue('backupManagedBmId'),
        cardNumber: stringValue('cardNumber'),
        cardStation: stringValue('cardStation'),
        changedFields: [...changedFields],
        channelId: stringValue('channelId'),
        inventoryStatus: deriveInventoryStatus
          ? userIds.length > 0
            ? ('ASSIGNED' as const)
            : ('AVAILABLE' as const)
          : (stringValue('inventoryStatus') as AdAccountInventoryStatus),
        managedBm: stringValue('managedBm'),
        managedBmId: stringValue('managedBmId'),
        remark: stringValue('remark'),
        timezone: stringValue('timezone'),
        userIds,
      };
    }),
  );
  accountSelectionScope.value = 'manual';
  selectedAccountIds.value = [];
  invalidateAllAccountRowsCache();
  await loadAccounts();
  message.success(
    `已新增 ${result.createdCount} 个广告账户，更新 ${result.updatedCount} 个`,
  );
}

async function submitBatchEdit(submission: AssetBatchEditSubmission) {
  batchEditSubmitting.value = true;
  try {
    await saveSpreadsheetSubmission(submission);
    batchEditOpen.value = false;
  } finally {
    batchEditSubmitting.value = false;
  }
}

async function submitOfficeSpreadsheet(submission: AssetBatchEditSubmission) {
  officeSpreadsheetSubmitting.value = true;
  try {
    await saveSpreadsheetSubmission(submission, true);
    officeSpreadsheetOpen.value = false;
  } finally {
    officeSpreadsheetSubmitting.value = false;
  }
}

function resetImport() {
  importError.value = '';
  selectedImportFile.value = undefined;
  uploadFiles.value = [];
}

function openImport() {
  resetImport();
  importModalOpen.value = true;
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  resetImport();
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (!extension || !['csv', 'xls', 'xlsx'].includes(extension)) {
    importError.value = '仅支持 .xlsx、.xls 或 .csv 文件';
    return Upload.LIST_IGNORE;
  }
  if (file.size > IMPORT_MAX_FILE_SIZE) {
    importError.value = '文件不能超过 5MB';
    return Upload.LIST_IGNORE;
  }

  selectedImportFile.value = file;
  uploadFiles.value = [file];
  return false;
};

async function downloadTemplate() {
  await ensureAccountOptionsReady();
  const XLSX = await import('xlsx');
  const headers = [
    ...AD_ACCOUNT_IMPORT_HEADERS,
    ...AD_ACCOUNT_IMPORT_OPTIONAL_HEADERS,
  ];
  // 模板只提供字段表头，避免示例账户被误当作真实数据一并提交。
  const worksheet = XLSX.utils.aoa_to_sheet([headers]);
  worksheet['!cols'] = headers.map((header) => ({
    wch: Math.max(14, header.length * 2 + 4),
  }));
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, '广告账户');
  XLSX.writeFileXLSX(workbook, '广告账户台账导入模板.xlsx');
}

function showImportFailures(record: Partial<AdAccountAssetImportHistory>) {
  importFailures.value = record.failures ?? [];
  importFailureModalOpen.value = true;
}

async function openImportHistory() {
  importHistoryModalOpen.value = true;
  await loadImportHistory();
}

async function loadImportHistory() {
  importHistoryLoading.value = true;
  try {
    importHistoryRecords.value = await getAdAccountImportHistory();
  } finally {
    importHistoryLoading.value = false;
  }
}

function decodeBase64(content: string) {
  const binary = window.atob(content);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

async function downloadImportFailureFile(recordId: string) {
  const file = await getAdAccountImportFailedFile(recordId);
  const blob = new Blob([decodeBase64(file.contentBase64)], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = file.fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function submitImport() {
  const file = selectedImportFile.value;
  if (!file) {
    message.warning('请先选择要导入的文件');
    return;
  }
  importing.value = true;
  try {
    const result = await importAdAccountAssets(file);
    importFailures.value = result.failures;
    if (result.failures.length > 0) {
      message.warning(
        `成功处理 ${result.successCount} 条，失败 ${result.failures.length} 条`,
      );
      importFailureModalOpen.value = true;
    } else {
      message.success(`已成功新增或更新 ${result.successCount} 条广告账户`);
      importModalOpen.value = false;
    }
    await loadImportHistory();
    invalidateAllAccountRowsCache();
    await loadAccounts(1);
  } finally {
    importing.value = false;
  }
}

onMounted(() => {
  window.addEventListener('pointerup', stopTableSelection);
});
onBeforeUnmount(() => {
  window.removeEventListener('pointerup', stopTableSelection);
});

void loadAccounts();
void ensureAccountOptionsReady();

defineExpose({
  exportAccounts,
  isExporting: exporting,
  openBatchEdit,
  openOfficeSpreadsheet,
  openImport,
  refresh: () => loadAccounts(currentPage.value),
  selectedAccountCount,
});
</script>

<template>
  <Card
    class="ad-account-ledger"
    :class="{ 'ad-account-ledger--neumorphic': neumorphic }"
    :body-style="{ padding: neumorphic ? '14px 16px' : '16px' }"
  >
    <div class="flex flex-col" :class="neumorphic ? 'gap-3' : 'gap-4'">
      <div
        v-if="selectedAccountSummary"
        class="flex flex-wrap items-center gap-2"
      >
        <Tag class="m-0" role="status" aria-live="polite">
          {{ selectedAccountSummary }}
        </Tag>
      </div>
      <div
        aria-label="广告账户列表。可用鼠标拖拽框选单元格，按 Ctrl 或 Command 加 C 复制。"
        :class="{
          'focus-visible:ring-2 focus-visible:ring-offset-2':
            !isPointerTableFocus,
        }"
        class="focus-visible:ring-ring select-none rounded-md outline-none"
        role="region"
        tabindex="0"
        @blur="handleTableBlur"
        @copy="tableSelection.copySelection"
        @keydown="handleTableKeydown"
        @pointercancel="stopTableSelection"
        @pointerdown="beginTableSelection"
        @pointermove="extendTableSelection"
        @pointerup="stopTableSelection"
      >
        <Table
          class="ad-account-asset-table"
          :columns="columns"
          :data-source="accountRows"
          :loading="loading"
          :pagination="{
            current: currentPage,
            pageSize,
            pageSizeOptions: props.pageSizeOptions,
            showSizeChanger: true,
            // Table 默认会把中等尺寸分页降为 small；使用官方默认规格以继续读取全局尺寸令牌。
            size: 'default',
            style: { margin: '12px 0 0' },
            total,
            onChange: changeAccountPage,
          }"
          :row-key="accountRowKey"
          :row-selection="rowSelection"
          :scroll="{
            x: ACCOUNT_TABLE_SCROLL_X,
            y: ASSET_TABLE_BODY_HEIGHT,
          }"
          :style="{
            '--asset-table-body-height': `${ASSET_TABLE_BODY_HEIGHT}px`,
          }"
          table-layout="fixed"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'usageUsers'">
              {{ assetTableDisplayText(record.usageUsers) }}
            </template>
            <template v-else-if="column.key === 'usageDepartment'">
              {{ assetTableDisplayText(record.usageDepartment) }}
            </template>
            <template v-else-if="column.key === 'channelName'">
              {{ assetTableDisplayText(record.channelName) }}
            </template>
            <template v-else-if="column.key === 'accountStatus'">
              <Tag
                v-if="assetTableRawText(record.accountStatus)"
                :color="getPlatformStatusMeta(record.accountStatus).color"
              >
                {{ getPlatformStatusMeta(record.accountStatus).label }}
              </Tag>
              <template v-else>-</template>
            </template>
            <template v-else-if="column.key === 'accountDailyLimit'">
              {{ formatAccountDailyLimit(record.accountDailyLimit) }}
            </template>
            <template v-else-if="column.key === 'inventoryStatus'">
              <Tag
                v-if="assetTableRawText(record.inventoryStatus)"
                :color="getInventoryStatusMeta(record.inventoryStatus).color"
              >
                {{ getInventoryStatusMeta(record.inventoryStatus).label }}
              </Tag>
              <template v-else>-</template>
            </template>
            <template v-else-if="column.key === 'deliveryDate'">
              {{ assetTableDisplayText(record.deliveryDate) }}
            </template>
            <template v-else-if="column.key === 'remark'">
              <OverflowTooltip :text="assetTableDisplayText(record.remark)" />
            </template>
            <template v-else-if="column.key === 'actions'">
              <Button type="link" @click="openLifecycle(record)"
                >生命周期</Button
              >
              <Dropdown trigger="click">
                <Button type="link">更多</Button>
                <template #overlay>
                  <Menu>
                    <MenuItem @click="openEditor(record)">编辑</MenuItem>
                    <MenuItem @click="openDailyLimitHistory(record)">
                      限额记录
                    </MenuItem>
                  </Menu>
                </template>
              </Dropdown>
            </template>
            <template v-else>
              {{ adAccountColumnDisplayText(record, column.key) }}
            </template>
          </template>
          <template #emptyText>
            <Empty description="暂无符合条件的广告账户" />
          </template>
        </Table>
      </div>
    </div>
  </Card>

  <Drawer
    v-model:open="drawerOpen"
    :closable="!saving"
    :mask-closable="!saving"
    title="编辑广告账户"
    width="min(640px, 100vw)"
  >
    <Form layout="vertical">
      <div class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
        <template v-for="field in adAccountEditorFields" :key="field.key">
          <FormItem v-if="field.key === 'accountId'" :label="field.label">
            <Input :value="editingAccountId" disabled />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'accountName'"
            :label="field.label"
          >
            <Input
              v-model:value="form.accountName"
              aria-label="账户名称由Facebook账户数据同步，不允许编辑"
              disabled
            />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'accountDailyLimit'"
            extra="由 Facebook 账户数据同步，不支持修改。"
            :label="field.label"
          >
            <Input
              :value="formatAccountDailyLimit(form.accountDailyLimit)"
              disabled
            />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'accountType'"
            :label="field.label"
          >
            <Select
              v-model:value="form.accountType"
              allow-clear
              :options="accountTypeOptions"
              placeholder="请选择账户类型"
              show-search
            />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'accountAttribute'"
            :label="field.label"
          >
            <Select
              v-model:value="form.accountAttribute"
              allow-clear
              :options="accountAttributeOptions"
              placeholder="请选择账户属性"
              show-search
            />
          </FormItem>
          <FormItem v-else-if="field.key === 'channelId'" :label="field.label">
            <Select
              v-model:value="form.channelId"
              allow-clear
              :options="channelOptions"
              placeholder="请选择所属渠道"
              show-search
              @update:value="syncFormChannelName"
            />
          </FormItem>
          <FormItem v-else-if="field.key === 'managedBm'" :label="field.label">
            <Input v-model:value="form.managedBm" />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'managedBmId'"
            :label="field.label"
          >
            <Input v-model:value="form.managedBmId" />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'backupManagedBm'"
            :label="field.label"
          >
            <Input v-model:value="form.backupManagedBm" />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'backupManagedBmId'"
            :label="field.label"
          >
            <Input v-model:value="form.backupManagedBmId" />
          </FormItem>
          <FormItem v-else-if="field.key === 'timezone'" :label="field.label">
            <Input v-model:value="form.timezone" />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'cardStation'"
            :label="field.label"
          >
            <Input v-model:value="form.cardStation" />
          </FormItem>
          <FormItem v-else-if="field.key === 'cardNumber'" :label="field.label">
            <Input.TextArea v-model:value="form.cardNumber" :rows="3" />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'inventoryStatus'"
            :label="field.label"
          >
            <Select
              v-model:value="inventoryStatus"
              :disabled="saving"
              :options="editableInventoryStatusOptions"
              placeholder="请选择库存状态"
            />
          </FormItem>
          <FormItem
            v-else-if="field.key === 'userIds'"
            :extra="
              canEditUsageUser
                ? undefined
                : '仅库存状态为“已分配”时可编辑使用人。'
            "
            :label="field.label"
          >
            <StableUserSelect
              v-model="editingUsageUserIds"
              :disabled="!canEditUsageUser || saving"
              :legacy-label="editingUsageUserLabel"
              multiple
              placeholder="请选择一位或多位使用人"
            />
          </FormItem>
          <FormItem v-else class="sm:col-span-2" :label="field.label">
            <Input.TextArea
              v-model:value="form.remark"
              :auto-size="{ minRows: 3, maxRows: 6 }"
              :maxlength="500"
              placeholder="请输入备注（非必填）"
              show-count
            />
          </FormItem>
        </template>
      </div>
    </Form>
    <template #footer>
      <div class="flex justify-end gap-2">
        <Button :disabled="saving" @click="drawerOpen = false">取消</Button>
        <Button :loading="saving" type="primary" @click="saveAccount"
          >保存</Button
        >
      </div>
    </template>
  </Drawer>

  <AssetBatchEditModal
    v-model:open="batchEditOpen"
    :fields="batchEditFields"
    identifier-key="accountId"
    :loading="batchEditLoading"
    :resolve-identifiers="resolveBatchEditIdentifiers"
    :rows="batchEditRows"
    :submitting="batchEditSubmitting"
    target-label="账户"
    title="批量修改广告账户"
    @submit="submitBatchEdit"
  />

  <AssetOfficeSpreadsheetModal
    v-if="officeSpreadsheetOpen"
    v-model:open="officeSpreadsheetOpen"
    allow-create
    :fields="officeSpreadsheetFields"
    identifier-key="accountId"
    :loading="officeSpreadsheetLoading"
    :rows="officeSpreadsheetRows"
    status-hint="使用人非空时自动设为已使用；为空时自动设为可分配。异常状态不能通过 Excel 设置。"
    :submitting="officeSpreadsheetSubmitting"
    target-label="广告账户"
    title="Excel 批量处理广告账户"
    @submit="submitOfficeSpreadsheet"
  />

  <AssetLifecycleDrawer
    v-model:open="lifecycleOpen"
    :account-id="lifecycleAccountId"
    :detail="lifecycleDetail"
    :loading="lifecycleLoading"
    @application="openApplicationDetail"
  />

  <AdAccountDailyLimitHistoryModal
    v-model:open="dailyLimitHistoryOpen"
    :account-id="dailyLimitHistoryAccountId"
  />

  <Modal
    v-model:open="importModalOpen"
    :closable="!importing"
    :mask-closable="!importing"
    title="导入新增或更新广告账户"
    width="min(880px, calc(100vw - 32px))"
  >
    <div class="flex flex-col gap-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <Alert
          class="min-w-0 flex-1"
          message="按账户 ID 匹配：不存在时新增，已存在时更新。文件由服务端统一解析和校验；使用人列缺失时保持现状，留空时清空分配。"
          show-icon
          type="info"
        />
        <div class="flex shrink-0 flex-wrap gap-2">
          <Button :disabled="importing" @click="openImportHistory">
            <IconifyIcon aria-hidden="true" icon="lucide:history" />导入记录
          </Button>
          <Button :disabled="importing" @click="downloadTemplate">
            <IconifyIcon aria-hidden="true" icon="lucide:download" />下载模板
          </Button>
        </div>
      </div>
      <Alert v-if="importError" :message="importError" show-icon type="error" />
      <UploadDragger
        v-model:file-list="uploadFiles"
        accept=".xlsx,.xls,.csv"
        :before-upload="beforeUpload"
        :disabled="importing"
        :max-count="1"
        @remove="resetImport"
      >
        <p
          class="ant-upload-drag-icon flex items-center justify-center"
          aria-hidden="true"
        >
          <IconifyIcon
            class="text-primary block text-2xl"
            icon="lucide:file-up"
          />
        </p>
        <p class="text-base font-medium">拖入文件，或点击选择文件</p>
        <p class="mb-0 text-sm text-slate-500">
          支持 .xlsx、.xls、.csv，文件不超过 5MB，单次最多 5000 条
        </p>
      </UploadDragger>
    </div>
    <template #footer>
      <div class="flex justify-end gap-2">
        <Button :disabled="importing" @click="importModalOpen = false"
          >取消</Button
        >
        <Button
          :disabled="!selectedImportFile"
          :loading="importing"
          type="primary"
          @click="submitImport"
        >
          开始导入
        </Button>
      </div>
    </template>
  </Modal>

  <Modal
    v-model:open="importFailureModalOpen"
    footer=""
    title="导入失败详情"
    width="min(620px, calc(100vw - 32px))"
  >
    <Table
      class="asset-dialog-fixed-table"
      :columns="importFailureColumns"
      :data-source="importFailures"
      :pagination="false"
      :row-key="(record) => `${record.line}-${record.message}`"
      size="small"
      :scroll="{ y: ASSET_MODAL_TABLE_BODY_HEIGHT }"
      :style="{
        '--asset-dialog-table-height': `${ASSET_MODAL_TABLE_BODY_HEIGHT}px`,
      }"
    />
  </Modal>

  <Modal
    v-model:open="importHistoryModalOpen"
    footer=""
    title="导入记录"
    width="min(900px, calc(100vw - 32px))"
  >
    <Table
      class="asset-dialog-fixed-table"
      :columns="importHistoryColumns"
      :data-source="importHistoryRecords"
      :loading="importHistoryLoading"
      :pagination="false"
      :row-key="(record) => record.id"
      size="small"
      :scroll="{ x: 760, y: ASSET_MODAL_TABLE_BODY_HEIGHT }"
      :style="{
        '--asset-dialog-table-height': `${ASSET_MODAL_TABLE_BODY_HEIGHT}px`,
      }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'failureCount'">
          {{ record.failures.length }}
        </template>
        <template v-else-if="column.key === 'actions'">
          <div
            v-if="record.failures.length > 0"
            class="flex items-center gap-1"
          >
            <Button
              type="link"
              @click="showImportFailures(record)"
            >
              查看原因
            </Button>
            <Button
              type="link"
              @click="downloadImportFailureFile(record.id)"
            >
              下载失败文件
            </Button>
          </div>
          <span v-else class="text-slate-400">无失败记录</span>
        </template>
      </template>
    </Table>
    <Alert
      v-if="!importHistoryLoading && importHistoryRecords.length === 0"
      class="mt-4"
      message="暂无导入记录"
      show-icon
      type="info"
    />
  </Modal>
</template>

<style scoped>
/* Ant Table 的 scroll.y 负责固定表头，这里补足固定高度，避免末页数据较少时表格收缩。 */
.ad-account-asset-table :deep(.ant-table-body) {
  min-height: var(--asset-table-body-height);
}

/* 账户 ID 与时区是完整标识，不能因窄列被拆分成多行。 */
:deep(.ad-account-asset-table__identity-cell) {
  overflow-wrap: normal !important;
  white-space: nowrap !important;
}

/* Ant 的自定义全选菜单使用绝对定位，需显式建立同一中心线，避免箭头高于复选框。 */

/* 与其他资产列表保持一致的行悬停反馈。 */
:deep(
  .ad-account-asset-table
    .ant-table-selection-extra
    .ant-dropdown-trigger
) {
  display: inline-flex;
  align-items: center;
  height: 20px;
}

:deep(.ad-account-asset-table .ant-table-tbody > tr:hover > td) {
  background: var(--adpulse-table-row-hover);
}

/* 选区使用全局语义色，并覆盖 Ant 表格的整行悬停背景，保证拖拽过程中边界始终可辨。 */
:deep(.ad-account-asset-table .ant-table-tbody > tr > td.table-range-selected),
:deep(
  .ad-account-asset-table .ant-table-tbody > tr:hover > td.table-range-selected
) {
  color: hsl(var(--accent-foreground));
  background: hsl(var(--accent)) !important;
}
</style>
