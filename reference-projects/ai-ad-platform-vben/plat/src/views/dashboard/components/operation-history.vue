<script setup lang="ts">
import type { TableColumnsType } from 'ant-design-vue';

import { defineEmits, defineProps, h, ref, watch } from 'vue';

import { Modal, Table, Tag } from 'ant-design-vue';

import { getOperationHistory } from '#/api/dashboard';

const props = defineProps({
  record: {
    default: null,
    type: Object,
  },
  visible: {
    default: false,
    type: Boolean,
  },
});

const emit = defineEmits(['update:visible']);

interface OperationData {
  _id: string;
  data: {
    auto_run: boolean;
    dev_id: string;
    ext_info: string;
    id: string;
    is_send: boolean;
    level: string;
    time: number;
    type: string;
    value: number;
  };
  dev: {
    ad_platform: string;
    agent_line: string;
    app_id: string;
    app_name: null | string;
    description: null | string;
    game_platform: string;
    placer_id: string;
    status: number;
  };
  start_time: string;
  status: string;
  update_time: string;
}

const loading = ref(false);
const operationData = ref<OperationData[]>([]);

const columns: TableColumnsType = [
  {
    dataIndex: 'start_time',
    title: '开始时间(账户时区)',
    width: 160,
  },
  {
    dataIndex: 'update_time',
    title: '更新时间(账户时区)',
    width: 160,
  },
  {
    customRender: ({ text }: { text: string }) => {
      const statusConfig: Record<string, { color: string; text: string }> = {
        COMPLETED: { color: 'success', text: '已完成' },
        FAILED: { color: 'error', text: '失败' },
        INVALID: { color: 'default', text: '无效' },
        MANUAL: { color: 'cyan', text: '手动处理' },
        RETRY: { color: 'warning', text: '重试中' },
        SENDING: { color: 'processing', text: '发送中' },
        STARTED: { color: 'blue', text: '已开始' },
      };
      const config = statusConfig[text] || { color: 'default', text };
      return h(Tag, { color: config.color }, () => config.text);
    },
    dataIndex: 'status',
    title: '状态',
    width: 100,
  },
  {
    dataIndex: ['data', 'type'],
    title: '操作',
    width: 120,
  },
  {
    dataIndex: ['data', 'level'],
    title: 'level',
    width: 120,
  },
  {
    dataIndex: ['data', 'id'],
    title: 'id',
    width: 180,
  },
  {
    dataIndex: ['data', 'value'],
    title: 'value',
    width: 100,
  },
  {
    customRender: ({ text }: { text: number }) => {
      return !text || text === 0 ? '立刻' : text;
    },
    dataIndex: ['data', 'time'],
    title: '定时时间(账户时区)',
    width: 160,
  },
  {
    customRender: ({ text }: { text: boolean }) => {
      return h(Tag, { color: text ? 'success' : 'default' }, () =>
        text ? '是' : '否',
      );
    },
    dataIndex: ['data', 'auto_run'],
    title: '自动执行',
    width: 88,
  },
  {
    customRender: ({ text }: { text: boolean }) => {
      return h(Tag, { color: text ? 'success' : 'default' }, () =>
        text ? '是' : '否',
      );
    },
    dataIndex: ['data', 'is_send'],
    title: '需要提醒',
    width: 88,
  },
  {
    dataIndex: ['data', 'ext_info'],
    title: '额外信息',
    width: 300,
  },
];

const fetchOperationData = async () => {
  try {
    loading.value = true;
    const agent_line = props.record.name;
    const game_platform = props.record.游戏平台;
    const date = props.record.时间.split(' ')[0];
    const response = await getOperationHistory({
      agent_line,
      date,
      game_platform,
    });
    operationData.value = response || [];
  } finally {
    loading.value = false;
  }
};
watch(
  () => props.visible,
  (newValue) => {
    if (newValue) {
      fetchOperationData();
    }
  },
);
</script>

<template>
  <div class="operation-history-modal">
    <Modal
      :open="visible"
      title="操作历史"
      width="1200px"
      @update:open="(val) => emit('update:visible', val)"
      :footer="null"
      :mask-closable="true"
    >
      <Table
        :columns="columns"
        :data-source="operationData"
        :loading="loading"
        :pagination="false"
        row-key="_id"
        :scroll="{ x: 'max-content' }"
      />
    </Modal>
  </div>
</template>
