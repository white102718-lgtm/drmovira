<script lang="ts" setup>
import type { ApprovalNodeConfig } from '#/api';

import { computed, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Empty,
  FormItem,
  Input,
  RadioButton,
  RadioGroup,
  Select,
  Tag,
} from 'ant-design-vue';

interface UserOption {
  label: string;
  value: string;
}

interface RoleOption {
  label: string;
  value: string;
}

const props = defineProps<{
  ccUserIds: string[];
  handlerId: string;
  modelValue: ApprovalNodeConfig[];
  roleOptions: RoleOption[];
  userOptions: UserOption[];
}>();
const emit = defineEmits<{
  'update:ccUserIds': [value: string[]];
  'update:handlerId': [value: string];
  'update:modelValue': [value: ApprovalNodeConfig[]];
}>();

const selectedIndex = ref(0);
const handlerSource = ref<'approval' | 'independent'>('independent');
const handlerNodeIndex = ref(0);
const handlerSourceInitialized = ref(false);
const selectedNode = computed(() => props.modelValue[selectedIndex.value]);
const selectedApproverType = computed(
  () => selectedNode.value?.approverType ?? 'USERS',
);
const handlerUserName = computed(
  () =>
    props.userOptions.find((item) => item.value === props.handlerId)?.label ??
    '',
);
const approvalHandlerOptions = computed(() =>
  props.modelValue.flatMap((node, index) => {
    let approverIds: string[] = [];
    if (node.approverIds?.length) approverIds = node.approverIds;
    else if (node.approverId) approverIds = [node.approverId];
    if ((node.approverType ?? 'USERS') !== 'USERS' || approverIds.length !== 1)
      return [];
    return [
      {
        label: `${node.name || `审批节点 ${index + 1}`}（${node.approverName || '未配置审批人'}）`,
        value: String(index),
      },
    ];
  }),
);
const handlerSourceLabel = computed(() => {
  if (handlerSource.value === 'independent') return '单独选择处理人';
  const node = props.modelValue[handlerNodeIndex.value];
  return node ? `复用「${node.name}」审批人` : '复用审批节点的审批人';
});

watch(
  [() => props.handlerId, () => props.modelValue.length],
  () => {
    if (handlerSourceInitialized.value) return;
    const matchedIndex = props.modelValue.findIndex(
      (node) =>
        (node.approverType ?? 'USERS') === 'USERS' &&
        (node.approverIds?.length ?? (node.approverId ? 1 : 0)) === 1 &&
        (node.approverIds?.[0] ?? node.approverId) === props.handlerId,
    );
    if (matchedIndex !== -1) {
      handlerSource.value = 'approval';
      handlerNodeIndex.value = matchedIndex;
    }
    handlerSourceInitialized.value = true;
  },
  { immediate: true },
);

watch(
  () => props.modelValue.length,
  (length) => {
    if (selectedIndex.value >= length)
      selectedIndex.value = Math.max(0, length - 1);
  },
);

function defaultNode(index: number): ApprovalNodeConfig {
  const user = props.userOptions[0];
  return {
    approverId: user?.value ?? '',
    approverIds: user ? [user.value] : [],
    approverName: user?.label ?? '',
    approverNames: user ? [user.label] : [],
    approverType: 'USERS',
    name: `审批节点 ${index + 1}`,
    roleIds: [],
    roleNames: [],
  };
}

function replace(nodes: ApprovalNodeConfig[]) {
  emit(
    'update:modelValue',
    nodes.map((node) => ({ ...node })),
  );
}

function insertNode(index: number) {
  const next = [...props.modelValue];
  next.splice(index, 0, defaultNode(index));
  if (handlerSource.value === 'approval' && handlerNodeIndex.value >= index) {
    handlerNodeIndex.value += 1;
  }
  replace(next);
  selectedIndex.value = index;
}

function updateSelected(patch: Partial<ApprovalNodeConfig>) {
  const node = selectedNode.value;
  if (!node) return;
  const next = [...props.modelValue];
  next[selectedIndex.value] = { ...node, ...patch };
  replace(next);
}

function selectedIds(value: unknown) {
  return Array.isArray(value) ? value.map(String) : [];
}

