import { computed, onMounted, onUnmounted, ref } from 'vue';

type DesktopNotificationPermission = NotificationPermission | 'unsupported';

interface DesktopSiteNotification {
  id: string;
  message: string;
  onClick: () => Promise<void> | void;
  title: string;
}

function getDesktopNotificationPermission(): DesktopNotificationPermission {
  if (
    typeof window === 'undefined' ||
    !window.isSecureContext ||
    !('Notification' in window)
  ) {
    return 'unsupported';
  }

  return window.Notification.permission;
}

/**
 * 管理后台标签页的系统桌面通知，并在权限不可用时降级为标题提醒。
 *
 * @remarks
 * 浏览器要求通知权限必须由用户主动操作触发，因此授权入口由调用方负责展示。
 */
export function useDesktopSiteNotifications() {
  const permission = ref<DesktopNotificationPermission>(
    getDesktopNotificationPermission(),
  );
  const isPageHidden = ref(false);
  const activeNotifications = new Set<Notification>();
  let titleBeforeAttention: string | undefined;

  const canRequestPermission = computed(() => permission.value === 'default');

  function restoreDocumentTitle() {
    if (titleBeforeAttention === undefined) return;
    document.title = titleBeforeAttention;
    titleBeforeAttention = undefined;
  }

  function closeActiveNotifications() {
    activeNotifications.forEach((notification) => notification.close());
    activeNotifications.clear();
  }

  function markDocumentTitleForAttention() {
    if (titleBeforeAttention === undefined) {
      titleBeforeAttention = document.title;
    }
    document.title = `[新消息] ${titleBeforeAttention}`;
  }

  function handleVisibilityChange() {
    isPageHidden.value = document.visibilityState === 'hidden';
    if (isPageHidden.value) return;

    restoreDocumentTitle();
    closeActiveNotifications();
  }

  async function requestPermission(): Promise<DesktopNotificationPermission> {
    if (!canRequestPermission.value) return permission.value;

    try {
      permission.value = await window.Notification.requestPermission();
    } catch {
      permission.value = 'unsupported';
    }
    return permission.value;
  }

  function showNotification(payload: DesktopSiteNotification) {
    if (!isPageHidden.value) return false;
    if (permission.value !== 'granted') {
      markDocumentTitleForAttention();
      return false;
    }

    try {
      const desktopNotification = new window.Notification(payload.title, {
        body: payload.message,
        icon: '/favicon.png',
        tag: `site-notification-${payload.id}`,
      });
      activeNotifications.add(desktopNotification);
      desktopNotification.onclose = () => {
        activeNotifications.delete(desktopNotification);
      };
      desktopNotification.onclick = () => {
        window.focus();
        desktopNotification.close();
        void payload.onClick();
      };
      return true;
    } catch {
      // 系统策略仍可能阻止通知构造，此时保留标题提醒，避免消息静默丢失。
      markDocumentTitleForAttention();
      return false;
    }
  }

  onMounted(() => {
    permission.value = getDesktopNotificationPermission();
    handleVisibilityChange();
    document.addEventListener('visibilitychange', handleVisibilityChange);
  });

  onUnmounted(() => {
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    restoreDocumentTitle();
    closeActiveNotifications();
  });

  return {
    canRequestPermission,
    requestPermission,
    showNotification,
  };
}
