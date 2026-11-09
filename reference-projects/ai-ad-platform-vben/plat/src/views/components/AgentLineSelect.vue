<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue';

import { TreeSelect } from 'ant-design-vue';

import { getAgentOptions } from '#/api/management/platform-config';

interface Props {
  /** 是否允许清空 */
  allowClear?: boolean;
  /** 是否禁用 */
  disabled?: boolean;
  /** 最多显示多少个标签，'responsive' 自适应 | 不传则显示全部 */
  maxTagCount?: 'responsive';
  /** 当前选中的值 */
  modelValue?: string | string[] | undefined;
  /** 是否多选 */
  multiple?: boolean;
  /** 占位符文本 */
  placeholder?: string;
  /** 项目名称（用于筛选代理线；底层仍兼容 game_platform 字段） */
  platform?: string;
  /** 是否可搜索 */
  showSearch?: boolean;
  /** 自定义样式 */
  style?: Record<string, any>;
  /** 兼容旧的value prop */
  value?: string | string[] | undefined;
  /** 容器总宽度 */
  width?: number | string;
}

interface Emits {
  (e: 'update:modelValue', value: string | string[] | undefined): void;
  (e: 'update:value', value: string | string[] | undefined): void;
  (e: 'change', value: string | string[] | undefined, platform?: string): void;
}

const props = withDefaults(defineProps<Props>(), {
  multiple: false,
  showSearch: true,
  allowClear: true,
  placeholder: '请选择代理线',
  disabled: false,
  maxTagCount: undefined,
  modelValue: undefined,
  platform: undefined,
  style: undefined,
  value: undefined,
  width: undefined,
});

const emit = defineEmits<Emits>();

const loading = ref(false);
const platformAgentData = ref<
  Array<{ agent_lines: string[]; game_platform: string; _id?: string }>
>([]);

// 缓存：平台名称到平台数据的映射，用于快速查找
const platformMap = computed(() => {
  const map = new Map<
    string,
    { agent_lines: string[]; platformIndex: number }
  >();
  platformAgentData.value.forEach((item, index) => {
    map.set(item.game_platform, {
      agent_lines: item.agent_lines,
      platformIndex: index,
    });
  });
  return map;
});

// 缓存：代理线到平台的映射，用于快速查找
const agentLineToPlatformMap = computed(() => {
  const map = new Map<string, string>();
  platformAgentData.value.forEach((item) => {
    item.agent_lines.forEach((line) => {
      map.set(line, item.game_platform);
    });
  });
  return map;
});

// 构建树形结构数据
const treeData = computed(() => {
  return platformAgentData.value.map((item, platformIndex) => ({
    title: item.game_platform,
    value: `platform_${platformIndex}_${item.game_platform}`,
    key: `platform_${platformIndex}_${item.game_platform}`,
    disabled: !props.multiple, // 多选时项目名称可选择，单选时不可选择
    children: item.agent_lines.map((agentLine) => ({
      title: agentLine,
      value: agentLine,
      key: agentLine,
      disabled: false, // 代理线可选择
    })),
  }));
});

// 内部值状态，用于处理异步数据加载
const internalValue = ref<string | string[] | undefined>(
  props.modelValue || props.value,
);

// 确保数据加载完成后才使用value
const computedValue = computed(() => {
  // 如果还在加载中，返回undefined
  if (loading.value) {
    return undefined;
  }

  // 多选模式下，检查是否有完整的平台被选中
  // 如果某个平台下的所有代理线都被选中，则在显示时也勾选父级
  if (props.multiple && Array.isArray(internalValue.value)) {
    const selectedLines = new Set(internalValue.value);
    const displayValues = [...internalValue.value];

    // 检查每个平台，使用 Set 进行 O(1) 查找
    platformAgentData.value.forEach((item, platformIndex) => {
      if (item.agent_lines.length > 0) {
        const allSelected = item.agent_lines.every((line) =>
          selectedLines.has(line),
        );
        if (allSelected) {
          // 如果该平台的所有代理线都被选中，添加平台节点到显示值中
          const platformValue = `platform_${platformIndex}_${item.game_platform}`;
          displayValues.push(platformValue);
        }
      }
    });

    return displayValues;
  }

  // 数据加载完成后，使用内部值
  return internalValue.value;
});

