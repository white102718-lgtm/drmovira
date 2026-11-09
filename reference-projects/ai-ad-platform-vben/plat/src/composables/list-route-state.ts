import type {
  LocationQuery,
  LocationQueryRaw,
  LocationQueryValue,
  LocationQueryValueRaw,
} from 'vue-router';

export type ListRouteState = Record<string, unknown>;

export interface ListRouteFieldCodec<T = unknown> {
  /** 将 URL 参数转换为页面筛选值；返回 undefined 时使用字段默认值。 */
  parse: (value: LocationQueryValue | LocationQueryValue[]) => T | undefined;
  /** 将页面筛选值转换为 URL 参数；返回 undefined 时从 URL 移除该字段。 */
  serialize: (
    value: T,
  ) => LocationQueryValueRaw | LocationQueryValueRaw[] | undefined;
}

export interface ListRouteFieldOptions<T = unknown> {
  /** 即使等于页面默认值也显式写入 URL，适用于主 Tab、资产分类等导航状态。 */
  always?: boolean;
  codec?: ListRouteFieldCodec<T>;
  key?: string;
}

export interface ListRoutePaginationSnapshot {
  page: number;
  pageSize: number;
}

export interface ListRoutePaginationOptions {
  defaultPageSize: number;
  pageKey?: string;
  pageSizeKey?: string;
  pageSizes?: number[];
}

export interface ParseListRouteStateOptions<T extends ListRouteState> {
  defaults: T;
  fields?: { [K in keyof T]?: ListRouteFieldOptions<T[K]> };
  pagination?: ListRoutePaginationOptions;
  query: LocationQuery;
  scope?: string;
}

export interface SerializeListRouteStateOptions<T extends ListRouteState> {
  currentQuery: LocationQuery;
  defaults?: T;
  fields?: { [K in keyof T]?: ListRouteFieldOptions<T[K]> };
  pagination?: ListRoutePaginationOptions;
  paginationState?: ListRoutePaginationSnapshot;
  scope?: string;
  state: T;
}

export interface ParsedListRouteState<T extends ListRouteState> {
  pagination?: ListRoutePaginationSnapshot;
  state: T;
}

const DEFAULT_PAGE_KEY = 'page';
const DEFAULT_PAGE_SIZE_KEY = 'page_size';

function cloneDefaultValue<T>(value: T): T {
  if (Array.isArray(value)) return [...value] as T;
  if (value && typeof value === 'object') return { ...value } as T;
  return value;
}

function firstQueryValue(
  value: LocationQueryValue | LocationQueryValue[],
): LocationQueryValue {
  return Array.isArray(value) ? (value[0] ?? null) : value;
}

function scopedKey(scope: string | undefined, key: string): string {
  return scope ? `${scope}_${key}` : key;
}

function resolveFieldKey<T extends ListRouteState>(
  field: keyof T,
  fields: ParseListRouteStateOptions<T>['fields'],
  scope?: string,
): string {
  const configuredKey = fields?.[field]?.key ?? String(field);
  return scopedKey(scope, configuredKey);
}

function isEmptyRouteValue(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    value === '' ||
    (Array.isArray(value) && value.length === 0)
  );
}

function serializePrimitive(value: unknown): LocationQueryValueRaw | undefined {
  if (isEmptyRouteValue(value)) return undefined;
  if (typeof value === 'boolean') return value ? '1' : '0';
  if (typeof value === 'number' || typeof value === 'string') {
    return String(value);
  }
  if (value instanceof Date) return value.toISOString();
  if (
    typeof value === 'object' &&
    value !== null &&
    'valueOf' in value &&
    typeof value.valueOf === 'function'
  ) {
    const primitive = value.valueOf();
    if (typeof primitive === 'number' || typeof primitive === 'string') {
      return String(primitive);
    }
  }
  return JSON.stringify(value);
}

function serializeDefaultValue(
  value: unknown,
): LocationQueryValueRaw | LocationQueryValueRaw[] | undefined {
  if (Array.isArray(value)) {
    const serialized = value
      .map(serializePrimitive)
      .filter((item): item is LocationQueryValueRaw => item !== undefined);
    return serialized.length > 0 ? serialized : undefined;
  }
  return serializePrimitive(value);
}

function parseBoolean(value: LocationQueryValue): boolean | undefined {
  if (value === '1' || value === 'true') return true;
  if (value === '0' || value === 'false') return false;
  return undefined;
}

