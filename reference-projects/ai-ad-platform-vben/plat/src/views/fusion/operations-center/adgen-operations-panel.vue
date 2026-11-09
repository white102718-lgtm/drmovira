<script lang="ts" setup>
import type { CascaderProps, TableColumnsType } from 'ant-design-vue';

import type {
  AdgenByteplusAssetPreview,
  AdgenByteplusAssetRow,
  AdgenCredentialKey,
  AdgenCredentialPool,
  AdgenErrorRow,
  AdgenFeatureRoute,
  AdgenModelPayload,
  AdgenModelRow,
  AdgenOperationsSnapshot,
  AdgenProviderKey,
  AdgenProviderOverview,
  AdgenQuotaPayload,
  AdgenQuotaSummary,
  AdgenUsageCostBreakdown,
  AdgenUsageCostPeriod,
  AdgenUsageRankingPeriod,
  AdgenUsageRankingRow,
  AdgenUserQuota,
  AdgenVideoInputMode,
  OperationRecord,
} from '#/api';

import { computed, onMounted, reactive, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Card,
  Cascader,
  Checkbox,
  Collapse,
  Drawer,
  Form,
  FormItem,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Popover,
  Progress,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  message,
} from 'ant-design-vue';

import {
  AdgenAssetDeleteUncertainError,
  addAdgenCredentialApi,
  addAdgenKlingCredentialApi,
  deleteAdgenByteplusAssetApi,
  deleteAdgenCredentialApi,
  deleteAdgenModelApi,
  getAdgenOperationsSnapshotApi,
  getAdgenByteplusAssetPreviewApi,
  getAdgenQuotaStatusApi,
  getAdgenQuotaSettingsApi,
  getAdgenUsageCostBreakdownApi,
  getAdgenUsageRankingApi,
  listAdgenByteplusAssetsApi,
  reconcileAdgenByteplusAssetsApi,
  resetAdgenCredentialPoolApi,
  saveAdgenFeatureRouteApi,
  saveAdgenModelApi,
  saveAdgenSystemQuotaApi,
  saveAdgenUserQuotaBatchApi,
  syncAdgenModelsApi,
} from '#/api';
import { OFFICIAL_ASSET_LIBRARY_ENABLED } from '#/embedded/adgen-canvas/officialAssetLibrary';

type ProviderKey = AdgenProviderKey;
type ProviderOverview = AdgenProviderOverview;
type ModelRow = AdgenModelRow;
type FeatureRoute = AdgenFeatureRoute;
type CredentialKey = AdgenCredentialKey;
type CredentialPool = AdgenCredentialPool;
type UsageRankingRow = AdgenUsageRankingRow;
type ErrorRow = AdgenErrorRow;

const props = defineProps<{
  loading: boolean;
  records: OperationRecord[];
}>();

const emit = defineEmits<{
  action: [record: OperationRecord];
  inspect: [record: OperationRecord];
  refresh: [];
}>();

const providerOptions = [
  { label: '全部服务商', value: 'all' },
  { label: 'Gemini', value: 'gemini' },
  { label: '百炼', value: 'bailian' },
  { label: 'BytePlus（新加坡）', value: 'byteplus' },
  { label: '可灵', value: 'kling' },
  { label: 'OpenAI', value: 'openai' },
  { label: '千问', value: 'qwen' },
];

function emptyProviderOverview(): ProviderOverview {
  return {
    calls: '0',
    chart: [0, 0, 0, 0, 0, 0, 0],
    cost: 'US$ 0.00',
    latency: '暂无数据',
    success: '0.0%',
  };
}

const providerStats = reactive<Record<ProviderKey, ProviderOverview>>({
  all: emptyProviderOverview(),
  bailian: emptyProviderOverview(),
  byteplus: emptyProviderOverview(),
  gemini: emptyProviderOverview(),
  kling: emptyProviderOverview(),
  openai: emptyProviderOverview(),
  qwen: emptyProviderOverview(),
});
const modelStats = reactive<Record<string, ProviderOverview>>({});

const selectedProvider = ref<ProviderKey>('all');
const selectedModel = ref('all');
const selectedApplicationType = ref('all');
const selectedModelPath = ref<string[]>([]);
const selectedPeriod = ref('7');
const backendLoading = ref(false);
const activeTab = ref('models');
const modelSearch = ref('');
const modelHealth = ref('all');
const activeRouteKey = ref('image');
const activePoolId = ref('gemini-image-prod');
const newCredential = ref('');
const klingApiKey = ref('');
const credentialResetting = ref(false);
const modelDrawerOpen = ref(false);
const syncDrawerOpen = ref(false);
const syncProvider = ref<Exclude<ProviderKey, 'all'>>('byteplus');
const syncingModels = ref(false);
const editingModelId = ref<string>();
const deletingModelId = ref<string>();
const usageRankingPeriod = ref<AdgenUsageRankingPeriod>('today');
const usageRankingSearch = ref('');
const usageRankingLoading = ref(false);
const quotaLoading = ref(false);
const quotaSaving = ref(false);
const quotaDrawerOpen = ref(false);
const quotaManagerTab = ref('system');
const selectedQuotaUserIds = ref<string[]>([]);
const usageCostPeriod = ref<AdgenUsageCostPeriod>('today');
const usageCostLoading = ref(false);
let usageCostRequestId = 0;

const usageCostPeriodOptions = [
  { label: '今日', value: 'today' },
  { label: '昨日', value: 'yesterday' },
  { label: '本周', value: 'this_week' },
  { label: '上周', value: 'last_week' },
  { label: '本月', value: 'this_month' },
  { label: '上月', value: 'last_month' },
  { label: '本年', value: 'this_year' },
] satisfies { label: string; value: AdgenUsageCostPeriod }[];

const usageRankingPeriodOptions = [
  { label: '当天', value: 'today' },
  { label: '昨天', value: 'yesterday' },
  { label: '本周内', value: 'week' },
  { label: '本月', value: 'month' },
  { label: '年度', value: 'year' },
] satisfies { label: string; value: AdgenUsageRankingPeriod }[];

function emptyQuotaSummary(): AdgenQuotaSummary {
  const emptyMetric = { limit: null, percent: 0, used: 0 };
  return {
    daily: { ...emptyMetric },
    monthly: { ...emptyMetric },
    users: [],
    weekly: { ...emptyMetric },
  };
}

const usageCostBreakdown = ref<AdgenUsageCostBreakdown>({
  currencies: [],
  endAt: '',
  label: '今日',
  period: 'today',
  providers: [],
  startAt: '',
  totalUsd: 0,
});
const quotaSettings = ref<AdgenQuotaSummary>(emptyQuotaSummary());
const systemQuotaForm = reactive<AdgenQuotaPayload>({
  dailyLimit: null,
  monthlyLimit: null,
  weeklyLimit: null,
});
const userQuotaForm = reactive<AdgenQuotaPayload>({
  dailyLimit: null,
  monthlyLimit: null,
  weeklyLimit: null,
});

const overview = computed(() =>
  selectedModel.value !== 'all'
    ? (modelStats[selectedModel.value] ?? emptyProviderOverview())
    : providerStats[selectedProvider.value],
);
const quotaUserOptions = computed(() =>
  quotaSettings.value.users.map((user) => ({
    label: user.department
      ? `${user.displayName}（${user.department}）`
      : user.displayName,
    value: user.userId,
  })),
);
const selectedQuotaUsers = computed(() =>
  quotaSettings.value.users.filter((user) =>
    selectedQuotaUserIds.value.includes(user.userId),
  ),
);

const usageCostQuota = computed(() => {
  const period = usageCostPeriod.value;
  const metric =
    period === 'today' || period === 'yesterday'
      ? quotaSettings.value.daily
      : period === 'this_week' || period === 'last_week'
        ? quotaSettings.value.weekly
        : period === 'this_month' || period === 'last_month'
          ? quotaSettings.value.monthly
          : undefined;
  const limit = metric?.limit ?? null;
  const percent = limit ? (usageCostBreakdown.value.totalUsd / limit) * 100 : 0;
  return {
    limit,
    percent: Math.min(Math.max(percent, 0), 100),
  };
});

function formatUsd(value: number) {
  return `US$ ${value.toFixed(4)}`;
}

function formatNativeCost(value: number, currency: string) {
  const amount = value.toLocaleString('zh-CN', {
    maximumFractionDigits: 4,
    minimumFractionDigits: 2,
  });
  if (currency === 'USD') return `US$ ${amount}`;
  if (currency === 'CNY') return `¥ ${amount}`;
  return `${currency} ${amount}`;
}

function formatUsageCount(value: number) {
  return value.toLocaleString('zh-CN');
}

const modelCascadeOptions = computed<CascaderProps['options']>(() => [
  { label: '全部', value: 'all' },
  ...providerOptions
    .filter((provider) => provider.value !== 'all')
    .map((provider) => {
      const providerModels = models.value.filter(
        (model) => model.provider === provider.label && model.usageTracked,
      );
      const applicationTypes = [
        ...new Set(providerModels.map((model) => model.type)),
      ];
      return {
        children: applicationTypes.map((applicationType) => ({
          children: providerModels
            .filter((model) => model.type === applicationType)
            .map((model) => ({ label: model.name, value: model.modelId })),
          label: applicationType,
          value: applicationType,
        })),
        label: provider.label,
        value: provider.value,
      };
    })
    .filter((provider) => provider.children.length > 0),
]);
const healthyResourceCount = computed(
  () => props.records.filter((record) => record.health === 'healthy').length,
);

watch(selectedModelPath, (path) => {
  selectedProvider.value = (path[0] as ProviderKey | undefined) ?? 'all';
  selectedApplicationType.value = path[1] ?? 'all';
  selectedModel.value = path[2] ?? 'all';
});

const models = ref<ModelRow[]>([]);

const filteredModels = computed(() => {
  const query = modelSearch.value.trim().toLowerCase();
  const providerLabel = providerOptions.find(
    (option) => option.value === selectedProvider.value,
  )?.label;
  return models.value.filter((item) => {
    const providerMatches =
      selectedProvider.value === 'all' || item.provider === providerLabel;
    const modelMatches =
      selectedModel.value === 'all' || item.modelId === selectedModel.value;
    const applicationTypeMatches =
      selectedApplicationType.value === 'all' ||
      item.type === selectedApplicationType.value;
    const healthMatches =
      modelHealth.value === 'all' || item.health === modelHealth.value;
    const queryMatches =
      !query ||
      `${item.name}${item.modelId}${item.provider}${item.type}`
        .toLowerCase()
        .includes(query);
    return (
      providerMatches &&
      modelMatches &&
      applicationTypeMatches &&
      healthMatches &&
      queryMatches
    );
  });
});

const syncProviderOptions = providerOptions.slice(1) as Array<{
  label: string;
  value: Exclude<ProviderKey, 'all'>;
}>;

function modelCapabilityTags(model: ModelRow | AdgenModelPayload): string[] {
  const row = model as ModelRow;
  if (row.capabilityTags?.length) return row.capabilityTags;
  const tags = [...(model.supportedResolutions || [])];
  if (model.supportsImageEdit) tags.push('参考图编辑');
  const inputLabels: Record<AdgenVideoInputMode, string> = {
    first_frame: '图生视频',
    first_last_frame: '首尾帧',
    reference_assets: '参考素材',
    text_to_video: '文生视频',
  };
  for (const mode of model.supportedInputModes || []) {
    tags.push(inputLabels[mode]);
  }
  if (
    model.durationParameterEnabled &&
    model.minDurationSeconds &&
    model.maxDurationSeconds
  ) {
    tags.push(`${model.minDurationSeconds}-${model.maxDurationSeconds} 秒`);
  }
  if (model.supportsNativeAudio) tags.push('原生音频');
  if (model.supportsMultiShot) tags.push('多镜头');
  return [...new Set(tags)];
}

