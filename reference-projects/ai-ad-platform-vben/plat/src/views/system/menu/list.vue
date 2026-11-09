<script lang="ts" setup>
import type {
  OnActionClickParams,
  VxeTableGridOptions,
} from '#/adapter/vxe-table';
import type { SystemMenuApi } from '#/api';

import { Page, useVbenDrawer } from '@vben/common-ui';
import { Plus } from '@vben/icons';

import { Button, message, Modal } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { deleteMenu, getMenuList } from '#/api';

import { useColumns } from './data';
import Form from './modules/form.vue';

const [FormDrawer, formDrawerApi] = useVbenDrawer({
  connectedComponent: Form,
  destroyOnClose: true,
});

const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: {
    columns: useColumns(onActionClick),
    keepSource: true,
    pagerConfig: { enabled: false },
    proxyConfig: { ajax: { query: getMenuList } },
    rowConfig: { keyField: 'id' },
    toolbarConfig: {
      custom: true,
      export: false,
      refresh: { code: 'query' },
      zoom: true,
    },
    treeConfig: {
      parentField: 'parentId',
      reserve: true,
      rowField: 'id',
      transform: false,
    },
  } as VxeTableGridOptions<SystemMenuApi.Menu>,
});

function onActionClick({ code, row }: OnActionClickParams<SystemMenuApi.Menu>) {
  if (code === 'edit') formDrawerApi.setData(row).open();
  if (code === 'append') formDrawerApi.setData({ parentId: row.id }).open();
  if (code === 'delete') onDelete(row);
}

function onDelete(row: SystemMenuApi.Menu) {
  Modal.confirm({
    cancelText: '取消',
    content: `确认删除“${row.menuName}”吗？`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除菜单',
    async onOk() {
      await deleteMenu(row.id);
      message.success('菜单已删除');
      gridApi.query();
    },
  });
}
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    description="维护导航结构、路由组件和权限标识，变更后将影响用户菜单。"
    header-class="gap-4 max-sm:flex-col max-sm:items-stretch"
    title="菜单管理"
  >
    <template #extra>
      <Button
        type="primary"
        @click="formDrawerApi.setData({ parentId: '0' }).open()"
      >
        <Plus class="size-5" aria-hidden="true" />
        新增菜单
      </Button>
    </template>
    <FormDrawer @success="gridApi.query()" />
    <Grid />
  </Page>
</template>
