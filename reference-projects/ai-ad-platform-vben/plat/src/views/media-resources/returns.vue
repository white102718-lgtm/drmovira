<script lang="ts" setup>
import type { TablePaginationConfig } from 'ant-design-vue';

import type {
  AssetReturnOutcome,
  AssetReturnRecord,
  AssetReturnStatus,
} from '#/api';

import { computed, onActivated, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Row,
  Select,
  Table,
  Tag,
} from 'ant-design-vue';

import { assetFlowApi, assetReturnApi } from '#/api';
import {
  createPositiveIntegerRouteQueryField,
  createStringRouteQueryField,
  useRouteListQuery,
} from '#/composables/use-route-list-query';

import BusinessPageHeader from '../components/BusinessPageHeader.vue';
import {
  inventoryAssetTypeFilterOptions,
  resolveInventoryAssetTypeFilter,
} from './components/asset-type-filter';
import { resolveInventoryAssetTypeLabel } from './components/asset-types';
import MediaResourcePage from './components/MediaResourcePage.vue';

const loading = ref(false);
const summaryLoading = ref(false);
const errorMessage = ref('');
const keyword = ref('');
const statusFilter = ref<'all' | AssetReturnStatus>('all');
const assetTypeFilter = ref('all');
const records = ref<AssetReturnRecord[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const completeOpen = ref(false);
const submitting = ref(false);
const activeReturn = ref<AssetReturnRecord>();
const assetSecretDataById = ref(new Map<string, string | undefined>());
const summaryCounts = reactive({ completed: 0, pending: 0, total: 0 });
const completeForm = reactive<{ outcome: AssetReturnOutcome }>({
  outcome: 'AVAILABLE',
});

const columns = [
  { dataIndex: 'returnNo', key: 'returnNo', title: '回收单', width: 210 },
  { key: 'asset', title: '资产', width: 250 },
  { key: 'ownership', title: '归属 / 使用人', width: 230 },
  { dataIndex: 'reason', key: 'reason', title: '回收原因', width: 270 },
  { key: 'status', title: '状态', width: 130 },
  { key: 'timeline', title: '处理时间', width: 220 },
  { key: 'actions', title: '操作', width: 120, fixed: 'right' as const },
];

const statusMeta: Record<AssetReturnStatus, { color: string; label: string }> =
  {
    COMPLETED: { color: 'green', label: '已完成' },
    PENDING: { color: 'orange', label: '待处理' },
  };

const outcomeMeta: Record<AssetReturnOutcome, string> = {
  AVAILABLE: '已重新入库',
  DISABLED: '已停用',
};

const statusOptions = [
  { label: '全部状态', value: 'all' },
  { label: '待处理', value: 'PENDING' },
  { label: '已完成', value: 'COMPLETED' },
];

const outcomeOptions = [
  { label: '重新进入可用库存', value: 'AVAILABLE' },
  { label: '停用并退出可用库存', value: 'DISABLED' },
];

const route = useRoute();
const router = useRouter();
useRouteListQuery({
  fields: {
    assetType: createStringRouteQueryField(assetTypeFilter, {
      allowedValues: inventoryAssetTypeFilterOptions.map((item) => item.value),
      defaultValue: 'all',
    }),
    page: createPositiveIntegerRouteQueryField(page, { defaultValue: 1 }),
    pageSize: createPositiveIntegerRouteQueryField(pageSize, {
      allowedValues: [10, 20, 50, 100],
      defaultValue: 20,
    }),
    q: createStringRouteQueryField(keyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
    status: createStringRouteQueryField(statusFilter, {
      allowedValues: statusOptions.map((item) => item.value),
      defaultValue: 'all',
    }),
  },
  onRouteApplied: () => void loadReturns(),
  route,
  router,
});

const summary = computed(() => [
  {
    icon: 'lucide:clock-3',
    label: '待完成回收',
    tone: 'bg-amber-50 text-amber-600',
    value: summaryCounts.pending,
  },
  {
    icon: 'lucide:circle-check-big',
    label: '已完成回收',
    tone: 'bg-emerald-50 text-emerald-600',
    value: summaryCounts.completed,
  },
  {
    icon: 'lucide:history',
    label: '全部回收记录',
    tone: 'bg-blue-50 text-blue-600',
    value: summaryCounts.total,
  },
]);

const pagination = computed<TablePaginationConfig>(() => ({
  current: page.value,
  pageSize: pageSize.value,
  showSizeChanger: true,
  showTotal: (value) => `共 ${value} 条`,
  total: total.value,
}));

function formatTime(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false });
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** Ant Design 表格插槽会丢失行泛型，在此统一恢复资产回收记录类型。 */
function returnRecord(value: unknown) {
  return value as AssetReturnRecord;
}

function returnStatusMeta(value: unknown) {
  return statusMeta[returnRecord(value).status];
}

function returnOutcomeLabel(value: unknown) {
  const outcome = returnRecord(value).outcome;
  return outcome ? outcomeMeta[outcome] : '';
}

async function loadReturns() {
  loading.value = true;
  errorMessage.value = '';
  try {
    const assetTypeParams = resolveInventoryAssetTypeFilter(
      assetTypeFilter.value,
    );
    const [result, assets] = await Promise.all([
      assetReturnApi.page({
        ...assetTypeParams,
        keyword: keyword.value.trim() || undefined,
        page: page.value,
        pageSize: pageSize.value,
        status: statusFilter.value === 'all' ? undefined : statusFilter.value,
      }),
      assetFlowApi.assets(),
    ]);
    records.value = result.items;
    total.value = result.total;
    const lastPage = Math.max(1, Math.ceil(result.total / pageSize.value));
    if (page.value > lastPage) {
      page.value = lastPage;
      await loadReturns();
      return;
    }
    assetSecretDataById.value = new Map(
      assets.map((asset) => [asset.id, asset.secretData]),
    );
  } catch (error) {
    records.value = [];
    total.value = 0;
    errorMessage.value = getErrorMessage(error, '回收记录加载失败');
  } finally {
    loading.value = false;
  }
}

async function loadSummary() {
  summaryLoading.value = true;
  try {
    const result = await assetReturnApi.summary();
    Object.assign(summaryCounts, result);
  } catch (error) {
    errorMessage.value ||= getErrorMessage(error, '回收统计加载失败');
  } finally {
    summaryLoading.value = false;
  }
}

async function refreshPage() {
  await Promise.all([loadReturns(), loadSummary()]);
}

function handleSearch() {
  page.value = 1;
  void loadReturns();
}

function handleStatusChange() {
  page.value = 1;
  void loadReturns();
}

function handleAssetTypeChange() {
  page.value = 1;
  void loadReturns();
}

function handleReset() {
  keyword.value = '';
  statusFilter.value = 'all';
  assetTypeFilter.value = 'all';
  page.value = 1;
  void loadReturns();
}

function handleTableChange(value: TablePaginationConfig) {
  const nextPageSize = value.pageSize ?? pageSize.value;
  page.value = nextPageSize === pageSize.value ? (value.current ?? 1) : 1;
  pageSize.value = nextPageSize;
  void loadReturns();
}

function openComplete(value: unknown) {
  activeReturn.value = returnRecord(value);
  completeForm.outcome = 'AVAILABLE';
  completeOpen.value = true;
}

async function completeReturn() {
  if (!activeReturn.value) return;
  submitting.value = true;
  try {
    await assetReturnApi.complete(activeReturn.value.id, completeForm.outcome);
    message.success(
      completeForm.outcome === 'AVAILABLE'
        ? '回收完成，资产已重新入库'
        : '回收完成，资产已停用',
    );
    completeOpen.value = false;
    await refreshPage();
  } catch (error) {
    message.error(getErrorMessage(error, '完成回收失败'));
  } finally {
    submitting.value = false;
  }
}

onMounted(() => void refreshPage());
let hasActivatedReturnsPage = false;
onActivated(() => {
  if (!hasActivatedReturnsPage) {
    hasActivatedReturnsPage = true;
    return;
  }
  void refreshPage();
});
</script>

<template>
  <MediaResourcePage>
    <div class="flex w-full min-w-0 flex-col gap-4">
      <BusinessPageHeader
        description="核对回收申请，清理资产绑定，并决定重新入库或停用。"
        icon="lucide:package-open"
        title="资源回收"
      >
        <template #extra>
          <Button :loading="loading || summaryLoading" @click="refreshPage">
            <IconifyIcon icon="lucide:refresh-cw" />刷新
          </Button>
        </template>
      </BusinessPageHeader>

      <Row :gutter="[16, 16]">
        <Col v-for="item in summary" :key="item.label" :xs="24" :sm="8">
          <Card :bordered="false" class="h-full shadow-sm">
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-sm text-slate-500">{{ item.label }}</div>
                <div class="mt-1 text-2xl font-semibold text-slate-900">
                  {{ item.value }}
                </div>
              </div>
              <span
                class="grid size-10 place-items-center rounded-xl"
                :class="item.tone"
              >
                <IconifyIcon :icon="item.icon" class="text-xl" />
              </span>
            </div>
          </Card>
        </Col>
      </Row>

      <Alert
        v-if="errorMessage"
        :message="errorMessage"
        closable
        show-icon
        type="error"
        @close="errorMessage = ''"
      />

      <Card :bordered="false" class="shadow-sm">
        <div class="mb-4 flex flex-col gap-3 md:flex-row">
          <Input.Search
            v-model:value="keyword"
            allow-clear
            class="w-full md:max-w-sm"
            placeholder="搜索回收单、资产、归属或申请人"
            @search="handleSearch"
          />
          <Select
            v-model:value="statusFilter"
            aria-label="按回收状态筛选"
            :options="statusOptions"
            class="w-full md:w-40"
            @change="handleStatusChange"
          />
          <Select
            v-model:value="assetTypeFilter"
            aria-label="按资产类型筛选"
            :options="inventoryAssetTypeFilterOptions"
            class="w-full md:w-44"
            @change="handleAssetTypeChange"
          />
          <Button @click="handleReset">重置</Button>
        </div>
        <Table
          :columns="columns"
          :data-source="records"
          :loading="loading"
          :pagination="pagination"
          :scroll="{ x: 1430 }"
          row-key="id"
          @change="handleTableChange"
        >
          <template #emptyText>
            <Empty description="暂无资源回收记录" />
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'returnNo'">
              <div class="font-medium text-slate-900">
                {{ record.returnNo }}
              </div>
              <div class="mt-1 text-xs text-slate-500">
                来源申请：{{ record.applicationId || '-' }}
              </div>
            </template>
            <template v-else-if="column.key === 'asset'">
              <div class="font-medium text-slate-800">
                {{ record.assetName }}
              </div>
              <div class="mt-1 font-mono text-xs text-slate-500">
                {{
                  resolveInventoryAssetTypeLabel(
                    record.assetType,
                    assetSecretDataById.get(record.assetId),
                  )
                }}
                ·
                {{ record.assetCode }}
              </div>
            </template>
            <template v-else-if="column.key === 'ownership'">
              <div>
                {{ record.channelName || record.projectName || '未指定归属' }}
              </div>
              <div class="mt-1 text-xs text-slate-500">
                原使用人：{{ record.assigneeName || '-' }}
              </div>
            </template>
            <template v-else-if="column.key === 'reason'">
              <div class="line-clamp-2 text-sm text-slate-700">
                {{ record.reason }}
              </div>
              <div class="mt-1 text-xs text-slate-500">
                申请人：{{ record.requestedByName }}
              </div>
            </template>
            <template v-else-if="column.key === 'status'">
              <Tag :color="returnStatusMeta(record).color">
                {{ returnStatusMeta(record).label }}
              </Tag>
              <div v-if="record.outcome" class="mt-1 text-xs text-slate-500">
                {{ returnOutcomeLabel(record) }}
              </div>
            </template>
            <template v-else-if="column.key === 'timeline'">
              <div>申请：{{ formatTime(record.createdAt) }}</div>
              <div
                v-if="record.completedAt"
                class="mt-1 text-xs text-slate-500"
              >
                完成：{{ formatTime(record.completedAt) }} ·
                {{ record.completedByName }}
              </div>
            </template>
            <template v-else-if="column.key === 'actions'">
              <Button
                v-if="record.status === 'PENDING'"
                type="link"
                class="px-0"
                @click="openComplete(record)"
              >
                完成回收
              </Button>
              <span v-else class="text-sm text-slate-400">已处理</span>
            </template>
          </template>
        </Table>
      </Card>
    </div>

    <Modal
      v-model:open="completeOpen"
      :confirm-loading="submitting"
      ok-text="确认完成"
      title="完成资源回收"
      @ok="completeReturn"
    >
      <Alert
        class="mb-4"
        message="请先确认相关业务已停止，资产权限与外部绑定已清理。"
        show-icon
        type="warning"
      />
      <div class="mb-4 rounded-lg bg-slate-50 p-3 text-sm">
        <div class="font-medium text-slate-800">
          {{ activeReturn?.assetName }}
        </div>
        <div class="mt-1 text-slate-500">
          {{ activeReturn?.assetCode }} ·
          {{
            activeReturn?.channelName ||
            activeReturn?.projectName ||
            '未指定归属'
          }}
        </div>
      </div>
      <Form layout="vertical">
        <FormItem label="回收结果" required>
          <Select
            v-model:value="completeForm.outcome"
            :options="outcomeOptions"
          />
        </FormItem>
      </Form>
      <Alert
        v-if="completeForm.outcome === 'DISABLED'"
        message="停用后资产不会回到可用库存，后续需管理员重新启用。"
        show-icon
        type="error"
      />
      <Alert
        v-else
        message="将解除使用人和来源申请绑定，资产重新进入可用库存。"
        show-icon
        type="success"
      />
    </Modal>
  </MediaResourcePage>
</template>
