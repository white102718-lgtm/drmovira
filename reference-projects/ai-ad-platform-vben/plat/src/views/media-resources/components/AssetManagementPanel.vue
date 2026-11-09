<script lang="ts" setup>
import type { RadioChangeEvent } from 'ant-design-vue';
import type { AssetExportColumn } from './asset-export';
import type {
  AssetFilterControl,
  AssetFilterField,
  AssetFilterValues,
} from './asset-filter';

import type {
  MediaAsset,
  MediaAssetBatchField,
  MediaAssetSavePayload,
  MediaAssetType,
  SystemDepartmentApi,
} from '#/api';
import type { EffectiveAppIdItem } from '#/api/management/platform-config';
import type { TableCopyColumn } from '#/views/components/useTableRangeSelection';

import {
  computed,
  defineAsyncComponent,
  onActivated,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';
import { getPopupContainer } from '@vben/utils';

import { useDebounceFn, useStorage } from '@vueuse/core';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  ConfigProvider,
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
  Pagination,
  Radio,
  RadioButton,
  RadioGroup,
  Select,
  Tag,
} from 'ant-design-vue';

import {
  assetFlowApi,
  assetReturnApi,
  getAdAccountAssetPage,
  getMyAdAccountAssets,
  isFusionDemoMode,
} from '#/api';
import {
  createJsonRouteQueryField,
  createPositiveIntegerRouteQueryField,
  createRouteQueryField,
  createStringRouteQueryField,
  readRouteQueryPositiveInteger,
  readRouteQueryText,
  useRouteListQuery,
} from '#/composables/use-route-list-query';
import {
  getAdvertisingLogin,
  getEffectiveAppIds,
} from '#/api/management/platform-config';
import {
  canDemoAction,
  filterDemoAdAccounts,
  getCurrentDemoActor,
} from '#/mock/demo-access';
import { projectService } from '#/domain/project';
import { useTableRangeSelection } from '#/views/components/useTableRangeSelection';

import ListLoading from '../../components/ListLoading.vue';
import { getSharedDepartmentTree } from '../../components/organization-options-cache';
import StableUserSelect from '../../components/StableUserSelect.vue';
import {
  findInventoryAssetTypeByAssetType,
  findInventoryAssetTypeBySubtype,
  getInventoryAssetEditorFieldKeys,
  getInventoryAssetPresentationKeys,
  getInventoryAssetTemplateFields,
  INVENTORY_ASSET_TYPES,
  type InventoryAssetEditorFieldKey,
  type InventoryAssetField,
  type InventoryAssetPresentationKey,
} from './asset-types';
import AssetImportModal from './AssetImportModal.vue';
import AdAccountAssetTable from './AdAccountAssetTable.vue';
import AssetDetailFormField from './AssetDetailFormField.vue';
import AssetFilterPanel from './AssetFilterPanel.vue';
import AssetLifecycleDrawer from './AssetLifecycleDrawer.vue';
import SensitiveAssetValue from './SensitiveAssetValue.vue';
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
import { loadAdAccountLifecycleDetail } from './ad-account-lifecycle';
import { ASSET_TABLE_VIEWPORT_HEIGHT } from './asset-table-layout';
import {
  ensureAdAccountOptions,
  ensureAssetChannelOptions,
  refreshAdAccountOptions,
  refreshAssetChannelOptions,
  useAssetOptionCache,
} from './asset-option-cache';
import {
  filterMyAdAccountAssets,
  mapMyAdAccountAssets,
  paginateMyAdAccountAssets,
  type MyAdAccountAssetRecord,
} from './my-ad-account-assets';
import {
  assetAccountApplicationActions,
  createAssetAccountApplicationRoute,
  type AssetAccountApplicationAction,
} from '../../workbench/asset-account-application-actions';

type AssetCategory = 'advertising' | 'network' | 'other' | 'personal';

// Univer 体积较大，仅在用户打开 Excel 批量处理弹窗时加载。
const AssetOfficeSpreadsheetModal = defineAsyncComponent(
  () => import('./AssetOfficeSpreadsheetModal.vue'),
);
type AssetStatus = 'allocated' | 'available' | 'exception' | 'return_pending';
type AssetTableAction =
  | 'account-application'
  | 'application'
  | 'delete'
  | 'edit'
  | 'return';

const ASSET_PAGE_SIZE = 10;
const DEFAULT_ASSET_PAGE_SIZE_OPTIONS = ['10', '20', '50', '100'];
const MANAGEMENT_ASSET_PAGE_SIZE_OPTIONS = [
  ...DEFAULT_ASSET_PAGE_SIZE_OPTIONS,
  '1000',
];

interface AssetCategoryMeta {
  description: string;
  icon: string;
  label: string;
}

interface AssetRecord {
  accountAttribute?: string;
  accountType?: string;
  applicationId?: string;
  assigneeId?: string;
  assigneeIds?: string[];
  birthday?: string;
  category: AssetCategory;
  channelId?: string;
  channelName?: string;
  createdAt: string;
  details?: Record<string, string>;
  emailLoginUrl?: string;
  gender?: string;
  id: string;
  identifier: string;
  inventoryAssigneeName?: string;
  inventoryStatus?: string;
  managedBm?: string;
  managedBmId?: string;
  name: string;
  note?: string;
  owner: string;
  password?: string;
  projectId?: string;
  projectName?: string;
  status: AssetStatus;
  subtype: string;
  teamId?: string;
  twoFactorKey?: string;
  usageDepartment?: string;
  usageTeamId?: string;
  usageUsers?: string;
  usageTeam?: string;
}

interface AssetInformationColumn {
  field?: InventoryAssetField;
  key: string;
  kind: 'detail' | 'projectName' | 'remark' | 'usageTeam';
  label: string;
  sensitive: boolean;
}

interface DepartmentOption {
  label: string;
  name: string;
  value: string;
}

const adAccountAssetTableRef = ref<InstanceType<typeof AdAccountAssetTable>>();

const subtypeOptionsByLegacyCategory: Record<
  AssetCategory,
  Array<{ label: string; value: string }>
> = {
  personal: [
    { label: 'Facebook Page', value: 'facebook_page' },
    { label: 'TG号', value: 'telegram' },
    { label: '兼容个号 · TikTok', value: 'tiktok' },
    { label: '兼容个号 · Google', value: 'google' },
    { label: '兼容个号 · Kwai', value: 'kwai' },
  ],
  advertising: [
    { label: '像素', value: 'pixel' },
    { label: 'App', value: 'app' },
    { label: 'SDK', value: 'sdk' },
    { label: 'BM', value: 'bm' },
  ],
  network: [
    { label: '手机', value: 'mobile' },
    { label: '电脑', value: 'computer' },
    { label: '兼容网络设备', value: 'static_ip' },
  ],
  other: [{ label: '其他', value: 'other' }],
};

const categoryMeta: Record<AssetCategory, AssetCategoryMeta> = {
  personal: {
    description: 'TG号、微信号等社交账号与凭证',
    icon: 'lucide:messages-square',
    label: '社交资产',
  },
  advertising: {
    description: '个号、广告户、像素、BM、绑包与主页等投放资源',
    icon: 'lucide:badge-dollar-sign',
    label: '广告资产',
  },
  network: {
    description: '电脑、手机、邮箱与静态 IP 等办公资源',
    icon: 'lucide:laptop',
    label: '办公资产',
  },
  other: {
    description: '暂未归入标准分类的其他资产',
    icon: 'lucide:package-search',
    label: '其他资产',
  },
};
const primaryCategoryKeys: AssetCategory[] = [
  'advertising',
  'personal',
  'network',
];
const assetCategoryOptions = primaryCategoryKeys.map((value) => ({
  label: categoryMeta[value].label,
  value,
}));

const statusMeta: Record<AssetStatus, { color: string; label: string }> = {
  available: { color: 'success', label: '可分配' },
  allocated: { color: 'processing', label: '已使用' },
  exception: { color: 'error', label: '异常' },
  return_pending: { color: 'warning', label: '待回收' },
};

const assetTypeOptions = INVENTORY_ASSET_TYPES.map((item) => ({
  category: item.category,
  label: item.label,
  value: item.subtype,
}));
// 广告账户由 MongoDB 台账维护，不再作为 media_asset 库存新增或导入。
const creatableAssetTypeOptions = assetTypeOptions.filter(
  (item) => item.value !== 'ad_account',
);

const ASSET_SUBTYPE_DETAIL_KEY = 'inventorySubtype';

const seedAssets: AssetRecord[] = [
  {
    category: 'advertising',
    createdAt: '2026-08-10 16:42',
    id: 'PA-001',
    identifier: 'mp018@rrr.com',
    name: 'Facebook SEA 个号 018',
    owner: '',
    status: 'available',
    subtype: 'fb',
  },
  {
    assigneeId: 'user-1',
    category: 'personal',
    createdAt: '2026-08-10 17:20',
    id: 'PA-002',
    identifier: 'tt_70988101',
    name: 'TikTok 日本个号 01',
    owner: '赵宁',
    projectId: 'project-pixel',
    status: 'allocated',
    subtype: 'tiktok',
    teamId: 'team-delivery-a',
  },
  {
    assigneeId: 'user-1',
    category: 'personal',
    createdAt: '2026-08-09 11:08',
    id: 'PA-003',
    identifier: 'gads-user-042',
    name: 'Google 海外个号 042',
    owner: '海外增长一部',
    status: 'allocated',
    subtype: 'google',
  },
  {
    category: 'personal',
    createdAt: '2026-08-08 09:31',
    id: 'PA-004',
    identifier: 'kwai_br_008',
    name: 'Kwai 巴西个号 008',
    owner: '',
    status: 'available',
    subtype: 'kwai',
  },
  {
    category: 'personal',
    createdAt: '2026-08-07 14:15',
    id: 'PA-005',
    identifier: '@mpower_ops_3',
    name: 'Telegram 运营号 03',
    owner: '媒介二组',
    status: 'allocated',
    subtype: 'telegram',
  },
  {
    category: 'advertising',
    createdAt: '2026-08-10 18:05',
    id: 'AD-001',
    identifier: 'px_12024801001',
    name: 'Starfall Purchase 像素',
    owner: 'Starfall 全球增长',
    projectId: 'project-starfall',
    status: 'allocated',
    subtype: 'pixel',
    teamId: 'team-delivery-a',
  },
  {
    category: 'advertising',
    createdAt: '2026-08-10 10:30',
    id: 'AD-002',
    identifier: 'bm_9824100281',
    name: 'Meta SEA 主 BM',
    owner: '媒介一组',
    status: 'allocated',
    subtype: 'bm',
  },
  {
    category: 'network',
    createdAt: '2026-08-11 08:20',
    id: 'NET-001',
    identifier: '103.28.***.18',
    name: '日本东京静态 IP 18',
    owner: 'TikTok 日本投放组',
    status: 'allocated',
    subtype: 'static_ip',
  },
  {
    category: 'network',
    createdAt: '2026-08-09 13:10',
    id: 'NET-002',
    identifier: '45.77.***.62',
    name: '美国西部静态 IP 62',
    owner: '',
    status: 'exception',
    subtype: 'static_ip',
  },
];

const assets = useStorage<AssetRecord[]>(
  'fusion:asset-management:v1',
  seedAssets,
);
const remoteAssets = ref<AssetRecord[]>([]);
const myAdAccountRecords = ref<MyAdAccountAssetRecord[]>([]);
const remoteAssetTotal = ref(0);
const remoteLoading = ref(false);
const remoteError = ref('');
const exportingAssets = ref(false);
const batchEditOpen = ref(false);
const batchEditSubmitting = ref(false);
const officeSpreadsheetOpen = ref(false);
const officeSpreadsheetSubmitting = ref(false);
const selectedAssetIds = ref<string[]>([]);
const batchEditRows = ref<AssetSpreadsheetSourceRow[]>([]);
const batchEditLoading = ref(false);
const officeSpreadsheetRows = ref<AssetSpreadsheetSourceRow[]>([]);
const officeSpreadsheetLoading = ref(false);
const currentAssetPage = ref(1);
const assetPageSize = ref(ASSET_PAGE_SIZE);
const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const activeCategory = ref<AssetCategory>('advertising');
const {
  accountAttributeOptions: adAccountAttributeFilterOptions,
  accountTypeOptions: adAccountTypeFilterOptions,
  channelLoading,
  channelOptions,
} = useAssetOptionCache();
const projectOptions = ref<Array<{ label: string; value: string }>>([]);
const departmentOptions = ref<DepartmentOption[]>([]);
const departmentOptionsLoading = ref(false);
const authorizationModalOpen = ref(false);
const authorizationAppsLoading = ref(false);
const authorizationSubmitting = ref(false);
const authorizationApps = ref<EffectiveAppIdItem[]>([]);
const selectedAuthorizationAppId = ref('');
const keyword = ref('');
const subtypeFilter = ref<string | undefined>('ad_account');
const assetFilterValues = ref<AssetFilterValues>({});
const advancedFiltersOpen = ref(false);
const drawerOpen = ref(false);
const savingAsset = ref(false);
const returnOpen = ref(false);
const lifecycleOpen = ref(false);
const lifecycleLoading = ref(false);
const lifecycleAccountId = ref<string>();
const lifecycleAssetSubtype = ref<string>();
const lifecycleDetail =
  ref<Awaited<ReturnType<typeof assetFlowApi.lifecycle>>>();
let lifecycleRequestVersion = 0;
const returnSubmitting = ref(false);
const returnReason = ref('');
const returnTarget = ref<AssetRecord>();
const assetImportModalRef = ref<InstanceType<typeof AssetImportModal>>();
let latestRemoteAssetRequestId = 0;
const reloadRemoteAssetsForFilters = useDebounceFn(
  () => void loadRemoteAssets(1),
  300,
);
const editingId = ref('');

function isAssetFilterValues(value: unknown): value is AssetFilterValues {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  return Object.values(value).every(
    (item) =>
      typeof item === 'string' ||
      (Array.isArray(item) && item.every((entry) => typeof entry === 'string')),
  );
}