function parseNumber(value: LocationQueryValue): number | undefined {
  if (value === null || value.trim() === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parseDefaultValue(
  value: LocationQueryValue | LocationQueryValue[],
  defaultValue: unknown,
): unknown {
  if (Array.isArray(defaultValue)) {
    const rawValues = Array.isArray(value) ? value : [value];
    // 兼容旧页面使用逗号连接多选值的历史链接。
    const expandedValues = rawValues.flatMap((item) =>
      typeof item === 'string' ? item.split(',') : [],
    );
    const firstDefault = defaultValue[0];
    if (typeof firstDefault === 'number') {
      return expandedValues
        .map((item) => parseNumber(item))
        .filter((item): item is number => item !== undefined);
    }
    return expandedValues;
  }

  const rawValue = firstQueryValue(value);
  if (rawValue === null) return undefined;
  if (typeof defaultValue === 'boolean') return parseBoolean(rawValue);
  if (typeof defaultValue === 'number') return parseNumber(rawValue);
  if (defaultValue && typeof defaultValue === 'object') {
    try {
      return JSON.parse(rawValue);
    } catch {
      return undefined;
    }
  }
  return rawValue;
}

function parsePositiveInteger(
  value: LocationQueryValue | LocationQueryValue[] | undefined,
  fallback: number,
): number {
  if (value === undefined) return fallback;
  const parsed = parseNumber(firstQueryValue(value));
  return parsed && Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

/**
 * 从 URL 查询参数恢复列表筛选与分页状态。
 *
 * @remarks
 * 非法值不会进入接口请求，而是回落到页面声明的默认值。
 */
export function parseListRouteState<T extends ListRouteState>(
  options: ParseListRouteStateOptions<T>,
): ParsedListRouteState<T> {
  const state = {} as T;
  for (const rawField of Object.keys(options.defaults)) {
    const field = rawField as keyof T;
    const defaultValue = options.defaults[field];
    const key = resolveFieldKey(field, options.fields, options.scope);
    const rawValue = options.query[key];
    if (rawValue === undefined) {
      state[field] = cloneDefaultValue(defaultValue) as T[keyof T];
      continue;
    }
    const parsedValue = options.fields?.[field]?.codec
      ? options.fields[field]!.codec!.parse(rawValue)
      : parseDefaultValue(rawValue, defaultValue);
    state[field] = cloneDefaultValue(
      parsedValue === undefined ? defaultValue : parsedValue,
    ) as T[keyof T];
  }

  if (!options.pagination) return { state };
  const pageKey = scopedKey(
    options.scope,
    options.pagination.pageKey ?? DEFAULT_PAGE_KEY,
  );
  const pageSizeKey = scopedKey(
    options.scope,
    options.pagination.pageSizeKey ?? DEFAULT_PAGE_SIZE_KEY,
  );
  const pageSize = parsePositiveInteger(
    options.query[pageSizeKey],
    options.pagination.defaultPageSize,
  );
  const allowedPageSize =
    !options.pagination.pageSizes ||
    options.pagination.pageSizes.length === 0 ||
    options.pagination.pageSizes.includes(pageSize)
      ? pageSize
      : options.pagination.defaultPageSize;

  return {
    pagination: {
      page: parsePositiveInteger(options.query[pageKey], 1),
      pageSize: allowedPageSize,
    },
    state,
  };
}

/** 将当前实际查询状态写入 URL，并保留不属于本列表的查询参数。 */
export function serializeListRouteState<T extends ListRouteState>(
  options: SerializeListRouteStateOptions<T>,
): LocationQueryRaw {
  const query: LocationQueryRaw = { ...options.currentQuery };
  for (const rawField of Object.keys(options.state)) {
    const field = rawField as keyof T;
    const key = resolveFieldKey(field, options.fields, options.scope);
    const value = options.fields?.[field]?.codec
      ? options.fields[field]!.codec!.serialize(options.state[field])
      : serializeDefaultValue(options.state[field]);
    const defaultValue = options.defaults
      ? options.fields?.[field]?.codec
        ? options.fields[field]!.codec!.serialize(options.defaults[field])
        : serializeDefaultValue(options.defaults[field])
      : undefined;
    const isDefaultValue =
      options.defaults !== undefined &&
      JSON.stringify(value) === JSON.stringify(defaultValue);
    if (
      value === undefined ||
      (isDefaultValue && !options.fields?.[field]?.always)
    )
      delete query[key];
    else query[key] = value;
  }

  if (options.pagination && options.paginationState) {
    const pageKey = scopedKey(
      options.scope,
      options.pagination.pageKey ?? DEFAULT_PAGE_KEY,
    );
    const pageSizeKey = scopedKey(
      options.scope,
      options.pagination.pageSizeKey ?? DEFAULT_PAGE_SIZE_KEY,
    );
    query[pageKey] = String(options.paginationState.page);
    query[pageSizeKey] = String(options.paginationState.pageSize);
  }
  return query;
}

export function normalizeLocationQuery(query: LocationQueryRaw): string {
  return JSON.stringify(
    Object.keys(query)
      .sort()
      .map((key) => [key, query[key]]),
  );
}

export const listRouteCodecs = {
  boolean: {
    parse(value: LocationQueryValue | LocationQueryValue[]) {
      return parseBoolean(firstQueryValue(value));
    },
    serialize(value: boolean) {
      return value ? '1' : '0';
    },
  } satisfies ListRouteFieldCodec<boolean>,
  stringArray: {
    parse(value: LocationQueryValue | LocationQueryValue[]) {
      const values = Array.isArray(value) ? value : [value];
      return values.flatMap((item) =>
        typeof item === 'string' ? item.split(',').filter(Boolean) : [],
      );
    },
    serialize(value: string[]) {
      return value.length > 0 ? value : undefined;
    },
  } satisfies ListRouteFieldCodec<string[]>,
};
