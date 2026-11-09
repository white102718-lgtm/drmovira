<script setup lang="ts">
import type {
  AdDashboardField,
  AdDashboardSchema,
} from '#/domain/ad-dashboard';

import { computed, ref, watch } from 'vue';

import { Button, Checkbox, message, Modal } from 'ant-design-vue';
import { ArrowDown, ArrowUp, GripVertical } from 'lucide-vue-next';

const props = defineProps<{
  disabled: boolean;
  fields: AdDashboardField[];
  loading: boolean;
  save: (fields: AdDashboardField[], visibleKeys: string[]) => Promise<void>;
  schema: AdDashboardSchema;
  visibleFields: AdDashboardField[];
}>();

const open = ref(false);
const saving = ref(false);
const draftFields = ref<AdDashboardField[]>([]);
const selectedKeys = ref<string[]>([]);
const draggingKey = ref('');
const optionalFields = computed(() =>
  draftFields.value.filter((field) => !field.fixed),
);
const allSelected = computed(() =>
  optionalFields.value.every((field) => selectedKeys.value.includes(field.key)),
);
const someSelected = computed(() =>
  optionalFields.value.some((field) => selectedKeys.value.includes(field.key)),
);

function openSettings() {
  draftFields.value = [...props.fields];
  selectedKeys.value = props.visibleFields.map((field) => field.key);
  open.value = true;
}

function toggleColumn(key: string, checked: boolean) {
  if (draftFields.value.find((field) => field.key === key)?.fixed) return;
  selectedKeys.value = checked
    ? [...new Set([key, ...selectedKeys.value])]
    : selectedKeys.value.filter((item) => item !== key);
}

function selectAll(checked: boolean) {
  selectedKeys.value = checked
    ? draftFields.value.map((field) => field.key)
    : draftFields.value
        .filter((field) => field.fixed)
        .map((field) => field.key);
}

function resetColumns() {
  draftFields.value = [...props.schema.fields];
  selectAll(true);
}

function canMove(index: number, offset: number) {
  const fields = optionalFields.value;
  return Boolean(
    fields[index] &&
      !fields[index]?.fixed &&
      fields[index + offset] &&
      !fields[index + offset]?.fixed,
  );
}

function moveColumn(key: string, targetKey: string) {
  const from = draftFields.value.findIndex((field) => field.key === key);
  const to = draftFields.value.findIndex((field) => field.key === targetKey);
  if (
    from === -1 ||
    to === -1 ||
    draftFields.value[from]?.fixed ||
    draftFields.value[to]?.fixed
  )
    return;
  const next = [...draftFields.value];
  const [field] = next.splice(from, 1);
  if (field) next.splice(to, 0, field);
  draftFields.value = next;
}

function moveBy(index: number, offset: number) {
  const field = optionalFields.value[index];
  const target = optionalFields.value[index + offset];
  if (field && target && canMove(index, offset))
    moveColumn(field.key, target.key);
}

async function confirm() {
  if (saving.value) return;
  saving.value = true;
  try {
    await props.save([...draftFields.value], [...selectedKeys.value]);
    open.value = false;
    message.success('列配置已保存');
  } catch {
    message.error('列配置保存失败，请重试');
  } finally {
    saving.value = false;
  }
}

// 未提交的勾选不会影响表格，也不会带到另一个维度。
watch(
  () => props.schema.category,
  () => {
    open.value = false;
  },
);
</script>

<template>
  <Button
    :disabled="disabled || saving"
    :loading="loading"
    @click="openSettings"
    >自定义列</Button
  >
  <Modal
    v-model:open="open"
    wrap-class-name="ux-fixed-modal"
    :title="`${schema.label} · 自定义列`"
    :width="520"
    :closable="!saving"
    :mask-closable="!saving"
    :keyboard="!saving"
  >
    <p class="text-muted-foreground mb-4 text-sm">
      固定列始终显示并保持左侧顺序。下方可选列支持隐藏或拖动调整，保存后下次打开仍生效。
    </p>
    <div class="mb-2 flex items-center justify-between gap-2">
      <Checkbox
        :checked="allSelected"
        :indeterminate="someSelected && !allSelected"
        :disabled="saving"
        @change="selectAll($event.target.checked ?? false)"
        >全选</Checkbox
      >
      <Button type="link" :disabled="saving" @click="resetColumns"
        >恢复默认</Button
      >
    </div>
    <ul class="rounded-md border p-2" aria-label="列显示与顺序">
      <li
        v-for="(field, index) in optionalFields"
        :key="field.key"
        class="hover:bg-muted flex items-center gap-2 rounded px-2 py-1"
        :draggable="!saving && !field.fixed"
        @dragstart="draggingKey = field.key"
        @dragend="draggingKey = ''"
        @dragover.prevent
        @drop.prevent="moveColumn(draggingKey, field.key)"
      >
        <GripVertical
          class="text-muted-foreground size-4 shrink-0"
          aria-hidden="true"
        />
        <Checkbox
          class="min-w-0 flex-1"
          :checked="selectedKeys.includes(field.key)"
          :disabled="saving"
          @change="toggleColumn(field.key, $event.target.checked ?? false)"
          >{{ field.label }}</Checkbox
        >
        <Button
          type="text"
          :disabled="saving || !canMove(index, -1)"
          :aria-label="`上移${field.label}`"
          @click="moveBy(index, -1)"
          ><ArrowUp class="size-4" aria-hidden="true"
        /></Button>
        <Button
          type="text"
          :disabled="saving || !canMove(index, 1)"
          :aria-label="`下移${field.label}`"
          @click="moveBy(index, 1)"
          ><ArrowDown class="size-4" aria-hidden="true"
        /></Button>
      </li>
    </ul>
    <template #footer>
      <Button :disabled="saving" @click="open = false">取消</Button>
      <Button type="primary" :loading="saving" @click="confirm">保存</Button>
    </template>
  </Modal>
</template>