const loadOptions = async () => {
  try {
    loading.value = true;

    const response = await getAgentOptions(props.platform);

    if (Array.isArray(response)) {
      platformAgentData.value = response.map((item: any) => ({
        ...item,
        game_platform: item._id || item.game_platform,
      }));
    }
  } catch (error) {
  } finally {
    loading.value = false;
  }
};

// 根据渠道号查找对应的项目名称 - 使用 Map 进行 O(1) 查找
const findPlatformByAgentLine = (agentLine: string): string | undefined => {
  return agentLineToPlatformMap.value.get(agentLine);
};

const handleChange = (value: string | string[] | undefined) => {
  let processedValue = value;

  // 如果是多选模式，需要将父级节点转换为子级节点
  if (props.multiple && Array.isArray(value)) {
    const addedAgentLines = new Set<string>();

    for (const selectedValue of value) {
      // 判断是否是平台节点（以 platform_ 开头）
      if (selectedValue.startsWith('platform_')) {
        // 找到对应的平台数据，将所有子级代理线添加到结果中
        const platformMatch = selectedValue.match(/platform_\d+_(.+)/);
        if (platformMatch) {
          const platformName = platformMatch[1];
          const platformData = platformMap.value.get(platformName);
          if (platformData) {
            // 直接添加到 Set 中，自动去重
            platformData.agent_lines.forEach((agentLine) => {
              addedAgentLines.add(agentLine);
            });
          }
        }
      } else {
        // 直接是代理线，添加到结果中
        addedAgentLines.add(selectedValue);
      }
    }

    // 将 Set 转为数组
    processedValue = [...addedAgentLines];
  }

  internalValue.value = processedValue;

  // 如果是单选且选择了渠道号，查找对应的项目名称
  let platform: string | undefined;
  if (!props.multiple && typeof processedValue === 'string' && processedValue) {
    platform = findPlatformByAgentLine(processedValue);
  }

  emit('update:modelValue', processedValue);
  emit('update:value', processedValue);
  emit('change', processedValue, platform);
};

onMounted(() => {
  loadOptions();
});

// 监听platform变化，重新加载数据
watch(
  () => props.platform,
  () => {
    loadOptions();
  },
);

// 监听modelValue和value变化，同步到内部值
watch(
  () => props.modelValue || props.value,
  (newValue) => {
    internalValue.value = newValue;
  },
  { immediate: true },
);

// 监听数据加载完成，如果有初始值则设置
watch(
  () => platformAgentData.value,
  (newData) => {
    // 数据加载完成后，如果有值，确保设置到内部值
    const currentValue = props.modelValue || props.value;
    if (newData.length > 0 && currentValue !== undefined) {
      internalValue.value = currentValue;
    }
  },
);

// 监听loading状态变化，数据加载完成后检查是否需要设置值
watch(
  () => loading.value,
  (isLoading) => {
    const currentValue = props.modelValue || props.value;
    if (!isLoading && currentValue !== undefined) {
      internalValue.value = currentValue;
    }
  },
);

// 导出刷新方法
const refresh = () => {
  loadOptions();
};

defineExpose({
  refresh,
  platformAgentData,
});
</script>

<template>
  <div
    :style="{
      display: 'inline-flex',
      alignItems: 'center',
      width: typeof width === 'number' ? `${width}px` : width,
    }"
  >
    <TreeSelect
      :key="platformAgentData.length"
      :value="computedValue"
      :tree-data="treeData"
      :multiple="multiple"
      :show-search="showSearch"
      :allow-clear="allowClear"
      :placeholder="placeholder"
      :style="{ minWidth: '180px', flex: 1, ...style }"
      :disabled="disabled"
      :loading="loading"
      tree-node-filter-prop="title"
      :tree-checkable="multiple"
      :virtual="false"
      :max-tag-count="maxTagCount"
      :dropdown-style="{ maxHeight: '400px', overflow: 'auto' }"
      @change="handleChange"
    />
  </div>
</template>
