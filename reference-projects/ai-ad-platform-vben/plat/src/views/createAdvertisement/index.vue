<script lang="ts" setup>
/* eslint-disable vue/html-closing-bracket-newline */
import type { CascaderProps, TableColumnsType } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import type { AgentOptionsItem } from '#/api/management/platform-config';

import type {
  AdvertiserItem,
  CreativeEnhancement,
  MaterialGroup,
  MaterialItem,
  RegionGroup,
  SelectedProduct,
  SeriesData,
} from './types';

import {
  computed,
  onActivated,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  shallowRef,
  toRaw,
  watch,
} from 'vue';

import { useUserStore } from '@vben/stores';

import {
  Button,
  Card,
  Cascader,
  Checkbox,
  Collapse,
  DatePicker,
  Input,
  InputNumber,
  message,
  Modal,
  Popover,
  Radio,
  Select,
  Spin,
  Steps,
  Switch,
  Table,
  Tabs,
  Tag,
  Textarea,
  Tooltip,
} from 'ant-design-vue';
import { useDebounceFn } from '@vueuse/core';
import { IconifyIcon, RotateCw } from '@vben/icons';
import dayjs from 'dayjs';

import {
  batchQueryMissionLineInfo,
  createAdvertisement,
  createMaterialTemplate,
  createTemplate,
  getAiSuggestionReportUrl,
  getMinioPresignedUrl,
  syncAdAccountApplications,
  updateMaterialTemplate,
  updateTemplate,
} from '#/api/advertisement';
import { isDemoMockEnabled } from '#/api/demo-mock';
import { reuseCreativeHistory } from '#/api/advertisement/creativeHistory';
import { validateCTAForMaterial } from '#/api/advertisement/mappings';
import {
  applyMaterialGroup,
  createMaterialGroup,
  getMaterialGroupDetail,
  reapplyHistory,
  updateMaterialGroup,
} from '#/api/advertisement/materialGroup';
import { transformToAdvertisementParams } from '#/api/advertisement/transform';
import { getAgentOptions } from '#/api/management/platform-config';
import { getMaterialsByIds } from '#/api/materials/all';
import { getUserOptions } from '#/api/system/user';
import countriesData from '#/data/facebook_countries.json';
import localesData from '#/data/facebook_locales.json';
import specialAdCountriesData from '#/data/special_ad_countries.json';

import AdEnhancementPopover from './components/AdEnhancementPopover.vue';
import ChatToolTemplatePopover from './components/ChatToolTemplatePopover.vue';
import DeviceOsPanel from './components/DeviceOsPanel.vue';
import MaterialGroupLoadTab from './components/MaterialGroupLoadTab.vue';
import MaterialTemplateLoadTab from './components/MaterialTemplateLoadTab.vue';
import TemplateLoadTab from './components/TemplateLoadTab.vue';
import { useAdvertiser } from './composables/useAdvertiser';
import AdCreativeSelectionModal from './modals/AdCreativeSelectionModal.vue';
import ChatToolModal from './modals/ChatToolModal.vue';
import CreativeHistoryModal from './modals/CreativeHistoryModal.vue';
import MaterialGroupHistoryModal from './modals/MaterialGroupHistoryModal.vue';
import MaterialGroupSaveModal from './modals/MaterialGroupSaveModal.vue';
import MaterialSelectionModal from './modals/MaterialSelectionModal.vue';
import OriginalPostModal from './modals/OriginalPostModal.vue';
import PersonalAuthAdvertiserModal from './modals/PersonalAuthAdvertiserModal.vue';
import QueryProgressModal from './modals/QueryProgressModal.vue';
import TemplateSaveModal from './modals/TemplateSaveModal.vue';
import OverflowTooltip from '#/views/components/OverflowTooltip.vue';
import { conversionEventOptions } from './constants';

// 转化发生位置选项
const conversionLocationOptions = [
  { value: 'APP', label: '应用' },
  { value: 'WEBSITE', label: '网站' },
  { value: 'PHONE_CALL', label: '电话' },
  { value: 'MESSENGER', label: 'Messenger' },
];

// 互动目标的转化发生位置选项
const engagementConversionLocationOptions = [
  { value: 'MESSENGER', label: '消息目标位置' },
];

// 互动目标的成效目标选项
const engagementOptimizationGoalOptions = [
  { label: '对话次数最大化', value: 'CONVERSATIONS' },
  { label: '链接点击量最大化', value: 'LINK_CLICKS' },
];

const optimizationGoalOptions = ref([
  { label: '应用事件数量最大化', value: 'OFFSITE_CONVERSIONS' },
  { label: '转化价值最大化', value: 'VALUE' },
  { label: '应用安装量最大化', value: 'APP_INSTALLS' },
  { label: '链接点击量最大化', value: 'LINK_CLICKS' },
]);

const commonCallToActionOptions = [
  { value: 'ORDER_NOW', label: '立即订购' },
  { value: 'SUBSCRIBE', label: '订阅' },
  { value: 'LEARN_MORE', label: '详细了解' },
  { value: 'DOWNLOAD', label: '下载' },
  { value: 'BOOK_NOW', label: '立即预定' },
  { value: 'SHOP_NOW', label: '去逛逛' },
  { value: 'LISTEN_NOW', label: '立即收听' },
  { value: 'PLAY_GAME', label: '玩游戏' },
  { value: 'WATCH_MORE', label: '更多视频' },
  { value: 'SIGN_UP', label: '立即注册' },
];

const imageOnlyCallToActionOptions = [
  { value: 'BUY_NOW', label: '立即购买' },
  { value: 'USE_APP', label: '使用应用' },
  { value: 'INSTALL_APP', label: '立即安装' },
];

const videoOnlyCallToActionOptions = [
  { value: 'NO_BUTTON', label: '无按钮' },
  { value: 'APPLY_NOW', label: '立即申请' },
  { value: 'BUY_TICKETS', label: '购票' },
  { value: 'CONTACT_US', label: '联系我们' },
  { value: 'GET_OFFER', label: '领取优惠' },
  { value: 'GET_QUOTE', label: '立即询价' },
  { value: 'GET_SHOWTIMES', label: '查看场次信息' },
  { value: 'REQUEST_TIME', label: '预约时间' },
  { value: 'SEE_MENU', label: '查看菜单' },
];

const allCallToActionOptions = [
  ...commonCallToActionOptions,
  ...imageOnlyCallToActionOptions,
  ...videoOnlyCallToActionOptions,
];

const engagementCallToActionOptions = [
  { value: 'MESSAGE_PAGE', label: '发消息' },
];

const getCallToActionOptions = (
  filetype?: 'image' | 'video',
  isEngagement?: boolean,
) => {
  if (isEngagement) return engagementCallToActionOptions;
  if (filetype === 'image')
    return [...commonCallToActionOptions, ...imageOnlyCallToActionOptions];
  if (filetype === 'video')
    return [...commonCallToActionOptions, ...videoOnlyCallToActionOptions];
  return allCallToActionOptions;
};

function checkTitleBytes(value: string) {
  if (new TextEncoder().encode(value).length > 255) {
    message.warning({
      content: `广告标题不能超过255字节，当前字节数为${
        new TextEncoder().encode(value).length
      }`,
      key: 'title-bytes-warning',
    });
  }
}

// 发布平台 / 设备平台 / 操作系统 选项
const publisherPlatformOptions = [
  { value: 'facebook', label: 'Facebook' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'audience_network', label: 'Audience Network' },
  { value: 'messenger', label: 'Messenger' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'threads', label: 'Threads' },
] as const;

// Step management
const currentStep = ref(0);

// Step 1: Product Configuration
const selectedProducts = ref<string[][]>([]);
const selectedTasksData = shallowRef<SelectedProduct[]>([]);

const defaultCountry = computed<string>(() => {
  const regions = (selectedTasksData.value[0] as any)?.target_region;
  return Array.isArray(regions) && regions.length > 0
    ? (regions[0] as string)
    : 'ID';
});

// 任务线数据
const cascaderOptions = ref<CascaderProps['options']>([]);
const loading = ref(false);
const processingTasks = ref(false);
const aiSuggestionOpen = ref(false);
const aiSuggestionSrc = ref('');
const aiSuggestionReports = ref<
  Array<{
    _id: string;
    game_platform: string;
    type_name: string;
    created_at: string;
    report_url: string;
    status: string;
  }>
>([]);
const aiSuggestionSelectedId = ref<string | undefined>(undefined);
const aiSuggestionIframeLoading = ref(false);

const aiSuggestionSelectOptions = computed(() =>
  aiSuggestionReports.value
    .filter((r) => r.status === 'completed')
    .map((r) => ({
      label: `${r.game_platform} ${r.type_name}报告 ${dayjs(r.created_at).format('YYYY-MM-DD HH:mm')}`,
      value: r._id,
    })),
);

async function openAiSuggestion() {
  const uniquePlatforms = new Set(
    selectedProducts.value.map((item) => item[0]),
  );
  if (!uniquePlatforms.size) {
    message.warning('请先选择一个项目的任务线');
    return;
  }
  if (uniquePlatforms.size > 1) {
    message.warning('AI建议只能支持一个项目的任务线');
    return;
  }
  const platformKey = [...uniquePlatforms][0] as string;
  const gamePlatform = platformKey.split('_').slice(2).join('_');
  try {
    const res = await getAiSuggestionReportUrl({
      game_platform: gamePlatform,
      // game_platform: 'goplay11',
      report_type: 1,
    });
    const completedReports = (res.reports ?? []).filter(
      (r: any) => r.status === 'completed',
    );
    if (!completedReports.length) {
      message.warning('暂无可用的 AI 建议报告');
      return;
    }
    aiSuggestionReports.value = completedReports;
    aiSuggestionSelectedId.value = undefined;
    aiSuggestionSrc.value = '';
    aiSuggestionOpen.value = true;
  } catch {
    message.error('获取 AI 建议报告失败');
  }
}

async function handleAiReportSelect(id: string) {
  const report = aiSuggestionReports.value.find((r) => r._id === id);
  if (!report) return;
  aiSuggestionIframeLoading.value = true;
  aiSuggestionSrc.value = '';
  try {
    const minioRes = await getMinioPresignedUrl(report.report_url);
    aiSuggestionSrc.value = minioRes.url;
  } catch {
    message.error('获取报告链接失败');
  } finally {
    aiSuggestionIframeLoading.value = false;
  }
}

const aiSuggestionDownloading = ref(false);

async function downloadAiReport() {
  if (!aiSuggestionSrc.value) {
    message.warning('请先选择一份报告');
    return;
  }
  aiSuggestionDownloading.value = true;
  try {
    const [{ default: html2canvas }, { default: jsPDF }] = await Promise.all([
      import('html2canvas'),
      import('jspdf'),
    ]);

    // 将 HTML 内容加载到隐藏 iframe（同源 blob URL）以便访问 DOM
    const res = await fetch(aiSuggestionSrc.value);
    const html = await res.text();
    const blob = new Blob([html], { type: 'text/html' });
    const blobUrl = URL.createObjectURL(blob);

    const iframe = document.createElement('iframe');
    iframe.style.cssText =
      'position:fixed;top:-9999px;left:-9999px;width:1200px;height:900px;border:none;visibility:hidden';
    document.body.appendChild(iframe);

    await new Promise<void>((resolve) => {
      iframe.onload = () => resolve();
      iframe.src = blobUrl;
    });

    // 等待图片等资源渲染
    await new Promise((r) => setTimeout(r, 600));

    const iframeDoc = iframe.contentDocument!;
    const canvas = await html2canvas(iframeDoc.body, {
      useCORS: true,
      allowTaint: true,
      scale: 1.5,
      width: iframeDoc.body.scrollWidth,
      height: iframeDoc.body.scrollHeight,
      windowWidth: iframeDoc.body.scrollWidth,
    });

    const imgW = 210; // A4 宽度 mm
    const imgH = (canvas.height * imgW) / canvas.width;
    // 用内容实际高度作为页面高度，避免分页截断内容
    const pdf = new jsPDF('p', 'mm', [imgW, imgH]);
    const imgData = canvas.toDataURL('image/jpeg', 0.92);
    pdf.addImage(imgData, 'JPEG', 0, 0, imgW, imgH);

    const reportLabel =
      aiSuggestionSelectOptions.value.find(
        (o) => o.value === aiSuggestionSelectedId.value,
      )?.label ?? 'AI建议报告';
    pdf.save(`${reportLabel}.pdf`);

    document.body.removeChild(iframe);
    URL.revokeObjectURL(blobUrl);
  } catch (err) {
    console.error('PDF 下载失败，回退为下载 HTML 文件:', err);
    // 回退：直接下载 HTML 文件
    try {
      const res = await fetch(aiSuggestionSrc.value);
      const html = await res.text();
      const blob = new Blob([html], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const reportLabel =
        aiSuggestionSelectOptions.value.find(
          (o) => o.value === aiSuggestionSelectedId.value,
        )?.label ?? 'AI建议报告';
      a.href = url;
      a.download = `${reportLabel}.html`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (fallbackErr) {
      console.error('HTML 下载也失败:', fallbackErr);
      message.error('下载报告失败');
    }
  } finally {
    aiSuggestionDownloading.value = false;
  }
}
const creatingAd = ref(false);
const adCreatingCooldown = ref(false);
const compactBuilder = ref(window.matchMedia('(max-width: 1023px)').matches);
const compactBuilderQuery = window.matchMedia('(max-width: 1023px)');
const handleBuilderBreakpoint = (event: MediaQueryListEvent) => {
  compactBuilder.value = event.matches;
};
const platformAgentData = ref<AgentOptionsItem[]>([]);
const agentOptionsSearchText = ref('');
let agentOptionsRequestId = 0;

// 正式接口使用项目稳定 ID，避免搜索改变项目排序后已选路径失效。
const getPlatformOptionValue = (project: AgentOptionsItem, index: number) =>
  `platform_${project.project_id ?? index}_${project._id}`;

// 项目和代理线由后端按当前用户部门过滤，页面不再拼接两个分页列表。
const loadAgentOptions = async (
  agentName?: string,
  requestId = ++agentOptionsRequestId,
) => {
  if (requestId !== agentOptionsRequestId) return;
  loading.value = true;
  try {
    const projects = await getAgentOptions(undefined, agentName?.trim());
    if (requestId !== agentOptionsRequestId) return;

    platformAgentData.value = projects
      .filter((project) => project.agent_lines.length > 0)
      .map((project) => ({ ...project, game_platform: project._id }));
    cascaderOptions.value = platformAgentData.value.map(
      (project, projectIndex) => ({
        label: project._id,
        value: getPlatformOptionValue(project, projectIndex),
        children: project.agent_lines.map((agentLine) => ({
          label: agentLine,
          value: agentLine,
        })),
      }),
    );
  } catch {
    // 请求层统一提示错误；清空失败查询的候选，防止继续使用上次结果。
    if (requestId === agentOptionsRequestId) {
      platformAgentData.value = [];
      cascaderOptions.value = [];
    }
  } finally {
    if (requestId === agentOptionsRequestId) loading.value = false;
  }
};

const searchAgentOptions = useDebounceFn(
  (searchText: string, requestId: number) =>
    loadAgentOptions(searchText || undefined, requestId),
  400,
);

const handleCascaderSearch = (searchText: string) => {
  // 输入时立即展示加载反馈并让旧请求失效，防抖期间也不会被旧结果覆盖。
  agentOptionsSearchText.value = searchText;
  if (!searchText.trim()) {
    // 清空搜索立即恢复默认项目及本人代理线，不等待下一次输入。
    void loadAgentOptions();
    return;
  }
  loading.value = true;
  void searchAgentOptions(searchText, ++agentOptionsRequestId);
};

// Table for selected tasks
const taskColumns: TableColumnsType = [
  { title: '项目名称', dataIndex: 'projectName', width: 100 },
  { title: '投放地区', dataIndex: 'regionName', width: 95 },
  { title: '任务线名称', dataIndex: 'taskName', width: 120 },
  { title: '投放链接', dataIndex: 'url', width: 300 },
  {
    title: '像素',
    dataIndex: 'pixel_name',
    width: 140,
  },
  {
    title: '广告账户',
    key: 'advertisers',
    width: 'auto',
  },
  {
    title: '操作',
    key: 'action',
    fixed: 'right',
    width: 80,
  },
];

// 创建确认弹窗：广告系列结构表格列
const confirmSeriesColumns: TableColumnsType = [
  { title: '广告系列', dataIndex: 'name', width: 140 },
  { title: '广告组', key: 'groups', width: 200 },
  { title: '排期时间(账户时区)', dataIndex: 'schedule', width: 190 },
  { title: '系列预算', key: 'campaignBudget', width: 150 },
  { title: '组预算', key: 'adsetBudget', width: 150 },
];

const step1Data = reactive({
  seriesName: '任务线_账户_日期_序号_投手',
  groupName: '任务线_日期_序号_投手',
  adName: '系统文件名',
});

// Step 2: Advertisement Series and Ad Group Settings

// Series List Management
const seriesList = ref<SeriesData[]>([
  {
    id: '1',
    name: '系列1',
    seriesSettings: {
      purchaseType: '竞拍',
      seriesType: '销量',
      objectiveType: '广告系列预算',
      budgetType: '单日预算',
      budget: 0,
      currency: 'USD',
      targetPrice: 'LOWEST_COST_WITHOUT_CAP',
      targetValue: '',
      optimizationMethod: '标准',
      flowOptimization: '不限',
      flowOptimizationAmount: 0,
      specialAdCategories: [],
      specialAdCountries: [],
      contextualMultiAds: true,
      inventoryFilterLevel: 'RELAXED',
    },
    regionGroups: [
      {
        id: '1',
        name: '地区组1',
        deliveryPosition: '网站',
        optimizationTarget: 'OFFSITE_CONVERSIONS',
        conversionGoal: undefined,
        conversionLocation: 'WEBSITE',
        applicationId: undefined,
        objectStoreUrl: undefined,
        billingEvent: 'IMPRESSIONS',
        country: 'ID',
        language: [],
        ageRangeStart: 18,
        ageStart: 18,
        ageRangeEnd: 65,
        gender: '不限',
        publisher_platforms: undefined,
        device_platforms: undefined,
        user_os: undefined,
        isNewModelEnabled: true,
        isExpanded: false,
      },
    ],
  },
]);

const currentSeriesIndex = ref(0);

// 计算当前激活的系列Tab的key
const activeSeriesKey = computed({
  get() {
    if (seriesList.value.length === 0) {
      return '';
    }
    const idx =
      typeof currentSeriesIndex.value === 'number'
        ? currentSeriesIndex.value
        : Number(currentSeriesIndex.value);
    const series = seriesList.value[idx];
    if (!series) {
      return seriesList.value.length > 0 ? seriesList.value[0]?.id : '';
    }
    return series.id;
  },
  set(key: string) {
    const index = seriesList.value.findIndex((series) => series.id === key);
    if (index !== -1) {
      currentSeriesIndex.value = index;
    }
  },
});

// 监听系列切换，重置地区组索引
watch(currentSeriesIndex, () => {
  currentRegionGroupIndex.value = 0;
  regionGroupClone.reset();
});

watch(currentStep, (step) => {
  if (step !== 1) return;
  const country = defaultCountry.value;
  seriesList.value.forEach((series) =>
    series.regionGroups.forEach((group) => {
      if (!group.country || group.country === 'ID') group.country = country;
    }),
  );
});

const CLONE_MIN = 1;
const CLONE_MAX = 100;

// 克隆 Popover 状态工厂，系列/地区组/素材组公共逻辑
function createClonePopoverState() {
  const openMap = reactive<Record<string, boolean>>({});
  const countMap = reactive<Record<string, number>>({});
  return {
    openMap,
    getCount: (id: string) => countMap[id] ?? 1,
    setCount: (id: string, count: number) => {
      countMap[id] = count;
    },
    setOpen(id: string, open: boolean) {
      openMap[id] = open;
      if (open) countMap[id] ??= 1;
    },
    reset() {
      for (const k in openMap) delete openMap[k];
    },
  };
}

const seriesClone = createClonePopoverState();
const regionGroupClone = createClonePopoverState();

// 统一 ID 生成：取列表中最大数值 ID + 1
function generateNextId(items: { id: string }[]): string {
  return String(Math.max(0, ...items.map((item) => Number(item.id) || 0)) + 1);
}

function validateCloneCount(count: number): null | number {
  const safeCount = Math.floor(Number(count));
  if (
    !Number.isFinite(safeCount) ||
    safeCount < CLONE_MIN ||
    safeCount > CLONE_MAX
  ) {
    message.warning(`克隆数量必须在 ${CLONE_MIN}~${CLONE_MAX} 之间`);
    return null;
  }
  return safeCount;
}

function deepRawClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(toRaw(obj)));
}

function cloneSeries(seriesId: string, count: number) {
  const originalSeries = seriesList.value.find((s) => s.id === seriesId);
  if (!originalSeries) return;
  const safeCount = validateCloneCount(count);
  if (safeCount === null) return;

  for (let i = 0; i < safeCount; i++) {
    const newId = generateNextId(seriesList.value);
    const newSeries: SeriesData = deepRawClone(originalSeries);
    newSeries.id = newId;
    newSeries.name = `系列${newId}`;
    newSeries.regionGroups = (newSeries.regionGroups || []).map(
      (group, idx) => ({
        ...group,
        id: String(idx + 1),
        name: `地区组${idx + 1}`,
      }),
    );
    seriesList.value.push(newSeries);
  }
  currentSeriesIndex.value = Math.max(0, seriesList.value.length - 1);
}

function regionGroupCloneKey(seriesIndex: number | string, groupId: string) {
  return `${String(seriesIndex)}::${groupId}`;
}

function cloneRegionGroup(
  seriesIndex: number | string,
  groupId: string,
  count: number,
) {
  const idx =
    typeof seriesIndex === 'number' ? seriesIndex : Number(seriesIndex);
  const series = seriesList.value[idx];
  if (!series) return;

  const originalGroup = series.regionGroups.find((g) => g.id === groupId);
  if (!originalGroup) return;
  const safeCount = validateCloneCount(count);
  if (safeCount === null) return;

  for (let i = 0; i < safeCount; i++) {
    const newId = String(series.regionGroups.length + 1);
    const newGroup: RegionGroup = deepRawClone(originalGroup);
    newGroup.id = newId;
    newGroup.name = `地区组${newId}`;
    series.regionGroups.push(newGroup);
  }
  currentRegionGroupIndex.value = Math.max(0, series.regionGroups.length - 1);
}

// Ad group basic settings
const conversionLocation = ref('WEBSITE');
const applicationId = ref<string | undefined>(undefined);
const performanceGoal = ref('OFFSITE_CONVERSIONS');

// APP转化位置相关
type AppInfo = {
  id: string;
  name: string;
  supported_platforms: string[]; // e.g. ['ANDROID'] | ['IOS']
  store_url: string; // 主要应用商店链接
};
const selectedAdAccountId = ref<string | undefined>(undefined);
const applicationOptions = ref<AppInfo[]>([]);
const selectedApplication = ref<AppInfo | undefined>(undefined);
const applicationOptionsLoading = ref(false);
const conversionEvent = ref<string | undefined>('PURCHASE');
const adGroupAdvertiserId = ref<string | undefined>(undefined);

const scheduleStartTime = ref<Dayjs | undefined>(undefined);
const scheduleEndTime = ref<Dayjs | undefined>(undefined);

const conversionEventLabel = computed(() => {
  const currentSeries = seriesList.value[currentSeriesIndex.value];
  const seriesType = currentSeries?.seriesSettings.seriesType;

  if (seriesType === '应用推广') {
    return '应用事件';
  }
  return '转化事件';
});

// 计算价值优化选项是否可用
const isValueOptimizationDisabled = computed(() => {
  const currentSeries = seriesList.value[currentSeriesIndex.value];
  if (!currentSeries) return true;

  const seriesType = currentSeries.seriesSettings.seriesType;
  // 当广告系列目标是"应用推广
  if (seriesType === '应用推广') {
    return conversionLocation.value !== 'APP';
  }
  // 只有广告系列目标是"销量"或"潜在客户"时，价值优化才可用
  return !['潜在客户', '销量'].includes(seriesType);
});

// 计算转化事件选项列表
const currentConversionEventOptions = computed(() => {
  const currentSeries = seriesList.value[currentSeriesIndex.value];
  const seriesType = currentSeries?.seriesSettings.seriesType;

  // 如果广告系列目标是"应用推广"，只显示特定的三个选项
  if (seriesType === '应用推广') {
    return conversionEventOptions.filter((option) =>
      ['COMPLETE_REGISTRATION', 'PURCHASE', 'SUBSCRIBE'].includes(option.value),
    );
  }

  return conversionEventOptions;
});

// 当前广告系列目标是否为互动
const isEngagementSeries = computed(() => {
  const currentSeries = seriesList.value[currentSeriesIndex.value];
  return currentSeries?.seriesSettings.seriesType === '互动';
});

// 根据广告系列目标返回对应的转化发生位置选项
const currentConversionLocationOptions = computed(() => {
  if (isEngagementSeries.value) {
    return engagementConversionLocationOptions;
  }
  return conversionLocationOptions;
});

// 判断是否需要显示转化事件
const shouldShowConversionEvent = computed(() => {
  if (isEngagementSeries.value) {
    return false;
  }
  return true;
});

// 判断应用选项是否可用
const isAppLocationDisabled = computed(() => {
  const currentSeries = seriesList.value[currentSeriesIndex.value];
  if (!currentSeries) return true;

  // 只有广告系列目标是"应用推广"时，应用选项才可用
  return currentSeries.seriesSettings.seriesType !== '应用推广';
});