const { isApplyingRoute } = useRouteListQuery({
  fields: {
    assetFilters: createJsonRouteQueryField(assetFilterValues, {
      defaultValue: {},
      isDefault: (value) => Object.keys(value).length === 0,
      validate: isAssetFilterValues,
    }),
    category: createStringRouteQueryField(activeCategory, {
      allowedValues: ['advertising', 'network', 'other', 'personal'],
      defaultValue: 'advertising',
    }),
    assetType: createRouteQueryField(subtypeFilter, {
      defaultValue: 'ad_account',
      parse: (value, defaultValue) => {
        const subtype = readRouteQueryText(value);
        return assetTypeOptions.some(
          (item) =>
            item.value === subtype && item.category === activeCategory.value,
        )
          ? subtype
          : (assetTypeOptions.find(
              (item) => item.category === activeCategory.value,
            )?.value ?? defaultValue);
      },
      serialize: (value) =>
        value ===
        assetTypeOptions.find((item) => item.category === activeCategory.value)
          ?.value
          ? undefined
          : value,
    }),
    page: createPositiveIntegerRouteQueryField(currentAssetPage, {
      defaultValue: 1,
    }),
    pageSize: createRouteQueryField(assetPageSize, {
      defaultValue: ASSET_PAGE_SIZE,
      parse: (value, defaultValue) =>
        readRouteQueryPositiveInteger(
          value,
          defaultValue,
          (route.path.includes('/my-assets')
            ? DEFAULT_ASSET_PAGE_SIZE_OPTIONS
            : MANAGEMENT_ASSET_PAGE_SIZE_OPTIONS
          ).map(Number),
        ),
      serialize: (value, defaultValue) =>
        value === defaultValue ? undefined : String(value),
    }),
    q: createStringRouteQueryField(keyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
  },
  onRouteApplied: () => {
    if (isAdAccountView.value) {
      void adAccountAssetTableRef.value?.refresh();
      return;
    }
    void loadRemoteAssets(currentAssetPage.value);
  },
  route,
  router,
});
const assetFormCategory = ref<AssetCategory>('advertising');
const formErrors = reactive<Record<string, string>>({});
const form = reactive({
  assigneeId: '',
  assigneeIds: [] as string[],
  birthday: '',
  channelId: undefined as string | undefined,
  channelName: '',
  createdAt: '',
  details: {} as Record<string, string>,
  emailLoginUrl: '',
  gender: '',
  identifier: '',
  name: '',
  note: '',
  owner: '',
  password: '',
  projectId: '',
  projectName: '',
  status: 'available' as AssetStatus,
  subtype: 'fb',
  twoFactorKey: '',
  usageTeam: '',
  usageTeamId: '',
});

/** 资产接口可能返回 ISO 时间，列表与详情统一使用本地可读的日期时间分隔符。 */
function assetCreatedAtValue(value: string) {
  return value.trim().replace('T', ' ');
}

function formatAssetCreatedAt(value: string) {
  return assetCreatedAtValue(value) || '-';
}

/** 合并不同服务返回的使用人名单，保留首次出现顺序并消除重复人员。 */
function mergeUsageUserNames(...values: Array<string | undefined>) {
  return [
    ...new Set(
      values
        .flatMap((value) => value?.split(/[、,，;；]/) ?? [])
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  ].join('、');
}

const isMyAssets = computed(() => route.path.includes('/my-assets'));
const assetPageSizeOptions = computed(() =>
  isMyAssets.value
    ? DEFAULT_ASSET_PAGE_SIZE_OPTIONS
    : MANAGEMENT_ASSET_PAGE_SIZE_OPTIONS,
);
const isMyAdAccountView = computed(
  () =>
    isMyAssets.value &&
    activeCategory.value === 'advertising' &&
    subtypeFilter.value === 'ad_account',
);
const statusFilterOptions = computed(() =>
  Object.entries(statusMeta)
    .filter(([value]) => !isMyAssets.value || value !== 'available')
    .map(([value, item]) => ({
      label: item.label,
      value,
    })),
);
const selectableAssetTypes = computed(() =>
  editingId.value ? assetTypeOptions : creatableAssetTypeOptions,
);
const formAssetTypeOptions = computed(() =>
  selectableAssetTypes.value.filter(
    (item) => item.category === assetFormCategory.value,
  ),
);
const isAdAccountView = computed(
  () =>
    !isMyAssets.value &&
    activeCategory.value === 'advertising' &&
    subtypeFilter.value === 'ad_account',
);
const isPixelListing = computed(() => subtypeFilter.value === 'pixel');
const currentSubtypeOptions = computed(() => {
  const standardOptions = assetTypeOptions
    .filter((item) => item.category === activeCategory.value)
    .map(({ label, value }) => ({ label, value }));
  if (!isFusionDemoMode()) return standardOptions;

  const standardValues = new Set(standardOptions.map((item) => item.value));
  return [
    ...standardOptions,
    ...subtypeOptionsByLegacyCategory[activeCategory.value].filter(
      (item) => !standardValues.has(item.value),
    ),
  ];
});

const currentAssetDetailFields = computed(() => {
  if (!subtypeFilter.value) return [];

  const assetType = findInventoryAssetTypeBySubtype(subtypeFilter.value);
  if (!assetType) return [];

  return assetType.fields;
});
function buildAssetInformationColumns(
  assetType: (typeof INVENTORY_ASSET_TYPES)[number],
  keys: readonly InventoryAssetPresentationKey[] = getInventoryAssetPresentationKeys(
    assetType,
  ),
) {
  const fieldsByKey = new Map(
    assetType.fields.map((field) => [field.key, field]),
  );

  return keys
    .map((key): AssetInformationColumn | undefined => {
      if (key.startsWith('detail.')) {
        const field = fieldsByKey.get(key.slice('detail.'.length));
        return field
          ? {
              field,
              key,
              kind: 'detail',
              label: field.label,
              sensitive: field.type === 'password',
            }
          : undefined;
      }
      if (key === 'projectName') {
        return {
          key,
          kind: key,
          label: '所属项目',
          sensitive: false,
        };
      }
      if (key === 'usageTeam') {
        return {
          key,
          kind: key,
          label: '使用团队',
          sensitive: false,
        };
      }
      return {
        key,
        kind: 'remark',
        label: '备注',
        sensitive: false,
      };
    })
    .filter((column): column is AssetInformationColumn => Boolean(column));
}

const currentAssetInformationColumns = computed<AssetInformationColumn[]>(
  () => {
    if (!subtypeFilter.value) return [];

    const assetType = findInventoryAssetTypeBySubtype(subtypeFilter.value);
    return assetType ? buildAssetInformationColumns(assetType) : [];
  },
);
const demoActor = computed(() =>
  isFusionDemoMode() ? getCurrentDemoActor() : undefined,
);
const canManageAssets = computed(
  () =>
    !isMyAssets.value &&
    (!isFusionDemoMode() || canDemoAction(demoActor.value, 'resource.manage')),
);
// 资产新增统一由资源管理承担，避免“我的资产”成为第二个库存录入入口。
const canCreateAssets = computed(() => canManageAssets.value);

function assetTableActions(asset: AssetRecord): AssetTableAction[] {
  const actions: AssetTableAction[] = [];
  const editable = canManageAssets.value && asset.status !== 'return_pending';
  const returnable = canManageAssets.value && asset.status === 'allocated';
  const deletable = editable && asset.subtype !== 'ad_account';

  if (canApplyAccountOperation(asset)) actions.push('account-application');
  if (editable) actions.push('edit');
  if (asset.applicationId) actions.push('application');
  if (returnable) actions.push('return');
  if (deletable) actions.push('delete');
  return actions;
}

function primaryAssetTableAction(asset: AssetRecord) {
  return assetTableActions(asset)[0];
}

function hasAdditionalAssetTableActions(asset: AssetRecord) {
  return assetTableActions(asset).length > 1;
}

function canApplyAccountOperation(asset: AssetRecord) {
  return isMyAssets.value && asset.subtype === 'ad_account';
}

/** 从本人资产进入的申请始终带上当前账户，申请页会据此限制可选账户范围。 */
function openAccountApplication(
  asset: AssetRecord,
  action: AssetAccountApplicationAction,
) {
  void router.push(
    createAssetAccountApplicationRoute(
      { account: asset.identifier, name: asset.name },
      action,
    ),
  );
}

const visibleAssets = computed(() =>
  isFusionDemoMode()
    ? filterDemoAdAccounts(demoActor.value, assets.value)
    : remoteAssets.value,
);
const selectedChannel = computed(() =>
  channelOptions.value.find((option) => option.value === form.channelId),
);
const currentAssetType = computed(() =>
  findInventoryAssetTypeBySubtype(form.subtype),
);
const currentAssetCategoryLabel = computed(
  () => categoryMeta[assetFormCategory.value]?.label ?? assetFormCategory.value,
);
const currentAssetTypeLabel = computed(
  () => currentAssetType.value?.label ?? form.subtype,
);
const isPixelAsset = computed(() => form.subtype === 'pixel');
const currentAssetFields = computed(() => {
  const assetType = currentAssetType.value;
  if (!assetType) return [];
  const fieldsByKey = new Map(
    assetType.fields.map((field) => [`detail.${field.key}`, field]),
  );
  return getInventoryAssetEditorFieldKeys(assetType)
    .filter((key) => key.startsWith('detail.'))
    .map((key) => fieldsByKey.get(key))
    .filter((field): field is InventoryAssetField => Boolean(field));
});
const currentAssetFormInformationColumns = computed(() =>
  currentAssetType.value
    ? buildAssetInformationColumns(
        currentAssetType.value,
        currentAssetType.value.assetType === 'PIXEL'
          ? (getInventoryAssetEditorFieldKeys(currentAssetType.value).map(
              (key) => (key === 'project' ? 'projectName' : key),
            ) as InventoryAssetPresentationKey[])
          : getInventoryAssetPresentationKeys(currentAssetType.value),
      )
    : [],
);

function toBatchDetailField(
  assetType: (typeof INVENTORY_ASSET_TYPES)[number],
  field: InventoryAssetField,
): AssetBatchEditField {
  return {
    aliases: field.excelHeader ? [field.excelHeader] : undefined,
    editable: field.key !== assetType.identifierKey,
    key: `detail.${field.key}`,
    label: field.label,
    options: field.options ? [...field.options] : undefined,
    placeholder: field.placeholder,
    required: field.required,
    sensitive: field.type === 'password',
    type:
      field.type === 'date' ||
      field.type === 'password' ||
      field.type === 'select'
        ? field.type
        : 'text',
  };
}

const batchEditFields = computed<AssetBatchEditField[]>(() => {
  const assetType = findInventoryAssetTypeBySubtype(subtypeFilter.value ?? '');
  if (!assetType) return [];

  const fieldsByKey = new Map(
    assetType.fields.map((field) => [`detail.${field.key}`, field]),
  );
  const toEditorField = (
    key: InventoryAssetEditorFieldKey,
  ): AssetBatchEditField | undefined => {
    if (key.startsWith('detail.')) {
      const field = fieldsByKey.get(key);
      return field ? toBatchDetailField(assetType, field) : undefined;
    }
    if (key === 'channel') {
      return {
        key,
        label: '渠道名称',
        options: channelOptions.value,
        required: true,
        type: 'select',
      };
    }
    if (key === 'project') {
      return {
        key,
        label: '所属项目',
        options: projectOptions.value,
        type: 'select',
      };
    }
    if (key === 'usageTeam') {
      return {
        helpText: '选择所属项目时必须选择使用团队。',
        key,
        label: '使用团队',
        options: departmentOptions.value,
        requiredWhen: {
          fieldKey: 'project',
          hint: '选择所属项目时必填',
          incompatibleMessage: '选择使用团队前必须先选择所属项目',
          values: projectOptions.value.map((option) => option.value),
        },
        type: 'select',
      };
    }
    if (key === 'inventoryStatus') {
      return {
        key,
        label: '库存状态',
        options: [
          { label: '可分配', value: 'AVAILABLE' },
          { label: '已使用', value: 'ASSIGNED' },
          { label: '异常', value: 'DISABLED' },
        ],
        required: true,
        type: 'select',
      };
    }
    if (key === 'usageUsers') {
      return {
        helpText: '库存状态为“已使用”时必须选择使用人。',
        key,
        label: '使用人',
        requiredWhen: {
          fieldKey: 'inventoryStatus',
          hint: '库存状态为“已使用”时必填',
          incompatibleMessage: '选择使用人时，库存状态必须为“已使用”',
          values: ['ASSIGNED'],
        },
        type: 'user',
      };
    }
    return { key: 'remark', label: '备注', type: 'textarea' };
  };

  return getInventoryAssetEditorFieldKeys(assetType)
    .map(toEditorField)
    .filter((field): field is AssetBatchEditField => Boolean(field));
});
const officeSpreadsheetFields = computed<AssetBatchEditField[]>(() =>
  batchEditFields.value
    .filter((field) => field.key !== 'inventoryStatus')
    .map((field) => {
      if (field.key === 'usageUsers') {
        return {
          ...field,
          helpText: '填写使用人自动设为已使用；留空自动设为可分配。',
          requiredWhen: undefined,
        };
      }
      if (field.key === 'usageTeam') {
        return {
          ...field,
          helpText: '所属项目和使用团队必须同时填写或同时留空。',
        };
      }
      return field;
    }),
);
const currentAssetRequiresChannel = computed(
  () => currentAssetType.value?.requiresChannel ?? true,
);
const showsChannelContext = computed(
  () =>
    findInventoryAssetTypeBySubtype(subtypeFilter.value ?? '')
      ?.requiresChannel ?? false,
);
const currentAssetFilterFields = computed<AssetFilterField[]>(() => {
  if (isAdAccountView.value || isMyAdAccountView.value) {
    return AD_ACCOUNT_ASSET_FILTER_FIELDS.map((field) => {
      if (field.key === 'accountType') {
        return {
          ...field,
          options: adAccountTypeFilterOptions.value,
        };
      }
      if (field.key === 'accountAttribute') {
        return {
          ...field,
          options: adAccountAttributeFilterOptions.value,
        };
      }
      if (field.key === 'channelName') {
        return {
          ...field,
          options: channelOptions.value.map((option) => ({
            label: option.label,
            value: option.label,
          })),
        };
      }
      return field;
    });
  }

  // 密码、Cookie 与令牌等凭据不得作为列表筛选条件，避免密码管理器将筛选区识别为登录表单。
  const detailFields: AssetFilterField[] = currentAssetDetailFields.value
    .filter((field) => field.type !== 'password')
    .map((field) => ({
      control:
        field.type === 'date' || field.type === 'select' ? field.type : 'text',
      key: `details.${field.key}`,
      label: field.label,
      options: field.options,
      placeholder: field.placeholder,
    }));
  const commonFields: AssetFilterField[] = [
    { key: 'id', label: '资产记录 ID' },
    ...(isPixelListing.value
      ? []
      : [{ control: 'user' as const, key: 'owner', label: '使用人' }]),
    { control: 'department', key: 'usageDepartment', label: '使用团队' },
    { control: 'date', key: 'createdAt', label: '入库日期' },
    {
      control: 'select',
      key: 'status',
      label: '库存状态',
      options: statusFilterOptions.value,
    },
    { key: 'note', label: '备注' },
  ];

  if (showsChannelContext.value) {
    commonFields.splice(
      3,
      0,
      { key: 'channelId', label: '渠道 ID' },
      {
        control: 'select',
        key: 'channelName',
        label: '渠道名称',
        options: channelOptions.value.map((option) => ({
          label: option.label,
          value: option.label,
        })),
      },
      { key: 'projectId', label: '项目 ID' },
      { key: 'projectName', label: '项目名称' },
    );
  } else if (isPixelListing.value) {
    commonFields.splice(3, 0, { key: 'projectName', label: '所属项目' });
  }

  return [...detailFields, ...commonFields];
});
const currentAssetFilterFieldsByKey = computed(
  () =>
    new Map(currentAssetFilterFields.value.map((field) => [field.key, field])),
);
const subtypeLabel = (value: string) =>
  assetTypeOptions.find((item) => item.value === value)?.label ??
  Object.values(subtypeOptionsByLegacyCategory)
    .flat()
    .find((item) => item.value === value)?.label ??
  value;

function assetDetailDisplayValue(
  asset: AssetRecord,
  field: InventoryAssetField,
) {
  const value = assetDetailValue(asset, field);

  if (!value) return '-';

  return (
    field.options?.find((option) => option.value === value)?.label ?? value
  );
}

function assetDetailValue(asset: AssetRecord, field: InventoryAssetField) {
  // 已持久化的空字符串表示用户主动清空；只有旧数据完全缺少字段时才使用兼容回退值。
  const details = asset.details ?? {};
  if (Object.hasOwn(details, field.key)) {
    return details[field.key]?.trim() ?? '';
  }

  const assetType = findInventoryAssetTypeBySubtype(asset.subtype);
  return field.key === assetType?.identifierKey
    ? asset.identifier
    : field.key === assetType?.nameKey
      ? asset.name
      : '';
}

function assetInformationValue(
  asset: AssetRecord,
  column: AssetInformationColumn,
) {
  if (column.kind === 'detail' && column.field) {
    return assetDetailDisplayValue(asset, column.field);
  }
  if (column.kind === 'projectName') {
    return asset.projectName || '-';
  }
  if (column.kind === 'usageTeam') return asset.usageTeam || '-';
  return asset.note || '-';
}

function assetInformationExportValue(
  asset: AssetRecord,
  column: AssetInformationColumn,
) {
  if (column.kind === 'detail' && column.field) {
    const value = assetDetailValue(asset, column.field);
    if (!value) return '';
    return (
      column.field.options?.find((option) => option.value === value)?.label ??
      value
    );
  }
  if (column.kind === 'projectName') return asset.projectName || '';
  if (column.kind === 'usageTeam') return asset.usageTeam || '';
  return asset.note || '';
}

function assetInformationCopyValue(
  asset: AssetRecord,
  column: AssetInformationColumn,
) {
  const value = assetInformationExportValue(asset, column);
  return column.sensitive && value ? '••••••••' : value;
}

function assetExportTextValue(asset: object, key: string) {
  const value = Reflect.get(asset, key);
  return typeof value === 'string' ? value : '';
}

function assetCategory(asset: AssetRecord) {
  return (
    findInventoryAssetTypeBySubtype(asset.subtype)?.category ?? asset.category
  );
}

function assetFilterValue(asset: AssetRecord, key: string) {
  if (key.startsWith('details.')) {
    const detailKey = key.slice('details.'.length);
    const field = currentAssetDetailFields.value.find(
      (item) => item.key === detailKey,
    );
    if (!field) return asset.details?.[detailKey];

    return assetDetailValue(asset, field);
  }

  return Reflect.get(asset, key);
}

/** 高级筛选按当前资产类型的字段定义匹配，隐藏字段不会残留并影响其他类型。 */
function matchesCurrentAssetFilters(asset: AssetRecord) {
  return Object.entries(assetFilterValues.value).every(([key, expected]) => {
    const field = currentAssetFilterFieldsByKey.value.get(key);
    if (!field) return true;
    return matchesAssetFilterValue(
      assetFilterValue(asset, key),
      expected,
      field.control,
    );
  });
}

function resetAssetFilters() {
  assetFilterValues.value = {};
}

/**
 * 切换资产分类、类型或菜单范围时，搜索条件不能跨范围沿用。
 */
function resetAssetSearchCriteria() {
  keyword.value = '';
  resetAssetFilters();
}

function clearFormError(key: string) {
  delete formErrors[key];
}

function clearDetailFormError(field: InventoryAssetField) {
  clearFormError(`details.${field.key}`);
}

/**
 * 渠道归属以渠道管理的稳定 ID 保存，名称只作为展示快照和旧读模型兼容字段。
 */
function syncSelectedChannel() {
  if (channelOptions.value.length === 0) return;

  const channel =
    channelOptions.value.find((option) => option.value === form.channelId) ??
    channelOptions.value.find((option) => option.label === form.channelName);
  form.channelId = channel?.value;
  form.channelName = channel?.label ?? '';
}

function handleChannelChange(value: unknown) {
  const channelId = typeof value === 'string' ? value : undefined;
  form.channelId = channelId;
  form.channelName =
    channelOptions.value.find((option) => option.value === channelId)?.label ??
    '';
  clearFormError('channelName');
}

function handleAssetStatusChange(value: unknown) {
  const status = Object.hasOwn(statusMeta, String(value))
    ? (String(value) as AssetStatus)
    : 'available';
  form.status = status;
  if (status !== 'allocated') {
    delete formErrors.assigneeId;
    form.assigneeId = '';
    form.assigneeIds = [];
    form.owner = '';
  }
}

function handleAssigneeChange(
  value: string | string[] | undefined,
  user?: { label: string },
) {
  const assigneeId = Array.isArray(value) ? value[0] : value;
  delete formErrors.assigneeId;
  form.assigneeId = assigneeId ?? '';
  form.owner = user?.label ?? '';
}

function createEmptyAssetDetails(subtype: string) {
  const assetType = findInventoryAssetTypeBySubtype(subtype);
  return Object.fromEntries(
    (assetType?.fields ?? []).map((field) => [field.key, '']),
  );
}

function parseAssetDetails(secretData?: string) {
  if (!secretData) return {};
  try {
    const value: unknown = JSON.parse(secretData);
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        item === undefined || item === null ? '' : String(item),
      ]),
    );
  } catch {
    return {};
  }
}

