<script lang="ts" setup>
import type { UploadFile, UploadProps } from 'ant-design-vue';

import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Divider,
  Empty,
  Form,
  FormItem,
  Input,
  InputNumber,
  Radio,
  Select,
  Slider,
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
import { useGlobalTaskStore, useProjectContextStore } from '#/store';

const projectStore = useProjectContextStore();
const taskStore = useGlobalTaskStore();
const route = useRoute();
const capabilities = ref<AiCapability[]>([]);
const activeCode = ref<AiCapabilityCode>('image-generate');
const capabilityKeyword = ref('');
const loading = ref(false);
const submitting = ref(false);
const fileList = ref<UploadFile[]>([]);
const lastTask = ref<AsyncTask>();
const resultReady = ref(false);
const promptInput = ref<{ focus?: () => void }>();
const uploadInputRef = ref<HTMLElement>();
const formErrors = reactive({
  material: '',
  project: '',
  prompt: '',
});

const formState = reactive({
  aspectRatio: '1:1',
  count: 4,
  creativity: 70,
  keepBrand: true,
  language: '简体中文',
  prompt: '',
  quality: 'standard',
});

const activeCapability = computed(() =>
  capabilities.value.find((item) => item.code === activeCode.value),
);
const filteredCapabilities = computed(() => {
  const keyword = capabilityKeyword.value.trim().toLowerCase();
  if (!keyword) return capabilities.value;
  return capabilities.value.filter((item) =>
    `${item.name}${item.description}${item.code}`
      .toLowerCase()
      .includes(keyword),
  );
});
const requiresPrompt = computed(() =>
  activeCapability.value?.inputKinds.includes('prompt'),
);
const acceptsUpload = computed(() =>
  activeCapability.value?.inputKinds.some(
    (kind) => kind === 'audio' || kind === 'image' || kind === 'video',
  ),
);
const outputLabel = computed(
  () =>
    ({
      audio: '音频',
      data: '数据',
      image: '图片',
      report: '分析报告',
      text: '文本',
      video: '视频',
    })[activeCapability.value?.outputKind ?? 'image'],
);

function selectCapabilityFromRoute(value: unknown) {
  if (typeof value !== 'string') return;
  if (capabilities.value.some((item) => item.code === value)) {
    activeCode.value = value as AiCapabilityCode;
  }
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  fileList.value = [...fileList.value, file];
  formErrors.material = '';
  return false;
};

function removeUpload(file: UploadFile) {
  fileList.value = fileList.value.filter((item) => item.uid !== file.uid);
}

function selectCapability(code: AiCapabilityCode) {
  activeCode.value = code;
  formErrors.material = '';
  formErrors.prompt = '';
}

function showValidationError(
  field: keyof typeof formErrors,
  messageText: string,
) {
  formErrors[field] = messageText;
  void nextTick(() => {
    if (field === 'prompt') {
      promptInput.value?.focus?.();
      return;
    }
    if (field === 'material') uploadInputRef.value?.focus();
  });
}

async function submitJob() {
  formErrors.project = '';
  formErrors.prompt = '';
  formErrors.material = '';
  if (!projectStore.selectedProjectId) {
    showValidationError('project', '请先选择项目后再提交 AI 任务');
    return;
  }
  if (requiresPrompt.value && !formState.prompt.trim()) {
    showValidationError('prompt', '请填写本次创作目标或提示词');
    return;
  }
  if (
    acceptsUpload.value &&
    !requiresPrompt.value &&
    fileList.value.length === 0
  ) {
    showValidationError('material', '请上传需要处理的素材');
    return;
  }

  submitting.value = true;
  resultReady.value = false;
  try {
    lastTask.value = await taskStore.submitAiJob({
      capability: activeCode.value,
      deliveryLineId: projectStore.selectedDeliveryLineId,
      expectedCount: formState.count,
      inputMaterialIds: fileList.value.map((file) => String(file.uid)),
      parameters: {
        aspectRatio: formState.aspectRatio,
        creativity: formState.creativity,
        keepBrand: formState.keepBrand,
        language: formState.language,
        quality: formState.quality,
      },
      projectId: projectStore.selectedProjectId,
      prompt: formState.prompt,
    });
    message.success('任务已提交，可在当前页面和任务中心查看进度');
    window.setTimeout(() => {
      if (!lastTask.value) return;
      lastTask.value.status = 'running';
      lastTask.value.progress = 42;
      lastTask.value.message = '正在执行模型生成与媒体处理';
    }, 600);
    window.setTimeout(() => {
      if (!lastTask.value) return;
      lastTask.value.status = 'success';
      lastTask.value.progress = 100;
      lastTask.value.resultCount = formState.count;
      lastTask.value.message = '有效结果已生成并写入生成历史';
      resultReady.value = true;
    }, 1800);
  } finally {
    submitting.value = false;
  }
}

