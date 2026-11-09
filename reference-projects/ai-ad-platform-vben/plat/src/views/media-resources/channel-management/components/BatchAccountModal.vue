<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { AccountTypeRecord } from '#/api/mpower';

import { computed, reactive, ref } from 'vue';

import {
  Button,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Select,
  Table,
} from 'ant-design-vue';

import { batchCreateChannelAccounts, getAccountTypes } from '#/api/mpower';

interface AccountDraft {
  accountId: string;
  accountType: string;
  key: number;
}

const props = defineProps<{ channelId: number | string }>();
const emit = defineEmits<{ success: [] }>();
const open = ref(false);
const saving = ref(false);
const text = ref('');
const defaultType = ref<string>();
const accountTypes = ref<AccountTypeRecord[]>([]);
const selectedKeys = ref<number[]>([]);
let nextKey = 1;
const rows = reactive<AccountDraft[]>([]);

const options = computed(() =>
  accountTypes.value.map((item) => ({
    label: item.accountType,
    value: item.accountType,
  })),
);
const columns: TableColumnsType = [
  { customRender: ({ index }) => index + 1, title: '序号', width: 70 },
  { dataIndex: 'accountId', title: '账户 ID' },
  { dataIndex: 'accountType', title: '账户类型', width: 220 },
  { key: 'action', title: '操作', width: 90 },
];

function addRow(accountId = '', accountType = '') {
  rows.push({ accountId, accountType, key: nextKey++ });
}

async function show() {
  text.value = '';
  defaultType.value = undefined;
  selectedKeys.value = [];
  rows.splice(0);
  addRow();
  open.value = true;
  const response = await getAccountTypes();
  accountTypes.value = response.data ?? [];
}

function scan() {
  const ids = text.value
    .split(/\r?\n+/)
    .map((line) => line.trim().replace(/^act_/, ''))
    .filter((line) => /^\d+$/.test(line));
  if (ids.length === 0) {
    message.warning('未识别到有效账户 ID');
    return;
  }
  const existing = new Set(rows.map((item) => item.accountId).filter(Boolean));
  if (rows.length === 1 && !rows[0]?.accountId) rows.splice(0, 1);
  ids.forEach((id) => {
    if (!existing.has(id)) addRow(id, defaultType.value ?? '');
  });
}

function batchSetType(value: any) {
  value = String(value ?? '');
  rows.forEach((row) => {
    if (selectedKeys.value.includes(row.key)) row.accountType = value;
  });
  selectedKeys.value = [];
}

async function submit() {
  const validRows = rows.filter((item) => item.accountId);
  if (validRows.length === 0) {
    message.warning('请至少添加一个账户 ID');
    return;
  }
  if (validRows.some((item) => !/^\d+$/.test(item.accountId))) {
    message.warning('账户 ID 必须为纯数字');
    return;
  }
  if (validRows.some((item) => !item.accountType)) {
    message.warning('请为所有账户选择账户类型');
    return;
  }
  const unique = [
    ...new Map(validRows.map((item) => [item.accountId, item])).values(),
  ];
  saving.value = true;
  try {
    await batchCreateChannelAccounts({
      accountList: unique.map(({ accountId, accountType }) => ({
        accountId,
        accountType,
      })),
      channelId: props.channelId,
    });
    message.success('批量导入成功');
    open.value = false;
    emit('success');
  } finally {
    saving.value = false;
  }
}

defineExpose({ show });
</script>

<template>
  <Modal
    v-model:open="open"
    :confirm-loading="saving"
    :width="920"
    ok-text="确定导入"
    title="批量导入账户"
    @ok="submit"
  >
    <Form layout="vertical">
      <div class="grid gap-4 md:grid-cols-[220px_1fr]">
        <FormItem label="默认账户类型">
          <Select v-model:value="defaultType" :options="options" allow-clear />
        </FormItem>
        <FormItem label="ID 识别（每行一个）">
          <Input.TextArea
            v-model:value="text"
            :rows="4"
            placeholder="123456789\nact_987654321"
          />
        </FormItem>
      </div>
      <Button type="primary" @click="scan">开始识别</Button>
    </Form>

    <div class="my-4 flex flex-wrap items-center gap-2">
      <Button
        danger
        @click="
          rows.splice(0, rows.length);
          addRow();
        "
      >
        清空列表
      </Button>
      <Select
        :disabled="selectedKeys.length === 0"
        :options="options"
        class="w-48"
        placeholder="批量修改账户类型"
        @change="batchSetType"
      />
      <Button @click="addRow()">+ 添加一行</Button>
    </div>

    <Table
      :columns="columns"
      :data-source="rows"
      :pagination="false"
      :row-selection="{
        selectedRowKeys: selectedKeys,
        onChange: (keys: (number | string)[]) =>
          (selectedKeys = keys.map(Number)),
      }"
      row-key="key"
      :scroll="{ y: 360 }"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <Input
          v-if="column.dataIndex === 'accountId'"
          v-model:value="record.accountId"
          placeholder="请输入账户 ID"
        />
        <Select
          v-else-if="column.dataIndex === 'accountType'"
          v-model:value="record.accountType"
          :options="options"
          class="w-full"
        />
        <Button
          v-else-if="column.key === 'action'"
          danger
          type="link"
          @click="rows.splice(rows.indexOf(record as AccountDraft), 1)"
        >
          删除
        </Button>
      </template>
    </Table>
  </Modal>
</template>