const modelColumns: TableColumnsType<ModelRow> = [
  { key: 'name', title: '模型', width: 240 },
  { dataIndex: 'provider', key: 'provider', title: '服务商', width: 140 },
  { dataIndex: 'type', key: 'type', title: '类型', width: 100 },
  { key: 'capabilities', title: '能力', width: 280 },
  { key: 'health', title: '状态', width: 88 },
  { dataIndex: 'calls', key: 'calls', title: '所选范围调用', width: 130 },
  { fixed: 'right', key: 'action', title: '操作', width: 180 },
];

const featureRoutes = reactive<FeatureRoute[]>([
  {
    category: '图片生成',
    defaultModel: 'Nano Banana 2 正式版',
    featureKey: 'workspace_image',
    key: 'image',
    limit: 10,
    limitField: 'max_batch_count',
    limitLabel: '最大批量数',
    models: [
      { enabled: true, id: 'gemini-2.5-flash-image', name: 'Nano Banana' },
      {
        enabled: true,
        id: 'gemini-3-pro-image',
        name: 'Nano Banana Pro 正式版',
      },
      {
        enabled: false,
        id: 'gemini-3-pro-image-preview',
        name: 'Nano Banana Pro Preview',
      },
      {
        enabled: true,
        id: 'gemini-3.1-flash-image',
        name: 'Nano Banana 2 正式版',
      },
      { enabled: false, id: 'wan2.7-image-pro', name: '万相 2.7 Image Pro' },
    ],
    name: '画布图片',
    resolution: '1K',
    resolutions: ['1K', '2K', '4K'],
  },
  {
    category: '视频生成',
    defaultModel: 'Veo 3.1 Fast',
    featureKey: 'workspace_video',
    key: 'video',
    limit: 20,
    limitField: 'max_extension_count',
    limitLabel: '最大延长次数',
    models: [
      { enabled: false, id: 'happyhorse-1.0-i2v', name: 'HappyHorse 图生视频' },
      {
        enabled: true,
        id: 'veo-3.1-fast-generate-preview',
        name: 'Veo 3.1 Fast',
      },
      { enabled: true, id: 'veo-3.1-generate-preview', name: 'Veo 3.1 标准' },
      { enabled: false, id: 'wan2.7-i2v', name: '万相 2.7 图生视频' },
    ],
    name: '画布视频',
    resolution: '720p',
    resolutions: ['720p', '1080p'],
  },
  {
    category: '对话模型',
    defaultModel: 'Qwen VL Plus',
    featureKey: 'workspace_chat',
    key: 'chat',
    limit: 28,
    limitField: 'max_context_messages',
    limitLabel: '最大上下文消息数',
    models: [
      { enabled: true, id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash' },
      { enabled: true, id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro' },
      { enabled: true, id: 'qwen-vl-plus', name: 'Qwen VL Plus' },
      { enabled: true, id: 'qwen-vl-max', name: 'Qwen VL Max' },
      { enabled: true, id: 'qwen-plus', name: 'Qwen Plus' },
      { enabled: true, id: 'qwen-max', name: 'Qwen Max' },
    ],
    name: '画布对话',
  },
  {
    category: '音乐生成',
    defaultModel: 'Lyria 3 Clip',
    featureKey: 'workspace_music',
    key: 'music',
    limit: 11,
    limitField: 'max_batch_count',
    limitLabel: '最大批量数',
    models: [
      { enabled: true, id: 'lyria-3-clip-preview', name: 'Lyria 3 Clip' },
      { enabled: true, id: 'lyria-3-pro-preview', name: 'Lyria 3 Pro' },
      { enabled: false, id: 'musicgen-pro', name: 'MusicGen Pro' },
    ],
    name: '画布音乐',
  },
  {
    category: '语音生成',
    defaultModel: 'Gemini 2.5 Flash TTS Preview',
    featureKey: 'workspace_tts',
    key: 'tts',
    limit: 10,
    limitField: 'max_batch_count',
    limitLabel: '最大批量数',
    models: [
      {
        enabled: true,
        id: 'gemini-2.5-flash-preview-tts',
        name: 'Gemini 2.5 Flash TTS Preview',
      },
      {
        enabled: true,
        id: 'gemini-2.5-pro-preview-tts',
        name: 'Gemini 2.5 Pro TTS Preview',
      },
      { enabled: false, id: 'openai-tts-1', name: 'OpenAI TTS' },
    ],
    name: '画布 TTS',
  },
]);

const activeRoute = computed(
  () =>
    featureRoutes.find((route) => route.key === activeRouteKey.value) ??
    featureRoutes[0]!,
);

const credentialPools = reactive<CredentialPool[]>([
  {
    available: 7,
    environment: '生产 / 国内',
    id: 'gemini-image-prod',
    keys: [],
    name: 'gemini-image-prod',
    provider: 'Gemini',
    quota: 68,
    serviceType: 'gemini',
    total: 8,
  },
  {
    available: 5,
    environment: '生产 / 国内',
    id: 'bailian-video-prod',
    keys: [],
    name: 'bailian-video-prod',
    provider: '百炼',
    quota: 42,
    serviceType: 'bailian',
    total: 5,
  },
  {
    available: 3,
    environment: '新加坡 / ap-southeast-1',
    id: 'byteplus-singapore',
    keys: [],
    name: 'byteplus-singapore',
    provider: 'BytePlus（新加坡）',
    quota: 81,
    serviceType: 'byteplus',
    total: 3,
  },
  {
    available: 2,
    environment: '生产 / 海外',
    id: 'openai-global',
    keys: [],
    name: 'openai-global',
    provider: 'OpenAI',
    quota: 74,
    serviceType: 'openai',
    total: 2,
  },
  {
    available: 0,
    environment: '本地 / MongoDB',
    id: 'kling-video-prod',
    keys: [],
    name: 'kling-video-prod',
    provider: '可灵',
    quota: 0,
    serviceType: 'kling',
    total: 0,
  },
]);

const credentialKeys = reactive<Record<string, CredentialKey[]>>({
  'bailian-video-prod': [
    {
      errorCount: 0,
      id: 'bailian-video-01',
      masked: 'sk_19bc2•••f181',
      status: 'healthy',
      usage: 42,
    },
    {
      errorCount: 1,
      id: 'bailian-video-02',
      masked: 'sk_81aa0•••c722',
      status: 'warning',
      usage: 36,
    },
  ],
  'gemini-image-prod': [
    {
      errorCount: 0,
      id: 'gemini-img-01',
      masked: 'gk_8729a•••ad60',
      status: 'healthy',
      usage: 77,
    },
    {
      errorCount: 0,
      id: 'gemini-img-02',
      masked: 'gk_a1194•••6b74',
      status: 'healthy',
      usage: 78,
    },
    {
      errorCount: 0,
      id: 'gemini-img-03',
      masked: 'gk_274b7•••bfeb',
      status: 'healthy',
      usage: 78,
    },
    {
      errorCount: 0,
      id: 'gemini-img-04',
      masked: 'gk_52e22•••ba97',
      status: 'healthy',
      usage: 77,
    },
  ],
  'openai-global': [
    {
      errorCount: 0,
      id: 'openai-global-01',
      masked: 'sk_91f00•••711a',
      status: 'healthy',
      usage: 28,
    },
    {
      errorCount: 0,
      id: 'openai-global-02',
      masked: 'sk_b703a•••c225',
      status: 'healthy',
      usage: 24,
    },
  ],
  'byteplus-singapore': [
    {
      errorCount: 0,
      id: 'volc-backup-01',
      masked: 'ak_e8420•••931a',
      status: 'healthy',
      usage: 18,
    },
    {
      errorCount: 0,
      id: 'volc-backup-02',
      masked: 'ak_6a310•••e204',
      status: 'healthy',
      usage: 16,
    },
  ],
});

const activePool = computed(
  () =>
    credentialPools.find((pool) => pool.id === activePoolId.value) ??
    credentialPools[0]!,
);
const activePoolKeys = computed(
  () => credentialKeys[activePool.value.id] ?? [],
);

const usageRankingRows = ref<UsageRankingRow[]>([]);
const filteredUsageRankingRows = computed(() => {
  const keyword = usageRankingSearch.value.trim().toLowerCase();
  if (!keyword) return usageRankingRows.value;
  return usageRankingRows.value.filter((row) =>
    [row.displayName, row.nickname, row.userId, row.username].some((value) =>
      value.toLowerCase().includes(keyword),
    ),
  );
});

const usageRankingColumns: TableColumnsType<UsageRankingRow> = [
  { dataIndex: 'rank', key: 'rank', title: '排名', width: 90 },
  {
    dataIndex: 'displayName',
    key: 'displayName',
    title: 'AdPulse 用户',
    width: 240,
  },
  { dataIndex: 'calls', key: 'calls', title: '调用次数', width: 140 },
  { dataIndex: 'share', key: 'share', title: '调用占比', width: 180 },
  { dataIndex: 'cost', key: 'cost', title: '预估成本', width: 160 },
];

const backendErrorRows = ref<ErrorRow[]>([]);
const errorRows = computed<ErrorRow[]>(() => {
  if (backendErrorRows.value.length > 0) return backendErrorRows.value;
  const actualErrors = props.records
    .filter((record) => record.category === '错误日志')
    .map((record) => ({
      action: record.health === 'offline' ? '重试' : '详情',
      deployment: record.name,
      id: record.id,
      requestId: `req_•••${record.id.slice(-4)}`,
      status: record.status,
      time: record.updatedAt,
      type: record.metric,
    }));
  return actualErrors;
});

const errorColumns: TableColumnsType<ErrorRow> = [
  { dataIndex: 'time', key: 'time', title: '时间', width: 170 },
  { dataIndex: 'deployment', key: 'deployment', title: '模型部署', width: 250 },
  { dataIndex: 'type', key: 'type', title: '错误类型', width: 160 },
  { dataIndex: 'requestId', key: 'requestId', title: '请求 ID', width: 150 },
  { key: 'status', title: '处理状态', width: 110 },
  { key: 'action', title: '操作', width: 100 },
];

function applySnapshot(snapshot: AdgenOperationsSnapshot) {
  Object.assign(providerStats, snapshot.providerStats);
  for (const modelId of Object.keys(modelStats)) delete modelStats[modelId];
  Object.assign(modelStats, snapshot.modelStats);
  models.value = snapshot.models;
  featureRoutes.splice(0, featureRoutes.length, ...snapshot.featureRoutes);
  credentialPools.splice(
    0,
    credentialPools.length,
    ...snapshot.credentialPools,
  );
  for (const poolId of Object.keys(credentialKeys)) {
    delete credentialKeys[poolId];
  }
  for (const pool of snapshot.credentialPools) {
    credentialKeys[pool.id] = pool.keys;
  }
  backendErrorRows.value = snapshot.errorRows;

  if (!featureRoutes.some((route) => route.key === activeRouteKey.value)) {
    activeRouteKey.value = featureRoutes[0]?.key ?? 'image';
  }
  if (!credentialPools.some((pool) => pool.id === activePoolId.value)) {
    activePoolId.value = credentialPools[0]?.id ?? '';
  }
}

async function refreshOperations(notifyParent = true) {
  backendLoading.value = true;
  try {
    applySnapshot(
      await getAdgenOperationsSnapshotApi(
        selectedPeriod.value === 'all' ? 'all' : Number(selectedPeriod.value),
      ),
    );
    if (notifyParent) emit('refresh');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '运维数据加载失败');
  } finally {
    backendLoading.value = false;
  }
}

async function loadUsageRanking() {
  usageRankingLoading.value = true;
  try {
    const ranking = await getAdgenUsageRankingApi(usageRankingPeriod.value);
    usageRankingRows.value = ranking.rows;
  } catch (error) {
    usageRankingRows.value = [];
    message.error(error instanceof Error ? error.message : '用量排行加载失败');
  } finally {
    usageRankingLoading.value = false;
  }
}

async function loadUsageCostBreakdown() {
  const requestId = ++usageCostRequestId;
  usageCostLoading.value = true;
  try {
    const result = await getAdgenUsageCostBreakdownApi(usageCostPeriod.value);
    if (requestId === usageCostRequestId) usageCostBreakdown.value = result;
  } catch (error) {
    if (requestId !== usageCostRequestId) return;
    usageCostBreakdown.value = {
      currencies: [],
      endAt: '',
      label:
        usageCostPeriodOptions.find(
          (option) => option.value === usageCostPeriod.value,
        )?.label ?? '',
      period: usageCostPeriod.value,
      providers: [],
      startAt: '',
      totalUsd: 0,
    };
    message.error(error instanceof Error ? error.message : '模型用量加载失败');
  } finally {
    if (requestId === usageCostRequestId) usageCostLoading.value = false;
  }
}

async function loadQuotaStatus() {
  quotaLoading.value = true;
  try {
    quotaSettings.value = await getAdgenQuotaStatusApi();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '系统配额加载失败');
  } finally {
    quotaLoading.value = false;
  }
}

