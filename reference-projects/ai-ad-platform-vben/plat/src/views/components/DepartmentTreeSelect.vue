<script lang="ts" setup>
import type { SystemDepartmentApi } from '#/api';

import { computed, onMounted, ref } from 'vue';

import { message, TreeSelect } from 'ant-design-vue';

import { getSharedDepartmentTree } from './organization-options-cache';

interface Props {
  modelValue?: string | string[];
  multiple?: boolean;
  placeholder?: string;
  valueMode?: 'id' | 'name';
}

interface DepartmentTreeNode {
  children?: DepartmentTreeNode[];
  disabled?: boolean;
  label: string;
  name: string;
  value: string;
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  multiple: false,
  placeholder: '请选择部门',
  valueMode: 'name',
});
const emit = defineEmits<{
  (event: 'update:modelValue', value: string | string[]): void;
  (
    event: 'change',
    value: string | string[],
    departments: Array<{ id: string; name: string }>,
  ): void;
}>();

const departments = ref<SystemDepartmentApi.Department[]>([]);
const loading = ref(false);

function toTreeNodes(
  nodes: SystemDepartmentApi.Department[],
): DepartmentTreeNode[] {
  return nodes.map((department) => ({
    children: toTreeNodes(department.children ?? []),
    disabled: department.status !== 1,
    label:
      department.status === 1
        ? department.deptName
        : `${department.deptName}（停用）`,
    name: department.deptName,
    value: department.id,
  }));
}

function flattenNodes(nodes: DepartmentTreeNode[]): DepartmentTreeNode[] {
  return nodes.flatMap((node) => [node, ...flattenNodes(node.children ?? [])]);
}

const treeData = computed(() => {
  const nodes = toTreeNodes(departments.value);
  if (props.valueMode === 'id') return nodes;
  const selectedNames = Array.isArray(props.modelValue)
    ? props.modelValue
    : [props.modelValue];
  const departmentNames = new Set(flattenNodes(nodes).map((node) => node.name));
  for (const legacyName of selectedNames.map((name) => name.trim())) {
    if (legacyName && !departmentNames.has(legacyName)) {
      nodes.unshift({
        disabled: true,
        label: `${legacyName}（历史部门）`,
        name: legacyName,
        value: `legacy:${legacyName}`,
      });
    }
  }
  return nodes;
});
const flatNodes = computed(() => flattenNodes(treeData.value));
const selectedValue = computed(() => {
  if (props.valueMode === 'id') return props.modelValue;
  const selectedNames = Array.isArray(props.modelValue)
    ? props.modelValue
    : [props.modelValue];
  const selectedIds = selectedNames
    .map((name) => flatNodes.value.find((node) => node.name === name)?.value)
    .filter((value): value is string => Boolean(value));
  return props.multiple ? selectedIds : selectedIds[0];
});

async function loadDepartments() {
  loading.value = true;
  try {
    departments.value = await getSharedDepartmentTree();
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '部门组织架构加载失败',
    );
  } finally {
    loading.value = false;
  }
}

function handleChange(value: unknown) {
  const ids = (Array.isArray(value) ? value : [value])
    .filter((item) => item !== null && item !== undefined && item !== '')
    .map(String)
    .filter(Boolean);
  const selectedDepartments = ids
    .map((id) => flatNodes.value.find((node) => node.value === id))
    .filter((node): node is DepartmentTreeNode => Boolean(node))
    .map((node) => ({ id: node.value, name: node.name }));
  const selectedValues =
    props.valueMode === 'id'
      ? selectedDepartments.map((department) => department.id)
      : selectedDepartments.map((department) => department.name);
  const nextValue = props.multiple ? selectedValues : (selectedValues[0] ?? '');
  emit('update:modelValue', nextValue);
  emit('change', nextValue, selectedDepartments);
}

onMounted(() => void loadDepartments());
</script>

<template>
  <TreeSelect
    allow-clear
    :loading="loading"
    :multiple="multiple"
    :placeholder="placeholder"
    show-search
    :tree-data="treeData"
    tree-node-filter-prop="label"
    :value="selectedValue"
    @change="handleChange"
  />
</template>
