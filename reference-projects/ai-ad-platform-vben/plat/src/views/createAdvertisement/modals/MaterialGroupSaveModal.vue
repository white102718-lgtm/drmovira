<script lang="ts" setup>
import { computed, reactive, ref, watch } from 'vue';

import { Button, Input, message, Modal } from 'ant-design-vue';

const props = defineProps<{
  currentGroupDescription?: string;
  currentGroupId?: string; // 当前素材组ID（用于显示来源和更新）
  currentGroupName?: string; // 当前素材组名称
  materialsCount: number;
  visible: boolean;
}>();

const emit = defineEmits<{
  cancel: [];
  confirm: [
    data: { description: string; name: string },
    action: 'create' | 'update',
  ];
}>();

// 表单数据
const formData = reactive({
  name: '',
  description: '',
});

// 加载状态
const saving = ref(false);

// 是否有来源素材组（用于显示更新选项）
const hasSourceGroup = computed(() => !!props.currentGroupId);

// 弹窗标题
const modalTitle = computed(() =>
  hasSourceGroup.value ? '保存素材组' : '保存素材组',
);

// 验证表单
function validateForm() {
  if (!formData.name.trim()) {
    message.warning('请输入素材组名称');
    return false;
  }

  if (formData.name.length > 100) {
    message.warning('素材组名称不能超过100个字符');
    return false;
  }

  if (formData.description.length > 500) {
    message.warning('素材组描述不能超过500个字符');
    return false;
  }

  if (props.materialsCount === 0) {
    message.warning('当前没有素材，无法保存素材组');
    return false;
  }

  return true;
}

// 更新素材组
async function handleUpdate() {
  if (!validateForm()) return;

  const data = {
    name: formData.name.trim(),
    description: formData.description.trim(),
  };

  emit('confirm', data, 'update');
}

// 另存为新素材组
async function handleSaveAs() {
  if (!validateForm()) return;

  const data = {
    name: formData.name.trim(),
    description: formData.description.trim(),
  };

  emit('confirm', data, 'create');
}

// 取消
function handleCancel() {
  emit('cancel');
}

// 重置表单
function resetForm() {
  formData.name = '';
  formData.description = '';
}

// 监听弹窗显示状态
watch(
  () => props.visible,
  (val) => {
    if (val) {
      // 打开弹窗时，如果有来源素材组，填充初始数据
      if (hasSourceGroup.value) {
        formData.name = props.currentGroupName || '';
        formData.description = props.currentGroupDescription || '';
      } else {
        resetForm();
      }
    }
  },
);
</script>

<template>
  <Modal
    :open="visible"
    :title="modalTitle"
    :confirm-loading="saving"
    width="600px"
    @cancel="handleCancel"
  >
    <div class="space-y-4 py-4">
      <!-- 来源信息 -->
      <div v-if="hasSourceGroup" class="rounded-lg bg-blue-50 p-3">
        <div class="mb-1 flex items-center gap-2">
          <span
            class="icon-[ant-design--info-circle-outlined] text-blue-500"
          ></span>
          <span class="text-sm font-medium text-gray-700">来源素材组</span>
        </div>
        <div class="ml-6 text-sm text-gray-600">
          {{ currentGroupName }}
        </div>
      </div>

      <!-- 素材组名称 -->
      <div class="flex items-start gap-3">
        <label class="w-20 pt-1 text-right text-sm text-gray-700">
          <span class="text-red-500">*</span> 名称:
        </label>
        <div class="flex-1">
          <Input
            v-model:value="formData.name"
            placeholder="请输入素材组名称（1-100字符）"
            :maxlength="100"
            show-count
          />
        </div>
      </div>

      <!-- 素材组描述 -->
      <div class="flex items-start gap-3">
        <label class="w-20 pt-1 text-right text-sm text-gray-700">
          描述:
        </label>
        <div class="flex-1">
          <Input.TextArea
            v-model:value="formData.description"
            placeholder="请输入素材组描述（最多500字符）"
            :maxlength="500"
            :rows="3"
            show-count
          />
        </div>
      </div>

      <!-- 素材数量提示 -->
      <div class="flex items-start gap-3">
        <label class="w-20 pt-1 text-right text-sm text-gray-700">
          素材数量:
        </label>
        <div class="flex-1">
          <div class="text-sm">
            <span class="font-semibold text-blue-600">{{
              materialsCount
            }}</span>
            <span class="ml-1 text-gray-600">个素材</span>
          </div>
          <div class="mt-1 text-xs text-gray-500">
            将保存当前所有素材及其配置（标题、正文、行动号召）
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <Button @click="handleCancel">取消</Button>

        <!-- 有来源素材组：显示另存为按钮 -->
        <Button
          v-if="hasSourceGroup"
          :loading="saving"
          :disabled="!formData.name.trim() || materialsCount === 0"
          @click="handleSaveAs"
        >
          <span class="icon-[ant-design--file-add-outlined] mr-1"></span>
          另存为
        </Button>

        <!-- 有来源素材组：显示更新按钮 -->
        <Button
          v-if="hasSourceGroup"
          type="primary"
          :loading="saving"
          :disabled="!formData.name.trim() || materialsCount === 0"
          @click="handleUpdate"
        >
          <span class="icon-[ant-design--save-outlined] mr-1"></span>
          更新
        </Button>

        <!-- 无来源素材组：只显示保存按钮 -->
        <Button
          v-if="!hasSourceGroup"
          type="primary"
          :loading="saving"
          :disabled="!formData.name.trim() || materialsCount === 0"
          @click="handleSaveAs"
        >
          <span class="icon-[ant-design--save-outlined] mr-1"></span>
          保存
        </Button>
      </div>
    </template>
  </Modal>
</template>

<style lang="scss" scoped>
/* 样式*/
</style>
