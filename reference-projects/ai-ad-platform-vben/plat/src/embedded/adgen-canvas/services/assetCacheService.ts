// Asset cache service using IndexedDB for persistent storage
const DB_NAME = 'AssetCache';
const STORE_NAME = 'assets';
const DB_VERSION = 1;
const CACHE_DURATION = 7 * 24 * 60 * 60 * 1000; // 7 days
const MAX_CACHE_ENTRIES = 500; // 超过此数量时淘汰最旧的条目
const CACHE_CLEANUP_INTERVAL = 10 * 60 * 1000; // 10 minutes

const DEBUG_CACHE = false;

interface CachedAsset {
  url: string;
  blob: Blob;
  timestamp: number;
}

let db: IDBDatabase | null = null;
let cleanupIntervalStarted = false;

const initDB = (): Promise<IDBDatabase> => {
  return new Promise((resolve, reject) => {
    if (db) {
      resolve(db);
      return;
    }

    if (!window.indexedDB) {
      if (DEBUG_CACHE) console.error('IndexedDB not supported');
      reject(new Error('IndexedDB not supported'));
      return;
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => {
      if (DEBUG_CACHE) console.error('[AssetCache] Failed to open IndexedDB:', request.error);
      reject(request.error);
    };

    request.onsuccess = () => {
      db = request.result;
      resolve(db);
    };

    request.onupgradeneeded = (event) => {
      const database = (event.target as IDBOpenDBRequest).result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME, { keyPath: 'url' });
      }
    };
  });
};

// ===== Blob URL 池：同一个 cache key 只创建一个 blob URL =====
const MAX_BLOB_POOL_SIZE = 200; // 最多保留 200 个 blob URL
const blobUrlPool = new Map<string, string>();

/** 淘汰最旧的 blob URL，保持池大小在限制内 */
const evictBlobPool = () => {
  while (blobUrlPool.size > MAX_BLOB_POOL_SIZE) {
    // Map 迭代顺序是插入顺序，第一个就是最旧的
    const oldest = blobUrlPool.keys().next().value;
    if (oldest === undefined) break;
    const oldUrl = blobUrlPool.get(oldest);
    if (oldUrl) URL.revokeObjectURL(oldUrl);
    blobUrlPool.delete(oldest);
  }
};

export const getCachedAsset = async (url: string): Promise<string | null> => {
  try {
    // 池中已有，移到末尾（LRU）并返回
    const existing = blobUrlPool.get(url);
    if (existing) {
      blobUrlPool.delete(url);
      blobUrlPool.set(url, existing);
      return existing;
    }

    const database = await initDB();
    const transaction = database.transaction(STORE_NAME, 'readonly');
    const store = transaction.objectStore(STORE_NAME);

    return new Promise((resolve) => {
      const request = store.get(url);

      request.onsuccess = () => {
        const cached = request.result as CachedAsset | undefined;
        if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
          const blobUrl = URL.createObjectURL(cached.blob);
          blobUrlPool.set(url, blobUrl);
          evictBlobPool();
          resolve(blobUrl);
        } else {
          resolve(null);
        }
      };

      request.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
};

export const cacheAsset = async (url: string, blob: Blob): Promise<void> => {
  try {
    const database = await initDB();
    const transaction = database.transaction(STORE_NAME, 'readwrite');
    const store = transaction.objectStore(STORE_NAME);

    await new Promise<void>((resolve, reject) => {
      const request = store.put({ url, blob, timestamp: Date.now() });
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  } catch {
    // 缓存写入失败不影响功能
  }
};

export const deleteCachedAsset = async (url: string): Promise<void> => {
  try {
    revokeCachedBlobUrl(url);

    const database = await initDB();
    const transaction = database.transaction(STORE_NAME, 'readwrite');
    const store = transaction.objectStore(STORE_NAME);

    await new Promise<void>((resolve, reject) => {
      const request = store.delete(url);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  } catch {
    // 删除失败不影响功能
  }
};

/**
 * 释放指定 cache key 对应的 blob URL
 */
export const revokeCachedBlobUrl = (url: string): void => {
  const blobUrl = blobUrlPool.get(url);
  if (blobUrl) {
    URL.revokeObjectURL(blobUrl);
    blobUrlPool.delete(url);
  }
};

/**
 * 批量释放一组 blob URL（例如翻页时释放上一页的）
 */
export const revokeBlobUrls = (urls: Iterable<string>): void => {
  for (const url of urls) {
    if (url.startsWith('blob:')) {
      URL.revokeObjectURL(url);
    }
  }
};

/**
 * 清理过期缓存 + 超量淘汰
 */
export const clearExpiredCache = async (): Promise<void> => {
  try {
    const database = await initDB();
    const transaction = database.transaction(STORE_NAME, 'readwrite');
    const store = transaction.objectStore(STORE_NAME);

    const allEntries: CachedAsset[] = [];

    const request = store.openCursor();
    request.onsuccess = (event) => {
      const cursor = (event.target as IDBRequest).result;
      if (cursor) {
        const cached = cursor.value as CachedAsset;
        // 删除过期条目
        if (Date.now() - cached.timestamp >= CACHE_DURATION) {
          cursor.delete();
          revokeCachedBlobUrl(cached.url);
        } else {
          allEntries.push(cached);
        }
        cursor.continue();
      } else {
        // 游标结束后，如果条目过多则淘汰最旧的
        if (allEntries.length > MAX_CACHE_ENTRIES) {
          allEntries.sort((a, b) => a.timestamp - b.timestamp);
          const toRemove = allEntries.slice(0, allEntries.length - MAX_CACHE_ENTRIES);
          const tx = database.transaction(STORE_NAME, 'readwrite');
          const s = tx.objectStore(STORE_NAME);
          for (const entry of toRemove) {
            s.delete(entry.url);
            revokeCachedBlobUrl(entry.url);
          }
        }
      }
    };
  } catch {
    // 清理失败不影响功能
  }
};

export const ensureAssetCacheMaintenance = (): void => {
  if (cleanupIntervalStarted || typeof window === 'undefined') return;
  cleanupIntervalStarted = true;

  void clearExpiredCache();
  window.setInterval(() => {
    void clearExpiredCache();
  }, CACHE_CLEANUP_INTERVAL);
};
