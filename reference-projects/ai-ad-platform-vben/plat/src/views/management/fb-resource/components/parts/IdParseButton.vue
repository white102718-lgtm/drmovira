<script lang="ts" setup>
import { ref } from 'vue';

import { Button, Input, message, Popover } from 'ant-design-vue';

const props = withDefaults(
  defineProps<{
    label: string;
    placeholder?: string;
  }>(),
  {
    placeholder: '粘贴任意文本，自动提取 10 位以上纯数字 ID',
  },
);

const emit = defineEmits<{
  parsed: [ids: string[]];
}>();

const open = ref(false);
const text = ref('');

const apply = () => {
  const ids = [...new Set(text.value.match(/\d{10,}/g) ?? [])];
  if (ids.length === 0) {
    message.warning('未识别到有效 ID（需为 10 位以上纯数字）');
    return;
  }
  emit('parsed', ids);
  text.value = '';
  open.value = false;
};
</script>

<template>
  <Popover
    v-model:open="open"
    trigger="click"
    placement="bottomRight"
    :overlay-style="{ width: '360px' }"
  >
    <template #content>
      <div class="space-y-2">
        <Input.TextArea
          v-model:value="text"
          :rows="4"
          :placeholder="props.placeholder"
        />
        <div class="text-right">
          <Button type="primary" @click="apply">解析</Button>
        </div>
      </div>
    </template>
    <Button type="dashed">{{ props.label }}</Button>
  </Popover>
</template>
