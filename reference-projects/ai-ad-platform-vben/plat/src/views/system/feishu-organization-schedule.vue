<script setup lang="ts">
import type { FeishuOrganizationSchedule } from '#/api/feishu-sync';

import { computed, reactive, ref, watch } from 'vue';

import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Select,
  Switch,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { updateFeishuOrganizationSchedule } from '#/api/feishu-sync';
import { $t } from '#/locales';

const props = defineProps<{
  canManage: boolean;
  config: FeishuOrganizationSchedule;
  previewId?: string;
  previewLoading: boolean;
}>();
const emit = defineEmits<{
  preview: [];
  saved: [config: FeishuOrganizationSchedule];
}>();
const form = reactive({ ...props.config });
const saving = ref(false);
const options = computed(() => [
  ...[15, 30, 60].map((count) => ({
    label: $t('feishuOrg.minutes', { count }),
    value: count,
  })),
  { label: $t('feishuOrg.daily'), value: 0 },
]);
const nextRun = computed(() =>
  props.config.nextRunAt
    ? dayjs(props.config.nextRunAt)
        .tz('Asia/Shanghai')
        .format('YYYY-MM-DD HH:mm:ss')
    : $t('feishuOrg.off'),
);

/** 服务端因缺失保护暂停后，开关同步反映实际状态，保留其他未保存输入。 */
watch(
  () => props.config.enabled,
  (enabled) => {
    form.enabled = enabled;
  },
);

async function handleSave() {
  if (form.enabled && !props.previewId) {
    message.warning($t('feishuOrg.needPreview'));
    return;
  }
  if (
    !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(form.dailyTime) ||
    !Number.isInteger(form.missingCountLimit) ||
    form.missingCountLimit < 1 ||
    form.missingCountLimit > 100_000 ||
    !Number.isInteger(form.missingPercentLimit) ||
    form.missingPercentLimit < 1 ||
    form.missingPercentLimit > 100
  ) {
    message.warning($t('feishuOrg.invalid'));
    return;
  }
  saving.value = true;
  try {
    const config = await updateFeishuOrganizationSchedule({
      dailyTime: form.dailyTime,
      enabled: form.enabled,
      intervalMinutes: form.intervalMinutes,
      missingCountLimit: form.missingCountLimit,
      missingPercentLimit: form.missingPercentLimit,
      previewId: props.previewId,
    });
    Object.assign(form, config);
    emit('saved', config);
    message.success($t('feishuOrg.saved'));
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <Alert :message="$t('feishuOrg.previewHint')" show-icon type="info" />
    <p class="text-muted-foreground m-0 text-sm">
      {{ $t('feishuOrg.nextRun', { time: nextRun }) }}
    </p>
    <Form layout="vertical" class="max-w-2xl" :disabled="!canManage || saving">
      <Form.Item :label="$t('feishuOrg.enabled')" html-for="org-sync-enabled">
        <Switch
          id="org-sync-enabled"
          v-model:checked="form.enabled"
          :aria-label="$t('feishuOrg.enabled')"
        />
      </Form.Item>
      <Form.Item
        :label="$t('feishuOrg.frequency')"
        html-for="org-sync-frequency"
      >
        <Select
          id="org-sync-frequency"
          v-model:value="form.intervalMinutes"
          :options="options"
          class="w-full"
        />
      </Form.Item>
      <Form.Item
        v-if="form.intervalMinutes === 0"
        :label="$t('feishuOrg.dailyTime')"
        html-for="org-sync-time"
        required
      >
        <Input id="org-sync-time" v-model:value="form.dailyTime" type="time" />
      </Form.Item>
      <div class="grid gap-x-4 sm:grid-cols-2">
        <Form.Item
          :label="$t('feishuOrg.countLimit')"
          html-for="org-sync-count"
          required
        >
          <InputNumber
            id="org-sync-count"
            v-model:value="form.missingCountLimit"
            :min="1"
            :max="100000"
            :precision="0"
            class="w-full"
          />
        </Form.Item>
        <Form.Item
          :label="$t('feishuOrg.percentLimit')"
          html-for="org-sync-percent"
          required
        >
          <InputNumber
            id="org-sync-percent"
            v-model:value="form.missingPercentLimit"
            :min="1"
            :max="100"
            :precision="0"
            class="w-full"
          />
        </Form.Item>
      </div>
      <Alert
        class="mb-4"
        :message="$t('feishuOrg.protection')"
        show-icon
        type="warning"
      />
      <div class="flex flex-wrap gap-2">
        <Button :loading="previewLoading" @click="emit('preview')">
          {{ $t('feishuOrg.preview') }}
        </Button>
        <Button type="primary" :loading="saving" @click="handleSave">
          {{ $t('feishuOrg.save') }}
        </Button>
      </div>
    </Form>
  </div>
</template>
