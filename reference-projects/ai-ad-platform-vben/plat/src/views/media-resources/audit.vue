<script lang="ts" setup>
import type { TablePaginationConfig } from 'ant-design-vue';

import { computed, onActivated, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
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
import MediaResourcePage from './components/MediaResourcePage.vue';

interface AuditRecord {
  action: string;
  actorName: string;
  createdAt: string;
  entity: string;
  id: string;
  message: string;
  projectName: string;
  result: 'failed' | 'success';
}

const loading = ref(false);
const errorMessage = ref('');
const errorType = ref<'error' | 'warning'>('warning');
const keyword = ref('');
const actionFilter = ref('all');
const operatorFilter = ref('all');
const logs = ref<AuditRecord[]>([]);
const page = ref(1);
const pageSize = ref(15);

const actionMeta: Record<string, { color: string; label: string }> = {
  APPROVED: { color: 'green', label: '审批通过' },
  ASSET_CREATED: { color: 'blue', label: '资产入库' },
  COMPLETED: { color: 'cyan', label: '处理与分配' },
  CONFIG_PUBLISHED: { color: 'purple', label: '配置发布' },
  REJECTED: { color: 'red', label: '审批驳回' },
  RETURN_COMPLETED: { color: 'green', label: '完成回收' },
  RETURN_REQUESTED: { color: 'orange', label: '发起回收' },
  SUBMITTED: { color: 'gold', label: '提交申请' },
};

const route = useRoute();
const router = useRouter();
const { isApplyingRoute } = useRouteListQuery({
  fields: {
    action: createStringRouteQueryField(actionFilter, {
      defaultValue: 'all',
    }),
    operator: createStringRouteQueryField(operatorFilter, {
      defaultValue: 'all',
    }),
    page: createPositiveIntegerRouteQueryField(page, { defaultValue: 1 }),
    pageSize: createPositiveIntegerRouteQueryField(pageSize, {
      allowedValues: [10, 15, 20, 50, 100],
      defaultValue: 15,
    }),
    q: createStringRouteQueryField(keyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
  },
  route,
  router,
});

const actionOptions = computed(() => [
  { label: '全部动作', value: 'all' },
  ...[...new Set(logs.value.map((item) => item.action))].map((value) => ({
    label: actionMeta[value]?.label || value,
    value,
  })),
]);

const operatorOptions = computed(() => [
  { label: '全部操作人', value: 'all' },
  ...[...new Set(logs.value.map((item) => item.actorName))]
    .sort((left, right) => left.localeCompare(right, 'zh-CN'))
    .map((value) => ({ label: value, value })),
]);

const filteredLogs = computed(() => {
  const query = keyword.value.trim().toLowerCase();
  return logs.value.filter(
    (item) =>
      (actionFilter.value === 'all' || item.action === actionFilter.value) &&
      (operatorFilter.value === 'all' ||
        item.actorName === operatorFilter.value) &&
      (!query ||
        [item.actorName, item.entity, item.message, item.projectName]
          .join(' ')
          .toLowerCase()
          .includes(query)),
  );
});

const pagination = computed<TablePaginationConfig>(() => ({
  current: page.value,
  pageSize: pageSize.value,
  showSizeChanger: true,
  total: filteredLogs.value.length,
}));

function handleTableChange(next: TablePaginationConfig) {
  const nextPageSize = next.pageSize ?? pageSize.value;
  page.value = nextPageSize === pageSize.value ? (next.current ?? 1) : 1;
  pageSize.value = nextPageSize;
}

watch([keyword, actionFilter, operatorFilter], () => {
  if (!isApplyingRoute.value) page.value = 1;
});

watch([() => filteredLogs.value.length, pageSize], ([total]) => {
  const lastPage = Math.max(1, Math.ceil(total / pageSize.value));
  if (page.value > lastPage) page.value = lastPage;
});

const summary = computed(() => [
  {
    icon: 'lucide:scroll-text',
    label: '审计记录',
    tone: 'bg-blue-50 text-blue-600',
    value: logs.value.length,
  },
  {
    icon: 'lucide:users',
    label: '操作人数',
    tone: 'bg-violet-50 text-violet-600',
    value: new Set(logs.value.map((item) => item.actorName)).size,
  },
  {
    icon: 'lucide:circle-x',
    label: '失败操作',
    tone: 'bg-red-50 text-red-600',
    value: logs.value.filter((item) => item.result === 'failed').length,
  },
]);

const columns = [
  { dataIndex: 'createdAt', key: 'createdAt', title: '时间', width: 180 },
  { key: 'action', title: '动作', width: 130 },
  { dataIndex: 'actorName', key: 'actorName', title: '操作人', width: 150 },
  { dataIndex: 'entity', key: 'entity', title: '业务对象', width: 230 },
  {
    dataIndex: 'projectName',
    key: 'projectName',
    title: '归属项目',
    width: 220,
  },
  { dataIndex: 'message', key: 'message', title: '操作说明', width: 360 },
  { key: 'result', title: '结果', width: 100 },
];

async function loadLogs() {
  loading.value = true;
  errorMessage.value = '';
  try {
    // 三类记录来自不同接口，单个数据源异常时仍展示其余真实记录。
    const [assetsResult, applicationsResult, configsResult, returnsResult] =
      await Promise.allSettled([
        assetFlowApi.assets(undefined, undefined, {
          skipErrorMessage: true,
        }),
        assetFlowApi.applications({ skipErrorMessage: true }),
        assetFlowApi.configs({ skipErrorMessage: true }),
        assetReturnApi.page({ page: 1, pageSize: 100 }),
      ]);
    const sources = [
      { label: '资产入库', result: assetsResult },
      { label: '申请审批', result: applicationsResult },
      { label: '审批配置', result: configsResult },
      { label: '资产回收', result: returnsResult },
    ];
    const failedSources = sources
      .filter(({ result }) => result.status === 'rejected')
      .map(({ label }) => label);
    const assets =
      assetsResult.status === 'fulfilled' ? assetsResult.value : [];
    const applications =
      applicationsResult.status === 'fulfilled' ? applicationsResult.value : [];
    const configs =
      configsResult.status === 'fulfilled' ? configsResult.value : [];
    const returns =
      returnsResult.status === 'fulfilled' ? returnsResult.value.items : [];

    if (failedSources.length > 0) {
      const hasAvailableSource = failedSources.length < sources.length;
      errorType.value = hasAvailableSource ? 'warning' : 'error';
      errorMessage.value = hasAvailableSource
        ? `${failedSources.join('、')}记录暂时不可用，已展示其余操作记录。`
        : '操作记录加载失败，请稍后重试。';
    }
    const applicationLogs = applications.flatMap((application) =>
      (application.approvalLogs ?? []).map((log) => ({
        action: log.action,
        actorName: log.actorName,
        createdAt: log.createdAt,
        entity: `${application.applicationNo} · ${application.title}`,
        id: `application-${application.id}-${log.id}`,
        message:
          log.action === 'COMPLETED'
            ? `资产处理与分配完成：${log.remark || '无备注'}`
            : `${log.nodeName || '审批流程'}：${log.remark || '无备注'}`,
        projectName: String(
          application.formData?.projectName ??
            application.formData?.project ??
            '未关联项目',
        ),
        result: 'success' as const,
      })),
    );
    const assetLogs: AuditRecord[] = assets.map((asset) => ({
      action: 'ASSET_CREATED',
      actorName: '资产管理员',
      createdAt: asset.createdAt,
      entity: `${asset.assetName} · ${asset.assetCode}`,
      id: `asset-${asset.id}`,
      message: '资产已入库并纳入项目库存',
      projectName: asset.projectName || '未归属项目',
      result: 'success',
    }));
    const configLogs: AuditRecord[] = configs.map((config) => ({
      action: 'CONFIG_PUBLISHED',
      actorName: config.handlerName || '流程管理员',
      createdAt: config.updatedAt,
      entity: config.name,
      id: `config-${config.id}`,
      message: `审批配置已发布，包含 ${config.nodes.length} 个节点`,
      projectName: '全局流程配置',
      result: 'success',
    }));
    const returnLogs: AuditRecord[] = returns.flatMap((record) => {
      const projectName =
        record.channelName || record.projectName || '未指定归属';
      const requested: AuditRecord = {
        action: 'RETURN_REQUESTED',
        actorName: record.requestedByName,
        createdAt: record.createdAt,
        entity: `${record.returnNo} · ${record.assetName}`,
        id: `return-${record.id}-requested`,
        message: `发起资产回收：${record.reason}`,
        projectName,
        result: 'success',
      };
      if (record.status !== 'COMPLETED' || !record.completedAt) {
        return [requested];
      }
      return [
        requested,
        {
          action: 'RETURN_COMPLETED',
          actorName: record.completedByName || '资源管理员',
          createdAt: record.completedAt,
          entity: `${record.returnNo} · ${record.assetName}`,
          id: `return-${record.id}-completed`,
          message:
            record.outcome === 'DISABLED'
              ? '资产回收完成并停用'
              : '资产回收完成并重新入库',
          projectName,
          result: 'success',
        },
      ];
    });
    logs.value = [
      ...applicationLogs,
      ...assetLogs,
      ...configLogs,
      ...returnLogs,
    ].sort((left, right) => right.createdAt.localeCompare(left.createdAt));
    if (
      actionFilter.value !== 'all' &&
      !logs.value.some((item) => item.action === actionFilter.value)
    ) {
      actionFilter.value = 'all';
    }
    if (
      operatorFilter.value !== 'all' &&
      !logs.value.some((item) => item.actorName === operatorFilter.value)
    ) {
      operatorFilter.value = 'all';
    }
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : '审计记录加载失败';
  } finally {
    loading.value = false;
  }
}

onMounted(loadLogs);
let hasActivatedAuditPage = false;
onActivated(() => {
  if (!hasActivatedAuditPage) {
    hasActivatedAuditPage = true;
    return;
  }
  void loadLogs();
});
</script>

<template>
  <MediaResourcePage>
    <div class="flex w-full min-w-0 flex-col gap-[var(--adpulse-section-gap)]">
      <BusinessPageHeader
        description="追踪资源申请、分配、回收和配置变更的关键操作。"
        icon="lucide:scroll-text"
        title="操作记录"
      >
        <template #extra>
          <Button :loading="loading" @click="loadLogs">
            <IconifyIcon icon="lucide:refresh-cw" />刷新
          </Button>
        </template>
      </BusinessPageHeader>

      <Row :gutter="[12, 12]">
        <Col v-for="item in summary" :key="item.label" :xs="24" :sm="8">
          <Card :bordered="false" class="h-full shadow-sm">
            <div class="flex items-center justify-between gap-3">
              <div>
                <div class="text-sm text-slate-500">{{ item.label }}</div>
                <div class="mt-0.5 text-xl font-semibold text-slate-900">
                  {{ item.value }}
                </div>
              </div>
              <span
                class="grid size-8 place-items-center rounded-lg"
                :class="item.tone"
              >
                <IconifyIcon :icon="item.icon" class="text-base" />
              </span>
            </div>
          </Card>
        </Col>
      </Row>

      <Alert
        message="操作记录只追加、不覆盖；筛选不会改变原始业务数据。"
        show-icon
        type="info"
      />

      <Alert
        v-if="errorMessage"
        show-icon
        :type="errorType"
        :message="errorMessage"
      />
      <Card :bordered="false" class="shadow-sm">
        <div
          class="mb-3 grid grid-cols-1 gap-2.5 md:grid-cols-[minmax(240px,1fr)_160px_160px]"
        >
          <Input
            v-model:value="keyword"
            allow-clear
            placeholder="搜索对象、项目、操作人或说明"
          >
            <template #prefix><IconifyIcon icon="lucide:search" /></template>
          </Input>
          <Select v-model:value="actionFilter" :options="actionOptions" />
          <Select v-model:value="operatorFilter" :options="operatorOptions" />
        </div>
        <Table
          :columns="columns"
          :data-source="filteredLogs"
          :loading="loading"
          :pagination="pagination"
          :scroll="{ x: 1290 }"
          row-key="id"
          @change="handleTableChange"
        >
          <template #emptyText>
            <Empty description="暂无真实审计记录" />
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'action'">
              <Tag :color="actionMeta[record.action]?.color || 'default'">
                {{ actionMeta[record.action]?.label || record.action }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'result'">
              <Tag :color="record.result === 'success' ? 'green' : 'red'">
                {{ record.result === 'success' ? '成功' : '失败' }}
              </Tag>
            </template>
          </template>
        </Table>
      </Card>
    </div>
  </MediaResourcePage>
</template>
