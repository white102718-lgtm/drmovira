<script lang="ts" setup>
import { nextTick, onBeforeUpdate, onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';

import {
  Button,
  Input,
  List,
  message,
  RadioButton,
  RadioGroup,
  Tag,
} from 'ant-design-vue';

import {
  createAttribution,
  deleteAttribution,
  getAllAttribution,
  updateAttribution,
} from '#/api/attribution/all';

interface MyOption {
  name: string;
  options: string[];
  title: string;
}

const activeKeys = ref<number[]>([]);
const lastEditInputValue = ref('');
const editInputValue = ref('');
const inputRefs = ref<Record<string, HTMLInputElement>>({});

const editOption = ref<string>('');
const editModeNames = ref<Set<string>>(new Set());
const isEditMode = (name: string) => {
  return editModeNames.value.has(name);
};
const getEditOptionName = (name: string, index: number) => {
  return `${name}-${index}`;
};
const resetEditOption = () => {
  editOption.value = '';
};
const setEditOption = (name: string, index: number) => {
  editOption.value = getEditOptionName(name, index);
};

const loading = ref(false);

const attributionOptions = ref<Record<string, MyOption>>({});
const initAttrData = async () => {
  const attributionOptionsData = await getAllAttribution();
  attributionOptions.value = {};
  attributionOptionsData.forEach((row: MyOption) => {
    attributionOptions.value[row.name] = row ?? {};
  });
  // 默认展开折叠面板
  activeKeys.value = Array.from(
    { length: Object.keys(attributionOptions.value).length },
    (_, i) => i,
  );
};
const initData = async () => {
  loading.value = true;
  try {
    await initAttrData();
  } catch {
    message.error('获取标签数据失败，请刷新页面重试');
  } finally {
    loading.value = false;
  }
};

const toggleEditMode = (
  name: string,
  action: 'cancel' | 'delete' | 'save' | 'update',
) => {
  if (isEditMode(name)) {
    switch (action) {
      case 'cancel': {
        editModeNames.value.clear();
        initData();
        break;
      }
      case 'delete': {
        deleteAttribution(name)
          .then(() => {
            message.success('删除成功');
            initAttrData();
          })
          .catch(() => message.error('删除失败'));
        break;
      }
      case 'save': {
        if (attributionOptions.value[name]) {
          updateAttribution(attributionOptions.value[name])
            .then(() => message.success('保存成功'))
            .catch(() => message.error('保存失败'));
        }
        break;
      }
    }
    // 无论哪种操作，都退出编辑模式
    editModeNames.value.delete(name);
  } else {
    editModeNames.value.add(name);
  }
};

const focusInput = (key: string) => {
  const inputEl = inputRefs.value[key];
  nextTick(() => {
    inputEl?.focus();
  });
};

const handleEdit = (name: string, index: number, value: string) => {
  if (isEditMode(name)) {
    setEditOption(name, index);
    editInputValue.value = value;
    lastEditInputValue.value = value;
    const refKey = getEditOptionName(name, index);
    focusInput(refKey);
  }
};
const handleEditConfirm = (name: string, index: number) => {
  const options = attributionOptions.value;
  if (options[name]?.options) {
    if (editInputValue.value) {
      options[name].options[index] = editInputValue.value;
    } else if (lastEditInputValue.value) {
      options[name].options[index] = lastEditInputValue.value;
    } else {
      options[name].options.pop();
    }
  }
  resetEditOption();
};

const handleAdd = (name: string) => {
  if (isEditMode(name)) {
    const options = attributionOptions.value;
    if (options[name]?.options) {
      if (editOption.value) {
        handleEditConfirm(name, options[name].options.length - 1);
      }
      options[name].options.push('');
      const tmp = options[name];
      nextTick(() => {
        handleEdit(name, tmp.options.length - 1, '');
      });
    }
  }
};

const handleClose = (name: string, option: string) => {
  if (attributionOptions.value[name]) {
    attributionOptions.value[name].options =
      attributionOptions.value[name].options.filter(
        (item) => item !== option,
      ) || [];
  }
  resetEditOption();
};

const setItemRef = (el: any | null, key: string) => {
  if (el) {
    inputRefs.value[key] = el;
  }
};
const newAttrOptionName = ref('');

// 添加创建新归因标签的函数
const createNewAttributionOption = async () => {
  if (!newAttrOptionName.value) {
    message.warning('请输入标签名称和标题');
    return;
  }
  try {
    await createAttribution(newAttrOptionName.value, newAttrOptionName.value);
    message.success('创建成功');
    await initAttrData();
    newAttrOptionName.value = '';
  } catch {
    message.error('创建失败');
  }
};
// 在更新前清空引用字典
onBeforeUpdate(() => {
  inputRefs.value = {};
});
// 初始化
onMounted(async () => {
  await initData();
});
</script>
<template>
  <Page
    auto-content-height
    description="维护投放归因标签及其可选值，统一报表与配置中的归因口径。"
    title="归因配置"
  >
    <List
      class="bg-card overflow-hidden rounded-xl border"
      :data-source="Object.values(attributionOptions)"
      :loading="loading"
    >
      <template #header>
        <div class="flex flex-wrap items-center gap-2">
          <Input
            v-model:value="newAttrOptionName"
            class="w-[220px] max-w-full"
            placeholder="输入新增名称"
          />
          <Button type="primary" @click="createNewAttributionOption">
            新增归因项
          </Button>
        </div>
      </template>
      <template #renderItem="{ item }">
        <List.Item class="!items-start gap-4">
          <div class="min-w-0 flex-1">
            <h3 class="text-foreground mb-2 text-sm font-semibold">
              {{ item.title }}
            </h3>
            <div class="flex flex-wrap items-center gap-2">
              <template v-for="(option, i) in item.options" :key="i">
                <Tag
                  v-show="!(getEditOptionName(item.name, i) === editOption)"
                  :closable="isEditMode(item.name)"
                  :style="isEditMode(item.name) ? { cursor: 'pointer' } : {}"
                  @click="handleEdit(item.name, i, option)"
                  @close="handleClose(item.name, option)"
                >
                  {{ option }}
                </Tag>
                <Input
                  v-show="getEditOptionName(item.name, i) === editOption"
                  :ref="(el) => setItemRef(el, getEditOptionName(item.name, i))"
                  v-model:value="editInputValue"
                  class="!w-[140px]"
                  size="small"
                  type="text"
                  @blur="handleEditConfirm(item.name, i)"
                  @keyup.enter="handleEditConfirm(item.name, i)"
                />
              </template>
              <Tag
                v-if="isEditMode(item.name)"
                class="bg-card cursor-pointer border-dashed"
                @click="handleAdd(item.name)"
              >
                <span class="icon-[ant-design--plus-outlined]"></span>
                新增
              </Tag>
            </div>
          </div>
          <Button
            v-if="!isEditMode(item.name)"
            @click.stop="toggleEditMode(item.name, 'update')"
          >
            修改
          </Button>
          <div v-else class="flex flex-wrap items-center gap-2">
            <Button danger @click.stop="toggleEditMode(item.name, 'delete')">
              删除
            </Button>
            <RadioGroup>
              <RadioButton @mousedown.stop="toggleEditMode(item.name, 'save')">
                保存
              </RadioButton>
              <RadioButton
                @mousedown.stop="toggleEditMode(item.name, 'cancel')"
              >
                取消
              </RadioButton>
            </RadioGroup>
          </div>
        </List.Item>
      </template>
    </List>
  </Page>
</template>
