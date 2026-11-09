<script lang="ts" setup>
import type { NotificationItem } from './types';

import { watch } from 'vue';

import { Bell, LoaderCircle, MailCheck } from '@vben/icons';
import { $t } from '@vben/locales';

import {
  VbenButton,
  VbenIconButton,
  VbenPopover,
  VbenScrollbar,
} from '@vben-core/shadcn-ui';

import { useToggle } from '@vueuse/core';

interface Props {
  /**
   * 显示圆点
   */
  dot?: boolean;
  /** 是否正在加载消息列表。 */
  loading?: boolean;
  /** 是否还有下一页消息。 */
  hasMore?: boolean;
  /**
   * 消息列表
   */
  notifications?: NotificationItem[];
}

defineOptions({ name: 'NotificationPopup' });

const props = withDefaults(defineProps<Props>(), {
  dot: false,
  hasMore: false,
  loading: false,
  notifications: () => [],
});

const emit = defineEmits<{
  clear: [];
  loadMore: [];
  makeAll: [];
  openChange: [boolean];
  read: [NotificationItem];
  viewAll: [];
}>();

const [open, toggle] = useToggle();

function close() {
  open.value = false;
}

function handleViewAll() {
  emit('viewAll');
  close();
}

function handleMakeAll() {
  emit('makeAll');
}

function handleClear() {
  emit('clear');
}

function handleClick(item: NotificationItem) {
  emit('read', item);
}

function handleScrollAt(state: { bottom: boolean }) {
  if (state.bottom && props.hasMore && !props.loading) {
    emit('loadMore');
  }
}

watch(open, (value) => emit('openChange', value));
</script>
<template>
  <VbenPopover
    v-model:open="open"
    content-class="relative right-2 w-[360px] p-0"
  >
    <template #trigger>
      <div class="flex-center mr-2 h-full" @click.stop="toggle()">
        <VbenIconButton
          :aria-label="$t('ui.widgets.openNotifications')"
          :aria-expanded="open"
          class="bell-button text-foreground relative"
          :tooltip="$t('ui.widgets.openNotifications')"
        >
          <span
            v-if="dot"
            class="bg-primary absolute right-0.5 top-0.5 h-2 w-2 rounded"
          ></span>
          <Bell class="size-4" />
        </VbenIconButton>
      </div>
    </template>

    <div class="relative">
      <div class="flex items-center justify-between p-4 py-3">
        <div class="text-foreground">{{ $t('ui.widgets.notifications') }}</div>
        <VbenIconButton
          :disabled="notifications.length <= 0 || loading"
          :tooltip="$t('ui.widgets.markAllAsRead')"
          @click="handleMakeAll"
        >
          <MailCheck class="size-4" />
        </VbenIconButton>
      </div>
      <VbenScrollbar
        v-if="notifications.length > 0 || loading"
        @scroll-at="handleScrollAt"
      >
        <ul
          :aria-busy="loading"
          class="!flex max-h-[360px] min-h-[96px] w-full flex-col"
        >
          <template v-for="item in notifications" :key="item.id ?? item.title">
            <li
              class="hover:bg-accent border-border relative flex w-full cursor-pointer items-start gap-5 border-t px-3 py-3"
              role="button"
              tabindex="0"
              @click="handleClick(item)"
              @keydown.enter="handleClick(item)"
              @keydown.space.prevent="handleClick(item)"
            >
              <span
                v-if="!item.isRead"
                class="bg-primary absolute right-2 top-2 h-2 w-2 rounded"
              ></span>

              <span
                class="relative flex h-10 w-10 shrink-0 overflow-hidden rounded-full"
              >
                <img
                  :src="item.avatar"
                  class="aspect-square h-full w-full object-cover"
                  alt=""
                />
              </span>
              <div class="flex flex-col gap-1 leading-none">
                <p class="font-semibold">{{ item.title }}</p>
                <p class="text-muted-foreground my-1 line-clamp-2 text-xs">
                  {{ item.message }}
                </p>
                <p class="text-muted-foreground line-clamp-2 text-xs">
                  {{ item.date }}
                </p>
              </div>
            </li>
          </template>
          <li
            v-if="loading"
            :aria-label="$t('ui.widgets.loadingNotifications')"
            class="text-muted-foreground flex-center min-h-12 border-t"
            role="status"
          >
            <LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
          </li>
          <li
            v-else-if="notifications.length > 0 && !hasMore"
            class="text-muted-foreground flex-center min-h-10 border-t text-xs"
          >
            {{ $t('ui.widgets.noMoreNotifications') }}
          </li>
        </ul>
      </VbenScrollbar>

      <template v-else>
        <div class="flex-center text-muted-foreground min-h-[150px] w-full">
          {{ $t('common.noData') }}
        </div>
      </template>

      <div
        class="border-border flex items-center justify-between border-t px-4 py-3"
      >
        <VbenButton
          :disabled="notifications.length <= 0 || loading"
          size="sm"
          variant="ghost"
          @click="handleClear"
        >
          {{ $t('ui.widgets.clearNotifications') }}
        </VbenButton>
        <VbenButton size="sm" @click="handleViewAll">
          {{ $t('ui.widgets.viewAll') }}
        </VbenButton>
      </div>
    </div>
  </VbenPopover>
</template>

<style scoped>
:deep(.bell-button) {
  &:hover {
    svg {
      animation: bell-ring 1s both;
    }
  }
}

@keyframes bell-ring {
  0%,
  100% {
    transform-origin: top;
  }

  15% {
    transform: rotateZ(10deg);
  }

  30% {
    transform: rotateZ(-10deg);
  }

  45% {
    transform: rotateZ(5deg);
  }

  60% {
    transform: rotateZ(-5deg);
  }

  75% {
    transform: rotateZ(2deg);
  }
}
</style>
