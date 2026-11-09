<script lang="ts" setup>
import type { AiCapabilityCode } from '#/api';

import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Input,
  message,
  Row,
  Select,
  Statistic,
  Tag,
} from 'ant-design-vue';

type CapabilityStatus = 'available' | 'integrated' | 'pending' | 'studio';

interface CapabilityItem {
  capability?: AiCapabilityCode;
  description: string;
  icon: string;
  name: string;
  source: 'AdGen' | 'AdPulse' | 'MPower' | '统一平台';
  status: CapabilityStatus;
  studioPage?: string;
  tags: string[];
  targetPath?: string;
}

interface CapabilityGroup {
  description: string;
  eyebrow: string;
  icon: string;
  items: CapabilityItem[];
  title: string;
  workflow: string[];
}

const groups: Record<string, CapabilityGroup> = {
  '/fusion/creative-batch': {
    description:
      '保留 AdGen 三条核心生产线，以父任务统一编排混剪、裂变、新创意和脚本产出。',
    eyebrow: 'CREATIVE ORCHESTRATION',
    icon: 'lucide:layers-3',
    title: '创意批量生产',
    workflow: [
      '选择项目与输入版本',
      '配置多条生产线',
      '并行执行与计费',
      '审核并入库',
    ],
    items: [
      {
        capability: 'creative-batch',
        description: '一次提交多条创意生产线，统一跟踪进度、产量、费用和结果。',
        icon: 'lucide:workflow',
        name: 'Creative Batch',
        source: 'AdGen',
        status: 'available',
        studioPage: 'creativebatch',
        tags: ['多生产线', 'SSE', '任务聚合'],
      },
      {
        capability: 'video-mashup',
        description: '对素材片段进行组合、脚本重排和批量合成，支持 50+ 产出。',
        icon: 'lucide:blend',
        name: '视频混剪',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'videomashup',
        tags: ['50+', 'Worker', 'FFmpeg'],
      },
      {
        capability: 'video-fission',
        description:
          '通过 AI 策略和媒体处理生成大规模视频变体，支持 100+ 产出。',
        icon: 'lucide:git-fork',
        name: '视频裂变',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'videofission',
        tags: ['100+', 'AI 策略', '分布式'],
      },
      {
        capability: 'new-creative',
        description: '从创意方向、分镜、视频、配音到背景音乐完成新创意生产。',
        icon: 'lucide:wand-sparkles',
        name: '新创意',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'newcreative',
        tags: ['分镜', 'Veo', 'TTS'],
      },
      {
        capability: 'copy-script',
        description: '批量生成标题、广告正文、CTA、标签和视频脚本。',
        icon: 'lucide:notebook-pen',
        name: '脚本与文案批量',
        source: 'AdGen',
        status: 'available',
        tags: ['标题', 'CTA', '脚本'],
      },
    ],
  },
  '/fusion/image-creation': {
    description: '覆盖从零生成、参考图改写、局部重绘到批量变体的图片生产链。',
    eyebrow: 'IMAGE PRODUCTION',
    icon: 'lucide:image',
    title: '图片创作',
    workflow: [
      '选择产品知识',
      '输入提示词或参考图',
      '生成与编辑',
      '审核并生成版本',
    ],
    items: [
      {
        capability: 'image-generate',
        description: '根据产品卖点、平台和尺寸要求生成广告图片。',
        icon: 'lucide:image-plus',
        name: '图片生成',
        source: 'AdGen',
        status: 'integrated',
        tags: ['Gemini', '多比例', '品牌约束'],
      },
      {
        capability: 'image-edit',
        description: '换背景、改文案、替换主体并保持视觉风格一致。',
        icon: 'lucide:scan-line',
        name: '图片编辑',
        source: 'AdGen',
        status: 'integrated',
        tags: ['参考图', '换背景', '改文案'],
      },
      {
        capability: 'image-inpaint',
        description: '使用蒙版精确重绘局部区域，保留未选区域。',
        icon: 'lucide:paintbrush',
        name: '局部重绘',
        source: 'AdGen',
        status: 'available',
        tags: ['蒙版', '局部编辑'],
      },
      {
        capability: 'batch-image',
        description: '按语言、卖点、尺寸和平台批量生成图片变体。',
        icon: 'lucide:images',
        name: '批量图片',
        source: 'AdGen',
        status: 'available',
        tags: ['批量', '多语言', '多尺寸'],
      },
      {
        capability: 'batch-image-edit',
        description: '对一批输入图片应用统一或逐张编辑指令。',
        icon: 'lucide:gallery-horizontal-end',
        name: '批量图片编辑',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'batchedit',
        tags: ['批处理', '上传队列'],
      },
    ],
  },
  '/fusion/video-creation': {
    description: '保留视频生成、延长、编辑、Seedance 与人物口播等完整能力。',
    eyebrow: 'VIDEO GENERATION',
    icon: 'lucide:clapperboard',
    title: '视频创作',
    workflow: ['输入图片或脚本', '选择视频模型', '异步生成', '转码与入库'],
    items: [
      {
        capability: 'video-generate',
        description: '从提示词、首帧或参考视频生成广告视频。',
        icon: 'lucide:video',
        name: '视频生成',
        source: 'AdGen',
        status: 'integrated',
        tags: ['Veo', '图生视频', '文生视频'],
      },
      {
        capability: 'seedance',
        description: '使用 Seedance 模型进行高质量视频生成。',
        icon: 'lucide:aperture',
        name: 'Seedance 2.0',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'seedance',
        tags: ['Seedance', '异步'],
      },
      {
        capability: 'video-extend',
        description: '延长已有视频并保持镜头、人物和画面风格连续。',
        icon: 'lucide:unfold-horizontal',
        name: '视频延长',
        source: 'AdGen',
        status: 'available',
        tags: ['连续性', '异步任务'],
      },
      {
        capability: 'video-edit',
        description: '根据编辑指令调整镜头内容、节奏或视觉元素。',
        icon: 'lucide:film',
        name: '视频编辑',
        source: 'AdGen',
        status: 'available',
        tags: ['模型编辑', '镜头调整'],
      },
      {
        capability: 'lip-sync',
        description: '根据音频驱动人物口型，生成口播类广告素材。',
        icon: 'lucide:message-circle-more',
        name: '唇形同步',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'lipsync',
        tags: ['人物', '音频驱动'],
      },
    ],
  },
  '/fusion/audio-avatar': {
    description: '统一音乐、配音、声音风格预览和口播视频制作。',
    eyebrow: 'AUDIO & AVATAR',
    icon: 'lucide:audio-lines',
    title: '音频与口播',
    workflow: ['选择脚本', '配置音色与音乐', '生成音频', '合成视频或素材入库'],
    items: [
      {
        capability: 'music-generate',
        description: '按情绪、节奏、时长和创意方向生成背景音乐。',
        icon: 'lucide:music-2',
        name: '音乐生成',
        source: 'AdGen',
        status: 'available',
        tags: ['Lyria', 'BGM', '时长控制'],
      },
      {
        capability: 'tts-generate',
        description: '将广告脚本转换为多语言语音，支持风格与语速控制。',
        icon: 'lucide:mic-vocal',
        name: 'TTS 配音',
        source: 'AdGen',
        status: 'available',
        tags: ['多语言', '音色', '语速'],
      },
      {
        capability: 'tts-preview',
        description: '在正式生成前快速预览音色和表达风格。',
        icon: 'lucide:headphones',
        name: '音色与风格预览',
        source: 'AdGen',
        status: 'available',
        tags: ['低成本预览', '风格选择'],
      },
      {
        capability: 'lip-sync',
        description: '把配音与人物素材合成为自然口播视频。',
        icon: 'lucide:messages-square',
        name: '口播视频',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'lipsync',
        tags: ['唇形同步', '人物素材'],
      },
    ],
  },
  '/fusion/video-toolbox': {
    description:
      '完整保留 AdGen 原有媒体处理工具，不将复杂编辑能力压缩为一个通用按钮。',
    eyebrow: 'MEDIA TOOLBOX',
    icon: 'lucide:wrench',
    title: '视频工具箱',
    workflow: [
      '上传或选择素材',
      '配置处理规则',
      'Worker 执行',
      '预览并保存结果',
    ],
    items: (
      [
        [
          'video-concat',
          '视频拼接',
          '组合多个视频并统一编码、比例和音轨。',
          'lucide:combine',
          'concat',
        ],
        [
          'batch-image-edit',
          '批量编辑',
          '批量处理图片尺寸、背景和视觉元素。',
          'lucide:gallery-horizontal',
          'batchedit',
        ],
        [
          'video-split',
          '视频分割',
          '按镜头、时长或规则切割视频。',
          'lucide:scissors-line-dashed',
          'videosplit',
        ],
        [
          'video-replicate',
          '视频复刻',
          '分析结构后重做内容、节奏和表达。',
          'lucide:copy',
          'videoreplicate',
        ],
        [
          'video-mashup',
          '视频混剪',
          '从素材池组合并批量输出新视频。',
          'lucide:blend',
          'videomashup',
        ],
        [
          'auto-edit',
          'AI 自动剪辑',
          '自动选择镜头、节奏、字幕和音乐。',
          'lucide:wand',
          'autoedit',
        ],
        [
          'video-fission',
          '视频裂变',
          '按多策略生成大规模变体。',
          'lucide:git-fork',
          'videofission',
        ],
        [
          'creative-batch',
          '创意批量',
          '统一编排混剪、裂变、新创意和脚本。',
          'lucide:layers-3',
          'creativebatch',
        ],
        [
          'new-creative',
          '新创意',
          '从方向到成片的完整自动生产线。',
          'lucide:sparkles',
          'newcreative',
        ],
        [
          'seedance',
          'Seedance 2.0',
          '使用 Seedance 执行视频生成。',
          'lucide:aperture',
          'seedance',
        ],
      ] as const
    ).map(([capability, name, description, icon, studioPage]) => ({
      capability: capability as AiCapabilityCode,
      description,
      icon,
      name,
      source: 'AdGen' as const,
      status: 'studio' as const,
      studioPage,
      tags: ['原能力保留', 'AdGen Studio'],
    })),
  },
  '/fusion/creative-intelligence': {
    description:
      '把竞品广告、素材标签、视频结构和全球趋势转化为可使用的创意输入。',
    eyebrow: 'CREATIVE INTELLIGENCE',
    icon: 'lucide:radar',
    title: '创意情报',
    workflow: ['采集情报', '分析与打标', '保存合规参考', '转为创意任务'],
    items: [
      {
        capability: 'ad-crawler',
        description: '采集和整理广告情报，保存来源与抓取时间。',
        icon: 'lucide:spider',
        name: '广告爬虫',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'crawler',
        tags: ['竞品', '来源记录'],
      },
      {
        capability: 'fb-ad-scraper',
        description: '从 Facebook 广告库采集可研究的广告素材。',
        icon: 'lucide:facebook',
        name: 'Facebook 广告库',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'fbadscraper',
        tags: ['Facebook', '广告库'],
      },
      {
        capability: 'material-tagging',
        description: '批量识别素材主题、卖点、风格、人物和镜头标签。',
        icon: 'lucide:tags',
        name: '素材智能打标',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'materialtagging',
        tags: ['暂停恢复', '批量任务'],
      },
      {
        capability: 'video-analyze',
        description: '拆解视频结构、镜头、字幕、节奏、卖点和 CTA。',
        icon: 'lucide:scan-search',
        name: '视频分析',
        source: 'AdGen',
        status: 'available',
        studioPage: 'analysis',
        tags: ['结构拆解', '创意洞察'],
      },
      {
        capability: 'news-trends',
        description: '聚合全球新闻与 Google Trends，发现创意热点。',
        icon: 'lucide:trending-up',
        name: '全球新闻与趋势',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'news',
        tags: ['热点', 'Google Trends'],
      },
    ],
  },
  '/fusion/adgen-library': {
    description: '集中访问生成历史、模板、产品创意资料和对象存储。',
    eyebrow: 'KNOWLEDGE & ASSETS',
    icon: 'lucide:archive',
    title: '历史、模板与存储',
    workflow: ['检索历史', '复用模板', '关联产品', '保存或派生素材'],
    items: [
      {
        description: '查看图片、视频、音频和脚本的生成记录与参数。',
        icon: 'lucide:history',
        name: '生成历史',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'history',
        tags: ['结果', '参数', '复用'],
      },
      {
        description: '管理提示词模板、创意模板和视频结构模板。',
        icon: 'lucide:panels-top-left',
        name: '模板管理',
        source: 'AdGen',
        status: 'studio',
        studioPage: 'templates',
        tags: ['提示词', '创意结构'],
      },
      {
        description:
          '维护与 Java Product 关联的卖点、参考图、参考视频和禁用信息。',
        icon: 'lucide:library-big',
        name: '产品创意知识库',
        source: '统一平台',
        status: 'integrated',
        tags: ['Product', 'CreativeProfile'],
        targetPath: '/fusion/product-knowledge',
      },
      {
        description: '管理 AdGen 生成过程使用的输入、临时结果和导出文件。',
        icon: 'lucide:hard-drive',
        name: '存储桶管理',
        source: 'AdGen',
        status: 'studio',
        tags: ['MinIO', '生命周期'],
      },
    ],
  },
  '/fusion/business-operations': {
    description:
      '保留 MPower 与项目交付相关的运营能力；与广告增长无关的租户管理页面不继续迁移。',
    eyebrow: 'MPOWER OPERATIONS',
    icon: 'lucide:landmark',
    title: 'MPower 运营支撑',
    workflow: ['客户管理', '项目管理', '渠道与账户', '审批与交付'],
    items: [
      {
        description: '统一管理渠道、代理线和渠道账户关联。',
        icon: 'lucide:waypoints',
        name: '渠道与代理账户',
        source: 'MPower',
        status: 'pending',
        tags: ['Channel', 'AgentAccount'],
      },
      {
        description: '将 MPower Task/Subtask 映射为 Project 与 DeliveryLine。',
        icon: 'lucide:network',
        name: '项目任务线',
        source: 'MPower',
        status: 'integrated',
        tags: ['Project', 'DeliveryLine'],
        targetPath: '/fusion/projects',
      },
      {
        description: '保留需求、资源和关键操作的审批流程。',
        icon: 'lucide:badge-check',
        name: '审批管理',
        source: 'MPower',
        status: 'pending',
        tags: ['流程', '审批记录'],
      },
      {
        description: '按项目、投放线和客户查看交付与经营报表。',
        icon: 'lucide:notebook-tabs',
        name: '项目报表中心',
        source: 'MPower',
        status: 'pending',
        tags: ['项目报表', '明细'],
      },
      {
        description: '管理广告账户申请、开户及媒介资源交付。',
        icon: 'lucide:badge-dollar-sign',
        name: '媒介账户与资源',
        source: 'MPower',
        status: 'pending',
        tags: ['开户', '媒介资源'],
      },
    ],
  },
  '/fusion/adgen-operations': {
    description:
      '保留 AdGen 模型、密钥、用量、错误和 Worker 运维能力，并逐步收口身份权限。',
    eyebrow: 'ADGEN OPERATIONS',
    icon: 'lucide:server-cog',
    title: 'AdGen 模型与运维',
    workflow: ['模型与密钥', '用量与成本', 'Worker 状态', '错误与审计'],
    items: (
      [
        [
          'geminikeys',
          'Gemini Key 池',
          '管理 Gemini 服务密钥、额度与健康状态。',
          'lucide:bolt',
        ],
        [
          'bailiankeys',
          '百炼 Key 池',
          '管理百炼模型密钥、额度与健康状态。',
          'lucide:cloud-lightning',
        ],
        [
          'systemkeys',
          '系统访问 Key',
          '管理系统间调用使用的作用域 API Key。',
          'lucide:key-round',
        ],
        [
          'usagestats',
          '用量统计',
          '按用户、模型、项目和周期统计调用与成本。',
          'lucide:chart-pie',
        ],
        [
          'errorlogs',
          '错误日志',
          '集中查看模型、任务、媒体处理和回调错误。',
          'lucide:bug',
        ],
        [
          'mediaconfig',
          '媒体模型配置',
          '配置模型目录、能力、价格与路由策略。',
          'lucide:sliders-horizontal',
        ],
        [
          'workermanagement',
          'Worker 管理',
          '查看分布式媒体 Worker、队列与处理状态。',
          'lucide:server',
        ],
        [
          'rolepermission',
          'AdGen 权限迁移',
          '逐步将 AdGen 页面权限映射到 Java 权限声明。',
          'lucide:shield-check',
        ],
      ] as const
    ).map(([studioPage, name, description, icon], index) => ({
      description,
      icon,
      name,
      source: 'AdGen' as const,
      status: (index === 7 ? 'pending' : 'studio') as CapabilityStatus,
      studioPage,
      tags: index === 7 ? ['Java 身份', '权限映射'] : ['管理员', '原能力保留'],
    })),
  },
};

