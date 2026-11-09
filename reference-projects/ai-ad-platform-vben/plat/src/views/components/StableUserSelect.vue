<script lang="ts" setup>
import type { DepartmentScopeUserOption } from '#/api/system/user';

import { computed, ref, watch } from 'vue';

import { Select } from 'ant-design-vue';

import { getTaskAssigneeNames } from '#/api/system/user';

import { getSharedOrganizationUsers } from './organization-options-cache';

interface Props {
  allowClear?: boolean;
  /** When no stable id is present, resolve a unique user from the legacy display name. */
  autoSelectLegacyLabel?: boolean;
  disabled?: boolean;
  getPopupContainer?: (triggerNode: HTMLElement) => HTMLElement;
  /** 任务分配时按 ERP 角色加载候选人；未传时保持原通用用户选择逻辑。 */
  assignmentRole?: 'creator' | 'operator';
  /** Display text for a persisted legacy name when its stable id is absent. */
  legacyLabel?: string;
  modelValue?: string | string[] | undefined;
  multiple?: boolean;
  open?: boolean;
  placeholder?: string;
}

interface Emits {
  (
    event: 'change',
    value: string | string[] | undefined,
    user?: DepartmentScopeUserOption,
  ): void;
  (event: 'loadError'): void;
  (event: 'openChange', open: boolean): void;
  (event: 'update:modelValue', value: string | string[] | undefined): void;
}

const props = withDefaults(defineProps<Props>(), {
  allowClear: true,
  assignmentRole: undefined,
  autoSelectLegacyLabel: false,
  disabled: false,
  legacyLabel: '',
  modelValue: undefined,
  multiple: false,
  open: undefined,
  placeholder: '请选择用户',
});

const emit = defineEmits<Emits>();

const loading = ref(false);
const loadFailed = ref(false);
const selectRef = ref<InstanceType<typeof Select>>();
const users = ref<DepartmentScopeUserOption[]>([]);

function toSelectOption(user: DepartmentScopeUserOption) {
  return {
    disabled: !user.available,
    label: user.available ? user.label : `${user.label}（负责人不可用）`,
    value: user.userId,
  };
}

const options = computed(() => {
  const selected = (
    Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue]
  ).filter(
    (value): value is string =>
      typeof value === 'string' && Boolean(value.trim()),
  );
  const unavailable = selected.filter(
    (value) => !users.value.some((user) => user.userId === value),
  );
  if (unavailable.length === 0) {
    return users.value.map((user) => toSelectOption(user));
  }
  return [
    ...unavailable.map((value) => ({
      disabled: true,
      label: `${props.legacyLabel || value}（负责人不可用）`,
      value,
    })),
    ...users.value.map((user) => toSelectOption(user)),
  ];
});

async function loadUsers() {
  loading.value = true;
  loadFailed.value = false;
  try {
    if (props.assignmentRole) {
      const names = await getTaskAssigneeNames(props.assignmentRole);
      users.value = names.map((name) => ({
        available: true,
        label: name,
        name,
        // 素材工单的 designers 保持存储 display_name，候选接口也只返回该字段。
        userId: name,
      }));
      return;
    }

    const organizationUsers = await getSharedOrganizationUsers();
    users.value = organizationUsers.map((user) => ({
      available: user.status === 1,
      label: user.displayName,
      name: user.displayName,
      userId: user.id,
    }));
  } catch {
    users.value = [];
    loadFailed.value = true;
    emit('loadError');
  } finally {
    loading.value = false;
  }
}

function handleChange(value: string | string[] | undefined) {
  const selected = Array.isArray(value) ? value[0] : value;
  const user = users.value.find((item) => item.userId === selected);
  emit('update:modelValue', value);
  emit('change', value, user);
}

function resolveLegacyUser() {
  if (
    !props.autoSelectLegacyLabel ||
    (Array.isArray(props.modelValue)
      ? props.modelValue.length > 0
      : Boolean(props.modelValue?.trim())) ||
    !props.legacyLabel.trim()
  ) {
    return;
  }
  const legacyLabel = props.legacyLabel.trim();
  const matches = users.value.filter(
    (user) =>
      user.name.trim() === legacyLabel || user.label.trim() === legacyLabel,
  );
  if (matches.length !== 1 || !matches[0]?.available) return;
  emit('update:modelValue', matches[0].userId);
  emit('change', matches[0].userId, matches[0]);
}

watch(
  () => [props.legacyLabel, props.modelValue, users.value] as const,
  resolveLegacyUser,
  { flush: 'post' },
);

watch(
  () => props.assignmentRole,
  () => void loadUsers(),
  { immediate: true },
);

defineExpose({
  focus: () => {
    const element = selectRef.value?.$el as HTMLElement | undefined;
    element?.querySelector<HTMLInputElement>('input')?.focus();
  },
  reload: loadUsers,
});
</script>

<template>
  <Select
    ref="selectRef"
    class="w-full"
    :allow-clear="allowClear"
    :disabled="disabled"
    :get-popup-container="getPopupContainer"
    :loading="loading"
    :value="modelValue"
    :style="{ width: '100%' }"
    :mode="multiple ? 'multiple' : undefined"
    :not-found-content="loadFailed ? '用户列表加载失败' : undefined"
    :options="options"
    :open="open"
    :placeholder="placeholder"
    option-filter-prop="label"
    show-search
    @dropdown-visible-change="emit('openChange', $event)"
    @change="
      (value) =>
        handleChange(
          Array.isArray(value)
            ? value.filter((item): item is string => typeof item === 'string')
            : typeof value === 'string'
              ? value
              : undefined,
        )
    "
  />
</template>
