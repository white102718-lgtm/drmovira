<script lang="ts" setup>
import type { UploadFile, UploadProps } from 'ant-design-vue';

import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Checkbox,
  Divider,
  Empty,
  Form,
  FormItem,
  Input,
  InputNumber,
  Modal,
  Progress,
  Radio,
  Select,
  Space,
  Switch,
  Tag,
  Upload,
  message,
} from 'ant-design-vue';

import {
  getAiCapabilitiesApi,
  type AiCapability,
  type AiCapabilityCode,
  type AsyncTask,
} from '#/api';
import {
  useGlobalTaskStore,
  useProjectContextStore,
  useWorkflowStore,
} from '#/store';

interface WorkbenchGroup {
  codes: AiCapabilityCode[];
  description: string;
  eyebrow: string;
  icon: string;
  title: string;
  workflow: string[];
}

const groupMap: Record<string, WorkbenchGroup> = {
  '/fusion/ai-studio': {
    codes: [
      'image-generate',
      'video-generate',
      'copy-script',
      'image-edit',
      'video-edit',
      'material-replicate',
      'tts-generate',
    ],
    description:
      '从产品知识、提示词或现有素材快速发起创意任务，并把有效结果直接沉淀为可投素材版本。',
    eyebrow: 'AI CREATIVE STUDIO',
    icon: 'lucide:wand-sparkles',
    title: 'AI 创意工作台',
    workflow: ['选择能力', '输入与配置', '异步生成', '预览入库'],
  },
  '/fusion/audio-avatar': {
    codes: ['music-generate', 'tts-generate', 'tts-preview', 'lip-sync'],
    description: '完成背景音乐、配音预览、多语言 TTS 和人物口播视频生产。',
    eyebrow: 'AUDIO & AVATAR',
    icon: 'lucide:audio-lines',
    title: '音频与口播',
    workflow: ['脚本与人物', '音色和音乐', '生成与试听', '口播合成'],
  },
  '/fusion/creative-batch': {
    codes: [
      'creative-batch',
      'video-mashup',
      'video-fission',
      'new-creative',
      'copy-script',
    ],
    description:
      '并行编排混剪、裂变、新创意和脚本产出，统一跟踪子任务与有效结果。',
    eyebrow: 'CREATIVE ORCHESTRATION',
    icon: 'lucide:layers-3',
    title: '创意批量生产',
    workflow: ['输入与策略', '生产线编排', '批量执行', '验收与入库'],
  },
  '/fusion/creative-intelligence': {
    codes: [
      'ad-crawler',
      'fb-ad-scraper',
      'material-tagging',
      'video-analyze',
      'news-trends',
    ],
    description:
      '聚合热点趋势与竞品创意，分析素材结构并直接转为可执行的创意输入。',
    eyebrow: 'TRENDING CREATIVE',
    icon: 'lucide:flame',
    title: '热点创意',
    workflow: ['发现热点', '采集与解析', '分析和打标', '保存创意机会'],
  },
  '/fusion/image-creation': {
    codes: [
      'image-generate',
      'image-edit',
      'image-inpaint',
      'batch-image',
      'batch-image-edit',
    ],
    description:
      '从零生成、参考图编辑、局部重绘并批量生产多语言、多尺寸图片变体。',
    eyebrow: 'IMAGE PRODUCTION',
    icon: 'lucide:image',
    title: '图片创作',
    workflow: ['产品知识', '提示词和参考图', '生成与编辑', '审核并入库'],
  },
  '/fusion/video-creation': {
    codes: [
      'video-generate',
      'seedance',
      'video-extend',
      'video-edit',
      'lip-sync',
    ],
    description: '从提示词、首帧或参考视频生成、延长和编辑广告视频。',
    eyebrow: 'VIDEO GENERATION',
    icon: 'lucide:clapperboard',
    title: '视频创作',
    workflow: ['脚本或参考素材', '模型和参数', '异步生成', '转码并入库'],
  },
  '/fusion/video-toolbox': {
    codes: [
      'video-concat',
      'batch-image-edit',
      'video-split',
      'video-replicate',
      'video-mashup',
      'auto-edit',
      'video-fission',
      'creative-batch',
      'new-creative',
      'seedance',
    ],
    description:
      '直接使用拼接、切割、复刻、混剪、自动剪辑和裂变等媒体处理工具。',
    eyebrow: 'MEDIA TOOLBOX',
    icon: 'lucide:wrench',
    title: '视频工具箱',
    workflow: ['选择素材', '配置处理规则', 'Worker 执行', '预览并保存'],
  },
};

const route = useRoute();
const router = useRouter();
const projectStore = useProjectContextStore();
const taskStore = useGlobalTaskStore();
const workflowStore = useWorkflowStore();
const capabilities = ref<AiCapability[]>([]);
const activeCode = ref<AiCapabilityCode>('image-generate');
const loading = ref(false);
const submitting = ref(false);
const fileList = ref<UploadFile[]>([]);
const completedPreview = ref(false);
const activeRun = ref<AsyncTask>();
const previewIndex = ref(1);
const previewOpen = ref(false);

const formState = reactive({
  aspectRatio: '9:16',
  beatSync: true,
  bpm: 110,
  cameraMotion: 'auto',
  complianceArchive: true,
  count: 6,
  creativity: 65,
  duration: 15,
  editMode: 'unified',
  includeCaptions: true,
  keepBrand: true,
  language: '简体中文',
  maskFeather: 12,
  materialSaveMode: 'new-version',
  maxResults: 50,
  model: 'auto',
  mood: 'energetic',
  normalizeAudio: true,
  pitch: 0,
  preserveSubject: true,
  prompt: '',
  quality: 'standard',
  region: 'global',
  resolution: '1080p',
  sceneSensitivity: 70,
  speed: 1,
  sourceUrl: '',
  splitMode: 'scene',
  targetPlatforms: ['facebook', 'tiktok'],
  transition: 'cut',
  variantStrategies: ['hook', 'cta'],
  voice: 'Nova',
});

