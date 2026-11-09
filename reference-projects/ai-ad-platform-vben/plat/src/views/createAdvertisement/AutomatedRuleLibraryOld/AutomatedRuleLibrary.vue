<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type {
  AutomationRule,
  MediaBuyer,
  OptionItem,
  PlatformConfig,
  RecordQuery,
  RuleQuery,
  RuleRecord,
} from '#/api/advertisement/automated-rule';

import { onActivated, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Button, message, Popconfirm, Switch, Tabs, Tag } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  copyRule,
  deleteRule,
  getMediaBuyers,
  getOptions,
  getPlatformConfigs,
  listRecords,
  listRules,
  toggleAutoExecute,
  toggleRule,
} from '#/api/advertisement/automated-rule';

const TabPane = Tabs.TabPane;
const router = useRouter();
const activeTab = ref('rules');

function handleTabChange(key: string | number) {
  if (key === 'rules') {
    ruleGridApi.reload();
  } else {
    recordGridApi.reload();
  }
}

const projectOptions = ref<{ label: string; value: string }[]>([]);
const mediaBuyerOptions = ref<{ label: string; value: string }[]>([]);
const levelOptions = ref<OptionItem[]>([]);

onActivated(() => {
  if (activeTab.value === 'rules') {
    ruleGridApi.reload();
  } else {
    recordGridApi.reload();
  }
});

onMounted(async () => {
  try {
    const [configs, buyers, opts] = await Promise.all([
      getPlatformConfigs(),
      getMediaBuyers(),
      getOptions(),
    ]);
    projectOptions.value = (configs as PlatformConfig[]).map((c) => ({
      label: c.name,
      value: c.id,
    }));
    mediaBuyerOptions.value = (buyers as MediaBuyer[]).map((m) => ({
      label: m.real_name,
      value: m.real_name,
    }));
    levelOptions.value = opts.levels;
    ruleGridApi.formApi?.updateSchema?.([
      {
        fieldName: 'project_id',
        componentProps: {
          allowClear: true,
          showSearch: true,
          options: projectOptions.value,
          placeholder: '全部',
        },
      },
      {
        fieldName: 'media_buyer',
        componentProps: {
          allowClear: true,
          showSearch: true,
          options: mediaBuyerOptions.value,
          placeholder: '全部',
        },
      },
    ]);
  } catch {
    // ignore
  }
});

// ── 投放规则库 ────────────────────────────────────────────
const ruleFormOptions: VbenFormProps = {
  commonConfig: { colon: false },
  schema: [
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '请输入' },
      fieldName: 'rule_name',
      label: '规则名称',
      labelClass: 'w-[60px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        showSearch: true,
        options: [],
        placeholder: '全部',
      },
      fieldName: 'project_id',
      label: '项目',
      labelClass: 'w-[30px]',
    },
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '请输入' },
      fieldName: 'account_id',
      label: '广告账户',
      labelClass: 'w-[65px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        showSearch: true,
        options: [],
        placeholder: '全部',
      },
      fieldName: 'media_buyer',
      label: '投放师',
      labelClass: 'w-[50px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '全部', value: undefined },
          { label: '开启', value: 'true' },
          { label: '关闭', value: 'false' },
        ],
        placeholder: '全部',
      },
      fieldName: 'enabled',
      label: '状态',
      labelClass: 'w-[30px]',
    },
  ],
  showCollapseButton: false,
  submitOnEnter: false,
  wrapperClass:
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[repeat(5,190px)_max-content] py-1 pb-0 gap-x-3',
};

