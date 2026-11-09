<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue';

import type { ChannelRecord } from '#/api/mpower';

import { reactive, ref } from 'vue';

import { Form, FormItem, Input, message, Modal } from 'ant-design-vue';

import { updateChannel } from '#/api/mpower';

const emit = defineEmits<{ success: [] }>();
const open = ref(false);
const saving = ref(false);
const formRef = ref<FormInstance>();
const channel = ref<ChannelRecord>();
const form = reactive({ tgGroupId: '', tgGroupName: '' });

function show(record: any) {
  channel.value = record;
  form.tgGroupId = String(record.tgGroupId ?? '');
  form.tgGroupName = record.tgGroupName ?? '';
  open.value = true;
}

async function submit() {
  await formRef.value?.validate();
  if (!channel.value) return;
  saving.value = true;
  try {
    await updateChannel({
      channelName: channel.value.channelName,
      id: channel.value.id,
      ...form,
    });
    message.success('设置成功');
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
    title="设置 Telegram 群组"
    @ok="submit"
  >
    <Form ref="formRef" :model="form" layout="vertical">
      <FormItem
        label="群组 ID"
        name="tgGroupId"
        :rules="[{ required: true, message: '请输入 Telegram 群组 ID' }]"
      >
        <Input v-model:value="form.tgGroupId" />
      </FormItem>
      <FormItem
        label="群名"
        name="tgGroupName"
        :rules="[{ required: true, message: '请输入 Telegram 群名' }]"
      >
        <Input v-model:value="form.tgGroupName" />
      </FormItem>
    </Form>
  </Modal>
</template>
