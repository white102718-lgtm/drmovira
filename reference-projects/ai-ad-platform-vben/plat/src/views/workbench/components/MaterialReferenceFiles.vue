<script setup lang="ts">
import type { OrderReference } from '#/api/requirement';

import { computed, onBeforeUnmount, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';
import { Button, Empty, message, Popover, Tooltip } from 'ant-design-vue';
import theme from 'ant-design-vue/es/theme';

import { downloadAttachmentsZip } from '#/api/requirement';
import { downloadFileByUrl } from '#/utils/download';
import {
  COMPRESSED_EXTS,
  COMPRESSED_MIMES,
  ORDER_ATTACHMENT_IMAGE_EXTS,
  ORDER_ATTACHMENT_VIDEO_EXTS,
} from '#/utils/upload';
import MediaPreview from '#/views/components/MediaPreview.vue';

type AttachmentSource = OrderReference | Record<string, unknown>;

/** 参考资料使用卡片，需求附件使用紧凑缩略图，共享预览和下载逻辑。 */
const props = withDefaults(
  defineProps<{
    references: AttachmentSource[];
    compact?: boolean;
  }>(),
  { compact: false },
);
const { token } = theme.useToken();
// 预览高于详情抽屉和附件浮层，并随全局弹层基准调整，避免被抽屉遮住。
const previewZIndex = computed(() => token.value.zIndexPopupBase + 100);
const previewOpen = defineModel<boolean>('previewOpen', { default: false });
const previewIndex = ref(0);
const downloading = ref(false);
const failedThumbnails = ref(new Set<string>());
let active = true;

function stringValue(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function safeUrl(source: unknown) {
  const value = stringValue(source);
  return value && /^https?:\/\//i.test(value) ? value : undefined;
}

function fileKind(file: AttachmentSource) {
  if (file.type === 'link') return 'link';
  const type = stringValue(file.filetype).toLowerCase();
  const mime = stringValue(file.content_type).toLowerCase();
  const extension =
    (
      stringValue(file.name) ||
      ('filename' in file && stringValue(file.filename)) ||
      stringValue(file.object_key) ||
      stringValue(file.basename)
    )
      .split('.')
      .pop()
      ?.toLowerCase() ?? '';
  if (
    type === 'archive' ||
    COMPRESSED_EXTS.includes(type) ||
    COMPRESSED_EXTS.includes(extension) ||
    COMPRESSED_MIMES.includes(mime)
  )
    return 'archive';
  if (
    type === 'video' ||
    mime.startsWith('video/') ||
    ORDER_ATTACHMENT_VIDEO_EXTS.includes(type) ||
    ORDER_ATTACHMENT_VIDEO_EXTS.includes(extension)
  )
    return 'video';
  if (
    type === 'image' ||
    mime.startsWith('image/') ||
    ORDER_ATTACHMENT_IMAGE_EXTS.includes(type) ||
    ORDER_ATTACHMENT_IMAGE_EXTS.includes(extension)
  )
    return 'image';
  return 'file';
}

function thumbnail(file: AttachmentSource, kind: string) {
  const img = stringValue(file.img);
  if (img) {
    // 历史附件保存纯 base64，新附件可能已经带 data URI 前缀。
    if (img.startsWith('data:image/') || safeUrl(img)) return img;
    return `data:image/png;base64,${img}`;
  }
  return kind === 'image' ? safeUrl(file.url) : undefined;
}

function formatSize(size: unknown) {
  if (typeof size !== 'number' || !Number.isFinite(size) || size < 0)
    return '大小未知';
  if (size >= 1024 ** 3) return `${(size / 1024 ** 3).toFixed(1)} GB`;
  if (size >= 1024 ** 2) return `${(size / 1024 ** 2).toFixed(1)} MB`;
  return `${(size / 1024).toFixed(0)} KB`;
}

const files = computed(() =>
  props.references.map((file, index) => {
    const kind = fileKind(file);
    const url = safeUrl(file.url);
    // 子需求附件沿用历史字典结构，兼容 name / filename 两种文件名字段。
    const name =
      stringValue(file.name) ||
      ('filename' in file && stringValue(file.filename)) ||
      stringValue(file.basename) ||
      url ||
      (props.compact ? '附件' : '参考资料');
    const objectKey = stringValue(file.object_key);
    return {
      key: `${objectKey || url || name}-${index}`,
      name,
      objectKey,
      downloadUrl: safeUrl(file.download_url) || url,
      kind,
      url,
      thumbnail: thumbnail(file, kind),
      meta: kind === 'link' ? '链接' : formatSize(file.size),
      previewable: Boolean(url) && (kind === 'image' || kind === 'video'),
      icon: {
        archive: 'lucide:file-archive',
        file: 'lucide:file',
        image: 'lucide:image',
        link: 'lucide:link',
        video: 'lucide:film',
      }[kind],
    };
  }),
);
const previewItems = computed(() =>
  files.value
    .filter((file) => file.previewable)
    .map((file) => ({ key: file.key, filetype: file.kind, url: file.url })),
);
const downloadKeys = computed(() => [
  ...new Set(
    files.value.flatMap((file) => (file.objectKey ? [file.objectKey] : [])),
  ),
]);

function openPreview(key: string) {
  const index = previewItems.value.findIndex((file) => file.key === key);
  if (index < 0) return;
  previewIndex.value = index;
  previewOpen.value = true;
}

async function downloadBatch() {
  if (downloading.value || !downloadKeys.value.length) return;
  downloading.value = true;
  try {
    const result = await downloadAttachmentsZip(downloadKeys.value);
    // 切换工单或关闭抽屉后，不再触发上一单的下载和消息。
    if (!active) return;
    const url = safeUrl(result?.url);
    if (!url) throw new Error('未获取到下载地址，请重试');
    downloadFileByUrl(url, result.filename || '参考资料.zip');
  } catch {
    if (active) message.error('参考资料打包下载失败，请重试');
  } finally {
    if (active) downloading.value = false;
  }
}

onBeforeUnmount(() => {
  active = false;
});
</script>

<template>
  <div>
    <div v-if="compact" class="flex flex-wrap items-center gap-1">
      <Popover
        v-for="file in files"
        :key="file.key"
        placement="top"
        :trigger="['hover', 'click']"
        color="hsl(var(--foreground))"
        :overlay-inner-style="{ padding: '4px 8px' }"
      >
        <template #content>
          <div class="text-background flex items-center gap-3">
            <button
              v-if="file.previewable"
              type="button"
              class="attachment-action"
              :aria-label="`预览 ${file.name}`"
              @click="openPreview(file.key)"
            >
              预览
            </button>
            <button
              v-if="file.downloadUrl"
              type="button"
              class="attachment-action"
              :aria-label="`下载 ${file.name}`"
              @click="downloadFileByUrl(file.downloadUrl, file.name)"
            >
              下载
            </button>
            <span v-else class="text-xs">暂无下载地址</span>
          </div>
        </template>
        <button
          type="button"
          class="attachment-thumbnail bg-muted text-muted-foreground flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded hover:opacity-80"
          :title="file.name"
          :aria-label="`查看附件 ${file.name} 的操作`"
        >
          <img
            v-if="file.thumbnail && !failedThumbnails.has(file.key)"
            :src="file.thumbnail"
            alt=""
            width="32"
            height="32"
            loading="lazy"
            class="h-full w-full object-cover"
            @error="failedThumbnails.add(file.key)"
          />
          <IconifyIcon
            v-else
            :icon="file.icon"
            class="size-5"
            aria-hidden="true"
          />
        </button>
      </Popover>
      <span v-if="!files.length" class="text-muted-foreground">—</span>
    </div>
    <template v-else>
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div class="flex min-w-0 flex-wrap items-center gap-2">
          <h2
            class="text-foreground m-0 flex items-center gap-2 text-base font-semibold"
          >
            <span
              class="bg-primary h-4 w-1 shrink-0 rounded"
              aria-hidden="true"
            ></span>
            参考资料
          </h2>
          <span class="text-muted-foreground text-sm"
            >支持图片 / 视频 / 压缩文件</span
          >
        </div>
        <Button
          :loading="downloading"
          :disabled="!downloadKeys.length"
          @click="downloadBatch"
          >打包下载</Button
        >
      </div>
      <ul v-if="files.length" class="reference-grid m-0 list-none p-0">
        <li
          v-for="file in files"
          :key="file.key"
          class="border-border bg-card flex min-w-0 items-center gap-2 rounded border px-3 py-2"
        >
          <div
            class="bg-muted text-muted-foreground flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded"
          >
            <img
              v-if="file.thumbnail && !failedThumbnails.has(file.key)"
              :src="file.thumbnail"
              alt=""
              width="40"
              height="40"
              loading="lazy"
              class="h-full w-full object-cover"
              @error="failedThumbnails.add(file.key)"
            />
            <IconifyIcon
              v-else
              :icon="file.icon"
              class="size-5"
              aria-hidden="true"
            />
          </div>
          <div class="min-w-0 flex-1">
            <Tooltip :title="file.name" :trigger="['hover', 'focus', 'click']">
              <span
                tabindex="0"
                class="reference-name text-foreground block truncate text-sm"
                >{{ file.name }}</span
              >
            </Tooltip>
            <p class="text-muted-foreground m-0 text-sm">{{ file.meta }}</p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button
              v-if="file.previewable"
              type="button"
              class="reference-action"
              :aria-label="`预览 ${file.name}`"
              @click="openPreview(file.key)"
            >
              预览
            </button>
            <a
              v-else-if="file.kind === 'link' && file.url"
              :href="file.url"
              target="_blank"
              rel="noopener noreferrer"
              class="reference-action"
              :aria-label="`打开链接 ${file.name}`"
              >打开</a
            >
            <button
              v-if="file.downloadUrl && file.kind !== 'link'"
              type="button"
              class="reference-action"
              :aria-label="`下载 ${file.name}`"
              @click="downloadFileByUrl(file.downloadUrl, file.name)"
            >
              下载
            </button>
          </div>
        </li>
      </ul>
      <Empty
        v-else
        :image="Empty.PRESENTED_IMAGE_SIMPLE"
        description="暂无参考资料"
      />
    </template>
    <MediaPreview
      v-if="previewOpen"
      v-model:open="previewOpen"
      v-model:current-index="previewIndex"
      :items="previewItems"
      :z-index="previewZIndex"
    />
  </div>
</template>

<style scoped>
.reference-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr));
  gap: 12px;
}

.reference-action,
.attachment-action {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  font-size: 14px;
  color: inherit;
  white-space: nowrap;
  cursor: pointer;
}

.reference-action {
  color: hsl(var(--primary));
}

.reference-action:hover,
.attachment-action:hover {
  text-decoration: underline;
}

.reference-action:focus-visible,
.reference-name:focus-visible,
.attachment-thumbnail:focus-visible {
  outline: 2px solid hsl(var(--ring));
  outline-offset: 2px;
  border-radius: 2px;
}

.attachment-action:focus-visible {
  outline: 2px solid hsl(var(--background));
  outline-offset: 2px;
  border-radius: 2px;
}
</style>
