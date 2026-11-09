<script setup lang="ts">
import type { TableColumnsType } from 'ant-design-vue';

import { defineEmits, defineProps, ref, watch } from 'vue';

import { Modal, Table } from 'ant-design-vue';

import { getBiHistory } from '#/api/dashboard';

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

interface HistoryItem {
  [key: string]: any;
  ad_platform: string;
  agent_line: string;
  amount_spent: number;
  app_installs: number;
  bi_first_arppu: null | number;
  bi_first_recharge_amount: number;
  bi_first_recharge_cost: null | number;
  bi_first_recharge_users: number;
  bi_first_roas: null | number;
  bi_registration_cost: null | number;
  bi_registrations: number;
  clicks_all: number;
  clicks_unique: number;
  complete_registration: number;
  cpc: null | number;
  cpm: null | number;
  date: string;
  dev_id: null | string;
  frequency: null | number;
  game_platform: string;
  id: string;
  impressions: number;
  inline_link_clicks: number;
  purchases: number;
  purchases_value: number;
  reach: number;
  timezone_name: null | string;
  unique_inline_link_clicks: number;
}

const loading = ref(false);
const historyData = ref<HistoryItem[]>([]);

const formatDateTime = (dateString: string) => {
  if (!dateString) return '';
  return `${dateString.replace('T', ' ').slice(0, 13)}时`;
};

const columns: TableColumnsType = [
  {
    customRender: ({ text }: { text: string }) => formatDateTime(text),
    dataIndex: 'date',
    title: '日期(账户时区)',
    width: 140,
  },
  {
    dataIndex: 'game_platform',
    title: '项目名称',
    width: 100,
  },
  {
    dataIndex: 'ad_platform',
    title: '投放平台',
    width: 100,
  },
  {
    dataIndex: 'agent_line',
    title: '代理线',
    width: 80,
  },
  {
    dataIndex: 'amount_spent',
    title: '花费',
    width: 90,
  },
  {
    dataIndex: 'bi_first_recharge_users',
    title: '首充人数',
    width: 90,
  },
  {
    dataIndex: 'bi_first_recharge_amount',
    title: '首充金额',
    width: 100,
  },
  {
    dataIndex: 'bi_first_recharge_cost',
    title: '首充成本',
    width: 90,
  },
  {
    dataIndex: 'bi_first_roas',
    title: '首充roas',
    width: 90,
  },
  {
    dataIndex: 'bi_first_arppu',
    title: '首充arppu',
    width: 100,
  },
  {
    dataIndex: 'bi_registration_cost',
    title: '注册成本',
    width: 90,
  },
  {
    dataIndex: 'impressions',
    title: '展示次数',
    width: 90,
  },
  {
    dataIndex: 'clicks_all',
    title: '点击次数',
    width: 90,
  },
  {
    dataIndex: 'bi_registrations',
    title: '注册',
    width: 70,
  },
];

const fetchHistoryData = async () => {
  try {
    loading.value = true;
    const agent_line = props.record.name;
    const game_platform = props.record.游戏平台;
    const date = props.record.时间?.split(' ')[0] || '';
    historyData.value = await getBiHistory({
      agent_line,
      date,
      game_platform,
    });
  } finally {
    loading.value = false;
  }
};

watch(
  () => props.visible,
  (newValue) => {
    if (newValue) {
      fetchHistoryData();
    }
  },
);
</script>

<template>
  <div class="bi-history-modal">
    <Modal
      :open="visible"
      :title="`BI历史 - ${props.record?.游戏平台 || ''} - ${props.record?.name || ''} - ${props.record?.时间?.split(' ')[0] || ''}`"
      width="1200px"
      @update:open="(val) => emit('update:visible', val)"
      :footer="null"
      :mask-closable="true"
    >
      <Table
        :columns="columns"
        :data-source="historyData"
        :loading="loading"
        :pagination="false"
        row-key="id"
        :scroll="{ x: 'max-content' }"
      />
    </Modal>
  </div>
</template>
