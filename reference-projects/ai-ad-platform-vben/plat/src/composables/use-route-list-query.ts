import type { Ref } from 'vue';
import type {
  LocationQuery,
  LocationQueryRaw,
  LocationQueryValue,
  LocationQueryValueRaw,
  RouteLocationNormalizedLoaded,
  Router,
} from 'vue-router';

import { nextTick, onBeforeUnmount, ref, watch } from 'vue';

type QueryInput = LocationQueryValue | LocationQueryValue[];
type QueryOutput = LocationQueryValueRaw | LocationQueryValueRaw[];

interface RouteListQueryField {
  debounceMs: number;
  parse: (value: QueryInput | undefined) => unknown;
  read: () => unknown;
  serialize: (value: unknown) => QueryOutput | undefined;
  write: (value: unknown) => void;
}

interface RouteListQueryOptions {
  fields: Record<string, RouteListQueryField>;
  onRouteApplied?: () => void;
  route: RouteLocationNormalizedLoaded;
  router: Router;
}

interface RouteQueryFieldOptions<T> {
  debounceMs?: number;
  defaultValue: T;
  parse: (value: QueryInput | undefined, defaultValue: T) => T;
  serialize: (value: T, defaultValue: T) => QueryOutput | undefined;
}

export function readRouteQueryText(value: QueryInput | undefined) {
  const item = Array.isArray(value) ? value[0] : value;
  return typeof item === 'string' ? item : '';
}

export function readRouteQueryPositiveInteger(
  value: QueryInput | undefined,
  defaultValue: number,
  allowedValues?: readonly number[],
) {
  const parsed = Number(readRouteQueryText(value));
  if (!Number.isInteger(parsed) || parsed < 1) return defaultValue;
  if (allowedValues && !allowedValues.includes(parsed)) return defaultValue;
  return parsed;
}

export function readRouteQueryJson<T>(
  value: QueryInput | undefined,
  defaultValue: T,
  validate: (value: unknown) => value is T,
) {
  const text = readRouteQueryText(value);
  if (!text) return defaultValue;
  try {
    const parsed: unknown = JSON.parse(text);
    return validate(parsed) ? parsed : defaultValue;
  } catch {
    return defaultValue;
  }
}

export function areRouteQueriesEqual(
  left: LocationQuery | LocationQueryRaw,
  right: LocationQuery | LocationQueryRaw,
) {
  const normalize = (query: LocationQuery | LocationQueryRaw) =>
    Object.keys(query)
      .sort()
      .map((key) => [key, query[key]]);
  return JSON.stringify(normalize(left)) === JSON.stringify(normalize(right));
}

export function mergeOwnedRouteQuery(
  query: LocationQuery | LocationQueryRaw,
  ownedValues: Record<string, QueryOutput | undefined>,
) {
  const merged: LocationQueryRaw = { ...query };
  for (const [key, value] of Object.entries(ownedValues)) {
    if (value === undefined) delete merged[key];
    else merged[key] = value;
  }
  return merged;
}

/** Declares a list-state field owned by the current page query. */
export function createRouteQueryField<T>(
  source: Ref<T>,
  options: RouteQueryFieldOptions<T>,
): RouteListQueryField {
  return {
    debounceMs: options.debounceMs ?? 0,
    parse: (value) => options.parse(value, options.defaultValue),
    read: () => source.value,
    serialize: (value) => options.serialize(value as T, options.defaultValue),
    write: (value) => {
      source.value = value as T;
    },
  };
}

export function createStringRouteQueryField<T extends string>(
  source: Ref<T>,
  options: {
    allowedValues?: readonly T[];
    debounceMs?: number;
    defaultValue: T;
  },
) {
  return createRouteQueryField(source, {
    debounceMs: options.debounceMs,
    defaultValue: options.defaultValue,
    parse: (value, defaultValue) => {
      const text = readRouteQueryText(value) as T;
      if (!text) return defaultValue;
      return !options.allowedValues || options.allowedValues.includes(text)
        ? text
        : defaultValue;
    },
    serialize: (value, defaultValue) =>
      value === defaultValue || !value ? undefined : value,
  });
}