// 监听广告系列目标变化，自动调整转化发生位置和转化事件
watch(
  () => seriesList.value[currentSeriesIndex.value]?.seriesSettings.seriesType,
  (newType, oldType) => {
    if (newType === '互动') {
      conversionLocation.value = 'MESSENGER';
      performanceGoal.value = 'CONVERSATIONS';
      return;
    }

    if (oldType === '互动') {
      conversionLocation.value = 'WEBSITE';
      performanceGoal.value = 'OFFSITE_CONVERSIONS';
      if (!conversionEvent.value) {
        conversionEvent.value = 'PURCHASE';
      }
    }

    if (newType !== '应用推广' && conversionLocation.value === 'APP') {
      conversionLocation.value = 'WEBSITE';
    }

    if (newType === '应用推广') {
      const allowedEvents = ['PURCHASE', 'COMPLETE_REGISTRATION', 'SUBSCRIBE'];
      if (
        !conversionEvent.value ||
        !allowedEvents.includes(conversionEvent.value)
      ) {
        conversionEvent.value = 'PURCHASE';
      }
    }
  },
);

// 已选广告账户列表
const allSelectedAdAccounts = computed(() => {
  const map = new Map<string, { id: string; name: string; personId: string }>();
  selectedTasksData.value.forEach((task) => {
    (task.advertisers || []).forEach((adv: any) => {
      if (adv.account && !map.has(adv.account)) {
        map.set(adv.account, {
          id: adv.account,
          name: adv.ad_account_name,
          personId: adv.personId || '',
        });
      }
    });
  });
  return [...map.values()];
});

// 从缓存数据中加载指定账号的应用列表
// 先从 task.accounts 找（初始加载数据），找不到再从 task.advertisers 找（弹窗筛选后选中的数据）
function loadApplicationsFromCache(accountId: string) {
  const seen = new Set<string>();
  const apps: AppInfo[] = [];
  for (const task of selectedTasksData.value) {
    const accountInAccounts = (task.accounts || []).find(
      (acc: any) => acc.ad_account_id === accountId,
    );
    const accountInAdvertisers = (task.advertisers || []).find(
      (adv: any) => (adv.accountId || adv.account) === accountId,
    );
    const sourceApps =
      accountInAccounts?.applications ||
      accountInAdvertisers?.applications ||
      [];
    for (const app of sourceApps) {
      if (seen.has(app.id)) continue;
      seen.add(app.id);
      const supported_platforms = (app.supported_platforms || []).map(
        (p: string) => p.toUpperCase(),
      );
      const store_url = (app.object_store_urls || {})['google_play'] || '';
      apps.push({ id: app.id, name: app.name, supported_platforms, store_url });
    }
  }
  applicationOptions.value = apps;
}

// 按应用 ID 从已选任务数据反查商店链接：导入模板后 applicationOptions 未加载、
// selectedApplication 为空，提交时以此兜底，避免 object_store_url 丢失。
function resolveAppStoreUrl(appId?: string): string | undefined {
  if (!appId) return undefined;
  for (const task of selectedTasksData.value) {
    for (const src of [...(task.accounts || []), ...(task.advertisers || [])]) {
      const app = (src.applications || []).find((a: any) => a.id === appId);
      const url = app && (app.object_store_urls || {}).google_play;
      if (url) return url;
    }
  }
  return undefined;
}

// 监听转化发生位置变化
watch(conversionLocation, (val) => {
  if (val !== 'APP') {
    selectedAdAccountId.value = undefined;
    selectedApplication.value = undefined;
    applicationId.value = undefined;
    applicationOptions.value = [];
  }
});

// 选中 applicationId 后自动同步 selectedApplication 并设置 DeviceOsPanel
watch(applicationId, (appId) => {
  const app = appId
    ? applicationOptions.value.find((a) => a.id === appId)
    : undefined;
  selectedApplication.value = app;
  if (!app) return;

  const os = app.supported_platforms?.[0]?.toUpperCase();
  if (!os) return;

  seriesList.value.forEach((series) => {
    series.regionGroups.forEach((group) => {
      if (os === 'ANDROID') {
        group.device_platforms = ['mobile'];
        group.user_os = ['Android'];
        group.user_device = ['Android_Smartphone', 'Android_Tablet'];
        group.user_os_version = undefined;
      } else if (os === 'IOS') {
        group.device_platforms = ['mobile'];
        group.user_os = ['iOS'];
        group.user_device = ['iPhone', 'iPad', 'iPod'];
        group.user_os_version = undefined;
      }
    });
  });
  seriesList.value = [...seriesList.value];
});

// Popover 广告账户 + 应用
const appComboOpen = ref(false);
const tempAdAccountId = ref<string | undefined>(undefined);
const tempApplicationId = ref<string | undefined>(undefined);

const appComboDisplayText = computed(() => {
  if (!applicationId.value) return '请选择应用';
  const app = applicationOptions.value.find(
    (a) => a.id === applicationId.value,
  );
  return app ? `${app.name}` : applicationId.value;
});

function handleAppComboOpenChange(open: boolean) {
  appComboOpen.value = open;
  if (open) {
    tempAdAccountId.value = selectedAdAccountId.value;
    tempApplicationId.value = applicationId.value;
    if (applicationOptions.value.length === 0 && tempAdAccountId.value) {
      loadApplicationsFromCache(tempAdAccountId.value);
    }
  }
}

// 切换账号时重新加载该账号的应用列表
function handleTempAccountChange(accountId: any) {
  tempApplicationId.value = undefined;
  applicationOptions.value = [];
  if (accountId) loadApplicationsFromCache(String(accountId));
}

function handleAppComboConfirm() {
  selectedAdAccountId.value = tempAdAccountId.value;
  applicationId.value = tempApplicationId.value;
  appComboOpen.value = false;
}

function handleAppComboClear(e: Event) {
  e.stopPropagation();
  selectedAdAccountId.value = undefined;
  applicationId.value = undefined;
  selectedApplication.value = undefined;
}

// 刷新应用列表（调用同步接口，使用 Popover 内的临时账户选择）
async function handleRefreshApplications() {
  if (!tempAdAccountId.value) {
    message.warning('请先选择广告账户');
    return;
  }
  const accInfo = allSelectedAdAccounts.value.find(
    (a) => a.id === tempAdAccountId.value,
  );
  if (!accInfo?.personId) {
    message.warning('未找到该账户对应的个号信息');
    return;
  }
  applicationOptionsLoading.value = true;
  try {
    const res: any = await syncAdAccountApplications({
      items: [
        {
          personal_id: accInfo.personId,
          ad_account_ids: [tempAdAccountId.value],
        },
      ],
      force_refresh: true,
    });
    const items: any[] = res?.items || [];
    const errorMessages = items
      .filter((item: any) => item.error)
      .map((item: any) => item.error);
    if (errorMessages.length > 0) {
      message.warning(errorMessages.join('；'));
      return;
    }
    const newApps: AppInfo[] = items.flatMap((item: any) =>
      (item.applications || []).map((app: any) => {
        const supported_platforms: string[] = (
          app.supported_platforms || []
        ).map((p: string) => p.toUpperCase());
        const storeUrls: Record<string, string> = app.object_store_urls || {};
        const store_url = storeUrls['google_play'] || '';
        return { id: app.id, name: app.name, supported_platforms, store_url };
      }),
    );
    if (newApps.length > 0) {
      applicationOptions.value = newApps;
      message.success('应用列表已刷新');
    } else {
      message.warning('未获取到应用数据');
    }
  } catch {
  } finally {
    applicationOptionsLoading.value = false;
  }
}

// 监听成效目标变化，自动调整转化事件
watch(performanceGoal, (newGoal, oldGoal) => {
  if (oldGoal === 'CONVERSATIONS' && newGoal === 'OFFSITE_CONVERSIONS') return;
  if (['LINK_CLICKS', 'OFFSITE_CONVERSIONS'].includes(newGoal)) {
    conversionEvent.value = undefined;
  }
  // 如果是转化价值最大化，且当前转化事件不在允许的列表中，重置为PURCHASE
  else if (newGoal === 'VALUE') {
    const allowedEvents = ['PURCHASE', 'COMPLETE_REGISTRATION', 'SUBSCRIBE'];
    if (
      !conversionEvent.value ||
      !allowedEvents.includes(conversionEvent.value)
    ) {
      conversionEvent.value = 'PURCHASE';
    }
  } else if (!conversionEvent.value) {
    conversionEvent.value = 'PURCHASE';
  }
});

// 监听特殊广告类别及其国家变化
watch(
  () =>
    seriesList.value.map((s) => ({
      catLen: s.seriesSettings.specialAdCategories?.length ?? 0,
      countries: s.seriesSettings.specialAdCountries ?? [],
    })),
  (newArr, oldArr) => {
    newArr.forEach((cur, i) => {
      const series = seriesList.value[i];
      if (!series) return;

      // 1. 特殊广告类别从无到有：锁定年龄为 18-65
      const justEnabled = cur.catLen > 0 && !oldArr?.[i]?.catLen;
      if (justEnabled) {
        series.regionGroups.forEach((group) => {
          group.ageRangeStart = 18;
          group.ageStart = 18;
          group.ageRangeEnd = 65;
        });
      }

      // 2. 有特殊广告类别时，国家变化同步回填地区组
      if (cur.catLen > 0) {
        const firstCountry = cur.countries[0] ?? undefined;
        series.regionGroups.forEach((group) => {
          group.country = firstCountry;
        });
      }
    });
  },
  { deep: true },
);

function addRegionGroup() {
  const currentSeries = seriesList.value[currentSeriesIndex.value];
  if (currentSeries) {
    const newId = String(currentSeries.regionGroups.length + 1);
    const newGroup: RegionGroup = {
      id: newId,
      name: `地区组${newId}`,
      deliveryPosition: '网站',
      optimizationTarget: 'OFFSITE_CONVERSIONS',
      conversionGoal: undefined,
      conversionLocation: 'APP',
      applicationId: undefined,
      objectStoreUrl: undefined,
      billingEvent: 'IMPRESSIONS', // 默认展示次数
      country: currentSeries.seriesSettings.specialAdCategories?.length
        ? undefined
        : defaultCountry.value,
      language: [],
      ageRangeStart: 18,
      ageStart: 18,
      ageRangeEnd: 65,
      gender: '不限',
      publisher_platforms: undefined,
      device_platforms: undefined,
      user_os: undefined,
      isNewModelEnabled: true,
      isExpanded: false,
    };
    currentSeries.regionGroups.push(newGroup);
    currentRegionGroupIndex.value = currentSeries.regionGroups.length - 1;
  }
}

// Series Management Functions
function addSeries() {
  const newId = generateNextId(seriesList.value);
  seriesList.value.push({
    id: newId,
    name: `系列${newId}`,
    seriesSettings: {
      purchaseType: '竞拍',
      seriesType: '销量',
      objectiveType: '广告系列预算',
      budgetType: '单日预算',
      budget: 0,
      currency: 'USD',
      targetPrice: 'LOWEST_COST_WITHOUT_CAP',
      targetValue: '',
      optimizationMethod: '标准',
      flowOptimization: '不限',
      flowOptimizationAmount: 0,
      specialAdCategories: [],
      specialAdCountries: [],
      contextualMultiAds: true,
      inventoryFilterLevel: 'RELAXED',
    },
    regionGroups: [
      {
        id: '1',
        name: '地区组1',
        deliveryPosition: '网站',
        optimizationTarget: 'OFFSITE_CONVERSIONS',
        conversionGoal: undefined,
        conversionLocation: 'APP',
        applicationId: undefined,
        objectStoreUrl: undefined,
        billingEvent: 'IMPRESSIONS',
        country: defaultCountry.value,
        language: [],
        ageRangeStart: 18,
        ageStart: 18,
        ageRangeEnd: 65,
        gender: '不限',
        publisher_platforms: undefined,
        device_platforms: undefined,
        user_os: undefined,
        isNewModelEnabled: true,
        isExpanded: false,
      },
    ],
  });
  currentSeriesIndex.value = seriesList.value.length - 1;
}

function applySettingsConfig(cfg: any) {
  if (!cfg) return;

  // v2: 全量模板（覆盖所有系列 + 所有地区组 + 全局设置）
  if (cfg?.version === 2 && Array.isArray(cfg.seriesList)) {
    const globals = cfg.globals || {};

    if (globals.conversionLocation !== undefined) {
      conversionLocation.value = globals.conversionLocation || 'WEBSITE';
    }
    if (globals.performanceGoal !== undefined) {
      performanceGoal.value = globals.performanceGoal || performanceGoal.value;
    }
    if (globals.conversionEvent !== undefined) {
      conversionEvent.value = globals.conversionEvent || undefined;
    }
    if (globals.applicationId !== undefined) {
      applicationId.value = globals.applicationId || undefined;
    }
    scheduleStartTime.value = globals.schedule_start_time
      ? dayjs.tz(globals.schedule_start_time)
      : undefined;
    scheduleEndTime.value = globals.schedule_end_time
      ? dayjs.tz(globals.schedule_end_time)
      : undefined;

    // normalize ids/names + fill minimal defaults
    const normalizedSeriesList: SeriesData[] = (
      cfg.seriesList as SeriesData[]
    ).map((s: any, seriesIdx: number) => {
      const seriesId = String(seriesIdx + 1);
      const seriesSettings = s?.seriesSettings || {};
      const regionGroupsRaw = Array.isArray(s?.regionGroups)
        ? s.regionGroups
        : [];
      const normalizedRegionGroups: RegionGroup[] = regionGroupsRaw.map(
        (g: any, groupIdx: number) => {
          const groupId = String(groupIdx + 1);
          return {
            id: groupId,
            name: g?.name || `地区组${groupId}`,
            deliveryPosition: g?.deliveryPosition ?? '网站',
            optimizationTarget: g?.optimizationTarget ?? 'OFFSITE_CONVERSIONS',
            conversionGoal: g?.conversionGoal,
            conversionLocation: g?.conversionLocation ?? 'WEBSITE',
            applicationId: g?.applicationId,
            objectStoreUrl: g?.objectStoreUrl,
            billingEvent: g?.billingEvent ?? 'IMPRESSIONS',
            country: g?.country ?? 'ID',
            language: g?.language,
            ageRangeStart: Number(g?.ageRangeStart ?? 18),
            ageStart: Number(g?.ageStart ?? 18),
            ageRangeEnd: Number(g?.ageRangeEnd ?? 65),
            gender: g?.gender ?? '不限',
            publisher_platforms: g?.publisher_platforms,
            device_platforms: g?.device_platforms,
            user_os: g?.user_os,
            user_device: g?.user_device,
            user_os_version: g?.user_os_version,
            isNewModelEnabled: !!g?.isNewModelEnabled,
            isExpanded: !!g?.isExpanded,
          } as RegionGroup;
        },
      );

      return {
        id: seriesId,
        name: s?.name || `系列${seriesId}`,
        seriesSettings: {
          purchaseType: seriesSettings.purchaseType ?? '竞拍',
          seriesType: seriesSettings.seriesType ?? '销量',
          objectiveType: seriesSettings.objectiveType ?? '广告系列预算',
          budgetType: seriesSettings.budgetType ?? '单日预算',
          budget: Number(seriesSettings.budget ?? 0),
          currency: seriesSettings.currency ?? 'USD',
          targetPrice: normalizeBidStrategy(seriesSettings.targetPrice),
          targetValue: seriesSettings.targetValue ?? '',
          optimizationMethod: seriesSettings.optimizationMethod ?? '标准',
          flowOptimization: seriesSettings.flowOptimization ?? '不限',
          flowOptimizationAmount: Number(
            seriesSettings.flowOptimizationAmount ?? 0,
          ),
          specialAdCategories: seriesSettings.specialAdCategories ?? [],
          specialAdCountries: seriesSettings.specialAdCountries ?? [],
          contextualMultiAds: seriesSettings.contextualMultiAds ?? true,
          inventoryFilterLevel:
            seriesSettings.inventoryFilterLevel ?? 'RELAXED',
        },
        regionGroups:
          normalizedRegionGroups.length > 0
            ? normalizedRegionGroups
            : [
                {
                  id: '1',
                  name: '地区组1',
                  deliveryPosition: '网站',
                  optimizationTarget: 'OFFSITE_CONVERSIONS',
                  conversionGoal: undefined,
                  conversionLocation: 'WEBSITE',
                  applicationId: undefined,
                  objectStoreUrl: undefined,
                  billingEvent: 'IMPRESSIONS',
                  country: 'ID',
                  language: [],
                  ageRangeStart: 18,
                  ageStart: 18,
                  ageRangeEnd: 65,
                  gender: '不限',
                  publisher_platforms: undefined,
                  device_platforms: undefined,
                  user_os: undefined,
                  user_device: undefined,
                  user_os_version: undefined,
                  isNewModelEnabled: true,
                  isExpanded: false,
                } as RegionGroup,
              ],
      } as SeriesData;
    });

    seriesList.value =
      normalizedSeriesList.length > 0 > 0
        ? normalizedSeriesList
        : ([
            {
              id: '1',
              name: '系列1',
              seriesSettings: {
                purchaseType: '竞拍',
                seriesType: '销量',
                objectiveType: '广告系列预算',
                budgetType: '单日预算',
                budget: 0,
                currency: 'USD',
                targetPrice: 'LOWEST_COST_WITHOUT_CAP',
                targetValue: '',
                optimizationMethod: '标准',
                flowOptimization: '不限',
                flowOptimizationAmount: 0,
                specialAdCategories: [],
                specialAdCountries: [],
                contextualMultiAds: true,
                inventoryFilterLevel: 'RELAXED',
              },
              regionGroups: [
                {
                  id: '1',
                  name: '地区组1',
                  deliveryPosition: '网站',
                  optimizationTarget: 'OFFSITE_CONVERSIONS',
                  conversionGoal: undefined,
                  conversionLocation: 'WEBSITE',
                  applicationId: undefined,
                  objectStoreUrl: undefined,
                  billingEvent: 'IMPRESSIONS',
                  country: 'ID',
                  language: [],
                  ageRangeStart: 18,
                  ageStart: 18,
                  ageRangeEnd: 65,
                  gender: '不限',
                  publisher_platforms: undefined,
                  device_platforms: undefined,
                  user_os: undefined,
                  user_device: undefined,
                  user_os_version: undefined,
                  isNewModelEnabled: true,
                  isExpanded: false,
                },
              ],
            },
          ] as SeriesData[]);

    currentSeriesIndex.value = 0;
    currentRegionGroupIndex.value = 0;
    return;
  }

  const seriesCfg = cfg.series || {};
  if (seriesList.value.length === 0) {
    seriesList.value.push({
      id: '1',
      name: '系列1',
      seriesSettings: {
        purchaseType: '竞拍',
        seriesType: '销量',
        objectiveType: '广告系列预算',
        budgetType: '单日预算',
        budget: 0,
        currency: 'USD',
        targetPrice: 'LOWEST_COST_WITHOUT_CAP',
        targetValue: '',
        optimizationMethod: '标准',
        flowOptimization: '不限',
        flowOptimizationAmount: 0,
        specialAdCategories: [],
        specialAdCountries: [],
        contextualMultiAds: true,
        inventoryFilterLevel: 'RELAXED',
      },
      regionGroups: [],
    });
    currentSeriesIndex.value = 0;
  }

  const seriesIdx =
    typeof currentSeriesIndex.value === 'number'
      ? currentSeriesIndex.value
      : Number(currentSeriesIndex.value);
  const currentSeries =
    seriesList.value[seriesIdx] ?? (seriesList.value[0] as SeriesData);

  if (seriesCfg) {
    Object.assign(currentSeries.seriesSettings, {
      purchaseType:
        seriesCfg.purchaseType ?? currentSeries.seriesSettings.purchaseType,
      seriesType:
        seriesCfg.seriesType ?? currentSeries.seriesSettings.seriesType,
      objectiveType:
        seriesCfg.objectiveType ?? currentSeries.seriesSettings.objectiveType,
      budgetType:
        seriesCfg.budgetType ?? currentSeries.seriesSettings.budgetType,
      budget: seriesCfg.budget ?? currentSeries.seriesSettings.budget,
      currency: seriesCfg.currency ?? currentSeries.seriesSettings.currency,
      targetPrice: normalizeBidStrategy(
        seriesCfg.targetPrice ?? currentSeries.seriesSettings.targetPrice,
      ),
      targetValue:
        seriesCfg.targetValue ?? currentSeries.seriesSettings.targetValue,
      optimizationMethod:
        seriesCfg.optimizationMethod ??
        currentSeries.seriesSettings.optimizationMethod,
      flowOptimization:
        seriesCfg.flowOptimization ??
        currentSeries.seriesSettings.flowOptimization,
      flowOptimizationAmount:
        seriesCfg.flowOptimizationAmount ??
        currentSeries.seriesSettings.flowOptimizationAmount,
      specialAdCategories:
        seriesCfg.specialAdCategories ??
        currentSeries.seriesSettings.specialAdCategories ??
        [],
      specialAdCountries:
        seriesCfg.specialAdCountries ??
        currentSeries.seriesSettings.specialAdCountries ??
        [],
    });
  }

  const adGroupCfg = cfg.adGroup || {};
  if (adGroupCfg.conversionLocation) {
    conversionLocation.value = adGroupCfg.conversionLocation;
  }
  if (adGroupCfg.performanceGoal) {
    performanceGoal.value = adGroupCfg.performanceGoal;
  }
  if (adGroupCfg.conversionEvent !== undefined) {
    conversionEvent.value = adGroupCfg.conversionEvent;
  }

  if (adGroupCfg.applicationId !== undefined) {
    applicationId.value = adGroupCfg.applicationId || undefined;
  }

  if (adGroupCfg.schedule_start_time) {
    scheduleStartTime.value = dayjs.tz(adGroupCfg.schedule_start_time);
  }
  if (adGroupCfg.schedule_end_time) {
    scheduleEndTime.value = dayjs.tz(adGroupCfg.schedule_end_time);
  }

  const regionCfg = cfg.regionGroup || {};
  if (currentSeries.regionGroups.length === 0) {
    currentSeries.regionGroups.push({
      id: '1',
      name: '地区组1',
      deliveryPosition: '网站',
      optimizationTarget: 'OFFSITE_CONVERSIONS',
      conversionGoal: undefined,
      conversionLocation: 'WEBSITE',
      applicationId: undefined,
      objectStoreUrl: undefined,
      billingEvent: 'IMPRESSIONS',
      country: 'ID',
      language: [],
      ageRangeStart: 18,
      ageStart: 18,
      ageRangeEnd: 65,
      gender: '不限',
      publisher_platforms: undefined,
      device_platforms: undefined,
      user_os: undefined,
      user_device: undefined,
      isNewModelEnabled: true,
      isExpanded: false,
    });
    currentRegionGroupIndex.value = 0;
  }

  const groupIdx =
    typeof currentRegionGroupIndex.value === 'number'
      ? currentRegionGroupIndex.value
      : Number(currentRegionGroupIndex.value);
  const currentGroup =
    (currentSeries.regionGroups[groupIdx] as RegionGroup | undefined) ??
    (currentSeries.regionGroups[0] as RegionGroup);
  Object.assign(currentGroup, {
    deliveryPosition:
      regionCfg.deliveryPosition ?? currentGroup.deliveryPosition,
    optimizationTarget:
      regionCfg.optimizationTarget ?? currentGroup.optimizationTarget,
    billingEvent: regionCfg.billingEvent ?? currentGroup.billingEvent,
    conversionGoal: regionCfg.conversionGoal ?? currentGroup.conversionGoal,
    conversionLocation:
      regionCfg.conversionLocation ?? currentGroup.conversionLocation,
    applicationId: regionCfg.applicationId ?? currentGroup.applicationId,
    objectStoreUrl: regionCfg.objectStoreUrl ?? currentGroup.objectStoreUrl,
    country: regionCfg.country ?? currentGroup.country,
    language: regionCfg.language ?? currentGroup.language,
    ageRangeStart: regionCfg.ageRangeStart ?? currentGroup.ageRangeStart,
    ageStart: regionCfg.ageStart ?? currentGroup.ageStart,
    ageRangeEnd: regionCfg.ageRangeEnd ?? currentGroup.ageRangeEnd,
    gender: regionCfg.gender ?? currentGroup.gender,
    publisher_platforms:
      regionCfg.publisher_platforms ?? currentGroup.publisher_platforms,
    device_platforms:
      regionCfg.device_platforms ?? currentGroup.device_platforms,
    user_os: regionCfg.user_os ?? currentGroup.user_os,
    user_device: regionCfg.user_device ?? currentGroup.user_device,
    user_os_version: regionCfg.user_os_version ?? currentGroup.user_os_version,
    isNewModelEnabled:
      regionCfg.isNewModelEnabled ?? currentGroup.isNewModelEnabled,
    isExpanded: regionCfg.isExpanded ?? currentGroup.isExpanded,
  });

  if (
    (adGroupCfg.applicationId === undefined || !adGroupCfg.applicationId) &&
    regionCfg.applicationId !== undefined
  ) {
    applicationId.value = regionCfg.applicationId || undefined;
  }
}

function deleteSeries(seriesId: string) {
  const index = seriesList.value.findIndex((series) => series.id === seriesId);
  if (index === -1) return;

  if (seriesList.value.length <= 1) {
    message.warning('至少需要保留一个广告系列，无法删除');
    return;
  }

  seriesList.value.splice(index, 1);

  // 如果当前索引超出范围，调整到有效范围
  if (currentSeriesIndex.value >= seriesList.value.length) {
    currentSeriesIndex.value = Math.max(0, seriesList.value.length - 1);
  }

  message.success('删除成功');
}