function applySystemQuotaForm(summary: AdgenQuotaSummary) {
  Object.assign(systemQuotaForm, {
    dailyLimit: summary.daily.limit,
    monthlyLimit: summary.monthly.limit,
    weeklyLimit: summary.weekly.limit,
  });
}

function applyUserQuotaForm(user?: AdgenUserQuota) {
  Object.assign(userQuotaForm, {
    dailyLimit: user?.dailyLimit ?? null,
    monthlyLimit: user?.monthlyLimit ?? null,
    weeklyLimit: user?.weeklyLimit ?? null,
  });
}

function applySelectedQuotaUsersForm(users = selectedQuotaUsers.value) {
  // 多选时由管理员填写一组新配额，并统一覆盖到所选人员；避免把任一
  // 单个人的旧值误显示为所有人的当前设置。
  if (users.length === 1) {
    applyUserQuotaForm(users[0]);
    return;
  }
  applyUserQuotaForm();
}

async function loadQuotaSettings() {
  quotaLoading.value = true;
  try {
    quotaSettings.value = await getAdgenQuotaSettingsApi();
    applySystemQuotaForm(quotaSettings.value);
    selectedQuotaUserIds.value = selectedQuotaUserIds.value.filter((userId) =>
      quotaSettings.value.users.some((user) => user.userId === userId),
    );
    if (selectedQuotaUserIds.value.length === 0) {
      selectedQuotaUserIds.value = quotaSettings.value.users[0]?.userId
        ? [quotaSettings.value.users[0].userId]
        : [];
    }
    applySelectedQuotaUsersForm();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '配额配置加载失败');
  } finally {
    quotaLoading.value = false;
  }
}

async function openQuotaManager() {
  quotaDrawerOpen.value = true;
  await loadQuotaSettings();
}

async function saveSystemQuota() {
  quotaSaving.value = true;
  try {
    await saveAdgenSystemQuotaApi({ ...systemQuotaForm });
    await loadQuotaSettings();
    message.success('系统配额已保存');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '系统配额保存失败');
  } finally {
    quotaSaving.value = false;
  }
}

async function saveUserQuota() {
  if (selectedQuotaUsers.value.length === 0) {
    message.warning('请先选择人员');
    return;
  }
  quotaSaving.value = true;
  try {
    const users = selectedQuotaUsers.value;
    await saveAdgenUserQuotaBatchApi(
      users.map((user) => user.userId),
      {
        ...userQuotaForm,
        displayNames: Object.fromEntries(
          users.map((user) => [user.userId, user.displayName]),
        ),
      },
    );
    await loadQuotaSettings();
    message.success(`已保存 ${users.length} 人的个人配额`);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '个人配额保存失败');
  } finally {
    quotaSaving.value = false;
  }
}

async function refreshDashboard() {
  await Promise.all([
    refreshOperations(),
    loadQuotaStatus(),
    loadUsageCostBreakdown(),
    loadUsageRanking(),
  ]);
}

// Do not render reference-preview metrics while the local backend snapshot is
// loading. Feature routes remain as safe form defaults until real data arrives.
models.value = [];
for (const pool of credentialPools) {
  pool.available = 0;
  pool.total = 0;
  pool.quota = 0;
  pool.environment = '等待本地后端';
}
for (const poolId of Object.keys(credentialKeys)) {
  delete credentialKeys[poolId];
}

const byteplusAssets = ref<AdgenByteplusAssetRow[]>([]);
const byteplusAssetUsed = ref(0);
const byteplusAssetLimit = ref(50);
const byteplusAssetConfigured = ref(true);
const byteplusAssetLoading = ref(false);
const byteplusAssetReconciling = ref(false);
const byteplusAssetOfficialCount = ref<null | number>(null);
const byteplusAssetLocalCount = ref(0);
const byteplusAssetScope = ref('');
const byteplusAssetCheckedAt = ref<null | string>(null);
const byteplusAssociationLabels = {
  Linked: '已关联',
  Missing: '官方缺失',
  Unlinked: '未关联',
};
const deletingByteplusAssetId = ref<string>();
const selectedByteplusAssetIds = ref<string[]>([]);
const batchDeletingByteplusAssets = ref(false);
const byteplusBatchProgress = ref(0);
const byteplusBatchTotal = ref(0);
const byteplusAssetBusy = computed(
  () =>
    byteplusAssetLoading.value ||
    batchDeletingByteplusAssets.value ||
    Boolean(deletingByteplusAssetId.value),
);
const byteplusAssetRowSelection = computed(() => ({
  selectedRowKeys: selectedByteplusAssetIds.value,
  onChange: (keys: (number | string)[]) => {
    selectedByteplusAssetIds.value = keys.map(String);
  },
  getCheckboxProps: () => ({ disabled: byteplusAssetBusy.value }),
}));
const byteplusAssetKeyword = ref('');
const byteplusAssetTypeFilter = ref<string>();
const byteplusAssetStatusFilter = ref<string>();
const byteplusAssetAssociationFilter = ref<string>();
const byteplusAssetTypeOptions = [
  { label: '图片（Image）', value: 'Image' },
  { label: '视频（Video）', value: 'Video' },
  { label: '音频（Audio）', value: 'Audio' },
];
const byteplusAssetStatusOptions = [
  { label: '可用（Active）', value: 'Active' },
  { label: '处理中（Processing）', value: 'Processing' },
  { label: '失败（Failed）', value: 'Failed' },
  { label: '无官方状态（—）', value: '__none__' },
];
const byteplusAssetAssociationOptions = Object.entries(
  byteplusAssociationLabels,
).map(([value, label]) => ({ value, label: `${label}（${value}）` }));
/** 各条件取交集，关键词对三个字段做不区分大小写的包含匹配。 */
const filteredByteplusAssets = computed(() => {
  const keyword = byteplusAssetKeyword.value.trim().toLowerCase();
  return byteplusAssets.value.filter(
    (asset) =>
      (!keyword ||
        [asset.name, asset.groupId, asset.id].some((value) =>
          (value || '').toLowerCase().includes(keyword),
        )) &&
      (!byteplusAssetTypeFilter.value ||
        asset.assetType === byteplusAssetTypeFilter.value) &&
      (!byteplusAssetStatusFilter.value ||
        (asset.status || '__none__') === byteplusAssetStatusFilter.value) &&
      (!byteplusAssetAssociationFilter.value ||
        asset.associationStatus === byteplusAssetAssociationFilter.value),
  );
});
// 隐藏的行不保留勾选，避免筛选后批量删除看不到的素材。
watch(
  filteredByteplusAssets,
  (assets) => {
    const visibleIds = new Set(assets.map((asset) => asset.id));
    selectedByteplusAssetIds.value = selectedByteplusAssetIds.value.filter(
      (id) => visibleIds.has(id),
    );
  },
  { flush: 'sync' },
);

function resetByteplusAssetFilters() {
  byteplusAssetKeyword.value = '';
  byteplusAssetTypeFilter.value = undefined;
  byteplusAssetStatusFilter.value = undefined;
  byteplusAssetAssociationFilter.value = undefined;
}

const byteplusAssetPreview = ref<AdgenByteplusAssetPreview>();
const byteplusAssetPreviewError = ref('');
const byteplusAssetPreviewLoading = ref(false);
const byteplusAssetPreviewOpen = ref(false);

const byteplusAssetColumns: TableColumnsType<AdgenByteplusAssetRow> = [
  { dataIndex: 'name', key: 'name', title: '名称' },
  { dataIndex: 'assetType', key: 'assetType', title: '类型', width: 100 },
  { dataIndex: 'status', key: 'status', title: '官方状态', width: 110 },
  {
    dataIndex: 'associationStatus',
    key: 'associationStatus',
    title: '关联状态',
    width: 130,
  },
  { dataIndex: 'groupId', key: 'groupId', title: '素材组 ID', width: 240 },
  { dataIndex: 'id', key: 'id', title: '素材 ID', width: 240 },
  { key: 'action', title: '操作', width: 140 },
];

async function loadByteplusAssets(reconcile = false) {
  if (byteplusAssetBusy.value) return;
  byteplusAssetReconciling.value = reconcile;
  byteplusAssetLoading.value = true;
  try {
    const data = await (reconcile
      ? reconcileAdgenByteplusAssetsApi()
      : listAdgenByteplusAssetsApi());
    byteplusAssetOfficialCount.value = data.officialCount;
    byteplusAssetLocalCount.value = data.localCount;
    byteplusAssetScope.value = data.scope;
    byteplusAssetCheckedAt.value = data.checkedAt;
    if (reconcile) message.success('官方素材核对完成，未关联素材已导入');
    byteplusAssets.value = data.items;
    selectedByteplusAssetIds.value = selectedByteplusAssetIds.value.filter(
      (id) => data.items.some((item) => item.id === id),
    );
    byteplusAssetUsed.value = data.used;
    byteplusAssetLimit.value = data.limit;
    byteplusAssetConfigured.value = data.configured;
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '加载官方素材库失败',
    );
  } finally {
    byteplusAssetLoading.value = false;
    byteplusAssetReconciling.value = false;
  }
}

async function removeByteplusAsset(assetId: string) {
  if (byteplusAssetBusy.value) return;
  deletingByteplusAssetId.value = assetId;
  try {
    const occupancy = await deleteAdgenByteplusAssetApi(assetId);
    byteplusAssetUsed.value = occupancy.used;
    byteplusAssetLimit.value = occupancy.limit;
    byteplusAssets.value = byteplusAssets.value.filter(
      (item) => item.id !== assetId,
    );
    byteplusAssetLocalCount.value = byteplusAssets.value.length;
    selectedByteplusAssetIds.value = selectedByteplusAssetIds.value.filter(
      (id) => id !== assetId,
    );
    message.success('素材记录已删除');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '删除失败');
  } finally {
    deletingByteplusAssetId.value = undefined;
  }
}

