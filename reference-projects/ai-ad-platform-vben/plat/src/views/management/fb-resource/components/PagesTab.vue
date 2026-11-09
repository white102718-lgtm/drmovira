<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { FbPage } from '#/api';

import { Page } from '@vben/common-ui';

import { message, Popover, Tag } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getPages } from '#/api';

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

const gridOptions: VxeGridProps<FbPage> = {
  columns: [
    { minWidth: 38, title: '序号', type: 'seq' },
    { field: '_id', minWidth: 180, title: 'ID' },
    { field: 'name', minWidth: 180, slots: { default: 'name' }, title: '名称' },
    { field: 'username', minWidth: 120, title: '用户名' },
    { field: 'category', minWidth: 120, title: '分类' },
    { field: 'fan_count', minWidth: 100, title: '粉丝数' },
    { field: 'followers_count', minWidth: 100, title: '关注数' },
    { field: 'new_like_count', minWidth: 100, title: '新点赞数' },
    { field: 'talking_about_count', minWidth: 100, title: '讨论数' },
    {
      field: 'can_post',
      minWidth: 80,
      slots: { default: 'can_post' },
      title: '可发帖',
    },
    {
      field: 'is_published',
      minWidth: 80,
      slots: { default: 'is_published' },
      title: '已发布',
    },
    {
      field: 'is_unclaimed',
      minWidth: 80,
      slots: { default: 'is_unclaimed' },
      title: '未认领',
    },
    { field: 'verification_status', minWidth: 100, title: '认证状态' },
    {
      field: 'link',
      minWidth: 150,
      slots: { default: 'link' },
      title: '链接',
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
        return await getPages(params);
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
  routeState: { scope: 'facebook_page' },
});

const copyLink = async (link: string) => {
  try {
    await navigator.clipboard.writeText(link);
    message.success('已复制到剪贴板');
  } catch {
    message.error('复制失败');
  }
};
</script>

<template>
  <Page
    content-class="!p-0 [&_.relative.rounded]:!pt-0 [&_.relative.rounded]:!pb-[2px]"
    class="h-full"
  >
    <Grid class="h-full">
      <template #name="{ row }">
        <div class="flex items-center gap-2">
          <img
            v-if="row.picture?.url"
            alt=""
            :src="row.picture.url"
            class="size-6 min-w-6 shrink-0 rounded-full object-cover"
          />
          <span>{{ row.name }}</span>
        </div>
      </template>

      <template #can_post="{ row }">
        <Tag :color="row.can_post ? 'success' : 'default'">
          {{ row.can_post ? '是' : '否' }}
        </Tag>
      </template>

      <template #is_published="{ row }">
        <Tag :color="row.is_published ? 'success' : 'default'">
          {{ row.is_published ? '是' : '否' }}
        </Tag>
      </template>

      <template #is_unclaimed="{ row }">
        <Tag :color="row.is_unclaimed ? 'warning' : 'success'">
          {{ row.is_unclaimed ? '是' : '否' }}
        </Tag>
      </template>

      <template #link="{ row }">
        <template v-if="row.link">
          <Popover trigger="click" placement="top">
            <template #content>
              <div class="flex items-center gap-2">
                <span class="max-w-[300px] break-all text-sm">{{
                  row.link
                }}</span>
                <a
                  class="shrink-0 text-blue-500 hover:underline"
                  @click="copyLink(row.link)"
                >
                  复制
                </a>
              </div>
            </template>
            <a class="text-blue-500 hover:underline">查看</a>
          </Popover>
          <a
            :href="row.link"
            target="_blank"
            class="mr-2 text-blue-500 hover:underline"
          >
            打开
          </a>
        </template>
        <span v-else class="text-gray-400">-</span>
      </template>
    </Grid>
  </Page>
</template>
