<script lang="ts" setup>
import type {
  OnActionClickParams,
  VxeTableGridOptions,
} from '#/adapter/vxe-table';
import type { SystemDepartmentApi } from '#/api';

import { Page, useVbenDrawer } from '@vben/common-ui';
import { Plus } from '@vben/icons';

import { Button, message, Modal } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { deleteDepartment, getSystemDepartmentTree } from '#/api';

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
    proxyConfig: { ajax: { query: getSystemDepartmentTree } },
    rowConfig: { keyField: 'id' },
    toolbarConfig: {
      custom: true,
      export: false,
      refresh: { code: 'query' },
      zoom: true,
    },
    treeConfig: {
      parentField: 'parentId',
      rowField: 'id',
      transform: false,
    },
  } as VxeTableGridOptions<SystemDepartmentApi.Department>,
});

function onActionClick({
  code,
  row,
}: OnActionClickParams<SystemDepartmentApi.Department>) {
  if (row.sourceType === 'FEISHU' && (code === 'edit' || code === 'delete')) {
    message.info('飞书部门由组织同步维护，请在飞书中调整后重新同步');
    return;
  }
  if (code === 'edit') formDrawerApi.setData(row).open();
  if (code === 'append') formDrawerApi.setData({ parentId: row.id }).open();
  if (code === 'delete') onDelete(row);
}

function onDelete(row: SystemDepartmentApi.Department) {
  Modal.confirm({
    cancelText: '取消',
    content: `确认删除部门“${row.deptName}”吗？`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除部门',
    async onOk() {
      await deleteDepartment(row.id);
      message.success('部门已删除');
      gridApi.query();
    },
  });
}
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    description="维护组织层级和部门关系。飞书同步部门请在飞书中调整后重新同步。"
    header-class="gap-4 max-sm:flex-col max-sm:items-stretch"
    title="部门管理"
  >
    <template #extra>
      <Button
        type="primary"
        @click="formDrawerApi.setData({ parentId: '0' }).open()"
      >
        <Plus class="size-5" aria-hidden="true" />
        新增部门
      </Button>
    </template>
    <FormDrawer @success="gridApi.query()" />
    <Grid />
  </Page>
</template>
