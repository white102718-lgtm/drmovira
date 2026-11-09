<script setup lang="ts">
import type {
  MaterialOrderDetail,
  MaterialOrderOrganization,
} from '#/api/requirement';
import { computed, ref, watch } from 'vue';
import {
  Alert,
  Button,
  Form,
  FormItem,
  Modal,
  Select,
  Spin,
  message,
} from 'ant-design-vue';
import {
  getMaterialOrderDetail,
  getMaterialOrderOrganization,
  shareMaterialOrder,
} from '#/api/requirement';

const props = defineProps<{ open: boolean; orderId?: string }>();
const emit = defineEmits<{ 'update:open': [value: boolean]; shared: [] }>();
const detail = ref<MaterialOrderDetail>();
const organization = ref<MaterialOrderOrganization>();
const recipientId = ref<string>();
const loading = ref(false);
const submitting = ref(false);
const error = ref('');
const submitError = ref('');
let requestSequence = 0;

const operatorOptions = computed(() => {
  const departments = new Map(
    (organization.value?.departments ?? []).map((row) => [row.id, row.name]),
  );
  return (organization.value?.users ?? [])
    .filter((user) =>
      user.roles.some((role) => role.toUpperCase() === 'OPERATOR'),
    )
    .map((user) => {
      const shared = detail.value?.shared_user_ids?.includes(user.id) ?? false;
      const department = departments.get(user.department_id);
      return {
        value: user.id,
        label: `${user.full_name}${department ? ` · ${department}` : ''}${shared ? '（已分享）' : ''}`,
        disabled: shared,
      };
    });
});
const sharedNames = computed(() =>
  (detail.value?.shared_users ?? []).map((row) => row.user_name).join('、'),
);
const canShare = computed(
  () =>
    !loading.value &&
    !submitting.value &&
    !error.value &&
    detail.value?.permissions.share &&
    detail.value.id === props.orderId &&
    operatorOptions.value.some(
      (option) => option.value === recipientId.value && !option.disabled,
    ),
);

function close() {
  if (!submitting.value) emit('update:open', false);
}
async function load() {
  const orderId = props.orderId;
  const token = ++requestSequence;
  detail.value = undefined;
  organization.value = undefined;
  recipientId.value = undefined;
  error.value = '';
  submitError.value = '';
  if (!orderId || !props.open) return;
  loading.value = true;
  try {
    const [order, options] = await Promise.all([
      getMaterialOrderDetail(orderId),
      getMaterialOrderOrganization(),
    ]);
    if (token !== requestSequence || !props.open) return;
    detail.value = order;
    organization.value = options;
    if (!order.permissions.share)
      error.value = '当前工单不可分享或您没有分享权限';
  } catch (value) {
    if (token === requestSequence)
      error.value = value instanceof Error ? value.message : '分享信息加载失败';
  } finally {
    if (token === requestSequence) loading.value = false;
  }
}
async function submit() {
  if (!canShare.value || !props.orderId || !recipientId.value) return;
  submitting.value = true;
  submitError.value = '';
  try {
    const result = await shareMaterialOrder(props.orderId, recipientId.value);
    message.success(
      result.already_shared ? '该工单已分享给此投手' : '工单分享成功',
    );
    emit('update:open', false);
    emit('shared');
  } catch (value) {
    submitError.value =
      value instanceof Error ? value.message : '工单分享失败，请重试';
  } finally {
    submitting.value = false;
  }
}
watch(
  () => [props.open, props.orderId] as const,
  ([open]) => {
    if (open) void load();
    else {
      ++requestSequence;
      loading.value = false;
    }
  },
  { immediate: true },
);
</script>

<template>
  <Modal
    :open="open"
    title="分享工单"
    :width="520"
    ok-text="确认分享"
    cancel-text="取消"
    :confirm-loading="submitting"
    :ok-button-props="{ disabled: !canShare }"
    :cancel-button-props="{ disabled: submitting }"
    :closable="!submitting"
    :mask-closable="!submitting"
    :keyboard="!submitting"
    @ok="submit"
    @cancel="close"
  >
    <Spin :spinning="loading">
      <Alert v-if="error" :message="error" type="error" show-icon>
        <template #action><Button @click="load">重试</Button></template>
      </Alert>
      <div v-else class="space-y-4">
        <div>
          <p class="mb-1 font-medium">{{ detail?.title || '加载工单…' }}</p>
          <p class="text-muted-foreground">{{ detail?.order_no }}</p>
        </div>
        <Form layout="vertical">
          <FormItem label="分享给投手" required>
            <Select
              v-model:value="recipientId"
              class="w-full"
              :options="operatorOptions"
              :disabled="loading || submitting"
              show-search
              allow-clear
              option-filter-prop="label"
              placeholder="请选择投手"
              aria-label="分享给投手"
            />
          </FormItem>
        </Form>
        <p class="text-muted-foreground">
          投手可在“分享给我的”查看工单和交付素材。
        </p>
        <p v-if="sharedNames" class="text-muted-foreground">
          已分享给：{{ sharedNames }}
        </p>
        <Alert
          v-if="submitError"
          :message="submitError"
          type="error"
          show-icon
        />
      </div>
    </Spin>
  </Modal>
</template>
