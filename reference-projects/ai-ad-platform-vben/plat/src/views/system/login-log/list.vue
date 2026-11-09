<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemLoginLogApi } from '#/api';

import { Page } from '@vben/common-ui';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getLoginLogList } from '#/api';

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
    showHeaderOverflow: 'tooltip',
    showOverflow: 'tooltip',
    proxyConfig: {
      ajax: {
        query: async ({ page }, values) => {
          const [startedAt, endedAt] = values.timeRange ?? [];
          const params = { ...values };
          delete params.timeRange;
          return getLoginLogList({
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
  } as VxeTableGridOptions<SystemLoginLogApi.LoginLog>,
});
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    description="查看账号登录结果、来源地址和时间，及时识别异常访问。"
    title="登录日志"
  >
    <Grid />
  </Page>
</template>