function serializeAssetDetails(
  subtype: string,
  details: Record<string, string>,
) {
  const normalizedDetails = { ...details };
  // 像素项目归属使用资产顶层 projectId/projectName，禁止继续回写旧扩展字段。
  if (subtype === 'pixel') delete normalizedDetails.projectName;

  // 微信号与 Facebook 账号暂时共用后端 PERSONAL 枚举，需持久化前端子类型用于回显。
  return JSON.stringify({
    ...normalizedDetails,
    [ASSET_SUBTYPE_DETAIL_KEY]: subtype,
  });
}

function handleAssetTypeChange(value: unknown) {
  delete formErrors.assetType;
  for (const key of Object.keys(formErrors)) {
    if (key.startsWith('details.')) delete formErrors[key];
  }
  const subtype = value ? String(value) : '';
  form.subtype = subtype;
  form.assigneeIds = [];
  form.details = createEmptyAssetDetails(subtype);
  const assetType = findInventoryAssetTypeBySubtype(subtype);
  if (assetType) assetFormCategory.value = assetType.category;
  if (!assetType?.requiresChannel) {
    delete formErrors.channelName;
    form.channelId = undefined;
    form.channelName = '';
  }
  if (subtype === 'pixel') {
    void Promise.all([loadProjectOptions(), loadDepartmentOptions()]);
  } else {
    delete formErrors.projectId;
    form.projectId = '';
    form.projectName = '';
    form.usageTeam = '';
    form.usageTeamId = '';
  }
}

function handleAssetCategoryChange(value: unknown) {
  const category = primaryCategoryKeys.includes(value as AssetCategory)
    ? (value as AssetCategory)
    : 'personal';
  assetFormCategory.value = category;
  handleAssetTypeChange(formAssetTypeOptions.value[0]?.value);
}

function resolveAssetIdentity() {
  const assetType = currentAssetType.value;
  if (!assetType) return { identifier: '', name: '' };
  const configuredIdentifier =
    form.details[assetType.identifierKey]?.trim() ?? '';
  const configuredName = form.details[assetType.nameKey]?.trim() ?? '';
  // 主页 ID 可选；为空时以必填的主页名称维持库存唯一标识。
  const identifier =
    configuredIdentifier ||
    (assetType.subtype === 'page' ? configuredName : '');
  return { identifier, name: configuredName || identifier };
}

function assetSubtype(assetType: MediaAssetType) {
  return (
    findInventoryAssetTypeByAssetType(assetType)?.subtype ??
    assetType.toLowerCase()
  );
}

function resolveRemoteAssetSubtype(
  assetType: MediaAssetType,
  details: Record<string, string>,
) {
  const persistedSubtype = details[ASSET_SUBTYPE_DETAIL_KEY];
  const persistedType = persistedSubtype
    ? findInventoryAssetTypeBySubtype(persistedSubtype)
    : undefined;
  return persistedType?.assetType === assetType
    ? persistedType.subtype
    : assetSubtype(assetType);
}

function assetStatus(status: string): AssetStatus {
  if (status === 'ASSIGNED') return 'allocated';
  if (status === 'AVAILABLE') return 'available';
  if (status === 'RETURN_PENDING') return 'return_pending';
  return 'exception';
}

function backendAssetStatus(
  status: AssetStatus,
): MediaAssetSavePayload['status'] {
  if (status === 'allocated') return 'ASSIGNED';
  if (status === 'exception') return 'DISABLED';
  return 'AVAILABLE';
}

function backendAssetType(subtype: string): MediaAssetType {
  return findInventoryAssetTypeBySubtype(subtype)?.assetType ?? 'PERSONAL';
}

const filteredAssets = computed(() => {
  if (!isFusionDemoMode()) return visibleAssets.value;

  return visibleAssets.value.filter(
    (asset) =>
      assetCategory(asset) === activeCategory.value &&
      (!subtypeFilter.value ||
        subtypeFilter.value === 'all' ||
        asset.subtype === subtypeFilter.value) &&
      matchesAssetKeyword(
        [
          asset,
          categoryMeta[assetCategory(asset)]?.label,
          subtypeLabel(asset.subtype),
          statusMeta[asset.status].label,
          ...currentAssetInformationColumns.value
            .filter((column) => !column.sensitive)
            .map((column) => assetInformationValue(asset, column)),
        ],
        keyword.value,
      ) &&
      matchesCurrentAssetFilters(asset),
  );
});
const paginatedAssets = computed(() => {
  if (!isFusionDemoMode()) return filteredAssets.value;

  const start = (currentAssetPage.value - 1) * assetPageSize.value;
  return filteredAssets.value.slice(start, start + assetPageSize.value);
});
const tableCopyColumns = computed<TableCopyColumn<AssetRecord>[]>(() => {
  const informationColumns = currentAssetInformationColumns.value.map(
    (column) => ({
      getText: (asset: AssetRecord) => assetInformationCopyValue(asset, column),
      key: column.key,
    }),
  );

  return [
    ...informationColumns,
    ...(showsChannelContext.value
      ? [
          {
            getText: (asset: AssetRecord) => asset.channelName || '',
            key: 'channelName',
          },
        ]
      : []),
    ...(!isPixelListing.value
      ? [{ getText: (asset: AssetRecord) => asset.owner, key: 'owner' }]
      : []),
    {
      getText: (asset: AssetRecord) => formatAssetCreatedAt(asset.createdAt),
      key: 'createdAt',
    },
    {
      getText: (asset: AssetRecord) => statusMeta[asset.status].label,
      key: 'status',
    },
  ];
});
const tableSelection = useTableRangeSelection({
  columns: tableCopyColumns,
  rows: paginatedAssets,
});

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