/** 逐条删除以遵守官方限流，失败项保留勾选方便重试。 */
async function removeSelectedByteplusAssets() {
  if (byteplusAssetBusy.value || selectedByteplusAssetIds.value.length === 0)
    return;
  const assetIds = [...selectedByteplusAssetIds.value];
  const failures: { id: string; reason: string }[] = [];
  batchDeletingByteplusAssets.value = true;
  byteplusBatchProgress.value = 0;
  byteplusBatchTotal.value = assetIds.length;
  try {
    for (const assetId of assetIds) {
      try {
        // 复用单条删除接口，服务端仍检查生成租约并保留恢复映射。
        const occupancy = await deleteAdgenByteplusAssetApi(assetId);
        byteplusAssetUsed.value = occupancy.used;
        byteplusAssetLimit.value = occupancy.limit;
        byteplusAssets.value = byteplusAssets.value.filter(
          (item) => item.id !== assetId,
        );
        selectedByteplusAssetIds.value = selectedByteplusAssetIds.value.filter(
          (id) => id !== assetId,
        );
        byteplusAssetLocalCount.value = byteplusAssets.value.length;
      } catch (error) {
        failures.push({
          id: assetId,
          reason: error instanceof Error ? error.message : '删除失败',
        });
        if (error instanceof AdgenAssetDeleteUncertainError) break;
      } finally {
        byteplusBatchProgress.value += 1;
      }
    }
    const succeeded = byteplusBatchProgress.value - failures.length;
    const pending = assetIds.length - byteplusBatchProgress.value;
    if (failures.length > 0) {
      Modal.warning({
        title: `批量删除结果：成功 ${succeeded} 条，失败或未确认 ${failures.length} 条，未执行 ${pending} 条`,
        content: failures
          .map((item) => `${item.id}：${item.reason}`)
          .join('；'),
        width: 640,
      });
    } else {
      message.success(`已删除 ${succeeded} 条素材记录`);
    }
  } finally {
    batchDeletingByteplusAssets.value = false;
  }
}

async function openByteplusAssetPreview(record: AdgenByteplusAssetRow) {
  const assetId = String(record.id || '');
  if (!assetId) {
    message.error('缺少素材 ID，无法预览');
    return;
  }
  byteplusAssetPreview.value = undefined;
  byteplusAssetPreviewError.value = '';
  byteplusAssetPreviewLoading.value = true;
  byteplusAssetPreviewOpen.value = true;
  try {
    byteplusAssetPreview.value = await getAdgenByteplusAssetPreviewApi(assetId);
  } catch (error) {
    byteplusAssetPreviewError.value =
      error instanceof Error ? error.message : '加载关联素材失败';
  } finally {
    byteplusAssetPreviewLoading.value = false;
  }
}

watch(activeTab, (tab) => {
  if (OFFICIAL_ASSET_LIBRARY_ENABLED && tab === 'byteplus-assets') {
    void loadByteplusAssets();
  }
});

onMounted(() => {
  void Promise.all([
    refreshOperations(false),
    loadQuotaStatus(),
    loadUsageCostBreakdown(),
    loadUsageRanking(),
  ]);
});
watch(selectedPeriod, () => refreshOperations(false));
watch(usageRankingPeriod, loadUsageRanking);
watch(usageCostPeriod, loadUsageCostBreakdown);
watch(selectedQuotaUserIds, () => {
  applySelectedQuotaUsersForm();
});

const modelTypeOptions = [
  '图片生成',
  '视频生成',
  '视频编辑',
  'TTS',
  '音乐生成',
  '对话模型',
].map((item) => ({ label: item, value: item }));
const videoInputModeOptions = [
  { label: '文生视频', value: 'text_to_video' },
  { label: '首帧图生视频', value: 'first_frame' },
  { label: '首尾帧图生视频', value: 'first_last_frame' },
  { label: '参考图 / 视频素材', value: 'reference_assets' },
] satisfies { label: string; value: AdgenVideoInputMode }[];
const imageResolutionOptions = ['1K', '2K', '3K', '4K'].map((value) => ({
  label: value,
  value,
}));
const videoResolutionOptions = ['480p', '720p', '1080p', '4k'].map((value) => ({
  label: value,
  value,
}));
const aspectRatioOptions = [
  '1:1',
  '16:9',
  '9:16',
  '4:3',
  '3:4',
  '3:2',
  '2:3',
  '21:9',
  'adaptive',
].map((value) => ({ label: value, value }));

function createEmptyModelForm(): AdgenModelPayload {
  return {
    defaultDurationSeconds: undefined,
    description: '',
    durationParameterEnabled: false,
    extensionMode: 'none',
    maxDurationSeconds: undefined,
    minDurationSeconds: undefined,
    modelId: '',
    name: '',
    provider: 'Gemini',
    supportedAspectRatios: ['1:1', '16:9', '9:16'],
    supportedInputModes: [],
    supportedResolutions: ['1K'],
    supportsExtension: false,
    supportsImageEdit: true,
    supportsMultiShot: false,
    supportsNativeAudio: false,
    type: '图片生成',
  };
}

const modelForm = reactive<AdgenModelPayload>(createEmptyModelForm());
const isImageModel = computed(() => modelForm.type === '图片生成');
const isVideoModel = computed(() => modelForm.type === '视频生成');
const isVisualModel = computed(() =>
  ['图片生成', '视频生成', '视频编辑'].includes(modelForm.type),
);
const resolutionOptions = computed(() =>
  isImageModel.value ? imageResolutionOptions : videoResolutionOptions,
);
const modelFormCapabilityTags = computed(() => modelCapabilityTags(modelForm));

function handleModelTypeChange(value: unknown) {
  if (typeof value !== 'string') return;
  const type = value;
  modelForm.supportedResolutions =
    type === '图片生成'
      ? ['1K', '2K']
      : ['视频生成', '视频编辑'].includes(type)
        ? ['720p', '1080p']
        : [];
  modelForm.supportedAspectRatios = [
    '图片生成',
    '视频生成',
    '视频编辑',
  ].includes(type)
    ? ['16:9', '9:16', '1:1']
    : [];
  if (type === '视频生成') {
    modelForm.supportedInputModes = ['text_to_video', 'first_frame'];
    modelForm.durationParameterEnabled = true;
    modelForm.defaultDurationSeconds = 5;
    modelForm.minDurationSeconds = 5;
    modelForm.maxDurationSeconds = 10;
  } else {
    modelForm.supportedInputModes = [];
    modelForm.durationParameterEnabled = false;
    modelForm.defaultDurationSeconds = undefined;
    modelForm.minDurationSeconds = undefined;
    modelForm.maxDurationSeconds = undefined;
    modelForm.supportsExtension = false;
    modelForm.extensionMode = 'none';
    modelForm.supportsNativeAudio = false;
    modelForm.supportsMultiShot = false;
  }
}

function openModelDrawer(modelValue?: ModelRow | Record<string, unknown>) {
  // 表格插槽将行记录标注为通用对象，数据源实际始终来自 ModelRow[]。
  const model = modelValue as ModelRow | undefined;
  editingModelId.value = model?.id;
  Object.assign(
    modelForm,
    model
      ? {
          defaultDurationSeconds: model.defaultDurationSeconds ?? undefined,
          description: model.description,
          durationParameterEnabled: model.durationParameterEnabled,
          extensionMode: model.extensionMode,
          maxDurationSeconds: model.maxDurationSeconds ?? undefined,
          minDurationSeconds: model.minDurationSeconds ?? undefined,
          modelId: model.modelId,
          name: model.name,
          provider: model.provider,
          supportedAspectRatios: [...model.supportedAspectRatios],
          supportedInputModes: [...model.supportedInputModes],
          supportedResolutions: [...model.supportedResolutions],
          supportsExtension: model.supportsExtension,
          supportsImageEdit: model.supportsImageEdit,
          supportsMultiShot: model.supportsMultiShot,
          supportsNativeAudio: model.supportsNativeAudio,
          type: model.type,
        }
      : createEmptyModelForm(),
  );
  modelDrawerOpen.value = true;
}

async function saveModel() {
  if (!modelForm.name.trim() || !modelForm.modelId.trim()) {
    message.warning('请填写显示名称和供应商模型 ID');
    return;
  }
  backendLoading.value = true;
  try {
    await saveAdgenModelApi(modelForm, editingModelId.value);
    await refreshOperations();
    modelDrawerOpen.value = false;
    message.success('模型配置已保存到本地后端');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '模型配置保存失败');
  } finally {
    backendLoading.value = false;
  }
}

async function deleteModel(modelValue: ModelRow | Record<string, unknown>) {
  const model = modelValue as ModelRow;
  deletingModelId.value = model.id;
  try {
    await deleteAdgenModelApi(model.id);
    await refreshOperations();
    message.success(`${model.name} 已删除`);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '模型删除失败');
  } finally {
    deletingModelId.value = undefined;
  }
}

async function saveRoute() {
  backendLoading.value = true;
  try {
    await saveAdgenFeatureRouteApi(activeRoute.value);
    await refreshOperations();
    message.success(`${activeRoute.value.name} 路由配置已保存到本地后端`);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '路由配置保存失败');
  } finally {
    backendLoading.value = false;
  }
}

async function addCredential() {
  if (activePool.value.serviceType === 'kling') {
    const apiKey = klingApiKey.value.trim();
    if (!apiKey) {
      message.warning('请输入可灵 API Key');
      return;
    }
    backendLoading.value = true;
    try {
      await addAdgenKlingCredentialApi(apiKey);
      klingApiKey.value = '';
      await refreshOperations();
      message.success('可灵凭据已安全写入 MongoDB');
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : '可灵凭据添加失败',
      );
    } finally {
      backendLoading.value = false;
    }
    return;
  }
  const raw = newCredential.value.trim();
  if (!raw) {
    message.warning('请输入新的 API Key');
    return;
  }
  backendLoading.value = true;
  try {
    await addAdgenCredentialApi(activePool.value.serviceType, raw);
    newCredential.value = '';
    await refreshOperations();
    message.success('凭据已安全写入本地 MongoDB');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '凭据添加失败');
  } finally {
    backendLoading.value = false;
  }
}

async function removeCredential(index: number) {
  const keys = credentialKeys[activePool.value.id];
  if (!keys) return;
  const key = keys[index];
  if (!key) return;
  backendLoading.value = true;
  try {
    await deleteAdgenCredentialApi(activePool.value.serviceType, key.id);
    await refreshOperations();
    message.success('凭据已从本地 MongoDB 移除');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '凭据移除失败');
  } finally {
    backendLoading.value = false;
  }
}

async function resetCredentialPool() {
  credentialResetting.value = true;
  try {
    await resetAdgenCredentialPoolApi(activePool.value.serviceType);
    await refreshOperations();
    message.success(`${activePool.value.provider} 凭据池已重置`);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '凭据池重置失败');
  } finally {
    credentialResetting.value = false;
  }
}

function openSyncDrawer() {
  syncProvider.value =
    selectedProvider.value === 'all' ? 'byteplus' : selectedProvider.value;
  syncDrawerOpen.value = true;
}

async function syncModels() {
  syncingModels.value = true;
  try {
    const result = await syncAdgenModelsApi(syncProvider.value);
    await refreshOperations();
    syncDrawerOpen.value = false;
    if (result.added.length > 0) {
      message.success(
        `已同步 ${result.added.length} 个新模型，默认不自动启用，请到功能路由中勾选。`,
      );
      return;
    }
    if (result.ignoredDeleted.length > 0) {
      message.info('没有新模型。已删除的模型不会被同步回来。');
      return;
    }
    message.info('该服务商模型已是最新，没有需要同步的新模型。');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '模型同步失败');
  } finally {
    syncingModels.value = false;
  }
}