const route = useRoute();
const router = useRouter();
const keyword = ref('');
const statusFilter = ref<'all' | CapabilityStatus>('all');
const detailOpen = ref(false);
const selected = ref<CapabilityItem | null>(null);

const currentGroup = computed(
  () =>
    groups[route.path] ?? {
      description: '该能力组正在整理中。',
      eyebrow: 'CAPABILITY CENTER',
      icon: 'lucide:boxes',
      items: [],
      title: '能力中心',
      workflow: [],
    },
);

const statusMeta: Record<CapabilityStatus, { color: string; label: string }> = {
  available: { color: 'blue', label: '可使用' },
  integrated: { color: 'green', label: '已接入' },
  pending: { color: 'orange', label: '待联调' },
  studio: { color: 'purple', label: 'AdGen Studio' },
};

const filteredItems = computed(() => {
  const search = keyword.value.trim().toLowerCase();
  return currentGroup.value.items.filter((item) => {
    const matchesStatus =
      statusFilter.value === 'all' || item.status === statusFilter.value;
    const matchesKeyword =
      !search ||
      `${item.name}${item.description}${item.source}${item.tags.join('')}`
        .toLowerCase()
        .includes(search);
    return matchesStatus && matchesKeyword;
  });
});

const stats = computed(() => [
  { label: '功能总数', value: currentGroup.value.items.length },
  {
    label: '统一页面',
    value: currentGroup.value.items.filter((item) =>
      ['available', 'integrated'].includes(item.status),
    ).length,
  },
  {
    label: '原能力保留',
    value: currentGroup.value.items.filter((item) => item.status === 'studio')
      .length,
  },
  {
    label: '待后端联调',
    value: currentGroup.value.items.filter((item) => item.status === 'pending')
      .length,
  },
]);