function restoreSavedInput() {
  const restoreId = route.query.restore;
  const templateId = route.query.template;
  if (typeof restoreId === 'string') {
    const raw = localStorage.getItem('fusion-ai-restore');
    if (!raw) return;
    try {
      const saved = JSON.parse(raw) as {
        capability?: AiCapabilityCode;
        parameters?: Partial<typeof formState>;
        prompt?: string;
      };
      if (saved.capability) selectCapabilityFromRoute(saved.capability);
      if (saved.prompt) formState.prompt = saved.prompt;
      if (saved.parameters) Object.assign(formState, saved.parameters);
      message.success('已从生成历史恢复提示词与参数');
    } catch {
      message.warning('历史参数无法解析，请重新配置');
    }
    return;
  }
  if (typeof templateId === 'string') {
    const raw = localStorage.getItem('fusion-ai-template');
    if (!raw) return;
    try {
      const saved = JSON.parse(raw) as { name?: string; prompt?: string };
      if (saved.prompt) formState.prompt = saved.prompt;
      message.success(`已套用模板：${saved.name || templateId}`);
    } catch {
      message.warning('模板内容无法解析，请重新选择');
    }
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    await projectStore.loadProjectOptions();
    capabilities.value = await getAiCapabilitiesApi();
    selectCapabilityFromRoute(route.query.capability);
    restoreSavedInput();
  } finally {
    loading.value = false;
  }
});

watch(
  () => route.query.capability,
  (value) => selectCapabilityFromRoute(value),
);
</script>

