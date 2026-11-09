<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemOperationLogApi } from '#/api';

import { Page } from '@vben/common-ui';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getOperationLogList } from '#/api';

import { useColumns, useGridFormSchema } from './data';

function formatTime(value: any, boundary: 'end' | 'start') {
  return value?.[boundary === 'start' ? 'startOf' : 'endOf']?.('day')?.format?.(
    'YYYY-MM-DDTHH:mm:ss',
  );
}

const [Grid] = useVbenVxeGrid({
  formOptions: {
    schema: useGridFormSchema(),
    showCollapseButton: true,
  },
  gridOptions: {
    columns: useColumns(),
    proxyConfig: {
      ajax: {
        query: async ({ page }, values) => {
          const [startedAt, endedAt] = values.timeRange ?? [];
          const params = { ...values };
          delete params.timeRange;
          return getOperationLogList({
            ...params,
            endedAt: formatTime(endedAt, 'end'),
            page: page.currentPage,
            pageSize: page.pageSize,
            startedAt: formatTime(startedAt, 'start'),
          });
        },
      },
    },
    rowConfig: { keyField: 'id' },
    toolbarConfig: {
      custom: true,
      export: false,
      refresh: { code: 'query' },
      zoom: true,
    },
  } as VxeTableGridOptions<SystemOperationLogApi.OperationLog>,
});
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    description="查看关键业务与系统操作记录，用于安全审计和问题追踪。"
    title="操作日志"
  >
    <Grid />
  </Page>
</template>
