<script lang="ts" setup>
import type { MediaAccount } from '#/store/media-resource';
import type { TablePaginationConfig } from 'ant-design-vue';

import { computed, reactive, ref, watch } from 'vue';
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
  Space,
  Table,
  Tag,
} from 'ant-design-vue';
import { storeToRefs } from 'pinia';

import { useMediaResourceStore } from '#/store/media-resource';
import {
  createPositiveIntegerRouteQueryField,
  createStringRouteQueryField,
  useRouteListQuery,
} from '#/composables/use-route-list-query';

import MediaResourcePage from './components/MediaResourcePage.vue';

const resourceStore = useMediaResourceStore();
const { exceptions } = storeToRefs(resourceStore);

const keyword = ref('');
const platformFilter = ref('all');
const page = ref(1);
const pageSize = ref(10);
const resolveOpen = ref(false);
const submitting = ref(false);
const activeAccount = ref<MediaAccount>();
const resolveForm = reactive<{
  note: string;
  outcome: 'available' | 'disabled';
}>({ note: '', outcome: 'available' });

const columns = [
  { key: 'account', title: '异常账户', width: 250 },
  { key: 'platform', title: '平台状态', width: 150 },
  { key: 'reason', title: '异常原因', width: 300 },
  { key: 'binding', title: '当前绑定', width: 240 },
  { key: 'time', title: '发现时间', width: 180 },
  { key: 'actions', title: '操作', width: 130 },
];

const platformMeta: Record<string, { color: string; label: string }> = {
  facebook: { color: 'blue', label: 'Facebook' },
  google: { color: 'red', label: 'Google' },
  kwai: { color: 'orange', label: 'Kwai' },
  tiktok: { color: 'default', label: 'TikTok' },
};

const platformOptions = [
  { label: '全部平台', value: 'all' },
  ...Object.entries(platformMeta).map(([value, item]) => ({
    label: item.label,
    value,
  })),
];

const route = useRoute();
const router = useRouter();
const { isApplyingRoute } = useRouteListQuery({
  fields: {
    page: createPositiveIntegerRouteQueryField(page, { defaultValue: 1 }),
    pageSize: createPositiveIntegerRouteQueryField(pageSize, {
      allowedValues: [10, 20, 50, 100],
      defaultValue: 10,
    }),
    platform: createStringRouteQueryField(platformFilter, {
      allowedValues: platformOptions.map((item) => item.value),
      defaultValue: 'all',
    }),
    q: createStringRouteQueryField(keyword, {
      debounceMs: 250,
      defaultValue: '',
    }),
  },
  route,
  router,
});

const outcomeOptions = [
  { label: '异常解除，恢复为可用', value: 'available' },
  { label: '确认不可用，停用账户', value: 'disabled' },
];

function formatTime(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false });
}

