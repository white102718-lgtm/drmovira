<script lang="ts" setup>
import { computed, ref } from 'vue';

import { Popover, TreeSelect } from 'ant-design-vue';

import { getTreeTags } from '#/api/tags/tree';
import Button from 'ant-design-vue/es/button';

import TagConfigSelect from './TagConfigSelect.vue';
import TagUserSelect from './TagUserSelect.vue';

interface TreeNode {
  [key: string]: any;

  checkable?: boolean;
  children?: TreeNode[];
  disabled?: boolean;
  label: string;
  value: string;
}

interface Props {
  allowClear?: boolean;
  disabled?: boolean;
  modelValue?: string[];
  placeholder?: string;
  style?: Record<string, any>;
  size?: 'small' | 'middle' | 'large';
}

interface Emits {
  (e: 'update:modelValue', value: string[] | undefined): void;
  (e: 'change', value: string[] | undefined): void;
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '选择标签',
  allowClear: true,
  disabled: false,
  size: 'middle',
});

const emit = defineEmits<Emits>();

// 内部状态
const popoverOpen = ref(false);
const selectedUser = ref<string | undefined>('ly');
const selectedConfigId = ref<string | undefined>('6979ec63006431b2350a2883');
const selectedConfigName = ref<string | undefined>();
const selectedTags = ref<string[]>([]);
const tagTreeData = ref<TreeNode[]>([]);
const tagTreeLoading = ref(false);

// 状态快照（用于取消操作）
const snapshot = ref<{
  configId?: string;
  configName?: string;
  tags: string[];
  user?: string;
}>({
  tags: [],
});

// 转换树数据为 TreeSelect 格式
const transformTreeData = (data: any[]): TreeNode[] => {
  const transformNode = (node: any): TreeNode => {
    const transformed: TreeNode = {
      checkable: true,
      label: node.title,
      value: node.key,
    };

    if (node.children && node.children.length > 0) {
      transformed.children = node.children.map((child: any) =>
        transformNode(child),
      );
    }

    return transformed;
  };

  return (data || []).map((node: any) => transformNode(node));
};

// 获取包含所有父节点的标签值列表
const getTagValuesWithParents = (selectedValues: string[] = []) => {
  if (selectedValues.length === 0 || !tagTreeData.value?.length) {
    return [];
  }

  const tagSet = new Set<string>();
  const parentMap = new Map<string, string | undefined>();

  // 构建父子关系映射
  const buildMaps = (nodes: TreeNode[], parentValue?: string) => {
    for (const node of nodes) {
      if (parentValue) {
        parentMap.set(node.value, parentValue);
      }

      if (node.children?.length) {
        buildMaps(node.children, node.value);
      }
    }
  };

  buildMaps(tagTreeData.value);

  // 收集路径上的所有节点
  const collectParentValues = (value: string) => {
    const path: string[] = [];
    let current: string | undefined = value;

    while (current) {
      path.unshift(current);
      current = parentMap.get(current);
    }

    return path;
  };

  for (const val of selectedValues) {
    const pathValues = collectParentValues(val);
    pathValues.forEach((v) => tagSet.add(v));
  }

  return [...tagSet];
};

// 加载标签树数据
const loadTagTreeData = async () => {
  if (!selectedUser.value) {
    tagTreeData.value = [];
    return;
  }

  try {
    tagTreeLoading.value = true;
    const data = await getTreeTags(selectedConfigId.value, selectedUser.value);
    tagTreeData.value = transformTreeData(data);
  } catch (error) {
    tagTreeData.value = [];
  } finally {
    tagTreeLoading.value = false;
  }
};

// 用户变化处理
const handleUserChange = (user: string | undefined) => {
  selectedUser.value = user;
  selectedConfigId.value = undefined;
  selectedConfigName.value = undefined;
  selectedTags.value = [];
  tagTreeData.value = [];

  loadTagTreeData();
};

// 配置变化处理
const handleConfigChange = (
  configId: string | undefined,
  configName: string | undefined,
) => {
  selectedConfigId.value = configId;
  selectedConfigName.value = configName;
  selectedTags.value = [];

  loadTagTreeData();
};

// 标签变化处理
const handleTagsChange = (tags: string[]) => {
  selectedTags.value = tags || [];
};

// 确定按钮处理
const handleConfirm = () => {
  // 获取包含父节点的完整标签路径
  const finalTags = getTagValuesWithParents(selectedTags.value);

  emit('update:modelValue', finalTags);
  emit('change', finalTags);

  popoverOpen.value = false;
};

