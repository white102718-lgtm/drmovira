<script setup lang="ts">
import type { Dayjs } from 'dayjs';
import type { TableColumnsType, TablePaginationConfig } from 'ant-design-vue';

import type { SystemLoginLogApi } from '#/api';

import { computed, onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  DatePicker,
  Empty,
  Input,
  Select,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { getLoginLogList } from '#/api';
import {
  createListRouteStateTarget,
  useListRouteState,
} from '#/composables/use-list-route-state';
import dayjs from 'dayjs';

type LoginTimeRange = [Dayjs, Dayjs] | undefined;

const authStageLabels: Record<SystemLoginLogApi.LoginLog['authStage'], string> =
  {
    1: '密码认证',
    2: '首次绑定 MFA',
    3: '验证 MFA',
    4: '飞书扫码',
  };

const columns: TableColumnsType<SystemLoginLogApi.LoginLog> = [
  {
    dataIndex: 'loginAt',
    ellipsis: true,
    key: 'loginAt',
    title: '登录时间',
    width: 180,
  },
  { ellipsis: true, key: 'user', title: '用户', width: 160 },
  {
    dataIndex: 'loginIdentifier',
    ellipsis: true,
    key: 'loginIdentifier',
    title: '登录标识',
    width: 170,
  },
  { ellipsis: true, key: 'authStage', title: '认证阶段', width: 130 },
  { key: 'loginResult', title: '结果', width: 88 },
  {
    dataIndex: 'clientIp',
    ellipsis: true,
    key: 'clientIp',
    title: '客户端 IP',
    width: 130,
  },
  { ellipsis: true, key: 'failureReason', title: '失败信息', width: 250 },
  { ellipsis: true, key: 'userAgent', title: '设备 / 浏览器', width: 320 },
];

const resultOptions = [
  { label: '全部结果', value: 'all' },
  { label: '成功', value: 1 },
  { label: '失败', value: 0 },
];

const authStageOptions = [
  { label: '全部认证阶段', value: 'all' },
  { label: '密码认证', value: 1 },
  { label: '首次绑定 MFA', value: 2 },
  { label: '验证 MFA', value: 3 },
  { label: '飞书扫码', value: 4 },
];

const keyword = ref('');
const clientIp = ref('');
const loginResult = ref<'all' | 0 | 1>('all');
const authStage = ref<'all' | 1 | 2 | 3 | 4>('all');
const timeRange = ref<LoginTimeRange>();
const records = ref<SystemLoginLogApi.LoginLog[]>([]);
const loading = ref(false);
const errorMessage = ref('');
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
let requestSequence = 0;
const routeState = createListRouteStateTarget({
  auth_stage: authStage,
  client_ip: clientIp,
  keyword,
  login_result: loginResult,
  time_range: timeRange,
});
const { commitQueryState, resetQueryState, restoreFromRoute } =
  useListRouteState({
    fields: {
      time_range: {
        codec: {
          parse(value) {
            const values = Array.isArray(value) ? value : [value];
            return values.length === 2 && values[0] && values[1]
              ? [dayjs(values[0]), dayjs(values[1])]
              : undefined;
          },
          serialize(value) {
            return value?.map((item) => item.format('YYYY-MM-DD'));
          },
        },
      },
    },
    onRouteStateRestored: () => loadLoginLogs(),
    pagination: {
      defaultPageSize: 20,
      page,
      pageSize,
    },
    state: routeState,
  });

const pagination = computed<TablePaginationConfig>(() => ({
  current: page.value,
  pageSize: pageSize.value,
  showSizeChanger: true,
  showTotal: (value) => `共 ${value} 条`,
  total: total.value,
}));

function getErrorMessage(error: unknown) {
  return error instanceof Error && error.message
    ? error.message
    : '登录日志加载失败，请稍后重试';
}

function formatTime(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false });
}

/** Ant Design 表格插槽会丢失行泛型，在此统一恢复登录日志类型。 */
function loginLogRecord(value: unknown) {
  return value as SystemLoginLogApi.LoginLog;
}

