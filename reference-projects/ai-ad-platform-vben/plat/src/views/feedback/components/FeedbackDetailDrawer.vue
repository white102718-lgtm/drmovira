<script setup lang="ts">
import type {
  FeedbackDetail,
  FeedbackDiagnostics,
  FeedbackListItem,
  FeedbackStatus,
} from '#/api';
import type { SystemUserApi } from '#/api/system/user';

import { computed, onBeforeUnmount, ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Divider,
  Empty,
  FormItem,
  Input,
  message,
  Select,
  Spin,
  Tag,
} from 'ant-design-vue';

import { getFeedbackDetailApi, updateFeedbackStatusApi } from '#/api';
import { downloadStoredFileApi } from '#/api/file';
import { getUserList } from '#/api/system/user';

import { categoryLabels, statusMeta } from '../data';
import MediaPreview from '#/views/components/MediaPreview.vue';

const emit = defineEmits<{ success: [] }>();

interface PreviewFile {
  isAttachmentPreview?: boolean;
  type: 'image' | 'video';
  url: string;
}

type FeedbackAttachment = FeedbackDetail['attachments'][number];

const detail = ref<FeedbackDetail>();
const loading = ref(false);
const status = ref<FeedbackStatus>('PENDING');
const adminReply = ref('');
const ownerId = ref<string>();
const ownerOptions = ref<Array<{ label: string; value: string }>>([]);
const ownerOptionsLoading = ref(false);
const previewOpen = ref(false);
const previewFile = ref<PreviewFile>();
const previewLoadingFileId = ref<string>();
const attachmentPreviews = ref<Record<string, PreviewFile>>({});
const attachmentPreviewLoadingIds = ref<Set<string>>(new Set());
let attachmentPreviewRequestVersion = 0;

const statusOptions = Object.entries(statusMeta).map(([value, meta]) => ({
  label: meta.label,
  value,
}));

const diagnosticLabels: Partial<Record<keyof FeedbackDiagnostics, string>> = {
  appVersion: '应用版本',
  browser: '浏览器',
  deviceMemory: '设备内存（GB）',
  devicePixelRatio: '像素比',
  deviceType: '设备类型',
  hardwareConcurrency: 'CPU 逻辑核心',
  language: '浏览器语言',
  networkType: '网络类型',
  operatingSystem: '操作系统',
  pageUrl: '发生页面',
  routeName: '路由名称',
  screenResolution: '屏幕分辨率',
  timezone: '时区',
  viewportSize: '页面视口',
};

const diagnosticEntries = computed(() => {
  const diagnostics = detail.value?.diagnostics;
  if (!diagnostics) return [];
  return Object.entries(diagnostics)
    .filter(
      ([key, value]) =>
        key !== 'consoleLogs' &&
        value !== undefined &&
        value !== null &&
        value !== '',
    )
    .map(([key, value]) => ({
      key,
      label: diagnosticLabels[key as keyof FeedbackDiagnostics] ?? String(key),
      value: String(value),
    }));
});

const consoleLogs = computed(
  () => detail.value?.diagnostics?.consoleLogs ?? [],
);

const [Drawer, drawerApi] = useVbenDrawer({
  confirmText: '保存处理结果',
  async onConfirm() {
    if (!detail.value) return;
    drawerApi.lock();
    try {
      detail.value = await updateFeedbackStatusApi(detail.value.id, {
        adminReply: adminReply.value.trim() || undefined,
        ownerId: ownerId.value ?? null,
        status: status.value,
      });
      message.success('处理结果已保存');
      emit('success');
    } finally {
      drawerApi.unlock();
    }
  },
  async onOpenChange(open) {
    if (!open) {
      closePreview();
      resetAttachmentPreviews();
      return;
    }
    const row = drawerApi.getData<FeedbackListItem>();
    if (!row?.id) return;
    loading.value = true;
    detail.value = undefined;
    resetAttachmentPreviews();
    try {
      detail.value = await getFeedbackDetailApi(row.id);
      status.value = detail.value.status;
      ownerId.value = detail.value.ownerId ?? undefined;
      adminReply.value = detail.value.adminReply ?? '';
      void loadAttachmentPreviews(detail.value.attachments);
      await loadOwnerOptions(detail.value);
    } finally {
      loading.value = false;
    }
  },
});

