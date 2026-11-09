<script lang="ts" setup>
import { computed, ref, watch } from 'vue';
import { Button, Input, Modal, message, Textarea } from 'ant-design-vue';

interface Props {
  open: boolean;
  initialName?: string;
  initialDescription?: string;
  title?: string;
}

interface Emits {
  (e: 'update:open', value: boolean): void;
  (e: 'confirm', templateName: string, description: string): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

const templateName = ref('');
const templateDescription = ref('');

const modalOpen = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value),
});

// 打开弹窗时回填
watch(
  () => props.open,
  (open) => {
    if (open) {
      templateName.value = props.initialName ?? '';
      templateDescription.value = props.initialDescription ?? '';
    }
  },
  { immediate: true },
);

function handleConfirm() {
  if (!templateName.value.trim()) {
    message.warning('请输入模版名称');
    return;
  }
  emit('confirm', templateName.value, templateDescription.value);
  handleCancel();
}

function handleCancel() {
  modalOpen.value = false;
  templateName.value = '';
  templateDescription.value = '';
}
</script>

<template>
  <Modal
    v-model:open="modalOpen"
    :title="props.title ?? '保存模板'"
    width="400px"
    @ok="handleConfirm"
  >
    <div class="space-y-4 py-4">
      <div class="flex items-center gap-4">
        <span class="shrink-0 text-sm text-gray-700">名称：</span>
        <Input
          class="ml-2 flex-1"
          v-model:value="templateName"
          placeholder="请输入模版名称"
        />
      </div>
      <div class="flex items-start gap-4">
        <span class="shrink-0 pt-2 text-sm text-gray-700">描述：</span>
        <Textarea
          class="ml-2 flex-1"
          v-model:value="templateDescription"
          placeholder="请输入模版描述"
          :rows="4"
        />
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-3">
        <Button class="rounded-md" @click="handleCancel">取消</Button>
        <Button type="primary" class="rounded-md" @click="handleConfirm">
          确认
        </Button>
      </div>
    </template>
  </Modal>
</template>
