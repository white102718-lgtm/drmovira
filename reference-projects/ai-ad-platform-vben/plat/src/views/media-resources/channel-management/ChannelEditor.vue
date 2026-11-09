<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue';

import { computed, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import {
  Button,
  Card,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Radio,
  RadioGroup,
  Select,
  Skeleton,
} from 'ant-design-vue';

import { createChannel, getChannel, updateChannel } from '#/api/mpower';
import SecondaryPageHeader from '#/components/SecondaryPageHeader.vue';

import MediaResourcePage from '../components/MediaResourcePage.vue';
import { SETTLEMENT_OPTIONS, TEAM_OPTIONS } from './constants';

const route = useRoute();
const router = useRouter();
const formRef = ref<FormInstance>();
const loading = ref(false);
const saving = ref(false);
const channelId = computed(() => String(route.params.id ?? ''));
const isEditing = computed(() => Boolean(channelId.value));
const title = computed(() => (isEditing.value ? '编辑渠道' : '添加渠道'));
const form = reactive({
  belongTeam: '',
  buyoutAmount: undefined as number | undefined,
  channelCode: '',
  channelName: '',
  channelShortName: '',
  channelType: 1,
  loginUrl: '',
  paymentAddress: '',
  remark: '',
  settlementCurrency: 'USD',
  settlementMethod: '预付实消',
  status: 1,
});

async function load() {
  if (!channelId.value) return;
  loading.value = true;
  try {
    const response = await getChannel(channelId.value);
    Object.assign(form, response.data ?? {});
  } finally {
    loading.value = false;
  }
}

async function submit() {
  await formRef.value?.validate();
  saving.value = true;
  try {
    const payload = { ...form } as Record<string, any>;
    if (form.settlementMethod !== '买断') delete payload.buyoutAmount;
    if (isEditing.value) {
      payload.id = channelId.value;
      await updateChannel(payload);
      message.success('保存成功');
    } else {
      await createChannel(payload);
      message.success('添加成功');
    }
    await router.push('/media-resources/channels');
  } finally {
    saving.value = false;
  }
}

watch(channelId, load, { immediate: true });
</script>

<template>
  <MediaResourcePage>
    <SecondaryPageHeader
      back-to="/media-resources/channels"
      card
      description="维护渠道基本信息与结算设置"
      :title="title"
    />

    <Card>
      <Skeleton v-if="loading" active />
      <Form v-else ref="formRef" :model="form" layout="vertical" class="w-full">
        <div class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
          <FormItem
            label="渠道类型"
            name="channelType"
            :rules="[{ required: true }]"
          >
            <RadioGroup v-model:value="form.channelType">
              <Radio :value="1">代理商</Radio>
              <Radio :value="2">号商</Radio>
            </RadioGroup>
          </FormItem>
          <FormItem
            label="所属团队"
            name="belongTeam"
            :rules="[{ required: true, message: '请选择所属团队' }]"
          >
            <Select v-model:value="form.belongTeam" :options="TEAM_OPTIONS" />
          </FormItem>
          <FormItem
            label="渠道名称"
            name="channelName"
            :rules="[{ required: true, message: '请输入渠道名称' }]"
          >
            <Input
              v-model:value="form.channelName"
              :maxlength="50"
              show-count
            />
          </FormItem>
          <FormItem
            label="渠道简称"
            name="channelShortName"
            :rules="[{ max: 15 }]"
          >
            <Input
              v-model:value="form.channelShortName"
              :maxlength="15"
              show-count
            />
          </FormItem>
          <FormItem
            label="渠道编码"
            name="channelCode"
            :rules="[
              { required: true, message: '请输入渠道编码' },
              { max: 10 },
              { pattern: /^[a-zA-Z0-9]+$/, message: '只能输入英文字母和数字' },
            ]"
          >
            <Input
              v-model:value="form.channelCode"
              :maxlength="10"
              show-count
            />
          </FormItem>
          <FormItem
            label="结算方式/要求"
            name="settlementMethod"
            :rules="[{ required: true }]"
          >
            <Select
              v-model:value="form.settlementMethod"
              :options="SETTLEMENT_OPTIONS"
            />
          </FormItem>
          <FormItem
            v-if="form.settlementMethod === '买断'"
            label="买断费"
            name="buyoutAmount"
            :rules="[{ required: true, message: '请输入买断费' }]"
          >
            <InputNumber
              v-model:value="form.buyoutAmount"
              :min="0"
              :precision="2"
              class="w-full"
            />
          </FormItem>
          <FormItem
            label="结算货币"
            name="settlementCurrency"
            :rules="[{ required: true }]"
          >
            <Select
              v-model:value="form.settlementCurrency"
              :options="
                ['USD', 'U', 'RMB'].map((value) => ({ label: value, value }))
              "
            />
          </FormItem>
          <FormItem
            class="md:col-span-2"
            label="收款地址"
            name="paymentAddress"
            :rules="[{ required: true, message: '请输入收款地址' }]"
          >
            <Input.TextArea v-model:value="form.paymentAddress" :rows="3" />
          </FormItem>
          <FormItem
            class="md:col-span-2"
            label="登录/对接链接"
            name="loginUrl"
            :rules="[{ required: true, message: '请输入登录/对接链接' }]"
          >
            <Input.TextArea v-model:value="form.loginUrl" :rows="3" />
          </FormItem>
          <FormItem label="状态" name="status" :rules="[{ required: true }]">
            <RadioGroup v-model:value="form.status">
              <Radio :value="1">正常</Radio>
              <Radio :value="0">停用</Radio>
            </RadioGroup>
          </FormItem>
          <FormItem class="md:col-span-2" label="备注">
            <Input.TextArea v-model:value="form.remark" :rows="3" />
          </FormItem>
        </div>
        <div class="flex justify-end gap-2">
          <Button @click="router.push('/media-resources/channels')">
            取消
          </Button>
          <Button :loading="saving" type="primary" @click="submit">
            {{ isEditing ? '保存' : '确认' }}
          </Button>
        </div>
      </Form>
    </Card>
  </MediaResourcePage>
</template>
