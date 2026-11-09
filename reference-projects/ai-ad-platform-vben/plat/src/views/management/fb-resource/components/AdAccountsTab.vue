<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { VxeGridProps } from '#/adapter/vxe-table';
import type { AdAccount } from '#/api';

import { ref } from 'vue';

import { Page } from '@vben/common-ui';

import { notification, Popover, Tag } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getAdAccounts } from '#/api';
import { FACEBOOK_AD_ACCOUNT_STATUS_LABELS } from '#/constants/facebook-ad-account-status';

import { parseAdAccountSearchIds } from './ad-account-search';

const sortState = ref<{ field?: string; order?: string }>({
  field: 'updated_at',
  order: 'desc',
});

function toggleUpdatedAtSort() {
  sortState.value = {
    field: 'updated_at',
    order: sortState.value.order === 'desc' ? 'asc' : 'desc',
  };
  void gridApi.reload();
}

// 账户状态映射
const accountStatusMap: Record<number, { color: string; text: string }> = {
  1: { color: 'success', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[1]! },
  2: { color: 'error', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[2]! },
  3: { color: 'warning', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[3]! },
  7: { color: 'warning', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[7]! },
  8: { color: 'warning', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[8]! },
  9: { color: 'warning', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[9]! },
  100: { color: 'error', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[100]! },
  101: { color: 'error', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[101]! },
  201: { color: 'success', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[201]! },
  202: { color: 'error', text: FACEBOOK_AD_ACCOUNT_STATUS_LABELS[202]! },
};

const formOptions: VbenFormProps = {
  commonConfig: {
    colon: false,
  },
  schema: [
    {
      component: 'Textarea',
      componentProps: {
        allowClear: true,
        autoSize: { maxRows: 3, minRows: 1 },
        placeholder: '多个 ID 可用空格或换行分隔',
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

const gridOptions: VxeGridProps<AdAccount> = {
  columns: [
    { minWidth: 38, title: '序号', type: 'seq' },
    { field: '_id', minWidth: 180, title: 'ID' },
    { field: 'name', minWidth: 150, title: '名称' },
    {
      field: 'account_status',
      minWidth: 90,
      slots: { default: 'account_status' },
      title: '状态',
    },
    { field: 'amount_spent', minWidth: 120, title: '账户总花费' },
    { field: 'spend_cap', minWidth: 100, title: '花费上限' },
    { field: 'currency', minWidth: 80, title: '币种' },
    { field: 'timezone_name', minWidth: 150, title: '时区' },
    { field: 'age', minWidth: 60, title: '账龄' },
    {
      field: 'is_prepay_account',
      minWidth: 80,
      title: '预付',
      formatter: ({ cellValue }) => (cellValue ? '是' : '否'),
    },
    { field: 'account_dsl', minWidth: 80, title: '单日账户限额' },
    { field: 'disable_reason', minWidth: 100, title: '禁用原因' },
    { field: 'owner', minWidth: 180, title: '所有者' },
    {
      field: 'pixels',
      minWidth: 100,
      slots: { default: 'pixels' },
      title: '像素',
    },
    {
      field: 'updated_at',
      formatter: ({ cellValue }) =>
        cellValue ? cellValue.slice(0, 19).replace('T', ' ') : '-',
      minWidth: 160,
      slots: { header: 'updated_at_header' },
      title: '更新时间',
    },
  ],
  pagerConfig: {
    pageSize: 20,
  },
  proxyConfig: {
    ajax: {
      query: async ({ page }: any, formValues) => {
        const ids = parseAdAccountSearchIds(formValues.id);
        const params = {
          id: ids,
          name: formValues.name || undefined,
          page: page.currentPage,
          page_size: page.pageSize,
          sort_by: sortState.value.field || undefined,
          sort_order: sortState.value.order || undefined,
        };
        const result = await getAdAccounts(params);
        if (result.missing_ids?.length) {
          notification.warning({
            description: result.missing_ids.join('、'),
            message: '以下 ID 未匹配成功',
            placement: 'bottomRight',
          });
        }
        return result;
      },
    },
  },
  showOverflow: true,
  stripe: true,
  toolbarConfig: {
    refresh: true,
  },
};

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions,
  routeState: { scope: 'ad_account' },
  gridOptions,
});
</script>

<template>
  <Page
    content-class="!p-0 [&_.relative.rounded]:!pt-0 [&_.relative.rounded]:!pb-[2px]"
    class="h-full"
  >
    <Grid class="h-full">
      <template #updated_at_header>
        <button
          class="inline-flex items-center justify-center gap-1 font-medium"
          type="button"
          @click.stop="toggleUpdatedAtSort"
        >
          <span>更新时间</span>
          <span>{{ sortState.order === 'desc' ? '↓' : '↑' }}</span>
        </button>
      </template>

      <template #account_status="{ row }">
        <Tag :color="accountStatusMap[row.account_status]?.color || 'default'">
          {{ accountStatusMap[row.account_status]?.text || row.account_status }}
        </Tag>
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
