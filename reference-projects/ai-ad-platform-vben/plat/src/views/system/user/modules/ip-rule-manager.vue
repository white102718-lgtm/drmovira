<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { SystemIpRuleApi } from '#/api';

import { reactive, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import {
  Button,
  Form,
  FormItem,
  Input,
  message,
  Modal as AntModal,
  Popconfirm,
  RadioGroup,
  Space,
  Switch,
  Table,
} from 'ant-design-vue';

import {
  createGlobalIpRule,
  deleteGlobalIpRule,
  getGlobalIpRules,
  updateGlobalIpRule,
} from '#/api';

const loading = ref(false);
const saving = ref(false);
const rules = ref<SystemIpRuleApi.Rule[]>([]);
const editorOpen = ref(false);
const editingId = ref<string>();
const form = reactive<SystemIpRuleApi.SaveRequest>({
  ipCidr: '',
  remark: '',
  ruleName: '',
  status: 1,
});

const columns: TableColumnsType<SystemIpRuleApi.Rule> = [
  { dataIndex: 'ruleName', key: 'ruleName', title: '规则名称' },
  { dataIndex: 'ipCidr', key: 'ipCidr', title: 'IP / CIDR' },
  { dataIndex: 'status', key: 'status', title: '状态', width: 90 },
  { dataIndex: 'remark', key: 'remark', title: '备注' },
  { key: 'action', title: '操作', width: 150 },
];

async function load() {
  loading.value = true;
  try {
    rules.value = await getGlobalIpRules();
  } finally {
    loading.value = false;
  }
}

function openEditor(rule?: Record<string, any>) {
  editingId.value = rule?.id;
  form.ipCidr = rule?.ipCidr ?? '';
  form.ruleName = rule?.ruleName ?? '';
  form.status = rule?.status ?? 1;
  form.remark = rule?.remark ?? '';
  editorOpen.value = true;
}

async function save() {
  if (!form.ipCidr.trim()) {
    message.warning('请输入 IP 或 CIDR');
    return;
  }
  saving.value = true;
  try {
    const payload = {
      ipCidr: form.ipCidr.trim(),
      remark: form.remark?.trim() || undefined,
      ruleName: form.ruleName?.trim() || undefined,
      status: form.status,
    };
    if (editingId.value) {
      await updateGlobalIpRule(editingId.value, payload);
    } else {
      await createGlobalIpRule(payload);
    }
    editorOpen.value = false;
    message.success('IP 规则已保存');
    await load();
  } finally {
    saving.value = false;
  }
}

async function remove(id: string) {
  await deleteGlobalIpRule(id);
  message.success('IP 规则已删除');
  await load();
}

const [Modal] = useVbenModal({
  async onOpenChange(open) {
    if (open) await load();
  },
});
</script>

<template>
  <Modal class="w-full max-w-[900px]" title="通用 IP 白名单">
    <div class="mb-3 flex justify-end">
      <Button type="primary" @click="openEditor()"> 新增规则 </Button>
    </div>
    <Table
      :columns="columns"
      :data-source="rules"
      :loading="loading"
      :pagination="false"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <Switch :checked="record.status === 1" disabled />
        </template>
        <template v-else-if="column.key === 'action'">
          <Space>
            <Button type="link" @click="openEditor(record)"> 编辑 </Button>
            <Popconfirm
              title="确认删除这条 IP 规则吗？"
              @confirm="remove(record.id)"
            >
              <Button danger type="link">删除</Button>
            </Popconfirm>
          </Space>
        </template>
      </template>
    </Table>

    <AntModal
      v-model:open="editorOpen"
      :confirm-loading="saving"
      :title="editingId ? '编辑 IP 规则' : '新增 IP 规则'"
      @ok="save"
    >
      <Form layout="vertical">
        <FormItem label="规则名称" name="ruleName">
          <Input
            v-model:value="form.ruleName"
            aria-label="规则名称"
            :maxlength="100"
          />
        </FormItem>
        <FormItem label="IP / CIDR" required>
          <Input
            v-model:value="form.ipCidr"
            :maxlength="64"
            placeholder="例如 203.0.113.8 或 203.0.113.0/24"
          />
        </FormItem>
        <FormItem label="状态">
          <RadioGroup
            v-model:value="form.status"
            :options="[
              { label: '启用', value: 1 },
              { label: '停用', value: 0 },
            ]"
            option-type="button"
          />
        </FormItem>
        <FormItem label="备注" name="remark">
          <Input.TextArea
            v-model:value="form.remark"
            aria-label="备注"
            :maxlength="500"
          />
        </FormItem>
      </Form>
    </AntModal>
  </Modal>
</template>