// 取消按钮处理
const handleCancel = () => {
  // 恢复快照状态
  selectedUser.value = snapshot.value.user;
  selectedConfigId.value = snapshot.value.configId;
  selectedConfigName.value = snapshot.value.configName;
  selectedTags.value = [...snapshot.value.tags];

  popoverOpen.value = false;
};

// 是否已初始化加载
const initialized = ref(false);

// Popover 打开/关闭处理
const handlePopoverOpenChange = (open: boolean) => {
  popoverOpen.value = open;

  if (open) {
    // 首次打开时加载数据
    if (!initialized.value) {
      initialized.value = true;
      loadTagTreeData();
    }
    // 打开时保存快照
    snapshot.value = {
      user: selectedUser.value,
      configId: selectedConfigId.value,
      configName: selectedConfigName.value,
      tags: [...(selectedTags.value || [])],
    };
  }
};

// 清空选择
const handleClear = (e: Event) => {
  e.stopPropagation();

  // 只清空标签状态，保留用户和配置
  selectedTags.value = [];

  emit('update:modelValue', undefined);
  emit('change', undefined);
};

// 显示文本
const displayText = computed(() => {
  const count = props.modelValue?.length || 0;

  if (count === 0) {
    return props.placeholder || '选择标签';
  }

  return `已选 ${count} 个标签`;
});

// 是否显示清空按钮
const showClear = computed(() => {
  return (
    props.allowClear &&
    !props.disabled &&
    props.modelValue &&
    props.modelValue.length > 0
  );
});

// 是否可以确定（至少选择了一个标签）
const canConfirm = computed(() => {
  return selectedTags.value && selectedTags.value.length > 0;
});

// 组件初始化时加载标签树数据
</script>

<template>
  <Popover
    v-model:open="popoverOpen"
    trigger="click"
    placement="bottomLeft"
    :overlay-style="{ width: '500px' }"
    @open-change="handlePopoverOpenChange"
  >
    <template #content>
      <div class="tag-combo-panel">
        <!-- 用户选择 -->
        <div class="panel-row">
          <label class="panel-label">用户:</label>
          <TagUserSelect
            v-model="selectedUser"
            disabled
            :style="{ width: '100%' }"
            @change="handleUserChange"
          />
        </div>

        <!-- 配置选择 -->
        <div class="panel-row">
          <label class="panel-label">配置:</label>
          <TagConfigSelect
            v-model="selectedConfigId"
            :selected-user="selectedUser"
            :style="{ width: '100%' }"
            @change="handleConfigChange"
          />
        </div>

        <!-- 标签选择 -->
        <div class="panel-row">
          <label class="panel-label">标签:</label>
          <TreeSelect
            v-model:value="selectedTags"
            :tree-data="tagTreeData"
            :loading="tagTreeLoading"
            :disabled="!selectedUser"
            tree-checkable
            show-checked-strategy="SHOW_CHILD"
            tree-default-expand-all
            allow-clear
            show-search
            max-tag-count="responsive"
            tree-node-filter-prop="label"
            placeholder="请先选择用户和配置"
            :style="{ width: '100%' }"
            @change="handleTagsChange"
          />
        </div>

        <!-- 操作按钮 -->
        <div class="panel-actions">
          <Button @click="handleCancel">取消</Button>
          <Button type="primary" :disabled="!canConfirm" @click="handleConfirm">
            确定
          </Button>
        </div>
      </div>
    </template>

    <!-- Trigger Button -->
    <Button
      :disabled="disabled"
      :style="style"
      :size="size"
      class="tag-combo-trigger"
    >
      <span class="truncate">{{ displayText }}</span>
      <span
        v-if="showClear"
        class="icon-[ant-design--close-circle-outlined] ml-1 text-gray-400 hover:text-gray-600"
        @click.stop="handleClear"
      ></span>
      <span v-else class="icon-[ant-design--down-outlined] ml-1"></span>
    </Button>
  </Popover>
</template>

<style scoped>
.tag-combo-panel {
  min-width: 480px;
  padding: 12px;
}

.panel-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.panel-label {
  flex-shrink: 0;
  min-width: 50px;
  font-weight: 500;
  color: rgb(0 0 0 / 85%);
}

.panel-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding-top: 12px;
  margin-top: 16px;
  border-top: 1px solid #f0f0f0;
}

.tag-combo-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.tag-combo-trigger .truncate {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  white-space: nowrap;
}
</style>