function beginTableSelection(
  event: PointerEvent,
  rowIndex: number,
  columnIndex: number,
) {
  if (event.button !== 0) return;

  const table = (event.currentTarget as HTMLElement).closest('table');
  table?.focus({ preventScroll: true });
  tableSelection.beginSelection(rowIndex, columnIndex);
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

function tableColumnIndex(column: string) {
  return tableCopyColumns.value.findIndex(({ key }) => key === column);
}
const assetPaginationTotal = computed(() =>
  isFusionDemoMode() ? filteredAssets.value.length : remoteAssetTotal.value,
);
const selectedAssetIdSet = computed(() => new Set(selectedAssetIds.value));
const areAllFilteredAssetsSelected = computed(
  () =>
    filteredAssets.value.length > 0 &&
    filteredAssets.value.every((asset) =>
      selectedAssetIdSet.value.has(asset.id),
    ),
);
const hasAssetTableActions = computed(() =>
  filteredAssets.value.some((asset) => assetTableActions(asset).length > 0),
);

function toggleAssetSelection(assetId: string) {
  selectedAssetIds.value = selectedAssetIdSet.value.has(assetId)
    ? selectedAssetIds.value.filter((id) => id !== assetId)
    : [...selectedAssetIds.value, assetId];
}

function toggleAllFilteredAssets() {
  selectedAssetIds.value = areAllFilteredAssetsSelected.value
    ? []
    : filteredAssets.value.map((asset) => asset.id);
}

function changeAssetPage(page: number, nextPageSize: number) {
  const nextPage = nextPageSize === assetPageSize.value ? page : 1;
  assetPageSize.value = nextPageSize;
  currentAssetPage.value = nextPage;
  if (isMyAdAccountView.value) {
    applyMyAdAccountPage(nextPage);
    return;
  }
  if (isAdAccountView.value) return;
  if (!isFusionDemoMode()) void loadRemoteAssets(nextPage);
}

watch(
  [activeCategory, subtypeFilter, keyword, assetFilterValues],
  () => {
    if (isApplyingRoute.value) return;
    currentAssetPage.value = 1;
    if (isFusionDemoMode()) return;
    if (isMyAdAccountView.value) {
      applyMyAdAccountPage(1);
      return;
    }
    if (!isAdAccountView.value) reloadRemoteAssetsForFilters();
  },
  { deep: true },
);
watch(paginatedAssets, () => tableSelection.clearSelection());

watch(
  filteredAssets,
  (currentAssets) => {
    if (!isFusionDemoMode()) return;

    const lastPage = Math.max(
      1,
      Math.ceil(currentAssets.length / assetPageSize.value),
    );
    if (currentAssetPage.value > lastPage) {
      currentAssetPage.value = lastPage;
    }

    const currentAssetIds = new Set(currentAssets.map((asset) => asset.id));
    const retainedIds = selectedAssetIds.value.filter((id) =>
      currentAssetIds.has(id),
    );
    if (retainedIds.length !== selectedAssetIds.value.length) {
      selectedAssetIds.value = retainedIds;
    }
  },
  { flush: 'sync' },
);

/** 无勾选时由服务端一次返回全部筛选结果，避免逐页重复查询和解密。 */
async function loadAllRemoteAssetsForExport() {
  if (isMyAdAccountView.value) return filterCurrentMyAdAccountAssets();

  const records = await assetFlowApi.searchAllAssets(buildAssetSearchFilters());
  return mapRemoteAssets(records);
}

/** 从完整选择集合读取导出数据，确保跨页勾选不会只命中当前页。 */
async function loadSelectedAssetsForExport() {
  const selectedIds = new Set(selectedAssetIds.value);
  if (isFusionDemoMode()) {
    return filteredAssets.value.filter((asset) => selectedIds.has(asset.id));
  }
  if (isMyAdAccountView.value) {
    return filterCurrentMyAdAccountAssets().filter((asset) =>
      selectedIds.has(asset.id),
    );
  }

  const records: MediaAsset[] = [];
  for (const batch of chunkAssetExportIds(selectedAssetIds.value)) {
    records.push(...(await assetFlowApi.batchQueryAssets(batch)));
  }
  return mapRemoteAssets(records);
}

function currentFilterControls() {
  return Object.fromEntries(
    currentAssetFilterFields.value.map((field) => [field.key, field.control]),
  );
}

function filterCurrentMyAdAccountAssets() {
  return filterMyAdAccountAssets(
    myAdAccountRecords.value,
    keyword.value,
    assetFilterValues.value,
    currentFilterControls(),
  );
}

/** “我的广告户”已一次性加载，搜索与翻页仅重算当前页，避免重复请求相同数据。 */
function applyMyAdAccountPage(page = currentAssetPage.value) {
  const filteredRecords = filterCurrentMyAdAccountAssets();
  const lastPage = Math.max(
    1,
    Math.ceil(filteredRecords.length / assetPageSize.value),
  );
  const resolvedPage = Math.min(page, lastPage);
  remoteAssets.value = paginateMyAdAccountAssets(
    filteredRecords,
    resolvedPage,
    assetPageSize.value,
  );
  currentAssetPage.value = resolvedPage;
  remoteAssetTotal.value = filteredRecords.length;
}

/** 有勾选时仅导出所选资产，否则导出当前筛选结果中的全部资产。 */
async function exportAssets() {
  exportingAssets.value = true;
  try {
    const assetsToExport =
      selectedAssetIds.value.length > 0
        ? await loadSelectedAssetsForExport()
        : isFusionDemoMode()
          ? filteredAssets.value
          : await loadAllRemoteAssetsForExport();
    if (assetsToExport.length === 0) {
      message.warning('暂无可导出的资产数据');
      return;
    }

    const assetType = findInventoryAssetTypeBySubtype(
      subtypeFilter.value ?? '',
    );
    if (!assetType) {
      message.error('当前资产类型不支持导出');
      return;
    }
    await Promise.all([
      assetType.requiresChannel
        ? ensureAssetChannelOptions()
        : Promise.resolve(),
      assetType.assetType === 'PIXEL'
        ? loadProjectOptions()
        : Promise.resolve(),
      assetType.assetType === 'PIXEL'
        ? loadDepartmentOptions()
        : Promise.resolve(),
    ]);
    const templateFields = getInventoryAssetTemplateFields(assetType);
    const informationColumns: AssetExportColumn[] = assetType.presentationKeys
      ? buildAssetInformationColumns(assetType).map((column) => ({
          key: column.key,
          label: column.field?.excelHeader ?? column.label,
          selectOptions:
            column.kind === 'projectName'
              ? projectOptions.value.map((option) => option.label)
              : column.kind === 'usageTeam'
                ? departmentOptions.value.map((option) => option.label)
                : column.field?.options?.map((option) => option.label),
          ...(column.kind === 'remark' ? { width: 24 } : {}),
        }))
      : templateFields.map((field) => ({
          key: `detail.${field.key}`,
          label: field.excelHeader ?? field.label,
          selectOptions: field.options?.map((option) => option.label),
        }));
    const contextColumns: AssetExportColumn[] = [
      ...(!assetType.presentationKeys && assetType.requiresChannel
        ? [
            {
              key: 'channelName',
              label: '渠道名称',
              selectOptions: channelOptions.value.map((option) => option.label),
              width: 20,
            },
          ]
        : []),
      ...(!assetType.presentationKeys
        ? (assetType.importContextHeaders ?? []).map((header) => ({
            key: header === '所属项目' ? 'projectName' : 'usageTeam',
            label: header,
            selectOptions:
              header === '所属项目'
                ? projectOptions.value.map((option) => option.label)
                : departmentOptions.value.map((option) => option.label),
          }))
        : []),
      ...(assetType.usageUserHeader
        ? [{ key: 'owner', label: assetType.usageUserHeader, width: 16 }]
        : []),
      ...(!assetType.presentationKeys
        ? [{ key: 'remark', label: '备注', width: 24 }]
        : []),
    ];
    const columns: AssetExportColumn[] = [
      ...informationColumns,
      ...contextColumns,
      ...(!isPixelListing.value && !assetType.usageUserHeader
        ? [{ key: 'owner', label: '使用人', width: 16 }]
        : []),
      { key: 'createdAt', label: '入库时间', width: 20 },
      { key: 'status', label: '库存状态', width: 14 },
    ];
    const rows = assetsToExport.map((asset) => ({
      ...Object.fromEntries(
        templateFields.map((field) => {
          const column: AssetInformationColumn = {
            field,
            key: `detail.${field.key}`,
            kind: 'detail',
            label: field.label,
            sensitive: field.type === 'password',
          };
          return [column.key, assetInformationExportValue(asset, column)];
        }),
      ),
      channelName: asset.channelName || '',
      createdAt: assetCreatedAtValue(asset.createdAt),
      owner: asset.owner || '',
      projectName: assetExportTextValue(asset, 'projectName'),
      remark: assetExportTextValue(asset, 'note'),
      status: statusMeta[asset.status].label,
      usageTeam: assetExportTextValue(asset, 'usageTeam'),
    }));
    const sheetName = assetType.excelSheetName ?? assetType.label;
    await downloadAssetWorkbook(
      `资产管理_${sheetName}_${formatAssetExportTimestamp()}.xlsx`,
      sheetName,
      columns,
      rows,
    );
    message.success(`已导出 ${rows.length} 条资产数据`);
  } finally {
    exportingAssets.value = false;
  }
}

async function openBatchEdit() {
  if (!canManageAssets.value) {
    message.warning('当前角色没有资产管理权限');
    return;
  }
  batchEditRows.value = [];
  batchEditOpen.value = true;
  batchEditLoading.value = true;
  try {
    if (isPixelListing.value) {
      await Promise.all([loadProjectOptions(), loadDepartmentOptions()]);
    }
    const records =
      isFusionDemoMode() || selectedAssetIds.value.length === 0
        ? []
        : await assetFlowApi.batchQueryAssets([...selectedAssetIds.value]);
    batchEditRows.value = records.map(toBatchEditRow);
  } finally {
    batchEditLoading.value = false;
  }
}

// 批量修改入口暂时隐藏，保留处理函数供恢复入口时直接复用。
void openBatchEdit;

async function openOfficeSpreadsheet() {
  if (!canManageAssets.value) {
    message.warning('当前角色没有资产管理权限');
    return;
  }
  officeSpreadsheetRows.value = [];
  officeSpreadsheetOpen.value = true;
  officeSpreadsheetLoading.value = true;
  try {
    if (isPixelListing.value) {
      await Promise.all([loadProjectOptions(), loadDepartmentOptions()]);
    }
    const records =
      isFusionDemoMode() || selectedAssetIds.value.length === 0
        ? []
        : await assetFlowApi.batchQueryAssets([...selectedAssetIds.value]);
    officeSpreadsheetRows.value = records.map(toBatchEditRow);
  } finally {
    officeSpreadsheetLoading.value = false;
  }
}

function toBatchEditRow(record: MediaAsset): AssetSpreadsheetSourceRow {
  const assetType = findInventoryAssetTypeBySubtype(subtypeFilter.value ?? '');
  const details = parseAssetDetails(record.secretData);
  const usageTeamId =
    departmentOptions.value.find((option) => option.name === record.usageTeam)
      ?.value ?? '';
  return {
    id: record.id,
    values: {
      channel: record.channelId ?? '',
      inventoryStatus: record.status,
      project: record.projectId ?? '',
      remark: record.remark ?? '',
      usageTeam: usageTeamId,
      usageUsers:
        record.assetType === 'PIXEL'
          ? (record.usageUserIds ?? '').split(',').filter(Boolean)
          : (record.assigneeId ?? ''),
      ...Object.fromEntries(
        (assetType?.fields ?? []).map((field) => [
          `detail.${field.key}`,
          details[field.key] ?? '',
        ]),
      ),
    },
  };
}

async function resolveBatchEditIdentifiers(identifiers: string[]) {
  const assetType = findInventoryAssetTypeBySubtype(subtypeFilter.value ?? '');
  if (!assetType || identifiers.length === 0) return [];
  const records = await assetFlowApi.batchQueryAssetsByIdentifiers(
    assetType.assetType,
    identifiers,
  );
  return records.map(toBatchEditRow);
}

async function saveSpreadsheetSubmission(
  submission: AssetBatchEditSubmission,
  deriveInventoryStatus = false,
) {
  const meta = findInventoryAssetTypeBySubtype(subtypeFilter.value ?? '')!;
  const stringValue = (
    row: AssetBatchEditSubmission['rows'][number],
    key: string,
  ) => {
    const value = row.values[key];
    return Array.isArray(value) ? '' : (value ?? '');
  };
  const result = await assetFlowApi.saveAssetSpreadsheet({
    rows: submission.rows.map((row) => {
      const changed = new Set(row.changedFields);
      const details = Object.fromEntries(
        meta.fields.map((field) => [
          field.key,
          stringValue(row, `detail.${field.key}`),
        ]),
      );
      const detailUpdates = Object.fromEntries(
        row.changedFields
          .filter((key) => key.startsWith('detail.'))
          .map((key) => [key.slice(7), stringValue(row, key)]),
      );
      const commonFields = new Set<MediaAssetBatchField>();
      if (changed.has('channel')) commonFields.add('CHANNEL');
      if (changed.has('inventoryStatus')) {
        commonFields.add('INVENTORY_STATUS');
      }
      if (changed.has('project')) commonFields.add('PROJECT');
      if (changed.has('usageTeam')) commonFields.add('USAGE_TEAM');
      if (changed.has('usageUsers')) commonFields.add('USAGE_USERS');
      if (changed.has('remark')) commonFields.add('REMARK');
      const channelId = stringValue(row, 'channel');
      const projectId = stringValue(row, 'project');
      const usageTeamId = stringValue(row, 'usageTeam');
      const usageUsers = row.values.usageUsers;
      const assigneeIds = Array.isArray(usageUsers)
        ? usageUsers
        : usageUsers
          ? [usageUsers]
          : [];
      if (deriveInventoryStatus) {
        if (meta.assetType === 'PIXEL') {
          commonFields.add('PROJECT');
          commonFields.add('USAGE_TEAM');
        } else {
          commonFields.add('INVENTORY_STATUS');
          commonFields.add('USAGE_USERS');
        }
      }
      const identifier = details[meta.identifierKey] ?? '';
      return {
        assetId: row.id,
        assigneeIds,
        changedFields: [...commonFields],
        detailUpdates,
        usageTeamId: usageTeamId || undefined,
        values: {
          assetCode: identifier,
          assetName: details[meta.nameKey]?.trim() || identifier,
          assetType: meta.assetType,
          assigneeId: assigneeIds.length === 1 ? assigneeIds[0] : undefined,
          assigneeIds: assigneeIds.length > 1 ? assigneeIds : undefined,
          channelId: channelId || undefined,
          channelName: channelOptions.value.find(
            (option) => option.value === channelId,
          )?.label,
          projectId: projectId || undefined,
          projectName: projectOptions.value.find(
            (option) => option.value === projectId,
          )?.label,
          remark: stringValue(row, 'remark'),
          secretData: serializeAssetDetails(meta.subtype, details),
          status:
            deriveInventoryStatus && meta.assetType === 'PIXEL'
              ? projectId
                ? 'ASSIGNED'
                : 'AVAILABLE'
              : deriveInventoryStatus
                ? assigneeIds.length > 0
                  ? 'ASSIGNED'
                  : 'AVAILABLE'
                : (stringValue(row, 'inventoryStatus') as
                    | 'ASSIGNED'
                    | 'AVAILABLE'
                    | 'DISABLED'),
          usageTeamId: usageTeamId || undefined,
        },
      };
    }),
    subtype: meta.subtype,
  });
  await loadRemoteAssets();
  selectedAssetIds.value = [];
  message.success(
    `已新增 ${result.createdCount} 行，更新 ${result.updatedCount} 行`,
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

function switchCategory(category: AssetCategory) {
  activeCategory.value = category;
  // 分类页默认定位到第一个可用的具体资产类型，避免展示“全部”聚合视图。
  subtypeFilter.value = currentSubtypeOptions.value[0]?.value;
  selectedAssetIds.value = [];
  resetAssetSearchCriteria();
}

function switchAssetSubtype(subtype: string) {
  subtypeFilter.value = subtype;
  selectedAssetIds.value = [];
  resetAssetSearchCriteria();
}

function handleAssetCategoryRadioChange(event: RadioChangeEvent) {
  const category = primaryCategoryKeys.find(
    (value) => value === event.target.value,
  );
  if (category) switchCategory(category);
}

function handleAssetSubtypeChange(event: RadioChangeEvent) {
  switchAssetSubtype(String(event.target.value));
}

async function openAuthorization() {
  selectedAuthorizationAppId.value = '';
  authorizationApps.value = [];
  authorizationModalOpen.value = true;
  authorizationAppsLoading.value = true;
  try {
    const apps = await getEffectiveAppIds();
    authorizationApps.value = Object.entries(apps).map(([name, app]) => ({
      ...app,
      name,
    }));
  } catch {
    authorizationApps.value = [];
  } finally {
    authorizationAppsLoading.value = false;
  }
}

function closeAuthorization() {
  if (authorizationSubmitting.value) return;
  authorizationModalOpen.value = false;
  selectedAuthorizationAppId.value = '';
}

async function confirmAuthorization() {
  const selectedApp = authorizationApps.value.find(
    (app) => app.app_id === selectedAuthorizationAppId.value,
  );
  if (!selectedApp) {
    message.warning('请选择授权应用');
    return;
  }

  authorizationSubmitting.value = true;
  try {
    const authorizationUrl = await getAdvertisingLogin(
      selectedApp.app_id,
      selectedApp.config_id,
    );
    if (!authorizationUrl) {
      message.error('未获取到 Facebook 授权地址');
      return;
    }
    authorizationModalOpen.value = false;
    window.location.assign(authorizationUrl);
  } finally {
    authorizationSubmitting.value = false;
  }
}

const menuAssetScopes: Readonly<
  Record<string, { category: AssetCategory; subtype: string }>
> = {
  '/media-assets/my-assets': {
    category: 'advertising',
    subtype: 'ad_account',
  },
  '/media-assets/my-assets/overview': {
    category: 'advertising',
    subtype: 'ad_account',
  },
  '/media-assets/conversion/app': { category: 'advertising', subtype: 'app' },
  '/media-assets/conversion/pixel': {
    category: 'advertising',
    subtype: 'pixel',
  },
  '/media-assets/conversion/sdk': { category: 'advertising', subtype: 'sdk' },
  '/media-assets/devices/computer': {
    category: 'network',
    subtype: 'computer',
  },
  '/media-assets/devices/mobile': { category: 'network', subtype: 'mobile' },
  '/media-assets/other': { category: 'other', subtype: 'other' },
  '/media-assets/social/facebook-page': {
    category: 'advertising',
    subtype: 'page',
  },
  '/media-assets/social/tg': { category: 'personal', subtype: 'telegram' },
};

function applyMenuAssetScope(path: string) {
  const scope = menuAssetScopes[path];
  if (!scope) return;

  activeCategory.value = scope.category;
  subtypeFilter.value = scope.subtype;
  resetAssetSearchCriteria();
}

/** 资产关联申请单时，统一进入既有的申请详情页。 */
function openApplicationDetail(applicationId: string) {
  void router.push({
    path: `/workbench/approvals/${encodeURIComponent(applicationId)}`,
  });
}

/**
 * 广告账户库存只记录已分配关系，名称以广告账户台账为准。这样账户被更名后，
 * “我的资产”不会继续显示开户时写入的占位名称（例如“广告账户 123”）。
 */
async function resolveAdAccountDetails(
  records: {
    assetCode: string;
    assetType: MediaAssetType;
  }[],
) {
  const accountIds = [
    ...new Set(
      records
        .filter((record) => record.assetType === 'AD_ACCOUNT')
        .map((record) => record.assetCode.trim())
        .filter(Boolean),
    ),
  ];
  const details = new Map<
    string,
    { accountName: string; usageUserName?: string }
  >();

  await Promise.all(
    accountIds.map(async (accountId) => {
      try {
        const page = await getAdAccountAssetPage({
          keyword: accountId,
          page: 1,
          pageSize: 10,
        });
        const account = page.items.find((item) => item.accountId === accountId);
        if (account) {
          details.set(accountId, {
            accountName: account.accountName.trim(),
            usageUserName: account.usageUserName,
          });
        }
      } catch {
        // 台账暂不可用时保留资产流水的历史名称，避免影响“我的资产”主列表。
      }
    }),
  );

  return details;
}

function serverFilterControl(control?: AssetFilterControl) {
  return control === 'date' || control === 'select' ? control : 'text';
}

function buildAssetSearchFilters() {
  const assetType = subtypeFilter.value
    ? findInventoryAssetTypeBySubtype(subtypeFilter.value)?.assetType
    : undefined;
  const filterControls: Record<string, 'date' | 'select' | 'text'> =
    Object.fromEntries(
      currentAssetFilterFields.value.map((field) => [
        field.key,
        serverFilterControl(field.control),
      ]),
    );
  const filterValues = Object.fromEntries(
    Object.entries(assetFilterValues.value)
      .map(([key, value]) => {
        const field = currentAssetFilterFieldsByKey.value.get(key);
        return [
          key,
          normalizeAssetFilterValues(value, field?.control),
        ] as const;
      })
      .filter(([, values]) => values.length > 0),
  );

  return {
    assetType,
    filterControls,
    filterValues,
    keyword: keyword.value.trim() || undefined,
    mine: isMyAssets.value,
    subtype: subtypeFilter.value === 'all' ? undefined : subtypeFilter.value,
  };
}

function buildAssetSearchParams(page: number) {
  return {
    ...buildAssetSearchFilters(),
    page,
    pageSize: assetPageSize.value,
  };
}

async function mapRemoteAssets(records: MediaAsset[]) {
  const adAccountDetails = isMyAssets.value
    ? await resolveAdAccountDetails(records)
    : new Map<string, { accountName: string; usageUserName?: string }>();

  return records.map((record) => {
    const details = parseAssetDetails(record.secretData);
    const subtype = resolveRemoteAssetSubtype(record.assetType, details);
    const adAccount = adAccountDetails.get(record.assetCode.trim());
    return {
      applicationId: record.applicationId
        ? String(record.applicationId).trim()
        : undefined,
      assigneeId: record.assigneeId,
      assigneeIds:
        record.assetType === 'PIXEL'
          ? (record.usageUserIds ?? '')
              .split(',')
              .map((userId) => userId.trim())
              .filter(Boolean)
          : undefined,
      birthday: details.birthday,
      category:
        findInventoryAssetTypeBySubtype(subtype)?.category ?? 'advertising',
      channelId: record.channelId || record.projectId,
      channelName: record.channelName || record.projectName,
      createdAt: record.createdAt,
      details,
      emailLoginUrl: details.emailLoginUrl,
      gender: details.gender,
      id: record.id,
      identifier: record.assetCode,
      name: adAccount?.accountName || record.assetName,
      note: record.remark,
      owner:
        record.assetType === 'PIXEL'
          ? ''
          : mergeUsageUserNames(
              record.usageUserNames,
              record.applicantNames,
              adAccount?.usageUserName,
              record.assigneeName,
            ) ||
            [record.assigneeName, record.assigneeDepartmentName]
              .filter((value): value is string => Boolean(value?.trim()))
              .join(' · '),
      password: details.password ? '已配置' : '',
      projectId: record.projectId,
      projectName: record.projectName,
      status: assetStatus(record.status),
      subtype,
      twoFactorKey: details.twoFa ? '已配置' : '',
      usageDepartment:
        record.usageTeam ||
        record.usageDepartmentNames ||
        record.assigneeDepartmentName,
      usageTeam: record.usageTeam,
    };
  });
}

async function loadProjectOptions() {
  if (projectOptions.value.length > 0) return;
  const projects = await projectService.listOptions();
  projectOptions.value = projects.map((project) => ({
    label: project.name,
    value: project.id,
  }));
}

function flattenDepartmentOptions(
  departments: readonly SystemDepartmentApi.Department[],
  parentName = '',
): DepartmentOption[] {
  return departments.flatMap((department) => {
    const label = parentName
      ? `${parentName} / ${department.deptName}`
      : department.deptName;
    return [
      ...(department.status === 1
        ? [{ label, name: department.deptName, value: department.id }]
        : []),
      ...flattenDepartmentOptions(department.children ?? [], label),
    ];
  });
}

function syncPixelUsageTeamId() {
  form.usageTeamId =
    departmentOptions.value.find((option) => option.name === form.usageTeam)
      ?.value ?? '';
}

async function loadDepartmentOptions() {
  if (departmentOptions.value.length > 0 || departmentOptionsLoading.value) {
    return;
  }
  departmentOptionsLoading.value = true;
  try {
    departmentOptions.value = flattenDepartmentOptions(
      await getSharedDepartmentTree(),
    );
    syncPixelUsageTeamId();
  } finally {
    departmentOptionsLoading.value = false;
  }
}

async function loadRemoteAssets(page = currentAssetPage.value) {
  if (isFusionDemoMode()) return;
  const requestId = ++latestRemoteAssetRequestId;
  remoteLoading.value = true;
  remoteError.value = '';
  try {
    if (isMyAdAccountView.value) {
      const accountRecords = mapMyAdAccountAssets(
        await getMyAdAccountAssets(),
        userStore.userInfo?.userId ?? '',
      );
      if (requestId !== latestRemoteAssetRequestId) return;

      myAdAccountRecords.value = accountRecords;
      applyMyAdAccountPage(page);
      return;
    }
    const result = await assetFlowApi.searchAssets(
      buildAssetSearchParams(page),
    );
    const records = await mapRemoteAssets(result.items);
    if (requestId !== latestRemoteAssetRequestId) return;

    remoteAssets.value = records;
    currentAssetPage.value = result.page;
    remoteAssetTotal.value = result.total;
  } catch (error) {
    if (requestId !== latestRemoteAssetRequestId) return;
    remoteError.value =
      error instanceof Error ? error.message : '媒介资产加载失败';
  } finally {
    if (requestId === latestRemoteAssetRequestId) remoteLoading.value = false;
  }
}

/** URL 恢复完成后只加载当前资产类型实际需要的字典。 */
async function ensureCurrentAssetOptions() {
  if (isAdAccountView.value || isMyAdAccountView.value) {
    await ensureAdAccountOptions();
    syncSelectedChannel();
    return;
  }
  if (!currentAssetType.value?.requiresChannel) return;

  await ensureAssetChannelOptions();
  syncSelectedChannel();
}

/** KeepAlive 返回页面时仅刷新当前资产类型依赖的字典。 */
async function refreshCurrentAssetOptions() {
  if (isAdAccountView.value || isMyAdAccountView.value) {
    await refreshAdAccountOptions();
    syncSelectedChannel();
    return;
  }
  if (!currentAssetType.value?.requiresChannel) return;

  await refreshAssetChannelOptions();
  syncSelectedChannel();
}

onMounted(() => {
  window.addEventListener('pointerup', stopTableSelection);
});
onBeforeUnmount(() => {
  window.removeEventListener('pointerup', stopTableSelection);
});
// 页面启用 KeepAlive 时定向刷新当前类型所需字典，避免维护页新增选项后仍显示旧快照。
let hasActivatedAssetPage = false;
onActivated(() => {
  if (!hasActivatedAssetPage) {
    hasActivatedAssetPage = true;
    return;
  }
  void refreshCurrentAssetOptions();
  if (isAdAccountView.value) {
    void adAccountAssetTableRef.value?.refresh();
    return;
  }
  void loadRemoteAssets(currentAssetPage.value);
});

watch(
  () => route.path,
  (path, previousPath) => {
    const hasUrlScope = route.query.category || route.query.assetType;
    if (previousPath || !hasUrlScope) applyMenuAssetScope(path);
    // 广告账户由 AdAccountAssetTable 单独分页加载，避免筛选时额外请求未展示的通用资产列表。
    if (!isAdAccountView.value) void loadRemoteAssets();
  },
  { immediate: true },
);

watch(
  [() => route.path, () => subtypeFilter.value],
  () => void ensureCurrentAssetOptions(),
  { immediate: true },
);

function openCreate() {
  if (!canCreateAssets.value) {
    message.warning('当前角色没有资产录入权限');
    return;
  }
  editingId.value = '';
  const defaultAssetCategory = primaryCategoryKeys.includes(
    activeCategory.value,
  )
    ? activeCategory.value
    : 'personal';
  assetFormCategory.value = defaultAssetCategory;
  const scopedAssetType = selectableAssetTypes.value.find(
    (item) =>
      item.category === defaultAssetCategory &&
      item.value === subtypeFilter.value,
  );
  const defaultAssetType =
    scopedAssetType ??
    selectableAssetTypes.value.find(
      (item) => item.category === defaultAssetCategory,
    );
  for (const key of Object.keys(formErrors)) delete formErrors[key];
  Object.assign(form, {
    assigneeId: '',
    assigneeIds: [],
    birthday: '',
    channelId: undefined,
    channelName: '',
    createdAt: '',
    details: createEmptyAssetDetails(defaultAssetType?.value ?? 'fb'),
    emailLoginUrl: '',
    gender: '',
    identifier: '',
    name: '',
    note: '',
    owner: '',
    password: '',
    projectId: '',
    projectName: '',
    status: 'available',
    subtype: defaultAssetType?.value ?? 'fb',
    twoFactorKey: '',
    usageTeam: '',
    usageTeamId: '',
  });
  if (form.subtype === 'pixel') {
    void Promise.all([loadProjectOptions(), loadDepartmentOptions()]);
  }
  drawerOpen.value = true;
}

async function openAssetImport() {
  if (!canCreateAssets.value) {
    message.warning('当前角色没有资产录入权限');
    return;
  }
  if (isAdAccountView.value) {
    adAccountAssetTableRef.value?.openImport();
    return;
  }
  assetImportModalRef.value?.show();
}

async function importAssetFile(file: File, subtype: string) {
  const result = await assetFlowApi.importAssetFile(file, subtype);
  if (result.successCount > 0) await loadRemoteAssets();
  return result;
}

async function loadAssetImportHistory(params: {
  page: number;
  pageSize: number;
}) {
  return assetFlowApi.importHistory(params);
}

async function downloadAssetImportFailedFile(id: string) {
  return assetFlowApi.importFailedFile(id);
}

function openEdit(asset: AssetRecord) {
  if (!canManageAssets.value) {
    message.warning('当前演示角色没有资产管理权限');
    return;
  }
  if (asset.status === 'return_pending') {
    message.warning('待回收资产暂不可编辑');
    return;
  }
  editingId.value = asset.id;
  for (const key of Object.keys(formErrors)) delete formErrors[key];
  const savedDetails = asset.details ?? {};
  const details = {
    ...createEmptyAssetDetails(asset.subtype),
    ...savedDetails,
  };
  const assetType = findInventoryAssetTypeBySubtype(asset.subtype);
  assetFormCategory.value = assetType?.category ?? asset.category;
  if (assetType) {
    if (!Object.hasOwn(savedDetails, assetType.identifierKey)) {
      details[assetType.identifierKey] = asset.identifier;
    }
    if (!Object.hasOwn(savedDetails, assetType.nameKey)) {
      details[assetType.nameKey] = asset.name;
    }
  }
  Object.assign(form, asset, {
    details,
    usageTeam: asset.usageTeam ?? '',
    usageTeamId: '',
  });
  syncSelectedChannel();
  if (asset.subtype === 'pixel') {
    void Promise.all([loadProjectOptions(), loadDepartmentOptions()]).then(
      syncPixelUsageTeamId,
    );
  }
  drawerOpen.value = true;
}

function handlePixelProjectChange(value: unknown) {
  const projectId =
    typeof value === 'string' || typeof value === 'number'
      ? String(value)
      : undefined;
  const project = projectOptions.value.find(
    (option) => option.value === projectId,
  );
  form.projectId = projectId ?? '';
  form.projectName = project?.label ?? '';
  delete formErrors.projectId;
  if (!projectId) {
    form.usageTeamId = '';
    form.usageTeam = '';
    delete formErrors.usageTeamId;
  }
}

function handlePixelUsageTeamChange(value: unknown) {
  const usageTeamId =
    typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  const department = departmentOptions.value.find(
    (option) => option.value === usageTeamId,
  );
  form.usageTeamId = usageTeamId;
  form.usageTeam = department?.name ?? '';
  delete formErrors.usageTeamId;
}

async function saveAsset() {
  const canSave = editingId.value
    ? canManageAssets.value
    : canCreateAssets.value;
  if (!canSave) {
    message.warning('当前角色没有资产录入权限');
    return;
  }
  for (const key of Object.keys(formErrors)) delete formErrors[key];
  if (!form.subtype) {
    formErrors.assetType = '请选择资产类型';
    message.error('请选择资产类型');
    return;
  }
  if (!editingId.value && form.subtype === 'ad_account') {
    message.error('广告账户由账户台账维护，不能在资产管理创建');
    return;
  }
  if (currentAssetRequiresChannel.value && !selectedChannel.value) {
    formErrors.channelName = '请选择渠道';
    message.error('请选择渠道');
    return;
  }
  const missingField = currentAssetFields.value.find(
    (field) => field.required && !form.details[field.key]?.trim(),
  );
  if (missingField) {
    formErrors[`details.${missingField.key}`] = `请填写${missingField.label}`;
    message.error(`请填写${missingField.label}`);
    return;
  }
  const hasUsageUser = Boolean(form.assigneeId?.trim() && form.owner?.trim());
  if (!isPixelAsset.value && form.status === 'allocated' && !hasUsageUser) {
    formErrors.assigneeId = '请选择使用人';
    message.error('请选择使用人');
    return;
  }
  if (isPixelAsset.value && form.projectId && !form.usageTeamId) {
    formErrors.usageTeamId = '请选择使用团队';
    message.error('请选择使用团队');
    return;
  }
  const { identifier, name } = resolveAssetIdentity();
  if (!identifier) {
    message.error('请填写资产唯一标识');
    return;
  }
  savingAsset.value = true;
  const safeForm = {
    ...form,
    birthday: form.details.birthday ?? '',
    emailLoginUrl: form.details.emailLoginUrl ?? '',
    gender: form.details.gender ?? '',
    password: form.details.password ? '已配置' : '',
    status: form.status || 'available',
    twoFactorKey: form.details.twoFa ? '已配置' : '',
  };
  try {
    if (!isFusionDemoMode()) {
      const assetType = backendAssetType(form.subtype);
      const channelAssignment = currentAssetRequiresChannel.value
        ? {
            channelId: selectedChannel.value?.value,
            channelName: selectedChannel.value?.label,
            // 项目字段保留渠道镜像，兼容仍从项目字段读取渠道归属的存量读模型。
            projectId: selectedChannel.value?.value,
            projectName: selectedChannel.value?.label,
          }
        : {};
      const projectAssignment = isPixelAsset.value
        ? {
            projectId: form.projectId,
            projectName: form.projectName,
            usageTeamId: form.projectId ? form.usageTeamId : undefined,
          }
        : {};
      const payload = {
        assetCode: identifier,
        assetName: name,
        assetType,
        assigneeId:
          form.status === 'allocated' && !isPixelAsset.value
            ? form.assigneeId
            : undefined,
        ...channelAssignment,
        ...projectAssignment,
        remark: form.note,
        secretData: serializeAssetDetails(form.subtype, form.details),
        status: backendAssetStatus(form.status),
      } as const;
      await (editingId.value
        ? assetFlowApi.updateAsset(editingId.value, payload)
        : assetFlowApi.createAsset(payload));
      drawerOpen.value = false;
      message.success(editingId.value ? '资产已更新' : '资产已入库');
      await loadRemoteAssets();
      return;
    }
    if (editingId.value) {
      assets.value = assets.value.map((asset) =>
        asset.id === editingId.value
          ? {
              ...asset,
              ...safeForm,
              details: { ...form.details },
              identifier,
              name,
            }
          : asset,
      );
      message.success('资产已更新');
    } else {
      assets.value = [
        {
          category: currentAssetType.value?.category ?? activeCategory.value,
          ...safeForm,
          details: { ...form.details },
          createdAt:
            form.details.createDate ||
            new Date().toLocaleString('zh-CN', { hour12: false }),
          id: `AST-${Date.now()}`,
          identifier,
          name,
          owner: safeForm.owner,
        },
        ...assets.value,
      ];
      message.success('资产已入库');
    }
    drawerOpen.value = false;
  } finally {
    savingAsset.value = false;
  }
}

function removeAsset(asset: AssetRecord) {
  if (!canManageAssets.value) {
    message.warning('当前演示角色没有资产管理权限');
    return;
  }
  if (asset.subtype === 'ad_account') {
    message.warning('广告账户由账户台账维护，不能在资产管理删除');
    return;
  }
  if (asset.status === 'return_pending') {
    message.warning('待回收资产暂不可删除');
    return;
  }
  Modal.confirm({
    content: `删除后将无法继续分配“${asset.name}”，确定删除吗？`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除资产',
    onOk: async () => {
      if (!isFusionDemoMode()) {
        await assetFlowApi.deleteAsset(asset.id);
        await loadRemoteAssets();
        message.success('资产已删除');
        return;
      }
      assets.value = assets.value.filter((item) => item.id !== asset.id);
      message.success('资产已删除');
    },
  });
}

function openReturn(asset: AssetRecord) {
  if (!canManageAssets.value || asset.status !== 'allocated') return;
  returnTarget.value = asset;
  returnReason.value = '';
  returnOpen.value = true;
}

async function openLifecycle(asset: AssetRecord) {
  const requestVersion = ++lifecycleRequestVersion;
  lifecycleAssetSubtype.value = asset.subtype;
  lifecycleAccountId.value =
    asset.subtype === 'ad_account' ? asset.identifier.trim() : undefined;
  lifecycleOpen.value = true;
  lifecycleLoading.value = true;
  lifecycleDetail.value = undefined;
  try {
    const detail =
      asset.subtype === 'ad_account'
        ? await loadAdAccountLifecycleDetail(asset.identifier)
        : await assetFlowApi.lifecycle(asset.id);
    if (requestVersion !== lifecycleRequestVersion) return;
    lifecycleDetail.value = detail;
  } finally {
    if (requestVersion === lifecycleRequestVersion) {
      lifecycleLoading.value = false;
    }
  }
}

async function submitReturn() {
  const target = returnTarget.value;
  if (!target) return;
  const reason = returnReason.value.trim();
  if (!reason) {
    message.warning('请填写回收原因');
    return;
  }
  if (reason.length > 1000) {
    message.warning('回收原因不能超过 1000 个字');
    return;
  }

  returnSubmitting.value = true;
  try {
    if (isFusionDemoMode()) {
      assets.value = assets.value.map((asset) =>
        asset.id === target.id ? { ...asset, status: 'return_pending' } : asset,
      );
    } else {
      await assetReturnApi.create(target.id, reason);
      await loadRemoteAssets();
    }
    returnOpen.value = false;
    message.success('回收申请已提交');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '提交回收申请失败');
  } finally {
    returnSubmitting.value = false;
  }
}
</script>

<template>
  <div
    class="asset-management-page flex min-h-0 w-full min-w-0 flex-col"
    :class="{ 'asset-management-page--neumorphic': !isMyAssets }"
    :style="{
      '--asset-management-table-viewport-height': `${ASSET_TABLE_VIEWPORT_HEIGHT}px`,
    }"
  >
    <section
      v-if="isMyAssets"
      class="flex flex-col justify-between sm:flex-row"
      :class="isMyAssets ? 'gap-3 sm:items-center' : 'gap-4 sm:items-end'"
    >
      <div class="min-w-0">
        <h1
          class="m-0 font-semibold"
          :class="
            isMyAssets
              ? 'text-foreground text-[var(--adpulse-page-title-size)]'
              : 'asset-page-title text-[var(--adpulse-page-title-size)]'
          "
        >
          {{ isMyAssets ? '我的资产' : '资产管理' }}
        </h1>
        <p
          class="mb-0 text-sm"
          :class="
            isMyAssets
              ? 'text-muted-foreground mt-1'
              : 'asset-page-description mt-1'
          "
        >
          {{
            isMyAssets
              ? '查看已分配的社交、广告与办公类资产。'
              : '统一维护社交、广告与办公资产，并记录库存、分配和异常状态。'
          }}
        </p>
      </div>
    </section>

    <Alert v-if="remoteError" type="error" show-icon :message="remoteError" />

    <Modal
      :closable="!authorizationSubmitting"
      :confirm-loading="authorizationSubmitting"
      :keyboard="!authorizationSubmitting"
      :mask-closable="!authorizationSubmitting"
      :ok-button-props="{
        disabled:
          authorizationAppsLoading ||
          authorizationApps.length === 0 ||
          !selectedAuthorizationAppId,
      }"
      :open="authorizationModalOpen"
      cancel-text="取消"
      ok-text="前往 Facebook 授权"
      title="授权账户"
      :width="560"
      @cancel="closeAuthorization"
      @ok="confirmAuthorization"
    >
      <div class="py-2">
        <p class="text-muted-foreground mb-4 text-sm leading-6">
          选择已配置的 Facebook 应用，系统将跳转到 Facebook 完成个号授权。
        </p>
        <div class="text-foreground mb-2 text-sm font-medium">
          <span class="text-destructive" aria-hidden="true">*</span>
          授权应用
        </div>
        <div
          v-if="authorizationAppsLoading"
          aria-busy="true"
          class="text-muted-foreground flex min-h-32 items-center justify-center text-sm"
        >
          正在加载授权应用…
        </div>
        <Empty
          v-else-if="authorizationApps.length === 0"
          description="暂无可用于 Facebook 授权的应用"
        />
        <Radio.Group
          v-else
          v-model:value="selectedAuthorizationAppId"
          class="flex w-full flex-col gap-2"
        >
          <Radio
            v-for="app in authorizationApps"
            :key="app.app_id"
            :value="app.app_id"
            class="border-border hover:bg-accent m-0 flex min-h-11 w-full items-center rounded-lg border px-3 py-2 transition-colors"
          >
            <span class="text-foreground font-medium">{{ app.name }}</span>
            <span class="text-muted-foreground ml-2 font-mono text-xs">
              {{ app.app_id }}
            </span>
          </Radio>
        </Radio.Group>
      </div>
    </Modal>
    <Card :body-style="{ padding: '16px' }">
      <div class="flex flex-col gap-4">
        <div
          class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between"
        >
          <div class="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-3">
            <div class="flex min-w-0 flex-wrap items-center gap-2">
              <span class="text-muted-foreground shrink-0 text-sm font-medium">
                资产分类
              </span>
              <RadioGroup
                aria-label="资产分类"
                button-style="solid"
                class="whitespace-nowrap"
                :value="activeCategory"
                @change="handleAssetCategoryRadioChange"
              >
                <RadioButton
                  v-for="category in primaryCategoryKeys"
                  :key="category"
                  :value="category"
                >
                  {{ categoryMeta[category].label }}
                </RadioButton>
              </RadioGroup>
            </div>
            <div class="flex min-w-0 flex-wrap items-center gap-2">
              <span class="text-muted-foreground shrink-0 text-sm font-medium">
                资产类型
              </span>
              <RadioGroup
                aria-label="资产类型"
                button-style="solid"
                class="whitespace-nowrap"
                :value="subtypeFilter"
                @change="handleAssetSubtypeChange"
              >
                <RadioButton
                  v-for="subtype in currentSubtypeOptions"
                  :key="subtype.value"
                  :value="subtype.value"
                >
                  {{ subtype.label }}
                </RadioButton>
              </RadioGroup>
            </div>
          </div>
          <div v-if="canManageAssets" class="flex flex-wrap gap-2">
            <Button
              v-if="isAdAccountView"
              class="!inline-flex items-center"
              @click="openAuthorization"
            >
              <IconifyIcon aria-hidden="true" icon="lucide:shield-check" />
              授权账户
            </Button>
            <Button
              class="!inline-flex items-center"
              :type="isAdAccountView ? 'primary' : 'default'"
              @click="openAssetImport"
            >
              <IconifyIcon aria-hidden="true" icon="lucide:file-up" />批量导入
            </Button>
            <Button
              v-if="!isAdAccountView"
              class="!inline-flex items-center"
              type="primary"
              @click="openCreate"
            >
              <IconifyIcon aria-hidden="true" icon="lucide:plus" />添加资产
            </Button>
          </div>
        </div>
        <div class="border-border border-t pt-4">
          <AssetFilterPanel
            v-model:filter-values="assetFilterValues"
            v-model:keyword="keyword"
            v-model:open="advancedFiltersOpen"
            :fields="currentAssetFilterFields"
            :keyword-placeholder="
              isAdAccountView
                ? '搜索账户名称；多个账户 ID 可用空格或换行分隔'
                : undefined
            "
            :multiline-keyword="isAdAccountView"
            panel-id="asset-management-advanced-filters"
            :search-input-key="`${activeCategory}-${subtypeFilter ?? 'all'}`"
          >
            <template #actions>
              <template v-if="isAdAccountView">
                <span
                  aria-hidden="true"
                  class="border-border mx-1 h-8 border-l"
                />
                <!-- 临时隐藏批量修改入口，保留实现便于后续恢复。 -->
                <!-- <Button
                  v-if="canManageAssets"
                  class="!inline-flex  items-center"
                  @click="adAccountAssetTableRef?.openBatchEdit()"
                >
                  <IconifyIcon
                    aria-hidden="true"
                    icon="lucide:clipboard-pen-line"
                  />
                  {{
                    adAccountAssetTableRef?.selectedAccountCount
                      ? `批量修改（${adAccountAssetTableRef.selectedAccountCount}）`
                      : '批量修改'
                  }}
                </Button> -->
                <Button
                  v-if="canManageAssets"
                  class="!inline-flex items-center"
                  @click="adAccountAssetTableRef?.openOfficeSpreadsheet()"
                >
                  <IconifyIcon aria-hidden="true" icon="lucide:sheet" />
                  {{
                    adAccountAssetTableRef?.selectedAccountCount
                      ? `Excel 批量处理（${adAccountAssetTableRef.selectedAccountCount}）`
                      : 'Excel 批量处理'
                  }}
                </Button>
                <Button
                  :loading="adAccountAssetTableRef?.isExporting"
                  class="!inline-flex items-center"
                  @click="adAccountAssetTableRef?.exportAccounts()"
                >
                  <IconifyIcon aria-hidden="true" icon="lucide:download" />
                  {{
                    adAccountAssetTableRef?.selectedAccountCount
                      ? `导出所选（${adAccountAssetTableRef.selectedAccountCount}）`
                      : '导出'
                  }}
                </Button>
              </template>
              <template v-else>
                <!-- 临时隐藏批量修改入口，保留实现便于后续恢复。 -->
                <!-- <Button
                  v-if="canManageAssets"
                  class="!inline-flex  items-center"
                  @click="openBatchEdit"
                >
                  <IconifyIcon
                    aria-hidden="true"
                    icon="lucide:clipboard-pen-line"
                  />
                  {{
                    selectedAssetIds.length
                      ? `批量修改（${selectedAssetIds.length}）`
                      : '批量修改'
                  }}
                </Button> -->
                <Button
                  v-if="canManageAssets"
                  class="!inline-flex items-center"
                  @click="openOfficeSpreadsheet"
                >
                  <IconifyIcon aria-hidden="true" icon="lucide:sheet" />
                  {{
                    selectedAssetIds.length
                      ? `Excel 批量处理（${selectedAssetIds.length}）`
                      : 'Excel 批量处理'
                  }}
                </Button>
                <Button
                  :loading="exportingAssets"
                  class="!inline-flex items-center"
                  @click="exportAssets"
                >
                  <IconifyIcon aria-hidden="true" icon="lucide:download" />
                  {{
                    selectedAssetIds.length > 0
                      ? `导出所选（${selectedAssetIds.length}）`
                      : '导出'
                  }}
                </Button>
              </template>
            </template>
          </AssetFilterPanel>
        </div>
      </div>
    </Card>

    <AdAccountAssetTable
      v-if="isAdAccountView"
      ref="adAccountAssetTableRef"
      :can-manage="canManageAssets"
      :filters="assetFilterValues"
      :keyword="keyword"
      :page="currentAssetPage"
      :page-size="assetPageSize"
      :page-size-options="assetPageSizeOptions"
      :restoring="isApplyingRoute"
      :neumorphic="!isMyAssets"
      @pagination-change="changeAssetPage"
    />
    <ListLoading v-else-if="remoteLoading" />
    <section
      v-else-if="filteredAssets.length > 0"
      :aria-busy="remoteLoading"
      class="min-w-0"
      :class="
        isMyAssets
          ? 'border-border bg-card rounded-xl border p-3'
          : 'asset-ledger-surface asset-neumorphic-surface'
      "
    >
      <div
        class="ux-native-table-viewport asset-table-viewport hidden lg:block"
      >
        <table
          aria-label="资产列表。可用鼠标拖拽框选单元格，按 Ctrl 或 Command 加 C 复制。"
          class="asset-management-table min-w-full table-auto border-collapse select-none text-left text-sm"
          tabindex="0"
          @copy="tableSelection.copySelection"
          @keydown="handleTableKeydown"
          @pointercancel="stopTableSelection"
          @pointermove="extendTableSelection"
          @pointerup="stopTableSelection"
        >
          <thead>
            <tr>
              <th class="w-12 px-3 py-3 text-center">
                <Checkbox
                  aria-label="全选当前筛选结果"
                  :checked="areAllFilteredAssetsSelected"
                  :indeterminate="
                    selectedAssetIds.length > 0 && !areAllFilteredAssetsSelected
                  "
                  @change="toggleAllFilteredAssets"
                />
              </th>
              <th
                v-for="column in currentAssetInformationColumns"
                :key="column.key"
                class="min-w-36 px-3 py-3 font-medium"
              >
                {{ column.label }}
              </th>
              <th
                v-if="showsChannelContext"
                class="min-w-36 px-3 py-3 font-medium"
              >
                渠道名称
              </th>
              <th v-if="!isPixelListing" class="min-w-24 px-3 py-3 font-medium">
                使用人
              </th>
              <th class="min-w-36 px-3 py-3 font-medium">入库时间</th>
              <th class="min-w-24 px-3 py-3 font-medium">库存状态</th>
              <th
                v-if="hasAssetTableActions"
                class="asset-table-sticky-head sticky right-0 z-20 min-w-28 border-l px-4 py-3 text-left font-medium"
              >
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(asset, rowIndex) in paginatedAssets"
              :key="asset.id"
              class="asset-table-row border-t"
            >
              <td class="w-12 px-3 py-3 text-center">
                <Checkbox
                  :aria-label="`选择资产：${asset.name}`"
                  :checked="selectedAssetIdSet.has(asset.id)"
                  @change="toggleAssetSelection(asset.id)"
                />
              </td>
              <td
                v-for="(column, columnIndex) in currentAssetInformationColumns"
                :key="column.key"
                :class="{
                  'bg-accent text-accent-foreground':
                    tableSelection.isCellSelected(rowIndex, columnIndex),
                }"
                class="max-w-48 cursor-cell px-3 py-3"
                data-table-selection-cell
                :data-column-index="columnIndex"
                :data-row-index="rowIndex"
                @pointerdown="
                  beginTableSelection($event, rowIndex, columnIndex)
                "
              >
                <SensitiveAssetValue
                  v-if="column.sensitive"
                  :label="column.label"
                  :value="assetInformationExportValue(asset, column)"
                />
                <div
                  v-else
                  class="truncate"
                  :title="assetInformationValue(asset, column)"
                >
                  {{ assetInformationValue(asset, column) }}
                </div>
              </td>
              <td
                v-if="showsChannelContext"
                :class="{
                  'bg-accent text-accent-foreground':
                    tableSelection.isCellSelected(
                      rowIndex,
                      tableColumnIndex('channelName'),
                    ),
                }"
                class="cursor-cell px-3 py-3"
                data-table-selection-cell
                :data-column-index="tableColumnIndex('channelName')"
                :data-row-index="rowIndex"
                @pointerdown="
                  beginTableSelection(
                    $event,
                    rowIndex,
                    tableColumnIndex('channelName'),
                  )
                "
              >
                <div class="truncate" :title="asset.channelName">
                  {{ asset.channelName || '-' }}
                </div>
              </td>
              <td
                v-if="!isPixelListing"
                :class="{
                  'bg-accent text-accent-foreground':
                    tableSelection.isCellSelected(
                      rowIndex,
                      tableColumnIndex('owner'),
                    ),
                }"
                class="cursor-cell truncate px-3 py-3"
                data-table-selection-cell
                :data-column-index="tableColumnIndex('owner')"
                :data-row-index="rowIndex"
                :title="asset.owner"
                @pointerdown="
                  beginTableSelection(
                    $event,
                    rowIndex,
                    tableColumnIndex('owner'),
                  )
                "
              >
                {{ asset.owner || '-' }}
              </td>
              <td
                :class="{
                  'bg-accent text-accent-foreground':
                    tableSelection.isCellSelected(
                      rowIndex,
                      tableColumnIndex('createdAt'),
                    ),
                }"
                class="cursor-cell px-3 py-3 text-slate-600"
                data-table-selection-cell
                :data-column-index="tableColumnIndex('createdAt')"
                :data-row-index="rowIndex"
                @pointerdown="
                  beginTableSelection(
                    $event,
                    rowIndex,
                    tableColumnIndex('createdAt'),
                  )
                "
              >
                {{ formatAssetCreatedAt(asset.createdAt) }}
              </td>
              <td
                :class="{
                  'bg-accent text-accent-foreground':
                    tableSelection.isCellSelected(
                      rowIndex,
                      tableColumnIndex('status'),
                    ),
                }"
                class="cursor-cell px-3 py-3"
                data-table-selection-cell
                :data-column-index="tableColumnIndex('status')"
                :data-row-index="rowIndex"
                @pointerdown="
                  beginTableSelection(
                    $event,
                    rowIndex,
                    tableColumnIndex('status'),
                  )
                "
              >
                <Tag :color="statusMeta[asset.status].color" class="!m-0">
                  {{ statusMeta[asset.status].label }}
                </Tag>
              </td>
              <td
                v-if="hasAssetTableActions"
                class="asset-table-sticky-cell sticky right-0 z-10 space-x-2 whitespace-nowrap border-l px-4 py-3 text-right"
              >
                <Button type="link" @click="openLifecycle(asset)"
                  >生命周期</Button
                >
                <Dropdown
                  v-if="
                    primaryAssetTableAction(asset) === 'account-application'
                  "
                  trigger="click"
                >
                  <Button type="link">账户操作</Button>
                  <template #overlay>
                    <Menu>
                      <MenuItem
                        v-for="action in assetAccountApplicationActions"
                        :key="action.applicationCode"
                        @click="openAccountApplication(asset, action)"
                      >
                        {{ action.label }}申请
                      </MenuItem>
                    </Menu>
                  </template>
                </Dropdown>
                <Button
                  v-else-if="primaryAssetTableAction(asset) === 'edit'"
                  type="link"
                  @click="openEdit(asset)"
                >
                  编辑
                </Button>
                <Button
                  v-else-if="primaryAssetTableAction(asset) === 'application'"
                  type="link"
                  @click="openApplicationDetail(asset.applicationId!)"
                >
                  查看申请单
                </Button>
                <Button
                  v-else-if="primaryAssetTableAction(asset) === 'return'"
                  type="link"
                  @click="openReturn(asset)"
                >
                  回收
                </Button>
                <Button
                  v-else-if="primaryAssetTableAction(asset) === 'delete'"
                  danger
                  type="link"
                  @click="removeAsset(asset)"
                >
                  删除
                </Button>
                <Dropdown
                  v-if="hasAdditionalAssetTableActions(asset)"
                  trigger="click"
                >
                  <Button type="link">更多</Button>
                  <template #overlay>
                    <Menu>
                      <MenuItem
                        v-if="
                          asset.applicationId &&
                          primaryAssetTableAction(asset) !== 'application'
                        "
                        @click="openApplicationDetail(asset.applicationId)"
                      >
                        查看申请单
                      </MenuItem>
                      <MenuItem
                        v-if="
                          canManageAssets &&
                          asset.status === 'allocated' &&
                          primaryAssetTableAction(asset) !== 'return'
                        "
                        @click="openReturn(asset)"
                      >
                        回收
                      </MenuItem>
                      <MenuItem
                        v-if="
                          canManageAssets &&
                          asset.status !== 'return_pending' &&
                          asset.subtype !== 'ad_account' &&
                          primaryAssetTableAction(asset) !== 'delete'
                        "
                        danger
                        @click="removeAsset(asset)"
                      >
                        删除
                      </MenuItem>
                    </Menu>
                  </template>
                </Dropdown>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="grid grid-cols-1 gap-3 lg:hidden">
        <Card
          v-for="asset in paginatedAssets"
          :key="asset.id"
          class="min-w-0"
          hoverable
        >
          <div class="flex min-w-0 items-start justify-between gap-3">
            <div class="flex min-w-0 items-start gap-3">
              <Checkbox
                :aria-label="`选择资产：${asset.name}`"
                :checked="selectedAssetIdSet.has(asset.id)"
                class="mt-0.5 shrink-0"
                @change="toggleAssetSelection(asset.id)"
              />
              <div class="min-w-0">
                <div
                  class="truncate font-semibold text-slate-900"
                  :title="asset.name"
                >
                  {{ asset.name }}
                </div>
                <div
                  class="mt-1 truncate font-mono text-xs text-slate-500"
                  :title="asset.identifier"
                >
                  {{ asset.identifier }}
                </div>
              </div>
            </div>
            <Tag :color="statusMeta[asset.status].color" class="!m-0 shrink-0">
              {{ statusMeta[asset.status].label }}
            </Tag>
          </div>
          <dl
            class="mt-4 grid grid-cols-[72px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm"
          >
            <dt class="text-slate-500">资产类型</dt>
            <dd class="m-0">
              <Tag>{{ subtypeLabel(asset.subtype) }}</Tag>
            </dd>
            <template
              v-for="column in currentAssetInformationColumns"
              :key="column.key"
            >
              <dt class="text-slate-500">{{ column.label }}</dt>
              <dd class="m-0 min-w-0">
                <SensitiveAssetValue
                  v-if="column.sensitive"
                  :label="column.label"
                  :value="assetInformationExportValue(asset, column)"
                />
                <span
                  v-else
                  class="block truncate"
                  :title="assetInformationValue(asset, column)"
                >
                  {{ assetInformationValue(asset, column) }}
                </span>
              </dd>
            </template>
            <template v-if="asset.subtype !== 'pixel'">
              <dt class="text-slate-500">使用人</dt>
              <dd class="m-0 truncate">{{ asset.owner }}</dd>
            </template>
            <template v-if="showsChannelContext">
              <dt class="text-slate-500">渠道名称</dt>
              <dd class="m-0 truncate">
                {{ asset.channelName || '-' }}
              </dd>
            </template>
            <dt class="text-slate-500">入库时间</dt>
            <dd class="m-0 truncate">
              {{ formatAssetCreatedAt(asset.createdAt) }}
            </dd>
            <dt class="text-slate-500">库存状态</dt>
            <dd class="m-0">
              <Tag :color="statusMeta[asset.status].color" class="!m-0">
                {{ statusMeta[asset.status].label }}
              </Tag>
            </dd>
          </dl>
          <div
            v-if="assetTableActions(asset).length > 0"
            class="mt-4 flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-3"
          >
            <Dropdown v-if="canApplyAccountOperation(asset)" trigger="click">
              <Button class=""> 账户操作 </Button>
              <template #overlay>
                <Menu>
                  <MenuItem
                    v-for="action in assetAccountApplicationActions"
                    :key="action.applicationCode"
                    @click="openAccountApplication(asset, action)"
                  >
                    {{ action.label }}申请
                  </MenuItem>
                </Menu>
              </template>
            </Dropdown>
            <Button class="" @click="openLifecycle(asset)">生命周期</Button>
            <Button
              v-if="asset.applicationId"
              class=""
              @click="openApplicationDetail(asset.applicationId)"
            >
              查看申请单
            </Button>
            <Button
              v-if="canManageAssets && asset.status === 'allocated'"
              class=""
              @click="openReturn(asset)"
            >
              回收
            </Button>
            <Button
              v-if="canManageAssets && asset.status !== 'return_pending'"
              class=""
              @click="openEdit(asset)"
            >
              编辑
            </Button>
            <Button
              v-if="
                canManageAssets &&
                asset.status !== 'return_pending' &&
                asset.subtype !== 'ad_account'
              "
              class=""
              danger
              @click="removeAsset(asset)"
            >
              删除
            </Button>
          </div>
        </Card>
      </div>
      <div class="asset-ledger-pagination mt-3 flex justify-end">
        <Pagination
          :current="currentAssetPage"
          :page-size="assetPageSize"
          :page-size-options="assetPageSizeOptions"
          :total="assetPaginationTotal"
          show-size-changer
          show-less-items
          @change="changeAssetPage"
        />
      </div>
    </section>
    <Card
      v-else
      :class="{ 'asset-empty-surface': !isMyAssets }"
      :aria-busy="remoteLoading"
    >
      <Empty description="当前筛选条件下暂无资产" />
    </Card>

    <Modal
      v-model:open="returnOpen"
      :confirm-loading="returnSubmitting"
      :mask-closable="!returnSubmitting"
      cancel-text="取消"
      ok-text="提交回收"
      title="申请回收资产"
      @ok="submitReturn"
    >
      <Alert
        class="mb-4"
        message="提交后资产将进入待回收状态，不再参与新的资产分配。"
        show-icon
        type="warning"
      />
      <div class="mb-4 rounded-lg bg-slate-50 p-3 dark:bg-slate-900">
        <div class="font-medium text-slate-900 dark:text-white">
          {{ returnTarget?.name }}
        </div>
        <div class="mt-1 font-mono text-xs text-slate-500">
          {{ returnTarget?.identifier }}
        </div>
      </div>
      <label
        class="mb-2 block text-sm font-medium text-slate-700 dark:text-slate-200"
        for="asset-return-reason"
      >
        回收原因
      </label>
      <Input.TextArea
        id="asset-return-reason"
        v-model:value="returnReason"
        :disabled="returnSubmitting"
        :maxlength="1000"
        :rows="4"
        placeholder="请说明项目结束、资产闲置或其他回收原因"
        show-count
      />
    </Modal>

    <Drawer
      v-model:open="drawerOpen"
      :closable="!savingAsset"
      :body-style="{ overflow: 'hidden', padding: 0 }"
      :mask-closable="!savingAsset"
      :title="editingId ? '编辑资产' : '添加资产'"
      width="min(560px, 100vw)"
      destroy-on-close
    >
      <div class="h-full min-h-0 overflow-y-auto">
        <ConfigProvider :get-popup-container="getPopupContainer">
          <div class="relative min-h-full p-6" data-popup-scroll-host>
            <Form layout="vertical">
              <FormItem label="资产分类" :required="!editingId">
                <Input
                  v-if="editingId"
                  :value="currentAssetCategoryLabel"
                  readonly
                />
                <Select
                  v-else
                  v-model:value="assetFormCategory"
                  :options="assetCategoryOptions"
                  placeholder="请选择资产分类"
                  @change="handleAssetCategoryChange"
                />
              </FormItem>
              <FormItem
                :help="formErrors.assetType"
                :extra="editingId ? '资产分类和类型创建后不可修改' : undefined"
                label="资产类型"
                :required="!editingId"
                :validate-status="formErrors.assetType ? 'error' : undefined"
              >
                <Input
                  v-if="editingId"
                  :value="currentAssetTypeLabel"
                  readonly
                />
                <Select
                  v-else
                  v-model:value="form.subtype"
                  allow-clear
                  :options="formAssetTypeOptions"
                  @change="handleAssetTypeChange"
                />
              </FormItem>
              <FormItem
                v-if="currentAssetRequiresChannel"
                :help="formErrors.channelName"
                label="渠道名称"
                required
                :validate-status="formErrors.channelName ? 'error' : undefined"
              >
                <Select
                  v-model:value="form.channelId"
                  allow-clear
                  :loading="channelLoading"
                  option-filter-prop="label"
                  :options="channelOptions"
                  placeholder="请选择渠道"
                  show-search
                  @change="handleChannelChange"
                />
              </FormItem>
              <div
                v-if="isPixelAsset"
                class="grid grid-cols-1 gap-x-4 sm:grid-cols-2"
              >
                <template
                  v-for="column in currentAssetFormInformationColumns"
                  :key="column.key"
                >
                  <AssetDetailFormField
                    v-if="column.kind === 'detail' && column.field"
                    v-model="form.details[column.field.key]"
                    :error="formErrors[`details.${column.field.key}`]"
                    :field="column.field"
                    :readonly="
                      Boolean(editingId) &&
                      column.field.key === currentAssetType?.identifierKey
                    "
                    @update:model-value="clearDetailFormError(column.field)"
                  />
                  <FormItem
                    v-else-if="column.kind === 'projectName'"
                    label="所属项目"
                  >
                    <Select
                      :value="form.projectId || undefined"
                      allow-clear
                      :loading="projectOptions.length === 0"
                      :options="projectOptions"
                      placeholder="请选择项目"
                      show-search
                      @change="handlePixelProjectChange"
                    />
                    <div class="mt-1 text-xs text-slate-500">
                      关联项目后自动标记为已分配；留空则作为可申请库存。
                    </div>
                  </FormItem>
                  <FormItem
                    v-else-if="column.kind === 'usageTeam'"
                    :help="formErrors.usageTeamId"
                    label="使用团队"
                    :required="Boolean(form.projectId)"
                    :validate-status="
                      formErrors.usageTeamId ? 'error' : undefined
                    "
                  >
                    <Select
                      :value="form.usageTeamId || undefined"
                      allow-clear
                      :disabled="!form.projectId"
                      :loading="departmentOptionsLoading"
                      option-filter-prop="label"
                      :options="departmentOptions"
                      placeholder="请选择系统部门"
                      show-search
                      @change="handlePixelUsageTeamChange"
                    />
                    <div class="mt-1 text-xs text-slate-500">
                      使用团队来自系统部门；未关联项目时无需选择。
                    </div>
                  </FormItem>
                  <FormItem v-else class="sm:col-span-2" label="备注">
                    <Input.TextArea
                      v-model:value="form.note"
                      allow-clear
                      :maxlength="300"
                      :rows="4"
                      show-count
                    />
                  </FormItem>
                </template>
              </div>
              <div v-else class="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
                <AssetDetailFormField
                  v-for="field in currentAssetFields"
                  :key="field.key"
                  v-model="form.details[field.key]"
                  :error="formErrors[`details.${field.key}`]"
                  :field="field"
                  :readonly="
                    Boolean(editingId) &&
                    field.key === currentAssetType?.identifierKey
                  "
                  @update:model-value="clearDetailFormError(field)"
                />
              </div>
              <FormItem v-if="!isPixelAsset" label="库存状态" required>
                <Select
                  v-model:value="form.status"
                  :options="
                    Object.entries(statusMeta)
                      .filter(([value]) => value !== 'return_pending')
                      .map(([value, item]) => ({
                        label: item.label,
                        value,
                      }))
                  "
                  @change="handleAssetStatusChange"
                />
              </FormItem>
              <FormItem
                v-if="form.status === 'allocated' && !isPixelAsset"
                :help="formErrors.assigneeId"
                label="使用人"
                required
                :validate-status="formErrors.assigneeId ? 'error' : undefined"
              >
                <StableUserSelect
                  v-model="form.assigneeId"
                  :legacy-label="form.owner"
                  placeholder="请选择使用人"
                  @change="handleAssigneeChange"
                  @load-error="message.error('用户列表加载失败，请稍后重试')"
                />
              </FormItem>
              <FormItem v-if="!isPixelAsset" label="备注">
                <Input.TextArea
                  v-model:value="form.note"
                  allow-clear
                  :maxlength="300"
                  :rows="4"
                  show-count
                />
              </FormItem>
            </Form>
          </div>
        </ConfigProvider>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <Button :disabled="savingAsset" @click="drawerOpen = false">
            取消
          </Button>
          <Button :loading="savingAsset" type="primary" @click="saveAsset">
            保存资产
          </Button>
        </div>
      </template>
    </Drawer>

    <AssetBatchEditModal
      v-model:open="batchEditOpen"
      allow-create
      :fields="batchEditFields"
      :identifier-key="`detail.${findInventoryAssetTypeBySubtype(subtypeFilter ?? '')?.identifierKey ?? ''}`"
      :loading="batchEditLoading"
      :resolve-identifiers="resolveBatchEditIdentifiers"
      :rows="batchEditRows"
      :submitting="batchEditSubmitting"
      target-label="资产"
      :title="`批量修改${subtypeLabel(subtypeFilter ?? '')}`"
      @submit="submitBatchEdit"
    />

    <AssetOfficeSpreadsheetModal
      v-if="officeSpreadsheetOpen"
      v-model:open="officeSpreadsheetOpen"
      allow-create
      :fields="officeSpreadsheetFields"
      :identifier-key="`detail.${findInventoryAssetTypeBySubtype(subtypeFilter ?? '')?.identifierKey ?? ''}`"
      :loading="officeSpreadsheetLoading"
      :rows="officeSpreadsheetRows"
      :status-hint="
        isPixelListing
          ? '所属项目和使用团队都填写时自动设为已使用；都为空时自动设为可分配。'
          : '使用人非空时自动设为已使用；为空时自动设为可分配。异常状态不能通过 Excel 设置。'
      "
      :submitting="officeSpreadsheetSubmitting"
      target-label="资产"
      :title="`Excel 批量处理${subtypeLabel(subtypeFilter ?? '')}`"
      @submit="submitOfficeSpreadsheet"
    />

    <AssetImportModal
      v-if="!isMyAssets"
      ref="assetImportModalRef"
      :default-asset-subtype="subtypeFilter"
      :on-download-failed-file="downloadAssetImportFailedFile"
      :on-import="importAssetFile"
      :on-load-history="loadAssetImportHistory"
    />
    <AssetLifecycleDrawer
      v-model:open="lifecycleOpen"
      :account-id="lifecycleAccountId"
      :asset-subtype="lifecycleAssetSubtype"
      :detail="lifecycleDetail"
      :loading="lifecycleLoading"
      @application="openApplicationDetail"
    />
  </div>
