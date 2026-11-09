<script lang="ts" setup>
import type { SystemDepartmentApi } from '#/api';

import { computed, ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';

import { useVbenForm } from '#/adapter/form';
import {
  createDepartment,
  getSystemDepartmentTree,
  getUserList,
  updateDepartment,
} from '#/api';

import { useFormSchema } from '../data';

const emit = defineEmits(['success']);
const editingId = ref<string>();

type TreeOption = {
  children?: TreeOption[];
  label: string;
  value: string;
};

function toOptions(nodes: SystemDepartmentApi.Department[]): TreeOption[] {
  return nodes.map((node) => ({
    children: toOptions(node.children ?? []),
    label: node.deptName,
    value: node.id,
  }));
}

async function buildSchema() {
  const [departmentsResult, usersResult] = await Promise.allSettled([
    getSystemDepartmentTree(),
    getUserList({ page: 1, pageSize: 200, status: 1 }),
  ]);
  const departments =
    departmentsResult.status === 'fulfilled' ? departmentsResult.value : [];
  const users =
    usersResult.status === 'fulfilled' ? usersResult.value.items : [];
  const departmentOptions: TreeOption[] = [
    { label: '根部门', value: '0' },
    ...toOptions(departments),
  ];
  const userOptions = users.map((user) => ({
    label: `${user.displayName}（${user.phone}）`,
    value: user.id,
  }));
  return useFormSchema().map((field) => {
    if (field.fieldName === 'parentId') {
      return {
        ...field,
        componentProps: {
          ...field.componentProps,
          treeData: departmentOptions,
        },
      };
    }
    if (field.fieldName === 'leaderUserId') {
      return {
        ...field,
        componentProps: { ...field.componentProps, options: userOptions },
      };
    }
    return field;
  });
}

const [Form, formApi] = useVbenForm({
  schema: useFormSchema(),
  showDefaultActions: false,
});

const title = computed(() => (editingId.value ? '编辑部门' : '新增部门'));

const [Drawer, drawerApi] = useVbenDrawer({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;
    const values = await formApi.getValues<SystemDepartmentApi.SaveRequest>();
    const payload: SystemDepartmentApi.SaveRequest = {
      ...values,
      deptCode: values.deptCode.trim().toUpperCase(),
      leaderUserId: values.leaderUserId || undefined,
      remark: values.remark?.trim() || undefined,
      sortOrder: values.sortOrder ?? 0,
    };
    drawerApi.lock();
    try {
      if (editingId.value) {
        await updateDepartment(editingId.value, payload);
      } else {
        await createDepartment(payload);
      }
      drawerApi.close();
      emit('success');
    } finally {
      drawerApi.unlock();
    }
  },
  async onOpenChange(open) {
    if (!open) return;
    const data = drawerApi.getData<
      Partial<SystemDepartmentApi.Department> & { parentId?: string }
    >();
    const initialValues = data?.id
      ? data
      : {
          parentId: data?.parentId ?? '0',
          sortOrder: 0,
          status: 1,
        };

    editingId.value = data?.id;
    formApi.setState({ schema: useFormSchema() });
    await formApi.resetForm();
    await formApi.setValues(initialValues);

    drawerApi.lock();
    try {
      formApi.setState({ schema: await buildSchema() });
      await formApi.setValues(initialValues);
    } finally {
      drawerApi.unlock();
    }
  },
});
</script>

<template>
  <Drawer class="w-full max-w-[560px]" :title="title">
    <Form />
  </Drawer>
</template>
