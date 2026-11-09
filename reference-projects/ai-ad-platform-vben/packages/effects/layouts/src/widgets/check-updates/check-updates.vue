<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';

import { $t } from '@vben/locales';
import { Info } from '@vben/icons';

interface Props {
  // 检查更新的地址
  checkUpdateUrl?: string;
}

defineOptions({ name: 'CheckUpdates', inheritAttrs: false });

const props = withDefaults(defineProps<Props>(), {
  checkUpdateUrl: import.meta.env.BASE_URL || '/',
});

const NOTICE_DATE_KEY = 'check_update_notice_date';
const POLL_INTERVAL = 10 * 60 * 1000;

const lastVersionTag = ref('');
const hasUpdate = ref(false);
const pollTimer = ref<ReturnType<typeof setTimeout>>();
const noticeTimer = ref<ReturnType<typeof setTimeout>>();
const showNotice = ref(false);
let isChecking = false;
let nextNoticeTime = 0;

function getMsUntilMidnight() {
  const now = new Date();
  const midnight = new Date(now);
  midnight.setHours(24, 0, 0, 0);
  return midnight.getTime() - now.getTime();
}

function hasShownToday() {
  return localStorage.getItem(NOTICE_DATE_KEY) === new Date().toDateString();
}

function markShownToday() {
  localStorage.setItem(NOTICE_DATE_KEY, new Date().toDateString());
}

async function getVersionTag() {
  try {
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') return null;
    const res = await fetch(props.checkUpdateUrl, { cache: 'no-cache', method: 'HEAD', redirect: 'manual' });
    return res.headers.get('etag') || res.headers.get('last-modified');
  } catch {
    return null;
  }
}

function handleCancel() {
  showNotice.value = false;
  hasUpdate.value = false;
}

function handleConfirm() {
  showNotice.value = false;
  window.location.reload();
}

// 每10分钟轮询版本变化，仅记录标记
async function pollVersion() {
  if (isChecking) return;
  isChecking = true;
  try {
    const versionTag = await getVersionTag();
    if (versionTag && lastVersionTag.value && versionTag !== lastVersionTag.value) {
      hasUpdate.value = true;
      lastVersionTag.value = versionTag;
    }
  } finally {
    isChecking = false;
    clearTimeout(pollTimer.value);
    pollTimer.value = setTimeout(pollVersion, POLL_INTERVAL);
  }
}

// 精确等到 0 点，有更新则弹出
function checkAtMidnight() {
  clearTimeout(noticeTimer.value);
  if (!hasShownToday() && hasUpdate.value) {
    markShownToday();
    showNotice.value = true;
  }
  const ms = getMsUntilMidnight();
  nextNoticeTime = Date.now() + ms;
  noticeTimer.value = setTimeout(checkAtMidnight, ms);
}

// 切回标签页：补触发版本轮询 + 检查是否错过了 0 点
function onVisibilityChange() {
  if (document.visibilityState !== 'visible') return;
  pollVersion();
  if (Date.now() >= nextNoticeTime) checkAtMidnight();
}

onMounted(async () => {
  const tag = await getVersionTag();
  if (tag) lastVersionTag.value = tag;
  pollTimer.value = setTimeout(pollVersion, POLL_INTERVAL);
  const ms = getMsUntilMidnight();
  nextNoticeTime = Date.now() + ms;
  noticeTimer.value = setTimeout(checkAtMidnight, ms);
  document.addEventListener('visibilitychange', onVisibilityChange);
});

onUnmounted(() => {
  clearTimeout(pollTimer.value);
  clearTimeout(noticeTimer.value);
  document.removeEventListener('visibilitychange', onVisibilityChange);
});
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="translate-y-4 opacity-0"
      enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="translate-y-0 opacity-100"
      leave-to-class="translate-y-4 opacity-0"
    >
      <div
        v-if="showNotice"
        class="fixed bottom-6 right-6 z-[9999] w-80 rounded-lg border border-border bg-background shadow-lg"
      >
        <div class="flex gap-2 p-4">
          <Info class="mt-0.5 size-5 shrink-0 text-primary" />
          <div>
            <p class="text-sm font-medium text-foreground">
              {{ $t('ui.widgets.checkUpdatesTitle') }}
            </p>
            <p class="mt-1 text-sm text-muted-foreground">
              {{ $t('ui.widgets.checkUpdatesDescription') }}
            </p>
          </div>
        </div>
        <div class="flex justify-end gap-2 px-4 pb-3">
          <button
            class="rounded-md px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            @click="handleCancel"
          >
            {{ $t('ui.widgets.checkUpdatesLater') }}
          </button>
          <button
            class="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            @click="handleConfirm"
          >
            {{ $t('common.refresh') }}
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
