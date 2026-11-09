<script setup lang="ts">
import type { ChannelMigrationCandidate } from '#/api/main';
import type { ShadcnDataTableColumn } from '#/components/ui/ShadcnDataTable.vue';

import { computed, ref, watch } from 'vue';

import { Button, Checkbox, message, Modal, Tag, Tabs } from 'ant-design-vue';

import {
  createChannelMigrationPlan,
  executeChannelMigration,
  getMigrationEnvironment,
} from '#/api/main';
import ShadcnDataTable from '#/components/ui/ShadcnDataTable.vue';

import AccountMigrationPanel from './AccountMigrationPanel.vue';

const tab = ref('channels');
const error = ref('');
const environmentLoading = ref(false);
let generation = 0;
const emit = defineEmits<{ success: [] }>();

const open = ref(false);
const loading = ref(false);
const executing = ref(false);
const confirmed = ref(false);
const environment = ref<'PRODUCTION' | 'TEST'>();
const planHash = ref('');
const rows = ref<ChannelMigrationCandidate[]>([]);
const selectedIds = ref<string[]>([]);

const columns: ShadcnDataTableColumn[] = [
  { key: 'select', title: '', width: 48 },
  { dataIndex: 'sourceId', key: 'sourceId', title: '老渠道 ID', width: 110 },
  {
    dataIndex: 'channelName',
    key: 'channelName',
    title: '渠道名称',
    width: 180,
  },
  {
    dataIndex: 'channelCode',
    key: 'channelCode',
    title: '渠道编码',
    width: 120,
  },
  {
    align: 'right',
    dataIndex: 'rateCount',
    key: 'rateCount',
    title: '费率数',
    width: 90,
  },
  { dataIndex: 'action', key: 'action', title: '预检结果', width: 220 },
];

const availableRows = computed(() =>
  rows.value.filter((row) => row.action === 'INSERT'),
);
const allSelected = computed(
  () =>
    availableRows.value.length > 0 &&
    availableRows.value.every((row) =>
      selectedIds.value.includes(row.sourceId),
    ),
);
const canExecute = computed(
  () =>
    selectedIds.value.length > 0 &&
    confirmed.value &&
    !executing.value &&
    !loading.value &&
    !!planHash.value &&
    !!environment.value,
);

function toggleAll(checked: boolean) {
  selectedIds.value = checked
    ? availableRows.value.map((row) => row.sourceId)
    : [];
}

function toggleRow(sourceId: string, checked: boolean) {
  selectedIds.value = checked
    ? [...new Set([...selectedIds.value, sourceId])]
    : selectedIds.value.filter((id) => id !== sourceId);
}

async function loadPlan() {
  const token = ++generation;
  rows.value = [];
  planHash.value = '';
  error.value = '';
  loading.value = true;
  confirmed.value = false;
  selectedIds.value = [];
  try {
    const plan = await createChannelMigrationPlan();
    if (token !== generation || !open.value) return;
    if (environment.value !== plan.environment)
      throw new Error('目标环境发生变化，请关闭后重新打开');
    planHash.value = plan.planHash;
    rows.value = plan.items;
    selectedIds.value = plan.items
      .filter((item) => item.action === 'INSERT')
      .map((item) => item.sourceId);
  } catch (e) {
    if (token === generation)
      error.value = e instanceof Error ? e.message : '渠道预检失败';
  } finally {
    if (token === generation) loading.value = false;
  }
}

async function show() {
  const token = ++generation;
  open.value = true;
  tab.value = 'channels';
  environment.value = undefined;
  error.value = '';
  environmentLoading.value = true;
  try {
    const result = await getMigrationEnvironment();
    if (!open.value || token !== generation) return;
    environment.value = result.targetEnvironment;
    await loadPlan();
  } catch (e) {
    if (token === generation)
      error.value = e instanceof Error ? e.message : '无法确认当前环境';
  } finally {
    environmentLoading.value = false;
  }
}

function close() {
  if (executing.value) return;
  ++generation;
  open.value = false;
}

async function execute() {
  if (!canExecute.value) return;
  executing.value = true;
  try {
    const result = await executeChannelMigration(
      selectedIds.value,
      planHash.value,
    );
    message.success(
      `迁移完成：${result.channelCount} 个渠道、${result.rateCount} 条费率`,
    );
    emit('success');
    await loadPlan();
  } catch (e) {
    error.value =
      e instanceof Error ? e.message : '执行请求失败；可重试同一计划确认结果';
  } finally {
    executing.value = false;
  }
}

