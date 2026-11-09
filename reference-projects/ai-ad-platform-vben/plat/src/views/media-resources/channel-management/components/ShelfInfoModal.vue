<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue';

import { reactive, ref } from 'vue';

import {
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
} from 'ant-design-vue';

import { getChannelGoods, saveChannelGoods } from '#/api/mpower';

import { REGION_OPTIONS, TIMEZONE_OPTIONS } from '../constants';

const emit = defineEmits<{ success: [] }>();
const open = ref(false);
const loading = ref(false);
const saving = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({
  channelId: '' as number | string,
  description: '',
  launchArea: ['999'] as string[],
  minBuyCount: 1,
  productName: '',
  rebate: 0,
  serviceFee: 0,
  stock: 9999,
  timezone: ['999'] as string[],
});

function normalizeExclusive(values: string[]) {
  if (values.at(-1) === '999') return ['999'];
  return values.filter((value) => value !== '999');
}

async function show(record: any) {
  Object.assign(form, {
    channelId: record.id,
    description: '',
    launchArea: ['999'],
    minBuyCount: 1,
    productName: '',
    rebate: 0,
    serviceFee: 0,
    stock: 9999,
    timezone: ['999'],
  });
  open.value = true;
  loading.value = true;
  try {
    const response = await getChannelGoods(record.id);
    const data: any = response.data;
    if (data) {
      Object.assign(form, {
        channelId: data.channelId ?? record.id,
        description: data.remark ?? '',
        launchArea: data.launchRegion
          ? String(data.launchRegion).split(',')
          : ['999'],
        minBuyCount: data.minBuyLimit ?? 1,
        productName: data.goodsName ?? '',
        rebate: data.rebateRate ?? 0,
        serviceFee: data.serviceFeeRatio ?? 0,
        stock: data.stockNum ?? 9999,
        timezone: data.timezone ? String(data.timezone).split(',') : ['999'],
      });
    }
  } finally {
    loading.value = false;
  }
}

async function submit() {
  await formRef.value?.validate();
  saving.value = true;
  try {
    await saveChannelGoods({
      channelId: form.channelId,
      goodsName: form.productName,
      launchRegion: form.launchArea.includes('999')
        ? ''
        : form.launchArea.join(','),
      minBugLimit: form.minBuyCount,
      rebateRate: form.rebate,
      remark: form.description,
      serviceFeeRatio: form.serviceFee,
      stockNum: form.stock,
      timezone: form.timezone.includes('999') ? '' : form.timezone.join(','),
    });
    message.success('上架信息保存成功');
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
    :width="800"
    title="上架信息"
    @ok="submit"
  >
    <Form ref="formRef" :disabled="loading" :model="form" layout="vertical">
      <div class="grid grid-cols-1 gap-x-5 md:grid-cols-2">
        <FormItem
          label="商品名称"
          name="productName"
          :rules="[{ required: true }]"
        >
          <Input v-model:value="form.productName" />
        </FormItem>
        <FormItem
          label="服务费"
          name="serviceFee"
          :rules="[{ required: true }]"
        >
          <InputNumber
            v-model:value="form.serviceFee"
            :min="0"
            :max="100"
            :precision="2"
            addon-after="%"
            class="w-full"
          />
        </FormItem>
        <FormItem label="返点">
          <InputNumber
            v-model:value="form.rebate"
            :min="0"
            :max="100"
            :precision="2"
            addon-after="%"
            class="w-full"
          />
        </FormItem>
        <FormItem label="库存" name="stock" :rules="[{ required: true }]">
          <InputNumber
            v-model:value="form.stock"
            :min="1"
            :max="9999"
            class="w-full"
          />
        </FormItem>
        <FormItem
          label="最低购买数量"
          name="minBuyCount"
          :rules="[{ required: true }]"
        >
          <InputNumber
            v-model:value="form.minBuyCount"
            :min="1"
            :max="100"
            class="w-full"
          />
        </FormItem>
        <FormItem
          label="投放地区"
          name="launchArea"
          :rules="[{ required: true }]"
        >
          <Select
            v-model:value="form.launchArea"
            :options="REGION_OPTIONS"
            mode="multiple"
            show-search
            @change="
              (value) =>
                (form.launchArea = normalizeExclusive(
                  (value || []) as string[],
                ))
            "
          />
        </FormItem>
        <FormItem
          label="适合时区"
          name="timezone"
          :rules="[{ required: true }]"
        >
          <Select
            v-model:value="form.timezone"
            :options="[
              { label: '全部时区', value: '999' },
              ...TIMEZONE_OPTIONS,
            ]"
            mode="multiple"
            show-search
            @change="
              (value) =>
                (form.timezone = normalizeExclusive((value || []) as string[]))
            "
          />
        </FormItem>
        <FormItem label="说明">
          <Input.TextArea
            v-model:value="form.description"
            :rows="3"
            :maxlength="200"
            show-count
          />
        </FormItem>
      </div>
    </Form>
  </Modal>
</template>
