<script lang="ts" setup>
import type { AdAccount, FbAssetRef, FbPage, FbPixel } from '#/api';

import { computed, ref } from 'vue';

import { Button, Input, message, Popover, Tag } from 'ant-design-vue';

import { getAdAccounts, getPages, getPixels } from '#/api';

const props = withDefaults(
  defineProps<{
    assetType: 'ad_account' | 'page' | 'pixel';
    buttonType?: 'dashed' | 'default' | 'link' | 'primary' | 'text';
    hideSearch?: boolean;
    modelValue?: FbAssetRef[];
    placeholder?: string;
  }>(),
  {
    buttonType: 'dashed',
    hideSearch: false,
    modelValue: () => [],
    placeholder: '',
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: FbAssetRef[]];
}>();

const MAX_RESULTS = 20;

const open = ref(false);
const searchId = ref('');
const searchName = ref('');
const loading = ref(false);
const results = ref<Array<{ id: string; name: string }>>([]);
const total = ref(0);
const searched = ref(false);
const batchText = ref('');
const batchLoading = ref(false);

const selected = computed<FbAssetRef[]>(() => props.modelValue ?? []);

const typeLabel = computed(() =>
  props.assetType === 'ad_account'
    ? '广告账户'
    : props.assetType === 'pixel'
      ? '像素'
      : '主页',
);

const queryAssets = (params: {
  id?: string;
  name?: string;
  page: number;
  page_size: number;
}) =>
  props.assetType === 'ad_account'
    ? getAdAccounts(params)
    : props.assetType === 'pixel'
      ? getPixels(params)
      : getPages(params);

const selectedKeys = computed(
  () => new Set(selected.value.map((item) => item.id)),
);

const batchPlaceholder = computed(() =>
  props.hideSearch
    ? '提取纯数字账户ID'
    : props.assetType === 'page'
      ? '支持名称 + 编号：\nDoãn Liêu\n编号:109749118134297'
      : '支持每行一条：\n827825373560889\n3218348325006641 DX+530-0116-10',
);

function update(next: FbAssetRef[]) {
  emit('update:modelValue', next);
}

async function search() {
  loading.value = true;
  try {
    const params = {
      id: searchId.value || undefined,
      name: searchName.value || undefined,
      page: 1,
      page_size: MAX_RESULTS,
    };
    const response = await queryAssets(params);
    const items = (response.items ?? []) as Array<AdAccount | FbPage | FbPixel>;
    results.value = items.map((row) => ({
      id: String(row._id),
      name: row.name || String(row._id),
    }));
    total.value = response.total ?? 0;
    searched.value = true;
  } finally {
    loading.value = false;
  }
}

function reset() {
  searchId.value = '';
  searchName.value = '';
  results.value = [];
  total.value = 0;
  searched.value = false;
}

function toggle(item: { id: string; name: string }) {
  const map = new Map(selected.value.map((p) => [p.id, p]));
  if (map.has(item.id)) {
    map.delete(item.id);
  } else {
    map.set(item.id, item);
  }
  update([...map.values()]);
}

function remove(id: string) {
  update(selected.value.filter((p) => p.id !== id));
}

function clearAll() {
  update([]);
}

function showAssetMessage(
  type: 'error' | 'success' | 'warning',
  content: string,
) {
  const key = `asset-message-${Date.now()}-${Math.random()}`;
  message[type]({
    content,
    duration: 10,
    key,
  });
}

