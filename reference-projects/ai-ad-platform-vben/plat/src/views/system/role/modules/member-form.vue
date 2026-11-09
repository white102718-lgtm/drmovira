<script lang="ts" setup>
import { useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { addUserToRole, getUserList } from '#/api';

const emit = defineEmits(['success']);

type MemberModalData = {
  roleId: string;
};

type FormValues = {
  userIds: string[];
};

const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' } },
  layout: 'horizontal',
  schema: [],
  showDefaultActions: false,
});

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;

    const { userIds } = await formApi.getValues<FormValues>();
    if (userIds.length === 0) {
      message.warning('请至少选择一名用户');
      return;
    }

    const { roleId } = modalApi.getData<MemberModalData>();
    modalApi.lock();
    try {
      await Promise.all(userIds.map((userId) => addUserToRole(userId, roleId)));
      await modalApi.close();
      message.success('已添加角色成员');
      emit('success');
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(open) {
    if (!open) return;

    const { roleId } = modalApi.getData<MemberModalData>();
    modalApi.lock();
    try {
      const [users, currentMembers] = await Promise.all([
        getUserList({ page: 1, pageSize: 200, status: 1 }),
        getUserList({ page: 1, pageSize: 200, roleId }),
      ]);
      const memberIds = new Set(currentMembers.items.map((user) => user.id));
      const options = users.items
        .filter((user) => !memberIds.has(user.id))
        .map((user) => ({
          label: user.phone
            ? `${user.displayName}（${user.phone}）`
            : user.displayName,
          value: user.id,
        }));

      formApi.resetForm();
      formApi.setState({
        schema: [
          {
            component: 'Select',
            componentProps: {
              mode: 'multiple',
              optionFilterProp: 'label',
              options,
              placeholder: '请选择用户',
              showSearch: true,
            },
            fieldName: 'userIds',
            help: '仅添加当前角色，不会创建、删除或修改用户账号。',
            label: '选择用户',
            rules: 'required',
          },
        ],
      });
      await formApi.setValues({ userIds: [] });
    } finally {
      modalApi.unlock();
    }
  },
});
</script>

<template>
  <Modal class="w-full max-w-[640px]" title="添加角色成员">
    <Form />
  </Modal>
</template>