</template>

<style scoped>
.asset-management-page {
  gap: var(--adpulse-page-section-gap, 16px);
}

.asset-management-page--neumorphic {
  --asset-surface: hsl(var(--card));
  --asset-surface-strong: hsl(var(--card));
  --asset-ink: hsl(var(--foreground));
  --asset-muted: hsl(var(--muted-foreground));
  --asset-line: hsl(var(--border));
  --asset-primary: hsl(var(--primary));
  --asset-primary-soft: hsl(var(--primary) / 10%);
  --asset-layer-shadow: var(--adpulse-card-shadow);
  color: var(--asset-ink);
}

.asset-management-page:not(.asset-management-page--neumorphic)
  .asset-category-option {
  min-height: 96px;
  padding: 16px;
  border-color: hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
}

.asset-management-page:not(.asset-management-page--neumorphic)
  .asset-category-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  font-size: 1.25rem;
}

.asset-management-page:not(.asset-management-page--neumorphic)
  .asset-category-option
  > span:last-child
  > strong {
  font-size: 1rem;
}

.asset-management-page:not(.asset-management-page--neumorphic)
  .asset-category-option
  > span:last-child
  > span {
  margin-top: 0.25rem;
  font-size: 0.875rem;
}

.asset-neumorphic-surface {
  border: 1px solid var(--asset-line);
  border-radius: var(--adpulse-card-radius);
  background: var(--asset-surface);
  box-shadow: var(--asset-layer-shadow);
}