function handleErrorAction(rowValue: ErrorRow | Record<string, any>) {
  const row = rowValue as ErrorRow;
  const source = props.records.find((record) => record.id === row.id);
  if (source) {
    if (row.action === '重试') emit('action', source);
    else emit('inspect', source);
    return;
  }
  message.success(row.action === '重试' ? '已创建重试任务' : '已打开错误详情');
}
</script>

<template>
  <div class="adgen-ops w-full min-w-0 space-y-4">
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div
          class="mb-1 flex items-center gap-2 text-xs font-medium text-slate-500"
        >
          <IconifyIcon icon="lucide:server-cog" class="text-blue-600" />
          <span>系统管理 / AdGen 模型与运维</span>
        </div>
        <h1 class="m-0 text-[22px] font-semibold tracking-tight text-slate-950">
          AdGen 模型与运维
        </h1>
        <p class="mb-0 mt-1 text-sm text-slate-500">
          日常维护 API Key，按服务商同步模型；能力由目录自动识别
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Tag color="green">
          {{ healthyResourceCount }} / {{ records.length || 5 }} 资源正常
        </Tag>
        <Button type="primary" @click="openSyncDrawer">
          <template #icon><IconifyIcon icon="lucide:refresh-cw" /></template>
          同步模型
        </Button>
      </div>
    </header>

    <Card class="ops-card" :body-style="{ padding: '14px' }">
      <div
        class="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(320px,2fr)_minmax(150px,1fr)_auto]"
      >
        <label class="ops-field sm:col-span-2 xl:col-span-1">
          <span>模型配置</span>
          <Cascader
            v-model:value="selectedModelPath"
            allow-clear
            change-on-select
            class="w-full"
            :options="modelCascadeOptions"
            placeholder="服务商 / 应用类型 / 模型"
            show-search
          />
        </label>
        <label class="ops-field">
          <span>时间范围</span>
          <Select
            v-model:value="selectedPeriod"
            class="w-full"
            :options="[
              { label: '近 7 天', value: '7' },
              { label: '今日', value: '1' },
              { label: '近 30 天', value: '30' },
              { label: '全部历史', value: 'all' },
            ]"
          />
        </label>
        <Button
          class="self-end"
          :loading="loading || backendLoading"
          @click="refreshDashboard()"
        >
          <template #icon><IconifyIcon icon="lucide:refresh-cw" /></template>
          刷新
        </Button>
      </div>
    </Card>

    <section
      class="grid grid-cols-2 gap-3 xl:grid-cols-4"
      aria-label="运行指标"
    >
      <Card class="ops-card metric-card" :body-style="{ padding: '16px' }">
        <div class="metric-label">调用次数</div>
        <div class="metric-value">{{ overview.calls }}</div>
        <div class="metric-hint">当前筛选范围</div>
      </Card>
      <Card class="ops-card metric-card" :body-style="{ padding: '16px' }">
        <div class="metric-label">成功率</div>
        <div class="metric-value text-emerald-600">{{ overview.success }}</div>
        <div class="metric-hint">来自后端用量日志</div>
      </Card>
      <Card class="ops-card metric-card" :body-style="{ padding: '16px' }">
        <div class="metric-label">预估成本</div>
        <div class="metric-value">{{ overview.cost }}</div>
        <div class="metric-hint">按后端计费记录汇总</div>
      </Card>
      <Card class="ops-card metric-card" :body-style="{ padding: '16px' }">
        <div class="metric-label">平均延迟</div>
        <div class="metric-value">{{ overview.latency }}</div>
        <div class="metric-hint">图片与视频综合</div>
      </Card>
    </section>

    <section
      class="grid gap-3 xl:grid-cols-[minmax(0,1.65fr)_minmax(280px,1fr)]"
    >
      <Card class="ops-card" :body-style="{ padding: '16px 18px 12px' }">
        <div class="mb-4 flex items-center justify-between gap-3">
          <h2 class="m-0 text-sm font-semibold text-slate-900">调用趋势</h2>
          <div class="flex items-center gap-4 text-xs text-slate-500">
            <span class="flex items-center gap-1.5"
              ><i class="h-2 w-2 rounded-full bg-blue-500"></i>调用</span
            >
            <span class="flex items-center gap-1.5"
              ><i class="h-2 w-2 rounded-full bg-orange-500"></i>失败</span
            >
          </div>
        </div>
        <div
          class="trend-grid flex h-40 items-end justify-around gap-2 px-2 pt-3"
        >
          <div
            v-for="(value, index) in overview.chart"
            :key="index"
            class="flex h-full flex-1 items-end justify-center gap-1"
          >
            <span
              class="trend-bar bg-blue-500"
              :style="{ height: `${value}%` }"
            ></span>
            <span
              class="trend-bar bg-orange-400"
              :style="{ height: `${Math.max(5, Math.round(value * 0.12))}%` }"
            ></span>
          </div>
        </div>
        <div
          class="mt-2 grid grid-cols-7 text-center text-[11px] text-slate-400"
        >
          <span
            v-for="day in [
              '周一',
              '周二',
              '周三',
              '周四',
              '周五',
              '周六',
              '今天',
            ]"
            :key="day"
            >{{ day }}</span
          >
        </div>
      </Card>

      <Card
        class="ops-card usage-cost-card"
        :body-style="{ padding: '16px 18px 14px' }"
      >
        <div class="mb-2 flex items-center justify-between">
          <div>
            <h2 class="m-0 text-sm font-semibold text-slate-900">系统已用量</h2>
            <p class="mb-0 mt-1 text-xs text-slate-400">
              按数据库模型价格与原币种统计
            </p>
          </div>
          <Button type="link" @click="openQuotaManager">管理</Button>
        </div>
        <Tabs
          v-model:active-key="usageCostPeriod"
          class="usage-cost-tabs"
          :animated="false"
          :tab-bar-gutter="14"
        >
          <Tabs.TabPane
            v-for="option in usageCostPeriodOptions"
            :key="option.value"
            :tab="option.label"
          />
        </Tabs>

        <div class="usage-cost-summary">
          <div class="currency-summary-list">
            <span class="currency-summary-label">币种汇总</span>
            <span
              v-for="item in usageCostBreakdown.currencies"
              :key="item.currency"
              class="currency-summary-chip"
            >
              {{ item.currency }}
              <strong>{{
                formatNativeCost(item.nativeCost, item.currency)
              }}</strong>
            </span>
            <span
              v-if="!usageCostBreakdown.currencies.length"
              class="text-xs text-slate-400"
              >暂无</span
            >
          </div>
          <div class="usd-total">
            <span>美元合计</span>
            <strong>{{ formatUsd(usageCostBreakdown.totalUsd) }}</strong>
          </div>
        </div>

        <div class="usage-budget-progress">
          <div class="usage-budget-meta">
            <span>{{ usageCostBreakdown.label }}预算进度</span>
            <span v-if="usageCostQuota.limit">
              {{ formatUsd(usageCostBreakdown.totalUsd) }} /
              {{ formatUsd(usageCostQuota.limit) }}
            </span>
            <span v-else>
              {{ formatUsd(usageCostBreakdown.totalUsd) }} · 未设置预算
            </span>
          </div>
          <Progress
            :percent="usageCostQuota.percent"
            :show-info="false"
            :status="
              usageCostQuota.limit &&
              usageCostBreakdown.totalUsd >= usageCostQuota.limit
                ? 'exception'
                : 'normal'
            "
          />
        </div>

        <div
          class="usage-provider-list"
          :class="{ 'is-loading': usageCostLoading }"
        >
          <div v-if="usageCostLoading" class="usage-empty">统计中…</div>
          <div
            v-else-if="!usageCostBreakdown.providers.length"
            class="usage-empty"
          >
            当前日期范围暂无厂商用量
          </div>
          <template v-else>
            <div
              v-for="provider in usageCostBreakdown.providers"
              :key="provider.providerId"
              class="usage-provider-row"
            >
              <div class="min-w-0">
                <div class="truncate text-xs font-medium text-slate-700">
                  {{ provider.providerName }}
                </div>
                <div class="mt-0.5 text-[11px] text-slate-400">
                  调用 {{ formatUsageCount(provider.calls) }} · 成功
                  {{ formatUsageCount(provider.successCalls) }}
                </div>
              </div>
              <div class="usage-provider-cost">
                <strong
                  v-for="cost in provider.currencies"
                  :key="cost.currency"
                >
                  {{ formatNativeCost(cost.nativeCost, cost.currency) }}
                </strong>
                <span
                  v-if="
                    provider.currencies.some((cost) => cost.currency !== 'USD')
                  "
                >
                  ≈ {{ formatUsd(provider.totalUsd) }}
                </span>
              </div>
            </div>
          </template>
        </div>
      </Card>
    </section>

    <Card class="ops-card management-card" :body-style="{ padding: 0 }">
      <Tabs v-model:active-key="activeTab" class="ops-tabs">
        <Tabs.TabPane key="models" tab="模型配置">
          <div
            class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 pb-4"
          >
            <div class="flex min-w-0 flex-1 flex-wrap gap-2">
              <Input.Search
                v-model:value="modelSearch"
                allow-clear
                class="max-w-[320px]"
                placeholder="搜索模型名称或 ID"
              />
              <Select
                v-model:value="modelHealth"
                class="w-32"
                :options="[
                  { label: '全部状态', value: 'all' },
                  { label: '正常', value: 'healthy' },
                  { label: '预警', value: 'warning' },
                ]"
              />
            </div>
            <Space :size="8">
              <Button @click="openModelDrawer()">
                <template #icon><IconifyIcon icon="lucide:plus" /></template>
                手动添加
              </Button>
              <Button type="primary" @click="openSyncDrawer">
                <template #icon
                  ><IconifyIcon icon="lucide:refresh-cw"
                /></template>
                同步模型
              </Button>
            </Space>
          </div>
          <Table
            :columns="modelColumns"
            :data-source="filteredModels"
            :pagination="false"
            :scroll="{ x: 1100 }"
            row-key="id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <div class="font-medium text-slate-900">{{ record.name }}</div>
                <div class="mt-0.5 font-mono text-[11px] text-slate-400">
                  {{ record.modelId }}
                </div>
              </template>
              <template v-else-if="column.key === 'capabilities'">
                <div
                  v-if="modelCapabilityTags(record).length"
                  class="model-capability-tags"
                >
                  <Tag
                    v-for="tag in modelCapabilityTags(record).slice(0, 4)"
                    :key="tag"
                  >
                    {{ tag }}
                  </Tag>
                  <span
                    v-if="modelCapabilityTags(record).length > 4"
                    class="text-xs text-slate-400"
                  >
                    +{{ modelCapabilityTags(record).length - 4 }}
                  </span>
                </div>
                <span v-else class="text-xs text-slate-400"
                  >同步后自动识别</span
                >
              </template>
              <template v-else-if="column.key === 'health'">
                <Tag :color="record.health === 'healthy' ? 'green' : 'orange'">
                  {{ record.health === 'healthy' ? '正常' : '预警' }}
                </Tag>
              </template>
              <template v-else-if="column.key === 'action'">
                <Space :size="4">
                  <Button type="link" @click="openModelDrawer(record)"
                    >查看</Button
                  >
                  <Popconfirm
                    :title="`确认删除 ${record.name}？`"
                    description="模型会从功能路由中同步移除；如果它是默认模型，将自动切换到剩余的第一个模型。"
                    ok-text="删除"
                    ok-type="danger"
                    cancel-text="取消"
                    @confirm="deleteModel(record)"
                  >
                    <Button
                      danger
                      type="link"
                      :loading="deletingModelId === record.id"
                      >删除</Button
                    >
                  </Popconfirm>
                </Space>
              </template>
            </template>
          </Table>
        </Tabs.TabPane>

        <Tabs.TabPane key="routes" tab="功能路由">
          <div class="route-manager">
            <aside class="route-nav">
              <h3 class="mb-3 px-2 text-sm font-semibold text-slate-800">
                功能配置
              </h3>
              <button
                v-for="route in featureRoutes"
                :key="route.key"
                class="route-nav-button"
                :class="{ active: activeRouteKey === route.key }"
                @click="activeRouteKey = route.key"
              >
                <span>{{ route.name }}</span>
                <small
                  >{{
                    route.models.filter((item) => item.enabled).length
                  }}
                  个模型</small
                >
              </button>
            </aside>
            <section class="min-w-0 p-5">
              <div
                class="mb-5 flex flex-wrap items-start justify-between gap-3"
              >
                <div>
                  <h3 class="m-0 text-base font-semibold text-slate-900">
                    {{ activeRoute.name }}
                  </h3>
                  <p class="mb-0 mt-1 text-xs text-slate-500">
                    {{ activeRoute.category }} · 保存后立即生成新路由版本
                  </p>
                </div>
                <Tag color="blue">production</Tag>
              </div>
              <div class="grid gap-4 lg:grid-cols-3">
                <FormItem label="默认模型" class="mb-0">
                  <Select
                    v-model:value="activeRoute.defaultModel"
                    class="w-full"
                    :options="
                      activeRoute.models.map((item) => ({
                        label: item.name,
                        value: item.id,
                      }))
                    "
                  />
                </FormItem>
                <FormItem :label="activeRoute.limitLabel" class="mb-0">
                  <InputNumber
                    v-model:value="activeRoute.limit"
                    class="w-full"
                    :min="1"
                    :max="50"
                  />
                </FormItem>
                <FormItem
                  v-if="activeRoute.resolutions"
                  label="默认分辨率"
                  class="mb-0"
                >
                  <Select
                    v-model:value="activeRoute.resolution"
                    class="w-full"
                    :options="
                      activeRoute.resolutions.map((item) => ({
                        label: item,
                        value: item,
                      }))
                    "
                  />
                </FormItem>
              </div>
              <div class="mt-5">
                <div class="mb-2 text-xs font-medium text-slate-600">
                  可用模型
                </div>
                <div class="grid gap-2 lg:grid-cols-2">
                  <div
                    v-for="routeModel in activeRoute.models"
                    :key="routeModel.id"
                    class="route-model-row"
                  >
                    <div class="min-w-0">
                      <div class="truncate text-sm font-medium text-slate-800">
                        {{ routeModel.name }}
                      </div>
                      <div
                        class="mt-0.5 truncate font-mono text-[10px] text-slate-400"
                      >
                        {{ routeModel.id }}
                      </div>
                    </div>
                    <Switch v-model:checked="routeModel.enabled" />
                  </div>
                </div>
              </div>
              <div class="mt-5 flex justify-end">
                <Button
                  type="primary"
                  :loading="backendLoading"
                  @click="saveRoute"
                  >保存路由配置</Button
                >
              </div>
            </section>
          </div>
        </Tabs.TabPane>

        <Tabs.TabPane
          v-if="OFFICIAL_ASSET_LIBRARY_ENABLED"
          key="byteplus-assets"
          tab="官方素材库"
        >
          <div
            class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-4"
          >
            <div class="text-muted-foreground min-w-0 flex-1 space-y-2 text-sm">
              <p class="mb-0 text-sm text-slate-600">
                画布勾选素材与官方导入素材共用配额，当前已知占用
                {{ byteplusAssetUsed }}/{{ byteplusAssetLimit }} 条。达到
                {{ Math.ceil(byteplusAssetLimit * 0.9) }}
                条时，自动清理最早入库且未被生成任务占用的素材至
                {{ Math.floor(byteplusAssetLimit * 0.8) }}
                条；仅自动清理已关联素材，未关联素材由人工维护。
              </p>
              <p class="mb-0">
                核对范围：{{
                  byteplusAssetScope || '当前配置项目的全部 AIGC 素材组'
                }}。 最近核对官方数量：{{
                  byteplusAssetOfficialCount ?? '尚未核对'
                }}； 本地记录：{{ byteplusAssetLocalCount }}。
                <span v-if="byteplusAssetCheckedAt">
                  核对时间：{{
                    new Date(byteplusAssetCheckedAt).toLocaleString('zh-CN')
                  }}。
                </span>
              </p>
            </div>
            <Space>
              <Button
                :disabled="byteplusAssetBusy"
                @click="loadByteplusAssets()"
              >
                刷新
              </Button>
              <Button
                type="primary"
                :loading="byteplusAssetReconciling"
                :disabled="
                  !byteplusAssetConfigured ||
                  (byteplusAssetBusy && !byteplusAssetReconciling)
                "
                @click="loadByteplusAssets(true)"
              >
                核对官方素材
              </Button>
              <Popconfirm
                :title="`确定删除选中的 ${selectedByteplusAssetIds.length} 条官方素材？`"
                description="官方缺失素材仅清理本地记录，其余素材从官方平台删除；已关联画布再次使用时需要重新入库。"
                :disabled="
                  byteplusAssetBusy || selectedByteplusAssetIds.length === 0
                "
                @confirm="removeSelectedByteplusAssets"
              >
                <Button
                  danger
                  :loading="batchDeletingByteplusAssets"
                  :disabled="
                    byteplusAssetBusy || selectedByteplusAssetIds.length === 0
                  "
                >
                  批量删除官方素材（{{ selectedByteplusAssetIds.length }}）
                </Button>
              </Popconfirm>
            </Space>
          </div>
          <p
            v-if="!byteplusAssetConfigured"
            class="px-4 pt-3 text-sm text-amber-700"
          >
            尚未配置 BYTEPLUS_ACCESS_KEY /
            BYTEPLUS_SECRET_KEY，入库接口目前不可用。
          </p>
          <div class="flex flex-wrap items-end gap-4 px-4 py-4">
            <div class="flex w-full flex-col gap-2 sm:w-80">
              <label for="byteplus-asset-keyword" class="text-sm"
                >名称 / 素材组 ID / 素材 ID</label
              >
              <Input
                id="byteplus-asset-keyword"
                v-model:value="byteplusAssetKeyword"
                allow-clear
                placeholder="输入名称或 ID 模糊筛选"
                :disabled="byteplusAssetBusy"
              />
            </div>
            <div class="flex w-full flex-col gap-2 sm:w-44">
              <label for="byteplus-asset-type" class="text-sm">类型</label>
              <Select
                id="byteplus-asset-type"
                v-model:value="byteplusAssetTypeFilter"
                allow-clear
                placeholder="全部类型"
                :options="byteplusAssetTypeOptions"
                :disabled="byteplusAssetBusy"
              />
            </div>
            <div class="flex w-full flex-col gap-2 sm:w-52">
              <label for="byteplus-asset-status" class="text-sm"
                >官方状态</label
              >
              <Select
                id="byteplus-asset-status"
                v-model:value="byteplusAssetStatusFilter"
                allow-clear
                placeholder="全部官方状态"
                :options="byteplusAssetStatusOptions"
                :disabled="byteplusAssetBusy"
              />
            </div>
            <div class="flex w-full flex-col gap-2 sm:w-52">
              <label for="byteplus-asset-association" class="text-sm"
                >关联状态</label
              >
              <Select
                id="byteplus-asset-association"
                v-model:value="byteplusAssetAssociationFilter"
                allow-clear
                placeholder="全部关联状态"
                :options="byteplusAssetAssociationOptions"
                :disabled="byteplusAssetBusy"
              />
            </div>
            <Button
              :disabled="byteplusAssetBusy"
              @click="resetByteplusAssetFilters"
              >重置筛选</Button
            >
            <span
              class="text-muted-foreground self-center text-sm"
              role="status"
            >
              显示 {{ filteredByteplusAssets.length }} /
              {{ byteplusAssets.length }} 条
            </span>
          </div>
          <p
            v-if="batchDeletingByteplusAssets"
            class="text-muted-foreground px-4 pt-3 text-sm"
            role="status"
          >
            正在删除 {{ byteplusBatchProgress }}/{{ byteplusBatchTotal }}
            条，官方限流可能需要等待，请保持页面打开。
          </p>
          <Table
            :columns="byteplusAssetColumns"
            :row-selection="byteplusAssetRowSelection"
            :data-source="filteredByteplusAssets"
            :loading="byteplusAssetLoading"
            :pagination="false"
            row-key="id"
          >
            <template #headerCell="{ column }">
              <span
                v-if="column.key === 'associationStatus'"
                class="inline-flex items-center gap-1"
              >
                关联状态
                <Popover trigger="click" placement="topLeft">
                  <template #content>
                    <div class="w-72 max-w-[80vw] space-y-2 text-sm">
                      <p class="mb-0">
                        已关联（Linked）：有画布来源文件映射，且最近核对未发现官方缺失。
                      </p>
                      <p class="mb-0">
                        未关联（Unlinked）：官方存在，但缺少本系统的画布来源文件映射。
                      </p>
                      <p class="mb-0">
                        官方缺失（Missing）：最近完整核对时官方已不存在，本地记录和恢复信息仍保留。
                      </p>
                    </div>
                  </template>
                  <button
                    type="button"
                    class="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex items-center justify-center rounded p-1 focus-visible:outline-none focus-visible:ring-2"
                    aria-label="查看关联状态说明"
                    @click.stop
                  >
                    <IconifyIcon icon="lucide:circle-help" class="size-4" />
                  </button>
                </Popover>
              </span>
              <template v-else>{{ column.title }}</template>
            </template>
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'associationStatus'">
                {{
                  byteplusAssociationLabels[
                    record.associationStatus as keyof typeof byteplusAssociationLabels
                  ] || '未关联'
                }}
                <span class="text-muted-foreground"
                  >({{ record.associationStatus }})</span
                >
              </template>
              <template v-else-if="column.key === 'status'">
                {{ record.status || '—' }}
              </template>
              <template v-else-if="column.key === 'action'">
                <Space :size="4">
                  <Button
                    size="small"
                    type="link"
                    :disabled="!record.canPreview"
                    @click="openByteplusAssetPreview(record)"
                  >
                    查看
                  </Button>
                  <Popconfirm
                    :title="
                      record.associationStatus === 'Missing'
                        ? '仅清理本地记录，确定继续？'
                        : record.associationStatus === 'Unlinked'
                          ? '将删除官方平台素材，确定继续？'
                          : '删除后画布需重新勾选才能再用'
                    "
                    :disabled="byteplusAssetBusy"
                    @confirm="removeByteplusAsset(record.id)"
                  >
                    <Button
                      danger
                      type="link"
                      :disabled="byteplusAssetBusy"
                      :loading="deletingByteplusAssetId === record.id"
                    >
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              </template>
            </template>
          </Table>

          <Modal
            v-model:open="byteplusAssetPreviewOpen"
            :footer="null"
            :title="byteplusAssetPreview?.name || '关联素材预览'"
            width="760px"
          >
            <div
              v-if="byteplusAssetPreviewLoading"
              class="flex min-h-48 items-center justify-center text-sm text-slate-500"
            >
              正在加载关联素材…
            </div>
            <div
              v-else-if="byteplusAssetPreviewError"
              class="flex min-h-48 items-center justify-center text-sm text-red-500"
            >
              {{ byteplusAssetPreviewError }}
            </div>
            <video
              v-else-if="
                byteplusAssetPreview?.assetType?.toLowerCase() === 'video'
              "
              :src="byteplusAssetPreview.previewUrl"
              class="max-h-[70vh] w-full rounded bg-black"
              controls
              playsinline
            />
            <img
              v-else-if="byteplusAssetPreview"
              :alt="byteplusAssetPreview.name"
              :src="byteplusAssetPreview.previewUrl"
              class="mx-auto max-h-[70vh] max-w-full rounded object-contain"
            />
          </Modal>
        </Tabs.TabPane>

        <Tabs.TabPane key="credentials" tab="凭据池">
          <div class="credential-manager">
            <aside class="route-nav">
              <h3 class="mb-3 px-2 text-sm font-semibold text-slate-800">
                凭据池
              </h3>
              <button
                v-for="pool in credentialPools"
                :key="pool.id"
                class="pool-nav-button"
                :class="{ active: activePoolId === pool.id }"
                @click="activePoolId = pool.id"
              >
                <span>{{ pool.name }}</span>
                <small
                  >{{ pool.provider }} · {{ pool.available }}/{{
                    pool.total
                  }}
                  可用</small
                >
              </button>
            </aside>
            <section class="min-w-0 p-5">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 class="m-0 text-base font-semibold text-slate-900">
                    {{ activePool.provider }} API Key 池
                  </h3>
                  <p class="mb-0 mt-1 text-xs text-slate-500">
                    {{ activePool.name }} · {{ activePool.environment }} ·
                    仅供模型部署内部调用
                  </p>
                </div>
                <Space wrap>
                  <Popconfirm
                    title="重置当前凭据池？"
                    description="该池所有凭据的使用次数和错误次数将清零。"
                    ok-text="重置"
                    cancel-text="取消"
                    @confirm="resetCredentialPool"
                  >
                    <Button
                      danger
                      type="text"
                      aria-label="重置当前凭据池"
                      title="重置当前凭据池"
                      :disabled="activePool.total === 0"
                      :loading="credentialResetting"
                    >
                      <IconifyIcon icon="lucide:refresh-cw" />
                    </Button>
                  </Popconfirm>
                  <Tag color="green">MongoDB</Tag>
                  <Tag>总计 {{ activePool.total }}</Tag>
                  <Tag color="green">可用 {{ activePool.available }}</Tag>
                  <Tag :color="activePool.quota > 75 ? 'orange' : 'blue'"
                    >配额 {{ activePool.quota }}%</Tag
                  >
                </Space>
              </div>
              <div
                v-if="activePool.serviceType === 'kling'"
                class="my-5 grid gap-2 md:grid-cols-[1fr_auto]"
              >
                <Input.Password
                  v-model:value="klingApiKey"
                  autocomplete="new-password"
                  placeholder="输入可灵 API Key"
                  @press-enter="addCredential"
                />
                <Button
                  type="primary"
                  :loading="backendLoading"
                  @click="addCredential"
                >
                  <template #icon><IconifyIcon icon="lucide:plus" /></template>
                  添加
                </Button>
              </div>
              <div v-else class="my-5 flex gap-2">
                <Input.Password
                  v-model:value="newCredential"
                  autocomplete="new-password"
                  :placeholder="`输入新的 ${activePool.provider} API Key`"
                />
                <Button
                  type="primary"
                  :loading="backendLoading"
                  @click="addCredential"
                >
                  <template #icon><IconifyIcon icon="lucide:plus" /></template>
                  添加
                </Button>
              </div>
              <div class="space-y-2">
                <div
                  v-for="(key, index) in activePoolKeys"
                  :key="key.id"
                  class="credential-row"
                >
                  <div class="min-w-0">
                    <div class="text-sm font-medium text-slate-800">
                      {{ key.id }}
                    </div>
                    <div class="mt-1 font-mono text-xs text-slate-500">
                      {{ key.masked }}
                    </div>
                  </div>
                  <div
                    class="flex flex-wrap items-center justify-end gap-2 text-xs text-slate-500"
                  >
                    <Tag
                      :color="key.status === 'healthy' ? 'green' : 'orange'"
                      >{{ key.status === 'healthy' ? '正常' : '预警' }}</Tag
                    >
                    <span>使用 {{ key.usage }}</span>
                    <span>错误 {{ key.errorCount }}</span>
                    <Button danger type="text" @click="removeCredential(index)">
                      <IconifyIcon icon="lucide:trash-2" />
                    </Button>
                  </div>
                </div>
              </div>
              <div
                class="mt-4 flex items-center justify-between text-xs text-slate-400"
              >
                <span
                  >当前展示 {{ activePoolKeys.length }} /
                  {{ activePool.total }}</span
                >
                <Button type="link">查看全部</Button>
              </div>
            </section>
          </div>
        </Tabs.TabPane>

        <Tabs.TabPane key="usage" tab="用量排行">
          <div
            class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 pb-4"
          >
            <Input.Search
              v-model:value="usageRankingSearch"
              allow-clear
              class="max-w-[360px]"
              placeholder="搜索用户名或用户 ID"
            />
            <Select
              v-model:value="usageRankingPeriod"
              class="w-32"
              :options="usageRankingPeriodOptions"
            />
          </div>
          <Table
            :columns="usageRankingColumns"
            :data-source="filteredUsageRankingRows"
            :loading="usageRankingLoading"
            :pagination="false"
            :scroll="{ x: 810 }"
            row-key="userId"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'rank'">
                <Tag :color="record.rank <= 3 ? 'blue' : 'default'">
                  {{ record.rank }}
                </Tag>
              </template>
              <template v-else-if="column.key === 'displayName'">
                <div class="font-medium text-slate-800">
                  {{ record.displayName }}
                </div>
                <div class="mt-1 text-xs text-slate-400">
                  ID {{ record.userId }}
                </div>
              </template>
              <template v-else-if="column.key === 'share'">
                <div class="flex items-center gap-3">
                  <Progress
                    class="max-w-28"
                    :percent="record.share"
                    :show-info="false"
                  />
                  <span class="text-xs text-slate-500"
                    >{{ record.share.toFixed(1) }}%</span
                  >
                </div>
              </template>
              <template v-else-if="column.key === 'cost'">
                <span class="font-medium text-slate-700">{{
                  formatUsd(record.cost)
                }}</span>
              </template>
            </template>
          </Table>
        </Tabs.TabPane>

        <Tabs.TabPane key="errors" tab="错误日志">
          <div
            class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 pb-4"
          >
            <Input.Search
              class="max-w-[360px]"
              placeholder="搜索模型、错误或请求 ID"
            />
            <Button
              ><template #icon><IconifyIcon icon="lucide:download" /></template
              >导出</Button
            >
          </div>
          <Table
            :columns="errorColumns"
            :data-source="errorRows"
            :pagination="false"
            :scroll="{ x: 940 }"
            row-key="id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <Tag
                  :color="
                    record.status.includes('待') || record.status.includes('需')
                      ? 'orange'
                      : 'green'
                  "
                  >{{ record.status }}</Tag
                >
              </template>
              <template v-else-if="column.key === 'action'">
                <Button type="link" @click="handleErrorAction(record)">{{
                  record.action
                }}</Button>
              </template>
            </template>
          </Table>
        </Tabs.TabPane>
      </Tabs>
    </Card>

    <Drawer
      v-model:open="quotaDrawerOpen"
      title="系统与个人配额管理"
      width="min(760px, 96vw)"
    >
      <Tabs v-model:active-key="quotaManagerTab">
        <Tabs.TabPane key="system" tab="系统配额">
          <p class="mb-5 mt-0 text-sm leading-6 text-slate-500">
            配额按预估成本（USD）限制。输入 0
            或留空表示不限额，保存后立即用于生成前校验。
          </p>
          <div class="grid gap-4 md:grid-cols-3">
            <section class="quota-editor-card">
              <div class="text-sm font-semibold text-slate-800">日上限</div>
              <InputNumber
                v-model:value="systemQuotaForm.dailyLimit"
                class="mt-3 w-full"
                :min="0"
                :precision="2"
                placeholder="不限额"
              />
              <div class="mt-3 text-xs text-slate-400">
                当前 {{ formatUsd(quotaSettings.daily.used) }}
              </div>
              <Progress
                class="mt-1"
                :percent="Math.min(quotaSettings.daily.percent, 100)"
                :show-info="false"
              />
            </section>
            <section class="quota-editor-card">
              <div class="text-sm font-semibold text-slate-800">周上限</div>
              <InputNumber
                v-model:value="systemQuotaForm.weeklyLimit"
                class="mt-3 w-full"
                :min="0"
                :precision="2"
                placeholder="不限额"
              />
              <div class="mt-3 text-xs text-slate-400">
                当前 {{ formatUsd(quotaSettings.weekly.used) }}
              </div>
              <Progress
                class="mt-1"
                :percent="Math.min(quotaSettings.weekly.percent, 100)"
                :show-info="false"
              />
            </section>
            <section class="quota-editor-card">
              <div class="text-sm font-semibold text-slate-800">月上限</div>
              <InputNumber
                v-model:value="systemQuotaForm.monthlyLimit"
                class="mt-3 w-full"
                :min="0"
                :precision="2"
                placeholder="不限额"
              />
              <div class="mt-3 text-xs text-slate-400">
                当前 {{ formatUsd(quotaSettings.monthly.used) }}
              </div>
              <Progress
                class="mt-1"
                :percent="Math.min(quotaSettings.monthly.percent, 100)"
                :show-info="false"
              />
            </section>
          </div>
        </Tabs.TabPane>

        <Tabs.TabPane key="personal" tab="个人配额">
          <Form layout="vertical">
            <FormItem label="人员" required>
              <div class="mb-2 flex items-center justify-end gap-2">
                <Button
                  type="link"
                  @click="
                    selectedQuotaUserIds = quotaSettings.users.map(
                      (user) => user.userId,
                    )
                  "
                >
                  全选
                </Button>
                <Button type="link" @click="selectedQuotaUserIds = []">
                  清空
                </Button>
              </div>
              <Select
                v-model:value="selectedQuotaUserIds"
                class="w-full"
                :filter-option="
                  (input, option) =>
                    String(option?.label ?? '')
                      .toLowerCase()
                      .includes(input.toLowerCase())
                "
                :loading="quotaLoading"
                :max-tag-count="3"
                :options="quotaUserOptions"
                mode="multiple"
                placeholder="按人员名称搜索并选择"
                show-search
              />
            </FormItem>
            <div class="grid gap-x-4 md:grid-cols-3">
              <FormItem label="个人日上限（USD）">
                <InputNumber
                  v-model:value="userQuotaForm.dailyLimit"
                  class="w-full"
                  :disabled="selectedQuotaUserIds.length === 0"
                  :min="0"
                  :precision="2"
                  placeholder="不限额"
                />
              </FormItem>
              <FormItem label="个人周上限（USD）">
                <InputNumber
                  v-model:value="userQuotaForm.weeklyLimit"
                  class="w-full"
                  :disabled="selectedQuotaUserIds.length === 0"
                  :min="0"
                  :precision="2"
                  placeholder="不限额"
                />
              </FormItem>
              <FormItem label="个人月上限（USD）">
                <InputNumber
                  v-model:value="userQuotaForm.monthlyLimit"
                  class="w-full"
                  :disabled="selectedQuotaUserIds.length === 0"
                  :min="0"
                  :precision="2"
                  placeholder="不限额"
                />
              </FormItem>
            </div>
          </Form>
          <div
            class="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-500"
          >
            可多选或全选人员后统一设置配额；保存会覆盖所选人员原有的个人配额。
            未单独配置时不限制个人用量。
          </div>
        </Tabs.TabPane>
      </Tabs>
      <template #footer>
        <div class="flex justify-end gap-2">
          <Button @click="quotaDrawerOpen = false">取消</Button>
          <Button
            v-if="quotaManagerTab === 'system'"
            type="primary"
            :loading="quotaSaving"
            @click="saveSystemQuota"
          >
            保存系统配额
          </Button>
          <Button
            v-else
            type="primary"
            :disabled="selectedQuotaUserIds.length === 0"
            :loading="quotaSaving"
            @click="saveUserQuota"
          >
            保存{{ selectedQuotaUserIds.length }}人配额
          </Button>
        </div>
      </template>
    </Drawer>

    <Drawer
      v-model:open="syncDrawerOpen"
      title="同步模型"
      width="min(480px, 96vw)"
    >
      <p class="mb-4 mt-0 text-sm leading-6 text-slate-500">
        按服务商把内置模型目录中尚未入库的模型补进来，并自动带上画质、比例和输入能力。已有配置和已删除的模型不会被覆盖。
      </p>
      <Form layout="vertical">
        <FormItem label="服务商" required>
          <Select
            v-model:value="syncProvider"
            class="w-full"
            :options="syncProviderOptions"
          />
        </FormItem>
      </Form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <Button @click="syncDrawerOpen = false">取消</Button>
          <Button type="primary" :loading="syncingModels" @click="syncModels">
            开始同步
          </Button>
        </div>
      </template>
    </Drawer>

    <Drawer
      v-model:open="modelDrawerOpen"
      :title="editingModelId ? '查看模型' : '手动添加模型'"
      width="min(600px, 96vw)"
    >
      <p class="mb-4 mt-0 text-sm leading-6 text-slate-500">
        日常请用「同步模型」。这里只用于补一条目录里还没有的模型
        ID，能力字段一般不用手填。
      </p>
      <Form layout="vertical">
        <div class="model-form-grid">
          <FormItem label="服务商" required>
            <Select
              v-model:value="modelForm.provider"
              :options="
                providerOptions
                  .slice(1)
                  .map((item) => ({ label: item.label, value: item.label }))
              "
            />
          </FormItem>
          <FormItem label="类型" required>
            <Select
              v-model:value="modelForm.type"
              :options="modelTypeOptions"
              @change="handleModelTypeChange"
            />
          </FormItem>
          <FormItem label="显示名称" required>
            <Input
              v-model:value="modelForm.name"
              placeholder="例如 Seedance 2.5"
            />
          </FormItem>
          <FormItem label="供应商模型 ID" required>
            <Input
              v-model:value="modelForm.modelId"
              placeholder="例如 provider-model-id"
            />
          </FormItem>
        </div>

        <FormItem label="模型说明">
          <Input.TextArea
            v-model:value="modelForm.description"
            :maxlength="500"
            :rows="2"
            show-count
            placeholder="说明模型定位、区域或使用限制"
          />
        </FormItem>

        <div
          v-if="modelFormCapabilityTags.length"
          class="model-capability-preview"
        >
          <div class="mb-2 text-xs font-medium text-slate-600">已识别能力</div>
          <div class="model-capability-tags">
            <Tag v-for="tag in modelFormCapabilityTags" :key="tag">{{
              tag
            }}</Tag>
          </div>
        </div>

        <Collapse v-if="isVisualModel" ghost class="model-advanced-collapse">
          <Collapse.Panel key="advanced" header="手动覆盖能力（一般无需填写）">
            <div class="model-form-section">
              <div>
                <h4>输出参数</h4>
                <p>从固定选项中选择模型接口实际支持的画质与比例。</p>
              </div>
              <FormItem label="支持画质" required>
                <Select
                  v-model:value="modelForm.supportedResolutions"
                  mode="multiple"
                  :options="resolutionOptions"
                  placeholder="请选择支持画质"
                />
              </FormItem>
              <FormItem label="支持画面比例">
                <Select
                  v-model:value="modelForm.supportedAspectRatios"
                  mode="multiple"
                  :options="aspectRatioOptions"
                  placeholder="请选择支持比例"
                />
              </FormItem>
              <div v-if="isImageModel" class="model-switch-row">
                <div>
                  <strong>参考图编辑</strong>
                  <span>允许图片节点作为参考素材输入</span>
                </div>
                <Switch v-model:checked="modelForm.supportsImageEdit" />
              </div>
            </div>

            <div v-if="isVideoModel" class="model-form-section">
              <div>
                <h4>视频输入能力</h4>
                <p>请只勾选供应商接口实际支持的模式。</p>
              </div>
              <Checkbox.Group
                v-model:value="modelForm.supportedInputModes"
                class="model-capability-grid"
              >
                <Checkbox
                  v-for="option in videoInputModeOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </Checkbox>
              </Checkbox.Group>

              <div class="model-switch-row">
                <div>
                  <strong>允许选择时长</strong>
                  <span>开启后，生成端可提交秒数参数</span>
                </div>
                <Switch v-model:checked="modelForm.durationParameterEnabled" />
              </div>
              <div
                v-if="modelForm.durationParameterEnabled"
                class="model-duration-grid"
              >
                <FormItem label="最短时长（秒）">
                  <InputNumber
                    v-model:value="modelForm.minDurationSeconds"
                    :min="1"
                    :max="300"
                    class="w-full"
                  />
                </FormItem>
                <FormItem label="默认时长（秒）">
                  <InputNumber
                    v-model:value="modelForm.defaultDurationSeconds"
                    :min="1"
                    :max="300"
                    class="w-full"
                  />
                </FormItem>
                <FormItem label="最长时长（秒）">
                  <InputNumber
                    v-model:value="modelForm.maxDurationSeconds"
                    :min="1"
                    :max="300"
                    class="w-full"
                  />
                </FormItem>
              </div>
            </div>
          </Collapse.Panel>
        </Collapse>
      </Form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <Button @click="modelDrawerOpen = false">取消</Button>
          <Button type="primary" :loading="backendLoading" @click="saveModel"
            >保存配置</Button
          >
        </div>
      </template>
    </Drawer>
  </div>