const currentGroup = computed(
  () =>
    groupMap[route.path] ?? {
      codes: [],
      description: '统一使用 AI 创意能力。',
      eyebrow: 'AI WORKBENCH',
      icon: 'lucide:wand-sparkles',
      title: 'AI 创意工作台',
      workflow: ['输入', '配置', '执行', '保存'],
    },
);

const groupCapabilities = computed(
  () =>
    currentGroup.value.codes
      .map((code) => capabilities.value.find((item) => item.code === code))
      .filter(Boolean) as AiCapability[],
);

const activeCapability = computed(
  () =>
    capabilities.value.find((item) => item.code === activeCode.value) ??
    groupCapabilities.value[0],
);

const requiresPrompt = computed(() =>
  activeCapability.value?.inputKinds.some(
    (kind) => kind === 'prompt' || kind === 'text',
  ),
);

const acceptsUpload = computed(() =>
  activeCapability.value?.inputKinds.some((kind) =>
    ['audio', 'image', 'video'].includes(kind),
  ),
);

const acceptsUrl = computed(() =>
  activeCapability.value?.inputKinds.includes('url'),
);

const isBatch = computed(() =>
  [
    'batch-image',
    'batch-image-edit',
    'batch-video',
    'copy-script',
    'creative-batch',
    'video-fission',
    'video-mashup',
  ].includes(activeCode.value),
);

const isToolbox = computed(() => route.path === '/fusion/video-toolbox');
const isIntelligence = computed(
  () => route.path === '/fusion/creative-intelligence',
);
const isImageCapability = computed(() =>
  [
    'batch-image',
    'batch-image-edit',
    'image-edit',
    'image-generate',
    'image-inpaint',
  ].includes(activeCode.value),
);
const isAudioCapability = computed(() =>
  ['music-generate', 'tts-generate', 'tts-preview'].includes(activeCode.value),
);

const outputMeta = computed(
  () =>
    ({
      audio: { icon: 'lucide:audio-lines', label: '音频' },
      data: { icon: 'lucide:database', label: '结构化数据' },
      image: { icon: 'lucide:image', label: '图片' },
      report: { icon: 'lucide:file-chart-column', label: '分析报告' },
      text: { icon: 'lucide:file-text', label: '文案与脚本' },
      video: { icon: 'lucide:clapperboard', label: '视频' },
    })[activeCapability.value?.outputKind ?? 'image'],
);

const recentTasks = computed(() => {
  const groupCodes = new Set(currentGroup.value.codes);
  return taskStore.tasks.filter(
    (task) => task.capability && groupCodes.has(task.capability),
  );
});

const sourceVersion = computed(() =>
  typeof route.query.sourceVersion === 'string'
    ? route.query.sourceVersion
    : '',
);

const creativeProfileId = computed(() =>
  typeof route.query.product === 'string' ? route.query.product : '',
);

const runInProgress = computed(() =>
  ['queued', 'running'].includes(activeRun.value?.status ?? ''),
);

const sampleInsightRows = computed(() => {
  if (activeCode.value === 'news-trends') {
    return [
      { label: '全球趋势', value: '多人协作、生存建造相关搜索 7 日上升 28%' },
      { label: '东南亚热点', value: '暑期组队活动与限时奖励讨论度提升' },
      { label: '创意机会', value: '用“3 秒集结队友”作为首屏视觉与文案钩子' },
    ];
  }
  if (activeCode.value === 'video-analyze') {
    return [
      { label: '开场钩子', value: '0-2.8 秒使用战斗胜负反转，信息密度高' },
      { label: '节奏', value: '平均镜头 1.6 秒，第 9 秒出现明显拖沓' },
      { label: 'CTA', value: '建议在 12 秒提前出现奖励与下载引导' },
    ];
  }
  return [
    { label: '有效素材', value: '已识别 18 条，重复 3 条' },
    { label: '主要标签', value: 'Gameplay、奖励、多人、竖屏、强 CTA' },
    { label: '合规记录', value: '已保存来源 URL、抓取时间与参考用途' },
  ];
});

function selectFirstCapability() {
  const queryCapability = route.query.capability;
  const target =
    typeof queryCapability === 'string' &&
    currentGroup.value.codes.includes(queryCapability as AiCapabilityCode)
      ? (queryCapability as AiCapabilityCode)
      : currentGroup.value.codes[0];
  if (target) activeCode.value = target;
}

function selectCapability(code: AiCapabilityCode) {
  if (runInProgress.value) {
    message.info('当前任务仍在执行，完成或取消后可切换其他工具');
    return;
  }
  activeCode.value = code;
  completedPreview.value = false;
  activeRun.value = undefined;
  void router.replace({
    query: { ...route.query, capability: code },
  });
}

function handleCapabilityChange(value: unknown) {
  selectCapability(value as AiCapabilityCode);
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  fileList.value = [...fileList.value, file];
  return false;
};

function removeUpload(file: UploadFile) {
  fileList.value = fileList.value.filter((item) => item.uid !== file.uid);
}

function moveUpload(index: number, offset: number) {
  const targetIndex = index + offset;
  if (targetIndex < 0 || targetIndex >= fileList.value.length) return;
  const next = [...fileList.value];
  const [item] = next.splice(index, 1);
  if (!item) return;
  next.splice(targetIndex, 0, item);
  fileList.value = next;
}