function chooseApprovers(value: unknown) {
  const ids = selectedIds(value);
  const users = ids.flatMap((id) => {
    const user = props.userOptions.find((item) => item.value === id);
    return user ? [user] : [];
  });
  updateSelected({
    approverId: users[0]?.value ?? '',
    approverIds: users.map((user) => user.value),
    approverName: users.map((user) => user.label).join('、'),
    approverNames: users.map((user) => user.label),
    approverType: 'USERS',
    roleIds: [],
    roleNames: [],
  });
  if (
    handlerSource.value === 'approval' &&
    handlerNodeIndex.value === selectedIndex.value
  ) {
    if (users.length === 1) emit('update:handlerId', users[0]?.value ?? '');
    else chooseHandlerSource('independent');
  }
}

function chooseRoles(value: unknown) {
  const ids = selectedIds(value);
  const roles = ids.flatMap((id) => {
    const role = props.roleOptions.find((item) => item.value === id);
    return role ? [role] : [];
  });
  updateSelected({
    approverId: '',
    approverIds: [],
    approverName: roles.map((role) => `角色：${role.label}`).join('、'),
    approverNames: [],
    approverType: 'ROLES',
    roleIds: roles.map((role) => role.value),
    roleNames: roles.map((role) => role.label),
  });
  if (
    handlerSource.value === 'approval' &&
    handlerNodeIndex.value === selectedIndex.value
  ) {
    chooseHandlerSource('independent');
  }
}

function chooseApproverType(value: unknown) {
  const type = value === 'ROLES' ? 'ROLES' : 'USERS';
  if (type === 'USERS') {
    chooseApprovers(props.userOptions[0] ? [props.userOptions[0].value] : []);
    return;
  }
  chooseRoles(props.roleOptions[0] ? [props.roleOptions[0].value] : []);
}

function updateCcUsers(value: unknown) {
  emit('update:ccUserIds', selectedIds(value));
}

function chooseHandlerSource(source: 'approval' | 'independent') {
  handlerSource.value = source;
  if (source !== 'approval') return;
  const matchedIndex = props.modelValue.findIndex(
    (node) =>
      (node.approverType ?? 'USERS') === 'USERS' &&
      (node.approverIds?.length ?? (node.approverId ? 1 : 0)) === 1 &&
      (node.approverIds?.[0] ?? node.approverId) === props.handlerId,
  );
  const fallbackIndex = Number(approvalHandlerOptions.value[0]?.value ?? -1);
  handlerNodeIndex.value = matchedIndex === -1 ? fallbackIndex : matchedIndex;
  if (handlerNodeIndex.value < 0) {
    handlerSource.value = 'independent';
    return;
  }
  chooseHandlerNode(String(handlerNodeIndex.value));
}

function chooseHandlerNode(indexValue: string) {
  const index = Number(indexValue);
  const node = props.modelValue[index];
  if (!node) return;
  handlerNodeIndex.value = index;
  emit('update:handlerId', node.approverIds?.[0] ?? node.approverId);
}

function move(offset: number) {
  const target = selectedIndex.value + offset;
  if (target < 0 || target >= props.modelValue.length) return;
  const next = [...props.modelValue];
  const [node] = next.splice(selectedIndex.value, 1);
  if (!node) return;
  next.splice(target, 0, node);
  if (handlerSource.value === 'approval') {
    if (handlerNodeIndex.value === selectedIndex.value) {
      handlerNodeIndex.value = target;
    } else if (handlerNodeIndex.value === target) {
      handlerNodeIndex.value = selectedIndex.value;
    }
  }
  replace(next);
  selectedIndex.value = target;
}

function remove() {
  if (props.modelValue.length <= 1) return;
  const removedIndex = selectedIndex.value;
  const next = props.modelValue.filter((_, index) => index !== removedIndex);
  if (handlerSource.value === 'approval') {
    if (handlerNodeIndex.value === removedIndex) {
      handlerNodeIndex.value = Math.min(removedIndex, next.length - 1);
      const handlerNode = next[handlerNodeIndex.value];
      if (handlerNode) emit('update:handlerId', handlerNode.approverId);
    } else if (handlerNodeIndex.value > removedIndex) {
      handlerNodeIndex.value -= 1;
    }
  }
  replace(next);
}
</script>

