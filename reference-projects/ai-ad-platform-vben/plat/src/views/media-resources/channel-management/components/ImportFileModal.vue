<script lang="ts" setup>
import type { UploadFile } from 'ant-design-vue';

import { ref } from 'vue';

import { message, Modal, UploadDragger } from 'ant-design-vue';

import {
  downloadChannelImportTemplate,
  importChannelAccounts,
} from '#/api/mpower';

import { downloadBlob } from '../constants';

const emit = defineEmits<{ success: [] }>();
const open = ref(false);
const uploading = ref(false);
const files = ref<UploadFile[]>([]);

function show() {
  files.value = [];
  open.value = true;
}

async function downloadTemplate() {
  const result = await downloadChannelImportTemplate();
  const blob =
    result instanceof Blob
      ? result
      : new Blob([(result as any).data ?? result]);
  downloadBlob(blob, '渠道导入模板.xlsx');
}

async function submit() {
  const raw = files.value[0]?.originFileObj;
  if (!raw) {
    message.warning('请先选择要上传的文件');
    return;
  }
  if (raw.size > 5 * 1024 * 1024) {
    message.warning('文件大小不能超过 5MB');
    return;
  }
  const data = new FormData();
  data.append('file', raw);
  uploading.value = true;
  try {
    const response = await importChannelAccounts(data);
    if (response.data?.length) {
      Modal.error({ content: response.data.join('\n'), title: '导入失败' });
      return;
    }
    message.success('导入成功');
    open.value = false;
    emit('success');
  } finally {
    uploading.value = false;
  }
}

defineExpose({ show });
</script>

<template>
  <Modal
    v-model:open="open"
    :confirm-loading="uploading"
    :width="600"
    title="批量导入账户"
    @ok="submit"
  >
    <UploadDragger
      v-model:file-list="files"
      accept=".xlsx,.xls,.csv"
      :before-upload="() => false"
      :max-count="1"
    >
      <p class="text-base">将文件拖到此处，或点击选择文件</p>
      <p class="text-slate-500">支持 .xlsx、.xls、.csv，不超过 5MB</p>
    </UploadDragger>
    <a class="mt-3 inline-block" @click="downloadTemplate">下载导入模板</a>
  </Modal>
</template>