function handleTabEdit(targetKey: any, action: any) {
  if (action === 'add') {
    addSeries();
  }
}

// Region Group Tab Management
const currentRegionGroupIndex = ref<number | string>(0);

const activeRegionGroupKey = computed({
  get() {
    const currentSeries = seriesList.value[currentSeriesIndex.value];
    if (!currentSeries || currentSeries.regionGroups.length === 0) {
      return '';
    }
    const idx =
      typeof currentRegionGroupIndex.value === 'number'
        ? currentRegionGroupIndex.value
        : Number(currentRegionGroupIndex.value);
    const group = currentSeries.regionGroups[idx];
    if (!group) {
      return currentSeries.regionGroups.length > 0
        ? `${currentSeries.id}-${currentSeries.regionGroups[0]?.id}`
        : '';
    }
    return `${currentSeries.id}-${group.id}`;
  },
  set(key: string) {
    const currentSeries = seriesList.value[currentSeriesIndex.value];
    if (!currentSeries) return;
    const index = currentSeries.regionGroups.findIndex(
      (group) => `${currentSeries.id}-${group.id}` === key,
    );
    if (index !== -1) {
      currentRegionGroupIndex.value = index;
    }
  },
});

// Function to handle region group tab edit operations
function handleRegionGroupTabEdit(targetKey: any, action: any) {
  const currentSeries = seriesList.value[currentSeriesIndex.value];
  if (currentSeries && action === 'add') {
    addRegionGroup();
  }
}

// Function to delete a region group
function deleteRegionGroup(seriesIndex: number | string, groupId: string) {
  const idx =
    typeof seriesIndex === 'number' ? seriesIndex : Number(seriesIndex);
  const series = seriesList.value[idx];
  if (!series) return;

  const index = series.regionGroups.findIndex((group) => group.id === groupId);
  if (index === -1) return;

  if (series.regionGroups.length <= 1) {
    message.warning('每个广告系列至少需要保留一个地区组，无法删除');
    return;
  }

  series.regionGroups.splice(index, 1);
  if (Number(currentRegionGroupIndex.value) >= series.regionGroups.length) {
    currentRegionGroupIndex.value = Math.max(0, series.regionGroups.length - 1);
  }
  message.success('删除成功');
}

// Function to handle age range start change
function handleAgeRangeStartChange(group: RegionGroup) {
  // If age range end is less than new start, set it to start
  if (group.ageRangeEnd < group.ageRangeStart) {
    group.ageRangeEnd = group.ageRangeStart;
  }
  // If age start is less than new range start, set it to range start
  if (group.ageStart < group.ageRangeStart) {
    group.ageStart = group.ageRangeStart;
  }
}

// Function to handle age start change
function handleAgeStartChange(group: RegionGroup) {
  // If age range end is less than new age start, set it to age start
  if (group.ageRangeEnd < group.ageStart) {
    group.ageRangeEnd = group.ageStart;
  }
}

// Build an age list from start to 65 (inclusive)
function buildAges(start: number) {
  const ages: number[] = [];
  for (let i = start; i <= 65; i++) {
    ages.push(i);
  }
  return ages;
}

// Step 4: Material Upload — 素材组管理
const materialGroups = ref<MaterialGroup[]>([
  {
    id: '1',
    name: '素材组1',
    materials: [],
    selectedIds: [],
    binding: { type: 'random' },
  },
]);
const activeMaterialGroupKey = ref<string>('1');
const materialGroupClone = createClonePopoverState();

// 当前激活素材组
const currentMaterialGroup = computed(() =>
  materialGroups.value.find((g) => g.id === activeMaterialGroupKey.value),
);

// 所有素材组的广告总数
const allMaterials = computed(() =>
  materialGroups.value.flatMap((g) => g.materials),
);

// 创意增强默认值
function defaultEnhancement(): CreativeEnhancement {
  return {
    show_summary: true,
    inline_comment: true,
    enhance_cta: true,
    reveal_details_over_time: true,
    show_destination_blurbs: true,
    image_brightness_and_contrast: true,
    image_templates: false,
    image_touchups: false,
    add_music: true,
    image_animation: false,
    video_filtering: false,
    detail_to_layout: false,
    video_auto_crop: false,
    text_optimizations: true,
    text_transformation_types: true,
    website_destination_optimization: true,
  };
}

// 统一初始化 enhancement，覆盖选择/历史/复用/追加所有来源路径
watch(
  () => allMaterials.value.map((m) => m.id).join(','),
  () => {
    allMaterials.value.forEach((m) => {
      if (!m.isOriginalPost && !m.enhancement) {
        m.enhancement = defaultEnhancement();
      }
    });
  },
  { immediate: true },
);

// uploadedMaterials / selectedMaterials 指向当前激活素材组，保持下方所有函数兼容
const uploadedMaterials = computed({
  get: () => currentMaterialGroup.value?.materials ?? [],
  set: (val: MaterialItem[]) => {
    if (currentMaterialGroup.value) currentMaterialGroup.value.materials = val;
  },
});
const selectedMaterials = computed({
  get: () => currentMaterialGroup.value?.selectedIds ?? [],
  set: (val: string[]) => {
    if (currentMaterialGroup.value)
      currentMaterialGroup.value.selectedIds = val;
  },
});
const showMaterialCheckboxes = ref(false); // 控制是否显示广告的 checkbox

// 预览模式状态（默认预览模式，不显示checkbox）
const isPreviewMode = ref(false);

// 框选功能相关状态
const isSelecting = ref(false);
const selectionBox = ref({
  startX: 0,
  startY: 0,
  endX: 0,
  endY: 0,
});
const materialsContainer = ref<HTMLElement | HTMLElement[]>();
const activeContainer = ref<HTMLElement | null>(null);
const selectionStartSelected = ref<Set<string>>(new Set());

// Advertiser Selection Modal
const showAdvertiserModal = ref(false);
const currentTaskIndex = ref<number>(-1);

const { handlePersonAccountChange: _handlePersonAccountChange } =
  useAdvertiser();

function openAdvertiserModal(index: number) {
  currentTaskIndex.value = index;
  showAdvertiserModal.value = true;
}

function handleAdvertiserConfirm(advertisers: AdvertiserItem[]) {
  if (currentTaskIndex.value >= 0 && advertisers.length > 0) {
    const taskData = selectedTasksData.value[currentTaskIndex.value];
    if (taskData) {
      const currentAdvertisers = taskData.advertisers || [];
      const existingIds = new Set(currentAdvertisers.map((a) => a.id));
      const newAdvertisers = advertisers
        .filter((adv) => !existingIds.has(adv.id))
        .map((adv) => ({
          ...adv,
          accountId: adv.account || adv.accountId || adv.id,
        }));
      const newTaskData = {
        ...taskData,
        advertisers: [...currentAdvertisers, ...newAdvertisers],
      };
      selectedTasksData.value = selectedTasksData.value.map((item, i) =>
        i === currentTaskIndex.value ? newTaskData : item,
      );
    }
  }
  showAdvertiserModal.value = false;
  currentTaskIndex.value = -1;
}

function removeAdvertiser(taskIndex: number, advertiserId: string) {
  const taskData = selectedTasksData.value[taskIndex];
  if (taskData && taskData.advertisers) {
    const newTaskData = {
      ...taskData,
      advertisers: taskData.advertisers.filter(
        (adv: any) => adv.id !== advertiserId,
      ),
    };
    selectedTasksData.value = selectedTasksData.value.map((item, i) =>
      i === taskIndex ? newTaskData : item,
    );
  }
}

// 个号变更处理:户跟着个号走(回填该个号之前选过的账户,没有为空),
// 像素跟着户走,主页默认代理线分配的,没有为空
async function handlePersonAccountChange(
  taskIndex: number,
  advIndex: number,
  personName: string | undefined,
  keepAccount = false,
) {
  const taskData = selectedTasksData.value[taskIndex];
  if (!taskData || !taskData.advertisers) return;

  const advertiser = taskData.advertisers[advIndex];
  if (!advertiser) return;

  // 记住旧个号下选的账户
  if (advertiser.personAccountName && advertiser.account) {
    (advertiser._accountByPerson ??= {})[advertiser.personAccountName] =
      advertiser.account;
  }

  advertiser.personAccountName = personName;

  if (keepAccount) {
    // 批量设置明确指定"该账户配该个号":账户不动,直接绑定
    if (personName && advertiser.account) {
      (advertiser._accountByPerson ??= {})[personName] = advertiser.account;
    }
  } else {
    const rememberedId = personName
      ? advertiser._accountByPerson?.[personName]
      : undefined;
    const remembered = rememberedId
      ? taskData.accounts?.find(
          (acc: any) => acc.ad_account_id === rememberedId,
        )
      : undefined;
    if (remembered) {
      // 回填账户,像素等随之重算(handleAccountChange 会保留当前个号)
      handleAccountChange(taskIndex, advIndex, rememberedId);
    } else {
      advertiser.account = undefined;
      advertiser.accountId = undefined;
      advertiser.accountName = undefined;
      advertiser.name = undefined;
      advertiser.assigned_page_id = undefined;
      advertiser.pixelOptions = [];
      advertiser.selectedPixel = undefined;
      advertiser.pixel = undefined;
    }
  }

  await _handlePersonAccountChange(advertiser, personName);

  advertiser.personId = advertiser.selectedPersonId;
  advertiser.publicPage = advertiser.publicPageOptions?.find(
    (page: any) => page.id === advertiser.selectedPublicPage,
  )?.name;

  selectedTasksData.value = [...selectedTasksData.value];
}

// 获取广告主的过滤后公共主页
function getFilteredPublicPagesForAdvertiser(advertiser: any) {
  if (!advertiser.publicPageOptions) {
    return [];
  }
  return advertiser.publicPageOptions.filter(
    (page: any) => page.personName === advertiser.personAccountName,
  );
}

function getAccountOptions(record: any, adv: any) {
  const accounts: any[] = adv.accountSearchOptions ?? record.accounts ?? [];
  if (
    adv.account &&
    !accounts.find((a: any) => a.ad_account_id === adv.account)
  ) {
    return [
      {
        ad_account_id: adv.account,
        ad_account_name: adv.accountName || adv.account,
      },
      ...accounts,
    ];
  }
  return accounts;
}

// 账户下拉后端搜索：限定在该行个号/像素下搜（无像素不传像素），清空关键字恢复默认选项
let accountSearchTimer: null | ReturnType<typeof setTimeout> = null;

function onAccountSearch(record: any, adv: any, value: string) {
  if (accountSearchTimer) clearTimeout(accountSearchTimer);
  const kw = (value || '').trim();
  if (!kw) {
    adv.accountSearchOptions = undefined;
    selectedTasksData.value = [...selectedTasksData.value];
    return;
  }
  accountSearchTimer = setTimeout(async () => {
    const resp = await batchQueryMissionLineInfo(
      [
        {
          task_name: record.projectName || '',
          subtask_name: record.taskName || '',
        },
      ],
      1,
      15,
      {
        ...(/^\d+$/.test(kw) ? { account_id: [kw] } : { account_name: [kw] }),
        ...(adv.personAccountName
          ? { person_name: adv.personAccountName }
          : {}),
        ...(adv.pixel ? { pixel_name_filter: adv.pixel } : {}),
      },
    );
    const items: any[] = Array.isArray(resp?.data) ? resp.data : [];
    const item = items.find((it) => it.subtask_name === record.taskName);
    adv.accountSearchOptions = item?.accounts || [];
    selectedTasksData.value = [...selectedTasksData.value];
  }, 400);
}

function handleAccountChange(
  taskIndex: number,
  advIndex: number,
  accountId: string | undefined,
) {
  const taskData = selectedTasksData.value[taskIndex];
  if (!taskData || !taskData.advertisers) return;

  const advertiser = taskData.advertisers[advIndex];
  if (!advertiser) return;

  // 清空账户:像素跟着户走一并清空,个号/主页不动
  if (!accountId) {
    if (advertiser.personAccountName && advertiser._accountByPerson) {
      delete advertiser._accountByPerson[advertiser.personAccountName];
    }
    advertiser.account = undefined;
    advertiser.accountId = undefined;
    advertiser.accountName = undefined;
    advertiser.name = undefined;
    advertiser.assigned_page_id = undefined;
    advertiser.pixelOptions = [];
    advertiser.selectedPixel = undefined;
    advertiser.pixel = undefined;
    advertiser.accountSearchOptions = undefined;
    selectedTasksData.value = [...selectedTasksData.value];
    return;
  }

  // 后端搜索选中的账户先并入 task.accounts（与批量设置 applyBatchAccountToTask 同款）
  const searched = (advertiser.accountSearchOptions || []).find(
    (acc: any) => acc.ad_account_id === accountId,
  );
  if (searched) {
    if (!Array.isArray(taskData.accounts)) taskData.accounts = [];
    if (
      !taskData.accounts.some((acc: any) => acc.ad_account_id === accountId)
    ) {
      taskData.accounts = [searched, ...taskData.accounts];
    }
  }

  // 从已选任务数据中查找对应的账户
  const selectedAccount = taskData.accounts?.find(
    (acc: any) => acc.ad_account_id === accountId,
  );

  if (!selectedAccount) return;
  advertiser.accountSearchOptions = undefined;

  // 处理新API结构
  const accountAndPage = selectedAccount.person_and_page || {};

  // 提取个号选项
  const personAccountOptions = Object.keys(accountAndPage).map((personName) => {
    const pages = accountAndPage[personName];
    const personId = pages[0]?.person_id || '';
    return { name: personName, person_id: personId };
  });

  // 展开所有主页
  const allPublicPageOptions: any[] = [];
  Object.entries(accountAndPage).forEach(
    ([personName, pages]: [string, any]) => {
      pages.forEach((page: any) => {
        allPublicPageOptions.push({
          id: page.id,
          name: page.name,
          label: `${page.name} ID: ${page.id}`,
          value: page.id,
          personName,
          personId: page.person_id,
        });
      });
    },
  );

  // 处理像素选项
  const pixelOptions = (selectedAccount.pixels || []).map((item: any) => ({
    id: item.id,
    name: item.name,
    label: `${item.name} ID: ${item.id}`,
    value: item.id,
  }));

  // 更新广告主数据
  advertiser.accountId = selectedAccount.ad_account_id;
  advertiser.accountName = selectedAccount.ad_account_name;
  advertiser.account = selectedAccount.ad_account_id;
  advertiser.name = selectedAccount.ad_account_name;
  advertiser.bmName = selectedAccount.bm_name || '-';
  advertiser.status = selectedAccount.status || '活跃';
  advertiser.spendCap = selectedAccount.spend_cap || 0;
  advertiser.balance = selectedAccount.balance || 0;
  advertiser.assigned_page_id = selectedAccount.assigned_page_id;

  advertiser.personAccountOptions = personAccountOptions;

  // 个号是主轴:换账户不动个号/主页,新账户没有当前个号才清空
  const keptPerson = personAccountOptions.find(
    (p) => p.name === advertiser.personAccountName,
  );
  if (keptPerson) {
    advertiser.selectedPersonAccount = keptPerson.name;
    advertiser.selectedPersonId = keptPerson.person_id;
    advertiser.personId = keptPerson.person_id;
    advertiser.publicPageOptions = allPublicPageOptions;
    const pageStillValid = allPublicPageOptions.some(
      (page: any) =>
        page.id === advertiser.selectedPublicPage &&
        page.personName === keptPerson.name,
    );
    if (!pageStillValid) {
      advertiser.selectedPublicPage = undefined;
      advertiser.publicPage = undefined;
    }
  } else if (advertiser.personAccountName) {
    advertiser.selectedPersonAccount = undefined;
    advertiser.selectedPersonId = undefined;
    advertiser.personAccountName = undefined;
    advertiser.personId = undefined;
    advertiser.publicPageOptions = allPublicPageOptions;
    advertiser.selectedPublicPage = undefined;
    advertiser.publicPage = undefined;
  } else {
    // 行里还没选过个号:默认个号跟代理线主页(assigned_page_id)的归属个号走
    const assignedPage = allPublicPageOptions.find(
      (page: any) => page.id === selectedAccount.assigned_page_id,
    );
    const defaultPersonName =
      assignedPage?.personName ?? personAccountOptions[0]?.name;
    const defaultPerson = personAccountOptions.find(
      (p) => p.name === defaultPersonName,
    );
    advertiser.selectedPersonAccount = defaultPersonName;
    advertiser.selectedPersonId = defaultPerson?.person_id;
    advertiser.personAccountName = defaultPersonName;
    advertiser.personId = defaultPerson?.person_id;
    advertiser.publicPageOptions = allPublicPageOptions;
    advertiser.selectedPublicPage = assignedPage?.id;
    advertiser.publicPage = assignedPage?.name;
  }

  // 像素跟着户走:只认代理线配置的像素,没有则为空
  advertiser.pixelOptions = pixelOptions;
  const linePixel = taskData.pixel_name
    ? pixelOptions.find((opt: any) => opt.name === taskData.pixel_name)
    : undefined;
  advertiser.selectedPixel = linePixel?.id;
  advertiser.pixel = linePixel?.name;

  // 记住该个号下选的账户,换个号时回填
  if (advertiser.personAccountName) {
    (advertiser._accountByPerson ??= {})[advertiser.personAccountName] =
      advertiser.account;
  }

  selectedTasksData.value = [...selectedTasksData.value];
}

function handlePublicPageChange(
  taskIndex: number,
  advIndex: number,
  value: string | undefined,
) {
  const taskData = selectedTasksData.value[taskIndex];
  if (!taskData || !taskData.advertisers) return;

  const advertiser = taskData.advertisers[advIndex];
  if (!advertiser) return;

  advertiser.selectedPublicPage = value;

  if (value && advertiser.publicPageOptions) {
    const selectedOption = advertiser.publicPageOptions.find(
      (opt) => opt.id === value,
    );
    advertiser.publicPage = selectedOption ? selectedOption.name : undefined;
  } else {
    advertiser.publicPage = undefined;
  }

  selectedTasksData.value = [...selectedTasksData.value];
}

function handlePixelChange(
  taskIndex: number,
  advIndex: number,
  value: string | undefined,
) {
  const taskData = selectedTasksData.value[taskIndex];
  if (!taskData || !taskData.advertisers) return;

  const advertiser = taskData.advertisers[advIndex];
  if (!advertiser) return;

  advertiser.selectedPixel = value;

  if (value && advertiser.pixelOptions) {
    const selectedOption = advertiser.pixelOptions.find(
      (opt) => opt.id === value,
    );
    advertiser.pixel = selectedOption ? selectedOption.name : undefined;
  } else {
    advertiser.pixel = undefined;
  }

  selectedTasksData.value = [...selectedTasksData.value];
}

// 批量设置已选任务线中的账户/个号/主页（仅对勾选的账户行生效）
const batchEditOpen = ref(false);
const batchEditAccountId = ref('');
const batchEditPersonName = ref<string | undefined>(undefined);
const batchEditPageId = ref<string | undefined>(undefined);
const batchEditLoading = ref(false);

// 勾选状态：key = taskCode::advId（同一任务线内 advId 唯一）
const batchSelectedKeys = ref<Set<string>>(new Set());

function advSelectKey(task: any, adv: any) {
  return `${task.taskCode}::${adv.id}`;
}

function isAdvSelected(task: any, adv: any) {
  return batchSelectedKeys.value.has(advSelectKey(task, adv));
}

const allAdvSelectKeys = computed(() => {
  const keys: string[] = [];
  selectedTasksData.value.forEach((task: any) =>
    (task.advertisers || []).forEach((adv: any) =>
      keys.push(advSelectKey(task, adv)),
    ),
  );
  return keys;
});

// 已勾选且仍存在的账户行数（行被删除后残留的 key 不算）
const batchSelectedCount = computed(
  () =>
    allAdvSelectKeys.value.filter((k) => batchSelectedKeys.value.has(k)).length,
);

const isAllBatchSelected = computed(
  () =>
    allAdvSelectKeys.value.length > 0 &&
    batchSelectedCount.value === allAdvSelectKeys.value.length,
);

function toggleBatchSelect(task: any, adv: any, checked: boolean) {
  const next = new Set(batchSelectedKeys.value);
  const key = advSelectKey(task, adv);
  if (checked) {
    next.add(key);
  } else {
    next.delete(key);
  }
  batchSelectedKeys.value = next;
}

function toggleBatchSelectAll(e: any) {
  batchSelectedKeys.value = e.target.checked
    ? new Set(allAdvSelectKeys.value)
    : new Set();
}

const batchEditPersonOptions = computed(() => {
  const set = new Set<string>();
  selectedTasksData.value.forEach((task: any) =>
    ((task.advertisers || []) as any[]).forEach((adv) => {
      if (!isAdvSelected(task, adv)) return;
      (adv.personAccountOptions || []).forEach((p: any) => {
        if (p.name) set.add(p.name);
      });
    }),
  );
  return [...set];
});

const batchEditPageOptions = computed(() => {
  const map = new Map<string, any>();
  selectedTasksData.value.forEach((task: any) =>
    ((task.advertisers || []) as any[]).forEach((adv) => {
      if (!isAdvSelected(task, adv)) return;
      (adv.publicPageOptions || []).forEach((page: any) => {
        if (
          batchEditPersonName.value &&
          page.personName &&
          page.personName !== batchEditPersonName.value
        ) {
          return;
        }
        if (page.id && !map.has(page.id)) map.set(page.id, page);
      });
    }),
  );
  return [...map.values()];
});

function openBatchEdit() {
  if (batchSelectedCount.value === 0) {
    message.warning('请先勾选要设置的账户行');
    return;
  }
  batchEditAccountId.value = '';
  batchEditPersonName.value = undefined;
  batchEditPageId.value = undefined;
  batchEditOpen.value = true;
}

// 包含勾选账户行的任务线下标
function batchSelectedTaskIndexes(): number[] {
  return selectedTasksData.value
    .map((task: any, i) =>
      (task.advertisers || []).some((adv: any) => isAdvSelected(task, adv))
        ? i
        : -1,
    )
    .filter((i) => i >= 0);
}

// 按任务线校验账户是否存在（走任务线账户查询接口，account_id 过滤 + 精确匹配），返回 taskIndex -> 账户 payload
async function validateBatchAccount(
  accountId: string,
  taskIndexes: number[],
): Promise<Map<number, any>> {
  const queries = taskIndexes.map((i) => ({
    task_name: selectedTasksData.value[i]?.projectName || '',
    subtask_name: selectedTasksData.value[i]?.taskName || '',
  }));
  const resp = await batchQueryMissionLineInfo(queries, 1, 15, {
    account_id: [accountId],
  });
  const items: any[] = Array.isArray(resp?.data) ? resp.data : [];
  const found = new Map<number, any>();
  for (const i of taskIndexes) {
    const task = selectedTasksData.value[i];
    const item = items.find(
      (it) =>
        it.subtask_name === task?.taskName &&
        it.task_name === task?.projectName,
    );
    const account = (item?.accounts || []).find(
      (acc: any) => acc.ad_account_id === accountId,
    );
    if (account) found.set(i, account);
  }
  return found;
}

function applyBatchAccountToTask(taskIndex: number, account: any) {
  const task = selectedTasksData.value[taskIndex] as any;
  if (!Array.isArray(task.accounts)) task.accounts = [];
  if (
    !task.accounts.some(
      (acc: any) => acc.ad_account_id === account.ad_account_id,
    )
  ) {
    task.accounts = [account, ...task.accounts];
  }
  (task.advertisers || []).forEach((adv: any, advIndex: number) => {
    if (!isAdvSelected(task, adv)) return;
    handleAccountChange(taskIndex, advIndex, account.ad_account_id);
  });
}

async function handleBatchEditConfirm() {
  const accountId = batchEditAccountId.value.trim();
  if (!accountId && !batchEditPersonName.value && !batchEditPageId.value) {
    message.warning('请至少填写一项修改内容');
    return;
  }

  batchEditLoading.value = true;
  try {
    if (accountId) {
      const taskIndexes = batchSelectedTaskIndexes();
      const foundByTask = await validateBatchAccount(accountId, taskIndexes);
      if (foundByTask.size === 0) {
        message.error(`账户「${accountId}」不存在或无权限使用`);
        return;
      }
      const missingTasks: string[] = [];
      taskIndexes.forEach((i) => {
        if (foundByTask.has(i)) {
          applyBatchAccountToTask(i, foundByTask.get(i));
        } else {
          missingTasks.push((selectedTasksData.value[i] as any).taskName || '');
        }
      });
      if (missingTasks.length > 0) {
        message.warning(
          `任务线 ${missingTasks.join('、')} 下未找到账户 ${accountId}，已跳过`,
        );
      }
    }

    let personSkipped = 0;
    let pageSkipped = 0;
    for (const [taskIndex, task] of selectedTasksData.value.entries()) {
      const advs = ((task as any).advertisers || []) as any[];
      for (const [advIndex, adv] of advs.entries()) {
        if (!isAdvSelected(task, adv)) continue;
        if (batchEditPersonName.value) {
          const matched = adv.personAccountOptions?.find(
            (p: any) => p.name === batchEditPersonName.value,
          );
          if (matched) {
            // 等个号的主页池就位,再应用批量主页,避免异步回填覆盖
            await handlePersonAccountChange(
              taskIndex,
              advIndex,
              matched.name,
              true,
            );
          } else {
            personSkipped++;
          }
        }
        if (batchEditPageId.value) {
          const page = adv.publicPageOptions?.find(
            (opt: any) =>
              opt.id === batchEditPageId.value &&
              opt.personName === adv.personAccountName,
          );
          if (page) {
            handlePublicPageChange(taskIndex, advIndex, page.id);
          } else {
            pageSkipped++;
          }
        }
      }
    }
    if (personSkipped > 0) {
      message.warning(`${personSkipped} 个账户行无该个号，已跳过`);
    }
    if (pageSkipped > 0) {
      message.warning(`${pageSkipped} 个账户行无该主页，已跳过`);
    }

    message.success('批量设置完成');
    batchEditOpen.value = false;
  } finally {
    batchEditLoading.value = false;
  }
}