async function loadLoginLogs() {
  await commitQueryState();
  const currentSequence = ++requestSequence;
  loading.value = true;
  errorMessage.value = '';

  try {
    const [startedAt, endedAt] = timeRange.value ?? [];
    const result = await getLoginLogList({
      authStage: authStage.value === 'all' ? undefined : authStage.value,
      clientIp: clientIp.value.trim() || undefined,
      endedAt: endedAt?.endOf('day').format('YYYY-MM-DDTHH:mm:ss'),
      keyword: keyword.value.trim() || undefined,
      loginResult: loginResult.value === 'all' ? undefined : loginResult.value,
      page: page.value,
      pageSize: pageSize.value,
      startedAt: startedAt?.startOf('day').format('YYYY-MM-DDTHH:mm:ss'),
    });

    // 快速切换分页时只接受最后一次请求，避免旧响应覆盖新数据。
    if (currentSequence !== requestSequence) return;
    records.value = result.items;
    total.value = result.total;
  } catch (error) {
    if (currentSequence !== requestSequence) return;
    records.value = [];
    total.value = 0;
    errorMessage.value = getErrorMessage(error);
  } finally {
    if (currentSequence === requestSequence) loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  void loadLoginLogs();
}

async function handleReset() {
  await resetQueryState();
  await loadLoginLogs();
}

function handleTableChange(value: TablePaginationConfig) {
  page.value = value.current ?? 1;
  pageSize.value = value.pageSize ?? 20;
  void loadLoginLogs();
}

onMounted(async () => {
  await restoreFromRoute();
  await loadLoginLogs();
});
</script>

<template>
  <Page class="system-management-page" content-class="pb-6">
    <div class="mx-auto flex max-w-[1600px] flex-col gap-4">
      <header class="flex items-start gap-3">
        <span
          class="bg-primary/10 text-primary grid size-11 shrink-0 place-items-center rounded-xl"
          aria-hidden="true"
        >
          <IconifyIcon icon="lucide:log-in" class="text-xl" />
        </span>
        <div>
          <h1 class="m-0 text-xl font-semibold">登录日志</h1>
          <p class="mb-0 mt-1 text-sm text-slate-500">
            查看账号登录结果、来源地址和认证过程，及时识别异常访问。
          </p>
        </div>
      </header>

      <Card>
        <div class="ux-filter-form mb-4">
          <Input
            v-model:value="keyword"
            allow-clear
            aria-label="关键词"
            class="ux-filter-search"
            placeholder="账号、显示名称或登录标识"
            @press-enter="handleSearch"
          >
            <template #prefix>
              <IconifyIcon icon="lucide:search" aria-hidden="true" />
            </template>
          </Input>
          <Input
            v-model:value="clientIp"
            allow-clear
            aria-label="客户端 IP"
            class="ux-filter-field"
            placeholder="客户端 IP"
            @press-enter="handleSearch"
          />
          <Select
            v-model:value="loginResult"
            aria-label="登录结果"
            class="ux-filter-field"
            :options="resultOptions"
          />
          <Select
            v-model:value="authStage"
            aria-label="认证阶段"
            class="ux-filter-field"
            :options="authStageOptions"
          />
          <DatePicker.RangePicker
            v-model:value="timeRange"
            class="ux-filter-field"
            aria-label="登录时间范围"
            :placeholder="['开始日期', '结束日期']"
          />
          <div class="ux-filter-actions">
            <Button type="primary" :loading="loading" @click="handleSearch">
              查询
            </Button>
            <Button :disabled="loading" @click="handleReset">重置</Button>
          </div>
        </div>

        <Alert
          v-if="errorMessage"
          class="mb-4"
          show-icon
          type="error"
          :message="errorMessage"
        >
          <template #action>
            <Button @click="loadLoginLogs">重新加载</Button>
          </template>
        </Alert>

        <Table
          class="login-log-table"
          :columns="columns"
          :data-source="records"
          :loading="loading"
          :pagination="pagination"
          :scroll="{ x: 1428 }"
          row-key="id"
          table-layout="fixed"
          @change="handleTableChange"
        >
          <template #emptyText>
            <Empty description="暂无登录日志" />
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'loginAt'">
              <Tooltip :title="formatTime(loginLogRecord(record).loginAt)">
                <span class="block truncate">
                  {{ formatTime(loginLogRecord(record).loginAt) }}
                </span>
              </Tooltip>
            </template>
            <template v-else-if="column.key === 'user'">
              <Tooltip
                :title="loginLogRecord(record).displayName || '未关联用户'"
              >
                <div class="block truncate font-medium">
                  {{ loginLogRecord(record).displayName || '未关联用户' }}
                </div>
              </Tooltip>
              <Tooltip :title="loginLogRecord(record).username || '-'">
                <div class="mt-1 block truncate text-xs text-slate-500">
                  {{ loginLogRecord(record).username || '-' }}
                </div>
              </Tooltip>
            </template>
            <template v-else-if="column.key === 'loginIdentifier'">
              <Tooltip :title="loginLogRecord(record).loginIdentifier || '-'">
                <span class="block truncate">
                  {{ loginLogRecord(record).loginIdentifier || '-' }}
                </span>
              </Tooltip>
            </template>
            <template v-else-if="column.key === 'authStage'">
              <Tooltip
                :title="authStageLabels[loginLogRecord(record).authStage]"
              >
                <span class="block truncate">
                  {{ authStageLabels[loginLogRecord(record).authStage] }}
                </span>
              </Tooltip>
            </template>
            <template v-else-if="column.key === 'loginResult'">
              <Tag
                :color="
                  loginLogRecord(record).loginResult === 1 ? 'success' : 'error'
                "
              >
                {{ loginLogRecord(record).loginResult === 1 ? '成功' : '失败' }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'failureReason'">
              <template v-if="loginLogRecord(record).failureReason">
                <Tooltip :title="loginLogRecord(record).failureReason">
                  <span class="block truncate">
                    {{ loginLogRecord(record).failureReason }}
                  </span>
                </Tooltip>
                <div
                  v-if="
                    loginLogRecord(record).failureCode !== null &&
                    loginLogRecord(record).failureCode !== undefined
                  "
                  class="mt-1 text-xs text-slate-500"
                >
                  错误码：{{ loginLogRecord(record).failureCode }}
                </div>
              </template>
              <span v-else>-</span>
            </template>
            <template v-else-if="column.key === 'userAgent'">
              <Tooltip :title="loginLogRecord(record).userAgent || '-'">
                <span class="block truncate">
                  {{ loginLogRecord(record).userAgent || '-' }}
                </span>
              </Tooltip>
            </template>
          </template>
        </Table>
      </Card>
    </div>
  </Page>
</template>

<style scoped></style>
