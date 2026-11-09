<script lang="ts" setup>
import type { Dayjs } from 'dayjs';

import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { AdConfigLevel, AdConfigObject } from '#/api';

import { computed, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';

import {
  Button,
  Checkbox,
  DatePicker,
  message,
  Modal,
  Select,
  Tag,
  Textarea,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getAdConfigRecords,
  getAdConfigResult,
  submitAdActivitiesPull,
  submitAdConfigPull,
} from '#/api';

const LEVEL_OPTIONS = [
  { label: '广告', value: 'ad' },
  { label: '广告组', value: 'adset' },
  { label: '系列', value: 'campaign' },
];
const LEVEL_LABEL: Record<string, string> = {
  ad: '广告',
  adset: '广告组',
  campaign: '系列',
};
const TYPE_OPTIONS = [
  { label: '广告配置', value: 'config' },
  { label: 'FB 操作记录', value: 'activities' },
];
const TYPE_LABEL: Record<string, string> = {
  config: '广告配置',
  activities: 'FB 操作记录',
};
const STATUS_META: Record<string, { color: string; text: string }> = {
  pending: { color: 'processing', text: '进行中' },
  done: { color: 'success', text: '成功' },
  failed: { color: 'error', text: '失败' },
};

// —— 顶部提交表单 ——
const submitting = ref(false);
const pull = reactive({
  level: 'ad' as AdConfigLevel,
  idsText: '',
  pull_type: 'config' as 'activities' | 'config',
  date: dayjs.tz().format('YYYY-MM-DD'),
  include_related: true,
});

async function handleSubmit() {
  const ids = [
    ...new Set(
      pull.idsText
        .split(/[\s,，]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ];
  if (ids.length === 0) {
    message.error('请至少输入一个 ID');
    return;
  }
  submitting.value = true;
  try {
    await (pull.pull_type === 'activities'
      ? submitAdActivitiesPull({
          level: pull.level,
          ids,
          date: pull.date,
          include_related: pull.include_related,
        })
      : submitAdConfigPull({
          level: pull.level,
          ids,
          include_related: pull.include_related,
        }));
    message.success(`已提交 ${ids.length} 个拉取任务，稍后刷新列表查看结果`);
    // 列表切到刚提交的类型再刷新,拉到的数据出现后即可见
    await gridApi.formApi.setValues({ pull_type: pull.pull_type });
    await gridApi.reload();
  } finally {
    submitting.value = false;
  }
}

// —— 已拉取对象列表 ——
const formOptions: VbenFormProps = {
  commonConfig: { colon: false },
  schema: [
    {
      component: 'Select',
      componentProps: {
        allowClear: false,
        options: TYPE_OPTIONS,
        class: 'w-full',
      },
      defaultValue: 'config',
      fieldName: 'pull_type',
      label: '类型',
      labelClass: 'w-[56px]',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        class: 'w-full',
        placeholder: '对象 ID',
      },
      fieldName: 'object_id',
      label: '对象 ID',
      labelClass: 'w-[56px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        placeholder: '层级',
        options: LEVEL_OPTIONS,
        class: 'w-full',
      },
      fieldName: 'level',
      label: '层级',
      labelClass: 'w-[56px]',
    },
  ],
  showCollapseButton: false,
  submitOnEnter: true,
  wrapperClass:
    'ad-config-filter-form !flex !flex-wrap !items-center py-1 pb-0',
};

const gridOptions: VxeGridProps<AdConfigObject> = {
  toolbarConfig: { refresh: { code: 'query' } },
  autoResize: true,
  border: true,
  columns: [
    { title: '序号', type: 'seq', width: 60 },
    {
      field: 'created_at',
      title: '拉取时间',
      minWidth: 160,
      formatter: ({ cellValue }) =>
        cellValue ? dayjs.tz(cellValue).format('YYYY-MM-DD HH:mm:ss') : '',
    },
    {
      field: 'level',
      title: '层级',
      minWidth: 90,
      formatter: ({ cellValue }) => LEVEL_LABEL[cellValue] || cellValue,
    },
    { field: 'object_id', title: '对象 ID', minWidth: 160 },
    { field: 'campaign_id', title: '所属系列', minWidth: 160 },
    { field: 'ad_set_id', title: '所属组', minWidth: 160 },
    {
      field: 'account_name',
      title: '账户',
      minWidth: 180,
      formatter: ({ row }) =>
        row.account_name
          ? `${row.account_name}(${row.account_id})`
          : row.account_id,
    },
    { field: 'date', title: '日期', minWidth: 110 },
    { field: 'real_name', title: '提交人', minWidth: 100 },
    {
      field: 'status',
      title: '状态',
      minWidth: 90,
      slots: { default: 'status' },
    },
    {
      align: 'center',
      slots: { default: 'action' },
      title: '操作',
      minWidth: 100,
    },
  ],
  keepSource: true,
  pagerConfig: { enabled: true, pageSize: 20 },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues) => {
        try {
          const result = await getAdConfigRecords({
            page: page.currentPage,
            page_size: page.pageSize,
            pull_type: formValues.pull_type || 'config',
            object_id: formValues.object_id || undefined,
            level: formValues.level || undefined,
          });
          return {
            total: result?.total ?? 0,
            items: result?.items ?? [],
          };
        } catch {
          return { total: 0, items: [] };
        }
      },
    },
  },
  showOverflow: false,
};

const [Grid, gridApi] = useVbenVxeGrid({ formOptions, gridOptions });

// —— 结果详情:同一 request_id(一次提交)拉到的所有对象 ——
const detailOpen = ref(false);
const detailLoading = ref(false);
const detailRow = ref<AdConfigObject | null>(null);
const detailObjects = ref<AdConfigObject[]>([]);