const ruleGridOptions: VxeGridProps<AutomationRule> = {
  columns: [
    { minWidth: 50, title: '序号', type: 'seq' },
    { field: 'id', minWidth: 120, showOverflow: true, title: '规则ID' },
    {
      field: 'rule_name',
      minWidth: 150,
      showOverflow: true,
      title: '规则名称',
    },
    {
      field: 'enabled',
      minWidth: 80,
      slots: { default: 'enabled' },
      title: '状态',
    },
    {
      field: 'auto_execute',
      minWidth: 100,
      slots: { default: 'auto_execute' },
      title: '自动执行',
    },
    {
      field: 'project_id',
      minWidth: 140,
      showOverflow: true,
      title: '项目名称',
      formatter: ({ row }) =>
        projectOptions.value.find((p) => p.value === row.project_id)?.label ||
        row.project_id ||
        '-',
    },
    {
      field: 'schedule_summary',
      minWidth: 100,
      formatter: ({ row }) => row?.schedule_summary || '-',
      title: '检查频次',
    },
    {
      field: 'schedule.effective_type',
      minWidth: 180,
      showOverflow: true,
      title: '生效时段',
      formatter: ({ row }) => {
        const s = row.schedule;
        if (!s) return '-';
        if (s.effective_type === 'long_term') return '长期';
        if (
          Array.isArray(s.effective_ranges) &&
          s.effective_ranges.length > 0
        ) {
          return s.effective_ranges
            .map((r: any) => {
              const start = r.start
                ? `${String(r.start).slice(0, 13).replace('T', ' ')}:00`
                : '';
              const end = r.end
                ? `${String(r.end).slice(0, 13).replace('T', ' ')}:00`
                : '';
              return start && end ? `${start} ~ ${end}` : start || end || '-';
            })
            .join('；');
        }
        return '-';
      },
    },
    {
      field: 'media_buyer',
      minWidth: 100,
      showOverflow: true,
      title: '投放师',
    },
    {
      field: 'updated_at',
      formatter: ({ cellValue }) =>
        cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-',
      minWidth: 160,
      title: '修改时间',
    },
    {
      field: 'operate',
      fixed: 'right',
      minWidth: 180,
      slots: { default: 'operate' },
      title: '操作',
    },
  ],
  pagerConfig: { pageSize: 20 },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues) => {
        const rawEnabled = formValues.enabled;
        const params: RuleQuery = {
          ...formValues,

          enabled:
            rawEnabled === 'true'
              ? true
              : // eslint-disable-next-line unicorn/no-nested-ternary
                rawEnabled === 'false'
                ? false
                : undefined,
          page: page.currentPage,
          page_size: page.pageSize,
        };
        return await listRules(params);
      },
    },
  },
  showOverflow: true,
  stripe: true,
  toolbarConfig: { refresh: true },
};

const [RuleGrid, ruleGridApi] = useVbenVxeGrid({
  formOptions: ruleFormOptions,
  gridOptions: ruleGridOptions,
});

// ── 行为记录 ─────────────────────────────────────────────
const recordFormOptions: VbenFormProps = {
  commonConfig: { colon: false },
  schema: [
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '请输入' },
      fieldName: 'rule_id',
      label: '规则ID',
      labelClass: 'w-[50px]',
    },
    {
      component: 'Input',
      componentProps: { allowClear: true, placeholder: '请输入' },
      fieldName: 'account_id',
      label: '广告账户',
      labelClass: 'w-[65px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '全部', value: undefined },
          { label: '待执行', value: 'pending' },
          { label: '已执行', value: 'executed' },
          { label: '已跳过', value: 'skipped' },
          { label: '已忽略', value: 'ignored' },
          { label: '执行失败', value: 'failed' },
        ],
        placeholder: '全部',
      },
      fieldName: 'status',
      label: '状态',
      labelClass: 'w-[30px]',
    },
  ],
  showCollapseButton: false,
  submitOnEnter: false,
  wrapperClass:
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[200px_200px_220px_max-content] py-1 pb-0 gap-x-3',
};

const recordStatusColorMap: Record<string, string> = {
  executed: 'success',
  failed: 'error',
  pending: 'processing',
  skipped: 'warning',
};

const recordStatusLabelMap: Record<string, string> = {
  executed: '已执行',
  failed: '执行失败',
  pending: '待执行',
  skipped: '已跳过',
  ignored: '已忽略',
};

const recordGridOptions: VxeGridProps<RuleRecord> = {
  columns: [
    { minWidth: 50, title: '序号', type: 'seq' },
    { field: 'rule_id', minWidth: 120, showOverflow: true, title: '规则ID' },
    {
      field: 'rule_name',
      minWidth: 150,
      showOverflow: true,
      title: '规则名称',
    },
    {
      field: 'object_name',
      minWidth: 130,
      showOverflow: true,
      title: '对象名称',
    },
    {
      field: 'level',
      minWidth: 80,
      title: '层级',
      formatter: ({ row }) =>
        levelOptions.value.find((l) => l.code === row.level)?.name ||
        row.level ||
        '-',
    },
    {
      field: 'status',
      minWidth: 90,
      slots: { default: 'record_status' },
      title: '状态',
    },
    { field: 'message', minWidth: 160, showOverflow: true, title: '执行结果' },
    {
      field: 'checked_at',
      formatter: ({ cellValue }) =>
        cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-',
      minWidth: 160,
      title: '检查时间',
    },
  ],
  pagerConfig: { pageSize: 20 },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues) => {
        const params: RecordQuery = {
          ...formValues,
          page: page.currentPage,
          page_size: page.pageSize,
        };
        return await listRecords(params);
      },
    },
  },
  showOverflow: true,
  stripe: true,
  toolbarConfig: { refresh: true },
};