</template>

<style scoped>
.ops-card {
  border-color: #e7ebf0;
  border-radius: 11px;
  box-shadow: 0 1px 2px rgb(15 23 42 / 3%);
}

.ops-field > span {
  display: block;
  margin-bottom: 5px;
  color: #64748b;
  font-size: 11px;
  font-weight: 500;
}

.metric-label {
  color: #64748b;
  font-size: 12px;
}

.metric-value {
  margin-top: 8px;
  color: #0f172a;
  font-size: clamp(20px, 2.3vw, 27px);
  font-weight: 620;
  line-height: 1;
  letter-spacing: -0.03em;
}

.metric-hint {
  margin-top: 8px;
  color: #94a3b8;
  font-size: 11px;
}

.trend-grid {
  background-image: linear-gradient(to top, #e9eef5 1px, transparent 1px);
  background-size: 100% 25%;
}

.trend-bar {
  width: min(18px, 32%);
  min-height: 4px;
  border-radius: 4px 4px 1px 1px;
  transition: opacity 180ms ease;
}

.usage-cost-card {
  min-width: 0;
}

.usage-cost-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 10px;
  border: 1px solid #e8eef5;
  border-radius: 8px;
  background: #f8fafc;
}

.currency-summary-list {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
}

.currency-summary-label {
  margin-right: 2px;
  color: #64748b;
  font-size: 11px;
}

