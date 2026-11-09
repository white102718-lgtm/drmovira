<script lang="ts" setup>
import type { FormInstance, TableColumnsType } from 'ant-design-vue';

import type { AccountTypeRecord } from '#/api/mpower';

import { reactive, ref } from 'vue';

import {
  Button,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Table,
} from 'ant-design-vue';

import {
  createAccountType,
  deleteAccountType,
  getAccountTypes,
  getChannelAccounts,
} from '#/api/mpower';

const open = ref(false);
const createOpen = ref(false);
const loading = ref(false);
const formRef = ref<FormInstance>();
const records = ref<AccountTypeRecord[]>([]);
const form = reactive({ accountType: '' });

const columns: TableColumnsType = [
  { customRender: ({ index }) => index + 1, title: '序号', width: 70 },
  { dataIndex: 'accountType', title: '账户类型' },
  { key: 'action', title: '操作', width: 90 },
];

function asAccountType(record: Record<string, unknown>): AccountTypeRecord {
  return {
    accountType: String(record.accountType ?? ''),
    id: String(record.id ?? ''),
  };
}

async function load() {
  loading.value = true;
  try {
    const response = await getAccountTypes();
    records.value = response.data ?? [];
  } finally {
    loading.value = false;
  }
}

function show() {
  open.value = true;
  void load();
}

function showCreate() {
  form.accountType = '';
  createOpen.value = true;
}

async function submitCreate() {
  await formRef.value?.validate();
  if (records.value.some((item) => item.accountType === form.accountType)) {
    message.warning('账户类型名称已存在');
    return;
  }
  await createAccountType({ ...form });
  message.success('新增成功');
  createOpen.value = false;
  await load();
}

async function remove(record: AccountTypeRecord) {
  const bound = await getChannelAccounts({
    accountType: record.accountType,
    pageNum: 1,
    pageSize: 1,
  });
  Modal.confirm({
    content:
      bound.total > 0
        ? '尚有广告账户绑定此类型，删除后这些账户将变为未分类，是否继续？'
        : '是否确认删除该账户类型？',
    okButtonProps: { danger: true },
    title: '删除账户类型',
    async onOk() {
      await deleteAccountType(record.id);
      message.success('删除成功');
      await load();
    },
  });
}

defineExpose({ show });
</script>

<template>
  <Modal v-model:open="open" :width="680" title="账户类型管理" :footer="null">
    <Button class="mb-4" type="primary" @click="showCreate">+ 新增</Button>
    <Table
      :columns="columns"
      :data-source="records"
      :loading="loading"
      :pagination="false"
      row-key="id"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <Button
          v-if="column.key === 'action'"
          danger
          type="link"
          @click="remove(asAccountType(record))"
        >
          删除
        </Button>
      </template>
    </Table>
  </Modal>

  <Modal
    v-model:open="createOpen"
    title="新增账户类型"
    ok-text="确定"
    @ok="submitCreate"
  >
    <Form ref="formRef" :model="form" layout="vertical">
      <FormItem
        label="账户类型名称"
        name="accountType"
        :rules="[
          { required: true, message: '请输入账户类型名称' },
          { max: 15 },
        ]"
      >
        <Input v-model:value="form.accountType" :maxlength="15" />
      </FormItem>
    </Form>
  </Modal>
</template>