.asset-page-header {
  min-height: var(--adpulse-page-header-min-height);
}

.asset-page-title {
  color: var(--asset-ink);
  letter-spacing: -0.02em;
}

.asset-page-description,
.asset-control-label {
  color: var(--asset-muted);
}

.asset-management-page--neumorphic .asset-category-rail {
  padding: 6px;
}

.asset-category-option {
  min-height: calc(var(--adpulse-control-height) + 14px);
  padding: 7px 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  transition:
    color 160ms ease,
    background-color 160ms ease,
    box-shadow 160ms ease,
    transform 160ms ease;
}

.asset-management-page--neumorphic .asset-category-option:hover {
  background: hsl(var(--muted) / 70%);
}

.asset-management-page--neumorphic .asset-category-option:active {
  transform: translateY(1px) scale(0.99);
}

.asset-category-option--active {
  color: var(--asset-primary);
  border-color: hsl(var(--primary) / 24%);
  background: var(--asset-primary-soft);
}

.asset-category-icon {
  width: calc(var(--adpulse-control-height) - 4px);
  height: calc(var(--adpulse-control-height) - 4px);
  border-radius: 9px;
}

.asset-management-page--neumorphic
  .asset-category-option--active
  .asset-category-icon {
  color: var(--asset-primary);
  background: hsl(var(--card) / 76%);
}

