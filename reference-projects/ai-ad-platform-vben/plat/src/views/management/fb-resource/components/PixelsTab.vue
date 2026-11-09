<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { FbPixel } from '#/api';

import { Page } from '@vben/common-ui';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getPixels } from '#/api';
import Tag from 'ant-design-vue/es/tag';

const formOptions: VbenFormProps = {
  commonConfig: {
    colon: false,
  },
  schema: [
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '精确匹配',
      },
      fieldName: 'id',
      label: 'ID',
      labelClass: 'w-[30px]',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '模糊匹配',
      },
      fieldName: 'name',
      label: '名称',
      labelClass: 'w-[40px]',
    },
  ],
  showCollapseButton: false,
  submitOnEnter: false,
  wrapperClass:
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[repeat(2,170px)_max-content] py-1 pb-1 gap-x-3',
};

const gridOptions: VxeGridProps<FbPixel> = {
  columns: [
    { minWidth: 38, title: '序号', type: 'seq' },
    { field: '_id', minWidth: 180, title: 'ID' },
    { field: 'name', minWidth: 150, title: '名称' },
    {
      field: 'owner_business',
      minWidth: 200,
      slots: { default: 'owner_business' },
      title: '所属BM',
    },
    { field: 'data_use_setting', minWidth: 120, title: '数据使用设置' },
    {
      field: 'is_unavailable',
      minWidth: 80,
      slots: { default: 'is_available' },
      title: '是否可用',
    },
    {
      field: 'last_fired_time',
      formatter: ({ cellValue }) =>
        cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-',
      minWidth: 160,
      title: '最后触发时间',
    },
    {
      field: 'updated_at',
      formatter: ({ cellValue }) =>
        cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-',
      minWidth: 160,
      title: '更新时间',
    },
  ],
  pagerConfig: {
    pageSize: 20,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }, formValues) => {
        const params = {
          id: formValues.id || undefined,
          name: formValues.name || undefined,
          page: page.currentPage,
          page_size: page.pageSize,
        };
        return await getPixels(params);
      },
    },
  },
  showOverflow: true,
  stripe: true,
  toolbarConfig: {
    refresh: true,
  },
};

const [Grid] = useVbenVxeGrid({
  formOptions,
  gridOptions,
  routeState: { scope: 'pixel' },
});
</script>

<template>
  <Page
    content-class="!p-0 [&_.relative.rounded]:!pt-0 [&_.relative.rounded]:!pb-[2px]"
    class="h-full"
  >
    <Grid class="h-full">
      <template #owner_business="{ row }">
        <template v-if="row.owner_business">
          <div>{{ row.owner_business.name }}</div>
          <div class="text-xs text-gray-500">{{ row.owner_business.id }}</div>
        </template>
        <span v-else class="text-gray-400">-</span>
      </template>

      <template #is_available="{ row }">
        <Tag :color="row.is_unavailable ? 'error' : 'success'">
          {{ row.is_unavailable ? '否' : '是' }}
        </Tag>
      </template>
    </Grid>
  </Page>
</template>
