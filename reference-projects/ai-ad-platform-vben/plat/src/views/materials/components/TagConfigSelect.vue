<script lang="ts" setup>
import type { TagConfig } from '#/api/tags/tree';

import { computed, ref, watch } from 'vue';

import { message, Popconfirm, Popover } from 'ant-design-vue';

import {
  createTagConfig,
  deleteTagConfig,
  getTagConfigOptions,
  updateTagConfig,
} from '#/api/tags/tree';
import { Button, Input } from 'ant-design-vue';

interface Props {
  disabled?: boolean;
  modelValue?: string | undefined;
  placeholder?: string;
  selectedUser?: string | undefined;
  style?: Record<string, any>;
}

interface Emits {
  (
    e: 'change',
    value: string | undefined,
    configName: string | undefined,
  ): void;
  (e: 'update:modelValue', value: string | undefined): void;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '选择配置',
  disabled: false,
});

const emit = defineEmits<Emits>();

const configOptions = ref<TagConfig[]>([]);
const configLoading = ref(false);
const configPopoverOpen = ref(false);
const newConfigName = ref('');
const editingConfigId = ref<null | string>(null);
const editConfigName = ref('');

// 当前选中的配置名称（用于显示）
const selectedConfigName = computed(() => {
  if (!props.modelValue) return undefined;
  return configOptions.value.find((c) => c.id === props.modelValue)?.name;
});

// 加载配置选项
const loadConfigOptions = async () => {
  try {
    configLoading.value = true;
    const response = await getTagConfigOptions(props.selectedUser);
    if (Array.isArray(response)) {
      configOptions.value = response;
    }
  } catch (error) {
  } finally {
    configLoading.value = false;
  }
};

// 选择配置
const selectConfig = (config: TagConfig) => {
  emit('update:modelValue', config.id);
  emit('change', config.id, config.name);
  configPopoverOpen.value = false;
};

// 清除配置选择
const clearConfigSelection = () => {
  emit('update:modelValue', undefined);
  emit('change', undefined, undefined);
  configPopoverOpen.value = false;
};

// 添加配置
const handleAddConfig = async () => {
  if (!props.selectedUser) {
    message.warning('请先选择用户');
    return;
  }

  const name = newConfigName.value.trim();
  if (!name) {
    message.warning('请输入配置名称');
    return;
  }

  if (configOptions.value.some((c) => c.name === name)) {
    message.warning('该配置名称已存在');
    return;
  }

  try {
    configLoading.value = true;
    const newConfig = await createTagConfig(name, props.selectedUser);
    configOptions.value = [...configOptions.value, newConfig];
    newConfigName.value = '';
    message.success('配置添加成功');
  } catch {
    message.error('添加配置失败');
  } finally {
    configLoading.value = false;
  }
};

// 开始编辑配置
const startEditConfig = (config: TagConfig) => {
  editingConfigId.value = config.id;
  editConfigName.value = config.name;
};

// 保存编辑配置
const saveEditConfig = async () => {
  const name = editConfigName.value.trim();
  if (!name || !editingConfigId.value) {
    cancelEditConfig();
    return;
  }

  if (
    configOptions.value.some(
      (c) => c.name === name && c.id !== editingConfigId.value,
    )
  ) {
    message.warning('该配置名称已存在');
    return;
  }

  try {
    configLoading.value = true;
    await updateTagConfig(editingConfigId.value, name);
    const index = configOptions.value.findIndex(
      (c) => c.id === editingConfigId.value,
    );
    if (index !== -1) {
      configOptions.value[index] = { ...configOptions.value[index], name };
    }
    message.success('配置更新成功');
    cancelEditConfig();

    // 如果修改的是当前选中的配置，触发 change 事件更新名称
    if (props.modelValue === editingConfigId.value) {
      emit('change', props.modelValue, name);
    }
  } catch {
    message.error('更新配置失败');
  } finally {
    configLoading.value = false;
  }
};

// 取消编辑配置
const cancelEditConfig = () => {
  editingConfigId.value = null;
  editConfigName.value = '';
};

