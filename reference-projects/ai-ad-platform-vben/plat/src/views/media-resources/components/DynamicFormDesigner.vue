<script lang="ts" setup>
import type { DynamicFieldType, DynamicFormField } from '#/api';

import { computed, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Checkbox,
  DatePicker,
  Empty,
  FormItem,
  Input,
  InputNumber,
  Select,
} from 'ant-design-vue';

const props = defineProps<{ modelValue: DynamicFormField[] }>();
const emit = defineEmits<{
  'update:modelValue': [value: DynamicFormField[]];
}>();

const selectedIndex = ref(0);
const fieldLibrary: Array<{
  icon: string;
  label: string;
  type: DynamicFieldType;
}> = [
  { icon: 'lucide:text-cursor-input', label: '单行文本', type: 'text' },
  { icon: 'lucide:align-left', label: '多行文本', type: 'textarea' },
  { icon: 'lucide:hash', label: '数字', type: 'number' },
  { icon: 'lucide:chevrons-up-down', label: '下拉框', type: 'select' },
  { icon: 'lucide:list-checks', label: '多选框', type: 'multi-select' },
  { icon: 'lucide:calendar-days', label: '日期', type: 'date' },
];
const fieldTypes = fieldLibrary.map(({ label, type }) => ({
  label,
  value: type,
}));
const validationRuleOptions = [
  { label: '数字 ID 列表（分号分隔）', value: 'digit-list' },
  { label: '像素名称:像素ID 列表', value: 'pixel-list' },
];
const fieldIndexClass =
  'absolute -left-2 -top-2 hidden rounded bg-blue-600 px-1.5 py-0.5 text-[10px] text-white group-hover:block';
const selectedField = computed(() => props.modelValue[selectedIndex.value]);

watch(
  () => props.modelValue.length,
  (length) => {
    if (selectedIndex.value >= length)
      selectedIndex.value = Math.max(0, length - 1);
  },
);

function replace(fields: DynamicFormField[]) {
  emit(
    'update:modelValue',
    fields.map((field) => ({
      ...field,
      options: field.options ? [...field.options] : undefined,
    })),
  );
}

function addField(type: DynamicFieldType) {
  const meta = fieldLibrary.find((item) => item.type === type)!;
  const next = [...props.modelValue];
  next.push({
    key: `field_${Date.now()}`,
    label: meta.label,
    options: ['multi-select', 'select'].includes(type)
      ? ['选项一', '选项二']
      : undefined,
    placeholder: `请输入${meta.label}`,
    required: false,
    type,
  });
  replace(next);
  selectedIndex.value = next.length - 1;
}

function updateSelected(patch: Partial<DynamicFormField>) {
  const field = selectedField.value;
  if (!field) return;
  const next = [...props.modelValue];
  next[selectedIndex.value] = { ...field, ...patch };
  replace(next);
}

function moveSelected(offset: number) {
  const target = selectedIndex.value + offset;
  if (target < 0 || target >= props.modelValue.length) return;
  const next = [...props.modelValue];
  const [field] = next.splice(selectedIndex.value, 1);
  if (!field) return;
  next.splice(target, 0, field);
  replace(next);
  selectedIndex.value = target;
}

function removeSelected() {
  const next = props.modelValue.filter(
    (_, index) => index !== selectedIndex.value,
  );
  replace(next);
}

function updateOptions(value: string) {
  updateSelected({
    options: value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  });
}

function updateFieldType(value: unknown) {
  const type = value as DynamicFieldType;
  updateSelected({
    options:
      ['multi-select', 'select'].includes(type) &&
      !selectedField.value?.options?.length
        ? ['选项一', '选项二']
        : selectedField.value?.options,
    type,
  });
}

function updateValidationRule(value: unknown) {
  updateSelected({
    validationRule: value
      ? (String(value) as DynamicFormField['validationRule'])
      : undefined,
  });
}

function updateMaxLength(value: unknown) {
  const maxLength = Number(value);
  updateSelected({
    maxLength:
      Number.isInteger(maxLength) && maxLength > 0 ? maxLength : undefined,
  });
}
</script>