.asset-management-page--neumorphic .asset-control-surface,
.asset-management-page--neumorphic .asset-ledger-surface {
  padding: var(--adpulse-card-padding);
}

.asset-table-viewport {
  height: var(--asset-management-table-viewport-height);
  min-height: var(--asset-management-table-viewport-height);
  border: 1px solid var(--asset-line);
  border-radius: 10px;
  background: var(--asset-surface-strong);
}

.asset-management-table thead tr {
  height: var(--adpulse-table-header-height);
}

.asset-management-table tbody tr {
  height: var(--adpulse-table-row-height);
}

.asset-management-page--neumorphic .asset-management-table thead th,
.asset-management-page--neumorphic .asset-table-sticky-head {
  color: var(--asset-muted);
  background: hsl(var(--muted));
  border-color: var(--asset-line);
}

.asset-management-page--neumorphic .asset-table-row,
.asset-management-page--neumorphic .asset-table-sticky-cell {
  border-color: var(--asset-line);
  background: var(--asset-surface-strong);
}

.asset-management-page--neumorphic .asset-table-row:hover > td,
.asset-management-page--neumorphic
  .asset-table-row:hover
  > .asset-table-sticky-cell {
  background: var(--adpulse-table-row-hover);
}

.asset-ledger-pagination {
  padding-inline: 2px;
}