// 删除配置
const handleDeleteConfig = async (config: TagConfig) => {
  try {
    configLoading.value = true;
    await deleteTagConfig(config.id);
    configOptions.value = configOptions.value.filter((c) => c.id !== config.id);

    // 如果删除的是当前选中的配置，清空选择
    if (props.modelValue === config.id) {
      clearConfigSelection();
    }

    message.success('配置删除成功');
  } catch {
    message.error('删除配置失败');
  } finally {
    configLoading.value = false;
  }
};

// 监听用户变化，重新加载配置列表
watch(
  () => props.selectedUser,
  () => {
    loadConfigOptions();
  },
  { immediate: true },
);
</script>

<template>
  <Popover
    v-if="!disabled"
    v-model:open="configPopoverOpen"
    trigger="click"
    placement="bottomLeft"
  >
    <template #content>
      <div class="w-64">
        <!-- 配置列表 -->
        <div class="max-h-60 overflow-y-auto">
          <div
            v-for="config in configOptions"
            :key="config.id"
            class="group flex items-center justify-between rounded px-2 py-1.5 hover:bg-gray-100"
            :class="{
              'bg-blue-50': modelValue === config.id,
            }"
          >
            <template v-if="editingConfigId === config.id">
              <Input
                v-model:value="editConfigName"
                class="mr-1 flex-1"
                @press-enter="saveEditConfig"
              />
              <Button
                type="text"
                class="!w-6 !min-w-0 !p-0 text-green-500"
                @click="saveEditConfig"
              >
                <span class="icon-[ant-design--check-outlined] text-sm"></span>
              </Button>
              <Button
                type="text"
                class="!w-6 !min-w-0 !p-0"
                @click="cancelEditConfig"
              >
                <span class="icon-[ant-design--close-outlined] text-sm"></span>
              </Button>
            </template>
            <template v-else>
              <span
                class="flex-1 cursor-pointer truncate"
                @click="selectConfig(config)"
              >
                {{ config.name }}
              </span>
              <div
                class="ml-1 flex items-center opacity-0 group-hover:opacity-100"
              >
                <Button
                  type="text"
                  class="!w-6 !min-w-0 !p-0"
                  @click="startEditConfig(config)"
                >
                  <span class="icon-[ant-design--edit-outlined] text-sm"></span>
                </Button>
                <Popconfirm
                  :title="`确定删除「${config.name}」？`"
                  ok-text="确定"
                  cancel-text="取消"
                  @confirm="handleDeleteConfig(config)"
                >
                  <Button type="text" danger class="!w-6 !min-w-0 !p-0">
                    <span
                      class="icon-[ant-design--delete-outlined] text-sm"
                    ></span>
                  </Button>
                </Popconfirm>
              </div>
            </template>
          </div>
          <div
            v-if="configOptions.length === 0"
            class="py-4 text-center text-gray-400"
          >
            暂无配置
          </div>
        </div>
        <!-- 添加新配置 -->
        <div class="mt-2 flex items-center gap-1 border-t pt-2">
          <Input
            v-model:value="newConfigName"
            placeholder="新配置名称"
            class="flex-1"
            @press-enter="handleAddConfig"
          />
          <Button
            type="primary"
            :loading="configLoading"
            @click="handleAddConfig"
          >
            添加
          </Button>
        </div>
      </div>
    </template>
    <Button
      :loading="configLoading"
      :disabled="disabled"
      class="flex max-w-32 items-center gap-1"
    >
      <span class="truncate">{{ selectedConfigName || placeholder }}</span>
      <span
        v-if="modelValue && !configLoading && !disabled"
        class="icon-[ant-design--close-circle-outlined] text-gray-400 hover:text-gray-600"
        @click.stop="clearConfigSelection"
      ></span>
      <span
        v-else-if="!configLoading && !disabled"
        class="icon-[ant-design--down-outlined]"
      ></span>
    </Button>
  </Popover>
  <Button
    v-else
    :loading="configLoading"
    disabled
    class="flex max-w-32 items-center gap-1"
  >
    <span class="truncate">{{ selectedConfigName || placeholder }}</span>
  </Button>
</template>
