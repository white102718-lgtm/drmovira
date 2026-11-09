<script lang="ts" setup>
import type { SystemUserApi } from '#/api/system/user';

import { ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import {
  Button,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Table,
} from 'ant-design-vue';

import { createApiKey, deleteApiKey, getUserApiKeys } from '#/api';

defineOptions({ name: 'ApiKeyForm' });

const emit = defineEmits<{ success: [] }>();

const userId = ref('');
const apiKeys = ref<SystemUserApi.ApiKey[]>([]);
const keysLoading = ref(false);

const createVisible = ref(false);
const createLoading = ref(false);
const nameValue = ref('');
const remarkValue = ref('');
const expiresDays = ref<number | undefined>(undefined);

const createdKey = ref('');
const showKeyModal = ref(false);

const columns = [
  { dataIndex: 'name', title: '名称', width: 120, align: 'center' as const },
  { dataIndex: 'remark', title: '备注', width: 100, align: 'center' as const },
  {
    dataIndex: 'key',
    title: '密钥',
    width: 100,
    ellipsis: true,
    align: 'center' as const,
  },
  {
    dataIndex: 'created_at',
    title: '创建时间',
    width: 120,
    align: 'center' as const,
  },
  {
    dataIndex: 'expires_at',
    title: '过期时间',
    width: 120,
    align: 'center' as const,
    customRender: ({ text }: { text: null | string }) => text ?? '永久有效',
  },
  {
    dataIndex: 'operation',
    title: '操作',
    width: 80,
    fixed: 'right' as const,
    align: 'center' as const,
  },
];

async function loadApiKeys() {
  if (!userId.value) return;
  keysLoading.value = true;
  try {
    const data = await getUserApiKeys(userId.value);
    apiKeys.value = Array.isArray(data) ? data : [];
  } finally {
    keysLoading.value = false;
  }
}

async function handleDelete(keyId: string) {
  const res = await deleteApiKey(userId.value, keyId);
  message.success(res.message || '撤销成功');
  await loadApiKeys();
  emit('success');
}

function openCreate() {
  nameValue.value = '';
  remarkValue.value = '';
  expiresDays.value = undefined;
  createVisible.value = true;
}

function setExpiresDays(val: null | number | string) {
  expiresDays.value = typeof val === 'number' ? val : undefined;
}

async function handleCreate() {
  if (!nameValue.value.trim()) {
    message.warning('名称为必填项');
    return;
  }
  createLoading.value = true;
  try {
    const res = await createApiKey(userId.value, {
      name: nameValue.value.trim(),
      remark: remarkValue.value || '',
      expires_days: expiresDays.value || -1,
    });
    message.success('创建成功');
    createVisible.value = false;
    createdKey.value = res.key ?? '';
    showKeyModal.value = true;
    if (createdKey.value) {
      await copyKey();
    }
    await loadApiKeys();
    emit('success');
  } finally {
    createLoading.value = false;
  }
}

async function copyKey() {
  try {
    await navigator.clipboard.writeText(createdKey.value);
    message.success('已复制');
  } catch {
    message.error('复制失败，请手动复制');
  }
}

const [VbenModal, modalApi] = useVbenModal({
  class: '!w-[900px]',
  confirmText: '关闭',
  fullscreenButton: false,
  footer: false,
  showCancelButton: false,
  showConfirmButton: false,
  async onConfirm() {
    await modalApi.close();
  },
  onOpenChange(isOpen: boolean) {
    if (isOpen) {
      const data = modalApi.getData<SystemUserApi.SystemUser>();
      userId.value = data?._id ?? '';
      apiKeys.value = [];
      loadApiKeys();
    }
  },
});
</script>
<template>
  <VbenModal>
    <template #title>
      <div class="flex w-full items-center gap-2 pr-6">
        <span>API密钥管理</span>
        <Button type="primary" @click="openCreate">创建</Button>
      </div>
    </template>
    <Table
      :columns="columns"
      :data-source="apiKeys"
      :loading="keysLoading"
      :pagination="false"
      :scroll="{ x: 700 }"
      row-key="_id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'operation'">
          <Popconfirm
            title="确认撤销该密钥？"
            @confirm="handleDelete(record.id)"
          >
            <Button danger type="text">撤销</Button>
          </Popconfirm>
        </template>
      </template>
    </Table>

    <Modal
      :confirm-loading="createLoading"
      :open="createVisible"
      title="创建API密钥"
      @ok="handleCreate"
      @update:open="createVisible = $event"
    >
      <div class="flex flex-col gap-3 py-2">
        <div>
          <div class="mb-1 text-sm">
            名称 <span class="text-red-500">*</span>
          </div>
          <Input
            :value="nameValue"
            class="w-full"
            placeholder="请输入密钥名称"
            @update:value="nameValue = $event"
          />
        </div>
        <div>
          <div class="mb-1 text-sm">备注（可选）</div>
          <Input
            :value="remarkValue"
            class="w-full"
            placeholder="请输入备注"
            @update:value="remarkValue = $event"
          />
        </div>
        <div>
          <div class="mb-1 text-sm">有效天数（可选）</div>
          <InputNumber
            :min="1"
            :value="expiresDays"
            class="w-full"
            placeholder="不填则永久有效"
            @update:value="setExpiresDays"
          />
        </div>
      </div>
    </Modal>

    <Modal
      :footer="null"
      :open="showKeyModal"
      title="保存您的密钥"
      @cancel="showKeyModal = false"
    >
      <div class="flex flex-col gap-3 py-2">
        <p class="text-sm text-gray-600">
          请将您的密钥保存在安全的地方，因为之后将无法再次查看。请妥善保管，任何持有此密钥的人都可以以您的名义发起请求。如果密钥丢失，您需要重新生成一个新的。
        </p>
        <div
          class="flex items-center gap-2 rounded border px-3 py-2 font-mono text-sm"
        >
          <span class="flex-1 break-all">{{ createdKey }}</span>
          <Button @click="copyKey">复制</Button>
        </div>
        <div class="flex justify-end">
          <Button type="primary" @click="showKeyModal = false">完成</Button>
        </div>
      </div>
    </Modal>
  </VbenModal>
</template>
