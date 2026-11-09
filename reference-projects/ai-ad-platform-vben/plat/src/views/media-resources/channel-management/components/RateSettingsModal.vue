<script lang="ts" setup>
import type { Dayjs } from 'dayjs';

import type { ChannelRecord } from '#/api/mpower';

import { computed, reactive, ref } from 'vue';

import {
  Button,
  DatePicker,
  Form,
  FormItem,
  InputNumber,
  message,
  Modal,
  Pagination,
  Table,
  Tag,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { createRate, getRatePage, updateRate } from '#/api/mpower';

type RateRecord = Record<string, any>;

const emit = defineEmits<{ success: [] }>();
const open = ref(false);
const editorOpen = ref(false);
const loading = ref(false);
const saving = ref(false);
const channel = ref<ChannelRecord>();
const rows = ref<RateRecord[]>([]);
const page = reactive({ pageNum: 1, pageSize: 10, total: 0 });
const form = reactive({
  effectiveDate: dayjs(),
  expiryDate: undefined as Dayjs | undefined,
  id: undefined as number | string | undefined,
  rebateRate: 0,
  serviceFee: 0,
});

const editorTitle = computed(() => (form.id ? '编辑费率' : '添加费率'));
const columns: any[] = [
  {
    customRender: ({ index }: { index: number }) => index + 1,
    title: '序号',
    width: 70,
  },
  { dataIndex: 'serviceFee', title: '服务费' },
  { dataIndex: 'rebateRate', title: '返点/折扣' },
  { dataIndex: 'effectiveDate', title: '生效日期' },
  { dataIndex: 'expiryDate', title: '失效日期' },
  { dataIndex: 'settingDate', title: '修改时间' },
  { dataIndex: 'status', title: '状态' },
  { key: 'action', title: '操作', width: 90 },
];

async function load() {
  if (!channel.value) return;
  loading.value = true;
  try {
    const response = await getRatePage({
      channelId: channel.value.id,
      pageNum: page.pageNum,
      pageSize: page.pageSize,
    });
    rows.value = (response.rows ?? []).map((item: any) => ({
      ...item,
      expiryDate: item.expiryDate || '长期',
      settingDate: item.updateTime || item.createTime,
      status: Number(item.status) === 1 ? '生效中' : '失效',
    }));
    page.total = response.total ?? 0;
  } finally {
    loading.value = false;
  }
}

function show(record: any) {
  channel.value = record;
  page.pageNum = 1;
  open.value = true;
  void load();
}

function showEditor(record?: RateRecord) {
  form.id = record?.id;
  form.serviceFee = Number(record?.serviceFee ?? 0);
  form.rebateRate = Number(record?.rebateRate ?? 0);
  form.effectiveDate = dayjs(record?.effectiveDate ?? undefined);
  form.expiryDate =
    record?.expiryDate && record.expiryDate !== '长期'
      ? dayjs(record.expiryDate)
      : undefined;
  editorOpen.value = true;
}

function overlaps(start: string, end?: string) {
  const from = dayjs(start).valueOf();
  const to = end ? dayjs(end).valueOf() : Number.POSITIVE_INFINITY;
  return rows.value.some((item) => {
    if (form.id && String(item.id) === String(form.id)) return false;
    const itemFrom = dayjs(item.effectiveDate).valueOf();
    const itemTo =
      item.expiryDate && item.expiryDate !== '长期'
        ? dayjs(item.expiryDate).valueOf()
        : Number.POSITIVE_INFINITY;
    return from <= itemTo && itemFrom <= to;
  });
}

async function submit() {
  if (!channel.value || !form.effectiveDate) {
    message.warning('请选择生效日期');
    return;
  }
  const effectiveDate = form.effectiveDate.format('YYYY-MM-DD');
  const expiryDate = form.expiryDate?.format('YYYY-MM-DD');
  if (expiryDate && dayjs(expiryDate).isBefore(effectiveDate)) {
    message.warning('失效日期不能早于生效日期');
    return;
  }
  if (overlaps(effectiveDate, expiryDate)) {
    message.error('该时间范围与已有费率重叠');
    return;
  }
  const payload = {
    channelId: channel.value.id,
    effectiveDate,
    expiryDate: expiryDate ?? null,
    id: form.id,
    rebateRate: Number(form.rebateRate || 0),
    serviceFee: Number(form.serviceFee),
  };
  saving.value = true;
  try {
    await (form.id ? updateRate(payload) : createRate(payload));
    message.success(form.id ? '费率编辑成功' : '费率添加成功');
    editorOpen.value = false;
    await load();
    emit('success');
  } finally {
    saving.value = false;
  }
}

defineExpose({ show });
</script>

<template>
  <Modal v-model:open="open" :width="1000" title="费率设置" :footer="null">
    <Button class="mb-4" type="primary" @click="showEditor()">
      + 添加费率
    </Button>
    <Table
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      :pagination="false"
      row-key="id"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'serviceFee'">
          {{ record.serviceFee }}%
        </template>
        <template v-else-if="column.dataIndex === 'rebateRate'">
          {{ record.rebateRate }}%
        </template>
        <Tag
          v-else-if="column.dataIndex === 'status'"
          :color="record.status === '生效中' ? 'success' : 'error'"
        >
          {{ record.status }}
        </Tag>
        <Button
          v-else-if="column.key === 'action'"
          type="link"
          @click="showEditor(record)"
        >
          编辑
        </Button>
      </template>
    </Table>
    <Pagination
      v-model:current="page.pageNum"
      v-model:page-size="page.pageSize"
      class="mt-4 text-right"
      :page-size-options="['10', '50', '100', '500']"
      :total="page.total"
      show-size-changer
      @change="load"
    />
  </Modal>

  <Modal
    v-model:open="editorOpen"
    :confirm-loading="saving"
    :title="editorTitle"
    @ok="submit"
  >
    <Form layout="vertical">
      <FormItem label="服务费">
        <InputNumber
          v-model:value="form.serviceFee"
          :min="0"
          :max="100"
          :precision="1"
          addon-after="%"
          class="w-full"
        />
      </FormItem>
      <FormItem label="返点/折扣">
        <InputNumber
          v-model:value="form.rebateRate"
          :min="0"
          :precision="2"
          class="w-full"
        />
      </FormItem>
      <FormItem label="生效日期" required>
        <DatePicker v-model:value="form.effectiveDate" class="w-full" />
      </FormItem>
      <FormItem label="失效日期">
        <DatePicker
          v-model:value="form.expiryDate"
          class="w-full"
          placeholder="长期"
          allow-clear
        />
      </FormItem>
    </Form>
  </Modal>
</template>
