import { computed, ref } from 'vue';

import { useStorage } from '@vueuse/core';
import { defineStore } from 'pinia';

export const MEDIA_CHANNEL_STORAGE_KEY = 'fusion:media-resource:channels:v1';

export type MediaChannelType = 'account_supplier' | 'agency';

export interface MediaChannel {
  createdAt: string;
  id: string;
  name: string;
  type: MediaChannelType;
}

export interface MediaChannelInput {
  name: string;
  type: MediaChannelType;
}

interface MediaChannelStorageEnvelope {
  items: MediaChannel[];
  schemaVersion: 1;
}

const seedChannels: readonly MediaChannel[] = [
  {
    createdAt: '2026-08-10 10:00',
    id: 'channel-mpower-media',
    name: 'MPOWER Media',
    type: 'agency',
  },
  {
    createdAt: '2026-08-09 14:30',
    id: 'channel-growth-supply',
    name: '增长供应商',
    type: 'account_supplier',
  },
];

function cloneSeedChannels(): MediaChannel[] {
  return seedChannels.map((channel) => ({ ...channel }));
}

function isChannelType(value: unknown): value is MediaChannelType {
  return value === 'agency' || value === 'account_supplier';
}

function normalizeChannel(value: unknown): MediaChannel | undefined {
  if (!value || typeof value !== 'object') return undefined;

  const source = value as Partial<MediaChannel>;
  if (!source.id || !source.name || !isChannelType(source.type)) {
    return undefined;
  }

  return {
    createdAt: source.createdAt || '',
    id: source.id,
    name: source.name,
    type: source.type,
  };
}

function normalizeStoredChannels(value: unknown): MediaChannelStorageEnvelope {
  const stored = value as undefined | { items?: unknown };
  let items: undefined | unknown[];

  if (Array.isArray(value)) {
    items = value;
  } else if (
    value &&
    typeof value === 'object' &&
    Array.isArray(stored?.items)
  ) {
    items = stored.items;
  }

  if (!items) {
    return { items: cloneSeedChannels(), schemaVersion: 1 };
  }

  return {
    items: items
      .map((item) => normalizeChannel(item))
      .filter((channel): channel is MediaChannel => channel !== undefined),
    schemaVersion: 1,
  };
}

function createChannelId() {
  return `channel-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useMediaChannelStore = defineStore('media-channel', () => {
  const stored = useStorage<unknown>(MEDIA_CHANNEL_STORAGE_KEY, {
    items: cloneSeedChannels(),
    schemaVersion: 1,
  });
  const state = ref<MediaChannelStorageEnvelope>(
    normalizeStoredChannels(stored.value),
  );

  /** Upgrade an early raw-array draft without changing any existing asset key. */
  stored.value = state.value;

  const channels = computed(() => state.value.items);

  function persist(items: MediaChannel[]) {
    state.value = { items, schemaVersion: 1 };
    stored.value = state.value;
  }

  function create(input: MediaChannelInput): MediaChannel {
    const name = input.name.trim();
    if (!name) throw new Error('请填写渠道名称');

    const duplicate = channels.value.some(
      (channel) => channel.name.localeCompare(name, 'zh-CN') === 0,
    );
    if (duplicate) throw new Error('渠道名称已存在');

    const channel: MediaChannel = {
      createdAt: new Date().toLocaleString('zh-CN', { hour12: false }),
      id: createChannelId(),
      name,
      type: input.type,
    };
    persist([channel, ...channels.value]);
    return channel;
  }

  function remove(id: string) {
    const next = channels.value.filter((channel) => channel.id !== id);
    if (next.length === channels.value.length) return false;
    persist(next);
    return true;
  }

  return { channels, create, remove };
});