watch(selectedIds, () => {
  confirmed.value = false;
});
defineExpose({ show });
</script>

<template>
  <Modal
    :closable="!executing"
    :footer="null"
    :mask-closable="false"
    :open="open"
    :width="'min(94vw, 920px)'"
    title="渠道与账户同步"
    centered
    @cancel="close"
  >
    <p v-if="environmentLoading" class="py-4 text-sm">正在核对目标环境…</p>
    <p v-if="error" role="alert" class="text-destructive mb-4 text-sm">
      {{ error }}
    </p>
    <Button v-if="!environment && !environmentLoading" @click="show"
      >重新连接</Button
    >
    <Tabs v-if="environment" v-model:active-key="tab">
      <Tabs.TabPane
        key="channels"
        tab="1. 渠道同步"
        :disabled="executing || loading"
      />
      <Tabs.TabPane
        key="accounts"
        tab="2. 渠道账户同步"
        :disabled="executing || loading"
      />
    </Tabs>
    <AccountMigrationPanel
      v-if="open && environment && tab === 'accounts'"
      :environment="environment"
      @success="emit('success')"
    />
    <section v-if="environment && tab === 'channels'" class="space-y-4">
      <div class="bg-muted/30 grid gap-3 rounded-lg border p-4 sm:grid-cols-3">
        <div>
          <div class="text-muted-foreground text-xs">目标环境</div>
          <Tag
            :color="environment === 'PRODUCTION' ? 'orange' : 'blue'"
            class="mt-1"
          >
            {{ environment === 'PRODUCTION' ? '生产' : '测试' }}
          </Tag>
        </div>
        <div>
          <div class="text-muted-foreground text-xs">未映射渠道</div>
          <div class="mt-1 text-sm font-medium">{{ rows.length }} 个</div>
        </div>
        <div>
          <div class="text-muted-foreground text-xs">已选择</div>
          <div class="mt-1 text-sm font-medium">
            {{ selectedIds.length }} 个
          </div>
        </div>
      </div>

      <p class="text-muted-foreground text-sm">
        系统只迁移尚未映射的老渠道及其费率。执行前会重新校验来源、目标实例和计划哈希。
      </p>

      <div class="max-h-[var(--adpulse-popup-table-height)] overflow-auto">
        <ShadcnDataTable
          :columns="columns"
          :data="rows"
          :empty-text="loading ? '正在扫描老库渠道' : '没有待迁移的新渠道'"
          :loading="loading"
          :paginate="false"
          row-key="sourceId"
        >
          <template #header-select>
            <Checkbox
              :checked="allSelected"
              :disabled="availableRows.length === 0 || loading || executing"
              @update:checked="toggleAll"
            />
          </template>
          <template #cell-select="{ record }">
            <Checkbox
              :checked="selectedIds.includes(record.sourceId)"
              :disabled="record.action !== 'INSERT' || loading || executing"
              @update:checked="toggleRow(record.sourceId, $event)"
            />
          </template>
          <template #cell-channelName="{ record }"
            ><span class="whitespace-pre-wrap">{{
              record.channelName
            }}</span></template
          >
          <template #cell-action="{ record }">
            <Tag :color="record.action === 'INSERT' ? 'green' : 'red'">
              {{ record.action === 'INSERT' ? '可迁移' : '存在冲突' }}
            </Tag>
            <span v-if="record.conflict" class="ml-2 text-xs text-red-600">
              {{ record.conflict }}
            </span>
          </template>
        </ShadcnDataTable>
      </div>

      <label class="flex items-start gap-2 rounded-md border p-3 text-sm">
        <Checkbox
          v-model:checked="confirmed"
          :disabled="executing || loading"
        />
        <span>
          我已确认当前目标为{{
            environment === 'PRODUCTION' ? '生产' : '测试'
          }}环境， 并同意迁移所选渠道及关联费率。
        </span>
      </label>

      <div class="flex flex-wrap justify-between gap-2 border-t pt-4">
        <Button :disabled="loading || executing" @click="loadPlan"
          >重新扫描</Button
        >
        <div class="flex gap-2">
          <Button :disabled="executing" @click="close">取消</Button>
          <Button
            :disabled="!canExecute"
            :loading="executing"
            type="primary"
            @click="execute"
          >
            确认迁移
          </Button>
        </div>
      </div>
    </section>
  </Modal>
</template>