function fillExample() {
  if (isIntelligence.value) {
    formState.sourceUrl = 'https://www.facebook.com/ads/library/';
    formState.prompt =
      '关注游戏类广告，提取前 3 秒钩子、核心卖点、CTA 和素材结构。';
    return;
  }
  if (activeCapability.value?.outputKind === 'audio') {
    formState.prompt =
      '用自然、有行动力的表达介绍首发奖励，语速适中，结尾强调立即组队。';
    return;
  }
  formState.prompt =
    '为 Starfall 全球增长项目制作竖屏广告：前 3 秒突出团队战斗反馈，中段展示成长奖励，结尾使用清晰 CTA；保持品牌蓝绿色，避免夸大承诺。';
}

async function submitJob() {
  if (runInProgress.value) {
    message.info('当前任务仍在执行，可在本页查看进度或前往任务中心');
    return;
  }
  if (!projectStore.selectedProjectId) {
    message.warning('请先选择项目');
    return;
  }
  if (requiresPrompt.value && !formState.prompt.trim()) {
    message.warning('请填写处理目标、脚本或提示词');
    return;
  }
  if (acceptsUrl.value && !formState.sourceUrl.trim()) {
    message.warning('请填写来源地址');
    return;
  }
  if (
    acceptsUpload.value &&
    !requiresPrompt.value &&
    !acceptsUrl.value &&
    fileList.value.length === 0
  ) {
    message.warning('请上传或选择需要处理的素材');
    return;
  }
  if (activeCode.value === 'video-concat' && fileList.value.length < 2) {
    message.warning('视频拼接至少需要 2 个输入视频');
    return;
  }
  if (activeCode.value === 'lip-sync' && fileList.value.length < 2) {
    message.warning('口型同步需要人物图片/视频与音频两类输入');
    return;
  }

  submitting.value = true;
  completedPreview.value = false;
  try {
    const payload = {
      capability: activeCode.value,
      deliveryLineId: projectStore.selectedDeliveryLineId,
      expectedCount: formState.count,
      inputMaterialIds: fileList.value.map((file) => String(file.uid)),
      parameters: {
        aspectRatio: formState.aspectRatio,
        beatSync: formState.beatSync,
        bpm: formState.bpm,
        cameraMotion: formState.cameraMotion,
        complianceArchive: formState.complianceArchive,
        creativity: formState.creativity,
        duration: formState.duration,
        editMode: formState.editMode,
        includeCaptions: formState.includeCaptions,
        keepBrand: formState.keepBrand,
        language: formState.language,
        maskFeather: formState.maskFeather,
        materialSaveMode: formState.materialSaveMode,
        maxResults: formState.maxResults,
        model: formState.model,
        mood: formState.mood,
        normalizeAudio: formState.normalizeAudio,
        pitch: formState.pitch,
        preserveSubject: formState.preserveSubject,
        quality: formState.quality,
        region: formState.region,
        resolution: formState.resolution,
        sceneSensitivity: formState.sceneSensitivity,
        speed: formState.speed,
        sourceUrl: formState.sourceUrl,
        splitMode: formState.splitMode,
        transition: formState.transition,
        voice: formState.voice,
      },
      projectId: projectStore.selectedProjectId,
      prompt: formState.prompt,
    };
    activeRun.value = await taskStore.submitAiJob(payload);
    message.success('任务已提交，页面内可继续查看进度，完成后自动回写生成历史');
  } finally {
    submitting.value = false;
  }
}

function revealCompletedRun() {
  if (!activeRun.value || !activeCapability.value) return;
  if (completedPreview.value) return;
  completedPreview.value = true;
}

function saveResult(index: number) {
  if (!activeRun.value || !activeCapability.value) return;
  return workflowStore.saveGeneratedMaterial({
    capability: activeCode.value,
    deliveryLineId: projectStore.selectedDeliveryLineId,
    kind: activeCapability.value.outputKind,
    name: `${activeCapability.value.name}结果 ${index}`,
    parentVersionId: sourceVersion.value || undefined,
    projectId: projectStore.selectedProjectId,
    ratio: formState.aspectRatio,
    resultIndex: index,
    saveMode: formState.materialSaveMode,
    sourceTaskId: activeRun.value.id,
  });
}

function isResultSaved(index: number) {
  return Boolean(
    activeRun.value &&
      workflowStore.findGeneratedMaterial(activeRun.value.id, index),
  );
}

function isResultApproved(index: number) {
  if (!activeRun.value) return false;
  return (
    workflowStore.findGeneratedMaterial(activeRun.value.id, index)?.status ===
    'approved'
  );
}

function handleResultAction(
  action: 'download' | 'preview' | 'save',
  index: number,
) {
  const resultName = `${activeCapability.value?.name || '生成'}结果 ${index}`;
  if (action === 'preview') {
    previewIndex.value = index;
    previewOpen.value = true;
    return;
  }
  if (action === 'download') {
    const manifest = {
      capability: activeCode.value,
      name: resultName,
      parameters: {
        aspectRatio: formState.aspectRatio,
        language: formState.language,
        quality: formState.quality,
      },
      projectId: projectStore.selectedProjectId,
      sourceTaskId: activeRun.value?.id,
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(manifest, null, 2)], {
        type: 'application/json;charset=utf-8',
      }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `${activeCode.value}-result-${index}.json`;
    link.click();
    URL.revokeObjectURL(url);
    message.success(`${resultName}清单已下载`);
    return;
  }
  const saved = saveResult(index);
  if (saved)
    message.success(
      `${resultName} 已按“${formState.materialSaveMode === 'new-version' ? '新建素材版本' : '新建独立素材'}”入库`,
    );
}

