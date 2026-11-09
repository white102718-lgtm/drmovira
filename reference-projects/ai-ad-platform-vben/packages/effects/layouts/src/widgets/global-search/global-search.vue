<script setup lang="ts">
import type { MenuRecordRaw } from '@vben/types';

import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { Search, SearchX } from '@vben/icons';
import { $t } from '@vben/locales';
import { isWindowsOs } from '@vben/utils';

import { useMagicKeys, whenever } from '@vueuse/core';

defineOptions({
  name: 'GlobalSearch',
});

const props = withDefaults(
  defineProps<{ enableShortcutKey?: boolean; menus?: MenuRecordRaw[] }>(),
  {
    enableShortcutKey: true,
    menus: () => [],
  },
);

const keyword = ref('');
const searchInputRef = ref<HTMLInputElement>();
const router = useRouter();

function flattenMenus(items: MenuRecordRaw[], result: MenuRecordRaw[] = []) {
  for (const item of items) {
    if (item.path) result.push(item);
    if (item.children?.length) flattenMenus(item.children, result);
  }
  return result;
}

const searchResults = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase();
  if (!query) return [];
  return flattenMenus(props.menus)
    .filter((item) =>
      $t(String(item.name ?? ''))
        .toLocaleLowerCase()
        .includes(query),
    )
    .slice(0, 8);
});

async function navigate(item: MenuRecordRaw) {
  keyword.value = '';
  if (/^https?:\/\//.test(item.path)) {
    window.open(item.path, '_blank', 'noopener,noreferrer');
    return;
  }
  await router.push(item.path);
}

function handleEnter() {
  const first = searchResults.value[0];
  if (first) void navigate(first);
}

const keys = useMagicKeys();
const cmd = isWindowsOs() ? keys['ctrl+k'] : keys['cmd+k'];
whenever(cmd!, () => {
  if (props.enableShortcutKey) {
    searchInputRef.value?.focus();
  }
});

const preventDefaultBrowserSearchHotKey = (event: KeyboardEvent) => {
  if (event.key?.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
  }
};

const toggleKeydownListener = () => {
  if (props.enableShortcutKey) {
    window.addEventListener('keydown', preventDefaultBrowserSearchHotKey);
  } else {
    window.removeEventListener('keydown', preventDefaultBrowserSearchHotKey);
  }
};

watch(() => props.enableShortcutKey, toggleKeydownListener);

onMounted(() => {
  toggleKeydownListener();

  onUnmounted(() => {
    window.removeEventListener('keydown', preventDefaultBrowserSearchHotKey);
  });
});
</script>

<template>
  <div class="relative">
    <label
      class="bg-accent/70 focus-within:ring-primary flex h-9 items-center gap-2 rounded-lg px-2 focus-within:ring-2"
    >
      <Search class="text-muted-foreground size-4 shrink-0" />
      <input
        ref="searchInputRef"
        v-model="keyword"
        :placeholder="$t('ui.widgets.search.title')"
        class="placeholder:text-muted-foreground min-w-0 flex-1 appearance-none border-0 bg-transparent text-xs outline-none focus:shadow-none focus:!outline-none focus:!ring-0 [&::-webkit-search-cancel-button]:appearance-none [&::-webkit-search-decoration]:appearance-none"
        type="search"
        @keydown.enter.prevent="handleEnter"
      />
      <kbd
        v-if="enableShortcutKey"
        class="text-muted-foreground hidden text-[10px] md:block"
      >
        <span>{{ isWindowsOs() ? 'Ctrl K' : '⌘ K' }}</span>
      </kbd>
    </label>
    <div
      v-if="keyword"
      class="bg-popover border-border absolute inset-x-0 top-11 z-50 max-h-80 overflow-y-auto rounded-lg border p-1 shadow-lg"
    >
      <button
        v-for="item in searchResults"
        :key="item.path"
        class="hover:bg-accent flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-xs"
        type="button"
        @click="navigate(item)"
      >
        <span class="min-w-0 flex-1 truncate">
          {{ $t(String(item.name ?? item.path)) }}
        </span>
      </button>
      <div
        v-if="searchResults.length === 0"
        class="text-muted-foreground flex items-center gap-2 px-3 py-4 text-xs"
      >
        <SearchX class="size-4" />没有匹配的页面
      </div>
    </div>
  </div>
</template>
