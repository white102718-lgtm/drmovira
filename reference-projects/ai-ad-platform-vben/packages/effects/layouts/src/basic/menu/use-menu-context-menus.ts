import type { RouteLocationNormalized } from 'vue-router';

import type { IContextMenuItem } from '@vben-core/tabs-ui';

import { useRouter } from 'vue-router';

import { useContentMaximize, useTabs } from '@vben/hooks';
import {
  ArrowLeftToLine,
  ArrowRightLeft,
  ArrowRightToLine,
  ExternalLink,
  FoldHorizontal,
  Fullscreen,
  Minimize2,
  Pin,
  PinOff,
  RotateCw,
  X,
} from '@vben/icons';
import { $t } from '@vben/locales';
import { useTabbarStore } from '@vben/stores';

export function useMenuContextMenus() {
  const router = useRouter();
  const tabbarStore = useTabbarStore();
  const { contentIsMaximize, toggleMaximize } = useContentMaximize();
  const {
    closeAllTabs,
    closeCurrentTab,
    closeLeftTabs,
    closeOtherTabs,
    closeRightTabs,
    getTabDisableState,
    openTabInNewWindow,
    refreshTab,
    toggleTabPin,
  } = useTabs();

  function createMenuContextMenus(data: {
    parentPaths: string[];
    path: string;
  }): IContextMenuItem[] {
    const { path } = data;

    // 在 tabbar 中查找对应的 tab
    const existingTab = tabbarStore.getTabs.find(
      (tab) => tab.path === path,
    ) as RouteLocationNormalized | undefined;

    // 如果没有打开的 tab，通过 router.resolve 获取路由信息作为后备
    const resolvedRoute = router.resolve({ path }) as RouteLocationNormalized;
    const tab = existingTab ?? resolvedRoute;

    const {
      disabledCloseAll,
      disabledCloseCurrent,
      disabledCloseLeft,
      disabledCloseOther,
      disabledCloseRight,
      disabledRefresh,
    } = getTabDisableState(tab);

    const affixTab = tab?.meta?.affixTab ?? false;

    // 如果该路径没有对应打开的 tab，关闭操作应禁用
    const disabledClose = disabledCloseCurrent || !existingTab;

    const menus: IContextMenuItem[] = [
      {
        handler: async () => {
          await openTabInNewWindow(tab);
        },
        icon: ExternalLink,
        key: 'open-in-new-window',
        text: $t('preferences.tabbar.contextMenu.openInNewWindow'),
      },
      {
        disabled: disabledClose,
        handler: async () => {
          await closeCurrentTab(tab);
        },
        icon: X,
        key: 'close',
        text: $t('preferences.tabbar.contextMenu.close'),
      },
      {
        handler: async () => {
          await toggleTabPin(tab);
        },
        icon: affixTab ? PinOff : Pin,
        key: 'affix',
        text: affixTab
          ? $t('preferences.tabbar.contextMenu.unpin')
          : $t('preferences.tabbar.contextMenu.pin'),
      },
      {
        handler: async () => {
          if (!contentIsMaximize.value) {
            await router.push(tab.fullPath ?? path);
          }
          toggleMaximize();
        },
        icon: contentIsMaximize.value ? Minimize2 : Fullscreen,
        key: contentIsMaximize.value ? 'restore-maximize' : 'maximize',
        text: contentIsMaximize.value
          ? $t('preferences.tabbar.contextMenu.restoreMaximize')
          : $t('preferences.tabbar.contextMenu.maximize'),
      },
      {
        disabled: disabledRefresh,
        handler: () => refreshTab(),
        icon: RotateCw,
        key: 'reload',
        separator: true,
        text: $t('preferences.tabbar.contextMenu.reload'),
      },
      {
        disabled: disabledCloseLeft,
        handler: async () => {
          await closeLeftTabs(tab);
        },
        icon: ArrowLeftToLine,
        key: 'close-left',
        text: $t('preferences.tabbar.contextMenu.closeLeft'),
      },
      {
        disabled: disabledCloseRight,
        handler: async () => {
          await closeRightTabs(tab);
        },
        icon: ArrowRightToLine,
        key: 'close-right',
        separator: true,
        text: $t('preferences.tabbar.contextMenu.closeRight'),
      },
      {
        disabled: disabledCloseOther,
        handler: async () => {
          await closeOtherTabs(tab);
        },
        icon: FoldHorizontal,
        key: 'close-other',
        text: $t('preferences.tabbar.contextMenu.closeOther'),
      },
      {
        disabled: disabledCloseAll,
        handler: closeAllTabs,
        icon: ArrowRightLeft,
        key: 'close-all',
        text: $t('preferences.tabbar.contextMenu.closeAll'),
      },
    ];

    const canToggleTabPin = tab?.meta?.tabClosable !== false;

    return menus.filter(
      (item) =>
        tabbarStore.getMenuList.includes(item.key) &&
        (item.key !== 'affix' || canToggleTabPin),
    );
  }

  return { createMenuContextMenus };
}