<template>
  <div
    class="border-border bg-card grid min-h-[var(--adpulse-popup-table-height)] grid-cols-1 overflow-hidden rounded-[var(--adpulse-card-radius)] border lg:grid-cols-[140px_minmax(320px,1fr)_260px]"
  >
    <aside
      class="border-border bg-muted/50 border-b p-3 lg:border-b-0 lg:border-r"
    >
      <p class="text-muted-foreground mb-3 text-xs font-semibold">基础控件</p>
      <button
        v-for="item in fieldLibrary"
        :key="item.type"
        class="mb-2 flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-left text-sm text-slate-700 transition hover:border-blue-400 hover:text-blue-600"
        type="button"
        @click="addField(item.type)"
      >
        <IconifyIcon :icon="item.icon" class="text-base" />
        {{ item.label }}
      </button>
      <p class="mb-0 mt-4 text-xs leading-5 text-slate-400">
        点击控件即可加入画布；画布字段支持排序和属性配置。
      </p>
    </aside>

    <section class="bg-muted/60 p-[var(--adpulse-card-padding)]">
      <div
        class="border-border bg-card mx-auto min-h-[var(--adpulse-popup-table-height)] max-w-[680px] rounded-[var(--adpulse-card-radius)] border p-[var(--adpulse-card-padding)] shadow-[var(--adpulse-card-shadow)]"
      >
        <div class="mb-5 border-b border-slate-100 pb-4">
          <h4 class="m-0 text-base font-semibold text-slate-900">
            申请表单预览
          </h4>
          <p class="mb-0 mt-1 text-xs text-slate-400">
            申请人实际填写时将按以下顺序展示
          </p>
        </div>
        <Empty
          v-if="modelValue.length === 0"
          description="从左侧添加表单控件"
        />
        <div
          v-for="(field, index) in modelValue"
          :key="`${field.key}-${index}`"
          class="group relative mb-3 cursor-pointer rounded-lg border bg-white p-4 transition"
          :class="
            selectedIndex === index
              ? 'border-blue-500 ring-2 ring-blue-100'
              : 'border-slate-200 hover:border-blue-300'
          "
          @click="selectedIndex = index"
        >
          <span :class="fieldIndexClass">{{ index + 1 }}</span>
          <FormItem class="!mb-0" :required="field.required">
            <template #label>{{ field.label || '未命名字段' }}</template>
            <Input
              v-if="field.type === 'text'"
              disabled
              :placeholder="field.placeholder || '请输入'"
            />
            <Input.TextArea
              v-else-if="field.type === 'textarea'"
              disabled
              :placeholder="field.placeholder || '请输入'"
              :rows="3"
            />
            <InputNumber
              v-else-if="field.type === 'number'"
              disabled
              class="!w-full"
              :placeholder="field.placeholder || '请输入数字'"
            />
            <Select
              v-else-if="['multi-select', 'select'].includes(field.type)"
              disabled
              :mode="field.type === 'multi-select' ? 'multiple' : undefined"
              :options="
                (field.options ?? []).map((option) => ({
                  label: option,
                  value: option,
                }))
              "
              placeholder="请选择"
            />
            <DatePicker
              v-else
              disabled
              class="!w-full"
              placeholder="请选择日期"
            />
          </FormItem>
        </div>
      </div>
    </section>

    <aside class="border-l border-slate-200 p-4">
      <div class="mb-4 flex items-center justify-between">
        <p class="m-0 text-sm font-semibold text-slate-800">字段属性</p>
        <span v-if="selectedField" class="text-xs text-slate-400">
          第 {{ selectedIndex + 1 }} 项
        </span>
      </div>
      <Empty v-if="!selectedField" description="请选择画布字段" />
      <template v-else>
        <FormItem label="字段名称" required>
          <Input
            :value="selectedField.label"
            @update:value="updateSelected({ label: String($event) })"
          />
        </FormItem>
        <FormItem label="字段标识" required>
          <Input
            :value="selectedField.key"
            @update:value="updateSelected({ key: String($event) })"
          />
        </FormItem>
        <FormItem label="控件类型">
          <Select
            :value="selectedField.type"
            :options="fieldTypes"
            @update:value="updateFieldType"
          />
        </FormItem>
        <FormItem label="占位提示">
          <Input
            :value="selectedField.placeholder"
            @update:value="updateSelected({ placeholder: String($event) })"
          />
        </FormItem>
        <FormItem
          v-if="['text', 'textarea'].includes(selectedField.type)"
          label="格式校验"
        >
          <Select
            allow-clear
            :value="selectedField.validationRule"
            :options="validationRuleOptions"
            placeholder="不限制格式"
            @update:value="updateValidationRule"
          />
        </FormItem>
        <FormItem
          v-if="['text', 'textarea'].includes(selectedField.type)"
          label="最大长度"
        >
          <InputNumber
            :max="10_000"
            :min="1"
            :precision="0"
            :value="selectedField.maxLength"
            class="!w-full"
            placeholder="不限制"
            @update:value="updateMaxLength"
          />
        </FormItem>
        <FormItem
          v-if="['multi-select', 'select'].includes(selectedField.type)"
          label="选项（逗号分隔）"
        >
          <Input
            :value="selectedField.options?.join(',')"
            @update:value="updateOptions(String($event))"
          />
        </FormItem>
        <Checkbox
          :checked="selectedField.required"
          @update:checked="updateSelected({ required: Boolean($event) })"
        >
          设为必填
        </Checkbox>
        <div class="mt-6 grid grid-cols-2 gap-2">
          <Button :disabled="selectedIndex === 0" @click="moveSelected(-1)">
            <IconifyIcon icon="lucide:arrow-up" />上移
          </Button>
          <Button
            :disabled="selectedIndex === modelValue.length - 1"
            @click="moveSelected(1)"
          >
            <IconifyIcon icon="lucide:arrow-down" />下移
          </Button>
          <Button danger class="col-span-2" @click="removeSelected">
            <IconifyIcon icon="lucide:trash-2" />删除字段
          </Button>
        </div>
      </template>
    </aside>
  </div>
</template>