.currency-summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  color: #64748b;
  background: #fff;
  font-size: 10px;
}

.currency-summary-chip strong {
  color: #334155;
  font-size: 11px;
}

.usd-total {
  flex: none;
  text-align: right;
}

.usd-total span,
.usage-provider-cost span {
  display: block;
  color: #94a3b8;
  font-size: 10px;
}

.usd-total strong {
  display: block;
  margin-top: 2px;
  color: #0f172a;
  font-size: 14px;
}

.usage-budget-progress {
  margin-top: 9px;
}

.usage-budget-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 2px;
  color: #64748b;
  font-size: 11px;
}

.usage-provider-list {
  max-height: 148px;
  min-height: 76px;
  margin-top: 8px;
  overflow-y: auto;
  border-top: 1px solid #eef2f7;
}

.usage-provider-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 2px;
  border-bottom: 1px solid #f1f5f9;
}

.usage-provider-cost {
  flex: none;
  color: #334155;
  font-size: 12px;
  text-align: right;
}

.usage-empty {
  display: flex;
  min-height: 76px;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 12px;
}

.quota-editor-card {
  padding: 16px;
  border: 1px solid #e7ebf0;
  border-radius: 11px;
  background: #fff;
}

.route-manager,
.credential-manager {
  display: grid;
  min-height: 390px;
  grid-template-columns: 210px minmax(0, 1fr);
}

