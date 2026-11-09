import { watch, type Ref, type ComputedRef } from 'vue';
import { useRoute, useRouter } from 'vue-router';

interface UsePlatformFromRouteOptions {
  selectedPlatform: Ref<string | undefined>;
  onPlatformChange?: (platformId: string) => Promise<void> | void;
  platformInputRef?: Ref<string>;
  ensureOptionsLoaded?: (platformId: string) => Promise<void> | void;
  getPlatformList?: () => Promise<string[]> | string[];
  platformListRef?: Ref<string[]> | ComputedRef<string[]>;
  immediate?: boolean;
}

export function usePlatformFromRoute(options: UsePlatformFromRouteOptions) {
  const route = useRoute();
  const router = useRouter();

  // 设置默认 platform
  async function setDefaultPlatform() {
    const platformFromRoute = route.query.platform as string;
    if (platformFromRoute) {
      return;
    }

    let platformList: string[] = [];

    if (options.platformListRef) {
      platformList = options.platformListRef.value;
    } else if (options.getPlatformList) {
      const result = await options.getPlatformList();
      platformList = Array.isArray(result) ? result : [];
    }

    if (platformList.length > 0) {
      const firstPlatform = platformList[0];
      router.push({
        query: {
          ...route.query,
          platform: firstPlatform,
        },
      });
    }
  }

  // 监听平台列表变化
  if (options.platformListRef) {
    const stopWatch = watch(
      () => options.platformListRef!.value,
      async () => {
        if (options.platformListRef!.value.length > 0) {
          if (!route.query.platform) {
            await setDefaultPlatform();
          }
          stopWatch();
        }
      },
      { immediate: true },
    );
  } else if (options.getPlatformList) {
    (async () => {
      const platformList = await options.getPlatformList!();
      if (Array.isArray(platformList) && platformList.length > 0 && !route.query.platform) {
        await setDefaultPlatform();
      }
    })();
  }

  watch(
    () => route.query.platform,
    async (newPlatform) => {
      if (typeof newPlatform !== 'string' || !newPlatform) {
        // URL 中平台被清除时，同步重置组件状态
        if (options.selectedPlatform.value) {
          options.selectedPlatform.value = undefined;
          if (options.platformInputRef) {
            options.platformInputRef.value = '';
          }
          if (options.onPlatformChange) {
            await options.onPlatformChange('');
          }
        }
        return;
      }

      if (options.selectedPlatform.value === newPlatform) {
        return;
      }

      options.selectedPlatform.value = newPlatform;

      if (options.platformInputRef) {
        options.platformInputRef.value = newPlatform;
      }

      if (options.ensureOptionsLoaded) {
        await options.ensureOptionsLoaded(newPlatform);
      }

      if (options.onPlatformChange) {
        await options.onPlatformChange(newPlatform);
      }
    },
    { immediate: options.immediate ?? true },
  );
}


