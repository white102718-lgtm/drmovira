<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { Button, Select } from 'ant-design-vue';
import type { DeliveryAgencyLineOption } from '#/api/task-center';
import { searchDeliveryAgencyLinesApi } from '#/api/task-center';

const props = defineProps<{ value?: string; name?: string }>();
defineOptions({ inheritAttrs: false });
const emit = defineEmits<{
  change: [value: DeliveryAgencyLineOption | undefined];
}>();
const rows = ref<DeliveryAgencyLineOption[]>([]);
const loading = ref(false);
const error = ref('');
const keyword = ref('');
const page = ref(0);
const hasMore = ref(true);
let sequence = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
// 已选值可能不在当前搜索页，保留名称避免退化为裸 ID。
const options = computed(() => {
  const values = new Map(rows.value.map((row) => [row.id, row]));
  if (props.value && props.name && !values.has(props.value))
    values.set(props.value, {
      cloakUrl: '',
      deliveryUrl: '',
      id: props.value,
      name: props.name,
      optimizerId: '',
      optimizerName: '',
      pixelId: '',
      pixelName: '',
      testCode: '',
      token: '',
      type: '',
    });
  return [...values.values()].map((row) => ({
    value: row.id,
    label: row.name,
    name: row.name,
    source: row,
  }));
});

async function load(reset = false) {
  if (!reset && (loading.value || !hasMore.value)) return;
  const request = ++sequence;
  const nextPage = reset ? 1 : page.value + 1;
  loading.value = true;
  error.value = '';
  try {
    const result = await searchDeliveryAgencyLinesApi(keyword.value, nextPage);
    if (request !== sequence) return;
    rows.value = reset ? result : [...rows.value, ...result];
    page.value = nextPage;
    hasMore.value = result.length === 30;
  } catch {
    if (request === sequence) error.value = '代理线加载失败，请重试';
  } finally {
    if (request === sequence) loading.value = false;
  }
}

/** 输入即使旧请求失效，防止较慢响应覆盖新关键词的结果。 */
function search(value: string) {
  keyword.value = value;
  error.value = '';
  sequence++;
  clearTimeout(timer);
  rows.value = [];
  page.value = 0;
  hasMore.value = true;
  loading.value = true;
  timer = setTimeout(() => void load(true), 300);
}
function open(visible: boolean) {
  if (visible && page.value === 0 && !loading.value) void load(true);
}
function scroll(event: Event) {
  const element = event.target as HTMLElement;
  if (element.scrollHeight - element.scrollTop - element.clientHeight < 40)
    void load();
}
function change(value: unknown) {
  const selected = options.value.find((row) => row.value === value);
  emit('change', selected?.source);
}
onBeforeUnmount(() => {
  clearTimeout(timer);
  sequence++;
});
</script>

<template>
  <Select
    v-bind="$attrs"
    :value="value"
    :options="options"
    :loading="loading"
    :filter-option="false"
    show-search
    allow-clear
    class="w-full"
    placeholder="选择代理线，输入名称搜索"
    @search="search"
    @change="change"
    @dropdown-visible-change="open"
    @popup-scroll="scroll"
  >
    <template #notFoundContent>{{
      loading ? '搜索中…' : error || '未找到代理线'
    }}</template>
  </Select>
  <div v-if="error" role="alert" class="text-destructive mt-1 text-sm">
    {{ error }}<Button @click="load(page === 0)">重试</Button>
  </div>
</template>