function saveAndCreateAd(index: number) {
  const saved = saveResult(index);
  if (!saved) return;
  workflowStore.approveMaterialVersion(saved.id);
  previewOpen.value = false;
  void router.push({
    path: '/fusion/ads/create',
    query: { materialVersion: saved.id, source: 'ai-workbench' },
  });
}

function viewHistory() {
  router.push({ path: '/fusion/adgen-library', query: { tab: 'history' } });
}

onMounted(async () => {
  loading.value = true;
  try {
    await Promise.all([
      projectStore.loadProjectOptions(),
      taskStore.refresh(projectStore.selectedProjectId),
    ]);
    capabilities.value = await getAiCapabilitiesApi();
    selectFirstCapability();
    if (sourceVersion.value) {
      if (!formState.prompt.trim())
        formState.prompt = `基于胜出素材版本 ${sourceVersion.value} 制作第二轮创意：保留已验证的开场结构，替换视觉表达与 CTA，并生成可归因的新素材版本。`;
      workflowStore.registerSecondCreative(
        projectStore.selectedProjectId,
        sourceVersion.value,
      );
    }
    if (creativeProfileId.value && !formState.prompt.trim()) {
      formState.prompt = `使用产品创意档案 ${creativeProfileId.value} 中的产品定位、受众、核心卖点与禁用信息生成本轮创意；保留品牌一致性并输出可审核的素材版本。`;
    }
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : 'AI 工作台加载失败，请稍后重试',
    );
  } finally {
    loading.value = false;
  }
});

watch(
  () => route.path,
  () => {
    selectFirstCapability();
    completedPreview.value = false;
    activeRun.value = undefined;
  },
);

watch(
  () => route.query.capability,
  () => selectFirstCapability(),
);

watch(
  () => activeRun.value?.status,
  (status) => {
    if (status === 'success' || status === 'partial_success')
      revealCompletedRun();
  },
);
</script>

