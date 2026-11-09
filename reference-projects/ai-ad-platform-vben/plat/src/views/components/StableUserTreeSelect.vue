<script lang="ts" setup>
import type { SystemDepartmentApi, SystemUserApi } from '#/api';
import type { DepartmentScopeUserOption } from '#/api/system/user';

import { computed, onMounted, ref } from 'vue';

import { message, TreeSelect } from 'ant-design-vue';

import {
  getSharedDepartmentTree,
  getSharedOrganizationUsers,
} from './organization-options-cache';

interface Props {
  legacyLabel?: string;
  modelValue?: string | string[];
  multiple?: boolean;
  placeholder?: string;
}

interface Emits {
  (
    event: 'change',
    value: string | string[] | undefined,
    user?: DepartmentScopeUserOption,
    users?: DepartmentScopeUserOption[],
  ): void;
  (event: 'update:modelValue', value: string | string[] | undefined): void;
}

interface UserTreeNode {
  children?: UserTreeNode[];
  disabled?: boolean;
  label: string;
  selectable?: boolean;
  value: string;
}

const props = withDefaults(defineProps<Props>(), {
  legacyLabel: '',
  modelValue: undefined,
  multiple: false,
  placeholder: '请选择用户',
});
const emit = defineEmits<Emits>();

const departments = ref<SystemDepartmentApi.Department[]>([]);
const loading = ref(false);
const users = ref<SystemUserApi.User[]>([]);

function getUserName(user: SystemUserApi.User) {
  return (
    user.realName?.trim() ||
    user.displayName.trim() ||
    user.username?.trim() ||
    user.id
  );
}

function buildDepartmentNodes(
  nodes: SystemDepartmentApi.Department[],
  usersByDepartment: Map<string, SystemUserApi.User[]>,
): UserTreeNode[] {
  return nodes.map((department) => ({
    children: [
      ...buildDepartmentNodes(department.children ?? [], usersByDepartment),
      ...(usersByDepartment.get(department.id) ?? []).map((user) => ({
        disabled: user.status !== 1,
        label: getUserName(user),
        value: user.id,
      })),
    ],
    label:
      department.status === 1
        ? department.deptName
        : `${department.deptName}（停用）`,
    selectable: false,
    value: `department:${department.id}`,
  }));
}

function collectDepartmentIds(
  nodes: SystemDepartmentApi.Department[],
): Set<string> {
  return new Set(
    nodes.flatMap((node) => [
      node.id,
      ...collectDepartmentIds(node.children ?? []),
    ]),
  );
}

const treeData = computed<UserTreeNode[]>(() => {
  const usersByDepartment = new Map<string, SystemUserApi.User[]>();
  const unassignedUsers: SystemUserApi.User[] = [];
  const departmentIds = collectDepartmentIds(departments.value);
  users.value.forEach((user) => {
    if (
      !user.primaryDepartmentId ||
      !departmentIds.has(user.primaryDepartmentId)
    ) {
      unassignedUsers.push(user);
      return;
    }
    const departmentUsers =
      usersByDepartment.get(user.primaryDepartmentId) ?? [];
    departmentUsers.push(user);
    usersByDepartment.set(user.primaryDepartmentId, departmentUsers);
  });

  const nodes = buildDepartmentNodes(departments.value, usersByDepartment);
  if (unassignedUsers.length) {
    nodes.push({
      children: unassignedUsers.map((user) => ({
        disabled: user.status !== 1,
        label: getUserName(user),
        value: user.id,
      })),
      label: '未分配部门',
      selectable: false,
      value: 'department:unassigned',
    });
  }

  const selectedUserIds = (
    Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue]
  ).filter((userId): userId is string => Boolean(userId?.trim()));
  const legacyUserIds = selectedUserIds.filter(
    (userId) => !users.value.some((user) => user.id === userId),
  );
  if (legacyUserIds.length) {
    nodes.unshift({
      children: legacyUserIds.map((userId, index) => ({
        disabled: true,
        label: (index === 0 && props.legacyLabel) || userId,
        value: userId,
      })),
      label: '历史负责人',
      selectable: false,
      value: 'department:legacy',
    });
  }
  return nodes;
});

async function loadOptions() {
  loading.value = true;
  try {
    const [departmentTree, allUsers] = await Promise.all([
      getSharedDepartmentTree(),
      getSharedOrganizationUsers(),
    ]);
    departments.value = departmentTree;
    users.value = allUsers;
  } catch (error) {
    message.error(
      error instanceof Error ? error.message : '用户组织架构加载失败',
    );
  } finally {
    loading.value = false;
  }
}

function handleChange(value: unknown) {
  const userIds = (Array.isArray(value) ? value : [value]).filter(
    (userId): userId is string => typeof userId === 'string',
  );
  const selectedUsers = userIds.flatMap((userId) => {
    const user = users.value.find((item) => item.id === userId);
    return user
      ? [
          {
            available: user.status === 1,
            label: getUserName(user),
            name: getUserName(user),
            userId: user.id,
          },
        ]
      : [];
  });
  const nextValue = props.multiple ? userIds : userIds[0];
  emit('update:modelValue', nextValue);
  emit('change', nextValue, selectedUsers[0], selectedUsers);
}

onMounted(() => void loadOptions());
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
    :value="modelValue"
    @change="handleChange"
  />
</template>
