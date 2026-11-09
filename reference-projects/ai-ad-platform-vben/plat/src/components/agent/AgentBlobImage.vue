<script lang="ts" setup>
import { computed, ref, watch } from 'vue';

import { Download, ZoomIn } from 'lucide-vue-next';

import { Image } from 'ant-design-vue';

import { fetchAttachment, rememberAgentDownloadCookie } from '#/api/agent';
import AgentDownloadLink from '#/components/agent/AgentDownloadLink.vue';
import { agentBlobHref } from '#/utils/download';

const props = defineProps<{ caption?: string; url: string }>();

const src = ref('');
const failed = ref('');
const previewing = ref(false);
const ready = ref(false);

const filename = computed(() => {
  const base = (props.caption || '成效图').replaceAll(/[/\\?%*:|"<>]/g, '_');
  return base.toLowerCase().endsWith('.png') ? base : `${base}.png`;
});

const preview = computed(() => ({
  onVisibleChange(visible: boolean) {
    previewing.value = visible;
  },
  src: src.value,
}));

async function load(url: string) {
  src.value = '';
  failed.value = '';
  ready.value = false;
  rememberAgentDownloadCookie();
  const href = agentBlobHref(url);
  try {
    await fetchAttachment(url);
    src.value = href;
    ready.value = true;
  } catch (error: any) {
    failed.value =
      error?.status === 404 ? '这张图已经过期了' : '图片加载失败，请重试';
  }
}

watch(() => props.url, load, { immediate: true });
</script>

<template>
  <figure class="relative m-0 max-w-full">
    <div v-if="src" class="relative">
      <Image
        :src="src"
        :alt="caption || '成效图'"
        :preview="preview"
        class="max-w-full overflow-hidden rounded-lg border border-slate-200"
      >
        <template #previewMask>
          <span class="flex items-center gap-1 text-sm">
            <ZoomIn class="h-4 w-4" />
            预览
          </span>
        </template>
      </Image>
      <AgentDownloadLink
        v-if="ready"
        class="absolute right-2 top-2 z-10 inline-flex items-center gap-1 rounded-md bg-white/90 px-2 py-1 text-xs text-slate-700 shadow-sm ring-1 ring-slate-200 hover:bg-white"
        :url="url"
        :filename="filename"
        @click.stop
      >
        <Download class="h-3.5 w-3.5" />
        下载
      </AgentDownloadLink>
    </div>
    <div
      v-else-if="failed"
      class="rounded-lg border border-dashed border-slate-300 px-3 py-6 text-center text-xs text-slate-400"
    >
      {{ failed }}
    </div>
    <div
      v-else
      class="h-40 w-full animate-pulse rounded-lg bg-slate-100"
      aria-label="加载图片"
    ></div>
    <figcaption v-if="caption" class="mt-1.5 text-xs text-slate-400">
      {{ caption }}
    </figcaption>
    <Teleport to="body">
      <AgentDownloadLink
        v-if="previewing && ready"
        class="fixed right-24 top-6 z-[1081] inline-flex items-center gap-1.5 rounded-full bg-black/55 px-3 py-1.5 text-sm text-white hover:bg-black/70"
        :url="url"
        :filename="filename"
      >
        <Download class="h-4 w-4" />
        下载
      </AgentDownloadLink>
    </Teleport>
  </figure>
</template>

<style scoped></style>
