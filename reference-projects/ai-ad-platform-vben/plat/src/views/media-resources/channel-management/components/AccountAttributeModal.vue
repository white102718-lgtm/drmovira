<script lang="ts" setup>
import type { FormInstance, TableColumnsType } from 'ant-design-vue';

import type { AdAccountAttribute } from '#/api';

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
  createAdAccountAttribute,
  deleteAdAccountAttribute,
  getAdAccountAttributes,
} from '#/api';

const open = ref(false);
const createOpen = ref(false);
const loading = ref(false);
const saving = ref(false);
const formRef = ref<FormInstance>();
const records = ref<AdAccountAttribute[]>([]);
const form = reactive({ accountAttribute: '' });

const columns: TableColumnsType<AdAccountAttribute> = [
  { customRender: ({ index }) => index + 1, title: '序号', width: 70 },
  { dataIndex: 'accountAttribute', title: '账户属性' },
  { key: 'action', title: '操作', width: 90 },
];

function asAccountAttribute(
  record: Record<string, unknown>,
): AdAccountAttribute {
  return {
    accountAttribute: String(record.accountAttribute ?? ''),
    createTime: String(record.createTime ?? ''),
    id: String(record.id ?? ''),
  };
}

async function load() {
  loading.value = true;
  try {
    records.value = await getAdAccountAttributes();
  } finally {
    loading.value = false;
  }
}

function show() {
  open.value = true;
  void load();
}

function showCreate() {
  form.accountAttribute = '';
  createOpen.value = true;
}

async function submitCreate() {
  await formRef.value?.validate();
  saving.value = true;
  try {
    await createAdAccountAttribute({ ...form });
    message.success('账户属性已新增');
    createOpen.value = false;
    await load();
  } finally {
    saving.value = false;
  }
}

function remove(record: AdAccountAttribute) {
  Modal.confirm({
    content: '删除后，已使用该属性的广告账户将保留原历史值。是否继续？',
    okButtonProps: { danger: true },
    title: '删除账户属性',
    async onOk() {
      await deleteAdAccountAttribute(record.id);
      message.success('账户属性已删除');
      await load();
    },
  });
}

defineExpose({ show });
</script>

<template>
  <Modal v-model:open="open" :footer="null" :width="680" title="账户属性管理">
    <Button class="mb-4" type="primary" @click="showCreate">+ 新增</Button>
    <Table
      :columns="columns"
      :data-source="records"
      :loading="loading"
      :pagination="false"
      bordered
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'action'">
          <Button
            danger
            type="link"
            @click="remove(asAccountAttribute(record))"
          >
            删除
          </Button>
        </template>
      </template>
    </Table>
  </Modal>

  <Modal
    v-model:open="createOpen"
    :confirm-loading="saving"
    title="新增账户属性"
    ok-text="确定"
    @ok="submitCreate"
  >
    <Form ref="formRef" :model="form" layout="vertical">
      <FormItem
        label="账户属性名称"
        name="accountAttribute"
        :rules="[
          { required: true, message: '请输入账户属性名称' },
          { max: 15, message: '账户属性名称不能超过 15 个字符' },
        ]"
      >
        <Input v-model:value="form.accountAttribute" :maxlength="15" />
      </FormItem>
    </Form>
  </Modal>
</template>