async function openDetail(row: AdConfigObject) {
  detailRow.value = row;
  detailObjects.value = [];
  detailOpen.value = true;
  await refreshDetail();
}

async function refreshDetail() {
  const row = detailRow.value;
  if (!row) return;
  detailLoading.value = true;
  try {
    const result = await getAdConfigResult(row.request_id, row.pull_type);
    detailObjects.value = result?.objects ?? [];
  } finally {
    detailLoading.value = false;
  }
}

const detailText = computed(() =>
  detailObjects.value.length > 0
    ? JSON.stringify(detailObjects.value, null, 2)
    : '暂无数据',
);
</script>

<template>
  <Page
    class="adpulse-section-page ad-config-page bg-muted/40"
    auto-content-height
    content-class="!flex !min-h-0 !flex-col !gap-4 !overflow-hidden p-4"
    description="按对象和日期拉取广告配置，并查看每次同步的执行结果。"
    title="广告配置"
  >
    <section class="border-border bg-card rounded-lg border p-4">
      <div class="mb-4">
        <h2 class="text-foreground m-0 text-base font-semibold">提交拉取</h2>
        <p class="text-muted-foreground mb-0 mt-1 text-sm">
          按对象和日期提交广告配置或操作记录的同步任务。
        </p>
      </div>
      <div class="flex flex-wrap items-end gap-4">
        <label class="flex w-full flex-col gap-1.5 sm:w-[120px]">
          <span class="text-foreground text-sm font-medium">对象层级</span>
          <Select
            v-model:value="pull.level"
            class="w-full"
            :options="LEVEL_OPTIONS"
          />
        </label>
        <label class="flex min-w-0 flex-1 flex-col gap-1.5">
          <span class="text-foreground text-sm font-medium">对象 ID</span>
          <Textarea
            v-model:value="pull.idsText"
            allow-clear
            class="w-full"
            placeholder="对象 ID，多个用换行 / 空格 / 逗号分隔"
            :auto-size="{ minRows: 1, maxRows: 4 }"
          />
        </label>
        <label class="flex w-full flex-col gap-1.5 sm:w-40">
          <span class="text-foreground text-sm font-medium">拉取类型</span>
          <Select
            v-model:value="pull.pull_type"
            class="w-full"
            :options="TYPE_OPTIONS"
          />
        </label>
        <label
          v-if="pull.pull_type === 'activities'"
          class="flex w-full flex-col gap-1.5 sm:w-[150px]"
        >
          <span class="text-foreground text-sm font-medium">日期</span>
          <DatePicker
            v-model:value="pull.date"
            class="w-full"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            :allow-clear="false"
            :disabled-date="
              (current: Dayjs) => current && current > dayjs.tz().endOf('day')
            "
          />
        </label>
        <div class="ad-config-related-option">
          <Checkbox v-model:checked="pull.include_related">
            拉取该系列下其他配置
          </Checkbox>
        </div>
        <Button
          type="primary"
          class=""
          :loading="submitting"
          @click="handleSubmit"
        >
          提交拉取
        </Button>
      </div>
    </section>

    <Grid>
      <template #status="{ row }">
        <Tag :color="STATUS_META[row.status]?.color">
          {{ STATUS_META[row.status]?.text || row.status }}
        </Tag>
      </template>
      <template #action="{ row }">
        <Button type="link" @click="openDetail(row)">查看</Button>
      </template>
    </Grid>

    <Modal
      v-model:open="detailOpen"
      :footer="null"
      title="拉取结果"
      width="820px"
    >
      <div v-if="detailRow" class="mb-2 flex items-center gap-2">
        <span class="text-muted-foreground">
          {{ TYPE_LABEL[detailRow.pull_type] }} · 本次拉取共
          {{ detailObjects.length }} 个对象
        </span>
        <Button :loading="detailLoading" @click="refreshDetail()">
          刷新
        </Button>
      </div>
      <pre
        class="bg-card max-h-[60vh] overflow-auto rounded-md border p-3 text-xs"
        >{{ detailText }}</pre
      >
    </Modal>
  </Page>
</template>

<style scoped>
.ad-config-page :deep(.vxe-grid--form-wrapper .relative.rounded) {
  padding-block: 0 !important;
}

.ad-config-page :deep(.vxe-grid--form-wrapper .flex-row.items-center.pb-2) {
  padding-bottom: 0 !important;
}

.ad-config-related-option {
  display: flex;
  min-height: var(--adpulse-control-height);
  align-items: center;
  align-self: flex-end;
}

.ad-config-page :deep(.ad-config-filter-form) {
  gap: var(--adpulse-filter-row-gap) var(--adpulse-filter-column-gap) !important;
}

.ad-config-page :deep(.ad-config-filter-form > .flex-row.items-center) {
  flex: 0 0 auto;
  width: auto;
  min-width: 0;
}

.ad-config-page
  :deep(.ad-config-filter-form > .flex-row.items-center > .flex-auto) {
  flex: 0 0 var(--adpulse-filter-field-width);
  width: var(--adpulse-filter-field-width);
  min-width: var(--adpulse-filter-field-width);
  max-width: var(--adpulse-filter-field-width);
}

.ad-config-page :deep(.ad-config-filter-form > .col-span-full) {
  display: flex;
  flex: 0 0 auto;
  width: auto !important;
  padding-bottom: 0 !important;
  gap: var(--adpulse-action-gap);
  align-items: center;
}

.ad-config-page :deep(.vxe-grid--toolbar-wrapper),
.ad-config-page :deep(.vxe-toolbar) {
  padding-block: 0;
  background: transparent;
}

.ad-config-page :deep(.vxe-grid--form-wrapper .bg-background-deep) {
  display: none;
}
</style>