async function loadOwnerOptions(feedback: FeedbackDetail) {
  ownerOptionsLoading.value = true;
  try {
    const result = await getUserList({ page: 1, pageSize: 200, status: 1 });
    ownerOptions.value = (result.items ?? []).map(
      (user: SystemUserApi.User) => ({
        label: user.username
          ? `${user.displayName}（${user.username}）`
          : user.displayName,
        value: user.id,
      }),
    );
    if (
      feedback.ownerId &&
      feedback.ownerName &&
      !ownerOptions.value.some((option) => option.value === feedback.ownerId)
    ) {
      ownerOptions.value.unshift({
        label: `${feedback.ownerName}（已停用）`,
        value: feedback.ownerId,
      });
    }
  } finally {
    ownerOptionsLoading.value = false;
  }
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function isPreviewableFile(file: FeedbackAttachment) {
  return (
    file.mimeType.startsWith('image/') || file.mimeType.startsWith('video/')
  );
}

function releaseAttachmentPreviews(previews = attachmentPreviews.value) {
  Object.values(previews).forEach((preview) => {
    URL.revokeObjectURL(preview.url);
  });
}

function resetAttachmentPreviews() {
  attachmentPreviewRequestVersion++;
  releaseAttachmentPreviews();
  attachmentPreviews.value = {};
  attachmentPreviewLoadingIds.value = new Set();
}

async function loadAttachmentPreviews(attachments: FeedbackAttachment[]) {
  const previewableFiles = attachments.filter(isPreviewableFile);
  if (previewableFiles.length === 0) return;

  const requestVersion = ++attachmentPreviewRequestVersion;
  attachmentPreviewLoadingIds.value = new Set(
    previewableFiles.map((file) => file.id),
  );
  const previews = await Promise.all(
    previewableFiles.map(async (file) => {
      try {
        const blob = await downloadStoredFileApi(file.id);
        return [
          file.id,
          {
            type: file.mimeType.startsWith('video/') ? 'video' : 'image',
            url: URL.createObjectURL(blob),
          },
        ] as const;
      } catch {
        return undefined;
      }
    }),
  );
  const nextPreviews = Object.fromEntries(
    previews.filter((preview): preview is readonly [string, PreviewFile] =>
      Boolean(preview),
    ),
  );

  // 抽屉切换时丢弃过期请求，避免旧附件缩略图写入新的反馈详情。
  if (requestVersion !== attachmentPreviewRequestVersion) {
    releaseAttachmentPreviews(nextPreviews);
    return;
  }
  attachmentPreviews.value = nextPreviews;
  attachmentPreviewLoadingIds.value = new Set();
}

function closePreview() {
  if (previewFile.value?.url && !previewFile.value.isAttachmentPreview) {
    URL.revokeObjectURL(previewFile.value.url);
  }
  previewOpen.value = false;
  previewFile.value = undefined;
}

async function handlePreview(file: FeedbackAttachment) {
  if (!isPreviewableFile(file) || previewLoadingFileId.value) return;
  const cachedPreview = attachmentPreviews.value[file.id];
  if (cachedPreview) {
    closePreview();
    previewFile.value = { ...cachedPreview, isAttachmentPreview: true };
    previewOpen.value = true;
    return;
  }
  previewLoadingFileId.value = file.id;
  try {
    const blob = await downloadStoredFileApi(file.id);
    closePreview();
    previewFile.value = {
      type: file.mimeType.startsWith('video/') ? 'video' : 'image',
      url: URL.createObjectURL(blob),
    };
    previewOpen.value = true;
  } catch {
    message.error(`${file.originalName} 预览失败，请稍后重试`);
  } finally {
    previewLoadingFileId.value = undefined;
  }
}

async function handleDownload(fileId: string, fileName: string) {
  const blob = await downloadStoredFileApi(fileId);
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

onBeforeUnmount(() => {
  closePreview();
  resetAttachmentPreviews();
});
</script>

<template>
  <Drawer class="w-full max-w-[760px]" title="反馈详情">
    <div
      v-if="loading"
      class="flex min-h-64 items-center justify-center"
      role="status"
    >
      <Spin tip="正在加载反馈详情" />
    </div>

    <div v-else-if="detail" class="space-y-4">
      <Card title="反馈内容">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <Tag>{{ categoryLabels[detail.category] }}</Tag>
          <Tag :color="statusMeta[detail.status].color">
            {{ statusMeta[detail.status].label }}
          </Tag>
          <span class="text-muted-foreground text-xs">
            {{ detail.createdAt }}
          </span>
        </div>
        <h3 class="text-foreground m-0 text-base font-semibold">
          {{ detail.title }}
        </h3>
        <p class="mb-0 mt-3 whitespace-pre-wrap break-words text-sm leading-6">
          {{ detail.content }}
        </p>
      </Card>

      <Card title="账号与来源">
        <Descriptions :column="1" bordered>
          <DescriptionsItem label="提交账号">
            {{ detail.submittedByName }}
            <span
              v-if="detail.submittedByUsername"
              class="text-muted-foreground"
            >
              （{{ detail.submittedByUsername }}）
            </span>
          </DescriptionsItem>
          <DescriptionsItem label="客户端 IP">
            {{ detail.clientIp || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="设备类型">
            {{ detail.deviceType || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="发生页面">
            <span class="break-all">{{ detail.pageUrl || '-' }}</span>
          </DescriptionsItem>
          <DescriptionsItem label="User-Agent">
            <span class="break-all">{{ detail.userAgent || '-' }}</span>
          </DescriptionsItem>
        </Descriptions>
      </Card>

      <Card title="附件">
        <ul v-if="detail.attachments.length > 0" class="m-0 space-y-2 p-0">
          <li
            v-for="file in detail.attachments"
            :key="file.id"
            class="border-border flex list-none items-center gap-3 rounded-lg border px-3 py-2"
          >
            <button
              v-if="isPreviewableFile(file)"
              class="bg-muted focus-visible:outline-primary relative size-16 shrink-0 overflow-hidden rounded-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              :aria-label="`预览附件 ${file.originalName}`"
              :disabled="attachmentPreviewLoadingIds.has(file.id)"
              type="button"
              @click="handlePreview(file)"
            >
              <Spin
                v-if="attachmentPreviewLoadingIds.has(file.id)"
                class="absolute inset-0 flex items-center justify-center"
              />
              <video
                v-else-if="attachmentPreviews[file.id]?.type === 'video'"
                aria-hidden="true"
                class="size-full object-cover"
                muted
                playsinline
                preload="metadata"
                :src="attachmentPreviews[file.id]?.url"
              />
              <img
                v-else-if="attachmentPreviews[file.id]?.url"
                alt=""
                class="size-full object-cover"
                :src="attachmentPreviews[file.id]?.url"
              />
              <IconifyIcon
                v-else
                aria-hidden="true"
                class="text-muted-foreground mx-auto size-5"
                :icon="
                  file.mimeType.startsWith('video/')
                    ? 'lucide:video'
                    : 'lucide:image'
                "
              />
              <span
                v-if="attachmentPreviews[file.id]?.type === 'video'"
                aria-hidden="true"
                class="absolute inset-0 flex items-center justify-center bg-black/30 text-white"
              >
                <IconifyIcon class="size-5" icon="lucide:play" />
              </span>
            </button>
            <IconifyIcon
              v-else
              aria-hidden="true"
              class="text-muted-foreground size-5 shrink-0"
              icon="lucide:paperclip"
            />
            <div class="min-w-0 flex-1">
              <p
                class="m-0 truncate text-sm font-medium"
                :title="file.originalName"
              >
                {{ file.originalName }}
              </p>
              <p class="text-muted-foreground m-0 mt-1 text-xs">
                {{ formatFileSize(file.fileSize) }} · {{ file.mimeType }}
              </p>
            </div>
            <Button
              v-if="!isPreviewableFile(file)"
              :aria-label="`下载附件 ${file.originalName}`"
              type="link"
              @click="handleDownload(file.id, file.originalName)"
            >
              下载
            </Button>
          </li>
        </ul>
        <Empty
          v-else
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
          description="暂无附件"
        />
      </Card>

      <Card title="客户端诊断信息">
        <Descriptions
          v-if="diagnosticEntries.length > 0"
          :column="1"
          bordered
          size="small"
        >
          <DescriptionsItem
            v-for="item in diagnosticEntries"
            :key="item.key"
            :label="item.label"
          >
            <span class="break-all">{{ item.value }}</span>
          </DescriptionsItem>
        </Descriptions>
        <Empty
          v-else
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
          description="用户未附带客户端诊断信息"
        />

        <Divider orientation="left">
          控制台记录（{{ consoleLogs.length }}）
        </Divider>
        <div
          v-if="consoleLogs.length > 0"
          class="bg-muted max-h-72 space-y-2 overflow-y-auto rounded-lg p-3"
        >
          <div
            v-for="(log, index) in consoleLogs"
            :key="`${log.timestamp}-${index}`"
            class="font-mono text-xs leading-5"
          >
            <span class="text-muted-foreground mr-2">{{ log.timestamp }}</span>
            <Tag
              class="mr-2"
              :color="log.level === 'error' ? 'error' : undefined"
            >
              {{ log.level }}
            </Tag>
            <span class="whitespace-pre-wrap break-all">{{ log.message }}</span>
          </div>
        </div>
        <p v-else class="text-muted-foreground m-0 text-sm">没有控制台记录</p>
      </Card>

      <Card title="处理结果">
        <div class="grid grid-cols-1 gap-x-4 gap-y-4 md:grid-cols-2">
          <FormItem class="mb-0" label="跟进状态" required>
            <Select
              v-model:value="status"
              :options="statusOptions"
              aria-label="跟进状态"
            />
          </FormItem>
          <FormItem class="mb-0" label="负责人">
            <Select
              v-model:value="ownerId"
              allow-clear
              aria-label="负责人"
              :loading="ownerOptionsLoading"
              option-filter-prop="label"
              :options="ownerOptions"
              placeholder="选择负责人"
              show-search
            />
          </FormItem>
          <FormItem class="mb-0 md:col-span-2" label="处理说明">
            <Input.TextArea
              v-model:value="adminReply"
              :auto-size="{ minRows: 3, maxRows: 8 }"
              :maxlength="5000"
              aria-label="处理说明"
              placeholder="填写定位结果、解决方式或关闭原因"
              show-count
            />
          </FormItem>
          <p
            v-if="detail.processedByName || detail.processedAt"
            class="text-muted-foreground m-0 text-xs md:col-span-2"
          >
            最近由 {{ detail.processedByName || '未知用户' }} 于
            {{ detail.processedAt || '-' }} 更新
          </p>
        </div>
      </Card>
    </div>
  </Drawer>

  <MediaPreview
    :autoplay="false"
    :filetype="previewFile?.type"
    :open="previewOpen"
    :url="previewFile?.url"
    :z-index="2100"
    @update:open="(open) => !open && closePreview()"
  />
</template>
