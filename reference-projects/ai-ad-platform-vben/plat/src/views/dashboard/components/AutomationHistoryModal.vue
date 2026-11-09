<script setup lang="ts">
import type {
  RuleRecord,
  SuggestedAction,
} from '#/api/advertisement/automated-rule';

import { computed, reactive, ref, watch } from 'vue';

import {
  Button,
  Input,
  Modal,
  Pagination,
  Select,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { listHistoryRecords } from '#/api/advertisement/automated-rule';

interface Props {
  open: boolean;
}
interface Emits {
  (e: 'update:open', value: boolean): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const modalOpen = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val),
});

const loading = ref(false);
const records = ref<RuleRecord[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const agentLines = ref<string[]>([]);

const filter = reactive({
  keyword: '',
  agent_line: undefined as string | undefined,
  source_type: undefined as string | undefined,
  status: undefined as string | undefined,
});

const statusOptions = [
  { label: '全部', value: undefined },
  { label: '待处理', value: 'pending' },
  { label: '已执行', value: 'executed' },
  { label: '已忽略', value: 'ignored' },
  { label: '失败', value: 'failed' },
  { label: '预览', value: 'dry_run' },
];

const sourceOptions = [
  { label: '全部', value: undefined },
  { label: '规则', value: 'rule' },
  { label: 'AI', value: 'ai' },
  { label: '手工', value: 'manual' },
];

const columns = [
  { key: 'rule_name', title: '规则名', width: 150, ellipsis: true },
  { key: 'agent_line', title: '代理线', width: 130, ellipsis: true },
  { key: 'account_id', title: '账户', width: 140, ellipsis: true },
  { key: 'object_name', title: '广告系列', width: 160, ellipsis: true },
  { key: 'status', title: '状态', width: 90 },
  { key: 'execution_record', title: '执行记录', width: 220 },
  { key: 'message', title: '消息', width: 180, ellipsis: true },
  { key: 'checked_at', title: '时间', width: 160 },
];

function actionTagColor(label: string): string {
  if (!label) return 'default';
  if (
    label.includes('暂停') ||
    label.includes('关闭') ||
    label.includes('停止')
  )
    return 'orange';
  if (
    label.includes('开启') ||
    label.includes('恢复') ||
    label.includes('启动')
  )
    return 'green';
  if (
    label.includes('提高') ||
    label.includes('增加') ||
    label.includes('上调')
  )
    return 'blue';
  if (
    label.includes('降低') ||
    label.includes('减少') ||
    label.includes('下调')
  )
    return 'gold';
  return 'purple';
}

const agentLineOptions = computed(() => [
  { label: '全部', value: undefined },
  ...agentLines.value.map((v) => ({ label: v, value: v })),
]);

async function loadPage() {
  loading.value = true;
  try {
    const result = await listHistoryRecords({
      page: page.value,
      page_size: pageSize.value,
      keyword: filter.keyword || undefined,
      agent_line: filter.agent_line,
      source_type: filter.source_type,
      status: filter.status,
    });
    records.value = result.items ?? [];
    total.value = result.total ?? 0;
    if ((result as any).filter_options?.agent_lines?.length) {
      agentLines.value = (result as any).filter_options.agent_lines;
    }
  } catch {
    // handled by interceptor
  } finally {
    loading.value = false;
  }
}

function resetAndLoad() {
  page.value = 1;
  loadPage();
}

function close() {
  modalOpen.value = false;
  page.value = 1;
  total.value = 0;
  Object.assign(filter, {
    keyword: '',
    agent_line: undefined,
    source_type: undefined,
    status: undefined,
  });
}

watch(
  () => ({ ...filter }),
  () => {
    if (props.open) resetAndLoad();
  },
);

watch(
  () => props.open,
  (val) => {
    if (val) {
      page.value = 1;
      loadPage();
    }
  },
);

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  pending: { color: 'processing', label: '待处理' },
  executed: { color: 'success', label: '已执行' },
  ignored: { color: 'default', label: '已忽略' },
  failed: { color: 'error', label: '失败' },
  dry_run: { color: 'cyan', label: '预览' },
};
</script>