async function applyBatch() {
  if (props.hideSearch) {
    const ids = [...new Set(batchText.value.match(/\d{10,}/g) ?? [])];
    if (ids.length === 0) {
      showAssetMessage(
        'warning',
        '未识别到有效的账户 ID（需为 10 位以上纯数字）',
      );
      return;
    }
    const map = new Map(selected.value.map((p) => [p.id, p]));
    ids.forEach((id) => map.set(id, { id, name: '' }));
    update([...map.values()]);
    batchText.value = '';
    showAssetMessage('success', `已加入 ${ids.length} 个${typeLabel.value} ID`);
    return;
  }

  const lines = batchText.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    showAssetMessage('warning', '请粘贴至少一行');
    return;
  }

  const map = new Map(selected.value.map((p) => [p.id, p]));
  let added = 0;
  // 没有纯数字 ID 的行，整行作为名称，后续走查询接口反查 ID
  const nameQueries: string[] = [];
  // 只有纯数字 ID、未带名称的行，后续按 ID 调接口补全 name
  const idLookups = new Set<string>();
  const consumedLineIndexes = new Set<number>();

  if (props.assetType === 'page') {
    lines.forEach((line, index) => {
      const idMatch = line.match(/(?:编号|id)[:：]?\s*(\d{10,})/i);
      if (!idMatch?.[1]) return;

      const id = idMatch[1];
      const inlineName = line.slice(0, idMatch.index).trim();
      let name = inlineName;
      let nameIndex = -1;

      if (!name) {
        for (let i = index - 1; i >= 0; i--) {
          const candidate = lines[i]!;
          if (consumedLineIndexes.has(i)) continue;
          if (/(?:编号|id)[:：]?\s*\d{10,}/i.test(candidate)) continue;
          if (/^\d{10,}$/.test(candidate)) continue;
          name = candidate;
          nameIndex = i;
          break;
        }
      }

      if (!name) return;

      map.set(id, { id, name });
      consumedLineIndexes.add(index);
      if (nameIndex >= 0) consumedLineIndexes.add(nameIndex);
      added++;
    });
  }

  lines.forEach((line, index) => {
    if (consumedLineIndexes.has(index)) return;
    const normalized = line.replace(/[，；;]/g, ' ').trim();
    const tokens = normalized.split(/\s+/).filter(Boolean);
    if (tokens.length === 0) return;
    // ID 为 10 位以上的连续纯数字，可能在前也可能在后，取第一个匹配到的
    const idIndex = tokens.findIndex((token) => /^\d{10,}$/.test(token));
    if (idIndex === -1) {
      nameQueries.push(normalized);
      return;
    }
    const id = tokens[idIndex]!;
    // 其余 token 组成 name，保留其间的空格
    const restName = tokens.filter((_, index) => index !== idIndex).join(' ');
    const existing = map.get(id);
    const name = restName || existing?.name || '';
    map.set(id, { id, name });
    // 没带名称的纯数字 ID，标记后续按 ID 反查 name
    if (!name) idLookups.add(id);
    added++;
  });

  // 没有 ID 的行，逐个按名称调用查询接口反查 ID：仅在唯一/精确命中时加入
  const notFound: string[] = []; // 未查到结果
  const ambiguous: string[] = []; // 命中多条、无法确定
  if (idLookups.size > 0 || nameQueries.length > 0) {
    batchLoading.value = true;
    try {
      // 只有纯数字 ID 的行：按 ID 查询补全 name
      for (const id of idLookups) {
        const params = { id, page: 1, page_size: 1 };
        // eslint-disable-next-line no-await-in-loop
        const response = await queryAssets(params);
        const items = (response.items ?? []) as Array<
          AdAccount | FbPage | FbPixel
        >;
        const row = items.find((item) => String(item._id) === id) ?? items[0];
        if (row?.name) {
          map.set(id, { id, name: row.name });
        }
      }

      for (const name of nameQueries) {
        const params = { name, page: 1, page_size: MAX_RESULTS };
        // eslint-disable-next-line no-await-in-loop
        const response = await queryAssets(params);
        const items = (response.items ?? []) as Array<
          AdAccount | FbPage | FbPixel
        >;
        if (items.length === 0) {
          notFound.push(name);
          continue;
        }
        // 精确名称匹配优先；否则仅当返回唯一一条时才采用
        const lower = name.toLowerCase();
        const exact = items.filter(
          (row) => (row.name ?? '').trim().toLowerCase() === lower,
        );
        let row: AdAccount | FbPage | FbPixel | undefined;
        if (exact.length === 1) {
          row = exact[0];
        } else if (exact.length === 0 && items.length === 1) {
          row = items[0];
        }
        // 精确命中多条，或模糊命中多条，均视为无法确定
        if (!row) {
          ambiguous.push(name);
          continue;
        }
        const id = String(row._id);
        map.set(id, { id, name: row.name || id });
        added++;
      }
    } finally {
      batchLoading.value = false;
    }
  }

  update([...map.values()]);
  // 保留未查到 / 命中多条的名称，方便用户修正后重新解析
  batchText.value = [...notFound, ...ambiguous].join('\n');

  if (notFound.length > 0) {
    const preview = notFound.slice(0, 5).join('、');
    const suffix = notFound.length > 5 ? ' 等' : '';
    showAssetMessage(
      'warning',
      `${notFound.length} 项未匹配到${typeLabel.value}：${preview}${suffix}`,
    );
  }

  if (ambiguous.length > 0) {
    const preview = ambiguous.slice(0, 5).join('、');
    const suffix = ambiguous.length > 5 ? ' 等' : '';
    showAssetMessage(
      'warning',
      `${ambiguous.length} 项命中多个${typeLabel.value}，请细化名称：${preview}${suffix}`,
    );
  }

  if (added > 0) {
    showAssetMessage('success', `已加入 ${added} 项${typeLabel.value}`);
  }
}
</script>

