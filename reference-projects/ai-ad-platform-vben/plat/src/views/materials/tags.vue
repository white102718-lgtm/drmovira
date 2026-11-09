<script lang="ts" setup>
import { nextTick, onBeforeUpdate, onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';

import {
  Button,
  Card,
  Collapse,
  CollapsePanel,
  Input,
  message,
  RadioButton,
  RadioGroup,
  Tag,
} from 'ant-design-vue';

import {
  createInferenceTag,
  deleteInferenceTag,
  getAllFactTags,
  getAllInferenceTags,
  updateFactTag,
  updateInferenceTag,
} from '#/api/materials/all';

interface MyTag {
  name: string;
  tags: string[];
  title: string;
}

const activeKeys = ref<number[]>([]);
const lastEditInputValue = ref('');
const editInputValue = ref('');
const inputRefs = ref<Record<string, HTMLInputElement>>({});

const editTag = ref<string>('');
const editModeNames = ref<Set<string>>(new Set());
const getEditMode = (prefix: string, name: string) => {
  return `${prefix}-${name}`;
};
const isEditMode = (prefix: string, name: string) => {
  return editModeNames.value.has(getEditMode(prefix, name));
};
const factPrefix = ref<string>('fact-');
const inferencePrefix = ref<string>('inf-');
const getEditTagName = (prefix: string, name: string, index: number) => {
  return `${prefix}-${name}-${index}`;
};
const resetEditTag = () => {
  editTag.value = '';
};
const setEditTag = (prefix: string, name: string, index: number) => {
  editTag.value = getEditTagName(prefix, name, index);
};

const loading = ref(false);

const factTags = ref<Record<string, MyTag>>({});
const inferenceTags = ref<Record<string, MyTag>>({});
const initFactData = async () => {
  const factTagsData = await getAllFactTags();
  factTags.value = {};
  factTagsData.forEach((row: MyTag) => {
    factTags.value[row.name] = row ?? {};
  });
};
const initInfData = async () => {
  const inferenceTagsData = await getAllInferenceTags();
  inferenceTags.value = {};
  inferenceTagsData.forEach((row: MyTag) => {
    inferenceTags.value[row.name] = row ?? {};
  });
  // 默认展开折叠面板
  activeKeys.value = Array.from(
    { length: Object.keys(inferenceTags.value).length },
    (_, i) => i,
  );
};
const initData = async () => {
  loading.value = true;
  try {
    await Promise.all([initFactData(), initInfData()]);
  } catch {
    message.error('获取标签数据失败，请刷新页面重试');
  } finally {
    loading.value = false;
  }
};
// TODO修改时在标签为输入框时直接点击保存会导致数据未修改
const toggleEditMode = (
  prefix: string,
  name: string,
  action: 'cancel' | 'delete' | 'save',
) => {
  if (isEditMode(prefix, name)) {
    switch (action) {
      case 'cancel': {
        editModeNames.value.clear();
        initData();
        break;
      }
      case 'delete': {
        deleteInferenceTag(name)
          .then(() => {
            message.success('删除成功');
            initInfData();
          })
          .catch(() => message.error('删除失败'));
        break;
      }
      case 'save': {
        if (prefix === factPrefix.value && factTags.value[name]) {
          updateFactTag(factTags.value[name])
            .then(() => message.success('保存成功'))
            .catch(() => message.error('保存失败'));
        } else if (inferenceTags.value[name]) {
          updateInferenceTag(inferenceTags.value[name])
            .then(() => message.success('保存成功'))
            .catch(() => message.error('保存失败'));
        }
        break;
      }
    }
    // 无论哪种操作，都退出编辑模式
    editModeNames.value.delete(getEditMode(prefix, name));
  } else {
    editModeNames.value.add(getEditMode(prefix, name));
  }
};

const focusInput = (key: string) => {
  const inputEl = inputRefs.value[key];
  nextTick(() => {
    inputEl?.focus();
  });
};

const handleEdit = (
  name: string,
  prefix: string,
  index: number,
  value: string,
) => {
  if (isEditMode(prefix, name)) {
    setEditTag(prefix, name, index);
    editInputValue.value = value;
    lastEditInputValue.value = value;
    const refKey = getEditTagName(prefix, name, index);
    focusInput(refKey);
  }
};
const handleEditConfirm = (prefix: string, name: string, index: number) => {
  const tags =
    prefix === factPrefix.value ? factTags.value : inferenceTags.value;
  if (tags[name]?.tags) {
    if (editInputValue.value) {
      tags[name].tags[index] = editInputValue.value;
    } else if (lastEditInputValue.value) {
      tags[name].tags[index] = lastEditInputValue.value;
    } else {
      tags[name].tags.pop();
    }
  }
  resetEditTag();
};

const handleAdd = (name: string, prefix: string) => {
  if (isEditMode(prefix, name)) {
    const tags =
      prefix === factPrefix.value ? factTags.value : inferenceTags.value;
    if (tags[name]?.tags) {
      if (editTag.value) {
        handleEditConfirm(prefix, name, tags[name].tags.length - 1);
      }
      tags[name].tags.push('');
      const tmp = tags[name];
      nextTick(() => {
        handleEdit(name, prefix, tmp.tags.length - 1, '');
      });
    }
  }
};

const handleClose = (prefix: string, name: string, tag: string) => {
  const tags =
    prefix === factPrefix.value ? factTags.value : inferenceTags.value;
  if (tags[name]) {
    tags[name].tags = tags[name].tags.filter((item) => item !== tag) || [];
  }
  resetEditTag();
};

const setItemRef = (el: any | null, key: string) => {
  if (el) {
    inputRefs.value[key] = el;
  }
};
const newInfTagName = ref('');

// 添加创建新推理标签的函数
const createNewInferenceTag = async () => {
  if (!newInfTagName.value) {
    message.warning('请输入标签名称和标题');
    return;
  }
  try {
    await createInferenceTag(newInfTagName.value, newInfTagName.value);
    message.success('创建成功');
    await initInfData();
    newInfTagName.value = '';
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
    description="维护素材事实标签和推理标签，确保检索、推荐和报表使用统一口径。"
    title="素材标签管理"
  >
    <div class="grid gap-4 lg:grid-cols-2">
      <Card
        v-for="item in Object.values(factTags)"
        :key="item.name"
        :title="item.title"
      >
        <template #extra>
          <Button
            :danger="isEditMode(factPrefix, item.name)"
            @click.stop="toggleEditMode(factPrefix, item.name, 'save')"
          >
            {{ isEditMode(factPrefix, item.name) ? '保存修改' : '修改' }}
          </Button>
        </template>
        <div class="flex flex-wrap items-center gap-2">
          <template v-for="(tag, index) in item.tags" :key="index">
            <Tag
              v-show="
                !(getEditTagName(factPrefix, item.name, index) === editTag)
              "
              @click="handleEdit(item.name, factPrefix, index, tag)"
              :closable="isEditMode(factPrefix, item.name)"
              @close="handleClose(factPrefix, item.name, tag)"
              :style="
                isEditMode(factPrefix, item.name) ? { cursor: 'pointer' } : {}
              "
            >
              {{ tag }}
            </Tag>
            <Input
              v-show="getEditTagName(factPrefix, item.name, index) === editTag"
              :ref="
                (el) =>
                  setItemRef(el, getEditTagName(factPrefix, item.name, index))
              "
              v-model:value="editInputValue"
              class="!w-[140px]"
              type="text"
              size="small"
              @blur="handleEditConfirm(factPrefix, item.name, index)"
              @keyup.enter="handleEditConfirm(factPrefix, item.name, index)"
            />
          </template>
          <!--新增框-->
          <Tag
            v-if="isEditMode(factPrefix, item.name)"
            class="bg-card cursor-pointer border-dashed"
            @click="handleAdd(item.name, factPrefix)"
          >
            <span class="icon-[ant-design--plus-outlined]"></span>
            新增
          </Tag>
        </div>
      </Card>
    </div>

    <Card title="推理标签" class="mt-4">
      <template #extra>
        <div class="flex flex-wrap items-center gap-2">
          <Input
            v-model:value="newInfTagName"
            class="w-[220px] max-w-full"
            placeholder="输入新增名称"
          />
          <Button type="primary" @click="createNewInferenceTag"> 新增 </Button>
        </div>
      </template>
      <Collapse v-model:active-key="activeKeys" :bordered="false">
        <CollapsePanel
          v-for="(item, index) in Object.values(inferenceTags)"
          :key="index"
          :header="item.title"
        >
          <template #extra>
            <Button
              v-if="!isEditMode(inferencePrefix, item.name)"
              @click.stop="toggleEditMode(inferencePrefix, item.name, 'save')"
            >
              修改
            </Button>
            <div v-else>
              <Button
                danger
                @click.stop="
                  toggleEditMode(inferencePrefix, item.name, 'delete')
                "
              >
                删除
              </Button>
              <RadioGroup>
                <RadioButton
                  danger
                  @mousedown.stop="
                    toggleEditMode(inferencePrefix, item.name, 'save')
                  "
                >
                  保存
                </RadioButton>
                <RadioButton
                  danger
                  @mousedown.stop="
                    toggleEditMode(inferencePrefix, item.name, 'cancel')
                  "
                >
                  取消
                </RadioButton>
              </RadioGroup>
            </div>
          </template>
          <div class="flex flex-wrap items-center gap-2">
            <template v-for="(tag, i) in item.tags" :key="i">
              <!--标签框-->
              <Tag
                v-show="
                  !(getEditTagName(inferencePrefix, item.name, i) === editTag)
                "
                @click="handleEdit(item.name, inferencePrefix, i, tag)"
                :closable="isEditMode(inferencePrefix, item.name)"
                @close="handleClose(inferencePrefix, item.name, tag)"
                :style="
                  isEditMode(inferencePrefix, item.name)
                    ? { cursor: 'pointer' }
                    : {}
                "
              >
                {{ tag }}
              </Tag>
              <Input
                v-show="
                  getEditTagName(inferencePrefix, item.name, i) === editTag
                "
                :ref="
                  (el) =>
                    setItemRef(
                      el,
                      getEditTagName(inferencePrefix, item.name, i),
                    )
                "
                v-model:value="editInputValue"
                class="!w-[140px]"
                type="text"
                size="small"
                @blur="handleEditConfirm(inferencePrefix, item.name, i)"
                @keyup.enter="handleEditConfirm(inferencePrefix, item.name, i)"
              />
            </template>
            <!--新增框-->
            <Tag
              v-if="isEditMode(inferencePrefix, item.name)"
              class="bg-card cursor-pointer border-dashed"
              @click="handleAdd(item.name, inferencePrefix)"
            >
              <span class="icon-[ant-design--plus-outlined]"></span>
              新增
            </Tag>
          </div>
        </CollapsePanel>
      </Collapse>
    </Card>
  </Page>
</template>
