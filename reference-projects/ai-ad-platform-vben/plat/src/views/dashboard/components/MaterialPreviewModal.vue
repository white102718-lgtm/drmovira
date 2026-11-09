<script setup lang="ts">
import { ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { Image } from 'ant-design-vue';

import { getMaterialUrlApi } from '#/api/materials/all';

const [VideoModal, videoModalApi] = useVbenModal({
  draggable: true,
  modal: true,
});

const videoUrl = ref<null | string>(null);
const isVideo = ref(false);
let abortController: AbortController | null = null;

// 预签名 URL 有效期 1 分钟,留 10s 边际;窗口内重开同一对象直接复用,浏览器也能命中媒体缓存
const URL_TTL_MS = 50_000;
const urlCache = new Map<string, { ts: number; url: string }>();

// 先弹出(videoUrl 为空展示加载中),URL 到位后再填充
const openModal = async (payload: {
  filename: string;
  filetype: string;
  name: string;
}) => {
  abortController?.abort();
  const controller = (abortController = new AbortController());

  const maxLength = 25;
  const displayName =
    payload.name.length > maxLength
      ? `${payload.name.slice(0, maxLength)}...`
      : payload.name;

  videoUrl.value = null;
  isVideo.value = payload.filetype === 'video';
  videoModalApi
    .setState({
      title: `${payload.filetype === 'video' ? '视频' : '图片'}预览 - ${displayName}`,
      fullscreenButton: false,
      footer: false,
      showCancelButton: false,
      showConfirmButton: false,
    })
    .open();

  const cached = urlCache.get(payload.filename);
  if (cached && Date.now() - cached.ts < URL_TTL_MS) {
    videoUrl.value = cached.url;
    return;
  }

  try {
    const response = await getMaterialUrlApi(
      payload.filename,
      controller.signal,
    );
    if (controller.signal.aborted) return;
    urlCache.set(payload.filename, { ts: Date.now(), url: response.url });
    videoUrl.value = response.url;
  } catch {}
};

defineExpose({ openModal });
</script>

<template>
  <VideoModal>
    <div v-if="videoUrl" class="flex justify-center">
      <video
        v-if="isVideo"
        :src="videoUrl"
        controls
        autoplay
        style="width: auto; min-width: 100%; height: auto; max-height: 68vh"
      ></video>
      <Image
        v-else
        :src="videoUrl"
        :preview="{ src: videoUrl }"
        alt="Material Preview"
        style="
          width: auto;
          min-width: 100%;
          height: auto;
          max-height: 68vh;
          object-fit: contain;
        "
      />
    </div>
    <div v-else class="flex items-center justify-center py-8">
      <div class="text-center">
        <div
          class="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600"
        ></div>
        <p class="text-gray-500">加载中...</p>
      </div>
    </div>
  </VideoModal>
</template>
