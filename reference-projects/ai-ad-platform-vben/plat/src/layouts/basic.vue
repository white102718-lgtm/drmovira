<script lang="ts" setup>
import type { NotificationItem } from '@vben/layouts';

import type { SiteNotification } from '#/api/asset-flow';

import {
  computed,
  onBeforeMount,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { AuthenticationLoginExpiredModal, useVbenModal } from '@vben/common-ui';
import { useTabs, useWatermark } from '@vben/hooks';
import { ArrowLeft, RotateCw, UserRoundPen, X } from '@vben/icons';
import {
  BasicLayout,
  LockScreen,
  Notification,
  UserDropdown,
} from '@vben/layouts';
import { preferences } from '@vben/preferences';
import { useAccessStore, useTabbarStore, useUserStore } from '@vben/stores';

import Button from 'ant-design-vue/es/button';
import Drawer from 'ant-design-vue/es/drawer';
import Empty from 'ant-design-vue/es/empty';
import List, { ListItem } from 'ant-design-vue/es/list';
import message from 'ant-design-vue/es/message';
import Modal from 'ant-design-vue/es/modal';
import Tag from 'ant-design-vue/es/tag';
import Tooltip from 'ant-design-vue/es/tooltip';
import { LoaderCircle } from 'lucide-vue-next';

import { assetFlowApi } from '#/api/asset-flow';
import { useDesktopSiteNotifications } from '#/composables/use-desktop-site-notifications';
import { useSiteNotificationStream } from '#/composables/use-site-notification-stream';
import SiteNotificationToastStack from '#/layouts/components/SiteNotificationToastStack.vue';
import ThemeColorSwitcher from '#/components/ThemeColorSwitcher.vue';
import UiScaleSwitcher from '#/components/UiScaleSwitcher.vue';
import { useAuthStore } from '#/store/auth';
import LoginForm from '#/views/_core/authentication/login.vue';
import MfaRebindModalForm from '#/views/_core/authentication/mfa-rebind-modal.vue';

const tabbarStore = useTabbarStore();
const { setMenuList } = tabbarStore;
setMenuList([
  'close',
  'affix',
  'maximize',
  'reload',
  'open-in-new-window',
  'close-left',
  'close-right',
  'close-other',
  'close-all',
]);

type AppNotification = NotificationItem & SiteNotification;
const NOTIFICATION_PAGE_SIZE = 20;
const LOAD_MORE_THRESHOLD = 24;
const NOTIFICATION_TOAST_DURATION = 8_000;
const MAX_VISIBLE_NOTIFICATION_TOASTS = 3;
const DESKTOP_NOTIFICATION_PROMPT_KEY =
  'adpulse:desktop-notification-prompt-dismissed';

const notifications = ref<AppNotification[]>([]);
const notificationToasts = ref<AppNotification[]>([]);
const allMessagesOpen = ref(false);
const hasUnreadNotifications = ref(false);
const hasMoreNotifications = ref(true);
const notificationsLoading = ref(false);
const notificationPage = ref(0);
const notificationToastTimers = new Map<
  string,
  ReturnType<typeof setTimeout>
>();

const userStore = useUserStore();
const authStore = useAuthStore();
const accessStore = useAccessStore();
const { destroyWatermark, updateWatermark } = useWatermark();
const {
  canRequestPermission: canRequestDesktopNotificationPermission,
  requestPermission: requestDesktopNotificationPermission,
  showNotification: showDesktopNotification,
} = useDesktopSiteNotifications();
const showDot = computed(() => hasUnreadNotifications.value);

const router = useRouter();
const route = useRoute();
const { closeCurrentTab, refreshTab } = useTabs();

const explicitParentPaths: Record<string, string> = {
  '/createAdvertisement/automated-rule-config': '/AutomatedRules',
  '/data-report/alert-rules': '/data-report',
  '/data-report/drilldown': '/data-report',
  '/profile': '/home',
  '/requirement/create': '/requirement/pool',
};

const preferredParentPath = computed(() => {
  const activePath = route.meta.activePath;
  if (typeof activePath === 'string' && activePath !== route.path) {
    return activePath;
  }

  const parentPath = route.meta.parentPath;
  if (typeof parentPath === 'string' && parentPath !== route.path) {
    return parentPath;
  }

  return explicitParentPaths[route.path] ?? '';
});

const hasSafeHistoryBack = computed(() => {
  if (typeof window === 'undefined') return false;

  const backPath = window.history.state?.back;
  if (typeof backPath !== 'string' || !backPath) return false;

  try {
    const backUrl = new URL(backPath, window.location.origin);
    return (
      backUrl.origin === window.location.origin &&
      `${backUrl.pathname}${backUrl.search}${backUrl.hash}` !== route.fullPath
    );
  } catch {
    return false;
  }
});

async function handleBack() {
  if (preferredParentPath.value) {
    await router.push(preferredParentPath.value);
    return;
  }

  if (hasSafeHistoryBack.value) {
    router.back();
    return;
  }

  await router.push('/home');
}

async function handleCloseCurrentTab() {
  const closingRoute = router.currentRoute.value;
  const isOnlyOpenTab = tabbarStore.getTabs.length <= 1;

  if (isOnlyOpenTab) {
    if (closingRoute.path === '/home') return;

    // 最后一个业务标签不能直接清空；先回到首页，再移除当前业务标签，避免关闭按钮无响应。
    await router.replace('/home');
  }

  await closeCurrentTab(closingRoute);
}

const menus = computed(() => [
  {
    handler: () => router.push('/profile'),
    icon: UserRoundPen,
    text: '个人信息',
  },
]);

const [MfaRebindModal] = useVbenModal({
  connectedComponent: MfaRebindModalForm,
});

// 暂时隐藏更换验证器入口：当前后端未提供 /auth/mfa/setup、enable、disable 等换绑接口。
// 管理员重置MFA后，用户下次登录会自动进入重新绑定流程。
const bottomMenus = computed(() => []);

const avatar = computed(() => {
  return userStore.userInfo?.avatar ?? preferences.app.defaultAvatar;
});

async function handleLogout() {
  await authStore.logout(true);
}

/** 站内通知沿用接口时间值，仅规范化展示格式，避免暴露 ISO 分隔符和毫秒。 */
function formatNotificationDateTime(value: string) {
  return value
    .replace('T', ' ')
    .replace(/\.\d+(?=Z?$)/, '')
    .replace(/Z$/, '');
}

function mapNotification(item: SiteNotification): AppNotification {
  return {
    ...item,
    avatar: preferences.app.defaultAvatar,
    date: formatNotificationDateTime(item.createdAt),
    isRead: item.isRead === true || item.isRead === 1,
  };
}

function dismissNotificationToast(id: string) {
  const timer = notificationToastTimers.get(id);
  if (timer !== undefined) clearTimeout(timer);
  notificationToastTimers.delete(id);
  notificationToasts.value = notificationToasts.value.filter(
    (item) => item.id !== id,
  );
}

function clearNotificationToasts() {
  notificationToastTimers.forEach((timer) => clearTimeout(timer));
  notificationToastTimers.clear();
  notificationToasts.value = [];
}

function enqueueNotificationToast(notification: AppNotification) {
  dismissNotificationToast(notification.id);
  const nextItems = [notification, ...notificationToasts.value];
  const removedItems = nextItems.slice(MAX_VISIBLE_NOTIFICATION_TOASTS);
  notificationToasts.value = nextItems.slice(
    0,
    MAX_VISIBLE_NOTIFICATION_TOASTS,
  );
  removedItems.forEach((item) => dismissNotificationToast(item.id));
  notificationToastTimers.set(
    notification.id,
    setTimeout(
      () => dismissNotificationToast(notification.id),
      NOTIFICATION_TOAST_DURATION,
    ),
  );
}

function handleStreamNotification(item: SiteNotification) {
  const notification = mapNotification(item);
  hasUnreadNotifications.value = true;
  if (notificationPage.value > 0) {
    notifications.value = [
      notification,
      ...notifications.value.filter((current) => current.id !== item.id),
    ];
  }
  enqueueNotificationToast(notification);
  showDesktopNotification({
    id: notification.id,
    message: notification.message,
    onClick: () => handleNoticeRead(notification),
    title: notification.title,
  });
}

async function loadNotificationUnreadStatus() {
  try {
    const status = await assetFlowApi.notificationUnreadStatus();
    hasUnreadNotifications.value = status.hasUnread;
  } catch {
    // 通用拦截器已反馈错误；保留旧状态，避免临时网络故障让红点闪烁。
  }
}

async function loadNotifications(reset = false) {
  if (notificationsLoading.value) return;
  if (!reset && !hasMoreNotifications.value) return;

  const nextPage = reset ? 1 : notificationPage.value + 1;
  notificationsLoading.value = true;
  try {
    const result = await assetFlowApi.notifications({
      page: nextPage,
      pageSize: NOTIFICATION_PAGE_SIZE,
    });
    const nextItems = result.items.map((item) => mapNotification(item));

    if (reset) {
      notifications.value = nextItems;
    } else {
      const existingIds = new Set(notifications.value.map((item) => item.id));
      notifications.value.push(
        ...nextItems.filter((item) => !existingIds.has(item.id)),
      );
    }
    notificationPage.value = result.page;
    hasMoreNotifications.value = result.hasMore;
  } catch {
    // 请求异常已由 API 层提示，保留已加载页便于用户继续查看。
  } finally {
    notificationsLoading.value = false;
  }
}

async function handleNotificationOpen(open: boolean) {
  if (!open) return;
  promptForDesktopNotifications();
  await loadNotifications(true);
}

function hasDismissedDesktopNotificationPrompt() {
  try {
    return localStorage.getItem(DESKTOP_NOTIFICATION_PROMPT_KEY) === 'true';
  } catch {
    return false;
  }
}

function markDesktopNotificationPromptDismissed() {
  try {
    localStorage.setItem(DESKTOP_NOTIFICATION_PROMPT_KEY, 'true');
  } catch {
    // 浏览器禁用本地存储时，仅允许当前会话再次提示，不影响通知主流程。
  }
}

function promptForDesktopNotifications() {
  if (
    !canRequestDesktopNotificationPermission.value ||
    hasDismissedDesktopNotificationPrompt()
  ) {
    return;
  }

  Modal.confirm({
    cancelText: '暂不开启',
    content: '切换到其他标签页或最小化窗口后，也能及时看到审批等系统消息。',
    okText: '开启',
    title: '开启桌面通知',
    onCancel: markDesktopNotificationPromptDismissed,
    async onOk() {
      markDesktopNotificationPromptDismissed();
      const permission = await requestDesktopNotificationPermission();
      if (permission === 'denied') {
        message.warning('浏览器已阻止桌面通知，可在地址栏的网站设置中重新开启');
      } else if (permission === 'unsupported') {
        message.warning('当前浏览器环境不支持桌面通知，将使用标签页标题提醒');
      }
    },
  });
}

async function handleLoadMoreNotifications() {
  await loadNotifications();
}

async function handleNoticeClear() {
  await assetFlowApi.readAllNotifications();
  notifications.value = [];
  notificationPage.value = 0;
  hasMoreNotifications.value = false;
  hasUnreadNotifications.value = false;
  clearNotificationToasts();
}

async function handleMakeAll() {
  await assetFlowApi.readAllNotifications();
  notifications.value.forEach((item) => (item.isRead = true));
  hasUnreadNotifications.value = false;
  clearNotificationToasts();
}

async function handleNoticeRead(item: NotificationItem) {
  const notice = item as AppNotification;
  if (!notice.isRead) await assetFlowApi.readNotification(notice.id);
  notice.isRead = true;
  await loadNotificationUnreadStatus();
  if (notice.targetPath) await router.push(notice.targetPath);
}

async function handleToastView(item: {
  date: string;
  id: string;
  message: string;
  title: string;
}) {
  const notice = notificationToasts.value.find(
    (notification) => notification.id === item.id,
  );
  if (!notice) return;
  dismissNotificationToast(notice.id);
  await handleNoticeRead(notice);
}

async function handleViewAllMessages() {
  allMessagesOpen.value = true;
  if (notificationPage.value === 0) await loadNotifications(true);
}

function handleMessagesScroll(event: Event) {
  const target = event.currentTarget as HTMLElement;
  const remaining =
    target.scrollHeight - target.scrollTop - target.clientHeight;
  if (remaining <= LOAD_MORE_THRESHOLD) void loadNotifications();
}

useSiteNotificationStream({
  onConnectionRejected: loadNotificationUnreadStatus,
  onNotification: handleStreamNotification,
});

onMounted(() => void loadNotificationUnreadStatus());
onUnmounted(clearNotificationToasts);

function handleClickLogo() {}

watch(
  () => preferences.app.watermark,
  async (enable) => {
    if (enable) {
      await updateWatermark({
        content: `${userStore.userInfo?.full_name} - ${userStore.userInfo?.realName}`,
      });
    } else {
      destroyWatermark();
    }
  },
  {
    immediate: true,
  },
);

onBeforeMount(() => {
  if (preferences.app.watermark) {
    destroyWatermark();
  }
});
</script>

<template>
  <a
    href="#__vben_main_content"
    class="bg-background text-foreground focus:ring-ring sr-only fixed left-4 top-4 z-[1000] rounded-md px-4 py-3 font-medium shadow-lg focus:not-sr-only focus:outline-none focus:ring-2"
  >
    跳到主内容
  </a>
  <BasicLayout
    class="adpulse-app-layout"
    @clear-preferences-and-logout="handleLogout"
    @click-logo="handleClickLogo"
  >
    <template #header-left-10>
      <div class="flex items-center gap-1">
        <Tooltip title="返回上一级">
          <Button
            type="text"
            aria-label="返回上一级"
            class="layout-utility-button flex items-center justify-center p-0 text-slate-600"
            @click="handleBack"
          >
            <ArrowLeft class="size-4" aria-hidden="true" />
          </Button>
        </Tooltip>
        <Tooltip title="刷新当前页面">
          <Button
            type="text"
            aria-label="刷新当前页面"
            class="layout-utility-button flex items-center justify-center p-0 text-slate-600"
            @click="() => refreshTab()"
          >
            <RotateCw class="size-4" aria-hidden="true" />
          </Button>
        </Tooltip>
        <Tooltip title="关闭当前标签页">
          <Button
            type="text"
            aria-label="关闭当前标签页"
            class="layout-utility-button flex items-center justify-center p-0 text-slate-600"
            @click="handleCloseCurrentTab"
          >
            <X class="size-4" aria-hidden="true" />
          </Button>
        </Tooltip>
      </div>
    </template>
    <template #user-dropdown>
      <UserDropdown
        :avatar
        :bottom-menus="bottomMenus"
        :menus
        :text="userStore.userInfo?.full_name"
        :description="userStore.userInfo?.realName"
        :tag-text="userStore.userInfo?.roles?.join(', ')"
        trigger="both"
        @logout="handleLogout"
      />
    </template>
    <template #header-right-55>
      <ThemeColorSwitcher />
    </template>
    <template #header-right-54>
      <UiScaleSwitcher />
    </template>
    <template #notification>
      <div class="layout-notification flex h-full items-center">
        <Notification
          :dot="showDot"
          :has-more="hasMoreNotifications"
          :loading="notificationsLoading"
          :notifications="notifications"
          @clear="handleNoticeClear"
          @load-more="handleLoadMoreNotifications"
          @make-all="handleMakeAll"
          @open-change="handleNotificationOpen"
          @read="handleNoticeRead"
          @view-all="handleViewAllMessages"
        />
      </div>
    </template>
    <template #extra>
      <SiteNotificationToastStack
        :items="notificationToasts"
        @close="dismissNotificationToast"
        @view="handleToastView"
      />
      <Drawer
        v-model:open="allMessagesOpen"
        title="全部消息"
        width="min(520px, 100vw)"
      >
        <div
          :aria-busy="notificationsLoading"
          class="max-h-[72dvh] overflow-y-auto"
          @scroll.passive="handleMessagesScroll"
        >
          <div
            v-if="notificationsLoading && notifications.length === 0"
            class="flex min-h-40 items-center justify-center"
            role="status"
            aria-label="正在加载通知"
          >
            <LoaderCircle
              aria-hidden="true"
              class="size-5 animate-spin motion-reduce:animate-none"
            />
          </div>
          <Empty
            v-else-if="notifications.length === 0"
            description="暂无消息"
          />
          <List v-else :data-source="notifications">
            <template #renderItem="{ item }">
              <ListItem
                class="cursor-pointer"
                role="button"
                tabindex="0"
                @click="handleNoticeRead(item)"
                @keydown.enter="handleNoticeRead(item)"
                @keydown.space.prevent="handleNoticeRead(item)"
              >
                <div class="w-full">
                  <div class="flex items-center justify-between gap-3">
                    <strong>{{ item.title }}</strong>
                    <Tag :color="item.isRead ? 'default' : 'blue'">
                      {{ item.isRead ? '已读' : '未读' }}
                    </Tag>
                  </div>
                  <p class="mb-0 mt-2 text-sm text-slate-600">
                    {{ item.message }}
                  </p>
                  <p class="mb-0 mt-1 text-xs text-slate-400">
                    {{ item.date }}
                  </p>
                </div>
              </ListItem>
            </template>
          </List>
          <div
            v-if="notificationsLoading && notifications.length > 0"
            class="flex min-h-12 items-center justify-center"
            role="status"
            aria-label="正在加载更多通知"
          >
            <LoaderCircle
              aria-hidden="true"
              class="size-4 animate-spin motion-reduce:animate-none"
            />
          </div>
          <p
            v-else-if="notifications.length > 0 && !hasMoreNotifications"
            class="mb-0 py-3 text-center text-xs text-slate-400"
          >
            没有更多消息了
          </p>
        </div>
      </Drawer>
      <MfaRebindModal />
      <AuthenticationLoginExpiredModal
        v-model:open="accessStore.loginExpired"
        :avatar
      >
        <LoginForm />
      </AuthenticationLoginExpiredModal>
    </template>
    <template #lock-screen>
      <LockScreen :avatar @to-login="handleLogout" />
    </template>
  </BasicLayout>
</template>
