<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

interface PreviewItem {
  filetype?: string;
  url?: string;
}

const props = defineProps<{
  autoplay?: boolean;
  currentIndex?: number;
  filetype?: string;
  items?: PreviewItem[];
  open: boolean;
  url?: string;
  zIndex?: number;
}>();

const emit = defineEmits<{
  'update:currentIndex': [value: number];
  'update:open': [value: boolean];
}>();

const activeIndex = computed(() => {
  const count = props.items?.length ?? 0;
  if (count === 0) return 0;
  return Math.min(Math.max(props.currentIndex ?? 0, 0), count - 1);
});

const activeItem = computed<PreviewItem>(() => {
  return (
    props.items?.[activeIndex.value] ?? {
      filetype: props.filetype,
      url: props.url,
    }
  );
});

const canSwitch = computed(() => (props.items?.length ?? 0) > 1);
const itemCount = computed(() => props.items?.length ?? 0);
const activeFiletype = computed(
  () => activeItem.value.filetype ?? props.filetype,
);
const activeUrl = computed(() => activeItem.value.url ?? props.url);
const mediaLoading = ref(false);
const mediaFailed = ref(false);

watch(
  () => [props.open, activeUrl.value] as const,
  ([open]) => {
    mediaLoading.value = open;
    mediaFailed.value = false;
  },
  { immediate: true },
);

function loaded() {
  mediaLoading.value = false;
}

function failed() {
  mediaLoading.value = false;
  mediaFailed.value = true;
}

function close() {
  emit('update:open', false);
}

function switchItem(offset: number) {
  const count = props.items?.length ?? 0;
  if (count <= 1) return;
  emit('update:currentIndex', (activeIndex.value + offset + count) % count);
}

function handleKeydown(event: KeyboardEvent) {
  if (!props.open) return;
  if (event.key === 'ArrowLeft') {
    event.preventDefault();
    switchItem(-1);
  } else if (event.key === 'ArrowRight') {
    event.preventDefault();
    switchItem(1);
  } else if (event.key === 'Escape') {
    close();
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown);
});
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="bg-overlay fixed inset-0 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="媒体预览"
      :style="{ zIndex: zIndex ?? 50 }"
      @click.self="close"
    >
      <div class="relative max-h-[90vh] max-w-[90vw]">
        <button
          class="absolute -right-3 -top-3 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-white text-gray-700 shadow hover:bg-gray-100"
          aria-label="关闭媒体预览"
          @click="close"
        >
          <span class="icon-[ant-design--close-outlined] text-sm" />
        </button>
        <video
          v-if="activeFiletype === 'video' || activeFiletype === 'mp4'"
          :autoplay="props.autoplay ?? true"
          :key="activeUrl"
          :src="activeUrl"
          controls
          playsinline
          preload="metadata"
          @loadeddata="loaded"
          @error="failed"
          class="max-h-[70vh] min-h-[180px] min-w-[320px] max-w-[85vw] rounded"
        />
        <img
          v-else
          alt="媒体预览"
          :src="activeUrl"
          @load="loaded"
          @error="failed"
          class="max-h-[70vh] min-h-[200px] min-w-[200px] max-w-[85vw] rounded object-contain"
        />
        <p
          v-if="mediaLoading"
          role="status"
          class="bg-background/90 text-foreground pointer-events-none absolute inset-0 flex items-center justify-center rounded text-sm"
        >
          正在加载预览…
        </p>
        <p
          v-if="mediaFailed"
          role="alert"
          class="bg-background text-foreground mt-3 rounded px-4 py-3 text-sm"
        >
          预览加载失败，请刷新页面后重试。
        </p>
        <div
          v-if="canSwitch"
          class="mx-auto mt-2 w-fit rounded-full bg-black/50 px-3 py-1 text-xs text-white"
        >
          {{ activeIndex + 1 }} / {{ itemCount }}
        </div>
      </div>
      <button
        v-if="canSwitch"
        class="fixed left-[10vw] top-1/2 z-10 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white shadow hover:bg-black/70"
        title="上一张"
        @click.stop="switchItem(-1)"
      >
        <span class="icon-[ant-design--left-outlined] text-2xl"></span>
      </button>
      <button
        v-if="canSwitch"
        class="fixed right-[10vw] top-1/2 z-10 flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-white shadow hover:bg-black/70"
        title="下一张"
        @click.stop="switchItem(1)"
      >
        <span class="icon-[ant-design--right-outlined] text-2xl"></span>
      </button>
    </div>
  </Teleport>
</template>