export function createOptionalStringRouteQueryField<T extends string>(
  source: Ref<T | undefined>,
  options: {
    allowedValues?: readonly T[];
  } = {},
) {
  return createRouteQueryField(source, {
    defaultValue: undefined,
    parse: (value) => {
      const text = readRouteQueryText(value) as T;
      if (!text) return undefined;
      return !options.allowedValues || options.allowedValues.includes(text)
        ? text
        : undefined;
    },
    serialize: (value) => value,
  });
}

export function createStringArrayRouteQueryField(
  source: Ref<string[]>,
  options: {
    allowedValues?: readonly string[];
  } = {},
) {
  return createRouteQueryField(source, {
    defaultValue: [],
    parse: (value) => {
      const values = (Array.isArray(value) ? value : [value])
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.trim())
        .filter(Boolean);
      const allowedValues = options.allowedValues;
      return [
        ...new Set(
          allowedValues
            ? values.filter((item) => allowedValues.includes(item))
            : values,
        ),
      ];
    },
    serialize: (value) => (value.length > 0 ? value : undefined),
  });
}

export function createPositiveIntegerRouteQueryField(
  source: Ref<number>,
  options: {
    allowedValues?: readonly number[];
    defaultValue: number;
  },
) {
  return createRouteQueryField(source, {
    defaultValue: options.defaultValue,
    parse: (value, defaultValue) =>
      readRouteQueryPositiveInteger(value, defaultValue, options.allowedValues),
    serialize: (value, defaultValue) =>
      value === defaultValue ? undefined : String(value),
  });
}

export function createJsonRouteQueryField<T>(
  source: Ref<T>,
  options: {
    defaultValue: T;
    isDefault: (value: T) => boolean;
    validate: (value: unknown) => value is T;
  },
) {
  return createRouteQueryField(source, {
    defaultValue: options.defaultValue,
    parse: (value, defaultValue) =>
      readRouteQueryJson(value, defaultValue, options.validate),
    serialize: (value) =>
      options.isDefault(value) ? undefined : JSON.stringify(value),
  });
}

/**
 * Keeps list filters and pagination in the URL while preserving query keys
 * owned by deep links or other page features.
 */
export function useRouteListQuery({
  fields,
  onRouteApplied,
  route,
  router,
}: RouteListQueryOptions) {
  const isApplyingRoute = ref(false);
  let initialized = false;
  let syncQueued = false;
  const timers = new Map<string, ReturnType<typeof setTimeout>>();

  function buildRouteQuery() {
    const values: Record<string, QueryOutput | undefined> = {};
    for (const [key, field] of Object.entries(fields)) {
      values[key] = field.serialize(field.read());
    }
    return mergeOwnedRouteQuery(route.query, values);
  }

  function syncRouteQuery() {
    if (isApplyingRoute.value) return;
    const query = buildRouteQuery();
    if (areRouteQueriesEqual(route.query, query)) return;
    void router.replace({ query });
  }

  function scheduleRouteSync() {
    if (syncQueued || isApplyingRoute.value) return;
    syncQueued = true;
    void nextTick(() => {
      syncQueued = false;
      syncRouteQuery();
    });
  }

  function applyRouteQuery(query: LocationQuery) {
    isApplyingRoute.value = true;
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
    for (const [key, field] of Object.entries(fields)) {
      field.write(field.parse(query[key]));
    }
    void nextTick(() => {
      isApplyingRoute.value = false;
      syncRouteQuery();
      if (initialized) onRouteApplied?.();
      initialized = true;
    });
  }

  applyRouteQuery(route.query);

  for (const [key, field] of Object.entries(fields)) {
    watch(
      field.read,
      () => {
        if (isApplyingRoute.value) return;
        const existingTimer = timers.get(key);
        if (existingTimer) clearTimeout(existingTimer);
        if (field.debounceMs > 0) {
          timers.set(
            key,
            setTimeout(() => {
              timers.delete(key);
              scheduleRouteSync();
            }, field.debounceMs),
          );
          return;
        }
        scheduleRouteSync();
      },
      { deep: true },
    );
  }

  watch(
    () => route.query,
    (query) => {
      if (areRouteQueriesEqual(query, buildRouteQuery())) return;
      applyRouteQuery(query);
    },
    { deep: true },
  );

  onBeforeUnmount(() => {
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
  });

  return { isApplyingRoute, syncRouteQuery };
}