// 批量新增：向选中任务线各加一行该账户，像素自动用对应线的像素（后端已将其排在 pixels 最前）
const batchAddOpen = ref(false);
const batchAddTaskCodes = ref<string[]>([]);
const batchAddAccountId = ref('');
const batchAddPersonName = ref<string | undefined>(undefined);
const batchAddPageId = ref<string | undefined>(undefined);
const batchAddValidating = ref(false);
const batchAddLoading = ref(false);
const batchAddFound = ref<Map<number, any>>(new Map());

// 已选任务线表格左侧勾选列（row-selection）驱动
function handleTaskSelectionChange(keys: any) {
  batchAddTaskCodes.value = keys as string[];
}

// 账户或任务线变化后，旧校验结果作废
watch([batchAddAccountId, batchAddTaskCodes], () => {
  batchAddFound.value = new Map();
  batchAddPersonName.value = undefined;
  batchAddPageId.value = undefined;
});

const batchAddPersonOptions = computed(() => {
  const set = new Set<string>();
  batchAddFound.value.forEach((account: any) => {
    Object.keys(account.person_and_page || {}).forEach((name) => set.add(name));
  });
  return [...set];
});

const batchAddPageOptions = computed(() => {
  const map = new Map<string, any>();
  batchAddFound.value.forEach((account: any) => {
    Object.entries(account.person_and_page || {}).forEach(
      ([personName, pages]: [string, any]) => {
        if (
          batchAddPersonName.value &&
          personName !== batchAddPersonName.value
        ) {
          return;
        }
        (pages || []).forEach((page: any) => {
          if (page.id && !map.has(page.id)) map.set(page.id, page);
        });
      },
    );
  });
  return [...map.values()];
});

function openBatchAdd() {
  if (batchAddSelectedCount.value === 0) {
    message.warning('请先在已选任务线表格左侧勾选任务线');
    return;
  }
  batchAddAccountId.value = '';
  batchAddOpen.value = true;
}

function batchAddTaskIndexes(): number[] {
  const codes = new Set(batchAddTaskCodes.value);
  return selectedTasksData.value
    .map((task: any, i) => (codes.has(task.taskCode) ? i : -1))
    .filter((i) => i >= 0);
}

// 勾选且仍存在的任务线数（删除任务线后残留的 key 不算）
const batchAddSelectedCount = computed(() => batchAddTaskIndexes().length);

async function handleBatchAddValidate(): Promise<boolean> {
  const accountId = batchAddAccountId.value.trim();
  if (!accountId) {
    message.warning('请输入广告账户ID');
    return false;
  }
  if (batchAddTaskCodes.value.length === 0) {
    message.warning('请选择任务线');
    return false;
  }
  batchAddValidating.value = true;
  try {
    const taskIndexes = batchAddTaskIndexes();
    const found = await validateBatchAccount(accountId, taskIndexes);
    batchAddFound.value = found;
    if (found.size === 0) {
      message.error(`账户「${accountId}」不存在或无权限使用`);
      return false;
    }
    const missing = taskIndexes
      .filter((i) => !found.has(i))
      .map((i) => (selectedTasksData.value[i] as any).taskName || '');
    if (missing.length > 0) {
      message.warning(
        `任务线 ${missing.join('、')} 下未找到账户 ${accountId}，将跳过`,
      );
    } else {
      message.success('账户校验通过');
    }
    return true;
  } finally {
    batchAddValidating.value = false;
  }
}

async function handleBatchAddConfirm() {
  if (batchAddFound.value.size === 0) {
    const ok = await handleBatchAddValidate();
    if (!ok) return;
  }
  batchAddLoading.value = true;
  try {
    let added = 0;
    let dup = 0;
    for (const [taskIndex, account] of batchAddFound.value) {
      const task = selectedTasksData.value[taskIndex] as any;
      if (!task) continue;
      const exists = (task.advertisers || []).some(
        (adv: any) =>
          adv.id === account.ad_account_id ||
          adv.account === account.ad_account_id,
      );
      if (exists) {
        dup++;
        continue;
      }
      if (!Array.isArray(task.accounts)) task.accounts = [];
      if (
        !task.accounts.some(
          (acc: any) => acc.ad_account_id === account.ad_account_id,
        )
      ) {
        task.accounts = [account, ...task.accounts];
      }
      if (!Array.isArray(task.advertisers)) task.advertisers = [];
      task.advertisers.push({ id: account.ad_account_id });
      const advIndex = task.advertisers.length - 1;
      handleAccountChange(taskIndex, advIndex, account.ad_account_id);
      const adv = task.advertisers[advIndex];
      if (batchAddPersonName.value) {
        const matched = adv.personAccountOptions?.find(
          (p: any) => p.name === batchAddPersonName.value,
        );
        if (matched) {
          // 等个号的主页池就位,再应用批量主页,避免异步回填覆盖
          await handlePersonAccountChange(
            taskIndex,
            advIndex,
            matched.name,
            true,
          );
        }
      }
      if (batchAddPageId.value) {
        const page = adv.publicPageOptions?.find(
          (opt: any) =>
            opt.id === batchAddPageId.value &&
            opt.personName === adv.personAccountName,
        );
        if (page) {
          handlePublicPageChange(taskIndex, advIndex, page.id);
        }
      }
      added++;
    }
    selectedTasksData.value = [...selectedTasksData.value];
    message.success(
      `已新增 ${added} 个账户行${
        dup > 0 ? `，${dup} 条任务线已存在该账户，跳过` : ''
      }`,
    );
    batchAddOpen.value = false;
  } finally {
    batchAddLoading.value = false;
  }
}

// Template Modal
const showTemplateModal = ref(false);
const appliedTemplateName = ref<string>('');
const appliedTemplateDescription = ref<string>('');
const templateLoadTabRef = ref<any>(null);

// 素材模板相关
const showMaterialTemplateModal = ref(false);
const appliedMaterialTemplateId = ref<null | string>(null);
const appliedMaterialTemplateName = ref<string>('');

// 素材组管理相关
const showMaterialGroupSaveModal = ref(false);
const showMaterialGroupHistoryModal = ref(false);
const materialGroupLoadTabRef = ref<any>(null);
const materialGroupHistoryModalRef = ref<any>(null);
// 当前应用的素材组信息（用于更新功能）
const currentMaterialGroupId = ref<null | string>(null);
const currentMaterialGroupName = ref<string>('');

// 创意历史相关
const showCreativeHistoryModal = ref(false);
const creativeHistoryModalRef = ref<any>(null);
const currentMaterialGroupDescription = ref<string>('');
const appliedMaterialTemplateDescription = ref<string>('');
const materialTemplateLoadTabRef = ref<any>(null);

const operatorOptions = ref<Array<{ label: string; value: string }>>([]);

let operatorOptionsLoaded = false;
async function loadOperatorOptions() {
  if (operatorOptionsLoaded) return;
  try {
    const names = await getUserOptions(['operator', 'operator_leader']);
    const options = (names || []).map((name: string) => ({
      label: name,
      value: name,
    }));
    operatorOptions.value = options;
    operatorOptionsLoaded = true;
  } catch {}
}

// 同步全局设置并构建表单数据（用于创建广告）
function prepareAdvertisementData() {
  seriesList.value.forEach((series) => {
    series.regionGroups.forEach((group) => {
      group.optimizationTarget = performanceGoal.value;
      group.conversionLocation = conversionLocation.value;
      group.conversionGoal = conversionEvent.value;
      if (conversionLocation.value === 'APP') {
        group.applicationId = applicationId.value;
      }
    });
  });

  return {
    selectedTasksData: selectedTasksData.value,
    seriesList: seriesList.value,
    uploadedMaterials: materialGroups.value.flatMap((g) => {
      let _targetAccountName: string | undefined;
      let _targetAdsetNames: string | undefined;

      if (g.binding.type === 'account' && g.binding.accountId) {
        _targetAccountName = advertiserOptions.value.find(
          (o) => o.value === g.binding.accountId,
        )?.label;
      } else if (
        g.binding.type === 'regionGroup' &&
        g.binding.regionGroupPath?.length === 2
      ) {
        const [seriesId, rgId] = g.binding.regionGroupPath;
        const series = seriesList.value.find((s) => s.id === seriesId);
        const rg = series?.regionGroups.find((r) => r.id === rgId);
        if (series && rg) _targetAdsetNames = `${series.name}/${rg.name}`;
      }

      return g.materials.map((m) => ({
        ...m,
        ...(_targetAccountName && { _targetAccountName }),
        ...(_targetAdsetNames && { _targetAdsetNames }),
        ...(g.binding.type === 'tag' && { _allocByTag: true }),
      }));
    }),
    adsPerGroup: adsPerGroup.value,
    conversionEvent: conversionEvent.value,
    conversionLocation: conversionLocation.value,
    applicationId: applicationId.value,
    appStoreUrl:
      selectedApplication.value?.store_url ||
      resolveAppStoreUrl(applicationId.value),
    schedule_start_time: scheduleStartTime.value?.toISOString(),
    schedule_end_time: scheduleEndTime.value?.toISOString(),
    step1Data,
    chatToolData: chatToolData.value ?? undefined,
    isEngagement: isEngagementSeries.value,
  };
}

function prepareTemplateSettings() {
  if (seriesList.value.length === 0) return null;
  const settingsV2 = {
    version: 2,
    globals: {
      conversionLocation: conversionLocation.value || '',
      performanceGoal: performanceGoal.value || '',
      conversionEvent: conversionEvent.value || '',
      applicationId: applicationId.value || '',
      schedule_start_time: scheduleStartTime.value
        ? scheduleStartTime.value.toISOString()
        : '',
      schedule_end_time: scheduleEndTime.value
        ? scheduleEndTime.value.toISOString()
        : '',
    },
    seriesList: JSON.parse(JSON.stringify(seriesList.value)) as SeriesData[],
  };

  return settingsV2;
}

async function handleTemplateSave(templateName: string, description: string) {
  try {
    const currentUser = userStore.userInfo?.realName || '';
    if (!currentUser) {
      message.error('无法获取用户信息，请重新登录');
      return;
    }

    const settings = prepareTemplateSettings();
    if (!settings) {
      message.error('无法获取模板设置数据，请检查配置');
      return;
    }

    if (appliedTemplateId.value) {
      await updateTemplate(appliedTemplateId.value, {
        name: templateName,
        real_name: currentUser,
        description: description || undefined,
        settings,
      });
      appliedTemplateName.value = templateName;
      appliedTemplateDescription.value = description || '';
      message.success('模板更新成功');
    } else {
      const result: any = await createTemplate({
        name: templateName,
        real_name: currentUser,
        description: description || undefined,
        settings,
      });

      const newId = result?.id || result?.data?.id;
      if (newId) {
        appliedTemplateId.value = newId;
      }
      appliedTemplateName.value = templateName;
      appliedTemplateDescription.value = description || '';

      message.success('模板保存成功');
    }

    const templateTabRefs = templateLoadTabRef.value as any;
    let templateTabInstance = null;

    templateTabInstance = Array.isArray(templateTabRefs)
      ? templateTabRefs[currentSeriesIndex.value]
      : templateTabRefs;

    if (
      templateTabInstance &&
      typeof templateTabInstance.refresh === 'function'
    ) {
      await templateTabInstance.refresh();
    }

    showTemplateModal.value = false;
  } catch {}
}

const showChatToolModal = ref(false);
const chatToolData = ref<null | {
  greeting: string;
  greetingType: string;
  questions: { autoReply: string; question: string }[];
  reengagementEnabled: boolean;
  reengagementText: string;
}>(null);

function handleChatToolConfirm(data: any) {
  chatToolData.value = data;
}

interface ChatToolTemplate {
  data: {
    greeting: string;
    greetingType: string;
    questions: { autoReply: string; question: string }[];
    reengagementEnabled: boolean;
    reengagementText: string;
  };
  id: string;
  name: string;
}

const batchChatToolTemplate = ref<ChatToolTemplate | null>(null);
const batchChatToolTemplateName = ref('');

function selectBatchChatToolTemplate(tpl: ChatToolTemplate) {
  batchChatToolTemplate.value = tpl;
  batchChatToolTemplateName.value = tpl.name;
}

// Material Selection Modal
const showMaterialModal = ref(false);

function handleMaterialConfirm(materials: MaterialItem[]) {
  const existingIds = new Set(uploadedMaterials.value.map((m) => m.id));
  const newMaterials = materials.filter((m) => !existingIds.has(m.id));
  uploadedMaterials.value = [...uploadedMaterials.value, ...newMaterials];
  showMaterialModal.value = false;
}

// 原帖 Modal
const showOriginalPostModal = ref(false);

const selectedOriginalPostIds = computed<string[]>(() => {
  return uploadedMaterials.value
    .filter((m) => m.isOriginalPost)
    .map((m) => m.id);
});

const selectedPageIds = computed<string[]>(() => {
  const ids = new Set<string>();
  selectedTasksData.value.forEach((task) => {
    (task.advertisers || []).forEach((adv: any) => {
      const pageId = adv.selectedPublicPage || adv.公共主页ID;
      if (pageId) ids.add(String(pageId));
    });
  });
  return [...ids];
});

// 广告账户选项（来自步骤一 selectedTasksData，去重）
const advertiserOptions = computed(() => {
  const seen = new Set<string>();
  const opts: { label: string; value: string }[] = [];
  for (const task of selectedTasksData.value) {
    for (const adv of task.advertisers ?? []) {
      if (!seen.has(adv.id)) {
        seen.add(adv.id);
        opts.push({ label: adv.name || adv.account || adv.id, value: adv.id });
      }
    }
  }
  return opts;
});

// 地区组级联选择器选项（一级系列，二级地区组）
const regionGroupCascaderOptions = computed(() =>
  seriesList.value.map((series) => ({
    label: series.name,
    value: series.id,
    children: series.regionGroups.map((group) => ({
      label: group.name,
      value: group.id,
    })),
  })),
);

function openOriginalPostModal() {
  if (selectedPageIds.value.length === 0) {
    message.warning('请先在第一步为广告账户配置公共主页');
    return;
  }
  showOriginalPostModal.value = true;
}

// ==================== 素材组 Tab 管理函数 ====================

function addMaterialGroup() {
  const newId = generateNextId(materialGroups.value);
  materialGroups.value.push({
    id: newId,
    name: `素材组${newId}`,
    materials: [],
    selectedIds: [],
    binding: { type: 'random' },
  });
  activeMaterialGroupKey.value = newId;
}

function cloneMaterialGroup(groupId: string, count: number) {
  const original = materialGroups.value.find((g) => g.id === groupId);
  if (!original) return;
  const safeCount = validateCloneCount(count);
  if (safeCount === null) return;

  for (let i = 0; i < safeCount; i++) {
    const newId = generateNextId(materialGroups.value);
    const cloned: MaterialGroup = deepRawClone(original);
    cloned.id = newId;
    cloned.name = `素材组${newId}`;
    cloned.materials = [];
    cloned.selectedIds = [];
    materialGroups.value.push(cloned);
  }
  activeMaterialGroupKey.value = materialGroups.value.at(-1)!.id;
}

function deleteMaterialGroup(groupId: string) {
  if (materialGroups.value.length <= 1) {
    message.warning('至少保留一个素材组');
    return;
  }
  materialGroups.value = materialGroups.value.filter((g) => g.id !== groupId);
  if (activeMaterialGroupKey.value === groupId) {
    activeMaterialGroupKey.value = materialGroups.value[0]!.id;
  }

  message.success('删除成功');
}

function confirmCloneMaterialGroup(groupId: string) {
  cloneMaterialGroup(groupId, materialGroupClone.getCount(groupId));
  materialGroupClone.setOpen(groupId, false);
}

function handleOriginalPostConfirm(posts: MaterialItem[]) {
  const existingIds = new Set(uploadedMaterials.value.map((m) => m.id));
  const newPosts = posts.filter((p) => !existingIds.has(p.id));
  uploadedMaterials.value = [...uploadedMaterials.value, ...newPosts];
  showOriginalPostModal.value = false;
}

// 临时广告 Modal — 素材合并进当前激活素材组
const showAdCreativeModal = ref(false);

function handleAdCreativeConfirm(materials: any[]) {
  const group = currentMaterialGroup.value;
  if (!group) return;
  const existingIds = new Set(group.materials.map((m) => m.id));
  const newMaterials = materials
    .filter((m) => !existingIds.has(m.id))
    .map((m) => ({ ...m, name: m.name || m.basename || m.filename || m.id }));
  group.materials.push(...newMaterials);
  showAdCreativeModal.value = false;
}

// 切换广告选择状态
function toggleMaterialSelection(materialId: string, checked: boolean) {
  if (checked) {
    // 添加到选中列表
    if (!selectedMaterials.value.includes(materialId)) {
      selectedMaterials.value.push(materialId);
    }
  } else {
    // 从选中列表移除
    selectedMaterials.value = selectedMaterials.value.filter(
      (id) => id !== materialId,
    );
  }
}

// 删除选中的广告
function deleteSelectedMaterials() {
  if (selectedMaterials.value.length === 0) {
    message.warning('请先选择要删除的广告');
    return;
  }

  // 从已上传广告列表中移除选中的广告
  const selectedSet = new Set(selectedMaterials.value);
  uploadedMaterials.value = uploadedMaterials.value.filter(
    (material) => !selectedSet.has(material.id),
  );

  message.success(`成功删除 ${selectedMaterials.value.length} 个广告`);

  // 清空选中列表
  selectedMaterials.value = [];
}

// 批量应用相关状态
const showBatchApplyCheckboxes = ref(false);
const batchApplySelectedMaterials = ref<string[]>([]);
const batchTitle = ref(''); // 批量应用的标题
const batchDescription = ref(''); // 批量应用的正文
const batchCallToAction = ref<string | undefined>(undefined); // 批量应用的行动号召

// 切换批量应用广告选择状态
function toggleBatchApplySelection(materialId: string, checked: boolean) {
  toggleMaterialSelection(materialId, checked);
}

// 框选功能
const startSelection = (event: MouseEvent) => {
  if (isPreviewMode.value) return;

  // 扩大可框选区域：允许在卡片上也开始框选，但排除交互元素
  const target = event.target as HTMLElement;
  const isInteractiveElement =
    target.tagName === 'INPUT' ||
    target.tagName === 'BUTTON' ||
    target.tagName === 'TEXTAREA' ||
    target.closest('input') ||
    target.closest('button') ||
    target.closest('textarea') ||
    target.closest('.ant-checkbox');

  if (isInteractiveElement) return; // 排除交互元素

  isSelecting.value = true;
  activeContainer.value = event.currentTarget as HTMLElement;
  // 记录框选开始时的选中状态
  selectionStartSelected.value = new Set<string>(selectedMaterials.value);

  const rect = activeContainer.value.getBoundingClientRect();
  selectionBox.value.startX =
    event.clientX - rect.left + activeContainer.value.scrollLeft;
  selectionBox.value.startY =
    event.clientY - rect.top + activeContainer.value.scrollTop;
  selectionBox.value.endX = selectionBox.value.startX;
  selectionBox.value.endY = selectionBox.value.startY;

  document.addEventListener('mousemove', updateSelection);
  document.addEventListener('mouseup', endSelection);
  event.preventDefault();
};

const updateSelection = (event: MouseEvent) => {
  if (!isSelecting.value || !activeContainer.value) return;

  const rect = activeContainer.value.getBoundingClientRect();
  selectionBox.value.endX =
    event.clientX - rect.left + activeContainer.value.scrollLeft;
  selectionBox.value.endY =
    event.clientY - rect.top + activeContainer.value.scrollTop;

  // 实时更新选中的卡片
  updateSelectedCards();
};

const endSelection = () => {
  isSelecting.value = false;
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
};

const updateSelectedCards = () => {
  if (!activeContainer.value) return;

  const cards = activeContainer.value.querySelectorAll('[data-card-id]');
  const newSelected = new Set<string>(selectionStartSelected.value); // 从初始状态开始

  const selectionRect = {
    left: Math.min(selectionBox.value.startX, selectionBox.value.endX),
    top: Math.min(selectionBox.value.startY, selectionBox.value.endY),
    right: Math.max(selectionBox.value.startX, selectionBox.value.endX),
    bottom: Math.max(selectionBox.value.startY, selectionBox.value.endY),
  };

  // 只有当选择框有一定大小时才进行选择操作
  const minSelectionSize = 5;
  if (
    Math.abs(selectionBox.value.endX - selectionBox.value.startX) <
      minSelectionSize ||
    Math.abs(selectionBox.value.endY - selectionBox.value.startY) <
      minSelectionSize
  ) {
    return;
  }

  cards.forEach((card) => {
    const cardRect = (card as HTMLElement).getBoundingClientRect();
    const containerRect = activeContainer.value!.getBoundingClientRect();

    const cardRelativeRect = {
      left:
        cardRect.left - containerRect.left + activeContainer.value!.scrollLeft,
      top: cardRect.top - containerRect.top + activeContainer.value!.scrollTop,
      right:
        cardRect.right - containerRect.left + activeContainer.value!.scrollLeft,
      bottom:
        cardRect.bottom - containerRect.top + activeContainer.value!.scrollTop,
    };

    // 检查卡片是否与选择框相交
    const isIntersecting = !(
      cardRelativeRect.right < selectionRect.left ||
      cardRelativeRect.left > selectionRect.right ||
      cardRelativeRect.bottom < selectionRect.top ||
      cardRelativeRect.top > selectionRect.bottom
    );

    const cardId = (card as HTMLElement).dataset.cardId!;
    if (isIntersecting) {
      // 如果卡片在框选区域内
      if (selectionStartSelected.value.has(cardId)) {
        // 如果原本已选中，则取消选择
        newSelected.delete(cardId);
      } else {
        // 如果原本未选中，则添加选择
        newSelected.add(cardId);
      }
    }
  });

  selectedMaterials.value = [...newSelected];
};

// 全选广告
function selectAllMaterials() {
  selectedMaterials.value = uploadedMaterials.value.map((m) => m.id);
  showMaterialCheckboxes.value = true;
}

// 反选广告
function invertMaterialSelection() {
  const currentSelected = new Set(selectedMaterials.value);
  selectedMaterials.value = uploadedMaterials.value
    .filter((m) => !currentSelected.has(m.id))
    .map((m) => m.id);
}

// 清空选择
function clearMaterialSelection() {
  selectedMaterials.value = [];
}

// 键盘快捷键支持
const handleKeyDown = (event: KeyboardEvent) => {
  if (currentStep.value !== 2 || isPreviewMode.value) return;

  if (event.key === 'Escape') {
    clearMaterialSelection();
  }
};

// 应用批量标题、正文和行动号召
function applyBatchTitleAndDescription() {
  if (selectedMaterials.value.length === 0) {
    message.warning('请先选择要应用的广告');
    return;
  }

  const batchChatData = batchChatToolTemplate.value
    ? {
        chatToolData: {
          ...batchChatToolTemplate.value.data,
          questions: JSON.parse(
            JSON.stringify(batchChatToolTemplate.value.data.questions),
          ),
        },
        chatToolTemplateName: batchChatToolTemplate.value.name,
      }
    : {};

  const selectedSet = new Set(selectedMaterials.value);
  let appliedCount = 0;
  let skippedCTACount = 0;

  uploadedMaterials.value = uploadedMaterials.value.map((material) => {
    if (selectedSet.has(material.id)) {
      appliedCount++;

      let finalCTA = batchCallToAction.value;
      if (finalCTA && material.filetype) {
        const isValid = validateCTAForMaterial(finalCTA, material.filetype);
        if (!isValid) {
          finalCTA = material.callToAction;
          skippedCTACount++;
        }
      }

      return {
        ...material,
        ...batchChatData,
        title: batchTitle.value,
        description: batchDescription.value,
        callToAction: finalCTA,
      };
    }
    return material;
  });

  if (skippedCTACount > 0) {
    message.warning(
      `已应用到 ${appliedCount} 个广告，其中 ${skippedCTACount} 个广告的行动号召因类型不匹配被跳过`,
    );
  } else {
    message.success(`成功应用到 ${appliedCount} 个广告`);
  }

  selectedMaterials.value = [];
}

// Validation functions
function validateStep1(): boolean {
  // 检查是否选择了任务线
  if (selectedTasksData.value.length === 0) {
    message.warning('请至少选择一条任务线');
    return false;
  }

  // 检查每条任务线是否配置了广告账户
  for (let i = 0; i < selectedTasksData.value.length; i++) {
    const task = selectedTasksData.value[i];
    if (!task.advertisers || task.advertisers.length === 0) {
      message.warning(`任务线"${task.taskName}"未配置广告账户，请配置后再继续`);
      return false;
    }
  }

  return true;
}

// 旧模板存的是选项文案(如 '最高数量'),规整为 FB 枚举值
function normalizeBidStrategy(value: unknown): string {
  return [
    'COST_CAP',
    'LOWEST_COST_WITH_BID_CAP',
    'LOWEST_COST_WITHOUT_CAP',
  ].includes(value as string)
    ? (value as string)
    : 'LOWEST_COST_WITHOUT_CAP';
}