const [RecordGrid, recordGridApi] = useVbenVxeGrid({
  formOptions: recordFormOptions,
  gridOptions: recordGridOptions,
});

// ── 操作 ──────────────────────────────────────────────────
function handleCreate() {
  router.push('/createAdvertisement/automated-rule-config');
}

function handleEdit(row: AutomationRule) {
  router.push(`/createAdvertisement/automated-rule-config?id=${row.id}`);
}

function handleDetail(row: AutomationRule) {
  router.push(
    `/createAdvertisement/automated-rule-config?id=${row.id}&readonly=1`,
  );
}

async function handleToggleEnabled(row: AutomationRule) {
  const next = !row.enabled;
  row.enabled = next;
  try {
    const res = await toggleRule(row.id);
    row.enabled = res.enabled;
  } catch {
    row.enabled = !next;
    message.error('切换失败');
  }
}

async function handleToggleAutoExecute(row: AutomationRule) {
  const next = !row.auto_execute;
  row.auto_execute = next;
  try {
    await toggleAutoExecute(row.id, next);
  } catch {
    row.auto_execute = !next;
    message.error('切换失败');
  }
}

async function handleDelete(row: AutomationRule) {
  await deleteRule(row.id);
  message.success('删除成功');
  await ruleGridApi.reload();
}

async function handleCopy(row: AutomationRule) {
  try {
    const res = await copyRule(row.id);
    message.success(`已复制为「${res.rule_name}」`);
    await ruleGridApi.reload();
  } catch {
    message.error('复制失败');
  }
}
</script>

<template>
  <div class="adpulse-section-page adpulse-tabs-page bg-background h-full pt-2">
    <Tabs
      v-model:active-key="activeTab"
      @change="handleTabChange"
      type="card"
      class="h-full"
    >
      <!-- 投放规则库 -->
      <TabPane key="rules" tab="投放规则库">
        <Page
          content-class="!p-0 [&_.relative.rounded]:!pt-0 [&_.relative.rounded]:!pb-[2px]"
          class="h-full"
        >
          <RuleGrid
            class="h-full [&_.vxe-grid]:overflow-hidden [&_.vxe-grid]:!pt-0"
          >
            <template #toolbar-tools>
              <Button type="primary" @click="handleCreate">+ 规则配置</Button>
            </template>

            <template #enabled="{ row }">
              <Switch
                :checked="row.enabled"
                checked-children="开"
                un-checked-children="关"
                @change="handleToggleEnabled(row)"
              />
            </template>

            <template #auto_execute="{ row }">
              <Switch
                :checked="row.auto_execute"
                checked-children="开"
                un-checked-children="关"
                @change="handleToggleAutoExecute(row)"
              />
            </template>

            <template #operate="{ row }">
              <Button type="link" class="pl-0 pr-1" @click="handleDetail(row)">
                查看详情
              </Button>
              <Button type="link" class="px-1" @click="handleEdit(row)">
                编辑
              </Button>
              <Popconfirm
                cancel-text="取消"
                ok-text="确定"
                placement="left"
                title="确定复制该规则吗？"
                @confirm="handleCopy(row)"
              >
                <Button type="link" class="px-1">复制</Button>
              </Popconfirm>
              <Popconfirm
                cancel-text="取消"
                ok-text="确定"
                placement="left"
                title="确定删除该规则吗？"
                @confirm="handleDelete(row)"
              >
                <Button type="link" class="p-0" danger>删除</Button>
              </Popconfirm>
            </template>
          </RuleGrid>
        </Page>
      </TabPane>

      <!-- 行为记录 -->
      <TabPane key="records" tab="行为记录">
        <Page
          content-class="!p-0 [&_.relative.rounded]:!pt-0 [&_.relative.rounded]:!pb-[2px]"
          class="h-full"
        >
          <RecordGrid
            class="h-full [&_.vxe-grid]:overflow-hidden [&_.vxe-grid]:!pt-0"
          >
            <template #record_status="{ row }">
              <Tag :color="recordStatusColorMap[row.status] || 'default'">
                {{ recordStatusLabelMap[row.status] || row.status || '-' }}
              </Tag>
            </template>
          </RecordGrid>
        </Page>
      </TabPane>
    </Tabs>
  </div>
</template>
