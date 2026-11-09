<script lang="ts" setup>
import type { SystemDepartmentApi, SystemRoleApi, SystemUserApi } from '#/api';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { message, Modal as AntModal } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  createUser,
  getSystemDepartmentTree,
  getRoleList,
  getUserDetail,
  updateUser,
} from '#/api';

import { useFormSchema } from '../data';

const emit = defineEmits(['success']);

type DepartmentTreeOption = {
  children?: DepartmentTreeOption[];
  label: string;
  value: string;
};

type PreservedFields = Pick<
  SystemUserApi.SaveRequest,
  'avatarUrl' | 'departmentScopes' | 'ipAccessMode' | 'ipCidrs'
>;

type UserFormValues = Omit<SystemUserApi.SaveRequest, keyof PreservedFields>;

type PhoneNumberInputExpose = {
  getPhoneValue: () => string;
};

const editingId = ref<string>();
const originalStatus = ref<SystemUserApi.User['status']>();
const preservedFields = ref<PreservedFields>({
  avatarUrl: undefined,
  departmentScopes: [],
  ipAccessMode: 0,
  ipCidrs: [],
});

function toDepartmentOptions(
  nodes: SystemDepartmentApi.Department[],
): DepartmentTreeOption[] {
  return nodes.map((node) => ({
    children: toDepartmentOptions(node.children ?? []),
    label: node.status === 1 ? node.deptName : `${node.deptName}（停用）`,
    value: node.id,
  }));
}

async function buildSchema() {
  const [roles, departments] = await Promise.all([
    getRoleList({ page: 1, pageSize: 200, status: 1 }),
    getSystemDepartmentTree(),
  ]);
  const roleOptions = roles.items.map((role: SystemRoleApi.Role) => ({
    label: role.roleName,
    value: role.id,
  }));
  const departmentOptions = toDepartmentOptions(departments);
  return useFormSchema().map((field) => {
    if (field.fieldName === 'roleIds') {
      return {
        ...field,
        componentProps: { ...field.componentProps, options: roleOptions },
      };
    }
    if (field.fieldName === 'primaryDepartmentId') {
      return {
        ...field,
        // 仅新增用户要求选择主部门，编辑时沿用原有校验规则。
        rules: editingId.value ? field.rules : ('required' as const),
        componentProps: {
          ...field.componentProps,
          treeData: departmentOptions,
        },
      };
    }
    return field;
  });
}

function configureOrganizationFieldAccess(
  schema: Awaited<ReturnType<typeof buildSchema>>,
  feishuManaged: boolean,
) {
  if (!feishuManaged) return schema;
  return schema.map((field) => {
    if (field.fieldName === 'phone') {
      return {
        ...field,
        componentProps: { ...field.componentProps, disabled: true },
        help: '飞书同步用户的手机号由组织同步维护',
      };
    }
    if (field.fieldName === 'primaryDepartmentId') {
      return {
        ...field,
        componentProps: { ...field.componentProps, disabled: true },
        help: '飞书同步用户的部门由组织同步维护',
      };
    }
    return field;
  });
}

const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' } },
  layout: 'horizontal',
  schema: [],
  showDefaultActions: false,
});

const title = computed(() => (editingId.value ? '编辑用户' : '新增用户'));

function confirmDisableUser(): Promise<boolean> {
  return new Promise((resolve) => {
    AntModal.confirm({
      cancelText: '取消',
      content:
        '停用会立即注销该用户的会话；其独占资产将恢复可分配，共享资产仅移除该用户的使用关系。',
      okButtonProps: { danger: true },
      okText: '确认停用',
      title: '确认停用用户',
      onCancel: () => resolve(false),
      onOk: () => resolve(true),
    });
  });
}

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const phone = formApi
      .getFieldComponentRef<PhoneNumberInputExpose>('phone')
      ?.getPhoneValue();
    if (phone !== undefined) {
      await formApi.setFieldValue('phone', phone, false);
    }
    if (!editingId.value) {
      const values = await formApi.getValues<UserFormValues>();
      // 新增时先清理姓名字段再校验，避免纯空格显示名称通过必填校验。
      await formApi.setValues({
        displayName: values.displayName?.trim() ?? '',
        englishNickname: values.englishNickname?.trim() ?? '',
        realName: values.realName?.trim() ?? '',
      });
    }
    const { valid } = await formApi.validate();
    if (!valid) return;

    const values = await formApi.getValues<UserFormValues>();
    const password = values.password?.trim();
    if (!editingId.value && !password) {
      message.warning('新建用户必须设置初始密码');
      return;
    }
    if (password && (password.length < 8 || password.length > 72)) {
      message.warning('密码长度必须为 8–72 位');
      return;
    }

    const payload: SystemUserApi.SaveRequest = {
      ...values,
      ...preservedFields.value,
      email: values.email?.trim() || undefined,
      englishNickname: values.englishNickname?.trim() || undefined,
      password: password || undefined,
      primaryDepartmentId: values.primaryDepartmentId || undefined,
      realName: values.realName?.trim() || undefined,
      remark: values.remark?.trim() || undefined,
      roleIds: values.roleIds ?? [],
    };

    if (
      editingId.value &&
      originalStatus.value === 1 &&
      payload.status === 0 &&
      !(await confirmDisableUser())
    ) {
      return;
    }

    modalApi.lock();
    try {
      if (editingId.value) {
        await updateUser(editingId.value, payload);
      } else {
        await createUser(payload);
      }
      await modalApi.close();
      emit('success');
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(open) {
    if (!open) return;
    modalApi.lock();
    try {
      formApi.resetForm();
      const row = modalApi.getData<SystemUserApi.User>();
      editingId.value = row?.id;
      originalStatus.value = row?.status;
      const [loadedSchema, detail] = await Promise.all([
        buildSchema(),
        row?.id ? getUserDetail(row.id) : Promise.resolve(undefined),
      ]);
      // 编辑用户时密码通过独立的“重置密码”弹框修改，避免在编辑弹窗中展示或提交密码。
      const schema = row?.id
        ? loadedSchema.filter((field) => field.fieldName !== 'password')
        : loadedSchema;
      formApi.setState({
        schema: configureOrganizationFieldAccess(
          schema,
          detail?.user.sourceType === 'FEISHU',
        ),
      });
      if (detail) {
        preservedFields.value = {
          avatarUrl: detail.user.avatarUrl?.trim() || undefined,
          departmentScopes: detail.departmentScopes,
          ipAccessMode: detail.user.ipAccessMode,
          ipCidrs: detail.ipCidrs,
        };
        await formApi.setValues({
          ...detail.user,
          password: undefined,
          roleIds: detail.roleIds,
        });
      } else {
        preservedFields.value = {
          avatarUrl: undefined,
          departmentScopes: [],
          ipAccessMode: 0,
          ipCidrs: [],
        };
        await formApi.setValues({
          phone: '+86',
          roleIds: [],
          status: 1,
        });
      }
    } finally {
      modalApi.unlock();
    }
  },
});
</script>

<template>
  <Modal class="w-full max-w-[760px]" :title="title">
    <Form />
  </Modal>
</template>