function validateStep2(): boolean {
  // 检查是否有广告系列
  if (seriesList.value.length === 0) {
    message.warning('请至少创建一个广告系列');
    return false;
  }

  // 检查转化事件是否已选择（仅在需要显示转化事件时校验）
  if (shouldShowConversionEvent.value && !conversionEvent.value) {
    message.warning('请选择转化事件');
    return false;
  }

  // 检查每个广告系列的必填项
  for (let i = 0; i < seriesList.value.length; i++) {
    const series = seriesList.value[i];

    // 检查预算
    if (!series.seriesSettings.budget || series.seriesSettings.budget <= 0) {
      message.warning(`${series.name}的预算必须大于0`);
      return false;
    }

    // 检查花费限额
    if (
      series.seriesSettings.flowOptimization === '自定义' &&
      (!series.seriesSettings.flowOptimizationAmount ||
        series.seriesSettings.flowOptimizationAmount <= 0)
    ) {
      message.warning(`${series.name}的花费限额必须大于0`);
      return false;
    }

    // 检查出价金额
    if (
      series.seriesSettings.targetPrice !== 'LOWEST_COST_WITHOUT_CAP' &&
      !(Number(series.seriesSettings.targetValue) > 0)
    ) {
      message.warning(`${series.name}的出价金额必须大于0`);
      return false;
    }

    // 检查特殊广告类别对应的国家
    if (
      series.seriesSettings.specialAdCategories?.length &&
      !series.seriesSettings.specialAdCountries?.length
    ) {
      message.warning(`${series.name}请选择对应的国家`);
      return false;
    }

    // 检查是否有地区组
    if (!series.regionGroups || series.regionGroups.length === 0) {
      message.warning(`${series.name}至少需要创建一个地区组`);
      return false;
    }

    // 检查每个地区组的必填项
    for (let j = 0; j < series.regionGroups.length; j++) {
      const group = series.regionGroups[j];

      // 检查地区
      if (!group.country) {
        message.warning(
          `${series.name}的${group.name}未选择地区，请选择后再继续`,
        );
        return false;
      }
    }
  }

  return true;
}

function validateStep3(): boolean {
  // 检查每个广告组的广告数量
  if (!adsPerGroup.value || adsPerGroup.value <= 0) {
    message.warning('每个广告组的广告数量必须大于0');
    return false;
  }

  // 检查是否上传了广告
  const allMaterials = materialGroups.value.flatMap((g) => g.materials);
  if (allMaterials.length === 0) {
    message.warning('请先上传广告');
    return false;
  }

  for (const material of allMaterials) {
    if (
      material.title &&
      new TextEncoder().encode(material.title).length > 255
    ) {
      message.warning(
        `广告"${material.name || material.materialId}"的标题超过255字节，请修改后再提交`,
      );
      return false;
    }

    const materialName = material.name || material.materialId || '';
    if (
      !material.callToAction &&
      !material.isOriginalPost &&
      material.filetype === 'video'
    ) {
      message.warning(`广告"${materialName}"未选择行动号召，请选择后再继续`);
      return false;
    }
    if (
      isEngagementSeries.value &&
      !material.chatToolData &&
      !material.isOriginalPost
    ) {
      message.warning(`广告"${materialName}"未选择聊天模板，请选择后再继续`);
      return false;
    }
  }

  // 动态素材广告组:FB 限制一个动态组只能 1 条广告、且只能一种格式,故图片/视频不能混选
  for (const series of seriesList.value) {
    for (const rg of series.regionGroups) {
      if (!rg.isDynamicCreative) continue;
      const reaching = materialGroups.value.filter((g) => {
        if (g.binding.type === 'regionGroup') {
          const path = g.binding.regionGroupPath;
          return !!path && path[0] === series.id && path[1] === rg.id;
        }
        return true; // random / tag / account 绑定都会进入该广告组
      });
      const types = new Set<string>();
      for (const g of reaching) {
        for (const m of g.materials) {
          if (m.filetype) types.add(m.filetype);
        }
      }
      if (types.size > 1) {
        message.warning(
          `广告组"${series.name}/${rg.name}"开启了动态素材,但同时包含图片和视频。FB 动态素材广告组只能有 1 条广告且只能一种格式,请把图片和视频分到不同广告组。`,
        );
        return false;
      }
    }
  }

  return true;
}

// 处理 Steps 点击切换
function handleStepChange(step: number) {
  if (step < currentStep.value) {
    currentStep.value = step;
    return;
  }

  // 向前切换时，依次校验之前的步骤
  for (let i = 0; i < step; i++) {
    if (i === 0 && !validateStep1()) {
      return;
    }
    if (i === 1 && !validateStep2()) {
      return;
    }
  }

  currentStep.value = step;
}

// Navigation
function nextStep() {
  // 步骤1校验
  if (currentStep.value === 0 && !validateStep1()) {
    return;
  }

  // 步骤2校验
  if (currentStep.value === 1 && !validateStep2()) {
    return;
  }

  if (currentStep.value < 2) {
    currentStep.value++;
  }
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--;
  }
}

function handleCreateAdvertisement() {
  if (!validateStep1()) {
    return;
  }
  if (!validateStep2()) {
    return;
  }
  if (!validateStep3()) {
    return;
  }

  showConfirmModal.value = true;
}

async function doCreateAdvertisement() {
  adCreatingCooldown.value = true;
  creatingAd.value = true;

  try {
    const formData = prepareAdvertisementData();
    const apiParams = transformToAdvertisementParams(formData);

    const newParams = Object.assign({}, apiParams, {
      campaign_num: Number(totalCreated.value),
      adset_num: Number(totalAdGroups.value),
      ad_num: Number(adsPerGroup.value),
    });

    // console.log('最终提交的广告参数', newParams);

    const newVar = await createAdvertisement(newParams);
    message.success(newVar);
    showConfirmModal.value = false;
  } finally {
    creatingAd.value = false;
    setTimeout(() => {
      adCreatingCooldown.value = false;
    }, 3000);
  }
}

async function handleProcessSelectedTasks() {
  // 检查是否有选中项
  if (!selectedProducts.value || selectedProducts.value.length === 0) {
    message.warning('请先选择任务线');
    return;
  }

  // 设置加载状态
  processingTasks.value = true;

  try {
    // 获取已存在的任务线代码集合，避免重复添加
    const existingTaskCodes = new Set(
      selectedTasksData.value.map((task) => task.taskCode),
    );
    // 额外：项目名称 + 任务线名称 组合的集合，用于过滤重复（性能 O(1)）
    const existingProjectTaskKeys = new Set(
      selectedTasksData.value.map(
        (task) => `${task.projectName || ''}||${task.taskName || ''}`,
      ),
    );

    // 构建批量查询参数
    const queries = selectedProducts.value.map((item) => {
      const platformValue = item[0] || '';
      const agentLine = item[1] || '';
      const platformMatch = platformValue.match(/platform_\d+_(.+)/);
      const platformName = platformMatch?.[1] ?? '';
      return {
        task_name: platformName,
        subtask_name: agentLine,
      };
    });

    // 批量查询任务线信息（meta_only: 只取线配置, 账户在弹窗打开时再查）
    const response = await batchQueryMissionLineInfo(
      queries,
      1,
      15,
      undefined,
      true,
    );
    const results = response?.data;
    const responseCode = response?.code;
    const responseMessage = response?.message;

    // 处理批量响应，先收集所有新数据再一次性更新
    const newTasks: SelectedProduct[] = [];
    const newProjectTaskKeys = new Set<string>(); // 避免本次批量内重复
    let duplicateCount = 0;

    if (results && Array.isArray(results)) {
      for (const [index, taskInfo] of results.entries()) {
        // 后端会跳过无配置的代理线, items 与 queries 不一定等长, 按 subtask_name 反查
        const query =
          queries.find((q) => q.subtask_name === taskInfo.subtask_name) ??
          queries[index]!;
        const taskCode =
          taskInfo.任务线编号 || `${query.subtask_name}_${Date.now()}_${index}`;

        const projectName = taskInfo.项目名称 || query.task_name;
        const taskName = taskInfo.任务线名称 || query.subtask_name;
        const projectTaskKey = `${projectName || ''}||${taskName || ''}`;

        // 检查是否已存在，避免重复添加
        if (
          !existingTaskCodes.has(taskCode) &&
          !existingProjectTaskKeys.has(projectTaskKey) &&
          !newProjectTaskKeys.has(projectTaskKey)
        ) {
          newTasks.push({
            projectName,
            regionName: Array.isArray(taskInfo.target_region)
              ? taskInfo.target_region
                  .map((code: string) => countryMap[code] ?? code)
                  .join('、')
              : '',
            taskName,
            taskCode,
            url: taskInfo.投放链接 || '',
            advertisers: [],
            ...taskInfo,
          });
          existingTaskCodes.add(taskCode);
          newProjectTaskKeys.add(projectTaskKey);
        } else {
          duplicateCount++;
        }
      }
    }

    // 一次性更新数组，避免多次触发响应式更新
    if (newTasks.length > 0) {
      selectedTasksData.value = [...selectedTasksData.value, ...newTasks];
    }

    // 显示结果消息
    if (newTasks.length > 0) {
      message.success(
        `成功添加 ${newTasks.length} 条任务线${
          duplicateCount > 0
            ? `，其中 ${duplicateCount} 条已存在未重复添加`
            : ''
        }`,
      );

      // 接口返回数据但有消息的情况
      if (
        responseCode === 0 &&
        responseMessage &&
        responseMessage !== 'Success'
      ) {
        message.warn(responseMessage);
      }
    } else if (responseCode === 400 && responseMessage) {
      message.error(responseMessage);
    } else {
      message.error('所选任务线未查询到或已存在，请检查选择或erp配置');
    }

    // 清空选择
    selectedProducts.value = [];
  } catch {
    // Ignore error
  } finally {
    processingTasks.value = false;
  }
}

// 批量添加：粘贴文本解析成多条代理线，反查所属平台后并入 selectedProducts，走同一条添加流程
const pasteAddOpen = ref(false);
const pasteAddText = ref('');
const pasteAddLoading = ref(false);

function openPasteAdd() {
  pasteAddText.value = '';
  pasteAddOpen.value = true;
}

async function handlePasteAddConfirm() {
  const names = [
    ...new Set(
      pasteAddText.value
        .split(/[\t\n\r,;、，；]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
  if (names.length === 0) {
    message.warning('请粘贴代理线名称');
    return;
  }
  pasteAddLoading.value = true;
  try {
    await loadAgentOptions();
    const lineToPlatform = new Map<string, string>();
    platformAgentData.value.forEach((item, platformIndex) => {
      item.agent_lines.forEach((line) => {
        if (!lineToPlatform.has(line)) {
          lineToPlatform.set(line, getPlatformOptionValue(item, platformIndex));
        }
      });
    });
    const missing = names.filter((name) => !lineToPlatform.has(name));
    if (missing.length > 0) {
      message.warning(`未找到代理线：${missing.join('、')}`);
    }
    const alreadySelected = new Set(
      selectedProducts.value.map((item) => item[1]),
    );
    const matched = names
      .filter((name) => lineToPlatform.has(name) && !alreadySelected.has(name))
      .map((name) => [lineToPlatform.get(name)!, name]);
    if (matched.length === 0) {
      if (missing.length === 0) {
        message.warning('代理线均已在选择框中');
      }
      return;
    }
    selectedProducts.value = [...selectedProducts.value, ...matched];
    pasteAddOpen.value = false;
    await handleProcessSelectedTasks();
  } finally {
    pasteAddLoading.value = false;
  }
}

function deleteTask(index: number) {
  selectedTasksData.value = selectedTasksData.value.filter(
    (_, i) => i !== index,
  );
}

// 已应用的模板 ID（用于区分创建/更新模板）
const appliedTemplateId = ref<null | string>(null);

// 素材模板保存处理
async function handleMaterialTemplateSave(
  templateName: string,
  description: string,
) {
  try {
    const currentUser = userStore.userInfo?.realName || '';
    if (!currentUser) {
      message.error('无法获取用户信息，请重新登录');
      return;
    }

    const templateData = {
      batchTitle: batchTitle.value,
      batchDescription: batchDescription.value,
    };

    if (appliedMaterialTemplateId.value) {
      await updateMaterialTemplate(appliedMaterialTemplateId.value, {
        name: templateName,
        real_name: currentUser,
        description: description || undefined,
        ...templateData,
      });
      appliedMaterialTemplateName.value = templateName;
      appliedMaterialTemplateDescription.value = description || '';
      message.success('模板更新成功');
    } else {
      const result: any = await createMaterialTemplate({
        name: templateName,
        real_name: currentUser,
        description: description || undefined,
        ...templateData,
      });

      const newId = result?.id || result?.data?.id;
      if (newId) {
        appliedMaterialTemplateId.value = newId;
      }
      appliedMaterialTemplateName.value = templateName;
      appliedMaterialTemplateDescription.value = description || '';

      message.success('模板保存成功');
    }

    await materialTemplateLoadTabRef.value?.refresh?.();
    showMaterialTemplateModal.value = false;
  } catch {}
}

// 素材模板应用处理
function handleMaterialTemplateApply(templateData: any) {
  appliedMaterialTemplateId.value = templateData.id || null;
  appliedMaterialTemplateName.value = templateData.name || '';
  appliedMaterialTemplateDescription.value = templateData.description || '';

  // 应用模板数据
  if (templateData.batchTitle !== undefined) {
    batchTitle.value = templateData.batchTitle;
  }
  if (templateData.batchDescription !== undefined) {
    batchDescription.value = templateData.batchDescription;
  }

  message.success('模板应用成功');
}

// ==================== 素材组管理相关函数 ====================

// 保存素材组
async function handleSaveMaterialGroup(
  data: {
    description: string;
    name: string;
    tags: string[];
  },
  action: 'create' | 'update',
) {
  try {
    // 收集当前所有素材及其配置
    const materials = uploadedMaterials.value.map((m) => ({
      material_id: m.materialId || m.id,
      title: m.title || '',
      body: m.description || '',
      call_to_action: m.callToAction,
    }));

    if (action === 'update' && currentMaterialGroupId.value) {
      // 更新现有素材组
      await updateMaterialGroup(currentMaterialGroupId.value, {
        name: data.name,
        description: data.description,
        tags: data.tags,
        materials,
      });

      // 更新当前记录的素材组信息
      currentMaterialGroupName.value = data.name;
      currentMaterialGroupDescription.value = data.description;

      message.success('素材组更新成功');
    } else {
      // 创建新素材组
      const response: any = await createMaterialGroup({
        name: data.name,
        description: data.description,
        materials,
      });

      // 如果是从现有素材组另存为，更新当前记录
      const responseData = response.data || response;
      if (responseData && responseData.id) {
        currentMaterialGroupId.value = responseData.id;
        currentMaterialGroupName.value = data.name;
        currentMaterialGroupDescription.value = data.description;
      }

      message.success('素材组保存成功');
    }

    showMaterialGroupSaveModal.value = false;

    // 刷新素材组列表
    if (materialGroupLoadTabRef.value) {
      materialGroupLoadTabRef.value.refresh();
    }
  } catch {}
}

// 应用素材组
async function handleMaterialGroupApply(
  groupId: string,
  mode: 'append' | 'replace',
) {
  try {
    const response: any = await applyMaterialGroup(groupId, mode);
    const responseData = response.data || response;
    const { materials, mode: appliedMode } = responseData;

    if (!materials || materials.length === 0) {
      message.warning('该素材组没有可用的素材');
      return;
    }

    // 批量获取素材的完整信息（包括图片）
    const materialIds = materials.map((m: any) => m.material_id);
    let fullMaterialsData: any[] = [];

    try {
      const materialsResponse: any = await getMaterialsByIds({
        ids: materialIds,
      });
      // 处理不同的返回格式
      const responseData = materialsResponse.data || materialsResponse;
      if (Array.isArray(responseData)) {
        fullMaterialsData = responseData;
      } else if (responseData && Array.isArray(responseData.items)) {
        fullMaterialsData = responseData.items;
      } else if (responseData && typeof responseData === 'object') {
        // 如果是单个对象，转换为数组
        fullMaterialsData = [responseData];
      }
    } catch (error) {
      console.warn('获取素材详情失败，将使用基本信息', error);
    }

    // 创建素材ID到完整数据的映射
    const materialDataMap = new Map();
    if (Array.isArray(fullMaterialsData)) {
      fullMaterialsData.forEach((mat: any) => {
        materialDataMap.set(mat._id || mat.id, mat);
      });
    }

    // 将后端返回的素材转换为前端格式，并合并完整数据
    const newMaterials = materials.map((m: any) => {
      const fullData = materialDataMap.get(m.material_id) || {};
      return {
        id: m.material_id,
        materialId: m.material_id,
        title: m.title,
        description: m.body,
        callToAction: m.call_to_action,
        displayLink: m.display_link || '',
        name:
          fullData.basename ||
          fullData.name ||
          `素材_${m.material_id.slice(0, 8)}`,
        filename: fullData.basename || fullData.filename || '',
        filetype: fullData.filetype || ('image' as 'image' | 'video'),
        unique_name: fullData.unique_name || '',
        uploadTime:
          fullData.upload_time ||
          fullData.uploadTime ||
          new Date().toISOString(),
        // 关键：添加图片数据
        img: fullData.img || fullData.thumbnail || '',
        thumbnail: fullData.thumbnail || fullData.img || '',
      };
    });

    if (appliedMode === 'replace') {
      uploadedMaterials.value = newMaterials;
      selectedMaterials.value = [];

      // 获取素材组详情，用于后续更新功能
      try {
        const groupDetail: any = await getMaterialGroupDetail(groupId);
        const groupData = groupDetail.data || groupDetail;
        currentMaterialGroupId.value = groupId;
        currentMaterialGroupName.value = groupData.name || '';
        currentMaterialGroupDescription.value = groupData.description || '';
      } catch (error) {
        console.warn('获取素材组详情失败，更新功能将不可用', error);
      }
      message.success(response.message || '素材组应用成功');
    } else {
      // 追加模式：智能去重并更新
      const existingMaterialsMap = new Map();
      uploadedMaterials.value.forEach((m) => {
        existingMaterialsMap.set(m.materialId || m.id, m);
      });

      let addedCount = 0;
      let updatedCount = 0;

      newMaterials.forEach((newMaterial) => {
        const materialId = newMaterial.materialId || newMaterial.id;
        const existingMaterial = existingMaterialsMap.get(materialId);

        if (existingMaterial) {
          // 素材已存在，更新其配置
          existingMaterial.title = newMaterial.title;
          existingMaterial.description = newMaterial.description;
          existingMaterial.callToAction = newMaterial.callToAction;
          updatedCount++;
        } else {
          // 素材不存在，追加新素材
          uploadedMaterials.value.push(newMaterial);
          addedCount++;
        }
      });

      // 追加模式下清空当前素材组记录
      currentMaterialGroupId.value = null;
      currentMaterialGroupName.value = '';
      currentMaterialGroupDescription.value = '';

      // 友好的提示信息
      const messages = [];
      if (addedCount > 0) messages.push(`新增 ${addedCount} 个素材`);
      if (updatedCount > 0)
        messages.push(`更新 ${updatedCount} 个已存在的素材`);
      message.success(
        messages.length > 0 ? `应用成功：${messages.join('，')}` : '应用成功',
      );
    }
  } catch {
  } finally {
    materialGroupLoadTabRef.value?.finishApply();
  }
}

// 重新应用历史
async function handleReapplyHistory(
  historyId: string,
  mode: 'append' | 'replace',
) {
  try {
    const response: any = await reapplyHistory(historyId, mode);
    const responseData = response.data || response;
    const { materials, mode: appliedMode } = responseData;

    if (!materials || materials.length === 0) {
      message.warning('该历史记录没有可用的素材');
      return;
    }

    // 批量获取素材的完整信息（包括图片）
    const materialIds = materials.map((m: any) => m.material_id);
    let fullMaterialsData: any[] = [];

    try {
      const materialsResponse: any = await getMaterialsByIds({
        ids: materialIds,
      });
      // 处理不同的返回格式
      const responseData = materialsResponse.data || materialsResponse;
      if (Array.isArray(responseData)) {
        fullMaterialsData = responseData;
      } else if (responseData && Array.isArray(responseData.items)) {
        fullMaterialsData = responseData.items;
      } else if (responseData && typeof responseData === 'object') {
        // 如果是单个对象，转换为数组
        fullMaterialsData = [responseData];
      }
    } catch (error) {
      console.warn('获取素材详情失败，将使用基本信息', error);
    }

    // 创建素材ID到完整数据的映射
    const materialDataMap = new Map();
    if (Array.isArray(fullMaterialsData)) {
      fullMaterialsData.forEach((mat: any) => {
        materialDataMap.set(mat._id || mat.id, mat);
      });
    }

    // 将后端返回的素材转换为前端格式，并合并完整数据
    const newMaterials = materials.map((m: any) => {
      const fullData = materialDataMap.get(m.material_id) || {};
      return {
        id: m.material_id,
        materialId: m.material_id,
        title: m.title,
        description: m.body,
        callToAction: m.call_to_action,
        displayLink: m.display_link || '',
        name:
          fullData.basename ||
          fullData.name ||
          `素材_${m.material_id.slice(0, 8)}`,
        filename: fullData.basename || fullData.filename || '',
        filetype: fullData.filetype || ('image' as 'image' | 'video'),
        unique_name: fullData.unique_name || '',
        uploadTime:
          fullData.upload_time ||
          fullData.uploadTime ||
          new Date().toISOString(),
        // 关键：添加图片数据
        img: fullData.img || fullData.thumbnail || '',
        thumbnail: fullData.thumbnail || fullData.img || '',
      };
    });

    if (appliedMode === 'replace') {
      uploadedMaterials.value = newMaterials;
      selectedMaterials.value = [];
      // 历史记录应用后清空素材组记录
      currentMaterialGroupId.value = null;
      currentMaterialGroupName.value = '';
      currentMaterialGroupDescription.value = '';
      message.success(response.message || '历史记录应用成功');
    } else {
      // 追加模式：智能去重并更新
      const existingMaterialsMap = new Map();
      uploadedMaterials.value.forEach((m) => {
        existingMaterialsMap.set(m.materialId || m.id, m);
      });

      let addedCount = 0;
      let updatedCount = 0;

      newMaterials.forEach((newMaterial) => {
        const materialId = newMaterial.materialId || newMaterial.id;
        const existingMaterial = existingMaterialsMap.get(materialId);

        if (existingMaterial) {
          // 素材已存在，更新其配置
          existingMaterial.title = newMaterial.title;
          existingMaterial.description = newMaterial.description;
          existingMaterial.callToAction = newMaterial.callToAction;
          updatedCount++;
        } else {
          // 素材不存在，追加新素材
          uploadedMaterials.value.push(newMaterial);
          addedCount++;
        }
      });

      // 友好的提示信息
      const messages = [];
      if (addedCount > 0) messages.push(`新增 ${addedCount} 个素材`);
      if (updatedCount > 0)
        messages.push(`更新 ${updatedCount} 个已存在的素材`);
      message.success(
        messages.length > 0 ? `应用成功：${messages.join('，')}` : '应用成功',
      );
    }

    showMaterialGroupHistoryModal.value = false;
  } catch {
  } finally {
    materialGroupHistoryModalRef.value?.finishApply();
  }
}

// 复用创意历史
async function handleReuseCreativeHistory(
  historyId: string,
  mode: 'append' | 'replace',
) {
  try {
    const response: any = await reuseCreativeHistory(historyId);
    const historyCreatives = response?.creatives || [];

    if (!Array.isArray(historyCreatives) || historyCreatives.length === 0) {
      message.warning('历史记录中没有素材数据');
      creativeHistoryModalRef.value?.finishReuse();
      return;
    }

    // 批量获取素材的完整信息（包括图片），图片用 image_hash，视频用 video_id
    const materialIds = historyCreatives
      .map((c: any) => c.image_hash || c.video_id)
      .filter(Boolean);

    let fullMaterialsData: any[] = [];

    if (materialIds.length > 0) {
      try {
        const materialsResponse: any = await getMaterialsByIds({
          ids: materialIds,
        });
        // 处理不同的返回格式
        const responseData = materialsResponse.data || materialsResponse;
        if (Array.isArray(responseData)) {
          fullMaterialsData = responseData;
        } else if (responseData && Array.isArray(responseData.items)) {
          fullMaterialsData = responseData.items;
        } else if (responseData && typeof responseData === 'object') {
          // 如果是单个对象，转换为数组
          fullMaterialsData = [responseData];
        }
      } catch (error) {
        console.warn('获取素材详情失败，将使用历史记录中的基本信息', error);
      }
    }

    // 创建素材ID到完整数据的映射
    const materialDataMap = new Map();
    if (Array.isArray(fullMaterialsData)) {
      fullMaterialsData.forEach((mat: any) => {
        materialDataMap.set(mat._id || mat.id, mat);
      });
    }

    // 转换历史创意数据为素材格式，并合并完整数据
    const newMaterials = historyCreatives.map(
      (creative: any, index: number) => {
        const materialId =
          creative.image_hash ||
          creative.video_id ||
          `history_${Date.now()}_${index}`;
        const fullData = materialDataMap.get(materialId) || {};

        return {
          id: materialId,
          materialId,
          title: creative.title || '',
          description: creative.body || creative.description || '',
          callToAction: creative.call_to_action?.type || '',
          displayLink: creative.display_link || '',
          name:
            fullData.basename ||
            fullData.name ||
            creative.basename ||
            creative.image_hash ||
            creative.video_id ||
            `素材_${index + 1}`,
          filename:
            fullData.basename ||
            fullData.filename ||
            creative.basename ||
            creative.image_hash ||
            creative.video_id ||
            '',
          filetype:
            fullData.filetype ||
            creative.filetype ||
            (creative.type === 'video' ? 'video' : 'image'),
          unique_name:
            fullData.unique_name ||
            fullData.basename ||
            creative.basename ||
            creative.image_hash ||
            creative.video_id ||
            '',
          uploadTime:
            fullData.upload_time ||
            fullData.uploadTime ||
            new Date().toISOString(),
          // 关键：添加图片数据
          img:
            fullData.img ||
            fullData.thumbnail ||
            creative.img ||
            creative.picture ||
            creative.path ||
            '',
          thumbnail:
            fullData.thumbnail ||
            fullData.img ||
            creative.img ||
            creative.picture ||
            creative.path ||
            '',
        };
      },
    );

    if (mode === 'replace') {
      uploadedMaterials.value = newMaterials;
      selectedMaterials.value = [];
      message.success(`已替换为历史创意（${newMaterials.length} 个素材）`);
    } else {
      // 追加模式：智能去重并更新创意配置
      const existingMaterialsMap = new Map();
      uploadedMaterials.value.forEach((m) => {
        existingMaterialsMap.set(m.materialId || m.id, m);
      });

      let addedCount = 0;
      let updatedCount = 0;

      newMaterials.forEach((newMaterial) => {
        const materialId = newMaterial.materialId || newMaterial.id;
        const existingMaterial = existingMaterialsMap.get(materialId);

        if (existingMaterial) {
          // 素材已存在，更新创意配置
          existingMaterial.title = newMaterial.title;
          existingMaterial.description = newMaterial.description;
          existingMaterial.callToAction = newMaterial.callToAction;
          updatedCount++;
        } else {
          // 素材不存在，追加新素材
          uploadedMaterials.value.push(newMaterial);
          addedCount++;
        }
      });

      const messages = [];
      if (addedCount > 0) messages.push(`新增 ${addedCount} 个素材`);
      if (updatedCount > 0)
        messages.push(`更新 ${updatedCount} 个素材的创意配置`);
      message.success(
        messages.length > 0 ? `应用成功：${messages.join('，')}` : '应用成功',
      );
    }

    showCreativeHistoryModal.value = false;
  } catch {
  } finally {
    creativeHistoryModalRef.value?.finishReuse();
  }
}

const showProgressModal = ref(false);
const userStore = useUserStore();

// 处理模板应用
function handleTemplateApply(templateData: any) {
  appliedTemplateId.value = templateData.id || null;
  appliedTemplateName.value = templateData.name || '';
  appliedTemplateDescription.value = templateData.description || '';

  const rawConfig = templateData.configData || templateData;
  const cfg = rawConfig.settings || rawConfig;

  applySettingsConfig(cfg);

  message.success('模板应用成功');
}

function handleQueryProgress() {
  showProgressModal.value = true;
}

// Step 3: Material Structure
const adsPerGroup = ref<number | undefined>(1);
// 素材分配模式,后续会扩展更多模式

// Computed
const stepTitles = ['广告账户设置', '广告系列和广告组设置', '广告结构'];

// 广告账户总数
const totalAdvertisers = computed(() => {
  return selectedTasksData.value.reduce((sum, task) => {
    return sum + (task.advertisers?.length || 0);
  }, 0);
});

// 一共创建的广告系列数量
const totalCreated = computed(() => {
  return seriesList.value.length;
});

// 广告组总数
const totalAdGroups = computed(() => {
  return seriesList.value.reduce(
    (sum, series) => sum + series.regionGroups.length,
    0,
  );
});

// 需要上传的广告数量 = 账户个数 × 广告组总数 × 每个广告组的广告数
const totalMaterials = computed(() => {
  if (!adsPerGroup.value) return 0;
  const advertisersCount = totalAdvertisers.value;
  const adGroupsCount = totalAdGroups.value;

  const adsCount = adsPerGroup.value;
  // 总广告数量 = 账户个数 × 广告组总数 × 每个广告组的广告数
  return advertisersCount * adGroupsCount * adsCount;
});

// 创建广告前的确认弹窗
const showConfirmModal = ref(false);

// 确认弹窗：已选任务线（任务线 → 链接 → 账户），结构同步骤一“已选任务线”
const confirmTaskList = computed(() =>
  selectedTasksData.value.map((task) => ({
    taskName: task.taskName || '',
    projectName: task.projectName || '',
    regionName: task.regionName || '',
    url: task.url || '',
    accounts: (task.advertisers ?? [])
      .filter((adv) => adv.account)
      .map((adv) => ({
        account: adv.accountName || adv.name || adv.account,
        accountId: adv.account || '',
        person: adv.personAccountName || '',
        page: adv.publicPage || '',
        pixel: adv.pixel || '',
      })),
  })),
);

// 确认弹窗：账户总数
const confirmAccountCount = computed(() =>
  confirmTaskList.value.reduce((sum, task) => sum + task.accounts.length, 0),
);

// 确认弹窗：广告系列结构 + 系列预算/组预算
const confirmSeriesSummary = computed(() => {
  // 排期时间为全局设置,所有广告组一致
  const scheduleText = `${scheduleStartTime.value?.format('YYYY-MM-DD HH:mm') ?? '立即开始'} ~ ${scheduleEndTime.value?.format('YYYY-MM-DD HH:mm') ?? '长期投放'}`;
  return seriesList.value.map((series) => {
    const s = series.seriesSettings;
    const isCampaignBudget = s.objectiveType === '广告系列预算';
    const budgetText = `${s.budgetType} ${s.budget} ${s.currency}`;
    return {
      id: series.id,
      name: series.name,
      groupCount: series.regionGroups.length,
      groupNames: series.regionGroups.map((g) => g.name).join('、'),
      schedule: scheduleText,
      campaignBudget: isCampaignBudget ? budgetText : '',
      adsetBudget: isCampaignBudget ? '' : budgetText,
    };
  });
});

// Select搜索过滤函数
const filterSelectOption = (input: string, option: any) => {
  const text = option.label || '';
  return text.toLowerCase().includes(input.toLowerCase());
};

const countryMap = Object.fromEntries(
  countriesData.map((c: { code: string; name: string }) => [
    c.code,
    `${c.name}`,
  ]),
);

// 地区组可用国家：特殊广告类别非空时只显示系列已选的国家
function getGroupCountries(series: SeriesData) {
  const codes = series.seriesSettings.specialAdCategories;
  if (!codes?.length) return countriesData;
  const allowed = new Set(series.seriesSettings.specialAdCountries ?? []);
  return specialAdCountriesData.filter((c: { code: string; name: string }) =>
    allowed.has(c.code),
  );
}

watch(showMaterialModal, (val) => {
  if (val) loadOperatorOptions();
});
watch(showProgressModal, (val) => {
  if (val) loadOperatorOptions();
});

onMounted(async () => {
  document.addEventListener('keydown', handleKeyDown);
  compactBuilderQuery.addEventListener('change', handleBuilderBreakpoint);
  // 首次进入先加载默认范围，展开选择框即可选项目和代理线。
  await loadAgentOptions();
  if (isDemoMockEnabled && selectedTasksData.value.length === 0) {
    const firstPlatform = platformAgentData.value[0];
    const demoLines = firstPlatform?.agent_lines?.slice(0, 2) ?? [];
    selectedProducts.value = demoLines.map((line) => [
      firstPlatform
        ? getPlatformOptionValue(firstPlatform, 0)
        : 'platform_0_Starfall 全球增长',
      line,
    ]);
    if (selectedProducts.value.length > 0) {
      await handleProcessSelectedTasks();
    }
  }
});

// 首次由 onMounted 加载；再次进入缓存页面时恢复默认选项，避免保留上次搜索结果。
let hasActivatedAgentOptions = false;
onActivated(() => {
  if (hasActivatedAgentOptions) {
    agentOptionsSearchText.value = '';
    void loadAgentOptions();
  }
  hasActivatedAgentOptions = true;
});

// 组件卸载时清理事件监听
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeyDown);
  document.removeEventListener('mousemove', updateSelection);
  document.removeEventListener('mouseup', endSelection);
  compactBuilderQuery.removeEventListener('change', handleBuilderBreakpoint);
});
</script>