function openCapability(item: CapabilityItem) {
  if (item.targetPath) {
    router.push(item.targetPath);
    return;
  }
  if (item.capability && item.status !== 'pending') {
    router.push({
      path: '/fusion/ai-studio',
      query: { capability: item.capability },
    });
    return;
  }
  selected.value = item;
  detailOpen.value = true;
}

function openFallbackWorkspace() {
  detailOpen.value = false;
  if (selected.value?.capability) {
    router.push({
      path: '/fusion/ai-studio',
      query: { capability: selected.value.capability },
    });
  } else {
    message.info('该能力必须通过原系统专用页面使用，暂不适合通用表单。');
  }
}
</script>

<template>
  <Page class="bg-slate-50" content-class="pb-6">
    <div class="flex w-full min-w-0 flex-col gap-4">
      <section
        class="overflow-hidden rounded-xl border border-slate-200 bg-white"
      >
        <div
          class="flex flex-col justify-between gap-5 p-5 lg:flex-row lg:items-center lg:p-6"
        >
          <div class="flex min-w-0 items-start gap-4">
            <div
              class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-sky-50 text-sky-700"
            >
              <IconifyIcon :icon="currentGroup.icon" class="text-2xl" />
            </div>
            <div class="min-w-0">
              <div class="text-xs font-semibold tracking-[0.14em] text-sky-700">
                {{ currentGroup.eyebrow }}
              </div>
              <h1 class="mb-0 mt-1 text-2xl font-semibold text-slate-950">
                {{ currentGroup.title }}
              </h1>
              <p class="mb-0 mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                {{ currentGroup.description }}
              </p>
            </div>
          </div>
          <Button
            class="shrink-0"
            type="primary"
            @click="router.push('/fusion/ai-tasks')"
          >
            <span class="flex items-center gap-2">
              <IconifyIcon icon="lucide:activity" />查看任务中心
            </span>
          </Button>
        </div>
        <div
          class="grid border-t border-slate-200 bg-slate-50 sm:grid-cols-2 xl:grid-cols-4"
        >
          <div
            v-for="(step, index) in currentGroup.workflow"
            :key="step"
            class="flex items-center gap-3 border-b border-slate-200 px-5 py-3 last:border-b-0 sm:border-r xl:border-b-0"
          >
            <span
              class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white"
            >
              {{ index + 1 }}
            </span>
            <span class="text-sm font-medium text-slate-700">{{ step }}</span>
          </div>
        </div>
      </section>

      <Row :gutter="[12, 12]">
        <Col v-for="item in stats" :key="item.label" :xs="12" :lg="6">
          <Card class="border-slate-200" :body-style="{ padding: '14px 16px' }">
            <Statistic :title="item.label" :value="item.value" />
          </Card>
        </Col>
      </Row>

      <Alert
        v-if="currentGroup.items.some((item) => item.status === 'studio')"
        message="复杂编辑和运维页面继续由 AdGen Studio 提供，功能不会因为统一前端而下线。配置部署地址后可从当前页面直接打开。"
        type="info"
        show-icon
      />

      <Card class="border-slate-200" :body-style="{ padding: '16px' }">
        <div class="flex flex-col gap-3 md:flex-row md:items-center">
          <Input.Search
            v-model:value="keyword"
            allow-clear
            class="md:max-w-md"
            placeholder="搜索功能、来源或标签"
          />
          <Select
            v-model:value="statusFilter"
            class="w-full md:w-44"
            :options="[
              { label: '全部接入状态', value: 'all' },
              ...Object.entries(statusMeta).map(([value, item]) => ({
                label: item.label,
                value,
              })),
            ]"
          />
        </div>
      </Card>

      <Empty
        v-if="filteredItems.length === 0"
        class="rounded-xl border border-slate-200 bg-white py-16"
        description="没有符合条件的功能"
      />
      <div v-else class="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        <Card
          v-for="item in filteredItems"
          :key="`${item.source}-${item.name}`"
          hoverable
          class="h-full border-slate-200"
          :body-style="{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            padding: '18px',
          }"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="flex min-w-0 items-start gap-3">
              <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700"
              >
                <IconifyIcon :icon="item.icon" class="text-lg" />
              </div>
              <div class="min-w-0">
                <h2 class="m-0 text-base font-semibold text-slate-900">
                  {{ item.name }}
                </h2>
                <div class="mt-1 text-xs text-slate-500">
                  来源：{{ item.source }}
                </div>
              </div>
            </div>
            <Tag :color="statusMeta[item.status].color" class="shrink-0">
              {{ statusMeta[item.status].label }}
            </Tag>
          </div>
          <p class="mb-0 mt-4 flex-1 text-sm leading-6 text-slate-600">
            {{ item.description }}
          </p>
          <div class="mt-4 flex flex-wrap gap-1.5">
            <Tag v-for="tag in item.tags" :key="tag">{{ tag }}</Tag>
          </div>
          <div class="mt-5 border-t border-slate-100 pt-4">
            <Button class="" type="link" @click="openCapability(item)">
              <span class="flex items-center gap-1.5">
                {{
                  item.targetPath
                    ? '打开页面'
                    : item.status === 'studio'
                      ? '使用统一工作台'
                      : item.status === 'pending'
                        ? '查看接入说明'
                        : '开始使用'
                }}
                <IconifyIcon icon="lucide:arrow-right" />
              </span>
            </Button>
          </div>
        </Card>
      </div>
    </div>

    <Drawer v-model:open="detailOpen" :title="selected?.name" width="440">
      <template v-if="selected">
        <div class="flex items-center gap-2">
          <Tag :color="statusMeta[selected.status].color">
            {{ statusMeta[selected.status].label }}
          </Tag>
          <Tag>{{ selected.source }}</Tag>
        </div>
        <p class="mt-4 text-sm leading-6 text-slate-600">
          {{ selected.description }}
        </p>
        <Alert
          v-if="selected.status === 'studio'"
          class="mt-4"
          message="AdGen 后端能力继续保留，所有前端入口统一在当前系统内打开，不再跳转外部登录页。"
          type="info"
          show-icon
        />
        <Alert
          v-else
          class="mt-4"
          message="页面入口与业务归属已经补齐，仍需对应后端接口、权限或主数据完成联调。"
          type="info"
          show-icon
        />
        <div class="mt-5 rounded-lg bg-slate-50 p-4">
          <div class="text-sm font-medium text-slate-900">接入要求</div>
          <ul class="mb-0 mt-3 space-y-2 pl-5 text-sm leading-6 text-slate-600">
            <li>使用 Java 身份并校验租户、项目与功能权限。</li>
            <li>任务携带项目、产品、输入素材版本和来源谱系。</li>
            <li>失败、取消和部分成功进入统一费用账本。</li>
          </ul>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2">
          <Button class="" @click="detailOpen = false">关闭</Button>
          <Button
            v-if="selected?.capability"
            class=""
            type="primary"
            @click="openFallbackWorkspace"
          >
            使用统一工作台
          </Button>
        </div>
      </template>
    </Drawer>
  </Page>
</template>
