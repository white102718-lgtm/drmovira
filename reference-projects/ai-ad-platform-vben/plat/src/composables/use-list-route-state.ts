import type { LocationQuery, LocationQueryRaw } from 'vue-router';

import { nextTick, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import type {
  ListRouteFieldOptions,
  ListRoutePaginationOptions,
  ListRouteState,
} from './list-route-state';

import {
  normalizeLocationQuery,
  parseListRouteState,
  serializeListRouteState,
} from './list-route-state';

interface MutableRef<T> {
  value: T;
}

type MutableRefRecord = Record<string, MutableRef<unknown>>;
type UnwrapMutableRefs<T extends MutableRefRecord> = {
  [K in keyof T]: T[K]['value'];
};

export interface UseListRouteStateOptions<T extends ListRouteState> {
  /** 默认仅对菜单可见页面启用；可用于页面级附加限制。 */
  enabled?: () => boolean;
  fields?: { [K in keyof T]?: ListRouteFieldOptions<T[K]> };
  onRouteStateRestored?: () => Promise<void> | void;
  pagination?: ListRoutePaginationOptions & {
    enabled?: () => boolean;
    page: MutableRef<number>;
    pageSize: MutableRef<number>;
  };
  scope?: string;
  state: T;
}

export interface CommitListQueryStateOptions {
  resetPage?: boolean;
}

function cloneState<T extends ListRouteState>(state: T): T {
  return Object.fromEntries(
    Object.entries(state).map(([key, value]) => [
      key,
      Array.isArray(value)
        ? [...value]
        : value && typeof value === 'object'
          ? { ...value }
          : value,
    ]),
  ) as T;
}

/** 将分散的 ref/toRef 组合成可供列表 URL 同步使用的状态对象。 */
export function createListRouteStateTarget<T extends MutableRefRecord>(
  sources: T,
): UnwrapMutableRefs<T> {
  return new Proxy({} as UnwrapMutableRefs<T>, {
    get(_target, key) {
      return typeof key === 'string' ? sources[key]?.value : undefined;
    },
    getOwnPropertyDescriptor(_target, key) {
      return typeof key === 'string' && key in sources
        ? { configurable: true, enumerable: true }
        : undefined;
    },
    ownKeys() {
      return Object.keys(sources);
    },
    set(_target, key, value) {
      if (typeof key !== 'string' || !sources[key]) return false;
      sources[key].value = value;
      return true;
    },
  });
}

/**
 * 让列表最后一次实际查询状态与当前路由查询参数保持一致。
 *
 * @remarks
 * 页面应在真正发起查询前调用 commitQueryState；带搜索按钮的表单不要在输入阶段调用。
 */
export function useListRouteState<T extends ListRouteState>(
  options: UseListRouteStateOptions<T>,
) {
  const route = useRoute();
  const router = useRouter();
  const routePath = route.path;
  const defaults = cloneState(options.state);
  const isApplyingRoute = ref(false);

  function isEnabled() {
    return route.meta.hideInMenu !== true && (options.enabled?.() ?? true);
  }

  function isPaginationEnabled() {
    return Boolean(
      options.pagination && options.pagination.enabled?.() !== false,
    );
  }

  function parseRoute(query: LocationQuery = route.query) {
    return parseListRouteState({
      defaults,
      fields: options.fields,
      pagination: isPaginationEnabled() ? options.pagination : undefined,
      query,
      scope: options.scope,
    });
  }

  function buildQuery(): LocationQueryRaw {
    const query = serializeListRouteState({
      currentQuery: route.query,
      defaults,
      fields: options.fields,
      pagination: isPaginationEnabled() ? options.pagination : undefined,
      paginationState:
        isPaginationEnabled() && options.pagination
          ? {
              page: options.pagination.page.value,
              pageSize: options.pagination.pageSize.value,
            }
          : undefined,
      scope: options.scope,
      state: options.state,
    });
    if (options.pagination && !isPaginationEnabled()) {
      const prefix = options.scope ? `${options.scope}_` : '';
      delete query[`${prefix}${options.pagination.pageKey ?? 'page'}`];
      delete query[`${prefix}${options.pagination.pageSizeKey ?? 'page_size'}`];
    }
    return query;
  }

  async function replaceQueryIfNeeded(query: LocationQueryRaw) {
    if (normalizeLocationQuery(query) === normalizeLocationQuery(route.query)) {
      return;
    }
    await router.replace({ path: route.path, query });
  }

  async function commitQueryState(
    commitOptions: CommitListQueryStateOptions = {},
  ) {
    if (!isEnabled() || isApplyingRoute.value) return;
    if (
      commitOptions.resetPage &&
      options.pagination &&
      isPaginationEnabled()
    ) {
      options.pagination.page.value = 1;
    }
    await replaceQueryIfNeeded(buildQuery());
  }

  async function restoreFromRoute(
    query: LocationQuery = route.query,
    normalize = true,
  ) {
    if (!isEnabled()) return parseRoute(query);
    isApplyingRoute.value = true;
    try {
      const restored = parseRoute(query);
      Object.assign(options.state, restored.state);
      if (options.pagination && isPaginationEnabled() && restored.pagination) {
        options.pagination.page.value = restored.pagination.page;
        options.pagination.pageSize.value = restored.pagination.pageSize;
      }
      await nextTick();
      if (normalize) await replaceQueryIfNeeded(buildQuery());
      return restored;
    } finally {
      isApplyingRoute.value = false;
    }
  }

  async function resetQueryState() {
    isApplyingRoute.value = true;
    try {
      Object.assign(options.state, cloneState(defaults));
      if (options.pagination && isPaginationEnabled()) {
        options.pagination.page.value = 1;
        options.pagination.pageSize.value = options.pagination.defaultPageSize;
      }
      await nextTick();
    } finally {
      isApplyingRoute.value = false;
    }
    await commitQueryState();
  }

  const stopRouteSubscription = watch(
    () => [route.path, normalizeLocationQuery(route.query)] as const,
    async () => {
      // KeepAlive 页面离开后仍可能存活，只处理本列表自己的路由，避免污染其他页面 URL。
      if (route.path !== routePath || !isEnabled()) return;
      if (isApplyingRoute.value) return;
      const currentQuery = buildQuery();
      if (
        normalizeLocationQuery(currentQuery) ===
        normalizeLocationQuery(route.query)
      ) {
        return;
      }
      await restoreFromRoute(route.query, true);
      await options.onRouteStateRestored?.();
    },
    { flush: 'post' },
  );

  return {
    commitQueryState,
    isApplyingRoute,
    resetQueryState,
    restoreFromRoute,
    stopRouteSubscription,
  };
}
