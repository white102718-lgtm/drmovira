<script setup lang="ts">
import { computed, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import AntDataTable from '#/components/ui/AntDataTable.vue';
import { Card, Input, Tag } from 'ant-design-vue';

import { Select } from 'ant-design-vue';

const keyword = ref('');
const moduleFilter = ref('all');
const records = [
  {
    id: 'OP-001',
    actor: '周敏',
    action: '审批通过并转发放',
    module: '审批中心',
    object: 'REQ-20260818-001',
    ip: '10.12.6.18',
    result: 'success',
    time: '2026-08-20 10:06:12',
  },
  {
    id: 'OP-002',
    actor: '媒介管理员',
    action: '编辑渠道账户',
    module: '媒介资源',
    object: 'channel-mpower-media',
    ip: '10.12.4.9',
    result: 'success',
    time: '2026-08-20 09:51:44',
  },
  {
    id: 'OP-003',
    actor: '赵宁',
    action: '提交办公资产申请',
    module: '资源申请',
    object: 'REQ-OFFICE-004',
    ip: '10.12.8.21',
    result: 'success',
    time: '2026-08-20 09:45:02',
  },
  {
    id: 'OP-004',
    actor: '系统管理员',
    action: '删除渠道账户',
    module: '媒介资源',
    object: 'channel-old-02',
    ip: '10.12.1.3',
    result: 'failed',
    time: '2026-08-19 17:20:28',
  },
];
const columns = [
  { dataIndex: 'time', key: 'time', title: '操作时间', width: 190 },
  { dataIndex: 'actor', key: 'actor', title: '操作人', width: 150 },
  { key: 'action', title: '操作内容', width: 260 },
  { dataIndex: 'module', key: 'module', title: '业务模块', width: 150 },
  { dataIndex: 'object', key: 'object', title: '操作对象', width: 220 },
  { dataIndex: 'ip', key: 'ip', title: 'IP 地址', width: 150 },
  { key: 'result', title: '结果', width: 110 },
];
const modules = [...new Set(records.map((record) => record.module))];
const filteredRecords = computed(() => {
  const query = keyword.value.trim().toLowerCase();
  return records.filter(
    (record) =>
      (!query ||
        Object.values(record).join(' ').toLowerCase().includes(query)) &&
      (moduleFilter.value === 'all' || record.module === moduleFilter.value),
  );
});
</script>

<template>
  <Page class="system-management-page" content-class="pb-6">
    <div class="mx-auto flex max-w-[1600px] flex-col gap-4">
      <header class="flex items-start gap-3">
        <span
          class="bg-muted text-foreground grid size-11 place-items-center rounded-xl"
        >
          <IconifyIcon icon="lucide:scroll-text" class="text-xl" />
        </span>
        <div>
          <h1 class="m-0 text-xl font-semibold">操作日志</h1>
          <p class="mb-0 mt-1 text-sm text-slate-500">
            审计用户在项目、任务、审批、资源和系统管理中的关键操作。
          </p>
        </div>
      </header>
      <Card>
        <div class="ux-filter-form mb-4">
          <Input
            v-model:value="keyword"
            allow-clear
            class="ux-filter-search"
            placeholder="搜索操作人、内容、对象或 IP"
          >
            <template #prefix>
              <IconifyIcon icon="lucide:search" />
            </template>
          </Input>
          <Select
            v-model:value="moduleFilter"
            class="ux-filter-field"
            :options="[
              { label: '全部模块', value: 'all' },
              ...modules.map((value) => ({ label: value, value })),
            ]"
          />
        </div>
        <AntDataTable
          :columns="columns"
          :data="filteredRecords"
          empty-text="暂无操作日志"
          :page-size="15"
          row-key="id"
        >
          <template #cell-action="{ record }">
            <div class="font-medium">{{ record.action }}</div>
            <div class="text-muted-foreground mt-1 text-xs">
              {{ record.id }}
            </div>
          </template>
          <template #cell-result="{ record }">
            <Tag :color="record.result === 'success' ? 'green' : 'red'">
              {{ record.result === 'success' ? '成功' : '失败' }}
            </Tag>
          </template>
        </AntDataTable>
      </Card>
    </div>
  </Page>
</template>