<template>
  <Popover
    v-model:open="open"
    trigger="click"
    placement="bottomLeft"
    :overlay-style="{ width: '460px' }"
    destroy-tooltip-on-hide
  >
    <template #content>
      <div class="space-y-3">
        <template v-if="!hideSearch">
          <div
            class="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_max-content_max-content]"
          >
            <Input
              v-model:value="searchId"
              allow-clear
              placeholder="按 ID 精确搜索"
              @press-enter="search"
            />
            <Input
              v-model:value="searchName"
              allow-clear
              placeholder="按名称模糊搜索"
              @press-enter="search"
            />
            <Button type="primary" :loading="loading" @click="search">
              搜索
            </Button>
            <Button @click="reset">重置</Button>
          </div>

          <div
            class="max-h-[200px] overflow-y-auto rounded border border-gray-200 dark:border-gray-700"
          >
            <div
              v-if="!searched"
              class="py-6 text-center text-xs text-gray-400"
            >
              输入搜索条件后查看{{ typeLabel }}
            </div>
            <div
              v-else-if="results.length === 0"
              class="py-6 text-center text-xs text-gray-400"
            >
              未匹配到{{ typeLabel }}
            </div>
            <div
              v-for="item in results"
              :key="item.id"
              class="flex cursor-pointer items-center gap-2 border-b border-gray-100 px-2 py-1 last:border-0 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
              @click="toggle(item)"
            >
              <input
                type="checkbox"
                :checked="selectedKeys.has(item.id)"
                @click.stop="toggle(item)"
              />
              <span class="text-xs text-gray-500">{{ item.id }}</span>
              <span class="truncate">{{ item.name }}</span>
            </div>
          </div>
          <div
            v-if="searched && total > MAX_RESULTS"
            class="text-xs text-amber-600"
          >
            匹配较多（共 {{ total }} 条），仅展示前
            {{ MAX_RESULTS }} 条；名称为模糊搜索，请细化关键词
          </div>
        </template>

        <div
          class="rounded border border-dashed border-gray-200 p-2 dark:border-gray-700"
        >
          <div class="mb-1 flex items-center justify-between">
            <div class="text-xs font-medium">批量粘贴解析{{ typeLabel }}</div>
            <Button
              type="link"
              class="px-0"
              :loading="batchLoading"
              @click="applyBatch"
            >
              解析并加入已选
            </Button>
          </div>
          <Input.TextArea
            v-model:value="batchText"
            :rows="3"
            :placeholder="batchPlaceholder"
          />
        </div>

        <div>
          <div class="mb-1 flex items-center justify-between text-xs">
            <span class="font-medium">已选 {{ selected.length }} 个</span>
            <Button
              v-if="selected.length"
              type="link"
              class="px-0"
              @click="clearAll"
            >
              清空
            </Button>
          </div>
          <div
            v-if="selected.length"
            class="flex max-h-[100px] flex-wrap gap-1 overflow-y-auto"
          >
            <Tag
              v-for="item in selected"
              :key="item.id"
              closable
              color="processing"
              @close.prevent="remove(item.id)"
            >
              {{ item.id }}{{ item.name ? ` ${item.name}` : '' }}
            </Tag>
          </div>
          <div v-else class="text-xs text-gray-400">
            尚未选择{{ typeLabel }}
          </div>
        </div>
      </div>
    </template>

    <Button
      :type="buttonType"
      :class="buttonType === 'dashed' ? 'w-full !text-left' : ''"
    >
      <span v-if="selected.length === 0">
        {{ placeholder || `+ 添加${typeLabel}` }}
      </span>
      <span v-else>已选 {{ selected.length }} 个</span>
    </Button>
  </Popover>
</template>
