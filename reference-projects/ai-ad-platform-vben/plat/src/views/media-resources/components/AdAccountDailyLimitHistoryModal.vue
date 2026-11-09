<script lang="ts" setup>
import type { ShadcnDataTableColumn } from '#/components/ui/ShadcnDataTable.vue';

import type {
  AdAccountDailyLimitChange,
  AdAccountDailyLimitChangePage,
} from '#/api';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Alert, Button, Modal, Tag } from 'ant-design-vue';

import { getAdAccountDailyLimitChanges } from '#/api';
import ShadcnDataTable from '#/components/ui/ShadcnDataTable.vue';

import {
  DAILY_LIMIT_CHANGE_META,
  dailyLimitChangeLabel,
  formatDailyLimit,
  formatDailyLimitDateTime,
} from './ad-account-daily-limit-history';
import {
  ASSET_MODAL_TABLE_BODY_HEIGHT,
  ASSET_TABLE_HEADER_HEIGHT,
} from './asset-table-layout';

const props = defineProps<{
  accountId?: string;
  open: boolean;
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
}>();

const PAGE_SIZE = 20;
const TABLE_PAGINATION_HEIGHT = 56;
const columns: ShadcnDataTableColumn[] = [
  { dataIndex: 'changedAt', key: 'changedAt', title: '变更时间', width: 190 },
  { key: 'limitChange', title: '日限额变化', width: 360 },
  { dataIndex: 'source', key: 'source', title: '来源', width: 180 },
];

const data = ref<AdAccountDailyLimitChangePage>();
const error = ref('');
const loading = ref(false);
const page = ref(1);
let requestVersion = 0;
let abortController: AbortController | undefined;

const modalTitle = computed(() =>
  data.value
    ? `账户日限额变更记录 · 共 ${data.value.total} 条`
    : '账户日限额变更记录',
);

const historyTableHeight = computed(
  () =>
    ASSET_MODAL_TABLE_BODY_HEIGHT +
    ASSET_TABLE_HEADER_HEIGHT +
    ((data.value?.total ?? 0) > PAGE_SIZE ? TABLE_PAGINATION_HEIGHT : 0),
);

function close() {
  emit('update:open', false);
}

function resetRequest() {
  requestVersion += 1;
  abortController?.abort();
  abortController = undefined;
  loading.value = false;
}

async function loadHistory(targetPage = page.value) {
  const accountId = props.accountId?.trim();
  if (!props.open || !accountId) return;

  resetRequest();
  const version = requestVersion;
  const controller = new AbortController();
  abortController = controller;
  page.value = targetPage;
  loading.value = true;
  error.value = '';
  try {
    const result = await getAdAccountDailyLimitChanges(
      accountId,
      { page: targetPage, pageSize: PAGE_SIZE },
      { signal: controller.signal, skipErrorMessage: true },
    );
    if (version !== requestVersion || controller.signal.aborted) return;
    data.value = result;
  } catch (requestError) {
    if (version !== requestVersion || controller.signal.aborted) return;
    error.value =
      requestError instanceof Error && requestError.message
        ? requestError.message
        : '日限额变更记录暂时无法获取，请稍后重试。';
  } finally {
    if (version === requestVersion) loading.value = false;
  }
}

function handlePageChange(targetPage: number) {
  void loadHistory(targetPage);
}

function changeMeta(change: AdAccountDailyLimitChange) {
  return DAILY_LIMIT_CHANGE_META[change.changeType] ?? { label: '限额变更' };
}

watch(
  () => [props.open, props.accountId] as const,
  ([open, accountId]) => {
    resetRequest();
    data.value = undefined;
    error.value = '';
    page.value = 1;
    if (open && accountId?.trim()) void loadHistory(1);
  },
  { immediate: true },
);

onBeforeUnmount(resetRequest);
</script>

<template>
  <Modal
    :footer="null"
    :open="open"
    :title="modalTitle"
    :width="'min(94vw, 840px)'"
    centered
    @cancel="close"
  >
    <div
      class="flex max-h-[min(72vh,680px)] min-h-0 flex-col gap-4 overflow-y-auto pr-1"
    >
      <Alert v-if="error" :message="error" role="alert" show-icon type="error">
        <template #action>
          <Button @click="loadHistory(page)">重新加载</Button>
        </template>
      </Alert>

      <section
        class="border-border bg-muted/30 grid shrink-0 gap-3 rounded-lg border p-4 sm:grid-cols-3"
      >
        <div class="min-w-0">
          <div class="text-muted-foreground text-xs">广告账户</div>
          <div class="text-foreground mt-1 truncate text-sm font-medium">
            {{ data?.accountName || '—' }}
          </div>
          <div class="text-muted-foreground mt-1 truncate font-mono text-xs">
            ID {{ data?.accountId || accountId || '—' }}
          </div>
        </div>
        <div>
          <div class="text-muted-foreground text-xs">当前账户日限额</div>
          <div
            class="text-foreground mt-1 text-base font-semibold tabular-nums"
          >
            {{ formatDailyLimit(data?.currentLimit, data?.currency) }}
          </div>
        </div>
        <div>
          <div class="text-muted-foreground text-xs">最近同步时间</div>
          <div class="text-foreground mt-1 text-sm font-medium tabular-nums">
            {{ formatDailyLimitDateTime(data?.lastSyncedAt) }}
          </div>
          <div
            v-if="data?.lastSyncedAt"
            class="text-muted-foreground mt-1 text-xs"
          >
            GMT+8
          </div>
        </div>
      </section>

      <div class="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <h3 class="text-foreground m-0 text-base font-semibold">变更明细</h3>
        <p class="text-muted-foreground m-0 text-xs">
          记录由 Facebook 平台同步，按发生时间倒序展示
        </p>
      </div>

      <div class="min-h-0 shrink-0">
        <ShadcnDataTable
          :columns="columns"
          :data="data?.items ?? []"
          empty-text="暂无日限额变更记录"
          :loading="loading"
          :page="page"
          :page-size="PAGE_SIZE"
          row-key="id"
          sticky-pagination
          :table-height="historyTableHeight"
          :total="data?.total ?? 0"
          @update:page="handlePageChange"
        >
          <template #cell-changedAt="{ record }">
            <div class="tabular-nums">
              {{ formatDailyLimitDateTime(record.changedAt) }}
            </div>
            <div class="text-muted-foreground mt-1 text-xs">GMT+8</div>
          </template>
          <template #cell-limitChange="{ record }">
            <div class="flex flex-wrap items-center gap-2 tabular-nums">
              <span class="text-muted-foreground">
                {{ formatDailyLimit(record.previousLimit, data?.currency) }}
              </span>
              <IconifyIcon
                aria-hidden="true"
                class="text-muted-foreground size-4 shrink-0"
                icon="lucide:arrow-right"
              />
              <span class="text-foreground font-medium">
                {{ formatDailyLimit(record.currentLimit, data?.currency) }}
              </span>
              <Tag :color="changeMeta(record).color" class="!m-0">
                {{ dailyLimitChangeLabel(record) }}
              </Tag>
            </div>
          </template>
          <template #cell-source>
            <span class="inline-flex items-center gap-1.5">
              <IconifyIcon
                aria-hidden="true"
                class="text-muted-foreground size-4"
                icon="lucide:refresh-cw"
              />
              Facebook 平台同步
            </span>
          </template>
        </ShadcnDataTable>
      </div>

      <div class="border-border flex shrink-0 justify-end border-t pt-4">
        <Button @click="close">关闭</Button>
      </div>
    </div>
  </Modal>
</template>
