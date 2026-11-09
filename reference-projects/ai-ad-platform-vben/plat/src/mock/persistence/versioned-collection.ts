export const COLLECTION_SCHEMA_VERSION = 1;

export interface CollectionEnvelope<T> {
  data: T[];
  schemaVersion: number;
  seededAt: string;
  updatedAt: string;
}

export interface StorageLike {
  getItem(key: string): null | string;
  setItem(key: string, value: string): void;
}

interface ReadCollectionOptions<T> {
  fallback: T[];
  now?: () => string;
  storage: StorageLike;
  storageKey: string;
}

function isCollectionEnvelope<T>(
  value: unknown,
): value is CollectionEnvelope<T> {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<CollectionEnvelope<T>>;
  return (
    Array.isArray(candidate.data) && typeof candidate.schemaVersion === 'number'
  );
}

function createEnvelope<T>(
  data: T[],
  timestamp: string,
): CollectionEnvelope<T> {
  return {
    data,
    schemaVersion: COLLECTION_SCHEMA_VERSION,
    seededAt: timestamp,
    updatedAt: timestamp,
  };
}

export function writeVersionedCollection<T>(
  storage: StorageLike,
  storageKey: string,
  data: T[],
  options: { now?: () => string; seededAt?: string } = {},
) {
  const timestamp = (options.now ?? (() => new Date().toISOString()))();
  storage.setItem(
    storageKey,
    JSON.stringify({
      data,
      schemaVersion: COLLECTION_SCHEMA_VERSION,
      seededAt: options.seededAt ?? timestamp,
      updatedAt: timestamp,
    } satisfies CollectionEnvelope<T>),
  );
}

/**
 * Reads the existing key in place so old bookmarks and browser data remain valid.
 * A legacy bare array is upgraded exactly once to the versioned envelope.
 */
export function readVersionedCollection<T>({
  fallback,
  now = () => new Date().toISOString(),
  storage,
  storageKey,
}: ReadCollectionOptions<T>): T[] {
  const raw = storage.getItem(storageKey);
  if (!raw) return fallback;

  try {
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      const timestamp = now();
      storage.setItem(
        storageKey,
        JSON.stringify(createEnvelope(parsed as T[], timestamp)),
      );
      return parsed as T[];
    }

    if (!isCollectionEnvelope<T>(parsed)) return fallback;

    if (parsed.schemaVersion === COLLECTION_SCHEMA_VERSION) {
      return parsed.data;
    }

    if (parsed.schemaVersion < COLLECTION_SCHEMA_VERSION) {
      const timestamp = now();
      storage.setItem(
        storageKey,
        JSON.stringify({
          ...parsed,
          schemaVersion: COLLECTION_SCHEMA_VERSION,
          updatedAt: timestamp,
        } satisfies CollectionEnvelope<T>),
      );
      return parsed.data;
    }
  } catch {
    return fallback;
  }

  return fallback;
}