<template>
  <Page auto-content-height class="bg-slate-50" content-class="p-0">
    <div class="flex min-h-0 flex-col bg-white xl:h-full xl:overflow-hidden">
      <header class="border-b border-slate-200 px-4 py-4 lg:px-5">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="flex min-w-0 items-start gap-3">
            <div
              class="bg-primary/10 text-primary flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--adpulse-card-radius)] text-lg"
            >
              <IconifyIcon :icon="currentGroup.icon" />
            </div>
            <div class="min-w-0">
              <h1
                class="text-foreground mb-0 font-semibold text-[var(--adpulse-page-title-size)]"
              >
                {{ currentGroup.title }}
              </h1>
              <p class="mb-0 mt-1 max-w-3xl text-xs leading-5 text-slate-500">
                {{ currentGroup.description }}
              </p>
            </div>
          </div>
          <Space wrap>
            <Button @click="viewHistory"
              ><template #icon><IconifyIcon icon="lucide:history" /></template
              >生成历史</Button
            >
            <Button @click="taskStore.openDrawer()"
              ><template #icon><IconifyIcon icon="lucide:activity" /></template
              >任务中心</Button
            >
          </Space>
        </div>
        <div class="mt-4 flex overflow-x-auto pb-1" aria-label="当前能力工作流">
          <div
            v-for="(step, index) in currentGroup.workflow"
            :key="step"
            class="flex shrink-0 items-center"
          >
            <div
              class="flex h-7 items-center rounded-full bg-slate-100 px-3 text-xs font-medium text-slate-600"
            >
              <span class="mr-1.5 text-blue-700">{{ index + 1 }}</span
              >{{ step }}
            </div>
            <IconifyIcon
              v-if="index < currentGroup.workflow.length - 1"
              icon="lucide:chevron-right"
              class="mx-1 text-slate-300"
            />
          </div>
        </div>
      </header>

      <div
        class="grid min-h-0 grid-cols-1 xl:flex-1 xl:grid-cols-[250px_minmax(0,1fr)_330px]"
      >
        <aside
          class="capability-list border-b border-slate-200 bg-slate-50 p-3 xl:overflow-y-auto xl:border-b-0 xl:border-r"
        >
          <div class="xl:hidden">
            <label
              class="mb-1.5 block text-xs font-semibold text-slate-600"
              for="mobile-capability-select"
            >
              选择工具
            </label>
            <Select
              id="mobile-capability-select"
              :value="activeCode"
              :disabled="runInProgress"
              :options="
                groupCapabilities.map((item) => ({
                  label: item.name,
                  value: item.code,
                }))
              "
              class="w-full"
              @change="handleCapabilityChange"
            />
          </div>
          <div
            class="text-muted-foreground mb-2 hidden px-2 text-xs font-semibold xl:block"
          >
            选择工具
          </div>
          <div class="hidden xl:block xl:space-y-1">
            <button
              v-for="item in groupCapabilities"
              :key="item.code"
              type="button"
              :disabled="runInProgress"
              class="min-h-11 min-w-[180px] rounded-lg border px-3 py-2.5 text-left transition-colors xl:w-full xl:min-w-0"
              :class="
                activeCode === item.code
                  ? 'border-blue-200 bg-white text-blue-800 shadow-sm'
                  : 'border-transparent text-slate-700 hover:bg-white'
              "
              :aria-current="activeCode === item.code ? 'page' : undefined"
              @click="selectCapability(item.code)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-medium">{{ item.name }}</span>
                <IconifyIcon
                  icon="lucide:chevron-right"
                  class="text-slate-400"
                />
              </div>
              <div
                class="mt-1 line-clamp-2 hidden text-xs leading-5 text-slate-500 xl:block"
              >
                {{ item.description }}
              </div>
            </button>
          </div>
        </aside>

        <main class="min-w-0 overflow-visible p-4 lg:p-5 xl:overflow-y-auto">
          <Alert
            v-if="!projectStore.selectedProjectId"
            class="mb-4"
            message="尚未选择项目，产出无法关联产品、素材版本与后续投放归因。"
            type="warning"
            show-icon
          />
          <Alert
            v-if="creativeProfileId"
            class="mb-4"
            :message="`已关联产品创意档案：${creativeProfileId}`"
            description="本次任务会继承档案中的卖点、受众、品牌约束和禁用信息。"
            type="success"
            show-icon
          />

          <div class="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <h2 class="m-0 text-xl font-semibold text-slate-900">
                  {{ activeCapability?.name }}
                </h2>
                <Tag color="blue">页面内可操作</Tag>
                <Tag>{{ outputMeta?.label }}</Tag>
              </div>
              <p class="mb-0 mt-1 max-w-2xl text-sm leading-6 text-slate-500">
                {{ activeCapability?.description }}
              </p>
            </div>
          </div>

          <Form layout="vertical">
            <FormItem v-if="acceptsUrl" label="来源地址" required>
              <Input
                v-model:value="formState.sourceUrl"
                placeholder="输入广告库、网页、视频或趋势来源 URL"
              >
                <template #prefix
                  ><IconifyIcon icon="lucide:link-2" class="text-slate-400"
                /></template>
              </Input>
              <div class="mt-2 text-xs text-slate-500">
                系统会保存来源地址、采集时间和研究用途；保存不代表获得商业复刻授权。
              </div>
            </FormItem>

            <FormItem
              v-if="requiresPrompt"
              :label="
                isIntelligence ? '分析目标与筛选条件' : '创作目标与处理指令'
              "
              required
            >
              <Input.TextArea
                v-model:value="formState.prompt"
                :rows="6"
                :maxlength="2000"
                show-count
                :placeholder="
                  isIntelligence
                    ? '说明品类、地区、平台、关注标签和希望提取的结构。'
                    : '说明卖点、受众、创意结构、画面要求、禁用信息和希望保留的品牌特征。'
                "
              />
              <Button class="mt-2" @click="fillExample"
                ><template #icon
                  ><IconifyIcon icon="lucide:sparkles" /></template
                >填入示例</Button
              >
            </FormItem>

            <FormItem v-if="acceptsUpload" label="输入素材">
              <Upload.Dragger
                :before-upload="beforeUpload"
                :file-list="fileList"
                multiple
                @remove="removeUpload"
              >
                <div class="py-5">
                  <IconifyIcon
                    icon="lucide:cloud-upload"
                    class="text-primary mx-auto text-2xl"
                  />
                  <p class="mb-1 mt-3 text-sm font-medium text-slate-800">
                    拖入图片、视频或音频，也可点击选择
                  </p>
                  <p class="m-0 text-xs text-slate-500">
                    支持多文件队列；正式环境提交后进入 AdGen 对象存储
                  </p>
                </div>
              </Upload.Dragger>
            </FormItem>

            <Card
              v-if="activeCode === 'video-concat' && fileList.length"
              title="拼接顺序"
              class="mb-4 border-slate-200"
            >
              <div class="space-y-2">
                <div
                  v-for="(file, index) in fileList"
                  :key="file.uid"
                  class="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2"
                >
                  <span
                    class="flex h-6 w-6 items-center justify-center rounded bg-blue-100 text-xs font-semibold text-blue-700"
                    >{{ index + 1 }}</span
                  >
                  <span
                    class="min-w-0 flex-1 truncate text-sm text-slate-700"
                    >{{ file.name }}</span
                  >
                  <Button
                    :aria-label="`上移 ${file.name}`"
                    :disabled="index === 0"
                    type="text"
                    @click="moveUpload(index, -1)"
                    ><IconifyIcon icon="lucide:arrow-up"
                  /></Button>
                  <Button
                    :aria-label="`下移 ${file.name}`"
                    :disabled="index === fileList.length - 1"
                    type="text"
                    @click="moveUpload(index, 1)"
                    ><IconifyIcon icon="lucide:arrow-down"
                  /></Button>
                </div>
              </div>
            </Card>

            <Card
              v-if="isImageCapability"
              title="图片专业设置"
              class="mb-4 border-slate-200"
            >
              <div class="grid gap-x-4 sm:grid-cols-2">
                <FormItem
                  v-if="['image-edit', 'batch-image-edit'].includes(activeCode)"
                  label="编辑方式"
                >
                  <Select
                    v-model:value="formState.editMode"
                    :options="[
                      { label: '统一指令', value: 'unified' },
                      { label: '逐张指令', value: 'per-image' },
                      { label: '自动识别差异', value: 'auto' },
                    ]"
                  />
                </FormItem>
                <FormItem
                  v-if="activeCode === 'image-inpaint'"
                  label="蒙版羽化"
                >
                  <InputNumber
                    v-model:value="formState.maskFeather"
                    :min="0"
                    :max="50"
                    addon-after="px"
                    class="w-full"
                  />
                </FormItem>
                <FormItem label="输出分辨率">
                  <Select
                    v-model:value="formState.resolution"
                    :options="[
                      { label: '1024 px', value: '1024' },
                      { label: '2048 px', value: '2048' },
                      { label: '4096 px', value: '4096' },
                    ]"
                  />
                </FormItem>
                <FormItem>
                  <div
                    class="flex min-h-11 items-center justify-between rounded-lg border border-slate-200 px-3 py-2"
                  >
                    <span class="text-sm text-slate-700">保护主体与商标</span>
                    <Switch v-model:checked="formState.preserveSubject" />
                  </div>
                </FormItem>
              </div>
            </Card>

            <Card
              v-if="isAudioCapability || activeCode === 'lip-sync'"
              title="声音与口播设置"
              class="mb-4 border-slate-200"
            >
              <div class="grid gap-x-4 sm:grid-cols-2">
                <FormItem v-if="activeCode !== 'music-generate'" label="音色">
                  <Select
                    v-model:value="formState.voice"
                    :options="[
                      { label: 'Nova · 活力女声', value: 'Nova' },
                      { label: 'Hikari · 日语女声', value: 'Hikari' },
                      { label: 'Orion · 沉稳男声', value: 'Orion' },
                    ]"
                  />
                </FormItem>
                <FormItem v-if="activeCode !== 'music-generate'" label="语速">
                  <InputNumber
                    v-model:value="formState.speed"
                    :min="0.6"
                    :max="1.6"
                    :step="0.05"
                    class="w-full"
                  />
                </FormItem>
                <FormItem label="情绪风格">
                  <Select
                    v-model:value="formState.mood"
                    :options="[
                      { label: '活力', value: 'energetic' },
                      { label: '可信', value: 'trust' },
                      { label: '史诗', value: 'epic' },
                      { label: '温暖', value: 'warm' },
                    ]"
                  />
                </FormItem>
                <FormItem
                  v-if="activeCode === 'music-generate'"
                  label="目标 BPM"
                >
                  <InputNumber
                    v-model:value="formState.bpm"
                    :min="60"
                    :max="180"
                    class="w-full"
                  />
                </FormItem>
              </div>
            </Card>

            <Card
              v-if="
                [
                  'video-generate',
                  'seedance',
                  'video-extend',
                  'video-edit',
                ].includes(activeCode)
              "
              title="视频生成设置"
              class="mb-4 border-slate-200"
            >
              <div class="grid gap-x-4 sm:grid-cols-2">
                <FormItem label="分辨率"
                  ><Select
                    v-model:value="formState.resolution"
                    :options="[
                      { label: '720p', value: '720p' },
                      { label: '1080p', value: '1080p' },
                      { label: '2K', value: '2k' },
                    ]"
                /></FormItem>
                <FormItem label="镜头运动"
                  ><Select
                    v-model:value="formState.cameraMotion"
                    :options="[
                      { label: '模型自动', value: 'auto' },
                      { label: '缓慢推进', value: 'push-in' },
                      { label: '环绕主体', value: 'orbit' },
                      { label: '固定镜头', value: 'static' },
                    ]"
                /></FormItem>
              </div>
            </Card>

            <Card
              v-if="isIntelligence"
              title="采集与分析范围"
              class="mb-4 border-slate-200"
            >
              <div class="grid gap-x-4 sm:grid-cols-2">
                <FormItem label="地区"
                  ><Select
                    v-model:value="formState.region"
                    :options="[
                      { label: '全球', value: 'global' },
                      { label: '北美', value: 'na' },
                      { label: '东南亚', value: 'sea' },
                      { label: '日本', value: 'jp' },
                    ]"
                /></FormItem>
                <FormItem label="最多采集"
                  ><InputNumber
                    v-model:value="formState.maxResults"
                    :min="10"
                    :max="500"
                    addon-after="条"
                    class="w-full"
                /></FormItem>
                <FormItem
                  ><div
                    class="flex min-h-11 items-center justify-between rounded-lg border border-slate-200 px-3 py-2"
                  >
                    <div>
                      <div class="text-sm text-slate-700">
                        保存来源与抓取时间
                      </div>
                      <div class="text-xs text-slate-500">用于合规研究记录</div>
                    </div>
                    <Switch
                      v-model:checked="formState.complianceArchive"
                    /></div
                ></FormItem>
              </div>
            </Card>

            <Card
              v-if="activeCode === 'creative-batch'"
              title="生产线编排"
              class="mb-4 border-slate-200"
            >
              <Checkbox.Group
                v-model:value="formState.targetPlatforms"
                class="grid gap-2 sm:grid-cols-2"
              >
                <Checkbox value="video-mashup">视频混剪</Checkbox>
                <Checkbox value="video-fission">视频裂变</Checkbox>
                <Checkbox value="new-creative">新创意</Checkbox>
                <Checkbox value="copy-script">脚本与文案</Checkbox>
              </Checkbox.Group>
            </Card>

            <div v-if="isToolbox" class="grid gap-4 sm:grid-cols-2">
              <FormItem label="处理模式"
                ><Select
                  v-model:value="formState.splitMode"
                  :options="[
                    { label: '按镜头自动处理', value: 'scene' },
                    { label: '按固定时长处理', value: 'duration' },
                    { label: '按脚本结构处理', value: 'script' },
                  ]"
              /></FormItem>
              <FormItem label="目标时长（秒）"
                ><InputNumber
                  v-model:value="formState.duration"
                  :min="3"
                  :max="180"
                  class="w-full"
              /></FormItem>
              <FormItem v-if="activeCode === 'video-concat'" label="片段转场"
                ><Select
                  v-model:value="formState.transition"
                  :options="[
                    { label: '直接切换', value: 'cut' },
                    { label: '交叉淡化', value: 'fade' },
                    { label: '运动匹配', value: 'motion' },
                  ]"
              /></FormItem>
              <FormItem v-if="activeCode === 'video-split'" label="镜头灵敏度"
                ><InputNumber
                  v-model:value="formState.sceneSensitivity"
                  :min="10"
                  :max="100"
                  class="w-full"
              /></FormItem>
              <FormItem
                v-if="
                  ['auto-edit', 'video-concat', 'video-mashup'].includes(
                    activeCode,
                  )
                "
                ><div
                  class="flex min-h-11 items-center justify-between rounded-lg border border-slate-200 px-3 py-2"
                >
                  <span class="text-sm text-slate-700">统一音量</span
                  ><Switch v-model:checked="formState.normalizeAudio" /></div
              ></FormItem>
              <FormItem
                v-if="['auto-edit', 'new-creative'].includes(activeCode)"
                ><div
                  class="flex min-h-11 items-center justify-between rounded-lg border border-slate-200 px-3 py-2"
                >
                  <span class="text-sm text-slate-700">自动字幕</span
                  ><Switch v-model:checked="formState.includeCaptions" /></div
              ></FormItem>
            </div>
          </Form>

          <Divider />
          <section aria-live="polite">
            <div class="mb-3 flex items-center justify-between gap-3">
              <h3 class="m-0 text-base font-semibold text-slate-900">
                执行结果
              </h3>
              <Button v-if="completedPreview" @click="viewHistory"
                >查看完整记录</Button
              >
            </div>
            <Card
              v-if="activeRun && !completedPreview"
              class="border-blue-200 bg-blue-50/40"
              :body-style="{ padding: '16px' }"
            >
              <div class="flex items-start gap-3">
                <div class="rounded-lg bg-blue-100 p-2 text-blue-700">
                  <IconifyIcon
                    icon="lucide:loader-circle"
                    class="animate-spin text-lg"
                  />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center justify-between gap-3">
                    <span class="font-medium text-slate-900">{{
                      activeRun.title
                    }}</span
                    ><Tag color="blue">{{
                      activeRun.status === 'queued' ? '排队中' : '执行中'
                    }}</Tag>
                  </div>
                  <p class="mb-2 mt-1 text-xs text-slate-500">
                    {{ activeRun.message }}
                  </p>
                  <Progress :percent="activeRun.progress" />
                </div>
              </div>
            </Card>

            <div
              v-else-if="completedPreview && isIntelligence"
              class="space-y-2"
            >
              <div
                v-for="row in sampleInsightRows"
                :key="row.label"
                class="flex flex-col gap-1 rounded-lg border border-slate-200 p-4 sm:flex-row sm:items-start"
              >
                <div class="w-28 shrink-0 text-xs font-semibold text-blue-700">
                  {{ row.label }}
                </div>
                <div class="text-sm leading-6 text-slate-700">
                  {{ row.value }}
                </div>
              </div>
              <Button type="primary" @click="router.push('/fusion/ai-studio')"
                >转为创意任务</Button
              >
            </div>

            <div
              v-else-if="completedPreview"
              class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
            >
              <div
                v-for="index in Math.min(formState.count, 6)"
                :key="index"
                class="result-card"
              >
                <div class="result-preview">
                  <IconifyIcon
                    :icon="outputMeta?.icon"
                    class="text-primary text-2xl"
                  />
                </div>
                <div class="p-3">
                  <div class="truncate text-sm font-medium text-slate-800">
                    {{ activeCapability?.name }}结果 {{ index }}
                  </div>
                  <div class="mt-1 text-xs text-slate-500">
                    {{ formState.aspectRatio }} · {{ formState.quality }}
                  </div>
                  <div class="mt-3 flex flex-wrap gap-1">
                    <Button @click="handleResultAction('preview', index)"
                      >预览</Button
                    >
                    <Button @click="handleResultAction('download', index)"
                      >下载</Button
                    >
                    <Button
                      :disabled="isResultSaved(index)"
                      type="primary"
                      @click="handleResultAction('save', index)"
                      >{{
                        isResultSaved(index)
                          ? isResultApproved(index)
                            ? '审核通过'
                            : '待审核'
                          : '入库'
                      }}</Button
                    >
                  </div>
                </div>
              </div>
            </div>

            <Empty
              v-else-if="!activeRun"
              :description="`提交后将在此展示${outputMeta?.label}结果、任务状态和入库动作`"
            />
          </section>
        </main>

        <aside
          class="overflow-visible border-t border-slate-200 bg-slate-50 p-4 xl:overflow-y-auto xl:border-l xl:border-t-0"
        >
          <h3 class="m-0 text-base font-semibold text-slate-900">执行参数</h3>
          <p class="mb-4 mt-1 text-xs leading-5 text-slate-500">
            参数会随任务保存，可在生成历史中恢复和复用。
          </p>
          <Form layout="vertical">
            <FormItem label="模型"
              ><Select
                v-model:value="formState.model"
                :options="[
                  { label: '自动路由（推荐）', value: 'auto' },
                  { label: 'Gemini / Veo', value: 'google' },
                  { label: '百炼模型池', value: 'bailian' },
                  { label: 'Seedance 2.0', value: 'seedance' },
                ]"
            /></FormItem>
            <FormItem v-if="!isIntelligence" label="产出数量"
              ><InputNumber
                v-model:value="formState.count"
                :min="1"
                :max="isBatch ? 100 : 20"
                class="w-full"
            /></FormItem>
            <FormItem
              v-if="
                ['image', 'video'].includes(activeCapability?.outputKind || '')
              "
              label="画面比例"
            >
              <Radio.Group
                v-model:value="formState.aspectRatio"
                button-style="solid"
                ><Radio.Button value="1:1">1:1</Radio.Button
                ><Radio.Button value="4:5">4:5</Radio.Button
                ><Radio.Button value="9:16">9:16</Radio.Button
                ><Radio.Button value="16:9">16:9</Radio.Button></Radio.Group
              >
            </FormItem>
            <FormItem
              v-if="activeCapability?.outputKind === 'video'"
              label="目标时长（秒）"
              ><InputNumber
                v-model:value="formState.duration"
                :min="3"
                :max="180"
                class="w-full"
            /></FormItem>
            <FormItem label="输出质量"
              ><Select
                v-model:value="formState.quality"
                :options="[
                  { label: '标准（更快）', value: 'standard' },
                  { label: '高清', value: 'high' },
                  { label: '精细（更慢）', value: 'ultra' },
                ]"
            /></FormItem>
            <FormItem v-if="!isIntelligence" label="入库策略">
              <Select
                v-model:value="formState.materialSaveMode"
                :options="[
                  { label: '新建素材版本', value: 'new-version' },
                  { label: '新建独立素材', value: 'new-material' },
                ]"
              />
            </FormItem>
            <FormItem label="语言"
              ><Select
                v-model:value="formState.language"
                :options="[
                  { label: '简体中文', value: '简体中文' },
                  { label: 'English', value: 'English' },
                  { label: '日本語', value: '日本語' },
                  { label: 'ไทย', value: 'ไทย' },
                ]"
            /></FormItem>
            <FormItem v-if="!isIntelligence" label="创意发散度"
              ><input
                v-model.number="formState.creativity"
                class="w-full accent-blue-700"
                min="0"
                max="100"
                type="range"
              />
              <div class="mt-1 flex justify-between text-[11px] text-slate-400">
                <span>稳健</span><span>{{ formState.creativity }}</span
                ><span>发散</span>
              </div></FormItem
            >
            <FormItem
              ><div
                class="flex min-h-11 items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2"
              >
                <div>
                  <div class="text-sm font-medium text-slate-800">
                    保持品牌一致性
                  </div>
                  <div class="text-xs text-slate-500">应用产品知识库约束</div>
                </div>
                <Switch v-model:checked="formState.keepBrand" /></div
            ></FormItem>
          </Form>
          <Alert
            message="失败、取消或未生成有效结果时退款；部分成功只结算有效产出。"
            type="info"
            show-icon
          />
          <Button
            block
            class="mt-4"
            type="primary"
            :loading="submitting"
            :disabled="loading || runInProgress"
            @click="submitJob"
            ><template #icon><IconifyIcon icon="lucide:play" /></template
            >{{ runInProgress ? '任务执行中' : '提交任务' }}</Button
          >

          <Divider />
          <div class="flex items-center justify-between">
            <h4 class="m-0 text-sm font-semibold text-slate-800">最近任务</h4>
            <Button type="link" @click="taskStore.openDrawer()">全部</Button>
          </div>
          <div v-if="recentTasks.length" class="mt-2 space-y-2">
            <div
              v-for="task in recentTasks.slice(0, 3)"
              :key="task.id"
              class="rounded-lg border border-slate-200 bg-white p-3"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="truncate text-xs font-medium text-slate-700">{{
                  task.title
                }}</span
                ><Tag
                  :color="
                    task.status === 'success'
                      ? 'green'
                      : task.status === 'failed'
                        ? 'red'
                        : 'blue'
                  "
                  >{{ task.status }}</Tag
                >
              </div>
              <Progress
                class="mt-2"
                :percent="task.progress"
                :show-info="false"
              />
            </div>
          </div>
          <div
            v-else
            class="mt-3 rounded-lg border border-dashed border-slate-300 p-4 text-center text-xs text-slate-400"
          >
            当前能力组暂无任务
          </div>
        </aside>
      </div>
    </div>

    <Modal
      v-model:open="previewOpen"
      :title="`${activeCapability?.name || '生成'}结果 ${previewIndex}`"
      :width="620"
      centered
    >
      <div
        class="overflow-hidden rounded-xl border border-slate-200 bg-slate-50"
      >
        <div class="result-preview min-h-64">
          <IconifyIcon :icon="outputMeta?.icon" class="text-primary text-3xl" />
        </div>
        <div
          class="grid gap-3 border-t border-slate-200 bg-white p-4 text-sm sm:grid-cols-2"
        >
          <div>
            <span class="text-slate-500">来源任务：</span
            ><span class="text-slate-800">{{ activeRun?.id }}</span>
          </div>
          <div>
            <span class="text-slate-500">输出规格：</span
            ><span class="text-slate-800"
              >{{ formState.aspectRatio }} · {{ formState.quality }}</span
            >
          </div>
          <div>
            <span class="text-slate-500">关联项目：</span
            ><span class="text-slate-800">{{
              projectStore.currentProject?.name
            }}</span>
          </div>
          <div>
            <span class="text-slate-500">素材状态：</span
            ><Tag
              :color="
                isResultApproved(previewIndex)
                  ? 'green'
                  : isResultSaved(previewIndex)
                    ? 'orange'
                    : 'default'
              "
              >{{
                isResultApproved(previewIndex)
                  ? '审核通过'
                  : isResultSaved(previewIndex)
                    ? '待审核'
                    : '待入库'
              }}</Tag
            >
          </div>
        </div>
      </div>
      <template #footer>
        <Button @click="previewOpen = false">关闭</Button>
        <Button @click="handleResultAction('download', previewIndex)"
          >下载结果清单</Button
        >
        <Button type="primary" @click="saveAndCreateAd(previewIndex)">{{
          isResultApproved(previewIndex)
            ? '去创建广告'
            : isResultSaved(previewIndex)
              ? '审核通过并创建广告'
              : '入库、审核并创建广告'
        }}</Button>
      </template>
    </Modal>
  </Page>
</template>

<style scoped>
.result-card {
  min-width: 0;
  overflow: hidden;
  background: white;
  border: 1px solid rgb(226 232 240);
  border-radius: 10px;
}

.result-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 128px;
  background:
    radial-gradient(circle at 30% 20%, rgb(219 234 254), transparent 42%),
    linear-gradient(145deg, rgb(248 250 252), rgb(238 242 255));
}

@media (max-width: 1279px) {
  .capability-list::-webkit-scrollbar {
    height: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .animate-spin {
    animation: none;
  }
}
</style>
