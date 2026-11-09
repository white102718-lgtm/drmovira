<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { OnActionClickParams } from '#/adapter/vxe-table';
import type { SystemUserApi } from '#/api';

import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import { Page, useVbenModal } from '@vben/common-ui';
import { Plus } from '@vben/icons';

import { Button, message, Modal } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getRoleDetail, getUserList, removeUserFromRole } from '#/api';
import SecondaryPageHeader from '#/components/SecondaryPageHeader.vue';

import { useGridFormSchema, useMemberColumns } from './data';
import MemberForm from './modules/member-form.vue';

const route = useRoute();
const roleName = ref('');
const roleId = computed(() => String(route.params.roleId ?? ''));
const description = computed(() =>
  roleName.value
    ? `查看“${roleName.value}”角色下的所有人员。`
    : '查看该角色下的所有人员。',
);

const [MemberFormModal, memberFormModalApi] = useVbenModal({
  connectedComponent: MemberForm,
  destroyOnClose: true,
});

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    schema: useGridFormSchema(),
    showCollapseButton: false,
    submitOnChange: true,
  },
  gridOptions: {
    columns: useMemberColumns(onActionClick),
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, values) =>
          getUserList({
            ...values,
            page: page.currentPage,
            pageSize: page.pageSize,
            roleId: roleId.value,
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
  } as VxeTableGridOptions<SystemUserApi.User>,
});

async function loadRoleName() {
  const detail = await getRoleDetail(roleId.value);
  roleName.value = detail.role.roleName;
}

function onActionClick({ code, row }: OnActionClickParams<SystemUserApi.User>) {
  if (code === 'removeRole') handleRemoveMember(row);
}

function handleAddMembers() {
  memberFormModalApi.setData({ roleId: roleId.value }).open();
}

function handleRemoveMember(row: SystemUserApi.User) {
  Modal.confirm({
    cancelText: '取消',
    content: `将“${row.displayName}”移出“${roleName.value || '当前'}”角色？此操作只移除该角色关系，不会删除用户账号。`,
    okButtonProps: { danger: true },
    okText: '移除角色',
    title: '移除角色成员',
    async onOk() {
      await removeUserFromRole(row.id, roleId.value);
      message.success('已移除角色成员，用户账号未受影响');
      gridApi.query();
    },
  });
}

onMounted(() => {
  void loadRoleName();
});
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    content-class="!flex !min-h-0 !flex-col !overflow-hidden"
  >
    <div class="flex min-h-0 min-w-0 flex-1 flex-col gap-4">
      <SecondaryPageHeader
        back-to="/system-management/roles"
        card
        :description="description"
        title="角色成员"
      >
        <template #extra>
          <Button type="primary" @click="handleAddMembers">
            <Plus class="size-5" aria-hidden="true" />
            添加用户
          </Button>
        </template>
      </SecondaryPageHeader>
      <MemberFormModal @success="gridApi.query()" />
      <div class="ux-fill-grid-host min-h-0 flex-1">
        <Grid />
      </div>
    </div>
  </Page>
</template>