<template>
  <div
    class="adpulse-section-page adpulse-builder-page min-h-full min-w-0 overflow-hidden bg-slate-50"
  >
    <div
      class="ad-builder-layout mx-auto flex h-full min-h-0 items-center justify-center gap-6 overflow-hidden px-6"
    >
      <!-- 左侧 Steps 导航 -->
      <div class="ad-builder-steps relative w-[215px] shrink-0">
        <Steps
          :direction="compactBuilder ? 'horizontal' : 'vertical'"
          :responsive="false"
          :current="currentStep"
          @change="handleStepChange"
        >
          <Steps.Step v-for="(title, index) in stepTitles" :key="index">
            <template #title>
              <Tooltip>
                <template #title>
                  <div>点击可切换进度</div>
                </template>
                <span>{{ title }}</span>
              </Tooltip>
            </template>
          </Steps.Step>
        </Steps>
        <!-- 上下一步按钮 -->
        <div
          class="builder-step-actions mx-auto mt-5 flex flex-col justify-center gap-3"
        >
          <template v-if="currentStep === 0">
            <div class="flex items-end gap-4">
              <Button type="primary" @click="handleQueryProgress">
                查询进度
              </Button>
              <Button type="primary" class="rounded-md" @click="nextStep">
                下一步
              </Button>
            </div>
          </template>

          <template v-else-if="currentStep === 1">
            <div class="flex items-end gap-4">
              <Button type="primary" @click="handleQueryProgress">
                查询进度
              </Button>
              <div class="flex flex-col items-center gap-2">
                <Button class="rounded-md" @click="prevStep">上一步</Button>
                <Button type="primary" class="rounded-md" @click="nextStep">
                  下一步
                </Button>
              </div>
            </div>
          </template>

          <template v-else-if="currentStep === 2">
            <div class="flex items-end gap-4">
              <Button type="primary" @click="handleQueryProgress">
                查询进度
              </Button>
              <div class="flex flex-col items-center gap-2">
                <Button
                  class="rounded-md"
                  :disabled="creatingAd"
                  @click="prevStep"
                >
                  上一步
                </Button>
                <Button
                  type="primary"
                  class="rounded-md"
                  :loading="creatingAd"
                  :disabled="creatingAd || adCreatingCooldown"
                  @click="handleCreateAdvertisement"
                >
                  创建广告
                </Button>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 主内容区域 -->
      <div class="ad-builder-content h-full min-w-0 flex-1 overflow-auto py-3">
        <div v-show="currentStep === 0" class="h-full">
          <div class="rounded-xl border border-gray-100 bg-white p-8 shadow-sm">
            <div class="mb-6 flex items-center justify-between">
              <h3 class="text-xl font-semibold text-gray-800">广告账户设置:</h3>
            </div>

            <div class="mb-6">
              <div class="builder-mode-row mb-1 flex items-center gap-3">
                <span class="text-sm font-medium text-gray-700"
                  >选择任务线：</span
                >
                <span class="text-sm text-gray-500">个人授权资产</span>
              </div>
              <div class="builder-task-row flex items-center gap-3">
                <span class="invisible text-sm font-medium">选择任务线：</span>
                <div class="builder-cascader-container" :aria-busy="loading">
                  <Cascader
                    v-model:value="selectedProducts"
                    :search-value="agentOptionsSearchText"
                    :options="cascaderOptions"
                    :loading="loading"
                    show-arrow
                    aria-label="选择任务线"
                    :disabled="processingTasks"
                    placeholder="请选择项目和代理线，可输入搜索"
                    style="width: 300px"
                    class="builder-cascader"
                    :show-search="{ filter: () => true }"
                    multiple
                    show-checked-strategy="SHOW_CHILD"
                    max-tag-count="responsive"
                    @search="handleCascaderSearch"
                  >
                    <template #tagRender="{ value, label }">
                      <Tag
                        :key="Array.isArray(value) ? value.join(',') : value"
                        color="blue"
                      >
                        {{
                          Array.isArray(value) && value.length === 2
                            ? `${value[1]}`
                            : label
                        }}
                      </Tag>
                    </template>
                  </Cascader>
                </div>
                <Button
                  type="primary"
                  :loading="processingTasks"
                  :disabled="
                    processingTasks ||
                    !selectedProducts ||
                    selectedProducts.length === 0
                  "
                  class="rounded-md text-white"
                  @click="handleProcessSelectedTasks"
                >
                  添加
                </Button>
                <Button
                  :disabled="processingTasks"
                  class="rounded-md"
                  @click="openPasteAdd"
                >
                  批量添加
                </Button>
                <button
                  class="relative flex items-center gap-1.5 overflow-hidden rounded-md px-3 py-1.5 text-sm font-medium text-white shadow-sm transition-all hover:shadow-md hover:brightness-110 active:scale-95"
                  style="
                    background: linear-gradient(
                      135deg,
                      #6366f1 0%,
                      #8b5cf6 50%,
                      #a855f7 100%
                    );
                  "
                  @click="openAiSuggestion"
                >
                  <span style="font-size: 15px">✦</span>
                  AI建议
                </button>
                <div
                  class="builder-batch-actions ml-auto flex items-center gap-3"
                >
                  <Button class="rounded-md" @click="openBatchEdit">
                    批量设置{{
                      batchSelectedCount > 0 ? `(${batchSelectedCount})` : ''
                    }}
                  </Button>
                  <Button class="rounded-md" @click="openBatchAdd">
                    批量新增{{
                      batchAddSelectedCount > 0
                        ? `(${batchAddSelectedCount})`
                        : ''
                    }}
                  </Button>
                </div>
              </div>
            </div>
            <Modal
              v-model:open="batchEditOpen"
              title="批量设置"
              width="420px"
              :ok-text="`设置(${batchSelectedCount})`"
              :confirm-loading="batchEditLoading"
              @ok="handleBatchEditConfirm"
            >
              <div class="flex flex-col gap-4 py-2">
                <div class="text-xs text-gray-400">
                  对已勾选的
                  {{ batchSelectedCount }} 个账户行生效，留空的项不设置
                </div>
                <div class="flex items-center gap-2">
                  <span class="w-14 shrink-0 text-sm text-gray-700"
                    >账户：</span
                  >
                  <Input
                    v-model:value="batchEditAccountId"
                    allow-clear
                    placeholder="输入广告账户ID"
                  />
                </div>
                <div class="flex items-center gap-2">
                  <span class="w-14 shrink-0 text-sm text-gray-700"
                    >个号：</span
                  >
                  <Select
                    v-model:value="batchEditPersonName"
                    class="flex-1"
                    show-search
                    allow-clear
                    :filter-option="filterSelectOption"
                    placeholder="选择个号"
                  >
                    <Select.Option
                      v-for="name in batchEditPersonOptions"
                      :key="name"
                      :value="name"
                      :label="name"
                    >
                      <OverflowTooltip :text="name" />
                    </Select.Option>
                  </Select>
                </div>
                <div class="flex items-center gap-2">
                  <span class="w-14 shrink-0 text-sm text-gray-700"
                    >主页：</span
                  >
                  <Select
                    v-model:value="batchEditPageId"
                    class="flex-1"
                    show-search
                    allow-clear
                    :filter-option="filterSelectOption"
                    placeholder="选择主页"
                  >
                    <Select.Option
                      v-for="page in batchEditPageOptions"
                      :key="page.id"
                      :value="page.id"
                      :label="page.name"
                    >
                      <OverflowTooltip :text="page.name" />
                    </Select.Option>
                  </Select>
                </div>
              </div>
            </Modal>
            <Modal
              v-model:open="pasteAddOpen"
              title="批量添加任务线"
              width="480px"
              ok-text="解析并添加"
              :confirm-loading="pasteAddLoading || processingTasks"
              @ok="handlePasteAddConfirm"
            >
              <div class="flex flex-col gap-2 py-2">
                <div class="text-xs text-gray-400">
                  粘贴代理线名称，一行一个（也支持逗号、顿号、分号分隔），解析后自动添加到已选任务线
                </div>
                <Textarea
                  v-model:value="pasteAddText"
                  :rows="8"
                  placeholder="粘贴代理线名称"
                />
              </div>
            </Modal>
            <Modal
              v-model:open="batchAddOpen"
              title="批量新增"
              width="480px"
              :ok-text="`新增(${batchAddSelectedCount})`"
              :confirm-loading="batchAddLoading || batchAddValidating"
              @ok="handleBatchAddConfirm"
            >
              <div class="flex flex-col gap-4 py-2">
                <div class="text-xs text-gray-400">
                  向表格中已勾选的 {{ batchAddSelectedCount }}
                  条任务线各新增一行该账户，像素自动使用对应任务线的像素；个号、主页留空则用默认值
                </div>
                <div class="flex items-center gap-2">
                  <span class="w-16 shrink-0 text-sm text-gray-700"
                    >账户：</span
                  >
                  <Input
                    v-model:value="batchAddAccountId"
                    allow-clear
                    placeholder="输入广告账户ID"
                  />
                  <Button
                    :loading="batchAddValidating"
                    @click="handleBatchAddValidate"
                  >
                    校验
                  </Button>
                </div>
                <div class="flex items-center gap-2">
                  <span class="w-16 shrink-0 text-sm text-gray-700"
                    >个号：</span
                  >
                  <Select
                    v-model:value="batchAddPersonName"
                    class="flex-1"
                    show-search
                    allow-clear
                    :disabled="batchAddFound.size === 0"
                    :filter-option="filterSelectOption"
                    placeholder="校验账户后可选，留空用默认"
                  >
                    <Select.Option
                      v-for="name in batchAddPersonOptions"
                      :key="name"
                      :value="name"
                      :label="name"
                    >
                      <OverflowTooltip :text="name" />
                    </Select.Option>
                  </Select>
                </div>
                <div class="flex items-center gap-2">
                  <span class="w-16 shrink-0 text-sm text-gray-700"
                    >主页：</span
                  >
                  <Select
                    v-model:value="batchAddPageId"
                    class="flex-1"
                    show-search
                    allow-clear
                    :disabled="batchAddFound.size === 0"
                    :filter-option="filterSelectOption"
                    placeholder="校验账户后可选，留空用默认"
                  >
                    <Select.Option
                      v-for="page in batchAddPageOptions"
                      :key="page.id"
                      :value="page.id"
                      :label="page.name"
                    >
                      <OverflowTooltip :text="page.name" />
                    </Select.Option>
                  </Select>
                </div>
              </div>
            </Modal>
            <Modal
              v-model:open="aiSuggestionOpen"
              title="AI建议"
              :footer="null"
              width="1200px"
              destroy-on-close
            >
              <div class="mb-3 flex items-center gap-2">
                <span class="shrink-0 text-sm text-gray-600"
                  >选择AI建议报告：</span
                >
                <Select
                  v-model:value="aiSuggestionSelectedId"
                  :options="aiSuggestionSelectOptions"
                  class="flex-1"
                  placeholder="请选择 AI 建议报告"
                  @change="handleAiReportSelect"
                />
                <Button
                  :disabled="!aiSuggestionSrc"
                  :loading="aiSuggestionDownloading"
                  type="primary"
                  @click="downloadAiReport"
                >
                  下载报告
                </Button>
              </div>
              <Spin :spinning="aiSuggestionIframeLoading" tip="报告加载中...">
                <div style="height: 75vh">
                  <iframe
                    v-if="aiSuggestionSrc"
                    :src="aiSuggestionSrc"
                    class="size-full"
                    style="border: none"
                  ></iframe>
                  <div
                    v-else
                    class="flex size-full flex-col items-center justify-center text-gray-400"
                  >
                    <span style="font-size: 40px">✦</span>
                    <span class="mt-2 text-sm"
                      >请从上方选择一份 AI 建议报告</span
                    >
                  </div>
                </div>
              </Spin>
            </Modal>

            <div class="mb-6 flex flex-col">
              <h4 class="mb-4 text-sm font-semibold text-gray-700">
                已选任务线：
              </h4>
              <div class="min-h-0 flex-1">
                <Table
                  :columns="taskColumns"
                  :data-source="selectedTasksData"
                  :pagination="false"
                  :scroll="{ x: 'max-content', y: 340 }"
                  :row-selection="{
                    selectedRowKeys: batchAddTaskCodes,
                    onChange: handleTaskSelectionChange,
                  }"
                  row-key="taskCode"
                  bordered
                >
                  <template #headerCell="{ column }">
                    <template v-if="column.key === 'advertisers'">
                      <div class="flex items-center gap-3">
                        <span>广告账户</span>
                        <Checkbox
                          :checked="isAllBatchSelected"
                          :indeterminate="
                            batchSelectedCount > 0 && !isAllBatchSelected
                          "
                          :disabled="allAdvSelectKeys.length === 0"
                          @change="toggleBatchSelectAll"
                        >
                          全选
                        </Checkbox>
                      </div>
                    </template>
                  </template>
                  <template #bodyCell="{ column, record, index }">
                    <template v-if="column.key === 'advertisers'">
                      <div class="flex flex-col gap-2">
                        <div
                          v-for="(adv, advIndex) in record.advertisers || []"
                          :key="adv.id || advIndex"
                          class="flex flex-wrap items-center gap-2"
                        >
                          <Checkbox
                            :checked="isAdvSelected(record, adv)"
                            @change="
                              (e) =>
                                toggleBatchSelect(record, adv, e.target.checked)
                            "
                          />
                          <div>
                            <span>账户：</span>
                            <Select
                              :value="adv.account"
                              placeholder="搜索账户名称/ID"
                              style="width: 220px"
                              show-search
                              allow-clear
                              :filter-option="false"
                              @search="(v) => onAccountSearch(record, adv, v)"
                              @change="
                                handleAccountChange(index, advIndex, $event)
                              "
                            >
                              <Select.Option
                                v-for="acc in getAccountOptions(record, adv)"
                                :key="acc.ad_account_id"
                                :value="acc.ad_account_id"
                                :label="acc.ad_account_name"
                              >
                                <div class="flex flex-col gap-0.5">
                                  <OverflowTooltip
                                    :text="acc.ad_account_name"
                                  />
                                  <span
                                    class="w-full overflow-hidden text-ellipsis whitespace-nowrap text-xs text-gray-400"
                                    >{{ acc.ad_account_id }}</span
                                  >
                                </div>
                              </Select.Option>
                            </Select>
                          </div>

                          <div>
                            <span>个号：</span>
                            <Select
                              :value="adv.personAccountName"
                              placeholder="选择个号"
                              style="width: 155px"
                              show-search
                              allow-clear
                              :filter-option="filterSelectOption"
                              @change="
                                handlePersonAccountChange(
                                  index,
                                  advIndex,
                                  $event,
                                )
                              "
                            >
                              <Select.Option
                                v-for="person in adv.personAccountOptions"
                                :key="person.name"
                                :value="person.name"
                                :label="person.name"
                              >
                                <OverflowTooltip :text="person.name" />
                              </Select.Option>
                            </Select>
                          </div>

                          <div>
                            <span>主页：</span>
                            <Select
                              :value="adv.selectedPublicPage"
                              placeholder="支持模糊搜索"
                              style="width: 160px"
                              show-search
                              allow-clear
                              :filter-option="filterSelectOption"
                              :disabled="!adv.personAccountName"
                              @change="
                                handlePublicPageChange(index, advIndex, $event)
                              "
                            >
                              <Select.Option
                                v-for="page in getFilteredPublicPagesForAdvertiser(
                                  adv,
                                )"
                                :key="page.id"
                                :value="page.id"
                                :label="page.name"
                              >
                                <div
                                  style="
                                    display: flex;
                                    gap: 6px;
                                    align-items: center;
                                  "
                                >
                                  <img
                                    v-if="page.picture"
                                    alt=""
                                    :src="page.picture"
                                    style="
                                      flex-shrink: 0;
                                      width: 18px;
                                      height: 18px;
                                      object-fit: cover;
                                      border-radius: 50%;
                                    "
                                  />
                                  <OverflowTooltip :text="page.name" />
                                </div>
                              </Select.Option>
                            </Select>
                          </div>

                          <div>
                            <span>像素：</span>
                            <Select
                              :value="adv.selectedPixel"
                              placeholder="选择像素"
                              style="width: 160px"
                              show-search
                              allow-clear
                              :filter-option="filterSelectOption"
                              @change="
                                handlePixelChange(index, advIndex, $event)
                              "
                            >
                              <Select.Option
                                v-for="pixel in adv.pixelOptions || []"
                                :key="pixel.id"
                                :value="pixel.id"
                                :label="pixel.name"
                              >
                                <OverflowTooltip :text="pixel.name" />
                              </Select.Option>
                            </Select>
                          </div>

                          <Button
                            type="text"
                            danger
                            @click="removeAdvertiser(index, adv.id)"
                          >
                            <span
                              class="icon-[ant-design--close-outlined]"
                            ></span>
                          </Button>
                        </div>

                        <Button
                          type="dashed"
                          class="rounded-md"
                          style="width: fit-content"
                          @click="openAdvertiserModal(index)"
                        >
                          + 选择账户
                        </Button>
                      </div>
                    </template>
                    <template v-if="column.key === 'action'">
                      <div class="flex items-center gap-2">
                        <Button
                          type="link"
                          danger
                          class="rounded-md"
                          @click="deleteTask(index)"
                        >
                          删除
                        </Button>
                      </div>
                    </template>
                  </template>
                </Table>
              </div>
            </div>

            <div
              class="space-y-4 rounded-lg border border-blue-100/50 bg-blue-50/30 p-6"
            >
              <h4 class="mb-4 text-sm font-semibold text-gray-700">
                广告名称设置
              </h4>
              <div class="grid w-[380px] grid-cols-1 gap-4">
                <div class="flex items-center gap-4">
                  <span class="w-24 text-sm text-gray-600">广告系列名称:</span>
                  <Input
                    v-model:value="step1Data.seriesName"
                    :disabled="true"
                    class="flex-1"
                  />
                </div>
                <div class="flex items-center gap-4">
                  <span class="w-24 text-sm text-gray-600">广告组名称:</span>
                  <Input
                    v-model:value="step1Data.groupName"
                    :disabled="true"
                    class="flex-1"
                  />
                </div>
                <div class="flex items-center gap-4">
                  <span class="w-24 text-sm text-gray-600">广告名称:</span>
                  <Input
                    v-model:value="step1Data.adName"
                    :disabled="true"
                    class="flex-1"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-show="currentStep === 1" class="h-full">
          <Tabs
            v-model:active-key="activeSeriesKey"
            type="editable-card"
            :hide-add="false"
            @edit="handleTabEdit"
          >
            <Tabs.TabPane
              v-for="(series, index) in seriesList"
              :key="series.id"
              :closable="false"
            >
              <template #tab>
                <div class="flex items-center gap-2">
                  <span>{{ series.name }}</span>
                  <Popover
                    :open="!!seriesClone.openMap[series.id]"
                    trigger="click"
                    placement="bottom"
                    @open-change="
                      (open) => seriesClone.setOpen(series.id, open)
                    "
                  >
                    <template #content>
                      <div class="w-[220px] space-y-2 p-2">
                        <div class="flex items-center justify-between gap-2">
                          <span class="text-sm text-gray-700">克隆数量</span>
                          <InputNumber
                            :min="CLONE_MIN"
                            :value="seriesClone.getCount(series.id)"
                            style="width: 120px"
                            @change="
                              (val) =>
                                seriesClone.setCount(
                                  series.id,
                                  Number(val ?? 1),
                                )
                            "
                          />
                        </div>
                        <div class="flex items-center justify-end gap-2">
                          <Button @click="seriesClone.setOpen(series.id, false)"
                            >取消</Button
                          >
                          <Button
                            type="primary"
                            @click="
                              () => {
                                cloneSeries(
                                  series.id,
                                  seriesClone.getCount(series.id),
                                );
                                seriesClone.setOpen(series.id, false);
                              }
                            "
                            >确定</Button
                          >
                        </div>
                      </div>
                    </template>
                    <span class="cursor-pointer text-[12px] text-blue-500"
                      >克隆</span
                    >
                  </Popover>
                  <Button
                    type="link"
                    class="p-0 text-[12px]"
                    danger
                    @click="deleteSeries(series.id)"
                  >
                    删除
                  </Button>
                </div>
              </template>
              <Card class="mb-4 rounded-lg shadow-sm">
                <template #title>
                  <div class="flex items-center gap-2">
                    <span>广告系列设置</span>
                    <div class="flex items-center gap-2">
                      <Button
                        class="rounded-md"
                        type="primary"
                        :disabled="creatingAd"
                        @click="showTemplateModal = true"
                      >
                        {{ appliedTemplateId ? '更新模板' : '保存模板' }}
                      </Button>
                      <TemplateLoadTab
                        ref="templateLoadTabRef"
                        :user-options="operatorOptions"
                        @apply="handleTemplateApply"
                        @open="loadOperatorOptions"
                      />
                    </div>
                  </div>
                </template>
                <div class="space-y-4">
                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 购买类型:
                    </span>
                    <Radio.Group
                      v-model:value="series.seriesSettings.purchaseType"
                    >
                      <Radio.Button value="竞拍">竞拍</Radio.Button>
                    </Radio.Group>
                  </div>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 广告系列目标:
                    </span>
                    <Radio.Group
                      v-model:value="series.seriesSettings.seriesType"
                    >
                      <Radio.Button value="销量">销量</Radio.Button>
                      <Radio.Button value="流量">流量</Radio.Button>
                      <Radio.Button value="潜在客户">潜在客户</Radio.Button>
                      <Radio.Button value="互动">互动</Radio.Button>
                      <Radio.Button value="认知度">认知度</Radio.Button>
                      <Radio.Button value="应用推广">应用推广</Radio.Button>
                    </Radio.Group>
                  </div>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 预算类型:
                    </span>
                    <Radio.Group
                      v-model:value="series.seriesSettings.objectiveType"
                    >
                      <Radio.Button value="广告系列预算">
                        广告系列预算
                      </Radio.Button>
                      <Radio.Button value="广告组预算">广告组预算</Radio.Button>
                    </Radio.Group>
                  </div>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                    </span>
                    <Select
                      v-model:value="series.seriesSettings.budgetType"
                      style="width: 200px"
                    >
                      <Select.Option value="单日预算">单日预算</Select.Option>
                      <Select.Option value="总预算">总预算</Select.Option>
                    </Select>
                    <Input
                      v-model:value.number="series.seriesSettings.budget"
                      type="number"
                      :min="0"
                      :step="0.01"
                      class="ml-4"
                      style="width: 260px"
                    >
                      <template #addonAfter>
                        {{ series.seriesSettings.currency }}
                      </template>
                    </Input>
                  </div>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 竞价策略:
                    </span>
                    <Select
                      v-model:value="series.seriesSettings.targetPrice"
                      style="width: 200px"
                      option-label-prop="label"
                    >
                      <Select.Option
                        value="LOWEST_COST_WITHOUT_CAP"
                        label="最高数量"
                        title="在你的预算条件下，最大限度地提升成效"
                      >
                        <span>最高数量</span>
                      </Select.Option>
                      <Select.Option
                        value="COST_CAP"
                        label="单次成效费用目标"
                        title="获得特定的单次成效费用，同时最大限度地提高成效数量"
                      >
                        <span>单次成效费用目标</span>
                      </Select.Option>
                      <Select.Option
                        value="LOWEST_COST_WITH_BID_CAP"
                        label="竞价上限"
                        title="控制每次竞拍的最高出价"
                      >
                        <span>竞价上限</span>
                      </Select.Option>
                    </Select>
                    <Input
                      v-if="
                        series.seriesSettings.targetPrice !==
                        'LOWEST_COST_WITHOUT_CAP'
                      "
                      v-model:value="series.seriesSettings.targetValue"
                      type="number"
                      :min="0"
                      :step="0.01"
                      class="ml-4"
                      style="width: 260px"
                      :placeholder="
                        series.seriesSettings.targetPrice === 'COST_CAP'
                          ? '单次成效费用目标'
                          : '竞价上限'
                      "
                    >
                      <template #addonAfter>
                        {{ series.seriesSettings.currency }}
                      </template>
                    </Input>
                  </div>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 投放类型:
                    </span>
                    <Radio.Group
                      v-model:value="series.seriesSettings.optimizationMethod"
                    >
                      <Radio.Button value="标准">标准</Radio.Button>
                    </Radio.Group>
                  </div>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 广告系列花费限额:
                    </span>
                    <Radio.Group
                      v-model:value="series.seriesSettings.flowOptimization"
                    >
                      <Radio.Button value="不限">不限</Radio.Button>
                      <Radio.Button value="自定义">自定义</Radio.Button>
                    </Radio.Group>
                    <Input
                      v-if="series.seriesSettings.flowOptimization === '自定义'"
                      v-model:value.number="
                        series.seriesSettings.flowOptimizationAmount
                      "
                      type="number"
                      :min="0"
                      class="ml-4"
                      style="width: 260px"
                    >
                      <template #addonAfter>USD</template>
                    </Input>
                  </div>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      特殊广告类别:
                    </span>
                    <Select
                      v-model:value="series.seriesSettings.specialAdCategories"
                      mode="multiple"
                      placeholder="请选择"
                      style="width: 300px"
                      allow-clear
                      max-tag-count="responsive"
                    >
                      <Select.Option value="FINANCIAL_PRODUCTS_SERVICES"
                        >金融产品和服务</Select.Option
                      >
                      <Select.Option value="EMPLOYMENT">就业</Select.Option>
                      <Select.Option value="HOUSING">住房</Select.Option>
                    </Select>
                  </div>

                  <div
                    v-if="series.seriesSettings.specialAdCategories?.length"
                    class="flex items-center gap-4"
                  >
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 国家:
                    </span>
                    <Select
                      v-model:value="series.seriesSettings.specialAdCountries"
                      mode="multiple"
                      placeholder="请选择"
                      style="width: 300px"
                      show-search
                      allow-clear
                      :filter-option="filterSelectOption"
                      max-tag-count="responsive"
                    >
                      <Select.Option
                        v-for="country in specialAdCountriesData"
                        :key="country.code"
                        :value="country.code"
                        :label="country.name"
                      >
                        {{ country.name }}
                      </Select.Option>
                    </Select>
                  </div>

                  <div class="flex items-start gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      自动广告主:
                    </span>
                    <Switch
                      v-model:checked="
                        series.seriesSettings.autoRegulationIdentity
                      "
                    />
                    <div class="flex flex-col gap-1">
                      <span class="text-xs text-gray-400">
                        投巴西等受限地区时，自动复用本账户已验证的广告主身份
                      </span>
                      <span class="text-xs font-medium text-gray-700">
                        需账户下先手动创建一个广告组，且包含「广告信息公示」、其中「广告主（选填）」已选择实际的广告主，否则无可复用的身份
                      </span>
                    </div>
                  </div>

                  <div class="flex items-start gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      多广告主广告:
                    </span>
                    <Switch
                      v-model:checked="series.seriesSettings.contextualMultiAds"
                    />
                    <div class="flex flex-col gap-1">
                      <span class="text-xs text-gray-400">
                        开启后广告可与其他广告主的广告一同展示，提升曝光机会
                      </span>
                    </div>
                  </div>

                  <Collapse ghost>
                    <Collapse.Panel
                      key="brand-safety"
                      header="品牌安全和适配性"
                    >
                      <div class="flex items-start gap-4">
                        <span class="w-40 text-sm font-medium text-gray-700">
                          库存筛选方案:
                        </span>
                        <Select
                          v-model:value="
                            series.seriesSettings.inventoryFilterLevel
                          "
                          style="width: 300px"
                        >
                          <Select.Option value="RELAXED"
                            >扩展库存</Select.Option
                          >
                          <Select.Option value="STANDARD"
                            >适量库存</Select.Option
                          >
                          <Select.Option value="STRICT">设限库存</Select.Option>
                          <Select.Option value="OFF">关闭</Select.Option>
                        </Select>
                        <div class="flex flex-col gap-1">
                          <span class="text-xs text-gray-400">
                            FB
                            默认为扩展库存（覆盖最广）；适量/设限逐级排除敏感内容，覆盖变窄、费用可能提高；关闭则不传该字段，由
                            FB 自行处理
                          </span>
                        </div>
                      </div>
                    </Collapse.Panel>
                  </Collapse>
                </div>
              </Card>

              <Card title="创建广告组" class="mb-4 rounded-lg shadow-sm">
                <div class="mb-6 space-y-4">
                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 转化发生位置:
                    </span>
                    <Select
                      v-model:value="conversionLocation"
                      placeholder="请选择转化发生位置"
                      style="width: 300px"
                    >
                      <Select.Option
                        v-for="option in currentConversionLocationOptions"
                        :key="option.value"
                        :value="option.value"
                        :disabled="
                          option.value === 'APP' && isAppLocationDisabled
                        "
                      >
                        {{ option.label }}
                      </Select.Option>
                    </Select>
                  </div>

                  <template v-if="conversionLocation === 'APP'">
                    <div class="flex items-center gap-4">
                      <span class="w-40 text-sm font-medium text-gray-700">
                        应用:
                      </span>
                      <Popover
                        v-if="series.id === activeSeriesKey"
                        v-model:open="appComboOpen"
                        trigger="click"
                        placement="bottomLeft"
                        :overlay-style="{ width: '350px' }"
                        @open-change="handleAppComboOpenChange"
                      >
                        <template #content>
                          <div style="padding: 4px 0">
                            <div class="mb-3 flex items-center gap-2">
                              <span
                                style="
                                  flex-shrink: 0;
                                  width: 72px;
                                  font-weight: 500;
                                  color: rgba(0, 0, 0, 0.85);
                                "
                                >广告账户:</span
                              >
                              <Select
                                v-model:value="tempAdAccountId"
                                placeholder="请选择广告账户"
                                style="flex: 1"
                                allow-clear
                                @change="handleTempAccountChange"
                              >
                                <Select.Option
                                  v-for="acc in allSelectedAdAccounts"
                                  :key="acc.id"
                                  :value="acc.id"
                                >
                                  <overflow-tooltip :text="acc.name" />
                                </Select.Option>
                              </Select>
                            </div>
                            <div class="mb-3 flex items-center gap-2">
                              <span
                                style="
                                  flex-shrink: 0;
                                  width: 72px;
                                  font-weight: 500;
                                  color: rgba(0, 0, 0, 0.85);
                                "
                                >应用:</span
                              >
                              <Select
                                v-model:value="tempApplicationId"
                                placeholder="请选择应用"
                                style="flex: 1"
                                :loading="applicationOptionsLoading"
                                show-search
                                allow-clear
                                :filter-option="
                                  (input, option) =>
                                    option.label
                                      ?.toLowerCase()
                                      .includes(input.toLowerCase())
                                "
                              >
                                <Select.Option
                                  v-for="app in applicationOptions"
                                  :key="app.id"
                                  :value="app.id"
                                  :label="app.name"
                                >
                                  {{ app.name }}
                                </Select.Option>
                              </Select>
                              <Button
                                type="text"
                                :loading="applicationOptionsLoading"
                                @click.stop="handleRefreshApplications"
                              >
                                <template
                                  v-if="!applicationOptionsLoading"
                                  #icon
                                >
                                  <RotateCw class="size-4" />
                                </template>
                              </Button>
                            </div>
                            <!-- 操作按钮 -->
                            <div
                              style="
                                display: flex;
                                justify-content: flex-end;
                                gap: 8px;
                                padding-top: 10px;
                                border-top: 1px solid #f0f0f0;
                                margin-top: 4px;
                              "
                            >
                              <Button @click="appComboOpen = false"
                                >取消</Button
                              >
                              <Button
                                type="primary"
                                :disabled="!tempApplicationId"
                                @click="handleAppComboConfirm"
                              >
                                确定
                              </Button>
                            </div>
                          </div>
                        </template>
                        <!-- 触发按钮 -->
                        <Button
                          style="
                            width: 300px;
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                          "
                        >
                          <span
                            style="
                              flex: 1;
                              overflow: hidden;
                              text-overflow: ellipsis;
                              white-space: nowrap;
                              text-align: left;
                            "
                          >
                            {{ appComboDisplayText }}
                          </span>
                          <span
                            v-if="applicationId"
                            class="icon-[ant-design--close-circle-outlined] ml-1 text-gray-400 hover:text-gray-600"
                            @click.stop="handleAppComboClear"
                          ></span>
                          <span
                            v-else
                            class="icon-[ant-design--down-outlined] ml-1"
                          ></span>
                        </Button>
                      </Popover>
                    </div>
                  </template>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span> 成效目标:
                    </span>
                    <Select
                      v-if="isEngagementSeries"
                      v-model:value="performanceGoal"
                      placeholder="请选择成效目标"
                      style="width: 300px"
                    >
                      <Select.Option
                        v-for="option in engagementOptimizationGoalOptions"
                        :key="option.value"
                        :value="option.value"
                      >
                        {{ option.label }}
                      </Select.Option>
                    </Select>
                    <Select
                      v-else
                      v-model:value="performanceGoal"
                      placeholder="请选择成效目标"
                      style="width: 300px"
                    >
                      <Select.Option
                        v-for="option in optimizationGoalOptions"
                        :key="option.value"
                        :value="option.value"
                        :disabled="
                          option.value === 'VALUE' &&
                          isValueOptimizationDisabled
                        "
                      >
                        {{ option.label }}
                      </Select.Option>
                    </Select>
                  </div>

                  <div
                    v-if="shouldShowConversionEvent"
                    class="flex items-center gap-4"
                  >
                    <span class="w-40 text-sm font-medium text-gray-700">
                      <span class="text-red-500">*</span>
                      {{ conversionEventLabel }}:
                    </span>
                    <Select
                      v-model:value="conversionEvent"
                      placeholder="请选择"
                      style="width: 300px"
                    >
                      <Select.Option
                        v-for="option in currentConversionEventOptions"
                        :key="option.value"
                        :value="option.value"
                      >
                        {{ option.label }}
                      </Select.Option>
                    </Select>
                  </div>

                  <!-- <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      广告主:
                    </span>
                    <Select
                      v-model:value="adGroupAdvertiserId"
                      placeholder="请选择广告主"
                      allow-clear
                      style="width: 300px"
                    >
                      <Select.Option
                        v-for="acc in allSelectedAdAccounts"
                        :key="acc.id"
                        :value="acc.id"
                      >
                        {{ acc.name }}
                      </Select.Option>
                    </Select>
                  </div> -->

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      排期开始时间:
                    </span>
                    <DatePicker
                      v-model:value="scheduleStartTime"
                      show-time
                      format="YYYY-MM-DD HH:mm"
                      :allow-clear="true"
                      style="width: 300px"
                      placeholder="请选择开始时间"
                    />
                    <span class="text-black-500 font-bold"
                      >排期时间以账户时区为准</span
                    >
                  </div>

                  <div class="flex items-center gap-4">
                    <span class="w-40 text-sm font-medium text-gray-700">
                      排期结束时间:
                    </span>
                    <DatePicker
                      v-model:value="scheduleEndTime"
                      show-time
                      format="YYYY-MM-DD HH:mm"
                      :allow-clear="true"
                      style="width: 300px"
                      placeholder="请选择结束时间"
                    />
                    <span class="text-black-500 font-bold"
                      >排期时间以账户时区为准</span
                    >
                  </div>
                </div>

                <div class="mb-4 mt-14">
                  <h4 class="mb-4 text-base font-semibold text-gray-800">
                    创建地区组
                  </h4>
                  <Tabs
                    v-model:active-key="activeRegionGroupKey"
                    type="editable-card"
                    :hide-add="false"
                    @edit="handleRegionGroupTabEdit"
                    class="mb-4"
                  >
                    <Tabs.TabPane
                      v-for="group in series.regionGroups"
                      :key="`${series.id}-${group.id}`"
                      :closable="false"
                    >
                      <template #tab>
                        <div class="flex items-center gap-2">
                          <span>{{ group.name }}</span>
                          <Popover
                            :open="
                              !!regionGroupClone.openMap[
                                regionGroupCloneKey(index, group.id)
                              ]
                            "
                            trigger="click"
                            placement="bottom"
                            @open-change="
                              (open) =>
                                regionGroupClone.setOpen(
                                  regionGroupCloneKey(index, group.id),
                                  open,
                                )
                            "
                          >
                            <template #content>
                              <div class="w-[220px] space-y-2 p-2">
                                <div
                                  class="flex items-center justify-between gap-2"
                                >
                                  <span class="text-sm text-gray-700"
                                    >克隆数量</span
                                  >
                                  <InputNumber
                                    :min="CLONE_MIN"
                                    :value="
                                      regionGroupClone.getCount(
                                        regionGroupCloneKey(index, group.id),
                                      )
                                    "
                                    style="width: 120px"
                                    @change="
                                      (val) =>
                                        regionGroupClone.setCount(
                                          regionGroupCloneKey(index, group.id),
                                          Number(val ?? 1),
                                        )
                                    "
                                  />
                                </div>
                                <div
                                  class="flex items-center justify-end gap-2"
                                >
                                  <Button
                                    @click="
                                      regionGroupClone.setOpen(
                                        regionGroupCloneKey(index, group.id),
                                        false,
                                      )
                                    "
                                    >取消</Button
                                  >
                                  <Button
                                    type="primary"
                                    @click="
                                      () => {
                                        const key = regionGroupCloneKey(
                                          index,
                                          group.id,
                                        );
                                        cloneRegionGroup(
                                          index,
                                          group.id,
                                          regionGroupClone.getCount(key),
                                        );
                                        regionGroupClone.setOpen(key, false);
                                      }
                                    "
                                    >确定</Button
                                  >
                                </div>
                              </div>
                            </template>
                            <span
                              class="cursor-pointer text-[12px] text-blue-500"
                            >
                              克隆
                            </span>
                          </Popover>
                          <Button
                            type="link"
                            class="p-0 text-[12px]"
                            danger
                            @click="
                              deleteRegionGroup(currentSeriesIndex, group.id)
                            "
                          >
                            删除
                          </Button>
                        </div>
                      </template>
                      <Card class="card-border-none">
                        <div class="space-y-4">
                          <div class="flex items-center gap-3">
                            <span class="text-sm text-gray-600"
                              >进阶赋能型受众:</span
                            >
                            <Switch v-model:checked="group.isNewModelEnabled" />
                          </div>

                          <div class="flex items-center gap-4">
                            <span
                              class="w-40 text-sm font-medium text-gray-700"
                            >
                              <span class="text-red-500">*</span> 地区:
                            </span>
                            <Select
                              v-model:value="group.country"
                              style="width: 200px"
                              show-search
                              :placeholder="
                                getGroupCountries(series).length
                                  ? '请选择'
                                  : '请先选择系列的国家选项'
                              "
                              :disabled="!getGroupCountries(series).length"
                              :filter-option="filterSelectOption"
                            >
                              <Select.Option
                                v-for="country in getGroupCountries(series)"
                                :key="country.code"
                                :value="country.code"
                                :label="country.name"
                              >
                                {{ country.name }}
                              </Select.Option>
                            </Select>
                          </div>

                          <div class="flex items-center gap-4">
                            <span
                              class="w-40 text-sm font-medium text-gray-700"
                            >
                              发布平台:
                            </span>
                            <Select
                              v-model:value="group.publisher_platforms"
                              mode="multiple"
                              placeholder="默认全部平台"
                              style="width: 350px"
                              allow-clear
                              :max-tag-count="2"
                            >
                              <Select.Option
                                v-for="opt in publisherPlatformOptions"
                                :key="opt.value"
                                :value="opt.value"
                              >
                                {{ opt.label }}
                              </Select.Option>
                            </Select>
                          </div>

                          <div class="flex items-center gap-4">
                            <span
                              class="w-40 text-sm font-medium text-gray-700"
                            >
                              <span class="text-red-500">*</span> 年龄下限:
                            </span>
                            <Select
                              v-model:value="group.ageRangeStart"
                              style="width: 200px"
                              :disabled="
                                !!series.seriesSettings.specialAdCategories
                                  ?.length
                              "
                              @change="handleAgeRangeStartChange(group)"
                            >
                              <Select.Option
                                v-for="age in Array.from(
                                  { length: 8 },
                                  (_, i) => 18 + i,
                                )"
                                :key="age"
                                :value="age"
                              >
                                {{ age }}
                              </Select.Option>
                            </Select>
                          </div>

                          <div class="flex items-center gap-4">
                            <span
                              class="w-40 text-sm font-medium text-gray-700"
                            >
                              <span class="text-red-500">*</span> 年龄:
                            </span>
                            <Select
                              v-model:value="group.ageStart"
                              style="width: 150px"
                              :disabled="
                                !!series.seriesSettings.specialAdCategories
                                  ?.length
                              "
                              @change="handleAgeStartChange(group)"
                            >
                              <Select.Option
                                v-for="age in buildAges(group.ageRangeStart)"
                                :key="`age-start-${age}`"
                                :value="age === 65 ? 65 : age"
                              >
                                {{ age }}
                              </Select.Option>
                            </Select>
                            <span class="mx-2 text-gray-500">—</span>
                            <Select
                              v-model:value="group.ageRangeEnd"
                              style="width: 150px"
                              :disabled="
                                !!series.seriesSettings.specialAdCategories
                                  ?.length
                              "
                            >
                              <Select.Option
                                v-for="age in buildAges(group.ageStart)"
                                :key="`age-end-${age}`"
                                :value="age === 65 ? 65 : age"
                              >
                                {{ age === 65 ? '65+' : age }}
                              </Select.Option>
                            </Select>
                          </div>

                          <div class="flex items-center gap-4">
                            <span
                              class="w-40 text-sm font-medium text-gray-700"
                            >
                              <span class="text-red-500">*</span> 性别:
                            </span>
                            <Select
                              v-model:value="group.gender"
                              style="width: 200px"
                            >
                              <Select.Option value="不限">不限</Select.Option>
                              <Select.Option value="男">男</Select.Option>
                              <Select.Option value="女">女</Select.Option>
                            </Select>
                          </div>

                          <div class="flex items-center gap-3">
                            <span class="text-sm text-gray-600">动态素材:</span>
                            <Switch v-model:checked="group.isDynamicCreative" />
                          </div>

                          <div class="flex items-center gap-4">
                            <span class="w-40 text-sm font-medium text-gray-700"
                              >&nbsp;&nbsp;语言:</span
                            >
                            <Select
                              v-model:value="group.language"
                              style="width: 400px"
                              mode="multiple"
                              show-search
                              allow-clear
                              :max-tag-count="2"
                              placeholder="请选择"
                              :filter-option="filterSelectOption"
                            >
                              <Select.Option
                                v-for="locale in localesData"
                                :key="locale.key"
                                :value="String(locale.key)"
                                :label="locale.name"
                              >
                                {{ locale.name }}
                              </Select.Option>
                            </Select>
                          </div>

                          <!-- 设备和操作系统面板组件 -->
                          <DeviceOsPanel
                            :model-value="group"
                            @update:model-value="
                              (val) => Object.assign(group, val)
                            "
                          />
                        </div>
                      </Card>
                    </Tabs.TabPane>
                  </Tabs>
                </div>
              </Card>
            </Tabs.TabPane>
          </Tabs>
        </div>

        <div v-show="currentStep === 2" class="h-full space-y-4">
          <div class="rounded-md bg-white p-3">
            <div class="flex items-center gap-2 text-sm">
              <div class="flex flex-shrink-0 items-center gap-2">
                <span class="text-gray-700">广告账户:</span>
                <span class="font-semibold">{{ totalAdvertisers }}</span>
                <span class="text-gray-700">个；</span>
              </div>
              <div class="flex flex-shrink-0 items-center gap-2">
                <span class="text-gray-700">广告系列:</span>
                <span class="font-semibold">{{ totalCreated }}</span>
                <span class="text-gray-700">个；</span>
              </div>
              <div class="flex flex-shrink-0 items-center gap-2">
                <span class="text-gray-700">广告组:</span>
                <span class="font-semibold">{{ totalAdGroups }}</span>
                <span class="text-gray-700">个；</span>
              </div>
              <div class="flex flex-shrink-0 items-center gap-2">
                <span class="text-gray-700">每个广告组</span>
                <Input
                  v-model:value="adsPerGroup"
                  class="w-[50px] text-center"
                  type="number"
                  :min="1"
                />
                <span class="text-gray-700">个广告；</span>
              </div>
              <div class="flex flex-shrink-0 items-center gap-2">
                <span class="text-gray-700">需要上传广告数量:</span>
                <span class="font-semibold">{{ totalMaterials }}</span>
              </div>
            </div>
            <div class="content mt-3 flex items-center gap-2">
              <span class="text-sm text-gray-700">广告模板:</span>
              <Button
                type="primary"
                class="rounded-md"
                :disabled="creatingAd"
                @click="showMaterialTemplateModal = true"
              >
                {{
                  appliedMaterialTemplateId
                    ? '更新正文标题模板'
                    : '保存正文标题模板'
                }}
              </Button>
              <MaterialTemplateLoadTab
                ref="materialTemplateLoadTabRef"
                :user-options="operatorOptions"
                @apply="handleMaterialTemplateApply"
                @open="loadOperatorOptions"
              />
            </div>
            <div class="mt-[12px] flex flex-wrap gap-2">
              <span class="text-gray-700">广告正文:</span>
              <Textarea
                v-model:value="batchDescription"
                :auto-size="{ minRows: 1, maxRows: 4 }"
                placeholder="请输入正文"
                style="width: 260px"
              />
              <span class="ml-2 text-gray-700">广告标题:</span>
              <Textarea
                v-model:value="batchTitle"
                :auto-size="{ minRows: 1, maxRows: 4 }"
                placeholder="请输入标题"
                style="width: 260px"
              />
              <span class="ml-2 text-gray-700">行动号召:</span>
              <Select
                v-model:value="batchCallToAction"
                placeholder="请选择行动号召"
                allow-clear
                style="align-self: flex-start; width: 200px"
              >
                <Select.Option
                  v-for="option in isEngagementSeries
                    ? engagementCallToActionOptions
                    : allCallToActionOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </Select.Option>
              </Select>
              <ChatToolTemplatePopover
                class="ml-2 self-start"
                @apply="selectBatchChatToolTemplate"
                @new="showChatToolModal = true"
              >
                <div class="flex">
                  聊天模板：
                  <Button class="flex items-center gap-2 rounded-md">
                    <span>{{ batchChatToolTemplateName || '请选择' }}</span>
                  </Button>
                </div>
              </ChatToolTemplatePopover>
              <Button
                type="primary"
                class="ml-2 flex items-center gap-2 rounded-md"
                @click="applyBatchTitleAndDescription"
              >
                批量应用{{
                  selectedMaterials.length > 0
                    ? `(${selectedMaterials.length})`
                    : ''
                }}
              </Button>
            </div>
          </div>

          <Card
            class="rounded-md"
            :head-style="{ border: 'none' }"
            :body-style="{ paddingTop: '0' }"
          >
            <template #title>
              <span>广告结构</span>
            </template>
            <Tabs
              v-model:active-key="activeMaterialGroupKey"
              type="editable-card"
              :hide-add="false"
              @edit="
                (_, action) => {
                  if (action === 'add') addMaterialGroup();
                }
              "
              :tab-bar-style="{ marginBottom: 0 }"
            >
              <Tabs.TabPane
                v-for="group in materialGroups"
                :key="group.id"
                :closable="false"
              >
                <template #tab>
                  <div class="flex items-center gap-2">
                    <span>{{ group.name }}</span>
                    <Popover
                      :open="!!materialGroupClone.openMap[group.id]"
                      trigger="click"
                      placement="bottom"
                      @open-change="
                        (open) => materialGroupClone.setOpen(group.id, open)
                      "
                    >
                      <template #content>
                        <div class="w-[220px] space-y-2 p-2">
                          <div class="flex items-center justify-between gap-2">
                            <span class="text-sm text-gray-700">克隆数量</span>
                            <InputNumber
                              :min="CLONE_MIN"
                              :value="materialGroupClone.getCount(group.id)"
                              style="width: 120px"
                              @change="
                                (val) =>
                                  materialGroupClone.setCount(
                                    group.id,
                                    Number(val ?? 1),
                                  )
                              "
                            />
                          </div>
                          <div class="flex items-center justify-end gap-2">
                            <Button
                              @click="
                                materialGroupClone.setOpen(group.id, false)
                              "
                              >取消</Button
                            >
                            <Button
                              type="primary"
                              @click="confirmCloneMaterialGroup(group.id)"
                              >确定</Button
                            >
                          </div>
                        </div>
                      </template>
                      <span class="cursor-pointer text-[12px] text-blue-500"
                        >克隆</span
                      >
                    </Popover>
                    <Button
                      type="link"
                      class="p-0 text-[12px]"
                      danger
                      @click.stop="deleteMaterialGroup(group.id)"
                      >删除</Button
                    >
                  </div>
                </template>

                <div
                  class="mb-3 flex flex-wrap items-center gap-3 border-b py-3"
                >
                  <span class="text-sm text-gray-700">绑定方式：</span>
                  <Radio.Group v-model:value="group.binding.type">
                    <Radio value="random">随机分配</Radio>
                    <Tooltip
                      title="标签互相包含(含相同)的素材不会分进同一广告组"
                    >
                      <Radio value="tag">按标签分组</Radio>
                    </Tooltip>
                    <Radio value="account">广告账户</Radio>
                    <Radio value="regionGroup">地区组</Radio>
                  </Radio.Group>
                  <Select
                    v-if="group.binding.type === 'account'"
                    v-model:value="group.binding.accountId"
                    :options="advertiserOptions"
                    placeholder="请选择广告账户"
                    style="width: 260px"
                    allow-clear
                  />
                  <Cascader
                    v-if="group.binding.type === 'regionGroup'"
                    v-model:value="group.binding.regionGroupPath"
                    :options="regionGroupCascaderOptions"
                    placeholder="请选择系列 / 地区组"
                    style="width: 300px"
                  />
                </div>

                <div class="mb-4 flex items-center justify-between">
                  <div class="flex items-center gap-3">
                    <Button
                      type="primary"
                      class="flex items-center gap-2 rounded-md"
                      @click="showMaterialModal = true"
                    >
                      添加广告
                    </Button>
                    <Button
                      type="primary"
                      class="flex items-center gap-2 rounded-md"
                      @click="showAdCreativeModal = true"
                    >
                      临时广告
                    </Button>
                    <Button
                      type="primary"
                      class="flex items-center gap-2 rounded-md"
                      @click="openOriginalPostModal"
                    >
                      添加原帖
                    </Button>
                    <Button
                      :type="
                        selectedMaterials.length > 0 ? 'primary' : 'default'
                      "
                      class="flex items-center gap-2 rounded-md"
                      @click="deleteSelectedMaterials"
                      :disabled="selectedMaterials.length === 0"
                    >
                      <span
                        :class="
                          selectedMaterials.length > 0
                            ? 'icon-[ant-design--delete-filled] text-white'
                            : 'icon-[ant-design--delete-outlined]'
                        "
                      ></span>
                      删除{{
                        selectedMaterials.length > 0
                          ? `(${selectedMaterials.length})`
                          : ''
                      }}
                    </Button>
                    <Button
                      type="primary"
                      class="flex items-center gap-2 rounded-md"
                      @click="showMaterialGroupSaveModal = true"
                      :disabled="creatingAd || uploadedMaterials.length === 0"
                    >
                      <span
                        class="icon-[ant-design--save-outlined] text-white"
                      ></span>
                      保存素材组
                    </Button>
                    <MaterialGroupLoadTab
                      ref="materialGroupLoadTabRef"
                      :has-current-materials="uploadedMaterials.length > 0"
                      @apply="handleMaterialGroupApply"
                      @history="showMaterialGroupHistoryModal = true"
                    />
                    <Tooltip title="查看并复用创意历史配置">
                      <Button
                        type="primary"
                        class="flex items-center gap-2 rounded-md"
                        @click="showCreativeHistoryModal = true"
                      >
                        <span
                          class="icon-[ant-design--history-outlined] text-white"
                        ></span>
                        创意历史
                      </Button>
                    </Tooltip>
                  </div>
                  <div class="flex items-center gap-1">
                    <span class="mr-6 text-sm text-gray-600">
                      已选择 {{ allMaterials.length }} 条广告
                    </span>
                    <Button.Group>
                      <Button
                        @click="selectAllMaterials"
                        :disabled="uploadedMaterials.length === 0"
                        >全选</Button
                      >
                      <Button
                        @click="invertMaterialSelection"
                        :disabled="uploadedMaterials.length === 0"
                        >反选</Button
                      >
                      <Button
                        @click="clearMaterialSelection"
                        :disabled="selectedMaterials.length === 0"
                        >清空 ({{ selectedMaterials.length }})</Button
                      >
                    </Button.Group>
                  </div>
                </div>

                <div
                  v-if="group.materials.length === 0"
                  class="border-border bg-muted/40 flex min-h-[var(--adpulse-table-viewport-height)] items-center justify-center rounded-lg border border-dashed"
                >
                  <div class="text-center text-gray-400">
                    <IconifyIcon
                      aria-hidden="true"
                      class="mx-auto mb-2 text-3xl"
                      icon="lucide:package-open"
                    />
                    <div>暂无广告，请点击"添加广告"按钮上传</div>
                  </div>
                </div>

                <div
                  v-else
                  ref="materialsContainer"
                  class="relative flex flex-wrap gap-4 overflow-y-auto p-[2px]"
                  :class="{
                    'cursor-crosshair select-none': !isPreviewMode,
                  }"
                  @mousedown="startSelection"
                >
                  <!-- 框选矩形 -->
                  <div
                    v-if="isSelecting"
                    class="pointer-events-none absolute z-50 border-2 border-blue-500 bg-blue-500/20"
                    :style="{
                      left: `${Math.min(selectionBox.startX, selectionBox.endX)}px`,
                      top: `${Math.min(selectionBox.startY, selectionBox.endY)}px`,
                      width: `${Math.abs(selectionBox.endX - selectionBox.startX)}px`,
                      height: `${Math.abs(selectionBox.endY - selectionBox.startY)}px`,
                    }"
                  ></div>

                  <div
                    v-for="material in group.materials"
                    :key="material.id"
                    :data-card-id="material.id"
                    class="group relative flex w-[175px] flex-col items-center border border-gray-200 bg-white py-2.5 transition-all"
                    :class="{
                      'ring-2 ring-blue-500': selectedMaterials.includes(
                        material.id,
                      ),
                      'max-h-[155px]': material.isOriginalPost,
                    }"
                  >
                    <div
                      v-if="
                        !isPreviewMode ||
                        showMaterialCheckboxes ||
                        showBatchApplyCheckboxes
                      "
                      class="absolute left-1.5 top-1.5 z-10 cursor-pointer"
                    >
                      <Checkbox
                        :checked="
                          showMaterialCheckboxes
                            ? selectedMaterials.includes(material.id)
                            : showBatchApplyCheckboxes
                              ? batchApplySelectedMaterials.includes(
                                  material.id,
                                )
                              : selectedMaterials.includes(material.id)
                        "
                        @change="
                          (e) =>
                            showMaterialCheckboxes
                              ? toggleMaterialSelection(
                                  material.id,
                                  e.target.checked,
                                )
                              : showBatchApplyCheckboxes
                                ? toggleBatchApplySelection(
                                    material.id,
                                    e.target.checked,
                                  )
                                : toggleMaterialSelection(
                                    material.id,
                                    e.target.checked,
                                  )
                        "
                        @click.stop
                      />
                    </div>
                    <div
                      v-if="material.isOriginalPost"
                      class="absolute right-[-8px] top-0 z-10"
                    >
                      <Tag color="blue">原帖</Tag>
                    </div>
                    <div
                      class="mx-auto flex aspect-square h-[112px] w-[112px] items-center justify-center bg-gray-200"
                    >
                      <img
                        v-if="material.img || material.thumbnail"
                        :src="`data:image/jpeg;base64,${material.img || material.thumbnail}`"
                        :alt="material.name"
                        class="h-full rounded-[4px] object-cover"
                      />
                      <div
                        v-else
                        class="flex h-full w-full items-center justify-center text-gray-400"
                      >
                        <IconifyIcon
                          aria-hidden="true"
                          class="text-3xl"
                          :icon="
                            material.filetype === 'video'
                              ? 'lucide:video'
                              : 'lucide:image'
                          "
                        />
                      </div>
                    </div>
                    <div
                      class="w-full truncate px-1 py-1.5 text-center text-sm text-gray-700"
                      :title="
                        material.isOriginalPost
                          ? material.pageId
                          : material.name || material.materialId
                      "
                    >
                      {{
                        material.isOriginalPost
                          ? material.materialId
                          : material.name || material.materialId
                      }}
                    </div>
                    <template v-if="!material.isOriginalPost">
                      <div>
                        <Textarea
                          type="text"
                          class="py-[1px] text-[14px]"
                          :auto-size="{ minRows: 1, maxRows: 4 }"
                          v-model:value="material.description"
                          placeholder="请输入广告正文"
                        />
                      </div>
                      <div class="mt-[8px]">
                        <Textarea
                          type="text"
                          class="py-[1px] text-[14px]"
                          :auto-size="{ minRows: 1, maxRows: 4 }"
                          v-model:value="material.title"
                          placeholder="请输入广告标题"
                          @change="checkTitleBytes(material.title || '')"
                        />
                      </div>
                      <div class="mt-[8px]">
                        <Select
                          v-model:value="material.callToAction"
                          placeholder="请选择行动号召"
                          allow-clear
                          class="py-[1px]"
                          style="width: 147px"
                        >
                          <Select.Option
                            v-for="option in getCallToActionOptions(
                              material.filetype,
                              isEngagementSeries,
                            )"
                            :key="option.value"
                            :value="option.value"
                          >
                            {{ option.label }}
                          </Select.Option>
                        </Select>
                      </div>
                      <div class="mt-[8px]">
                        <AdEnhancementPopover
                          :material="material"
                          @new-chat-tool="showChatToolModal = true"
                        />
                      </div>
                    </template>
                  </div>
                </div>
              </Tabs.TabPane>
            </Tabs>
          </Card>
        </div>
      </div>
    </div>

    <!-- Modals -->
    <PersonalAuthAdvertiserModal
      :open="showAdvertiserModal"
      :task-data="
        currentTaskIndex >= 0 ? selectedTasksData[currentTaskIndex] : undefined
      "
      @update:open="
        (v) => {
          if (!v) showAdvertiserModal = false;
        }
      "
      @confirm="handleAdvertiserConfirm"
    />
    <TemplateSaveModal
      v-model:open="showTemplateModal"
      :title="appliedTemplateId ? '更新模板' : '保存模板'"
      :initial-name="appliedTemplateId ? appliedTemplateName : ''"
      :initial-description="appliedTemplateId ? appliedTemplateDescription : ''"
      @confirm="handleTemplateSave"
    />
    <TemplateSaveModal
      v-model:open="showMaterialTemplateModal"
      :title="appliedMaterialTemplateId ? '更新素材模板' : '保存素材模板'"
      :initial-name="
        appliedMaterialTemplateId ? appliedMaterialTemplateName : ''
      "
      :initial-description="
        appliedMaterialTemplateId ? appliedMaterialTemplateDescription : ''
      "
      @confirm="handleMaterialTemplateSave"
    />
    <ChatToolModal
      v-model="showChatToolModal"
      @confirm="handleChatToolConfirm"
    />
    <MaterialSelectionModal
      v-model:open="showMaterialModal"
      :operator-options="operatorOptions"
      :uploaded-material-ids="uploadedMaterials.map((m) => m.id)"
      @confirm="handleMaterialConfirm"
    />

    <!-- 素材组管理弹窗 -->
    <MaterialGroupSaveModal
      :visible="showMaterialGroupSaveModal"
      :materials-count="uploadedMaterials.length"
      :current-group-id="currentMaterialGroupId"
      :current-group-name="currentMaterialGroupName"
      :current-group-description="currentMaterialGroupDescription"
      @confirm="handleSaveMaterialGroup"
      @cancel="showMaterialGroupSaveModal = false"
    />
    <MaterialGroupHistoryModal
      ref="materialGroupHistoryModalRef"
      :visible="showMaterialGroupHistoryModal"
      :has-current-materials="uploadedMaterials.length > 0"
      @reapply="handleReapplyHistory"
      @update:visible="showMaterialGroupHistoryModal = $event"
    />
    <CreativeHistoryModal
      ref="creativeHistoryModalRef"
      :visible="showCreativeHistoryModal"
      :has-current-materials="uploadedMaterials.length > 0"
      @reuse="handleReuseCreativeHistory"
      @update:visible="showCreativeHistoryModal = $event"
    />
    <AdCreativeSelectionModal
      :open="showAdCreativeModal"
      :selected-ids="uploadedMaterials.map((m) => m.id)"
      @update:open="(val) => (showAdCreativeModal = val)"
      @confirm="handleAdCreativeConfirm"
    />

    <QueryProgressModal v-model:open="showProgressModal" />
    <OriginalPostModal
      v-model:open="showOriginalPostModal"
      :page-ids="selectedPageIds"
      :selected-post-ids="selectedOriginalPostIds"
      @confirm="handleOriginalPostConfirm"
    />

    <Modal
      v-model:open="showConfirmModal"
      title="确认创建广告"
      width="1000px"
      :mask-closable="true"
      ok-text="确认创建"
      :cancel-button-props="{ style: { display: 'none' } }"
      :confirm-loading="creatingAd"
      :ok-button-props="{ disabled: creatingAd || adCreatingCooldown }"
      @ok="doCreateAdvertisement"
    >
      <div class="max-h-[72vh] space-y-4 overflow-y-auto pr-1">
        <!-- 已选任务线（任务线 → 链接 → 账户） -->
        <div>
          <div class="mb-2 flex items-center gap-2">
            <span class="text-sm font-semibold text-gray-800">已选任务线</span>
            <Tag color="blue">{{ confirmTaskList.length }} 条任务线</Tag>
            <Tag color="geekblue">{{ confirmAccountCount }} 个账户</Tag>
          </div>
          <div class="space-y-4">
            <div
              v-for="(task, tIdx) in confirmTaskList"
              :key="`${task.taskName}_${tIdx}`"
              class="overflow-hidden rounded-lg border-2 border-gray-300 shadow-sm"
            >
              <!-- 任务线 -->
              <div
                class="flex flex-nowrap items-center gap-x-3 border-b border-gray-200 bg-blue-50 px-3 py-2"
              >
                <span class="flex-shrink-0 text-sm font-bold text-gray-900">
                  {{ task.taskName || '—' }}
                </span>
                <span
                  v-if="task.projectName"
                  class="flex-shrink-0 text-xs text-gray-500"
                >
                  {{ task.projectName }}
                </span>
                <Tag v-if="task.regionName" color="blue" class="flex-shrink-0">
                  {{ task.regionName }}
                </Tag>
                <a
                  v-if="task.url"
                  :href="task.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="min-w-0 truncate text-sm text-blue-600 hover:underline"
                  :title="task.url"
                >
                  {{ task.url }}
                </a>
              </div>
              <!-- 账户（列对齐表格） -->
              <div class="px-3 py-2">
                <table
                  v-if="task.accounts.length"
                  class="w-full table-fixed text-sm"
                >
                  <thead>
                    <tr class="text-xs text-gray-400">
                      <th class="w-[28%] py-1 pr-4 text-left font-normal">
                        账户
                      </th>
                      <th class="w-[24%] py-1 pr-4 text-left font-normal">
                        个号
                      </th>
                      <th class="w-[24%] py-1 pr-4 text-left font-normal">
                        主页
                      </th>
                      <th class="w-[24%] py-1 text-left font-normal">像素</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(acc, aIdx) in task.accounts"
                      :key="`${acc.accountId}_${aIdx}`"
                      class="border-t border-gray-100"
                    >
                      <td class="py-1 pr-4 align-top">
                        <div class="font-medium leading-tight text-gray-800">
                          {{ acc.account }}
                        </div>
                        <div class="text-xs leading-tight text-gray-400">
                          {{ acc.accountId }}
                        </div>
                      </td>
                      <td
                        class="truncate py-1 pr-4 align-top text-gray-700"
                        :title="acc.person || ''"
                      >
                        {{ acc.person || '—' }}
                      </td>
                      <td
                        class="truncate py-1 pr-4 align-top text-gray-700"
                        :title="acc.page || ''"
                      >
                        {{ acc.page || '—' }}
                      </td>
                      <td
                        class="truncate py-1 align-top text-gray-700"
                        :title="acc.pixel || ''"
                      >
                        {{ acc.pixel || '—' }}
                      </td>
                    </tr>
                  </tbody>
                </table>
                <span v-else class="text-xs text-gray-400">未配置账户</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 广告系列结构 + 预算 -->
        <div>
          <div class="mb-2 flex items-center gap-2">
            <span class="text-sm font-semibold text-gray-800"
              >广告系列结构</span
            >
            <Tag color="blue">{{ totalCreated }} 个系列</Tag>
            <Tag color="geekblue">{{ totalAdGroups }} 个广告组</Tag>
          </div>
          <Table
            :columns="confirmSeriesColumns"
            :data-source="confirmSeriesSummary"
            :pagination="false"
            row-key="id"
            bordered
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'groups'">
                <div class="flex flex-col">
                  <span class="font-medium">{{ record.groupCount }} 个</span>
                  <span class="text-xs text-gray-400">
                    {{ record.groupNames }}
                  </span>
                </div>
              </template>
              <template v-else-if="column.key === 'campaignBudget'">
                <span v-if="record.campaignBudget" class="font-medium">
                  {{ record.campaignBudget }}
                </span>
                <span v-else class="text-xs text-gray-400">—</span>
              </template>
              <template v-else-if="column.key === 'adsetBudget'">
                <span v-if="record.adsetBudget" class="font-medium">
                  {{ record.adsetBudget }}
                </span>
                <span v-else class="text-xs text-gray-400">—</span>
              </template>
            </template>
          </Table>
        </div>

        <!-- 上传素材数量 -->
        <div>
          <div class="mb-2 text-sm font-semibold text-gray-800">上传素材</div>
          <div
            class="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-md bg-gray-50 px-3 py-2 text-sm text-gray-700"
          >
            <span
              >每个广告组 <b>{{ adsPerGroup }}</b> 个广告</span
            >
            <span>
              需要上传广告数量
              <b class="text-blue-600">{{ totalMaterials }}</b>
            </span>
          </div>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style lang="scss" scoped>
