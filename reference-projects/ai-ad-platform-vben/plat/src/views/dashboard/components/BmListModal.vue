<script setup lang="ts">
import { ref } from 'vue';

import { message, Modal, Tooltip } from 'ant-design-vue';

import { getBmMap } from '#/api/dashboard';

const open = ref(false);
const loading = ref(false);
const accountId = ref('');
const bmList = ref<Array<{ bm_id: string; bm_name: string }>>([]);

const openModal = async (accId: string) => {
  // 接口统一返回不带 act_ 前缀的键，兼容两种账户 ID 来源。
  const normalizedId = accId.trim().replace(/^act_/, '');
  accountId.value = normalizedId;
  bmList.value = [];
  open.value = true;
  loading.value = true;
  try {
    const bmMap = await getBmMap([normalizedId]);
    bmList.value = bmMap?.[normalizedId] ?? [];
  } finally {
    loading.value = false;
  }
};

defineExpose({ openModal });

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    message.success(`已复制: ${text}`);
  } catch {
    message.error('复制失败');
  }
};
</script>

<template>
  <Modal v-model:open="open" :footer="null" title="账户 BM" width="480px">
    <div class="mb-2 text-gray-500">账户 {{ accountId }}</div>
    <div v-if="loading" class="py-4 text-center">查询中…</div>
    <div
      v-else-if="bmList.length"
      class="grid grid-cols-[1fr_auto] items-center gap-x-6 gap-y-2"
    >
      <template v-for="bm in bmList" :key="bm.bm_id">
        <Tooltip :title="`点击复制 ${bm.bm_name}`">
          <a class="min-w-0 truncate" @click="copyText(bm.bm_name)">
            {{ bm.bm_name }}
          </a>
        </Tooltip>
        <Tooltip title="点击复制">
          <a class="font-mono" @click="copyText(bm.bm_id)">{{ bm.bm_id }}</a>
        </Tooltip>
      </template>
    </div>
    <div v-else class="py-4 text-center text-gray-400">未查询到该账户的 BM</div>
  </Modal>
</template>
