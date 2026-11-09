/** 素材库当前页面的短期缓存：请求合并、过期淘汰；不写入浏览器持久存储。 */
export function createMaterialPageRequestCache<T>(options: {
  maxEntries: number;
  maxBytes?: number;
  sizeOf?: (value: T) => number;
}) {
  const entries = new Map<
    string,
    {
      bytes: number;
      expiresAt: number;
      promise: Promise<T>;
    }
  >();

  function prune() {
    const now = Date.now();
    for (const [key, entry] of entries) {
      if (entry.expiresAt <= now) entries.delete(key);
    }
    let bytes = [...entries.values()].reduce(
      (total, entry) => total + entry.bytes,
      0,
    );
    for (const [key, entry] of entries) {
      if (
        entries.size <= options.maxEntries &&
        bytes <= (options.maxBytes ?? Infinity)
      )
        break;
      entries.delete(key);
      bytes -= entry.bytes;
    }
  }

  function get(key: string, loader: () => Promise<T>): Promise<T> {
    prune();
    const cached = entries.get(key);
    if (cached) {
      // 调整访问顺序，但不延长有效期，避免反复访问一直看不到外部更新。
      entries.delete(key);
      entries.set(key, cached);
      return cached.promise;
    }
    const entry = {
      bytes: 0,
      expiresAt: Infinity,
      promise: Promise.resolve().then(loader),
    };
    entry.promise = entry.promise
      .then((value) => {
        // 刷新/编辑后，旧请求即便完成也不能把过期数据写回缓存。
        if (entries.get(key) === entry) {
          entry.expiresAt = Date.now() + MATERIAL_PAGE_CACHE_TTL;
          entry.bytes = options.sizeOf?.(value) ?? 0;
          if (entry.bytes > (options.maxBytes ?? Infinity)) entries.delete(key);
          prune();
        }
        return value;
      })
      .catch((error: unknown) => {
        if (entries.get(key) === entry) entries.delete(key);
        throw error;
      });
    entries.set(key, entry);
    prune();
    return entry.promise;
  }

  return { clear: () => entries.clear(), get };
}

export const MATERIAL_PAGE_CACHE_TTL = 2 * 60 * 1000;