<template>
  <Modal
    :open="modalOpen"
    :footer="null"
    width="1100px"
    destroy-on-close
    @update:open="
      (v) => {
        if (!v) close();
      }
    "
  >
    <template #title>
      <span>自动化执行记录</span>
    </template>

    <div>
      <!-- 筛选栏 -->
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <Input
          v-model:value="filter.keyword"
          allow-clear
          class="w-52"
          placeholder="关键词搜索"
          @change="resetAndLoad"
        >
          <template #prefix>
            <span
              aria-hidden="true"
              class="icon-[ant-design--search-outlined] text-sm text-gray-400"
            ></span>
          </template>
        </Input>
        <Select
          v-model:value="filter.agent_line"
          :options="agentLineOptions"
          allow-clear
          show-search
          :filter-option="
            (input, opt) =>
              ((opt?.label as string) ?? '')
                .toLowerCase()
                .includes(input.toLowerCase())
          "
          class="w-36"
          placeholder="代理线 全部"
        />
        <Select
          v-model:value="filter.status"
          :options="statusOptions"
          allow-clear
          class="w-28"
          placeholder="状态 全部"
        />
        <Select
          v-model:value="filter.source_type"
          :options="sourceOptions"
          allow-clear
          class="w-28"
          placeholder="来源 全部"
        />
        <Button
          type="link"
          class="!px-0"
          @click="
            Object.assign(filter, {
              keyword: '',
              agent_line: undefined,
              status: undefined,
              source_type: undefined,
            })
          "
        >
          清空筛选
        </Button>
      </div>

      <!-- 表格 -->
      <Table
        :columns="columns"
        :data-source="records"
        :loading="loading"
        :pagination="false"
        :row-key="(r) => r.id"
        :scroll="{ x: 1000, y: 380 }"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <Tag :color="STATUS_MAP[record.status]?.color" class="text-xs">
              {{ STATUS_MAP[record.status]?.label ?? record.status }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'execution_record'">
            <template
              v-if="(record as any).notification_item?.suggested_action"
            >
              <div class="flex flex-wrap items-center gap-1 text-xs">
                <Tag
                  :color="
                    actionTagColor(
                      (record as any).notification_item.suggested_action.label,
                    )
                  "
                  class="mr-0"
                >
                  {{ (record as any).notification_item.suggested_action.label }}
                </Tag>
                <template
                  v-if="
                    (
                      (record as any).notification_item
                        .suggested_action as SuggestedAction
                    ).type !== 'status'
                  "
                >
                  <span class="text-gray-800">
                    ${{
                      (
                        (record as any).notification_item
                          .suggested_action as SuggestedAction
                      ).current_value ?? '-'
                    }}
                  </span>
                  <span class="text-gray-400">→</span>
                  <span class="font-medium text-teal-600">
                    ${{
                      (
                        (record as any).notification_item
                          .suggested_action as SuggestedAction
                      ).target_value ?? '-'
                    }}
                  </span>
                </template>
              </div>
            </template>
            <span v-else class="text-xs text-gray-400">-</span>
          </template>
          <template
            v-else-if="
              column.key &&
              ['rule_name', 'object_name', 'message'].includes(
                column.key as string,
              )
            "
          >
            <Tooltip :title="(record as any)[column.key as string]">
              <span
                class="text-xs"
                :class="column.key === 'message' ? 'text-gray-600' : ''"
              >
                {{ (record as any)[column.key as string] || '-' }}
              </span>
            </Tooltip>
          </template>
          <template v-else>
            <span class="text-xs">{{
              column.key ? (record as any)[column.key as string] || '-' : '-'
            }}</span>
          </template>
        </template>
      </Table>

      <!-- 底部 -->
      <div class="mt-3 flex items-center justify-between">
        <span class="text-xs text-gray-400">共 {{ total }} 条</span>
        <div class="flex items-center gap-3">
          <Pagination
            v-model:current="page"
            v-model:page-size="pageSize"
            :total="total"
            :show-size-changer="true"
            :page-size-options="['10', '20', '50']"
            show-quick-jumper
            @change="loadPage"
            @show-size-change="
              () => {
                page = 1;
                loadPage();
              }
            "
          />
          <Button @click="close">关闭</Button>
        </div>
      </div>
    </div>
  </Modal>
</template>
