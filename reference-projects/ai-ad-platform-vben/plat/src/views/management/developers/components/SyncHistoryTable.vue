<script lang="ts" setup>
import type { VxeGridProps } from '#/adapter/vxe-table';
import type { AdSyncHistoryParams } from '#/api/management/developer';

import { message, Tooltip } from 'ant-design-vue';
import dayjs, { Dayjs } from 'dayjs';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getAdSyncHistory } from '#/api/management/developer';

// 同步历史项接口定义
interface SyncHistoryItem {
  ad_platform: string;
  agent_line: string;
  app_name: string;
  create_time: string;
  day: string;
  description: string;
  dev_id: string;
  errors?: string;
  game_platform: string;
  hour: number;
  placer_id: string;
  proxy: string;
  run_status: string;
  update_time?: string;
}

const dateFormat = 'YYYY-MM-DD';
const availableHours = Array.from({ length: 24 }, (_, i) => i);

// 设置表格选项
const syncHistoryGridOptions: VxeGridProps<SyncHistoryItem> = {
  columns: [
    { align: 'left', width: 60, title: '序号', type: 'seq' },
    { field: 'dev_id', minWidth: 80, title: '开发者ID' },
    { field: 'ad_platform', minWidth: 70, title: '广告平台' },
    { field: 'placer_id', width: 120, title: '投放人' },
    { field: 'date', width: 140, title: '日期' },
    { field: 'proxy', width: 140, title: '代理' },
    { field: 'run_status', width: 120, title: '状态' },
    {
      field: 'errors',
      minWidth: 220,
      slots: { default: 'errors' },
      title: '错误详情',
    },
    {
      field: 'create_time',
      formatter: ({ cellValue }) => {
        return cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-';
      },
      width: 160,
      title: '创建时间',
    },
    {
      field: 'update_time',
      formatter: ({ cellValue }) => {
        return cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-';
      },
      width: 160,
      title: '更新时间',
    },
  ],
  height: '100%',
  keepSource: true,
  pagerConfig: {
    pageSize: 20,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues: Record<string, any>) => {
        try {
          const params: AdSyncHistoryParams = {
            day: formValues.day,
            page: page.currentPage,
            page_size: page.pageSize,
          };
          if (formValues.hour !== undefined && formValues.hour !== null) {
            params.hour = formValues.hour;
          }
          if (formValues.agent_lines) {
            params.agent_lines = formValues.agent_lines;
          }
          return await getAdSyncHistory(params);
        } catch {
          message.error('加载同步历史数据失败');
          return {
            page: 1,
            page_size: 10,
            pages: 0,
            total: 0,
            items: [],
          };
        }
      },
    },
  },
  showOverflow: true,
  toolbarConfig: {
    refresh: true,
  },
};

// 表单配置
const formOptions = {
  schema: [
    {
      component: 'DatePicker',
      componentProps: {
        allowClear: false,
        disabledDate: (current: Dayjs) => {
          return current && current > dayjs.tz().endOf('day');
        },
        format: dateFormat,
        placeholder: '日期',
        valueFormat: dateFormat,
      },
      defaultValue: dayjs.tz().format(dateFormat),
      fieldName: 'day',
      label: '日期',
      required: true,
      labelClass: 'w-[30px]',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: availableHours.map((hour) => ({
          label: hour.toString(),
          value: hour,
        })),
        placeholder: '小时',
      },
      fieldName: 'hour',
      label: '小时',
      labelClass: 'w-[30px]',
    },
  ],
  showAdvanced: false,
  showCollapseButton: false,
  wrapperClass:
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[300px_200px_max-content] py-2.5 pb-0 gap-x-4',
  wrapperCol: { span: 12 },
};

// 创建表格
const [Grid] = useVbenVxeGrid({
  formOptions,
  routeState: { scope: 'sync_history' },
  gridOptions: syncHistoryGridOptions,
  tableTitle: '数据同步历史记录',
});
</script>

<template>
  <Grid class="developer-management-grid h-full min-w-0">
    <template #errors="{ row }">
      <div v-if="row.errors" style="width: 100%">
        <Tooltip
          :title="row.errors"
          placement="left"
          :overlay-style="{
            maxWidth: '800px',
            maxHeight: '400px',
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
          }"
        >
          <div class="cursor-pointer overflow-hidden text-slate-600">
            {{ row.errors }}
          </div>
        </Tooltip>
      </div>
      <span v-else>-</span>
    </template>
  </Grid>
</template>
