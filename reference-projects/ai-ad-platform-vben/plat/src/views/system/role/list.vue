<script lang="ts" setup>
import type {
  OnActionClickParams,
  VxeTableGridOptions,
} from '#/adapter/vxe-table';
import type { SystemRoleApi } from '#/api';

import { useRouter } from 'vue-router';

import { Page, useVbenDrawer } from '@vben/common-ui';
import { Plus } from '@vben/icons';

import { Button, message, Modal } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { deleteRole, getRoleList } from '#/api';

import { useColumns, useGridFormSchema } from './data';
import Form from './modules/form.vue';

const router = useRouter();

const [FormDrawer, formDrawerApi] = useVbenDrawer({
  connectedComponent: Form,
  destroyOnClose: true,
});

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    schema: useGridFormSchema(),
    showCollapseButton: false,
    submitOnChange: true,
  },
  gridOptions: {
    columns: useColumns(onActionClick),
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, values) =>
          getRoleList({
            ...values,
            page: page.currentPage,
            pageSize: page.pageSize,
          }),
      },
    },
    rowConfig: { keyField: 'id' },
    toolbarConfig: {
      custom: true,
      export: false,
      refresh: { code: 'query' },
      zoom: true,
    },
  } as VxeTableGridOptions<SystemRoleApi.Role>,
});

function onActionClick({ code, row }: OnActionClickParams<SystemRoleApi.Role>) {
  if (code === 'members') onViewMembers(row);
  if (code === 'edit') formDrawerApi.setData(row).open();
  if (code === 'delete') onDelete(row);
}

function onViewMembers(row: SystemRoleApi.Role) {
  void router.push(`/system-management/roles/${row.id}/members`);
}

function onDelete(row: SystemRoleApi.Role) {
  Modal.confirm({
    cancelText: '取消',
    content: `确认删除角色“${row.roleName}”吗？`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除角色',
    async onOk() {
      await deleteRole(row.id);
      message.success('角色已删除');
      gridApi.query();
    },
  });
}
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    description="配置角色信息与菜单权限，统一管理系统访问边界。"
    header-class="gap-4 max-sm:flex-col max-sm:items-stretch"
    title="角色权限"
  >
    <template #extra>
      <Button type="primary" @click="formDrawerApi.setData(null).open()">
        <Plus class="size-5" aria-hidden="true" />
        新增角色
      </Button>
    </template>
    <FormDrawer @success="gridApi.query()" />
    <Grid />
  </Page>
</template>