.route-nav {
  padding: 14px 12px;
  border-right: 1px solid #e7ebf0;
  background: #f8fafc;
}

.route-nav-button,
.pool-nav-button {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 5px;
  padding: 10px;
  border: 0;
  border-radius: 8px;
  color: #334155;
  background: transparent;
  text-align: left;
}

.pool-nav-button {
  display: block;
}

.route-nav-button small,
.pool-nav-button small {
  color: #94a3b8;
  font-size: 10px;
}

.pool-nav-button small {
  display: block;
  margin-top: 4px;
}

.route-nav-button:hover,
.pool-nav-button:hover,
.route-nav-button.active,
.pool-nav-button.active {
  color: #2563eb;
  background: hsl(var(--muted));
}

.route-model-row,
.credential-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 12px;
  border: 1px solid #e7ebf0;
  border-radius: 9px;
  background: #fff;
}

.model-form-grid,
.model-duration-grid {
  display: grid;
  gap: 0 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.model-duration-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.model-form-section {
  margin-bottom: 16px;
  padding: 16px;
  border: 1px solid #e7ebf0;
  border-radius: 10px;
  background: #f8fafc;
}

.model-form-section h4 {
  margin: 0;
  color: #1e293b;
  font-size: 14px;
  font-weight: 600;
}

.model-form-section p {
  margin: 4px 0 14px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.model-capability-preview {
  margin-bottom: 8px;
  padding: 12px 16px;
  border: 1px solid #e7ebf0;
  border-radius: 10px;
  background: #f8fafc;
}

.model-capability-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.model-advanced-collapse {
  margin-top: 8px;
  background: transparent;
}

.model-capability-grid {
  display: grid;
  gap: 10px 16px;
  margin-bottom: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.model-switch-row {
  display: flex;
  min-height: 56px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0;
  border-top: 1px solid #e7ebf0;
}

.model-switch-row strong,
.model-switch-row span {
  display: block;
}

.model-switch-row strong {
  color: #334155;
  font-size: 13px;
  font-weight: 600;
}

.model-switch-row span {
  margin-top: 2px;
  color: #64748b;
  font-size: 12px;
}

@media (max-width: 767px) {
  .route-manager,
  .credential-manager {
    grid-template-columns: 1fr;
  }

  .route-nav {
    border-right: 0;
    border-bottom: 1px solid #e7ebf0;
  }

  .model-form-grid,
  .model-duration-grid,
  .model-capability-grid {
    grid-template-columns: 1fr;
  }
}
</style>
