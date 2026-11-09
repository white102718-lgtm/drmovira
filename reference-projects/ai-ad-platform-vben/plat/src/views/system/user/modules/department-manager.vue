<script lang="ts" setup>
import type { SystemDepartmentApi } from '#/api';

import { computed, onMounted, ref } from 'vue';

import { Input, Spin, Tree } from 'ant-design-vue';

import { getSystemDepartmentTree } from '#/api';

const emit = defineEmits<{
  loaded: [departments: SystemDepartmentApi.Department[]];
  select: [id: string | undefined];
}>();

const departments = ref<SystemDepartmentApi.Department[]>([]);
const expandedKeys = ref<string[]>([]);
const loading = ref(false);
const searchValue = ref('');
const selectedKeys = ref<string[]>([]);

function allKeys(nodes: SystemDepartmentApi.Department[]): string[] {
  return nodes.flatMap((node) => [node.id, ...allKeys(node.children ?? [])]);
}

function filterTree(
  nodes: SystemDepartmentApi.Department[],
  keyword: string,
): SystemDepartmentApi.Department[] {
  if (!keyword.trim()) return nodes;
  return nodes.reduce<SystemDepartmentApi.Department[]>((result, node) => {
    const children = filterTree(node.children ?? [], keyword);
    if (
      node.deptName.toLowerCase().includes(keyword.trim().toLowerCase()) ||
      children.length > 0
    ) {
      result.push({ ...node, children });
    }
    return result;
  }, []);
}

function toTreeData(nodes: SystemDepartmentApi.Department[]): any[] {
  return nodes.map((node) => ({
    children: toTreeData(node.children ?? []),
    department: node,
    key: node.id,
    title: node.deptName,
  }));
}

const treeData = computed(() =>
  toTreeData(filterTree(departments.value, searchValue.value)),
);

async function load() {
  loading.value = true;
  try {
    departments.value = await getSystemDepartmentTree();
    emit('loaded', departments.value);
    expandedKeys.value = allKeys(departments.value);
  } finally {
    loading.value = false;
  }
}

function onSelect(keys: Array<number | string>, { selected, node }: any) {
  selectedKeys.value = keys.map(String);
  emit(
    'select',
    selected
      ? (node.department as SystemDepartmentApi.Department).id
      : undefined,
  );
}

onMounted(load);
</script>

<template>
  <div
    class="border-border bg-card flex h-full min-h-0 flex-col overflow-hidden rounded-md border p-3"
  >
    <Input
      v-model:value="searchValue"
      allow-clear
      class="mb-3 shrink-0"
      placeholder="搜索部门"
    />
    <!-- 使用独立容器约束树的滚动范围，避免 Spin 将样式应用到加载指示器。 -->
    <div class="min-h-0 flex-1 overflow-auto">
      <Spin :spinning="loading" wrapper-class-name="min-h-32">
        <Tree
          v-if="treeData.length"
          v-model:expanded-keys="expandedKeys"
          :selected-keys="selectedKeys"
          :tree-data="treeData"
          block-node
          @select="onSelect"
        />
        <div
          v-else-if="!loading"
          class="text-muted-foreground py-8 text-center"
        >
          暂无部门数据
        </div>
      </Spin>
    </div>
  </div>
</template>