.asset-empty-surface {
  border-color: var(--asset-line);
  background: var(--asset-surface);
  box-shadow: var(--asset-layer-shadow);
}

.asset-management-page--neumorphic ::selection {
  color: var(--asset-ink);
  background: hsl(var(--primary) / 20%);
}

.asset-management-page--neumorphic * {
  scrollbar-color: hsl(var(--primary) / 42%) transparent;
  scrollbar-width: thin;
}

.asset-management-page--neumorphic *::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.asset-management-page--neumorphic *::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: hsl(var(--primary) / 42%);
  background-clip: padding-box;
}

/* 固定数据视口滚动时保留列标题，避免用户失去当前字段上下文。 */
.asset-management-table thead th {
  position: sticky;
  top: 0;
  z-index: 10;
  background: hsl(var(--muted));
}

.asset-management-table thead th:last-child {
  z-index: 30;
}

@media (max-width: 767px) {
  .asset-management-page--neumorphic .asset-page-header,
  .asset-management-page--neumorphic .asset-control-surface,
  .asset-management-page--neumorphic .asset-ledger-surface {
    padding: 12px;
  }

  .asset-management-page--neumorphic .asset-category-rail {
    gap: 4px;
  }

  .asset-category-option {
    min-height: 52px;
    padding-block: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .asset-category-option {
    transition: none;
  }
}
</style>