const filteredExceptions = computed(() => {
  const query = keyword.value.trim().toLowerCase();
  return exceptions.value.filter((account) => {
    const searchable = [
      account.name,
      account.accountId,
      account.projectName,
      account.teamName,
      account.assigneeName,
      account.exceptionReason,
      account.businessManagerName,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return (
      (!query || searchable.includes(query)) &&
      (platformFilter.value === 'all' ||
        account.platform === platformFilter.value)
    );
  });
});

const pagination = computed<TablePaginationConfig>(() => ({
  current: page.value,
  pageSize: pageSize.value,
  showSizeChanger: true,
  total: filteredExceptions.value.length,
}));

function handleTableChange(next: TablePaginationConfig) {
  const nextPageSize = next.pageSize ?? pageSize.value;
  page.value = nextPageSize === pageSize.value ? (next.current ?? 1) : 1;
  pageSize.value = nextPageSize;
}

watch([keyword, platformFilter], () => {
  if (!isApplyingRoute.value) page.value = 1;
});

watch([() => filteredExceptions.value.length, pageSize], ([total]) => {
  const lastPage = Math.max(1, Math.ceil(total / pageSize.value));
  if (page.value > lastPage) page.value = lastPage;
});

const summary = computed(() => [
  {
    icon: 'lucide:triangle-alert',
    label: '异常账户',
    tone: 'bg-red-50 text-red-600',
    value: exceptions.value.length,
  },
  {
    icon: 'lucide:link-2-off',
    label: '影响项目资源',
    tone: 'bg-amber-50 text-amber-600',
    value: exceptions.value.filter((account) => account.projectId).length,
  },
  {
    icon: 'lucide:shield-alert',
    label: '平台受限',
    tone: 'bg-violet-50 text-violet-600',
    value: exceptions.value.filter((account) =>
      ['disabled', 'restricted'].includes(account.platformStatus),
    ).length,
  },
]);

function openResolve(account: { id?: unknown }) {
  const accountId = typeof account.id === 'string' ? account.id : '';
  activeAccount.value = exceptions.value.find((item) => item.id === accountId);
  if (!activeAccount.value) {
    message.error('未找到对应的异常账户');
    return;
  }
  resolveForm.note = '';
  resolveForm.outcome = 'available';
  resolveOpen.value = true;
}

async function resolve() {
  if (!activeAccount.value || !resolveForm.note.trim()) {
    message.warning('请填写处理说明');
    return;
  }
  submitting.value = true;
  try {
    await Promise.resolve(
      resourceStore.resolveException(
        activeAccount.value.id,
        resolveForm.outcome,
        resolveForm.note.trim(),
      ),
    );
    message.success(
      resolveForm.outcome === 'available'
        ? '异常已处理，账户已恢复可用'
        : '异常已处理，账户已停用',
    );
    resolveOpen.value = false;
  } catch (error) {
    message.error(error instanceof Error ? error.message : '处理异常失败');
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <MediaResourcePage>
    <div class="flex w-full min-w-0 flex-col gap-4">
      <Card :bordered="false" class="shadow-sm">
        <div class="flex items-start gap-3">
          <span
            class="grid size-11 shrink-0 place-items-center rounded-xl bg-red-50 text-red-600"
          >
            <IconifyIcon icon="lucide:triangle-alert" class="text-xl" />
          </span>
          <div>
            <h1 class="m-0 text-xl font-semibold text-slate-900">异常资源</h1>
            <p class="mb-0 mt-1 text-sm text-slate-500">
              集中处理平台限制、风控和状态异常，恢复前需确认账户可正常使用。
            </p>
          </div>
        </div>
      </Card>

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
        message="异常账户不会进入可用资源池；若仍绑定项目，请先与投手确认在途广告和替换方案。"
        show-icon
        type="warning"
      />

      <Card :bordered="false" class="shadow-sm">
        <div class="mb-4 flex flex-col gap-3 md:flex-row">
          <Input
            v-model:value="keyword"
            allow-clear
            class="w-full md:max-w-sm"
            placeholder="搜索账户、项目、团队或异常原因"
          >
            <template #prefix><IconifyIcon icon="lucide:search" /></template>
          </Input>
          <Select
            v-model:value="platformFilter"
            class="w-full md:w-40"
            :options="platformOptions"
          />
        </div>

        <Table
          :columns="columns"
          :data-source="filteredExceptions"
          :pagination="pagination"
          row-key="id"
          :scroll="{ x: 1250 }"
          @change="handleTableChange"
        >
          <template #emptyText>
            <Empty description="当前没有待处理的异常资源" />
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'account'">
              <div class="font-medium text-slate-900">{{ record.name }}</div>
              <div class="mt-1 text-xs text-slate-500">
                {{ record.accountId }}
              </div>
              <div
                v-if="record.businessManagerName"
                class="mt-1 text-xs text-slate-500"
              >
                {{ record.businessManagerName }}
              </div>
            </template>
            <template v-else-if="column.key === 'platform'">
              <Space direction="vertical" size="small">
                <Tag :color="platformMeta[record.platform]?.color ?? 'default'">
                  {{ platformMeta[record.platform]?.label ?? record.platform }}
                </Tag>
                <Tag color="red">{{ record.platformStatus }}</Tag>
              </Space>
            </template>
            <template v-else-if="column.key === 'reason'">
              <div class="line-clamp-3 text-sm text-slate-700">
                {{ record.exceptionReason || '未填写异常原因' }}
              </div>
            </template>
            <template v-else-if="column.key === 'binding'">
              <template v-if="record.projectId">
                <div class="font-medium text-slate-800">
                  {{ record.projectName }}
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  {{ record.teamName }} · {{ record.assigneeName }}
                </div>
              </template>
              <span v-else class="text-sm text-slate-400">未绑定项目</span>
            </template>
            <template v-else-if="column.key === 'time'">
              {{ formatTime(record.exceptionAt || record.updatedAt) }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <Button type="link" class="!px-0" @click="openResolve(record)">
                处理异常
              </Button>
            </template>
          </template>
        </Table>
      </Card>
    </div>

    <Modal
      v-model:open="resolveOpen"
      :confirm-loading="submitting"
      ok-text="确认处理"
      title="处理异常资源"
      @ok="resolve"
    >
      <div class="mb-4 rounded-lg bg-slate-50 p-3 text-sm">
        <div class="font-medium text-slate-800">{{ activeAccount?.name }}</div>
        <div class="mt-1 text-slate-500">
          {{ activeAccount?.accountId }} · {{ activeAccount?.exceptionReason }}
        </div>
      </div>
      <Form layout="vertical">
        <FormItem label="处理结果" required>
          <Select
            v-model:value="resolveForm.outcome"
            :options="outcomeOptions"
          />
        </FormItem>
        <FormItem label="处理说明" required>
          <Input.TextArea
            v-model:value="resolveForm.note"
            :maxlength="300"
            :rows="4"
            placeholder="说明核查结果、平台反馈或停用依据"
            show-count
          />
        </FormItem>
      </Form>
      <Alert
        v-if="resolveForm.outcome === 'disabled'"
        message="账户将退出可用库存；若存在项目绑定，请同步完成替换或回收。"
        show-icon
        type="error"
      />
      <Alert
        v-else
        message="账户将恢复为可用状态，重新进入审批选户范围。"
        show-icon
        type="success"
      />
    </Modal>
  </MediaResourcePage>
</template>

<style scoped></style>