<template>
  <Page auto-content-height class="bg-slate-50" content-class="p-0">
    <div
      class="border-border bg-card grid h-full min-h-0 grid-cols-1 overflow-hidden border-t lg:grid-cols-[240px_minmax(0,1fr)_300px]"
    >
      <h1 class="sr-only">AI 创意工作台</h1>
      <aside
        class="order-1 overflow-y-auto border-b border-slate-200 bg-slate-50 lg:order-none lg:border-b-0 lg:border-r"
      >
        <details class="mobile-panel lg:block">
          <summary class="mobile-panel__summary lg:hidden">
            <span class="flex min-w-0 items-center gap-2">
              <IconifyIcon icon="lucide:wand-sparkles" class="text-blue-600" />
              <span class="truncate font-medium text-slate-900"
                >选择 AI 能力</span
              >
            </span>
            <span class="ml-3 truncate text-xs text-slate-500">
              {{ activeCapability?.name || '加载中' }}
            </span>
          </summary>
          <div class="mobile-panel__content p-4">
            <div class="mb-4 hidden lg:block">
              <h2 class="m-0 text-lg font-semibold text-slate-900">
                AI 创意工作台
              </h2>
              <p class="mb-0 mt-1 text-xs leading-5 text-slate-500">
                保留现有图片、视频、编辑、复刻、拼接和切割能力。
              </p>
            </div>
            <Input.Search
              v-model:value="capabilityKeyword"
              allow-clear
              aria-label="搜索 AI 能力"
              class="mb-3"
              placeholder="搜索 AI 能力"
            />
            <div class="space-y-1" aria-label="AI 能力列表">
              <button
                v-for="item in filteredCapabilities"
                :key="item.code"
                type="button"
                class="w-full cursor-pointer rounded-lg border px-3 py-3 text-left transition-colors"
                :class="
                  activeCode === item.code
                    ? 'border-blue-200 bg-blue-50 text-blue-700'
                    : 'border-transparent bg-transparent text-slate-700 hover:bg-slate-100'
                "
                @click="selectCapability(item.code)"
              >
                <span class="flex items-center justify-between gap-2">
                  <span class="text-sm font-medium">{{ item.name }}</span>
                  <IconifyIcon icon="lucide:chevron-right" class="text-sm" />
                </span>
                <span class="mt-1 block text-xs leading-5 text-slate-500">{{
                  item.description
                }}</span>
              </button>
            </div>
          </div>
        </details>
      </aside>

      <aside
        class="order-2 overflow-y-auto border-b border-slate-200 bg-slate-50 lg:order-none lg:border-b-0 lg:border-l"
      >
        <details class="mobile-panel lg:block">
          <summary class="mobile-panel__summary lg:hidden">
            <span class="flex min-w-0 items-center gap-2">
              <IconifyIcon
                icon="lucide:sliders-horizontal"
                class="text-blue-600"
              />
              <span class="truncate font-medium text-slate-900">生成参数</span>
            </span>
            <span class="ml-3 truncate text-xs text-slate-500">
              {{ formState.count }} 个 · {{ formState.aspectRatio }}
            </span>
          </summary>
          <div class="mobile-panel__content p-5">
            <h2 class="m-0 text-base font-semibold text-slate-900">生成参数</h2>
            <p class="mb-5 mt-1 text-xs text-slate-500">
              不同能力共用基础参数，后端按能力转换。
            </p>

            <Form layout="vertical">
              <FormItem label="产出数量">
                <InputNumber
                  v-model:value="formState.count"
                  :min="1"
                  :max="50"
                  class="w-full"
                />
              </FormItem>
              <FormItem label="画面比例">
                <Radio.Group
                  v-model:value="formState.aspectRatio"
                  button-style="solid"
                >
                  <Radio.Button value="1:1">1:1</Radio.Button>
                  <Radio.Button value="4:5">4:5</Radio.Button>
                  <Radio.Button value="9:16">9:16</Radio.Button>
                  <Radio.Button value="16:9">16:9</Radio.Button>
                </Radio.Group>
              </FormItem>
              <FormItem label="输出质量">
                <Select
                  v-model:value="formState.quality"
                  :options="[
                    { label: '标准（更快）', value: 'standard' },
                    { label: '高清', value: 'high' },
                    { label: '精细（更慢）', value: 'ultra' },
                  ]"
                />
              </FormItem>
              <FormItem label="文案语言">
                <Select
                  v-model:value="formState.language"
                  :options="[
                    { label: '简体中文', value: '简体中文' },
                    { label: 'English', value: 'English' },
                    { label: '日本語', value: '日本語' },
                    { label: 'ไทย', value: 'ไทย' },
                  ]"
                />
              </FormItem>
              <FormItem label="创意发散度">
                <Slider
                  v-model:value="formState.creativity"
                  :marks="{ 20: '稳健', 70: '平衡', 100: '发散' }"
                />
              </FormItem>
              <FormItem>
                <div
                  class="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-3"
                >
                  <div>
                    <div class="text-sm font-medium text-slate-800">
                      保持品牌一致性
                    </div>
                    <div class="mt-1 text-xs text-slate-500">
                      优先继承品牌色和构图
                    </div>
                  </div>
                  <Switch v-model:checked="formState.keepBrand" />
                </div>
              </FormItem>
            </Form>

            <Divider />
            <Alert
              message="AI 失败、取消或未生成有效产出时，任务进入退款状态；部分成功只结算有效产出。"
              type="info"
              show-icon
            />
            <Button
              block
              class="mt-4 hidden lg:block"
              type="primary"
              :loading="submitting"
              :disabled="loading"
              @click="submitJob"
            >
              提交 AI 任务
            </Button>
          </div>
        </details>
      </aside>

      <main class="order-3 min-w-0 overflow-y-auto p-5 lg:order-none lg:p-6">
        <Alert
          v-if="!projectStore.selectedProjectId || formErrors.project"
          class="mb-4"
          :message="
            formErrors.project || '尚未选择项目，AI 产出无法进入素材闭环'
          "
          type="warning"
          show-icon
          role="alert"
        />
        <div class="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2">
              <h2 class="m-0 text-xl font-semibold text-slate-900">
                {{ activeCapability?.name || '加载中' }}
              </h2>
              <Tag color="blue">异步任务</Tag>
            </div>
            <p class="mb-0 mt-1 text-sm text-slate-500">
              {{ activeCapability?.description }}
            </p>
          </div>
          <div class="text-right text-xs text-slate-500">
            <div>
              当前项目：{{ projectStore.currentProject?.name || '未选择' }}
            </div>
            <div class="mt-1">产出类型：{{ outputLabel }}</div>
          </div>
        </div>

        <Form layout="vertical">
          <FormItem
            v-if="requiresPrompt"
            label="创作目标与提示词"
            required
            :validate-status="formErrors.prompt ? 'error' : undefined"
            :help="formErrors.prompt || undefined"
          >
            <Input.TextArea
              ref="promptInput"
              v-model:value="formState.prompt"
              :maxlength="2000"
              :rows="7"
              placeholder="说明产品卖点、目标受众、创意方向、画面结构、禁用元素和希望保留的品牌特征。"
              show-count
              @update:value="formErrors.prompt = ''"
            />
            <div class="mt-2 flex flex-wrap gap-2">
              <Button
                @click="
                  formState.prompt =
                    '突出首充福利与即时反馈，画面节奏紧凑，保留品牌主色，不使用夸大承诺。'
                "
                >增长卖点模板</Button
              >
              <Button
                @click="
                  formState.prompt =
                    '参考上传素材的结构，重做视觉元素与文案，避免直接复制商标和人物形象。'
                "
                >合规复刻模板</Button
              >
            </div>
          </FormItem>

          <FormItem
            v-if="acceptsUpload"
            label="输入素材"
            :validate-status="formErrors.material ? 'error' : undefined"
            :help="formErrors.material || undefined"
          >
            <div ref="uploadInputRef" tabindex="-1">
              <Upload.Dragger
                :before-upload="beforeUpload"
                :file-list="fileList"
                :multiple="true"
                @remove="removeUpload"
              >
                <div class="py-5">
                  <IconifyIcon
                    icon="lucide:cloud-upload"
                    class="text-primary mx-auto text-2xl"
                  />
                  <p class="mb-1 mt-3 text-sm font-medium text-slate-800">
                    上传图片、视频或音频，也可后续接入素材库选择器
                  </p>
                  <p class="m-0 text-xs text-slate-500">
                    文件暂不上传，提交任务时统一登记为输入素材
                  </p>
                </div>
              </Upload.Dragger>
            </div>
          </FormItem>
        </Form>

        <Button
          block
          class="mb-4 lg:hidden"
          type="primary"
          :loading="submitting"
          :disabled="loading"
          @click="submitJob"
        >
          提交 AI 任务
        </Button>

        <Divider />
        <Card title="本次产出与任务状态" class="border-slate-200">
          <div
            v-if="lastTask && !resultReady"
            class="rounded-lg bg-blue-50 p-4"
          >
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-sm font-medium text-slate-900">
                  {{ lastTask.title }}
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  {{ lastTask.message }}
                </div>
              </div>
              <Tag color="blue">
                {{ lastTask.status === 'queued' ? '排队中' : '执行中' }}
              </Tag>
            </div>
            <div class="mt-3 h-2 overflow-hidden rounded-full bg-blue-100">
              <div
                class="h-full rounded-full bg-blue-600 transition-all"
                :style="{ width: `${lastTask.progress}%` }"
              ></div>
            </div>
          </div>
          <div
            v-else-if="resultReady"
            class="grid grid-cols-2 gap-3 md:grid-cols-3"
          >
            <div
              v-for="index in Math.min(formState.count, 6)"
              :key="index"
              class="overflow-hidden rounded-lg border border-slate-200 bg-white"
            >
              <div class="bg-muted flex min-h-24 items-center justify-center">
                <IconifyIcon
                  :icon="
                    activeCapability?.outputKind === 'video'
                      ? 'lucide:clapperboard'
                      : activeCapability?.outputKind === 'audio'
                        ? 'lucide:audio-lines'
                        : activeCapability?.outputKind === 'text'
                          ? 'lucide:file-text'
                          : 'lucide:image'
                  "
                  class="text-primary text-2xl"
                />
              </div>
              <div class="p-3">
                <div class="truncate text-sm font-medium text-slate-800">
                  {{ activeCapability?.name }}结果 {{ index }}
                </div>
                <div class="mt-2 flex flex-wrap gap-1">
                  <Button @click="message.info(`结果 ${index} 已打开预览`)"
                    >预览</Button
                  >
                  <Button
                    @click="message.success(`结果 ${index} 下载任务已创建`)"
                    >下载</Button
                  >
                  <Button
                    type="primary"
                    @click="
                      message.success(`结果 ${index} 已写入当前项目素材库`)
                    "
                    >入库</Button
                  >
                </div>
              </div>
            </div>
          </div>
          <Empty
            v-else
            :description="`提交后将生成 ${formState.count} 个${outputLabel}产出，并自动回写当前项目素材库`"
          />
        </Card>
      </main>
    </div>
  </Page>
</template>

<style scoped>
.mobile-panel__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 52px;
  padding: 0 16px;
  cursor: pointer;
}

.mobile-panel__summary::-webkit-details-marker {
  display: none;
}

.mobile-panel__summary::after {
  margin-left: 8px;
  font-size: 18px;
  color: #64748b;
  content: '⌄';
}

.mobile-panel[open] .mobile-panel__summary::after {
  transform: rotate(180deg);
}

.mobile-panel__content {
  display: none;
}

.mobile-panel[open] .mobile-panel__content {
  display: block;
}

@media (min-width: 1024px) {
  .mobile-panel__content {
    display: block;
  }
}
</style>
