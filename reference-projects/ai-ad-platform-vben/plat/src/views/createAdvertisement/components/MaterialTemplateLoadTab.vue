<script lang="ts" setup>
import { ref, watch } from 'vue';
import {
  Button,
  message,
  Modal,
  Popover,
  Select,
  Tooltip,
} from 'ant-design-vue';

import { useUserStore } from '@vben/stores';
import {
  deleteMaterialTemplate,
  getMaterialTemplateList,
} from '#/api/advertisement';

const emit = defineEmits<{
  apply: [templateData: any];
  open: [];
}>();

const props = defineProps<{
  userOptions?: Array<{ label: string; value: string }>;
}>();

const userStore = useUserStore();

const popoverVisible = ref(false);

// 用户选择状态
const selectedUser = ref<string | undefined>(undefined);
const userOptions = ref<Array<{ label: string; value: string }>>([]);

// 模板列表状态
const templateList = ref<any[]>([]);
const selectedTemplate = ref<string | undefined>(undefined);
const loadingTemplates = ref(false);
const deletingTemplate = ref(false);

// Select 搜索过滤函数
const filterSelectOption = (input: string, option: any) => {
  const text = option.label || '';
  return text.toLowerCase().includes(input.toLowerCase());
};

const filterUserOption = (input: string, option?: { label?: string }) => {
  const label = option?.label || '';
  return label.toLowerCase().includes(input.toLowerCase());
};

// 加载模板列表
async function loadTemplateList() {
  try {
    loadingTemplates.value = true;
    const params = selectedUser.value
      ? { real_name: selectedUser.value }
      : undefined;
    const res: any = await getMaterialTemplateList(params);

    if (Array.isArray(res)) {
      templateList.value = res;
    } else {
      templateList.value = [];
    }
  } catch (error: any) {
  } finally {
    loadingTemplates.value = false;
  }
}

async function refresh() {
  // 避免用户列表还没加载时，模板列表拉取参数不一致
  await loadTemplateList();
}

defineExpose({
  refresh,
});

// 用户变化时重新加载模板
function onUserChange(value: any) {
  selectedUser.value = value as string | undefined;
  selectedTemplate.value = undefined;
  loadTemplateList();
}

// 应用模板
function handleApplyTemplate() {
  if (!selectedUser.value) {
    message.warning('请先选择用户');
    return;
  }

  if (!selectedTemplate.value) {
    message.warning('请先选择要应用的模板');
    return;
  }

  // 直接从模板列表中找到选中的模板
  const template = templateList.value.find(
    (t) => t.id === selectedTemplate.value,
  );

  if (!template) {
    message.error('未找到选中的模板');
    return;
  }

  emit('apply', template);
  popoverVisible.value = false;
}

// 取消操作
function handleCancel() {
  popoverVisible.value = false;
}

// 删除模板
function handleDeleteTemplate(templateId: string, event?: Event) {
  if (event) {
    event.stopPropagation();
  }

  Modal.confirm({
    title: '确认删除',
    content: '确定要删除该模板吗？此操作不可恢复。',
    okText: '确认',
    cancelText: '取消',
    okType: 'danger',
    onOk: async () => {
      try {
        deletingTemplate.value = true;
        await deleteMaterialTemplate(templateId);

        templateList.value = templateList.value.filter(
          (t) => t.id !== templateId,
        );

        if (selectedTemplate.value === templateId) {
          selectedTemplate.value = undefined;
        }

        message.success('模板删除成功');
      } catch (error: any) {
      } finally {
        deletingTemplate.value = false;
      }
    },
  });
}

watch(
  () => props.userOptions,
  (val) => {
    userOptions.value = Array.isArray(val) ? val : [];
  },
  { immediate: true, deep: true },
);

watch(popoverVisible, async (val) => {
  if (val) {
    emit('open');
    if (!selectedUser.value) {
      const currentUser = userStore.userInfo?.realName;
      if (currentUser) {
        selectedUser.value = currentUser;
      }
    }
    await loadTemplateList();
  }
});
</script>

<template>
  <div class="material-template-load-tab">
    <Popover
      v-model:open="popoverVisible"
      trigger="click"
      placement="bottomLeft"
      overlay-class-name="material-template-load-popover"
      :overlay-style="{ zIndex: 999 }"
    >
      <template #content>
        <div class="w-[400px] p-2">
          <div class="mb-4 flex items-center gap-3 px-[20px]">
            <span class="w-10 text-sm text-gray-700">用户:</span>
            <Select
              v-model:value="selectedUser"
              :options="userOptions"
              show-search
              :filter-option="filterUserOption"
              placeholder="请选择用户"
              style="width: 300px"
              allow-clear
              @change="onUserChange"
            />
          </div>

          <div class="mb-4 flex items-center gap-3 px-[20px]">
            <span class="w-10 text-sm text-gray-700">模板:</span>
            <Select
              v-model:value="selectedTemplate"
              placeholder="请先选择模板"
              style="width: 300px"
              :loading="loadingTemplates"
              allow-clear
              show-search
              :filter-option="filterSelectOption"
              option-label-prop="label"
            >
              <Select.Option
                v-for="template in templateList"
                :key="template.id"
                :value="template.id"
                :label="template.name"
              >
                <div class="flex items-center justify-between">
                  <div class="flex flex-1 flex-col">
                    <div class="font-medium text-gray-800">
                      {{ template.name }}
                    </div>
                    <div class="text-xs text-gray-500">
                      {{ template.description || '暂无描述' }}
                    </div>
                  </div>
                  <span
                    class="icon-[ant-design--delete-outlined] ml-2 cursor-pointer text-red-500 hover:text-red-600"
                    @click="handleDeleteTemplate(template.id, $event)"
                  ></span>
                </div>
              </Select.Option>
            </Select>
          </div>

          <div
            class="flex items-center justify-end gap-2 border-t border-gray-200 pt-3"
          >
            <Button @click="handleCancel">取消</Button>
            <Button
              type="primary"
              :disabled="!selectedTemplate"
              @click="handleApplyTemplate"
            >
              确定
            </Button>
          </div>
        </div>
      </template>

      <Tooltip title="导入已保存的广告正文和标题模板">
        <Button type="primary" class="rounded-md">
          <span class="icon-[ant-design--import-outlined] mr-1"></span>
          导入模板
        </Button>
      </Tooltip>
    </Popover>
  </div>
</template>

<style lang="scss" scoped>
.material-template-load-tab {
  display: inline-block;
}
</style>

<style lang="scss">
.material-template-load-popover {
}
</style>
