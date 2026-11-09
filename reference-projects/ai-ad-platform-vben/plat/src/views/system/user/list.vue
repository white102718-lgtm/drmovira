<script lang="ts" setup>
import type {
  OnActionClickParams,
  VxeTableGridOptions,
} from '#/adapter/vxe-table';
import type { SystemDepartmentApi, SystemUserApi } from '#/api';

import { h, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page, useVbenModal } from '@vben/common-ui';
import { IconifyIcon, Plus } from '@vben/icons';

import {
  Button,
  Dropdown,
  Input,
  Menu,
  MenuItem,
  message,
  Modal,
} from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deleteUser,
  getUserList,
  resetUserMfa,
  resetUserPassword,
} from '#/api';

import { useColumns, useGridFormSchema } from './data';
import DepartmentManager from './modules/department-manager.vue';
import Form from './modules/form.vue';
import IpRuleManager from './modules/ip-rule-manager.vue';

const router = useRouter();
const selectedDepartmentId = ref<string>();
const departmentNames = ref(new Map<string, string>());

// 复用左侧完整部门树，所属部门按主部门 ID 匹配，不受树搜索和筛选影响。
function onDepartmentsLoaded(departments: SystemDepartmentApi.Department[]) {
  const names = new Map<string, string>();
  function collect(nodes: SystemDepartmentApi.Department[]) {
    for (const node of nodes) {
      names.set(node.id, node.deptName);
      collect(node.children ?? []);
    }
  }
  collect(departments);
  departmentNames.value = names;
}

function getDepartmentName(id: null | string | undefined) {
  return id ? (departmentNames.value.get(id) ?? '—') : '—';
}

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: Form,
  destroyOnClose: true,
});

const [IpRuleModal, ipRuleModalApi] = useVbenModal({
  connectedComponent: IpRuleManager,
  destroyOnClose: true,
});

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    schema: useGridFormSchema(),
    showCollapseButton: false,
    submitOnChange: true,
  },
  gridOptions: {
    columns: useColumns(onActionClick, getDepartmentName),
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) =>
          getUserList({
            ...formValues,
            departmentId: selectedDepartmentId.value,
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
  } as VxeTableGridOptions<SystemUserApi.User>,
});

function onActionClick({ code, row }: OnActionClickParams<SystemUserApi.User>) {
  if (code === 'edit') onEdit(row);
  if (code === 'delete') onDelete(row);
  if (code === 'resetMfa') onResetMfa(row);
  if (code === 'resetPassword') onResetPassword(row);
}

function onEdit(row: SystemUserApi.User) {
  formModalApi.setData(row).open();
}

function onCreate() {
  formModalApi.setData(null).open();
}

function onDelete(row: SystemUserApi.User) {
  Modal.confirm({
    cancelText: '取消',
    content: `删除后用户将无法登录；其独占资产会恢复可分配，共享资产会移除该用户的使用关系。确认删除“${row.displayName}”吗？`,
    okButtonProps: { danger: true },
    okText: '删除',
    title: '删除用户',
    async onOk() {
      await deleteUser(row.id);
      message.success('用户已删除，相关资产已完成释放');
      gridApi.query();
    },
  });
}

function onResetMfa(row: SystemUserApi.User) {
  Modal.confirm({
    cancelText: '取消',
    content: `重置后“${row.displayName}”下次登录需要重新绑定验证器。`,
    okText: '确认重置',
    title: '重置 MFA',
    async onOk() {
      await resetUserMfa(row.id);
      message.success('MFA 已重置');
      gridApi.query();
    },
  });
}

function onResetPassword(row: SystemUserApi.User) {
  const password = ref('');
  Modal.confirm({
    cancelText: '取消',
    content: h(Input, {
      autocomplete: 'new-password',
      placeholder: '请输入 8–72 位新密码',
      type: 'password',
      value: password.value,
      'onUpdate:value': (value: string) => (password.value = value),
    }),
    okText: '确认重置',
    title: `重置“${row.displayName}”的密码`,
    async onOk() {
      if (password.value.length < 8 || password.value.length > 72) {
        message.warning('密码长度必须为 8–72 位');
        throw new Error('invalid password');
      }
      await resetUserPassword(row.id, password.value);
      message.success('密码已重置');
    },
  });
}

function onDepartmentSelect(id: string | undefined) {
  selectedDepartmentId.value = id;
  gridApi.query();
}
</script>

<template>
  <Page
    auto-content-height
    class="system-management-page"
    content-class="!min-h-0 !overflow-hidden"
    description="管理用户手机号、部门归属、安全策略与登录凭据。"
    header-class="gap-4 max-sm:flex-col max-sm:items-stretch"
    title="用户管理"
  >
    <template #extra>
      <div class="flex flex-wrap items-center gap-2">
        <Dropdown :trigger="['click']">
          <Button>
            更多
            <IconifyIcon icon="lucide:chevron-down" aria-hidden="true" />
          </Button>
          <template #overlay>
            <Menu>
              <MenuItem @click="router.push('/system/login-log')">
                登录日志
              </MenuItem>
              <MenuItem @click="router.push('/system/operation-log')">
                操作日志
              </MenuItem>
              <MenuItem @click="ipRuleModalApi.open()">
                通用 IP 白名单
              </MenuItem>
            </Menu>
          </template>
        </Dropdown>
        <Button type="primary" @click="onCreate">
          <Plus class="size-5" aria-hidden="true" />
          新增用户
        </Button>
      </div>
    </template>
    <FormModal @success="gridApi.query()" />
    <IpRuleModal />
    <div class="flex h-full min-h-0 min-w-0 gap-3 max-xl:flex-col">
      <DepartmentManager
        class="w-[230px] shrink-0 max-xl:max-h-[240px] max-xl:w-full"
        @loaded="onDepartmentsLoaded"
        @select="onDepartmentSelect"
      />
      <div class="ux-fill-grid-host h-full min-h-0 min-w-0 flex-1">
        <Grid />
      </div>
    </div>
  </Page>
</template>