<template>
  <div
    class="grid min-h-[500px] grid-cols-[minmax(620px,1fr)_320px] overflow-hidden rounded-xl border border-slate-200 bg-white"
  >
    <section class="overflow-x-auto bg-slate-100/70 p-6">
      <div class="mb-5 flex items-center justify-between">
        <div>
          <h4 class="m-0 text-base font-semibold text-slate-900">
            审批流程画布
          </h4>
          <p class="mb-0 mt-1 text-xs text-slate-400">
            点击连线上的“+”插入节点，节点按从左到右顺序执行
          </p>
        </div>
        <Tag color="blue">{{ modelValue.length }} 个审批节点</Tag>
      </div>
      <div class="flex min-w-max items-center py-16">
        <div class="flow-terminal bg-emerald-500">
          <IconifyIcon icon="lucide:play" />
          <span>发起申请</span>
        </div>
        <template
          v-for="(node, index) in modelValue"
          :key="`${node.name}-${index}`"
        >
          <div class="flow-link">
            <button type="button" @click="insertNode(index)">
              <IconifyIcon icon="lucide:plus" />
            </button>
          </div>
          <button
            class="flow-node"
            :class="selectedIndex === index ? 'is-selected' : ''"
            type="button"
            @click="selectedIndex = index"
          >
            <span class="flow-node-icon">
              <IconifyIcon icon="lucide:user-check" />
            </span>
            <span class="min-w-0 text-left">
              <strong class="block truncate text-sm text-slate-900">{{
                node.name || `审批节点 ${index + 1}`
              }}</strong>
              <small class="mt-1 block truncate text-slate-500">
                审批人：{{ node.approverName || '未配置' }}
              </small>
            </span>
          </button>
        </template>
        <div class="flow-link">
          <button type="button" @click="insertNode(modelValue.length)">
            <IconifyIcon icon="lucide:plus" />
          </button>
        </div>
        <div class="flow-handler">
          <span class="flow-node-icon is-handler">
            <IconifyIcon icon="lucide:package-check" />
          </span>
          <span class="min-w-0 text-left">
            <strong class="block text-sm text-slate-900">处理与分配</strong>
            <small class="mt-1 block truncate text-slate-500">
              {{ handlerUserName || '未配置处理人' }}
            </small>
            <small class="mt-0.5 block truncate text-amber-600">
              {{ handlerSourceLabel }}
            </small>
          </span>
        </div>
      </div>
      <div class="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p class="mb-1 text-sm font-semibold text-amber-900">唯一流程处理人</p>
        <p class="mb-3 text-xs leading-5 text-amber-700">
          所有审批节点通过后，申请进入该处理人的待办，由其选择资产并完成分配。
        </p>
        <RadioGroup
          :value="handlerSource"
          button-style="solid"
          class="mb-3"
          @update:value="chooseHandlerSource($event)"
        >
          <RadioButton value="approval">选择审批节点的审批人</RadioButton>
          <RadioButton value="independent">单独选择处理人</RadioButton>
        </RadioGroup>
        <Select
          v-if="handlerSource === 'approval'"
          :value="String(handlerNodeIndex)"
          :options="approvalHandlerOptions"
          placeholder="请选择要复用的审批节点"
          class="w-full"
          @update:value="chooseHandlerNode(String($event))"
        />
        <Select
          v-else
          :value="handlerId"
          show-search
          option-filter-prop="label"
          :options="userOptions"
          placeholder="请选择独立处理人"
          class="w-full"
          @update:value="emit('update:handlerId', String($event))"
        />
      </div>
      <div
        class="rounded-lg border border-dashed border-slate-300 bg-white/70 p-4"
      >
        <p class="mb-2 text-xs font-semibold text-slate-500">流程结束后抄送</p>
        <Select
          :value="ccUserIds"
          class="w-full"
          max-tag-count="responsive"
          mode="multiple"
          show-search
          option-filter-prop="label"
          :options="userOptions"
          placeholder="可选；审批结束后生成站内通知"
          @update:value="updateCcUsers"
        />
      </div>
    </section>

    <aside class="border-l border-slate-200 p-4">
      <div class="mb-4 flex items-center justify-between">
        <p class="m-0 text-sm font-semibold text-slate-800">节点属性</p>
        <span v-if="selectedNode" class="text-xs text-slate-400">
          节点 {{ selectedIndex + 1 }}
        </span>
      </div>
      <Empty v-if="!selectedNode" description="请在画布中添加节点" />
      <template v-else>
        <FormItem label="节点名称" required>
          <Input
            :value="selectedNode.name"
            @update:value="updateSelected({ name: String($event) })"
          />
        </FormItem>
        <FormItem label="审批人" required>
          <RadioGroup
            :value="selectedApproverType"
            button-style="solid"
            class="mb-3 w-full"
            @update:value="chooseApproverType($event)"
          >
            <RadioButton value="USERS">指定成员</RadioButton>
            <RadioButton value="ROLES">按角色</RadioButton>
          </RadioGroup>
          <Select
            v-if="selectedApproverType === 'USERS'"
            :value="
              selectedNode.approverIds?.length
                ? selectedNode.approverIds
                : selectedNode.approverId
                  ? [selectedNode.approverId]
                  : []
            "
            class="w-full"
            max-tag-count="responsive"
            mode="multiple"
            show-search
            option-filter-prop="label"
            :options="userOptions"
            placeholder="选择一名或多名审批人；任一人通过即可"
            @update:value="chooseApprovers($event)"
          />
          <Select
            v-else
            :value="selectedNode.roleIds ?? []"
            class="w-full"
            max-tag-count="responsive"
            mode="multiple"
            show-search
            option-filter-prop="label"
            :options="roleOptions"
            placeholder="选择一个或多个角色；任一角色成员通过即可"
            @update:value="chooseRoles($event)"
          />
          <p class="mb-0 mt-2 text-xs leading-5 text-slate-500">
            多人或多角色节点采用或签：任一符合条件的成员审批后，流程进入下一节点。
          </p>
        </FormItem>
        <div class="mt-6 grid grid-cols-2 gap-2">
          <Button :disabled="selectedIndex === 0" @click="move(-1)">
            <IconifyIcon icon="lucide:arrow-left" />前移
          </Button>
          <Button
            :disabled="selectedIndex === modelValue.length - 1"
            @click="move(1)"
          >
            后移<IconifyIcon icon="lucide:arrow-right" />
          </Button>
          <Button
            danger
            class="col-span-2"
            :disabled="modelValue.length <= 1"
            @click="remove"
          >
            <IconifyIcon icon="lucide:trash-2" />删除节点
          </Button>
        </div>
      </template>
    </aside>
  </div>
