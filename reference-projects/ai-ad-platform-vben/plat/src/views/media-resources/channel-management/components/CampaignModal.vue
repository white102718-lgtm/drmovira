<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import { computed, ref } from 'vue';

import { Input, Modal, Table } from 'ant-design-vue';

import { getCampaignSpend } from '#/api/mpower';

import { formatMoney } from '../constants';

const open = ref(false);
const loading = ref(false);
const campaignName = ref('');
const rows = ref<Record<string, any>[]>([]);
const context = ref<Record<string, any>>({});
let timer: ReturnType<typeof setTimeout> | undefined;

const columns: TableColumnsType = [
  { dataIndex: 'campaignName', title: '系列名称' },
  { dataIndex: 'campaignId', title: '系列 ID' },
  { dataIndex: 'spendAmount', title: '花费金额' },
  { dataIndex: 'returnAmount', title: '回流金额' },
];
const totals = computed(() => ({
  returnAmount: rows.value.reduce(
    (sum, item) => sum + Number(item.returnAmount || 0),
    0,
  ),
  spendAmount: rows.value.reduce(
    (sum, item) => sum + Number(item.spendAmount || 0),
    0,
  ),
}));

async function load() {
  loading.value = true;
  try {
    const response = await getCampaignSpend({
      ...context.value,
      campaignName: campaignName.value || undefined,
      pageNum: 1,
      pageSize: 999_999,
    });
    rows.value = response.data?.records ?? [];
  } finally {
    loading.value = false;
  }
}

function show(payload: {
  accountId: string;
  endDate?: string;
  startDate?: string;
}) {
  context.value = payload;
  campaignName.value = '';
  rows.value = [];
  open.value = true;
  void load();
}

function search() {
  clearTimeout(timer);
  timer = setTimeout(load, 400);
}

defineExpose({ show });
</script>

<template>
  <Modal v-model:open="open" :width="900" title="广告系列" :footer="null">
    <Input.Search
      v-model:value="campaignName"
      class="mb-4 max-w-md"
      placeholder="请输入广告系列名称"
      allow-clear
      @change="search"
      @search="load"
    />
    <Table
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      :pagination="false"
      row-key="campaignId"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'spendAmount'">
          ${{ formatMoney(record.spendAmount) }}
        </template>
        <template v-else-if="column.dataIndex === 'returnAmount'">
          ${{ formatMoney(record.returnAmount) }}
        </template>
      </template>
      <template #summary>
        <Table.Summary>
          <Table.Summary.Row>
            <Table.Summary.Cell :index="0">汇总</Table.Summary.Cell>
            <Table.Summary.Cell :index="1">/</Table.Summary.Cell>
            <Table.Summary.Cell :index="2">
              ${{ formatMoney(totals.spendAmount) }}
            </Table.Summary.Cell>
            <Table.Summary.Cell :index="3">
              ${{ formatMoney(totals.returnAmount) }}
            </Table.Summary.Cell>
          </Table.Summary.Row>
        </Table.Summary>
      </template>
    </Table>
  </Modal>
</template>