.ad-builder-layout,
.ad-builder-content {
  max-width: 100%;
}

.ad-builder-content > div {
  min-width: 0;
  max-width: 100%;
}

@media (max-width: 1023px) {
  .ad-builder-layout {
    height: auto;
    min-height: 100%;
    flex-direction: column;
    align-items: stretch;
    justify-content: flex-start;
    gap: 12px;
    padding: 16px;
    overflow: visible;
  }

  .ad-builder-steps {
    width: 100%;
    padding: 14px 16px;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    background: #fff;
  }

  .builder-step-actions,
  .builder-step-actions > div,
  .builder-step-actions > div > div {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
  }

  .ad-builder-content {
    width: 100%;
    height: auto;
    overflow-x: hidden;
    overflow-y: visible;
  }

  .builder-mode-row,
  .builder-task-row,
  .builder-batch-actions {
    flex-wrap: wrap;
  }

  .builder-task-row > .invisible {
    display: none;
  }

  .builder-cascader-container {
    width: min(100%, 420px);
  }

  .builder-cascader {
    width: 100% !important;
  }

  .builder-batch-actions {
    width: 100%;
    margin-left: 0;
  }
}

@media (max-width: 639px) {
  .ad-builder-layout {
    padding: 12px;
  }

  .ad-builder-steps {
    padding: 12px;
    overflow-x: auto;
  }

  .builder-step-actions {
    min-width: 410px;
    justify-content: flex-start;
  }
}

.select-option-text {
  display: inline-block;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  white-space: nowrap;
}

.card-border-none {
  border: none;
}

:deep(.progress-row-clickable) {
  cursor: pointer;
}

:deep(.progress-row-clickable:hover > td) {
  background-color: hsl(var(--accent)) !important;
}

:deep(.progress-row-selected > td) {
  background-color: hsl(var(--muted)) !important;
}

:deep(.progress-ad-row-failed) {
  background-color: #fff1f0 !important;
}

:deep(.progress-ad-row-failed:hover > td) {
  background-color: #ffe4e2 !important;
}

:deep(.progress-ad-row-success) {
  background-color: #f6ffed !important;
}

:deep(.progress-ad-row-success:hover > td) {
  background-color: #edfae0 !important;
}

/* Tabs 横向滚动 */
</style>