</template>

<style scoped>
.flow-terminal {
  display: flex;
  height: 72px;
  width: 112px;
  flex-shrink: 0;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 14px;
  color: white;
  box-shadow: 0 8px 20px rgb(15 23 42 / 10%);
}
.flow-link {
  position: relative;
  height: 2px;
  width: 66px;
  flex-shrink: 0;
  background: #93c5fd;
}
.flow-link::after {
  position: absolute;
  right: -2px;
  top: -3px;
  height: 8px;
  width: 8px;
  content: '';
  transform: rotate(45deg);
  border-right: 2px solid #60a5fa;
  border-top: 2px solid #60a5fa;
}
.flow-link button {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 2;
  display: grid;
  height: 24px;
  width: 24px;
  transform: translate(-50%, -50%);
  place-items: center;
  border: 1px solid #93c5fd;
  border-radius: 999px;
  background: white;
  color: #2563eb;
  transition: 0.2s;
}
.flow-link button:hover {
  transform: translate(-50%, -50%) scale(1.12);
  background: #2563eb;
  color: white;
}
.flow-node {
  display: flex;
  height: 98px;
  width: 220px;
  flex-shrink: 0;
  align-items: center;
  gap: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 14px;
  background: white;
  padding: 14px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 7%);
  transition: 0.2s;
}
.flow-handler {
  display: flex;
  height: 98px;
  width: 220px;
  flex-shrink: 0;
  align-items: center;
  gap: 12px;
  border: 1px solid #fde68a;
  border-radius: 14px;
  background: #fffbeb;
  padding: 14px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 7%);
}
.flow-node:hover,
.flow-node.is-selected {
  border-color: hsl(var(--foreground));
  box-shadow:
    0 0 0 3px hsl(var(--muted)),
    0 10px 26px rgb(0 0 0 / 8%);
}
.flow-node-icon {
  display: grid;
  height: 40px;
  width: 40px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 12px;
  background: hsl(var(--muted));
  color: hsl(var(--foreground));
  font-size: 18px;
}
.flow-node-icon.is-handler {
  background: #fef3c7;
  color: #d97706;
}
</style>
