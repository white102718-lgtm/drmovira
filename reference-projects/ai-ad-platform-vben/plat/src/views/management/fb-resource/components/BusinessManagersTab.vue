<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { Business } from '#/api';

import { Page } from '@vben/common-ui';

import { Popover, Tag } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getBusinesses } from '#/api';

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
      label: 'BM ID',
      labelClass: 'w-[50px]',
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
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '精确匹配',
      },
      fieldName: 'personal_id',
      label: '个号ID',
      labelClass: 'w-[50px]',
    },
  ],
  showCollapseButton: false,
  submitOnEnter: false,
  wrapperClass:
    'grid-cols-1 sm:grid-cols-2 xl:grid-cols-[repeat(3,170px)_max-content] py-1 pb-1 gap-x-3',
};

const gridOptions: VxeGridProps<Business> = {
  columns: [
    { minWidth: 38, title: '序号', type: 'seq' },
    { field: '_id', minWidth: 220, title: '唯一标识' },
    { field: 'business_id', minWidth: 180, title: 'BM ID' },
    { field: 'business_name', minWidth: 200, title: 'BM名称' },
    { field: 'facebook_id', minWidth: 180, title: '个号ID' },
    {
      field: 'accounts',
      minWidth: 120,
      slots: { default: 'accounts' },
      title: '广告账户',
    },
    {
      field: 'pages',
      minWidth: 120,
      slots: { default: 'pages' },
      title: '主页',
    },
    {
      field: 'pixels',
      minWidth: 120,
      slots: { default: 'pixels' },
      title: '像素',
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
          personal_id: formValues.personal_id || undefined,
        };
        return await getBusinesses(params);
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
  routeState: { scope: 'business_manager' },
});
</script>

<template>
  <Page
    content-class="!p-0 [&_.relative.rounded]:!pt-0 [&_.relative.rounded]:!pb-[2px]"
    class="h-full"
  >
    <Grid class="h-full">
      <template #accounts="{ row }">
        <Popover v-if="row.accounts?.length" placement="bottom" trigger="click">
          <template #content>
            <div class="max-h-[300px] max-w-[400px] overflow-y-auto">
              <div
                v-for="item in row.accounts"
                :key="item.id"
                class="mb-1 flex items-center gap-2 border-b border-gray-100 pb-1 last:border-0 dark:border-gray-700"
              >
                <span class="text-xs text-gray-500">{{ item.id }}</span>
                <span>{{ item.name }}</span>
              </div>
            </div>
          </template>
          <Tag color="blue" class="cursor-pointer">
            {{ row.accounts.length }} 个
          </Tag>
        </Popover>
        <span v-else class="text-gray-400">-</span>
      </template>

      <template #pages="{ row }">
        <Popover v-if="row.pages?.length" placement="bottom" trigger="click">
          <template #content>
            <div class="max-h-[300px] max-w-[400px] overflow-y-auto">
              <div
                v-for="item in row.pages"
                :key="item.id"
                class="mb-1 flex items-center gap-2 border-b border-gray-100 pb-1 last:border-0 dark:border-gray-700"
              >
                <span class="text-xs text-gray-500">{{ item.id }}</span>
                <span>{{ item.name }}</span>
              </div>
            </div>
          </template>
          <Tag color="orange" class="cursor-pointer">
            {{ row.pages.length }} 个
          </Tag>
        </Popover>
        <span v-else class="text-gray-400">-</span>
      </template>

      <template #pixels="{ row }">
        <Popover v-if="row.pixels?.length" placement="bottom" trigger="click">
          <template #content>
            <div class="max-h-[300px] max-w-[400px] overflow-y-auto">
              <div
                v-for="item in row.pixels"
                :key="item.id"
                class="mb-1 flex items-center gap-2 border-b border-gray-100 pb-1 last:border-0 dark:border-gray-700"
              >
                <span class="text-xs text-gray-500">{{ item.id }}</span>
                <span>{{ item.name }}</span>
              </div>
            </div>
          </template>
          <Tag color="purple" class="cursor-pointer">
            {{ row.pixels.length }} 个
          </Tag>
        </Popover>
        <span v-else class="text-gray-400">-</span>
      </template>
    </Grid>
  </Page>
</template>
